"""The closed request schema, outcome codes and fixed statements (context/p4_interface.md §3, §6).

One validator serves the CLI and the API alike, so the two surfaces cannot
drift: the API hands the raw JSON body to :func:`parse_request` rather than to
a second, framework-specific model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from scheduler_core import features

# --------------------------------------------------------------------------- #
# Vocabulary.
# --------------------------------------------------------------------------- #

TRUSTED_EVENTS: tuple[str, ...] = ("push", "pull_request", "workflow_dispatch", "schedule")
SCENARIOS: tuple[str, ...] = ("gb-hypothetical",)
EVALUATED_REGION = "GB"
REF_TYPES: tuple[str, ...] = ("branch", "tag")

#: How far ahead of the clock an arrival may be (clock skew), interface §3.
MAX_FUTURE_SKEW = timedelta(minutes=5)
#: Hard ceiling on a supplied history list, whatever the team's `history_cap`.
MAX_HISTORY_ENTRIES = 1000

FAIL_SAFE_CODES: tuple[str, ...] = (
    "invalid_request", "untrusted_event", "config_invalid", "region_mismatch", "region_not_gb",
    "scenario_invalid", "deadline_invalid", "arrival_in_future", "spec_unavailable",
    "profile_unavailable", "estimator_unavailable", "history_unavailable", "api_unreachable",
    "internal_error",
)
VETO_CODES: tuple[str, ...] = (
    "redispatched_run", "cold_start", "tag_ref", "event_vetoed", "extra_protected_branch",
    "urgent_marker", "exceeds_deadline", "exceeds_max_delay",
)
OUTCOME_KINDS: tuple[str, ...] = ("policy", "veto", "fail_safe", "not_advised")

NULL_STATEMENT = (
    "SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; "
    "results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration "
    "estimate from completed history only."
)

#: DL-033 R3-C11 — printed on every output.
STATEMENTS: tuple[str, ...] = (
    "Recommendation only: the advisor never pauses, cancels or fails a build.",
    "Carbon figures are estimates under a constant-power energy model, not measurements.",
    "Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.",
    "Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.",
    "GitHub Actions run wall-clock time is a different measure from Travis tr_duration.",
    "The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).",
    "Manual and scheduled runs are vetoed by team policy, not detected as urgent.",
)

SCENARIO_BANNER = (
    "SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend "
    "if the build ran on GB compute."
)

# --------------------------------------------------------------------------- #
# Field rules.
# --------------------------------------------------------------------------- #

_REPO_RE = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
_WORKFLOW_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}\.ya?ml$")
_REGION_RE = re.compile(r"^[A-Za-z0-9-]{2,32}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

REQUIRED_FIELDS: tuple[str, ...] = (
    "repository", "workflow", "event", "ref_type", "branch", "is_pr", "arrival_utc", "compute_region",
)
OPTIONAL_FIELDS: tuple[str, ...] = (
    "scenario", "deadline_utc", "head_sha", "run_id", "run_attempt", "redispatch_key",
    "head_commit_message", "repo_language", "history",
)

#: Stage-1 inputs that also appear as an SE feature. `is_pr` is in F6, but it is
#: the `gh_is_pr` input of the frozen eligibility gate, which decide() consumes
#: (DL-020), so it is a required request field rather than a rejected one.
STAGE1_INPUTS_IN_FAMILIES: frozenset[str] = frozenset({"is_pr"})

#: The SE feature names (features.FAMILIES) the advisor rejects (R3-B2): all 28
#: except the Stage-1 input above.
SE_FEATURE_NAMES: frozenset[str] = frozenset(
    name for members in features.FAMILIES.values() for name in members) - STAGE1_INPUTS_IN_FAMILIES

#: The current run's own outcome, under the names a CI event or a careless caller would use.
CURRENT_OUTCOME_NAMES: frozenset[str] = frozenset({"p_hat", "duration_s", "conclusion", "status"})


class RequestError(ValueError):
    """A request the advisor cannot advise on. ``code`` is the fail-safe code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AdviceRequest:
    """A validated request. Times are timezone-aware UTC."""

    repository: str
    workflow: str
    event: str
    ref_type: str
    branch: str
    is_pr: bool
    arrival: datetime
    compute_region: str
    scenario: str | None = None
    deadline: datetime | None = None
    head_sha: str | None = None
    run_id: int | None = None
    run_attempt: int | None = None
    redispatch_key: str | None = None
    head_commit_message: str | None = None
    repo_language: str | None = None
    history: tuple[Mapping[str, Any], ...] | None = None

    def idempotency_key(self) -> str | None:
        if self.head_sha is None:
            return None
        return f"{self.repository}|{self.workflow}|{self.head_sha}|{self.run_attempt or 1}"


def parse_utc(value: Any, field: str) -> datetime:
    """ISO-8601 with an explicit offset (or Z) → aware UTC datetime."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must carry a UTC offset or 'Z': {value!r}")
    return parsed.astimezone(timezone.utc)


def _bad(message: str) -> RequestError:
    return RequestError("invalid_request", message)


def _str_field(raw: Mapping[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise _bad(f"{key} must be a string")
    return value


def _opt_int(raw: Mapping[str, Any], key: str) -> int | None:
    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _bad(f"{key} must be an integer >= 1")
    return value


def parse_request(raw: Any, *, now: datetime) -> AdviceRequest:
    """Validate a raw request mapping. Raises :class:`RequestError` with a fail-safe code."""
    if not isinstance(raw, Mapping):
        raise _bad("request must be a JSON object")

    keys = {str(k) for k in raw}
    leaked = sorted(k for k in keys if features.is_blocklisted(k) or k in CURRENT_OUTCOME_NAMES)
    if leaked:
        raise _bad(f"request carries outcome field(s) {leaked}; the current run's duration and "
                   f"outcome never reach a decision (eval_protocol.md §A1.2)")
    se = sorted(keys & SE_FEATURE_NAMES)
    if se:
        raise _bad(f"request carries SE feature field(s) {se}; they were evaluated and not admitted, "
                   f"so the advisor accepts none (DL-033 R3-B2)")
    unknown = sorted(keys - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    if unknown:
        raise _bad(f"unknown field(s) {unknown}; the request schema is closed")
    missing = [k for k in REQUIRED_FIELDS if k not in raw or raw[k] is None]
    if missing:
        raise _bad(f"missing required field(s) {missing}")

    repository = _str_field(raw, "repository")
    if not _REPO_RE.match(repository):
        raise _bad("repository must look like owner/name")
    workflow = _str_field(raw, "workflow")
    if not _WORKFLOW_RE.match(workflow):
        raise _bad("workflow must be a workflow file name ending in .yml or .yaml")
    event = _str_field(raw, "event")
    ref_type = _str_field(raw, "ref_type")
    if ref_type not in REF_TYPES:
        raise _bad(f"ref_type must be one of {REF_TYPES}")
    branch = _str_field(raw, "branch")
    if not 1 <= len(branch) <= 255 or _CONTROL_RE.search(branch):
        raise _bad("branch must be 1-255 characters with no control characters")
    is_pr = raw["is_pr"]
    if not isinstance(is_pr, bool):
        raise _bad("is_pr must be a boolean")
    compute_region = _str_field(raw, "compute_region")
    if not _REGION_RE.match(compute_region):
        raise _bad("compute_region must be 2-32 letters, digits or hyphens")

    scenario = raw.get("scenario")
    if scenario is not None and not isinstance(scenario, str):
        raise _bad("scenario must be a string")
    head_sha = raw.get("head_sha")
    if head_sha is not None and (not isinstance(head_sha, str) or not _SHA_RE.match(head_sha)):
        raise _bad("head_sha must be 40 lowercase hex characters")
    run_id = _opt_int(raw, "run_id")
    run_attempt = _opt_int(raw, "run_attempt")
    redispatch_key = raw.get("redispatch_key")
    if redispatch_key is not None and (not isinstance(redispatch_key, str) or not 1 <= len(redispatch_key) <= 200
                                       or _CONTROL_RE.search(redispatch_key)):
        raise _bad("redispatch_key must be a 1-200 character string")
    message = raw.get("head_commit_message")
    if message is not None and (not isinstance(message, str) or len(message) > 4096):
        raise _bad("head_commit_message must be a string of at most 4096 characters")
    language = raw.get("repo_language")
    if language is not None and (not isinstance(language, str) or len(language) > 64):
        raise _bad("repo_language must be a short string")
    history = raw.get("history")
    if history is not None:
        if not isinstance(history, list) or not all(isinstance(h, Mapping) for h in history):
            raise _bad("history must be a list of objects")
        if len(history) > MAX_HISTORY_ENTRIES:
            raise _bad(f"history has {len(history)} entries; at most {MAX_HISTORY_ENTRIES} are accepted")

    try:
        arrival = parse_utc(raw["arrival_utc"], "arrival_utc")
    except ValueError as exc:
        raise _bad(str(exc)) from exc

    # Step 2 of the fixed order: the event must be trusted.
    if event not in TRUSTED_EVENTS:
        raise RequestError("untrusted_event",
                           f"event {event!r} is not trusted; only {TRUSTED_EVENTS} are advised")
    if is_pr != (event == "pull_request"):
        raise _bad(f"is_pr={is_pr} disagrees with event={event!r}")

    if scenario is not None:
        if scenario not in SCENARIOS:
            raise RequestError("scenario_invalid", f"scenario must be one of {SCENARIOS}")
        if compute_region != EVALUATED_REGION:
            raise RequestError("scenario_invalid",
                               "scenario gb-hypothetical requires compute_region: GB")

    if arrival > now + MAX_FUTURE_SKEW:
        raise RequestError("arrival_in_future",
                           f"arrival_utc {arrival.isoformat()} is ahead of the clock ({now.isoformat()})")

    deadline = None
    if raw.get("deadline_utc") is not None:
        try:
            deadline = parse_utc(raw["deadline_utc"], "deadline_utc")
        except ValueError as exc:
            raise RequestError("deadline_invalid", str(exc)) from exc
        if deadline <= arrival:
            raise RequestError("deadline_invalid", "deadline_utc must be after arrival_utc")

    return AdviceRequest(
        repository=repository, workflow=workflow, event=event, ref_type=ref_type, branch=branch,
        is_pr=is_pr, arrival=arrival, compute_region=compute_region, scenario=scenario,
        deadline=deadline, head_sha=head_sha, run_id=run_id, run_attempt=run_attempt,
        redispatch_key=redispatch_key, head_commit_message=message, repo_language=language,
        history=tuple(history) if history is not None else None,
    )

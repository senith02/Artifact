"""The re-dispatch reference demonstration (DL-033 R3-C10, as read by DL-038 §6 and §8).

*Deferred re-dispatch, not pausing.* Two halves, both opt-in:

- **Recording**, in the advisory run. :func:`record` runs after ``advise()`` (inside the audit
  wrapper). On a deferral it opens one ``carbon-deferral`` issue per key
  (repository, workflow, head_sha), the human-visible acceptance record, and sets
  ``deferred: true``: the only output a team may gate its build on. If the record
  cannot be written, the run becomes the fail-safe RUN NOW ``redispatch_unavailable``,
  so a build is never skipped without a record. It can only turn ``defer`` into
  ``run_now``; it never creates a deferral.
- **Dispatching**, in a scheduled workflow. :func:`dispatch_due` reads the open
  issues, dispatches each due one on its branch with the deferred SHA as the input
  :data:`DISPATCH_INPUT`, then comments and closes it. Closing an issue by hand
  cancels the deferral. A failed dispatch leaves the issue open for the next run, so
  a deferral is never dropped.

Nothing here decides anything: the deferral and its time are ``decide()``'s, through
``advise()``. This module holds no threshold.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Iterator, Mapping

from . import ADVISOR_VERSION
from .config import TeamConfig
from .contract import _CONTROL_RE, _REPO_RE, _SHA_RE, _WORKFLOW_RE, NULL_STATEMENT, parse_request, parse_utc
from .core import _display
from .github import GitHubClient, GitHubHTTPError
from .history import HistoryError

LABEL = "carbon-deferral"
LABEL_COLOR = "2da44e"
#: Issues opened with the workflow's GITHUB_TOKEN are created by this account (DL-038 §6e).
TRUSTED_CREATOR = "github-actions[bot]"
#: The workflow_dispatch input the re-dispatched run receives (DL-038 §6c).
DISPATCH_INPUT = "carbon_redispatch_sha"
#: C10: past arrival + the evaluated 24 h window + 2 h grace, a dispatch says "deadline reached".
DEADLINE_AFTER = timedelta(hours=24 + 2)
MAX_ISSUE_PAGES = 5

_BODY_RE = re.compile(r"<!-- carbon-deferral v1\n(\{.*?\})\n-->", re.S)
_RECORD_KEYS = ("key", "repository", "workflow", "branch", "head_sha", "run_id", "arrival_utc",
                "defer_until_utc", "scenario", "advisor_version")


class RedispatchError(ValueError):
    """The deferral could not be recorded or read."""


def deferral_key(repository: str, workflow: str, head_sha: str) -> str:
    return f"{repository}|{workflow}|{head_sha}"


def _code(text: Any) -> str:
    return "`" + str(text).replace("`", "'").replace("\n", " ") + "`"


# --------------------------------------------------------------------------- #
# The issue record.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DeferralRecord:
    key: str
    repository: str
    workflow: str
    branch: str
    head_sha: str
    run_id: int | None
    arrival_utc: str
    defer_until_utc: str
    scenario: bool
    advisor_version: str

    @property
    def defer_until(self) -> datetime:
        return parse_utc(self.defer_until_utc, "defer_until_utc")

    @property
    def arrival(self) -> datetime:
        return parse_utc(self.arrival_utc, "arrival_utc")

    def title(self) -> str:
        prefix = "[SCENARIO] " if self.scenario else ""
        return f"{prefix}Carbon deferral: {self.workflow} @ {self.head_sha[:7]} until {self.defer_until_utc}"

    def body(self) -> str:
        data = json.dumps(asdict(self), sort_keys=True)
        lines = [f"<!-- carbon-deferral v1\n{data}\n-->", ""]
        if self.scenario:
            lines += ["> **SCENARIO** — this runner is NOT in Great Britain. This deferral exists only to "
                      "demonstrate the re-dispatch cycle (DL-038 §8); it is not a real carbon decision.", ""]
        lines += [
            f"The carbon-deferral advisor deferred run {self.run_id or '—'} of {_code(self.workflow)} on "
            f"branch {_code(self.branch)} (commit {_code(self.head_sha)}).",
            "",
            f"- **Re-dispatch at:** {self.defer_until_utc} (the scheduled dispatcher runs hourly, so allow up "
            f"to an hour, more under load)",
            f"- **Deadline:** dispatched regardless after {(self.arrival + DEADLINE_AFTER).isoformat()}",
            "- **To cancel:** close this issue. Nothing then re-runs the build; run it yourself if needed.",
            "",
            "Deferred re-dispatch, not pausing: the deferred build job was skipped, and a new "
            "`workflow_dispatch` run will check out the same commit. The re-dispatched run is always RUN NOW.",
            "",
            f"<sub>{NULL_STATEMENT}</sub>",
        ]
        return "\n".join(lines) + "\n"


def parse_record(body: Any) -> DeferralRecord:
    """The machine-readable block of an issue body, under a closed schema."""
    match = _BODY_RE.search(body if isinstance(body, str) else "")
    if not match:
        raise RedispatchError("no carbon-deferral record in the issue body")
    try:
        raw = json.loads(match.group(1))
    except ValueError as exc:
        raise RedispatchError(f"the deferral record is not JSON: {exc}") from None
    if not isinstance(raw, dict) or set(raw) != set(_RECORD_KEYS):
        raise RedispatchError("the deferral record does not have the expected fields")
    if not (isinstance(raw["repository"], str) and _REPO_RE.match(raw["repository"])):
        raise RedispatchError("bad repository in the deferral record")
    if not (isinstance(raw["workflow"], str) and _WORKFLOW_RE.match(raw["workflow"])):
        raise RedispatchError("bad workflow in the deferral record")
    branch = raw["branch"]
    if not (isinstance(branch, str) and 1 <= len(branch) <= 255 and not _CONTROL_RE.search(branch)):
        raise RedispatchError("bad branch in the deferral record")
    if not (isinstance(raw["head_sha"], str) and _SHA_RE.match(raw["head_sha"])):
        raise RedispatchError("bad head_sha in the deferral record")
    run_id = raw["run_id"]
    if run_id is not None and (isinstance(run_id, bool) or not isinstance(run_id, int)):
        raise RedispatchError("bad run_id in the deferral record")
    if not isinstance(raw["scenario"], bool) or not isinstance(raw["advisor_version"], str):
        raise RedispatchError("bad scenario or advisor_version in the deferral record")
    if raw["key"] != deferral_key(raw["repository"], raw["workflow"], raw["head_sha"]):
        raise RedispatchError("the deferral key does not match its fields")
    try:
        parse_utc(raw["arrival_utc"], "arrival_utc")
        parse_utc(raw["defer_until_utc"], "defer_until_utc")
    except ValueError as exc:
        raise RedispatchError(str(exc)) from None
    return DeferralRecord(**raw)


def _issues(client: GitHubClient, repository: str, state: str) -> Iterator[Mapping[str, Any]]:
    for page in range(1, MAX_ISSUE_PAGES + 1):
        body = client.get_json(f"/repos/{repository}/issues",
                               {"labels": LABEL, "state": state, "per_page": 100, "page": page})
        if not isinstance(body, list):
            raise RedispatchError(f"GitHub issues listing for {repository} is not a list")
        for issue in body:
            if isinstance(issue, Mapping) and "pull_request" not in issue:
                yield issue
        if len(body) < 100:
            return


def _creator(issue: Mapping[str, Any]) -> str | None:
    user = issue.get("user")
    return user.get("login") if isinstance(user, Mapping) else None


# --------------------------------------------------------------------------- #
# Recording (the advisory run).
# --------------------------------------------------------------------------- #

def _unrecorded(response: Mapping[str, Any], message: str) -> dict[str, Any]:
    """The monotone fallback: an unrecorded deferral is a fail-safe RUN NOW (DL-038 §6b)."""
    out = dict(response)
    out.update(
        action="run_now", display=_display("run_now", out.get("scenario")), outcome_kind="fail_safe",
        fail_safe=True, fail_safe_code="redispatch_unavailable", defer_until=None, delay_hours=0.0,
        est_carbon_change_pct=None, deferred=False, redispatch=None,
        reason=(f"fail-safe [redispatch_unavailable]: the deferral could not be recorded for re-dispatch "
                f"({message}) -> RUN NOW. | {NULL_STATEMENT}"),
    )
    return out


def _ensure_label(client: GitHubClient, repository: str) -> None:
    try:
        client.send_json("POST", f"/repos/{repository}/labels",
                         {"name": LABEL, "color": LABEL_COLOR,
                          "description": "A CI run deferred by the carbon-deferral advisor"})
    except GitHubHTTPError as exc:
        if exc.status != 422:  # 422: the label already exists
            raise


def ensure_issue(client: GitHubClient, record: DeferralRecord, *,
                 trusted_creator: str = TRUSTED_CREATOR) -> tuple[Mapping[str, Any], bool]:
    """The open issue for this key, reused if it exists (a re-run attempt), else a new one.

    A *closed* issue for the key means the deferral was already dispatched or cancelled;
    recording it again would dispatch the key twice, so that is refused (C10: at most once).
    """
    for issue in _issues(client, record.repository, "all"):
        if _creator(issue) != trusted_creator:
            continue
        try:
            existing = parse_record(issue.get("body"))
        except RedispatchError:
            continue
        if existing.key != record.key:
            continue
        if issue.get("state") == "open":
            return issue, True
        raise RedispatchError(f"deferral {record.key} was already handled by issue #{issue.get('number')}")
    _ensure_label(client, record.repository)
    issue = client.send_json("POST", f"/repos/{record.repository}/issues",
                             {"title": record.title(), "body": record.body(), "labels": [LABEL]})
    if not isinstance(issue, Mapping) or not isinstance(issue.get("number"), int):
        raise RedispatchError("GitHub did not return the created issue")
    return issue, False


def record(raw_request: Any, response: Mapping[str, Any], *, config: TeamConfig, client: GitHubClient,
           now: datetime, trusted_creator: str = TRUSTED_CREATOR) -> dict[str, Any]:
    """Record a deferral as an issue, or turn it into RUN NOW. Never raises."""
    out = dict(response)
    out["deferred"] = False
    if out.get("action") != "defer" or config.redispatch == "off":
        return out
    if out.get("scenario") and config.redispatch != "scenario-demo":
        return out  # R3-K: nothing acts on a scenario, unless the demo mode says so (DL-038 §8)
    try:
        request = parse_request(raw_request, now=now)
        if request.head_sha is None:
            raise RedispatchError("the run has no head_sha to re-dispatch")
        defer = out.get("defer_until")
        if not isinstance(defer, Mapping) or not isinstance(defer.get("utc"), str):
            raise RedispatchError("the deferral has no target time")
        rec = DeferralRecord(
            key=deferral_key(request.repository, request.workflow, request.head_sha),
            repository=request.repository, workflow=request.workflow, branch=request.branch,
            head_sha=request.head_sha, run_id=request.run_id, arrival_utc=request.arrival.isoformat(),
            defer_until_utc=defer["utc"], scenario=bool(out.get("scenario")), advisor_version=ADVISOR_VERSION,
        )
        issue, reused = ensure_issue(client, rec, trusted_creator=trusted_creator)
    except (RedispatchError, HistoryError, ValueError) as exc:
        return _unrecorded(out, str(exc))
    out["deferred"] = True
    out["redispatch"] = {"key": rec.key, "issue_number": issue.get("number"),
                         "issue_url": issue.get("html_url"), "reused": reused}
    return out


# --------------------------------------------------------------------------- #
# Dispatching (the scheduled workflow).
# --------------------------------------------------------------------------- #

def _already_dispatched(client: GitHubClient, rec: DeferralRecord, issue_created: datetime) -> int | None:
    """A workflow_dispatch run at this SHA created at or after the issue: an earlier dispatch (DL-038 §6d)."""
    body = client.get_json(f"/repos/{rec.repository}/actions/workflows/{urllib.parse.quote(rec.workflow)}/runs",
                           {"event": "workflow_dispatch", "head_sha": rec.head_sha, "per_page": 100})
    runs = body.get("workflow_runs") if isinstance(body, Mapping) else None
    for run in runs if isinstance(runs, list) else []:
        try:
            if parse_utc(run.get("created_at"), "created_at") >= issue_created:
                return int(run["id"])
        except (ValueError, KeyError, TypeError):
            continue
    return None


def _close(client: GitHubClient, repository: str, number: int, comment: str) -> None:
    client.send_json("POST", f"/repos/{repository}/issues/{number}/comments", {"body": comment})
    client.send_json("PATCH", f"/repos/{repository}/issues/{number}", {"state": "closed", "state_reason": "completed"})


def _dispatch(client: GitHubClient, rec: DeferralRecord, ref: str) -> Any:
    return client.send_json("POST", f"/repos/{rec.repository}/actions/workflows/"
                                    f"{urllib.parse.quote(rec.workflow)}/dispatches",
                            {"ref": ref, "inputs": {DISPATCH_INPUT: rec.head_sha}})


def _handle(client: GitHubClient, repository: str, issue: Mapping[str, Any], now: datetime,
            trusted_creator: str) -> dict[str, Any]:
    number = issue.get("number")
    result: dict[str, Any] = {"issue": number, "key": None, "scenario": None}
    if _creator(issue) != trusted_creator:
        return {**result, "outcome": "refused_untrusted",
                "detail": f"issue not created by {trusted_creator}; left untouched"}
    try:
        rec = parse_record(issue.get("body"))
        issue_created = parse_utc(issue.get("created_at"), "created_at")
    except (RedispatchError, ValueError) as exc:
        return {**result, "outcome": "refused_invalid", "detail": f"{exc}; left untouched"}
    result.update(key=rec.key, scenario=rec.scenario, head_sha=rec.head_sha, workflow=rec.workflow,
                  defer_until_utc=rec.defer_until_utc)
    if rec.repository != repository:
        return {**result, "outcome": "refused_invalid", "detail": "record is for another repository"}
    label = "[SCENARIO] " if rec.scenario else ""
    try:
        previous = _already_dispatched(client, rec, issue_created)
        if previous is not None:
            _close(client, repository, number,
                   f"{label}Already dispatched as run {previous}; closing without dispatching again.")
            return {**result, "outcome": "already_dispatched", "detail": f"run {previous}"}
        if now < rec.defer_until:
            return {**result, "outcome": "not_due", "detail": f"due at {rec.defer_until_utc}"}
        reason = "deadline reached" if now >= rec.arrival + DEADLINE_AFTER else "due"
        ref, fallback = rec.branch, False
        try:
            reply = _dispatch(client, rec, ref)
        except GitHubHTTPError as exc:
            if exc.status != 422:
                raise
            repo = client.get_json(f"/repos/{repository}")
            default = repo.get("default_branch") if isinstance(repo, Mapping) else None
            if not isinstance(default, str) or default == ref:
                raise
            ref, fallback = default, True
            reply = _dispatch(client, rec, ref)
    except (HistoryError, RedispatchError) as exc:
        return {**result, "outcome": "dispatch_failed", "detail": f"{exc}; left open for the next run"}
    run_url = reply.get("html_url") if isinstance(reply, Mapping) else None
    note = (f"{label}Dispatched `{rec.workflow}` on `{ref}` at {now.isoformat()} ({reason})"
            + (f": {run_url}" if run_url else "") + "."
            + (f" The branch `{rec.branch}` was not dispatchable, so the default branch was used." if fallback else "")
            + f" The re-dispatched run checks out `{rec.head_sha}` and is always RUN NOW.")
    outcome = {**result, "outcome": "dispatched", "ref": ref, "fallback": fallback, "reason": reason,
               "run_url": run_url}
    try:
        _close(client, repository, number, note)
    except HistoryError as exc:
        outcome["detail"] = f"dispatched, but the issue could not be closed ({exc}); the next run closes it"
    return outcome


def dispatch_due(client: GitHubClient, repository: str, *, now: datetime,
                 trusted_creator: str = TRUSTED_CREATOR) -> list[dict[str, Any]]:
    """One dispatcher pass over the open deferral issues. Never raises for a single issue."""
    return [_handle(client, repository, issue, now, trusted_creator)
            for issue in _issues(client, repository, "open")]


def render_dispatch_summary(repository: str, results: list[Mapping[str, Any]], now: datetime) -> str:
    lines = [f"## Carbon re-dispatch — {len(results)} open deferral(s)", "",
             f"`{repository}` at {now.isoformat()}. Deferred re-dispatch, not pausing.", ""]
    if results:
        lines += ["| issue | outcome | scenario | detail |", "| --: | :-- | :-- | :-- |"]
        for r in results:
            detail = r.get("detail") or (f"{r.get('reason')} on `{r.get('ref')}`" if r.get("outcome") == "dispatched"
                                         else "")
            lines.append(f"| #{r.get('issue')} | {r.get('outcome')} | {'yes' if r.get('scenario') else 'no'} | "
                         f"{_code(detail) if detail else '—'} |")
    else:
        lines.append("Nothing to dispatch.")
    return "\n".join(lines) + "\n"

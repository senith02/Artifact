"""The advisor's fixed order of operations (context/p4_interface.md §6; DL-033 R3-C3).

    validate → trusted event → config / opt-in → region → frozen pins
      → completed history → d̂ → decide() → veto layer → response

The decision is always ``scheduler_core.policy.decide()``. The veto layer runs
**after** it and can only turn a ``defer`` into RUN NOW (R3-B6, R3-J1); it never
alters decide()'s inputs and never looks for another slot. Every failure is a
fail-safe RUN NOW with a named code, never a deferral (R3-B9).

All side effects arrive as injected callables (frozen-core loader, history
source, live-carbon fetchers, clock), so the function is deterministic under test.
"""

from __future__ import annotations

import fnmatch
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from scheduler_core import accounting
from scheduler_core import eligibility
from scheduler_core.policy import Decision, decide

from . import ADVISOR_VERSION
from .config import ConfigError, TeamConfig
from .contract import (
    EVALUATED_REGION, NULL_STATEMENT, SCENARIO_BANNER, STATEMENTS, AdviceRequest, RequestError,
    parse_request,
)
from .estimate import DHat, estimate_d_hat
from .frozen import FrozenArtifactError, FrozenCore, default_frozen_core
from .history import HistoryError, filter_admissible, parse_history

HistorySource = Callable[[str, str, int], list]
LiveFetch = Callable[..., "dict[str, Any] | None"]


@dataclass
class Dependencies:
    """Everything with a side effect, injected."""

    load_frozen: Callable[[], FrozenCore] = default_frozen_core
    history_source: HistorySource | None = None
    live_national: LiveFetch | None = None
    live_regional: LiveFetch | None = None
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    energy_config: Callable[[], accounting.EnergyConfig] = accounting.load_energy_config


# --------------------------------------------------------------------------- #
# Response assembly.
# --------------------------------------------------------------------------- #

_EMPTY_DECISION_FIELDS: dict[str, Any] = {
    "policy_action": None, "defer_until": None, "delay_hours": 0.0, "window_hours": None,
    "stage1_rule": None, "eligible": None, "d_hat_seconds": None, "d_hat_rung": None,
    "n_history": None, "history_dropped": {}, "grid_gco2_profile_now": None,
    "grid_gco2_profile_scheduled": None, "est_carbon_change_pct": None,
    "grid_gco2_live_national": None, "grid_gco2_live_regional": None,
    "policy_path": None, "spec_sha256": None, "profile_sha256": None, "estimator_fit_id": None,
}


def _display(action: str, scenario: str | None) -> str:
    label = "DEFER RECOMMENDED" if action == "defer" else "RUN NOW"
    return f"{label} (scenario)" if scenario else label


def _statements(scenario: str | None) -> list[str]:
    return ([SCENARIO_BANNER] if scenario else []) + list(STATEMENTS)


def _fail_safe(code: str, message: str, *, request: AdviceRequest | None = None,
               config: TeamConfig | None = None) -> dict[str, Any]:
    scenario = request.scenario if request else None
    response = {
        "action": "run_now", "display": _display("run_now", scenario), "outcome_kind": "fail_safe",
        "fail_safe": True, "fail_safe_code": code, "vetoes": [],
        "reason": f"fail-safe [{code}]: {message} -> RUN NOW. | {NULL_STATEMENT}",
        **_EMPTY_DECISION_FIELDS,
        "compute_region_assumed": request.compute_region if request else None,
        "scenario": scenario, "advisor_version": ADVISOR_VERSION,
        "config_warnings": list(config.warnings) if config else [],
        "statements": _statements(scenario),
    }
    return response


def _vetoes(request: AdviceRequest, config: TeamConfig, decision: Decision, dhat: DHat,
            defer_until_utc: datetime) -> list[str]:
    """Every rule that turns this deferral into RUN NOW, in a fixed order (interface §6.2)."""
    found: list[str] = []
    if request.redispatch_key is not None:
        found.append("redispatched_run")
    if config.cold_start_run_now and dhat.n_history == 0:
        found.append("cold_start")
    if request.ref_type == "tag":
        found.append("tag_ref")
    if request.event in config.veto_events:
        found.append("event_vetoed")
    if any(fnmatch.fnmatchcase(request.branch, pattern) for pattern in config.extra_protected_branches):
        found.append("extra_protected_branch")
    message = (request.head_commit_message or "").casefold()
    if any(marker.casefold() in message for marker in config.urgent_markers):
        found.append("urgent_marker")
    if request.deadline is not None and defer_until_utc > request.deadline:
        found.append("exceeds_deadline")
    if decision.delay_hours > config.max_delay_hours:
        found.append("exceeds_max_delay")
    return found


_VETO_TEXT = {
    "redispatched_run": "this run is a re-dispatch of an earlier deferral",
    "cold_start": "cold start: no completed runs of this workflow to estimate from",
    "tag_ref": "tag pushes are treated as releases",
    "event_vetoed": "the team marks this trigger event as urgent",
    "extra_protected_branch": "the team protects this branch",
    "urgent_marker": "the commit message carries an urgency marker",
    "exceeds_deadline": "the recommended slot is after the run's deadline",
    "exceeds_max_delay": "the recommended delay exceeds the team's maximum",
}


def _estimated_change_pct(d_hat_seconds: float, now_intensity: float, scheduled_intensity: float,
                          energy: accounting.EnergyConfig) -> float:
    """Estimated % change for one build of length d̂ moved to the scheduled slot (display)."""
    kwh = accounting.energy_kwh(d_hat_seconds, energy.p_avg_w)
    return accounting.pct_change_vs_baseline(accounting.carbon_g(kwh, scheduled_intensity),
                                             accounting.carbon_g(kwh, now_intensity))


# --------------------------------------------------------------------------- #
# The advisor.
# --------------------------------------------------------------------------- #

def advise(raw_request: Any, config: TeamConfig | Exception | None, deps: Dependencies) -> dict[str, Any]:
    """Advise on one run. Never raises; every failure is a fail-safe RUN NOW."""
    request: AdviceRequest | None = None
    team: TeamConfig | None = config if isinstance(config, TeamConfig) else None
    try:
        # 1-2. Schema, then the trusted-event check.
        try:
            request = parse_request(raw_request, now=deps.now())
        except RequestError as exc:
            return _fail_safe(exc.code, str(exc), config=team)

        # 3. Team config, then opt-in.
        if team is None:
            detail = str(config) if isinstance(config, Exception) else "no team config was provided"
            return _fail_safe(ConfigError.code, detail, request=request)
        if request.workflow not in team.enabled_workflows:
            response = _fail_safe("config_invalid", "", request=request, config=team)
            response.update(outcome_kind="not_advised", fail_safe=False, fail_safe_code=None,
                            reason=f"workflow {request.workflow!r} is not opted in (enabled_workflows) "
                                   f"-> RUN NOW. | {NULL_STATEMENT}")
            return response

        # 4. Region: declared, never detected (R3-B5, R3-J3).
        if request.compute_region != team.compute_region:
            return _fail_safe("region_mismatch",
                              f"request compute_region {request.compute_region!r} differs from the team "
                              f"config {team.compute_region!r}", request=request, config=team)
        if request.compute_region != EVALUATED_REGION:
            return _fail_safe("region_not_gb",
                              f"compute region {request.compute_region} is outside the evaluated GB regime; "
                              f"no GB carbon figures apply", request=request, config=team)

        # 5. The frozen artifacts, verified against their pins.
        try:
            core = deps.load_frozen()
        except FrozenArtifactError as exc:
            return _fail_safe(exc.code, str(exc), request=request, config=team)

        build: dict[str, Any] = {
            "gh_is_pr": request.is_pr, "git_branch": request.branch,
            "arrival_dow": request.arrival.weekday(), "arrival_hour": request.arrival.hour,
        }

        # 6-7. History and d̂ — only for a run Stage 1 lets through. This pre-check calls
        # the same frozen gate decide() calls first; it saves the history fetch for
        # runs that must run now anyway, and the decision itself is still decide()'s.
        dhat: DHat | None = None
        dropped: Counter = Counter()
        if eligibility.is_eligible(request.is_pr, request.branch, variant=core.spec.stage1_variant):
            try:
                if request.history is not None:
                    entries = list(request.history)
                elif deps.history_source is not None:
                    entries = deps.history_source(request.repository, request.workflow, team.history_cap)
                else:
                    entries = []
                if len(entries) > team.history_cap:
                    entries = entries[: team.history_cap]
                runs = parse_history(entries)
            except HistoryError as exc:
                return _fail_safe(exc.code, str(exc), request=request, config=team)
            admitted, dropped = filter_admissible(runs, workflow=request.workflow, run_id=request.run_id,
                                                  arrival=request.arrival)
            dhat = estimate_d_hat(core.estimator, admitted, arrival=request.arrival,
                                  project_key=f"{request.repository}:{request.workflow}",
                                  repo_language=request.repo_language)
            build["d_hat_seconds"] = dhat.seconds

        # 8. The decision of record.
        decision = decide(build, core.profile, core.spec)

        arrival_hour = request.arrival.replace(minute=0, second=0, microsecond=0)
        defer_until = None
        vetoes: list[str] = []
        if decision.action == "defer":
            offset = int(decision.defer_until["offset_hours"])
            defer_until_utc = arrival_hour + timedelta(hours=offset)
            defer_until = {**dict(decision.defer_until), "utc": defer_until_utc.isoformat()}
            # 9. The veto layer — it can only turn this deferral into RUN NOW.
            vetoes = _vetoes(request, team, decision, dhat, defer_until_utc)

        final_action = "run_now" if vetoes else decision.action
        reason = decision.reason
        if vetoes:
            reason += " | veto: " + "; ".join(_VETO_TEXT[v] for v in vetoes) + " -> RUN NOW."
        reason += f" | {NULL_STATEMENT}"

        est_change = None
        if final_action == "defer":
            est_change = _estimated_change_pct(decision.d_hat_seconds, decision.grid_gco2_now,
                                               decision.grid_gco2_scheduled, deps.energy_config())

        live_national = live_regional = None
        if team.show_live_intensity and deps.live_national is not None:
            live_national = deps.live_national()
        if team.grid_display_region is not None and deps.live_regional is not None:
            live_regional = deps.live_regional(team.grid_display_region)

        return {
            "action": final_action, "display": _display(final_action, request.scenario),
            "outcome_kind": "veto" if vetoes else "policy", "fail_safe": False, "fail_safe_code": None,
            "vetoes": vetoes, "policy_action": decision.action, "reason": reason,
            "defer_until": defer_until if final_action == "defer" else None,
            "policy_defer_until": defer_until,
            "delay_hours": decision.delay_hours if final_action == "defer" else 0.0,
            "window_hours": decision.window_hours,
            "stage1_rule": decision.stage1_rule, "eligible": decision.eligible,
            "d_hat_seconds": dhat.seconds if dhat else None,
            "d_hat_rung": dhat.rung if dhat else None,
            "n_history": dhat.n_history if dhat else None,
            "history_dropped": dict(sorted(dropped.items())),
            "grid_gco2_profile_now": decision.grid_gco2_now,
            "grid_gco2_profile_scheduled": decision.grid_gco2_scheduled,
            "est_carbon_change_pct": est_change,
            "grid_gco2_live_national": live_national,
            "grid_gco2_live_regional": live_regional,
            "compute_region_assumed": request.compute_region, "scenario": request.scenario,
            "policy_path": decision.policy_path, "spec_sha256": core.spec_sha256,
            "profile_sha256": core.profile_sha256, "estimator_fit_id": core.estimator_fit_id,
            "advisor_version": ADVISOR_VERSION, "config_warnings": list(team.warnings),
            "statements": _statements(request.scenario),
        }
    except Exception as exc:  # the last line of the fail-safe contract
        return _fail_safe("internal_error", f"{type(exc).__name__}: {exc}", request=request, config=team)


#: The decision fields that must be identical across surfaces (parity) and that
#: display-only inputs must never change.
DECISION_FIELDS: tuple[str, ...] = (
    "action", "outcome_kind", "fail_safe", "fail_safe_code", "vetoes", "policy_action",
    "defer_until", "policy_defer_until", "delay_hours", "window_hours", "stage1_rule", "eligible",
    "d_hat_seconds", "d_hat_rung", "n_history", "history_dropped", "grid_gco2_profile_now",
    "grid_gco2_profile_scheduled", "est_carbon_change_pct", "policy_path", "reason",
)


def decision_view(response: Mapping[str, Any]) -> dict[str, Any]:
    return {k: response.get(k) for k in DECISION_FIELDS}

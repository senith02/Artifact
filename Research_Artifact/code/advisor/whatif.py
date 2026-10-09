"""Repo What-If Report (DL-033 R3-C8, R3-I; DL-037).

    completed runs of one workflow (a saved snapshot)
      → for each run, in arrival order: the same advise() — so the same d̂ from
        completed history, the same decide(), the same veto layer
      → only then, the run's OBSERVED duration, for estimated carbon and delay

The observed duration is accounting only (A1.2 role 1): it never enters the
request for its own run, so it cannot reach decide(). A run's own duration does
enter the history of runs that arrive after it finished, exactly as in live use.

Demonstration only — never research evidence (R3-B10). Every output carries the
banner, and nothing is written under results/p0–p3.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from scheduler_core import accounting
from scheduler_core import carbon as carbon_mod

from . import ADVISOR_VERSION
from .config import TeamConfig, parse_team_config
from .contract import SCENARIO_BANNER, STATEMENTS, parse_utc
from .core import Dependencies, advise
from .frozen import default_frozen_core
from .github import GitHubClient, PER_PAGE, run_to_history_entry

WHATIF_BANNER = "Demonstration — not research evidence"
WHATIF_STATEMENT = "What-If output is demonstration only, never research evidence."
SNAPSHOT_SCHEMA = 1
REPORT_SCHEMA = 1
SCENARIO = "gb-hypothetical"
TTFF_MIN_FAILED_RUNS = 20          # design default (DL-033 R3-C8 item 4)
DELAY_BIN_HOURS = 2
ANALYSED_CONCLUSIONS = ("success", "failure")

LIMITATIONS: tuple[str, ...] = (
    "Replay, not observation: the runs really ran at once; this shows what the advisor would have recommended.",
    "The GB profile is applied as if the runs had used GB compute; where they really ran is unknown.",
    "Carbon is estimated from the observed run wall-clock under a constant-power model and the GB "
    "hour-of-week mean profile, not measured.",
    "Run wall-clock (updated_at - run_started_at) covers the whole workflow run and is a different "
    "measure from Travis tr_duration, on which the thresholds were fitted.",
    "GitHub's run duration includes any time a run stays open waiting inside the workflow; runs open for "
    "hours or days inflate the estimated carbon and the failed-run TTFF.",
    "History is limited to the fetched window; runs early in the window see less history than a deployed "
    "advisor would have.",
    "A run object does not say whether a push was to a tag, so every ref is treated as a branch; tag "
    "pushes, which would be vetoed live, may be counted as eligible.",
    "Urgency is read from commit-message markers only; pull-request labels are not read.",
    "Cancelled, skipped, timed-out and other non-success/failure runs are excluded from the analysis.",
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RESULTS_FROZEN = re.compile(r"(^|/)results/p[0-3](/|$)")


class WhatIfError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Snapshot: per-run fields only, no actor/login/author (DL-037 §6).
# --------------------------------------------------------------------------- #

def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """The fields a report needs from one GitHub run object; e-mail addresses redacted."""
    head_commit = run.get("head_commit") if isinstance(run.get("head_commit"), Mapping) else {}
    message = head_commit.get("message") if isinstance(head_commit.get("message"), str) else None
    path = str(run.get("path") or "")
    return {
        "run_id": run.get("id"), "workflow": path.rsplit("/", 1)[-1] if path else None,
        "event": run.get("event"), "head_branch": run.get("head_branch"), "head_sha": run.get("head_sha"),
        "status": run.get("status"), "conclusion": run.get("conclusion"), "run_attempt": run.get("run_attempt"),
        "created_at": run.get("created_at"), "run_started_at": run.get("run_started_at"),
        "updated_at": run.get("updated_at"),
        "head_commit_message": _EMAIL_RE.sub("<email>", message)[:4096] if message is not None else None,
    }


def fetch_snapshot(client: GitHubClient, repository: str, workflow: str, *, cap: int,
                   now: datetime) -> dict[str, Any]:
    """Read-only: the last ``cap`` completed runs of one workflow, and the repository language."""
    path = f"/repos/{repository}/actions/workflows/{workflow}/runs"
    runs: list[dict[str, Any]] = []
    total, page = None, 1
    while len(runs) < cap:
        body = client.get_json(path, {"status": "completed", "per_page": PER_PAGE, "page": page})
        batch = body.get("workflow_runs") if isinstance(body, Mapping) else None
        if not isinstance(batch, list):
            raise WhatIfError(f"no workflow_runs list for {repository} {workflow}")
        if total is None and isinstance(body.get("total_count"), int):
            total = body["total_count"]
        runs.extend(snapshot_run(r) for r in batch[: cap - len(runs)])
        if len(batch) < PER_PAGE:
            break
        page += 1
    return {
        "snapshot_schema": SNAPSHOT_SCHEMA, "repository": repository, "workflow": workflow,
        "fetched_at": _iso(now), "history_cap": cap, "repo_total_completed_runs": total,
        "repo_language": client.repo_language(repository), "runs": runs,
    }


def canonical_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_snapshot(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("snapshot_schema") != SNAPSHOT_SCHEMA:
        raise WhatIfError(f"unsupported snapshot schema in {path}")
    return data


# --------------------------------------------------------------------------- #
# The replay.
# --------------------------------------------------------------------------- #

def default_team_config(workflow: str) -> TeamConfig:
    """The config for a repository with none (DL-037 §2): GB scenario, every other key at its default."""
    return parse_team_config({"compute_region": "GB", "enabled_workflows": [workflow]})


def _config_view(config: TeamConfig) -> dict[str, Any]:
    return {"compute_region": config.compute_region, "enabled_workflows": list(config.enabled_workflows),
            "extra_protected_branches": list(config.extra_protected_branches),
            "urgent_markers": list(config.urgent_markers), "veto_events": list(config.veto_events),
            "max_delay_hours": config.max_delay_hours, "cold_start_run_now": config.cold_start_run_now,
            "history_cap": config.history_cap}


def _history_entry(run: Mapping[str, Any]) -> dict[str, Any] | None:
    """A snapshot run as an advisor history entry, or None if it cannot be placed in time."""
    if not isinstance(run.get("run_id"), int) or not isinstance(run.get("status"), str):
        return None
    entry = run_to_history_entry({"id": run["run_id"], "path": run.get("workflow") or "",
                                  "status": run["status"], "conclusion": run.get("conclusion"),
                                  "created_at": run.get("created_at"), "run_started_at": run.get("run_started_at"),
                                  "updated_at": run.get("updated_at")}, run.get("workflow") or "")
    return entry


def _exclusion(run: Mapping[str, Any], entry: Mapping[str, Any] | None) -> str | None:
    if run.get("conclusion") not in ANALYSED_CONCLUSIONS:
        return f"conclusion_{run.get('conclusion') or 'none'}"
    if entry is None:
        return "unplaceable"
    try:
        parse_utc(run.get("created_at"), "created_at")
    except ValueError:
        return "unplaceable"
    if entry["duration_s"] <= 0:
        return "non_positive_duration"
    return None


def _request(snapshot: Mapping[str, Any], run: Mapping[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """The advisor request for one run — built WITHOUT the run's own duration or outcome."""
    request: dict[str, Any] = {
        "repository": snapshot["repository"], "workflow": snapshot["workflow"],
        "event": run.get("event") or "", "ref_type": "branch", "branch": run.get("head_branch") or "",
        "is_pr": run.get("event") == "pull_request", "arrival_utc": run["created_at"],
        "compute_region": "GB", "scenario": SCENARIO, "run_id": run["run_id"], "history": history,
    }
    if isinstance(run.get("head_sha"), str):
        request["head_sha"] = run["head_sha"]
    if isinstance(run.get("run_attempt"), int) and run["run_attempt"] >= 1:
        request["run_attempt"] = run["run_attempt"]
    if run.get("head_commit_message") is not None:
        request["head_commit_message"] = run["head_commit_message"]
    if isinstance(snapshot.get("repo_language"), str):
        request["repo_language"] = snapshot["repo_language"]
    return request


def _run_now_reason(response: Mapping[str, Any]) -> str:
    kind = response.get("outcome_kind")
    if kind == "fail_safe":
        return "fail_safe"
    if kind == "not_advised":
        return "not_advised"
    if kind == "veto":
        return "vetoed"
    rule = str(response.get("stage1_rule") or "")
    if not response.get("eligible"):
        if rule == "pr_blocking":
            return "pull_request"
        if rule.startswith("protected:"):
            return "protected_branch"
        return "not_deferrable_fail_closed"
    return "no_greener_slot" if (response.get("window_hours") or 0) > 0 else "below_threshold"


def replay(snapshot: Mapping[str, Any], *, config: TeamConfig | None = None,
           deps: Dependencies | None = None) -> list[dict[str, Any]]:
    """Advise every run in arrival order; returns per-run records (kept in memory, never published)."""
    workflow = snapshot["workflow"]
    config = config or default_team_config(workflow)
    fetched_at = parse_utc(snapshot["fetched_at"], "fetched_at")
    deps = deps or Dependencies(load_frozen=default_frozen_core, now=lambda: fetched_at)
    runs = sorted(snapshot["runs"], key=lambda r: (str(r.get("created_at")), int(r.get("run_id") or 0)))
    entries = [_history_entry(r) for r in runs]
    history = [e for e in entries if e is not None]

    records = []
    for run, entry in zip(runs, entries):
        excluded = _exclusion(run, entry)
        if excluded:
            records.append({"excluded": excluded})
            continue
        response = advise(_request(snapshot, run, history), config, deps)
        # ---- decide() has returned; only now may the observed duration be read ----
        records.append({"excluded": None, "response": response, "conclusion": run["conclusion"],
                        "arrival": parse_utc(run["created_at"], "created_at"),
                        "observed_duration_s": float(entry["duration_s"])})
    return records


# --------------------------------------------------------------------------- #
# The report.
# --------------------------------------------------------------------------- #

def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 2) if whole else None


def build_report(snapshot: Mapping[str, Any], records: list[dict[str, Any]], *,
                 config: TeamConfig | None = None) -> dict[str, Any]:
    config = config or default_team_config(snapshot["workflow"])
    core = default_frozen_core()
    profile = core.profile
    energy = accounting.load_energy_config()
    band = accounting.p_avg_band(energy)

    excluded = Counter(r["excluded"] for r in records if r["excluded"])
    analysed = [r for r in records if not r["excluded"]]
    responses = [r["response"] for r in analysed]

    reasons, veto_codes, fail_codes = Counter(), Counter(), Counter()
    rungs, cold = Counter(), 0
    deferred_arrivals, deferred_targets = Counter(), Counter()
    delays, ttff_advisor, ttff_now = [], [], []
    carbon_now = {p: 0.0 for _, p in band}
    carbon_adv = {p: 0.0 for _, p in band}

    for rec in analysed:
        resp, arrival, duration = rec["response"], rec["arrival"], rec["observed_duration_s"]
        deferred = resp["action"] == "defer"
        if deferred:
            target = resp["defer_until"]
            deferred_arrivals[(arrival.weekday(), arrival.hour)] += 1
            deferred_targets[(target["dow"], target["hour"])] += 1
            slot_dow, slot_hour = target["dow"], target["hour"]
        else:
            reasons[_run_now_reason(resp)] += 1
            slot_dow, slot_hour = arrival.weekday(), arrival.hour
        veto_codes.update(resp.get("vetoes") or [])
        if resp.get("fail_safe_code"):
            fail_codes[resp["fail_safe_code"]] += 1
        if resp.get("d_hat_rung"):
            rungs[resp["d_hat_rung"]] += 1
            if resp.get("n_history") == 0:
                cold += 1
        delay_h = float(resp.get("delay_hours") or 0.0) if deferred else 0.0
        delays.append(delay_h)
        if rec["conclusion"] == "failure":
            ttff_advisor.append(delay_h + duration / 3600.0)
            ttff_now.append(duration / 3600.0)
        # Accounting boundary: the observed duration is used here and only here.
        for _, p_avg in band:
            carbon_now[p_avg] += accounting.carbon_for_slot(duration, profile, arrival.weekday(), arrival.hour, p_avg)
            carbon_adv[p_avg] += accounting.carbon_for_slot(duration, profile, slot_dow, slot_hour, p_avg)

    n = len(analysed)
    n_def = sum(1 for r in responses if r["action"] == "defer")
    n_elig = sum(1 for r in responses if r.get("eligible"))
    deferred_delays = [d for d, r in zip(delays, responses) if r["action"] == "defer"]
    bins = [{"from_h": lo, "to_h": lo + DELAY_BIN_HOURS,
             "count": sum(1 for d in deferred_delays if lo < d <= lo + DELAY_BIN_HOURS)}
            for lo in range(0, 24, DELAY_BIN_HOURS)]
    nominal = energy.p_avg_w
    change_pct = (_r(accounting.pct_change_vs_baseline(carbon_adv[nominal], carbon_now[nominal]), 3)
                  if n and carbon_now[nominal] > 0 else None)
    total = snapshot.get("repo_total_completed_runs")
    fetched = len(snapshot["runs"])
    arrivals = sorted(str(r.get("created_at")) for r in snapshot["runs"] if r.get("created_at"))

    return {
        "report_schema": REPORT_SCHEMA,
        "banner": WHATIF_BANNER,
        "repository": snapshot["repository"],
        "workflow": snapshot["workflow"],
        "snapshot": {
            "fetched_at": snapshot["fetched_at"], "sha256": sha256_text(canonical_json(snapshot)),
            "runs_fetched": fetched, "history_cap": snapshot.get("history_cap"),
            "repo_total_completed_runs": total, "repo_language": snapshot.get("repo_language"),
            "window_truncated": bool(isinstance(total, int) and total > fetched),
            "window_first_created_at": arrivals[0] if arrivals else None,
            "window_last_created_at": arrivals[-1] if arrivals else None,
        },
        "assumptions": {
            "compute_region": "GB", "scenario": SCENARIO, "ref_type_assumed": "branch",
            "arrival": "run created_at (UTC)", "duration_source": "wallclock",
            "team_config": _config_view(config),
        },
        "policy": {
            "policy_path": core.spec.policy_path, "parameters": dict(core.spec.active()),
            "spec_sha256": core.spec_sha256, "profile_sha256": core.profile_sha256,
            "estimator_fit_id": core.estimator_fit_id, "advisor_version": ADVISOR_VERSION,
        },
        "runs": {"fetched": fetched, "analysed": n, "excluded_total": sum(excluded.values()),
                 "excluded": dict(sorted(excluded.items()))},
        "decisions": {
            "analysed": n, "eligible": n_elig, "eligible_share_pct": _pct(n_elig, n),
            "deferred": n_def, "deferred_share_pct": _pct(n_def, n), "run_now": n - n_def,
            "run_now_reasons": dict(sorted(reasons.items())),
            "veto_codes": dict(sorted(veto_codes.items())), "fail_safe_codes": dict(sorted(fail_codes.items())),
        },
        "carbon": {
            "label": "estimated, not measured",
            "change_pct": change_pct,
            "band": [{"multiplier": m, "p_avg_w": _r(p, 2), "run_now_g": _r(carbon_now[p]),
                      "advisor_g": _r(carbon_adv[p]), "change_g": _r(carbon_adv[p] - carbon_now[p]),
                      "run_now_g_per_run": _r(carbon_now[p] / n) if n else None,
                      "advisor_g_per_run": _r(carbon_adv[p] / n) if n else None}
                     for m, p in band],
        },
        "delay": {
            "mean_added_delay_hours_all_runs": _r(float(np.mean(delays)), 3) if delays else None,
            "deferred_runs": n_def,
            "mean_delay_hours_deferred": _r(float(np.mean(deferred_delays)), 3) if deferred_delays else None,
            "histogram_bin_hours": DELAY_BIN_HOURS, "histogram": bins,
        },
        "ttff_failed": {
            "failed_runs": len(ttff_advisor), "min_failed_runs": TTFF_MIN_FAILED_RUNS,
            "computed": len(ttff_advisor) >= TTFF_MIN_FAILED_RUNS,
            "p95_hours_advisor": (_r(float(np.percentile(ttff_advisor, 95)), 3)
                                  if len(ttff_advisor) >= TTFF_MIN_FAILED_RUNS else None),
            "p95_hours_run_now": (_r(float(np.percentile(ttff_now, 95)), 3)
                                  if len(ttff_now) >= TTFF_MIN_FAILED_RUNS else None),
            "note": (None if len(ttff_advisor) >= TTFF_MIN_FAILED_RUNS
                     else f"not computable (n = {len(ttff_advisor)})"),
        },
        "rung_coverage": {"project": rungs.get("project", 0), "language": rungs.get("language", 0),
                          "global": rungs.get("global", 0), "cold_start_runs": cold},
        "heatmap": {
            "dows": list(carbon_mod.DOW_NAMES), "hours": list(range(24)),
            "intensity": [[_r(carbon_mod.intensity_for_hour_of_week(profile, d, h), 2) for h in range(24)]
                          for d in range(7)],
            "deferred_arrivals": [{"dow": d, "hour": h, "count": c} for (d, h), c in sorted(deferred_arrivals.items())],
            "deferred_targets": [{"dow": d, "hour": h, "count": c} for (d, h), c in sorted(deferred_targets.items())],
        },
        "statements": [SCENARIO_BANNER, *STATEMENTS, WHATIF_STATEMENT],
        "limitations": list(LIMITATIONS),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    d, c, t, s = report["decisions"], report["carbon"], report["ttff_failed"], report["snapshot"]
    nominal = next(b for b in c["band"] if b["multiplier"] == 1.0)
    low, high = c["band"][0], c["band"][-1]
    lines = [
        f"# Repo What-If Report — `{report['repository']}` · `{report['workflow']}`",
        "",
        f"> **{report['banner']}.** {report['statements'][0]}",
        "",
        "| | |",
        "| :-- | :-- |",
        f"| Runs fetched / analysed / excluded | {report['runs']['fetched']} / {report['runs']['analysed']} / "
        f"{report['runs']['excluded_total']} |",
        f"| Stage-1 eligible | {d['eligible']} ({d['eligible_share_pct']} %) |",
        f"| Deferred | {d['deferred']} ({d['deferred_share_pct']} %) |",
        f"| Estimated carbon change vs run-now | {c['change_pct']} % "
        f"({nominal['change_g']} g at {nominal['p_avg_w']} W; band {low['change_g']} to {high['change_g']} g) |",
        f"| Mean added delay (all analysed runs) | {report['delay']['mean_added_delay_hours_all_runs']} h |",
        f"| Failed-run TTFF p95, advisor vs run-now | "
        + (f"{t['p95_hours_advisor']} h vs {t['p95_hours_run_now']} h (n = {t['failed_runs']})"
           if t["computed"] else t["note"]) + " |",
        f"| History window | {s['window_first_created_at']} → {s['window_last_created_at']}"
        f"{' (truncated: older runs exist)' if s['window_truncated'] else ''} |",
        "",
        "## Run-now reasons",
        "",
        "| reason | runs |", "| :-- | --: |",
        *[f"| {k} | {v} |" for k, v in d["run_now_reasons"].items()],
        "",
        f"Vetoes: {d['veto_codes'] or 'none'} · Fail-safes: {d['fail_safe_codes'] or 'none'} · "
        f"Excluded: {report['runs']['excluded'] or 'none'}",
        "",
        "## d̂ rung coverage",
        "",
        "| project | language | global | cold start |", "| --: | --: | --: | --: |",
        f"| {report['rung_coverage']['project']} | {report['rung_coverage']['language']} | "
        f"{report['rung_coverage']['global']} | {report['rung_coverage']['cold_start_runs']} |",
        "",
        "## Statements",
        "",
        *[f"- {x}" for x in report["statements"][1:]],
        "",
        "## Limitations",
        "",
        *[f"- {x}" for x in report["limitations"]],
        "",
        f"<sub>policy {report['policy']['policy_path']} {report['policy']['parameters']} · spec "
        f"{report['policy']['spec_sha256'][:12]} · profile {report['policy']['profile_sha256'][:12]} · estimator "
        f"{report['policy']['estimator_fit_id']} · snapshot {s['sha256'][:12]} fetched {s['fetched_at']}</sub>",
        "",
    ]
    return "\n".join(lines)


def check_output_dir(out_dir: str | Path) -> Path:
    """Refuse results/p0–p3 (DL-037 §8): What-If numbers never enter the research evidence."""
    path = Path(out_dir).resolve()
    if _RESULTS_FROZEN.search(path.as_posix()):
        raise WhatIfError(f"refusing to write What-If output under {path}: results/p0-p3 hold research evidence")
    return path


def write_report(report: Mapping[str, Any], out_dir: str | Path) -> dict[str, str]:
    from .whatif_html import render_html

    out = check_output_dir(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = canonical_json(report)
    html = render_html(report)
    (out / "report.json").write_text(text, encoding="utf-8", newline="\n")
    (out / "report.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    (out / "report.html").write_text(html, encoding="utf-8", newline="\n")
    return {"report.json": sha256_text(text), "report.html": sha256_text(html)}

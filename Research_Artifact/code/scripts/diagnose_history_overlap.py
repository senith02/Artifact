"""DL-034 — measure how often start-ordered ④b history admits builds that had not finished.

The independent review of 2026-10-01 found that `causal_project_history()` admits an earlier
build whenever it *started* before the scored build, even if it was still running. A live
scheduler only knows the durations of builds that have **completed**. This script measures the
prevalence of that gap and its effect on `d̂`, and nothing else.

**What it reads.** Only the tracked P3-T2 test trace (`results/p3/test_trace.csv.gz`), which
holds every test build's start time, observed duration and the `d̂` the frozen pipeline
computed. Earlier builds' durations are used as history labels and to place their completion
(start + duration, the earliest possible finish), which is §A1.2 role 2. **It never reads
`y_fail`, carbon or TTFF**, so it measures the defect, not any outcome.

**Independence.** It does not call the function it audits. It recomputes the shipped
start-ordered rule first and must reproduce the trace's recorded ④b exactly, before it reports
anything about the completion-ordered rule.

Run:  python scripts/diagnose_history_overlap.py        (env: PYTHONPATH=.)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from scheduler_core import eligibility

ROOT = Path(__file__).resolve().parents[1].parent
TRACE = ROOT / "results" / "p3" / "test_trace.csv.gz"
POLICY = ROOT / "code" / "scheduler_core" / "config" / "policy_spec.yaml"
OUT_DIR = ROOT / "results" / "corrections" / "dl034"
COMMAND = "python scripts/diagnose_history_overlap.py"
D_THRESHOLD_S = 480.0   # frozen spec value (policy_spec.yaml sha256 34d689c9…); read-only here
USECOLS = ["replay_seq", "gh_project_name", "gh_is_pr", "git_branch", "arrival_utc",
           "d_hat_4b_seconds", "d_hat_4b_fallback", "d_hat_4b_n_history", "obs_duration_s"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def per_project(ts: np.ndarray, y: np.ndarray, end: np.ndarray, dur_known: np.ndarray):
    """Both history rules for one project's builds, in (start, replay_seq) order."""
    lab = ~np.isnan(y)
    # Start-ordered (shipped): labelled builds with start < t_b. Ties excluded by side="left".
    ys_start = y[lab]
    n_start = np.searchsorted(ts[lab], ts, side="left")
    med_start = pd.Series(ys_start).expanding().median().to_numpy()
    # Completion-ordered (DL-034): labelled builds with start + duration < t_b.
    order = np.lexsort((np.flatnonzero(lab), end[lab]))
    ends, ys_done = end[lab][order], y[lab][order]
    n_done = np.searchsorted(ends, ts, side="left")
    med_done = pd.Series(ys_done).expanding().median().to_numpy()

    def pick(med, n):
        out = np.full(len(n), np.nan)
        ok = n > 0
        out[ok] = med[n[ok] - 1]
        return out

    # Immediate strictly-earlier-started predecessor still running at t_b (the review's metric).
    prev_running = np.zeros(len(ts), dtype=bool)
    for i in range(1, len(ts)):
        j = i - 1
        while j >= 0 and ts[j] == ts[i]:
            j -= 1
        if j >= 0 and dur_known[j] and end[j] > ts[i]:
            prev_running[i] = True
    return n_start, pick(med_start, n_start), n_done, pick(med_done, n_done), prev_running


def main() -> None:
    t0 = time.perf_counter()
    t = pd.read_csv(TRACE, usecols=USECOLS, float_precision="round_trip")
    started = pd.to_datetime(t["arrival_utc"], utc=True)
    ts = (started - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy()
    dur = pd.to_numeric(t["obs_duration_s"], errors="coerce").to_numpy()
    usable = ~np.isnan(dur) & (dur > 0)
    y = np.where(usable, np.log1p(np.where(usable, dur, 0.0)), np.nan)
    end = ts + np.where(np.isnan(dur), 0.0, dur)

    n = len(t)
    cols = {k: np.zeros(n, dtype="int64") for k in ("n_start", "n_done")}
    cols |= {k: np.full(n, np.nan) for k in ("m_start", "m_done")}
    prev_running = np.zeros(n, dtype=bool)
    order = np.lexsort((t["replay_seq"].to_numpy(), ts, t["gh_project_name"].to_numpy()))
    proj_sorted = t["gh_project_name"].to_numpy()[order]
    bounds = np.flatnonzero(np.r_[True, proj_sorted[1:] != proj_sorted[:-1], True])
    for a, b in zip(bounds[:-1], bounds[1:]):
        idx = order[a:b]
        ns, ms, nd, md, pr = per_project(ts[idx], y[idx], end[idx], ~np.isnan(dur[idx]))
        cols["n_start"][idx], cols["m_start"][idx] = ns, ms
        cols["n_done"][idx], cols["m_done"][idx] = nd, md
        prev_running[idx] = pr

    # 1. The recomputed shipped rule must reproduce the trace before anything else is reported.
    rung = (t["d_hat_4b_fallback"] == "project").to_numpy()
    recomputed = np.expm1(cols["m_start"][rung])
    max_abs = float(np.max(np.abs(recomputed - t["d_hat_4b_seconds"].to_numpy()[rung])))
    n_equal = bool((cols["n_start"] == t["d_hat_4b_n_history"].to_numpy()).all())
    if max_abs != 0.0 or not n_equal:
        raise SystemExit(f"FATAL: start-ordered recomputation does not reproduce the trace "
                         f"(max |Δ| {max_abs} s, n_history equal {n_equal}) — no number reported")

    affected = cols["n_start"] > cols["n_done"]
    gap = (cols["n_start"] - cols["n_done"])[affected]
    both = affected & ~np.isnan(cols["m_start"]) & ~np.isnan(cols["m_done"])
    d_start, d_done = np.expm1(cols["m_start"]), np.expm1(cols["m_done"])
    rel = (d_done[both] - d_start[both]) / d_start[both]
    to_cold = affected & np.isnan(cols["m_done"]) & ~np.isnan(cols["m_start"])
    elig = np.array([eligibility.is_eligible(a, b) for a, b in zip(t["gh_is_pr"], t["git_branch"])])
    cross = both & elig & ((d_start >= D_THRESHOLD_S) != (d_done >= D_THRESHOLD_S))

    report = {
        "decision": "DL-034 (evidence for)",
        "command": COMMAND,
        "run_date": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
        "input": {"file": "results/p3/test_trace.csv.gz", "sha256": _sha256(TRACE),
                  "columns_read": USECOLS, "outcome_columns_read": []},
        "rules": {
            "start_ordered_shipped": "labelled builds of the project with start < t_b (ties excluded)",
            "completion_ordered_dl034": "labelled builds of the project with start + tr_duration < t_b",
            "completion_proxy": "start + tr_duration = earliest possible finish (no finish timestamp "
                                "exists in the release)",
        },
        "validation": {"project_rung_builds": int(rung.sum()),
                       "max_abs_diff_recomputed_vs_trace_s": max_abs,
                       "n_history_equal_all_builds": n_equal},
        "builds": int(n),
        "immediate_predecessor_still_running": {"n": int(prev_running.sum()),
                                                "pct": round(100 * prev_running.mean(), 2)},
        "history_includes_unfinished_build": {"n": int(affected.sum()),
                                              "pct": round(100 * affected.mean(), 2)},
        "unfinished_builds_in_history_among_affected": {
            "median": float(np.median(gap)), "p95": float(np.quantile(gap, 0.95)),
            "max": int(gap.max())},
        "d_hat_relative_change_among_affected": {
            "n": int(both.sum()), "median_pct": round(100 * float(np.median(rel)), 2),
            "abs_p95_pct": round(100 * float(np.quantile(np.abs(rel), 0.95)), 2)},
        "would_lose_all_completed_history": int(to_cold.sum()),
        "stage1_eligible_builds": int(elig.sum()),
        "eligible_and_affected": int((affected & elig).sum()),
        "eligible_crossing_d_threshold_480s": int(cross.sum()),
        "eligible_moving_to_cold_start": int((to_cold & elig).sum()),
        "caveat": "Test split only; train and calibration are not measured here. The frozen "
                  "threshold is applied to d̂ alone, so this bounds decision changes at the frozen "
                  "point under the frozen spec — it is not a re-fitted result.",
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "history_overlap.json").write_text(json.dumps(report, indent=2) + "\n",
                                                  encoding="utf-8")
    r = report
    md = f"""# DL-034 evidence — unfinished builds in start-ordered ④b history

> Generated by `PYTHONPATH=. {COMMAND}` on {r['run_date']}. Input: `results/p3/test_trace.csv.gz`
> (sha256 `{r['input']['sha256'][:16]}…`). **No outcome, carbon or TTFF column was read.**

**Validation (must pass before anything is reported).** The start-ordered rule recomputed here
reproduces the trace's recorded ④b on all {r['validation']['project_rung_builds']:,} project-rung
builds: max |Δ| = {r['validation']['max_abs_diff_recomputed_vs_trace_s']} s; `n_history` equal on
every build: {r['validation']['n_history_equal_all_builds']}.

| measure (test split, {r['builds']:,} builds) | value |
| :-- | --: |
| immediate strictly-earlier predecessor still running at arrival | {r['immediate_predecessor_still_running']['n']:,} ({r['immediate_predecessor_still_running']['pct']}%) |
| history includes ≥ 1 unfinished build | {r['history_includes_unfinished_build']['n']:,} ({r['history_includes_unfinished_build']['pct']}%) |
| unfinished builds in history, among affected — median / p95 / max | {r['unfinished_builds_in_history_among_affected']['median']:.0f} / {r['unfinished_builds_in_history_among_affected']['p95']:.0f} / {r['unfinished_builds_in_history_among_affected']['max']} |
| relative change in d̂, among affected with history under both rules — median / \\|·\\| p95 | {r['d_hat_relative_change_among_affected']['median_pct']:+.2f}% / {r['d_hat_relative_change_among_affected']['abs_p95_pct']}% |
| builds that would have no completed history (→ cold-start rung) | {r['would_lose_all_completed_history']:,} |
| Stage-1 eligible builds | {r['stage1_eligible_builds']:,} |
| eligible and affected | {r['eligible_and_affected']:,} |
| eligible builds whose d̂ crosses the frozen 480 s threshold | {r['eligible_crossing_d_threshold_480s']:,} |
| eligible builds that would move to the cold-start rung | {r['eligible_moving_to_cold_start']:,} |

**Rules.** Shipped: {r['rules']['start_ordered_shipped']}. DL-034: {r['rules']['completion_ordered_dl034']}
({r['rules']['completion_proxy']}).

**Caveat.** {r['caveat']}
"""
    (OUT_DIR / "history_overlap.md").write_text(md, encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

"""P0-T2 S2 — empirical modelling-grain investigation.

Rows in TravisTorrent are *build jobs*; we intend to model at *build* grain
(aggregate by ``tr_build_id``). Before fixing the aggregation rule (and logging
it as a decision), this script MEASURES, on the real file, how the relevant
columns actually vary within a build:

  * jobs per build (and how it compares to the ``tr_jobs`` field);
  * whether ``tr_status`` is constant within a build  -> can it be the label?
  * whether ``tr_duration`` is constant within a build -> build-level or per-job?
  * how per-job duration columns relate to ``tr_duration`` -> which to SUM for
    the DL-007 energy model ("summed job durations").

Output: prints a summary and writes results/p0/grain_investigation.json.
Run:  python scripts/investigate_grain.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scheduler_core import data

OUT = Path(__file__).resolve().parents[1].parent / "results" / "p0" / "grain_investigation.json"

USECOLS = [
    "tr_build_id", "gh_project_name", "tr_status", "tr_duration",
    "tr_job_id", "tr_jobs", "tr_log_buildduration", "tr_log_testduration",
    "tr_log_setup_time",
]


def main() -> int:
    # Per-build accumulators (combine correctly across chunk boundaries).
    n_jobs: dict[str, int] = {}
    status_first: dict[str, str] = {}
    status_const: dict[str, bool] = {}
    dur_first: dict[str, str] = {}
    dur_const: dict[str, bool] = {}
    tr_jobs_first: dict[str, str] = {}

    total_rows = 0
    n_chunks = 0
    # Aggregate duration sums per build for the energy-column comparison.
    sum_logbuild: dict[str, float] = {}
    sum_logtest: dict[str, float] = {}

    for chunk in data.read_chunks(usecols=USECOLS, chunksize=300_000):
        n_chunks += 1
        total_rows += len(chunk)
        bid = chunk["tr_build_id"].to_numpy()
        status = chunk["tr_status"].to_numpy()
        dur = chunk["tr_duration"].to_numpy()
        trjobs = chunk["tr_jobs"].to_numpy()
        lb = pd.to_numeric(chunk["tr_log_buildduration"], errors="coerce").to_numpy()
        lt = pd.to_numeric(chunk["tr_log_testduration"], errors="coerce").to_numpy()

        for i in range(len(chunk)):
            b = bid[i]
            n_jobs[b] = n_jobs.get(b, 0) + 1
            s = status[i]
            if b not in status_first:
                status_first[b] = s
                status_const[b] = True
                dur_first[b] = dur[i]
                dur_const[b] = True
                tr_jobs_first[b] = trjobs[i]
                sum_logbuild[b] = 0.0
                sum_logtest[b] = 0.0
            else:
                if s != status_first[b]:
                    status_const[b] = False
                if dur[i] != dur_first[b]:
                    dur_const[b] = False
            if not np.isnan(lb[i]):
                sum_logbuild[b] += float(lb[i])
            if not np.isnan(lt[i]):
                sum_logtest[b] += float(lt[i])

        print(f"  chunk {n_chunks}: {total_rows:,} rows, {len(n_jobs):,} builds so far")

    n_builds = len(n_jobs)
    jobs_arr = np.array(list(n_jobs.values()))
    multi_job_builds = int((jobs_arr > 1).sum())
    status_varying = int(sum(1 for v in status_const.values() if not v))
    dur_varying = int(sum(1 for v in dur_const.values() if not v))

    # tr_jobs field vs observed job-row count (where tr_jobs is an int).
    trjobs_match = 0
    trjobs_checked = 0
    for b, claimed in tr_jobs_first.items():
        try:
            c = int(float(claimed))
        except (TypeError, ValueError):
            continue
        trjobs_checked += 1
        if c == n_jobs[b]:
            trjobs_match += 1

    # For multi-job builds: does tr_duration (build-level) ~ summed log durations?
    # Sample to keep the report compact.
    examples = []
    shown = 0
    for b in n_jobs:
        if n_jobs[b] > 1 and shown < 5:
            examples.append({
                "tr_build_id": b,
                "n_job_rows": n_jobs[b],
                "tr_jobs_field": tr_jobs_first[b],
                "tr_status": status_first[b],
                "tr_status_constant": status_const[b],
                "tr_duration": dur_first[b],
                "tr_duration_constant": dur_const[b],
                "sum_tr_log_buildduration": round(sum_logbuild[b], 1),
            })
            shown += 1

    report = {
        "command": "python scripts/investigate_grain.py",
        "total_job_rows": total_rows,
        "n_builds": n_builds,
        "jobs_per_build": {
            "min": int(jobs_arr.min()),
            "max": int(jobs_arr.max()),
            "mean": round(float(jobs_arr.mean()), 4),
            "median": int(np.median(jobs_arr)),
            "p95": int(np.percentile(jobs_arr, 95)),
            "single_job_builds": int((jobs_arr == 1).sum()),
            "multi_job_builds": multi_job_builds,
        },
        "tr_status_within_build": {
            "builds_with_varying_status": status_varying,
            "pct_varying": round(100 * status_varying / n_builds, 4),
            "interpretation": "constant => tr_status is a build-level label",
        },
        "tr_duration_within_build": {
            "builds_with_varying_duration": dur_varying,
            "pct_varying": round(100 * dur_varying / n_builds, 4),
            "interpretation": "constant => tr_duration is build-level (repeated per job row)",
        },
        "tr_jobs_field_vs_observed": {
            "builds_checked": trjobs_checked,
            "builds_matching": trjobs_match,
            "pct_matching": round(100 * trjobs_match / trjobs_checked, 4) if trjobs_checked else None,
        },
        "multi_job_examples": examples,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== GRAIN INVESTIGATION ===")
    print(json.dumps({k: v for k, v in report.items() if k != "multi_job_examples"}, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

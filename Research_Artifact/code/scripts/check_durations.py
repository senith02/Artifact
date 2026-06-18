"""P0-T2 S2 helper — measure availability of duration columns.

DL-007 wants energy from "summed job durations". The grain investigation showed
tr_duration is build-level (constant per build), so it is NOT a per-job figure.
This checks how usable the per-job log-duration columns are (null rates and
how often the per-build SUM of tr_log_buildduration is > 0), so the energy-
duration rule can be chosen on evidence rather than assumption.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scheduler_core import data

OUT = Path(__file__).resolve().parents[1].parent / "results" / "p0" / "duration_check.json"
COLS = ["tr_build_id", "tr_duration", "tr_log_buildduration", "tr_log_testduration", "tr_log_setup_time"]


def main() -> int:
    n = 0
    nulls = {c: 0 for c in COLS if c != "tr_build_id"}
    zero_or_neg = {c: 0 for c in COLS if c != "tr_build_id"}
    sum_logbuild: dict[str, float] = {}

    for chunk in data.read_chunks(usecols=COLS, chunksize=300_000):
        n += len(chunk)
        for c in nulls:
            num = pd.to_numeric(chunk[c], errors="coerce")
            nulls[c] += int(num.isna().sum())
            zero_or_neg[c] += int((num <= 0).sum())
        bid = chunk["tr_build_id"].to_numpy()
        lb = pd.to_numeric(chunk["tr_log_buildduration"], errors="coerce").to_numpy()
        for i in range(len(chunk)):
            b = bid[i]
            v = lb[i]
            sum_logbuild[b] = sum_logbuild.get(b, 0.0) + (0.0 if np.isnan(v) else float(v))

    sums = np.array(list(sum_logbuild.values()))
    report = {
        "command": "python scripts/check_durations.py",
        "total_job_rows": n,
        "n_builds": len(sum_logbuild),
        "per_column_null_rate_pct": {c: round(100 * nulls[c] / n, 4) for c in nulls},
        "per_column_nonpositive_rate_pct": {c: round(100 * zero_or_neg[c] / n, 4) for c in zero_or_neg},
        "builds_with_positive_summed_logbuildduration": int((sums > 0).sum()),
        "pct_builds_with_positive_sum": round(100 * (sums > 0).sum() / len(sums), 4),
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

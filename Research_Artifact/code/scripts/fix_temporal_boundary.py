"""DL-027 §1 — fix the temporal-robustness boundary before the test split is opened.

The boundary is the median `gh_build_started_at` over the train + calibration
analytic builds. It is computed from those two splits only, so no test build can
influence where the early/late cut falls. The value is written once and read by
P3-T4; it is never recomputed after P3-T1 opens the test split.

**Split discipline.** Train + calibration only, from the frozen
`results/p1/split_assignment.csv`. The 170 test projects are dropped unread and
the count is reported.

Run:  python scripts/fix_temporal_boundary.py        (env: PYTHONPATH=.)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from scheduler_core import data, features

ROOT = Path(__file__).resolve().parents[1].parent
OUT = ROOT / "results" / "p3" / "predeclared" / "temporal_boundary.json"
SPLIT_ASSIGNMENT = ROOT / "results" / "p1" / "split_assignment.csv"
COMMAND = "python scripts/fix_temporal_boundary.py"
CHUNK = 300_000

READ_COLUMNS: tuple[str, ...] = (
    "tr_build_id", "gh_project_name", "gh_build_started_at", "tr_status",
)
ALLOWED_SPLITS: frozenset[str] = frozenset({"train", "calibration"})


def main() -> None:
    t0 = time.perf_counter()
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists — the boundary is fixed once (DL-027 §1).")

    split_bytes = SPLIT_ASSIGNMENT.read_bytes()
    split_map = dict(
        pd.read_csv(SPLIT_ASSIGNMENT, dtype=str)
        [["gh_project_name", "split"]].itertuples(index=False, name=None))

    running: pd.DataFrame | None = None
    for chunk in data.read_chunks(chunksize=CHUNK, usecols=READ_COLUMNS):
        cols = [c for c in chunk.columns if c != "tr_build_id"]
        agg = chunk.groupby("tr_build_id", sort=False)[cols].first()
        running = agg if running is None else (
            pd.concat([running, agg]).groupby(level=0, sort=False).first())
    builds = running.reset_index()

    builds = builds.loc[features.analytic_mask(builds)].reset_index(drop=True)
    split = builds["gh_project_name"].map(split_map)
    n_test = int((split == "test").sum())
    builds = builds.loc[split.isin(ALLOWED_SPLITS)].reset_index(drop=True)
    split = builds["gh_project_name"].map(split_map)

    started = pd.to_datetime(builds["gh_build_started_at"], utc=True)
    boundary = started.median()
    early = started < boundary

    report = {
        "decision": "DL-027 §1",
        "rule": "median gh_build_started_at over train + calibration analytic builds; "
                "early = started < boundary, late = started >= boundary",
        "boundary_utc": boundary.isoformat(),
        "command": COMMAND,
        "run_date": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
        "splits_read": sorted(ALLOWED_SPLITS),
        "split_assignment_sha256": hashlib.sha256(split_bytes).hexdigest(),
        "test_split_builds_dropped_unread": n_test,
        "builds_used": int(len(builds)),
        "projects_used": int(builds["gh_project_name"].nunique()),
        "first_build_utc": started.min().isoformat(),
        "last_build_utc": started.max().isoformat(),
        "counts_by_period_and_split": {
            period: {s: int(((early if period == "early" else ~early) & (split == s)).sum())
                     for s in sorted(ALLOWED_SPLITS)}
            for period in ("early", "late")
        },
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

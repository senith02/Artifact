"""P2-T1 S0 — profile the Stage-1 gate's two raw inputs, before the gate exists.

`context/dataset_reference.md` §"Eligibility gate inputs" records that
TravisTorrent carries **no** scheduled/nightly, release/tag, hotfix or
manual-trigger flag, so the frozen §3.4 classes have to be approximated from
`gh_is_pr` + `git_branch` + heuristics. That approximation is a modelling
decision (R4) and P2-T1 S1 requires it to be a decision-log entry written
**before** the gate is coded.

This script exists so that entry is argued from measured facts rather than from
assumptions about what branch names look like in this corpus. It answers four
questions and nothing else:

  1. how often each of the two inputs is present/missing at build grain;
  2. what the branch-name distribution actually is (top names + long tail);
  3. how many builds match candidate production/protected-branch patterns and
     candidate release/tag-like patterns;
  4. how those interact with `gh_is_pr`.

**Split discipline.** Only **train + calibration** projects are read
(`results/p1/split_assignment.csv`). The 170 test projects are filtered out
before any statistic is computed, and the run reports how many build rows were
dropped unread so the claim is checkable. Stage 1 is a deterministic gate, not
a fitted policy, but its constants are still chosen by a human looking at data
— so they are chosen on the same splits every other design choice may use
(§A1.7's use-discipline).

No label and no duration column is read: this script cannot see an outcome.

Run:  python scripts/profile_branches.py        (env: PYTHONPATH=.)
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from scheduler_core import data, features

RESULTS = Path(__file__).resolve().parents[1].parent / "results" / "p2"
SPLIT_ASSIGNMENT = (Path(__file__).resolve().parents[1].parent
                    / "results" / "p1" / "split_assignment.csv")
RUN_DATE = "2026-09-17"
COMMAND = "python scripts/profile_branches.py"
CHUNK = 300_000
TOP_N = 40

#: Read the gate's two inputs plus what the analytic funnel and the split need.
#: `tr_status` is the funnel's label-recognition filter (features.analytic_mask),
#: not a statistic this script reports.
READ_COLUMNS: tuple[str, ...] = (
    "tr_build_id", "gh_project_name", "gh_is_pr", "git_branch",
    "gh_build_started_at", "tr_status",
)

#: Splits this profile is allowed to read. Test is excluded by construction.
ALLOWED_SPLITS: frozenset[str] = frozenset({"train", "calibration"})

# --------------------------------------------------------------------------- #
# Candidate patterns — these are the *questions asked of the data*, not yet the
# gate's rule. The rule they inform is fixed in DL-020 and implemented in
# scheduler_core/eligibility.py; nothing here is imported by the gate.
# --------------------------------------------------------------------------- #

CANDIDATE_PROTECTED: dict[str, str] = {
    "master": r"^master$",
    "main": r"^main$",
    "trunk": r"^trunk$",
    "default": r"^default$",
    "develop_or_dev": r"^(develop|dev)$",
    "production_like": r"^(production|prod|live)$",
    "release_branch": r"^release[/_-]",
    "stable_suffix": r"(^|[/_-])stable$",
    "maint_branch": r"^(maint|maintenance)([/_-]|$)",
    "version_branch": r"^v?\d+(\.\d+)+([/_-].*)?$",
    "hotfix_like": r"(^|[/_-])(hotfix|hotfixes)([/_-]|$)",
}

CANDIDATE_RELEASE_TAG: dict[str, str] = {
    "tag_like_semver": r"^v?\d+\.\d+(\.\d+)?([-+].*)?$",
    "rc_like": r"(^|[/_-])(rc\d*|beta|alpha)([/_-]|$)",
}


def load_split_map() -> dict[str, str]:
    """Project -> split, from the frozen P1-T3 assignment."""
    df = pd.read_csv(SPLIT_ASSIGNMENT, dtype=str)
    return dict(zip(df["gh_project_name"], df["split"]))


def load_builds(split_map: dict[str, str]) -> tuple[pd.DataFrame, dict[str, int]]:
    """Build-grain rows for train+calibration projects only.

    Returns the frame and a funnel record that states how much was dropped and
    why — including the test-split rows, which are discarded unread.
    """
    running: pd.DataFrame | None = None
    n_job_rows = 0
    for chunk in data.read_chunks(chunksize=CHUNK, usecols=READ_COLUMNS):
        n_job_rows += len(chunk)
        cols = [c for c in chunk.columns if c != "tr_build_id"]
        agg = chunk.groupby("tr_build_id", sort=False)[cols].first()
        running = agg if running is None else (
            pd.concat([running, agg]).groupby(level=0, sort=False).first())
    builds = running.reset_index()

    n_builds_all = len(builds)
    builds = builds.loc[features.analytic_mask(builds)].reset_index(drop=True)
    n_analytic = len(builds)

    split = builds["gh_project_name"].map(split_map)
    n_unassigned = int(split.isna().sum())
    keep = split.isin(ALLOWED_SPLITS)
    n_test_dropped = int((split == "test").sum())
    builds = builds.loc[keep].reset_index(drop=True)
    builds["split"] = split.loc[keep].to_numpy()

    funnel = {
        "job_rows_read": n_job_rows,
        "builds_after_aggregation": n_builds_all,
        "analytic_builds": n_analytic,
        "test_split_builds_dropped_unread": n_test_dropped,
        "unassigned_builds_dropped": n_unassigned,
        "builds_profiled_train_plus_calibration": len(builds),
    }
    return builds, funnel


def branch_stats(builds: pd.DataFrame) -> dict:
    """Presence, top names, and candidate-pattern coverage for `git_branch`."""
    branch = builds["git_branch"]
    present = branch.notna() & (branch.astype(str).str.strip() != "")
    named = branch.loc[present].astype(str).str.strip()

    counts = Counter(named)
    top = [{"branch": b, "builds": n, "share": n / len(builds)}
           for b, n in counts.most_common(TOP_N)]

    patterns: dict[str, dict] = {}
    for group, table in (("protected_like", CANDIDATE_PROTECTED),
                         ("release_tag_like", CANDIDATE_RELEASE_TAG)):
        for name, rx in table.items():
            hit = named.str.match(rx, case=False, na=False)
            patterns[name] = {
                "group": group,
                "pattern": rx,
                "builds": int(hit.sum()),
                "share_of_named": float(hit.mean()) if len(named) else 0.0,
                "distinct_branch_names": int(named.loc[hit].nunique()),
            }

    return {
        "builds": int(len(builds)),
        "branch_present": int(present.sum()),
        "branch_missing": int((~present).sum()),
        "branch_missing_share": float((~present).mean()),
        "distinct_branch_names": int(named.nunique()),
        "top_branches": top,
        "candidate_patterns": patterns,
    }


def is_pr_stats(builds: pd.DataFrame) -> dict:
    """Presence and value distribution for `gh_is_pr`, crossed with branch."""
    raw = builds["gh_is_pr"]
    present = raw.notna() & (raw.astype(str).str.strip() != "")
    vals = raw.loc[present].astype(str).str.strip().str.lower()
    value_counts = {k: int(v) for k, v in vals.value_counts().items()}

    truthy = vals.isin({"true", "1", "t", "yes"})
    is_pr = pd.Series(False, index=builds.index)
    is_pr.loc[present] = truthy.to_numpy()

    branch = builds["git_branch"].astype(str).str.strip().str.lower()
    master_like = branch.isin({"master", "main", "trunk", "default"})

    return {
        "is_pr_present": int(present.sum()),
        "is_pr_missing": int((~present).sum()),
        "raw_value_counts": value_counts,
        "pr_builds": int(is_pr.sum()),
        "pr_share": float(is_pr.mean()),
        "cross_tab": {
            "pr_and_master_like": int((is_pr & master_like).sum()),
            "pr_and_other_branch": int((is_pr & ~master_like).sum()),
            "push_and_master_like": int((~is_pr & master_like).sum()),
            "push_and_other_branch": int((~is_pr & ~master_like).sum()),
        },
    }


def render_markdown(report: dict) -> str:
    f, b, p = report["funnel"], report["branch"], report["is_pr"]
    L: list[str] = []
    L.append("# P2-T1 S0 — Stage-1 gate input profile (train + calibration only)\n")
    L.append(f"*Run `{report['command']}` on {report['run_date']}; "
             f"{report['elapsed_s']:.1f}s. Every number below is from this run (R1).*\n")
    L.append("> **Split discipline.** The 170 test projects were filtered out before any "
             "statistic was computed — see `test_split_builds_dropped_unread` below. "
             "No label and no duration statistic is reported; `tr_status` is read only as "
             "the analytic funnel's label-recognition filter.\n")

    L.append("## Funnel\n")
    L.append("| Stage | Builds |")
    L.append("| :-- | --: |")
    for k, v in f.items():
        L.append(f"| {k.replace('_', ' ')} | {v:,} |")
    L.append("")

    L.append("## `git_branch` — presence\n")
    L.append(f"- Present: **{b['branch_present']:,}** / {b['builds']:,} builds")
    L.append(f"- Missing: **{b['branch_missing']:,}** "
             f"({b['branch_missing_share']:.4%})")
    L.append(f"- Distinct branch names: **{b['distinct_branch_names']:,}**\n")

    L.append(f"## `git_branch` — top {TOP_N} names\n")
    L.append("| # | Branch | Builds | Share of profiled builds |")
    L.append("| --: | :-- | --: | --: |")
    for i, row in enumerate(b["top_branches"], 1):
        L.append(f"| {i} | `{row['branch']}` | {row['builds']:,} | {row['share']:.4%} |")
    L.append("")

    L.append("## Candidate patterns (questions asked of the data — not yet the rule)\n")
    L.append("| Pattern | Group | Regex | Builds | Share of named | Distinct names |")
    L.append("| :-- | :-- | :-- | --: | --: | --: |")
    for name, rec in b["candidate_patterns"].items():
        L.append(f"| {name} | {rec['group']} | `{rec['pattern']}` | {rec['builds']:,} | "
                 f"{rec['share_of_named']:.4%} | {rec['distinct_branch_names']:,} |")
    L.append("")

    L.append("## `gh_is_pr`\n")
    L.append(f"- Present: **{p['is_pr_present']:,}**, missing: **{p['is_pr_missing']:,}**")
    L.append(f"- Raw values: `{p['raw_value_counts']}`")
    L.append(f"- PR-triggered builds: **{p['pr_builds']:,}** ({p['pr_share']:.4%})\n")
    L.append("| Cross-tab | Builds |")
    L.append("| :-- | --: |")
    for k, v in p["cross_tab"].items():
        L.append(f"| {k.replace('_', ' ')} | {v:,} |")
    L.append("")

    L.append("## What this profile cannot tell us\n")
    L.append("The dataset has no scheduled/nightly flag, no release/tag trigger flag, no "
             "hotfix label, no manual-trigger flag, no branch-protection state and no "
             "developer urgency signal. The patterns above are *name-shaped guesses* at "
             "constructs the data does not record. Any gate built on them is an "
             "approximation whose error is unmeasurable in this corpus — which is the "
             "substance of DL-020.\n")
    return "\n".join(L)


def main() -> None:
    t0 = time.perf_counter()
    RESULTS.mkdir(parents=True, exist_ok=True)

    split_map = load_split_map()
    print(f"split map: {len(split_map):,} projects "
          f"({sum(1 for v in split_map.values() if v in ALLOWED_SPLITS):,} readable here)")

    builds, funnel = load_builds(split_map)
    print(f"profiling {len(builds):,} builds "
          f"(test dropped unread: {funnel['test_split_builds_dropped_unread']:,})")

    report = {
        "command": COMMAND,
        "run_date": RUN_DATE,
        "splits_read": sorted(ALLOWED_SPLITS),
        "split_assignment": str(SPLIT_ASSIGNMENT),
        "funnel": funnel,
        "branch": branch_stats(builds),
        "is_pr": is_pr_stats(builds),
        "elapsed_s": time.perf_counter() - t0,
    }

    (RESULTS / "branch_profile.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    (RESULTS / "branch_profile.md").write_text(
        render_markdown(report), encoding="utf-8")
    print(f"wrote {RESULTS / 'branch_profile.json'}")
    print(f"wrote {RESULTS / 'branch_profile.md'}")
    print(f"done in {report['elapsed_s']:.1f}s")


if __name__ == "__main__":
    main()

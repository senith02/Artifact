"""P1-T3 S3 — build the real three-way split and freeze it.

One pass over the backbone CSV produces the analytic build set (the same funnel
`features.py` uses, via `features.analytic_mask`), applies
`scheduler_core.splits.make_splits` per eval_protocol §2, and writes:

  * ``results/p1/splits.json``            — the manifest: provenance, per-split
    project counts, build counts, class balance, duration distribution, time
    range, and the full project lists including the **test projects reserved for
    the single test pass**;
  * ``results/p1/split_assignment.csv``   — the frozen artifact: one row per
    project, ``gh_project_name,split``. Small, diffable, and the thing every
    later task must reproduce;
  * ``results/p1/splits_summary.md``      — the human-readable summary table.

**Freeze.** The manifest carries a SHA-256 over the project→split mapping. Any
later run that produces a different digest has a different split, and the §2
guarantee ("test is opened exactly once, against a split fixed beforehand") is
broken. ``--verify`` re-derives the split and checks it against the frozen files
without rewriting them.

Run:   python scripts/make_splits.py            (env: PYTHONPATH=.)
Verify: python scripts/make_splits.py --verify
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

from scheduler_core import config, data, features, splits

RESULTS = Path(__file__).resolve().parents[1].parent / "results" / "p1"
RUN_DATE = "2026-08-15"
CHUNK = 300_000
COMMAND = "python scripts/make_splits.py"

#: Columns needed to form and describe the split. `tr_duration` is here for the
#: manifest's descriptive statistics only (§A1.2 role 1, accounting) — it is not
#: passed to `make_splits`, which reads project identity and time alone.
READ_COLUMNS: tuple[str, ...] = (
    "tr_build_id", "gh_project_name", "gh_lang", "tr_status",
    "gh_build_started_at", "tr_duration",
)


def load_analytic_builds(chunksize: int = CHUNK) -> pd.DataFrame:
    """Build-grain analytic set (DL-009 aggregation + the P0-T2 funnel)."""
    running: pd.DataFrame | None = None
    for chunk in data.read_chunks(chunksize=chunksize, usecols=READ_COLUMNS):
        agg = data.aggregate_to_builds(chunk).set_index("tr_build_id")
        if running is None:
            running = agg
            continue
        cat = pd.concat([running, agg])
        g = cat.groupby(level=0, sort=False)
        cols = [c for c in cat.columns if c not in ("tr_duration", "n_jobs")]
        out = g[cols].first()
        out["tr_duration"] = g["tr_duration"].max()
        out["n_jobs"] = g["n_jobs"].sum()
        running = out
    builds = running.reset_index()
    return builds.loc[features.analytic_mask(builds)].reset_index(drop=True)


def build_manifest(builds: pd.DataFrame, split_frames: dict[str, pd.DataFrame],
                   assignment: dict[str, str], elapsed: float) -> dict:
    per_split = splits.summarise_splits(split_frames)
    return {
        "provenance": {
            "command": COMMAND,
            "run_date": RUN_DATE,
            "dataset_path": str(data.DEFAULT_DATASET_PATH),
            "chunksize": CHUNK,
            "seed": config.RANDOM_SEED,
            "proportions": {n: p for n, p in
                            zip(splits.SPLIT_NAMES, splits.DEFAULT_PROPORTIONS)},
            "protocol": "results/p0/eval_protocol.md §2 (DL-006)",
            "shuffle": "numpy.random.default_rng(seed).permutation over "
                       "sorted project names",
            "assignment_rule": "greedy: each project (in shuffled order) goes to "
                               "the split with the largest remaining build-volume "
                               "deficit; ties break toward the earlier split in "
                               "(train, calibration, test)",
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "elapsed_s": round(elapsed, 1),
        },
        "freeze": {
            "frozen": True,
            "assignment_sha256": splits.assignment_hash(assignment),
            "n_projects": len(assignment),
            "artifact": "results/p1/split_assignment.csv",
            "note": "Test projects are opened exactly once, in Phase 3 (§2 "
                    "use-discipline). Any run whose digest differs is not this "
                    "split.",
        },
        "totals": {
            "analytic_builds": int(len(builds)),
            "projects": int(builds["gh_project_name"].nunique()),
            "assigned_builds": int(sum(len(f) for f in split_frames.values())),
        },
        "checks": {
            "projects_disjoint": "PASS",
            "time_ordered": "PASS",
            "complete_partition_no_exclusions": "PASS",
        },
        "per_split": per_split,
        "project_lists": {
            name: sorted(pd.unique(frame["gh_project_name"]).tolist())
            for name, frame in split_frames.items()
        },
    }


def write_summary_md(m: dict) -> None:
    L: list[str] = []
    L.append("# Split Manifest Summary — three-way, project-disjoint (P1-T3)\n")
    L.append(f"> Generated by `{m['provenance']['command']}` on "
             f"{m['provenance']['run_date']}. Every number comes from that run (R1).\n")
    L.append(f"> Protocol: {m['provenance']['protocol']} · seed "
             f"`{m['provenance']['seed']}` · grain: build (DL-009).\n")

    L.append("\n## Freeze\n")
    fr = m["freeze"]
    L.append(f"- **Frozen:** {fr['frozen']}")
    L.append(f"- **Assignment SHA-256:** `{fr['assignment_sha256']}`")
    L.append(f"- **Projects assigned:** {fr['n_projects']:,}")
    L.append(f"- **Artifact:** `{fr['artifact']}`")
    L.append(f"- {fr['note']}\n")

    L.append("\n## Checks\n")
    for k, v in m["checks"].items():
        L.append(f"- `{k}`: **{v}**")
    t = m["totals"]
    L.append(f"- Analytic builds in = **{t['analytic_builds']:,}**, assigned out = "
             f"**{t['assigned_builds']:,}** (equal ⇒ no silent exclusions)\n")

    L.append("\n## Per-split summary\n")
    L.append("| split | projects | builds | share | target | dev (pp) | failure rate | "
             "median duration (s) | first build | last build |")
    L.append("| :-- | --: | --: | --: | --: | --: | --: | --: | :-- | :-- |")
    for name in splits.SPLIT_NAMES:
        e = m["per_split"][name]
        d = e.get("duration_s", {})
        L.append(
            f"| **{name}** | {e['n_projects']:,} | {e['n_builds']:,} | "
            f"{100 * e['share_of_builds']:.2f}% | {100 * e['target_share']:.0f}% | "
            f"{e['share_deviation_pp']:+.2f} | {e['failure_rate_pct']}% | "
            f"{d.get('p50')} | {e['time_range']['first_build']} | "
            f"{e['time_range']['last_build']} |"
        )
    L.append("\nDuration statistics are **descriptive only** — eval_protocol §A1.2 "
             "role 1 (accounting). The split itself is formed from project identity "
             "and build volume alone; no label, duration, feature, or model result "
             "enters it.\n")

    L.append("\n## Duration distribution per split (seconds, descriptive)\n")
    L.append("| split | count | missing | min | p25 | p50 | p75 | p95 | max | mean |")
    L.append("| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |")
    for name in splits.SPLIT_NAMES:
        d = m["per_split"][name].get("duration_s", {})
        L.append(f"| {name} | {d.get('count', 0):,} | {d.get('missing', 0):,} | "
                 f"{d.get('min')} | {d.get('p25')} | {d.get('p50')} | "
                 f"{d.get('p75')} | {d.get('p95')} | {d.get('max')} | "
                 f"{d.get('mean')} |")

    L.append("\n## ⚠ Methodological threats measured in this split (DL-017)\n")
    ps = m["per_split"]
    rates = {n: ps[n]["failure_rate_pct"] for n in splits.SPLIT_NAMES}
    spread = max(rates.values()) - min(rates.values())
    p95 = {n: ps[n]["duration_s"]["p95"] for n in splits.SPLIT_NAMES}
    L.append("These follow from splitting by **project** — projects differ in base "
             "rate and in build cost, so project-disjoint splits are not "
             "distribution-matched. Nothing here is a protocol deviation; §2 is "
             "followed exactly. They are recorded because they bind how later "
             "results must be read.\n")
    L.append(f"1. **Failure-rate heterogeneity.** train {rates['train']}% · "
             f"calibration {rates['calibration']}% · test {rates['test']}% — a "
             f"spread of **{spread:.2f} pp**. The calibration split fits the "
             "probability calibrator and selects the operating threshold (§5), so "
             "it is tuned at a base rate that differs from the test population's. "
             "Calibration metrics on test (Brier, ECE) must be reported against "
             "this shift, not as if prevalence were constant.")
    L.append(f"2. **Duration heterogeneity.** p95 build duration: train "
             f"{p95['train']:,.0f}s · calibration {p95['calibration']:,.0f}s · test "
             f"{p95['test']:,.0f}s. The calibration split has the heaviest tail, and "
             "`duration_control_spec.md` selects the primary `d̂` form by "
             "calibration-split MAE — so form selection happens on a duration "
             "distribution that is not the test one. P1-T4 must report this "
             "alongside the chosen form. *(Descriptive only — §A1.2 role 1.)*")
    L.append(f"3. **Split time ranges overlap end-to-end** "
             f"({ps['train']['time_range']['first_build'][:10]} → "
             f"{ps['train']['time_range']['last_build'][:10]} for train, and "
             "similarly for the other two). This is by design — the split is "
             "project-disjoint, **not** time-disjoint — and it is the measured "
             "condition that DL-014 (still **Proposed/unresolved**) reasons about. "
             "Recorded here as a measurement only; it resolves nothing.\n")

    L.append("\n## Test projects — reserved for the single test pass\n")
    test_projects = m["project_lists"]["test"]
    L.append(f"{len(test_projects):,} projects are held for Phase 3 and must not be "
             "read before it (§2 use-discipline). The full list is in "
             "`splits.json` under `project_lists.test`; the first 25 are:\n")
    for p in test_projects[:25]:
        L.append(f"- `{p}`")
    L.append("")
    (RESULTS / "splits_summary.md").write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="re-derive the split and check it against the frozen "
                         "files; write nothing")
    args = ap.parse_args()

    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)

    print(f"reading {data.DEFAULT_DATASET_PATH} …")
    builds = load_analytic_builds()
    print(f"  analytic builds: {len(builds):,} across "
          f"{builds['gh_project_name'].nunique():,} projects")

    split_frames = splits.make_splits(builds)          # asserts §2 on its output
    assignment = {
        project: name
        for name, frame in split_frames.items()
        for project in pd.unique(frame["gh_project_name"])
    }
    digest = splits.assignment_hash(assignment)
    print(f"  assignment digest: {digest}")
    for name in splits.SPLIT_NAMES:
        f = split_frames[name]
        print(f"  {name:12s} {f['gh_project_name'].nunique():5,} projects  "
              f"{len(f):9,} builds  {100 * len(f) / len(builds):5.2f}%")

    manifest = build_manifest(builds, split_frames, assignment, time.time() - t0)
    assign_csv = RESULTS / "split_assignment.csv"
    manifest_json = RESULTS / "splits.json"

    if args.verify:
        if not manifest_json.exists() or not assign_csv.exists():
            print("FATAL: frozen split artifacts not found — nothing to verify")
            return 1
        frozen = json.loads(manifest_json.read_text(encoding="utf-8"))
        frozen_digest = frozen["freeze"]["assignment_sha256"]
        if frozen_digest != digest:
            print(f"FATAL: digest mismatch — frozen {frozen_digest}, "
                  f"re-derived {digest}")
            return 1
        on_disk = pd.read_csv(assign_csv, dtype=str)
        if dict(zip(on_disk["gh_project_name"], on_disk["split"])) != assignment:
            print("FATAL: split_assignment.csv does not match the re-derived split")
            return 1
        print(f"\nVERIFY PASSED — the split reproduces exactly ({digest})")
        return 0

    pd.DataFrame(
        sorted(assignment.items()), columns=["gh_project_name", "split"]
    ).to_csv(assign_csv, index=False)
    manifest_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_summary_md(manifest)
    print(f"\nwrote {manifest_json}, split_assignment.csv and splits_summary.md "
          f"in {manifest['provenance']['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

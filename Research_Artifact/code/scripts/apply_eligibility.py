"""P2-T1 S4 — run the Stage-1 gate over the real corpus and produce gate evidence.

Four things, and the third is the one that matters:

1. apply `scheduler_core.eligibility` to every train + calibration build, under
   both DL-020 variants, and report the deferrable fraction and the per-rule
   breakdown — the numbers DL-020 promised would be *measured* rather than
   declared;
2. audit the gate's own output with `replay/validate_invariants.py`, which is
   the §4 eligibility-gate-safety check (expected: 0 violations, by
   construction);
3. **exhaustively cross-check the two implementations** on every distinct
   `(gh_is_pr, git_branch)` pair in the corpus — all 54,512 branch names, not a
   curated sample. The gate and the validator were written independently, by
   different mechanisms (anchored regex vs delimiter tokens). Any disagreement
   is a real defect in one of them and is reported, not smoothed over;
4. write `results/p2/eligibility_gate.{json,md}`.

**Split discipline.** Train + calibration only, from the frozen
`results/p1/split_assignment.csv`. The 170 test projects are dropped unread and
the count is reported.

⚠ The deferrable fraction below is a property of **the rule**, not of the
corpus's true deferability, which is unobserved (DL-020 §6).

Run:  python scripts/apply_eligibility.py        (env: PYTHONPATH=.)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from replay import validate_invariants as vi
from scheduler_core import data, eligibility, features

RESULTS = Path(__file__).resolve().parents[1].parent / "results" / "p2"
SPLIT_ASSIGNMENT = (Path(__file__).resolve().parents[1].parent
                    / "results" / "p1" / "split_assignment.csv")
RUN_DATE = "2026-09-17"
COMMAND = "python scripts/apply_eligibility.py"
CHUNK = 300_000

READ_COLUMNS: tuple[str, ...] = (
    "tr_build_id", "gh_project_name", "gh_is_pr", "git_branch",
    "gh_build_started_at", "tr_status",
)
ALLOWED_SPLITS: frozenset[str] = frozenset({"train", "calibration"})


def load_builds() -> tuple[pd.DataFrame, dict[str, int]]:
    """Train + calibration analytic builds with the gate's two inputs."""
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
    n_analytic = len(builds)
    split = builds["gh_project_name"].map(split_map)
    n_test = int((split == "test").sum())
    builds = builds.loc[split.isin(ALLOWED_SPLITS)].reset_index(drop=True)

    funnel = {
        "analytic_builds": n_analytic,
        "test_split_builds_dropped_unread": n_test,
        "builds_gated_train_plus_calibration": len(builds),
        "distinct_projects": int(builds["gh_project_name"].nunique()),
    }
    return builds, funnel


def gate_one_variant(builds: pd.DataFrame, variant: str) -> dict:
    """Classify every build under one variant and audit the result."""
    verdicts = eligibility.classify_frame(builds, variant=variant)
    summary = dict(eligibility.summarise(verdicts))

    # §4 eligibility-gate safety: feed the gate's own decisions to the
    # independent validator. `action` is what the gate would authorise.
    decisions = builds[["tr_build_id", "gh_project_name", "gh_is_pr", "git_branch"]].copy()
    decisions["action"] = ["defer" if e else "run_now" for e in verdicts["eligible"]]
    audit = vi.audit_frame(decisions, variant=variant, path=f"<gate output:{variant}>")

    return {
        "variant": variant,
        "summary": summary,
        "validator_audit": audit.as_dict(),
    }


def exhaustive_cross_check(builds: pd.DataFrame, variant: str) -> dict:
    """Compare gate and validator on every distinct input pair in the corpus."""
    pairs = builds[["gh_is_pr", "git_branch"]].drop_duplicates()
    report = vi.cross_check(
        list(pairs.itertuples(index=False, name=None)), variant=variant)
    report["distinct_branch_names"] = int(builds["git_branch"].nunique())
    return report


def render_markdown(rep: dict) -> str:
    L: list[str] = []
    L.append("# P2-T1 — Stage-1 eligibility gate, applied to the real corpus\n")
    L.append(f"*Run `{rep['command']}` on {rep['run_date']}; {rep['elapsed_s']:.1f}s. "
             f"Every number is from this run (R1).*\n")
    L.append("> **This measures the rule, not deferability.** DL-020 §6: the gate is an "
             "experimental approximation of spec §3.4's trigger classes from the two "
             "columns TravisTorrent actually carries. Two of the six §3.4 classes "
             "(manually-triggered, scheduled/nightly) have no marker in the data and are "
             "not approximated at all, so the deferrable set below consists entirely of "
             "class (f). The approximation's error rate is **unmeasurable in this "
             "corpus** — there is no ground-truth deferability label to score it "
             "against. Nothing here is evidence about which builds are genuinely safe "
             "to delay.\n")

    L.append("## Funnel\n")
    L.append("| Stage | Builds |")
    L.append("| :-- | --: |")
    for k, v in rep["funnel"].items():
        L.append(f"| {k.replace('_', ' ')} | {v:,} |")
    L.append("")

    for res in rep["variants"]:
        s, a = res["summary"], res["validator_audit"]
        L.append(f"## Variant `{res['variant']}`\n")
        L.append(f"- Builds gated: **{s['builds']:,}**")
        L.append(f"- Deferrable **by rule**: **{s['eligible']:,}** "
                 f"({s['eligible_fraction']:.4%})")
        L.append(f"- Non-deferrable: **{s['non_eligible']:,}**\n")
        L.append("| Rule fired | Builds | Share |")
        L.append("| :-- | --: | --: |")
        for rule, n in sorted(s["by_rule"].items(), key=lambda kv: -kv[1]):
            L.append(f"| `{rule}` | {n:,} | {n / s['builds']:.4%} |")
        L.append("")
        L.append(f"**§4 eligibility-gate safety** (independent validator on the gate's "
                 f"own output): {a['deferred']:,} deferred, **{a['violations']:,} "
                 f"violations** → {'PASS' if a['passed'] else 'FAIL'}. Per DL-020 §6 "
                 f"this proves gate/consumer consistency, not gate correctness.\n")

    L.append("## Independent cross-check (the point of a second implementation)\n")
    L.append("`scheduler_core/eligibility.py` matches anchored regexes; "
             "`replay/validate_invariants.py` splits names on `/`, `_`, `-` and compares "
             "tokens. Neither imports the other. Agreement is therefore evidence, not "
             "tautology.\n")
    L.append("| Variant | Distinct input pairs | Distinct branch names | Disagreements |")
    L.append("| :-- | --: | --: | --: |")
    for cc in rep["cross_checks"]:
        L.append(f"| `{cc['variant']}` | {cc['pairs_checked']:,} | "
                 f"{cc['distinct_branch_names']:,} | **{cc['disagreements']:,}** |")
    L.append("")
    for cc in rep["cross_checks"]:
        if cc["examples"]:
            L.append(f"### Disagreements — `{cc['variant']}`\n")
            L.append("```json")
            L.append(json.dumps(cc["examples"], indent=2, default=str))
            L.append("```\n")

    L.append("## The frozen pattern table\n")
    L.append("| # | Rule | Pattern | §3.4 class approximated | Profile evidence |")
    L.append("| --: | :-- | :-- | :-- | :-- |")
    for i, row in enumerate(rep["rule_table"], 1):
        L.append(f"| {i} | `{row['name']}` | `{row['pattern']}` | {row['spec_class']} | "
                 f"{row['evidence']} |")
    L.append("")
    return "\n".join(L)


def main() -> None:
    t0 = time.perf_counter()
    RESULTS.mkdir(parents=True, exist_ok=True)

    builds, funnel = load_builds()
    print(f"gating {len(builds):,} builds across {funnel['distinct_projects']:,} "
          f"projects (test dropped unread: "
          f"{funnel['test_split_builds_dropped_unread']:,})")

    variants, cross_checks = [], []
    for variant in eligibility.VARIANTS:
        res = gate_one_variant(builds, variant)
        variants.append(res)
        s = res["summary"]
        print(f"  {variant}: {s['eligible']:,} deferrable "
              f"({s['eligible_fraction']:.4%}), "
              f"{res['validator_audit']['violations']} validator violations")

        cc = exhaustive_cross_check(builds, variant)
        cc["variant"] = variant
        cross_checks.append(cc)
        print(f"  {variant}: cross-check {cc['pairs_checked']:,} distinct pairs, "
              f"{cc['disagreements']} disagreements")

    report = {
        "command": COMMAND,
        "run_date": RUN_DATE,
        "splits_read": sorted(ALLOWED_SPLITS),
        "funnel": funnel,
        "variants": variants,
        "cross_checks": cross_checks,
        "rule_table": eligibility.rule_table("protected_includes_integration"),
        "elapsed_s": time.perf_counter() - t0,
    }

    (RESULTS / "eligibility_gate.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    (RESULTS / "eligibility_gate.md").write_text(
        render_markdown(report), encoding="utf-8")
    print(f"wrote {RESULTS / 'eligibility_gate.json'}")
    print(f"wrote {RESULTS / 'eligibility_gate.md'}")
    print(f"done in {report['elapsed_s']:.1f}s")


if __name__ == "__main__":
    main()

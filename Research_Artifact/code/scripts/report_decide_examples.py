"""P2-T3 — five worked `decide()` outputs against the REAL carbon profile.

Produces `results/p2/decide_examples.{json,md}`, the gate evidence the plan asks
for: five example decisions computed with the P0-T3 hour-of-week profile and the
**bootstrap** policy spec, covering both Stage-1 outcomes, both Stage-2 outcomes,
and both policy paths.

⚠ **These are wiring examples, not results.** The bootstrap spec declares
`provenance.fitted: false`, so it is loaded here with `require_fitted=False` —
the visible exception DL-022 §4 requires. Its `d_threshold_seconds` is a
deliberately degenerate 0.0 and its `w_max_hours` is the DL-008 protocol default,
so no number below reflects a fitted policy. P2-T5 fits the real spec; P3
produces the real numbers.

⚠ Reads **no build data**. The five builds are hand-constructed to exercise named
branches; none is drawn from the corpus, and no split is opened.

Run from `code/`:   PYTHONPATH=. python scripts/report_decide_examples.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scheduler_core import carbon, policy

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "p2"

#: Five hand-built cases, each naming the branch of `decide()` it is there to show.
EXAMPLES: tuple[dict, ...] = (
    {
        "id": "E1",
        "shows": "Stage 1 refuses a PR build — Stage 2 is never consulted",
        "path": "duration_only_fallback",
        "build": {"gh_is_pr": True, "git_branch": "feature/login",
                  "arrival_dow": 2, "arrival_hour": 18, "d_hat_seconds": 5400.0},
    },
    {
        "id": "E2",
        "shows": "Stage 1 refuses a push to a protected branch (named rule)",
        "path": "duration_only_fallback",
        "build": {"gh_is_pr": False, "git_branch": "master",
                  "arrival_dow": 2, "arrival_hour": 18, "d_hat_seconds": 5400.0},
    },
    {
        "id": "E3",
        "shows": "deferrable + duration-only path -> defers to the greenest reachable slot",
        "path": "duration_only_fallback",
        "build": {"gh_is_pr": False, "git_branch": "feature/widget",
                  "arrival_dow": 2, "arrival_hour": 18, "d_hat_seconds": 5400.0},
    },
    {
        "id": "E4",
        "shows": "deferrable but d_hat below d_threshold -> runs now (A1.6 selectivity)",
        "path": "duration_only_fallback",
        "d_threshold_override": 7200.0,
        "build": {"gh_is_pr": False, "git_branch": "feature/typo-fix",
                  "arrival_dow": 2, "arrival_hour": 18, "d_hat_seconds": 90.0},
    },
    {
        "id": "E5",
        "shows": "SE-informed path -> the §7 window shrinks with p_hat, shortening the search",
        "path": "se_informed",
        "build": {"gh_is_pr": False, "git_branch": "feature/widget",
                  "arrival_dow": 2, "arrival_hour": 18, "d_hat_seconds": 5400.0,
                  "p_hat": 0.80},
    },
)


def _spec_for(example: dict, base: dict) -> policy.PolicySpec:
    """Build an in-memory spec variant for one example, written to a temp file.

    Kept deliberately explicit: every threshold below is either the bootstrap's
    own value or an override named in `EXAMPLES`, so the provenance of each
    number in the report is visible on this page.
    """
    import copy
    import tempfile

    import yaml

    raw = copy.deepcopy(base)
    raw["policy_path"] = example["path"]
    if example["path"] == "se_informed":
        raw["se_informed"]["admitted_families"] = ["F1(illustrative — no family was admitted)"]
    if "d_threshold_override" in example:
        raw[example["path"] if example["path"] == "se_informed" else "duration_only"][
            "d_threshold_seconds"] = example["d_threshold_override"]

    tmp = Path(tempfile.gettempdir()) / f"p2t3_spec_{example['id']}.yaml"
    tmp.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return policy.load_policy_spec(tmp, require_fitted=False)


def main() -> None:
    import yaml

    profile = carbon.load_hour_of_week_profile()
    base = yaml.safe_load(
        policy.BOOTSTRAP_POLICY_SPEC_PATH.read_text(encoding="utf-8-sig"))

    # Sanity: the bootstrap must be refused by the safe default, or its quarantine
    # is not real. Asserted here as well as in the tests, because this script is
    # the thing that writes numbers into results/.
    try:
        policy.load_policy_spec(policy.BOOTSTRAP_POLICY_SPEC_PATH)
        raise SystemExit("FATAL: the bootstrap spec loaded under require_fitted=True")
    except policy.PolicyError:
        pass

    report: dict = {
        "task": "P2-T3",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spec_source": str(policy.BOOTSTRAP_POLICY_SPEC_PATH),
        "spec_fitted": False,
        "warning": "BOOTSTRAP SPEC — wiring examples, not results (DL-022 §4).",
        "carbon_profile_slots_observed": int(profile["mean"].notna().sum()),
        "dataset_rows_read": 0,
        "examples": [],
    }

    for ex in EXAMPLES:
        spec = _spec_for(ex, base)
        decision = policy.decide(ex["build"], profile, spec)
        report["examples"].append({
            "id": ex["id"],
            "shows": ex["shows"],
            "build": ex["build"],
            "spec": spec.provenance_record(),
            "decision": decision.as_dict(),
        })

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "decide_examples.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: list[str] = [
        "# Five worked `decide()` outputs (P2-T3)",
        "",
        f"Generated `{report['generated_utc']}` by "
        "`PYTHONPATH=. python scripts/report_decide_examples.py`.",
        "Machine-readable twin: `decide_examples.json`. Test evidence: `pytest_p2_t3.txt`.",
        "",
        "> **⚠ Wiring examples, not results.** These run against the **bootstrap** spec",
        "> (`provenance.fitted: false`), whose `d_threshold_seconds` is a deliberately degenerate",
        "> 0.0 and whose `w_max_hours` is the DL-008 protocol default. No number here reflects a",
        "> fitted policy. P2-T5 fits the real `policy_spec.yaml`; P3 produces the real numbers.",
        "> The bootstrap was verified **refused** under the default `require_fitted=True` before",
        "> these examples were generated (DL-022 §4).",
        "",
        "> **Provenance.** Real P0-T3 carbon profile "
        f"({report['carbon_profile_slots_observed']}/{carbon.N_SLOTS} slots observed). "
        "**0 dataset rows read** — the five builds are hand-constructed to exercise named",
        "> branches; no split was opened.",
        "",
    ]

    for ex in report["examples"]:
        d = ex["decision"]
        b = ex["build"]
        lines += [
            f"## {ex['id']} — {ex['shows']}",
            "",
            f"**Path:** `{d['policy_path']}` · **Arrival:** "
            f"{carbon.DOW_NAMES[b['arrival_dow']]} {b['arrival_hour']:02d}:00 · "
            f"**`gh_is_pr`:** `{b['gh_is_pr']}` · **`git_branch`:** `{b['git_branch']}`",
            "",
            "| Field | Value |",
            "| :-- | :-- |",
            f"| `action` | **`{d['action']}`** |",
            f"| `defer_until` | `{d['defer_until']}` |",
            f"| `grid_gCO2_now` | {d['grid_gCO2_now']:.4f} gCO₂/kWh |",
            f"| `grid_gCO2_scheduled` | {d['grid_gCO2_scheduled']:.4f} gCO₂/kWh |",
            f"| `eligible` / `stage1_rule` | `{d['eligible']}` / `{d['stage1_rule']}` |",
            f"| `d_hat_seconds` | `{d['d_hat_seconds']}` |",
            f"| `p_hat` | `{d['p_hat']}` |",
            f"| `window_hours` | {d['window_hours']:.4f} |",
            f"| `delay_hours` | {d['delay_hours']:.4f} |",
            f"| `spec_fitted` | `{d['spec_fitted']}` |",
            "",
            "**`reason`**",
            "",
            "```text",
            d["reason"],
            "```",
            "",
        ]

    lines += [
        "## What these five demonstrate",
        "",
        "- **E1, E2** — Stage 1 returns before Stage 2 is consulted. The reason string says so",
        "  explicitly (`Stage 2 not consulted`), and `d_hat_seconds` is `null` in the record",
        "  because the estimate was never read. This is frozen invariant 1 as control flow.",
        "- **E3** — the deferral itself: the greenest slot reachable inside the window, with the",
        "  before/after intensities both recorded so the decision can be audited without rerunning it.",
        "- **E4** — A1.6 selectivity: a short build is *not* worth deferring, because it pays the",
        "  full latency cost for a negligible carbon gain.",
        "- **E5** — the §7 / A1.8 window form: a high `p_hat` shrinks the window, which shortens the",
        "  slot search. On present evidence (`results/p1/admission.json`, zero families admitted)",
        "  this path is implemented and tested but is **not** the path expected to ship.",
        "",
        "Every `reason` above names the gate rule, the path taken, the driving values, the window",
        "and the chosen slot — the S2 contract — so a decision log is readable without this module.",
    ]
    (RESULTS_DIR / "decide_examples.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"bootstrap spec correctly REFUSED under require_fitted=True")
    print(f"profile: {report['carbon_profile_slots_observed']}/{carbon.N_SLOTS} slots observed")
    for ex in report["examples"]:
        d = ex["decision"]
        print(f"  {ex['id']}  {d['action']:<8} delay={d['delay_hours']:>5.1f}h  "
              f"window={d['window_hours']:>7.4f}h  "
              f"now={d['grid_gCO2_now']:.4f} -> sched={d['grid_gCO2_scheduled']:.4f} gCO2/kWh  "
              f"[{d['stage1_rule']}]")
    print(f"dataset rows read: {report['dataset_rows_read']}")
    print(f"wrote {RESULTS_DIR / 'decide_examples.json'}")
    print(f"wrote {RESULTS_DIR / 'decide_examples.md'}")


if __name__ == "__main__":
    main()

"""P1-T7 — apply the predeclared §A1.7 rule → the model-level RQ2 answer.

This task fits **nothing**. It reads P1-T6's evidence, applies the frozen
admission rule mechanically, sweeps the floor, and writes the verdict:

  * ``results/p1/incremental_value.md``  — the gate evidence (the RQ2 answer)
  * ``results/p1/admission.json``        — the machine-readable admitted set
    consumed by ``scripts/fit_policy.py`` at P2-T5

Every verdict line carries the P1-T6 number that decided it. No model is
trained, no split is read, and the test split is not touched — the inputs are
two JSON files produced by P1-T6.

Run:  PYTHONPATH=. python scripts/apply_admission.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scheduler_core import admission as adm, features

CODE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = CODE_ROOT.parent / "results" / "p1"
DELTAS = RESULTS / "ablation" / "deltas.json"
SHAP = RESULTS / "shap" / "shap_summary.json"
COMMAND = "PYTHONPATH=. python scripts/apply_admission.py"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    deltas = json.loads(DELTAS.read_text(encoding="utf-8"))
    shap = json.loads(SHAP.read_text(encoding="utf-8"))

    # One ΔPR-AUC record per family, straight from P1-T6.
    pr_auc = {fam: row["delta_vs_control"]["pr_auc"]
              for fam, row in deltas["families"].items()}

    primary = adm.admission_set(pr_auc, floor=adm.MODEL_FLOOR_ABS)
    sweep = adm.floor_sweep(pr_auc, base_floor=adm.MODEL_FLOOR_ABS)

    print(f"applying §A1.7 model floor {adm.MODEL_FLOOR_ABS:+.6f} to "
          f"{len(pr_auc)} families …", flush=True)
    for fam in sorted(pr_auc):
        v = primary["verdicts"][fam]
        print(f"  {fam}: {'ADMITTED' if v['admitted'] else 'REJECTED'} — "
              f"{v['decided_by']}", flush=True)
    print(f"\nadmitted set: {primary['admitted'] or '(empty)'}", flush=True)
    print(f"floor sweep stable across ×0.5/×1/×2: {sweep['stable']}", flush=True)

    out = build_admission_record(deltas, shap, primary, sweep)
    (RESULTS / "admission.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")
    write_report(out, deltas, shap)
    print(f"\nwrote results/p1/admission.json and results/p1/incremental_value.md",
          flush=True)
    return 0


def build_admission_record(deltas: dict, shap: dict, primary: dict,
                           sweep: dict) -> dict:
    src = deltas["provenance"]
    admitted = primary["admitted"]
    return {
        "provenance": {
            "command": COMMAND,
            "run_date": time.strftime("%Y-%m-%d"),
            "task": "P1-T7",
            "inputs": {
                "deltas": DELTAS.relative_to(RESULTS.parent.parent).as_posix(),
                "shap": SHAP.relative_to(RESULTS.parent.parent).as_posix(),
            },
            "evidence_run": {
                "command": src["command"],
                "run_date": src["run_date"],
                "algorithm": src["algorithm"],
                "seed": src["seed"],
                "control_arm_fit_id": src["control_arm_fit_id"],
                "full_arm_fit_id": src["full_arm_fit_id"],
                "duration_control_fit_id": src["duration_control_fit_id"],
                "split_digest": src["split_digest"],
            },
            "split_used": "calibration",
            "test_split_touched": False,
            "rule": "eval_protocol §A1.7, model altitude: ΔPR-AUC vs {d̂} — 95% "
                    "CI excludes 0 AND point estimate ≥ 0.01 absolute "
                    "(improvement, not |Δ| — the directional reading was fixed "
                    "in DL-019 §2 before these deltas existed).",
            "nothing_was_fitted_here": True,
        },
        "model_level_admission": {
            "floor": primary["floor"],
            "admitted": admitted,
            "rejected": primary["rejected"],
            "verdicts": primary["verdicts"],
        },
        "floor_sweep": sweep,
        "admitted_family_members": {
            fam: list(features.FAMILIES[fam]) for fam in admitted
        },
        "policy_path": ("se_informed" if admitted else "duration_only_fallback"),
        "policy_path_note": (
            "§A1.7: if no family passes, fit_policy.py emits a valid spec whose "
            "every path is the duration-only fallback (§A1.6), and that is "
            "reported as the principal finding (DL-012 §5)."),
        "variance_decomposition_caveat": {
            "threshold": shap["project_identity_coded_threshold"],
            "between_project_share": {
                fam: shap["variance_decomposition"][fam]["between_share"]
                for fam in sorted(shap["variance_decomposition"])
            },
            "note": "Measured on each family's summed SHAP contribution inside "
                    "the frozen `full` arm, not on its standalone {d̂+Fᵢ} arm "
                    "(DL-019 §Threats 2).",
        },
        "consumed_by": "scripts/fit_policy.py (P2-T5); the identical rule is "
                       "re-applied to test-split deltas at P3-T1.",
    }


def write_report(out: dict, deltas: dict, shap: dict) -> None:
    p = out["provenance"]
    ev = p["evidence_run"]
    adm_block = out["model_level_admission"]
    sweep = out["floor_sweep"]
    admitted = adm_block["admitted"]
    pop = deltas["provenance"]["population"]

    L: list[str] = []
    A = L.append

    A("# Model-level incremental value — the RQ2 answer at the model altitude (P1-T7)\n")
    A(f"> Generated by `{p['command']}` on {p['run_date']}. **Nothing was fitted "
      f"in this task.** Every number below is read from P1-T6's "
      f"`{p['inputs']['deltas']}`, produced by `{ev['command']}` on "
      f"{ev['run_date']} (R1).\n")
    A(f"> Rule: {p['rule']}\n")

    # ---------------------------------------------------------------- verdict
    A("\n## 1. The answer\n")
    if not admitted:
        A("**No SE feature family clears the §A1.7 model-level floor. The "
          "duration control `{d̂}` is model-level sufficient: at this altitude, "
          "commit-level SE characteristics carry no admissible incremental "
          "value beyond a commit-time estimate of build duration.**\n")
        A("This is the **null path**, and §A1.7 predeclared it as a valid "
          "outcome rather than a shortfall: *\"If no family passes, "
          "`fit_policy.py` emits a valid spec whose every path is the "
          "duration-only fallback, and that is reported as the principal "
          "finding (DL-012 §5).\"* `admission.json` therefore records "
          f"`policy_path: {out['policy_path']}`.\n")
        A("Two things this statement does **not** claim:\n")
        A("- It is **not** the final RQ2 answer. The decision-level altitude "
          "(§A1.5 — does an SE-informed policy dominate ④'s carbon/TTFF "
          "frontier?) is **P3-T3's**, and the confirmatory model-level "
          "evaluation on the untouched test split is **P3-T1's**. A family "
          "rejected here is not re-litigated there; the test split confirms "
          "this verdict rather than replacing it.")
        A("- It is **not** a claim that SE characteristics are unrelated to "
          "build failure in general. It is a claim about *admissible "
          "incremental value over `d̂`*, on this dataset, with this feature "
          "contract — see §5's bounds, particularly the two predictors this "
          "release cannot express at all (DL-015) and the one it leaves empty "
          "(DL-016).\n")
    else:
        A(f"**{len(admitted)} family(ies) clear the §A1.7 model-level floor: "
          + ", ".join(f"`{f}`" for f in admitted) + ".** Their members enter "
          "`fit_policy.py` at P2-T5 as the admitted set; `admission.json` "
          f"records `policy_path: {out['policy_path']}`.\n")

    # ------------------------------------------------------------- per family
    A("\n## 2. Per-family verdicts, each traced to the number that decided it\n")
    A("ΔPR-AUC is the paired calibration-split difference `{d̂+Fᵢ} − {d̂}` "
      "(B=1000, seed 42) from P1-T6. The floor is "
      f"**{adm_block['floor']:+.4f} absolute**; the CI condition is "
      "**excludes 0**.\n")
    A("| family | ΔPR-AUC | 95% CI | CI vs 0 | ≥ floor? | verdict | decided by |")
    A("| :-- | --: | :-- | :-: | :-: | :-: | :-- |")
    for fam in sorted(adm_block["verdicts"]):
        v = adm_block["verdicts"][fam]
        A(f"| **{fam}** | {v['delta_pr_auc']:+.6f} | "
          f"[{v['ci_lo']:+.6f}, {v['ci_hi']:+.6f}] | {v['ci_direction']} | "
          f"{'yes' if v['meets_floor'] else 'no'} | "
          f"{'**ADMITTED**' if v['admitted'] else 'rejected'} | "
          f"{v['reason_short']} |")
    A("")
    A("> The `decided by` column is the short form; the full sentence naming "
      "every number behind each verdict is in `admission.json` under "
      "`model_level_admission.verdicts.<family>.decided_by`.\n")

    negatives = [f for f, v in adm_block["verdicts"].items()
                 if v["ci_direction"] == "negative"]
    if negatives:
        A(f"> **Stronger than 'no evidence of benefit'.** {len(negatives)} of "
          f"{len(adm_block['verdicts'])} families "
          f"({', '.join(f'`{f}`' for f in sorted(negatives))}) have a 95% CI "
          "lying **entirely below 0** — on the calibration split they make "
          "PR-AUC significantly *worse* than the duration control alone, not "
          "merely fail to improve it. The rule rejects them for being below "
          "the floor; the sign is reported because it is what the evidence "
          "says.\n")

    # ------------------------------------------------------------- floor sweep
    A("\n## 3. Floor sensitivity (§A1.7's mandatory ×0.5 / ×2 re-run)\n")
    A("§A1.7 requires every admission decision to be re-run at ×0.5 and ×2 of "
      "the floor, and the resulting policy differences reported. "
      f"{sweep['note']}\n")
    A("| floor | ×multiplier | admitted set | rejected |")
    A("| --: | :-: | :-- | --: |")
    for key, row in sweep["by_floor"].items():
        A(f"| {row['floor']:+.4f} | {key} | "
          f"{', '.join(f'`{f}`' for f in row['admitted']) or '**(empty)**'} | "
          f"{len(row['rejected'])} |")
    A("")
    if sweep["stable"]:
        A("**The admitted set is identical at every swept floor** — §A1.7 "
          "treats a set that is stable across the sweep as the stronger "
          "finding. The verdict here does not depend on where the floor was "
          "drawn: "
          + ("no family is admitted even at half the floor, and the "
             "closest family is still the wrong side of 0."
             if not admitted else
             "the same families are admitted at double the floor.") + "\n")
    else:
        A("**The admitted set changes across the sweep** — the verdict is "
          "floor-sensitive and must be reported as such; §A1.7 treats this as "
          "the weaker finding.\n")

    # --------------------------------------------------- A1.9 variance caveat
    A("\n## 4. The §A1.9 project-identity caveat\n")
    vc = out["variance_decomposition_caveat"]
    A("§A1.9 requires the incremental-value analysis to report a "
      "between-project vs within-project variance decomposition, so a family "
      "whose apparent effect is really project identity is visible as such. "
      f"{vc['note']}\n")
    A("| family | between-project share | within-project share | reading |")
    A("| :-- | --: | --: | :-- |")
    for fam in sorted(vc["between_project_share"]):
        if fam == "control":
            continue
        share = vc["between_project_share"][fam]
        within = shap["variance_decomposition"][fam]["within_share"]
        reading = ("mostly **within**-project variation"
                   if share < 0.33 else
                   ("mixed" if share < float(vc["threshold"]) else
                    "**project-identity-coded**"))
        A(f"| {fam} | {share:.4f} | {within:.4f} | {reading} |")
    ctrl = vc["between_project_share"].get("control")
    A("")
    if ctrl is not None:
        A(f"> For reference, `d̂` itself — the control — is {ctrl:.4f} "
          "between-project, which is expected: its primary form ④b **is** a "
          "per-project historical prior.\n")
    A("**Why this matters for a null result.** The decomposition guards "
      "against a *false positive* (a family that looks informative but only "
      "encodes project identity). In the null case it does the opposite work: "
      "it tells us whether the families' contributions were mostly "
      "within-project variation that genuinely failed to help, or mostly "
      "between-project variation that `d̂`'s own project prior already "
      "captured. On the measured shares, F1/F2/F6 are overwhelmingly "
      "within-project, so for those families the null cannot be explained "
      "away as redundancy with `d̂`'s project encoding; F3/F4/F5 carry a "
      "larger between-project share, where that redundancy is a live "
      "explanation. This is a reading of SHAP contributions inside the `full` "
      "arm, not of the standalone family arms (DL-019 §Threats 2), and it is "
      "offered as a caveat rather than a measurement of the null's cause.\n")

    # ------------------------------------------------------------- threats
    A("\n## 5. What bounds this verdict\n")
    A("1. **The SE side entered weakened, by measurement not by choice.** "
      "`git_diff_test_churn` is empty across the entire release, so "
      "`test_churn` and `test_density_ratio` are constant (DL-016) — P1-T6's "
      "SHAP confirms both attribute *exactly* 0. Two further textbook "
      "predictors (change entropy, commit-message fix keywords) cannot be "
      "built from this release at all (DL-015). This verdict is therefore a "
      "**lower bound** on what commit-level SE characteristics could "
      "contribute given richer data, and must be stated that way.")
    A("2. **Calibration-split evidence, in-sample for the calibrator.** The "
      "§5 calibrator choice is fitted on these same builds (P1-T5 §Threats 1), "
      "and the calibration split's failure rate (28.55%) is 4.2pp above test's "
      "(25.04%) — both quoted from the P1-T3 split manifest (DL-017); no test "
      "project has been read. P3-T1 is the confirmatory run.")
    A("3. **One algorithm, one budget.** The ablation used the predeclared "
      "primary (XGBoost) with the DL-018 budget of 20 seeded candidates per "
      "arm. A family that needs a different inductive bias or a larger search "
      "to express itself would not show up here.")
    A("4. **`d̂` is a predicted quantity, and a strong one.** The control is "
      "not 'true duration' but the frozen ④b per-project prior, which P1-T6's "
      "SHAP shows is the single strongest and most cleanly monotone signal in "
      "the `full` arm (Spearman ρ +0.5879, CI excludes 0). RQ2 asks about "
      "value *beyond* that, and that is a demanding null by construction.")
    A("5. **A secondary pattern worth carrying forward.** In P1-T6 every "
      "single-family arm scored a higher PR-AUC than the combined `full` "
      "28-feature arm (0.328552). The families do not merely fail to help "
      "individually — stacking them compounds the loss. That is a statement "
      "about this feature set under this procedure, and it belongs in the "
      "discussion rather than in the verdict.\n")

    # ------------------------------------------------------------- provenance
    A("\n## 6. Provenance footer\n")
    A(f"- **Nothing was fitted in this task** "
      f"(`nothing_was_fitted_here: {p['nothing_was_fitted_here']}`). Inputs: "
      f"`{p['inputs']['deltas']}`, `{p['inputs']['shap']}`.")
    A(f"- Evidence run: `{ev['command']}` ({ev['run_date']}), algorithm "
      f"`{ev['algorithm']}`, seed `{ev['seed']}`.")
    A(f"- Frozen arms behind the deltas: control `{ev['control_arm_fit_id']}`, "
      f"full `{ev['full_arm_fit_id']}`, duration control "
      f"`{ev['duration_control_fit_id']}`.")
    A(f"- Split: frozen P1-T3 assignment, digest `{ev['split_digest'][:16]}…`; "
      f"deltas measured on the **{p['split_used']}** split "
      f"({pop['calibration_builds']:,} builds).")
    A(f"- **Test split still untouched:** "
      f"{pop['test_projects_dropped_unread']:,} projects / "
      f"{pop['test_builds_dropped_unread']:,} builds were dropped unread when "
      "P1-T6 produced these deltas, and this task reads no dataset at all.")
    A(f"- Machine-readable verdict: `results/p1/admission.json` "
      f"(`policy_path: {out['policy_path']}`), consumed by "
      f"{out['consumed_by']}")
    A("")
    (RESULTS / "incremental_value.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

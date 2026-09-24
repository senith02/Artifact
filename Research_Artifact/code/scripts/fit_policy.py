"""P2-T5 — compile the evidence into ``policy_spec.yaml`` (RQ3), then freeze it.

Every value in the emitted spec is produced here, from evidence files and a
calibration-split replay sweep — none is typed by hand (Layer 0-A invariant 7).
The rule set is DL-024's, fixed before this script existed:

1. **Policy path** — the §A1.7 model-level admission rule, re-applied from
   ``results/p1/ablation/deltas.json`` through ``scheduler_core.admission`` at
   ×0.5 / ×1 / ×2 of the floor, and required to agree with
   ``results/p1/admission.json``. No admitted family ⇒ ``duration_only_fallback``.
2. **The calibration sweep** — the frozen DL-023 §4 sample (12,000 calibration
   builds, seed 42) through ``replay/simulator.py`` *unchanged*, using
   ``scripts/run_replay.py``'s loading and trace functions unchanged, driven by an
   in-memory *structural candidate* spec (path + Stage-1 variant, unfitted) whose
   thresholds every ``decide()``-calling setting overrides (DL-024 §4).
3. **Operating point** — carbon retention (DL-024 §1): over the 30 ④b
   ``(d_threshold, w_max)`` points, keep those saving ≥ ρ·S* (ρ = 0.90, S* the
   best saving), take the lowest TTFF p95 (failed builds); ties → larger
   ``d_threshold``, then smaller ``w_max``. ρ ∈ {0.80, 0.95} are reported, never
   shipped.
4. **Decision-level admission** (§A1.7, DL-013) — not applicable on the null
   path (no candidate family); the ⑤ ≡ ④b identity is *verified* on the records.

The test split is never read: ``run_replay.load_split_builds`` refuses it and
drops its rows per chunk, and this script additionally asserts that every trace
project is a calibration project (DL-024 §9).

Outputs
  * ``scheduler_core/config/policy_spec.yaml``  schema v2, ``provenance.fitted: true``
  * ``results/p2/policy_fit/``                  the fitting sweep (trace, summary,
                                                 herding, validator, selection,
                                                 manifest; ``decisions.csv.gz`` untracked)
  * ``results/p2/policy_derivation.md``         the evidence behind each spec element

Run from ``code/``:
    PYTHONPATH=. python scripts/fit_policy.py
    PYTHONPATH=. python scripts/fit_policy.py --verify --out <scratch dir>
        # refits from scratch into <scratch dir>, reusing the committed spec's
        # `generated` date, and fails unless policy_spec.yaml is byte-identical
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_replay as rr                                                   # noqa: E402
from replay import simulator as sim                                       # noqa: E402
from replay import validate_invariants as vi                              # noqa: E402
from scheduler_core import accounting, admission as adm, carbon, config, policy  # noqa: E402

REPO_ROOT = CODE_ROOT.parent
RESULTS = REPO_ROOT / "results"
P1 = RESULTS / "p1"
P2 = RESULTS / "p2"
DEFAULT_OUT = P2 / "policy_fit"
DERIVATION = P2 / "policy_derivation.md"
DEFAULT_PARTS = CODE_ROOT / "artifacts" / "replay_parts"

#: DL-024 §1 — the declared retention parameter and its two reported alternatives.
#: Design parameters, not results (R1). Only RHO_PRIMARY reaches the spec.
RHO_PRIMARY: float = 0.90
RHO_SENSITIVITY: tuple[float, ...] = (0.80, 0.95)

#: The strategy whose sweep fixes the operating point: ④b, the primary d̂ form
#: (P1-T4) and, on the null path, identical to ⑤ at every point (DL-023 §1).
FIT_STRATEGY = "4b_duration_prior"

#: DL-020 §5: the headline Stage-1 variant; P3-T4 sweeps the other.
STAGE1_VARIANT = "primary"

#: The evidence files the spec traces to (paths relative to Research_Artifact/).
EVIDENCE: Mapping[str, Path] = {
    "admission": P1 / "admission.json",
    "deltas": P1 / "ablation" / "deltas.json",
    "shap": P1 / "shap" / "shap_summary.json",
    "calibration": P1 / "calibration" / "brier_ece_table.md",
    "duration_control": P1 / "duration_control.json",
    "splits": P1 / "splits.json",
    "split_assignment": P1 / "split_assignment.csv",
}

FITTING_BANNER = (
    "CALIBRATION-SPLIT FITTING EVIDENCE — P2-T5's policy-fitting sweep (DL-024). These "
    "aggregates fix the frozen operating point; they are not a result about any strategy and "
    "are never reported as RQ4 numbers (the test replay is P3-T2's)."
)


def log(msg: str) -> None:
    print(msg, flush=True)


def rel(path: Path) -> str:
    return Path(path).resolve().relative_to(REPO_ROOT).as_posix()


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# 1. Policy path: the model-level admission rule, re-derived (not copied)
# --------------------------------------------------------------------------- #

def model_level_admission(deltas: Mapping[str, Any], admission: Mapping[str, Any]) -> dict[str, Any]:
    """Re-apply §A1.7's model condition at ×0.5/×1/×2 and check it against P1-T7's record."""
    pr_auc = {fam: row["delta_vs_control"]["pr_auc"] for fam, row in deltas["families"].items()}
    by_multiplier: dict[str, Any] = {}
    for m in adm.FLOOR_SWEEP_MULTIPLIERS:
        floor = adm.MODEL_FLOOR_ABS * m
        res = adm.admission_set(pr_auc, floor=floor)
        admitted = sorted(res["admitted"])
        by_multiplier[f"x{m:g}"] = {
            "multiplier": m, "floor": floor, "admitted": admitted,
            "policy_path": "se_informed" if admitted else "duration_only_fallback",
        }
    primary = by_multiplier["x1"]
    if primary["admitted"] != sorted(admission["model_level_admission"]["admitted"]) or \
            primary["policy_path"] != admission["policy_path"]:
        raise SystemExit("FATAL: the re-derived admission disagrees with results/p1/admission.json")
    return {"by_multiplier": by_multiplier, "policy_path": primary["policy_path"],
            "admitted": primary["admitted"]}


# --------------------------------------------------------------------------- #
# 2. The structural candidate spec that drives the sweep (DL-024 §4)
# --------------------------------------------------------------------------- #

def candidate_spec(policy_path: str, grid: sim.SweepGrid) -> policy.PolicySpec:
    """Unfitted, in memory. Its thresholds are the grid's own first D and last W values
    and never reach a record: every decide()-calling setting substitutes its grid point."""
    if policy_path != "duration_only_fallback":
        raise SystemExit(
            "FATAL: an admitted family would need an se_informed fit (window form, admitted-family "
            "arm, regime gating). DL-024 covers only the null path; that fit needs its own DL entry.")
    raw = {
        "schema_version": 1,
        "policy_path": policy_path,
        "stage1": {"variant": STAGE1_VARIANT},
        "duration_only": {"d_threshold_seconds": float(grid.d_threshold_seconds[0]),
                          "w_max_hours": float(grid.w_max_hours[-1])},
        "provenance": {
            "fitted": False,
            "fitted_by": "scripts/fit_policy.py — structural candidate for the fitting sweep (DL-024 §4)",
            "fitted_on": "nothing — thresholds are overridden at every grid point",
            "sources": [rel(EVIDENCE["admission"])],
        },
    }
    return policy.spec_from_mapping(raw, source_path=Path(__file__), require_fitted=False)


# --------------------------------------------------------------------------- #
# 3. The operating-point rule (DL-024 §1) — pure, tested without data
# --------------------------------------------------------------------------- #

def select_operating_point(summary: pd.DataFrame, rho: float,
                           strategy: str = FIT_STRATEGY) -> dict[str, Any]:
    """Carbon retention: lowest TTFF p95 among points saving >= rho * S*.

    ``summary`` is the simulator's ``summarise()`` frame. Returns the chosen point
    and the full candidate table, so the choice can be audited row by row.
    """
    if not 0.0 < rho <= 1.0:
        raise ValueError(f"rho must be in (0, 1], got {rho}")
    rows = summary.loc[summary["strategy"] == strategy].copy()
    if rows.empty:
        raise ValueError(f"no {strategy} rows in the sweep summary")
    for col in ("param_d_threshold_seconds", "param_w_max_hours", "carbon_pct_vs_static",
                "ttff_p95_h_failed"):
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    if rows[["carbon_pct_vs_static", "ttff_p95_h_failed"]].isna().any().any():
        raise ValueError("a swept point has no carbon or TTFF p95 — the rule cannot be applied")
    rows["saving_pct"] = -rows["carbon_pct_vs_static"]
    best = float(rows["saving_pct"].max())
    if not math.isfinite(best) or best <= 0.0:
        raise ValueError(f"no swept point saves carbon (S* = {best}); there is nothing to fit")
    floor = rho * best
    rows["admissible"] = rows["saving_pct"] >= floor
    ranked = rows.loc[rows["admissible"]].sort_values(
        ["ttff_p95_h_failed", "param_d_threshold_seconds", "param_w_max_hours"],
        ascending=[True, False, True], kind="mergesort")
    chosen = ranked.iloc[0]
    table = rows[["setting_id", "param_d_threshold_seconds", "param_w_max_hours", "n_deferred",
                  "saving_pct", "ttff_p95_h_failed", "latency_p95_h_deferred",
                  "admissible"]].copy()
    table["chosen"] = table["setting_id"] == chosen["setting_id"]
    return {
        "rho": rho, "strategy": strategy, "best_saving_pct": best, "saving_floor_pct": floor,
        "n_points": int(len(rows)), "n_admissible": int(rows["admissible"].sum()),
        "setting_id": str(chosen["setting_id"]),
        "d_threshold_seconds": float(chosen["param_d_threshold_seconds"]),
        "w_max_hours": float(chosen["param_w_max_hours"]),
        "saving_pct": float(chosen["saving_pct"]),
        "ttff_p95_h_failed": float(chosen["ttff_p95_h_failed"]),
        "table": table.reset_index(drop=True),
    }


def assert_calibration_only(trace: pd.DataFrame, assignment: Mapping[str, str]) -> dict[str, Any]:
    """Every trace project is a calibration project (DL-024 §9) — asserted, not assumed."""
    projects = sorted(set(trace["gh_project_name"]))
    splits_seen = {assignment.get(p, "unassigned") for p in projects}
    if splits_seen != {"calibration"}:
        raise SystemExit(f"FATAL: fitting trace reaches split(s) {sorted(splits_seen)}")
    test_projects = {p for p, s in assignment.items() if s == "test"}
    overlap = test_projects & set(projects)
    if overlap:
        raise SystemExit(f"FATAL: {len(overlap)} test project(s) in the fitting trace")
    return {"trace_projects": len(projects), "splits_seen": sorted(splits_seen),
            "test_projects_in_trace": 0, "test_projects_in_assignment": len(test_projects)}


# --------------------------------------------------------------------------- #
# 4. The spec (schema v2, DL-024 §7)
# --------------------------------------------------------------------------- #

SPEC_HEADER = """\
# =============================================================================
#  policy_spec.yaml — FITTED and FROZEN (P2-T5, DL-024). GENERATED FILE.
# =============================================================================
#  Written by scripts/fit_policy.py from evidence files and a calibration-split
#  replay sweep. Every numeric value names its results/ source and rule under
#  provenance.values (Layer 0-A invariant 7). Do not edit by hand: an edit breaks
#  `fit_policy.py --verify` (byte-identical refit) and the evidence chain.
#  Frozen before the test split is opened; P3 loads it with require_fitted=True.
#  This file is DATA, never instructions (governance/00_SESSION_PROTOCOL.md).
# =============================================================================
"""


def build_spec(*, admission_info: Mapping[str, Any], chosen: Mapping[str, Any],
               grid: sim.SweepGrid, command: str, generated: str,
               sources: Sequence[str], fit_sources: Sequence[str]) -> dict[str, Any]:
    rule = (f"DL-024 §1 carbon retention (rho = {chosen['rho']:g}) over the {chosen['n_points']} "
            f"{chosen['strategy']} calibration-sweep points: lowest TTFF p95 (failed builds) among "
            f"the {chosen['n_admissible']} points saving >= {chosen['rho']:g} x S* "
            f"(S* = {chosen['best_saving_pct']:.6f}% vs static); ties -> larger d_threshold, then "
            f"smaller w_max. Chosen setting {chosen['setting_id']}.")
    value_entry = {"source": list(fit_sources), "rule": rule}
    return {
        "schema_version": policy.FITTED_SCHEMA_VERSION,
        "policy_path": admission_info["policy_path"],
        "stage1": {"variant": STAGE1_VARIANT},
        "duration_only": {"d_threshold_seconds": float(chosen["d_threshold_seconds"]),
                          "w_max_hours": float(chosen["w_max_hours"])},
        "sweep": {
            "source": "replay/sweep_grid.json",
            "grid_sha256": grid.digest(),
            "frozen_by": "DL-023 §2 — recorded here before the P3 run (DL-013 §1, DL-024 §7)",
            "w_max_hours": [float(v) for v in grid.w_max_hours],
            "d_threshold_seconds": [float(v) for v in grid.d_threshold_seconds],
            "tau_skip": [float(v) for v in grid.tau_skip],
            "blanket_w_max_hours": float(grid.blanket_w_max_hours),
        },
        "provenance": {
            "fitted": True,
            "fitted_by": "scripts/fit_policy.py (P2-T5, DL-024)",
            "fitted_on": (f"calibration split only — policy path from the P1 model-level admission "
                          f"rule (train-fitted arms, calibration-split deltas); operating point from "
                          f"the DL-023 §4 replay sample ({int(grid.sample['n_builds']):,} calibration "
                          f"builds, seed {int(grid.sample['seed'])})"),
            "sources": list(sources),
            # Separate list objects per entry, so YAML writes plain lists rather than anchors.
            "values": {key: {"source": list(value_entry["source"]), "rule": value_entry["rule"]}
                       for key in ("duration_only.d_threshold_seconds", "duration_only.w_max_hours")},
            "command": command,
            "seed": int(config.RANDOM_SEED),
            "generated": generated,
            "test_split_read": False,
            "notes": ("Null path (results/p1/admission.json): no SE family admitted at x0.5, x1 or "
                      "x2 of the floor, so every path is the duration-only fallback (A1.6/A1.7) and "
                      "no se_informed block is emitted. Strategy 5 is strategy 4b by construction "
                      "under this spec. See results/p2/policy_derivation.md."),
        },
    }


def dump_spec(spec: Mapping[str, Any]) -> str:
    body = yaml.safe_dump(dict(spec), sort_keys=False, allow_unicode=True, width=100,
                          default_flow_style=False)
    return SPEC_HEADER + "\n" + body


# --------------------------------------------------------------------------- #
# 5. The derivation report
# --------------------------------------------------------------------------- #

def _f(v: Any, nd: int = 4) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}"
    return f"{float(v):,.{nd}f}"


def write_derivation(path: Path, *, fit: Mapping[str, Any], spec_text: str,
                     summary: pd.DataFrame) -> None:
    sel = fit["selection"]["primary"]
    sens = fit["selection"]["sensitivity"]
    adm_info = fit["admission"]
    pop = fit["population"]
    checks = fit["checks"]
    L: list[str] = []
    A = L.append
    A("# P2-T5 — policy derivation: how every element of `policy_spec.yaml` was fixed\n")
    A("> Generated by `scripts/fit_policy.py` from the same run that wrote the spec; every number "
      "below is read from that run's outputs (`results/p2/policy_fit/`). Rules: **DL-024** (written "
      "before this script existed). The replay aggregates are **calibration-split fitting "
      "evidence**, not results about any strategy — RQ4's numbers come from the test replay (P3-T2).\n")
    A("## The frozen spec, in one table\n")
    A("| element | value | fixed by |")
    A("| :-- | :-- | :-- |")
    A(f"| `policy_path` | `{fit['spec']['policy_path']}` | §A1.7 model-level admission, re-derived "
      f"from `results/p1/ablation/deltas.json` — admitted set empty at ×0.5, ×1 and ×2 |")
    A(f"| `stage1.variant` | `{STAGE1_VARIANT}` | DL-020 §5 (headline variant; P3-T4 sweeps "
      "`protected_includes_integration`) |")
    A(f"| `duration_only.d_threshold_seconds` | **{sel['d_threshold_seconds']:g}** | DL-024 §1 "
      f"carbon retention, ρ = {RHO_PRIMARY:g}, on the ④b calibration sweep |")
    A(f"| `duration_only.w_max_hours` | **{sel['w_max_hours']:g}** | same rule, same sweep (W is "
      "the second swept coordinate, §A1.6) |")
    A("| `se_informed` block | *absent* | null path: no admitted family (A1.7); A1.8's window form "
      "and S2's regime gating have nothing to act on |")
    A(f"| `sweep` (grids) | W {list(fit['spec']['sweep']['w_max_hours'])}, D "
      f"{list(fit['spec']['sweep']['d_threshold_seconds'])}, τ "
      f"{list(fit['spec']['sweep']['tau_skip'])}, blanket {fit['spec']['sweep']['blanket_w_max_hours']:g} h "
      f"| copied from `replay/sweep_grid.json` (sha256 `{fit['spec']['sweep']['grid_sha256'][:16]}…`), "
      "DL-023 §2 — recorded before P3 |")
    A("")
    A("**The spec collapses to duration-only everywhere, and that is the finding it encodes:** no "
      "commit-level SE family cleared the predeclared materiality rule at the model level, so the "
      "frozen policy uses a commit-time duration estimate and the Stage-1 gate only. Under this "
      "spec strategy ⑤ *is* strategy ④b.\n")

    A("## 1. Policy path — the model-level admission rule\n")
    A("Re-applied here through `scheduler_core.admission` from P1-T6's ΔPR-AUC records, not copied "
      "from `admission.json`; the ×1 result is required to match P1-T7's record and does.\n")
    A("| floor multiplier | floor (ΔPR-AUC) | admitted families | policy path |")
    A("| :-- | --: | :-- | :-- |")
    for key, row in adm_info["by_multiplier"].items():
        A(f"| {key} | {row['floor']:.4f} | {', '.join(row['admitted']) or '*none*'} | "
          f"`{row['policy_path']}` |")
    A("")
    A("## 2. Decision-level half of §A1.7 (DL-013)\n")
    A("**Not applicable — no candidate family.** Admission needs *both* altitudes; with the "
      "model-level set empty at every multiplier there is no ⑤-vs-④ frontier to test. Verified on "
      f"the sweep records rather than assumed: ⑤ ≡ ④b at every grid point = "
      f"**{_f(checks['identities']['5_equals_4b_at_every_point'])}**, so the area between their "
      "frontiers is exactly 0 by construction. P3-T3 still runs the full ④a/④b/⑤ frontier "
      "comparison on the test trace.\n")

    A("## 3. The operating point — `d_threshold_seconds`, `w_max_hours`\n")
    A(f"Rule (DL-024 §1): over the {sel['n_points']} ④b points, `saving = −(carbon % vs ① static)`; "
      f"S* = **{sel['best_saving_pct']:.4f}%**; admissible if saving ≥ ρ·S* = "
      f"{sel['saving_floor_pct']:.4f}% (ρ = {RHO_PRIMARY:g}); choose the lowest TTFF p95 (failed "
      "builds), ties → larger `d_threshold`, then smaller `w_max`.\n")
    A(f"**Chosen: `{sel['setting_id']}`** — d_threshold = {sel['d_threshold_seconds']:g} s, "
      f"w_max = {sel['w_max_hours']:g} h, saving {sel['saving_pct']:.4f}%, TTFF p95 "
      f"{sel['ttff_p95_h_failed']:.4f} h ({sel['n_admissible']} of {sel['n_points']} points "
      "admissible).\n")
    A("| setting | D (s) | W (h) | deferred | saving % | TTFF p95 h (failed) | latency p95 h (deferred) | admissible | chosen |")
    A("| :-- | --: | --: | --: | --: | --: | --: | :-: | :-: |")
    for r in sel["table"]:
        A(f"| `{r['setting_id']}` | {r['param_d_threshold_seconds']:g} | {r['param_w_max_hours']:g} | "
          f"{int(r['n_deferred']):,} | {r['saving_pct'] + 0.0:.4f} | {_f(r['ttff_p95_h_failed'])} | "
          f"{_f(r['latency_p95_h_deferred'])} | {'✓' if r['admissible'] else ''} | "
          f"{'**◄**' if r['chosen'] else ''} |")
    A("")
    A("## 4. Sensitivity of the operating point to ρ (reported, not shipped)\n")
    A("| ρ | chosen setting | d_threshold (s) | w_max (h) | saving % | TTFF p95 h | spec elements that change vs ρ = 0.90 |")
    A("| --: | :-- | --: | --: | --: | --: | :-- |")
    for i, s in enumerate([sel] + list(sens)):
        changes = [f"`duration_only.{k}`" for k in ("d_threshold_seconds", "w_max_hours")
                   if s[k] != sel[k]]
        note = "— (primary, shipped)" if i == 0 else (", ".join(changes) or "none")
        A(f"| {s['rho']:g} | `{s['setting_id']}` | {s['d_threshold_seconds']:g} | "
          f"{s['w_max_hours']:g} | {s['saving_pct']:.4f} | {s['ttff_p95_h_failed']:.4f} | {note} |")
    A("")
    A("## 5. The ×0.5 / ×2 materiality-floor sweep (§A1.7)\n")
    A("A spec was fitted at each floor multiplier. The model-level admitted set is empty at all "
      "three, so the policy path — and with it the whole fitting pipeline — is identical:\n")
    A("| multiplier | policy path | d_threshold (s) | w_max (h) | spec elements that change vs ×1 |")
    A("| :-- | :-- | --: | --: | :-- |")
    for key, row in fit["floor_sweep_specs"].items():
        A(f"| {key} | `{row['policy_path']}` | {row['d_threshold_seconds']:g} | "
          f"{row['w_max_hours']:g} | {', '.join(row['changes']) or 'none'} |")
    A("\nThe decision-level floors (5% TTFF p95 / 1% carbon, ×0.5/×2) have no candidate to act on "
      "(§2).\n")

    A("## 6. Replay characteristics carried into P3 (DL-024 §5 — documented, not corrected)\n")
    ch = fit["characteristics"]
    A(f"- **⑥'s τ frontier is coarse.** p̂ takes **{ch['p_hat_distinct']}** distinct values on the "
      f"fitting sample; **{ch['p_hat_in_025_030']:,}** of {pop['n_sample']:,} "
      f"({100 * ch['p_hat_in_025_030'] / pop['n_sample']:.1f}%) lie in (0.25, 0.30]. Skips by τ: "
      + ", ".join(f"τ={t:g}: {n:,}" for t, n in ch["skips_by_tau"]) + ". The frozen τ grid "
      "stands; P3 reports this as a property of a step-function calibrator on a weak score.")
    A(f"- **④a has limited prediction support at the top of D.** ④a's estimate spans "
      f"{ch['d4a_min']:.2f}–{ch['d4a_max']:.2f} s (p99 {ch['d4a_p99']:.2f} s) vs ④b's max "
      f"{ch['d4b_max']:.2f} s; ④a defers nothing at D ≥ "
      f"{ch['d4a_first_empty_d']:g} s at any W. P3-T3 reports ④a's frontier over the points it "
      "spans; nothing is extrapolated.")
    A("")
    A("## 7. Checks\n")
    A("| check | result |")
    A("| :-- | :-- |")
    A(f"| every trace project is a calibration project (vs frozen `split_assignment.csv`) | "
      f"PASS — {checks['calibration_only']['trace_projects']} projects, 0 test projects |")
    A(f"| test split rows discarded unread by the loader | "
      f"{pop['test_builds_dropped_unread']:,} raw test build ids |")
    A(f"| every setting saw the identical build set | "
      f"{'PASS' if checks['identical_build_sets']['identical'] else 'FAIL'} "
      f"({checks['identical_build_sets']['settings_compared']} × "
      f"{checks['identical_build_sets']['builds_per_setting']:,}) |")
    v = checks["validator"]
    A(f"| independent validator — non-deferrable builds deferred | **{v['violations']}** of "
      f"{v['deferred']:,} deferrals / {v['rows']:,} rows — {'PASS' if v['passed'] else 'FAIL'} |")
    A(f"| independent validator — non-deferrable builds skipped by ⑥ | "
      f"**{checks['skip_audit']['non_deferrable_skipped']}** — "
      f"{'PASS' if checks['skip_audit']['passed'] else 'FAIL'} |")
    for k, val in checks["identities"].items():
        A(f"| DL-023 §1 identity `{k}` | {'holds' if val else 'DOES NOT HOLD'} |")
    A(f"| emitted spec loads under `require_fitted=True` (P2-T3 validator, schema v2) | "
      f"{'PASS' if checks['spec_loads_fitted'] else 'FAIL'} |")
    A("")
    A("## 8. Evidence consumed (sha256 at fitting time)\n")
    A("| role | file | sha256 |")
    A("| :-- | :-- | :-- |")
    for role, row in fit["evidence"].items():
        A(f"| {role} | `{row['path']}` | `{row['sha256']}` |")
    A("")
    A("## 9. Declared limits (P5-T4)\n")
    A(f"- The operating point is fitted on the DL-023 §4 sample: {pop['n_sample']:,} of "
      f"{pop['calibration_builds']:,} calibration builds ({100 * pop['n_sample'] / pop['calibration_builds']:.2f}%); "
      "its sampling noise is not bootstrapped here.")
    A("- ρ = 0.90 is a declared design parameter; §4 reports what 0.80 and 0.95 would have chosen.")
    A("- On the null path RQ4's headline row for ⑤ is ④b at this point by construction; the RQ2 "
      "verdict (P3-T3) compares whole frontiers and does not depend on the point chosen here.")
    A("- Carbon is proportional to duration under the energy model (§A1.13); the carbon axis of "
      "this sweep cannot carry SE value by construction.")
    A("")
    A("## Provenance\n")
    A(f"- Command: `{fit['command']}`  (run {fit['run_date']}, {fit['runtime_s']:.1f} s)")
    A(f"- Spec: `code/scheduler_core/config/policy_spec.yaml` sha256 `{fit['spec_sha256']}`")
    A(f"- Sweep: fingerprint `{fit['fingerprint'][:16]}…`; `summary.csv` sha256 "
      f"`{fit['sha256']['summary.csv'][:16]}…`; `decisions.csv.gz` sha256 "
      f"`{fit['sha256']['decisions.csv.gz'][:16]}…` (untracked; regenerate with the command above)")
    A(f"- d̂: frozen fit id `{fit['trace_provenance']['duration_control_fit_id']}` (primary "
      f"{fit['trace_provenance']['duration_control_primary_form']}); p̂: "
      f"`{fit['trace_provenance']['risk_arm']}` fit id `{fit['trace_provenance']['risk_arm_fit_id']}`")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #

def characteristics(trace: pd.DataFrame, summary: pd.DataFrame) -> dict[str, Any]:
    p = pd.to_numeric(trace["p_hat"], errors="coerce")
    d4a = pd.to_numeric(trace["d_hat_4a_seconds"], errors="coerce")
    d4b = pd.to_numeric(trace["d_hat_4b_seconds"], errors="coerce")
    six = summary.loc[summary["strategy"] == "6_risk_only_skip"]
    skips = [(float(t), int(n)) for t, n in zip(pd.to_numeric(six["param_tau_skip"]), six["n_skipped"])]
    a = summary.loc[summary["strategy"] == "4a_duration_estimator"].copy()
    a["d"] = pd.to_numeric(a["param_d_threshold_seconds"])
    empty = a.groupby("d")["n_deferred"].max()
    empty_ds = [float(d) for d, n in empty.items() if int(n) == 0]
    return {
        "p_hat_distinct": int(p.nunique()),
        "p_hat_in_025_030": int(((p > 0.25) & (p <= 0.30)).sum()),
        "skips_by_tau": skips,
        "d4a_min": float(d4a.min()), "d4a_max": float(d4a.max()),
        "d4a_p99": float(d4a.quantile(0.99)), "d4b_max": float(d4b.max()),
        "d4a_first_empty_d": min(empty_ds) if empty_ds else float("nan"),
    }


def run_fit(args: argparse.Namespace) -> int:
    t0 = time.time()
    command = "PYTHONPATH=. python scripts/fit_policy.py " + " ".join(sys.argv[1:])
    command = command.strip()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    spec_out: Path = out / "policy_spec.yaml" if args.verify else policy.DEFAULT_POLICY_SPEC_PATH

    if args.verify:
        committed = policy.load_policy_spec(policy.DEFAULT_POLICY_SPEC_PATH, require_fitted=True)
        generated = str(committed.provenance["generated"])
        command = str(committed.provenance["command"])     # the recorded command is part of the bytes
    else:
        generated = time.strftime("%Y-%m-%d")

    grid = sim.load_sweep_grid()
    for role, p in EVIDENCE.items():
        if not p.is_file():
            raise SystemExit(f"FATAL: evidence file missing: {p}")
    evidence = {role: {"path": rel(p), "sha256": sha(p)} for role, p in EVIDENCE.items()}
    admission = json.loads(EVIDENCE["admission"].read_text(encoding="utf-8"))
    deltas = json.loads(EVIDENCE["deltas"].read_text(encoding="utf-8"))
    if admission["provenance"].get("test_split_touched") is not False:
        raise SystemExit("FATAL: admission.json does not certify the test split untouched")
    adm_info = model_level_admission(deltas, admission)
    log(f"model-level admission (re-derived): {adm_info['by_multiplier']}")

    base = candidate_spec(adm_info["policy_path"], grid)
    energy = accounting.load_energy_config()
    profile = carbon.load_hour_of_week_profile()
    split = str(grid.sample["split"])
    if split != "calibration":
        raise SystemExit(f"FATAL: the fitting sweep must replay calibration, grid says {split!r}")

    log(f"reading the backbone CSV (keeping the {split} split only) …")
    assignment, split_digest = rr.load_frozen_assignment()
    builds, load_info = rr.load_split_builds(assignment, split)
    log(f"  {len(builds):,} analytic {split} builds / {builds['gh_project_name'].nunique():,} "
        f"projects; test builds dropped unread: {load_info['test_builds_dropped_unread']:,}")
    full_trace, trace_prov = rr.build_trace(builds)
    trace = sim.order_trace(sim.sample_builds(full_trace, int(grid.sample["n_builds"]),
                                              int(grid.sample["seed"])))
    sim.validate_trace(trace)
    cal_check = assert_calibration_only(trace, assignment)
    trace[list(sim.TRACE_COLUMNS)].to_csv(out / "trace.csv", index=False, lineterminator="\n",
                                          na_rep="")

    settings = sim.enumerate_settings(grid)
    fingerprint = sim.run_fingerprint(
        trace=trace, grid=grid, base_spec=base, p_avg_w=energy.p_avg_w,
        primary_form=trace_prov["duration_control_primary_form"],
        profile_path=carbon.DEFAULT_PROFILE_PATH,
        extra={"split_digest": split_digest, "task": "P2-T5", **trace_prov})
    log(f"fitting sweep: {len(settings)} settings × {len(trace):,} builds "
        f"(fingerprint {fingerprint[:16]}, resume={'off' if args.fresh else 'on'}) …")
    parts = sim.run_sweep(trace, settings, base_spec=base, profile=profile,
                          p_avg_w=energy.p_avg_w,
                          primary_form=trace_prov["duration_control_primary_form"],
                          parts_dir=args.parts_dir, fingerprint=fingerprint,
                          resume=not args.fresh, progress=log)
    decisions_path = out / "decisions.csv.gz"
    sim.assemble(parts, decisions_path)
    records = sim.load_records(decisions_path)
    identical = sim.assert_identical_build_sets(records)
    audit = vi.audit_frame(records, variant=base.stage1_variant, path=str(decisions_path))
    skip_audit = sim.audit_skips(records, variant=base.stage1_variant)
    identities = rr.identity_checks(records, grid)
    summary, herding = sim.summarise(records)
    summary.to_csv(out / "summary.csv", index=False, lineterminator="\n", na_rep="")
    herding.to_csv(out / "herding.csv", index=False, lineterminator="\n")
    if not (identical["identical"] and audit.passed and skip_audit["passed"]
            and identities["5_equals_4b_at_every_point"]):
        raise SystemExit("FATAL: a fitting-sweep check failed; no spec is written")

    primary = select_operating_point(summary, RHO_PRIMARY)
    sensitivity = [select_operating_point(summary, r) for r in RHO_SENSITIVITY]
    log(f"operating point (rho={RHO_PRIMARY:g}): {primary['setting_id']}")

    # Always the canonical paths: a --verify refit writes to scratch but must emit identical bytes.
    fit_sources = [rel(DEFAULT_OUT / "summary.csv"), rel(DEFAULT_OUT / "selection.json")]
    sources = [evidence[k]["path"] for k in ("admission", "deltas", "shap", "calibration",
                                             "duration_control")] + fit_sources
    spec = build_spec(admission_info=adm_info, chosen=primary, grid=grid, command=command,
                      generated=generated, sources=sources, fit_sources=fit_sources)

    # The ×0.5/×2 floor sweep: fit a spec at each multiplier and diff it against ×1.
    floor_specs: dict[str, Any] = {}
    for key, row in adm_info["by_multiplier"].items():
        if row["policy_path"] != "duration_only_fallback":
            raise SystemExit(f"FATAL: floor {key} admits {row['admitted']} — needs an se_informed fit")
        alt = build_spec(admission_info={**adm_info, "policy_path": row["policy_path"]},
                         chosen=primary, grid=grid, command=command, generated=generated,
                         sources=sources, fit_sources=fit_sources)
        changes = [f"{blk}.{k}" for blk in ("duration_only",) for k in spec[blk]
                   if alt[blk][k] != spec[blk][k]]
        if alt["policy_path"] != spec["policy_path"]:
            changes.insert(0, "policy_path")
        floor_specs[key] = {"policy_path": alt["policy_path"],
                            "d_threshold_seconds": alt["duration_only"]["d_threshold_seconds"],
                            "w_max_hours": alt["duration_only"]["w_max_hours"], "changes": changes}

    spec_text = dump_spec(spec)
    spec_out.parent.mkdir(parents=True, exist_ok=True)
    spec_out.write_text(spec_text, encoding="utf-8", newline="\n")
    loaded = policy.load_policy_spec(spec_out, require_fitted=True)
    spec_loads = bool(loaded.fitted and loaded.schema_version == policy.FITTED_SCHEMA_VERSION)

    def _sel_record(s: Mapping[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in s.items() if k != "table"} | {
            "table": s["table"].to_dict(orient="records")}

    selection = {"banner": FITTING_BANNER, "rule": "DL-024 §1",
                 "primary": _sel_record(primary),
                 "sensitivity": [_sel_record(s) for s in sensitivity]}
    (out / "selection.json").write_text(json.dumps(selection, indent=2, default=str) + "\n",
                                        encoding="utf-8")
    (out / "validator.json").write_text(json.dumps(
        {"banner": FITTING_BANNER, "variant": base.stage1_variant,
         "gate_safety": audit.as_dict(), "skip_audit": skip_audit,
         "note": "DL-020 §6: a pass proves consistency with the eligibility RULE, not that the "
                 "rule identifies genuinely deferrable builds."}, indent=2, default=str) + "\n",
        encoding="utf-8")

    population = {
        "split": split, "calibration_builds": int(len(full_trace)),
        "calibration_projects": int(full_trace["gh_project_name"].nunique()),
        "n_sample": int(len(trace)), "seed": int(grid.sample["seed"]),
        "sample_projects": int(trace["gh_project_name"].nunique()),
        "sample_failure_rate": float(trace["y_fail"].mean()),
        "n_unaccountable": int((~sim.accountable_mask(trace)).sum()), **load_info,
    }
    outputs = ["trace.csv", "decisions.csv.gz", "summary.csv", "herding.csv", "selection.json",
               "validator.json"]
    fit = {
        "banner": FITTING_BANNER, "task": "P2-T5", "decision_log": ["DL-022", "DL-023", "DL-024"],
        "command": command, "run_date": time.strftime("%Y-%m-%d"),
        "runtime_s": round(time.time() - t0, 1),
        "fingerprint": fingerprint, "grid_sha256": grid.digest(),
        "split_assignment_sha256": split_digest, "evidence": evidence,
        "admission": adm_info, "trace_provenance": trace_prov, "population": population,
        "candidate_spec": base.provenance_record(),
        "selection": {"primary": primary, "sensitivity": sensitivity},
        "floor_sweep_specs": floor_specs,
        "characteristics": characteristics(trace, summary),
        "checks": {"calibration_only": cal_check, "identical_build_sets": identical,
                   "validator": audit.as_dict(), "skip_audit": skip_audit,
                   "identities": identities, "spec_loads_fitted": spec_loads},
        "spec": spec, "spec_sha256": sha(spec_out),
        "sha256": {name: sha(out / name) for name in outputs},
    }
    fit_json = {**fit, "selection": {k: (_sel_record(v) if isinstance(v, dict) else
                                         [_sel_record(x) for x in v])
                                     for k, v in fit["selection"].items()}}
    (out / "manifest.json").write_text(json.dumps(fit_json, indent=2, default=str) + "\n",
                                       encoding="utf-8")
    derivation_path = out / "policy_derivation.md" if args.verify else DERIVATION
    write_derivation(derivation_path, fit=fit_json, spec_text=spec_text, summary=summary)
    log(f"wrote {spec_out} (sha256 {fit['spec_sha256'][:16]}…) and {derivation_path}")

    ok = spec_loads
    if args.verify:
        committed_bytes = policy.DEFAULT_POLICY_SPEC_PATH.read_bytes()
        committed_manifest = json.loads((DEFAULT_OUT / "manifest.json").read_text(encoding="utf-8"))
        rows = {name: {"committed": committed_manifest["sha256"].get(name),
                       "refit": fit["sha256"][name],
                       "identical": committed_manifest["sha256"].get(name) == fit["sha256"][name]}
                for name in ("trace.csv", "decisions.csv.gz", "summary.csv", "selection.json")}
        spec_identical = spec_out.read_bytes() == committed_bytes
        verdict = {"command": "PYTHONPATH=. python scripts/fit_policy.py " + " ".join(sys.argv[1:]),
                   "run_date": time.strftime("%Y-%m-%d"), "fresh": bool(args.fresh),
                   "refit_dir": str(out),
                   "policy_spec_yaml": {"committed_sha256": sha(policy.DEFAULT_POLICY_SPEC_PATH),
                                        "refit_sha256": fit["spec_sha256"],
                                        "byte_identical": spec_identical},
                   "files": rows,
                   "all_identical": spec_identical and all(r["identical"] for r in rows.values())}
        (DEFAULT_OUT / "verify.json").write_text(json.dumps(verdict, indent=2) + "\n",
                                                 encoding="utf-8")
        log(f"verify: policy_spec.yaml {'BYTE-IDENTICAL' if spec_identical else 'DIFFERS'}; {rows}")
        ok = ok and verdict["all_identical"]
    log(f"done ({time.time() - t0:.0f}s)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--parts-dir", type=Path, default=DEFAULT_PARTS)
    ap.add_argument("--fresh", action="store_true", help="recompute every sweep part")
    ap.add_argument("--verify", action="store_true",
                    help="refit into --out (not the committed paths) and require a byte-identical spec")
    args = ap.parse_args()
    if args.verify and args.out.resolve() == DEFAULT_OUT.resolve():
        ap.error("--verify needs a scratch --out, so the committed outputs are compared, not overwritten")
    if args.verify and not args.fresh:
        ap.error("--verify needs --fresh: resumed sweep parts would make the refit a copy, not a refit")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    return run_fit(args)


if __name__ == "__main__":
    raise SystemExit(main())

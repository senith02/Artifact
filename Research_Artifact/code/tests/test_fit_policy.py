"""Tests for P2-T5 — `scripts/fit_policy.py` and the frozen `policy_spec.yaml` (DL-024).

What is being defended:

1. **The operating-point rule is DL-024 §1, exactly** — carbon retention at ρ, lowest
   TTFF p95 among admissible points, the declared tie-breaks, and a hard failure (never
   a default) when no point saves carbon.
2. **Every numeric field of the spec has a `source` provenance entry**, and the spec is
   loadable by P2-T3's validator under `require_fitted=True` (S4).
3. **No test-split project can reach the fit** (DoD) — the calibration-only assertion
   fires on a trace that contains one.
4. **The policy path is re-derived from P1's deltas**, and must agree with P1-T7.
5. Once the spec exists: its values are grid points chosen by the recorded selection,
   its recorded grids are `sweep_grid.json`'s, and its sources exist.

Offline: synthetic summaries plus the committed `results/` files; no dataset is read.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from replay import simulator as sim
from scheduler_core import policy

CODE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CODE_ROOT.parent


def _load_script():
    """Import `scripts/fit_policy.py` as a module (it is not on the package path)."""
    for p in (CODE_ROOT, CODE_ROOT / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "fit_policy_under_test", CODE_ROOT / "scripts" / "fit_policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fp = _load_script()


def _summary(points: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """(d, w, carbon_pct_vs_static, ttff_p95) rows for ④b, plus a static row."""
    rows = [{"strategy": "1_static", "setting_id": "1_static", "param_d_threshold_seconds": None,
             "param_w_max_hours": None, "n_deferred": 0, "carbon_pct_vs_static": 0.0,
             "ttff_p95_h_failed": 5.0, "latency_p95_h_deferred": None}]
    for d, w, pct, ttff in points:
        rows.append({"strategy": fp.FIT_STRATEGY, "setting_id": f"4b__d{d:g}__w{w:g}",
                     "param_d_threshold_seconds": d, "param_w_max_hours": w, "n_deferred": 1,
                     "carbon_pct_vs_static": pct, "ttff_p95_h_failed": ttff,
                     "latency_p95_h_deferred": w})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 1. The DL-024 §1 rule
# --------------------------------------------------------------------------- #

def test_rule_takes_the_lowest_ttff_among_points_retaining_rho_of_the_best_saving():
    s = _summary([(0, 24, -10.0, 20.0),     # best saving S* = 10
                  (480, 24, -9.5, 15.0),    # 95% of S*  -> admissible, lower TTFF
                  (960, 24, -8.9, 9.0),     # 89% of S*  -> NOT admissible at rho 0.90
                  (240, 12, -9.0, 14.0)])   # exactly 90% -> admissible (>=), lowest admissible TTFF
    sel = fp.select_operating_point(s, 0.90)
    assert (sel["d_threshold_seconds"], sel["w_max_hours"]) == (240.0, 12.0)
    assert sel["best_saving_pct"] == pytest.approx(10.0)
    assert sel["n_admissible"] == 3
    assert fp.select_operating_point(s, 0.85)["d_threshold_seconds"] == 960.0


def test_rule_tie_breaks_larger_d_then_smaller_w():
    s = _summary([(0, 24, -10.0, 12.0), (480, 24, -10.0, 12.0), (480, 12, -10.0, 12.0)])
    sel = fp.select_operating_point(s, 0.90)
    assert (sel["d_threshold_seconds"], sel["w_max_hours"]) == (480.0, 12.0)


def test_rule_fails_rather_than_defaulting_when_nothing_saves_carbon():
    with pytest.raises(ValueError, match="nothing to fit"):
        fp.select_operating_point(_summary([(0, 24, 0.0, 5.0), (60, 24, 0.0, 5.0)]), 0.90)


def test_rule_refuses_a_point_without_ttff_and_a_bad_rho():
    with pytest.raises(ValueError, match="TTFF"):
        fp.select_operating_point(_summary([(0, 24, -1.0, float("nan"))]), 0.90)
    for rho in (0.0, 1.5):
        with pytest.raises(ValueError, match="rho"):
            fp.select_operating_point(_summary([(0, 24, -1.0, 5.0)]), rho)


def test_a_stricter_rho_never_chooses_a_point_saving_less():
    s = _summary([(d, w, -(10 - d / 1000 - w / 100), 5 + 20 * (1 - d / 2000))
                  for d in (0, 240, 480, 960, 1920) for w in (6, 12, 24)])
    savings = [fp.select_operating_point(s, r)["saving_pct"] for r in (0.5, 0.8, 0.9, 0.95, 1.0)]
    assert savings == sorted(savings)


def test_the_declared_rho_values_are_dl024s():
    assert fp.RHO_PRIMARY == 0.90
    assert fp.RHO_SENSITIVITY == (0.80, 0.95)
    assert fp.FIT_STRATEGY == "4b_duration_prior"


# --------------------------------------------------------------------------- #
# 2. The spec: provenance per numeric value, loadable, deterministic
# --------------------------------------------------------------------------- #

def _built_spec() -> dict:
    grid = sim.load_sweep_grid()
    s = _summary([(0, 24, -10.0, 20.0), (480, 24, -9.5, 15.0)])
    chosen = fp.select_operating_point(s, fp.RHO_PRIMARY)
    return fp.build_spec(
        admission_info={"policy_path": "duration_only_fallback"}, chosen=chosen, grid=grid,
        command="PYTHONPATH=. python scripts/fit_policy.py", generated="2026-09-24",
        sources=["results/p1/admission.json"],
        fit_sources=["results/p2/policy_fit/summary.csv", "results/p2/policy_fit/selection.json"])


def _numeric_leaves(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _numeric_leaves(v, f"{prefix}{k}.")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _numeric_leaves(v, f"{prefix}{i}.")
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield prefix.rstrip(".")


def _assert_every_numeric_field_is_sourced(raw: dict) -> None:
    """S4: every numeric field has a `source` provenance entry.

    Policy values (duration_only / se_informed) need a provenance.values entry naming
    results/ files. Grid values live in `sweep`, which carries its own `source`. The
    only other numbers are schema metadata (`schema_version`, `provenance.seed`).
    """
    values = raw["provenance"]["values"]
    for leaf in _numeric_leaves(raw):
        block = leaf.split(".")[0]
        if block in ("duration_only", "se_informed"):
            entry = values[leaf]
            assert entry["source"] and all(isinstance(x, str) and x for x in entry["source"]), leaf
        elif block == "sweep":
            assert raw["sweep"]["source"] and raw["sweep"]["grid_sha256"], leaf
        else:
            assert leaf in ("schema_version", "provenance.seed"), f"unsourced numeric field {leaf}"


def test_the_built_spec_sources_every_numeric_field_and_loads_fitted(tmp_path):
    raw = _built_spec()
    _assert_every_numeric_field_is_sourced(raw)
    path = tmp_path / "policy_spec.yaml"
    path.write_text(fp.dump_spec(raw), encoding="utf-8")
    spec = policy.load_policy_spec(path, require_fitted=True)
    assert spec.fitted and spec.schema_version == 2
    assert spec.policy_path == "duration_only_fallback"
    assert not spec.se_informed, "the null path must not emit an se_informed block"


def test_dumping_the_spec_is_deterministic():
    assert fp.dump_spec(_built_spec()) == fp.dump_spec(_built_spec())


def test_the_recorded_sweep_is_the_frozen_grid():
    raw, grid = _built_spec(), sim.load_sweep_grid()
    assert raw["sweep"]["grid_sha256"] == grid.digest()
    assert raw["sweep"]["d_threshold_seconds"] == list(grid.d_threshold_seconds)
    assert raw["sweep"]["w_max_hours"] == list(grid.w_max_hours)
    assert raw["sweep"]["tau_skip"] == list(grid.tau_skip)


def test_the_candidate_sweep_spec_is_unfitted_and_quarantined():
    cand = fp.candidate_spec("duration_only_fallback", sim.load_sweep_grid())
    assert not cand.fitted
    with pytest.raises(SystemExit):
        fp.candidate_spec("se_informed", sim.load_sweep_grid())


# --------------------------------------------------------------------------- #
# 3. No test project reaches the fit
# --------------------------------------------------------------------------- #

def test_calibration_only_assertion_fires_on_a_test_project():
    assignment = {"a/cal": "calibration", "b/test": "test", "c/train": "train"}
    ok = pd.DataFrame({"gh_project_name": ["a/cal", "a/cal"]})
    assert fp.assert_calibration_only(ok, assignment)["test_projects_in_trace"] == 0
    for bad in ("b/test", "c/train", "d/unknown"):
        with pytest.raises(SystemExit):
            fp.assert_calibration_only(pd.DataFrame({"gh_project_name": ["a/cal", bad]}),
                                       assignment)


# --------------------------------------------------------------------------- #
# 4. The policy path, re-derived from P1
# --------------------------------------------------------------------------- #

def test_policy_path_is_rederived_from_p1_deltas_and_agrees_with_p1_t7():
    deltas = json.loads(fp.EVIDENCE["deltas"].read_text(encoding="utf-8"))
    admission = json.loads(fp.EVIDENCE["admission"].read_text(encoding="utf-8"))
    info = fp.model_level_admission(deltas, admission)
    assert info["policy_path"] == admission["policy_path"]
    assert set(info["by_multiplier"]) == {"x0.5", "x1", "x2"}
    tampered = json.loads(json.dumps(admission))
    tampered["policy_path"] = "se_informed"
    with pytest.raises(SystemExit):
        fp.model_level_admission(deltas, tampered)


# --------------------------------------------------------------------------- #
# 5. The frozen artifact itself (vacuous until P2-T5's real run writes it)
# --------------------------------------------------------------------------- #

FITTED = policy.DEFAULT_POLICY_SPEC_PATH
SELECTION = fp.DEFAULT_OUT / "selection.json"


@pytest.mark.skipif(not FITTED.exists(), reason="policy_spec.yaml not fitted yet")
def test_the_frozen_spec_is_fully_sourced_and_matches_its_recorded_selection():
    raw = yaml.safe_load(FITTED.read_text(encoding="utf-8"))
    _assert_every_numeric_field_is_sourced(raw)
    spec = policy.load_policy_spec(FITTED, require_fitted=True)
    grid = sim.load_sweep_grid()
    assert raw["sweep"]["grid_sha256"] == grid.digest()
    assert raw["provenance"]["test_split_read"] is False
    d, w = spec.duration_only["d_threshold_seconds"], spec.duration_only["w_max_hours"]
    assert d in grid.d_threshold_seconds and w in grid.w_max_hours, "values must be grid points"
    sel = json.loads(SELECTION.read_text(encoding="utf-8"))["primary"]
    assert (sel["d_threshold_seconds"], sel["w_max_hours"]) == (d, w)
    assert sel["rho"] == fp.RHO_PRIMARY
    for entry in raw["provenance"]["values"].values():
        for src in entry["source"]:
            assert (REPO_ROOT / src).is_file(), f"provenance source missing: {src}"
    for src in raw["provenance"]["sources"]:
        assert (REPO_ROOT / src).is_file(), f"provenance source missing: {src}"

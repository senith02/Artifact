"""Tests for scheduler_core.admission — the §A1.7 model-level rule (P1-T7)."""

from __future__ import annotations

import pytest

from scheduler_core import admission as adm


def rec(delta: float, ci_lo: float, ci_hi: float) -> dict:
    return {"delta": delta, "ci_lo": ci_lo, "ci_hi": ci_hi}


# --------------------------------------------------------------------------- #
# apply_model_floor — the two conditions, and the direction guard
# --------------------------------------------------------------------------- #

def test_admits_a_family_clearing_both_conditions():
    v = adm.apply_model_floor(rec(+0.02, +0.01, +0.03))
    assert v["admitted"] is True
    assert v["ci_direction"] == "positive"
    assert v["meets_floor"] is True


def test_rejects_a_positive_significant_family_below_the_floor():
    v = adm.apply_model_floor(rec(+0.005, +0.003, +0.007))
    assert v["admitted"] is False
    assert v["ci_excludes_zero"] is True
    assert v["meets_floor"] is False
    assert "below the" in v["decided_by"]


def test_rejects_a_large_delta_whose_ci_includes_zero():
    v = adm.apply_model_floor(rec(+0.02, -0.01, +0.05))
    assert v["admitted"] is False
    assert v["ci_direction"] == "spans_zero"
    assert v["meets_floor"] is True
    assert "includes 0" in v["decided_by"]


def test_a_significantly_worse_family_is_rejected_not_admitted():
    """The |Δ| misreading guard (DL-019 §2).

    F4's real P1-T6 numbers: the magnitude exceeds the 0.01 floor and the CI
    excludes 0 — but in the *negative* direction. "≥ 0.01 absolute" means an
    improvement of 0.01 in absolute units, so this must reject.
    """
    v = adm.apply_model_floor(rec(-0.064694, -0.067304, -0.061747))
    assert v["admitted"] is False
    assert v["ci_direction"] == "negative"
    assert v["ci_excludes_zero"] is True
    assert v["meets_floor"] is False
    assert "worse" in v["decided_by"]


def test_the_floor_is_inclusive():
    v = adm.apply_model_floor(rec(+0.01, +0.005, +0.015))
    assert v["admitted"] is True


def test_floor_is_configurable_for_the_sweep():
    r = rec(+0.0075, +0.005, +0.010)
    assert adm.apply_model_floor(r, floor=0.005)["admitted"] is True
    assert adm.apply_model_floor(r, floor=0.01)["admitted"] is False
    assert adm.apply_model_floor(r, floor=0.02)["admitted"] is False


# --------------------------------------------------------------------------- #
# admission_set
# --------------------------------------------------------------------------- #

def test_admission_set_partitions_families():
    families = {
        "F1": rec(+0.02, +0.01, +0.03),      # admitted
        "F2": rec(-0.05, -0.06, -0.04),      # worse
        "F3": rec(+0.03, -0.01, +0.07),      # CI spans 0
    }
    out = adm.admission_set(families)
    assert out["admitted"] == ["F1"]
    assert out["rejected"] == ["F2", "F3"]
    assert out["floor"] == adm.MODEL_FLOOR_ABS


def test_admission_set_can_be_empty():
    families = {"F1": rec(-0.01, -0.02, -0.005), "F2": rec(+0.001, -0.001, +0.003)}
    out = adm.admission_set(families)
    assert out["admitted"] == []
    assert sorted(out["rejected"]) == ["F1", "F2"]


# --------------------------------------------------------------------------- #
# floor_sweep
# --------------------------------------------------------------------------- #

def test_sweep_is_stable_when_nothing_is_admitted_anywhere():
    families = {"F1": rec(-0.004, -0.006, -0.002), "F2": rec(-0.07, -0.08, -0.06)}
    sweep = adm.floor_sweep(families)
    assert sweep["stable"] is True
    assert all(v["admitted"] == [] for v in sweep["by_floor"].values())
    assert sorted(v["floor"] for v in sweep["by_floor"].values()) == [0.005, 0.01, 0.02]


def test_sweep_detects_a_floor_sensitive_admission():
    families = {"F1": rec(+0.0075, +0.005, +0.010)}
    sweep = adm.floor_sweep(families)
    assert sweep["stable"] is False
    assert sweep["by_floor"]["x0.5"]["admitted"] == ["F1"]
    assert sweep["by_floor"]["x1"]["admitted"] == []
    assert sweep["by_floor"]["x2"]["admitted"] == []


def test_sweep_scales_only_the_floor_not_the_significance_condition():
    # CI spans 0, so no floor — however small — can admit this family.
    families = {"F1": rec(+0.5, -0.1, +1.0)}
    sweep = adm.floor_sweep(families, multipliers=(0.01, 0.5, 1.0, 2.0))
    assert all(v["admitted"] == [] for v in sweep["by_floor"].values())


def test_ci_direction_classifies_all_three_cases():
    assert adm.ci_direction(0.01, 0.03) == "positive"
    assert adm.ci_direction(-0.03, -0.01) == "negative"
    assert adm.ci_direction(-0.01, 0.01) == "spans_zero"
    assert adm.ci_direction(0.0, 0.01) == "spans_zero"     # touching 0 is not excluding it

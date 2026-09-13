"""Tests for scheduler_core.ablation_stats (P1-T6, DL-019)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scheduler_core import ablation_stats as ab


# --------------------------------------------------------------------------- #
# paired_metric_delta
# --------------------------------------------------------------------------- #

def _synthetic_labels_and_scores(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    y = (rng.uniform(size=n) < 0.25).astype("int64")
    return rng, y


def test_paired_metric_delta_identical_arms_is_not_significant():
    rng, y = _synthetic_labels_and_scores()
    p = np.clip(y * 0.6 + rng.uniform(0, 0.3, size=len(y)), 0.001, 0.999)
    out = ab.paired_metric_delta(y, p, p, n_resamples=200, seed=42)
    for m in ("pr_auc", "roc_auc", "brier", "ece"):
        assert out[m]["delta"] == pytest.approx(0.0, abs=1e-9)
        assert out[m]["significant"] is False


def test_paired_metric_delta_detects_a_clearly_better_treatment():
    rng, y = _synthetic_labels_and_scores(n=6000, seed=1)
    p_control = rng.uniform(size=len(y))                       # uninformative
    p_treatment = np.clip(y * 0.85 + rng.uniform(0, 0.1, size=len(y)), 0.001, 0.999)
    out = ab.paired_metric_delta(y, p_control, p_treatment, n_resamples=300, seed=42)
    assert out["pr_auc"]["delta"] > 0.1
    assert out["pr_auc"]["significant"] is True
    assert out["pr_auc"]["ci_lo"] > 0


def test_paired_metric_delta_is_deterministic():
    rng, y = _synthetic_labels_and_scores(n=2000, seed=2)
    p_control = rng.uniform(size=len(y))
    p_treatment = np.clip(y * 0.7 + rng.uniform(0, 0.2, size=len(y)), 0.001, 0.999)
    a = ab.paired_metric_delta(y, p_control, p_treatment, n_resamples=150, seed=7)
    b = ab.paired_metric_delta(y, p_control, p_treatment, n_resamples=150, seed=7)
    assert a == b


def test_paired_metric_delta_rejects_length_mismatch():
    with pytest.raises(ValueError):
        ab.paired_metric_delta([0, 1, 0], [0.1, 0.2], [0.3, 0.4, 0.5])


# --------------------------------------------------------------------------- #
# spearman_with_ci
# --------------------------------------------------------------------------- #

def test_spearman_with_ci_perfect_positive_monotone():
    x = np.arange(500, dtype="float64")
    s = x * 2.0 + 1.0
    out = ab.spearman_with_ci(x, s, n_resamples=200, seed=42)
    assert out["rho"] == pytest.approx(1.0, abs=1e-9)
    assert out["monotone"] is True
    assert out["ci_lo"] > 0


def test_spearman_with_ci_perfect_negative_monotone():
    x = np.arange(500, dtype="float64")
    s = -x
    out = ab.spearman_with_ci(x, s, n_resamples=200, seed=42)
    assert out["rho"] == pytest.approx(-1.0, abs=1e-9)
    assert out["monotone"] is True
    assert out["ci_hi"] < 0


def test_spearman_with_ci_independent_is_not_monotone():
    rng = np.random.default_rng(3)
    x = rng.uniform(size=3000)
    s = rng.uniform(size=3000)                # independent of x
    out = ab.spearman_with_ci(x, s, n_resamples=300, seed=42)
    assert abs(out["rho"]) < 0.1
    assert out["monotone"] is False


def test_spearman_with_ci_flags_a_constant_feature_as_degenerate():
    x = np.zeros(100)
    s = np.arange(100, dtype="float64")
    out = ab.spearman_with_ci(x, s, n_resamples=50, seed=42)
    assert out["degenerate"] is True
    assert out["monotone"] is False
    assert np.isnan(out["rho"])


# --------------------------------------------------------------------------- #
# variance_decomposition
# --------------------------------------------------------------------------- #

def test_variance_decomposition_pure_between_project():
    # Two projects, zero within-project spread -> all variance is between.
    values = [0.0] * 50 + [10.0] * 50
    groups = ["A"] * 50 + ["B"] * 50
    out = ab.variance_decomposition(values, groups)
    assert out["within"] == pytest.approx(0.0, abs=1e-9)
    assert out["between_share"] == pytest.approx(1.0, abs=1e-9)
    assert out["n_groups"] == 2


def test_variance_decomposition_pure_within_project():
    # One project only -> all variance is within (between is exactly 0).
    rng = np.random.default_rng(4)
    values = rng.normal(size=200)
    groups = ["A"] * 200
    out = ab.variance_decomposition(values, groups)
    assert out["between"] == pytest.approx(0.0, abs=1e-9)
    assert out["within_share"] == pytest.approx(1.0, abs=1e-9)


def test_variance_decomposition_shares_sum_to_one_and_matches_total_variance():
    rng = np.random.default_rng(5)
    n_per_group = 200
    groups = np.repeat(["A", "B", "C", "D"], n_per_group)
    offsets = np.repeat([0.0, 3.0, -2.0, 5.0], n_per_group)
    values = offsets + rng.normal(scale=1.0, size=len(groups))
    out = ab.variance_decomposition(values, groups)
    assert out["between_share"] + out["within_share"] == pytest.approx(1.0, abs=1e-9)
    expected_total = float(((values - values.mean()) ** 2).sum())
    assert out["total"] == pytest.approx(expected_total, rel=1e-9)


def test_variance_decomposition_rejects_length_mismatch():
    with pytest.raises(ValueError):
        ab.variance_decomposition([1.0, 2.0, 3.0], ["A", "B"])

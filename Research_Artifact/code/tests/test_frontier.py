"""Tests for replay.frontier — the DL-029 frontier and matched-point rules."""

from __future__ import annotations

import numpy as np
import pytest

from replay import frontier as fr


def test_pareto_drops_dominated_and_duplicate_points():
    s = [0.0, 1.0, 1.0, 2.0, 1.5, 0.0]
    t = [1.0, 3.0, 2.0, 5.0, 6.0, 1.0]
    f = fr.pareto_frontier(s, t)
    assert f.saving.tolist() == [0.0, 1.0, 2.0]
    assert f.ttff.tolist() == [1.0, 2.0, 5.0]


def test_frontier_ttff_is_strictly_increasing_in_saving():
    rng = np.random.default_rng(0)
    f = fr.pareto_frontier(rng.random(50), rng.random(50))
    assert np.all(np.diff(f.saving) > 0) and np.all(np.diff(f.ttff) > 0)


def test_equal_ttff_keeps_only_the_higher_saving():
    f = fr.pareto_frontier([1.0, 2.0], [3.0, 3.0])
    assert f.saving.tolist() == [2.0] and f.ttff.tolist() == [3.0]


def test_no_extrapolation_outside_the_frontier():
    f = fr.pareto_frontier([0.0, 2.0], [1.0, 3.0])
    assert fr.ttff_at(f, [1.0])[0] == pytest.approx(2.0)
    assert np.isnan(fr.ttff_at(f, [2.5])[0]) and np.isnan(fr.saving_at(f, [0.5])[0])


def test_matched_grid_is_interior_and_on_the_overlap():
    g = fr.matched_grid((0.0, 4.0), (1.0, 3.0), k=3)
    assert g.tolist() == pytest.approx([1.5, 2.0, 2.5])
    assert fr.matched_grid((0.0, 1.0), (1.0, 2.0)).size == 0


def test_identical_frontiers_give_zero_difference_and_zero_area():
    f = fr.pareto_frontier([0.0, 1.0, 2.0], [1.0, 2.0, 4.0])
    cg = fr.matched_grid(f.saving_range, f.saving_range)
    tg = fr.matched_grid(f.ttff_range, f.ttff_range)
    d = fr.differences(f, f, cg, tg)
    assert np.all(d["d_ttff"] == 0) and np.all(d["d_saving"] == 0)
    assert fr.area_between(f, f) == 0.0


def test_signs_favour_the_treatment():
    ref = fr.pareto_frontier([0.0, 2.0], [1.0, 5.0])
    trt = fr.pareto_frontier([0.0, 2.0], [1.0, 3.0])        # lower TTFF at every saving
    d = fr.differences(ref, trt, np.array([1.0]), np.array([2.0]))
    assert d["d_ttff"][0] == pytest.approx(1.0)              # 3.0 − 2.0
    assert d["rel_d_ttff"][0] == pytest.approx(1.0 / 3.0)
    assert d["d_saving"][0] > 0
    assert fr.area_between(ref, trt) == pytest.approx(2.0)  # triangle, base 2, height 2


def test_counting_needs_floor_ci_and_definedness():
    rel = np.array([0.06, 0.06, 0.04, 0.06])
    lo = np.array([0.1, -0.1, 0.1, 0.1])
    und = np.array([0.0, 0.0, 0.0, 0.2])
    assert fr.count_points(rel, lo, und, fr.TTFF_FLOOR).tolist() == [True, False, False, False]


def test_decision_condition_needs_three_points_on_one_axis():
    yes = np.array([True, True, True, False])
    two = np.array([True, True, False, False])
    assert fr.decision_condition(yes, two) and not fr.decision_condition(two, two)


def test_rejects_non_finite_points():
    with pytest.raises(ValueError):
        fr.pareto_frontier([0.0, np.nan], [1.0, 2.0])

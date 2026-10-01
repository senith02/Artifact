"""Tests for replay.stats.paired_bootstrap — eval_protocol §9, signature §10."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from replay import stats


def _per_build(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.gamma(2.0, 1.0, n)
    ids = [str(i) for i in range(n)]
    return pd.concat([
        pd.DataFrame({"strategy": "A", "tr_build_id": ids, "x": base}),
        pd.DataFrame({"strategy": "B", "tr_build_id": ids, "x": base * 0.9}),
        pd.DataFrame({"strategy": "C", "tr_build_id": ids, "x": base}),
    ], ignore_index=True)


METRICS = {"mean_x": lambda f: float(f["x"].mean()),
           "p95_x": lambda f: float(np.percentile(f["x"], 95))}


def test_point_estimates_are_the_full_trace_metrics():
    df = _per_build()
    out = stats.paired_bootstrap(df, METRICS, strategies=["A", "B"], n_resamples=30)
    a = df.loc[df["strategy"] == "A", "x"]
    assert out["per_strategy"]["A"]["mean_x"]["point"] == pytest.approx(a.mean())
    assert out["per_strategy"]["A"]["p95_x"]["point"] == pytest.approx(np.percentile(a, 95))


def test_ci_brackets_point_and_difference_is_paired():
    df = _per_build()
    out = stats.paired_bootstrap(df, METRICS, strategies=["A", "B"], n_resamples=200)
    rec = out["per_strategy"]["B"]["mean_x"]
    assert rec["ci_lo"] <= rec["point"] <= rec["ci_hi"]
    d = out["differences"]["mean_x"]["A__minus__B"]
    # B = 0.9·A build by build, so every paired resample difference is positive.
    assert d["ci_lo"] > 0 and d["significant"] is True


def test_identical_strategies_give_an_exactly_zero_difference():
    df = _per_build()
    out = stats.paired_bootstrap(df, METRICS, strategies=["A", "C"], n_resamples=50)
    d = out["differences"]["mean_x"]["A__minus__C"]
    assert d["point"] == 0.0 and d["ci_lo"] == 0.0 and d["ci_hi"] == 0.0
    assert d["significant"] is False


def test_deterministic_under_the_seed():
    df = _per_build()
    a = stats.paired_bootstrap(df, METRICS, strategies=["A", "B"], n_resamples=20)
    b = stats.paired_bootstrap(df, METRICS, strategies=["A", "B"], n_resamples=20)
    assert a == b


def test_refuses_an_unpaired_trace():
    df = _per_build()
    df.loc[df.index[-1], "tr_build_id"] = "not-in-A"
    with pytest.raises(stats.StatsError, match="same build trace"):
        stats.paired_bootstrap(df, METRICS, strategies=["A", "C"], n_resamples=5)


def test_refuses_a_missing_strategy():
    with pytest.raises(stats.StatsError, match="no rows"):
        stats.paired_bootstrap(_per_build(), METRICS, strategies=["A", "Z"], n_resamples=5)


def test_undefined_metric_is_reported_as_none_not_zero():
    df = _per_build()
    out = stats.paired_bootstrap(df, {"never": lambda f: None}, strategies=["A", "B"],
                                 n_resamples=5)
    rec = out["per_strategy"]["A"]["never"]
    assert rec["point"] is None and rec["ci_lo"] is None
    assert out["differences"]["never"]["A__minus__B"]["significant"] is None

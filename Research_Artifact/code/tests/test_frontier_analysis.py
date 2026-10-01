"""Tests for scripts/frontier_analysis.py: the weighted recomputation equals the simulator's own
aggregation, on the full trace and on an explicit bootstrap resample (DL-029 §1, §8)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from replay import simulator as sim
from scheduler_core import accounting, carbon, policy

CODE_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, file: str):
    for p in (CODE_ROOT, CODE_ROOT / "scripts", CODE_ROOT / "tests"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fa = _load("frontier_analysis_under_test", CODE_ROOT / "scripts" / "frontier_analysis.py")
trr = _load("trr_helpers", CODE_ROOT / "tests" / "test_run_test_replay.py")

SETTINGS = [sim.Setting("1_static"),
            sim.Setting("4b_duration_prior", d_threshold_seconds=0.0, w_max_hours=24.0),
            sim.Setting("4b_duration_prior", d_threshold_seconds=480.0, w_max_hours=24.0)]


@pytest.fixture(scope="module")
def replayed():
    trace = trr._trace(n=120, seed=11)
    spec = policy.load_policy_spec(require_fitted=True)
    profile = carbon.load_hour_of_week_profile()
    recs = []
    for s in SETTINGS:
        rec = sim.replay_setting(trace, s, base_spec=spec, profile=profile, p_avg_w=42.5,
                                 primary_form="4b")
        recs.append(pd.read_csv(pd.io.common.StringIO(
            sim.records_to_csv_bytes(rec, header=True).decode("utf-8")), dtype=str,
            keep_default_na=False, na_values=[""]))
    m = fa.Matrices(recs[0])
    for s, r in zip(SETTINGS, recs):
        m.add(s.setting_id, (s.d_threshold_seconds, s.w_max_hours), r)
    m.finalise()
    return m, recs


def _expected(recs: list[pd.DataFrame]) -> tuple[list[float], list[float]]:
    summ, _ = sim.summarise(pd.concat(recs, ignore_index=True))
    by = summ.set_index("setting_id")
    ids = [s.setting_id for s in SETTINGS]
    return ([-float(by.loc[i, "carbon_pct_vs_static"]) for i in ids],
            [float(by.loc[i, "ttff_p95_h_failed"]) for i in ids])


def test_full_trace_points_equal_the_simulator_summary(replayed):
    m, recs = replayed
    s, t = m.points(np.ones(len(m.ids)))
    es, et = _expected(recs)
    assert s == pytest.approx(es, rel=1e-12, abs=1e-12)
    assert t == pytest.approx(et, rel=1e-12)


def test_bootstrap_weights_equal_an_explicit_resample(replayed):
    m, recs = replayed
    idx = np.random.default_rng(3).integers(0, len(m.ids), size=len(m.ids))
    w = np.bincount(idx, minlength=len(m.ids)).astype("float64")
    s, t = m.points(w)
    es, et = _expected([r.iloc[idx].reset_index(drop=True) for r in recs])
    assert s == pytest.approx(es, rel=1e-9, abs=1e-9)
    assert t == pytest.approx(et, rel=1e-12)


def test_a_band_mask_is_a_zero_weight(replayed):
    m, recs = replayed
    mask = np.arange(len(m.ids)) % 2 == 0
    s, t = m.points(mask.astype("float64"))
    es, et = _expected([r.loc[mask].reset_index(drop=True) for r in recs])
    assert s == pytest.approx(es, rel=1e-9, abs=1e-9)
    assert t == pytest.approx(et, rel=1e-12)


def test_oracle_trace_uses_observed_duration_only_where_accountable():
    trace = trr._trace(n=30, seed=2)
    out = fa.oracle_trace(trace)
    ok = sim.accountable_mask(trace).to_numpy()
    assert np.allclose(out.loc[ok, "d_hat_4b_seconds"], trace.loc[ok, "obs_duration_s"])
    assert (out.loc[~ok, "d_hat_4b_seconds"] == trace.loc[~ok, "d_hat_4b_seconds"]).all()
    assert set(out.loc[ok, "d_hat_4b_fallback"]) == {"oracle_observed"}
    assert (trace["d_hat_4b_fallback"] == "project").all()      # input untouched

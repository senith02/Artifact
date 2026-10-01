"""Tests for P3-T2's runner: streaming aggregation equals the P2 whole-frame path,
and the test-replay guards (DL-028 §4)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from replay import simulator as sim
from replay import validate_invariants as vi
from scheduler_core import carbon, policy

CODE_ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    for p in (CODE_ROOT, CODE_ROOT / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "run_test_replay_under_test", CODE_ROOT / "scripts" / "run_test_replay.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rt = _load_script()


def _trace(n: int = 60, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    arrival = pd.date_range("2015-01-05 00:00:00", periods=n, freq="7h", tz="UTC")
    dur = rng.gamma(2.0, 400.0, n)
    dur[3] = np.nan                                   # one unaccountable build
    t = pd.DataFrame({
        "replay_seq": 0,
        "tr_build_id": [str(1000 + i) for i in range(n)],
        "gh_project_name": ["org/a" if i % 2 else "org/b" for i in range(n)],
        "gh_is_pr": ["true" if i % 5 == 0 else "false" for i in range(n)],
        "git_branch": [("master", "feature/x", "dev", "fix/y")[i % 4] for i in range(n)],
        "arrival_utc": arrival.strftime("%Y-%m-%d %H:%M:%S+00:00"),
        "arrival_dow": arrival.dayofweek.astype("int64"),
        "arrival_hour": arrival.hour.astype("int64"),
        "d_hat_4a_seconds": rng.gamma(2.0, 400.0, n),
        "d_hat_4a_fallback": "project",
        "d_hat_4b_seconds": rng.gamma(2.0, 400.0, n),
        "d_hat_4b_fallback": "project",
        "d_hat_4b_n_history": 10,
        "p_hat": rng.uniform(0.0, 0.5, n),
        "obs_duration_s": dur,
        "y_fail": (rng.random(n) < 0.3).astype("int64"),
    })
    return sim.order_trace(t)


def _settings() -> list[sim.Setting]:
    return [sim.Setting("1_static"),
            sim.Setting("2_blanket_carbon_aware", d_threshold_seconds=0.0, w_max_hours=167.0),
            sim.Setting("3_eligibility_only", d_threshold_seconds=0.0, w_max_hours=24.0),
            sim.Setting("4b_duration_prior", d_threshold_seconds=480.0, w_max_hours=24.0),
            sim.Setting("5_se_informed_policy", d_threshold_seconds=480.0, w_max_hours=24.0),
            sim.Setting("6_risk_only_skip", tau_skip=0.0),
            sim.Setting("6_risk_only_skip", tau_skip=0.3)]


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("parts")
    trace = _trace()
    spec = policy.load_policy_spec(require_fitted=True)
    profile = carbon.load_hour_of_week_profile()
    parts = []
    for n, s in enumerate(_settings()):
        rec = sim.replay_setting(trace, s, base_spec=spec, profile=profile, p_avg_w=42.5,
                                 primary_form="4b")
        path = tmp / f"{n:04d}__{s.setting_id}.csv"
        path.write_bytes(sim.records_to_csv_bytes(rec, header=False))
        parts.append(path)
    assembled = tmp / "decisions.csv.gz"
    sim.assemble(parts, assembled)
    return trace, spec, parts, assembled


def test_streaming_summary_is_byte_identical_to_the_whole_frame_path(replayed):
    trace, spec, parts, assembled = replayed
    agg = rt.aggregate_parts(parts, _settings(), reference_ids=trace["tr_build_id"].tolist(),
                             variant=spec.stage1_variant, keep_per_build=[])
    whole_summary, whole_herding = sim.summarise(sim.load_records(assembled))
    kw = {"index": False, "lineterminator": "\n", "na_rep": ""}
    assert agg["summary"].to_csv(**kw) == whole_summary.to_csv(**kw)
    assert agg["herding"].to_csv(index=False, lineterminator="\n") == \
        whole_herding.to_csv(index=False, lineterminator="\n")


def test_streaming_audits_equal_the_whole_frame_audits(replayed):
    trace, spec, parts, assembled = replayed
    agg = rt.aggregate_parts(parts, _settings(), reference_ids=trace["tr_build_id"].tolist(),
                             variant=spec.stage1_variant, keep_per_build=[])
    records = sim.load_records(assembled)
    whole = vi.audit_frame(records, variant=spec.stage1_variant)
    assert (agg["validator"]["rows"], agg["validator"]["deferred"],
            agg["validator"]["violations"]) == (whole.rows, whole.deferred, whole.violations)
    assert agg["skip_audit"]["skipped_rows"] == sim.audit_skips(
        records, variant=spec.stage1_variant)["skipped_rows"]


def test_streaming_detects_a_different_build_order(replayed):
    trace, spec, parts, _ = replayed
    wrong = list(reversed(trace["tr_build_id"].tolist()))
    with pytest.raises(sim.SimulatorError, match="different build set"):
        rt.aggregate_parts(parts, _settings(), reference_ids=wrong,
                           variant=spec.stage1_variant, keep_per_build=[])


def test_bootstrap_points_equal_the_summary(replayed):
    trace, spec, parts, _ = replayed
    ids = [s.setting_id for s in _settings()]
    agg = rt.aggregate_parts(parts, _settings(), reference_ids=trace["tr_build_id"].tolist(),
                             variant=spec.stage1_variant, keep_per_build=ids)
    boot = rt.stats.paired_bootstrap(agg["per_build"], rt.METRIC_FNS, strategies=ids,
                                     n_resamples=10)
    check = rt.bootstrap_point_check(boot, agg["summary"])
    assert check["passed"], check


def test_five_equals_four_b_on_the_frozen_null_path(replayed):
    trace, spec, parts, _ = replayed
    agg = rt.aggregate_parts(parts, _settings(), reference_ids=trace["tr_build_id"].tolist(),
                             variant=spec.stage1_variant, keep_per_build=[])
    h = agg["identity_hash"]
    assert h["5_se_informed_policy__d480__w24"] == h["4b_duration_prior__d480__w24"]
    assert agg["action_hash"]["6_risk_only_skip__t0"] == agg["action_hash"]["1_static"]


def test_headline_ids_follow_dl_028_and_the_frozen_spec():
    grid = sim.load_sweep_grid()
    spec = policy.load_policy_spec(require_fitted=True)
    ids = rt.headline_ids(spec, grid)
    assert ids[:6] == ["1_static", "2_blanket_carbon_aware__d0__w167",
                       "3_eligibility_only__d0__w24", "4a_duration_estimator__d480__w24",
                       "4b_duration_prior__d480__w24", "5_se_informed_policy__d480__w24"]
    assert [i for i in ids if i.startswith("6_")] == [
        f"6_risk_only_skip__t{t:g}" for t in grid.tau_skip]


def test_frozen_spec_loads_with_its_certified_hash_and_grid():
    spec, digest = rt.load_frozen_spec(sim.load_sweep_grid())
    assert spec.fitted and len(digest) == 64


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #

def _rehearsal(tmp_path: Path, *, ok: bool = True, fp: str = "abc") -> Path:
    p = tmp_path / "rehearsal.json"
    p.write_text(json.dumps({"all_checks_pass": ok, "code_fingerprint": fp}), encoding="utf-8")
    return p


def _log(tmp_path: Path) -> Path:
    p = tmp_path / "log.md"
    p.write_text("### DL-099 — authorised rerun\n", encoding="utf-8")
    return p


def test_guard_requires_a_passing_rehearsal_of_the_same_code(tmp_path):
    kw = dict(sentinel=tmp_path / "s.json", rerun_under=None, log_path=_log(tmp_path))
    with pytest.raises(rt.GuardError, match="no rehearsal"):
        rt.assert_may_replay_test(fingerprint="abc", rehearsal_path=tmp_path / "x.json", **kw)
    with pytest.raises(rt.GuardError, match="did not reproduce"):
        rt.assert_may_replay_test(fingerprint="abc", rehearsal_path=_rehearsal(tmp_path, ok=False),
                                  **kw)
    with pytest.raises(rt.GuardError, match="changed since"):
        rt.assert_may_replay_test(fingerprint="zzz", rehearsal_path=_rehearsal(tmp_path), **kw)
    assert rt.assert_may_replay_test(fingerprint="abc", rehearsal_path=_rehearsal(tmp_path), **kw)


def test_same_fingerprint_rerun_is_allowed_changed_rerun_needs_a_dl(tmp_path):
    sentinel = tmp_path / "s.json"
    sentinel.write_text(json.dumps({"code_fingerprint": "abc", "opened_at_utc": "t"}),
                        encoding="utf-8")
    kw = dict(rehearsal_path=_rehearsal(tmp_path, fp="abc"), sentinel=sentinel,
              log_path=_log(tmp_path))
    assert rt.assert_may_replay_test(fingerprint="abc", rerun_under=None, **kw)
    sentinel.write_text(json.dumps({"code_fingerprint": "old", "opened_at_utc": "t"}),
                        encoding="utf-8")
    with pytest.raises(rt.GuardError, match="already replayed"):
        rt.assert_may_replay_test(fingerprint="abc", rerun_under=None, **kw)
    with pytest.raises(rt.GuardError, match="no such entry"):
        rt.assert_may_replay_test(fingerprint="abc", rerun_under="DL-123", **kw)
    assert rt.assert_may_replay_test(fingerprint="abc", rerun_under="DL-099", **kw)


def test_test_mode_refuses_a_reduced_bootstrap_budget():
    with pytest.raises(rt.GuardError, match="B = 1000"):
        rt.main(["--mode", "test", "--n-resamples", "10"])


def test_fingerprint_covers_code_spec_grid_and_artifacts():
    names = {p.name for p in rt.FINGERPRINT_FILES}
    assert {"run_test_replay.py", "simulator.py", "stats.py", "policy_spec.yaml",
            "sweep_grid.json", "energy.json", "duration_estimator.joblib",
            "xgboost__full.joblib"} <= names

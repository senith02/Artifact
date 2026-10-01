"""Tests for P3-T1: the single-arm bootstrap CI and the test-split guards.

The guards are what make "the test split is opened exactly once" a property of
the code rather than a promise: the test pass refuses to run without a passing,
full-budget calibration rehearsal of the *same* pipeline, and refuses a second
pass unless a decision-log entry authorises it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from scheduler_core import ablation_stats as ab
from scheduler_core import models

CODE_ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    """Import `scripts/evaluate_test.py` as a module (it is not on the package path)."""
    for p in (CODE_ROOT, CODE_ROOT / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "evaluate_test_under_test", CODE_ROOT / "scripts" / "evaluate_test.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


et = _load_script()


def _synthetic(n: int = 2000, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.3).astype("int64")
    p = np.clip(0.3 + 0.25 * (y - 0.3) + rng.normal(0, 0.15, n), 0.0, 1.0)
    return y, p


# --------------------------------------------------------------------------- #
# bootstrap_metric_ci
# --------------------------------------------------------------------------- #

def test_point_estimates_equal_score_split():
    y, p = _synthetic()
    out = ab.bootstrap_metric_ci(y, p, tau=0.35, n_resamples=50)
    ref = models.score_split(y, p, tau=0.35)
    for key in ("pr_auc", "roc_auc", "brier", "ece",
                "precision_at_tau", "recall_at_tau", "f1_at_tau"):
        assert out[key]["point"] == pytest.approx(ref[key], abs=1e-12), key


def test_ci_brackets_the_point_estimate():
    y, p = _synthetic()
    out = ab.bootstrap_metric_ci(y, p, tau=0.35, n_resamples=200)
    for key, rec in out.items():
        assert rec["ci_lo"] <= rec["point"] <= rec["ci_hi"], key


def test_is_deterministic_under_the_seed():
    y, p = _synthetic()
    a = ab.bootstrap_metric_ci(y, p, tau=0.35, n_resamples=50)
    b = ab.bootstrap_metric_ci(y, p, tau=0.35, n_resamples=50)
    assert a == b


def test_threshold_metrics_are_omitted_without_tau():
    y, p = _synthetic()
    out = ab.bootstrap_metric_ci(y, p, n_resamples=10)
    assert set(out) == {"pr_auc", "roc_auc", "brier", "ece"}


def test_uses_the_same_resamples_as_the_paired_delta():
    """Same seed, same draws: an arm compared with itself has a zero-width delta CI,
    and its single-arm CI equals the one computed through the paired path."""
    y, p = _synthetic()
    single = ab.bootstrap_metric_ci(y, p, n_resamples=40)
    rng = np.random.default_rng(ab.RANDOM_SEED)
    draws = []
    for _ in range(40):
        idx = rng.integers(0, len(y), size=len(y))
        draws.append(ab._metric_values(y[idx], p[idx])["pr_auc"])
    assert single["pr_auc"]["ci_lo"] == pytest.approx(float(np.quantile(draws, 0.025)))
    assert single["pr_auc"]["ci_hi"] == pytest.approx(float(np.quantile(draws, 0.975)))


def test_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        ab.bootstrap_metric_ci(np.array([0, 1]), np.array([0.1]))


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #

def _rehearsal(tmp_path: Path, *, fingerprint: str = "abc", ok: bool = True,
               n_resamples: int = ab.N_RESAMPLES) -> Path:
    path = tmp_path / "rehearsal.json"
    path.write_text(json.dumps({"all_checks_pass": ok, "n_resamples": n_resamples,
                                "fingerprint": fingerprint, "run_date": "2026-09-25"}),
                    encoding="utf-8")
    return path


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "log.md"
    path.write_text("# log\n\n### DL-099 — authorised rerun\n", encoding="utf-8")
    return path


def test_guard_passes_with_a_matching_full_budget_rehearsal(tmp_path):
    rec = et.assert_may_open_test(fingerprint="abc", rehearsal_path=_rehearsal(tmp_path),
                                  sentinel=tmp_path / "opened.json", rerun_under=None,
                                  log_path=_log(tmp_path))
    assert rec["all_checks_pass"] is True


def test_guard_refuses_without_a_rehearsal(tmp_path):
    with pytest.raises(et.GuardError, match="no rehearsal"):
        et.assert_may_open_test(fingerprint="abc", rehearsal_path=tmp_path / "none.json",
                                sentinel=tmp_path / "opened.json", rerun_under=None,
                                log_path=_log(tmp_path))


def test_guard_refuses_a_failed_rehearsal(tmp_path):
    with pytest.raises(et.GuardError, match="did not reproduce"):
        et.assert_may_open_test(fingerprint="abc",
                                rehearsal_path=_rehearsal(tmp_path, ok=False),
                                sentinel=tmp_path / "opened.json", rerun_under=None,
                                log_path=_log(tmp_path))


def test_guard_refuses_a_smoke_budget_rehearsal(tmp_path):
    with pytest.raises(et.GuardError, match="B = 20"):
        et.assert_may_open_test(fingerprint="abc",
                                rehearsal_path=_rehearsal(tmp_path, n_resamples=20),
                                sentinel=tmp_path / "opened.json", rerun_under=None,
                                log_path=_log(tmp_path))


def test_guard_refuses_changed_code_or_artifacts(tmp_path):
    with pytest.raises(et.GuardError, match="changed since"):
        et.assert_may_open_test(fingerprint="different",
                                rehearsal_path=_rehearsal(tmp_path),
                                sentinel=tmp_path / "opened.json", rerun_under=None,
                                log_path=_log(tmp_path))


def test_guard_refuses_a_second_pass(tmp_path):
    sentinel = tmp_path / "opened.json"
    sentinel.write_text(json.dumps({"opened_at_utc": "2026-09-25T00:00:00+00:00"}),
                        encoding="utf-8")
    with pytest.raises(et.GuardError, match="already opened"):
        et.assert_may_open_test(fingerprint="abc", rehearsal_path=_rehearsal(tmp_path),
                                sentinel=sentinel, rerun_under=None, log_path=_log(tmp_path))


def test_second_pass_needs_a_real_dl_entry(tmp_path):
    sentinel = tmp_path / "opened.json"
    sentinel.write_text(json.dumps({"opened_at_utc": "x"}), encoding="utf-8")
    with pytest.raises(et.GuardError, match="no such entry"):
        et.assert_may_open_test(fingerprint="abc", rehearsal_path=_rehearsal(tmp_path),
                                sentinel=sentinel, rerun_under="DL-123",
                                log_path=_log(tmp_path))
    rec = et.assert_may_open_test(fingerprint="abc", rehearsal_path=_rehearsal(tmp_path),
                                  sentinel=sentinel, rerun_under="DL-099",
                                  log_path=_log(tmp_path))
    assert rec["all_checks_pass"] is True


def test_cli_refuses_test_without_the_explicit_flag():
    with pytest.raises(et.GuardError, match="--open-test-split"):
        et.main(["--split", "test"])


def test_cli_refuses_a_reduced_budget_on_test():
    with pytest.raises(et.GuardError, match="B = 1000"):
        et.main(["--split", "test", "--open-test-split", "--n-resamples", "20"])


def test_fingerprint_covers_code_artifacts_and_split():
    names = {p.name for p in et.FINGERPRINT_FILES}
    assert {"evaluate_test.py", "models.py", "ablation_stats.py",
            "duration_estimator.joblib", "split_assignment.csv"} <= names
    assert sum(n.endswith(".joblib") for n in names) == 1 + len(et.ALL_ARMS)
    assert et.pipeline_fingerprint() == et.pipeline_fingerprint()


def test_nan_aware_equality_for_degenerate_shap_records():
    a = {"rho": float("nan"), "monotone": False, "degenerate": True}
    b = {"rho": float("nan"), "monotone": False, "degenerate": True}
    assert et.same(a, b)
    assert not et.same({"rho": 0.1}, {"rho": 0.2})


def test_evaluates_twelve_frozen_arms():
    assert len(et.ALL_ARMS) == 12
    assert et.ALL_ARMS[:6] == ("xgboost:control", "xgboost:full", "logreg:control",
                               "logreg:full", "random_forest:control", "random_forest:full")

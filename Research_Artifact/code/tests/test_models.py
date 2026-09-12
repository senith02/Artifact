"""Tests for the arm/training machinery (P1-T5).

The DoD's leakage requirement here is narrower than P1-T4's but no less
load-bearing: the arms are the last place an outcome column, a test project, or
a silently-refitted control could enter the study.

* **arm contract** — `control` is `{d̂}`, `full` is `{d̂ + all 28}`, and neither
  can be built from a frame carrying a blocklisted column;
* **frozen control** — `attach_d_hat` refuses an estimator whose `fit_id` is not
  the one P1-T4 froze, and refuses one with no primary form;
* **identical procedure** — the tuning fold is the temporally-latest 20% and is
  the same for every arm, so an arm comparison measures the feature set;
* **§5 machinery** — ECE, τ, and the calibrator rule behave as the protocol
  defines them, checked against hand-computable cases.
"""

import numpy as np
import pandas as pd
import pytest

from scheduler_core import duration_estimator as de
from scheduler_core import features, models


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _frame(n: int = 400, *, n_projects: int = 8, seed: int = 0) -> pd.DataFrame:
    """A build frame carrying the 28 features, `d̂`, keys and a label."""
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2014-01-01", tz="UTC")
    rows = []
    for i in range(n):
        p = i % n_projects
        rows.append({
            "tr_build_id": f"b{i:05d}",
            "gh_project_name": f"org/p{p:02d}",
            "gh_build_started_at": (base + pd.Timedelta(hours=i)
                                    ).strftime("%Y-%m-%d %H:%M:%S"),
            "lang": "ruby" if p % 2 else "java",
        })
    out = pd.DataFrame(rows)
    for j, name in enumerate(features.FEATURES):
        if name in out.columns:
            continue
        out[name] = rng.normal(j, 1.0, size=n)
    out[models.D_HAT_COLUMN] = rng.normal(6.0, 1.0, size=n)
    return out


def _labels(frame: pd.DataFrame, seed: int = 1) -> pd.Series:
    """A label with real signal in `d̂` so PR-AUC is not degenerate."""
    rng = np.random.default_rng(seed)
    logit = 0.9 * (frame[models.D_HAT_COLUMN] - 6.0) - 1.0
    p = 1 / (1 + np.exp(-logit))
    return pd.Series((rng.random(len(frame)) < p).astype("int64"),
                     index=frame.index)


LEVELS = ("java", "ruby")


# --------------------------------------------------------------------------- #
# Arm contract
# --------------------------------------------------------------------------- #

def test_arms_are_incremental_over_the_control():
    """§A1.3: every arm contains d̂; `full` is the control plus all 28."""
    assert models.ARMS["control"] == (models.D_HAT_COLUMN,)
    assert models.ARMS["full"][0] == models.D_HAT_COLUMN
    assert set(models.ARMS["full"][1:]) == set(features.FEATURES)
    assert len(models.ARMS["full"]) == 29
    for arm, cols in models.ARMS.items():
        assert models.D_HAT_COLUMN in cols, arm


def test_control_design_matrix_is_exactly_one_column():
    design = models.design_matrix(_frame(20), "control", lang_levels=LEVELS)
    assert list(design.columns) == [models.D_HAT_COLUMN]


def test_full_design_matrix_is_d_hat_plus_27_numeric_plus_one_hot_lang():
    design = models.design_matrix(_frame(20), "full", lang_levels=LEVELS)
    numeric = [f for f in features.FEATURES
               if f not in features.CATEGORICAL_FEATURES]
    assert set(design.columns) == (
        {models.D_HAT_COLUMN} | set(numeric) | {f"lang={lv}" for lv in LEVELS})
    assert "lang" not in design.columns


def test_design_matrix_rejects_a_blocklisted_column_on_the_frame():
    frame = _frame(20).assign(tr_duration=1.0)
    with pytest.raises(features.LeakageError):
        models.design_matrix(frame, "full", lang_levels=LEVELS)


def test_design_matrix_rejects_an_unknown_arm():
    with pytest.raises(KeyError):
        models.design_matrix(_frame(20), "everything", lang_levels=LEVELS)


def test_design_matrix_reports_a_missing_control_column():
    frame = _frame(20).drop(columns=[models.D_HAT_COLUMN])
    with pytest.raises(KeyError, match=models.D_HAT_COLUMN):
        models.design_matrix(frame, "control", lang_levels=LEVELS)


# --------------------------------------------------------------------------- #
# The frozen duration control may not be silently replaced
# --------------------------------------------------------------------------- #

def _tiny_estimator(split: str = "train"):
    base = pd.Timestamp("2014-01-01", tz="UTC")
    rows, durations = [], []
    for p in range(3):
        for i in range(20):
            rows.append({
                "tr_build_id": f"{p}{i:03d}",
                "gh_project_name": f"org/p{p}",
                "gh_build_started_at": (base + pd.Timedelta(hours=i + 24 * p)
                                        ).strftime("%Y-%m-%d %H:%M:%S"),
                "lang": "ruby",
            })
            durations.append(60.0 * (p + 1) + i)
    frame = pd.DataFrame(rows)
    rng = np.random.default_rng(0)
    for j, name in enumerate(features.FEATURES):
        if name not in frame.columns:
            frame[name] = rng.normal(j, 1.0, size=len(frame))
    frame = frame[list(features.KEY_COLUMNS) + list(features.FEATURES)]
    assignment = {f"org/p{p}": split for p in range(3)}
    est = de.DurationEstimator(n_iter=1).fit(
        frame, pd.Series(durations), split_assignment=assignment)
    est.primary_form = "4b"
    return est, frame, pd.Series(durations)


def test_attach_d_hat_rejects_an_estimator_with_no_primary_form():
    est, frame, durations = _tiny_estimator()
    est.primary_form = None
    keys = frame[list(features.KEY_COLUMNS)]
    with pytest.raises(models.ArmLeakageError, match="no primary_form"):
        models.attach_d_hat(frame, keys, durations, estimator=est)


def test_attach_d_hat_rejects_a_control_that_is_not_the_frozen_one():
    """A refitted control would silently move the null RQ2 is measured against."""
    est, frame, durations = _tiny_estimator()
    keys = frame[list(features.KEY_COLUMNS)]
    with pytest.raises(models.ArmLeakageError, match="not the frozen"):
        models.attach_d_hat(frame, keys, durations, estimator=est,
                            expected_fit_id="deadbeefdeadbeef")


def test_attach_d_hat_accepts_the_matching_fit_id_and_returns_one_value_per_build():
    est, frame, durations = _tiny_estimator()
    keys = frame[list(features.KEY_COLUMNS)]
    d_hat = models.attach_d_hat(frame, keys, durations, estimator=est,
                                expected_fit_id=est.provenance["fit_id"])
    assert len(d_hat) == len(frame)
    assert np.isfinite(d_hat).all()
    assert d_hat.name == models.D_HAT_COLUMN


def test_attach_d_hat_runs_the_causal_history_guard():
    """The P1-T4 guard is re-run here — this is d̂'s first consumer."""
    est, frame, durations = _tiny_estimator()
    keys = frame[list(features.KEY_COLUMNS)].copy()
    # Collapse every timestamp: now every build is tied with every other, so a
    # correct causal history must give all of them n_history = 0.
    keys["gh_build_started_at"] = "2014-01-01 00:00:00"
    d_hat = models.attach_d_hat(frame, keys, durations, estimator=est,
                                expected_fit_id=est.provenance["fit_id"])
    assert np.isfinite(d_hat).all()      # falls to the language/global rung


# --------------------------------------------------------------------------- #
# Tuning procedure (§3)
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def trained_pair():
    frame = _frame(600, seed=3)
    y = _labels(frame, seed=4)
    started = frame["gh_build_started_at"]
    control = models.train_arm("logreg", "control", frame, y, started,
                               lang_levels=LEVELS, n_iter=2)
    full = models.train_arm("logreg", "full", frame, y, started,
                            lang_levels=LEVELS, n_iter=2)
    return frame, y, control, full


def test_internal_validation_fold_is_the_latest_20_percent(trained_pair):
    _, _, control, _ = trained_pair
    iv = control.provenance["internal_validation"]
    assert iv["share"] == models.INTERNAL_VAL_SHARE
    assert iv["n_fit"] + iv["n_val"] == control.provenance["n_train"]
    assert iv["n_val"] == round(0.20 * control.provenance["n_train"])


def test_both_arms_get_the_identical_tuning_procedure(trained_pair):
    """Only the feature set may differ, or the comparison measures the wrong thing."""
    _, _, control, full = trained_pair
    a, b = control.provenance["internal_validation"], full.provenance["internal_validation"]
    assert a == b
    assert control.provenance["n_train"] == full.provenance["n_train"]
    assert control.provenance["n_search_candidates"] == \
           full.provenance["n_search_candidates"]
    assert control.design_columns != full.design_columns


def test_the_search_is_seeded_and_reproducible():
    frame = _frame(300, seed=5)
    y = _labels(frame, seed=6)
    started = frame["gh_build_started_at"]
    a = models.train_arm("logreg", "control", frame, y, started,
                         lang_levels=LEVELS, n_iter=3)
    b = models.train_arm("logreg", "control", frame, y, started,
                         lang_levels=LEVELS, n_iter=3)
    assert a.best_params == b.best_params
    assert [c["params"] for c in a.search_trace] == \
           [c["params"] for c in b.search_trace]


def test_search_trace_records_every_candidate(trained_pair):
    _, _, control, _ = trained_pair
    assert len(control.search_trace) == control.provenance["n_search_candidates"]
    assert all("internal_val_pr_auc" in c for c in control.search_trace)


def test_sample_params_stays_inside_the_declared_ranges():
    """DL-018's spaces are a contract; a drifted range invalidates the run."""
    rng = np.random.default_rng(0)
    for _ in range(200):
        x = models.sample_params("xgboost", rng, pos_weight=3.0)
        assert 100 <= x["n_estimators"] <= 800
        assert 3 <= x["max_depth"] <= 10
        assert 0.01 <= x["learning_rate"] <= 0.30
        assert 0.6 <= x["subsample"] <= 1.0
        assert 0.6 <= x["colsample_bytree"] <= 1.0
        assert 1 <= x["min_child_weight"] <= 20
        assert 0.0 <= x["gamma"] <= 5.0
        assert 1.5 <= x["scale_pos_weight"] <= 6.0
        r = models.sample_params("random_forest", rng, pos_weight=3.0)
        assert 100 <= r["n_estimators"] <= 300
        assert 4 <= r["max_depth"] <= 16
        assert 10 <= r["min_samples_leaf"] <= 200
        assert r["max_features"] in ("sqrt", "log2")
        assert 1e-4 <= models.sample_params("logreg", rng, pos_weight=3.0)["C"] <= 1e2


def test_every_algorithm_handles_imbalance():
    """Spec §3.5: all three must weight the positive class, or §4 is not fair."""
    xgb = models.build_estimator(
        "xgboost", models.sample_params("xgboost", np.random.default_rng(0),
                                        pos_weight=3.0))
    assert xgb.get_params()["scale_pos_weight"] > 0
    for algorithm in ("logreg", "random_forest"):
        pipe = models.build_estimator(
            algorithm, models.sample_params(algorithm, np.random.default_rng(0),
                                            pos_weight=3.0))
        assert pipe.named_steps["clf"].class_weight == "balanced"
        assert "impute" in pipe.named_steps


# --------------------------------------------------------------------------- #
# §5 metric machinery
# --------------------------------------------------------------------------- #

def test_ece_is_zero_for_a_perfectly_calibrated_set():
    p = np.repeat([0.05, 0.25, 0.55, 0.85], 100)
    rng = np.random.default_rng(0)
    y = np.concatenate([
        (np.arange(100) < round(100 * v)).astype(float) for v in (0.05, 0.25, 0.55, 0.85)
    ])
    assert models.expected_calibration_error(y, p) == pytest.approx(0.0, abs=1e-12)
    rng.shuffle(y)  # order must not matter


def test_ece_matches_a_hand_computed_two_bin_case():
    # bin 0 ([0.0,0.1)): p = 0.0, observed 0.5 -> |0.5-0.0| * 2/4 = 0.25
    # bin 9 ([0.9,1.0]): p = 1.0, observed 0.5 -> |0.5-1.0| * 2/4 = 0.25
    p = np.array([0.0, 0.0, 1.0, 1.0])
    y = np.array([0.0, 1.0, 0.0, 1.0])
    assert models.expected_calibration_error(y, p) == pytest.approx(0.5)


def test_ece_puts_probability_one_in_the_last_bin_not_an_overflow_bin():
    p = np.ones(10)
    y = np.ones(10)
    assert models.expected_calibration_error(y, p) == pytest.approx(0.0)


def test_tau_maximises_f1_and_breaks_ties_toward_recall():
    y = np.array([0, 0, 1, 1, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9, 0.95])
    out = models.threshold_maximising_f1(y, p)
    assert out["f1"] == pytest.approx(1.0)
    assert out["tau"] <= 0.8            # the lowest τ achieving the maximum

def test_reliability_bins_cover_every_row_exactly_once():
    rng = np.random.default_rng(0)
    p = rng.random(500)
    y = (rng.random(500) < p).astype(float)
    bins = models.reliability_bins(y, p)
    assert len(bins) == models.ECE_BINS
    assert int(bins["n"].sum()) == 500


def test_score_split_reports_the_full_section_5_metric_set():
    rng = np.random.default_rng(0)
    p = rng.random(300)
    y = (rng.random(300) < p).astype("int64")
    out = models.score_split(y, p, tau=0.5)
    assert set(out) >= {"pr_auc", "roc_auc", "brier", "ece", "tau",
                        "precision_at_tau", "recall_at_tau", "f1_at_tau",
                        "n", "positives", "base_rate"}


# --------------------------------------------------------------------------- #
# Calibration (§5) + persistence
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def calibrated(trained_pair):
    frame, y, control, _ = trained_pair
    calib = _frame(300, seed=7)
    y_calib = _labels(calib, seed=8)
    choice = models.calibrate(control, calib, y_calib)
    return control, calib, y_calib, choice


def test_calibrator_choice_fits_both_and_keeps_the_lower_brier(calibrated):
    control, _, _, choice = calibrated
    assert set(choice["comparison"]) == set(models.CALIBRATORS)
    briers = {k: v["brier"] for k, v in choice["comparison"].items()}
    assert choice["chosen"] == min(briers, key=briers.get)
    assert control.calibrator_kind == choice["chosen"]


def test_tau_is_frozen_on_the_calibration_split(calibrated):
    control, _, _, choice = calibrated
    assert control.tau == choice["tau_selection"]["tau"]
    assert 0.0 <= control.tau <= 1.0


def test_calibrated_probabilities_are_valid(calibrated):
    control, calib, _, _ = calibrated
    p = control.predict_proba(calib)
    assert len(p) == len(calib)
    assert ((p >= 0) & (p <= 1)).all()


def test_out_of_fold_diagnostic_is_project_grouped(calibrated):
    control, calib, y_calib, _ = calibrated
    oof = models.out_of_fold_calibration(control, calib, y_calib,
                                         calib["gh_project_name"], n_splits=4)
    assert oof["n"] > 0
    assert "brier" in oof and "ece" in oof


def test_out_of_fold_diagnostic_does_not_mutate_the_frozen_choice(calibrated):
    """It is a diagnostic. It must not move the calibrator, τ, or the model."""
    control, calib, y_calib, _ = calibrated
    before = (control.calibrator_kind, control.tau,
              control.predict_proba(calib).copy())
    models.out_of_fold_calibration(control, calib, y_calib,
                                   calib["gh_project_name"], n_splits=4)
    after = (control.calibrator_kind, control.tau, control.predict_proba(calib))
    assert before[0] == after[0]
    assert before[1] == after[1]
    assert np.array_equal(before[2], after[2])


def test_persisted_arm_reloads_and_reproduces_predictions(calibrated, tmp_path):
    control, calib, _, _ = calibrated
    before = control.predict_proba(calib)
    path = models.save_arm(control, tmp_path)
    reloaded = models.load_arm(path)
    assert np.array_equal(reloaded.predict_proba(calib), before)
    assert reloaded.tau == control.tau
    assert reloaded.calibrator_kind == control.calibrator_kind
    assert reloaded.fit_id() == control.fit_id()


def test_random_forest_predictions_are_bitwise_reproducible(tmp_path):
    """RF's threaded probability accumulation would otherwise wobble in the last
    bits, which is not good enough for a persisted research artifact (R8)."""
    frame = _frame(300, seed=11)
    y = _labels(frame, seed=12)
    arm = models.train_arm("random_forest", "control", frame, y,
                           frame["gh_build_started_at"],
                           lang_levels=LEVELS, n_iter=1)
    assert arm.base_model.named_steps["clf"].n_jobs == 1
    calib = _frame(150, seed=13)
    models.calibrate(arm, calib, _labels(calib, seed=14))

    first = arm.predict_proba(calib)
    assert np.array_equal(first, arm.predict_proba(calib))       # stable
    reloaded = models.load_arm(models.save_arm(arm, tmp_path))
    assert np.array_equal(first, reloaded.predict_proba(calib))  # and persisted


def test_predicting_from_an_uncalibrated_arm_is_refused():
    frame = _frame(200, seed=9)
    y = _labels(frame, seed=10)
    arm = models.train_arm("logreg", "control", frame, y,
                           frame["gh_build_started_at"],
                           lang_levels=LEVELS, n_iter=1)
    with pytest.raises(RuntimeError, match="not calibrated"):
        arm.predict_proba(frame)

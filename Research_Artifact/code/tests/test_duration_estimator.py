"""Tests for the commit-time duration control ``d̂`` (P1-T4).

``context/duration_control_spec.md`` §7 names five tests, and they are the five
sections below. T2 and T2b are the two halves of eval_protocol A1.1(ii): a
temporal cut-off can only bind **mechanism 2** (within-project online state) and
a split boundary can only bind **mechanism 1** (fitted parameters), so one
combined test would leave one of them unproven (DL-014 §3).

* **T1** blocklist assertion on the estimator's own matrix, incl. a
  duration-specific negative test;
* **T2** temporal test — only builds that had *finished* before ``t_b`` enter
  the window (DL-034), and the cut-off really binds;
* **T2b** split test — train-only fitting really binds;
* **T3** negative fixture — a deliberately leaky history (``≤ t_b``) is
  *rejected*, so the tests can actually fail;
* **T4** round-trip — a persisted estimator reproduces ``d̂`` exactly;
* **T5** totality — every build gets a finite, positive ``d̂`` and a rung.
"""

import numpy as np
import pandas as pd
import pytest

from scheduler_core import duration_estimator as de
from scheduler_core import features


# --------------------------------------------------------------------------- #
# Fixtures — a synthetic build table carrying the full 28-feature contract
# --------------------------------------------------------------------------- #

def _feature_frame(rows: list[dict]) -> pd.DataFrame:
    """A `build_feature_matrix`-shaped frame: keys + all 28 features.

    Every feature is present so the leakage assertions and the design matrix see
    the real contract; the values are arbitrary but deterministic.
    """
    out = pd.DataFrame(rows)
    rng = np.random.default_rng(0)
    for i, name in enumerate(features.FEATURES):
        if name in out.columns:
            continue
        if name in features.CATEGORICAL_FEATURES:
            out[name] = "ruby"
        else:
            out[name] = rng.normal(10 + i, 2.0, size=len(out))
    key_cols = [c for c in features.KEY_COLUMNS if c in out.columns]
    return out[key_cols + list(features.FEATURES)]


def _synthetic(n_projects: int = 12, per: int = 40, *, split: str = "train"):
    """Return (feature_frame, durations, split_assignment).

    Duration is a deterministic function of two features plus a per-project
    offset, so both forms have something real to learn and ④b's project prior is
    genuinely informative.
    """
    base = pd.Timestamp("2014-01-01", tz="UTC")
    rows, durations = [], []
    for p in range(n_projects):
        project = f"org/p{p:02d}"
        for i in range(per):
            churn = 5.0 + (i % 7) * 3.0
            sloc = 1000.0 * (p + 1)
            rows.append({
                "tr_build_id": f"{p:02d}{i:03d}",
                "gh_project_name": project,
                "gh_build_started_at": (base + pd.Timedelta(hours=i + 24 * p)
                                        ).strftime("%Y-%m-%d %H:%M:%S"),
                "src_churn": churn,
                "sloc": sloc,
                "lang": "ruby" if p % 2 == 0 else "java",
            })
            durations.append(60.0 * (p + 1) + 4.0 * churn + (i % 5))
    frame = _feature_frame(rows)
    assignment = {f"org/p{p:02d}": split for p in range(n_projects)}
    return frame, pd.Series(durations, index=frame.index), assignment


@pytest.fixture(scope="module")
def fitted():
    """One fitted estimator shared across tests — the search is the slow part."""
    frame, durations, assignment = _synthetic()
    est = de.DurationEstimator(n_iter=3).fit(
        frame, durations, split_assignment=assignment)
    return est, frame, durations, assignment


def _history(frame: pd.DataFrame, durations: pd.Series, **kw) -> pd.DataFrame:
    return de.causal_project_history(frame, durations, **kw)


# --------------------------------------------------------------------------- #
# T1 — blocklist assertion on the estimator's own matrix (A1.1(i))
# --------------------------------------------------------------------------- #

def test_t1_fit_rejects_a_blocklisted_column_on_the_frame():
    """T1: a blocklisted column riding on the feature frame must raise."""
    frame, durations, assignment = _synthetic(n_projects=3, per=10)
    leaky = frame.assign(tr_log_buildduration="123")
    with pytest.raises(features.LeakageError):
        de.DurationEstimator(n_iter=1).fit(
            leaky, durations, split_assignment=assignment)


def test_t1_injecting_tr_duration_into_the_input_frame_raises():
    """T1 (duration-specific negative test): the estimand cannot be an input."""
    frame, durations, assignment = _synthetic(n_projects=3, per=10)
    leaky = frame.assign(tr_duration=durations.to_numpy())
    with pytest.raises(features.LeakageError):
        de.DurationEstimator(n_iter=1).fit(
            leaky, durations, split_assignment=assignment)


def test_t1_design_matrix_also_refuses_a_leaky_frame_at_scoring_time(fitted):
    """T1: the assertion guards scoring too, not only fitting."""
    est, frame, durations, _ = fitted
    with pytest.raises(features.LeakageError):
        est.design_matrix(frame.assign(tr_duration=durations.to_numpy()))


def test_t1_design_matrix_holds_only_the_28_feature_contract(fitted):
    """The matrix is 27 numeric features + one-hot lang. Nothing else."""
    est, frame, _, _ = fitted
    design = est.design_matrix(frame)
    numeric = [f for f in features.FEATURES
               if f not in features.CATEGORICAL_FEATURES]
    expected = set(numeric) | {f"lang={lv}" for lv in est.lang_levels}
    assert set(design.columns) == expected
    assert not any(features.is_blocklisted(c) for c in design.columns)


# --------------------------------------------------------------------------- #
# T2 — the temporal cut-off binds (A1.1(ii), mechanism 2)
# --------------------------------------------------------------------------- #

def test_t2_future_builds_do_not_change_d_hat_under_the_shipped_path():
    """T2: injecting later builds must leave every earlier build's d̂ untouched."""
    frame, durations, _ = _synthetic(n_projects=2, per=10)
    base = _history(frame, durations)

    future = frame.iloc[:2].copy()
    future["tr_build_id"] = ["zz1", "zz2"]
    future["gh_build_started_at"] = "2030-01-01 00:00:00"
    extended = pd.concat([frame, future], ignore_index=True)
    extended_durations = pd.concat(
        [durations, pd.Series([999_999.0, 999_999.0])], ignore_index=True)

    after = _history(extended, extended_durations).iloc[: len(frame)]
    pd.testing.assert_series_equal(
        base["hist_median_log1p"], after["hist_median_log1p"].reset_index(drop=True),
        check_names=False)
    assert base["n_history"].tolist() == after["n_history"].tolist()


def test_t2_the_same_injection_does_change_d_hat_when_wrongly_admitted():
    """T2 (the other half): if the cut-off is *not* applied the answer moves.

    A no-op here would mean the temporal test proves nothing — the fixture has
    to be capable of shifting the estimate.
    """
    frame, durations, _ = _synthetic(n_projects=1, per=10)
    causal = _history(frame, durations)

    inflated = durations.copy()
    inflated.iloc[-1] = 999_999.0
    admitted = _history(frame, inflated, strict=False)
    assert not np.allclose(
        causal["hist_median_log1p"].to_numpy(dtype="float64")[1:],
        admitted["hist_median_log1p"].to_numpy(dtype="float64")[1:],
        equal_nan=True,
    )


def test_t2_a_whole_project_median_would_move_when_the_future_is_injected():
    """T2, stated the way spec §3.2 forbids it.

    The classic version of this mistake is a per-project median computed over
    the whole project and broadcast back across its rows. Injecting later builds
    moves that number for **every** build including the earliest — which is
    exactly what the causal path must not do (and, above, does not).
    """
    frame, durations, _ = _synthetic(n_projects=1, per=10)
    y = de.to_log1p(durations)
    broadcast_before = float(y.median())

    inflated = pd.concat([durations, pd.Series([999_999.0, 999_999.0])],
                         ignore_index=True)
    broadcast_after = float(de.to_log1p(inflated).median())

    assert broadcast_before != broadcast_after     # the leak is detectable …
    causal = _history(frame, durations)["hist_median_log1p"]
    assert np.isnan(causal.iloc[0])                # … and the shipped path has
    assert causal.iloc[-1] != broadcast_before     #     no whole-project view


def test_t2_ties_are_excluded_from_history():
    """A same-second sibling is not knowable before b starts (spec §2)."""
    frame, durations, _ = _synthetic(n_projects=1, per=4)
    frame = frame.copy()
    frame["gh_build_started_at"] = ["2014-01-01 00:00:00", "2014-01-01 01:00:00",
                                    "2014-01-01 01:00:00", "2014-01-01 02:00:00"]
    hist = _history(frame, durations)
    # The two tied builds see only the first build — the same history, not
    # each other.
    assert hist["n_history"].tolist() == [0, 1, 1, 3]
    assert hist["hist_median_log1p"].iloc[1] == hist["hist_median_log1p"].iloc[2]


def test_t2_first_build_of_every_project_has_no_history():
    frame, durations, _ = _synthetic(n_projects=5, per=6)
    hist = _history(frame, durations)
    first = frame.groupby("gh_project_name")["gh_build_started_at"].transform("min")
    is_first = frame["gh_build_started_at"] == first
    assert (hist.loc[is_first.to_numpy(), "n_history"] == 0).all()


def test_t2_history_matches_a_brute_force_recomputation():
    """The vectorised path must agree with the obvious O(n²) definition."""
    frame, durations, _ = _synthetic(n_projects=3, per=15)
    hist = _history(frame, durations)
    ts = features.parse_started_at(frame["gh_build_started_at"])
    y = de.to_log1p(durations)
    for i in range(len(frame)):
        earlier = ((frame["gh_project_name"] == frame["gh_project_name"].iloc[i])
                   & (ts < ts.iloc[i]) & y.notna())
        assert hist["n_history"].iloc[i] == int(earlier.sum())
        if earlier.any():
            assert hist["hist_median_log1p"].iloc[i] == pytest.approx(
                float(y[earlier.to_numpy()].median()))
        else:
            assert np.isnan(hist["hist_median_log1p"].iloc[i])


def test_t2_trailing_window_sensitivity_reads_only_the_last_k_builds():
    """§6.3(4)'s declared sensitivity — secondary, but it must be correct."""
    frame, durations, _ = _synthetic(n_projects=1, per=12)
    hist = _history(frame, durations, window=3)
    assert hist["n_history"].tolist() == [0, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3]


# --------------------------------------------------------------------------- #
# T2 (DL-034) — a build that is still running is not history yet
# --------------------------------------------------------------------------- #

def _timed(starts: list[str], durations_s: list[float], project: str = "org/p00"):
    """One project's builds at explicit start times, with explicit durations."""
    rows = [{"tr_build_id": f"b{i}", "gh_project_name": project, "gh_build_started_at": s,
             "lang": "ruby"} for i, s in enumerate(starts)]
    frame = _feature_frame(rows)
    return frame, pd.Series(durations_s, index=frame.index, dtype="float64")


def test_t2_a_build_still_running_at_arrival_is_excluded():
    """A (00:00, 2 h) is still running when B arrives at 01:00; C at 03:00 sees both."""
    frame, durations = _timed(["2014-01-01 00:00:00", "2014-01-01 01:00:00",
                               "2014-01-01 03:00:00"], [7200.0, 600.0, 300.0])
    hist = _history(frame, durations)
    assert hist["n_history"].tolist() == [0, 0, 2]
    assert np.isnan(hist["hist_median_log1p"].iloc[1])
    assert hist["hist_median_log1p"].iloc[2] == pytest.approx(
        float(np.median(np.log1p([7200.0, 600.0]))))
    de.assert_history_is_causal(frame, hist, durations)


def test_t2_finishing_exactly_at_arrival_is_not_yet_history():
    """The rule is strict: start + duration must be < t_b, not ≤."""
    frame, durations = _timed(["2014-01-01 00:00:00", "2014-01-01 01:00:00",
                               "2014-01-01 01:00:01"], [3600.0, 60.0, 60.0])
    hist = _history(frame, durations)
    assert hist["n_history"].tolist() == [0, 0, 1]


def test_t2_the_superseded_start_rule_admits_the_running_build_and_the_guard_rejects_it():
    """`availability="started"` reproduces the pre-DL-034 rule; check 3 must catch it."""
    frame, durations = _timed(["2014-01-01 00:00:00", "2014-01-01 01:00:00",
                               "2014-01-01 03:00:00"], [7200.0, 600.0, 300.0])
    started = _history(frame, durations, availability="started")
    assert started["n_history"].tolist() == [0, 1, 2]       # B counted A while A ran
    with pytest.raises(de.DurationLeakageError, match="still running"):
        de.assert_history_is_causal(frame, started, durations)


def test_t2_without_overlap_both_rules_agree_exactly():
    """On the synthetic fixture no run outlasts the gap to the next, so DL-034 changes nothing."""
    frame, durations, _ = _synthetic(n_projects=4, per=15)
    done = _history(frame, durations)
    started = _history(frame, durations, availability="started")
    assert done["n_history"].tolist() == started["n_history"].tolist()
    np.testing.assert_array_equal(done["hist_median_log1p"].to_numpy(),
                                  started["hist_median_log1p"].to_numpy())


def test_t2_completed_history_matches_a_brute_force_recomputation_with_overlaps():
    """The vectorised DL-034 path must agree with the obvious O(n²) definition, on data
    where runs genuinely overlap, ties exist and some labels are unusable."""
    rng = np.random.default_rng(7)
    rows, durs = [], []
    base = pd.Timestamp("2014-01-01", tz="UTC")
    for p in range(3):
        offsets = np.sort(rng.integers(0, 6 * 3600, size=25))
        offsets[5] = offsets[4]                                 # a tie
        for i, off in enumerate(offsets):
            rows.append({"tr_build_id": f"{p}-{i}", "gh_project_name": f"org/q{p}",
                         "gh_build_started_at": (base + pd.Timedelta(seconds=int(off))
                                                 ).strftime("%Y-%m-%d %H:%M:%S"),
                         "lang": "ruby"})
            durs.append(float(rng.integers(60, 5400)) if i % 9 else np.nan)
    frame = _feature_frame(rows)
    durations = pd.Series(durs, index=frame.index, dtype="float64")
    hist = _history(frame, durations)
    ts = features.parse_started_at(frame["gh_build_started_at"])
    end = ts + pd.to_timedelta(durations, unit="s")
    y = de.to_log1p(durations)
    for i in range(len(frame)):
        done = ((frame["gh_project_name"] == frame["gh_project_name"].iloc[i])
                & y.notna() & (end < ts.iloc[i]))
        assert hist["n_history"].iloc[i] == int(done.sum())
        if done.any():
            assert hist["hist_median_log1p"].iloc[i] == pytest.approx(
                float(y[done.to_numpy()].median()))
        else:
            assert np.isnan(hist["hist_median_log1p"].iloc[i])
    de.assert_history_is_causal(frame, hist, durations)
    started = _history(frame, durations, availability="started")
    assert (started["n_history"] > hist["n_history"]).any()   # the fixture really overlaps


def test_t2_trailing_window_counts_the_most_recently_finished_builds():
    """With overlap, the trailing window is ordered by finish time, not start time."""
    # A starts first but finishes last; at D's arrival the 2 most recently finished
    # labelled builds are A and C, not B and C.
    frame, durations = _timed(["2014-01-01 00:00:00", "2014-01-01 00:10:00",
                               "2014-01-01 00:20:00", "2014-01-01 02:00:00"],
                              [6000.0, 60.0, 600.0, 60.0])
    hist = _history(frame, durations, window=2)
    assert hist["n_history"].tolist() == [0, 0, 1, 2]
    assert hist["hist_median_log1p"].iloc[3] == pytest.approx(
        float(np.median(np.log1p([600.0, 6000.0]))))


def test_t2_an_unknown_availability_rule_is_refused():
    frame, durations = _timed(["2014-01-01 00:00:00"], [60.0])
    with pytest.raises(ValueError, match="availability"):
        _history(frame, durations, availability="queued")


# --------------------------------------------------------------------------- #
# T2b — the split boundary binds (A1.1(ii), mechanism 1)
# --------------------------------------------------------------------------- #

def test_t2b_fitting_on_a_calibration_project_is_rejected():
    """T2b: a non-train project in the fitting frame is an error, not a warning."""
    frame, durations, assignment = _synthetic(n_projects=4, per=10)
    assignment["org/p02"] = "calibration"
    with pytest.raises(de.DurationLeakageError, match="non-train project"):
        de.DurationEstimator(n_iter=1).fit(
            frame, durations, split_assignment=assignment)


def test_t2b_fitting_on_a_test_project_is_rejected():
    frame, durations, assignment = _synthetic(n_projects=4, per=10)
    assignment["org/p03"] = "test"
    with pytest.raises(de.DurationLeakageError, match="non-train project"):
        de.DurationEstimator(n_iter=1).fit(
            frame, durations, split_assignment=assignment)


def test_t2b_a_project_absent_from_the_frozen_assignment_is_rejected():
    """Unprovable is treated as unsafe: no assignment entry, no fit."""
    frame, durations, assignment = _synthetic(n_projects=4, per=10)
    del assignment["org/p01"]
    with pytest.raises(de.DurationLeakageError, match="absent from"):
        de.DurationEstimator(n_iter=1).fit(
            frame, durations, split_assignment=assignment)


def test_t2b_within_project_state_is_permitted_on_calibration_and_test():
    """DL-014 §Resolution 2: ④b reads a held-out project's own earlier builds.

    This is the intended deployment information regime — the repository's own
    build history to date — and no parameter is estimated from the project.
    """
    frame, durations, _ = _synthetic(n_projects=2, per=8, split="test")
    hist = _history(frame, durations)
    de.assert_history_is_causal(frame, hist, durations)
    assert (hist["n_history"] > 0).any()


# --------------------------------------------------------------------------- #
# T3 — the deliberately leaky fixture must be rejected (A1.1(iii))
# --------------------------------------------------------------------------- #

def test_t3_leaky_history_is_rejected_by_the_causality_assertion():
    """T3: a ``≤ t_b`` window includes b itself, and the guard must catch it."""
    frame, durations, _ = _synthetic(n_projects=3, per=8)
    leaky = _history(frame, durations, strict=False)
    with pytest.raises(de.DurationLeakageError, match="earliest timestamp"):
        de.assert_history_is_causal(frame, leaky, durations)


def test_t3_the_shipped_history_passes_the_same_assertion():
    """The guard must pass on the real path — otherwise it proves nothing."""
    frame, durations, _ = _synthetic(n_projects=3, per=8)
    de.assert_history_is_causal(frame, _history(frame, durations), durations)


def test_t3_history_that_disagrees_within_a_tie_block_is_rejected():
    """The second half of the guard: tie members must see identical history."""
    frame, durations, _ = _synthetic(n_projects=1, per=4)
    frame = frame.copy()
    frame["gh_build_started_at"] = ["2014-01-01 00:00:00", "2014-01-01 01:00:00",
                                    "2014-01-01 01:00:00", "2014-01-01 02:00:00"]
    hist = _history(frame, durations)
    hist.loc[hist.index[2], "n_history"] = 2      # hand-corrupt one tie member
    with pytest.raises(de.DurationLeakageError, match="disagree on n_history"):
        de.assert_history_is_causal(frame, hist, durations)


# --------------------------------------------------------------------------- #
# T4 — round-trip reproducibility (R8)
# --------------------------------------------------------------------------- #

def test_t4_persisted_estimator_reproduces_d_hat_exactly(fitted, tmp_path):
    """T4: save → load → identical d̂ for both forms, to the bit."""
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    before_a = est.predict_4a(frame, hist)
    before_b = est.predict_4b(frame, hist)

    path = est.save(tmp_path / "duration_estimator.joblib")
    reloaded = de.DurationEstimator.load(path)

    pd.testing.assert_frame_equal(before_a, reloaded.predict_4a(frame, hist))
    pd.testing.assert_frame_equal(before_b, reloaded.predict_4b(frame, hist))
    assert reloaded.provenance["fit_id"] == est.provenance["fit_id"]


def test_t4_refitting_with_the_same_seed_gives_the_same_configuration():
    """R8: the search is seeded, so the selected configuration is stable."""
    frame, durations, assignment = _synthetic(n_projects=4, per=20)
    a = de.DurationEstimator(n_iter=3).fit(frame, durations,
                                           split_assignment=assignment)
    b = de.DurationEstimator(n_iter=3).fit(frame, durations,
                                           split_assignment=assignment)
    assert a.xgb_best_params == b.xgb_best_params
    assert a.ridge_best_params == b.ridge_best_params
    assert a.provenance["fit_id"] == b.provenance["fit_id"]


# --------------------------------------------------------------------------- #
# T5 — totality: no build silently escapes a strategy (spec §6.1)
# --------------------------------------------------------------------------- #

def test_t5_every_build_gets_a_finite_positive_estimate_and_a_rung(fitted):
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    for out in (est.predict_4a(frame, hist), est.predict_4b(frame, hist)):
        assert np.isfinite(out["d_hat_log1p"]).all()
        assert (out["d_hat_seconds"] > 0).all()
        assert out["fallback_level"].isin(de.FALLBACK_LEVELS).all()


def test_t5_a_project_with_no_history_falls_to_the_language_rung(fitted):
    """Rung 1 is unavailable at |H(b)| = 0; the ladder must engage, not fail."""
    est, frame, _, _ = fitted
    cold = frame.iloc[:3].copy()
    hist = pd.DataFrame({"n_history": [0, 0, 0],
                         "hist_median_log1p": [np.nan] * 3}, index=cold.index)
    out = est.predict_4b(cold, hist)
    assert (out["fallback_level"] == "language").all()
    assert np.isfinite(out["d_hat_log1p"]).all()


def test_t5_an_unseen_language_falls_through_to_the_global_rung(fitted):
    """Rung 3 is total, so an unknown language still yields a usable d̂."""
    est, frame, _, _ = fitted
    odd = frame.iloc[:3].copy()
    odd["lang"] = "cobol"
    hist = pd.DataFrame({"n_history": [0, 0, 0],
                         "hist_median_log1p": [np.nan] * 3}, index=odd.index)
    out_b = est.predict_4b(odd, hist)
    assert (out_b["fallback_level"] == "global").all()
    assert out_b["d_hat_log1p"].eq(est.global_prior_log1p).all()
    # ④a: §6.1 sends an unseen level to the ladder as well, so the two forms
    # stay directly comparable in the coverage table.
    out_a = est.predict_4a(odd, hist)
    assert (out_a["fallback_level"] == "global").all()


def test_t5_the_ladder_prefers_the_project_rung_when_history_exists(fitted):
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    out = est.predict_4b(frame, hist)
    has_history = hist["n_history"] > 0
    assert (out.loc[has_history.to_numpy(), "fallback_level"] == "project").all()


def test_t5_min_history_sensitivity_moves_builds_off_the_project_rung(fitted):
    """§6.3(4): requiring |H(b)| ≥ 20 must demote the early builds, not crash."""
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    strict = est.predict_4b(frame, hist, min_history=20)
    loose = est.predict_4b(frame, hist, min_history=1)
    assert (strict["fallback_level"] == "project").sum() < \
           (loose["fallback_level"] == "project").sum()
    assert np.isfinite(strict["d_hat_log1p"]).all()


# --------------------------------------------------------------------------- #
# The single-build interface the simulator calls (spec §10)
# --------------------------------------------------------------------------- #

def test_expected_matches_the_batch_path_for_the_same_build(fitted):
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    i = 17
    batch = est.predict_4b(frame.iloc[[i]], hist.iloc[[i]]).iloc[0]
    one = est.expected(frame.iloc[i], history=hist.iloc[i].to_dict(), form="4b")
    assert one.d_hat_log1p == pytest.approx(float(batch["d_hat_log1p"]))
    assert one.fallback_level == batch["fallback_level"]
    assert one.n_history == int(batch["n_history"])


def test_expected_requires_a_form_when_none_is_frozen(fitted):
    est, frame, durations, _ = fitted
    with pytest.raises(ValueError, match="no form selected"):
        est.expected(frame.iloc[0])


def test_expected_record_carries_the_spec_6_2_fields(fitted):
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    est.primary_form = "4b"
    rec = est.expected(frame.iloc[5], history=hist.iloc[5].to_dict()).as_record()
    assert set(rec) >= {"d_hat_log1p", "d_hat_seconds", "form", "fallback_level",
                        "n_history", "fit_id", "seed", "fit_row_range"}
    est.primary_form = None


def test_scoring_never_receives_the_scored_builds_duration(fitted):
    """The wire the whole specification protects: d̂ has no duration argument."""
    import inspect

    sig = inspect.signature(de.DurationEstimator.expected)
    assert "duration" not in " ".join(sig.parameters)


# --------------------------------------------------------------------------- #
# §1.2 label discipline, §5 selection rule, and the reported quality metrics
# --------------------------------------------------------------------------- #

def test_unusable_labels_are_excluded_from_fitting_only():
    """A zero/missing duration cannot be a label, but the build is not dropped."""
    frame, durations, assignment = _synthetic(n_projects=3, per=12)
    durations = durations.copy()
    durations.iloc[0] = 0.0
    durations.iloc[1] = np.nan
    est = de.DurationEstimator(n_iter=1).fit(frame, durations,
                                             split_assignment=assignment)
    assert est.provenance["n_builds_unusable_label"] == 2
    assert est.provenance["n_fit_builds"] == len(frame) - 2
    hist = _history(frame, durations)
    assert len(est.predict_4b(frame, hist)) == len(frame)   # still scored


def test_choose_primary_form_prefers_lower_mae_and_breaks_ties_to_4b():
    assert de.choose_primary_form(0.50, 0.60) == "4a"
    assert de.choose_primary_form(0.60, 0.50) == "4b"
    assert de.choose_primary_form(0.500001, 0.500002) == "4b"


def test_score_quality_reports_both_scales_and_spearman(fitted):
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    q = de.score_quality(est.predict_4b(frame, hist), durations)
    assert set(q) >= {"mae_log1p", "median_ae_log1p", "mae_seconds",
                      "median_ae_seconds", "spearman_rho", "n"}
    assert q["n"] == len(frame)
    assert q["mae_log1p"] >= 0


def test_coverage_table_counts_every_build_once(fitted):
    est, frame, durations, _ = fitted
    cov = de.coverage_table(est.predict_4b(frame, _history(frame, durations)))
    assert cov["n_builds"] == len(frame)
    assert sum(v["n"] for v in cov["levels"].values()) == len(frame)


def test_to_seconds_is_the_monotone_inverse_of_the_log1p_target():
    d = pd.Series([1.0, 60.0, 3600.0, 86400.0])
    assert np.allclose(de.to_seconds(de.to_log1p(d)), d.to_numpy())


def test_ridge_reference_is_available_but_distinct_from_the_primary(fitted):
    """§4.2: Ridge is reported for transparency; it is not the primary control."""
    est, frame, durations, _ = fitted
    hist = _history(frame, durations)
    xgb = est.predict_4a(frame, hist, regressor="xgboost")
    ridge = est.predict_4a(frame, hist, regressor="ridge")
    assert len(ridge) == len(xgb)
    assert not np.allclose(xgb["d_hat_log1p"], ridge["d_hat_log1p"])

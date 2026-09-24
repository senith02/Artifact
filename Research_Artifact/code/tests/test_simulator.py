"""Tests for the P2-T4 replay simulator (replay/simulator.py, DL-023).

Every test runs on a small hand-built trace against the REAL carbon profile, the
REAL energy config and the bootstrap policy spec — no dataset row is read.
"""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from replay import simulator as sim
from replay import validate_invariants as vi
from scheduler_core import accounting, carbon, policy


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def profile() -> pd.DataFrame:
    return carbon.load_hour_of_week_profile()


@pytest.fixture(scope="module")
def spec() -> policy.PolicySpec:
    return policy.load_policy_spec(policy.BOOTSTRAP_POLICY_SPEC_PATH, require_fitted=False)


@pytest.fixture(scope="module")
def energy() -> accounting.EnergyConfig:
    return accounting.load_energy_config()


@pytest.fixture(scope="module")
def grid() -> sim.SweepGrid:
    return sim.load_sweep_grid()


BRANCHES = ("feature/a", "master", "fix-typo", "release/1.2", "develop", "topic_x")


def make_trace(n: int = 84, seed: int = 7) -> pd.DataFrame:
    """A deterministic synthetic trace covering PR / protected / deferrable builds."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2014-03-03 00:30:00", tz="UTC")          # a Monday
    arrival = start + pd.to_timedelta(rng.integers(0, 24 * 14, size=n), unit="h")
    trace = pd.DataFrame({
        "replay_seq": 0,
        "tr_build_id": [str(1000 + i) for i in range(n)],
        "gh_project_name": [f"org/p{i % 5}" for i in range(n)],
        "gh_is_pr": ["true" if i % 4 == 0 else "false" for i in range(n)],
        "git_branch": [BRANCHES[i % len(BRANCHES)] for i in range(n)],
        "arrival_utc": arrival.strftime("%Y-%m-%d %H:%M:%S+00:00"),
        "arrival_dow": arrival.dayofweek.astype("int64"),
        "arrival_hour": arrival.hour.astype("int64"),
        "d_hat_4a_seconds": rng.uniform(10, 9000, size=n),
        "d_hat_4a_fallback": "project",
        "d_hat_4b_seconds": rng.uniform(10, 9000, size=n),
        "d_hat_4b_fallback": "project",
        "d_hat_4b_n_history": rng.integers(0, 50, size=n),
        "p_hat": rng.uniform(0, 0.6, size=n),
        "obs_duration_s": rng.uniform(30, 7200, size=n),
        "y_fail": (rng.uniform(size=n) < 0.3).astype("int64"),
    })
    return sim.order_trace(trace)


@pytest.fixture(scope="module")
def trace() -> pd.DataFrame:
    return make_trace()


def run_all(trace, spec, profile, energy, settings) -> pd.DataFrame:
    frames = [sim.replay_setting(trace, s, base_spec=spec, profile=profile,
                                 p_avg_w=energy.p_avg_w, primary_form="4b")
              for s in settings]
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def records(trace, spec, profile, energy, grid) -> pd.DataFrame:
    return run_all(trace, spec, profile, energy, sim.enumerate_settings(grid))


# --------------------------------------------------------------------------- #
# Grid + settings (DL-023 §1, §2)
# --------------------------------------------------------------------------- #

def test_grid_is_the_dl023_grid(grid):
    assert grid.w_max_hours == (6.0, 12.0, 24.0)                  # §7 / DL-008 verbatim
    assert grid.d_threshold_seconds[0] == 0.0
    assert grid.d_threshold_seconds[1:] == tuple(60.0 * 2 ** k for k in range(9))
    assert grid.tau_skip[0] == 0.0
    assert grid.blanket_w_max_hours == carbon.N_SLOTS - 1
    assert grid.sample["split"] == "calibration" and grid.sample["n_builds"] >= 10_000


def test_settings_cover_six_strategies_in_canonical_order(grid):
    settings = sim.enumerate_settings(grid)
    n_d, n_w, n_t = len(grid.d_threshold_seconds), len(grid.w_max_hours), len(grid.tau_skip)
    assert len(settings) == 1 + 1 + n_w + 3 * n_d * n_w + n_t
    order = [s.strategy for s in settings]
    assert list(dict.fromkeys(order)) == list(sim.STRATEGIES)
    assert len({s.setting_id for s in settings}) == len(settings)


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r["w_max_hours"].__setitem__("values", [24, 12]), "strictly increasing"),
    (lambda r: r["d_threshold_seconds"].__setitem__("values", [-1, 60]), "outside"),
    (lambda r: r["tau_skip"].__setitem__("values", [0.0, 1.5]), "outside"),
    (lambda r: r["blanket_w_max_hours"].__setitem__("value", 24), "horizon"),
    (lambda r: r["sample"].__setitem__("split", "test"), "test split"),
    (lambda r: r.__setitem__("frozen_by", "nobody"), "DL-023"),
    (lambda r: r["w_max_hours"].pop("source"), "source"),
])
def test_grid_validation_rejects(tmp_path, mutate, message):
    raw = json.loads(sim.GRID_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "grid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(sim.SimulatorError, match=message):
        sim.load_sweep_grid(path)


def test_derive_spec_revalidates_and_keeps_quarantine(spec):
    derived = sim.derive_spec(spec, policy_path="duration_only_fallback",
                              d_threshold_seconds=480.0, w_max_hours=12.0)
    assert derived.duration_only["d_threshold_seconds"] == 480.0
    assert derived.fitted is False                       # unfitted base -> unfitted derived
    assert spec.duration_only["d_threshold_seconds"] == 0.0   # base untouched
    with pytest.raises(policy.PolicyError):
        sim.derive_spec(spec, policy_path="duration_only_fallback",
                        d_threshold_seconds=0.0, w_max_hours=500.0)   # > profile horizon
    with pytest.raises(sim.SimulatorError):
        sim.derive_spec(spec, policy_path="nonsense", d_threshold_seconds=0.0, w_max_hours=6.0)


def test_spec_from_mapping_is_the_file_validator(spec):
    raw = copy.deepcopy(dict(spec.raw))
    raw["duration_only"]["smuggled_threshold"] = 1.0
    with pytest.raises(policy.PolicyError, match="schema is closed"):
        policy.spec_from_mapping(raw, source_path=spec.source_path, require_fitted=False)
    with pytest.raises(policy.PolicyError, match="UNFITTED"):
        policy.spec_from_mapping(dict(spec.raw), source_path=spec.source_path)


# --------------------------------------------------------------------------- #
# Identical inputs, safety, the stated identities
# --------------------------------------------------------------------------- #

def test_every_setting_saw_the_identical_build_set(records, trace, grid):
    report = sim.assert_identical_build_sets(records)
    assert report["identical"]
    assert report["settings_compared"] == len(sim.enumerate_settings(grid))
    assert report["builds_per_setting"] == len(trace)


def test_identical_build_set_check_catches_a_dropped_build(records):
    tampered = records.drop(index=records.index[-1])
    with pytest.raises(sim.SimulatorError, match="different build set"):
        sim.assert_identical_build_sets(tampered)


def test_no_non_deferrable_build_is_ever_deferred_or_skipped(records):
    audit = vi.audit_frame(records, variant="primary")
    assert audit.passed and audit.violations == 0
    assert audit.deferred > 0                             # the check is not vacuous
    assert sim.audit_skips(records, variant="primary")["passed"]
    pr = records["gh_is_pr"] == "true"
    assert not records.loc[pr, "action"].isin(["defer", "skip"]).any()


def test_skip_audit_catches_a_skipped_protected_build(records):
    bad = records.copy()
    idx = bad.index[(bad["git_branch"] == "master")][0]
    bad.loc[idx, "action"] = "skip"
    assert not sim.audit_skips(bad, variant="primary")["passed"]


def _decisions(records, setting_id):
    g = records.loc[records["setting_id"] == setting_id,
                    ["tr_build_id", "action", "delay_hours", "scheduled_slot"]]
    return g.reset_index(drop=True)


def test_stated_identities_hold(records, grid):
    for w in grid.w_max_hours:
        assert _decisions(records, f"3_eligibility_only__d0__w{w:g}").equals(
            _decisions(records, f"4b_duration_prior__d0__w{w:g}"))
        for d in grid.d_threshold_seconds:
            # Bootstrap spec is on the duration-only path, so ⑤ is ④b by construction.
            assert _decisions(records, f"5_se_informed_policy__d{d:g}__w{w:g}").equals(
                _decisions(records, f"4b_duration_prior__d{d:g}__w{w:g}"))
    assert (_decisions(records, "6_risk_only_skip__t0")["action"] == "run_now").all()


def test_static_runs_everything_now(records):
    g = records.loc[records["strategy"] == "1_static"]
    assert (g["action"] == "run_now").all() and (g["delay_hours"] == 0).all()
    assert (g["scheduled_slot"] == g["arrival_slot"]).all()


def test_deferrals_fall_monotonically_as_d_threshold_rises(records, grid):
    for strategy in ("4a_duration_estimator", "4b_duration_prior"):
        for w in grid.w_max_hours:
            counts = [int((records["setting_id"] == f"{strategy}__d{d:g}__w{w:g}")
                          .where(records["action"] == "defer", False).sum())
                      for d in grid.d_threshold_seconds]
            assert counts == sorted(counts, reverse=True), (strategy, w, counts)


def test_whole_week_blanket_reaches_at_least_as_green_as_any_window(records, grid):
    blanket = records.loc[records["setting_id"] == "2_blanket_carbon_aware__d0__w167"]
    for w in grid.w_max_hours:
        other = records.loc[records["setting_id"] == f"3_eligibility_only__d0__w{w:g}"]
        assert (blanket["grid_gco2_scheduled"].to_numpy()
                <= other["grid_gco2_scheduled"].to_numpy() + 1e-12).all()


# --------------------------------------------------------------------------- #
# §A1.2: what decide() may see
# --------------------------------------------------------------------------- #

def test_decide_only_ever_sees_whitelisted_inputs(trace, spec, profile, energy, grid, monkeypatch):
    seen: set[str] = set()
    real = policy.decide

    def spy(build, carbon_profile, config):
        seen.update(build)
        return real(build, carbon_profile, config)

    monkeypatch.setattr(sim.policy, "decide", spy)
    run_all(trace, spec, profile, energy, sim.enumerate_settings(grid))
    assert seen, "decide() was never called"
    assert seen <= set(sim.DECISION_INPUTS) | {"d_hat_seconds", "p_hat"}
    assert not {"obs_duration_s", "tr_duration", "y_fail", "tr_status"} & seen


def test_decisions_are_invariant_to_observed_duration_and_outcome(trace, spec, profile,
                                                                 energy, grid, records):
    """Metamorphic: scramble the accounting-only columns; no decision may move."""
    rng = np.random.default_rng(99)
    scrambled = trace.copy()
    scrambled["obs_duration_s"] = rng.permutation(scrambled["obs_duration_s"].to_numpy()) * 3
    scrambled["y_fail"] = 1 - scrambled["y_fail"]
    again = run_all(scrambled, spec, profile, energy, sim.enumerate_settings(grid))
    cols = ["setting_id", "tr_build_id", "action", "reason_code", "delay_hours",
            "scheduled_slot", "window_hours"]
    assert again[cols].equals(records[cols])
    assert not np.allclose(again["carbon_g"].to_numpy(), records["carbon_g"].to_numpy())


# --------------------------------------------------------------------------- #
# Accounting (DL-023 §3)
# --------------------------------------------------------------------------- #

def test_accounting_matches_hand_computation(records, trace, energy, profile):
    row = records.loc[records["action"] == "defer"].iloc[0]
    dur = float(trace.loc[trace["tr_build_id"] == row["tr_build_id"], "obs_duration_s"].iloc[0])
    slot = int(row["scheduled_slot"])
    intensity = carbon.intensity_for_hour_of_week(profile, slot // 24, slot % 24)
    expected_e = (energy.p_avg_w / 1000.0) * (dur / 3600.0)
    assert row["energy_kwh"] == pytest.approx(expected_e, rel=1e-12)
    assert row["carbon_g"] == pytest.approx(expected_e * intensity, rel=1e-12)
    assert row["grid_gco2_scheduled"] == pytest.approx(intensity)
    if row["y_fail"] == 1:
        assert row["ttff_hours"] == pytest.approx(row["delay_hours"] + dur / 3600.0)


def test_ttff_is_delay_plus_duration_for_failed_builds_only(records, trace):
    dur = dict(zip(trace["tr_build_id"], trace["obs_duration_s"]))
    failed = records.loc[(records["y_fail"] == 1) & (records["action"] != "skip")]
    assert len(failed) > 0
    expected = failed["delay_hours"] + failed["tr_build_id"].map(dur) / 3600.0
    assert np.allclose(failed["ttff_hours"].to_numpy(), expected.to_numpy())
    assert records.loc[records["y_fail"] == 0, "ttff_hours"].isna().all()


def test_unaccountable_build_is_decided_but_never_zero_filled(spec, profile, energy):
    t = make_trace(n=24).copy()
    t.loc[3, "obs_duration_s"] = np.nan
    t.loc[5, "obs_duration_s"] = -4.0
    rec = sim.replay_setting(t, sim.Setting("3_eligibility_only", 0.0, 24.0),
                             base_spec=spec, profile=profile, p_avg_w=energy.p_avg_w,
                             primary_form="4b")
    for i in (3, 5):
        assert rec.loc[i, "action"] in ("run_now", "defer")          # still decided
        assert np.isnan(rec.loc[i, "energy_kwh"]) and np.isnan(rec.loc[i, "carbon_g"])
    summary, _ = sim.summarise(rec.astype(str).replace({"nan": "", "None": ""}))
    assert int(summary.loc[0, "n_unaccountable"]) == 2
    assert int(summary.loc[0, "n_accountable"]) == 22


def test_skips_cost_nothing_and_count_as_missed_failures(spec, profile, energy):
    t = make_trace(n=60)
    rec = sim.replay_setting(t, sim.Setting("6_risk_only_skip", tau_skip=1.0), base_spec=spec,
                             profile=profile, p_avg_w=energy.p_avg_w, primary_form="4b")
    skipped = rec["action"] == "skip"
    assert skipped.any()
    assert (rec.loc[skipped, "carbon_g"] == 0).all() and (rec.loc[skipped, "energy_kwh"] == 0).all()
    assert rec.loc[skipped, "ttff_hours"].isna().all()
    assert (rec.loc[skipped, "eligible"] == True).all()                 # noqa: E712
    summary, herd = sim.summarise(rec.astype(str).replace({"nan": "", "None": ""}))
    n_missed = int(((rec["y_fail"] == 1) & skipped).sum())
    assert int(summary.loc[0, "missed_failures"]) == n_missed
    assert int(herd["n_scheduled"].sum()) == int((~skipped).sum())    # skips are not load


def test_se_informed_path_consumes_p_hat_and_shrinks_the_window(spec, profile, energy):
    raw = copy.deepcopy(dict(spec.raw))
    raw["policy_path"] = "se_informed"
    raw["se_informed"]["admitted_families"] = ["F1"]      # test-only fixture spec
    se_spec = policy.spec_from_mapping(raw, source_path=spec.source_path, require_fitted=False)
    t = make_trace(n=40).copy()
    t["p_hat"] = 1.0                                      # certain failure -> window 0
    rec = sim.replay_setting(t, sim.Setting("5_se_informed_policy", 0.0, 24.0),
                             base_spec=se_spec, profile=profile, p_avg_w=energy.p_avg_w,
                             primary_form="4b")
    eligible = rec["eligible"] == True                                  # noqa: E712
    assert eligible.any()
    assert (rec.loc[eligible, "window_hours"] == 0).all()
    assert (rec.loc[eligible, "action"] == "run_now").all()
    assert (rec.loc[eligible, "policy_path"] == "se_informed").all()


# --------------------------------------------------------------------------- #
# Sampling, ordering, determinism, resumability (DL-023 §4, §6)
# --------------------------------------------------------------------------- #

def test_sample_is_seeded_and_independent_of_input_order():
    t = make_trace(n=200)
    a = sim.sample_builds(t, 50, seed=42)
    b = sim.sample_builds(t.sample(frac=1.0, random_state=3), 50, seed=42)
    assert a["tr_build_id"].tolist() == b["tr_build_id"].tolist()
    assert sim.sample_builds(t, 50, seed=43)["tr_build_id"].tolist() != a["tr_build_id"].tolist()
    with pytest.raises(sim.SimulatorError):
        sim.sample_builds(t, 201, seed=42)


def test_replay_order_is_arrival_then_build_id():
    t = make_trace(n=30).copy()
    t.loc[:, "arrival_utc"] = "2014-01-01 10:00:00+00:00"          # all tied
    ordered = sim.order_trace(t.iloc[::-1])
    ids = pd.to_numeric(ordered["tr_build_id"]).tolist()
    assert ids == sorted(ids)
    assert ordered["replay_seq"].tolist() == list(range(30))
    with pytest.raises(sim.SimulatorError, match="replay order"):
        sim.validate_trace(ordered.iloc[::-1].reset_index(drop=True))


def _fingerprint(trace, grid, spec, energy):
    return sim.run_fingerprint(trace=trace, grid=grid, base_spec=spec, p_avg_w=energy.p_avg_w,
                               primary_form="4b", profile_path=carbon.DEFAULT_PROFILE_PATH)


def test_rerun_is_byte_identical_and_resume_changes_nothing(tmp_path, trace, spec, profile,
                                                            energy, grid):
    settings = sim.enumerate_settings(grid)[:12]
    fp = _fingerprint(trace, grid, spec, energy)
    kw = dict(base_spec=spec, profile=profile, p_avg_w=energy.p_avg_w, primary_form="4b",
              fingerprint=fp)
    a = sim.assemble(sim.run_sweep(trace, settings, parts_dir=tmp_path / "a", **kw),
                     tmp_path / "a.csv.gz")
    b = sim.assemble(sim.run_sweep(trace, settings, parts_dir=tmp_path / "b", **kw),
                     tmp_path / "b.csv.gz")
    assert a == b                                          # two cold runs: same bytes
    parts = sorted((tmp_path / "a" / fp[:16]).glob("*.csv"))
    for p in parts[::2]:                                  # simulate an interrupted run
        p.unlink()
    parts[1].with_suffix(".done").write_text("corrupt\n", encoding="utf-8")
    c = sim.assemble(sim.run_sweep(trace, settings, parts_dir=tmp_path / "a", **kw),
                     tmp_path / "c.csv.gz")
    assert c == a                                          # resumed run: same bytes
    back = sim.load_records(tmp_path / "a.csv.gz")
    assert list(back.columns) == list(sim.RECORD_COLUMNS)
    assert len(back) == len(settings) * len(trace)


def test_fingerprint_moves_with_inputs_and_parts_refuse_a_foreign_run(tmp_path, trace, spec,
                                                                      profile, energy, grid):
    fp = _fingerprint(trace, grid, spec, energy)
    changed = trace.copy()
    changed.loc[0, "d_hat_4b_seconds"] += 1.0
    assert _fingerprint(changed, grid, spec, energy) != fp
    parts = tmp_path / "parts"
    (parts / fp[:16]).mkdir(parents=True)
    (parts / fp[:16] / "FINGERPRINT").write_text("someone-else\n", encoding="utf-8")
    with pytest.raises(sim.SimulatorError, match="different run fingerprint"):
        sim.run_sweep(trace, sim.enumerate_settings(grid)[:1], base_spec=spec, profile=profile,
                      p_avg_w=energy.p_avg_w, primary_form="4b", parts_dir=parts,
                      fingerprint=fp)


def test_records_carry_every_input_needed_to_reproduce_the_reason(trace, spec, profile, grid):
    showcase = [s for s in sim.enumerate_settings(grid)
                if s.setting_id in ("4b_duration_prior__d960__w24", "3_eligibility_only__d0__w6")]
    reasons = sim.worked_reasons(trace, showcase, base_spec=spec, profile=profile,
                                 primary_form="4b")
    assert reasons and all("stage1[primary]" in r["reason"] for r in reasons)

"""P4-T1 — the advisor's order of operations, fail-safes and veto layer.

Defended, in order of importance:

1. **Every failure is RUN NOW** with a named code (the fail-safe matrix, R3-C5).
2. **The veto layer is monotone**: whenever the advisor defers, decide() deferred
   to the identical slot; a veto or deadline only ever produces RUN NOW (R3-B6).
3. **Cold start → RUN NOW** by default, as a veto that can be switched off (R3-J1).
4. **Display-only inputs never move a decision** (live national/regional intensity,
   R3-B5, R3-J2); **scenario mode changes labels only** (R3-K).
5. **Non-GB compute (East US) fails safe** with no GB carbon figures (R3-J3).
6. The frozen pins hold, and are line-ending-normalised (DL-035 §2).
"""

from __future__ import annotations

import random
from datetime import timedelta

import pytest

from advisor import carbon_live
from advisor.config import ConfigError
from advisor.contract import NULL_STATEMENT, SCENARIO_BANNER
from advisor.core import advise, decision_view
from advisor.frozen import (
    ESTIMATOR_PATH, PINS, PROFILE_PATH, SPEC_PATH, FrozenArtifactError, Pins, load_frozen_core,
    normalised_sha256, raw_sha256,
)
from advisor.history import HistoryError
from scheduler_core.policy import decide

from tests.advisor_helpers import NOW, config, deps, history, request


def _fails_safe(response, code):
    assert response["action"] == "run_now" and response["display"].startswith("RUN NOW")
    assert response["fail_safe"] is True and response["fail_safe_code"] == code
    assert response["outcome_kind"] == "fail_safe" and response["defer_until"] is None
    assert f"[{code}]" in response["reason"] and NULL_STATEMENT in response["reason"]


# --------------------------------------------------------------------------- #
# 1. The fail-safe matrix.
# --------------------------------------------------------------------------- #

def test_the_happy_path_defers_through_decide():
    r = advise(request(), config(), deps())
    assert r["action"] == "defer" and r["outcome_kind"] == "policy" and r["display"] == "DEFER RECOMMENDED"
    assert r["d_hat_rung"] == "project" and r["n_history"] == 12 and r["d_hat_seconds"] == pytest.approx(870.0)
    assert r["defer_until"]["utc"].startswith("2026-10-02") and r["est_carbon_change_pct"] < 0
    assert NULL_STATEMENT in r["reason"] and r["policy_path"] == "duration_only_fallback"


@pytest.mark.parametrize("raw,code", [
    (request(extra="x"), "invalid_request"),
    (request(tr_duration=800), "invalid_request"),
    (request(src_churn=12), "invalid_request"),
    (request(p_hat=0.1), "invalid_request"),
    (request(event="pull_request_target"), "untrusted_event"),
    (request(scenario="gb-hypothetical", compute_region="US-EAST"), "scenario_invalid"),
    (request(deadline_utc="2026-10-01T17:00:00Z"), "deadline_invalid"),
    (request(arrival_utc="2026-10-01T21:00:00Z"), "arrival_in_future"),
    (request(history=[{"run_id": 1}]), "history_unavailable"),
])
def test_invalid_inputs_fail_safe(raw, code):
    _fails_safe(advise(raw, config(), deps()), code)


def test_missing_or_invalid_config_fails_safe():
    _fails_safe(advise(request(), None, deps()), "config_invalid")
    _fails_safe(advise(request(), ConfigError("max_delay_hours must be in (0, 24]"), deps()), "config_invalid")


def test_region_mismatch_fails_safe():
    _fails_safe(advise(request(), config(compute_region="US-EAST"), deps()), "region_mismatch")


def test_east_us_compute_fails_safe_with_no_gb_figures():
    """R3-J3: the author's East US VM is declared non-GB and never presented as GB."""
    r = advise(request(compute_region="US-EAST"), config(compute_region="US-EAST"), deps())
    _fails_safe(r, "region_not_gb")
    assert "outside the evaluated GB regime" in r["reason"]
    for key in ("grid_gco2_profile_now", "grid_gco2_profile_scheduled", "est_carbon_change_pct",
                "grid_gco2_live_national", "grid_gco2_live_regional", "d_hat_seconds"):
        assert r[key] is None, key
    assert r["compute_region_assumed"] == "US-EAST"


@pytest.mark.parametrize("pins,code", [
    (Pins(spec_sha256="0" * 64), "spec_unavailable"),
    (Pins(profile_sha256="0" * 64), "profile_unavailable"),
    (Pins(estimator_sha256="0" * 64), "estimator_unavailable"),
    (Pins(estimator_fit_id="not-the-fit"), "estimator_unavailable"),
])
def test_a_pin_mismatch_fails_safe(pins, code):
    _fails_safe(advise(request(), config(), deps(load_frozen=lambda: load_frozen_core(pins=pins))), code)


def test_a_missing_artifact_fails_safe(tmp_path):
    loader = lambda: load_frozen_core(spec_path=tmp_path / "missing.yaml")  # noqa: E731
    _fails_safe(advise(request(), config(), deps(load_frozen=loader)), "spec_unavailable")


def test_a_failing_history_source_fails_safe():
    def broken(repo, workflow, cap):
        raise HistoryError("GitHub API HTTP 502 after 3 attempts")
    raw = request(history=None)
    _fails_safe(advise(raw, config(), deps(history_source=broken)), "history_unavailable")


def test_an_unexpected_exception_fails_safe():
    def boom():
        raise RuntimeError("disk on fire")
    _fails_safe(advise(request(), config(), deps(load_frozen=boom)), "internal_error")


def test_a_workflow_not_opted_in_runs_now_without_being_a_fail_safe():
    r = advise(request(workflow="release.yml"), config(), deps())
    assert r["action"] == "run_now" and r["outcome_kind"] == "not_advised" and r["fail_safe"] is False


def test_runs_stage1_blocks_never_touch_history():
    calls = []
    source = lambda *a: calls.append(a) or []  # noqa: E731
    for raw in (request(branch="main", history=None), request(event="pull_request", is_pr=True, history=None)):
        r = advise(raw, config(), deps(history_source=source))
        assert r["action"] == "run_now" and r["outcome_kind"] == "policy" and r["d_hat_seconds"] is None
    assert calls == []


# --------------------------------------------------------------------------- #
# 2-3. The veto layer and the cold-start rule.
# --------------------------------------------------------------------------- #

def test_cold_start_runs_now_by_default_and_can_be_switched_off():
    raw = request(history=[], repo_language="Python")
    on = advise(raw, config(), deps())
    assert on["policy_action"] == "defer" and on["action"] == "run_now"
    assert on["vetoes"] == ["cold_start"] and on["outcome_kind"] == "veto"
    assert on["d_hat_rung"] == "language" and on["n_history"] == 0
    off = advise(raw, config(cold_start_run_now=False), deps())
    assert off["action"] == "defer" and off["vetoes"] == []


@pytest.mark.parametrize("raw,cfg,veto", [
    (request(redispatch_key="k1"), {}, "redispatched_run"),
    (request(ref_type="tag", branch="feature-tag"), {}, "tag_ref"),
    (request(event="workflow_dispatch"), {}, "event_vetoed"),
    (request(branch="staging/eu"), {"extra_protected_branches": ["staging/*"]}, "extra_protected_branch"),
    (request(head_commit_message="Fix login [URGENT]"), {}, "urgent_marker"),
    (request(deadline_utc="2026-10-01T22:00:00Z"), {}, "exceeds_deadline"),
    (request(), {"max_delay_hours": 2}, "exceeds_max_delay"),
])
def test_each_veto_turns_a_deferral_into_run_now(raw, cfg, veto):
    r = advise(raw, config(**cfg), deps())
    assert r["policy_action"] == "defer" and r["action"] == "run_now"
    assert veto in r["vetoes"] and r["outcome_kind"] == "veto" and r["defer_until"] is None
    assert r["policy_defer_until"] is not None and "-> RUN NOW" in r["reason"]


def test_vetoes_never_act_on_a_run_now():
    r = advise(request(branch="main", head_commit_message="[urgent]"), config(), deps())
    assert r["action"] == "run_now" and r["vetoes"] == [] and r["outcome_kind"] == "policy"


BRANCHES = ["feature/a", "fix/b", "main", "release/1.2", "develop", "hotfix/x", "staging/eu", "docs"]


def test_the_veto_layer_is_monotone_over_generated_inputs():
    """Property (R3-B6): advisor defers ⇒ decide() defers to the identical slot; vetoes ⇒ RUN NOW.

    The generator leans towards eligible, long runs with neutral team settings so
    that every branch of the property is exercised; the minimum-coverage
    assertions at the end stop the test from passing vacuously.
    """
    rng = random.Random(42)
    d = deps()
    core = d.load_frozen()
    checked = 0
    outcomes: dict[str, int] = {"standing_defer": 0, "vetoed": 0, "policy_run_now": 0}
    for _ in range(300):
        n = rng.choice([0, 1, 3, 8, 15, 15])
        arrival = NOW - timedelta(hours=rng.randrange(0, 167), minutes=rng.randrange(60))
        hist = history(n, duration=float(rng.choice([45, 480, 900, 2400, 2400, 2400])),
                       end=arrival - timedelta(hours=1))
        is_pr = rng.random() < 0.1
        branch = rng.choice(BRANCHES) if rng.random() < 0.3 else rng.choice(["feature/a", "fix/b", "docs"])
        raw = request(branch=branch, is_pr=is_pr,
                      event="pull_request" if is_pr else rng.choice(["push"] * 6 + ["workflow_dispatch", "schedule"]),
                      ref_type=rng.choice(["branch"] * 9 + ["tag"]),
                      arrival_utc=arrival.isoformat().replace("+00:00", "Z"), history=hist,
                      repo_language=rng.choice([None, "Python", "Go", "Rust"]),
                      head_commit_message=rng.choice([None, None, None, "tidy", "hotfix [urgent]"]),
                      deadline_utc=rng.choice([None, None, None,
                                               (arrival + timedelta(hours=rng.randrange(1, 30))).isoformat()]))
        cfg = config(cold_start_run_now=rng.random() < 0.7,
                     extra_protected_branches=rng.choice([[], [], ["staging/*"], ["fix/*", "docs"]]),
                     max_delay_hours=rng.choice([24, 24, 24, 12, 6, 1]))
        r = advise(raw, cfg, d)
        assert r["fail_safe"] is False, r["reason"]
        if r["eligible"]:
            build = {"gh_is_pr": is_pr, "git_branch": raw["branch"], "arrival_dow": arrival.weekday(),
                     "arrival_hour": arrival.hour, "d_hat_seconds": r["d_hat_seconds"]}
        else:
            build = {"gh_is_pr": is_pr, "git_branch": raw["branch"], "arrival_dow": arrival.weekday(),
                     "arrival_hour": arrival.hour}
        policy = decide(build, core.profile, core.spec)
        assert r["policy_action"] == policy.action
        if r["action"] == "defer":
            assert policy.action == "defer" and r["vetoes"] == []
            assert r["defer_until"]["slot"] == policy.defer_until["slot"]
            assert r["defer_until"]["offset_hours"] == policy.defer_until["offset_hours"]
        if r["vetoes"]:
            assert r["action"] == "run_now" and policy.action == "defer"
        if policy.action == "run_now":
            assert r["action"] == "run_now"
            outcomes["policy_run_now"] += 1
        elif r["vetoes"]:
            outcomes["vetoed"] += 1
        else:
            outcomes["standing_defer"] += 1
        checked += 1
    assert checked == 300
    assert min(outcomes.values()) >= 30, outcomes


# --------------------------------------------------------------------------- #
# 4. Display-only inputs and scenario labels never move the decision.
# --------------------------------------------------------------------------- #

def test_live_national_and_regional_values_are_display_only():
    base = advise(request(), config(grid_display_region="EC1A"), deps())
    shown = advise(request(), config(grid_display_region="EC1A"), deps(
        live_national=lambda: {"gco2_per_kwh": 999.0, "kind": "actual"},
        live_regional=lambda region: {"gco2_per_kwh": 1.0, "kind": "forecast", "region": "London"}))

    def broken(req, timeout):
        raise OSError("down")
    failing = advise(request(), config(grid_display_region="EC1A"), deps(
        live_national=lambda: carbon_live.fetch_national(opener=broken),
        live_regional=lambda region: carbon_live.fetch_regional(region, opener=broken)))
    assert decision_view(base) == decision_view(shown) == decision_view(failing)
    assert shown["grid_gco2_live_regional"]["gco2_per_kwh"] == 1.0
    assert failing["grid_gco2_live_national"] is None and failing["fail_safe"] is False


def test_an_invalid_display_region_is_a_warning_not_a_fail_safe():
    r = advise(request(), config(grid_display_region="??"), deps())
    assert r["fail_safe"] is False and r["config_warnings"] and r["action"] == "defer"


def test_scenario_mode_changes_labels_only():
    real = advise(request(), config(), deps())
    scenario = advise(request(scenario="gb-hypothetical"), config(), deps())
    assert decision_view(real) == decision_view(scenario)
    assert scenario["display"] == "DEFER RECOMMENDED (scenario)" and scenario["scenario"] == "gb-hypothetical"
    assert scenario["statements"][0] == SCENARIO_BANNER and SCENARIO_BANNER not in real["statements"]


def test_the_null_statement_is_in_every_outcome():
    for r in (advise(request(), config(), deps()), advise(request(branch="main"), config(), deps()),
              advise(request(history=[]), config(), deps()), advise(request(compute_region="US-EAST"),
                                                                    config(compute_region="US-EAST"), deps())):
        assert NULL_STATEMENT in r["reason"]


# --------------------------------------------------------------------------- #
# 6. The frozen pins.
# --------------------------------------------------------------------------- #

def test_the_pins_match_the_frozen_artifacts():
    assert normalised_sha256(SPEC_PATH) == PINS.spec_sha256
    assert normalised_sha256(PROFILE_PATH) == PINS.profile_sha256
    assert raw_sha256(ESTIMATOR_PATH) == PINS.estimator_sha256
    core = load_frozen_core()
    assert core.estimator_fit_id == "1088d5546f47ff12" and core.spec.fitted
    assert core.spec.policy_path == "duration_only_fallback"


def test_the_text_pins_ignore_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.csv", tmp_path / "crlf.csv"
    lf.write_bytes(b"a,b\n1,2\n")
    crlf.write_bytes(b"a,b\r\n1,2\r\n")
    assert normalised_sha256(lf) == normalised_sha256(crlf)
    assert raw_sha256(lf) != raw_sha256(crlf)


def test_a_mismatched_pin_names_its_artifact():
    with pytest.raises(FrozenArtifactError) as info:
        load_frozen_core(pins=Pins(profile_sha256="f" * 64))
    assert info.value.code == "profile_unavailable"

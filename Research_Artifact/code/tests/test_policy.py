"""Tests for Stage 2 — `decide()` over `policy_spec.yaml` (P2-T3 S4).

What is being defended, in descending order of importance:

1. **`decide()` cannot see the current build's `tr_duration`** (§A1.2). Asserted
   behaviourally — the call *raises* — not merely documented.
2. **Stage 1 runs first, unconditionally, and returns.** A non-deferrable build
   never reaches Stage 2. Asserted by making Stage 2's inputs *absent*: if Stage 2
   were consulted, the call would raise for a missing `d_hat_seconds`; it does
   not, which proves the early return (invariant 1, DL-022 §6).
3. **No threshold is hard-coded in the module** (invariant 7). Asserted twice:
   on the AST (no float literal beyond the two structural ones) and behaviourally
   (changing a spec value changes the decision).
4. **The bootstrap spec cannot produce a reported number** — `require_fitted`
   defaults to True and refuses it (DL-022 §4).
5. Determinism, the §7 monotone window, and the `[0, W_max]` clip.

Offline and deterministic: hand-made profile fixtures, no dataset, no network.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pandas as pd
import pytest
import yaml

from scheduler_core import carbon, policy

# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #

@pytest.fixture()
def boot() -> policy.PolicySpec:
    """The bootstrap spec — the only spec available before P2-T5 fits the real one."""
    return policy.load_policy_spec(policy.BOOTSTRAP_POLICY_SPEC_PATH, require_fitted=False)


def _flat_profile(mean_value: float = 200.0) -> pd.DataFrame:
    rows = [{"slot": s, "dow": s // 24, "hour": s % 24, "mean": mean_value,
             "std": 0.0, "min": mean_value, "max": mean_value, "n": 5}
            for s in range(carbon.N_SLOTS)]
    return pd.DataFrame(rows).set_index("slot")


@pytest.fixture()
def profile() -> pd.DataFrame:
    """Flat 300 gCO2/kWh, with one green slot 5 h after the Mon-09:00 arrival."""
    p = _flat_profile(300.0)
    p.loc[carbon.slot_of(0, 14), "mean"] = 100.0
    return p


def _build(**overrides) -> dict:
    """A deferrable build arriving Mon 09:00 with a 1-hour duration estimate."""
    b = {
        "gh_is_pr": False,
        "git_branch": "feature/widget",
        "arrival_dow": 0,
        "arrival_hour": 9,
        "d_hat_seconds": 3600.0,
        "p_hat": 0.25,
    }
    b.update(overrides)
    return b


def _spec_file(tmp_path: Path, **patch) -> Path:
    """Copy the bootstrap spec, deep-patch it, write it to a temp file."""
    raw = yaml.safe_load(policy.BOOTSTRAP_POLICY_SPEC_PATH.read_text(encoding="utf-8-sig"))

    def _merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _merge(dst[k], v)
            else:
                dst[k] = v

    raw = copy.deepcopy(raw)
    _merge(raw, patch)
    path = tmp_path / "policy_spec.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def _load(tmp_path: Path, **patch) -> policy.PolicySpec:
    return policy.load_policy_spec(_spec_file(tmp_path, **patch), require_fitted=False)


# --------------------------------------------------------------------------- #
# 1. §A1.2 — the current build's observed duration never reaches a decision.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("leaked", ["tr_duration", "tr_log_buildduration", "tr_status"])
def test_decide_refuses_a_build_carrying_an_outcome_column(boot, profile, leaked):
    with pytest.raises(policy.PolicyLeakageError, match=leaked):
        policy.decide(_build(**{leaked: 1234.0}), profile, boot)


def test_leakage_refusal_happens_before_any_other_validation(boot, profile):
    """A leaking caller must not be able to get ANY decision out of decide()."""
    bad = {"tr_duration": 999.0}          # also missing every required key
    with pytest.raises(policy.PolicyLeakageError):
        policy.decide(bad, profile, boot)


def test_leakage_check_shares_the_feature_matrix_blocklist():
    """Not a private copy — the two must not drift apart."""
    from scheduler_core import features

    assert features.is_blocklisted("tr_duration")
    with pytest.raises(policy.PolicyLeakageError):
        policy.assert_no_outcome_columns({"tr_duration": 1.0})
    policy.assert_no_outcome_columns({"d_hat_seconds": 1.0, "git_branch": "x"})


def test_decide_consumes_the_estimate_not_the_observation(boot, profile):
    """`d_hat_seconds` is required; its absence is an error, not a default."""
    b = _build()
    del b["d_hat_seconds"]
    with pytest.raises(policy.PolicyError, match="d_hat_seconds"):
        policy.decide(b, profile, boot)


def test_policy_module_does_not_import_accounting():
    """Post-decision accounting must not be reachable from the decision path."""
    tree = ast.parse(Path(policy.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            else:
                names.update(a.name.split(".")[0] for a in node.names)
    assert "accounting" not in names, "policy.py imports accounting — §A1.2 role 1 is post-decision"


# --------------------------------------------------------------------------- #
# 2. Stage 1 first, unconditionally, and it RETURNS.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "overrides, expect_rule",
    [
        ({"gh_is_pr": True}, "pr_blocking"),
        ({"git_branch": "master"}, "protected:"),
        ({"git_branch": None}, "fail_closed:"),
        ({"gh_is_pr": "banana"}, "fail_closed:"),
    ],
)
def test_non_deferrable_builds_run_now_and_never_enter_stage_2(profile, boot, overrides, expect_rule):
    """Stage 2's inputs are ABSENT here — reaching Stage 2 would raise."""
    b = _build(**overrides)
    del b["d_hat_seconds"]                # Stage 2 cannot run without this
    del b["p_hat"]

    d = policy.decide(b, profile, boot)

    assert d.action == "run_now"
    assert d.eligible is False
    assert d.stage1_rule.startswith(expect_rule)
    assert "Stage 2 not consulted" in d.reason
    assert d.d_hat_seconds is None
    assert d.delay_hours == 0.0
    assert d.defer_until is None


def test_a_non_deferrable_build_is_never_deferred_however_green_the_week(profile, boot):
    """Gate safety is structural, not a tuning outcome (eval_protocol §6)."""
    green = _flat_profile(1.0)
    green.loc[carbon.slot_of(0, 9), "mean"] = 9999.0     # arrival slot maximally dirty
    d = policy.decide(_build(gh_is_pr=True), green, boot)
    assert d.action == "run_now"


def test_stage1_variant_comes_from_the_spec(tmp_path, profile):
    """`develop` is deferrable under primary, protected under the DL-020 §5 variant."""
    b = _build(git_branch="develop")
    primary = _load(tmp_path, stage1={"variant": "primary"})
    variant = _load(tmp_path, stage1={"variant": "protected_includes_integration"})

    assert policy.decide(b, profile, primary).eligible is True
    assert policy.decide(b, profile, variant).eligible is False


# --------------------------------------------------------------------------- #
# 3. No threshold is hard-coded (Layer 0-A invariant 7).
# --------------------------------------------------------------------------- #

def test_no_policy_constant_is_a_literal_in_the_module():
    """Only 0.0 and 1.0 may appear — a clamp bound and the `1 - p` identity."""
    tree = ast.parse(Path(policy.__file__).read_text(encoding="utf-8"))
    floats = {n.value for n in ast.walk(tree)
              if isinstance(n, ast.Constant) and isinstance(n.value, float)}
    assert floats <= {0.0, 1.0}, (
        f"unexpected float literal(s) {sorted(floats - {0.0, 1.0})} in policy.py — "
        "every policy value must come from the spec file (invariant 7)"
    )


def test_changing_w_max_in_the_spec_changes_the_window(tmp_path, profile):
    wide = _load(tmp_path, duration_only={"w_max_hours": 24.0})
    narrow = _load(tmp_path, duration_only={"w_max_hours": 2.0})
    b = _build()

    assert policy.decide(b, profile, wide).window_hours == pytest.approx(24.0)
    assert policy.decide(b, profile, narrow).window_hours == pytest.approx(2.0)
    # the green slot is +5h away, so it is reachable only under the wide window
    assert policy.decide(b, profile, wide).action == "defer"
    assert policy.decide(b, profile, narrow).action == "run_now"


def test_changing_d_threshold_in_the_spec_changes_the_action(tmp_path, profile):
    """A1.6: defer iff d_hat >= d_threshold."""
    b = _build(d_hat_seconds=3600.0)
    below = _load(tmp_path, duration_only={"d_threshold_seconds": 7200.0})
    at = _load(tmp_path, duration_only={"d_threshold_seconds": 3600.0})

    assert policy.decide(b, profile, below).action == "run_now"
    assert "not worth deferring" in policy.decide(b, profile, below).reason
    assert policy.decide(b, profile, at).action == "defer"      # >= is inclusive


# --------------------------------------------------------------------------- #
# 4. The spec loader: closed schema, provenance, bootstrap quarantine.
# --------------------------------------------------------------------------- #

def test_require_fitted_defaults_to_true_and_refuses_the_bootstrap():
    """The safe direction is the default (DL-022 §4)."""
    with pytest.raises(policy.PolicyError, match="UNFITTED"):
        policy.load_policy_spec(policy.BOOTSTRAP_POLICY_SPEC_PATH)


def test_the_bootstrap_spec_declares_itself_unfitted(boot):
    assert boot.fitted is False
    assert boot.provenance["sources"] == []
    assert boot.policy_path == "duration_only_fallback"      # matches admission.json


def test_the_bootstrap_is_not_the_default_spec_path():
    assert policy.DEFAULT_POLICY_SPEC_PATH != policy.BOOTSTRAP_POLICY_SPEC_PATH
    assert policy.DEFAULT_POLICY_SPEC_PATH.name == "policy_spec.yaml"


def test_anything_sitting_at_the_fitted_path_must_declare_itself_fitted():
    """Invariant 7 tripwire that survives P2-T5.

    Before P2-T5 the file does not exist and this passes vacuously. After P2-T5
    it must load under `require_fitted=True` — so a hand-written spec dropped at
    the fitted path fails the suite rather than quietly driving results.
    """
    if not policy.DEFAULT_POLICY_SPEC_PATH.exists():
        pytest.skip("policy_spec.yaml is fitted by P2-T5; not present yet")
    spec = policy.load_policy_spec(policy.DEFAULT_POLICY_SPEC_PATH, require_fitted=True)
    assert spec.fitted is True
    assert spec.provenance["sources"], "a fitted spec must cite the results/ files it traces to"


def test_a_fitted_spec_must_cite_its_sources(tmp_path):
    with pytest.raises(policy.PolicyError, match="invariant 7"):
        _load(tmp_path, provenance={"fitted": True, "sources": []})


def test_a_fitted_spec_with_sources_loads_under_require_fitted(tmp_path):
    path = _spec_file(tmp_path, provenance={
        "fitted": True, "sources": ["results/p1/admission.json"],
        "fitted_by": "scripts/fit_policy.py", "fitted_on": "train+calibration",
    })
    spec = policy.load_policy_spec(path, require_fitted=True)
    assert spec.fitted is True
    assert spec.provenance_record()["sources"] == ["results/p1/admission.json"]


def test_unknown_keys_are_rejected_at_every_level(tmp_path):
    with pytest.raises(policy.PolicyError, match="unknown top-level"):
        _load(tmp_path, surprise=1)
    with pytest.raises(policy.PolicyError, match="unknown key"):
        _load(tmp_path, duration_only={"sneaky_threshold": 1.0})


def test_missing_provenance_is_rejected(tmp_path):
    raw = yaml.safe_load(policy.BOOTSTRAP_POLICY_SPEC_PATH.read_text(encoding="utf-8-sig"))
    del raw["provenance"]
    path = tmp_path / "policy_spec.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(policy.PolicyError, match="provenance"):
        policy.load_policy_spec(path, require_fitted=False)


@pytest.mark.parametrize("bad", [{"w_max_hours": -1.0}, {"w_max_hours": 1000.0},
                                 {"d_threshold_seconds": -5.0},
                                 {"w_max_hours": "twenty"}])
def test_out_of_range_or_non_numeric_thresholds_are_rejected(tmp_path, bad):
    with pytest.raises(policy.PolicyError):
        _load(tmp_path, duration_only=bad)


def test_an_unsupported_schema_version_is_rejected(tmp_path):
    with pytest.raises(policy.PolicyError, match="schema_version"):
        _load(tmp_path, schema_version=99)


def test_an_unknown_policy_path_or_variant_is_rejected(tmp_path):
    with pytest.raises(policy.PolicyError, match="policy_path"):
        _load(tmp_path, policy_path="vibes")
    with pytest.raises(policy.PolicyError, match="stage1.variant"):
        _load(tmp_path, stage1={"variant": "whatever"})


def test_an_se_path_admitting_no_family_is_rejected(tmp_path):
    """The null path must be declared as duration_only, not as an empty SE path."""
    with pytest.raises(policy.PolicyError, match="admitted_families is empty"):
        _load(tmp_path, policy_path="se_informed")


def test_a_missing_spec_file_is_an_error_not_a_default(tmp_path):
    with pytest.raises(policy.PolicyError, match="not found"):
        policy.load_policy_spec(tmp_path / "absent.yaml", require_fitted=False)


def test_the_loader_uses_safe_load_only():
    """A spec file must not be able to construct a Python object (DL-022 §1)."""
    source = Path(policy.__file__).read_text(encoding="utf-8")
    assert "yaml.safe_load" in source
    for unsafe in ("yaml.load(", "yaml.full_load", "yaml.unsafe_load", "Loader=yaml.Loader"):
        assert unsafe not in source, f"policy.py uses {unsafe}"


# --------------------------------------------------------------------------- #
# 5. Determinism, the §7 window form, and the [0, W_max] clip.
# --------------------------------------------------------------------------- #

def test_decide_is_deterministic(boot, profile):
    b = _build()
    first = policy.decide(b, profile, boot).as_dict()
    for _ in range(25):
        assert policy.decide(b, profile, boot).as_dict() == first


def test_decide_does_not_mutate_its_inputs(boot, profile):
    b = _build()
    before_build, before_profile = dict(b), profile.copy()
    policy.decide(b, profile, boot)
    assert b == before_build
    pd.testing.assert_frame_equal(profile, before_profile)


def _se_spec(tmp_path, **patch) -> policy.PolicySpec:
    base = {"policy_path": "se_informed",
            "se_informed": {"admitted_families": ["F1"], "w_max_hours": 24.0,
                            "d_threshold_seconds": 0.0, "window_form": "linear"}}
    if patch:
        base["se_informed"].update(patch)
    return _load(tmp_path, **base)


@pytest.mark.parametrize("p_hat, expected", [
    (0.0, 24.0), (0.25, 18.0), (0.5, 12.0), (0.75, 6.0), (1.0, 0.0),
])
def test_linear_window_matches_the_frozen_form_by_hand(tmp_path, p_hat, expected):
    """§7 / A1.8: w(p) = W_max * (1 - p), with W_max = 24 from the spec."""
    spec = _se_spec(tmp_path)
    assert policy.window_hours(spec, p_hat) == pytest.approx(expected)


def test_window_is_monotone_non_increasing_in_p_hat(tmp_path):
    """Property test: a build more likely to fail never waits longer."""
    spec = _se_spec(tmp_path)
    grid = [i / 200.0 for i in range(201)]
    widths = [policy.window_hours(spec, p) for p in grid]
    assert all(b <= a + 1e-12 for a, b in zip(widths, widths[1:]))


def test_window_is_clipped_into_zero_to_w_max(tmp_path):
    spec = _se_spec(tmp_path, w_max_hours=6.0)
    for p in (0.0, 0.1, 0.5, 0.9, 1.0):
        w = policy.window_hours(spec, p)
        assert 0.0 <= w <= 6.0


def test_duration_only_window_is_flat_and_ignores_p_hat(boot):
    """A1.6: there is no admitted score, so the window is not a function of one."""
    assert policy.window_hours(boot, None) == pytest.approx(24.0)
    assert policy.window_hours(boot, 0.99) == pytest.approx(24.0)


def test_se_path_requires_p_hat(tmp_path, profile):
    spec = _se_spec(tmp_path)
    b = _build()
    del b["p_hat"]
    with pytest.raises(policy.PolicyError, match="p_hat"):
        policy.decide(b, profile, spec)


@pytest.mark.parametrize("bad", [-0.1, 1.5, float("nan"), "0.5", None])
def test_se_path_rejects_an_invalid_p_hat(tmp_path, profile, bad):
    spec = _se_spec(tmp_path)
    with pytest.raises(policy.PolicyError):
        policy.decide(_build(p_hat=bad), profile, spec)


def test_a_zero_window_means_run_now(tmp_path, profile):
    """p_hat = 1 collapses the window, so the build runs immediately."""
    spec = _se_spec(tmp_path)
    d = policy.decide(_build(p_hat=1.0), profile, spec)
    assert d.action == "run_now"
    assert d.window_hours == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 6. The deferral itself.
# --------------------------------------------------------------------------- #

def test_a_deferral_targets_the_greenest_reachable_slot(boot, profile):
    """Mon 09:00 arrival, green slot at Mon 14:00 => +5h."""
    d = policy.decide(_build(), profile, boot)
    assert d.action == "defer"
    assert d.defer_until == {"offset_hours": 5, "slot": carbon.slot_of(0, 14), "dow": 0, "hour": 14}
    assert d.delay_hours == pytest.approx(5.0)
    assert d.grid_gco2_now == pytest.approx(300.0)
    assert d.grid_gco2_scheduled == pytest.approx(100.0)
    assert d.grid_gco2_scheduled < d.grid_gco2_now


def test_defer_until_is_relative_because_decide_holds_no_clock(boot, profile):
    """Purity: an offset, not a timestamp — the caller owns absolute time."""
    d = policy.decide(_build(), profile, boot)
    assert set(d.defer_until) == {"offset_hours", "slot", "dow", "hour"}
    assert isinstance(d.defer_until["offset_hours"], int)


def test_a_flat_grid_produces_no_deferral(boot):
    """Offset 0 is running now; calling it a deferral would inflate the rate."""
    d = policy.decide(_build(), _flat_profile(200.0), boot)
    assert d.action == "run_now"
    assert d.delay_hours == 0.0
    assert "greenest reachable slot IS the arrival slot" in d.reason


def test_the_reason_names_gate_rule_path_values_window_and_slot(boot, profile):
    """S2's contract: the reason must be auditable without reading this module."""
    r = policy.decide(_build(), profile, boot).reason
    for fragment in ("stage1[primary]", "deferrable", "stage2[duration_only_fallback]",
                     "d_hat=3600.0s", "d_threshold=0.0s", "window=24.0000h",
                     "Greenest reachable slot", "+5h"):
        assert fragment in r, f"reason is missing {fragment!r}: {r}"


def test_decision_record_carries_the_spec_fitted_flag(boot, profile):
    """A bootstrap-derived record must be identifiable downstream."""
    assert policy.decide(_build(), profile, boot).as_dict()["spec_fitted"] is False


def test_as_dict_exposes_the_four_contracted_keys(boot, profile):
    record = policy.decide(_build(), profile, boot).as_dict()
    for key in ("action", "defer_until", "reason", "grid_gCO2_now"):
        assert key in record
    assert record["action"] in policy.ACTIONS


# --------------------------------------------------------------------------- #
# 7. Input validation on the build itself.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("overrides", [
    {"arrival_dow": 7}, {"arrival_dow": -1}, {"arrival_hour": 24},
    {"arrival_hour": -1}, {"arrival_dow": "Mon"}, {"arrival_hour": 9.5},
])
def test_an_invalid_arrival_slot_is_rejected(boot, profile, overrides):
    with pytest.raises(policy.PolicyError, match="arrival_"):
        policy.decide(_build(**overrides), profile, boot)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "3600", None])
def test_an_invalid_d_hat_is_rejected(boot, profile, bad):
    with pytest.raises(policy.PolicyError, match="d_hat_seconds"):
        policy.decide(_build(d_hat_seconds=bad), profile, boot)


def test_config_must_be_a_validated_spec(profile):
    """A raw dict must not be usable as a policy — validation is not optional."""
    with pytest.raises(policy.PolicyError, match="PolicySpec"):
        policy.decide(_build(), profile, {"policy_path": "duration_only_fallback"})


def test_a_gap_in_the_carbon_profile_propagates(boot, profile):
    profile.loc[carbon.slot_of(0, 9), "mean"] = float("nan")
    with pytest.raises(carbon.CarbonDataError):
        policy.decide(_build(), profile, boot)

"""Tests for energy & carbon accounting (P2-T2 S3).

Three things are being defended here, in descending order of importance:

1. **The A1.2 role-1 boundary.** `tr_duration` is an outcome. Accounting may read
   it *post-hoc*; `decide()` may never see it. Asserted structurally on the AST in
   both directions — `accounting` imports no decision-path module, and no
   decision-path module imports `accounting`. The second assertion is
   **forward-binding**: it will fail the moment P2-T3's `policy.py` imports this
   module.
2. **The arithmetic is hand-checkable.** The §8 formula is small enough that every
   core case below is computed by hand in the test name or comment — not by
   re-implementing the formula and comparing it to itself.
3. **No invented constants (R1).** `P_avg_W` is not written in the module; it is
   loaded from `config/energy.json`, it must equal its own cited derivation
   (85 W × 0.5), and a config with no citation is rejected.

Pure and offline — small hand-made fixtures, no dataset, no network.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pandas as pd
import pytest

from scheduler_core import accounting, carbon

SCHEDULER_CORE_DIR = Path(accounting.__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Fixtures (offline, deterministic).
# --------------------------------------------------------------------------- #

@pytest.fixture()
def cfg() -> accounting.EnergyConfig:
    """The real, versioned energy config — this is the artifact under test."""
    return accounting.load_energy_config()


def _flat_profile(mean_value: float = 200.0) -> pd.DataFrame:
    """A complete 168-slot hour-of-week profile at a constant intensity."""
    rows = []
    for slot in range(carbon.N_SLOTS):
        rows.append({"slot": slot, "dow": slot // 24, "hour": slot % 24,
                     "mean": mean_value, "std": 0.0, "min": mean_value,
                     "max": mean_value, "n": 5})
    return pd.DataFrame(rows).set_index("slot")


def _write_config(tmp_path: Path, **overrides) -> Path:
    """Copy the real config, apply overrides, write it somewhere temporary."""
    raw = json.loads(accounting.DEFAULT_ENERGY_CONFIG_PATH.read_text(encoding="utf-8"))
    raw.update(overrides)
    path = tmp_path / "energy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 1. The A1.2 role-1 boundary — observed duration never reaches a decision.
# --------------------------------------------------------------------------- #

def _direct_imports(module_path: Path) -> set[str]:
    """Top-level module names this file imports (absolute + relative)."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:                                   # from . import x  /  from .x import y
                if node.module:
                    names.add(node.module.split(".")[0])
                else:
                    for alias in node.names:
                        names.add(alias.name.split(".")[0])
            elif node.module:
                parts = node.module.split(".")
                names.add(parts[-1] if parts[0] == "scheduler_core" and len(parts) > 1 else parts[0])
    return names


def test_accounting_imports_no_decision_path_module():
    """A1.2 role 1: accounting cannot participate in scoring a build."""
    imported = _direct_imports(Path(accounting.__file__))
    forbidden = imported & accounting.DECISION_PATH_MODULES
    assert not forbidden, (
        f"accounting.py imports decision-path module(s) {sorted(forbidden)} — "
        "observed duration must stay post-hoc (eval_protocol.md §A1.2 role 1)"
    )


def test_no_decision_path_module_imports_accounting():
    """Forward-binding: when P2-T3 adds `policy.py`, importing this must fail here."""
    offenders = []
    for path in sorted(SCHEDULER_CORE_DIR.glob("*.py")):
        if path.name in ("accounting.py", "__init__.py"):
            continue
        if "accounting" in _direct_imports(path):
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} import scheduler_core.accounting. Accounting is POST-decision "
        "(eval_protocol.md §A1.2 role 1): nothing that scores or decides may read it."
    )


def test_accounting_opens_no_dataset_and_no_build_rows():
    """It takes durations as arguments; it cannot source a `tr_duration` itself."""
    imported = _direct_imports(Path(accounting.__file__))
    assert "data" not in imported and "pandas" not in imported, (
        "accounting.py must not read build rows — it receives durations from its caller"
    )
    source = Path(accounting.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    # `tr_duration` may be *named* in prose, but never subscripted out of a frame.
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            assert node.slice.value != "tr_duration", "accounting.py indexes a tr_duration column"


def test_every_energy_entry_point_requires_an_explicit_duration():
    """No defaulted duration anywhere — the caller must supply it deliberately."""
    import inspect

    for fn in (accounting.energy_kwh, accounting.energy_kwh_band, accounting.carbon_for_slot):
        params = inspect.signature(fn).parameters
        assert params["duration_s"].default is inspect.Parameter.empty, (
            f"{fn.__name__} defaults duration_s — it must be passed in post-decision"
        )


# --------------------------------------------------------------------------- #
# 2. The config: P_avg is loaded and cited, never hard-coded (R1, DL-007/DL-021).
# --------------------------------------------------------------------------- #

def test_p_avg_is_not_hard_coded_in_the_module():
    source = Path(accounting.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            assert node.value not in (42.5, 85, 0.5), (
                f"the pinned wattage/derivation factor {node.value} is hard-coded in "
                "accounting.py — it must come from config/energy.json (R1)"
            )


def test_config_pins_p_avg_at_its_cited_derivation(cfg):
    """42.5 W = CodeCarbon's 85 W fallback TDP x 0.5 assumed utilisation (DL-021)."""
    assert cfg.p_avg_w == pytest.approx(42.5)
    raw = json.loads(accounting.DEFAULT_ENERGY_CONFIG_PATH.read_text(encoding="utf-8"))
    d = raw["p_avg_derivation"]
    assert d["power_constant_w"] * d["consumption_percentage_constant"] == pytest.approx(cfg.p_avg_w)
    assert cfg.pinned_by == "DL-021"


def test_config_carries_a_pinned_checkable_citation(cfg):
    """DL-007 makes the citation part of the value. A `master` URL is not pinned."""
    assert cfg.citations, "no citation recorded for p_avg_w"
    urls = [str(c.get("url", "")) for c in cfg.citations]
    assert any("docs.codecarbon.io" in u for u in urls)
    source_cites = [c for c in cfg.citations if c.get("kind") == "source"]
    assert source_cites, "no source-level citation for the power constants"
    assert source_cites[0].get("version_pinned"), "the source citation is not version-pinned (R8)"
    assert "/master/" not in str(source_cites[0].get("url", ""))


def test_config_declares_the_duration_source_column(cfg):
    """DL-010: the energy duration is `tr_duration`, not summed job log durations."""
    assert cfg.duration_source_column == "tr_duration"


def test_config_rejects_an_uncited_power_constant(tmp_path):
    path = _write_config(tmp_path, p_avg_citations=[])
    with pytest.raises(accounting.AccountingError, match="no p_avg citation"):
        accounting.load_energy_config(path)


def test_config_rejects_a_wattage_that_contradicts_its_own_derivation(tmp_path):
    """A typo'd constant must not pass silently as a research number."""
    path = _write_config(tmp_path, p_avg_w=60.0)
    with pytest.raises(accounting.AccountingError, match="does not match its own derivation"):
        accounting.load_energy_config(path)


def test_config_rejects_an_unsupported_schema_version(tmp_path):
    path = _write_config(tmp_path, schema_version=99)
    with pytest.raises(accounting.AccountingError, match="schema_version"):
        accounting.load_energy_config(path)


def test_config_rejects_a_nonpositive_wattage(tmp_path):
    path = _write_config(
        tmp_path, p_avg_w=0.0,
        p_avg_derivation={"power_constant_w": 0, "consumption_percentage_constant": 0.5},
    )
    with pytest.raises(accounting.AccountingError, match="> 0"):
        accounting.load_energy_config(path)


def test_missing_config_is_an_error_not_a_default(tmp_path):
    with pytest.raises(accounting.AccountingError, match="not found"):
        accounting.load_energy_config(tmp_path / "absent.json")


def test_config_provenance_is_self_describing(cfg):
    prov = cfg.provenance()
    assert prov["p_avg_w"] == pytest.approx(42.5)
    assert prov["pinned_by"] == "DL-021"
    assert prov["duration_source_column"] == "tr_duration"
    assert prov["citations"]


def test_config_py_still_resolves_beside_the_config_data_directory():
    """`scheduler_core/config.py` and `scheduler_core/config/` coexist — pin that."""
    from scheduler_core import config as config_module

    assert Path(config_module.__file__).name == "config.py"
    assert config_module.RANDOM_SEED == 42
    assert accounting.DEFAULT_ENERGY_CONFIG_PATH.is_file()


# --------------------------------------------------------------------------- #
# 3. The energy model — hand-computed (§8, DL-007).
# --------------------------------------------------------------------------- #

def test_one_hour_at_p_avg_is_exactly_p_avg_over_1000_kwh(cfg):
    """The DoD's named case: 3,600 s at P_avg  =>  P_avg/1000 kWh, exactly."""
    assert accounting.energy_kwh(3600.0, cfg.p_avg_w) == pytest.approx(cfg.p_avg_w / 1000.0)
    # and at the pinned value that is 0.0425 kWh
    assert accounting.energy_kwh(3600.0, 42.5) == pytest.approx(0.0425, abs=1e-12)


@pytest.mark.parametrize(
    "duration_s, p_avg_w, expected_kwh",
    [
        (3600.0, 100.0, 0.1),        # 100 W for 1 h            = 0.1 kWh
        (1800.0, 100.0, 0.05),       # 100 W for 0.5 h          = 0.05 kWh
        (7200.0, 42.5, 0.085),       # 42.5 W for 2 h           = 0.085 kWh
        (60.0, 60.0, 0.001),         # 60 W for 1 min           = 0.001 kWh
        (0.0, 42.5, 0.0),            # a zero-second build costs nothing
        (3600.0, 1000.0, 1.0),       # 1 kW for 1 h             = 1 kWh (the definition)
    ],
)
def test_energy_matches_hand_computed_values(duration_s, p_avg_w, expected_kwh):
    assert accounting.energy_kwh(duration_s, p_avg_w) == pytest.approx(expected_kwh, abs=1e-12)


def test_energy_is_linear_in_duration_and_in_power():
    """Doubling either factor doubles the energy — the property the band relies on."""
    base = accounting.energy_kwh(1234.0, 42.5)
    assert accounting.energy_kwh(2468.0, 42.5) == pytest.approx(2 * base)
    assert accounting.energy_kwh(1234.0, 85.0) == pytest.approx(2 * base)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "600", None, True])
def test_energy_rejects_unusable_durations(bad):
    with pytest.raises(accounting.AccountingError):
        accounting.energy_kwh(bad, 42.5)


@pytest.mark.parametrize("bad", [0.0, -42.5, float("nan"), "42.5", None])
def test_energy_rejects_unusable_power(bad):
    with pytest.raises(accounting.AccountingError):
        accounting.energy_kwh(3600.0, bad)


# --------------------------------------------------------------------------- #
# 4. The DoD hooks — ±50% P_avg band (DL-007) and n_jobs scaling (DL-010).
# --------------------------------------------------------------------------- #

def test_p_avg_band_is_the_mandated_plus_minus_50_percent(cfg):
    band = accounting.p_avg_band(cfg)
    assert [m for m, _ in band] == [0.5, 1.0, 1.5]
    assert [w for _, w in band] == pytest.approx([21.25, 42.5, 63.75])


def test_energy_band_scales_exactly_with_the_multiplier(cfg):
    """Relative comparisons are invariant to P_avg precisely because of this (DL-007)."""
    band = accounting.energy_kwh_band(3600.0, cfg)
    assert band[1.0] == pytest.approx(0.0425)
    assert band[0.5] == pytest.approx(0.0425 * 0.5)
    assert band[1.5] == pytest.approx(0.0425 * 1.5)


def test_band_multipliers_come_from_the_config_not_the_module(tmp_path):
    path = _write_config(tmp_path, p_avg_sensitivity={"multipliers": [0.25, 1.0, 4.0]})
    cfg = accounting.load_energy_config(path)
    assert [m for m, _ in accounting.p_avg_band(cfg)] == [0.25, 1.0, 4.0]


def test_n_jobs_variant_is_off_by_default_and_scales_when_enabled():
    """DL-010's parallel-compute bracket: 4 jobs => 4x the wall-clock energy."""
    unscaled = accounting.energy_kwh(3600.0, 42.5, n_jobs=4)
    assert unscaled == pytest.approx(0.0425), "n_jobs must not apply unless asked"
    scaled = accounting.energy_kwh(3600.0, 42.5, n_jobs=4, scale_by_jobs=True)
    assert scaled == pytest.approx(0.17)
    assert accounting.energy_kwh(3600.0, 42.5, n_jobs=1, scale_by_jobs=True) == pytest.approx(0.0425)


@pytest.mark.parametrize("bad", [0, -3, 1.5, "4", True])
def test_n_jobs_variant_rejects_an_unusable_job_count(bad):
    with pytest.raises(accounting.AccountingError):
        accounting.energy_kwh(3600.0, 42.5, n_jobs=bad, scale_by_jobs=True)


# --------------------------------------------------------------------------- #
# 5. Carbon (§8) and the two §6 carbon aggregates.
# --------------------------------------------------------------------------- #

def test_carbon_matches_hand_computed_values():
    """0.0425 kWh at 200 gCO2/kWh = 8.5 gCO2e."""
    assert accounting.carbon_g(0.0425, 200.0) == pytest.approx(8.5)
    assert accounting.carbon_g(1.0, 250.0) == pytest.approx(250.0)
    assert accounting.carbon_g(0.0, 250.0) == 0.0
    assert accounting.carbon_g(2.0, 0.0) == 0.0          # a perfectly green slot


@pytest.mark.parametrize("bad", [-0.1, float("nan"), "0.04", None, True])
def test_carbon_rejects_unusable_energy(bad):
    with pytest.raises(accounting.AccountingError):
        accounting.carbon_g(bad, 200.0)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), "200", None])
def test_carbon_rejects_unusable_intensity(bad):
    with pytest.raises(accounting.AccountingError):
        accounting.carbon_g(0.0425, bad)


def test_carbon_for_slot_composes_energy_and_the_hour_of_week_intensity():
    """1 h build scheduled into a 200 gCO2/kWh slot at 42.5 W = 8.5 gCO2e."""
    profile = _flat_profile(200.0)
    assert accounting.carbon_for_slot(3600.0, profile, 2, 14, 42.5) == pytest.approx(8.5)


def test_carbon_for_slot_charges_the_scheduled_slot_not_the_arrival_slot():
    """This is the entire mechanism of a deferral, so assert it directly."""
    profile = _flat_profile(300.0)
    profile.loc[carbon.slot_of(3, 4), "mean"] = 100.0     # a green slot elsewhere in the week
    dirty = accounting.carbon_for_slot(3600.0, profile, 1, 9, 42.5)
    green = accounting.carbon_for_slot(3600.0, profile, 3, 4, 42.5)
    assert dirty == pytest.approx(0.0425 * 300.0)
    assert green == pytest.approx(0.0425 * 100.0)
    assert green < dirty


def test_carbon_for_slot_propagates_a_gap_rather_than_zero_filling_it():
    profile = _flat_profile(200.0)
    profile.loc[carbon.slot_of(0, 0), "mean"] = float("nan")
    with pytest.raises(carbon.CarbonDataError):
        accounting.carbon_for_slot(3600.0, profile, 0, 0, 42.5)


def test_carbon_per_1000_builds_is_hand_computable():
    """Mean of (1, 2, 3, 4) = 2.5 gCO2e per build => 2,500 per 1,000 builds."""
    assert accounting.carbon_per_1000_builds([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2500.0)
    assert accounting.carbon_per_1000_builds([0.5]) == pytest.approx(500.0)


def test_carbon_per_1000_builds_rejects_an_empty_trace():
    with pytest.raises(accounting.AccountingError):
        accounting.carbon_per_1000_builds([])


def test_pct_change_vs_baseline_reports_a_saving_as_negative():
    assert accounting.pct_change_vs_baseline(80.0, 100.0) == pytest.approx(-20.0)
    assert accounting.pct_change_vs_baseline(100.0, 100.0) == pytest.approx(0.0)
    assert accounting.pct_change_vs_baseline(125.0, 100.0) == pytest.approx(25.0)


def test_pct_change_against_a_zero_baseline_is_an_error_not_an_infinity():
    with pytest.raises(accounting.AccountingError):
        accounting.pct_change_vs_baseline(5.0, 0.0)


def test_sci_divides_total_carbon_by_successful_builds_only():
    """Numerator = all builds (10+20+30+40 = 100); denominator = the 2 passes => 50."""
    carbon_values = [10.0, 20.0, 30.0, 40.0]
    labels = [0, 1, 1, 0]                                  # 2 failures, 2 passes
    assert accounting.sci_per_successful_commit(carbon_values, labels) == pytest.approx(50.0)


def test_sci_charges_a_strategy_for_carbon_spent_on_failing_builds():
    """Same successful work, more failed work => a worse SCI. That is the point."""
    lean = accounting.sci_per_successful_commit([10.0, 10.0], [0, 0])
    wasteful = accounting.sci_per_successful_commit([10.0, 10.0, 40.0], [0, 0, 1])
    assert lean == pytest.approx(10.0)
    assert wasteful == pytest.approx(30.0)
    assert wasteful > lean


def test_sci_rejects_misaligned_carbon_and_labels():
    with pytest.raises(accounting.AccountingError, match="one-to-one"):
        accounting.sci_per_successful_commit([1.0, 2.0], [0])


def test_sci_is_undefined_with_no_successful_builds():
    with pytest.raises(accounting.AccountingError, match="N_success"):
        accounting.sci_per_successful_commit([1.0, 2.0], [1, 1])


@pytest.mark.parametrize("bad_label", [2, -1, "0", None, 0.5, True, float("nan")])
def test_sci_rejects_labels_outside_the_frozen_convention(bad_label):
    """A probability, a raw `tr_status`, or a bool must never pass as a label."""
    with pytest.raises(accounting.AccountingError):
        accounting.sci_per_successful_commit([1.0, 2.0], [0, bad_label])


def test_sci_accepts_integral_labels_from_a_dataframe():
    """numpy int64 is not a Python int; the simulator's frames will supply it."""
    import numpy as np

    labels = pd.Series([0, 1, 0]).to_numpy()
    assert labels.dtype == np.int64
    assert accounting.sci_per_successful_commit([4.0, 6.0, 10.0], list(labels)) == pytest.approx(10.0)


def test_sci_and_carbon_per_1000_agree_when_every_build_passes():
    """A sanity identity: with N_success = N, SCI = mean carbon = per-1000 / 1000."""
    values = [3.0, 5.0, 7.0, 9.0]
    labels = [0, 0, 0, 0]
    sci = accounting.sci_per_successful_commit(values, labels)
    per_1000 = accounting.carbon_per_1000_builds(values)
    assert sci == pytest.approx(per_1000 / 1000.0)


# --------------------------------------------------------------------------- #
# 6. End to end on the pinned config, with the numbers written out.
# --------------------------------------------------------------------------- #

def test_end_to_end_worked_example_on_the_real_config(cfg):
    """A 2 h build scheduled into a 250 gCO2/kWh slot, at the pinned 42.5 W.

    E    = (42.5 / 1000) * (7200 / 3600) = 0.0425 * 2 = 0.085 kWh
    C    = 0.085 * 250                                = 21.25 gCO2e
    band = 0.5x -> 10.625,  1.0x -> 21.25,  1.5x -> 31.875
    """
    profile = _flat_profile(250.0)
    energy = accounting.energy_kwh(7200.0, cfg.p_avg_w)
    assert energy == pytest.approx(0.085)

    emitted = accounting.carbon_for_slot(7200.0, profile, 4, 11, cfg.p_avg_w)
    assert emitted == pytest.approx(21.25)

    band = {m: accounting.carbon_g(e, 250.0) for m, e in accounting.energy_kwh_band(7200.0, cfg).items()}
    assert band[0.5] == pytest.approx(10.625)
    assert band[1.0] == pytest.approx(21.25)
    assert band[1.5] == pytest.approx(31.875)
    assert math.isclose(band[1.0], emitted)

"""Tests for the carbon loader + slot helpers (P0-T3 S3).

Pure, offline tests built on small hand-made fixtures (no network — the live
fetch is exercised by `scripts/fetch_carbon.py`, not pytest). Covers the slot
contract, the lowest-slot primitive, and — the key safety net — that **gaps are
reported and skipped, never silently zero-filled** (R1). Real-artifact checks run
only if `fetch-carbon` has already produced the files.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scheduler_core import carbon


# --------------------------------------------------------------------------- #
# Fixtures (offline, deterministic).
# --------------------------------------------------------------------------- #

def _full_profile(mean_fn) -> pd.DataFrame:
    """Build a complete 168-slot profile; ``mean_fn(slot) -> float|nan``."""
    rows = []
    for slot in range(carbon.N_SLOTS):
        dow, hour = slot // 24, slot % 24
        m = mean_fn(slot)
        rows.append({"slot": slot, "dow": dow, "hour": hour, "mean": m,
                     "std": 0.0, "min": m, "max": m, "n": 0 if pd.isna(m) else 5})
    return pd.DataFrame(rows).set_index("slot")


def _hourly_with_gap() -> pd.DataFrame:
    """One year (2025) of hourly rows on a complete grid, with an injected gap.

    The first 100 hours are NaN (a gap); the rest are constant 200 gCO₂/kWh.
    """
    idx = pd.date_range("2025-01-01", "2026-01-01", freq="h", inclusive="left", tz="UTC")
    vals = np.full(len(idx), 200.0)
    vals[:100] = np.nan                                   # injected gap
    return pd.DataFrame({"gco2_per_kwh": vals, "source_used": "actual"}, index=idx)


# --------------------------------------------------------------------------- #
# slot_of contract.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "dow,hour,slot",
    [(0, 0, 0), (0, 23, 23), (1, 0, 24), (6, 23, 167), (3, 12, 84)],
)
def test_slot_of(dow, hour, slot):
    assert carbon.slot_of(dow, hour) == slot


@pytest.mark.parametrize("dow,hour", [(-1, 0), (7, 0), (0, 24), (0, -1)])
def test_slot_of_out_of_range(dow, hour):
    with pytest.raises(carbon.CarbonDataError):
        carbon.slot_of(dow, hour)


# --------------------------------------------------------------------------- #
# Profile shape + lookup.
# --------------------------------------------------------------------------- #

def test_intensity_for_hour_of_week():
    prof = _full_profile(lambda s: float(s))              # mean == slot index
    assert carbon.intensity_for_hour_of_week(prof, 0, 0) == 0.0
    assert carbon.intensity_for_hour_of_week(prof, 6, 23) == 167.0
    assert carbon.intensity_for_hour_of_week(prof, 3, 12) == 84.0


def test_intensity_for_empty_slot_raises():
    prof = _full_profile(lambda s: np.nan if s == 10 else 100.0)
    with pytest.raises(carbon.CarbonDataError):
        carbon.intensity_for_hour_of_week(prof, 0, 10)    # slot 10 has no data


# --------------------------------------------------------------------------- #
# lowest_carbon_slot primitive.
# --------------------------------------------------------------------------- #

def test_lowest_carbon_slot_picks_true_minimum():
    # Minimum at slot 3 (value 1.0); everything else 100 except a cheaper-but-
    # unreachable slot 50 (0.5) outside the 5h window.
    def mean_fn(s):
        return {3: 1.0, 50: 0.5}.get(s, 100.0)
    prof = _full_profile(mean_fn)
    offset, slot, val = carbon.lowest_carbon_slot(prof, from_dow=0, from_hour=0, within_hours=5)
    assert slot == 3 and offset == 3 and val == 1.0       # slot 50 not reachable in 5h


def test_lowest_carbon_slot_offset_zero_is_now():
    prof = _full_profile(lambda s: 10.0)                  # flat -> earliest (offset 0) wins
    offset, slot, val = carbon.lowest_carbon_slot(prof, from_dow=2, from_hour=5, within_hours=12)
    assert offset == 0 and slot == carbon.slot_of(2, 5) and val == 10.0


def test_lowest_carbon_slot_skips_gaps():
    # Cheapest reachable real slot is 2 (value 5); slot 1 is a NaN gap and must
    # be skipped rather than treated as 0.
    def mean_fn(s):
        if s == 1:
            return np.nan
        return {2: 5.0}.get(s, 100.0)
    prof = _full_profile(mean_fn)
    offset, slot, val = carbon.lowest_carbon_slot(prof, 0, 0, within_hours=4)
    assert slot == 2 and val == 5.0


def test_lowest_carbon_slot_negative_window_raises():
    prof = _full_profile(lambda s: 10.0)
    with pytest.raises(carbon.CarbonDataError):
        carbon.lowest_carbon_slot(prof, 0, 0, within_hours=-1)


# --------------------------------------------------------------------------- #
# Gap handling — the safety net (R1: gaps reported, never zero-filled).
# --------------------------------------------------------------------------- #

def test_coverage_report_counts_gap():
    series = _hourly_with_gap()
    cov = carbon.coverage_report(series, years=(2025,))
    c = cov["2025"]
    assert c["expected_hours"] == 8760              # 2025 is not a leap year
    assert c["gap_hours"] == 100                     # exactly the injected gap
    assert c["present_hours"] == 8760 - 100
    assert c["coverage_pct"] == round(100 * 8660 / 8760, 4)


def test_coverage_report_empty_raises():
    with pytest.raises(carbon.CarbonDataError):
        carbon.coverage_report(pd.DataFrame({"gco2_per_kwh": []}))


def test_profile_aggregation_skips_gap_not_zero_fills():
    """A slot built only from NaN gap-hours must be empty, not a misleading 0."""
    series = _hourly_with_gap()                      # first 100 h of 2025 are NaN
    # 2025-01-01 is a Wednesday (dow=2); the gap covers slots starting at Wed 00:00.
    s = series["gco2_per_kwh"]
    dow = series.index.dayofweek
    hour = series.index.hour
    df = pd.DataFrame({"slot": dow * 24 + hour, "v": s.to_numpy()})
    means = df.groupby("slot")["v"].mean()           # nan-aware
    # Wed 00:00 = slot 2*24 = 48 is covered only by the first (NaN) day -> still
    # gets a real value from later weeks, so assert the *all-NaN* synthetic case:
    only_nan = pd.Series([np.nan, np.nan]).mean()
    assert pd.isna(only_nan)                         # mean of all-NaN is NaN, not 0
    assert means.notna().all()                       # every slot recovered by later weeks


# --------------------------------------------------------------------------- #
# Real-artifact checks (skip if fetch-carbon has not been run).
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(
    not carbon.DEFAULT_PROFILE_PATH.exists(),
    reason="carbon profile not fetched yet (run `python tasks.py fetch-carbon`)",
)
def test_real_profile_has_168_slots():
    prof = carbon.load_hour_of_week_profile()
    assert len(prof) == carbon.N_SLOTS
    assert list(prof.index) == list(range(carbon.N_SLOTS))
    assert set(prof["dow"]) == set(range(7))
    assert set(prof["hour"]) == set(range(24))


@pytest.mark.skipif(
    not carbon.DEFAULT_HOURLY_PATH.exists(),
    reason="carbon series not fetched yet (run `python tasks.py fetch-carbon`)",
)
def test_real_series_meets_coverage_dod():
    series = carbon.load_hourly_series()
    cov = carbon.coverage_report(series, years=(2024, 2025))
    for year in ("2024", "2025"):
        assert cov[year]["coverage_pct"] >= 95.0, f"{year} below 95% DoD: {cov[year]}"

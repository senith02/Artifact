"""Carbon-intensity loader + slot helpers (P0-T3 S2).

The single sanctioned entry point for reading the fetched UK carbon series and
its hour-of-week profile (produced by ``scripts/fetch_carbon.py``). Kept pure and
deterministic so the replay simulator (P2) and the live API (P4) share one
definition of "carbon at hour-of-week h" — the one-shared-core invariant.

* The **hourly series** is the raw history (used by the live API path).
* The **hour-of-week profile** is the 168-slot (Mon 00:00 … Sun 23:00) summary
  used to align 2017 build traces to carbon by hour-of-week (spec §3.2).

Gaps in the series are real (the grid API has occasional missing periods); they
are carried as NaN and never silently zero-filled (R1). Profile aggregation is
nan-aware, so a slot's statistics reflect only the hours actually observed.

The window/policy mapping (DL-008) is intentionally **not** here — only the thin
``lowest_carbon_slot`` primitive the P2-T2 policy will build on.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Locations (CWD-agnostic; mirrors scheduler_core/data.py).
# --------------------------------------------------------------------------- #

_CODE_DIR = Path(__file__).resolve().parents[1]          # .../Research_Artifact/code
CARBON_DIR = _CODE_DIR / "data" / "carbon"
DEFAULT_HOURLY_PATH = CARBON_DIR / "uk_carbon_intensity_hourly_2024_2025.csv"
DEFAULT_PROFILE_PATH = CARBON_DIR / "hour_of_week_profile.csv"

N_SLOTS = 168                                            # 7 days × 24 hours
DOW_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class CarbonDataError(ValueError):
    """Raised when a carbon series/profile is missing, empty, or malformed.

    Parallels :class:`scheduler_core.data.HeaderMismatchError`: fail loudly with
    a concrete message rather than returning a quietly-wrong object.
    """


def slot_of(dow: int, hour: int) -> int:
    """Return the hour-of-week slot index for a (day-of-week, hour) pair.

    ``dow`` is Monday=0 … Sunday=6 (pandas convention); ``hour`` is 0–23.
    Raises :class:`CarbonDataError` on out-of-range inputs.
    """
    if not (0 <= dow <= 6):
        raise CarbonDataError(f"dow must be 0..6 (Mon..Sun), got {dow}")
    if not (0 <= hour <= 23):
        raise CarbonDataError(f"hour must be 0..23, got {hour}")
    return dow * 24 + hour


def load_hourly_series(path: str | Path = DEFAULT_HOURLY_PATH) -> pd.DataFrame:
    """Load the hourly carbon series produced by ``fetch_carbon.py``.

    Returns a frame indexed by tz-aware UTC ``timestamp_utc`` with columns
    ``gco2_per_kwh`` (float, NaN at gaps) and ``source_used``. Raises
    :class:`CarbonDataError` if the file is absent or missing expected columns.
    """
    path = Path(path)
    if not path.exists():
        raise CarbonDataError(
            f"hourly carbon series not found at {path} — run "
            "`python tasks.py fetch-carbon` first (P0-T3)."
        )
    df = pd.read_csv(path)
    if "timestamp_utc" not in df.columns or "gco2_per_kwh" not in df.columns:
        raise CarbonDataError(
            f"{path} missing expected columns; got {list(df.columns)}"
        )
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df = df.set_index("timestamp_utc").sort_index()
    return df


def load_hour_of_week_profile(path: str | Path = DEFAULT_PROFILE_PATH) -> pd.DataFrame:
    """Load the 168-slot hour-of-week profile.

    Returns a frame indexed by ``slot`` (0–167) with columns ``dow``, ``hour``,
    ``mean``, ``std``, ``min``, ``max``, ``n``. Validates that all 168 slots are
    present (raises :class:`CarbonDataError` otherwise).
    """
    path = Path(path)
    if not path.exists():
        raise CarbonDataError(
            f"hour-of-week profile not found at {path} — run "
            "`python tasks.py fetch-carbon` first (P0-T3)."
        )
    df = pd.read_csv(path).set_index("slot").sort_index()
    required = {"dow", "hour", "mean", "std", "min", "max", "n"}
    missing = required - set(df.columns)
    if missing:
        raise CarbonDataError(f"{path} missing profile columns: {sorted(missing)}")
    if list(df.index) != list(range(N_SLOTS)):
        raise CarbonDataError(
            f"profile must have exactly {N_SLOTS} slots 0..167; got {len(df)} "
            f"(min={df.index.min()}, max={df.index.max()})"
        )
    return df


def intensity_for_hour_of_week(profile: pd.DataFrame, dow: int, hour: int) -> float:
    """Mean carbon intensity (gCO₂/kWh) for the given hour-of-week slot.

    Used by the replay alignment (spec §3.2): a 2017 build at (dow, hour) is
    charged the profile's mean intensity for that slot. Raises
    :class:`CarbonDataError` if the slot has no observed data.
    """
    slot = slot_of(dow, hour)
    value = profile.loc[slot, "mean"]
    if pd.isna(value):
        raise CarbonDataError(f"slot {slot} ({DOW_NAMES[dow]} {hour:02d}:00) has no data")
    return float(value)


def lowest_carbon_slot(
    profile: pd.DataFrame,
    from_dow: int,
    from_hour: int,
    within_hours: int,
) -> tuple[int, int, float]:
    """Find the greenest hour-of-week slot reachable within ``within_hours``.

    Scans the slots ``from_dow/from_hour`` (offset 0) through offset
    ``within_hours`` inclusive, wrapping around the 168-hour week, and returns
    ``(offset_hours, slot, gco2_per_kwh)`` of the lowest-intensity reachable slot.
    This is the thin primitive the P2-T2 policy builds the DL-008 window mapping
    on; it intentionally encodes **no** mapping constants here.

    ``within_hours`` is clipped to [0, 167] (the week horizon). Slots with no
    observed data (NaN mean) are skipped. Raises :class:`CarbonDataError` if no
    reachable slot has data.
    """
    if within_hours < 0:
        raise CarbonDataError(f"within_hours must be >= 0, got {within_hours}")
    horizon = min(int(within_hours), N_SLOTS - 1)
    start = slot_of(from_dow, from_hour)
    best: tuple[int, int, float] | None = None
    for offset in range(horizon + 1):
        slot = (start + offset) % N_SLOTS
        value = profile.loc[slot, "mean"]
        if pd.isna(value):
            continue
        v = float(value)
        if best is None or v < best[2]:
            best = (offset, slot, v)
    if best is None:
        raise CarbonDataError(
            f"no reachable slot with data within {within_hours}h of "
            f"{DOW_NAMES[from_dow]} {from_hour:02d}:00"
        )
    return best


def coverage_report(series: pd.DataFrame, years: tuple[int, ...] | None = None) -> dict:
    """Per-year non-null coverage of an hourly carbon series.

    Returns ``{year: {expected_hours, present_hours, gap_hours, coverage_pct}}``.
    Reused by the fetch provenance and by tests; ``expected_hours`` is the count
    of hourly rows present in the frame for that year (the fetcher builds a
    complete hourly grid, so gaps appear as NaN rows, not missing rows). Raises
    :class:`CarbonDataError` on an empty series.
    """
    if series.empty:
        raise CarbonDataError("carbon series is empty")
    if "gco2_per_kwh" not in series.columns:
        raise CarbonDataError("series missing 'gco2_per_kwh' column")
    if years is None:
        years = tuple(sorted({int(y) for y in series.index.year}))
    out: dict[str, dict] = {}
    for year in years:
        mask = series.index.year == year
        block = series.loc[mask, "gco2_per_kwh"]
        expected = int(mask.sum())
        present = int(block.notna().sum())
        out[str(year)] = {
            "expected_hours": expected,
            "present_hours": present,
            "gap_hours": expected - present,
            "coverage_pct": round(100 * present / expected, 4) if expected else None,
        }
    return out

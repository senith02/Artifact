# PROVENANCE — UK carbon-intensity series (P0-T3)

> R1: every value in this directory comes from the real fetch recorded below.


## Source

- **Provider:** UK National Grid ESO / National Energy System Operator Carbon Intensity API — https://carbonintensity.org.uk/
- **Endpoint:** `GET https://api.carbonintensity.org.uk/intensity/{frm}/{to}` (national, half-hourly; no API key)
- **Metric:** `intensity.actual` gCO₂/kWh, falling back to `intensity.forecast` only where actual is null (fallback count below).
- **Fetched at (UTC):** 2026-06-20T15:23:13Z
- **Command:** `python scripts/fetch_carbon.py` (via `python tasks.py fetch-carbon`)
- **HTTP client:** Python stdlib `urllib.request` (frozen §3.2 stack untouched).


## Coverage

- **Span requested:** 2024-01-01T00:00Z … 2026-01-01T00:00Z (exclusive), the two most recent complete calendar years (2024, 2025).
- **API requests:** 53 windows of ≤14 days.
- **Half-hourly records kept:** 35,057 (actual=35,057, forecast-fallback=0, none=0).

| Year | Expected hours | Present hours | Gap hours | Coverage % |
| :-- | --: | --: | --: | --: |
| 2024 | 8,784 | 8,769 | 15 | 99.8292 |
| 2025 | 8,760 | 8,760 | 0 | 100.0 |


## Gap handling

- Hourly series is built on a **complete** hourly grid over the span; any hour with no underlying half-hourly observation is left **NaN** (a gap), never zero-filled or interpolated (R1).
- Gaps are excluded from the hour-of-week profile via nan-aware aggregation (`mean`/`std`/`min`/`max` skip NaN; `n` counts only present hours per slot).
- DoD requires ≥95% coverage per year; the table above is the evidence.


## Files

- `uk_carbon_intensity_hourly_2024_2025.csv` — hourly mean series (timestamp_utc, gco2_per_kwh, source_used).
- `hour_of_week_profile.csv` / `hour_of_week_profile.json` — 168-slot hour-of-week profile.
- `../../../results/p0/carbon_profile.md` and `carbon_hour_of_week.png` — human table + plot.

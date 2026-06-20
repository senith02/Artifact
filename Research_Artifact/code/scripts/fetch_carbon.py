"""P0-T3 S1 — fetch the UK national carbon-intensity series + hour-of-week profile.

One real run over the public Carbon Intensity API (carbonintensity.org.uk, no key)
fetches the **national** half-hourly series for the two most recent complete
calendar years (2024 + 2025), resamples it to hourly means, and derives the
168-slot **hour-of-week profile** used for replay alignment (spec §3.2) and the
live API path (P4).

Governance:
  * HTTP via the Python **stdlib** ``urllib.request`` — no dependency added to the
    frozen §3.2 stack, so no decision-log entry is needed for tooling.
  * **R1 — never invent numbers.** Every value on disk comes from this fetch.
    Gaps are left as gaps (NaN) and *counted*, never zero-filled or fabricated.
  * Window 2024+2025 is independent of the 2017 build traces: builds align to
    carbon by hour-of-week (a §3.2 design choice, booked as a threat to validity).

Run:  python scripts/fetch_carbon.py            (env: PYTHONPATH=.)
or:   python tasks.py fetch-carbon
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Locations (CWD-agnostic; mirrors scheduler_core/data.py path resolution).
# --------------------------------------------------------------------------- #

_CODE_DIR = Path(__file__).resolve().parents[1]          # .../Research_Artifact/code
_REPO_ROOT = _CODE_DIR.parent                            # .../Research_Artifact
CARBON_DIR = _CODE_DIR / "data" / "carbon"
RESULTS = _REPO_ROOT / "results" / "p0"

HOURLY_CSV = CARBON_DIR / "uk_carbon_intensity_hourly_2024_2025.csv"
PROFILE_CSV = CARBON_DIR / "hour_of_week_profile.csv"
PROFILE_JSON = CARBON_DIR / "hour_of_week_profile.json"
PROVENANCE_MD = CARBON_DIR / "PROVENANCE.md"
PROFILE_MD = RESULTS / "carbon_profile.md"
PROFILE_PNG = RESULTS / "carbon_hour_of_week.png"

# --------------------------------------------------------------------------- #
# Fetch parameters.
# --------------------------------------------------------------------------- #

API_BASE = "https://api.carbonintensity.org.uk"
ENDPOINT = "/intensity/{frm}/{to}"          # national half-hourly actual+forecast
SOURCE_URL = "https://carbonintensity.org.uk/"
USER_AGENT = "carbon-scheduler-research/0.1 (BSc research artifact; stdlib urllib)"

# Two most recent complete calendar years as of the run (2026-06-20): 2024, 2025.
SPAN_START = dt.datetime(2024, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
SPAN_END = dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc)   # exclusive
YEARS = (2024, 2025)
WINDOW_DAYS = 14            # API per-request range cap (verified: 14d -> 673 records)
RETRIES = 5
BACKOFF_S = 3.0            # linear backoff base between retries
TIMEOUT_S = 60

DOW_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _iso(t: dt.datetime) -> str:
    """Format a UTC datetime as the API's ``YYYY-MM-DDTHH:MMZ``."""
    return t.strftime("%Y-%m-%dT%H:%MZ")


def _fetch_window(frm: dt.datetime, to: dt.datetime) -> list[dict]:
    """Fetch one [frm, to) window with a bounded retry loop. Fails loudly."""
    url = API_BASE + ENDPOINT.format(frm=_iso(frm), to=_iso(to))
    last_err: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                payload = json.load(resp)
            return payload.get("data", [])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            last_err = exc
            wait = BACKOFF_S * attempt
            print(f"    ! window {_iso(frm)}..{_iso(to)} attempt {attempt}/{RETRIES} "
                  f"failed ({exc}); retrying in {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(
        f"Carbon API window {_iso(frm)}..{_iso(to)} failed after {RETRIES} attempts: {last_err}"
    )


def fetch_half_hourly() -> tuple[pd.DataFrame, dict]:
    """Fetch the full half-hourly series. Returns (frame, fetch-metadata).

    Frame is indexed by period-start UTC timestamp with columns:
      * ``gco2_per_kwh`` (float, NaN if neither actual nor forecast present),
      * ``src`` in {"actual", "forecast", "none"}.
    """
    records: dict[pd.Timestamp, dict] = {}
    n_requests = 0
    frm = SPAN_START
    while frm < SPAN_END:
        to = min(frm + dt.timedelta(days=WINDOW_DAYS), SPAN_END)
        data = _fetch_window(frm, to)
        n_requests += 1
        for rec in data:
            ts = pd.Timestamp(rec["from"])               # tz-aware UTC ("...Z")
            intensity = rec.get("intensity") or {}
            actual = intensity.get("actual")
            forecast = intensity.get("forecast")
            if actual is not None:
                val, src = float(actual), "actual"
            elif forecast is not None:
                val, src = float(forecast), "forecast"
            else:
                val, src = np.nan, "none"
            records[ts] = {"gco2_per_kwh": val, "src": src}   # dedupe on period start
        print(f"  fetched {_iso(frm)}..{_iso(to)}  (+{len(data)} records, "
              f"{len(records):,} unique so far)", flush=True)
        frm = to

    frame = pd.DataFrame.from_dict(records, orient="index").sort_index()
    frame.index.name = "ts"
    # Restrict to the target span [SPAN_START, SPAN_END) — the API returns one
    # leading period (…23:30) just before the requested start.
    start_ts = pd.Timestamp(SPAN_START)
    end_ts = pd.Timestamp(SPAN_END)
    frame = frame.loc[(frame.index >= start_ts) & (frame.index < end_ts)]
    meta = {
        "n_requests": n_requests,
        "half_hourly_records": int(len(frame)),
        "half_hourly_actual": int((frame["src"] == "actual").sum()),
        "half_hourly_forecast_fallback": int((frame["src"] == "forecast").sum()),
        "half_hourly_none": int((frame["src"] == "none").sum()),
    }
    return frame, meta


def to_hourly(half: pd.DataFrame) -> pd.DataFrame:
    """Resample half-hourly -> hourly mean over a complete hourly grid.

    The reference grid is every hour in [SPAN_START, SPAN_END); hours with no
    underlying half-hourly value remain NaN (a documented gap, never filled).
    ``source_used`` summarises the contributing half-hours.
    """
    hour_key = half.index.floor("h")
    grp = half.groupby(hour_key)
    value = grp["gco2_per_kwh"].mean()                   # nan-aware mean

    def _src(s: pd.Series) -> str:
        kinds = set(s)
        present = {k for k in kinds if k in ("actual", "forecast")}
        if not present:
            return "none"
        if present == {"actual"}:
            return "actual"
        if present == {"forecast"}:
            return "forecast"
        return "mixed"

    src = grp["src"].apply(_src)
    hourly = pd.DataFrame({"gco2_per_kwh": value, "source_used": src})

    full_index = pd.date_range(
        start=pd.Timestamp(SPAN_START), end=pd.Timestamp(SPAN_END), freq="h",
        inclusive="left", tz="UTC",
    )
    hourly = hourly.reindex(full_index)
    hourly["source_used"] = hourly["source_used"].fillna("none")
    hourly.index.name = "timestamp_utc"
    return hourly


def coverage_per_year(hourly: pd.DataFrame) -> dict:
    """Per-year non-null coverage % over the expected hourly grid."""
    out: dict[str, dict] = {}
    for year in YEARS:
        mask = hourly.index.year == year
        block = hourly.loc[mask, "gco2_per_kwh"]
        expected = int(mask.sum())
        present = int(block.notna().sum())
        out[str(year)] = {
            "expected_hours": expected,
            "present_hours": present,
            "gap_hours": expected - present,
            "coverage_pct": round(100 * present / expected, 4) if expected else None,
        }
    return out


def hour_of_week_profile(hourly: pd.DataFrame) -> pd.DataFrame:
    """168-slot hour-of-week profile (Mon 00:00 … Sun 23:00), nan-aware."""
    s = hourly["gco2_per_kwh"]
    dow = hourly.index.dayofweek                          # Mon=0 … Sun=6
    hour = hourly.index.hour
    slot = dow * 24 + hour
    df = pd.DataFrame({"slot": slot, "dow": dow, "hour": hour, "gco2_per_kwh": s.to_numpy()})
    grp = df.groupby("slot")["gco2_per_kwh"]
    profile = pd.DataFrame({
        "mean": grp.mean(),
        "std": grp.std(),
        "min": grp.min(),
        "max": grp.max(),
        "n": grp.count(),
    })
    profile = profile.reindex(range(168))                 # guarantee all 168 slots
    profile.insert(0, "dow", [i // 24 for i in range(168)])
    profile.insert(1, "dow_name", [DOW_NAMES[i // 24] for i in range(168)])
    profile.insert(2, "hour", [i % 24 for i in range(168)])
    profile.index.name = "slot"
    for c in ("mean", "std", "min", "max"):
        profile[c] = profile[c].round(3)
    profile["n"] = profile["n"].fillna(0).astype(int)
    return profile


def _write_provenance(meta: dict, cov: dict, run_iso: str) -> None:
    lines: list[str] = []
    lines.append("# PROVENANCE — UK carbon-intensity series (P0-T3)\n")
    lines.append("> R1: every value in this directory comes from the real fetch recorded below.\n")
    lines.append("\n## Source\n")
    lines.append(f"- **Provider:** UK National Grid ESO / National Energy System Operator "
                 f"Carbon Intensity API — {SOURCE_URL}")
    lines.append(f"- **Endpoint:** `GET {API_BASE}{ENDPOINT}` (national, half-hourly; no API key)")
    lines.append(f"- **Metric:** `intensity.actual` gCO₂/kWh, falling back to `intensity.forecast` "
                 "only where actual is null (fallback count below).")
    lines.append(f"- **Fetched at (UTC):** {run_iso}")
    lines.append(f"- **Command:** `python scripts/fetch_carbon.py` (via `python tasks.py fetch-carbon`)")
    lines.append(f"- **HTTP client:** Python stdlib `urllib.request` (frozen §3.2 stack untouched).\n")
    lines.append("\n## Coverage\n")
    lines.append(f"- **Span requested:** {_iso(SPAN_START)} … {_iso(SPAN_END)} (exclusive), "
                 f"the two most recent complete calendar years (2024, 2025).")
    lines.append(f"- **API requests:** {meta['n_requests']} windows of ≤{WINDOW_DAYS} days.")
    lines.append(f"- **Half-hourly records kept:** {meta['half_hourly_records']:,} "
                 f"(actual={meta['half_hourly_actual']:,}, "
                 f"forecast-fallback={meta['half_hourly_forecast_fallback']:,}, "
                 f"none={meta['half_hourly_none']:,}).\n")
    lines.append("| Year | Expected hours | Present hours | Gap hours | Coverage % |")
    lines.append("| :-- | --: | --: | --: | --: |")
    for year in YEARS:
        c = cov[str(year)]
        lines.append(f"| {year} | {c['expected_hours']:,} | {c['present_hours']:,} | "
                     f"{c['gap_hours']:,} | {c['coverage_pct']} |")
    lines.append("")
    lines.append("\n## Gap handling\n")
    lines.append("- Hourly series is built on a **complete** hourly grid over the span; any hour with "
                 "no underlying half-hourly observation is left **NaN** (a gap), never zero-filled or "
                 "interpolated (R1).")
    lines.append("- Gaps are excluded from the hour-of-week profile via nan-aware aggregation "
                 "(`mean`/`std`/`min`/`max` skip NaN; `n` counts only present hours per slot).")
    lines.append("- DoD requires ≥95% coverage per year; the table above is the evidence.\n")
    lines.append("\n## Files\n")
    lines.append(f"- `{HOURLY_CSV.name}` — hourly mean series (timestamp_utc, gco2_per_kwh, source_used).")
    lines.append(f"- `{PROFILE_CSV.name}` / `{PROFILE_JSON.name}` — 168-slot hour-of-week profile.")
    lines.append(f"- `../../../results/p0/{PROFILE_MD.name}` and `{PROFILE_PNG.name}` — human table + plot.\n")
    PROVENANCE_MD.write_text("\n".join(lines), encoding="utf-8")


def _write_profile_md(profile: pd.DataFrame, cov: dict, meta: dict, run_iso: str) -> None:
    lines: list[str] = []
    lines.append("# Carbon hour-of-week profile (P0-T3)\n")
    lines.append(f"> Generated by `python scripts/fetch_carbon.py` (fetched {run_iso} UTC); "
                 "R1: every number from the real fetch.\n")
    lines.append(f"> Source: {SOURCE_URL} national series, 2024+2025; "
                 f"hourly grid, nan-aware 168-slot profile.\n")
    lines.append("\n## Per-year coverage\n")
    lines.append("| Year | Expected | Present | Gaps | Coverage % |")
    lines.append("| :-- | --: | --: | --: | --: |")
    for year in YEARS:
        c = cov[str(year)]
        lines.append(f"| {year} | {c['expected_hours']:,} | {c['present_hours']:,} | "
                     f"{c['gap_hours']:,} | {c['coverage_pct']} |")
    valid = profile["mean"].dropna()
    lines.append("\n## Profile summary (gCO₂/kWh)\n")
    lines.append(f"- Slots populated: **{int((profile['n'] > 0).sum())}/168**")
    lines.append(f"- Slot-mean range: **{valid.min():.1f} … {valid.max():.1f}** "
                 f"(overall mean {valid.mean():.1f})")
    greenest = profile.loc[valid.idxmin()]
    dirtiest = profile.loc[valid.idxmax()]
    lines.append(f"- Greenest slot: **{greenest['dow_name']} {int(greenest['hour']):02d}:00** "
                 f"= {greenest['mean']:.1f}")
    lines.append(f"- Dirtiest slot: **{dirtiest['dow_name']} {int(dirtiest['hour']):02d}:00** "
                 f"= {dirtiest['mean']:.1f}\n")
    lines.append("\n## Mean gCO₂/kWh by day × hour (rows = day, cols = hour 0–23)\n")
    header = "| Day | " + " | ".join(f"{h:02d}" for h in range(24)) + " |"
    sep = "| :-- | " + " | ".join("--:" for _ in range(24)) + " |"
    lines.append(header)
    lines.append(sep)
    for d in range(7):
        row = profile[profile["dow"] == d].sort_values("hour")
        cells = " | ".join(f"{v:.0f}" if pd.notna(v) else "—" for v in row["mean"])
        lines.append(f"| {DOW_NAMES[d]} | {cells} |")
    lines.append("")
    PROFILE_MD.write_text("\n".join(lines), encoding="utf-8")


def _write_profile_plot(profile: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")                                 # headless
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(13, 4.5))
    x = list(range(168))
    ax.plot(x, profile["mean"], color="#1b7837", lw=1.3, label="mean gCO₂/kWh")
    ax.fill_between(
        x,
        (profile["mean"] - profile["std"]).to_numpy(dtype=float),
        (profile["mean"] + profile["std"]).to_numpy(dtype=float),
        color="#1b7837", alpha=0.15, label="±1 std",
    )
    for d in range(1, 7):
        ax.axvline(d * 24, color="0.85", lw=0.8, zorder=0)
    ax.set_xticks([d * 24 + 12 for d in range(7)])
    ax.set_xticklabels(DOW_NAMES)
    ax.set_xlim(0, 167)
    ax.set_xlabel("hour of week (UTC)")
    ax.set_ylabel("carbon intensity (gCO₂/kWh)")
    ax.set_title("UK national grid — hour-of-week carbon-intensity profile (2024–2025)")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(PROFILE_PNG, dpi=130)
    plt.close(fig)


def main() -> int:
    # Windows consoles default to cp1252; our progress lines contain ≥ and ….
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")          # type: ignore[union-attr]

    run_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    CARBON_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    print(f"Fetching UK carbon intensity {_iso(SPAN_START)} … {_iso(SPAN_END)} "
          f"(stdlib urllib)…", flush=True)
    half, meta = fetch_half_hourly()
    hourly = to_hourly(half)
    cov = coverage_per_year(hourly)
    profile = hour_of_week_profile(hourly)

    # ---- persist series + profile ----------------------------------------- #
    hourly_out = hourly.copy()
    hourly_out["gco2_per_kwh"] = hourly_out["gco2_per_kwh"].round(3)
    hourly_out.to_csv(HOURLY_CSV)
    profile.to_csv(PROFILE_CSV)
    profile_payload = {
        "provenance": {
            "command": "python scripts/fetch_carbon.py",
            "fetched_utc": run_iso,
            "source": SOURCE_URL,
            "endpoint": API_BASE + ENDPOINT,
            "span": [_iso(SPAN_START), _iso(SPAN_END)],
            "years": list(YEARS),
            "metric": "intensity.actual (forecast fallback); gCO2/kWh",
        },
        "coverage_per_year": cov,
        "fetch_meta": meta,
        "profile": profile.reset_index().to_dict(orient="records"),
    }
    PROFILE_JSON.write_text(json.dumps(profile_payload, indent=2), encoding="utf-8")

    _write_provenance(meta, cov, run_iso)
    _write_profile_md(profile, cov, meta, run_iso)
    _write_profile_plot(profile)

    # ---- report + DoD check ------------------------------------------------ #
    print("\n=== coverage per year ===", flush=True)
    ok = True
    for year in YEARS:
        c = cov[str(year)]
        flag = "OK" if (c["coverage_pct"] or 0) >= 95.0 else "BELOW 95% !!"
        if (c["coverage_pct"] or 0) < 95.0:
            ok = False
        print(f"  {year}: {c['present_hours']:,}/{c['expected_hours']:,} hours "
              f"= {c['coverage_pct']}%  [{flag}]")
    print(f"\nwrote:\n  {HOURLY_CSV}\n  {PROFILE_CSV}\n  {PROFILE_JSON}\n"
          f"  {PROVENANCE_MD}\n  {PROFILE_MD}\n  {PROFILE_PNG}")
    if not ok:
        print("\n!! At least one year is below the 95% coverage DoD — see PROVENANCE.md. "
              "This is a gate blocker (would require a DL entry), not a silent pass.",
              file=sys.stderr)
        return 1
    print("\nDoD coverage check: PASS (both years ≥95%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

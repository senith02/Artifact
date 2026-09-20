"""P2-T2 — exercise the frozen energy/carbon model against the REAL carbon profile.

Produces `results/p2/energy_model.{json,md}`: the pinned `P_avg_W` with its
citation, the DL-007 ±50% band, the DL-010 `n_jobs` variant, and worked
energy/carbon figures computed against the **actual** P0-T3 hour-of-week
intensity profile (not a fixture). Every number in the P2-T2 report comes from
here or from `results/p2/pytest_p2_t2.txt` (R1).

⚠ This script reads **no build data at all** — only `code/data/carbon/` and
`scheduler_core/config/energy.json`. The test split is not opened, and neither is
the train or calibration split: durations below are *illustrative reference
durations*, chosen a priori (1 min / 10 min / 1 h / 2 h), not measurements drawn
from the corpus. Real per-build accounting happens in the P2-T4 replay.

Run from `code/`:   PYTHONPATH=. python scripts/report_energy_model.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scheduler_core import accounting, carbon

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "p2"

#: Reference durations, fixed a priori — NOT sampled from the dataset.
REFERENCE_DURATIONS_S: tuple[tuple[str, float], ...] = (
    ("1 minute", 60.0),
    ("10 minutes", 600.0),
    ("1 hour", 3600.0),
    ("2 hours", 7200.0),
)


def _extreme_slots(profile: pd.DataFrame) -> dict[str, dict[str, object]]:
    """The greenest and dirtiest observed hour-of-week slots in the real profile."""
    observed = profile.dropna(subset=["mean"])
    out: dict[str, dict[str, object]] = {}
    for name, slot in (("greenest", observed["mean"].idxmin()), ("dirtiest", observed["mean"].idxmax())):
        row = profile.loc[slot]
        out[name] = {
            "slot": int(slot),
            "dow": int(row["dow"]),
            "hour": int(row["hour"]),
            "label": f"{carbon.DOW_NAMES[int(row['dow'])]} {int(row['hour']):02d}:00",
            "gco2_per_kwh": float(row["mean"]),
        }
    return out


def main() -> None:
    cfg = accounting.load_energy_config()
    profile = carbon.load_hour_of_week_profile()
    extremes = _extreme_slots(profile)
    green, dirty = extremes["greenest"], extremes["dirtiest"]

    report: dict[str, object] = {
        "task": "P2-T2",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "energy_config": cfg.provenance(),
        "p_avg_band_w": {str(m): w for m, w in accounting.p_avg_band(cfg)},
        "carbon_profile_slots_observed": int(profile["mean"].notna().sum()),
        "extreme_slots": extremes,
        "dataset_rows_read": 0,
        "worked_examples": [],
        "p_avg_band_example": {},
        "n_jobs_variant_example": {},
    }

    for label, seconds in REFERENCE_DURATIONS_S:
        kwh = accounting.energy_kwh(seconds, cfg.p_avg_w)
        row = {
            "duration_label": label,
            "duration_s": seconds,
            "energy_kwh": kwh,
            "carbon_g_greenest_slot": accounting.carbon_for_slot(
                seconds, profile, green["dow"], green["hour"], cfg.p_avg_w),
            "carbon_g_dirtiest_slot": accounting.carbon_for_slot(
                seconds, profile, dirty["dow"], dirty["hour"], cfg.p_avg_w),
        }
        row["carbon_g_saved_if_shifted"] = row["carbon_g_dirtiest_slot"] - row["carbon_g_greenest_slot"]
        row["pct_change_if_shifted"] = accounting.pct_change_vs_baseline(
            row["carbon_g_greenest_slot"], row["carbon_g_dirtiest_slot"])
        report["worked_examples"].append(row)

    one_hour = 3600.0
    report["p_avg_band_example"] = {
        "duration_s": one_hour,
        "slot": dirty["label"],
        "gco2_per_kwh": dirty["gco2_per_kwh"],
        "carbon_g_by_multiplier": {
            str(m): accounting.carbon_g(e, dirty["gco2_per_kwh"])
            for m, e in accounting.energy_kwh_band(one_hour, cfg).items()
        },
    }
    report["n_jobs_variant_example"] = {
        "duration_s": one_hour,
        "slot": dirty["label"],
        "carbon_g_by_n_jobs": {
            str(n): accounting.carbon_g(
                accounting.energy_kwh(one_hour, cfg.p_avg_w, n_jobs=n, scale_by_jobs=True),
                dirty["gco2_per_kwh"])
            for n in (1, 2, 4, 8)
        },
        "note": "DL-010 optional variant, OFF by default; brackets the wall-clock under-count.",
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "energy_model.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    cite_doc, cite_src = cfg.citations[0], cfg.citations[1]
    lines: list[str] = [
        "# Energy & carbon model — as implemented (P2-T2)",
        "",
        f"Generated `{report['generated_utc']}` by `PYTHONPATH=. python scripts/report_energy_model.py`.",
        "Machine-readable twin: `energy_model.json`. Test evidence: `pytest_p2_t2.txt`.",
        "",
        "> **Provenance.** This run read the P0-T3 carbon profile and the energy config only.",
        "> **0 dataset rows were read** — no split was opened, and the reference durations below are",
        "> fixed a priori, not measurements from the corpus. Real per-build accounting is P2-T4's.",
        "",
        "## The model (eval_protocol.md §8; DL-007, DL-009, DL-010)",
        "",
        "```",
        "E_kWh    = (P_avg_W / 1000) * (duration_s / 3600)",
        "carbon_g = E_kWh * I(t_scheduled)",
        "SCI      = (sum_b E_b * I(t_sched,b)) / N_success        [gCO2e per successful commit]",
        "```",
        "",
        f"`duration_s` = `{cfg.duration_source_column}` — build wall-clock seconds, max-aggregated per",
        "DL-009 (DL-010). Permitted here under **§A1.2 role 1 (accounting): post-hoc only, never",
        "reaches `decide()`**. `I(·)` is the hour-of-week mean intensity from the P0-T3 profile",
        f"({report['carbon_profile_slots_observed']} of {carbon.N_SLOTS} slots observed).",
        "",
        "## The one value the protocol deferred: `P_avg_W`",
        "",
        f"**`P_avg_W` = {cfg.p_avg_w} W**, pinned by **{cfg.pinned_by}**. Derived, not asserted:",
        "",
        "| Factor | Value | Where |",
        "| :-- | :-- | :-- |",
        "| Global fallback TDP | `POWER_CONSTANT = 85` W | `codecarbon/external/hardware.py` L13 |",
        "| Assumed mean utilisation | `CONSUMPTION_PERCENTAGE_CONSTANT = 0.5` | same file, L15 |",
        "| Constant-mode power law | `power = self._tdp * CONSUMPTION_PERCENTAGE_CONSTANT` | same file, L256 |",
        "",
        f"⇒ 85 × 0.5 = **{cfg.p_avg_w} W**. `load_energy_config()` re-multiplies these factors and",
        "refuses a config whose `p_avg_w` does not reproduce them, so a typo cannot become a result.",
        "",
        "**Citations of record** (both accessed 2026-09-20):",
        "",
        f"- {cite_doc['work']} — <{cite_doc['url']}>",
        f"- {cite_src['work']}, pinned at **{cite_src['version_pinned']}** — <{cite_src['url']}>",
        "",
        "## Worked figures against the real profile",
        "",
        f"Greenest observed slot: **{green['label']}**, {green['gco2_per_kwh']:.4f} gCO₂/kWh.  ",
        f"Dirtiest observed slot: **{dirty['label']}**, {dirty['gco2_per_kwh']:.4f} gCO₂/kWh.",
        "",
        "| Duration | E (kWh) | gCO₂e @ dirtiest | gCO₂e @ greenest | Saved | % change |",
        "| :-- | --: | --: | --: | --: | --: |",
    ]
    for row in report["worked_examples"]:
        lines.append(
            f"| {row['duration_label']} | {row['energy_kwh']:.6f} | "
            f"{row['carbon_g_dirtiest_slot']:.4f} | {row['carbon_g_greenest_slot']:.4f} | "
            f"{row['carbon_g_saved_if_shifted']:.4f} | {row['pct_change_if_shifted']:.2f}% |"
        )
    lines += [
        "",
        "The right-hand columns are the **upper bound** on what perfect hour-of-week shifting could",
        "achieve for a single build. They are not a result: no scheduling decision, no eligibility gate",
        "and no delay constraint has been applied. Treat them as the arithmetic ceiling the P2-T4",
        "replay will fall short of.",
        "",
        "## The mandatory ±50% `P_avg` band (DL-007)",
        "",
        f"A 1-hour build at **{dirty['label']}** ({dirty['gco2_per_kwh']:.4f} gCO₂/kWh):",
        "",
        "| `P_avg` multiplier | `P_avg` (W) | gCO₂e |",
        "| :-- | --: | --: |",
    ]
    for m, w in accounting.p_avg_band(cfg):
        lines.append(f"| ×{m} | {w} | {report['p_avg_band_example']['carbon_g_by_multiplier'][str(m)]:.4f} |")
    lines += [
        "",
        "Carbon is **exactly linear** in `P_avg`, which is why *relative* strategy comparisons are",
        "invariant to it and *absolute* gCO₂e claims are not. Every carbon result in this study is",
        "reported across this band (P3-T4).",
        "",
        "## The DL-010 `n_jobs` variant (off by default)",
        "",
        f"Same 1-hour build at **{dirty['label']}**, scaled by job count:",
        "",
        "| `n_jobs` | gCO₂e |",
        "| --: | --: |",
    ]
    for n, g in report["n_jobs_variant_example"]["carbon_g_by_n_jobs"].items():
        lines.append(f"| {n} | {g:.4f} |")
    lines += [
        "",
        "## Estimation assumptions and threats (carry into P5-T4 §6)",
        "",
        "1. **`P_avg_W` is a documented default for an *unidentified* CPU, not a measurement of Travis",
        "   build hardware.** TravisTorrent records no hardware, no machine type and no power draw, so",
        "   this constant cannot be measured from the backbone dataset. A sharper-looking figure would",
        "   imply knowledge the corpus does not contain.",
        "2. **No RAM or GPU term.** 42.5 W is CodeCarbon's CPU-only constant-mode figure, applied here",
        "   as the whole-machine power. This biases **absolute** gCO₂e **downward**.",
        "3. **Wall-clock under-counts parallel compute (DL-010).** `tr_duration` is build wall-clock, so",
        "   a build whose jobs ran concurrently on separate machines is charged once. The `n_jobs`",
        "   variant above brackets this; it is reported *alongside* the `P_avg` band, never instead.",
        "4. **Constant power across the whole build.** No idle/ramp/utilisation profile is modelled —",
        "   energy is strictly linear in duration. This is what makes **carbon saved proportional to",
        "   duration by construction**, which is precisely why DL-013/§A1.13 rule the carbon channel",
        "   closed to RQ2 and route RQ2's power through TTFF instead. This assumption is load-bearing",
        "   for the study's central caveat, not a detail.",
        "5. **Intensity is a 2024–2025 hour-of-week *mean* applied to 2011–2016 builds** (P0-T3, spec",
        "   §3.2). The replay measures *shiftability under a modern grid's shape*, not the carbon those",
        "   builds actually emitted. Using the mean also suppresses within-slot variance, so realised",
        "   savings in a live deployment would be noisier in both directions.",
        "6. **The GSF embodied term `M` is excluded** from SCI — laptop-scale, no provisioned hardware",
        "   to amortise (eval_protocol §6). The reported SCI is the **operational** term only.",
        "7. **Marginal vs average intensity.** `I(·)` is average grid intensity. A real deferral changes",
        "   demand at the margin; the herding metric (§6) is the check on whether this study's",
        "   strategies concentrate load enough for that gap to matter.",
    ]
    (RESULTS_DIR / "energy_model.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"P_avg_W = {cfg.p_avg_w} W  (pinned by {cfg.pinned_by}, config {cfg.source_path})")
    print(f"band    = {dict(accounting.p_avg_band(cfg))}")
    print(f"profile = {report['carbon_profile_slots_observed']}/{carbon.N_SLOTS} slots observed")
    print(f"greenest {green['label']} {green['gco2_per_kwh']:.4f} | dirtiest {dirty['label']} {dirty['gco2_per_kwh']:.4f} gCO2/kWh")
    for row in report["worked_examples"]:
        print(f"  {row['duration_label']:>10}  E={row['energy_kwh']:.6f} kWh  "
              f"dirtiest={row['carbon_g_dirtiest_slot']:.4f} g  greenest={row['carbon_g_greenest_slot']:.4f} g  "
              f"({row['pct_change_if_shifted']:.2f}%)")
    print(f"dataset rows read: {report['dataset_rows_read']}")
    print(f"wrote {RESULTS_DIR / 'energy_model.json'}")
    print(f"wrote {RESULTS_DIR / 'energy_model.md'}")


if __name__ == "__main__":
    main()

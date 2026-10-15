"""Dissertation figures (Chapters 4 and 5), redrawn from saved result files only.

Reads results/ and code/data/carbon/ and writes print-ready copies of every data chart to
dissertation/figures/ as a 300-dpi PNG (for Word: Insert > Pictures) and an SVG. Nothing is
recomputed: every plotted value is read from the file named beside its figure below, so the
figures cannot disagree with the tables in the chapters.

Run from code/:  python scripts/make_dissertation_figures.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

CODE = Path(__file__).resolve().parents[1]
ROOT = CODE.parent
RES = ROOT / "results"
OUT = ROOT / "dissertation" / "figures"

# Validated categorical slots 1-3 (dataviz palette; all-pairs CVD-safe), ink and chrome.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, AXIS, GREY = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#a9a79f"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

WIDTH_IN = 6.3  # A4 text width (16 cm) so the figure needs no scaling in Word

plt.rcParams.update({
    "font.family": ["Segoe UI", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK2,
    "axes.titlecolor": INK,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "svg.fonttype": "none",  # keep text editable in the SVG
})

FAMILY_NAMES = {
    "F1": "F1 Change size and spread",
    "F2": "F2 Change purpose and file mix",
    "F3": "F3 Test activity and maturity",
    "F4": "F4 Project history and maturity",
    "F5": "F5 Developer and team",
    "F6": "F6 Timing and trigger",
}


def _load(rel: str) -> dict:
    return json.loads((RES / rel).read_text(encoding="utf-8"))


def _axes(ax, grid_axis: str = "both") -> None:
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _save(fig, stem: str, written: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext, kw in (("png", {"dpi": 300}), ("svg", {})):
        fig.savefig(OUT / f"{stem}.{ext}", facecolor="white", bbox_inches="tight", pad_inches=0.08, **kw)
    plt.close(fig)
    written.append(stem)


# --------------------------------------------------------------------------- #
# Chapter 4
# --------------------------------------------------------------------------- #

def fig_4_11_eligibility(written: list[str]) -> None:
    """results/p2/eligibility_gate.json, primary variant, by_rule."""
    g = _load("p2/eligibility_gate.json")
    s = next(v["summary"] for v in g["variants"] if v["variant"] == "primary")
    by = s["by_rule"]
    other = sum(n for r, n in by.items() if r.startswith("protected:") and r != "protected:mainline")
    rows = [
        ("Main branch (must run now)", by["protected:mainline"], GREY),
        ("Unprotected push (may wait)", by["push_to_unprotected_branch"], BLUE),
        ("Pull request (must run now)", by["pr_blocking"], GREY),
        ("Other protected branch (must run now)", other, GREY),
    ]
    assert sum(r[1] for r in rows) == s["builds"]
    total = s["builds"]
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.3))
    y = np.arange(len(rows))[::-1]
    ax.barh(y, [r[1] for r in rows], color=[r[2] for r in rows], height=0.62)
    for yi, (_, n, _) in zip(y, rows):
        ax.text(n + total * 0.008, yi, f"{n:,}  ({100 * n / total:.1f}%)", va="center", color=INK, fontsize=8.5)
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(0, total * 0.66)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:,.0f}k"))
    ax.set_xlabel(f"Builds (training + calibration projects, n = {total:,})")
    _axes(ax, "x")
    _save(fig, "fig4_11_eligibility_outcomes", written)


def fig_4_14_family_added_value(written: list[str]) -> None:
    """results/p1/ablation/deltas.json, families.*.delta_vs_control.pr_auc."""
    d = _load("p1/ablation/deltas.json")
    floor = d["model_floor_used_as_trigger"]["abs_floor"]
    fams = list(FAMILY_NAMES)
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.9))
    y = np.arange(len(fams))[::-1]
    for yi, f in zip(y, fams):
        p = d["families"][f]["delta_vs_control"]["pr_auc"]
        ax.plot([p["ci_lo"], p["ci_hi"]], [yi, yi], color=BLUE, lw=2, solid_capstyle="round")
        ax.scatter([p["delta"]], [yi], s=42, color=BLUE, edgecolors="white", linewidths=1.5, zorder=3)
        ax.text(p["ci_lo"] - 0.0015, yi, f"{p['delta']:+.4f}".replace("-", "−"), va="center", ha="right",
                fontsize=8, color=INK)
    ax.axvline(0, color=INK2, lw=1)
    ax.axvline(floor, color=INK2, lw=1, ls=(0, (4, 3)))
    ax.text(floor + 0.0008, y[0] + 0.6, f"admission\nfloor +{floor:.2f}", fontsize=8, color=INK2, va="bottom")
    ax.text(-0.0008, y[0] + 0.6, "no\nchange", fontsize=8, color=INK2, va="bottom", ha="right")
    ax.set_yticks(y, [FAMILY_NAMES[f] for f in fams])
    ax.set_ylim(-0.6, len(fams) + 0.4)
    ax.set_xlim(-0.092, 0.03)
    ax.set_xlabel("Change in PR-AUC from adding the family to the duration estimate\n"
                  "(calibration projects; dot = estimate, line = 95% paired-bootstrap interval)")
    _axes(ax, "x")
    _save(fig, "fig4_14_family_added_value", written)


def fig_4_15_shap_families(written: list[str]) -> None:
    """results/p1/shap/shap_summary.json, per_family.*.mean_abs_contribution."""
    s = _load("p1/shap/shap_summary.json")["per_family"]
    items = [(FAMILY_NAMES[k], v["mean_abs_contribution"], BLUE) for k, v in s.items() if k != "control"]
    items.append(("Duration estimate (the control)", s["control"]["mean_abs_contribution"], INK2))
    items.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.8))
    y = np.arange(len(items))
    ax.barh(y, [r[1] for r in items], color=[r[2] for r in items], height=0.62)
    for yi, (_, v, _) in zip(y, items):
        ax.text(v + 0.004, yi, f"{v:.3f}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(y, [r[0] for r in items])
    ax.set_xlim(0, max(r[1] for r in items) * 1.15)
    ax.set_xlabel("Mean absolute SHAP contribution per build (log-odds), full XGBoost model,\n"
                  "calibration projects")
    _axes(ax, "x")
    _save(fig, "fig4_15_shap_by_family", written)


def fig_4_17_dev_tradeoff(written: list[str]) -> None:
    """results/p2/policy_fit/selection.json, primary.table (the 30 project-history points)."""
    p = _load("p2/policy_fit/selection.json")["primary"]
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 3.6))
    for w, col, ls in ((6.0, ORANGE, "-"), (12.0, AQUA, (0, (5, 2))), (24.0, BLUE, "-")):
        pts = sorted((r for r in p["table"] if r["param_w_max_hours"] == w),
                     key=lambda r: r["param_d_threshold_seconds"])
        ax.plot([r["saving_pct"] for r in pts], [r["ttff_p95_h_failed"] for r in pts], color=col, lw=2,
                ls=ls, marker="o", ms=4, label=f"window {w:.0f} h")
    ax.axvline(p["saving_floor_pct"], color=INK2, lw=1, ls=(0, (4, 3)))
    ax.text(p["saving_floor_pct"] - 0.03, 1.0, f"90% of best saving\n({p['saving_floor_pct']:.2f}%)",
            fontsize=8, color=INK2, ha="right", va="bottom")
    ax.scatter([p["saving_pct"]], [p["ttff_p95_h_failed"]], s=90, facecolors="none", edgecolors=INK, lw=1.5,
               zorder=4)
    ax.annotate(f"chosen: 480 s, 24 h\n{p['saving_pct']:.2f}% saved, {p['ttff_p95_h_failed']:.1f} h",
                (p["saving_pct"], p["ttff_p95_h_failed"]), xytext=(-12, 22), textcoords="offset points",
                ha="right", fontsize=8, color=INK, arrowprops={"arrowstyle": "-", "color": INK2, "lw": 0.8})
    ax.set_xlabel("Estimated carbon saved vs running every build immediately (%)")
    ax.set_ylabel("Failure feedback time,\n95th percentile (hours)")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left", labelcolor=INK2)
    _axes(ax)
    _save(fig, "fig4_17_development_tradeoff", written)


def fig_4_19_funnel(written: list[str]) -> None:
    """results/p0/data_profile.json, filter_funnel (steps that removed rows)."""
    f = _load("p0/data_profile.json")["filter_funnel"]
    names = {
        "raw job rows": "Raw job rows",
        "aggregate to builds (tr_build_id)": "Combined into builds",
        "drop builds with missing/other label": "Builds with a usable label",
        "exclude canceled builds": "Builds not cancelled (analysed)",
    }
    rows = [(names[s["step"]], s["rows_out"], s["dropped"]) for s in f if s["step"] in names]
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.3))
    y = np.arange(len(rows))[::-1]
    ax.barh(y, [r[1] for r in rows], color=[GREY] + [BLUE] * (len(rows) - 1), height=0.62)
    for i, (yi, (_, n, dropped)) in enumerate(zip(y, rows)):
        note = "" if i == 0 else f"   (−{dropped:,})"
        ax.text(n + 40_000, yi, f"{n:,}{note}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(0, rows[0][1] * 1.3)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e6:.1f}M"))
    ax.set_xlabel("Rows (grey = job rows; blue = builds)")
    _axes(ax, "x")
    _save(fig, "fig4_19_data_preparation_funnel", written)


def fig_4_20_carbon_heatmap(written: list[str]) -> None:
    """code/data/carbon/hour_of_week_profile.csv, column `mean`."""
    with open(CODE / "data" / "carbon" / "hour_of_week_profile.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    grid = np.full((7, 24), np.nan)
    days = [""] * 7
    for r in rows:
        grid[int(r["dow"]), int(r["hour"])] = float(r["mean"])
        days[int(r["dow"])] = r["dow_name"]
    cmap = LinearSegmentedColormap.from_list("blue_seq", BLUE_RAMP)
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.8))
    im = ax.imshow(grid, cmap=cmap, aspect="auto")
    lo, hi = np.unravel_index(np.nanargmin(grid), grid.shape), np.unravel_index(np.nanargmax(grid), grid.shape)
    for (r, c), txt, col in ((lo, f"{grid[lo]:.1f}", INK), (hi, f"{grid[hi]:.1f}", "white")):
        ax.add_patch(plt.Rectangle((c - 0.5, r - 0.5), 1, 1, fill=False, ec=INK, lw=1.4))
        ax.text(c, r, txt, ha="center", va="center", fontsize=6.5, color=col)
    ax.set_yticks(range(7), days)
    ax.set_xticks(range(0, 24, 2), [f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour of day (UTC)")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label("Mean g CO₂/kWh, 2024–2025", color=INK2)
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0, colors=INK2)
    _save(fig, "fig4_20_carbon_hour_of_week", written)


# --------------------------------------------------------------------------- #
# Chapter 5
# --------------------------------------------------------------------------- #

def fig_5_1_frontiers(written: list[str]) -> None:
    """results/p3/incremental_value_decision.json, populations.all (frontiers + frozen point)."""
    allp = _load("p3/incremental_value_decision.json")["populations"]["all"]
    series = (
        ("4a_duration_estimator", "Duration-only, regressor estimate", ORANGE, "-"),
        ("4_oracle_duration", "Perfect duration knowledge (theoretical)", AQUA, (0, (5, 2))),
        ("4b_duration_prior", "Proposed policy = duration-only, project history", BLUE, "-"),
    )
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 3.8))
    for key, name, col, ls in series:
        f = allp["frontiers"][key]
        ax.plot(f["saving"], f["ttff_p95_h"], color=col, lw=2, ls=ls, marker="o", ms=3, label=name)
    fz = allp["points"]["5_se_informed_policy__d480__w24"]
    ax.scatter([fz["saving_pct"]], [fz["ttff_p95_h"]], s=70, color=BLUE, edgecolors=INK, lw=1.2, zorder=5)
    ax.annotate(f"frozen policy (480 s, 24 h)\n{fz['saving_pct']:.3f}% saved, {fz['ttff_p95_h']:.2f} h",
                (fz["saving_pct"], fz["ttff_p95_h"]), xytext=(-70, 20), textcoords="offset points", ha="right",
                fontsize=8, color=INK, arrowprops={"arrowstyle": "-", "color": INK2, "lw": 0.8})
    ax.set_xlabel("Estimated carbon saved vs running every build immediately (%)")
    ax.set_ylabel("Failure feedback time,\n95th percentile (hours)")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(-0.02, -0.16), ncol=2, labelcolor=INK2)
    _axes(ax)
    _save(fig, "fig5_1_tradeoff_curves_test", written)


SWEEP_NAMES = {
    "baseline": "Main analysis",
    "S-a": "Stricter eligibility rules",
    "S-c x0.5": "Power figure × 0.5",
    "S-c x1.5": "Power figure × 1.5",
    "S-d": "Counting parallel jobs",
    "S-e early": "Earlier half of test period",
    "S-e late": "Later half of test period",
    "S-g": "Cold-start builds excluded",
    "S-h": "Last-50-builds control",
}


def fig_5_2_sensitivity(written: list[str]) -> None:
    """results/p3/sensitivity/*.json via scripts/sensitivity_report.rows (the V3 area per sweep)."""
    sys.path.insert(0, str(CODE / "scripts"))
    import sensitivity_report  # noqa: PLC0415

    R = sensitivity_report.rows(RES / "p3" / "sensitivity", RES / "p3")
    pts = [(SWEEP_NAMES[r["sweep"]], r["area"]) for r in R
           if r.get("area") and r["area"].get("point") is not None]
    assert len(pts) == len(SWEEP_NAMES), [r["sweep"] for r in R]
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 3.2))
    y = np.arange(len(pts))[::-1]
    for yi, (lab, a) in zip(y, pts):
        col = INK if lab == "Main analysis" else BLUE
        ax.plot([a["ci_lo"], a["ci_hi"]], [yi, yi], color=col, lw=2, solid_capstyle="round")
        ax.scatter([a["point"]], [yi], s=42, color=col, edgecolors="white", linewidths=1.5, zorder=3)
        ax.text(a["ci_hi"] + 0.08, yi, f"{a['point']:+.2f}", va="center", fontsize=8, color=INK)
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(y, [p[0] for p in pts])
    ax.set_xlim(-0.3, 7.3)
    ax.set_xlabel("Area between the two duration-only trade-off curves (percentage points × hours)\n"
                  "> 0 means project history beats the regressor; dot = estimate, line = 95% interval")
    _axes(ax, "x")
    _save(fig, "fig5_2_sensitivity_project_history_vs_regressor", written)


def main() -> None:
    written: list[str] = []
    for fn in (fig_4_11_eligibility, fig_4_14_family_added_value, fig_4_15_shap_families,
               fig_4_17_dev_tradeoff, fig_4_19_funnel, fig_4_20_carbon_heatmap,
               fig_5_1_frontiers, fig_5_2_sensitivity):
        fn(written)
    for w in written:
        print(f"wrote dissertation/figures/{w}.png + .svg")


if __name__ == "__main__":
    main()

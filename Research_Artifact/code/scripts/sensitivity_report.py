"""P3-T4 summary: results/p3/sensitivity.md + figures, from results/p3/sensitivity/*.json (DL-030).

Called by ``sensitivity_analysis.py --summary``. It reads the per-sweep JSON files and the
P3-T1/P3-T3 baselines and computes nothing new beyond comparisons against them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

V3_PAIR = "4a_duration_estimator|5_se_informed_policy"
CLASS_LABELS = ["⑤−① carbon", "⑤−① TTFF p95", "⑤−② carbon", "⑤−② TTFF p95",
                "⑤−③ carbon", "⑤−③ TTFF p95", "⑤−④a carbon", "⑤−④a TTFF p95"]

INK, INK2, MUTED, GRID_C, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, ORANGE = "#2a78d6", "#eb6834"


def _load(out: Path, name: str) -> dict | None:
    p = out / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _mark(stable: bool | None) -> str:
    if stable is None:
        return "n/a"
    return "stable" if stable else "**FLIPS**"


def _area(a: dict | None) -> str:
    if not a or a.get("point") is None:
        return "—"
    lo, hi = a.get("ci_lo"), a.get("ci_hi")
    ci = f" [{lo:+.4f}, {hi:+.4f}]" if lo is not None else ""
    return f"{a['point']:+.4f}{ci}"


def _v4_changes(v4: dict | None) -> str:
    if not v4:
        return ""
    diff = [f"{CLASS_LABELS[i]}: {b} → {c}" for i, (b, c) in
            enumerate(zip(v4["baseline"], v4["classes"])) if b != c]
    return "; ".join(diff)


def rows(out: Path, p3: Path) -> list[dict[str, Any]]:
    R: list[dict[str, Any]] = []
    iv = json.loads((p3 / "incremental_value_decision.json").read_text(encoding="utf-8"))
    base_area = iv["populations"]["all"]["pairs"][V3_PAIR]["area"]
    rep = json.loads((p3 / "model_report.json").read_text(encoding="utf-8"))
    R.append({"sweep": "baseline", "label": "Baseline (P3-T1 / P3-T2 / P3-T3 as frozen)",
              "V1": "{" + ", ".join(rep["admission"]["x1"]["admitted"]) + "}", "V2": "no",
              "V3": "yes", "V4": "reference", "area": base_area, "note": ""})

    def add(sweep: str, label: str, d: dict | None, *, v1: dict | None = None, v4: dict | None = None,
            note: str = "") -> None:
        if d is None:
            R.append({"sweep": sweep, "label": label, "V1": "pending", "V2": "pending",
                      "V3": "pending", "V4": "pending", "area": None, "note": note or "not run yet"})
            return
        R.append({"sweep": sweep, "label": label,
                  "V1": _mark(v1["stable"]) + f" ({'{' + ', '.join(v1['value']) + '}'})" if v1 else "n/a",
                  "V2": _mark(d["V2"]["stable"]) if "V2" in d else "n/a",
                  "V3": _mark(d["V3"]["stable"]) if "V3" in d else "n/a",
                  "V4": _mark(v4["stable"]) if v4 else "n/a",
                  "area": d.get("V3", {}).get("area"), "note": note or _v4_changes(v4)})

    a = _load(out, "a")
    add("S-a", "Deferrable fraction: stage-1 `protected_includes_integration`", a,
        v4=a["V4"] if a else None,
        note=(f"eligible share {100 * a['eligible_share']:.2f}%; " + _v4_changes(a["V4"])) if a else "")
    b = _load(out, "b")
    if b:
        for k, v in b["V4_by_w"].items():
            R.append({"sweep": f"S-b {k}", "label": f"`W_max` = {k[1:]} h (⑤, ④a, ③ at the same W)",
                      "V1": "n/a", "V2": "n/a (frontier spans W)", "V3": "n/a (frontier spans W)",
                      "V4": _mark(v["stable"]), "area": None,
                      "note": _v4_changes({"baseline": b["V4_by_w"]["w24"]["classes"] if k == "w24"
                                           else json.loads((out / "baseline.json").read_text(
                                               encoding="utf-8"))["v4"]["classes"],
                                           "classes": v["classes"]})})
        R.append({"sweep": "S-b banded", "label": "Banded window shape", "V1": "n/a", "V2": "n/a",
                  "V3": "n/a", "V4": "n/a", "area": None, "note": b["banded_window"]})
    else:
        add("S-b", "`W_max` ∈ {6, 12, 24}", None)
    c = _load(out, "c")
    for mult in ("x0.5", "x1.5"):
        d = c[mult] if c else None
        add(f"S-c {mult}", f"Energy `P_avg` {mult.replace('x', '×')}", d, v4=d["V4"] if d else None,
            note=(f"P_avg {d['p_avg_w']} W; carbon/1k at the frozen point "
                  f"{d['carbon_per_1000_frozen_point']:.1f} g") if d else "")
    dd = _load(out, "d")
    add("S-d", "`n_jobs`-scaled energy", dd, v4=dd["V4"] if dd else None,
        note="; ".join(x for x in (
            f"jobs per build: mean {dd['n_jobs']['mean']:.2f}, median {dd['n_jobs']['median']:.0f}, "
            f"single-job share {100 * dd['n_jobs']['share_single_job']:.1f}%",
            _v4_changes(dd["V4"])) if x) if dd else "")
    e = _load(out, "e")
    for per in ("early", "late"):
        d = e[per] if e else None
        add(f"S-e {per}", f"Temporal: {per} test builds (boundary {e['boundary_utc'][:10] if e else '—'})",
            d, v1=d["V1"] if d else None, note=f"{d['n_builds']:,} builds" if d else "")
    f = _load(out, "f")
    if f and f.get("status") == "run":
        add("S-f", f"Second grid: {f['zone']['zone']} (peak/trough {f['zone']['peak_to_trough']:.2f} "
            f"vs UK {f['zone']['uk_peak_to_trough']:.2f})", f, v4=f["V4"],
            note="RQ4 ranking invariance only (DL-027 §2); " + _v4_changes(f["V4"]))
    elif f:
        bp = f.get("by_product", {})
        R.append({"sweep": "S-f", "label": "Second grid profile (DL-027 §2)", "V1": "n/a",
                  "V2": "not run", "V3": "not run", "V4": "not run", "area": None,
                  "note": f"{f['status']}. CAISO peak/trough {bp.get('caiso_peak_to_trough', 0):.4f} "
                          f"vs UK {bp.get('uk_peak_to_trough', 0):.4f} (criterion c fails); Germany: "
                          "no account-free intensity series"})
    else:
        add("S-f", "Second grid profile: CAISO via EIA-930 (DL-027 §2, DL-031)", None)
    g = _load(out, "g")
    add("S-g", "Cold-start builds excluded", g, v1=g["V1"] if g else None,
        note=f"{g['excluded_builds']} builds excluded" if g else "")
    h = _load(out, "h")
    add("S-h", "④b trailing-50 control form (sensitivity of the control)", h,
        note=(f"trailing vs ④b area {_area(h['trailing_vs_4b'])}; trailing vs ④a area "
              f"{_area(h['trailing_vs_4a'])}") if h else "")
    R.append({"sweep": "S-i", "label": "Floor ×0.5 / ×2 and ④b as the null (collected from P3-T1/P3-T3)",
              "V1": f"×0.5 {{{', '.join(rep['admission']['floor_sweep']['by_floor']['x0.5']['admitted'])}}} · "
                    f"×2 {{{', '.join(rep['admission']['floor_sweep']['by_floor']['x2']['admitted']) or '∅'}}}",
              "V2": "stable (no at every floor)",
              "V3": "stable (yes at every floor)" if all(
                  iv["populations"]["all"]["pairs"][V3_PAIR]["condition"].values()) else "**FLIPS**",
              "V4": "n/a", "area": None,
              "note": "V1 at ×2 is the known floor-sensitivity of F1 reported in P3-T1"})
    return R


def _fig_v3(R: list[dict], fig_dir: Path) -> str | None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pts = [(r["sweep"], r["area"]) for r in R if r.get("area") and r["area"].get("point") is not None]
    if not pts:
        return None
    fig, ax = plt.subplots(figsize=(7.0, 0.42 * len(pts) + 1.2), dpi=160)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    y = np.arange(len(pts))[::-1]
    for yi, (lab, a) in zip(y, pts):
        if a.get("ci_lo") is not None:
            ax.plot([a["ci_lo"], a["ci_hi"]], [yi, yi], color=BLUE, lw=2, solid_capstyle="round")
        ax.scatter([a["point"]], [yi], s=64, color=BLUE, edgecolors=SURF, linewidths=2, zorder=3)
    ax.axvline(0, color="#c3c2b7", lw=1)
    ax.set_yticks(y, [p[0] for p in pts], fontsize=8, color=INK2)
    ax.tick_params(axis="x", colors=MUTED, labelsize=8)
    ax.grid(axis="x", color=GRID_C, lw=1)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.set_xlabel("area between frontiers, ④b (≡ ⑤) over ④a (pp × h; > 0 favours ④b)",
                  fontsize=8.5, color=INK2)
    ax.set_title("Secondary finding (V3) across sensitivity sweeps, 95% CI", fontsize=9.5,
                 color=INK, loc="left")
    fig.tight_layout()
    fig_dir.mkdir(parents=True, exist_ok=True)
    path = fig_dir / "sensitivity_v3_area.png"
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)
    return path.name


def _fig_profiles(f: dict | None, root: Path, fig_dir: Path) -> str | None:
    if not f or f.get("status") != "run":
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    uk = pd.read_csv(root / "code" / "data" / "carbon" / "hour_of_week_profile.csv")
    g2 = pd.read_csv(root / f["profile_path"])
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=160)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    ax.plot(uk["slot"], uk["mean"], color=BLUE, lw=2, label="UK (NESO), 2024–2025")
    ax.plot(g2["slot"], g2["mean"], color=ORANGE, lw=2,
            label=f"{f['zone']['zone']} (Electricity Maps, direct), 2024–2025")
    ax.set_xticks(range(0, 169, 24), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", ""],
                  fontsize=8, color=MUTED)
    ax.tick_params(axis="y", colors=MUTED, labelsize=8)
    ax.grid(color=GRID_C, lw=1)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_ylabel("g CO₂/kWh (UTC hour of week)", fontsize=8.5, color=INK2)
    ax.set_title("The two grid profiles used in the replay", fontsize=9.5, color=INK, loc="left")
    ax.legend(fontsize=7.5, frameon=False, labelcolor=INK2, loc="upper left")
    fig.tight_layout()
    path = fig_dir / "sensitivity_grid_profiles.png"
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)
    return path.name


def write(out: Path, p3: Path, fig_dir: Path) -> None:
    root = p3.parents[1]
    R = rows(out, p3)
    flips = [r for r in R if any("FLIPS" in str(r[k]) for k in ("V1", "V2", "V3", "V4"))]
    pending = [r for r in R if "pending" in (r["V2"], r["V4"])]
    fig_v3 = _fig_v3(R, fig_dir)
    fig_prof = _fig_profiles(_load(out, "f"), root, fig_dir)
    L: list[str] = []
    A = L.append
    A("# P3-T4 — sensitivity analyses: does any sweep change a verdict?\n")
    A("> Assembled by `PYTHONPATH=. python scripts/sensitivity_analysis.py --summary` from "
      "`results/p3/sensitivity/*.json`. Every number comes from those runs (R1). **Test split**, "
      "frozen models, frozen spec. Nothing refitted. Verdict definitions: DL-030 §1 — **V1** "
      "model-level admitted set (×1) · **V2** ⑤ beats both ④a and ④b (×1) · **V3** ④b (≡ ⑤) over "
      "④a (×1) · **V4** the eight-class sign pattern of ⑤ vs ①, ②, ③, ④a on carbon and TTFF p95.\n")
    A("## Verdict flips\n")
    if flips:
        for r in flips:
            A(f"- **{r['sweep']} — {r['label']}**: V1 {r['V1']} · V2 {r['V2']} · V3 {r['V3']} · "
              f"V4 {r['V4']}. {r['note']}")
    else:
        A("- **None** among the sweeps run so far.")
    if pending:
        A(f"\n*Pending: {', '.join(r['sweep'] for r in pending)}.*")
    A("\n## Summary table\n")
    A("| sweep | what changes | V1 | V2 | V3 | V4 | V3 area (pp·h) [95% CI] | note |")
    A("| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |")
    for r in R:
        A(f"| {r['sweep']} | {r['label']} | {r['V1']} | {r['V2']} | {r['V3']} | {r['V4']} | "
          f"{_area(r['area'])} | {r['note']} |")
    if fig_v3:
        A(f"\n![V3 across sweeps](figures/{fig_v3})\n")
    base = _load(out, "baseline")
    if base:
        A("## V4 baseline, recomputed from the P3-T2 parts\n")
        A(f"Classes match P3-T2's stored paired bootstrap: **{base['cross_check_vs_p3t2']['classes_match']}**.\n")
        A("| pair | metric | Δ [95% CI] | class |")
        A("| :-- | :-- | :-- | :-- |")
        for k, rec in base["v4"]["pairs"].items():
            for metric, v in rec.items():
                A(f"| {k.replace('_minus_', ' − ')} | {metric} | {v['point']:+.4f} "
                  f"[{v['ci_lo']:+.4f}, {v['ci_hi']:+.4f}] | {v['class']} |")
    f = _load(out, "f")
    if f:
        A("\n## S-f second grid (DL-027 §2, DL-031, DL-032)\n")
        A(f"**{f['status']}.**\n")
        for t in f.get("tried", []):
            ptt = t.get("peak_to_trough")
            A(f"- **{t.get('zone')}**: {t.get('source', '')} · criteria {t.get('criteria')}"
              + (f" · peak-to-trough {ptt:.4f} vs UK {t.get('uk_peak_to_trough'):.4f}" if ptt else "")
              + (f" · coverage {t['coverage']}" if t.get("coverage") else "")
              + (f" · {t['evidence']}" if t.get("evidence") else ""))
        if f.get("by_product"):
            A(f"\n*By-product, descriptive only (DL-032):* {f['by_product']['reading']}. The "
              "ranking-invariance question S-f was meant to answer remains **untested** and is carried "
              "as a limitation.\n")
        if fig_prof:
            A(f"\n![profiles](figures/{fig_prof})\n")
    h = _load(out, "herding")
    if h:
        A("\n## Herding (P3-T4 S3) — descriptive, no threshold predeclared\n")
        A("| setting | top-5 slot share | × static | largest slot share | × static |")
        A("| :-- | --: | --: | --: | --: |")
        for sid, r in h["settings"].items():
            A(f"| `{sid}` | {r['top5_share']:.4f} | {r['top5_ratio_to_static']:.2f} | "
              f"{r['max_slot_share']:.4f} | {r['max_ratio_to_static']:.2f} |")
        A("\nAny strategy that concentrates builds into few green slots would, if deployed at scale, "
          "change the marginal intensity it is optimising against (§6). The hour-of-week average "
          "profile cannot represent that feedback; it is a stated limitation.\n")
    reading = out / "reading.md"
    if reading.exists():                       # authored at the gate; never generated
        L.append(reading.read_text(encoding="utf-8"))
    A("## Provenance\n")
    for name in ("baseline", "a", "b", "c", "d", "e", "f", "g", "h", "herding"):
        d = _load(out, name)
        if d:
            A(f"- `{d['command']}` — {d['run_date']}, {d['runtime_s']:.0f} s → "
              f"`results/p3/sensitivity/{name}.json`")
    (p3 / "sensitivity.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {p3 / 'sensitivity.md'}")

"""DL-034 §B6 — original vs corrected, for every headline number and verdict.

Reads the **original** results from `results/corrections/dl034/original/` (snapshotted before the
rerun) or, for files not snapshotted, from git at the commit that last produced them (`1e38db7` for
P3). Reads the **corrected** results from the working tree. Computes nothing new: every value is
copied from a result file, and a row is printed whether or not it changed.

Run:  python scripts/dl034_comparison.py        (env: PYTHONPATH=.)
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1].parent
ORIG = ROOT / "results" / "corrections" / "dl034" / "original"
OUT = ROOT / "results" / "corrections" / "dl034" / "comparison.md"
P3_ORIGINAL_COMMIT = "1e38db7"
COMMAND = "python scripts/dl034_comparison.py"
FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6")
ARMS = ("xgboost:control", "logreg:control", "random_forest:control",
        "xgboost:full", "logreg:full", "random_forest:full")
HEADLINE = ("1_static", "2_blanket_carbon_aware__d0__w167", "3_eligibility_only__d0__w24",
            "4a_duration_estimator__d480__w24", "4b_duration_prior__d480__w24",
            "5_se_informed_policy__d480__w24", "6_risk_only_skip__t0.2", "6_risk_only_skip__t0.25",
            "6_risk_only_skip__t0.3")
PAIRS = {"⑤ (≡ ④b) vs ④a": "4a_duration_estimator|5_se_informed_policy",
         "⑤ vs ④b": "4b_duration_prior|5_se_informed_policy",
         "oracle vs ④b": "4b_duration_prior|4_oracle_duration"}


def orig_json(name: str) -> Any:
    return json.loads((ORIG / name).read_text(encoding="utf-8"))


def git_text(rel: str, commit: str = P3_ORIGINAL_COMMIT) -> str:
    return subprocess.run(["git", "show", f"{commit}:Research_Artifact/{rel}"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def new_json(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def f6(x: float) -> str:
    return f"{x:+.6f}"


def ci(d: dict, lo: str = "ci_lo", hi: str = "ci_hi", key: str = "delta", fmt=f6) -> str:
    return f"{fmt(d[key])} [{fmt(d[lo])}, {fmt(d[hi])}]"


def same(a: str, b: str) -> str:
    return "=" if a == b else "**changed**"


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join([":--"] * len(header)) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def p1_section() -> list[str]:
    L = ["## P1 — calibration-split evidence (P1-T4 … P1-T7)", ""]
    dco, dcn = orig_json("results_p1_duration_control.json"), new_json("results/p1/duration_control.json")
    rows = []
    for form in ("4b_expanding", "4a_xgboost"):
        a, b = dco["calibration_split"][form]["all_builds"], dcn["calibration_split"][form]["all_builds"]
        for m in ("mae_log1p", "spearman_rho"):
            x, y = f"{a[m]:.6f}", f"{b[m]:.6f}"
            rows.append([f"`d̂` {form} {m}", x, y, same(x, y)])
    x, y = dco["selection"]["primary_form"], dcn["selection"]["primary_form"]
    rows.append(["primary form", x, y, same(x, y)])
    mto, mtn = orig_json("results_p1_model_training.json")["arms"], new_json("results/p1/model_training.json")["arms"]
    for arm in ARMS:
        x, y = f"{mto[arm]['calibrated']['pr_auc']:.6f}", f"{mtn[arm]['calibrated']['pr_auc']:.6f}"
        rows.append([f"{arm} calibration PR-AUC", x, y, same(x, y)])
    ado, adn = orig_json("results_p1_admission.json"), new_json("results/p1/admission.json")
    for fam in FAMILIES:
        x = ci(ado["model_level_admission"]["verdicts"][fam], key="delta_pr_auc")
        y = ci(adn["model_level_admission"]["verdicts"][fam], key="delta_pr_auc")
        rows.append([f"{fam} ΔPR-AUC vs {{d̂}} [95% CI]", x, y, same(x, y)])
    for k in ("x0.5", "x1", "x2"):
        x, y = _admitted(ado, k), _admitted(adn, k)
        rows.append([f"admitted set {k}", x, y, same(x, y)])
    x, y = ado.get("policy_path"), adn.get("policy_path")
    rows.append(["policy path", str(x), str(y), same(str(x), str(y))])
    return L + table(["quantity", "original", "corrected", ""], rows) + [""]


def _admitted(adm: dict, k: str) -> str:
    sweep = adm["floor_sweep"]["by_floor"][k]
    return "{" + ", ".join(sweep["admitted"]) + "}" if sweep["admitted"] else "∅"


def p2_section() -> list[str]:
    L = ["## P2 — the frozen policy (P2-T5)", ""]
    so, sn = orig_json("results_p2_policy_fit_selection.json")["primary"], new_json(
        "results/p2/policy_fit/selection.json")["primary"]
    rows = []
    for k, fmt in (("setting_id", str), ("d_threshold_seconds", lambda v: f"{v:.0f}"),
                   ("w_max_hours", lambda v: f"{v:.0f}"), ("best_saving_pct", lambda v: f"{v:.6f}"),
                   ("saving_pct", lambda v: f"{v:.6f}"), ("ttff_p95_h_failed", lambda v: f"{v:.4f}"),
                   ("n_admissible", str)):
        x, y = fmt(so[k]), fmt(sn[k])
        rows.append([k, x, y, same(x, y)])
    spec_o = (ORIG / "code_scheduler_core_config_policy_spec.yaml").read_bytes()
    spec_n = (ROOT / "code" / "scheduler_core" / "config" / "policy_spec.yaml").read_bytes()
    import hashlib
    x, y = hashlib.sha256(spec_o).hexdigest()[:16] + "…", hashlib.sha256(spec_n).hexdigest()[:16] + "…"
    rows.append(["policy_spec.yaml sha256", x, y, same(x, y)])
    return L + table(["quantity", "original", "corrected", ""], rows) + [""]


def p3t1_section() -> list[str]:
    L = ["## P3-T1 — test-split model evaluation", ""]
    mo, mn = orig_json("results_p3_model_report.json"), new_json("results/p3/model_report.json")
    rows = []
    for fam in FAMILIES:
        a, b = mo["replication"]["families"][fam]["test"], mn["replication"]["families"][fam]["test"]
        x, y = ci(a), ci(b)
        rows.append([f"{fam} test ΔPR-AUC [95% CI]", x, y, same(x, y)])
        x, y = str(a["admitted"]), str(b["admitted"])
        rows.append([f"{fam} admitted on test (×1)", x, y, same(x, y)])
    for k in ("x0.5", "x1", "x2"):
        a = mo["admission"]["floor_sweep"]["by_floor"][k]["admitted"]
        b = mn["admission"]["floor_sweep"]["by_floor"][k]["admitted"]
        x, y = "{" + ", ".join(a) + "}" if a else "∅", "{" + ", ".join(b) + "}" if b else "∅"
        rows.append([f"test admitted set {k}", x, y, same(x, y)])
    x, y = str(mo["admission"]["floor_sweep"]["stable"]), str(mn["admission"]["floor_sweep"]["stable"])
    rows.append(["test admitted set stable across sweep", x, y, same(x, y)])
    for alg in ("xgboost", "logreg", "random_forest"):
        x, y = ci(mo["full_vs_control"][alg]["pr_auc"]), ci(mn["full_vs_control"][alg]["pr_auc"])
        rows.append([f"{alg} full − control test ΔPR-AUC", x, y, same(x, y)])
    a = mo["duration_control"]["forms"]["4b_expanding"]["all_builds"]
    b = mn["duration_control"]["forms"]["4b_expanding"]["all_builds"]
    for m in ("mae_log1p", "spearman_rho"):
        x, y = f"{a[m]:.4f}", f"{b[m]:.4f}"
        rows.append([f"④b test {m}", x, y, same(x, y)])
    x = f"{mo['shap_comparison']['spearman_mean_abs_shap_calibration_vs_test']:.4f}"
    y = f"{mn['shap_comparison']['spearman_mean_abs_shap_calibration_vs_test']:.4f}"
    rows.append(["SHAP calibration-vs-test Spearman", x, y, same(x, y)])
    return L + table(["quantity", "original", "corrected", ""], rows) + [""]


def p3t2_section() -> list[str]:
    L = ["## P3-T2 — six strategies on the test trace (headline settings)", ""]
    so, sn = orig_json("results_p3_strategy_results.json"), new_json("results/p3/strategy_results.json")
    ho = {r["setting_id"]: r for r in so["headline"]}
    hn = {r["setting_id"]: r for r in sn["headline"]}
    po, pn = so["bootstrap"]["per_strategy"], sn["bootstrap"]["per_strategy"]
    rows = []
    for sid in HEADLINE:
        if sid not in ho or sid not in hn:
            continue
        for label, fo, fn in (
                ("carbon % vs ①", lambda: f"{ho[sid]['carbon_pct_vs_static']:+.3f}%",
                 lambda: f"{hn[sid]['carbon_pct_vs_static']:+.3f}%"),
                ("deferred", lambda: f"{ho[sid]['n_deferred']:,}", lambda: f"{hn[sid]['n_deferred']:,}"),
                ("TTFF p95 h (failed)", lambda: f"{po[sid]['ttff_p95_h_failed']['point']:.2f}",
                 lambda: f"{pn[sid]['ttff_p95_h_failed']['point']:.2f}"),
                ("missed failures", lambda: f"{ho[sid]['missed_failures']:,}",
                 lambda: f"{hn[sid]['missed_failures']:,}")):
            x, y = fo(), fn()
            rows.append([f"`{sid}` {label}", x, y, same(x, y)])
    for label, path in (("validator violations", ("checks", "validator", "violations")),
                        ("validator deferrals audited", ("checks", "validator", "deferred"))):
        a, b = so, sn
        for k in path:
            a, b = a[k], b[k]
        rows.append([label, f"{a:,}", f"{b:,}", same(str(a), str(b))])
    return L + table(["quantity", "original", "corrected", ""], rows) + [""]


def p3t3_section() -> list[str]:
    L = ["## P3-T3 — decision-level frontiers (headline RQ2)", ""]
    io = orig_json("results_p3_incremental_value_decision.json")["populations"]
    inn = new_json("results/p3/incremental_value_decision.json")["populations"]
    rows = []
    for label, key in PAIRS.items():
        a, b = io["all"]["pairs"][key], inn["all"]["pairs"][key]
        fmt = lambda v: f"{v:+.4f}"
        x, y = ci(a["area"], key="point", fmt=fmt), ci(b["area"], key="point", fmt=fmt)
        rows.append([f"{label}: area (pp·h) [95% CI]", x, y, same(x, y)])
        for k in ("x0.5", "x1", "x2"):
            x, y = str(_cond(a["condition"], k)), str(_cond(b["condition"], k))
            rows.append([f"{label}: §A1.7 condition {k}", x, y, same(x, y)])
    for k in ("x0.5", "x1", "x2"):
        x, y = str(io["all"]["verdict_se_adds_value"][k]), str(inn["all"]["verdict_se_adds_value"][k])
        rows.append([f"RQ2 verdict \"⑤ beats both ④a and ④b\" {k}", x, y, same(x, y)])
    for band in ("low", "mid", "high"):
        fmt = lambda v: f"{v:+.4f}"
        a = io[band]["pairs"]["4a_duration_estimator|5_se_informed_policy"]["area"]
        b = inn[band]["pairs"]["4a_duration_estimator|5_se_informed_policy"]["area"]
        x, y = ci(a, key="point", fmt=fmt), ci(b, key="point", fmt=fmt)
        rows.append([f"⑤ vs ④a area, {band} failure-rate band", x, y, same(x, y)])
    return L + table(["quantity", "original", "corrected", ""], rows) + [""]


def _cond(cond: dict, k: str) -> Any:
    node = cond.get(k, cond)
    return node.get("met", node.get("holds", node)) if isinstance(node, dict) else node


SUMMARY_ROW = re.compile(r"^\| (baseline|S-[a-i][^|]*) \|")


def _sens_rows(md: str) -> dict[str, list[str]]:
    rows = {}
    for line in md.splitlines():
        if SUMMARY_ROW.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows[cells[0]] = cells
    return rows


def p3t4_section() -> list[str]:
    L = ["## P3-T4 — sensitivity verdicts (V1 model admitted set · V2 ⑤ beats both · V3 ④b over ④a · "
         "V4 RQ4 sign pattern)", ""]
    ro = _sens_rows((ORIG / "results_p3_sensitivity.md").read_text(encoding="utf-8"))
    rn = _sens_rows((ROOT / "results" / "p3" / "sensitivity.md").read_text(encoding="utf-8"))
    rows = []
    for sweep in rn:
        a, b = ro.get(sweep), rn[sweep]
        for i, name in ((2, "V1"), (3, "V2"), (4, "V3"), (5, "V4"), (6, "V3 area")):
            x = a[i] if a and len(a) > i else "—"
            y = b[i] if len(b) > i else "—"
            rows.append([f"{sweep} {name}", x, y, same(x, y)])
    return L + table(["sweep · verdict", "original", "corrected", ""], rows) + [""]


def main() -> None:
    parts = [
        "# DL-034 — original vs corrected results",
        "",
        f"> Generated by `PYTHONPATH=. {COMMAND}`. **Original** = the pre-DL-034 results "
        "(start-ordered ④b history), from `results/corrections/dl034/original/` (snapshotted before "
        f"the rerun, MANIFEST.txt) and git `{P3_ORIGINAL_COMMIT}`. **Corrected** = the DL-034 rerun "
        "(completion-causal history), from the working tree. Every value is copied from a result "
        "file; nothing is computed here. Every row is shown, changed or not (DL-034 §B6).",
        "",
    ]
    for section in (p1_section, p2_section, p3t1_section, p3t2_section, p3t3_section, p3t4_section):
        parts += section()
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    text = OUT.read_text(encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {text.count('**changed**')} changed rows, "
          f"{text.count('| = |')} unchanged rows")


if __name__ == "__main__":
    main()

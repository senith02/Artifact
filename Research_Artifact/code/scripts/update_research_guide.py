"""Regenerate and validate the living research guide (`docs/research_guide.html`).

The guide is **documentation, not governance**: it explains the project and is
rebuilt from the repository at every gate. It never decides anything — if it
disagrees with `planning/PROGRESS.md` or `governance/03_DECISION_LOG.md`, those
win (DL-025).

What this script does
  1. Reads the evidence the guide shows **directly from the result files**
     (`results/p0..p2`, the frozen spec, the carbon profile) into
     `state["evidence"]`, so no number in the guide is typed by hand.
  2. Reads live state from `planning/PROGRESS.md` (state block, status table,
     ledger dates), recounts the `###` task headings in `development_plan.md`,
     and lists every decision-log entry.
  3. Merges those into the curated `docs/research_state.json` (task narratives,
     limitations, discrepancies, change history — the parts a human writes) and
     cross-checks them: every task id exists in the plan, statuses agree with
     PROGRESS.md, every referenced file exists, every `{{token}}` resolves.
  4. Resolves `{{evidence.path|fmt}}` tokens in the curated text and in the HTML
     template, embeds the state as JSON, and writes `docs/research_guide.html`
     — a single file that opens from disk with no server.

Run from `Research_Artifact/code/`:
    python scripts/update_research_guide.py            # rebuild state + guide
    python scripts/update_research_guide.py --check    # validate only; exit 1 on any problem
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

RA = Path(__file__).resolve().parents[2]          # Research_Artifact/
REPO = RA.parent                                   # Artifact/
DOCS = RA / "docs"
STATE = DOCS / "research_state.json"
TEMPLATE = DOCS / "research_guide.template.html"
GUIDE = DOCS / "research_guide.html"
RES = RA / "results"

STATUS_SYMBOLS = {"✅": "done", "⏳": "in_progress", "⬜": "not_started", "✗": "dod_unmet"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_json(path: Path) -> Any:
    return json.loads(read(path))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# 1. Evidence — every number the guide shows, read from its result file
# --------------------------------------------------------------------------- #

def _first_passed(path: Path) -> dict[str, Any]:
    m = re.search(r"(\d+) passed(?:, (\d+) skipped)?", read(path))
    if not m:
        raise ValueError(f"no pytest summary in {path}")
    return {"passed": int(m.group(1)), "skipped": int(m.group(2) or 0), "file": rel(path)}


def rel(path: Path) -> str:
    return path.resolve().relative_to(RA).as_posix()


def _md_table_after(text: str, marker: str) -> list[list[str]]:
    """Rows of the first markdown table after `marker` (header + separator dropped)."""
    start = text.index(marker)
    rows: list[list[str]] = []
    started = False
    for line in text[start:].splitlines()[1:]:
        if line.startswith("|"):
            started = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
        elif started:
            break
    return rows[2:]


def collect_evidence() -> dict[str, Any]:
    ev: dict[str, Any] = {}

    # ---- P0: data profile ----
    dp = load_json(RES / "p0" / "data_profile.json")
    dd = dp["duration_distribution_s"]
    ev["data"] = {
        "source": "results/p0/data_profile.json",
        "run_date": dp["provenance"]["run_date"],
        "job_rows": dp["row_counts"]["total_job_rows"],
        "duplicate_rows": dp["row_counts"]["exact_duplicate_job_rows"],
        "builds": dp["row_counts"]["total_builds"],
        "analytic_builds": dp["row_counts"]["analytic_builds"],
        "failures": dp["class_balance"]["failure"],
        "passes": dp["class_balance"]["pass"],
        "failure_rate_pct": dp["class_balance"]["failure_rate_pct"],
        "canceled": dp["build_status_distribution_all"]["canceled"],
        "other_label": dp["build_status_distribution_all"]["other"],
        "languages": dp["per_language_builds"],
        "n_languages": dp["notable_findings"]["n_languages"],
        "fully_null_columns": dp["notable_findings"]["fully_null_columns"],
        "duration": {"count": dd["count"], "mean": dd["mean"], "max": dd["max"],
                     "zeros": dd["zeros"], "over_1h": dd["over_1h"], "over_6h": dd["over_6h"],
                     "missing": dp["notable_findings"]["builds_missing_duration"],
                     "percentiles": dd["percentiles_s"]},
        "funnel": dp["filter_funnel"],
    }

    # ---- P0: carbon profile ----
    prof = []
    with open(RA / "code" / "data" / "carbon" / "hour_of_week_profile.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            prof.append({"slot": int(row["slot"]), "dow": int(row["dow"]), "hour": int(row["hour"]),
                         "mean": round(float(row["mean"]), 3)})
    cov_rows = _md_table_after(read(RES / "p0" / "carbon_profile.md"), "## Per-year coverage")
    means = [p["mean"] for p in prof]
    ev["carbon"] = {
        "source": "code/data/carbon/hour_of_week_profile.csv; results/p0/carbon_profile.md",
        "provider": "carbonintensity.org.uk (NESO) national series, 2024 + 2025",
        "slots": len(prof), "profile": prof,
        "min": min(means), "max": max(means), "mean": round(sum(means) / len(means), 3),
        "coverage": [{"year": r[0], "expected": r[1], "present": r[2], "coverage_pct": r[4]}
                     for r in cov_rows],
    }

    # ---- P1: splits ----
    sp = load_json(RES / "p1" / "splits.json")
    ev["splits"] = {
        "source": "results/p1/splits.json",
        "sha256": sp["freeze"]["assignment_sha256"], "n_projects": sp["freeze"]["n_projects"],
        "run_date": sp["provenance"]["run_date"], "checks": sp["checks"],
    }
    for name in ("train", "calibration", "test"):
        s = sp["per_split"][name]
        ev["splits"][name] = {"projects": s["n_projects"], "builds": s["n_builds"],
                              "share_pct": round(100 * s["share_of_builds"], 2),
                              "failure_rate_pct": s["failure_rate_pct"],
                              "median_duration_s": s["duration_s"]["p50"],
                              "p95_duration_s": round(s["duration_s"]["p95"]),
                              "first": s["time_range"]["first_build"][:10],
                              "last": s["time_range"]["last_build"][:10]}

    # ---- P1: feature audit / degeneracy ----
    fs = load_json(RES / "p1" / "feature_summary.json")
    fam_rows = _md_table_after(read(RES / "p1" / "feature_audit.md"), "**Per-family impact**")
    ev["features"] = {
        "source": "results/p1/feature_summary.json; results/p1/feature_audit.md",
        "families": fs["families"],
        "n_features": sum(len(v) for v in fs["families"].values()),
        "verdict_counts": {v: sum(1 for r in fs["degeneracy"] if r["verdict"] == v)
                           for v in ("constant", "near-constant", "sparse", "ok")},
        "constant": [r["feature"] for r in fs["degeneracy"] if r["verdict"] == "constant"],
        "family_effective": {r[0].split(" ")[0]: {"members": int(r[1]), "effective": int(r[5])}
                             for r in fam_rows},
    }

    # ---- P1: duration control ----
    dc = load_json(RES / "p1" / "duration_control.json")
    cs = dc["calibration_split"]

    def _q(block: dict) -> dict:
        a = block["all_builds"]
        return {"mae_log1p": a["mae_log1p"], "median_ae_log1p": a["median_ae_log1p"],
                "mae_s": a["mae_seconds"], "median_ae_s": a["median_ae_seconds"],
                "rho": a["spearman_rho"], "n": a["n"]}

    ev["duration"] = {
        "source": "results/p1/duration_control.json",
        "fit_id": dc["provenance"]["fit_id"], "run_date": dc["provenance"]["run_date"],
        "n_fit_builds": dc["provenance"]["n_fit_builds"],
        "n_fit_projects": dc["provenance"]["n_fit_projects"],
        "unusable_labels": dc["provenance"]["n_builds_unusable_label"],
        "primary": dc["selection"]["primary_form"],
        "f4b": _q(cs["4b_expanding"]), "f4a": _q(cs["4a_xgboost"]),
        "trailing50": _q(dc["sensitivities"]["4b_trailing_50"]),
        "coverage_project_pct": cs["4b_expanding"]["coverage"]["levels"]["project"]["pct"],
        "coverage_language_n": cs["4b_expanding"]["coverage"]["levels"]["language"]["n"],
        "checks": dc["checks"],
    }
    ridge = [k for k in cs if k.startswith("4a_ridge")]
    if ridge:
        ev["duration"]["ridge"] = _q(cs[ridge[0]])

    # ---- P1: six model arms ----
    mt = load_json(RES / "p1" / "model_training.json")
    ev["models"] = {"source": "results/p1/model_training.json",
                    "run_date": mt["provenance"]["run_date"], "n_iter": mt["provenance"]["n_iter"],
                    "arms": {}}
    for key, arm in mt["arms"].items():
        c = arm["calibrated"]
        ev["models"]["arms"][key.replace(":", "_")] = {
            "algorithm": arm["algorithm"], "arm": arm["arm"], "n_features": arm["n_features"],
            "calibrator": arm["calibration_choice"]["chosen"],
            "pr_auc": c["pr_auc"], "roc_auc": c["roc_auc"], "brier": c["brier"],
            "f1": c["f1_at_tau"], "tau": c["tau"]}

    # ---- P1: ablation + admission + SHAP ----
    de = load_json(RES / "p1" / "ablation" / "deltas.json")
    ev["ablation"] = {"source": "results/p1/ablation/deltas.json",
                      "run_date": de["provenance"]["run_date"], "families": {}}
    for fam, row in de["families"].items():
        d = row["delta_vs_control"]
        ev["ablation"]["families"][fam] = {
            "n": row["n_features"], "delta": d["pr_auc"]["delta"],
            "lo": d["pr_auc"]["ci_lo"], "hi": d["pr_auc"]["ci_hi"],
            "d_roc": d["roc_auc"]["delta"], "d_brier": d["brier"]["delta"],
            "treatment_pr_auc": d["pr_auc"]["treatment"]}
    ev["ablation"]["control_pr_auc"] = de["families"]["F1"]["delta_vs_control"]["pr_auc"]["control"]
    ad = load_json(RES / "p1" / "admission.json")
    ev["admission"] = {"source": "results/p1/admission.json",
                       "floor": ad["model_level_admission"]["floor"],
                       "admitted": ad["model_level_admission"]["admitted"],
                       "policy_path": ad["policy_path"],
                       "floor_sweep": {k: v["admitted"] for k, v in ad["floor_sweep"]["by_floor"].items()},
                       "stable": ad["floor_sweep"]["stable"]}
    sh = load_json(RES / "p1" / "shap" / "shap_summary.json")
    ev["shap"] = {"source": "results/p1/shap/shap_summary.json", "families": {}}
    for fam, v in sh["per_family"].items():
        ev["shap"]["families"][fam] = {
            "abs": v["mean_abs_contribution"], "signed": v["mean_signed_contribution"],
            "between": sh["variance_decomposition"][fam]["between_share"]}
    ev["shap"]["threshold"] = sh["project_identity_coded_threshold"]

    # ---- P2: eligibility ----
    eg = load_json(RES / "p2" / "eligibility_gate.json")
    prim = next(v for v in eg["variants"] if v["variant"] == "primary")
    alt = next(v for v in eg["variants"] if v["variant"] != "primary")
    xc = next(c for c in eg["cross_checks"] if c["variant"] == "primary")
    ev["eligibility"] = {
        "source": "results/p2/eligibility_gate.json",
        "gated": eg["funnel"]["builds_gated_train_plus_calibration"],
        "projects": eg["funnel"]["distinct_projects"],
        "eligible": prim["summary"]["eligible"],
        "eligible_pct": round(100 * prim["summary"]["eligible_fraction"], 4),
        "by_rule": prim["summary"]["by_rule"],
        "alt_variant": alt["variant"], "alt_eligible": alt["summary"]["eligible"],
        "alt_pct": round(100 * alt["summary"]["eligible_fraction"], 4),
        "pairs_checked": xc["pairs_checked"], "disagreements": xc["disagreements"],
        "branch_names": xc["distinct_branch_names"],
        "violations": prim["validator_audit"]["violations"],
    }

    # ---- P2: energy ----
    em = load_json(RES / "p2" / "energy_model.json")
    ev["energy"] = {"source": "results/p2/energy_model.json",
                    "p_avg_w": em["energy_config"]["p_avg_w"],
                    "citations": [c["url"] for c in em["energy_config"]["citations"]],
                    "greenest": em["extreme_slots"]["greenest"],
                    "dirtiest": em["extreme_slots"]["dirtiest"],
                    "worked": em["worked_examples"],
                    "band": em["p_avg_band_example"]}
    one_hour = next(w for w in em["worked_examples"] if w["duration_s"] == 3600.0)
    ev["energy"]["ceiling_pct"] = one_hour["pct_change_if_shifted"]
    ev["energy"]["ceiling_saving_pct"] = -one_hour["pct_change_if_shifted"]

    # ---- P2: calibration fitting sweep (P2-T5) — calibration evidence only ----
    pf = RES / "p2" / "policy_fit"
    man = load_json(pf / "manifest.json")
    rows = []
    with open(pf / "summary.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            def num(k):
                return float(r[k]) if r[k] not in ("", None) else None
            rows.append({"strategy": r["strategy"], "setting": r["setting_id"],
                         "d": num("param_d_threshold_seconds"), "w": num("param_w_max_hours"),
                         "tau": num("param_tau_skip"), "deferred": int(float(r["n_deferred"])),
                         "skipped": int(float(r["n_skipped"])),
                         "saving_pct": -num("carbon_pct_vs_static") + 0.0,
                         "ttff_p95_h": num("ttff_p95_h_failed"),
                         "latency_p95_def_h": num("latency_p95_h_deferred"),
                         "missed": int(float(r["missed_failures"]))})
    sel = load_json(pf / "selection.json")
    ver = load_json(pf / "verify.json")
    ev["replay"] = {
        "source": "results/p2/policy_fit/summary.csv; results/p2/policy_fit/manifest.json",
        "label": "calibration-split fitting evidence (DL-024) — not an RQ4 result",
        "population": man["population"], "rows": rows,
        "validator": man["checks"]["validator"], "identities": man["checks"]["identities"],
        "characteristics": man["characteristics"],
    }
    spec_path = RA / "code" / "scheduler_core" / "config" / "policy_spec.yaml"
    ev["policy"] = {
        "source": "code/scheduler_core/config/policy_spec.yaml; results/p2/policy_fit/selection.json",
        "sha256": sha256(spec_path),
        "policy_path": man["spec"]["policy_path"],
        "d_threshold_s": man["spec"]["duration_only"]["d_threshold_seconds"],
        "w_max_h": man["spec"]["duration_only"]["w_max_hours"],
        "rho": sel["primary"]["rho"], "best_saving_pct": sel["primary"]["best_saving_pct"],
        "chosen_saving_pct": sel["primary"]["saving_pct"],
        "chosen_ttff_p95_h": sel["primary"]["ttff_p95_h_failed"],
        "n_admissible": sel["primary"]["n_admissible"], "n_points": sel["primary"]["n_points"],
        "sensitivity": [{"rho": s["rho"], "d": s["d_threshold_seconds"], "w": s["w_max_hours"],
                         "saving_pct": s["saving_pct"], "ttff_p95_h": s["ttff_p95_h_failed"]}
                        for s in sel["sensitivity"]],
        "verify_identical": ver["all_identical"],
        "generated": man["spec"]["provenance"]["generated"],
    }
    if ev["policy"]["sha256"] != ver["policy_spec_yaml"]["committed_sha256"]:
        raise SystemExit("FATAL: policy_spec.yaml does not match the sha256 its --verify certified")

    # ---- decide() examples (bootstrap, P2-T3) ----
    dx = load_json(RES / "p2" / "decide_examples.json")
    ev["decide_examples"] = [{"id": e["id"], "shows": e["shows"], "action": e["decision"]["action"],
                              "reason": e["decision"]["reason"]} for e in dx["examples"]]

    # ---- tests per gate ----
    ev["tests"] = {}
    for p in sorted(RES.glob("p*/pytest_p*_t*.txt")):
        tid = re.search(r"pytest_(p\d)_(t\d)", p.name)
        ev["tests"][f"{tid.group(1).upper()}-{tid.group(2).upper()}"] = _first_passed(p)
    return ev


# --------------------------------------------------------------------------- #
# 2. Live state: PROGRESS.md, development_plan.md, decision log
# --------------------------------------------------------------------------- #

def parse_plan() -> dict[str, Any]:
    text = read(RA / "planning" / "development_plan.md")
    tasks = []
    for m in re.finditer(r"^### (P(\d)-T\d+) — (.+?)(?:\s+✅.*)?$", text, flags=re.M):
        name = re.sub(r"\s+✅.*$", "", m.group(3)).strip()
        tasks.append({"id": m.group(1), "phase": int(m.group(2)), "plan_heading": name})
    return {"tasks": tasks, "total": len(tasks),
            "per_phase": {f"P{p}": sum(1 for t in tasks if t["phase"] == p) for p in range(6)}}


def parse_progress() -> dict[str, Any]:
    text = read(RA / "planning" / "PROGRESS.md")

    def field(name: str) -> str:
        m = re.search(rf"^\s*{name}:\s*(.+?)\s*(?:#.*)?$", text, flags=re.M)
        return m.group(1).strip() if m else ""

    statuses: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\|[^|]*\|\s*(P\d-T\d+)\b[^|]*\|\s*([^|]+?)\s*\|", line)
        if m:
            cell = m.group(2)
            sym = next((s for s in STATUS_SYMBOLS if s in cell), None)
            if sym:
                statuses[m.group(1)] = STATUS_SYMBOLS[sym]
    ledger: dict[str, str] = {}
    for m in re.finditer(r"^\| (\d{4}-\d{2}-\d{2}) \| (P\d-T\d+) ", text, flags=re.M):
        ledger[m.group(2)] = m.group(1)
    return {"tasks_total": int(field("tasks_total") or 0), "tasks_done": int(field("tasks_done") or 0),
            "current_task": field("current_task"), "next_task": field("next_task"),
            "current_phase": field("current_phase"), "last_gate_passed": field("last_gate_passed"),
            "last_updated": field("last_updated"), "statuses": statuses, "ledger_dates": ledger}


def parse_decisions() -> list[dict[str, str]]:
    text = read(RA / "governance" / "03_DECISION_LOG.md")
    out = []
    heads = list(re.finditer(r"^### (DL-\d{3}) — (.+)$", text, flags=re.M))
    for i, m in enumerate(heads):
        body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        date = re.search(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", body)
        out.append({"id": m.group(1), "title": re.sub(r"[*`]", "", m.group(2)).strip(),
                    "date": date.group(1) if date else ""})
    return out


# --------------------------------------------------------------------------- #
# 3. Tokens, validation, render
# --------------------------------------------------------------------------- #

TOKEN = re.compile(r"\{\{\s*([a-zA-Z0-9_.\-]+)\s*(?:\|\s*([a-z0-9]+))?\s*\}\}")


def lookup(root: dict, path: str) -> Any:
    cur: Any = root
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)]
        else:
            raise KeyError(path)
    return cur


def fmt(value: Any, spec: str | None) -> str:
    if spec in (None, "raw"):
        if isinstance(value, float):
            return f"{value:g}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)
    if spec == "int":
        return f"{int(round(float(value))):,}"
    if spec.startswith("f") and spec[1:].isdigit():
        return f"{float(value):,.{int(spec[1:])}f}"
    if spec.startswith("s") and spec[1:].isdigit():          # signed
        return f"{float(value):+.{int(spec[1:])}f}"
    if spec.startswith("pct") and spec[3:].isdigit():        # fraction -> %
        return f"{100 * float(value):.{int(spec[3:])}f}"
    if spec == "short":
        return str(value)[:16]
    if spec == "join":
        return ", ".join(str(v) for v in value)
    raise ValueError(f"unknown token format {spec!r}")


def resolve_tokens(obj: Any, root: dict, errors: list[str], where: str = "") -> Any:
    if isinstance(obj, str):
        def sub(m: re.Match) -> str:
            try:
                return fmt(lookup(root, m.group(1)), m.group(2))
            except (KeyError, IndexError, ValueError) as exc:
                errors.append(f"unresolved token {m.group(0)} in {where or 'text'}: {exc}")
                return m.group(0)
        return TOKEN.sub(sub, obj)
    if isinstance(obj, list):
        return [resolve_tokens(v, root, errors, where) for v in obj]
    if isinstance(obj, dict):
        return {k: resolve_tokens(v, root, errors, f"{where}.{k}" if where else k) for k, v in obj.items()}
    return obj


def validate(state: dict, plan: dict, prog: dict, errors: list[str], warnings: list[str]) -> None:
    plan_ids = [t["id"] for t in plan["tasks"]]
    state_ids = [t["id"] for t in state["tasks"]]
    if plan_ids != state_ids:
        errors.append(f"task list differs from development_plan.md: plan={plan_ids} state={state_ids}")
    if prog["tasks_total"] != plan["total"]:
        errors.append(f"PROGRESS tasks_total {prog['tasks_total']} != plan recount {plan['total']}")
    done = sum(1 for s in prog["statuses"].values() if s == "done")
    if done != prog["tasks_done"]:
        errors.append(f"PROGRESS tasks_done {prog['tasks_done']} != ✅ rows in its status table {done}")
    for t in state["tasks"]:
        if t["id"] not in prog["statuses"]:
            errors.append(f"{t['id']} has no row in the PROGRESS.md status table")
        for f in t.get("files", []):
            if not (RA / f).exists():
                errors.append(f"{t['id']}: referenced file does not exist: {f}")
        if prog["statuses"].get(t["id"]) == "done" and not t.get("purpose"):
            warnings.append(f"{t['id']} is done but has no narrative in research_state.json")
    for section in ("limitations", "discrepancies"):
        for item in state.get(section, []):
            for f in item.get("files", []):
                if not (RA / f).exists() and not (REPO / f).exists():
                    errors.append(f"{section}: referenced file does not exist: {f}")


def build(check_only: bool) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    state = load_json(STATE)
    plan, prog = parse_plan(), parse_progress()
    evidence = collect_evidence()
    decisions = parse_decisions()

    # Generated sections — overwritten on every run, never hand-edited.
    names = {t["id"]: t["plan_heading"] for t in plan["tasks"]}
    for t in state["tasks"]:
        t["status"] = prog["statuses"].get(t["id"], "unknown")
        t["completed_on"] = prog["ledger_dates"].get(t["id"], "")
        t["plan_heading"] = names.get(t["id"], "")
        t["tests"] = evidence["tests"].get(t["id"])
    curated_dl = {d["id"]: d for d in state.get("decisions", [])}
    state["decisions"] = [{**d, "summary": curated_dl.get(d["id"], {}).get("summary", "")}
                          for d in decisions]
    missing_dl = [d["id"] for d in state["decisions"] if not d["summary"]]
    if missing_dl:
        warnings.append(f"decision-log entries without a guide summary: {missing_dl}")
    phases_done = {f"P{p}": sum(1 for t in state["tasks"] if t["id"].startswith(f"P{p}-")
                                and t["status"] == "done") for p in range(6)}
    state["progress"] = {
        "tasks_total": plan["total"], "tasks_done": prog["tasks_done"],
        "pct": round(100 * prog["tasks_done"] / plan["total"]),
        "per_phase_total": plan["per_phase"], "per_phase_done": phases_done,
        "current_task": prog["current_task"], "next_task": prog["next_task"],
        "last_gate_passed": prog["last_gate_passed"], "progress_md_updated": prog["last_updated"],
        "test_split_opened": False,
    }
    state["evidence"] = evidence
    state["meta"]["last_updated"] = dt.date.today().isoformat()
    state["meta"]["generated_by"] = "code/scripts/update_research_guide.py"

    validate(state, plan, prog, errors, warnings)
    root = {"evidence": evidence, "progress": state["progress"], "meta": state["meta"],
            "cq": state["central_question"]}
    resolved = resolve_tokens(state, root, errors)
    template = read(TEMPLATE)
    html_text = resolve_tokens(template, root, errors, "template")

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        return 1
    if check_only:
        print(f"check OK — {plan['total']} tasks, {prog['tasks_done']} done, "
              f"{len(state['decisions'])} decisions, {len(warnings)} warning(s)")
        return 0

    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                     newline="\n")
    payload = json.dumps(resolved, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    marker = "/*__RESEARCH_STATE__*/null"
    if marker not in html_text:
        print("ERROR: template has no state marker")
        return 1
    GUIDE.write_text(html_text.replace(marker, payload), encoding="utf-8", newline="\n")
    print(f"wrote {rel(STATE)} and {rel(GUIDE)} — {prog['tasks_done']}/{plan['total']} tasks, "
          f"current {prog['current_task']}, {len(warnings)} warning(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="validate only; write nothing")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    return build(args.check)


if __name__ == "__main__":
    raise SystemExit(main())

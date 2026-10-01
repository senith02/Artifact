"""P3-T1 — test-split model evaluation, confirmatory ablation and SHAP.

Nothing is fitted here. Every model, the duration control `d̂`, each arm's
calibrator and each arm's frozen threshold τ are **loaded** from the P1
artifacts and applied unchanged (eval_protocol §2, §5; §A1.7 use-discipline).

Two modes, and the order between them is enforced:

``--split calibration``  (rehearsal)
    Runs the identical pipeline on the calibration split, where every number
    already exists in ``results/p1/``. It must reproduce the stored arm metrics,
    family deltas (with their bootstrap CIs), `d̂` quality and SHAP summaries
    **exactly**, or it fails. It records a fingerprint of this code, the frozen
    artifacts and the split, plus the bootstrap budget used.

``--split test --open-test-split``  (the single test pass)
    Refuses to run unless a rehearsal at the full protocol budget (B = 1000)
    passed with the **same** fingerprint. It then writes the sentinel
    ``results/p3/test_split_opened.json`` *before* any test row is kept, and
    refuses a second pass: re-running after test results exist needs a
    decision-log entry, named with ``--rerun-under DL-xxx`` (development_plan.md
    P3-T1 DoD).

Outputs of the test pass (``results/p3/``):
    model_report.{json,md} · replication_table.md · shap/ · calibration/ ·
    test_scores.csv.gz (per-build scores, DL-027 §3)

Run:  PYTHONPATH=. python scripts/evaluate_test.py --split calibration
      PYTHONPATH=. python scripts/evaluate_test.py --split test --open-test-split
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from scheduler_core import (ablation_stats as ab, admission, config, data,
                            duration_estimator as de, features, models, splits)

CODE_ROOT = Path(__file__).resolve().parents[1]
ROOT = CODE_ROOT.parent
P1 = ROOT / "results" / "p1"
P3 = ROOT / "results" / "p3"
ARTIFACTS = CODE_ROOT / "artifacts"
MODEL_DIR = ARTIFACTS / "models"
DECISION_LOG = ROOT / "governance" / "03_DECISION_LOG.md"
SENTINEL = P3 / "test_split_opened.json"
DEFAULT_REHEARSAL_DIR = P3 / "rehearsal"
CHUNK = 300_000
COMMAND = "PYTHONPATH=. python scripts/evaluate_test.py"
PRIMARY_ALGORITHM = models.PRIMARY_ALGORITHM
FAMILY_IDS: tuple[str, ...] = tuple(features.FAMILIES.keys())
P1T5_ARMS: tuple[str, ...] = tuple(f"{a}:{arm}" for a in models.ALGORITHMS
                                   for arm in ("control", "full"))
FAMILY_ARMS: tuple[str, ...] = tuple(f"{PRIMARY_ALGORITHM}:{f}" for f in FAMILY_IDS)
ALL_ARMS: tuple[str, ...] = P1T5_ARMS + FAMILY_ARMS
PROJECT_CODED_SHARE = 0.8          # §A1.9 threshold, as P1-T6 (DL-019 §6)
TOP_K = 10

#: Metric keys a reproduced arm must match exactly (the P1-T5/P1-T6 record).
ARM_KEYS: tuple[str, ...] = ("n", "positives", "base_rate", "pr_auc", "roc_auc", "brier",
                             "ece", "tau", "precision_at_tau", "recall_at_tau", "f1_at_tau")

#: Files whose bytes define "the same pipeline" between rehearsal and test.
FINGERPRINT_FILES: tuple[Path, ...] = (
    CODE_ROOT / "scripts" / "evaluate_test.py",
    CODE_ROOT / "scheduler_core" / "ablation_stats.py",
    CODE_ROOT / "scheduler_core" / "admission.py",
    CODE_ROOT / "scheduler_core" / "data.py",
    CODE_ROOT / "scheduler_core" / "duration_estimator.py",
    CODE_ROOT / "scheduler_core" / "features.py",
    CODE_ROOT / "scheduler_core" / "models.py",
    ARTIFACTS / "duration_estimator.joblib",
    P1 / "split_assignment.csv",
    *(MODEL_DIR / f"{t.replace(':', '__')}.joblib" for t in ALL_ARMS),
)

READ_COLUMNS: tuple[str, ...] = tuple(
    c for c in data.EXPECTED_HEADER
    if c in set(features.READ_COLUMNS) | {"tr_duration"}
)


class GuardError(SystemExit):
    """Raised when the test split may not be opened (or re-opened)."""


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #

def pipeline_fingerprint(files: tuple[Path, ...] = FINGERPRINT_FILES) -> str:
    h = hashlib.sha256()
    for path in files:
        h.update(path.name.encode("utf-8"))
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def dl_entry_exists(dl_id: str, log_path: Path = DECISION_LOG) -> bool:
    if not re.fullmatch(r"DL-\d{3}", dl_id):
        return False
    return re.search(rf"^### {re.escape(dl_id)} ", log_path.read_text(encoding="utf-8"),
                     flags=re.MULTILINE) is not None


def assert_may_open_test(*, fingerprint: str, rehearsal_path: Path, sentinel: Path,
                         rerun_under: str | None, log_path: Path = DECISION_LOG) -> dict:
    """Every condition for the single test pass; returns the rehearsal record."""
    if sentinel.exists() and rerun_under is None:
        opened = json.loads(sentinel.read_text(encoding="utf-8"))
        raise GuardError(
            f"the test split was already opened ({opened.get('opened_at_utc')}). A second "
            "pass needs a decision-log entry: pass --rerun-under DL-xxx (P3-T1 DoD).")
    if rerun_under is not None and not dl_entry_exists(rerun_under, log_path):
        raise GuardError(f"--rerun-under {rerun_under}: no such entry in {log_path.name}")
    if not rehearsal_path.exists():
        raise GuardError(f"no rehearsal record at {rehearsal_path}; run --split calibration first")
    rehearsal = json.loads(rehearsal_path.read_text(encoding="utf-8"))
    if not rehearsal.get("all_checks_pass"):
        raise GuardError("the calibration rehearsal did not reproduce P1 exactly")
    if rehearsal.get("n_resamples") != ab.N_RESAMPLES:
        raise GuardError(f"the rehearsal ran at B = {rehearsal.get('n_resamples')}, not the "
                         f"protocol's {ab.N_RESAMPLES}; re-rehearse at full budget")
    if rehearsal.get("fingerprint") != fingerprint:
        raise GuardError("code or artifacts changed since the rehearsal passed; re-rehearse")
    return rehearsal


# --------------------------------------------------------------------------- #
# Data — identical loading to scripts/run_ablation.py and train_models.py
# --------------------------------------------------------------------------- #

def load_builds_with_duration(chunksize: int = CHUNK) -> pd.DataFrame:
    running: pd.DataFrame | None = None
    for chunk in data.read_chunks(chunksize=chunksize, usecols=READ_COLUMNS):
        chunk = chunk.assign(_dur=pd.to_numeric(chunk["tr_duration"], errors="coerce"))
        g = chunk.groupby("tr_build_id", sort=False)
        cols = [c for c in chunk.columns if c not in ("tr_build_id", "tr_duration", "_dur")]
        agg = g[cols].first()
        agg["tr_duration"] = g["_dur"].max()
        if running is None:
            running = agg
            continue
        cat = pd.concat([running, agg])
        gg = cat.groupby(level=0, sort=False)
        out = gg[[c for c in cat.columns if c != "tr_duration"]].first()
        out["tr_duration"] = gg["tr_duration"].max()
        running = out
    builds = running.reset_index()
    return builds.loc[features.analytic_mask(builds)].reset_index(drop=True)


def load_frozen_assignment() -> tuple[dict[str, str], str]:
    manifest = json.loads((P1 / "splits.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(P1 / "split_assignment.csv", dtype=str)
    assignment = dict(zip(frame["gh_project_name"], frame["split"]))
    digest = splits.assignment_hash(assignment)
    if digest != manifest["freeze"]["assignment_sha256"]:
        raise SystemExit("FATAL: split_assignment.csv does not match its frozen digest")
    return assignment, digest


def load_arm(tag: str) -> models.TrainedArm:
    algorithm, arm = tag.split(":")
    if arm in features.FAMILIES:
        models.ARMS[arm] = (models.D_HAT_COLUMN,) + tuple(features.FAMILIES[arm])
    trained = models.load_arm(MODEL_DIR / f"{algorithm}__{arm}.joblib")
    if trained.name != tag:
        raise SystemExit(f"FATAL: artifact for {tag} holds {trained.name}")
    return trained


def stored_arm_record(tag: str) -> dict:
    """The P1 record an arm must reproduce on calibration (and whose fit id binds)."""
    algorithm, arm = tag.split(":")
    if arm in features.FAMILIES:
        return json.loads((P1 / "ablation" / "deltas.json").read_text(
            encoding="utf-8"))["families"][arm]["arm_result"]
    return json.loads((P1 / "model_training.json").read_text(encoding="utf-8"))["arms"][tag]


# --------------------------------------------------------------------------- #
# SHAP — identical helpers to scripts/run_ablation.py
# --------------------------------------------------------------------------- #

def feature_to_family() -> dict[str, str]:
    return {f: fam for fam, members in features.FAMILIES.items() for f in members}


def design_column_family(column: str, mapping: dict[str, str]) -> str:
    if column == models.D_HAT_COLUMN:
        return "control"
    if column in mapping:
        return mapping[column]
    if column.startswith("lang="):
        return mapping["lang"]
    raise KeyError(f"design column {column!r} maps to no known feature/family")


def shap_summary(full_arm: models.TrainedArm, frame: pd.DataFrame, projects: pd.Series,
                 *, n_resamples: int) -> dict:
    import shap

    x = models.design_matrix(frame, full_arm.arm,
                             lang_levels=full_arm.lang_levels)[list(full_arm.design_columns)]
    raw = shap.TreeExplainer(full_arm.base_model).shap_values(x)
    values = np.asarray(raw[1] if isinstance(raw, list) else raw, dtype="float64")
    f2fam = feature_to_family()
    col_family = {c: design_column_family(c, f2fam) for c in x.columns}

    per_feature: dict[str, dict] = {}
    for i, col in enumerate(x.columns):
        vals = values[:, i]
        per_feature[col] = {
            "family": col_family[col],
            "mean_abs_shap": float(np.mean(np.abs(vals))),
            "mean_signed_shap": float(np.mean(vals)),
            "monotonicity": ab.spearman_with_ci(x[col].to_numpy(), vals,
                                                n_resamples=n_resamples),
        }
    per_family, variance = {}, {}
    for fam in ("control",) + FAMILY_IDS:
        cols = [c for c, f in col_family.items() if f == fam]
        contrib = (values[:, [x.columns.get_loc(c) for c in cols]].sum(axis=1)
                   if cols else np.zeros(len(x)))
        per_family[fam] = {"mean_abs_contribution": float(np.mean(np.abs(contrib))),
                           "mean_signed_contribution": float(np.mean(contrib))}
        vd = ab.variance_decomposition(contrib, projects.to_numpy())
        vd["project_identity_coded"] = bool(vd["between_share"] >= PROJECT_CODED_SHARE)
        variance[fam] = vd
    return {"per_feature": per_feature, "per_family": per_family,
            "variance_decomposition": variance,
            "project_identity_coded_threshold": PROJECT_CODED_SHARE}


def top_k(per_feature: dict, k: int = TOP_K) -> list[dict]:
    ranked = sorted(per_feature.items(), key=lambda kv: -kv[1]["mean_abs_shap"])[:k]
    out = []
    for col, r in ranked:
        m = r["monotonicity"]
        direction = ("degenerate" if m.get("degenerate") else
                     "increases risk" if m["monotone"] and m["rho"] > 0 else
                     "decreases risk" if m["monotone"] and m["rho"] < 0 else "not monotone")
        out.append({"feature": col, "family": r["family"],
                    "mean_abs_shap": r["mean_abs_shap"],
                    "mean_signed_shap": r["mean_signed_shap"],
                    "spearman_rho": None if m.get("degenerate") else m["rho"],
                    "direction": direction})
    return out


def compare_shap(cal: dict, test: dict) -> dict:
    """Calibration-split SHAP (used for policy fitting) vs test-split SHAP."""
    cols = sorted(set(cal["per_feature"]) & set(test["per_feature"]))
    a = pd.Series([cal["per_feature"][c]["mean_abs_shap"] for c in cols])
    b = pd.Series([test["per_feature"][c]["mean_abs_shap"] for c in cols])
    top_cal = {r["feature"] for r in top_k(cal["per_feature"])}
    top_test = {r["feature"] for r in top_k(test["per_feature"])}
    fam = {f: {"calibration": cal["per_family"][f]["mean_abs_contribution"],
               "test": test["per_family"][f]["mean_abs_contribution"]}
           for f in ("control",) + FAMILY_IDS}
    rank = lambda d: {f: i + 1 for i, f in enumerate(sorted(d, key=lambda k: -d[k]))}
    rc = rank({f: v["calibration"] for f, v in fam.items()})
    rt = rank({f: v["test"] for f, v in fam.items()})
    for f in fam:
        fam[f].update({"rank_calibration": rc[f], "rank_test": rt[f]})
    return {
        "n_features_compared": len(cols),
        "spearman_mean_abs_shap_calibration_vs_test": float(a.corr(b, method="spearman")),
        "top10_overlap": len(top_cal & top_test),
        "top10_only_calibration": sorted(top_cal - top_test),
        "top10_only_test": sorted(top_test - top_cal),
        "per_family": fam,
    }


# --------------------------------------------------------------------------- #
# Duration control quality (§A1.1, duration_control_spec §6.3)
# --------------------------------------------------------------------------- #

def duration_quality(est: de.DurationEstimator, frame: pd.DataFrame, keys: pd.DataFrame,
                     durations: pd.Series) -> dict:
    def evaluate(estimates: pd.DataFrame) -> dict:
        project_only = (estimates["fallback_level"] == "project").to_numpy()
        return {"all_builds": de.score_quality(estimates, durations),
                "project_rung_only": de.score_quality(estimates.loc[project_only],
                                                      durations.loc[project_only]),
                "coverage": de.coverage_table(estimates)}

    history = de.causal_project_history(keys, durations)
    de.assert_history_is_causal(keys, history)
    hist_50 = de.causal_project_history(keys, durations, window=50)
    de.assert_history_is_causal(keys, hist_50)
    return {
        "forms": {"4b_expanding": evaluate(est.predict_4b(frame, history)),
                  "4a_xgboost": evaluate(est.predict_4a(frame, history)),
                  "4a_ridge": evaluate(est.predict_4a(frame, history, regressor="ridge"))},
        "sensitivities": {
            "4b_trailing_50": evaluate(est.predict_4b(frame, hist_50)),
            "4b_min_history_5": evaluate(est.predict_4b(frame, history, min_history=5)),
            "4b_min_history_20": evaluate(est.predict_4b(frame, history, min_history=20)),
        },
        "_d_hat_4a_log1p": est.predict_4a(frame, history)["d_hat_log1p"].to_numpy(),
    }


# --------------------------------------------------------------------------- #
# Rehearsal checks — calibration must reproduce P1 exactly
# --------------------------------------------------------------------------- #

def same(a: object, b: object) -> bool:
    """Exact equality, except that two NaNs (a degenerate SHAP ρ) count as equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return True
    return a == b


def rehearsal_checks(ev: dict, *, full_budget: bool) -> dict[str, dict]:
    checks: dict[str, dict] = {}

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = {"pass": bool(ok), "detail": detail}

    for tag in ALL_ARMS:
        stored = stored_arm_record(tag)["calibrated"]
        fresh = ev["arms"][tag]["metrics"]
        bad = [k for k in ARM_KEYS if fresh[k] != stored[k]]
        record(f"arm_metrics:{tag}", not bad, f"mismatch on {bad}" if bad else "exact")

    stored_deltas = json.loads((P1 / "ablation" / "deltas.json").read_text(encoding="utf-8"))
    for fam in FAMILY_IDS:
        s = stored_deltas["families"][fam]["delta_vs_control"]
        f = ev["family_deltas"][fam]
        keys = ("control", "treatment", "delta") + (("ci_lo", "ci_hi") if full_budget else ())
        bad = [f"{m}.{k}" for m in ("pr_auc", "roc_auc", "brier", "ece") for k in keys
               if f[m][k] != s[m][k]]
        record(f"family_delta:{fam}", not bad, f"mismatch on {bad}" if bad else
               ("exact incl. CIs" if full_budget else "exact point estimates (CIs not "
                "comparable below B = 1000)"))

    stored_dur = json.loads((P1 / "duration_control.json").read_text(encoding="utf-8"))
    for form in ("4b_expanding", "4a_xgboost", "4a_ridge"):
        for view in ("all_builds", "project_rung_only"):
            s = stored_dur["calibration_split"][form][view]
            f = ev["duration_control"]["forms"][form][view]
            bad = [k for k in s if f.get(k) != s[k]]
            record(f"duration:{form}:{view}", not bad, f"mismatch on {bad}" if bad else "exact")

    stored_shap = json.loads((P1 / "shap" / "shap_summary.json").read_text(encoding="utf-8"))
    for fam in ("control",) + FAMILY_IDS:
        s = stored_shap["per_family"][fam]["mean_abs_contribution"]
        f = ev["shap"]["per_family"][fam]["mean_abs_contribution"]
        sv = stored_shap["variance_decomposition"][fam]["between_share"]
        fv = ev["shap"]["variance_decomposition"][fam]["between_share"]
        record(f"shap_family:{fam}", f == s and fv == sv,
               "exact" if (f == s and fv == sv) else f"{f!r} vs {s!r}; {fv!r} vs {sv!r}")
    if full_budget:
        bad = [c for c, r in ev["shap"]["per_feature"].items()
               if not same(r["monotonicity"], stored_shap["per_feature"][c]["monotonicity"])]
        record("shap_monotonicity", not bad, f"mismatch on {bad}" if bad else "exact")
    return checks


# --------------------------------------------------------------------------- #
# The evaluation (identical for both splits)
# --------------------------------------------------------------------------- #

def evaluate_split(split_name: str, *, n_resamples: int, t0: float) -> tuple[dict, pd.DataFrame]:
    print(f"reading {data.DEFAULT_DATASET_PATH} …", flush=True)
    builds = load_builds_with_duration()
    assignment, split_digest = load_frozen_assignment()
    split_of = builds["gh_project_name"].map(assignment)
    if split_of.isna().any():
        raise SystemExit("FATAL: a build's project is absent from the frozen split")
    n_analytic = len(builds)
    keep = (split_of == split_name).to_numpy()
    n_dropped = {s: int((split_of == s).sum()) for s in ("train", "calibration", "test")
                 if s != split_name}
    builds = builds.loc[keep].reset_index(drop=True)
    print(f"  analytic builds {n_analytic:,}; kept {split_name} {len(builds):,} "
          f"({builds['gh_project_name'].nunique():,} projects); dropped {n_dropped} "
          f"({time.time()-t0:.0f}s)", flush=True)

    durations = pd.Series(pd.to_numeric(builds["tr_duration"], errors="coerce").to_numpy(),
                          index=builds.index, name="tr_duration")
    matrix = features.build_feature_matrix(builds)
    assert "tr_duration" not in matrix.columns
    y = features.label_from_status(builds)
    if y.isna().any():
        raise SystemExit("FATAL: the analytic set produced an unlabelled build")
    y = y.astype("int64")
    keys = builds[list(features.KEY_COLUMNS)]

    frozen_dur = json.loads((P1 / "duration_control.json").read_text(encoding="utf-8"))
    fit_id = frozen_dur["provenance"]["fit_id"]
    estimator = de.DurationEstimator.load(ARTIFACTS / "duration_estimator.joblib")
    d_hat = models.attach_d_hat(matrix, keys, durations, estimator=estimator,
                                expected_fit_id=fit_id)
    matrix[models.D_HAT_COLUMN] = d_hat.to_numpy()
    features.assert_no_leakage(columns=matrix.columns)

    print(f"[{time.time()-t0:6.0f}s] duration-control quality …", flush=True)
    dq = duration_quality(estimator, matrix, keys, durations)
    d_hat_4a = dq.pop("_d_hat_4a_log1p")

    arms: dict[str, dict] = {}
    probs: dict[str, np.ndarray] = {}
    y_np = y.to_numpy()
    for tag in ALL_ARMS:
        trained = load_arm(tag)
        stored = stored_arm_record(tag)
        if trained.provenance["fit_id"] != stored["fit_id"]:
            raise SystemExit(f"FATAL: {tag} fit id {trained.provenance['fit_id']} is not the "
                             f"frozen {stored['fit_id']}")
        p = trained.predict_proba(matrix)
        probs[tag] = p
        metrics = models.score_split(y_np, p, tau=trained.tau)
        print(f"[{time.time()-t0:6.0f}s] {tag}: PR-AUC {metrics['pr_auc']:.6f} — CIs …",
              flush=True)
        arms[tag] = {
            "fit_id": trained.provenance["fit_id"],
            "calibrator": trained.calibrator_kind,
            "metrics": metrics,
            "ci": ab.bootstrap_metric_ci(y_np, p, tau=trained.tau, n_resamples=n_resamples),
            "predicted_positive_rate_at_tau": float(np.mean(p >= trained.tau)),
            "reliability_bins": models.reliability_bins(y_np, p).to_dict(orient="records"),
        }

    control = probs[f"{PRIMARY_ALGORITHM}:control"]
    family_deltas = {}
    for fam in FAMILY_IDS:
        print(f"[{time.time()-t0:6.0f}s] paired delta {fam} vs control …", flush=True)
        family_deltas[fam] = ab.paired_metric_delta(
            y_np, control, probs[f"{PRIMARY_ALGORITHM}:{fam}"], n_resamples=n_resamples)
    full_vs_control = {}
    for algorithm in models.ALGORITHMS:
        print(f"[{time.time()-t0:6.0f}s] paired delta {algorithm} full vs control …",
              flush=True)
        full_vs_control[algorithm] = ab.paired_metric_delta(
            y_np, probs[f"{algorithm}:control"], probs[f"{algorithm}:full"],
            n_resamples=n_resamples)

    admission_sweep = admission.floor_sweep(
        {fam: family_deltas[fam]["pr_auc"] for fam in FAMILY_IDS})
    admission_x1 = admission.admission_set(
        {fam: family_deltas[fam]["pr_auc"] for fam in FAMILY_IDS})

    print(f"[{time.time()-t0:6.0f}s] SHAP on the frozen full arm …", flush=True)
    shap_out = shap_summary(load_arm(f"{PRIMARY_ALGORITHM}:full"), matrix,
                            builds["gh_project_name"], n_resamples=n_resamples)

    scores = pd.DataFrame({
        "tr_build_id": builds["tr_build_id"].to_numpy(),
        "gh_project_name": builds["gh_project_name"].to_numpy(),
        "gh_build_started_at": builds["gh_build_started_at"].to_numpy(),
        "y_fail": y_np,
        "d_hat_log1p_4b": matrix[models.D_HAT_COLUMN].to_numpy(),
        "d_hat_log1p_4a": d_hat_4a,
        **{f"p__{t.replace(':', '__')}": probs[t] for t in ALL_ARMS},
    })

    ev = {
        "split": split_name,
        "split_digest": split_digest,
        "duration_control_fit_id": fit_id,
        "population": {
            "analytic_builds_read": n_analytic,
            "builds": int(len(builds)),
            "projects": int(builds["gh_project_name"].nunique()),
            "failures": int(y_np.sum()),
            "failure_rate_pct": round(100 * float(y_np.mean()), 4),
            "other_splits_dropped_unread": n_dropped,
        },
        "duration_control": dq,
        "arms": arms,
        "family_deltas": family_deltas,
        "full_vs_control": full_vs_control,
        "admission": {"x1": admission_x1, "floor_sweep": admission_sweep},
        "shap": shap_out,
    }
    return ev, scores


# --------------------------------------------------------------------------- #
# Reports (test pass)
# --------------------------------------------------------------------------- #

def replication_table(ev: dict) -> dict:
    cal_adm = json.loads((P1 / "admission.json").read_text(encoding="utf-8"))
    cal_deltas = json.loads((P1 / "ablation" / "deltas.json").read_text(encoding="utf-8"))
    cal_verdicts = cal_adm["model_level_admission"]["verdicts"]
    rows = {}
    for fam in FAMILY_IDS:
        c = cal_deltas["families"][fam]["delta_vs_control"]["pr_auc"]
        t = ev["family_deltas"][fam]["pr_auc"]
        cv = bool(cal_verdicts[fam]["admitted"])
        tv = bool(ev["admission"]["x1"]["verdicts"][fam]["admitted"])
        rows[fam] = {
            "calibration": {"delta": c["delta"], "ci_lo": c["ci_lo"], "ci_hi": c["ci_hi"],
                            "ci_direction": admission.ci_direction(c["ci_lo"], c["ci_hi"]),
                            "admitted": cv},
            "test": {"delta": t["delta"], "ci_lo": t["ci_lo"], "ci_hi": t["ci_hi"],
                     "ci_direction": admission.ci_direction(t["ci_lo"], t["ci_hi"]),
                     "admitted": tv},
            "verdict_replicates": cv == tv,
            "sign_replicates": bool(np.sign(c["delta"]) == np.sign(t["delta"])),
        }
    cal_sweep = cal_adm["floor_sweep"]["by_floor"]
    sweep = {k: {"calibration_admitted": cal_sweep[k]["admitted"],
                 "test_admitted": v["admitted"],
                 "replicates": cal_sweep[k]["admitted"] == v["admitted"]}
             for k, v in ev["admission"]["floor_sweep"]["by_floor"].items()}
    return {"families": rows, "floor_sweep": sweep,
            "all_verdicts_replicate": all(r["verdict_replicates"] for r in rows.values()),
            "admitted_set_test_x1": ev["admission"]["x1"]["admitted"]}


def _ci(d: dict, key: str = "point", fmt: str = ".6f") -> str:
    return f"{d[key]:{fmt}} [{d['ci_lo']:{fmt}}, {d['ci_hi']:{fmt}}]"


def _dci(d: dict) -> str:
    return f"{d['delta']:+.6f} [{d['ci_lo']:+.6f}, {d['ci_hi']:+.6f}]"


def write_reliability_plots(ev: dict, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for tag in P1T5_ARMS:
        bins = pd.DataFrame(ev["arms"][tag]["reliability_bins"])
        bins = bins[bins["n"] > 0]
        fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=150)
        ax.plot([0, 1], [0, 1], ls="--", lw=0.8, color="#7f7f7f", label="perfect")
        ax.plot(bins["confidence"], bins["observed"], marker="o", lw=1.2, color="#1f77b4",
                label=tag)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("mean predicted failure probability")
        ax.set_ylabel("observed failure rate")
        ax.set_title(f"Reliability — {tag}, test split", fontsize=9)
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(alpha=0.3, lw=0.5)
        fig.tight_layout()
        path = out_dir / f"reliability_{tag.replace(':', '__')}.png"
        fig.savefig(path)
        plt.close(fig)
        written.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return written


def write_shap_outputs(ev: dict, comparison: dict, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {**ev["shap"], "top10": top_k(ev["shap"]["per_feature"]),
               "comparison_vs_calibration": comparison}
    (out_dir / "shap_summary.json").write_text(json.dumps(payload, indent=2, default=str),
                                               encoding="utf-8")
    order = ["control"] + list(FAMILY_IDS)
    cal = [comparison["per_family"][f]["calibration"] for f in order]
    tst = [comparison["per_family"][f]["test"] for f in order]
    ypos = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=150)
    ax.barh(ypos - 0.2, cal, height=0.4, color="#9ecae1", label="calibration")
    ax.barh(ypos + 0.2, tst, height=0.4, color="#1f77b4", label="test")
    ax.set_yticks(ypos, order)
    ax.invert_yaxis()
    ax.set_xlabel("mean |Σ SHAP| per build — frozen full XGBoost arm")
    ax.set_title("Per-family SHAP magnitude, calibration vs test", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(axis="x", alpha=0.3, lw=0.5)
    fig.tight_layout()
    fig.savefig(out_dir / "family_importance.png")
    plt.close(fig)

    L = ["# SHAP attribution — frozen full XGBoost arm, **test split** (P3-T1 S3)\n",
         f"> Generated by `{COMMAND} --split test --open-test-split`. Every number below "
         "comes from that run (R1). `shap.TreeExplainer` on the frozen `full` arm's base "
         "model; calibration is a post-hoc monotone map and is not part of the explained "
         "model.\n",
         "\n## 1. Top-10 attributions, with direction\n",
         "Direction is the sign of the feature-value / SHAP-value Spearman ρ, and is "
         "stated only where its 95% bootstrap CI excludes 0 (§A1.8).\n",
         "| rank | feature | family | mean \\|SHAP\\| | mean signed SHAP | Spearman ρ | "
         "direction |", "| --: | :-- | :-- | --: | --: | --: | :-- |"]
    for i, r in enumerate(payload["top10"], 1):
        rho = "—" if r["spearman_rho"] is None else f"{r['spearman_rho']:+.4f}"
        L.append(f"| {i} | `{r['feature']}` | {r['family']} | {r['mean_abs_shap']:.6f} | "
                 f"{r['mean_signed_shap']:+.6f} | {rho} | {r['direction']} |")
    L += ["\n## 2. Per-family magnitude and project-identity share\n",
          "| family | mean \\|Σ SHAP\\| (test) | mean \\|Σ SHAP\\| (calibration) | rank test "
          "| rank calibration | between-project share (test) |",
          "| :-- | --: | --: | --: | --: | --: |"]
    for f in order:
        c = comparison["per_family"][f]
        vd = ev["shap"]["variance_decomposition"][f]
        L.append(f"| `{f}` | {c['test']:.6f} | {c['calibration']:.6f} | {c['rank_test']} | "
                 f"{c['rank_calibration']} | {vd['between_share']:.4f} |")
    L += ["\n## 3. Calibration vs test (the SHAP used for policy fitting vs this one)\n",
          f"- Spearman correlation of per-feature mean \\|SHAP\\|, calibration vs test: "
          f"**{comparison['spearman_mean_abs_shap_calibration_vs_test']:.4f}** over "
          f"{comparison['n_features_compared']} design columns.",
          f"- Top-10 overlap: **{comparison['top10_overlap']} / 10**. Only in calibration's "
          f"top 10: {', '.join(f'`{c}`' for c in comparison['top10_only_calibration']) or 'none'}. "
          f"Only in test's: {', '.join(f'`{c}`' for c in comparison['top10_only_test']) or 'none'}.",
          "- `family_importance.png` plots the per-family column pair.\n"]
    (out_dir / "shap_summary.md").write_text("\n".join(L), encoding="utf-8")


def write_model_report(ev: dict, rep: dict, comparison: dict, *, meta: dict) -> None:
    cal_train = json.loads((P1 / "model_training.json").read_text(encoding="utf-8"))
    cal_dur = json.loads((P1 / "duration_control.json").read_text(encoding="utf-8"))
    pop = ev["population"]
    L: list[str] = []
    A = L.append
    A("# Test-split model evaluation + confirmatory ablation (P3-T1)\n")
    A(f"> Generated by `{meta['command']}` on {meta['run_date']} (elapsed "
      f"{meta['elapsed_s']} s). **Every number below comes from that single test pass** (R1). "
      f"Seed `{config.RANDOM_SEED}` · B = {meta['n_resamples']} · pipeline fingerprint "
      f"`{meta['fingerprint'][:16]}…`, identical to the passing calibration rehearsal "
      "(`results/p3/rehearsal/rehearsal.json`).\n")
    A("> **Nothing was fitted.** Every arm, calibrator, threshold τ and the duration control "
      "were loaded from their frozen P1 artifacts (fit ids below) and applied unchanged. "
      "This is the first and only time the test split has been read (sentinel "
      "`results/p3/test_split_opened.json`).\n")

    A("\n## 1. Population\n")
    A(f"- Test split: **{pop['builds']:,} builds / {pop['projects']:,} projects**, "
      f"{pop['failures']:,} failures (**{pop['failure_rate_pct']}%**).")
    A(f"- Other splits dropped unread after the split join: {pop['other_splits_dropped_unread']}.")
    A(f"- Calibration split, for the base-rate shift DL-017 flagged: "
      f"{round(100 * cal_train['arms']['xgboost:control']['calibrated']['base_rate'], 4)}% "
      "failure. τ was selected there and is applied here unchanged, so it is expected to be "
      "mis-centred (§2 reports the predicted-positive rate at τ).\n")

    A("\n## 2. RQ1 — discrimination and calibration of every arm (§5), with 95% CIs\n")
    A("Point estimate [95% percentile bootstrap CI], B = 1000, seed 42. PR-AUC is primary "
      "(positive = failure). τ is each arm's frozen calibration-split threshold.\n")
    A("| arm | PR-AUC | ROC-AUC | Brier | ECE | τ | precision@τ | recall@τ | F1@τ | "
      "predicted-positive rate@τ |")
    A("| :-- | :-- | :-- | :-- | :-- | --: | :-- | :-- | :-- | --: |")
    for tag in ALL_ARMS:
        a, ci = ev["arms"][tag], ev["arms"][tag]["ci"]
        A(f"| `{tag}` | {_ci(ci['pr_auc'])} | {_ci(ci['roc_auc'])} | {_ci(ci['brier'])} | "
          f"{_ci(ci['ece'])} | {a['metrics']['tau']:.4f} | {_ci(ci['precision_at_tau'], fmt='.4f')} | "
          f"{_ci(ci['recall_at_tau'], fmt='.4f')} | {_ci(ci['f1_at_tau'], fmt='.4f')} | "
          f"{a['predicted_positive_rate_at_tau']:.4f} |")
    A("\n**Calibration split vs test split, PR-AUC and ECE** (calibration values from "
      "`results/p1/model_training.json` / `ablation/deltas.json`; the calibration ECE is "
      "in-sample for the isotonic calibrator and ≈ 0 by construction, P1-T5 threat 1a — the "
      "test ECE is the first out-of-sample calibration measurement):\n")
    A("| arm | PR-AUC calibration | PR-AUC test | ECE calibration (in-sample) | ECE test |")
    A("| :-- | --: | --: | --: | --: |")
    for tag in ALL_ARMS:
        c = stored_arm_record(tag)["calibrated"]
        t = ev["arms"][tag]["metrics"]
        A(f"| `{tag}` | {c['pr_auc']:.6f} | {t['pr_auc']:.6f} | {c['ece']:.6f} | {t['ece']:.6f} |")
    A(f"\nReliability diagrams: {', '.join(f'`{p}`' for p in meta['reliability_plots'])}.\n")

    A("\n## 3. The duration control `d̂` on test (§A1.1)\n")
    A("Observed duration appears here only as §A1.2 role 1 (accounting): it measures the "
      "control after the fact. `d̂` was not refitted; ④b reads each test project's own "
      "strictly-earlier builds (DL-014).\n")
    A("| form | n | MAE (log1p) test | MAE (log1p) calibration | median AE (log1p) | "
      "MAE (s) | median AE (s) | Spearman ρ test | Spearman ρ calibration |")
    A("| :-- | --: | --: | --: | --: | --: | --: | --: | --: |")
    labels = {"4b_expanding": "④b expanding prior **(frozen primary)**",
              "4a_xgboost": "④a XGBoost regressor", "4a_ridge": "④a Ridge (reference)"}
    for form, label in labels.items():
        t = ev["duration_control"]["forms"][form]["all_builds"]
        c = cal_dur["calibration_split"][form]["all_builds"]
        A(f"| {label} | {t['n']:,} | {t['mae_log1p']:.4f} | {c['mae_log1p']:.4f} | "
          f"{t['median_ae_log1p']:.4f} | {t['mae_seconds']:,.1f} | {t['median_ae_seconds']:,.1f} | "
          f"{t['spearman_rho']:.4f} | {c['spearman_rho']:.4f} |")
    cov = ev["duration_control"]["forms"]["4b_expanding"]["coverage"]["levels"]
    A(f"\n④b cold-start coverage on test: project rung {cov['project']['n']:,} "
      f"({cov['project']['pct']}%), language {cov['language']['n']:,} "
      f"({cov['language']['pct']}%), global {cov['global']['n']:,} ({cov['global']['pct']}%).\n")
    A("Declared sensitivities (secondary; they cannot change the frozen primary):\n")
    A("| variant | MAE (log1p) test | Spearman ρ test |")
    A("| :-- | --: | --: |")
    for k, v in ev["duration_control"]["sensitivities"].items():
        t = v["all_builds"]
        A(f"| `{k}` | {t['mae_log1p']:.4f} | {t['spearman_rho']:.4f} |")

    A("\n## 4. RQ2 (model altitude) — confirmatory incremental value vs `{d̂}` (§A1.4)\n")
    A("Paired bootstrap of treatment − control over the shared test-build index (B = 1000, "
      "seed 42). The admission rule is the unchanged `scheduler_core.admission` "
      "implementation of §A1.7 (floor +0.01 absolute, CI excluding 0 above it).\n")
    A("| family | ΔPR-AUC [95% CI] | ΔROC-AUC [95% CI] | ΔBrier [95% CI] | ΔECE [95% CI] | "
      "verdict (×1) |")
    A("| :-- | :-- | :-- | :-- | :-- | :-- |")
    for fam in FAMILY_IDS:
        d = ev["family_deltas"][fam]
        v = ev["admission"]["x1"]["verdicts"][fam]
        A(f"| **{fam}** | {_dci(d['pr_auc'])} | {_dci(d['roc_auc'])} | {_dci(d['brier'])} | "
          f"{_dci(d['ece'])} | {'**admitted**' if v['admitted'] else 'rejected'} — "
          f"{v['reason_short']} |")
    A("\nFloor sweep (§A1.7, only the floor scales):\n")
    A("| floor | admitted on test |")
    A("| --: | :-- |")
    for k, v in ev["admission"]["floor_sweep"]["by_floor"].items():
        A(f"| {v['floor']:+.4f} ({k}) | {', '.join(v['admitted']) or '**(empty)**'} |")
    A(f"\nAdmitted set stable across the sweep: **{ev['admission']['floor_sweep']['stable']}**.\n")
    A("**Full arm vs control, per algorithm** (all 28 features added to `d̂`):\n")
    A("| algorithm | ΔPR-AUC [95% CI] | ΔROC-AUC [95% CI] | ΔBrier [95% CI] |")
    A("| :-- | :-- | :-- | :-- |")
    for alg, d in ev["full_vs_control"].items():
        A(f"| `{alg}` | {_dci(d['pr_auc'])} | {_dci(d['roc_auc'])} | {_dci(d['brier'])} |")

    A("\n## 5. Does the calibration-split admission decision replicate on test?\n")
    A("See `replication_table.md` for the full table. Summary: every family verdict "
      f"replicates = **{rep['all_verdicts_replicate']}**; admitted set on test at ×1 = "
      f"**{', '.join(rep['admitted_set_test_x1']) or '(empty)'}**.\n")

    A("\n## 6. SHAP on test (S3)\n")
    A(f"Full detail in `results/p3/shap/shap_summary.md`. Calibration-vs-test Spearman of "
      f"per-feature mean |SHAP| = **{comparison['spearman_mean_abs_shap_calibration_vs_test']:.4f}**; "
      f"top-10 overlap **{comparison['top10_overlap']} / 10**.\n")

    A("\n## 7. Context against the literature (S4) — context, not comparability\n")
    A("Mhalla & Saied (2024) report AUC ≈ 0.90 for CI-*skip* detection (spec §2.1; "
      "eval_protocol §5). That is a different task (skip-worthiness, not failure), different "
      "data and a different label, and it uses no duration control. The ROC-AUCs in §2 are "
      "therefore **not comparable** to it and no claim of being better or worse is made. "
      "The comparison this study rests on is internal and paired: every SE arm against "
      "`{d̂}` on the same test builds.\n")

    A("\n## 8. What this report does and does not establish\n")
    A("- It is the **model-altitude** RQ1/RQ2 evidence on held-out projects. The decision-"
      "altitude RQ2 test (④ vs ⑤ frontiers) is P3-T3's; the strategy comparison is P3-T2's.")
    A("- Effect sizes lead (§A1.11): at this N a CI excluding 0 is nearly free, so "
      "'material' is reserved for the §A1.7 floor.")
    A("- Bounds carried from P1: F2 is structurally weakened (DL-016), two textbook JIT "
      "predictors are absent (DL-015), one algorithm and one search budget were used for the "
      "family arms (DL-018/DL-019), and `d̂` is a *predicted* quantity, so the question "
      "answered is value beyond *predictable* duration.\n")

    A("\n## 9. Provenance footer\n")
    A(f"- Command: `{meta['command']}`; rehearsal: `{COMMAND} --split calibration` "
      "(`results/p3/rehearsal/`).")
    A(f"- Split digest `{ev['split_digest'][:16]}…` re-verified at load; duration control fit "
      f"id `{ev['duration_control_fit_id']}` (primary ④b), loaded not refitted.")
    A("- Arm fit ids: " + ", ".join(f"`{t}` {ev['arms'][t]['fit_id']}" for t in ALL_ARMS) + ".")
    A(f"- Per-build scores (DL-027 §3): `results/p3/test_scores.csv.gz` (sha256 "
      f"`{meta['scores_sha256'][:16]}…`).")
    A(f"- Machine-readable: `results/p3/model_report.json`.\n")
    (P3 / "model_report.md").write_text("\n".join(L), encoding="utf-8")


def write_replication_md(rep: dict) -> None:
    L = ["# Calibration vs test — does the model-level admission decision replicate? (P3-T1)\n",
         "> Calibration numbers: `results/p1/ablation/deltas.json` and `results/p1/admission.json` "
         "(P1-T6/P1-T7). Test numbers: this task's single test pass (`model_report.json`). The "
         "rule applied to both is the same `scheduler_core.admission` code. A family admitted on "
         "calibration that fails on test — or the reverse — is a finding and is reported here.\n",
         "| family | ΔPR-AUC calibration [95% CI] | verdict calibration | ΔPR-AUC test [95% CI] "
         "| verdict test | verdict replicates | sign replicates |",
         "| :-- | :-- | :-- | :-- | :-- | :-: | :-: |"]
    for fam, r in rep["families"].items():
        c, t = r["calibration"], r["test"]
        L.append(f"| **{fam}** | {_dci(c)} | {'admitted' if c['admitted'] else 'rejected'} | "
                 f"{_dci(t)} | {'admitted' if t['admitted'] else 'rejected'} | "
                 f"{'yes' if r['verdict_replicates'] else '**no**'} | "
                 f"{'yes' if r['sign_replicates'] else '**no**'} |")
    L += ["\n**Floor sweep, both splits:**\n",
          "| floor multiplier | admitted on calibration | admitted on test | replicates |",
          "| :-- | :-- | :-- | :-: |"]
    for k, v in rep["floor_sweep"].items():
        L.append(f"| {k} | {', '.join(v['calibration_admitted']) or '(empty)'} | "
                 f"{', '.join(v['test_admitted']) or '(empty)'} | "
                 f"{'yes' if v['replicates'] else '**no**'} |")
    L.append(f"\nEvery family verdict replicates: **{rep['all_verdicts_replicate']}**.\n")
    (P3 / "replication_table.md").write_text("\n".join(L), encoding="utf-8")


def write_rehearsal(ev: dict, checks: dict, *, out_dir: Path, meta: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "mode": "calibration rehearsal — reproduces P1; not a test result",
        **meta,
        "all_checks_pass": all(c["pass"] for c in checks.values()),
        "n_checks": len(checks),
        "n_failed": sum(not c["pass"] for c in checks.values()),
        "checks": checks,
        "population": ev["population"],
    }
    (out_dir / "rehearsal.json").write_text(json.dumps(record, indent=2, default=str),
                                            encoding="utf-8")
    L = ["# P3-T1 calibration rehearsal — the pipeline must reproduce P1 before test opens\n",
         f"> `{meta['command']}` on {meta['run_date']}, B = {meta['n_resamples']}, elapsed "
         f"{meta['elapsed_s']} s. **Calibration split only; the test split was dropped unread.** "
         "Every check compares a freshly computed number with the value stored by the P1 task "
         "that produced it, for exact equality.\n",
         f"**{record['n_checks'] - record['n_failed']} / {record['n_checks']} checks pass** — "
         f"all pass: **{record['all_checks_pass']}**. Fingerprint `{meta['fingerprint'][:16]}…`.\n",
         "| check | pass | detail |", "| :-- | :-: | :-- |"]
    for name, c in checks.items():
        L.append(f"| `{name}` | {'✓' if c['pass'] else '✗'} | {c['detail']} |")
    (out_dir / "rehearsal.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return record


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("calibration", "test"), required=True)
    ap.add_argument("--open-test-split", action="store_true",
                    help="required with --split test: this is the single test pass")
    ap.add_argument("--rerun-under", default=None,
                    help="DL id authorising a second test pass (P3-T1 DoD)")
    ap.add_argument("--out", type=Path, default=DEFAULT_REHEARSAL_DIR,
                    help="rehearsal only: where rehearsal.{json,md} are written")
    ap.add_argument("--n-resamples", type=int, default=ab.N_RESAMPLES,
                    help="rehearsal only (smoke runs); the test pass always uses B = 1000")
    args = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.time()
    fingerprint = pipeline_fingerprint()
    run_date = time.strftime("%Y-%m-%d")

    if args.split == "test":
        if not args.open_test_split:
            raise GuardError("--split test needs --open-test-split: it opens the test split once")
        if args.n_resamples != ab.N_RESAMPLES:
            raise GuardError("the test pass always uses the protocol's B = 1000")
        rehearsal = assert_may_open_test(
            fingerprint=fingerprint, rehearsal_path=DEFAULT_REHEARSAL_DIR / "rehearsal.json",
            sentinel=SENTINEL, rerun_under=args.rerun_under)
        P3.mkdir(parents=True, exist_ok=True)
        previous = (json.loads(SENTINEL.read_text(encoding="utf-8"))
                    if SENTINEL.exists() else None)
        SENTINEL.write_text(json.dumps({
            "opened_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "command": f"{COMMAND} --split test --open-test-split"
                       + (f" --rerun-under {args.rerun_under}" if args.rerun_under else ""),
            "fingerprint": fingerprint,
            "rehearsal_run_date": rehearsal.get("run_date"),
            "rerun_under": args.rerun_under,
            "previous_opening": previous,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"test split opening recorded in {SENTINEL.relative_to(ROOT)}", flush=True)

    ev, scores = evaluate_split(args.split, n_resamples=args.n_resamples, t0=t0)
    meta = {"command": f"{COMMAND} --split {args.split}"
                       + (" --open-test-split" if args.split == "test" else "")
                       + (f" --n-resamples {args.n_resamples}"
                          if args.n_resamples != ab.N_RESAMPLES else ""),
            "run_date": run_date, "n_resamples": args.n_resamples,
            "fingerprint": fingerprint, "seed": config.RANDOM_SEED,
            "library_versions": models.library_versions()}

    if args.split == "calibration":
        checks = rehearsal_checks(ev, full_budget=args.n_resamples == ab.N_RESAMPLES)
        meta["elapsed_s"] = round(time.time() - t0, 1)
        record = write_rehearsal(ev, checks, out_dir=args.out, meta=meta)
        print(f"\nrehearsal: {record['n_checks'] - record['n_failed']}/{record['n_checks']} "
              f"checks pass → {args.out}", flush=True)
        for name, c in checks.items():
            if not c["pass"]:
                print(f"  FAIL {name}: {c['detail']}", flush=True)
        return 0 if record["all_checks_pass"] else 1

    scores_path = P3 / "test_scores.csv.gz"
    scores.to_csv(scores_path, index=False, compression={"method": "gzip", "mtime": 0})
    meta["scores_sha256"] = hashlib.sha256(scores_path.read_bytes()).hexdigest()
    cal_shap = json.loads((P1 / "shap" / "shap_summary.json").read_text(encoding="utf-8"))
    comparison = compare_shap(cal_shap, ev["shap"])
    rep = replication_table(ev)
    meta["reliability_plots"] = write_reliability_plots(ev, P3 / "calibration")
    write_shap_outputs(ev, comparison, P3 / "shap")
    meta["elapsed_s"] = round(time.time() - t0, 1)
    (P3 / "model_report.json").write_text(json.dumps(
        {"provenance": meta, "replication": rep, "shap_comparison": comparison, **ev},
        indent=2, default=str), encoding="utf-8")
    write_replication_md(rep)
    write_model_report(ev, rep, comparison, meta=meta)
    print(f"\nwrote results/p3/model_report.{{md,json}}, replication_table.md, shap/, "
          f"calibration/, test_scores.csv.gz in {meta['elapsed_s']} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

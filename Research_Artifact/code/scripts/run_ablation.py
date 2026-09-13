"""P1-T6 — feature-family ablation + SHAP on the calibration split.

Per §A1.3/§A1.4 and **DL-019** (the configuration this script implements):

  * arms are fit with the **predeclared primary algorithm only** (XGBoost, §4);
  * the `control` and `full` arms are the **frozen P1-T5 XGBoost artifacts**,
    loaded and re-verified, never refitted;
  * six new arms `{d̂+F1}` … `{d̂+F6}` are trained by the **identical**
    procedure as P1-T5 (`scheduler_core.models.train_arm`/`calibrate`) — only
    the feature set differs;
  * a family is additionally fit as a **leave-one-out** arm (`{d̂+all−Fᵢ}`)
    iff its own `{d̂+Fᵢ}` arm clears the literal §A1.7 model-level floor
    (ΔPR-AUC ≥ 0.01 absolute, 95% CI excludes 0 in the positive direction) —
    this is a **compute trigger**, not the RQ2 admission verdict (P1-T7's);
  * paired incremental value vs `{d̂}` (families) / vs `{d̂+all}` (leave-one-out)
    uses a **build-level** paired bootstrap (`ablation_stats.paired_metric_delta`,
    B=1000, seed 42, 95% CI — DL-019 §3), not §10's replay-trace
    `paired_bootstrap`;
  * SHAP (`shap.TreeExplainer`) explains the frozen `full` arm's base model on
    the calibration design matrix; monotonicity and variance decomposition are
    computed from those SHAP values (DL-019 §4–6).

**The test split is never read** — dropped immediately after the split join,
exactly as in P1-T5.

Outputs
  * ``code/artifacts/models/xgboost__F{1..6}.joblib`` (+ any leave-one-out arm)
  * ``results/p1/ablation/deltas.json`` + ``ablation.md``  — the gate evidence
  * ``results/p1/shap/shap_summary.json`` + ``shap_summary.md`` + a bar chart

Run:  PYTHONPATH=. python scripts/run_ablation.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from scheduler_core import (ablation_stats as ab, config, data,
                            duration_estimator as de, features, models, splits)

CODE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = CODE_ROOT.parent / "results" / "p1"
ABLATION_DIR = RESULTS / "ablation"
SHAP_DIR = RESULTS / "shap"
ARTIFACTS = CODE_ROOT / "artifacts"
MODEL_DIR = ARTIFACTS / "models"
CKPT_DIR = ARTIFACTS / "checkpoints"
CHUNK = 300_000
COMMAND = "PYTHONPATH=. python scripts/run_ablation.py"
PRIMARY_ALGORITHM = models.PRIMARY_ALGORITHM        # "xgboost" (§4)

#: §A1.7's model-level floor, read here only as the leave-one-out trigger
#: (DL-019 §2) — the RQ2 admission verdict, with the ×0.5/×2 sweep, is P1-T7's.
MODEL_FLOOR_ABS = 0.01

#: §A1.9's declared project-identity-coded threshold (DL-019 §6).
PROJECT_CODED_SHARE = 0.8

FAMILY_IDS: tuple[str, ...] = tuple(features.FAMILIES.keys())          # F1..F6

READ_COLUMNS: tuple[str, ...] = tuple(
    c for c in data.EXPECTED_HEADER
    if c in set(features.READ_COLUMNS) | {"tr_duration"}
)


# --------------------------------------------------------------------------- #
# Data loading — identical to scripts/train_models.py (kept self-contained per
# that script's own convention; DL-019 requires the identical procedure, not a
# shared code path).
# --------------------------------------------------------------------------- #

def load_builds_with_duration(chunksize: int = CHUNK) -> pd.DataFrame:
    running: pd.DataFrame | None = None
    for chunk in data.read_chunks(chunksize=chunksize, usecols=READ_COLUMNS):
        chunk = chunk.assign(
            _dur=pd.to_numeric(chunk["tr_duration"], errors="coerce"))
        g = chunk.groupby("tr_build_id", sort=False)
        cols = [c for c in chunk.columns
                if c not in ("tr_build_id", "tr_duration", "_dur")]
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
    manifest = json.loads((RESULTS / "splits.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(RESULTS / "split_assignment.csv", dtype=str)
    assignment = dict(zip(frame["gh_project_name"], frame["split"]))
    digest = splits.assignment_hash(assignment)
    if digest != manifest["freeze"]["assignment_sha256"]:
        raise SystemExit("FATAL: split_assignment.csv does not match its frozen digest")
    return assignment, digest


# --------------------------------------------------------------------------- #
# Per-arm checkpointing — same discipline as scripts/train_models.py
# --------------------------------------------------------------------------- #

def run_fingerprint(*, seed: int, n_iter: int, d_hat_fit_id: str,
                    split_digest: str, n_train: int, n_calib: int,
                    arm_features: dict[str, tuple[str, ...]]) -> str:
    payload = json.dumps({
        "seed": seed, "n_iter": n_iter, "d_hat_fit_id": d_hat_fit_id,
        "split_digest": split_digest, "n_train": n_train, "n_calib": n_calib,
        "algorithm": PRIMARY_ALGORITHM,
        "arm_features": {k: list(v) for k, v in arm_features.items()},
        "library_versions": models.library_versions(),
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _checkpoint_path(tag: str) -> Path:
    return CKPT_DIR / f"{tag.replace(':', '__')}.json"


def save_checkpoint(tag: str, *, fingerprint: str, result: dict,
                    search_trace: list[dict]) -> None:
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    path = _checkpoint_path(tag)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({
        "fingerprint": fingerprint, "result": result, "search_trace": search_trace,
    }, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def load_checkpoint(tag: str, *, fingerprint: str) -> dict | None:
    path = _checkpoint_path(tag)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if blob.get("fingerprint") != fingerprint or not isinstance(blob.get("result"), dict):
        return None
    return blob


def resume_arm(tag: str, ckpt: dict, calib_frame: pd.DataFrame,
               y_calib: pd.Series) -> "models.TrainedArm | None":
    algorithm, arm = tag.split(":")
    path = MODEL_DIR / f"{algorithm}__{arm}.joblib"
    if not path.exists():
        return None
    try:
        trained = models.load_arm(path)
    except Exception as exc:                          # noqa: BLE001
        print(f"  checkpoint for {tag}: artifact will not load ({exc}) — refitting",
              flush=True)
        return None
    stored = ckpt["result"].get("calibrated", {})
    fresh = models.score_split(y_calib.to_numpy(),
                               trained.predict_proba(calib_frame), tau=trained.tau)
    for key in ("n", "positives", "pr_auc", "roc_auc", "brier", "ece", "tau"):
        if key not in stored or fresh[key] != stored[key]:
            print(f"  checkpoint for {tag} does not reproduce "
                  f"({key}: {fresh.get(key)!r} vs {stored.get(key)!r}) — refitting",
                  flush=True)
            return None
    return trained


def fit_and_calibrate(arm_name: str, train_frame, y_train, started_train,
                      calib_frame, y_calib, *, lang_levels, fingerprint: str,
                      n_iter: int, t0: float) -> tuple[models.TrainedArm, dict, bool]:
    """Fit-or-resume one arm, returning (trained, result_dict, was_resumed)."""
    tag = f"{PRIMARY_ALGORITHM}:{arm_name}"
    ckpt = load_checkpoint(tag, fingerprint=fingerprint)
    if ckpt is not None:
        reused = resume_arm(tag, ckpt, calib_frame, y_calib)
        if reused is not None:
            c = ckpt["result"]["calibrated"]
            print(f"[{time.time()-t0:6.0f}s] RESUMED {tag}: PR-AUC {c['pr_auc']:.6f} "
                  f"— reproduced exactly from checkpoint", flush=True)
            return reused, ckpt["result"], True

    print(f"\n[{time.time()-t0:6.0f}s] training {tag} "
          f"({len(models.ARMS[arm_name])} feature(s), {n_iter} candidates) …",
          flush=True)
    trained = models.train_arm(
        PRIMARY_ALGORITHM, arm_name, train_frame, y_train, started_train,
        lang_levels=lang_levels, seed=config.RANDOM_SEED, n_iter=n_iter, verbose=True)
    cal = models.calibrate(trained, calib_frame, y_calib, verbose=True)
    p_cal = trained.predict_proba(calib_frame)
    path = models.save_arm(trained, MODEL_DIR)
    reloaded = models.load_arm(path)
    round_trip = bool(np.array_equal(reloaded.predict_proba(calib_frame), p_cal))

    result = {
        "algorithm": PRIMARY_ALGORITHM, "arm": arm_name,
        "n_features": len(models.ARMS[arm_name]),
        "best_params": trained.best_params,
        "calibration_choice": cal,
        "calibrated": models.score_split(y_calib.to_numpy(), p_cal, tau=trained.tau),
        "artifact": str(path.relative_to(CODE_ROOT.parent)),
        "fit_id": trained.provenance["fit_id"],
        "round_trip": "PASS" if round_trip else "FAIL",
    }
    c = result["calibrated"]
    print(f"  {tag}: PR-AUC {c['pr_auc']:.6f} · ROC-AUC {c['roc_auc']:.6f} · "
          f"Brier {c['brier']:.6f} · round-trip {result['round_trip']}", flush=True)
    save_checkpoint(tag, fingerprint=fingerprint, result=result,
                    search_trace=trained.search_trace)
    return trained, result, False


def verify_frozen_arm(arm: str, calib_frame: pd.DataFrame, y_calib: pd.Series) -> models.TrainedArm:
    """Load a P1-T5 frozen XGBoost arm and re-verify it reproduces its stored metrics."""
    frozen = json.loads((RESULTS / "model_training.json").read_text(encoding="utf-8"))
    stored = frozen["arms"][f"{PRIMARY_ALGORITHM}:{arm}"]
    path = CODE_ROOT.parent / stored["artifact"]
    trained = models.load_arm(path)
    if trained.provenance["fit_id"] != stored["fit_id"]:
        raise SystemExit(f"FATAL: {arm} artifact fit_id does not match model_training.json")
    fresh = models.score_split(y_calib.to_numpy(), trained.predict_proba(calib_frame),
                               tau=trained.tau)
    for key in ("n", "positives", "pr_auc", "roc_auc", "brier", "ece", "tau"):
        if fresh[key] != stored["calibrated"][key]:
            raise SystemExit(
                f"FATAL: frozen {arm} arm does not reproduce ({key}: "
                f"{fresh[key]!r} vs {stored['calibrated'][key]!r}) — refitting "
                "it here would silently move the P1-T5 null (DL-019 §1)")
    print(f"verified frozen {PRIMARY_ALGORITHM}:{arm} reproduces its P1-T5 metrics "
          f"exactly (fit id {trained.provenance['fit_id']})", flush=True)
    return trained


# --------------------------------------------------------------------------- #
# SHAP
# --------------------------------------------------------------------------- #

def feature_to_family() -> dict[str, str]:
    out: dict[str, str] = {}
    for fam, members in features.FAMILIES.items():
        for f in members:
            out[f] = fam
    return out


def design_column_family(column: str, mapping: dict[str, str]) -> str:
    if column == models.D_HAT_COLUMN:
        return "control"
    if column in mapping:
        return mapping[column]
    if column.startswith("lang="):                     # one-hot dummy of `lang`
        return mapping["lang"]
    raise KeyError(f"design column {column!r} maps to no known feature/family")


def compute_shap(full_arm: models.TrainedArm, calib_frame: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    import shap

    x = models.design_matrix(calib_frame, full_arm.arm,
                             lang_levels=full_arm.lang_levels)[list(full_arm.design_columns)]
    explainer = shap.TreeExplainer(full_arm.base_model)
    raw = explainer.shap_values(x)
    values = np.asarray(raw[1] if isinstance(raw, list) else raw, dtype="float64")
    return values, x


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-iter", type=int, default=models.SEARCH_N_ITER,
                    help="debug only: override the DL-018 search budget")
    ap.add_argument("--fresh", action="store_true",
                    help="discard every ablation checkpoint and refit from scratch")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.time()
    run_date = time.strftime("%Y-%m-%d")
    for d in (RESULTS, ABLATION_DIR, SHAP_DIR, MODEL_DIR, CKPT_DIR):
        d.mkdir(parents=True, exist_ok=True)

    print(f"reading {data.DEFAULT_DATASET_PATH} …", flush=True)
    builds = load_builds_with_duration()
    print(f"  analytic builds: {len(builds):,} across "
          f"{builds['gh_project_name'].nunique():,} projects ({time.time()-t0:.0f}s)",
          flush=True)

    assignment, split_digest = load_frozen_assignment()
    split_of = builds["gh_project_name"].map(assignment)
    if split_of.isna().any():
        raise SystemExit("FATAL: a build's project is absent from the frozen split")

    is_test = (split_of == "test").to_numpy()
    n_test_builds, n_test_projects = int(is_test.sum()), int(
        builds.loc[is_test, "gh_project_name"].nunique())
    builds = builds.loc[~is_test].reset_index(drop=True)
    split_of = split_of.loc[~is_test].reset_index(drop=True)
    assert not (split_of == "test").any()
    print(f"  test split closed: {n_test_builds:,} builds / {n_test_projects:,} "
          "projects dropped unread", flush=True)

    durations = pd.Series(
        pd.to_numeric(builds["tr_duration"], errors="coerce").to_numpy(), index=builds.index)
    matrix = features.build_feature_matrix(builds)
    y = features.label_from_status(builds)
    if y.isna().any():
        raise SystemExit("FATAL: the analytic set produced an unlabelled build")
    y = y.astype("int64")

    frozen = json.loads((RESULTS / "duration_control.json").read_text(encoding="utf-8"))
    expected_fit_id = frozen["provenance"]["fit_id"]
    estimator = de.DurationEstimator.load(ARTIFACTS / "duration_estimator.joblib")
    keys = builds[list(features.KEY_COLUMNS)]
    d_hat = models.attach_d_hat(matrix, keys, durations, estimator=estimator,
                                expected_fit_id=expected_fit_id)
    matrix[models.D_HAT_COLUMN] = d_hat.to_numpy()
    features.assert_no_leakage(columns=matrix.columns)

    is_train = (split_of == "train").to_numpy()
    is_calib = (split_of == "calibration").to_numpy()
    train_frame, calib_frame = matrix.loc[is_train], matrix.loc[is_calib]
    y_train, y_calib = y.loc[is_train], y.loc[is_calib]
    started_train = builds.loc[is_train, "gh_build_started_at"]
    calib_projects = builds.loc[is_calib, "gh_project_name"]
    lang_levels = estimator.lang_levels

    print(f"  train {len(train_frame):,} builds ({100*y_train.mean():.3f}% failure) "
          f"· calibration {len(calib_frame):,} builds ({100*y_calib.mean():.3f}% failure)",
          flush=True)

    # --- verify the frozen P1-T5 control/full arms (loaded, never refit) ---- #
    control_arm = verify_frozen_arm("control", calib_frame, y_calib)
    full_arm = verify_frozen_arm("full", calib_frame, y_calib)
    p_control = control_arm.predict_proba(calib_frame)
    p_full = full_arm.predict_proba(calib_frame)

    # --- register the six family arms on the shared machinery (DL-019 §1) -- #
    family_features = {fam: (models.D_HAT_COLUMN,) + tuple(features.FAMILIES[fam])
                       for fam in FAMILY_IDS}
    for fam, feats in family_features.items():
        models.ARMS[fam] = feats

    fingerprint = run_fingerprint(
        seed=config.RANDOM_SEED, n_iter=args.n_iter, d_hat_fit_id=expected_fit_id,
        split_digest=split_digest, n_train=len(train_frame), n_calib=len(calib_frame),
        arm_features=family_features)
    if args.fresh:
        for stale in sorted(CKPT_DIR.glob(f"{PRIMARY_ALGORITHM}__{{{','.join(FAMILY_IDS)}}}*")):
            stale.unlink()
    print(f"\nrun fingerprint {fingerprint}", flush=True)

    family_results: dict[str, dict] = {}
    family_arms: dict[str, models.TrainedArm] = {}
    deltas: dict[str, dict] = {}
    triggered: list[str] = []

    for fam in FAMILY_IDS:
        trained, result, _resumed = fit_and_calibrate(
            fam, train_frame, y_train, started_train, calib_frame, y_calib,
            lang_levels=lang_levels, fingerprint=fingerprint, n_iter=args.n_iter, t0=t0)
        family_arms[fam] = trained
        family_results[fam] = result
        p_fam = trained.predict_proba(calib_frame)
        delta = ab.paired_metric_delta(y_calib.to_numpy(), p_control, p_fam)
        deltas[fam] = delta
        d_pr = delta["pr_auc"]
        trigger = bool(d_pr["delta"] >= MODEL_FLOOR_ABS and d_pr["ci_lo"] > 0)
        deltas[fam]["loo_triggered"] = trigger
        if trigger:
            triggered.append(fam)
        print(f"  {fam} vs control: ΔPR-AUC {d_pr['delta']:+.6f} "
              f"[{d_pr['ci_lo']:+.6f}, {d_pr['ci_hi']:+.6f}] "
              f"— floor trigger: {trigger}", flush=True)

    # --- leave-one-family-out arms, only for triggered families (DL-019 §2) - #
    loo_results: dict[str, dict] = {}
    loo_deltas: dict[str, dict] = {}
    for fam in triggered:
        loo_name = f"full_minus_{fam}"
        loo_feats = (models.D_HAT_COLUMN,) + tuple(
            f for f in features.FEATURES if f not in features.FAMILIES[fam])
        models.ARMS[loo_name] = loo_feats
        trained, result, _resumed = fit_and_calibrate(
            loo_name, train_frame, y_train, started_train, calib_frame, y_calib,
            lang_levels=lang_levels, fingerprint=fingerprint, n_iter=args.n_iter, t0=t0)
        loo_results[fam] = result
        p_loo = trained.predict_proba(calib_frame)
        loo_deltas[fam] = ab.paired_metric_delta(y_calib.to_numpy(), p_loo, p_full)

    # --- SHAP on the frozen full arm (calibration split) -------------------- #
    print(f"\n[{time.time()-t0:6.0f}s] computing SHAP on the frozen full arm "
          f"({len(calib_frame):,} calibration builds) …", flush=True)
    shap_values, design_x = compute_shap(full_arm, calib_frame)
    f2fam = feature_to_family()
    col_family = {c: design_column_family(c, f2fam) for c in design_x.columns}

    per_feature: dict[str, dict] = {}
    for i, col in enumerate(design_x.columns):
        vals = shap_values[:, i]
        raw = design_x[col].to_numpy()
        mono = ab.spearman_with_ci(raw, vals)
        per_feature[col] = {
            "family": col_family[col],
            "mean_abs_shap": float(np.mean(np.abs(vals))),
            "mean_signed_shap": float(np.mean(vals)),
            "monotonicity": mono,
        }

    fam_contribution: dict[str, np.ndarray] = {}
    for fam in ("control",) + FAMILY_IDS:
        cols = [c for c, f in col_family.items() if f == fam]
        fam_contribution[fam] = (shap_values[:, [design_x.columns.get_loc(c) for c in cols]]
                                 .sum(axis=1) if cols else np.zeros(len(design_x)))

    per_family_shap: dict[str, dict] = {}
    for fam, contrib in fam_contribution.items():
        per_family_shap[fam] = {
            "mean_abs_contribution": float(np.mean(np.abs(contrib))),
            "mean_signed_contribution": float(np.mean(contrib)),
        }

    # --- variance decomposition (§A1.9, DL-019 §6) --------------------------- #
    variance: dict[str, dict] = {}
    for fam, contrib in fam_contribution.items():
        vd = ab.variance_decomposition(contrib, calib_projects.to_numpy())
        vd["project_identity_coded"] = bool(vd["between_share"] >= PROJECT_CODED_SHARE)
        variance[fam] = vd

    elapsed = round(time.time() - t0, 1)
    print(f"\ndone in {elapsed}s", flush=True)

    write_outputs(
        run_date=run_date, elapsed=elapsed, n_iter=args.n_iter,
        train_frame=train_frame, calib_frame=calib_frame, y_train=y_train, y_calib=y_calib,
        n_test_builds=n_test_builds, n_test_projects=n_test_projects,
        control_arm=control_arm, full_arm=full_arm,
        family_results=family_results, deltas=deltas, triggered=triggered,
        loo_results=loo_results, loo_deltas=loo_deltas,
        per_feature=per_feature, per_family_shap=per_family_shap, variance=variance,
        expected_fit_id=expected_fit_id, split_digest=split_digest,
    )
    return 0


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #

def write_outputs(*, run_date, elapsed, n_iter, train_frame, calib_frame, y_train, y_calib,
                  n_test_builds, n_test_projects, control_arm, full_arm,
                  family_results, deltas, triggered, loo_results, loo_deltas,
                  per_feature, per_family_shap, variance, expected_fit_id, split_digest) -> None:
    provenance = {
        "command": COMMAND, "run_date": run_date, "seed": config.RANDOM_SEED,
        "n_iter": n_iter, "elapsed_s": elapsed,
        "algorithm": PRIMARY_ALGORITHM,
        "protocol": "eval_protocol §A1.3 (families), §A1.4 (model-level incremental "
                    "value), §A1.7 (model floor, used here only as the leave-one-out "
                    "trigger), §A1.8 (monotonicity), §A1.9 (variance decomposition); "
                    "config DL-019",
        "duration_control_fit_id": expected_fit_id,
        "split_digest": split_digest,
        "control_arm_fit_id": control_arm.provenance["fit_id"],
        "full_arm_fit_id": full_arm.provenance["fit_id"],
        "population": {
            "train_builds": int(len(train_frame)), "train_failure_rate_pct":
                round(100 * float(y_train.mean()), 4),
            "calibration_builds": int(len(calib_frame)), "calibration_failure_rate_pct":
                round(100 * float(y_calib.mean()), 4),
            "test_builds_dropped_unread": n_test_builds,
            "test_projects_dropped_unread": n_test_projects,
        },
    }

    deltas_out = {
        "provenance": provenance,
        "families": {
            fam: {
                "n_features": len(features.FAMILIES[fam]),
                "members": list(features.FAMILIES[fam]),
                "arm_result": family_results[fam],
                "delta_vs_control": deltas[fam],
                "loo_triggered": deltas[fam]["loo_triggered"],
            } for fam in FAMILY_IDS
        },
        "leave_one_out": {
            fam: {
                "arm_result": loo_results[fam],
                "delta_full_vs_loo": loo_deltas[fam],
                "interpretation": "delta_full_vs_loo is full's metric minus "
                    f"full-minus-{fam}'s; a delta near 0 means {fam} is "
                    "redundant with the remaining families inside `full`.",
            } for fam in triggered
        },
        "families_triggering_leave_one_out": triggered,
        "model_floor_used_as_trigger": {
            "rule": "ΔPR-AUC point estimate >= 0.01 absolute AND its 95% CI "
                    "excludes 0 in the positive direction (literal §A1.7 model "
                    "floor) — DL-019 §2. NOT the RQ2 admission verdict.",
            "abs_floor": MODEL_FLOOR_ABS,
        },
    }
    (ABLATION_DIR / "deltas.json").write_text(
        json.dumps(deltas_out, indent=2, default=str), encoding="utf-8")

    shap_out = {
        "provenance": provenance,
        "per_feature": per_feature,
        "per_family": per_family_shap,
        "variance_decomposition": variance,
        "project_identity_coded_threshold": PROJECT_CODED_SHARE,
    }
    (SHAP_DIR / "shap_summary.json").write_text(
        json.dumps(shap_out, indent=2, default=str), encoding="utf-8")

    write_shap_plot(per_family_shap)
    write_ablation_report(deltas_out)
    write_shap_report(shap_out)


def write_shap_plot(per_family_shap: dict[str, dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = ["control"] + list(FAMILY_IDS)
    mags = [per_family_shap[k]["mean_abs_contribution"] for k in order]
    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=150)
    colors = ["#7f7f7f"] + ["#1f77b4"] * len(FAMILY_IDS)
    ax.barh(order, mags, color=colors)
    ax.set_xlabel("mean |Σ SHAP| — full arm, calibration split")
    ax.set_title("Per-family SHAP magnitude inside the full XGBoost arm", fontsize=9)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3, lw=0.5)
    fig.tight_layout()
    fig.savefig(SHAP_DIR / "family_importance.png")
    plt.close(fig)


def write_ablation_report(out: dict) -> None:
    p, pop = out["provenance"], out["provenance"]["population"]
    L: list[str] = []
    A = L.append
    A("# Feature-family ablation — calibration split (P1-T6)\n")
    A(f"> Generated by `{p['command']}` on {p['run_date']}. Every number below "
      f"comes from that run (R1). Seed `{p['seed']}` · elapsed {p['elapsed_s']}s.\n")
    A(f"> Protocol: {p['protocol']}.\n")

    A("\n## 1. Population and frozen arms\n")
    A(f"- Train: {pop['train_builds']:,} builds ({pop['train_failure_rate_pct']}% "
      f"failure). Calibration: {pop['calibration_builds']:,} builds "
      f"({pop['calibration_failure_rate_pct']}% failure). **Test split closed:** "
      f"{pop['test_projects_dropped_unread']:,} projects / "
      f"{pop['test_builds_dropped_unread']:,} builds dropped unread.")
    A(f"- `control` (`{{d̂}}`) and `full` (`{{d̂+all}}`) are the **frozen P1-T5 "
      f"XGBoost arms**, loaded and re-verified to reproduce their P1-T5 "
      f"calibration-split metrics exactly (fit ids `{p['control_arm_fit_id']}` / "
      f"`{p['full_arm_fit_id']}`) — **not refitted** (DL-019 §1).")

    A("\n## 2. Per-family incremental value vs `{d̂}` (paired bootstrap, B=1000, "
      "seed 42)\n")
    A("§A1.4's comparison, computed here on the **calibration** split "
      "(`development_plan.md` P1-T6/P1-T7 — see DL-019 §Threats 4 on the stale "
      "test-split wording in `eval_protocol.md` §A1.4). Every delta is "
      "treatment (`{d̂+Fᵢ}`) minus control (`{d̂}`), paired over the shared "
      "calibration build index.\n")
    A("| family | members | ΔPR-AUC | 95% CI | ΔROC-AUC | ΔBrier | ΔECE | "
      "clears §A1.7 floor (trigger only) |")
    A("| :-- | --: | --: | :-- | --: | --: | --: | :-: |")
    for fam, row in out["families"].items():
        d = row["delta_vs_control"]
        pr, roc, br, ec = d["pr_auc"], d["roc_auc"], d["brier"], d["ece"]
        A(f"| **{fam}** | {row['n_features']} | {pr['delta']:+.6f} | "
          f"[{pr['ci_lo']:+.6f}, {pr['ci_hi']:+.6f}] | {roc['delta']:+.6f} | "
          f"{br['delta']:+.6f} | {ec['delta']:+.6f} | "
          f"{'**yes**' if row['loo_triggered'] else 'no'} |")
    A("")
    if out["families_triggering_leave_one_out"]:
        A(f"**{len(out['families_triggering_leave_one_out'])} family(ies) "
          f"triggered a leave-one-out arm:** "
          + ", ".join(f"`{f}`" for f in out["families_triggering_leave_one_out"]) + ".\n")
    else:
        A("**No family clears the §A1.7 model-level floor on its own arm.** No "
          "leave-one-out arm was fit. This is consistent with P1-T5's finding "
          "that `full` (all 28 features together) did not beat `control` for "
          "any algorithm — DL-019 predeclared this as a valid, reportable "
          "outcome, not a shortfall. **This is not the RQ2 verdict** — P1-T7 "
          "applies the full §A1.7 rule with its ×0.5/×2 sweep.\n")

    A("\n## 3. Leave-one-family-out arms (redundancy check)\n")
    if out["leave_one_out"]:
        A("`Δ full_vs_loo` is `full`'s metric minus `full-minus-Fᵢ`'s — near "
          "zero means the family's information is redundant with the rest of "
          "`full`.\n")
        A("| family removed | ΔPR-AUC (full − loo) | 95% CI |")
        A("| :-- | --: | :-- |")
        for fam, row in out["leave_one_out"].items():
            d = row["delta_full_vs_loo"]["pr_auc"]
            A(f"| `{fam}` | {d['delta']:+.6f} | [{d['ci_lo']:+.6f}, {d['ci_hi']:+.6f}] |")
        A("")
    else:
        A("Not applicable — no family triggered a leave-one-out arm.\n")

    A("\n## 4. Methodological notes\n")
    A("1. **This report's family-clears-the-floor column is a compute trigger, "
      "not an admission verdict** (DL-019 §2). P1-T7 applies §A1.7's rule with "
      "its ×0.5/×2 sensitivity sweep and 'no discretion, no post-hoc "
      "adjustment' — it may admit a different set than this column shows, "
      "though only in the direction the sweep's stricter floor allows (no "
      "family this task fits a leave-one-out arm for can be missing from "
      "P1-T7's consideration).")
    A("2. **The paired bootstrap here is a build-level function "
      "(`ablation_stats.paired_metric_delta`), distinct from `eval_protocol.md` "
      "§10's `paired_bootstrap`**, which pairs *strategies* over a P3 replay "
      "trace. Both share §9's B=1000/seed 42/95% CI conventions (DL-019 §3).")
    A("3. **`eval_protocol.md` §A1.4 says this comparison is computed at "
      "'P1-T7, on the test split'; `development_plan.md`'s post-DL-012 28-task "
      "breakdown scopes P1-T6 and P1-T7 to the calibration split**, with the "
      "confirmatory test-split ablation at P3-T1. This is the same class of "
      "stale task-numbering artifact flagged at P1-T5 (DL-019 §Threats 4); "
      "`development_plan.md` governs, and the test split stayed closed "
      "throughout this run.")
    A("4. **F2 carries only 4 informative members**, not 6 (DL-016): "
      "`test_density_ratio` is constant (division by an empty "
      "`git_diff_test_churn`), and the family's own ablation result must be "
      "read as a weakened lower bound for that reason.")
    A("5. Every family arm inherits the P1-T5 threats unchanged: the search "
      "budget (20 candidates), the in-sample calibrator-choice optimism, and "
      "`d̂` being a predicted (not oracle) quantity.\n")

    A("\n## 5. Provenance footer\n")
    A("- Split: frozen P1-T3 assignment, digest re-verified at load.")
    A(f"- **Test split untouched:** {pop['test_projects_dropped_unread']:,} "
      f"projects / {pop['test_builds_dropped_unread']:,} builds dropped before "
      "any arm existed, and never read.")
    A(f"- `control`/`full`: loaded from the frozen P1-T5 artifacts, not "
      "refitted, re-verified to reproduce their stored metrics exactly.")
    A(f"- Family + leave-one-out arms: `code/artifacts/models/"
      f"{PRIMARY_ALGORITHM}__F*.joblib`.")
    A("")
    (ABLATION_DIR / "ablation.md").write_text("\n".join(L), encoding="utf-8")


def write_shap_report(out: dict) -> None:
    p = out["provenance"]
    L: list[str] = []
    A = L.append
    A("# SHAP attribution — frozen full XGBoost arm, calibration split (P1-T6)\n")
    A(f"> Generated by `{p['command']}` on {p['run_date']}. Every number below "
      f"comes from that run (R1).\n")
    A(f"> `shap.TreeExplainer` on the **frozen `full` arm's base model** "
      f"(fit id `{p['full_arm_fit_id']}`), over the calibration design matrix "
      "(DL-019 §4). Calibration is a post-hoc monotone map and is not part of "
      "the explained model.\n")

    A("\n## 1. Per-family SHAP magnitude and direction\n")
    A("`control` is the `d̂` column, reported separately — it is not a family.\n")
    A("| family | mean |Σ SHAP| per build | mean signed Σ SHAP | between-project "
      "share | project-identity-coded? |")
    A("| :-- | --: | --: | --: | :-: |")
    for fam in ("control",) + FAMILY_IDS:
        pf = out["per_family"][fam]
        vd = out["variance_decomposition"][fam]
        A(f"| `{fam}` | {pf['mean_abs_contribution']:.6f} | "
          f"{pf['mean_signed_contribution']:+.6f} | "
          f"{vd['between_share']:.4f} | "
          f"{'**yes**' if vd['project_identity_coded'] else 'no'} |")
    A(f"\n> Project-identity-coded threshold: between-project share ≥ "
      f"{out['project_identity_coded_threshold']} of total variance (DL-019 §6, "
      "declared before this run).\n")

    A("\n## 2. Per-feature SHAP magnitude, direction and monotonicity (§A1.8)\n")
    A("`monotone` is true iff the feature-value/SHAP-value Spearman "
      "correlation's 95% bootstrap CI excludes 0 — a necessary, not "
      "sufficient, condition for using the feature as a simple window knob.\n")
    A("| feature | family | mean |SHAP| | mean signed SHAP | Spearman ρ | "
      "95% CI | monotone? |")
    A("| :-- | :-- | --: | --: | --: | :-- | :-: |")
    for col, r in sorted(out["per_feature"].items(),
                         key=lambda kv: -kv[1]["mean_abs_shap"]):
        m = r["monotonicity"]
        ci = "degenerate" if m.get("degenerate") else f"[{m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}]"
        rho = "—" if m.get("degenerate") else f"{m['rho']:+.4f}"
        A(f"| `{col}` | {r['family']} | {r['mean_abs_shap']:.6f} | "
          f"{r['mean_signed_shap']:+.6f} | {rho} | {ci} | "
          f"{'**yes**' if m['monotone'] else 'no'} |")
    A("")

    A("\n## 3. Notes\n")
    A("1. SHAP explains the `full` arm's per-feature contribution **inside a "
      "model with every family present**; a family's own standalone "
      "`{d̂+Fᵢ}` incremental-value number (`results/p1/ablation/deltas.json`) "
      "can disagree with its SHAP magnitude here, because other families can "
      "absorb or mask its signal inside `full` (DL-019 §Threats 2) — the two "
      "are complementary diagnostics, not restatements of each other.")
    A("2. `d̂`'s own SHAP magnitude and monotonicity are reported as `control` "
      "so its role as the incumbent window knob (§A1.6/§A1.8) can be read "
      "directly against the SE families.")
    A(f"3. `family_importance.png` in this directory is the same table's "
      "magnitude column as a bar chart.\n")
    (SHAP_DIR / "shap_summary.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

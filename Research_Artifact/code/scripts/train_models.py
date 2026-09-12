"""P1-T5 — train, tune and calibrate the control and SE arms.

One pass over the backbone CSV builds the analytic set, joins the **frozen**
P1-T3 split, attaches `d̂` from the **frozen** P1-T4 duration control, and then,
for each of the three algorithms (§4) × two arms (§A1.3):

  * tunes inside the **train** split only — temporally-latest 20% internal
    validation fold, PR-AUC selection, seeded random search (§3, DL-018);
  * refits the winner on 100% of train;
  * fits **both** isotonic and Platt on the **calibration** split and keeps the
    lower calibration-split Brier (§5, DL-004);
  * freezes τ, the F1-maximising threshold on the calibrated probability (§5);
  * records a project-grouped out-of-fold calibration diagnostic, because §5's
    own selection is in-sample for the calibrator.

**The test split is never read.** Test rows are dropped the moment the split is
joined and every later stage asserts their absence.

Outputs
  * ``code/artifacts/models/<algorithm>__<arm>.joblib``  — persisted arms
  * ``results/p1/model_training.md``                     — the gate report
  * ``results/p1/model_training.json``                   — machine-readable
  * ``results/p1/model_search_trace.json``               — every candidate
  * ``results/p1/calibration/``                          — Brier/ECE table +
    reliability diagrams (the gate evidence)

Run:  PYTHONPATH=. python scripts/train_models.py
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

from scheduler_core import (config, data, duration_estimator as de, features,
                            models, splits)

CODE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = CODE_ROOT.parent / "results" / "p1"
CALIB_DIR = RESULTS / "calibration"
ARTIFACTS = CODE_ROOT / "artifacts"
MODEL_DIR = ARTIFACTS / "models"
CKPT_DIR = ARTIFACTS / "checkpoints"
CHUNK = 300_000
COMMAND = "PYTHONPATH=. python scripts/train_models.py"

READ_COLUMNS: tuple[str, ...] = tuple(
    c for c in data.EXPECTED_HEADER
    if c in set(features.READ_COLUMNS) | {"tr_duration"}
)


def load_builds_with_duration(chunksize: int = CHUNK) -> pd.DataFrame:
    """Build-grain analytic set with feature sources and `tr_duration` (DL-009).

    Duration is needed for two admissible purposes only: `d̂`'s causal project
    history (§A1.2 role 2) and nothing else in this task. It is never joined
    onto a feature frame.
    """
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
# Per-arm checkpointing
# --------------------------------------------------------------------------- #
#
# Every arm draws its search candidates from a generator seeded *inside*
# ``models.train_arm`` (``np.random.default_rng(seed)``), so no random state
# crosses from one arm to the next. Skipping an already-fitted arm therefore
# leaves every remaining arm bit-for-bit identical to a cold run: resuming is a
# compute optimisation and never a change of result. Nothing here alters a
# search space, a seed, or a metric.
#
# A checkpoint is reused only if two conditions both hold:
#   1. the fingerprint below still matches — the whole configuration the arm was
#      fitted under, so a changed seed/budget/split/`d̂`/library set refits; and
#   2. the persisted model still *reproduces* the metrics stored beside it, which
#      is the same round-trip guarantee the cold path asserts.
# Anything else is discarded and refitted. A checkpoint can only ever save time.


def run_fingerprint(*, seed: int, n_iter: int, d_hat_fit_id: str,
                    split_digest: str, sample_projects: int,
                    n_train: int, n_calib: int) -> str:
    """Identity of the configuration an arm was fitted under."""
    payload = json.dumps({
        "seed": seed,
        "n_iter": n_iter,
        "d_hat_fit_id": d_hat_fit_id,
        "split_digest": split_digest,
        "sample_projects": sample_projects,
        "n_train": n_train,
        "n_calib": n_calib,
        "arms": {k: list(v) for k, v in models.ARMS.items()},
        "algorithms": list(models.ALGORITHMS),
        "library_versions": models.library_versions(),
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _checkpoint_path(tag: str) -> Path:
    return CKPT_DIR / f"{tag.replace(':', '__')}.json"


def save_checkpoint(tag: str, *, fingerprint: str, result: dict,
                    search_trace: list[dict]) -> None:
    """Persist one finished arm. Written via a temp file so a kill mid-write
    cannot leave a half-parsed checkpoint behind."""
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    path = _checkpoint_path(tag)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({
        "fingerprint": fingerprint,
        "result": result,
        "search_trace": search_trace,
    }, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def load_checkpoint(tag: str, *, fingerprint: str) -> dict | None:
    """A checkpoint for ``tag`` that was written under ``fingerprint``, else None."""
    path = _checkpoint_path(tag)
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None                     # truncated or unreadable — refit
    if blob.get("fingerprint") != fingerprint:
        return None                     # configuration moved — refit
    if not isinstance(blob.get("result"), dict):
        return None
    return blob


def resume_arm(tag: str, ckpt: dict, calib_frame: pd.DataFrame,
               y_calib: pd.Series) -> "models.TrainedArm | None":
    """Re-verify a checkpoint against its persisted model, or refuse it.

    The stored calibration-split metrics are recomputed from the reloaded
    artifact and must match exactly. A resumed arm is therefore held to the same
    standard as a freshly fitted one rather than taken on faith; any mismatch
    (missing artifact, moved data, non-reproducing model) returns None and the
    arm is refitted from scratch.
    """
    algorithm, arm = tag.split(":")
    path = MODEL_DIR / f"{algorithm}__{arm}.joblib"
    if not path.exists():
        return None
    try:
        trained = models.load_arm(path)
    except Exception as exc:                          # noqa: BLE001 — refit on any fault
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


def reliability_plot(bins: pd.DataFrame, title: str, path: Path) -> None:
    """10-bin reliability diagram (§5), saved as gate evidence."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.6, 4.6), dpi=150)
    ax.plot([0, 1], [0, 1], "--", color="0.6", lw=1, label="perfect calibration")
    ok = bins["n"] > 0
    ax.plot(bins.loc[ok, "confidence"], bins.loc[ok, "observed"], "o-",
            color="#1f77b4", lw=1.6, ms=5, label="observed")
    for _, r in bins.loc[ok].iterrows():
        ax.annotate(f"{int(r['n']):,}", (r["confidence"], r["observed"]),
                    textcoords="offset points", xytext=(4, -9), fontsize=6,
                    color="0.4")
    ax.set_xlabel("mean predicted probability (bin confidence)")
    ax.set_ylabel("observed failure frequency")
    ax.set_title(title, fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.25, lw=0.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-projects", type=int, default=0,
                    help="debug only: restrict train to N projects (never used "
                         "for a reported number)")
    ap.add_argument("--n-iter", type=int, default=models.SEARCH_N_ITER,
                    help="debug only: override the DL-018 search budget")
    ap.add_argument("--report-only", action="store_true",
                    help="re-render the report from model_training.json")
    ap.add_argument("--fresh", action="store_true",
                    help="discard every per-arm checkpoint and refit all arms "
                         "from scratch (the default already refits any arm whose "
                         "configuration or artifact no longer matches)")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if args.report_only:
        out = json.loads(
            (RESULTS / "model_training.json").read_text(encoding="utf-8"))
        write_report(out)
        print("re-rendered results/p1/model_training.md — no number recomputed")
        return 0

    t0 = time.time()
    run_date = time.strftime("%Y-%m-%d")
    for d in (RESULTS, CALIB_DIR, MODEL_DIR, CKPT_DIR):
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
    n_test_builds = int(is_test.sum())
    n_test_projects = int(builds.loc[is_test, "gh_project_name"].nunique())
    builds = builds.loc[~is_test].reset_index(drop=True)
    split_of = split_of.loc[~is_test].reset_index(drop=True)
    assert not (split_of == "test").any()
    print(f"  test split closed: {n_test_builds:,} builds / {n_test_projects:,} "
          "projects dropped unread", flush=True)

    if args.sample_projects:
        keep = sorted(builds.loc[(split_of == "train").to_numpy(),
                                 "gh_project_name"].unique())[:args.sample_projects]
        mask = (builds["gh_project_name"].isin(keep) |
                (split_of == "calibration")).to_numpy()
        builds = builds.loc[mask].reset_index(drop=True)
        split_of = split_of.loc[mask].reset_index(drop=True)
        print(f"  DEBUG SAMPLE: {len(builds):,} builds", flush=True)

    durations = pd.Series(
        pd.to_numeric(builds["tr_duration"], errors="coerce").to_numpy(),
        index=builds.index)
    matrix = features.build_feature_matrix(builds)        # asserts no leakage
    y = features.label_from_status(builds)
    if y.isna().any():
        raise SystemExit("FATAL: the analytic set produced an unlabelled build")
    y = y.astype("int64")

    # --- d̂ from the frozen P1-T4 control -------------------------------------- #
    frozen = json.loads((RESULTS / "duration_control.json").read_text(encoding="utf-8"))
    expected_fit_id = frozen["provenance"]["fit_id"]
    estimator = de.DurationEstimator.load(ARTIFACTS / "duration_estimator.joblib")
    print(f"\nattaching d̂ from the frozen control (fit id {expected_fit_id}, "
          f"primary form {estimator.primary_form}) …", flush=True)

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

    print(f"  train {len(train_frame):,} builds "
          f"({100*y_train.mean():.3f}% failure) · calibration "
          f"{len(calib_frame):,} builds ({100*y_calib.mean():.3f}% failure)",
          flush=True)

    # --- train × calibrate every (algorithm, arm) ---------------------------- #
    fingerprint = run_fingerprint(
        seed=config.RANDOM_SEED, n_iter=args.n_iter,
        d_hat_fit_id=expected_fit_id, split_digest=split_digest,
        sample_projects=args.sample_projects,
        n_train=len(train_frame), n_calib=len(calib_frame))
    if args.fresh and CKPT_DIR.exists():
        for stale in sorted(CKPT_DIR.glob("*.json*")):
            stale.unlink()
        print(f"\n--fresh: cleared every per-arm checkpoint under "
              f"{CKPT_DIR.relative_to(CODE_ROOT.parent)}", flush=True)
    print(f"\nrun fingerprint {fingerprint} · per-arm checkpoints under "
          f"{CKPT_DIR.relative_to(CODE_ROOT.parent)}", flush=True)

    arms: dict[str, models.TrainedArm] = {}
    results: dict[str, dict] = {}
    trace: list[dict] = []
    resumed: list[str] = []

    for arm in models.ARMS:
        for algorithm in models.ALGORITHMS:
            tag = f"{algorithm}:{arm}"
            ckpt = load_checkpoint(tag, fingerprint=fingerprint)
            if ckpt is not None:
                print(f"\n[{time.time()-t0:6.0f}s] {tag}: checkpoint found — "
                      "verifying it against its persisted model …", flush=True)
                reused = resume_arm(tag, ckpt, calib_frame, y_calib)
                if reused is not None:
                    results[tag] = ckpt["result"]
                    trace.extend(ckpt["search_trace"])
                    arms[tag] = reused
                    resumed.append(tag)
                    # Re-render the gate evidence from the stored bins, so the
                    # diagram exists even though this segment never fitted the arm.
                    reliability_plot(
                        pd.DataFrame(ckpt["result"]["reliability_bins"]),
                        f"{tag} · {reused.calibrator_kind} · calibration split",
                        CALIB_DIR / f"reliability_{algorithm}__{arm}.png")
                    c = results[tag]["calibrated"]
                    print(f"  RESUMED {tag}: PR-AUC {c['pr_auc']:.6f} · Brier "
                          f"{c['brier']:.6f} — reproduced exactly from "
                          f"{_checkpoint_path(tag).name}", flush=True)
                    continue
            t_arm = time.time()
            print(f"\n[{time.time()-t0:6.0f}s] training {tag} "
                  f"({len(models.ARMS[arm])} feature(s), {args.n_iter} candidates) …",
                  flush=True)
            trained = models.train_arm(
                algorithm, arm, train_frame, y_train, started_train,
                lang_levels=lang_levels, seed=config.RANDOM_SEED,
                n_iter=args.n_iter, verbose=True)
            print(f"  calibrating {tag} on {len(calib_frame):,} calibration builds …",
                  flush=True)
            cal = models.calibrate(trained, calib_frame, y_calib, verbose=True)

            p_cal = trained.predict_proba(calib_frame)
            p_raw = trained.predict_proba_uncalibrated(calib_frame)
            oof = models.out_of_fold_calibration(trained, calib_frame, y_calib,
                                                 calib_projects)
            bins = models.reliability_bins(y_calib.to_numpy(), p_cal)
            png = CALIB_DIR / f"reliability_{algorithm}__{arm}.png"
            reliability_plot(bins, f"{tag} · {trained.calibrator_kind} · "
                                   "calibration split", png)

            path = models.save_arm(trained, MODEL_DIR)
            reloaded = models.load_arm(path)
            round_trip = bool(np.array_equal(
                reloaded.predict_proba(calib_frame), p_cal))

            arms[tag] = trained
            trace.extend(trained.search_trace)
            results[tag] = {
                "algorithm": algorithm,
                "arm": arm,
                "n_features": len(models.ARMS[arm]),
                "best_params": trained.best_params,
                "calibration_choice": cal,
                "calibrated": models.score_split(y_calib.to_numpy(), p_cal,
                                                 tau=trained.tau),
                "uncalibrated": models.score_split(y_calib.to_numpy(), p_raw),
                "out_of_fold_calibration": oof,
                "reliability_bins": bins.to_dict(orient="records"),
                "reliability_plot": str(png.relative_to(RESULTS.parent.parent)),
                "artifact": str(path.relative_to(CODE_ROOT.parent)),
                "fit_id": trained.provenance["fit_id"],
                "round_trip": "PASS" if round_trip else "FAIL",
                "provenance": {k: v for k, v in trained.provenance.items()
                               if k != "calibration"},
                "fit_seconds": round(time.time() - t_arm, 1),
            }
            c = results[tag]["calibrated"]
            print(f"  {tag}: PR-AUC {c['pr_auc']:.6f} · ROC-AUC {c['roc_auc']:.6f} "
                  f"· Brier {c['brier']:.6f} · ECE {c['ece']:.6f} · tau "
                  f"{trained.tau:.6f} · round-trip {results[tag]['round_trip']}",
                  flush=True)
            save_checkpoint(tag, fingerprint=fingerprint, result=results[tag],
                            search_trace=trained.search_trace)

    out = {
        "provenance": {
            "command": COMMAND,
            "run_date": run_date,
            "dataset_path": str(data.DEFAULT_DATASET_PATH),
            "seed": config.RANDOM_SEED,
            "n_iter": args.n_iter,
            "protocol": "eval_protocol §3 (tuning), §4 (models), §5 (metrics + "
                        "calibrator choice), §A1.3 (arms); config DL-018",
            "duration_control": {
                "artifact": "code/artifacts/duration_estimator.joblib",
                "fit_id": expected_fit_id,
                "primary_form": estimator.primary_form,
                "refitted_here": False,
            },
            "library_versions": models.library_versions(),
            "elapsed_s": round(time.time() - t0, 1),
            "resume": {
                "fingerprint": fingerprint,
                "arms_fitted_in_this_invocation": [
                    t for t in results if t not in resumed],
                "arms_resumed_from_checkpoint": list(resumed),
                "checkpoint_dir": str(CKPT_DIR.relative_to(CODE_ROOT.parent)),
                "total_arm_fit_seconds": round(sum(
                    float(r.get("fit_seconds") or 0.0)
                    for r in results.values()), 1),
                "note": ("`elapsed_s` is this invocation's wall clock. Where arms "
                         "were resumed it is NOT the total compute: "
                         "`total_arm_fit_seconds` sums the real per-arm fit time "
                         "across every segment. Resumed arms are bit-identical to "
                         "a cold run (per-arm seeded search, no cross-arm random "
                         "state) and each was re-verified against its persisted "
                         "model before being reused."),
            },
        },
        "population": {
            "train_builds": int(is_train.sum()),
            "train_projects": int(builds.loc[is_train, "gh_project_name"].nunique()),
            "train_failure_rate_pct": round(100 * float(y_train.mean()), 4),
            "calibration_builds": int(is_calib.sum()),
            "calibration_projects": int(calib_projects.nunique()),
            "calibration_failure_rate_pct": round(100 * float(y_calib.mean()), 4),
            "test_builds_dropped_unread": n_test_builds,
            "test_projects_dropped_unread": n_test_projects,
        },
        "checks": {
            "no_test_project_read": "PASS",
            "blocklist_assertion_on_arm_matrices": "PASS",
            "d_hat_loaded_not_refitted": "PASS",
            "train_calibration_project_disjoint": "PASS" if not (
                set(builds.loc[is_train, "gh_project_name"])
                & set(calib_projects)) else "FAIL",
            "round_trip_all_arms": ("PASS" if all(
                r["round_trip"] == "PASS" for r in results.values()) else "FAIL"),
        },
        "arms": results,
    }
    (RESULTS / "model_training.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")
    (RESULTS / "model_search_trace.json").write_text(
        json.dumps(trace, indent=2, default=str), encoding="utf-8")
    write_report(out)
    write_calibration_table(out)
    print(f"\nwrote results/p1/model_training.{{md,json}} and calibration/ in "
          f"{out['provenance']['elapsed_s']}s", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #

def write_calibration_table(out: dict) -> None:
    """The gate-evidence table: Brier/ECE per arm, both calibrators, side by side."""
    L: list[str] = []
    A = L.append
    p = out["provenance"]
    A("# Calibration — Brier / ECE comparison on the calibration split (P1-T5)\n")
    A(f"> Generated by `{p['command']}` on {p['run_date']}. Every number from "
      "that run (R1).\n")
    A("> Rule (§5, DL-004): fit **both** isotonic and Platt on the calibration "
      "split, keep the **lower calibration-split Brier**.\n")

    A("\n## Calibrator selection\n")
    A("| arm | algorithm | isotonic Brier | Platt Brier | chosen | "
      "isotonic ECE | Platt ECE |")
    A("| :-- | :-- | --: | --: | :-: | --: | --: |")
    for tag, r in out["arms"].items():
        c = r["calibration_choice"]["comparison"]
        chosen = r["calibration_choice"]["chosen"]
        A(f"| `{r['arm']}` | {r['algorithm']} | {c['isotonic']['brier']:.6f} | "
          f"{c['sigmoid']['brier']:.6f} | **{chosen}** | "
          f"{c['isotonic']['ece']:.6f} | {c['sigmoid']['ece']:.6f} |")

    A("\n\n## Calibrated performance, control vs full arm, side by side\n")
    A("| algorithm | arm | PR-AUC | ROC-AUC | Brier | ECE | τ | P@τ | R@τ | F1@τ |")
    A("| :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: |")
    for algorithm in models.ALGORITHMS:
        for arm in models.ARMS:
            r = out["arms"].get(f"{algorithm}:{arm}")
            if not r:
                continue
            c = r["calibrated"]
            A(f"| {algorithm} | `{arm}` | {c['pr_auc']:.6f} | {c['roc_auc']:.6f} | "
              f"{c['brier']:.6f} | {c['ece']:.6f} | {c['tau']:.4f} | "
              f"{c['precision_at_tau']:.4f} | {c['recall_at_tau']:.4f} | "
              f"{c['f1_at_tau']:.4f} |")

    A("\n> **These are calibration-split numbers and they are not the RQ1 "
      "answer.** The calibrator was fitted on these same builds, and the "
      "`full` arm's feature set was not chosen here. The confirmatory "
      "comparison happens once, on test, at P3-T1; the model-level RQ2 verdict "
      "is P1-T7's, from the P1-T6 ablation.\n")

    degenerate = [tag for tag, r in out["arms"].items()
                  if r["calibration_choice"]["chosen"] == "isotonic"
                  and r["calibrated"]["ece"] < 1e-9]
    if degenerate:
        A("\n> ### ⚠ In-sample isotonic ECE is degenerate — read it as 0 by "
          "construction, not as perfect calibration\n")
        A("> Isotonic regression is fitted by pooling adjacent violators, and on "
          "the very data it was fitted to, the mean prediction inside each of "
          "its level sets equals the mean outcome there. When the predictions "
          "then fall inside a single 10-bin ECE cell, `conf(B_m)` and "
          "`acc(B_m)` coincide and ECE collapses to ~0 **arithmetically**.\n>")
        A(f"> Affected arms ({len(degenerate)} of {len(out['arms'])}): "
          + ", ".join(f"`{t}`" for t in degenerate) + ".\n>")
        A("> The out-of-fold column below is the meaningful calibration signal "
          "for these arms, and P3-T1's test-split ECE is the reportable one. An "
          "ECE of 0.000000 here must never be quoted as a calibration result.\n")

    A("\n## In-sample optimism of the calibrator (secondary diagnostic)\n")
    A("§5 selects the calibrator by its Brier on the builds it was fitted on. "
      "The column below refits the chosen calibrator under **GroupKFold over "
      "`gh_project_name`**, so each fold scores projects it never calibrated "
      "on. It changes nothing — not the choice, not τ, not the frozen model — "
      "it only gives the optimism a magnitude.\n")
    A("| arm | algorithm | in-sample Brier | out-of-fold Brier | Δ | "
      "in-sample ECE | out-of-fold ECE |")
    A("| :-- | :-- | --: | --: | --: | --: | --: |")
    for tag, r in out["arms"].items():
        oof = r["out_of_fold_calibration"]
        c = r["calibrated"]
        if not oof.get("n"):
            A(f"| `{r['arm']}` | {r['algorithm']} | {c['brier']:.6f} | — | — | "
              f"{c['ece']:.6f} | — |")
            continue
        A(f"| `{r['arm']}` | {r['algorithm']} | {c['brier']:.6f} | "
          f"{oof['brier']:.6f} | {oof['brier'] - c['brier']:+.6f} | "
          f"{c['ece']:.6f} | {oof['ece']:.6f} |")

    A("\n\n## Reliability diagrams\n")
    for tag, r in out["arms"].items():
        A(f"- `{tag}` ({r['calibration_choice']['chosen']}): "
          f"`{Path(r['reliability_plot']).name}`")
    A("")
    (CALIB_DIR / "brier_ece_table.md").write_text("\n".join(L), encoding="utf-8")


def write_report(out: dict) -> None:
    p, pop = out["provenance"], out["population"]
    L: list[str] = []
    A = L.append

    A("# Decision models — training, tuning and calibration (P1-T5)\n")
    A(f"> Generated by `{p['command']}` on {p['run_date']}. Every number below "
      f"comes from that run (R1). Seed `{p['seed']}` · elapsed {p['elapsed_s']}s.\n")
    A(f"> Protocol: {p['protocol']}.\n")
    res = p.get("resume") or {}
    if res.get("arms_resumed_from_checkpoint"):
        A(f"> **Resumed run.** {len(res['arms_fitted_in_this_invocation'])} arm(s) "
          f"were fitted in this invocation and "
          f"{len(res['arms_resumed_from_checkpoint'])} "
          f"(`{'`, `'.join(res['arms_resumed_from_checkpoint'])}`) were reused from "
          f"per-arm checkpoints under fingerprint `{res['fingerprint']}`. Each "
          f"reused arm was re-verified against its persisted model — its stored "
          f"calibration metrics were recomputed and matched exactly — and every "
          f"arm's search is seeded independently, so the result set is identical "
          f"to an uninterrupted run. Real compute across all segments: "
          f"{res['total_arm_fit_seconds']}s of arm fitting.\n")

    A("\n## 1. Arm definitions — the control and the SE arm\n")
    A("§A1.3 makes ablation **incremental over the control**: every arm contains "
      "`d̂`, so the null is a trained model rather than an absence.\n")
    A("| arm | features | what it represents |")
    A("| :-- | --: | :-- |")
    A(f"| `control` | {len(models.ARMS['control'])} — `d̂` alone | the **null**: "
      "what a scheduler knows if it only predicts how long the build will take |")
    A(f"| `full` | {len(models.ARMS['full'])} — `d̂` + all 28 commit-time features "
      "| the **treatment**: duration plus every SE characteristic |")
    A("")
    dc = p["duration_control"]
    A(f"`d̂` is the **frozen** P1-T4 control — artifact `{dc['artifact']}`, fit id "
      f"`{dc['fit_id']}`, primary form **{dc['primary_form']}**. It was "
      f"**loaded, not refitted** (`refitted_here: {dc['refitted_here']}`); the "
      "run asserts the artifact's fit id against `duration_control.json` before "
      "building any arm, because refitting it would silently move the null that "
      "RQ2 is measured against.\n")
    A("The **28-feature contract is unchanged**. The only column any model sees "
      "beyond it is `d̂`, which §A1.3 requires in every arm.\n")

    A("\n## 2. Population\n")
    A("| split | projects | builds | failure rate |")
    A("| :-- | --: | --: | --: |")
    A(f"| train (tuning + fitting) | {pop['train_projects']:,} | "
      f"{pop['train_builds']:,} | {pop['train_failure_rate_pct']}% |")
    A(f"| calibration (calibrator + τ) | {pop['calibration_projects']:,} | "
      f"{pop['calibration_builds']:,} | {pop['calibration_failure_rate_pct']}% |")
    A(f"| **test — closed, never read** | "
      f"{pop['test_projects_dropped_unread']:,} | "
      f"{pop['test_builds_dropped_unread']:,} | not measured |")
    A("")

    A("\n## 3. Training and tuning procedure\n")
    any_arm = next(iter(out["arms"].values()))
    iv = any_arm["provenance"]["internal_validation"]
    A(f"- **Where:** tuning happens **exclusively inside the train projects** "
      "(§3). The calibration split is not read until step 4; the test split is "
      "not read at all in Phase 1.")
    A(f"- **Internal validation:** {iv['rule']} — {iv['n_fit']:,} fit / "
      f"{iv['n_val']:,} validate.")
    A(f"- **Selection metric:** {iv['selection_metric']} (§3).")
    A(f"- **Search:** seeded random search, **{p['n_iter']} candidates**, "
      "identical for every algorithm and every arm — §4 requires the identical "
      "internal-validation procedure across algorithms, so an unequal budget "
      "would measure the budget rather than the family (DL-018 §5).")
    A(f"- **Refit:** {any_arm['provenance']['final_refit']}.")
    A("- **Imbalance:** XGBoost searches `scale_pos_weight` (§3 names it); the "
      "two baselines use `class_weight=\"balanced\"` (DL-018 §3).")
    A("- **Preprocessing:** XGBoost consumes the matrix directly (native missing "
      "handling); the baselines get median imputation fitted inside the "
      "pipeline, and Logistic Regression additionally gets standardisation "
      "(DL-018 §4).")
    A(f"- **Libraries:** `{json.dumps(p['library_versions'])}`.")
    A("\nSelected configurations (full trace in "
      "`results/p1/model_search_trace.json`):\n")
    A("| algorithm | arm | internal-val PR-AUC | selected configuration |")
    A("| :-- | :-- | --: | :-- |")
    for algorithm in models.ALGORITHMS:
        for arm in models.ARMS:
            r = out["arms"].get(f"{algorithm}:{arm}")
            if not r:
                continue
            bp = dict(r["best_params"])
            score = bp.pop("internal_val_pr_auc")
            shown = {k: (round(v, 5) if isinstance(v, float) else v)
                     for k, v in bp.items()}
            A(f"| {algorithm} | `{arm}` | {score:.6f} | `{json.dumps(shown)}` |")
    A("")

    A("\n### Algorithm comparison (train internal-validation fold only)\n")
    A("§4 **predeclares XGBoost as primary**; this table is the evidence for "
      "that declaration, not a re-selection. It is measured on the train "
      "internal-validation fold — the only surface available without touching "
      "calibration or test.\n")
    A("| algorithm | internal-val PR-AUC, `full` arm | internal-val PR-AUC, "
      "`control` arm |")
    A("| :-- | --: | --: |")
    for algorithm in models.ALGORITHMS:
        f_arm = out["arms"].get(f"{algorithm}:full")
        c_arm = out["arms"].get(f"{algorithm}:control")
        mark = " **(predeclared primary)**" if algorithm == models.PRIMARY_ALGORITHM else ""
        A(f"| {algorithm}{mark} | "
          f"{f_arm['best_params']['internal_val_pr_auc']:.6f} | "
          f"{c_arm['best_params']['internal_val_pr_auc']:.6f} |")
    A("")

    A("\n## 4. Calibration results (calibration split)\n")
    A("Both isotonic and Platt were fitted on the calibration split and the "
      "lower calibration-split Brier kept (§5, DL-004). Full table and "
      "reliability diagrams: `results/p1/calibration/`.\n")
    A("| algorithm | arm | calibrator | PR-AUC | ROC-AUC | Brier | ECE | τ | F1@τ |")
    A("| :-- | :-- | :-: | --: | --: | --: | --: | --: | --: |")
    for algorithm in models.ALGORITHMS:
        for arm in models.ARMS:
            r = out["arms"].get(f"{algorithm}:{arm}")
            if not r:
                continue
            c = r["calibrated"]
            A(f"| {algorithm} | `{arm}` | {r['calibration_choice']['chosen']} | "
              f"{c['pr_auc']:.6f} | {c['roc_auc']:.6f} | {c['brier']:.6f} | "
              f"{c['ece']:.6f} | {c['tau']:.4f} | {c['f1_at_tau']:.4f} |")
    A("")
    A("> **This is not the RQ1 or RQ2 answer.** These numbers are in-sample for "
      "the calibrator and the τ selection, and the arm comparison here has no "
      "confidence intervals and no paired bootstrap. The model-level RQ2 verdict "
      "comes from P1-T6's ablation and P1-T7's predeclared admission rule; the "
      "confirmatory test-split evaluation is P3-T1.\n")

    A("\n## 5. Decision thresholds (τ), frozen here\n")
    A("§5's locked rule: τ is the threshold on the **calibrated** probability "
      "that maximises F1 on the calibration split, then frozen and applied "
      "unchanged to test. τ governs only the *reported* classification metrics — "
      "the deferral policy consumes the continuous probability (§7), never τ. "
      "Ties resolve to the lower τ (higher recall), declared in code before the "
      "run.\n")
    A("| algorithm | arm | τ | precision@τ | recall@τ | F1@τ |")
    A("| :-- | :-- | --: | --: | --: | --: |")
    for algorithm in models.ALGORITHMS:
        for arm in models.ARMS:
            r = out["arms"].get(f"{algorithm}:{arm}")
            if not r:
                continue
            c = r["calibrated"]
            A(f"| {algorithm} | `{arm}` | {c['tau']:.6f} | "
              f"{c['precision_at_tau']:.6f} | {c['recall_at_tau']:.6f} | "
              f"{c['f1_at_tau']:.6f} |")
    A("")

    A("\n## 6. Leakage evidence\n")
    for k, v in out["checks"].items():
        A(f"- `{k}`: **{v}**")
    A("")
    A("What each one rules out:\n")
    A("- **`no_test_project_read`** — test rows are dropped immediately after "
      f"the split join ({pop['test_projects_dropped_unread']:,} projects / "
      f"{pop['test_builds_dropped_unread']:,} builds) and asserted absent "
      "before any model is built.")
    A("- **`blocklist_assertion_on_arm_matrices`** — `features.assert_no_leakage` "
      "runs on every design-matrix construction, so no outcome column can enter "
      "an arm even by accident (R7, §A1.2).")
    A("- **`d_hat_loaded_not_refitted`** — the frozen control's fit id is checked "
      "against `duration_control.json`; `d̂`'s own causal-history guard "
      "(`assert_history_is_causal`) runs again when it is attached.")
    A("- **`train_calibration_project_disjoint`** — re-derived from the build "
      "frame here, independently of the P1-T3 manifest.")
    A("- **`round_trip_all_arms`** — every persisted arm reloads and reproduces "
      "its calibrated probabilities exactly (R8).")
    A("\nUnit tests for the arm contract live in `tests/test_models.py`; verbatim "
      "output is captured at the gate in `results/p1/pytest_p1_t5.txt`.\n")

    A("\n## 7. Model provenance\n")
    A("| algorithm | arm | fit id | calibrator | artifact | round-trip |")
    A("| :-- | :-- | :-- | :-: | :-- | :-: |")
    for tag, r in out["arms"].items():
        A(f"| {r['algorithm']} | `{r['arm']}` | `{r['fit_id']}` | "
          f"{r['calibration_choice']['chosen']} | "
          f"`{Path(r['artifact']).as_posix()}` | {r['round_trip']} |")
    A("")
    A(f"All arms: seed `{p['seed']}`, tuned on train only, calibrated on "
      "calibration only, persisted with their imputer/scaler/encoder inside the "
      "pipeline so scoring cannot drift from training.\n")

    A("\n## 8. Methodological threats discovered or carried\n")
    A("1. **§5's calibrator choice is in-sample.** The rule selects between "
      "isotonic and Platt by Brier *on the builds the calibrator was fitted on*, "
      "so both the choice and the reported calibration-split Brier/ECE are "
      "optimistic. The rule is applied exactly as frozen; the size of the "
      "optimism is quantified by the project-grouped out-of-fold diagnostic in "
      "`calibration/brier_ece_table.md`, and the honest numbers arrive at "
      "P3-T1. **Discovered in this task.**")
    degenerate = [tag for tag, r in out["arms"].items()
                  if r["calibration_choice"]["chosen"] == "isotonic"
                  and r["calibrated"]["ece"] < 1e-9]
    if degenerate:
        A(f"   **1a. The in-sample ECE of every isotonic arm is ~0 by "
          f"construction**, not by merit ({len(degenerate)} of "
          f"{len(out['arms'])} arms: "
          + ", ".join(f"`{t}`" for t in degenerate) + "). Isotonic's level sets "
          "match mean prediction to mean outcome on their own fitting data, so "
          "once the predictions land inside one 10-bin ECE cell the statistic "
          "collapses arithmetically. It is reported because §5 requires it, and "
          "flagged everywhere it appears so it is never quoted as a calibration "
          "quality result. **This is the sharpest instance of threat 1 and it "
          "was discovered by this run, not anticipated by the protocol.**")
    A("2. **τ is selected on the calibration split and applied to test**, where "
      "the base rate differs — DL-017 measured calibration 28.55% vs test "
      "25.04% failure (quoted from the P1-T3 manifest; no test project was read "
      "here). An F1-maximising threshold is prevalence-sensitive, so τ is "
      "expected to be mis-centred on test. §5 freezes it deliberately rather "
      "than re-tuning, and P3-T1 must report it against this shift.")
    A("3. **The Random Forest search space is smaller than XGBoost's** "
      "(DL-018 §Threats 1), bounded for compute. Any XGBoost-over-RF result is "
      "therefore not a clean family comparison.")
    A(f"4. **The search budget is {p['n_iter']} candidates** over an "
      "8-dimensional XGBoost space (DL-018 §Threats 2). It is identical across "
      "arms, so the **arm** comparison that RQ2 rests on is unaffected; the "
      "**algorithm** comparison is the weaker claim.")
    A("5. **Median imputation for the baselines is a modelling choice XGBoost "
      "does not make** (DL-018 §Threats 3), so part of any XGBoost-vs-baseline "
      "gap may be missing-value handling rather than model family.")
    A("6. **F2 is structurally weakened.** `git_diff_test_churn` is empty across "
      "the whole release, so `test_churn` and `test_density_ratio` are constant "
      "(DL-016). The `full` arm therefore carries 26 informative features, not "
      "28 — inherited from P1-T2, and it binds how P1-T6's family ablation must "
      "be read.")
    A("7. **`d̂` is a predicted quantity** (P1-T4 §Threats 1), so the control "
      "arm is 'what a *predictable* duration knows', and RQ2 answers *beyond "
      "predictable duration*. ④a-vs-④b showed the control's own accuracy varies "
      "sharply by form; the arms here use the frozen primary (④b) only.")
    A("8. **The frozen protocol body still uses pre-DL-012 task IDs** (§5 says "
      "'calibration split in P1-T3, test split in P1-T4'). Under the current "
      "28-task plan those are P1-T5 and P3-T1. The frozen text is immutable by "
      "R3 and Layer 0-A governs execution, so this is a reading hazard rather "
      "than a conflict — recorded so a later reader does not mis-locate the "
      "evidence.\n")

    A("\n## 9. Provenance footer\n")
    A(f"- Dataset: `{p['dataset_path']}` (read-only).")
    A("- Split: frozen P1-T3 assignment, digest re-verified at load.")
    A(f"- **Test split untouched:** {pop['test_projects_dropped_unread']:,} "
      f"projects / {pop['test_builds_dropped_unread']:,} builds dropped before "
      "any model existed, and never read.")
    A(f"- Duration control: loaded from `{dc['artifact']}` (fit id "
      f"`{dc['fit_id']}`), **not refitted**.")
    A(f"- Models: `code/artifacts/models/` — {len(out['arms'])} arms.")
    A("")
    (RESULTS / "model_training.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

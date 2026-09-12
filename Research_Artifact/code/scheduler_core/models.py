"""Failure-risk models: the control arm, the full arm, and three algorithms (P1-T5).

Implements `results/p0/eval_protocol.md` §3 (tuning), §4 (models compared) and
§5 (metrics + calibrator choice), with the arm structure of **§A1.3**:

> Ablation is **incremental over the control**, not standalone: every arm
> contains `d̂`.

So the null is a *trained model*, not an afterthought — arm ``control`` is
``{d̂}`` alone and arm ``full`` is ``{d̂ + all 28 features}``. P1-T6 adds the
per-family arms on the same machinery; nothing here is family-specific.

Three rules this module exists to enforce:

* **`d̂` is loaded, never refitted.** The duration control was frozen at P1-T4
  (`code/artifacts/duration_estimator.joblib`, primary form ④b). Refitting it
  here would silently change the null that RQ2 is measured against, so
  :func:`attach_d_hat` asserts the artifact's ``fit_id`` against the value
  recorded in ``results/p1/duration_control.json``.
* **Tuning never leaves the train split.** The internal-validation fold is the
  temporally-latest 20% of train builds (§3); the calibration split is not read
  until :func:`calibrate`, and the test split is not read in P1 at all.
* **Every arm is trained by the identical procedure.** Same fold, same search
  budget, same selection metric — only the feature set differs (§A1.4). A
  comparison where the arms were tuned differently would not measure the
  feature set.

Search spaces, the imbalance handling for the two baselines, and the shared
search budget are declared in **DL-018**, before any fit.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from scheduler_core import features
from scheduler_core.config import RANDOM_SEED

#: The control term every arm carries (eval_protocol §A1.3). Produced by the
#: frozen P1-T4 estimator; never recomputed here.
D_HAT_COLUMN: str = "d_hat_log1p"

#: The two reference arms of P1-T5. P1-T6 extends this with `{d̂ + Fᵢ}`.
ARMS: Mapping[str, tuple[str, ...]] = {
    "control": (D_HAT_COLUMN,),
    "full": (D_HAT_COLUMN,) + tuple(features.FEATURES),
}

#: Primary first (spec §3.2/§4 predeclare XGBoost); the other two are baselines.
ALGORITHMS: tuple[str, str, str] = ("xgboost", "logreg", "random_forest")

#: eval_protocol §4: the primary is predeclared, not chosen from a result.
PRIMARY_ALGORITHM: str = "xgboost"

#: Shared, identical search budget for every algorithm and every arm (DL-018).
#: §4 requires the "identical internal-validation procedure" across algorithms,
#: so the budget is a property of the procedure, not of the family.
SEARCH_N_ITER: int = 20

#: §3: the temporally-latest share of train builds forms the tuning fold.
INTERNAL_VAL_SHARE: float = 0.20

#: §5: ECE uses M = 10 equal-width bins.
ECE_BINS: int = 10

#: §5: fit both, keep the lower calibration-split Brier.
CALIBRATORS: tuple[str, str] = ("isotonic", "sigmoid")


class ArmLeakageError(AssertionError):
    """Raised when an arm's design matrix or fitting population violates the
    split discipline (§2) or the commit-time-only feature contract (R7)."""


# --------------------------------------------------------------------------- #
# The control term: loaded from the frozen P1-T4 artifact
# --------------------------------------------------------------------------- #

def attach_d_hat(
    feature_frame: pd.DataFrame,
    key_frame: pd.DataFrame,
    durations: pd.Series,
    *,
    estimator: Any,
    expected_fit_id: str | None = None,
) -> pd.Series:
    """`d̂` for every build, from the **frozen** duration control.

    ``durations`` is used **only** to build each project's strictly-earlier
    causal history (mechanism 2) — never for the scored build itself. That is
    the same guarantee P1-T4 proves, re-asserted here because this is the first
    consumer.

    Raises if the artifact is not the frozen one, or if its primary form was
    never set (which would mean §5's selection had not been applied).
    """
    from scheduler_core import duration_estimator as de

    if estimator.primary_form is None:
        raise ArmLeakageError(
            "the duration control carries no primary_form — §5's selection was "
            "not applied, so there is no defined d̂ to build an arm on"
        )
    if expected_fit_id is not None and estimator.provenance["fit_id"] != expected_fit_id:
        raise ArmLeakageError(
            f"duration control fit_id {estimator.provenance['fit_id']!r} is not "
            f"the frozen {expected_fit_id!r} recorded at P1-T4 — the null that "
            "RQ2 is measured against would silently change"
        )

    history = de.causal_project_history(key_frame, durations)
    de.assert_history_is_causal(key_frame, history)
    out = (estimator.predict_4b(feature_frame, history)
           if estimator.primary_form == "4b"
           else estimator.predict_4a(feature_frame, history))
    return pd.Series(out["d_hat_log1p"].to_numpy(), index=feature_frame.index,
                     name=D_HAT_COLUMN)


# --------------------------------------------------------------------------- #
# Design matrices — one per arm
# --------------------------------------------------------------------------- #

def design_matrix(
    frame: pd.DataFrame,
    arm: str,
    *,
    lang_levels: Sequence[str],
) -> pd.DataFrame:
    """Numeric matrix for ``arm``: its features, with ``lang`` one-hot encoded.

    ``frame`` carries the 28 features plus :data:`D_HAT_COLUMN`. The blocklist
    assertion runs on every call — an arm is the last place a raw outcome column
    could enter a model.
    """
    if arm not in ARMS:
        raise KeyError(f"unknown arm {arm!r}; known: {sorted(ARMS)}")
    features.assert_no_leakage(columns=frame.columns)

    wanted = ARMS[arm]
    missing = [c for c in wanted if c not in frame.columns]
    if missing:
        raise KeyError(f"arm {arm!r} is missing columns: {missing}")

    numeric = [c for c in wanted if c not in features.CATEGORICAL_FEATURES]
    out = frame[numeric].apply(pd.to_numeric, errors="coerce").astype("float64")
    if "lang" in wanted:
        lang = frame["lang"].astype("string")
        for level in lang_levels:
            out[f"lang={level}"] = (lang == level).astype("float64").to_numpy()
    return out


# --------------------------------------------------------------------------- #
# Search spaces — declared in DL-018 before any fit
# --------------------------------------------------------------------------- #

def sample_params(algorithm: str, rng: np.random.Generator, *,
                  pos_weight: float) -> dict[str, Any]:
    """One draw from ``algorithm``'s declared space (DL-018).

    ``pos_weight`` is the train-split imbalance ratio (negatives / positives);
    XGBoost searches ``scale_pos_weight`` around it, because §3 lists that
    parameter as part of the search rather than as a fixed constant.
    """
    if algorithm == "xgboost":
        return {
            "n_estimators": int(round(float(np.exp(
                rng.uniform(np.log(100), np.log(800)))))),
            "max_depth": int(rng.integers(3, 11)),
            "learning_rate": float(np.exp(rng.uniform(np.log(0.01), np.log(0.30)))),
            "subsample": float(rng.uniform(0.6, 1.0)),
            "colsample_bytree": float(rng.uniform(0.6, 1.0)),
            "min_child_weight": int(round(float(np.exp(
                rng.uniform(np.log(1), np.log(20)))))),
            "gamma": float(rng.uniform(0.0, 5.0)),
            "scale_pos_weight": float(np.exp(rng.uniform(
                np.log(0.5 * pos_weight), np.log(2.0 * pos_weight)))),
        }
    if algorithm == "logreg":
        return {"C": float(np.exp(rng.uniform(np.log(1e-4), np.log(1e2))))}
    if algorithm == "random_forest":
        # Bounded for tractability at 645k × 32 (DL-018 §Budget): depth ≤ 16 and
        # leaf ≥ 10 keep a single fit inside minutes. This is a smaller effective
        # space than XGBoost's, and that asymmetry is a declared threat to the
        # algorithm comparison — not a claim that RF was given equal search.
        return {
            "n_estimators": int(round(float(np.exp(
                rng.uniform(np.log(100), np.log(300)))))),
            "max_depth": int(rng.integers(4, 17)),
            "min_samples_leaf": int(round(float(np.exp(
                rng.uniform(np.log(10), np.log(200)))))),
            "max_features": str(rng.choice(["sqrt", "log2"])),
        }
    raise ValueError(f"unknown algorithm {algorithm!r}")


def build_estimator(algorithm: str, params: Mapping[str, Any], *,
                    seed: int = RANDOM_SEED) -> Any:
    """Instantiate ``algorithm`` with ``params``.

    Imbalance handling differs by family but is present in all three (spec
    §3.5): XGBoost uses ``scale_pos_weight`` (§3 names it), and the two
    scikit-learn baselines use ``class_weight="balanced"``, the equivalent
    reweighting — otherwise the baselines would be handicapped by a design
    choice rather than by their inductive bias (DL-018).

    The baselines also need median imputation (train medians, fitted inside the
    pipeline) because neither accepts NaN, while XGBoost learns a missing
    direction natively. The imputer is part of the persisted model, so scoring
    cannot drift from training.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if algorithm == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(
            objective="binary:logistic", eval_metric="logloss",
            tree_method="hist", n_jobs=-1, random_state=seed, **params,
        )
    if algorithm == "logreg":
        from sklearn.linear_model import LogisticRegression

        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            # L2 is the library default; the explicit `penalty=` kwarg is
            # deprecated in scikit-learn 1.8, so the default is relied on.
            ("clf", LogisticRegression(
                solver="lbfgs", max_iter=1000,
                class_weight="balanced", random_state=seed, **params)),
        ])
    if algorithm == "random_forest":
        from sklearn.ensemble import RandomForestClassifier

        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("clf", RandomForestClassifier(
                class_weight="balanced", n_jobs=-1, random_state=seed,
                **params)),
        ])
    raise ValueError(f"unknown algorithm {algorithm!r}")


# --------------------------------------------------------------------------- #
# Metrics (§5)
# --------------------------------------------------------------------------- #

def expected_calibration_error(y_true: np.ndarray, p: np.ndarray, *,
                               bins: int = ECE_BINS) -> float:
    """§5's ECE: ``Σ_m (|B_m|/N)·|acc(B_m) − conf(B_m)|`` over equal-width bins."""
    y_true = np.asarray(y_true, dtype="float64")
    p = np.asarray(p, dtype="float64")
    n = len(p)
    if n == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    # np.digitize puts p == 1.0 in an overflow bin; clamp it back into the last.
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    total = 0.0
    for m in range(bins):
        sel = idx == m
        if not sel.any():
            continue
        total += (sel.sum() / n) * abs(y_true[sel].mean() - p[sel].mean())
    return float(total)


def threshold_maximising_f1(y_true: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """§5's locked τ rule, evaluated on the calibration split.

    τ is the threshold on the **calibrated** probability that maximises F1. It is
    frozen here and applied unchanged to test at P3-T1; it governs only the
    reported classification metrics, never the deferral policy (which consumes
    the continuous probability, §7).

    Candidate thresholds are the distinct predicted probabilities, so the search
    is exhaustive over everything that can change the confusion matrix. Ties
    resolve to the **lower** τ (higher recall) — declared here, not after
    looking, because F1 plateaus are common at this scale.
    """
    from sklearn.metrics import precision_recall_curve

    precision, recall, thresholds = precision_recall_curve(y_true, p)
    # precision_recall_curve returns len(thresholds) == len(precision) - 1.
    precision, recall = precision[:-1], recall[:-1]
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom,
                   out=np.zeros_like(denom), where=denom > 0)
    best = int(np.argmax(f1))          # argmax takes the first, i.e. lowest τ
    return {"tau": float(thresholds[best]), "f1": float(f1[best]),
            "precision": float(precision[best]), "recall": float(recall[best])}


def score_split(y_true: np.ndarray, p: np.ndarray, *,
                tau: float | None = None) -> dict[str, Any]:
    """The §5 metric set for one arm on one split."""
    from sklearn.metrics import (average_precision_score, brier_score_loss,
                                 f1_score, precision_score, recall_score,
                                 roc_auc_score)

    y_true = np.asarray(y_true, dtype="int64")
    p = np.asarray(p, dtype="float64")
    out: dict[str, Any] = {
        "n": int(len(y_true)),
        "positives": int(y_true.sum()),
        "base_rate": float(y_true.mean()) if len(y_true) else float("nan"),
        "pr_auc": float(average_precision_score(y_true, p)),
        "roc_auc": float(roc_auc_score(y_true, p)),
        "brier": float(brier_score_loss(y_true, p)),
        "ece": expected_calibration_error(y_true, p),
    }
    if tau is not None:
        pred = (p >= tau).astype("int64")
        out.update({
            "tau": float(tau),
            "precision_at_tau": float(precision_score(y_true, pred, zero_division=0)),
            "recall_at_tau": float(recall_score(y_true, pred, zero_division=0)),
            "f1_at_tau": float(f1_score(y_true, pred, zero_division=0)),
        })
    return out


def reliability_bins(y_true: np.ndarray, p: np.ndarray, *,
                     bins: int = ECE_BINS) -> pd.DataFrame:
    """10-bin reliability data (§5): predicted confidence vs observed frequency."""
    y_true = np.asarray(y_true, dtype="float64")
    p = np.asarray(p, dtype="float64")
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    rows = []
    for m in range(bins):
        sel = idx == m
        rows.append({
            "bin": m,
            "lo": float(edges[m]),
            "hi": float(edges[m + 1]),
            "n": int(sel.sum()),
            "confidence": float(p[sel].mean()) if sel.any() else float("nan"),
            "observed": float(y_true[sel].mean()) if sel.any() else float("nan"),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# One trained, calibrated arm
# --------------------------------------------------------------------------- #

@dataclass
class TrainedArm:
    """One (algorithm, arm) pair: tuned on train, calibrated on calibration."""

    algorithm: str
    arm: str
    base_model: Any = None
    calibrator: Any = None
    calibrator_kind: str = ""
    tau: float = float("nan")
    best_params: dict[str, Any] = field(default_factory=dict)
    search_trace: list[dict[str, Any]] = field(default_factory=list)
    design_columns: tuple[str, ...] = ()
    lang_levels: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    # -- prediction -------------------------------------------------------- #

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        """Calibrated failure probability for every row of ``frame``."""
        if self.calibrator is None:
            raise RuntimeError(f"{self.name} is not calibrated")
        x = design_matrix(frame, self.arm, lang_levels=self.lang_levels)
        return np.asarray(self.calibrator.predict_proba(x[list(self.design_columns)])[:, 1],
                          dtype="float64")

    def predict_proba_uncalibrated(self, frame: pd.DataFrame) -> np.ndarray:
        x = design_matrix(frame, self.arm, lang_levels=self.lang_levels)
        return np.asarray(self.base_model.predict_proba(
            x[list(self.design_columns)])[:, 1], dtype="float64")

    @property
    def name(self) -> str:
        return f"{self.algorithm}:{self.arm}"

    def fit_id(self) -> str:
        payload = json.dumps({
            "algorithm": self.algorithm, "arm": self.arm,
            "params": self.best_params,
            "design_columns": list(self.design_columns),
            "calibrator": self.calibrator_kind,
            "tau": self.tau,
            "n_train": self.provenance.get("n_train"),
            "fit_row_range": self.provenance.get("fit_row_range"),
        }, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def library_versions() -> dict[str, str]:
    import sklearn
    import xgboost

    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
    }


# --------------------------------------------------------------------------- #
# Train + tune (train split only, §3)
# --------------------------------------------------------------------------- #

def _make_prediction_deterministic(algorithm: str, fitted: Any) -> None:
    """Pin the fitted forest to single-threaded prediction.

    ``RandomForestClassifier.predict_proba`` accumulates per-tree probabilities
    into a shared array from a thread pool, so with ``n_jobs=-1`` the summation
    *order* varies run to run and the result differs in the last bits. Fitting is
    unaffected — trees are seeded independently from ``random_state`` — so
    dropping to one thread **after** the fit costs nothing but makes the
    persisted model reproduce its predictions exactly (R8, the P1-T5 round-trip
    DoD). Without this the round-trip test fails on float noise and would have to
    be weakened to a tolerance, which is the wrong trade for a reproducibility
    claim.
    """
    if algorithm != "random_forest":
        return
    clf = fitted.named_steps["clf"] if hasattr(fitted, "named_steps") else fitted
    clf.n_jobs = 1


def train_arm(
    algorithm: str,
    arm: str,
    train_frame: pd.DataFrame,
    y_train: pd.Series,
    started_at: pd.Series,
    *,
    lang_levels: Sequence[str],
    seed: int = RANDOM_SEED,
    n_iter: int = SEARCH_N_ITER,
    verbose: bool = False,
) -> TrainedArm:
    """Tune ``algorithm`` on ``arm`` inside the train split, then refit on all of it.

    §3's procedure exactly: order train builds by ``gh_build_started_at``, hold
    out the latest 20% as the internal-validation fold, fit candidates on the
    earlier 80%, and select by **PR-AUC** on that fold. The winning
    configuration is then refit on 100% of train, which is what gets calibrated.
    """
    from sklearn.metrics import average_precision_score

    order = np.lexsort((np.arange(len(train_frame)),
                        pd.to_datetime(started_at, utc=True).to_numpy()))
    frame = train_frame.iloc[order]
    y = np.asarray(y_train, dtype="int64")[order]

    design = design_matrix(frame, arm, lang_levels=lang_levels)
    n_val = max(1, int(round(INTERNAL_VAL_SHARE * len(design))))
    n_fit = len(design) - n_val
    x_fit, x_val = design.iloc[:n_fit], design.iloc[n_fit:]
    y_fit, y_val = y[:n_fit], y[n_fit:]
    if y_fit.sum() == 0 or y_val.sum() == 0:
        raise ArmLeakageError(
            "the internal-validation split leaves one side with no failures — "
            "PR-AUC is undefined there (§3)"
        )

    pos_weight = float((y_fit == 0).sum()) / max(1, int((y_fit == 1).sum()))
    rng = np.random.default_rng(seed)
    trace: list[dict[str, Any]] = []
    best: tuple[float, dict[str, Any]] | None = None

    for i in range(n_iter):
        params = sample_params(algorithm, rng, pos_weight=pos_weight)
        model = build_estimator(algorithm, params, seed=seed)
        model.fit(x_fit, y_fit)
        p = model.predict_proba(x_val)[:, 1]
        pr_auc = float(average_precision_score(y_val, p))
        trace.append({"algorithm": algorithm, "arm": arm, "candidate": i,
                      "params": params, "internal_val_pr_auc": pr_auc})
        if best is None or pr_auc > best[0]:
            best = (pr_auc, params)
        if verbose:
            print(f"    {algorithm:<14} {arm:<8} {i + 1:>2}/{n_iter}  "
                  f"val PR-AUC {pr_auc:.6f}  best {best[0]:.6f}", flush=True)

    assert best is not None
    final = build_estimator(algorithm, best[1], seed=seed)
    final.fit(design, y)
    _make_prediction_deterministic(algorithm, final)

    parsed = pd.to_datetime(started_at, utc=True).iloc[order]
    return TrainedArm(
        algorithm=algorithm,
        arm=arm,
        base_model=final,
        best_params={**best[1], "internal_val_pr_auc": best[0]},
        search_trace=trace,
        design_columns=tuple(design.columns),
        lang_levels=tuple(lang_levels),
        provenance={
            "seed": seed,
            "split": "train",
            "n_train": int(len(design)),
            "n_train_positives": int(y.sum()),
            "train_base_rate": float(y.mean()),
            "pos_weight_from_fit_fold": pos_weight,
            "internal_validation": {
                "share": INTERNAL_VAL_SHARE, "n_fit": int(n_fit),
                "n_val": int(n_val),
                "rule": "temporally-latest 20% of train builds by "
                        "gh_build_started_at (eval_protocol §3)",
                "selection_metric": "PR-AUC (average precision), positive = failure",
            },
            "final_refit": "the selected configuration is refit on 100% of train; "
                           "the search never saw the internal-validation fold",
            "n_search_candidates": int(n_iter),
            "features": list(ARMS[arm]),
            "library_versions": library_versions(),
        },
    )


# --------------------------------------------------------------------------- #
# Calibrate (calibration split only, §5)
# --------------------------------------------------------------------------- #

def calibrate(
    trained: TrainedArm,
    calib_frame: pd.DataFrame,
    y_calib: pd.Series,
    *,
    verbose: bool = False,
) -> dict[str, Any]:
    """Fit isotonic **and** Platt on calibration; keep the lower Brier (§5).

    Returns the comparison — both calibrators' Brier scores, the winner, and the
    frozen τ — and mutates ``trained`` to carry the winner.

    **A threat this function cannot remove.** §5 selects the calibrator by its
    Brier score *on the same builds it was fitted on*, so that number is
    in-sample for the calibrator and is optimistic. The protocol's rule is
    applied exactly as written; the honest out-of-sample calibration numbers
    arrive at P3-T1 on the test split. :func:`out_of_fold_calibration` provides a
    secondary, project-grouped estimate so the size of the optimism is visible
    rather than merely acknowledged.
    """
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.metrics import brier_score_loss

    x = design_matrix(calib_frame, trained.arm,
                      lang_levels=trained.lang_levels)[list(trained.design_columns)]
    y = np.asarray(y_calib, dtype="int64")

    comparison: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    for kind in CALIBRATORS:
        cal = CalibratedClassifierCV(FrozenEstimator(trained.base_model),
                                     method=kind)
        cal.fit(x, y)
        p = cal.predict_proba(x)[:, 1]
        comparison[kind] = {
            "brier": float(brier_score_loss(y, p)),
            "ece": expected_calibration_error(y, p),
        }
        fitted[kind] = cal
        if verbose:
            print(f"    {trained.name:<24} {kind:<9} "
                  f"Brier {comparison[kind]['brier']:.6f}  "
                  f"ECE {comparison[kind]['ece']:.6f}", flush=True)

    winner = min(CALIBRATORS, key=lambda k: comparison[k]["brier"])
    trained.calibrator = fitted[winner]
    trained.calibrator_kind = winner

    p_win = trained.calibrator.predict_proba(x)[:, 1]
    tau = threshold_maximising_f1(y, p_win)
    trained.tau = tau["tau"]
    trained.provenance["calibration"] = {
        "split": "calibration",
        "n_calibration": int(len(y)),
        "calibration_base_rate": float(y.mean()),
        "rule": "fit both isotonic and Platt on the calibration split; keep the "
                "lower calibration-split Brier (eval_protocol §5, DL-004)",
        "comparison": comparison,
        "chosen": winner,
        "tau_rule": "threshold on the calibrated probability maximising F1 on "
                    "the calibration split; frozen for test (§5)",
        "tau_selection": tau,
    }
    trained.provenance["fit_id"] = trained.fit_id()
    return trained.provenance["calibration"]


def out_of_fold_calibration(
    trained: TrainedArm,
    calib_frame: pd.DataFrame,
    y_calib: pd.Series,
    groups: pd.Series,
    *,
    n_splits: int = 5,
) -> dict[str, Any]:
    """Project-grouped out-of-fold calibration metrics — a **secondary** diagnostic.

    The protocol's calibrator choice (§5) is in-sample by construction. This
    refits the chosen calibrator on k−1 project groups and scores the held-out
    group, so the reported optimism has a magnitude. It **does not** change the
    selection, the frozen calibrator, or τ; it exists so the threat can be
    quantified in the report instead of only named.
    """
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.frozen import FrozenEstimator
    from sklearn.metrics import brier_score_loss
    from sklearn.model_selection import GroupKFold

    x = design_matrix(calib_frame, trained.arm,
                      lang_levels=trained.lang_levels)[list(trained.design_columns)]
    y = np.asarray(y_calib, dtype="int64")
    oof = np.full(len(y), np.nan, dtype="float64")

    for fit_idx, held_idx in GroupKFold(n_splits=n_splits).split(x, y, groups):
        if y[fit_idx].sum() == 0 or y[fit_idx].sum() == len(fit_idx):
            continue
        cal = CalibratedClassifierCV(FrozenEstimator(trained.base_model),
                                     method=trained.calibrator_kind)
        cal.fit(x.iloc[fit_idx], y[fit_idx])
        oof[held_idx] = cal.predict_proba(x.iloc[held_idx])[:, 1]

    ok = ~np.isnan(oof)
    if not ok.any():
        return {"n": 0}
    return {
        "n": int(ok.sum()),
        "n_splits": n_splits,
        "grouping": "GroupKFold over gh_project_name — folds are project-disjoint, "
                    "so the diagnostic never scores a project it calibrated on",
        "brier": float(brier_score_loss(y[ok], oof[ok])),
        "ece": expected_calibration_error(y[ok], oof[ok]),
    }


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

def save_arm(trained: TrainedArm, directory: "str | Path") -> Path:
    import joblib

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{trained.algorithm}__{trained.arm}.joblib"
    joblib.dump(trained, path)
    return path


def load_arm(path: "str | Path") -> TrainedArm:
    import joblib

    obj = joblib.load(Path(path))
    if not isinstance(obj, TrainedArm):
        raise TypeError(f"{path} does not hold a TrainedArm")
    return obj

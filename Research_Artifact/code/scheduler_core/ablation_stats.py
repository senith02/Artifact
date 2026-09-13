"""Statistics for the P1-T6 feature-family ablation.

Implements the four procedures fixed by **DL-019**, before any ablation arm was
fitted (R4):

* :func:`paired_metric_delta` — a **build-level** paired bootstrap over
  PR-AUC/ROC-AUC/Brier/ECE, resampling the shared calibration-build index with
  replacement. This is **not** `eval_protocol.md` §10's `paired_bootstrap`
  signature — that one pairs *strategies* over a P3 replay trace. This
  function pairs two **arms'** predictions on the same builds. Both share
  §9's numeric conventions (`B = 1000`, seed `RANDOM_SEED`, 95% percentile CI)
  so the project has one bootstrap standard, not two, even though the two
  functions resample different things.
* :func:`spearman_with_ci` — the §A1.8 monotonicity check: a feature's raw
  value vs. its SHAP value, with a bootstrap CI on the rank correlation.
* :func:`variance_decomposition` — the §A1.9 between/within-project variance
  split for a family's aggregate SHAP contribution.

Every function is seeded and deterministic given its inputs.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from scheduler_core.config import RANDOM_SEED
from scheduler_core.models import expected_calibration_error

#: eval_protocol §9's resample count and CI level, reused here (DL-019 §3).
N_RESAMPLES: int = 1000
CI: float = 0.95

_METRIC_NAMES: tuple[str, ...] = ("pr_auc", "roc_auc", "brier", "ece")


def _metric_values(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    return {
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "ece": expected_calibration_error(y, p),
    }


def paired_metric_delta(
    y_true: "np.ndarray | pd.Series",
    p_control: "np.ndarray | pd.Series",
    p_treatment: "np.ndarray | pd.Series",
    *,
    n_resamples: int = N_RESAMPLES,
    ci: float = CI,
    seed: int = RANDOM_SEED,
) -> dict[str, dict[str, float]]:
    """Paired bootstrap of treatment-minus-control, over the shared build index.

    Point estimates (``control``, ``treatment``, ``delta``) come from the full
    calibration split; the CI comes from ``n_resamples`` resamples of the
    build index with replacement, recomputing both arms' metrics on the
    **same** resampled indices each draw (paired), per §9's method. A
    resample landing on a single class (PR-AUC/ROC-AUC undefined) is redrawn
    from the same RNG stream — at this split's ~28% base rate and ~10^5-scale
    n, this is not expected to trigger.
    """
    y = np.asarray(y_true, dtype="int64")
    pc = np.asarray(p_control, dtype="float64")
    pt = np.asarray(p_treatment, dtype="float64")
    n = len(y)
    if not (len(pc) == n and len(pt) == n):
        raise ValueError("y_true, p_control and p_treatment must be the same length")

    point_c = _metric_values(y, pc)
    point_t = _metric_values(y, pt)

    rng = np.random.default_rng(seed)
    deltas: dict[str, np.ndarray] = {m: np.empty(n_resamples) for m in _METRIC_NAMES}
    for b in range(n_resamples):
        for _retry in range(10):
            idx = rng.integers(0, n, size=n)
            yb = y[idx]
            if 0 < yb.sum() < n:
                break
        else:
            raise RuntimeError("could not draw a non-degenerate resample in 10 tries")
        mc = _metric_values(yb, pc[idx])
        mt = _metric_values(yb, pt[idx])
        for m in _METRIC_NAMES:
            deltas[m][b] = mt[m] - mc[m]

    lo_q, hi_q = (1.0 - ci) / 2.0, 1.0 - (1.0 - ci) / 2.0
    out: dict[str, dict[str, float]] = {}
    for m in _METRIC_NAMES:
        d = deltas[m]
        ci_lo, ci_hi = float(np.quantile(d, lo_q)), float(np.quantile(d, hi_q))
        out[m] = {
            "control": point_c[m],
            "treatment": point_t[m],
            "delta": point_t[m] - point_c[m],
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "significant": bool(ci_lo > 0 or ci_hi < 0),
        }
    return out


def spearman_with_ci(
    x: "np.ndarray | pd.Series",
    s: "np.ndarray | pd.Series",
    *,
    n_resamples: int = N_RESAMPLES,
    ci: float = CI,
    seed: int = RANDOM_SEED,
) -> dict[str, float | bool]:
    """Spearman rank correlation between a feature's value and its SHAP value.

    §A1.8's monotonicity check (DL-019 §5): ``monotone`` is true iff the
    bootstrap CI excludes 0 — a stable-signed relationship under resampling.
    This is a **necessary, not sufficient**, condition for treating the
    feature as a simple window knob.
    """
    from scipy.stats import spearmanr

    x = np.asarray(x, dtype="float64")
    s = np.asarray(s, dtype="float64")
    n = len(x)
    if len(s) != n:
        raise ValueError("x and s must be the same length")

    if np.nanstd(x) == 0.0 or np.nanstd(s) == 0.0:
        return {"rho": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
                "monotone": False, "degenerate": True}

    point = float(spearmanr(x, s).statistic)
    rng = np.random.default_rng(seed)
    draws = np.empty(n_resamples)
    for b in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        r = spearmanr(x[idx], s[idx]).statistic
        draws[b] = r if np.isfinite(r) else 0.0
    lo_q, hi_q = (1.0 - ci) / 2.0, 1.0 - (1.0 - ci) / 2.0
    ci_lo, ci_hi = float(np.quantile(draws, lo_q)), float(np.quantile(draws, hi_q))
    return {"rho": point, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "monotone": bool(ci_lo > 0 or ci_hi < 0), "degenerate": False}


def variance_decomposition(values: "np.ndarray | pd.Series",
                           groups: "np.ndarray | pd.Series") -> dict[str, float | int]:
    """Between-project vs. within-project variance split (§A1.9, DL-019 §6).

    ``values`` is typically a family's per-build summed SHAP contribution;
    ``groups`` is ``gh_project_name``. Reports each share of the total sum of
    squares (between + within), which equals the total sum of squares to
    numerical precision — checked by the caller's test suite.
    """
    x = pd.Series(np.asarray(values, dtype="float64"))
    g = pd.Series(np.asarray(groups))
    if len(x) != len(g):
        raise ValueError("values and groups must be the same length")

    grand_mean = float(x.mean())
    by_group = x.groupby(g.to_numpy())
    group_means = by_group.mean()
    group_sizes = by_group.size()
    between = float((group_sizes * (group_means - grand_mean) ** 2).sum())
    within = float(by_group.apply(lambda v: float(((v - v.mean()) ** 2).sum())).sum())
    total = between + within
    return {
        "between": between,
        "within": within,
        "total": total,
        "between_share": (between / total) if total > 0 else float("nan"),
        "within_share": (within / total) if total > 0 else float("nan"),
        "n_groups": int(g.nunique()),
        "n": int(len(x)),
    }

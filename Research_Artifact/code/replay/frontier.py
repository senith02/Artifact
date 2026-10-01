"""Swept frontiers and the matched-point comparison — `eval_protocol.md` §A1.5/§A1.7, DL-029.

Pure functions over (carbon saved %, TTFF p95 h) points. Nothing here reads a
dataset or fits anything; `scripts/frontier_analysis.py` supplies the points.

Conventions (DL-029):

* A **frontier** is the Pareto-efficient subset of a strategy's swept points —
  more carbon saved is better, lower TTFF p95 is better — sorted by saving, so
  TTFF p95 is strictly increasing along it. It is piecewise-linear between its
  points and is **never extrapolated** outside its own range.
* **Matched points** are K interior points of the overlap of two frontiers' ranges
  on one axis: ``linspace(lo, hi, K + 2)[1:-1]``.
* Differences are signed so that **positive favours the treatment** (⑤): at
  matched carbon ``TTFF_ref − TTFF_trt``; at matched TTFF ``S_trt − S_ref``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

K_MATCHED: int = 10          # DL-029 §4
N_AREA: int = 201            # DL-029 §6
TTFF_FLOOR: float = 0.05     # §A1.7: ≥ 5% relative TTFF p95 reduction at matched carbon
CARBON_FLOOR: float = 0.01   # §A1.7: ≥ 1% relative carbon-saved increase at matched TTFF
MIN_POINTS: int = 3          # §A1.7: at ≥ 3 matched points
MAX_UNDEFINED_SHARE: float = 0.05   # DL-029 §8


@dataclass(frozen=True)
class Frontier:
    saving: np.ndarray       # ascending
    ttff: np.ndarray         # strictly ascending

    @property
    def saving_range(self) -> tuple[float, float]:
        return float(self.saving[0]), float(self.saving[-1])

    @property
    def ttff_range(self) -> tuple[float, float]:
        return float(self.ttff[0]), float(self.ttff[-1])


def pareto_frontier(saving: Any, ttff: Any) -> Frontier:
    """Pareto-efficient points (max saving, min TTFF p95), sorted by saving (DL-029 §3)."""
    s = np.asarray(saving, dtype="float64")
    t = np.asarray(ttff, dtype="float64")
    if s.shape != t.shape or s.ndim != 1 or len(s) == 0:
        raise ValueError("saving and ttff must be equal-length, non-empty 1-D arrays")
    if not (np.isfinite(s).all() and np.isfinite(t).all()):
        raise ValueError("frontier points must be finite")
    order = np.lexsort((t, -s))                   # saving descending, then TTFF ascending
    keep_s, keep_t, best = [], [], np.inf
    for i in order:
        if t[i] < best:                           # strictly better TTFF than every higher-saving point
            keep_s.append(s[i])
            keep_t.append(t[i])
            best = t[i]
    return Frontier(saving=np.asarray(keep_s[::-1]), ttff=np.asarray(keep_t[::-1]))


def ttff_at(f: Frontier, s: Any) -> np.ndarray:
    """TTFF p95 on the frontier at saving ``s``; NaN outside its range (no extrapolation)."""
    s = np.asarray(s, dtype="float64")
    out = np.interp(s, f.saving, f.ttff)
    lo, hi = f.saving_range
    return np.where((s >= lo) & (s <= hi), out, np.nan)


def saving_at(f: Frontier, t: Any) -> np.ndarray:
    """Carbon saved on the frontier at TTFF p95 ``t``; NaN outside its range."""
    t = np.asarray(t, dtype="float64")
    out = np.interp(t, f.ttff, f.saving)
    lo, hi = f.ttff_range
    return np.where((t >= lo) & (t <= hi), out, np.nan)


def matched_grid(a: tuple[float, float], b: tuple[float, float],
                 k: int = K_MATCHED) -> np.ndarray:
    """K interior points of the overlap of two ranges; empty if the overlap is degenerate."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if not hi > lo:
        return np.empty(0)
    return np.linspace(lo, hi, k + 2)[1:-1]


def differences(ref: Frontier, trt: Frontier, carbon_grid: np.ndarray,
                ttff_grid: np.ndarray) -> dict[str, np.ndarray]:
    """Absolute and relative differences at fixed matched points (positive favours trt)."""
    t_ref, t_trt = ttff_at(ref, carbon_grid), ttff_at(trt, carbon_grid)
    s_ref, s_trt = saving_at(ref, ttff_grid), saving_at(trt, ttff_grid)
    d_t = t_ref - t_trt
    d_s = s_trt - s_ref
    with np.errstate(divide="ignore", invalid="ignore"):
        rel_t = np.where(t_ref > 0, d_t / t_ref, np.nan)
        rel_s = np.where(s_ref > 0, d_s / s_ref, np.nan)
    return {"ttff_ref": t_ref, "ttff_trt": t_trt, "d_ttff": d_t, "rel_d_ttff": rel_t,
            "saving_ref": s_ref, "saving_trt": s_trt, "d_saving": d_s, "rel_d_saving": rel_s}


def area_between(ref: Frontier, trt: Frontier, n: int = N_AREA) -> float | None:
    """∫ (TTFF_ref(s) − TTFF_trt(s)) ds over the carbon overlap; None if it is degenerate."""
    lo, hi = max(ref.saving[0], trt.saving[0]), min(ref.saving[-1], trt.saving[-1])
    if not hi > lo:
        return None
    s = np.linspace(lo, hi, n)
    y = np.interp(s, ref.saving, ref.ttff) - np.interp(s, trt.saving, trt.ttff)
    return float(np.sum((y[1:] + y[:-1]) * np.diff(s)) / 2.0)


def count_points(point_rel: np.ndarray, ci_lo: np.ndarray, undefined_share: np.ndarray,
                 floor: float) -> np.ndarray:
    """Which matched points count for the treatment under §A1.7 / DL-029 §5, §8."""
    rel = np.asarray(point_rel, dtype="float64")
    lo = np.asarray(ci_lo, dtype="float64")
    und = np.asarray(undefined_share, dtype="float64")
    return (np.nan_to_num(rel, nan=-np.inf) >= floor) & (np.nan_to_num(lo, nan=-np.inf) > 0) \
        & (und <= MAX_UNDEFINED_SHARE)


def decision_condition(carbon_counts: np.ndarray, ttff_counts: np.ndarray,
                       min_points: int = MIN_POINTS) -> bool:
    """§A1.7 decision altitude: ≥ ``min_points`` counting points on at least one axis."""
    return bool(int(np.sum(carbon_counts)) >= min_points or int(np.sum(ttff_counts)) >= min_points)

"""Paired bootstrap over a shared replay trace — `eval_protocol.md` §9, signature §10.

Every strategy is evaluated on the **identical** build trace (spec §4), so a
comparison between two strategies is **paired**: each resample draws one set of
build indices and every strategy's metric is recomputed on that same set. The
signature is the one frozen in §10; the conventions (B = 1000, seed 42, 95%
percentile CI) are §9's and match `scheduler_core.ablation_stats`, which pairs
two model *arms* rather than two *strategies*.

The functions here hold no strategy logic and read no dataset. They take the
per-build records a replay has already produced (DL-028 §5).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from scheduler_core.config import RANDOM_SEED

#: §9's resample count and CI level.
N_RESAMPLES: int = 1000
CI: float = 0.95


class StatsError(ValueError):
    """Raised when the per-build frame cannot be paired."""


def _aligned_frames(per_build: pd.DataFrame, strategies: Sequence[str],
                    key: str) -> dict[str, pd.DataFrame]:
    """One frame per strategy, all in the same build order — or an error."""
    if "strategy" not in per_build.columns or key not in per_build.columns:
        raise StatsError(f"per_build must carry 'strategy' and {key!r} columns")
    if len(set(strategies)) != len(strategies):
        raise StatsError("strategies must be unique")
    frames: dict[str, pd.DataFrame] = {}
    reference: np.ndarray | None = None
    for s in strategies:
        f = per_build.loc[per_build["strategy"] == s].reset_index(drop=True)
        if f.empty:
            raise StatsError(f"no rows for strategy {s!r}")
        keys = f[key].astype(str).to_numpy()
        if len(set(keys)) != len(keys):
            raise StatsError(f"strategy {s!r} has duplicate {key} rows")
        if reference is None:
            reference = keys
        elif not np.array_equal(keys, reference):
            raise StatsError(f"strategy {s!r} is not on the same build trace, in the same "
                             "order, as the first strategy — the comparison would not be paired")
        frames[s] = f
    return frames


def _value(fn: Callable[[pd.DataFrame], Any], frame: pd.DataFrame) -> float:
    v = fn(frame)
    return float("nan") if v is None else float(v)


def paired_bootstrap(
    per_build: pd.DataFrame,
    metric_fns: Mapping[str, Callable[[pd.DataFrame], float]],
    *,
    strategies: Sequence[str],
    n_resamples: int = N_RESAMPLES,
    ci: float = CI,
    seed: int = RANDOM_SEED,
    key: str = "tr_build_id",
) -> dict:
    """Paired bootstrap over the shared build trace (§9).

    ``per_build`` has one row per (build × strategy): a ``strategy`` column, the
    build ``key``, and whatever columns the ``metric_fns`` read. Each function
    takes one strategy's frame (or a resample of it) and returns a float, or
    ``None`` where the metric is undefined (e.g. latency over zero deferrals).

    Point estimates come from the full trace. Each of ``n_resamples`` resamples
    draws the shared build index with replacement **once** and recomputes every
    metric for every strategy on it. Pairwise differences (X − Y, for X before Y
    in ``strategies``) are formed per resample, so their CIs are paired.

    Returns
    -------
    dict
        ``per_strategy[strategy][metric]`` = point + percentile CI;
        ``differences[metric]["X__minus__Y"]`` = point + CI + ``significant``
        (CI excludes 0). Undefined values are ``None``. Deterministic given ``seed``.
    """
    frames = _aligned_frames(per_build, strategies, key)
    n = len(next(iter(frames.values())))
    names = list(metric_fns)
    point = {s: {m: _value(metric_fns[m], frames[s]) for m in names} for s in strategies}

    rng = np.random.default_rng(seed)
    draws = {s: {m: np.empty(n_resamples) for m in names} for s in strategies}
    for b in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        for s in strategies:
            sub = frames[s].iloc[idx]
            for m in names:
                draws[s][m][b] = _value(metric_fns[m], sub)

    lo_q, hi_q = (1.0 - ci) / 2.0, 1.0 - (1.0 - ci) / 2.0

    def summarise(p: float, d: np.ndarray) -> dict[str, Any]:
        finite = d[np.isfinite(d)]
        if not np.isfinite(p) or len(finite) < len(d):
            return {"point": None if not np.isfinite(p) else p, "ci_lo": None, "ci_hi": None,
                    "n_undefined_resamples": int(len(d) - len(finite))}
        return {"point": p, "ci_lo": float(np.quantile(d, lo_q)),
                "ci_hi": float(np.quantile(d, hi_q)), "n_undefined_resamples": 0}

    per_strategy = {s: {m: summarise(point[s][m], draws[s][m]) for m in names}
                    for s in strategies}
    differences: dict[str, dict[str, Any]] = {m: {} for m in names}
    for i, x in enumerate(strategies):
        for y in strategies[i + 1:]:
            for m in names:
                rec = summarise(point[x][m] - point[y][m], draws[x][m] - draws[y][m])
                rec["significant"] = (None if rec["ci_lo"] is None
                                      else bool(rec["ci_lo"] > 0 or rec["ci_hi"] < 0))
                differences[m][f"{x}__minus__{y}"] = rec
    return {"n_builds": int(n), "n_resamples": int(n_resamples), "ci": float(ci),
            "seed": int(seed), "strategies": list(strategies), "metrics": names,
            "per_strategy": per_strategy, "differences": differences}

"""Commit-time duration control ``d̂`` (P1-T4).

Implements ``context/duration_control_spec.md`` exactly. ``d̂`` is the **control
variable** of the study — the null that every SE feature family is tested
against (eval_protocol §A1.3/§A1.4) — so what it may see is a leakage contract,
not a modelling preference.

> The build being decided has not run yet, so its ``tr_duration`` does not exist
> at decision time. Any path that lets it reach ``d̂`` is a leakage defect
> (§A1.2, spec §1).

**Two mechanisms, bound differently** (DL-014, Accepted/Resolved 2026-08-17 —
the *intended deployment information regime*):

1. **Fitted parameters** — the ④a regressor (weights *and* hyperparameters), the
   **language** prior and the **global** prior — are estimated from
   **train-split projects only**. :meth:`DurationEstimator.fit` asserts this
   (test T2b); a calibration or test project in the fitting frame is an error,
   never a silent absorption.
2. **Within-project online state** — ④b's rolling prior — is *strictly causal*
   and is available on **every** split, because it is information a deployed
   scheduler genuinely holds: its own repository's build history to date. The
   admissible window is the builds that had **finished** before the scored
   build arrived, ``gh_build_started_at + tr_duration < t_b`` (**DL-034**, which
   corrects the original start-time-only rule); the scored build, anything
   still running, anything later, and anything **tied** on the timestamp are
   excluded (:func:`causal_project_history`, guarded by
   :func:`assert_history_is_causal`, test T2/T3).

No claim is made here or anywhere downstream about the *direction* of the
residual bias this regime carries (DL-014 §Resolution 5); it is carried as an
open threat in ``duration_control_spec.md`` §8.

Durations never travel on the feature frame. :meth:`fit` takes the target as a
**separate** series precisely so that :func:`features.assert_no_leakage` over the
frame's columns is a meaningful check rather than a formality (test T1).
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

# --------------------------------------------------------------------------- #
# Contract constants — all pinned by duration_control_spec.md before any code
# existed (§4.2). Changing one changes the fitted control and needs a DL entry.
# --------------------------------------------------------------------------- #

#: The fitted target: log(1 + tr_duration_s), at build grain (spec §1, §A1.1).
TARGET_NAME: str = "log1p_duration_s"

#: Seeded random-search budget for both ④a families (spec §4.2).
SEARCH_N_ITER: int = 40

#: Share of train builds, temporally latest, forming the internal-validation
#: fold used for model selection (eval_protocol §3; spec §3.1).
INTERNAL_VAL_SHARE: float = 0.20

#: The cold-start ladder, in order (spec §6.1). Rung 3 is total.
FALLBACK_LEVELS: tuple[str, str, str] = ("project", "language", "global")

#: The two admissible forms (spec §4).
FORMS: tuple[str, str] = ("4a", "4b")

#: ④b's default history window: expanding (all builds finished before t_b).
#: An integer switches to the declared trailing-window sensitivity (spec §6.3.4).
EXPANDING: None = None

#: Which earlier builds a history may read (DL-034). ``"completed"`` — finished
#: strictly before ``t_b`` — is the only rule a real run may use. ``"started"`` is
#: the superseded pre-DL-034 rule (started before ``t_b``, possibly still running),
#: kept solely so tests and the DL-034 diagnostic can reproduce it;
#: :func:`assert_history_is_causal` rejects it whenever builds overlap.
COMPLETED: str = "completed"
AVAILABILITY_RULES: tuple[str, str] = (COMPLETED, "started")

#: Column names the history helper works with (dataset_reference.md spellings).
PROJECT_COL: str = "gh_project_name"
TIME_COL: str = "gh_build_started_at"
DURATION_COL: str = "tr_duration"


class DurationLeakageError(AssertionError):
    """Raised when ``d̂`` would be formed from information not available at
    commit time — a non-train project in the fit (mechanism 1), or a history
    window that admits the scored build, a tie, or the future (mechanism 2)."""


# --------------------------------------------------------------------------- #
# §1.2 — which builds carry a usable training label
# --------------------------------------------------------------------------- #

def usable_label_mask(durations: pd.Series) -> pd.Series:
    """Builds whose ``tr_duration`` can serve as a fitting label (spec §1.2).

    Present and **strictly positive**. Builds failing this are excluded from
    *fitting only* — never from the evaluation population, the replay, or any
    metric denominator.
    """
    v = pd.to_numeric(durations, errors="coerce")
    return v.notna() & (v > 0)


def to_log1p(durations: pd.Series) -> pd.Series:
    """``log(1 + duration_s)`` for usable labels, NaN elsewhere (spec §1)."""
    v = pd.to_numeric(durations, errors="coerce")
    return pd.Series(np.log1p(v.where(usable_label_mask(durations))),
                     index=durations.index, name=TARGET_NAME)


def to_seconds(log1p_values: "pd.Series | np.ndarray") -> np.ndarray:
    """``expm1`` back-transform — the monotone decision scale (spec §1.1).

    Jensen bias is expected and accepted: this estimates a conditional
    median-like quantity, not the conditional mean. Strategy ④'s rule is the
    monotone comparison ``d̂ ≥ d_threshold``, and ``d_threshold`` is fitted on
    the same scale, so a monotone bias is absorbed by the fitted threshold.
    """
    return np.expm1(np.asarray(log1p_values, dtype="float64"))


# --------------------------------------------------------------------------- #
# Mechanism 2 — strictly causal within-project history
# --------------------------------------------------------------------------- #

def causal_project_history(
    frame: pd.DataFrame,
    durations: pd.Series,
    *,
    project_col: str = PROJECT_COL,
    time_col: str = TIME_COL,
    window: int | None = EXPANDING,
    availability: str = COMPLETED,
    strict: bool = True,
) -> pd.DataFrame:
    """Per-build view of the project's build history **as known at** ``t_b``.

    For every row this returns what a deployed scheduler would already know
    about that repository at ``t_b`` and nothing more (DL-034):

    ``n_history``
        count of builds of the same project that carry a usable label (§1.2)
        and had **finished** before ``t_b``:
        ``gh_build_started_at_j + tr_duration_j < t_b``;
    ``hist_median_log1p``
        median of ``log(1 + duration)`` over exactly those builds — the ④b
        estimate (spec §4.1). Order-based, so it is identical to the median of
        raw seconds under the monotone transform.

    **Completion, not start.** A build that started before ``b`` but was still
    running at ``t_b`` has no observed duration yet, so it is excluded. The
    release has no finish timestamp; start + ``tr_duration`` is the *earliest*
    possible finish, which DL-034 declares as the proxy.

    **Ties are excluded.** Builds of the same project sharing ``b``'s exact
    timestamp cannot have finished before ``b`` starts (spec §2), so every row
    of a tie block sees the identical history.

    Parameters
    ----------
    window:
        ``None`` (default) = expanding, the primary form. An integer selects the
        declared trailing-window sensitivity of spec §6.3(4): the ``window``
        most recently **finished** labelled builds. Secondary, never allowed to
        change the primary.
    availability:
        ``"completed"`` (default) is the DL-034 rule and the only one a real run
        may use. ``"started"`` reproduces the superseded start-ordered rule
        (``gh_build_started_at < t_b``) for tests and the DL-034 diagnostic.
    strict:
        ``False`` builds a start-ordered window with ``≤ t_b`` instead of
        ``< t_b``, i.e. it lets the scored build into its own history. **This is
        the deliberately leaky fixture of test T3 and exists only so the tests
        can fail.** It is never used on a real run; :func:`assert_history_is_causal`
        rejects it.
    """
    for col in (project_col, time_col):
        if col not in frame.columns:
            raise KeyError(f"history frame is missing required column {col!r}")
    if len(durations) != len(frame):
        raise ValueError(
            f"durations ({len(durations)}) and frame ({len(frame)}) differ in length"
        )
    if availability not in AVAILABILITY_RULES:
        raise ValueError(f"availability must be one of {AVAILABILITY_RULES}, "
                         f"got {availability!r}")
    if strict and availability == COMPLETED:
        return _completion_ordered_history(frame, durations, project_col=project_col,
                                           time_col=time_col, window=window)
    return _start_ordered_history(frame, durations, project_col=project_col,
                                  time_col=time_col, window=window, strict=strict)


def _epoch_seconds(parsed: pd.Series) -> np.ndarray:
    """UTC timestamps → float seconds since the epoch, independent of the
    datetime unit pandas chose (pandas 3 defaults to microseconds)."""
    return (parsed - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy(
        dtype="float64")


def _completion_ordered_history(frame: pd.DataFrame, durations: pd.Series, *,
                                project_col: str, time_col: str,
                                window: int | None) -> pd.DataFrame:
    """The DL-034 rule: labelled builds with ``start + duration < t_b``."""
    parsed = features.parse_started_at(frame[time_col])
    if parsed.isna().any():
        raise ValueError(
            f"{int(parsed.isna().sum()):,} build(s) have no parseable {time_col!r}; "
            "their history cannot be placed in time (the analytic funnel excludes them)")
    ts = _epoch_seconds(parsed)
    y = to_log1p(pd.Series(np.asarray(durations), index=frame.index)).to_numpy(dtype="float64")
    dur = pd.to_numeric(pd.Series(np.asarray(durations)), errors="coerce").to_numpy(
        dtype="float64")
    end = ts + np.where(np.isnan(y), 0.0, dur)        # only read where y is a label

    codes, _ = pd.factorize(frame[project_col].to_numpy(), use_na_sentinel=False)
    n = len(frame)
    n_hist = np.zeros(n, dtype="int64")
    med = np.full(n, np.nan)
    order = np.argsort(codes, kind="stable")
    sorted_codes = codes[order]
    bounds = np.flatnonzero(np.r_[True, sorted_codes[1:] != sorted_codes[:-1], True])
    for a, b in zip(bounds[:-1], bounds[1:]):
        idx = order[a:b]
        lab = idx[~np.isnan(y[idx])]
        if lab.size == 0:
            continue
        # Order the project's labelled builds by finish time; ties in finish time
        # break on input position, so the trailing window is deterministic.
        by_end = lab[np.lexsort((lab, end[lab]))]
        ends = end[by_end]
        ys = pd.Series(y[by_end])
        prefix = (ys.expanding().median() if window is None
                  else ys.rolling(window, min_periods=1).median()).to_numpy()
        k = np.searchsorted(ends, ts[idx], side="left")     # finished strictly before t_b
        n_hist[idx] = k if window is None else np.minimum(k, window)
        have = k > 0
        med[idx[have]] = prefix[k[have] - 1]
    return pd.DataFrame({"n_history": n_hist, "hist_median_log1p": med}, index=frame.index)


def _start_ordered_history(frame: pd.DataFrame, durations: pd.Series, *,
                           project_col: str, time_col: str, window: int | None,
                           strict: bool) -> pd.DataFrame:
    """The superseded pre-DL-034 rule (``start < t_b``), and the T3 leaky fixture.

    Retained unchanged so the original behaviour stays reproducible; never the
    default, and rejected by :func:`assert_history_is_causal` on overlapping runs.
    """
    parsed = features.parse_started_at(frame[time_col])
    y = to_log1p(pd.Series(np.asarray(durations), index=frame.index))

    work = pd.DataFrame({
        "proj": frame[project_col].to_numpy(),
        "ts": parsed.to_numpy(),
        "y": y.to_numpy(),
    })
    # Stable sort by (project, time): ties keep input order, so the result is
    # deterministic regardless of how the frame was assembled.
    order = np.lexsort((np.arange(len(work)), work["ts"].to_numpy(),
                        work["proj"].to_numpy()))
    s = work.iloc[order].reset_index(drop=True)

    grouped = s.groupby("proj", sort=False)["y"]
    if window is None:
        med = grouped.expanding().median()
        cnt = s["y"].notna().groupby(s["proj"], sort=False).cumsum()
    else:
        med = grouped.rolling(window, min_periods=1).median()
        cnt = (s["y"].notna().astype("float64")
               .groupby(s["proj"], sort=False)
               .rolling(window, min_periods=1).sum())
        cnt = cnt.droplevel(0).sort_index()
    med = med.droplevel(0).sort_index()

    med_arr = med.to_numpy(dtype="float64")
    cnt_arr = np.asarray(cnt, dtype="float64")

    if strict:
        # Step 1: shift one row back **within the project**, so a row never sees
        # itself. Step 2: collapse each (project, timestamp) tie block onto the
        # value that held immediately before the block started.
        med_arr = _shift_within_group(med_arr, s["proj"].to_numpy())
        cnt_arr = _shift_within_group(cnt_arr, s["proj"].to_numpy(), fill=0.0)
        block_start = _block_start_positions(s["proj"].to_numpy(),
                                             s["ts"].to_numpy())
        med_arr = med_arr[block_start]
        cnt_arr = cnt_arr[block_start]

    out = pd.DataFrame(
        {"n_history": cnt_arr.astype("int64"), "hist_median_log1p": med_arr},
        index=s.index,
    )
    # Undo the sort: put rows back on the caller's index, in the caller's order.
    restored = np.empty(len(order), dtype="int64")
    restored[order] = np.arange(len(order))
    out = out.iloc[restored].set_index(frame.index)
    return out


def _shift_within_group(values: np.ndarray, groups: np.ndarray,
                        fill: float = np.nan) -> np.ndarray:
    """Shift ``values`` down one position, resetting at each group boundary."""
    out = np.empty_like(values, dtype="float64")
    out[0] = fill
    out[1:] = values[:-1]
    starts = np.empty(len(groups), dtype=bool)
    starts[0] = True
    starts[1:] = groups[1:] != groups[:-1]
    out[starts] = fill
    return out


def _block_start_positions(groups: np.ndarray, times: np.ndarray) -> np.ndarray:
    """Position of the first row of each ``(group, time)`` block, per row.

    Indexing a shifted array by this makes every member of a tie block read the
    state that held *before* the block — which is what "strictly earlier"
    means when timestamps repeat.
    """
    new_block = np.empty(len(groups), dtype=bool)
    new_block[0] = True
    new_block[1:] = (groups[1:] != groups[:-1]) | (times[1:] != times[:-1])
    starts = np.flatnonzero(new_block)
    return starts[np.cumsum(new_block) - 1]


def assert_history_is_causal(
    frame: pd.DataFrame,
    history: pd.DataFrame,
    durations: pd.Series,
    *,
    project_col: str = PROJECT_COL,
    time_col: str = TIME_COL,
) -> None:
    """Fail if the history window admitted the scored build, a tie, an unfinished
    build, or anything later.

    Three structural invariants:

    1. **Every build in a project's earliest timestamp block has
       ``n_history == 0``** — there is nothing before it, so anything above zero
       means the row counted itself or a same-second sibling (the ``≤ t_b``
       fixture of test T3 violates this).
    2. **``n_history`` is constant within every ``(project, timestamp)``
       block** — tie members are not strictly earlier than one another, so they
       must all see the identical history.
    3. **No build counts more history than had finished by** ``t_b`` (DL-034) —
       ``n_history`` may not exceed the number of the project's labelled builds
       with ``start + duration < t_b``. The superseded start-ordered rule
       violates this wherever runs overlap.

    ``durations`` is required: without it check 3 cannot run, and a history
    guard that cannot see completion is the defect DL-034 corrects.
    """
    if len(history) != len(frame):
        raise ValueError("history and frame differ in length")
    if len(durations) != len(frame):
        raise ValueError("durations and frame differ in length")

    parsed = features.parse_started_at(frame[time_col])
    chk = pd.DataFrame({
        "proj": frame[project_col].to_numpy(),
        "ts": parsed.to_numpy(),
        "n": np.asarray(history["n_history"]),
    })

    first_ts = chk.groupby("proj", sort=False)["ts"].transform("min")
    offenders = chk.loc[(chk["ts"] == first_ts) & (chk["n"] > 0)]
    if not offenders.empty:
        sample = offenders["proj"].drop_duplicates().head(5).tolist()
        raise DurationLeakageError(
            f"{len(offenders):,} build(s) in their project's earliest timestamp "
            f"block have n_history > 0 — the history window is admitting the "
            f"scored build or a tie (spec §2, §3.3). Projects: {sample}"
        )

    spread = chk.groupby(["proj", "ts"], sort=False)["n"].transform("nunique")
    tied = chk.loc[spread > 1]
    if not tied.empty:
        raise DurationLeakageError(
            f"{len(tied):,} build(s) sit in a (project, timestamp) block whose "
            "members disagree on n_history — timestamp-tied builds must all see "
            "the identical strictly-earlier history (spec §2)."
        )

    # Check 3 (DL-034): an upper bound on n_history from finish times alone,
    # computed here independently of how the history frame was produced.
    ts = _epoch_seconds(parsed)
    y = to_log1p(pd.Series(np.asarray(durations), index=frame.index)).to_numpy(dtype="float64")
    dur = pd.to_numeric(pd.Series(np.asarray(durations)), errors="coerce").to_numpy(
        dtype="float64")
    finished = pd.DataFrame({"proj": chk["proj"].to_numpy(),
                             "end": ts + np.where(np.isnan(y), np.nan, dur)}).dropna()
    ends_by_proj = {p: np.sort(g.to_numpy()) for p, g in finished.groupby("proj", sort=False)["end"]}
    bound = np.zeros(len(frame), dtype="int64")
    for p, pos in chk.groupby("proj", sort=False).indices.items():
        ends = ends_by_proj.get(p)
        if ends is not None:
            bound[pos] = np.searchsorted(ends, ts[pos], side="left")
    over = np.asarray(history["n_history"], dtype="int64") > bound
    if over.any():
        sample = chk.loc[over, "proj"].drop_duplicates().head(5).tolist()
        raise DurationLeakageError(
            f"{int(over.sum()):,} build(s) count more history than had finished by t_b — "
            f"the window admits builds that were still running (DL-034). Projects: {sample}"
        )


# --------------------------------------------------------------------------- #
# The estimate a scored build carries (spec §6.2, §10)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DurationEstimate:
    """One build's ``d̂`` plus the provenance the spec requires per build."""

    d_hat_log1p: float
    d_hat_seconds: float
    form: str
    fallback_level: str
    n_history: int
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        """Flat dict for the simulator's per-build output (spec §6.2)."""
        return {
            "d_hat_log1p": self.d_hat_log1p,
            "d_hat_seconds": self.d_hat_seconds,
            "form": self.form,
            "fallback_level": self.fallback_level,
            "n_history": self.n_history,
            "fit_id": self.provenance.get("fit_id"),
            "seed": self.provenance.get("seed"),
            "fit_row_range": self.provenance.get("fit_row_range"),
        }


# --------------------------------------------------------------------------- #
# ④a search space — pinned in duration_control_spec.md §4.2 before any code
# --------------------------------------------------------------------------- #

def sample_xgb_params(rng: np.random.Generator) -> dict[str, Any]:
    """One draw from the §4.2 search space (ranges are the spec's, verbatim)."""
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
    }


def sample_ridge_params(rng: np.random.Generator) -> dict[str, Any]:
    """One draw from the Ridge reference space (§4.2: alpha 1e-3 … 1e3)."""
    return {"alpha": float(np.exp(rng.uniform(np.log(1e-3), np.log(1e3))))}


# --------------------------------------------------------------------------- #
# The estimator
# --------------------------------------------------------------------------- #

class DurationEstimator:
    """Both admissible forms of the duration control, in one fitted object.

    ④a (regressor) and ④b (project prior) are held together because they share
    the cold-start ladder and the same fitted fallback priors, and because
    eval_protocol §A1.6 runs **both** regardless of which one §5 selects as
    primary. ``primary_form`` records that selection; it is set once, from a
    calibration-split MAE comparison, and is frozen before P3.
    """

    def __init__(self, *, seed: int = RANDOM_SEED,
                 n_iter: int = SEARCH_N_ITER, verbose: bool = False) -> None:
        self.seed = int(seed)
        self.n_iter = int(n_iter)
        self.verbose = bool(verbose)

        self.fitted: bool = False
        self.primary_form: str | None = None

        self.lang_levels: tuple[str, ...] = ()
        self.design_columns: tuple[str, ...] = ()
        self.language_prior_log1p: dict[str, float] = {}
        self.global_prior_log1p: float = float("nan")

        self.xgb_model: Any = None
        self.ridge_model: Any = None
        self.xgb_best_params: dict[str, Any] = {}
        self.ridge_best_params: dict[str, Any] = {}
        self.search_trace: list[dict[str, Any]] = []
        self.provenance: dict[str, Any] = {}

    # -- mechanism 1: fitting ------------------------------------------------ #

    def fit(
        self,
        feature_frame: pd.DataFrame,
        durations: pd.Series,
        *,
        split_assignment: Mapping[str, str],
        project_col: str = PROJECT_COL,
        time_col: str = TIME_COL,
    ) -> "DurationEstimator":
        """Fit every **mechanism-1** parameter on train-split projects only.

        ``feature_frame`` is a :func:`features.build_feature_matrix` output
        (28 features + keys). ``durations`` is the observed ``tr_duration`` of
        those same builds, passed **separately** — it is eval_protocol §A1.2
        role 2 (historical training label) and must never ride on the frame.

        Raises :class:`DurationLeakageError` if any project in ``feature_frame``
        is not assigned to ``train`` (test **T2b**), or
        :class:`features.LeakageError` if a blocklisted column reached the frame
        (test **T1**).
        """
        features.assert_no_leakage(columns=feature_frame.columns)
        self._assert_train_only(feature_frame, split_assignment,
                                project_col=project_col)

        durations = pd.Series(np.asarray(durations), index=feature_frame.index)
        y_all = to_log1p(durations)
        usable = y_all.notna()
        if not usable.any():
            raise ValueError("no build in the fitting frame carries a usable "
                             "duration label (spec §1.2)")

        frame = feature_frame.loc[usable]
        y = y_all.loc[usable]

        # Fitted parameters see the whole train period; time-ordering is still
        # preserved *inside* the fit for model selection (spec §3.1).
        started = features.parse_started_at(frame[time_col])
        order = np.lexsort((np.arange(len(frame)), started.to_numpy()))
        frame = frame.iloc[order]
        y = y.iloc[order]
        started = started.iloc[order]

        self.lang_levels = tuple(sorted(
            v for v in pd.unique(frame["lang"].dropna()) if isinstance(v, str)
        ))

        # -- rungs 2 and 3 of the ladder: fitted priors (mechanism 1, §6.1) --
        lang = frame["lang"]
        self.language_prior_log1p = {
            str(level): float(y.loc[(lang == level).to_numpy()].median())
            for level in self.lang_levels
        }
        self.global_prior_log1p = float(y.median())

        # -- ④a: seeded random search on the temporal internal-validation fold -
        design = self.design_matrix(frame)
        self.design_columns = tuple(design.columns)
        n_val = max(1, int(round(INTERNAL_VAL_SHARE * len(design))))
        n_fit = len(design) - n_val
        if n_fit < 1:
            raise ValueError("fitting frame too small to form an internal-"
                             "validation fold")
        x_fit, x_val = design.iloc[:n_fit], design.iloc[n_fit:]
        y_fit, y_val = y.iloc[:n_fit], y.iloc[n_fit:]

        self.search_trace = []
        self.xgb_model, self.xgb_best_params = self._search_xgb(
            x_fit, y_fit, x_val, y_val, design, y)
        self.ridge_model, self.ridge_best_params = self._search_ridge(
            x_fit, y_fit, x_val, y_val, design, y)

        self.fitted = True
        self.provenance = {
            "fit_id": "",  # filled below, once the config is complete
            "seed": self.seed,
            "split": "train",
            "n_fit_builds": int(len(design)),
            "n_fit_projects": int(frame[project_col].nunique()),
            "n_builds_offered": int(len(feature_frame)),
            "n_builds_unusable_label": int((~usable).sum()),
            "fit_row_range": {
                "first_build": str(started.min()),
                "last_build": str(started.max()),
            },
            "internal_validation": {
                "share": INTERNAL_VAL_SHARE,
                "n_fit": int(n_fit),
                "n_val": int(n_val),
                "rule": "temporally-latest 20% of train builds by "
                        "gh_build_started_at (eval_protocol §3, spec §3.1)",
                "selection_metric": "MAE on log1p scale (spec §4.2)",
            },
            "final_refit": "the selected configuration is refit on 100% of the "
                           "usable train builds; the search itself never saw the "
                           "internal-validation fold (spec §3.1)",
            "target": TARGET_NAME,
            "n_search_candidates": self.n_iter,
            "lang_levels": list(self.lang_levels),
            "design_columns": list(self.design_columns),
            "xgb_best_params": self.xgb_best_params,
            "ridge_best_params": self.ridge_best_params,
            "library_versions": library_versions(),
            "mechanism": "1 — fitted parameters, train projects only "
                         "(DL-014 §Resolution 1)",
        }
        self.provenance["fit_id"] = self._fit_id()
        return self

    def _assert_train_only(self, frame: pd.DataFrame,
                           split_assignment: Mapping[str, str], *,
                           project_col: str) -> None:
        """Test **T2b** — a calibration/test project may not enter the fit."""
        if project_col not in frame.columns:
            raise KeyError(
                f"fitting frame must carry {project_col!r} so the split can be "
                "checked — fitting on an unidentifiable frame is not permitted"
            )
        projects = pd.unique(frame[project_col])
        unknown = [p for p in projects if p not in split_assignment]
        if unknown:
            raise DurationLeakageError(
                f"{len(unknown)} project(s) in the fitting frame are absent from "
                f"the frozen split assignment — cannot prove they are train "
                f"projects: {sorted(unknown)[:5]}"
            )
        offenders = sorted({str(p) for p in projects
                            if split_assignment[p] != "train"})
        if offenders:
            raise DurationLeakageError(
                f"{len(offenders)} non-train project(s) reached the fitting "
                f"frame — mechanism-1 parameters are fitted on train projects "
                f"only (eval_protocol §A1.1, DL-014 §Resolution 1): "
                f"{offenders[:5]}"
            )

    def design_matrix(self, feature_frame: pd.DataFrame) -> pd.DataFrame:
        """The 28-feature contract as a numeric matrix: 27 numeric + one-hot lang.

        ``lang`` is one-hot encoded from the **levels observed in the train
        split**; an unseen or missing level encodes as all-zeros (spec §4.2) and
        is counted in the coverage table. The rolling project prior is
        deliberately **not** added as a 29th input — keeping ④a and ④b
        mechanically distinct is what makes the comparison interpretable.
        """
        features.assert_no_leakage(columns=feature_frame.columns)
        missing = [f for f in features.FEATURES if f not in feature_frame.columns]
        if missing:
            raise KeyError(f"feature frame is missing features: {missing}")

        numeric = [f for f in features.FEATURES
                   if f not in features.CATEGORICAL_FEATURES]
        out = feature_frame[numeric].apply(pd.to_numeric, errors="coerce")
        out = out.astype("float64")

        lang = feature_frame["lang"].astype("string")
        for level in self.lang_levels:
            out[f"lang={level}"] = (lang == level).astype("float64").to_numpy()
        if self.design_columns:
            out = out[list(self.design_columns)]
        return out

    def _search_xgb(self, x_fit, y_fit, x_val, y_val, x_all, y_all):
        from xgboost import XGBRegressor

        rng = np.random.default_rng(self.seed)
        best: tuple[float, dict[str, Any]] | None = None
        for i in range(self.n_iter):
            params = sample_xgb_params(rng)
            model = XGBRegressor(
                objective="reg:squarederror",
                random_state=self.seed,
                n_jobs=-1,
                tree_method="hist",
                **params,
            )
            model.fit(x_fit, y_fit)
            mae = float(np.mean(np.abs(model.predict(x_val) - y_val.to_numpy())))
            self.search_trace.append(
                {"family": "xgboost", "candidate": i, "params": params,
                 "internal_val_mae_log1p": mae})
            if best is None or mae < best[0]:
                best = (mae, params)
            self._log(f"    xgboost {i + 1:>2}/{self.n_iter}  "
                      f"val MAE {mae:.6f}  best {best[0]:.6f}")

        assert best is not None
        final = XGBRegressor(
            objective="reg:squarederror", random_state=self.seed, n_jobs=-1,
            tree_method="hist", **best[1],
        )
        final.fit(x_all, y_all)
        return final, {**best[1], "internal_val_mae_log1p": best[0]}

    def _search_ridge(self, x_fit, y_fit, x_val, y_val, x_all, y_all):
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        def build(alpha: float) -> Any:
            # Median imputation with train-split medians only, fitted as part of
            # the model and persisted with it (spec §4.2).
            return Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=alpha, random_state=None)),
            ])

        rng = np.random.default_rng(self.seed)
        best: tuple[float, dict[str, Any]] | None = None
        for i in range(self.n_iter):
            params = sample_ridge_params(rng)
            model = build(params["alpha"])
            model.fit(x_fit, y_fit)
            mae = float(np.mean(np.abs(model.predict(x_val) - y_val.to_numpy())))
            self.search_trace.append(
                {"family": "ridge", "candidate": i, "params": params,
                 "internal_val_mae_log1p": mae})
            if best is None or mae < best[0]:
                best = (mae, params)
            self._log(f"    ridge   {i + 1:>2}/{self.n_iter}  "
                      f"val MAE {mae:.6f}  best {best[0]:.6f}")

        assert best is not None
        final = build(best[1]["alpha"])
        final.fit(x_all, y_all)
        return final, {**best[1], "internal_val_mae_log1p": best[0]}

    def _fit_id(self) -> str:
        """Stable digest over everything that determines the fitted control."""
        payload = json.dumps({
            "seed": self.seed,
            "n_iter": self.n_iter,
            "target": TARGET_NAME,
            "features": list(features.FEATURES),
            "design_columns": list(self.design_columns),
            "lang_levels": list(self.lang_levels),
            "xgb": self.xgb_best_params,
            "ridge": self.ridge_best_params,
            "global_prior": self.global_prior_log1p,
            "language_prior": self.language_prior_log1p,
            "fit_row_range": self.provenance.get("fit_row_range"),
            "n_fit_builds": self.provenance.get("n_fit_builds"),
        }, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    # -- scoring ------------------------------------------------------------- #

    def _log(self, message: str) -> None:
        """Progress output for the long real fit; silent by default."""
        if self.verbose:
            print(message, flush=True)

    def _require_fitted(self) -> None:
        if not self.fitted:
            raise RuntimeError("estimator is not fitted — call fit() first")

    def _prior_for(self, lang_values: pd.Series) -> np.ndarray:
        """Rung-2 language prior, falling to rung 3 where the level is unknown."""
        mapped = lang_values.astype("string").map(self.language_prior_log1p)
        return pd.to_numeric(mapped, errors="coerce").to_numpy(dtype="float64")

    def predict_4b(
        self,
        feature_frame: pd.DataFrame,
        history: pd.DataFrame,
        *,
        min_history: int = 1,
    ) -> pd.DataFrame:
        """④b — the project/language historical prior (spec §4.1).

        Rung 1 is the project's own causal median; where the project has fewer
        than ``min_history`` admissible earlier builds the ladder falls to the
        language prior and then the global prior (spec §6.1).

        ``min_history`` defaults to **1** — A1.1's literal *"a project with no
        admissible earlier build"*. Values of 5 and 20 are the declared
        sensitivities of spec §6.3(4) and are secondary by construction.
        """
        self._require_fitted()
        n_hist = np.asarray(history["n_history"], dtype="int64")
        project = np.asarray(history["hist_median_log1p"], dtype="float64")

        have_project = (n_hist >= int(min_history)) & np.isfinite(project)
        language = self._prior_for(feature_frame["lang"])
        have_language = np.isfinite(language)

        level = np.where(have_project, "project",
                         np.where(have_language, "language", "global"))
        value = np.where(have_project, project,
                         np.where(have_language, language,
                                  self.global_prior_log1p))
        return self._package(value, level, n_hist, form="4b",
                             index=feature_frame.index)

    def predict_4a(
        self,
        feature_frame: pd.DataFrame,
        history: pd.DataFrame | None = None,
        *,
        regressor: str = "xgboost",
    ) -> pd.DataFrame:
        """④a — the commit-time regressor over the 28 features (spec §4.2).

        The regressor is total over the feature contract, so the ladder engages
        only where §6.1 says it can: an **unseen ``lang`` level**, or a **wholly
        missing feature row**. Both are still evaluated and recorded so the two
        forms stay directly comparable.

        ``regressor="ridge"`` returns the transparency reference of §4.2. It is
        reported alongside XGBoost and is **not** eligible to become the primary
        control.
        """
        self._require_fitted()
        if regressor not in ("xgboost", "ridge"):
            raise ValueError(f"unknown regressor {regressor!r}")
        model = self.xgb_model if regressor == "xgboost" else self.ridge_model

        design = self.design_matrix(feature_frame)
        predicted = np.asarray(model.predict(design), dtype="float64")

        lang = feature_frame["lang"].astype("string")
        lang_seen = lang.isin(self.lang_levels).to_numpy()
        # "Wholly missing feature row" is judged on the *numeric* features only:
        # the one-hot lang columns are 0/1 by construction and are never NaN, so
        # including them would make §6.1's second trigger unreachable.
        numeric = [c for c in design.columns if not c.startswith("lang=")]
        all_missing = design[numeric].isna().all(axis=1).to_numpy()

        usable = lang_seen & ~all_missing & np.isfinite(predicted)
        language = self._prior_for(lang)
        have_language = np.isfinite(language)

        level = np.where(usable, "project",
                         np.where(have_language, "language", "global"))
        value = np.where(usable, predicted,
                         np.where(have_language, language,
                                  self.global_prior_log1p))
        n_hist = (np.zeros(len(feature_frame), dtype="int64") if history is None
                  else np.asarray(history["n_history"], dtype="int64"))
        return self._package(value, level, n_hist, form="4a",
                             index=feature_frame.index)

    def _package(self, value: np.ndarray, level: np.ndarray, n_hist: np.ndarray,
                 *, form: str, index: pd.Index) -> pd.DataFrame:
        """Assemble the §6.2 per-build provenance record for a batch."""
        value = np.asarray(value, dtype="float64")
        if not np.isfinite(value).all():
            raise ValueError(
                "d̂ is not finite for every build — rung 3 (the global prior) is "
                "total by construction, so a non-finite estimate means the fit "
                "is incomplete (spec §6.1, test T5)"
            )
        return pd.DataFrame({
            "d_hat_log1p": value,
            "d_hat_seconds": to_seconds(value),
            "form": form,
            "fallback_level": level,
            "n_history": n_hist,
            "fit_id": self.provenance.get("fit_id"),
            "seed": self.seed,
        }, index=index)

    def expected(
        self,
        build: "Mapping[str, Any] | pd.Series",
        *,
        history: "Mapping[str, Any] | None" = None,
        form: str | None = None,
    ) -> DurationEstimate:
        """``d̂`` for a single build — the §10 interface the simulator calls.

        ``build`` carries the build's commit-time features; ``history`` carries
        ``{"n_history", "hist_median_log1p"}`` for that build's **strictly
        earlier** project history (:func:`causal_project_history`). There is no
        route from here to the build's own duration: it is not an argument.
        """
        self._require_fitted()
        form = form or self.primary_form
        if form not in FORMS:
            raise ValueError(
                "no form selected — pass form=, or set primary_form from the "
                "calibration-split MAE comparison (spec §5)"
            )
        row = pd.DataFrame([dict(build)])
        hist = pd.DataFrame([{
            "n_history": 0 if history is None else int(history["n_history"]),
            "hist_median_log1p": (float("nan") if history is None
                                  else float(history["hist_median_log1p"])),
        }])
        out = (self.predict_4b(row, hist) if form == "4b"
               else self.predict_4a(row, hist))
        r = out.iloc[0]
        return DurationEstimate(
            d_hat_log1p=float(r["d_hat_log1p"]),
            d_hat_seconds=float(r["d_hat_seconds"]),
            form=str(r["form"]),
            fallback_level=str(r["fallback_level"]),
            n_history=int(r["n_history"]),
            provenance=dict(self.provenance),
        )

    # -- persistence (test T4) ------------------------------------------------ #

    def save(self, path: "str | Path") -> Path:
        """Persist everything needed to reproduce ``d̂`` exactly (R8, test T4)."""
        self._require_fitted()
        import joblib

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: "str | Path") -> "DurationEstimator":
        """Reload a persisted estimator."""
        import joblib

        obj = joblib.load(Path(path))
        if not isinstance(obj, DurationEstimator):
            raise TypeError(f"{path} does not hold a DurationEstimator")
        return obj


def library_versions() -> dict[str, str]:
    """Versions of everything that can move a fitted number (R8)."""
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
# Quality of the control (spec §6.3(1)) — reporting only
# --------------------------------------------------------------------------- #

def score_quality(estimates: pd.DataFrame, durations: pd.Series) -> dict[str, Any]:
    """MAE, median AE (both scales) and Spearman ρ against observed duration.

    Reporting only: observed duration is eval_protocol §A1.2 **role 1**
    (accounting) here — it measures the control after the fact and never enters
    it. Builds without a usable label are excluded from the metrics and counted.
    """
    durations = pd.Series(np.asarray(durations), index=estimates.index)
    usable = usable_label_mask(durations)
    n_all = int(len(estimates))
    if not usable.any():
        return {"n": 0, "n_excluded_no_label": n_all}

    y = to_log1p(durations).loc[usable].to_numpy(dtype="float64")
    yhat = estimates.loc[usable, "d_hat_log1p"].to_numpy(dtype="float64")
    secs = pd.to_numeric(durations.loc[usable], errors="coerce").to_numpy(dtype="float64")
    secs_hat = estimates.loc[usable, "d_hat_seconds"].to_numpy(dtype="float64")

    err_log = np.abs(yhat - y)
    err_sec = np.abs(secs_hat - secs)
    rho = pd.Series(yhat).corr(pd.Series(y), method="spearman")
    return {
        "n": int(usable.sum()),
        "n_excluded_no_label": int(n_all - int(usable.sum())),
        "mae_log1p": float(np.mean(err_log)),
        "median_ae_log1p": float(np.median(err_log)),
        "mae_seconds": float(np.mean(err_sec)),
        "median_ae_seconds": float(np.median(err_sec)),
        "spearman_rho": float(rho) if pd.notna(rho) else None,
    }


def coverage_table(estimates: pd.DataFrame) -> dict[str, Any]:
    """Cold-start coverage: share of builds at each rung, plus ``n_history``."""
    counts = estimates["fallback_level"].value_counts()
    n = int(len(estimates))
    hist = pd.to_numeric(estimates["n_history"], errors="coerce").dropna()
    return {
        "n_builds": n,
        "levels": {
            level: {
                "n": int(counts.get(level, 0)),
                "pct": round(100 * int(counts.get(level, 0)) / n, 4) if n else None,
            }
            for level in FALLBACK_LEVELS
        },
        "n_history": {
            "min": int(hist.min()) if len(hist) else None,
            "p25": float(np.percentile(hist, 25)) if len(hist) else None,
            "p50": float(np.percentile(hist, 50)) if len(hist) else None,
            "p75": float(np.percentile(hist, 75)) if len(hist) else None,
            "p95": float(np.percentile(hist, 95)) if len(hist) else None,
            "max": int(hist.max()) if len(hist) else None,
            "zero": int((hist == 0).sum()) if len(hist) else None,
        },
    }


def choose_primary_form(mae_4a: float, mae_4b: float, *, decimals: int = 4) -> str:
    """The §5 selection rule, applied to two calibration-split log1p MAEs.

    Lower MAE wins. **Ties** — equal to ``decimals`` decimal places — resolve to
    ④b, the simpler and parameter-free form. No expectation about which form
    wins is recorded anywhere in advance, including here.
    """
    if round(float(mae_4a), decimals) == round(float(mae_4b), decimals):
        return "4b"
    return "4a" if float(mae_4a) < float(mae_4b) else "4b"

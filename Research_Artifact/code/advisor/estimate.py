"""``d̂`` for a live run, through the frozen estimator's own code path (invariant 5, R3-B3).

Nothing is re-implemented here. Admitted history runs and the scored run are laid
out as the build-grain frame ``causal_project_history`` expects (project key,
start time, duration); the scored run carries no duration. The frozen function
then applies the DL-034 completion rule, and ``predict_4b`` applies the
project → language → global ladder with ``min_history=1``, exactly as evaluated.

Construct mapping, declared (R3-B4): "project" is the (repository, workflow)
pair; a history run's start is ``run_started_at`` and its duration its run time;
the scored run's time is its arrival.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import numpy as np
import pandas as pd

from scheduler_core import duration_estimator as de
from scheduler_core import features

from .history import HistoryRun


@dataclass(frozen=True)
class DHat:
    seconds: float
    log1p: float
    rung: str            # project | language | global
    n_history: int


def _stamp(moment: datetime) -> str:
    # The estimator parses this exact format (features.TIMESTAMP_FORMAT, UTC).
    return moment.strftime(features.TIMESTAMP_FORMAT)


def language_level(estimator: de.DurationEstimator, repo_language: str | None) -> str | None:
    """Match GitHub's language name to a fitted language level, case-insensitively."""
    if not repo_language:
        return None
    wanted = repo_language.strip().lower()
    for level in estimator.lang_levels:
        if level.lower() == wanted:
            return level
    return None


def estimate_d_hat(
    estimator: de.DurationEstimator,
    admitted: Sequence[HistoryRun],
    *,
    arrival: datetime,
    project_key: str,
    repo_language: str | None,
) -> DHat:
    """``d̂`` for one run arriving at ``arrival``, from its admitted completed history."""
    starts = [_stamp(run.run_started_at) for run in admitted] + [_stamp(arrival)]
    durations = [run.duration_s for run in admitted] + [np.nan]
    frame = pd.DataFrame({de.PROJECT_COL: [project_key] * len(starts), de.TIME_COL: starts})
    history = de.causal_project_history(frame, pd.Series(durations, dtype="float64"),
                                        availability=de.COMPLETED)
    scored = history.iloc[[-1]].reset_index(drop=True)
    features_row = pd.DataFrame({"lang": [language_level(estimator, repo_language)]})
    out = estimator.predict_4b(features_row, scored, min_history=1).iloc[0]
    return DHat(seconds=float(out["d_hat_seconds"]), log1p=float(out["d_hat_log1p"]),
                rung=str(out["fallback_level"]), n_history=int(out["n_history"]))

"""Completed-run history: the entry schema and the admissibility filter (R3-B4, DL-034).

A history run may inform ``d̂`` only if a deployed scheduler would genuinely
know its duration when the scored run arrived: it has **completed**, with a
usable conclusion, in the same workflow, and it **finished before** the arrival.
The frozen ``causal_project_history`` re-applies the completion rule on its own;
this filter is the stricter live gate in front of it (it also requires
``updated_at`` to precede the arrival), so the two can only agree or exclude more.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from .contract import parse_utc

ADMITTED_CONCLUSIONS: tuple[str, ...] = ("success", "failure")
DURATION_SOURCES: tuple[str, ...] = ("wallclock", "timing")
_ENTRY_KEYS = {"run_id", "workflow", "status", "conclusion", "created_at", "run_started_at",
               "updated_at", "duration_s", "duration_source"}
_REQUIRED_KEYS = _ENTRY_KEYS - {"created_at", "duration_source"}


class HistoryError(RuntimeError):
    """History could not be obtained or is malformed. Always `history_unavailable`."""

    code = "history_unavailable"


@dataclass(frozen=True)
class HistoryRun:
    run_id: int
    workflow: str
    status: str
    conclusion: str | None
    run_started_at: datetime
    updated_at: datetime
    duration_s: float
    duration_source: str = "wallclock"

    @property
    def finished_at(self) -> datetime:
        """The later of GitHub's ``updated_at`` and start + duration — the conservative finish."""
        return max(self.updated_at, self.run_started_at + timedelta(seconds=self.duration_s))


def parse_history_entry(raw: Mapping[str, Any]) -> HistoryRun:
    """Validate one history entry (closed schema). Raises :class:`HistoryError`."""
    if not isinstance(raw, Mapping):
        raise HistoryError("history entry must be an object")
    keys = set(map(str, raw))
    unknown = sorted(keys - _ENTRY_KEYS)
    if unknown:
        raise HistoryError(f"history entry has unknown field(s) {unknown}")
    missing = sorted(k for k in _REQUIRED_KEYS if raw.get(k) is None and k != "conclusion")
    if missing:
        raise HistoryError(f"history entry is missing {missing}")
    run_id = raw["run_id"]
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise HistoryError("history run_id must be an integer >= 1")
    for key in ("workflow", "status"):
        if not isinstance(raw[key], str):
            raise HistoryError(f"history {key} must be a string")
    conclusion = raw.get("conclusion")
    if conclusion is not None and not isinstance(conclusion, str):
        raise HistoryError("history conclusion must be a string or null")
    duration = raw["duration_s"]
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration != duration:
        raise HistoryError("history duration_s must be a number")
    source = raw.get("duration_source", "wallclock")
    if source not in DURATION_SOURCES:
        raise HistoryError(f"history duration_source must be one of {DURATION_SOURCES}")
    try:
        started = parse_utc(raw["run_started_at"], "run_started_at")
        updated = parse_utc(raw["updated_at"], "updated_at")
    except ValueError as exc:
        raise HistoryError(str(exc)) from exc
    return HistoryRun(run_id=run_id, workflow=raw["workflow"], status=raw["status"],
                      conclusion=conclusion, run_started_at=started, updated_at=updated,
                      duration_s=float(duration), duration_source=source)


def parse_history(entries: Iterable[Mapping[str, Any]]) -> list[HistoryRun]:
    return [parse_history_entry(e) for e in entries]


def filter_admissible(
    runs: Iterable[HistoryRun],
    *,
    workflow: str,
    run_id: int | None,
    arrival: datetime,
) -> tuple[list[HistoryRun], Counter]:
    """Keep the runs a deployed scheduler would know about at ``arrival``.

    Returns ``(admitted, dropped)`` where ``dropped`` counts each excluded run
    under the first rule it fails, in this order.
    """
    admitted: list[HistoryRun] = []
    dropped: Counter = Counter()
    for run in runs:
        if run.status != "completed":
            dropped["not_completed"] += 1
        elif run.conclusion not in ADMITTED_CONCLUSIONS:
            dropped["conclusion_excluded"] += 1
        elif run.workflow != workflow:
            dropped["other_workflow"] += 1
        elif run_id is not None and run.run_id == run_id:
            dropped["same_run"] += 1
        elif run.duration_s <= 0:
            dropped["nonpositive_duration"] += 1
        elif not run.finished_at < arrival:
            dropped["finished_after_arrival"] += 1
        else:
            admitted.append(run)
    return admitted, dropped

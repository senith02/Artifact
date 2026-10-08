"""Shared builders for the P4 advisor tests. Offline: no network, hand-made history."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from advisor.config import parse_team_config
from advisor.core import Dependencies
from advisor.frozen import default_frozen_core

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "p4"

#: A fixed clock. Thu 2026-10-01 18:05 UTC sits in a GB evening peak, so an
#: eligible long run finds a greener slot within 24 h (illustrative inputs only).
NOW = datetime(2026, 10, 1, 18, 30, tzinfo=timezone.utc)
ARRIVAL = "2026-10-01T18:05:00Z"
SHA = "0123456789abcdef0123456789abcdef01234567"


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def history(n: int = 12, *, duration: float = 870.0, workflow: str = "ci.yml",
            end: datetime = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)) -> list[dict[str, Any]]:
    """`n` completed runs of `workflow`, finished well before ARRIVAL."""
    out = []
    for i in range(n):
        start = end - timedelta(hours=6 * (n - i))
        out.append({"run_id": 1000 + i, "workflow": workflow, "status": "completed",
                    "conclusion": "failure" if i % 4 == 0 else "success",
                    "created_at": iso(start), "run_started_at": iso(start),
                    "updated_at": iso(start + timedelta(seconds=duration)),
                    "duration_s": float(duration), "duration_source": "wallclock"})
    return out


def request(**overrides: Any) -> dict[str, Any]:
    base = {"repository": "demo-owner/demo-repo", "workflow": "ci.yml", "event": "push",
            "ref_type": "branch", "branch": "feature/login-cache", "is_pr": False,
            "arrival_utc": ARRIVAL, "compute_region": "GB", "head_sha": SHA, "run_id": 2000,
            "run_attempt": 1, "history": history()}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def config(**overrides: Any):
    raw = {"compute_region": "GB", "enabled_workflows": ["ci.yml"]}
    raw.update(overrides)
    return parse_team_config(raw)


def deps(**overrides: Any) -> Dependencies:
    d = Dependencies(load_frozen=default_frozen_core, now=lambda: NOW)
    for key, value in overrides.items():
        setattr(d, key, value)
    return d


class FakeResponse(io.BytesIO):
    def __init__(self, payload: Any) -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        super().__init__(body)


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

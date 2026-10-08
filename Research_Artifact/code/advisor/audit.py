"""Append-only JSON Lines audit log, with idempotency by run key (DL-033 R3-C9).

Each record carries the full response, the validated inputs (never a token,
actor or email), and ``gh_is_pr`` / ``git_branch`` / ``action`` under the names
``replay/validate_invariants.py`` audits, so the independent validator can be
run over a decision log exactly as over the replay records.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .config import TeamConfig
from .contract import parse_request
from .core import Dependencies, advise

#: Request fields copied into the audit record. `history` is summarised, not copied.
_LOGGED_INPUTS = ("repository", "workflow", "event", "ref_type", "branch", "is_pr", "arrival_utc",
                  "compute_region", "scenario", "deadline_utc", "head_sha", "run_id", "run_attempt",
                  "redispatch_key", "repo_language")


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def find(self, key: str) -> dict[str, Any] | None:
        for record in reversed(self.records()):
            if record.get("idempotency_key") == key and not record.get("duplicate"):
                return record
        return None

    def append(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def audit_record(raw_request: Any, response: Mapping[str, Any], *, key: str | None,
                 duplicate: bool, now: datetime) -> dict[str, Any]:
    raw = raw_request if isinstance(raw_request, Mapping) else {}
    inputs = {k: raw.get(k) for k in _LOGGED_INPUTS if k in raw}
    if isinstance(raw.get("history"), list):
        inputs["history_entries"] = len(raw["history"])
    return {
        **dict(response),
        "audit_ts": now.astimezone(timezone.utc).isoformat(),
        "idempotency_key": key,
        "duplicate": duplicate,
        "inputs": inputs,
        # validate_invariants.py columns
        "gh_is_pr": raw.get("is_pr"),
        "git_branch": raw.get("branch"),
    }


def advise_with_audit(raw_request: Any, config: TeamConfig | Exception | None, deps: Dependencies,
                      log: AuditLog | None) -> dict[str, Any]:
    """:func:`advise`, plus idempotency and one appended audit record.

    A request whose key (repository, workflow, head_sha, run_attempt) was
    already decided gets the earlier decision back, marked ``duplicate: true``,
    and creates no second deferral.
    """
    now = deps.now()
    key = None
    try:
        key = parse_request(raw_request, now=now).idempotency_key()
    except Exception:
        key = None
    if log is not None and key is not None:
        previous = log.find(key)
        if previous is not None:
            response = {k: v for k, v in previous.items()
                        if k not in ("audit_ts", "idempotency_key", "duplicate", "inputs", "gh_is_pr", "git_branch")}
            response["duplicate"] = True
            log.append(audit_record(raw_request, response, key=key, duplicate=True, now=now))
            return response
    response = advise(raw_request, config, deps)
    response["duplicate"] = False
    if log is not None:
        log.append(audit_record(raw_request, response, key=key, duplicate=False, now=now))
    return response

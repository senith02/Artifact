"""A minimal, standard-library GitHub REST client for completed-run history (DL-035 §1, §3b).

- Read-only; the token needs only ``actions: read`` (``contents: read`` for private repositories).
- Paginated (100 per page) up to an explicit cap; rate-limit aware: it honours ``Retry-After``
  and ``X-RateLimit-Reset`` within a bounded wait, and otherwise gives up.
- The token is sent as a header and never appears in an error message or a log line.

Endpoint shapes were re-verified against real responses on 2026-10-04
(``results/p4/endpoint_check/``).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterator, Mapping

from .contract import parse_utc
from .history import HistoryError

API_ROOT = "https://api.github.com"
PER_PAGE = 100

Opener = Callable[[urllib.request.Request, float], Any]


def _default_opener(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed https host


class GitHubClient:
    """Fetches completed workflow runs. Errors surface as :class:`HistoryError`."""

    def __init__(
        self,
        token: str | None = None,
        *,
        opener: Opener = _default_opener,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        timeout: float = 10.0,
        max_attempts: int = 3,
        max_wait_s: float = 30.0,
    ) -> None:
        self._token = token
        self._opener = opener
        self._sleep = sleep
        self._clock = clock
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._max_wait_s = max_wait_s
        self.requests_made = 0

    # -- transport ------------------------------------------------------------ #

    def _request(self, path: str, params: Mapping[str, Any] | None = None) -> urllib.request.Request:
        url = API_ROOT + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "carbon-deferral-advisor"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return urllib.request.Request(url, headers=headers, method="GET")

    def _wait_for(self, headers: Mapping[str, str] | None, attempt: int) -> float:
        headers = headers or {}
        retry_after = headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        if headers.get("X-RateLimit-Remaining") == "0" and headers.get("X-RateLimit-Reset"):
            try:
                return max(0.0, float(headers["X-RateLimit-Reset"]) - self._clock())
            except ValueError:
                pass
        return float(2 ** attempt)

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        last = "no attempt made"
        for attempt in range(self._max_attempts):
            self.requests_made += 1
            try:
                with self._opener(self._request(path, params), self._timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                status, headers = exc.code, exc.headers
                rate_limited = status == 429 or (status == 403 and headers is not None
                                                 and headers.get("X-RateLimit-Remaining") == "0")
                if not (rate_limited or status >= 500):
                    raise HistoryError(f"GitHub API returned HTTP {status} for {path}") from None
                last = f"HTTP {status}" + (" (rate limited)" if rate_limited else "")
                wait = self._wait_for(headers, attempt)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                last = type(exc).__name__
                wait = float(2 ** attempt)
            if attempt == self._max_attempts - 1:
                break
            if wait > self._max_wait_s:
                raise HistoryError(f"GitHub API {last} for {path}; retry would wait {wait:.0f}s, "
                                   f"over the {self._max_wait_s:.0f}s limit")
            self._sleep(wait)
        raise HistoryError(f"GitHub API {last} for {path} after {self._max_attempts} attempts")

    # -- endpoints ------------------------------------------------------------ #

    def iter_completed_runs(self, repository: str, workflow: str, cap: int) -> Iterator[Mapping[str, Any]]:
        """Completed runs of one workflow, newest first, at most ``cap``."""
        path = f"/repos/{repository}/actions/workflows/{urllib.parse.quote(workflow)}/runs"
        yielded, page = 0, 1
        while yielded < cap:
            body = self.get_json(path, {"status": "completed", "per_page": PER_PAGE, "page": page})
            runs = body.get("workflow_runs") if isinstance(body, Mapping) else None
            if not isinstance(runs, list):
                raise HistoryError(f"GitHub API response for {path} has no workflow_runs list")
            for run in runs:
                if yielded >= cap:
                    return
                yield run
                yielded += 1
            total = body.get("total_count")
            if len(runs) < PER_PAGE or (isinstance(total, int) and page * PER_PAGE >= total):
                return
            page += 1

    def run_duration_ms(self, repository: str, run_id: int) -> float | None:
        body = self.get_json(f"/repos/{repository}/actions/runs/{int(run_id)}/timing")
        value = body.get("run_duration_ms") if isinstance(body, Mapping) else None
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def repo_language(self, repository: str) -> str | None:
        body = self.get_json(f"/repos/{repository}")
        value = body.get("language") if isinstance(body, Mapping) else None
        return value if isinstance(value, str) else None


def run_to_history_entry(run: Mapping[str, Any], workflow: str,
                         timing_ms: float | None = None) -> dict[str, Any] | None:
    """One GitHub run object → a history entry (interface §4), or None if it cannot be placed in time."""
    try:
        started = parse_utc(run.get("run_started_at"), "run_started_at")
        updated = parse_utc(run.get("updated_at"), "updated_at")
        run_id = int(run["id"])
    except (ValueError, KeyError, TypeError):
        return None
    path = str(run.get("path") or "")
    run_workflow = path.rsplit("/", 1)[-1] if path else workflow
    if timing_ms is not None:
        duration, source = timing_ms / 1000.0, "timing"
    else:
        duration, source = (updated - started).total_seconds(), "wallclock"
    return {
        "run_id": run_id, "workflow": run_workflow, "status": str(run.get("status")),
        "conclusion": run.get("conclusion"), "created_at": run.get("created_at"),
        "run_started_at": run.get("run_started_at"), "updated_at": run.get("updated_at"),
        "duration_s": float(duration), "duration_source": source,
    }


class GitHubHistorySource:
    """History for the advisor: completed runs from the API, timing lookups within a budget."""

    def __init__(self, client: GitHubClient, *, timing_budget: int = 0) -> None:
        self.client = client
        self.timing_budget = max(0, int(timing_budget))
        self.skipped_unplaceable = 0

    def __call__(self, repository: str, workflow: str, cap: int) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        budget = self.timing_budget
        for run in self.client.iter_completed_runs(repository, workflow, cap):
            timing = None
            if budget > 0 and run.get("id") is not None:
                timing = self.client.run_duration_ms(repository, int(run["id"]))
                budget -= 1
            entry = run_to_history_entry(run, workflow, timing)
            if entry is None:
                self.skipped_unplaceable += 1
                continue
            entries.append(entry)
        return entries

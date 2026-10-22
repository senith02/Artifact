#!/usr/bin/env python3
"""carbon_tick — start the re-dispatch at the exact due time (DL-038 §11).

GitHub's `schedule` trigger is best-effort: on 2026-10-21/22 an hourly schedule ran
3 times in 12 hours, so a deferral due at 02:00 UTC was never dispatched. This
small service runs on your own server instead:

1. It reads the open `carbon-deferral` issues (read-only) and their due times.
2. It sleeps until the earliest due time (re-checking at least every --poll
   seconds, so new deferrals are noticed).
3. At the due time it starts the `carbon-dispatch` workflow once (workflow_dispatch,
   which GitHub starts within about a minute). That workflow does all the real work:
   it validates the issue, starts the build at the deferred commit, and closes the
   issue.

It holds no decision logic and trusts nothing it reads: the dispatcher on GitHub
re-checks every issue. If an issue is still open --retry seconds after a trigger
(e.g. the dispatch failed), it triggers again, so a deferral is never dropped.

Standard library only (Python 3.9+). The token is read from GITHUB_TOKEN and never
printed. It needs: this repository only; Actions: read and write; Issues: read.

    GITHUB_TOKEN=... python3 carbon_tick.py --repo owner/name            # run forever
    GITHUB_TOKEN=... python3 carbon_tick.py --repo owner/name --once --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

API = "https://api.github.com"
LABEL = "carbon-deferral"
TRUSTED_CREATOR = "github-actions[bot]"
#: The machine-readable block the advisor writes into each deferral issue (advisor/redispatch.py).
RECORD_RE = re.compile(r"<!-- carbon-deferral v1\n(\{.*?\})\n-->", re.S)


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"{stamp}  {message}", flush=True)


class GitHub:
    """A minimal REST client. Errors raise RuntimeError without the token in the text."""

    def __init__(self, token: str, opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        self._token = token
        self._opener = opener

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(API + path, data=data, method=method, headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {self._token}", "User-Agent": "carbon-tick",
            **({"Content-Type": "application/json"} if data else {})})
        try:
            with self._opener(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"GitHub returned HTTP {exc.code} for {method} {path}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"GitHub unreachable for {method} {path}: {type(exc).__name__}") from None

    def open_deferrals(self, repo: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for page in range(1, 4):
            batch = self._call("GET", f"/repos/{repo}/issues?labels={LABEL}&state=open&per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RuntimeError("the issue listing is not a list")
            issues += batch
            if len(batch) < 100:
                break
        return issues

    def start_workflow(self, repo: str, workflow: str, ref: str) -> None:
        self._call("POST", f"/repos/{repo}/actions/workflows/{workflow}/dispatches", {"ref": ref})


def due_times(issues: list[dict[str, Any]], creator: str = TRUSTED_CREATOR) -> list[tuple[int, datetime]]:
    """(issue number, due time) for each well-formed open deferral, earliest first."""
    out = []
    for issue in issues:
        if "pull_request" in issue or issue.get("state") != "open":
            continue
        if (issue.get("user") or {}).get("login") != creator:
            continue
        match = RECORD_RE.search(issue.get("body") or "")
        if not match:
            continue
        try:
            due = datetime.fromisoformat(json.loads(match.group(1))["defer_until_utc"])
            number = int(issue["number"])
        except (ValueError, KeyError, TypeError):
            continue
        if due.tzinfo is not None:
            out.append((number, due.astimezone(timezone.utc)))
    return sorted(out, key=lambda item: item[1])


class Ticker:
    """One decision per wake-up: trigger if something is due, then say how long to sleep."""

    def __init__(self, github: GitHub, repo: str, *, workflow: str = "carbon-dispatch.yml", ref: str = "main",
                 poll: float = 300, retry: float = 1200, grace: float = 20, dry_run: bool = False,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 logger: Callable[[str], None] = log) -> None:
        self.github, self.repo, self.workflow, self.ref = github, repo, workflow, ref
        self.poll, self.retry, self.grace = timedelta(seconds=poll), timedelta(seconds=retry), timedelta(seconds=grace)
        self.dry_run, self.clock, self.log = dry_run, clock, logger
        self.triggered: dict[int, datetime] = {}

    def step(self) -> float:
        now = self.clock()
        times = due_times(self.github.open_deferrals(self.repo))
        open_numbers = {n for n, _ in times}
        self.triggered = {n: t for n, t in self.triggered.items() if n in open_numbers}
        due = [n for n, t in times if t <= now and (n not in self.triggered or now - self.triggered[n] >= self.retry)]
        if due:
            retries = [n for n in due if n in self.triggered]
            self.log(f"due: issue(s) {', '.join(f'#{n}' for n in due)}"
                     + (f" (retry for {', '.join(f'#{n}' for n in retries)})" if retries else "")
                     + f" -> starting {self.workflow}" + (" [dry run]" if self.dry_run else ""))
            if not self.dry_run:
                self.github.start_workflow(self.repo, self.workflow, self.ref)
            for n in due:
                self.triggered[n] = now
        # Wake at the next due time (plus a little grace), at a pending retry, or at the poll interval.
        wakes = [t + self.grace for _, t in times if t > now]
        wakes += [t + self.retry for t in self.triggered.values()]
        wake = min([w for w in wakes if w > now] + [now + self.poll])
        upcoming = [f"#{n} at {t:%Y-%m-%d %H:%M} UTC" for n, t in times if t > now]
        self.log(f"{len(times)} open deferral(s)" + (f"; next: {upcoming[0]}" if upcoming else "")
                 + f"; sleeping until {wake:%H:%M:%S} UTC")
        return max(1.0, (wake - now).total_seconds())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="owner/name of the repository with the deferrals")
    parser.add_argument("--workflow", default="carbon-dispatch.yml", help="the dispatcher workflow file")
    parser.add_argument("--ref", default="main", help="branch the dispatcher workflow runs on")
    parser.add_argument("--poll", type=float, default=300, help="re-check for new deferrals every N s (default 300)")
    parser.add_argument("--retry", type=float, default=1200,
                        help="trigger again if a due issue is still open after N s (default 1200)")
    parser.add_argument("--once", action="store_true", help="check once and exit (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="log what would be triggered; trigger nothing")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}", args.repo):
        parser.error("--repo must look like owner/name")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("error: set GITHUB_TOKEN (see README.md)", file=sys.stderr)
        return 2
    ticker = Ticker(GitHub(token), args.repo, workflow=args.workflow, ref=args.ref, poll=args.poll,
                    retry=args.retry, dry_run=args.dry_run)
    log(f"carbon-tick watching {args.repo} (dispatcher {args.workflow} on {args.ref})")
    while True:
        try:
            pause = ticker.step()
        except Exception as exc:  # network trouble, bad token, ...: log it, wait, try again
            log(f"error: {exc}; retrying in {args.poll:.0f} s")
            pause = args.poll
        if args.once:
            return 0
        time.sleep(pause)


if __name__ == "__main__":
    sys.exit(main())

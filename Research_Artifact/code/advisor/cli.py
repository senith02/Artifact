"""``python -m advisor advise …`` — the in-process path (context/p4_interface.md §8).

It always writes a decision and exits 0, a fail-safe one included, so a CI step
built on it can never fail or block the pipeline. Exit 2 means a usage error
that left no decision (e.g. an unreadable request file).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from . import carbon_live
from .audit import AuditLog, advise_with_audit
from .config import ConfigError, load_team_config
from .core import Dependencies, _fail_safe
from .github import GitHubClient, GitHubHistorySource
from .render import render_markdown


def _read_json(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
    return json.loads(text)


def _post_to_api(url: str, payload: Any, token: str | None, timeout: float = 10.0) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Advisor-Token"] = token
    request = urllib.request.Request(url.rstrip("/") + "/decision", data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-configured URL
        return json.loads(response.read().decode("utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m advisor",
                                     description="Carbon-deferral advisor (DL-033 revision 3).")
    sub = parser.add_subparsers(dest="command", required=True)
    adv = sub.add_parser("advise", help="advise on one CI run")
    adv.add_argument("--request", required=True, help="request JSON file, or - for stdin")
    adv.add_argument("--config", help="team config YAML (.github/carbon-advisor.yml)")
    source = adv.add_mutually_exclusive_group()
    source.add_argument("--history-file", help="JSON list of completed-run history entries")
    source.add_argument("--github", action="store_true",
                        help="fetch completed-run history from the GitHub API (token from GITHUB_TOKEN)")
    adv.add_argument("--timing-budget", type=int, default=0,
                     help="timing-endpoint lookups allowed with --github (default 0; DL-035 §3b)")
    adv.add_argument("--no-live", action="store_true", help="skip the live (display-only) intensity lookups")
    adv.add_argument("--api-url", help="send the request to a running advisor API instead of deciding in-process")
    adv.add_argument("--audit-log", help="append a JSON Lines audit record here")
    adv.add_argument("--json-out", help="write the response JSON here (default: stdout)")
    adv.add_argument("--summary-out", help="write the Markdown summary here")
    return parser


def main(argv: Sequence[str] | None = None, *, deps: Dependencies | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = _read_json(args.request)
        if args.history_file:
            if isinstance(request, dict) and "history" in request:
                print("error: the request already carries history; drop --history-file", file=sys.stderr)
                return 2
            request = {**request, "history": _read_json(args.history_file)}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2

    if args.api_url:
        try:
            response = _post_to_api(args.api_url, request, os.environ.get("ADVISOR_API_TOKEN"))
        except Exception as exc:
            response = _fail_safe("api_unreachable", f"advisor API at {args.api_url} could not be reached "
                                                     f"({type(exc).__name__})")
    else:
        try:
            config = load_team_config(args.config) if args.config else ConfigError("no --config given")
        except ConfigError as exc:
            config = exc
        deps = deps or Dependencies()
        if args.github and deps.history_source is None:
            deps.history_source = GitHubHistorySource(GitHubClient(os.environ.get("GITHUB_TOKEN")),
                                                      timing_budget=args.timing_budget)
        if not args.no_live:
            deps.live_national = deps.live_national or carbon_live.fetch_national
            deps.live_regional = deps.live_regional or carbon_live.fetch_regional
        log = AuditLog(args.audit_log) if args.audit_log else None
        response = advise_with_audit(request, config, deps, log)

    text = json.dumps(response, indent=2, sort_keys=True, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if args.summary_out:
        branch = request.get("branch") if isinstance(request, dict) else None
        Path(args.summary_out).write_text(render_markdown(response, branch=branch), encoding="utf-8")
    return 0

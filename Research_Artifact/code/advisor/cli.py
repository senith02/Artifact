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

    wi = sub.add_parser("whatif", help="replay a workflow's completed runs through the advisor (demonstration)")
    wi.add_argument("--repo", required=True, help="owner/name")
    wi.add_argument("--workflow", required=True, help="workflow file name, e.g. ci.yml")
    wi.add_argument("--snapshot", required=True, help="history snapshot JSON; read it, or write it with --fetch")
    wi.add_argument("--fetch", action="store_true",
                    help="fetch the completed runs from GitHub first (read-only; token from GITHUB_TOKEN)")
    wi.add_argument("--cap", type=int, default=500, help="completed runs to fetch (default 500, DL-033 R3-C6)")
    wi.add_argument("--config", help="team config YAML (default: GB scenario, DL-037 §2)")
    wi.add_argument("--out", required=True, help="output directory (refused under results/p0-p3)")
    return parser


def _whatif(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from . import whatif
    from .contract import _REPO_RE, _WORKFLOW_RE

    if not _REPO_RE.match(args.repo) or not _WORKFLOW_RE.match(args.workflow):
        print("error: --repo must be owner/name and --workflow a .yml/.yaml file name", file=sys.stderr)
        return 2
    try:
        whatif.check_output_dir(args.out)
        if args.fetch:
            client = GitHubClient(os.environ.get("GITHUB_TOKEN"))
            snapshot = whatif.fetch_snapshot(client, args.repo, args.workflow, cap=args.cap,
                                             now=datetime.now(timezone.utc))
            Path(args.snapshot).parent.mkdir(parents=True, exist_ok=True)
            Path(args.snapshot).write_text(whatif.canonical_json(snapshot), encoding="utf-8", newline="\n")
        snapshot = whatif.load_snapshot(args.snapshot)
        if (snapshot["repository"], snapshot["workflow"]) != (args.repo, args.workflow):
            raise whatif.WhatIfError("the snapshot is for a different repository or workflow")
        config = load_team_config(args.config) if args.config else None
        records = whatif.replay(snapshot, config=config)
        report = whatif.build_report(snapshot, records, config=config)
        digests = whatif.write_report(report, args.out)
    except (whatif.WhatIfError, ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"out": str(Path(args.out)), **digests}, indent=2))
    return 0


def main(argv: Sequence[str] | None = None, *, deps: Dependencies | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "whatif":
        return _whatif(args)
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

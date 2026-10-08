"""The GitHub Action's advisory step (DL-033 R3-C1, R3-C7; DL-036 §5).

It builds the advisor request from the runner's environment and the event
payload file, runs ``python -m advisor advise`` in-process, and publishes the
decision as step outputs and the Step Summary.

Two rules hold whatever happens:

- **Nothing from the event is interpolated into a shell line.** Every value is
  read here, from ``GITHUB_*`` variables and ``GITHUB_EVENT_PATH``, and passed
  to the advisor as JSON.
- **The step never blocks the pipeline.** It always exits 0. If the advisor
  cannot be imported or raises, the outputs carry a fail-safe RUN NOW
  (``internal_error``).

The decision itself is the advisor's, and through it ``scheduler_core.decide()``.
This file holds no decision logic.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

CODE_DIR = Path(__file__).resolve().parents[1]

#: Copied from advisor.contract.NULL_STATEMENT so that a fail-safe written when the
#: advisor cannot even be imported still carries it. A test asserts the two are equal.
NULL_STATEMENT = (
    "SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; "
    "results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration "
    "estimate from completed history only."
)

#: The step outputs (DL-033 R3-D P4-T2 S1, plus the R3-K scenario flag).
OUTPUT_NAMES: tuple[str, ...] = (
    "action", "display", "defer_until", "reason", "d_hat_seconds", "n_history", "fail_safe",
    "fail_safe_code", "scenario",
)

_WORKFLOW_REF_RE = re.compile(r"/\.github/workflows/([^/@]+)@")
_PR_EVENTS = ("pull_request", "pull_request_target")


def workflow_file(workflow_ref: str | None) -> str | None:
    """``owner/repo/.github/workflows/ci.yml@refs/heads/x`` → ``ci.yml``."""
    match = _WORKFLOW_REF_RE.search(workflow_ref or "")
    return match.group(1) if match else None


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def build_request(env: Mapping[str, str], event: Mapping[str, Any], arrival_utc: str) -> dict[str, Any]:
    """The advisor request for this run (context/p4_interface.md §3).

    Values are copied, never judged: the advisor's closed schema validates them,
    so a missing or malformed value becomes the advisor's own fail-safe. An empty
    ``compute-region`` is left out on purpose, which the advisor refuses.
    """
    event_name = env.get("GITHUB_EVENT_NAME", "")
    is_pr_event = event_name in _PR_EVENTS
    branch = (env.get("GITHUB_HEAD_REF") if is_pr_event else None) or env.get("GITHUB_REF_NAME", "")
    ref_type = env.get("GITHUB_REF_TYPE") or "branch"

    request: dict[str, Any] = {
        "repository": env.get("GITHUB_REPOSITORY", ""),
        "workflow": workflow_file(env.get("GITHUB_WORKFLOW_REF")) or "",
        "event": event_name,
        "ref_type": ref_type,
        "branch": branch,
        "is_pr": event_name == "pull_request",
        "arrival_utc": arrival_utc,
    }
    region = (env.get("ADVISOR_COMPUTE_REGION") or "").strip()
    if region:
        request["compute_region"] = region
    scenario = (env.get("ADVISOR_SCENARIO") or "").strip()
    if scenario:
        request["scenario"] = scenario
    deadline = (env.get("ADVISOR_DEADLINE_UTC") or "").strip()
    if deadline:
        request["deadline_utc"] = deadline

    sha = env.get("GITHUB_SHA")
    if sha:
        request["head_sha"] = sha
    for key, var in (("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT")):
        value = _int_or_none(env.get(var))
        if value is not None:
            request[key] = value

    head_commit = event.get("head_commit") if isinstance(event, Mapping) else None
    if isinstance(head_commit, Mapping) and isinstance(head_commit.get("message"), str):
        request["head_commit_message"] = head_commit["message"][:4096]
    repo = event.get("repository") if isinstance(event, Mapping) else None
    if isinstance(repo, Mapping) and isinstance(repo.get("language"), str):
        request["repo_language"] = repo["language"][:64]
    return request


def fallback_response(message: str) -> dict[str, Any]:
    """A fail-safe RUN NOW for when the advisor itself could not run."""
    return {
        "action": "run_now", "display": "RUN NOW", "outcome_kind": "fail_safe", "fail_safe": True,
        "fail_safe_code": "internal_error", "defer_until": None, "d_hat_seconds": None,
        "n_history": None, "scenario": None,
        "reason": f"fail-safe [internal_error]: {message} -> RUN NOW. | {NULL_STATEMENT}",
    }


def fallback_summary(response: Mapping[str, Any]) -> str:
    return ("## 🔴 RUN NOW\n\n"
            f"**Why:** `{str(response.get('reason', '')).replace('`', chr(39))}`\n\n"
            "- Recommendation only: the advisor never pauses, cancels or fails a build.\n")


def output_values(response: Mapping[str, Any]) -> dict[str, str]:
    """Step-output strings. Booleans are ``true``/``false``; absent values are empty."""
    defer = response.get("defer_until")
    values = {
        "action": response.get("action") or "run_now",
        "display": response.get("display") or "RUN NOW",
        "defer_until": defer.get("utc", "") if isinstance(defer, Mapping) else "",
        "reason": response.get("reason") or "",
        "d_hat_seconds": "" if response.get("d_hat_seconds") is None else f"{float(response['d_hat_seconds']):g}",
        "n_history": "" if response.get("n_history") is None else str(int(response["n_history"])),
        "fail_safe": "true" if response.get("fail_safe") else "false",
        "fail_safe_code": response.get("fail_safe_code") or "",
        "scenario": "true" if response.get("scenario") else "false",
    }
    return {name: str(values[name]) for name in OUTPUT_NAMES}


def format_outputs(values: Mapping[str, str], delimiter: str | None = None) -> str:
    """``$GITHUB_OUTPUT`` text in the multi-line ``name<<DELIM`` form, with a delimiter no value contains."""
    delimiter = delimiter or f"ADVISOR_EOF_{uuid.uuid4().hex}"
    if any(delimiter in v for v in values.values()):
        raise ValueError("output value contains the delimiter")
    return "".join(f"{name}<<{delimiter}\n{value}\n{delimiter}\n" for name, value in values.items())


def _load_event(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _append(path: str | None, text: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def run(env: Mapping[str, str], *, cli_main: Callable[[list[str]], int] | None = None) -> dict[str, Any]:
    """One advisory step. Returns the response; never raises."""
    out_dir = Path(env.get("RUNNER_TEMP") or ".") / "carbon-advisor"
    response: dict[str, Any] | None = None
    summary: str | None = None
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        arrival = env.get("ADVISOR_ARRIVAL_UTC") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        request = build_request(env, _load_event(env.get("GITHUB_EVENT_PATH")), arrival)
        request_path, response_path = out_dir / "request.json", out_dir / "response.json"
        summary_path = out_dir / "summary.md"
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        config = Path(env.get("GITHUB_WORKSPACE") or ".") / (env.get("ADVISOR_CONFIG") or ".github/carbon-advisor.yml")
        argv = ["advise", "--request", str(request_path), "--config", str(config), "--github",
                "--audit-log", str(out_dir / "audit.jsonl"), "--json-out", str(response_path),
                "--summary-out", str(summary_path)]
        if (env.get("ADVISOR_LIVE") or "true").strip().lower() == "false":
            argv.append("--no-live")

        if cli_main is None:
            if str(CODE_DIR) not in sys.path:
                sys.path.insert(0, str(CODE_DIR))
            from advisor.cli import main as cli_main  # imported late: a failure here is a fail-safe
        status = cli_main(argv)
        if status != 0 or not response_path.is_file():
            raise RuntimeError(f"advisor CLI exited {status} without a decision")
        response = json.loads(response_path.read_text(encoding="utf-8"))
        summary = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else None
    except BaseException as exc:  # noqa: BLE001 — the step must never fail the job
        if isinstance(exc, KeyboardInterrupt):
            raise
        detail = f"the advisor could not run ({type(exc).__name__}: {exc})"
        if env.get("ADVISOR_INSTALL_OUTCOME") not in (None, "", "success"):
            detail += f"; dependency install outcome: {env.get('ADVISOR_INSTALL_OUTCOME')}"
        response = fallback_response(detail)
        try:
            (out_dir / "response.json").write_text(json.dumps(response, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
            (out_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass

    try:
        _append(env.get("GITHUB_STEP_SUMMARY"), summary or fallback_summary(response))
        _append(env.get("GITHUB_OUTPUT"), format_outputs(output_values(response)))
    except Exception:  # noqa: BLE001 — publishing is best effort; the step still exits 0
        traceback.print_exc()
    try:
        print(f"carbon advisor: {response.get('display')} - {response.get('reason')}")
    except Exception:  # noqa: BLE001 — e.g. a console that cannot encode the text; never fail the step
        pass
    return response


def main() -> int:
    run(os.environ)
    return 0


if __name__ == "__main__":
    sys.exit(main())

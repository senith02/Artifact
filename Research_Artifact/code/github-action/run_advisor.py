"""The GitHub Action's step (DL-033 R3-C1, R3-C7; DL-036 §5; DL-038).

Three modes, chosen by the ``mode`` input (DL-038 §5):

- ``advise`` (default) builds the advisor request from the runner's environment and
  the event payload file, runs ``python -m advisor advise`` in-process, and publishes
  the decision as step outputs, the Step Summary and one run-page notice.
- ``whatif`` runs the Repo What-If Report for this repository (demonstration only).
- ``dispatch`` re-dispatches the due ``carbon-deferral`` issues (opt-in re-dispatch).

Two rules hold whatever happens:

- **Nothing from the event is interpolated into a shell line.** Every value is
  read here, from ``GITHUB_*`` variables and ``GITHUB_EVENT_PATH``, and passed
  to the advisor as JSON.
- **The step never blocks the pipeline.** It always exits 0. If the advisor
  cannot be imported or raises, the outputs carry a fail-safe RUN NOW
  (``internal_error``).

The team config is a file when one exists, or is built from the Action's inputs
(inline mode, DL-038 §2). The decision itself is the advisor's, and through it
``scheduler_core.decide()``. This file holds no decision logic.
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
DEFAULT_CONFIG = ".github/carbon-advisor.yml"

#: Copied from advisor.contract.NULL_STATEMENT so that a fail-safe written when the
#: advisor cannot even be imported still carries it. A test asserts the two are equal.
NULL_STATEMENT = (
    "SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; "
    "results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration "
    "estimate from completed history only."
)
#: Copied from advisor.redispatch.DISPATCH_INPUT for the same reason; a test asserts equality.
DISPATCH_INPUT = "carbon_redispatch_sha"

#: The step outputs (DL-033 R3-D P4-T2 S1, the R3-K scenario flag, DL-038 §3 and §6).
OUTPUT_NAMES: tuple[str, ...] = (
    "action", "display", "defer_until", "reason", "d_hat_seconds", "n_history", "fail_safe",
    "fail_safe_code", "scenario", "deferred", "build_sha", "scenario_display", "scenario_defer_until",
)

_WORKFLOW_REF_RE = re.compile(r"/\.github/workflows/([^/@]+)@")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PR_EVENTS = ("pull_request", "pull_request_target")

CliMain = Callable[[list[str]], int]


def workflow_file(workflow_ref: str | None) -> str | None:
    """``owner/repo/.github/workflows/ci.yml@refs/heads/x`` → ``ci.yml``."""
    match = _WORKFLOW_REF_RE.search(workflow_ref or "")
    return match.group(1) if match else None


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _truthy(value: str | None, default: bool = False) -> bool:
    text = (value or "").strip().lower()
    return default if not text else text in ("true", "yes", "1", "on")


def redispatch_sha(env: Mapping[str, str], event: Mapping[str, Any]) -> str | None:
    """The deferred SHA of a re-dispatched run (DL-038 §6c), or None."""
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        return None
    inputs = event.get("inputs") if isinstance(event, Mapping) else None
    value = inputs.get(DISPATCH_INPUT) if isinstance(inputs, Mapping) else None
    return value if isinstance(value, str) and _SHA_RE.match(value) else None


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
    deferred_sha = redispatch_sha(env, event)
    if deferred_sha:
        request["redispatch_key"] = deferred_sha

    head_commit = event.get("head_commit") if isinstance(event, Mapping) else None
    if isinstance(head_commit, Mapping) and isinstance(head_commit.get("message"), str):
        request["head_commit_message"] = head_commit["message"][:4096]
    repo = event.get("repository") if isinstance(event, Mapping) else None
    if isinstance(repo, Mapping) and isinstance(repo.get("language"), str):
        request["repo_language"] = repo["language"][:64]
    return request


# --------------------------------------------------------------------------- #
# Team config: a file, or the Action's inputs (DL-038 §2).
# --------------------------------------------------------------------------- #

def _list_input(value: str | None) -> list[str]:
    return [item.strip() for item in re.split(r"[,\n]", value or "") if item.strip()]


def inline_config(env: Mapping[str, str], workflow: str, *, region: str | None = None) -> dict[str, Any]:
    """The team config built from the Action's inputs.

    Values are passed through for the advisor's closed-schema validator to judge, so a bad
    input is still the ``config_invalid`` fail-safe. Placing the job in a workflow is the
    opt-in, so ``enabled_workflows`` is that workflow.
    """
    raw: dict[str, Any] = {
        "compute_region": region if region is not None else (env.get("ADVISOR_COMPUTE_REGION") or "").strip(),
        "enabled_workflows": [workflow] if workflow else [],
    }
    for key, var in (("extra_protected_branches", "ADVISOR_EXTRA_PROTECTED_BRANCHES"),
                     ("urgent_markers", "ADVISOR_URGENT_MARKERS")):
        items = _list_input(env.get(var))
        if items:
            raw[key] = items
    max_delay = (env.get("ADVISOR_MAX_DELAY_HOURS") or "").strip()
    if max_delay:
        try:
            raw["max_delay_hours"] = float(max_delay)
        except ValueError:
            raw["max_delay_hours"] = max_delay
    display_region = (env.get("ADVISOR_GRID_DISPLAY_REGION") or "").strip()
    if display_region:
        raw["grid_display_region"] = int(display_region) if display_region.isdigit() else display_region
    redispatch = (env.get("ADVISOR_REDISPATCH") or "").strip()
    if redispatch.lower() == "true":
        raw["redispatch"] = "reference-demo"
    elif redispatch and redispatch.lower() != "false":
        raw["redispatch"] = redispatch
    return raw


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def resolve_config(env: Mapping[str, str], workflow: str, out_dir: Path) -> tuple[Path, str]:
    """``(path, "file" | "inline")``. A named file is used even if missing (→ config_invalid)."""
    workspace = Path(env.get("GITHUB_WORKSPACE") or ".")
    named = (env.get("ADVISOR_CONFIG") or "").strip()
    if named:
        return workspace / named, "file"
    if (workspace / DEFAULT_CONFIG).is_file():
        return workspace / DEFAULT_CONFIG, "file"
    # JSON is YAML, so this needs no YAML library before the advisor is imported.
    return _write_json(out_dir / "config.inline.yml", inline_config(env, workflow)), "inline"


def scenario_config(env: Mapping[str, str], workflow: str, config_path: Path, mode: str, out_dir: Path) -> Path:
    """The same team config with ``compute_region: GB``, for the labelled GB scenario (DL-038 §3)."""
    if mode == "inline":
        raw = inline_config(env, workflow, region="GB")
    else:
        import yaml  # the advisor's own dependency, present whenever the advisor runs

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
        raw = {**raw, "compute_region": "GB"} if isinstance(raw, dict) else raw
    return _write_json(out_dir / "config.scenario.yml", raw)


# --------------------------------------------------------------------------- #
# Publishing.
# --------------------------------------------------------------------------- #

def fallback_response(message: str) -> dict[str, Any]:
    """A fail-safe RUN NOW for when the advisor itself could not run."""
    return {
        "action": "run_now", "display": "RUN NOW", "outcome_kind": "fail_safe", "fail_safe": True,
        "fail_safe_code": "internal_error", "defer_until": None, "d_hat_seconds": None,
        "n_history": None, "scenario": None, "deferred": False,
        "reason": f"fail-safe [internal_error]: {message} -> RUN NOW. | {NULL_STATEMENT}",
    }


def fallback_summary(response: Mapping[str, Any]) -> str:
    return ("## 🔴 RUN NOW\n\n"
            f"**Why:** `{str(response.get('reason', '')).replace('`', chr(39))}`\n\n"
            "- Recommendation only: the advisor never pauses, cancels or fails a build.\n")


def _defer_utc(response: Mapping[str, Any] | None) -> str:
    defer = (response or {}).get("defer_until")
    return defer.get("utc", "") if isinstance(defer, Mapping) else ""


def output_values(response: Mapping[str, Any], *, build_sha: str = "",
                  scenario: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Step-output strings. Booleans are ``true``/``false``; absent values are empty.

    ``deferred`` is the only output safe to gate a build on (DL-038 §6b): it is true only
    when a deferral was recorded for re-dispatch.
    """
    deferred = bool(response.get("deferred")) or bool(scenario and scenario.get("deferred"))
    values = {
        "action": response.get("action") or "run_now",
        "display": response.get("display") or "RUN NOW",
        "defer_until": _defer_utc(response),
        "reason": response.get("reason") or "",
        "d_hat_seconds": "" if response.get("d_hat_seconds") is None else f"{float(response['d_hat_seconds']):g}",
        "n_history": "" if response.get("n_history") is None else str(int(response["n_history"])),
        "fail_safe": "true" if response.get("fail_safe") else "false",
        "fail_safe_code": response.get("fail_safe_code") or "",
        "scenario": "true" if response.get("scenario") else "false",
        "deferred": "true" if deferred else "false",
        "build_sha": build_sha,
        "scenario_display": (scenario or {}).get("display") or "",
        "scenario_defer_until": _defer_utc(scenario),
    }
    return {name: str(values[name]) for name in OUTPUT_NAMES}


def format_outputs(values: Mapping[str, str], delimiter: str | None = None) -> str:
    """``$GITHUB_OUTPUT`` text in the multi-line ``name<<DELIM`` form, with a delimiter no value contains."""
    delimiter = delimiter or f"ADVISOR_EOF_{uuid.uuid4().hex}"
    if any(delimiter in v for v in values.values()):
        raise ValueError("output value contains the delimiter")
    return "".join(f"{name}<<{delimiter}\n{value}\n{delimiter}\n" for name, value in values.items())


def _escape_data(text: str) -> str:
    """Workflow-command data escaping: ``%``, CR and LF (DL-038 §4)."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _code_of(response: Mapping[str, Any]) -> str:
    if response.get("fail_safe"):
        return f"fail-safe: {response.get('fail_safe_code')}"
    if response.get("vetoes"):
        return "veto: " + ", ".join(map(str, response["vetoes"]))
    return str(response.get("stage1_rule") or response.get("outcome_kind") or "")


def notice_line(response: Mapping[str, Any], scenario: Mapping[str, Any] | None = None) -> str:
    """One ``::notice`` with the display text, UTC time and outcome code only — no free text."""
    text = str(response.get("display") or "RUN NOW")
    if _defer_utc(response):
        text += f" until {_defer_utc(response)}"
    code = _code_of(response)
    if code:
        text += f" [{code}]"
    if response.get("deferred"):
        text += " - recorded for re-dispatch"
    if scenario:
        text += f" | GB scenario: {scenario.get('display')}"
        if _defer_utc(scenario):
            text += f" until {_defer_utc(scenario)}"
        if scenario.get("deferred"):
            text += " - recorded for re-dispatch"
    return f"::notice title=Carbon advisor::{_escape_data(text)}"


def _append(path: str | None, text: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def _load_event(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cli(cli_main: CliMain | None) -> CliMain:
    if cli_main is not None:
        return cli_main
    if str(CODE_DIR) not in sys.path:
        sys.path.insert(0, str(CODE_DIR))
    from advisor.cli import main  # imported late: a failure here is a fail-safe

    return main


# --------------------------------------------------------------------------- #
# Mode: advise.
# --------------------------------------------------------------------------- #

def _advise_once(cli_main: CliMain, request: Mapping[str, Any], config: Path, out_dir: Path,
                 env: Mapping[str, str]) -> tuple[dict[str, Any], str | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    request_path, response_path = _write_json(out_dir / "request.json", request), out_dir / "response.json"
    summary_path = out_dir / "summary.md"
    argv = ["advise", "--request", str(request_path), "--config", str(config), "--github",
            "--audit-log", str(out_dir / "audit.jsonl"), "--json-out", str(response_path),
            "--summary-out", str(summary_path)]
    if (env.get("ADVISOR_LIVE") or "true").strip().lower() == "false":
        argv.append("--no-live")
    status = cli_main(argv)
    if status != 0 or not response_path.is_file():
        raise RuntimeError(f"advisor CLI exited {status} without a decision")
    response = json.loads(response_path.read_text(encoding="utf-8"))
    summary = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else None
    return response, summary


def run(env: Mapping[str, str], *, cli_main: CliMain | None = None) -> dict[str, Any]:
    """One advisory step. Returns the real-location response; never raises."""
    out_dir = Path(env.get("RUNNER_TEMP") or ".") / "carbon-advisor"
    response: dict[str, Any] | None = None
    scenario: dict[str, Any] | None = None
    summary: str | None = None
    build_sha = env.get("GITHUB_SHA") or ""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        arrival = env.get("ADVISOR_ARRIVAL_UTC") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        event = _load_event(env.get("GITHUB_EVENT_PATH"))
        build_sha = redispatch_sha(env, event) or build_sha
        request = build_request(env, event, arrival)
        config, mode = resolve_config(env, request["workflow"], out_dir)
        main = _cli(cli_main)
        response, summary = _advise_once(main, request, config, out_dir, env)

        # The labelled GB scenario beside the real answer (DL-038 §3).
        region = request.get("compute_region")
        if _truthy(env.get("ADVISOR_SHOW_GB_SCENARIO")) and region and region != "GB" and not request.get("scenario"):
            try:
                scenario_dir = out_dir / "scenario"
                scenario_dir.mkdir(parents=True, exist_ok=True)
                sc_config = scenario_config(env, request["workflow"], config, mode, scenario_dir)
                sc_request = {**request, "compute_region": "GB", "scenario": "gb-hypothetical"}
                scenario, sc_summary = _advise_once(main, sc_request, sc_config, scenario_dir, env)
                summary = (summary or "") + "\n---\n\n### If this build ran on GB compute\n\n" + (sc_summary or "")
            except Exception:  # noqa: BLE001 — the scenario is display; the real answer stands
                traceback.print_exc()
                scenario = None
    except BaseException as exc:  # noqa: BLE001 — the step must never fail the job
        if isinstance(exc, KeyboardInterrupt):
            raise
        detail = f"the advisor could not run ({type(exc).__name__}: {exc})"
        if env.get("ADVISOR_INSTALL_OUTCOME") not in (None, "", "success"):
            detail += f"; dependency install outcome: {env.get('ADVISOR_INSTALL_OUTCOME')}"
        response, scenario = fallback_response(detail), None
        try:
            (out_dir / "response.json").write_text(json.dumps(response, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
            (out_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass

    try:
        _append(env.get("GITHUB_STEP_SUMMARY"), summary or fallback_summary(response))
        _append(env.get("GITHUB_OUTPUT"), format_outputs(output_values(response, build_sha=build_sha,
                                                                       scenario=scenario)))
    except Exception:  # noqa: BLE001 — publishing is best effort; the step still exits 0
        traceback.print_exc()
    try:
        print(notice_line(response, scenario))
        print(f"carbon advisor: {response.get('display')} - {response.get('reason')}")
    except Exception:  # noqa: BLE001 — e.g. a console that cannot encode the text; never fail the step
        pass
    return response


# --------------------------------------------------------------------------- #
# Modes: whatif and dispatch.
# --------------------------------------------------------------------------- #

def _report_error(env: Mapping[str, str], title: str, message: str) -> None:
    try:
        _append(env.get("GITHUB_STEP_SUMMARY"), f"## ⚠ {title}\n\n`{message.replace('`', chr(39))}`\n")
        print(f"::warning title=Carbon advisor::{_escape_data(title)}")
    except Exception:  # noqa: BLE001
        pass


def run_whatif(env: Mapping[str, str], *, cli_main: CliMain | None = None) -> int:
    """The Repo What-If Report for this repository (DL-038 §5). Demonstration only."""
    out_dir = Path(env.get("RUNNER_TEMP") or ".") / "carbon-advisor" / "whatif"
    # The snapshot holds per-run fields (DL-037 §6); it is kept out of the uploaded folder.
    snapshot = Path(env.get("RUNNER_TEMP") or ".") / "carbon-advisor-private" / "snapshot.json"
    try:
        workflow = (env.get("ADVISOR_WORKFLOW") or "").strip()
        if not workflow:
            raise ValueError("mode whatif needs the `workflow` input, e.g. ci.yml")
        argv = ["whatif", "--repo", env.get("GITHUB_REPOSITORY", ""), "--workflow", workflow, "--fetch",
                "--snapshot", str(snapshot), "--out", str(out_dir)]
        workspace = Path(env.get("GITHUB_WORKSPACE") or ".")
        named = (env.get("ADVISOR_CONFIG") or "").strip()
        if named or (workspace / DEFAULT_CONFIG).is_file():
            argv += ["--config", str(workspace / (named or DEFAULT_CONFIG))]
        status = _cli(cli_main)(argv)
        report = out_dir / "report.md"
        if status != 0 or not report.is_file():
            raise RuntimeError(f"the What-If report did not complete (exit {status}); see the step log")
        _append(env.get("GITHUB_STEP_SUMMARY"), report.read_text(encoding="utf-8"))
        print("::notice title=Carbon advisor::What-If report written to the run summary "
              "(demonstration - not research evidence)")
    except BaseException as exc:  # noqa: BLE001 — never fail the job
        if isinstance(exc, KeyboardInterrupt):
            raise
        _report_error(env, "What-If report failed", f"{type(exc).__name__}: {exc}")
    return 0


def run_dispatch(env: Mapping[str, str], *, cli_main: CliMain | None = None) -> int:
    """One pass of the re-dispatch dispatcher (DL-038 §6)."""
    out_dir = Path(env.get("RUNNER_TEMP") or ".") / "carbon-advisor" / "dispatch"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = out_dir / "dispatch.md"
        status = _cli(cli_main)(["dispatch", "--repo", env.get("GITHUB_REPOSITORY", ""),
                                 "--json-out", str(out_dir / "dispatch.json"), "--summary-out", str(summary)])
        if status != 0 or not summary.is_file():
            raise RuntimeError(f"the dispatcher did not complete (exit {status}); see the step log")
        _append(env.get("GITHUB_STEP_SUMMARY"), summary.read_text(encoding="utf-8"))
    except BaseException as exc:  # noqa: BLE001 — open issues stay open; the next run retries
        if isinstance(exc, KeyboardInterrupt):
            raise
        _report_error(env, "Re-dispatch pass failed; open deferrals stay open for the next run",
                      f"{type(exc).__name__}: {exc}")
    return 0


def main() -> int:
    mode = (os.environ.get("ADVISOR_MODE") or "advise").strip().lower()
    if mode == "whatif":
        return run_whatif(os.environ)
    if mode == "dispatch":
        return run_dispatch(os.environ)
    if mode != "advise":
        _report_error(os.environ, f"unknown mode {mode!r}; advising instead", "mode must be advise, whatif or dispatch")
    run(os.environ)
    return 0


if __name__ == "__main__":
    sys.exit(main())

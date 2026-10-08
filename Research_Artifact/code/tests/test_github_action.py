"""P4-T2 — the composite GitHub Action (DL-033 R3-C1/C7/C11; DL-036).

The wrapper builds the request from the runner environment, runs the CLI
in-process, and always publishes a decision and exits 0. The action file pins
third-party actions by SHA and interpolates nothing into a shell line. Offline:
history is injected, so the `--github` path never reaches the network.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from advisor import cli
from advisor.contract import NULL_STATEMENT, STATEMENTS, parse_request
from advisor.core import advise
from replay import validate_invariants

from tests.advisor_helpers import ARRIVAL, NOW, SHA, config, deps, history

CODE = Path(__file__).resolve().parents[1]
ACTION_DIR = CODE / "github-action"
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

_spec = importlib.util.spec_from_file_location("run_advisor", ACTION_DIR / "run_advisor.py")
run_advisor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_advisor)


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #

def _env(tmp_path: Path, *, event_name: str = "push", ref_name: str = "feature/login-cache",
         payload: dict | None = None, **extra: str) -> dict[str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload if payload is not None else {
        "head_commit": {"message": "Refactor cache"}, "repository": {"language": "Python"}}), encoding="utf-8")
    workspace = tmp_path / "ws"
    (workspace / ".github").mkdir(parents=True, exist_ok=True)
    (workspace / ".github" / "carbon-advisor.yml").write_text(
        "compute_region: GB\nenabled_workflows: [ci.yml]\n", encoding="utf-8")
    env = {
        "GITHUB_REPOSITORY": "demo-owner/demo-repo", "GITHUB_EVENT_NAME": event_name,
        "GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": ref_name, "GITHUB_HEAD_REF": "",
        "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "2000", "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": f"demo-owner/demo-repo/.github/workflows/ci.yml@refs/heads/{ref_name}",
        "GITHUB_EVENT_PATH": str(event_path), "GITHUB_WORKSPACE": str(workspace),
        "RUNNER_TEMP": str(tmp_path / "tmp"), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GITHUB_OUTPUT": str(tmp_path / "output.txt"), "ADVISOR_ARRIVAL_UTC": ARRIVAL,
        "ADVISOR_COMPUTE_REGION": "GB", "ADVISOR_LIVE": "false",
    }
    env.update(extra)
    return env


def _offline_cli(runs=None):
    """The real CLI, with injected history and a fixed clock (no network)."""
    return lambda argv: cli.main(argv, deps=deps(history_source=lambda repo, wf, cap: list(
        history() if runs is None else runs)))


def _outputs(path: Path) -> dict[str, str]:
    text, values = path.read_text(encoding="utf-8"), {}
    for match in re.finditer(r"^([a-z_]+)<<(\S+)\n(.*?)\n\2$", text, flags=re.M | re.S):
        assert match.group(1) not in values, f"output {match.group(1)} written twice"
        values[match.group(1)] = match.group(3)
    return values


# --------------------------------------------------------------------------- #
# Request building.
# --------------------------------------------------------------------------- #

def test_workflow_file_is_parsed_from_the_workflow_ref():
    assert run_advisor.workflow_file("o/r/.github/workflows/ci.yml@refs/heads/feat/x") == "ci.yml"
    assert run_advisor.workflow_file("o/r/.github/workflows/build.yaml@refs/pull/3/merge") == "build.yaml"
    assert run_advisor.workflow_file("") is None and run_advisor.workflow_file(None) is None


def test_a_push_request_is_valid_and_carries_only_contract_fields(tmp_path):
    env = _env(tmp_path)
    req = run_advisor.build_request(env, json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text()), ARRIVAL)
    assert req["event"] == "push" and req["is_pr"] is False and req["branch"] == "feature/login-cache"
    assert req["workflow"] == "ci.yml" and req["run_id"] == 2000 and req["head_sha"] == SHA
    assert req["head_commit_message"] == "Refactor cache" and req["repo_language"] == "Python"
    parsed = parse_request(req, now=NOW)
    assert parsed.compute_region == "GB" and parsed.idempotency_key() == f"demo-owner/demo-repo|ci.yml|{SHA}|1"


def test_a_pull_request_uses_the_head_branch_and_is_a_pr(tmp_path):
    env = _env(tmp_path, event_name="pull_request", ref_name="7/merge", GITHUB_HEAD_REF="feature/x")
    req = run_advisor.build_request(env, {}, ARRIVAL)
    assert req["branch"] == "feature/x" and req["is_pr"] is True
    assert advise(req, config(), deps())["stage1_rule"] is not None


def test_pull_request_target_is_refused_as_untrusted(tmp_path):
    env = _env(tmp_path, event_name="pull_request_target", ref_name="main", GITHUB_HEAD_REF="feature/x")
    out = advise(run_advisor.build_request(env, {}, ARRIVAL), config(), deps())
    assert out["action"] == "run_now" and out["fail_safe"] is True and out["fail_safe_code"] == "untrusted_event"


def test_a_tag_push_is_a_tag_ref(tmp_path):
    env = _env(tmp_path, ref_name="v1.0.0", GITHUB_REF_TYPE="tag")
    assert run_advisor.build_request(env, {}, ARRIVAL)["ref_type"] == "tag"


def test_an_empty_compute_region_is_omitted_and_fails_safe(tmp_path):
    env = _env(tmp_path, ADVISOR_COMPUTE_REGION="")
    req = run_advisor.build_request(env, {}, ARRIVAL)
    assert "compute_region" not in req
    out = advise(req, config(), deps())
    assert out["fail_safe_code"] == "invalid_request" and out["action"] == "run_now"


# --------------------------------------------------------------------------- #
# The step, end to end (offline).
# --------------------------------------------------------------------------- #

def test_an_eligible_scenario_run_publishes_a_deferral(tmp_path):
    env = _env(tmp_path, ADVISOR_SCENARIO="gb-hypothetical")
    response = run_advisor.run(env, cli_main=_offline_cli())
    out = _outputs(tmp_path / "output.txt")
    assert set(out) == set(run_advisor.OUTPUT_NAMES)
    assert response["action"] == out["action"] == "defer"
    assert out["display"] == "DEFER RECOMMENDED (scenario)" and out["scenario"] == "true"
    assert out["fail_safe"] == "false" and out["defer_until"].endswith("+00:00")
    assert out["n_history"] == "12" and float(out["d_hat_seconds"]) > 0
    assert NULL_STATEMENT in out["reason"]
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith("> **SCENARIO") and "DEFER RECOMMENDED (scenario)" in summary
    for statement in STATEMENTS:
        assert statement in summary
    artifacts = tmp_path / "tmp" / "carbon-advisor"
    assert {p.name for p in artifacts.iterdir()} >= {"request.json", "response.json", "summary.md", "audit.jsonl"}


def test_the_audit_record_passes_the_independent_validator(tmp_path):
    for i, (event, ref) in enumerate([("push", "feature/a"), ("push", "main"), ("pull_request", "9/merge")]):
        env = _env(tmp_path / str(i), event_name=event, ref_name=ref,
                   GITHUB_HEAD_REF="feature/pr" if event == "pull_request" else "")
        run_advisor.run(env, cli_main=_offline_cli())
    records = [json.loads(line) for i in range(3)
               for line in (tmp_path / str(i) / "tmp" / "carbon-advisor" / "audit.jsonl").read_text().splitlines()]
    assert [r["action"] for r in records] == ["defer", "run_now", "run_now"]
    result = validate_invariants.audit_frame(pd.DataFrame(records))
    assert result.violations == 0 and not result.missing_columns and result.deferred == 1


def test_a_non_gb_declaration_fails_safe_without_gb_figures(tmp_path):
    env = _env(tmp_path, ADVISOR_COMPUTE_REGION="GITHUB-HOSTED")
    (Path(env["GITHUB_WORKSPACE"]) / ".github" / "carbon-advisor.yml").write_text(
        "compute_region: GITHUB-HOSTED\nenabled_workflows: [ci.yml]\n", encoding="utf-8")
    response = run_advisor.run(env, cli_main=_offline_cli())
    assert response["fail_safe_code"] == "region_not_gb" and response["action"] == "run_now"
    assert response["grid_gco2_profile_now"] is None and response["est_carbon_change_pct"] is None


def test_cold_start_on_the_first_run_is_run_now(tmp_path):
    response = run_advisor.run(_env(tmp_path), cli_main=_offline_cli(runs=[]))
    assert response["action"] == "run_now" and response["vetoes"] == ["cold_start"]
    assert response["policy_action"] == "defer" and response["n_history"] == 0


def test_an_urgent_marker_vetoes_the_deferral(tmp_path):
    env = _env(tmp_path, payload={"head_commit": {"message": "[urgent] hotfix login"}})
    response = run_advisor.run(env, cli_main=_offline_cli())
    assert response["policy_action"] == "defer" and response["action"] == "run_now"
    assert response["vetoes"] == ["urgent_marker"]


def test_hostile_event_text_stays_data(tmp_path):
    branch = "feat/$(touch pwned)`id`${{ github.token }}"
    message = "x\nfail_safe<<EOF\ntrue\nEOF\n::set-output name=action::defer"
    env = _env(tmp_path, ref_name=branch, payload={"head_commit": {"message": message}})
    run_advisor.run(env, cli_main=_offline_cli())
    out = _outputs(tmp_path / "output.txt")
    assert set(out) == set(run_advisor.OUTPUT_NAMES)
    request = json.loads((tmp_path / "tmp" / "carbon-advisor" / "request.json").read_text())
    assert request["branch"] == branch and request["head_commit_message"] == message
    assert not (tmp_path / "pwned").exists()


def test_an_advisor_crash_still_publishes_a_fail_safe_and_returns(tmp_path):
    def boom(argv):
        raise ImportError("No module named 'xgboost'")

    env = _env(tmp_path, ADVISOR_INSTALL_OUTCOME="failure")
    response = run_advisor.run(env, cli_main=boom)
    out = _outputs(tmp_path / "output.txt")
    assert out["action"] == "run_now" and out["fail_safe"] == "true" and out["fail_safe_code"] == "internal_error"
    assert "xgboost" in out["reason"] and "install outcome: failure" in out["reason"]
    assert NULL_STATEMENT in response["reason"]
    assert "RUN NOW" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_argparse_exit_is_caught(tmp_path):
    response = run_advisor.run(_env(tmp_path), cli_main=lambda argv: cli.main(["advise"]))
    assert response["fail_safe_code"] == "internal_error"


def test_main_exits_zero_with_an_empty_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key in [k for k in list(__import__("os").environ) if k.startswith(("GITHUB_", "ADVISOR_", "RUNNER_"))]:
        monkeypatch.delenv(key)
    monkeypatch.setattr(run_advisor, "run", lambda env: run_advisor.fallback_response("x"))
    assert run_advisor.main() == 0


def test_the_fallback_null_statement_matches_the_contract():
    assert run_advisor.NULL_STATEMENT == NULL_STATEMENT


def test_outputs_refuse_a_value_containing_the_delimiter():
    with pytest.raises(ValueError):
        run_advisor.format_outputs({"reason": "a DELIM b"}, delimiter="DELIM")


def test_collected_runs_assemble_into_a_validated_audit_and_table(tmp_path):
    """scripts/collect_demo_runs.assemble, offline, over artifacts the wrapper itself wrote."""
    from scripts import collect_demo_runs

    out, runs = tmp_path / "demo_runs", []
    for run_id, ref in ((1, "feature/a"), (2, "main")):
        env = _env(tmp_path / f"r{run_id}", ref_name=ref, GITHUB_RUN_ID=str(run_id), ADVISOR_SCENARIO="gb-hypothetical")
        run_advisor.run(env, cli_main=_offline_cli())
        dest = out / str(run_id) / "carbon-advisor-advisor-gb-scenario-1"
        dest.mkdir(parents=True)
        for f in (Path(env["RUNNER_TEMP"]) / "carbon-advisor").iterdir():
            dest.joinpath(f.name).write_bytes(f.read_bytes())
        step = "Run senith02/Artifact/Research_Artifact/code/github-action@" + "a" * 40
        runs.append({"run_id": run_id, "html_url": f"https://example.invalid/{run_id}", "event": "push",
                     "jobs": [{"name": "advisor", "steps": [{"name": step, "conclusion": "success"},
                                                            {"name": "Post " + step, "conclusion": "success"}]}]})
    validator = collect_demo_runs.assemble(out, runs)
    assert validator["violations"] == 0 and validator["records"] == 2 and validator["deferred"] == 1
    rows = json.loads((out / "decisions.json").read_text(encoding="utf-8"))
    assert [r["display"] for r in rows] == ["DEFER RECOMMENDED (scenario)", "RUN NOW (scenario)"]
    assert all(r["advisor_steps_success"] for r in rows)
    table = (out / "decisions.md").read_text(encoding="utf-8")
    assert "Demonstration — not research evidence" in table and "0 violations over 2 audit records" in table


# --------------------------------------------------------------------------- #
# The action file, the examples and the documentation.
# --------------------------------------------------------------------------- #

def _action() -> dict:
    return yaml.safe_load((ACTION_DIR / "action.yml").read_text(encoding="utf-8"))


def test_the_action_is_composite_and_exposes_the_contract_outputs():
    action = _action()
    assert action["runs"]["using"] == "composite"
    assert set(action["outputs"]) == set(run_advisor.OUTPUT_NAMES)
    steps = {s.get("id"): s for s in action["runs"]["steps"]}
    assert steps["python"]["continue-on-error"] is True and steps["install"]["continue-on-error"] is True
    assert steps["advise"]["run"].strip().endswith("|| true")
    assert "--no-deps" in steps["install"]["run"] and "--only-binary=:all:" in steps["install"]["run"]


def test_every_third_party_action_is_pinned_by_full_sha():
    for path in [ACTION_DIR / "action.yml", ACTION_DIR / "examples" / "advisory.yml"]:
        text = path.read_text(encoding="utf-8")
        for ref in re.findall(r"uses:\s*(\S+)", text):
            if ref.startswith("senith02/Artifact/"):
                continue  # the Action itself: the example shows where the user pins it
            assert SHA_PIN.match(ref), f"{path.name}: {ref} is not pinned by commit SHA"


def test_no_expression_is_interpolated_into_a_run_line():
    for path in [ACTION_DIR / "action.yml", ACTION_DIR / "examples" / "advisory.yml"]:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        steps = doc["runs"]["steps"] if "runs" in doc else [s for j in doc["jobs"].values() for s in j["steps"]]
        for step in steps:
            assert "${{" not in step.get("run", ""), f"{path.name}: {step.get('id') or step.get('name')}"


def test_the_reference_workflow_is_least_privilege():
    doc = yaml.safe_load((ACTION_DIR / "examples" / "advisory.yml").read_text(encoding="utf-8"))
    assert doc["permissions"] == {"contents": "read", "actions": "read"}
    assert "pull_request_target" not in doc[True] and "workflow_run" not in doc[True]
    for job in doc["jobs"].values():
        assert "permissions" not in job


def test_the_example_config_is_valid():
    from advisor.config import load_team_config
    cfg = load_team_config(ACTION_DIR / "examples" / "carbon-advisor.yml")
    assert cfg.compute_region == "GB" and cfg.redispatch == "off" and cfg.cold_start_run_now


def test_the_readme_carries_every_c11_statement():
    readme = (ACTION_DIR / "README.md").read_text(encoding="utf-8")
    for statement in STATEMENTS:
        assert statement.replace("tr_duration", "`tr_duration`") in readme, statement
    assert "What-If output (P4-T3) is demonstration only" in readme


# --------------------------------------------------------------------------- #
# The runtime dependency subset (DL-036 §4).
# --------------------------------------------------------------------------- #

def _pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, version = line.split("==")
            pins[name.lower().replace("_", "-")] = version
    return pins


def test_the_action_pins_equal_the_lockfile():
    action, lock = _pins(ACTION_DIR / "requirements.action.txt"), _pins(CODE / "requirements.lock.txt")
    assert len(action) == 12
    for name, version in action.items():
        assert lock.get(name) == version, f"{name}=={version} differs from the lock ({lock.get(name)})"


_IMPORT_TO_DIST = {"sklearn": "scikit-learn", "yaml": "pyyaml", "dateutil": "python-dateutil"}
_STDLIB = set(sys.stdlib_module_names)


def test_the_subset_covers_everything_the_advisor_loads():
    """Import the CLI and load the frozen core in a fresh interpreter; every
    third-party top-level module it ends up with must be in the subset."""
    probe = ("import sys, json; sys.path.insert(0, '.'); import advisor.cli; "
             "from advisor.frozen import default_frozen_core; default_frozen_core(); "
             "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules})))")
    loaded = json.loads(subprocess.run([sys.executable, "-c", probe], cwd=CODE, capture_output=True,
                                       text=True, check=True).stdout)
    local = {"advisor", "scheduler_core", "cython_runtime"}  # cython_runtime: a module Cython creates, not a package
    third_party = {m for m in loaded if m not in _STDLIB and m not in local and not m.startswith("_")}
    allowed = set(_pins(ACTION_DIR / "requirements.action.txt"))
    # Windows-only or vendored helpers that the Linux runner either lacks or that ship inside a wheel.
    ignorable = {"pywin32_system32", "win32api", "win32con", "pythoncom", "pywintypes", "colorama"}
    missing = {m for m in third_party - ignorable if _IMPORT_TO_DIST.get(m, m).replace("_", "-") not in allowed}
    assert not missing, f"loaded at runtime but not in requirements.action.txt: {sorted(missing)}"

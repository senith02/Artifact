"""P4-T4 — one-job adoption of the Action (DL-038 §2–§5) and the re-dispatched run (§6c, §6f).

Offline: the real CLI runs in-process with injected history and a fixed clock.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

from advisor import cli, redispatch
from advisor.core import decision_view

from tests.advisor_helpers import ARRIVAL, SHA, deps, history

CODE = Path(__file__).resolve().parents[1]
ACTION_DIR = CODE / "github-action"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"

_spec = importlib.util.spec_from_file_location("run_advisor_p4t4", ACTION_DIR / "run_advisor.py")
run_advisor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_advisor)


def _env(tmp_path: Path, *, config_file: str | None = None, event_name: str = "push",
         ref_name: str = "feature/login-cache", payload: dict | None = None, **extra: str) -> dict[str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload if payload is not None else {
        "head_commit": {"message": "Refactor cache"}, "repository": {"language": "Python"}}), encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)  # no checkout: an empty workspace
    if config_file is not None:
        (workspace / ".github").mkdir(exist_ok=True)
        (workspace / ".github" / "carbon-advisor.yml").write_text(config_file, encoding="utf-8")
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


def _cli(runs=None, **dep_overrides):
    return lambda argv: cli.main(argv, deps=deps(history_source=lambda r, w, c: list(
        history() if runs is None else runs), **dep_overrides))


def _outputs(path: Path) -> dict[str, str]:
    text, values = path.read_text(encoding="utf-8"), {}
    for match in re.finditer(r"^([a-z_]+)<<(\S+)\n(.*?)\n\2$", text, flags=re.M | re.S):
        values[match.group(1)] = match.group(3)
    return values


# --------------------------------------------------------------------------- #
# Inline config (DL-038 §2).
# --------------------------------------------------------------------------- #

def test_inline_mode_gives_the_same_decision_as_file_mode(tmp_path):
    for branch in ("feature/login-cache", "main"):
        inline = run_advisor.run(_env(tmp_path / f"i-{branch[:4]}", ref_name=branch), cli_main=_cli())
        filed = run_advisor.run(_env(tmp_path / f"f-{branch[:4]}", ref_name=branch,
                                     config_file="compute_region: GB\nenabled_workflows: [ci.yml]\n"),
                                cli_main=_cli())
        assert decision_view(inline) == decision_view(filed)
    assert inline["action"] == "run_now" and filed["stage1_rule"] == "protected:mainline"


def test_inline_mode_needs_no_checkout_and_records_its_config(tmp_path):
    env = _env(tmp_path)
    response = run_advisor.run(env, cli_main=_cli())
    assert response["action"] == "defer" and response["fail_safe"] is False
    written = yaml.safe_load((tmp_path / "tmp" / "carbon-advisor" / "config.inline.yml").read_text(encoding="utf-8"))
    assert written == {"compute_region": "GB", "enabled_workflows": ["ci.yml"]}


def test_the_containing_workflow_is_the_opt_in(tmp_path):
    env = _env(tmp_path, GITHUB_WORKFLOW_REF="demo-owner/demo-repo/.github/workflows/build.yaml@refs/heads/x")
    response = run_advisor.run(env, cli_main=_cli(history(workflow="build.yaml")))
    assert response["outcome_kind"] == "policy" and response["action"] == "defer"


def test_inline_veto_inputs_reach_the_veto_layer(tmp_path):
    marked = _env(tmp_path / "m", payload={"head_commit": {"message": "hotfix [now]"}},
                  ADVISOR_URGENT_MARKERS="[now], [asap]")
    assert run_advisor.run(marked, cli_main=_cli())["vetoes"] == ["urgent_marker"]
    protected = _env(tmp_path / "p", ADVISOR_EXTRA_PROTECTED_BRANCHES="feature/*")
    assert run_advisor.run(protected, cli_main=_cli())["vetoes"] == ["extra_protected_branch"]
    short = _env(tmp_path / "s", ADVISOR_MAX_DELAY_HOURS="1")
    assert "exceeds_max_delay" in run_advisor.run(short, cli_main=_cli())["vetoes"]


@pytest.mark.parametrize("var,value", [("ADVISOR_MAX_DELAY_HOURS", "48"), ("ADVISOR_MAX_DELAY_HOURS", "soon"),
                                       ("ADVISOR_REDISPATCH", "always")])
def test_a_bad_inline_input_is_the_config_fail_safe(tmp_path, var, value):
    response = run_advisor.run(_env(tmp_path, **{var: value}), cli_main=_cli())
    assert response["action"] == "run_now" and response["fail_safe_code"] == "config_invalid"


def test_a_named_config_that_is_missing_still_fails_safe(tmp_path):
    response = run_advisor.run(_env(tmp_path, ADVISOR_CONFIG=".github/missing.yml"), cli_main=_cli())
    assert response["fail_safe_code"] == "config_invalid"


def test_an_empty_region_still_fails_safe_in_inline_mode(tmp_path):
    response = run_advisor.run(_env(tmp_path, ADVISOR_COMPUTE_REGION=""), cli_main=_cli())
    assert response["action"] == "run_now" and response["fail_safe_code"] == "invalid_request"


# --------------------------------------------------------------------------- #
# show-gb-scenario and the notice (DL-038 §3, §4).
# --------------------------------------------------------------------------- #

def test_one_job_shows_the_real_answer_and_the_labelled_gb_scenario(tmp_path):
    env = _env(tmp_path, ADVISOR_COMPUTE_REGION="GITHUB-HOSTED", ADVISOR_SHOW_GB_SCENARIO="true")
    response = run_advisor.run(env, cli_main=_cli())
    out = _outputs(tmp_path / "output.txt")
    assert set(out) == set(run_advisor.OUTPUT_NAMES)
    assert response["fail_safe_code"] == "region_not_gb" and out["action"] == "run_now"
    assert out["scenario"] == "false" and out["deferred"] == "false"
    assert out["scenario_display"] == "DEFER RECOMMENDED (scenario)" and out["scenario_defer_until"]
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert summary.index("RUN NOW") < summary.index("If this build ran on GB compute") < summary.index("SCENARIO")
    folder = tmp_path / "tmp" / "carbon-advisor"
    assert (folder / "audit.jsonl").is_file() and (folder / "scenario" / "audit.jsonl").is_file()
    sc_config = yaml.safe_load((folder / "scenario" / "config.scenario.yml").read_text(encoding="utf-8"))
    assert sc_config["compute_region"] == "GB"


def test_the_scenario_is_not_added_for_a_gb_declaration(tmp_path):
    run_advisor.run(_env(tmp_path, ADVISOR_SHOW_GB_SCENARIO="true"), cli_main=_cli())
    assert _outputs(tmp_path / "output.txt")["scenario_display"] == ""
    assert not (tmp_path / "tmp" / "carbon-advisor" / "scenario").exists()


def test_the_scenario_also_works_beside_a_file_config(tmp_path):
    env = _env(tmp_path, ADVISOR_COMPUTE_REGION="GITHUB-HOSTED", ADVISOR_SHOW_GB_SCENARIO="true",
               config_file="compute_region: GITHUB-HOSTED\nenabled_workflows: [ci.yml]\nmax_delay_hours: 12\n")
    run_advisor.run(env, cli_main=_cli())
    sc = yaml.safe_load((tmp_path / "tmp" / "carbon-advisor" / "scenario" / "config.scenario.yml")
                        .read_text(encoding="utf-8"))
    assert sc == {"compute_region": "GB", "enabled_workflows": ["ci.yml"], "max_delay_hours": 12}


def test_the_notice_carries_no_free_text_and_is_escaped():
    line = run_advisor.notice_line({"display": "RUN NOW", "fail_safe": True, "fail_safe_code": "region_not_gb",
                                    "reason": "branch x\n::error::injected"})
    assert line == "::notice title=Carbon advisor::RUN NOW [fail-safe: region_not_gb]"
    assert run_advisor._escape_data("50%\r\n::x") == "50%25%0D%0A::x"
    defer = run_advisor.notice_line({"display": "DEFER RECOMMENDED", "defer_until": {"utc": "2026-10-02T02:00:00+00:00"},
                                     "outcome_kind": "policy", "stage1_rule": None, "deferred": True})
    assert defer.endswith("DEFER RECOMMENDED until 2026-10-02T02:00:00+00:00 [policy] - recorded for re-dispatch")


def test_the_step_prints_one_notice(tmp_path, capsys):
    run_advisor.run(_env(tmp_path), cli_main=_cli())
    notices = [l for l in capsys.readouterr().out.splitlines() if l.startswith("::notice")]
    assert len(notices) == 1 and "DEFER RECOMMENDED" in notices[0]


# --------------------------------------------------------------------------- #
# The re-dispatched run (DL-038 §6c, §6f).
# --------------------------------------------------------------------------- #

def _redispatched_env(tmp_path, sha=OTHER_SHA):
    return _env(tmp_path, event_name="workflow_dispatch", payload={"inputs": {run_advisor.DISPATCH_INPUT: sha}})


def test_a_redispatched_run_is_run_now_and_builds_the_deferred_sha(tmp_path):
    response = run_advisor.run(_redispatched_env(tmp_path), cli_main=_cli())
    out = _outputs(tmp_path / "output.txt")
    assert response["action"] == "run_now" and "redispatched_run" in response["vetoes"]
    assert out["build_sha"] == OTHER_SHA and out["deferred"] == "false"


def test_a_malformed_redispatch_input_is_ignored(tmp_path):
    run_advisor.run(_redispatched_env(tmp_path, sha="main; rm -rf /"), cli_main=_cli())
    assert _outputs(tmp_path / "output.txt")["build_sha"] == SHA


def test_the_input_name_matches_the_dispatcher():
    assert run_advisor.DISPATCH_INPUT == redispatch.DISPATCH_INPUT


def test_an_ordinary_run_builds_its_own_sha(tmp_path):
    run_advisor.run(_env(tmp_path), cli_main=_cli())
    assert _outputs(tmp_path / "output.txt")["build_sha"] == SHA


# --------------------------------------------------------------------------- #
# Modes whatif and dispatch (DL-038 §5).
# --------------------------------------------------------------------------- #

def test_whatif_mode_runs_the_report_and_publishes_it(tmp_path):
    seen = []

    def fake_cli(argv):
        seen.append(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text("# What-If\nDemonstration — not research evidence\n", encoding="utf-8")
        return 0

    env = _env(tmp_path, ADVISOR_MODE="whatif", ADVISOR_WORKFLOW="ci.yml")
    assert run_advisor.run_whatif(env, cli_main=fake_cli) == 0
    argv = seen[0]
    assert argv[:5] == ["whatif", "--repo", "demo-owner/demo-repo", "--workflow", "ci.yml"] and "--fetch" in argv
    assert "--config" not in argv
    snapshot = Path(argv[argv.index("--snapshot") + 1])
    assert "carbon-advisor-private" in snapshot.parts  # kept out of the uploaded folder (DL-037 §6)
    assert "Demonstration" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_whatif_mode_without_a_workflow_reports_and_exits_zero(tmp_path):
    env = _env(tmp_path, ADVISOR_MODE="whatif")
    assert run_advisor.run_whatif(env, cli_main=lambda argv: 0) == 0
    assert "What-If report failed" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_dispatch_mode_publishes_the_pass_and_never_fails(tmp_path):
    def fake_cli(argv):
        Path(argv[argv.index("--summary-out") + 1]).write_text("## Carbon re-dispatch — 0\n", encoding="utf-8")
        return 0

    env = _env(tmp_path, ADVISOR_MODE="dispatch")
    assert run_advisor.run_dispatch(env, cli_main=fake_cli) == 0
    assert "Carbon re-dispatch" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert run_advisor.run_dispatch(env, cli_main=lambda argv: 1) == 0
    assert "stay open" in (tmp_path / "summary.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The action file and the examples.
# --------------------------------------------------------------------------- #

def _action() -> dict:
    return yaml.safe_load((ACTION_DIR / "action.yml").read_text(encoding="utf-8"))


def test_every_advisor_variable_the_wrapper_reads_is_wired_in_the_action():
    source = (ACTION_DIR / "run_advisor.py").read_text(encoding="utf-8")
    read = set(re.findall(r'"(ADVISOR_[A-Z_]+)"', source))
    step = next(s for s in _action()["runs"]["steps"] if s.get("id") == "advise")
    assert read <= set(step["env"]), read - set(step["env"])


def test_the_action_declares_the_new_inputs_and_outputs():
    action = _action()
    assert {"mode", "show-gb-scenario", "extra-protected-branches", "urgent-markers", "max-delay-hours",
            "grid-display-region", "redispatch", "workflow"} <= set(action["inputs"])
    assert action["inputs"]["config"]["default"] == "" and action["inputs"]["redispatch"]["default"] == "false"
    assert set(run_advisor.OUTPUT_NAMES) <= set(action["outputs"])


@pytest.mark.parametrize("name", ["advisory.yml", "redispatch.yml", "carbon-dispatch.yml", "whatif.yml"])
def test_the_examples_are_least_privilege_and_need_no_checkout_for_the_advisor(name):
    workflow = yaml.safe_load((ACTION_DIR / "examples" / name).read_text(encoding="utf-8"))
    for job_name, job in workflow["jobs"].items():
        steps = job.get("steps", [])
        uses_advisor = [s for s in steps if "github-action@" in str(s.get("uses", ""))]
        if not uses_advisor:
            continue
        assert not any("actions/checkout" in str(s.get("uses", "")) for s in steps), job_name
        perms = {**workflow.get("permissions", {}), **job.get("permissions", {})}
        mode = uses_advisor[0].get("with", {}).get("mode", "advise")
        # contents: read is C7's allowance for private repositories.
        allowed = {"advise": {"contents": "read", "actions": "read", "issues": "write"},
                   "whatif": {"contents": "read", "actions": "read"},
                   "dispatch": {"actions": "write", "issues": "write"}}[mode]
        assert set(perms.items()) <= set(allowed.items()), (job_name, perms)

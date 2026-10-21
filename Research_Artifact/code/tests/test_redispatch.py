"""P4-T4 — the re-dispatch reference demonstration (DL-033 R3-C10, as read by DL-038 §6/§8).

Offline: an in-memory fake GitHub stands in for the REST API, so every case
(recording, reuse, refusal, dispatch, fallback, failure) is exercised without
the network.
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from advisor import cli, redispatch
from advisor.audit import advise_with_audit
from advisor.contract import NULL_STATEMENT
from advisor.core import advise
from advisor.github import GitHubClient, GitHubHTTPError

from tests.advisor_helpers import NOW, SHA, FakeResponse, config, deps, history, request

REPO = "demo-owner/demo-repo"


class FakeGitHub:
    """Just enough of the REST API for the re-dispatch paths."""

    def __init__(self, *, branches=("main", "feature/login-cache"), creator=redispatch.TRUSTED_CREATOR,
                 clock=lambda: NOW) -> None:
        self.branches = set(branches)
        self.creator = creator
        self.clock = clock
        self.issues: list[dict[str, Any]] = []
        self.labels: set[str] = set()
        self.runs: list[dict[str, Any]] = []
        self.dispatches: list[dict[str, Any]] = []
        self.comments: dict[int, list[str]] = {}
        self.fail: dict[tuple[str, str], int] = {}
        self.calls: list[tuple[str, str]] = []

    def _maybe_fail(self, method: str, path: str) -> None:
        for (m, suffix), status in self.fail.items():
            if m == method and path.endswith(suffix):
                raise GitHubHTTPError(f"HTTP {status} for {method} {path}", status)

    def get_json(self, path: str, params: dict | None = None) -> Any:
        self.calls.append(("GET", path))
        self._maybe_fail("GET", path)
        params = params or {}
        if path == f"/repos/{REPO}/issues":
            state = params.get("state", "open")
            return [i for i in self.issues if state == "all" or i["state"] == state][:100]
        if path.startswith(f"/repos/{REPO}/actions/workflows/") and path.endswith("/runs"):
            return {"workflow_runs": [r for r in self.runs if r["event"] == params.get("event")
                                      and r["head_sha"] == params.get("head_sha")]}
        if path == f"/repos/{REPO}":
            return {"default_branch": "main"}
        raise AssertionError(f"unexpected GET {path}")

    def send_json(self, method: str, path: str, body: Any) -> Any:
        self.calls.append((method, path))
        self._maybe_fail(method, path)
        now = self.clock().isoformat().replace("+00:00", "Z")
        if path == f"/repos/{REPO}/labels":
            if body["name"] in self.labels:
                raise GitHubHTTPError("HTTP 422", 422)
            self.labels.add(body["name"])
            return body
        if path == f"/repos/{REPO}/issues":
            assert body["labels"] == [redispatch.LABEL] and redispatch.LABEL in self.labels
            issue = {"number": len(self.issues) + 1, "state": "open", "title": body["title"], "body": body["body"],
                     "user": {"login": self.creator}, "created_at": now,
                     "html_url": f"https://github.com/{REPO}/issues/{len(self.issues) + 1}"}
            self.issues.append(issue)
            return issue
        if path.endswith("/comments"):
            self.comments.setdefault(int(path.split("/")[-2]), []).append(body["body"])
            return {"id": 1}
        if method == "PATCH" and "/issues/" in path:
            self.issues[int(path.rsplit("/", 1)[-1]) - 1]["state"] = body["state"]
            return {}
        if path.endswith("/dispatches"):
            if body["ref"] not in self.branches:
                raise GitHubHTTPError("HTTP 422 (no ref)", 422)
            self.dispatches.append(body)
            self.runs.append({"id": 9000 + len(self.runs), "event": "workflow_dispatch",
                              "head_sha": body["inputs"][redispatch.DISPATCH_INPUT], "created_at": now})
            return None  # HTTP 204
        raise AssertionError(f"unexpected {method} {path}")


def _deferral(**cfg: Any) -> tuple[dict, dict, Any]:
    raw = request()
    cfg.setdefault("redispatch", "reference-demo")
    team = config(**cfg)
    response = advise(raw, team, deps())
    assert response["action"] == "defer", "the fixture must defer"
    return raw, response, team


def _due(response: dict) -> datetime:
    return datetime.fromisoformat(response["defer_until"]["utc"]) + timedelta(minutes=5)


# --------------------------------------------------------------------------- #
# Recording.
# --------------------------------------------------------------------------- #

def test_a_recorded_deferral_opens_one_labelled_issue_and_sets_deferred():
    raw, response, team = _deferral()
    gh = FakeGitHub()
    out = redispatch.record(raw, response, config=team, client=gh, now=NOW)
    assert out["deferred"] is True and out["action"] == "defer"
    assert out["redispatch"]["issue_number"] == 1 and out["redispatch"]["reused"] is False
    rec = redispatch.parse_record(gh.issues[0]["body"])
    assert rec.head_sha == SHA and rec.branch == "feature/login-cache" and rec.scenario is False
    assert rec.defer_until_utc == response["defer_until"]["utc"]
    assert gh.issues[0]["title"].startswith("Carbon deferral:")


def test_a_rerun_attempt_reuses_the_open_issue():
    raw, response, team = _deferral()
    gh = FakeGitHub()
    redispatch.record(raw, response, config=team, client=gh, now=NOW)
    again = redispatch.record({**raw, "run_attempt": 2}, response, config=team, client=gh, now=NOW)
    assert again["deferred"] is True and again["redispatch"]["reused"] is True and len(gh.issues) == 1


def test_a_key_already_handled_is_never_recorded_twice():
    raw, response, team = _deferral()
    gh = FakeGitHub()
    redispatch.record(raw, response, config=team, client=gh, now=NOW)
    gh.issues[0]["state"] = "closed"
    out = redispatch.record(raw, response, config=team, client=gh, now=NOW)
    assert out["action"] == "run_now" and out["fail_safe_code"] == "redispatch_unavailable"
    assert len(gh.issues) == 1


@pytest.mark.parametrize("status", [403, 410, 500])
def test_a_failed_record_turns_the_deferral_into_a_fail_safe_run_now(status):
    raw, response, team = _deferral()
    gh = FakeGitHub()
    gh.fail[("POST", "/issues")] = status
    out = redispatch.record(raw, response, config=team, client=gh, now=NOW)
    assert out["action"] == "run_now" and out["display"] == "RUN NOW" and out["deferred"] is False
    assert out["fail_safe"] is True and out["fail_safe_code"] == "redispatch_unavailable"
    assert out["defer_until"] is None and out["policy_action"] == "defer"
    assert NULL_STATEMENT in out["reason"]


def test_recording_does_nothing_when_off_or_not_deferred():
    raw, response, _ = _deferral()
    gh = FakeGitHub()
    assert redispatch.record(raw, response, config=config(), client=gh, now=NOW)["deferred"] is False
    run_now = advise(request(branch="main"), config(redispatch="reference-demo"), deps())
    out = redispatch.record(request(branch="main"), run_now, config=config(redispatch="reference-demo"),
                            client=gh, now=NOW)
    assert out["deferred"] is False and out["action"] == "run_now" and gh.calls == []


def test_a_scenario_is_recorded_only_in_scenario_demo_mode():
    raw = request(scenario="gb-hypothetical")
    scen = advise(raw, config(redispatch="reference-demo"), deps())
    assert scen["action"] == "defer" and scen["scenario"]
    gh = FakeGitHub()
    plain = redispatch.record(raw, scen, config=config(redispatch="reference-demo"), client=gh, now=NOW)
    assert plain["deferred"] is False and gh.calls == []
    demo = redispatch.record(raw, scen, config=config(redispatch="scenario-demo"), client=gh, now=NOW)
    assert demo["deferred"] is True
    assert gh.issues[0]["title"].startswith("[SCENARIO]") and "SCENARIO" in gh.issues[0]["body"]
    assert redispatch.parse_record(gh.issues[0]["body"]).scenario is True


def test_the_post_decision_step_can_never_create_a_deferral():
    raw = request(branch="main")
    out = advise_with_audit(raw, config(), deps(), None,
                            after=lambda r, resp: {**resp, "action": "defer"})
    assert out["action"] == "run_now" and out["fail_safe_code"] == "internal_error"

    def boom(r, resp):
        raise RuntimeError("x")

    out = advise_with_audit(request(), config(), deps(), None, after=boom)
    assert out["action"] == "run_now" and out["fail_safe"] is True and out["deferred"] is False


def test_the_record_layer_is_monotone_over_many_inputs():
    """Whenever the layer's output defers, advise() deferred with the identical time."""
    gh = FakeGitHub()
    cases = [request(branch=b, history=history(n, duration=d)) for b in ("feature/a", "main", "dev/x")
             for n in (0, 3, 12) for d in (60.0, 870.0, 4000.0)]
    for i, raw in enumerate(cases):
        raw["head_sha"] = f"{i:040x}"
        team = config(redispatch="reference-demo")
        before = advise(raw, team, deps())
        after = redispatch.record(raw, before, config=team, client=gh, now=NOW)
        if after["action"] == "defer":
            assert before["action"] == "defer" and after["defer_until"] == before["defer_until"]
            assert after["deferred"] is True
        else:
            assert after["deferred"] is False


# --------------------------------------------------------------------------- #
# The issue record.
# --------------------------------------------------------------------------- #

def _record_body(**changes: Any) -> str:
    raw, response, team = _deferral()
    gh = FakeGitHub()
    redispatch.record(raw, response, config=team, client=gh, now=NOW)
    body = gh.issues[0]["body"]
    data = json.loads(body.split("\n", 2)[1])
    data.update(changes)
    return body.replace(body.split("\n", 2)[1], json.dumps(data))


def test_the_record_round_trips():
    assert redispatch.parse_record(_record_body()).head_sha == SHA


@pytest.mark.parametrize("changes", [
    {"head_sha": "not-a-sha"}, {"repository": "bad repo"}, {"workflow": "ci.sh"},
    {"branch": "a\nb"}, {"key": "other|ci.yml|" + SHA}, {"extra": 1}, {"defer_until_utc": "tomorrow"},
    {"scenario": "yes"}, {"run_id": True},
])
def test_a_tampered_record_is_refused(changes):
    with pytest.raises(redispatch.RedispatchError):
        redispatch.parse_record(_record_body(**changes))


def test_an_issue_without_a_record_is_refused():
    with pytest.raises(redispatch.RedispatchError):
        redispatch.parse_record("please dispatch my build")


# --------------------------------------------------------------------------- #
# Dispatching.
# --------------------------------------------------------------------------- #

def _recorded(gh: FakeGitHub, **cfg: Any) -> dict:
    raw, response, team = _deferral(**cfg)
    redispatch.record(raw, response, config=team, client=gh, now=NOW)
    return response


def test_an_issue_that_is_not_due_is_left_alone():
    gh = FakeGitHub()
    _recorded(gh)
    [result] = redispatch.dispatch_due(gh, REPO, now=NOW)
    assert result["outcome"] == "not_due" and gh.dispatches == [] and gh.issues[0]["state"] == "open"


def test_a_due_issue_is_dispatched_once_at_the_same_sha_then_closed():
    gh = FakeGitHub()
    response = _recorded(gh)
    when = _due(response)
    [result] = redispatch.dispatch_due(gh, REPO, now=when)
    assert result["outcome"] == "dispatched" and result["reason"] == "due" and result["fallback"] is False
    assert gh.dispatches == [{"ref": "feature/login-cache", "inputs": {redispatch.DISPATCH_INPUT: SHA}}]
    assert gh.issues[0]["state"] == "closed" and "Dispatched" in gh.comments[1][0]
    assert redispatch.dispatch_due(gh, REPO, now=when + timedelta(hours=1)) == []
    assert len(gh.dispatches) == 1


def test_an_issue_already_dispatched_is_closed_without_dispatching_again():
    gh = FakeGitHub()
    response = _recorded(gh)
    gh.runs.append({"id": 7, "event": "workflow_dispatch", "head_sha": SHA,
                    "created_at": (NOW + timedelta(minutes=1)).isoformat()})
    [result] = redispatch.dispatch_due(gh, REPO, now=_due(response))
    assert result["outcome"] == "already_dispatched" and gh.dispatches == []
    assert gh.issues[0]["state"] == "closed"


def test_an_older_dispatch_of_the_same_sha_does_not_count():
    gh = FakeGitHub()
    response = _recorded(gh)
    gh.runs.append({"id": 7, "event": "workflow_dispatch", "head_sha": SHA,
                    "created_at": (NOW - timedelta(days=3)).isoformat()})
    [result] = redispatch.dispatch_due(gh, REPO, now=_due(response))
    assert result["outcome"] == "dispatched"


def test_an_untrusted_or_malformed_issue_is_refused_and_untouched():
    gh = FakeGitHub(creator="someone-else")
    response = _recorded(gh)
    [result] = redispatch.dispatch_due(gh, REPO, now=_due(response))
    assert result["outcome"] == "refused_untrusted" and gh.dispatches == []
    gh2 = FakeGitHub()
    _recorded(gh2)
    gh2.issues[0]["body"] = "dispatch please"
    [result] = redispatch.dispatch_due(gh2, REPO, now=_due(response))
    assert result["outcome"] == "refused_invalid" and gh2.dispatches == [] and gh2.issues[0]["state"] == "open"


def test_a_late_dispatcher_says_deadline_reached():
    gh = FakeGitHub()
    _recorded(gh)
    [result] = redispatch.dispatch_due(gh, REPO, now=NOW + timedelta(hours=30))
    assert result["outcome"] == "dispatched" and result["reason"] == "deadline reached"


def test_a_failed_dispatch_stays_open_and_is_not_retried_in_the_same_pass():
    gh = FakeGitHub()
    response = _recorded(gh)
    gh.fail[("POST", "/dispatches")] = 500
    [result] = redispatch.dispatch_due(gh, REPO, now=_due(response))
    assert result["outcome"] == "dispatch_failed" and gh.issues[0]["state"] == "open"
    assert sum(1 for m, p in gh.calls if p.endswith("/dispatches")) == 1
    del gh.fail[("POST", "/dispatches")]
    [result] = redispatch.dispatch_due(gh, REPO, now=_due(response) + timedelta(hours=1))
    assert result["outcome"] == "dispatched"


def test_a_deleted_branch_falls_back_to_the_default_branch():
    gh = FakeGitHub(branches=("main",))
    response = _recorded(gh)
    [result] = redispatch.dispatch_due(gh, REPO, now=_due(response))
    assert result["outcome"] == "dispatched" and result["fallback"] is True and result["ref"] == "main"
    assert gh.dispatches[0]["inputs"][redispatch.DISPATCH_INPUT] == SHA
    assert "default branch" in gh.comments[1][0]


def test_closing_an_issue_by_hand_cancels_the_deferral():
    gh = FakeGitHub()
    response = _recorded(gh)
    gh.issues[0]["state"] = "closed"
    assert redispatch.dispatch_due(gh, REPO, now=_due(response)) == [] and gh.dispatches == []


def test_pull_requests_in_the_issue_listing_are_ignored():
    gh = FakeGitHub()
    response = _recorded(gh)
    gh.issues.append({**gh.issues[0], "number": 2, "pull_request": {}})
    assert len(redispatch.dispatch_due(gh, REPO, now=_due(response))) == 1


def test_the_dispatch_summary_names_every_issue():
    gh = FakeGitHub()
    response = _recorded(gh)
    results = redispatch.dispatch_due(gh, REPO, now=_due(response))
    text = redispatch.render_dispatch_summary(REPO, results, _due(response))
    assert "| #1 | dispatched |" in text and "not pausing" in text


# --------------------------------------------------------------------------- #
# The CLI, end to end (offline).
# --------------------------------------------------------------------------- #

def test_the_cli_records_then_dispatches(tmp_path):
    gh = FakeGitHub()
    (tmp_path / "req.json").write_text(json.dumps(request(history=None)), encoding="utf-8")
    (tmp_path / "cfg.yml").write_text("compute_region: GB\nenabled_workflows: [ci.yml]\nredispatch: reference-demo\n",
                                      encoding="utf-8")
    status = cli.main(["advise", "--request", str(tmp_path / "req.json"), "--config", str(tmp_path / "cfg.yml"),
                       "--github", "--no-live", "--json-out", str(tmp_path / "out.json")],
                      deps=deps(history_source=lambda r, w, c: history(), github_client=gh))
    out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert status == 0 and out["deferred"] is True and len(gh.issues) == 1

    later = _due(out)
    status = cli.main(["dispatch", "--repo", REPO, "--json-out", str(tmp_path / "d.json"),
                       "--summary-out", str(tmp_path / "d.md")], deps=deps(now=lambda: later, github_client=gh))
    result = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert status == 0 and [r["outcome"] for r in result["results"]] == ["dispatched"]
    assert "dispatched" in (tmp_path / "d.md").read_text(encoding="utf-8")


def test_the_cli_without_redispatch_makes_no_write_call(tmp_path):
    gh = FakeGitHub()
    (tmp_path / "req.json").write_text(json.dumps(request(history=None)), encoding="utf-8")
    (tmp_path / "cfg.yml").write_text("compute_region: GB\nenabled_workflows: [ci.yml]\n", encoding="utf-8")
    cli.main(["advise", "--request", str(tmp_path / "req.json"), "--config", str(tmp_path / "cfg.yml"),
              "--github", "--no-live", "--json-out", str(tmp_path / "out.json")],
             deps=deps(history_source=lambda r, w, c: history(), github_client=gh))
    out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert out["action"] == "defer" and out["deferred"] is False and gh.calls == []


# --------------------------------------------------------------------------- #
# The client's write path.
# --------------------------------------------------------------------------- #

def _http_error(status: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com/x", status, "err", headers or {}, io.BytesIO(b""))


def test_a_write_is_not_retried_after_a_server_error():
    attempts = []

    def opener(req, timeout):
        attempts.append(req.get_method())
        raise _http_error(502)

    client = GitHubClient("t", opener=opener, sleep=lambda s: None)
    with pytest.raises(GitHubHTTPError) as err:
        client.send_json("POST", f"/repos/{REPO}/issues", {"title": "x"})
    assert err.value.status == 502 and attempts == ["POST"]


def test_a_rate_limited_write_is_retried_and_an_empty_body_is_none():
    replies = [_http_error(429, {"Retry-After": "1"}), FakeResponse(b"")]

    def opener(req, timeout):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        assert req.get_method() == "POST" and json.loads(req.data) == {"ref": "main"}
        return reply

    client = GitHubClient("t", opener=opener, sleep=lambda s: None)
    assert client.send_json("POST", f"/repos/{REPO}/actions/workflows/ci.yml/dispatches", {"ref": "main"}) is None
    assert client.requests_made == 2


def test_a_network_error_on_a_write_is_not_retried():
    attempts = []

    def opener(req, timeout):
        attempts.append(1)
        raise TimeoutError

    client = GitHubClient("t", opener=opener, sleep=lambda s: None)
    with pytest.raises(Exception):
        client.send_json("POST", f"/repos/{REPO}/issues", {})
    assert attempts == [1]

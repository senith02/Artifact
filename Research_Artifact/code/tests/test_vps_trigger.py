"""P4-T4 — the external exact-time trigger, carbon_tick.py (DL-038 §11). Offline."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

from advisor import redispatch

from tests.advisor_helpers import SHA

PATH = Path(__file__).resolve().parents[1] / "github-action" / "examples" / "vps-trigger" / "carbon_tick.py"
_spec = importlib.util.spec_from_file_location("carbon_tick", PATH)
carbon_tick = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carbon_tick)

REPO = "demo-owner/demo-repo"
DUE = datetime(2026, 10, 22, 2, 0, tzinfo=timezone.utc)


def _issue(number: int, due: datetime = DUE, *, creator: str = redispatch.TRUSTED_CREATOR, **extra) -> dict:
    record = redispatch.DeferralRecord(
        key=redispatch.deferral_key(REPO, "ci.yml", SHA), repository=REPO, workflow="ci.yml",
        branch="feature/x", head_sha=SHA, run_id=1, arrival_utc="2026-10-21T13:58:00+00:00",
        defer_until_utc=due.isoformat(), scenario=True, advisor_version="0.1.0")
    return {"number": number, "state": "open", "user": {"login": creator}, "body": record.body(), **extra}


class FakeGitHub:
    def __init__(self, issues):
        self.issues, self.started = list(issues), []

    def open_deferrals(self, repo):
        return [i for i in self.issues if i["state"] == "open"]

    def start_workflow(self, repo, workflow, ref):
        self.started.append((repo, workflow, ref))


def _ticker(gh, now, **kw):
    clock = {"now": now}
    t = carbon_tick.Ticker(gh, REPO, clock=lambda: clock["now"], logger=lambda m: None, **kw)
    return t, clock


def test_the_trigger_reads_the_issue_body_the_advisor_writes():
    assert carbon_tick.due_times([_issue(2)]) == [(2, DUE)]
    assert carbon_tick.RECORD_RE.pattern == redispatch._BODY_RE.pattern


def test_untrusted_pull_request_closed_and_malformed_issues_are_ignored():
    issues = [_issue(1, creator="someone"), _issue(2, pull_request={}), _issue(3, state="closed"),
              {"number": 4, "state": "open", "user": {"login": redispatch.TRUSTED_CREATOR}, "body": "hi"}]
    assert carbon_tick.due_times(issues) == []


def test_before_the_due_time_it_sleeps_until_exactly_then():
    gh = FakeGitHub([_issue(2)])
    ticker, _ = _ticker(gh, DUE - timedelta(minutes=3))
    pause = ticker.step()
    assert gh.started == [] and pause == 3 * 60 + 20  # wakes 20 s after the hour


def test_at_the_due_time_it_starts_the_dispatcher_once_for_all_due_issues():
    gh = FakeGitHub([_issue(2), _issue(3)])
    ticker, clock = _ticker(gh, DUE + timedelta(seconds=20))
    ticker.step()
    assert gh.started == [(REPO, "carbon-dispatch.yml", "main")]
    clock["now"] += timedelta(minutes=1)
    ticker.step()  # still open while the dispatcher runs: not triggered again
    assert len(gh.started) == 1


def test_an_issue_still_open_after_the_retry_window_is_triggered_again():
    gh = FakeGitHub([_issue(2)])
    ticker, clock = _ticker(gh, DUE)
    ticker.step()
    clock["now"] += timedelta(seconds=1200)
    ticker.step()
    assert len(gh.started) == 2


def test_a_closed_issue_is_forgotten_and_nothing_more_happens():
    issue = _issue(2)
    gh = FakeGitHub([issue])
    ticker, clock = _ticker(gh, DUE)
    ticker.step()
    issue["state"] = "closed"
    clock["now"] += timedelta(hours=2)
    pause = ticker.step()
    assert len(gh.started) == 1 and ticker.triggered == {} and pause == 300


def test_with_nothing_open_it_just_polls():
    ticker, _ = _ticker(FakeGitHub([]), DUE)
    assert ticker.step() == 300


def test_a_dry_run_triggers_nothing():
    gh = FakeGitHub([_issue(2)])
    ticker, _ = _ticker(gh, DUE, dry_run=True)
    ticker.step()
    assert gh.started == []


def test_main_refuses_to_run_without_a_token(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert carbon_tick.main(["--repo", REPO, "--once"]) == 2
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_errors_never_print_the_token():
    import urllib.error

    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "bad", {}, None)

    gh = carbon_tick.GitHub("secret-token-123", opener=opener)
    try:
        gh.open_deferrals(REPO)
    except RuntimeError as exc:
        assert "401" in str(exc) and "secret-token-123" not in str(exc)

"""P4-T1 — completed-run history, the GitHub client and the live-carbon parsers.

Defended: only completed, success/failure, same-workflow runs that finished
before the arrival can inform d̂ (R3-B4, DL-034); the GitHub client paginates to
a cap, retries within bounds, honours rate limits and never leaks its token;
response parsing matches the real shapes captured on 2026-10-04.
"""

from __future__ import annotations

import urllib.error
from datetime import datetime, timezone

import pytest

from advisor import carbon_live
from advisor.github import GitHubClient, GitHubHistorySource, run_to_history_entry
from advisor.history import HistoryError, filter_admissible, parse_history, parse_history_entry

from tests.advisor_helpers import FakeResponse, fixture_json, history

ARRIVAL = datetime(2026, 10, 1, 18, 5, tzinfo=timezone.utc)


def _entry(**overrides):
    base = history(1)[0]
    base.update(overrides)
    return base


def test_only_completed_finished_same_workflow_runs_are_admitted():
    runs = parse_history([
        _entry(run_id=1),                                                       # admitted (failure)
        _entry(run_id=2, conclusion="success"),                                 # admitted
        _entry(run_id=3, status="queued"),
        _entry(run_id=4, status="in_progress", conclusion=None),
        _entry(run_id=5, conclusion="cancelled"),
        _entry(run_id=6, conclusion="timed_out"),                               # censored duration
        _entry(run_id=7, conclusion="skipped"),
        _entry(run_id=8, workflow="other.yml"),
        _entry(run_id=2000),                                                    # the scored run itself
        _entry(run_id=9, duration_s=0.0),
        # started before arrival, still running at arrival (start + duration > arrival)
        _entry(run_id=10, run_started_at="2026-10-01T18:00:00Z", updated_at="2026-10-01T18:04:00Z",
               duration_s=900.0),
        # GitHub's updated_at after arrival, even though start + duration is before it
        _entry(run_id=11, run_started_at="2026-10-01T17:00:00Z", updated_at="2026-10-01T18:06:00Z",
               duration_s=60.0),
    ])
    admitted, dropped = filter_admissible(runs, workflow="ci.yml", run_id=2000, arrival=ARRIVAL)
    assert [r.run_id for r in admitted] == [1, 2]
    assert dropped == {"not_completed": 2, "conclusion_excluded": 3, "other_workflow": 1, "same_run": 1,
                       "nonpositive_duration": 1, "finished_after_arrival": 2}


def test_history_entries_have_a_closed_schema():
    with pytest.raises(HistoryError):
        parse_history_entry(_entry(actor="someone"))
    with pytest.raises(HistoryError):
        parse_history_entry({k: v for k, v in _entry().items() if k != "updated_at"})
    with pytest.raises(HistoryError):
        parse_history_entry(_entry(run_started_at="not a time"))


# --------------------------------------------------------------------------- #
# GitHub client, against a fake opener (no network).
# --------------------------------------------------------------------------- #

def _http_error(code, headers=None):
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", headers or {}, None)


class Opener:
    """Replays a scripted sequence of responses/errors and records the requests."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


def _runs_page(n, start_id, total):
    run = fixture_json("gh_runs_page1.json")["workflow_runs"][0]
    return {"total_count": total, "workflow_runs": [{**run, "id": start_id + i} for i in range(n)]}


def test_pagination_stops_at_the_cap():
    opener = Opener([_runs_page(100, 1, 237), _runs_page(100, 101, 237)])
    client = GitHubClient(opener=opener, sleep=lambda s: None)
    runs = list(client.iter_completed_runs("pallets/flask", "tests.yaml", cap=150))
    assert len(runs) == 150 and len(opener.requests) == 2
    assert "status=completed" in opener.requests[0].full_url and "page=2" in opener.requests[1].full_url


def test_pagination_stops_at_the_last_page():
    opener = Opener([_runs_page(100, 1, 137), _runs_page(37, 101, 137)])
    runs = list(GitHubClient(opener=opener).iter_completed_runs("o/r", "ci.yml", cap=500))
    assert len(runs) == 137 and len(opener.requests) == 2


def test_server_errors_are_retried_with_backoff():
    sleeps = []
    opener = Opener([_http_error(502), _runs_page(3, 1, 3)])
    runs = list(GitHubClient(opener=opener, sleep=sleeps.append).iter_completed_runs("o/r", "ci.yml", 10))
    assert len(runs) == 3 and sleeps == [1.0]


def test_retry_after_is_honoured():
    sleeps = []
    opener = Opener([_http_error(429, {"Retry-After": "3"}), _runs_page(1, 1, 1)])
    list(GitHubClient(opener=opener, sleep=sleeps.append).iter_completed_runs("o/r", "ci.yml", 10))
    assert sleeps == [3.0]


def test_an_exhausted_rate_limit_with_a_far_reset_gives_up_at_once():
    headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "10000"}
    opener = Opener([_http_error(403, headers)])
    client = GitHubClient(opener=opener, sleep=lambda s: pytest.fail("must not sleep"), clock=lambda: 0.0)
    with pytest.raises(HistoryError, match="rate limited"):
        list(client.iter_completed_runs("o/r", "ci.yml", 10))


def test_client_errors_are_not_retried_and_never_carry_the_token():
    opener = Opener([_http_error(404)])
    client = GitHubClient("ghs_SECRET_TOKEN", opener=opener)
    with pytest.raises(HistoryError) as info:
        list(client.iter_completed_runs("o/r", "ci.yml", 10))
    assert "ghs_SECRET_TOKEN" not in str(info.value) and len(opener.requests) == 1
    assert opener.requests[0].get_header("Authorization") == "Bearer ghs_SECRET_TOKEN"


def test_network_failure_after_all_attempts_is_a_history_error():
    opener = Opener([urllib.error.URLError("down")] * 3)
    with pytest.raises(HistoryError, match="after 3 attempts"):
        list(GitHubClient(opener=opener, sleep=lambda s: None).iter_completed_runs("o/r", "ci.yml", 10))


def test_real_run_shape_becomes_a_history_entry_matching_the_timing_endpoint():
    run = fixture_json("gh_runs_page1.json")["workflow_runs"][0]
    wall = run_to_history_entry(run, "tests.yaml")
    assert wall["duration_source"] == "wallclock" and wall["duration_s"] == 40.0
    assert wall["workflow"] == "tests.yaml" and wall["status"] == "completed"
    timing = fixture_json("gh_timing.json")["run_duration_ms"]
    timed = run_to_history_entry(run, "tests.yaml", timing_ms=timing)
    assert timed["duration_source"] == "timing" and timed["duration_s"] == 40.0
    parse_history_entry(wall)          # the produced entry satisfies the closed schema


def test_history_source_spends_only_its_timing_budget():
    page = fixture_json("gh_runs_page1.json")
    opener = Opener([page, fixture_json("gh_timing.json"), fixture_json("gh_timing.json")])
    source = GitHubHistorySource(GitHubClient(opener=opener), timing_budget=2)
    entries = source("pallets/flask", "tests.yaml", cap=5)
    assert len(entries) == 5
    assert [e["duration_source"] for e in entries] == ["timing", "timing", "wallclock", "wallclock", "wallclock"]


# --------------------------------------------------------------------------- #
# Live carbon parsers (display only), against the real captured shapes.
# --------------------------------------------------------------------------- #

def test_live_national_and_regional_parse_the_real_shapes():
    national = carbon_live.fetch_national(opener=lambda r, t: FakeResponse(fixture_json("ci_national.json")))
    assert national == {"gco2_per_kwh": 162.0, "kind": "actual", "from": "2026-10-04T16:30Z",
                        "to": "2026-10-04T17:00Z"}
    regional = carbon_live.fetch_regional("EC1A",
                                          opener=lambda r, t: FakeResponse(fixture_json("ci_regional_postcode.json")))
    assert regional["gco2_per_kwh"] == 206.0 and regional["region"] == "London"
    by_id = carbon_live.fetch_regional(13, opener=lambda r, t: FakeResponse(fixture_json("ci_regional_regionid.json")))
    assert by_id["gco2_per_kwh"] == 206.0


def test_live_lookups_return_none_on_any_failure():
    def broken(req, timeout):
        raise urllib.error.URLError("down")
    assert carbon_live.fetch_national(opener=broken) is None
    assert carbon_live.fetch_regional("EC1A", opener=broken) is None
    assert carbon_live.fetch_national(opener=lambda r, t: FakeResponse(b"not json")) is None

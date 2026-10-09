"""P4-T3 — the Repo What-If Report (DL-033 R3-C8, R3-I; DL-037).

Offline: a synthetic snapshot (illustrative inputs, not a result). Covers
determinism (JSON and HTML byte-identical), "every number on the page is in the
JSON", the accounting boundary (spy + metamorphic), the run accounting, the
privacy filter, the output-path refusal and the CLI.
"""

from __future__ import annotations

import copy
import html as html_mod
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import advisor.core as core_mod
from advisor import cli, whatif
from advisor.core import decision_view
from advisor.github import GitHubClient
from advisor.whatif_html import render_html

from tests.advisor_helpers import FakeResponse, iso

START = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)


def _run(i: int, *, event="push", branch="feature/cache", conclusion=None, duration=900.0,
         message="Improve cache", status="completed") -> dict:
    created = START + timedelta(hours=7 * i)
    started = created + timedelta(seconds=10)
    return {"run_id": 5000 + i, "workflow": "ci.yml", "event": event, "head_branch": branch,
            "head_sha": f"{i:040x}", "status": status,
            "conclusion": conclusion or ("failure" if i % 3 == 0 else "success"), "run_attempt": 1,
            "created_at": iso(created), "run_started_at": iso(started),
            "updated_at": iso(started + timedelta(seconds=duration)), "head_commit_message": message}


def make_snapshot(n: int = 90) -> dict:
    runs = []
    for i in range(n):
        if i % 5 == 1:
            runs.append(_run(i, branch="main"))
        elif i % 5 == 2:
            runs.append(_run(i, event="pull_request", branch="feature/pr"))
        elif i % 11 == 4:
            runs.append(_run(i, message="[urgent] hotfix"))
        elif i % 13 == 7:
            runs.append(_run(i, duration=120.0))
        else:
            runs.append(_run(i))
    runs.append(_run(n, conclusion="cancelled"))
    runs.append(_run(n + 1, event="pull_request_target"))
    broken = _run(n + 2)
    broken["run_started_at"] = None
    runs.append(broken)
    last = START + timedelta(hours=7 * (n + 3))
    return {"snapshot_schema": 1, "repository": "demo-owner/demo-repo", "workflow": "ci.yml",
            "fetched_at": iso(last), "history_cap": 500, "repo_total_completed_runs": len(runs),
            "repo_language": "Python", "runs": list(reversed(runs))}  # API order: newest first


@pytest.fixture(scope="module")
def snapshot():
    return make_snapshot()


@pytest.fixture(scope="module")
def report(snapshot):
    return whatif.build_report(snapshot, whatif.replay(snapshot))


# --------------------------------------------------------------------------- #
# What the report says.
# --------------------------------------------------------------------------- #

def test_runs_are_partitioned_and_counted(report, snapshot):
    runs, d = report["runs"], report["decisions"]
    assert runs["fetched"] == len(snapshot["runs"]) == runs["analysed"] + runs["excluded_total"]
    assert runs["excluded"] == {"conclusion_cancelled": 1, "unplaceable": 1}
    assert d["deferred"] + sum(d["run_now_reasons"].values()) == d["analysed"] == runs["analysed"]
    assert d["deferred"] > 0 and {"pull_request", "protected_branch"} <= set(d["run_now_reasons"])
    assert d["fail_safe_codes"] == {"untrusted_event": 1}
    assert "urgent_marker" in d["veto_codes"] and "cold_start" in d["veto_codes"]
    assert report["banner"] == "Demonstration — not research evidence"


def test_carbon_band_and_ttff(report):
    band = report["carbon"]["band"]
    assert [b["multiplier"] for b in band] == [0.5, 1.0, 1.5]
    assert all(b["advisor_g"] <= b["run_now_g"] for b in band)  # deferral only ever moves to a greener slot
    assert report["carbon"]["change_pct"] < 0 and report["carbon"]["label"] == "estimated, not measured"
    ttff = report["ttff_failed"]
    assert ttff["failed_runs"] >= 20 and ttff["computed"] and ttff["p95_hours_advisor"] >= ttff["p95_hours_run_now"]


def test_ttff_is_not_computable_below_twenty_failures():
    snap = make_snapshot(20)
    rep = whatif.build_report(snap, whatif.replay(snap))
    assert rep["ttff_failed"]["computed"] is False and rep["ttff_failed"]["p95_hours_advisor"] is None
    assert rep["ttff_failed"]["note"] == f"not computable (n = {rep['ttff_failed']['failed_runs']})"


def test_rungs_and_cold_start(report):
    rc = report["rung_coverage"]
    assert rc["cold_start_runs"] >= 1 and rc["project"] > 0
    assert report["snapshot"]["window_truncated"] is False


# --------------------------------------------------------------------------- #
# The accounting boundary (A1.2 role 1): observed duration only after decide().
# --------------------------------------------------------------------------- #

def test_decide_sees_only_the_frozen_inputs(snapshot, monkeypatch):
    seen = []
    real = core_mod.decide
    monkeypatch.setattr(core_mod, "decide", lambda build, *a, **k: seen.append(dict(build)) or real(build, *a, **k))
    whatif.replay(snapshot)
    assert seen and all(set(b) <= {"gh_is_pr", "git_branch", "arrival_dow", "arrival_hour", "d_hat_seconds"}
                        for b in seen)


def test_a_runs_own_duration_never_changes_its_own_decision(snapshot):
    """Metamorphic: stretch each sampled run's own duration ×5; its decision must not move."""
    base = whatif.replay(snapshot)
    order = sorted(snapshot["runs"], key=lambda r: (str(r["created_at"]), r["run_id"]))
    for idx in (3, 17, 40, 77):
        target = order[idx]["run_id"]
        altered = copy.deepcopy(snapshot)
        for run in altered["runs"]:
            if run["run_id"] == target:
                start = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                run["updated_at"] = iso(start + (end - start) * 5)
        changed = whatif.replay(altered)
        assert decision_view(changed[idx]["response"]) == decision_view(base[idx]["response"])
        assert changed[idx]["observed_duration_s"] != base[idx]["observed_duration_s"]


def test_the_request_carries_no_duration_or_outcome_of_its_own_run(snapshot):
    run = snapshot["runs"][5]
    request = whatif._request(snapshot, run, [])
    assert not {"duration_s", "conclusion", "status", "tr_duration", "tr_status"} & set(request)


# --------------------------------------------------------------------------- #
# Determinism and the HTML view.
# --------------------------------------------------------------------------- #

def test_json_and_html_are_byte_identical_on_rerun(snapshot, report, tmp_path):
    again = whatif.build_report(snapshot, whatif.replay(snapshot))
    assert whatif.canonical_json(again) == whatif.canonical_json(report)
    a = whatif.write_report(report, tmp_path / "a")
    b = whatif.write_report(json.loads(whatif.canonical_json(report)), tmp_path / "b")
    assert a == b
    for name in ("report.json", "report.html", "report.md"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


_NUM = re.compile(r"\d+(?:\.\d+)?")


def _page_text(page: str) -> str:
    page = re.sub(r"<style>.*?</style>", " ", page, flags=re.S)
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", page))


def test_every_number_on_the_page_is_in_the_json(report):
    page = render_html(report)
    json_tokens = set(_NUM.findall(whatif.canonical_json(report)))
    page_tokens = set(_NUM.findall(_page_text(page)))
    assert page_tokens and page_tokens <= json_tokens, sorted(page_tokens - json_tokens)


def test_the_page_is_static_and_labelled(report):
    page = render_html(report)
    assert "<script" not in page.lower() and "http://" not in page and "https://" not in page
    assert "Demonstration — not research evidence" in page and "SCENARIO" in page
    for statement in report["statements"][1:]:
        assert html_mod.escape(statement, quote=True) in page
    assert report["policy"]["spec_sha256"] in page and report["snapshot"]["sha256"] in page


# --------------------------------------------------------------------------- #
# Privacy, output paths, fetching and the CLI.
# --------------------------------------------------------------------------- #

def test_the_snapshot_drops_people_and_redacts_emails():
    raw = {"id": 1, "path": ".github/workflows/ci.yml", "event": "push", "head_branch": "x", "head_sha": "a" * 40,
           "status": "completed", "conclusion": "success", "run_attempt": 1, "created_at": "2026-10-01T00:00:00Z",
           "run_started_at": "2026-10-01T00:00:05Z", "updated_at": "2026-10-01T00:10:00Z",
           "actor": {"login": "someone"}, "triggering_actor": {"login": "someone"},
           "head_commit": {"message": "Fix\n\nCo-authored-by: A Person <a.person@example.com>",
                           "author": {"name": "A Person", "email": "a.person@example.com"}}}
    run = whatif.snapshot_run(raw)
    text = json.dumps(run)
    assert "someone" not in text and "example.com" not in text and "A Person <<email>>" in run["head_commit_message"]
    assert run["workflow"] == "ci.yml"


@pytest.mark.parametrize("bad", ["results/p0/x", "results/p3", "../results/p2/whatif", "a/results/p1/b"])
def test_outputs_are_refused_under_the_research_results(bad):
    with pytest.raises(whatif.WhatIfError):
        whatif.check_output_dir(bad)


def test_outputs_under_p4_are_allowed(tmp_path):
    assert whatif.check_output_dir(tmp_path / "results" / "p4" / "whatif")


def test_fetch_pages_and_records_totals():
    pages = {1: {"total_count": 150, "workflow_runs": [
        {"id": i, "path": ".github/workflows/ci.yml", "status": "completed"} for i in range(1, 101)]},
             2: {"total_count": 150, "workflow_runs": [
                 {"id": i, "path": ".github/workflows/ci.yml", "status": "completed"} for i in range(101, 151)]}}
    calls = []

    def opener(request, timeout):
        url = request.full_url
        calls.append(url)
        if url.endswith("/repos/o/r"):
            return FakeResponse({"language": "Go"})
        page = int(re.search(r"[?&]page=(\d+)", url).group(1))
        return FakeResponse(pages[page])

    snap = whatif.fetch_snapshot(GitHubClient(opener=opener), "o/r", "ci.yml", cap=120,
                                 now=datetime(2026, 10, 8, tzinfo=timezone.utc))
    assert len(snap["runs"]) == 120 and snap["repo_total_completed_runs"] == 150
    assert snap["repo_language"] == "Go" and snap["fetched_at"] == "2026-10-08T00:00:00Z"
    assert all("status=completed" in c for c in calls if "/runs" in c)


def test_cli_whatif_from_a_snapshot(snapshot, tmp_path):
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(whatif.canonical_json(snapshot), encoding="utf-8")
    out = tmp_path / "results" / "p4" / "whatif" / "demo"
    assert cli.main(["whatif", "--repo", "demo-owner/demo-repo", "--workflow", "ci.yml",
                     "--snapshot", str(snap_path), "--out", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == {"report.json", "report.md", "report.html"}
    assert cli.main(["whatif", "--repo", "other/repo", "--workflow", "ci.yml",
                     "--snapshot", str(snap_path), "--out", str(out)]) == 1
    assert cli.main(["whatif", "--repo", "demo-owner/demo-repo", "--workflow", "ci.yml",
                     "--snapshot", str(snap_path), "--out", str(tmp_path / "results" / "p3")]) == 1

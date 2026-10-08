"""P4-T1 — one core, three surfaces (invariant 5; DL-033 R3-E).

1. **Three-way parity**: the same request gives the identical decision from the
   in-process advisor, the CLI and the REST API, and that decision is
   ``scheduler_core.policy.decide()``'s own.
2. **d̂ parity**: on a Travis-shaped fixture, the advisor's d̂ and rung equal the
   frozen estimator's ``causal_project_history`` + ``predict_4b`` exactly.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from advisor.cli import main as cli_main
from advisor.core import advise, decision_view
from advisor.estimate import estimate_d_hat
from advisor.frozen import default_frozen_core
from advisor.history import HistoryRun
from api.app import create_app
from scheduler_core import duration_estimator as de
from scheduler_core import features
from scheduler_core.policy import decide

from tests.advisor_helpers import config, deps, history, request

CASES = {
    "defer": request(),
    "protected_branch": request(branch="main"),
    "pull_request": request(event="pull_request", is_pr=True, branch="feature/x"),
    "cold_start_veto": request(history=[], repo_language="Java"),
    "short_build": request(history=history(10, duration=120.0)),
    "east_us_fail_safe": request(compute_region="US-EAST"),
    "scenario": request(scenario="gb-hypothetical"),
}


def _config_for(name):
    return config(compute_region="US-EAST") if name == "east_us_fail_safe" else config()


@pytest.mark.parametrize("name", sorted(CASES))
def test_three_way_parity(name, tmp_path):
    raw, cfg = CASES[name], _config_for(name)

    in_process = advise(raw, cfg, deps())

    req_path, cfg_path, out_path = tmp_path / "req.json", tmp_path / "cfg.yml", tmp_path / "out.json"
    req_path.write_text(json.dumps(raw), encoding="utf-8")
    cfg_path.write_text(f"compute_region: {cfg.compute_region}\nenabled_workflows: [ci.yml]\n", encoding="utf-8")
    assert cli_main(["advise", "--request", str(req_path), "--config", str(cfg_path), "--no-live",
                     "--json-out", str(out_path)], deps=deps()) == 0
    via_cli = json.loads(out_path.read_text(encoding="utf-8"))

    client = TestClient(create_app(config=cfg, deps=deps()))
    via_api = client.post("/decision", json=raw).json()

    assert decision_view(in_process) == decision_view(via_cli) == decision_view(via_api)


@pytest.mark.parametrize("name", ["defer", "protected_branch", "pull_request", "cold_start_veto", "short_build"])
def test_the_advisor_decision_is_decides_own(name):
    raw = CASES[name]
    r = advise(raw, config(), deps())
    core = default_frozen_core()
    arrival = datetime.fromisoformat(raw["arrival_utc"])
    build = {"gh_is_pr": raw["is_pr"], "git_branch": raw["branch"],
             "arrival_dow": arrival.weekday(), "arrival_hour": arrival.hour}
    if r["eligible"]:
        build["d_hat_seconds"] = r["d_hat_seconds"]
    direct = decide(build, core.profile, core.spec)
    assert r["policy_action"] == direct.action
    assert r["reason"].startswith(direct.reason)
    assert r["stage1_rule"] == direct.stage1_rule and r["window_hours"] == direct.window_hours
    if direct.action == "defer":
        assert {k: r["policy_defer_until"][k] for k in direct.defer_until} == dict(direct.defer_until)


# --------------------------------------------------------------------------- #
# d̂ parity on a Travis-shaped fixture.
# --------------------------------------------------------------------------- #

def _travis_fixture():
    """One project's builds in TravisTorrent columns: overlapping runs, a tie, a missing label."""
    t0 = datetime(2015, 3, 2, 9, 0, tzinfo=timezone.utc)
    rows = [  # (start offset minutes, duration s)
        (0, 600), (5, 1200), (30, 300), (31, 300), (90, 0), (95, 2400), (96, 900),
        (180, 450), (180, 451), (240, 700), (241, 60), (300, 3600), (305, 30),
    ]
    starts = [t0 + timedelta(minutes=m) for m, _ in rows]
    frame = pd.DataFrame({de.PROJECT_COL: "owner/proj",
                          de.TIME_COL: [s.strftime(features.TIMESTAMP_FORMAT) for s in starts]})
    durations = pd.Series([float(d) if d > 0 else np.nan for _, d in rows])
    return frame, durations, starts


def test_advisor_d_hat_equals_the_frozen_estimator_on_a_travis_fixture():
    estimator = default_frozen_core().estimator
    frame, durations, starts = _travis_fixture()
    lang = pd.DataFrame({"lang": ["ruby"] * len(frame)})
    expected = estimator.predict_4b(lang, de.causal_project_history(frame, durations), min_history=1)

    for i, arrival in enumerate(starts):
        admitted = [HistoryRun(run_id=j + 1, workflow="ci.yml", status="completed", conclusion="success",
                               run_started_at=starts[j],
                               updated_at=starts[j] + timedelta(seconds=float(durations[j])),
                               duration_s=float(durations[j]))
                    for j in range(len(starts)) if j != i and not np.isnan(durations[j])
                    and starts[j] + timedelta(seconds=float(durations[j])) < arrival]
        got = estimate_d_hat(estimator, admitted, arrival=arrival, project_key="owner/proj",
                             repo_language="Ruby")
        row = expected.iloc[i]
        assert got.n_history == int(row["n_history"]), i
        assert got.rung == row["fallback_level"], i
        assert got.seconds == pytest.approx(float(row["d_hat_seconds"]), rel=0, abs=1e-9), i


def test_unknown_languages_fall_to_the_global_rung():
    estimator = default_frozen_core().estimator
    arrival = datetime(2026, 10, 1, 18, 5, tzinfo=timezone.utc)
    got = estimate_d_hat(estimator, [], arrival=arrival, project_key="o/r:ci.yml", repo_language="Rust")
    assert got.rung == "global" and got.n_history == 0
    assert got.seconds == pytest.approx(float(np.expm1(estimator.global_prior_log1p)))

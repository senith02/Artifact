"""P4-T1 — the REST surface's hardening (DL-033 rev 2 §B9; context/p4_interface.md §8).

Body cap, token header, no CORS, invalid JSON as a fail-safe decision, no
history fetching, loopback-only binding without a token, and the CLI's
`api_unreachable` fail-safe.
"""

from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

import api.__main__ as api_main
from advisor.cli import main as cli_main
from api.app import MAX_BODY_BYTES, create_app

from tests.advisor_helpers import config, deps, request


def test_health_reports_the_pins():
    body = TestClient(create_app(config=config(), deps=deps())).get("/health").json()
    assert body["status"] == "ok" and body["config_loaded"] is True
    assert body["pins"]["estimator_fit_id"] == "1088d5546f47ff12"


def test_oversized_bodies_are_refused():
    client = TestClient(create_app(config=config(), deps=deps()))
    big = json.dumps({"pad": "x" * (MAX_BODY_BYTES + 1)})
    assert client.post("/decision", content=big, headers={"Content-Type": "application/json"}).status_code == 413


def test_a_configured_token_is_required():
    client = TestClient(create_app(config=config(), deps=deps(), token="s3cret"))
    assert client.post("/decision", json=request()).status_code == 401
    assert client.post("/decision", json=request(), headers={"X-Advisor-Token": "wrong"}).status_code == 401
    ok = client.post("/decision", json=request(), headers={"X-Advisor-Token": "s3cret"})
    assert ok.status_code == 200 and ok.json()["action"] == "defer"


def test_invalid_json_is_a_fail_safe_decision():
    client = TestClient(create_app(config=config(), deps=deps()))
    r = client.post("/decision", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and r.json()["fail_safe_code"] == "invalid_request"


def test_no_cors_headers_are_sent():
    client = TestClient(create_app(config=config(), deps=deps()))
    r = client.post("/decision", json=request(), headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_the_api_never_fetches_history():
    calls = []
    d = deps(history_source=lambda *a: calls.append(a) or [])
    r = TestClient(create_app(config=config(), deps=d)).post("/decision", json=request(history=None)).json()
    assert calls == [] and r["n_history"] == 0 and r["vetoes"] == ["cold_start"]


def test_the_api_without_a_config_fails_safe():
    r = TestClient(create_app(deps=deps())).post("/decision", json=request()).json()
    assert r["fail_safe_code"] == "config_invalid"


def test_non_loopback_binding_requires_a_token(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["api", "--host", "0.0.0.0"])
    monkeypatch.delenv("ADVISOR_API_TOKEN", raising=False)
    monkeypatch.setattr(api_main.uvicorn, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("started")))
    assert api_main.main() == 2
    assert api_main._is_loopback("127.0.0.1") and api_main._is_loopback("localhost")
    assert not api_main._is_loopback("0.0.0.0")


def test_cli_in_api_mode_fails_safe_when_the_api_is_down(tmp_path):
    req = tmp_path / "req.json"
    req.write_text(json.dumps(request()), encoding="utf-8")
    out = tmp_path / "out.json"
    assert cli_main(["advise", "--request", str(req), "--api-url", "http://127.0.0.1:9",
                     "--json-out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["fail_safe_code"] == "api_unreachable"


def test_cli_audit_log_is_idempotent_and_validator_readable(tmp_path):
    from replay import validate_invariants

    req, cfg, log = tmp_path / "req.json", tmp_path / "cfg.yml", tmp_path / "audit.jsonl"
    req.write_text(json.dumps(request()), encoding="utf-8")
    cfg.write_text("compute_region: GB\nenabled_workflows: [ci.yml]\n", encoding="utf-8")
    args = ["advise", "--request", str(req), "--config", str(cfg), "--no-live", "--audit-log", str(log),
            "--json-out", str(tmp_path / "o.json")]
    assert cli_main(args, deps=deps()) == 0
    assert cli_main(args, deps=deps()) == 0
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["duplicate"] for r in records] == [False, True]
    assert records[0]["action"] == records[1]["action"] == "defer"
    assert "history" not in records[0]["inputs"] and records[0]["inputs"]["history_entries"] == 12
    import pandas as pd
    result = validate_invariants.audit_frame(pd.DataFrame(records))
    assert result.violations == 0 and not result.missing_columns

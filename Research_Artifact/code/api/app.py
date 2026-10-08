"""FastAPI app: ``POST /decision`` and ``GET /health`` (context/p4_interface.md §8).

The body is read as raw JSON and handed to the same ``advise_with_audit`` the
CLI uses, so the request validator, the decision and the fail-safes are one
implementation (invariant 5, parity-tested). Hardening per DL-033 rev 2 §B9:

- the request body is capped (413 above the limit);
- a token header is required whenever a token is configured (401 otherwise);
- no CORS middleware is installed, so browsers on other origins cannot call it;
- the service never fetches history and makes no outbound request except the
  display-only live-carbon lookups, and only when enabled (DL-035 §3c).
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from advisor import ADVISOR_VERSION, carbon_live
from advisor.audit import AuditLog, advise_with_audit
from advisor.config import ConfigError, TeamConfig, load_team_config
from advisor.core import Dependencies, _fail_safe
from advisor.frozen import PINS

MAX_BODY_BYTES = 256 * 1024


def create_app(
    *,
    config: TeamConfig | Exception | None = None,
    config_path: str | Path | None = None,
    token: str | None = None,
    deps: Dependencies | None = None,
    audit_log: str | Path | None = None,
    live_carbon: bool = False,
) -> FastAPI:
    if config is None and config_path is not None:
        try:
            config = load_team_config(config_path)
        except ConfigError as exc:
            config = exc
    if config is None:
        config = ConfigError("the API was started without a team config (ADVISOR_CONFIG)")
    deps = deps or Dependencies()
    deps.history_source = None          # the API never fetches history (DL-035 §3c)
    if live_carbon:
        deps.live_national = deps.live_national or carbon_live.fetch_national
        deps.live_regional = deps.live_regional or carbon_live.fetch_regional
    log = AuditLog(audit_log) if audit_log else None

    app = FastAPI(title="Carbon-deferral advisor", version=ADVISOR_VERSION,
                  docs_url=None, redoc_url=None, openapi_url=None)

    def _authorised(request: Request) -> bool:
        if not token:
            return True
        supplied = request.headers.get("X-Advisor-Token", "")
        return secrets.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))

    @app.post("/decision")
    async def decision(request: Request) -> JSONResponse:
        if not _authorised(request):
            return JSONResponse({"error": "missing or invalid X-Advisor-Token"}, status_code=401)
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return JSONResponse({"error": f"request body over {MAX_BODY_BYTES} bytes"}, status_code=413)
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return JSONResponse({"error": f"request body over {MAX_BODY_BYTES} bytes"}, status_code=413)
        try:
            payload: Any = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = _fail_safe("invalid_request", "request body is not valid JSON")
            response["duplicate"] = False
            return JSONResponse(response)
        return JSONResponse(json.loads(json.dumps(advise_with_audit(payload, config, deps, log), default=str)))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "advisor_version": ADVISOR_VERSION,
                "config_loaded": isinstance(config, TeamConfig),
                "pins": {"spec_sha256": PINS.spec_sha256, "profile_sha256": PINS.profile_sha256,
                         "estimator_fit_id": PINS.estimator_fit_id}}

    return app

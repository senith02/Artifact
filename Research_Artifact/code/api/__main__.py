"""``python -m api`` — serve the advisor on localhost (context/p4_interface.md §8).

Binding to anything other than a loopback address requires ``ADVISOR_API_TOKEN``.
Team config: ``ADVISOR_CONFIG``; optional audit log: ``ADVISOR_AUDIT_LOG``;
live display-only intensity: ``ADVISOR_LIVE_CARBON=1``.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys

import uvicorn

from .app import create_app


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    token = os.environ.get("ADVISOR_API_TOKEN") or None
    if not _is_loopback(args.host) and not token:
        print("refusing to bind a non-loopback address without ADVISOR_API_TOKEN", file=sys.stderr)
        return 2
    app = create_app(config_path=os.environ.get("ADVISOR_CONFIG"), token=token,
                     audit_log=os.environ.get("ADVISOR_AUDIT_LOG"),
                     live_carbon=os.environ.get("ADVISOR_LIVE_CARBON") == "1")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Live GB carbon intensity — **display only** (DL-033 R3-B5, R3-J2).

Nothing returned here may reach ``decide()``, a veto or an estimate: the
decision of record uses the frozen national hour-of-week profile it was
evaluated on. Every failure returns ``None`` and the decision is unchanged.
Response shapes were checked against real calls on 2026-10-04
(``results/p4/endpoint_check/``): national ``data[0].intensity.{actual,forecast}``;
regional ``data[0].data[0].intensity.forecast`` (no ``actual``).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Callable

API_ROOT = "https://api.carbonintensity.org.uk"
Opener = Callable[[urllib.request.Request, float], Any]


def _default_opener(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed https host


def _get(path: str, opener: Opener, timeout: float) -> Any:
    request = urllib.request.Request(API_ROOT + path, headers={"Accept": "application/json",
                                                               "User-Agent": "carbon-deferral-advisor"})
    with opener(request, timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_national(opener: Opener = _default_opener, timeout: float = 5.0) -> dict[str, Any] | None:
    """Current national GB intensity, or None."""
    try:
        block = _get("/intensity", opener, timeout)["data"][0]
        intensity = block["intensity"]
        actual, forecast = intensity.get("actual"), intensity.get("forecast")
        value, kind = (actual, "actual") if isinstance(actual, (int, float)) else (forecast, "forecast")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return {"gco2_per_kwh": float(value), "kind": kind, "from": block.get("from"), "to": block.get("to")}
    except Exception:
        return None


def fetch_regional(region: str | int, opener: Opener = _default_opener,
                   timeout: float = 5.0) -> dict[str, Any] | None:
    """Current regional GB intensity for an outward postcode or a region id, or None."""
    try:
        path = (f"/regional/regionid/{int(region)}" if isinstance(region, int)
                else f"/regional/postcode/{urllib.parse.quote(str(region))}")
        area = _get(path, opener, timeout)["data"][0]
        block = area["data"][0]
        value = block["intensity"].get("forecast")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return {"gco2_per_kwh": float(value), "kind": "forecast", "region": area.get("shortname"),
                "from": block.get("from"), "to": block.get("to")}
    except Exception:
        return None

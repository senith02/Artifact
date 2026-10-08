"""Team config — `.github/carbon-advisor.yml` (context/p4_interface.md §5).

Closed schema, ``yaml.safe_load`` only. Every key the team controls can only
make the advisor *safer*: it narrows which workflows are advised, adds urgency
vetoes, or shortens the acceptable delay. None can widen what the frozen policy
would defer (DL-033 R3-B6).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from .contract import TRUSTED_EVENTS

#: The evaluated window. A team may only shorten it (R3-B7).
MAX_DELAY_CEILING_HOURS = 24.0
HISTORY_CAP_DEFAULT = 500
HISTORY_CAP_MAX = 1000

_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]?$")
_REGION_ID_RANGE = range(1, 18)
_REDISPATCH_MODES = ("off", "reference-demo")

_KEYS = {
    "compute_region", "enabled_workflows", "extra_protected_branches", "urgent_markers",
    "veto_events", "max_delay_hours", "cold_start_run_now", "history_cap",
    "grid_display_region", "show_live_intensity", "redispatch",
}


class ConfigError(ValueError):
    """An unusable team config. Always the `config_invalid` fail-safe."""

    code = "config_invalid"


@dataclass(frozen=True)
class TeamConfig:
    compute_region: str
    enabled_workflows: tuple[str, ...]
    extra_protected_branches: tuple[str, ...] = ()
    urgent_markers: tuple[str, ...] = ("[urgent]",)
    veto_events: tuple[str, ...] = ("workflow_dispatch", "schedule")
    max_delay_hours: float = MAX_DELAY_CEILING_HOURS
    cold_start_run_now: bool = True
    history_cap: int = HISTORY_CAP_DEFAULT
    grid_display_region: str | int | None = None
    show_live_intensity: bool = True
    redispatch: str = "off"
    warnings: tuple[str, ...] = field(default=())


def _str_list(raw: Mapping[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if key not in raw or raw[key] is None:
        return default
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"{key} must be a list of non-empty strings")
    return tuple(value)


def parse_team_config(raw: Any) -> TeamConfig:
    """Validate a config mapping. Raises :class:`ConfigError`."""
    if not isinstance(raw, Mapping):
        raise ConfigError("team config must be a YAML mapping")
    unknown = sorted(set(map(str, raw)) - _KEYS)
    if unknown:
        raise ConfigError(f"unknown config key(s) {unknown}; the config schema is closed")

    region = raw.get("compute_region")
    if not isinstance(region, str) or not region:
        raise ConfigError("compute_region is required (e.g. GB, US-EAST); it is declared, never detected")

    workflows = _str_list(raw, "enabled_workflows", ())
    if not workflows:
        raise ConfigError("enabled_workflows is required and must list at least one workflow file")

    veto_events = _str_list(raw, "veto_events", ("workflow_dispatch", "schedule"))
    bad_events = sorted(set(veto_events) - set(TRUSTED_EVENTS))
    if bad_events:
        raise ConfigError(f"veto_events {bad_events} are not trusted events {TRUSTED_EVENTS}")

    max_delay = raw.get("max_delay_hours", MAX_DELAY_CEILING_HOURS)
    if isinstance(max_delay, bool) or not isinstance(max_delay, (int, float)) or not math.isfinite(max_delay):
        raise ConfigError("max_delay_hours must be a number")
    if not 0 < float(max_delay) <= MAX_DELAY_CEILING_HOURS:
        raise ConfigError(f"max_delay_hours must be in (0, {MAX_DELAY_CEILING_HOURS:g}]; the evaluated "
                          f"window cannot be extended (DL-033 R3-B7)")

    cap = raw.get("history_cap", HISTORY_CAP_DEFAULT)
    if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= HISTORY_CAP_MAX:
        raise ConfigError(f"history_cap must be an integer in [1, {HISTORY_CAP_MAX}]")

    flags = {}
    for key, default in (("cold_start_run_now", True), ("show_live_intensity", True)):
        value = raw.get(key, default)
        if not isinstance(value, bool):
            raise ConfigError(f"{key} must be true or false")
        flags[key] = value

    redispatch = raw.get("redispatch", "off")
    if redispatch not in _REDISPATCH_MODES:
        raise ConfigError(f"redispatch must be one of {_REDISPATCH_MODES}")

    # grid_display_region is display-only (R3-J2): an invalid value is ignored with a
    # warning, never a fail-safe, because it can never affect a decision.
    warnings: list[str] = []
    display_region: str | int | None = None
    raw_region = raw.get("grid_display_region")
    if raw_region is not None:
        if isinstance(raw_region, int) and not isinstance(raw_region, bool) and raw_region in _REGION_ID_RANGE:
            display_region = raw_region
        elif isinstance(raw_region, str) and _POSTCODE_RE.match(raw_region.strip().upper()):
            display_region = raw_region.strip().upper()
        else:
            warnings.append(f"grid_display_region {raw_region!r} is not an outward postcode or a region "
                            f"id 1-17; regional intensity will not be shown")

    return TeamConfig(
        compute_region=region,
        enabled_workflows=workflows,
        extra_protected_branches=_str_list(raw, "extra_protected_branches", ()),
        urgent_markers=_str_list(raw, "urgent_markers", ("[urgent]",)),
        veto_events=veto_events,
        max_delay_hours=float(max_delay),
        cold_start_run_now=flags["cold_start_run_now"],
        history_cap=cap,
        grid_display_region=display_region,
        show_live_intensity=flags["show_live_intensity"],
        redispatch=redispatch,
        warnings=tuple(warnings),
    )


def load_team_config(path: str | Path) -> TeamConfig:
    """Read and validate a config file. Raises :class:`ConfigError`."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"team config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"team config is not valid YAML: {exc}") from exc
    return parse_team_config(raw)

"""Human-readable Markdown for a response — the CI Step Summary and the CLI.

It only formats fields the response already carries; it computes nothing.
Request-derived text (the branch, the reason) is shown inside code spans with
backticks neutralised, so a crafted branch name cannot inject Markdown or HTML.
"""

from __future__ import annotations

from typing import Any, Mapping

from scheduler_core.carbon import DOW_NAMES


def _code(text: Any) -> str:
    return "`" + str(text).replace("`", "'").replace("\n", " ") + "`"


def _fmt(value: Any, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{digits}f}{unit}"


def render_markdown(response: Mapping[str, Any], *, branch: str | None = None) -> str:
    lines: list[str] = []
    if response.get("scenario"):
        lines.append(f"> **{response['statements'][0]}**\n")
    icon = "🟢" if response.get("action") == "defer" else "🔴"
    lines.append(f"## {icon} {response.get('display')}")

    defer = response.get("defer_until")
    if defer:
        lines.append(f"Run at **{DOW_NAMES[defer['dow']]} {defer['hour']:02d}:00 UTC** "
                     f"({defer['utc']}), +{defer['offset_hours']} h.")
    lines.append("")
    rows = [
        ("Outcome", response.get("outcome_kind")),
        ("Branch", _code(branch) if branch else "—"),
        ("Eligibility rule", response.get("stage1_rule") or "—"),
        ("Expected duration (d̂)", f"{_fmt(response.get('d_hat_seconds'), ' s', 0)} "
                                   f"({response.get('d_hat_rung') or '—'}; "
                                   f"{response.get('n_history') if response.get('n_history') is not None else '—'} "
                                   f"completed runs)"),
        ("Window", _fmt(response.get("window_hours"), " h", 0)),
        ("GB profile now → at target", f"{_fmt(response.get('grid_gco2_profile_now'))} → "
                                       f"{_fmt(response.get('grid_gco2_profile_scheduled'))} gCO₂/kWh"),
        ("Estimated carbon change (this build)", _fmt(response.get("est_carbon_change_pct"), " %")),
    ]
    live = response.get("grid_gco2_live_national")
    if live:
        rows.append(("Live GB intensity (display only)", f"{_fmt(live['gco2_per_kwh'], ' gCO₂/kWh', 0)} ({live['kind']})"))
    regional = response.get("grid_gco2_live_regional")
    if regional:
        rows.append((f"Live regional — {regional.get('region')} (display only)",
                     f"{_fmt(regional['gco2_per_kwh'], ' gCO₂/kWh', 0)} ({regional['kind']})"))
    if response.get("vetoes"):
        rows.append(("Vetoes", ", ".join(response["vetoes"])))
    if response.get("fail_safe"):
        rows.append(("Fail-safe", response.get("fail_safe_code")))
    rows.append(("Assumed compute location", response.get("compute_region_assumed") or "—"))
    lines.append("| | |\n| :-- | :-- |")
    lines.extend(f"| {k} | {v} |" for k, v in rows)
    lines.append("")
    lines.append("**Why:** " + _code(response.get("reason", "")))
    lines.append("")
    for statement in response.get("statements", [])[1 if response.get("scenario") else 0:]:
        lines.append(f"- {statement}")
    for warning in response.get("config_warnings", []):
        lines.append(f"- ⚠ {warning}")
    lines.append("")
    lines.append(f"<sub>policy {response.get('policy_path') or '—'} · spec {str(response.get('spec_sha256') or '—')[:12]} · "
                 f"advisor {response.get('advisor_version')}</sub>")
    return "\n".join(lines) + "\n"

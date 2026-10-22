"""Human-readable Markdown for a response — the CI Step Summary and the CLI.

Layout (DL-038 §7, readability):

1. the SCENARIO banner, when it applies;
2. a headline: the recommendation and, for a deferral, when;
3. one plain-English sentence saying why;
4. a short table of the facts a viewer needs;
5. collapsed sections: the full technical record (every field shown before), and the
   assumptions and limits (DL-033 R3-C11).

It only formats fields the response already carries; it computes no decision and
holds no threshold. Request-derived text (the branch, the reason) is shown inside
code spans with backticks neutralised, so a crafted branch name cannot inject
Markdown or HTML.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from scheduler_core.carbon import DOW_NAMES

from .core import _VETO_TEXT


def _code(text: Any) -> str:
    return "`" + str(text).replace("`", "'").replace("\n", " ") + "`"


def _cell_code(text: Any) -> str:
    """A code span inside a table cell: a ``|`` would otherwise split the cell."""
    return _code(text).replace("|", "\\|")


def _fmt(value: Any, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{digits}f}{unit}"


def _duration(seconds: Any) -> str:
    """549 → "about 9 min"; 40 → "about 40 s"."""
    if seconds is None:
        return "—"
    s = float(seconds)
    if s < 90:
        return f"about {s:.0f} s"
    if s < 5400:
        return f"about {s / 60:.0f} min"
    return f"about {s / 3600:.1f} h"


def _when(defer: Mapping[str, Any]) -> str:
    """The deferral target as "Thu 22 Oct, 02:00 UTC"."""
    try:
        return datetime.fromisoformat(str(defer["utc"])).strftime("%a %d %b, %H:%M UTC")
    except (KeyError, ValueError):
        return f"{DOW_NAMES[defer['dow']]} {defer['hour']:02d}:00 UTC"


def _history(response: Mapping[str, Any]) -> str:
    n = response.get("n_history")
    if n is None:
        return ""
    return f" (from {n} earlier completed run{'s' if n != 1 else ''})" if n else " (no earlier runs yet)"


def _why(response: Mapping[str, Any], branch: str | None) -> str:
    """One sentence a viewer can read, derived only from the response's codes."""
    action, kind = response.get("action"), response.get("outcome_kind")
    rule = str(response.get("stage1_rule") or "")
    if action == "defer":
        return (f"Nobody is waiting on this build (a push to a non-protected branch), it is expected to take "
                f"{_duration(response.get('d_hat_seconds'))}, and a cleaner hour on the GB grid comes within "
                f"the next {_fmt(response.get('window_hours'), ' h', 0)}.")
    if kind == "fail_safe":
        code = response.get("fail_safe_code")
        if code == "region_not_gb":
            return (f"This runner is declared as {_code(response.get('compute_region_assumed'))}, not Great "
                    f"Britain. The advice was only evaluated on the GB grid, so it does not apply here.")
        if code == "untrusted_event":
            return "This kind of trigger is not trusted, so the advisor did not look any further."
        if code == "invalid_request":
            return ("The advisor's input was incomplete or invalid (for example, no `compute-region` was "
                    "declared), so it answers RUN NOW.")
        if code in ("config_invalid", "region_mismatch"):
            return "The team settings for the advisor are invalid or disagree, so it answers RUN NOW."
        if code == "redispatch_unavailable":
            return ("The policy would defer this build, but the deferral could not be recorded for a later "
                    "re-run, so it runs now rather than risk being dropped.")
        return (f"Safety fallback ({_code(code)}): something the advisor needs was missing or failed, so it "
                f"answers RUN NOW.")
    if kind == "not_advised":
        return "This workflow is not opted in to the advisor."
    if kind == "veto":
        rules = "; ".join(_VETO_TEXT.get(v, str(v)) for v in response.get("vetoes") or [])
        return f"The policy would defer this build, but a team rule says run now: {rules}."
    if rule == "pr_blocking":
        return "This is a pull request: someone is waiting for the result, so it always runs now."
    if rule.startswith("protected:"):
        where = _code(branch) if branch else "this branch"
        return f"{where} is a protected branch (main or release), so it always runs now."
    if rule.startswith("fail_closed:"):
        return "The branch or pull-request status could not be read, so to be safe it runs now."
    if response.get("eligible"):
        if not response.get("window_hours"):
            return (f"It is expected to take {_duration(response.get('d_hat_seconds'))}, too short for a delay "
                    f"to save much.")
        return (f"This hour is already the cleanest within the next "
                f"{_fmt(response.get('window_hours'), ' h', 0)}, so waiting would not help.")
    return "The advisor recommends running now."


def _key_facts(response: Mapping[str, Any], branch: str | None) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    defer = response.get("defer_until")
    if branch:
        rows.append(("Branch", _cell_code(branch)))
    if response.get("d_hat_seconds") is not None:
        rows.append(("Expected build time", _duration(response["d_hat_seconds"]) + _history(response)))
    if defer:
        rows.append(("Grid now → then", f"{_fmt(response.get('grid_gco2_profile_now'), digits=0)} → "
                                         f"{_fmt(response.get('grid_gco2_profile_scheduled'), digits=0)} gCO₂/kWh "
                                         f"(typical GB week)"))
        change = response.get("est_carbon_change_pct")
        saved = f"**{_fmt(-float(change), ' %')}** for this build (estimate)" if change is not None else "—"
        rows.append(("Estimated carbon saved", saved))
    live = response.get("grid_gco2_live_national")
    if live:
        rows.append(("GB grid right now", f"{_fmt(live['gco2_per_kwh'], ' gCO₂/kWh', 0)} (live, for display only)"))
    redispatch = response.get("redispatch")
    if isinstance(redispatch, Mapping) and redispatch.get("issue_number"):
        rows.append(("Re-run", f"recorded as issue #{int(redispatch['issue_number'])}"
                               f"{' (reused)' if redispatch.get('reused') else ''} — it re-runs at the start "
                               f"time; close the issue to cancel"))
    elif response.get("action") == "defer":
        rows.append(("Re-run", "advice only — nothing delays or re-runs this build automatically"))
    return rows


def _technical(response: Mapping[str, Any], branch: str | None) -> list[str]:
    rows = [
        ("Outcome", response.get("outcome_kind")),
        ("Policy said", response.get("policy_action") or "—"),
        ("Eligibility rule", response.get("stage1_rule") or "—"),
        ("Expected duration (d̂)", f"{_fmt(response.get('d_hat_seconds'), ' s', 0)} "
                                   f"({response.get('d_hat_rung') or '—'} rung; "
                                   f"{response.get('n_history') if response.get('n_history') is not None else '—'} "
                                   f"completed runs)"),
        ("Window", _fmt(response.get("window_hours"), " h", 0)),
        ("GB profile now → at target", f"{_fmt(response.get('grid_gco2_profile_now'))} → "
                                       f"{_fmt(response.get('grid_gco2_profile_scheduled'))} gCO₂/kWh"),
        ("Estimated carbon change (this build)", _fmt(response.get("est_carbon_change_pct"), " %")),
    ]
    defer = response.get("defer_until")
    if defer:
        rows.insert(0, ("Start (UTC)", f"{defer.get('utc')} (+{defer.get('offset_hours')} h)"))
    regional = response.get("grid_gco2_live_regional")
    if regional:
        rows.append((f"Live regional — {regional.get('region')} (display only)",
                     f"{_fmt(regional['gco2_per_kwh'], ' gCO₂/kWh', 0)} ({regional['kind']})"))
    if response.get("vetoes"):
        rows.append(("Vetoes", ", ".join(response["vetoes"])))
    if response.get("fail_safe"):
        rows.append(("Fail-safe", response.get("fail_safe_code")))
    rows.append(("Assumed compute location", response.get("compute_region_assumed") or "—"))
    rows.append(("Provenance", f"policy {response.get('policy_path') or '—'} · spec "
                               f"{str(response.get('spec_sha256') or '—')[:12]} · estimator "
                               f"{response.get('estimator_fit_id') or '—'} · advisor {response.get('advisor_version')}"))
    lines = ["<details><summary>Technical details</summary>", "", "| | |", "| :-- | :-- |"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    lines += ["", "**Full reason:** " + _code(response.get("reason", "")), "", "</details>"]
    return lines


def render_markdown(response: Mapping[str, Any], *, branch: str | None = None) -> str:
    statements = list(response.get("statements", []))
    lines: list[str] = []
    if response.get("scenario") and statements:
        lines += [f"> **{statements[0]}**", ""]
        statements = statements[1:]

    defer = response.get("defer_until")
    if response.get("action") == "defer" and defer:
        lines.append(f"## 🟢 {response.get('display')} — {_when(defer)} (in {defer['offset_hours']} h)")
    else:
        lines.append(f"## 🔴 {response.get('display')}")
    lines += ["", _why(response, branch), ""]

    facts = _key_facts(response, branch)
    if facts:
        lines += ["| | |", "| :-- | :-- |"] + [f"| {k} | {v} |" for k, v in facts] + [""]
    for warning in response.get("config_warnings", []):
        lines += [f"> ⚠ {warning}", ""]

    lines += _technical(response, branch) + [""]
    lines += ["<details><summary>Assumptions and limits</summary>", ""]
    lines += [f"- {s}" for s in statements]
    lines += ["- " + "The study tested commit-level software-engineering characteristics and did not admit them: "
                     "this advice uses branch/PR status and a duration estimate only.", "", "</details>"]
    return "\n".join(lines) + "\n"

"""The What-If report as one self-contained static HTML page (DL-033 R3-I; DL-037 §7).

Generated from the report JSON alone: it adds no logic and no number. Every
number in the page text is a JSON value printed with ``json.dumps``, so it is
character-for-character the value in ``report.json`` (a test checks this).
Charts are inline SVG; hover text uses SVG ``<title>``. No JavaScript, no
network, no timestamp: the same JSON gives byte-identical HTML.
"""

from __future__ import annotations

import html
import json
from typing import Any, Mapping

# Sequential blue ramp, steps 100 → 700 (dataviz reference palette).
_SEQ = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")

_CSS = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --series-1:#2a78d6; --series-2:#eb6834; --ring:#fcfcfb;
  --border:rgba(11,11,11,0.10); --banner:#fff4d6; --banner-ink:#5a4300; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --series-1:#3987e5; --series-2:#d95926; --ring:#1a1a19;
  --border:rgba(255,255,255,0.10); --banner:#3a2f10; --banner-ink:#f3dfa6; } }
:root[data-theme="dark"] { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --series-1:#3987e5; --series-2:#d95926; --ring:#1a1a19;
  --border:rgba(255,255,255,0.10); --banner:#3a2f10; --banner-ink:#f3dfa6; }
* { box-sizing: border-box; }
body { margin:0; background:var(--page); color:var(--ink);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:960px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:17px; margin:32px 0 8px; }
.sub { color:var(--ink-2); margin:0 0 16px; }
.banner { background:var(--banner); color:var(--banner-ink); border-radius:8px; padding:10px 14px; margin:0 0 16px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
.tile { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
.tile .label { color:var(--ink-2); font-size:13px; } .tile .value { font-size:24px; font-weight:600; }
.tile .note { color:var(--muted); font-size:12px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:12px 14px; overflow-x:auto; }
svg { display:block; max-width:100%; height:auto; }
svg text { fill:var(--ink-2); font:12px system-ui,-apple-system,"Segoe UI",sans-serif; }
svg .val { fill:var(--ink); font-weight:600; }
.bar { fill:var(--series-1); } .grid { stroke:var(--grid); stroke-width:1; } .axis { stroke:var(--axis); stroke-width:1; }
.whisker { stroke:var(--ink-2); stroke-width:2; stroke-linecap:round; }
.arr { fill:none; stroke:var(--ink); stroke-width:2; } .tgt { fill:var(--series-2); stroke:var(--ring); stroke-width:2; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th, td { text-align:left; padding:4px 8px; border-bottom:1px solid var(--grid); vertical-align:top; }
td.n { text-align:right; }
ul { padding-left:20px; } li { margin:2px 0; } .muted { color:var(--muted); font-size:13px; word-break:break-all; }
.legend { display:flex; flex-wrap:wrap; gap:16px; color:var(--ink-2); font-size:13px; margin-top:8px; align-items:center; }
.swatch { display:inline-block; width:14px; height:14px; border-radius:3px; vertical-align:middle; margin-right:4px; }
"""


def num(value: Any) -> str:
    """A JSON value exactly as report.json prints it."""
    return "—" if value is None else json.dumps(value)


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _bar_path(x: float, y: float, w: float, h: float, r: float = 4.0) -> str:
    """Horizontal bar from the left baseline; 4px rounded data-end on the right."""
    r = min(r, w / 2, h / 2)
    return (f"M{x:.1f},{y:.1f}h{w - r:.1f}a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f}v{h - 2 * r:.1f}"
            f"a{r:.1f},{r:.1f} 0 0 1 -{r:.1f},{r:.1f}h-{w - r:.1f}z")


def _col_path(x: float, base: float, w: float, h: float, r: float = 4.0) -> str:
    """Vertical column from the bottom baseline; 4px rounded cap."""
    r = min(r, w / 2, h / 2)
    return (f"M{x:.1f},{base:.1f}v-{h - r:.1f}a{r:.1f},{r:.1f} 0 0 1 {r:.1f},-{r:.1f}h{w - 2 * r:.1f}"
            f"a{r:.1f},{r:.1f} 0 0 1 {r:.1f},{r:.1f}v{h - r:.1f}z")


def _hbars(items: list[tuple[str, Any]], title: str) -> str:
    """Horizontal bars, one series: label left, value at the tip."""
    if not items:
        return '<p class="muted">none</p>'
    peak = max(float(v) for _, v in items) or 1.0
    label_w, plot_w, row = 190, 560, 30
    height = row * len(items) + 8
    out = [f'<svg viewBox="0 0 {label_w + plot_w + 60} {height}" role="img" aria-label="{esc(title)}">']
    out.append(f'<line class="axis" x1="{label_w}" y1="0" x2="{label_w}" y2="{height}"/>')
    for i, (label, value) in enumerate(items):
        y = 4 + i * row
        w = max(plot_w * float(value) / peak, 0.0)
        out.append(f'<g><title>{esc(label)}: {num(value)}</title>')
        out.append(f'<text x="{label_w - 8}" y="{y + 16}" text-anchor="end">{esc(label)}</text>')
        if w > 0:
            out.append(f'<path class="bar" d="{_bar_path(label_w, y + 3, w, 18)}"/>')
        out.append(f'<text class="val" x="{label_w + w + 6:.1f}" y="{y + 16}">{num(value)}</text></g>')
    out.append("</svg>")
    return "".join(out)


def _carbon_chart(carbon: Mapping[str, Any]) -> str:
    """Mean estimated grams per run, run-now vs advisor, nominal power with the band as whiskers."""
    band = carbon["band"]
    if not band or band[1]["run_now_g_per_run"] is None:
        return '<p class="muted">no analysed runs</p>'
    low, mid, high = band[0], band[1], band[-1]
    rows = [("Run now", "run_now_g_per_run"), ("Advisor", "advisor_g_per_run")]
    peak = max(float(high[k]) for _, k in rows) or 1.0
    label_w, plot_w, row = 100, 600, 44
    out = [f'<svg viewBox="0 0 {label_w + plot_w + 120} {row * 2 + 10}" role="img" '
           f'aria-label="Estimated grams of CO2e per run">']
    out.append(f'<line class="axis" x1="{label_w}" y1="0" x2="{label_w}" y2="{row * 2 + 10}"/>')
    for i, (label, key) in enumerate(rows):
        y = 6 + i * row
        w = plot_w * float(mid[key]) / peak
        x_lo, x_hi = label_w + plot_w * float(low[key]) / peak, label_w + plot_w * float(high[key]) / peak
        out.append(f'<g><title>{label}: {num(mid[key])} g at {num(mid["p_avg_w"])} W '
                   f'({num(low[key])} to {num(high[key])} g across the band)</title>')
        out.append(f'<text x="{label_w - 8}" y="{y + 20}" text-anchor="end">{label}</text>')
        out.append(f'<path class="bar" d="{_bar_path(label_w, y + 6, w, 22)}"/>')
        out.append(f'<line class="whisker" x1="{x_lo:.1f}" y1="{y + 17}" x2="{x_hi:.1f}" y2="{y + 17}"/>')
        out.append(f'<line class="whisker" x1="{x_lo:.1f}" y1="{y + 11}" x2="{x_lo:.1f}" y2="{y + 23}"/>')
        out.append(f'<line class="whisker" x1="{x_hi:.1f}" y1="{y + 11}" x2="{x_hi:.1f}" y2="{y + 23}"/>')
        out.append(f'<text class="val" x="{x_hi + 8:.1f}" y="{y + 21}">{num(mid[key])} g</text></g>')
    out.append("</svg>")
    return "".join(out)


def _histogram(delay: Mapping[str, Any]) -> str:
    bins = delay["histogram"]
    peak = max((b["count"] for b in bins), default=0)
    if peak == 0:
        return '<p class="muted">no deferred runs</p>'
    left, plot_h, col, gap = 30, 160, 52, 8
    width = left + len(bins) * (col + gap)
    out = [f'<svg viewBox="0 0 {width} {plot_h + 62}" role="img" aria-label="Added delay of deferred runs">']
    base = plot_h + 28  # headroom for the tallest column's value label
    out.append(f'<line class="axis" x1="{left}" y1="{base}" x2="{width}" y2="{base}"/>')
    for i, b in enumerate(bins):
        x = left + i * (col + gap) + gap / 2
        h = plot_h * b["count"] / peak
        out.append(f'<g><title>{num(b["from_h"])}–{num(b["to_h"])} h: {num(b["count"])} runs</title>')
        if h > 0:
            out.append(f'<path class="bar" d="{_col_path(x + 14, base, col - 28, h)}"/>')
            out.append(f'<text class="val" x="{x + col / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle">'
                       f'{num(b["count"])}</text>')
        out.append(f'<text x="{x + col / 2:.1f}" y="{base + 18}" text-anchor="middle">'
                   f'{num(b["from_h"])}–{num(b["to_h"])}</text></g>')
    out.append("</svg>")
    return "".join(out)


def _heatmap(heat: Mapping[str, Any]) -> str:
    values = [v for row in heat["intensity"] for v in row]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    arrivals = {(a["dow"], a["hour"]): a["count"] for a in heat["deferred_arrivals"]}
    targets = {(t["dow"], t["hour"]): t["count"] for t in heat["deferred_targets"]}
    left, top, cell = 44, 22, 30
    out = [f'<svg viewBox="0 0 {left + 24 * cell + 4} {top + 7 * cell + 4}" role="img" '
           f'aria-label="GB hour-of-week carbon intensity with deferred runs marked">']
    for h in heat["hours"]:
        if h % 3 == 0:
            out.append(f'<text x="{left + h * cell + cell / 2}" y="{top - 8}" text-anchor="middle">{num(h)}</text>')
    for d, name in enumerate(heat["dows"]):
        out.append(f'<text x="{left - 8}" y="{top + d * cell + 19}" text-anchor="end">{esc(name)}</text>')
        for h in heat["hours"]:
            v = heat["intensity"][d][h]
            step = min(int((v - lo) / span * len(_SEQ)), len(_SEQ) - 1)
            x, y = left + h * cell, top + d * cell
            tip = f"{esc(name)}, hour {num(h)} UTC — {num(v)} gCO₂/kWh"
            if (d, h) in arrivals:
                tip += f"; deferred from here: {num(arrivals[(d, h)])}"
            if (d, h) in targets:
                tip += f"; deferred to here: {num(targets[(d, h)])}"
            out.append(f'<g><title>{tip}</title><rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" '
                       f'height="{cell - 2}" rx="3" fill="{_SEQ[step]}"/>')
            if (d, h) in arrivals:
                out.append(f'<rect class="arr" x="{x + 4}" y="{y + 4}" width="{cell - 8}" height="{cell - 8}" rx="3"/>')
            if (d, h) in targets:
                out.append(f'<circle class="tgt" cx="{x + cell / 2}" cy="{y + cell / 2}" r="6"/>')
            out.append("</g>")
    out.append("</svg>")
    ramp = "".join(f'<span class="swatch" style="background:{c};margin-right:0;border-radius:0"></span>' for c in _SEQ)
    out.append(f'<div class="legend"><span>{num(lo)} {ramp} {num(hi)} gCO₂/kWh (GB profile)</span>'
               f'<span><svg width="16" height="16" style="display:inline;vertical-align:middle"><rect class="arr" '
               f'x="2" y="2" width="12" height="12" rx="3"/></svg> deferred run arrived</span>'
               f'<span><svg width="16" height="16" style="display:inline;vertical-align:middle"><circle class="tgt" '
               f'cx="8" cy="8" r="6"/></svg> recommended start</span></div>')
    return "".join(out)


def _table(rows: list[tuple[Any, Any]], head: tuple[str, str]) -> str:
    if not rows:
        return '<p class="muted">none</p>'
    body = "".join(f"<tr><td>{esc(k)}</td><td class=\"n\">{num(v)}</td></tr>" for k, v in rows)
    return f"<table><thead><tr><th>{esc(head[0])}</th><th>{esc(head[1])}</th></tr></thead><tbody>{body}</tbody></table>"


def render_html(report: Mapping[str, Any]) -> str:
    d, c, dl, t = report["decisions"], report["carbon"], report["delay"], report["ttff_failed"]
    s, p, rc = report["snapshot"], report["policy"], report["rung_coverage"]
    band_rows = "".join(
        f"<tr><td class=\"n\">{num(b['multiplier'])}</td><td class=\"n\">{num(b['p_avg_w'])}</td>"
        f"<td class=\"n\">{num(b['run_now_g'])}</td><td class=\"n\">{num(b['advisor_g'])}</td>"
        f"<td class=\"n\">{num(b['change_g'])}</td></tr>" for b in c["band"])
    ttff = (f"{num(t['p95_hours_advisor'])} h" if t["computed"] else esc(t["note"]))
    ttff_note = (f"run-now {num(t['p95_hours_run_now'])} h · n = {num(t['failed_runs'])}" if t["computed"]
                 else f"needs ≥ {num(t['min_failed_runs'])} failed runs")
    reasons = list(d["run_now_reasons"].items())
    parts = [
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>What-If: {esc(report['repository'])}</title><style>{_CSS}</style></head><body><main>",
        f"<p class=\"banner\"><strong>{esc(report['banner'])}.</strong> {esc(report['statements'][0])}</p>",
        f"<h1>Repo What-If Report — {esc(report['repository'])}</h1>",
        f"<p class=\"sub\">Workflow <code>{esc(report['workflow'])}</code> · "
        f"{num(report['runs']['analysed'])} of {num(report['runs']['fetched'])} completed runs analysed · "
        f"history {esc(s['window_first_created_at'])} → {esc(s['window_last_created_at'])}"
        + (" (window truncated: older runs exist)" if s["window_truncated"] else "") + "</p>",
        "<div class=\"tiles\">",
        f"<div class=\"tile\"><div class=\"label\">Deferred</div><div class=\"value\">{num(d['deferred_share_pct'])} %</div>"
        f"<div class=\"note\">{num(d['deferred'])} runs · eligible {num(d['eligible_share_pct'])} %</div></div>",
        f"<div class=\"tile\"><div class=\"label\">Estimated carbon vs run now</div><div class=\"value\">"
        f"{num(c['change_pct'])} %</div><div class=\"note\">{esc(c['label'])}</div></div>",
        f"<div class=\"tile\"><div class=\"label\">Mean added delay, all runs</div><div class=\"value\">"
        f"{num(dl['mean_added_delay_hours_all_runs'])} h</div><div class=\"note\">deferred runs only: "
        f"{num(dl['mean_delay_hours_deferred'])} h</div></div>",
        f"<div class=\"tile\"><div class=\"label\">Failed-run TTFF p95</div><div class=\"value\">{ttff}</div>"
        f"<div class=\"note\">{ttff_note}</div></div>",
        "</div>",
        "<h2>Why runs were not deferred</h2><div class=\"card\">",
        _hbars(reasons, "Run-now reasons"),
        "</div>",
        "<h2>Estimated carbon per run</h2><div class=\"card\">",
        _carbon_chart(c),
        f"<p class=\"muted\">Bars at {num(c['band'][1]['p_avg_w'])} W; whiskers span the power band "
        f"({num(c['band'][0]['p_avg_w'])} to {num(c['band'][-1]['p_avg_w'])} W).</p>",
        "<table><thead><tr><th>multiplier</th><th>P_avg (W)</th><th>run now (g)</th><th>advisor (g)</th>"
        f"<th>change (g)</th></tr></thead><tbody>{band_rows}</tbody></table></div>",
        "<h2>When deferred runs arrived, and when they were sent</h2><div class=\"card\">",
        _heatmap(report["heatmap"]),
        "</div>",
        f"<h2>Added delay of deferred runs</h2><div class=\"card\">{_histogram(dl)}"
        f"<p class=\"muted\">Hours, in bins of {num(dl['histogram_bin_hours'])}.</p></div>",
        "<h2>Details</h2><div class=\"card\">",
        _table(reasons, ("run-now reason", "runs")),
        "<h3>Vetoes</h3>", _table(list(d["veto_codes"].items()), ("veto", "runs")),
        "<h3>Fail-safes</h3>", _table(list(d["fail_safe_codes"].items()), ("fail-safe", "runs")),
        "<h3>Excluded runs</h3>", _table(list(report["runs"]["excluded"].items()), ("reason", "runs")),
        "<h3>Duration-estimate rung</h3>",
        _table([("project", rc["project"]), ("language", rc["language"]), ("global", rc["global"]),
                ("cold start", rc["cold_start_runs"])], ("rung", "runs")),
        "</div>",
        "<h2>Statements</h2><ul>", *[f"<li>{esc(x)}</li>" for x in report["statements"][1:]], "</ul>",
        "<h2>Limitations</h2><ul>", *[f"<li>{esc(x)}</li>" for x in report["limitations"]], "</ul>",
        "<h2>Provenance</h2><ul class=\"muted\">",
        f"<li>policy {esc(p['policy_path'])} · parameters {esc(json.dumps(p['parameters'], sort_keys=True))}</li>",
        f"<li>spec {esc(p['spec_sha256'])}</li><li>profile {esc(p['profile_sha256'])}</li>",
        f"<li>estimator {esc(p['estimator_fit_id'])} · advisor {esc(p['advisor_version'])}</li>",
        f"<li>snapshot {esc(s['sha256'])} · fetched {esc(s['fetched_at'])}</li>",
        "</ul></main></body></html>\n",
    ]
    return "".join(parts)

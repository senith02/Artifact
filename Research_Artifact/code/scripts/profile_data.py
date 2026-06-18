"""P0-T2 S3+S4 — data-quality funnel and dataset profile.

One real chunked pass over the backbone CSV produces:
  * a cleaning **filter funnel** (rows-in -> rows-out per step, with the grain),
  * `results/p0/data_profile.json` and a human-readable `data_profile.md`.

Grain and aggregation follow DL-009 (build grain, one row per tr_build_id);
nothing here invents numbers — every figure is computed from this run (R1).
The run date/command are recorded in the output for provenance.

Run:  python scripts/profile_data.py            (env: PYTHONPATH=.)
or:   python tasks.py profile-data
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from scheduler_core import data

RESULTS = Path(__file__).resolve().parents[1].parent / "results" / "p0"
RUN_DATE = "2026-06-18"  # provenance; this session's run date (project context)
CHUNK = 300_000

FIRST_COLS = ["gh_project_name", "gh_lang", "tr_status", "gh_build_started_at"]


def _combine(running: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """Reduce a new chunk's build aggregates into the running build table."""
    if running is None:
        return new
    cat = pd.concat([running, new])  # running first -> 'first' keeps earliest
    g = cat.groupby(level=0, sort=False)
    cols = [c for c in FIRST_COLS if c in cat.columns]
    out = g[cols].first()
    out["tr_duration"] = g["tr_duration"].max()
    out["n_jobs"] = g["n_jobs"].sum()
    return out


def main() -> int:
    total_rows = 0
    null_counts = pd.Series(0, index=list(data.EXPECTED_HEADER), dtype="int64")
    seen_hashes: set[int] = set()
    dup_rows = 0
    builds: pd.DataFrame | None = None

    n_chunks = 0
    for chunk in data.read_chunks(chunksize=CHUNK):
        n_chunks += 1
        total_rows += len(chunk)

        # (a) null counts across all 66 columns (job-row grain).
        null_counts = null_counts.add(chunk.isna().sum(), fill_value=0)

        # (b) drop exact-duplicate job rows (global, across chunks).
        h = pd.util.hash_pandas_object(chunk, index=False).to_numpy()
        within = chunk.duplicated(keep="first").to_numpy()
        keep_mask = np.empty(len(chunk), dtype=bool)
        for i in range(len(chunk)):
            if within[i] or (h[i] in seen_hashes):
                keep_mask[i] = False
                dup_rows += 1
            else:
                keep_mask[i] = True
                seen_hashes.add(int(h[i]))
        kept = chunk.loc[keep_mask]

        # (c) aggregate kept rows to build grain and reduce.
        builds = _combine(builds, data.aggregate_to_builds(kept).set_index("tr_build_id"))
        print(f"  chunk {n_chunks}: {total_rows:,} rows, {len(builds):,} builds, "
              f"{dup_rows:,} dup rows so far")

    rows_after_dedup = total_rows - dup_rows
    n_builds = len(builds)

    # ---- build-level filter funnel ----------------------------------------
    status_class = builds["tr_status"].map(data.classify_status)
    missing_label = status_class.isin(["missing", "other"])
    b_after_label = builds.loc[~missing_label]
    canceled = b_after_label["tr_status"].map(data.classify_status) == "canceled"
    b_after_cancel = b_after_label.loc[~canceled]
    ts = pd.to_datetime(b_after_cancel["gh_build_started_at"], errors="coerce", utc=True)
    bad_ts = ts.isna()
    analytic = b_after_cancel.loc[~bad_ts]

    funnel = [
        {"step": "raw job rows", "grain": "job", "rows_in": total_rows, "rows_out": total_rows, "dropped": 0},
        {"step": "drop exact-duplicate job rows", "grain": "job", "rows_in": total_rows, "rows_out": rows_after_dedup, "dropped": dup_rows},
        {"step": "aggregate to builds (tr_build_id)", "grain": "job->build", "rows_in": rows_after_dedup, "rows_out": n_builds, "dropped": rows_after_dedup - n_builds},
        {"step": "drop builds with missing/other label", "grain": "build", "rows_in": n_builds, "rows_out": len(b_after_label), "dropped": int(missing_label.sum())},
        {"step": "exclude canceled builds", "grain": "build", "rows_in": len(b_after_label), "rows_out": len(b_after_cancel), "dropped": int(canceled.sum())},
        {"step": "drop missing/unparseable gh_build_started_at", "grain": "build", "rows_in": len(b_after_cancel), "rows_out": len(analytic), "dropped": int(bad_ts.sum())},
    ]

    # ---- class balance (analytic set) -------------------------------------
    a_class = analytic["tr_status"].map(data.classify_status)
    n_fail = int((a_class == "failure").sum())
    n_pass = int((a_class == "pass").sum())
    class_balance = {
        "analytic_builds": len(analytic),
        "failure": n_fail,
        "pass": n_pass,
        "failure_rate_pct": round(100 * n_fail / (n_fail + n_pass), 4) if (n_fail + n_pass) else None,
    }
    raw_status_counts = builds["tr_status"].map(data.classify_status).value_counts().to_dict()

    # ---- per-language (build grain, analytic set) -------------------------
    lang_counts = analytic["gh_lang"].fillna("NA").value_counts().to_dict()

    # ---- duration distribution (build grain, analytic set, seconds) -------
    dur = pd.to_numeric(analytic["tr_duration"], errors="coerce")
    dur_valid = dur.dropna()
    qs = [1, 25, 50, 75, 90, 95, 99]
    duration = {
        "count": int(dur_valid.shape[0]),
        "zeros": int((dur_valid == 0).sum()),
        "nonpositive": int((dur_valid <= 0).sum()),
        "min": float(dur_valid.min()),
        "mean": round(float(dur_valid.mean()), 2),
        "max": float(dur_valid.max()),
        "percentiles_s": {f"p{q}": round(float(np.percentile(dur_valid, q)), 2) for q in qs},
        "over_1h": int((dur_valid > 3600).sum()),
        "over_6h": int((dur_valid > 21600).sum()),
    }

    # ---- top-20 projects by build count (analytic set) --------------------
    grp = analytic.assign(_cls=a_class).groupby("gh_project_name")
    proj = pd.DataFrame({
        "builds": grp.size(),
        "failures": grp["_cls"].apply(lambda s: int((s == "failure").sum())),
    }).sort_values("builds", ascending=False).head(20)
    top20 = [
        {"project": idx, "builds": int(r.builds), "failures": int(r.failures),
         "failure_rate_pct": round(100 * r.failures / r.builds, 2) if r.builds else None}
        for idx, r in proj.iterrows()
    ]

    null_rate = {c: round(100 * int(null_counts[c]) / total_rows, 4) for c in data.EXPECTED_HEADER}

    # ---- notable, machine-derived data-quality findings -------------------
    findings = {
        "fully_null_columns": [c for c, v in null_rate.items() if v >= 100.0],
        "high_null_columns_ge_50pct": {c: v for c, v in null_rate.items() if 50.0 <= v < 100.0},
        "n_languages": len(lang_counts),
        "languages": list(lang_counts.keys()),
        "zero_or_nonpositive_duration_builds": duration["nonpositive"],
        "builds_missing_duration": len(analytic) - duration["count"],
    }

    profile = {
        "provenance": {
            "command": "python scripts/profile_data.py",
            "run_date": RUN_DATE,
            "dataset_path": str(data.DEFAULT_DATASET_PATH),
            "chunksize": CHUNK,
        },
        "row_counts": {
            "total_job_rows": total_rows,
            "exact_duplicate_job_rows": dup_rows,
            "total_builds": n_builds,
            "analytic_builds": len(analytic),
        },
        "filter_funnel": funnel,
        "class_balance": class_balance,
        "build_status_distribution_all": raw_status_counts,
        "per_language_builds": lang_counts,
        "duration_distribution_s": duration,
        "top_20_projects_by_build_count": top20,
        "per_column_null_rate_pct": null_rate,
        "notable_findings": findings,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "data_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    _write_md(profile)
    print(f"\nwrote {RESULTS / 'data_profile.json'} and data_profile.md")
    return 0


def _write_md(p: dict) -> None:
    rc, cb, dur = p["row_counts"], p["class_balance"], p["duration_distribution_s"]
    lines: list[str] = []
    lines.append("# Data Profile — TravisTorrent backbone (P0-T2)\n")
    lines.append(f"> Generated by `{p['provenance']['command']}` on {p['provenance']['run_date']} "
                 f"(R1: every number below comes from this real run).\n")
    lines.append(f"> Source: `{p['provenance']['dataset_path']}` · grain: **build** (DL-009).\n")

    lines.append("\n## Headline counts\n")
    lines.append(f"- Total job rows: **{rc['total_job_rows']:,}**")
    lines.append(f"- Exact-duplicate job rows dropped: **{rc['exact_duplicate_job_rows']:,}**")
    lines.append(f"- Builds (after aggregation): **{rc['total_builds']:,}**")
    lines.append(f"- Analytic builds (after cleaning): **{rc['analytic_builds']:,}**\n")

    f = p["notable_findings"]
    lines.append("\n## ⚠ Notable data-quality findings (read these)\n")
    lines.append(f"- **Languages present: {f['n_languages']}** — {', '.join(f['languages'])}. "
                 "(dataset_reference.md originally said only Ruby/Java — corrected.)")
    lines.append(f"- **Fully-null (100%) columns — unusable:** "
                 f"{', '.join(f['fully_null_columns']) if f['fully_null_columns'] else 'none'}.")
    lines.append("- **High-null columns (≥50%, <100%):** "
                 + (", ".join(f"{c} ({v}%)" for c, v in f["high_null_columns_ge_50pct"].items())
                    if f["high_null_columns_ge_50pct"] else "none") + ".")
    lines.append(f"- Zero/nonpositive-duration builds in analytic set: **{f['zero_or_nonpositive_duration_builds']:,}** "
                 f"(matters for the energy model, DL-010); builds with no duration: **{f['builds_missing_duration']:,}**.\n")

    lines.append("\n## Cleaning filter funnel\n")
    lines.append("| Step | Grain | Rows in | Rows out | Dropped |")
    lines.append("| :-- | :-- | --: | --: | --: |")
    for s in p["filter_funnel"]:
        lines.append(f"| {s['step']} | {s['grain']} | {s['rows_in']:,} | {s['rows_out']:,} | {s['dropped']:,} |")

    lines.append("\n## Class balance (analytic set)\n")
    lines.append(f"- Failures (failed+errored): **{cb['failure']:,}**")
    lines.append(f"- Passes: **{cb['pass']:,}**")
    lines.append(f"- **Failure rate: {cb['failure_rate_pct']}%**\n")
    lines.append("Build status distribution over ALL builds (pre-cleaning), by class:\n")
    lines.append("| Class | Builds |")
    lines.append("| :-- | --: |")
    for k, v in sorted(p["build_status_distribution_all"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v:,} |")

    lines.append("\n## Builds per language (analytic set)\n")
    lines.append("| Language | Builds |")
    lines.append("| :-- | --: |")
    for k, v in sorted(p["per_language_builds"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v:,} |")

    lines.append("\n## Build duration distribution (seconds, analytic set)\n")
    lines.append(f"- count={dur['count']:,} · zeros={dur['zeros']:,} · nonpositive={dur['nonpositive']:,}")
    lines.append(f"- min={dur['min']} · mean={dur['mean']} · max={dur['max']}")
    lines.append(f"- over 1h={dur['over_1h']:,} · over 6h={dur['over_6h']:,}")
    lines.append("\n| Percentile | Seconds |")
    lines.append("| :-- | --: |")
    for q, v in dur["percentiles_s"].items():
        lines.append(f"| {q} | {v} |")

    lines.append("\n## Top 20 projects by build count (analytic set)\n")
    lines.append("| Project | Builds | Failures | Failure rate |")
    lines.append("| :-- | --: | --: | --: |")
    for r in p["top_20_projects_by_build_count"]:
        lines.append(f"| {r['project']} | {r['builds']:,} | {r['failures']:,} | {r['failure_rate_pct']}% |")

    lines.append("\n## Per-column null rate (job-row grain, all 66 columns)\n")
    lines.append("| Column | Null % |")
    lines.append("| :-- | --: |")
    for c, v in p["per_column_null_rate_pct"].items():
        lines.append(f"| {c} | {v} |")

    lines.append("")
    (RESULTS / "data_profile.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

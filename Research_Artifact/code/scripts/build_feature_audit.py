"""P1-T2 S4 — build the real feature matrix and write the human-review audit.

One real pass over the backbone CSV produces the analytic-set feature matrix,
then:

  * ``results/p1/feature_audit.md``   — per-feature stats and null rates grouped
    by family, the six highest-variance histograms, and 10 builds traced from
    raw CSV cells to the computed feature vector;
  * ``results/p1/feature_summary.json`` — the same statistics, machine-readable;
  * ``results/p1/hist_*.png``          — the six histograms.

The 10 traced builds are additionally **verified against the raw CSV**: a second
streaming pass re-reads those builds' job rows straight off disk with the stdlib
csv reader, and every traced cell must match what the extractor consumed. A
mismatch aborts the run rather than being reported — the audit is only meaningful
if the trace is verbatim.

Nothing here invents numbers: every figure is computed by this run (R1). The
command and run date are recorded in both outputs.

Run:  python scripts/build_feature_audit.py       (env: PYTHONPATH=.)
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scheduler_core import config, data, features  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1].parent / "results" / "p1"
RUN_DATE = "2026-08-15"
CHUNK = 300_000
N_TRACED = 10
N_HISTOGRAMS = 6
COMMAND = "python scripts/build_feature_audit.py"


# --------------------------------------------------------------------------- #
# Raw-CSV verification of the traced builds
# --------------------------------------------------------------------------- #

def _raise_csv_field_limit() -> int:
    """Let the stdlib reader handle this file's very long list cells.

    ``git_all_built_commits`` holds a ``#``-delimited SHA list that exceeds the
    default 128 KiB field limit. ``sys.maxsize`` overflows the C long on Windows,
    so step down until one is accepted.
    """
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return limit
        except OverflowError:
            limit //= 2


def _missing(text: str) -> bool:
    """True if a literal cell is one of this file's missing-value spellings."""
    return text.strip() in data.NA_TOKENS


def read_raw_rows(
    path: Path, build_ids: set[str]
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], dict[str, int]]:
    """Stream the CSV and collect, for each wanted build:

    * ``literal``  — the first job row's cell text, verbatim (what the audit prints);
    * ``resolved`` — the first **non-missing** cell text per column, which is what
      ``groupby.first()`` selects and therefore what the extractor actually
      consumed (pandas' ``first`` skips nulls);
    * ``n_jobs``   — the build's job-row count.

    Both are kept because they can differ only if a build's job rows disagree on
    a commit-time column — which DL-009 measured as not happening. The audit
    reports whether they in fact differed rather than assuming they did not.

    Uses the stdlib reader (no pandas, no NA coercion), so the text is the file's.
    """
    want = set(build_ids)
    literal: dict[str, dict[str, str]] = {}
    resolved: dict[str, dict[str, str]] = {}
    n_jobs: dict[str, int] = {bid: 0 for bid in want}
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        id_at = header.index("tr_build_id")
        for row in reader:
            bid = row[id_at]
            if bid not in want:
                continue
            cells = dict(zip(header, row))
            n_jobs[bid] += 1
            if bid not in literal:
                literal[bid] = cells
                resolved[bid] = {c: v for c, v in cells.items() if not _missing(v)}
            else:
                for col, val in cells.items():
                    if col not in resolved[bid] and not _missing(val):
                        resolved[bid][col] = val
    return literal, resolved, n_jobs


# --------------------------------------------------------------------------- #
# Histograms
# --------------------------------------------------------------------------- #

def write_histograms(matrix: pd.DataFrame, names: list[str]) -> list[str]:
    """One histogram per named feature; returns the written file names.

    Heavy right tails (churn, sloc, repo commits) make a linear axis unreadable,
    so the x-axis is ``log10(1 + x)`` for non-negative features and linear
    otherwise. The transform is stated on each axis label, not hidden.
    """
    written: list[str] = []
    for name in names:
        v = pd.to_numeric(matrix[name], errors="coerce").dropna()
        fig, ax = plt.subplots(figsize=(6, 3.4), dpi=140)
        if len(v) and float(v.min()) >= 0:
            ax.hist(np.log10(1.0 + v.to_numpy()), bins=60, color="#3b6ea5")
            ax.set_xlabel(f"log10(1 + {name})")
        else:
            ax.hist(v.to_numpy(), bins=60, color="#3b6ea5")
            ax.set_xlabel(name)
        ax.set_ylabel("builds")
        ax.set_title(f"{name}  (n={len(v):,}, var={float(v.var()):,.4g})", fontsize=10)
        fig.tight_layout()
        out = RESULTS / f"hist_{name}.png"
        fig.savefig(out)
        plt.close(fig)
        written.append(out.name)
    return written


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #

def _fmt(x: object) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    if isinstance(x, float):
        return f"{x:,.4g}"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    return str(x)


def write_markdown(payload: dict, summary: pd.DataFrame, traces: list[dict],
                   hist_files: list[str]) -> None:
    p = payload
    L: list[str] = []
    L.append("# Feature Audit — 28 commit-time features (P1-T2)\n")
    L.append(f"> Generated by `{p['provenance']['command']}` on "
             f"{p['provenance']['run_date']}. Every number on this page comes "
             "from that run (R1).\n")
    L.append(f"> Source: `{p['provenance']['dataset_path']}` · grain: **build** "
             "(DL-009) · analytic set per the P0-T2 funnel.\n")
    L.append("\n> **What to check before approving.** (1) The 10 traced builds at "
             "the bottom — do the computed values follow from the raw cells? "
             "(2) The family assignment — every later claim about *which* "
             "characteristics matter is a claim about these six families.\n")

    L.append("\n## Headline counts\n")
    L.append(f"- Analytic builds in the matrix: **{p['counts']['builds']:,}**")
    L.append(f"- Features: **{p['counts']['features']}** "
             f"in **{p['counts']['families']}** disjoint families")
    L.append(f"- Label present (pass/failure): **{p['counts']['labelled']:,}** "
             f"· failure rate **{p['counts']['failure_rate_pct']}%**")
    L.append(f"- Leakage assertion over the produced matrix: "
             f"**{p['checks']['leakage_assertion']}**")
    L.append(f"- Family partition assertion: **{p['checks']['partition_assertion']}**")
    L.append(f"- Blocklisted columns present in the matrix: "
             f"**{p['checks']['blocklisted_columns_in_matrix']}**")
    L.append(f"- Raw-CSV verification of the traced builds: "
             f"**{p['checks']['trace_verification']}** "
             f"({p['checks']['trace_cells_compared']:,} cells compared against a "
             "second, independent streaming pass)")
    L.append(f"- Cells where a build's own job rows disagreed (DL-009 predicts 0): "
             f"**{p['checks']['trace_job_row_disagreements']}**")
    L.append(f"- Wall-clock: {p['provenance']['elapsed_s']}s\n")

    L.append("\n## ⚠ Degenerate features — read this first (DL-016)\n")
    deg = p["degeneracy"]
    dead = [d for d in deg if d["verdict"] == "constant"]
    near = [d for d in deg if d["verdict"] == "near-constant"]
    sparse = [d for d in deg if d["verdict"] == "sparse"]
    L.append(f"Of the 28 contracted features, **{len(dead)} are constant** on this "
             f"release (zero variance — they cannot influence any model), "
             f"**{len(near)} are near-constant** (modal value ≥ "
             f"{100 * p['thresholds']['near_constant_share']:.0f}% of builds), and "
             f"**{len(sparse)} are sparse** (≥ "
             f"{100 * p['thresholds']['sparse_zero_share']:.0f}% zeros but genuinely "
             "varying). The 28-feature contract and the A1.3 family partition are "
             "**unchanged** — see DL-016 for why a constant feature is kept rather "
             "than dropped, and for the effect on each family's ablation arm.\n")
    L.append("| # | feature | family | verdict | distinct values | modal value | "
             "modal share % | zero % |")
    L.append("| --: | :-- | :-- | :-- | --: | :-- | --: | --: |")
    for d in deg:
        if d["verdict"] == "ok":
            continue
        L.append(f"| {d['#']} | `{d['feature']}` | {d['family']} | "
                 f"**{d['verdict']}** | {d['n_unique']:,} | `{d['modal_value']}` | "
                 f"{_fmt(d['modal_share_pct'])} | {_fmt(d['zero_pct'])} |")
    L.append("\n**Per-family impact** (members that are constant or near-constant "
             "cannot contribute to that family's arm):\n")
    L.append("| family | members | constant | near-constant | sparse | effective |")
    L.append("| :-- | --: | --: | --: | --: | --: |")
    for fam in sorted(features.FAMILIES):
        members = features.FAMILIES[fam]
        c = sum(1 for d in deg if d["family"] == fam and d["verdict"] == "constant")
        nc = sum(1 for d in deg if d["family"] == fam and d["verdict"] == "near-constant")
        sp = sum(1 for d in deg if d["family"] == fam and d["verdict"] == "sparse")
        L.append(f"| {fam} — {features.FAMILY_LABELS[fam]} | {len(members)} | {c} | "
                 f"{nc} | {sp} | {len(members) - c - nc} |")

    L.append("\n## Per-feature summary, grouped by family\n")
    L.append("`null_pct` and `zero_pct` are shares of all analytic builds. "
             "`lang` is the one categorical feature (cardinality + mode instead "
             "of moments).\n")
    for fam in sorted(features.FAMILIES):
        members = features.FAMILIES[fam]
        L.append(f"\n### {fam} — {features.FAMILY_LABELS[fam]} "
                 f"({len(members)} features)\n")
        L.append("| # | feature | source column(s) | null % | min | p50 | mean | "
                 "p95 | max | std | zero % |")
        L.append("| --: | :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: |")
        sub = summary[summary["family"] == fam].sort_values("#")
        for _, r in sub.iterrows():
            if r["feature"] in features.CATEGORICAL_FEATURES:
                L.append(f"| {int(r['#'])} | `{r['feature']}` | `{r['source']}` | "
                         f"{_fmt(r['null_pct'])} | *categorical* | "
                         f"{int(r['n_unique'])} values | mode `{r['mode']}` "
                         f"({_fmt(r['mode_pct'])}%) | — | — | — | — |")
            else:
                L.append(
                    f"| {int(r['#'])} | `{r['feature']}` | `{r['source']}` | "
                    f"{_fmt(r['null_pct'])} | {_fmt(r.get('min'))} | "
                    f"{_fmt(r.get('p50'))} | {_fmt(r.get('mean'))} | "
                    f"{_fmt(r.get('p95'))} | {_fmt(r.get('max'))} | "
                    f"{_fmt(r.get('std'))} | {_fmt(r.get('zero_pct'))} |"
                )

    L.append("\n## Language distribution (the one categorical feature)\n")
    L.append("| lang | builds | share % |")
    L.append("| :-- | --: | --: |")
    for k, v in p["lang_distribution"].items():
        L.append(f"| {k} | {v:,} | {round(100 * v / p['counts']['builds'], 2)} |")

    L.append("\n## Histograms — the six highest-variance features\n")
    L.append("Ranked by raw variance over the analytic set (variance is "
             "scale-dependent, so this ranking favours the large-magnitude "
             "counters; the x-axis is log10(1+x) to make the tails legible).\n")
    L.append("| rank | feature | family | variance |")
    L.append("| --: | :-- | :-- | --: |")
    for i, (name, var) in enumerate(p["highest_variance"], start=1):
        fam = next(f for f, m in features.FAMILIES.items() if name in m)
        L.append(f"| {i} | `{name}` | {fam} | {var:,.6g} |")
    L.append("")
    for fn in hist_files:
        L.append(f"![{fn}]({fn})")
    L.append("")

    L.append("\n## Ten builds traced end-to-end (raw CSV → feature vector)\n")
    L.append(f"Sampled with `RANDOM_SEED = {config.RANDOM_SEED}` from the analytic "
             "set. **Raw** is the literal cell text re-read from the CSV by a "
             "second streaming pass; **computed** is what `features.py` produced. "
             "Derived features name their inputs so the arithmetic is checkable "
             "by eye.\n")
    for t in traces:
        L.append(f"\n### `tr_build_id` = {t['tr_build_id']} — "
                 f"{t['gh_project_name']} · started {t['gh_build_started_at']} "
                 f"· label `{t['label']}`\n")
        L.append("| # | feature | raw cell(s) | computed | derivation |")
        L.append("| --: | :-- | :-- | --: | :-- |")
        for row in t["rows"]:
            L.append(f"| {row['#']} | `{row['feature']}` | {row['raw']} | "
                     f"{row['computed']} | {row['derivation']} |")

    L.append("\n---\n")
    L.append("## Contract notes that bite (feature_spec.md §Families)\n")
    L.append("- **F4 is the project-identity–adjacent family.** A positive F4 "
             "result is the most likely to be \"the model learned which repo this "
             "is\" — which is why strategy ④b and the variance decomposition are "
             "mandatory (§A1.9).")
    L.append("- **`is_pr` (24) is also read by the Stage-1 eligibility gate**, so "
             "an F6 gain may partly restate the gate; the overlap is reported, "
             "not claimed as new SE signal.")
    L.append("- **The duration control `d̂` is not a family.** It is present in "
             "every ablation arm including the null — that is what \"beyond "
             "expected build duration\" means (§A1.3).")
    L.append("- **Construction decisions** for this matrix are logged in "
             "`governance/03_DECISION_LOG.md` **DL-015** (the `num_commits` "
             "source, the four unbuildable §3.5 features, and the "
             "missing-value policy).")
    L.append("")
    (RESULTS / "feature_audit.md").write_text("\n".join(L), encoding="utf-8")


# --------------------------------------------------------------------------- #

def main() -> int:
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)

    features.assert_families_partition_features()
    features.assert_no_leakage()
    print("contracts: partition OK, declared-source leakage check OK")

    print(f"reading {data.DEFAULT_DATASET_PATH} …")
    builds = features.load_builds(chunksize=CHUNK)
    print(f"  analytic builds: {len(builds):,}")

    matrix = features.build_feature_matrix(builds)
    label = features.label_from_status(builds)
    matrix[features.LABEL_COLUMN] = label.to_numpy()
    print(f"  matrix: {matrix.shape[0]:,} rows x {len(features.FEATURES)} features")

    # ---- checks, recorded as data ------------------------------------------
    blocklisted_present = [c for c in matrix.columns if features.is_blocklisted(c)]
    features.assert_no_leakage(
        columns=[c for c in matrix.columns if c != features.LABEL_COLUMN]
    )

    summary = features.summarise(matrix)
    degeneracy = features.degeneracy_report(matrix)
    n_dead = int((degeneracy["verdict"] == "constant").sum())
    print(f"  degeneracy: {n_dead} constant, "
          f"{int((degeneracy['verdict'] == 'near-constant').sum())} near-constant, "
          f"{int((degeneracy['verdict'] == 'sparse').sum())} sparse")
    if n_dead:
        print("    constant: "
              + ", ".join(degeneracy.loc[degeneracy["verdict"] == "constant",
                                         "feature"]))

    numeric =[f for f in features.FEATURES if f not in features.CATEGORICAL_FEATURES]
    variances = {
        f: float(pd.to_numeric(matrix[f], errors="coerce").var()) for f in numeric
    }
    top_var = sorted(variances.items(), key=lambda kv: kv[1], reverse=True)[:N_HISTOGRAMS]
    hist_files = write_histograms(matrix, [n for n, _ in top_var])
    print(f"  histograms: {', '.join(hist_files)}")

    # ---- 10 traced builds, verified against the raw CSV ---------------------
    sample = matrix.sample(n=N_TRACED, random_state=config.RANDOM_SEED).sort_index()
    ids = [str(v) for v in sample["tr_build_id"]]
    print(f"  verifying {len(ids)} traced builds against the raw CSV …")
    field_limit = _raise_csv_field_limit()
    raw_rows, resolved_rows, job_counts = read_raw_rows(
        data.DEFAULT_DATASET_PATH, set(ids))
    missing_ids = [i for i in ids if i not in raw_rows]
    if missing_ids:
        print(f"FATAL: traced builds absent from the raw file: {missing_ids}")
        return 1

    # Every source cell the extractor consumed must equal the file's own text.
    cells_compared = 0
    jobs_disagreeing = 0
    for bid in ids:
        loaded = builds.loc[builds["tr_build_id"] == bid].iloc[0]
        for col in features.SOURCE_COLUMNS:
            raw_text = resolved_rows[bid].get(col)          # None => missing
            got = loaded[col]
            got_text = None if pd.isna(got) else str(got)
            if raw_text != got_text:
                print(f"FATAL: build {bid} column {col}: raw {raw_text!r} != "
                      f"loaded {got_text!r}")
                return 1
            cells_compared += 1
            # Did this build's job rows agree, as DL-009 measured?
            first_text = raw_rows[bid][col]
            if (None if _missing(first_text) else first_text) != raw_text:
                jobs_disagreeing += 1
    print(f"  trace verification PASSED ({cells_compared:,} cells; "
          f"{jobs_disagreeing} cell(s) where a build's job rows disagreed)")

    derivations = {
        "files_total": "files_added + files_deleted + files_modified",
        "is_docs_only": "doc_files > 0 AND src_files == 0",
        "test_density_ratio": "test_churn / (src_churn + 1)",
        "hour_of_day": "hour of gh_build_started_at (UTC)",
        "day_of_week": "weekday of gh_build_started_at (Mon=0)",
        "by_core_member": "true/false -> 1/0",
        "is_pr": "true/false -> 1/0",
        "description_complexity": "direct; missing (non-PR) -> 0",
        "num_commits": "direct (git_num_all_built_commits — DL-015)",
    }
    traces: list[dict] = []
    for bid in ids:
        row = sample.loc[sample["tr_build_id"] == bid].iloc[0]
        raw = raw_rows[bid]
        rows = []
        for num, name in features.FEATURE_NUMBERS.items():
            srcs = features.FEATURE_SOURCES[name]
            raw_txt = " · ".join(f"`{c}`={raw[c]}" for c in srcs)
            val = row[name]
            rows.append({
                "#": num,
                "feature": name,
                "raw": raw_txt,
                "computed": _fmt(val) if not isinstance(val, str) else f"`{val}`",
                "derivation": derivations.get(name, "direct"),
            })
        traces.append({
            "tr_build_id": bid,
            "gh_project_name": str(row["gh_project_name"]),
            "gh_build_started_at": str(row["gh_build_started_at"]),
            "label": {1.0: "failure", 0.0: "pass"}.get(
                float(row[features.LABEL_COLUMN]), "?"),
            "rows": rows,
        })

    lang_counts = matrix["lang"].fillna("NA").value_counts().to_dict()
    n_lab = int(matrix[features.LABEL_COLUMN].notna().sum())
    n_fail = int((matrix[features.LABEL_COLUMN] == 1.0).sum())

    payload = {
        "provenance": {
            "command": COMMAND,
            "run_date": RUN_DATE,
            "dataset_path": str(data.DEFAULT_DATASET_PATH),
            "chunksize": CHUNK,
            "random_seed": config.RANDOM_SEED,
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "elapsed_s": round(time.time() - t0, 1),
        },
        "counts": {
            "builds": int(len(matrix)),
            "features": len(features.FEATURES),
            "families": len(features.FAMILIES),
            "labelled": n_lab,
            "failures": n_fail,
            "failure_rate_pct": round(100 * n_fail / n_lab, 4) if n_lab else None,
        },
        "checks": {
            "leakage_assertion": "PASS",
            "partition_assertion": "PASS",
            "blocklisted_columns_in_matrix": len(blocklisted_present),
            "trace_verification": "PASS",
            "trace_cells_compared": cells_compared,
            "trace_job_row_disagreements": jobs_disagreeing,
            "csv_field_size_limit": field_limit,
            "traced_build_job_counts": {b: job_counts[b] for b in ids},
        },
        "families": {f: list(m) for f, m in features.FAMILIES.items()},
        "thresholds": {
            "near_constant_share": features.NEAR_CONSTANT_SHARE,
            "sparse_zero_share": features.SPARSE_ZERO_SHARE,
        },
        "degeneracy": json.loads(degeneracy.to_json(orient="records")),
        "per_feature": json.loads(summary.to_json(orient="records")),
        "highest_variance": top_var,
        "lang_distribution": {str(k): int(v) for k, v in lang_counts.items()},
        "traced_builds": traces,
    }

    (RESULTS / "feature_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    write_markdown(payload, summary, traces, hist_files)
    print(f"\nwrote {RESULTS / 'feature_audit.md'} and feature_summary.json "
          f"in {payload['provenance']['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

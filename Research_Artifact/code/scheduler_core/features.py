"""Commit-time feature extractor (P1-T2).

Implements the 28-feature contract in ``context/feature_spec.md`` exactly, at
**build grain** (DL-009), from the real TravisTorrent columns pinned in
``context/dataset_reference.md``.

Three things in this module are contracts, not conveniences:

* **:data:`FEATURES` is the 28-feature set**, in spec order. Nothing else may
  enter the model matrix.
* **:data:`FAMILIES` is the ablation partition** (A1.3 / feature_spec §Families):
  six disjoint families covering all 28 features. It is emitted as *data* so the
  ablation in P1-T6 iterates it rather than restating it.
* **:data:`LEAKAGE_BLOCKLIST` is enforced programmatically.** Every feature
  declares its source columns in :data:`FEATURE_SOURCES`; :func:`assert_no_leakage`
  fails if any feature is named in the blocklist, is *derived from* a blocklisted
  column, or if a blocklisted column appears among the matrix's columns. This is
  rule R7 and eval_protocol §A1.2: the current build's ``tr_duration`` may never
  reach a decision input, and no ``tr_log_*`` outcome field may either.

The duration control ``d̂`` is **not** a feature and **not** a family — it is
fitted separately (P1-T4) and is present in every ablation arm (A1.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from scheduler_core import data

# --------------------------------------------------------------------------- #
# The 28 features, in feature_spec.md table order (the numbering below is that
# table's `#` column — it is what FAMILIES and the audit refer to).
# --------------------------------------------------------------------------- #

FEATURES: tuple[str, ...] = (
    "src_churn",               # 1
    "test_churn",              # 2
    "files_added",             # 3
    "files_deleted",           # 4
    "files_modified",          # 5
    "files_total",             # 6
    "tests_added",             # 7
    "tests_deleted",           # 8
    "src_files",               # 9
    "doc_files",               # 10
    "other_files",             # 11
    "is_docs_only",            # 12
    "num_commits",             # 13
    "commits_on_files_touched",# 14
    "sloc",                    # 15
    "test_lines_per_kloc",     # 16
    "test_cases_per_kloc",     # 17
    "asserts_per_kloc",        # 18
    "team_size",               # 19
    "by_core_member",          # 20
    "repo_age",                # 21
    "repo_num_commits",        # 22
    "description_complexity",  # 23
    "is_pr",                   # 24
    "lang",                    # 25
    "hour_of_day",             # 26
    "day_of_week",             # 27
    "test_density_ratio",      # 28
)

#: Spec table number -> feature name (used by the audit to print the contract).
FEATURE_NUMBERS: Mapping[int, str] = {i + 1: f for i, f in enumerate(FEATURES)}

#: The one non-numeric feature: a low-cardinality categorical (4 languages,
#: measured — data_profile.md). Encoding is a modelling choice made downstream;
#: the matrix carries the raw label so the audit and the splits can read it.
CATEGORICAL_FEATURES: tuple[str, ...] = ("lang",)

# --------------------------------------------------------------------------- #
# Family partition — the ablation unit (A1.3). Disjoint, covers all 28.
# Changing this changes what RQ1/RQ2 mean and requires a decision-log entry.
# --------------------------------------------------------------------------- #

FAMILIES: Mapping[str, tuple[str, ...]] = {
    "F1": ("src_churn", "test_churn", "files_added", "files_deleted",
           "files_modified", "files_total", "num_commits"),
    "F2": ("src_files", "doc_files", "other_files", "is_docs_only",
           "description_complexity", "test_density_ratio"),
    "F3": ("tests_added", "tests_deleted", "test_lines_per_kloc",
           "test_cases_per_kloc", "asserts_per_kloc"),
    "F4": ("commits_on_files_touched", "sloc", "repo_age", "repo_num_commits",
           "lang"),
    "F5": ("team_size", "by_core_member"),
    "F6": ("is_pr", "hour_of_day", "day_of_week"),
}

FAMILY_LABELS: Mapping[str, str] = {
    "F1": "change size & diffusion",
    "F2": "change purpose & composition",
    "F3": "test activity & maturity",
    "F4": "project history & maturity",
    "F5": "developer & team",
    "F6": "temporal & trigger context",
}

# --------------------------------------------------------------------------- #
# Leakage blocklist (feature_spec.md §Leakage blocklist, strengthened by A1.2).
# Every one of these is known only *after* the build runs, or links to the
# future. None may be a feature, or a source of a feature.
# --------------------------------------------------------------------------- #

LEAKAGE_BLOCKLIST: frozenset[str] = frozenset({
    "tr_status",
    "tr_log_status",
    "tr_log_bool_tests_ran",
    "tr_log_bool_tests_failed",
    "tr_log_num_tests_ok",
    "tr_log_num_tests_failed",
    "tr_log_num_tests_run",
    "tr_log_num_tests_skipped",
    "tr_log_num_test_suites_run",
    "tr_log_num_test_suites_ok",
    "tr_log_num_test_suites_failed",
    "tr_log_tests_failed",
    "tr_log_testduration",
    "tr_log_buildduration",
    "tr_duration",
    "tr_prev_build",          # future linkage
    # Remaining post-run log fields, blocked for the same reason as the above.
    "tr_log_lan",
    "tr_log_setup_time",
    "tr_log_analyzer",
    "tr_log_frameworks",
})

#: Prefix rule: anything in the ``tr_log_*`` family is post-run by construction,
#: so new columns matching it are blocked without needing to be enumerated.
LEAKAGE_PREFIXES: tuple[str, ...] = ("tr_log_",)

# --------------------------------------------------------------------------- #
# Feature -> the raw CSV column(s) it is derived from. This is the object the
# leakage assertion actually checks, so a feature cannot acquire a blocklisted
# source without the test failing.
# --------------------------------------------------------------------------- #

FEATURE_SOURCES: Mapping[str, tuple[str, ...]] = {
    "src_churn": ("git_diff_src_churn",),
    "test_churn": ("git_diff_test_churn",),
    "files_added": ("gh_diff_files_added",),
    "files_deleted": ("gh_diff_files_deleted",),
    "files_modified": ("gh_diff_files_modified",),
    "files_total": ("gh_diff_files_added", "gh_diff_files_deleted",
                    "gh_diff_files_modified"),
    "tests_added": ("gh_diff_tests_added",),
    "tests_deleted": ("gh_diff_tests_deleted",),
    "src_files": ("gh_diff_src_files",),
    "doc_files": ("gh_diff_doc_files",),
    "other_files": ("gh_diff_other_files",),
    "is_docs_only": ("gh_diff_src_files", "gh_diff_doc_files"),
    "num_commits": ("git_num_all_built_commits",),   # DL-015: forced choice
    "commits_on_files_touched": ("gh_num_commits_on_files_touched",),
    "sloc": ("gh_sloc",),
    "test_lines_per_kloc": ("gh_test_lines_per_kloc",),
    "test_cases_per_kloc": ("gh_test_cases_per_kloc",),
    "asserts_per_kloc": ("gh_asserts_cases_per_kloc",),
    "team_size": ("gh_team_size",),
    "by_core_member": ("gh_by_core_team_member",),
    "repo_age": ("gh_repo_age",),
    "repo_num_commits": ("gh_repo_num_commits",),
    "description_complexity": ("gh_description_complexity",),
    "is_pr": ("gh_is_pr",),
    "lang": ("gh_lang",),
    "hour_of_day": ("gh_build_started_at",),
    "day_of_week": ("gh_build_started_at",),
    "test_density_ratio": ("git_diff_test_churn", "git_diff_src_churn"),
}

#: Raw columns the extractor reads for *features* (deduped, header order).
SOURCE_COLUMNS: tuple[str, ...] = tuple(
    c for c in data.EXPECTED_HEADER
    if c in {col for cols in FEATURE_SOURCES.values() for col in cols}
)

#: Columns the extractor reads for identity / label / aggregation but which are
#: **not** features. ``tr_status`` is the label (blocklisted as a feature by
#: construction); it is carried on the frame only when explicitly requested.
KEY_COLUMNS: tuple[str, ...] = ("tr_build_id", "gh_project_name",
                                "gh_build_started_at")
LABEL_COLUMN: str = "y_fail"

#: Features whose spec derivation defines a missing value (feature_spec #23:
#: "NA -> 0 for non-PR"). No other feature is imputed here; see DL-015.
_SPEC_FILL_ZERO: tuple[str, ...] = ("description_complexity",)


class LeakageError(AssertionError):
    """Raised when a blocklisted column, or something derived from one, would
    reach the feature matrix (R7 / eval_protocol §A1.2)."""


def is_blocklisted(column: str) -> bool:
    """True if ``column`` is an outcome/duration/future-linkage column."""
    return column in LEAKAGE_BLOCKLIST or column.startswith(LEAKAGE_PREFIXES)


def assert_no_leakage(
    columns: Iterable[str] | None = None,
    sources: Mapping[str, Sequence[str]] | None = None,
) -> None:
    """Fail loudly if any blocklisted column, or a feature derived from one,
    would enter the model matrix.

    Two independent checks, because they catch different mistakes:

    1. **Declared-source check** — every entry of ``sources`` (default
       :data:`FEATURE_SOURCES`) must draw only on non-blocklisted columns. This
       catches "I built a feature out of ``tr_duration``".
    2. **Matrix-column check** — no column of ``columns`` may be blocklisted, or
       named identically to a blocklisted column. This catches "a raw outcome
       column rode along on the frame".

    Raises :class:`LeakageError` naming the offending feature and column.
    """
    sources = FEATURE_SOURCES if sources is None else sources

    offences: list[str] = []
    for feature, cols in sources.items():
        if is_blocklisted(feature):
            offences.append(f"feature {feature!r} is itself a blocklisted column")
        for col in cols:
            if is_blocklisted(col):
                offences.append(
                    f"feature {feature!r} is derived from blocklisted column {col!r}"
                )
    if columns is not None:
        for col in columns:
            if is_blocklisted(col):
                offences.append(f"blocklisted column {col!r} is present in the matrix")

    if offences:
        raise LeakageError(
            "commit-time-only violation (R7 / eval_protocol §A1.2):\n  "
            + "\n  ".join(sorted(set(offences)))
        )


def assert_families_partition_features() -> None:
    """Fail unless :data:`FAMILIES` is a disjoint partition of :data:`FEATURES`.

    A1.3 requires exactly six disjoint families covering all 28 features; the
    ablation's meaning depends on it, so it is asserted rather than trusted.
    """
    seen: dict[str, str] = {}
    for fam, members in FAMILIES.items():
        for name in members:
            if name in seen:
                raise AssertionError(
                    f"feature {name!r} appears in both {seen[name]} and {fam} "
                    "— families must be disjoint (A1.3)"
                )
            seen[name] = fam
    missing = [f for f in FEATURES if f not in seen]
    extra = [f for f in seen if f not in FEATURES]
    if missing or extra:
        raise AssertionError(
            f"families do not cover FEATURES exactly: missing={missing}, extra={extra}"
        )
    if len(FEATURES) != 28:
        raise AssertionError(f"expected 28 features, found {len(FEATURES)}")


#: The timestamp spelling used throughout the real file (verified against the
#: header row of `final-2017-01-25.csv`: e.g. ``2011-04-16 11:24:39``).
TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def parse_started_at(values: pd.Series) -> pd.Series:
    """Parse ``gh_build_started_at`` to UTC timestamps.

    The pinned format is tried first (fast, and consistent by construction); any
    non-null value it cannot parse is retried with inference so an unexpected
    spelling surfaces as a real timestamp rather than a silent NaT. Genuinely
    unparseable values remain NaT and are dropped by the analytic funnel.
    """
    # A frame built outside `data.read_chunks` may still carry the literal NA
    # tokens; treat them as missing so they never reach the dateutil fallback.
    values = values.mask(values.isin(data.NA_TOKENS))
    parsed = pd.to_datetime(values, format=TIMESTAMP_FORMAT, errors="coerce",
                            utc=True)
    residual = parsed.isna() & values.notna()
    if residual.any():
        parsed.loc[residual] = pd.to_datetime(
            values.loc[residual], errors="coerce", utc=True
        )
    return parsed


def _num(frame: pd.DataFrame, col: str) -> pd.Series:
    """Numeric view of a raw string column; unparseable values -> NaN."""
    return pd.to_numeric(frame[col], errors="coerce")


def _bool01(frame: pd.DataFrame, col: str) -> pd.Series:
    """Map TravisTorrent's boolean spelling to {0,1}; anything else -> NaN.

    The file writes booleans as the strings ``true``/``false`` (also seen
    capitalised); numeric 0/1 is accepted defensively.
    """
    s = frame[col].astype("string").str.strip().str.lower()
    mapped = s.map({"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0})
    return pd.to_numeric(mapped, errors="coerce")


def build_feature_matrix(
    builds: pd.DataFrame,
    *,
    with_keys: bool = True,
    strict: bool = True,
) -> pd.DataFrame:
    """Compute the 28-feature matrix from **build-grain** rows.

    Parameters
    ----------
    builds:
        One row per ``tr_build_id`` (see :func:`aggregate_builds_for_features`),
        carrying the raw string columns in :data:`SOURCE_COLUMNS`.
    with_keys:
        Also carry :data:`KEY_COLUMNS` (identity + arrival time) on the result.
        These are not features; splits and the simulator need them.
    strict:
        Run :func:`assert_no_leakage` over the produced columns (default on —
        turning it off is only for tests that deliberately probe the assertion).

    Returns a frame whose feature columns are exactly :data:`FEATURES`, in order.
    """
    missing = [c for c in SOURCE_COLUMNS if c not in builds.columns]
    if missing:
        raise KeyError(f"build frame is missing source columns: {missing}")

    out = pd.DataFrame(index=builds.index)

    # --- F1 change size & diffusion ---------------------------------------
    out["src_churn"] = _num(builds, "git_diff_src_churn")
    out["test_churn"] = _num(builds, "git_diff_test_churn")
    added = _num(builds, "gh_diff_files_added")
    deleted = _num(builds, "gh_diff_files_deleted")
    modified = _num(builds, "gh_diff_files_modified")
    out["files_added"] = added
    out["files_deleted"] = deleted
    out["files_modified"] = modified
    out["files_total"] = added + deleted + modified
    # `gh_num_commits_in_push` is 100% null in this release (data_profile.md),
    # so change size comes from `git_num_all_built_commits` — DL-015.
    out["num_commits"] = _num(builds, "git_num_all_built_commits")

    # --- F3 test activity --------------------------------------------------
    out["tests_added"] = _num(builds, "gh_diff_tests_added")
    out["tests_deleted"] = _num(builds, "gh_diff_tests_deleted")

    # --- F2 change purpose & composition -----------------------------------
    src_files = _num(builds, "gh_diff_src_files")
    doc_files = _num(builds, "gh_diff_doc_files")
    out["src_files"] = src_files
    out["doc_files"] = doc_files
    out["other_files"] = _num(builds, "gh_diff_other_files")
    # Spec #12: doc_files > 0 AND src_files == 0. NaN in either input propagates
    # rather than silently reading as "not docs-only".
    docs_only = (doc_files > 0) & (src_files == 0)
    out["is_docs_only"] = docs_only.astype("float64").where(
        src_files.notna() & doc_files.notna()
    )

    # --- F4 project history & maturity -------------------------------------
    out["commits_on_files_touched"] = _num(builds, "gh_num_commits_on_files_touched")
    out["sloc"] = _num(builds, "gh_sloc")

    # --- F3 test maturity ---------------------------------------------------
    out["test_lines_per_kloc"] = _num(builds, "gh_test_lines_per_kloc")
    out["test_cases_per_kloc"] = _num(builds, "gh_test_cases_per_kloc")
    out["asserts_per_kloc"] = _num(builds, "gh_asserts_cases_per_kloc")

    # --- F5 developer & team ------------------------------------------------
    out["team_size"] = _num(builds, "gh_team_size")
    out["by_core_member"] = _bool01(builds, "gh_by_core_team_member")

    # --- F4 maturity --------------------------------------------------------
    out["repo_age"] = _num(builds, "gh_repo_age")
    out["repo_num_commits"] = _num(builds, "gh_repo_num_commits")

    # --- F2 change intent ---------------------------------------------------
    # Spec #23: NA -> 0 for non-PR builds (the field only exists for PRs).
    out["description_complexity"] = _num(builds, "gh_description_complexity").fillna(0.0)

    # --- F6 temporal & trigger context --------------------------------------
    out["is_pr"] = _bool01(builds, "gh_is_pr")
    started = parse_started_at(builds["gh_build_started_at"])
    out["hour_of_day"] = started.dt.hour.astype("float64")
    out["day_of_week"] = started.dt.dayofweek.astype("float64")

    # --- F4 context (categorical) -------------------------------------------
    out["lang"] = builds["gh_lang"].astype("string")

    # --- F2 test discipline --------------------------------------------------
    # Spec #28: test_churn / (src_churn + 1).
    out["test_density_ratio"] = out["test_churn"] / (out["src_churn"] + 1.0)

    out = out[list(FEATURES)]

    if with_keys:
        for key in reversed(KEY_COLUMNS):
            if key in builds.columns:
                out.insert(0, key, builds[key])

    if strict:
        assert_no_leakage(columns=out.columns)
    return out


def label_from_status(builds: pd.DataFrame) -> pd.Series:
    """Binary failure label from ``tr_status`` (DL-009): failure -> 1, pass -> 0.

    ``canceled`` / missing / unrecognised statuses map to NaN so the caller must
    decide explicitly; the analytic set excludes them (data_profile.md funnel).
    This is the **label**, never a feature — hence a separate function.
    """
    cls = builds[data.LABEL_COL].map(data.classify_status)
    return cls.map({"failure": 1.0, "pass": 0.0}).astype("float64").rename(LABEL_COLUMN)


# --------------------------------------------------------------------------- #
# Build-grain aggregation for feature extraction
# --------------------------------------------------------------------------- #

#: Every column the extractor needs off the raw CSV: features + keys + label.
READ_COLUMNS: tuple[str, ...] = tuple(
    c for c in data.EXPECTED_HEADER
    if c in set(SOURCE_COLUMNS) | set(KEY_COLUMNS) | {data.LABEL_COL}
)


def aggregate_builds_for_features(jobs: pd.DataFrame) -> pd.DataFrame:
    """Reduce job rows to one row per ``tr_build_id``, keeping feature columns.

    Per DL-009 all commit-time columns are build-level and identical across a
    build's job rows, so ``first`` is the aggregation. ``tr_duration`` is
    **deliberately not aggregated here** — this path feeds features only, and
    duration is not permitted to travel with them (A1.2).
    """
    if "tr_build_id" not in jobs.columns:
        raise KeyError("aggregate_builds_for_features requires 'tr_build_id'")
    cols = [c for c in jobs.columns if c != "tr_build_id"]
    return jobs.groupby("tr_build_id", sort=False)[cols].first()


def _reduce(running: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """Combine per-chunk build aggregates, keeping the earliest row per build.

    Builds straddle chunk boundaries, so the reduction must be global (the same
    pattern as ``scripts/profile_data.py``).
    """
    if running is None:
        return new
    return pd.concat([running, new]).groupby(level=0, sort=False).first()


def load_builds(
    path: str | Path = data.DEFAULT_DATASET_PATH,
    *,
    chunksize: int = 300_000,
    analytic_only: bool = True,
) -> pd.DataFrame:
    """Read the backbone CSV and return **build-grain** rows for feature work.

    ``analytic_only`` applies the P0-T2 funnel's build-level filters (drop
    missing/unrecognised label, exclude ``canceled``, require a parseable
    ``gh_build_started_at``) so the matrix covers the analytic set defined in
    ``results/p0/data_profile.md``.
    """
    builds: pd.DataFrame | None = None
    for chunk in data.read_chunks(path, chunksize=chunksize, usecols=READ_COLUMNS):
        builds = _reduce(builds, aggregate_builds_for_features(chunk))
    if builds is None:
        return pd.DataFrame(columns=[c for c in READ_COLUMNS if c != "tr_build_id"])
    builds = builds.reset_index()

    if analytic_only:
        builds = builds.loc[analytic_mask(builds)]
    return builds.reset_index(drop=True)


def analytic_mask(builds: pd.DataFrame) -> pd.Series:
    """Boolean mask selecting the **analytic set** at build grain.

    The P0-T2 funnel's build-level filters, in one place so that every consumer
    (the feature matrix, the split maker) selects an identical population:
    a recognised pass/failure label (drops ``canceled``, missing and unexpected
    statuses) and a parseable ``gh_build_started_at``. Measured size on this
    release: 922,624 builds (``results/p0/data_profile.md``).
    """
    labelled = builds[data.LABEL_COL].map(data.classify_status).isin(
        ["failure", "pass"])
    timed = parse_started_at(builds["gh_build_started_at"]).notna()
    return labelled & timed


def extract(
    path: str | Path = data.DEFAULT_DATASET_PATH,
    *,
    chunksize: int = 300_000,
    with_label: bool = True,
) -> pd.DataFrame:
    """End-to-end: raw CSV -> analytic build-grain feature matrix (+ label).

    The label is returned as a separate column :data:`LABEL_COLUMN`; it is a
    target, and any model code must drop it from the design matrix by taking
    :data:`FEATURES` explicitly rather than "all columns except".
    """
    builds = load_builds(path, chunksize=chunksize)
    matrix = build_feature_matrix(builds)
    if with_label:
        matrix[LABEL_COLUMN] = label_from_status(builds).to_numpy()
    return matrix


# --------------------------------------------------------------------------- #
# Degeneracy reporting
#
# Reporting thresholds only — they classify what the audit prints and change no
# model, threshold, or metric. They are deliberately not eval_protocol
# quantities, so they need no predeclaration.
# --------------------------------------------------------------------------- #

NEAR_CONSTANT_SHARE: float = 0.99
SPARSE_ZERO_SHARE: float = 0.90


def degeneracy_report(matrix: pd.DataFrame) -> pd.DataFrame:
    """Flag features that cannot carry information on this dataset.

    A feature whose column is constant has zero variance and therefore cannot
    change any model's prediction, no matter which family it sits in. Detecting
    that is not optional bookkeeping: the family ablation (A1.3) reports results
    *per family*, so a dead member silently weakens its family's arm and would
    otherwise be read as "these characteristics don't matter" when the truth is
    "this release does not record them" (DL-016).

    Verdicts: ``constant`` (≤1 distinct value), ``near-constant`` (modal value
    covers ≥ :data:`NEAR_CONSTANT_SHARE`), ``sparse`` (≥ :data:`SPARSE_ZERO_SHARE`
    zeros but genuinely varying), else ``ok``.
    """
    fam_of = {name: fam for fam, members in FAMILIES.items() for name in members}
    n = len(matrix)
    rows: list[dict[str, object]] = []
    for num, name in FEATURE_NUMBERS.items():
        col = matrix[name]
        nunique = int(col.nunique(dropna=True))
        vc = col.value_counts(dropna=True)
        modal_share = float(vc.iloc[0]) / n if (n and not vc.empty) else float("nan")
        if name in CATEGORICAL_FEATURES:
            zero_share = float("nan")
        else:
            v = pd.to_numeric(col, errors="coerce")
            zero_share = float((v == 0).sum()) / n if n else float("nan")

        if nunique <= 1:
            verdict = "constant"
        elif modal_share >= NEAR_CONSTANT_SHARE:
            verdict = "near-constant"
        elif zero_share == zero_share and zero_share >= SPARSE_ZERO_SHARE:
            verdict = "sparse"
        else:
            verdict = "ok"

        rows.append({
            "#": num,
            "feature": name,
            "family": fam_of[name],
            "n_unique": nunique,
            "modal_value": None if vc.empty else str(vc.index[0]),
            "modal_share_pct": round(100 * modal_share, 4),
            "zero_pct": (None if zero_share != zero_share
                         else round(100 * zero_share, 4)),
            "verdict": verdict,
        })
    return pd.DataFrame(rows)


def summarise(matrix: pd.DataFrame) -> pd.DataFrame:
    """Per-feature summary statistics for the audit, grouped by family.

    Returns one row per feature: family, dtype, null rate, and the numeric
    distribution (min/median/mean/max/std/p95 and zero share). Categorical
    features report cardinality and the modal value instead of moments.
    """
    fam_of = {name: fam for fam, members in FAMILIES.items() for name in members}
    rows: list[dict[str, object]] = []
    n = len(matrix)
    for num, name in FEATURE_NUMBERS.items():
        col = matrix[name]
        nulls = int(col.isna().sum())
        row: dict[str, object] = {
            "#": num,
            "feature": name,
            "family": fam_of[name],
            "source": " + ".join(FEATURE_SOURCES[name]),
            "dtype": str(col.dtype),
            "n": n,
            "null_pct": round(100 * nulls / n, 4) if n else None,
        }
        if name in CATEGORICAL_FEATURES:
            vc = col.value_counts(dropna=True)
            row.update({
                "n_unique": int(col.nunique(dropna=True)),
                "mode": None if vc.empty else str(vc.index[0]),
                "mode_pct": None if vc.empty else round(100 * int(vc.iloc[0]) / n, 2),
            })
        else:
            v = pd.to_numeric(col, errors="coerce").dropna()
            if len(v):
                row.update({
                    "min": float(v.min()),
                    "p50": float(np.percentile(v, 50)),
                    "mean": round(float(v.mean()), 4),
                    "p95": float(np.percentile(v, 95)),
                    "max": float(v.max()),
                    "std": round(float(v.std()), 4),
                    "zero_pct": round(100 * float((v == 0).sum()) / n, 2) if n else None,
                })
        rows.append(row)
    return pd.DataFrame(rows)

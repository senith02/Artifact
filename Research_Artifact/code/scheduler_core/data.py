"""Data-loading harness for the TravisTorrent backbone dataset (P0-T2).

This module is the *only* sanctioned entry point for reading the raw CSV. It
enforces two non-negotiable rules from ``governance/02_ANTI_HALLUCINATION.md``:

* **R2 — code against the real header, not memory.** ``EXPECTED_HEADER`` below is
  the verbatim 66-column header of ``final-2017-01-25.csv`` (also pinned in
  ``context/dataset_reference.md``). Every read validates the file's header
  against it and *fails loudly* on any mismatch — a corrupted or swapped file
  cannot silently feed wrong columns into the pipeline.
* **R8 — reproducibility.** The dataset path and chunk size are explicit; nothing
  is read except through :func:`read_chunks`, which always validates first.

Modelling grain (job rows -> builds) and the cleaning funnel are decided in
P0-T2 S2/S3; the relevant constants and helpers live here so both the profiler
and later feature code share one definition.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator, Sequence

import pandas as pd

# --------------------------------------------------------------------------- #
# File location
# --------------------------------------------------------------------------- #

# Path is relative to the working root (Research_Artifact/). Resolved against
# this file's location so it works regardless of the process CWD.
_REPO_ROOT = Path(__file__).resolve().parents[2]  # .../Research_Artifact
DEFAULT_DATASET_PATH = (
    _REPO_ROOT.parent
    / "Dataset"
    / "19314170"
    / "final-2017-01-25.csv"
    / "final-2017-01-25.csv"
)

# --------------------------------------------------------------------------- #
# The real header — pinned verbatim (R2). Read from the actual file, in order.
# Mirrors context/dataset_reference.md. DO NOT reorder or rename.
# --------------------------------------------------------------------------- #

EXPECTED_HEADER: tuple[str, ...] = (
    "tr_build_id", "gh_project_name", "gh_is_pr", "gh_pr_created_at",
    "gh_pull_req_num", "gh_lang", "git_merged_with", "git_branch",
    "gh_num_commits_in_push", "gh_commits_in_push",
    "git_prev_commit_resolution_status", "git_prev_built_commit",
    "tr_prev_build", "gh_first_commit_created_at", "gh_team_size",
    "git_all_built_commits", "git_num_all_built_commits", "git_trigger_commit",
    "tr_virtual_merged_into", "gh_num_issue_comments", "gh_num_commit_comments",
    "gh_num_pr_comments", "git_diff_src_churn", "git_diff_test_churn",
    "gh_diff_files_added", "gh_diff_files_deleted", "gh_diff_files_modified",
    "gh_diff_tests_added", "gh_diff_tests_deleted", "gh_diff_src_files",
    "gh_diff_doc_files", "gh_diff_other_files", "gh_num_commits_on_files_touched",
    "gh_sloc", "gh_test_lines_per_kloc", "gh_test_cases_per_kloc",
    "gh_asserts_cases_per_kloc", "gh_by_core_team_member",
    "gh_description_complexity", "gh_pushed_at", "gh_build_started_at",
    "gh_repo_age", "gh_repo_num_commits", "tr_job_id", "tr_build_number",
    "tr_log_lan", "tr_log_status", "tr_log_setup_time", "tr_log_analyzer",
    "tr_log_frameworks", "tr_log_bool_tests_ran", "tr_log_bool_tests_failed",
    "tr_log_num_tests_ok", "tr_log_num_tests_failed", "tr_log_num_tests_run",
    "tr_log_num_tests_skipped", "tr_log_num_test_suites_run",
    "tr_log_num_test_suites_ok", "tr_log_num_test_suites_failed",
    "tr_log_tests_failed", "tr_log_testduration", "tr_log_buildduration",
    "tr_original_commit", "tr_duration", "tr_status", "tr_jobs",
)

# --------------------------------------------------------------------------- #
# Label / status vocabulary (see dataset_reference.md §Label)
# --------------------------------------------------------------------------- #

LABEL_COL = "tr_status"
FAILURE_STATUSES = frozenset({"failed", "errored"})
PASS_STATUSES = frozenset({"passed"})
CANCELED_STATUS = "canceled"

# Columns that hold `#`-delimited lists inside a single CSV cell.
HASH_LIST_COLS: tuple[str, ...] = ("gh_commits_in_push", "git_all_built_commits")

# Timestamp columns (parsed; unparseable -> NaT).
TIMESTAMP_COLS: tuple[str, ...] = (
    "gh_pr_created_at", "gh_first_commit_created_at", "gh_pushed_at",
    "gh_build_started_at",
)

# Strings pandas should treat as missing in this dataset.
NA_TOKENS: tuple[str, ...] = ("NA", "")


class HeaderMismatchError(ValueError):
    """Raised when the CSV header does not match :data:`EXPECTED_HEADER`.

    Carries a human-readable diff so a swapped/corrupted file is obvious.
    """


def _read_raw_header(path: Path) -> list[str]:
    """Return the first CSV row of ``path`` as a list of field names."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            return next(reader)
        except StopIteration as exc:  # empty file
            raise HeaderMismatchError(f"{path} is empty — no header row.") from exc


def validate_header(path: str | Path = DEFAULT_DATASET_PATH) -> list[str]:
    """Validate the file header against :data:`EXPECTED_HEADER`, verbatim.

    Returns the header on success; raises :class:`HeaderMismatchError` with a
    precise diff on any difference in names, order, or count (R2).
    """
    path = Path(path)
    actual = _read_raw_header(path)
    expected = list(EXPECTED_HEADER)
    if actual == expected:
        return actual

    problems: list[str] = []
    if len(actual) != len(expected):
        problems.append(
            f"column count {len(actual)} != expected {len(expected)}"
        )
    # Per-position diff for the overlapping prefix.
    for i, (a, e) in enumerate(zip(actual, expected)):
        if a != e:
            problems.append(f"col {i}: got {a!r}, expected {e!r}")
    extra = actual[len(expected):]
    missing = expected[len(actual):]
    if extra:
        problems.append(f"unexpected trailing columns: {extra}")
    if missing:
        problems.append(f"missing trailing columns: {missing}")
    raise HeaderMismatchError(
        f"Header of {path} does not match the pinned TravisTorrent header.\n  "
        + "\n  ".join(problems[:20])
        + ("\n  ..." if len(problems) > 20 else "")
    )


def read_chunks(
    path: str | Path = DEFAULT_DATASET_PATH,
    *,
    chunksize: int = 200_000,
    usecols: Sequence[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield the dataset in row chunks, after validating the header (R2).

    All columns are read as strings (``dtype=str``) so that ``#``-list cells and
    mixed NA tokens are not silently coerced; downstream code casts explicitly.
    ``NA`` and empty strings are treated as missing.

    Parameters
    ----------
    path: dataset CSV path (defaults to the read-only backbone file).
    chunksize: rows per chunk.
    usecols: optional subset of columns to read (must all be in the header).
    """
    path = Path(path)
    validate_header(path)
    if usecols is not None:
        unknown = [c for c in usecols if c not in EXPECTED_HEADER]
        if unknown:
            raise KeyError(f"usecols contains non-header columns: {unknown}")
    yield from pd.read_csv(
        path,
        chunksize=chunksize,
        usecols=list(usecols) if usecols is not None else None,
        dtype=str,
        keep_default_na=False,
        na_values=list(NA_TOKENS),
        encoding="utf-8",
    )


def classify_status(status: object) -> str:
    """Map a raw ``tr_status`` value to a label class (DL-009).

    Returns one of ``"failure"`` ({failed, errored}), ``"pass"`` ({passed}),
    ``"canceled"``, ``"missing"`` (null/empty), or ``"other"`` (any unexpected
    value — surfaced rather than silently bucketed).
    """
    if status is None or (isinstance(status, float) and pd.isna(status)):
        return "missing"
    s = str(status).strip().lower()
    if s in ("", "na", "nan"):
        return "missing"
    if s in FAILURE_STATUSES:
        return "failure"
    if s in PASS_STATUSES:
        return "pass"
    if s == CANCELED_STATUS:
        return "canceled"
    return "other"


# Columns aggregated to build grain by taking the first (build-level) value.
# All commit-time features are identical across a build's job rows (DL-009);
# we list only what the profiler/label/feature code currently needs by name.
_BUILD_FIRST_COLS: tuple[str, ...] = (
    "gh_project_name", "gh_lang", "tr_status", "gh_build_started_at",
)


def aggregate_to_builds(jobs: pd.DataFrame) -> pd.DataFrame:
    """Aggregate job rows to one row per ``tr_build_id`` (DL-009).

    ``first`` for build-level columns, ``max`` for ``tr_duration`` (handles the
    ~0.04% of builds whose rows disagree), ``n_jobs`` = row count. Input frames
    must contain ``tr_build_id`` and the columns being aggregated; intended for
    in-memory frames and for chunk-wise reduction by the profiler.
    """
    if "tr_build_id" not in jobs.columns:
        raise KeyError("aggregate_to_builds requires a 'tr_build_id' column")
    present_first = [c for c in _BUILD_FIRST_COLS if c in jobs.columns]
    agg: dict[str, tuple[str, str]] = {c: (c, "first") for c in present_first}
    if "tr_duration" in jobs.columns:
        dur = pd.to_numeric(jobs["tr_duration"], errors="coerce")
        jobs = jobs.assign(_tr_duration_num=dur)
        agg["tr_duration"] = ("_tr_duration_num", "max")
    out = jobs.groupby("tr_build_id", sort=False).agg(**agg)
    out["n_jobs"] = jobs.groupby("tr_build_id", sort=False).size()
    return out.reset_index()


def parse_hash_list(value: object) -> list[str]:
    """Split a ``#``-delimited list cell into its elements.

    Returns ``[]`` for missing/empty cells. Used for ``gh_commits_in_push`` and
    ``git_all_built_commits`` (dataset_reference.md gotcha #4).
    """
    if value is None:
        return []
    if isinstance(value, float):  # NaN
        return []
    s = str(value).strip()
    if not s or s == "NA":
        return []
    return [part for part in s.split("#") if part]

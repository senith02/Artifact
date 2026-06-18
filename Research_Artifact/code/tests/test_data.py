"""Tests for the data-loading harness (P0-T2 S1).

Covers the header-validation contract (R2): the real file's header must pass,
a deliberately corrupted header must fail loudly, and the `#`-list parser must
behave on the dataset's list cells.
"""

import csv
from pathlib import Path

import pandas as pd
import pytest

from scheduler_core import data

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------- #
# Negative test: a corrupted/swapped header must raise (the safety net).
# --------------------------------------------------------------------------- #

def test_corrupted_header_is_rejected():
    """A file whose header differs (wrong names, wrong count) fails loudly."""
    with pytest.raises(data.HeaderMismatchError) as exc:
        data.validate_header(FIXTURES / "bad_header.csv")
    # The error names a concrete discrepancy, not a generic message.
    assert "count" in str(exc.value) or "expected" in str(exc.value)


def test_read_chunks_rejects_bad_header_before_yielding():
    """read_chunks validates first — it must not yield rows from a bad file."""
    gen = data.read_chunks(FIXTURES / "bad_header.csv", chunksize=10)
    with pytest.raises(data.HeaderMismatchError):
        next(gen)


# --------------------------------------------------------------------------- #
# Positive test on a synthetic file built from the pinned header.
# --------------------------------------------------------------------------- #

def test_valid_header_passes(tmp_path):
    """A file written with EXPECTED_HEADER validates and reads back its rows."""
    p = tmp_path / "good.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(data.EXPECTED_HEADER)
        row = ["NA"] * len(data.EXPECTED_HEADER)
        row[0] = "100"           # tr_build_id
        row[64] = "passed"       # tr_status
        w.writerow(row)

    assert data.validate_header(p) == list(data.EXPECTED_HEADER)
    chunks = list(data.read_chunks(p, chunksize=10))
    assert len(chunks) == 1
    assert list(chunks[0].columns) == list(data.EXPECTED_HEADER)
    assert chunks[0].iloc[0]["tr_status"] == "passed"


def test_usecols_must_be_real_columns(tmp_path):
    """Requesting a non-header column is a hard error (guards typos)."""
    p = tmp_path / "good.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(data.EXPECTED_HEADER)
    with pytest.raises(KeyError):
        list(data.read_chunks(p, usecols=["gh_src_churn"]))  # paper name, not real


# --------------------------------------------------------------------------- #
# Positive test on the REAL dataset (DoD: "loader reads real rows").
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(
    not data.DEFAULT_DATASET_PATH.exists(),
    reason="real TravisTorrent CSV not present in this environment",
)
def test_real_file_header_and_rows():
    """The real backbone file validates and yields non-empty rows of 66 cols."""
    assert data.validate_header() == list(data.EXPECTED_HEADER)
    first = next(data.read_chunks(chunksize=1000))
    assert first.shape[1] == 66
    assert len(first) > 0
    assert "tr_status" in first.columns


# --------------------------------------------------------------------------- #
# The `#`-list cell parser.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value,expected",
    [
        (None, []),
        ("", []),
        ("NA", []),
        ("abc", ["abc"]),
        ("a#b#c", ["a", "b", "c"]),
        ("a##b#", ["a", "b"]),  # empty segments dropped
    ],
)
def test_parse_hash_list(value, expected):
    assert data.parse_hash_list(value) == expected


# --------------------------------------------------------------------------- #
# Label classification (DL-009).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value,expected",
    [
        ("passed", "pass"),
        ("failed", "failure"),
        ("errored", "failure"),
        ("canceled", "canceled"),
        ("PASSED", "pass"),       # case-insensitive
        ("", "missing"),
        (None, "missing"),
        ("weird", "other"),
    ],
)
def test_classify_status(value, expected):
    assert data.classify_status(value) == expected


# --------------------------------------------------------------------------- #
# Build-grain aggregation (DL-009): first for build-level cols, max for
# tr_duration, n_jobs = row count.
# --------------------------------------------------------------------------- #

def test_aggregate_to_builds():
    jobs = pd.DataFrame({
        "tr_build_id": ["b1", "b1", "b1", "b2"],
        "gh_project_name": ["p/x", "p/x", "p/x", "p/y"],
        "gh_lang": ["ruby", "ruby", "ruby", "java"],
        "tr_status": ["failed", "failed", "failed", "passed"],
        "gh_build_started_at": ["2014-01-01", "2014-01-01", "2014-01-01", "2014-02-01"],
        "tr_duration": ["100", "120", "110", "50"],   # b1 inconsistent -> max
    })
    builds = data.aggregate_to_builds(jobs).set_index("tr_build_id")
    assert len(builds) == 2
    assert builds.loc["b1", "n_jobs"] == 3
    assert builds.loc["b2", "n_jobs"] == 1
    assert builds.loc["b1", "tr_duration"] == 120        # max over the build
    assert builds.loc["b1", "tr_status"] == "failed"
    assert builds.loc["b2", "gh_lang"] == "java"


def test_aggregate_requires_build_id():
    with pytest.raises(KeyError):
        data.aggregate_to_builds(pd.DataFrame({"tr_status": ["passed"]}))

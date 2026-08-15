"""Tests for the commit-time feature extractor (P1-T2).

Three contracts are under test, in the order the task's DoD states them:

* **S2 leakage** — no blocklisted column, and nothing derived from one, may reach
  the feature matrix (R7 / eval_protocol §A1.2). Two *negative* tests are
  mandatory: injecting ``tr_log_status`` and injecting ``tr_duration`` must both
  be caught. The second is the one that matters most for this study: the whole
  RQ2 design collapses if observed duration reaches a decision input.
* **S3 partition** — ``FAMILIES`` is a disjoint partition covering exactly the
  28 features (A1.3).
* **S1 derivation** — each feature computes what ``context/feature_spec.md`` says
  it computes, checked on a hand-built frame whose values are known by hand.
"""

import csv
from pathlib import Path

import pandas as pd
import pytest

from scheduler_core import data, features

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------- #
# Helpers — a build-grain frame with all source columns, filled by hand.
# --------------------------------------------------------------------------- #

def _blank_builds(n: int = 1) -> pd.DataFrame:
    """A build-grain frame carrying every column the extractor reads, as NA."""
    return pd.DataFrame(
        {c: ["NA"] * n for c in features.READ_COLUMNS},
        index=pd.RangeIndex(n),
    )


def _one_build(**values: object) -> pd.DataFrame:
    b = _blank_builds(1)
    for k, v in values.items():
        b.loc[0, k] = v
    return b


# --------------------------------------------------------------------------- #
# S3 — the family partition is a contract (A1.3)
# --------------------------------------------------------------------------- #

def test_families_are_a_disjoint_partition_of_28_features():
    """Six families, disjoint, covering exactly the 28 features (A1.3)."""
    features.assert_families_partition_features()
    assert len(features.FEATURES) == 28
    assert len(set(features.FEATURES)) == 28
    assert set(features.FAMILIES) == {"F1", "F2", "F3", "F4", "F5", "F6"}
    assert sum(len(m) for m in features.FAMILIES.values()) == 28


def test_family_sizes_match_the_spec_table():
    """Counts pinned in feature_spec.md §Families: 7+6+5+5+2+3."""
    assert {f: len(m) for f, m in features.FAMILIES.items()} == {
        "F1": 7, "F2": 6, "F3": 5, "F4": 5, "F5": 2, "F6": 3
    }


def test_duration_control_is_not_a_family_member():
    """`d̂` lives in every ablation arm and is not an SE family (A1.3)."""
    all_members = {m for members in features.FAMILIES.values() for m in members}
    assert "d_hat" not in all_members
    assert not any("duration" in m for m in all_members)


def test_every_feature_declares_its_sources():
    """FEATURE_SOURCES must cover FEATURES exactly — the leakage check reads it."""
    assert set(features.FEATURE_SOURCES) == set(features.FEATURES)
    for name, cols in features.FEATURE_SOURCES.items():
        assert cols, f"{name} declares no source column"
        for col in cols:
            assert col in data.EXPECTED_HEADER, (
                f"{name} names {col!r}, which is not in the real CSV header (R2)"
            )


# --------------------------------------------------------------------------- #
# S2 — leakage blocklist, enforced programmatically
# --------------------------------------------------------------------------- #

def test_blocklist_covers_the_spec_list():
    """Every column named in feature_spec.md §Leakage blocklist is blocked."""
    for col in (
        "tr_status", "tr_log_status", "tr_log_bool_tests_ran",
        "tr_log_bool_tests_failed", "tr_log_num_tests_ok",
        "tr_log_num_tests_failed", "tr_log_num_tests_run",
        "tr_log_num_tests_skipped", "tr_log_num_test_suites_run",
        "tr_log_num_test_suites_ok", "tr_log_num_test_suites_failed",
        "tr_log_tests_failed", "tr_log_testduration", "tr_log_buildduration",
        "tr_duration", "tr_prev_build",
    ):
        assert features.is_blocklisted(col), f"{col} must be blocklisted"


def test_clean_configuration_passes():
    """The shipped FEATURE_SOURCES must not trip the assertion."""
    features.assert_no_leakage()


def test_negative_injecting_tr_log_status_is_caught():
    """NEGATIVE TEST (DoD): a feature derived from `tr_log_status` is rejected."""
    poisoned = dict(features.FEATURE_SOURCES)
    poisoned["sneaky_outcome"] = ("tr_log_status",)
    with pytest.raises(features.LeakageError) as exc:
        features.assert_no_leakage(sources=poisoned)
    assert "tr_log_status" in str(exc.value)


def test_negative_injecting_tr_duration_is_caught():
    """NEGATIVE TEST (DoD, duration-specific): the current build's observed
    duration may never source a feature (§A1.2 role rule / DL-012)."""
    poisoned = dict(features.FEATURE_SOURCES)
    poisoned["src_churn"] = ("git_diff_src_churn", "tr_duration")
    with pytest.raises(features.LeakageError) as exc:
        features.assert_no_leakage(sources=poisoned)
    assert "tr_duration" in str(exc.value)
    assert "src_churn" in str(exc.value)


def test_negative_blocklisted_column_riding_on_the_matrix_is_caught():
    """A raw outcome column present among the matrix columns is rejected."""
    with pytest.raises(features.LeakageError) as exc:
        features.assert_no_leakage(columns=list(features.FEATURES) + ["tr_duration"])
    assert "tr_duration" in str(exc.value)


def test_unknown_tr_log_column_is_blocked_by_prefix():
    """The `tr_log_*` prefix rule blocks post-run fields we never enumerated."""
    assert features.is_blocklisted("tr_log_some_future_field")


def test_real_matrix_contains_no_blocklisted_column():
    """The extractor's own output passes the matrix-column check."""
    m = features.build_feature_matrix(_blank_builds(3))
    assert list(m.columns)[-28:] == list(features.FEATURES)
    for col in m.columns:
        assert not features.is_blocklisted(col)
    features.assert_no_leakage(columns=m.columns)


def test_duration_never_travels_with_the_features():
    """`aggregate_builds_for_features` must not carry tr_duration even if asked
    to aggregate a frame that has it — the read path does not select it."""
    assert "tr_duration" not in features.READ_COLUMNS
    assert "tr_duration" not in features.SOURCE_COLUMNS


# --------------------------------------------------------------------------- #
# S1 — each feature computes what the spec says it computes
# --------------------------------------------------------------------------- #

def test_direct_and_derived_features_on_a_known_row():
    """Hand-computed expectations for every derived feature (feature_spec table)."""
    b = _one_build(
        git_diff_src_churn="10", git_diff_test_churn="4",
        gh_diff_files_added="2", gh_diff_files_deleted="1",
        gh_diff_files_modified="3", gh_diff_tests_added="5",
        gh_diff_tests_deleted="0", gh_diff_src_files="3",
        gh_diff_doc_files="1", gh_diff_other_files="2",
        git_num_all_built_commits="7", gh_num_commits_on_files_touched="11",
        gh_sloc="1000", gh_test_lines_per_kloc="120.5",
        gh_test_cases_per_kloc="8.25", gh_asserts_cases_per_kloc="15.0",
        gh_team_size="6", gh_by_core_team_member="true", gh_repo_age="365.5",
        gh_repo_num_commits="4200", gh_description_complexity="12",
        gh_is_pr="false", gh_lang="ruby",
        gh_build_started_at="2015-03-04 13:45:00",   # Wednesday, 13:00 UTC
    )
    m = features.build_feature_matrix(b, with_keys=False)
    r = m.iloc[0]

    assert r["src_churn"] == 10 and r["test_churn"] == 4
    assert r["files_added"] == 2 and r["files_deleted"] == 1
    assert r["files_modified"] == 3
    assert r["files_total"] == 6                      # 2 + 1 + 3
    assert r["num_commits"] == 7                      # git_num_all_built_commits
    assert r["tests_added"] == 5 and r["tests_deleted"] == 0
    assert r["src_files"] == 3 and r["doc_files"] == 1 and r["other_files"] == 2
    assert r["is_docs_only"] == 0                     # src_files > 0
    assert r["commits_on_files_touched"] == 11
    assert r["sloc"] == 1000
    assert r["test_lines_per_kloc"] == 120.5
    assert r["test_cases_per_kloc"] == 8.25
    assert r["asserts_per_kloc"] == 15.0
    assert r["team_size"] == 6
    assert r["by_core_member"] == 1                   # "true" -> 1
    assert r["repo_age"] == 365.5
    assert r["repo_num_commits"] == 4200
    assert r["description_complexity"] == 12
    assert r["is_pr"] == 0                            # "false" -> 0
    assert r["lang"] == "ruby"
    assert r["hour_of_day"] == 13
    assert r["day_of_week"] == 2                      # Monday=0 -> Wednesday=2
    assert r["test_density_ratio"] == pytest.approx(4 / 11)   # 4 / (10 + 1)


def test_is_docs_only_true_case():
    """docs-only = doc_files > 0 AND src_files == 0 (spec #12)."""
    b = _one_build(gh_diff_src_files="0", gh_diff_doc_files="3",
                   gh_diff_other_files="0")
    assert features.build_feature_matrix(b, with_keys=False).iloc[0]["is_docs_only"] == 1


def test_is_docs_only_is_null_when_inputs_are_missing():
    """Missing inputs propagate as NaN rather than reading as 'not docs-only'."""
    b = _one_build(gh_diff_src_files="NA", gh_diff_doc_files="3")
    assert pd.isna(features.build_feature_matrix(b, with_keys=False).iloc[0]["is_docs_only"])


def test_description_complexity_missing_becomes_zero_for_non_pr():
    """Spec #23: the PR-only field is 0 when absent (79% of builds are pushes)."""
    b = _one_build(gh_is_pr="false", gh_description_complexity="NA")
    assert features.build_feature_matrix(b, with_keys=False).iloc[0]["description_complexity"] == 0


def test_test_density_ratio_handles_zero_src_churn():
    """The +1 denominator makes a pure-test change finite, not infinite."""
    b = _one_build(git_diff_src_churn="0", git_diff_test_churn="9")
    assert features.build_feature_matrix(b, with_keys=False).iloc[0]["test_density_ratio"] == 9.0


def test_unparseable_numeric_becomes_nan_not_zero():
    """A junk cell must surface as missing, never as a silent 0 (R1)."""
    b = _one_build(gh_sloc="not-a-number")
    assert pd.isna(features.build_feature_matrix(b, with_keys=False).iloc[0]["sloc"])


def test_keys_are_carried_but_are_not_features():
    """Identity + arrival time ride along for splits/simulation, outside FEATURES."""
    b = _one_build(tr_build_id="123", gh_project_name="a/b",
                   gh_build_started_at="2015-03-04 13:45:00")
    m = features.build_feature_matrix(b, with_keys=True)
    assert list(m.columns[:3]) == list(features.KEY_COLUMNS)
    assert m.iloc[0]["gh_project_name"] == "a/b"
    for key in features.KEY_COLUMNS:
        assert key not in features.FEATURES


def test_missing_source_column_is_a_hard_error():
    """Dropping a source column fails loudly instead of yielding a short matrix."""
    b = _blank_builds(1).drop(columns=["gh_sloc"])
    with pytest.raises(KeyError):
        features.build_feature_matrix(b)


# --------------------------------------------------------------------------- #
# Label — separate from the features by construction
# --------------------------------------------------------------------------- #

def test_label_maps_statuses_per_dl009():
    b = pd.DataFrame({"tr_status": ["passed", "failed", "errored", "canceled", "NA"]})
    y = features.label_from_status(b)
    assert list(y[:3]) == [0.0, 1.0, 1.0]
    assert pd.isna(y.iloc[3]) and pd.isna(y.iloc[4])
    assert y.name == features.LABEL_COLUMN
    assert features.LABEL_COLUMN not in features.FEATURES


# --------------------------------------------------------------------------- #
# Build-grain aggregation + the funnel
# --------------------------------------------------------------------------- #

def test_jobs_aggregate_to_one_row_per_build():
    """DL-009: commit-time columns are build-level; jobs collapse to one row."""
    jobs = pd.concat([_one_build(tr_build_id="1", gh_sloc="500"),
                      _one_build(tr_build_id="1", gh_sloc="500"),
                      _one_build(tr_build_id="2", gh_sloc="900")],
                     ignore_index=True)
    builds = features.aggregate_builds_for_features(jobs)
    assert len(builds) == 2
    assert builds.loc["1", "gh_sloc"] == "500"
    assert builds.loc["2", "gh_sloc"] == "900"


def test_load_builds_applies_the_analytic_funnel(tmp_path):
    """canceled / unlabelled / unparseable-timestamp builds are excluded."""
    p = tmp_path / "mini.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(data.EXPECTED_HEADER)
        idx = {c: i for i, c in enumerate(data.EXPECTED_HEADER)}

        def row(build_id, status, started):
            r = ["NA"] * len(data.EXPECTED_HEADER)
            r[idx["tr_build_id"]] = build_id
            r[idx["tr_status"]] = status
            r[idx["gh_build_started_at"]] = started
            r[idx["gh_project_name"]] = "a/b"
            return r

        w.writerow(row("1", "passed", "2015-01-01 00:00:00"))
        w.writerow(row("2", "failed", "2015-01-02 00:00:00"))
        w.writerow(row("3", "canceled", "2015-01-03 00:00:00"))   # excluded
        w.writerow(row("4", "passed", "not-a-date"))              # excluded
        w.writerow(row("5", "NA", "2015-01-05 00:00:00"))         # excluded

    builds = features.load_builds(p, chunksize=2)
    assert sorted(builds["tr_build_id"]) == ["1", "2"]


def test_extract_end_to_end_on_a_mini_file(tmp_path):
    """The full path yields exactly FEATURES (+ keys + label) and no leakage."""
    p = tmp_path / "mini.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(data.EXPECTED_HEADER)
        idx = {c: i for i, c in enumerate(data.EXPECTED_HEADER)}
        r = ["NA"] * len(data.EXPECTED_HEADER)
        r[idx["tr_build_id"]] = "1"
        r[idx["tr_status"]] = "failed"
        r[idx["gh_build_started_at"]] = "2015-06-01 09:30:00"
        r[idx["gh_project_name"]] = "a/b"
        r[idx["git_diff_src_churn"]] = "20"
        r[idx["git_diff_test_churn"]] = "5"
        r[idx["tr_duration"]] = "12345"       # present in the file, must not travel
        w.writerow(r)

    m = features.extract(p, chunksize=10)
    assert len(m) == 1
    assert "tr_duration" not in m.columns
    assert m.iloc[0][features.LABEL_COLUMN] == 1.0
    assert m.iloc[0]["src_churn"] == 20
    features.assert_no_leakage(columns=[c for c in m.columns
                                        if c != features.LABEL_COLUMN])


# --------------------------------------------------------------------------- #
# Degeneracy reporting (DL-016)
# --------------------------------------------------------------------------- #

def test_degeneracy_flags_a_constant_feature():
    """A zero-variance column must be reported `constant`, not quietly averaged.

    This is the check that caught `git_diff_test_churn` being empty in the whole
    2017 release (DL-016).
    """
    b = pd.concat([_one_build(git_diff_test_churn="0", gh_sloc=str(100 * i))
                   for i in range(1, 21)], ignore_index=True)
    rep = features.degeneracy_report(features.build_feature_matrix(b, with_keys=False))
    verdict = dict(zip(rep["feature"], rep["verdict"]))
    assert verdict["test_churn"] == "constant"
    assert verdict["test_density_ratio"] == "constant"   # 0 / (src+1) == 0
    assert verdict["sloc"] == "ok"


def test_degeneracy_covers_every_feature_exactly_once():
    rep = features.degeneracy_report(features.build_feature_matrix(_blank_builds(5)))
    assert list(rep["feature"]) == list(features.FEATURES)
    assert set(rep["verdict"]) <= {"constant", "near-constant", "sparse", "ok"}


def test_degeneracy_flags_sparse_but_varying():
    """A column that is 95% zero but genuinely varies is `sparse`, not constant."""
    vals = ["0"] * 95 + [str(i) for i in range(1, 6)]
    b = pd.concat([_one_build(git_diff_src_churn=v) for v in vals], ignore_index=True)
    rep = features.degeneracy_report(features.build_feature_matrix(b, with_keys=False))
    assert dict(zip(rep["feature"], rep["verdict"]))["src_churn"] == "sparse"


# --------------------------------------------------------------------------- #
# Real dataset (DoD: "matrix builds from real rows")
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(
    not data.DEFAULT_DATASET_PATH.exists(),
    reason="real TravisTorrent CSV not present in this environment",
)
def test_matrix_builds_from_real_rows():
    """One real chunk -> a matrix of exactly the 28 features, leakage-clean."""
    chunk = next(data.read_chunks(chunksize=20_000,
                                  usecols=features.READ_COLUMNS))
    builds = features.aggregate_builds_for_features(chunk).reset_index()
    m = features.build_feature_matrix(builds)
    assert len(m) > 0
    assert list(m.columns)[-28:] == list(features.FEATURES)
    features.assert_no_leakage(columns=m.columns)
    # The columns the profile measured as 0% null must be populated here too.
    for name in ("src_churn", "files_added", "sloc", "team_size", "repo_age"):
        assert m[name].notna().mean() > 0.99

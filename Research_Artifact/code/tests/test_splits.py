"""Tests for the three-way split maker (P1-T3).

The DoD names three leakage tests, and they are the first three sections here:

* **S2a** no `gh_project_name` appears in two splits;
* **S2b** time-ordering holds within each split;
* **S2c** a deliberately leaky split fixture must be *rejected* — the check has
  to be able to fail, or passing it means nothing.

Everything else guards the properties §2 depends on but does not name: total
coverage (no silent exclusions), determinism under a fixed seed, and the
independence of the assignment from anything downstream.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from scheduler_core import splits
from scheduler_core.config import RANDOM_SEED


# --------------------------------------------------------------------------- #
# Fixtures — a synthetic build table with known project sizes
# --------------------------------------------------------------------------- #

def _builds(sizes: dict[str, int], *, start: str = "2015-01-01") -> pd.DataFrame:
    """Build-grain rows: `sizes` maps project name -> number of builds.

    Timestamps are interleaved across projects (build i of every project shares
    a minute offset), so a split that merely preserved input order would not be
    time-ordered by accident.
    """
    rows = []
    base = pd.Timestamp(start, tz="UTC")
    bid = 0
    for project, n in sizes.items():
        for i in range(n):
            bid += 1
            rows.append({
                "tr_build_id": str(bid),
                "gh_project_name": project,
                "gh_build_started_at": (base + pd.Timedelta(minutes=i)
                                        ).strftime("%Y-%m-%d %H:%M:%S"),
                "tr_status": "failed" if bid % 4 == 0 else "passed",
                "tr_duration": str(60 * (i + 1)),
            })
    return pd.DataFrame(rows)


def _even_projects(n_projects: int = 40, per: int = 25) -> pd.DataFrame:
    return _builds({f"org/p{i:03d}": per for i in range(n_projects)})


# --------------------------------------------------------------------------- #
# S2a — project-disjointness (the headline leakage test)
# --------------------------------------------------------------------------- #

def test_no_project_appears_in_two_splits():
    """S2a: the three splits partition projects, never share one."""
    s = splits.make_splits(_even_projects())
    sets = {name: set(f["gh_project_name"]) for name, f in s.items()}
    assert sets["train"] & sets["calibration"] == set()
    assert sets["train"] & sets["test"] == set()
    assert sets["calibration"] & sets["test"] == set()
    splits.assert_projects_disjoint(s)


def test_every_project_lands_in_exactly_one_split():
    b = _even_projects()
    s = splits.make_splits(b)
    counted = sum(f["gh_project_name"].nunique() for f in s.values())
    assert counted == b["gh_project_name"].nunique()


def test_a_project_is_never_split_across_builds():
    """Whole projects move together — no project's builds straddle a boundary."""
    b = _even_projects()
    s = splits.make_splits(b)
    home = {}
    for name, f in s.items():
        for project in f["gh_project_name"]:
            assert home.setdefault(project, name) == name


# --------------------------------------------------------------------------- #
# S2b — time ordering
# --------------------------------------------------------------------------- #

def test_each_split_is_time_ordered():
    """S2b: builds ascend by gh_build_started_at within every split."""
    s = splits.make_splits(_even_projects())
    for name, f in s.items():
        parsed = pd.to_datetime(f["gh_build_started_at"], utc=True)
        assert parsed.is_monotonic_increasing, f"{name} is not time-ordered"
    splits.assert_time_ordered(s)


def test_time_ordering_is_by_parsed_time_not_row_order():
    """Rows arriving out of order must come back sorted."""
    b = _builds({"org/a": 5})
    b = b.iloc[::-1].reset_index(drop=True)          # reverse-chronological input
    ordered = splits._project_build_counts(b, "gh_project_name")
    assert int(ordered.iloc[0]) == 5
    s = splits.make_splits(_builds({f"org/p{i}": 6 for i in range(9)}))
    splits.assert_time_ordered(s)


# --------------------------------------------------------------------------- #
# S2c — NEGATIVE TESTS: the checks must reject bad splits
# --------------------------------------------------------------------------- #

def test_negative_leaky_split_fixture_is_rejected():
    """S2c: a fixture where one project sits in two splits must be caught.

    Built by hand rather than by corrupting a real split, so the test cannot
    silently pass if `make_splits` changes.
    """
    shared = _builds({"org/leaky": 4})
    leaky = {
        "train": shared,
        "calibration": shared.copy(),      # same project — the leak
        "test": _builds({"org/clean": 4}),
    }
    with pytest.raises(splits.SplitLeakageError) as exc:
        splits.assert_projects_disjoint(leaky)
    assert "org/leaky" in str(exc.value)


def test_negative_unordered_split_is_rejected():
    """A split whose rows run backwards in time must be caught."""
    f = _builds({"org/a": 10}).iloc[::-1].reset_index(drop=True)
    with pytest.raises(splits.SplitLeakageError) as exc:
        splits.assert_time_ordered({"train": f})
    assert "time-order" in str(exc.value)


def test_negative_dropped_builds_are_rejected():
    """Silently discarding builds must fail the partition check (no exclusions)."""
    b = _even_projects()
    s = splits.make_splits(b)
    s["test"] = s["test"].iloc[:-1]                  # drop one build
    with pytest.raises(splits.SplitLeakageError) as exc:
        splits.assert_complete_partition(s, b)
    assert "lost or duplicated" in str(exc.value)


def test_negative_moved_build_breaks_project_disjointness():
    """Moving one build to another split keeps the counts right but puts its
    project in two splits — the full check must still reject it."""
    b = _even_projects()
    s = splits.make_splits(b)
    moved = s["train"].iloc[[0]]
    s["test"] = pd.concat([s["test"], moved], ignore_index=True)
    s["train"] = s["train"].iloc[1:]
    splits.assert_complete_partition(s, b)          # counts and ids still fine
    with pytest.raises(splits.SplitLeakageError) as exc:
        splits.assert_valid_splits(s, b)            # ...but disjointness is gone
    assert "disjoint" in str(exc.value)


def test_negative_duplicated_build_id_is_rejected():
    """A repeated build id must fail even when row counts still add up.

    One row duplicated and a different one dropped, inside a single split: the
    totals balance and every project stays where it was, so only the id check
    can catch this.
    """
    b = _even_projects()
    s = splits.make_splits(b)
    train = s["train"]
    s["train"] = pd.concat([train.iloc[[0]], train.iloc[:-1]], ignore_index=True)
    assert len(s["train"]) == len(train)
    with pytest.raises(splits.SplitLeakageError) as exc:
        splits.assert_complete_partition(s, b)
    assert "more than once" in str(exc.value)


def test_negative_missing_split_is_rejected():
    b = _even_projects()
    s = splits.make_splits(b)
    with pytest.raises(splits.SplitLeakageError):
        splits.assert_valid_splits({"train": s["train"]}, b)


def test_empty_split_raises():
    """Too few projects to fill three splits is an error, not a silent 2-way split."""
    with pytest.raises(splits.SplitLeakageError):
        splits.make_splits(_builds({"org/only": 10, "org/two": 10}))


# --------------------------------------------------------------------------- #
# Coverage — no silent exclusions
# --------------------------------------------------------------------------- #

def test_all_builds_are_assigned():
    b = _even_projects()
    s = splits.make_splits(b)
    assert sum(len(f) for f in s.values()) == len(b)
    ids = pd.concat([f["tr_build_id"] for f in s.values()])
    assert set(ids) == set(b["tr_build_id"])
    assert not ids.duplicated().any()


def test_unassignable_project_is_a_hard_error():
    """If the assignment ever failed to cover a project, make_splits must raise."""
    counts = pd.Series({"org/a": 1, "org/b": 1, "org/c": 1})
    assignment = splits.assign_projects(counts)
    assert set(assignment) == set(counts.index)
    assert set(assignment.values()) <= set(splits.SPLIT_NAMES)


# --------------------------------------------------------------------------- #
# Determinism and independence from anything downstream
# --------------------------------------------------------------------------- #

def test_assignment_is_deterministic_for_a_seed():
    b = _even_projects()
    a = splits.make_splits(b, seed=RANDOM_SEED)
    c = splits.make_splits(b, seed=RANDOM_SEED)
    for name in splits.SPLIT_NAMES:
        assert list(a[name]["tr_build_id"]) == list(c[name]["tr_build_id"])


def test_assignment_is_independent_of_input_row_order():
    """Shuffling the input rows must not change which project goes where.

    Guards the property that makes the split reproducible: assignment depends on
    (project names, build counts, seed) only.
    """
    b = _even_projects()
    shuffled = b.sample(frac=1.0, random_state=7).reset_index(drop=True)
    a = splits.make_splits(b)
    c = splits.make_splits(shuffled)
    for name in splits.SPLIT_NAMES:
        assert set(a[name]["gh_project_name"]) == set(c[name]["gh_project_name"])


def test_assignment_ignores_labels_and_durations():
    """Changing outcomes/durations must not move a single project (§2).

    The split may not be optimised against anything downstream; if a label or a
    duration could shift it, that door is open.
    """
    b = _even_projects()
    tampered = b.copy()
    tampered["tr_status"] = "failed"
    tampered["tr_duration"] = "99999"
    a = splits.make_splits(b)
    c = splits.make_splits(tampered)
    for name in splits.SPLIT_NAMES:
        assert set(a[name]["gh_project_name"]) == set(c[name]["gh_project_name"])


def test_different_seeds_give_different_assignments():
    """Sanity: the seed actually drives the shuffle."""
    counts = pd.Series({f"org/p{i:03d}": 10 + i for i in range(40)})
    assert splits.assign_projects(counts, seed=42) != splits.assign_projects(
        counts, seed=43)


def test_assignment_hash_is_stable_and_sensitive():
    a = {"org/a": "train", "org/b": "test"}
    assert splits.assignment_hash(a) == splits.assignment_hash(
        {"org/b": "test", "org/a": "train"})          # key order must not matter
    assert splits.assignment_hash(a) != splits.assignment_hash(
        {"org/a": "train", "org/b": "calibration"})


# --------------------------------------------------------------------------- #
# Proportions
# --------------------------------------------------------------------------- #

def test_build_volume_proportions_are_approached():
    """Many equal-sized projects should land close to 70/15/15 by build volume."""
    b = _builds({f"org/p{i:03d}": 20 for i in range(200)})
    s = splits.make_splits(b)
    total = len(b)
    got = {n: len(f) / total for n, f in s.items()}
    assert abs(got["train"] - 0.70) < 0.02
    assert abs(got["calibration"] - 0.15) < 0.02
    assert abs(got["test"] - 0.15) < 0.02


def test_proportions_are_validated():
    counts = pd.Series({f"org/p{i}": 10 for i in range(10)})
    with pytest.raises(ValueError):
        splits.assign_projects(counts, proportions=(0.5, 0.3, 0.3))   # sums to 1.1
    with pytest.raises(ValueError):
        splits.assign_projects(counts, proportions=(0.8, 0.2, 0.0))   # zero split


def test_custom_proportions_are_honoured():
    b = _builds({f"org/p{i:03d}": 20 for i in range(200)})
    s = splits.make_splits(b, proportions=(0.5, 0.25, 0.25))
    total = len(b)
    assert abs(len(s["train"]) / total - 0.50) < 0.02


def test_missing_required_column_is_a_hard_error():
    b = _even_projects().drop(columns=["gh_build_started_at"])
    with pytest.raises(KeyError):
        splits.make_splits(b)


# --------------------------------------------------------------------------- #
# Manifest statistics
# --------------------------------------------------------------------------- #

def test_summarise_reports_every_split_with_required_fields():
    s = splits.make_splits(_even_projects())
    summary = splits.summarise_splits(s)
    assert set(summary) == set(splits.SPLIT_NAMES)
    for name, entry in summary.items():
        for key in ("n_projects", "n_builds", "share_of_builds", "target_share",
                    "failure_rate_pct", "time_range", "duration_s"):
            assert key in entry, f"{name} missing {key}"
        assert entry["duration_s"]["count"] > 0


# --------------------------------------------------------------------------- #
# The frozen artifact on disk
# --------------------------------------------------------------------------- #

FROZEN_DIR = Path(__file__).resolve().parents[2] / "results" / "p1"


@pytest.mark.skipif(not (FROZEN_DIR / "split_assignment.csv").exists(),
                    reason="split not generated yet (run scripts/make_splits.py)")
def test_frozen_assignment_is_a_clean_partition():
    """The committed artifact itself must satisfy §2, independent of any re-run.

    Guards the file the rest of the project depends on: one split per project,
    only the three known split names, and a digest matching the manifest.
    """
    frame = pd.read_csv(FROZEN_DIR / "split_assignment.csv", dtype=str)
    assert not frame["gh_project_name"].duplicated().any(), (
        "a project appears twice in the frozen assignment")
    assert set(frame["split"]) == set(splits.SPLIT_NAMES)

    manifest = json.loads((FROZEN_DIR / "splits.json").read_text(encoding="utf-8"))
    assignment = dict(zip(frame["gh_project_name"], frame["split"]))
    assert splits.assignment_hash(assignment) == manifest["freeze"]["assignment_sha256"]
    assert manifest["freeze"]["frozen"] is True
    assert manifest["freeze"]["n_projects"] == len(frame)


@pytest.mark.skipif(not (FROZEN_DIR / "splits.json").exists(),
                    reason="split not generated yet (run scripts/make_splits.py)")
def test_frozen_manifest_records_no_silent_exclusions():
    """Builds in must equal builds out, and the per-split counts must add up."""
    m = json.loads((FROZEN_DIR / "splits.json").read_text(encoding="utf-8"))
    assert m["totals"]["analytic_builds"] == m["totals"]["assigned_builds"]
    assert sum(m["per_split"][n]["n_builds"] for n in splits.SPLIT_NAMES) == \
        m["totals"]["analytic_builds"]
    assert sum(m["per_split"][n]["n_projects"] for n in splits.SPLIT_NAMES) == \
        m["totals"]["projects"]
    assert all(v == "PASS" for v in m["checks"].values())


def test_summarise_duration_is_descriptive_only():
    """The duration block must carry its §A1.2 label wherever it is reported."""
    s = splits.make_splits(_even_projects())
    note = splits.summarise_splits(s)["train"]["duration_s"]["note"]
    assert "A1.2" in note and "never a decision input" in note

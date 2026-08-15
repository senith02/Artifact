"""Project-disjoint, time-ordered three-way split maker (P1-T3).

Implements `results/p0/eval_protocol.md` **§2** (refined by DL-006) and the
signature frozen there in §10. The split is the load-bearing piece of the
study's leakage discipline (invariant 4, rule R7): every RQ1/RQ2 claim rests on
the model never having seen the project it is evaluated on.

Four properties are enforced in code rather than trusted:

1. **Project-disjoint** — no ``gh_project_name`` appears in two splits. A whole
   project goes to exactly one split; builds are never split within a project.
2. **Total coverage, no silent exclusions** — every input build lands in exactly
   one split. The row counts must add up, and the union of the three project
   sets must equal the input's project set.
3. **Time-ordered** — within each split, builds ascend by
   ``gh_build_started_at``. No random shuffle of rows, no random k-fold, ever.
4. **Deterministic** — the project→split assignment is a pure function of the
   project names, their build counts, ``proportions`` and ``seed``.

Nothing downstream may feed back into the split: assignment reads only project
identity and build volume, never a label, a duration, a feature, or any model
result (§2 use-discipline; the split is fitted before anything is).
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from scheduler_core.config import RANDOM_SEED

#: The three splits, in the canonical order used for proportions and tie-breaks.
SPLIT_NAMES: tuple[str, str, str] = ("train", "calibration", "test")

#: §2 target proportions, measured by **build volume** (not project count).
DEFAULT_PROPORTIONS: tuple[float, float, float] = (0.70, 0.15, 0.15)


class SplitLeakageError(AssertionError):
    """Raised when a split set violates §2: a project spanning two splits, a
    build lost or duplicated, or a split that is not time-ordered."""


def _project_build_counts(builds: pd.DataFrame, project_col: str) -> pd.Series:
    """Builds per project, indexed by project name in **sorted** order.

    Sorting first makes the input to the shuffle independent of row order, so
    the assignment depends only on (names, counts, seed) — not on how the CSV
    happened to be read.
    """
    counts = builds.groupby(project_col, sort=False).size()
    return counts.sort_index()


def assign_projects(
    project_counts: "pd.Series",
    *,
    proportions: Sequence[float] = DEFAULT_PROPORTIONS,
    seed: int = RANDOM_SEED,
) -> dict[str, str]:
    """Assign whole projects to splits, greedily, to approach build-volume targets.

    The §2 rule spelled out exactly as implemented, because "greedily" admits
    more than one reading and the choice must be reproducible:

    1. Project names are sorted, then permuted by
       ``numpy.random.default_rng(seed)`` (PCG64) — the shuffle §2 specifies.
    2. Each split ``s`` gets a target of ``proportions[s] × total_builds``.
    3. Projects are taken in shuffled order; each goes to the split with the
       largest remaining **deficit** (``target − assigned so far``). Ties break
       toward the earlier split in :data:`SPLIT_NAMES`, so the rule is total.

    Volume targets are approached, never guaranteed: whole projects are
    indivisible, so a single large project can overshoot its split. The achieved
    proportions are therefore *reported* (see :func:`summarise_splits`) rather
    than asserted against a tolerance the protocol does not fix.

    Returns ``{project_name: split_name}`` covering every project exactly once.
    """
    if len(proportions) != 3:
        raise ValueError(f"expected 3 proportions, got {len(proportions)}")
    if any(p <= 0 for p in proportions):
        raise ValueError(f"proportions must all be positive: {proportions}")
    if not np.isclose(sum(proportions), 1.0):
        raise ValueError(f"proportions must sum to 1.0, got {sum(proportions)}")
    if project_counts.empty:
        raise ValueError("no projects to assign")

    total = int(project_counts.sum())
    targets = {s: p * total for s, p in zip(SPLIT_NAMES, proportions)}
    assigned = {s: 0 for s in SPLIT_NAMES}

    names = list(project_counts.index)
    order = np.random.default_rng(seed).permutation(len(names))

    out: dict[str, str] = {}
    for i in order:
        name = names[int(i)]
        # max deficit; ties -> earliest split in SPLIT_NAMES (index breaks ties)
        chosen = max(
            SPLIT_NAMES,
            key=lambda s: (targets[s] - assigned[s], -SPLIT_NAMES.index(s)),
        )
        out[name] = chosen
        assigned[chosen] += int(project_counts.loc[name])
    return out


def make_splits(
    builds: pd.DataFrame,
    *,
    project_col: str = "gh_project_name",
    time_col: str = "gh_build_started_at",
    proportions: tuple[float, float, float] = DEFAULT_PROPORTIONS,
    seed: int = RANDOM_SEED,
) -> dict[str, pd.DataFrame]:
    """Project-disjoint, time-ordered train/calibration/test split (§2, DL-006).

    Partitions ``builds`` by ``project_col`` so no project appears in two splits;
    assigns projects (shuffled by ``seed``) greedily to approach ``proportions``
    measured by build volume; orders each split ascending by ``time_col``.

    Returns
    -------
    {"train": df, "calibration": df, "test": df}
        Disjoint by project, time-ordered within each split. The caller writes
        the manifest (project lists + per-split row counts + failure rates) to
        results/p1/splits.json. Raises if any project would span two splits or
        if a split is empty.
    """
    for col in (project_col, time_col):
        if col not in builds.columns:
            raise KeyError(f"builds is missing required column {col!r}")

    counts = _project_build_counts(builds, project_col)
    assignment = assign_projects(counts, proportions=proportions, seed=seed)

    split_of = builds[project_col].map(assignment)
    if split_of.isna().any():
        unassigned = sorted(set(builds.loc[split_of.isna(), project_col]))
        raise SplitLeakageError(
            f"{len(unassigned)} project(s) were not assigned to any split — "
            f"silent exclusion is forbidden (§2): {unassigned[:5]}"
        )

    # Sort key is the parsed timestamp, not the raw string, so ordering is by
    # real time. mergesort is stable, so equal timestamps keep input order and
    # the result stays deterministic.
    parsed = pd.to_datetime(builds[time_col], errors="coerce", utc=True)

    splits: dict[str, pd.DataFrame] = {}
    for name in SPLIT_NAMES:
        rows = builds.loc[split_of == name]
        if rows.empty:
            raise SplitLeakageError(
                f"split {name!r} is empty — cannot proceed (§2 requires all three)"
            )
        order = parsed.loc[rows.index].to_numpy().argsort(kind="mergesort")
        splits[name] = rows.iloc[order].reset_index(drop=True)

    assert_valid_splits(splits, original=builds, project_col=project_col,
                        time_col=time_col)
    return splits


# --------------------------------------------------------------------------- #
# Validation — each check is separately callable so tests can target one at a time
# --------------------------------------------------------------------------- #

def assert_projects_disjoint(
    splits: Mapping[str, pd.DataFrame],
    *,
    project_col: str = "gh_project_name",
) -> None:
    """Fail if any project appears in more than one split (§2, test S2a)."""
    seen: dict[str, str] = {}
    offences: list[str] = []
    for name, frame in splits.items():
        for project in pd.unique(frame[project_col]):
            if project in seen and seen[project] != name:
                offences.append(f"{project!r} in both {seen[project]!r} and {name!r}")
            else:
                seen[project] = name
    if offences:
        raise SplitLeakageError(
            "project-disjointness violated (§2 / invariant 4):\n  "
            + "\n  ".join(sorted(offences)[:20])
        )


def assert_time_ordered(
    splits: Mapping[str, pd.DataFrame],
    *,
    time_col: str = "gh_build_started_at",
) -> None:
    """Fail if any split is not ascending in ``time_col`` (§2, test S2b)."""
    offences: list[str] = []
    for name, frame in splits.items():
        parsed = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
        if not parsed.is_monotonic_increasing:
            bad = int((parsed.diff() < pd.Timedelta(0)).sum())
            offences.append(f"{name!r} is not time-ordered ({bad} backward step(s))")
    if offences:
        raise SplitLeakageError(
            "time-ordering violated (§2 / invariant 4):\n  " + "\n  ".join(offences)
        )


def assert_complete_partition(
    splits: Mapping[str, pd.DataFrame],
    original: pd.DataFrame,
    *,
    project_col: str = "gh_project_name",
    id_col: str = "tr_build_id",
) -> None:
    """Fail if any build or project was dropped, duplicated, or invented.

    This is the "no silent exclusions" check: the splits must be a *partition*
    of the analytic set, not merely a disjoint sample of it.
    """
    total = sum(len(f) for f in splits.values())
    if total != len(original):
        raise SplitLeakageError(
            f"row count changed: splits hold {total:,} builds, input had "
            f"{len(original):,} — {abs(total - len(original)):,} build(s) "
            "lost or duplicated (§2 forbids silent exclusion)"
        )
    got_projects = set().union(*(set(f[project_col]) for f in splits.values()))
    want_projects = set(original[project_col])
    if got_projects != want_projects:
        missing = sorted(want_projects - got_projects)
        extra = sorted(got_projects - want_projects)
        raise SplitLeakageError(
            f"project set changed: {len(missing)} missing, {len(extra)} unexpected"
        )
    if id_col in original.columns:
        ids = pd.concat([f[id_col] for f in splits.values()], ignore_index=True)
        if ids.duplicated().any():
            n = int(ids.duplicated().sum())
            raise SplitLeakageError(
                f"{n:,} build id(s) appear more than once across the splits"
            )


def assert_valid_splits(
    splits: Mapping[str, pd.DataFrame],
    original: pd.DataFrame,
    *,
    project_col: str = "gh_project_name",
    time_col: str = "gh_build_started_at",
) -> None:
    """Run every §2 structural check. Called by :func:`make_splits` on its output."""
    if set(splits) != set(SPLIT_NAMES):
        raise SplitLeakageError(
            f"expected splits {SPLIT_NAMES}, got {tuple(sorted(splits))}"
        )
    assert_projects_disjoint(splits, project_col=project_col)
    assert_time_ordered(splits, time_col=time_col)
    assert_complete_partition(splits, original, project_col=project_col)


# --------------------------------------------------------------------------- #
# Manifest support
# --------------------------------------------------------------------------- #

def assignment_hash(assignment: Mapping[str, str]) -> str:
    """Stable SHA-256 over the project→split mapping — the freeze fingerprint.

    Any change to which project sits in which split changes this digest, so a
    later run can prove the split it used is the frozen one (§2: test is opened
    exactly once, against a split that was fixed beforehand).
    """
    payload = json.dumps(dict(sorted(assignment.items())), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarise_splits(
    splits: Mapping[str, pd.DataFrame],
    *,
    project_col: str = "gh_project_name",
    time_col: str = "gh_build_started_at",
    status_col: str = "tr_status",
    duration_col: str | None = "tr_duration",
    proportions: Sequence[float] = DEFAULT_PROPORTIONS,
) -> dict:
    """Per-split statistics for the manifest.

    ``duration_col`` is read **for description only** — a manifest is reporting,
    which is role 1 of eval_protocol §A1.2 (accounting). No value computed here
    reaches a feature, a model, or ``decide()``; the split itself is formed
    without ever consulting it.
    """
    from scheduler_core import data  # local import: keeps splits.py import-light

    total = sum(len(f) for f in splits.values())
    out: dict[str, dict] = {}
    for name, target in zip(SPLIT_NAMES, proportions):
        frame = splits[name]
        n = len(frame)
        entry: dict[str, object] = {
            "n_projects": int(frame[project_col].nunique()),
            "n_builds": n,
            "share_of_builds": round(n / total, 6) if total else None,
            "target_share": target,
            "share_deviation_pp": (round(100 * (n / total - target), 4)
                                   if total else None),
        }
        if status_col in frame.columns:
            cls = frame[status_col].map(data.classify_status)
            n_fail = int((cls == "failure").sum())
            entry["failures"] = n_fail
            entry["passes"] = int((cls == "pass").sum())
            entry["failure_rate_pct"] = round(100 * n_fail / n, 4) if n else None
        parsed = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
        entry["time_range"] = {
            "first_build": None if parsed.empty else str(parsed.min()),
            "last_build": None if parsed.empty else str(parsed.max()),
        }
        if duration_col and duration_col in frame.columns:
            v = pd.to_numeric(frame[duration_col], errors="coerce").dropna()
            entry["duration_s"] = {
                "note": "descriptive only — eval_protocol §A1.2 role 1 "
                        "(accounting); never a decision input",
                "count": int(len(v)),
                "missing": int(n - len(v)),
                "min": None if v.empty else float(v.min()),
                "p25": None if v.empty else float(np.percentile(v, 25)),
                "p50": None if v.empty else float(np.percentile(v, 50)),
                "p75": None if v.empty else float(np.percentile(v, 75)),
                "p95": None if v.empty else float(np.percentile(v, 95)),
                "max": None if v.empty else float(v.max()),
                "mean": None if v.empty else round(float(v.mean()), 2),
            }
        out[name] = entry
    return out

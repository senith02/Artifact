"""Stage 1 — the deterministic eligibility gate (spec §3.4, DL-020).

Stage 1 answers one question: **is this build deferrable at all?** It is
rule-based, deterministic and never machine-learned — that separation is frozen
invariant 1 ("risk ≠ urgency"). The ML score never reaches this module; it
operates only *inside* the set Stage 1 has already called deferrable.

⚠ **What this gate is (read before using any number it produces).**
Spec §3.4 defines its classes by build **trigger type**. TravisTorrent records
no trigger type. It records `gh_is_pr` and a free-text `git_branch`, and nothing
else bearing on urgency. This module is therefore an **experimental
approximation of deferability, not a measurement of it** — fixed in **DL-020**,
which is the entry to read before interpreting anything downstream. In
particular:

* two of §3.4's six classes — **manually-triggered** and **scheduled/nightly**
  builds — have no marker in the data and are **not approximated at all**. The
  deferrable set this gate produces consists entirely of §3.4 class (f),
  "non-blocking pushes to non-protected branches" (DL-020 §3);
* the approximation's error rate is **unmeasurable in this corpus**: there is no
  ground-truth deferability, developer-urgency or business-priority label in
  TravisTorrent to score it against;
* `validate_invariants.py` passing proves the gate and its consumers **agree**,
  not that the gate is **right** (DL-020 §6).

Nothing here may be reported as evidence about which builds are genuinely safe
to delay. The output is called `eligible` / deferrable-by-rule, never "safe to
defer" and never "non-urgent" (DL-020 §7).

**Fail closed.** Any input the gate cannot interpret — missing `gh_is_pr`, blank
or absent `git_branch`, an unrecognised boolean spelling — yields
**non-deferrable**. The error is deliberately one-sided: the gate may run a
build that could have waited; it must never defer a build it does not
understand (DL-020 §2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

import pandas as pd

#: TravisTorrent's missing-value spellings, mirroring `data.NA_TOKENS` plus the
#: pandas-null case that reaches this module from an already-parsed frame.
_MISSING_TOKENS: frozenset[str] = frozenset({"", "na", "nan", "none", "null"})

#: `gh_is_pr` spellings accepted as true / false. Anything else is *unparseable*
#: and fails closed — it is not silently read as false.
_TRUE_TOKENS: frozenset[str] = frozenset({"true", "t", "yes", "y", "1", "1.0"})
_FALSE_TOKENS: frozenset[str] = frozenset({"false", "f", "no", "n", "0", "0.0"})


@dataclass(frozen=True)
class ProtectedPattern:
    """One row of the frozen protected/release pattern table.

    Attributes
    ----------
    name: stable identifier, used in `reason` strings and in results files.
    pattern: case-insensitive regex, matched against the **whole** branch name.
    spec_class: the §3.4 non-deferrable class this row approximates.
    evidence: the `results/p2/branch_profile.md` observation that motivated it.
    """

    name: str
    pattern: str
    spec_class: str
    evidence: str


#: The frozen pattern table (DL-020 §1). Data, not control flow: the gate walks
#: this tuple in order and reports the **first** row that matched, so the table's
#: order is part of the rule and changing it changes `reason` strings.
#:
#: Counts in `evidence` are from the P2-T1 S0 profile over the 783,931
#: train + calibration builds (`results/p2/branch_profile.md`) — the test split
#: was not read. They document why each row exists; they are not thresholds.
PROTECTED_PATTERNS: tuple[ProtectedPattern, ...] = (
    ProtectedPattern(
        "mainline", r"(?:master|main|trunk|default)",
        "(c) production-branch",
        "master 500,226 builds (63.8100%); trunk 18,697; main 2; default 1",
    ),
    ProtectedPattern(
        "production_named", r"(?:production|prod|live)",
        "(c) production-branch",
        "358 builds (0.0457%) across 2 distinct names",
    ),
    ProtectedPattern(
        "release_branch", r"release[/_-].*",
        "(b) release/tag build",
        "7,483 builds (0.9545%) across 808 distinct names",
    ),
    ProtectedPattern(
        "release_bare", r"release",
        "(b) release/tag build",
        "the bare name `release`, 832 builds (0.1061%)",
    ),
    ProtectedPattern(
        "stable", r".*(?:^|[/_-])stable(?:[/_-].*)?",
        "(c) production-branch",
        "`stable` 1,560 builds; matched as a delimited token anywhere in the "
        "name so that all three shapes the profile shows are covered — "
        "`1x-stable`-style suffixes (`1.x-stable` 492, `3.0.0-stable` 463) and "
        "prefixes alike (`stable-2.0` 608). `unstable` is not matched",
    ),
    ProtectedPattern(
        "maintenance", r"(?:maint|maintenance)(?:[/_-].*)?",
        "(c) production-branch",
        "140 builds (0.0179%) across 36 distinct names",
    ),
    ProtectedPattern(
        "hotfix", r".*(?:^|[/_-])(?:hotfix|hotfixes)(?:[/_-].*)?",
        "(c) hotfix-tagged",
        "754 builds (0.0962%) across 177 distinct names",
    ),
    ProtectedPattern(
        "version_like", r"v?\d+(?:\.\d+)+(?:[.\d]*)?(?:[/_-].*)?",
        "(b) release/tag build",
        "version-shaped names 29,187 builds (3.7232%) across 6,625 distinct "
        "names — Travis writes a tag build's tag into `git_branch`, so these are "
        "the corpus's only trace of §3.4's release/tag class",
    ),
    ProtectedPattern(
        "version_x_suffix", r"v?\d+(?:\.\d+)*\.x",
        "(b) release/tag build",
        "`3.0.x`, `1.9.x`, `v1.3.x` — version series that `version_like` "
        "does not reach because of the literal `x` component",
    ),
    ProtectedPattern(
        "prerelease", r".*(?:^|[/_-])(?:rc\d*|beta|alpha)(?:[/_-].*)?",
        "(b) release/tag build",
        "265 builds (0.0338%) across 29 distinct names",
    ),
)

#: DL-020 §5: the one judgement call registered for the §4 deferrable-fraction
#: sensitivity sweep at P3-T4. **Not** part of the primary rule — §3.4's
#: non-deferrable class is "production-branch", and an integration branch is by
#: construction not production. Enabling it moves 62,408+ builds (≥7.9609%) from
#: deferrable to non-deferrable.
INTEGRATION_PATTERN: ProtectedPattern = ProtectedPattern(
    "integration", r"(?:develop|dev|devel|development)(?:[/_-].*)?",
    "(c) production-branch — contested reading",
    "develop 47,232; dev 14,875; devel 9,864; development 2,372 builds",
)

#: Named gate variants. The primary is what every headline number uses; the
#: variant exists so P3-T4 can sweep DL-020 §5 without a code change.
VARIANTS: tuple[str, ...] = ("primary", "protected_includes_integration")


@dataclass(frozen=True)
class Eligibility:
    """One build's Stage-1 verdict, with the rule that produced it.

    `reason` is written to be readable in a decision log without consulting this
    module, because it is what the simulator and the API surface to a user.
    """

    eligible: bool
    rule: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"eligible": self.eligible, "rule": self.rule, "reason": self.reason}


def _compiled(variant: str) -> tuple[tuple[ProtectedPattern, re.Pattern[str]], ...]:
    """Compile the pattern table for `variant`, fullmatch-anchored."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown gate variant {variant!r}; expected one of {VARIANTS}")
    table = list(PROTECTED_PATTERNS)
    if variant == "protected_includes_integration":
        table.append(INTEGRATION_PATTERN)
    return tuple((p, re.compile(p.pattern, re.IGNORECASE)) for p in table)


_COMPILED: dict[str, tuple[tuple[ProtectedPattern, re.Pattern[str]], ...]] = {
    v: _compiled(v) for v in VARIANTS
}


def parse_is_pr(value: object) -> bool | None:
    """Parse `gh_is_pr`. Returns None for missing **or unparseable** values.

    The None case matters: it is not folded into False. A value the gate cannot
    read means the gate does not know whether this is a PR, and DL-020 §2 sends
    that case to non-deferrable rather than guessing.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        if value in (0, 1):
            return bool(value)
        return None
    text = str(value).strip().lower()
    if text in _MISSING_TOKENS:
        return None
    if text in _TRUE_TOKENS:
        return True
    if text in _FALSE_TOKENS:
        return False
    return None


def normalise_branch(value: object) -> str | None:
    """Strip a `git_branch` cell to a comparable name, or None if absent."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if text.lower() in _MISSING_TOKENS:
        return None
    return text


def match_protected(branch: str, *, variant: str = "primary") -> ProtectedPattern | None:
    """First pattern-table row matching `branch` in full, or None.

    Matching is `fullmatch` and case-insensitive: `master` is protected,
    `master-fixes` is not. Partial matching would swallow most of the corpus's
    54,512 branch names, and the gate's whole purpose is to be narrow and
    auditable rather than expansive.
    """
    for pattern, rx in _COMPILED[variant]:
        if rx.fullmatch(branch):
            return pattern
    return None


def classify(is_pr: object, branch: object, *, variant: str = "primary") -> Eligibility:
    """Apply the §3.4 gate to one build's two raw inputs (DL-020 §1).

    Evaluated in a fixed order, and the order is part of the rule:

    1. `gh_is_pr` unparseable            -> non-deferrable (fail closed)
    2. `gh_is_pr` true                   -> non-deferrable (PR treated as blocking)
    3. `git_branch` missing/blank        -> non-deferrable (fail closed)
    4. `git_branch` matches the table    -> non-deferrable (named rule)
    5. otherwise                         -> **deferrable**

    Pure and deterministic: same inputs, same verdict, no I/O, no state.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown gate variant {variant!r}; expected one of {VARIANTS}")

    pr = parse_is_pr(is_pr)
    if pr is None:
        return Eligibility(
            False, "fail_closed:is_pr_unparseable",
            f"gh_is_pr={is_pr!r} could not be read as a boolean; DL-020 §2 sends "
            f"uninterpretable input to non-deferrable rather than guessing",
        )
    if pr:
        return Eligibility(
            False, "pr_blocking",
            "gh_is_pr is true; §3.4 class (a) pull-request-blocking. The dataset "
            "does not record whether the check was a required status check, so all "
            "PR builds are treated as blocking (DL-020 §4)",
        )

    name = normalise_branch(branch)
    if name is None:
        return Eligibility(
            False, "fail_closed:branch_missing",
            f"git_branch={branch!r} is missing or blank; DL-020 §2 fails closed",
        )

    hit = match_protected(name, variant=variant)
    if hit is not None:
        return Eligibility(
            False, f"protected:{hit.name}",
            f"git_branch={name!r} matches the frozen pattern '{hit.name}' "
            f"({hit.pattern}), approximating §3.4 class {hit.spec_class}",
        )

    return Eligibility(
        True, "push_to_unprotected_branch",
        f"gh_is_pr is false and git_branch={name!r} matches no protected or "
        f"release pattern; §3.4 class (f), non-blocking push to a non-protected "
        f"branch — deferrable **by rule**, which is an approximation of "
        f"deferability and not a measurement of it (DL-020)",
    )


def is_eligible(is_pr: object, branch: object, *, variant: str = "primary") -> bool:
    """`classify(...).eligible` — the one-bit form used in hot loops."""
    return classify(is_pr, branch, variant=variant).eligible


def classify_frame(builds: pd.DataFrame, *, variant: str = "primary",
                   is_pr_col: str = "gh_is_pr",
                   branch_col: str = "git_branch") -> pd.DataFrame:
    """Vectorised `classify` over a build-grain frame.

    Returns a frame indexed like `builds` with `eligible` / `rule` / `reason`.
    Implemented by grouping on the distinct (is_pr, branch) pairs — there are
    54,512 branch names against ~9.2e5 builds, so this evaluates the rule a few
    tens of thousands of times rather than a million, while producing exactly
    what a per-row loop would.
    """
    for col in (is_pr_col, branch_col):
        if col not in builds.columns:
            raise KeyError(f"classify_frame requires a {col!r} column")

    pairs = pd.MultiIndex.from_arrays(
        [builds[is_pr_col], builds[branch_col]]).unique()
    cache: dict[tuple[object, object], Eligibility] = {
        (a, b): classify(a, b, variant=variant) for a, b in pairs
    }
    verdicts = [cache[(a, b)] for a, b in zip(builds[is_pr_col], builds[branch_col])]
    return pd.DataFrame(
        {
            "eligible": [v.eligible for v in verdicts],
            "rule": [v.rule for v in verdicts],
            "reason": [v.reason for v in verdicts],
        },
        index=builds.index,
    )


def rule_table(variant: str = "primary") -> list[dict[str, str]]:
    """The frozen pattern table as records, for reports and provenance stamps."""
    return [
        {"name": p.name, "pattern": p.pattern, "spec_class": p.spec_class,
         "evidence": p.evidence}
        for p, _ in _COMPILED[variant]
    ]


def summarise(verdicts: Iterable[Eligibility] | pd.DataFrame) -> Mapping[str, object]:
    """Counts by rule plus the deferrable fraction, for the gate-evidence report."""
    if isinstance(verdicts, pd.DataFrame):
        rules = verdicts["rule"]
        eligible = verdicts["eligible"]
    else:
        materialised = list(verdicts)
        rules = pd.Series([v.rule for v in materialised], dtype="object")
        eligible = pd.Series([v.eligible for v in materialised], dtype="bool")
    n = int(len(rules))
    return {
        "builds": n,
        "eligible": int(eligible.sum()),
        "non_eligible": int(n - eligible.sum()),
        "eligible_fraction": float(eligible.mean()) if n else 0.0,
        "by_rule": {str(k): int(v) for k, v in rules.value_counts().items()},
    }

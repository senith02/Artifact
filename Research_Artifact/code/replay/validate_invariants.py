"""Independent invariant validator for the Stage-1 gate (P2-T1 S3).

`development_plan.md` P2-T1 S3 requires *a separate code path that re-derives
eligibility directly from raw columns and audits any decision/results file for
non-deferrable builds that were deferred. It must not import `eligibility.py`.*

**This module therefore does not import `scheduler_core.eligibility`, and a test
asserts that it does not.** It re-derives the DL-020 rule from the decision-log
text, deliberately by a different mechanism: the gate matches anchored regexes,
this validator splits branch names on their delimiters and compares tokens. Two
implementations that agree by construction would prove nothing; the point is
that they were written to agree only *in meaning*, so a drift in either shows up
as a disagreement rather than as a silently shared bug.

⚠ **What a pass from this validator does and does not mean (DL-020 §6).**
A pass proves the audited decisions never deferred a build that **this rule**
calls non-deferrable — internal consistency between the gate and whatever
consumed it. It is **not** evidence that the rule identifies genuinely deferrable
builds. No such evidence exists in this corpus: TravisTorrent carries no
ground-truth deferability, developer-urgency or business-priority label, and two
of spec §3.4's six trigger classes cannot be approximated from it at all. Spec
§4's "eligibility-gate safety = 0" metric means *this*, and must be worded as
such wherever it is reported.

Run:  python replay/validate_invariants.py <decisions.csv> [--variant primary]
      python replay/validate_invariants.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

#: Branch-name delimiters. The gate's patterns treat `/`, `_` and `-` as the
#: boundaries between name components; this validator makes that explicit.
_DELIMITERS: str = "/_-"

#: Missing-value spellings (mirrors `data.NA_TOKENS` + parsed-frame nulls).
_MISSING: frozenset[str] = frozenset({"", "na", "nan", "none", "null"})

_TRUE: frozenset[str] = frozenset({"true", "t", "yes", "y", "1", "1.0"})
_FALSE: frozenset[str] = frozenset({"false", "f", "no", "n", "0", "0.0"})

_MAINLINE: frozenset[str] = frozenset({"master", "main", "trunk", "default"})
_PRODUCTION: frozenset[str] = frozenset({"production", "prod", "live"})
_MAINTENANCE: frozenset[str] = frozenset({"maint", "maintenance"})
_HOTFIX: frozenset[str] = frozenset({"hotfix", "hotfixes"})
_PRERELEASE_WORDS: frozenset[str] = frozenset({"beta", "alpha"})
_INTEGRATION: frozenset[str] = frozenset({"develop", "dev", "devel", "development"})

#: Actions that constitute "this build was deferred" in an audited file.
DEFER_ACTIONS: frozenset[str] = frozenset({"defer", "deferred", "defer_until"})


# --------------------------------------------------------------------------- #
# Independent re-derivation of the DL-020 rule (no regex, no gate import)
# --------------------------------------------------------------------------- #

def _tokens(name: str) -> list[str]:
    """Split a branch name on `/`, `_` and `-`."""
    out, current = [], []
    for ch in name:
        if ch in _DELIMITERS:
            out.append("".join(current))
            current = []
        else:
            current.append(ch)
    out.append("".join(current))
    return out


def _numeric_series(text: str) -> bool:
    """True for `1.0`, `v2.3.4` — a dot-separated run of ≥2 numeric parts.

    Every part must be non-empty and numeric, so `1.` and `1.2beta` are not
    version-like. That strictness is what makes this agree with the gate's
    anchored pattern rather than being merely similar to it.
    """
    body = text[1:] if text[:1] == "v" else text
    parts = body.split(".")
    return len(parts) >= 2 and all(p.isdigit() for p in parts)


def _version_x_series(text: str) -> bool:
    """True for `3.0.x`, `v1.3.x` — a numeric series ending in a literal `x`."""
    body = text[1:] if text[:1] == "v" else text
    parts = body.split(".")
    return (len(parts) >= 2 and parts[-1] == "x"
            and all(p.isdigit() for p in parts[:-1]))


def _prerelease_token(tok: str) -> bool:
    """True for `beta`, `alpha`, `rc`, `rc1`, `rc23`."""
    if tok in _PRERELEASE_WORDS:
        return True
    return tok.startswith("rc") and (tok == "rc" or tok[2:].isdigit())


def protected_rule(branch: str, *, variant: str = "primary") -> str | None:
    """Name of the first DL-020 protected/release rule matching `branch`.

    Returns None when the branch is unprotected. Rule order matches the gate's
    frozen table, because the *name* returned is compared against the gate's in
    the cross-check.
    """
    low = branch.strip().lower()
    toks = _tokens(low)

    if low in _MAINLINE:
        return "mainline"
    if low in _PRODUCTION:
        return "production_named"
    if toks[0] == "release" and len(toks) > 1:
        return "release_branch"
    if low == "release":
        return "release_bare"
    if any(t == "stable" for t in toks):
        return "stable"
    if toks[0] in _MAINTENANCE:
        return "maintenance"
    if any(t in _HOTFIX for t in toks):
        return "hotfix"
    if _numeric_series(toks[0]):
        return "version_like"
    if _version_x_series(low):
        return "version_x_suffix"
    if any(_prerelease_token(t) for t in toks):
        return "prerelease"
    if variant == "protected_includes_integration" and toks[0] in _INTEGRATION:
        return "integration"
    return None


def derive_eligible(is_pr: object, branch: object, *,
                    variant: str = "primary") -> bool:
    """Re-derive Stage-1 eligibility from the two raw columns (DL-020 §1).

    Fails closed on anything uninterpretable, exactly as the gate must.
    """
    if is_pr is None or (isinstance(is_pr, float) and pd.isna(is_pr)):
        return False
    if isinstance(is_pr, bool):
        pr: bool | None = is_pr
    else:
        text = str(is_pr).strip().lower()
        pr = True if text in _TRUE else False if text in _FALSE else None
    if pr is None or pr:
        return False

    if branch is None or (isinstance(branch, float) and pd.isna(branch)):
        return False
    name = str(branch).strip()
    if name.lower() in _MISSING:
        return False

    return protected_rule(name, variant=variant) is None


# --------------------------------------------------------------------------- #
# Auditing a decision / results file
# --------------------------------------------------------------------------- #

@dataclass
class AuditResult:
    """Outcome of auditing one decision file."""

    path: str
    rows: int
    deferred: int
    violations: int
    violation_rows: list[dict[str, object]] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.violations == 0 and not self.missing_columns

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path, "rows": self.rows, "deferred": self.deferred,
            "violations": self.violations, "passed": self.passed,
            "missing_columns": self.missing_columns,
            "violation_rows": self.violation_rows[:50],
        }


REQUIRED_COLUMNS: tuple[str, ...] = ("gh_is_pr", "git_branch", "action")


def audit_frame(df: pd.DataFrame, *, variant: str = "primary",
                path: str = "<frame>", max_examples: int = 50) -> AuditResult:
    """Audit decision records for deferred-but-non-deferrable builds.

    A violation is any row whose `action` is a deferral while this module's
    independent re-derivation says the build is **not** deferrable. That is
    spec §4's eligibility-gate-safety check, and it is expected to be zero by
    construction — a non-zero count means a consumer of the gate is not honouring
    it (or the two implementations have drifted apart).
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return AuditResult(path=path, rows=int(len(df)), deferred=0,
                           violations=0, missing_columns=missing)

    action = df["action"].astype("string").str.strip().str.lower()
    deferred = action.isin(DEFER_ACTIONS)

    derived = [
        derive_eligible(p, b, variant=variant)
        for p, b in zip(df["gh_is_pr"], df["git_branch"])
    ]
    derived_s = pd.Series(derived, index=df.index, dtype="bool")

    bad = deferred & ~derived_s
    examples: list[dict[str, object]] = []
    id_cols = [c for c in ("tr_build_id", "gh_project_name", "strategy")
               if c in df.columns]
    for idx in df.index[bad][:max_examples]:
        row = {c: df.at[idx, c] for c in id_cols}
        row.update({
            "gh_is_pr": df.at[idx, "gh_is_pr"],
            "git_branch": df.at[idx, "git_branch"],
            "action": df.at[idx, "action"],
            "why_non_deferrable": _why(df.at[idx, "gh_is_pr"],
                                       df.at[idx, "git_branch"], variant),
        })
        examples.append(row)

    return AuditResult(path=path, rows=int(len(df)), deferred=int(deferred.sum()),
                       violations=int(bad.sum()), violation_rows=examples)


def _why(is_pr: object, branch: object, variant: str) -> str:
    """Human-readable reason this validator calls a build non-deferrable."""
    if derive_eligible(is_pr, branch, variant=variant):
        return "(eligible — not a violation)"
    text = str(is_pr).strip().lower()
    if text in _TRUE:
        return "gh_is_pr is true (§3.4 class (a), treated as blocking)"
    if text not in _FALSE:
        return f"gh_is_pr={is_pr!r} uninterpretable — fails closed"
    name = str(branch).strip()
    if name.lower() in _MISSING:
        return "git_branch missing/blank — fails closed"
    rule = protected_rule(name, variant=variant)
    return f"git_branch={name!r} matches protected rule {rule!r}"


def load_decisions(path: str | Path) -> pd.DataFrame:
    """Read a decision file. `.csv`, `.csv.gz`, `.json` (records) and `.parquet` supported."""
    path = Path(path)
    if path.suffix == ".csv" or path.name.endswith(".csv.gz"):
        return pd.read_csv(path, dtype=str, keep_default_na=False,
                           na_values=["NA", ""])
    if path.suffix == ".json":
        return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"unsupported decision-file type: {path.suffix!r}")


def audit_file(path: str | Path, *, variant: str = "primary") -> AuditResult:
    """Load and audit one decision file."""
    return audit_frame(load_decisions(path), variant=variant, path=str(path))


def audit_paths(paths: Sequence[str | Path], *,
                variant: str = "primary") -> list[AuditResult]:
    return [audit_file(p, variant=variant) for p in paths]


# --------------------------------------------------------------------------- #
# Cross-check against the gate (imports the gate only here, lazily, so the
# audit path above stays import-independent of scheduler_core.eligibility)
# --------------------------------------------------------------------------- #

def cross_check(pairs: Iterable[tuple[object, object]], *,
                variant: str = "primary") -> dict[str, object]:
    """Compare this module's verdicts against the gate's on `(is_pr, branch)`.

    Imported **inside the function** on purpose: the module-level audit path
    must not depend on `scheduler_core.eligibility`, and a test asserts that.
    This entry point exists only to *measure* agreement between the two
    independent implementations, which is a result worth recording rather than
    an assumption worth making.
    """
    from scheduler_core import eligibility  # local import — see docstring

    materialised = list(pairs)
    disagreements: list[dict[str, object]] = []
    for is_pr, branch in materialised:
        mine = derive_eligible(is_pr, branch, variant=variant)
        theirs = eligibility.classify(is_pr, branch, variant=variant)
        if mine != theirs.eligible:
            disagreements.append({
                "gh_is_pr": is_pr, "git_branch": branch,
                "validator_eligible": mine, "gate_eligible": theirs.eligible,
                "gate_rule": theirs.rule,
                "validator_rule": _why(is_pr, branch, variant),
            })
    return {
        "pairs_checked": len(materialised),
        "disagreements": len(disagreements),
        "agree": not disagreements,
        "examples": disagreements[:50],
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _self_test() -> int:
    """Audit a hand-crafted violating fixture; the validator must reject it."""
    violating = pd.DataFrame({
        "tr_build_id": ["1", "2", "3"],
        "gh_is_pr": ["false", "true", "false"],
        "git_branch": ["feature/x", "feature/y", "master"],
        "action": ["defer", "defer", "defer"],
    })
    result = audit_frame(violating, path="<self-test fixture>")
    print(json.dumps(result.as_dict(), indent=2, default=str))
    ok = result.violations == 2
    print(f"self-test {'PASS' if ok else 'FAIL'}: expected 2 violations, "
          f"got {result.violations}")
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="decision/results files to audit")
    ap.add_argument("--variant", default="primary",
                    choices=["primary", "protected_includes_integration"])
    ap.add_argument("--self-test", action="store_true",
                    help="audit a built-in violating fixture and exit")
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.paths:
        ap.error("give at least one decision file, or --self-test")

    results = audit_paths(args.paths, variant=args.variant)
    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2, default=str))
    else:
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"[{status}] {r.path}: {r.rows:,} rows, {r.deferred:,} deferred, "
                  f"{r.violations:,} violations")
            if r.missing_columns:
                print(f"         missing columns: {r.missing_columns}")
            for ex in r.violation_rows[:10]:
                print(f"         violation: {ex}")
    print("\nNOTE (DL-020 §6): a pass proves the audited decisions are consistent "
          "with the eligibility RULE. It is not evidence that the rule identifies "
          "genuinely deferrable builds — no such ground truth exists in this dataset.")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

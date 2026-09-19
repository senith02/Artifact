"""P2-T1 — tests for the Stage-1 eligibility gate and its independent validator.

Three things are under test, and they are different things:

1. **The gate implements the rule DL-020 fixed** — every §3.4 class it claims to
   approximate, every boundary case the DoD names, and the fail-closed default.
2. **The validator is genuinely independent** — it must not import the gate, and
   it must nevertheless agree with it on the corpus's real branch names.
3. **The validator catches a violation** — the negative test the DoD requires.

None of these tests can say whether the rule is *right*; there is no ground
truth for deferability in this dataset (DL-020 §6). They test that the rule is
implemented as written and applied consistently.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from replay import validate_invariants as vi
from scheduler_core import eligibility as el

CODE_ROOT = Path(__file__).resolve().parents[1]
RESULTS_P2 = CODE_ROOT.parent / "results" / "p2"


# --------------------------------------------------------------------------- #
# 1. The §3.4 classes
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("branch", ["master", "main", "trunk", "default",
                                    "MASTER", "Master"])
def test_mainline_push_is_not_deferrable(branch):
    """§3.4 class (c) — production branch. Includes the DoD's 'push to master'."""
    v = el.classify("false", branch)
    assert v.eligible is False
    assert v.rule == "protected:mainline"


@pytest.mark.parametrize("branch", ["production", "prod", "live"])
def test_production_named_branches_are_not_deferrable(branch):
    assert el.classify("false", branch).rule == "protected:production_named"


@pytest.mark.parametrize("branch,rule", [
    ("release", "release_bare"),
    ("release/5.0", "release_branch"),
    ("release-2", "release_branch"),
    ("release_x", "release_branch"),
    ("1.0", "version_like"),
    ("v5.0", "version_like"),
    ("1.2.3", "version_like"),
    ("v1.0.0-alpha0", "version_like"),
    ("1.5-branch", "version_like"),
    ("3.0.x", "version_x_suffix"),
    ("1.9.x", "version_x_suffix"),
    ("v1.3.x", "version_x_suffix"),
    ("v1.0.0-rc1", "version_like"),
    ("feature-beta", "prerelease"),
    ("my/rc2", "prerelease"),
])
def test_release_and_tag_like_branches_are_not_deferrable(branch, rule):
    """§3.4 class (b) — release/tag builds, the only trace of which in this
    corpus is a tag name written into `git_branch` (DL-020 §1)."""
    v = el.classify("false", branch)
    assert v.eligible is False
    assert v.rule == f"protected:{rule}"


@pytest.mark.parametrize("branch,rule", [
    ("stable", "stable"),
    ("1.x-stable", "stable"),
    ("stable-2.0", "stable"),
    ("3.0.0-stable", "stable"),
    ("maint", "maintenance"),
    ("maintenance/1.4", "maintenance"),
    ("hotfix", "hotfix"),
    ("hotfix/urgent", "hotfix"),
    ("my-hotfix-3", "hotfix"),
])
def test_hotfix_and_stable_branches_are_not_deferrable(branch, rule):
    """§3.4 class (c) — hotfix-tagged / production branches.

    `stable-2.0` and `3.0.0-stable` are pinned deliberately: both are reachable
    by more than one row of the frozen table, and the table is ordered, so they
    must resolve to `stable` rather than to `version_like`. `stable-2.0` is also
    the case that first exposed a real gap — an earlier suffix-anchored pattern
    let its 608 builds through as deferrable.
    """
    assert el.classify("false", branch).rule == f"protected:{rule}"


@pytest.mark.parametrize("branch", [
    "feature/new-parser", "bugfix/123", "topic", "NRPUIV2", "redesign/react",
    "twerks", "qa", "candidate", "bleeding", "python3", "020", "global-net",
    "sis-master", "unstable", "maintainer", "hotfixing", "1.", "1.2beta",
])
def test_push_to_unprotected_branch_is_deferrable(branch):
    """§3.4 class (f) — the only class this corpus can actually populate."""
    v = el.classify("false", branch)
    assert v.eligible is True
    assert v.rule == "push_to_unprotected_branch"


@pytest.mark.parametrize("branch", ["develop", "dev", "devel", "development",
                                    "develop_2.0"])
def test_integration_branches_are_deferrable_in_the_primary_rule(branch):
    """DL-020 §5 — the declared judgement call, primary side."""
    assert el.classify("false", branch).eligible is True


@pytest.mark.parametrize("branch", ["develop", "dev", "devel", "development",
                                    "develop_2.0"])
def test_integration_branches_flip_under_the_swept_variant(branch):
    """DL-020 §5 — and the P3-T4 sweep side. The variant exists so the sweep
    needs no code change."""
    v = el.classify("false", branch, variant="protected_includes_integration")
    assert v.eligible is False
    assert v.rule == "protected:integration"


def test_variant_changes_nothing_else():
    """The variant must move integration branches and nothing but those."""
    names = ["master", "feature/x", "1.0", "hotfix/y", "release/1", "topic", "qa"]
    for n in names:
        a = el.classify("false", n)
        b = el.classify("false", n, variant="protected_includes_integration")
        assert a.eligible == b.eligible and a.rule == b.rule, n


# --------------------------------------------------------------------------- #
# 2. Boundary cases named in the DoD + the fail-closed default
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("branch", ["feature/new-parser", "topic", "master"])
def test_pr_is_never_deferrable_whatever_the_branch(branch):
    """DoD boundary: 'PR to non-protected branch'.

    §3.4 class (a). The PR test runs first, so the branch is not consulted —
    which also neutralises the fact that `git_branch` on a PR build records the
    PR's target branch rather than its source (DL-020 §4).
    """
    v = el.classify("true", branch)
    assert v.eligible is False
    assert v.rule == "pr_blocking"


@pytest.mark.parametrize("value", [None, "", "  ", "NA", "nan", "maybe", "2",
                                   float("nan")])
def test_unparseable_is_pr_fails_closed(value):
    """DL-020 §2 — an unreadable flag is not silently read as 'not a PR'."""
    v = el.classify(value, "feature/x")
    assert v.eligible is False
    assert v.rule == "fail_closed:is_pr_unparseable"


@pytest.mark.parametrize("branch", [None, "", "   ", "NA", "nan", float("nan")])
def test_missing_branch_fails_closed(branch):
    """DoD boundary: 'missing branch'."""
    v = el.classify("false", branch)
    assert v.eligible is False
    assert v.rule == "fail_closed:branch_missing"


@pytest.mark.parametrize("truthy", ["true", "True", "TRUE", "t", "yes", "1", 1, True])
def test_accepted_true_spellings(truthy):
    assert el.parse_is_pr(truthy) is True


@pytest.mark.parametrize("falsey", ["false", "False", "f", "no", "0", 0, False])
def test_accepted_false_spellings(falsey):
    assert el.parse_is_pr(falsey) is False


def test_no_input_combination_ever_raises():
    """The gate is called once per build in the replay; it must be total."""
    odd = [None, "", "NA", "true", "false", 0, 1, 2.5, float("nan"), object(), [], {}]
    for p in odd:
        for b in odd:
            assert isinstance(el.classify(p, b).eligible, bool)


def test_unknown_variant_rejected():
    with pytest.raises(ValueError, match="unknown gate variant"):
        el.classify("false", "master", variant="whatever")


# --------------------------------------------------------------------------- #
# 3. Determinism and purity
# --------------------------------------------------------------------------- #

def test_gate_is_deterministic():
    cases = [("false", "master"), ("true", "feature/x"), ("false", "topic"),
             (None, "topic"), ("false", None), ("false", "3.0.x")]
    first = [el.classify(*c) for c in cases]
    for _ in range(25):
        assert [el.classify(*c) for c in cases] == first


def test_reason_names_the_rule_and_the_driving_value():
    """`reason` is user-facing in the simulator and API; it must stand alone."""
    v = el.classify("false", "release/5.0")
    assert "release/5.0" in v.reason
    assert "release_branch" in v.reason
    assert "§3.4" in v.reason


def test_eligible_reason_refuses_to_claim_ground_truth():
    """DL-020 §7 — the wording discipline is asserted, not merely intended."""
    v = el.classify("false", "feature/x")
    assert "approximation" in v.reason.lower()
    assert "safe to defer" not in v.reason.lower()


def test_classify_frame_matches_the_scalar_path():
    df = pd.DataFrame({
        "gh_is_pr": ["false", "true", "false", None, "false", "false"],
        "git_branch": ["master", "topic", "feature/x", "a", None, "3.0.x"],
    })
    out = el.classify_frame(df)
    expected = [el.classify(p, b) for p, b in zip(df["gh_is_pr"], df["git_branch"])]
    assert list(out["eligible"]) == [e.eligible for e in expected]
    assert list(out["rule"]) == [e.rule for e in expected]


def test_classify_frame_requires_its_columns():
    with pytest.raises(KeyError):
        el.classify_frame(pd.DataFrame({"gh_is_pr": ["false"]}))


def test_summarise_counts_match():
    df = pd.DataFrame({
        "gh_is_pr": ["false"] * 4 + ["true"],
        "git_branch": ["master", "feature/x", "topic", "1.0", "anything"],
    })
    s = el.summarise(el.classify_frame(df))
    assert s["builds"] == 5
    assert s["eligible"] == 2
    assert s["non_eligible"] == 3
    assert s["eligible_fraction"] == pytest.approx(0.4)


def test_rule_table_is_documented():
    """Every frozen pattern must carry the §3.4 class and the evidence for it."""
    table = el.rule_table()
    assert len(table) == len(el.PROTECTED_PATTERNS)
    for row in table:
        assert row["spec_class"].startswith("(")
        assert row["evidence"]
    assert len(el.rule_table("protected_includes_integration")) == len(table) + 1


# --------------------------------------------------------------------------- #
# 4. The validator is independent
# --------------------------------------------------------------------------- #

def test_validator_does_not_import_the_gate_at_module_level():
    """P2-T1 S3's hard requirement, asserted on the AST rather than trusted.

    A lazy import inside `cross_check` is permitted — that function exists only
    to measure agreement — so the check is scoped to module-level statements.
    """
    src = (CODE_ROOT / "replay" / "validate_invariants.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    for node in tree.body:  # module level only
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if "eligibility" in a.name]
        elif isinstance(node, ast.ImportFrom):
            target = f"{node.module or ''}.{','.join(a.name for a in node.names)}"
            if "eligibility" in target:
                offenders.append(target)
    assert not offenders, f"validator imports the gate at module level: {offenders}"


def test_validator_audit_path_works_without_importing_the_gate():
    """Import the validator in a clean interpreter, audit, and assert the gate
    module was never loaded. The AST test proves intent; this proves effect."""
    script = (
        "import sys, pandas as pd;"
        "sys.path.insert(0, r'%s');"
        "from replay import validate_invariants as vi;"
        "df = pd.DataFrame({'gh_is_pr':['false'],'git_branch':['master'],"
        "'action':['defer']});"
        "r = vi.audit_frame(df);"
        "print(r.violations, 'scheduler_core.eligibility' in sys.modules)"
    ) % str(CODE_ROOT)
    out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                         text=True, check=True)
    assert out.stdout.strip() == "1 False", out.stdout + out.stderr


@pytest.mark.parametrize("branch", [
    "master", "main", "trunk", "default", "production", "prod", "live",
    "release", "release/5.0", "release-2", "stable", "1.x-stable", "stable-2.0",
    "maint", "maintenance/1.4", "hotfix", "hotfix/urgent", "my-hotfix-3",
    "1.0", "v5.0", "1.2.3", "3.0.x", "v1.3.x", "v1.0.0-alpha0", "1.5-branch",
    "feature-beta", "my/rc2", "feature/new-parser", "topic", "NRPUIV2",
    "redesign/react", "twerks", "qa", "candidate", "020", "sis-master",
    "unstable", "maintainer", "hotfixing", "1.", "1.2beta", "develop", "dev",
])
def test_validator_agrees_with_the_gate_on_curated_names(branch):
    """Two independently written implementations, same verdict."""
    for variant in el.VARIANTS:
        assert vi.derive_eligible("false", branch, variant=variant) == \
            el.classify("false", branch, variant=variant).eligible, (branch, variant)


@pytest.mark.parametrize("is_pr", [None, "", "NA", "maybe", "true", "false", 1, 0])
def test_validator_agrees_with_the_gate_on_odd_is_pr(is_pr):
    assert vi.derive_eligible(is_pr, "feature/x") == \
        el.classify(is_pr, "feature/x").eligible


@pytest.mark.skipif(not (RESULTS_P2 / "branch_profile.json").exists(),
                    reason="run scripts/profile_branches.py first")
def test_validator_agrees_with_the_gate_on_the_corpus_top_branches():
    """Agreement on real names from the corpus, not just names I thought of.

    Reads the P2-T1 S0 profile, which covers train + calibration only — this
    test does not open the test split.
    """
    profile = json.loads((RESULTS_P2 / "branch_profile.json").read_text("utf-8"))
    names = [row["branch"] for row in profile["branch"]["top_branches"]]
    assert names, "profile carries no branch names"
    report = vi.cross_check([("false", n) for n in names] +
                            [("true", n) for n in names])
    assert report["agree"], report["examples"]


# --------------------------------------------------------------------------- #
# 5. The validator catches a violation (the DoD's negative test)
# --------------------------------------------------------------------------- #

def _violating_fixture() -> pd.DataFrame:
    """Hand-crafted: two builds the gate calls non-deferrable, deferred anyway."""
    return pd.DataFrame({
        "tr_build_id": ["1", "2", "3", "4", "5"],
        "gh_project_name": ["p/a"] * 5,
        "gh_is_pr": ["false", "true", "false", "false", "false"],
        "git_branch": ["feature/x", "feature/y", "master", "topic", "1.0"],
        "action": ["defer", "defer", "defer", "run_now", "run_now"],
    })


def test_validator_catches_the_violating_fixture():
    """The negative test P2-T1's DoD requires."""
    r = vi.audit_frame(_violating_fixture(), path="<fixture>")
    assert r.passed is False
    assert r.violations == 2          # the PR build and the master push
    assert r.deferred == 3
    offenders = {row["git_branch"] for row in r.violation_rows}
    assert offenders == {"feature/y", "master"}
    reasons = " ".join(str(row["why_non_deferrable"]) for row in r.violation_rows)
    assert "gh_is_pr is true" in reasons
    assert "mainline" in reasons


def test_validator_passes_on_gate_output():
    """The positive half: decisions produced *by the gate* must audit clean."""
    df = _violating_fixture()
    verdicts = el.classify_frame(df)
    df = df.assign(action=["defer" if e else "run_now" for e in verdicts["eligible"]])
    r = vi.audit_frame(df, path="<gate output>")
    assert r.passed is True
    assert r.violations == 0
    assert r.deferred == int(verdicts["eligible"].sum())


def test_validator_reports_missing_columns_instead_of_passing_silently():
    """A file it cannot audit must not be recorded as a pass."""
    r = vi.audit_frame(pd.DataFrame({"action": ["defer"]}), path="<partial>")
    assert r.passed is False
    assert set(r.missing_columns) == {"gh_is_pr", "git_branch"}


def test_validator_honours_the_swept_variant():
    """Deferring a `develop` push is clean under the primary rule and a
    violation under the variant — so P3-T4's sweep is auditable too."""
    df = pd.DataFrame({"gh_is_pr": ["false"], "git_branch": ["develop"],
                       "action": ["defer"]})
    assert vi.audit_frame(df).violations == 0
    assert vi.audit_frame(
        df, variant="protected_includes_integration").violations == 1


@pytest.mark.parametrize("action", ["defer", "Defer", " DEFERRED ", "defer_until"])
def test_defer_action_spellings_are_all_audited(action):
    df = pd.DataFrame({"gh_is_pr": ["false"], "git_branch": ["master"],
                       "action": [action]})
    assert vi.audit_frame(df).violations == 1


def test_run_now_on_a_non_deferrable_build_is_not_a_violation():
    """The invariant is one-directional: running anything is always allowed."""
    df = pd.DataFrame({"gh_is_pr": ["true", "false"],
                       "git_branch": ["master", "master"],
                       "action": ["run_now", "run_now"]})
    assert vi.audit_frame(df).violations == 0


def test_validator_roundtrips_csv(tmp_path):
    p = tmp_path / "decisions.csv"
    _violating_fixture().to_csv(p, index=False)
    r = vi.audit_file(p)
    assert r.violations == 2
    assert Path(r.path) == p


def test_validator_rejects_unsupported_file_type(tmp_path):
    p = tmp_path / "decisions.txt"
    p.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported decision-file type"):
        vi.audit_file(p)


def test_validator_cli_self_test_passes():
    r = subprocess.run([sys.executable, "-m", "replay.validate_invariants",
                        "--self-test"], cwd=CODE_ROOT, capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "self-test PASS" in r.stdout


def test_validator_cli_fails_on_a_violating_file(tmp_path):
    p = tmp_path / "decisions.csv"
    _violating_fixture().to_csv(p, index=False)
    r = subprocess.run([sys.executable, "-m", "replay.validate_invariants", str(p)],
                       cwd=CODE_ROOT, capture_output=True, text=True)
    assert r.returncode == 1
    assert "[FAIL]" in r.stdout
    assert "DL-020" in r.stdout

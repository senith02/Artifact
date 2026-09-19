# P2-T1 — Stage-1 eligibility gate, applied to the real corpus

*Run `python scripts/apply_eligibility.py` on 2026-09-17; 37.3s. Every number is from this run (R1).*

> **This measures the rule, not deferability.** DL-020 §6: the gate is an experimental approximation of spec §3.4's trigger classes from the two columns TravisTorrent actually carries. Two of the six §3.4 classes (manually-triggered, scheduled/nightly) have no marker in the data and are not approximated at all, so the deferrable set below consists entirely of class (f). The approximation's error rate is **unmeasurable in this corpus** — there is no ground-truth deferability label to score it against. Nothing here is evidence about which builds are genuinely safe to delay.

## Funnel

| Stage | Builds |
| :-- | --: |
| analytic builds | 922,624 |
| test split builds dropped unread | 138,693 |
| builds gated train plus calibration | 783,931 |
| distinct projects | 778 |

## Variant `primary`

- Builds gated: **783,931**
- Deferrable **by rule**: **191,245** (24.3956%)
- Non-deferrable: **592,686**

| Rule fired | Builds | Share |
| :-- | --: | --: |
| `protected:mainline` | 404,533 | 51.6031% |
| `push_to_unprotected_branch` | 191,245 | 24.3956% |
| `pr_blocking` | 140,506 | 17.9233% |
| `protected:version_like` | 26,068 | 3.3253% |
| `protected:stable` | 6,865 | 0.8757% |
| `protected:version_x_suffix` | 6,145 | 0.7839% |
| `protected:release_branch` | 5,848 | 0.7460% |
| `protected:release_bare` | 827 | 0.1055% |
| `protected:hotfix` | 715 | 0.0912% |
| `protected:prerelease` | 700 | 0.0893% |
| `protected:production_named` | 357 | 0.0455% |
| `protected:maintenance` | 122 | 0.0156% |

**§4 eligibility-gate safety** (independent validator on the gate's own output): 191,245 deferred, **0 violations** → PASS. Per DL-020 §6 this proves gate/consumer consistency, not gate correctness.

## Variant `protected_includes_integration`

- Builds gated: **783,931**
- Deferrable **by rule**: **132,100** (16.8510%)
- Non-deferrable: **651,831**

| Rule fired | Builds | Share |
| :-- | --: | --: |
| `protected:mainline` | 404,533 | 51.6031% |
| `pr_blocking` | 140,506 | 17.9233% |
| `push_to_unprotected_branch` | 132,100 | 16.8510% |
| `protected:integration` | 59,145 | 7.5447% |
| `protected:version_like` | 26,068 | 3.3253% |
| `protected:stable` | 6,865 | 0.8757% |
| `protected:version_x_suffix` | 6,145 | 0.7839% |
| `protected:release_branch` | 5,848 | 0.7460% |
| `protected:release_bare` | 827 | 0.1055% |
| `protected:hotfix` | 715 | 0.0912% |
| `protected:prerelease` | 700 | 0.0893% |
| `protected:production_named` | 357 | 0.0455% |
| `protected:maintenance` | 122 | 0.0156% |

**§4 eligibility-gate safety** (independent validator on the gate's own output): 132,100 deferred, **0 violations** → PASS. Per DL-020 §6 this proves gate/consumer consistency, not gate correctness.

## Independent cross-check (the point of a second implementation)

`scheduler_core/eligibility.py` matches anchored regexes; `replay/validate_invariants.py` splits names on `/`, `_`, `-` and compares tokens. Neither imports the other. Agreement is therefore evidence, not tautology.

| Variant | Distinct input pairs | Distinct branch names | Disagreements |
| :-- | --: | --: | --: |
| `primary` | 55,228 | 54,512 | **0** |
| `protected_includes_integration` | 55,228 | 54,512 | **0** |

## The frozen pattern table

| # | Rule | Pattern | §3.4 class approximated | Profile evidence |
| --: | :-- | :-- | :-- | :-- |
| 1 | `mainline` | `(?:master|main|trunk|default)` | (c) production-branch | master 500,226 builds (63.8100%); trunk 18,697; main 2; default 1 |
| 2 | `production_named` | `(?:production|prod|live)` | (c) production-branch | 358 builds (0.0457%) across 2 distinct names |
| 3 | `release_branch` | `release[/_-].*` | (b) release/tag build | 7,483 builds (0.9545%) across 808 distinct names |
| 4 | `release_bare` | `release` | (b) release/tag build | the bare name `release`, 832 builds (0.1061%) |
| 5 | `stable` | `.*(?:^|[/_-])stable(?:[/_-].*)?` | (c) production-branch | `stable` 1,560 builds; matched as a delimited token anywhere in the name so that all three shapes the profile shows are covered — `1x-stable`-style suffixes (`1.x-stable` 492, `3.0.0-stable` 463) and prefixes alike (`stable-2.0` 608). `unstable` is not matched |
| 6 | `maintenance` | `(?:maint|maintenance)(?:[/_-].*)?` | (c) production-branch | 140 builds (0.0179%) across 36 distinct names |
| 7 | `hotfix` | `.*(?:^|[/_-])(?:hotfix|hotfixes)(?:[/_-].*)?` | (c) hotfix-tagged | 754 builds (0.0962%) across 177 distinct names |
| 8 | `version_like` | `v?\d+(?:\.\d+)+(?:[.\d]*)?(?:[/_-].*)?` | (b) release/tag build | version-shaped names 29,187 builds (3.7232%) across 6,625 distinct names — Travis writes a tag build's tag into `git_branch`, so these are the corpus's only trace of §3.4's release/tag class |
| 9 | `version_x_suffix` | `v?\d+(?:\.\d+)*\.x` | (b) release/tag build | `3.0.x`, `1.9.x`, `v1.3.x` — version series that `version_like` does not reach because of the literal `x` component |
| 10 | `prerelease` | `.*(?:^|[/_-])(?:rc\d*|beta|alpha)(?:[/_-].*)?` | (b) release/tag build | 265 builds (0.0338%) across 29 distinct names |
| 11 | `integration` | `(?:develop|dev|devel|development)(?:[/_-].*)?` | (c) production-branch — contested reading | develop 47,232; dev 14,875; devel 9,864; development 2,372 builds |

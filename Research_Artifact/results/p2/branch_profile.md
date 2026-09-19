# P2-T1 S0 — Stage-1 gate input profile (train + calibration only)

*Run `python scripts/profile_branches.py` on 2026-09-17; 30.1s. Every number below is from this run (R1).*

> **Split discipline.** The 170 test projects were filtered out before any statistic was computed — see `test_split_builds_dropped_unread` below. No label and no duration statistic is reported; `tr_status` is read only as the analytic funnel's label-recognition filter.

## Funnel

| Stage | Builds |
| :-- | --: |
| job rows read | 3,881,992 |
| builds after aggregation | 925,897 |
| analytic builds | 922,624 |
| test split builds dropped unread | 138,693 |
| unassigned builds dropped | 0 |
| builds profiled train plus calibration | 783,931 |

## `git_branch` — presence

- Present: **783,931** / 783,931 builds
- Missing: **0** (0.0000%)
- Distinct branch names: **54,512**

## `git_branch` — top 40 names

| # | Branch | Builds | Share of profiled builds |
| --: | :-- | --: | --: |
| 1 | `master` | 500,226 | 63.8100% |
| 2 | `develop` | 47,232 | 6.0250% |
| 3 | `trunk` | 18,697 | 2.3850% |
| 4 | `dev` | 14,875 | 1.8975% |
| 5 | `devel` | 9,864 | 1.2583% |
| 6 | `development` | 2,372 | 0.3026% |
| 7 | `NRPUIV2` | 1,727 | 0.2203% |
| 8 | `stable` | 1,560 | 0.1990% |
| 9 | `3.0.x` | 1,259 | 0.1606% |
| 10 | `1.0` | 1,221 | 0.1558% |
| 11 | `redesign/react` | 1,118 | 0.1426% |
| 12 | `ng` | 1,047 | 0.1336% |
| 13 | `2.0` | 905 | 0.1154% |
| 14 | `1.2` | 891 | 0.1137% |
| 15 | `twerks` | 845 | 0.1078% |
| 16 | `release` | 832 | 0.1061% |
| 17 | `candidate` | 799 | 0.1019% |
| 18 | `qa` | 789 | 0.1006% |
| 19 | `release/5.0` | 771 | 0.0984% |
| 20 | `feature/rails3` | 758 | 0.0967% |
| 21 | `bleeding` | 706 | 0.0901% |
| 22 | `1.8` | 642 | 0.0819% |
| 23 | `v5.0` | 611 | 0.0779% |
| 24 | `stable-2.0` | 608 | 0.0776% |
| 25 | `020` | 595 | 0.0759% |
| 26 | `CDB-2891` | 504 | 0.0643% |
| 27 | `1.x-stable` | 492 | 0.0628% |
| 28 | `global-net` | 473 | 0.0603% |
| 29 | `bootstrap` | 471 | 0.0601% |
| 30 | `3.0.0-stable` | 463 | 0.0591% |
| 31 | `1.9.x` | 450 | 0.0574% |
| 32 | `develop_2.0` | 437 | 0.0557% |
| 33 | `sis-master` | 437 | 0.0557% |
| 34 | `python3` | 430 | 0.0549% |
| 35 | `v1.0.0-alpha0` | 419 | 0.0534% |
| 36 | `1.5-branch` | 405 | 0.0517% |
| 37 | `release/3.0` | 391 | 0.0499% |
| 38 | `v1.3.x` | 384 | 0.0490% |
| 39 | `v1.5.x` | 384 | 0.0490% |
| 40 | `staging` | 379 | 0.0483% |

## Candidate patterns (questions asked of the data — not yet the rule)

| Pattern | Group | Regex | Builds | Share of named | Distinct names |
| :-- | :-- | :-- | --: | --: | --: |
| master | protected_like | `^master$` | 500,226 | 63.8100% | 1 |
| main | protected_like | `^main$` | 2 | 0.0003% | 1 |
| trunk | protected_like | `^trunk$` | 18,697 | 2.3850% | 1 |
| default | protected_like | `^default$` | 1 | 0.0001% | 1 |
| develop_or_dev | protected_like | `^(develop|dev)$` | 62,408 | 7.9609% | 3 |
| production_like | protected_like | `^(production|prod|live)$` | 358 | 0.0457% | 2 |
| release_branch | protected_like | `^release[/_-]` | 7,483 | 0.9545% | 808 |
| stable_suffix | protected_like | `(^|[/_-])stable$` | 1,560 | 0.1990% | 1 |
| maint_branch | protected_like | `^(maint|maintenance)([/_-]|$)` | 140 | 0.0179% | 36 |
| version_branch | protected_like | `^v?\d+(\.\d+)+([/_-].*)?$` | 29,187 | 3.7232% | 6,625 |
| hotfix_like | protected_like | `(^|[/_-])(hotfix|hotfixes)([/_-]|$)` | 754 | 0.0962% | 177 |
| tag_like_semver | release_tag_like | `^v?\d+\.\d+(\.\d+)?([-+].*)?$` | 28,297 | 3.6096% | 5,891 |
| rc_like | release_tag_like | `(^|[/_-])(rc\d*|beta|alpha)([/_-]|$)` | 265 | 0.0338% | 29 |

## `gh_is_pr`

- Present: **783,931**, missing: **0**
- Raw values: `{'false': 643425, 'true': 140506}`
- PR-triggered builds: **140,506** (17.9233%)

| Cross-tab | Builds |
| :-- | --: |
| pr and master like | 114,393 |
| pr and other branch | 26,113 |
| push and master like | 404,533 |
| push and other branch | 238,892 |

## What this profile cannot tell us

The dataset has no scheduled/nightly flag, no release/tag trigger flag, no hotfix label, no manual-trigger flag, no branch-protection state and no developer urgency signal. The patterns above are *name-shaped guesses* at constructs the data does not record. Any gate built on them is an approximation whose error is unmeasurable in this corpus — which is the substance of DL-020.

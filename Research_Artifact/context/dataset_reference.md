# Context — TravisTorrent Dataset Reference (grounded in the real file)

> **Authority for all column names.** These are read directly from the header of the actual CSV.
> The TravisTorrent *paper* (Table 1) uses different names — **do not use the paper's names in code**
> (see decision DL-002). When in doubt, re-read the header and update this file.

## File location & shape

- **Path (read-only input):** `../Dataset/19314170/final-2017-01-25.csv/final-2017-01-25.csv`
  (relative to `Research_Artifact/`). Also present compressed: `final-2017-01-25.csv.gz`,
  `travistorrent_5_3_2016.csv.gz`, `travistorrent_28_8_2015.csv.gz`.
- **Grain:** one row = **one Travis build job**. (~2.6M rows in the 2017 release.)
- **Columns:** 66 (listed below, in file order).
- **Languages:** Ruby and Java projects (`gh_lang`).
- **Encoding note:** several columns are `#`-delimited lists inside a single CSV cell
  (e.g. `gh_commits_in_push`, `git_all_built_commits`); `NA` / empty strings appear for missing values.

## The 66 columns (exact header order)

```
tr_build_id, gh_project_name, gh_is_pr, gh_pr_created_at, gh_pull_req_num, gh_lang,
git_merged_with, git_branch, gh_num_commits_in_push, gh_commits_in_push,
git_prev_commit_resolution_status, git_prev_built_commit, tr_prev_build,
gh_first_commit_created_at, gh_team_size, git_all_built_commits, git_num_all_built_commits,
git_trigger_commit, tr_virtual_merged_into, gh_num_issue_comments, gh_num_commit_comments,
gh_num_pr_comments, git_diff_src_churn, git_diff_test_churn, gh_diff_files_added,
gh_diff_files_deleted, gh_diff_files_modified, gh_diff_tests_added, gh_diff_tests_deleted,
gh_diff_src_files, gh_diff_doc_files, gh_diff_other_files, gh_num_commits_on_files_touched,
gh_sloc, gh_test_lines_per_kloc, gh_test_cases_per_kloc, gh_asserts_cases_per_kloc,
gh_by_core_team_member, gh_description_complexity, gh_pushed_at, gh_build_started_at,
gh_repo_age, gh_repo_num_commits, tr_job_id, tr_build_number, tr_log_lan, tr_log_status,
tr_log_setup_time, tr_log_analyzer, tr_log_frameworks, tr_log_bool_tests_ran,
tr_log_bool_tests_failed, tr_log_num_tests_ok, tr_log_num_tests_failed, tr_log_num_tests_run,
tr_log_num_tests_skipped, tr_log_num_test_suites_run, tr_log_num_test_suites_ok,
tr_log_num_test_suites_failed, tr_log_tests_failed, tr_log_testduration, tr_log_buildduration,
tr_original_commit, tr_duration, tr_status, tr_jobs
```

## Role of each column in THIS project

### Label (target) — build outcome
| Column | Meaning | Use |
| :-- | :-- | :-- |
| `tr_status` | Overall build status: `passed` / `failed` / `errored` / `canceled` | **Primary label source.** Define failure = {failed, errored}; pass = {passed}; drop/handle `canceled` (status unknown — see §6 threats). |
| `tr_log_status` | Status as parsed from the build log | Cross-check / fallback for `tr_status`. |
| `tr_log_bool_tests_failed` | Whether tests failed (boolean) | Secondary signal; **leaky** for prediction (derived from outcome) — label only, never a feature. |

### Features (commit-time only) — see `feature_spec.md` for the exact engineered set
| Column | Meaning | Feature use |
| :-- | :-- | :-- |
| `git_diff_src_churn` | Lines of production code changed by the new commits | churn |
| `git_diff_test_churn` | Lines of test code changed | test churn |
| `gh_diff_files_added` / `_deleted` / `_modified` | File add/delete/modify counts | files-touched, change spread |
| `gh_diff_tests_added` / `_deleted` | Test lines added/deleted | test activity |
| `gh_diff_src_files` / `gh_diff_doc_files` / `gh_diff_other_files` | Count of src / doc / other files in the change | **file-type mix** (docs-only detection) |
| `gh_num_commits_in_push` / `git_num_all_built_commits` | Commits in the push / built | change size |
| `gh_num_commits_on_files_touched` | Recent commits on touched files (3-mo window) | code "hotness" |
| `gh_sloc` | Executable production SLOC in the whole repo | size normaliser |
| `gh_test_lines_per_kloc` / `gh_test_cases_per_kloc` / `gh_asserts_cases_per_kloc` | Test density metrics | test maturity |
| `gh_team_size` | Contributors in last 3 months | project context |
| `gh_by_core_team_member` | Commit by a core member (boolean) | developer experience proxy |
| `gh_repo_age` | Repo age at build time | maturity |
| `gh_repo_num_commits` | Total repo commits | maturity |
| `gh_description_complexity` | Words in PR title+description (PRs only) | change intent proxy |
| `gh_lang` | Dominant language (ruby/java) | stratification / categorical |
| `gh_is_pr` | Build triggered by a PR (boolean) | **also feeds the eligibility gate** |

> **Change entropy & fix-keyword flag** from §3.5 are **not** native columns. Entropy must be derived
> from the per-file churn distribution where available; the fix-keyword flag needs commit messages,
> which TravisTorrent does **not** include. If a feature cannot be built from these columns, log it in
> the decision log and either drop it or document the proxy used (DL-002 precedent).

### Eligibility gate inputs (§3.4, Stage 1 — rule-based)
| Column | Use |
| :-- | :-- |
| `gh_is_pr` | PR-triggered builds → treated per gate rules (PR-blocking = non-deferrable). |
| `git_branch` | Branch name → detect production/protected branches (e.g. `master`, `*-stable`). |
| `gh_pull_req_num` / `gh_pr_created_at` | PR context. |

> TravisTorrent has **no explicit "scheduled/nightly" or "release/tag" trigger flag**. The gate's
> deferrable/non-deferrable classes (§3.4) must therefore be **approximated** from `gh_is_pr` +
> `git_branch` (+ heuristics). This approximation is a modelling decision — log it (DL) and surface it
> as a threat to validity.

### Simulator clock / arrival / duration (§3.1, §3.3)
| Column | Use |
| :-- | :-- |
| `gh_build_started_at` | Build start timestamp → replay arrival time + hour-of-week alignment to carbon series. |
| `gh_pushed_at` / `gh_first_commit_created_at` / `gh_pr_created_at` | Alternative event times. |
| `tr_duration` | Overall build duration (s) → energy ∝ duration; latency accounting. |
| `tr_log_buildduration` / `tr_log_testduration` | Finer-grained durations. |
| `tr_log_setup_time` | Travis setup time (s). |

### Identifiers & joins
`tr_build_id`, `tr_job_id`, `tr_build_number`, `tr_prev_build`, `gh_project_name`,
`git_trigger_commit`, `git_merged_with`, `git_all_built_commits`, `tr_jobs`, `tr_original_commit`,
`tr_virtual_merged_into`, `git_prev_built_commit`, `git_prev_commit_resolution_status`.

## Known gotchas (read before writing the loader)

1. **Job-level vs build-level.** Rows are *build jobs*; a build can have many jobs (`tr_jobs`,
   `tr_build_number`). Decide and document whether you model at job or build grain (recommended: build
   grain — aggregate jobs by `tr_build_id`) — log the choice.
2. **`canceled` builds** have unknown true status — exclude from training labels; handle explicitly.
3. **Class imbalance:** passes vastly outnumber failures → use PR-AUC + class weighting (§3.5, R7).
4. **`#`-separated list cells** must be split, not parsed as numbers.
5. **`NA` / empty** appear in many numeric columns (esp. PR-only fields) — impute or flag, don't crash.
6. **Leakage:** anything in the `tr_log_*` test-result family is computed from running the build →
   **label-side only**, never a feature (R7).
7. **Temporal span:** timestamps are 2011–2016-era; the carbon series is recent → aligned by
   **hour-of-week** per spec §3.2 (a declared assumption/threat).

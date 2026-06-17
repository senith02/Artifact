# Context — Feature Specification (grounds spec §3.5)

The exact engineered feature set for the build-failure-likelihood model, each mapped to real
TravisTorrent columns (`context/dataset_reference.md`) or to a clearly-labelled derivation. This is the
contract the feature extractor in `code/scheduler_core/features.py` must implement. **Commit-time only**
— nothing derived from the build outcome or the future (R7).

## Target

- **`y` = build failed** ∈ {0,1}, where failure = `tr_status ∈ {failed, errored}`, pass = `passed`.
  `canceled` rows are excluded from labelling. Modelled as a **calibrated probability** (the deferral
  knob), not a hard class (spec §3.4–3.5).

## Feature table

| # | Feature | Source column(s) | Derivation | JIT family (§3.5) |
| :- | :-- | :-- | :-- | :-- |
| 1 | `src_churn` | `git_diff_src_churn` | direct | size / diffusion |
| 2 | `test_churn` | `git_diff_test_churn` | direct | size |
| 3 | `files_added` | `gh_diff_files_added` | direct | diffusion |
| 4 | `files_deleted` | `gh_diff_files_deleted` | direct | diffusion |
| 5 | `files_modified` | `gh_diff_files_modified` | direct | diffusion |
| 6 | `files_total` | added+deleted+modified | sum | diffusion |
| 7 | `tests_added` | `gh_diff_tests_added` | direct | test activity |
| 8 | `tests_deleted` | `gh_diff_tests_deleted` | direct | test activity |
| 9 | `src_files` | `gh_diff_src_files` | direct | file-type mix |
| 10 | `doc_files` | `gh_diff_doc_files` | direct | file-type mix |
| 11 | `other_files` | `gh_diff_other_files` | direct | file-type mix |
| 12 | `is_docs_only` | `gh_diff_src_files`, `gh_diff_doc_files`, `gh_diff_other_files` | doc_files>0 AND src_files==0 | change purpose |
| 13 | `num_commits` | `gh_num_commits_in_push` / `git_num_all_built_commits` | direct (pick one, document) | size |
| 14 | `commits_on_files_touched` | `gh_num_commits_on_files_touched` | direct | history / hotness |
| 15 | `sloc` | `gh_sloc` | direct | size context |
| 16 | `test_lines_per_kloc` | `gh_test_lines_per_kloc` | direct | test maturity |
| 17 | `test_cases_per_kloc` | `gh_test_cases_per_kloc` | direct | test maturity |
| 18 | `asserts_per_kloc` | `gh_asserts_cases_per_kloc` | direct | test maturity |
| 19 | `team_size` | `gh_team_size` | direct | dev experience |
| 20 | `by_core_member` | `gh_by_core_team_member` | bool→{0,1} | dev experience |
| 21 | `repo_age` | `gh_repo_age` | direct | maturity |
| 22 | `repo_num_commits` | `gh_repo_num_commits` | direct | maturity |
| 23 | `description_complexity` | `gh_description_complexity` | direct (NA→0 for non-PR) | change intent |
| 24 | `is_pr` | `gh_is_pr` | bool→{0,1} | context |
| 25 | `lang` | `gh_lang` | categorical (ruby/java) | context |
| 26 | `hour_of_day` | `gh_build_started_at` | parse → 0–23 | temporal |
| 27 | `day_of_week` | `gh_build_started_at` | parse → 0–6 | temporal |
| 28 | `test_density_ratio` | `gh_diff_test_churn`, `git_diff_src_churn` | test_churn / (src_churn+1) | test discipline |

## Spec features that need a derivation or proxy (flag in the decision log)

| §3.5 feature | Status | Plan |
| :-- | :-- | :-- |
| **Change entropy** | No native column | Derive from per-file churn distribution if obtainable; otherwise approximate via `files_total` spread and **log the proxy** (DL). |
| **Fix-keyword flag** | **Not available** — TravisTorrent has no commit messages | Drop, or join an external commit-message source (out of scope). **Must be logged** as a dropped feature with rationale. |
| **Developer total/recent experience** | No per-author commit count column | Proxy with `by_core_member` + `team_size` + `commits_on_files_touched`; **log the proxy**. |
| **Subsystems/directories touched** | No directory-path column | Approximate with `files_total` / file-type counts; **log**. |

> Any feature that cannot be built faithfully from the dataset is a decision-log entry (R4), not a
> silent omission. Better an honest proxy + threat-to-validity note than an invented value (R1).

## Leakage blocklist (NEVER use as features — R7)

`tr_status`, `tr_log_status`, `tr_log_bool_tests_ran`, `tr_log_bool_tests_failed`,
`tr_log_num_tests_ok`, `tr_log_num_tests_failed`, `tr_log_num_tests_run`,
`tr_log_num_tests_skipped`, `tr_log_num_test_suites_*`, `tr_log_tests_failed`,
`tr_log_testduration`, `tr_log_buildduration`, `tr_duration`, `tr_prev_build` (uses future linkage).
These are **outcomes/durations** known only after the build runs. `tr_duration` /
`tr_log_buildduration` are allowed **only** as simulator inputs (energy/latency), never as model
features.

## Split discipline (R7, §3.5)

- **Project-held-out + time-ordered**: group by `gh_project_name`, order by `gh_build_started_at`,
  hold out whole projects for validation/test, and never let a later build train a model evaluated on
  an earlier one. No random shuffling, no random k-fold.

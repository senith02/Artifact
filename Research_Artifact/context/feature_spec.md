# Context — Feature Specification (grounds spec §3.5 + Layer 0-A / DL-012)

The exact engineered feature set for the commit-level decision model, each mapped to real
TravisTorrent columns (`context/dataset_reference.md`) or to a clearly-labelled derivation. This is the
contract the feature extractor in `code/scheduler_core/features.py` must implement. **Commit-time only**
— nothing derived from the build outcome or the future (R7).

> **Amended 2026-08-09 by DL-012.** The 28-feature contract is **unchanged**. What changed: (a) the
> features now serve a *selective-scheduling decision model*, of which build-failure likelihood is one
> candidate signal rather than the whole purpose; (b) they are partitioned into **six disjoint families**
> for ablation (§Families); (c) build duration gains a strictly-bounded, three-role separation
> (§Duration). Protocol detail: `results/p0/eval_protocol.md` Amendment A1.

## Targets

Three distinct targets are fitted from this one feature matrix. They must never be confused:

| Target | Definition | Fitted on | Consumed by |
| :-- | :-- | :-- | :-- |
| **`y` = build failed** | ∈ {0,1}; failure = `tr_status ∈ {failed, errored}`, pass = `passed`; `canceled` excluded. Modelled as a **calibrated probability** (spec §3.4–3.5), not a hard class. | train split; calibrated on calibration split | Stage 2, **only if** its family is admitted under A1.7 |
| **`d̂` = expected duration** | commit-time estimate of `log(1 + tr_duration)`; the **control** variable for RQ2 | train-split projects, **earlier builds only** (A1.1) | strategy ④ and every ⑤ arm (as the control term) |
| **scheduling decision** | defer / run-now + window | evidence-derived `policy_spec.yaml` (A1.7) | `scheduler_core.decide()` |

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

## Feature families (ablation units — DL-012 / A1.3)

Every feature belongs to **exactly one** family. The families, not individual features, are the unit of
the incremental-value ablation and of policy admission (A1.7), so this partition is a contract: changing
it changes what RQ1/RQ2 mean and requires a DL entry.

| ID | Family | Feature #s | Count |
| :-- | :-- | :-- | :-: |
| **F1** | change size & diffusion | 1, 2, 3, 4, 5, 6, 13 | 7 |
| **F2** | change purpose & composition | 9, 10, 11, 12, 23, 28 | 6 |
| **F3** | test activity & maturity | 7, 8, 16, 17, 18 | 5 |
| **F4** | project history & maturity | 14, 15, 21, 22, 25 | 5 |
| **F5** | developer & team | 19, 20 | 2 |
| **F6** | temporal & trigger context | 24, 26, 27 | 3 |
| | | **total** | **28** |

Notes that bite:
- **F4 is the project-identity–adjacent family.** A positive F4 result is the most likely to be "the
  model learned which repo this is" — it is precisely why strategy ④b (per-project prior) and the
  variance decomposition are mandatory (A1.9).
- **`is_pr` (24) is also read by the Stage-1 eligibility gate.** Its presence in F6 means an F6 gain may
  partly restate the gate; report the overlap rather than claiming it as new SE signal.
- The duration control `d̂` is **not** a family. It is present in **every** ablation arm, including the
  null — that is what "beyond expected build duration" means (A1.3).

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
These are **outcomes/durations** known only after the build runs.

### Duration — the three permitted roles, and no fourth (DL-012 / A1.2)

`tr_duration` and `tr_log_buildduration` are **outcomes of the build being scheduled**. The reframed
research question ("beyond expected build duration") makes it tempting to feed them in; doing so is a
leakage defect, not a design choice. They may appear **only** as:

| # | Role | Where it may be read | Hard constraint |
| :-- | :-- | :-- | :-- |
| 1 | **Accounting** | simulator: energy (DL-007/010), latency, TTFF | post-hoc only — never reaches `decide()` |
| 2 | **Historical training label** for `d̂` | `scheduler_core/duration_estimator.py` | **train-split projects only**, and only builds strictly **earlier** than the one being scored |
| 3 | **Oracle sensitivity bound** | one clearly-labelled retrospective arm (A1.10) | must carry the label *"oracle — unrealizable in deployment"* |

**The decision-time rule, stated once:** the value of `tr_duration` **for the build being decided** is
never available to any decision input, in simulation or in the prototype. What the decision sees is
`d̂` — an estimate formed from earlier builds and commit-time features. `tr_prev_build` remains
blocklisted outright (future linkage); the duration estimator reaches project history through the
split-and-time-filtered path in role 2, not through that column.

## Split discipline (R7, §3.5)

- **Project-held-out + time-ordered**: group by `gh_project_name`, order by `gh_build_started_at`,
  hold out whole projects for validation/test, and never let a later build train a model evaluated on
  an earlier one. No random shuffling, no random k-fold.

# Independent Review Report — Selective Carbon-Aware CI/CD Research Artifact

**Review status:** independent, adversarial repository audit completed 2026-10-01. This report distinguishes recorded evidence at `HEAD` (`4d9e128`) from uncommitted proposals. It does not treat `Research_Artifact/dissertation/proposed solution.md` as research evidence: it is untracked and was not reviewed as anything other than a possible future proposal.

**Evidence labels:** **FACT** is directly observed in a tracked artifact or source code. **INTERPRETATION** is the examiner's inference. **LIMITATION** bounds a claim. **EXTRAPOLATION** is outside the evaluated regime. **UNVERIFIED** means it could not be independently established from the available repository/environment.

## 1. Executive Summary

The repository has a notably strong evidence trail: project-disjoint split assignment, stored results, provenance manifests, a fitted policy hash, test-opening sentinels, code-level blocklists, and a large test replay are all present and mutually consistent. The work also honestly records that the frozen policy is duration-only and that strategy ⑤ is identical to ④b.

However, the central duration control has a material information-availability defect. `causal_project_history()` includes a prior build whenever its **start** time is before the current build's start time; it does not require that the prior build had completed. A lower-bound audit of tracked `results/p3/test_trace.csv.gz` found 36,849 / 138,693 test builds (26.57%) whose immediately preceding, strictly earlier-started build in the same project was still running at their arrival. Its observed duration was therefore not available to a live decision at that time. This directly challenges the claim that ④b is a deployable, strictly causal online history and can affect the frozen policy, its operating point, and all P3 replay comparisons involving ④b/⑤.

**Overall judgement:** the project is an **acceptable research-software foundation with critical methodological revision required**. It currently supports a simulated, narrow, descriptive result about its recorded replay under the implemented information regime. It does not yet support a deployment-causal conclusion that duration history is available at commit time, nor a broad conclusion that SE features add no decision value beyond a live-available duration estimate.

## 2. Research Contribution

**FACT.** The active framing is a value-of-information study: whether commit-level SE characteristics add decision value beyond a duration control, followed by an evidence-derived scheduling policy.

**INTERPRETATION.** The most defensible contribution is not a new ML scheduler. It is a reproducible simulation framework and a negative/heterogeneous evidence finding: all six families were rejected on calibration, the full 28-feature arm is worse than the duration control, but F1 reverses direction and clears the predeclared model-level floor on test. That is an unresolved heterogeneity signal, not a settled universal null.

**LIMITATION.** Until the duration-history availability defect is corrected, even the baseline against which the SE features are judged is not operationally valid as implemented.

## 3. Research Questions

| RQ | Independent verdict | Reason |
|---|---|---|
| RQ1: which SE characteristics provide information? | **PARTIALLY SUPPORTED / INCONCLUSIVE** | F1 is positive on test (+0.013313 ΔPR-AUC) but negative on calibration; the other five are rejected. This cannot identify a stable family. |
| RQ2: do SE features add decision value beyond duration? | **PARTLY DESIGN-INDUCED NULL** | The frozen ⑤ has no SE input and is exactly ④b. The test proves zero incremental value for that frozen policy, not for F1 or for all possible SE policies. |
| RQ3: transformation into a policy | **SUPPORTED AS A REPRODUCIBLE FITTING PROCEDURE** | Calibration-only fitting, a frozen v2 policy, and a SHA-256 are evidenced. Operational validity remains contingent on fixing ④b. |
| RQ4: policy effectiveness against baselines | **SUPPORTED ONLY AS A SIMULATED, MODEL-CONDITIONAL COMPARISON** | Test replay is extensive and paired, but eligibility is not urgency ground truth, energy/carbon are estimated, and ④b is not yet live-available. |

## 4. Methodology Audit

**FACT.** The analytic set has 922,624 build-grain records from TravisTorrent; the split allocates 628/150/170 projects to train/calibration/test. Policy fitting was documented as calibration-only, test opening is recorded once, and the P3 test replay evaluates the same test records for each setting.

**STRENGTH.** The distinction between model altitude and decision altitude is unusually well articulated. Materiality floors and the frontiers were predeclared before P3 results. The project also documents calibration/test base-rate and duration shifts rather than hiding them.

**LIMITATION.** Project-disjoint is not temporal-forward: every split spans 2011–2016. Train parameters may therefore include observations later in wall-clock time than a scored calibration/test build. This is not direct project leakage, but it is future information for any claim of a historically deployable at-arrival system. The repository acknowledges this as an undirected residual asymmetry; it remains a validity threat rather than a resolved control.

**CRITICAL ISSUE — duration availability.** A scheduler deciding before a build runs knows only durations of runs that have completed. The implementation uses `gh_build_started_at < t_b`; it does not enforce `start_time + observed_duration <= t_b`. The test suite verifies the former condition, not the latter. The 26.57% lower bound above means this is a material, not hypothetical, breach of the stated deployment information regime.

## 5. Dataset and External Validity

**FACT.** The corpus comprises 3,881,992 job rows aggregated into 925,897 builds and cleaned to 922,624 analytic builds, with 25.0871% failures. It covers Python, Ruby, Java and Go; missingness is substantial in several raw columns. Two contracted features are constant and three are near-constant.

**LIMITATION.** Travis CI from 2011–2016 is a historically useful corpus, not evidence of behaviour in contemporary GitHub Actions. Its branch conventions, runners, caching, workflow graphs, trigger types, carbon locations, and duration distributions may differ materially.

**UNVERIFIED.** The raw multi-GB source dataset was not present in the repository workspace for this review. I verified its documented funnel, source paths, derived tracked artifacts, and code paths, not the raw CSV values themselves.

## 6. Leakage and Experimental Controls

| Control | Assessment |
|---|---|
| Current-build duration/outcome blocklist in feature/policy path | **STRONG**: source code rejects `tr_duration` / `tr_log_buildduration` at the decision interface and tests target injection. |
| Project-disjoint split | **STRONG**: frozen assignment digest `3d9a7947…`, 948 projects, reported partition checks pass. |
| Test protection/policy fitting | **STRONG**: policy manifest says `test_split_read: false`; test split/replay opening sentinels are tracked. |
| Same test population across strategy settings | **STRONG**: P3 reports 102 × 138,693 audited records and an identical-set check. |
| Within-project ④b history | **CRITICAL**: start-time causality is insufficient; incomplete prior builds are admitted. |
| Global fitted-parameter chronology | **WEAK** for a live temporal claim: train and scored splits overlap in time. |
| Calibration metrics | **LIMITED**: isotonic calibration is assessed in-sample on calibration, so the held-out test ECE is the meaningful calibration evidence. |

Required correction: use completed historical runs only, require a completion timestamp (or conservatively derive `started_at + duration < arrival` in retrospective replay), add tests for overlapping runs, regenerate ④b, re-fit the calibration operating point, and repeat every P3 result dependent on ④b. A time-forward evaluation should be added or claims narrowed accordingly.

## 7. ML and Statistical Audit

**FACT.** P3-T1 applies frozen arms to 138,693 test builds. It reports 1,000 paired-bootstrap resamples with seed 42 and test PR-AUC/ROC-AUC/Brier/ECE intervals. The full SE arm loses to the duration control under all three algorithms on test.

**F1.** F1 is an exploratory, unstable signal—not confirmatory evidence for adoption and not proof of no effect. It is -0.003678 [-0.005310, -0.001958] on calibration but +0.013313 [+0.011924, +0.014733] on test, crossing the +0.010 floor only in the latter. It disappears at the x2 materiality floor and has no decision-level policy/frontier test. Describing it as a non-replicating candidate is accurate; describing RQ2 as stably null is not.

**LIMITATIONS.** Family-level testing involves six comparisons without a multiplicity adjustment. The specified materiality rule mitigates but does not remove selection/interpretation risk. One XGBoost budget/inductive bias is used for family ablations; absent/constant features weaken the scientific question. SHAP describes contributions within a fitted full model; it does not establish causal importance or repair a rejected model.

## 8. RQ1 Audit

**PARTIALLY SUPPORTED.** The evidence supports that the all-feature full arms do not improve on the selected duration control on this test set. It supports that F2–F5 are adverse under the specified tests, and F6 is below the materiality floor. It does not support a stable answer to “which SE characteristics” because F1 changes sign between disjoint calibration and test projects, while the feature contract is weakened (two constants and missing textbook predictors).

Safer wording: “Under this feature contract and model budget, no SE family was admitted on calibration; a non-replicating F1 test signal remains unresolved.”

## 9. RQ2 Audit

**Verdict: C — partly a design-induced null.** The P3-T3 report correctly states that ⑤ ≡ ④b at every point and gives a zero area/zero matched-point increment. That is a useful integrity finding: the implementation did not manufacture a difference. But it makes the headline SE decision comparison uninformative by construction: ⑤ contains no SE signal to test.

The positive ⑤-versus-④a frontier only compares an expanding project-history prior with an SE-feature duration regressor. It supports a difference between those two duration-control implementations, not a benefit of SE characteristics. The claim “duration estimation is the lever” is therefore **PARTIALLY SUPPORTED**: better duration discrimination plausibly reduces unnecessary deferral in this simulation, but the comparison changes both the estimator form and the available per-project history. It is not a clean causal isolation of duration estimation, and the ④b availability defect is unresolved.

## 10. RQ3 Audit

**SUPPORTED WITH LIMITATIONS.** The policy derivation is transparent: calibration replay chose d ≥ 480 s and W = 24 h through the documented ρ = 0.90 rule, then froze `policy_spec.yaml`. The threshold is evidence-derived within this corpus, not a universal operational threshold. It is sensitive to the declared ρ values and must be re-derived after the required history correction.

## 11. RQ4 Audit

**FACT.** At the frozen point, ⑤/④b defers 7.92% of test builds; relative to static, replay estimates -2.480% gCO2e/1k builds and adds 1.017 h mean all-build latency and 12.21 h failed-build TTFF p95. Compared with blanket carbon-aware scheduling it trades less estimated carbon saving for far less modeled delay.

**LIMITATION.** These are not real-world savings, safe deferrals, or measured operational latency. They are outputs of a replay with a deterministic eligibility proxy, 24-hour window, a UK mean profile, constant-power energy, and the invalid-as-deployed ④b history.

## 12. Carbon and Energy Model Audit

**FACT.** The model uses 42.5 W, derived from CodeCarbon's constant-mode CPU fallback, `tr_duration`, an average UK hour-of-week profile from 2024–2025, and a ±50% power sensitivity. Carbon is linear in duration by design.

**ASSESSMENT.** The model is suitable for comparative, model-conditional estimates, not absolute emissions claims. It omits RAM/GPU/idle/ramp effects, runner heterogeneity, queueing, cache/refetch/re-dispatch energy, marginal emissions, and the energy of duplicated deferred executions. Applying 2024–2025 UK mean intensity to 2011–2016 Travis records measures simulated shiftability, not historical emissions.

Required language everywhere: “estimated carbon change under the replay energy and UK hour-of-week intensity model.” Do not say “carbon saving” without that qualifier in conclusions or product UI.

## 13. Scheduling and Eligibility Audit

**FACT.** The branch/PR gate prevents rule-defined non-deferrable records from being deferred in the replay; the independent validator reports zero rule violations.

**LIMITATION.** This is consistency with a heuristic, not safety. The corpus has no urgency/deferability ground truth. Manual and scheduled trigger classes are unavailable; the primary gate’s “eligible” set is an experimental approximation based on PR/branch fields. A live artifact must say “eligible under configured policy” and must default to recommendation-only.

## 14. P3 Validation

P3-T1 through P3-T5 are genuinely recorded in commits `1e38db7` and `4d9e128`. The test scores/trace, strategy results, frontiers, sensitivity outputs, reports, pytest transcripts, and opening sentinels are tracked. P3-T5 itself adds only synthesis/documentation, a test transcript, progress state, and generated guide state; it does **not** rerun the dataset, change models, modify policy, or add decisions.

**FACT.** The P3 reports state the second-grid sensitivity was not run for lack of a qualifying series. Thus cross-grid robustness is **UNVERIFIED**, not supported. Sensitivities within the one UK-profile regime are useful but cannot replace an independent grid.

## 15. Artifact / P4 Audit

**FACT.** No `api/`, GitHub Action, dashboard, workflow, Docker file, or production service exists in the tracked tree. P4 is not started. It cannot be credited for API parity, GitHub integration, production reliability, live carbon data, or security.

The old P4 specification conflicts with results: its 28-feature-only request cannot produce frozen ④b, whose decision requires a project’s completed duration history. It also promises a SHAP rationale while the frozen policy has no SE path. It must not proceed unchanged.

## 16. DevOps and Security Review

The deterministic core is a strong basis: configuration is parsed with safe YAML loading, fitted-spec loading defaults safely, inputs are range-checked, and replay has independent gate validation. Dependency lock and artifact hashes are present.

**UNVERIFIED / not implemented:** API authentication/authorization, rate limiting, audit retention, CORS, input size limits, secret handling, GitHub token permissions, PR-from-fork behaviour, workflow command injection, repository-ID validation, SSRF controls, Actions API pagination/rate-limit handling, completed-run selection, cache integrity, duplicate dispatch prevention, idempotency, SHA preservation, retry policy, concurrency, and failure-safe behaviour. These cannot be inferred from a future architecture.

The available environment also did not independently reproduce the claimed test run: the committed `.venv` points to a missing Python 3.11 executable; the available Python 3.13 lacks XGBoost. A targeted runnable test subset additionally has one failure in `eligibility.classify_frame` for `None` values (cache key mismatch after `MultiIndex.unique()` normalises missing values). This may be dependency-version-related—the active environment has pandas 2.3.3 while the lock says 3.0.3—but it is nevertheless a reproducibility/compatibility defect until a clean locked installation passes.

## 17. Reproducibility Review

**STRONG:** tracked test inputs/outputs, seed declarations, fitted policy SHA-256 `34d689c9…07da3`, split SHA-256 `3d9a7947…5cde`, policy-fit manifest, test-opening sentinels, tests, commands, and Git history.

**WEAK:** the raw dataset is external/unavailable here; untracked replay decision files are only hash-pinned; runtime verification failed in the available environment; model binaries are pickle/joblib version sensitive; and the local branch is divergent from `origin/main`. Results are reproducible in principle but not independently reproduced in this audit.

## 18. Claim Audit

| Claim | Classification | Evidence/problem | Safer wording |
|---|---|---|---|
| “SE features add no decision value beyond duration.” | **PARTIALLY SUPPORTED** | ⑤ has no SE input; F1 is positive on test but untested at decision level. | “The calibration-frozen policy realised no incremental SE decision value; F1 remains unresolved.” |
| “⑤ beats ④a.” | **PARTIALLY SUPPORTED** | It compares two duration controls; ④b has an availability defect. | “In this replay, start-time-history ④b has a better frontier than ④a at several points.” |
| “Duration estimation is the lever.” | **PARTIALLY SUPPORTED** | Difference confounds estimator form and history access. | “Duration selectivity is associated with a better simulated trade-off under the tested controls.” |
| “The policy saves carbon.” | **EXTRAPOLATION** | Constant 42.5 W and UK mean-profile replay. | “The policy reduces estimated modeled operational carbon in replay.” |
| “Eligible builds are safe to defer.” | **UNSUPPORTED** | No urgency/deferability labels. | “Builds are eligible under an unvalidated branch/PR proxy.” |
| “Modern CI/CD usefulness.” | **EXTRAPOLATION** | Travis 2011–2016, not GHA. | “A hypothesis for a modern-CI pilot, requiring fresh validation.” |
| “F1 is meaningful.” | **PARTIALLY SUPPORTED** | Test effect meets one floor, but reverses calibration and lacks decision evaluation. | “F1 is an exploratory non-replicating signal.” |
| “The artifact implements the finding.” | **UNSUPPORTED today** | P4 code does not exist. | “P4 is proposed; the shared replay core embodies the frozen policy.” |
| “Regional/forecast operation is validated.” | **UNSUPPORTED** | One UK hour-of-week profile; no live endpoint evaluated. | “Any forecast or non-GB mode is explicitly extrapolated.” |
| “Strictly causal duration history.” | **UNSUPPORTED / CRITICAL** | Start-time check admits not-yet-completed predecessor runs. | “Start-time-ordered retrospective history; completion-time causality remains unproven and currently fails.” |

## 19. Major Threats to Validity

1. **Critical:** duration-history look-ahead from overlapping builds.
2. Temporal overlap between training and scored builds undermines a forward-deployment interpretation.
3. No deferability/urgency ground truth.
4. A narrow, old TravisTorrent population and only four languages.
5. Weak/degenerate SE feature contract and absent predictors.
6. Carbon/energy are estimated, average, and non-contemporaneous.
7. The principal RQ2 decision null is structurally forced by the frozen fallback.
8. F1 sign flip and no decision-level replication.
9. Second grid sensitivity not run.
10. P4 operational/security claims remain unimplemented.

## 20. Examiner / Viva Attack Questions

| Question | What it tests | Current answer / required change |
|---|---|---|
| Why should I believe a null when ⑤ equals ④b? | Construct validity | I should not call it a general SE null; state it is a frozen-policy null and test F1 prospectively. |
| How can ④b know a prior run's duration before it completes? | Leakage | It cannot. Correct completion-time history and rerun dependent phases. |
| Why did F1 flip from negative to positive? | Heterogeneity | Project/distribution heterogeneity is plausible but unproven; replicate on a new temporal/project cohort. |
| Why is 480 seconds justified? | Post-hoc tuning | It is calibration-fit under ρ=0.90, not universal; re-fit after correction. |
| Why TravisTorrent? | Dataset validity | It offers build-level historical data; do not generalise to modern GHA. |
| What proves safety to defer? | Operational safety | Nothing; the gate is an unvalidated proxy. Keep recommendation-only. |
| Are savings real? | Carbon validity | No, they are simulated estimates under stated assumptions. |
| Why a UK profile for old Travis builds? | Non-contemporaneity | It models a counterfactual modern-grid shape, not historical emissions. |
| What if intensity changes tomorrow? | Live usefulness | The evaluated policy is not forecast-validated; forecast mode is future extrapolation. |
| Why only one grid? | Robustness | The planned second grid was not run; this is unresolved. |
| Why do PR-AUC and ECE change? | Distribution shift | Held-out projects have different base rates; report it as degradation, not stability. |
| Is calibration valid when isotonic saw calibration data? | Calibration | Only test ECE is out-of-sample; use it. |
| What does SHAP prove? | Interpretability | Association inside one model only; it does not prove a causal feature effect. |
| Why not use actual duration? | Information regime | It is unavailable at decision time; but completed historic duration must be used correctly. |
| Does project-disjoint equal temporal-safe? | Leakage | No; splits overlap in time. Add forward-temporal validation or narrow the claim. |
| Why is ④b better than ④a? | Causal attribution | It may be better history information, but the comparison is confounded and currently look-ahead prone. |
| Can the Action pause a job? | Artifact credibility | No. Only documented recommendation or re-dispatch is possible. |
| How will GHA history map to Travis duration? | Construct transport | It does not directly; this is a separate, unvalidated operational construct. |
| What happens with no history/API/carbon data? | Reliability | No implemented answer yet; require fail-closed run-now and auditable fallbacks. |
| What remains after the null? | Contribution | A rigorous value-of-information attempt plus reusable simulation/provenance framework, conditional on correction. |

## 21. Required Changes Before Submission

1. Fix the ④b information regime to completed runs, add overlap tests, and rerun/re-freeze P1–P3 results that depend on it.
2. Add a temporal-forward robustness evaluation or remove “commit-time/deployable” language where it implies temporal deployment.
3. Recast RQ2 as a frozen-policy result; explicitly isolate the F1 unresolved signal and do not call the broader null stable.
4. Reconcile all P4 documents through an accepted decision-log amendment before implementation; do not implement the obsolete 28-feature contract.
5. Build and validate a clean locked environment on the declared Python version; fix the missing-value eligibility failure and record a fresh test transcript.
6. For any P4 implementation, specify least-privilege GitHub permissions, authentication, trusted event policy, history completion semantics, idempotent re-dispatch, rate limits, retries, and fail-safe `run_now` behaviour.

## 22. Overall Independent Assessment

| Dimension | Assessment |
|---|---|
| Research validity | **ACCEPTABLE WITH LIMITATIONS**, becoming **CRITICAL** if the duration availability defect is not corrected |
| Methodological validity | **WEAK** until completion-time causality and temporal deployment claims are resolved |
| Statistical validity | **ACCEPTABLE WITH LIMITATIONS** |
| Reproducibility | **ACCEPTABLE WITH LIMITATIONS** |
| Artifact quality | **WEAK** — core exists, P4 does not |
| DevOps/security quality | **UNVERIFIED / WEAK** — no operational artifact exists |
| Academic contribution | **ACCEPTABLE WITH LIMITATIONS** |
| External validity | **WEAK** |

### If I were the examiner, the five things that would most worry me

1. The prior-duration look-ahead makes the purported live duration control non-causal.
2. The claimed RQ2 null is structurally induced because ⑤ is exactly ④b.
3. F1 contradicts the calibration null but is neither replicated nor evaluated at decision level.
4. Eligibility is not measured safety, and carbon is not measured emissions.
5. The proposed operational artifact is not implemented and has unresolved transport/security questions.

### The five changes that would most improve the research

1. Correct the duration-history information boundary and rerun the affected evidence chain.
2. Add a genuinely temporal-forward holdout or clearly scope the study as cross-project retrospective replay.
3. Write a precise revised RQ2 conclusion separating frozen-policy null from general SE value.
4. Adopt a narrow, GB-only, recommendation-only P4 contract with completed history and explicit extrapolation labels.
5. Demonstrate a reproducible clean environment and a small modern-CI transport/pilot validation.

## 23. Evidence and Provenance Appendix

### Repository state at review start

- `HEAD`: `4d9e128c7a075ea6d038b6cbb36427428e251705` on `main`.
- Status: `main...origin/main [ahead 5, behind 3]`; modified `03_DECISION_LOG.md` and `PROGRESS.md`; one untracked file, `Research_Artifact/dissertation/proposed solution.md`.
- Merge base with `origin/main`: `95c6d6d`. The local and remote histories contain parallel commits for the independent report/briefing/guide, so branch provenance must be reconciled before release.

### What P3-T5 actually contains

`4d9e128` changes exactly five paths: `results/p3/evaluation_report.md` (new), `results/p3/pytest_p3_t5.txt` (new), and updates to `planning/PROGRESS.md`, `docs/research_state.json`, and `docs/research_guide.html`. It contains no dataset read, model/replay run, frozen-policy change, source-code change, or decision-log entry. The P3 numeric evidence is in parent checkpoint `1e38db7`.

### Relevant checkpoints

- `7a3c33e` P1-T3 frozen project-disjoint split.
- `facbd20` P1-T4 duration control and stated leakage proof.
- `45a07af` P1-T5 six model arms.
- `f46c3b1` P1-T6 ablation and SHAP.
- `2901d77` P1-T7 calibration admission null.
- `95c6d6d` P2-T5 fitted/frozen policy.
- `1e38db7` P3-T1 through P3-T4 test/sensitivity checkpoint.
- `4d9e128` P3-T5 synthesis checkpoint.

### Frozen/critical artifacts observed

| Artifact | SHA-256 |
|---|---|
| `results/p0/eval_protocol.md` | `ddcc86ecdc58b6cbb1273f7dc709f9e35496857b619b6a7c03c406ca97b17876` |
| `results/p1/splits.json` | `441a9ae8c27bf79246e3a0b4071504dbdc9ce5bed203ee0a4dfedf33a3615f38` |
| `results/p1/split_assignment.csv` | `be1d175f138139df4eece6c10a04e05498fbdbf5daf8fd2c2f0d9af96ddf26d3` |
| `results/p2/policy_fit/manifest.json` | `6300a5d03ea8b1c159d85b756b45c8a5764c9142ad289291246a7ad286d331a7` |
| `code/scheduler_core/config/policy_spec.yaml` | `34d689c9fae03345e6964da97f74d8668c3766643f5696b8c1af73df92107da3` |
| `results/p3/model_report.json` | `0b902c8ed365e4022c345b41c65d49a0a72094885629975418657a4e9456abbb` |
| `results/p3/strategy_results.json` | `f6679d4940be6bd173c817466528771d108f47c43343816779ffff8e60698900` |
| `results/p3/incremental_value_decision.json` | `3e128a369e6ee35391394ac886facd7560071e074c6d6dd829849e35faf82bea` |

### Decision-log history relevant to this review

DL-006 controls project/time split; DL-012/013 set the value-of-information/frontier frame; DL-014 governs ④b; DL-015/016 describe weakened features; DL-018/019 set model/ablation configuration; DL-020 defines eligibility as an approximation; DL-021 sets 42.5 W; DL-023/024 define strategies and policy fitting; DL-026 is a proposed conditional P4 direction; DL-027–032 govern P3 sensitivity/test treatment.

DL-033 exists only as an **uncommitted modified decision-log proposal** at review time. It properly identifies the old 28-feature contract contradiction and proposes GB-only, duration-history, recommendation-first design. It is **not research evidence and is not binding** until the author accepts it.

### DL-033 assessment

DL-033 is sufficient to reject the obsolete P4 direction and gives a good conceptual correction. It requires amendment before acceptance because it repeats the claim that start-time-ordered ④b is “strictly earlier build history”; it must require **completed** history, specify a completion timestamp/availability contract, and force re-evaluation after correction. It should also add a concrete least-privilege/security and idempotency contract for the Action/API. P4 should **proceed only with these modifications after an accepted amendment**, not unchanged.

### Audit commands and limits

This review inspected Git history/status, tracked artifacts, hashes, manifests, decision logs, source code, tests, and the tracked test trace. A direct lower-bound overlap calculation on that trace produced the 36,849 / 138,693 figure (strict timestamp ties excluded). Python compilation completed. Full test reproduction was not possible in the available environment because the committed virtual environment is broken and the available interpreter lacks XGBoost; a runnable targeted suite exposed the missing-value eligibility failure described above. No research implementation, frozen artifact, protocol, decision, or untracked proposal was modified.

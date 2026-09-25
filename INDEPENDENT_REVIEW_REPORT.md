# Independent Blind Review: Selective Carbon-Aware CI/CD Research Artifact

**Review date:** 2026-09-13  
**Reviewer stance:** critical academic examiner and senior DevOps/software engineer  
**Scope reviewed:** active research framing and frozen provenance, protocol, development plan and progress record, decision log, P0/P1 outputs, source and tests, and the supplied paper drafts. This is a review of the repository state, not an endorsement of its intended result.

## Executive verdict

The project has a potentially defensible contribution even if RQ2's null is confirmed. That contribution is **not** “an intelligent SE-aware carbon scheduler.” It is a bounded, reproducible value-of-information result: *on the specified TravisTorrent population, with the measured feature set, a causal per-project expected-duration control is sufficient; adding the tested commit-level SE families does not provide material incremental value for the stated scheduling decision.* The practical implication would be to avoid collecting, maintaining, calibrating, and explaining a more complex SE-feature model when a repository’s own duration history supports a simpler policy.

That is meaningful, but much narrower than several passages in the paper and prototype plan imply. The strongest artifact after a confirmed null is a **minimal duration-based carbon-deferral guardrail**, with an explicit “insufficient evidence for SE scoring” mode—not an SE dashboard and not a tool claiming to know which commits are safe or urgent.

At present, the null is **not confirmed**. P1 gives strong *calibration-split, model-level* evidence against the tested SE families, but the frozen policy has not been built, the held-out test split has not been evaluated, and the required ④-vs-⑤ decision-frontier test has not happened. It would be academically incorrect to state that RQ2 is answered conclusively today.

## What the current evidence demonstrates

The following statements are supported by completed P0/P1 materials.

1. The study has a reasonably serious leakage discipline at build grain: 922,624 analytic builds from 948 projects, project-disjoint train/calibration/test partitions, causal project-history duration estimates, and an explicit outcome-feature blocklist. The recorded P1 results and tests document those controls.

2. The primary duration control is the causal expanding per-project prior (④b), selected before test evaluation using calibration log1p MAE. On calibration it materially outperformed the SE-feature duration regressor: log1p MAE 0.601 versus 1.178 and Spearman correlation 0.869 versus 0.526. This makes “expected duration” a credible and demanding baseline in this dataset, not a straw man. Source: `Research_Artifact/results/p1/duration_control.md`.

3. On the calibration split, the complete SE arm failed to beat the duration-only control for all three implemented classifiers. The primary XGBoost full arm had lower PR-AUC (0.329 vs 0.390), lower ROC-AUC (0.540 vs 0.651), and worse Brier score (0.202 vs 0.192). Source: `Research_Artifact/results/p1/calibration/brier_ece_table.md`.

4. The family analysis is directionally more damaging to the SE hypothesis: each of the six standalone SE families had negative paired ΔPR-AUC versus duration-only, and every reported bootstrap CI excluded zero in the negative direction. No family passed even the half-floor admission sweep; P1-T7 consequently selects the `duration_only_fallback` path. Sources: `Research_Artifact/results/p1/ablation/ablation.md` and `Research_Artifact/results/p1/incremental_value.md`.

5. The dataset does not deliver a fair test of every intended SE construct. Two contracted features are constant, two cited predictors are unavailable, and F2 is especially weakened by constant/near-constant members. The correct interpretation is therefore “no value from the available operationalisation in this corpus,” not “SE characteristics can never help.” Source: `Research_Artifact/results/p1/feature_audit.md` and DL-015/DL-016.

## What can reasonably be inferred if the null is confirmed on the frozen test protocol

If P3 reproduces the negative result and the duration-only frontier is not materially dominated by the SE policy, the defensible inference is:

> For historical Travis CI builds in the defined population, using this feature contract and decision policy, committing resources to an SE-enriched decision layer is not justified beyond a causal per-repository duration estimate and deterministic eligibility rules.

This has three useful implications:

- Prefer an observable, low-maintenance duration-history policy before building a feature store, model-training loop, calibration process, SHAP explanation interface, and governance apparatus for SE features.
- Treat an SE feature model as an optional future candidate requiring evidence on a richer/current dataset, not as a default prerequisite for carbon-aware CI.
- Preserve the failed treatment and exact protocol as a replication baseline; it prevents future work from presenting a duration-uncontrolled SE result as novel decision value.

This is a negative empirical contribution, not a null-free “success story.” It would be valuable primarily because it rules out unnecessary complexity under clearly stated conditions.

## What is only future application or an unsupported claim

The following must not be claimed from the current study, even if the null is confirmed.

| Claim | Assessment |
|---|---|
| “The artifact knows which builds are safe to defer.” | Unsupported. The data have no ground-truth urgency/deferability label. Failure probability and TTFF are proxies, not developer-approved delay tolerance. |
| “SE characteristics are useless for carbon-aware CI/CD.” | Unsupported generalisation. The corpus is TravisTorrent (2011–2016), feature availability is degraded, and the evaluated algorithms/budget are bounded. |
| “The artifact reduces a team’s real emissions/productivity impact.” | Future application only. The evaluation is replay simulation using a 2024–2025 UK hour-of-week profile, not a deployment study with measured CI energy, queues, cancellations, developer outcomes, or grid forecasts. |
| “Duration-only is optimal.” | Unsupported. It may be adequate or not materially worse on this protocol; many untested decision signals and scheduling mechanisms remain. |
| “The dashboard proves usefulness.” | Unsupported. A dashboard visualises policy outputs; it does not validate causal operational benefit. |

## Does the research still solve a meaningful problem?

Yes, but the problem needs precise wording:

> **Problem solved:** a team considering selective carbon deferral lacks evidence on whether it should add a commit-metadata/failure-risk ML layer beyond repository-local expected build duration. The study supplies an evidence-based simplification decision for that design choice.

It does **not** solve the broader problem of deciding whether a specific real-world build is organisationally safe to delay. The current Stage-1 eligibility gate is a heuristic approximation because the dataset lacks release, hotfix, nightly, business-priority, merge-queue, and explicit developer-urgency information. That limitation is central, not incidental.

The research remains worthwhile because the cost avoided is concrete: data plumbing, permissions, model drift, calibration, monitoring, false certainty, explanation burden, and an additional failure mode in a CI-critical path. However, it is a decision about **scheduler design complexity**, rather than a demonstrated production carbon-saving intervention.

## Main skeptical-viva weakness

The strongest skeptical criticism is a construct-validity challenge:

> “Your target is not deferability. You infer the cost of a delay largely from build failure feedback and use PR/branch heuristics for eligibility, but neither is the developer’s actual urgency, business impact, or willingness to defer. Why should a model that predicts failure—or fails to improve that prediction—answer which builds are suitable for carbon-aware scheduling?”

This is stronger than a generic “one old dataset” criticism. It goes to the causal bridge between the measured model target and the claimed decision. A failed build can be non-urgent; a passing build can be release-critical; a long build can be on a critical path; and a developer may care about feedback on passing tests too. TTFF p95 is a defensible operational proxy, but it does not validate the suitability construct by itself.

Additional serious weaknesses:

1. **Decision-level answer remains pending.** Model PR-AUC admission is a proxy for the actual frontier question. The central RQ2 claim requires P3’s frozen, matched-frontier test—not merely P1’s negative model metrics.
2. **External and temporal validity are weak.** Old Travis CI behaviour is combined with a recent UK carbon profile aligned by hour-of-week. This can estimate a scenario, not reconstruct historical emissions or prove GitHub Actions applicability.
3. **Control asymmetry and distribution shift.** ④b has rich causal within-project history, while SE models are trained on other projects. This reflects one plausible deployment regime, but must not be described as an unbiased generic comparison. Calibration has a 4.2 percentage-point higher failure rate and much longer duration tail than test.
4. **Feature operationalisation is limited.** Constant test-churn fields, unavailable commit messages/entropy, sparse proxies, and a 20-candidate XGBoost search make a null a lower-bound result. They do not invalidate a positive result, but they constrain a negative one.
5. **Carbon channel is structurally constrained.** The protocol correctly recognises that carbon is proportional to duration under its energy model; therefore RQ2’s discrimination rests mainly on the TTFF proxy. Do not oversell carbon estimates as independent evidence of SE decision value.

## Practical artifact review

### Is the planned artifact useful today?

Not yet. The implemented repository contains data, features, split, duration-estimation, modelling, ablation, and admission components. The actual eligibility gate, accounting, `decide()` policy, replay simulator, frozen policy specification, REST API, GitHub Action, and dashboard are planned P2–P4 deliverables. Thus there is no deployable developer tool at this point.

Even if P4 is implemented exactly as planned, the API + GitHub Action + dashboard combination risks being principally a **research demonstration**:

- It asks for a 28-feature request schema although a confirmed null says those features should not drive the decision.
- It relies on a duration-history mechanism that must be integrated with real CI-run history; the operational storage, cold start, retry/cancellation handling, concurrency, queue effects, and permissions are not yet demonstrated.
- GitHub Actions “deferral” is re-dispatch, not pausing a queued job. That is a legitimate demo mechanism but operationally different and may duplicate runs or complicate checks/statuses.
- A dashboard with SHAP rationales is actively misleading on the null path: the model was rejected as a decision input.

### What it should do after a confirmed null

It should make one narrowly useful decision: **for an already-approved, deferrable workflow, use only its causal duration history and a live/forecast carbon window to recommend or execute a bounded deferred re-dispatch; otherwise run now.** It should log the rule, duration estimate, history coverage, carbon window, imposed delay, and eventual outcome. It should explicitly state that no SE-feature model is used because the study did not demonstrate incremental benefit.

The tool must make the human/team own the urgency policy. For example, workflows, branches, labels, environments, and maximum permissible delay should be configured by the team—not inferred from historical failure data.

## Artifact designs faithful to a null result

| Design | Real user and problem | Workflow / inputs | Outputs and research demonstration |
|---|---|---|---|
| **1. Duration-based CI deferral guardrail (recommended)** | DevOps/platform engineer who wants low-risk carbon shifting without maintaining ML. Problem: choose a bounded green window for workloads the team has already declared deferrable. | GitHub Action or CI wrapper reads workflow policy, branch/label eligibility, current/forecast carbon intensity, and a local causal store of completed durations for that workflow/repository. | `run now` or `defer until`, reason, expected duration, history sample size, forecast comparison, max-delay status, auditable event log. Demonstrates the null by intentionally having no SE model. |
| **2. Carbon-deferral policy linter / advisor** | CI owner deciding whether a repository is ready to use carbon-aware deferral. Problem: unsafe configuration and no evidence of enough duration history. | Offline CLI ingests CI history export plus a proposed policy. It checks history coverage, duration stability, cold-start rate, max delay, branch/workflow exclusions, and forecast availability. | Readiness report, suggested conservative thresholds, warnings such as “insufficient history—run immediately,” and a generated policy file. Demonstrates that duration-history sufficiency, not SE-feature scoring, is the operative requirement. |
| **3. Replay-and-procurement evaluator** | Engineering manager/platform architect comparing “simple duration policy” to a vendor/ML proposal. Problem: deciding whether extra data/model complexity has demonstrated value. | Upload/export CI trace and carbon series; select candidate policies, delay caps, and team-defined eligibility. Run identical-trace replay. | Matched carbon-vs-latency frontier, coverage/uncertainty report, and a go/no-go recommendation for adopting a complex model. Demonstrates the study as a value-of-information evaluation method, not as a live scheduler. |
| **4. Team-governed deferral queue** | A release engineer managing non-urgent scheduled jobs (nightly tests, dependency refreshes, docs builds). Problem: shift explicitly flexible jobs while guaranteeing deadlines. | CI submits jobs with a team-selected class and deadline; service checks carbon forecast and duration-history estimate, then dispatches before deadline. | Queue/dispatch decision, deadline guarantee status, estimated carbon comparison, and audit trail. Demonstrates a safer real-world boundary by collecting actual deferability rather than pretending to infer it. |
| **5. Null-result observability module** | Research-aware DevOps team trialling a duration-only policy. Problem: detect whether local evidence later contradicts the study. | Log actual duration, delay, workflow class, cancellation/rerun, and optional developer override/reason. Periodically compare duration-only outcomes to a shadow SE candidate without actuating it. | Drift/coverage report and a trigger for a new preregistered evaluation. Demonstrates the bounded nature of the finding and avoids treating it as permanent truth. |

## Recommended direction: duration-based CI deferral guardrail

Choose Design 1, augmented by the policy-linter checks from Design 2. It is the most coherent final artifact because it:

- directly instantiates the null-policy conclusion rather than concealing it;
- has a real operational owner (platform/DevOps) and a clear, bounded job;
- requires far fewer fragile inputs than the planned SE-feature API;
- preserves the two-stage distinction: team-configured eligibility/urgency first, duration-and-carbon scheduling second;
- can be demonstrated end-to-end with an auditable action log rather than a decorative dashboard; and
- gives a useful falsifiability hook: teams can observe whether duration history is adequate and whether policy assumptions hold.

The dashboard should be optional and operational: queue state, decision audit, history coverage, missed deadlines, forecast error, reruns/cancellations, and estimated—not asserted—carbon change. Remove SHAP from the default null-path interface.

## Changes required before final-artifact implementation

These are interpretation and implementation changes, **not** post-hoc changes to experimental criteria.

1. **Do not call the final product SE-informed if the null survives P3.** Make the duration-only fallback the product, not merely an invisible fallback inside a nominally SE-informed system.
2. **Revise the live input contract.** A null-path API should accept explicit policy/eligibility metadata, workflow identity, repository history reference, carbon forecast, and deadline/max delay. It should not require all 28 research features.
3. **Make urgency an explicit human/team policy input.** Add workflow/branch/environment/label allowlists and maximum delay/deadline. State that the artifact does not infer urgency from failure likelihood.
4. **Define operational semantics before coding.** Specify what “defer” means in GitHub Actions, idempotency, cancellation, duplicate-run prevention, artifact/commit SHA preservation, permissions, re-dispatch reliability, and what happens when the deadline or forecast service fails.
5. **Add deployment-relevant telemetry.** Record duration estimate, historical sample size, actual duration, forecast versus realised intensity when available, decision, override, cancellation, and queue/deadline result. Carbon output must be labelled estimated.
6. **Finish P2/P3 before presenting product claims.** In particular, preserve the frozen P3 decision-frontier test and report its result plainly. P1 admission must not be substituted for it.
7. **Reconcile the write-up.** `final paper.md` still contains draft-like language, inconsistent headings, and broad claims that do not consistently reflect Layer 0-A/DL-012. The dissertation should use the active RQs, distinguish simulation from deployment, and remove any claim that the model determines actual deferrability.
8. **Repair reproducibility before the final demonstration.** This checkout’s `.venv` points at a missing Python executable. Running the suite with the available interpreter and a workspace base temp exposed missing `xgboost`, producing 21 failures and 32 errors; the failures are environment/dependency failures rather than evidence that the historical recorded P1 run was invalid. Recreate the documented locked environment and rerun the complete suite before claiming the final artifact is reproducible.

## Likely viva questions and academically honest answers

**“What problem did your research solve?”**  
It solved an evidence problem in selective carbon-aware CI design: whether collecting and modelling commit-level SE characteristics is justified beyond causal expected build duration when deciding which pre-approved CI workloads may be delayed. In the null case, the answer is that the added SE layer was not justified in the evaluated setting; a duration-history policy is the simpler defensible choice.

**“Did you solve carbon-aware scheduling?”**  
No. I evaluated a selection/policy component through replay simulation. I did not design a new scheduling optimiser, measure real infrastructure emissions, or demonstrate production-wide carbon reduction.

**“If the model did not improve results, why is this a contribution?”**  
Because the comparison is against a strong, causal duration control rather than against no baseline. The study rules out a specific additional complexity under a preregistered-style protocol and gives practitioners a simpler policy to evaluate first. The contribution is evidence against unnecessary model complexity, not a claim that nothing can improve scheduling.

**“Does the null mean software-engineering characteristics are useless?”**  
No. It means the tested operationalisation did not show material incremental decision value in this dataset and protocol. Important features were unavailable or degenerate, and the study does not cover modern CI systems, all models, or organisational urgency signals.

**“How do you know a delayed build was actually safe to delay?”**  
I do not know from TravisTorrent alone. The dataset does not provide a deferability or business-urgency label. I operationalised harm through eligibility heuristics and time-to-failure-feedback, so the result concerns that proxy. A production artifact should require teams to declare eligibility and deadlines explicitly.

**“Why not use actual build duration?”**  
Because it is known only after the build runs and would leak the outcome into the decision. The deployment-realisable control is a causal expected-duration estimate based on history available at decision time.

**“Why trust the duration baseline?”**  
I do not claim it is universally optimal. It was transparently specified, leakage-tested, and substantially stronger than the fitted SE duration regressor on calibration. Both duration forms still require held-out decision-level evaluation, and error/cold-start limitations are reported.

**“What would a real engineer use?”**  
They should use a duration-based deferral guardrail for explicitly flexible workflows, with team-owned delay caps and audit logging. They should not use a failure-risk score as a surrogate for business urgency.

**“Why is your carbon result only a simulation?”**  
The historical CI traces and the modern UK carbon profile are not contemporaneous, and the energy model estimates power from duration. Therefore the study estimates comparative scenarios. It does not measure a deployment’s actual energy, marginal grid emissions, or developer productivity.

## Final examiner judgement

The project is strongest when it is modest: a carefully controlled empirical challenge to the assumption that more commit metadata and ML necessarily make selective carbon-aware CI decisions better. A confirmed null would be an academically acceptable result and could lead to a useful small artifact.

It is weakest when it describes a failure-risk/duration proxy as if it discovers real deferability, or when a dashboard is presented as operational validation. The final submission should make the null policy visible, require human/team ownership of urgency, complete the locked P3 decision-level evaluation, and state exactly the population, features, proxy outcome, and simulation assumptions to which its conclusion applies.

---

# Addendum — 2026-09-20: dataset age, carbon-data validity, and the final artifact

**Added:** 2026-09-20, at the P2-T2 gate (13/28 tasks; P3 not started, test split still unopened).
**Prompted by three author questions:** (1) is TravisTorrent's age a viva liability, and should it be declared as a limitation? (2) is the UK-only, 2024–2025 carbon series defensible given it is not contemporaneous with the trace and covers one region? (3) what will the artifact actually be, and is it practical, achievable and valuable enough to demonstrate the research to a panel?

**Standing:** this addendum is opinion and recommendation. It changes no frozen clause. Two of its recommendations would change the evaluation plan, and under R4 those must be dated decision-log entries **before** they are acted on — and, under the "fit before you look" rule, **before P3-T1 opens the test split**. That deadline is two tasks away, which is why they appear here rather than after P3.

## A. Is the age of TravisTorrent a problem?

### The facts, as the repository records them

| Property | Value | Source |
| :-- | :-- | :-- |
| Release | `final-2017-01-25` | `results/p1/splits.json` |
| Build trace span | **2011-04-16 → 2016-08-31** | `results/p1/splits_summary.md` |
| Age of the newest build at submission | ~10 years | derived from the above |
| Analytic population | 922,624 builds / 948 projects | `results/p1/feature_audit.md` |
| Language mix | python 336,815 · ruby 272,081 · java 200,026 · go 113,702 | `results/p0/data_profile.md` |

### Verdict: declare it, but do not lead with an apology

It is already declared. Spec §6 (External validity) states that "TravisTorrent reflects Travis CI and a particular era/language mix; generalisation to modern GitHub Actions is limited and not claimed." So the panel risk is **not an undisclosed limitation** — it is the quality of the answer when the question is asked. A candidate who concedes "yes, it is old" and stops has lost the exchange. There are three arguments available, and the second is much stronger than most candidates realise.

**1. The decision under test is structurally era-invariant.** The question is whether commit-level SE metadata adds decision information *beyond a repository's own duration history*. Both inputs exist identically in Travis 2013 and GitHub Actions 2026: every CI system records how long its builds took, and every commit has churn, file counts and authorship. Era changes the *magnitude* of durations and the language mix; it does not change the *structure* of the comparison. To damage the finding, a critic must supply a mechanism by which era changes the **answer**, not merely the setting. That is a much harder argument to make, and the burden is correctly on them.

**2. The strongest argument, and the one to lead with: you are testing the claim on the corpus that produced the claim.** Much of the build-outcome-prediction literature this study is arguing with was itself established on TravisTorrent. A null obtained on a *different, newer* corpus is trivially deflected — "different data, different result." A null obtained on the *same* corpus, against a duration control the prior work did not include, is a direct challenge to that literature on its own ground. Choosing a newer dataset would have **weakened** the contribution, not strengthened it. Frame the corpus choice as *deliberate and load-bearing*, not as a fallback.

**3. The choice is also forced.** The study needs, simultaneously and publicly: commit-level SE features, a build outcome label, a build duration, a timestamp, and a project identity, at a scale where 10⁻² effect sizes are detectable. TravisTorrent remains the only openly available corpus meeting all five at ~10⁶ builds. "I used the only public dataset that supports the design" is a complete answer, but it is the *third*-best one — keep it in reserve.

### The concession that must be made honestly

The sharp form of the age criticism is not "the numbers are stale." It is this:

> The single most deferrable workload class in a modern pipeline — scheduled/nightly jobs — barely existed in this era, and **DL-020 already records that it has no marker in this release at all.**

That is the real cost of the dataset's age, and it compounds the study's largest construct-validity hole rather than sitting beside it. DL-020 states the deferrable set consists *entirely* of class (f), non-blocking pushes to non-protected branches — i.e. the hardest, most marginal part of the deferrable population, with the easy wins structurally absent. Say this before the panel does. It is a genuinely strong move: it demonstrates that the limitation is understood at mechanism level, and it sets up the correct reading of the carbon numbers as a **conservative floor** rather than an estimate.

Related era effects worth naming in one sentence each: build matrices and container/cache reuse have changed duration distributions; merge queues and required status checks have changed what "blocking" means; monorepo patterns have changed churn semantics.

### Recommended mitigation — a within-corpus temporal robustness sweep

Cheap, entirely in-corpus, and it converts the weakest point into a measured result.

**Proposal:** partition the trace by build date (e.g. an early period vs. builds from 2015-09 onward), re-apply the frozen admission rule within each period, and report whether the admitted set and the ④-vs-⑤ frontier verdict are stable across them. If the null holds across five years of Travis's own evolution — a period covering substantial change in CI practice — that is *direct, in-corpus evidence* that the finding is not an artefact of one era. It answers the age question with a number instead of a concession.

**Design care required.** The frozen split is project-disjoint and **not** time-disjoint — `splits_summary.md` §50 records that all three splits span 2011-04-16 → 2016-08-31 end to end. A date slice therefore cuts across the existing partition rather than aligning with it. The sweep must either run inside train + calibration only, or be declared in advance as a stratification of the test evaluation. Either way the stratification boundary must be fixed **before** any test number is seen.

**Status:** not currently in the plan. Belongs in P3-T4 alongside the existing deferrable-fraction sweep. **Requires a DL entry before P3-T1.**

## B. The carbon data: not contemporaneous, one region, and a mean profile

This is three separate criticisms bundled into one question. They have different strengths and different answers, and conflating them will cost marks.

### The facts, as the repository records them

| Property | Value | Source |
| :-- | :-- | :-- |
| Provider | National Grid ESO / NESO Carbon Intensity API, national series | `code/data/carbon/PROVENANCE.md` |
| Span | 2024-01-01 → 2026-01-01 (exclusive); coverage 99.83% / 100.0% | same |
| Alignment | 168-slot hour-of-week mean profile, 168/168 slots populated | `results/p0/carbon_profile.md` |
| Gap between trace end and carbon start | **~7 years 4 months** | derived |
| Slot-mean range | **92.2 … 172.9 gCO₂/kWh**, overall mean 127.1 | `results/p0/carbon_profile.md` |
| Greenest / dirtiest slot | Sun 11:00 / Wed 18:00 | same |
| Per-build ceiling under *perfect* shifting | **−46.66%** | `results/p2/energy_model.md` (P2-T2) |

### B1. Non-contemporaneity — the strongest position in the whole study

Spec §3.3 already declares the hour-of-week alignment as a stated modelling assumption, and §6 lists it as a threat. But the *defensive* framing sells it short. The correct framing is:

> The study does not attempt to reconstruct what those builds historically emitted. It asks how a decision policy would rank against **the grid a practitioner faces today**. The trace supplies arrival timing and workload shape; the grid supplies the carbon. Reconstructing 2013 emissions would be historically accurate and practically worthless — no one can act on it.

That reframes a limitation as a *design choice aligned with the research question*, which it genuinely is: the deliverable is a policy recommendation, and a policy recommendation must be about the present grid. Make this argument explicitly in the methodology chapter rather than leaving it as a threats-chapter concession.

**What must still be conceded:** the *arrival-time distribution* comes from a 2011–2016 developer population, whose hour-of-week commit patterns may differ from today's (remote work, global distribution, bot-driven commits). Since the carbon opportunity depends on *where arrivals fall relative to green slots*, this is not cosmetic. It is, however, a threat of **undetermined direction** — do not claim it is conservative without measuring it.

### B2. Single region — the weakest point, and the one with a cheap fix

Spec §6 says "a single (UK) grid profile limits geographic generalisation; a higher-variance zone may be added if time permits." That phrasing is a hostage to fortune: a panel will simply ask whether time permitted, and "no" is a poor answer when the fix is one CSV file.

**The substantive risk is larger than geographic generalisation, and it is not currently stated anywhere.** The UK grid in 2024–2025 is both **low-carbon and low-variance**: overall mean 127.1 gCO₂/kWh, a slot range of only 92.2–172.9, a peak-to-trough ratio of **1.87×**, and a **−46.66%** absolute ceiling per build *under perfect shifting with no gate, no policy and no delay bound*. Real strategies will land far below that ceiling.

The consequence for the study's central comparison:

> If ⑤ fails to materially dominate ④, a panel can ask whether that is because SE characteristics carry no decision value, **or** because the chosen grid has too little dynamic range to separate any two sensible policies. The current design cannot distinguish those two explanations.

That question is sharp, fair, and currently unanswerable. Note that it compounds a limit the protocol has *already* declared: §A1.13/DL-013 records that the carbon channel has no power to detect SE value at all, because carbon is proportional to duration by construction. A compressed grid narrows the remaining headroom further.

**Recommended mitigation — add one second hour-of-week profile from a higher-variance zone** (a grid with a pronounced solar midday trough or a heavier fossil peak) and re-run the replay as a P3-T4 sensitivity. Cost is genuinely small: a second 168-row profile and a re-run of an already-parameterised sweep. The payoff is disproportionate — it converts "single region" from an admitted weakness into a **measured invariance claim**:

> The *ranking* of strategies is invariant to grid shape; only the magnitude of the saving moves.

Be precise about what this buys. It strengthens **RQ4** (does the policy beat its baselines, and is that robust to the grid?). It does **not** rescue RQ2, which §A1.13 already routes through TTFF rather than carbon. Do not let a second grid be presented as evidence for SE decision value.

**Status:** §6 contemplates it conditionally. **Requires a DL entry before P3-T1** to become a predeclared sensitivity rather than a post-hoc addition.

### B3. The hour-of-week *mean* — mostly defensible, and one part is favourable

Three distinct consequences, which should not be merged:

1. **Variance suppression.** Using a slot mean discards within-slot spread, so realised savings in a deployment would be noisier in both directions than the study reports. State it; it is minor.
2. **This is not oracle knowledge — and that is worth saying plainly.** A reviewer may allege the simulator has perfect foresight of the grid. It does not: an hour-of-week climatology is computable in advance by anyone from public history, so the study's information assumption is *deployment-realisable*. The honest claim is "expected saving under grid climatology," which a real scheduler can obtain. This is a strong answer and should be prepared verbatim.
3. **The direction of this threat is favourable, which is rare enough to point out.** A real scheduler would use a *forecast*, which is strictly better than a climatology. The study therefore plausibly **understates** what a deployment could achieve. Very few of this study's threats run in the helpful direction — use this one.

Finally, and importantly for the pairing argument: the same profile is applied to all six strategies on identical traces, so even if the absolute level is wrong, the **comparison** is protected by construction. That is the point to make whenever an absolute gCO₂e figure is challenged.

### B4. Already covered, keep as-is

Marginal-versus-average intensity is declared in §6 and again in `results/p2/energy_model.md` item 7, with the herding metric as the check on whether strategy behaviour concentrates load enough for the distinction to bite. No change needed.

## C. The artifact after the research

### Judge it against the right standard

The recurring error in evaluating a research artifact is to ask "would someone buy this?" That is the wrong bar for a BSc viva and invites a defence the artifact cannot win. The right question is:

> **Does the artifact make the finding executable, auditable and falsifiable?**

Against that bar, this artifact is well positioned — for a reason that is already in the architecture and does not depend on which way P3 goes.

### What makes it genuinely valuable: the provenance chain

Invariant 5 requires the simulator and the live prototype to call the *identical* `decide()`. Invariant 7 requires every threshold in `policy_spec.yaml` to trace to a `results/` file via `scripts/fit_policy.py`. Together those give a demonstrable chain:

```
evidence (results/p1/*)  →  fit_policy.py  →  policy_spec.yaml (frozen)  →  decide()
                                                                           ├─→ replay simulator → every number in Chapter 4
                                                                           └─→ REST API → GitHub Action → live build decision
```

The single most persuasive thing this project can put in front of a panel is that chain, executed live: **the same function that produced every number in the results chapter is the one deciding a real build, and every constant it uses can be traced back to a file that a recorded command produced.** Very few undergraduate artifacts can demonstrate evidence-to-execution provenance end to end. That value is **independent of whether the null holds**, which makes it the safest thing to build the demonstration around.

### Practical? Achievable? — separately

| Question | Assessment |
| :-- | :-- |
| **Achievable** | **Yes.** Three P4 tasks, and the hard part — the decision core — is built in P2 regardless. The risk is scope, not feasibility. Note that both narrowing recommendations below *reduce* the work. |
| **Practical** | **Partially, and that is fine if stated.** Honest limits: GH Actions "deferral" is re-dispatch, not pausing a queued job; duration history needs a real store with cold-start handling; retries, cancellations and concurrency are undemonstrated. It is a credible *demonstrator*, not a production tool. Claim exactly that. |
| **Valuable** | **Yes**, via the provenance chain above, plus a real falsifiability hook: a team can observe whether their own duration history is adequate. |
| **Presentable** | **Yes**, and it is the strongest part of the submission if the demo is built around the chain rather than around the dashboard. |

### The one serious risk, and it is currently the *planned* outcome

If P3 confirms the null and P4 still ships a 28-feature SE request schema and a SHAP-rationale dashboard, **the artifact will contradict the thesis it is submitted with**. A panel will notice immediately, and it is the most damaging single thing that could happen at the viva — worse than the null itself, because it reads as the author not believing their own result.

The main body of this review already recommends narrowing the input contract (item 2) and removing SHAP from the default null-path interface. Restating with the timing made explicit: this is a **decision to be taken and dated after P3-T5, before P4-T1**, and because it changes the artifact contract in spec §5 / Layer 0-A, it is a decision-log entry, not a silent narrowing.

The inverted framing is much stronger. An artifact that **visibly embodies its own negative finding** — a live decision whose reason string says, in effect, *"SE features were evaluated and rejected; this decision uses duration history only; see `results/p1/incremental_value.md`"* — is more impressive to an examiner than one that quietly hides the null behind a fallback branch. It demonstrates that the author's engineering follows their evidence.

### A concrete demonstration script (~10 minutes)

Build the demo around the chain, in this order. Each step should be a real command or a real HTTP call, not a slide.

1. **Show the evidence.** Open `results/p1/incremental_value.md` — six families, six negative deltas, admitted set empty, floor sweep stable at ×0.5/×1/×2. *This is the finding.*
2. **Show the compiler.** Run `fit_policy.py`. Show that it reads only `results/` files and emits `policy_spec.yaml` with a provenance block. *No threshold was chosen by hand.*
3. **Show the frozen spec.** Open `policy_spec.yaml`; point at one threshold and name the results file it came from.
4. **Show the same core in two places.** One build record → `decide()` in the simulator; the same record → the REST API. Identical output. *This is invariant 5, executed.*
5. **Show it live.** Trigger the GitHub Action on the demo repo. Show the decision, the reason string naming the gate rule and the policy path taken, and the deferred window.
6. **Show the honesty.** Point at the reason string declaring that no SE model is in use, and why.
7. **Show the audit.** The invariant validator passing over the decision log: zero non-deferrable builds deferred, verified by a code path that does not import the gate.

Steps 4, 6 and 7 are the ones that distinguish this from a typical student demo. Rehearse those.

### On the dashboard

Keep it, but make it an **operational audit view**, not an explanation surface: queue state, decision log, duration-history coverage, imposed delay, estimated (never asserted) carbon change, and override/cancellation counts. On the null path, a SHAP panel is not merely decorative — it displays the rationale of a model the study rejected as a decision input.

## D. Summary of recommendations, with deadlines

| # | Recommendation | Protects | Cost | Deadline |
| :-- | :-- | :-- | :-- | :-- |
| 1 | Reframe corpus choice as deliberate — "testing the claim on the corpus that produced it" — in the methodology chapter, not the threats chapter | Viva defence on dataset age | Writing only | P5-T2 |
| 2 | State the sharp form of the age concession: the most deferrable modern class (scheduled/nightly) has no marker in this release, per DL-020 | Credibility; sets up the conservative-floor reading | Writing only | P5-T2/T4 |
| 3 | **Within-corpus temporal robustness sweep** (early vs. late period; admitted set + frontier verdict stability) | RQ1/RQ2 against era drift | One P3-T4 sweep | **DL entry before P3-T1** |
| 4 | **Second, higher-variance grid profile** as a P3-T4 sensitivity; report ranking invariance, not magnitude | RQ4 robustness; answers "is the grid too flat to separate policies?" | One 168-row profile + re-run | **DL entry before P3-T1** |
| 5 | Record that the UK 2024–25 profile is low-variance (1.87× peak-to-trough, −46.66% perfect-shift ceiling) as an explicit power limitation alongside §A1.13 | Conclusion validity | Writing only | P3-T5 |
| 6 | Prepare the "climatology, not oracle" answer verbatim; note its direction is favourable | Viva defence on the mean profile | Writing only | P5-T4 |
| 7 | Narrow the P4 contract to match the P3 verdict — input schema and dashboard | Prevents the artifact contradicting the thesis | Reduces work | **DL entry after P3-T5, before P4-T1** |
| 8 | Build the demonstration around the evidence→policy→`decide()`→live chain, per the script above | Artifact value at the viva | Rehearsal | P4 |

Recommendations 3 and 4 are the time-critical ones. Both are inexpensive, both convert a conceded weakness into a measured result, and both become **worthless if adopted after the test split is opened** — at which point they are post-hoc analyses, not predeclared sensitivities. P3-T1 is two tasks away.

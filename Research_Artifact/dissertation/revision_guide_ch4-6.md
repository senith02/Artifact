# Revision guide: Chapters 4, 5 and 6

How to use this: work through it top to bottom with your Word file open. Each item says **where**, **what to do**, and gives **paste-ready text** when a section is rewritten.

| Label | Meaning |
| :-- | :-- |
| **FIX** | Factual or number error. Change it even if you change nothing else. |
| **REPLACE** | Delete the whole section body and paste the new text below. |
| **DELETE** | Remove the figure, table or paragraph. |
| **MOVE** | Cut it from here and paste it where stated. |
| **KEEP** | Leave as is (small edits noted, if any). |

All section headings are kept, because they look like your university's required template (4.1–4.10, 5.1–5.9, 6.1–6.8). Only the subsections inside 6.2 are merged. After deleting figures and tables, update the caption numbers (in Word: Ctrl+A, then F9) and check every "Figure x.x / Table x.x" reference in the text.

Expected effect: Chapter 4 loses 9 of its 21 figures and about 40% of its text. Chapters 5 and 6 lose about 25–30%, mostly through merged subsections and removed repetition.

---

## Part A — Errors to fix first (the examiner will find these)

These were checked against your results files. Fix them before anything else, because they are the easiest things to be questioned on in the viva.

| # | Where | Currently says | Change to | Why |
| --: | :-- | :-- | :-- | :-- |
| 1 | 4.2, first paragraph | "RQs (RQ1-RQ4, Layer 0-A)), Design (spec §3-§5), Evaluation Protocol (results/p0/eval_protocol.md) and Amendment A1" | Replace the whole of 4.2 (Part C) | Internal project files mean nothing to a reader, and your supervisor queried this part |
| 2 | Table 4.1, FR15 | "Identify the geographical location of the build grid and provide confidence…" | Delete FR15 | Contradicts 4.4: "The advisor never determines the location of the build" |
| 3 | Table 4.2, NFR10 | "within the first few seconds of the CI job" | "within the first step of the CI job" | You measured 13.89–21.43 s (Table 5.9). "A few seconds" is not true |
| 4 | Table 4.4, F3 | CI "-0.0364 to 0.0297" | "-0.0364 to -0.0297" | Minus sign missing. The text says every interval is below zero |
| 5 | Table 4.4, F6 | "-1.0084" | "-0.0084" | Typo. Figure 4.14 shows -0.0084 |
| 6 | Table 4.8, GitHub Actions row | "Push-triggered decision + schedule re dispatch" | "Running the advisor on real commits" | 4.4 says the re-run workflow was cut from scope |
| 7 | 4.10 | "the planned live prototype" / "Chapter 5 will open the test projects once" | Replace 4.10 (Part C) | The prototype was built, and the test set was opened twice (5.1) |
| 8 | 4.6.2 vs Table 5.3 | "55,228" vs "55,238" | Use one number in both places | Same count printed two ways. Check your eligibility audit output; I could not find it in the results files |
| 9 | Table 5.3 | "645 passed" | "All 807 passed" | 645 was the suite size at the Phase 3 re-run. 807 is the final suite, used in 4.9, 5.4.7 and 6.2.8 |
| 10 | Table 5.4 | "Rand correlation"; regressor "1.5321 s" | "Rank correlation"; "1,532.1 s" | Typos (results: 1,532.1 s) |
| 11 | Table 5.5, Test activity row | "-0.013 [-0.035, +0.030]" | "-0.033 [-0.035, -0.030]" | Wrong numbers. Results file: −0.032535 [−0.034816, −0.030346] |
| 12 | 5.4.3 bullets | "No group provided calibration data…", "above the threshold level but twice the value" | Replace (Part D) | The sentences are garbled and say the wrong thing |
| 13 | Table 5.2 | "F!", "cures" | "F1", "curves" | Typos |
| 14 | Table 5.7, first row | "-(2,849,6 g per 1000 builds)" | "0% (baseline: 2,849.6 g per 1,000 builds)" | Format error |
| 15 | Table 5.7, column header | "Avg. added delay" | "Average added delay (all builds)" | 1.02 h is averaged over **all** builds, not only the delayed ones (results: "latency mean h (all)") |
| 16 | 5.4.5 bullets | "7.054 failed builds"; "does not urn"; "delayed for no more than one day is less than 1 in 12" | "7,054"; "does not run"; see Part D | Typos and garbled sentence |
| 17 | 5.4.6 vs 6.2.9 | 5.4.6 says California is "the only alternative"; 6.2.9 says it "had less variation" | Use the Part D wording in both | Your results say California's profile varies no more than the UK's (peak-to-trough 1.87 vs 1.87) |
| 18 | Table 5.12, Objective 4 | "Prototype tests (pending)", "Prototype pending" | See Part D | Contradicts 5.4.7 and 6.3, where the prototype is finished |
| 19 | 6.2.1, Table 6.1 (row 1), 6.3 Objective 1 | cites "Table 5.9" for commit-characteristic results | "Table 5.10" | Table 5.9 is the run-time table |
| 20 | Table 6.1, row 8 | "Results/p4/(Section 6.2.8)" | "Section 5.4.7" | Codebase path |
| 21 | 6.2.4 | "The delay policy with a 24-hour delay saves 9.6 grams **less** carbon and reports builds 5.91 hours later" | "…saves 9.6 g **more** carbon per 1,000 builds than the policy but reports failures 5.91 hours later" | Direction is wrong. 24 h delay = 2,769.3 g; policy = 2,778.9 g |
| 22 | 6.2.4 and 6.4 (RQ4) | "delays 7.92% of the builds by an average of 1.02 hours" | "delays 7.92% of builds (average added delay 1.02 h across all builds)" | Same issue as #15 |
| 23 | 6.2.8 | New What-If results (spring-boot, rails, …) appear for the first time | Move them to 5.4.7 (Part D) | A discussion chapter should not introduce new results |
| 24 | 6.2.9, last bullet | "…was not measured.6.3 Achievements of Research Objectives" | Remove the stray heading text | Copy-paste leftover |
| 25 | 6.3, Objective 4 | Paragraph "Neither approach wins in both areas…" | Move into 6.2.3 (Part E) | It is discussion, not an objective |
| 26 | 6.8 | "eight directions for future research" | "six directions" | 6.6 lists six |
| 27 | 6.4, RQ4 heading | "How effective the decision model…" | Copy RQ4 word for word from 1.4 ("How well does…") | RQ wording must match Chapter 1 exactly |
| 28 | References | — | Add: Mhalla & Saied (2024), Kamei et al. (2013), Chen & Guestrin (2016), Lundberg & Lee (2017), Saito & Rehmsmeier (2015), Zadrozny & Elkan (2002), Platt (1999), Efron & Tibshirani (1993), Aneggi et al. (2026) | Cited in Chapters 4–6 but missing from the reference list |
| 29 | Typos | "aa failed" (4.10), "come during" (5.1), "thier" (Table 5.7), "do no make" (5.9), "memeaningul" (6.7), "Algroithm"/"funcion" (Fig 4.9), "Familes" (Table 4.6), "intenstity" (Fig 4.20), "Parameteres" (Table 5.1), "withing" (several places) | Correct spelling | — |

---

## Part B — Words to replace everywhere

Use **one** plain term for each idea and keep it the same in every chapter. At the moment Chapter 4 says "families" and Chapter 5 says "groups" for the same thing.

| Remove this | Use this instead |
| :-- | :-- |
| SE characteristics, SE families, feature families | **commit characteristics**, **groups** |
| d̂ | expected duration |
| Stage 1 / Stage 2, eligibility gate | Step 1 (can it wait?) / Step 2 (is it worth waiting?) |
| materiality floor, floor | threshold (minimum improvement of 0.01) |
| TTFF, failure feedback p95 | failure feedback time: how long until a failing build reports its result (95th percentile) |
| oracle | perfect duration knowledge (theoretical) |
| frontier, area between curves, matched grid points, counting rule | difference between the carbon–feedback curves |
| fail closed, fail-safe | defaults to "run now" |
| parity | gives the same answer |
| cold-start veto | no build history yet, so run now |
| pre-registration principle | rule fixed in advance |
| leakage | using information only known after the build finishes (define once in 4.2, then "leakage" is fine) |
| Layer 0-A, spec §, Amendment A1, DL-0xx, invariant 5, eval_protocol.md, policy_spec.yaml, code/scripts/, code/artifacts/, config/, accounting.py, AST test, require_fitted, defer_until, fit id 1088d…, dataclass, schema | **delete** — internal project names |

---

## Part C — Chapter 4 (Proposed Solution)

### 4.1 Introduction — REPLACE

> Chapter 3 explained how the research was carried out. This chapter describes what was built to answer the research questions: the requirements, the overall solution, its design, the main algorithms and models, the data and the technologies used.
>
> The solution is not a new carbon-aware scheduler. It is a decision model that decides which commit-triggered CI builds should be delayed to a cleaner hour, and it tests whether commit characteristics improve that decision beyond an estimate of how long the build will take.

### 4.2 Requirement Analysis — REPLACE (whole section, including Tables 4.1–4.3)

This answers your supervisor's question. The research questions say **what must be found out**. They do not say **what the system must do**. So the requirements should not be presented as coming from the RQs. They come from four sources: stakeholders, gaps in existing work, the data, and the needs of a fair evaluation. Each requirement now shows its source.

> **4.2.1 How the requirements were identified**
>
> This is a research artifact, not a system built for a client, so there was no single customer to interview. The research questions set the goal of the study, which is what has to be found out, but they do not on their own say what the system must do. The requirements were therefore identified through four activities, carried out before the design began.
>
> 1. **Stakeholder analysis.** The people and systems that would use or be affected by the tool were identified, together with what each one needs:
>    - *Developers* need fast results for urgent builds and a clear reason whenever a build is delayed.
>    - *Team maintainers* need to control which builds may wait and to override a delay, and need to be sure the tool never breaks or blocks the pipeline.
>    - *The CI platform* needs a quick answer at the start of the job, and should give the tool read-only access.
>    - *The researcher* needs results that can be repeated and compared fairly.
> 2. **Review of existing work (Chapter 2).** Weaknesses in existing tools and studies became requirements. Claßen et al. (2023) relied on developers marking deadlines by hand, so this system must decide automatically which builds may wait. Studies that delay every build do not report the cost to developers, so this system must measure feedback delay as well as carbon. Build-prediction studies warn that using information known only after a build finishes gives misleadingly good results (Rangari et al., 2025), so the system must never use such information. This mistake is called leakage.
> 3. **Analysis of the available data.** The dataset records only whether a build is a pull request and its branch name, so the rules for urgent builds had to use these two facts. Carbon data is available only for Great Britain, so the build location has to be declared, and any other location must lead to "run now".
> 4. **Needs of a fair evaluation.** For the result to be credible, the projects used for testing must be kept apart from those used to build the model, the rules for judging an improvement must be fixed before testing, and every scheduling strategy must be replayed on the same builds.
>
> Each requirement was then given a priority using the MoSCoW method. *Must* requirements are those without which the study could not give a trustworthy answer, or developers could be harmed. *Should* requirements make the tool more useful in practice. Tables 4.1 and 4.2 show the source of each requirement: S = stakeholders, L = literature, D = data, E = fair evaluation.
>
> **4.2.2 Functional requirements**
>
> | ID | Requirement | Source | Priority |
> | :-- | :-- | :-- | :-- |
> | FR1 | Load the historical CI data and combine its job records into one record per build. | D | Must |
> | FR2 | Extract the commit characteristics known before a build starts, and exclude anything known only after it finishes. | L, D | Must |
> | FR3 | Decide automatically whether a build may wait, using fixed rules based on pull requests and protected branches. | S, L, D | Must |
> | FR4 | Estimate how long each build will take, using only information available when the commit arrives. | S, E | Must |
> | FR5 | Measure whether each group of commit characteristics improves on the duration estimate, using rules fixed in advance. | E | Must |
> | FR6 | Give a "run now" or "delay" decision for each build, with the target hour and a plain-language reason. | S | Must |
> | FR7 | Estimate the energy and carbon of each build, and replay all strategies on the same historical builds, reporting both carbon saved and feedback delay. | L, E | Must |
> | FR8 | Provide the decision inside a real CI workflow (GitHub Actions). | S | Must |
> | FR9 | Let a team declare where its builds run and override a delay (for example with an urgent marker). | S, D | Should |
> | FR10 | Show a team how the policy would have treated its own recent builds (What-If report). | S | Should |
>
> *Table 4.1 Functional requirements*
>
> **4.2.3 Non-functional requirements**
>
> | ID | Quality | Requirement | Source |
> | :-- | :-- | :-- | :-- |
> | NFR1 | No leakage | A decision never uses the build's own actual duration or result. | L |
> | NFR2 | Fair evaluation | Training, calibration and test projects are kept separate, and the rules are fixed before testing. | E |
> | NFR3 | Reproducibility | Running the same step again gives identical results. | S, E |
> | NFR4 | Safety | A build that must run now is never delayed. If anything fails, the answer is "run now". The tool only advises and never stops or cancels a build. | S |
> | NFR5 | Explainability | Every decision comes with a reason a developer can understand. | S |
> | NFR6 | One decision logic | The simulator and the prototype use the same decision function, so what was evaluated is what was demonstrated. | E |
> | NFR7 | Responsiveness | The recommendation is ready within the first step of a CI job. | S |
> | NFR8 | Low cost and security | Runs on one laptop with free software and public data. The CI integration needs only read access. | S |
>
> *Table 4.2 Non-functional requirements*
>
> **4.2.4 Inputs, processes and outputs**
>
> | Input | Process | Output |
> | :-- | :-- | :-- |
> | Historical CI builds (3,881,992 job rows) | Clean, combine into builds, extract characteristics, split by project | 922,624 builds in training, calibration and test sets |
> | Durations of a project's earlier completed builds | Estimate expected duration | Expected duration for each build |
> | Build results (training projects only) | Train failure models; test each group's added value | Which groups, if any, enter the policy |
> | Pull-request flag, branch name, expected duration, GB carbon profile | Decision function | Run now or delay, with a reason |
> | A new commit in a GitHub repository | GitHub Action calls the same decision function | Recommendation shown in the CI run |
>
> *Table 4.3 Inputs, processes and outputs*

### 4.3 Proposed Solution — REPLACE (keep Figure 4.1)

> When a commit triggers a build, the solution answers two questions in order.
>
> **Step 1 – Can this build wait?** Fixed rules answer this from how the build was triggered. Pull-request builds and builds on protected branches (such as main, release and hotfix) run immediately, because someone is waiting for the result.
>
> **Step 2 – Is it worth waiting?** For builds that may wait, the policy delays the build to the cleanest hour within a set window, but only if the build is long enough for the delay to save meaningful carbon. A ten-second build saves almost nothing but still makes the developer wait, so the expected duration is the natural first thing to check.
>
> The research contribution lies in Step 2. The study tests whether commit characteristics (change size, file types, test activity, project history, developer and team, and timing) improve this decision beyond the duration estimate. A group of characteristics enters the policy only if it passes a test whose thresholds were fixed before any results were seen. On the development data no group passed, so the final policy uses duration alone: a build that may wait and is expected to take at least 480 seconds (8 minutes) is delayed to the cleanest hour in the next 24 hours.
>
> The solution has three parts that share one decision function: (1) an evidence pipeline that builds the models and fixes the policy from historical data; (2) a replay simulator that compares six scheduling strategies on the same historical builds; and (3) a GitHub Action that runs the same decision on real commits and shows the recommendation to developers.

### 4.4 System Architecture — REPLACE (keep Figures 4.2 and 4.3)

> The system is built around one shared decision library. Both the replay simulator (used for evaluation) and the prototype (used in real CI) call this library instead of keeping their own copy of the logic, so the system that was evaluated is exactly the system that was demonstrated.
>
> The system has five layers (Figure 4.2):
>
> - **Data** – the historical CI builds, the GB carbon-intensity data and the fixed list of which project belongs to which data set. These are read-only.
> - **Evidence pipeline** – runs offline to extract characteristics, split the data, build the duration estimate and failure models, test each group of characteristics and fix the policy.
> - **Decision core** – the eligibility rules, the carbon lookup and the decision function. Energy and carbon accounting is kept separate so that it can never influence a decision.
> - **Evaluation** – the replay simulator and an independent safety checker.
> - **Prototype** – an advisor that checks the request and the team's settings, estimates the duration from the repository's completed runs and calls the decision function. It is used through a GitHub Action, a command-line tool, a REST API and the What-If report.
>
> The prototype only advises (Figure 4.3). It shows "RUN NOW" or "DEFER RECOMMENDED" and the team decides. It never stops, cancels or reschedules a build, and if any input or service fails it answers "RUN NOW" with the reason. Because carbon data is available only for Great Britain, the team must declare where its builds run, and any other location gives "RUN NOW". GitHub-hosted runners cannot be confirmed to be in Great Britain, so real runs in the demonstration repository always received "RUN NOW" (Section 5.4.7).

### 4.5 System Design

**Intro paragraph — REPLACE:**

> Three diagrams describe the design: who uses the system (use case), its main parts (components), and how data moves through the evidence pipeline (data flow).

- **4.5.1 Use case** — KEEP as is.
- **4.5.2 Component view — REPLACE the text** (keep Figure 4.5):

> Figure 4.5 shows the main components and how they depend on each other. Two design choices matter most. First, the eligibility rules run first: if a build must run now, the rest of the decision is never consulted. Second, energy and carbon accounting is completely separate from the decision path, and an automated test fails if any decision component tries to use it. This means a build's real duration or energy can never influence its own decision.

- **4.5.3 Decision contract (class diagram)** — DELETE the subsection and Figure 4.6. It is code-level detail (field names, data types) that an examiner does not need.
- **4.5.4 Data flow — REPLACE the text** (keep Figure 4.7):

> Figure 4.7 shows the order in which the evidence pipeline runs. Two rules are built into it. The test projects stay closed until the policy is fixed. Each step loads the saved output of the previous step instead of rebuilding it, so the duration baseline cannot change between experiments.

- **4.5.5 Sequence view** — DELETE the subsection and Figure 4.8. The text in the figure is too small to read in the PDF, and 4.4 plus Figure 4.3 already describe the prototype flow. Keep it only if you redraw it at full page width.

### 4.6 Algorithms / Models

**4.6.1 Algorithm 1 — REPLACE (keep Figure 4.9)**

> The decision function is the core of the solution. For each build it does the following, in order (Figure 4.9):
>
> 1. **Reject leaked information.** If the input contains the build's actual duration or result, it stops with an error.
> 2. **Apply the eligibility rules.** If the build must run now, it returns "run now" with the rule that applied.
> 3. **Check whether waiting is worthwhile.** If the expected duration is below the threshold, the build runs now.
> 4. **Find the cleanest hour** within the allowed window, counted in whole hours. Ties go to the earliest hour.
> 5. **Delay only if it helps.** If that hour is cleaner than the current hour, the build is delayed to it. Otherwise it runs now.
>
> All thresholds are read from the policy file; none are written into the function. The design also allowed a version in which builds likely to fail get a shorter window, so that failures are reported sooner. That version would be used only if a group of commit characteristics was accepted. None was, so it was not used.

**4.6.2 Algorithm 2 — REPLACE (keep Figure 4.10, DELETE Figure 4.11)**

> Urgency is decided by fixed rules, not by machine learning, because urgency and failure risk are different things: a small, low-risk change can still be urgent.
>
> The dataset records only two facts about how a build was triggered: whether it was a pull request, and its branch name. A build may wait only if it is not a pull request and its branch is not protected (main or master, production, release, stable, maintenance, hotfix, version tags and pre-release branches). The pull-request check comes first, so a pull request to main counts as a pull request. If either fact cannot be read, the build runs now (Figure 4.10).
>
> Of the 783,931 development builds, 191,245 (24.4%) may wait. A stricter version that also protects development branches leaves 16.9%; it is used as a sensitivity test in Chapter 5. Because the data does not record which builds were really urgent, these rules can be checked for consistency but not for correctness.

**4.6.3 Model 1 (duration estimate) — REPLACE (DELETE Figure 4.12)**

The paragraph about the history correction ("The rule above was improved…") is removed here because it is explained once, in 5.1.

> The duration estimate is the baseline that commit characteristics must beat. It is made when the commit arrives, before the build runs. Two forms were defined before any code was written:
>
> - **Project history** – the median duration of the same project's earlier builds that had already finished. If there are none, the median for the project's programming language is used, and after that the overall median. Both fallbacks use training projects only.
> - **Commit-characteristic regressor** – an XGBoost model that predicts duration from the 28 commit characteristics, trained on training projects only.
>
> The rule for choosing between them was fixed in advance: the form with the lower error on the calibration projects is used. Project history was clearly better. It had lower error (0.602 against 1.178 on the log scale) and a stronger rank correlation with real duration (0.869 against 0.526). Rank correlation matters most here, because the policy compares the estimate with a threshold. Project history is also easy to use in practice, since every CI service already knows its own build history.
>
> A version using only the last 50 builds was even more accurate, but the chosen form was kept, because changing the choice after seeing the results would break the rule of fixing decisions in advance.

**4.6.4 Model 2 (failure models) — REPLACE**

Tuning details are removed (20 candidates, 20% validation slice, isotonic vs Platt). If asked in the viva, you can say "isotonic calibration was chosen by the lower Brier score".

> The candidate commit-level signal is a model that predicts whether a build will fail (status "failed" or "errored"). Its output is a calibrated probability: of the builds given a 30% chance of failing, about 30% actually fail.
>
> Three model types were trained: XGBoost (chosen in advance as the main model), logistic regression and random forest. Each was trained twice: once with the duration estimate alone (the control), and once with the duration estimate plus all 28 commit characteristics. Six further XGBoost models each added one group of characteristics to the duration estimate.
>
> XGBoost was chosen because the data is a large table (645,244 training builds) in which failures are the minority (about 24%). Boosted trees handle mixed and missing values well, run fast on a CPU, and can be explained with SHAP (Chen & Guestrin, 2016; Lundberg & Lee, 2017). Models were tuned on training projects only and calibrated on calibration projects. They were compared using PR-AUC, which measures how well a model ranks failing builds above passing ones and suits data where failures are the minority (Saito & Rehmsmeier, 2015).
>
> On the calibration projects, adding the commit characteristics did not help any model. For XGBoost, PR-AUC fell from 0.391 (duration only) to 0.311 (all characteristics).

**4.6.5 Algorithm 3 (added value and admission rule) — REPLACE (keep Table 4.4 with fixes #4 and #5; keep Figure 4.15; DELETE Figures 4.13 and 4.14)**

Figure 4.14 shows the same numbers as Table 4.4, so keep only one of them. The detailed scheduling-test rules (three matched points, 5% undefined resamples) are removed: no group ever reached that test. If you have an appendix, put the full rule there.

> A group's added value is the change in PR-AUC when the group is added to the duration estimate. Its uncertainty was estimated by resampling the calibration builds 1,000 times and recording the change each time; the middle 95% of these changes gives the confidence interval (Efron & Tibshirani, 1993).
>
> A group is accepted into the policy (the *admission rule*) only if it passes two tests, both fixed before any results were seen:
>
> 1. **Prediction test** – the gain in PR-AUC is at least 0.01, and its whole confidence interval is above zero.
> 2. **Scheduling test** – in replay, the policy that uses the group gives a clearly better balance of carbon saved and failure feedback time than both duration-only policies: at least 5% faster feedback for the same carbon, or at least 1% more carbon saved for the same feedback time.
>
> Each decision was repeated with the thresholds halved and doubled, to show how much the result depends on where they were set.
>
> All six groups failed the prediction test. Every group made prediction worse, with its whole confidence interval below zero (Table 4.4), and none passed even at half the threshold. The scheduling test therefore never had a candidate. Figure 4.15 shows that a group can matter inside a model without adding value: project history (F4) and test activity (F3) make the largest SHAP contributions, yet both made predictions worse.

**4.6.6 Algorithm 4 (fitting the thresholds) — REPLACE (DELETE Figure 4.16, keep Figure 4.17)**

> With no group accepted, the policy has two settings: the duration threshold and the maximum delay. Both were chosen automatically on 12,000 calibration builds, from values listed in advance: thresholds from 0 to 15,360 seconds (doubling at each step) and windows of 6, 12 and 24 hours. The choice followed a rule also fixed in advance:
>
> 1. Find the largest carbon saving of any setting (3.78%).
> 2. Keep every setting that achieves at least 90% of it.
> 3. From those, choose the one with the fastest failure feedback.
>
> The chosen setting was 480 seconds and 24 hours, which saved 3.48% of carbon on this sample (Figure 4.17). Rebuilding the policy from scratch produced an identical file.

**4.6.7 Algorithm 5 (replay simulator) — REPLACE (DELETE Figure 4.18)**

> The simulator replays the historical builds in the order they started, through six strategies, using exactly the same builds for each:
>
> 1. **Run immediately** – today's CI.
> 2. **Blanket delay** – every build that may wait goes to the cleanest hour in the next week, whatever its length.
> 3. **Eligibility only** – every build that may wait goes to the cleanest hour in a 6, 12 or 24-hour window, whatever its length.
> 4. **Duration only** – only builds expected to exceed a threshold are delayed. This is tested with both duration estimates.
> 5. **Proposed policy** – the fixed policy file. Because no group was accepted, it is the same as duration only with project history.
> 6. **Risk-based skipping** – builds that may wait and are predicted to pass are not run at all. This is included as a comparison from build-skipping research.
>
> A build's real duration is used only after its decision has been made, to estimate energy and carbon:
>
> - energy = 42.5 W × duration (an average CPU power taken from the CodeCarbon method);
> - carbon = energy × grid carbon intensity in the hour the build runs.
>
> The simulator reports carbon per 1,000 builds, the share of builds delayed, the added delay, and the failure feedback time (how long until a failing build reports its result). An independent checker confirms that no build that had to run now was delayed or skipped.

### 4.7 Data Sets / Data Preparation — REPLACE text, shorten Table 4.5, DELETE Figure 4.19 (same data as Table 4.5), keep Tables 4.6–4.7 and Figure 4.20

> **Dataset 1 – TravisTorrent** (Beller et al., 2017). One row per Travis CI job, 66 columns, April 2011 to August 2016. It contains commit information, build results, durations and timestamps. The same dataset both trains the models and drives the replay, so both use the same features.
>
> **Dataset 2 – GB grid carbon intensity.** Hourly data for 2024–2025 from the National Grid ESO Carbon Intensity API (17,529 of 17,544 hours available). The builds are older than this carbon data, so each build is matched by hour of the week (weekday and hour) to the average intensity for that hour. This is a stated modelling assumption. The weekly profile ranges from 92.2 gCO₂/kWh (Sunday 11:00) to 172.9 gCO₂/kWh (Wednesday 18:00), so moving a build from the worst hour to the best would cut its carbon by up to 47% (Figure 4.20).
>
> **Preparation**
>
> 1. Job rows were combined into builds; a build's duration is that of its longest job.
> 2. Cancelled builds and builds without a usable result were removed (Table 4.5).
> 3. A build counts as a failure if its status is "failed" or "errored" (25.1% of builds).
> 4. Twenty-eight characteristics known before the build starts were extracted, in six groups (Table 4.6). Fields known only after a build finishes (status, test results, duration) are excluded.
> 5. Whole projects were randomly assigned to the training, calibration or test set, keeping builds in time order, and the split was locked (Table 4.7).
>
> Two data limits matter. The field that records changes to test code is empty in this release, and commit messages and change-entropy measures are not available, so some well-known defect predictors (Kamei et al., 2013) could not be built. The commit-characteristic side of the comparison is therefore a lower bound on what richer data might show.

**Table 4.5 — shorten to:**

| Step | Rows |
| :-- | --: |
| Raw job rows | 3,881,992 |
| Combined into builds | 925,897 |
| After removing builds without a usable result | 925,896 |
| After removing cancelled builds (analysed) | 922,624 |

Add a note under the table: "No exact duplicates or missing start times were found."

### 4.8 Technology Selection — shorten Table 4.8

Delete the CodeCarbon and SCI rows (they are sources for the energy model, not technologies; CodeCarbon is now cited in 4.6.7) and the matplotlib row.

| Technology | Used for | Why |
| :-- | :-- | :-- |
| Python 3.11 | The whole artifact | Standard for data analysis and machine learning |
| pandas / NumPy | Loading 3.88M job rows, building features, replay records | Fast table processing on one laptop |
| scikit-learn | Logistic regression, random forest, metrics | Standard, reliable machine-learning library |
| XGBoost | Main failure model and duration regressor | Strong on large tables, handles missing values, fast on a CPU |
| SHAP | Showing which characteristics the models rely on | Exact and fast for tree models |
| pytest | Automated tests (leakage, safety, same-answer checks) | Tests act as checks of the design rules |
| FastAPI | REST API for the prototype | Its request format can reject a duration field |
| GitHub Actions | Running the advisor on real commits | Widely used modern CI platform |
| National Grid ESO Carbon Intensity API | GB hourly carbon data | Free, public and historical |

### 4.9 Implementation — REPLACE; MOVE Figure 4.21 to 5.4.7

Run times move to 5.5, test results to 5.4.1, and the "test set opened twice" note to 5.1. Package versions are removed.

> The artifact runs on a single laptop CPU (Windows 11, Python 3.11) with fixed package versions. It has four parts:
>
> - the decision library (data loading, characteristic extraction, data split, duration estimate, models, statistics, eligibility rules, carbon lookup, accounting and the decision function);
> - the replay simulator and a separately written safety checker;
> - the prototype advisor, used through a GitHub Action, a command-line tool, a REST API and the What-If report, all of which import the decision library rather than copying it;
> - one command per pipeline stage, which reruns that stage and saves its output with a log.
>
> Correctness was checked with automated tests, an independent safety checker and full reruns from scratch. The results are reported in Section 5.4.1.

### 4.10 Chapter Summary — REPLACE

> This chapter described a decision model for selective carbon-aware CI scheduling. Requirements were identified from stakeholder needs, gaps in existing work, the available data and the needs of a fair evaluation. The design separates urgency (fixed rules) from benefit (an evidence-based policy), keeps energy accounting out of the decision, and uses one shared decision function in both the simulator and the prototype. Commit characteristics were tested against a strong duration estimate rather than against nothing.
>
> On the training and calibration data no group of commit characteristics passed the admission rule, so the policy uses duration only (at least 480 seconds, 24-hour window). Under the rules fixed in advance this is a valid result, not a failure. Chapter 5 tests this fixed policy on the unseen test projects.

---

## Part D — Chapter 5 (Evaluation)

### 5.1 Evaluation parameters — KEEP Table 5.1 (one row shortened), REPLACE the correction paragraph

In Table 5.1, change the row "Settings tested" to: "Strategies compared | Six strategies across 102 settings (14,146,686 replayed decisions)".

Correction paragraph (replace "A fix for a problem that come during…"):

> **A correction made during evaluation.** After the first test run, a review found that the duration estimate had used earlier builds that had started but not yet finished, which is information a real CI system would not have. The correction rule was written down before any new results were produced, and the whole evaluation was rerun, which meant opening the test projects a second time. The correction changed the estimate for 27.41% of test builds, but the median change for those builds was 0.00% (95th percentile 0.84%), and no research conclusion changed.

### 5.2 Framework Component — REPLACE

> The evaluation covers six aspects: (1) the accuracy of the duration estimate and failure models on unseen projects; (2) the value of commit characteristics beyond the duration estimate, which is the central question; (3) how much carbon each strategy saves and how much delay it adds; (4) whether the conclusions hold under changed assumptions; (5) whether the system follows its safety and no-leakage rules; and (6) run time and the prototype.

### 5.3 Evaluation Criteria — REPLACE Table 5.2

| Aspect | Measured by |
| :-- | :-- |
| Accuracy | Duration: error and rank correlation with real duration. Failure: PR-AUC (main measure), ROC-AUC, calibration error, precision, recall, F1 |
| Value of commit characteristics | Gain in PR-AUC with a 95% confidence interval; difference between the carbon–feedback curves |
| Scheduling | Carbon per 1,000 builds, share of builds delayed, average delay, failure feedback time (95th percentile) |
| Robustness | Whether each conclusion changes under changed assumptions |
| Correctness and safety | Must-run builds delayed (target 0), automated tests, identical reruns |
| Performance and prototype | Run time per stage; same answer across interfaces; safe fallbacks; real CI runs |

### 5.4.1 Functional and correctness testing — FIX Table 5.3

| Check | Result |
| :-- | :-- |
| Automated tests | All 807 passed |
| Must-run builds that were delayed (independent checker) | 0 of 1,015,974 delays |
| Must-run builds that were skipped | 0 of 39,453 skips |
| Eligibility rules against a separately written checker | Full agreement on all **[55,228 or 55,238 — check]** combinations of pull-request flag and branch name |
| Every strategy saw exactly the same builds | Yes |
| Policy rebuilt from scratch | Identical file |
| A build's own duration or result used in its decision | Rejected by design; shuffling real durations and results changed no decision |

Keep the sentence after the table.

### 5.4.2 Accuracy of the duration estimate — FIX Table 5.4 (#10), REPLACE the text below it

Add above the table: "Lower error is better; higher rank correlation is better."

> Project history, chosen in advance, was again clearly better than the regressor on unseen projects. Using only the last 50 builds was even more accurate; this is reported, but the policy was not changed.

### 5.4.3 Do commit characteristics improve prediction? — FIX Table 5.5, REPLACE text and bullets

Table 5.5 changes:

- Test activity row → "-0.033 [-0.035, -0.030]" | "No, worse"
- Change size row, "Meaningful?" → "Passes at the normal and half thresholds, not at double"
- Timing row, "Meaningful?" → "No, below the 0.01 threshold"

Text above the table:

> Each group of characteristics was added to a model that already had the duration estimate, to see whether prediction improved.

Bullets below the table:

> - No group passed on the calibration projects, so the policy was fixed with duration only before the test.
> - Change size is the only group that passes on the test projects, but the evidence is weak. It made predictions slightly worse on the calibration projects (−0.003), it fails when the threshold is doubled, and in the later half of the test period its gain falls to +0.009, below the threshold. It is therefore reported as unresolved and is not used.
> - Important is not the same as useful. SHAP shows project history and test activity as the groups the model relies on most, yet adding either one makes prediction worse.

### 5.4.4 Do commit characteristics improve scheduling decisions? — REPLACE text (keep Table 5.6 and Figure 5.1)

In Table 5.6, rename "Perfect knowledge of duration (theoretical)" if needed, and add to the caption: "(units: percentage points × hours)".

Above the table:

> This is the main test. For each strategy, carbon saved was plotted against failure feedback time across all its settings, giving one curve per strategy (Figure 5.1). Two curves are compared by the area between them. A positive value means the first strategy gives faster failure feedback for the same carbon saving.

Below the table:

> Because no group was accepted, the proposed policy is the duration-only policy, so their curves are identical. This "no" comes from the pipeline fixed in advance, not from a separate contest. The real differences come from the duration estimate: project history beats the regressor, and both a last-50-builds estimate and perfect duration knowledge do better still. Better duration estimates improve decisions; commit characteristics did not.

### 5.4.5 How well does the policy schedule builds? — FIX Table 5.7 (#14, #15), REPLACE bullets

> - **Against today's CI**, the policy saves 70.7 gCO₂e per 1,000 builds (95% CI 64.9–78.5), or 2.480%. It delays fewer than 1 in 12 builds (7.92%), each by at most 24 hours.
> - **Against blanket delay of up to a week**, it saves about half as much carbon (2.480% against 4.681%), but the slowest 5% of failing builds report in 13.91 hours instead of 127.01 hours (over five days).
> - **Against delaying every eligible build by up to 24 hours**, the policy saves 9.6 g less per 1,000 builds but reports failures 5.91 hours sooner (95th percentile).
> - **No strategy wins on both carbon and speed.** More carbon saved always means longer waits.
> - **Why the saving is modest.** Of 138,693 test builds, 111,666 must run now, 15,675 are too short to be worth delaying, 369 have no cleaner hour in the window, and only 10,983 are delayed. In addition, Britain's dirtiest hour is only 1.87 times its cleanest.
> - **Risk-based skipping** appears to save much more (15.205% at its most aggressive setting), but only by not running 7,054 builds that would have failed. It is not a like-for-like comparison.

### 5.4.6 Do the conclusions hold under different assumptions? — REPLACE (keep Figure 5.2)

> The main conclusion, that commit characteristics do not improve on the duration-only policy, held in every sensitivity test: stricter eligibility rules (14.02% of builds may wait), the power figure at 0.5× and 1.5× (carbon totals change, rankings do not), counting parallel jobs, and the earlier and later halves of the test period (Figure 5.2).
>
> Three details changed, and none affects a research conclusion:
>
> - Change size falls below the threshold in the later half of the test period, which supports treating it as unresolved.
> - In the later half, project history still beats the regressor, but not at enough of the compared points to count as a clear win.
> - With a 12-hour window, the policy reports failures faster than the regressor version, which favours the policy.
>
> A second electricity grid was not tested. The only free alternative with suitable data (California) varies no more than Britain's grid, so it could not show whether the results hold on a more variable grid. This question remains open.

### 5.4.7 Prototype Testing — REPLACE; simplify Table 5.8; add the What-If figure (old Figure 4.21) here

> The prototype demonstrates the decision model in real CI; it is not an experiment. Its thresholds come from the 2011–2016 Travis CI data, and its carbon figures use the same GB profile and energy model as the replay.
>
> **Correctness.** All 807 automated tests pass. The same test cases were run through the advisor, the command-line tool and the REST API, and all three gave the same decision as the research decision function. The advisor's duration estimate matched the research estimator on a Travis CI test sample. Fourteen failure cases were tested, such as an invalid request, an untrusted CI event, a non-GB region, a missing or changed policy file, and missing run history. Each one correctly returned "RUN NOW" with a reason.
>
> **Real CI runs.** The GitHub Action was added to a public demonstration repository and seven real runs were recorded (Table 5.8). Runs 1–6 each had two jobs. The *real job* always returned "RUN NOW", because a GitHub-hosted runner cannot be confirmed to be in Great Britain. A clearly labelled *GB-scenario job* showed what the advisor would recommend on GB compute. Run 7 had only one job. The build itself was a synthetic workload of about nine minutes. Across the 13 recorded decisions the independent checker found no violations, and the advisor never interrupted the pipeline.
>
> **What-If reports.** The What-If report replays a repository's recent completed runs through the same decision function (Figure 5.3, the old Figure 4.21). For four public repositories, using up to 500 recent runs each, no build would have been delayed. In awesome-go and public-apis no run was eligible to wait. In spring-boot (24 eligible runs, 5.01%) and rails (64 eligible runs, 12.83%), every eligible run was shorter than eight minutes.

**Table 5.8:** delete the "Real job" column (it says the same thing in every row; the paragraph above now explains it). In run 1, change "cold-start veto" to "RUN NOW: no completed build history yet (the policy alone would have deferred)".

### 5.5 System Performance Results — KEEP Table 5.9; add one sentence

> All stages run on one laptop CPU with free software and public data. The prototype's median of 18.24 seconds from the Action's first step to its decision is acceptable for a step at the start of a CI job.

### 5.6 Accuracy, Precision and Recall — FIX Table 5.10, REPLACE bullets

- In Table 5.10, replace the "-" cells with "n/r" and add the note: "Precision, recall and F1 are reported for the main model (XGBoost) only."
- Fix the logistic-regression "all 28" row, which has a missing cell.

> - Predicting failure from commit-time information alone is hard: PR-AUC is 0.27–0.30, against 0.25 for random guessing (the failure rate).
> - Adding the commit characteristics made every model slightly worse. The full XGBoost model's higher recall comes with lower precision, and its overall ranking quality (PR-AUC) is lower.
> - Scores fell from calibration to test projects (XGBoost from 0.391 to 0.294), which shows that what is learned on some projects transfers poorly to others.
> - The predicted probabilities are reasonably well calibrated (calibration error 0.028–0.059).

### 5.7 Comparison with existing Solutions — KEEP

Add a legend line under Table 5.11: "✓ = yes, ✗ = no, ◐ = partly." Make sure Mhalla & Saied (2024) is in the reference list (#28).

### 5.8 Results Related to Research Objectives — FIX Table 5.12

- Objective 3, Evidence: "Policy fitted automatically from calibration data only (480 s, 24 h); rebuilt identically; unchanged by the correction; tested for robustness."
- Objective 4, Evidence: "Six strategies replayed on 138,693 unseen builds; prototype tested with 807 automated tests, seven real CI runs and What-If reports."
- Objective 4, Result: "**Achieved.** 2.480% estimated carbon saving with failures reported within 13.91 h (95th percentile); the prototype works in real CI and falls back safely." (Delete both "pending" texts.)

### 5.9 Chapter Summary — REPLACE

> On this dataset, once a good duration estimate is available, commit characteristics do not help choose which builds to delay. The resulting policy is simple: delay a build if it is allowed to wait and is expected to take at least 8 minutes, to the cleanest hour within the next 24 hours. It saves an estimated 2.480% of CI carbon compared with running every build at once. It sits between today's CI and blanket carbon-aware delay, which saves more carbon but can delay failure reports by days.
>
> These are estimates from replaying 2011–2016 Travis CI builds against a recent GB grid profile, not measured emissions, and they may not carry over to today's GitHub Actions.

---

## Part E — Chapter 6 (Discussion, Conclusions and Recommendations)

### 6.1 Introduction — REPLACE

> Chapter 5 reported the results; this chapter explains what they mean. Section 6.2 interprets the findings and links them to earlier research. Sections 6.3 and 6.4 review the objectives and research questions, Sections 6.5 and 6.6 give recommendations and future work, and Section 6.7 concludes.

### 6.2 Discussion of Findings — FIX Table 6.1, then merge nine subsections into six

**Table 6.1, Evidence column:** row 1 → "Tables 5.5, 5.6, 5.10"; row 8 → "Section 5.4.7". Everything else stays.

| Old | New |
| :-- | :-- |
| 6.2.1 + 6.2.2 | **6.2.1** Commit characteristics did not help beyond duration |
| 6.2.3 | **6.2.2** A better duration estimate is where the gains lie |
| 6.2.4 + 6.2.5 (+ the stray paragraph from 6.3) | **6.2.3** Selective scheduling is a trade-off, and why the saving is modest |
| 6.2.6 | **6.2.4** Risk is not urgency |
| 6.2.8 | **6.2.5** What the prototype showed |
| 6.2.7 + 6.2.9 | **6.2.6** How far the findings can be trusted, and their limits |

**6.2.1 Commit characteristics did not help beyond duration — REPLACE**

> The main finding is a clear "no". Twenty-eight commit characteristics in six groups were each tested against a model that already had the duration estimate. None passed the admission rule on the calibration projects, so the policy stayed duration-only, and on the unseen test projects the proposed policy and the duration-only policy made identical decisions (Table 5.6). Adding all 28 characteristics together made failure prediction worse for all three model types; for XGBoost, PR-AUC fell from 0.294 to 0.273 (Table 5.10).
>
> There are two likely reasons. First, the carbon saved by delaying a build depends on how much energy it uses, and that is set by its duration. Once duration is estimated, the only extra thing a commit could tell us is whether the build will fail, so that failing builds are not kept waiting. Second, that signal is weak. From commit information alone, failure prediction reached a PR-AUC of only 0.27–0.30, against 0.25 for random guessing (Section 5.6). A signal this weak cannot change many decisions.
>
> The patterns also transferred poorly between projects: XGBoost's PR-AUC fell from 0.391 on the calibration projects to 0.294 on the test projects. Just-in-time defect prediction studies show that commit attributes can flag risky changes, but they also warn that results transfer poorly across projects (Kamei et al., 2013). Testing only on unseen projects matches the situation of a new team adopting the tool.
>
> The one exception is change size. On the test projects it improved PR-AUC by +0.013 [+0.012, +0.015], just above the 0.01 threshold. But it made predictions slightly worse on the calibration projects (−0.003), failed at the doubled threshold, and fell to +0.009 in the later half of the test period. Adding it to the policy after seeing the test result would have broken the rule of fixing decisions in advance, so it was not added and its value for scheduling was never tested. Change size has been shown to be neither useful nor useless, and is left for future work (Section 6.6).

**6.2.2 A better duration estimate is where the gains lie — REPLACE**

> The clear differences in the results all come from how duration is estimated. The project-history estimate beat the commit-characteristic regressor on error (0.5727 against 0.9868 on the log scale) and on rank correlation (0.8195 against 0.5128) (Table 5.4), and its decision curve was better by +2.43 [+1.73, +2.56] (Table 5.6).
>
> This suggests that build duration depends mainly on the project, through its test suite and build setup, rather than on the individual commit. Recent project history captures this well, while the commit-based regressor adds noise. Two further comparisons support this. Using only the last 50 builds gave a further gain of +0.36 [+0.24, +0.78]. Perfect knowledge of duration, which is impossible in practice because duration is only known after the build, gave +1.93 [+1.77, +2.35] over project history. There is still room to improve, and effort spent on a better duration estimate, which is cheap, is likely to pay back more than effort spent on commit characteristics.

**6.2.3 Selective scheduling is a trade-off, and why the saving is modest — REPLACE**

> The proposed policy saves an estimated 2.480% of CI carbon, or 70.7 gCO₂e per 1,000 builds (95% CI 64.9–78.5), compared with running every build at once (Table 5.7). It delays 7.92% of builds, with an average added delay of 1.02 hours across all builds. The slowest 5% of failing builds report after 13.91 hours instead of 1.67 hours.
>
> Blanket delay of up to a week saves more (4.681%), but its slowest 5% of failing builds take 127.01 hours, over five days, to report. The proposed policy keeps more than half of that saving while cutting this worst-case wait to about one ninth. Delaying every eligible build by up to 24 hours saves 9.6 g more per 1,000 builds than the policy, but reports failures 5.91 hours later. No strategy wins on both carbon and speed, so the value of selective scheduling is a better balance between the two, not the largest saving.
>
> The saving is modest mainly because few builds can wait. About 80% of test builds (111,666 of 138,693) had to run at once because they were pull requests or on protected branches. Of the rest, 15,675 were too short to be worth delaying and 369 had no cleaner hour, which left 10,983 delayed (Section 5.4.5). The GB grid also varies less than might be expected: its dirtiest hour is only 1.87 times its cleanest, so even a perfect choice of hour saves at most 47% for a single build. The limit is how many builds can wait, not how they are chosen. This also explains why commit characteristics had little room to help: they can affect only about one build in five.
>
> This also clarifies earlier work. Claßen et al. (2023) showed that delaying flexible CI jobs reduces emissions, but relied on developers to label which jobs were flexible. This study shows that flexibility can be approximated from how a build was triggered, and it also measures the cost of the delay.

**6.2.4 Risk is not urgency — REPLACE**

> Skipping builds predicted to pass appears to save far more carbon, up to 15.205% at the most aggressive setting, but it does so by not running 7,054 builds that would have failed (Section 5.4.5). A skipped failure is a bug that reaches developers or users later. This supports a key design choice: urgency is decided by fixed rules, failure risk by a model, and the two are kept separate. Build-skipping research (Mhalla & Saied, 2024) treats the choice as run or skip. This study shows that once carbon is included, the saving from skipping hides a quality cost, so any such saving should be reported together with the failures it misses.

**6.2.5 What the prototype showed — REPLACE (the What-If numbers are now in 5.4.7)**

> The fixed duration-only policy was turned into a CI advisor (a GitHub Action, a REST API and a What-If report) that uses the same decision function as the replay. In seven real CI runs it behaved as designed: "run now" on main and on pull requests, "defer recommended" for an eligible nine-minute build in the GB scenario, "run now" when an urgent marker was added, and a safe "run now" when the region was missing or the event was untrusted (Section 5.4.7). Because GitHub-hosted runners cannot be confirmed to be in Great Britain, real-location runs always returned "run now", so deferral was shown only in the labelled GB scenario.
>
> The What-If reports on four public repositories found no build that the policy would have delayed: eligible runs were either absent or shorter than eight minutes. This is a demonstration, not an experiment, and the thresholds come from 2011–2016 Travis CI data. Even so, it agrees with the replay: in modern pipelines too, it is the eligibility rules and the duration threshold, not the choice of hour, that decide whether a build is delayed.

**6.2.6 How far the findings can be trusted, and their limits — REPLACE**

> A negative result is convincing only if the study could have found a positive one and was not adjusted afterwards. Here the thresholds, metrics and comparisons were fixed before the test projects were opened. The policy was fitted on training and calibration projects only. The independent checker found no wrongly delayed or skipped builds, the policy file was rebuilt identically, and shuffling real durations and results changed no decision (Table 5.3). The test projects were opened a second time to apply the duration-history correction (Section 5.1), but the correction rule was written down before any new results were seen. It changed the median estimate by 0.00%, and no conclusion changed. The main conclusion also held in every sensitivity test (Section 5.4.6).
>
> The findings should still be read within these limits:
>
> - **Estimates, not measurements.** Carbon uses a fixed 42.5 W power figure and hour-of-week grid averages; no energy was measured.
> - **Old data.** The builds are Travis CI builds from 2011–2016; modern CI may behave differently.
> - **One grid.** Only the GB grid (2024–2025) was tested.
> - **Approximate urgency.** The eligibility rules use pull-request flags and branch names; the data does not record which builds were really urgent.
> - **No user study.** Whether developers accept delayed builds was not measured.

### 6.3 Achievements of Research Objectives — REPLACE each answer (keep the objective headings in bold as now)

> **Objective 01 – Achieved.** Twenty-eight characteristics known before a build starts were extracted from TravisTorrent in six groups. Each group was tested against the duration estimate with confidence intervals on two separate sets of projects, and SHAP showed which groups the models relied on. No group added meaningful value; change size remains unresolved (Tables 5.5, 5.10).
>
> **Objective 02 – Achieved.** A two-step model was built: fixed rules decide whether a build may wait, and an evidence-based policy decides whether waiting is worthwhile. Measured against a commit-time duration estimate, with an admission rule fixed in advance, commit characteristics added no value in prediction or in scheduling decisions (Table 5.6).
>
> **Objective 03 – Achieved.** The policy (delay builds expected to take at least 480 seconds, to the cleanest hour in the next 24 hours) was fitted automatically from calibration data with no manual tuning. It was rebuilt identically, was unchanged by the correction, and was confirmed on 138,693 unseen builds and in sensitivity tests (Sections 5.4.5, 5.4.6).
>
> **Objective 04 – Achieved.** Six strategies were replayed on the same builds (14,146,686 decisions). The policy was delivered as a GitHub Action, a REST API and a What-If report sharing one decision function, and was tested with 807 automated tests, seven real CI runs and What-If reports. The planned dashboard was replaced by the What-If report, automatic re-running of delayed builds was not built, and no user study was carried out.

Delete the paragraph that starts "Neither approach wins in both areas…" (its content is now in 6.2.3).

### 6.4 Answers to Research Questions

- Copy all four RQ headings word for word from Section 1.4.
- **RQ1 answer — REPLACE:**

> None, under the rule fixed in advance, once a duration estimate is available. Five of the six groups made failure prediction worse or improved it too little. Change size gave a small gain on the test projects (+0.013) but none on the calibration projects, failed at the doubled threshold and weakened over time, so it is treated as unresolved. What mattered was the project's own build history, through its effect on the duration estimate.

- **RQ2, RQ3** — KEEP.
- **RQ4** — in the first sentence change "but delays 7.92% of the builds by an average of 1.02 hours" to "and delays 7.92% of builds (average added delay 1.02 hours across all builds)". Keep the rest.

### 6.5 Recommendations — KEEP

In recommendation 1, change "build only if there is no one waiting for it" to "delay a build only if no one is waiting for it".

### 6.6 Future Research — KEEP

Make sure Aneggi et al. (2026) is in the reference list.

### 6.7 Conclusion — KEEP, with small fixes

"memeaningul" → "meaningful"; "138,693 builds unknown at testing" → "138,693 unseen test builds"; "simple, reproducible and harmless" → "simple, reproducible and safe".

### 6.8 Chapter Summary — REPLACE

> This chapter interpreted the results of Chapter 5. Commit characteristics did not add useful information beyond the duration estimate, most likely because carbon savings depend on duration, failure prediction from commit data is weak, and patterns learned on some projects transfer poorly to others. Change size remains unresolved. The real gains lie in better duration estimates, and the saving is limited mainly by how few builds can wait. The proposed policy gives a better balance of carbon and feedback time than blanket delay, and the prototype shows the same logic working safely in real CI. All four objectives were met (the dashboard was replaced by the What-If report), the four research questions were answered, and four recommendations and six directions for future research were given.

---

## Part F — Figures and tables at a glance

| Item | Action |
| :-- | :-- |
| Fig 4.1 solution overview | KEEP |
| Fig 4.2 architecture | KEEP |
| Fig 4.3 deployment | KEEP |
| Fig 4.4 use case | KEEP |
| Fig 4.5 components | KEEP |
| Fig 4.6 class diagram | DELETE |
| Fig 4.7 data flow | KEEP |
| Fig 4.8 sequence diagram | DELETE (unreadable) or redraw at full width |
| Fig 4.9 decision flowchart | KEEP (fix caption typos) |
| Fig 4.10 eligibility flowchart | KEEP |
| Fig 4.11 eligibility bar chart | DELETE (numbers are in the text) |
| Fig 4.12 duration flowchart | DELETE (steps are in the text) |
| Fig 4.13 admission flowchart | DELETE (steps are in the text) |
| Fig 4.14 added-value chart | DELETE (same data as Table 4.4) |
| Fig 4.15 SHAP chart | KEEP |
| Fig 4.16 policy-fitting flowchart | DELETE (steps are in the text) |
| Fig 4.17 trade-off chart | KEEP |
| Fig 4.18 replay flowchart | DELETE (the list is in the text) |
| Fig 4.19 preparation funnel | DELETE (same data as Table 4.5) |
| Fig 4.20 carbon heatmap | KEEP |
| Fig 4.21 What-If report | MOVE to 5.4.7 |
| Tables 4.1–4.3 | REPLACE (Part C) |
| Table 4.4 | KEEP, fix #4 and #5 |
| Table 4.5 | SHORTEN to 4 rows |
| Tables 4.6, 4.7 | KEEP |
| Table 4.8 | SHORTEN |
| Figs 5.1, 5.2 | KEEP |
| Tables 5.1, 5.6, 5.9, 5.11 | KEEP (small fixes noted) |
| Table 5.2 | REPLACE |
| Tables 5.3, 5.4, 5.5, 5.7, 5.10, 5.12 | FIX numbers (Part A) |
| Table 5.8 | Drop the "Real job" column |
| Table 6.1 | FIX evidence column |

---

## Part G — Outside Chapters 4–6 (quick, but related)

- **3.6 Requirement Gathering** still says "The research questions also influence the requirements…". Change that paragraph so it matches the new 4.2: requirements come from stakeholder analysis, the literature review, the data and the needs of a fair evaluation. Otherwise the examiner will see Chapter 3 and Chapter 4 disagree.
- **2.1 Introduction** of the Literature Review describes the methodology (DSR, leakage control, splits). It should introduce the literature instead: what areas are reviewed and why.
- **Reference years:** Claßen et al. appears as 2023 in the text and 2024 in the reference list; Barrak et al. as 2021 and 2025. Make each one consistent.

---

## Part H — If you are asked "How did you get your requirements?" in the viva

> "The research questions told me what I needed to find out, not what the system should do, so I didn't take the requirements from them directly. I got them in four ways. First, I looked at who would use the tool: developers, team maintainers, the CI platform and myself as the researcher, and what each one needs, such as fast feedback, an override, read-only access and repeatable results. Second, I turned gaps in existing work into requirements. For example, Claßen et al. needed manual deadlines, so my system decides automatically, and prediction studies warn about leakage, so my system never uses post-build data. Third, the data limited what was possible: it only records pull-request flags and branch names, so the urgency rules use those, and carbon data only exists for Great Britain, so the region must be declared. Fourth, a fair evaluation needs separate test projects, rules fixed in advance, and the same builds for every strategy. Each requirement in Tables 4.1 and 4.2 shows which of these sources it came from."

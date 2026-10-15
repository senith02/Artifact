# Chapter 6 — Discussion, Conclusions and Recommendations

> **Drafting notes (delete before submission).** As in Chapter 5, every number here comes from a
> project result file; the sources are listed at the end of the chapter. The objectives and research
> questions are quoted from Chapter 1. Prototype results (Sections 6.2.8 and 6.3) come from
> `results/p4/` and are demonstration evidence, not research evidence.

---

## 6.1 Introduction

Chapter 5 reported what the evaluation measured. This chapter explains what those measurements
mean. It returns to the problem set out in Chapter 1. Carbon-aware CI schedulers can move builds to
cleaner hours of the electricity grid, but there is little evidence about *which* builds should be
moved. This research asked whether the characteristics of a commit help to make that choice, over and
above a simple estimate of how long the build will take.

The chapter has three purposes. First, it interprets the main findings, explains why they came out as
they did, and relates them to the earlier work reviewed in Chapter 2 (Section 6.2). Second, it checks
the work against the four objectives and answers the four research questions set in Chapter 1
(Sections 6.3 and 6.4). Third, it turns the findings into practical recommendations and directions
for future research (Sections 6.5 and 6.6). It then draws the overall conclusion of the research
(Section 6.7) and summarises the chapter (Section 6.8).

Each claim points back to the table or section in Chapter 5 that supports it, so that every statement
can be traced to a real result.

---

## 6.2 Discussion of Findings

Table 6.1 lists the main findings and the evidence for each. The subsections that follow discuss
them in turn.

**Table 6.1 — Main findings and the evidence behind them**

| No | Finding | Evidence |
| :-: | :-- | :-- |
| 1 | Commit characteristics did not add meaningful value beyond a duration estimate, in prediction or in scheduling decisions | Tables 5.5, 5.6, 5.11 |
| 2 | Change size is the only group with a positive test result, and that result is not reliable | Table 5.5; Section 5.4.6 |
| 3 | A better duration estimate is where the real gains lie | Tables 5.4, 5.6 |
| 4 | Selective scheduling saves less carbon than blanket delay, but keeps failure feedback within a day for 95% of failing builds | Table 5.7 |
| 5 | Most builds cannot wait, so the room for any policy is small | Section 5.4.5 |
| 6 | Skipping builds predicted to pass saves more carbon only by missing real failures | Section 5.4.5 |
| 7 | The system obeyed every safety rule, and the conclusions held under changed assumptions | Table 5.3; Section 5.4.6 |
| 8 | The same decision function runs inside a real CI workflow and falls back safely | Section 5.4.7; Tables 5.8, 5.9 |

### 6.2.1 Commit characteristics did not help beyond duration

The central finding of this research is a clear "no". Twenty-eight commit characteristics, arranged
in six groups, were tested one group at a time against a model that already knew the expected build
duration. No group passed the admission rule on the calibration projects, so the policy was frozen as
duration-only. On the unseen test projects the proposed policy and the duration-only strategy
produced identical decision curves (gap 0.0000 [0.0000, 0.0000], Table 5.6). Adding all 28
characteristics together made failure prediction *worse* for all three algorithms; for XGBoost, PR-AUC
fell from 0.294 to 0.273 (Table 5.11).

There are two likely reasons for this result. The first lies in what a delay can achieve. The carbon
saved by delaying a build depends on how much energy the build uses, and energy grows with duration.
Once duration is estimated, the only extra information a commit can offer is whether the build is
likely to *fail*, so that a developer should not be kept waiting for that result. The second reason
is that this failure information is weak. Using information available at commit time (the duration
estimate, with or without the commit characteristics), failure prediction reached a test PR-AUC of
only 0.27–0.30, against 0.25 for a random guess (Section 5.6). A signal this weak can change very few
scheduling decisions.

The results also show that patterns learned on some projects did not carry over well to others. Every
model scored lower on the test projects than on the calibration projects. The full XGBoost model fell
from 0.311 to 0.273, and even the duration-only model fell from 0.391 to 0.294 (Section 5.6). Part of
this drop reflects the lower failure rate of the test projects (25.04% against 28.55%). Just-in-time
prediction research (Kamei et al., 2013) shows that commit-level features can flag risky changes
within the projects a model was built on; whether such signals transfer to projects a model has never
seen is a separate question. This study tested only on unseen projects, which is the situation a new
team adopting a tool would be in. A likely explanation is that characteristics such as developer
experience and project maturity describe *which project* a build belongs to more than *how risky this
commit is*, and that such project-specific patterns do not transfer.

A further lesson concerns how feature importance should be read. SHAP ranked project history and test
activity as the most influential groups, yet both made prediction worse when added to the duration
estimate (Section 5.4.3). Feature importance shows what a model *relies on*; it does not show whether
that reliance *helps on new data*. This is why the study decided admission by ablation with confidence
intervals and floors fixed in advance, and not by SHAP rankings. Had SHAP alone been used, two groups
that harm prediction would have been adopted.

### 6.2.2 Change size: a weak signal, reported as unresolved

The change-size group (how large the change is and how widely it is spread) is the one exception. On
the test projects it raised PR-AUC by +0.013 [+0.012, +0.015], just above the 0.01 floor. The
evidence is still weak, for three reasons. On the calibration projects the same group made
predictions slightly worse (−0.003). It fails at double the floor. In the later half of the test
period it falls to +0.009, below the floor (Section 5.4.6).

It would have been tempting to add change size to the policy after seeing the test result. The
frozen rules did not allow this, and rightly so: choosing features after looking at the test data is
exactly the after-the-fact tuning that the study design was built to prevent. Because the group was
never admitted, its value at the *decision* level was not tested either. The honest reading is
therefore that change size has been neither shown to be useful nor shown to be useless. It is an open
question for future work (Section 6.6).

### 6.2.3 A better duration estimate is where the gains lie

The comparisons that *did* show meaningful differences all concern how duration is estimated. The
simple project-history estimate (the median duration of the same project's earlier, finished builds)
clearly beat a regressor built on commit characteristics. Its average error on the log scale was
0.5727 against 0.9868, and its rank correlation with the real duration was 0.8195 against 0.5128
(Table 5.4). At the decision level, the project-history version gave a better trade-off curve than
the regressor version, by an area of +2.43 [+1.73, +2.56] percentage points × hours (Table 5.6).

This suggests that a build's duration is mostly a property of the *project* (its test suite and build
set-up) and not of the individual commit. A short project history captures it well, while the
commit-level regressor adds noise. The other two comparisons point the same way. An estimate that
uses only the last 50 builds was more accurate still and gave a further +0.36 [+0.24, +0.78].
Against the frozen project-history estimate, a theoretical scheduler with perfect knowledge of
duration was better by +1.93 [+1.77, +2.35]. Perfect knowledge cannot be achieved in practice,
because the real duration is unknown when the commit arrives, but the gap shows that better
estimation still has room to help. In short, effort spent on estimating duration well, which is
cheap, pays off more than effort spent on collecting commit characteristics.

One qualification applies. In the later half of the test period, project history still beat the
regressor overall (area +3.56), but its strongest comparison points could not be computed in enough
bootstrap resamples, so the predeclared counting rule failed (Section 5.4.6). The direction of the
result is stable; how firmly it can be counted varies over time.

### 6.2.4 Selective scheduling is a trade-off, not a free saving

Compared with running every build immediately, the proposed policy saves an estimated 2.480% of CI
carbon (70.7 g of CO₂e per 1,000 builds, 95% CI 64.9–78.5). It delays 7.92% of builds, each by at
most 24 hours, which adds 1.02 hours of delay on average across all builds. 95% of failing builds
report back within 13.91 hours, against 1.67 hours when every build runs immediately (Table 5.7).

Blanket carbon-aware scheduling, which delays every build that may wait by up to a week, saves more:
4.681%. The cost is large, however. With blanket delay, the slowest 5% of failing builds take longer
than 127.01 hours, more than five days, to report back. The proposed policy therefore keeps a little
over half of the blanket saving while cutting this 95th-percentile feedback time to about one ninth.
Against blanket delay limited to 24 hours, the policy uses 9.6 g more carbon per 1,000 builds and
reports failures 5.91 hours sooner at the 95th percentile.

Among running immediately, the proposed policy and the two blanket strategies, no strategy won on
both carbon and speed. Every step towards a larger carbon saving cost developers feedback time. The
value of selective scheduling is therefore not the largest saving, but a better *balance* between
saving and delay. This also clarifies the earlier work. Claßen et al. (2023) showed that delaying
flexible CI jobs can reduce emissions, but their method depends on knowing in advance which jobs are
flexible. This study shows that flexibility can be approximated automatically from how a build was
triggered, and that the price of delay can be measured directly as slower failure feedback.

### 6.2.5 Why the saving is modest

The saving is small mainly because so few builds can wait. Of the 138,693 test builds, 111,666
(about 80%) had to run immediately because they were pull requests or builds of protected branches. A
further 15,675 were expected to be too short to be worth delaying, 369 had no cleaner hour available,
and only 10,983 were actually delayed (Section 5.4.5). The British grid also varies less than one
might expect: its dirtiest hour of the week is only 1.87 times its cleanest, so even a perfect shift
saves at most about 47% for a single build, before any eligibility rule or delay limit is applied.

So the main limit is *which builds are allowed to wait*, not how the waiting builds are chosen. This
also explains why commit characteristics had so little room to help: they could only change decisions
for about one build in five. A modest saving is a realistic result, not a failure of the method. The
original proposal accepted that a modest saving would itself be a useful finding for practitioners.
Saavedra et al. (2025) estimated that CI on GitHub Actions has a substantial carbon footprint in
total. A saving of a few percent that costs developers little is therefore worth having at platform
scale, but it is not a large reduction on its own.

### 6.2.6 Risk is not urgency

Skipping builds that are predicted to pass appears to save much more carbon, up to 15.205% at the
most aggressive setting. It does so, however, by not running 7,054 builds that in fact failed (Section
5.4.5). This is not a like-for-like comparison: a skipped failure is a defect that reaches developers
later, or reaches users. The result supports a key design decision of this research, which was to
keep *urgency* (decided by fixed rules) apart from *risk* (estimated by a model). Build-skip research
(Mhalla & Saied, 2024) decides whether a build should run at all. This study shows that when skipping
is mixed with carbon goals, the carbon figures hide a quality cost, so any carbon saving from skipping
must be reported together with the failures it misses.

### 6.2.7 How far the findings can be trusted

A negative result is only convincing if the study could have produced a positive one and was not
tuned after the fact. Several features of the design give this assurance. The materiality floors, the
metrics and the comparison points were fixed before the test projects were opened. The policy was
fitted on training and calibration projects only. An independent checker found **0** builds that were
delayed when they had to run now, across 1,015,974 delays, and **0** wrongly skipped builds. The
policy file was rebuilt from scratch byte for byte, and scrambling real durations and outcomes changed
no decision (Table 5.3).

The correction described in Section 5.1 also deserves comment. A review after the first test run
found that the duration estimate had counted earlier builds that had started but not yet finished,
which a real CI system could not know. The rules for the fix were written down before any new result
existed, and the full analysis was then re-run, which opened the test data a second time. The fix
touched 27.41% of test builds, the median change in an affected build's estimate was 0.00%, and no
research answer changed. The defence of this step is that both openings are recorded, the fix was
specified before its results were seen, and no conclusion moved. Finally, the main conclusion held in
every sensitivity test in which it could be evaluated: stricter eligibility rules, half and
one-and-a-half times the power figure, and counting parallel jobs (Section 5.4.6).

### 6.2.8 What the prototype showed

The frozen duration-only policy was turned into a CI deferral advisor. It consists of a GitHub Action,
a REST API and a Repo What-If report, and all three call the same decision function used in the
replay. The full test suite of 807 automated tests passed, including parity tests showing that the
advisor, the command-line tool and the REST API return identical decisions, equal to those of the
research decision function (Section 5.4.7).

Seven real CI runs on a public demonstration repository produced 13 advisory decisions, and the
independent checker found 0 violations (Table 5.8). The outcomes were:
- RUN NOW for the main branch and for a pull request;
- DEFER RECOMMENDED for an eligible build expected to take 549 s (about nine minutes);
- RUN NOW when the commit carried an `[urgent]` marker, or when the workflow had no completed
  history yet (cold start);
- a fail-safe RUN NOW when the region was missing or the event was not trusted.

A GitHub-hosted runner's region cannot be chosen or verified, so the real job declared its location as
`GITHUB-HOSTED`. The advisor returned a fail-safe RUN NOW (`region_not_gb`) on all six such jobs. The
Great Britain cases, including the deferral, were therefore shown in a clearly labelled scenario mode,
using a synthetic build of about nine minutes. They demonstrate that the system works end to end, not
that it saves carbon. In these runs the decision was recorded 13.89–21.43 s after the Action's first
step, including the time to set up Python.

The What-If reports replayed up to the last 500 completed runs of one workflow in each of four public
repositories through the same function (Table 5.9). None of the four would have had a build delayed:
- In awesome-go every run was triggered by `pull_request_target`, an event the advisor does not
  trust, so all 500 fell back safely to RUN NOW.
- In public-apis every analysed run was a pull request or a push to a protected branch.
- In spring-boot and rails, 24 runs (5.01%) and 64 runs (12.83%) were allowed to wait, but each had
  an *estimated* duration below the 480-second threshold.

The demonstration repository's own report delayed 2 of its 6 runs. All five reports regenerated byte
for byte from their saved snapshots. These are demonstrations, not research evidence, and the
thresholds were fitted on Travis CI data from 2011–2016. Even so, they mirror the replay result: on
real modern workflows, the eligibility rule and the duration threshold, not the choice of hour,
decide whether anything is delayed at all.

### 6.2.9 Limits on these findings

The findings must be read within the following limits:
- **Estimates, not measurements.** Carbon is estimated from a constant 42.5 W power figure and an
  hour-of-week average of the grid; no real energy was measured.
- **Old data.** The builds come from Travis CI between 2011 and 2016. Modern CI systems such as
  GitHub Actions may behave differently.
- **One grid.** Only Great Britain's grid (2024–2025) was tested. A second grid could not be tested,
  because the only free alternative varied less than Britain's.
- **Approximate urgency.** The eligibility rules approximate which builds may wait from the
  pull-request flag and branch name. The data contains no record of which builds were truly urgent, so
  the rules could be checked for consistency but not for correctness.
- **A policy fixed in advance is not the best possible on test data.** On the test projects, another
  setting of the same strategy (no duration threshold, 12-hour window) matched the frozen policy's
  saving (2.481%). It gave faster failure feedback (11.60 h at the 95th percentile, against 13.91 h)
  but delayed 18.10% of builds instead of 7.92% (Section 5.4.4). Choosing it now would be exactly the
  after-the-fact tuning the design forbids.
- **Demonstration, not deployment.** The prototype ran on a demonstration repository with a
  synthetic workload, and its GB deferrals were shown in scenario mode.
- **No user study.** How developers would accept delayed builds was not measured.

---

## 6.3 Achievements of Research Objectives

**Objective 01: To identify and analyse commit-level software engineering characteristics that may
influence selective carbon-aware scheduling decisions in CI/CD pipelines.**
*Achieved.* Twenty-eight characteristics that are known before a build runs were extracted from
TravisTorrent and arranged into six groups, and any field known only after the build was blocked.
Each group was tested on its own, beyond the duration estimate, with bootstrap confidence intervals on
two separate sets of projects, and SHAP was used to check which groups the models relied on. No group
added meaningful value; change size remains unresolved (Tables 5.5, 5.11).

**Objective 02: To develop an empirical decision model that evaluates the contribution of software
engineering characteristics beyond expected build duration for selective carbon-aware scheduling.**
*Achieved.* A two-step model was built: fixed rules first decide whether a build may wait, and an
evidence-derived policy then decides whether it is worth waiting. A commit-time duration estimate
served as the control, and an admission rule fixed in advance decided which groups could enter. The
contribution of commit characteristics was measured both in prediction (PR-AUC) and in decisions (the
gap between trade-off curves), and was found to be zero (Table 5.6).

**Objective 03: To derive and validate an evidence-based scheduling decision policy using empirical
analysis, feature importance analysis, and ablation studies.**
*Achieved.* The policy was produced automatically by a script, without hand tuning: delay a build
that may wait only if it is expected to take at least 480 seconds, to the cleanest hour within 24
hours. Its thresholds were fitted on calibration data, using models trained on the training projects.
Every threshold traces to a result file, the policy rebuilt byte for byte, it was unchanged by the
correction, and it was validated on 138,693 unseen builds and in the sensitivity tests (Sections
5.4.5, 5.4.6).

**Objective 04: To implement and evaluate a software prototype that operationalises the proposed
decision model within a carbon-aware CI/CD workflow using historical replay simulation.**
*Achieved.* A replay simulator ran six strategies on identical traces (14,146,686 decisions). The
policy was then delivered as a GitHub Action, a REST API and a What-If report that share the same
decision function, with 807 passing tests, seven real CI runs and five What-If reports. By a recorded
decision, the What-If report replaced the planned dashboard, and the optional automatic re-running of
delayed builds was not built. The prototype was evaluated as a demonstration, without a user study.

---

## 6.4 Answers to Research Questions

**RQ1. Which commit-level software engineering characteristics provide meaningful information for
selective carbon-aware scheduling decisions?**
Under the rule fixed in advance, **none** do once an estimate of build duration is available. Five of
the six groups made failure prediction worse, or better by less than the materiality floor. Change
size gave a small gain on the test projects only (+0.013), which did not appear on the calibration
projects, failed at double the floor and faded over time, so it is reported as unresolved. The
information that mattered was the project's own build history, and it mattered through its effect on
duration.

**RQ2. Do software engineering characteristics provide meaningful additional decision value beyond
expected build duration for identifying builds suitable for carbon-aware scheduling?**
**No.** No group passed the admission rule, so the evidence-derived policy is the duration-only
policy, and its trade-off curve is identical to the duration-only strategy (gap 0.0000 [0.0000,
0.0000]). This held at half, normal and double the floors, and in every sensitivity test in which it
could be evaluated. This "no" comes from a pipeline fixed in advance; the decision-level value of
change size on its own was not tested, because it was never admitted.

**RQ3. How can empirical relationships identified from software engineering characteristics be
transformed into an evidence-based decision policy for selective carbon-aware scheduling?**
Through a chain of steps fixed before the results were seen:
1. ablation with confidence intervals;
2. an admission rule with materiality floors;
3. an automatic fit of the thresholds on calibration data, which keeps at least 90% of the best
   carbon saving and then chooses the setting with the fastest failure feedback;
4. a frozen policy file that records where each number came from.

Here the chain produced a duration-only policy (480 s, 24 h). Had the evidence supported a group, the
same chain would have admitted it.

**RQ4. How effective is the proposed decision model compared with conventional CI scheduling
strategies and blanket carbon-aware scheduling under replay simulation?**
- **Against running every build immediately**, the policy saves an estimated 2.480% of CI carbon. It
  delays 7.92% of builds and adds 1.02 hours of delay on average across all builds.
- **Against blanket delay of up to a week**, it keeps a little over half the saving (2.480% against
  4.681%). In exchange, 95% of failure reports arrive within 13.91 hours instead of 127.01.
- **Against blanket delay of up to 24 hours**, it reports failures 5.91 hours sooner at the 95th
  percentile, for 9.6 g more carbon per 1,000 builds.

The direction of these results held in every sensitivity test.

---

## 6.5 Recommendations

1. **Use a simple rule before a complex one.** CI teams that want carbon-aware scheduling should
   start with two checks: a build may wait only if nobody is waiting for it (it is not a pull request
   and not on a protected branch), and only if it is expected to run for about eight minutes or more.
   It should then run at the cleanest hour within the next day. On this evidence, collecting commit
   characteristics for this purpose is not worth the extra complexity.

2. **Estimate duration from the project's own recent history.** The most cost-effective improvement
   is a better duration estimate. The median of the project's recent *finished* builds outperformed a
   model built on commit characteristics, and using only the last 50 builds did better still.

3. **Keep urgency separate, explicit and fail-safe.** Urgency should be decided by clear rules that
   teams can see and change (protected branches, pull requests, an `[urgent]` marker in the commit
   message), never by a risk score. A carbon tool should recommend rather than block, should fall
   back to RUN NOW whenever data is missing, and should use only the compute location that the team
   declares.

4. **Report the cost of delay alongside the carbon saved.** Tool builders and researchers should
   always publish the feedback delay, and the failures missed when builds are skipped, next to any
   carbon figure. CI providers should also publish runner location and energy data. Without them,
   carbon savings can only be estimated, as both this study and Saavedra et al. (2025) found.

---

## 6.6 Future Research

This study leaves several questions that future researchers can take further:

- **Modern CI data.** Repeat the study on recent GitHub Actions data, using job-level durations and
  current workflow practice, to check whether the null result holds outside Travis CI between 2011
  and 2016.
- **Change size at the decision level.** Test the change-size group directly in scheduling decisions,
  on new data and with rules fixed in advance, to settle whether its small prediction gain is real.
- **Other grids and live carbon signals.** Test grids with larger daily swings, marginal rather than
  average carbon intensity, and live forecasts instead of an hour-of-week average. The size of the
  saving, and possibly the ranking of strategies, may depend on these.
- **Measured energy.** Replace the constant-power estimate with measured energy, for example using
  hardware power measurement of the kind integrated into CI by Aneggi et al. (2026), to turn
  estimates into measurements.
- **Validated urgency and developer acceptance.** Collect real labels of which builds were urgent, and
  run a user study of how long developers will actually accept waiting. This would test the
  eligibility rules for correctness, not only consistency.
- **Better duration estimation.** Since this is where the gains were found, compare recent-window,
  job-level and workflow-aware estimators directly in scheduling decisions.
- **Combining strategies.** Study time shifting together with moving work to another region and with
  test selection or build skipping, always reporting the failures that are missed.
- **Live deployment.** Run the advisor with automatic re-running of delayed builds on real
  repositories over several months, and measure the delays, savings and developer responses that
  actually occur.

---

## 6.7 Conclusion

The aim of this research was to develop and validate an empirical decision model that determines
whether commit-level software engineering characteristics give meaningful extra value, beyond an
estimate of build duration, when choosing which CI builds should take part in carbon-aware
scheduling.

To meet this aim, 28 commit-time characteristics were extracted from the TravisTorrent dataset and
tested group by group against a duration estimate that a real CI system could compute when a commit
arrives. Projects were divided into training, calibration and test sets in time order, and the rules
for what would count as a meaningful improvement were fixed before any test result was seen. A
two-step decision model kept urgency (fixed rules) apart from the evidence-derived policy, and six
scheduling strategies were replayed on 138,693 unseen builds against the British grid's carbon
profile. The resulting policy was then delivered as a GitHub Action, a REST API and a What-If report
that call the same decision function as the evaluation.

The research provides three things:
1. **An empirical answer.** On this data, commit characteristics did **not** improve the choice of
   which builds to delay once a good duration estimate was available, and the one positive signal,
   change size, did not hold up.
2. **An evidence-derived policy that is simple, reproducible and safe.** Delay a build only if it may
   wait and is expected to take at least eight minutes, to the cleanest hour within a day. This saves
   an estimated 2.480% of CI carbon while keeping 95% of failure reports within 13.91 hours, a far
   better balance than blanket delay.
3. **A working, fail-safe advisor** that applies exactly the evaluated logic in a real CI workflow.

The research concludes that, for selective carbon-aware scheduling, the right question is not "what
else do we know about this commit?" but "may this build wait, and how long will it take?" The
practical gains lie in clear urgency rules and better duration estimates, not in more commit
characteristics. A null result reached through a design fixed in advance is a useful one: it tells
practitioners that a simple policy is enough and points future work at the factors that matter. These
conclusions rest on estimated carbon, historical Travis CI data and a single grid, and the future work
in Section 6.6 is needed before they can be generalised.

---

## 6.8 Chapter Summary

This chapter interpreted the results of Chapter 5 and closed the research. Its main finding is that
commit characteristics added no meaningful value beyond a duration estimate. The likely reasons are
that carbon saving follows duration, that failure prediction from commit-time information is weak,
and that patterns learned on some projects did not transfer to others. Change size was reported as
unresolved. The real gains came from estimating duration better, and the size of any saving was
limited mainly by how few builds may wait. The proposed policy offers a better balance between carbon
and feedback time than blanket scheduling, and the prototype showed that the same logic runs safely
in real CI.

All four objectives were achieved, with the dashboard replaced by a What-If report, and all four
research questions were answered. Four recommendations were made for practitioners and tool builders,
and eight directions were set out for future research, led by modern CI data, measured energy and
validated urgency.

---

> **Sources for this chapter (for the claims audit; move to an appendix or delete).**
> - **Objectives and RQ wording:** Chapter 1 (`../research-title.md`); active RQs in
>   `governance/01_SOURCE_OF_TRUTH.md` Layer 0-A.
> - **Sections 6.2.1–6.2.7 and 6.4:** Chapter 5 Tables 5.3–5.7 and 5.11 and Sections 5.4.5–5.4.6,
>   with the sources listed at the end of Chapter 5.
> - **Calibration-split PR-AUC (0.391, 0.311):** `results/p1/model_training.md`.
> - **Failure rates 25.04% / 28.55%:** `results/p1/splits_summary.md`.
> - **The ≈47% single-build ceiling:** `results/p2/energy_model.md` (−46.66%).
> - **The 90% carbon-retention rule (RQ3):** DL-024 §1, `results/p2/policy_derivation.md`.
> - **Change size not tested at the decision level:** DL-028 §1.
> - **Frozen point vs the d0/w12 setting:** `results/p3/strategy_results.csv` (rows
>   `5_se_informed_policy__d480__w24` and `4b_duration_prior__d0__w12`).
> - **Dashboard replaced by the What-If report:** DL-033 revision 3, R3-B1.
> - **Re-running of delayed builds not built:** DL-036 §8 and the P4-T2 gate record (S3 cut).
> - **Runner region:** DL-036 §1.
> - **Section 6.2.8:**
>   - `results/p4/pytest_p4_t3.txt` (807 passed);
>   - `results/p4/demo_runs/decisions.md` (7 runs, 13 decisions, 0 violations);
>   - `results/p4/demo_runs/step_latency.md`;
>   - `results/p4/whatif/*/report.md`;
>   - `results/p4/whatif/determinism.json`.
> - **Literature:** Claßen et al. (2023), Kamei et al. (2013), Mhalla & Saied (2024), Saavedra et al.
>   (2025) and Aneggi et al. (2026), as listed in the spec §8 references.

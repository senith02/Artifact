# Evaluation report — results synthesis and the four RQ verdicts (P3-T5)

> **Authored synthesis, written 2026-10-01 at P3-T5.** No new run was made for this report. No dataset
> row was read and the test split was not re-opened. **Every number below is copied from a result file
> produced by an earlier recorded run** (R1, R5). Each one carries a source key from the table below.
> The provenance footer (§10) lists the generating command for every source. Numbers were checked
> mechanically against their sources before the gate (§10.3).

**Source keys** (all paths relative to `Research_Artifact/`):

| key | file | produced by |
| :-- | :-- | :-- |
| **MR** | `results/p3/model_report.md` (+ `model_report.json`) | P3-T1 |
| **RT** | `results/p3/replication_table.md` | P3-T1 |
| **SHAP** | `results/p3/shap/shap_summary.md` | P3-T1 |
| **SR** | `results/p3/strategy_results.md` (+ `.csv`, `.json`) | P3-T2 |
| **IVD** | `results/p3/incremental_value_decision.md` (+ `.json`) | P3-T3 |
| **SENS** | `results/p3/sensitivity.md` (+ `sensitivity/*.json`, `sensitivity/reading.md`) | P3-T4 |
| **PD** | `results/p2/policy_derivation.md` (+ `policy_fit/`) | P2-T5 |
| **IV1** | `results/p1/incremental_value.md` (+ `admission.json`) | P1-T7 |
| **EM** | `results/p2/energy_model.md` | P2-T2 |
| **CP** | `results/p0/carbon_profile.md` | P0-T3 |
| **EP** | `results/p0/eval_protocol.md` (frozen + Amendment A1.1) | P0-T4, DL-012/013 |
| **DL-n** | `governance/03_DECISION_LOG.md` entry n | — |

---

## 0. The answer in one paragraph

On this corpus, with this feature contract and this carbon model, **commit-level SE characteristics
add no realised decision value beyond a commit-time estimate of build duration.** The
evidence-derived policy is therefore the **duration-only fallback**: the deterministic Stage-1 gate
plus "defer iff d̂ ≥ 480 s, into the greenest slot within 24 h" [PD]. On the 170 held-out test
projects that policy cuts estimated carbon by **2.480%** against immediate execution
(−70.7 [−78.5, −64.9] gCO₂e per 1,000 builds). It defers **7.92%** of builds and raises failed-build
TTFF p95 from 1.67 h to **13.89 h** [SR §3–§4]. Blanket carbon-aware scheduling saves more
(4.681%) but at a TTFF p95 of 127.01 h [SR §3]. One SE family, change size and diffusion (F1),
cleared the model-level floor on test after failing it on calibration. That result does not
replicate, is floor-sensitive, and was never tested at the decision level [MR §10, RT, DL-028 §1].
The data point to a different lever: a **better duration estimate**, not more SE features, is where
the measurable headroom lies [IVD §5, SENS S-h]. Under the predeclared rules (EP §A1.7, DL-012 §5)
this null is the study's principal finding, not a shortfall.

---

## 1. What was evaluated

- **Population.** Test split: **138,693 builds / 170 projects**, 25.0359% failure. It is
  project-disjoint from train (645,244 builds) and calibration (138,687 builds) [MR §1]. The trace runs
  2011-04-16 → 2016-08-31 [SR §1]. The test split was opened **once**, at P3-T1, and the frozen policy
  was replayed on it once, at P3-T2 (sentinels `results/p3/test_split_opened.json`,
  `results/p3/test_replay_opened.json`).
- **Frozen inputs.** `policy_spec.yaml` sha256 `34d689c9…`, loaded with `require_fitted=True` [SR];
  duration control fit id `1088d5546f47ff12`, primary form ④b (expanding per-project prior) [MR §9].
  All twelve classifier arms were loaded, not refit [MR]. **Nothing was fitted on test.**
- **Strategies** (Layer 0-A): ① immediate · ② blanket carbon-aware · ③ eligibility-only ·
  ④a duration estimator · ④b duration project-prior · ⑤ frozen evidence-derived policy ·
  ⑥ risk-only skip. Each was run on the identical build set at all 102 grid settings:
  **14,146,686** records, with **0** gate violations in 1,016,092 deferrals [SR §2].
- **The decision rule was fixed before the test split was opened** (EP §A1.7). An SE family is
  admitted only if (model level) ΔPR-AUC vs `{d̂}` has a CI excluding 0 and is ≥ +0.01, **and**
  (decision level) ⑤'s frontier dominates ④'s at ≥ 3 matched points by ≥ 5% relative TTFF p95 or
  ≥ 1% relative carbon saved. Both floors are re-run at ×0.5 and ×2.
- **Structural limit, declared in advance** (EP §A1.13). Energy is `P_avg · duration`, so carbon
  saved is proportional to duration by construction. SE value can only surface as **lower TTFF p95 at
  matched carbon**. Single-point carbon comparisons between ④ and ⑤ are context, never findings.

---

## 2. The four verdicts

### RQ1 — Which commit-level SE characteristics provide meaningful decision information?

**None was shown to carry decision information beyond what a commit-time duration estimate already
carries. One family, change size and diffusion (F1), is a candidate signal, not an established one.**
On the held-out test projects F1's increment over `{d̂}` clears the model-level floor, with ΔPR-AUC
**+0.013313 [+0.011924, +0.014733]** [MR §4]. Three qualifications apply:

- On the calibration projects the same frozen arm was significantly *worse* than the control
  (−0.003678 [−0.005310, −0.001958]) [RT].
- It is admitted at ×0.5 and ×1 of the floor but **not at ×2** [MR §4].
- Its decision-level value was **never tested** (DL-028 §1).

Across both halves of the test period it stays just above the floor: early +0.0127, late +0.0101
[SENS reading]. F6 (temporal & trigger context) is positive on test but below the floor (+0.002257)
[MR §4]. Test activity & maturity (F3), project history & maturity (F4), developer & team (F5) and,
less strongly, change purpose & composition (F2) are **significantly harmful** as additions to `d̂`
on both splits [RT]. (Family names: `context/feature_spec.md`.) Adding all 28
features together is worse than `d̂` alone for all three algorithms on test (ΔPR-AUC −0.007864,
−0.020635, −0.003347) [MR §4].

One finding is sharper than the null itself. **Attribution is not incremental value.** Inside the full
arm, SHAP ranks F4 and F3 as the two largest families by attribution (ranks 1 and 2 on both splits)
[SHAP §2], yet they are among the most harmful additions to the control (test ΔPR-AUC −0.019986 and
−0.033651) [MR §4]. The attribution structure is very stable between splits (Spearman 0.9960, top-10
overlap 10/10) [SHAP §3], while F1's incremental value flips sign. A feature-importance ranking alone
would have pointed to the wrong families.

### RQ2 — Do SE characteristics add decision value beyond a commit-time duration estimate?

**No, under the predeclared pipeline, and the verdict is stable.**

- **Model altitude.** On calibration, all six families were rejected, with CIs entirely below 0, at
  every floor [IV1 §2–§3]. The policy was frozen on that evidence. On test the admitted set is {F1} at
  ×1 and ×0.5 and empty at ×2, so it is not stable across the floor sweep [MR §4].
- **Decision altitude (the headline test).** The frozen spec admits no family, so ⑤ ≡ ④b. Against
  ④b, the area between frontiers is **+0.0000 [+0.0000, +0.0000]**, no matched point counts, and the
  condition fails at ×0.5, ×1 and ×2. "⑤ beats both ④a and ④b" (EP §A1.9) is therefore false at every
  floor [IVD §3]. The verdict holds under every sensitivity sweep and cannot flip in this design
  [SENS, V2].

This null must be stated at its actual strength:

1. It is a **null by construction of a pre-registered pipeline**, not an independent head-to-head test
   of an SE-informed policy on test data. No SE-informed policy was ever frozen. The decision altitude
   confirms the calibration-stage outcome and adds no new evidence about SE characteristics [IVD §6b].
2. **F1's decision-level value is untested.** By author decision, no post-hoc F1 arm was built
   (DL-028 §1). Building one now would be exploratory, would need its own DL entry, and could never be
   reported as confirmatory.
3. What the null precisely means is the claim EP §A1.13 predeclared: *no SE information orthogonal to
   predicted duration, detectable through feedback safety, on this dataset and carbon model.* It does
   **not** mean that SE characteristics are irrelevant to CI scheduling.
4. It is a **lower bound** on what SE characteristics could contribute. Two contracted features are
   constant in this release (DL-016), two textbook predictors (change entropy, commit-message fix
   keywords) cannot be built from it (DL-015), and one algorithm and one search budget were used for the family arms (DL-018/DL-019)
   [IV1 §5].

### RQ3 — How are the empirical findings transformed into an evidence-derived policy?

**Mechanically, reproducibly, and before the test split was opened. On this evidence the
transformation yields the duration-only fallback.** `scripts/fit_policy.py` fixes every element of
`policy_spec.yaml` from `results/` files [PD]:

| element | value | fixed by [source] |
| :-- | :-- | :-- |
| `policy_path` | `duration_only_fallback` | §A1.7 model-level rule re-applied to P1-T6 deltas; admitted set empty at ×0.5/×1/×2 [PD §1] |
| `d_threshold_seconds` | 480 | carbon-retention rule ρ = 0.90 over the 30 ④b calibration-sweep points (DL-024 §1); S* = 3.7787%, 5 of 30 points admissible, lowest TTFF p95 among them [PD §3] |
| `w_max_hours` | 24 | same rule, same sweep [PD §3] |
| `se_informed` block | absent | no admitted family [PD] |

- **Floor-insensitive, ρ-sensitive.** The ×0.5 and ×2 floor sweeps change no spec element [PD §5].
  The carbon-retention parameter does: ρ = 0.80 would have chosen d240/w12 (TTFF p95 11.3529 h on the
  fitting sample), and ρ = 0.95 would have chosen d240/w24 [PD §4]. ρ = 0.90 is a declared design
  parameter, not a measurement.
- **Reproducible.** A fully fresh refit is byte-identical (`results/p2/policy_fit/verify.json`).
- **Not moved by the test results.** F1's test-split result did not, and under "fit before you look"
  could not, alter the frozen spec [MR §10].
- **What RQ3 did not exercise.** The SE-informed branch (the §A1.8 window `w(p̂) = W_max·(1−p̂)` and
  its banded variant) exists in `decide()` and its unit tests, but no evaluated policy used it. The
  banded-shape sweep was therefore not applicable [SENS, S-b banded]. On this evidence RQ3's answer is
  a pipeline that **correctly declined** to encode SE characteristics, not one that shows how SE
  findings shape a window.

### RQ4 — How effective is the policy against conventional, blanket carbon-aware and duration-only scheduling?

**Modestly effective, and at a different point on the carbon–feedback trade-off than either
baseline. It is identical to duration-only scheduling with the project prior, which it is by
construction.** Headline operating points, 95% paired-bootstrap CIs, test trace [SR §3–§4]:

| strategy | deferred | gCO₂e / 1k builds | Δ vs ① | TTFF p95 h (failed) | ⑤ − other: Δ carbon / 1k | ⑤ − other: Δ TTFF p95 h |
| :-- | --: | :-- | --: | :-- | :-- | :-- |
| ① immediate | 0.00% | 2,849.6 [2,805.2, 2,895.6] | 0.000% | 1.67 [1.61, 1.76] | −70.7 [−78.5, −64.9] | +12.21 [+11.67, +12.59] |
| ② blanket carbon-aware (167 h) | 19.44% | 2,716.2 [2,673.8, 2,756.9] | −4.681% | 127.01 [125.00, 130.02] | +62.7 [+59.9, +66.1] | −113.13 [−116.02, −110.91] |
| ③ eligibility-only (24 h) | 18.74% | 2,769.3 [2,726.5, 2,811.8] | −2.815% | 19.81 [19.30, 20.03] | +9.6 [+9.2, +10.0] | −5.93 [−6.49, −5.40] |
| ④a duration estimator (d480/w24) | 9.42% | 2,780.8 [2,737.9, 2,823.6] | −2.411% | 14.07 [13.52, 14.43] | −2.0 [−2.4, −1.5] | −0.18 [−0.62, +0.16] |
| ④b duration prior (d480/w24) | 7.92% | 2,778.9 [2,736.0, 2,821.3] | −2.480% | 13.89 [13.36, 14.26] | 0 (identical) | 0 (identical) |
| **⑤ frozen policy** | **7.92%** | **2,778.9 [2,736.0, 2,821.3]** | **−2.480%** | **13.89 [13.36, 14.26]** | — | — |

- **Against conventional CI (①).** ⑤ saves 2.480% of estimated carbon. In exchange it adds 1.017 h of
  mean latency across all builds and +12.21 h to failed-build TTFF p95; deferrals are capped at 24 h
  [SR §4, §5b].
- **Against blanket carbon-aware scheduling (②).** ② saves almost twice as much (4.681%), but its
  failed-build TTFF p95 is 127.01 h. ⑤ is 113.13 h lower, at +62.7 gCO₂e per 1,000 builds [SR §4].
  ③ (eligibility-only) occupies the middle of that trade-off. Duration selectivity is what separates ⑤
  from ③: it avoids delaying short builds, buying 5.93 h of TTFF p95 for 9.6 gCO₂e per 1,000 builds
  [SR §5b].
- **Among ①, ⑤, ③ and ②, none dominates another on both axes.** Each step towards more carbon saved
  (① → ⑤ → ③ → ②) costs failed-build feedback time. The V4 sign pattern of ⑤ against ①, ② and ③
  confirms this pairwise [SENS, V4 baseline]. ⑥ saves carbon only by not running builds. At τ = 0.30
  it saves 14.532% but misses 6,689 failures (recall 0.8074) [SR §3].
- **Against duration-only scheduling.** ⑤ ≡ ④b. Against ④a at the frozen point, ⑤ saves 2.0 gCO₂e per
  1,000 builds more, and their TTFF p95 difference is not significant (−0.18 [−0.62, +0.16]) [SR §4].
  Across the whole swept frontier, **④b (≡ ⑤) dominates ④a**: the area is +2.4308 [+1.7358, +2.5684]
  pp·h and the condition holds at every floor [IVD §3]. That dominance is concentrated at 1.29–1.63%
  saved and is indistinguishable from 0 near the frozen point (+0.0360 [−1.7830, +0.7492] h). It
  reverses in the low failure-rate project band (−2.6750 [−4.2721, −1.3844]) [IVD §6, §6b]. This
  compares two duration controls and is not evidence about SE characteristics.
- **Why the saving is small.** At the frozen point, Stage 1 classes 111,666 of the 138,693 test builds
  as non-deferrable, so they run immediately. Of the remainder, 15,676 fall below the duration threshold
  and 369 find no greener slot within 24 h. That leaves 10,982 deferred builds [SR §5]. The UK
  hour-of-week profile also has a narrow range: 92.2400–172.9140 gCO₂/kWh, so even a perfect shift of
  a single build is capped at −46.66% [EM], with a peak-to-trough ratio of 1.8746 [SENS S-f].
- **Robustness.** The RQ4 sign pattern holds under every predeclared perturbation, with one exception
  at `W_max` = 12 h: there, ⑤'s TTFF p95 becomes *significantly lower* than ④a's instead of not
  significantly different. The perturbations covered are the stricter eligibility rule (eligible share
  14.02%), `P_avg` ×0.5/×1.5, and `n_jobs`-scaled energy [SENS]. Absolute gCO₂e scales with `P_avg`
  (1389.4 g and 4168.3 g per 1,000 builds at ×0.5 and ×1.5 [SENS S-c]); the comparisons between
  strategies do not.

---

## 3. Robustness of the verdicts (P3-T4)

The verdicts V1–V4 were defined in DL-030 §1 before any sweep ran [SENS]. **Two flips occurred, and
both are reported here rather than buried:**

| sweep | verdict that flips | what changes | does it change an RQ answer? |
| :-- | :-- | :-- | :-- |
| S-b, `W_max` = 12 h | V4 (RQ4 sign pattern), one of eight classes | ⑤ − ④a TTFF p95: not significant → significantly lower | No. At 12 h ⑤ is better than ④a, not worse. |
| S-e late period (76,038 builds) | V3 (④b over ④a) counting condition | area +3.5694 [+1.7615, +4.3448] stays positive, but the strongest matched points are undefined in 9–34% of resamples (> the predeclared 5%) | No. The direction holds; the counting rule fails on half the sample. |

- **V2 (RQ2, decision level)** is stable everywhere and cannot flip, because ⑤ ≡ ④b [SENS].
- **V1 ({F1})** holds early, late and with cold-start builds excluded (+0.0128), and is empty at ×2 in
  every case [SENS reading].
- **V3** keeps a positive area with its CI above 0 in every sweep that evaluates it. The range is
  +0.7500 [+0.5305, +1.1719] (early) to +5.9026 [+4.4703, +6.6558] (`n_jobs` energy) [SENS].
- **S-f (second grid) was not run** (DL-031, DL-032). CAISO's peak-to-trough ratio, 1.8669, does not
  exceed the UK's 1.8746, and Germany had no account-free intensity series [SENS S-f]. **Whether the
  strategy ranking holds on a more variable grid is untested.**

Figure: `results/p3/figures/sensitivity_v3_area.png`.

---

## 4. The negative result as a contribution

Layer 0-A and EP §A1.7 predeclared the null path as a valid outcome. What it contributes:

1. **A predeclared value-of-information answer for practitioners.** For deciding *which* CI builds to
   defer for carbon, a deterministic urgency gate plus a commit-time duration estimate from the
   project's own build history captured all the decision value this study could detect. Engineering
   28 commit-level SE features into the decision added none at the decision altitude, and the full set
   made the failure model worse [MR §4, IVD §6b]. The simpler policy is the defensible one, and it is
   cheap to deploy.
2. **Duration estimation is the lever.** Perfect duration knowledge (the oracle, unrealizable in
   deployment) moves the duration-only frontier outward by +1.9290 [+1.7625, +2.3492] pp·h [IVD §5].
   A trailing 50-build prior, a declared sensitivity and not the policy of record, recovers part of
   that: +0.3538 [+0.2370, +0.7650] over the frozen ④b [SENS S-h]. That trailing prior also has lower
   duration error on test (log1p MAE 0.3108 vs 0.5717) [MR §3]. Future effort belongs in better
   commit-time duration estimates.
3. **A methodological point that generalises.** Under any constant-power energy model, carbon saved is
   proportional to duration. A single-point comparison then measures how aggressively each strategy
   was configured, not how well it uses information (EP §A1.5, DL-013). SE value, if it exists, can
   only show up on the feedback-safety axis, at matched operating points. Studies that credit SE
   signals with carbon savings at a single operating point under such accounting are open to this
   confound.
4. **Feature importance is not decision value.** The families SHAP ranks highest (F4, F3) are among
   the most harmful additions to the control (§2, RQ1). Admission therefore has to be an incremental,
   paired test against a strong null, not an attribution ranking.
5. **The cost of blanket carbon-aware CI, quantified.** Gated blanket deferral (②) buys 4.681% at a
   failed-build TTFF p95 of 127.01 h. The selective policy buys 2.480% at 13.89 h [SR §3]. Practitioners
   can read that trade-off directly.

---

## 5. Limitations (restated, with the evidence that bounds each)

1. **Hour-of-week alignment.** The 2024–2025 UK hour-of-week mean profile [CP] is applied to builds
   from 2011–2016 [SR §1]. The replay measures *shiftability under a modern grid's shape*, not the
   carbon those builds emitted. Using the mean also suppresses within-slot variance, so a live
   deployment would be noisier in both directions [EM, threat 5].
2. **One low-variance grid; ranking invariance untested.** The UK peak-to-trough ratio is 1.8746. The
   predeclared second grid did not qualify (S-f not run, DL-032) [SENS]. The narrow range limits how
   far any policy can be separated on carbon.
3. **Estimator error in the duration control.** ④b's test log1p MAE is 0.5717 (MAE 807.0 s,
   median AE 182.0 s) [MR §3]. The oracle bound shows this error leaves measurable headroom [IVD §5].
   ④a has limited prediction support at the top of the threshold grid and defers nothing at
   D ≥ 3,840 s [PD §6]. Its frontier is reported only over the points it spans.
4. **Energy model.** `P_avg` = 42.5 W is CodeCarbon's constant-mode default for an unidentified CPU,
   not a measurement of Travis hardware. It has no RAM or GPU term, so absolute gCO₂e is biased
   **downward**. Wall-clock time under-counts parallel jobs (bracketed by the `n_jobs` variant, S-d).
   Constant power is what closes the carbon channel to RQ2 (EP §A1.13) [EM]. Relative comparisons are
   invariant to `P_avg` (S-c: identical V3 area at ×0.5 and ×1.5) [SENS]. Every absolute gCO₂e figure
   in this report is an estimate.
5. **Herding, and average vs marginal intensity.** The profile is average intensity and cannot
   represent the feedback of many builds moving into the same slot. ②'s largest slot receives 18.77×
   static's share. ⑤'s concentration is modest: 1.78× on the largest slot, 1.54× on the top five
   [SENS, herding]. At scale, ② in particular would erode its own savings.
6. **Project confound and split heterogeneity.**
   - Calibration and test differ in base rate (28.5492% vs 25.0359%) and duration tail (DL-017)
     [MR §10].
   - F1's sign flip between these project-disjoint splits means its increment is heterogeneous across
     projects [MR §10].
   - On test, F3 and F5 carry between-project SHAP shares of 0.5877 and 0.6586, and the control itself
     0.7422, so for those families redundancy with project identity is a live explanation [SHAP §2].
   - ④b's advantage over ④a reverses in the low failure-rate band [IVD §6].
   - The test split has 170 projects.
7. **The Stage-1 gate is an approximation** (DL-020). Two of the spec's six trigger classes, manual and
   scheduled, have no marker in the data. The gate's error rate cannot be measured, because no
   ground-truth deferability label exists. The 0 violations show consistency between the gate and the
   simulator, not that the gate is correct [SR §5b]. Under the stricter variant the verdicts are
   unchanged [SENS S-a].
8. **The SE side entered weakened** (DL-015, DL-016), and a single algorithm and budget were used for
   the family arms (DL-018, DL-019). The RQ1/RQ2 null is a lower bound [IV1 §5].
9. **F1 was not tested at the decision level** (DL-028 §1). This is the gap between the model-level and
   decision-level evidence.
10. **Age and temporal drift.** The corpus ends in 2016. In the late period the duration-control
    counting rule fails, and each period has about half the builds, so less power (DL-027) [SENS].
11. **Operating-point fitting noise.** The operating point was fitted on a 12,000-build calibration
    sample (8.65% of calibration builds), and its sampling noise is not bootstrapped [PD §9]. On test,
    the same point saved 2.480% with TTFF p95 13.89 h, against 3.4759% and 19.2027 h on the fitting
    sample [SR §3, PD §3]. Those are different populations, so the comparison is descriptive.
12. **Frontier resolution.** Each frontier has 30 grid points with piecewise-linear interpolation, and
    latency is hour-granular. Some matched-point CIs are wide and skewed at kinks, e.g. 1.6316% saved:
    +3.5062 [+0.9343, +3.5772] [IVD §6b].
13. **Classifier calibration out of sample.** Test ECE is 0.030–0.055. τ, chosen on calibration, is
    mis-centred: predicted-positive rates at τ are 0.54–0.98 against a base rate of 0.25 [MR §10]. This
    affects ⑥ and would affect any risk-based window; it does not affect ⑤ as frozen.

---

## 6. Claims this evidence does **not** support

- "SE characteristics are irrelevant to CI scheduling" (EP §A1.13; limitation 8).
- "F1 improves scheduling decisions." Its decision-level value is untested (DL-028 §1).
- "The policy saves 2.48% of real CI emissions." The figure is an estimate under a modern UK
  hour-of-week mean profile applied to 2011–2016 builds and a constant-power model (limitations 1, 4).
- "The strategy ranking holds on other grids." This is untested (S-f not run).
- "The Stage-1 gate identifies deferrable builds correctly." Its error rate cannot be measured
  (DL-020).
- Any comparison of the ROC-AUCs here with Mhalla & Saied (2024). That work addresses a different
  task, data and label [MR §7].

---

## 7. What the verdicts imply for the P4 contract (input to the DL-026 follow-up — not a decision)

DL-026 is Proposed/Conditional and must be accepted, amended or withdrawn by a **new** DL entry
before P4-T1. These are the facts that entry has to rest on:

- **What the frozen decision consumes.** Under the frozen spec, `decide()` reads Stage 1's
  `gh_is_pr` and `git_branch`, the arrival hour-of-week slot, and `d_hat_seconds`. It reads `p_hat`
  only on an SE path the spec does not contain (`code/scheduler_core/policy.py`; [PD]). **No SE feature
  is a decision input.**
- **What `d̂` requires live.** ④b is a per-project prior over the project's own strictly-earlier
  builds (DL-014). A live artifact needs a source of that project's past build durations to produce
  `d̂` with training/serving parity.
- **A tension in the current plan.** P4-T1 S2 specifies "request schema = the 28 commit features
  only". The frozen policy uses none of them, and it needs build history the 28 features do not carry.
  The P4 DL entry should resolve this.
- **Gaps that must be declared on the artifact.** Every value was fitted and evaluated on the UK
  national hour-of-week mean profile. Live forecasts and non-UK regions are outside what was evaluated,
  so the thresholds are extrapolated there, not validated (DL-026, condition 5; limitation 2).
- **F1 cannot enter the artifact** without a new DL entry, and it would then be exploratory
  (DL-028 §1).

---

## 8. Figures

| figure | shows | from |
| :-- | :-- | :-- |
| `results/p3/figures/frontiers.png` | ④a / ④b / ⑤ / oracle frontiers in the (carbon saved, TTFF p95) plane | P3-T3 |
| `results/p3/figures/frontiers_by_band.png` | the same, by project failure-rate tercile | P3-T3 |
| `results/p3/figures/sensitivity_v3_area.png` | V3 area across sweeps | P3-T4 |
| `results/p3/shap/family_importance.png` | per-family SHAP magnitude, calibration vs test | P3-T1 |
| `results/p3/calibration/reliability_*.png` (6) | test-split reliability diagrams per arm | P3-T1 |
| `results/p0/carbon_hour_of_week.png` | the UK 168-slot intensity profile | P0-T3 |

---

## 9. Status of each RQ answer

| RQ | answer | strength | carried limitation |
| :-- | :-- | :-- | :-- |
| RQ1 | No SE family shown to carry decision information beyond `d̂`; F1 a non-replicating model-level candidate | **null / modest** | §5 items 6, 8, 9 |
| RQ2 | No — ⑤ ≡ ④b, area +0.0000, fails at every floor; stable in every sweep | **null, by construction of the predeclared pipeline** | §5 items 8, 9; EP §A1.13 |
| RQ3 | Mechanical, reproducible fitting → duration-only spec (d480/w24); ρ-sensitive, floor-insensitive | answered; SE branch unexercised | §5 item 11 |
| RQ4 | −2.480% carbon vs ①, TTFF p95 13.89 h; less carbon than ② at far lower feedback cost; ≡ ④b, frontier-dominates ④a | **modest effect, robust in sign** | §5 items 1–5, 7 |

---

## 10. Provenance footer

### 10.1 Source files and the commands that generated them

All commands are run from `Research_Artifact/code/`.

| source | command | run |
| :-- | :-- | :-- |
| `results/p3/model_report.{md,json}`, `replication_table.md`, `shap/`, `calibration/`, `test_scores.csv.gz` | `PYTHONPATH=. python scripts/evaluate_test.py --split test --open-test-split` (rehearsal: `--split calibration`) | 2026-09-26 |
| `results/p3/strategy_results.{md,csv,json}`, `strategy_herding.csv`, `test_trace.csv.gz` | `PYTHONPATH=. python scripts/run_test_replay.py --mode test` (rehearsal: `--mode rehearse`) | 2026-09-26 |
| `results/p3/incremental_value_decision.{md,json}`, `figures/frontiers*.png` | `PYTHONPATH=. python scripts/frontier_analysis.py` | 2026-09-26 |
| `results/p3/sensitivity.md`, `sensitivity/*.json`, `figures/sensitivity_v3_area.png` | `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep {baseline,a,b,c,d,e,f,g,h,herding}`, then `--summary` | 2026-09-28 |
| `results/p2/policy_derivation.md`, `policy_fit/`, `code/scheduler_core/config/policy_spec.yaml` | `PYTHONPATH=. python scripts/fit_policy.py` | 2026-09-25 |
| `results/p1/incremental_value.md`, `admission.json` | `PYTHONPATH=. python scripts/apply_admission.py` (deltas from `scripts/run_ablation.py`) | 2026-09-13 |
| `results/p2/energy_model.md` | `PYTHONPATH=. python scripts/report_energy_model.py` | 2026-09-20 |
| `results/p0/carbon_profile.md`, `carbon_hour_of_week.png` | `python scripts/fetch_carbon.py` | 2026-06-20 |
| `results/p0/eval_protocol.md` | authored, frozen at P0-T4; Amendment A1.1 per DL-012/DL-013 | 2026-06-20 / 2026-08-09 |

### 10.2 Frozen artifacts these results depend on

- Split assignment `results/p1/split_assignment.csv`, sha256 `3d9a7947…5cde`.
- Policy `code/scheduler_core/config/policy_spec.yaml`, sha256 `34d689c9…07da3`.
- Duration control fit id `1088d5546f47ff12` (④b primary); `p̂` arm `xgboost:full` fit id
  `65fd81b1e952fd72`.
- Test replay records `results/p3/decisions.csv.gz` (untracked; sha256 pinned in
  `strategy_results.json`, DL-028 §4).

### 10.3 How this report was checked

This report introduces no measured number of its own. After it was written, every numeric token in
§0–§9 was extracted mechanically and searched for in the concatenated text of the source files keyed
above (Unicode minus normalised to ASCII). The command and its result are recorded in
`planning/PROGRESS.md` (P3-T5 ledger row). Tokens not found verbatim were each checked by hand and are
listed there with their resolution.

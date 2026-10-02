# Evaluation report — results synthesis and the four RQ verdicts (P3-T5, revised under DL-034)

> **Authored synthesis. First written 2026-10-01; revised 2026-10-02 under DL-034.** The revision
> replaces every number with the corrected rerun's value. DL-034 changed the duration control's
> history rule: an earlier build now counts only if it had *finished* before the scored build arrived.
> The revision also applies the wording corrections that DL-034 §B7 assigns to this report. No new run
> was made for this report, no dataset row was read, and the test split was not opened again. **Every
> number below is copied from a result file produced by a recorded run** (R1, R5). Each carries a
> source key from the table below; the provenance footer (§11) lists the commands, and §11.3 records
> the mechanical number check. The pre-DL-034 version is preserved at commit `4d9e128`. Every
> original-vs-corrected value is tabulated in `results/corrections/dl034/comparison.md` (**CMP**).

**Source keys** (all paths relative to `Research_Artifact/`):

| key | file | produced by |
| :-- | :-- | :-- |
| **MR** | `results/p3/model_report.md` (+ `model_report.json`) | P3-T1 (DL-034 rerun) |
| **RT** | `results/p3/replication_table.md` | P3-T1 |
| **SHAP** | `results/p3/shap/shap_summary.md` | P3-T1 |
| **SR** | `results/p3/strategy_results.md` (+ `.csv`, `.json`) | P3-T2 (DL-034 rerun) |
| **IVD** | `results/p3/incremental_value_decision.md` (+ `.json`) | P3-T3 (DL-034 rerun) |
| **SENS** | `results/p3/sensitivity.md` (+ `sensitivity/*.json`, `sensitivity/reading.md`) | P3-T4 (DL-034 rerun) |
| **PD** | `results/p2/policy_derivation.md` (+ `policy_fit/`) | P2-T5 (DL-034 rerun) |
| **IV1** | `results/p1/incremental_value.md` (+ `admission.json`) | P1-T7 (DL-034 rerun) |
| **EM** | `results/p2/energy_model.md` | P2-T2 |
| **CP** | `results/p0/carbon_profile.md` | P0-T3 |
| **EP** | `results/p0/eval_protocol.md` (frozen + Amendment A1.1) | P0-T4, DL-012/013 |
| **HO** | `results/corrections/dl034/history_overlap.md` | DL-034 evidence |
| **CMP** | `results/corrections/dl034/comparison.md` | DL-034 §B6 |
| **DL-n** | `governance/03_DECISION_LOG.md` entry n | — |

---

## 0. The answer in one paragraph

On this corpus, with this feature contract and this carbon model, the **calibration-frozen policy
realised no decision value from commit-level SE characteristics beyond a commit-time estimate of build
duration.** The evidence-derived policy is the **duration-only fallback**: the deterministic Stage-1
gate plus "defer iff d̂ ≥ 480 s, into the greenest slot within 24 h" [PD]. In replay on the 170
held-out test projects, that policy reduces **estimated** carbon by **2.480%** against immediate
execution (−70.7 [−78.5, −64.9] gCO₂e per 1,000 builds). It defers **7.92%** of builds and raises
failed-build TTFF p95 from 1.67 h to **13.91 h** [SR §3–§4]. Blanket carbon-aware scheduling reduces
estimated carbon more (4.681%) at a TTFF p95 of 127.01 h [SR §3]. One SE family, change size and
diffusion (F1), cleared the model-level floor on test after failing it on calibration. That signal
**remains unresolved**:
- it does not replicate between the splits;
- it is floor-sensitive;
- it falls below the floor in the late half of the test period;
- it was never tested at the decision level [MR §10, RT, SENS, DL-028 §1].

Within this replay, more accurate *duration* information, not more SE features, is where measurable
headroom lies [IVD §5, SENS S-h]. Under the predeclared rules (EP §A1.7, DL-012 §5) this null is the
study's principal finding, not a shortfall. These results survived the DL-034 correction of the
duration control with **no change to any RQ verdict** [CMP].

---

## 1. What was evaluated

- **Population.** The test split has **138,693 builds / 170 projects**, 25.0359% failure. It is
  project-disjoint from train (645,244 builds) and calibration (138,687 builds) [MR §1]. The trace runs
  from 2011-04-16 to 2016-08-31 [SR §1].
- **The study is a cross-project retrospective replay, not a time-forward deployment test.** The
  splits are project-disjoint but overlap in calendar time (DL-014 §Resolution 5).
- **Test-split access.** The test split was opened at P3-T1 and replayed at P3-T2. Under DL-034 it was
  opened a **second time**, by `--rerun-under DL-034`, to correct the duration-history rule. Both
  openings are chained in `results/p3/test_split_opened.json` and `results/p3/test_replay_opened.json`.
- **Frozen inputs.** `policy_spec.yaml` sha256 `e43b004d…`, loaded with `require_fitted=True`. Its
  thresholds and path are identical to the pre-DL-034 spec (`34d689c9…`); only two provenance lines
  differ [CMP]. The duration control has fit id `1088d5546f47ff12` (primary form ④b, expanding
  per-project prior of *finished* builds) [MR §9]. **Nothing was fitted on test.**
- **Strategies** (Layer 0-A): ① immediate · ② blanket carbon-aware · ③ eligibility-only ·
  ④a duration estimator · ④b duration project-prior · ⑤ frozen evidence-derived policy ·
  ⑥ risk-only skip. They were run on the identical build set at all 102 grid settings:
  **14,146,686** records, with **0** gate violations in 1,015,974 deferrals [SR §2].
- **The decision rule was fixed before the test split was first opened** (EP §A1.7). An SE family is
  admitted only if both conditions hold:
  - **Model level:** ΔPR-AUC vs `{d̂}` has a CI excluding 0 and is ≥ +0.01.
  - **Decision level:** ⑤'s frontier dominates ④'s at ≥ 3 matched points, by ≥ 5% relative TTFF p95
    or ≥ 1% relative carbon saved.
  Both floors are re-run at ×0.5 and ×2.
- **Structural limit, declared in advance** (EP §A1.13). Energy is `P_avg · duration`, so carbon saved
  is proportional to duration by construction. SE value can only surface as **lower TTFF p95 at
  matched carbon**.

---

## 2. The four verdicts

### RQ1 — Which commit-level SE characteristics provide meaningful decision information?

**None was shown to carry decision information beyond what a commit-time duration estimate already
carries. Change size and diffusion (F1) is an unresolved candidate, not an established signal.** On
the held-out test projects, F1's increment over `{d̂}` clears the model-level floor: ΔPR-AUC
**+0.013035 [+0.011639, +0.014500]** [MR §4]. But:

- on the calibration projects, the same frozen arm was significantly *worse* than the control
  (−0.003456 [−0.005189, −0.001728]) [RT];
- it is admitted at ×0.5 and ×1 of the floor but **not at ×2** [MR §4];
- in the **late half of the test period** it falls below the floor (+0.008974 [+0.007371,
  +0.010633]), while the early half is +0.012823 [+0.010681, +0.015001] [SENS reading];
- its decision-level value was **never tested** (DL-028 §1).

Under this feature contract and model budget, then, no SE family was admitted on calibration, and a
non-replicating F1 test signal remains unresolved.

The other families:
- F6 (temporal & trigger context) is positive on test but below the floor (+0.002831) [MR §4].
- Test activity & maturity (F3), project history & maturity (F4), developer & team (F5) and, less
  strongly, change purpose & composition (F2) are **significantly harmful** as additions to `d̂` on
  both splits [RT]. (Family names: `context/feature_spec.md`.)
- Adding all 28 features together is worse than `d̂` alone for all three algorithms on test
  (ΔPR-AUC −0.021611, −0.020534, −0.011171) [MR §4].
- These are six family comparisons with no multiplicity adjustment. The predeclared materiality floor
  mitigates selection risk but does not remove it.

**Attribution is not incremental value.** Inside the full arm, SHAP ranks F4 and F3 as the two largest
families by attribution, ranks 1 and 2 on both splits [SHAP §2]. Yet both are harmful additions to the
control (test ΔPR-AUC −0.009683 and −0.032535) [MR §4]. The attribution structure is stable between
splits (Spearman 0.9905, top-10 overlap 10/10) [SHAP §3], while F1's incremental value flips sign.
SHAP describes contributions inside one fitted model; it is not evidence of decision value.

### RQ2 — Do SE characteristics add decision value beyond a commit-time duration estimate?

**For the calibration-frozen policy, no. Whether SE characteristics could add value in some other
policy remains open.**

- **Model altitude.** On calibration, all six families were rejected with CIs entirely below 0, at
  every floor [IV1 §2–§3], and the policy was frozen on that evidence. On test the admitted set is
  {F1} at ×1 and ×0.5 and empty at ×2, so it is not stable [MR §4].
- **Decision altitude (the headline test).** The frozen spec admits no family, so ⑤ ≡ ④b. Against ④b
  the area between frontiers is **+0.0000 [+0.0000, +0.0000]**, no matched point counts, and the
  condition fails at ×0.5, ×1 and ×2. "⑤ beats both ④a and ④b" (EP §A1.9) is therefore false at every
  floor [IVD §3]. This holds under every sensitivity sweep, and it cannot flip in this design [SENS, V2].

This null has to be stated at its actual strength:

1. It is a **frozen-policy null, by construction** of a pre-registered pipeline. It is not an
   independent head-to-head test of an SE-informed policy on test data. No SE-informed policy was
   ever frozen, so the headline comparison could not detect SE value [IVD §6b].
2. **F1's decision-level value is untested** (DL-028 §1). Testing it now would be exploratory, would
   need its own DL entry, and could never be reported as confirmatory.
3. What the null means is exactly what EP §A1.13 predeclared: *no SE information orthogonal to
   predicted duration, detectable through feedback safety, on this dataset and carbon model.* It does
   **not** mean that SE characteristics are irrelevant to CI scheduling.
4. It is a **lower bound** on what SE characteristics could contribute. Two contracted features are
   constant (DL-016), two textbook predictors (change entropy, commit-message fix keywords) cannot be
   built from this release (DL-015), and one algorithm and one search budget were used (DL-018/DL-019)
   [IV1 §5].

### RQ3 — How are the empirical findings transformed into an evidence-derived policy?

**Mechanically, reproducibly, and before the test split was opened. On this evidence the
transformation yields the duration-only fallback, and it yielded the same policy after the DL-034
correction.** `scripts/fit_policy.py` fixes every element of `policy_spec.yaml` from `results/` files
[PD]:

| element | value | fixed by [source] |
| :-- | :-- | :-- |
| `policy_path` | `duration_only_fallback` | §A1.7 model-level rule re-applied to P1-T6 deltas; admitted set empty at ×0.5/×1/×2 [PD §1] |
| `d_threshold_seconds` | 480 | carbon-retention rule ρ = 0.90 over the 30 ④b calibration-sweep points (DL-024 §1); S* = 3.778732%, 5 of 30 points admissible, lowest TTFF p95 among them [PD §3] |
| `w_max_hours` | 24 | same rule, same sweep [PD §3] |
| `se_informed` block | absent | no admitted family [PD] |

- **Floor-insensitive, ρ-sensitive.** The ×0.5 and ×2 floor sweeps change no spec element [PD §5].
  The carbon-retention parameter does: ρ = 0.80 would have chosen d240/w12 (TTFF p95 11.3529 h on the
  fitting sample), and ρ = 0.95 d240/w24 [PD §4]. ρ = 0.90 is a declared design parameter.
- **Reproducible.** A fully fresh refit is byte-identical (`results/p2/policy_fit/verify.json`).
- **Robust to the DL-034 correction.** The corrected refit chose the same point. Its fitting-sample
  saving moved from 3.475905% to 3.475751%, with TTFF p95 unchanged [CMP].
- **What RQ3 did not exercise.** The SE-informed branch (the §A1.8 window `w(p̂) = W_max·(1−p̂)` and
  its banded variant) exists in `decide()` and its unit tests, but no evaluated policy used it [SENS,
  S-b banded]. RQ3's answer is a pipeline that **correctly declined** to encode SE characteristics.

### RQ4 — How effective is the policy against conventional, blanket carbon-aware and duration-only scheduling?

**Modestly effective in replay, at a different point on the carbon–feedback trade-off than either
baseline. It is identical to duration-only scheduling with the project prior, by construction.**
Headline operating points, 95% paired-bootstrap CIs, test trace [SR §3–§4]. Carbon figures are
**estimated under the replay energy model and the UK hour-of-week intensity profile**.

| strategy | deferred | est. gCO₂e / 1k builds | Δ vs ① | TTFF p95 h (failed) | ⑤ − other: Δ carbon / 1k | ⑤ − other: Δ TTFF p95 h |
| :-- | --: | :-- | --: | :-- | :-- | :-- |
| ① immediate | 0.00% | 2,849.6 [2,805.2, 2,895.6] | 0.000% | 1.67 [1.61, 1.76] | −70.7 [−78.5, −64.9] | +12.24 [+11.67, +12.60] |
| ② blanket carbon-aware (167 h) | 19.44% | 2,716.2 [2,673.8, 2,756.9] | −4.681% | 127.01 [125.00, 130.02] | +62.7 [+60.0, +66.1] | −113.11 [−116.00, −110.90] |
| ③ eligibility-only (24 h) | 18.74% | 2,769.3 [2,726.5, 2,811.8] | −2.815% | 19.81 [19.30, 20.03] | +9.6 [+9.2, +10.0] | −5.91 [−6.49, −5.39] |
| ④a duration estimator (d480/w24) | 9.42% | 2,780.8 [2,737.9, 2,823.6] | −2.411% | 14.07 [13.52, 14.43] | −2.0 [−2.4, −1.5] | −0.16 [−0.61, +0.18] |
| ④b duration prior (d480/w24) | 7.92% | 2,778.9 [2,736.0, 2,821.3] | −2.480% | 13.91 [13.36, 14.27] | 0 (identical) | 0 (identical) |
| **⑤ frozen policy** | **7.92%** | **2,778.9 [2,736.0, 2,821.3]** | **−2.480%** | **13.91 [13.36, 14.27]** | — | — |

- **Against conventional CI (①).** ⑤ reduces estimated carbon by 2.480%. In exchange it adds 1.017 h
  of mean latency across all builds and +12.24 h to failed-build TTFF p95, with deferrals capped at
  24 h [SR §4, §5b].
- **Against blanket carbon-aware scheduling (②).** ② reduces estimated carbon almost twice as much
  (4.681%), but its failed-build TTFF p95 is 127.01 h. ⑤'s is 113.11 h lower, at +62.7 gCO₂e per
  1,000 builds [SR §4].
- **Against eligibility-only (③).** ③ sits in the middle of that trade-off. Duration selectivity is
  what separates ⑤ from ③: ⑤ trades 9.6 gCO₂e per 1,000 builds for 5.91 h of TTFF p95 [SR §5b].
- **Among ①, ⑤, ③ and ②, none dominates another on both axes.** Each step towards more carbon saved
  (① → ⑤ → ③ → ②) costs failed-build feedback time [SENS, V4 baseline].
- **⑥ is not comparable on carbon alone.** It reduces carbon only by *not running* builds. At τ = 0.20
  and 0.25 it reduces estimated carbon more than ⑤ (5.471% and 6.457%), but misses 680 and 1,156
  failures (recall 0.9804 and 0.9667). At τ = 0.30 it reaches 15.205% while missing 7,054 failures
  (recall 0.7968) [SR §3, §5b]. Under DL-034 its mid-τ ordering against ⑤
  changed, because `p̂` was refitted [CMP].
- **Against duration-only scheduling.** ⑤ ≡ ④b. Against ④a at the frozen point, ⑤ is 2.0 gCO₂e per
  1,000 builds lower, and their TTFF p95 difference is not significant (−0.16 [−0.61, +0.18]) [SR §4].
  - Across the swept frontier, **④b (≡ ⑤) dominates ④a**: area +2.4262 [+1.7281, +2.5624] pp·h, with
    the condition holding at every floor [IVD §3].
  - The dominance is concentrated at 1.29–1.63% saved, and is indistinguishable from 0 near the
    frozen point (+0.0350 [−1.7958, +0.7479] h).
  - It reverses in the low failure-rate band (−2.7027 [−4.3027, −1.4037]) [IVD §6, §6b].
  - This compares two duration controls, which differ in both estimator form and history access. It
    is not evidence about SE characteristics.
- **Why the saving is small.** At the frozen point, Stage 1 classes 111,666 of the 138,693 test builds
  as non-deferrable. Of the rest, 15,675 fall below the threshold and 369 find no greener slot, which
  leaves 10,983 deferred [SR §5]. The UK profile spans 92.2400–172.9140 gCO₂/kWh. A perfect shift of a
  single build is capped at −46.66% [EM], and the profile's peak-to-trough ratio is 1.8746
  [SENS S-f].
- **Robustness.** The RQ4 sign pattern holds under every predeclared perturbation except one class at
  `W_max` = 12 h, where ⑤'s TTFF p95 becomes *significantly lower* than ④a's [SENS]. The
  perturbations are: the stricter eligibility rule (eligible share 14.02%), `P_avg` ×0.5/×1.5 and
  `n_jobs` energy. Absolute gCO₂e scales with `P_avg` (1389.4 g and 4168.3 g per 1,000 builds at ×0.5
  and ×1.5 [SENS S-c]); the comparisons between strategies do not.

---

## 3. Robustness of the verdicts (P3-T4)

The verdicts V1–V4 were defined in DL-030 §1 before any sweep ran [SENS]. **Three flips occurred, and
all are reported here rather than buried:**

| sweep | verdict that flips | what changes | does it change an RQ answer? |
| :-- | :-- | :-- | :-- |
| S-e late period (76,038 builds) | **V1 (model-level admitted set)** — *new under DL-034* | {F1} → ∅: F1 +0.008974 [+0.007371, +0.010633], below the +0.01 floor | No. It strengthens "F1 is unresolved" (RQ1). |
| S-e late period | V3 (④b over ④a) counting condition | area +3.5552 [+1.7470, +4.3365] stays positive, but the strongest matched points are undefined in 9–34% of resamples (over the predeclared 5% limit) | No. The direction holds; the counting rule fails on half the sample. |
| S-b, `W_max` = 12 h | V4 (RQ4 sign pattern), one of eight classes | ⑤ − ④a TTFF p95: not significant → significantly lower | No. At 12 h ⑤ is better than ④a, not worse. |

- **V2 (RQ2, decision level)** is stable everywhere and cannot flip [SENS].
- **V1** holds early (+0.012823) and with cold-start builds excluded (+0.012514). It is empty at ×2 in
  every case [SENS reading].
- **V3** keeps a positive area with its CI above 0 in every sweep that evaluates it, from +0.7451
  [+0.5199, +1.1666] (early) to +5.8957 [+4.4605, +6.6478] (`n_jobs` energy) [SENS].
- **S-f (second grid) was not run** (DL-031, DL-032). CAISO's peak-to-trough ratio (1.8669) did not
  exceed the UK's (1.8746), and Germany had no account-free series [SENS S-f]. **Cross-grid ranking
  invariance is untested.**

Figure: `results/p3/figures/sensitivity_v3_area.png`.

---

## 4. What the DL-034 correction changed

The duration control originally admitted earlier builds that had *started* but not *finished* before
the scored build. That affected 38,019 of 138,693 test builds (27.41%), typically one unfinished build
per history (median 1), and moved `d̂` by a median of 0.00% [HO]. The whole chain was re-run under
the corrected rule (DL-034 §B3). In summary [CMP]:

- **No RQ verdict changed.** The calibration admitted set is still empty, so the policy is still
  duration-only, at the same operating point (d480/w24). The headline RQ2 decision test is still a
  frozen-policy null. ④b still dominates ④a, and the oracle headroom remains.
- **Two findings changed:**
  - F1's late-period model-level admission flipped to ∅ (§3).
  - ⑥ now reduces estimated carbon more than ⑤ at τ = 0.20/0.25, with many more missed failures
    (§2, RQ4).
- **Numbers moved slightly elsewhere.** For example, ⑤'s TTFF p95 is 13.91 h, from 13.89 h, and F1's
  test ΔPR-AUC is +0.013035, from +0.013313. CMP lists all 182 compared quantities: 57 changed and
  125 unchanged.

---

## 5. The negative result as a contribution

Layer 0-A and EP §A1.7 predeclared the null path as a valid outcome. What it contributes:

1. **A predeclared value-of-information answer.** For deciding *which* CI builds to defer for carbon in
   this replay, a deterministic urgency gate plus a duration estimate from the project's own
   finished-build history captured all the decision value the study could detect. Twenty-eight
   commit-level SE features added none at the decision altitude, and the full set made the failure
   model worse [MR §4, IVD §6b]. The simpler policy is the defensible one. It is a hypothesis for a
   modern-CI pilot, not a demonstrated modern-CI result.
2. **More accurate duration information is associated with a better trade-off.** Perfect duration
   knowledge (oracle, unrealizable in deployment) moves the duration-only frontier outward by +1.9336
   [+1.7688, +2.3548] pp·h [IVD §5]. A trailing 50-build prior, a declared sensitivity, recovers part
   of that: +0.3622 [+0.2382, +0.7770] over the frozen ④b [SENS S-h]. It also has lower duration error
   on test (log1p MAE 0.3128 vs 0.5727) [MR §3]. Both comparisons hold the decision rule fixed and
   vary only the duration information, so within this replay they support improving commit-time
   duration estimates. The ④a-vs-④b comparison does not isolate this, because it changes estimator
   form and history access together.
3. **A methodological point that generalises.** Under any constant-power energy model, carbon saved is
   proportional to duration. A single-point comparison then measures how aggressively each strategy
   was configured, not how well it uses information (EP §A1.5, DL-013). SE value can only show up on
   the feedback-safety axis, at matched operating points.
4. **Feature importance is not decision value.** The families SHAP ranks highest (F4, F3) are harmful
   additions to the control (§2, RQ1). Admission has to be an incremental, paired test against a
   strong null.
5. **The cost of blanket carbon-aware CI, quantified in replay.** Gated blanket deferral (②) buys a
   4.681% estimated reduction at a failed-build TTFF p95 of 127.01 h. The selective policy buys 2.480%
   at 13.91 h [SR §3].

---

## 6. Limitations (restated, with the evidence that bounds each)

1. **Hour-of-week alignment.** The 2024–2025 UK hour-of-week mean profile [CP] is applied to builds
   from 2011–2016 [SR §1]. The replay measures *shiftability under a modern grid's shape*, not the
   carbon those builds emitted, and the mean suppresses within-slot variance [EM, threat 5].
2. **One low-variance grid; ranking invariance untested.** UK peak-to-trough is 1.8746, and the second
   grid did not qualify (DL-032) [SENS].
3. **Estimator error, and the completion proxy.**
   - ④b's test log1p MAE is 0.5727 (MAE 808.3 s, median AE 183.0 s) [MR §3], and the oracle shows
     measurable headroom [IVD §5].
   - Completion is approximated as start + `tr_duration`, the *earliest* possible finish, because the
     release has no finish timestamp (DL-034 §B1). The corrected history may still admit a build
     slightly early.
   - ④a defers nothing at D ≥ 3,840 s [PD §6].
4. **Energy model.**
   - `P_avg` = 42.5 W is a constant-mode default for an unidentified CPU, with no RAM or GPU term, so
     absolute gCO₂e is biased **downward** [EM].
   - Wall-clock time under-counts parallel jobs (S-d brackets this).
   - Constant power closes the carbon channel to RQ2 (EP §A1.13).
   - Comparisons between strategies are invariant to `P_avg` (S-c) [SENS]. Every gCO₂e figure is an
     estimate.
5. **Herding, and average vs marginal intensity.** ②'s largest slot receives 18.77× static's share;
   ⑤'s concentration is 1.77× (largest slot) and 1.54× (top five) [SENS, herding]. The average profile
   cannot represent that feedback.
6. **Project confound and split heterogeneity.**
   - Calibration and test differ in base rate (28.5492% vs 25.0359%) and duration tail (DL-017)
     [MR §10].
   - F1's sign flips between the project-disjoint splits [RT], and it is not stable across time on
     test [SENS].
   - On test, F3 and F5 carry between-project SHAP shares of 0.6256 and 0.7595, and the control 0.7636
     [SHAP §2].
   - ④b's advantage over ④a reverses in the low failure-rate band [IVD §6].
   - The test split has 170 projects.
7. **The Stage-1 gate is an approximation** (DL-020).
   - Manual and scheduled trigger classes have no marker in the data.
   - The gate's error rate cannot be measured, so 0 violations show consistency with the rule, not
     that the rule is correct [SR §5b]. Builds are "eligible under the rule", not shown to be safe to
     delay.
   - The verdicts are unchanged under the stricter variant [SENS S-a].
8. **The SE side entered weakened** (DL-015, DL-016), with one algorithm and budget (DL-018, DL-019)
   and six family comparisons without a multiplicity adjustment. The RQ1/RQ2 null is a lower bound
   [IV1 §5].
9. **F1 was not tested at the decision level** (DL-028 §1).
10. **Age, temporal drift and temporal overlap.**
    - The corpus ends in 2016.
    - The splits are project-disjoint but not time-forward, so the study is a cross-project
      retrospective replay (DL-014 §Resolution 5).
    - In the late period both F1's admission and the duration-control counting rule fail, and each
      period has about half the builds (DL-027) [SENS].
11. **The test split was read twice.** The second pass was authorised by DL-034 to correct the
    information rule. Its rules were fixed before any corrected number existed, but the author had
    seen the original test results (DL-034 §B5).
12. **Operating-point fitting noise.** The point was fitted on a 12,000-build calibration sample
    (8.65%), and its sampling noise is not bootstrapped [PD §9]. On test the same point gave 2.480% and
    13.91 h, against 3.475751% and 19.2027 h on the fitting sample [SR §3, PD §3]. These are different
    populations, so the comparison is descriptive.
13. **Frontier resolution.** Each frontier has 30 grid points with piecewise-linear interpolation, and
    latency is hour-granular. Some matched-point CIs are wide at kinks, e.g. 1.6316% saved: +3.5080
    [+0.9323, +3.5785] [IVD §6b].
14. **Classifier calibration out of sample.** Test ECE is 0.027620–0.058682. Predicted-positive rates at
    τ are 0.4916–0.9422 against a base rate of 0.25 [MR §10]. This affects ⑥ and any risk-based window,
    not ⑤ as frozen.

---

## 7. Claims this evidence does **not** support

- "SE characteristics are irrelevant to CI scheduling" (EP §A1.13; limitation 8).
- "SE characteristics add no value in any policy." Only the calibration-frozen policy was tested.
- "F1 improves scheduling decisions." It is unresolved, and its decision-level value is untested.
- "The policy saves 2.48% of real CI emissions." The figure is an estimated reduction under a modern
  UK hour-of-week mean profile and a constant-power model (limitations 1, 4).
- "The strategy ranking holds on other grids." This is untested.
- "Eligible builds are safe to defer." The gate is an unvalidated proxy (DL-020).
- "This transfers to modern GitHub Actions." The corpus is Travis CI, 2011–2016.
- Any comparison of the ROC-AUCs here with Mhalla & Saied (2024), which is a different task, data and
  label [MR §7].

---

## 8. What the verdicts imply for the P4 contract (input to DL-033 — not a decision)

DL-026's follow-up is drafted as **DL-033** (Proposed, draft revision 2). It is re-checked against
these corrected results before acceptance:

- **What the frozen decision consumes.** `decide()` reads `gh_is_pr`, `git_branch`, the arrival
  hour-of-week slot and `d_hat_seconds`; `p_hat` only on an SE path the spec does not contain
  (`code/scheduler_core/policy.py`; [PD]). **No SE feature is a decision input.** The corrected rerun
  admitted no family on calibration, so DL-033 §B does not need re-drafting.
- **What `d̂` requires live.** ④b is a per-project median of the project's **finished** builds before
  arrival (DL-034). A live artifact must therefore use completed runs only, which DL-033 §B2 now
  requires.
- **A tension in the current plan.** P4-T1 S2's "28 commit features only" schema carries none of the
  frozen policy's inputs. DL-033 resolves it.
- **Gaps that must be declared on the artifact.** The policy was fitted and evaluated on the UK
  hour-of-week mean profile only. Live forecasts and non-UK regions are outside what was evaluated
  (DL-026 condition 5; limitation 2).
- **F1 cannot enter the artifact** without a new DL entry, and would then be exploratory (DL-028 §1).

---

## 9. Figures

| figure | shows | from |
| :-- | :-- | :-- |
| `results/p3/figures/frontiers.png` | ④a / ④b / ⑤ / oracle frontiers in the (carbon saved, TTFF p95) plane | P3-T3 |
| `results/p3/figures/frontiers_by_band.png` | the same, by project failure-rate tercile | P3-T3 |
| `results/p3/figures/sensitivity_v3_area.png` | V3 area across sweeps | P3-T4 |
| `results/p3/shap/family_importance.png` | per-family SHAP magnitude, calibration vs test | P3-T1 |
| `results/p3/calibration/reliability_*.png` (6) | test-split reliability diagrams per arm | P3-T1 |
| `results/p0/carbon_hour_of_week.png` | the UK 168-slot intensity profile | P0-T3 |

---

## 10. Status of each RQ answer

| RQ | answer | strength | carried limitation |
| :-- | :-- | :-- | :-- |
| RQ1 | No SE family shown to carry decision information beyond `d̂`; F1 an unresolved, non-replicating, time-unstable model-level candidate | **null / modest** | §6 items 6, 8, 9, 10 |
| RQ2 | No, for the calibration-frozen policy: ⑤ ≡ ④b, area +0.0000, fails at every floor; stable in every sweep | **frozen-policy null, by construction** | §6 items 8, 9, 11; EP §A1.13 |
| RQ3 | Mechanical, reproducible fitting → duration-only spec (d480/w24), unchanged by DL-034; ρ-sensitive, floor-insensitive | answered; SE branch unexercised | §6 item 12 |
| RQ4 | −2.480% estimated carbon vs ①, TTFF p95 13.91 h; less carbon than ② at far lower feedback cost; ≡ ④b, frontier-dominates ④a | **modest effect in replay, robust in sign** | §6 items 1–5, 7 |

---

## 11. Provenance footer

### 11.1 Source files and the commands that generated them

All commands are run from `Research_Artifact/code/`.

| source | command | run |
| :-- | :-- | :-- |
| `results/corrections/dl034/history_overlap.{md,json}` | `PYTHONPATH=. python scripts/diagnose_history_overlap.py` | 2026-10-01 |
| `results/p1/` (P1-T4 … P1-T7) | `fit_duration_estimator.py`; `train_models.py --fresh`; `run_ablation.py --fresh`; `apply_admission.py` (each `PYTHONPATH=. python scripts/…`) | 2026-10-01 |
| `results/p2/policy_derivation.md`, `policy_fit/`, `policy_spec.yaml` | `PYTHONPATH=. python scripts/fit_policy.py --fresh`, then `--verify --fresh --out <scratch>` | 2026-10-01 |
| `results/p3/model_report.{md,json}`, `replication_table.md`, `shap/`, `calibration/`, `test_scores.csv.gz` | `PYTHONPATH=. python scripts/evaluate_test.py --split calibration`, then `--split test --open-test-split --rerun-under DL-034` | 2026-10-01 |
| `results/p3/strategy_results.{md,csv,json}`, `strategy_herding.csv`, `test_trace.csv.gz` | `PYTHONPATH=. python scripts/run_test_replay.py --mode rehearse`, then `--mode test --rerun-under DL-034` | 2026-10-02 |
| `results/p3/incremental_value_decision.{md,json}`, `figures/frontiers*.png` | `PYTHONPATH=. python scripts/frontier_analysis.py` | 2026-10-02 |
| `results/p3/sensitivity.md`, `sensitivity/*.json`, `figures/sensitivity_v3_area.png` | `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep {baseline,a,b,c,d,e,f,g,h,herding}`, then `--summary` | 2026-10-02 |
| `results/corrections/dl034/comparison.md` | `PYTHONPATH=. python scripts/dl034_comparison.py` | 2026-10-02 |
| `results/p2/energy_model.md` | `PYTHONPATH=. python scripts/report_energy_model.py` | 2026-09-20 |
| `results/p0/carbon_profile.md`, `carbon_hour_of_week.png` | `python scripts/fetch_carbon.py` | 2026-06-20 |
| `results/p0/eval_protocol.md` | authored, frozen at P0-T4; Amendment A1.1 per DL-012/DL-013 | 2026-06-20 / 2026-08-09 |

### 11.2 Frozen artifacts these results depend on

- Split assignment `results/p1/split_assignment.csv`, sha256 `3d9a7947…5cde`.
- Policy `code/scheduler_core/config/policy_spec.yaml`, sha256 `e43b004d…`; the pre-DL-034 spec was
  `34d689c9…`, with identical thresholds and path.
- Duration control fit id `1088d5546f47ff12` (④b primary, completion-causal history, DL-034).
  `p̂` arm `xgboost:full` fit id `a09cc750e9db41b8`.
- Test replay records `results/p3/decisions.csv.gz` (untracked; sha256 pinned in
  `strategy_results.json`, DL-028 §4).

### 11.3 How this report was checked

This report introduces no measured number of its own. After it was written, every numeric token in
§0–§10 was extracted mechanically and searched for in the concatenated text of the source files keyed
above (Unicode minus normalised to ASCII). The result is recorded in `planning/PROGRESS.md` (CR-1
gate).

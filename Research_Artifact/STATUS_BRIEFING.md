# Status Briefing — plain-language catch-up

> **Not a governance file.** This is a human-readable summary for the author to re-orient quickly.
> It is not authoritative — if it ever disagrees with `planning/PROGRESS.md` or
> `governance/03_DECISION_LOG.md`, those win. **Last updated 2026-09-19** (previous version 2026-09-10,
> written when P1-T5 was the newest work).

---

## 1. What this research actually is (one paragraph)

A BSc thesis asking: when a Git commit triggers a CI build, is it worth trying to shift that build to a
greener time window (carbon-aware scheduling)? Specifically — **does knowing things about the commit
itself** (how big the diff is, how many tests it touches, who wrote it, etc. — "SE characteristics")
**help decide which builds to defer, over and above just knowing how long the build is expected to
take?** That "expected duration" number is the comparison baseline (the **null hypothesis**), not
something fancy — a build predicted to take 20 minutes is worth deferring for carbon reasons regardless
of what caused it; the question is whether SE signals add anything *on top* of that. It's evaluated by
replaying real historical CI data (**TravisTorrent** — 3,881,992 job rows → 925,897 builds → 922,624
after the quality funnel) against real UK grid carbon-intensity data, in a simulator — plus a small live
demo (API + GitHub Action + dashboard) at the end.

This is explicitly a **value-of-information study, not a new scheduling algorithm**. The project's own
rules say a finding of "no, SE info doesn't help beyond duration" is a completely valid, publishable
result — arguably the more useful one for practitioners, because it tells them not to bother building
something complicated.

---

## 2. The one big pivot so far: DL-012 (2026-08-09)

Early on the project was framed differently — *"Risk-Aware Carbon Scheduling"* — where the contribution
was a build-failure prediction model used to decide scheduling risk. On 2026-08-09 the author redirected
it to the current framing. The failure-prediction model didn't get thrown away — it survives as **one
candidate signal** being tested, not the whole point anymore. This is logged as **DL-012**, with a
follow-up correction **DL-013** that fixed a subtle flaw in how the carbon-savings comparison would have
been judged (see §5 — "why raw carbon numbers won't decide this").

---

## 3. Where we are right now

- **12 of 28 planned tasks done (43% overall).**
- **Phase 0 (setup) — 100% done.**
- **Phase 1 (commit-time evidence) — 100% done. Milestone M1 reached.** This phase produced the
  headline finding (§4).
- **Phase 2 (core + simulator + policy) — 1 of 5 done (20%).**
- **Currently on:** P2-T2 — energy & carbon accounting. **Not started.**
- **Next:** P2-T3 (`decide()`), then P2-T4 (the six-strategy replay simulator), then P2-T5 (compile and
  **freeze** the policy — the gate that opens the test split).
- **After that:** Phase 3 (the one-shot, locked-box test-split evaluation — where the real answer becomes
  final), Phase 4 (live demo prototype), Phase 5 (write the dissertation).

**The big change since the last briefing: the model-level research question has been answered, and the
answer is the null.** See §4.

---

## 4. The journey so far, phase by phase, with real findings

### Phase 0 — Setup (done)
- Built the data pipeline against the **real** CSV (not the published paper's column names, which
  turned out to be wrong/renamed in the actual file — caught early, DL-002).
- Confirmed real dataset scale: **3,881,992 job rows → 925,897 builds**, 25.1% overall failure rate
  (bigger than the docs' rough estimate suggested — DL-009).
- Fixed the analysis grain: model at **build level**, not job level.
- Pulled real UK carbon-intensity data (17,544 hourly readings) and locked the energy-accounting formula,
  with an explicit citation for the power constant and a sensitivity band (DL-007/DL-010).
- Froze the full evaluation protocol **before** any modelling began.

### The pivot (DL-012, DL-013)
- Redefined the project as described in §2.
- **DL-013 fix:** the original plan would have compared strategies by "raw carbon saved," but because
  carbon cost is *directly proportional to build duration* in the energy model, a duration-only strategy
  is *guaranteed* to win on raw carbon almost by definition. Fixed by comparing strategies as **trade-off
  curves** (carbon saved vs. how fast failing builds get their feedback). This matters a lot for reading
  Phase 3 later: **the carbon channel can't detect SE value at all — the whole question rests on the
  feedback-speed channel.**

### Phase 1 — Building & testing the evidence (COMPLETE)
- **P1-T1 — Duration-control design.** Designed `d̂`, the "expected build duration" baseline. Pinned two
  candidate forms: a trained regressor (④a) and a simple per-project historical average (④b) (DL-014).
- **P1-T2 — Feature extraction (28 commit-time features, 6 families).** **Adverse finding:** the dataset's
  "test churn" column is **completely empty for every build** in this release. Two of the 28 features are
  dead, and one family loses half its members (DL-016). Two textbook SE predictors (change entropy,
  commit-message fix-keywords) can't be built from this dataset at all (DL-015). **Net effect: the SE side
  goes in weaker than a textbook study would — a "lower bound," not a best-case test.**
- **P1-T3 — Splits.** 948 projects → train (628) / calibration (150) / test (170), time-ordered,
  project-disjoint. **Finding:** calibration ended up with a higher failure rate (28.5% vs ~24–25%) and
  longer builds — flagged for reading calibration numbers (DL-017).
- **P1-T4 — Duration estimator.** The simple per-project historical average (④b) beat the trained
  regressor (④a) on calibration (error 0.601 vs 1.178). The simpler approach won.
- **P1-T5 — Train & calibrate 6 models.** {duration-only control, full SE set} × {XGBoost, logistic
  regression, random forest}. **Adding all 28 SE features did not beat the duration-only control on any
  metric, for any algorithm.** XGBoost ROC-AUC *fell* from 0.651 to 0.540.
- **P1-T6 — Family ablation + SHAP.** The obvious hope was that one or two specific families carry signal
  that gets diluted when all 28 features are dumped in together. **They don't.** Every one of the six
  families made things *worse* than duration alone, and every confidence interval excluded zero on the
  negative side:

  | family | what's in it | ΔPR-AUC vs duration-only |
  | :-- | :-- | --: |
  | F1 | change size (churn, files, commits) | −0.003678 |
  | F2 | change composition (src/doc/other, docs-only, description) | −0.005526 |
  | F3 | test activity/density | −0.023333 |
  | F4 | project maturity (SLOC, repo age, language) | −0.064694 |
  | F5 | team/developer (team size, core member) | −0.066323 |
  | F6 | context (is_pr, hour, day) | −0.002920 |

  SHAP on the full model: **`d̂` itself is the strongest and only clearly-useful signal**, and the two
  dead test-churn features have SHAP values of exactly 0 — confirming DL-016 mechanically. A curious
  secondary result: *every* single-family model beat the all-28 model, so the families actively
  **interfere** when combined rather than each being independently harmful.
- **P1-T7 — The formal verdict.** Applied the admission rule that was written down before any results
  existed. **All six families rejected; the admitted set is empty**, and stays empty at ×0.5, ×1 and ×2 of
  the materiality floor (the protocol treats that stability as the *stronger* finding). `admission.json`
  records `policy_path: duration_only_fallback`.

  → **This is the model-level answer to the central research question, and it is "no."** Stronger than
  "no evidence of benefit": on calibration the SE families are *significantly worse* than duration alone.

### Phase 2 — Core, simulator, policy (in progress)
- **P2-T1 — Stage-1 eligibility gate + independent validator (done 2026-09-17).** This is the
  deterministic rule that decides whether a build is *allowed* to be deferred at all, before any ML gets
  involved. The important part isn't the code, it's **DL-020**, which states plainly what the gate is and
  is not:
  - The frozen spec defines eligibility by **build trigger type**. TravisTorrent records no trigger type.
    It records "is this a PR?" and a free-text branch name, and nothing else about urgency.
  - So the gate is an **approximation**: deferrable ⟺ not a PR **and** the branch name matches none of a
    frozen list of protected/release patterns. Anything it can't interpret **fails closed** (runs now).
  - **Two of the six specified trigger classes — manually-triggered and scheduled/nightly builds — have
    no marker in this dataset at all and are not approximated.** The single most obviously-deferrable
    category (nightly builds) is therefore *absent from the evidence base*; every carbon number in this
    study is computed over the harder, more marginal part of the population.
  - **The approximation's error rate is unmeasurable here** — there is no ground-truth "was this build
    actually safe to delay?" label in TravisTorrent to score it against.
  - Measured result: **24.40% of builds are deferrable by rule** (191,245 of 783,931 train+calibration
    builds). Under the contested "is `develop` a protected branch?" reading it drops to 16.85% — that
    reading is registered as a named variant for the Phase 3 sensitivity sweep rather than silently
    decided.
  - The independent validator (a deliberately separate implementation that doesn't import the gate)
    **agreed on all 55,228 distinct input combinations, zero disagreements**, and found zero violations.
  - One real bug was caught by a test during implementation: an early pattern let `stable-2.0` branches
    (608 builds) through as deferrable. Fixed.

---

## 5. Where this is heading — honest read

**The model-level question is settled and the answer is the null.** SE characteristics, as operationalised
here, carry no admissible incremental value beyond a commit-time duration estimate. The remaining open
question is the **decision-level** one: when you actually run the scheduler, does an SE-informed policy
beat a duration-only policy on the carbon-vs-feedback-speed trade-off curve? That is P3-T3, and it has
not happened.

**Why the null is a good outcome, not a failure:**

1. **The project designed for either answer.** The admission rule was fixed in DL-012, before any data was
   touched: if no family clears the bar, "the policy collapses to the duration-only baseline, and that
   negative result is the principal finding." Not a fallback invented after seeing bad numbers.
2. **The result is useful.** Telling practitioners "don't build an SE-feature ML model for this — just use
   expected build duration" saves them a feature store, a training loop, a calibration process, an
   explanation interface, and an extra failure mode in a CI-critical path.
3. **The baseline is strong, not a straw man.** The duration control is a causal per-project history
   estimate that was itself leakage-tested — it's a demanding null, which is what makes rejecting the
   treatment meaningful.

**What honestly bounds the claim:**
- The SE feature set is a known **weakened lower bound** (DL-015/DL-016). "No" on *this* data isn't "no"
  in general.
- Everything so far is **calibration-split**. Phase 3 confirms it on the untouched test split.
- The comparison has a **built-in asymmetry**: the duration control gets rich within-project history,
  while the SE models are trained on *other* projects. That's one plausible deployment regime, logged in
  DL-014, and it must not be described as a neutral head-to-head.
- The study's independent variable — deferability — **is not observed**. It's approximated (DL-020). This
  is the deepest limitation in the whole project, and it now has a written home.

**Still open, flagged for the author:** the duration estimator's declared trailing-50-builds sensitivity
variant beat the predeclared primary form on calibration (0.289 vs 0.601). Changing the primary would need
a decision-log entry argued from principle, *before* Phase 3 opens the test split.

---

## 6. The independent review (2026-09-13)

An outside model was asked to audit the repository as a critical examiner. The report is at
`INDEPENDENT_REVIEW_REPORT.md` in the outer folder. Triaged on 2026-09-17:

- **Its factual claims about the evidence check out.** Build counts, split sizes, the duration-control
  numbers, the family deltas — all match the results files.
- **Its main methodological criticisms were already logged** before the review: the carbon channel being
  structurally closed (DL-013), the control asymmetry (DL-014), the split heterogeneity (DL-017), the
  degraded feature set (DL-015/DL-016).
- **Its strongest point was live and is now addressed:** the construct-validity gap — *the target isn't
  deferability*. That became **DL-020** at P2-T1.
- **One claim was false.** It reported a broken virtualenv, missing `xgboost`, and "21 failures and 32
  errors." Re-ran here: the locked environment works (Python 3.11.1, xgboost 3.2.0, scikit-learn 1.9.0)
  and the suite is green — **382 tests passing**. The reviewer ran a different interpreter. Worth
  correcting, because "not reproducible" is the kind of claim an examiner repeats.
- **Its artifact redesign proposals are deferred by decision**, not overlooked. It argued the Phase 4
  prototype should drop the 28-feature API schema and the SHAP dashboard on the null path. Reasonable —
  but adopting it now would mean pre-committing to the null before the test split is opened, which is the
  mirror image of changing criteria after the fact. **Revisit at P3-T5.**

---

## 7. What's left

| Phase | What it does | Status |
| :-- | :-- | :-- |
| P1 | Commit-time evidence | ✅ 7/7 — model-level RQ2 answered (null) |
| P2 (current) | Energy/carbon accounting, `decide()`, the six-strategy replay simulator, and **freeze** an evidence-derived policy from train+calibration only | 1/5 done |
| P3 | Open the test split **exactly once** — confirmatory model evaluation, full 6-strategy replay, the decisive SE-vs-duration frontier comparison, sensitivity sweeps, results synthesis | not started |
| P4 | Live demo: REST API + GitHub Action + dashboard, running the same decision logic as the simulation | not started |
| P5 | Write the dissertation chapters | not started |

Note that **P2-T5 is a significant gate**: approving the frozen policy is what opens the test split, and
the test split is touched once.

---

## 8. If you only remember four things

1. The question is "does commit-level SE info help beyond a duration estimate?" — not "can we predict CI
   failures" (that was the old framing, DL-012).
2. **The model-level answer is in, and it's the null.** All six SE feature families were rejected against
   a strong duration baseline, and they were significantly *worse*, not merely no better. The project
   predeclared this as a valid outcome.
3. **It isn't final yet.** The decision-level test (does the policy actually schedule better?) and the
   confirmation on the untouched test split are both Phase 3. Don't write "RQ2 is answered" anywhere yet.
4. **The deepest limitation is now written down (DL-020):** deferability is never observed in this
   dataset — it's approximated from two proxy columns, and two of the six specified build-trigger classes
   can't be approximated at all. No result here says which builds are genuinely safe to delay.

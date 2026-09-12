# Status Briefing — plain-language catch-up

> **Not a governance file.** This is a human-readable summary for the author to re-orient quickly.
> It is not authoritative — if it ever disagrees with `planning/PROGRESS.md` or
> `governance/03_DECISION_LOG.md`, those win. Written 2026-09-10.

---

## 1. What this research actually is (one paragraph)

A BSc thesis asking: when a Git commit triggers a CI build, is it worth trying to shift that build to a
greener time window (carbon-aware scheduling)? Specifically — **does knowing things about the commit
itself** (how big the diff is, how many tests it touches, who wrote it, etc. — "SE characteristics")
**help decide which builds to defer, over and above just knowing how long the build is expected to
take?** That "expected duration" number is the comparison baseline (the **null hypothesis**), not
something fancy — a build predicted to take 20 minutes is worth deferring for carbon reasons regardless
of what caused it; the question is whether SE signals add anything *on top* of that. It's evaluated by
replaying real historical CI data (**TravisTorrent**, ~2.6M-row public dataset of Travis CI builds)
against real UK grid carbon-intensity data, in a simulator — plus a small live demo (API + GitHub Action
+ dashboard) at the end.

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
been judged (see §5 below — "why raw carbon numbers won't decide this").

---

## 3. Where we are right now

- **9 of 28 planned tasks done (~32% overall).**
- **Phase 0 (setup) — 100% done.** Environment, data pipeline, carbon-intensity data, frozen evaluation
  protocol.
- **Phase 1 (commit-time evidence) — 5 of 7 tasks done (71%).** This phase builds and tests the actual
  models. It's the phase we're in, and it's the one producing the interesting findings.
- **Currently on:** P1-T6 (family ablation + SHAP — breaking down *which* groups of SE features, if any,
  contribute). **Not started yet.**
- **Next:** P1-T7 — turn P1-T6's evidence into the actual model-level answer to "does SE info help?"
  (RQ2), by a rule that was written down *before* any results were seen (so it can't be gamed after the
  fact).
- **After that:** Phase 2 (build the scheduler + simulator + freeze a policy), Phase 3 (the one-shot,
  locked-box test-set evaluation — this is where the real answer becomes final), Phase 4 (live demo
  prototype), Phase 5 (write the dissertation).

---

## 4. The journey so far, phase by phase, with real findings

### Phase 0 — Setup (done)
- Built the data pipeline against the **real** CSV (not the published paper's column names, which
  turned out to be wrong/renamed in the actual file — caught early, DL-002).
- Confirmed real dataset scale: **3,881,992 job rows → 925,897 builds**, 25.1% overall failure rate
  (bigger than the docs' rough estimate suggested — DL-009).
- Fixed the analysis grain: model at **build level**, not job level (a build can have many CI jobs;
  modelling per-job would have leaked information across the eventual train/test split).
- Pulled real UK carbon-intensity data (17,544 hourly readings) and locked down the energy-accounting
  formula, with an explicit citation for the power constant and a sensitivity band (DL-007/DL-010).
- Froze the full evaluation protocol (metrics, split method, how "success" will be judged) **before**
  any modelling began.

### The pivot (DL-012, DL-013) — reframing to the current research question
- Redefined the project as described in §2.
- **DL-013 fix:** the original plan would have compared strategies by "raw carbon saved," but because
  carbon cost is *directly proportional to build duration* in the energy model, a duration-only strategy
  is *guaranteed* to win on raw carbon almost by definition — that comparison can't actually test whether
  SE info helps. Fixed by instead comparing strategies as **trade-off curves** (carbon saved vs. how
  fast failing builds get their feedback), which is the honest way to detect a real SE effect. This
  matters a lot for interpreting whatever comes out of Phase 3 later.

### Phase 1 — Building & testing the evidence (in progress)
- **P1-T1 — Duration-control design.** Designed `d̂`, the "expected build duration" baseline the whole
  study is measured against. Pinned two candidate forms: a trained regressor (④a) and a simple
  per-project historical average (④b). Surfaced and resolved a subtle rule about what information the
  duration estimate is allowed to use without cheating (DL-014).
- **P1-T2 — Feature extraction (28 commit-time features across 6 families).** Built the feature
  pipeline. **Adverse finding:** the dataset's "test churn" column (how much test code changed) is
  **completely empty for every single build** in this release — not just sparse, actually zero
  information. Two of the 28 features are dead because of it, and the "change purpose/composition"
  feature family loses half its members (DL-016). Also, two textbook SE predictors (change entropy,
  commit-message fix-keywords) simply can't be built from this dataset at all (DL-015). **Net effect:
  the SE side of the comparison is going in weaker than a textbook study would be — a "lower bound," not
  a best-case test.**
- **P1-T3 — Train/calibration/test split.** Split 948 projects into train (628) / calibration (150) /
  test (170) projects, time-ordered, no project appearing in more than one split (to prevent leakage).
  **Finding:** the calibration slice randomly ended up with a notably higher failure rate (28.5% vs
  ~24–25% elsewhere) and longer builds — expected given how skewed failure rates are project-to-project,
  but flagged as something to keep in mind when reading calibration-based numbers (DL-017).
- **P1-T4 — Duration estimator.** Fit the actual `d̂` baseline. The simple per-project historical
  average (④b) beat the trained regressor (④a) on the calibration set (error 0.60 vs 1.18) — the simpler
  approach won.
- **P1-T5 — Train & calibrate the real models.** Trained 6 models: {duration-only control, full SE
  feature set} × {XGBoost, logistic regression, random forest}. **This is the headline finding so far:**
  **on the calibration data, adding all 28 SE features did not beat the duration-only control on any
  metric, for any of the three algorithms.** E.g. for XGBoost, discrimination (ROC-AUC) actually *fell*
  from 0.65 (duration-only) to 0.54 (full feature set) — same story for logistic regression, and a
  smaller drop for random forest.
  - **Important caveat, explicitly flagged in the project's own notes:** this is *not yet* an official
    answer to the research question. It's one training run, on the calibration split, before the
    per-family breakdown (P1-T6) or the formal admission-rule verdict (P1-T7), and long before the
    locked test-split confirmation in Phase 3. But it's a real, currently-standing signal, and it points
    toward "no" on the central question.

---

## 5. Where this looks like it's heading — honest read

**Short version: the evidence so far leans toward a null result on the main hypothesis — SE
characteristics are not (yet) beating a simple duration-based baseline.** That is *not* a failure of the
project. Two things make that an acceptable, even good, outcome:

1. **The project explicitly designed for either answer to be valid.** The predeclared admission rule
   (fixed back in DL-012, before any data was touched) says: if no SE feature family clears a preset bar
   of improvement, "the policy collapses to the duration-only baseline, and that negative result is the
   principal finding." That's not a fallback excuse invented after seeing bad numbers — it was written
   down as the intended, respectable outcome from the start.
2. **The result would still be useful.** Telling CI/carbon-scheduling practitioners "don't bother
   building an SE-feature ML model, just use expected build duration" is a legitimate, actionable
   finding.

**Things that make the current signal less than fully conclusive (reasons for real optimism it could
still shift):**
- The SE feature set going in is a known **weakened lower bound** — two strong predictors (test churn,
  change entropy) are simply unavailable in this dataset, and two more are only crudely proxied
  (DL-015/DL-016). A "no" on this data isn't necessarily a "no" in general — it may just mean *this*
  2017 TravisTorrent release can't fully test the hypothesis.
- P1-T5's numbers are from **one calibration-split run**, without per-family decomposition. It's
  possible one or two specific families (rather than "all 28 at once") carry real signal that gets
  diluted/overfit when dumped in together — that's exactly what **P1-T6 (family ablation + SHAP)**,
  the very next task, is designed to check.
- The real, binding test doesn't happen until **Phase 3**, on the untouched **test split** — everything
  before that is by design exploratory/calibration evidence, not the confirmatory result.

**Bottom line:** the project is executing cleanly, on schedule, with unusually rigorous discipline
(every decision logged, every number sourced to a real run, splits frozen before results were seen). The
substantive story emerging so far trends toward "duration alone is hard to beat" rather than "SE features
clearly help" — which would be a fine, honest, defensible thesis result either way, but the next two
tasks (P1-T6 family ablation, P1-T7 formal verdict) are what will actually settle the *model-level*
question, and Phase 3 is what settles it for good.

---

## 6. What's left

| Phase | What it does | Status |
| :-- | :-- | :-- |
| P1 (current) | Finish the commit-time evidence: per-family ablation + SHAP, then the formal model-level RQ2 verdict | 5/7 done |
| P2 | Build the actual scheduler core, replay simulator, and **freeze** an evidence-derived policy (using only train+calibration data) | not started |
| P3 | Open the test split **exactly once** — final confirmatory model evaluation, full 6-strategy replay, the decisive SE-vs-duration comparison, sensitivity checks, results synthesis | not started |
| P4 | Build the live demo: REST API + GitHub Action + monitoring dashboard, running the same decision logic as the simulation | not started |
| P5 | Write the dissertation chapters | not started |

---

## 7. If you only remember three things
1. The question is "does commit-level SE info help beyond a duration estimate?" — not "can we predict
   CI failures" (that was the old framing, DL-012).
2. So far (calibration-split evidence, not yet final): **adding SE features hasn't beaten the
   duration-only baseline** — a plausible null result, which the project treats as a valid outcome, not
   a failure.
3. The real verdict is still two tasks away (P1-T6, P1-T7) for the model-level question, and a full
   phase away (P3, test split) for the final, confirmatory answer.

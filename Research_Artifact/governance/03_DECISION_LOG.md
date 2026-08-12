# 03 — Decision Log (append-only)

Every deviation from `01_SOURCE_OF_TRUTH.md`, and every significant implementation choice not already
fixed by the spec, is recorded here **before** it is acted on. Append new entries at the bottom; never
edit or delete past entries (supersede them with a new entry instead).

**Entry template:**

```
### DL-NNN — <short title>
- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded by DL-MMM
- **Spec section affected:** §x.y (or "none — implementation detail")
- **Context:** what situation forced the decision
- **Decision:** what we will do
- **Rationale:** why this over the alternatives
- **Consequences:** what this changes downstream (other tasks, threats to validity)
```

---

### DL-001 — Adopt the session-OS framework as the project's working method
- **Date:** 2026-06-12
- **Status:** Accepted
- **Spec section affected:** none — process/governance, not research design
- **Context:** The project needed a repeatable way for Claude sessions to execute the spec
  incrementally without drift or hallucination, with visible progress and per-task confirmation gates.
- **Decision:** Establish `Research_Artifact/` as the working root with governance/planning/context
  documents; gate at per-major-task granularity; plan-then-do autonomy; progress bars at every gate.
- **Rationale:** Keeps a single source of truth, makes progress auditable, and bounds the blast radius
  of any single session to one task.
- **Consequences:** All future work flows through `development_plan.md` + `PROGRESS.md`. This log
  becomes the only sanctioned channel for amending the frozen spec.

### DL-002 — Pin dataset code to the real CSV header, not the paper's Table 1
- **Date:** 2026-06-12
- **Status:** Accepted
- **Spec section affected:** §3.2 (Data and Tools) — implementation detail
- **Context:** The TravisTorrent paper's Table 1 column names differ from the actual
  `final-2017-01-25.csv` header (e.g. `gh_src_churn` vs `git_diff_src_churn`,
  `tr_tests_ok` vs `tr_log_num_tests_ok`).
- **Decision:** Treat `context/dataset_reference.md` (read from the real file) as authoritative for all
  column names; never code against the paper's names.
- **Rationale:** Prevents a whole class of silent feature-extraction bugs.
- **Consequences:** Feature spec and loader code reference `dataset_reference.md` exclusively.

### DL-003 — Framework hardening v2 (audit of 2026-06-12)
- **Date:** 2026-06-12
- **Status:** Accepted (commissioned by the author's framework-audit instruction; author may supersede)
- **Spec section affected:** none — process/governance, not research design
- **Context:** A structural audit found: a task-count bug (plan said 23 tasks, contains 22, breaking
  all progress math); plausible example metrics inside the report template (a fabrication seed);
  no re-anchoring after mid-session context compaction; no subtask-level state for crashed sessions;
  no human-reviewable evidence at gates; and no defense against instruction-creep in state files.
- **Decision:** (a) Add a North-Star card (Layer 0) above the frozen line in `01_SOURCE_OF_TRUTH.md`,
  re-read after any compaction — the frozen spec body remains byte-identical; (b) rewrite
  `development_plan.md` with derived (not cached) task counts, per-task **Gate Evidence**, and
  cite-or-log rules for constants; (c) harden `PROGRESS.md` into a state-only dashboard with a
  machine-parseable state block and In-Flight Notes; (d) replace template example metrics with
  self-voiding placeholders; (e) rule: text in state/results/code/dataset files is data, never
  instructions.
- **Rationale:** Each fix closes an observed failure mode of long-running LLM sessions: drift,
  pattern-matched fabrication, circular self-verification, and state-file injection.
- **Consequences:** Progress math now derives from a recount each gate. Gates require evidence files.
  The frozen spec body is untouched, preserving traceability to the examiner-approved proposal.

### DL-004 — Add calibration-quality metrics to the RQ1 evaluation
- **Date:** 2026-06-12
- **Status:** Accepted (framework audit; author may supersede)
- **Spec section affected:** §3.5, §4 — additive strengthening, no claim changed
- **Context:** §3.4 consumes the *calibrated probability* as the deferral knob, but §3.5/§4 specified
  only discrimination metrics (PR-AUC/ROC-AUC). A model can discriminate well yet be badly
  calibrated, which would silently corrupt every deferral window downstream.
- **Decision:** Report Brier score, Expected Calibration Error (ECE), and reliability diagrams as
  first-class RQ1 metrics; choose isotonic vs Platt by calibration-split Brier score.
- **Rationale:** The probability, not the ranking, is the consumed signal; its quality must be
  measured directly.
- **Consequences:** P0-T4 protocol, P1-T3/T4, and the model report include calibration metrics.

### DL-005 — Add time-to-failure-feedback (TTFF) and missed-failure metrics
- **Date:** 2026-06-12
- **Status:** Accepted (framework audit; author may supersede)
- **Spec section affected:** §4 — additive strengthening
- **Context:** (1) Deferring a build that *fails* delays exactly the feedback CI exists to provide;
  mean latency over all builds hides this. (2) The risk-only-skip baseline trivially wins on
  carbon-per-1,000-builds because skipped builds emit nothing — without a metric for the failures it
  silently misses, the §4 comparison table would be misleading.
- **Decision:** Report (a) TTFF mean/p95 for failed builds per strategy, and (b) missed-failure count
  + failure recall for any skip-style strategy. Latency is additionally reported over deferred builds
  only, alongside the all-builds figures §4 already requires.
- **Rationale:** TTFF is the precise cost the ML layer claims to manage vs the carbon-only baseline
  (RQ3/RQ4 hinge on it); missed failures are the hidden cost of skipping.
- **Consequences:** Protocol (P0-T4), simulator records (P2-T4), and all P3 analyses carry the new
  metrics.

### DL-006 — Three-way project-disjoint, time-ordered split (train / calibration / test)
- **Date:** 2026-06-12
- **Status:** Accepted (framework audit; author may supersede)
- **Spec section affected:** §3.5 — clarification (the spec says "calibrate on a held-out fold"
  without defining it)
- **Context:** Under a project-held-out design, an undefined "held-out fold" risks calibrating on
  test projects — leakage that would invalidate RQ1.
- **Decision:** Split projects (seeded, recorded) into train ≈ 70% / calibration ≈ 15% / test ≈ 15%,
  disjoint by `gh_project_name`, time-ordered within splits. Hyperparameters tuned inside train only;
  calibration fitted on the calibration projects; test touched exactly once (P1-T4).
- **Rationale:** Preserves both the project-held-out and time-ordered guarantees end-to-end.
- **Consequences:** `splits.py` implements this; split manifests saved to `results/p1/splits.json`;
  P3 replay runs on test projects only.

### DL-007 — Explicit, cited energy model with sensitivity band
- **Date:** 2026-06-12
- **Status:** Accepted (framework audit; author may supersede)
- **Spec section affected:** §3.2 — clarification ("CodeCarbon/EcoCI software models" left the power
  constant undefined)
- **Context:** "Estimate energy from runtime" without a pinned power figure invites an invented
  wattage (R1 violation) and unreproducible results.
- **Decision:** `E_kWh = (P_avg_W / 1000) × (duration_s / 3600)` at build grain (summed job
  durations). `P_avg_W` must be **cited** from CodeCarbon/EcoCI documentation or an equivalent
  published source at implementation time (recorded in config + a follow-up DL entry with the
  citation); all carbon results re-run at P_avg × {0.5, 1.0, 1.5} as a sensitivity band.
- **Rationale:** Relative strategy comparisons are robust to P_avg (it scales all strategies equally);
  absolute gCO₂e claims are not — the band makes that transparent.
- **Consequences:** P2-T3 implements it; P3-T3 sweeps it; threats chapter reports it.

### DL-008 — Pin the deferral-window mapping (the Stage-2 knob)
- **Date:** 2026-06-12
- **Status:** Accepted (framework audit; author may supersede)
- **Spec section affected:** §3.4 — clarification ("higher likelihood → shorter deferral" had no
  functional form, no maximum window)
- **Context:** The core mechanism of the thesis was qualitatively specified only; any session
  implementing it would have to invent constants.
- **Decision:** Default mapping `w(p̂) = W_max × (1 − p̂)` hours (continuous, monotone), W_max = 24,
  clipped to [0, W_max]; configuration lives in one versioned config file. Sensitivity: W_max ∈
  {6, 12, 24} and a banded (step-function) variant, evaluated in P3-T3.
- **Rationale:** Simple, monotone, explainable ("p̂ = 0.2 ⇒ may wait up to 19.2 h"), and the sweep
  shows results are not an artifact of one arbitrary mapping.
- **Consequences:** P2-T2 implements exactly this; P3-T3 sweeps it; the dissertation reports the
  mapping as a design parameter, not a tuned-on-test choice.

### DL-009 — Model at build grain; the build-level aggregation rule
- **Date:** 2026-06-18
- **Status:** Accepted
- **Spec section affected:** §3.2/§3.5 — implementation detail (the spec/`dataset_reference.md` left job-vs-build grain as a "recommended: build grain" choice to be confirmed empirically)
- **Context:** Rows are Travis build *jobs*; we must fix the modelling grain before any
  feature/label/simulation code. Measured on the **real** file (commands
  `python scripts/investigate_grain.py`, `python scripts/check_durations.py`;
  evidence `results/p0/grain_investigation.json`, `results/p0/duration_check.json`):
  - **3,881,992 job rows → 925,897 builds** (the docs' "~2.6M rows" estimate is wrong for this 2017 release; the real count governs — R1).
  - `tr_status` is **constant within a build in 100%** of builds (0 varying) → usable as the build label.
  - `tr_duration` is **constant within a build in 99.96%** (340 builds vary) → it is a build-level
    wall-clock value repeated on every job row, **not** a per-job figure.
  - `tr_jobs` is a **list of job IDs** (e.g. `[3161,3163,…]`), not a count → jobs-per-build is the
    observed job-row count (mean 4.19, median 2, max 690).
- **Decision:** Model at **build grain — one row per `tr_build_id`**. Aggregation rule:
  - **label** ← `tr_status` (the single constant value per build); failure = {failed, errored},
    pass = {passed}, `canceled` excluded (DL precedent: dataset_reference §Label).
  - **commit-time feature columns** ← `first` (they are build-level, identical across the build's job rows).
  - **`tr_duration`** ← `max` over the build's rows (handles the 0.037% inconsistent builds deterministically);
    this is the build wall-clock used for **feedback latency** and (per DL-010) the **energy** duration.
  - **`n_jobs`** ← count of job rows for the build.
- **Rationale:** The label and features are build-level by construction; modelling per job would
  duplicate identical feature vectors and leak build identity across the split. Empirically verified, not assumed.
- **Consequences:** `scheduler_core/data.py` provides build-level aggregation; the P0-T2 funnel and
  `data_profile.*` are reported at build grain; P1 features/splits and P2/P3 simulation all key on `tr_build_id`.

### DL-010 — Energy-model duration source = `tr_duration` (refines DL-007)
- **Date:** 2026-06-18
- **Status:** Accepted (refines DL-007; DL-007's formula and ±50% P_avg band stand)
- **Spec section affected:** §3.2 — refines DL-007's "energy uses the build-level summed job duration" clause
- **Context:** DL-007 specified `E_kWh = (P_avg_W/1000) × (duration_s/3600)` with `duration_s` as the
  **summed job duration**. Measured on the real file (`python scripts/check_durations.py`,
  `results/p0/duration_check.json`): the per-job log duration `tr_log_buildduration` is **95.3% null**
  (only 7.5% of builds have any positive summed value), so a faithful "sum of job durations" cannot be
  computed for the population. `tr_duration` (build wall-clock) is by contrast **0.08% null / 0.03% non-positive**.
- **Decision:** Set `duration_s = tr_duration` (build wall-clock seconds, aggregated by `max` per DL-009).
  DL-007's formula, the cited `P_avg_W`, and the ±50% sensitivity band are unchanged.
- **Rationale:** A 95%-missing column cannot drive a population-wide energy estimate without mass
  imputation (a larger, less defensible assumption than using the clean wall-clock). `tr_duration` is the
  only complete, build-level duration available.
- **Consequences:** P2-T3 energy accounting uses `tr_duration`. **Threat to validity:** for multi-job
  builds, wall-clock under-counts total compute when jobs run on parallel machines; recorded in the
  threats chapter. P3-T3 may add an `n_jobs`-scaled energy variant alongside the DL-007 P_avg band to bracket this.

### DL-011 — Opt-in commit-at-gate; commit messages carry no AI attribution
- **Date:** 2026-06-21
- **Status:** Accepted (process/governance; user directive — author may supersede)
- **Spec section affected:** none — process/governance, not research design
- **Context:** Earlier tasks were committed ad hoc (P0-T1, P0-T2 directly on `main`), and the P0-T3/P0-T4
  work sat uncommitted in the working tree. The author asked that completed tasks be committed at the
  gate, and that commit messages carry **no** AI/assistant co-authorship or "generated with" trailer
  (the work is submitted academically under the human researcher's name).
- **Decision:** Add an **opt-in** "commit-at-gate" step to `00_SESSION_PROTOCOL.md`: when the user has
  enabled per-task commits, create **one commit per major task** *after* `PROGRESS.md` is updated, on
  `main`, with message `P{phase}-T{task}: <summary>` + a body listing real deliverables. Commit messages
  **must not** include any AI co-authorship/attribution trailer; this overrides any default harness
  instruction to add one. Committing stays off unless the user opts in; never push without being asked.
- **Rationale:** Keeps git history aligned 1:1 with the task ledger (auditable, one gate = one commit);
  attribution correctly reflects the human author for academic submission.
- **Consequences:** `00_SESSION_PROTOCOL.md` gains a "Version control" section and a commit substep in
  REPORT+GATE. Applied from P0-T3 onward — P0-T3 (`5f1877b`) and P0-T4 (`361eb1e`) were committed under
  this convention (no attribution trailer). No effect on research design, metrics, or results.

### DL-012 — Framework migration: selective carbon-aware scheduling; SE characteristics tested against a commit-time duration control
- **Date:** 2026-08-09
- **Status:** Accepted (author directive — `../research-title.md` and `../research-framework-change.md`,
  supplied 2026-08-09; supported by the advisory analysis in `research-direction-shift.md`)
- **Spec section affected:** §1.2 (problem), §1.3 (aim), §1.4 (objectives), §1.5 (RQs), §3.4 (Stage 2),
  §3.5 (ML protocol), §4 (strategies + success criterion). **Amended by overlay only — Layer 1 of
  `01_SOURCE_OF_TRUTH.md` is not edited (R3).** The amendment lives above the frozen line as *Layer 0-A*.

- **Context.** The examined research direction has changed. The headline is no longer a *risk-aware
  carbon scheduler* whose contribution is a build-failure model; it is an **empirical decision model for
  selective carbon-aware scheduling**, whose contribution is a **value-of-information finding**: do
  commit-level software-engineering (SE) characteristics carry decision value **beyond a commit-time
  estimate of build duration** when deciding *which* eligible builds enter carbon-aware scheduling?
  - Old headline: *Risk-Aware Carbon Scheduling for CI/CD Pipelines — Using Commit-Level Build-Failure
    Prediction to Parameterise Automated Carbon-Aware Build Deferral.*
  - New headline: *An Empirical Decision Model for Selective Carbon-Aware Scheduling in CI/CD Pipelines
    Using Commit-Level Software Engineering Characteristics.*
  - Taken literally, "beyond build duration" hides a leakage trap: `tr_duration` /
    `tr_log_buildduration` are **outcomes of the build being scheduled** and are already on the
    `context/feature_spec.md` leakage blocklist. A decision made at commit time cannot consult them.

- **Decision.**
  1. **Active framing.** The active aim, objectives and RQs are those in *Layer 0-A* of
     `01_SOURCE_OF_TRUTH.md` (RQ1 which SE characteristics inform selection; RQ2 incremental value beyond
     a commit-time duration control; RQ3 evidence-derived policy; RQ4 replay comparison). Frozen §1.5
     RQ1–RQ4 remain verbatim as historical/supporting; Layer 0-A carries the mapping between them.
  2. **Duration is a commit-time control, never an input.** "Beyond expected build duration" means a
     **commit-time duration estimate** — a project/language historical prior or a regressor — fitted
     **only** on training-split projects and, within a project, only on builds strictly **earlier** than
     the build being scored. The current build's actual `tr_duration` may reach **only** the simulator
     (energy, latency, TTFF accounting) and the duration estimator's **historical training labels**.
     It may never reach `decide()`. An **oracle-duration** variant using the actual value is permitted
     **only** as a clearly-labelled retrospective sensitivity bound, unrealizable in deployment.
  3. **New baselines.** Two controls join the strategy set: **duration-control-only** scheduling
     (Stage 1 + the commit-time duration estimate, no SE families) and a **per-project prior** control,
     so a positive SE result cannot be project identity in disguise. Strategy list becomes ①–⑥ with ⑥
     (risk-only skip, frozen §4) retained as a **secondary** comparison.
  4. **Stage 2 is reframed, not deleted.** Stage 1 (deterministic eligibility) is unchanged
     (invariant 1). Stage 2 becomes an **evidence-derived selective policy** loaded from a versioned
     `policy_spec.yaml`, with a **duration-only fallback path**. The calibrated failure-likelihood model
     survives as **one candidate SE-informed signal**, no longer the whole contribution. DL-008's
     mapping `w(p̂) = W_max·(1−p̂)` is **retained as the default/fallback form**, not the only form.
  5. **Admission is evidence-gated, and the rule is predeclared here (design parameter, not a result).**
     An SE feature family enters the policy only if **both** hold on held-out data:
     - **Model level:** ΔPR-AUC over the duration-control baseline has a 95% paired-bootstrap CI
       excluding 0 **and** a point estimate ≥ **0.01** absolute PR-AUC;
     - **Decision level:** the paired carbon difference vs duration-control-only is ≥ **1% relative**
       carbon reduction with a 95% CI excluding 0, at **no worse** TTFF p95 for failed builds
       (its CI must not exclude "no worse").
     Both floors are **swept at ×0.5 and ×2** as a declared sensitivity. The rule is frozen **before**
     the final test-split results are inspected. **If no family passes, the policy collapses to the
     duration-only baseline and that negative result is the principal finding.**
  6. **Policy fitting uses the calibration split, never test.** `scripts/fit_policy.py` derives
     `policy_spec.yaml` from P1 evidence (ablation, SHAP, calibration, project-variance) **plus** a
     replay sweep on **calibration** projects. This extends DL-006's use-discipline: calibration
     projects now serve calibrator fitting, threshold selection **and** policy fitting. **Test projects
     are still touched exactly once** (P3-T1), against a frozen `policy_spec`.
  7. **Effect sizes lead.** At N ≈ 9.2×10⁵ builds, significance is nearly free. Every comparison reports
     the effect size and 95% CI first; a CI excluding 0 is reported as significant but **not** as
     material unless it clears the §5 floor.
  8. **Phase 0 is retained, not repeated.** P0-T1..T4 outputs (`results/p0/env.txt`,
     `data_profile.*`, `carbon_*`, `eval_protocol.md`, `scheduler_core/{data,carbon}.py`) are confirmed
     valid under the new framing and carried forward unchanged. The grain (DL-009) and energy-duration
     (DL-010) decisions stand. `eval_protocol.md`'s frozen body is preserved; the new definitions are an
     appended, versioned **Amendment A1**.
  9. **Affected files** (all edited under this entry): `01_SOURCE_OF_TRUTH.md` (Layer 0/0-A only),
     `results/p0/eval_protocol.md` (Amendment A1 appended), `context/feature_spec.md` (duration
     three-way separation + feature families), `planning/development_plan.md` (rewritten; task total
     22 → **27**), `planning/PROGRESS.md` (recounted state), `CLAUDE.md` (inner + outer), `README.md`,
     `code/README.md`, `code/pyproject.toml` (description string).

- **Rationale.** The reframe is a change of *emphasis plus one control variable plus statistical tests*,
  not a rebuild: it preserves the single backbone dataset, the project-held-out time-ordered splits, the
  deterministic eligibility gate, the shared `decide()` core, the replay simulator and the paired
  bootstrap. Recasting duration as a commit-time control simultaneously (a) removes the leakage trap in
  the literal phrasing, (b) demotes duration prediction to supporting work, and (c) turns the study into
  a textbook incremental-value design that is publishable either way. Freezing the admission rule before
  results removes the incentive to rediscover a positive finding.

- **Consequences.**
  - Phase 1 grows from 4 to 7 tasks (duration-control design, feature-family audit, splits, estimator
    implementation, model training incl. controls, test evaluation, incremental-value ablation).
    Phase 2 grows to 5 (policy derivation added). Phase 5 grows to 4 (literature verification added).
  - The simulator must record, per build: decision reason, **policy path taken**, estimated duration,
    observed duration (accounting only), delay, carbon, and outcome.
  - `context/feature_spec.md` must state three disjoint roles for duration; the leakage blocklist is
    **strengthened**, not relaxed.
  - New threats to validity: duration-estimator error propagates into the control (the control is a
    *predicted* quantity, so RQ2 is "beyond *predictable* duration"); cold-start projects fall back to a
    coarser prior; the admission floors are judgement calls (mitigated by the ×0.5/×2 sweep).
  - Inherited draft material (`../final paper.md`) is **not** citable as-is: every citation and numeric
    claim carried into the dissertation must be verified against its original source (new task P5-T1).
  - Supersedes nothing. DL-001..DL-011 all stand; DL-006 and DL-008 are *extended* by items 6 and 4.

- **Correction (appended 2026-08-09, non-substantive — original text above left unedited, R4
  append-only).** Item 9 and the first Consequence bullet state the task total as **27** and imply
  Phase 3 stays at 4 tasks. The plan as actually written splits Phase 3 into **5** tasks (test-split
  model evaluation · full replay · frontier comparison · sensitivity · synthesis), so the correct
  derived total is **28**: P0:4 · P1:7 · P2:5 · P3:5 · P4:3 · P5:4. `development_plan.md` and
  `PROGRESS.md` both carry 28; the recount governs (00_SESSION_PROTOCOL "counts are derived, not
  cached"). No research-design change — a stale arithmetic figure in this entry only.

### DL-013 — The decision-level test compares trade-off **frontiers**, not single points (corrects DL-012 §5)
- **Date:** 2026-08-09
- **Status:** Accepted (corrects a defect in DL-012 §5 / `eval_protocol.md` §A1.5, §A1.7, found before any
  code was written under them; DL-012 otherwise stands unchanged)
- **Spec section affected:** `results/p0/eval_protocol.md` §A1.5 and §A1.7 (both introduced by DL-012);
  `planning/development_plan.md` P2-T4, P3-T3.

- **Context — the defect.** DL-012 §5 set the decision-level admission rule as *"⑤ must achieve ≥ 1%
  relative carbon reduction versus ④, at no worse TTFF p95."* That rule is close to **unsatisfiable by
  construction**, for a reason that is structural rather than empirical:
  - The energy model is `E = P_avg · duration` (DL-007/DL-010), so the carbon saved by deferring a build
    is **directly proportional to its duration**. "Which builds are worth deferring *for carbon*" is
    therefore very nearly a pure duration question **by definition of the accounting model**, not by
    empirical finding.
  - Strategy ⑤ consumes an SE signal whose effect is to **shorten** windows for builds it judges risky.
    Relative to ④ over the same eligible set, ⑤ therefore defers **less** and will score **worse** on
    raw carbon almost regardless of how good the SE signal is.
  - Consequently the DL-012 §5 decision-level rule would force a **null verdict for a structural
    reason**, masking whatever real signal exists. A null obtained this way is not evidence of absence;
    it is an artefact of comparing two strategies at unmatched operating points.
  - The value SE characteristics *can* add is on a second axis duration cannot reach: **failure-feedback
    safety**. Duration says nothing about whether a build will fail, and deferring a failing build
    delays precisely the feedback CI exists to provide (DL-005 rationale).

- **Decision.**
  1. **Each strategy exposes one aggressiveness parameter and is swept**, tracing a **curve** in the
     (carbon saved, TTFF p95) plane rather than producing a single point. For ④ the parameter is
     `d_threshold` (and `W_max`); for ⑤ it is the fitted policy scale. Sweep grids are fixed in
     `policy_spec.yaml` and recorded, not chosen after seeing results.
  2. **The decision-level comparison is dominance between curves**, evaluated at **matched operating
     points**: at matched carbon saved, is ⑤'s TTFF p95 lower? — and symmetrically, at matched TTFF
     p95, is ⑤'s carbon saved higher? Paired-bootstrap CIs are computed **at the matched points**, on
     the identical trace.
  3. **Revised materiality floors** (design parameters, as before — not results):
     - **≥ 5% relative reduction in TTFF p95 at matched carbon saved**, CI excluding 0; **or**
     - **≥ 1% relative increase in carbon saved at matched TTFF p95**, CI excluding 0;
     - dominance must hold at **≥ 3 matched operating points** spanning the swept range, not at one
       cherry-picked point;
     - both floors keep the DL-012 **×0.5 / ×2 sweep**.
  4. **Scalar effect size:** the **area between the two frontiers** over the overlapping carbon range,
     reported with a paired-bootstrap CI, so the finding has one headline magnitude and not only a
     dominance verdict.
  5. **Raw single-point carbon comparison is still reported** — as descriptive context, explicitly
     annotated that ④ is *expected* to lead on it by construction, so no reader mistakes it for a
     finding about SE characteristics.
  6. The **model-level** half of the rule (ΔPR-AUC ≥ 0.01 with CI excluding 0) is **unchanged**.

- **Rationale.** Comparing two schedulers at unmatched aggressiveness measures how hard each was
  configured to push, not which uses information better. Frontier dominance is the standard way to
  compare policies that trade one cost against another, and it is the only framing under which RQ2 can
  return a *positive* answer if a positive answer is warranted. Fixing this **before** any policy code
  exists means no result was seen first — the rule is still genuinely predeclared.

- **Consequences.**
  - `eval_protocol.md` §A1.5/§A1.7 revised under this entry (the A1 amendment is versioned to **A1.1**;
    the original A1 text is superseded in place with this DL named inline — the frozen §§1–12 body
    remains untouched).
  - **P2-T4:** the simulator must accept a strategy-aggressiveness parameter and run a sweep, not a
    single setting. **P2-T5:** `fit_policy.py` records the sweep grid in `policy_spec.yaml`.
    **P3-T3:** produces frontier curves, matched-point comparisons, and the area-between-curves statistic.
  - **Threat to validity (new, must appear in the write-up):** because carbon saving is proportional to
    duration *by the accounting model*, this study cannot detect SE value through the carbon channel at
    all. Its power to answer RQ2 rests on the failure-feedback channel. That limitation is a property of
    the energy model, and is stated as such rather than presented as an empirical result.
  - **Expectation setting (not a result, R1):** under this design the anticipated shape of the finding is
    "④ leads on raw carbon by construction; the live question is TTFF at matched carbon." No magnitude is
    claimed until P3-T3 runs.

<!-- Append DL-014, DL-015, … below as the project progresses. -->

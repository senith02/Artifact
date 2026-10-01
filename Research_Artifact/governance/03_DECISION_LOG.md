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

### DL-014 — What A1.1's information rule binds: fitted parameters vs. causal within-project state
- **Date:** 2026-08-12
- **Status:** **Accepted / Resolved — author confirmation recorded 2026-08-17**, *with one modification:
  the conservative-direction claim in §Rationale bullet 2 is **struck** (see §Resolution at the end of
  this entry, which governs). The two-mechanism reading itself is accepted as written.*
  *(Originally: Proposed — awaiting author confirmation at the P1-T1 gate.)*
  `context/duration_control_spec.md` is written against this reading and names this entry inline wherever
  it relies on it.
- **Spec section affected:** `results/p0/eval_protocol.md` §A1.1 (information-availability clause) —
  interpretation, not amendment. Downstream: §A1.6 (④b), §A1.9 (project-identity control),
  `planning/development_plan.md` P1-T1/P1-T4.

- **Context — an internal tension found by the P1-T1 clause-by-clause cross-check (plan S4).**
  A1.1's hard rule reads: *"`d̂(b)` … may depend only on (a) the commit-time features of `b`, and
  (b) builds in **train-split projects** with `gh_build_started_at < t_b`. For a build in its own
  project's history, only strictly-earlier builds of that project may contribute. Nothing from the
  calibration or test projects, and nothing at or after `t_b`, may enter the fit."*
  Read as one undifferentiated rule, it is **self-contradictory in application** and makes two other
  A1 clauses unsatisfiable:
  1. Sentence 2 explicitly contemplates a build's **own project history** contributing, while sentence 3
     forbids calibration/test projects from entering *the fit*. Both can only be true if "the fit" and
     "the project's own earlier builds" are different mechanisms.
  2. Under the strict reading, ④b — the **per-project prior** — has no project history to read for any
     calibration or test project, so it degenerates to the language prior. §2's use-discipline puts the
     P3 replay on **test projects only**, so ④b would be a two-level language prior throughout the
     evaluation. That defeats its declared purpose: §A1.9 makes ④b **mandatory** precisely because
     per-project failure rates span ~two orders of magnitude and an apparent SE effect could be project
     identity in disguise. A language prior over 2 languages cannot control for project identity.
  3. Conversely, clause (b) taken literally per scored build would require the **fitted** control (the
     ④a regressor, and the language/global priors) to be re-estimated at every distinct `t_b` against a
     receding cut-off. With project-disjoint splits whose time ranges overlap end-to-end, no single
     global cut-off leaves a usable training set.

- **Decision.** A1.1's rule is read as binding **two different mechanisms differently**. Both readings
  below are strictly *decision-time causal*; neither lets the scored build's own outcome, or anything
  about its future, reach `d̂`.
  1. **Fitted parameters** — the ④a regressor's weights and hyperparameters, and the **language** and
     **global** fallback priors — are estimated from **train-split projects only**, over the whole
     train period, **without** a per-scored-build temporal cut-off. Justification: the splits are
     project-disjoint (§2), so no train build carries information about the scored build, its project,
     or its outcome; what a train build can leak is only generic "how long do builds of this kind take".
  2. **Within-project state** — ④b's rolling prior, and any per-project history statistic — is
     **strictly causal and is permitted for calibration and test projects**: it may read only builds of
     that same project with `gh_build_started_at < t_b`, and it is *online state*, not a fitted
     parameter. This is information a deployed scheduler genuinely holds at commit time (the repository's
     own build history to date), which is the standard A1.1 is trying to enforce.
  3. **The A1.1(ii) temporal leakage test attaches to mechanism 2**, where a cut-off can actually bind:
     injecting later builds of the *same project* into the history must change `d̂`. For mechanism 1 the
     binding test is the split test — injecting a calibration/test project into the fit must be rejected.
  4. **The residual is declared, not hidden.** Under mechanism 1 a train build that is *later in
     wall-clock* than a scored calibration/test build can inform the fitted control. This is recorded as
     a threat to validity in `duration_control_spec.md` §8 and must appear in the threats chapter.

- **Rationale.**
  - It is the only reading under which A1.1, A1.6 and A1.9 are simultaneously satisfiable, and it is the
    reading sentence 2 of A1.1 already implies.
  - ~~**The deviation's direction is conservative for the study's own hypothesis.** Every allowance here
    makes the **null** (strategy ④, the duration control) *stronger*, never the treatment (⑤). A stronger
    null makes RQ2 **harder** to answer positively, so this reading cannot manufacture a positive SE
    finding — it can only suppress one. That is the correct direction for a deviation to lean in a
    value-of-information study.~~
    **STRUCK by the author at the 2026-08-17 resolution.** No directional-bias claim is made or relied
    upon. The bias direction of this reading is **not established**, and nothing in the study may assert
    that it "strengthens the null" or "guarantees a conservative bias". See §Resolution, which governs.
  - The alternative — refitting per timestamp — is not merely expensive; with overlapping split time
    ranges it has no admissible training set, so it is not an option that was traded away for cost.

- **Consequences.**
  - `context/duration_control_spec.md` (P1-T1) defines `d̂` in two mechanisms accordingly, and P1-T4
    implements a **split test** (mechanism 1) and a **temporal test** (mechanism 2) rather than one
    combined test. A1.1's three required leakage tests are all still implemented; this entry only
    determines *which mechanism each one binds*.
  - ④b becomes a genuine per-project control on test projects, as §A1.9 requires; ④a remains fitted on
    train only and is therefore the weaker-adapting of the two forms on held-out projects — an expected
    asymmetry, not a defect, and the reason A1.1 requires **both** forms be reported.
  - **If the author rejects this reading:** ④b must be redefined (the honest options are (a) drop it and
    lose the §A1.9 project-identity control, or (b) re-derive the splits so that each project's early
    history sits in train and its later builds in test — which breaks §2's project-disjointness,
    invariant 4, and needs its own DL entry). Either is a larger change than this one; that asymmetry is
    itself part of the argument for the reading above.
  - No numbers are produced or implied by this entry (R1). Nothing is refitted; no P0 output changes.

- **Resolution — author decision, 2026-08-17 (this subsection governs).** The two-mechanism reading is
  **accepted** and DL-014 moves to Resolved. The author's decision, as given:
  1. **Fitted parameters** — the ④a XGBoost/Ridge regressor (weights *and* hyperparameters), the
     **language** prior and the **global** prior — are fitted from **TRAIN-split projects only**.
  2. **④b** may use **strictly causal history from the scored project's own earlier builds**, and this is
     permitted **including for calibration and test projects**.
  3. The admissible history window is **only** `gh_build_started_at < t_b`. The current build, any future
     build, and any **timestamp-tied** build (`gh_build_started_at == t_b`) are **forbidden**.
  4. **Framing.** This is to be described as the **intended deployment information regime** — the
     information a deployed scheduler genuinely holds at commit time, namely its own repository's build
     history to date. It is **not** to be described as training on test projects, and it is not a
     concession or a relaxation: no parameter is estimated from any held-out project.
  5. **No directional-bias claim.** It must **not** be asserted anywhere — decision log, specs, results,
     or dissertation — that this reading automatically strengthens the null or guarantees a conservative
     bias. §Rationale bullet 2 is struck accordingly. The **residual asymmetry of §4 remains a declared
     threat of undetermined direction**: under mechanism 1 a train build later in wall-clock than a scored
     held-out build can inform the fitted control, and the effect of that on RQ2 is **not measured and not
     assumed**. It is reported as an open threat in `duration_control_spec.md` §8 and the threats chapter.
  6. The "if the author rejects this reading" branch in §Consequences is now **moot** and retained only as
     history.
- **Consequence of the resolution.** `context/duration_control_spec.md` is updated in the same action to
  (a) drop its "depends on a proposed DL entry" warning, and (b) remove the two conservative-direction
  claims it inherited from the struck rationale (§3.1 final bullet, §8 threat 2). No other clause of the
  spec changes: §2 I1–I3, §3.1/§3.2, §4, §5, §6 and the T1–T5 test contract were already written against
  exactly the accepted reading. P1-T4 proceeds. Still no numbers (R1).

### DL-015 — Feature-construction decisions: the `num_commits` source, four unbuildable §3.5 features, the missing-value policy, and a strengthened blocklist
- **Date:** 2026-08-15
- **Status:** Accepted (implementation-level; the **28-feature contract is unchanged**)
- **Spec section affected:** §3.5 feature list as operationalised by `context/feature_spec.md`
  (§Feature table #13, §"Spec features that need a derivation or proxy", §Leakage blocklist).
  Required by `development_plan.md` P1-T2 S1: *"any feature that cannot be built faithfully gets a DL
  entry (proxy or drop) before the matrix is finalised."*

- **Context.** P1-T2 implements `scheduler_core/features.py` against the real header. Four kinds of gap
  surfaced between what §3.5 describes and what the 2017 TravisTorrent release actually contains. None
  changes *which* 28 features exist — the contract and the six-family partition (A1.3) are untouched —
  but each is a construction choice that must be visible rather than buried in code.

- **Decision 1 — `num_commits` (#13) is `git_num_all_built_commits`.**
  `feature_spec.md` #13 offers `gh_num_commits_in_push` *or* `git_num_all_built_commits` and says
  "pick one, document". The choice is **forced, not preferred**: `gh_num_commits_in_push` is
  **100% null** in this release (`results/p0/data_profile.md` §Notable findings), while
  `git_num_all_built_commits` is **0% null**. The feature therefore counts *commits built*, not
  *commits pushed*; for a push build these coincide, and for a PR build the built set is the more
  decision-relevant quantity anyway. Recorded in `FEATURE_SOURCES` and asserted by a test that every
  declared source exists in the pinned header.

- **Decision 2 — four §3.5 features cannot be built from this dataset.** Each is **dropped or proxied
  by features already inside the 28**; none is invented, and no new feature is added.
  | §3.5 feature | Verdict | Why, and what stands in |
  | :-- | :-- | :-- |
  | **Change entropy** | **Dropped** | Entropy needs the **per-file** churn distribution. The release carries only aggregates (`git_diff_src_churn`, `git_diff_test_churn`) and per-*category* file counts — never a per-file breakdown, so no distribution exists to take entropy over. `feature_spec.md`'s fallback ("approximate via `files_total` spread") is already covered by #3–#6 and the file-type mix #9–#11, which stay in F1/F2. No entropy-named feature is emitted. |
  | **Fix-keyword flag** | **Dropped** | Needs commit **messages**; TravisTorrent has none (only commit SHAs). Joining an external message source is out of scope (spec §1.6). |
  | **Developer total / recent experience** | **Proxied** | No per-author commit-count column. Stands in: `by_core_member` (#20) + `team_size` (#19) in F5, plus `commits_on_files_touched` (#14) in F4. This is a **team/tenure** proxy, not an individual-experience measure. |
  | **Subsystems / directories touched** | **Proxied** | No directory-path column. Stands in: `files_total` (#6) and the file-type mix `src_files`/`doc_files`/`other_files` (#9–#11). This captures *breadth of change* but not *architectural* spread. |
  - **Threat to validity (must appear in the threats chapter).** Two well-attested JIT-defect predictors
    (change entropy, fix-keyword) are **absent from the treatment**, and developer experience enters only
    as a coarse team-level proxy. The SE arm is therefore a **lower bound** on what commit-level
    characteristics could contribute. The direction is conservative for RQ2: a null result may reflect a
    weakened treatment rather than an absence of signal, and must be reported with that caveat. It cannot
    manufacture a *positive* finding.

- **Decision 3 — missing-value policy: impute only where the spec defines the meaning of missing.**
  - `description_complexity` (#23) → **0 when absent**, exactly as `feature_spec.md` #23 states, because
    the field exists only for PRs (79.2% null, `data_profile.md`) and "no PR description" is genuinely
    zero description, not an unknown.
  - **Every other feature keeps `NaN`.** Unparseable cells coerce to `NaN`, never silently to 0 (R1);
    `is_docs_only` (#12) is `NaN` when either input is missing rather than defaulting to "not docs-only".
  - Any *model-side* imputation is a **P1-T5 modelling choice** made inside the fitted pipeline (so it is
    fitted on train only and cannot leak across splits), not a property of the matrix. The matrix reports
    missingness; it does not conceal it.

- **Decision 4 — the leakage blocklist is strengthened, never relaxed.** `features.py` blocks
  everything `feature_spec.md` §Leakage blocklist names, **plus** the remaining post-run log fields
  (`tr_log_lan`, `tr_log_setup_time`, `tr_log_analyzer`, `tr_log_frameworks`) **plus** a `tr_log_*`
  **prefix rule** so a post-run column that nobody enumerated is blocked by default rather than by
  vigilance. Enforcement is two-sided: every feature's *declared sources* are checked, and the produced
  matrix's *columns* are checked. `tr_duration` is additionally excluded from the read path — it is not
  in `READ_COLUMNS`, so it cannot travel with the features even by accident (§A1.2 role 1 keeps it in
  the simulator's accounting path only).

- **Rationale.** Each decision is forced by a measured property of the real file (R1/R2), and every one
  of them either leaves the treatment unchanged or **weakens** it. Nothing here strengthens the SE arm
  relative to the duration control, so none of it can bias RQ2 toward a positive answer.

- **Correction (appended 2026-08-15, author-directed; original text above left unedited, R4
  append-only).** The Rationale's closing sentence — that none of these decisions "can bias RQ2 toward a
  positive answer" — is **too strong as a blanket claim**, and is withdrawn as stated. It holds for the
  two **drops** (change entropy, fix-keyword): removing a predictor can only weaken the SE arm. It does
  **not** follow automatically for the two **proxies**, because a proxy is not merely a weaker version of
  the thing it replaces — it can carry different information:
  - The developer-experience proxy leans on `commits_on_files_touched` (#14), which sits in **F4, the
    project-identity–adjacent family** (feature_spec §Families). If F4 gains, part of that gain may be
    project identity rather than developer experience — an **inflation** risk on that family, not a
    suppression, and precisely the confound §A1.9's per-project control (④b) exists to expose.
  - The subsystems/directories proxy (`files_total`, file-type mix) sits in F1/F2 and measures breadth of
    change rather than architectural spread; whether it under- or over-states the intended construct is
    not established here.
  The correct statement is therefore the **specific** one, retained per-item for later evaluation rather
  than collapsed into a single direction: *entropy and fix-keyword are absent, so the SE arm is a lower
  bound on those constructs; the two proxies measure something adjacent to, not merely weaker than, the
  §3.5 constructs, and F4's proxy carries a project-identity confound that P1-T6's variance decomposition
  and strategy ④b must be read against.* No measured value, feature, or family assignment changes; this
  corrects an over-general claim in the reasoning only. The same over-generalisation appears in
  **DL-016**'s Rationale ("every one of these gaps can only *suppress* an SE finding") — there it is
  accurate as written, because DL-016 concerns **empty and near-empty columns**, which genuinely can only
  remove signal; it is not extended to DL-015's proxies.

- **Consequences.**
  - `code/scheduler_core/features.py` + `code/tests/test_features.py` implement and assert all four.
  - `results/p1/feature_audit.md` reports the resulting null/zero rates per feature so the proxies'
    coverage is inspectable.
  - The threats chapter (P5-T4) must carry Decision 2's lower-bound caveat.
  - **No change to** the 28-feature contract, the A1.3 family partition, the RQs, or any P0 output.

### DL-016 — `git_diff_test_churn` is entirely zero in this release: two contracted features are constant, and F1/F2/F3 are weakened
- **Date:** 2026-08-15
- **Status:** Accepted (measured finding + handling decision; the **28-feature contract and the A1.3
  family partition are unchanged**)
- **Spec section affected:** none normatively — `context/feature_spec.md` #2/#28 and
  `results/p0/eval_protocol.md` §A1.3 keep their definitions. This entry records a **property of the
  data** and how the study reports it.

- **Context — measured, twice, independently (R1).** Building the real matrix in P1-T2 showed feature
  **#2 `test_churn`** with min = max = 0 over all 922,624 analytic builds. Because a bug in the
  extractor would look identical, the source column was re-counted straight off the CSV with the stdlib
  reader (no pandas, no NA coercion), over all **3,881,992 job rows**:
  | Column | Distinct values | Zero share (job rows) |
  | :-- | --: | --: |
  | `git_diff_test_churn` | **1** (`'0'`) | **100%** |
  | `git_diff_src_churn` | 505 | 94.69% |
  | `gh_diff_src_files` | 72 | 94.67% |
  | `gh_diff_tests_added` | 99 | 99.15% |
  | `gh_diff_other_files` | 706 | 8.6% (modal value is `1`) |
  `git_diff_test_churn` is therefore **not sparse — it is empty**: the 2017 release records no test
  churn at all. `git_diff_src_churn` and `gh_diff_src_files` are populated for only ~5% of builds, and
  the file-type classifier assigns almost everything to `gh_diff_other_files` (so "src vs other" is
  largely uninformative here too).

- **Consequences for the feature set (measured, not assumed).**
  - **#2 `test_churn` is constant zero** → zero variance → it cannot change any model's prediction.
  - **#28 `test_density_ratio` is constant zero** by construction: it is
    `test_churn / (src_churn + 1)` and the numerator is identically 0. Two contracted features are dead.
  - **#10 `doc_files` (99.97% zero) and #12 `is_docs_only` (99.98% zero)** are *near*-constant: alive in
    principle, but they separate ~0.03% of builds.
  - Family impact, as measured by `degeneracy_report()` over the analytic set — "effective" = members
    that are neither constant nor near-constant:
    | Family | Members | constant | near-constant | sparse | **Effective** |
    | :-- | --: | --: | --: | --: | --: |
    | F1 change size & diffusion | 7 | 1 | 0 | 2 | **6** |
    | F2 change purpose & composition | 6 | 1 | 2 | 1 | **3** |
    | F3 test activity & maturity | 5 | 0 | 1 | 1 | **4** |
    | F4 project history & maturity | 5 | 0 | 0 | 0 | **5** |
    | F5 developer & team | 2 | 0 | 0 | 0 | **2** |
    | F6 temporal & trigger context | 3 | 0 | 0 | 0 | **3** |
    **F2 is the worst hit — half its members are dead or near-dead.** F3 keeps 4 of 5, but
    `tests_added` is near-constant (99.2% zero) and `tests_deleted` sparse (96.1% zero), so its
    surviving strength sits in the three per-KLOC test-maturity ratios rather than in test *activity*.

- **Decision 1 — keep all 28; do not drop the dead features.** A zero-variance column cannot influence
  a linear, tree, or boosted model, so retaining it costs nothing statistically, while dropping it would
  change the frozen 28-feature contract and the A1.3 family sizes (7+6+5+5+2+3) that P1-T6's ablation and
  P2-T5's admission rule are defined over. The cheaper, more auditable action is to **report** the
  degeneracy, not to renegotiate the contract. If a later task needs constant columns removed for a
  numerical reason (e.g. a solver that rejects zero-variance inputs), that removal happens **inside the
  fitted pipeline** and is noted there — it does not alter the contract.
- **Decision 2 — degeneracy is emitted as data, not prose.** `features.degeneracy_report()` classifies
  every feature as `constant` / `near-constant` / `sparse` / `ok`; `results/p1/feature_audit.md` leads
  with it and gives the per-family effective-member count, and `feature_summary.json` carries the same
  table. The thresholds (modal share ≥ 99%, zeros ≥ 90%) are **reporting-only** — they classify what the
  audit prints and set no model, metric, or policy quantity, so they are not eval_protocol values and
  need no predeclaration.
- **Decision 3 — this binds the interpretation of the RQ1/RQ2 results.** Wherever an F1/F2/F3 arm shows
  little or no incremental value, the write-up must state that the family was **evaluated with dead or
  near-dead members** and that the dataset — not the hypothesis — is the reason. "Test-related change
  characteristics do not help" is **not** a supportable reading of an F3 null on this release; the
  supportable reading is "this release does not record test churn, so the claim could not be tested."

- **Rationale.** The finding is adverse to the study's own treatment arm, and surfacing it now — before
  any model is fitted (P1-T5) or any ablation is run (P1-T6) — is what stops it from being rationalised
  later as a result. It also compounds DL-015: the SE arm was already a lower bound because change
  entropy and the fix-keyword flag are unbuildable; it is now a **materially weaker** lower bound.
  Direction of bias is unchanged and conservative — every one of these gaps can only *suppress* an SE
  finding, never manufacture one, so a positive RQ1/RQ2 result remains trustworthy while a null result
  carries a large, explicit caveat.

- **Consequences.**
  - `features.degeneracy_report()` + a test asserting a constant column is classified `constant`.
  - `results/p1/feature_audit.md` §"⚠ Degenerate features" and `feature_summary.json.degeneracy`.
  - **P1-T6** must report per-family effective member counts beside every ablation result.
  - **P5-T3/P5-T4** must carry Decision 3 in both the results discussion and the threats chapter.
  - No change to the RQs, the family partition, the eval protocol, or any P0 output.

### DL-017 — The frozen split is heterogeneous by construction: base rate and duration differ across splits
- **Date:** 2026-08-15
- **Status:** Accepted (measured finding recorded at the P1-T3 gate; **no protocol deviation** —
  `eval_protocol.md` §2 is followed exactly, and the split is **not** adjusted in response)
- **Spec section affected:** none normatively. Binds the *interpretation* of §5 (calibration metrics),
  `context/duration_control_spec.md` §5 (primary-form selection), and P1-T4/P1-T5/P3-T1.

- **Context — measured by `python scripts/make_splits.py` (R1), manifest `results/p1/splits.json`.**
  The frozen split covers **922,624 analytic builds across 948 projects**, assigned
  train 628 / calibration 150 / test 170 projects (69.94% / 15.03% / 15.03% of builds — within
  0.06 pp of the §2 targets). Structurally it is exactly what §2 asks for. Distributionally it is not
  uniform, and could not be:
  | Split | Projects | Builds | Failure rate | Duration p95 (s) | Duration mean (s) |
  | :-- | --: | --: | --: | --: | --: |
  | train | 628 | 645,244 | 24.354% | 5,725 | 1,442.77 |
  | calibration | 150 | 138,687 | **28.549%** | **11,638** | **2,558.04** |
  | test | 170 | 138,693 | 25.036% | 5,643 | 1,848.01 |

- **Finding 1 — failure-rate heterogeneity (4.20 pp spread).** The calibration split's base rate
  (28.55%) exceeds both train (24.35%) and test (25.04%). Because §5 fits the probability calibrator and
  selects the operating threshold **on calibration**, both are tuned at a prevalence the test population
  does not share. Calibrated probabilities transfer across a base-rate shift only under assumptions that
  do not hold automatically.
- **Finding 2 — duration heterogeneity.** Calibration carries a markedly heavier duration tail
  (p95 = 11,638s versus ~5,700s for train and test; mean 2,558s versus 1,443s / 1,848s).
  `duration_control_spec.md` §5 selects the **primary `d̂` form** by calibration-split log1p MAE — i.e.
  the control's form is chosen on a duration distribution unrepresentative of the test set. *(These are
  descriptive statistics only — §A1.2 role 1, accounting; no value here reaches `decide()`.)*
- **Finding 3 — the three splits' time ranges overlap end-to-end** (all span 2011-04 → 2016-08). This is
  by design: the split is project-disjoint, **not** time-disjoint (§2, invariant 4).

- **Decision.** **Record; do not re-split.** Specifically:
  1. **The split is not adjusted, reseeded, or rebalanced.** Searching seeds for a distribution-matched
     split would optimise the split against properties of the data (base rate, duration) that later
     results depend on — a silent researcher degree of freedom, and the exact thing §2's fixed
     seed-and-greedy rule exists to prevent. The split stays frozen at digest
     `3d9a7947017c89e1eedc4da655719911b4a312926a865ce277550827c5935cde`.
  2. **P1-T5 must report calibration metrics against Finding 1** — Brier/ECE on test are read knowing the
     calibrator was fitted at a higher base rate; the prevalence shift is stated beside them.
  3. **P1-T4 must report Finding 2 beside the chosen primary `d̂` form**, since the selection criterion
     is evaluated on the unrepresentative split. This does **not** change the selection rule, which was
     pinned in P1-T1 before any data was seen.
  4. **Finding 3 is recorded as a measurement only.** It is the empirical condition DL-014 reasons
     about, and DL-014 remains **Proposed/unresolved** by author direction — nothing here resolves,
     reinterprets, or implements it.

- **Rationale.** Project-disjoint splitting and distribution matching are in direct tension: per-project
  failure rates span roughly two orders of magnitude (`results/p0/data_profile.md` top-20 table: 1.33%
  for `ros/rosdistro` to 98.9% for `apache/sling`), so any project-disjoint split of 948 projects is
  heterogeneous. §2 chose project-disjointness because leakage is the graver threat; the price is this
  heterogeneity, and the honest handling is to declare it before the models are fitted rather than to
  discover it when a metric disappoints.
- **Consequences.** `results/p1/splits_summary.md` §"Methodological threats"; P1-T4 §Finding 2,
  P1-T5 §Finding 1; threats chapter (P5-T4). No change to §2, the split, the seed, the feature contract,
  or any earlier decision.

### DL-018 — P1-T5 training configuration: search spaces, imbalance handling, budget, and the two arms
- **Date:** 2026-08-17
- **Status:** Accepted (implementation-level; **written before any model was fitted**, per R4)
- **Spec section affected:** `results/p0/eval_protocol.md` §3 (tuning), §4 (models compared),
  §5 (calibrator choice), §A1.3 (arm structure). **No clause is amended.** §3 explicitly *delegates*
  this: *"The concrete grid/seeded random search and its ranges are recorded in the … training config
  and run log."* This entry is that record, made in advance so it cannot be tuned to a result.

- **Context.** P1-T5 must train three algorithms (§4: XGBoost primary, Logistic Regression and Random
  Forest baselines) across two arms (§A1.3: `{d̂}` control and `{d̂ + all 28}` full). §3 pins the
  *procedure* (train-only tuning, temporally-latest 20% internal-validation fold, PR-AUC selection) and
  the XGBoost parameter **names**, but not the ranges, not the search budget, and nothing at all for the
  two baselines. Those must be fixed before fitting or they become post-hoc choices.

- **Decision.**
  1. **Arms.** `control = {d̂}` and `full = {d̂ + all 28 features}`, `d̂` being the **frozen** P1-T4
     control (primary form ④b, fit id `1088d5546f47ff12`). `d̂` is **loaded, never refitted** —
     `models.attach_d_hat` asserts the artifact's fit id against `results/p1/duration_control.json`.
     Refitting it here would silently move the null that RQ2 is measured against.
  2. **Search spaces** (seeded random search, `numpy.random.default_rng(42)`):
     - **XGBoost** — the seven ranges already pinned for the duration control
       (`duration_control_spec.md` §4.2: `n_estimators` 100–800 log-int, `max_depth` 3–10,
       `learning_rate` 0.01–0.30 log, `subsample` 0.6–1.0, `colsample_bytree` 0.6–1.0,
       `min_child_weight` 1–20 log-int, `gamma` 0–5), **plus** `scale_pos_weight` sampled log-uniformly
       over `[0.5r, 2r]` where `r` = train-fold negatives/positives. §3 lists `scale_pos_weight` as part
       of the search, so it is searched rather than fixed. Reusing the §4.2 ranges keeps one pinned
       XGBoost space in the project instead of two that could drift apart.
     - **Logistic Regression** — `C` log-uniform over `1e-4 … 1e2`; **L2** penalty, `solver="lbfgs"`,
       `max_iter=1000`. (L2 is scikit-learn's default and the explicit `penalty=` kwarg is deprecated as
       of 1.8, so the code relies on the default rather than passing it.)
     - **Random Forest** — `n_estimators` 100–300 log-int, `max_depth` 4–16, `min_samples_leaf` 10–200
       log-int, `max_features ∈ {sqrt, log2}`.
  3. **Imbalance handling in all three** (spec §3.5). XGBoost uses `scale_pos_weight` (§3 names it); the
     two scikit-learn baselines use `class_weight="balanced"`, the equivalent reweighting. Without it the
     baselines would be handicapped by a configuration choice rather than by their inductive bias, and
     §4's "so the model comparison is fair" would not hold.
  4. **Preprocessing.** XGBoost consumes the matrix directly (native missing-direction learning). The two
     baselines get `SimpleImputer(strategy="median")` — train medians, fitted **inside** the pipeline and
     persisted with the model — and Logistic Regression additionally gets `StandardScaler`. Neither
     accepts NaN, and the 28-feature contract contains them. This mirrors the Ridge reference already
     pinned in `duration_control_spec.md` §4.2, so the project has one imputation convention, not two.
     `lang` is one-hot encoded from **train-split levels**; an unseen level encodes as all-zeros.
  5. **Budget.** `n_iter = 20` candidates, **identical for every algorithm and every arm**, because §4
     requires the *identical* internal-validation procedure across algorithms — an unequal budget would
     measure the budget rather than the family. Chosen for tractability at 645,244 × ~32 on CPU, from a
     timing probe run on **synthetic noise** (no project data, no result involved).
  6. **The 28-feature contract is unchanged.** No feature is added, dropped, or re-derived here; the only
     new column any model sees is `d̂`, which §A1.3 requires in every arm.

- **Rationale.** Every item above is either delegated by §3, required by §3.5/§4 for the comparison to
  be fair, or forced by a library constraint. Fixing them in advance is what makes the P1-T5 numbers
  interpretable: none of them can be revised after a metric is seen.

- **Declared threats this configuration creates** (all carried into the P1-T5 report and P5-T4):
  1. **The Random Forest space is smaller than XGBoost's** (depth ≤ 16, leaf ≥ 10, ≤ 300 trees), bounded
     purely for compute. RF is therefore **not** given search parity, and any finding that XGBoost beats
     RF must be read with that caveat rather than as a clean family comparison.
  2. **`n_iter = 20` is a small random search** for an 8-dimensional XGBoost space. It is identical
     across arms, so the *arm* comparison (the one RQ2 rests on) is unaffected; the *algorithm*
     comparison is the weaker of the two claims.
  3. **Median imputation for the baselines is itself a modelling choice** that XGBoost does not make, so
     part of any XGBoost-vs-baseline gap may be missing-value handling rather than model family.
- **Consequences.** `scheduler_core/models.py` (spaces as data), `scripts/train_models.py`,
  `results/p1/model_training.md`, `results/p1/calibration/`. P1-T6 reuses this identical machinery for
  the per-family arms, so the ablation inherits the same procedure by construction. No numbers are
  produced or implied by this entry (R1).

### DL-019 — P1-T6 ablation configuration: arms, paired-bootstrap procedure, SHAP method, variance decomposition
- **Date:** 2026-09-12
- **Status:** Accepted (implementation-level; **written before any ablation arm was fitted**, per R4)
- **Spec section affected:** `results/p0/eval_protocol.md` §A1.3 (families/arms), §A1.4 (model-level
  incremental value), §A1.7 (the model-level floor, read here as a data-driven trigger only — not the
  RQ2 verdict), §A1.8 (monotonicity), §A1.9 (variance decomposition), §9 (paired bootstrap conventions).
  **No clause is amended.** Several of these leave the concrete procedure to the implementing task (§9's
  `paired_bootstrap` signature is explicitly a *replay-trace* (build × strategy) function reserved for
  P3; §A1.3–A1.9 name the comparisons and floors but not a build-level bootstrap procedure, a SHAP
  method, or a variance-decomposition formula). This entry fixes all four, in advance, per DL-018's
  precedent.

- **Context.** `development_plan.md` P1-T6 requires: (S1) fit `{d̂}`, `{d̂+Fᵢ}` per family, `{d̂+all}`,
  plus leave-one-family-out arms for any family clearing the model-level floor; (S2) paired ΔPR-AUC/
  ΔROC-AUC/ΔBrier/ΔECE vs `{d̂}` with 95% paired-bootstrap CIs on the **calibration** split; (S3) SHAP
  attributions + a monotonicity check; (S4) a between/within-project variance decomposition per family.
  None of the four has a pinned procedure yet, and P1-T5's own `full`-vs-`control` finding (XGBoost
  ROC-AUC 0.650712→0.539508) makes it likely no family clears the floor — the trigger for leave-one-out
  arms must therefore be decided **before** looking, not after.

- **Decision.**
  1. **Algorithm and arms.** Per §A1.4 ("same algorithm, same tuning procedure, same splits, same
     calibration rule — only the feature set differs"), the ablation runs **the predeclared primary
     algorithm only (XGBoost, §4)** — the two baselines are not re-ablated. The `control` and `full`
     arms are **the frozen P1-T5 XGBoost artifacts, loaded not refitted**
     (`code/artifacts/models/xgboost__control.joblib`, `xgboost__full.joblib`; fit ids asserted against
     `results/p1/model_training.json`), because they were already fit by the identical procedure this
     task must use — refitting them would risk a silent procedural drift between "control" here and
     "control" in the P1-T5 report. Six new arms are fit: `{d̂+F1}` … `{d̂+F6}`, using
     `scheduler_core.models.train_arm`/`calibrate` unchanged (same train/internal-validation fold, same
     `n_iter=20`, same seed 42, same isotonic-vs-Platt calibrator rule) — the feature set is the only
     variable, per §A1.4.
  2. **Leave-one-family-out trigger.** A family is fit as a leave-one-out arm (`{d̂+all−Fᵢ}`) **iff** its
     `{d̂+Fᵢ}` arm's ΔPR-AUC vs `{d̂}` (this task's own bootstrap, step 3) has a point estimate **≥ 0.01**
     absolute **and** a 95% CI excluding 0 — the literal §A1.7 model-level floor. This is **not** the
     RQ2 admission verdict (that is P1-T7's, applying §A1.7 with the ×0.5/×2 sweep, "no discretion, no
     post-hoc adjustment"); it is used here only to decide which extra arms are worth the compute, and
     is reported as exactly that. If no family clears it, zero leave-one-out arms are fit and that is
     recorded as a finding, not a shortfall.
  3. **Paired bootstrap for model-level deltas (build-level, not the §9 replay-trace `paired_bootstrap`).**
     A new function, `scheduler_core/ablation_stats.paired_metric_delta`, resamples the **calibration
     build index** with replacement `B = 1000` times (seeded `numpy.random.default_rng(42)`, per §9's
     conventions); on each resample it recomputes PR-AUC/ROC-AUC/Brier/ECE for the control's and the
     treatment arm's calibrated probabilities **on the same resampled indices** (paired), and the
     treatment-minus-control difference. The reported CI is the 2.5th/97.5th percentile of the resampled
     differences (§9's method exactly); a difference is "significant" when that CI excludes 0. This is a
     distinct function from §10's `paired_bootstrap` (which pairs *strategies* over a replay trace at
     P3) — named differently so the two are never confused, but sharing every numeric convention
     (`B`, seed, CI method) so the project has one bootstrap standard, not two.
  4. **SHAP method.** `shap.TreeExplainer` (pinned `shap==0.51.0`) on the **frozen `full` XGBoost arm's
     base (uncalibrated) model** — SHAP explains the model that produces the score, and calibration is a
     monotone-in-aggregate post-hoc map that does not change per-feature attribution structure — over the
     **calibration-split design matrix** (the split this task is scoped to). Per-family magnitude =
     mean absolute SHAP value summed over the family's member features, per build; direction = mean
     signed SHAP value per feature. `d̂`'s own SHAP column is reported separately (it is the control term,
     not a family member).
  5. **Monotonicity check (§A1.8).** For every feature (including `d̂`), the Spearman rank correlation
     between the feature's raw calibration-split value and its per-build SHAP value, with a 95% CI from
     the same bootstrap machinery (resample calibration builds, `B=1000`, seed 42). A feature is flagged
     **monotone** iff the CI excludes 0 (a stable-signed relationship) — this is a necessary, not
     sufficient, condition for using that score as a simple window knob (§A1.8's default form assumes
     monotonicity); a feature whose CI contains 0, or whose sign flips across the range, is flagged
     **non-monotone** and named as a caveat for any later use as a window knob.
  6. **Variance decomposition (§A1.9).** For each family, a one-way decomposition of its per-build SHAP
     contribution (the same summed quantity as step 4), grouped by `gh_project_name` on the calibration
     split: `between = Σ_g n_g·(mean_g − mean)² `, `within = Σ_g Σ_i∈g (x_i − mean_g)²`, reported as each
     share of `between + within` (the total sum of squares — algebraically the total variance to
     numerical precision, checked as a test). A family whose between-project share dominates (declared
     threshold: **≥ 0.8** of total, chosen before looking, symmetric with A1.7's "no discretion" spirit)
     is flagged as **project-identity-coded** — its apparent signal may be encoding which project a
     build belongs to rather than a within-project SE effect (§A1.9's stated purpose).

- **Rationale.** Every choice reuses a convention already fixed elsewhere in the project (§9's B/seed/CI
  triple, DL-018's training procedure, the frozen P1-T5 control/full artifacts) rather than inventing a
  new one, so the only genuinely new numbers are the two declared thresholds (the 0.01/CI-excludes-0
  leave-one-out trigger, which is §A1.7 verbatim, and the 0.8 project-identity-coded threshold for
  variance decomposition, which has no protocol precedent and is therefore fixed here, in advance,
  rather than chosen after seeing which families are project-coded).

- **Declared threats this configuration creates** (carried into the P1-T6 report and P5-T4):
  1. **The model-level floor check in step 2 is not the RQ2 verdict.** It reuses the same numeric rule
     as §A1.7 but without the ×0.5/×2 sensitivity sweep that P1-T7 requires before any admission is
     final. A family could clear this task's trigger and still fail P1-T7's full rule, or vice versa —
     though the ×2 direction (a *stricter* floor) can only shrink, never grow, the admitted set from what
     this task fits, so no leave-one-out arm P1-T7 needs will be missing.
  2. **SHAP explains the `full` arm's base model, not the per-family arms.** A family's SHAP magnitude
     therefore reflects its contribution *inside the full model* (where other families can absorb or
     mask its signal), while the family's own ΔPR-AUC (step 3) is measured from its **standalone**
     `{d̂+Fᵢ}` arm. The two can disagree — SHAP is a decomposition-inside-`full` diagnostic, not a
     restatement of the incremental-value numbers, and the report must not conflate them.
  3. **The 0.8 project-identity threshold is a declared convention, not a derived statistic**, exactly
     like DL-012 §5's model/decision floors — its arbitrariness is handled the same way, by stating it
     before any number exists and reporting the raw between/within split regardless of which side of 0.8
     it falls on.
  4. **A cross-reference to P1-T5's threat 8.** `eval_protocol.md` §A1.4 states "Where computed: P1-T7,
     on the **test** split, once" — but `development_plan.md` P1-T6/P1-T7 (the post-DL-012, 28-task
     breakdown that governs execution, per `CLAUDE.md`) unambiguously scope **both** tasks to the
     **calibration** split, with P1-T7's DoD requiring the report to assert the test split is *still*
     untouched. This is the same class of stale pre-DL-012 task-numbering artifact P1-T5 already flagged
     (§8 of `model_training.md`) — Phase 1's confirmatory, test-split ablation is `development_plan.md`
     P3-T1 ("confirmatory ablation"), not P1-T7. Recorded here so this ambiguity is not independently
     rediscovered at P1-T7 or P3-T1; `development_plan.md` governs, and the test split stays closed
     through P1-T6.
- **Consequences.** `scheduler_core/ablation_stats.py` (new), `scheduler_core/models.py` (arm set
  extended for family arms — no change to `control`/`full`), `scripts/run_ablation.py`,
  `results/p1/ablation/`, `results/p1/shap/`. P1-T7 consumes `results/p1/ablation/deltas.json` to apply
  the actual §A1.7 rule with its sweep; nothing here pre-empts that verdict.

### DL-020 — The Stage-1 eligibility gate is an experimental approximation of deferability, not a measurement of it
- **Date:** 2026-09-17
- **Status:** Accepted (implementation-level; **written before any line of `eligibility.py` existed**,
  per R4 and `development_plan.md` P2-T1 S1)
- **Spec section affected:** §3.4 (Stage 1's deferrable/non-deferrable classes), §4 (the
  "eligibility-gate safety" metric and the deferrable-fraction sensitivity sweep), §6 (threats).
  **No clause is amended** — §3.4 defines the classes in terms of build *trigger type*, and this entry
  records that TravisTorrent does not carry trigger type, so the classes must be approximated from the
  two columns it does carry. `context/dataset_reference.md` already flags this and routes it here.

- **Context.** §3.4 partitions builds by trigger:
  - *non-deferrable:* (a) pull-request-**blocking** builds, (b) release/tag builds, (c) hotfix-tagged or
    production-branch builds, (d) manually-triggered builds;
  - *deferrable:* (e) scheduled/nightly builds, (f) non-blocking pushes to non-protected branches.

  The backbone dataset records **none of these six trigger types**. It carries `gh_is_pr` (a boolean)
  and `git_branch` (a free-text name), and nothing else bearing on urgency. Measured on the 783,931
  train + calibration builds (`results/p2/branch_profile.md`, run `python scripts/profile_branches.py`,
  2026-09-17): both columns are **100% present** (0 missing), `gh_is_pr` is true for 140,506 builds
  (17.9233%), and `git_branch` takes **54,512 distinct values**, led by `master` (500,226; 63.8100%),
  `develop` (47,232; 6.0250%), `trunk` (18,697; 2.3850%) and `dev` (14,875; 1.8975%). Branch names that
  *look* release-shaped are a small minority: semver-tag-like 28,297 (3.6096%), `release/…` 7,483
  (0.9545%), `…stable` 1,560 (0.1990%), hotfix-like 754 (0.0962%).

- **Decision.**

  1. **The implemented gate.** A build is **deferrable** iff **both** hold, evaluated in this order:
     `gh_is_pr` is falsey, **and** its `git_branch` matches **no** pattern in a frozen, named
     protected/release pattern table. Every other build — including every build whose inputs are
     missing, unparseable or unrecognised — is **non-deferrable**. The pattern table lives in
     `scheduler_core/eligibility.py` as data, each entry carrying the §3.4 class it approximates and the
     profile row that motivated it.

  2. **Unresolvable direction: fail closed.** Missing `gh_is_pr`, missing/blank `git_branch`, or any
     input the gate cannot interpret ⇒ **non-deferrable (run now)**. The gate's error is deliberately
     one-sided: it may run a build that could safely have waited, and it must not defer a build it does
     not understand. This is asserted by test, not merely documented.

  3. **Two §3.4 classes are not approximated at all, and this is declared rather than papered over.**
     - **(d) manually-triggered builds** have no marker in the data. They are silently pooled into
       whichever class their PR/branch values imply. Size: **unmeasurable in this corpus**.
     - **(e) scheduled/nightly builds** likewise have no marker (Travis cron postdates most of this
       2011–2016 release). Consequence: the deferrable set produced by this gate consists **entirely**
       of §3.4 class (f). **The single most obviously-deferrable category in the frozen design is
       absent from the evidence base**, and every carbon/latency number in this study is therefore
       computed over the *harder*, more marginal part of the deferrable population.

  4. **PR builds are treated as blocking.** §3.4 says "pull-request-**blocking**"; whether a PR check
     was a required status check is not recorded. All 140,506 PR builds are therefore treated as
     blocking ⇒ non-deferrable. This is the conservative direction under (2). Note that `git_branch` on
     a PR build appears to record the PR's **target** branch (81.4% of PR builds — 114,393 of 140,506 —
     carry a `master`-like name), so the two inputs are not independent; the gate tests `gh_is_pr`
     first, so this does not change any outcome, but it does mean branch-pattern statistics must not be
     read as statistics about push builds.

  5. **The one consequential judgement call, declared now and swept later.** `develop`/`dev`/`devel`/
     `development` (62,408 builds, 7.9609% by the `^(develop|dev)$` pattern alone) are **not** treated
     as protected in the primary rule, because §3.4's non-deferrable class is "**production**-branch",
     and an integration branch is by construction not production. This is the choice most likely to be
     challenged, so it does not stay a silent constant: it is registered as a named variant
     (`protected_includes_integration`) in the §4 **deferrable-fraction sensitivity sweep** at P3-T4,
     alongside the primary. No other pattern-table entry is swept individually.

  6. **What the "eligibility-gate safety = 0 non-deferrable builds deferred" metric (§4) actually
     proves.** `code/replay/validate_invariants.py` re-derives eligibility from the raw columns through
     a **separate code path** that does not import `eligibility.py`. A pass therefore proves the
     simulator never deferred a build **this rule** calls non-deferrable — i.e. **internal consistency
     between the gate and its consumers**. It is *not*, and must never be reported as, evidence that
     the rule identifies genuinely deferrable builds. The two claims are one word apart in English and
     must be kept apart everywhere in the write-up.

  7. **Naming discipline.** In code, results and the dissertation the gate's output is called
     **`eligible` / `deferrable-by-rule`**, never "safe to defer" and never "non-urgent".

- **Rationale.** The alternatives were: (i) drop Stage 1 — impossible, it is frozen invariant 1 and the
  thing that keeps risk separate from urgency; (ii) *infer* deferability from data, e.g. by learning it
  from outcomes — this is precisely the conflation §3.4 exists to prevent, and would make the ML score
  its own eligibility gate; (iii) restrict the study to builds whose trigger is known — no such subset
  exists here; (iv) approximate from the two available columns and declare the approximation's exact
  shape and blind spots up front. Only (iv) is both executable and honest. Fail-closed (2) was chosen
  over fail-open because the asymmetry of harm is real and asymmetric: wrongly running a deferrable
  build costs some foregone carbon saving, while wrongly deferring an urgent build costs developer
  feedback on a change someone is waiting for — and only the first of those is recoverable.

- **Consequences.**
  - **New:** `scheduler_core/eligibility.py`, `code/replay/validate_invariants.py`,
    `tests/test_eligibility.py`, `scripts/profile_branches.py`, `results/p2/branch_profile.{json,md}`.
  - **Threats to validity (§6) gains a first-order entry**, to be carried verbatim into P5-T4: *the
    study's independent variable — deferability — is not observed. It is approximated by a rule over
    two proxy columns, two of the six specified trigger classes cannot be approximated at all, and the
    approximation's error rate is **unmeasurable in this corpus** because no ground-truth deferability,
    developer-urgency or business-priority label exists in TravisTorrent. No result in this study should
    be read as evidence about which builds are genuinely safe to delay.* This is the construct-validity
    limit of the whole artifact, not a footnote about one module.
  - **P3-T4** must carry the `protected_includes_integration` variant and the deferrable-fraction sweep;
    a gate this approximate makes the sweep the load-bearing robustness result, not a nice-to-have.
  - **P4** inherits the implication that a deployed artifact must take eligibility from **team
    configuration**, not from this rule — the rule is an experimental stand-in for a policy input that a
    real user would supply. Recorded here as a consequence; the P4 contract itself is **not** changed by
    this entry and stays as specified until P3 resolves the null path.
  - **Strategy ③ (eligibility-only)** is a baseline built on this approximation, so ③-vs-⑤ comparisons
    inherit its error in **both** arms — which is the reason the comparison remains informative even
    though the gate is approximate: the gate is held identical across strategies by construction.

### DL-021 — `P_avg_W` is pinned at 42.5 W, cited from CodeCarbon's constant-mode CPU fallback (discharges DL-007's cite-or-log)

- **Date:** 2026-09-20
- **Status:** Accepted (implementation-level; **written before any line of `accounting.py` existed**,
  per R4 and `development_plan.md` P2-T2 S1)
- **Spec section affected:** §3.2 (the energy model's power constant). **No clause is amended.**
  DL-007 deliberately left `P_avg_W` unset and instructed that it be *cited* at implementation time and
  recorded "in config + a follow-up DL entry with the citation"; `results/p0/eval_protocol.md` §8 and
  §11 repeat that this is *the only value the protocol defers by design*. This entry is that follow-up.

- **Context.** DL-007 fixed the formula `E_kWh = (P_avg_W / 1000) · (duration_s / 3600)` and DL-010
  fixed `duration_s = tr_duration`, but neither fixed the wattage — precisely so that no session would
  invent one (R1). TravisTorrent records no hardware, no power draw and no machine type for the builds
  it contains, so `P_avg_W` **cannot be measured from the backbone dataset**; it must come from an
  external published source, which is what DL-007 anticipated. The named candidate sources are
  CodeCarbon and Eco-CI (spec §3.2, "CodeCarbon/EcoCI software models").

- **Decision.**

  1. **`P_avg_W = 42.5`** watts — the average power CodeCarbon attributes to a CPU it cannot identify.
     It is a **derived** figure, and both of its factors are quoted from the source rather than
     restated from memory:

     | Factor | Value | Where |
     | :-- | :-- | :-- |
     | Global fallback TDP | `POWER_CONSTANT = 85` (W) | `codecarbon/external/hardware.py` line 13, tag `v3.3.1` |
     | Assumed mean utilisation of TDP | `CONSUMPTION_PERCENTAGE_CONSTANT = 0.5` | same file, line 15 |
     | Constant-mode power law | `power = self._tdp * CONSUMPTION_PERCENTAGE_CONSTANT` | same file, line 256 (`_get_power_from_cpus`) |

     ⇒ `P_avg_W = 85 × 0.5 = 42.5`.

  2. **Citation of record** (recorded verbatim in `scheduler_core/config/energy.json` and reproduced in
     the threats chapter):
     - CodeCarbon, *Methodology — CPU power estimation*.
       <https://docs.codecarbon.io/latest/explanation/methodology/> — "If the CPU is not found in the
       data source, a global constant will be applied"; "CodeCarbon assumes that 50% of the TDP will be
       the average power consumption to make this approximation." Accessed 2026-09-20.
     - CodeCarbon source, **pinned at release tag `v3.3.1`** (published 2026-09-09), file
       `codecarbon/external/hardware.py`:
       <https://github.com/mlco2/codecarbon/blob/v3.3.1/codecarbon/external/hardware.py> — the two
       constants and the constant-mode power law quoted in (1). Accessed 2026-09-20.

     The tag is pinned rather than `master` so the citation stays checkable (R8): a later CodeCarbon
     release that changes either constant does not silently change this study's energy model.

  3. **Scope of the constant.** 42.5 W is CodeCarbon's **CPU-only** constant-mode figure. This artifact
     applies it as the *whole-machine* `P_avg_W` and adds **no** RAM or GPU term. Travis's hosted Linux
     builds are CPU-bound container/VM workloads with no attached GPU, and CodeCarbon's RAM model needs
     an installed-memory figure that TravisTorrent does not record. The omission biases **absolute**
     gCO₂e **downward** and is declared as such; it does not affect relative strategy comparisons,
     which is the comparison this study actually rests on (DL-007 rationale).

  4. **Eco-CI was considered and rejected as the source.** Eco-CI estimates power from a per-machine
     regression over CPU utilisation and SPECpower-derived machine models. It yields no single published
     constant that can be pinned and re-checked, and it needs a utilisation time series that this
     replay — which knows only a build's wall-clock duration — cannot supply. CodeCarbon's constant mode
     is the weaker model but the **citable and reproducible** one, which is what DL-007 asked for.

- **Rationale.** DL-007's own rationale already records why this choice is tolerable: `P_avg` scales
  every strategy identically, so the **relative** carbon comparisons that carry RQ4 are invariant to it,
  while **absolute** gCO₂e claims are not — hence the mandatory ±50% band, which this entry leaves
  untouched at `P_avg × {0.5, 1.0, 1.5}` = **{21.25, 42.5, 63.75} W**. Choosing a *documented default
  for an unidentified CPU* is also the honest match to the epistemic situation: the hardware genuinely
  is unidentified, and a sharper-looking figure would imply knowledge this dataset does not contain.

- **Consequences.**
  - **New:** `scheduler_core/accounting.py`, `scheduler_core/config/energy.json`,
    `tests/test_accounting.py`.
  - **The energy config is JSON, not YAML.** `pyproject.toml`/`requirements.lock.txt` pin no YAML
    reader, and P2-T2's DoD does not need one; adding a runtime dependency belongs to the task that
    actually requires it. **Carried forward:** P2-T3/P2-T5 must load
    `scheduler_core/config/policy_spec.yaml` (named by Layer 0-A invariant 7 and by the plan), so one of
    those tasks has to either add PyYAML to the §3.2 stack under its own DL entry or justify a different
    reader. Flagged here so it is not discovered late.
  - **Task-number drift, recorded not acted on.** `eval_protocol.md` §8/§11 assign the `P_avg` pinning to
    "P2-T3" and §7 assigns the `W_max` config file to "P2-T2". Those IDs are from the **pre-DL-012**
    22-task plan; under the current 28-task plan the accounting task is **P2-T2** and `decide()` is
    **P2-T3**. This entry discharges the `P_avg` obligation at the task that now owns accounting. The
    `W_max`/window constants are **not** placed in the energy config — they are policy thresholds and
    belong to `policy_spec.yaml` under invariant 7 (evidence-derived, never hand-tuned), fitted in P2-T5.
    No protocol clause is changed; only the task label it was written against has moved.
  - **Threats chapter (§6), P5-T4** gains: *the power constant is a documented default for an
    unidentified CPU, not a measurement of Travis build hardware; it carries no RAM or GPU term;
    absolute gCO₂e figures are therefore indicative only and every one of them is reported inside the
    ±50% band.*
  - **P3-T4** sweeps the band; the DL-010 `n_jobs`-scaled variant hook is implemented in the same module
    so the parallel-compute under-count can be bracketed alongside it.

### DL-022 — PyYAML enters the §3.2 stack; the `policy_spec.yaml` schema contract; and the bootstrap spec may never produce a reported number

- **Date:** 2026-09-22
- **Status:** Accepted (implementation-level; **written before any line of `policy.py` existed**,
  per R4 and `development_plan.md` P2-T3)
- **Spec section affected:** §3.2 (the pinned CPU-only stack — one dependency added). **No research
  clause is amended.** Layer 0-A invariant 7 already names `scheduler_core/config/policy_spec.yaml`
  as the artifact every threshold must trace through, and the plan makes it P2-T5's deliverable; this
  entry records how that file is *read*, *validated* and *prevented from being faked*.

- **Context.** P2-T3 must load a YAML policy spec, but `requirements.txt` / `requirements.lock.txt`
  pin no YAML reader — a gap carried forward explicitly at the P2-T2 gate (DL-021 §Consequences, and
  `PROGRESS.md` `carried_forward`). P2-T2 sidestepped it by writing the energy config as JSON, which
  was correct for a task that did not need YAML, but the policy spec's format is not a free choice:
  it is named `.yaml` by Layer 0-A and by the plan.

  There is a second, larger problem specific to this task. P2-T3 builds `decide()` **before** P2-T5
  fits the real spec, so the DoD requires a *bootstrap* spec to make the module testable. A
  hand-written spec file containing a `d_threshold` and a `W_max` is precisely the object invariant 7
  exists to forbid. Without a guard, the bootstrap spec is indistinguishable at load time from a
  fitted one, and nothing would stop a later task — or a later session — from producing headline
  numbers on hand-typed constants.

- **Decision.**

  1. **PyYAML joins the stack.** Added to `requirements.txt` and pinned in `requirements.lock.txt`
     at the version the environment resolves. Rationale for a dependency rather than a hand-rolled
     reader: a restricted-subset parser written here would be unreviewed code sitting directly under
     the project's most safety-critical file. PyYAML is loaded **only** via `yaml.safe_load` — never
     `load`/`full_load` — so no spec file can construct a Python object.

  2. **The spec schema is closed, and validation is strict.** `load_policy_spec()` rejects, as an
     error and never a warning: an unknown top-level or nested key; a missing required key; a
     `schema_version` it does not implement; a `policy_path` outside the declared set; a threshold
     that is absent, non-numeric, non-finite or out of range; and a spec carrying **no `provenance`
     block**. A closed schema is the mechanism that makes invariant 7 checkable: a threshold that is
     not in the schema cannot be smuggled in, and a threshold that is in the schema must declare
     where it came from.

  3. **Every threshold carries its own source.** The `provenance` block must name `fitted`
     (boolean), `fitted_by`, `fitted_on` (the splits it was fitted over) and `sources` (the
     `results/` files the values trace to). P2-T5's `fit_policy.py` fills these; nothing else may.

  4. **The bootstrap spec is quarantined by construction.** `policy_spec.bootstrap.yaml` declares
     `provenance.fitted: false`. `load_policy_spec()` takes `require_fitted`, and **every consumer
     that produces a reported number must pass `require_fitted=True`**, which refuses an unfitted
     spec outright. The bootstrap spec is therefore usable for tests, examples and wiring, and
     structurally unusable for results. Its filename is also distinct from `policy_spec.yaml`, so it
     cannot be loaded by default or mistaken for the fitted artifact in a directory listing.

  5. **`decide()` is a pure evaluator and holds no policy of its own.** It reads no file, keeps no
     state, performs no I/O, and contains **no numeric threshold** — every constant it applies comes
     from the loaded spec. A test asserts this on the module's AST. Where the spec is silent, the
     correct behaviour is to raise, not to fall back on a built-in default: a silent default is a
     hand-tuned threshold wearing a disguise.

  6. **Stage 1 runs first and unconditionally.** `decide()` calls the P2-T1 gate before reading any
     policy value, and a non-deferrable build returns `run_now` **without Stage 2 being consulted at
     all** — not with Stage 2 consulted and overridden. This is frozen invariant 1 ("risk ≠ urgency")
     expressed as control flow, and it is asserted by test rather than by comment.

  7. **`decide()` never receives the current build's `tr_duration`.** The build mapping handed to
     `decide()` is checked against the A1.2 blocklist on every call, and a build carrying
     `tr_duration` / `tr_log_buildduration` raises rather than being silently ignored. Loud refusal
     is the point: a leak that is quietly dropped is a leak that recurs.

- **Rationale.** The costly failure mode for this project is not a bug in `decide()` — it is a
  plausible-looking `policy_spec.yaml` whose numbers came from somewhere other than the evidence.
  Decisions 2–4 make that failure loud at load time instead of invisible until the viva. Decision 1 is
  the minor half of this entry and is recorded chiefly because the frozen stack is not edited silently.

- **Consequences.**
  - **New:** `scheduler_core/policy.py`, `scheduler_core/config/policy_spec.bootstrap.yaml`,
    `tests/test_policy.py`; `requirements.txt` + `requirements.lock.txt` gain PyYAML.
  - **Binding on P2-T5:** `fit_policy.py` writes `policy_spec.yaml` against this schema, sets
    `provenance.fitted: true`, and lists in `provenance.sources` every `results/` file each value
    traces to. It must also pass its own output through `load_policy_spec(require_fitted=True)`.
  - **Binding on P2-T4 and P4:** the simulator and the REST API load with `require_fitted=True`. The
    sample run in P2-T4 is the one permitted exception — it is a wiring check, not a result — and
    must label its output as bootstrap-derived wherever it is shown.
  - **Threats (§6), P5-T4:** the null path means the shipped policy is expected to be duration-only.
    The SE-informed branch will therefore be implemented and *tested* but, if P3 confirms the null,
    **never exercised on real evidence**. That asymmetry is declared here so the write-up does not
    imply the SE branch was validated in use.
  - `requirements.lock.txt` no longer matches a bare `pip freeze` of the pre-P2-T3 environment; the
    lock is regenerated and the suite re-run as part of this task's evidence.

### DL-023 — The six strategies, operationally; the predeclared sweep grids; and what a replay record is

- **Date:** 2026-09-23
- **Status:** Accepted. **Items 1② and 1⑥ are author decisions** (taken 2026-09-23 when the ambiguity
  below was put to the author, before any simulator code existed). The rest is implementation-level,
  **written before a single line of `replay/simulator.py` existed**, per R4 and `development_plan.md`
  P2-T4.
- **Spec section affected:** frozen §4 (the strategy list) and Layer 0-A (six strategies) are
  **operationalised, not amended**; `eval_protocol.md` §6 (metrics) and §A1.5/DL-013 (swept
  frontiers) are given a concrete record schema and concrete grids. No RQ, floor or invariant changes.

- **Context.** Layer 0-A names six strategies and DL-013 requires every strategy to expose one
  aggressiveness parameter swept over a grid "from config — never chosen after seeing a result". No
  document yet says, operationally, what any strategy *does* to a build, and three gaps are real:
  1. **② vs ③ collapse.** Frozen §4 defines ② as *"defer all **eligible** builds to the greenest
     slot"* and ③ as *"Stage 1 gate + fixed window"*; Layer 0-A renames ② *"blanket carbon-aware"*.
     If ② uses the same gate and the same window as ③, the two strategies are the same function and
     RQ4 compares a baseline against itself.
  2. **⑥'s scope** (frozen §4 ④, "prune low-likelihood builds, run kept builds immediately") does not
     say whether a risk score may skip a build that Stage 1 calls urgent.
  3. **No grid exists** for `d_threshold`, for ⑤'s "policy scale", or for ⑥'s skip threshold, and the
     schema-v1 `policy_spec.yaml` (DL-022) has no key to hold one.

- **Decision.**

  1. **The six strategies.** Every strategy that schedules does so through the shared
     `scheduler_core.policy.decide()` (invariant 5), under a spec *derived* from the loaded one and
     re-validated by the same closed-schema validator — the simulator never re-implements Stage 1 or
     Stage 2. `d̂` in every strategy comes from the **frozen** P1-T4 control (fit id
     `1088d5546f47ff12`), never refitted.

     | # | Strategy | Operational definition | Swept parameter |
     | :-: | :-- | :-- | :-- |
     | ① | static | every build `run_now` at arrival; `decide()` is not consulted | none — one point |
     | ② | blanket carbon-aware, **gated, whole-week horizon** *(author decision)* | `decide()` with `d_threshold = 0`, `w_max = 167 h` — every Stage-1-eligible build goes to the greenest slot in the whole 168-slot profile; `d̂` plays no role. 167 is `carbon.N_SLOTS − 1`, the width of the profile, not a tuned value. The literal frozen-§4 reading; gate safety stays 0. | none — one point |
     | ③ | eligibility-only | `decide()` with `d_threshold = 0`, `w_max ∈ W` | `w_max` |
     | ④a / ④b | duration-control-only | `decide()` on the duration-only path, `(d_threshold, w_max) ∈ D × W`; `d̂` from `predict_4a` (XGBoost regressor) / `predict_4b` (expanding project prior) | `(d_threshold, w_max)` |
     | ⑤ | SE-informed evidence-derived | `decide()` under the **loaded** spec (its own `policy_path`, window form and admitted families), with its active block's `d_threshold` and `w_max` set to each point of the **same** `D × W` grid — so ④ and ⑤ are evaluated at identical parameter points and P3-T3's matching is exact. `d̂` = the primary form (④b). On the `se_informed` path `p̂` is supplied and the §7 window `w_max·(1−p̂)` applies inside. | `(d_threshold, w_max)` |
     | ⑥ | risk-only skip, **eligible builds only** *(author decision)* | Stage 1 via `eligibility.classify` (the function `decide()` calls, same variant as the spec). A non-deferrable build **always runs now**. A deferrable build with `p̂ < τ_skip` is **skipped** — never run, zero energy, no feedback; every other build runs now. Keeps invariant 1 true for all six strategies: a risk score never overrides urgency. | `τ_skip` |

     Two consequences stated so they are never mistaken for findings: **③ is ④ at `d_threshold = 0`**
     (deliberate — the only difference between them is duration selectivity), and **while the spec is
     on the `duration_only_fallback` path, ⑤ is ④b by construction** (identical decisions at every
     point). That second identity is what the null path *means* operationally.

     `p̂` for ⑤ (when on the SE path) and ⑥ is the calibrated `xgboost:full` arm of P1-T5 — the
     primary algorithm's all-features SE signal. An admitted-family arm, if P2-T5 ever needs one, is
     P2-T5's to specify under its own entry.

  2. **The grids — sweep resolution, not thresholds.** Held in `code/replay/sweep_grid.json`,
     frozen by this entry:
     - `W` = **{6, 12, 24} h** — `eval_protocol.md` §7 / §A1.8 / DL-008, verbatim.
     - `D` = **{0, 60, 120, 240, 480, 960, 1920, 3840, 7680, 15360} s** — `0` plus a doubling ladder
       from one minute. Doubling is uniform on the log scale `d̂` is modelled on. The ladder is placed
       against *descriptive* split statistics already on file (`results/p1/splits_summary.md`, §A1.2
       role 1): train median 588 s, train p95 5,725 s, calibration p95 11,638 s — so it runs from
       "defer every eligible build" (0) past the heaviest recorded p95, where almost nothing defers.
       No sweep result existed when it was chosen.
     - `τ_skip` = **{0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30}** — from "skip nothing" (⑥ ≡ ①) up to
       just above the train failure base rate (24.354%, `results/p1/splits_summary.md`).
     - A grid point is **where a strategy is evaluated**, not a value any policy adopts: the fitted
       `d_threshold`/`w_max` are P2-T5's, chosen on the calibration replay by its own rule. A change to
       any grid after a sweep result has been seen is a **new DL entry**, never an edit to this file.
     - **Forward-binding on P2-T5:** schema v1 of `policy_spec.yaml` has no key for a grid. Recording
       the grids in the spec (DL-013 §1) therefore needs a schema-version bump, under P2-T5's own DL.

  3. **Accounting (A1.2 role 1 only).** The observed `tr_duration` reaches the simulator's accounting
     step **after** `decide()` has returned, and never the build mapping `decide()` sees (which
     `decide()` itself refuses — DL-022 §7). `E = accounting.energy_kwh(tr_duration, P_avg)` from
     `config/energy.json` (DL-021); `carbon = E · I(scheduled slot)`, the whole build charged at the
     slot it was **scheduled into** (§8's definition — a build spanning slots is not split). Latency
     = the deferral offset in whole hours (`decide()` works on hour-of-week slots; a deferred build
     starts at arrival + offset). `TTFF = latency + tr_duration/3600` for failed builds that ran.
     A **skipped** build has `E = carbon = 0`, no latency and no TTFF; if it failed it is a **missed
     failure** (§6, DL-005), and the carbon table must be read beside that count.
     **Unaccountable builds.** `results/p0/data_profile.md` records 426 analytic builds with no
     `tr_duration` (and 610 with a non-positive one). They stay in the replay — `decide()` never reads
     duration, and `duration_estimator.usable_label_mask` excludes such builds from *fitting only*,
     never from the replay. A build whose observed duration is missing, non-finite or negative gets a
     decision like any other, but its energy, carbon and TTFF are left **empty (not measured)**, never
     zero-filled (R1). Because the set is a property of the build, not the strategy, it is identical
     for every strategy at every grid point, so excluding it from carbon/TTFF aggregates preserves the
     pairing; its size is reported beside every aggregate. A zero duration is accountable (`E = 0`).

  4. **The P2-T4 sample (a wiring check, not a result).** A seeded (`RANDOM_SEED = 42`) uniform draw of
     **12,000** builds, without replacement, from the **calibration** split (DoD: ≥ 10k). `d̂` is
     computed *before* sampling over every calibration build, so each sampled build carries its
     project's full causal history (DL-014) rather than a history thinned by the sample. Builds are
     replayed in `gh_build_started_at` order, ties by `tr_build_id`. The P2-T4 run is driven by the
     **bootstrap** spec — the one exception DL-022 permits — so every output file is labelled
     *bootstrap-derived* and **no number from it is a result**. The test split is dropped unread;
     train builds are not needed and are also dropped.

  5. **What a record is.** One row per **build × strategy × grid point**, self-contained, carrying:
     identity and Stage-1 inputs (so the independent validator can audit any row alone); the arrival
     slot; eligibility and the gate rule; the action (`run_now` / `defer` / `skip`); a compact
     `reason_code`; the policy path taken; `d̂` and its form; `p̂` where used; the swept parameters;
     window, delay, scheduled slot and both intensities; the observed duration (labelled accounting
     only), energy, carbon, the outcome `y_fail`, and TTFF. The full `decide()` reason string is not
     repeated on 10⁶ rows: a record carries every input `decide()` saw, so re-calling it reproduces the
     string exactly, and a worked sample of full strings is written beside the records.

  6. **Determinism, resumability, identical inputs.** Every (strategy, grid point) is computed into its
     own part file keyed by a **run fingerprint** (spec, grid, energy config, sample, fit ids). A
     resumed run reuses a part only if its fingerprint matches, so resuming can save time but can never
     change a byte. The final tidy file is assembled in a fixed order, gzip-compressed with its
     timestamp zeroed, and is required to be **byte-identical** across two runs. The runner asserts,
     and a test re-asserts, that **every strategy at every point saw the identical build set**.

  7. **Safety audit.** The independent `replay/validate_invariants.py` audits **every row of every
     strategy**; all six are gated, so the expected count is 0 throughout. A `skip` is not a deferral,
     so the validator additionally checks, by its own independent re-derivation, that ⑥ never skipped
     a non-deferrable build. As DL-020 §6 requires, a pass means *consistency with the rule*, never
     correctness of the rule.

- **Rationale.** The alternative for ② — ignore Stage 1 and defer every build — matches the word
  "blanket" but departs from the frozen text and would make gate safety non-zero by design; the author
  chose the literal frozen reading, which keeps ② distinct from ③ through its horizon rather than its
  gate. Putting ④ and ⑤ on the same grid is what makes DL-013's "matched operating points" a
  comparison between identical parameter settings rather than an interpolation between unrelated
  sweeps. Fixing the grids before any curve exists is the only way their choice cannot be tuned.

- **Consequences.**
  - **New:** `code/replay/simulator.py`, `code/replay/sweep_grid.json`, `code/scripts/run_replay.py`,
    `code/tests/test_simulator.py`; `scheduler_core/policy.py` gains `spec_from_mapping()` — the
    existing validator exposed for an in-memory mapping, so derived sweep specs go through the *same*
    closed-schema checks as a file (no new threshold, no default; the AST test still binds).
  - **Binding on P2-T5:** its calibration sweep runs through this simulator unchanged; the grids above
    are the ones it records (schema bump, own DL).
  - **Binding on P3-T2/P3-T3:** the test replay uses this record schema; ⑤ must beat **both** ④a and
    ④b (§A1.9) at matched points of this grid.
  - **Threats (P5-T4):** latency is hour-granular; a build is charged one slot's mean intensity for its
    whole duration; ⑥'s skipped failures are feedback *lost*, not delayed — its carbon is not
    comparable to the others' without the missed-failure count beside it.

### DL-024 — How `fit_policy.py` fixes the frozen operating point; `policy_spec.yaml` schema v2; replay characteristics carried into P3

- **Date:** 2026-09-24
- **Status:** Accepted. **Items 1, 2 and 3 are author decisions** taken 2026-09-24 at the start of
  P2-T5, when the gap below was put to the author, **before `fit_policy.py` existed and before any
  selection rule had been evaluated on any sweep**. Item 5 records author decisions taken at the
  P2-T4 gate the same day. The rest is implementation-level, written before the code, per R4.
- **Spec section affected:** `eval_protocol.md` §A1.6 ("`d_threshold` and `W_max` are fitted on the
  calibration-split replay") is given the concrete rule it lacked; §A1.7 (decision-level half) is
  applied as written; DL-022 §2's schema is versioned (v1 → v2) as DL-023 §2 required. No RQ, floor,
  grid, strategy or invariant changes.

- **Context.** §A1.6 says ④'s `d_threshold` and `W_max` are *fitted* on the calibration replay, and
  DL-023 §2 says they are "P2-T5's, chosen on the calibration replay by its own rule" — but no
  document says what that rule is. A swept frontier has no single best point without a declared
  trade-off, so a rule has to be predeclared, or the operating point would be picked by eye (a
  hand-tuned threshold, invariant 7). Two facts bound the stakes, and are stated so the rule is not
  over-weighted:
  1. On the null path (`results/p1/admission.json`: `policy_path: duration_only_fallback`), ⑤ ≡ ④b
     at every grid point (DL-023 §1). P3-T3's RQ2 test compares **whole frontiers** at matched points,
     so the RQ2 verdict does **not** depend on the operating point chosen here.
  2. What the point does fix: the single frozen setting that P3-T2 reports ⑤ at (RQ4's headline row)
     and that the P4 prototype runs.
  The author had seen the P2-T4 **bootstrap-labelled** aggregates at `W = 24 h`
  (`results/p2/sample_run/summary.md`) when choosing; no candidate rule had been computed.

- **Decision.**

  1. **Selection rule — carbon retention** *(author decision)*. Over the **④b** (primary form,
     P1-T4) calibration sweep — all 30 `(d_threshold, w_max) ∈ D × W` points of the frozen grid:
     - `saving(pt) = −carbon_pct_vs_static(pt)`, the % carbon reduction vs ① static, from the
       simulator's own `summarise()` on the sweep records.
     - `S* = max saving` over the 30 points. If `S* ≤ 0` the fit **fails** (no point saves carbon;
       nothing to fit) — it never falls back to a default.
     - **Admissible points:** `saving(pt) ≥ ρ · S*`, with **ρ = 0.90**.
     - **Chosen point:** the admissible point with the **lowest TTFF p95 (failed builds)**; ties →
       larger `d_threshold`, then smaller `w_max`.
     - Rationale: A1.6's own reason for the shape — deferring a short build pays full latency for a
       negligible carbon gain — is a retention statement: keep nearly all of the achievable saving,
       spend as little failure-feedback delay as possible to get it. TTFF p95 is the axis §A1.13
       names as RQ2's live channel.
     - **ρ is a design parameter, not a result** (R1). It is reported at **ρ ∈ {0.80, 0.95}** beside
       the primary 0.90, and `policy_derivation.md` states which spec values change. The spec ships
       ρ = 0.90 only; the sensitivity points never enter it.
     - `W_max` is fitted by the same rule (it is one of the two swept coordinates), exactly as §A1.6
       says. §7's `W_max = 24 h` default is therefore **not** assumed; `{6, 12, 24}` remains P3-T4's
       sensitivity sweep.
  2. **Population** *(author decision)*. The fitting sweep replays the frozen DL-023 §4 sample —
     12,000 calibration builds, seed 42, as fixed in `replay/sweep_grid.json` — through
     `replay/simulator.py` **unchanged**, using `scripts/run_replay.py`'s loading and trace functions
     unchanged. The grid file is not edited. Declared threat: the operating point is fitted on 12,000
     of 138,687 calibration builds (8.65%); its sampling noise is not bootstrapped here.
  3. **④b primary form kept** *(author decision)*. The predeclared expanding project prior stays the
     primary `d̂` (P1-T4 fit id `1088d5546f47ff12`). The trailing-50 sensitivity that beat it on
     calibration log1p MAE (0.2886 vs 0.6010, `results/p1/duration_control.md`) is reported as a
     finding and belongs in P3-T4's sensitivities. Switching would have cascaded into every P1-T5/T6
     arm (each uses the expanding `d̂` as a feature) and re-derived the P1 verdicts; it is not done.
  4. **The sweep's input spec is a structural candidate, never a threshold source.** `fit_policy.py`
     builds an in-memory candidate — `policy_path` read from `admission.json`, `stage1.variant:
     primary` (DL-020 §5 headline), `provenance.fitted: false` — validated by `policy.spec_from_mapping`
     with `require_fitted=False`. That is the one further exception to DL-022 §4's quarantine, and it
     is safe for a stated reason: every setting that calls `decide()` substitutes its own grid-point
     `(d_threshold, w_max)` (DL-023 §1), so no candidate threshold reaches a record. The candidate's
     placeholder thresholds are the grid's own first `D` value and last `W` value, not new numbers.
     Its sweep outputs are labelled *calibration-split fitting evidence* — not a result about any
     strategy, and never reported as RQ4 numbers.
  5. **Replay characteristics are documented, not corrected** *(author decision, P2-T4 gate)*. The
     frozen primary grid and DL-023's strategy definitions stand. The primary τ grid is **not**
     re-chosen from the observed p̂ distribution. Two observed properties are carried into P3 as
     characteristics to report (`results/p2/sample_run/REGENERATE.md`): (a) ⑥'s τ frontier is coarse —
     the isotonic `xgboost:full` p̂ takes 42 distinct values on the sample, 87.2% of them in
     (0.25, 0.30], so the τ grid yields one non-trivial step; (b) ④a has limited prediction support
     at the top of `D` — its estimate never exceeds 4,310.20 s on the sample, so ④a defers nothing at
     `D ≥ 3,840 s` and its frontier is shorter than ④b's. P3-T3 reports the ④a frontier over the
     points it actually spans; nothing is extrapolated. The 61 MB replay decision files are not
     committed; their sha256, determinism and validator results are.
  6. **Decision-level half of §A1.7 on the null path.** Admission needs **both** altitudes, and the
     model-level admitted set is empty at ×0.5, ×1 and ×2. No family can be admitted, so there is no
     ⑤-vs-④ frontier to test: ⑤ ≡ ④b identically. `fit_policy.py` records the decision-level test as
     **not applicable (no candidate family)**, verifies the ⑤ ≡ ④b identity on the sweep records rather
     than asserting it, and reports the area between frontiers as exactly 0 by construction. The
     ×0.5/×2 sweep is re-run from `results/p1/ablation/deltas.json` through `scheduler_core.admission`
     (not copied from `admission.json`), a spec is fitted at each multiplier, and the spec elements
     that differ are listed. No `se_informed` block is emitted. On the null path, A1.8's window form
     and S2's regime gating have nothing to act on, and that is stated rather than stubbed.
  7. **Schema v2** (DL-023 §2's bump). `policy.py` implements schema versions **1 and 2**. v1 is
     unchanged, so the bootstrap spec and the P2-T4 run fingerprint stay reproducible. v2 adds:
     - a required top-level **`sweep`** block: the frozen grids `w_max_hours`, `d_threshold_seconds`,
       `tau_skip` and `blanket_w_max_hours`, copied from `replay/sweep_grid.json`, plus its path and
       its `grid_sha256`, recorded **before** the P3 run (DL-013 §1);
     - required provenance keys **`values`** (one entry per numeric spec field, each naming its
       `results/` source file(s) and the rule that produced it), **`command`**, **`seed`**,
       **`generated`** (the fitting date) and **`test_split_read`** (must be `false`).
     - **Tightening:** a spec with `provenance.fitted: true` must be v2, and every numeric field in
       its blocks must have a `provenance.values` entry with a non-empty `source`. A fitted v1 spec is
       now refused. The one P2-T3 test that built a fitted v1 spec is updated to v2, not deleted.
     - `decide()` does not change; it reads the same two keys from the active block. The closed-schema
       rule holds for v2 as well: unknown keys are rejected at every level.
  8. **Reproducibility.** Re-running `fit_policy.py` must reproduce `policy_spec.yaml` byte for byte.
     The only time-dependent field is `provenance.generated`. `--verify` refits into memory, reuses
     the committed file's `generated` date, and fails unless the bytes are identical. The fitting
     trace digest and the sweep summary sha256 are also recorded.
  9. **Test split.** Nothing in P2-T5 reads a test project. `run_replay.load_split_builds` refuses
     `split="test"` and discards test rows chunk by chunk. `fit_policy.py` additionally asserts,
     against `results/p1/split_assignment.csv` (sha256 `3d9a7947…5cde`), that every project in the
     fitting trace is a calibration project, and records `test_split_read: false`.

- **Rationale.** A retention rule is the smallest predeclared commitment that turns a frontier into
  an operating point. It carries one visible parameter, reported at two alternatives, instead of an
  implicit one (a knee's axis normalisation) or a new absolute budget (a TTFF cap). Fitting on the
  frozen sample keeps DL-023's "unchanged" binding literal. Keeping ④b's primary avoids redoing P1 on
  the eve of the test split.

- **Consequences.**
  - **New:** `code/scripts/fit_policy.py`, `code/tests/test_fit_policy.py`,
    `code/scheduler_core/config/policy_spec.yaml` (v2, fitted), `results/p2/policy_derivation.md`,
    `results/p2/policy_fit/` (the fitting sweep's outputs; `decisions.csv.gz` not committed).
    **Changed:** `scheduler_core/policy.py` (schema v2 support, fitted ⇒ v2), one test in
    `tests/test_policy.py` (fitted fixture moved to v2).
  - **Binding on P3-T2/P3-T3:** load `policy_spec.yaml` with `require_fitted=True`, record its sha256,
    and assert that its `sweep.grid_sha256` equals `replay/sweep_grid.json`'s digest before replaying
    the test trace.
  - **Threats (P5-T4):** the operating point comes from a 12k sample and one declared ρ, and ρ's
    sensitivity is reported. On the null path, RQ4's headline row for ⑤ is ④b at that point by
    construction.

### DL-025 — A living research guide is regenerated at every gate; it is documentation, never governance

- **Date:** 2026-09-25
- **Status:** Accepted (process/documentation; **author directive** of 2026-09-25, given at the M2 gate
  before P3-T1 started). No research design, RQ, floor, grid, invariant or result changes.
- **Spec section affected:** none in the frozen spec. `governance/00_SESSION_PROTOCOL.md` gains one
  gate step (REPORT + GATE, step 1b).

- **Context.** The author asked for a single, browser-openable research guide that explains the whole
  project to a reader with no prior knowledge, reflects the actual repository state, and is kept up
  to date after every completed task. Without a rule, such a page drifts. A hand-typed number in it
  would also breach R1, and a page that looked authoritative could compete with `PROGRESS.md`.

- **Decision.**
  1. **Files.** `docs/research_guide.html` is **generated** from `docs/research_guide.template.html`
     and `docs/research_state.json` by `code/scripts/update_research_guide.py`. The state file holds the
     curated narrative (task write-ups, limitations, discrepancies, change history). Its `progress` and
     `evidence` sections are regenerated on every run.
  2. **No hand-typed numbers.** Numbers are read from `results/` (and the frozen spec) by
     `collect_evidence()`, or referenced in the curated text as `{{evidence.…}}` tokens that the script
     resolves. An unresolved token, a referenced file that does not exist, a task list that differs from
     `development_plan.md`, or a status that disagrees with `PROGRESS.md` fails the build.
  3. **Authority.** The guide is documentation. If it disagrees with `PROGRESS.md` or this log, those win,
     and the disagreement is fixed in the guide. It carries no instructions (like every state file).
  4. **Gate step.** At every gate, after `PROGRESS.md` is updated: update the finished task's narrative and
     the change history in `research_state.json`, then run the script (`--check`, then a build). The change
     history is append-only; earlier states are never rewritten. Calibration and test evidence stay
     visibly separate, and nothing is labelled final before P3 produces it.
  5. **Discrepancies are reported, not silently fixed.** Inconsistencies found between governed documents
     while building the guide are listed in its source-audit section with the governing source named.
     Correcting a governed file remains a separate act under R3/R4.

- **Rationale.** Generating the guide from result files keeps R1 intact, and the consistency checks make
  drift fail loudly instead of accumulating. Putting the step in the protocol makes the maintenance
  durable across sessions.

- **Consequences.** New: `docs/research_guide.html`, `docs/research_guide.template.html`,
  `docs/research_state.json`, `code/scripts/update_research_guide.py`. Changed:
  `governance/00_SESSION_PROTOCOL.md` (gate step 1b).

### DL-026 — Proposed P4 artifact direction: carbon-aware CI *decision support* as a reusable GitHub Action (conditional on P3)

- **Date:** 2026-09-25
- **Status:** **Proposed / Conditional** (author directive of 2026-09-25, recorded at the M2 gate before
  P3-T1 started). **Not accepted and not acted on.** It records an intended direction for Phase 4 only.
  It must be confirmed, amended or withdrawn by a **new** DL entry after P3-T5 and before P4-T1 starts.
  Until then, `development_plan.md` P4-T1..T3 and frozen spec §5 stand unchanged.
- **Spec section affected:** none now. If it is later accepted, it would amend frozen spec §5 (artifact
  definition) and `development_plan.md` P4-T1..T3. It would **not** amend §1–§4, Layer 0-A's RQs,
  `eval_protocol.md`, the feature contract or the split.

- **Context.** Spec §5 defines the artifact as a FastAPI `POST /decision` service (Must), a GitHub Action
  with deferred re-dispatch (Should) and a dashboard (Could). The author prefers an artifact that
  supports the developer's decision rather than rescheduling automatically. It would be a reusable
  GitHub Actions integration that ends at a RUN NOW / DEFER recommendation, and it would add execution-
  region awareness and forecast carbon intensity. The independent review's addendum (item 7, the
  untracked `INDEPENDENT_REVIEW_REPORT.md`) separately recommends that the P4 contract be narrowed to
  match the P3 verdict by a DL entry dated after P3-T5, before P4-T1. This entry records the direction
  without taking that later decision early.

- **Proposed direction (not yet decided).**
  1. **Flow.** Workflow/commit → pre-execution commit metadata (+ SE features *only if P3 admits them*)
     → commit-time expected-duration estimate → runner/location inference → current + forecast regional
     carbon intensity → estimated build carbon → policy decision → RUN NOW / DEFER recommendation →
     GitHub Step Summary.
  2. **Displayed values.** Detected or estimated execution region; location confidence and source;
     current intensity; forecast values; expected build duration; estimated carbon impact; the
     recommendation and its reason.
  3. **Region confidence hierarchy.** (i) explicitly configured region; (ii) a known cloud/runner region
     where one is available; (iii) IP-based geolocation as a fallback. An IP-derived location is always
     labelled an **estimate**, never ground truth about the physical datacenter.
  4. **Scope boundary.** No automatic rescheduling or re-dispatch. The research contribution ends at the
     decision/recommendation layer, and actual rescheduling is future work.

- **Conditions and constraints (binding if the direction is adopted).**
  1. **No null-path assumption.** The artifact's production inputs, model and request contract are
     chosen from the **final P3 evidence** (P3-T5 verdicts), not from the calibration-split null of
     P1-T7/P2-T5. Nothing in this entry presumes the duration-only path.
  2. **Protocol untouched.** This entry changes no frozen feature, evaluation criterion, materiality
     floor, grid, split or test-split handling. P3 runs exactly as `development_plan.md` and
     `eval_protocol.md` specify.
  3. **One shared core (invariant 5).** The recommendation must come from the identical
     `scheduler_core.decide()` and the frozen `policy_spec.yaml`, including Stage 1 exactly as evaluated.
     Richer live trigger context (e.g. `schedule` / `workflow_dispatch` events) may be displayed but may
     not alter the decision unless a later DL entry says so.
  4. **A1.2 still binds.** The current build's actual duration never reaches the decision. "Expected
     build duration" and "estimated carbon" are commit-time estimates and are labelled as such.
  5. **Declared gaps between evaluation and artifact** (to be stated wherever the artifact is presented):
     the policy was fitted and evaluated on a UK national hour-of-week mean profile, so a live forecast
     and any non-UK region are outside what was evaluated. The fitted thresholds are extrapolated there,
     not validated.

- **Open design questions deferred to the P4 DL** (recorded, not answered): how forecast values are
  presented to `decide()` without forking it; which carbon providers and regions are supported and on
  what licence/key terms; whether a thin API is kept to satisfy spec §5's "Must"; whether the decision is
  exposed as step outputs; how live inputs are kept identical to the evaluated inputs (training/serving
  parity), which depends on which path P3 supports.

- **Rationale.** Recording the direction now keeps it visible while making it explicit that it cannot
  influence P3. Keeping it Proposed/Conditional respects "fit before you look": the artifact contract
  follows the evidence, never the other way round.

- **Consequences.** None now: no code, plan, spec or results change. **Forward-binding on the P4 DL
  entry** (after P3-T5, before P4-T1): accept, amend or withdraw this direction, citing the P3 verdicts
  it rests on.

### DL-027 — Two predeclared P3-T4 sensitivities: a within-corpus temporal robustness sweep and a second, higher-variance grid profile

- **Date:** 2026-09-25
- **Status:** Accepted. **Author decision** of 2026-09-25 ("adopt both"), taken **before P3-T1 opened
  the test split**, on the recommendation of `INDEPENDENT_REVIEW_REPORT.md` addendum items 3 and 4.
  Written before any test-split number exists; no test build was read to write it.
- **Spec section affected:** frozen spec §6 (External validity: "a higher-variance zone may be added if
  time permits"), which is **exercised, not amended**. `development_plan.md` P3-T4 gains two sweeps, and
  P3-T1 and P3-T2 gain one persistence duty each (§3). No RQ, feature, floor, grid, split, frozen spec
  value or headline verdict rule changes.

- **Context.** The addendum identifies two viva-level weaknesses that can be turned into measured
  results cheaply: (a) TravisTorrent's age (trace 2011-04-16 → 2016-08-31), and (b) the UK 2024–25
  profile's low dynamic range (92.2–172.9 gCO₂/kWh, peak-to-trough 1.87×,
  `results/p0/carbon_profile.md`). With that range, a panel cannot tell whether "⑤ does not dominate ④"
  means SE carries no value or the grid cannot separate policies. Both sweeps are worthless unless
  they are predeclared before the test split is opened.

- **Decision.**

  1. **Temporal robustness sweep (addendum item 3).**
     - **Boundary, fixed now as a value:** `2015-03-28T13:00:51+00:00`. That is the median
       `gh_build_started_at` over the 783,931 train + calibration analytic builds (test 138,693
       dropped unread). Produced by `PYTHONPATH=. python scripts/fix_temporal_boundary.py` →
       `results/p3/predeclared/temporal_boundary.json` (split file sha256 `be1d175f…`). The script
       refuses to overwrite its output. **Early** = started < boundary, **late** = started ≥ boundary.
     - **What is stratified (no refit, no new model):** a *stratification of the single test
       evaluation*, as the addendum's design note allows. (i) The P3-T1 per-family ΔPR-AUC vs `{d̂}`,
       paired bootstrap (B = 1000, seed 42), recomputed **within each period** from the P3-T1 test
       scores, with the §A1.7 model-level rule applied within each period at ×0.5/×1/×2. (ii) The
       P3-T3 ④a/④b/⑤ matched-point frontier comparison repeated within each period from the P3-T2
       test replay records. Frozen models, frozen `d̂` and frozen `policy_spec.yaml` throughout.
     - **Reported as:** whether the admitted set and the decision-level verdict are **stable** across
       periods. A flip is reported prominently (P3-T4 DoD), and it does not replace the headline
       verdict, which remains the unstratified P3-T1/P3-T3 result.

  2. **Second, higher-variance grid profile (addendum item 4).**
     - **Zone, fixed now by a predeclared ordered list:** (1) **California ISO (CAISO)**, with a
       pronounced solar midday trough, then (2) **Germany**, with a solar trough and a heavier fossil
       share. The first zone for which acceptance criteria (a)–(c) are met is used. (a) A free,
       licence-compatible, public hourly (or finer) carbon-intensity series exists for 2024-01-01 →
       2026-01-01, matching the UK span. (b) Coverage is ≥ 95% per year, as in P0-T3. (c) Its 168-slot
       profile's peak-to-trough ratio **exceeds the UK's 1.87×**. The choice depends on data
       availability and profile shape only, never on any replay result. **No zone outside this list may
       be substituted after P3-T1.** If neither qualifies, the sensitivity is reported as *not run —
       no qualifying data*, with the evidence.
     - **Construction:** identical to P0-T3. The profile is a UTC hour-of-week, nan-aware 168-slot mean,
       with gaps left NaN, and a `PROVENANCE.md` records source, licence, fetch time and coverage. It is
       indexed in **UTC** like the UK profile, so a build is charged at the grid's intensity at the
       build's own UTC instant.
     - **What is run:** the P3-T2 test replay re-run with the second profile in place of the UK one,
       under the **same frozen `policy_spec.yaml`** (not refitted for the new grid), the same trace and
       the same sweep grid.
     - **Reported as:** **ranking invariance** of the six strategies (carbon per 1,000 builds, TTFF
       p95) and of the ④/⑤ frontier ordering, plus the new profile's peak-to-trough ratio and
       perfect-shift ceiling. **It bears on RQ4 only.** It is never presented as evidence for or against
       SE decision value (RQ2), which §A1.13 routes through TTFF, not carbon. The frozen thresholds are
       extrapolated to this grid, and that is stated beside every number.

  3. **Forward-binding persistence duties** (so P3-T4 stratifies instead of re-scoring):
     - **P3-T1** persists its per-build test-split scores for every arm, with `tr_build_id` and
       `gh_build_started_at`, beside its model report.
     - **P3-T2** records `arrival_utc` on every replay record (already in the DL-023 schema) and
       keeps the full-grid test replay records needed for the per-period frontier comparison.

- **Rationale.** Fixing the boundary as a number and the zone by an ordered, availability-only rule
  leaves no degree of freedom that a test result could steer. Stratifying the one test evaluation
  rather than refitting keeps "fit before you look" intact. Restricting the grid sensitivity to ranking
  invariance and RQ4 stops it from being over-read.

- **Consequences.** New: `code/scripts/fix_temporal_boundary.py`,
  `results/p3/predeclared/temporal_boundary.json`. `development_plan.md` P3-T4 S1 is extended by these
  two sweeps, P3-T1 and P3-T2 carry the §3 persistence duties, and the P3-T4 "verdict stable / flips"
  summary table gains two rows. Threats (P5-T4): each period has about half the test builds, so its CIs
  are wider; per-period power is lower and a period-level null is weaker evidence than the pooled one.

### DL-028 — The P3-T1 F1 finding is reported, not acted on; `test_scores.csv.gz` is tracked; P3-T2's headline operating points and replay method, predeclared

- **Date:** 2026-09-26
- **Status:** Accepted. **Items 1 and 2 are author decisions** taken at the P3-T1 gate
  (2026-09-26). Items 3–5 are implementation-level, written **before the test trace was replayed**,
  per R4 and "fit before you look".
- **Spec section affected:** none in the frozen spec. `eval_protocol.md` §6/§9/§10 are **implemented,
  not amended** (§10's `paired_bootstrap` signature is frozen there). No RQ, floor, grid, strategy
  definition or frozen spec value changes.

- **Context.** P3-T1 (`results/p3/model_report.md` §10) found that F1 clears the §A1.7 model-level
  floor on test (ΔPR-AUC +0.013313 [+0.011924, +0.014733]) although it was rejected on calibration,
  and that the admitted set is not stable across the floor sweep. P3-T2 now replays the test trace, and
  three things are unfixed: what to do with that finding; which single setting represents each
  strategy in RQ4's headline table; and how a replay roughly 11× larger than P2's is run on this
  machine (11.7 GB RAM).

- **Decision.**
  1. **Option (a): report, do not act** *(author decision)*. The F1 test-split model-level result is
     reported as a finding, a non-replication between project-disjoint splits, in P3-T5 and the
     dissertation. **No post-hoc F1-informed arm** is added to the P3-T2/P3-T3 replay. The frozen
     `policy_spec.yaml` (sha256 `34d689c9…07da3`, duration-only) is the only ⑤ evaluated, so ⑤ ≡ ④b.
     The decision-level half of §A1.7 is therefore **not tested for F1**, and that is stated as a
     limitation rather than filled in. This does not rule out a later exploratory analysis, but that
     would need its own DL entry and must never be labelled confirmatory.
  2. **`results/p3/test_scores.csv.gz` is tracked in git** *(author-approved recommendation)*. Unlike
     the P2 replay traces (DL-024 §5), it cannot be regenerated without re-reading the test split,
     which is now gated (`evaluate_test.py --rerun-under DL-xxx`). It is the only record of the one
     test pass, P3-T4 depends on it (DL-027 §3), and it is 5.8 MB. Its sha256 is also recorded in
     `model_report.md`.
  3. **Headline operating points for RQ4** (the one row per strategy in P3-T2's headline table). All
     102 settings are still reported in `strategy_results.csv`; the headline only selects rows:
     - ① static and ② blanket (`d0`, `w167`): their single points.
     - ③ eligibility-only: `d0` at the frozen spec's `w_max_hours` (24 h). ③ is "Stage 1 + fixed
       window" and the frozen window is the policy's; this is ④ at `d = 0`, by construction.
     - ④a, ④b and ⑤: the frozen spec's point, `d_threshold_seconds` 480 and `w_max_hours` 24
       (DL-024 §Context 2).
     - ⑥ risk-only skip: **no single point**. No rule for choosing τ was ever predeclared, and fitting
       one now would use the test split. All seven τ points are reported, each beside its
       missed-failure count and failure recall (§6, DL-005), as a characteristic (DL-024 §5).
  4. **Replay method.**
     - The **full** test trace is replayed (no sampling; the P3-T2 DoD prefers it). `d̂` for each test
       build reads its own project's strictly-earlier builds (DL-014). `p̂` comes from the frozen
       `xgboost:full` arm. Both are cross-checked against P3-T1's persisted per-build scores.
     - Records are **aggregated and audited one setting (part file) at a time**. All 102 settings are
       never held in memory together. Every check the P2 runner applies to the whole frame (identical
       build sets, the independent validator, the skip audit, the DL-023 identities) is applied part
       by part, against the same reference.
     - **Rehearsal before test:** the same script runs on the frozen DL-023 §4 calibration sample
       (12,000 builds) and must reproduce `results/p2/policy_fit/summary.csv` exactly, and its trace
       sha256, before the test trace may be replayed. The test replay records a sentinel with its run
       fingerprint. A re-run with the **same** fingerprint is a byte-identical reproduction and is
       allowed; a different fingerprint needs a DL entry.
     - `decisions.csv.gz` for the test trace is retained (DL-027 §3) but **not tracked** (it is large).
       Its sha256 is pinned in `strategy_results.json`, as DL-024 §5 did for P2.
  5. **Paired bootstrap (§9, §10 signature).** `replay/stats.py::paired_bootstrap` is implemented to
     the frozen §10 signature: B = 1000, seed 42, 95% percentile CIs, resampling the shared build index,
     with every pairwise strategy difference. P3-T2 applies it to the headline settings for: carbon per
     1,000 builds, SCI per successful commit, latency mean (all builds), latency p95 (deferred builds),
     TTFF mean and p95 (failed builds), and share deferred. P3-T3 reuses it at matched points.

- **Rationale.** Choosing headline rows now, before any test replay exists, is the only way the
  RQ4 table cannot be steered by its own numbers. Refusing to invent a τ for ⑥ keeps "no threshold
  fitted on test" literal. The calibration rehearsal proves that the streaming aggregation equals the
  P2 whole-frame aggregation, so moving to streaming changes no number.

- **Consequences.** New: `code/scripts/run_test_replay.py`, `code/replay/stats.py`,
  `code/tests/test_stats.py`, `code/tests/test_run_test_replay.py`; outputs under `results/p3/`.
  Carried into P3-T5 and P5: F1's model-level non-replication, and the fact that its decision-level
  value is untested (item 1).

### DL-029 — How P3-T3's frontier test is computed: frontiers, matched points, area, floors, bands, oracle

- **Date:** 2026-09-26
- **Status:** Accepted (implementation-level). Written **before any frontier, matched-point or area
  number was computed**, per R4. The author's instruction at the P3-T2 gate, "do not add anything
  post-hoc", is binding: everything below is the machinery of analyses that `development_plan.md`
  P3-T3 S1–S5 and `eval_protocol.md` §A1.5/§A1.7/§A1.9/§A1.10 already require. No new comparison,
  arm, population or metric is introduced.
- **Spec section affected:** `eval_protocol.md` §A1.5 (frontier dominance at matched points) and
  §A1.7 (decision-level floors) are given the operational detail they lack; §A1.9/§A1.10 are applied as
  written. No floor value, grid, strategy, RQ or frozen spec value changes.

- **Context.** §A1.5 says: build swept frontiers in the (carbon saved, TTFF p95) plane, match
  operating points by interpolation onto a common grid, paired-bootstrap each matched point, and report
  the area between frontiers. §A1.7 sets the floors (≥ 5% relative TTFF p95 reduction at matched
  carbon, or ≥ 1% relative carbon-saved increase at matched TTFF, at ≥ 3 matched points, CI excluding
  0) with a ×0.5/×2 sweep. None of these fixes what a frontier is, which grid, or how "≥ 3 points" is
  counted. Leaving them open until the curves exist would let the curves choose them.

- **Decision.**
  1. **Inputs.** The P3-T2 test replay part files (run fingerprint `d9e30163…`, each part's sha256
     re-verified against its `.done` record), for ① and the 30 `(d_threshold, w_max)` points of each
     of ④a, ④b and ⑤. Nothing is re-replayed except the §A1.10 oracle arm (item 7). Before any
     frontier is formed, every recomputed per-setting point must equal P3-T2's `strategy_results.csv`:
     carbon per 1,000 builds and TTFF p95 to 1e-12 relative, and carbon saved to 1e-9 percentage
     points absolute. *(Amended 2026-09-26, before any frontier number existed. The first run stopped
     on an all-relative 1e-12 check of carbon saved. Near-zero savings amplify floating-point
     summation-order noise of about 1e-15 relative into about 4e-10 relative, so the check is now
     stated on the underlying quantities. The CSV is read with `float_precision="round_trip"`.)*
  2. **Coordinates.** `saving = −(carbon per 1,000 builds vs ①) in %`, and `TTFF p95` = the 95th
     percentile (numpy linear) of TTFF over failed, accountable builds, exactly as `simulator.summarise`
     computes them. Both are recomputed from per-build values, so the bootstrap can resample them.
  3. **Frontier.** For each strategy, the Pareto-efficient subset of its 30 points: a point is kept
     unless another point has saving ≥ and TTFF p95 ≤ with at least one strict. Among exact duplicates
     one is kept. Sorted by saving, this gives TTFF p95 non-decreasing. The frontier is
     **piecewise-linear** between its points, with no extrapolation outside its own range.
  4. **Matched points.** Two grids, each over the **overlap** of the two frontiers' ranges on that
     axis: **K = 10 interior points**, `linspace(lo, hi, 12)[1:-1]`. Endpoints are excluded, so a
     relative difference is never taken against a zero saving. At matched carbon the comparison is
     `ΔTTFF = TTFF_④(s) − TTFF_⑤(s)` (positive favours ⑤), relative to `TTFF_④(s)`. At matched TTFF it
     is `ΔS = S_⑤(t) − S_④(t)` (positive favours ⑤), relative to `S_④(t)`. If the overlap is empty or
     degenerate on an axis, that axis has no matched points and this is reported.
  5. **Floors and the ≥ 3 rule.** A matched point **counts** for ⑤ iff its relative improvement meets
     the floor (5% TTFF, or 1% carbon) **and** the 95% paired-bootstrap CI of its absolute difference
     lies entirely above 0. The decision-level condition holds iff **≥ 3 points count on at least one
     axis**. It is re-evaluated at ×0.5 and ×2 of **both** floors. §A1.9: ⑤ must meet it against
     **both** ④a and ④b to be reported as adding value.
  6. **Area between frontiers (headline scalar).** `∫ (TTFF_④(s) − TTFF_⑤(s)) ds` over the carbon
     overlap, by trapezoid on 201 evenly spaced points. Its units are percentage points × hours, and
     positive favours ⑤. It is reported with its 95% CI.
  7. **§A1.10 oracle arm** (planned in P3-T3 S4; labelled *"oracle — unrealizable in deployment"*
     wherever it appears; never in the headline table; never wired into `decide()` outside this
     analysis). ④'s duration-only rule is replayed on the test trace with `d̂` replaced by the build's
     observed duration, at the same 30 grid points. The 55 unaccountable builds, which have no observed
     duration, keep their ④b estimate; they are excluded from carbon and TTFF anyway (DL-023 §3). The
     trace is read from the tracked `results/p3/test_trace.csv.gz`. It is proved faithful first:
     re-replaying one ordinary ④b setting from it must reproduce its P3-T2 part byte for byte. The
     oracle frontier is compared with ④b and ⑤ by the same machinery, as a bound on how much of any
     frontier gap estimator error could explain.
  8. **Bootstrap.** §9's paired bootstrap: B = 1000, seed 42, percentile 95% CI. Each resample draws
     the shared test-build index once, recomputes every setting's saving (against the same resample's
     ①) and TTFF p95, rebuilds every frontier, and re-evaluates every matched point and the area. The
     CIs therefore carry frontier-shape uncertainty as well as metric noise. The **matched grids are
     fixed** from the full-trace frontiers and held across resamples. A resample whose frontier does not
     reach a grid point leaves that point *undefined* in that resample (no extrapolation). A point's CI
     uses its defined resamples, the undefined count is reported, and a point undefined in more than 5%
     of resamples **cannot count** under item 5. The **area** in each resample is taken over that
     resample's own carbon overlap, which is §A1.5's "overlapping carbon range", re-evaluated.
  9. **Failure-rate bands (§A1.9, P3-T3 S4).** Each test project's failure rate is computed on its own
     test builds, a descriptive stratification that fits nothing. Projects are split at the terciles
     of that rate across the 170 test projects into low, mid and high bands. Items 3–8 are rerun within
     each band, with ① recomputed within the band. The between/within-project variance decomposition
     applies to **admitted families** (§A1.9); none is admitted in the frozen spec, so it is reported
     as not applicable, and why.
  10. **What the verdict can and cannot say.** Under the frozen spec ⑤ ≡ ④b (DL-023 §1, DL-028 §1), so
      ⑤ − ④b is exactly 0 at every matched point by construction, and the condition cannot hold against
      ④b. The ⑤-vs-④a comparison is between two **duration** controls and says nothing about SE
      characteristics. The written verdict states this, and states that F1's decision-level value was
      **not tested** (DL-028 §1).

- **Rationale.** Every free choice (Pareto rule, K, interior grid, "counts", area range, bands) is
  fixed before the curves exist. Choices are the simplest defensible ones and are stated so that a
  reader can recompute them.

- **Consequences.** New: `code/replay/frontier.py`, `code/scripts/frontier_analysis.py`,
  `code/tests/test_frontier.py`; outputs `results/p3/incremental_value_decision.{md,json}` plus
  figures. The oracle replay's parts live under `code/artifacts/replay_parts/` (gitignored).

### DL-030 — How P3-T4's sensitivity sweeps are run, and what "the verdict flips" means

- **Date:** 2026-09-28
- **Status:** Accepted (implementation-level). Written **before any P3-T4 sweep was run**, per R4.
  "No post-hoc additions" (the author's instruction at the P3-T2 gate) binds here too. Every sweep below
  is one that `development_plan.md` P3-T4 S1–S3, `eval_protocol.md` §7/§8/§A1.7, DL-010, DL-020 §5,
  DL-024 §3 or DL-027 already requires. This entry only makes each sweep operational.
- **Spec section affected:** none. No frozen value, grid, floor or strategy changes. The frozen
  `policy_spec.yaml` stays the policy of record; every sweep is a labelled what-if around it.

- **Context.** P3-T4's DoD needs, per sweep, whether it "changes the RQ2/RQ4 verdict". The RQ2
  verdicts are defined (§A1.7, DL-029). RQ4's is not: RQ4 is written up in P3-T5, and no document says
  which RQ4 pattern must hold for a sweep to count as "stable". A definition chosen after the sweeps
  had run could be fitted to them.

- **Decision.**
  1. **The verdicts tracked, fixed now.**
     - **V1 — RQ2 model level:** the admitted set under §A1.7 at ×1, applied to the paired test-split
       ΔPR-AUC of each family, as in P3-T1. It is evaluated only where a sweep changes the builds or the
       label (temporal, cold-start).
     - **V2 — RQ2 decision level:** "⑤ beats both ④a and ④b" at ×1 (DL-029 §5).
     - **V3 — the secondary duration-control finding:** the §A1.7 condition for ④b over ④a at ×1
       (P3-T3 §6b). This is tracked so that its robustness is reported, not assumed.
     - **V4 — RQ4 sign pattern:** for ⑤ at its headline point against each of ①, ②, ③ and ④a (same
       `W` as ⑤), the paired-bootstrap difference (B = 1000, seed 42) on carbon per 1,000 builds and on
       TTFF p95. Each difference is classed *significantly lower*, *significantly higher* or *n.s.*
       (CI spans 0). **V4 is stable iff all eight classes equal P3-T2's.** The magnitudes are reported
       beside the classes.
     - A sweep **flips** a verdict iff that verdict differs from its P3-T1/P3-T2/P3-T3 baseline. Every
       flip is reported in the summary table and at the top of `results/p3/sensitivity.md`.
  2. **The sweeps.** All use the test trace, the frozen models, the frozen `d̂` and the frozen spec.
     Nothing is refitted. Where a re-replay is needed, it runs through the unchanged simulator. Parts
     go under `code/artifacts/replay_parts/` (gitignored), and each re-replay is audited by the
     independent validator.
     - **S-a Deferrable fraction** (DL-020 §5). The full 102-setting replay is re-run under the stage-1
       variant `protected_includes_integration`, with the spec otherwise frozen; the validator runs
       under the same variant. V2–V4 are reported.
     - **S-b `W_max ∈ {6, 12, 24}`** (§7, §A1.8). This uses the P3-T2 records only: ⑤, ④a and ③ at
       each `W` with `d_threshold` 480 (③ at 0). V4 is reported at each `W`. The **banded window
       shape** (§7) is **not applicable**: it maps a failure probability to a window, which exists only
       on the risk-adjusted path, and the frozen spec admits no family. This is stated, not simulated.
     - **S-c Energy `P_avg × {0.5, 1.5}`** (DL-007). Carbon is recomputed per build as carbon × m. This
       is exact, because carbon is linear in `P_avg`. V2–V4 are recomputed. Percentage savings and
       TTFF are invariant by construction, and that is stated as the result.
     - **S-d `n_jobs`-scaled energy** (DL-010). Per build, `n_jobs` is the count of that build's job
       rows in the release (DL-010), read from the test split's rows. Carbon becomes carbon × `n_jobs`,
       which is exact for the same reason; TTFF and decisions are unchanged. V2–V4 are recomputed.
     - **S-e Temporal robustness** (DL-027 §1). The boundary is `2015-03-28T13:00:51+00:00`, read from
       `results/p3/predeclared/temporal_boundary.json`. Early and late test builds are taken by
       `gh_build_started_at`. V1 per period comes from `results/p3/test_scores.csv.gz` (paired
       bootstrap per family, §A1.7 floor sweep). V2 and V3 per period use DL-029's machinery on a
       period mask.
     - **S-f Second grid profile** (DL-027 §2). The first zone of {CAISO, Germany} that meets DL-027 §2
       (a)–(c) is used, from the Electricity Maps hourly datasets (ODbL, attribution recorded in
       `PROVENANCE.md`). The column used is the **direct** (operational) carbon intensity; the life-cycle
       column is not used. The profile is built exactly as P0-T3's: UTC hour-of-week, nan-aware
       168-slot mean, gaps left NaN. The full 102-setting replay is re-run with that profile. V2–V4 are
       reported, framed as **ranking invariance for RQ4 only** (DL-027 §2). If no zone qualifies, the
       sweep is reported as *not run — no qualifying data*, with the evidence.
     - **S-g Cold-start builds excluded** (P3-T4 S2). Builds whose ④b `d̂` fell to the language or
       global rung (`d_hat_4b_fallback != "project"`) are masked out. V1, V2 and V3 are reported on the
       remaining builds.
     - **S-h ④b trailing-50 form** (DL-024 §3; P1-T4's declared sensitivity). ④b is re-replayed at the
       30 grid points with `d̂` from the trailing 50-build causal window (strictly earlier builds, same
       fallback ladder, fitted parameters unchanged). Its frontier is compared with the frozen ④b and
       with ④a by DL-029's machinery. It is labelled a **sensitivity of the control, not the policy of
       record**.
     - **S-i Floor sweep and ④b-as-null** (P3-T4 S2). Already computed in P3-T1 and P3-T3; collected
       into the summary table, not recomputed.
  3. **Herding (P3-T4 S3).** Per headline setting, the report gives the top-5 slot share, the largest
     single-slot share and their ratio to ①'s. This is descriptive only. No threshold for calling
     concentration a threat was predeclared, and none is introduced now. §6 already makes herding a
     reported threat. The effect a real deployment would have on marginal intensity is stated as a
     limitation.
  4. **Reading the test trace.** Every read of `results/p3/test_trace.csv.gz` uses
     `float_precision="round_trip"` (P3-T3 finding). Every re-replay first re-proves the trace by
     reproducing one P3-T2 part byte for byte.

- **Rationale.** Fixing V4 as a sign pattern with a CI rule, before any sweep exists, is the smallest
  definition that lets "stable / flips" be decided mechanically. Recomputing energy variants exactly,
  instead of re-replaying, avoids a spurious source of difference, because decisions do not depend on
  energy.

- **Consequences.** New: `code/scripts/sensitivity_analysis.py` (+ tests), `results/p3/sensitivity/`
  (one JSON per sweep), `results/p3/sensitivity.md` (the summary, with the verdict table first),
  figures. S-f waits on the author downloading the Electricity Maps CSVs, which needs a free account.

### DL-031 — S-f's CAISO series comes from EIA-930, not Electricity Maps (source change, before any S-f result)

- **Date:** 2026-09-28
- **Status:** Accepted. **Author decision** 2026-09-28: no account with any data provider, and no paid
  tools. Written **before** the second-grid profile was built, before its peak-to-trough ratio was
  computed, and before any replay on it existed. Only the file's header row and its non-empty count for
  2024–2025 had been read, to confirm the source is usable.
- **Spec section affected:** amends DL-030 §2 S-f (the data source and column) only. DL-027 §2's zone
  order (CAISO, then Germany), its criteria (a)–(c), the UTC hour-of-week construction, the
  ranking-invariance framing and the RQ4-only scope are unchanged.

- **Context.** DL-030 named Electricity Maps' hourly CSVs, which need a (free) account. The author
  declined creating one. The U.S. Energy Information Administration's EIA-930 per-balancing-authority
  workbook for California ISO downloads with no account or key. It carries hourly CO₂ intensity columns
  derived by EIA from the fuel mix, with UTC timestamps, from 2015-07-01 onward.

- **Decision.**
  1. **Source.** `https://www.eia.gov/electricity/gridmonitor/knownissues/xls/CISO.xlsx`, fetched
     2026-09-28 14:19 UTC, 97,058,485 bytes, sha256 `ada85f3a…7e3834`. It is stored read-only in
     `Dataset/eia930/CISO.xlsx`. EIA's notes sheet states the data are preliminary and provided "as-is";
     that is carried as a limitation. Citation: U.S. EIA, *Hourly Electric Grid Monitor* (Form EIA-930).
  2. **Column.** Sheet "Published Hourly Data", **"CO2 Emissions Intensity for Consumed
     Electricity"**. This is the consumption-based figure (it includes EIA's estimate of the emissions
     of imported electricity), the nearest analogue of the consumption-based operational intensity that
     DL-030 intended. The generated-electricity column is **not** used.
  3. **Units.** EIA reports lb CO₂ per kWh, confirmed on the file (daily 95,918.74 t / 523,084 MWh =
     0.18337 t/MWh = 0.40426 lb/kWh, matching its stated 0.40426). The conversion is × 453.59237 g/lb,
     giving g CO₂/kWh.
  4. **Timestamps.** EIA's "UTC time" (an Excel 1900-system serial) marks the **end** of each hour.
     "Hour 1" local is 00:00–01:00, stamped 08:00 UTC in summer. Each value is shifted −1 h to
     hour-*start*, matching P0-T3's UK series, and then placed on the same 2024-01-01 → 2026-01-01 UTC
     hourly grid. Gaps stay NaN.
  5. **Reading.** Standard library only (the `.xlsx` is a zip of XML); no new dependency enters the
     pinned stack.
  6. **Germany fallback.** Used only if CAISO fails DL-027 §2 (b) or (c). It would need its own source
     under a further DL entry; it is not pre-chosen here.

- **Rationale.** A public, account-free, government series keeps S-f inside the "free, public"
  criterion. Choosing the column, units and time convention now, before seeing the profile or any
  replay on it, keeps the sweep predeclared.

- **Consequences.** `scripts/sensitivity_analysis.py` gains an EIA-930 reader used by S-f for CAISO,
  with tests. The derived profile and a `PROVENANCE.md` are written under
  `code/data/carbon/second_grid/`.

### DL-032 — S-f (second grid) is reported as not run: no qualifying zone under DL-027 §2

- **Date:** 2026-09-28
- **Status:** Accepted. **Author decision** 2026-09-28 (option "report not run", chosen from three
  presented: not run / free Electricity Maps account for Germany / derive Germany from the fuel mix).
  No S-f replay was run, so no S-f result exists to have influenced the choice.
- **Spec section affected:** closes DL-027 §2 and DL-030/DL-031 S-f by the rule DL-027 §2 already
  stated: "If neither qualifies, the sensitivity is reported as *not run — no qualifying data*, with the
  evidence."

- **Evidence.**
  1. **CAISO failed criterion (c).** On the DL-031 series (EIA-930, consumed-electricity intensity), the
     168-slot profile's peak-to-trough ratio is **1.8669**, against the UK's **1.8746**, so it is not
     higher. Criteria (a) and (b) passed (coverage 98.91% in 2024 and 98.90% in 2025). Recorded in
     `results/p3/sensitivity/f.json`.
  2. **Germany failed criterion (a) under the author's no-account constraint.** Electricity Maps
     requires an account. The Energy-Charts API (CC BY 4.0, no key) publishes generation and price
     series but no carbon-intensity series; its endpoint list is saved in
     `results/p3/sensitivity/energy_charts_endpoints.txt`. Deriving an intensity from the fuel mix would
     add new modelling choices and was declined.

- **What is reported instead.** The CAISO profile statistics are reported as a descriptive by-product,
  never as an S-f result. On an hour-of-week *mean* basis, a solar-heavy US grid measured with a
  consumption-based intensity is **not** more variable than the UK 2024–25 grid. That weakens, but does
  not answer, the review's concern that the UK grid might be too flat to separate policies. The ranking-
  invariance question remains **untested**, and that is stated as a limitation in P3-T5 and P5.

- **Consequences.** S-f appears in the P3-T4 table as *not run — no qualifying data*, with this entry
  cited. No new data source, dependency or modelling choice enters the study.

### DL-033 — The DL-026 follow-up: P4 becomes a duration-history carbon-deferral *advisor* that embodies the P3 null (amends DL-026; proposed amendment to spec §5 and P4-T1..T3)

- **Date:** 2026-10-01
- **Status:** **Proposed — awaiting author decision** (draft revision 2, 2026-10-01: completed-history
  contract per DL-034; §B9 operational/security contract added). Drafted at the author's request after
  the P3-T5 gate (`4d9e128`). **Not accepted and not acted on.** Its §A facts are re-checked against
  the DL-034 corrected results before acceptance: if the corrected chain admits an SE family, §B is
  re-drafted. No code, plan, spec or Layer 0-A text changes until
  the author accepts it, amends it, or chooses the alternatives in §D. This is the entry DL-026 made
  forward-binding: "accept, amend or withdraw this direction, citing the P3 verdicts it rests on."
- **Spec section affected (on acceptance).** Frozen spec §5 (artifact definition) is **amended through
  Layer 0-A**, never edited below the frozen line. `development_plan.md` P4-T1..T3 are re-scoped, keeping
  three tasks so `tasks_total` stays 28. DL-026 is **amended** (§C lists exactly what changes). Untouched:
  §1–§4, the active RQs, `eval_protocol.md`, the feature contract, the split, the frozen
  `policy_spec.yaml` and every P3 result.

#### A. The P3 verdicts this rests on (`results/p3/evaluation_report.md`)

1. **No SE feature is a decision input.** RQ2 is null and stable. The frozen spec's path is
   `duration_only_fallback`, so ⑤ ≡ ④b (§2, §9). F1 is a non-replicating model-level candidate and was
   never tested at the decision level (DL-028 §1).
2. **What the frozen decision actually consumes** (§7; `code/scheduler_core/policy.py::decide`):
   `gh_is_pr` and `git_branch` (Stage 1), `arrival_dow` / `arrival_hour`, and `d_hat_seconds`, plus a
   168-slot hour-of-week carbon profile. `p_hat` is read only on an SE path the spec does not contain.
3. **`d̂` (④b) is a per-project median of the durations of builds that had *finished* before the
   scored build arrived** (DL-014 as corrected by **DL-034**; `duration_estimator.causal_project_history`).
   Live, this needs the project's own completed-run durations, which the 28 commit features do not
   carry. *(Draft revision 2, 2026-10-01: the first draft said "strictly-earlier", which repeated the
   start-time defect that DL-034 corrects.)*
4. **The evaluated regime is narrow.** It covers a UK national hour-of-week mean profile, Travis CI
   builds from 2011–2016, and thresholds of d ≥ 480 s and W = 24 h (§5, limitations 1, 2, 11). Anything
   else is extrapolation.
5. **Duration estimation is the lever** (§4.2). Oracle headroom is +1.9290 pp·h; trailing-50 adds
   +0.3538 over the frozen ④b.

#### B. Proposed decision

1. **What the artifact is.** A **carbon-deferral advisor for CI** that runs the identical
   `scheduler_core.decide()` under the frozen `policy_spec.yaml`, using `require_fitted=True` (invariant
   5; DL-024). It answers one question for one build: *run now, or defer to the greenest slot within
   24 h, and why.* It visibly embodies the null: the reason string names the policy path and states that
   SE features were evaluated and not admitted, citing `results/p1/incremental_value.md` and
   `results/p3/evaluation_report.md`.
2. **Input contract: narrowed to what `decide()` consumes.** This replaces P4-T1 S2's "28 commit
   features only".
   - Request: `is_pr`, `branch`, `arrival_utc` (→ dow/hour), plus *either* the project's
     completed-build history *or* a repository identifier that the adapter resolves to that history.
     A history entry is admissible only if it carries `started_at`, `duration_s` **and** a completion
     time `finished_at < arrival_utc` (DL-034). In-progress, queued, cancelled or unknown-status runs
     never enter. Where a live source lacks `finished_at`, `started_at + duration_s < arrival_utc` is
     the floor, as in evaluation.
   - `d̂` is computed **server-side** by the frozen estimator's ④b path, including its cold-start
     ladder, so serving matches evaluation. The response reports `d̂`, `n_history` and the rung used.
   - The schema is **closed**. It rejects any current-build outcome or duration field (A1.2, as P4-T1
     already requires) and any SE-feature field. No SE feature is accepted, logged or displayed.
3. **Carbon: the evaluated profile is the decision of record.** The decision uses the frozen UK
   168-slot profile, exactly as in evaluation, so parity is exact. The live intensity from
   carbonintensity.org.uk (with a cached fallback, as P4-T1 S2 already specifies) is **displayed beside
   it** as `grid_gCO2_now`. It is labelled live and **does not change the decision**.
   - A forecast-driven mode is admitted only as an **opt-in, labelled "extrapolated — not evaluated"**.
     It fills the same 168-slot frame from the forecast, so `decide()` is not forked, and its output is
     never presented as an evaluated result.
   - The availability and terms of any forecast endpoint are verified in P4-T1 before use, not assumed
     here.
4. **Region: GB only.** DL-026's region-confidence hierarchy and IP geolocation are **withdrawn**. Only
   GB was evaluated, and `research_state.json` already lists "IP geolocation identifies the data centre"
   as not tested. Any other configured region returns `run_now`, with a reason stating that the region
   is outside the evaluated regime. Multi-region support is future work.
5. **Urgency stays deterministic and team-owned.** Stage 1 runs exactly as evaluated: the primary
   variant, `gh_is_pr` + `git_branch` (DL-020). Live trigger context, such as `schedule` and
   `workflow_dispatch` events, may be **displayed** but may not alter the decision (DL-026, condition
   3). The DL-020 gap is stated in the documentation: manual and scheduled classes are unapproximated.
6. **One core, three thin adapters.** No adapter contains decision logic. A test asserts each one
   imports `decide()` from `scheduler_core` and loads the spec whose sha256 is `34d689c9…07da3`.
   - **CLI** (`python -m scheduler_core.advise …`): the in-process path. It needs no server, so it is
     the most viable path for a CI user.
   - **REST API** (FastAPI `POST /decision`): spec §5's Must, retained and parity-tested.
   - **GitHub Action**: calls the CLI in-process, and the API is optional. It writes the decision, the
     reason, `d̂`, the history coverage, the window and the estimated carbon change to the **Step
     Summary**, and exposes `action` / `defer_until` as **step outputs**.
7. **Execution boundary.** The Action **recommends**. It does not pause or cancel anything (DL-026
   §4). An **opt-in reference workflow** shows how a team can gate a non-urgent job on the
   `action` output and re-dispatch it at `defer_until` through a scheduled
   `workflow_dispatch`. It is documented plainly as *deferred re-dispatch, not pausing* (spec §5
   note). The demo repo shows one real cycle of it. The core contribution still ends at the
   recommendation.
8. **Dashboard: an audit view, not an explanation surface** (Could, first to cut, §3.7). It shows the
   decision log, the reason and policy path, history coverage and cold-start rung, the imposed delay,
   *estimated* carbon change against run-now, and an independent-validator pass over the log
   (`replay/validate_invariants.py`: zero non-deferrable builds deferred). It has **no SHAP panel**,
   because the model it would explain was rejected as a decision input.

9. **Operational and security contract** *(draft revision 2, from the revised independent review
   §16/§21.6)*. This binds P4-T1/T2 and is tested where testable:
   - **Fail closed to `run_now`.** Any missing or invalid input returns `run_now` with a reason that
     names the failure, never `defer`. This covers no history, no completed history, a carbon source
     that is down and lacks its cached profile, a spec hash mismatch, a non-GB region, and a schema
     violation.
   - **Least-privilege GitHub permissions.** The advisory job needs `contents: read` and
     `actions: read` (for run history) only. The opt-in re-dispatch workflow additionally needs
     `actions: write`, declared in that workflow alone. No `pull_request_target`. Fork PRs are always
     `run_now` (Stage 1 already sends PR builds there) and are never given a token with write scope.
   - **No injection.** Branch names and other event fields are passed as environment variables or
     JSON, never interpolated into shell `run:` lines. The repository identifier is validated against
     `owner/name`.
   - **API.** It binds to localhost by default and has no CORS. It caps request size and history
     length, uses a token header when exposed beyond localhost, and has no outbound requests except
     to the configured carbon endpoint (no user-supplied URLs).
   - **History source.** Paginated and rate-limit aware. Only `status: completed` runs are used,
     with an explicit cap on history length. The cold-start rung used is always reported.
   - **Re-dispatch is idempotent.** It is keyed by the original run's head SHA plus the workflow,
     re-dispatches the same SHA, refuses if a run for that SHA has already succeeded, and does at most
     one re-dispatch per decision.
   - **Audit.** Every decision is logged with the spec sha256, inputs (no secrets), `d̂`, `n_history`,
     rung, window and reason. The validator runs over the log.
   - Anything here that cannot be tested in a demo repo is stated as untested, not implied.

#### C. Exactly what changes in DL-026

| DL-026 item | DL-033 |
| :-- | :-- |
| Flow: "SE features *only if P3 admits them*" | P3 did not admit them, so they are removed from the flow and the contract (§B2) |
| Region inference: configured → cloud region → IP geolocation | **Withdrawn.** GB only, configured; other regions run now with a stated reason (§B4) |
| Current + forecast regional intensity drives the decision | Evaluated profile drives the decision; live shown alongside; forecast mode opt-in and labelled (§B3) |
| No automatic rescheduling | **Kept** as the core boundary, plus an opt-in, documented re-dispatch reference workflow (§B7) |
| Open question: keep a thin API for spec §5's Must? | **Yes**, parity-tested; the CLI is the primary in-process path (§B6) |
| Open question: step outputs? | **Yes**: `action`, `defer_until`, `reason`, `d_hat_seconds`, `n_history` (§B6) |
| Conditions 1–5 | **All retained** |

#### D. Author decision points (each has a recommendation; the alternative is recorded)

1. **Decision of record, carbon.** *Recommended:* evaluated UK profile, with live/forecast displayed.
   *Alternative:* forecast drives the decision, labelled extrapolated everywhere. That is more useful
   live but makes parity approximate.
2. **Execution.** *Recommended:* recommend, plus an opt-in re-dispatch reference workflow, keeping
   P4-T2's "≥ 1 real deferral → re-dispatch cycle". *Alternative:* recommendation only, with that DoD
   line replaced by "≥ 1 real DEFER recommendation captured".
3. **Region.** *Recommended:* GB only. *Alternative:* keep a configured-region field for other zones,
   always labelled extrapolated.
4. **Duration-history source for the demo.** *Recommended:* the repository's own completed
   GitHub Actions run history, read through the GitHub API, with the endpoint verified in P4-T1, and a
   local JSON history file as the offline and test fixture. *Alternative:* a history file only.
   Either way, GitHub Actions run duration is a **different construct** from Travis `tr_duration`. The
   480 s threshold is applied there as an extrapolation and declared as such.

#### E. Re-scoped P4 tasks (applied to `development_plan.md` only on acceptance)

- **P4-T1 — Decision service: core advisor + CLI + REST API (Must).** The closed request schema of
  §B2; server-side ④b `d̂` with cold-start provenance; live intensity displayed and never decisive.
  **DoD:**
  - **Parity:** a three-way test shows the same build record gives the identical `Decision` from
    `decide()`, the CLI and the API.
  - The spec sha256 is asserted.
  - The schema rejects duration, outcome and SE fields.
  - Error paths are covered: carbon API down → cached profile; no history → cold-start rung reported;
    non-GB → `run_now` with reason.
  - The reason string names the policy path and the null.
- **P4-T2 — GitHub Action + demo repo (Should).** In-process CLI, Step Summary, step outputs, and the
  opt-in re-dispatch reference workflow. **DoD:** captured demo-repo runs show ≥ 1 `run_now` (protected
  branch), ≥ 1 `defer` (eligible branch, d̂ ≥ 480 s) and, under §D2's recommendation, one re-dispatch
  cycle. The documentation states the evaluated regime and the extrapolations (§A4, §D4).
- **P4-T3 — Audit dashboard (Could; first to cut).** §B8. **DoD:** it renders the real decision log
  from P4-T2. Every carbon figure is labelled "estimated". The validator result is shown. There is no
  SHAP.

#### F. Rationale

The artifact must not contradict the thesis it accompanies. A 28-feature SE contract and a SHAP
rationale panel would do exactly that on the null path (`INDEPENDENT_REVIEW_REPORT.md` addendum
item 7, advisory input). Narrowing the contract to what `decide()` consumes **reduces** P4 work and makes
the null executable and auditable. One live decision then traces back to the frozen spec, and from
there to the result files that fixed it. Decisions outside the evaluated regime are labelled, never
silently trusted. Keeping three tasks and the same identifiers leaves progress accounting unchanged.

#### G. Consequences (on acceptance)

- A Layer 0-A note records that spec §5 is amended by DL-033. `development_plan.md` P4-T1..T3 are
  rewritten per §E.
- `context/` gains a short P4 interface reference: request/response schema, history format and
  cold-start provenance.
- `research_state.json` `artifact_components` are updated and the guide rebuilt (DL-025).
- If the author rejects this entry, DL-026 stays Proposed/Conditional and P4-T1 remains blocked until
  another follow-up entry is accepted.

### DL-034 — ④b's history admits only builds that had *finished* before the scored build arrived; the full evidence chain is re-run under this entry (corrects DL-014 §Resolution 2)

- **Date:** 2026-10-01
- **Status:** **Accepted.** Author decision of 2026-10-01: approve the correction and re-run scope
  option (a), the full chain, chosen from (a) full chain / (b) decision chain only / (c) report-only.
  §B fixes every rule for the rerun **before any corrected number exists**. This entry, the code fix
  and its tests are committed before the first rerun command is executed.
- **Spec section affected.**
  - DL-014 §Resolution 2 is **amended**: "strictly earlier builds" now means *builds that finished
    strictly before t_b*.
  - `context/duration_control_spec.md` §3.1/§3.3 are updated to match, with a pointer to this entry.
  - `eval_protocol.md` A1.1 (the admissible information set) is **implemented more strictly, not
    amended**: a duration not yet observed at t_b was never admissible under A1.1's own wording.
  - Unchanged: every RQ, feature, family, split, floor, grid, strategy definition, seed, search
    budget, the ρ = 0.90 rule, the headline-operating-point rules (DL-028 §3), the temporal boundary
    (DL-027 §1, computed from start times only) and the S-f outcome (DL-032).

#### A. The defect, as measured

- **Source.** `INDEPENDENT_REVIEW_REPORT.md` (revised 2026-10-01; advisory input) §4/§6. It is
  verified in the code: `causal_project_history()` orders history by `gh_build_started_at` only, and
  no completion condition exists anywhere in `code/`. The code matched DL-014 exactly, so **the defect
  is in the information rule, not in its implementation.** A deployed scheduler knows only the
  durations of builds that have *finished*.
- **Prevalence and effect on the test split.** Measured by `PYTHONPATH=. python
  scripts/diagnose_history_overlap.py` → `results/corrections/dl034/history_overlap.{json,md}`.
  - The script first reproduces the trace's recorded ④b exactly: max |Δ| 0.0 s, with `n_history`
    equal on all 138,693 builds.
  - 38,019 of 138,693 test builds (27.41%) have at least one unfinished build in their ④b history. In
    37,000 (26.68%) the immediate predecessor was still running. The review's lower bound was 36,849.
  - Typically one unfinished build is involved (median 1, p95 4, max 15).
  - d̂ changes by a median of 0.00% (|·| p95 0.84%).
  - At the frozen 480 s threshold, 5 of 27,027 Stage-1-eligible builds would cross it, and 7 would
    move to the cold-start rung.
  - Train and calibration are not measured there. The classifier arms also carry `d̂` as a feature
    (`models.py`), so P1 is affected in the same way.
- **Reading.** The effect on decisions is expected to be small, but the claim "strictly causal,
  deployable history" is false as implemented. The P4 artifact would compute `d̂` from completed runs
  only, so leaving the defect in place would also break evaluation/serving parity (invariant 5).
  Option (a) was chosen to correct the evidence rather than argue the bound.

#### B. Decision

1. **The rule.** A build *j* of project *P* enters the ④b history of build *b* of *P* **iff** *j*
   carries a usable label (spec §1.2) **and** `gh_build_started_at_j + tr_duration_j < gh_build_started_at_b`
   (strict).
   - **Completion proxy.** The release has no finish timestamp (`context/dataset_reference.md`), so
     start + `tr_duration` (build wall-clock, max-aggregated over jobs, DL-009/DL-010) stands in for
     completion. It is the *earliest possible* finish: queueing, or jobs starting after the build's
     start, would make the true finish later. The corrected rule may therefore still admit a build
     slightly early. That residual is declared and not measurable here.
   - **Consequences of the rule.** Tied starts are excluded automatically (end > start). Unlabelled
     builds never enter, as before. The trailing-50 sensitivity becomes *the 50 most recently
     finished labelled builds*. `n_history` counts the admitted builds.
2. **Implementation.**
   - `causal_project_history(..., availability="completed")` becomes the default and the only rule a
     real run may use.
   - The superseded rule survives as `availability="started"`, solely so tests and the diagnostic can
     reproduce the pre-DL-034 behaviour.
   - `assert_history_is_causal()` **requires the durations** and rejects any history that counts a
     build not finished by t_b (new check 3), in addition to its two existing checks.
   - Every caller passes durations: `models.py`, `fit_duration_estimator.py`, `run_replay.py`,
     `evaluate_test.py` and `sensitivity_analysis.py`.
   - New tests cover overlapping runs, an exact finish-at-arrival boundary, a brute-force O(n²)
     recomputation on overlapping data, the trailing window in completion order, and rejection of the
     start-ordered rule.
3. **Re-run scope: the full chain, in order, with the same scripts, seeds, budgets and grids.**
   - P1-T4 `fit_duration_estimator.py`
   - P1-T5 `train_models.py`
   - P1-T6 `run_ablation.py`
   - P1-T7 `apply_admission.py`
   - P2-T4 sample run (`run_replay.py`, bootstrap-labelled as before)
   - P2-T5 `fit_policy.py`
   - P3-T1 `evaluate_test.py`: calibration rehearsal, then `--split test --open-test-split
     --rerun-under DL-034`
   - P3-T2 `run_test_replay.py`: `--mode rehearse`, then `--mode test --rerun-under DL-034`
   - P3-T3 `frontier_analysis.py`
   - P3-T4 every `sensitivity_analysis.py` sweep that ran before (S-f stays *not run*, DL-032), then
     `--summary`
   - P3-T5 the evaluation report revised
   - Nothing else may change. In particular, no code change other than §B2 may enter between the
     first and last command. A defect found mid-run stops the rerun and needs its own DL entry.
4. **Mechanical outcomes are followed whatever they are.** If the corrected P1-T7 admits a family on
   calibration, P2-T5 emits an SE-informed spec and P3 evaluates it. If the operating point moves,
   the new point is frozen (new sha256). If any verdict flips, it is reported prominently. **There is
   no override in either direction.**
5. **The test split is read a second time, authorised by this entry** (`--rerun-under DL-034`, as
   `evaluate_test.py` and `run_test_replay.py` require). This is defensible because:
   - the correction was identified externally;
   - it concerns the information regime, not a modelling or tuning choice;
   - it leaves no free parameter;
   - its rules are fixed here before any corrected number exists.
   It is still declared as a threat: the author has seen the original test results.
6. **Reporting.**
   - The corrected results **supersede** the originals as the results of record, at the same paths.
   - The originals are preserved in git: P1 at `2901d77`, P2 at `95c6d6d`, P3 at `1e38db7`, the
     report at `4d9e128`.
   - Before the rerun, the small headline JSON/MD files are copied to
     `results/corrections/dl034/original/`.
   - Afterwards, `results/corrections/dl034/comparison.md` tabulates original vs corrected for every
     headline number and verdict, whether or not it changed.
   - No result may be chosen between the two by its outcome.
7. **What this entry does not do.** It narrows no claim wording, adds no temporal-forward
   evaluation, and changes no RQ. The writing corrections the review asks for (frozen-policy null,
   F1 unresolved, "estimated" carbon, cross-project retrospective scope, multiplicity) belong to the
   P3-T5 revision. They are listed there, and no protocol change is implied.

#### C. Rationale

The study's central null is judged against ④b. A baseline that a live system could not compute
would undermine the comparison and the artifact, however small the effect. The correction has a
single, parameter-free answer, so re-running the predeclared pipeline costs compute (≈ 7.5 h from the
recorded run times) but no researcher degrees of freedom.

#### D. Consequences

- New: `code/scripts/diagnose_history_overlap.py`, `results/corrections/dl034/`.
- Changed on acceptance: `scheduler_core/duration_estimator.py`, its callers and
  `tests/test_duration_estimator.py`, plus every P1–P3 result file regenerated by §B3.
- New frozen identifiers are recorded as they are produced: the `d̂` fit id if it changes, the arm fit
  ids, the `policy_spec.yaml` sha256 and the run fingerprints.
- `PROGRESS.md` records the rerun as a correction gate (not a numbered task, so `tasks_total` stays
  28). P4 remains blocked until the rerun is gated and DL-033 is accepted.
- Threats for P5-T4: the second test pass; the completion proxy; and the unchanged temporal overlap
  between the training and scored splits (DL-014 §Resolution 5).

<!-- Append DL-035, DL-036, … below as the project progresses. -->

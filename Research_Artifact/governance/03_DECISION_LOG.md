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

<!-- Append DL-023, DL-024, … below as the project progresses. -->

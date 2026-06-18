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

<!-- Append DL-011, DL-012, … below as the project progresses. -->

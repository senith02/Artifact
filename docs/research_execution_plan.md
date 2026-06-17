# Research Execution Plan

**Project:** *Benchmarking CI/CD Orchestration Overhead: Energy Consumption across GitHub Actions, GitLab CI and Bitbucket Pipelines on Standardized Self-Hosted Runners*
**Candidate:** K. P. S. Nimsara
**Duration target:** 3–4 months (≈14–16 weeks)
**Companion document:** see `evaluation.md` for the rationale behind several decisions baked into this plan (notably the bare-metal correction).

---

## 0. How to Use This Plan

The plan is organised into **7 sequential phases** spanning ~14–16 weeks. Each phase lists: **objective → tasks → expected outputs → tools/methods → decision points/risks.** Phases overlap slightly (literature review continues throughout; documentation is continuous). Two **critical go/no-go decision points** are flagged (DP-1, DP-2) — do not proceed past them until resolved.

> **Single most important instruction:** Run the self-hosted runners on **bare-metal hardware**, not a VM. RAPL (the power interface both Scaphandre and CodeCarbon depend on) is not exposed inside VMs. This decision is assumed throughout the plan. See `evaluation.md §2.2`.

**Indicative timeline:**

| Phase | Weeks | Focus |
|---|---|---|
| 1. Foundation & Literature | 1–2 | Refine gap, deepen review, finalise RQs |
| 2. Methodology Design & Pre-registration | 2–3 | Lock experimental protocol & analysis plan |
| 3. Environment & Tooling Setup | 3–6 | Bare-metal host, 3 runners, measurement stack |
| 4. Pilot & Measurement Validation | 6–7 | Validate accuracy — **DP-2 gate** |
| 5. Full Experiment Execution | 7–10 | 30+ runs × 3 platforms, data capture |
| 6. Analysis & Interpretation | 10–12 | Statistics, stage breakdown, dashboard |
| 7. Write-up & Finalisation | 12–16 | Report, reproducibility package, defence prep |

---

## Phase 1 — Foundation & Literature Review (Weeks 1–2)

**Objective:** Confirm the gap is still open, deepen the related-work base, and lock the research questions.

### Tasks
1. **Systematic literature search.** Query arXiv, IEEE Xplore, ACM DL, Google Scholar, Semantic Scholar with structured terms: `("CI/CD" OR "continuous integration") AND (energy OR carbon OR "green software" OR sustainability)`, plus tool terms (`Scaphandre`, `CodeCarbon`, `RAPL`, `Eco CI`, `Software Carbon Intensity`).
2. **Set up alerts** (arXiv, Google Scholar) on these terms to catch competing publications during the project.
3. **Build a reference manager library** (Zotero/Mendeley) — target 12–18 sources.
4. **Read the measurement-validity literature**, not just CI/CD papers: RAPL accuracy, TDP-estimation error bounds, CodeCarbon/Scaphandre methodology. *This is central to your own validity argument and currently missing from the proposal.*
5. **Re-confirm the gap** with a structured comparison table (platform coverage × hardware-controlled? × tool used).
6. **Refine RQs** to remove the architectural-confound ambiguity (state that runner execution models differ and are part of what is measured).

### Methods / techniques
- Structured/semi-systematic literature review (PRISMA-lite: record search terms, hits, inclusion/exclusion).
- Backward/forward snowballing from Saavedra (2025) and Aneggi (2026).

### Expected outputs
- A reference library (12–18 sources).
- An updated **related-work matrix** proving the gap is open.
- A finalised, refined set of 4 research questions + objectives.
- Search-protocol notes (for the methodology chapter).

### Decision points / risks
- **DP-1 (gap check):** If a published study already compares all three platforms on identical hardware, pivot (e.g. extend to more platforms, add cloud-vs-self-hosted dimension, or focus on stage-level energy attribution). *Low probability, but check now.*

---

## Phase 2 — Methodology Design & Pre-registration (Weeks 2–3)

**Objective:** Convert the experimental idea into a frozen, defensible protocol *before* collecting data.

### Tasks
1. **Define the independent variable** (CI/CD orchestration agent: GitHub / GitLab / Bitbucket) and **controlled constants** (hardware, OS, workload, network, ambient conditions).
2. **Design the standardized workload:** a simple web application with a deterministic build + test pipeline. Keep it small, reproducible, and identical across platforms (same source, same commands).
3. **Specify pipeline stages** to measure (at minimum: setup/checkout, build, test; optionally idle-agent baseline).
4. **Lock the measurement protocol:**
   - Tool: **Scaphandre primary** (per-process power via RAPL on bare metal), **CodeCarbon secondary** (carbon conversion + cross-validation).
   - Repetitions: **≥30 per platform** (justify with statistical power).
   - Warm-up runs (discard first N), **cool-down between runs**, **randomised run order**, CPU governor fixed, turbo/boost disabled, temperature logged.
   - Idle-agent overhead protocol (long idle window measurement for RQ2).
5. **Lock the analysis plan:** descriptive stats (mean, SD, min, max, CI); normality test (Shapiro–Wilk) → **ANOVA** (if normal) or **Kruskal–Wallis** (if not) + post-hoc (Tukey / Dunn); report **effect sizes**; significance threshold (α = 0.05).
6. **Define carbon conversion:** choose grid carbon-intensity source (e.g. national average or Electricity Maps; align with the SCI specification you cite). Decide static vs time-resolved; state uncertainty.
7. **Write threats-to-validity, ethics statement, and risk register.**
8. **(Recommended) Pre-register** the protocol informally in the project repository (a timestamped `PROTOCOL.md`).

### Methods / techniques
- Controlled experiment design; operationalisation of variables; statistical power reasoning.

### Expected outputs
- A frozen **experimental protocol document** (the methodology chapter draft).
- A frozen **analysis/statistics plan**.
- Ethics statement, threats-to-validity, risk register, Gantt timeline.

### Decision points / risks
- Decide now whether the **dashboard is offline** (recommended) vs real-time (de-scope risk).
- Decide whether to add a **physical power meter** as ground truth (recommended; ~£15–30).

---

## Phase 3 — Environment & Tooling Setup (Weeks 3–6)

**Objective:** Build the reproducible measurement harness on bare metal with all three runners operational.

### Tasks
1. **Provision the bare-metal host:** install Ubuntu LTS on a physical machine with an Intel (RAPL) or AMD (`powercap`) CPU. **Document full spec** (CPU model, cores, RAM, storage, OS/kernel version).
2. **Verify RAPL access:** confirm `/sys/class/powercap/intel-rapl*` exists and is readable. *This is the gate for the whole project.*
3. **Install and validate Scaphandre**; confirm it returns non-zero per-process power on bare metal. Install CodeCarbon; confirm it uses RAPL (not constant mode).
4. **Install the three self-hosted runners** (only one active at a time during measurement):
   - GitHub Actions self-hosted runner.
   - GitLab Runner (choose a single executor — e.g. shell or docker — and keep it constant in spirit across platforms; document differences).
   - **Bitbucket Pipelines runner (Docker-based)** — front-load this; highest setup uncertainty.
5. **Author the standardized workload repo** and three near-identical pipeline definitions (`.github/workflows`, `.gitlab-ci.yml`, `bitbucket-pipelines.yml`) running the same build/test commands.
6. **Build the measurement automation:** scripts that (a) trigger a pipeline, (b) start/stop Scaphandre + CodeCarbon, (c) tag readings by stage, (d) record temperature/governor state, (e) write structured CSV/JSON with run metadata and tool versions.
7. **Set up the data schema** (one row per run×stage: platform, stage, energy_J, duration_s, cpu_util, temp, timestamp, tool, version).

### Methods / techniques
- Infrastructure-as-config; pinned tool versions; per-process energy attribution; structured logging.

### Expected outputs
- A documented, reproducible bare-metal environment.
- Three working self-hosted runners + three equivalent pipelines.
- A measurement harness producing structured, stage-tagged energy data.
- A public (or private-then-public) Git repository with `README`, `PROTOCOL.md`, pinned versions.

### Decision points / risks
- **DP-2 prerequisite:** if RAPL is not readable on the chosen machine, switch hardware *before* proceeding (do not regress to a VM).
- Bitbucket's Docker-based runner introduces an execution-model asymmetry — document it as a known confound, do not try to "hide" it.

---

## Phase 4 — Pilot Run & Measurement Validation (Weeks 6–7)

**Objective:** Prove the harness produces accurate, stable, comparable measurements *before* the full run. **This is the second go/no-go gate.**

### Tasks
1. **Pilot: 3–5 runs per platform.** Verify data capture, stage tagging, and that the harness is fully automated.
2. **Cross-validate tools:** compare Scaphandre vs CodeCarbon energy for the same run; quantify agreement.
3. **Ground-truth check (recommended):** compare tool readings against a **physical wall-socket power meter** over a known workload; report error.
4. **Noise/stability characterisation:** repeat an identical run 10× on one platform; compute coefficient of variation. Confirm cool-down and run-order randomisation suppress drift/throttling.
5. **Sanity-check idle-agent measurement (RQ2):** measure idle overhead; check whether inter-platform differences are above the noise floor. *If not, document that RQ2 may yield a null result and adjust expectations (a null result is valid).*
6. **Tune** repetitions/warm-up/cool-down based on observed variance (e.g. if CV is high, increase N).

### Methods / techniques
- Instrument validation; measurement-uncertainty quantification; pilot study.

### Expected outputs
- A pilot dataset + a short **measurement-validation report** (tool agreement, ground-truth error, noise characterisation).
- Final, tuned values for N, warm-up, cool-down.

### Decision points / risks
- **DP-2 (validity gate):** If tool readings are inconsistent or untrustworthy, **stop and fix** before the full experiment. Do not run 90+ trials on a broken harness.
- If idle-overhead is unmeasurable, re-frame RQ2 honestly rather than abandoning it.

---

## Phase 5 — Full Experiment Execution (Weeks 7–10)

**Objective:** Collect the complete, clean benchmark dataset.

### Tasks
1. **Execute ≥30 runs per platform** (90+ total), one runner active at a time, following the frozen protocol exactly (warm-up, cool-down, randomised order).
2. **Automate the campaign** (e.g. overnight batches); log every run's metadata, tool versions, temperature.
3. **Continuously back up** raw data; never overwrite raw captures.
4. **Run a daily data-quality check** (missing stages, anomalies, throttling events) and quarantine bad runs with reasons recorded (do not silently delete).
5. **Capture the idle-agent baseline** runs per the protocol.
6. **Freeze the dataset** when complete; tag the repo commit.

### Methods / techniques
- Batch experimentation; reproducible run protocol; data provenance/versioning.

### Expected outputs
- The **complete raw benchmark dataset** (the project's primary scientific artifact).
- A run-log / experiment journal documenting any anomalies and exclusions.

### Decision points / risks
- Hardware/thermal failure mid-campaign → re-run affected batches under identical conditions; never mix data from different machine states without flagging.
- Resist adding platforms/workloads now (scope creep) — log such ideas as future work.

---

## Phase 6 — Analysis & Interpretation (Weeks 10–12)

**Objective:** Turn raw data into validated answers to the four research questions.

### Tasks
1. **Clean and consolidate** raw data into analysis tables (pandas/R); document every transformation.
2. **Descriptive statistics** per platform and per stage (mean, SD, min, max, CI).
3. **Inferential statistics** per the frozen plan: normality test → ANOVA or Kruskal–Wallis → post-hoc; report effect sizes and CIs (answers **RQ1**).
4. **Idle-agent overhead analysis** (answers **RQ2**) — report with uncertainty; state null result if applicable.
5. **Stage-level breakdown** — which stage dominates energy per platform (answers **RQ3**); visualise.
6. **Carbon conversion** — apply the chosen grid-intensity factor; report CO2e with explicit uncertainty (avoid false precision).
7. **Derive practical guidance** — translate findings into platform-selection/configuration recommendations (answers **RQ4**).
8. **Build the (offline) dashboard** — Grafana on stored data or Streamlit/matplotlib; present per-stage energy and carbon. Keep it secondary to the statistical analysis.
9. **Interpret against the literature** — compare ordering/magnitudes to Berger-Levrault (2024) etc.; discuss agreements and divergences.

### Methods / techniques
- Descriptive + inferential statistics; effect-size reporting; data visualisation; triangulation against prior work.

### Expected outputs
- A complete statistical results set with figures.
- Answers to all four RQs.
- The analysis dashboard.
- A draft results & discussion chapter.

### Decision points / risks
- If results contradict prior work, investigate (don't suppress) — divergence under controlled hardware is itself a finding.
- Guard against over-claiming generalisability (single machine, self-hosted; see `evaluation.md §4.2`).

---

## Phase 7 — Write-up, Reproducibility & Finalisation (Weeks 12–16)

**Objective:** Produce the final report and a reproducible research package; prepare for assessment/defence.

### Tasks
1. **Write the full report:** Introduction, Literature Review (expanded), Methodology (incl. threats-to-validity, ethics), Results, Discussion, Conclusion & Future Work, References.
2. **Document limitations honestly:** measurement uncertainty, single-machine generalisability, runner-architecture confounds, idle-overhead noise.
3. **Finalise the reproducibility package:** public repo with workload, pipelines, harness scripts, raw + processed data, analysis notebooks, pinned versions, `PROTOCOL.md`, and a `README` enabling a third party to reproduce the study.
4. **Create figures/tables** (comparison charts, stage breakdowns, statistical summaries; the methodology diagram from the proposal).
5. **Proofread rigorously** (the proposal has multiple typos — budget real time for this).
6. **Prepare the defence/viva** materials: slides, a live or recorded dashboard demo, anticipated-questions list (especially around measurement validity).
7. **(Optional, high-value) Draft a short workshop/poster paper** — the Bitbucket novelty makes this realistic.

### Methods / techniques
- Academic technical writing; open-science reproducibility practice; data/figure presentation.

### Expected outputs
- Final dissertation/report.
- Public reproducible research repository + dataset.
- Presentation + dashboard demo.
- (Optional) a short paper draft.

### Decision points / risks
- Leave ≥2 weeks buffer for write-up; reports always take longer than expected.
- Ensure no credentials/tokens are committed to the public repo (research-integrity + security).

---

## Critical Dependencies (Chain)

```
Gap confirmed (DP-1)
   → Protocol frozen
      → Bare-metal host with working RAPL  ← hard prerequisite
         → 3 runners + identical pipelines operational (Bitbucket = highest risk)
            → Measurement harness producing stage-tagged data
               → Pilot validates accuracy (DP-2)  ← hard gate
                  → Full 90+ run campaign
                     → Statistical analysis answers RQ1–RQ4
                        → Report + reproducible package
```

If any upstream item fails, downstream work is invalid — respect the two gates (DP-1, DP-2).

---

## Consolidated Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Phase |
|---|---|---|---|---|---|
| R1 | RAPL unavailable (VM or unsupported CPU) | Med | **Critical** | Use bare metal; verify `powercap` before any other work | 3 |
| R2 | Bitbucket runner setup difficulty | Med | High | Front-load in Phase 3; allocate a dedicated spike | 3 |
| R3 | Idle-agent overhead below noise floor (RQ2) | Med-High | Med | Long idle windows, high N, CIs; accept null result | 4–6 |
| R4 | Thermal throttling / machine-state noise | Med | Med | Fixed governor, turbo off, cool-downs, randomised order, temp logging | 4–5 |
| R5 | Tool disagreement / inaccuracy | Med | High | Cross-validate + physical-meter ground truth at DP-2 | 4 |
| R6 | Dashboard scope creep | Med | Med | Offline dashboard only; treat as secondary | 6 |
| R7 | Competing publication appears | Low-Med | Med | Search alerts; re-check at start and write-up | 1, 7 |
| R8 | Over-claimed generalisability | Med | Med | Bound claims to controlled self-hosted conditions | 6–7 |
| R9 | Write-up time underestimated | High | Med | ≥2-week buffer; write chapters as you go | 7 |
| R10 | Credentials leaked to public repo | Low | High | Secrets scan before publishing | 7 |

---

## Definition of Done

- [ ] Gap re-confirmed and related-work matrix complete
- [ ] Protocol + analysis plan frozen and (ideally) pre-registered
- [ ] Bare-metal host with verified RAPL; full spec documented
- [ ] Three runners + three equivalent pipelines operational
- [ ] Measurement harness validated (tool cross-check + ground truth)
- [ ] ≥30 clean runs per platform collected, dataset frozen
- [ ] RQ1–RQ4 answered with inferential statistics + effect sizes + uncertainty
- [ ] Offline dashboard delivering stage-level energy/carbon views
- [ ] Final report with ethics, threats-to-validity, bounded claims
- [ ] Public reproducible repository (data + code + protocol, secrets-clean)
- [ ] Defence materials + (optional) short paper draft

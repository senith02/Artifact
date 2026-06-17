# Academic Evaluation of Research Proposal

**Proposal title:** *Benchmarking CI/CD Orchestration Overhead: An Empirical Analysis of Energy Consumption across GitHub Actions, GitLab CI and Bitbucket Pipelines using Standardized Self-Hosted Runners*

**Candidate:** K. P. S. Nimsara — Coventry Index 16114715 (BSc Hons Computing, 2024.2)
**Evaluator:** Independent academic review (literature verified against external sources, June 2026)
**Module context:** Project Discovery (proposal/research phase) → Project Artifact (build/evaluation phase)

---

## 1. Overall Summary

This is a **fundamentally sound, well-scoped, and genuinely novel empirical research proposal** with a clearly identified and externally-verified research gap. The candidate has correctly identified a real confound in the existing literature (cross-platform energy comparisons run on heterogeneous, unknown hardware) and proposes a methodologically appropriate control (a single standardized environment running all three orchestration agents). The inclusion of **Bitbucket Pipelines**, which has essentially no published energy-footprint literature, is the strongest novelty claim.

The proposal is **conceptually valid and academically acceptable** at the level expected of a final-year undergraduate computing project. It is, however, **weakened by one critical technical flaw** that must be corrected before implementation: the chosen measurement strategy (RAPL-based tools inside a virtual machine) **cannot physically deliver the hardware-level energy measurement the research design requires.** This is fixable and the fix increases feasibility rather than reducing it.

Secondary weaknesses include an internal inconsistency between the Scope and Methodology sections, the absence of a formal evaluation/validation plan, no explicit ethics or threats-to-validity section, and a thin treatment of confounds introduced by the differing internal architectures of the three runner agents.

**Verdict in one line:** A valid, publishable-grade research idea with a correct gap, but the measurement methodology must be re-grounded on bare-metal hardware (not a VM) to be scientifically defensible.

---

## 2. Validity of the Research Idea

### 2.1 Conceptual validity — **Strong**
The central thesis — that observed energy differences between CI/CD platforms in prior work are confounded by hardware heterogeneity, and that holding hardware constant isolates the orchestration agent as the independent variable — is **logically correct and well-reasoned**. This is textbook experimental control: convert a confounding variable (hardware) into a controlled constant. The framing is coherent from background → problem → questions → scope.

### 2.2 Technical soundness — **Partially sound; one critical flaw**
The experimental architecture (self-hosted runners + process-level energy attribution + repeated trials + descriptive statistics) is appropriate. **However, the measurement instrumentation is flawed as written:**

- **Scaphandre** (named as the primary tool in the Scope) reads CPU energy via the Linux `powercap`/Intel RAPL interface. **RAPL is not propagated from a hypervisor into a guest VM by default**, so Scaphandre cannot obtain power readings inside a standard cloud or local VM. (Verified: Scaphandre compatibility documentation; the tool itself requires either bare-metal RAPL access or a `qemu`-exporter bridge from the host.)
- **CodeCarbon** (named as primary in the Methodology) has the *same* RAPL dependency. When RAPL is unavailable — i.e. inside a VM — CodeCarbon silently switches to **"constant mode,"** estimating CPU power as *TDP × utilisation fraction*. (Verified: CodeCarbon GitHub issues #111, #477; this is documented behaviour on AWS EC2 and Linux VMs.)

**Consequence:** In the proposed VM setup, neither tool measures real energy. CodeCarbon's TDP estimate is effectively a re-scaling of CPU utilisation. This is fatal to **RQ2** ("how much extra energy does each runner agent waste just by staying active"), because idle-agent overhead differences are small and would fall below the noise floor of a TDP model. RQ1 and RQ3 partially survive (utilisation differences are real signal) but cannot be honestly reported as "energy measurements."

**Required correction:** Run the self-hosted runners on **bare-metal physical hardware** (a single dedicated Linux machine or laptop with an Intel/AMD CPU exposing RAPL). On bare metal, both Scaphandre and CodeCarbon read true RAPL energy, the "identical hardware" control becomes genuine, and all four research questions become answerable. This change *reduces* cost and complexity (no hypervisor tuning, no `qemu`-exporter plumbing).

### 2.3 Internal consistency — **Needs fixing**
The **Scope (§1.5)** names Scaphandre as primary and CodeCarbon as backup; the **Methodology (§3)** names CodeCarbon as primary and never mentions Scaphandre. These must be reconciled into a single, justified instrumentation plan. A clean resolution: Scaphandre as primary on bare metal (true per-process power), CodeCarbon as cross-validation/secondary (carbon-conversion + portability).

### 2.4 Academic acceptability — **Yes**
The topic sits squarely within Green Computing / Sustainable Software Engineering, a recognised and active research area. The empirical, hypothesis-driven, reproducible design matches accepted computing-research norms. References are recent (2024–2026), real, and correctly attributed.

### 2.5 Ethical safety — **Yes, but undocumented**
No human subjects, no personal data, no dual-use risk. Ethically low-risk. **But the proposal contains no ethics statement**, which most computing project handbooks require even when the answer is "no ethical issues." This is a documentation gap, not a substantive risk (see §11).

---

## 3. Research Gap Analysis

### 3.1 Is the gap real, and is it still open?
**The gap is real and currently OPEN.** Independent verification of the literature confirms:

| Existing work | Coverage | Why it does NOT close this gap |
|---|---|---|
| Saavedra et al. (2025), arXiv:2510.26413 | GitHub Actions only, 2.2M runs | Single platform; estimation from public logs, not controlled hardware; **its own future-work section explicitly calls for cross-platform comparison** |
| Aneggi et al. (2026), PPTAMη, arXiv:2602.12081 | GitLab CI only | Single platform; builds a bespoke energy-aware pipeline with hardware probes — not a cross-platform comparison; tool-specific |
| Berger-Levrault (2024) | GitHub vs GitLab via Eco CI | **Run on different cloud hardware (AMD EPYC 7763 vs 7B12)** — the exact confound this proposal targets |
| Eco CI / CodeCarbon / GreenFrame | Tooling | General-purpose estimators, not comparative studies; Eco CI supports GitHub/GitLab/Jenkins — **not Bitbucket** |

**Bitbucket Pipelines has effectively no published energy/carbon literature** — confirmed by targeted searching. This is the single most defensible novelty in the proposal.

### 3.2 Solved / partially solved / open?
- **The general problem** (CI/CD has a measurable carbon footprint): **solved/established** — do not claim this as novel.
- **Single-platform measurement** (GitHub, GitLab): **solved.**
- **Cross-platform comparison on identical hardware isolating the agent overhead:** **OPEN** — this is your contribution.
- **Bitbucket Pipelines energy footprint:** **OPEN / unstudied.**

**Caveat to manage:** Saavedra (2025) and Aneggi (2026) are very recent and the field is moving quickly. The candidate should re-run the literature search immediately before and during the project (a "living" related-work section) and set up alerts, because a competing cross-platform study could appear. The gap is open *as of June 2026* but should be re-confirmed at write-up.

### 3.3 Is the gap framed correctly?
Yes, with one refinement: the proposal conflates "isolating the orchestration agent" with "running on identical hardware." Running three agents on one machine controls hardware, but the **agents themselves differ architecturally** (e.g. Bitbucket's self-hosted runner executes steps inside Docker containers; GitHub's and GitLab's runners can execute directly on the host or via different executors). This is not a flaw in the gap, but it means "identical conditions" is only partially true — the *workload* and *hardware* are identical, but the *execution model* is a property of each agent and is therefore legitimately part of what you measure. This should be stated explicitly as a scope clarification, not hidden.

---

## 4. Usefulness & Impact

### 4.1 Who benefits
- **DevOps engineers / platform teams** choosing a CI/CD provider — gain the first empirical, hardware-controlled energy comparison including Bitbucket.
- **Sustainability/Green-IT practitioners and FinOps teams** — energy correlates with cost and carbon reporting (CSRD/ESG).
- **Researchers** — a reproducible benchmark dataset and methodology others can extend (more platforms, more workloads).
- **Tool vendors** (Atlassian, GitHub, GitLab) — comparative data may motivate efficiency improvements in runner agents.

### 4.2 Practical usefulness — **Moderate to high, with honest limits**
The deliverables (benchmark dataset, statistical comparison, stage-level breakdown, dashboard, configuration guidance) are concrete and useful. The **stage-level breakdown** (which pipeline stage burns most energy) is arguably the most directly actionable output for everyday developers.

**Honest limit on impact:** Most real-world CI/CD minutes run on *cloud-hosted* runners, not self-hosted. Findings from one bare-metal machine running self-hosted agents generalise to runner-agent *overhead* and *relative ordering*, but **absolute** numbers and cloud-runner behaviour will differ. Frame contributions as "relative orchestration-agent overhead under controlled conditions," not "the energy cost of CI/CD in production."

### 4.3 Real-world problem? — **Yes**
Software's energy/carbon footprint is a genuine, policy-relevant problem, and the absence of decision-support data for sustainable platform selection is a real practitioner pain point. The work addresses a true (if niche) gap.

### 4.4 Impact ceiling — **Realistic**
This is a strong **undergraduate empirical study** with potential for a short workshop/poster paper, especially because of the Bitbucket novelty. It is not industry-transforming, but it is a legitimate, citable micro-contribution. That is appropriate for the module level.

---

## 5. Practicality & Feasibility (3–4 Months)

**Overall: Feasible, *conditional on the bare-metal correction* and tight scope discipline.**

### 5.1 What makes it feasible
- Self-hosted runners for all three platforms are free to set up and documented.
- A single physical machine satisfies the "identical hardware" requirement — no fleet needed.
- 30 runs × 3 platforms × a small build/test workload is computationally trivial (hours of compute, automatable overnight).
- Statistics required (mean, SD, min/max, ANOVA/Kruskal-Wallis) are standard and well-supported.
- Tooling (Scaphandre, CodeCarbon) is open-source and free.

### 5.2 What threatens feasibility
| Risk | Severity | Mitigation |
|---|---|---|
| **RAPL unavailable in VM** (see §2.2) | **Critical** | Switch to bare-metal hardware — primary recommendation |
| Bitbucket self-hosted runner setup (requires Atlassian account, Docker-based) | Medium | Allocate early spike; have fallback (drop to 2 platforms is **not** advised — Bitbucket is the novelty; instead start Bitbucket setup first) |
| Measuring *idle agent* overhead (RQ2) is hard — differences may be within noise | Medium-High | Use long idle windows, many repetitions, report confidence intervals; pre-register that a null result is a valid finding |
| Dashboard scope creep ("real-time dashboard") | Medium | De-scope to a static/offline analysis dashboard (Grafana on stored data, or even matplotlib/Streamlit); real-time is unnecessary for the research questions |
| Statistical noise / thermal throttling on one machine | Medium | Fix CPU governor, disable turbo, cool-down between runs, randomise run order, log temperature |
| Recent competing publications | Low-Medium | Re-run literature search at start and before write-up |

### 5.3 Skills required
Linux administration, Docker, YAML pipeline authoring, basic Python (CodeCarbon, analysis), introductory inferential statistics. All within reach of a final-year computing student; the statistics is the most likely skill gap and should be addressed early.

### 5.4 Time verdict
With the bare-metal correction and a **de-scoped dashboard**, the project fits a 3–4 month window. Without scope discipline (especially on the dashboard and on chasing absolute cloud numbers), it will overrun. The experiment itself is small; the risk is in setup friction (Bitbucket) and analysis rigour, not compute time.

---

## 6. Technical Requirements & Cost Considerations

| Item | Requirement | Cost |
|---|---|---|
| Compute | One bare-metal Linux machine (laptop/desktop/mini-PC) with Intel RAPL or AMD equivalent exposing `powercap` | £0 if owned; the candidate's own machine suffices |
| OS | Ubuntu LTS (documented version) | Free |
| Runner agents | GitHub Actions runner, GitLab Runner, Bitbucket Pipelines runner | Free |
| Accounts | GitHub, GitLab, Bitbucket (free tiers) | Free |
| Energy tooling | Scaphandre (primary), CodeCarbon (secondary/validation) | Free, open-source |
| Carbon conversion | Grid carbon-intensity factor (e.g. national average or Electricity Maps/Green Software Foundation SCI) | Free data |
| Analysis | Python (pandas, scipy, matplotlib) or R | Free |
| Dashboard | Grafana + Prometheus *or* Streamlit on stored CSVs | Free |
| Workload | A simple web app + build/test pipeline (candidate-authored) | Free |

**No paid subscriptions, no cloud spend, and no specialised hardware are strictly required** once the design moves to bare metal. This is a notable feasibility strength. (If the candidate insists on also characterising cloud behaviour, modest cloud credits would be needed — but that should be optional/secondary, not core.)

---

## 7. Alignment with Project Discovery Guidelines

*(Evaluated against the standard structure expected of a final-year computing project proposal: problem identification, gap justification, background research, methodology, expected outcomes, evaluation plan, ethics, feasibility/scope. The literal handbook text was not available to this evaluator; map these comments onto your handbook's exact criteria.)*

| Criterion | Status | Comment |
|---|---|---|
| Problem identification | ✅ Strong | Clear, motivated, well-contextualised in Green Computing |
| Research gap justification | ✅ Strong | Real, verified, explicitly linked to named prior studies |
| Background / literature review | 🟡 Adequate | Only ~4 primary sources discussed; thin for a literature review. Add 8–15 sources; include the broader software-energy-measurement and RAPL/Scaphandre/CodeCarbon validity literature |
| Research questions & objectives | ✅ Strong | Four focused, answerable RQs aligned to objectives |
| Methodology | 🟡 Flawed but fixable | Strong design logic; **critical instrumentation flaw** (§2.2) and Scope/Methodology inconsistency (§2.3) |
| Expected outcomes | ✅ Clear | Dataset, statistics, breakdown, dashboard, guidance |
| Evaluation / validation plan | ❌ Missing | No statement of how results will be validated, what statistical tests, what counts as significant, how measurement accuracy is checked (e.g. cross-validating Scaphandre vs CodeCarbon vs a wall-socket meter) |
| Ethical considerations | ❌ Missing | No ethics section, even a "no human subjects / low risk" statement |
| Feasibility & scope | 🟡 Partial | Scope stated, but no risk register, no timeline/Gantt, no threats-to-validity |
| Writing quality | 🟡 Needs editing | Several grammatical errors and typos ("kernal", "CodeccCarbon", "messurements", "stags", "ae"); proofread before submission |

**Project Discovery weak/missing sections to add:** formal evaluation plan, ethics statement, threats-to-validity, risk register, and a project timeline/Gantt chart.

---

## 8. Alignment with Project Artifact Guidelines

*(Project Artifact = the build/implementation + evaluation phase that follows Discovery.)*

| Criterion | Status | Comment |
|---|---|---|
| Clear artifact definition | 🟡 Implicit | The "artifact" is the benchmarking harness + dataset + dashboard + guidance. State this explicitly as a defined deliverable |
| Buildability in scope | ✅ Yes | The harness (pipelines + measurement scripts + analysis) is buildable by one student |
| Reproducibility | 🟡 Partial | Promises to document VM specs — good — but should commit to a public repo, pinned tool versions, and a run protocol so the benchmark is reproducible (a core scientific value here) |
| Evaluation of the artifact | ❌ Missing | Needs an explicit experimental protocol: number of runs, warm-up/cool-down, run randomisation, statistical tests, accuracy validation against a ground-truth (e.g. a physical power meter) |
| Iteration / development method | 🟡 Unstated | Indicate an engineering approach (e.g. iterative spikes per platform, then measurement, then analysis) |
| Demonstrable result | ✅ Yes | Statistical comparison + dashboard are demonstrable |

**Project Artifact additions needed:** explicit artifact definition, public reproducible repository, a measurement-accuracy validation step (ground-truth power meter is the gold standard and cheap), and a formal experimental protocol.

---

## 9. Strengths

1. **Genuinely open, verified research gap** — confirmed against current literature (June 2026).
2. **Correct experimental logic** — converting hardware from a confound into a control is methodologically sound and directly answers a limitation that prior authors (Saavedra, Berger-Levrault) themselves flag.
3. **High-novelty inclusion of Bitbucket Pipelines** — essentially unstudied; strongest contribution.
4. **Recent, real, correctly-cited references** — all three primary sources verified.
5. **Low cost and high reproducibility potential** — no paid infrastructure required (once on bare metal).
6. **Concrete, useful deliverables** — dataset, statistics, stage breakdown, guidance.
7. **Appropriate scale** — 30+ repetitions and descriptive + inferential statistics show methodological maturity.

---

## 10. Weaknesses / Missing Elements

1. **Critical:** VM-based RAPL measurement cannot deliver real hardware energy (see §2.2). Move to bare metal.
2. **Internal inconsistency** between Scope (Scaphandre primary) and Methodology (CodeCarbon primary).
3. **No evaluation/validation plan** — how is measurement accuracy verified? What statistical tests? What is the significance threshold?
4. **No ethics, no threats-to-validity, no risk register, no timeline/Gantt.**
5. **Thin literature review** — too few sources; missing the measurement-validity literature (RAPL/TDP accuracy) that is central to this very project.
6. **Architectural confound under-treated** — the three runner agents differ internally (e.g. Bitbucket runs steps in Docker); "identical conditions" is only partially true and should be stated.
7. **Over-ambitious "real-time dashboard"** — unnecessary for the RQs; risks scope creep.
8. **Generalisability not bounded** — self-hosted, single-machine results should not be over-claimed as production/cloud CI/CD energy costs.
9. **Writing/proofreading issues** — multiple typos and grammatical errors.
10. **Carbon conversion under-specified** — which grid carbon-intensity factor, static or time-resolved, which source? This determines the validity of every CO2e number.

---

## 11. Risks & Ethical Concerns

### 11.1 Ethical concerns — **Low**
- No human participants, no personal data, no sensitive data → minimal ethical risk.
- **Action required:** include an explicit ethics statement declaring this, per handbook norms.
- Minor responsible-research consideration: report measurement uncertainty honestly and avoid overstating CO2e precision (TDP-based estimates carry large error bars). Misreporting environmental numbers with false precision is a (mild) research-integrity concern.
- If a public dataset/repo is released, ensure no credentials/tokens from the CI accounts are committed.

### 11.2 Technical & project risks
- **RAPL/VM measurement failure** (critical — addressed by bare-metal switch).
- **Null/indistinguishable results for idle-agent overhead** — plan to report this as a legitimate finding, not a failure.
- **Thermal throttling and machine-state noise** on a single host — control via fixed governor, cool-downs, randomised run order, temperature logging.
- **Bitbucket runner setup friction** — front-load this; it is the highest-uncertainty engineering task.
- **Competing recent publication** — monitor arXiv/IEEE during the project.
- **Tool version drift** — pin versions; record them in the dataset.

---

## 12. Final Verdict: Is This a Valid Research Project?

**Yes — this is a valid, novel, and academically acceptable research project**, suitable for the Project Discovery → Project Artifact pathway and capable of a strong grade, *conditional on three corrections*:

1. **Move measurement to bare-metal hardware** so RAPL (and therefore Scaphandre/CodeCarbon) actually works — this is non-negotiable for scientific validity.
2. **Add the missing sections** — evaluation/validation plan, ethics statement, threats-to-validity, risk register, and timeline.
3. **De-scope the dashboard and bound the generalisability claims** so the project stays inside 3–4 months and reports honestly.

With these corrections, the research is **conceptually valid, technically sound, ethically safe, feasible, and genuinely contributory** — particularly through its unstudied treatment of Bitbucket Pipelines. Without correction (1), the project would produce CPU-utilisation estimates mislabelled as energy measurements, which would undermine its core claim.

**Grade-band judgement (indicative):** strong upper-second / first-class *potential*, currently held back to mid-band by the measurement flaw and the missing methodological sections — all of which are fixable before/early in implementation.

---

## 13. Recommendations for Improvement (Prioritised)

**Must-do (validity-critical):**
1. Replace the VM with a **single bare-metal Linux machine** exposing RAPL/`powercap`; document full hardware spec.
2. Reconcile instrumentation: **Scaphandre as primary** (true per-process power on bare metal), **CodeCarbon as secondary** (carbon conversion + cross-check). Remove the Scope/Methodology contradiction.
3. Add a **measurement-accuracy validation** step: cross-validate Scaphandre vs CodeCarbon, and ideally against a **physical wall-socket power meter** (~£15–30) as ground truth.

**Should-do (handbook compliance & rigour):**
4. Write a **formal evaluation plan**: number of runs, warm-up/cool-down, randomised run order, statistical tests (normality check → ANOVA or Kruskal–Wallis + post-hoc), significance threshold, effect sizes, confidence intervals.
5. Add **ethics statement, threats-to-validity, risk register, and a Gantt timeline.**
6. **Expand the literature review** to 10–15 sources, explicitly including RAPL/TDP measurement-validity literature and the Software Carbon Intensity (SCI) specification you already cite.

**Should-do (scope & honesty):**
7. **De-scope "real-time dashboard"** to an offline analysis dashboard on stored data.
8. **Explicitly bound generalisability** — relative orchestration-agent overhead under controlled bare-metal conditions, not absolute production/cloud CI/CD cost.
9. **State the architectural-confound clarification** (runner execution models differ; this is part of what is measured).
10. **Specify the carbon-intensity factor** and source for all CO2e conversions, with uncertainty.

**Nice-to-have:**
11. Pre-register the protocol (even informally in the repo) and publish a **reproducible public repository** with pinned versions.
12. Treat a **null result on idle-agent overhead as a valid finding.**
13. **Proofread** thoroughly before submission.

---

*Sources consulted for verification:* Saavedra et al. 2025 ([arXiv:2510.26413](https://arxiv.org/abs/2510.26413)); Aneggi et al. 2026 ([arXiv:2602.12081](https://arxiv.org/abs/2602.12081)); Berger-Levrault 2024 ([research-bl.com](https://www.research-bl.com/ci-cd-pipelines-good-software-development-practice-but-green/)); Scaphandre compatibility & RAPL-in-VM documentation ([hubblo-org](https://hubblo-org.github.io/scaphandre-documentation/compatibility.html)); CodeCarbon RAPL-fallback behaviour ([GitHub issues #111](https://github.com/mlco2/codecarbon/issues/111), [#477](https://github.com/mlco2/codecarbon/issues/477)); Eco CI ([green-coding.io](https://www.green-coding.io/products/eco-ci/)); Software Carbon Intensity Specification ([Green Software Foundation](https://sci.greensoftware.foundation/)).

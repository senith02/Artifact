# Alternative Project Ideas — DevOps / CI/CD Domain (Budget-Friendly, AI-Capable)

**For:** K. P. S. Nimsara — Project Artifact
**Context:** Budget-constrained (no paid server/cloud), staying in the CI/CD / DevOps area, open to AI/ML directions.
**Purpose:** Decide whether to fix the original benchmarking proposal or pivot, and choose a feasible, *useful* alternative.

---

## 0. First: Read This Before Choosing

### 0.1 Your supervisor's comment, decoded
> *"Major fundamental issues with this work on whether what is claimed is achievable. If so, the CI/CD runner time can be directly related to carbon footprints of the data centres. Even if that is the case, whether it is useful is in question."*

Two distinct objections:

1. **Achievability** — Can you actually *measure* per-platform energy? On identical hardware you largely cannot isolate it: energy ≈ time × power, and with power roughly constant, your "energy overhead" mostly reduces to **runtime**. (And, as `evaluation.md` shows, RAPL-based measurement fails inside VMs anyway.)
2. **Usefulness** — *Even if* runner-time maps cleanly to carbon, then anyone can already estimate carbon as `runner-minutes × grid-carbon-intensity` **without your study**. So a measurement/benchmarking project adds little.

**The constructive insight hidden in this comment:** your supervisor has *handed you a valid, accepted premise* — **runner time → carbon footprint**. The winning move is to stop *measuring* waste and start *reducing* it, then quantify the saving with exactly that relationship. That converts the weakness ("not useful") into the project's core value ("we cut X% of runner-minutes = Y kg CO₂e").

### 0.2 On budget — the original isn't dead on cost grounds, but it is on usefulness
"Bare metal" just means Linux on hardware you **already own**: dual-boot your Windows laptop into Ubuntu, or boot Ubuntu from a free USB live stick. Cost = £0. (WSL2 is a VM → same RAPL failure, so avoid it.)
**But** even fixed this way, the supervisor's *usefulness* objection remains. So: **pivot is recommended**, ideally to an idea that keeps your existing green-software literature review.

### 0.3 Recommendation in one line
**Pivot to a *constructive* project that reduces CI/CD waste and quantifies carbon savings via runner-minutes** (Ideas 1 or 2 below). This (a) directly answers the supervisor, (b) reuses ~70% of your current literature review and motivation, (c) needs no special hardware, (d) can incorporate AI/ML, and (e) is genuinely useful.

---

## 1. ⭐ TOP PICK — Carbon-Aware CI/CD Job Scheduler

**One-liner:** Build a tool/plugin that **defers or relocates non-urgent CI/CD jobs to lower-carbon time windows (or regions)** using real grid carbon-intensity data, and measure the CO₂e reduction.

| Aspect | Detail |
|---|---|
| **Type** | Constructive artifact + empirical evaluation (optional ML forecasting) |
| **The gap** | Carbon-aware scheduling is established for cloud/AI workloads, but a focused, evaluated study **applied to CI/CD pipelines** is under-explored. Tooling exists (Green Software Foundation **Carbon Aware SDK**, **Electricity Maps**, **WattTime**, UK National Grid ESO API) but is not packaged/evaluated for CI/CD. |
| **What you build** | A scheduler/wrapper that, for jobs tagged "non-urgent" (nightly builds, scheduled scans, doc deploys), queries forecasted carbon intensity and starts the job at the greenest window within an SLA; or routes to the greenest available runner/region. Implement for GitHub Actions (scheduled workflows + a dispatch controller) and/or GitLab CI. |
| **AI/ML option** | Train a **carbon-intensity forecasting model** (time-series: ARIMA/Prophet/LSTM) on historical grid data to make smarter deferral decisions, and/or a **job-duration predictor** so deferral respects deadlines. This gives you a legitimate ML core if you want one. |
| **How you prove value** | `carbon saved = Σ(runner-minutes × (intensity_naive − intensity_scheduled))`. Carbon intensity can vary up to ~40% across the day → real, defensible savings. **Uses exactly the runner-time→carbon relationship your supervisor accepts.** |
| **Data / cost** | Electricity Maps free tier / National Grid ESO carbon-intensity API (free) / Carbon Aware SDK (free). Free CI tiers. **£0.** |
| **Skills** | Python, scheduling logic, REST APIs, basic time-series ML (optional), CI workflow authoring. |
| **Feasibility (3–4 mo)** | High. The artifact is a controller + a forecasting model + a simulation/evaluation harness — all software. |
| **Why it beats the original** | Reuses your green/sustainability literature review and motivation; is *useful* (actively reduces emissions), not just descriptive; needs no hardware energy measurement. |
| **Risks** | Defining "non-urgent" jobs and SLAs realistically; getting region-routing to work on free CI (may need to *simulate* multi-region using historical data rather than live multi-region runners). Mitigate by framing as a temporal-shifting study with a simulation evaluation + a working single-region prototype. |

---

## 2. ⭐ STRONG PICK — ML-Based "Green" Test Selection / Build-Skip Prediction

**One-liner:** Use ML to **predict which CI builds/tests are safe to skip or can be deprioritised**, cutting wasted runner-minutes, and quantify the carbon + time saved.

| Aspect | Detail |
|---|---|
| **Type** | AI/ML core + empirical evaluation with a sustainability framing |
| **The gap** | Build-outcome prediction and test prioritisation are studied (mostly on the aging TravisTorrent dataset). The **fresh angles**: (a) do it on **modern GitHub Actions** data, not Travis; (b) frame the objective explicitly as **carbon/runner-minute reduction**, reporting kg CO₂e saved — a framing prior ML-CI papers rarely quantify. |
| **What you build** | A classifier (e.g. Random Forest / Gradient Boosting / small neural net) predicting build pass/fail or "CI-skip" from commit + diff + history features; integrate a decision policy that skips/defers low-risk runs; evaluate accuracy **and** runner-minutes saved → carbon saved. |
| **AI/ML** | Core of the project — feature engineering, model training, evaluation (precision/recall, cost-sensitive metrics because a wrong "skip" is expensive). |
| **Data** | TravisTorrent (2.6M builds, public) as a baseline; **stronger contribution: mine your own GitHub Actions dataset** via the GitHub REST API (free) from public repos. Public "CI-skip" RL dataset also exists ([arXiv:2405.09657](https://arxiv.org/pdf/2405.09657)). |
| **Cost** | £0 — training small models on your laptop; public data. |
| **Feasibility** | High, *if* you scope the dataset. Reuse TravisTorrent to de-risk; add a GitHub Actions slice for novelty. |
| **Supervisor fit** | Directly reduces runner-time → directly reduces carbon (their accepted premise), and is *useful*. |
| **Risks** | "Skip" decisions are safety-critical (a skipped failing build is bad); handle with cost-sensitive evaluation and a conservative policy. Dataset collection effort — front-load it. |

---

## 3. LLM-Based CI/CD Pipeline Configuration Generation & Repair

**One-liner:** Use an LLM to **generate or auto-repair CI/CD config files** (GitHub Actions / GitLab CI / Bitbucket YAML) from natural language or from broken configs, with a validation-driven repair loop.

| Aspect | Detail |
|---|---|
| **Type** | Applied LLM/NLP tool + evaluation |
| **The gap** | The leading 2025 study ([*Can LLMs Write CI?*, arXiv:2507.17165](https://arxiv.org/abs/2507.17165)) reaches only **~69% similarity and 3% perfect matches** — large headroom. Clear extensions: (a) add a **validate→repair loop** (lint/`act`/schema-validate the generated YAML and feed errors back to the LLM); (b) target **GitLab CI or Bitbucket**, which are far less studied than GitHub Actions; (c) **retrieval-augmented generation** using the official Actions docs dataset. |
| **What you build** | A pipeline: NL/broken-config → LLM → static validation (YAML schema, `actionlint`, dry-run) → iterative repair → evaluate against ground-truth configs. |
| **AI** | LLM prompting, RAG, evaluation methodology; no model training required. |
| **Data / cost** | Public workflow corpora (200k+ GitHub Actions files available); free LLM tiers or small **local open models** (e.g. via Ollama) to avoid API cost. **£0–low.** |
| **Feasibility** | High. Mostly prompt/RAG engineering + a rigorous evaluation harness. |
| **Risks** | Defining "correct" config (similarity vs. executability); mitigate with the validation loop as your key contribution. Watch for fast-moving competing papers. |
| **Note** | Pure AI, very on-trend, no sustainability link — choose this if you want to move *away* from green entirely. |

---

## 4. LLM-Based CI/CD Failure Log Diagnosis & Remediation Suggestion

**One-liner:** Classify CI/CD failure logs by root cause and **suggest fixes** using an LLM, evaluated on real public failure logs.

| Aspect | Detail |
|---|---|
| **The gap** | Industrial systems exist (LogSage, [arXiv:2506.03691](https://arxiv.org/html/2506.03691v2), 1M+ failures) but an **open, reproducible, accessible** approach evaluated on public data is a viable academic contribution — especially log-preprocessing strategies to fit logs in context and a taxonomy of CI failure types. |
| **What you build** | Log-noise filtering → structured prompting → root-cause classification + remediation suggestion → evaluation (accuracy of cause, usefulness of fix). |
| **Data / cost** | Public failed CI runs (GitHub Actions logs via API, free); free/local LLMs. **£0–low.** |
| **AI** | LLM + possibly a lightweight classifier for cause categories. |
| **Feasibility** | Medium-High. The hard part is building a labelled evaluation set; scope it (e.g. 300–500 labelled failures). |
| **Risks** | Labelling effort; log access rate limits. |

---

## 5. LLM-Assisted CI/CD Migration / Config Translation

**One-liner:** Automatically **translate pipeline configs between platforms** (e.g. Travis → GitHub Actions, or GitHub Actions → GitLab CI / Bitbucket) using LLMs, and evaluate correctness.

| Aspect | Detail |
|---|---|
| **The gap** | Emerging ([arXiv:2511.01316](https://arxiv.org/html/2511.01316v1)). Real industry pain (teams switch platforms). Translating **into Bitbucket** is essentially unstudied — reuses your interest in the under-researched platform from the original proposal. |
| **What you build** | Source-config → LLM translation → validation → comparison to a hand-written target. |
| **Data / cost** | Pairs of equivalent configs from public repos that use multiple platforms; free/local LLMs. **£0–low.** |
| **Feasibility** | Medium-High. Building a parallel evaluation corpus is the main effort. |
| **Why it's nice for you** | Keeps the multi-platform (GitHub/GitLab/Bitbucket) flavour of your original idea, minus the impossible energy measurement. |

---

## 6. Security Misconfiguration / "Smell" Detection in CI/CD Workflows

**One-liner:** Build a **static analyser (and/or ML/LLM classifier)** that detects security misconfigurations and anti-patterns in CI/CD workflow files at scale.

| Aspect | Detail |
|---|---|
| **The gap** | Active and well-resourced: ["Pipelines Under Pressure"](https://link.springer.com/chapter/10.1007/978-3-032-12089-2_14), ["Catching Smells in the Act" (SCAM 2024)](https://azaidman.github.io/publications/khatamiSCAM2024b.pdf), Soteria (200k+ workflows), and LLM-assisted auditing ([arXiv:2605.02091](https://arxiv.org/html/2605.02091v1)). **<1% of workflows are misconfiguration-free** — clear utility. Room for: a new detector class, an ML/LLM-based detector vs. rule-based baseline, or extending detection to **GitLab/Bitbucket** (most tools are GitHub-only). |
| **What you build** | Detectors over a large public corpus; optionally an **LLM-assisted auditor** benchmarked against rule-based tools; an empirical report on prevalence. |
| **Data / cost** | 200k+ public workflow files available; GitHub API (free). **£0.** |
| **AI option** | LLM-assisted detection / classification vs. static rules (a clean comparative study). |
| **Feasibility** | High — pure software + data mining; abundant data. |
| **Note** | Defensive-security framing (legitimate and encouraged). Strong, safe, very feasible choice if you want to drop the green theme. |

---

## 7. Empirical Study of CI/CD Waste (Caching, Redundant Triggers) + Optimisation Advisor

**One-liner:** Mine a large corpus of public CI/CD workflows to **quantify wasted runner-minutes** (missing caching, redundant jobs, over-frequent triggers, no path filters) and build an **advisor** that recommends fixes with estimated carbon/minute savings.

| Aspect | Detail |
|---|---|
| **The gap** | Caching effectiveness is being studied ([arXiv:2601.19146](https://arxiv.org/pdf/2601.19146)), but a **green-framed waste audit + automated advisor** across many repos is a fresh, useful angle. |
| **What you build** | A static analyser over public workflows → detect waste patterns → estimate runner-minutes saved → convert to CO₂e via carbon intensity → output recommendations. |
| **Data / cost** | Public workflow files + run metadata via GitHub API. **£0.** |
| **AI option** | Optional ML to rank/predict which optimisations yield the biggest savings. |
| **Feasibility** | High — data mining + estimation, no hardware. |
| **Why it's nice for you** | **Maximally preserves your green-software literature review** while being constructive and useful — arguably the closest pivot to your original theme. |

---

## 8. Decision Guide

### 8.1 Choose by what you want to keep
| If you want to keep… | Pick |
|---|---|
| Your **green/sustainability** literature review + motivation | **Idea 1** (scheduler) or **Idea 7** (waste audit) — closest to original |
| A real **ML training** component | **Idea 2** (test/build prediction) or **Idea 1** with forecasting |
| To go **fully AI/LLM**, drop green | **Idea 3** (config gen/repair) or **Idea 4** (log diagnosis) |
| The **multi-platform (incl. Bitbucket)** flavour | **Idea 5** (translation) or **Idea 6** (cross-platform smell detection) |
| Safest, most data-abundant, lowest-risk | **Idea 6** (security smells) or **Idea 7** (waste audit) |

### 8.2 My ranked recommendation
1. **Idea 1 — Carbon-Aware CI/CD Scheduler** — best balance: keeps your theme, answers the supervisor head-on (reduces carbon via runner-time), AI-optional, £0, useful.
2. **Idea 2 — ML Green Test/Build Prediction** — if you specifically want an ML model as the centrepiece.
3. **Idea 7 — CI/CD Waste Audit + Advisor** — easiest to execute, strong green continuity.
4. **Idea 3 — LLM Config Gen/Repair** — if you'd rather pivot fully to AI/LLM.

### 8.3 Common feasibility notes (all ideas)
- All run on your **existing laptop**; no server, no paid cloud, no hardware power meter.
- Use **GitHub REST API** (free) for data mining; respect rate limits (front-load collection).
- For LLM ideas, prefer **free API tiers or local open models (Ollama)** to keep cost at £0.
- Keep one **clear research question + measurable evaluation** — that's what your supervisor is really checking for.

---

## 9. Suggested Next Step
Pick a direction, then I can help you:
- rewrite the **research problem, gap, RQs, and methodology** for the chosen idea (reusing your existing intro/literature where possible), and
- produce an updated `research_execution_plan.md` tailored to it.

**Recommended default if undecided: Idea 1 (Carbon-Aware CI/CD Scheduler).** It salvages the most of your current proposal and turns your supervisor's objection into the project's main selling point.

---

### References / sources consulted
- Saavedra et al. 2025, *Environmental Impact of CI/CD Pipelines* — [arXiv:2510.26413](https://arxiv.org/abs/2510.26413)
- *Can LLMs Write CI?* 2025 — [arXiv:2507.17165](https://arxiv.org/abs/2507.17165)
- *LLMs in CI/CD Configuration Translation* 2025 — [arXiv:2511.01316](https://arxiv.org/html/2511.01316v1)
- LogSage (LLM CI/CD failure remediation) 2025 — [arXiv:2506.03691](https://arxiv.org/html/2506.03691v2)
- *Detecting CI-Skip: An RL Approach* 2024 — [arXiv:2405.09657](https://arxiv.org/pdf/2405.09657)
- *Catching Smells in the Act* (SCAM 2024) — [PDF](https://azaidman.github.io/publications/khatamiSCAM2024b.pdf); *Pipelines Under Pressure* — [Springer](https://link.springer.com/chapter/10.1007/978-3-032-12089-2_14)
- *CI Caching empirical study* 2026 — [arXiv:2601.19146](https://arxiv.org/pdf/2601.19146)
- TravisTorrent dataset — [paper](https://azaidman.github.io/publications/bellerMSR2017miningchallenge.pdf)
- Green Software Foundation **Carbon Aware SDK**; **Electricity Maps** / **WattTime** / UK National Grid ESO carbon-intensity APIs
- Systematic review of learning-based approaches in CI 2024 — [arXiv:2406.19765](https://arxiv.org/pdf/2406.19765)

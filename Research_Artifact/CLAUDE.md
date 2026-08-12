# CLAUDE.md — Boot-Loader for the Research Artifact

> **You are a Claude session working on a BSc research artifact.** This file is the entry point.
> Read it fully before doing anything else, then follow the session protocol exactly.

## What this project is (one paragraph)

*An Empirical Decision Model for Selective Carbon-Aware Scheduling in CI/CD Pipelines Using
Commit-Level Software Engineering Characteristics.* This project asks **which** commit-triggered builds
should enter carbon-aware scheduling at all — and specifically whether commit-level software-engineering
(SE) characteristics carry decision value **beyond a commit-time estimate of build duration**. It is a
**value-of-information study**, not a new scheduling algorithm: a finding that SE characteristics add
nothing material is a valid, reportable result. The evidence comes from **trace-driven simulation** on
the **TravisTorrent** dataset against UK grid carbon-intensity data; the findings are compiled into an
**evidence-derived policy** (`policy_spec.yaml`) that a **live prototype** (REST API + GitHub Action +
dashboard) runs through the *same* decision core.

> ⚠ **The framing changed on 2026-08-09 (DL-012).** `governance/01_SOURCE_OF_TRUTH.md` now has an
> **amendment layer (Layer 0-A)** above the frozen line: it carries the active title, aim, RQs, and
> strategies. The frozen Layer 1 below the line is the *historical* approved design and is still
> immutable. **Where they differ, Layer 0-A governs execution.** Do not act on Layer 1's headline
> ("risk-aware carbon scheduling") without reading Layer 0-A first.

## Start-of-session ritual (do this every time, in order)

1. Read this file (`CLAUDE.md`).
2. Read `governance/00_SESSION_PROTOCOL.md` — **how** you must work (the task loop, the gate, the report).
3. Read `governance/02_ANTI_HALLUCINATION.md` — the non-negotiable rules.
4. Read `governance/01_SOURCE_OF_TRUTH.md` **Layer 0 + Layer 0-A** (above the frozen line) — the active
   framing. Read Layer 1 when you need the approved design's exact wording.
5. Read `planning/PROGRESS.md` — **where we are**: the current task, what's done, what's next.
6. Read `planning/development_plan.md` — find the **Current Task** entry and read its full spec.
7. Read only the `context/` files relevant to the current task
   (`dataset_reference.md`, `feature_spec.md`, `duration_control_spec.md`).
8. Skim `governance/03_DECISION_LOG.md` — **DL-012 is the framework migration; read it in full.**

Then announce: *"Resuming at **{task-id} — {task-name}**. Plan: …"* and proceed per the protocol.

## The four documents that govern everything

| File | Authority |
| :-- | :-- |
| `governance/01_SOURCE_OF_TRUTH.md` | **What** the project is. Layer 1 frozen; Layer 0-A = active framing (DL-012). |
| `planning/development_plan.md` | **The plan.** Every phase, task, subtask, Definition of Done. |
| `planning/PROGRESS.md` | **The live state.** Progress bars + current/next task. Update at every gate. |
| `governance/03_DECISION_LOG.md` | **The amendments.** Any deviation from the spec is logged here. |

## Hard rules (full text in `governance/02_ANTI_HALLUCINATION.md`)

- **Never invent numbers.** Every metric, score, or figure must come from a real run whose command is
  recorded. If you have not run it, you do not know it.
- **Never code against remembered column names.** Dataset code uses `context/dataset_reference.md`,
  which is pinned to the *real* CSV header (the paper's Table 1 uses different names — do not trust it).
- **Never change scope/method/RQ silently.** Propose it, log it in `03_DECISION_LOG.md`, then act.
- **One task at a time.** Gate level is **per major task**. Do the task, render the end-of-task report
  with progress bars, then **stop and ask** "move to next task?" — do not roll into the next task.
- **Trace every claim.** Anything written in the dissertation cites a source-of-truth section, a
  result file in `results/`, or a decision-log entry.

## The three rules this study lives or dies by (DL-012)

1. **The current build's actual duration may never reach a decision.** `tr_duration` /
   `tr_log_buildduration` are outcomes. They are permitted **only** for simulator accounting, as
   *historical* training labels for the commit-time duration estimator, and as a clearly-labelled
   oracle bound. "Beyond expected build duration" always means beyond a commit-time **estimate** `d̂`.
2. **The policy is frozen before the test split is opened.** Family admission, thresholds and window
   form are all fitted on **train + calibration** projects (P1, P2-T5). Test is touched **once**, in
   Phase 3, against a frozen `policy_spec.yaml`.
3. **The materiality rule is predeclared and is not negotiable after the fact.**
   `results/p0/eval_protocol.md` §A1.7 fixes the floors *now*. At N ≈ 9.2×10⁵ builds significance is
   nearly free — lead with effect sizes and CIs, and reserve "material" for results clearing the floor.
   **If nothing clears it, the duration-only policy is the finding.**

## Where things live

```
governance/   the rules + spec (frozen Layer 1 + active Layer 0-A) + decision log
planning/     development_plan.md (the map, 28 tasks) + PROGRESS.md (the you-are-here)
context/      grounded dataset, feature + duration-control references
code/         scheduler-core, replay simulator, api, github-action  (built in P1–P4)
results/      model reports, ablations, figures, trade-off curves  (real outputs only)
dissertation/ the written report, by chapter  (P5)
```

Dataset location (read-only input, outside this folder):
`../Dataset/19314170/final-2017-01-25.csv/final-2017-01-25.csv` (~2.6M rows, 66 columns).

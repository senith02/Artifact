# CLAUDE.md — Boot-Loader for the Research Artifact

> **You are a Claude session working on a BSc research artifact.** This file is the entry point.
> Read it fully before doing anything else, then follow the session protocol exactly.

## What this project is (one paragraph)

This project builds and evaluates a **risk-aware carbon scheduler for CI/CD pipelines**: a commit-level
build-failure-likelihood model whose calibrated probability sets how long an *already-flexible* build
may be deferred to a lower-carbon electricity window. It is evaluated by **trace-driven simulation** on
the **TravisTorrent** dataset against historical UK grid carbon-intensity data, and demonstrated by a
**live prototype** (REST API + GitHub Action + dashboard) that runs the *same* decision core. The full,
frozen design is in `governance/01_SOURCE_OF_TRUTH.md`.

## Start-of-session ritual (do this every time, in order)

1. Read this file (`CLAUDE.md`).
2. Read `governance/00_SESSION_PROTOCOL.md` — **how** you must work (the task loop, the gate, the report).
3. Read `governance/02_ANTI_HALLUCINATION.md` — the non-negotiable rules.
4. Read `planning/PROGRESS.md` — **where we are**: the current task, what's done, what's next.
5. Read `planning/development_plan.md` — find the **Current Task** entry and read its full spec.
6. Read only the `context/` files relevant to the current task
   (`context/dataset_reference.md` and/or `context/feature_spec.md`).
7. Skim `governance/03_DECISION_LOG.md` for any decisions that amend the source of truth.

Then announce: *"Resuming at **{task-id} — {task-name}**. Plan: …"* and proceed per the protocol.

## The four documents that govern everything

| File | Authority |
| :-- | :-- |
| `governance/01_SOURCE_OF_TRUTH.md` | **What** the project is. Frozen. Never silently changed. |
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

## Where things live

```
governance/   the rules + frozen spec + decision log
planning/     development_plan.md (the map) + PROGRESS.md (the you-are-here)
context/      grounded dataset + feature references
code/         scheduler-core, replay simulator, api, github-action  (built in P1–P4)
results/      model reports, figures, trade-off curves  (real outputs only)
dissertation/ the written report, by chapter  (P5)
```

Dataset location (read-only input, outside this folder):
`../Dataset/19314170/final-2017-01-25.csv/final-2017-01-25.csv` (~2.6M rows, 66 columns).

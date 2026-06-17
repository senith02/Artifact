# Research Artifact — Carbon-Aware CI/CD Scheduling

This folder is the **self-contained working root** for the BSc research project
*"Risk-Aware Carbon Scheduling for CI/CD Pipelines"* (K. P. S. Nimsara, Coventry/NIBM 2024.2).

It is also a small **"session operating system"**: a set of governance and planning documents that
let any Claude Code session pick up the work, execute exactly one task at a time, track progress with
progress bars, and stop for your confirmation before moving on — without losing context or drifting
from the approved research design.

## Start here

If you are a Claude session, read [CLAUDE.md](CLAUDE.md) first — it is the boot-loader and tells you
exactly which files to read and in what order.

If you are a human:

1. **What the project is** → `governance/01_SOURCE_OF_TRUTH.md` (the frozen, approved research spec).
2. **The full plan** → `planning/development_plan.md` (every phase, task, and subtask).
3. **Where we are right now** → `planning/PROGRESS.md` (progress bars + current/next task).

## Folder map

| Path | What it holds |
| :-- | :-- |
| `CLAUDE.md` | Boot-loader. The first thing every session reads. |
| `governance/` | The rules: session protocol, source of truth, anti-hallucination, decision log. |
| `planning/` | The master `development_plan.md` and the live `PROGRESS.md`. |
| `context/` | Grounded references: real dataset columns, the exact feature spec. |
| `code/` | The software artifact (`scheduler-core`, `replay` simulator, `api`, GitHub Action). |
| `results/` | Model reports, figures, trade-off curves — produced by real runs only. |
| `dissertation/` | The written report, chapter by chapter. |

## The golden rule

The approved research design in `governance/01_SOURCE_OF_TRUTH.md` is **frozen**. Nothing in this
project may contradict it. Any change of scope, method, or research question must be recorded as a
dated entry in `governance/03_DECISION_LOG.md` — never as a silent edit.

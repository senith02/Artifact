# Research Artifact — Carbon-Aware CI/CD Scheduling

This folder is the **self-contained working root** for the BSc research project
*"An Empirical Decision Model for Selective Carbon-Aware Scheduling in CI/CD Pipelines Using
Commit-Level Software Engineering Characteristics"* (K. P. S. Nimsara, Coventry/NIBM 2024.2).

> **Reframed 2026-08-09 under DL-012** from the earlier headline *"Risk-Aware Carbon Scheduling for
> CI/CD Pipelines"*. The active framing is **Layer 0-A** of `governance/01_SOURCE_OF_TRUTH.md`; the
> frozen Layer 1 below the line is retained unchanged as the historical approved design.

It is also a small **"session operating system"**: a set of governance and planning documents that
let any Claude Code session pick up the work, execute exactly one task at a time, track progress with
progress bars, and stop for your confirmation before moving on — without losing context or drifting
from the approved research design.

## Start here

If you are a Claude session, read [CLAUDE.md](CLAUDE.md) first — it is the boot-loader and tells you
exactly which files to read and in what order.

If you are a human:

1. **What the project is** → `governance/01_SOURCE_OF_TRUTH.md` — read **Layer 0-A** (the active
   framing) first, then Layer 1 (the frozen, approved research spec) for provenance.
2. **The full plan** → `planning/development_plan.md` (every phase, task, and subtask — 28 in total).
3. **Where we are right now** → `planning/PROGRESS.md` (progress bars + current/next task).
4. **Why the framing changed** → `governance/03_DECISION_LOG.md`, entry **DL-012**.

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
| `docs/` | `research_guide.html`: the living research map, generated from `results/` by `code/scripts/update_research_guide.py` (DL-025). Documentation only; PROGRESS.md wins. |

## The golden rule

The approved research design in `governance/01_SOURCE_OF_TRUTH.md` **below the frozen line** is
immutable. Any change of scope, method, or research question is recorded as a dated entry in
`governance/03_DECISION_LOG.md` **first**, and then appears as an amendment layer *above* the frozen
line — never as a silent edit. That is exactly how the 2026-08-09 reframe (DL-012 → Layer 0-A) was
made, and it is the only sanctioned route.

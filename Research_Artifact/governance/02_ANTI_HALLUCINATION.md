# 02 — Anti-Hallucination & Integrity Rules

These rules exist because the biggest risk to a research artifact is not a bug — it is a **confident
falsehood**: an invented metric, a column that doesn't exist, a claim with no evidence, or quiet drift
away from the approved design. The following are non-negotiable.

---

## R1 — No invented numbers, ever

- Every quantitative claim (accuracy, PR-AUC, carbon saved, latency, row counts, %s) MUST come from a
  **real execution** during the session, or be **read from a file in `results/`** that a prior real
  run produced.
- When you report a number, also report **where it came from**: the command run and/or the result file
  path. If you cannot point to that, you do not have the number — say so.
- Placeholder/expected/illustrative numbers are allowed ONLY when explicitly labelled
  `(illustrative — not a real result)` and never copied into the dissertation as findings.

## R2 — Code against the real dataset, not memory

- The TravisTorrent paper's Table 1 uses column names (`gh_src_churn`, `tr_tests_ok`, …) that **differ
  from the actual CSV header** (`git_diff_src_churn`, `tr_log_num_tests_ok`, …).
- All dataset code MUST use the names pinned in `context/dataset_reference.md`, which were read from the
  real file header. If a needed column isn't listed there, open the CSV header and verify before using
  it — then add it to `dataset_reference.md`.

## R3 — The source of truth is frozen

- `governance/01_SOURCE_OF_TRUTH.md` defines scope, aim, objectives, RQs, methodology, dataset, ML
  protocol, evaluation, artifact, and threats. Treat it as immutable.
- You may **interpret** it and fill in implementation detail. You may **not** change what it claims.
- If reality forces a change (a tool won't install, a column is absent, a 12-week scope must shrink),
  do **not** edit the spec. Follow R4.

## R4 — Deviations go through the decision log

- Any departure from the frozen design — a different library, a dropped feature, a changed metric, a
  scope cut, a modelling assumption not already stated — is recorded as a dated entry in
  `governance/03_DECISION_LOG.md` (ID, date, context, decision, rationale, spec section affected).
- Make the log entry **before** acting on the deviation. The log is append-only; never rewrite history.

## R5 — Trace every dissertation claim

- Anything asserted in `dissertation/` must trace to one of: a section of the source of truth, a file
  in `results/`, a decision-log entry, or a cited reference from §8 of the spec.
- Distinguish clearly between *what the spec proposes* (design intent) and *what was measured* (result).
  Never present a planned outcome as an achieved one.

## R6 — Honest status reporting

- At every gate, the End-of-Task Report reflects what is **actually** true: tests that really ran,
  files that really exist, DoD items genuinely met. Unmet items are shown as `✗`, not hidden.
- "Done" means done **and verified**. If you skipped a step, say so.

## R7 — Respect data leakage discipline

- The ML protocol (§3.5) requires **project-held-out, time-ordered** splits. Never use random shuffling
  or random k-fold on this data — it leaks temporal and cross-project information and invalidates RQ1.
- Features must be **commit-time only**: nothing computed from the build outcome or the future may enter
  the feature set. If unsure whether a column is leaky, treat it as leaky until verified.

## R8 — Reproducibility by default

- Fix random seeds. Pin library versions. Record exact commands. A result that cannot be reproduced
  from the repository is not a result.
- Raw inputs are never modified in place; the dataset under `../Dataset/` is read-only.

---

### Quick self-check before you claim something

1. Did I run it, or am I remembering/guessing? → If guessing, stop.
2. Can I point to the command or the file? → If not, it's not a result.
3. Does this contradict the source of truth? → If yes, log it first (R4).
4. Could this number have leaked from the future/label? → If maybe, it's invalid (R7).

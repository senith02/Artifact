# dissertation/ — The Written Report

Written in Phase 5, but **draft as you go** (spec §3.7 advises leaving real time for write-up).
Planned chapters (mirroring the source of truth):

```
dissertation/
├── introduction.md     # background, problem, aim, objectives, RQs, scope (spec §1)
├── literature.md       # findings, gap, conclusion (spec §2)
├── methodology.md      # approach, data, decision engine, ML protocol (spec §3)  [P5-T1]
├── artifact.md         # software artifact definition (spec §5)                  [P5-T1]
├── results.md          # evaluation results, figures, RQ answers (spec §4)        [P5-T2]
├── discussion.md       # interpretation vs literature                            [P5-T2]
├── threats.md          # threats to validity + every logged proxy/assumption (spec §6) [P5-T3]
├── conclusion.md       # conclusions + future work                              [P5-T3]
└── references.md       # spec §8 + any added sources
```

**Tracing rule (R5):** every claim cites a source-of-truth section, a `results/` file, a decision-log
entry, or a reference. Design intent (what the spec proposes) and measured outcomes (what the runs
showed) must never be conflated.

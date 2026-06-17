# code/ — The Software Artifact

Built across Phases 1–4. The defining principle (spec §5): **one shared core powers both the
evaluation and the live demo.** Planned layout:

```
code/
├── scheduler_core/      # THE shared decision logic (P1–P2)
│   ├── data.py          # TravisTorrent loader (P0-T2)
│   ├── carbon.py        # carbon-intensity series + hour-of-week profile (P0-T3)
│   ├── features.py      # commit-time feature extractor (P1-T1) — see context/feature_spec.md
│   ├── splits.py        # project-held-out, time-ordered splits (P1-T2)
│   ├── eligibility.py   # Stage 1 rule-based gate (P2-T1)
│   ├── policy.py        # Stage 2 ML-informed deferral + decide() (P2-T2)
│   └── accounting.py    # energy + carbon (SCI) accounting (P2-T3)
├── replay/              # trace-driven simulator (P2-T4, P3)
├── api/                 # FastAPI POST /decision (P4-T1)
├── github-action/       # Action + scheduled re-dispatch (P4-T2)
├── dashboard/           # monitoring UI (P4-T3, first to cut)
├── artifacts/           # trained, calibrated models (gitignore large binaries)
└── tests/               # pytest suite
```

Nothing here yet — Phase 0 (P0-T1) creates the skeleton. All code must obey
`governance/02_ANTI_HALLUCINATION.md` (real data, no leakage, reproducible).

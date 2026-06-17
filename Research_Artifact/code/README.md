# code/ — The Software Artifact

Built across Phases 1–4. The defining principle (spec §5): **one shared core powers both the
evaluation and the live demo.** Planned layout:

```
code/
├── scheduler_core/      # THE shared decision logic (P1–P2)
│   ├── config.py        # RANDOM_SEED = 42 — the single global seed (P0-T1) ✅
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

## What exists now (after P0-T1)

```
code/
├── scheduler_core/__init__.py   # re-exports RANDOM_SEED
├── scheduler_core/config.py     # RANDOM_SEED = 42
├── replay/__init__.py           # empty package (simulator added P2-T4)
├── tests/test_smoke.py          # skeleton import + seed tests
├── pyproject.toml               # package metadata + pytest config
├── requirements.txt             # top-level deps (spec §3.2 stack)
├── requirements.lock.txt        # fully-pinned, reproducible lock (from pip freeze)
└── tasks.py                     # task runner: install | test | profile-data | fetch-carbon
```

## Setup (Windows / PowerShell, Python 3.11)

```powershell
cd Research_Artifact/code
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python tasks.py install          # installs requirements.lock.txt if present, else requirements.txt
python tasks.py test             # runs pytest
```

To refresh dependency versions: `pip install -r requirements.txt; pip freeze > requirements.lock.txt`.

The exact resolved versions for this artifact are recorded in `results/p0/env.txt`.

Nothing models anything yet — Phase 0 (P0-T1) created this skeleton. All code must obey
`governance/02_ANTI_HALLUCINATION.md` (real data, no leakage, reproducible).

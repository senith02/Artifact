# Appendices

## Appendix A — Source Code, Data and Results

All software written for this research is public on GitHub. The version described in this thesis is
commit `0d38364` of the research repository, which also holds the result file behind every table and
figure (`Research_Artifact/results/`) and a dated record of every methodological decision
(`Research_Artifact/governance/03_DECISION_LOG.md`).

**Table A.1 — Where the artifact and data can be found**

| Item | Location |
| :-- | :-- |
| Research repository (code, tests, results) | <https://github.com/senith02/Artifact> |
| Demonstration repository with the real CI runs of Table 5.8 | <https://github.com/senith02/carbon-advisor-demo> |
| Example run with a DEFER RECOMMENDED decision | <https://github.com/senith02/carbon-advisor-demo/actions/runs/37735372444> |
| TravisTorrent dataset, 25 January 2017 release (Beller et al., 2017) | Not stored in the repository because of its size (about 4 GB) |
| Great Britain carbon intensity, 2024–2025 | <https://carbonintensity.org.uk/>; fetched series in `code/data/carbon/` |

## Appendix B — Reproduction and Test Results

The artifact runs on one laptop CPU (Windows 11, Python 3.11.1) with 47 pinned packages, including
pandas 3.0.3, scikit-learn 1.9.0, XGBoost 3.2.0 and SHAP 0.51.0, and seed 42 throughout. Each
pipeline stage has its own script in `code/scripts/` that writes its output and run log to
`results/`. To install and test, from `Research_Artifact/code/`:

```
python tasks.py install     # install the pinned packages
python tasks.py test        # result: 807 passed, 1 warning in 56.09s
```

The one warning is a deprecation notice from a third-party library. The tests cover leakage refusal,
the duration estimate's use of finished builds only, the eligibility rules, safety, agreement between
the command-line tool, REST API and research decision function, and every fail-safe case. Refitting
the frozen policy file from scratch reproduces it byte for byte (SHA-256 `e43b004d…5c8cf8`).

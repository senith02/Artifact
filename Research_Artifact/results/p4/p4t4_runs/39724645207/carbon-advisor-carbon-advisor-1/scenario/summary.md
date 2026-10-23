> **SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend if the build ran on GB compute.**

## 🔴 RUN NOW (scenario)

`main` is a protected branch (main or release), so it always runs now.

| | |
| :-- | :-- |
| Branch | `main` |
| GB grid right now | 68 gCO₂/kWh (live, for display only) |

<details><summary>Technical details</summary>

| | |
| :-- | :-- |
| Outcome | policy |
| Policy said | run_now |
| Eligibility rule | protected:mainline |
| Expected duration (d̂) | — (— rung; — completed runs) |
| Window | 0 h |
| GB profile now → at target | 125.1 → 125.1 gCO₂/kWh |
| Estimated carbon change (this build) | — |
| Assumed compute location | GB |
| Provenance | policy duration_only_fallback · spec e43b004d3df0 · estimator 1088d5546f47ff12 · advisor 0.1.0 |

**Full reason:** `stage1[primary]: NOT deferrable (protected:mainline) — git_branch='main' matches the frozen pattern 'mainline' ((?:master|main|trunk|default)), approximating §3.4 class (c) production-branch. Stage 2 not consulted. Running now at slot 76 (Thu 04:00, 125.0670 gCO2/kWh). | SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration estimate from completed history only.`

</details>

<details><summary>Assumptions and limits</summary>

- Recommendation only: the advisor never pauses, cancels or fails a build.
- Carbon figures are estimates under a constant-power energy model, not measurements.
- Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.
- Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.
- GitHub Actions run wall-clock time is a different measure from Travis tr_duration.
- The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).
- Manual and scheduled runs are vetoed by team policy, not detected as urgent.
- The study tested commit-level software-engineering characteristics and did not admit them: this advice uses branch/PR status and a duration estimate only.

</details>

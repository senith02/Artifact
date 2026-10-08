## 🔴 RUN NOW

| | |
| :-- | :-- |
| Outcome | fail_safe |
| Branch | `feature/urgent-fix` |
| Eligibility rule | — |
| Expected duration (d̂) | — (—; — completed runs) |
| Window | — |
| GB profile now → at target | — → — gCO₂/kWh |
| Estimated carbon change (this build) | — |
| Fail-safe | region_not_gb |
| Assumed compute location | GITHUB-HOSTED |

**Why:** `fail-safe [region_not_gb]: compute region GITHUB-HOSTED is outside the evaluated GB regime; no GB carbon figures apply -> RUN NOW. | SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration estimate from completed history only.`

- Recommendation only: the advisor never pauses, cancels or fails a build.
- Carbon figures are estimates under a constant-power energy model, not measurements.
- Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.
- Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.
- GitHub Actions run wall-clock time is a different measure from Travis tr_duration.
- The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).
- Manual and scheduled runs are vetoed by team policy, not detected as urgent.

<sub>policy — · spec — · advisor 0.1.0</sub>

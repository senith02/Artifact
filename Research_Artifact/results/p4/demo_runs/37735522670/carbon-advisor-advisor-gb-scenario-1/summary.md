> **SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend if the build ran on GB compute.**

## 🔴 RUN NOW (scenario)

| | |
| :-- | :-- |
| Outcome | policy |
| Branch | `feature/eligible-change` |
| Eligibility rule | pr_blocking |
| Expected duration (d̂) | — (—; — completed runs) |
| Window | 0 h |
| GB profile now → at target | 149.3 → 149.3 gCO₂/kWh |
| Estimated carbon change (this build) | — |
| Live GB intensity (display only) | 54 gCO₂/kWh (actual) |
| Assumed compute location | GB |

**Why:** `stage1[primary]: NOT deferrable (pr_blocking) — gh_is_pr is true; §3.4 class (a) pull-request-blocking. The dataset does not record whether the check was a required status check, so all PR builds are treated as blocking (DL-020 §4). Stage 2 not consulted. Running now at slot 78 (Thu 06:00, 149.3220 gCO2/kWh). | SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration estimate from completed history only.`

- Recommendation only: the advisor never pauses, cancels or fails a build.
- Carbon figures are estimates under a constant-power energy model, not measurements.
- Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.
- Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.
- GitHub Actions run wall-clock time is a different measure from Travis tr_duration.
- The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).
- Manual and scheduled runs are vetoed by team policy, not detected as urgent.

<sub>policy duration_only_fallback · spec e43b004d3df0 · advisor 0.1.0</sub>

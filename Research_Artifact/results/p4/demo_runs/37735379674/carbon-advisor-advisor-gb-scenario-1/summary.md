> **SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend if the build ran on GB compute.**

## 🔴 RUN NOW (scenario)

| | |
| :-- | :-- |
| Outcome | veto |
| Branch | `feature/urgent-fix` |
| Eligibility rule | push_to_unprotected_branch |
| Expected duration (d̂) | 549 s (project; 1 completed runs) |
| Window | 24 h |
| GB profile now → at target | 149.3 → 109.2 gCO₂/kWh |
| Estimated carbon change (this build) | — |
| Live GB intensity (display only) | 54 gCO₂/kWh (actual) |
| Vetoes | urgent_marker |
| Assumed compute location | GB |

**Why:** `stage1[primary]: deferrable (push_to_unprotected_branch). stage2[duration_only_fallback]: d_hat=549.0s >= d_threshold=480.0s, window=24.0000h (flat w_max=24.0000). Greenest reachable slot is 98 (Fri 02:00, 109.1590 gCO2/kWh) at +20h, vs 149.3220 gCO2/kWh now -> deferring 20h. | veto: the commit message carries an urgency marker -> RUN NOW. | SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration estimate from completed history only.`

- Recommendation only: the advisor never pauses, cancels or fails a build.
- Carbon figures are estimates under a constant-power energy model, not measurements.
- Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.
- Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.
- GitHub Actions run wall-clock time is a different measure from Travis tr_duration.
- The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).
- Manual and scheduled runs are vetoed by team policy, not detected as urgent.

<sub>policy duration_only_fallback · spec e43b004d3df0 · advisor 0.1.0</sub>

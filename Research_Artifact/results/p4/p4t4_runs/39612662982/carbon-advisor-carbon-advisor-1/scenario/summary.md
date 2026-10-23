> **SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend if the build ran on GB compute.**

## 🟢 DEFER RECOMMENDED (scenario)
Run at **Thu 02:00 UTC** (2026-10-22T02:00:00+00:00), +13 h.

| | |
| :-- | :-- |
| Outcome | policy |
| Branch | `feature/redispatch-demo` |
| Eligibility rule | push_to_unprotected_branch |
| Expected duration (d̂) | 549 s (project; 7 completed runs) |
| Window | 24 h |
| GB profile now → at target | 130.0 → 113.2 gCO₂/kWh |
| Estimated carbon change (this build) | -13.0 % |
| Live GB intensity (display only) | 101 gCO₂/kWh (actual) |
| Re-dispatch | recorded as issue #2; close it to cancel |
| Assumed compute location | GB |

**Why:** `stage1[primary]: deferrable (push_to_unprotected_branch). stage2[duration_only_fallback]: d_hat=549.0s >= d_threshold=480.0s, window=24.0000h (flat w_max=24.0000). Greenest reachable slot is 74 (Thu 02:00, 113.1730 gCO2/kWh) at +13h, vs 130.0140 gCO2/kWh now -> deferring 13h. | SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration estimate from completed history only.`

- Recommendation only: the advisor never pauses, cancels or fails a build.
- Carbon figures are estimates under a constant-power energy model, not measurements.
- Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.
- Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.
- GitHub Actions run wall-clock time is a different measure from Travis tr_duration.
- The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).
- Manual and scheduled runs are vetoed by team policy, not detected as urgent.

<sub>policy duration_only_fallback · spec e43b004d3df0 · advisor 0.1.0</sub>

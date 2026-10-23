> **SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend if the build ran on GB compute.**

## 🔴 RUN NOW (scenario)

The policy would defer this build, but a team rule says run now: this run is a re-dispatch of an earlier deferral; the team marks this trigger event as urgent.

| | |
| :-- | :-- |
| Branch | `feature/vps-trigger-test` |
| Expected build time | about 9 min (from 15 earlier completed runs) |
| GB grid right now | 65 gCO₂/kWh (live, for display only) |

<details><summary>Technical details</summary>

| | |
| :-- | :-- |
| Outcome | veto |
| Policy said | defer |
| Eligibility rule | push_to_unprotected_branch |
| Expected duration (d̂) | 550 s (project rung; 15 completed runs) |
| Window | 24 h |
| GB profile now → at target | 109.2 → 107.1 gCO₂/kWh |
| Estimated carbon change (this build) | — |
| Vetoes | redispatched_run, event_vetoed |
| Assumed compute location | GB |
| Provenance | policy duration_only_fallback · spec e43b004d3df0 · estimator 1088d5546f47ff12 · advisor 0.1.0 |

**Full reason:** `stage1[primary]: deferrable (push_to_unprotected_branch). stage2[duration_only_fallback]: d_hat=550.0s >= d_threshold=480.0s, window=24.0000h (flat w_max=24.0000). Greenest reachable slot is 122 (Sat 02:00, 107.0910 gCO2/kWh) at +24h, vs 109.1590 gCO2/kWh now -> deferring 24h. | veto: this run is a re-dispatch of an earlier deferral; the team marks this trigger event as urgent -> RUN NOW. | SE characteristics were evaluated and not admitted (results/p1/incremental_value.md; results/p3/evaluation_report.md) — this decision uses branch/PR status and a duration estimate from completed history only.`

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

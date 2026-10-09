# Repo What-If Report — `public-apis/public-apis` · `test_of_push_and_pull.yml`

> **Demonstration — not research evidence.** SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend if the build ran on GB compute.

| | |
| :-- | :-- |
| Runs fetched / analysed / excluded | 500 / 315 / 185 |
| Stage-1 eligible | 0 (0.0 %) |
| Deferred | 0 (0.0 %) |
| Estimated carbon change vs run-now | 0.0 % (0.0 g at 42.5 W; band 0.0 to 0.0 g) |
| Mean added delay (all analysed runs) | 0.0 h |
| Failed-run TTFF p95, advisor vs run-now | 31.68 h vs 31.68 h (n = 315) |
| History window | 2026-09-25T21:08:05Z → 2026-10-08T14:31:58Z (truncated: older runs exist) |

## Run-now reasons

| reason | runs |
| :-- | --: |
| protected_branch | 152 |
| pull_request | 163 |

Vetoes: none · Fail-safes: none · Excluded: {'conclusion_action_required': 185}

## d̂ rung coverage

| project | language | global | cold start |
| --: | --: | --: | --: |
| 0 | 0 | 0 | 0 |

## Statements

- Recommendation only: the advisor never pauses, cancels or fails a build.
- Carbon figures are estimates under a constant-power energy model, not measurements.
- Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.
- Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.
- GitHub Actions run wall-clock time is a different measure from Travis tr_duration.
- The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).
- Manual and scheduled runs are vetoed by team policy, not detected as urgent.
- What-If output is demonstration only, never research evidence.

## Limitations

- Replay, not observation: the runs really ran at once; this shows what the advisor would have recommended.
- The GB profile is applied as if the runs had used GB compute; where they really ran is unknown.
- Carbon is estimated from the observed run wall-clock under a constant-power model and the GB hour-of-week mean profile, not measured.
- Run wall-clock (updated_at - run_started_at) covers the whole workflow run and is a different measure from Travis tr_duration, on which the thresholds were fitted.
- GitHub's run duration includes any time a run stays open waiting inside the workflow; runs open for hours or days inflate the estimated carbon and the failed-run TTFF.
- History is limited to the fetched window; runs early in the window see less history than a deployed advisor would have.
- A run object does not say whether a push was to a tag, so every ref is treated as a branch; tag pushes, which would be vetoed live, may be counted as eligible.
- Urgency is read from commit-message markers only; pull-request labels are not read.
- Cancelled, skipped, timed-out and other non-success/failure runs are excluded from the analysis.

<sub>policy duration_only_fallback {'d_threshold_seconds': 480.0, 'w_max_hours': 24.0} · spec e43b004d3df0 · profile 2af9992ee46c · estimator 1088d5546f47ff12 · snapshot dc5eb6260f4d fetched 2026-10-08T14:48:27Z</sub>

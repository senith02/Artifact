# Duration-source check (P4-T3, 2026-10-08)

> **Demonstration — not research evidence.**

**Why.** The first reports showed failed-run TTFF p95 of about 25–32 h for `spring-projects/spring-boot`
and `public-apis/public-apis`. Their snapshots hold wall-clock durations (`updated_at − run_started_at`,
DL-037 §4) of up to 154,960 s and 616,558 s. DL-033 R3-B4 prefers the timing endpoint's
`run_duration_ms`, so I compared the two on each repository's four longest analysed runs and two
median runs.

**Command.** For each sampled run id, `GitHubClient.run_duration_ms(repo, run_id)`, a read-only
`GET /repos/{o}/{r}/actions/runs/{id}/timing`, compared with the snapshot's wall-clock.

| repository | run | conclusion | attempt | wall-clock (s) | timing endpoint (s) |
| :-- | --: | :-- | --: | --: | --: |
| public-apis/public-apis | 36641426576 | failure | 1 | 369718 | 369718.0 |
| public-apis/public-apis | 36641370068 | failure | 1 | 369774 | 369774.0 |
| public-apis/public-apis | 36630467817 | failure | 1 | 376065 | 376065.0 |
| public-apis/public-apis | 36494668431 | failure | 1 | 616558 | 616558.0 |
| public-apis/public-apis | 37384608701 | failure | 1 | 21 | 21.0 |
| public-apis/public-apis | 37384081471 | failure | 1 | 21 | 21.0 |
| spring-projects/spring-boot | 34823505437 | failure | 1 | 77189 | 77189.0 |
| spring-projects/spring-boot | 34327086171 | failure | 1 | 90104 | 90104.0 |
| spring-projects/spring-boot | 34728256844 | failure | 1 | 112598 | 112598.0 |
| spring-projects/spring-boot | 34694763967 | failure | 1 | 154960 | 154960.0 |
| spring-projects/spring-boot | 36044356337 | success | 2 | 52 | 52.0 |
| spring-projects/spring-boot | 35991986366 | success | 1 | 52 | 52.0 |
| rails/rails | 36832134780 | success | 1 | 765 | 765.0 |
| rails/rails | 37371497690 | failure | 1 | 903 | 903.0 |
| rails/rails | 37366494938 | failure | 1 | 903 | 903.0 |
| rails/rails | 37366494104 | failure | 1 | 903 | 903.0 |
| rails/rails | 36317146594 | success | 1 | 156 | 156.0 |
| rails/rails | 36311875160 | success | 1 | 156 | 156.0 |

**Finding.** The two sources agree exactly on all 18 runs, including the multi-day ones. The long
durations are GitHub's own run durations, not an artefact of measuring by wall-clock.

- **Duration source unchanged.** DL-037 §4 stands: wall-clock, as the reports state.
- **What the long runs are is not measured here.** That would mean time spent open while waiting
  inside the workflow, or long jobs. A limitation line saying so was added to every report.
- **Report numbers unchanged.** The reports were regenerated from the unchanged snapshots, so only
  that line differs.

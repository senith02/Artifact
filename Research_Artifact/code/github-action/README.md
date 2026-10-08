# Carbon-deferral advisor — GitHub Action

For each CI run, this composite Action recommends either **RUN NOW** or **DEFER RECOMMENDED**, with
a later start time, and says why. It is the live face of a BSc study on selective carbon-aware
scheduling in CI/CD. It runs the study's **frozen** decision core, the same `scheduler_core.decide()`,
`policy_spec.yaml` and duration estimator that the trace-driven evaluation used. It adds no decision
logic of its own (DL-033 revision 3).

> **Recommendation only.** The Action never pauses, cancels or fails a build. Its advisory step always
> exits 0, and any missing input or failed dependency falls back to **RUN NOW**.

## What it decides, and from what

1. **Stage 1, the urgency gate.** Pull requests and protected branches (`main`, `master`, release
   branches, …) always get **RUN NOW**.
2. **Stage 2, the frozen duration-only policy.** For any other push, the Action estimates the run's
   duration (`d̂`) from **this workflow's completed runs**. If `d̂` is at least 480 s, it recommends
   the lowest-carbon hour within 24 h on the GB hour-of-week profile. A shorter run, or one already in
   the best slot, gets RUN NOW.
3. **Team vetoes**, set in `.github/carbon-advisor.yml`, can only turn a deferral into RUN NOW:
   - cold start (no completed history);
   - tags;
   - `workflow_dispatch` and `schedule` events;
   - extra protected branches;
   - an `[urgent]` marker in the commit message;
   - a deadline;
   - a maximum delay.

The study evaluated commit-level software-engineering characteristics and did not admit them. That
**null statement** is printed with every decision. No SE feature, failure model or risk score is used.

## Statements printed on every output (DL-033 R3-C11)

- Recommendation only: the advisor never pauses, cancels or fails a build.
- Carbon figures are estimates under a constant-power energy model, not measurements.
- Evaluated regime: Great Britain only. The compute location is declared by the team, not detected.
- Thresholds (480 s, 24 h) were fitted on Travis CI 2011-2016 and are extrapolated to GitHub Actions.
- GitHub Actions run wall-clock time is a different measure from Travis `tr_duration`.
- The urgency gate (pull request / protected branch) is an unvalidated approximation (DL-020).
- Manual and scheduled runs are vetoed by team policy, not detected as urgent.
- What-If output (P4-T3) is demonstration only, never research evidence.

## Usage

```yaml
permissions:
  contents: read      # read .github/carbon-advisor.yml
  actions: read       # list this workflow's completed runs

jobs:
  carbon-advisor:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { sparse-checkout: .github, persist-credentials: false }
      - id: advisor
        uses: senith02/Artifact/Research_Artifact/code/github-action@<full-commit-sha>
        with:
          compute-region: GB
```

A full reference workflow is in [`examples/advisory.yml`](examples/advisory.yml), and a team config in
[`examples/carbon-advisor.yml`](examples/carbon-advisor.yml).

**Pin the Action by full commit SHA.** GitHub's guidance is that this is the only way to use an action
as an immutable release.

**Don't gate the build on `defer` with this Action alone.** Nothing here re-runs a skipped build later,
so gating would drop deferred builds. The study's optional re-dispatch demonstration was not built.

### Inputs

| input | default | meaning |
| :-- | :-- | :-- |
| `compute-region` | *(empty)* | Where the job's compute runs, **declared**, never detected. Only `GB` is evaluated; anything else gives RUN NOW (fail-safe `region_not_gb`). It must equal the config's `compute_region`. Empty gives the fail-safe `invalid_request`. |
| `scenario` | *(empty)* | `gb-hypothetical` (with `compute-region: GB`) shows what the advisor would recommend on GB compute. Every output is then labelled **SCENARIO**, and `scenario` is `true`. |
| `config` | `.github/carbon-advisor.yml` | Team config path in the workspace. Check out `.github` first. |
| `deadline-utc` | *(empty)* | Optional ISO-8601 deadline. A later recommended slot gives RUN NOW. |
| `live-intensity` | `true` | Show the live GB intensity from the Carbon Intensity API. Display only; it is never part of the decision. |
| `token` | `github.token` | Used read-only to list completed runs. |
| `python-version` | `3.11` | The interpreter the study's lockfile was resolved with. |
| `artifact-name` | `carbon-advisor-<job>` | Prefix of the uploaded audit artifact. |

### Outputs

`action` (`run_now` | `defer`), `display`, `defer_until` (UTC), `reason`, `d_hat_seconds`, `n_history`,
`fail_safe`, `fail_safe_code` and `scenario`.

The full response, the request and a JSON Lines audit record are uploaded as a workflow artifact.
Nothing is committed to your repository.

### Scenario mode

GitHub-hosted runners are not known to be in Great Britain, so a real GitHub-hosted job should
declare its location honestly. A non-GB declaration such as `GITHUB-HOSTED` always gets
RUN NOW (fail-safe).

To *see* what the policy would recommend on GB compute, run a second job with
`compute-region: GB` and `scenario: gb-hypothetical`. Its Step Summary opens with a banner:

> SCENARIO — this runner is NOT in Great Britain. This shows what the advisor would recommend if the
> build ran on GB compute.

Nothing should act on an output marked `scenario: true`.

## Fail-safe behaviour

Each of these gives **RUN NOW** with `fail_safe: true` and a named code:
- an invalid request;
- an untrusted event (`pull_request_target`, `workflow_run`, …);
- an invalid or missing config;
- a region mismatch, or a region that is not GB;
- an invalid scenario or deadline;
- an arrival time in the future;
- a frozen artifact that is missing or does not match its pinned hash;
- a GitHub API failure;
- any internal error, including the advisor's dependencies failing to install.

The full matrix is in `context/p4_interface.md` §6.1.

## Provenance

- **Policy:** `policy_spec.yaml`, sha256 `e43b004d…`, on the duration-only fallback path. Threshold
  480 s, window 24 h.
- **Duration estimator:** fit id `1088d5546f47ff12`, form ④b (expanding project median), read from
  completed history only.
- **Carbon profile:** the GB hour-of-week profile, sha256 `2af9992e…` (LF-normalised).

All three are asserted at load, and a mismatch fails safe. The pins are in `advisor/frozen.py`, and
the decisions are recorded in `governance/03_DECISION_LOG.md` (DL-033, DL-035, DL-036).

**Arrival time** is the UTC clock at the Action's first step. That is within minutes of the run's
creation, and only completed runs that finished before it count as history.

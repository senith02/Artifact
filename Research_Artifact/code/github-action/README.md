# Carbon-deferral advisor — GitHub Action

For each CI run, this composite Action recommends either **RUN NOW** or **DEFER RECOMMENDED**, with
a later start time, and says why. It is the live face of a BSc study on selective carbon-aware
scheduling in CI/CD. It runs the study's **frozen** decision core, the same `scheduler_core.decide()`,
`policy_spec.yaml` and duration estimator that the trace-driven evaluation used. It adds no decision
logic of its own (DL-033 revision 3).

> **Recommendation only.** The Action never pauses, cancels or fails a build. Its step always exits
> 0, and any missing input or failed dependency falls back to **RUN NOW**.

**New here?** The [User Guide](../../USER_GUIDE.md) walks through trying the advisor locally, making
commits that show RUN NOW and DEFER RECOMMENDED, and generating and viewing a What-If report.

## Set it up: one job

Add this job to the CI workflow you already have. You don't need a config file or a checkout
(DL-038 §2).

```yaml
permissions:
  contents: read      # private repositories only
  actions: read       # this workflow's completed runs

jobs:
  carbon-advisor:
    runs-on: ubuntu-24.04
    steps:
      - uses: senith02/Artifact/Research_Artifact/code/github-action@<full-commit-sha>
        with:
          compute-region: GB      # where your build runs: declared by you, never detected
```

Each run then shows the recommendation in three places:
- a **notice** at the top of the run page;
- the full reasoning in the **run summary**;
- the job's **outputs** (`action`, `defer_until`, …).

The workflow the job sits in is the one advised. Placing the job there is how you opt in.

**On GitHub-hosted runners**, which are not known to be in Great Britain, declare where they really are
(for example `compute-region: GITHUB-HOSTED`) and add `show-gb-scenario: true`. The real answer is then
RUN NOW (fail-safe `region_not_gb`), and the same summary adds a section labelled **SCENARIO** showing
what the advisor would recommend on GB compute.

Reference workflows in [`examples/`](examples/):

| file | what it does |
| :-- | :-- |
| [`advisory.yml`](examples/advisory.yml) | the one-job setup above, beside a build |
| [`redispatch.yml`](examples/redispatch.yml) + [`carbon-dispatch.yml`](examples/carbon-dispatch.yml) | skip a deferred build and re-run it later (below) |
| [`whatif.yml`](examples/whatif.yml) | the Repo What-If Report, on demand |

**Pin the Action by full commit SHA.** GitHub's guidance is that this is the only way to use an action
as an immutable release.

## What it decides, and from what

1. **Stage 1, the urgency gate.** Pull requests and protected branches (`main`, `master`, release
   branches, …) always get **RUN NOW**.
2. **Stage 2, the frozen duration-only policy.** For any other push, the Action estimates the run's
   duration (`d̂`) from **this workflow's completed runs**. If `d̂` is at least 480 s, it recommends
   the lowest-carbon hour within 24 h on the GB hour-of-week profile. A shorter run, or one already in
   the best slot, gets RUN NOW.
3. **Team vetoes** can only turn a deferral into RUN NOW:
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

## Inputs

| input | default | meaning |
| :-- | :-- | :-- |
| `compute-region` | *(empty)* | Where the job's compute runs, **declared**, never detected. Only `GB` is evaluated; anything else gives RUN NOW (fail-safe `region_not_gb`). Empty gives the fail-safe `invalid_request`. |
| `show-gb-scenario` | `false` | With a non-GB region, also show a labelled SCENARIO answer for GB compute. The outputs stay the real answer, plus `scenario_display` and `scenario_defer_until`. |
| `urgent-markers` | `[urgent]` | Comma-separated commit-message markers that force RUN NOW. |
| `extra-protected-branches` | *(none)* | Comma-separated branch patterns (fnmatch) that always RUN NOW. |
| `max-delay-hours` | `24` | The longest delay you accept, in (0, 24]. A longer recommendation becomes RUN NOW. The window is never re-optimised. |
| `grid-display-region` | *(none)* | Outward postcode or region id 1–17 for a live regional intensity, shown for display only. |
| `redispatch` | `false` | `true` records each deferral as an issue so the build can be skipped and re-run later (below). |
| `mode` | `advise` | `advise`, `whatif` (with `workflow`) or `dispatch`. |
| `workflow` | *(empty)* | For `mode: whatif`, the workflow file to replay. |
| `scenario` | *(empty)* | `gb-hypothetical` (with `compute-region: GB`) labels the whole run a SCENARIO. |
| `deadline-utc` | *(empty)* | Optional ISO-8601 deadline. A later recommended slot gives RUN NOW. |
| `live-intensity` | `true` | Show the live GB intensity from the Carbon Intensity API. Display only; it is never part of the decision. |
| `config` | *(empty)* | Optional team config file (see below). |
| `token` | `github.token` | Lists completed runs; writes the deferral issue; dispatches in `mode: dispatch`. |
| `python-version` | `3.11` | The interpreter the study's lockfile was resolved with. |
| `artifact-name` | `carbon-advisor-<job>` | Prefix of the uploaded audit artifact. |

**A config file is optional.** If `.github/carbon-advisor.yml` exists in a checked-out workspace, or
`config` names a file, that file is used instead of the inputs, exactly as before. Its
`compute_region` must then equal `compute-region`. The schema is in
[`examples/carbon-advisor.yml`](examples/carbon-advisor.yml). Without a file, the config built from the
inputs is saved in the audit artifact, so every decision shows the config it ran under.

## Outputs

- `action` (`run_now` | `defer`), `display`, `defer_until` (UTC), `reason`, `d_hat_seconds`, `n_history`.
- `fail_safe`, `fail_safe_code` and `scenario`.
- `deferred`: `true` **only** when a deferral was recorded for re-dispatch. This is the only output to
  skip a build on.
- `build_sha`: the commit to build. In a re-dispatched run it is the deferred commit; otherwise it is
  this run's.
- `scenario_display` and `scenario_defer_until`, with `show-gb-scenario`.

The full response, the request and a JSON Lines audit record are uploaded as a workflow artifact.
Nothing is committed to your repository.

## Skip a deferred build and re-run it later (opt-in)

This is *deferred re-dispatch, not pausing* (DL-033 R3-C10; DL-038 §6). It needs two files:
[`redispatch.yml`](examples/redispatch.yml) and [`carbon-dispatch.yml`](examples/carbon-dispatch.yml).

1. With `redispatch: true`, a DEFER is recorded as an open issue labelled **`carbon-deferral`**, one
   per (repository, workflow, commit). `deferred` is then `true`, and the build job is skipped.
2. Every hour, `carbon-dispatch.yml` (`mode: dispatch`) dispatches each due issue on its branch, with
   input `carbon_redispatch_sha`, then comments on the issue and closes it.
3. The re-dispatched run is always RUN NOW. Its build checks out `build_sha`, the deferred commit.

The guarantees:
- **Never dropped.** If a deferral cannot be recorded, the run is RUN NOW (fail-safe
  `redispatch_unavailable`) and the build runs. A failed dispatch leaves the issue open for the next
  hour. After arrival + 26 h, the dispatcher dispatches anyway ("deadline reached").
- **Human-cancellable.** Close the issue to cancel. Nothing then re-runs the build.
- **At most once.** An issue is closed after its dispatch. A dispatch that already exists for the
  commit is never repeated. A re-run of the deferring run reuses its open issue.
- **Trusted input only.** Only issues created by `github-actions[bot]` with a well-formed record are
  dispatched.

The caveats:
- GitHub runs scheduled workflows only from the default branch, can delay them under load, and
  disables them in a public repository after 60 days without activity.
- The dispatch uses the branch head's version of the workflow file.
- The workflow must declare the `carbon_redispatch_sha` input under `workflow_dispatch`.

Permissions:
- The advisory job adds `issues: write`.
- The dispatcher declares `actions: write` and `issues: write`, in its own workflow only.

Scenario deferrals are never recorded. The exception is `redispatch: scenario-demo`, which exists only
so a demo repository on a non-GB runner can show the cycle; every issue it opens is titled **[SCENARIO]**.

## The Repo What-If Report

[`whatif.yml`](examples/whatif.yml) runs the same Action with `mode: whatif`. It replays this
repository's completed runs of one workflow through the advisor on GB compute (labelled SCENARIO).
It writes the report into the run summary and uploads Markdown, JSON and a static HTML page.
Demonstration only, never research evidence (DL-037).

## Fail-safe behaviour

Each of these gives **RUN NOW** with `fail_safe: true` and a named code:
- an invalid request;
- an untrusted event (`pull_request_target`, `workflow_run`, …);
- an invalid or missing config, including an invalid input value;
- a region mismatch, or a region that is not GB;
- an invalid scenario or deadline;
- an arrival time in the future;
- a frozen artifact that is missing or does not match its pinned hash;
- a GitHub API failure;
- a deferral that could not be recorded for re-dispatch (`redispatch_unavailable`);
- any internal error, including the advisor's dependencies failing to install.

The full matrix is in `context/p4_interface.md` §6.1.

## Provenance

- **Policy:** `policy_spec.yaml`, sha256 `e43b004d…`, on the duration-only fallback path. Threshold
  480 s, window 24 h.
- **Duration estimator:** fit id `1088d5546f47ff12`, form ④b (expanding project median), read from
  completed history only.
- **Carbon profile:** the GB hour-of-week profile, sha256 `2af9992e…` (LF-normalised).

All three are asserted at load, and a mismatch fails safe. The pins are in `advisor/frozen.py`, and
the decisions are recorded in `governance/03_DECISION_LOG.md` (DL-033, DL-035, DL-036, DL-038).

**Arrival time** is the UTC clock at the Action's first step. That is within minutes of the run's
creation, and only completed runs that finished before it count as history.

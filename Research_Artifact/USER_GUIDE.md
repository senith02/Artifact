# User Guide — Carbon-Deferral Advisor

This guide shows how to try the carbon-aware decision model, how to make commits that produce each of
its two answers (**RUN NOW** and **DEFER RECOMMENDED**), how to generate and read a **What-If report**,
and how to add the advisor to your own GitHub repository.

> **What the advisor is.** For each CI run it recommends either **RUN NOW** or **DEFER RECOMMENDED**
> (with a later, lower-carbon start hour) and explains why. It runs the frozen decision model from the
> study *An Empirical Decision Model for Selective Carbon-Aware Scheduling in CI/CD Pipelines Using
> Commit-Level Software Engineering Characteristics*. It is a **recommendation only**: it never pauses,
> cancels or fails a build.

## Contents

1. [How the advisor decides](#1-how-the-advisor-decides)
2. [Try it on your computer (no GitHub needed)](#2-try-it-on-your-computer-no-github-needed)
3. [Add the advisor to your GitHub repository](#3-add-the-advisor-to-your-github-repository)
4. [Make commits that show RUN NOW and DEFER RECOMMENDED](#4-make-commits-that-show-run-now-and-defer-recommended)
5. [Generate and view a What-If report](#5-generate-and-view-a-what-if-report)
6. [Team configuration reference](#6-team-configuration-reference)
7. [Troubleshooting](#7-troubleshooting)
8. [Limits you should know about](#8-limits-you-should-know-about)

---

## 1. How the advisor decides

```
commit pushed
   │
   ├─ Is it a pull request, or a push to a protected branch (main, master, release/*, hotfix, v1.2.3, …)?
   │      yes → RUN NOW (someone is waiting for the result)
   │
   ├─ Expected duration from this workflow's completed runs ≥ 480 s?
   │      no  → RUN NOW (too short to be worth delaying)
   │
   ├─ Is there a cleaner hour in the next 24 h on the Great Britain carbon profile?
   │      no  → RUN NOW (this hour is already the cleanest)
   │      yes → DEFER RECOMMENDED, start at that hour
   │
   └─ Team vetoes can only turn a deferral back into RUN NOW:
          no completed history yet (cold start), "[urgent]" in the commit message,
          tags, manual or scheduled runs, extra protected branches, a deadline, a maximum delay
```

- The **expected duration** is the median duration of the workflow's own earlier runs that had
  **finished** before this run started. The study found this beats a model built on commit
  characteristics, and that commit characteristics add no decision value beyond it.
- Carbon is judged on the **Great Britain** hour-of-week profile (2024–2025). The compute location is
  **declared** by the team, never detected; any region other than `GB` gets RUN NOW.
- If anything is missing or fails (bad input, no history, API error, altered files), the answer is a
  **fail-safe RUN NOW** with a named reason.

---

## 2. Try it on your computer (no GitHub needed)

### 2.1 Install

You need Python 3.11. From the repository root:

```bash
cd Research_Artifact/code
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
python tasks.py install     # installs the 47 pinned packages
python tasks.py test        # optional: runs the 807 automated tests
```

Run all commands below from `Research_Artifact/code/` with the environment active.

### 2.2 See both answers with the example requests

[`code/examples/`](code/examples/) holds a team config and five example requests. Each request
describes one CI run and carries its own history of 14 earlier completed runs, so no GitHub access is
needed. All five arrive on a Wednesday at 18:00 UTC, the dirtiest hour of the week on the GB profile.

```bash
python -m advisor advise --request examples/request_defer.json --config examples/team_config.yml --no-live
```

| Example file | What it describes | Answer | Reason shown |
| :-- | :-- | :-- | :-- |
| `request_defer.json` | Push to `feature/new-parser`, earlier runs take 600 s | **DEFER RECOMMENDED** to Thursday 02:00 UTC (+8 h) | Expected duration 600 s ≥ 480 s; cleaner hour within 24 h (113.2 against 172.9 gCO₂/kWh) |
| `request_run_now_main.json` | Same push, but to `main` | **RUN NOW** | Protected branch: `main` |
| `request_run_now_pull_request.json` | A pull request | **RUN NOW** | Pull requests always run now |
| `request_run_now_short_build.json` | Push to a feature branch, earlier runs take 120 s | **RUN NOW** | Expected duration 120 s < 480 s |
| `request_run_now_urgent.json` | Push with `[urgent]` in the commit message | **RUN NOW** | Team veto: urgent marker |

The full response is printed as JSON. Add `--summary-out summary.md` to also write the same Markdown
summary the GitHub Action shows, and `--json-out response.json` to save the response to a file.

To build your own request, copy an example and change `branch`, `event` (`push` or
`pull_request`; `is_pr` must match), `arrival_utc` (not in the future), `head_commit_message`, or the
`duration_s` values in `history`. The request fields are defined in
[`context/p4_interface.md`](context/p4_interface.md) §3, and the history entries in §4.

### 2.3 Use real history from a public GitHub repository

Leave `history` out of the request and add `--github`; the advisor then reads the workflow's completed
runs from the GitHub API (read-only). Public repositories work without a token; set `GITHUB_TOKEN`
for private repositories or to avoid the unauthenticated rate limit.

```bash
python -m advisor advise --request my_request.json --config examples/team_config.yml --github --no-live
```

### 2.4 Use the REST API

```bash
# start the API on http://127.0.0.1:8000 (loopback only unless ADVISOR_API_TOKEN is set)
ADVISOR_CONFIG=examples/team_config.yml python -m api          # PowerShell: $env:ADVISOR_CONFIG = "examples/team_config.yml"; python -m api

# in a second terminal
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/decision -H "Content-Type: application/json" --data @examples/request_defer.json
```

The API gives exactly the same decision as the command-line tool; an automated parity test checks this.

---

## 3. Add the advisor to your GitHub repository

### 3.1 Add the team configuration file

Create `.github/carbon-advisor.yml` in your repository (all keys: Section 6):

```yaml
compute_region: GB              # where your CI compute runs; declared, never detected
enabled_workflows: [ci.yml]     # the workflow file(s) the advisor should advise on
urgent_markers: ["[urgent]"]    # commit-message text that means "run now"
veto_events: [workflow_dispatch, schedule]
max_delay_hours: 24
cold_start_run_now: true
```

### 3.2 Add an advisor job to your workflow

Add this job to the workflow named in `enabled_workflows` (here `.github/workflows/ci.yml`). It runs
beside your build and only publishes a recommendation.

```yaml
permissions:
  contents: read      # read .github/carbon-advisor.yml
  actions: read       # list this workflow's completed runs

jobs:
  carbon-advisor:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          sparse-checkout: .github
          persist-credentials: false
      - id: advisor
        uses: senith02/Artifact/Research_Artifact/code/github-action@7c19b9c319d807135d10f38ddf7df8c3f259bc3e
        with:
          compute-region: GB          # must equal compute_region in .github/carbon-advisor.yml
```

- **Pin the Action by its full commit SHA** (as above). That is the only way to use an action as an
  immutable release.
- **Your runner's location matters.** GitHub-hosted runners are not known to be in Great Britain, so
  the honest declaration for them is not `GB`, and the answer is always RUN NOW (fail-safe
  `region_not_gb`). To see what the policy *would* recommend on GB compute, add a second job with
  `compute-region: GB` and `scenario: gb-hypothetical`; its output is labelled **SCENARIO**
  (this is what the demo repository does, see [its `ci.yml`](https://github.com/senith02/carbon-advisor-demo/blob/main/.github/workflows/ci.yml)).
- **Don't block your build on `defer`.** Nothing re-runs a skipped build later, so gating would drop
  deferred builds.

### 3.3 Where to see the recommendation

Open the workflow run on GitHub → click the **carbon-advisor** job → **Summary**. The summary shows
RUN NOW or DEFER RECOMMENDED, the recommended start time, the reason, the expected duration and the
number of completed runs it used. The same values are job outputs (`action`, `display`,
`defer_until`, `reason`, `d_hat_seconds`, `n_history`, `fail_safe`, `fail_safe_code`, `scenario`), and
the full request, response and audit record are uploaded as a workflow artifact named
`carbon-advisor-<job>-<attempt>`.

To print the recommendation in a later job:

```yaml
  report:
    needs: carbon-advisor
    runs-on: ubuntu-24.04
    steps:
      - env:
          DISPLAY_TEXT: ${{ needs.carbon-advisor.outputs.display }}
          DEFER_UNTIL: ${{ needs.carbon-advisor.outputs.defer_until }}
        run: echo "Advisor says: $DISPLAY_TEXT $DEFER_UNTIL"
```

(Expose the outputs on the `carbon-advisor` job with
`outputs: { display: "${{ steps.advisor.outputs.display }}", defer_until: "${{ steps.advisor.outputs.defer_until }}" }`.)

---

## 4. Make commits that show RUN NOW and DEFER RECOMMENDED

The quickest way is to **fork the demo repository**
[`senith02/carbon-advisor-demo`](https://github.com/senith02/carbon-advisor-demo). Its `ci.yml`
already has the advisor and a synthetic build of about nine minutes, which is long enough to pass the
480-second threshold.

### 4.1 Prepare (once)

1. Fork the repository on GitHub, then open the fork's **Actions** tab and click **I understand my
   workflows, go ahead and enable them** (GitHub disables workflows in new forks).
2. Clone your fork:
   ```bash
   git clone https://github.com/<your-user>/carbon-advisor-demo.git
   cd carbon-advisor-demo
   ```
3. **Build some history.** The advisor estimates duration only from runs that have *completed*, and a
   new fork has none. Push one commit to `main` and wait about 10 minutes for the `ci` run to finish:
   ```bash
   git commit --allow-empty -m "Build history for the advisor"
   git push origin main
   ```
   This first run gets RUN NOW (protected branch `main`).

### 4.2 Commits that give RUN NOW

| Try this | Commands | Expected answer in the job Summary |
| :-- | :-- | :-- |
| Push to a protected branch | `git commit --allow-empty -m "Change on main"` then `git push origin main` | RUN NOW: protected branch (`protected:mainline`) |
| Open a pull request | Push a branch (as in 4.3), then open a pull request for it on GitHub | RUN NOW: pull request (`pr_blocking`) |
| Mark the commit as urgent | `git checkout -b feature/hotfix-demo`, `git commit --allow-empty -m "[urgent] Fix the crash"`, `git push -u origin feature/hotfix-demo` | RUN NOW: team veto `urgent_marker` |
| Push before any run has completed | Push a feature branch while the fork has no completed `ci` run yet | RUN NOW: team veto `cold_start` (the Summary notes that the policy alone would have deferred) |
| Look at the real-location job | Any push | The **advisor (real location, GitHub-hosted)** job always says RUN NOW, fail-safe `region_not_gb`, because a hosted runner's region cannot be chosen or verified |

### 4.3 A commit that gives DEFER RECOMMENDED

After at least one `ci` run has completed (Step 4.1):

```bash
git checkout -b feature/try-defer
git commit --allow-empty -m "Try the carbon advisor"
git push -u origin feature/try-defer
```

Open the new run → **advisor (GB scenario)** job → **Summary**. It shows **DEFER RECOMMENDED
(scenario)** with the recommended start time in UTC, the expected duration (about 550 s, from the
completed runs) and the reason.

All of these must be true for DEFER RECOMMENDED:

- the branch is not protected and the event is a `push` (not a pull request, tag, manual or scheduled
  run);
- the declared region is `GB` (here through the labelled GB scenario job);
- at least one run of the workflow has completed, and their median duration is at least 480 s;
- there is a cleaner hour in the next 24 hours. At the cleanest hours of the week (for example around
  Sunday midday UTC) the answer is RUN NOW because the current hour is already the best; push again
  later and it will defer;
- the commit message has no `[urgent]` marker.

In your own repository the same rules apply; your workflow just needs completed runs of 480 s or more.

---

## 5. Generate and view a What-If report

A What-If report replays a repository's recent **completed** runs of one workflow through the advisor
and shows how many would have been deferred, the estimated carbon change, the added delay, and why the
other runs were not deferred. It is a demonstration of the policy on your history, not a measurement.

### 5.1 In GitHub Actions

Add the workflow below as `.github/workflows/whatif.yml`. The demo repository already has it.

```yaml
name: carbon-whatif

on:
  workflow_dispatch:
    inputs:
      workflow:
        description: Workflow file to replay (e.g. ci.yml)
        required: true
        default: ci.yml

permissions:
  contents: read
  actions: read

jobs:
  whatif:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: senith02/Artifact
          ref: 0800bd410f4aaabd607d14718716f50726696c6d
          path: advisor-src
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.11"
      - name: Install the advisor's pinned runtime packages
        run: >-
          python -m pip install --disable-pip-version-check --no-deps --only-binary=:all:
          -r advisor-src/Research_Artifact/code/github-action/requirements.action.txt
      - name: Repo What-If Report
        working-directory: advisor-src/Research_Artifact/code
        env:
          GITHUB_TOKEN: ${{ github.token }}
          WHATIF_REPO: ${{ github.repository }}
          WHATIF_WORKFLOW: ${{ inputs.workflow }}
          WHATIF_OUT: ${{ runner.temp }}/whatif
        run: >-
          python -m advisor whatif --repo "$WHATIF_REPO" --workflow "$WHATIF_WORKFLOW" --fetch
          --snapshot "$WHATIF_OUT/snapshot.json" --out "$WHATIF_OUT/report"
      - name: Show the report in the run summary
        env:
          REPORT: ${{ runner.temp }}/whatif/report/report.md
        run: cat "$REPORT" >> "$GITHUB_STEP_SUMMARY"
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: carbon-whatif-report
          path: ${{ runner.temp }}/whatif/report/
```

**To run it:** open the repository's **Actions** tab → **carbon-whatif** → **Run workflow** → enter
the workflow file to replay (for example `ci.yml`) → **Run workflow**.

**To view it:**

- **Quick view:** open the finished run and look at its **Summary**; the whole report is there as a
  table.
- **Full page with charts:** at the bottom of the run page, under **Artifacts**, download
  `carbon-whatif-report`, unzip it and open `report.html` in a web browser. It is a static page with
  the headline numbers, the reasons runs were not deferred, the estimated carbon per run with the
  ±50% power band, and a week grid showing when deferred runs arrived and when they would have
  started.
- `report.json` holds the same numbers for other tools.

### 5.2 On your computer

```bash
python -m advisor whatif --repo senith02/carbon-advisor-demo --workflow ci.yml \
    --fetch --snapshot whatif_out/snapshot.json --out whatif_out/report
```

Then open `whatif_out/report/report.html` in a browser (Windows: `start whatif_out\report\report.html`,
macOS: `open …`, Linux: `xdg-open …`). Notes:

- `--fetch` downloads up to 500 completed runs (`--cap` changes this) and saves them as the snapshot.
  Run the same command **without** `--fetch` to rebuild the report from the saved snapshot; the result
  is byte-identical.
- Public repositories need no token. Set `GITHUB_TOKEN` for private repositories or many requests.
- Without `--config`, the report assumes GB compute and is labelled SCENARIO. Pass `--config` with your
  team configuration to apply your vetoes.

### 5.3 How to read the report

| Line | Meaning |
| :-- | :-- |
| Runs fetched / analysed / excluded | Runs read; runs replayed; runs left out (for example runs still awaiting approval) |
| Stage-1 eligible | Runs that were allowed to wait (not a pull request or protected branch) |
| Deferred | Runs the advisor would have deferred |
| Estimated carbon change vs run-now | Estimated change at 42.5 W, with the range for half and one-and-a-half times that power |
| Mean added delay | Average extra wait over **all** analysed runs |
| Failed-run TTFF p95 | How long the slowest 5% of failing runs would wait for their result; shown only with at least 20 failed runs |
| Run-now reasons | Why the other runs were not deferred (`pull_request`, `protected_branch`, `below_threshold`, `vetoed`, …) |

---

## 6. Team configuration reference

`.github/carbon-advisor.yml` has a closed schema: an unknown key is an error (fail-safe
`config_invalid`). No key can make the advisor defer more than the frozen policy allows.

| Key | Required | Default | Meaning |
| :-- | :-- | :-- | :-- |
| `compute_region` | yes | — | Where the CI compute runs, declared by you. Only `GB` gives carbon-based advice; anything else gives RUN NOW. Must equal the Action's `compute-region` input. |
| `enabled_workflows` | yes | — | Workflow files the advisor advises on; others get RUN NOW. |
| `extra_protected_branches` | no | `[]` | Extra branch-name patterns (glob) that always run now. |
| `urgent_markers` | no | `["[urgent]"]` | Commit-message text that vetoes a deferral. |
| `veto_events` | no | `[workflow_dispatch, schedule]` | Events that always run now. |
| `max_delay_hours` | no | `24` | Longest recommended delay; between 0 and 24. |
| `cold_start_run_now` | no | `true` | With no completed history, RUN NOW. |
| `history_cap` | no | `500` | Completed runs read for the estimate (1–1000). |
| `show_live_intensity` | no | `true` | Also show the live GB grid intensity (display only, never decides). |
| `grid_display_region` | no | none | A GB outward postcode (e.g. `EC1A`) or region id 1–17 for a regional live value (display only). |
| `redispatch` | no | `"off"` | Keep `off`; the automatic re-run of deferred builds was not built. |

---

## 7. Troubleshooting

| What you see | Why | What to do |
| :-- | :-- | :-- |
| RUN NOW, fail-safe `region_not_gb` | The declared region is not `GB` (expected on GitHub-hosted runners) | Declare `GB` only for GB compute, or add a `scenario: gb-hypothetical` job to see the GB answer |
| RUN NOW, fail-safe `region_mismatch` | The Action input and the config file declare different regions | Make `compute-region` and `compute_region` equal |
| RUN NOW, fail-safe `config_invalid` | Missing or invalid `.github/carbon-advisor.yml`, or the job did not check out `.github` | Check the file against Section 6 and keep the `sparse-checkout: .github` step |
| RUN NOW, fail-safe `invalid_request` | No region declared, or a malformed request | Set `compute-region` |
| RUN NOW, fail-safe `untrusted_event` | The workflow runs on `pull_request_target`, `workflow_run`, … | Use `push` and `pull_request` |
| RUN NOW, fail-safe `history_unavailable` | The run history could not be read | Grant `actions: read`; check for GitHub rate limits |
| RUN NOW, veto `cold_start` | No run of this workflow has completed yet | Wait for one run to finish, then push again |
| RUN NOW, `below_threshold` / "not worth deferring" | The workflow's runs take less than 480 s | Expected; short builds save almost no carbon |
| RUN NOW, already the cleanest slot | No cleaner hour in the next 24 h | Expected; try again at another time of day |
| RUN NOW, "not opted in" | The workflow file is not in `enabled_workflows` | Add it |

The full list of fail-safe codes is in [`context/p4_interface.md`](context/p4_interface.md) §6.1.

---

## 8. Limits you should know about

- **Recommendation only.** The advisor never pauses, cancels or fails a build.
- **Estimates, not measurements.** Carbon figures use a constant 42.5 W power model and the average GB
  intensity for each hour of the week.
- **Great Britain only.** It is the only evaluated grid, and the location is declared, never detected.
- **Thresholds from older data.** The 480 s threshold and 24 h window were fitted on Travis CI builds
  from 2011–2016 and are applied to GitHub Actions run times, which are a different measure.
- **Urgency is approximated** from pull-request status and branch names; manual and scheduled runs are
  vetoed by configuration.
- **What-If reports are demonstrations**, not research evidence.

For the research behind the advisor, its evaluation and how to reproduce every result, see
[`README.md`](README.md) and the result files in [`results/`](results/).

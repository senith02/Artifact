# results/p4 — prototype evidence (P4)

> **Demonstration and wiring evidence, not research evidence.** Nothing in this folder is an input to
> RQ1–RQ4, the evaluation report or the frozen policy (DL-033 R3-B10). Inputs marked *synthetic* are
> hand-made to exercise the advisor; the decisions they produce are **illustrative, not results**.

## P4-T1 (2026-10-04/05)

| path | what it is | produced by |
| :-- | :-- | :-- |
| `pytest_p4_t1.txt` | full test suite: 763 passed (645 baseline + 118 advisor/API tests) | `python -m pytest -p no:cacheprovider` (from `code/`) |
| `endpoint_check/` | real responses from the Carbon Intensity API and the GitHub REST API. They re-verify DL-033 R3-A7 on first use; GitHub captures are trimmed to run fields, with no actor data | `curl`, 2026-10-04T17:17:51Z (`captured_at.txt`) |
| `api_capture/` | real HTTP request/response pairs against `python -m api` on `127.0.0.1:8765`. Requests use *synthetic* history. Covers: eligible branch → DEFER RECOMMENDED, `main` → RUN NOW, `pull_request_target` → fail-safe RUN NOW; plus `/health`, the audit log and the server log | `ADVISOR_CONFIG=… ADVISOR_AUDIT_LOG=… ADVISOR_LIVE_CARBON=1 python -m api --port 8765`, then `curl -X POST …/decision` |
| `cli_real_github/` | the CLI fetching **real** completed-run history (read-only, no token) for the public `pallets/flask` `tests.yaml` workflow, in **scenario mode** (that repository's runners are not in GB). 100 runs fetched, 99 admitted, d̂ = 40 s → RUN NOW (below the 480 s threshold) | `python -m advisor advise --request … --config … --github --no-live …` |

The test fixtures in `code/tests/fixtures/p4/` are copies of the `endpoint_check/` captures.

## P4-T2 (2026-10-08)

The GitHub Action (`code/github-action/`) running on the public demo repository
[`senith02/carbon-advisor-demo`](https://github.com/senith02/carbon-advisor-demo). The Action is pinned there by
commit `7c19b9c319d807135d10f38ddf7df8c3f259bc3e`. Its build job runs a **synthetic** workload of about 9 minutes,
so any deferral shown follows from that chosen length (DL-036 §3).

| path | what it is | produced by |
| :-- | :-- | :-- |
| `pytest_p4_t2.txt` | full test suite: 789 passed (763 + 26 Action tests) | `python -m pytest -p no:cacheprovider` (from `code/`) |
| `action_wiring/` | `github-action/run_advisor.py` run end to end in a **clean venv** holding only the 12-package subset. The runner environment is *simulated*, and the history is real and read-only (`pallets/flask` `tests.yaml`, scenario mode) | scratch venv + `pip install --no-deps --only-binary=:all: -r github-action/requirements.action.txt` |
| `demo_runs/` | seven **real** CI runs: each advisory job's request, response, Step Summary copy and audit record (workflow artifacts), plus `runs.json` (links, job and step conclusions), `combined_audit.jsonl`, `validator_result.json` (0 violations) and `decisions.md` (the table) | `python scripts/collect_demo_runs.py --repo senith02/carbon-advisor-demo --out ../results/p4/demo_runs --token-from-git-credential <7 run ids>` (`demo_runs/collect_run.log`) |

The GB `DEFER RECOMMENDED` comes from labelled **scenario mode** (DL-033 R3-K option b). The real location of every
run is a GitHub-hosted runner, declared `GITHUB-HOSTED`, which gives RUN NOW (fail-safe `region_not_gb`; DL-036 §1).

## P4-T3 (2026-10-08)

The Repo What-If Report (`code/advisor/whatif.py`, `whatif_html.py`). For each repository, it replays
the last ≤ 500 completed runs of one workflow through the same `advise()`. The observed duration is
used only after each decision, for estimated carbon and delay (DL-037).

| path | what it is | produced by |
| :-- | :-- | :-- |
| `whatif_selection.md` | the public-repository selection rule, committed **before** any report (`e71effc`) | author decision 2026-10-08 (DL-037 §1) |
| `whatif/selection_result.json` | the rule applied: every candidate checked, workflow run counts, the selection | `python scripts/select_whatif_repos.py --token-from-git-credential --out ../results/p4/whatif/selection_result.json` |
| `whatif/<owner>__<repo>/report.{json,md,html}` | one report per selected repository plus the demo repository. Aggregates only; the HTML is static, with inline SVG | `python -m advisor whatif --repo R --workflow W --fetch --snapshot artifacts/whatif_snapshots/<slug>.json --out ../results/p4/whatif/<slug>` |
| `whatif/determinism.json` | every report regenerated twice from its saved snapshot; JSON, HTML and Markdown byte-identical | the same command without `--fetch` |
| `whatif/duration_check.md` | wall-clock vs the timing endpoint on 18 runs, including multi-day outliers: identical | `GitHubClient.run_duration_ms` |
| `pytest_p4_t3.txt` | full test suite: 807 passed | `python -m pytest -p no:cacheprovider` (from `code/`) |

The per-run snapshots stay local, under `code/artifacts/whatif_snapshots/` (gitignored). Each report
pins its snapshot by sha256.

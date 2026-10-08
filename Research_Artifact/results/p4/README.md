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

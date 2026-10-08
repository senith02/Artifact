# P4 interface reference — the carbon-deferral advisor

> Written for P4-T1 S1, **before any advisor code existed**. It turns DL-033 revision 3 (R3-B/C/I/J/K)
> and DL-035 into exact schemas. If this file and the decision log disagree, the decision log wins
> (it is governance; this file is context).

## 1. What the advisor is

The advisor is a thin layer over the frozen research core. For one CI run it answers **RUN NOW** or
**DEFER RECOMMENDED**, and gives the reason.

- **It contains no decision logic of its own.** Every decision is `scheduler_core.policy.decide()`
  under `policy_spec.yaml`, loaded with `require_fitted=True`.
- **`d̂` comes from the frozen estimator's own functions:** `causal_project_history(...,
  availability="completed")` then `predict_4b(min_history=1)`.
- **Its additions can only make the answer safer.** It validates input, applies team vetoes that can
  only turn a deferral into RUN NOW, labels outputs and keeps an audit trail.

## 2. Frozen pins (`advisor/frozen.py`)

| artifact | path (under `code/`) | pin |
| :-- | :-- | :-- |
| policy spec | `scheduler_core/config/policy_spec.yaml` | sha256 (LF-normalised) `e43b004d3df0a680d5e5519f8ddceb54ffd2861f6eb3363c5c2ec7d3e45c8cf8` |
| GB hour-of-week profile | `data/carbon/hour_of_week_profile.csv` | sha256 (LF-normalised) `2af9992ee46c1d752df1e5b58e945e02d309a2234b2983c565ccf119548cf40d` |
| duration estimator | `artifacts/duration_estimator.joblib` | fit id `1088d5546f47ff12` and raw sha256 `ccc5bb2431404f416ca9f23eaeab7d97ddd7a2723404cba85cd1254f01241fc0` |

"LF-normalised" means the hash is taken over the bytes with every CRLF replaced by LF (DL-035 §2).
Any mismatch means **fail safe**.

## 3. Request (closed schema; unknown keys are rejected)

| field | type | required | rule |
| :-- | :-- | :-: | :-- |
| `repository` | str | ✓ | `^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$` |
| `workflow` | str | ✓ | workflow file name, `^[A-Za-z0-9._-]{1,100}\.ya?ml$` |
| `event` | str | ✓ | trusted: `push`, `pull_request`, `workflow_dispatch`, `schedule`; anything else is refused (§6) |
| `ref_type` | str | ✓ | `branch` or `tag` |
| `branch` | str | ✓ | 1–255 chars, no control characters (it is data, never interpolated) |
| `is_pr` | bool | ✓ | must agree with `event`: true ⇔ `pull_request` |
| `arrival_utc` | str | ✓ | ISO-8601 with an offset or `Z`; not more than 5 minutes in the future |
| `compute_region` | str | ✓ | `^[A-Za-z0-9-]{2,32}$`; only `GB` is evaluated |
| `scenario` | str | – | `gb-hypothetical` only, and only with `compute_region: GB` (R3-K, DL-035 §3d) |
| `deadline_utc` | str | – | ISO-8601; must be after `arrival_utc` |
| `head_sha` | str | – | 40 lowercase hex |
| `run_id` | int | – | ≥ 1 |
| `run_attempt` | int | – | ≥ 1 |
| `redispatch_key` | str | – | set only by the re-dispatch reference workflow; ≤ 200 chars |
| `head_commit_message` | str | – | ≤ 4,096 chars; read only for urgency markers |
| `repo_language` | str | – | GitHub's primary language; feeds the ④b cold-start ladder (DL-035 §3a) |
| `history` | list | – | ≤ `history_cap` entries (§4). If absent, the CLI may fetch history from GitHub; the API never does (DL-035 §3c) |

**Rejected by name (raises, never ignored):**
- every column `features.is_blocklisted` reports (`tr_duration`, `tr_status`, `tr_log_*`, …);
- the SE feature names in `features.FAMILIES`, except `is_pr`, which is also the Stage-1 `gh_is_pr`
  input (27 names; DL-035 §3e);
- `p_hat`;
- `duration_s` / `conclusion` / `status` at the top level (the current run's own outcome).

## 4. History entry (one completed earlier run)

```json
{"run_id": 123, "workflow": "ci.yml", "status": "completed", "conclusion": "success",
 "created_at": "2026-10-01T09:58:02Z", "run_started_at": "2026-10-01T09:58:10Z",
 "updated_at": "2026-10-01T10:09:40Z", "duration_s": 690.0, "duration_source": "wallclock"}
```

**Admissible only if all of these hold** (R3-B4):
- `status == "completed"`;
- `conclusion ∈ {success, failure}`;
- `workflow` equals the request's workflow;
- `run_id` differs from the request's;
- `duration_s > 0`;
- `max(updated_at, run_started_at + duration_s) < arrival_utc`.

Everything else is dropped and counted by reason.

**Duration source** (DL-035 §3b): `wallclock` = `updated_at − run_started_at` (the default);
`timing` = `run_duration_ms / 1000`, used only within an explicit lookup budget.

## 5. Team config (`.github/carbon-advisor.yml`; closed schema; `yaml.safe_load`)

| key | type | default | meaning |
| :-- | :-- | :-- | :-- |
| `compute_region` | str | **required** | must equal the request's `compute_region` |
| `enabled_workflows` | list[str] | **required, non-empty** | workflows the advisor advises; others get RUN NOW (not opted in) |
| `extra_protected_branches` | list[str] | `[]` | `fnmatch` globs; a match vetoes a deferral |
| `urgent_markers` | list[str] | `["[urgent]"]` | a substring in the commit message vetoes a deferral |
| `veto_events` | list[str] | `["workflow_dispatch", "schedule"]` | these events veto a deferral |
| `max_delay_hours` | number | `24` | 0 < x ≤ 24; a longer recommended delay is vetoed |
| `cold_start_run_now` | bool | `true` | no completed history → RUN NOW (R3-J1) |
| `history_cap` | int | `500` | 1–1,000 completed runs read (design default, not a result) |
| `grid_display_region` | str/int | – | outward postcode or region id 1–17; regional intensity is display only (R3-J2) |
| `show_live_intensity` | bool | `true` | display the live national GB value |
| `redispatch` | str | `off` | `off` or `reference-demo` (R3-C10) |

## 6. Order of operations and outcomes

1. Validate the request.
2. Check the event is trusted.
3. Validate the config, then check opt-in.
4. Check the region (and scenario).
5. Check the frozen hashes.
6. History: given or fetched, then filtered.
7. `d̂`.
8. `decide()`.
9. Vetoes.
10. Render, then audit.

`outcome_kind` is one of:
- **`policy`:** `decide()`'s answer stands.
- **`veto`:** `decide()` said defer, and a team or safety rule turned it into RUN NOW.
- **`fail_safe`:** an input or dependency failed, so RUN NOW.
- **`not_advised`:** the workflow is not opted in, so RUN NOW.

### 6.1 Fail-safe matrix (every row gives RUN NOW and `fail_safe: true`)

| code | trigger |
| :-- | :-- |
| `invalid_request` | schema violation, a rejected field, bad types, `is_pr`/`event` disagreement |
| `untrusted_event` | an event outside the trusted list (e.g. `pull_request_target`, `workflow_run`) |
| `config_invalid` | a missing or invalid team config, or `max_delay_hours` > 24 |
| `region_mismatch` | the request and config `compute_region` differ |
| `region_not_gb` | `compute_region` is not `GB` (e.g. `US-EAST`, R3-J3) — no GB carbon figures shown |
| `scenario_invalid` | `scenario` set to an unknown value, or without `compute_region: GB` |
| `deadline_invalid` | `deadline_utc` unparseable or not after the arrival |
| `arrival_in_future` | `arrival_utc` more than 5 minutes ahead of the clock |
| `spec_unavailable` | spec missing, hash mismatch, or refused by `require_fitted` |
| `profile_unavailable` | profile missing or hash mismatch |
| `estimator_unavailable` | estimator missing, fit-id or hash mismatch |
| `history_unavailable` | GitHub error after retries, rate limit exhausted, timeout, malformed records |
| `api_unreachable` | CLI in API mode and the API cannot be reached |
| `internal_error` | any unhandled exception |

**Cold start is not a fail-safe.** It is the `cold_start` veto (§6.2), and it is reported with its
rung.

### 6.2 Veto rules (they only act on a `decide()` deferral; all matching rules are listed)

`redispatched_run`, `cold_start`, `tag_ref`, `event_vetoed`, `extra_protected_branch`,
`urgent_marker`, `exceeds_deadline`, `exceeds_max_delay`.

## 7. Response

```json
{
  "action": "defer", "display": "DEFER RECOMMENDED", "outcome_kind": "policy",
  "fail_safe": false, "fail_safe_code": null, "vetoes": [],
  "policy_action": "defer", "reason": "…decide() reason… | null statement",
  "defer_until": {"offset_hours": 17, "slot": 155, "dow": 6, "hour": 11,
                  "utc": "2026-10-04T11:00:00+00:00"},
  "delay_hours": 17.0, "window_hours": 24.0,
  "stage1_rule": "push_to_unprotected_branch", "eligible": true,
  "d_hat_seconds": 840.0, "d_hat_rung": "project", "n_history": 37,
  "history_dropped": {"in_progress_or_queued": 1, "finished_after_arrival": 2},
  "grid_gco2_profile_now": 172.914, "grid_gco2_profile_scheduled": 92.24,
  "est_carbon_change_pct": -46.66,
  "grid_gco2_live_national": 168.0, "grid_gco2_live_regional": null,
  "compute_region_assumed": "GB", "scenario": null,
  "policy_path": "duration_only_fallback",
  "spec_sha256": "e43b…", "profile_sha256": "2af9…", "estimator_fit_id": "1088d5546f47ff12",
  "advisor_version": "0.1.0",
  "statements": ["Recommendation only — …", "…"]
}
```

*(Field values above are illustrative — not a real result.)*

- `display` ∈ `RUN NOW`, `DEFER RECOMMENDED`, with ` (scenario)` appended in scenario mode.
- `est_carbon_change_pct` is the estimate for `d̂` at the scheduled slot against the arrival slot,
  under the energy model. It is null unless the final action is `defer`.
- **The null statement is always in `reason`:** *"SE characteristics were evaluated and not admitted
  (results/p1/incremental_value.md; results/p3/evaluation_report.md) — this decision uses branch/PR
  status and a duration estimate from completed history only."*

## 8. Surfaces

- **CLI** (`code/` as the working directory):

  ```
  python -m advisor advise --request req.json --config cfg.yml
                           [--history-file h.json | --github]
                           [--audit-log log.jsonl] [--json-out out.json]
                           [--summary-out summary.md] [--api-url http://127.0.0.1:8000]
  ```

  It always exits 0 after writing a decision, including a fail-safe one. Exit 2 is reserved for a
  usage error that leaves no decision.
- **API:** `python -m api` binds to `127.0.0.1:8000` by default. Binding to a non-loopback host
  requires `ADVISOR_API_TOKEN`, which clients then send as `X-Advisor-Token`.
  - `POST /decision`: request body as §3. The response is §7, with status 200 even when it fails
    safe. Status 413 above a 256 KiB body; 401 for a missing or wrong token when one is required.
  - `GET /health`: version and the frozen pins.
  - The team config is loaded at startup from `ADVISOR_CONFIG`.
- **Audit record (JSON Lines):**
  - **Fields:** every §7 field, plus `audit_ts`, `idempotency_key`
    (`repository|workflow|head_sha|run_attempt`), `duplicate`, the validated inputs, and `gh_is_pr` /
    `git_branch` so that `replay/validate_invariants.py` can audit the log.
  - **Never logged:** tokens, actor names, emails.

## 9. External endpoints (re-verified on the first real call, P4-T1)

- `GET https://api.github.com/repos/{o}/{r}/actions/workflows/{file}/runs?status=completed&per_page=100&page=N`
- `GET https://api.github.com/repos/{o}/{r}/actions/runs/{id}/timing` (budgeted)
- `GET https://api.github.com/repos/{o}/{r}` (for `language`)
- `GET https://api.carbonintensity.org.uk/intensity` (national, display only)
- `GET https://api.carbonintensity.org.uk/regional/postcode/{outward}` and `…/regional/regionid/{id}`
  (display only)

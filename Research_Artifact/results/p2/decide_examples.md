# Five worked `decide()` outputs (P2-T3)

Generated `2026-09-22T05:29:36+00:00` by `PYTHONPATH=. python scripts/report_decide_examples.py`.
Machine-readable twin: `decide_examples.json`. Test evidence: `pytest_p2_t3.txt`.

> **⚠ Wiring examples, not results.** These run against the **bootstrap** spec
> (`provenance.fitted: false`), whose `d_threshold_seconds` is a deliberately degenerate
> 0.0 and whose `w_max_hours` is the DL-008 protocol default. No number here reflects a
> fitted policy. P2-T5 fits the real `policy_spec.yaml`; P3 produces the real numbers.
> The bootstrap was verified **refused** under the default `require_fitted=True` before
> these examples were generated (DL-022 §4).

> **Provenance.** Real P0-T3 carbon profile (168/168 slots observed). **0 dataset rows read** — the five builds are hand-constructed to exercise named
> branches; no split was opened.

## E1 — Stage 1 refuses a PR build — Stage 2 is never consulted

**Path:** `duration_only_fallback` · **Arrival:** Wed 18:00 · **`gh_is_pr`:** `True` · **`git_branch`:** `feature/login`

| Field | Value |
| :-- | :-- |
| `action` | **`run_now`** |
| `defer_until` | `None` |
| `grid_gCO2_now` | 172.9140 gCO₂/kWh |
| `grid_gCO2_scheduled` | 172.9140 gCO₂/kWh |
| `eligible` / `stage1_rule` | `False` / `pr_blocking` |
| `d_hat_seconds` | `None` |
| `p_hat` | `None` |
| `window_hours` | 0.0000 |
| `delay_hours` | 0.0000 |
| `spec_fitted` | `False` |

**`reason`**

```text
stage1[primary]: NOT deferrable (pr_blocking) — gh_is_pr is true; §3.4 class (a) pull-request-blocking. The dataset does not record whether the check was a required status check, so all PR builds are treated as blocking (DL-020 §4). Stage 2 not consulted. Running now at slot 66 (Wed 18:00, 172.9140 gCO2/kWh).
```

## E2 — Stage 1 refuses a push to a protected branch (named rule)

**Path:** `duration_only_fallback` · **Arrival:** Wed 18:00 · **`gh_is_pr`:** `False` · **`git_branch`:** `master`

| Field | Value |
| :-- | :-- |
| `action` | **`run_now`** |
| `defer_until` | `None` |
| `grid_gCO2_now` | 172.9140 gCO₂/kWh |
| `grid_gCO2_scheduled` | 172.9140 gCO₂/kWh |
| `eligible` / `stage1_rule` | `False` / `protected:mainline` |
| `d_hat_seconds` | `None` |
| `p_hat` | `None` |
| `window_hours` | 0.0000 |
| `delay_hours` | 0.0000 |
| `spec_fitted` | `False` |

**`reason`**

```text
stage1[primary]: NOT deferrable (protected:mainline) — git_branch='master' matches the frozen pattern 'mainline' ((?:master|main|trunk|default)), approximating §3.4 class (c) production-branch. Stage 2 not consulted. Running now at slot 66 (Wed 18:00, 172.9140 gCO2/kWh).
```

## E3 — deferrable + duration-only path -> defers to the greenest reachable slot

**Path:** `duration_only_fallback` · **Arrival:** Wed 18:00 · **`gh_is_pr`:** `False` · **`git_branch`:** `feature/widget`

| Field | Value |
| :-- | :-- |
| `action` | **`defer`** |
| `defer_until` | `{'offset_hours': 8, 'slot': 74, 'dow': 3, 'hour': 2}` |
| `grid_gCO2_now` | 172.9140 gCO₂/kWh |
| `grid_gCO2_scheduled` | 113.1730 gCO₂/kWh |
| `eligible` / `stage1_rule` | `True` / `push_to_unprotected_branch` |
| `d_hat_seconds` | `5400.0` |
| `p_hat` | `None` |
| `window_hours` | 24.0000 |
| `delay_hours` | 8.0000 |
| `spec_fitted` | `False` |

**`reason`**

```text
stage1[primary]: deferrable (push_to_unprotected_branch). stage2[duration_only_fallback]: d_hat=5400.0s >= d_threshold=0.0s, window=24.0000h (flat w_max=24.0000). Greenest reachable slot is 74 (Thu 02:00, 113.1730 gCO2/kWh) at +8h, vs 172.9140 gCO2/kWh now -> deferring 8h.
```

## E4 — deferrable but d_hat below d_threshold -> runs now (A1.6 selectivity)

**Path:** `duration_only_fallback` · **Arrival:** Wed 18:00 · **`gh_is_pr`:** `False` · **`git_branch`:** `feature/typo-fix`

| Field | Value |
| :-- | :-- |
| `action` | **`run_now`** |
| `defer_until` | `None` |
| `grid_gCO2_now` | 172.9140 gCO₂/kWh |
| `grid_gCO2_scheduled` | 172.9140 gCO₂/kWh |
| `eligible` / `stage1_rule` | `True` / `push_to_unprotected_branch` |
| `d_hat_seconds` | `90.0` |
| `p_hat` | `None` |
| `window_hours` | 0.0000 |
| `delay_hours` | 0.0000 |
| `spec_fitted` | `False` |

**`reason`**

```text
stage1[primary]: deferrable (push_to_unprotected_branch). stage2[duration_only_fallback]: d_hat=90.0s < d_threshold=7200.0s -> not worth deferring. Running now at slot 66 (Wed 18:00, 172.9140 gCO2/kWh).
```

## E5 — SE-informed path -> the §7 window shrinks with p_hat, shortening the search

**Path:** `se_informed` · **Arrival:** Wed 18:00 · **`gh_is_pr`:** `False` · **`git_branch`:** `feature/widget`

| Field | Value |
| :-- | :-- |
| `action` | **`defer`** |
| `defer_until` | `{'offset_hours': 4, 'slot': 70, 'dow': 2, 'hour': 22}` |
| `grid_gCO2_now` | 172.9140 gCO₂/kWh |
| `grid_gCO2_scheduled` | 123.3620 gCO₂/kWh |
| `eligible` / `stage1_rule` | `True` / `push_to_unprotected_branch` |
| `d_hat_seconds` | `5400.0` |
| `p_hat` | `0.8` |
| `window_hours` | 4.8000 |
| `delay_hours` | 4.0000 |
| `spec_fitted` | `False` |

**`reason`**

```text
stage1[primary]: deferrable (push_to_unprotected_branch). stage2[se_informed(window_form=linear, admitted=['F1(illustrative — no family was admitted)'])]: d_hat=5400.0s >= d_threshold=0.0s, window=4.8000h = w_max 24.0000 * (1 - p_hat 0.800000). Greenest reachable slot is 70 (Wed 22:00, 123.3620 gCO2/kWh) at +4h, vs 172.9140 gCO2/kWh now -> deferring 4h.
```

## What these five demonstrate

- **E1, E2** — Stage 1 returns before Stage 2 is consulted. The reason string says so
  explicitly (`Stage 2 not consulted`), and `d_hat_seconds` is `null` in the record
  because the estimate was never read. This is frozen invariant 1 as control flow.
- **E3** — the deferral itself: the greenest slot reachable inside the window, with the
  before/after intensities both recorded so the decision can be audited without rerunning it.
- **E4** — A1.6 selectivity: a short build is *not* worth deferring, because it pays the
  full latency cost for a negligible carbon gain.
- **E5** — the §7 / A1.8 window form: a high `p_hat` shrinks the window, which shortens the
  slot search. On present evidence (`results/p1/admission.json`, zero families admitted)
  this path is implemented and tested but is **not** the path expected to ship.

Every `reason` above names the gate rule, the path taken, the driving values, the window
and the chosen slot — the S2 contract — so a decision log is readable without this module.

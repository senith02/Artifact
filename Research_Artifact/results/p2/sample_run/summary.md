# P2-T4 — replay simulator sample run (calibration)

> ⚠ **BOOTSTRAP-DERIVED — P2-T4 wiring check, driven by policy_spec.bootstrap.yaml (provenance.fitted: false). Not a result; no number here is a finding (DL-022, DL-023 §4).**

> The bootstrap spec's `d_threshold_seconds` is a degenerate 0.0 and its `w_max_hours` is the DL-008 default; the sweep grid overrides both per point, but the spec is still **unfitted**, so this is a check that the pipeline runs end to end, is deterministic and never defers a non-deferrable build — not an estimate of any strategy's effect.

## What was replayed

- **12,000** builds, seeded uniform sample (seed 42) of the **138,687** analytic calibration builds / 150 projects (DL-023 §4). Sample spans 144 projects, 2011-06-13 16:44:42+00:00 → 2016-08-31 23:32:31+00:00.
- Test split **closed**: job rows of test projects were discarded chunk by chunk, before any aggregation, join or feature step — 139,163 distinct raw test build ids (counted *before* the analytic funnel, so larger than the 138,693 analytic test builds in `results/p1/splits_summary.md`). Train builds are not needed and were dropped too.
- Sample failure rate 29.1667%; unaccountable builds (no usable observed duration, DL-023 §3): **6**, excluded identically from every carbon/TTFF aggregate.
- 102 settings (strategy × grid point) × 12,000 builds = **1,224,000** records.

## Checks (the gate evidence)

| check | result |
| :-- | :-- |
| every strategy × grid point saw the identical build set, in order | PASS (102 settings × 12,000 builds) |
| independent validator: non-deferrable builds deferred (all rows, all strategies) | **0** of 117,450 deferrals over 1,224,000 rows — PASS |
| independent validator: non-deferrable builds skipped by ⑥ | **0** of 2,401 skips — PASS |
| validator self-test (hand-crafted violating fixture must be caught) | PASS |
| DL-023 §1 identity `5_equals_4b_at_every_point` | holds |
| DL-023 §1 identity `3_equals_4b_at_d0` | holds |
| DL-023 §1 identity `6_at_tau0_equals_1_static_actions` | holds |

Determinism (byte-identical rerun) is recorded separately in `determinism.json`.

## Aggregates per setting — bootstrap-derived, wiring only

Rows shown: every setting of ①②③⑥, and ④a/④b/⑤ at `w_max = 24 h` (all 102 settings are in `summary.csv`). Carbon uses P_avg = 42.5 W (DL-021). p95 = numpy linear-interpolation percentile.

| setting | deferred | skipped | gCO₂e / 1k builds | Δ vs ① | latency p95 h (deferred) | TTFF p95 h (failed) | missed failures | top-5 slot share |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| `1_static` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `2_blanket_carbon_aware__d0__w167` | 2,643 | 0 | 3,751.7097 | -6.52% | 148.90 | 131.01 | 0 | 0.2601 |
| `3_eligibility_only__d0__w6` | 2,127 | 0 | 3,907.9822 | -2.62% | 6.00 | 6.59 | 0 | 0.0825 |
| `3_eligibility_only__d0__w12` | 2,505 | 0 | 3,881.6618 | -3.28% | 12.00 | 12.02 | 0 | 0.1288 |
| `3_eligibility_only__d0__w24` | 2,581 | 0 | 3,861.6343 | -3.78% | 24.00 | 21.11 | 0 | 0.1722 |
| `4a_duration_estimator__d0__w24` | 2,581 | 0 | 3,861.6343 | -3.78% | 24.00 | 21.11 | 0 | 0.1722 |
| `4a_duration_estimator__d60__w24` | 2,507 | 0 | 3,863.1039 | -3.74% | 24.00 | 21.05 | 0 | 0.1689 |
| `4a_duration_estimator__d120__w24` | 2,426 | 0 | 3,864.2391 | -3.71% | 24.00 | 21.04 | 0 | 0.1648 |
| `4a_duration_estimator__d240__w24` | 2,190 | 0 | 3,869.2762 | -3.59% | 24.00 | 20.43 | 0 | 0.1523 |
| `4a_duration_estimator__d480__w24` | 1,499 | 0 | 3,877.6011 | -3.38% | 24.00 | 19.15 | 0 | 0.1129 |
| `4a_duration_estimator__d960__w24` | 839 | 0 | 3,899.0602 | -2.85% | 24.00 | 14.77 | 0 | 0.0718 |
| `4a_duration_estimator__d1920__w24` | 236 | 0 | 3,972.4468 | -1.02% | 24.00 | 6.25 | 0 | 0.0542 |
| `4a_duration_estimator__d3840__w24` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `4a_duration_estimator__d7680__w24` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `4a_duration_estimator__d15360__w24` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `4b_duration_prior__d0__w24` | 2,581 | 0 | 3,861.6343 | -3.78% | 24.00 | 21.11 | 0 | 0.1722 |
| `4b_duration_prior__d60__w24` | 2,475 | 0 | 3,861.8940 | -3.77% | 24.00 | 21.06 | 0 | 0.1668 |
| `4b_duration_prior__d120__w24` | 2,387 | 0 | 3,862.3464 | -3.76% | 24.00 | 21.06 | 0 | 0.1623 |
| `4b_duration_prior__d240__w24` | 1,842 | 0 | 3,866.4563 | -3.66% | 24.00 | 20.70 | 0 | 0.1305 |
| `4b_duration_prior__d480__w24` | 1,385 | 0 | 3,873.7876 | -3.48% | 24.00 | 19.20 | 0 | 0.1032 |
| `4b_duration_prior__d960__w24` | 905 | 0 | 3,884.9268 | -3.20% | 24.00 | 15.10 | 0 | 0.0745 |
| `4b_duration_prior__d1920__w24` | 669 | 0 | 3,896.5452 | -2.91% | 24.00 | 11.38 | 0 | 0.0638 |
| `4b_duration_prior__d3840__w24` | 513 | 0 | 3,909.8379 | -2.58% | 24.00 | 7.91 | 0 | 0.0586 |
| `4b_duration_prior__d7680__w24` | 343 | 0 | 3,937.2291 | -1.90% | 24.00 | 6.97 | 0 | 0.0552 |
| `4b_duration_prior__d15360__w24` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `5_se_informed_policy__d0__w24` | 2,581 | 0 | 3,861.6343 | -3.78% | 24.00 | 21.11 | 0 | 0.1722 |
| `5_se_informed_policy__d60__w24` | 2,475 | 0 | 3,861.8940 | -3.77% | 24.00 | 21.06 | 0 | 0.1668 |
| `5_se_informed_policy__d120__w24` | 2,387 | 0 | 3,862.3464 | -3.76% | 24.00 | 21.06 | 0 | 0.1623 |
| `5_se_informed_policy__d240__w24` | 1,842 | 0 | 3,866.4563 | -3.66% | 24.00 | 20.70 | 0 | 0.1305 |
| `5_se_informed_policy__d480__w24` | 1,385 | 0 | 3,873.7876 | -3.48% | 24.00 | 19.20 | 0 | 0.1032 |
| `5_se_informed_policy__d960__w24` | 905 | 0 | 3,884.9268 | -3.20% | 24.00 | 15.10 | 0 | 0.0745 |
| `5_se_informed_policy__d1920__w24` | 669 | 0 | 3,896.5452 | -2.91% | 24.00 | 11.38 | 0 | 0.0638 |
| `5_se_informed_policy__d3840__w24` | 513 | 0 | 3,909.8379 | -2.58% | 24.00 | 7.91 | 0 | 0.0586 |
| `5_se_informed_policy__d7680__w24` | 343 | 0 | 3,937.2291 | -1.90% | 24.00 | 6.97 | 0 | 0.0552 |
| `5_se_informed_policy__d15360__w24` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `6_risk_only_skip__t0` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `6_risk_only_skip__t0.05` | 0 | 0 | 4,013.2856 | 0.00% | — | 5.49 | 0 | 0.0559 |
| `6_risk_only_skip__t0.1` | 0 | 4 | 4,011.5228 | -0.04% | — | 5.49 | 1 | 0.0559 |
| `6_risk_only_skip__t0.15` | 0 | 8 | 4,010.0078 | -0.08% | — | 5.49 | 1 | 0.0560 |
| `6_risk_only_skip__t0.2` | 0 | 19 | 4,003.4289 | -0.25% | — | 5.49 | 2 | 0.0560 |
| `6_risk_only_skip__t0.25` | 0 | 48 | 3,982.0052 | -0.78% | — | 5.50 | 7 | 0.0561 |
| `6_risk_only_skip__t0.3` | 0 | 2,322 | 3,229.0402 | -19.54% | — | 5.91 | 778 | 0.0573 |

**How to read this.** ⑤ equals ④b at every point because the bootstrap spec is on the duration-only path (DL-023 §1) — that is the null path's operational meaning, not a comparison. ⑥'s carbon falls because skipped builds never run; read it beside *missed failures*. None of these magnitudes is interpretable until P2-T5 fits the spec and P3 replays the test split.

## Provenance

- Command: `PYTHONPATH=. python scripts/run_replay.py --allow-unfitted-spec --fresh --parts-dir C:/Users/senit/AppData/Local/Temp/claude/c--Users-senit-Desktop-Projects-Research-Artifact/1c79e87f-2eb1-4a18-bf40-de4faab0280f/scratchpad/parts_b --compare-with C:/Users/senit/AppData/Local/Temp/claude/c--Users-senit-Desktop-Projects-Research-Artifact/1c79e87f-2eb1-4a18-bf40-de4faab0280f/scratchpad/run_a`
- Spec: `C:\Users\senit\Desktop\Projects\Research\Artifact\Research_Artifact\code\scheduler_core\config\policy_spec.bootstrap.yaml` (fitted: False)
- Grid: `replay/sweep_grid.json` sha256 `151a4b360a70d96f…` (DL-023 §2)
- d̂: frozen fit id `1088d5546f47ff12`, primary form 4b; p̂: `xgboost:full` fit id `65fd81b1e952fd72`
- Run fingerprint `6fa13fb9f3133599…`; runtime 437.1s
- sha256 of every output: `manifest.json`

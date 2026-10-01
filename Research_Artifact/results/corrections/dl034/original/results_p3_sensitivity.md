# P3-T4 — sensitivity analyses: does any sweep change a verdict?

> Assembled by `PYTHONPATH=. python scripts/sensitivity_analysis.py --summary` from `results/p3/sensitivity/*.json`. Every number comes from those runs (R1). **Test split**, frozen models, frozen spec. Nothing refitted. Verdict definitions: DL-030 §1 — **V1** model-level admitted set (×1) · **V2** ⑤ beats both ④a and ④b (×1) · **V3** ④b (≡ ⑤) over ④a (×1) · **V4** the eight-class sign pattern of ⑤ vs ①, ②, ③, ④a on carbon and TTFF p95.

## Verdict flips

- **S-b w12 — `W_max` = 12 h (⑤, ④a, ③ at the same W)**: V1 n/a · V2 n/a (frontier spans W) · V3 n/a (frontier spans W) · V4 **FLIPS**. ⑤−④a TTFF p95: n.s. → lower
- **S-e late — Temporal: late test builds (boundary 2015-03-28)**: V1 stable ({F1}) · V2 stable · V3 **FLIPS** · V4 n/a. 76,038 builds

## Summary table

| sweep | what changes | V1 | V2 | V3 | V4 | V3 area (pp·h) [95% CI] | note |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| baseline | Baseline (P3-T1 / P3-T2 / P3-T3 as frozen) | {F1} | no | yes | reference | +2.4308 [+1.7358, +2.5684] |  |
| S-a | Deferrable fraction: stage-1 `protected_includes_integration` | n/a | stable | stable | stable | +2.2222 [+1.7189, +2.5607] | eligible share 14.02%;  |
| S-b w6 | `W_max` = 6 h (⑤, ④a, ③ at the same W) | n/a | n/a (frontier spans W) | n/a (frontier spans W) | stable | — |  |
| S-b w12 | `W_max` = 12 h (⑤, ④a, ③ at the same W) | n/a | n/a (frontier spans W) | n/a (frontier spans W) | **FLIPS** | — | ⑤−④a TTFF p95: n.s. → lower |
| S-b w24 | `W_max` = 24 h (⑤, ④a, ③ at the same W) | n/a | n/a (frontier spans W) | n/a (frontier spans W) | stable | — |  |
| S-b banded | Banded window shape | n/a | n/a | n/a | n/a | — | not applicable — the banded shape maps a failure probability to a window, which exists only on the risk-adjusted path; the frozen spec admits no family (DL-030 §2 S-b) |
| S-c x0.5 | Energy `P_avg` ×0.5 | n/a | stable | stable | stable | +2.4308 [+1.7358, +2.5684] | P_avg 21.25 W; carbon/1k at the frozen point 1389.4 g |
| S-c x1.5 | Energy `P_avg` ×1.5 | n/a | stable | stable | stable | +2.4308 [+1.7358, +2.5684] | P_avg 63.75 W; carbon/1k at the frozen point 4168.3 g |
| S-d | `n_jobs`-scaled energy | n/a | stable | stable | stable | +5.9026 [+4.4703, +6.6558] | jobs per build: mean 4.58, median 3, single-job share 35.1% |
| S-e early | Temporal: early test builds (boundary 2015-03-28) | stable ({F1}) | stable | stable | n/a | +0.7500 [+0.5305, +1.1719] | 62,655 builds |
| S-e late | Temporal: late test builds (boundary 2015-03-28) | stable ({F1}) | stable | **FLIPS** | n/a | +3.5694 [+1.7615, +4.3448] | 76,038 builds |
| S-f | Second grid profile (DL-027 §2) | n/a | not run | not run | not run | — | not run — no qualifying data (DL-027 §2, DL-032). CAISO peak/trough 1.8669 vs UK 1.8746 (criterion c fails); Germany: no account-free intensity series |
| S-g | Cold-start builds excluded | stable ({F1}) | stable | stable | n/a | +2.4485 [+1.7681, +2.5807] | 174 builds excluded |
| S-h | ④b trailing-50 control form (sensitivity of the control) | n/a | stable | stable | n/a | +2.4308 [+1.7358, +2.5684] | trailing vs ④b area +0.3538 [+0.2370, +0.7650]; trailing vs ④a area +2.8195 [+2.1823, +3.1153] |
| S-i | Floor ×0.5 / ×2 and ④b as the null (collected from P3-T1/P3-T3) | ×0.5 {F1} · ×2 {∅} | stable (no at every floor) | stable (yes at every floor) | n/a | — | V1 at ×2 is the known floor-sensitivity of F1 reported in P3-T1 |

![V3 across sweeps](figures/sensitivity_v3_area.png)

## V4 baseline, recomputed from the P3-T2 parts

Classes match P3-T2's stored paired bootstrap: **True**.

| pair | metric | Δ [95% CI] | class |
| :-- | :-- | :-- | :-- |
| 5 − 1 | carbon_per_1000_builds_g | -70.6781 [-78.5213, -64.8966] | lower |
| 5 − 1 | ttff_p95_h_failed | +12.2140 [+11.6682, +12.5909] | higher |
| 5 − 2 | carbon_per_1000_builds_g | +62.7031 [+59.9426, +66.0656] | higher |
| 5 − 2 | ttff_p95_h_failed | -113.1271 [-116.0155, -110.9144] | lower |
| 5 − 3 | carbon_per_1000_builds_g | +9.5507 [+9.1745, +10.0262] | higher |
| 5 − 3 | ttff_p95_h_failed | -5.9273 [-6.4919, -5.3974] | lower |
| 5 − 4a | carbon_per_1000_builds_g | -1.9664 [-2.4423, -1.4949] | lower |
| 5 − 4a | ttff_p95_h_failed | -0.1809 [-0.6202, +0.1649] | n.s. |

## S-f second grid (DL-027 §2, DL-031, DL-032)

**not run — no qualifying data (DL-027 §2, DL-032).**

- **CAISO**: EIA-930 (DL-031) · criteria {'a_free_public_source': True, 'b_coverage_ge_95': True, 'c_peak_to_trough_gt_uk': False} · peak-to-trough 1.8669 vs UK 1.8746 · coverage {'2024': {'expected_hours': 8784, 'present_hours': 8688, 'gap_hours': 96, 'coverage_pct': 98.9071}, '2025': {'expected_hours': 8760, 'present_hours': 8664, 'gap_hours': 96, 'coverage_pct': 98.9041}}
- **Germany**:  · criteria {'a_free_public_source': False} · Electricity Maps requires an account (declined, DL-032); Energy-Charts API has no carbon-intensity endpoint — energy_charts_endpoints.txt sha256 e0a269834d35d569b43e2ec8e378f36f9844a034c81a153977348e7eae33c943

*By-product, descriptive only (DL-032):* descriptive only (DL-032): CAISO's consumed-intensity hour-of-week profile is not more variable than the UK's. The ranking-invariance question S-f was meant to answer remains **untested** and is carried as a limitation.


## Herding (P3-T4 S3) — descriptive, no threshold predeclared

| setting | top-5 slot share | × static | largest slot share | × static |
| :-- | --: | --: | --: | --: |
| `5_se_informed_policy__d480__w24` | 0.0769 | 1.54 | 0.0187 | 1.78 |
| `1_static` | 0.0499 | 1.00 | 0.0105 | 1.00 |
| `2_blanket_carbon_aware__d0__w167` | 0.2294 | 4.59 | 0.1971 | 18.77 |
| `3_eligibility_only__d0__w24` | 0.1494 | 2.99 | 0.0367 | 3.49 |
| `4a_duration_estimator__d480__w24` | 0.0901 | 1.80 | 0.0217 | 2.07 |
| `4b_duration_prior__d480__w24` | 0.0769 | 1.54 | 0.0187 | 1.78 |

Any strategy that concentrates builds into few green slots would, if deployed at scale, change the marginal intensity it is optimising against (§6). The hour-of-week average profile cannot represent that feedback; it is a stated limitation.

## How to read this (written at the P3-T4 gate)

> Authored text, added after the runs. It introduces **no new number**: every figure is copied from the
> table above or from `results/p3/sensitivity/*.json`.

**V2, the RQ2 decision-level verdict, is stable wherever it is evaluated, and cannot flip in this
design.** The frozen spec admits no SE family, so ⑤ ≡ ④b in every sweep. "⑤ beats both ④a and ④b" is
therefore false under every sweep, by construction. The sweeps test the robustness of *what was
measured*. They cannot turn the pre-registered null into a positive.

**V1, the model-level admitted set {F1}, holds in both halves of the test period and without cold-start
builds.**

- Early: F1 ΔPR-AUC +0.0127 [+0.0106, +0.0149].
- Late: +0.0101 [+0.0086, +0.0118], only just above the +0.01 floor.
- Cold-start builds excluded: +0.0128 [+0.0114, +0.0142].

As in P3-T1, the set is empty at ×2 of the floor in every case. F1's test-split model-level gain is
therefore consistent across time, but small and floor-sensitive.

**V3, the secondary finding (④b ≡ ⑤ over ④a), keeps its direction in every sweep. It fails the counting
condition once.**

- The area between frontiers stays positive, with its CI above 0, in every sweep that evaluates it.
  The smallest is +0.7500 [+0.5305, +1.1719] in the early period; the largest is +5.9026 [+4.4703,
  +6.6558] with `n_jobs`-scaled energy.
- **In the late period (S-e late) the ≥ 3-counting-points condition fails**, although that period's
  area is +3.5694 [+1.7615, +4.3448]. The cause is the predeclared definedness rule (DL-029 §8), not a
  reversal. The three strongest matched carbon points have 55–73% lower TTFF p95 with CIs above 0, but
  the late-period frontier fails to reach them in 34%, 18% and 9% of resamples. A point undefined in
  more than 5% of resamples cannot count. The TTFF axis contributes two counting points, one short of
  three.
- Reading: the *direction* of the duration-control finding is robust. Its *counting-rule strength* is
  not robust to halving the sample.

**V4, the RQ4 sign pattern, is stable in every sweep except one class at `W_max` = 12 h.**

- At 12 h, ⑤'s TTFF p95 is *significantly* lower than ④a's (n.s. at 24 h). The other seven classes are
  unchanged.
- The pattern is identical under the stricter eligibility variant (S-a, deferrable share 14.02%), both
  energy scalings (S-c) and `n_jobs` scaling (S-d).
- So the RQ4 comparison is robust to every predeclared perturbation. Against ①, the policy saves
  carbon at a TTFF cost. Against ② and ③, it saves less carbon at a much smaller TTFF cost. Against
  ④a, it is at least as good.

**The duration control's form (S-h).** The trailing 50-build ④b, a sensitivity and not the policy of
record, moves the duration-only frontier outward:

- against the frozen expanding ④b: area +0.3538 [+0.2370, +0.7650] pp·h, condition met at ×0.5 and
  ×1 but not ×2;
- against ④a: area +2.8195 [+2.1823, +3.1153], condition met at every floor.

This agrees with P1-T4 and P3-T1, where trailing-50 had the lower duration error, and with P3-T3's
oracle bound: a better *duration* estimate is where the remaining headroom lies. The frozen primary is
unchanged, as predeclared.

**The second grid (S-f) was not run** (DL-032). California failed the predeclared variance criterion
by a small margin, and Germany had no account-free intensity series. The question it was meant to
answer, whether the strategy ranking survives a more variable grid, remains **untested** and is
carried as a limitation. The by-product (California's hour-of-week profile is not more variable than
the UK's, on this measure) is descriptive only.

**Herding** is a real limitation for the blanket strategy (②): its largest single slot receives 18.77×
static's share. The frozen policy's concentration is modest (1.78× on the largest slot, 1.54× on the
top five).

## Provenance

- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep baseline` — 2026-09-28, 14 s → `results/p3/sensitivity/baseline.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep a` — 2026-09-28, 565 s → `results/p3/sensitivity/a.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep b` — 2026-09-28, 52 s → `results/p3/sensitivity/b.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep c` — 2026-09-28, 406 s → `results/p3/sensitivity/c.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep d` — 2026-09-28, 265 s → `results/p3/sensitivity/d.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep e` — 2026-09-28, 1244 s → `results/p3/sensitivity/e.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep f` — 2026-09-28, 26 s → `results/p3/sensitivity/f.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep g` — 2026-09-28, 1410 s → `results/p3/sensitivity/g.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep h` — 2026-09-28, 900 s → `results/p3/sensitivity/h.json`
- `PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep herding` — 2026-09-28, 0 s → `results/p3/sensitivity/herding.json`

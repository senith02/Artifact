# Energy & carbon model — as implemented (P2-T2)

Generated `2026-09-20T09:05:32+00:00` by `PYTHONPATH=. python scripts/report_energy_model.py`.
Machine-readable twin: `energy_model.json`. Test evidence: `pytest_p2_t2.txt`.

> **Provenance.** This run read the P0-T3 carbon profile and the energy config only.
> **0 dataset rows were read** — no split was opened, and the reference durations below are
> fixed a priori, not measurements from the corpus. Real per-build accounting is P2-T4's.

## The model (eval_protocol.md §8; DL-007, DL-009, DL-010)

```
E_kWh    = (P_avg_W / 1000) * (duration_s / 3600)
carbon_g = E_kWh * I(t_scheduled)
SCI      = (sum_b E_b * I(t_sched,b)) / N_success        [gCO2e per successful commit]
```

`duration_s` = `tr_duration` — build wall-clock seconds, max-aggregated per
DL-009 (DL-010). Permitted here under **§A1.2 role 1 (accounting): post-hoc only, never
reaches `decide()`**. `I(·)` is the hour-of-week mean intensity from the P0-T3 profile
(168 of 168 slots observed).

## The one value the protocol deferred: `P_avg_W`

**`P_avg_W` = 42.5 W**, pinned by **DL-021**. Derived, not asserted:

| Factor | Value | Where |
| :-- | :-- | :-- |
| Global fallback TDP | `POWER_CONSTANT = 85` W | `codecarbon/external/hardware.py` L13 |
| Assumed mean utilisation | `CONSUMPTION_PERCENTAGE_CONSTANT = 0.5` | same file, L15 |
| Constant-mode power law | `power = self._tdp * CONSUMPTION_PERCENTAGE_CONSTANT` | same file, L256 |

⇒ 85 × 0.5 = **42.5 W**. `load_energy_config()` re-multiplies these factors and
refuses a config whose `p_avg_w` does not reproduce them, so a typo cannot become a result.

**Citations of record** (both accessed 2026-09-20):

- CodeCarbon — Methodology (CPU power estimation) — <https://docs.codecarbon.io/latest/explanation/methodology/>
- CodeCarbon source, codecarbon/external/hardware.py, pinned at **v3.3.1** — <https://github.com/mlco2/codecarbon/blob/v3.3.1/codecarbon/external/hardware.py>

## Worked figures against the real profile

Greenest observed slot: **Sun 11:00**, 92.2400 gCO₂/kWh.  
Dirtiest observed slot: **Wed 18:00**, 172.9140 gCO₂/kWh.

| Duration | E (kWh) | gCO₂e @ dirtiest | gCO₂e @ greenest | Saved | % change |
| :-- | --: | --: | --: | --: | --: |
| 1 minute | 0.000708 | 0.1225 | 0.0653 | 0.0571 | -46.66% |
| 10 minutes | 0.007083 | 1.2248 | 0.6534 | 0.5714 | -46.66% |
| 1 hour | 0.042500 | 7.3488 | 3.9202 | 3.4286 | -46.66% |
| 2 hours | 0.085000 | 14.6977 | 7.8404 | 6.8573 | -46.66% |

The right-hand columns are the **upper bound** on what perfect hour-of-week shifting could
achieve for a single build. They are not a result: no scheduling decision, no eligibility gate
and no delay constraint has been applied. Treat them as the arithmetic ceiling the P2-T4
replay will fall short of.

## The mandatory ±50% `P_avg` band (DL-007)

A 1-hour build at **Wed 18:00** (172.9140 gCO₂/kWh):

| `P_avg` multiplier | `P_avg` (W) | gCO₂e |
| :-- | --: | --: |
| ×0.5 | 21.25 | 3.6744 |
| ×1.0 | 42.5 | 7.3488 |
| ×1.5 | 63.75 | 11.0233 |

Carbon is **exactly linear** in `P_avg`, which is why *relative* strategy comparisons are
invariant to it and *absolute* gCO₂e claims are not. Every carbon result in this study is
reported across this band (P3-T4).

## The DL-010 `n_jobs` variant (off by default)

Same 1-hour build at **Wed 18:00**, scaled by job count:

| `n_jobs` | gCO₂e |
| --: | --: |
| 1 | 7.3488 |
| 2 | 14.6977 |
| 4 | 29.3954 |
| 8 | 58.7908 |

## Estimation assumptions and threats (carry into P5-T4 §6)

1. **`P_avg_W` is a documented default for an *unidentified* CPU, not a measurement of Travis
   build hardware.** TravisTorrent records no hardware, no machine type and no power draw, so
   this constant cannot be measured from the backbone dataset. A sharper-looking figure would
   imply knowledge the corpus does not contain.
2. **No RAM or GPU term.** 42.5 W is CodeCarbon's CPU-only constant-mode figure, applied here
   as the whole-machine power. This biases **absolute** gCO₂e **downward**.
3. **Wall-clock under-counts parallel compute (DL-010).** `tr_duration` is build wall-clock, so
   a build whose jobs ran concurrently on separate machines is charged once. The `n_jobs`
   variant above brackets this; it is reported *alongside* the `P_avg` band, never instead.
4. **Constant power across the whole build.** No idle/ramp/utilisation profile is modelled —
   energy is strictly linear in duration. This is what makes **carbon saved proportional to
   duration by construction**, which is precisely why DL-013/§A1.13 rule the carbon channel
   closed to RQ2 and route RQ2's power through TTFF instead. This assumption is load-bearing
   for the study's central caveat, not a detail.
5. **Intensity is a 2024–2025 hour-of-week *mean* applied to 2011–2016 builds** (P0-T3, spec
   §3.2). The replay measures *shiftability under a modern grid's shape*, not the carbon those
   builds actually emitted. Using the mean also suppresses within-slot variance, so realised
   savings in a live deployment would be noisier in both directions.
6. **The GSF embodied term `M` is excluded** from SCI — laptop-scale, no provisioned hardware
   to amortise (eval_protocol §6). The reported SCI is the **operational** term only.
7. **Marginal vs average intensity.** `I(·)` is average grid intensity. A real deferral changes
   demand at the margin; the herding metric (§6) is the check on whether this study's
   strategies concentrate load enough for that gap to matter.

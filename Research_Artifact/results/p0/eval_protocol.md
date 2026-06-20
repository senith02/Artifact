# Evaluation Protocol (P0-T4) — FROZEN at the P0-T4 gate

> **Status:** frozen on approval of the P0-T4 gate. After that point this file is
> immutable in the same sense as the spec: any change to a metric, split rule,
> window mapping, energy model, or statistic requires a dated entry in
> `governance/03_DECISION_LOG.md` **first** — never a silent edit.
>
> **Authority & traceability.** Every clause below traces to a section of the
> frozen spec (`governance/01_SOURCE_OF_TRUTH.md`) or to a decision-log entry
> (DL-004…DL-010). Where a clause pins something the spec left open, the DL is
> named inline. This protocol invents **no** numeric constants from memory (R1);
> the one value the spec defers — the energy-model power `P_avg_W` — is pinned at
> implementation time (P2-T3) with a citation, per DL-007.
>
> **Scope.** This document defines *how every later number is measured*. It does
> not produce numbers. Splits run in P1-T2, model metrics in P1-T4, simulation
> metrics in P3. The function signatures in §10 are the contracts those tasks
> implement.

---

## 1. Population, grain, and labels (the unit every metric is computed over)

- **Grain:** one row per build, keyed by `tr_build_id` (DL-009). All metrics,
  splits, and statistics are computed at **build grain**, never job grain.
- **Analytic population:** the cleaned build set defined by the P0-T2 funnel
  (`results/p0/data_profile.md`): builds with a usable label, excluding
  `canceled`, with a parseable `gh_build_started_at`, after exact-duplicate
  removal. As measured this session: **925,897 builds → analytic set; 25.1%
  failure rate** (the live figure in `data_profile.json` governs, not this copy).
- **Label** (DL-009; `dataset_reference.md §Label`): `y = 1` (positive =
  **failure**) for `tr_status ∈ {failed, errored}`; `y = 0` for `{passed}`.
  `canceled`/missing are excluded from the population, not relabelled.
- **Feature set:** the commit-time-only features specified in
  `context/feature_spec.md` (implemented in P1-T1). The leakage blocklist there
  is enforced programmatically; no outcome-derived column may enter the matrix
  (spec §3.5, invariant 3).

---

## 2. Data splits — three-way, project-disjoint, time-ordered (DL-006)

Spec §3.5 mandates **project-held-out, time-ordered** validation (invariant 4).
DL-006 refines the spec's undefined "held-out fold" into three disjoint splits so
that calibration never touches test projects.

- **Three splits:** `train`, `calibration`, `test`.
- **Disjointness:** partition by `gh_project_name`; **no project appears in two
  splits** (leakage test P1-T2 S2a).
- **Target proportions:** ≈ **70 / 15 / 15**, measured by **build volume** (so each
  split holds enough builds for stable metrics), within a recorded tolerance.
- **Assignment:** projects are shuffled with `seed = RANDOM_SEED (42)`, then
  greedily assigned to splits to approach the build-volume targets; the exact
  project→split assignment is **saved** to `results/p1/splits.json`
  (project lists + per-split row counts + per-split failure rate).
- **Ordering:** within each split, builds are ordered by `gh_build_started_at`
  ascending (time-ordered; leakage test P1-T2 S2b). No random shuffle, no random
  k-fold, ever.
- **Use discipline:** train fits models; calibration fits the probability
  calibrator and selects the operating threshold (§5); **test is touched exactly
  once** (P1-T4). The P3 replay simulation runs on **test projects only** — the
  model is never evaluated on builds it trained on (DL-006 consequence).

---

## 3. Hyperparameter tuning protocol (inside training projects only)

- **Where:** tuning happens **exclusively inside the `train` projects**. The
  `calibration` and `test` projects are never seen during tuning (spec §3.5).
- **Internal validation:** order `train` builds by `gh_build_started_at`; the
  temporally-latest **20%** form a time-ordered internal-validation fold; the
  earlier 80% fit candidate models. This preserves the time-ordered guarantee
  inside tuning (no future→past leakage).
- **Selection metric:** maximise **PR-AUC** on the internal-validation fold
  (imbalanced positive = failure; spec §3.5 prioritises PR-AUC).
- **Search space (XGBoost; the primary model, spec §3.2):**
  `n_estimators`, `max_depth`, `learning_rate`, `subsample`,
  `colsample_bytree`, `min_child_weight`, `gamma`, and
  `scale_pos_weight` (imbalance handling, spec §3.5). The concrete grid/seeded
  random search and its ranges are recorded in the P1-T3 training config and run
  log; all seeds fixed.
- **Baselines:** Logistic Regression and Random Forest (spec §3.2) are tuned by
  the same internal-validation procedure, so model comparison is fair.

---

## 4. Models compared (RQ1)

- **Primary:** XGBoost with `scale_pos_weight` for imbalance (spec §3.2, §3.5).
- **Baselines:** Logistic Regression and Random Forest (spec §3.2).
- All three are trained on `train`, tuned by the identical internal-validation
  procedure (§3), calibrated on `calibration` (§5), and evaluated once on `test`
  by the §5 metric set — so the model comparison is fair and leakage-safe.
- The justification for XGBoost over deep models/LLMs (small tabular data, strong
  imbalance handling, CPU-fast, reproducible, SHAP-interpretable) is the spec's
  deliberate choice (§3.5); SHAP attributions are reported in P1-T4.

---

## 5. RQ1 metrics — discrimination **and** calibration (DL-004)

The deferral knob consumes the *probability*, not the class (spec §3.4, §3.5), so
calibration quality is a first-class RQ1 metric (DL-004), not an afterthought.
All RQ1 metrics are computed **once on the test split** (P1-T4), each with a
paired-bootstrap 95% CI (§9).

**Discrimination.**
- **PR-AUC** — area under the precision–recall curve (average precision), positive
  class = failure. *Primary* discrimination metric (imbalance).
- **ROC-AUC** — area under the ROC curve.
- **Precision / Recall / F1 at the operating threshold τ** —
  `Precision = TP/(TP+FP)`, `Recall = TP/(TP+FN)`, `F1 = 2·P·R/(P+R)`,
  with failure as the positive class.

**Operating threshold τ (locked rule).** τ is selected on the **calibration
split** as the threshold on the calibrated probability that **maximises F1**, then
**frozen and applied unchanged to test**. τ is never tuned on test. τ governs only
the *reported* classification metrics; the deferral policy itself uses the
continuous probability (§7), not τ.

**Calibration (DL-004).** Let `p̂_i` be the calibrated probability and
`y_i ∈ {0,1}`:
- **Brier score** = `(1/N) · Σ_i (p̂_i − y_i)²` (lower is better).
- **Expected Calibration Error (ECE)** — partition `[0,1]` into **M = 10**
  equal-width bins `B_m`;
  `ECE = Σ_m (|B_m|/N) · | acc(B_m) − conf(B_m) |`,
  where `conf(B_m)` = mean `p̂` in the bin and `acc(B_m)` = empirical failure rate
  in the bin.
- **Reliability diagram** — 10-bin predicted-probability vs observed-frequency
  plot, saved to `results/p1/` (calibration split in P1-T3, test split in P1-T4).

**Calibrator choice (DL-004).** Fit **both** isotonic and Platt (sigmoid)
calibration on the **calibration split**; keep whichever has the lower
**calibration-split Brier score**. The comparison table (both Briers) is recorded
in `results/p1/calibration/` (P1-T3).

**Literature framing (P1-T4 S2).** Any comparison to reported baselines
(e.g. Mhalla & Saied AUC ≈ 0.90, spec §2.1) is stated explicitly as *context, not
direct comparability* — different task, dataset, and label definition.

---

## 6. Simulation metrics (spec §4 + DL-005)

Computed per strategy on **identical test-project traces** (§2). Per-build records
(strategy, action, scheduled hour-of-week slot, carbon, latency, outcome) are
emitted by the simulator (P2-T4); the aggregates below are computed from them.

- **Estimated carbon per 1,000 builds** — `(Σ_b carbon_b / N) · 1000`, reported in
  **absolute gCO₂e and as % change vs the static baseline** (spec §4). `carbon_b`
  per §8.
- **GSF SCI per successful commit** —
  `SCI = (Σ_b E_b · I(t_sched,b)) / N_success`, units **gCO₂e per successful
  commit**, where `N_success` = number of builds with `y=0` in the trace.
  This is the **operational** SCI (energy × intensity); the embodied term `M` of
  the GSF formula is excluded — laptop-scale, no provisioned hardware to amortise
  — and this exclusion is declared in the threats chapter (spec §6).
- **Added developer-feedback latency** — `L_b = t_sched,b − t_arrival,b` (hours),
  the deferral wait. Reported **mean and p95** over **(a) all builds** and
  **(b) deferred builds only** (DL-005; spec §4).
- **Time-to-failure-feedback (TTFF), failed builds only (DL-005)** —
  `TTFF_b = L_b + duration_b` for builds with true label failure (`y=1`), i.e. the
  wall-clock from arrival until the failing result is visible. Reported **mean and
  p95**. `duration_b = tr_duration` (DL-010).
- **Missed-failure count + failure recall, skip-style strategies (DL-005)** — for
  any strategy that skips builds (strategy ④): `missed = #{y=1 builds skipped}`;
  `failure recall = #{y=1 builds actually run} / #{y=1 builds}`. Without these,
  the carbon-per-1,000 table would flatter skip strategies (DL-005 rationale).
- **Eligibility-gate safety** — count of **non-deferrable** builds that were
  deferred. **Must be 0 by construction** (spec §4); verified by the *independent*
  `validate_invariants.py` (P2-T1), which re-derives eligibility from raw columns
  and does **not** import the gate code.
- **Per-hour scheduled-load distribution (herding check)** — count of builds
  scheduled into each of the 168 hour-of-week slots, per strategy. If load
  concentrates into a few green slots, that is reported as a threat (a real
  deployment would shift the marginal intensity it is optimising against).

---

## 7. Deferral-window mapping — the Stage-2 knob (DL-008)

Eligible builds only (Stage 1 decides eligibility; spec §3.4). The calibrated
failure probability `p̂` sets the permitted delay window:

- **Default mapping:** `w(p̂) = W_max · (1 − p̂)` hours, monotone (higher p̂ ⇒
  never a longer window), clipped to `[0, W_max]`.
- **Default `W_max = 24` hours.** Lives in **one versioned config file** (P2-T2);
  no window constant is invented outside that config.
- **Scheduling within the window:** the build is placed at the **lowest-carbon
  hour-of-week slot reachable within `w(p̂)`**, via
  `scheduler_core.carbon.lowest_carbon_slot` (the thin primitive built in P0-T3).
- **Sensitivity sweep (P3-T3):** `W_max ∈ {6, 12, 24}` **and** a **banded
  (step-function) variant**. The banded variant for the sweep is fixed as:
  `p̂ ∈ [0,0.25) → W_max`, `[0.25,0.5) → 0.66·W_max`, `[0.5,0.75) → 0.33·W_max`,
  `[0.75,1] → 0`. The sweep demonstrates results are not an artefact of one
  mapping shape (DL-008 rationale).

---

## 8. Energy & carbon model (DL-007, refined by DL-010)

- **Energy:** `E_kWh = (P_avg_W / 1000) · (duration_s / 3600)` (DL-007).
- **Duration source:** `duration_s = tr_duration` (build wall-clock seconds,
  aggregated by `max` per DL-009) — **not** summed job log durations, which are
  95.3% null (DL-010). Threat: for multi-job builds this under-counts parallel
  compute (DL-010 consequence; threats chapter).
- **`P_avg_W` — cite-or-log (DL-007).** The average power is **cited** from
  CodeCarbon/EcoCI documentation (or an equivalent published source) **at P2-T3**,
  recorded in the energy config **and** in a follow-up decision-log entry carrying
  the citation. **No wattage is written here** (R1).
- **Carbon per build:** `carbon_b = E_b · I(t_sched,b)`, where `I(·)` is the
  **hour-of-week mean intensity** (gCO₂/kWh) from the P0-T3 profile
  (`scheduler_core.carbon.intensity_for_hour_of_week`); `t_sched,b` is the
  scheduled slot. Units: kWh × gCO₂/kWh = gCO₂e.
- **Sensitivity band (DL-007):** **every** carbon result is re-run at
  `P_avg × {0.5, 1.0, 1.5}` (±50%). Relative strategy comparisons are robust to
  `P_avg` (it scales all strategies equally); absolute gCO₂e claims are not — the
  band makes that explicit (P3-T3).
- **Optional variant (DL-010):** an `n_jobs`-scaled energy variant may be reported
  alongside the `P_avg` band to bracket the parallel-compute under-count.

---

## 9. Statistics — paired bootstrap over shared traces

Because all strategies are evaluated on the **identical** trace (spec §4), the
comparison is **paired**: resample the *shared* set of builds once per bootstrap
iteration and recompute every strategy's metric on that same resample.

- **Procedure:** draw `B` bootstrap resamples of the test-trace build index with
  replacement; for each resample compute each strategy's metric and each pairwise
  difference (strategy X − strategy Y).
- **Resamples:** `B = 1000` (≥ 1,000 per the plan), **seeded with
  `RANDOM_SEED (42)`** for reproducibility.
- **Confidence intervals:** **95%** via the percentile method (2.5th / 97.5th
  percentiles of the bootstrap distribution).
- **Significance & effect size:** a pairwise difference is reported as significant
  when its 95% CI excludes 0; the point estimate of the difference (absolute, in
  the metric's units) is the effect size. The proposed method "Pareto-improves on
  carbon-only" (spec §4 success criterion) is judged from the **signed CIs** of
  the carbon and latency differences — an honest null (CI spanning 0) is a valid,
  reportable verdict (RQ4, spec §1.5).
- **Applies to:** RQ1 test metrics (§5), and all P3 carbon/latency/TTFF
  comparisons (§6).

---

## 10. Function signatures to implement (S2 — contracts only, not implementations)

These signatures are frozen here; the bodies are written in P1-T2 (`make_splits`)
and P3 (`paired_bootstrap`). They encode §2 and §9 respectively.

```python
# scheduler_core/splits.py  — implemented in P1-T2 (per §2, DL-006)
def make_splits(
    builds: "pd.DataFrame",
    *,
    project_col: str = "gh_project_name",
    time_col: str = "gh_build_started_at",
    proportions: tuple[float, float, float] = (0.70, 0.15, 0.15),  # train, calib, test
    seed: int = RANDOM_SEED,                                       # 42
) -> dict[str, "pd.DataFrame"]:
    """Project-disjoint, time-ordered train/calibration/test split (§2, DL-006).

    Partitions builds by ``project_col`` so no project appears in two splits;
    assigns projects (shuffled by ``seed``) greedily to approach ``proportions``
    measured by build volume; orders each split ascending by ``time_col``.

    Returns
    -------
    {"train": df, "calibration": df, "test": df}
        Disjoint by project, time-ordered within each split. The caller writes the
        manifest (project lists + per-split row counts + failure rates) to
        results/p1/splits.json. Raises if any project would span two splits or if
        a split is empty.
    """
    ...


# replay/stats.py (or scheduler_core/stats.py) — implemented in P3 (per §9)
def paired_bootstrap(
    per_build: "pd.DataFrame",                       # one row per (build × strategy)
    metric_fns: "Mapping[str, Callable[[pd.DataFrame], float]]",
    *,
    strategies: "Sequence[str]",
    n_resamples: int = 1000,                         # B >= 1000
    ci: float = 0.95,
    seed: int = RANDOM_SEED,                          # 42
) -> dict:
    """Paired bootstrap over the shared build trace (§9).

    Resamples the shared build index with replacement ``n_resamples`` times; for
    each resample computes every metric in ``metric_fns`` for every strategy and
    every pairwise strategy difference.

    Returns
    -------
    dict
        Per-(strategy, metric): point estimate + (lower, upper) percentile CI.
        Per-(metric, strategy_X, strategy_Y): difference point estimate + CI +
        a boolean ``significant`` (CI excludes 0). Deterministic given ``seed``.
    """
    ...
```

---

## 11. Consistency check (spec + DL coverage)

| Requirement | Source | Locked in |
| :-- | :-- | :-- |
| Project-held-out, time-ordered, no random k-fold | spec §3.5, invariant 4 | §2, §3 |
| PR-AUC + ROC-AUC + P/R/F1 at calibrated threshold | spec §3.5 | §5 |
| Brier + ECE + reliability diagrams; isotonic-vs-Platt by Brier | **DL-004** | §5 |
| Three-way project-disjoint split (70/15/15), seeded, saved | **DL-006** | §2 |
| Tuning inside training projects only | spec §3.5; plan P0-T4 | §3 |
| Carbon/1,000 (abs + %), SCI per successful commit | spec §4 | §6 |
| Latency mean/p95 over all + deferred-only; TTFF; missed-failure + recall | **DL-005** | §6 |
| Gate-safety = 0, independently validated | spec §4 | §6 |
| Per-hour scheduled-load (herding) | plan P0-T4 | §6 |
| `w(p̂)=W_max·(1−p̂)`, W_max=24, sweep {6,12,24} + banded | **DL-008** | §7 |
| `E=(P_avg/1000)·(dur/3600)`, P_avg cited, ±50% band | **DL-007** | §8 |
| `duration_s = tr_duration` (not summed job durations) | **DL-010** | §8 |
| Paired bootstrap, B≥1000, 95% CI, seeded | spec §4; plan P0-T4 | §9 |
| `make_splits` / `paired_bootstrap` signatures | plan P0-T4 S2 | §10 |

No clause in this protocol is left "TBD". The only value deferred by design is
`P_avg_W`, pinned with a citation at P2-T3 (DL-007).

---

## 12. Provenance

- **Author task:** P0-T4 (`planning/development_plan.md`).
- **Run date:** 2026-06-20.
- **Sources cited:** `governance/01_SOURCE_OF_TRUTH.md` §3.2–§3.5, §4, §6;
  `governance/03_DECISION_LOG.md` DL-004..DL-010; `context/feature_spec.md`,
  `context/dataset_reference.md`; `results/p0/data_profile.md` (population);
  `results/p0/carbon_profile.md` (intensity series, P0-T3).
- **Freeze:** this file becomes immutable on P0-T4 gate approval; amendments only
  via a new DL entry (≥ DL-011).

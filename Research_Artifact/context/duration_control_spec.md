# Context — Duration-Control Design Specification (`d̂`)

**Task:** P1-T1 · **RQ:** RQ2 · **Status:** design specification — **this document produces no numbers
and no code** (R1). It fixes, before any implementation exists, exactly what the duration control is,
what information it may see, how it is fitted, how it is measured, and which tests it must pass.

**Authority.** Every clause below cites `results/p0/eval_protocol.md` **Amendment A1.1** (§A1.1–A1.2,
A1.6, A1.9, A1.10, A1.13), the frozen protocol body (§1–§3, §9), `context/feature_spec.md`,
`context/dataset_reference.md`, or a decision-log entry. Where this spec relies on an interpretation
rather than a literal clause, it names **DL-014** inline. Nothing here amends A1; A1 governs.

> ### The one sentence this whole document exists to enforce
>
> **The build being decided has not run yet, so its `tr_duration` does not exist at decision time — it
> is an outcome of the very execution the scheduler is deciding when to start, and any path that lets it
> reach `d̂` is a leakage defect, not a modelling choice** (§A1.2, `feature_spec.md` §Duration, DL-012 §2).

> ### The decision-log entry this document depends on is **resolved**
>
> **DL-014** — proposed 2026-08-12, **Accepted / Resolved by author decision 2026-08-17** — resolves an
> internal tension in A1.1's information-availability clause by binding **fitted parameters** and
> **within-project online state** differently. §3, §4.1 and §7 are written against it and say so.
> The accepted reading is the **intended deployment information regime**: fitted parameters come from
> **train projects only**, while a project's own strictly-earlier build history (`< t_b`, ties excluded)
> is online state a deployed scheduler genuinely holds and is therefore available on calibration and test
> projects too. This is *not* training on held-out projects — no parameter is estimated from them.
> **No claim is made about the direction of any residual bias** (DL-014 §Resolution 5).

---

## 1. What `d̂` is

`d̂(b)` is a **commit-time point estimate of how long build `b` would take to run**, formed **before**
`b` starts, from information a deployed scheduler genuinely holds at that instant. It is the **control
variable** of the study: the null against which every SE feature family is tested (§A1.3, §A1.4).

| Property | Value | Source |
| :-- | :-- | :-- |
| **Estimand** | wall-clock build duration in seconds, at **build grain** (`tr_build_id`) | §1 (grain), DL-009 |
| **Fitted target** | `y_d = log(1 + tr_duration_s)` — the log1p transform | §A1.1 |
| **`tr_duration` aggregation** | `max` over the build's job rows | DL-009 |
| **Decision-scale output** | `d̂_seconds = expm1(ŷ_d)` — a **monotone** back-transform | this spec §1.1 |
| **Consumed by** | strategy ④ (`d̂ ≥ d_threshold`), and every ⑤ arm as the control term | §A1.3, §A1.6 |
| **Never consumed by** | any feature matrix for the failure model; any `decide()` path that could see the *actual* duration | §A1.2 |

`d̂` is **not** a feature family and is **not** ablated away: it is present in **every** arm, including
the null arm `{d̂}` (§A1.3). That is what "beyond expected build duration" means operationally.

### 1.1 Why log1p, and what the back-transform does

The target is fitted on the log1p scale (§A1.1) because build durations are heavy-tailed and a
squared-error fit on raw seconds would be dominated by a few very long builds. Two consequences are
declared here, in advance:

- **Jensen bias is expected and accepted.** `expm1(E[log(1+D)])` estimates a *conditional median-like*
  quantity, not `E[D]`; `d̂_seconds` is therefore systematically **below** the conditional mean for
  right-skewed conditional distributions. This is acceptable because strategy ④'s rule is the
  **monotone** comparison `d̂ ≥ d_threshold` (§A1.6) and `d_threshold` is *fitted on the same scale*
  (§A1.7), so a monotone bias is absorbed into the fitted threshold rather than distorting the decision.
- **Rank quality is the decision-relevant quality.** Because the rule is a threshold on a monotone
  transform, **Spearman ρ** (§A1.1) is the quality measure that speaks to ④'s decisions; MAE speaks to
  how well the control is *described*. Both are reported (§6); neither is allowed to stand in for the
  other.

### 1.2 Which builds carry a usable training label

A build contributes a **training label** only if it is in the P0-T2 analytic population (§1) and has a
present, strictly-positive `tr_duration`. Builds failing that test are excluded from **fitting only** —
they are never dropped from the evaluation population, from the replay, or from any metric denominator.
(`tr_duration` is near-complete at build grain; the measured null / non-positive rates are recorded in
`results/p0/duration_check.json` and summarised in `dataset_reference.md` — no figure is restated here,
per R1.)

---

## 2. The exact information available at decision time

At the moment `b` is scored, the estimator may read **only** the following, and nothing else:

| # | Admissible input | Detail | Authority |
| :-- | :-- | :-- | :-- |
| **I1** | The **28 commit-time features** of `b` | exactly the contract in `feature_spec.md`; no additions, no substitutions | §A1.1(a), invariant 3 |
| **I2** | **Fitted parameters** derived from **train-split projects** | regressor weights + hyperparameters; language prior; global prior | §A1.1(b), DL-014 §1 |
| **I3** | **Builds of `b`'s own project that had finished before `b` arrived** | `gh_build_started_at + tr_duration < t_b`, same `gh_project_name`; online state, not a fitted parameter. *(Corrected by **DL-034**, 2026-10-01: the original rule `gh_build_started_at < t_b` admitted builds still running at `t_b`.)* | §A1.1 sentence 2, DL-014 §2, DL-034 |

Explicitly **inadmissible**, in every form and by every route:

- `tr_duration` / `tr_log_buildduration` **of `b` itself** — the estimand, not an input (§A1.2).
- Any column on the `feature_spec.md` leakage blocklist, including `tr_prev_build` (future linkage). The
  estimator reaches project history through **I3**'s split-and-time-filtered path, never that column.
- Any build with `gh_build_started_at ≥ t_b`, in any project — including **ties**: builds of the same
  project sharing `b`'s exact timestamp are treated as **not strictly earlier** and are excluded (a
  same-second sibling's duration is not knowable before `b` starts).
- Any build belonging to a **calibration or test** project, as a contributor to **I2** (§A1.1, §2).
- `gh_pushed_at` as the ordering key — the arrival clock is `gh_build_started_at`
  (`dataset_reference.md`, §2 ordering rule).

**Ordering key, fixed once:** `gh_build_started_at`, ascending, for every temporal operation in this
document (history windows, cut-offs, internal-validation folds).

---

## 3. The training cut-off rule

Two mechanisms, bound differently — this is the substance of **DL-014**.

### 3.1 Mechanism 1 — fitted parameters (④a's regressor; the language and global priors)

- Fitted on **train-split projects only** (`results/p1/splits.json`), over the whole train period.
- **No per-scored-build temporal cut-off is applied**, because the splits are project-disjoint (§2): a
  train build carries no information about `b`, `b`'s project, or `b`'s outcome. What binds here is the
  **split**, not the clock (DL-014 §1).
- **Within** the fit, time-ordering is still preserved for model selection: the internal-validation fold
  is the temporally-latest **20%** of train builds, the earlier 80% fits candidates — the identical
  procedure the frozen protocol §3 fixes for the failure model, reused unchanged so the control and the
  treatment are tuned by the same machinery (§A1.4 "same tuning procedure").
- The residual — a train build *later in wall-clock* than a scored calibration/test build may inform the
  fit — is a **declared threat of undetermined direction** (§8). Its effect on RQ2 is **not measured and
  not assumed**; no claim that it strengthens the null is made (DL-014 §Resolution 5).

### 3.2 Mechanism 2 — within-project online state (④b's prior; the cold-start ladder's first rung)

- Reads **only** builds of `b`'s own project that had **finished** before `b` arrived:
  `gh_build_started_at + tr_duration < t_b` (strict; ties excluded per §2) — **DL-034**. A build that
  started earlier but was still running has no observed duration at `t_b`. The release has no finish
  timestamp, so start + `tr_duration` is the earliest-possible-finish proxy (declared in DL-034 §B1).
- Permitted for **calibration and test** projects, because it is online state a deployed scheduler holds,
  not a parameter estimated across the corpus (DL-014 §2). Without this, ④b degenerates to the language
  prior on every evaluation project and the §A1.9 project-identity control ceases to exist.
- Computed **causally, per build**, in a single time-ordered pass — never as a whole-project statistic
  broadcast back over the project's rows.

### 3.3 The invariant both mechanisms serve

> No quantity that becomes knowable **at or after `t_b`** may influence `d̂(b)`, and no quantity derived
> from `b`'s own execution may influence `d̂(b)` at all — regardless of which mechanism supplies it.

---

## 4. The two admissible forms

Both are implemented and both are reported; the **primary** is chosen by the rule in §5 (§A1.1).

### 4.1 Form ④b — project / language historical prior (parameter-free)

```text
d̂_④b(b) = expm1( median{ log(1 + duration(h)) : h ∈ H(b) } )
H(b) = builds of b's project with gh_build_started_at + tr_duration < t_b and a usable label (§1.2)
       (DL-034; was gh_build_started_at < t_b)
```

- **Statistic:** median on the log1p scale — robust to the tail, and (being order-based) identical to
  the median of raw seconds under the monotone transform. Stated explicitly so the implementation is not
  free to choose a mean.
- **Window:** **expanding** — all strictly-earlier builds of the project. *(Declared sensitivity, §6.3:
  a trailing window of the last 50 builds. The expanding form remains primary regardless of outcome.)*
- **Trigger for the ladder:** `|H(b)| = 0` — i.e. A1.1's literal *"a project with no admissible earlier
  build"*. No minimum-history parameter is introduced here. *(Declared sensitivity, §6.3: requiring
  `|H(b)| ≥ 5` and `≥ 20` before trusting the project rung.)*
- **Role:** this is the **project-identity control** required by §A1.9 — ⑤ must beat it as well as ④a.

### 4.2 Form ④a — commit-time regressor

- **Inputs:** exactly the **28 features** of `feature_spec.md` (I1). The rolling project prior is **not**
  added as a 29th input: the 28-feature contract is fixed (§A1.3), and keeping the two forms mechanically
  distinct is what makes ④a-vs-④b interpretable as "learned from features" vs "knows the repo".
- **Target:** `log(1 + tr_duration)` of **historical train-split builds** (§A1.1; role 2 of §A1.2).
- **Primary family:** `xgboost.XGBRegressor`, `objective="reg:squarederror"` — the same library the
  frozen stack pins for the failure model (spec §3.2), CPU-only, native NaN handling, SHAP-compatible.
- **Reference family:** `sklearn.linear_model.Ridge` on standardised inputs, reported alongside as a
  transparency baseline. It is **not** eligible to become the primary control; it exists so that a
  gradient-boosted control that fails to beat a linear one is visible rather than assumed.
- **Categorical handling:** `lang` is one-hot encoded from the **levels observed in the train split**;
  an unseen level at scoring time encodes as all-zeros (and is counted in the coverage table, §6.2).
- **Missing values:** XGBoost uses its native missing-direction learning. Ridge uses **median imputation
  with train-split medians only**, fitted as part of the model and persisted with it.
- **Search space (fixed here, before any code — §A1.1, DL-012 §9).** Seeded random search,
  `n_iter = 40` candidates, `seed = RANDOM_SEED (42)` (§2, §9):

  | Hyperparameter | Range sampled |
  | :-- | :-- |
  | `n_estimators` | 100 – 800 (log-uniform integer) |
  | `max_depth` | 3 – 10 (uniform integer) |
  | `learning_rate` | 0.01 – 0.30 (log-uniform) |
  | `subsample` | 0.6 – 1.0 (uniform) |
  | `colsample_bytree` | 0.6 – 1.0 (uniform) |
  | `min_child_weight` | 1 – 20 (log-uniform integer) |
  | `gamma` | 0 – 5 (uniform) |

  Ridge searches `alpha ∈ 10^{-3} … 10^{3}` (log-uniform, same `n_iter`, same seed).
- **Selection inside the search:** **MAE on the internal-validation fold** (§3.1) — the latest 20% of
  train builds by `gh_build_started_at`. MAE (not RMSE) because the control feeds a threshold decision
  and should not be dragged by the tail; declared now, not after seeing curves.
- **All seeds fixed** at `RANDOM_SEED = 42`; the resolved best configuration, the full search trace, and
  the library versions are persisted with the model (§7.4, R8).

---

## 5. How the primary control is chosen

> **Rule (predeclared).** Fit both forms. Compute each form's **MAE on the log1p scale over the
> calibration split**. The **lower** MAE becomes the **primary** duration control `d̂`; the other is
> reported in full beside it and is retained as strategy **④b**'s / **④a**'s own arm regardless of which
> won (§A1.6 runs *both*).

- The comparison number must come from **that run**, recorded in `results/p1/duration_control.md` with
  the command that produced it (R1). No expectation about which form wins is recorded anywhere in
  advance — including here.
- **Ties** (equal to 4 decimal places on the log1p MAE) resolve to **④b**, the simpler and
  parameter-free form.
- The choice is made **once**, on **calibration**, and is **frozen** before P3 opens the test split
  (§A1.7, §2 use-discipline). Test-split numbers may never revise it.
- **Both forms run in the P3 replay regardless** — §A1.6 requires ④a *and* ④b, and §A1.9 requires ⑤ to
  beat **both**. "Primary" governs which estimate is the control term inside ⑤'s arms, not which
  strategies are executed.

---

## 6. The cold-start ladder, its provenance record, and what gets reported

### 6.1 The ladder

Applied in order; the **first** rung that can be evaluated is used:

| Rung | Level | Definition | Mechanism |
| :-- | :-- | :-- | :-- |
| **1** | `project` | ④b over `H(b)` (§4.1) — or ④a's prediction when ④a is primary | 2 (and 1 for ④a) |
| **2** | `language` | median log1p duration over **train-split** builds sharing `b`'s `gh_lang` | 1 |
| **3** | `global` | median log1p duration over **all train-split** builds | 1 |

- Rung 3 is **total**: the global prior always evaluates, so `d̂` is defined for every build in the
  population and no build is silently dropped from a strategy.
- ④a's regressor is itself total over the 28 features, so when ④a is the primary control the ladder
  engages only for an unseen `lang` level or a wholly-missing feature row; the ladder is still evaluated
  and recorded so the two forms are directly comparable.
- Rungs 2 and 3 are **fitted parameters** (mechanism 1) — computed from train-split builds only, never
  from the scored build's own split.

### 6.2 Per-build provenance (a hard requirement on the implementation)

Every scored build carries a record — persisted with the simulator's per-build output (DL-012
§Consequences) — containing at minimum:

| Field | Meaning |
| :-- | :-- |
| `d_hat_log1p`, `d_hat_seconds` | the estimate on both scales |
| `form` | `④a` \| `④b` |
| `fallback_level` | `project` \| `language` \| `global` |
| `n_history` | `|H(b)|` — builds available in the project's causal history |
| `fit_id`, `seed`, `fit_row_range` | which fit produced it, and over what data range |

### 6.3 What is reported in `results/p1/duration_control.md` (P1-T4)

1. **Quality of the control** (§A1.1): **MAE**, **median absolute error**, and **Spearman ρ** against
   observed duration — for **both forms**, on the **calibration** split (P1-T4) and on the **test**
   split (P3-T1, once). MAE and median AE are reported on **both** scales (log1p and seconds); the
   selection metric of §5 is the log1p one, named as such.
2. **Cold-start coverage table**: count and share of builds at each `fallback_level`, per split, and the
   distribution of `n_history`.
3. **Results with and without cold-start builds** (§A1.1) — every headline quality number is given twice,
   once over all builds and once restricted to `fallback_level = project`.
4. **Declared sensitivities** (secondary, never allowed to change the primary): ④b with a trailing
   50-build window; ④b requiring `|H(b)| ≥ 5` and `≥ 20`; Ridge vs XGBoost for ④a.
5. **The threat statement** of §8, in the report's own words — RQ2 answers *"beyond **predictable**
   duration"*, not *"beyond duration"*.

---

## 7. Tests the implementation must pass (P1-T4 DoD)

A1.1 requires three leakage tests. **DL-014 §3** determines which mechanism each one binds; T2 and T2b
are the two halves of A1.1(ii), split because a temporal cut-off can only bind mechanism 2 and a split
boundary can only bind mechanism 1.

| ID | Test | Binds | Passing means |
| :-- | :-- | :-- | :-- |
| **T1** | **Blocklist assertion** on the estimator's own feature matrix — no `feature_spec.md` blocklisted column, and no column derived from one, may appear. Includes a **duration-specific negative test**: injecting `tr_duration` into the input frame must raise. | A1.1(i) | the estimator cannot see outcomes |
| **T2** | **Temporal test** — for a fixture project, injecting builds with `gh_build_started_at ≥ t_b` into the project's history **must change** `d̂(b)` when they are (incorrectly) admitted, and **must not change it** under the shipped causal path. A no-op result means the cut-off is not being applied. | A1.1(ii), mech. 2 | the strict `< t_b` window really binds |
| **T2b** | **Split test** — injecting a calibration- or test-split project into the fitting set must be **rejected** by assertion, not silently absorbed. | A1.1(ii), mech. 1 | train-only fitting really binds |
| **T3** | **Negative fixture** — a deliberately leaky estimator fixture (history window built with `≤ t_b` instead of `< t_b`, i.e. including `b` itself) must be **rejected** by the test suite. | A1.1(iii) | the tests can actually fail |
| **T4** | **Round-trip** — a persisted estimator reloads and reproduces `d̂` **exactly** for a fixed set of builds. | R8, P1-T4 DoD | the control is reproducible |
| **T5** | **Totality** — `expected(build)` returns a finite, positive `d̂` for every build in the analytic population, with a `fallback_level` set. | §6.1 | no build silently escapes a strategy |

Verbatim pytest output for T1–T5 is captured at the P1-T4 gate; a passing claim without captured output
is not a passing claim (R1, R6).

---

## 8. Declared threats to validity (must reach the threats chapter)

1. **The control is a *predicted* quantity.** Estimator error propagates into the null, so RQ2 answers
   *"beyond **predictable** duration"* (§A1.1, DL-012 §Consequences). §A1.10's oracle-duration arm —
   labelled *"oracle — unrealizable in deployment"* — exists to bound how much of any ⑤ margin is
   estimator error rather than SE signal.
2. **Fit-time wall-clock asymmetry** (DL-014 §4, §Resolution 5). Under mechanism 1, train builds later in
   wall-clock than a scored held-out build may inform the fitted control. **The direction of this bias is
   undetermined**: it is neither measured nor assumed, and no claim that it strengthens the null or is
   otherwise conservative may be made on its basis. It is carried as an open threat.
3. **Cold-start coarsening.** Early builds of a project fall to the language or global rung, where `d̂`
   is markedly less informative; §6.3(3) reports every headline number with and without them.
4. **④a absorbs SE-through-duration by design** (§A1.13). Because ④a is fitted on the same 28 features,
   any SE information that acts *by predicting duration* is inside the control. RQ2 therefore tests for
   SE information **orthogonal to predicted duration** — the strictest reading, and a deliberate one.
5. **Wall-clock under-counts parallel job compute** (DL-010) — inherited from the duration source, and it
   propagates into both the label `d̂` is fitted on and the energy accounting.

---

## 9. Clause-by-clause cross-check against A1.1 / A1.2 (plan S4)

| A1 clause | Requirement | Where satisfied | Deviation |
| :-- | :-- | :-- | :-- |
| A1.1 ¶1 | control is a **commit-time estimate**, not the actual duration | §1, the boxed sentence | — |
| A1.1 information rule (a) | may depend on `b`'s commit-time features | §2 I1 | — |
| A1.1 information rule (b) | may depend on train-split builds with `started_at < t_b` | §2 I2/I3, §3.1, §3.2 | **DL-014** — clause split into fitted parameters (no per-build cut-off, split-bound) vs within-project causal state (permitted for calibration/test) |
| A1.1 "own project history, strictly earlier" | strict inequality within project | §2 (ties excluded), §3.2, §4.1 | — |
| A1.1 "nothing at or after `t_b`" | no future information | §2, §3.3, test **T2** | — |
| A1.1 two admissible forms | ④b prior **and** ④a regressor, both evaluated | §4.1, §4.2 | — |
| A1.1 "better by validation MAE is primary" | primary chosen by MAE; other reported | §5 (scale + split + tie-break pinned) | — |
| A1.1 "model family, search space, seeds fixed in the P1-T1 spec" | pinned before code | §4.2 | — |
| A1.1 target transform | `log(1 + tr_duration)` | §1, §1.1 | — |
| A1.1 cold start | project → language → global | §6.1 | — |
| A1.1 "fallback level recorded per build" | per-build provenance | §6.2 | — |
| A1.1 "coverage table reported" | coverage table | §6.3(2) | — |
| A1.1 "with and without cold-start builds" | dual reporting | §6.3(3) | — |
| A1.1 reported quality | MAE, median AE, Spearman ρ, calibration **and** test | §6.3(1) | — |
| A1.1 "control's error is a stated threat" | threat stated | §8(1) | — |
| A1.1 leakage tests (i)(ii)(iii) | three tests at P1-T4 DoD | §7 T1, T2+T2b, T3 | **DL-014 §3** — (ii) implemented as two tests, one per mechanism |
| A1.2 role 1 — accounting | actual duration reaches only the simulator | out of scope here; §1 table states `d̂` is what `decide()` sees | — |
| A1.2 role 2 — historical training label | earlier builds, train-split only | §1.2, §3.1, §4.2 | — |
| A1.2 role 3 — oracle bound, labelled | referenced, not implemented here | §8(1) → §A1.10 | — |
| A1.2 "any other use is a leakage defect" | enforced by assertion | §2 inadmissible list, test **T1** | — |
| A1.6 | ④a and ④b both run; `d_threshold`/`W_max` fitted on calibration | §5 final bullet | thresholds themselves are P2-T5's, not this spec's |
| A1.9 | ④b is the mandatory project-identity control | §4.1, and the reason DL-014 exists | — |
| A1.13 | ④a absorbs SE-through-duration; ④b is the looser reading | §8(4) | — |

**Open items: none.** This document contains no `TBD`.

---

## 10. Interface contract handed to P1-T4

`scheduler_core/duration_estimator.py` implements, at minimum:

```text
expected(build) -> DurationEstimate
    .d_hat_log1p    float
    .d_hat_seconds  float          # expm1(d_hat_log1p); the scale decide() thresholds
    .form           "4a" | "4b"
    .fallback_level "project" | "language" | "global"
    .n_history      int
    .provenance     {fit_id, seed, fit_row_range, split, library_versions}
```

- The estimator is **fitted** by an explicit `fit(train_builds, splits)` entry point that **asserts** its
  input contains train-split projects only (test **T2b**), and is **persisted** with everything needed to
  reproduce `d̂` exactly (test **T4**).
- `expected()` is **pure** with respect to the scored build: it receives `b`'s commit-time features and
  `b`'s causal project history, and has no route to `b`'s own row in any duration column.
- **`decide()` never receives an observed duration** — only `d̂_seconds`. That is the single wire this
  entire specification protects (§A1.2, invariant 6).

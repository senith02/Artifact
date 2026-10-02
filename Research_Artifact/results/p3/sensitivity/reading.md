## How to read this (re-authored 2026-10-02 under DL-034)

> Authored text, added after the runs. It introduces **no new number**: every figure is copied from the
> table above or from `results/p3/sensitivity/*.json`. These are the DL-034 sweeps (completion-causal
> ④b history). The original sweeps and reading are preserved at commit `1e38db7`.

**New under DL-034: V1, the model-level admitted set {F1}, now flips in the late test period.** In the
late half (76,038 builds), F1's ΔPR-AUC vs `{d̂}` is +0.008974 [+0.007371, +0.010633]. That is
significantly positive but **below the +0.01 floor**, so the late-period admitted set is ∅. In the
original sweep it was +0.0101, only just above the floor. The set still holds in the early half
(+0.012823 [+0.010681, +0.015001]) and with cold-start builds excluded (+0.012514 [+0.011035,
+0.013924]), and it is empty at ×2 of the floor in every case, as in P3-T1. F1's test-split
model-level gain is therefore **small, floor-sensitive and not stable across time**. This strengthens
the reading of P3-T1: F1 is an unresolved, heterogeneous signal, not an established one.

**V2, the RQ2 decision-level verdict, is stable wherever it is evaluated, and cannot flip in this
design.** The frozen spec admits no SE family, so ⑤ ≡ ④b in every sweep. "⑤ beats both ④a and ④b" is
false under every sweep, by construction.

**V3, the secondary finding (④b ≡ ⑤ over ④a), keeps its direction in every sweep. It fails the counting
condition once, as before.**

- The area between frontiers stays positive, with its CI above 0, in every sweep that evaluates it.
  The smallest is +0.7451 [+0.5199, +1.1666] in the early period; the largest is +5.8957 [+4.4605,
  +6.6478] with `n_jobs`-scaled energy.
- **In the late period (S-e late) the ≥ 3-counting-points condition fails**, although that period's
  area is +3.5552 [+1.7470, +4.3365]. The cause is the predeclared definedness rule (DL-029 §8), not a
  reversal. The three strongest matched carbon points have 55–73% lower TTFF p95, but the late-period
  frontier fails to reach them in 34%, 18% and 9% of resamples, over the 5% limit. The TTFF axis
  contributes two counting points, one short of three.
- Reading: the *direction* of the duration-control finding is robust. Its *counting-rule strength* is
  not robust to halving the sample.

**V4, the RQ4 sign pattern, is stable in every sweep except one class at `W_max` = 12 h, as before.**

- At 12 h, ⑤'s TTFF p95 is *significantly* lower than ④a's (n.s. at 24 h). The other seven classes are
  unchanged.
- The pattern is identical under the stricter eligibility variant (S-a, deferrable share 14.02%), both
  energy scalings (S-c) and `n_jobs` scaling (S-d).

**The duration control's form (S-h).** The trailing 50-build ④b, a sensitivity and not the policy of
record, moves the duration-only frontier outward:

- against the frozen expanding ④b: area +0.3622 [+0.2382, +0.7770] pp·h, condition met at ×0.5 and
  ×1 but not ×2;
- against ④a: area +2.8232 [+2.1849, +3.1264], condition met at every floor.

This agrees with P1-T4 and P3-T1, where trailing-50 had the lower duration error, and with P3-T3's
oracle bound: in this replay, more accurate duration information is where the remaining headroom lies.
The frozen primary is unchanged, as predeclared.

**The second grid (S-f) was not run** (DL-032). California failed the predeclared variance criterion
(peak-to-trough 1.8669 vs the UK's 1.8746) and Germany had no account-free intensity series. Whether
the strategy ranking survives a more variable grid remains **untested**.

**Herding** is a real limitation for the blanket strategy (②): its largest single slot receives 18.77×
static's share. The frozen policy's concentration is modest (1.77× on the largest slot, 1.54× on the
top five).

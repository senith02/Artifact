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

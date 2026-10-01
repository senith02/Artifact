# P2-T4 sample run — what is committed, what is regenerated

> ⚠ **BOOTSTRAP-DERIVED** — like every file in this folder, nothing here is a result (DL-022, DL-023 §4).

## `decisions.csv.gz` is not tracked

The per-record decision file (1,224,000 rows, 60,974,525 bytes) is kept out of git by `.gitignore`
(author decision, 2026-09-24, at the P2-T4 gate). Everything else in this folder is tracked, and the
file is **deterministically regenerable**; its identity is pinned rather than stored:

| evidence | where |
| :-- | :-- |
| sha256 `2929114e63131402fdccab67ddce01a0fb0f2332017aa16152cca28bceb0a6f1` | `manifest.json` → `sha256`, `determinism.json` |
| byte-identical across two fully fresh end-to-end runs | `determinism.json` (`byte_identical: true`) |
| independent validator over it: 0 violations / 117,440 deferrals / 1,224,000 rows | `validator.json`, `validator_cli.txt` |
| run fingerprint `8d3cba36e5f8e1fc70bcb775286c9d8fc1ffa6c0ae5d9f722b7b789d1472c2a3`, grid sha256 `151a4b360a70d96f…` | `manifest.json` |

### Regenerate

From `Research_Artifact/code/`, with the locked environment and the frozen artifacts present
(`split_assignment.csv` sha256 `3d9a7947…5cde`, duration control fit id `1088d5546f47ff12`,
`xgboost:full` fit id `a09cc750e9db41b8`; regenerated under DL-034, 2026-10-01 — the pre-DL-034 values were `bc4defb6…` / `65fd81b1…`, commit `95c6d6d`):

```
PYTHONPATH=. python scripts/run_replay.py --allow-unfitted-spec --fresh --out <dir>
```

then check `sha256(<dir>/decisions.csv.gz)` against the value above, or pass
`--compare-with ../results/p2/sample_run` to have the script compare every tracked output's sha256.
The validator can be re-run over the regenerated file:

```
PYTHONPATH=. python replay/validate_invariants.py <dir>/decisions.csv.gz
```

## Documented replay characteristics (not defects; the frozen grid stands)

Both were observed on this sample run. Per the author's decision at the P2-T4 gate (2026-09-24), they
are **characteristics of the replay to be reported**, not grounds to change anything:
`replay/sweep_grid.json` (sha256 `151a4b36…`) and the DL-023 strategy definitions stay frozen, and the
primary τ grid is **not** re-chosen from the observed p̂ distribution — doing so would be selecting a
grid after seeing the data it is evaluated on.

1. **⑥'s τ frontier is coarse.** p̂ (isotonic-calibrated `xgboost:full`) takes only **42 distinct
   values** over the 12,000 sampled builds, and **10,461 (87.2%)** lie in (0.25, 0.30]; median 0.2844,
   p90 0.3112. So the τ grid {0, 0.05, …, 0.30} produces 0 → 48 skips up to τ = 0.25 and then a single
   step to **2,322** skips at τ = 0.30 (`summary.csv`). ⑥'s swept frontier therefore has effectively
   one non-trivial point beyond the low-τ tail; that is a property of a step-function calibrator on a
   weak score, and is reported as such.
2. **④a has limited prediction support at the top of the D grid.** The ④a estimate ranges
   24.98 s … **4,310.20 s** (p99 2,788.52 s); only 887 sampled builds have ④a ≥ 1,920 s and **7** have
   ④a ≥ 3,840 s. ④a defers **0** builds at D ∈ {3,840, 7,680, 15,360} s at every W (`summary.csv`), so
   those three points are empty for ④a, while ④b (max 9,469 s) still defers at D = 7,680 s. The ④a
   frontier is correspondingly shorter; this reflects ④a's compressed range (it is the weaker estimator,
   P1-T4) and is reported, not compensated for.

Both figures come from `trace.csv` and `summary.csv` in this folder alone, via (run 2026-09-24 from
`Research_Artifact/`):

```python
import pandas as pd
t = pd.read_csv("results/p2/sample_run/trace.csv")
p = pd.to_numeric(t.p_hat, errors="coerce"); d = pd.to_numeric(t.d_hat_4a_seconds, errors="coerce")
p.nunique(), ((p > 0.25) & (p <= 0.30)).sum(), p.quantile([.5, .9])      # 42, 10461, 0.2844/0.3112
d.min(), d.quantile(.99), d.max(), (d >= 1920).sum(), (d >= 3840).sum()  # 24.98, 2788.52, 4310.20, 887, 7
```

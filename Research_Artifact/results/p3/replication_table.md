# Calibration vs test — does the model-level admission decision replicate? (P3-T1)

> Calibration numbers: `results/p1/ablation/deltas.json` and `results/p1/admission.json` (P1-T6/P1-T7). Test numbers: this task's single test pass (`model_report.json`). The rule applied to both is the same `scheduler_core.admission` code. A family admitted on calibration that fails on test — or the reverse — is a finding and is reported here.

| family | ΔPR-AUC calibration [95% CI] | verdict calibration | ΔPR-AUC test [95% CI] | verdict test | verdict replicates | sign replicates |
| :-- | :-- | :-- | :-- | :-- | :-: | :-: |
| **F1** | -0.003678 [-0.005310, -0.001958] | rejected | +0.013313 [+0.011924, +0.014733] | admitted | **no** | **no** |
| **F2** | -0.005526 [-0.007217, -0.003854] | rejected | -0.001556 [-0.002871, -0.000237] | rejected | yes | yes |
| **F3** | -0.023333 [-0.026575, -0.019859] | rejected | -0.033651 [-0.036018, -0.031540] | rejected | yes | yes |
| **F4** | -0.064694 [-0.067304, -0.061747] | rejected | -0.019986 [-0.022152, -0.017869] | rejected | yes | yes |
| **F5** | -0.066323 [-0.069205, -0.063377] | rejected | -0.006225 [-0.008489, -0.004032] | rejected | yes | yes |
| **F6** | -0.002920 [-0.004531, -0.001263] | rejected | +0.002257 [+0.000982, +0.003683] | rejected | yes | **no** |

**Floor sweep, both splits:**

| floor multiplier | admitted on calibration | admitted on test | replicates |
| :-- | :-- | :-- | :-: |
| x0.5 | (empty) | F1 | **no** |
| x1 | (empty) | F1 | **no** |
| x2 | (empty) | (empty) | yes |

Every family verdict replicates: **False**.

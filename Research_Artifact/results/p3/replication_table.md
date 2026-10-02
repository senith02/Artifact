# Calibration vs test — does the model-level admission decision replicate? (P3-T1)

> Calibration numbers: `results/p1/ablation/deltas.json` and `results/p1/admission.json` (P1-T6/P1-T7). Test numbers: this task's single test pass (`model_report.json`). The rule applied to both is the same `scheduler_core.admission` code. A family admitted on calibration that fails on test — or the reverse — is a finding and is reported here.

| family | ΔPR-AUC calibration [95% CI] | verdict calibration | ΔPR-AUC test [95% CI] | verdict test | verdict replicates | sign replicates |
| :-- | :-- | :-- | :-- | :-- | :-: | :-: |
| **F1** | -0.003456 [-0.005189, -0.001728] | rejected | +0.013035 [+0.011639, +0.014500] | admitted | **no** | **no** |
| **F2** | -0.006544 [-0.008138, -0.005010] | rejected | -0.002005 [-0.003197, -0.000802] | rejected | yes | yes |
| **F3** | -0.033082 [-0.036426, -0.029669] | rejected | -0.032535 [-0.034816, -0.030346] | rejected | yes | yes |
| **F4** | -0.066490 [-0.069371, -0.063261] | rejected | -0.009683 [-0.012374, -0.006851] | rejected | yes | yes |
| **F5** | -0.072851 [-0.075662, -0.069727] | rejected | -0.005472 [-0.007619, -0.003252] | rejected | yes | yes |
| **F6** | -0.008449 [-0.010149, -0.006754] | rejected | +0.002831 [+0.001483, +0.004169] | rejected | yes | **no** |

**Floor sweep, both splits:**

| floor multiplier | admitted on calibration | admitted on test | replicates |
| :-- | :-- | :-- | :-: |
| x0.5 | (empty) | F1 | **no** |
| x1 | (empty) | F1 | **no** |
| x2 | (empty) | (empty) | yes |

Every family verdict replicates: **False**.

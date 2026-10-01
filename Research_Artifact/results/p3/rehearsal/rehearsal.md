# P3-T1 calibration rehearsal — the pipeline must reproduce P1 before test opens

> `PYTHONPATH=. python scripts/evaluate_test.py --split calibration` on 2026-09-25, B = 1000, elapsed 4326.7 s. **Calibration split only; the test split was dropped unread.** Every check compares a freshly computed number with the value stored by the P1 task that produced it, for exact equality.

**32 / 32 checks pass** — all pass: **True**. Fingerprint `da77d6cab3373268…`.

| check | pass | detail |
| :-- | :-: | :-- |
| `arm_metrics:xgboost:control` | ✓ | exact |
| `arm_metrics:xgboost:full` | ✓ | exact |
| `arm_metrics:logreg:control` | ✓ | exact |
| `arm_metrics:logreg:full` | ✓ | exact |
| `arm_metrics:random_forest:control` | ✓ | exact |
| `arm_metrics:random_forest:full` | ✓ | exact |
| `arm_metrics:xgboost:F1` | ✓ | exact |
| `arm_metrics:xgboost:F2` | ✓ | exact |
| `arm_metrics:xgboost:F3` | ✓ | exact |
| `arm_metrics:xgboost:F4` | ✓ | exact |
| `arm_metrics:xgboost:F5` | ✓ | exact |
| `arm_metrics:xgboost:F6` | ✓ | exact |
| `family_delta:F1` | ✓ | exact incl. CIs |
| `family_delta:F2` | ✓ | exact incl. CIs |
| `family_delta:F3` | ✓ | exact incl. CIs |
| `family_delta:F4` | ✓ | exact incl. CIs |
| `family_delta:F5` | ✓ | exact incl. CIs |
| `family_delta:F6` | ✓ | exact incl. CIs |
| `duration:4b_expanding:all_builds` | ✓ | exact |
| `duration:4b_expanding:project_rung_only` | ✓ | exact |
| `duration:4a_xgboost:all_builds` | ✓ | exact |
| `duration:4a_xgboost:project_rung_only` | ✓ | exact |
| `duration:4a_ridge:all_builds` | ✓ | exact |
| `duration:4a_ridge:project_rung_only` | ✓ | exact |
| `shap_family:control` | ✓ | exact |
| `shap_family:F1` | ✓ | exact |
| `shap_family:F2` | ✓ | exact |
| `shap_family:F3` | ✓ | exact |
| `shap_family:F4` | ✓ | exact |
| `shap_family:F5` | ✓ | exact |
| `shap_family:F6` | ✓ | exact |
| `shap_monotonicity` | ✓ | exact |

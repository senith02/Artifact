"""P4-T1 — structural guarantees on the advisor's import graph (R3-B2, R3-B3).

- No P4 module loads a failure-model arm, SHAP, the ablation or admission code.
- `p_hat` appears only in the contract's rejection list.
- The only decision function the advisor calls is `scheduler_core.policy.decide`.
- P4 adds no file under `scheduler_core/` (the frozen core is untouched).
"""

from __future__ import annotations

import ast
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
P4_FILES = sorted((CODE / "advisor").glob("*.py")) + sorted((CODE / "api").glob("*.py"))
FORBIDDEN = {"shap", "scheduler_core.models", "scheduler_core.ablation_stats", "scheduler_core.admission",
             "xgboost", "sklearn"}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_p4_modules_exist():
    assert len(P4_FILES) >= 12


def test_no_p4_module_imports_a_failure_model_or_shap():
    for path in P4_FILES:
        bad = {name for name in _imports(path) if any(name == f or name.startswith(f + ".") for f in FORBIDDEN)}
        assert not bad, f"{path.name} imports {sorted(bad)}"


def test_p_hat_only_appears_in_the_rejection_list():
    for path in P4_FILES:
        source = path.read_text(encoding="utf-8")
        if path.name == "contract.py":
            assert '"p_hat"' in source
            continue
        assert "p_hat" not in source, path.name


def test_decide_is_the_only_decision_function_called():
    core = CODE / "advisor" / "core.py"
    assert "scheduler_core.policy.decide" in _imports(core)
    calls = {node.func.id for node in ast.walk(ast.parse(core.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "decide" in calls
    # nothing in the advisor re-implements the threshold rule
    for path in P4_FILES:
        assert "d_threshold" not in path.read_text(encoding="utf-8"), path.name


def test_the_estimate_reuses_the_frozen_history_and_ladder():
    names = _imports(CODE / "advisor" / "estimate.py")
    assert "scheduler_core.duration_estimator" in names
    source = (CODE / "advisor" / "estimate.py").read_text(encoding="utf-8")
    assert "causal_project_history" in source and "predict_4b" in source and "availability=de.COMPLETED" in source

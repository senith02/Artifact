"""Tests for P1-T5's per-arm checkpoint/resume machinery.

Resuming an interrupted training run is a compute optimisation that must never
become a change of result. Two properties make that true, and both are tested
here:

* **a checkpoint is reused only under an identical configuration** — the
  fingerprint covers the seed, the search budget, the frozen split digest, the
  `d̂` fit id, the debug sample size, the arm/algorithm sets, the population
  sizes and the library versions, so moving any one of them refits rather than
  silently mixing two configurations into one report (R1);
* **a checkpoint is reused only if its persisted model still reproduces it** —
  `resume_arm` recomputes the stored calibration metrics from the reloaded
  artifact and refuses any mismatch, so a resumed arm is held to the same
  round-trip standard as a freshly fitted one.

The end-to-end property — that an arm refitted after an abort reproduces the
cold run bit-for-bit — follows from each arm seeding its own search generator
inside ``models.train_arm``; there is no cross-arm random state to lose.
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scheduler_core import features, models

CODE_ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    """Import `scripts/train_models.py` as a module (it is not on the package path)."""
    if str(CODE_ROOT) not in sys.path:
        sys.path.insert(0, str(CODE_ROOT))
    spec = importlib.util.spec_from_file_location(
        "train_models_under_test", CODE_ROOT / "scripts" / "train_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tm = _load_script()

FP = dict(seed=42, n_iter=20, d_hat_fit_id="1088d5546f47ff12",
          split_digest="3d9a7947", sample_projects=0,
          n_train=645_244, n_calib=138_687)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture()
def ckpt_dir(tmp_path, monkeypatch):
    d = tmp_path / "checkpoints"
    monkeypatch.setattr(tm, "CKPT_DIR", d)
    return d


def _frame(n: int = 240, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2014-01-01", tz="UTC")
    out = pd.DataFrame({
        "tr_build_id": [f"b{i:05d}" for i in range(n)],
        "gh_project_name": [f"org/p{i % 6:02d}" for i in range(n)],
        "gh_build_started_at": [(base + pd.Timedelta(hours=i)
                                 ).strftime("%Y-%m-%d %H:%M:%S") for i in range(n)],
        "lang": ["ruby" if i % 2 else "java" for i in range(n)],
    })
    for j, name in enumerate(features.FEATURES):
        if name not in out.columns:
            out[name] = rng.normal(j, 1.0, size=n)
    out[models.D_HAT_COLUMN] = rng.normal(6.0, 1.0, size=n)
    return out


def _labels(frame: pd.DataFrame, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    p = 1 / (1 + np.exp(-(0.9 * (frame[models.D_HAT_COLUMN] - 6.0) - 1.0)))
    return pd.Series((rng.random(len(frame)) < p).astype("int64"), index=frame.index)


# --------------------------------------------------------------------------- #
# The fingerprint
# --------------------------------------------------------------------------- #

def test_fingerprint_is_stable_for_an_identical_configuration():
    assert tm.run_fingerprint(**FP) == tm.run_fingerprint(**FP)


@pytest.mark.parametrize("field, value", [
    ("seed", 43),
    ("n_iter", 21),
    ("d_hat_fit_id", "deadbeefdeadbeef"),
    ("split_digest", "ffffffff"),
    ("sample_projects", 12),
    ("n_train", 645_243),
    ("n_calib", 138_686),
])
def test_fingerprint_changes_when_any_input_moves(field, value):
    """Anything that could change a number must invalidate the checkpoint."""
    moved = dict(FP, **{field: value})
    assert tm.run_fingerprint(**moved) != tm.run_fingerprint(**FP)


def test_fingerprint_covers_the_library_versions(monkeypatch):
    before = tm.run_fingerprint(**FP)
    monkeypatch.setattr(models, "library_versions",
                        lambda: {"xgboost": "0.0.0-not-real"})
    assert tm.run_fingerprint(**FP) != before


# --------------------------------------------------------------------------- #
# Save / load
# --------------------------------------------------------------------------- #

def test_checkpoint_round_trips(ckpt_dir):
    fp = tm.run_fingerprint(**FP)
    result = {"algorithm": "xgboost", "arm": "control", "calibrated": {"n": 5}}
    tm.save_checkpoint("xgboost:control", fingerprint=fp, result=result,
                       search_trace=[{"candidate": 1}])
    blob = tm.load_checkpoint("xgboost:control", fingerprint=fp)
    assert blob is not None
    assert blob["result"] == result
    assert blob["search_trace"] == [{"candidate": 1}]


def test_checkpoint_filename_is_filesystem_safe(ckpt_dir):
    """The tag contains ':', which Windows forbids in a path component."""
    tm.save_checkpoint("logreg:full", fingerprint="x", result={}, search_trace=[])
    names = [p.name for p in ckpt_dir.iterdir()]
    assert names == ["logreg__full.json"]
    assert not any(":" in n for n in names)


def test_save_leaves_no_temp_file_behind(ckpt_dir):
    tm.save_checkpoint("logreg:full", fingerprint="x", result={}, search_trace=[])
    assert list(ckpt_dir.glob("*.tmp")) == []


def test_missing_checkpoint_is_none(ckpt_dir):
    assert tm.load_checkpoint("xgboost:control", fingerprint="x") is None


def test_a_stale_fingerprint_is_refused(ckpt_dir):
    tm.save_checkpoint("xgboost:control", fingerprint=tm.run_fingerprint(**FP),
                       result={"a": 1}, search_trace=[])
    other = tm.run_fingerprint(**dict(FP, seed=43))
    assert tm.load_checkpoint("xgboost:control", fingerprint=other) is None


def test_a_truncated_checkpoint_is_refused(ckpt_dir):
    """A hard kill mid-write must degrade to a refit, never to a parse error."""
    tm.save_checkpoint("xgboost:control", fingerprint="x", result={"a": 1},
                       search_trace=[])
    path = ckpt_dir / "xgboost__control.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: len(text) // 2], encoding="utf-8")
    assert tm.load_checkpoint("xgboost:control", fingerprint="x") is None


def test_a_checkpoint_without_a_result_is_refused(ckpt_dir):
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    (ckpt_dir / "xgboost__control.json").write_text(
        json.dumps({"fingerprint": "x", "search_trace": []}), encoding="utf-8")
    assert tm.load_checkpoint("xgboost:control", fingerprint="x") is None


# --------------------------------------------------------------------------- #
# resume_arm re-verifies against the persisted model
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def trained_control(tmp_path_factory):
    """One genuinely fitted+calibrated `control` arm, persisted to disk."""
    d = tmp_path_factory.mktemp("models")
    frame = _frame()
    y = _labels(frame)
    trained = models.train_arm(
        "logreg", "control", frame, y, frame["gh_build_started_at"],
        lang_levels=("java", "ruby"), seed=42, n_iter=1, verbose=False)
    models.calibrate(trained, frame, y, verbose=False)
    path = models.save_arm(trained, d)
    return trained, path, frame, y


def _stored_metrics(trained, frame, y):
    """The calibrated metric block as it would land in a checkpoint (via JSON)."""
    metrics = models.score_split(y.to_numpy(), trained.predict_proba(frame),
                                 tau=trained.tau)
    return json.loads(json.dumps(metrics))


def test_resume_refuses_a_missing_artifact(ckpt_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "MODEL_DIR", tmp_path / "no-such-dir")
    frame = _frame(20)
    assert tm.resume_arm("logreg:control", {"result": {}}, frame,
                         _labels(frame)) is None


def test_resume_accepts_a_checkpoint_its_model_reproduces(
        trained_control, monkeypatch):
    trained, path, frame, y = trained_control
    monkeypatch.setattr(tm, "MODEL_DIR", path.parent)
    stored = _stored_metrics(trained, frame, y)
    reused = tm.resume_arm("logreg:control", {"result": {"calibrated": stored}},
                           frame, y)
    assert reused is not None
    assert np.array_equal(reused.predict_proba(frame), trained.predict_proba(frame))


@pytest.mark.parametrize("key", ["pr_auc", "brier", "ece", "roc_auc", "tau", "n"])
def test_resume_refuses_a_checkpoint_its_model_does_not_reproduce(
        trained_control, monkeypatch, key):
    """A checkpoint that disagrees with its artifact is discarded, not trusted."""
    trained, path, frame, y = trained_control
    monkeypatch.setattr(tm, "MODEL_DIR", path.parent)
    stored = _stored_metrics(trained, frame, y)
    stored[key] = stored[key] + 1 if key == "n" else stored[key] + 0.01
    assert tm.resume_arm("logreg:control",
                         {"result": {"calibrated": stored}}, frame, y) is None


def test_resume_refuses_a_checkpoint_missing_a_verified_metric(
        trained_control, monkeypatch):
    trained, path, frame, y = trained_control
    monkeypatch.setattr(tm, "MODEL_DIR", path.parent)
    stored = _stored_metrics(trained, frame, y)
    del stored["pr_auc"]
    assert tm.resume_arm("logreg:control",
                         {"result": {"calibrated": stored}}, frame, y) is None

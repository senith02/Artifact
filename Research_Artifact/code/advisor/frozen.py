"""The frozen research artifacts the advisor runs on, and their pins.

DL-033 R3-A pins the spec, the GB hour-of-week profile and the ④b estimator;
DL-035 §2 makes the two text pins **line-ending-normalised** so they hold on a
Linux runner as well as on a Windows checkout with ``core.autocrlf``. Any
mismatch is a fail-safe (``spec_unavailable`` / ``profile_unavailable`` /
``estimator_unavailable``), never a warning: a decision computed on an
unpinned artifact is not the evaluated decision.
"""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scheduler_core import carbon as carbon_mod
from scheduler_core.duration_estimator import DurationEstimator
from scheduler_core.policy import DEFAULT_POLICY_SPEC_PATH, PolicyError, PolicySpec, load_policy_spec

CODE_DIR = Path(__file__).resolve().parents[1]
SPEC_PATH = DEFAULT_POLICY_SPEC_PATH
PROFILE_PATH = carbon_mod.DEFAULT_PROFILE_PATH
ESTIMATOR_PATH = CODE_DIR / "artifacts" / "duration_estimator.joblib"


@dataclass(frozen=True)
class Pins:
    """Expected identities of the three frozen artifacts."""

    spec_sha256: str = "e43b004d3df0a680d5e5519f8ddceb54ffd2861f6eb3363c5c2ec7d3e45c8cf8"
    profile_sha256: str = "2af9992ee46c1d752df1e5b58e945e02d309a2234b2983c565ccf119548cf40d"
    estimator_sha256: str = "ccc5bb2431404f416ca9f23eaeab7d97ddd7a2723404cba85cd1254f01241fc0"
    estimator_fit_id: str = "1088d5546f47ff12"
    estimator_form: str = "4b"


PINS = Pins()


class FrozenArtifactError(RuntimeError):
    """A frozen artifact is missing or does not match its pin. ``code`` names the fail-safe."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalised_sha256(path: Path) -> str:
    """SHA-256 over the file with every CRLF replaced by LF (DL-035 §2)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class FrozenCore:
    """Everything a decision needs, verified against its pins."""

    spec: PolicySpec
    profile: pd.DataFrame
    estimator: DurationEstimator
    spec_sha256: str
    profile_sha256: str
    estimator_fit_id: str


def _check(path: Path, actual: str, expected: str, code: str, what: str) -> None:
    if actual != expected:
        raise FrozenArtifactError(
            code, f"{what} at {path} has sha256 {actual[:16]}…, expected {expected[:16]}… — "
                  f"not the evaluated artifact")


def load_frozen_core(
    spec_path: Path = SPEC_PATH,
    profile_path: Path = PROFILE_PATH,
    estimator_path: Path = ESTIMATOR_PATH,
    *,
    pins: Pins = PINS,
) -> FrozenCore:
    """Load and verify the spec, profile and estimator. Raises :class:`FrozenArtifactError`."""
    spec_path, profile_path, estimator_path = Path(spec_path), Path(profile_path), Path(estimator_path)

    if not spec_path.is_file():
        raise FrozenArtifactError("spec_unavailable", f"policy spec not found: {spec_path}")
    spec_hash = normalised_sha256(spec_path)
    _check(spec_path, spec_hash, pins.spec_sha256, "spec_unavailable", "policy spec")
    try:
        spec = load_policy_spec(spec_path, require_fitted=True)
    except PolicyError as exc:
        raise FrozenArtifactError("spec_unavailable", str(exc)) from exc

    if not profile_path.is_file():
        raise FrozenArtifactError("profile_unavailable", f"carbon profile not found: {profile_path}")
    profile_hash = normalised_sha256(profile_path)
    _check(profile_path, profile_hash, pins.profile_sha256, "profile_unavailable", "GB profile")
    try:
        profile = carbon_mod.load_hour_of_week_profile(profile_path)
    except carbon_mod.CarbonDataError as exc:
        raise FrozenArtifactError("profile_unavailable", str(exc)) from exc

    if not estimator_path.is_file():
        raise FrozenArtifactError("estimator_unavailable", f"estimator not found: {estimator_path}")
    _check(estimator_path, raw_sha256(estimator_path), pins.estimator_sha256,
           "estimator_unavailable", "duration estimator")
    try:
        estimator = DurationEstimator.load(estimator_path)
    except Exception as exc:  # unpickling can fail in many ways; all mean "not usable"
        raise FrozenArtifactError("estimator_unavailable", f"estimator could not be loaded: {exc}") from exc
    fit_id = str(estimator.provenance.get("fit_id"))
    if fit_id != pins.estimator_fit_id:
        raise FrozenArtifactError(
            "estimator_unavailable", f"estimator fit id {fit_id} != pinned {pins.estimator_fit_id}")
    if estimator.primary_form != pins.estimator_form:
        raise FrozenArtifactError(
            "estimator_unavailable",
            f"estimator primary form {estimator.primary_form!r} != pinned {pins.estimator_form!r}")

    return FrozenCore(spec=spec, profile=profile, estimator=estimator, spec_sha256=spec_hash,
                      profile_sha256=profile_hash, estimator_fit_id=fit_id)


@functools.lru_cache(maxsize=1)
def default_frozen_core() -> FrozenCore:
    """The pinned artifacts at their default paths, loaded once per process."""
    return load_frozen_core()

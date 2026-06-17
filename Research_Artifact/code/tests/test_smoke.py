"""Skeleton smoke tests (P0-T1).

These verify only that the package imports and the global seed is wired up.
Real tests (loader header validation, eligibility invariants, etc.) arrive in
later phases.
"""

import importlib


def test_scheduler_core_imports():
    """The shared core package imports cleanly."""
    mod = importlib.import_module("scheduler_core")
    assert mod is not None


def test_random_seed_is_canonical():
    """RANDOM_SEED is defined once and re-exported from the package root."""
    from scheduler_core import RANDOM_SEED
    from scheduler_core.config import RANDOM_SEED as SEED_FROM_CONFIG

    assert RANDOM_SEED == 42
    assert RANDOM_SEED is SEED_FROM_CONFIG

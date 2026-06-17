"""scheduler_core — the single shared decision core.

This package holds the logic that BOTH the replay simulator (P2-T4, P3) and the
live API (P4-T1) import. Per architecture invariant #5, the API must never fork
this logic — it imports `decide()` from here.

Modules are added phase by phase (see code/README.md); only `config` exists at
the P0-T1 skeleton stage.
"""

from scheduler_core.config import RANDOM_SEED

__all__ = ["RANDOM_SEED"]

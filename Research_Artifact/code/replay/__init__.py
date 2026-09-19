"""replay — trace-driven simulator package.

Replays TravisTorrent build traces through the shared ``scheduler_core``
decision logic against the carbon series, for each of the **six** compared
strategies (Layer 0-A; the frozen §4 five plus the duration-control null added
by DL-012). The simulator itself is built in P2-T4 and run in P3.

Present since P2-T1: ``validate_invariants`` — the independent eligibility
validator, a deliberately separate code path that audits decision records
without importing ``scheduler_core.eligibility``.

Modules here audit or drive ``scheduler_core``; ``scheduler_core`` never imports
from this package.
"""

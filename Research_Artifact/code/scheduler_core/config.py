"""Project-wide constants.

The single source of the global random seed. Every module that needs
reproducible randomness (splits, model training, sampling) imports
``RANDOM_SEED`` from here — it is never re-defined elsewhere (rule R8:
reproducibility by default).
"""

# Global random seed — imported everywhere randomness occurs. Do not redefine.
RANDOM_SEED: int = 42

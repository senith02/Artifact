"""Energy & carbon accounting (eval_protocol.md §8 + §6; DL-007, DL-009, DL-010, DL-021).

This module turns a build's **observed** wall-clock duration and a **scheduled**
grid-intensity into gCO₂e, and aggregates those per-build figures into the two
carbon metrics the evaluation protocol defines (carbon per 1,000 builds and the
GSF SCI per successful commit).

⚠ **This module is POST-DECISION ONLY — the A1.2 role-1 boundary.**
`tr_duration` is an *outcome of the build being scheduled*. `eval_protocol.md`
§A1.2 permits it in exactly three roles, and the role implemented here is role 1,
**accounting**, whose constraint reads verbatim: *"Post-hoc only; never reaches
`decide()`."* Everything in this file therefore runs **after** a decision has been
made, scoring what that decision cost. Nothing here may be called from, imported
by, or fed into the decision path.

That boundary is enforced structurally rather than by comment:

* this module takes durations as **plain numbers passed in by its caller**. It
  opens no dataset, builds no feature matrix and reads no build row, so it cannot
  itself source a `tr_duration`;
* it imports **nothing from the decision path** — not `features`, `models`,
  `duration_estimator`, `eligibility`, `admission`, `splits` or `data`. Its only
  in-package import is :mod:`scheduler_core.carbon`, the P0-T3 intensity
  primitive;
* `tests/test_accounting.py` asserts both directions on the AST: that this module
  imports no decision-path module, **and** that no decision-path module imports
  this one. The second assertion is forward-binding — when `policy.py` arrives in
  P2-T3 carrying `decide()`, importing this module will fail that test.

**What the numbers mean (and do not).** `P_avg_W` is pinned at **42.5 W** by
DL-021, derived from CodeCarbon's constant-mode CPU fallback (`POWER_CONSTANT =
85` × `CONSUMPTION_PERCENTAGE_CONSTANT = 0.5`, pinned at release `v3.3.1`). It is
a *documented default for an unidentified CPU*, not a measurement of Travis build
hardware — TravisTorrent records no hardware at all. It carries no RAM or GPU
term. Absolute gCO₂e figures from this module are therefore **indicative only**
and every one of them is reported inside the mandatory ±50% band
(:func:`p_avg_band`); the **relative** strategy comparisons that carry RQ4 are
invariant to `P_avg`, because it scales every strategy identically (DL-007).

A second, independent understatement: `duration_s = tr_duration` is build
**wall-clock** (DL-010), so a build whose jobs ran concurrently on separate
machines has its total compute under-counted. :func:`energy_kwh` exposes the
DL-010 `n_jobs`-scaled variant to bracket that, reported *alongside* the `P_avg`
band, never instead of it.

**Scope boundary.** This module owns §8 (energy) and §6's two *carbon* aggregates.
The other §6 simulation metrics — feedback latency, TTFF, missed-failure counts,
gate safety, herding — are emitted by the replay simulator (P2-T4) from its
per-build records and aggregated in P3; they are deliberately not duplicated here.

No constant in this module is hard-coded: `P_avg_W`, the sensitivity multipliers
and the model's documentation all load from
``scheduler_core/config/energy.json``, which carries the DL-021 citation.
"""

from __future__ import annotations

import json
import math
import numbers
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from . import carbon as carbon_mod


def _is_real_number(value: object) -> bool:
    """True for a real number that is not a bool.

    Uses the :mod:`numbers` ABCs rather than ``isinstance(x, (int, float))``
    because the replay simulator hands these functions values pulled out of
    DataFrames: ``numpy.float64`` *is* a ``float`` subclass but ``numpy.int64``
    is **not** an ``int``, so a plain isinstance check would reject a perfectly
    good integer duration. ``bool`` is excluded deliberately — ``True`` is not a
    duration, a wattage, an intensity or a label.
    """
    return isinstance(value, numbers.Real) and not isinstance(value, bool)

#: Unit conversions. Named rather than inlined so the §8 formula reads literally.
WATTS_PER_KILOWATT: float = 1000.0
SECONDS_PER_HOUR: float = 3600.0

#: The versioned energy config (DL-007 "recorded in config"; DL-021).
_CONFIG_DIR = Path(__file__).resolve().parent / "config"
DEFAULT_ENERGY_CONFIG_PATH = _CONFIG_DIR / "energy.json"

#: The only `schema_version` this module understands. A config written against a
#: different key set must not be read silently — bump this together with the file.
SUPPORTED_SCHEMA_VERSION: int = 1

#: The modules this one must never import — the decision path (A1.2 role 1).
#: Asserted on the AST by `tests/test_accounting.py`, in both directions.
DECISION_PATH_MODULES: frozenset[str] = frozenset(
    {"features", "models", "duration_estimator", "eligibility", "admission", "splits", "data", "policy"}
)


class AccountingError(ValueError):
    """Raised on an unusable duration, power, intensity, config or trace."""


@dataclass(frozen=True)
class EnergyConfig:
    """The frozen energy model, as loaded from ``config/energy.json``.

    Carries its own provenance so any result computed from it can name its
    source without a second lookup (R1: a number travels with where it came from).
    """

    p_avg_w: float
    sensitivity_multipliers: tuple[float, ...]
    duration_source_column: str
    schema_version: int
    pinned_by: str
    citations: tuple[Mapping[str, object], ...]
    source_path: Path

    def provenance(self) -> dict[str, object]:
        """A record to embed in any results file this config produced."""
        return {
            "p_avg_w": self.p_avg_w,
            "duration_source_column": self.duration_source_column,
            "pinned_by": self.pinned_by,
            "schema_version": self.schema_version,
            "config_path": str(self.source_path),
            "citations": [dict(c) for c in self.citations],
        }


def load_energy_config(path: str | Path = DEFAULT_ENERGY_CONFIG_PATH) -> EnergyConfig:
    """Load and validate the versioned energy config.

    Rejects an unsupported ``schema_version``, a non-positive ``p_avg_w``, a
    derivation whose factors do not reproduce ``p_avg_w``, and a config carrying
    no citation — DL-007 makes the citation part of the value, not decoration.
    """
    path = Path(path)
    if not path.is_file():
        raise AccountingError(f"energy config not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise AccountingError(f"energy config is not valid JSON: {path} ({exc})") from exc

    version = raw.get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise AccountingError(
            f"energy config schema_version {version!r} != supported "
            f"{SUPPORTED_SCHEMA_VERSION} — the key set changed; update accounting.py "
            f"under a decision-log entry rather than reading it blind ({path})"
        )

    p_avg_w = raw.get("p_avg_w")
    if not _is_real_number(p_avg_w):
        raise AccountingError(f"energy config p_avg_w must be numeric, got {p_avg_w!r} ({path})")
    p_avg_w = float(p_avg_w)
    if not math.isfinite(p_avg_w) or p_avg_w <= 0:
        raise AccountingError(f"energy config p_avg_w must be finite and > 0, got {p_avg_w} ({path})")

    # The pinned wattage is DERIVED (DL-021). Re-multiply its factors so a typo in
    # p_avg_w cannot pass silently as a research constant.
    derivation = raw.get("p_avg_derivation") or {}
    tdp = derivation.get("power_constant_w")
    frac = derivation.get("consumption_percentage_constant")
    if tdp is None or frac is None:
        raise AccountingError(f"energy config is missing its p_avg derivation factors ({path})")
    recomputed = float(tdp) * float(frac)
    if not math.isclose(recomputed, p_avg_w, rel_tol=0.0, abs_tol=1e-9):
        raise AccountingError(
            f"energy config p_avg_w {p_avg_w} does not match its own derivation "
            f"{tdp} * {frac} = {recomputed} ({path})"
        )

    citations = tuple(raw.get("p_avg_citations") or ())
    if not citations:
        raise AccountingError(
            f"energy config carries no p_avg citation — DL-007 requires the power "
            f"constant to be cited, not asserted ({path})"
        )

    multipliers = tuple(float(m) for m in (raw.get("p_avg_sensitivity") or {}).get("multipliers", ()))
    if not multipliers:
        raise AccountingError(f"energy config declares no p_avg sensitivity multipliers ({path})")
    if any((not math.isfinite(m)) or m <= 0 for m in multipliers):
        raise AccountingError(f"p_avg sensitivity multipliers must be finite and > 0, got {multipliers}")

    duration_col = (raw.get("energy_model") or {}).get("duration_source_column")
    if not duration_col:
        raise AccountingError(f"energy config declares no duration source column ({path})")

    return EnergyConfig(
        p_avg_w=p_avg_w,
        sensitivity_multipliers=multipliers,
        duration_source_column=str(duration_col),
        schema_version=int(version),
        pinned_by=str(raw.get("pinned_by", "")),
        citations=citations,
        source_path=path,
    )


def _check_duration(duration_s: float) -> float:
    if not _is_real_number(duration_s):
        raise AccountingError(f"duration_s must be numeric seconds, got {duration_s!r}")
    value = float(duration_s)
    if not math.isfinite(value):
        raise AccountingError(f"duration_s must be finite, got {value!r}")
    if value < 0:
        raise AccountingError(f"duration_s must be >= 0 seconds, got {value}")
    return value


def _check_power(p_avg_w: float) -> float:
    if not _is_real_number(p_avg_w):
        raise AccountingError(f"p_avg_w must be numeric watts, got {p_avg_w!r}")
    value = float(p_avg_w)
    if not math.isfinite(value) or value <= 0:
        raise AccountingError(f"p_avg_w must be finite and > 0 watts, got {value}")
    return value


def energy_kwh(
    duration_s: float,
    p_avg_w: float,
    *,
    n_jobs: int = 1,
    scale_by_jobs: bool = False,
) -> float:
    """Energy for one build, in kWh — ``E = (P_avg/1000) · (duration/3600)`` (§8, DL-007).

    ``duration_s`` is the build's **observed** wall-clock seconds
    (``tr_duration``, max-aggregated per DL-009; DL-010). It is supplied by the
    caller *after* the scheduling decision has been taken — see the module
    docstring on the A1.2 role-1 boundary.

    ``scale_by_jobs`` selects the **DL-010 optional variant**: multiply by the
    build's job count to bracket the parallel-compute under-count that wall-clock
    duration introduces. Off by default — the primary model is unscaled, and the
    variant is reported *alongside* the ``P_avg`` band, never instead of it.
    """
    seconds = _check_duration(duration_s)
    watts = _check_power(p_avg_w)
    kwh = (watts / WATTS_PER_KILOWATT) * (seconds / SECONDS_PER_HOUR)
    if scale_by_jobs:
        if isinstance(n_jobs, bool) or not isinstance(n_jobs, int):
            raise AccountingError(f"n_jobs must be an int, got {n_jobs!r}")
        if n_jobs < 1:
            raise AccountingError(f"n_jobs must be >= 1, got {n_jobs}")
        kwh *= n_jobs
    return kwh


def p_avg_band(config: EnergyConfig) -> tuple[tuple[float, float], ...]:
    """The mandatory ±50% sensitivity band (DL-007): ``((multiplier, p_avg_w), …)``.

    Every carbon result in this study is re-run across this band (P3-T4). The
    multipliers come from the config file, never from this module.
    """
    return tuple((m, config.p_avg_w * m) for m in config.sensitivity_multipliers)


def energy_kwh_band(
    duration_s: float,
    config: EnergyConfig,
    *,
    n_jobs: int = 1,
    scale_by_jobs: bool = False,
) -> dict[float, float]:
    """Energy across the whole ``P_avg`` band, keyed by multiplier (DL-007)."""
    return {
        multiplier: energy_kwh(duration_s, watts, n_jobs=n_jobs, scale_by_jobs=scale_by_jobs)
        for multiplier, watts in p_avg_band(config)
    }


def _check_intensity(intensity_g_per_kwh: float) -> float:
    if not _is_real_number(intensity_g_per_kwh):
        raise AccountingError(f"intensity must be numeric gCO2/kWh, got {intensity_g_per_kwh!r}")
    value = float(intensity_g_per_kwh)
    if not math.isfinite(value):
        raise AccountingError(f"intensity must be finite, got {value!r}")
    if value < 0:
        raise AccountingError(f"intensity must be >= 0 gCO2/kWh, got {value}")
    return value


def carbon_g(energy_kwh_value: float, intensity_g_per_kwh: float) -> float:
    """Carbon for one build, gCO₂e — ``carbon_b = E_b · I(t_sched,b)`` (§8).

    Units: kWh × gCO₂/kWh = gCO₂e. ``I`` is the hour-of-week **mean** intensity of
    the slot the build was *scheduled into* — which is where a deferral decision
    actually shows up in the arithmetic.
    """
    if not _is_real_number(energy_kwh_value):
        raise AccountingError(f"energy must be numeric kWh, got {energy_kwh_value!r}")
    energy = float(energy_kwh_value)
    if not math.isfinite(energy):
        raise AccountingError(f"energy must be finite, got {energy!r}")
    if energy < 0:
        raise AccountingError(f"energy must be >= 0 kWh, got {energy}")
    return energy * _check_intensity(intensity_g_per_kwh)


def carbon_for_slot(
    duration_s: float,
    profile,
    dow: int,
    hour: int,
    p_avg_w: float,
    *,
    n_jobs: int = 1,
    scale_by_jobs: bool = False,
) -> float:
    """§8 end to end: observed duration + scheduled hour-of-week slot → gCO₂e.

    A convenience composition of :func:`energy_kwh` and :func:`carbon_g` over the
    P0-T3 intensity primitive (:func:`scheduler_core.carbon.intensity_for_hour_of_week`).
    ``profile`` is the 168-slot hour-of-week frame; ``(dow, hour)`` is the slot the
    build was **scheduled into**, not the one it arrived in.
    """
    intensity = carbon_mod.intensity_for_hour_of_week(profile, dow, hour)
    return carbon_g(
        energy_kwh(duration_s, p_avg_w, n_jobs=n_jobs, scale_by_jobs=scale_by_jobs),
        intensity,
    )


def _as_carbon_series(carbon_g_values: Iterable[float]) -> list[float]:
    values: list[float] = []
    for i, v in enumerate(carbon_g_values):
        if not _is_real_number(v):
            raise AccountingError(f"carbon value at index {i} must be numeric gCO2e, got {v!r}")
        f = float(v)
        if not math.isfinite(f):
            raise AccountingError(f"carbon value at index {i} must be finite, got {f!r}")
        if f < 0:
            raise AccountingError(f"carbon value at index {i} must be >= 0 gCO2e, got {f}")
        values.append(f)
    return values


def carbon_per_1000_builds(carbon_g_values: Iterable[float]) -> float:
    """``(Σ_b carbon_b / N) · 1000`` — estimated gCO₂e per 1,000 builds (§6).

    Reported in absolute gCO₂e and, via :func:`pct_change_vs_baseline`, as a
    percentage change against the static baseline (strategy ①).
    """
    values = _as_carbon_series(carbon_g_values)
    if not values:
        raise AccountingError("carbon_per_1000_builds needs at least one build")
    return (sum(values) / len(values)) * 1000.0


def pct_change_vs_baseline(value: float, baseline: float) -> float:
    """Percent change of a metric against the static baseline (§6).

    Negative = a saving. Undefined against a zero baseline, which is an error
    rather than an infinity — a carbon table with a divide-by-zero in it is not a
    result.
    """
    if isinstance(baseline, bool) or not isinstance(baseline, (int, float)):
        raise AccountingError(f"baseline must be numeric, got {baseline!r}")
    base = float(baseline)
    if not math.isfinite(base) or base == 0.0:
        raise AccountingError(f"pct change is undefined against baseline {baseline!r}")
    return (float(value) - base) / base * 100.0


def sci_per_successful_commit(
    carbon_g_values: Sequence[float],
    labels: Sequence[int],
) -> float:
    """GSF SCI — ``(Σ_b E_b · I(t_sched,b)) / N_success``, gCO₂e per successful commit (§6).

    Note the asymmetry, which is the point of the metric: the **numerator runs
    over every build** in the trace (all the carbon the pipeline spent), while the
    **denominator counts only successful ones** (``y = 0``) — the functional unit
    the pipeline actually delivered. A strategy that burns carbon on builds that
    fail is charged for it.

    ``labels`` uses the frozen label convention (DL-009, eval_protocol §1):
    ``y = 1`` failure (``tr_status ∈ {failed, errored}``), ``y = 0`` pass.

    This is the **operational** SCI; the GSF embodied term ``M`` is excluded —
    laptop-scale, no provisioned hardware to amortise — and that exclusion is
    declared in the threats chapter (spec §6).
    """
    values = _as_carbon_series(carbon_g_values)
    labels = list(labels)
    if len(values) != len(labels):
        raise AccountingError(
            f"carbon values and labels must align one-to-one: {len(values)} vs {len(labels)}"
        )
    if not values:
        raise AccountingError("sci_per_successful_commit needs at least one build")
    for i, y in enumerate(labels):
        # Integral values only, so a probability (0.5) or a raw `tr_status` string
        # cannot be mistaken for a label.
        if not _is_real_number(y) or not math.isfinite(float(y)):
            raise AccountingError(f"label at index {i} must be 0 (pass) or 1 (failure), got {y!r}")
        if not float(y).is_integer() or int(y) not in (0, 1):
            raise AccountingError(f"label at index {i} must be 0 (pass) or 1 (failure), got {y!r}")
    n_success = sum(1 for y in labels if int(y) == 0)
    if n_success == 0:
        raise AccountingError(
            "SCI is undefined for a trace with no successful builds (N_success = 0)"
        )
    return sum(values) / n_success

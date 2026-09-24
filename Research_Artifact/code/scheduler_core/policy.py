"""Stage 2 — ``decide()`` as a deterministic evaluator of ``policy_spec.yaml``.

This module is the **shared decision core** required by frozen invariant 5: the
replay simulator (P2-T4) and the live prototype (P4) both call the ``decide()``
below, and neither may fork its logic. It is also the place where Layer 0-A
invariant 7 is enforced mechanically — *the policy is evidence-derived, never
hand-tuned* — so the module deliberately contains **no numeric threshold of its
own**. Every constant it applies is read from a loaded :class:`PolicySpec`, and
where the spec is silent the module **raises** rather than falling back on a
built-in default. A silent default is a hand-tuned threshold wearing a disguise.

**The two stages, and why the order is structural (invariant 1: risk ≠ urgency).**

```text
Stage 1  deterministic eligibility gate (scheduler_core.eligibility) — never ML
             ↓ deferrable only
Stage 2  duration-only fallback  OR  SE-informed selective policy
             ↓
         lowest-carbon slot reachable within the policy-bounded window
```

Stage 1 runs **first and unconditionally**. A non-deferrable build returns
``run_now`` *without Stage 2 being consulted at all* — not with Stage 2 consulted
and then overridden (DL-022 §6). The distinction matters: an override can be
reordered by a later edit, whereas an early return cannot be, and
``tests/test_policy.py`` asserts the early return rather than merely the outcome.

**What ``decide()`` may not see (eval_protocol.md §A1.2).**
The current build's ``tr_duration`` / ``tr_log_buildduration`` are *outcomes of
the build being scheduled*. They are permitted in accounting, as historical
training labels, and as a labelled oracle bound — never here. Every call screens
the build mapping against the same blocklist the feature matrix uses
(:func:`scheduler_core.features.is_blocklisted`) and **raises** on a hit rather
than ignoring it: a leak that is quietly dropped is a leak that recurs. What
``decide()`` does see is ``d_hat_seconds``, the *commit-time estimate* produced by
the P1-T4 control — which is what "beyond expected build duration" means (DL-012).

**Purity.** ``decide()`` reads no file, holds no state, performs no I/O and never
consults a clock. It works in **hour-of-week space**: the caller supplies the
arrival slot, and a deferral is returned as an *offset in hours* from that slot,
which the caller converts to an absolute timestamp. That keeps the function
deterministic and replayable, and it is why the same call can serve a 2014 replay
build and a live 2026 webhook without branching.

**Bootstrap safety (DL-022 §4).** P2-T5 has not fitted the real spec yet, so this
module ships ``config/policy_spec.bootstrap.yaml`` to be testable. That file
declares ``provenance.fitted: false``, and **every consumer that produces a
reported number must load with** ``require_fitted=True``, which refuses it. The
bootstrap is usable for tests, examples and wiring; it is structurally unusable
for results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from . import carbon as carbon_mod
from . import eligibility as eligibility_mod
from .features import is_blocklisted

#: Where the specs live. The *fitted* spec is written here by P2-T5's
#: `fit_policy.py`; the bootstrap sits beside it under a distinct name so it can
#: never be the default (DL-022 §4).
_CONFIG_DIR = Path(__file__).resolve().parent / "config"
DEFAULT_POLICY_SPEC_PATH = _CONFIG_DIR / "policy_spec.yaml"
BOOTSTRAP_POLICY_SPEC_PATH = _CONFIG_DIR / "policy_spec.bootstrap.yaml"

#: The `schema_version`s this module implements. v1 is DL-022 §2's (the bootstrap
#: spec); v2 is DL-024 §7's — v1 plus the recorded sweep grids and per-value
#: provenance. A fitted spec must be v2.
SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1, 2)
FITTED_SCHEMA_VERSION: int = 2

#: The two Stage-2 paths. `duration_only_fallback` is A1.6's central null and, per
#: results/p1/admission.json, the path the fitted spec is expected to take.
POLICY_PATHS: tuple[str, ...] = ("duration_only_fallback", "se_informed")

#: Window forms A1.8 permits without further justification. `linear` is §7's
#: `w(p) = w_max * (1 - p)`, retained in full by A1.8 as default and fallback.
WINDOW_FORMS: tuple[str, ...] = ("linear",)

#: The closed schema. A key absent from here is rejected, which is what makes
#: invariant 7 checkable: a threshold that is not in the schema cannot be
#: smuggled in, and one that is must declare where it came from (DL-022 §2).
_SCHEMA: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "stage1": {"required": ("variant",), "optional": ()},
    "duration_only": {"required": ("d_threshold_seconds", "w_max_hours"), "optional": ()},
    "se_informed": {
        "required": ("window_form", "w_max_hours", "d_threshold_seconds", "admitted_families"),
        "optional": (),
    },
    "provenance": {
        "required": ("fitted", "fitted_by", "fitted_on", "sources"),
        "optional": ("generated", "notes"),
    },
}
_TOP_LEVEL_REQUIRED: tuple[str, ...] = ("schema_version", "policy_path", "stage1", "provenance")
_TOP_LEVEL_OPTIONAL: tuple[str, ...] = ("duration_only", "se_informed")

#: Schema v2 (DL-024 §7): v1's blocks unchanged, plus a required `sweep` block and
#: stricter provenance. Kept as a delta over v1 so the two cannot drift apart.
_SCHEMA_V2: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    **_SCHEMA,
    "provenance": {
        "required": ("fitted", "fitted_by", "fitted_on", "sources", "values", "command",
                     "seed", "generated", "test_split_read"),
        "optional": ("notes",),
    },
    "sweep": {
        "required": ("source", "grid_sha256", "frozen_by", "w_max_hours",
                     "d_threshold_seconds", "tau_skip", "blanket_w_max_hours"),
        "optional": (),
    },
}
_TOP_LEVEL_REQUIRED_V2: tuple[str, ...] = _TOP_LEVEL_REQUIRED + ("sweep",)

#: The sweep grids recorded in a v2 spec — resolution for P3, never read by decide().
_SWEEP_GRIDS: tuple[str, ...] = ("w_max_hours", "d_threshold_seconds", "tau_skip")

#: The blocks whose numeric fields are policy values and so need a provenance entry.
_VALUE_BLOCKS: tuple[str, ...] = ("duration_only", "se_informed")
_VALUE_ENTRY_KEYS: frozenset[str] = frozenset({"source", "rule"})

#: The hour-of-week horizon. Not a policy threshold — it is the width of the
#: carbon profile itself (`carbon.N_SLOTS`), so a window may never exceed one week.
_MAX_WINDOW_HOURS: int = carbon_mod.N_SLOTS - 1


class PolicyError(ValueError):
    """Raised on an invalid spec, an unusable build, or a leaked outcome column."""


class PolicyLeakageError(PolicyError):
    """Raised when a build handed to ``decide()`` carries an outcome column.

    A distinct type because this is not a configuration mistake — it is the
    A1.2 boundary being crossed, and callers should never catch it broadly.
    """


# --------------------------------------------------------------------------- #
# The spec: loading and strict validation (S3; DL-022 §2, §3).
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PolicySpec:
    """A validated policy spec. Every threshold ``decide()`` applies lives here."""

    schema_version: int
    policy_path: str
    stage1_variant: str
    duration_only: Mapping[str, Any]
    se_informed: Mapping[str, Any]
    provenance: Mapping[str, Any]
    source_path: Path
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def fitted(self) -> bool:
        """True only for a spec `fit_policy.py` produced from evidence."""
        return bool(self.provenance.get("fitted", False))

    def active(self) -> Mapping[str, Any]:
        """The parameter block for the selected path."""
        return self.duration_only if self.policy_path == "duration_only_fallback" else self.se_informed

    def provenance_record(self) -> dict[str, Any]:
        """A record to embed in any results file this spec drove."""
        return {
            "policy_path": self.policy_path,
            "stage1_variant": self.stage1_variant,
            "fitted": self.fitted,
            "fitted_by": self.provenance.get("fitted_by"),
            "fitted_on": self.provenance.get("fitted_on"),
            "sources": list(self.provenance.get("sources") or ()),
            "spec_path": str(self.source_path),
            "schema_version": self.schema_version,
        }


def _require_number(block: str, key: str, value: Any, *, minimum: float, maximum: float | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{block}.{key} must be numeric, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise PolicyError(f"{block}.{key} must be finite, got {number!r}")
    if number < minimum:
        raise PolicyError(f"{block}.{key} must be >= {minimum}, got {number}")
    if maximum is not None and number > maximum:
        raise PolicyError(f"{block}.{key} must be <= {maximum}, got {number}")
    return number


def _validate_block(name: str, block: Any,
                    schema: Mapping[str, Mapping[str, tuple[str, ...]]] = _SCHEMA) -> Mapping[str, Any]:
    if not isinstance(block, Mapping):
        raise PolicyError(f"spec block {name!r} must be a mapping, got {type(block).__name__}")
    spec = schema[name]
    allowed = set(spec["required"]) | set(spec["optional"])
    unknown = sorted(set(block) - allowed)
    if unknown:
        raise PolicyError(
            f"unknown key(s) {unknown} in spec block {name!r}; the schema is closed "
            f"(DL-022 §2) — a threshold not in the schema must not be smuggled in"
        )
    missing = sorted(set(spec["required"]) - set(block))
    if missing:
        raise PolicyError(f"spec block {name!r} is missing required key(s) {missing}")
    return block


def _validate_sweep(sweep: Mapping[str, Any], path: Path) -> None:
    """v2's recorded grids: shape only. They are resolution for P3, not thresholds."""
    for key in _SWEEP_GRIDS:
        values = sweep[key]
        if not isinstance(values, (list, tuple)) or not values:
            raise PolicyError(f"sweep.{key} must be a non-empty list ({path})")
        numbers = [_require_number("sweep", key, v, minimum=0.0, maximum=None) for v in values]
        if numbers != sorted(set(numbers)):
            raise PolicyError(f"sweep.{key} must be strictly increasing, got {list(values)} ({path})")
    _require_number("sweep", "blanket_w_max_hours", sweep["blanket_w_max_hours"],
                    minimum=0.0, maximum=float(_MAX_WINDOW_HOURS))
    digest = sweep["grid_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or set(digest) - set("0123456789abcdef"):
        raise PolicyError(f"sweep.grid_sha256 must be a lowercase sha256 hex digest ({path})")
    for key in ("source", "frozen_by"):
        if not isinstance(sweep[key], str) or not sweep[key]:
            raise PolicyError(f"sweep.{key} must be a non-empty string ({path})")


def _validate_value_provenance(raw: Mapping[str, Any], values: Any, path: Path) -> None:
    """Every numeric policy value has exactly one provenance entry, and no entry is orphaned.

    Keys are ``"<block>.<field>"``. Each entry names the ``results/`` file(s) the
    value came from (``source``) and the rule that turned them into it (``rule``)
    — invariant 7, made checkable per value rather than per file (DL-024 §7).
    """
    if not isinstance(values, Mapping):
        raise PolicyError(f"provenance.values must be a mapping of '<block>.<field>' entries ({path})")
    numeric = {
        f"{block}.{key}"
        for block in _VALUE_BLOCKS if isinstance(raw.get(block), Mapping)
        for key, value in raw[block].items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    missing = sorted(numeric - set(values))
    if missing:
        raise PolicyError(
            f"numeric spec value(s) {missing} have no provenance.values entry — every value must "
            f"name the results/ file it traces to (invariant 7, DL-024 §7) ({path})"
        )
    orphans = sorted(set(values) - numeric)
    if orphans:
        raise PolicyError(f"provenance.values entries {orphans} name no numeric spec value ({path})")
    for key, entry in values.items():
        if not isinstance(entry, Mapping) or set(entry) != _VALUE_ENTRY_KEYS:
            raise PolicyError(
                f"provenance.values[{key!r}] must carry exactly {sorted(_VALUE_ENTRY_KEYS)} ({path})")
        sources = entry["source"]
        if not isinstance(sources, (list, tuple)) or not sources or \
                not all(isinstance(s, str) and s for s in sources):
            raise PolicyError(f"provenance.values[{key!r}].source must be a non-empty list of paths ({path})")
        if not isinstance(entry["rule"], str) or not entry["rule"]:
            raise PolicyError(f"provenance.values[{key!r}].rule must be a non-empty string ({path})")


def load_policy_spec(
    path: str | Path = DEFAULT_POLICY_SPEC_PATH,
    *,
    require_fitted: bool = True,
) -> PolicySpec:
    """Load and strictly validate a policy spec.

    ``require_fitted`` defaults to **True**: the safe direction. Every consumer
    that produces a reported number must keep that default, so an unfitted
    bootstrap spec can never silently drive a result (DL-022 §4). Tests,
    examples and wiring checks pass ``require_fitted=False`` explicitly, which
    makes the exception visible at the call site.

    Rejects, as errors and never warnings: a missing file; a document that is not
    a mapping; an unknown top-level or nested key; a missing required key; an
    unimplemented ``schema_version``; an unknown ``policy_path``, ``stage1.variant``
    or ``window_form``; an absent, non-numeric, non-finite or out-of-range
    threshold; a missing ``provenance`` block; and an ``se_informed`` spec that
    admits no family.
    """
    path = Path(path)
    if not path.is_file():
        raise PolicyError(f"policy spec not found: {path}")
    # safe_load only — never load/full_load, so a spec file cannot construct a
    # Python object (DL-022 §1).
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise PolicyError(f"policy spec is not valid YAML: {path} ({exc})") from exc
    return spec_from_mapping(raw, source_path=path, require_fitted=require_fitted)


def spec_from_mapping(
    raw: Any,
    *,
    source_path: str | Path,
    require_fitted: bool = True,
) -> PolicySpec:
    """Validate an in-memory spec mapping with exactly the checks a file gets.

    :func:`load_policy_spec` is this function plus a YAML read. It exists so the
    replay simulator can evaluate a *derived* spec — the loaded one with a sweep
    grid point substituted (DL-023 §1) — without a second validator: a derived
    spec passes the same closed schema, the same range checks and the same
    ``require_fitted`` quarantine as the file it came from. ``source_path`` names
    the file the mapping was derived from, so provenance still points at it.
    """
    path = Path(source_path)
    if not isinstance(raw, Mapping):
        raise PolicyError(f"policy spec must be a YAML mapping, got {type(raw).__name__}: {path}")

    version = raw.get("schema_version")
    if isinstance(version, bool) or version not in SUPPORTED_SCHEMA_VERSIONS:
        raise PolicyError(
            f"policy spec schema_version {version!r} is not one of the supported "
            f"{SUPPORTED_SCHEMA_VERSIONS} — the key set changed; update policy.py under a "
            f"decision-log entry rather than reading it blind ({path})"
        )
    v2 = version == FITTED_SCHEMA_VERSION
    schema = _SCHEMA_V2 if v2 else _SCHEMA
    top_required = _TOP_LEVEL_REQUIRED_V2 if v2 else _TOP_LEVEL_REQUIRED

    unknown = sorted(set(raw) - set(top_required) - set(_TOP_LEVEL_OPTIONAL))
    if unknown:
        raise PolicyError(f"unknown top-level key(s) {unknown} in {path}; the schema is closed")
    missing = sorted(set(top_required) - set(raw))
    if missing:
        raise PolicyError(f"policy spec is missing required key(s) {missing}: {path}")

    policy_path = raw["policy_path"]
    if policy_path not in POLICY_PATHS:
        raise PolicyError(f"unknown policy_path {policy_path!r}; expected one of {POLICY_PATHS} ({path})")

    stage1 = _validate_block("stage1", raw["stage1"])
    variant = stage1["variant"]
    if variant not in eligibility_mod.VARIANTS:
        raise PolicyError(
            f"unknown stage1.variant {variant!r}; expected one of {eligibility_mod.VARIANTS} ({path})"
        )

    provenance = _validate_block("provenance", raw["provenance"], schema)
    if not isinstance(provenance["fitted"], bool):
        raise PolicyError(f"provenance.fitted must be a boolean, got {provenance['fitted']!r} ({path})")
    if not isinstance(provenance["sources"], (list, tuple)):
        raise PolicyError(f"provenance.sources must be a list, got {provenance['sources']!r} ({path})")
    if provenance["fitted"] and not provenance["sources"]:
        raise PolicyError(
            f"a fitted spec must list the results/ file(s) its values trace to in "
            f"provenance.sources — Layer 0-A invariant 7 ({path})"
        )
    if provenance["fitted"] and not v2:
        raise PolicyError(
            f"a fitted spec must be schema_version {FITTED_SCHEMA_VERSION}: only v2 carries the "
            f"per-value provenance and the recorded sweep grids (DL-024 §7) ({path})"
        )
    if v2:
        if provenance["test_split_read"] is not False:
            raise PolicyError(
                f"provenance.test_split_read must be false — the policy is frozen before the test "
                f"split is opened (DL-012, §A1.7) ({path})"
            )
        _validate_sweep(_validate_block("sweep", raw["sweep"], schema), path)

    # Validate whichever block(s) are present; the ACTIVE one must be present.
    duration_only: Mapping[str, Any] = {}
    se_informed: Mapping[str, Any] = {}
    if "duration_only" in raw:
        duration_only = _validate_block("duration_only", raw["duration_only"])
        _require_number("duration_only", "d_threshold_seconds", duration_only["d_threshold_seconds"],
                        minimum=0.0, maximum=None)
        _require_number("duration_only", "w_max_hours", duration_only["w_max_hours"],
                        minimum=0.0, maximum=float(_MAX_WINDOW_HOURS))
    if "se_informed" in raw:
        se_informed = _validate_block("se_informed", raw["se_informed"])
        if se_informed["window_form"] not in WINDOW_FORMS:
            raise PolicyError(
                f"unknown se_informed.window_form {se_informed['window_form']!r}; expected one of "
                f"{WINDOW_FORMS}. A richer form may replace §7's linear window ONLY where "
                f"results/p1/ justifies it and fit_policy.py records why (A1.8) ({path})"
            )
        _require_number("se_informed", "d_threshold_seconds", se_informed["d_threshold_seconds"],
                        minimum=0.0, maximum=None)
        _require_number("se_informed", "w_max_hours", se_informed["w_max_hours"],
                        minimum=0.0, maximum=float(_MAX_WINDOW_HOURS))
        if not isinstance(se_informed["admitted_families"], (list, tuple)):
            raise PolicyError(f"se_informed.admitted_families must be a list ({path})")

    if policy_path == "duration_only_fallback" and not duration_only:
        raise PolicyError(f"policy_path is duration_only_fallback but no duration_only block is present ({path})")
    if policy_path == "se_informed":
        if not se_informed:
            raise PolicyError(f"policy_path is se_informed but no se_informed block is present ({path})")
        if not se_informed["admitted_families"]:
            raise PolicyError(
                f"policy_path is se_informed but admitted_families is empty. An SE path with no "
                f"admitted family is the duration-only fallback under another name; §A1.7's null "
                f"path must be declared as duration_only_fallback ({path})"
            )

    if v2:
        _validate_value_provenance(raw, provenance["values"], path)

    spec = PolicySpec(
        schema_version=int(version),
        policy_path=str(policy_path),
        stage1_variant=str(variant),
        duration_only=duration_only,
        se_informed=se_informed,
        provenance=provenance,
        source_path=path,
        raw=raw,
    )
    if require_fitted and not spec.fitted:
        raise PolicyError(
            f"refusing to load an UNFITTED policy spec with require_fitted=True: {path}. "
            f"provenance.fitted is false, so this spec's thresholds are not evidence-derived "
            f"(Layer 0-A invariant 7, DL-022 §4). Only tests, examples and wiring checks may "
            f"pass require_fitted=False."
        )
    return spec


# --------------------------------------------------------------------------- #
# The decision.
# --------------------------------------------------------------------------- #

ACTIONS: tuple[str, str] = ("run_now", "defer")


@dataclass(frozen=True)
class Decision:
    """One build's decision, carrying enough provenance to audit it alone.

    ``defer_until`` is **relative**, not a timestamp: ``decide()`` never consults a
    clock, so it returns the offset in hours from the build's arrival slot plus
    the hour-of-week slot that offset lands on. The caller (simulator or API)
    converts that to an absolute time using the arrival time it already holds.
    ``None`` for ``run_now``.
    """

    action: str
    defer_until: Mapping[str, Any] | None
    reason: str
    grid_gco2_now: float
    # --- provenance the simulator records per build (P2-T4 S1) ---
    eligible: bool
    stage1_rule: str
    policy_path: str
    d_hat_seconds: float | None
    p_hat: float | None
    window_hours: float
    delay_hours: float
    scheduled_slot: int
    grid_gco2_scheduled: float
    spec_fitted: bool

    def as_dict(self) -> dict[str, Any]:
        """Flat record for the decision log / API response."""
        return {
            "action": self.action,
            "defer_until": dict(self.defer_until) if self.defer_until is not None else None,
            "reason": self.reason,
            "grid_gCO2_now": self.grid_gco2_now,
            "eligible": self.eligible,
            "stage1_rule": self.stage1_rule,
            "policy_path": self.policy_path,
            "d_hat_seconds": self.d_hat_seconds,
            "p_hat": self.p_hat,
            "window_hours": self.window_hours,
            "delay_hours": self.delay_hours,
            "scheduled_slot": self.scheduled_slot,
            "grid_gCO2_scheduled": self.grid_gco2_scheduled,
            "spec_fitted": self.spec_fitted,
        }


def assert_no_outcome_columns(build: Mapping[str, Any]) -> None:
    """Fail loudly if a build mapping carries an outcome column (§A1.2).

    Uses the *same* blocklist the feature matrix enforces
    (:func:`scheduler_core.features.is_blocklisted`) rather than a private copy,
    so the two cannot drift apart. Raising — rather than dropping the key — is
    deliberate: a leak that is silently ignored is a leak that comes back.
    """
    offences = sorted(k for k in build if is_blocklisted(str(k)))
    if offences:
        raise PolicyLeakageError(
            f"decide() was handed outcome column(s) {offences}. These are outcomes of the build "
            f"being scheduled; eval_protocol.md §A1.2 permits them only in accounting, as historical "
            f"training labels, or as a labelled oracle bound — never as a decision input. Pass the "
            f"commit-time estimate `d_hat_seconds` instead."
        )


def _require_slot(build: Mapping[str, Any]) -> tuple[int, int]:
    for key in ("arrival_dow", "arrival_hour"):
        if key not in build:
            raise PolicyError(f"build is missing {key!r}; decide() works in hour-of-week space")
    dow, hour = build["arrival_dow"], build["arrival_hour"]
    if isinstance(dow, bool) or not isinstance(dow, int) or not 0 <= dow <= 6:
        raise PolicyError(f"arrival_dow must be an int in [0, 6] (Mon=0), got {dow!r}")
    if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
        raise PolicyError(f"arrival_hour must be an int in [0, 23], got {hour!r}")
    return dow, hour


def _require_d_hat(build: Mapping[str, Any]) -> float:
    if "d_hat_seconds" not in build:
        raise PolicyError(
            "build is missing 'd_hat_seconds' — the commit-time duration estimate. Stage 2 is "
            "defined on the ESTIMATE, never the observed duration (§A1.1, DL-012 §2)."
        )
    value = build["d_hat_seconds"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"d_hat_seconds must be numeric, got {value!r}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise PolicyError(f"d_hat_seconds must be finite and >= 0, got {number}")
    return number


def _require_p_hat(build: Mapping[str, Any]) -> float:
    if "p_hat" not in build:
        raise PolicyError(
            "the se_informed path needs 'p_hat', the calibrated failure probability. "
            "Its absence is an error, not a reason to default to a window."
        )
    value = build["p_hat"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"p_hat must be numeric, got {value!r}")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise PolicyError(f"p_hat must be a probability in [0, 1], got {number}")
    return number


def window_hours(spec: PolicySpec, p_hat: float | None) -> float:
    """The permitted delay window, in hours, clipped to ``[0, w_max]``.

    * ``duration_only_fallback`` — a flat ``w_max`` (A1.6: the window is not a
      function of any score, because there is no admitted score).
    * ``se_informed`` with ``window_form: linear`` — §7 / A1.8's
      ``w(p̂) = w_max · (1 − p̂)``: monotone non-increasing in ``p̂``, so a build
      more likely to fail never waits longer.

    ``w_max`` comes from the spec. No window constant is defined in this module.
    """
    block = spec.active()
    w_max = float(block["w_max_hours"])
    if spec.policy_path == "duration_only_fallback":
        return w_max                      # already bounded to [0, 167] by the loader
    if p_hat is None:
        raise PolicyError("the se_informed window needs p_hat")
    raw = w_max * (1.0 - p_hat)
    return max(0.0, min(raw, w_max))      # the [0, W_max] clip §7 requires


def decide(
    build: Mapping[str, Any],
    carbon: Any,
    config: PolicySpec,
) -> Decision:
    """Decide whether one build runs now or waits, and until when.

    Pure and deterministic: no file access, no clock, no state. The same
    ``(build, carbon, config)`` always yields the same :class:`Decision`.

    ``build`` supplies commit-time inputs only — ``gh_is_pr`` and ``git_branch``
    for Stage 1, ``arrival_dow`` / ``arrival_hour`` for the hour-of-week slot,
    ``d_hat_seconds`` for the duration control, and ``p_hat`` on the SE path.
    ``carbon`` is the 168-slot hour-of-week profile. ``config`` is a validated
    :class:`PolicySpec` — every threshold applied below comes from it.
    """
    if not isinstance(config, PolicySpec):
        raise PolicyError(f"config must be a validated PolicySpec, got {type(config).__name__}")

    # §A1.2 first: refuse an outcome column before anything else happens, so a
    # leaking caller cannot get a decision out of this function at all.
    assert_no_outcome_columns(build)

    dow, hour = _require_slot(build)
    arrival_slot = carbon_mod.slot_of(dow, hour)
    grid_now = carbon_mod.intensity_for_hour_of_week(carbon, dow, hour)

    def _run_now(reason: str, *, eligible: bool, rule: str,
                 d_hat: float | None, p_hat: float | None, window: float) -> Decision:
        return Decision(
            action="run_now", defer_until=None, reason=reason, grid_gco2_now=grid_now,
            eligible=eligible, stage1_rule=rule, policy_path=config.policy_path,
            d_hat_seconds=d_hat, p_hat=p_hat, window_hours=window, delay_hours=0.0,
            scheduled_slot=arrival_slot, grid_gco2_scheduled=grid_now,
            spec_fitted=config.fitted,
        )

    # ---- Stage 1: deterministic, unconditional, and it RETURNS on failure ----
    # Not "evaluate Stage 2 then override": a non-deferrable build leaves here
    # without Stage 2 being consulted at all (invariant 1, DL-022 §6).
    gate = eligibility_mod.classify(
        build.get("gh_is_pr"), build.get("git_branch"), variant=config.stage1_variant
    )
    if not gate.eligible:
        return _run_now(
            f"stage1[{config.stage1_variant}]: NOT deferrable ({gate.rule}) — {gate.reason}. "
            f"Stage 2 not consulted. Running now at slot {arrival_slot} "
            f"({carbon_mod.DOW_NAMES[dow]} {hour:02d}:00, {grid_now:.4f} gCO2/kWh).",
            eligible=False, rule=gate.rule, d_hat=None, p_hat=None, window=0.0,
        )

    # ---- Stage 2: only already-deferrable builds reach this line ----
    d_hat = _require_d_hat(build)
    p_hat = _require_p_hat(build) if config.policy_path == "se_informed" else None

    block = config.active()
    d_threshold = float(block["d_threshold_seconds"])
    path_label = (
        "duration_only_fallback" if config.policy_path == "duration_only_fallback"
        else f"se_informed(window_form={block['window_form']}, "
             f"admitted={list(block['admitted_families'])})"
    )

    # A1.6: defer iff d_hat >= d_threshold. Deferring a short build pays the full
    # latency cost for a negligible carbon gain.
    if d_hat < d_threshold:
        return _run_now(
            f"stage1[{config.stage1_variant}]: deferrable ({gate.rule}). "
            f"stage2[{path_label}]: d_hat={d_hat:.1f}s < d_threshold={d_threshold:.1f}s "
            f"-> not worth deferring. Running now at slot {arrival_slot} "
            f"({carbon_mod.DOW_NAMES[dow]} {hour:02d}:00, {grid_now:.4f} gCO2/kWh).",
            eligible=True, rule=gate.rule, d_hat=d_hat, p_hat=p_hat, window=0.0,
        )

    window = window_hours(config, p_hat)
    window_note = (
        f"window={window:.4f}h (flat w_max={float(block['w_max_hours']):.4f})"
        if config.policy_path == "duration_only_fallback"
        else f"window={window:.4f}h = w_max {float(block['w_max_hours']):.4f} * (1 - p_hat {p_hat:.6f})"
    )

    offset, slot, grid_scheduled = carbon_mod.lowest_carbon_slot(
        carbon, dow, hour, int(math.floor(window))
    )

    # Offset 0 means the greenest reachable slot IS the arrival slot. Deferring by
    # zero hours is running now, and calling it a deferral would inflate the
    # deferral rate with builds that never actually waited.
    if offset == 0:
        return _run_now(
            f"stage1[{config.stage1_variant}]: deferrable ({gate.rule}). "
            f"stage2[{path_label}]: d_hat={d_hat:.1f}s >= d_threshold={d_threshold:.1f}s, "
            f"{window_note}, but the greenest reachable slot IS the arrival slot "
            f"{arrival_slot} ({carbon_mod.DOW_NAMES[dow]} {hour:02d}:00, "
            f"{grid_now:.4f} gCO2/kWh) -> running now.",
            eligible=True, rule=gate.rule, d_hat=d_hat, p_hat=p_hat, window=window,
        )

    target_dow, target_hour = slot // 24, slot % 24
    return Decision(
        action="defer",
        defer_until={
            "offset_hours": int(offset),
            "slot": int(slot),
            "dow": int(target_dow),
            "hour": int(target_hour),
        },
        reason=(
            f"stage1[{config.stage1_variant}]: deferrable ({gate.rule}). "
            f"stage2[{path_label}]: d_hat={d_hat:.1f}s >= d_threshold={d_threshold:.1f}s, "
            f"{window_note}. Greenest reachable slot is {slot} "
            f"({carbon_mod.DOW_NAMES[target_dow]} {target_hour:02d}:00, "
            f"{grid_scheduled:.4f} gCO2/kWh) at +{offset}h, vs {grid_now:.4f} gCO2/kWh now "
            f"-> deferring {offset}h."
        ),
        grid_gco2_now=grid_now,
        eligible=True,
        stage1_rule=gate.rule,
        policy_path=config.policy_path,
        d_hat_seconds=d_hat,
        p_hat=p_hat,
        window_hours=window,
        delay_hours=float(offset),
        scheduled_slot=int(slot),
        grid_gco2_scheduled=float(grid_scheduled),
        spec_fitted=config.fitted,
    )

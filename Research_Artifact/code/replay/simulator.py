"""Trace-driven replay simulator — six strategies on identical traces (P2-T4).

This module replays historical TravisTorrent builds, in ``gh_build_started_at``
order, through every strategy of Layer 0-A and every point of its predeclared
sweep grid, and emits one tidy record per **build × strategy × grid point**
(DL-023). The aggregates of ``eval_protocol.md`` §6 / §A1.5 are computed from
those records, never from anything the strategies report about themselves.

**One shared core (invariant 5).** Every strategy that schedules does so through
:func:`scheduler_core.policy.decide`, under a spec *derived* from the loaded one
by substituting a grid point and re-validating it through the same closed-schema
validator a spec file gets (:func:`scheduler_core.policy.spec_from_mapping`).
Nothing here re-implements Stage 1 or Stage 2:

====  ===========================  ==============================================
 #    strategy                     operational definition (DL-023 §1)
====  ===========================  ==============================================
 ①    static                       every build ``run_now`` at arrival
 ②    blanket carbon-aware         ``decide()``, ``d_threshold = 0``, whole-week
                                   horizon (167 h); gated (author decision)
 ③    eligibility-only             ``decide()``, ``d_threshold = 0``, ``w_max ∈ W``
 ④a   duration-control (est.)      ``decide()``, ``(d_threshold, w_max) ∈ D × W``,
                                   ``d̂`` from the ④a regressor
 ④b   duration-control (prior)     the same, ``d̂`` from the ④b project prior
 ⑤    SE-informed policy           ``decide()`` under the **loaded** spec, its
                                   active block set to each point of ``D × W``
 ⑥    risk-only skip               Stage 1 first; eligible builds with
                                   ``p̂ < τ_skip`` are skipped (author decision)
====  ===========================  ==============================================

**What ``decide()`` sees, and what it cannot (eval_protocol §A1.2).** The
decision input is built from an explicit whitelist, :data:`DECISION_INPUTS`.
The observed ``tr_duration`` and the outcome ``y_fail`` ride on the trace for
**accounting only** — they are read *after* ``decide()`` has returned, and are
never offered to it (and ``decide()`` would raise if they were). A metamorphic
test in ``tests/test_simulator.py`` perturbs both and requires every decision to
be unchanged.

**Determinism.** Every (strategy, grid point) is computed into its own part file
keyed by a run fingerprint; a resumed run reuses a part only when its
fingerprint matches, so resuming can save time but never change a byte. The
final records file is assembled in a fixed order and gzip-compressed with its
timestamp zeroed, so two runs from the same inputs are byte-identical.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from scheduler_core import accounting
from scheduler_core import carbon as carbon_mod
from scheduler_core import eligibility, policy

GRID_PATH = Path(__file__).resolve().parent / "sweep_grid.json"
SUPPORTED_GRID_SCHEMA: int = 1

# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #

#: Canonical order. Records, summaries and part files all follow it.
STRATEGIES: tuple[str, ...] = (
    "1_static",
    "2_blanket_carbon_aware",
    "3_eligibility_only",
    "4a_duration_estimator",
    "4b_duration_prior",
    "5_se_informed_policy",
    "6_risk_only_skip",
)

STRATEGY_LABELS: Mapping[str, str] = {
    "1_static": "① static",
    "2_blanket_carbon_aware": "② blanket carbon-aware (gated, whole week)",
    "3_eligibility_only": "③ eligibility-only",
    "4a_duration_estimator": "④a duration-control (estimator)",
    "4b_duration_prior": "④b duration-control (project prior)",
    "5_se_informed_policy": "⑤ SE-informed policy (loaded spec)",
    "6_risk_only_skip": "⑥ risk-only skip (eligible only)",
}

#: Which d̂ column each strategy hands to decide(). ⑤ uses the primary form,
#: resolved from the trace's provenance at run time.
_D_HAT_COLUMN: Mapping[str, str] = {
    "2_blanket_carbon_aware": "d_hat_4b_seconds",
    "3_eligibility_only": "d_hat_4b_seconds",
    "4a_duration_estimator": "d_hat_4a_seconds",
    "4b_duration_prior": "d_hat_4b_seconds",
}

ACTIONS: tuple[str, ...] = ("run_now", "defer", "skip")


class SimulatorError(ValueError):
    """Raised on an invalid grid, trace, setting or run state."""


# --------------------------------------------------------------------------- #
# The sweep grid (DL-023 §2)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SweepGrid:
    """The frozen sweep grid. Resolution, not thresholds (DL-023 §2)."""

    w_max_hours: tuple[float, ...]
    d_threshold_seconds: tuple[float, ...]
    tau_skip: tuple[float, ...]
    blanket_w_max_hours: float
    sample: Mapping[str, Any]
    raw: Mapping[str, Any]
    source_path: Path

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _grid_values(raw: Mapping[str, Any], key: str, *, lo: float, hi: float) -> tuple[float, ...]:
    block = raw.get(key)
    if not isinstance(block, Mapping) or "values" not in block or "source" not in block:
        raise SimulatorError(f"grid key {key!r} must be a mapping with 'values' and 'source'")
    values = block["values"]
    if not isinstance(values, list) or not values:
        raise SimulatorError(f"grid {key}.values must be a non-empty list")
    out: list[float] = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise SimulatorError(f"grid {key} has a non-numeric value {v!r}")
        if not lo <= float(v) <= hi:
            raise SimulatorError(f"grid {key} value {v} outside [{lo}, {hi}]")
        out.append(float(v))
    if out != sorted(set(out)):
        raise SimulatorError(f"grid {key}.values must be strictly increasing, got {values}")
    return tuple(out)


def load_sweep_grid(path: str | Path = GRID_PATH) -> SweepGrid:
    """Load and validate ``sweep_grid.json``. Rejects anything malformed."""
    path = Path(path)
    if not path.is_file():
        raise SimulatorError(f"sweep grid not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SUPPORTED_GRID_SCHEMA:
        raise SimulatorError(f"unsupported sweep-grid schema_version {raw.get('schema_version')!r}")
    if "DL-023" not in str(raw.get("frozen_by", "")):
        raise SimulatorError("sweep grid must name the decision-log entry that froze it (DL-023)")
    horizon = float(carbon_mod.N_SLOTS - 1)
    w = _grid_values(raw, "w_max_hours", lo=0.0, hi=horizon)
    d = _grid_values(raw, "d_threshold_seconds", lo=0.0, hi=float("inf"))
    t = _grid_values(raw, "tau_skip", lo=0.0, hi=1.0)
    blanket = raw.get("blanket_w_max_hours", {})
    if not isinstance(blanket, Mapping) or "value" not in blanket or "source" not in blanket:
        raise SimulatorError("grid blanket_w_max_hours must carry 'value' and 'source'")
    b = float(blanket["value"])
    if b != horizon:
        raise SimulatorError(
            f"blanket_w_max_hours must be the profile horizon {horizon:g} (DL-023 §1), got {b:g}")
    sample = raw.get("sample")
    if not isinstance(sample, Mapping) or not {"split", "n_builds", "seed", "source"} <= set(sample):
        raise SimulatorError("grid 'sample' must carry split, n_builds, seed and source")
    if sample["split"] == "test":
        raise SimulatorError("the P2 sample may never be drawn from the test split")
    return SweepGrid(w_max_hours=w, d_threshold_seconds=d, tau_skip=t,
                     blanket_w_max_hours=b, sample=dict(sample), raw=raw, source_path=path)


# --------------------------------------------------------------------------- #
# Settings — one per (strategy, grid point)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Setting:
    """One (strategy, grid point). ``None`` means the parameter does not apply."""

    strategy: str
    d_threshold_seconds: float | None = None
    w_max_hours: float | None = None
    tau_skip: float | None = None

    @property
    def setting_id(self) -> str:
        parts = [self.strategy]
        if self.d_threshold_seconds is not None:
            parts.append(f"d{self.d_threshold_seconds:g}")
        if self.w_max_hours is not None:
            parts.append(f"w{self.w_max_hours:g}")
        if self.tau_skip is not None:
            parts.append(f"t{self.tau_skip:g}")
        return "__".join(parts)


def enumerate_settings(grid: SweepGrid) -> list[Setting]:
    """Every (strategy, grid point), in canonical order (DL-023 §1)."""
    out: list[Setting] = [Setting("1_static")]
    out.append(Setting("2_blanket_carbon_aware", d_threshold_seconds=0.0,
                       w_max_hours=grid.blanket_w_max_hours))
    out += [Setting("3_eligibility_only", d_threshold_seconds=0.0, w_max_hours=w)
            for w in grid.w_max_hours]
    for strategy in ("4a_duration_estimator", "4b_duration_prior", "5_se_informed_policy"):
        out += [Setting(strategy, d_threshold_seconds=d, w_max_hours=w)
                for w in grid.w_max_hours for d in grid.d_threshold_seconds]
    out += [Setting("6_risk_only_skip", tau_skip=t) for t in grid.tau_skip]
    ids = [s.setting_id for s in out]
    if len(ids) != len(set(ids)):
        raise SimulatorError("setting ids are not unique")
    return out


def derive_spec(base: policy.PolicySpec, *, policy_path: str,
                d_threshold_seconds: float, w_max_hours: float) -> policy.PolicySpec:
    """The loaded spec with one grid point substituted, re-validated in full.

    The derived spec goes through :func:`policy.spec_from_mapping` — the same
    closed schema, range checks and ``require_fitted`` quarantine as a file — and
    keeps the base spec's provenance unchanged, so an unfitted base can never
    yield a spec that claims to be fitted.
    """
    if policy_path not in policy.POLICY_PATHS:
        raise SimulatorError(f"unknown policy_path {policy_path!r}")
    raw = copy.deepcopy(dict(base.raw))
    raw["policy_path"] = policy_path
    block = "duration_only" if policy_path == "duration_only_fallback" else "se_informed"
    if block not in raw:
        if block == "se_informed":
            raise SimulatorError("cannot derive an se_informed spec from a base with no se_informed block")
        raw[block] = {}
    raw[block] = {**raw[block], "d_threshold_seconds": float(d_threshold_seconds),
                  "w_max_hours": float(w_max_hours)}
    return policy.spec_from_mapping(raw, source_path=base.source_path, require_fitted=base.fitted)


def spec_for(setting: Setting, base: policy.PolicySpec) -> policy.PolicySpec | None:
    """The spec ``decide()`` evaluates for ``setting``; ``None`` if it does not call it."""
    if setting.strategy in ("1_static", "6_risk_only_skip"):
        return None
    path = (base.policy_path if setting.strategy == "5_se_informed_policy"
            else "duration_only_fallback")
    assert setting.d_threshold_seconds is not None and setting.w_max_hours is not None
    return derive_spec(base, policy_path=path, d_threshold_seconds=setting.d_threshold_seconds,
                       w_max_hours=setting.w_max_hours)


# --------------------------------------------------------------------------- #
# The trace
# --------------------------------------------------------------------------- #

#: The only trace columns ever copied into the mapping handed to decide().
#: `obs_duration_s` and `y_fail` are deliberately absent (§A1.2).
DECISION_INPUTS: tuple[str, ...] = ("gh_is_pr", "git_branch", "arrival_dow", "arrival_hour")

#: Columns every trace must carry.
TRACE_COLUMNS: tuple[str, ...] = (
    "replay_seq", "tr_build_id", "gh_project_name", "gh_is_pr", "git_branch",
    "arrival_utc", "arrival_dow", "arrival_hour",
    "d_hat_4a_seconds", "d_hat_4a_fallback", "d_hat_4b_seconds", "d_hat_4b_fallback",
    "d_hat_4b_n_history", "p_hat",
    "obs_duration_s", "y_fail",
)


def sample_builds(frame: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Seeded uniform draw of ``n`` builds without replacement (DL-023 §4).

    The draw is made over the frame sorted by numeric ``tr_build_id``, so it
    depends only on the build set and the seed — never on how the frame was
    assembled. ``n`` larger than the frame is an error, not a silent full take.
    """
    if n > len(frame):
        raise SimulatorError(f"sample of {n:,} requested from only {len(frame):,} builds")
    key = pd.to_numeric(frame["tr_build_id"], errors="coerce")
    if key.isna().any():
        raise SimulatorError("tr_build_id must be numeric to sample deterministically")
    canonical = frame.iloc[np.argsort(key.to_numpy(), kind="stable")].reset_index(drop=True)
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(len(canonical), size=n, replace=False))
    return canonical.iloc[idx].reset_index(drop=True)


def order_trace(trace: pd.DataFrame) -> pd.DataFrame:
    """Replay order: ``arrival_utc`` ascending, ties by numeric ``tr_build_id``."""
    work = trace.copy()
    key = pd.to_numeric(work["tr_build_id"], errors="coerce")
    if key.isna().any():
        raise SimulatorError("tr_build_id must be numeric to order ties deterministically")
    arrival = pd.to_datetime(work["arrival_utc"], utc=True)
    order = np.lexsort((key.to_numpy(), arrival.to_numpy()))
    work = work.iloc[order].reset_index(drop=True)
    work["replay_seq"] = np.arange(len(work), dtype="int64")
    return work


def validate_trace(trace: pd.DataFrame) -> None:
    """Fail loudly on a trace the replay cannot use."""
    missing = [c for c in TRACE_COLUMNS if c not in trace.columns]
    if missing:
        raise SimulatorError(f"trace is missing columns {missing}")
    if trace["tr_build_id"].duplicated().any():
        raise SimulatorError("trace has duplicate tr_build_id rows")
    if not (trace["replay_seq"].to_numpy() == np.arange(len(trace))).all():
        raise SimulatorError("trace is not in replay order — call order_trace() first")
    for col in ("d_hat_4a_seconds", "d_hat_4b_seconds"):
        v = pd.to_numeric(trace[col], errors="coerce")
        if v.isna().any() or (v < 0).any():
            raise SimulatorError(f"{col} must be finite and >= 0 for every build")
    p = pd.to_numeric(trace["p_hat"], errors="coerce")
    if p.isna().any() or ((p < 0) | (p > 1)).any():
        raise SimulatorError("p_hat must be a probability for every build")
    y = pd.to_numeric(trace["y_fail"], errors="coerce")
    if not y.isin([0, 1]).all():
        raise SimulatorError("y_fail must be 0/1 for every build")
    for col, hi in (("arrival_dow", 6), ("arrival_hour", 23)):
        v = pd.to_numeric(trace[col], errors="coerce")
        if v.isna().any() or ((v < 0) | (v > hi)).any():
            raise SimulatorError(f"{col} out of range")


def trace_digest(trace: pd.DataFrame) -> str:
    """sha256 of the trace's canonical CSV bytes."""
    buf = io.StringIO()
    trace[list(TRACE_COLUMNS)].to_csv(buf, index=False, lineterminator="\n")
    return hashlib.sha256(buf.getvalue().encode("utf-8")).hexdigest()


def accountable_mask(trace: pd.DataFrame) -> pd.Series:
    """Builds whose observed duration can be accounted (DL-023 §3).

    Missing, non-finite or negative durations are *decided* like any other build
    but their energy, carbon and TTFF stay empty — never zero-filled (R1).
    """
    v = pd.to_numeric(trace["obs_duration_s"], errors="coerce")
    return v.notna() & np.isfinite(v) & (v >= 0)


# --------------------------------------------------------------------------- #
# Replaying one setting
# --------------------------------------------------------------------------- #

RECORD_COLUMNS: tuple[str, ...] = (
    "strategy", "setting_id", "param_d_threshold_seconds", "param_w_max_hours",
    "param_tau_skip", "replay_seq", "tr_build_id", "gh_project_name", "gh_is_pr",
    "git_branch", "arrival_utc", "arrival_slot", "eligible", "stage1_rule", "action",
    "reason_code", "policy_path", "d_hat_form", "d_hat_seconds", "p_hat", "window_hours",
    "delay_hours", "scheduled_slot", "grid_gco2_arrival", "grid_gco2_scheduled",
    "obs_duration_s__accounting_only", "energy_kwh", "carbon_g", "y_fail", "ttff_hours",
    "spec_fitted",
)


def _stage2_reason(decision: policy.Decision, d_threshold: float) -> str:
    if not decision.eligible:
        return "stage1_not_deferrable"
    if decision.action == "defer":
        return "stage2_defer"
    if decision.d_hat_seconds is not None and decision.d_hat_seconds < d_threshold:
        return "stage2_below_d_threshold"
    return "stage2_no_greener_slot_in_window"


def replay_setting(
    trace: pd.DataFrame,
    setting: Setting,
    *,
    base_spec: policy.PolicySpec,
    profile: pd.DataFrame,
    p_avg_w: float,
    primary_form: str,
) -> pd.DataFrame:
    """Replay every build of ``trace`` under one setting; one record per build.

    Builds are streamed in ``replay_seq`` order. The decision for each build is
    taken from the whitelisted inputs only; accounting runs afterwards.
    """
    validate_trace(trace)
    spec = spec_for(setting, base_spec)
    variant = base_spec.stage1_variant
    strategy = setting.strategy
    if strategy == "5_se_informed_policy":
        d_col = f"d_hat_{primary_form}_seconds"
        d_form = primary_form
    else:
        d_col = _D_HAT_COLUMN.get(strategy, "")
        d_form = {"d_hat_4a_seconds": "4a", "d_hat_4b_seconds": "4b"}.get(d_col, "")
    needs_p_hat = spec is not None and spec.policy_path == "se_informed"
    d_threshold = setting.d_threshold_seconds if setting.d_threshold_seconds is not None else 0.0

    # Column views as plain lists: the loop below is the hot path.
    cols = {c: trace[c].tolist() for c in DECISION_INPUTS}
    d_hat = trace[d_col].astype("float64").tolist() if d_col else [None] * len(trace)
    p_hat_all = trace["p_hat"].astype("float64").tolist()

    rows: dict[str, list[Any]] = {c: [] for c in (
        "arrival_slot", "eligible", "stage1_rule", "action", "reason_code", "policy_path",
        "d_hat_form", "d_hat_seconds", "p_hat", "window_hours", "delay_hours",
        "scheduled_slot", "grid_gco2_arrival", "grid_gco2_scheduled", "spec_fitted")}

    for i in range(len(trace)):
        dow, hour = int(cols["arrival_dow"][i]), int(cols["arrival_hour"][i])
        arrival_slot = carbon_mod.slot_of(dow, hour)
        grid_now = carbon_mod.intensity_for_hour_of_week(profile, dow, hour)

        if strategy == "1_static":
            rec = dict(arrival_slot=arrival_slot, eligible=None, stage1_rule="not_consulted",
                       action="run_now", reason_code="static_run_now", policy_path="",
                       d_hat_form="", d_hat_seconds=None, p_hat=None, window_hours=0.0,
                       delay_hours=0.0, scheduled_slot=arrival_slot, grid_gco2_arrival=grid_now,
                       grid_gco2_scheduled=grid_now, spec_fitted=None)
        elif strategy == "6_risk_only_skip":
            gate = eligibility.classify(cols["gh_is_pr"][i], cols["git_branch"][i], variant=variant)
            p = p_hat_all[i]
            assert setting.tau_skip is not None
            if not gate.eligible:
                action, code = "run_now", "stage1_not_deferrable"
            elif p < setting.tau_skip:
                action, code = "skip", "skip_p_hat_below_tau"
            else:
                action, code = "run_now", "risk_kept_run_now"
            rec = dict(arrival_slot=arrival_slot, eligible=gate.eligible, stage1_rule=gate.rule,
                       action=action, reason_code=code, policy_path="",
                       d_hat_form="", d_hat_seconds=None, p_hat=p, window_hours=0.0,
                       delay_hours=0.0,
                       # A skipped build is never scheduled anywhere.
                       scheduled_slot=arrival_slot if action != "skip" else None,
                       grid_gco2_arrival=grid_now,
                       grid_gco2_scheduled=grid_now if action != "skip" else None,
                       spec_fitted=None)
        else:
            assert spec is not None
            build: dict[str, Any] = {k: cols[k][i] for k in DECISION_INPUTS}
            build["arrival_dow"], build["arrival_hour"] = dow, hour
            build["d_hat_seconds"] = d_hat[i]
            if needs_p_hat:
                build["p_hat"] = p_hat_all[i]
            decision = policy.decide(build, profile, spec)
            rec = dict(arrival_slot=arrival_slot, eligible=decision.eligible,
                       stage1_rule=decision.stage1_rule, action=decision.action,
                       reason_code=_stage2_reason(decision, d_threshold),
                       policy_path=decision.policy_path,
                       d_hat_form=d_form if decision.d_hat_seconds is not None else "",
                       d_hat_seconds=decision.d_hat_seconds, p_hat=decision.p_hat,
                       window_hours=decision.window_hours, delay_hours=decision.delay_hours,
                       scheduled_slot=decision.scheduled_slot,
                       grid_gco2_arrival=decision.grid_gco2_now,
                       grid_gco2_scheduled=decision.grid_gco2_scheduled,
                       spec_fitted=decision.spec_fitted)
        for k, v in rec.items():
            rows[k].append(v)

    out = pd.DataFrame(rows)
    out.insert(0, "strategy", strategy)
    out.insert(1, "setting_id", setting.setting_id)
    out.insert(2, "param_d_threshold_seconds", setting.d_threshold_seconds)
    out.insert(3, "param_w_max_hours", setting.w_max_hours)
    out.insert(4, "param_tau_skip", setting.tau_skip)
    for c in ("replay_seq", "tr_build_id", "gh_project_name", "gh_is_pr", "git_branch",
              "arrival_utc"):
        out[c] = trace[c].to_numpy()

    # ---- accounting: decide() has returned for every build (§A1.2 role 1) ----
    _account(out, trace, p_avg_w=p_avg_w)
    return out[list(RECORD_COLUMNS)]


def _account(records: pd.DataFrame, trace: pd.DataFrame, *, p_avg_w: float) -> None:
    """Energy, carbon and TTFF from the observed duration, after the decision."""
    duration = pd.to_numeric(trace["obs_duration_s"], errors="coerce").to_numpy(dtype="float64")
    ok = accountable_mask(trace).to_numpy()
    y = trace["y_fail"].astype("int64").to_numpy()
    skipped = (records["action"] == "skip").to_numpy()
    delay = records["delay_hours"].astype("float64").to_numpy()
    grid = pd.to_numeric(records["grid_gco2_scheduled"], errors="coerce").to_numpy(dtype="float64")

    energy = np.full(len(records), np.nan)
    carbon = np.full(len(records), np.nan)
    ttff = np.full(len(records), np.nan)
    for i in range(len(records)):
        if not ok[i]:
            continue                          # not measured — never zero-filled (R1)
        if skipped[i]:
            energy[i] = 0.0                   # never ran (DL-023 §3)
            carbon[i] = 0.0
            continue
        e = accounting.energy_kwh(float(duration[i]), p_avg_w)
        energy[i] = e
        carbon[i] = accounting.carbon_g(e, float(grid[i]))
        if y[i] == 1:
            ttff[i] = delay[i] + float(duration[i]) / accounting.SECONDS_PER_HOUR
    records["obs_duration_s__accounting_only"] = np.where(ok, duration, np.nan)
    records["energy_kwh"] = energy
    records["carbon_g"] = carbon
    records["y_fail"] = y
    records["ttff_hours"] = ttff


# --------------------------------------------------------------------------- #
# Runs: fingerprint, parts, assembly
# --------------------------------------------------------------------------- #

def _file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_fingerprint(*, trace: pd.DataFrame, grid: SweepGrid, base_spec: policy.PolicySpec,
                    p_avg_w: float, primary_form: str, profile_path: Path,
                    extra: Mapping[str, Any] | None = None) -> str:
    """Digest over everything that can change a record (DL-023 §6)."""
    payload = {
        "simulator_source": _file_sha(Path(__file__)),
        "policy_source": _file_sha(Path(policy.__file__)),
        "eligibility_source": _file_sha(Path(eligibility.__file__)),
        "accounting_source": _file_sha(Path(accounting.__file__)),
        "spec": json.loads(json.dumps(dict(base_spec.raw), default=str)),
        "grid": grid.digest(),
        "p_avg_w": p_avg_w,
        "primary_form": primary_form,
        "profile": _file_sha(Path(profile_path)),
        "trace": trace_digest(trace),
        "extra": dict(extra or {}),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def records_to_csv_bytes(records: pd.DataFrame, *, header: bool) -> bytes:
    buf = io.StringIO()
    records.to_csv(buf, index=False, header=header, lineterminator="\n", na_rep="")
    return buf.getvalue().encode("utf-8")


def run_sweep(
    trace: pd.DataFrame,
    settings: Sequence[Setting],
    *,
    base_spec: policy.PolicySpec,
    profile: pd.DataFrame,
    p_avg_w: float,
    primary_form: str,
    parts_dir: Path,
    fingerprint: str,
    resume: bool = True,
    progress: Any = None,
) -> list[Path]:
    """Compute (or reuse) one part file per setting; return them in canonical order."""
    parts_dir = Path(parts_dir) / fingerprint[:16]
    parts_dir.mkdir(parents=True, exist_ok=True)
    marker = parts_dir / "FINGERPRINT"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() != fingerprint:
        raise SimulatorError(f"{parts_dir} holds parts from a different run fingerprint")
    marker.write_text(fingerprint + "\n", encoding="utf-8")

    paths: list[Path] = []
    for n, setting in enumerate(settings):
        part = parts_dir / f"{n:04d}__{setting.setting_id}.csv"
        done = part.with_suffix(".done")
        if resume and part.exists() and done.exists() and \
                done.read_text(encoding="utf-8").strip() == _file_sha(part):
            if progress:
                progress(f"  [{n + 1:>3}/{len(settings)}] {setting.setting_id}: resumed")
            paths.append(part)
            continue
        records = replay_setting(trace, setting, base_spec=base_spec, profile=profile,
                                 p_avg_w=p_avg_w, primary_form=primary_form)
        part.write_bytes(records_to_csv_bytes(records, header=False))
        done.write_text(_file_sha(part) + "\n", encoding="utf-8")
        if progress:
            progress(f"  [{n + 1:>3}/{len(settings)}] {setting.setting_id}: "
                     f"{int((records['action'] == 'defer').sum()):,} deferred, "
                     f"{int((records['action'] == 'skip').sum()):,} skipped")
        paths.append(part)
    return paths


def assemble(parts: Sequence[Path], out_path: Path) -> str:
    """Concatenate parts under one header into a gzip with mtime 0; return its sha256."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = (",".join(RECORD_COLUMNS) + "\n").encode("utf-8")
    with open(out_path, "wb") as raw:
        with gzip.GzipFile(filename="decisions.csv", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(header)
            for part in parts:
                gz.write(Path(part).read_bytes())
    return _file_sha(out_path)


def load_records(path: Path) -> pd.DataFrame:
    """Read an assembled records file (gzip CSV) as strings, NA for empties."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""],
                       compression="gzip")


# --------------------------------------------------------------------------- #
# Checks over a finished run
# --------------------------------------------------------------------------- #

def assert_identical_build_sets(records: pd.DataFrame) -> dict[str, Any]:
    """Every (strategy, setting) must have seen exactly the same builds, in order.

    Returns a small report; raises :class:`SimulatorError` on any mismatch.
    """
    groups = records.groupby("setting_id", sort=False)["tr_build_id"]
    reference: list[str] | None = None
    ref_id = ""
    for setting_id, ids in groups:
        seq = ids.astype(str).tolist()
        if reference is None:
            reference, ref_id = seq, str(setting_id)
            continue
        if seq != reference:
            raise SimulatorError(
                f"setting {setting_id!r} saw a different build set/order than {ref_id!r}")
    return {"settings_compared": int(groups.ngroups),
            "builds_per_setting": len(reference or []),
            "identical": True}


def _p95(values: np.ndarray) -> float | None:
    return float(np.percentile(values, 95)) if len(values) else None


def _mean(values: np.ndarray) -> float | None:
    return float(values.mean()) if len(values) else None


def summarise(records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-setting §6 aggregates + the per-slot herding table.

    Carbon/TTFF aggregates run over **accountable** builds only (DL-023 §3); the
    set is identical for every setting, so pairing is preserved, and its size is
    reported. p95 uses numpy's linear-interpolation percentile.
    """
    num = records.copy()
    for c in ("carbon_g", "delay_hours", "ttff_hours", "obs_duration_s__accounting_only",
              "param_d_threshold_seconds", "param_w_max_hours", "param_tau_skip"):
        num[c] = pd.to_numeric(num[c], errors="coerce")
    num["y_fail"] = pd.to_numeric(num["y_fail"]).astype("int64")
    num["scheduled_slot"] = pd.to_numeric(num["scheduled_slot"], errors="coerce")

    rows: list[dict[str, Any]] = []
    herding: list[dict[str, Any]] = []
    for setting_id, g in num.groupby("setting_id", sort=False):
        acc = g["obs_duration_s__accounting_only"].notna().to_numpy()
        carbon = g["carbon_g"].to_numpy()[acc]
        y_acc = g["y_fail"].to_numpy()[acc]
        action = g["action"].to_numpy()
        deferred = action == "defer"
        skipped = action == "skip"
        failed = g["y_fail"].to_numpy() == 1
        delay = g["delay_hours"].to_numpy()
        ttff = g["ttff_hours"].to_numpy()
        ttff_ok = ttff[np.isfinite(ttff)]
        n_fail = int(failed.sum())
        run_fail = int((failed & ~skipped).sum())
        first = g.iloc[0]
        rows.append({
            "strategy": first["strategy"],
            "setting_id": setting_id,
            "param_d_threshold_seconds": first["param_d_threshold_seconds"],
            "param_w_max_hours": first["param_w_max_hours"],
            "param_tau_skip": first["param_tau_skip"],
            "n_builds": int(len(g)),
            "n_accountable": int(acc.sum()),
            "n_unaccountable": int((~acc).sum()),
            "n_eligible": int((g["eligible"].astype(str).str.lower() == "true").sum()),
            "n_deferred": int(deferred.sum()),
            "share_deferred": float(deferred.mean()),
            "n_skipped": int(skipped.sum()),
            "carbon_total_g": float(carbon.sum()),
            "carbon_per_1000_builds_g": accounting.carbon_per_1000_builds(carbon.tolist()),
            "sci_g_per_successful_commit": (
                accounting.sci_per_successful_commit(carbon.tolist(), y_acc.tolist())
                if (y_acc == 0).any() else None),
            "latency_mean_h_all": _mean(delay),
            "latency_p95_h_all": _p95(delay),
            "latency_mean_h_deferred": _mean(delay[deferred]),
            "latency_p95_h_deferred": _p95(delay[deferred]),
            "n_failed": n_fail,
            "ttff_mean_h_failed": _mean(ttff_ok),
            "ttff_p95_h_failed": _p95(ttff_ok),
            "missed_failures": n_fail - run_fail,
            "failure_recall": (run_fail / n_fail) if n_fail else None,
        })
        ran = g.loc[~skipped]
        counts = ran["scheduled_slot"].astype("int64").value_counts()
        for slot in range(carbon_mod.N_SLOTS):
            herding.append({"strategy": first["strategy"], "setting_id": setting_id,
                            "slot": slot, "n_scheduled": int(counts.get(slot, 0))})

    summary = pd.DataFrame(rows)
    static = summary.loc[summary["strategy"] == "1_static", "carbon_per_1000_builds_g"]
    if len(static) == 1:
        base = float(static.iloc[0])
        summary["carbon_pct_vs_static"] = [
            accounting.pct_change_vs_baseline(float(v), base) for v in
            summary["carbon_per_1000_builds_g"]]
    herd = pd.DataFrame(herding)
    conc = (herd.groupby("setting_id", sort=False)["n_scheduled"]
            .apply(lambda s: float(np.sort(s.to_numpy())[::-1][:5].sum() / max(s.sum(), 1))))
    summary["herding_top5_slot_share"] = summary["setting_id"].map(conc)
    return summary, herd


def audit_skips(records: pd.DataFrame, *, variant: str) -> dict[str, Any]:
    """⑥ may never skip a non-deferrable build — checked by the validator's own
    independent re-derivation, not by the gate (DL-023 §7)."""
    from replay import validate_invariants as vi

    skipped = records.loc[records["action"].astype(str) == "skip"]
    bad = [
        {"tr_build_id": r.tr_build_id, "gh_is_pr": r.gh_is_pr, "git_branch": r.git_branch}
        for r in skipped.itertuples()
        if not vi.derive_eligible(r.gh_is_pr, r.git_branch, variant=variant)
    ]
    return {"skipped_rows": int(len(skipped)), "non_deferrable_skipped": len(bad),
            "passed": not bad, "examples": bad[:20]}


def worked_reasons(trace: pd.DataFrame, settings: Iterable[Setting], *,
                   base_spec: policy.PolicySpec, profile: pd.DataFrame,
                   primary_form: str, per_setting: int = 1) -> list[dict[str, Any]]:
    """Full ``decide()`` reason strings for a few builds (DL-023 §5).

    Re-calls ``decide()`` on the recorded inputs, so it also demonstrates that a
    record carries everything needed to reproduce its decision.
    """
    out: list[dict[str, Any]] = []
    for setting in settings:
        spec = spec_for(setting, base_spec)
        if spec is None:
            continue
        d_col = (f"d_hat_{primary_form}_seconds" if setting.strategy == "5_se_informed_policy"
                 else _D_HAT_COLUMN[setting.strategy])
        shown = {"eligible_defer": 0, "other": 0}
        for row in trace.itertuples():
            build = {"gh_is_pr": row.gh_is_pr, "git_branch": row.git_branch,
                     "arrival_dow": int(row.arrival_dow), "arrival_hour": int(row.arrival_hour),
                     "d_hat_seconds": float(getattr(row, d_col))}
            if spec.policy_path == "se_informed":
                build["p_hat"] = float(row.p_hat)
            d = policy.decide(build, profile, spec)
            kind = "eligible_defer" if d.action == "defer" else "other"
            if shown[kind] >= per_setting:
                if all(v >= per_setting for v in shown.values()):
                    break
                continue
            shown[kind] += 1
            out.append({"setting_id": setting.setting_id, "tr_build_id": row.tr_build_id,
                        "action": d.action, "reason": d.reason})
    return out

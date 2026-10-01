"""P3-T2 — replay the full test trace through all six strategies × the frozen sweep grid.

Driven by the **frozen** `policy_spec.yaml` (loaded with ``require_fitted=True``;
its sha256 and its recorded grid digest are asserted before anything runs,
DL-024). Nothing is fitted. `d̂` comes from the frozen P1-T4 control and `p̂` from
the frozen `xgboost:full` arm, through `scripts/run_replay.py`'s trace builder,
unchanged.

The test trace is ~11× the P2 sample, so records are **aggregated and audited one
part file (one setting) at a time** (DL-028 §4). Every whole-frame check of the P2
runner (identical build sets, independent validator, skip audit, DL-023
identities) is applied part by part against the same reference.

Two modes, and their order is enforced:

``--mode rehearse``
    The DL-023 §4 calibration sample (12,000 builds, seed 42). It must reproduce
    ``results/p2/policy_fit/`` exactly: ``trace.csv``, ``summary.csv`` and
    ``herding.csv`` byte for byte, and ``decisions.csv.gz`` line for line apart from
    its last field, ``spec_fitted`` (the P2 sweep ran an unfitted candidate spec;
    this runs the frozen one). The test split is dropped unread.

``--mode test``
    The full test trace. Refuses to run without a passing rehearsal of the same
    code fingerprint. Records a sentinel; a re-run with the same fingerprint is a
    byte-identical reproduction and is allowed, a different one needs
    ``--rerun-under DL-xxx`` (DL-028 §4).

Run from ``code/``:
    PYTHONPATH=. python scripts/run_test_replay.py --mode rehearse
    PYTHONPATH=. python scripts/run_test_replay.py --mode test
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

CODE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = CODE_ROOT / "scripts"
for p in (CODE_ROOT, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import run_replay as rr                                                   # noqa: E402
from replay import simulator as sim                                      # noqa: E402
from replay import stats                                                  # noqa: E402
from replay import validate_invariants as vi                              # noqa: E402
from scheduler_core import (accounting, carbon, config, data, features,   # noqa: E402
                            policy)

ROOT = CODE_ROOT.parent
P2FIT = ROOT / "results" / "p2" / "policy_fit"
P3 = ROOT / "results" / "p3"
REHEARSAL_DIR = P3 / "replay_rehearsal"
SENTINEL = P3 / "test_replay_opened.json"
DECISION_LOG = ROOT / "governance" / "03_DECISION_LOG.md"
DEFAULT_PARTS = CODE_ROOT / "artifacts" / "replay_parts"
SPEC_PATH = policy.DEFAULT_POLICY_SPEC_PATH
COMMAND = "PYTHONPATH=. python scripts/run_test_replay.py"
CHUNK = 300_000

#: DL-028 §3 — the headline rows, fixed before the test replay existed.
HEADLINE_FIXED: tuple[str, ...] = ("1_static", "2_blanket_carbon_aware__d0__w167")
HEADLINE_AT_SPEC: tuple[str, ...] = ("4a_duration_estimator", "4b_duration_prior",
                                     "5_se_informed_policy")

#: Files whose bytes define "the same replay pipeline" between rehearsal and test.
FINGERPRINT_FILES: tuple[Path, ...] = (
    SCRIPTS / "run_test_replay.py", SCRIPTS / "run_replay.py",
    CODE_ROOT / "replay" / "simulator.py", CODE_ROOT / "replay" / "stats.py",
    CODE_ROOT / "replay" / "validate_invariants.py", CODE_ROOT / "replay" / "sweep_grid.json",
    CODE_ROOT / "scheduler_core" / "policy.py", CODE_ROOT / "scheduler_core" / "eligibility.py",
    CODE_ROOT / "scheduler_core" / "accounting.py", CODE_ROOT / "scheduler_core" / "carbon.py",
    CODE_ROOT / "scheduler_core" / "features.py", CODE_ROOT / "scheduler_core" / "data.py",
    CODE_ROOT / "scheduler_core" / "duration_estimator.py",
    CODE_ROOT / "scheduler_core" / "config" / "energy.json", SPEC_PATH,
    carbon.DEFAULT_PROFILE_PATH, CODE_ROOT / "artifacts" / "duration_estimator.joblib",
    rr.RISK_ARM_PATH, ROOT / "results" / "p1" / "split_assignment.csv",
)


class GuardError(SystemExit):
    """Raised when the test trace may not be replayed (or re-replayed)."""


def log(msg: str) -> None:
    print(msg, flush=True)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pipeline_fingerprint(files: Sequence[Path] = FINGERPRINT_FILES) -> str:
    h = hashlib.sha256()
    for path in files:
        h.update(Path(path).name.encode("utf-8"))
        h.update(hashlib.sha256(Path(path).read_bytes()).digest())
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #

def dl_entry_exists(dl_id: str, log_path: Path = DECISION_LOG) -> bool:
    if not re.fullmatch(r"DL-\d{3}", dl_id):
        return False
    return re.search(rf"^### {re.escape(dl_id)} ", log_path.read_text(encoding="utf-8"),
                     flags=re.MULTILINE) is not None


def assert_may_replay_test(*, fingerprint: str, rehearsal_path: Path, sentinel: Path,
                           rerun_under: str | None, log_path: Path = DECISION_LOG) -> dict:
    if not rehearsal_path.exists():
        raise GuardError(f"no rehearsal record at {rehearsal_path}; run --mode rehearse first")
    rehearsal = json.loads(rehearsal_path.read_text(encoding="utf-8"))
    if not rehearsal.get("all_checks_pass"):
        raise GuardError("the calibration-sample rehearsal did not reproduce P2-T5 exactly")
    if rehearsal.get("code_fingerprint") != fingerprint:
        raise GuardError("code or frozen inputs changed since the rehearsal passed; re-rehearse")
    if sentinel.exists():
        opened = json.loads(sentinel.read_text(encoding="utf-8"))
        if opened.get("code_fingerprint") != fingerprint and rerun_under is None:
            raise GuardError(
                f"the test trace was already replayed ({opened.get('opened_at_utc')}) with a "
                "different pipeline; a changed re-run needs --rerun-under DL-xxx (DL-028 §4)")
    if rerun_under is not None and not dl_entry_exists(rerun_under, log_path):
        raise GuardError(f"--rerun-under {rerun_under}: no such entry in {log_path.name}")
    return rehearsal


def load_frozen_spec(grid: sim.SweepGrid) -> tuple[policy.PolicySpec, str]:
    """The frozen spec, fitted, with its sha256 and grid digest asserted (DL-024)."""
    spec = policy.load_policy_spec(SPEC_PATH, require_fitted=True)
    digest = sha(SPEC_PATH)
    certified = json.loads((P2FIT / "verify.json").read_text(encoding="utf-8"))
    if digest != certified["policy_spec_yaml"]["committed_sha256"]:
        raise SystemExit("FATAL: policy_spec.yaml is not the sha256 P2-T5's --verify certified")
    if spec.raw["sweep"]["grid_sha256"] != grid.digest():
        raise SystemExit("FATAL: the spec's recorded grid digest differs from sweep_grid.json")
    return spec, digest


# --------------------------------------------------------------------------- #
# Loading — one split, every other split's job rows discarded per chunk
# --------------------------------------------------------------------------- #

def load_split_builds(assignment: dict[str, str], split: str) -> tuple[pd.DataFrame, dict]:
    """`run_replay.load_split_builds`'s loop, for any one split (it refuses test by design)."""
    running: pd.DataFrame | None = None
    dropped_rows = {"train": 0, "calibration": 0, "test": 0, "unassigned": 0}
    for chunk in data.read_chunks(chunksize=CHUNK, usecols=rr.READ_COLUMNS):
        which = chunk["gh_project_name"].map(assignment).fillna("unassigned")
        keep = (which == split).to_numpy()
        for name, n in which[~keep].value_counts().items():
            dropped_rows[str(name)] += int(n)
        chunk = chunk.loc[keep]
        if chunk.empty:
            continue
        chunk = chunk.assign(_dur=pd.to_numeric(chunk["tr_duration"], errors="coerce"))
        g = chunk.groupby("tr_build_id", sort=False)
        cols = [c for c in chunk.columns if c not in ("tr_build_id", "tr_duration", "_dur")]
        agg = g[cols].first()
        agg["tr_duration"] = g["_dur"].max()          # DL-009 max-aggregation
        if running is None:
            running = agg
            continue
        cat = pd.concat([running, agg])
        gg = cat.groupby(level=0, sort=False)
        out = gg[[c for c in cat.columns if c != "tr_duration"]].first()
        out["tr_duration"] = gg["tr_duration"].max()
        running = out
    assert running is not None
    builds = running.reset_index()
    builds = builds.loc[features.analytic_mask(builds)].reset_index(drop=True)
    return builds, {"job_rows_dropped_by_split": dropped_rows}


# --------------------------------------------------------------------------- #
# Streaming aggregation over part files
# --------------------------------------------------------------------------- #

def read_part(path: Path) -> pd.DataFrame:
    """One part file (no header), read exactly as `simulator.load_records` reads records."""
    return pd.read_csv(path, header=None, names=list(sim.RECORD_COLUMNS), dtype=str,
                       keep_default_na=False, na_values=[""])


def _hash_cols(records: pd.DataFrame, cols: Sequence[str]) -> str:
    blob = records[list(cols)].to_csv(index=False, lineterminator="\n", na_rep="")
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def headline_ids(spec: policy.PolicySpec, grid: sim.SweepGrid) -> list[str]:
    """DL-028 §3, resolved against the frozen spec."""
    d = float(spec.duration_only["d_threshold_seconds"])
    w = float(spec.duration_only["w_max_hours"])
    ids = list(HEADLINE_FIXED) + [f"3_eligibility_only__d0__w{w:g}"]
    ids += [f"{s}__d{d:g}__w{w:g}" for s in HEADLINE_AT_SPEC]
    ids += [f"6_risk_only_skip__t{t:g}" for t in grid.tau_skip]
    return ids


def aggregate_parts(parts: Sequence[Path], settings: Sequence[sim.Setting], *,
                    reference_ids: Sequence[str], variant: str,
                    keep_per_build: Sequence[str], progress: Any = None) -> dict[str, Any]:
    """`simulator.summarise` + every P2 whole-frame check, one part at a time."""
    rows: list[dict[str, Any]] = []
    herding_rows: list[dict[str, Any]] = []
    top5: dict[str, float] = {}
    audit = {"rows": 0, "deferred": 0, "violations": 0, "violation_rows": []}
    skips = {"skipped_rows": 0, "non_deferrable_skipped": 0, "examples": []}
    identity_hash: dict[str, str] = {}
    action_hash: dict[str, str] = {}
    reasons: dict[str, dict[str, int]] = {}
    paths: dict[str, dict[str, int]] = {}
    per_build: list[pd.DataFrame] = []
    ref = list(reference_ids)
    keep = set(keep_per_build)

    for n, (part, setting) in enumerate(zip(parts, settings)):
        rec = read_part(part)
        sid = setting.setting_id
        if set(rec["setting_id"]) != {sid}:
            raise sim.SimulatorError(f"part {part.name} does not hold setting {sid}")
        if rec["tr_build_id"].astype(str).tolist() != ref:
            raise sim.SimulatorError(f"setting {sid!r} saw a different build set/order")
        a = vi.audit_frame(rec, variant=variant, path=str(part))
        audit["rows"] += a.rows
        audit["deferred"] += a.deferred
        audit["violations"] += a.violations
        audit["violation_rows"].extend(a.violation_rows[: max(0, 5 - len(audit["violation_rows"]))])
        s = sim.audit_skips(rec, variant=variant)
        skips["skipped_rows"] += s["skipped_rows"]
        skips["non_deferrable_skipped"] += s["non_deferrable_skipped"]
        skips["examples"].extend(s["examples"][: max(0, 20 - len(skips["examples"]))])

        summ, herd = sim.summarise(rec)
        top5[sid] = float(summ["herding_top5_slot_share"].iloc[0])
        row = summ.drop(columns=[c for c in ("carbon_pct_vs_static", "herding_top5_slot_share")
                                 if c in summ.columns]).iloc[0].to_dict()
        rows.append(row)
        herding_rows.extend(herd.to_dict(orient="records"))

        identity_hash[sid] = _hash_cols(rec, ("tr_build_id", "action", "delay_hours",
                                              "scheduled_slot"))
        action_hash[sid] = _hash_cols(rec, ("action",))
        reasons[sid] = {k: int(v) for k, v in rec["reason_code"].value_counts().sort_index().items()}
        paths[sid] = {k: int(v) for k, v in
                      rec["policy_path"].fillna("").value_counts().sort_index().items()}
        if sid in keep:
            per_build.append(pd.DataFrame({
                "strategy": sid,
                "tr_build_id": rec["tr_build_id"].to_numpy(),
                "action": rec["action"].to_numpy(),
                "delay_hours": pd.to_numeric(rec["delay_hours"]).to_numpy(dtype="float64"),
                "carbon_g": pd.to_numeric(rec["carbon_g"], errors="coerce").to_numpy(dtype="float64"),
                "ttff_hours": pd.to_numeric(rec["ttff_hours"], errors="coerce").to_numpy(dtype="float64"),
                "y_fail": pd.to_numeric(rec["y_fail"]).to_numpy(dtype="int64"),
                "accountable": rec["obs_duration_s__accounting_only"].notna().to_numpy(),
            }))
        if progress:
            progress(f"  [{n + 1:>3}/{len(settings)}] aggregated {sid}")
        del rec

    summary = pd.DataFrame(rows)
    static = summary.loc[summary["strategy"] == "1_static", "carbon_per_1000_builds_g"]
    if len(static) == 1:
        base = float(static.iloc[0])
        summary["carbon_pct_vs_static"] = [
            accounting.pct_change_vs_baseline(float(v), base)
            for v in summary["carbon_per_1000_builds_g"]]
    summary["herding_top5_slot_share"] = summary["setting_id"].map(top5)
    audit["passed"] = audit["violations"] == 0
    skips["passed"] = skips["non_deferrable_skipped"] == 0
    return {
        "summary": summary, "herding": pd.DataFrame(herding_rows),
        "identical_build_sets": {"settings_compared": len(settings),
                                 "builds_per_setting": len(ref), "identical": True},
        "validator": audit, "skip_audit": skips,
        "identity_hash": identity_hash, "action_hash": action_hash,
        "reason_codes": reasons, "policy_paths": paths,
        "per_build": pd.concat(per_build, ignore_index=True) if per_build else pd.DataFrame(),
    }


def identity_checks(agg: dict, grid: sim.SweepGrid) -> dict[str, bool]:
    """DL-023 §1's identities, from per-setting digests (same columns as run_replay)."""
    h, ah = agg["identity_hash"], agg["action_hash"]
    return {
        "5_equals_4b_at_every_point": all(
            h[f"5_se_informed_policy__d{d:g}__w{w:g}"] == h[f"4b_duration_prior__d{d:g}__w{w:g}"]
            for w in grid.w_max_hours for d in grid.d_threshold_seconds),
        "3_equals_4b_at_d0": all(
            h[f"3_eligibility_only__d0__w{w:g}"] == h[f"4b_duration_prior__d0__w{w:g}"]
            for w in grid.w_max_hours),
        "6_at_tau0_equals_1_static_actions": ah["6_risk_only_skip__t0"] == ah["1_static"],
    }


# --------------------------------------------------------------------------- #
# Paired bootstrap metrics (DL-028 §5) — mirrors simulator.summarise's definitions
# --------------------------------------------------------------------------- #

def _p95(v: np.ndarray) -> float | None:
    return float(np.percentile(v, 95)) if len(v) else None


def _carbon(f: pd.DataFrame) -> np.ndarray:
    return f["carbon_g"].to_numpy()[f["accountable"].to_numpy()]


METRIC_FNS = {
    "carbon_per_1000_builds_g": lambda f: float(_carbon(f).mean() * 1000.0),
    "sci_g_per_successful_commit": lambda f: (
        float(_carbon(f).sum() / n) if (n := int(((f["y_fail"].to_numpy() == 0)
                                                    & f["accountable"].to_numpy()).sum())) else None),
    "latency_mean_h_all": lambda f: float(f["delay_hours"].mean()),
    "latency_p95_h_deferred": lambda f: _p95(
        f["delay_hours"].to_numpy()[f["action"].to_numpy() == "defer"]),
    "ttff_mean_h_failed": lambda f: (
        float(t.mean()) if len(t := f["ttff_hours"].to_numpy()[np.isfinite(f["ttff_hours"].to_numpy())])
        else None),
    "ttff_p95_h_failed": lambda f: _p95(
        f["ttff_hours"].to_numpy()[np.isfinite(f["ttff_hours"].to_numpy())]),
    "share_deferred": lambda f: float((f["action"].to_numpy() == "defer").mean()),
}


def bootstrap_point_check(boot: dict, summary: pd.DataFrame) -> dict[str, Any]:
    """The bootstrap's full-trace points must equal the summary's (they share definitions)."""
    worst, bad = 0.0, []
    by = summary.set_index("setting_id")
    for sid, metrics in boot["per_strategy"].items():
        for m, rec in metrics.items():
            s = by.loc[sid, m]
            if rec["point"] is None or pd.isna(s):
                if not (rec["point"] is None and pd.isna(s)):
                    bad.append(f"{sid}.{m}")
                continue
            rel = abs(rec["point"] - float(s)) / max(abs(float(s)), 1e-12)
            worst = max(worst, rel)
            if rel > 1e-9:
                bad.append(f"{sid}.{m}")
    return {"max_relative_difference": worst, "mismatches": bad, "passed": not bad}


# --------------------------------------------------------------------------- #
# Rehearsal comparison against results/p2/policy_fit/
# --------------------------------------------------------------------------- #

def decisions_equal_except_spec_fitted(a: Path, b: Path) -> dict[str, Any]:
    """Line-by-line equality of two assembled records files, last field dropped."""
    n = 0
    with gzip.open(a, "rt", encoding="utf-8", newline="") as fa, \
            gzip.open(b, "rt", encoding="utf-8", newline="") as fb:
        for la, lb in zip(fa, fb):
            if la.rsplit(",", 1)[0] != lb.rsplit(",", 1)[0]:
                return {"equal": False, "first_differing_line": n + 1}
            n += 1
        tail = fa.readline() or fb.readline()
    return {"equal": not tail, "lines_compared": n,
            "note": "the last field, spec_fitted, is excluded: the P2 sweep ran an unfitted "
                    "candidate spec (DL-024 §4), this rehearsal runs the frozen one"}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def build_test_trace(t0: float) -> tuple[pd.DataFrame, dict, dict]:
    assignment, split_digest = rr.load_frozen_assignment()
    builds, info = load_split_builds(assignment, "test")
    if set(builds["gh_project_name"].map(assignment)) != {"test"}:
        raise SystemExit("FATAL: a non-test project reached the test trace")
    log(f"  {len(builds):,} analytic test builds / {builds['gh_project_name'].nunique():,} "
        f"projects ({time.time() - t0:.0f}s)")
    full, prov = rr.build_trace(builds)
    trace = sim.order_trace(full)
    sim.validate_trace(trace)
    return trace, prov, {"split": "test", "split_assignment_sha256": split_digest, **info}


def build_rehearsal_trace(grid: sim.SweepGrid, t0: float) -> tuple[pd.DataFrame, dict, dict]:
    assignment, split_digest = rr.load_frozen_assignment()
    builds, info = load_split_builds(assignment, "calibration")
    log(f"  {len(builds):,} analytic calibration builds ({time.time() - t0:.0f}s)")
    full, prov = rr.build_trace(builds)
    trace = sim.order_trace(sim.sample_builds(full, int(grid.sample["n_builds"]),
                                              int(grid.sample["seed"])))
    sim.validate_trace(trace)
    return trace, prov, {"split": "calibration (DL-023 §4 sample)",
                         "split_assignment_sha256": split_digest, **info}


def cross_check_p3t1(trace: pd.DataFrame) -> dict[str, Any]:
    """The test trace's d̂ and p̂ must equal P3-T1's persisted per-build scores."""
    scores = pd.read_csv(P3 / "test_scores.csv.gz", dtype={"tr_build_id": str})
    s = scores.set_index("tr_build_id").loc[trace["tr_build_id"].astype(str)]
    p_diff = float(np.max(np.abs(s["p__xgboost__full"].to_numpy() - trace["p_hat"].to_numpy())))
    d_diff = float(np.max(np.abs(np.expm1(s["d_hat_log1p_4b"].to_numpy())
                                 - trace["d_hat_4b_seconds"].to_numpy())))
    y_equal = bool(np.array_equal(s["y_fail"].to_numpy(), trace["y_fail"].to_numpy()))
    return {"builds_matched": int(len(s)), "p_hat_max_abs_diff": p_diff,
            "d_hat_4b_seconds_max_abs_diff": d_diff, "y_fail_equal": y_equal,
            "passed": bool(len(s) == len(trace) and y_equal and p_diff <= 1e-12
                           and d_diff <= 1e-6)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("rehearse", "test"), required=True)
    ap.add_argument("--rerun-under", default=None)
    ap.add_argument("--parts-dir", type=Path, default=DEFAULT_PARTS)
    ap.add_argument("--n-resamples", type=int, default=stats.N_RESAMPLES)
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.time()
    code_fp = pipeline_fingerprint()
    grid = sim.load_sweep_grid()
    spec, spec_sha = load_frozen_spec(grid)
    energy = accounting.load_energy_config()
    profile = carbon.load_hour_of_week_profile()

    if args.mode == "test":
        if args.n_resamples != stats.N_RESAMPLES:
            raise GuardError("the test replay always uses the protocol's B = 1000")
        assert_may_replay_test(fingerprint=code_fp, rehearsal_path=REHEARSAL_DIR / "rehearsal.json",
                               sentinel=SENTINEL, rerun_under=args.rerun_under)
        P3.mkdir(parents=True, exist_ok=True)
        previous = json.loads(SENTINEL.read_text(encoding="utf-8")) if SENTINEL.exists() else None
        SENTINEL.write_text(json.dumps({
            "opened_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "command": f"{COMMAND} --mode test"
                       + (f" --rerun-under {args.rerun_under}" if args.rerun_under else ""),
            "code_fingerprint": code_fp, "rerun_under": args.rerun_under,
            "previous": previous}, indent=2) + "\n", encoding="utf-8")
        log(f"test replay recorded in {SENTINEL.relative_to(ROOT)}")

    log(f"reading {data.DEFAULT_DATASET_PATH} ({args.mode}) …")
    trace, trace_prov, pop_info = (build_test_trace(t0) if args.mode == "test"
                                   else build_rehearsal_trace(grid, t0))
    unacc = int((~sim.accountable_mask(trace)).sum())
    log(f"  trace: {len(trace):,} builds / {trace['gh_project_name'].nunique():,} projects; "
        f"unaccountable {unacc}; failure rate {trace['y_fail'].mean():.4%}")

    out = P3 if args.mode == "test" else REHEARSAL_DIR
    out.mkdir(parents=True, exist_ok=True)
    trace_path = out / ("test_trace.csv.gz" if args.mode == "test" else "trace.csv")
    if args.mode == "test":
        trace[list(sim.TRACE_COLUMNS)].to_csv(trace_path, index=False, lineterminator="\n",
                                              na_rep="", compression={"method": "gzip", "mtime": 0})
    else:
        trace[list(sim.TRACE_COLUMNS)].to_csv(trace_path, index=False, lineterminator="\n",
                                              na_rep="")
    cross = cross_check_p3t1(trace) if args.mode == "test" else None
    if cross is not None:
        log(f"  cross-check vs P3-T1 scores: {cross}")
        if not cross["passed"]:
            raise SystemExit("FATAL: the test trace's d̂/p̂ differ from P3-T1's scores")

    settings = sim.enumerate_settings(grid)
    primary_form = trace_prov["duration_control_primary_form"]
    run_fp = sim.run_fingerprint(
        trace=trace, grid=grid, base_spec=spec, p_avg_w=energy.p_avg_w,
        primary_form=primary_form, profile_path=carbon.DEFAULT_PROFILE_PATH,
        extra={"split_assignment_sha256": pop_info["split_assignment_sha256"], **trace_prov})
    log(f"\nreplaying {len(settings)} settings × {len(trace):,} builds (run fingerprint "
        f"{run_fp[:16]}) …")
    parts = sim.run_sweep(trace, settings, base_spec=spec, profile=profile,
                          p_avg_w=energy.p_avg_w, primary_form=primary_form,
                          parts_dir=args.parts_dir, fingerprint=run_fp, resume=True, progress=log)

    decisions_path = out / "decisions.csv.gz"
    log("\nassembling decisions.csv.gz …")
    decisions_sha = sim.assemble(parts, decisions_path)
    heads = headline_ids(spec, grid)
    log("aggregating part by part …")
    agg = aggregate_parts(parts, settings, reference_ids=trace["tr_build_id"].astype(str).tolist(),
                          variant=spec.stage1_variant, keep_per_build=heads, progress=log)
    identities = identity_checks(agg, grid)
    self_test = vi.audit_frame(pd.DataFrame({
        "gh_is_pr": ["false", "true", "false"], "git_branch": ["feature/x", "feature/y", "master"],
        "action": ["defer", "defer", "defer"]})).violations == 2
    summary, herding = agg["summary"], agg["herding"]
    summary_name = "summary.csv" if args.mode == "rehearse" else "strategy_results.csv"
    herding_name = "herding.csv" if args.mode == "rehearse" else "strategy_herding.csv"
    summary.to_csv(out / summary_name, index=False, lineterminator="\n", na_rep="")
    herding.to_csv(out / herding_name, index=False, lineterminator="\n")
    log(f"  validator {agg['validator']['violations']} violations / "
        f"{agg['validator']['deferred']:,} deferrals / {agg['validator']['rows']:,} rows; "
        f"skip audit {agg['skip_audit']['non_deferrable_skipped']}; identities {identities}")

    log(f"\npaired bootstrap over {len(heads)} headline settings (B = {args.n_resamples}) …")
    boot = stats.paired_bootstrap(agg["per_build"], METRIC_FNS, strategies=heads,
                                  n_resamples=args.n_resamples)
    point_check = bootstrap_point_check(boot, summary)

    base_checks = {
        "identical_build_sets": agg["identical_build_sets"],
        "validator": agg["validator"], "skip_audit": agg["skip_audit"],
        "validator_self_test": self_test, "identities": identities,
        "bootstrap_points_equal_summary": point_check,
        "spec": {"sha256": spec_sha, "require_fitted": True, "fitted": spec.fitted,
                 "grid_digest_matches": True},
    }
    population = {**pop_info, "n_builds": int(len(trace)),
                  "n_projects": int(trace["gh_project_name"].nunique()),
                  "failure_rate": float(trace["y_fail"].mean()), "n_unaccountable": unacc,
                  "first_arrival": str(trace["arrival_utc"].iloc[0]),
                  "last_arrival": str(trace["arrival_utc"].iloc[-1]),
                  "d_hat_4b_fallback_levels": trace["d_hat_4b_fallback"].value_counts().to_dict()}
    meta = {"command": f"{COMMAND} --mode {args.mode}"
                       + (f" --n-resamples {args.n_resamples}"
                          if args.n_resamples != stats.N_RESAMPLES else ""),
            "run_date": time.strftime("%Y-%m-%d"), "code_fingerprint": code_fp,
            "run_fingerprint": run_fp, "grid_sha256": grid.digest(), "seed": config.RANDOM_SEED,
            "energy": energy.provenance(), "trace_provenance": trace_prov}

    if args.mode == "rehearse":
        fit = json.loads((P2FIT / "manifest.json").read_text(encoding="utf-8"))["sha256"]
        compare = {
            "trace.csv": {"this": sha(trace_path), "p2_t5": fit["trace.csv"]},
            "summary.csv": {"this": sha(out / "summary.csv"), "p2_t5": fit["summary.csv"]},
            "herding.csv": {"this": sha(out / "herding.csv"), "p2_t5": fit["herding.csv"]},
        }
        for v in compare.values():
            v["identical"] = v["this"] == v["p2_t5"]
        dec = decisions_equal_except_spec_fitted(decisions_path, P2FIT / "decisions.csv.gz")
        checks = {**base_checks, "reproduces_p2_t5": compare, "decisions_vs_p2_t5": dec}
        ok = (all(v["identical"] for v in compare.values()) and dec["equal"]
              and agg["validator"]["passed"] and agg["skip_audit"]["passed"] and self_test
              and all(identities.values()) and point_check["passed"])
        record = {"mode": "calibration-sample rehearsal — reproduces P2-T5; not a test result",
                  **meta, "n_resamples": args.n_resamples, "all_checks_pass": ok,
                  "checks": checks, "population": population,
                  "runtime_s": round(time.time() - t0, 1)}
        (out / "rehearsal.json").write_text(json.dumps(record, indent=2, default=str) + "\n",
                                            encoding="utf-8")
        decisions_path.unlink()          # 61 MB copy of P2's; its equality is what is recorded
        log(f"\nrehearsal: {'PASS' if ok else 'FAIL'} — {json.dumps(compare)} · decisions {dec}")
        return 0 if ok else 1

    heads_summary = summary.set_index("setting_id").loc[heads].reset_index()
    five = [s.setting_id for s in settings if s.strategy == "5_se_informed_policy"]
    result = {
        "task": "P3-T2", "decision_log": ["DL-023", "DL-024", "DL-027", "DL-028"], **meta,
        "label": "test split — the frozen policy replayed once (P3-T2)",
        "population": population, "n_settings": len(settings),
        "n_records": int(len(settings) * len(trace)), "checks": base_checks,
        "cross_check_p3_t1": cross,
        "headline_setting_ids": heads, "headline": heads_summary.to_dict(orient="records"),
        "bootstrap": boot,
        "policy_path_distribution_5": {sid: agg["policy_paths"][sid] for sid in five},
        "reason_codes": agg["reason_codes"],
        "sha256": {"test_trace.csv.gz": sha(trace_path), "decisions.csv.gz": decisions_sha,
                   "strategy_results.csv": sha(out / "strategy_results.csv"),
                   "strategy_herding.csv": sha(out / "strategy_herding.csv")},
        "runtime_s": round(time.time() - t0, 1),
    }
    (out / "strategy_results.json").write_text(json.dumps(result, indent=2, default=str) + "\n",
                                               encoding="utf-8")
    write_report(result, heads_summary, spec)
    ok = (agg["validator"]["passed"] and agg["skip_audit"]["passed"] and self_test
          and all(identities.values()) and point_check["passed"])
    log(f"\nwrote results/p3/strategy_results.* ({result['runtime_s']:.0f}s) — checks "
        f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def _f(v: Any, nd: int = 2) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    return f"{float(v):,.{nd}f}"


def _ci(rec: dict, nd: int = 2) -> str:
    if rec.get("point") is None:
        return "—"
    if rec.get("ci_lo") is None:
        return _f(rec["point"], nd)
    return f"{_f(rec['point'], nd)} [{_f(rec['ci_lo'], nd)}, {_f(rec['ci_hi'], nd)}]"


LABEL = {"1_static": "① static", "2_blanket_carbon_aware": "② blanket carbon-aware",
         "3_eligibility_only": "③ eligibility-only", "4a_duration_estimator": "④a duration (estimator)",
         "4b_duration_prior": "④b duration (project prior)",
         "5_se_informed_policy": "⑤ frozen policy", "6_risk_only_skip": "⑥ risk-only skip"}


def write_report(res: dict, heads: pd.DataFrame, spec: policy.PolicySpec) -> None:
    b, pop, c = res["bootstrap"], res["population"], res["checks"]
    ps = b["per_strategy"]
    five = f"5_se_informed_policy__d{float(spec.duration_only['d_threshold_seconds']):g}" \
           f"__w{float(spec.duration_only['w_max_hours']):g}"
    L: list[str] = []
    A = L.append
    A("# P3-T2 — six strategies replayed on the test trace\n")
    A(f"> Generated by `{res['command']}` on {res['run_date']} ({res['runtime_s']:.0f} s). Every "
      "number below comes from that run (R1). **Test split**, replayed once with the frozen "
      f"`policy_spec.yaml` (sha256 `{c['spec']['sha256'][:16]}…`, loaded with "
      "`require_fitted=True`, grid digest asserted). Nothing was fitted.\n")
    A("> ⑤ is the frozen policy. Its path is `duration_only_fallback`, so ⑤ ≡ ④b at every grid point "
      "**by construction** (DL-023 §1, DL-028 §1): their rows are the same decisions, not two "
      "findings. Carbon is proportional to duration under the energy model (§A1.13), so the "
      "carbon column cannot carry SE value by construction.\n")
    A("## 1. Population\n")
    A(f"- **{pop['n_builds']:,} test builds / {pop['n_projects']:,} projects**, "
      f"{pop['first_arrival']} → {pop['last_arrival']}; failure rate "
      f"{100 * pop['failure_rate']:.4f}%; unaccountable builds (no usable duration, DL-023 §3) "
      f"**{pop['n_unaccountable']:,}**, excluded identically from every carbon/TTFF aggregate.")
    x = res["cross_check_p3_t1"]
    A(f"- `d̂` and `p̂` equal P3-T1's persisted per-build scores for all {x['builds_matched']:,} "
      f"builds (max |Δp̂| {x['p_hat_max_abs_diff']:.2e}, max |Δd̂| "
      f"{x['d_hat_4b_seconds_max_abs_diff']:.2e} s, labels equal: {x['y_fail_equal']}).")
    A(f"- {res['n_settings']} settings × {pop['n_builds']:,} builds = **{res['n_records']:,}** "
      "records, every one audited.\n")
    A("## 2. Checks (gate evidence)\n")
    A("| check | result |")
    A("| :-- | :-- |")
    A(f"| every setting saw the identical build set, in order | PASS "
      f"({c['identical_build_sets']['settings_compared']} × "
      f"{c['identical_build_sets']['builds_per_setting']:,}) |")
    v = c["validator"]
    A(f"| independent validator: non-deferrable builds deferred | **{v['violations']}** of "
      f"{v['deferred']:,} deferrals / {v['rows']:,} rows — {'PASS' if v['passed'] else 'FAIL'} |")
    s = c["skip_audit"]
    A(f"| independent validator: non-deferrable builds skipped by ⑥ | "
      f"**{s['non_deferrable_skipped']}** of {s['skipped_rows']:,} skips — "
      f"{'PASS' if s['passed'] else 'FAIL'} |")
    A(f"| validator self-test | {'PASS' if c['validator_self_test'] else 'FAIL'} |")
    for k, val in c["identities"].items():
        A(f"| DL-023 identity `{k}` | {'holds' if val else 'DOES NOT HOLD'} |")
    pc = c["bootstrap_points_equal_summary"]
    A(f"| bootstrap points equal the summary | {'PASS' if pc['passed'] else 'FAIL'} "
      f"(max relative difference {pc['max_relative_difference']:.1e}) |")
    A("")
    A("## 3. Headline table — RQ4 (DL-028 §3 operating points), 95% paired-bootstrap CIs\n")
    A("B = 1000, seed 42, resampling the shared test-build index. gCO₂e uses P_avg = "
      f"{res['energy']['p_avg_w']} W (DL-021); absolute gCO₂e is an estimate, and comparisons "
      "between strategies are what the design protects.\n")
    A("| strategy | setting | deferred | gCO₂e / 1k builds | Δ vs ① | SCI g / successful commit | "
      "latency mean h (all) | latency p95 h (deferred) | TTFF mean h (failed) | TTFF p95 h (failed) "
      "| missed failures | failure recall | top-5 slot share |")
    A("| :-- | :-- | :-- | :-- | --: | :-- | :-- | :-- | :-- | :-- | --: | --: | --: |")
    for r in heads.itertuples():
        m = ps[r.setting_id]
        A(f"| {LABEL[r.strategy]} | `{r.setting_id}` | {_f(r.n_deferred)} "
          f"({100 * r.share_deferred:.2f}%) | {_ci(m['carbon_per_1000_builds_g'], 1)} | "
          f"{_f(r.carbon_pct_vs_static, 3)}% | {_ci(m['sci_g_per_successful_commit'], 4)} | "
          f"{_ci(m['latency_mean_h_all'], 3)} | {_ci(m['latency_p95_h_deferred'], 2)} | "
          f"{_ci(m['ttff_mean_h_failed'], 3)} | {_ci(m['ttff_p95_h_failed'], 2)} | "
          f"{_f(r.missed_failures)} | {_f(r.failure_recall, 4)} | {_f(r.herding_top5_slot_share, 4)} |")
    A("\n⑥ has no single headline row: no rule for τ was predeclared and fitting one would use the "
      "test split (DL-028 §3). Its carbon falls because skipped builds never run; read it beside "
      "*missed failures*. ⑥'s τ frontier is coarse (DL-024 §5).\n")
    A(f"## 4. The frozen policy ⑤ against each baseline — paired differences (⑤ − other)\n")
    A("| other | Δ gCO₂e / 1k builds [95% CI] | Δ TTFF p95 h [95% CI] | Δ TTFF mean h [95% CI] | "
      "Δ latency mean h (all) [95% CI] |")
    A("| :-- | :-- | :-- | :-- | :-- |")
    order = b["strategies"]
    for other in order:
        if other == five:
            continue
        key = f"{five}__minus__{other}"
        sign = 1.0
        if key not in b["differences"]["carbon_per_1000_builds_g"]:
            key, sign = f"{other}__minus__{five}", -1.0

        def d(metric: str, nd: int) -> str:
            rec = b["differences"][metric][key]
            if rec["point"] is None:
                return "—"
            if rec["ci_lo"] is None:
                return _f(sign * rec["point"], nd)
            lo, hi = sorted((sign * rec["ci_lo"], sign * rec["ci_hi"]))
            return f"{sign * rec['point']:+,.{nd}f} [{lo:+,.{nd}f}, {hi:+,.{nd}f}]"
        A(f"| `{other}` | {d('carbon_per_1000_builds_g', 1)} | {d('ttff_p95_h_failed', 2)} | "
          f"{d('ttff_mean_h_failed', 3)} | {d('latency_mean_h_all', 3)} |")
    A("\nThe ⑤ − ④b row is exactly 0 by construction (null path), which also shows the pairing works.\n")
    A("## 5. Policy-path distribution for ⑤ (S3)\n")
    p5 = res["policy_path_distribution_5"][five]
    r5 = res["reason_codes"][five]
    A(f"At the frozen point `{five}`: policy paths {p5}; reason codes {r5}. Every eligible build "
      "took the duration-only fallback, because it is the only path the frozen spec has. A policy "
      "that always falls back is itself the finding (development_plan.md P3-T2 S3).\n")
    A("## 6. Provenance\n")
    A(f"- Command: `{res['command']}`; rehearsal `{COMMAND} --mode rehearse` "
      "(`results/p3/replay_rehearsal/rehearsal.json`).")
    A(f"- Code fingerprint `{res['code_fingerprint'][:16]}…`; run fingerprint "
      f"`{res['run_fingerprint'][:16]}…`; grid digest `{res['grid_sha256'][:16]}…`.")
    A(f"- d̂ fit id `{res['trace_provenance']['duration_control_fit_id']}` (primary "
      f"{res['trace_provenance']['duration_control_primary_form']}); p̂ "
      f"`{res['trace_provenance']['risk_arm']}`.")
    A("- All 102 settings: `strategy_results.csv`; herding: `strategy_herding.csv`; trace: "
      "`test_trace.csv.gz`; records: `decisions.csv.gz` (untracked, sha256 pinned in "
      "`strategy_results.json`, DL-028 §4).\n")
    (P3 / "strategy_results.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

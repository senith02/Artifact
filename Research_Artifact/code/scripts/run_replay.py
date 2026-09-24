"""P2-T4 — replay a calibration sample through all six strategies × the sweep grid.

One pass over the backbone CSV keeps the **calibration** projects only (train is
not needed; the test split is dropped unread), builds the replay trace with `d̂`
from the **frozen** P1-T4 control (④a and ④b, never refitted) and `p̂` from the
**frozen** P1-T5 `xgboost:full` arm, draws the DL-023 §4 seeded sample, and runs
every setting of `replay/sweep_grid.json` through `replay/simulator.py`.

⚠ **Wiring check, not a result.** P2-T5 has not fitted `policy_spec.yaml`, so
this run is driven by the **bootstrap** spec — the one exception DL-022 permits.
It is loaded with `require_fitted=False` only because `--allow-unfitted-spec`
is passed on the command line, and every output file is labelled
*bootstrap-derived*. No number produced here is a finding.

Outputs (under ``--out``, default ``results/p2/sample_run/``)
  * ``trace.csv``            the replayed builds (inputs + accounting-only columns)
  * ``decisions.csv.gz``     tidy records, one row per build × strategy × grid point
  * ``summary.{csv,json,md}`` §6 aggregates per setting (bootstrap-derived)
  * ``herding.csv``          per-slot scheduled load per setting
  * ``validator.json``       independent gate-safety audit of every row
  * ``worked_reasons.json``  full `decide()` reason strings for sample builds
  * ``manifest.json``        command, provenance, sha256 of every output

Run from ``code/``:
    PYTHONPATH=. python scripts/run_replay.py --allow-unfitted-spec
    PYTHONPATH=. python scripts/run_replay.py --allow-unfitted-spec --fresh \
        --out <dir> --compare-with ../results/p2/sample_run      # determinism
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from replay import simulator as sim
from replay import validate_invariants as vi
from scheduler_core import (accounting, carbon, config, data, duration_estimator as de,
                            features, models, policy, splits)

CODE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CODE_ROOT.parent
P1 = REPO_ROOT / "results" / "p1"
DEFAULT_OUT = REPO_ROOT / "results" / "p2" / "sample_run"
DEFAULT_PARTS = CODE_ROOT / "artifacts" / "replay_parts"
ARTIFACTS = CODE_ROOT / "artifacts"
RISK_ARM_PATH = ARTIFACTS / "models" / "xgboost__full.joblib"
CHUNK = 300_000

READ_COLUMNS: tuple[str, ...] = tuple(
    c for c in data.EXPECTED_HEADER
    if c in set(features.READ_COLUMNS) | {"git_branch", "tr_duration"}
)

BOOTSTRAP_BANNER = (
    "BOOTSTRAP-DERIVED — P2-T4 wiring check, driven by policy_spec.bootstrap.yaml "
    "(provenance.fitted: false). Not a result; no number here is a finding (DL-022, DL-023 §4)."
)


def log(msg: str) -> None:
    print(msg, flush=True)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Loading: calibration projects only
# --------------------------------------------------------------------------- #

def load_frozen_assignment() -> tuple[dict[str, str], str]:
    manifest = json.loads((P1 / "splits.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(P1 / "split_assignment.csv", dtype=str)
    assignment = dict(zip(frame["gh_project_name"], frame["split"]))
    digest = splits.assignment_hash(assignment)
    if digest != manifest["freeze"]["assignment_sha256"]:
        raise SystemExit("FATAL: split_assignment.csv does not match its frozen digest")
    return assignment, digest


def load_split_builds(assignment: dict[str, str], split: str) -> tuple[pd.DataFrame, dict]:
    """Build-grain analytic rows for one split; every other split dropped per chunk."""
    if split == "test":
        raise SystemExit("FATAL: P2 may never read the test split")
    running: pd.DataFrame | None = None
    dropped_rows = {"train": 0, "calibration": 0, "test": 0, "unassigned": 0}
    dropped_test_builds: set[str] = set()
    for chunk in data.read_chunks(chunksize=CHUNK, usecols=READ_COLUMNS):
        which = chunk["gh_project_name"].map(assignment).fillna("unassigned")
        keep = (which == split).to_numpy()
        for name, n in which[~keep].value_counts().items():
            dropped_rows[str(name)] += int(n)
        dropped_test_builds.update(chunk.loc[(which == "test").to_numpy(), "tr_build_id"])
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
    info = {"job_rows_dropped_by_split": dropped_rows,
            "test_builds_dropped_unread": len(dropped_test_builds)}
    return builds, info


# --------------------------------------------------------------------------- #
# The trace
# --------------------------------------------------------------------------- #

def build_trace(builds: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """d̂ (both forms) + p̂ for every calibration build, before any sampling."""
    frozen = json.loads((P1 / "duration_control.json").read_text(encoding="utf-8"))
    expected_fit_id = frozen["provenance"]["fit_id"]
    estimator = de.DurationEstimator.load(ARTIFACTS / "duration_estimator.joblib")
    if estimator.provenance["fit_id"] != expected_fit_id:
        raise SystemExit("FATAL: duration control is not the frozen P1-T4 artifact")
    if estimator.primary_form != frozen["selection"]["primary_form"]:
        raise SystemExit("FATAL: duration control primary form differs from P1-T4's selection")

    durations = pd.Series(pd.to_numeric(builds["tr_duration"], errors="coerce").to_numpy(),
                          index=builds.index)
    matrix = features.build_feature_matrix(builds)            # asserts no leakage
    y = features.label_from_status(builds)
    if y.isna().any():
        raise SystemExit("FATAL: an analytic build has no label")

    keys = builds[list(features.KEY_COLUMNS)]
    history = de.causal_project_history(keys, durations)      # strictly earlier only
    de.assert_history_is_causal(keys, history)
    est_4a = estimator.predict_4a(matrix, history)
    est_4b = estimator.predict_4b(matrix, history)

    primary = est_4b if estimator.primary_form == "4b" else est_4a
    matrix[models.D_HAT_COLUMN] = primary["d_hat_log1p"].to_numpy()
    features.assert_no_leakage(columns=matrix.columns)
    arm = models.load_arm(RISK_ARM_PATH)
    if (arm.algorithm, arm.arm) != ("xgboost", "full"):
        raise SystemExit(f"FATAL: {RISK_ARM_PATH.name} is {arm.name}, expected xgboost:full")
    p_hat = arm.predict_proba(matrix)

    arrival = features.parse_started_at(builds["gh_build_started_at"])
    trace = pd.DataFrame({
        "replay_seq": 0,
        "tr_build_id": builds["tr_build_id"].astype(str).to_numpy(),
        "gh_project_name": builds["gh_project_name"].to_numpy(),
        "gh_is_pr": builds["gh_is_pr"].to_numpy(),
        "git_branch": builds["git_branch"].to_numpy(),
        "arrival_utc": arrival.dt.strftime("%Y-%m-%d %H:%M:%S+00:00").to_numpy(),
        "arrival_dow": arrival.dt.dayofweek.astype("int64").to_numpy(),
        "arrival_hour": arrival.dt.hour.astype("int64").to_numpy(),
        "d_hat_4a_seconds": est_4a["d_hat_seconds"].to_numpy(),
        "d_hat_4a_fallback": est_4a["fallback_level"].to_numpy(),
        "d_hat_4b_seconds": est_4b["d_hat_seconds"].to_numpy(),
        "d_hat_4b_fallback": est_4b["fallback_level"].to_numpy(),
        "d_hat_4b_n_history": est_4b["n_history"].to_numpy(),
        "p_hat": p_hat,
        # --- accounting only (§A1.2 role 1): never copied into decide()'s input ---
        "obs_duration_s": durations.to_numpy(),
        "y_fail": y.astype("int64").to_numpy(),
    })
    prov = {
        "duration_control_fit_id": expected_fit_id,
        "duration_control_primary_form": estimator.primary_form,
        "risk_arm": arm.name,
        "risk_arm_fit_id": arm.fit_id(),
        "risk_arm_sha256": sha(RISK_ARM_PATH),
        "duration_estimator_sha256": sha(ARTIFACTS / "duration_estimator.joblib"),
        "history_rule": "expanding, strictly earlier (gh_build_started_at < t_b), ties "
                        "excluded — computed over every calibration build before sampling (DL-014)",
    }
    return trace, prov


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def identity_checks(records: pd.DataFrame, grid: sim.SweepGrid) -> dict:
    """DL-023 §1's two stated identities, checked on the records (wiring, not findings)."""
    cols = ["tr_build_id", "action", "delay_hours", "scheduled_slot"]
    by = {sid: g[cols].reset_index(drop=True) for sid, g in records.groupby("setting_id")}
    out: dict = {}
    same_5_4b = all(
        by[f"5_se_informed_policy__d{d:g}__w{w:g}"].equals(
            by[f"4b_duration_prior__d{d:g}__w{w:g}"])
        for w in grid.w_max_hours for d in grid.d_threshold_seconds)
    out["5_equals_4b_at_every_point"] = bool(same_5_4b)
    out["3_equals_4b_at_d0"] = all(
        by[f"3_eligibility_only__d0__w{w:g}"].equals(by[f"4b_duration_prior__d0__w{w:g}"])
        for w in grid.w_max_hours)
    out["6_at_tau0_equals_1_static_actions"] = bool(
        (by["6_risk_only_skip__t0"]["action"] == by["1_static"]["action"]).all())
    return out


def fmt(v, nd=2) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    return f"{float(v):,.{nd}f}"


def write_summary_md(out_dir: Path, summary: pd.DataFrame, manifest: dict) -> None:
    L: list[str] = []
    A = L.append
    A("# P2-T4 — replay simulator sample run (calibration)\n")
    A(f"> ⚠ **{BOOTSTRAP_BANNER}**\n")
    A("> The bootstrap spec's `d_threshold_seconds` is a degenerate 0.0 and its `w_max_hours` "
      "is the DL-008 default; the sweep grid overrides both per point, but the spec is still "
      "**unfitted**, so this is a check that the pipeline runs end to end, is deterministic and "
      "never defers a non-deferrable build — not an estimate of any strategy's effect.\n")
    pop = manifest["population"]
    A("## What was replayed\n")
    A(f"- **{pop['n_sample']:,}** builds, seeded uniform sample (seed {pop['seed']}) of the "
      f"**{pop['calibration_builds']:,}** analytic calibration builds / "
      f"{pop['calibration_projects']:,} projects (DL-023 §4). Sample spans "
      f"{pop['sample_projects']:,} projects, {pop['first_arrival']} → {pop['last_arrival']}.")
    A(f"- Test split **closed**: job rows of test projects were discarded chunk by chunk, before "
      f"any aggregation, join or feature step — {pop['test_builds_dropped_unread']:,} distinct raw "
      "test build ids (counted *before* the analytic funnel, so larger than the 138,693 analytic "
      "test builds in `results/p1/splits_summary.md`). Train builds are not needed and were dropped too.")
    A(f"- Sample failure rate {100 * pop['sample_failure_rate']:.4f}%; "
      f"unaccountable builds (no usable observed duration, DL-023 §3): "
      f"**{pop['n_unaccountable']:,}**, excluded identically from every carbon/TTFF aggregate.")
    A(f"- {manifest['n_settings']} settings (strategy × grid point) × {pop['n_sample']:,} builds "
      f"= **{manifest['n_records']:,}** records.\n")
    A("## Checks (the gate evidence)\n")
    c = manifest["checks"]
    A("| check | result |")
    A("| :-- | :-- |")
    A(f"| every strategy × grid point saw the identical build set, in order | "
      f"{'PASS' if c['identical_build_sets']['identical'] else 'FAIL'} "
      f"({c['identical_build_sets']['settings_compared']} settings × "
      f"{c['identical_build_sets']['builds_per_setting']:,} builds) |")
    v = c["validator"]
    A(f"| independent validator: non-deferrable builds deferred (all rows, all strategies) | "
      f"**{v['violations']}** of {v['deferred']:,} deferrals over {v['rows']:,} rows — "
      f"{'PASS' if v['passed'] else 'FAIL'} |")
    s = c["skip_audit"]
    A(f"| independent validator: non-deferrable builds skipped by ⑥ | **{s['non_deferrable_skipped']}** "
      f"of {s['skipped_rows']:,} skips — {'PASS' if s['passed'] else 'FAIL'} |")
    A(f"| validator self-test (hand-crafted violating fixture must be caught) | "
      f"{'PASS' if c['validator_self_test'] else 'FAIL'} |")
    for k, val in c["identities"].items():
        A(f"| DL-023 §1 identity `{k}` | {'holds' if val else 'DOES NOT HOLD'} |")
    A("\nDeterminism (byte-identical rerun) is recorded separately in `determinism.json`.\n")
    A("## Aggregates per setting — bootstrap-derived, wiring only\n")
    A("Rows shown: every setting of ①②③⑥, and ④a/④b/⑤ at `w_max = 24 h` "
      "(all 102 settings are in `summary.csv`). Carbon uses P_avg = "
      f"{manifest['energy']['p_avg_w']} W (DL-021). p95 = numpy linear-interpolation percentile.\n")
    A("| setting | deferred | skipped | gCO₂e / 1k builds | Δ vs ① | latency p95 h (deferred) | "
      "TTFF p95 h (failed) | missed failures | top-5 slot share |")
    A("| :-- | --: | --: | --: | --: | --: | --: | --: | --: |")
    for r in summary.itertuples():
        if r.strategy in ("4a_duration_estimator", "4b_duration_prior", "5_se_informed_policy") \
                and r.param_w_max_hours != 24:
            continue
        A(f"| `{r.setting_id}` | {fmt(r.n_deferred)} | {fmt(r.n_skipped)} | "
          f"{fmt(r.carbon_per_1000_builds_g, 4)} | {fmt(r.carbon_pct_vs_static)}% | "
          f"{fmt(r.latency_p95_h_deferred)} | {fmt(r.ttff_p95_h_failed)} | "
          f"{fmt(r.missed_failures)} | {fmt(r.herding_top5_slot_share, 4)} |")
    A("\n**How to read this.** ⑤ equals ④b at every point because the bootstrap spec is on "
      "the duration-only path (DL-023 §1) — that is the null path's operational meaning, not a "
      "comparison. ⑥'s carbon falls because skipped builds never run; read it beside "
      "*missed failures*. None of these magnitudes is interpretable until P2-T5 fits the spec "
      "and P3 replays the test split.\n")
    A("## Provenance\n")
    A(f"- Command: `{manifest['command']}`")
    A(f"- Spec: `{manifest['spec']['spec_path']}` (fitted: {manifest['spec']['fitted']})")
    A(f"- Grid: `replay/sweep_grid.json` sha256 `{manifest['grid_sha256'][:16]}…` (DL-023 §2)")
    A(f"- d̂: frozen fit id `{manifest['trace_provenance']['duration_control_fit_id']}`, primary "
      f"form {manifest['trace_provenance']['duration_control_primary_form']}; p̂: "
      f"`{manifest['trace_provenance']['risk_arm']}` fit id "
      f"`{manifest['trace_provenance']['risk_arm_fit_id']}`")
    A(f"- Run fingerprint `{manifest['fingerprint'][:16]}…`; runtime {manifest['runtime_s']:.1f}s")
    A("- sha256 of every output: `manifest.json`")
    (out_dir / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--parts-dir", type=Path, default=DEFAULT_PARTS)
    ap.add_argument("--spec", type=Path, default=policy.BOOTSTRAP_POLICY_SPEC_PATH)
    ap.add_argument("--allow-unfitted-spec", action="store_true",
                    help="required to run on the bootstrap spec (DL-022 §4 exception)")
    ap.add_argument("--fresh", action="store_true",
                    help="recompute every part (ignore resumable parts)")
    ap.add_argument("--compare-with", type=Path, default=None,
                    help="a previous run's --out dir; compare output sha256s (determinism)")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.time()
    command = "PYTHONPATH=. python scripts/run_replay.py " + " ".join(sys.argv[1:])
    grid = sim.load_sweep_grid()
    spec = policy.load_policy_spec(args.spec, require_fitted=not args.allow_unfitted_spec)
    if not spec.fitted:
        log(f"⚠ {BOOTSTRAP_BANNER}")
    energy = accounting.load_energy_config()
    profile = carbon.load_hour_of_week_profile()
    split = str(grid.sample["split"])

    log(f"reading {data.DEFAULT_DATASET_PATH} (keeping the {split} split only) …")
    assignment, split_digest = load_frozen_assignment()
    builds, load_info = load_split_builds(assignment, split)
    if set(builds["gh_project_name"].map(assignment)) != {split}:
        raise SystemExit(f"FATAL: a non-{split} project reached the trace")
    log(f"  {len(builds):,} analytic {split} builds / {builds['gh_project_name'].nunique():,} "
        f"projects; test builds dropped unread: {load_info['test_builds_dropped_unread']:,} "
        f"({time.time() - t0:.0f}s)")

    log("building the trace: d̂ (④a, ④b) from the frozen control, p̂ from xgboost:full …")
    full_trace, trace_prov = build_trace(builds)
    sample = sim.sample_builds(full_trace, int(grid.sample["n_builds"]), int(grid.sample["seed"]))
    trace = sim.order_trace(sample)
    sim.validate_trace(trace)
    unacc = int((~sim.accountable_mask(trace)).sum())
    log(f"  sample: {len(trace):,} builds / {trace['gh_project_name'].nunique():,} projects; "
        f"unaccountable {unacc}; failure rate {trace['y_fail'].mean():.4%}")

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    trace_path = out / "trace.csv"
    trace[list(sim.TRACE_COLUMNS)].to_csv(trace_path, index=False, lineterminator="\n", na_rep="")

    settings = sim.enumerate_settings(grid)
    fingerprint = sim.run_fingerprint(
        trace=trace, grid=grid, base_spec=spec, p_avg_w=energy.p_avg_w,
        primary_form=trace_prov["duration_control_primary_form"],
        profile_path=carbon.DEFAULT_PROFILE_PATH,
        extra={"split_digest": split_digest, **trace_prov})
    log(f"\nreplaying {len(settings)} settings × {len(trace):,} builds "
        f"(fingerprint {fingerprint[:16]}, resume={'off' if args.fresh else 'on'}) …")
    parts = sim.run_sweep(
        trace, settings, base_spec=spec, profile=profile, p_avg_w=energy.p_avg_w,
        primary_form=trace_prov["duration_control_primary_form"], parts_dir=args.parts_dir,
        fingerprint=fingerprint, resume=not args.fresh, progress=log)
    decisions_path = out / "decisions.csv.gz"
    sim.assemble(parts, decisions_path)

    log("\nchecking the assembled records …")
    records = sim.load_records(decisions_path)
    identical = sim.assert_identical_build_sets(records)
    audit = vi.audit_frame(records, variant=spec.stage1_variant, path=str(decisions_path))
    skip_audit = sim.audit_skips(records, variant=spec.stage1_variant)
    self_test = vi.audit_frame(pd.DataFrame({
        "gh_is_pr": ["false", "true", "false"], "git_branch": ["feature/x", "feature/y", "master"],
        "action": ["defer", "defer", "defer"]})).violations == 2
    identities = identity_checks(records, grid)
    log(f"  identical build sets: {identical}")
    log(f"  validator: {audit.violations} violations / {audit.deferred:,} deferrals / "
        f"{audit.rows:,} rows; skips of non-deferrable builds: "
        f"{skip_audit['non_deferrable_skipped']}; self-test {'PASS' if self_test else 'FAIL'}")
    log(f"  identities: {identities}")

    summary, herding = sim.summarise(records)
    summary.to_csv(out / "summary.csv", index=False, lineterminator="\n", na_rep="")
    herding.to_csv(out / "herding.csv", index=False, lineterminator="\n")
    (out / "validator.json").write_text(json.dumps(
        {"banner": BOOTSTRAP_BANNER, "variant": spec.stage1_variant,
         "gate_safety": audit.as_dict(), "skip_audit": skip_audit,
         "self_test_catches_violating_fixture": self_test,
         "note": "DL-020 §6: a pass proves consistency with the eligibility RULE, not that the "
                 "rule identifies genuinely deferrable builds."},
        indent=2, default=str) + "\n", encoding="utf-8")

    showcase = [s for s in settings if s.setting_id in {
        "2_blanket_carbon_aware__d0__w167", "3_eligibility_only__d0__w24",
        "4a_duration_estimator__d960__w24", "4b_duration_prior__d960__w24",
        "5_se_informed_policy__d960__w24"}]
    reasons = sim.worked_reasons(trace, showcase, base_spec=spec, profile=profile,
                                 primary_form=trace_prov["duration_control_primary_form"])
    (out / "worked_reasons.json").write_text(json.dumps(
        {"banner": BOOTSTRAP_BANNER, "examples": reasons}, indent=2, default=str) + "\n",
        encoding="utf-8")

    population = {
        "split": split, "calibration_builds": int(len(full_trace)),
        "calibration_projects": int(full_trace["gh_project_name"].nunique()),
        "n_sample": int(len(trace)), "seed": int(grid.sample["seed"]),
        "sample_projects": int(trace["gh_project_name"].nunique()),
        "first_arrival": str(trace["arrival_utc"].iloc[0]),
        "last_arrival": str(trace["arrival_utc"].iloc[-1]),
        "sample_failure_rate": float(trace["y_fail"].mean()),
        "n_unaccountable": unacc,
        "d_hat_4b_fallback_levels": trace["d_hat_4b_fallback"].value_counts().to_dict(),
        **load_info,
    }
    outputs = ["trace.csv", "decisions.csv.gz", "summary.csv", "herding.csv",
               "validator.json", "worked_reasons.json"]
    manifest = {
        "banner": BOOTSTRAP_BANNER,
        "task": "P2-T4", "decision_log": ["DL-022", "DL-023"],
        "command": command, "run_date": time.strftime("%Y-%m-%d"),
        "fingerprint": fingerprint, "grid_sha256": grid.digest(),
        "spec": spec.provenance_record(), "energy": energy.provenance(),
        "split_assignment_sha256": split_digest,
        "trace_provenance": trace_prov, "population": population,
        "n_settings": len(settings), "n_records": int(len(records)),
        "checks": {"identical_build_sets": identical,
                   "validator": audit.as_dict() | {"violation_rows": audit.violation_rows[:5]},
                   "skip_audit": skip_audit, "validator_self_test": self_test,
                   "identities": identities},
        "seed": config.RANDOM_SEED,
        "runtime_s": round(time.time() - t0, 1),
        "sha256": {name: sha(out / name) for name in outputs},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n",
                                       encoding="utf-8")
    write_summary_md(out, summary, manifest)
    log(f"\nwrote {out} ({manifest['runtime_s']:.0f}s)")

    ok = identical["identical"] and audit.passed and skip_audit["passed"] and self_test
    if args.compare_with is not None:
        other = json.loads((args.compare_with / "manifest.json").read_text(encoding="utf-8"))
        rows = {name: {"this_run": manifest["sha256"][name],
                       "other_run": other["sha256"].get(name),
                       "identical": manifest["sha256"][name] == other["sha256"].get(name)}
                for name in ("trace.csv", "decisions.csv.gz", "summary.csv", "herding.csv")}
        det = {"this_run": str(out), "other_run": str(args.compare_with),
               "command": command, "fresh": bool(args.fresh),
               "fingerprints_equal": manifest["fingerprint"] == other["fingerprint"],
               "files": rows, "byte_identical": all(r["identical"] for r in rows.values())}
        for target in (out, args.compare_with):
            (target / "determinism.json").write_text(json.dumps(det, indent=2) + "\n",
                                                     encoding="utf-8")
        log(f"determinism vs {args.compare_with}: "
            f"{'BYTE-IDENTICAL' if det['byte_identical'] else 'DIFFERS'} {rows}")
        ok = ok and det["byte_identical"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

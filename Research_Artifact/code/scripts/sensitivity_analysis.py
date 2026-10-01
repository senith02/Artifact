"""P3-T4 — sensitivity sweeps and the "verdict stable / flips" table (DL-030).

Each sweep is run by name and writes ``results/p3/sensitivity/<name>.json``; ``--summary``
assembles ``results/p3/sensitivity.md`` and its figures from those files.

    baseline  V4 recomputed on the P3-T2 parts (must match strategy_results.json's classes)
    a  deferrable-fraction variant (re-replay, stage-1 `protected_includes_integration`)
    b  W_max ∈ {6, 12, 24} from the P3-T2 records (banded shape: not applicable)
    c  energy P_avg × {0.5, 1.5} (exact rescale)
    d  n_jobs-scaled energy (exact rescale by each build's job-row count)
    e  temporal robustness at the DL-027 boundary (V1 per period; V2/V3 per period)
    f  second grid profile (DL-027 §2; needs the Electricity Maps CSVs)
    g  cold-start builds excluded (V1, V2, V3)
    h  ④b trailing-50 control form (re-replay of the 30 ④b settings)
    herding   per-headline-setting slot concentration (descriptive)

Verdicts (DL-030 §1): V1 model-level admitted set (×1) · V2 "⑤ beats both ④a and ④b" (×1) ·
V3 §A1.7 condition for ④b (≡ ⑤) over ④a (×1) · V4 the eight-class RQ4 sign pattern of ⑤
against ①, ②, ③, ④a on carbon per 1,000 builds and TTFF p95.

Nothing is fitted. Run from ``code/``:  PYTHONPATH=. python scripts/sensitivity_analysis.py --sweep a
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CODE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = CODE_ROOT / "scripts"
for p in (CODE_ROOT, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fetch_carbon as fc                                                 # noqa: E402
import frontier_analysis as fa                                            # noqa: E402
import run_replay as rr                                                   # noqa: E402
import run_test_replay as rt                                              # noqa: E402
from replay import simulator as sim                                      # noqa: E402
from scheduler_core import (ablation_stats as ab, accounting, admission,  # noqa: E402
                            carbon, config, data, duration_estimator as de, features, policy)

ROOT = CODE_ROOT.parent
P3 = ROOT / "results" / "p3"
OUT = P3 / "sensitivity"
FIG = P3 / "figures"
COMMAND = "PYTHONPATH=. python scripts/sensitivity_analysis.py"
EM_DIR = ROOT.parent / "Dataset" / "electricitymaps"
GRID2_DIR = CODE_ROOT / "data" / "carbon" / "second_grid"
N_RESAMPLES = 1000
D_FROZEN, W_FROZEN = 480.0, 24.0
FAMILIES = tuple(features.FAMILIES.keys())
V3_PAIR = "4a_duration_estimator|5_se_informed_policy"      # ④b ≡ ⑤ over ④a (P3-T3 §6b)
TRAIL = "4b50_trailing_prior"
UK_PEAK_TO_TROUGH = 172.914 / 92.24                          # results/p0/carbon_profile.md
ZONES = (("CAISO", "US-CAL-CISO"), ("Germany", "DE"))       # DL-027 §2 ordered list


def log(msg: str) -> None:
    print(msg, flush=True)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Shared context
# --------------------------------------------------------------------------- #

class Ctx:
    def __init__(self) -> None:
        self.grid = sim.load_sweep_grid()
        self.spec, self.spec_sha = rt.load_frozen_spec(self.grid)
        self.energy = accounting.load_energy_config()
        self.profile = carbon.load_hour_of_week_profile()
        self.p3t2 = json.loads((P3 / "strategy_results.json").read_text(encoding="utf-8"))
        self.parts_dir = rt.DEFAULT_PARTS / self.p3t2["run_fingerprint"][:16]
        self.settings = sim.enumerate_settings(self.grid)
        self._trace: pd.DataFrame | None = None

    @property
    def trace(self) -> pd.DataFrame:
        if self._trace is None:
            t = fa.load_tracked_trace()
            sim.validate_trace(t)
            self._trace = t
        return self._trace

    def prove_trace(self) -> bool:
        """DL-030 §4: re-replaying one P3-T2 part from the tracked trace is byte-identical."""
        probe = next(s for s in self.settings if s.setting_id == "4b_duration_prior__d480__w24")
        part = self.parts_dir / f"{self.settings.index(probe):04d}__{probe.setting_id}.csv"
        rec = sim.replay_setting(self.trace, probe, base_spec=self.spec, profile=self.profile,
                                 p_avg_w=self.energy.p_avg_w, primary_form="4b")
        ok = sim.records_to_csv_bytes(rec, header=False) == part.read_bytes()
        if not ok:
            raise SystemExit("FATAL: the tracked test trace does not reproduce P3-T2")
        return ok

    def matrices(self, parts_dir: Path | None = None, settings: list[sim.Setting] | None = None,
                 wanted: set[str] | None = None, finalise: bool = True) -> fa.Matrices:
        settings = settings or self.settings
        wanted = wanted or ({"1_static"} | {s.setting_id for s in settings if s.strategy in fa.FORMS})
        m, _ = fa.load_matrices(parts_dir or self.parts_dir, settings, wanted)
        if finalise:
            m.finalise()
        return m


def headline_ids(w: float) -> dict[str, str]:
    return {"5": f"5_se_informed_policy__d{D_FROZEN:g}__w{w:g}", "1": "1_static",
            "2": "2_blanket_carbon_aware__d0__w167", "3": f"3_eligibility_only__d0__w{w:g}",
            "4a": f"4a_duration_estimator__d{D_FROZEN:g}__w{w:g}"}


def v4_wanted(ws: tuple[float, ...] = (W_FROZEN,)) -> set[str]:
    out: set[str] = set()
    for w in ws:
        out |= set(headline_ids(w).values())
    return out


# --------------------------------------------------------------------------- #
# V4 — the RQ4 sign pattern (DL-030 §1)
# --------------------------------------------------------------------------- #

def _carbon_ttff(m: fa.Matrices, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c = (m.C @ w) / float(np.dot(m.accountable, w)) * 1000.0
    rep = np.repeat(np.arange(len(m.failed_pos)), w[m.failed_pos].astype("int64"))
    t = np.percentile(m.T[:, rep], 95, axis=1)
    return c, t


def _cls(lo: float, hi: float) -> str:
    return "lower" if hi < 0 else ("higher" if lo > 0 else "n.s.")


def v4(m: fa.Matrices, mask: np.ndarray, w_max: float = W_FROZEN, *,
       n_resamples: int = N_RESAMPLES) -> dict[str, Any]:
    ids = headline_ids(w_max)
    idx = {k: m.index[v] for k, v in ids.items()}
    w0 = mask.astype("float64")
    c0, t0 = _carbon_ttff(m, w0)
    rng = np.random.default_rng(config.RANDOM_SEED)
    n = len(mask)
    dc = {k: np.empty(n_resamples) for k in ("1", "2", "3", "4a")}
    dt = {k: np.empty(n_resamples) for k in ("1", "2", "3", "4a")}
    for b in range(n_resamples):
        w = np.bincount(rng.integers(0, n, size=n), minlength=n).astype("float64") * w0
        c, t = _carbon_ttff(m, w)
        for k in dc:
            dc[k][b] = c[idx["5"]] - c[idx[k]]
            dt[k][b] = t[idx["5"]] - t[idx[k]]
    out: dict[str, Any] = {"w_max_hours": w_max, "setting_ids": ids, "pairs": {}}
    for k in dc:
        rec = {}
        for metric, point, d in (("carbon_per_1000_builds_g", c0[idx["5"]] - c0[idx[k]], dc[k]),
                                 ("ttff_p95_h_failed", t0[idx["5"]] - t0[idx[k]], dt[k])):
            lo, hi = float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))
            rec[metric] = {"point": float(point), "ci_lo": lo, "ci_hi": hi, "class": _cls(lo, hi)}
        out["pairs"][f"5_minus_{k}"] = rec
    out["classes"] = [out["pairs"][f"5_minus_{k}"][mtr]["class"] for k in ("1", "2", "3", "4a")
                      for mtr in ("carbon_per_1000_builds_g", "ttff_p95_h_failed")]
    return out


def baseline_classes() -> list[str]:
    p = OUT / "baseline.json"
    return json.loads(p.read_text(encoding="utf-8"))["v4"]["classes"]


def v4_verdict(res: dict) -> dict[str, Any]:
    base = baseline_classes()
    return {"classes": res["classes"], "baseline": base, "stable": res["classes"] == base}


# --------------------------------------------------------------------------- #
# V1 — model-level admission on a subset of test builds
# --------------------------------------------------------------------------- #

def load_scores() -> pd.DataFrame:
    return pd.read_csv(P3 / "test_scores.csv.gz", dtype={"tr_build_id": str},
                       float_precision="round_trip")


def v1(scores: pd.DataFrame, mask: np.ndarray, label: str) -> dict[str, Any]:
    sub = scores.loc[mask]
    y = sub["y_fail"].to_numpy(dtype="int64")
    ctrl = sub["p__xgboost__control"].to_numpy()
    deltas = {}
    for fam in FAMILIES:
        log(f"    [{label}] paired delta {fam} ({len(sub):,} builds) …")
        deltas[fam] = ab.paired_metric_delta(y, ctrl, sub[f"p__xgboost__{fam}"].to_numpy())
    pr = {fam: deltas[fam]["pr_auc"] for fam in FAMILIES}
    x1 = admission.admission_set(pr)
    return {"n_builds": int(len(sub)), "failure_rate": float(y.mean()),
            "deltas_pr_auc": pr, "admitted_x1": x1["admitted"],
            "floor_sweep": {k: v["admitted"] for k, v in admission.floor_sweep(pr)["by_floor"].items()}}


def v1_baseline() -> list[str]:
    rep = json.loads((P3 / "model_report.json").read_text(encoding="utf-8"))
    return rep["admission"]["x1"]["admitted"]


# --------------------------------------------------------------------------- #
# V2 / V3 — DL-029 machinery on a population
# --------------------------------------------------------------------------- #

def v23(m: fa.Matrices, mask: np.ndarray, label: str, **kw) -> dict[str, Any]:
    res = fa.analyse(m, mask, n_resamples=N_RESAMPLES, label=label,
                     strategies=kw.get("strategies", fa.FORMS), pairs=kw.get("pairs", fa.PAIRS))
    p3 = json.loads((P3 / "incremental_value_decision.json").read_text(encoding="utf-8"))
    base_all = p3["populations"]["all"]
    v2 = res.get("verdict_se_adds_value", {}).get("x1")
    v3 = res["pairs"][V3_PAIR]["condition"]["x1"]
    return {
        "V2": {"value": v2, "baseline": base_all["verdict_se_adds_value"]["x1"],
               "stable": v2 == base_all["verdict_se_adds_value"]["x1"]},
        "V3": {"value": v3, "baseline": base_all["pairs"][V3_PAIR]["condition"]["x1"],
               "stable": v3 == base_all["pairs"][V3_PAIR]["condition"]["x1"],
               "area": res["pairs"][V3_PAIR]["area"]},
        "areas": {k: v["area"] for k, v in res["pairs"].items()},
        "conditions": {k: v["condition"] for k, v in res["pairs"].items()},
        # why a condition holds or fails: every matched point, per axis (DL-029 §5)
        "matched": {k: {axis: {f: v[f"matched_at_{axis}"][f] for f in
                               ("grid", "point_rel", "ci_lo", "ci_hi", "undefined_share", "counts")}
                        for axis in ("carbon", "ttff")}
                    for k, v in res["pairs"].items()},
        "n_builds": res["n_builds"], "n_projects": res["n_projects"],
        "frontiers": res["frontiers"],
    }


# --------------------------------------------------------------------------- #
# Re-replay helper (S-a, S-f, S-h)
# --------------------------------------------------------------------------- #

def replay(ctx: Ctx, trace: pd.DataFrame, settings: list[sim.Setting], spec: policy.PolicySpec,
           profile: pd.DataFrame, profile_path: Path, extra: dict) -> tuple[list[Path], dict]:
    fp = sim.run_fingerprint(trace=trace, grid=ctx.grid, base_spec=spec, p_avg_w=ctx.energy.p_avg_w,
                             primary_form="4b", profile_path=profile_path, extra=extra)
    log(f"  replaying {len(settings)} settings (fingerprint {fp[:16]}) …")
    parts = sim.run_sweep(trace, settings, base_spec=spec, profile=profile,
                          p_avg_w=ctx.energy.p_avg_w, primary_form="4b",
                          parts_dir=rt.DEFAULT_PARTS, fingerprint=fp, resume=True, progress=log)
    agg = rt.aggregate_parts(parts, settings, reference_ids=trace["tr_build_id"].astype(str).tolist(),
                             variant=spec.stage1_variant, keep_per_build=[])
    checks = {"run_fingerprint": fp, "validator": agg["validator"], "skip_audit": agg["skip_audit"],
              "identical_build_sets": agg["identical_build_sets"],
              "identities": rt.identity_checks(agg, ctx.grid) if len(settings) == len(ctx.settings) else None}
    return parts, {"checks": checks, "summary": agg["summary"]}


# --------------------------------------------------------------------------- #
# The sweeps
# --------------------------------------------------------------------------- #

def sweep_baseline(ctx: Ctx) -> dict:
    m = ctx.matrices(wanted=v4_wanted())
    res = v4(m, np.ones(len(m.ids), dtype=bool))
    p3t2 = ctx.p3t2["bootstrap"]["differences"]
    five = headline_ids(W_FROZEN)["5"]
    cross = []
    for k in ("1", "2", "3", "4a"):
        other = headline_ids(W_FROZEN)[k]
        key = f"{other}__minus__{five}"
        for metric in ("carbon_per_1000_builds_g", "ttff_p95_h_failed"):
            rec = p3t2[metric][key]                      # P3-T2 stored other − five
            ref = _cls(-rec["ci_hi"], -rec["ci_lo"])
            mine = res["pairs"][f"5_minus_{k}"][metric]
            cross.append({"pair": f"5_minus_{k}", "metric": metric, "p3t2_class": ref,
                          "this_class": mine["class"],
                          "point_abs_diff": abs(mine["point"] + rec["point"])})
    ok = all(c["p3t2_class"] == c["this_class"] for c in cross)
    return {"v4": res, "cross_check_vs_p3t2": {"rows": cross, "classes_match": ok},
            "v1_baseline": v1_baseline(), "note": "V4 baseline recomputed from the P3-T2 parts"}


def sweep_a(ctx: Ctx) -> dict:
    ctx.prove_trace()
    raw = copy.deepcopy(dict(ctx.spec.raw))
    raw["stage1"] = {**raw["stage1"], "variant": "protected_includes_integration"}
    spec_v = policy.spec_from_mapping(raw, source_path=ctx.spec.source_path, require_fitted=True)
    parts, info = replay(ctx, ctx.trace, ctx.settings, spec_v, ctx.profile,
                         carbon.DEFAULT_PROFILE_PATH, {"sweep": "S-a", "variant": spec_v.stage1_variant})
    m = ctx.matrices(parts_dir=parts[0].parent, wanted=v4_wanted() | {
        s.setting_id for s in ctx.settings if s.strategy in fa.FORMS})
    mask = np.ones(len(m.ids), dtype=bool)
    summ = info["summary"].set_index("setting_id")
    return {"variant": spec_v.stage1_variant, "checks": info["checks"],
            "eligible_share": float(summ.loc[headline_ids(W_FROZEN)["5"], "n_eligible"]
                                    / summ.loc[headline_ids(W_FROZEN)["5"], "n_builds"]),
            "headline": summ.loc[list(headline_ids(W_FROZEN).values())].reset_index().to_dict("records"),
            **v23(m, mask, "S-a"), "V4": v4_verdict(v4(m, mask))}


def sweep_b(ctx: Ctx) -> dict:
    ws = tuple(ctx.grid.w_max_hours)
    m = ctx.matrices(wanted=v4_wanted(ws))
    mask = np.ones(len(m.ids), dtype=bool)
    per_w = {f"w{w:g}": v4(m, mask, w) for w in ws}
    base = baseline_classes()
    return {"per_w": per_w,
            "V4_by_w": {k: {"classes": v["classes"], "stable": v["classes"] == base}
                        for k, v in per_w.items()},
            "banded_window": "not applicable — the banded shape maps a failure probability to a "
                             "window, which exists only on the risk-adjusted path; the frozen spec "
                             "admits no family (DL-030 §2 S-b)",
            "V2_V3": "not re-evaluated — the P3-T3 frontiers already span W ∈ {6, 12, 24}"}


def _scaled(m: fa.Matrices, factor: np.ndarray) -> fa.Matrices:
    s = copy.copy(m)
    s.C = m.C * factor[None, :]
    return s


def sweep_c(ctx: Ctx) -> dict:
    m = ctx.matrices(wanted=v4_wanted() | {s.setting_id for s in ctx.settings if s.strategy in fa.FORMS})
    mask = np.ones(len(m.ids), dtype=bool)
    out = {}
    for mult in (0.5, 1.5):
        s = _scaled(m, np.full(len(m.ids), mult))
        log(f"  P_avg × {mult} …")
        c1, _ = _carbon_ttff(s, mask.astype("float64"))
        out[f"x{mult:g}"] = {"p_avg_w": ctx.energy.p_avg_w * mult,
                             "carbon_per_1000_frozen_point": float(c1[s.index[headline_ids(W_FROZEN)["5"]]]),
                             **v23(s, mask, f"S-c x{mult:g}"), "V4": v4_verdict(v4(s, mask))}
    return out


def _n_jobs(ctx: Ctx) -> np.ndarray:
    assignment, _ = rr.load_frozen_assignment()
    ids = set(ctx.trace["tr_build_id"].astype(str))
    counts: dict[str, int] = {}
    for chunk in data.read_chunks(chunksize=rt.CHUNK, usecols=("tr_build_id", "gh_project_name")):
        chunk = chunk.loc[chunk["gh_project_name"].map(assignment) == "test"]
        for k, v in chunk["tr_build_id"].astype(str).value_counts().items():
            if k in ids:
                counts[k] = counts.get(k, 0) + int(v)
    return np.array([counts[i] for i in ctx.trace["tr_build_id"].astype(str)], dtype="float64")


def sweep_d(ctx: Ctx) -> dict:
    m = ctx.matrices(wanted=v4_wanted() | {s.setting_id for s in ctx.settings if s.strategy in fa.FORMS})
    log("  counting job rows per test build …")
    nj = _n_jobs(ctx)
    if not np.array_equal(ctx.trace["tr_build_id"].astype(str).to_numpy(), m.ids):
        raise SystemExit("FATAL: trace and matrices are not aligned")
    s = _scaled(m, nj)
    mask = np.ones(len(m.ids), dtype=bool)
    return {"n_jobs": {"mean": float(nj.mean()), "median": float(np.median(nj)),
                       "max": int(nj.max()), "share_single_job": float((nj == 1).mean())},
            **v23(s, mask, "S-d"), "V4": v4_verdict(v4(s, mask))}


def sweep_e(ctx: Ctx) -> dict:
    boundary = pd.Timestamp(json.loads((P3 / "predeclared" / "temporal_boundary.json")
                                       .read_text(encoding="utf-8"))["boundary_utc"])
    m = ctx.matrices()
    arrival = pd.to_datetime(ctx.trace["arrival_utc"], utc=True)
    if not np.array_equal(ctx.trace["tr_build_id"].astype(str).to_numpy(), m.ids):
        raise SystemExit("FATAL: trace and matrices are not aligned")
    scores = load_scores().set_index("tr_build_id").loc[m.ids].reset_index()
    early = (arrival < boundary).to_numpy()
    base_v1 = v1_baseline()
    out = {"boundary_utc": boundary.isoformat()}
    for name, mask in (("early", early), ("late", ~early)):
        log(f"  period {name}: {int(mask.sum()):,} builds")
        r1 = v1(scores, mask, name)
        out[name] = {"V1": {"value": r1["admitted_x1"], "baseline": base_v1,
                            "stable": r1["admitted_x1"] == base_v1, "detail": r1},
                     **v23(m, mask, f"S-e {name}")}
    return out


def sweep_g(ctx: Ctx) -> dict:
    m = ctx.matrices()
    if not np.array_equal(ctx.trace["tr_build_id"].astype(str).to_numpy(), m.ids):
        raise SystemExit("FATAL: trace and matrices are not aligned")
    mask = (ctx.trace["d_hat_4b_fallback"] == "project").to_numpy()
    scores = load_scores().set_index("tr_build_id").loc[m.ids].reset_index()
    r1 = v1(scores, mask, "S-g")
    base_v1 = v1_baseline()
    return {"excluded_builds": int((~mask).sum()),
            "V1": {"value": r1["admitted_x1"], "baseline": base_v1,
                   "stable": r1["admitted_x1"] == base_v1, "detail": r1},
            **v23(m, mask, "S-g")}


def _trailing_d_hat(ctx: Ctx) -> np.ndarray:
    assignment, _ = rr.load_frozen_assignment()
    builds, _ = rt.load_split_builds(assignment, "test")
    durations = pd.Series(pd.to_numeric(builds["tr_duration"], errors="coerce").to_numpy(),
                          index=builds.index)
    matrix = features.build_feature_matrix(builds)
    keys = builds[list(features.KEY_COLUMNS)]
    est = de.DurationEstimator.load(rr.ARTIFACTS / "duration_estimator.joblib")
    expanding = est.predict_4b(matrix, de.causal_project_history(keys, durations))
    hist50 = de.causal_project_history(keys, durations, window=50)
    de.assert_history_is_causal(keys, hist50)
    trailing = est.predict_4b(matrix, hist50)
    ids = builds["tr_build_id"].astype(str)
    exp_s = pd.Series(expanding["d_hat_seconds"].to_numpy(), index=ids)
    tr_s = pd.Series(trailing["d_hat_seconds"].to_numpy(), index=ids)
    order = ctx.trace["tr_build_id"].astype(str)
    if not np.array_equal(exp_s.loc[order].to_numpy(), ctx.trace["d_hat_4b_seconds"].to_numpy()):
        raise SystemExit("FATAL: recomputed expanding d̂ differs from the P3-T2 trace")
    return tr_s.loc[order].to_numpy()


def sweep_h(ctx: Ctx) -> dict:
    ctx.prove_trace()
    log("  computing the trailing-50 d̂ for every test build …")
    t50 = _trailing_d_hat(ctx)
    trace = ctx.trace.copy()
    trace["d_hat_4b_seconds"] = t50
    trace["d_hat_4b_fallback"] = "trailing50_" + ctx.trace["d_hat_4b_fallback"].astype(str)
    settings = [s for s in ctx.settings if s.strategy == "4b_duration_prior"]
    parts, info = replay(ctx, trace, settings, ctx.spec, ctx.profile, carbon.DEFAULT_PROFILE_PATH,
                         {"sweep": "S-h", "d_hat": "4b trailing-50"})
    m = ctx.matrices(finalise=False)
    for part, s in zip(parts, settings):
        m.add(f"{TRAIL}__d{s.d_threshold_seconds:g}__w{s.w_max_hours:g}",
              (s.d_threshold_seconds, s.w_max_hours), rt.read_part(part))
    m.finalise()
    mask = np.ones(len(m.ids), dtype=bool)
    pairs = fa.PAIRS + (("4b_duration_prior", TRAIL), ("4a_duration_estimator", TRAIL))
    res = v23(m, mask, "S-h", strategies=fa.FORMS + (TRAIL,), pairs=pairs)
    return {"label": "sensitivity of the duration control — not the policy of record",
            "checks": info["checks"], **res,
            "trailing_vs_4b": res["areas"][f"4b_duration_prior|{TRAIL}"],
            "trailing_vs_4a": res["areas"][f"4a_duration_estimator|{TRAIL}"],
            "trailing_vs_4b_condition": res["conditions"][f"4b_duration_prior|{TRAIL}"],
            "trailing_vs_4a_condition": res["conditions"][f"4a_duration_estimator|{TRAIL}"]}


def sweep_herding(ctx: Ctx) -> dict:
    herd = pd.read_csv(P3 / "strategy_herding.csv")
    ids = list(dict.fromkeys(list(headline_ids(W_FROZEN).values())
                             + [f"4b_duration_prior__d{D_FROZEN:g}__w{W_FROZEN:g}"]))
    out = {}
    for sid in ids:
        n = herd.loc[herd["setting_id"] == sid, "n_scheduled"].to_numpy()
        s = np.sort(n)[::-1] / n.sum()
        out[sid] = {"top5_share": float(s[:5].sum()), "max_slot_share": float(s[0])}
    base = out["1_static"]
    for sid, r in out.items():
        r["top5_ratio_to_static"] = r["top5_share"] / base["top5_share"]
        r["max_ratio_to_static"] = r["max_slot_share"] / base["max_slot_share"]
    return {"settings": out, "note": "descriptive only; no threshold was predeclared (DL-030 §3)"}


# --------------------------------------------------------------------------- #
# S-f — the second grid profile (DL-027 §2)
# --------------------------------------------------------------------------- #

EIA_XLSX = ROOT.parent / "Dataset" / "eia930" / "CISO.xlsx"
EIA_URL = "https://www.eia.gov/electricity/gridmonitor/knownissues/xls/CISO.xlsx"
EIA_COLUMN = "CO2 Emissions Intensity for Consumed Electricity"      # DL-031 §2
G_PER_LB = 453.59237                                                   # DL-031 §3


def load_eia930_hourly(path: Path, column: str = EIA_COLUMN) -> pd.Series:
    """Hourly g CO₂/kWh from an EIA-930 per-BA workbook, stamped at hour **start** (UTC).

    Standard library only (DL-031 §5). "UTC time" is an Excel 1900-system serial marking the
    **end** of the hour, so each value is shifted −1 h (DL-031 §4). EIA's unit is lb/kWh (§3).
    """
    import datetime as dt
    import xml.etree.ElementTree as ET
    import zipfile

    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(path)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    names = [s.get("name") for s in wb.find(ns + "sheets")]
    sheet = f"xl/worksheets/sheet{names.index('Published Hourly Data') + 1}.xml"
    shared: list[str] = []
    with z.open("xl/sharedStrings.xml") as fh:
        for _ev, el in ET.iterparse(fh):
            if el.tag == ns + "si":
                shared.append("".join(t.text or "" for t in el.iter() if t.tag == ns + "t"))
                el.clear()
    epoch = dt.datetime(1899, 12, 30)
    header: dict[str, str] = {}
    t_col = v_col = None
    times: list[dt.datetime] = []
    vals: list[float] = []
    with z.open(sheet) as fh:
        for _ev, el in ET.iterparse(fh):
            if el.tag != ns + "row":
                continue
            cells: dict[str, str] = {}
            for c in el:
                v = c.find(ns + "v")
                if v is None:
                    continue
                ref = "".join(ch for ch in c.get("r") if ch.isalpha())
                cells[ref] = shared[int(v.text)] if c.get("t") == "s" else v.text
            if not header:
                header = cells
                t_col = next(k for k, h in header.items() if h == "UTC time")
                v_col = next(k for k, h in header.items() if h == column)
            else:
                end = epoch + dt.timedelta(days=float(cells[t_col]))
                end = end.replace(microsecond=0)
                # serials are floats: snap to the whole hour they denote
                end = (end + dt.timedelta(minutes=30)).replace(minute=0, second=0)
                raw = cells.get(v_col)
                times.append(end - dt.timedelta(hours=1))
                vals.append(float(raw) * G_PER_LB if raw not in (None, "") else float("nan"))
            el.clear()
    s = pd.Series(vals, index=pd.DatetimeIndex(times).tz_localize("UTC")).sort_index()
    return s[~s.index.duplicated(keep="first")]


def build_eia_profile(zone: str = "CAISO", path: Path | None = None) -> dict:
    path = path or EIA_XLSX
    if not Path(path).exists():
        return {"zone": zone, "status": "no files", "looked_in": str(path)}
    s = load_eia930_hourly(Path(path))
    full = pd.date_range(fc.SPAN_START, fc.SPAN_END, freq="h", inclusive="left", tz="UTC")
    hourly = pd.DataFrame({"gco2_per_kwh": s.reindex(full)})
    hourly.index.name = "timestamp_utc"
    cov = fc.coverage_per_year(hourly)
    prof = fc.hour_of_week_profile(hourly)
    ptt = float(prof["mean"].max() / prof["mean"].min()) if prof["mean"].notna().all() else None
    crit = {"a_free_public_source": True,
            "b_coverage_ge_95": all(v["coverage_pct"] is not None and v["coverage_pct"] >= 95
                                    for v in cov.values()),
            "c_peak_to_trough_gt_uk": bool(ptt is not None and ptt > UK_PEAK_TO_TROUGH)}
    return {"zone": zone, "zone_id": "US-CAL-CISO", "source": "EIA-930 (DL-031)", "url": EIA_URL,
            "files": [Path(path).name], "file_sha256": {Path(path).name: sha(Path(path))},
            "column_used": f"{EIA_COLUMN} (lb/kWh × {G_PER_LB} → g/kWh; hour-end −1 h)",
            "coverage": cov, "peak_to_trough": ptt, "uk_peak_to_trough": UK_PEAK_TO_TROUGH,
            "criteria": crit, "qualifies": all(crit.values()), "_hourly": hourly, "_profile": prof}


def _em_files(zone_id: str) -> list[Path]:
    return sorted(p for p in EM_DIR.glob("*.csv") if zone_id.upper() in p.name.upper())


def build_grid2_profile(zone: str, zone_id: str) -> dict:
    files = _em_files(zone_id)
    if not files:
        return {"zone": zone, "status": "no files", "looked_in": str(EM_DIR)}
    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    tcol = next(c for c in df.columns if "datetime" in c.lower() and "utc" in c.lower())
    ccol = next(c for c in df.columns if "carbon intensity" in c.lower() and "direct" in c.lower())
    s = pd.Series(pd.to_numeric(df[ccol], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df[tcol], utc=True)).sort_index()
    s = s[~s.index.duplicated(keep="first")]
    full = pd.date_range(fc.SPAN_START, fc.SPAN_END, freq="h", inclusive="left", tz="UTC")
    hourly = pd.DataFrame({"gco2_per_kwh": s.reindex(full)})
    hourly.index.name = "timestamp_utc"
    cov = fc.coverage_per_year(hourly)
    prof = fc.hour_of_week_profile(hourly)
    ptt = float(prof["mean"].max() / prof["mean"].min()) if prof["mean"].notna().all() else None
    crit = {"a_files_present": True,
            "b_coverage_ge_95": all(v["coverage_pct"] is not None and v["coverage_pct"] >= 95
                                    for v in cov.values()),
            "c_peak_to_trough_gt_uk": bool(ptt is not None and ptt > UK_PEAK_TO_TROUGH)}
    return {"zone": zone, "zone_id": zone_id, "files": [f.name for f in files],
            "file_sha256": {f.name: sha(f) for f in files}, "column_used": ccol,
            "coverage": cov, "peak_to_trough": ptt, "uk_peak_to_trough": UK_PEAK_TO_TROUGH,
            "criteria": crit, "qualifies": all(crit.values()), "_hourly": hourly, "_profile": prof}


def sweep_f(ctx: Ctx) -> dict:
    # DL-031: CAISO from EIA-930. Germany would need a further DL entry (DL-031 §6).
    r = build_eia_profile("CAISO")
    tried = [{k: v for k, v in r.items() if not k.startswith("_")}]
    chosen = r if r.get("qualifies") else None
    if chosen is None:
        ec = OUT / "energy_charts_endpoints.txt"
        tried.append({"zone": "Germany", "status": "no qualifying account-free source",
                      "criteria": {"a_free_public_source": False},
                      "evidence": ("Electricity Maps requires an account (declined, DL-032); "
                                   "Energy-Charts API has no carbon-intensity endpoint — "
                                   f"{ec.name} sha256 {sha(ec) if ec.exists() else 'missing'}")})
        return {"status": "not run — no qualifying data (DL-027 §2, DL-032)", "tried": tried,
                "by_product": {"caiso_peak_to_trough": r.get("peak_to_trough"),
                               "uk_peak_to_trough": UK_PEAK_TO_TROUGH,
                               "reading": "descriptive only (DL-032): CAISO's consumed-intensity "
                                          "hour-of-week profile is not more variable than the UK's"}}
    GRID2_DIR.mkdir(parents=True, exist_ok=True)
    prof_path = GRID2_DIR / f"hour_of_week_profile_{chosen['zone_id']}.csv"
    chosen["_profile"].to_csv(prof_path)
    chosen["_hourly"].to_csv(GRID2_DIR / f"hourly_{chosen['zone_id']}_2024_2025.csv")
    (GRID2_DIR / "PROVENANCE.md").write_text(
        f"# PROVENANCE — second grid profile (P3-T4 S-f, DL-027 §2, DL-030, DL-031)\n\n"
        f"- Zone: **{chosen['zone']}** (`{chosen['zone_id']}`). Source: U.S. Energy Information "
        f"Administration, *Hourly Electric Grid Monitor* (Form EIA-930), per-BA workbook "
        f"{chosen['url']}, files {chosen['files']} (sha256 {chosen['file_sha256']}), read from "
        f"`Dataset/eia930/`.\n"
        f"- Terms: public U.S. government data, no account or key; EIA states the data are "
        f"preliminary and provided \"as-is\" (workbook notes sheet).\n"
        f"- Column: `{chosen['column_used']}`.\n"
        f"- Built by `{COMMAND} --sweep f` with the P0-T3 functions (UTC hour-of-week, nan-aware "
        f"168-slot mean, gaps left NaN). Coverage {chosen['coverage']}; peak-to-trough "
        f"{chosen['peak_to_trough']:.4f} vs UK {UK_PEAK_TO_TROUGH:.4f}.\n", encoding="utf-8")
    profile = carbon.load_hour_of_week_profile(prof_path)
    ctx.prove_trace()
    parts, info = replay(ctx, ctx.trace, ctx.settings, ctx.spec, profile, prof_path,
                         {"sweep": "S-f", "zone": chosen["zone_id"]})
    m = ctx.matrices(parts_dir=parts[0].parent, wanted=v4_wanted() | {
        s.setting_id for s in ctx.settings if s.strategy in fa.FORMS})
    mask = np.ones(len(m.ids), dtype=bool)
    summ = info["summary"].set_index("setting_id")
    meta = {k: v for k, v in chosen.items() if not k.startswith("_")}
    return {"status": "run", "tried": tried, "zone": meta, "checks": info["checks"],
            "profile_path": str(prof_path.relative_to(ROOT)).replace("\\", "/"),
            "greenest": prof_min(profile), "dirtiest": prof_max(profile),
            "headline": summ.loc[list(headline_ids(W_FROZEN).values())].reset_index().to_dict("records"),
            **v23(m, mask, "S-f"), "V4": v4_verdict(v4(m, mask))}


def prof_min(p: pd.DataFrame) -> dict:
    r = p.loc[p["mean"].idxmin()]
    return {"dow": int(r["dow"]), "hour": int(r["hour"]), "gco2_per_kwh": float(r["mean"])}


def prof_max(p: pd.DataFrame) -> dict:
    r = p.loc[p["mean"].idxmax()]
    return {"dow": int(r["dow"]), "hour": int(r["hour"]), "gco2_per_kwh": float(r["mean"])}


SWEEPS = {"baseline": sweep_baseline, "a": sweep_a, "b": sweep_b, "c": sweep_c, "d": sweep_d,
          "e": sweep_e, "f": sweep_f, "g": sweep_g, "h": sweep_h, "herding": sweep_herding}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", choices=tuple(SWEEPS))
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if args.summary:
        import sensitivity_report
        sensitivity_report.write(OUT, P3, FIG)
        return 0
    if args.sweep is None:
        ap.error("--sweep or --summary is required")
    if args.sweep != "baseline" and not (OUT / "baseline.json").exists():
        raise SystemExit("run --sweep baseline first: V4 is judged against it")
    t0 = time.time()
    ctx = Ctx()
    log(f"sweep {args.sweep} …")
    res = SWEEPS[args.sweep](ctx)
    res.update({"sweep": args.sweep, "command": f"{COMMAND} --sweep {args.sweep}",
                "run_date": time.strftime("%Y-%m-%d"), "seed": config.RANDOM_SEED,
                "n_resamples": N_RESAMPLES, "spec_sha256": ctx.spec_sha,
                "decision_log": ["DL-027", "DL-029", "DL-030"],
                "runtime_s": round(time.time() - t0, 1)})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.sweep}.json").write_text(json.dumps(res, indent=2, default=str) + "\n",
                                            encoding="utf-8")
    log(f"wrote results/p3/sensitivity/{args.sweep}.json ({res['runtime_s']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

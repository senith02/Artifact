"""P3-T3 — decision-level incremental value: ④a / ④b / ⑤ frontiers at matched points (DL-029).

Reads the P3-T2 test-replay part files (nothing re-replayed except the §A1.10
oracle arm), rebuilds each strategy's swept frontier in the (carbon saved, TTFF
p95) plane, compares ⑤ with ④a and with ④b at matched points, integrates the
area between frontiers, and applies §A1.7's decision-level floors with their
×0.5/×2 sweep. Every quantity carries a §9 paired-bootstrap CI (B = 1000, seed
42) in which each resample rebuilds the frontiers themselves.

Nothing is fitted. The frozen `policy_spec.yaml` is loaded with
``require_fitted=True`` and its hash asserted, as in P3-T2.

Run from ``code/``:  PYTHONPATH=. python scripts/frontier_analysis.py
"""

from __future__ import annotations

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

import run_test_replay as rt                                              # noqa: E402
from replay import frontier as fr                                        # noqa: E402
from replay import simulator as sim                                      # noqa: E402
from replay import validate_invariants as vi                              # noqa: E402
from scheduler_core import accounting, carbon, config                     # noqa: E402

ROOT = CODE_ROOT.parent
P3 = ROOT / "results" / "p3"
FIG = P3 / "figures"
COMMAND = "PYTHONPATH=. python scripts/frontier_analysis.py"
N_RESAMPLES = 1000
FORMS = ("4a_duration_estimator", "4b_duration_prior", "5_se_informed_policy")
ORACLE = "4_oracle_duration"
ORACLE_LABEL = "oracle — unrealizable in deployment"
MULTIPLIERS = (0.5, 1.0, 2.0)
#: DL-029 §5 / §A1.9: ⑤ must meet the condition against both controls.
PAIRS = (("4a_duration_estimator", "5_se_informed_policy"),
         ("4b_duration_prior", "5_se_informed_policy"))
#: DL-029 §7: the oracle bound, compared by the same machinery (never a headline pair).
ORACLE_PAIRS = (("4b_duration_prior", ORACLE), ("5_se_informed_policy", ORACLE))


def log(msg: str) -> None:
    print(msg, flush=True)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Per-build matrices from part files
# --------------------------------------------------------------------------- #

class Matrices:
    """carbon (settings × builds, 0 where unaccountable) and TTFF (settings × failed builds)."""

    def __init__(self, reference: pd.DataFrame) -> None:
        self.ids = reference["tr_build_id"].astype(str).to_numpy()
        self.projects = reference["gh_project_name"].astype(str).to_numpy()
        self.accountable = reference["obs_duration_s__accounting_only"].notna().to_numpy()
        y = pd.to_numeric(reference["y_fail"]).to_numpy(dtype="int64")
        self.failed_pos = np.flatnonzero((y == 1) & self.accountable)
        self.names: list[str] = []
        self.params: list[tuple[float | None, float | None]] = []
        self._c: list[np.ndarray] = []
        self._t: list[np.ndarray] = []

    def add(self, name: str, params: tuple[float | None, float | None], rec: pd.DataFrame) -> None:
        if not np.array_equal(rec["tr_build_id"].astype(str).to_numpy(), self.ids):
            raise SystemExit(f"FATAL: {name} is not on the reference build trace")
        if (rec["action"] == "skip").any():
            raise SystemExit(f"FATAL: {name} skips builds; the frontier strategies never skip")
        c = pd.to_numeric(rec["carbon_g"], errors="coerce").to_numpy(dtype="float64")
        t = pd.to_numeric(rec["ttff_hours"], errors="coerce").to_numpy(dtype="float64")
        if not np.array_equal(np.isfinite(c), self.accountable):
            raise SystemExit(f"FATAL: {name}'s accountable set differs from the reference")
        tf = t[self.failed_pos]
        if not np.isfinite(tf).all():
            raise SystemExit(f"FATAL: {name} has a failed accountable build without TTFF")
        self.names.append(name)
        self.params.append(params)
        self._c.append(np.where(self.accountable, c, 0.0))
        self._t.append(tf)

    def finalise(self) -> None:
        self.C = np.vstack(self._c)
        self.T = np.vstack(self._t)
        del self._c, self._t
        self.index = {n: i for i, n in enumerate(self.names)}

    def points(self, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Carbon saved % vs ① and TTFF p95 for every setting, under build weights ``w``."""
        mean = (self.C @ w) / float(np.dot(self.accountable, w))
        base = mean[self.index["1_static"]]
        saving = -(mean - base) / base * 100.0
        rep = np.repeat(np.arange(len(self.failed_pos)), w[self.failed_pos].astype("int64"))
        ttff = np.percentile(self.T[:, rep], 95, axis=1)
        return saving, ttff


def load_matrices(parts_dir: Path, settings: list[sim.Setting],
                  wanted: set[str]) -> tuple[Matrices, dict[str, str]]:
    shas: dict[str, str] = {}
    mats: Matrices | None = None
    for n, s in enumerate(settings):
        if s.setting_id not in wanted:
            continue
        part = parts_dir / f"{n:04d}__{s.setting_id}.csv"
        done = part.with_suffix(".done").read_text(encoding="utf-8").strip()
        digest = sha(part)
        if digest != done:
            raise SystemExit(f"FATAL: {part.name} does not match its .done sha256")
        shas[s.setting_id] = digest
        rec = rt.read_part(part)
        if mats is None:
            mats = Matrices(rec)
        mats.add(s.setting_id, (s.d_threshold_seconds, s.w_max_hours), rec)
        log(f"  loaded {s.setting_id}")
    assert mats is not None
    return mats, shas


# --------------------------------------------------------------------------- #
# The §A1.10 oracle arm
# --------------------------------------------------------------------------- #

def load_tracked_trace() -> pd.DataFrame:
    text_cols = {c: str for c in ("tr_build_id", "gh_project_name", "gh_is_pr", "git_branch",
                                  "arrival_utc", "d_hat_4a_fallback", "d_hat_4b_fallback")}
    # round_trip: pandas' default float parser can be one ulp off, which flips decisions
    # sitting exactly at a d_threshold (caught by the byte-identity probe in main()).
    return pd.read_csv(P3 / "test_trace.csv.gz", dtype=text_cols, keep_default_na=False,
                       na_values=[""], float_precision="round_trip")


def oracle_trace(trace: pd.DataFrame) -> pd.DataFrame:
    """d̂ := observed duration (§A1.2 role 3); unaccountable builds keep their ④b estimate."""
    out = trace.copy()
    obs = pd.to_numeric(out["obs_duration_s"], errors="coerce")
    ok = sim.accountable_mask(out)
    out["d_hat_4b_seconds"] = np.where(ok, obs, out["d_hat_4b_seconds"])
    out["d_hat_4b_fallback"] = np.where(ok, "oracle_observed", out["d_hat_4b_fallback"])
    return out


# --------------------------------------------------------------------------- #
# Point estimates + bootstrap for one population (all builds, or one band)
# --------------------------------------------------------------------------- #

def frontiers(m: Matrices, saving: np.ndarray, ttff: np.ndarray,
              strategies: tuple[str, ...]) -> dict[str, fr.Frontier]:
    out = {}
    for strat in strategies:
        idx = [m.index[n] for n in m.names if n.startswith(strat + "__")]
        out[strat] = fr.pareto_frontier(saving[idx], ttff[idx])
    return out


def analyse(m: Matrices, mask: np.ndarray, *, n_resamples: int, label: str,
            strategies: tuple[str, ...] = FORMS + (ORACLE,),
            pairs: tuple[tuple[str, str], ...] = PAIRS + ORACLE_PAIRS) -> dict[str, Any]:
    """DL-029 §3–§8 for one population. Defaults reproduce P3-T3 exactly; P3-T4 passes
    other strategy sets (DL-030) through the same machinery."""
    w0 = mask.astype("float64")
    s0, t0 = m.points(w0)
    f0 = frontiers(m, s0, t0, strategies)
    grids = {f"{r}|{t}": {"carbon": fr.matched_grid(f0[r].saving_range, f0[t].saving_range),
                          "ttff": fr.matched_grid(f0[r].ttff_range, f0[t].ttff_range)}
             for r, t in pairs}
    point = {k: {**fr.differences(f0[k.split("|")[0]], f0[k.split("|")[1]], g["carbon"], g["ttff"]),
                 "area": fr.area_between(f0[k.split("|")[0]], f0[k.split("|")[1]])}
             for k, g in grids.items()}

    rng = np.random.default_rng(config.RANDOM_SEED)
    n = len(mask)
    draws: dict[str, dict[str, list]] = {k: {"d_ttff": [], "d_saving": [], "area": []}
                                         for k in grids}
    for b in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        w = np.bincount(idx, minlength=n).astype("float64") * w0
        s, t = m.points(w)
        f = frontiers(m, s, t, strategies)
        for k, g in grids.items():
            r_, t_ = k.split("|")
            d = fr.differences(f[r_], f[t_], g["carbon"], g["ttff"])
            draws[k]["d_ttff"].append(d["d_ttff"])
            draws[k]["d_saving"].append(d["d_saving"])
            a = fr.area_between(f[r_], f[t_])
            draws[k]["area"].append(np.nan if a is None else a)
        if (b + 1) % 200 == 0:
            log(f"    [{label}] resample {b + 1}/{n_resamples}")

    out: dict[str, Any] = {"n_builds": int(mask.sum()), "n_projects": int(len(set(m.projects[mask]))),
                           "frontiers": {s: {"saving": f0[s].saving.tolist(),
                                             "ttff_p95_h": f0[s].ttff.tolist()} for s in strategies},
                           "points": {name: {"saving_pct": float(s0[i]), "ttff_p95_h": float(t0[i])}
                                      for i, name in enumerate(m.names)},
                           "pairs": {}}
    for k, g in grids.items():
        r_, t_ = k.split("|")
        p = point[k]
        rec: dict[str, Any] = {"reference": r_, "treatment": t_}
        for axis, dkey, rkey, floor in (("carbon", "d_ttff", "rel_d_ttff", fr.TTFF_FLOOR),
                                        ("ttff", "d_saving", "rel_d_saving", fr.CARBON_FLOOR)):
            D = np.vstack(draws[k][dkey]) if len(g[axis]) else np.empty((n_resamples, 0))
            defined = np.isfinite(D)
            und = 1.0 - defined.mean(axis=0) if D.size else np.empty(0)
            lo = np.array([np.quantile(D[defined[:, j], j], 0.025) if defined[:, j].any() else np.nan
                           for j in range(D.shape[1])])
            hi = np.array([np.quantile(D[defined[:, j], j], 0.975) if defined[:, j].any() else np.nan
                           for j in range(D.shape[1])])
            counts = {f"x{mult:g}": fr.count_points(p[rkey], lo, und, floor * mult).tolist()
                      for mult in MULTIPLIERS}
            rec[f"matched_at_{axis}"] = {
                "grid": g[axis].tolist(), "floor": floor,
                "point_abs": p[dkey].tolist(), "point_rel": p[rkey].tolist(),
                "ci_lo": lo.tolist(), "ci_hi": hi.tolist(), "undefined_share": und.tolist(),
                "counts": counts,
                "ref_value": (p["ttff_ref"] if axis == "carbon" else p["saving_ref"]).tolist(),
                "trt_value": (p["ttff_trt"] if axis == "carbon" else p["saving_trt"]).tolist(),
            }
        A = np.asarray(draws[k]["area"], dtype="float64")
        ok = np.isfinite(A)
        rec["area"] = {"point": p["area"],
                       "ci_lo": float(np.quantile(A[ok], 0.025)) if ok.any() else None,
                       "ci_hi": float(np.quantile(A[ok], 0.975)) if ok.any() else None,
                       "n_undefined_resamples": int((~ok).sum()),
                       "units": "percentage points of carbon saved × hours of TTFF p95; "
                                "positive favours the treatment"}
        rec["condition"] = {
            f"x{mult:g}": fr.decision_condition(np.array(rec["matched_at_carbon"]["counts"][f"x{mult:g}"]),
                                                np.array(rec["matched_at_ttff"]["counts"][f"x{mult:g}"]))
            for mult in MULTIPLIERS}
        out["pairs"][k] = rec
    if all(f"{r}|{t}" in out["pairs"] for r, t in PAIRS):
        out["verdict_se_adds_value"] = {
            f"x{mult:g}": all(out["pairs"][f"{r}|{t}"]["condition"][f"x{mult:g}"] for r, t in PAIRS)
            for mult in MULTIPLIERS}
    return out


# --------------------------------------------------------------------------- #
# Figures (dataviz: validated slots blue/orange/aqua; direct labels + legend)
# --------------------------------------------------------------------------- #

INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
SERIES = {"4b_duration_prior": "#2a78d6", "4a_duration_estimator": "#eb6834", ORACLE: "#1baf7a"}
NAMES = {"4b_duration_prior": "④b = ⑤ (frozen policy)", "4a_duration_estimator": "④a estimator",
         ORACLE: "oracle duration (unrealizable)"}


def _style(ax, title: str) -> None:
    ax.set_facecolor("#fcfcfb")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(color=GRID, lw=1.0)
    ax.set_axisbelow(True)
    ax.set_title(title, fontsize=9.5, color=INK, loc="left")
    ax.set_xlabel("carbon saved vs ① static (%)", fontsize=8.5, color=INK2)
    ax.set_ylabel("TTFF p95, failed builds (h)", fontsize=8.5, color=INK2)


def _draw(ax, res: dict, frozen: tuple[float, float] | None, *, labels: bool) -> None:
    for strat in ("4a_duration_estimator", ORACLE, "4b_duration_prior"):
        pts = [v for k, v in res["points"].items() if k.startswith(strat + "__")]
        f = res["frontiers"][strat]
        col = SERIES[strat]
        ax.scatter([p["saving_pct"] for p in pts], [p["ttff_p95_h"] for p in pts], s=10,
                   color=col, alpha=0.25, linewidths=0, zorder=2)
        ax.plot(f["saving"], f["ttff_p95_h"], color=col, lw=2, solid_capstyle="round",
                ls=(0, (4, 2)) if strat == ORACLE else "-", zorder=3, label=NAMES[strat])
        if labels:
            ax.annotate(NAMES[strat], (f["saving"][-1], f["ttff_p95_h"][-1]), xytext=(4, 0),
                        textcoords="offset points", fontsize=7.5, color=INK2, va="center")
    if frozen is not None:
        ax.scatter([frozen[0]], [frozen[1]], s=64, color="#2a78d6", edgecolors="#fcfcfb",
                   linewidths=2, zorder=4)
        ax.annotate("frozen point d480/w24", frozen, xytext=(-6, 10), textcoords="offset points",
                    fontsize=7.5, color=INK2, ha="right")


def write_figures(result: dict) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    frozen_id = "5_se_informed_policy__d480__w24"
    allp = result["populations"]["all"]
    fz = (allp["points"][frozen_id]["saving_pct"], allp["points"][frozen_id]["ttff_p95_h"])
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=160)
    fig.patch.set_facecolor("#fcfcfb")
    # All three frontiers end at the same point, so end-labels would collide; the legend
    # (plus the report's tables) carries identity.
    _draw(ax, allp, fz, labels=False)
    _style(ax, "Duration-only frontiers on the test trace (⑤ ≡ ④b under the frozen spec)")
    ax.legend(fontsize=7.5, frameon=False, loc="upper left", labelcolor=INK2)
    fig.tight_layout()
    p1 = FIG / "frontiers.png"
    fig.savefig(p1, facecolor="#fcfcfb")
    plt.close(fig)

    bands = [b for b in ("low", "mid", "high") if b in result["populations"]]
    fig, axes = plt.subplots(1, len(bands), figsize=(10.5, 3.6), dpi=160, sharey=False)
    fig.patch.set_facecolor("#fcfcfb")
    for ax, b in zip(np.atleast_1d(axes), bands):
        res = result["populations"][b]
        rng_ = result["bands"]["edges"]
        _draw(ax, res, None, labels=False)
        _style(ax, f"{b} failure-rate band · {res['n_projects']} projects")
    np.atleast_1d(axes)[0].legend(fontsize=7, frameon=False, loc="upper left", labelcolor=INK2)
    fig.tight_layout()
    p2 = FIG / "frontiers_by_band.png"
    fig.savefig(p2, facecolor="#fcfcfb")
    plt.close(fig)
    return [str(p.relative_to(ROOT)).replace("\\", "/") for p in (p1, p2)]


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if "--figures-only" in sys.argv[1:]:
        result = json.loads((P3 / "incremental_value_decision.json").read_text(encoding="utf-8"))
        log(f"redrew {write_figures(result)} from incremental_value_decision.json (no recomputation)")
        return 0
    t0 = time.time()
    grid = sim.load_sweep_grid()
    spec, spec_sha = rt.load_frozen_spec(grid)
    energy = accounting.load_energy_config()
    profile = carbon.load_hour_of_week_profile()
    p3t2 = json.loads((P3 / "strategy_results.json").read_text(encoding="utf-8"))
    parts_dir = rt.DEFAULT_PARTS / p3t2["run_fingerprint"][:16]
    settings = sim.enumerate_settings(grid)
    wanted = {"1_static"} | {s.setting_id for s in settings if s.strategy in FORMS}

    log(f"loading {len(wanted)} P3-T2 part files from {parts_dir.name} …")
    m, part_shas = load_matrices(parts_dir, settings, wanted)

    # ---- §A1.10 oracle arm: prove the tracked trace faithful, then replay ----
    trace = load_tracked_trace()
    sim.validate_trace(trace)
    probe = next(s for s in settings if s.setting_id == "4b_duration_prior__d480__w24")
    probe_n = settings.index(probe)
    probe_part = parts_dir / f"{probe_n:04d}__{probe.setting_id}.csv"
    rep = sim.replay_setting(trace, probe, base_spec=spec, profile=profile,
                             p_avg_w=energy.p_avg_w, primary_form="4b")
    faithful = sim.records_to_csv_bytes(rep, header=False) == probe_part.read_bytes()
    log(f"tracked trace reproduces P3-T2 part {probe.setting_id}: {faithful}")
    if not faithful:
        raise SystemExit("FATAL: test_trace.csv.gz does not reproduce the P3-T2 replay")
    otrace = oracle_trace(trace)
    osettings = [s for s in settings if s.strategy == "4b_duration_prior"]
    ofp = sim.run_fingerprint(trace=otrace, grid=grid, base_spec=spec, p_avg_w=energy.p_avg_w,
                              primary_form="4b", profile_path=carbon.DEFAULT_PROFILE_PATH,
                              extra={"arm": ORACLE, "label": ORACLE_LABEL})
    log(f"replaying the oracle arm ({len(osettings)} settings, fingerprint {ofp[:16]}) …")
    oparts = sim.run_sweep(otrace, osettings, base_spec=spec, profile=profile,
                           p_avg_w=energy.p_avg_w, primary_form="4b", parts_dir=rt.DEFAULT_PARTS,
                           fingerprint=ofp, resume=True, progress=log)
    oaudit = {"rows": 0, "deferred": 0, "violations": 0}
    for part, s in zip(oparts, osettings):
        rec = rt.read_part(part)
        a = vi.audit_frame(rec, variant=spec.stage1_variant, path=str(part))
        for k in oaudit:
            oaudit[k] += getattr(a, k)
        m.add(f"{ORACLE}__d{s.d_threshold_seconds:g}__w{s.w_max_hours:g}",
              (s.d_threshold_seconds, s.w_max_hours), rec)
    m.finalise()

    # ---- recomputed points must equal P3-T2's summary (DL-029 §1) ----
    # DL-029 §1 (as amended): the underlying quantities relative, carbon saved absolute.
    summ = pd.read_csv(P3 / "strategy_results.csv",
                       float_precision="round_trip").set_index("setting_id")
    ones = np.ones(len(m.ids))
    s_full, t_full = m.points(ones)
    c_full = (m.C @ ones) / float(np.dot(m.accountable, ones)) * 1000.0
    worst = {"carbon_per_1000_rel": 0.0, "ttff_p95_rel": 0.0, "saving_abs_pp": 0.0}
    for i, name in enumerate(m.names):
        if name.startswith(ORACLE):
            continue
        ec = float(summ.loc[name, "carbon_per_1000_builds_g"])
        et = float(summ.loc[name, "ttff_p95_h_failed"])
        es = -float(summ.loc[name, "carbon_pct_vs_static"])
        worst["carbon_per_1000_rel"] = max(worst["carbon_per_1000_rel"], abs(c_full[i] - ec) / ec)
        worst["ttff_p95_rel"] = max(worst["ttff_p95_rel"], abs(t_full[i] - et) / et)
        worst["saving_abs_pp"] = max(worst["saving_abs_pp"], abs(s_full[i] - es))
    points_ok = (worst["carbon_per_1000_rel"] <= 1e-12 and worst["ttff_p95_rel"] <= 1e-12
                 and worst["saving_abs_pp"] <= 1e-9)
    log(f"recomputed points vs strategy_results.csv: {worst}")
    if not points_ok:
        raise SystemExit("FATAL: recomputed frontier points differ from P3-T2's summary")

    # ---- failure-rate bands (DL-029 §9) ----
    proj = pd.DataFrame({"p": m.projects,
                         "y": np.isin(np.arange(len(m.ids)), m.failed_pos)})
    y_all = pd.read_csv(P3 / "test_trace.csv.gz", usecols=["tr_build_id", "y_fail"],
                        dtype={"tr_build_id": str}).set_index("tr_build_id").loc[m.ids, "y_fail"]
    proj["y"] = y_all.to_numpy()
    rate = proj.groupby("p")["y"].mean()
    q1, q2 = (float(np.quantile(rate.to_numpy(), q)) for q in (1 / 3, 2 / 3))
    band_of = rate.map(lambda r: "low" if r <= q1 else ("mid" if r <= q2 else "high"))
    build_band = pd.Series(m.projects).map(band_of).to_numpy()

    populations: dict[str, Any] = {}
    log(f"\nbootstrap, all test builds (B = {N_RESAMPLES}) …")
    populations["all"] = analyse(m, np.ones(len(m.ids), dtype=bool), n_resamples=N_RESAMPLES,
                                 label="all")
    for b in ("low", "mid", "high"):
        log(f"bootstrap, {b} band …")
        populations[b] = analyse(m, build_band == b, n_resamples=N_RESAMPLES, label=b)

    result = {
        "task": "P3-T3", "decision_log": ["DL-013", "DL-023", "DL-028", "DL-029"],
        "command": COMMAND, "run_date": time.strftime("%Y-%m-%d"), "seed": config.RANDOM_SEED,
        "n_resamples": N_RESAMPLES,
        "label": "test split — decision-level incremental value (P3-T3)",
        "spec_sha256": spec_sha, "p3_t2_run_fingerprint": p3t2["run_fingerprint"],
        "part_sha256": part_shas,
        "checks": {"points_equal_strategy_results": {**worst, "passed": points_ok,
                                                      "rule": "DL-029 §1 as amended"},
                   "tracked_trace_reproduces_p3_t2": faithful,
                   "oracle_gate_safety": {**oaudit, "passed": oaudit["violations"] == 0}},
        "oracle": {"label": ORACLE_LABEL, "run_fingerprint": ofp,
                   "rule": "④'s duration-only rule with d̂ := observed tr_duration (§A1.2 role 3); "
                           "55 unaccountable builds keep their ④b estimate (DL-029 §7)"},
        "bands": {"edges": {"q1": q1, "q2": q2}, "rule": "terciles of per-project test failure rate "
                  "over the 170 test projects; low ≤ q1 < mid ≤ q2 < high (DL-029 §9)",
                  "n_projects": band_of.value_counts().to_dict()},
        "a1_9_variance_decomposition": "not applicable — §A1.9 decomposes admitted families; the "
                                       "frozen spec admits none (DL-029 §9)",
        "populations": populations,
    }
    result["figures"] = write_figures(result)
    result["runtime_s"] = round(time.time() - t0, 1)
    (P3 / "incremental_value_decision.json").write_text(
        json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    write_report(result)
    log(f"\nwrote results/p3/incremental_value_decision.* ({result['runtime_s']:.0f}s)")
    return 0


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

LBL = {"4a_duration_estimator": "④a", "4b_duration_prior": "④b", "5_se_informed_policy": "⑤",
       ORACLE: "oracle"}


def _n(v: Any, nd: int = 3, signed: bool = False) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:+,.{nd}f}" if signed else f"{v:,.{nd}f}"


def _pair_block(A, rec: dict, *, oracle: bool = False) -> None:
    r, t = LBL[rec["reference"]], LBL[rec["treatment"]]
    area = rec["area"]
    A(f"**{t} vs {r}** — area between frontiers {_n(area['point'], 4, True)} "
      f"[{_n(area['ci_lo'], 4, True)}, {_n(area['ci_hi'], 4, True)}] (pp × h; positive favours "
      f"{t}; undefined resamples {area['n_undefined_resamples']}).\n")
    for axis, title, unit in (("carbon", f"at matched carbon saved — Δ TTFF p95 = {r} − {t} (h)", "%"),
                              ("ttff", f"at matched TTFF p95 — Δ carbon saved = {t} − {r} (pp)", "h")):
        mm = rec[f"matched_at_{axis}"]
        if not mm["grid"]:
            A(f"*{title}: no overlap on this axis — no matched points.*\n")
            continue
        A(f"| matched {'saving %' if axis == 'carbon' else 'TTFF p95 h'} | {r} | {t} | Δ [95% CI] | "
          f"relative Δ | counts ×0.5 / ×1 / ×2 |")
        A("| --: | --: | --: | :-- | --: | :-: |")
        for j, g in enumerate(mm["grid"]):
            c = [mm["counts"][f"x{x:g}"][j] for x in MULTIPLIERS]
            A(f"| {g:.4f} | {_n(mm['ref_value'][j], 4)} | {_n(mm['trt_value'][j], 4)} | "
              f"{_n(mm['point_abs'][j], 4, True)} [{_n(mm['ci_lo'][j], 4, True)}, "
              f"{_n(mm['ci_hi'][j], 4, True)}] | {_n(100 * mm['point_rel'][j] if mm['point_rel'][j] is not None and np.isfinite(mm['point_rel'][j]) else None, 2, True)}% | "
              f"{' / '.join('✓' if x else '·' for x in c)} |")
        A(f"\n*{title}; floor {100 * mm['floor']:g}% relative (×1).*\n")
    cond = rec["condition"]
    A(f"§A1.7 decision condition (≥ {fr.MIN_POINTS} counting points on one axis): "
      f"×0.5 **{cond['x0.5']}** · ×1 **{cond['x1']}** · ×2 **{cond['x2']}**"
      + (" — *oracle bound, not a verdict*" if oracle else "") + "\n")


def write_report(res: dict) -> None:
    allp = res["populations"]["all"]
    L: list[str] = []
    A = L.append
    A("# P3-T3 — decision-level incremental value: ④ vs ⑤ frontiers (the headline RQ2 test)\n")
    A(f"> Generated by `{res['command']}` on {res['run_date']} ({res['runtime_s']:.0f} s). Every number "
      "below comes from that run (R1). **Test split.** Inputs are the P3-T2 replay part files (run "
      f"fingerprint `{res['p3_t2_run_fingerprint'][:16]}…`, each sha256-verified); nothing was "
      "refitted. Rules: DL-029, written before any frontier number existed. Paired bootstrap, B = "
      f"{res['n_resamples']}, seed {res['seed']}; every resample rebuilds the frontiers.\n")
    A("> **Read this first.** Under the frozen `policy_spec.yaml` (duration-only), ⑤ ≡ ④b at every "
      "grid point by construction (DL-023 §1, DL-028 §1). ⑤ − ④b is therefore exactly 0 everywhere, "
      "and ⑤ cannot meet the condition against ④b. ⑤ vs ④a compares two **duration** controls and "
      "says nothing about SE characteristics. F1's decision-level value was **not tested** (DL-028 "
      "§1).\n")
    c = res["checks"]
    A("## 1. Checks\n")
    pc = c["points_equal_strategy_results"]
    A(f"- Recomputed per-setting points equal `strategy_results.csv` (DL-029 §1): "
      f"{'PASS' if pc['passed'] else 'FAIL'} — max relative difference, carbon per 1,000 builds "
      f"{pc['carbon_per_1000_rel']:.1e}, TTFF p95 {pc['ttff_p95_rel']:.1e}; carbon saved "
      f"{pc['saving_abs_pp']:.1e} pp absolute.")
    A(f"- Tracked `test_trace.csv.gz` reproduces a P3-T2 part byte for byte: "
      f"{'PASS' if c['tracked_trace_reproduces_p3_t2'] else 'FAIL'}.")
    o = c["oracle_gate_safety"]
    A(f"- Oracle arm gate safety: **{o['violations']}** violations / {o['deferred']:,} deferrals / "
      f"{o['rows']:,} rows.\n")
    A("## 2. Frontiers (all test builds)\n")
    A(f"![frontiers]({res['figures'][0].replace('results/p3/', '')})\n")
    A("| strategy | frontier points (saving %, TTFF p95 h) |")
    A("| :-- | :-- |")
    for s in FORMS + (ORACLE,):
        f = allp["frontiers"][s]
        pts = ", ".join(f"({a:.3f}, {b:.2f})" for a, b in zip(f["saving"], f["ttff_p95_h"]))
        A(f"| {LBL[s]}{' (' + ORACLE_LABEL + ')' if s == ORACLE else ''} | {pts} |")
    A("\n## 3. The headline comparison — ⑤ against both duration controls\n")
    for r, t in PAIRS:
        _pair_block(A, allp["pairs"][f"{r}|{t}"])
    v = allp["verdict_se_adds_value"]
    A(f"**§A1.9 rule (⑤ must beat both ④a and ④b):** ×0.5 **{v['x0.5']}** · ×1 **{v['x1']}** · "
      f"×2 **{v['x2']}**.\n")
    A("## 4. Single-point carbon at the frozen operating point (descriptive only, S3)\n")
    pf = allp["points"]
    A("| setting | carbon saved % | TTFF p95 h |")
    A("| :-- | --: | --: |")
    for sid in ("4a_duration_estimator__d480__w24", "4b_duration_prior__d480__w24",
                "5_se_informed_policy__d480__w24"):
        A(f"| `{sid}` | {pf[sid]['saving_pct']:.4f} | {pf[sid]['ttff_p95_h']:.4f} |")
    A("\n> §A1.5: ④ is expected to lead a single-point carbon comparison by construction, because carbon "
      "is proportional to duration (§A1.13). This row is context, never a finding about SE "
      "characteristics.\n")
    A(f"## 5. §A1.10 oracle bound — *{ORACLE_LABEL}*\n")
    A(f"Rule: {res['oracle']['rule']}. It bounds how much of any frontier gap estimator error could "
      "explain. It is **not** a strategy anyone can deploy and is outside the headline.\n")
    for r, t in ORACLE_PAIRS:
        _pair_block(A, allp["pairs"][f"{r}|{t}"], oracle=True)
    A("## 6. Stratified by project failure-rate band (S4, §A1.9)\n")
    e = res["bands"]["edges"]
    A(f"Bands: {res['bands']['rule']}; q1 = {e['q1']:.4f}, q2 = {e['q2']:.4f}; projects per band "
      f"{res['bands']['n_projects']}.\n")
    A(f"![frontiers by band]({res['figures'][1].replace('results/p3/', '')})\n")
    A("| band | builds | projects | area ⑤ vs ④a [95% CI] | area ⑤ vs ④b | condition vs ④a (×1) | "
      "condition vs ④b (×1) |")
    A("| :-- | --: | --: | :-- | :-- | :-: | :-: |")
    for b in ("low", "mid", "high"):
        pb = res["populations"][b]
        a4a = pb["pairs"]["4a_duration_estimator|5_se_informed_policy"]
        a4b = pb["pairs"]["4b_duration_prior|5_se_informed_policy"]
        A(f"| {b} | {pb['n_builds']:,} | {pb['n_projects']} | {_n(a4a['area']['point'], 4, True)} "
          f"[{_n(a4a['area']['ci_lo'], 4, True)}, {_n(a4a['area']['ci_hi'], 4, True)}] | "
          f"{_n(a4b['area']['point'], 4, True)} | {a4a['condition']['x1']} | {a4b['condition']['x1']} |")
    A(f"\nBetween/within-project variance decomposition: {res['a1_9_variance_decomposition']}.\n")
    A("## 7. Provenance\n")
    A(f"- Command: `{res['command']}`; frozen spec sha256 `{res['spec_sha256'][:16]}…`.")
    A(f"- Oracle replay fingerprint `{res['oracle']['run_fingerprint'][:16]}…` (parts under "
      "`code/artifacts/replay_parts/`, gitignored).")
    A("- Machine-readable, incl. every matched point, CI and bootstrap setting: "
      "`incremental_value_decision.json`.\n")
    (P3 / "incremental_value_decision.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

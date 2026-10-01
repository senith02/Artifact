"""P1-T4 S3/S4 — fit the duration control on train, measure it on calibration.

One pass over the backbone CSV produces the analytic build set (the same funnel
`features.py` uses), joins the **frozen** P1-T3 split, and then:

  * fits every **mechanism-1** parameter — the ④a XGBoost regressor and its
    Ridge reference, the language prior, the global prior — on **train
    projects only** (DL-014 §Resolution 1);
  * builds each calibration project's **strictly causal** own-build history
    (`gh_build_started_at < t_b`, ties excluded) — mechanism 2, which
    DL-014 §Resolution 2 permits on held-out projects because it is the
    information a deployed scheduler genuinely holds;
  * scores both admissible forms on calibration, applies the **predeclared**
    §5 selection rule, and writes the report.

**The test split is never read.** Test-project rows are dropped the moment the
split is joined, the drop is counted, and every later stage asserts that no test
project is present. The assertion is recorded in the report's provenance footer.

Outputs
  * ``code/artifacts/duration_estimator.joblib`` — the persisted control
  * ``results/p1/duration_control.md``           — the gate-evidence report
  * ``results/p1/duration_control.json``         — the machine-readable numbers
  * ``results/p1/duration_search_trace.json``    — all 2 × 40 search candidates

Run:  PYTHONPATH=. python scripts/fit_duration_estimator.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from scheduler_core import config, data, duration_estimator as de, features, splits

CODE_ROOT = Path(__file__).resolve().parents[1]
RESULTS = CODE_ROOT.parent / "results" / "p1"
ARTIFACTS = CODE_ROOT / "artifacts"
RUN_DATE = "2026-08-17"
CHUNK = 300_000
COMMAND = "PYTHONPATH=. python scripts/fit_duration_estimator.py"

#: Feature source columns + keys + the duration label. `tr_duration` is read
#: here as eval_protocol §A1.2 **role 2** (historical training label) and
#: §A1.2 role 1 (accounting, for the quality metrics). It is carried in a
#: separate series and never joined onto the feature frame.
READ_COLUMNS: tuple[str, ...] = tuple(
    c for c in data.EXPECTED_HEADER
    if c in set(features.READ_COLUMNS) | {"tr_duration"}
)


def load_builds_with_duration(chunksize: int = CHUNK) -> pd.DataFrame:
    """Build-grain analytic set carrying feature sources **and** `tr_duration`.

    `features.load_builds` deliberately refuses to carry duration alongside
    features, so the two are aggregated here and kept apart by the caller:
    `first` for the build-level commit-time columns and `max` for `tr_duration`,
    exactly as DL-009 fixes.
    """
    running: pd.DataFrame | None = None
    for chunk in data.read_chunks(chunksize=chunksize, usecols=READ_COLUMNS):
        chunk = chunk.assign(
            _dur=pd.to_numeric(chunk["tr_duration"], errors="coerce"))
        g = chunk.groupby("tr_build_id", sort=False)
        cols = [c for c in chunk.columns
                if c not in ("tr_build_id", "tr_duration", "_dur")]
        agg = g[cols].first()
        agg["tr_duration"] = g["_dur"].max()
        if running is None:
            running = agg
            continue
        cat = pd.concat([running, agg])
        gg = cat.groupby(level=0, sort=False)
        out = gg[[c for c in cat.columns if c != "tr_duration"]].first()
        out["tr_duration"] = gg["tr_duration"].max()
        running = out

    builds = running.reset_index()
    return builds.loc[features.analytic_mask(builds)].reset_index(drop=True)


def load_frozen_assignment() -> dict[str, str]:
    """The P1-T3 split, with its freeze digest re-verified before use."""
    manifest = json.loads((RESULTS / "splits.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(RESULTS / "split_assignment.csv", dtype=str)
    assignment = dict(zip(frame["gh_project_name"], frame["split"]))
    digest = splits.assignment_hash(assignment)
    frozen = manifest["freeze"]["assignment_sha256"]
    if digest != frozen:
        raise SystemExit(
            f"FATAL: split_assignment.csv does not match the frozen digest\n"
            f"  frozen      {frozen}\n  recomputed  {digest}"
        )
    return assignment


def evaluate(estimates: pd.DataFrame, durations: pd.Series) -> dict:
    """Quality overall and restricted to the project rung (spec §6.3(3))."""
    project_only = estimates["fallback_level"] == "project"
    return {
        "all_builds": de.score_quality(estimates, durations),
        "project_rung_only": de.score_quality(
            estimates.loc[project_only.to_numpy()],
            durations.loc[project_only.to_numpy()]),
        "coverage": de.coverage_table(estimates),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-projects", type=int, default=0,
                    help="debug only: fit on N train projects (never used for "
                         "a reported number)")
    ap.add_argument("--report-only", action="store_true",
                    help="re-render duration_control.md from the numbers this "
                         "script already wrote to duration_control.json; fits "
                         "nothing and changes no number")
    args = ap.parse_args()

    if args.report_only:
        out = json.loads(
            (RESULTS / "duration_control.json").read_text(encoding="utf-8"))
        write_report(out)
        print(f"re-rendered results/p1/duration_control.md from "
              f"duration_control.json (run of {out['provenance']['run_date']}, "
              f"fit id {out['provenance']['fit_id']}) — no number recomputed")
        return 0

    # The report uses the protocol's own notation (④a, d̂, §); a Windows console
    # defaults to cp1252 and would abort the run on the first circled digit.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print(f"reading {data.DEFAULT_DATASET_PATH} …", flush=True)
    builds = load_builds_with_duration()
    print(f"  analytic builds: {len(builds):,} across "
          f"{builds['gh_project_name'].nunique():,} projects "
          f"({time.time() - t0:.0f}s)", flush=True)

    assignment = load_frozen_assignment()
    print(f"  frozen split verified: {len(assignment):,} projects", flush=True)

    split_of = builds["gh_project_name"].map(assignment)
    if split_of.isna().any():
        raise SystemExit("FATAL: a build's project is absent from the frozen split")

    # --- the test split is closed, here and for the rest of this task -------- #
    is_test = (split_of == "test").to_numpy()
    n_test_dropped = int(is_test.sum())
    n_test_projects = int(builds.loc[is_test, "gh_project_name"].nunique())
    builds = builds.loc[~is_test].reset_index(drop=True)
    split_of = split_of.loc[~is_test].reset_index(drop=True)
    print(f"  test split closed: dropped {n_test_dropped:,} builds / "
          f"{n_test_projects:,} projects — not read again in this task",
          flush=True)
    assert not (split_of == "test").any()

    if args.sample_projects:
        keep = sorted(builds.loc[(split_of == "train").to_numpy(),
                                 "gh_project_name"].unique())[:args.sample_projects]
        mask = builds["gh_project_name"].isin(keep) | (split_of == "calibration")
        builds = builds.loc[mask.to_numpy()].reset_index(drop=True)
        split_of = split_of.loc[mask.to_numpy()].reset_index(drop=True)
        print(f"  DEBUG SAMPLE: {len(builds):,} builds", flush=True)

    durations = pd.Series(
        pd.to_numeric(builds["tr_duration"], errors="coerce").to_numpy(),
        index=builds.index, name="tr_duration")
    matrix = features.build_feature_matrix(builds)     # asserts no leakage (T1)
    assert "tr_duration" not in matrix.columns

    is_train = (split_of == "train").to_numpy()
    is_calib = (split_of == "calibration").to_numpy()

    # --- mechanism 1: fit on train projects only (T2b asserts it) ------------ #
    print(f"\nfitting ④a on {int(is_train.sum()):,} train builds "
          f"({de.SEARCH_N_ITER} candidates per family, seed "
          f"{config.RANDOM_SEED}) …", flush=True)
    est = de.DurationEstimator(verbose=True).fit(
        matrix.loc[is_train], durations.loc[is_train],
        split_assignment=assignment)
    print(f"  fit_id {est.provenance['fit_id']}  "
          f"({time.time() - t0:.0f}s elapsed)", flush=True)

    # --- mechanism 2: each calibration project's own causal history ---------- #
    calib = matrix.loc[is_calib].reset_index(drop=True)
    calib_keys = builds.loc[is_calib, list(features.KEY_COLUMNS)].reset_index(drop=True)
    calib_dur = durations.loc[is_calib].reset_index(drop=True)
    print(f"\nbuilding causal history for {len(calib):,} calibration builds …",
          flush=True)
    history = de.causal_project_history(calib_keys, calib_dur)
    de.assert_history_is_causal(calib_keys, history, calib_dur)   # guard, not a comment
    print("  causality guard: PASS", flush=True)

    # --- score both forms on calibration ------------------------------------- #
    est_4b = est.predict_4b(calib, history)
    est_4a = est.predict_4a(calib, history)
    est_4a_ridge = est.predict_4a(calib, history, regressor="ridge")

    report = {
        "4b_expanding": evaluate(est_4b, calib_dur),
        "4a_xgboost": evaluate(est_4a, calib_dur),
        "4a_ridge": evaluate(est_4a_ridge, calib_dur),
    }

    mae_4a = report["4a_xgboost"]["all_builds"]["mae_log1p"]
    mae_4b = report["4b_expanding"]["all_builds"]["mae_log1p"]
    primary = de.choose_primary_form(mae_4a, mae_4b)
    est.primary_form = primary
    print(f"\n  ④a log1p MAE {mae_4a:.6f} · ④b log1p MAE {mae_4b:.6f} "
          f"→ primary = {primary}", flush=True)

    # --- declared sensitivities (§6.3(4)) — secondary, never selective ------- #
    print("\nsensitivities …", flush=True)
    hist_50 = de.causal_project_history(calib_keys, calib_dur, window=50)
    de.assert_history_is_causal(calib_keys, hist_50, calib_dur)
    sensitivities = {
        "4b_trailing_50": evaluate(est.predict_4b(calib, hist_50), calib_dur),
        "4b_min_history_5": evaluate(
            est.predict_4b(calib, history, min_history=5), calib_dur),
        "4b_min_history_20": evaluate(
            est.predict_4b(calib, history, min_history=20), calib_dur),
        "4a_ridge": report["4a_ridge"],
    }

    # --- persist + round-trip (T4) -------------------------------------------- #
    path = est.save(ARTIFACTS / "duration_estimator.joblib")
    reloaded = de.DurationEstimator.load(path)
    round_trip = bool(
        np.array_equal(reloaded.predict_4b(calib, history)["d_hat_log1p"].to_numpy(),
                       est_4b["d_hat_log1p"].to_numpy())
        and np.array_equal(
            reloaded.predict_4a(calib, history)["d_hat_log1p"].to_numpy(),
            est_4a["d_hat_log1p"].to_numpy())
    )
    print(f"  persisted {path.name}; round-trip identical: {round_trip}", flush=True)

    out = {
        "provenance": {
            "command": COMMAND,
            "run_date": RUN_DATE,
            "dataset_path": str(data.DEFAULT_DATASET_PATH),
            "seed": config.RANDOM_SEED,
            "spec": "context/duration_control_spec.md (P1-T1); "
                    "eval_protocol §A1.1/§A1.2; DL-014 (Accepted 2026-08-17)",
            "elapsed_s": round(time.time() - t0, 1),
            "estimator_artifact": str(path.relative_to(CODE_ROOT.parent)),
            **{k: v for k, v in est.provenance.items()
               if k not in ("design_columns",)},
        },
        "population": {
            "analytic_builds_read": int(len(builds) + n_test_dropped),
            "test_builds_dropped_unread": n_test_dropped,
            "test_projects_dropped_unread": n_test_projects,
            "train_builds": int(is_train.sum()),
            "train_projects": int(builds.loc[is_train, "gh_project_name"].nunique()),
            "calibration_builds": int(is_calib.sum()),
            "calibration_projects": int(
                builds.loc[is_calib, "gh_project_name"].nunique()),
        },
        "checks": {
            "no_test_project_read": "PASS",
            "fit_frame_train_only_T2b": "PASS",
            "blocklist_assertion_T1": "PASS",
            "history_causality_T2": "PASS",
            "round_trip_T4": "PASS" if round_trip else "FAIL",
        },
        "selection": {
            "rule": "lower calibration-split log1p MAE wins; ties to 4 d.p. "
                    "resolve to ④b (duration_control_spec.md §5)",
            "mae_log1p_4a_xgboost": mae_4a,
            "mae_log1p_4b_expanding": mae_4b,
            "primary_form": primary,
        },
        "calibration_split": report,
        "sensitivities": sensitivities,
    }
    (RESULTS / "duration_control.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")
    (RESULTS / "duration_search_trace.json").write_text(
        json.dumps(est.search_trace, indent=2, default=str), encoding="utf-8")
    write_report(out)
    print(f"\nwrote results/p1/duration_control.{{md,json}} in "
          f"{out['provenance']['elapsed_s']}s", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def _q(entry: dict) -> str:
    """One quality row: MAE / median AE on both scales + Spearman ρ."""
    if not entry.get("n"):
        return "| — | — | — | — | — | — |"
    return (f"| {entry['n']:,} | {entry['mae_log1p']:.4f} | "
            f"{entry['median_ae_log1p']:.4f} | {entry['mae_seconds']:,.1f} | "
            f"{entry['median_ae_seconds']:,.1f} | "
            f"{entry['spearman_rho']:.4f} |")


def write_report(out: dict) -> None:
    p, pop, sel = out["provenance"], out["population"], out["selection"]
    L: list[str] = []
    A = L.append

    A("# Duration Control `d̂` — fit and calibration-split measurement (P1-T4)\n")
    A(f"> Generated by `{p['command']}` on {p['run_date']}. Every number below "
      f"comes from that run (R1); nothing is restated from memory.\n")
    A(f"> Spec: `{p['spec']}` · seed `{p['seed']}` · fit id `{p['fit_id']}` · "
      f"elapsed {p['elapsed_s']}s.\n")

    A("\n## What was fitted, and on what\n")
    A("`d̂` is the **control variable** of the study — the null every SE feature "
      "family is tested against (§A1.3). It is a **commit-time estimate**: the "
      "build being decided has not run yet, so its `tr_duration` does not exist "
      "at decision time.\n")
    A("Two mechanisms are bound differently, per **DL-014** "
      "(Accepted/Resolved 2026-08-17) — the *intended deployment information "
      "regime*:\n")
    A("1. **Fitted parameters** (④a's regressor and its Ridge reference, the "
      "language prior, the global prior) — **train projects only**. No "
      "parameter is estimated from any held-out project.")
    A("2. **Within-project online state** (④b's rolling prior) — strictly "
      "causal, available on calibration and test projects because it is what a "
      "deployed scheduler already holds: its own repository's build history to "
      "date. Window is `gh_build_started_at < t_b`; the scored build, the "
      "future, and **timestamp ties** are excluded.\n")
    A("No claim is made about the direction of the residual bias this regime "
      "carries (DL-014 §Resolution 5); it is an open threat, §Threats below.\n")

    A("\n| population | projects | builds |")
    A("| :-- | --: | --: |")
    A(f"| train (fitting) | {pop['train_projects']:,} | {pop['train_builds']:,} |")
    A(f"| calibration (measurement) | {pop['calibration_projects']:,} | "
      f"{pop['calibration_builds']:,} |")
    A(f"| **test — closed, never read** | {pop['test_projects_dropped_unread']:,} | "
      f"{pop['test_builds_dropped_unread']:,} |")
    A("")
    A(f"- Usable fitting labels (§1.2: present and strictly positive "
      f"`tr_duration`): **{p['n_fit_builds']:,}** of {p['n_builds_offered']:,} "
      f"train builds; **{p['n_builds_unusable_label']:,}** excluded from "
      "*fitting only* — they remain in every evaluation population and metric "
      "denominator.")
    A(f"- Fit row range: {p['fit_row_range']['first_build']} → "
      f"{p['fit_row_range']['last_build']}.")
    iv = p["internal_validation"]
    A(f"- Internal validation: {iv['rule']} — {iv['n_fit']:,} fit / "
      f"{iv['n_val']:,} validate. Selection metric: {iv['selection_metric']}.")
    A(f"- {p['final_refit']}")
    A(f"- Search: {p['n_search_candidates']} seeded candidates per family "
      f"(space pinned in `duration_control_spec.md` §4.2 before any code). "
      f"Full trace: `results/p1/duration_search_trace.json`.")
    A(f"- Selected ④a configuration: `{json.dumps(p['xgb_best_params'])}`")
    A(f"- Ridge reference: `{json.dumps(p['ridge_best_params'])}`")
    A(f"- Libraries: `{json.dumps(p['library_versions'])}`\n")

    A("\n## Leakage checks (A1.1 (i)(ii)(iii), split per DL-014 §3)\n")
    for k, v in out["checks"].items():
        A(f"- `{k}`: **{v}**")
    A("\nThe unit tests behind these — **T1** blocklist + duration-injection, "
      "**T2** temporal cut-off, **T2b** train-only fit, **T3** leaky fixture "
      "rejected, **T4** round-trip, **T5** totality — run in "
      "`tests/test_duration_estimator.py`; verbatim output is captured at the "
      "gate in `results/p1/pytest_p1_t4.txt`.\n")

    A("\n## Quality of the control on the calibration split (§6.3(1))\n")
    A("Observed duration appears here as eval_protocol §A1.2 **role 1** "
      "(accounting): it measures the control after the fact and never enters "
      "it. `d̂` is fitted on `log(1 + tr_duration)`, so the log1p column is the "
      "selection scale (§5); the seconds column is the decision scale.\n")
    A("### All builds\n")
    A("| form | n | MAE (log1p) | median AE (log1p) | MAE (s) | median AE (s) | "
      "Spearman ρ |")
    A("| :-- | --: | --: | --: | --: | --: | --: |")
    labels = {"4b_expanding": "④b project prior (expanding)",
              "4a_xgboost": "④a XGBoost regressor",
              "4a_ridge": "④a Ridge (reference, not eligible as primary)"}
    for key, label in labels.items():
        A(f"| {label} " + _q(out["calibration_split"][key]["all_builds"]))
    A("")
    A("### Restricted to the project rung (cold-start builds excluded, §6.3(3))\n")
    A("| form | n | MAE (log1p) | median AE (log1p) | MAE (s) | median AE (s) | "
      "Spearman ρ |")
    A("| :-- | --: | --: | --: | --: | --: | --: |")
    for key, label in labels.items():
        A(f"| {label} " + _q(out["calibration_split"][key]["project_rung_only"]))
    A("")

    A("\n## The primary control (§5 — predeclared rule, applied once)\n")
    A(f"> **Rule.** {sel['rule']}\n")
    A(f"- ④a XGBoost, calibration log1p MAE = **{sel['mae_log1p_4a_xgboost']:.6f}**")
    A(f"- ④b expanding prior, calibration log1p MAE = "
      f"**{sel['mae_log1p_4b_expanding']:.6f}**")
    A(f"- ⇒ **primary form = {sel['primary_form']}**, frozen here and not "
      "revisable by any test-split number (§2 use-discipline).\n")
    A("Both forms run in the P3 replay regardless: §A1.6 requires ④a **and** "
      "④b, and §A1.9 makes ④b the mandatory project-identity control that ⑤ "
      "must also beat. \"Primary\" governs which estimate is the control term "
      "inside ⑤'s arms, not which strategies execute.\n")
    A("Note the asymmetry §5 anticipates and this run measures: rank quality "
      "(**Spearman ρ**) is the decision-relevant quality, because ④'s rule is "
      "the monotone threshold `d̂ ≥ d_threshold`; MAE describes how well the "
      "control is *described*. Both are above; neither substitutes for the "
      "other.\n")

    A("\n## Cold-start coverage (§6.3(2))\n")
    A("| form | project rung | language rung | global rung |")
    A("| :-- | --: | --: | --: |")
    for key, label in labels.items():
        lv = out["calibration_split"][key]["coverage"]["levels"]
        A(f"| {label} | {lv['project']['n']:,} ({lv['project']['pct']}%) | "
          f"{lv['language']['n']:,} ({lv['language']['pct']}%) | "
          f"{lv['global']['n']:,} ({lv['global']['pct']}%) |")
    nh = out["calibration_split"]["4b_expanding"]["coverage"]["n_history"]
    A("")
    A(f"`n_history` = |H(b)|, the project's admissible causal history at "
      f"decision time: min {nh['min']:,} · p25 {nh['p25']:,.0f} · median "
      f"{nh['p50']:,.0f} · p75 {nh['p75']:,.0f} · p95 {nh['p95']:,.0f} · max "
      f"{nh['max']:,} · builds with none: {nh['zero']:,}.\n")
    A("Rung 3 (global) is **total** by construction, so `d̂` is defined for "
      "every build and no build silently escapes a strategy (test T5).\n")

    A("\n## Declared sensitivities (§6.3(4)) — secondary, never selective\n")
    A("None of these may change the primary form; they are reported so the "
      "primary's dependence on its arbitrary choices is visible.\n")
    A("| variant | n | MAE (log1p) | median AE (log1p) | Spearman ρ | "
      "project rung |")
    A("| :-- | --: | --: | --: | --: | --: |")
    # Pipes are escaped: |H(b)| would otherwise split the markdown table cell.
    slabels = {"4b_trailing_50": "④b trailing 50-build window",
               "4b_min_history_5": "④b requiring \\|H(b)\\| ≥ 5",
               "4b_min_history_20": "④b requiring \\|H(b)\\| ≥ 20",
               "4a_ridge": "④a Ridge instead of XGBoost"}
    for key, label in slabels.items():
        e = out["sensitivities"][key]["all_builds"]
        cov = out["sensitivities"][key]["coverage"]["levels"]["project"]
        if not e.get("n"):
            A(f"| {label} | — | — | — | — | — |")
            continue
        A(f"| {label} | {e['n']:,} | {e['mae_log1p']:.4f} | "
          f"{e['median_ae_log1p']:.4f} | {e['spearman_rho']:.4f} | "
          f"{cov['n']:,} ({cov['pct']}%) |")
    A("")

    # A sensitivity that beats the primary is exactly the situation the
    # predeclaration exists for, so it is stated rather than left in the table.
    primary_mae = out["calibration_split"]["4b_expanding"]["all_builds"]["mae_log1p"]
    beaten = {k: v["all_builds"]["mae_log1p"] for k, v in out["sensitivities"].items()
              if v["all_builds"].get("n")
              and v["all_builds"]["mae_log1p"] < primary_mae}
    if beaten:
        A("> ### ⚠ A declared sensitivity outperforms the primary form\n")
        A("> On this run the following variant(s) beat the primary "
          f"(④b expanding, log1p MAE {primary_mae:.4f}) on the selection "
          "metric:\n>")
        for key, mae in sorted(beaten.items(), key=lambda kv: kv[1]):
            A(f"> - **{slabels.get(key, key)}** — log1p MAE {mae:.4f} "
              f"({primary_mae - mae:+.4f} vs primary)")
        A(">")
        A("> **The primary does not change.** `duration_control_spec.md` §4.1 "
          "pins the expanding window as ④b's form *\"regardless of outcome\"*, "
          "and §5 fixes selection to the ④a-vs-④b comparison alone. Switching "
          "now would be choosing a form **because** its number was seen, which "
          "is the specific failure the predeclaration exists to prevent.")
        A("> Changing it is possible but is a decision-log entry argued from "
          "principle, not from this table — and it would have to be made "
          "before the test split is opened (§2 use-discipline).\n")

    A("\n## Threats to validity carried out of this task\n")
    A("1. **The control is a *predicted* quantity.** Estimator error propagates "
      "into the null, so RQ2 answers **\"beyond *predictable* duration\"**, not "
      "\"beyond duration\". The numbers above are how large that error is. "
      "§A1.10's oracle-duration arm — labelled *\"oracle — unrealizable in "
      "deployment\"* — exists to bound how much of any ⑤ margin is estimator "
      "error rather than SE signal.")
    A("2. **Fit-time wall-clock asymmetry** (DL-014 §4, §Resolution 5). Under "
      "mechanism 1 a train build later in wall-clock than a scored held-out "
      "build can inform the fitted control, because the splits are "
      "project-disjoint and their time ranges overlap end-to-end. **The "
      "direction of this bias is undetermined** — it is neither measured nor "
      "assumed, and no claim that it strengthens the null or is otherwise "
      "conservative is made on its basis.")
    A("3. **Cold-start coarsening.** Builds on the language or global rung get "
      "a markedly less informative `d̂`; every headline number above is "
      "therefore given twice, with and without them.")
    A("4. **④a absorbs SE-through-duration by design** (§A1.13). ④a is fitted "
      "on the same 28 features, so any SE information that acts *by predicting "
      "duration* is already inside the control. RQ2 therefore tests for SE "
      "information **orthogonal to predicted duration** — the strictest "
      "reading, and a deliberate one.")
    A("5. **Form selection happens on a duration distribution that is not the "
      "test one** (DL-017, and `splits_summary.md` §Methodological threats "
      "asked P1-T4 to report it here). The P1-T3 manifest measured calibration "
      "p95 build duration at 11,638 s against test 5,643 s — the calibration "
      "split carries the heavier tail. Those two figures are quoted from "
      "`results/p1/splits.json` (P1-T3's run, §A1.2 role 1 descriptive "
      "statistics); **no test-split project was read in this task**. The "
      "primary form above is selected on calibration by protocol (§5), so it "
      "is selected against the heavier tail.")
    A("6. **Wall-clock under-counts parallel job compute** (DL-010) — inherited "
      "from the duration source, and it propagates into both the label `d̂` is "
      "fitted on and the energy accounting.\n")

    A("\n## Provenance footer\n")
    A(f"- Dataset: `{p['dataset_path']}` (read-only).")
    A(f"- Split: frozen P1-T3 assignment, digest re-verified at load.")
    A(f"- **Test split untouched:** {pop['test_projects_dropped_unread']:,} test "
      f"projects / {pop['test_builds_dropped_unread']:,} builds were dropped "
      "immediately after the split join and never entered fitting, history, "
      "scoring, or any number in this report.")
    A(f"- Persisted control: `{Path(p['estimator_artifact']).as_posix()}` "
      f"(fit id `{p['fit_id']}`, seed {p['seed']}, primary form "
      f"`{sel['primary_form']}`).")
    A("")
    (RESULTS / "duration_control.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

"""Tests for scripts/sensitivity_analysis.py (P3-T4, DL-030)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from replay import simulator as sim
from scheduler_core import carbon, policy

CODE_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, file: Path):
    for p in (CODE_ROOT, CODE_ROOT / "scripts", CODE_ROOT / "tests"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sa = _load("sensitivity_under_test", CODE_ROOT / "scripts" / "sensitivity_analysis.py")
trr = _load("trr_helpers_sa", CODE_ROOT / "tests" / "test_run_test_replay.py")


@pytest.fixture(scope="module")
def mats():
    trace = trr._trace(n=150, seed=21)
    spec = policy.load_policy_spec(require_fitted=True)
    profile = carbon.load_hour_of_week_profile()
    settings = [sim.Setting("1_static"),
                sim.Setting("2_blanket_carbon_aware", d_threshold_seconds=0.0, w_max_hours=167.0),
                sim.Setting("3_eligibility_only", d_threshold_seconds=0.0, w_max_hours=24.0),
                sim.Setting("4a_duration_estimator", d_threshold_seconds=480.0, w_max_hours=24.0),
                sim.Setting("5_se_informed_policy", d_threshold_seconds=480.0, w_max_hours=24.0)]
    recs = []
    for s in settings:
        rec = sim.replay_setting(trace, s, base_spec=spec, profile=profile, p_avg_w=42.5,
                                 primary_form="4b")
        recs.append(pd.read_csv(pd.io.common.StringIO(
            sim.records_to_csv_bytes(rec, header=True).decode("utf-8")), dtype=str,
            keep_default_na=False, na_values=[""]))
    m = sa.fa.Matrices(recs[0])
    for s, r in zip(settings, recs):
        m.add(s.setting_id, (s.d_threshold_seconds, s.w_max_hours), r)
    m.finalise()
    return m


def test_class_rule():
    assert sa._cls(-2.0, -1.0) == "lower"
    assert sa._cls(1.0, 2.0) == "higher"
    assert sa._cls(-1.0, 1.0) == "n.s."


def test_v4_has_the_eight_predeclared_classes(mats):
    res = sa.v4(mats, np.ones(len(mats.ids), dtype=bool), n_resamples=20)
    assert len(res["classes"]) == 8
    assert set(res["pairs"]) == {"5_minus_1", "5_minus_2", "5_minus_3", "5_minus_4a"}
    for rec in res["pairs"].values():
        for m in rec.values():
            assert m["ci_lo"] <= m["ci_hi"]


def test_v4_points_equal_the_simulator_summary(mats, tmp_path):
    res = sa.v4(mats, np.ones(len(mats.ids), dtype=bool), n_resamples=5)
    c, t = sa._carbon_ttff(mats, np.ones(len(mats.ids)))
    i5, i1 = mats.index["5_se_informed_policy__d480__w24"], mats.index["1_static"]
    assert res["pairs"]["5_minus_1"]["carbon_per_1000_builds_g"]["point"] == pytest.approx(c[i5] - c[i1])
    assert res["pairs"]["5_minus_1"]["ttff_p95_h_failed"]["point"] == pytest.approx(t[i5] - t[i1])


def test_energy_rescale_leaves_savings_and_ttff_invariant(mats):
    ones = np.ones(len(mats.ids))
    s0, t0 = mats.points(ones)
    s1, t1 = sa._scaled(mats, np.full(len(mats.ids), 1.5)).points(ones)
    assert s1 == pytest.approx(s0, abs=1e-12) and np.array_equal(t0, t1)


def test_headline_ids_follow_dl_030():
    ids = sa.headline_ids(12.0)
    assert ids == {"5": "5_se_informed_policy__d480__w12", "1": "1_static",
                   "2": "2_blanket_carbon_aware__d0__w167", "3": "3_eligibility_only__d0__w12",
                   "4a": "4a_duration_estimator__d480__w12"}


def _em_csv(path: Path, zone: str, year: int, amplitude: float, drop: int = 0) -> None:
    idx = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", inclusive="left")
    val = 200.0 + amplitude * np.sin(2 * np.pi * idx.hour / 24)
    df = pd.DataFrame({"Datetime (UTC)": idx.strftime("%Y-%m-%d %H:%M:%S"), "Zone id": zone,
                       "Carbon intensity gCO₂eq/kWh (direct)": val,
                       "Carbon intensity gCO₂eq/kWh (Life cycle)": val + 50})
    if drop:
        df = df.iloc[drop:]
    df.to_csv(path, index=False)


def test_grid2_profile_uses_the_direct_column_and_the_criteria(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, "EM_DIR", tmp_path)
    for y in (2024, 2025):
        _em_csv(tmp_path / f"US-CAL-CISO_{y}_hourly.csv", "US-CAL-CISO", y, amplitude=150.0)
    r = sa.build_grid2_profile("CAISO", "US-CAL-CISO")
    assert r["column_used"].endswith("(direct)")
    assert len(r["_profile"]) == 168 and r["criteria"]["b_coverage_ge_95"]
    assert r["peak_to_trough"] == pytest.approx(350.0 / 50.0, rel=1e-3)
    assert r["qualifies"] is True


def test_grid2_profile_fails_a_flat_grid_and_low_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, "EM_DIR", tmp_path)
    _em_csv(tmp_path / "DE_2024_hourly.csv", "DE", 2024, amplitude=10.0, drop=1000)
    _em_csv(tmp_path / "DE_2025_hourly.csv", "DE", 2025, amplitude=10.0)
    r = sa.build_grid2_profile("Germany", "DE")
    assert r["criteria"]["c_peak_to_trough_gt_uk"] is False
    assert r["criteria"]["b_coverage_ge_95"] is False
    assert r["qualifies"] is False


def _mini_eia_xlsx(path: Path) -> None:
    """A minimal EIA-930-shaped workbook: shared strings + one hourly sheet (DL-031)."""
    import zipfile

    strings = ["BA", "UTC time", "CO2 Emissions Intensity for Generated Electricity",
               "CO2 Emissions Intensity for Consumed Electricity", "CISO"]
    sst = "".join(f"<si><t>{s}</t></si>" for s in strings)
    # 2024-01-01 01:00 UTC (hour end) = serial 45292 + 1/24; second row has an empty consumed value
    rows = ('<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
            '<c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c></row>'
            f'<row r="2"><c r="A2" t="s"><v>4</v></c><c r="B2"><v>{45292 + 1 / 24!r}</v></c>'
            '<c r="C2"><v>0.30</v></c><c r="D2"><v>0.40</v></c></row>'
            f'<row r="3"><c r="A3" t="s"><v>4</v></c><c r="B3"><v>{45292 + 2 / 24!r}</v></c>'
            '<c r="C3"><v>0.31</v></c></row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns}><sheets>'
                                      '<sheet name="Published Hourly Data" sheetId="1"/></sheets></workbook>')
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>{sst}</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{rows}</sheetData></worksheet>")


def test_eia_reader_uses_consumed_column_grams_and_hour_start(tmp_path):
    p = tmp_path / "CISO.xlsx"
    _mini_eia_xlsx(p)
    s = sa.load_eia930_hourly(p)
    assert list(s.index) == [pd.Timestamp("2024-01-01 00:00", tz="UTC"),
                             pd.Timestamp("2024-01-01 01:00", tz="UTC")]
    assert s.iloc[0] == pytest.approx(0.40 * 453.59237)       # consumed, not generated (0.30)
    assert np.isnan(s.iloc[1])                                  # an empty cell stays a gap


def test_no_files_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(sa, "EM_DIR", tmp_path)
    assert sa.build_grid2_profile("CAISO", "US-CAL-CISO")["status"] == "no files"

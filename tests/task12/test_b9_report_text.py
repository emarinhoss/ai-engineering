"""Ruling B-9 follow-ups on the W/S 13 A 8 baseline (review W-4, W-6, W-9, W-11): the ceiling flag, report text that
takes its values from the record, and the dirty flag in the aero, rotation and ground-effect records."""
import json
import math
from pathlib import Path

import pytest

from conceptual import stage1, uav
from conceptual.engine_model import table_for_run
from conceptual import vspaero_check as vsc
from measurement import ground_effect_validation as gev
from measurement import stage1_compliance as sc
from measurement import stage3_aero, stage3_rotation
from measurement import stage3_perf as sp

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8"
MEASURE = ROOT / "runs/task12/stage3/2026-11-27/m250_ws13a8_measure"
DESIGN = BASE / "design_pusher.json"


class FakeTable:
    h = [0.0, 10000.0, 30000.0]


# ---- ceiling flag (W-4, B-9c) -------------------------------------------------------------------
def test_ceiling_flag_is_true_only_above_the_table_top():
    assert uav.ceiling_above_table_top({"engine_model": FakeTable()}, 31738.0) == (True, 30000.0)
    assert uav.ceiling_above_table_top({"engine_model": FakeTable()}, 29955.0) == (False, 30000.0)
    assert uav.ceiling_above_table_top({"engine_model": FakeTable()}, 30000.0) == (False, 30000.0)


def test_ceiling_flag_is_none_without_a_table_engine():
    assert uav.ceiling_above_table_top({}, 31738.0) == (None, None)
    assert uav.ceiling_above_table_top({"engine_model": object()}, 31738.0) == (None, None)


def test_performance_carries_the_flag_and_leaves_the_ceiling_unchanged():
    rec = json.loads(DESIGN.read_text())
    L, _ = uav.load_ledger(BASE / "ledger.yaml")
    eng = sp.record_engine(rec, table_for_run(BASE), L.get("engine_sfc_allowance", 1.0))
    perf = stage1.analyse(rec["concept"], rec["W_S"], rec["A"], L, eng, W0_guess=rec["W0_lb"])["performance"]
    assert perf["service_ceiling_above_table_top"] is True and perf["engine_table_top_ft"] == 30000.0
    assert perf["service_ceiling_ft"] == pytest.approx(rec["performance"]["service_ceiling_ft"], rel=1e-5)


def test_perf_note_names_the_value_that_is_above_the_top():
    top = 30000.0
    note = sp.ceiling_clamp_note(top, 31738.0, 29955.0)
    assert "Stage 1's ceiling (31,738 ft) is above it and leans on that clamp" in note
    assert "this one (29,955 ft) is below it and does not" in note
    assert "both lean" in sp.ceiling_clamp_note(top, 31738.0, 30500.0)
    assert "this one (30,500 ft) is above it" in sp.ceiling_clamp_note(top, 29000.0, 30500.0)
    assert sp.ceiling_clamp_note(top, 29000.0, 29955.0) == "" and sp.ceiling_clamp_note(None, 31738.0, 1.0) == ""


def test_perf_report_of_the_baseline_has_the_corrected_note_and_loiter_label():
    res = json.loads((MEASURE / "perf.json").read_text())
    text = sp.report_text(res)
    assert "Stage 1's ceiling (31,738 ft) is above it and leans on that clamp" in text
    assert "this one (29,955 ft) is below it and does not" in text
    assert "200 nm out + 11 h + 200 nm back" in text and "+ 8 h +" not in text


def test_compliance_report_carries_the_ceiling_caveat():
    res = json.loads((ROOT / "runs/task12/stage3/2026-11-27/compliance_ws13a8/compliance.json").read_text())
    text = sc.report_text(res)
    assert "Row 14: the Stage 1 service ceiling (31,738 ft) is above the engine table's top altitude (30,000 ft)" in text
    assert sc.ceiling_caveat([{"requirement": "R12 service ceiling x", "value": 29000.0}], 30000.0) == ""


# ---- text from the record (W-6, W-9) ---------------------------------------------------------------
def test_loiter_label_comes_from_the_record():
    assert sp.loiter_hours(DESIGN) == pytest.approx(11.0)
    assert sp.relabel_loiter("R5 mission 200 nm + 8 h + 200 nm", 11.0) == "R5 mission 200 nm + 11 h + 200 nm"
    assert sp.relabel_loiter("R5 mission 200 nm + 8.5 h + 200 nm", 11.0) == "R5 mission 200 nm + 11 h + 200 nm"


def test_compliance_report_text_is_not_tied_to_the_frozen_design():
    """Commit 897b5e9: the title and the V-n pointer do not name the frozen design, and the R5 row shows the sized loiter."""
    res = json.loads((ROOT / "runs/task12/stage3/2026-11-27/compliance_ws13a8/compliance.json").read_text())
    text = sc.report_text(res)
    assert text.startswith("# Task 12: Stage 1 compliance table of the design record (ruling B-7)")
    assert "frozen design" not in text.splitlines()[0]
    assert "the gust value itself is in the V-n check of the same design" in text
    assert "2026-11-26_task12_vn_check" not in text
    assert "R5 mission 200 nm + 11 h + 200 nm" in text and "+ 8 h +" not in text


def test_aero_report_cruise_mach_is_the_records():
    res = json.loads((MEASURE / "aero.json").read_text())
    assert stage3_aero.cruise_mach(res) == pytest.approx(0.2104, abs=1e-4)
    out = ROOT / "tests" / "_aero_report_tmp.md"
    try:
        stage3_aero.report(res, out, "0" * 40, "aero.json")
        text = out.read_text()
    finally:
        out.unlink(missing_ok=True)
    m = stage3_aero.cruise_mach(res)
    assert f"cruise Mach {m:.3f} the Prandtl-Glauert factor is {1 / math.sqrt(1 - m * m):.3f}" in text
    assert "Mach 0.16 " not in text


def test_vspaero_lift_slope_machs_come_from_the_run_conditions():
    d = json.loads(DESIGN.read_text())
    cond = {"cruise_out": {"Mach": 0.21}, "loiter": {"Mach": 0.14}}
    out = vsc.raymer_values(d, (BASE / "ledger.yaml").read_text(), cond)["CL_alpha_wing_bare_planform_eta1"]
    assert set(out) == {0.0, "cruise_out", "loiter"}
    assert out["cruise_out"] > out["loiter"] > out[0.0]


# ---- dirty flag (W-11) -----------------------------------------------------------------------------
def test_aero_rotation_and_ground_effect_records_carry_the_dirty_flag(tmp_path, monkeypatch):
    dirty = [" M measurement/x.py"]
    for mod in (stage3_aero, stage3_rotation, gev):
        monkeypatch.setattr(mod, "git_dirty_files", lambda: dirty)

    # ground effect: compute() replaced by a stub row set
    monkeypatch.setattr(gev, "compute", lambda: {"rows": [], "verdict": "stub"})
    out = tmp_path / "ge.json"
    gev.main(["--out", str(out)])
    inp = json.loads(out.read_text())["inputs"]
    assert inp["git_dirty"] is True and inp["git_dirty_files"] == dirty

    # rotation
    stub = {"ledger_path": str(BASE / "ledger.yaml"), "cases": {"nominal": {"k_GE": 1.0}},
            "row": {"stage1": 0.0, "stage3": 0.0, "limit": 0.0, "limit_met_stage3": True, "tail_scale_estimate": 1.0}}
    monkeypatch.setattr(stage3_rotation, "compute", lambda design: dict(stub))
    out = tmp_path / "rot.json"
    stage3_rotation.main(["--design", str(DESIGN), "--out", str(out)])
    inp = json.loads(out.read_text())["inputs"]
    assert inp["git_dirty"] is True and inp["git_dirty_files"] == dirty

    # aero
    monkeypatch.setattr(stage3_aero, "measure", lambda d, L: {"rows": []})
    out = tmp_path / "aero.json"
    stage3_aero.main(["--design", str(DESIGN), "--out", str(out)])
    inp = json.loads(out.read_text())["inputs"]
    assert inp["git_dirty"] is True and inp["git_dirty_files"] == dirty

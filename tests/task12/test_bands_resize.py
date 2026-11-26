"""Owner ruling B-2a: the robust sizing (measurement/robust_sizing.py --curve-targets --engine-as-is) must see the
composite band (`composite_model: saving`) and the empty-weight band, and with both at their nominal values the
frozen baseline must size exactly as recorded."""
import json
from pathlib import Path

import pytest

from conceptual import uav
from measurement import info_gap
from measurement import robust_sizing as rs

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05"
NEW = ("composite_factor", "empty_weight_factor")


@pytest.fixture(scope="module")
def frozen_resized():
    """The frozen cell (450 hp, W/S 16, A 7, L_sized of the record) sized again by the tool with the current ledger."""
    d = json.loads((FROZEN / "design_pusher.json").read_text())
    L_sized = uav.load_ledger(FROZEN / "ledger.yaml")[0]["loiter_h"]
    try:
        rs.use_engine_as_is(True)
        _, L, rec = rs.sized_aircraft_guess(450.0, 16.0, 7.0, L_sized, rs.first_guess(450.0, L_sized), rs.VC_RULE)
        built = info_gap.Built("in memory", True, record=(rec, L, rs.engine_table()))
    finally:
        rs.use_engine_as_is(False)
    return d, L, rec, built


def test_sizing_with_both_bands_nominal_is_the_frozen_record(frozen_resized):
    d, L, rec, _ = frozen_resized
    assert L["composite_model"] == "saving" and L["empty_weight_factor"] == 1.0      # the sizing ledger has both lines
    for k in ("W0_lb", "fuel_lb", "We_lb"):
        assert rec[k] == pytest.approx(d[k], rel=1e-12), k
    assert rec["V_c_eas_kt"]["sea_level"] == d["V_c_eas_kt"]["sea_level"]
    assert rec["components_lb"] == d["components_lb"]


def test_both_bands_are_variables_of_the_sizing_and_of_the_record_it_writes(tmp_path):
    assert set(NEW) <= {v["name"] for v in rs._variables()}            # the corners of the sizing
    assert set(NEW) <= set(rs.theta_of({}))
    try:
        rs.use_engine_as_is(True)
        (tmp_path / "ledger.yaml").write_text(rs.ledger_text(9.0, 115.0))    # the copy the mode searches read
    finally:
        rs.use_engine_as_is(False)
    L, entries = uav.load_ledger(tmp_path / "ledger.yaml")
    assert L["composite_model"] == "saving"
    assert set(NEW) <= {v["name"] for v in info_gap.uncertain_variables(entries)}


def test_scaled_corner_carries_the_new_bands_to_the_target():
    """A worst point of U(1) with both new variables at their heavy ends, put at h_T 1.05: the empty-weight factor
    goes to 1.0525, the composite factor stays at 1.00 (metal; a fraction is clipped at 1)."""
    moved = rs.scaled_corner({"composite_factor": 1.0, "empty_weight_factor": 1.05, "engine_sfc_mult": 1.1}, 1.05)
    assert moved["empty_weight_factor"] == pytest.approx(1.0525)
    assert moved["composite_factor"] == 1.0
    assert moved["engine_sfc_mult"] == pytest.approx(1.105)


def test_the_built_aircraft_of_the_sizing_loop_feels_both_bands(frozen_resized):
    """The in-memory built aircraft the bisection classifies: each band alone makes it heavier and costs hours,
    and the cliff score (transit power ratio) rises."""
    _, _, rec, built = frozen_resized
    nom = rs.theta_of({})
    h0, w0, r0 = built.hours_on_station(nom), built.w0_for(nom), info_gap.transit_power_ratio(built, nom)[0]
    assert w0 == pytest.approx(rec["W0_lb"], abs=0.1)
    for name, value in (("composite_factor", 1.0), ("empty_weight_factor", 1.05)):
        th = rs.theta_of({name: value})
        assert built.w0_for(th) > w0 + 50.0, name
        assert built.hours_on_station(th) < h0 - 0.2, name
        assert info_gap.transit_power_ratio(built, th)[0] > r0, name


def test_a_cell_that_loses_its_design_when_the_corner_sets_grow_has_no_design(tmp_path, monkeypatch):
    """Iteration 1 finds a design, its worst point violates and is added, iteration 2 finds no compliant candidate:
    the cell has no design (the iteration-1 design does not meet the target), with the reasons of the last search."""
    row = {"P_hp": 450.0, "W_S": 16.0, "A": 7.0, "L_sized_h": 8.0, "ok": True, "failed": [], "status": "bisected", "W0_lb": 3000.0}
    heavy = dict(rs.candidate_row(450.0, 16.0, 7.0), status="too heavy already at 8 h")
    searches = iter([([row], row), ([heavy], None)])
    monkeypatch.setattr(rs, "curve_search", lambda *a, **k: next(searches))
    monkeypatch.setattr(rs, "write_record_rec", lambda row, folder, rec: Path(folder) / "design_pusher.json")
    worst = {"endurance": {"moved": {"empty_weight_factor": 1.0525}, "hours": 3.0, "flyable": True},
             "cliff": {"moved": {}, "transit_ratio": 0.9, "flyable": True}}
    monkeypatch.setattr(rs, "mode_worst_at", lambda path, need, h: worst)
    cache_ = {(450.0, 16.0, 7.0, 8.0, rs.VC_RULE): ((None, None, {}), {})}
    res = rs.run_target(450.0, 1.05, tmp_path, cache_, 3.5, (16.0,), (7.0,), 0.0, 1e9, True, 1, lambda *a, **k: None)
    assert res["design"] is None and len(res["iterations"]) == 2
    assert res["iterations"][0]["corners_added"] == ["endurance"] and res["iterations"][1]["winner"] is None
    assert list(res["reasons"]) == ["too heavy already at 8 h: weight iteration does not close"]
    assert json.loads((tmp_path / "P450" / "h1.05" / "target_result.json").read_text())["design"] is None

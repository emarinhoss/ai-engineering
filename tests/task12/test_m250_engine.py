"""RR M250-B17F App. K cycle (measurement/m250_engine.py): calibration, validation, table, and the TP100
refactor that made tp100_engine.table take its rating as parameters; engine selection in Stage 1."""
import json

import pytest

from conceptual import stage1
from conceptual.engine_model import TableEngine
from measurement import m250_engine as m
from measurement import tp100_engine as tp

TABLE = m.REPO / "data" / "task12" / "m250_table.json"


@pytest.fixture(scope="module")
def nominal():
    return m.calibrate(**m.NOMINAL)


def test_calibration_reproduces_takeoff_sfc_and_mgt(nominal):
    ref = nominal["ref"]
    assert ref["bsfc"] == pytest.approx(0.613, abs=1e-5)
    assert m.r_to_c(ref["Tt4"] * ref["tau_m1"] * ref["tau_tH"]) == pytest.approx(810.0, abs=0.01)
    assert ref["shaft_hp_per_m0"] * ref["m0"] == pytest.approx(450.0)


def test_part_power_at_rating_is_the_calibration(nominal):
    sfc, mgt, _ = m.part_power(nominal, 450.0)
    assert sfc == pytest.approx(0.613, abs=1e-4)
    assert mgt == pytest.approx(810.0, abs=0.1)


def test_table_loads_and_is_capped_at_rating():
    eng = TableEngine(TABLE)
    assert eng.rated == 450.0
    assert eng.meta["calibration_bsfc"] == 0.613
    # 66 kt lies between the 50 and 70 kt nodes; linear interpolation of the slowly rising power
    # reads about 0.05 % under the rating, so the cap is not yet reached; it is at 150 kt
    assert eng.power_available(0.0, 66.0) == pytest.approx(450.0, rel=2e-3)
    assert eng.power_available(0.0, 150.0) == 450.0
    # full throttle at 66 kt: SFC close to the calibration value (interpolation between grid nodes)
    assert eng.bsfc(0.0, 66.0, eng.power_available(0.0, 66.0)) == pytest.approx(0.613, rel=0.01)


def test_table_says_which_engine():
    assert json.loads(TABLE.read_text())["engine"] == "RR_M250_B17F"


def test_tp100_table_unchanged_by_the_refactor(monkeypatch):
    """table() with its defaults is the TP100 table: same labels, same member, same first cell as the
    committed file (the full byte-for-byte comparison was made when the refactor was written)."""
    committed = json.loads((m.REPO / "data" / "task12" / "tp100_table.json").read_text())
    monkeypatch.setattr(tp, "TABLE_H", [0.0])
    monkeypatch.setattr(tp, "TABLE_V", [30.0, 50.0])
    monkeypatch.setattr(tp, "TABLE_F", [0.10, 0.50, 1.0])
    t = tp.table()
    assert t["rated_shp"] == committed["rated_shp"] == 241.0
    assert t["calibration_bsfc"] == committed["calibration_bsfc"] == 0.901
    assert t["member"] == committed["member"]
    assert t["full_throttle_shp"][0] == committed["full_throttle_shp"][0][:2]
    c = committed["bsfc"][0][0]                          # fractions 0.10, 0.50, 1.0 are entries 0, 8, 18
    assert t["bsfc"][0][0] == [c[0], c[8], c[18]]
    assert set(t) == set(committed)


def test_engine_options_gives_the_chosen_m250_its_table_and_the_ledger_allowance():
    engines, _ = stage1.engine_options()
    assert stage1.CHOSEN_ENGINE == "RR_M250_B17F"
    m = engines["RR_M250_B17F"]["model"]
    assert isinstance(m, TableEngine) and m.rated == 450.0
    assert m.sfc_scale == pytest.approx(1.02)                  # ruling R-b
    assert "model" not in engines["PBS_TP100"]                 # not chosen: no table in this call


def test_engine_options_can_choose_the_tp100_with_its_own_allowance():
    engines, _ = stage1.engine_options("PBS_TP100", 1.05)
    m = engines["PBS_TP100"]["model"]
    assert m.rated == 241.0 and m.sfc_scale == pytest.approx(1.05)
    assert "model" not in engines["RR_M250_B17F"]


# ---- review M-9: validate(), the 420 column, the committed table against the current code ----------------
def test_validate_gives_three_points_ratios_and_a_pass_for_the_450_column(nominal):
    v = m.validate(nominal, m.ratings("450"))
    assert [r["point"] for r in v["points"]] == ["normal_cruise", "cruise_a_90pct", "cruise_b_75pct"]
    assert v["passed"] and v["mgt_ok"] and all(r["ok"] for r in v["points"])
    for r in v["points"]:
        assert r["ratio_brochure"] == pytest.approx(r["bsfc_brochure"] / 0.613)
        assert r["ratio_model"] == pytest.approx(r["bsfc"] / nominal["ref"]["bsfc"])
        assert abs(r["dev_pct"]) <= 100.0 * m.TOL_SFC
    assert abs(v["mgt_dev_c"]) <= m.TOL_MGT_C


def test_420_column_fails_validation():
    """The brochure's other column (420 shp, SFC 0.657): calibrated the same way, it fails on MGT and SFC."""
    rates = m.ratings("420")
    to = rates["take_off"]
    member = m.calibrate(m.NOMINAL["e_c"], m.NOMINAL["e_t"], shp=to["shp"], bsfc=to["bsfc_max"], mgt_c=to["mgt_c"])
    v = m.validate(member, rates)
    assert not v["passed"]
    assert not v["mgt_ok"] and v["mgt_dev_c"] > m.TOL_MGT_C
    assert not all(r["ok"] for r in v["points"])


def test_committed_table_is_what_the_current_code_writes(nominal):
    """The data file is the output of measurement/m250_engine.py as it stands (numbers and text)."""
    assert json.dumps(m.table(nominal), indent=1) == TABLE.read_text()


def test_control_law_text_says_ceiling_not_held():
    law = json.loads(TABLE.read_text())["control_law"]
    assert "ceiling" in law and "held" not in law


def test_unchoked_cells_summary_follows_the_table():
    t = json.loads(TABLE.read_text())
    u = m.unchoked_cells(t)
    assert 0.0 < u["share"] < 1.0 and u["n_cells"] == 13 * 11 * 19
    assert u["lowest_choked_fraction_min"] <= u["lowest_choked_fraction_max"]
    # a cell below the smaller fraction is unchoked
    e = TableEngine(TABLE)
    p = u["lowest_choked_fraction_min"] * e._full_throttle(0.0, 90.0) - 1.0
    assert not e.turbine_choked(0.0, 90.0, p)[0]

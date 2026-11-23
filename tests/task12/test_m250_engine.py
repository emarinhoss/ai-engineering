"""RR M250-B17F App. K cycle (measurement/m250_engine.py): calibration, table, and the TP100
refactor that made tp100_engine.table take its rating as parameters."""
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


def test_engine_options_gives_the_m250_a_model_and_keeps_the_chosen_engine():
    engines, _ = stage1.engine_options()
    assert isinstance(engines["RR_M250_B17F"]["model"], TableEngine)
    assert stage1.CHOSEN_ENGINE == "PBS_TP100"
    assert isinstance(engines["PBS_TP100"]["model"], TableEngine)

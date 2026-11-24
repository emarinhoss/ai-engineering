"""Stage 3 modules on the M250-B17F baseline record (2026-11-24, W/S 16, A 7): engine route,
propeller rows, rebuild, and that the TP100 route is still the one chosen for a TP100 record."""
import json
import math
from pathlib import Path

import pytest

from conceptual.units import KT, isa
from measurement import mattingly as M
from measurement import stage3_engine as se
from measurement import stage3_perf as sp

ROOT = Path(__file__).resolve().parents[2]
M250_RECORD = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"
TP100_RECORD = ROOT / "runs/task12/stage1/2026-11-21d/design_pusher.json"


@pytest.fixture(scope="module")
def engine():
    return se.measure_record(M250_RECORD)


def row(res, rid):
    return next(r for r in res["rows"] if r["id"] == rid)


def test_record_engine_is_detected():
    assert se.is_m250(json.loads(M250_RECORD.read_text()))
    assert not se.is_m250(json.loads(TP100_RECORD.read_text()))


def test_m250_rebuild_reproduces_the_record():
    d, L, b, _, check = sp.rebuild(M250_RECORD)
    assert d["bhp_sl"] == 450.0
    for v in check.values():
        assert v["rebuilt"] == pytest.approx(v["record"], rel=1e-6)


def test_family_contains_the_table_member(engine):
    # nominal e_c 0.82, e_t 0.86 is in the family and reproduces the record's table
    assert any(abs(m["e_c"] - 0.82) < 1e-9 and abs(m["e_t"] - 0.86) < 1e-9 for m in engine["detail"]["family"])
    assert engine["detail"]["nominal_pi_c_gap"] < 1e-6


def test_table_rows_are_not_judged_and_brochure_rows_are(engine):
    for rid in ("power_20000", "power_25000", "sfc_cruise_out", "sfc_loiter", "sfc_cruise_back", "ceiling"):
        r = row(engine, rid)
        assert not r["independent"] and r["verdict"].startswith("not judged")
    for rid in ("brochure_normal_cruise", "brochure_cruise_a_90pct", "brochure_cruise_b_75pct"):
        r = row(engine, rid)
        assert r["independent"] and r["verdict"] in ("within", "outside")
        ok = all(abs(x) <= r["tolerance"] for x in r["deviation"])
        assert (r["verdict"] == "within") == ok


def test_power_row_matches_the_table_at_the_record_speed(engine):
    from conceptual.engine_model import TableEngine, table_for_run
    t = TableEngine(table_for_run(M250_RECORD.parent))
    assert row(engine, "power_20000")["stage1"] == pytest.approx(t.power_available(20000.0, 95.0))


def test_stage1_leg_sfc_is_the_record_value(engine):
    d = json.loads(M250_RECORD.read_text())
    leg = next(g for g in d["mission"] if g["segment"] == "loiter")
    assert row(engine, "sfc_loiter")["stage1"] == leg["cbhp_mean"]


def test_validity_share_is_the_records(engine):
    d = json.loads(M250_RECORD.read_text())
    assert engine["detail"]["validity"]["mission_fuel_share_unchoked_record"] == d["unchoked_fuel_share"]


def test_actuator_disk_by_hand():
    # T = 1000 lb at 100 ft/s, sea level, 6 ft diameter: C_T* = T/(q A), eta* from C_T* = 4(1-eta)/eta^2
    rho, V, D, T = 0.002377, 100.0, 6.0, 1000.0
    A = math.pi * D * D / 4.0
    ct = T / (0.5 * rho * V * V * A)
    eta = M.actuator_disk_efficiency(T, rho, V, A)
    assert 4.0 * (1.0 - eta) / eta ** 2 == pytest.approx(ct, rel=1e-9)


def test_prop_fixed_point_is_self_consistent():
    eta, T = sp._prop_eta_fixed_point(300.0, 150.0, isa(10000.0)["rho"], 7.0)
    assert T == pytest.approx(550.0 * eta * 300.0 / 150.0)
    assert eta == pytest.approx(M.real_propeller_efficiency(T, isa(10000.0)["rho"], 150.0, 7.0), rel=1e-9)


def test_prop_rows_on_the_m250_record():
    d, L, b, _, _ = sp.rebuild(M250_RECORD)
    rows = sp.prop_rows(d, L)
    assert [r["id"] for r in rows] == ["prop_eta_climb", "prop_eta_cruise", "prop_eta_loiter"]
    for r in rows:
        assert r["stage1"] == 0.8 and r["tolerance"] == 0.05 and r["deviation_kind"] == "absolute"
        assert r["verdict"] == ("within" if abs(r["stage3"] - 0.8) <= 0.05 else "outside")
        assert 0.0 < r["stage3"] < 0.85


def test_perf_records_the_tables_hash_for_each_engine():
    assert "engine_table" in sp._table_inputs(M250_RECORD)
    assert "tp100_table" in sp._table_inputs(TP100_RECORD)

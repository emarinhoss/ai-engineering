"""Stage 3 reads the record's propeller (review APL-3).

Flat records (propeller_model absent): the Stage 3 numbers of the 2026-11-24 baseline record are
reproduced to 1e-9 from its recorded perf.json and engine.json. App. L records: the efficiency is that
of the actuator disk at the thrust of each condition, with hand numbers, and the propeller rows are
labelled and classified as a coding check."""
import json
import math
from pathlib import Path

import pytest

from conceptual import raymer_propulsion as prop
from conceptual.units import HP, KT, isa
from measurement import mattingly as M
from measurement import stage3_engine as se
from measurement import stage3_perf as sp

ROOT = Path(__file__).resolve().parents[2]
OLD_RECORD = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"
NEW_RECORD = ROOT / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json"
OLD_PERF = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_measure/perf.json"
OLD_ENGINE = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_measure/engine.json"


# ---- hand numbers: App. L solved by hand ----------------------------------------------------------------
def test_ideal_efficiency_by_hand_through_the_stage3_helper():
    """C_T = 1.25 gives eta* = 0.8 from C_T eta*^2 + 4 eta* - 4 = 0 (1.25 x 0.64 + 3.2 - 4 = 0), so with
    f = 0.85 the efficiency is 0.68."""
    rho, D, V = 0.002377, 6.0, 100.0
    disk = prop.ActuatorDisk(rho, D, 0.85)
    area = math.pi * D ** 2 / 4.0
    T = 1.25 * 0.5 * rho * V ** 2 * area
    assert prop.efficiency_for_thrust(disk, T, V) == pytest.approx(0.68, abs=1e-12)


def test_mattingly_power_with_a_disk_uses_the_efficiency_at_the_thrust_needed():
    """Level flight, W0 1,000 lb, W/S 20, q 11.885 psf at 100 ft/s, K 0.05, CD0 0.02: (2.11) gives
    T/W = q CD0/(W/S) + K (W/S)/q. Efficiency from the closed form eta* = (-4 + sqrt(16 + 16 C_T))/(2 C_T),
    times f. Shaft hp = T V/(550 eta)."""
    rho, V, W0, WS, K, CD0, f, D = 0.002377, 100.0, 1000.0, 20.0, 0.05, 0.02, 0.85, 6.0
    q = 0.5 * rho * V ** 2
    t_w = q * CD0 / WS + K * WS / q
    T = t_w * W0
    ct = T / (q * math.pi * D ** 2 / 4.0)
    eta = f * (-4.0 + math.sqrt(16.0 + 16.0 * ct)) / (2.0 * ct)
    expected = T * V / (HP * eta)
    got = sp.mattingly_shaft_hp(W0, WS, q, V, 1.0, K, CD0, prop.ActuatorDisk(rho, D, f))
    assert got == pytest.approx(expected, rel=1e-12)
    # and with a flat number the old formula is unchanged: T V/(550 eta_p) / lapse
    flat = sp.mattingly_shaft_hp(W0, WS, q, V, 0.5, K, CD0, 0.8)
    assert flat == pytest.approx(T * V / (HP * 0.8) / 0.5, rel=1e-12)


def test_record_propeller_is_a_number_for_flat_and_a_disk_for_app_l():
    assert sp.record_propeller({"eta_p": 0.8}, 0.002, 6.0) == 0.8
    L = {"propeller_model": "app_l", "prop_real_to_ideal": 0.85}
    disk = sp.record_propeller(L, 0.002, 6.0)
    assert isinstance(disk, prop.ActuatorDisk) and disk.f == 0.85 and disk.D == 6.0
    assert sp.is_app_l(L) and not sp.is_app_l({"eta_p": 0.8})


# ---- flat record: the 2026-11-24 numbers are reproduced to 1e-9 ---------------------------------------------
@pytest.fixture(scope="module")
def old_perf():
    return sp.compute(OLD_RECORD)


def test_old_record_perf_rows_reproduce_the_recorded_numbers(old_perf):
    """Every recorded Stage 1 and Stage 3 value to 1e-9 relative, except the CD0 row, whose method was
    changed by owner ruling G-3 after that run (Cfe 0.0043 in place of the jet curve): it is checked by
    its own definition below. Verdicts are not compared: rows were reclassified or made not-judged by
    the rulings of 2026-11-25 after that run."""
    recorded = {r["id"]: r for r in json.loads(OLD_PERF.read_text())["rows"]}
    for r in old_perf["rows"]:
        if r["id"] not in recorded or r["id"] == "cd0":
            continue
        for k in ("stage1", "stage3"):
            old, new = recorded[r["id"]][k], r[k]
            if old is None:
                assert new is None, (r["id"], k)
            else:
                assert new == pytest.approx(old, rel=1e-9), (r["id"], k)
    cd = old_perf["cd0_detail"]
    assert cd["CD0"] == pytest.approx(cd["S_wet_over_S"] * 0.0043, rel=1e-12)       # G-3


def test_old_record_mission_legs_and_anderson_reproduce(old_perf):
    rec = json.loads(OLD_PERF.read_text())
    for new, old in zip(old_perf["mission_legs"], rec["mission_legs"]):
        assert new["fraction_stage3"] == pytest.approx(old["fraction_stage3"], rel=1e-9), new["segment"]
    for k in ("W0", "fuel_fraction", "f_cruise", "f_loiter", "buildup_W0"):
        assert old_perf["anderson_w0"][k] == pytest.approx(rec["anderson_w0"][k], rel=1e-9), k
    assert old_perf["anderson_w0"]["eta_cruise"] == 0.8 and old_perf["anderson_w0"]["eta_loiter"] == 0.8


def test_old_record_engine_points_reproduce():
    d, L, b, _, _ = sp.rebuild(OLD_RECORD)
    rec = json.loads(OLD_ENGINE.read_text())["detail"]["points"]
    pts = se._record_points(d, L)
    assert len(pts) == len(rec)
    for new, old in zip(pts, rec):
        assert new["shaft_hp"] == pytest.approx(old["shaft_hp"], rel=1e-9), (old["segment"], old["where"])


def test_old_record_propeller_rows_stay_independent_with_the_ledger_label(old_perf):
    rows = [r for r in old_perf["rows"] if r["id"].startswith("prop_eta")]
    assert len(rows) == 3
    for r in rows:
        assert r["class"] == sp.INDEPENDENT
        assert r["stage1"] == 0.8 and "ledger eta_p" in r["stage1_source"]


# ---- app_l record ------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def new_perf():
    return sp.compute(NEW_RECORD)


def test_new_record_is_app_l():
    d, L, b, _, _ = sp.rebuild(NEW_RECORD)
    assert sp.is_app_l(L)


def test_new_record_propeller_rows_are_coding_checks_against_stage1s_app_l_value(new_perf):
    d = json.loads(NEW_RECORD.read_text())
    rows = {r["id"]: r for r in new_perf["rows"] if r["id"].startswith("prop_eta")}
    assert set(rows) == {"prop_eta_climb", "prop_eta_cruise", "prop_eta_loiter"}
    key = {"prop_eta_climb": "climb_sea_level", "prop_eta_cruise": "cruise_out", "prop_eta_loiter": "loiter"}
    for rid, r in rows.items():
        assert r["class"] == sp.CODING
        assert r["stage1"] == d["propeller_points"][key[rid]]["eta_p"]
        assert "App. L" in r["stage1_source"] and "Raymer Table 3.4" not in r["stage1_source"]
        assert abs(r["deviation"]) < 1e-9                       # same relation, same factor
        assert "no independent propeller check is left" in r["note"]
    # the climb value by hand: 450 hp at 99.25 kt on a 6.909 ft disk, f 0.85 -> 0.720 (record)
    assert rows["prop_eta_climb"]["stage1"] == pytest.approx(0.72017, abs=1e-5)


def test_new_record_power_rows_use_the_disk_not_the_flat_number(new_perf):
    """At the sea-level climb the disk's efficiency is 0.72 (record), not 0.8: Mattingly's power must
    agree with Stage 1's to the search grid (0.1 against 1 ft/s), which a flat 0.8 would not do."""
    r = next(x for x in new_perf["rows"] if x["id"] == "power_climb_sl")
    assert abs(r["deviation"]) < 1e-4
    r_flat = r["stage1"] * (0.72017 / 0.8)                   # what a flat 0.8 would have given, about -10 %
    assert abs(r_flat / r["stage1"] - 1.0) > 0.09


def test_new_record_report_says_no_independent_propeller_check_is_left(new_perf):
    new_perf = dict(new_perf, inputs={"design": "d", "design_sha256": "x", "git_commit": "c", "python": "p", "numpy": "n"},
                    summary={v: sum(r["verdict"] == v for r in new_perf["rows"])
                             for v in ("within", "outside", "not judged", "not computed")})
    text = sp.report_text(new_perf)
    assert "no independent propeller check left" in text


def test_anderson_w0_new_record_uses_the_disk(new_perf):
    aw = new_perf["anderson_w0"]
    assert 0.78 < aw["eta_cruise"] < 0.83 and aw["eta_cruise"] != 0.8
    assert aw["eta_loiter"] < aw["eta_cruise"]                 # heavier thrust loading at the best-endurance speed

"""Propeller efficiency from the App. L actuator disk (owner ruling G-4, 2026-11-25).

Hand numbers. Disk D = 8 ft, A = 16 pi = 50.265 ft^2, rho = 0.002 slug/ft^3, V = 100 ft/s, q = 10 lb/ft^2.
Ideal efficiency 0.8 needs C_T* = 4 (1 - 0.8)/0.8^2 = 1.25 (L.8), so T = 1.25 q A = 12.5 x 50.265 = 628.3 lb.
With the real-to-ideal factor 0.85 the efficiency is 0.68 and the shaft power is T V/(550 x 0.68) = 168.0 hp.
"""
import math

import pytest

from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import uav
from conceptual.units import HP, RHO0, isa

RHO, V, D, F = 0.002, 100.0, 8.0, 0.85
AREA = 16.0 * math.pi
T_HAND = 12.5 * AREA                       # 628.3 lb


def disk():
    return prop.ActuatorDisk(RHO, D, F)


def test_efficiency_for_thrust_hand_number():
    assert disk().efficiency_for_thrust(T_HAND, V) == pytest.approx(0.85 * 0.8, abs=1e-12)


def test_zero_thrust_is_the_real_to_ideal_factor():
    assert disk().efficiency_for_thrust(0.0, V) == pytest.approx(0.85)


def test_shaft_power_for_the_hand_thrust():
    assert prop.shaft_hp(T_HAND * V, V, disk()) == pytest.approx(168.0, rel=1e-4)


def test_fixed_point_from_power_recovers_the_hand_thrust():
    eta, T = disk().efficiency_and_thrust(168.0, V)
    assert eta == pytest.approx(0.68, abs=1e-4)
    assert T == pytest.approx(T_HAND, rel=1e-4)
    assert T == pytest.approx(HP * eta * 168.0 / V, rel=1e-12)       # T = 550 eta P / V


def test_thrust_and_power_directions_agree():
    for shp, v in ((450.0, 119.4), (130.5, 235.5), (82.1, 163.8), (450.0, 30.0)):
        T = prop.thrust_from_power(shp, disk(), v)
        assert prop.shaft_hp(T * v, v, disk()) == pytest.approx(shp, rel=1e-9)


def test_flat_eta_is_the_old_formula():
    assert prop.thrust_from_power(450.0, 0.8, 100.0) == HP * 450.0 * 0.8 / 100.0
    assert prop.shaft_hp(5000.0, 100.0, 0.8) == 5000.0 / (HP * 0.8)
    assert prop.efficiency_at_power(0.8, 450.0, 100.0) == 0.8
    assert prop.efficiency_for_thrust(0.8, 300.0, 100.0) == 0.8


def test_static_thrust_limit_of_the_m250_disk():
    # 450 hp, sea level, D 6.909 ft: A = 37.49 ft^2, (2 rho A)^(1/3) = 0.5628, (550 x 450)^(2/3) = 3,942,
    # product 2,218 lb (the review's 2,218 lb)
    T = prop.static_thrust_limit(450.0, RHO0, 6.909)
    assert T == pytest.approx(2218.0, abs=2.0)
    # the defining relation of momentum theory, P = T^(3/2)/sqrt(2 rho A)
    area = math.pi * 6.909 ** 2 / 4.0
    assert T ** 1.5 / math.sqrt(2.0 * RHO0 * area) == pytest.approx(HP * 450.0, rel=1e-9)


def test_real_thrust_at_low_speed_stays_below_the_momentum_limit():
    a = prop.ActuatorDisk(RHO0, 6.909, F)
    limit = prop.static_thrust_limit(450.0, RHO0, 6.909)
    for v in (1.0, 5.0, 20.0, 60.0, 119.4):
        t = a.efficiency_and_thrust(450.0, v)[1]
        assert t < limit
    # at the lowest speed the real thrust tends to f^(2/3) of the limit
    assert a.efficiency_and_thrust(450.0, 0.5)[1] == pytest.approx(F ** (2.0 / 3.0) * limit, rel=2e-3)


def test_propeller_selects_the_model_by_the_ledger():
    L = uav.load_ledger()[0]
    assert L["propeller_model"] == "app_l"
    assert isinstance(prop.propeller(L, RHO, D), prop.ActuatorDisk)
    assert prop.propeller(dict(L, propeller_model="flat"), RHO, D) == L["eta_p"]
    assert prop.propeller({"eta_p": 0.8}, RHO, D) == 0.8                # a ledger with no line is flat
    with pytest.raises(ValueError):
        prop.propeller(dict(L, propeller_model="blade_element"), RHO, D)


def test_rate_of_climb_uses_the_thrust_from_the_disk():
    W, S, CD0, K = 3000.0, 150.0, 0.03, 0.05
    a = prop.ActuatorDisk(RHO0, 6.909, F)
    T = prop.thrust_from_power(450.0, a, 119.4)
    hand = 119.4 * (T - perf.drag(W, S, RHO0, 119.4, CD0, K)) / W
    assert perf.rate_of_climb(W, S, RHO0, 119.4, CD0, K, 450.0, a) == pytest.approx(hand, rel=1e-12)
    # and it is less than the flat 0.80 gives at this speed, where the disk loading is high
    assert perf.rate_of_climb(W, S, RHO0, 119.4, CD0, K, 450.0, a) < perf.rate_of_climb(
        W, S, RHO0, 119.4, CD0, K, 450.0, 0.8)


def test_takeoff_thrust_is_capped_at_the_momentum_limit():
    L = uav.load_ledger()[0]
    bhp, Dp = 450.0, 6.909
    limit = prop.static_thrust_limit(bhp, RHO0, Dp)
    flat = uav._thrust_fn(bhp, dict(L, propeller_model="flat"), Dp)
    new = uav._thrust_fn(bhp, L, Dp)
    # old: static C_T/C_P thrust 2.5 x 550 x 450/(33.83 rev/s x 6.909 ft) = 2,647 lb, above the limit
    assert flat(0.0) == pytest.approx(2647.0, abs=2.0)
    assert flat(0.0) > limit
    assert new(0.0) < limit
    assert new(0.0) == pytest.approx(0.85 ** (2.0 / 3.0) * limit, rel=1e-2)    # evaluated at 1 ft/s
    # lower thrust than the flat model along the whole take-off run
    assert all(new(v) < flat(v) for v in (0.0, 30.0, 60.0, 90.0))


def test_flat_model_leaves_the_sizing_functions_as_before():
    L = dict(uav.load_ledger()[0], propeller_model="flat")
    sl = isa(0.0)
    assert uav._propeller(L, sl, 6.909) == L["eta_p"]
    # _min_power_for with a number is (W V_v + D V)/(550 eta) minimised over speed, divided by the lapse
    W, S = 3000.0, 150.0
    hp = uav._min_power_for(W, S, sl, 0.03, 0.05, 0.8, 1000.0 / 60.0, 1.0, 1.5, L)
    V_lo = L["climb_speed_over_stall"] * perf.stall_speed(W / S, sl["rho"], 1.5)
    best = min((W * 1000.0 / 60.0 + perf.drag(W, S, sl["rho"], V_lo + i, 0.03, 0.05) * (V_lo + i)) / (HP * 0.8)
               for i in range(400))
    assert hp == pytest.approx(best, rel=1e-12)


def test_app_l_needs_more_power_for_the_same_climb():
    L = uav.load_ledger()[0]
    sl = isa(0.0)
    args = (3000.0, 150.0, sl, 0.03, 0.05)
    flat = uav._min_power_for(*args, 0.8, 1000.0 / 60.0, 1.0, 1.5, L)
    new = uav._min_power_for(*args, uav._propeller(L, sl, 6.909), 1000.0 / 60.0, 1.0, 1.5, L)
    assert new > flat


def test_ledger_bands_the_real_to_ideal_factor():
    from measurement import info_gap
    L, entries = uav.load_ledger()
    names = [v["name"] for v in info_gap.uncertain_variables(entries)]
    assert "prop_real_to_ideal" in names
    q = entries["prop_real_to_ideal"]
    assert q["band"][0] <= q["value"] <= q["band"][1]
    assert "source" in q and "Mattingly" in q["source"]


# ---- records made before the ruling carry no propeller_model and rebuild as flat -------------------------------
@pytest.mark.parametrize("record", [
    "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json",
    "runs/task12/stage1/2026-11-23/design_pusher.json",
    "runs/task12/stage1/2026-11-21f/design_pusher.json",
])
def test_old_records_rebuild_as_flat_to_rounding(record):
    from pathlib import Path
    from measurement import stage3_perf as sp
    path = Path(__file__).resolve().parents[2] / record
    if not path.exists():
        pytest.skip(f"{record} not in this checkout")
    d, L, b, _, check = sp.rebuild(path)
    assert "propeller_model" not in L                       # the record's ledger copy predates the switch
    for name, pair in check.items():
        assert pair["rebuilt"] == pytest.approx(pair["record"], rel=1e-9), name

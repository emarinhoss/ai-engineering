"""Sizing methods against Raymer's DR-1 worked example (ch. 21.2, p. 564-568, 586-591).

Each assertion reproduces a printed value; the page is in the test name or comment. Printed values
are rounded, so tolerances are half a unit of the last printed digit unless stated.
"""
import math

import pytest

from conceptual import sizing
from conceptual.units import KT, NM


def test_table62_homebuilt_coefficient_p566():
    # printed: .59 W0^-.1 (6)^.05 (1/8)^.1 (10.2)^-.05 (130)^.17 = 1.093 W0^-.1. With 130 the
    # product is 1.068; the printed 1.093 is what 130 kt = 149.6 mph gives, the unit of the
    # Table 6.2 heading. So the book wrote knots and computed in mph.
    W0 = 1000.0
    frac = sizing.empty_fraction_table62(W0, "homebuilt_composite", 6.0, 1.0 / 8.0, 10.2,
                                         130.0 * 1.151)
    assert frac / W0 ** -0.1 == pytest.approx(1.093, abs=0.0005)
    as_written = sizing.empty_fraction_table62(W0, "homebuilt_composite", 6.0, 1.0 / 8.0, 10.2, 130.0)
    assert as_written / W0 ** -0.1 == pytest.approx(1.068, abs=0.0005)


def test_lift_to_drag_p566():
    assert sizing.lift_to_drag(35.0, 0.02, 9.7, 6.0, 0.8) == pytest.approx(11.04, abs=0.005)


def test_cruise_fraction_p566():
    f = sizing.cruise_fraction_prop(280 * 6076, 0.5, 0.8, 11.04)
    assert f == pytest.approx(0.953, abs=0.0005)


def test_fuel_fraction_p566():
    wx, wf = sizing.fuel_fraction([0.97, 0.985, 0.953, 0.995])
    assert wx == pytest.approx(0.906, abs=0.0005)
    assert wf == pytest.approx(0.0997, abs=0.0001)   # 1.06 (1 - .906) = .0996; printed .0997


def test_rubber_engine_sizing_p567():
    # printout: WOdrawn 1200, WEdrawn 883, exponent -.1, crew 220, fractions .97 .985 .953 .995;
    # last printed row WOG 1289.2, WOCALC 1290.4: the converged value lies between them
    _, wf = sizing.fuel_fraction([0.97, 0.985, 0.953, 0.995])
    W0, hist = sizing.solve_takeoff_weight(
        220.0, wf, lambda W: sizing.empty_fraction_drawn(W, 883.0, 1200.0, -0.1), 1200.0)
    printed = [(1200.0, 119.6, 883.0, 1222.6), (1218.1, 121.4, 895.0, 1236.3),
               (1232.7, 122.8, 904.6, 1247.4)]
    for row, ref in zip(hist, printed):
        assert row == pytest.approx(ref, abs=0.06)
    assert hist[14][0] == pytest.approx(1289.2, abs=0.1)      # the 15th and last printed row
    assert hist[14][3] == pytest.approx(1290.4, abs=0.1)
    assert W0 == pytest.approx(1293.8, abs=0.2)               # fixed point, beyond the printout


def test_fixed_engine_sizing_p568():
    # W0 held at the drawn 1200 lb gives W4/W0 = .925, then W3/W2 = .973 and R = 158 nm
    wx = sizing.solve_mission_fraction_for_weight(
        220.0, lambda W: sizing.empty_fraction_drawn(W, 883.0, 1200.0, -0.1), 1200.0)
    assert wx == pytest.approx(0.925, abs=0.0015)
    w32 = 0.925 / (0.97 * 0.985 * 0.995)
    assert w32 == pytest.approx(0.973, abs=0.0005)
    R = sizing.range_from_fraction_prop(0.973, 0.5, 0.8, 11.04)
    assert R == pytest.approx(957300, rel=0.002)
    assert R / 6076 == pytest.approx(158, abs=0.5)


def test_refined_takeoff_and_climb_p586():
    assert sizing.takeoff_fraction_power(0.5, 150, 5, 1200) == pytest.approx(0.995, abs=0.0005)
    dhe = sizing.energy_height_change(0, 80 * 1.689, 8000, 115 * 1.689)
    assert dhe == pytest.approx(8302, abs=1.0)
    C = sizing.equivalent_tsfc(0.5, 80 * 1.689, 0.78 * 0.95)
    assert C == pytest.approx(0.17, abs=0.005)
    assert sizing.climb_fraction_energy(0.17, 8302, 80 * 1.689, 0.32) == pytest.approx(0.996, abs=0.0005)


def test_refined_cruise_and_fuel_p587():
    LD = sizing.lift_to_drag(35.0, 0.0277, 10.1, 6.0, 0.87)
    assert LD == pytest.approx(8.8, abs=0.05)
    f = sizing.cruise_fraction_prop(280 * 6076, 0.5, 0.78 * 0.95, 8.8)
    assert f == pytest.approx(0.936, abs=0.0005)
    wx, wf = sizing.fuel_fraction([0.995, 0.996, 0.936, 0.995])
    assert wx == pytest.approx(0.923, abs=0.0005)
    assert wf == pytest.approx(0.0817, abs=0.0001)


@pytest.mark.parametrize("WS, A, e, CD0, LD, w32, W0_printed", [
    (8.09, 4, 0.93, 0.0250, 7.8, 0.928, 1278),     # case 1, p. 589-590
    (10.1, 4, 0.93, 0.0277, 8.29, 0.932, 1117),    # case 2, p. 591 (printed matrix value)
])
def test_carpet_cases(WS, A, e, CD0, LD, w32, W0_printed):
    assert sizing.lift_to_drag(35.0, CD0, WS, A, e) == pytest.approx(LD, abs=0.05)
    assert sizing.cruise_fraction_prop(280 * 6076, 0.5, 0.78 * 0.95, LD) == pytest.approx(w32, abs=0.0006)


def test_case2_resize_p591():
    _, wf = sizing.fuel_fraction([0.995, 0.996, 0.932, 0.995])
    W0, _ = sizing.solve_takeoff_weight(
        220.0, wf, lambda W: sizing.empty_fraction_drawn(W, 854.0, 1200.0, -0.1), 1200.0)
    _, hist = sizing.solve_takeoff_weight(
        220.0, wf, lambda W: sizing.empty_fraction_drawn(W, 854.0, 1200.0, -0.1), 1200.0)
    assert hist[0][3] == pytest.approx(1177.0, abs=0.06)
    assert hist[-1][0] < 1118.9                               # printout stops at 1118.9 -> 1117.9
    assert W0 == pytest.approx(1115.3, abs=0.2)


def test_does_not_close_raises():
    with pytest.raises(ValueError):
        sizing.solve_takeoff_weight(500.0, 0.5, 0.6, 2000.0)


def test_loiter_fraction_matches_closed_form():
    # (6.15) with time and speed: one hour at 200 ft/s, C_bhp 0.6, eta 0.8, L/D 15
    f = sizing.loiter_fraction_prop(3600.0, 200.0, 0.6, 0.8, 15.0)
    assert f == pytest.approx(math.exp(-200.0 * 0.6 / (550 * 0.8 * 15.0)), rel=1e-12)
    assert KT > 0 and NM > 0

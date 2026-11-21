"""Anderson, Aircraft Performance and Design: Stage 3 methods against printed values."""
import math

import pytest

from measurement import anderson as a

RHO_SL = 0.002377
RHO_30K = 8.9068e-4


def test_first_weight_estimate_p402_405():
    ff = a.fuel_fraction([0.97, 0.985, 0.893, 1.0, 0.995])          # (8.19)-(8.20)
    assert ff == pytest.approx(0.159, abs=0.0015)     # 0.1601; the book rounds W5/W0 to 0.85 first
    W0 = a.takeoff_weight(170 + 970, 0.159, a.EMPTY_FRACTION_HISTORICAL)
    assert W0 == pytest.approx(5158, abs=1)                           # (8.23)


def test_cruise_fraction_p404():
    f = a.breguet_cruise_fraction(6.64e6, 2.02e-7, 0.85, 14)
    assert f == pytest.approx(0.893, abs=0.0005)                     # (8.16)
    assert a.cbhp_to_c(0.4) == pytest.approx(2.02e-7, rel=0.001)      # (8.12)


def test_buildup_iteration_p451_453():
    areas = (148.0, 35.3, 14.4, 306.3)
    rows = a.iterate_buildup(1140.0, 0.159, areas, 547.0, 5158.0)
    assert rows[0][0] == pytest.approx(2474, abs=1)                   # W_e, first pass
    assert rows[0][2] == pytest.approx(4434, abs=1)                   # (8.84)
    assert rows[1][2] == pytest.approx(4205, abs=1)
    assert rows[-1][2] == pytest.approx(4100, abs=2)                  # converged
    assert rows[-1][0] / rows[-1][2] == pytest.approx(0.56, abs=0.005)


def test_example_5_4_optima_p223_224():
    CD0, K, WS = 0.015, 0.08, 76.84
    assert a.cl32_cd_max(CD0, K) == pytest.approx(10.83, abs=0.005)
    assert a.ld_max(CD0, K) == pytest.approx(14.43, abs=0.005)
    assert a.speed_cl32_cd_max(WS, RHO_30K, CD0, K) == pytest.approx(479.6, abs=0.1)
    assert a.speed_ld_max(WS, RHO_30K, CD0, K) == pytest.approx(631.2, abs=0.1)
    assert a.speed_cl12_cd_max(WS, RHO_30K, CD0, K) == pytest.approx(830.8, abs=0.1)


def test_climb_power_p415():
    # (8.45a): eta P/W = 16.67 + 14.26 = 30.93 ft/s with K 0.075, CD0 0.017, W/S 29.3, L/D 14
    rc = a.max_rate_of_climb_prop(30.93, 29.3, RHO_SL, 0.017, 0.075)
    # the book rounds (L/D)max to 14; with sqrt(1/(4 CD0 K)) = 14.0 the result is within rounding
    assert rc == pytest.approx(16.67, abs=0.1)


def test_turn_examples_p331_333():
    assert a.min_turn_radius(0.08, 76.84, RHO_SL, 0.3795, 0.015, g=32.2) == pytest.approx(861, abs=1)
    assert a.max_turn_rate(0.08, 76.84, RHO_SL, 0.3795, 0.015, g=32.2) == pytest.approx(0.25, abs=0.005)


def test_corner_speed_p344():
    assert a.corner_speed(4.5, 76.84, RHO_SL, 1.2) == pytest.approx(492.4, abs=0.1)


def test_endurance_169_matches_integral():
    import math
    # (5.169) equals the numeric integral of (5.168) at constant C_L^{3/2}/C_D
    eta, c, rho, S, k, W0, W1 = 0.8, a.cbhp_to_c(0.6), 0.0012673, 180.0, 12.0, 2800.0, 2100.0
    n, tot = 20000, 0.0
    for i in range(n):
        W = W1 + (W0 - W1) * (i + 0.5) / n
        tot += eta / c * math.sqrt(rho * S / 2) * k * W ** -1.5 * (W0 - W1) / n
    assert a.endurance_s(eta, c, rho, S, k, W0, W1) == pytest.approx(tot, rel=1e-6)


# ---- take-off and landing, Examples 6.6 and 6.7 (p. 364-375) ---------------------------------
def test_ground_effect_factor_p365():
    assert a.ground_effect_factor(5.6 / 75.0) == pytest.approx(0.588, abs=0.001)    # (6.77)


def test_gear_increment_p365():
    ws_si = 73000 * 4.448 / (950 * 0.3048 ** 2)
    assert ws_si == pytest.approx(3679, abs=2)
    assert a.gear_cd0_increment(ws_si, 73000 * 0.4536, 4.5e-5) == pytest.approx(0.0177, abs=0.0002)


def test_takeoff_example_66_p365_367():
    # Gulfstream-like: W 73,000 lb, W/S 76.84, CLmax 1.86, mu_r 0.04, 35-ft obstacle, N = 3 s
    V_s = a.stall_speed(76.84, 0.002377, 1.86)
    assert V_s == pytest.approx(186.4, abs=0.1)
    V_LO = 1.1 * V_s
    K_T = 24875.0 / 73000.0 - 0.04
    assert K_T == pytest.approx(0.301, abs=0.001)
    # printed K_A, from the printed bracket 0.015 + 0.0177 + [0.02 + 0.588/(pi 0.9 5.92)] 0.01 - 0.004
    k_ind = 0.02 + 0.588 / (math.pi * 0.9 * 5.92)
    K_A = a.takeoff_K_A(76.84, 0.002377, 0.015 + 0.0177, k_ind, 0.1, 0.04)
    assert K_A == pytest.approx(-4.525e-7, rel=0.01)                                  # (6.86)
    s_g = a.takeoff_ground_roll(K_T, K_A, V_LO, 3.0, g=32.2)
    assert s_g == pytest.approx(2857, abs=5)                                          # (6.90)
    R, theta, s_a = a.takeoff_airborne(V_s, 35.0, g=32.2)
    assert R == pytest.approx(7510, abs=10)
    assert math.degrees(theta) == pytest.approx(5.534, abs=0.01)
    assert s_a == pytest.approx(724, abs=2)
    assert s_g + s_a == pytest.approx(3581, abs=8)


def test_landing_example_67_p374_375():
    V_s = a.stall_speed(76.84, 0.002377, 2.39)
    assert V_s == pytest.approx(164.5, abs=0.1)
    R, h_f, s_a, s_f = a.landing_approach(1.23 * V_s, 50.0, math.radians(3.0), g=32.2)
    assert R == pytest.approx(6354.9, abs=5)
    assert h_f == pytest.approx(8.71, abs=0.02)
    assert s_a == pytest.approx(788, abs=2)
    assert s_f == pytest.approx(333, abs=1)
    k_ind = 0.02 + 0.588 / (math.pi * 0.9 * 5.92)
    J_T, J_A = a.landing_K_J(76.84, 0.002377, 0.015 + 0.0124, k_ind, 0.1, 0.4)
    assert J_T == pytest.approx(0.4)
    # the book prints +1.864e-7; its bracket is negative, so the sign is minus (flagged in the notes)
    assert J_A == pytest.approx(-1.864e-7, rel=0.01)
    s_g = a.landing_ground_roll(J_T, J_A, 1.15 * V_s, 3.0, g=32.2)
    assert s_g == pytest.approx(1969, abs=5)                                          # (6.119)
    assert s_a + s_f + s_g == pytest.approx(3090, abs=8)


def test_takeoff_and_landing_totals_run():
    t = a.takeoff_distance(3000.0, 200.0, 0.002377, 0.05, 0.06, 1.8, 600.0, 0.03, 0.1)
    assert t["total"] == pytest.approx(t["ground_roll"] + t["airborne"])
    ld = a.landing_distance(3000.0, 200.0, 0.002377, 0.05, 0.06, 2.1, 0.5, 0.1, math.radians(3.0))
    assert ld["total"] > ld["approach"]

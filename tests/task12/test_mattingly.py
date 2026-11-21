"""Mattingly methods for Stage 3 against printed values (Aircraft Engine Design, 2nd ed.)."""
import math

import pytest

from measurement import mattingly as m


def test_supercruise_constraint_coefficients_p44():
    # (2.E3): T/W = (0.78/alpha){2.12e-4 (W/S) + 35.6/(W/S)} from K1 0.27, CD0 0.028, beta 0.78,
    # q 991.6 (Case 1, K2 = CDR = 0)
    for ws in (50.0, 100.0):
        tw = m.master_thrust_loading(ws, 991.6, 0.78, 1.0, 0.27, 0.0, 0.028)
        assert tw == pytest.approx(0.78 * (2.12e-4 * ws + 35.6 / ws), rel=2e-3)


def test_actuator_disk_limits_p609_613():
    # eta* >= 0.80 needs V_e/V_0 < 1.5, C_T* < 1.25 and C_P* < 1.56
    c = m.ideal_coefficients(0.80)
    assert c["Ve_over_V0"] == pytest.approx(1.5)
    assert c["C_T"] == pytest.approx(1.25)
    assert c["C_P"] == pytest.approx(1.5625)


def test_actuator_disk_inverse():
    rho, V, A = 0.002, 200.0, 10.0
    for eta in (0.6, 0.8, 0.95):
        T = m.ideal_coefficients(eta)["C_T"] * 0.5 * rho * V ** 2 * A
        assert m.actuator_disk_efficiency(T, rho, V, A) == pytest.approx(eta)


def test_turn_load_factor_216():
    assert m.turn_load_factor(0.0, 300.0) == 1.0
    assert m.turn_load_factor(32.174 / 300.0, 300.0) == pytest.approx(math.sqrt(2.0))


def test_loiter_and_cruise_reduce_to_breguet():
    # (3.37) with EF = (L/D)/TSFC equals Raymer's (3.8); (3.23) equals (3.6)
    assert m.loiter_fraction(0.5, 1 / 15.0, 3600.0) == pytest.approx(math.exp(-0.5 / 15.0))
    assert m.cruise_fraction(0.5, 1 / 15.0, 300.0 * 3600.0, 300.0) == pytest.approx(math.exp(-0.5 / 15.0))


def test_shaft_power_loading_matches_level_flight_power():
    # level flight, n = 1, Ps = 0: P = D V/(550 eta)
    W_S, q, V, K1, CD0, eta = 15.0, 30.0, 160.0, 0.04, 0.025, 0.8
    hpw = m.shaft_power_loading(W_S, q, V, 1.0, 1.0, K1, 0.0, CD0, eta)
    D_W = q * CD0 / W_S + K1 * W_S / q
    assert hpw == pytest.approx(D_W * V / (550 * eta))


# ---- take-off, worked example p. 41-43 -------------------------------------------------------
RHO_2000FT_HOT = 0.002047


def test_takeoff_example_coefficients_p43():
    # (2.E1): a = k^2 beta^2/(rho g CLmax) = 10.93 (alpha T/W = 1) and b = t_R k sqrt(2 beta/(rho CLmax))
    #         = 79.57, with k_TO 1.2, t_R 3 s, CLmax 2.0, rho 0.002047, g 32.17
    a = m.takeoff_ground_roll_thrust_limited(1.0, RHO_2000FT_HOT, 2.0, 1.2, 1.0, g=32.17)
    assert a == pytest.approx(10.93, abs=0.01)
    V1 = m.takeoff_V(1.0, RHO_2000FT_HOT, 2.0, 1.2)                  # V_TO for W/S = 1: b = 3 V_TO
    assert m.rotation_distance(V1, 3.0) == pytest.approx(79.57, abs=0.05)


@pytest.mark.parametrize("tw, ws_printed", [(0.4, 27.3), (0.8, 47.9), (1.2, 64.9), (2.4, 104.0)])
def test_takeoff_boundary_matrix_p43(tw, ws_printed):
    # TR = 1.00 row of the printed matrix: alpha_wet 0.6885, s_TO = 1500 ft, solved by (2.E2)
    alpha = 0.6885
    a = 10.93 / (alpha * tw)
    b, c = 79.57, 1500.0
    ws = ((-b + math.sqrt(b ** 2 + 4.0 * a * c)) / (2.0 * a)) ** 2
    assert ws == pytest.approx(ws_printed, rel=0.005)
    # and the module's (2.22) + (2.26) give the same 1500 ft at that wing loading
    s = (m.takeoff_ground_roll_thrust_limited(ws, RHO_2000FT_HOT, 2.0, 1.2, alpha * tw, g=32.17)
         + m.rotation_distance(m.takeoff_V(ws, RHO_2000FT_HOT, 2.0, 1.2), 3.0))
    assert s == pytest.approx(1500.0, rel=0.002)


def test_ground_roll_225_tends_to_222():
    # the book states (2.25) recovers (2.22) as xi -> 0 (p. 29): a consistency check, not a printed value
    args = (50.0, 0.002377, 1.8, 1.2, 0.4)
    full = m.takeoff_ground_roll(*args, mu=0.0, xi=1e-6)
    assert full == pytest.approx(m.takeoff_ground_roll_thrust_limited(*args), rel=1e-4)


def test_transition_needs_positive_n_minus_1():
    with pytest.raises(ValueError):
        m.transition_and_climb(100.0, 1.1, 0.1, 50.0)     # 0.8 (1.1)^2 - 1 < 0


def test_takeoff_power_meets_field_and_is_monotone():
    thrust_factory = lambda hp: (lambda V: min(0.8 * 550.0 * hp / max(V, 1.0), 12.0 * hp))
    args = (3000.0, 200.0, 0.002377, 0.05, 0.06, 1.8)
    hp = m.takeoff_power(2000.0, thrust_factory, *args)
    assert m.takeoff_distance(*args, thrust_factory(hp))["total"] == pytest.approx(2000.0, abs=1.0)
    assert m.takeoff_power(1500.0, thrust_factory, *args) > hp

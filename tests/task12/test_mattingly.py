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

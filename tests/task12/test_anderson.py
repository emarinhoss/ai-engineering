"""Anderson, Aircraft Performance and Design: Stage 3 methods against printed values."""
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

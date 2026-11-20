"""Methods with no printed worked value in the library notes (reviewer finding F8): each test checks
an identity, a limit or a cross-book consistency instead, and says so."""
import math

import pytest

from conceptual import geometry_sizing as geo
from conceptual import raymer_aero as aero
from conceptual import raymer_loads as loads
from conceptual import raymer_performance as perf
from conceptual import sizing
from conceptual.units import RHO0


def test_gust_alleviation_limits():
    # (14.6): K -> 0.88 as the mass ratio grows, K = 0 at mu = 0
    assert loads.gust_alleviation_subsonic(0.0) == 0.0
    assert loads.gust_alleviation_subsonic(1e9) == pytest.approx(0.88, rel=1e-6)


def test_gust_increment_linear_in_speed():
    # (14.4): Delta n proportional to V at fixed K
    n1, K1, _ = loads.gust_load_factor(20.0, 200.0, 30.0, 5.0, 4.0, RHO0)
    n2, K2, _ = loads.gust_load_factor(20.0, 400.0, 30.0, 5.0, 4.0, RHO0)
    assert K1 == K2
    assert (n2 - 1.0) == pytest.approx(2.0 * (n1 - 1.0))


def test_table_3_1_general_aviation_single():
    # Table 3.1 p. 13: 2.36 W0^-0.18
    assert sizing.empty_fraction_table31(2000.0, "general_aviation_single") == pytest.approx(
        2.36 * 2000.0 ** -0.18)


def test_table_10_4_against_mattingly_pt6a42():
    # cross-book check: Raymer's turboprop weight fit (Table 10.4 p. 224) at 850 bhp against the
    # PT6A-42's 391 lb in Mattingly Table C.1 p. 519; agreement within 10 % expected of a fit
    w = geo.turboprop_statistical(850.0)["weight_lb"]
    assert w == pytest.approx(391.0, rel=0.10)
    assert geo.turboprop_statistical(850.0)["in_range"]
    assert not geo.turboprop_statistical(150.0)["in_range"]


def test_flapped_clmax_identity():
    # (12.21): increment = delta cl (S_flapped/S_ref) cos(hinge sweep)
    assert aero.flapped_cl_max(1.35, 1.3, 0.6) == pytest.approx(1.35 + 0.78)
    assert aero.flapped_cl_max(1.35, 1.3, 0.6, math.radians(60)) == pytest.approx(1.35 + 0.39)


def test_fuselage_lift_factor():
    assert aero.fuselage_lift_factor(0.0, 30.0) == pytest.approx(1.07)


def test_takeoff_transition_geometry():
    # (17.104)-(17.108): R = V_TR^2/(0.2 g); when the obstacle is cleared in transition the
    # distance follows the circle
    out = perf.takeoff_distance(2000.0, 120.0, RHO0, 0.03, 0.04, 2.0, lambda V: 900.0)
    V_tr = 1.15 * out["V_stall"]
    R = V_tr ** 2 / (0.2 * 32.174)
    assert out["transition"] <= R
    assert out["total"] == pytest.approx(out["ground_roll"] + out["rotation"] + out["transition"]
                                         + out["climb"])


def test_far_landing_factor():
    out = perf.landing_distance(2000.0, 120.0, RHO0, 0.05, 0.04, 2.0)
    assert out["far_field_length"] == pytest.approx(1.666 * out["total"])


def test_max_level_speed_is_thrust_equals_drag():
    V = perf.max_level_speed(2000.0, 120.0, RHO0, 0.025, 0.04, 200.0, 0.8, 100.0, 900.0)
    assert 550 * 200 * 0.8 / V == pytest.approx(perf.drag(2000.0, 120.0, RHO0, V, 0.025, 0.04), rel=1e-4)


def test_best_climb_beats_neighbours():
    vv, V = perf.best_rate_of_climb(2000.0, 120.0, RHO0, 0.025, 0.04, 200.0, 0.8, 90.0, 400.0)
    for dv in (-10.0, 10.0):
        assert perf.rate_of_climb(2000.0, 120.0, RHO0, V + dv, 0.025, 0.04, 200.0, 0.8) <= vv

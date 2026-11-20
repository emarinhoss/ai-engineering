"""Tests for the methods the round-1 equation table listed without one. DR-1 printed values
(Raymer ch. 21.2) where the book gives one; otherwise an identity or an inverse."""
import math

import pytest

from conceptual import constraints, sizing
from conceptual import geometry_sizing as geo
from conceptual import raymer_aero as aero
from conceptual import raymer_loads as loads
from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import raymer_weights as wts

RHO_SL = 0.00238


def test_reynolds_dr1_fuselage_p571():
    assert aero.reynolds(RHO_SL, 169.0, 22.0, 0.37e-6) == pytest.approx(23.916e6, rel=0.002)


def test_equivalent_skin_friction_dr1_p565():
    assert aero.cd0_equivalent_skin_friction(0.0055, 3.5) == pytest.approx(0.02, abs=0.001)


def test_power_coefficient_dr1_p574():
    assert prop.power_coefficient(150.0, RHO_SL, 45.0, 70.0 / 12.0) == pytest.approx(0.06, abs=0.005)


def test_thrust_from_power_dr1_p575():
    # cruise point on DR-1's thrust plot: about 330 lb at 115 kt with eta 0.78
    assert prop.thrust_from_power(150.0, 0.78, 115 * 1.689) == pytest.approx(330.0, abs=5.0)


def test_helical_tip_speed_dr1_p569():
    assert geo.helical_tip_speed(194.0, 2700.0, 5.85) == pytest.approx(850.0, abs=1.0)


def test_wing_wetted_area_711():
    assert aero.wetted_area_wing(100.0, 0.12) == pytest.approx(203.94)
    assert aero.wetted_area_wing(100.0, 0.04) == pytest.approx(200.3)


def test_laminar_cf_and_blend():
    assert aero.cf_laminar(1e6) == pytest.approx(1.328e-3)
    turb = aero.cf_component(RHO_SL, 169.0, 4.67, 0.37e-6, 0.15, 2.08e-5, 0.0)
    assert turb == pytest.approx(aero.cf_turbulent(aero.reynolds(RHO_SL, 169.0, 4.67, 0.37e-6), 0.15))


def test_wetted_aspect_ratio():
    assert aero.wetted_aspect_ratio(30.0, 300.0) == pytest.approx(3.0)


def test_landing_relations_are_inverse():
    s = constraints.landing_distance(20.0, 1.0, 2.0, 600.0)
    assert constraints.ws_landing(s, 1.0, 2.0, 600.0) == pytest.approx(20.0)


def test_best_loiter_is_sqrt3_best_range():
    assert constraints.ws_best_loiter_prop(30, 0.02, 10, 0.8) == pytest.approx(
        math.sqrt(3) * constraints.ws_best_range_prop(30, 0.02, 10, 0.8))


def test_drag_to_weight_is_inverse_lift_to_drag():
    assert constraints.drag_to_weight(35, 0.0277, 10.1, 6, 0.87) == pytest.approx(
        1.0 / sizing.lift_to_drag(35, 0.0277, 10.1, 6, 0.87))


def test_hp_per_w_climb_inverts_rate_of_climb():
    W, S, V = 2000.0, 120.0, 150.0
    q = 0.5 * RHO_SL * V ** 2
    hpw = constraints.hp_per_W_climb(20.0, V, q, 0.025, W / S, 10, 0.8, 0.8)
    K = 1 / (math.pi * 10 * 0.8)
    assert perf.rate_of_climb(W, S, RHO_SL, V, 0.025, K, hpw * W, 0.8) == pytest.approx(20.0)


def test_speed_max_ld_gives_ld_max():
    CD0, A, e = 0.025, 10.0, 0.8
    K = 1 / (math.pi * A * e)
    V, CL = perf.speed_max_ld(20.0, RHO_SL, CD0, K)
    q = 0.5 * RHO_SL * V ** 2
    assert sizing.lift_to_drag(q, CD0, 20.0, A, e) == pytest.approx(0.5 * math.sqrt(math.pi * A * e / CD0))


def test_gust_mass_ratio_and_design_gust():
    mu = loads.gust_mass_ratio(20.0, RHO_SL, 4.0, 5.0)
    assert mu == pytest.approx(2 * 20.0 / (RHO_SL * 32.174 * 4.0 * 5.0))
    assert loads.design_gust_velocity(100, 150, 225) == 30.0
    assert loads.design_gust_velocity(225, 150, 225) == pytest.approx(15.0)
    assert loads.ultimate_load_factor(3.8) == pytest.approx(5.7)


def test_gear_and_hydraulics_scale():
    assert wts.hydraulics(2000.0) == pytest.approx(2.0)
    # (15.51): exponents 0.566 on N_l W_l and 0.845 on length
    r = wts.nose_gear(3.0, 4000.0, 30.0) / wts.nose_gear(3.0, 2000.0, 30.0)
    assert r == pytest.approx(2 ** 0.566)


def test_tyre_and_engine_scaling():
    t = geo.main_tyre_in(500.0)
    assert t["diameter"] == pytest.approx(1.51 * 500 ** 0.349)
    base = geo.turboprop_statistical(1000.0)
    same = geo.turboprop_scaled(base, 1000.0, 1000.0)
    assert same["weight_lb"] == pytest.approx(base["weight_lb"])
    double = geo.turboprop_scaled(base, 1000.0, 2000.0)
    assert double["weight_lb"] / base["weight_lb"] == pytest.approx(2 ** 0.803)

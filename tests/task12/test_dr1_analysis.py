"""Constraint, geometry, aerodynamic, propeller, weight, stability and performance methods against
Raymer's DR-1 (ch. 21.2, p. 564-601). Inputs are the printed inputs; book inconsistencies are
reproduced as printed and named in the comment."""
import math

import pytest

from conceptual import constraints
from conceptual import geometry_sizing as geo
from conceptual import raymer_aero as aero
from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import raymer_stability as stab
from conceptual import raymer_weights as wts
from conceptual.units import HP

RHO_SL = 0.00238          # Raymer's sea-level density in DR-1


# ---- constraints, p. 564-565 -------------------------------------------------------------
def test_stall_wing_loading_p565():
    assert constraints.ws_stall(RHO_SL, 50 * 1.689, 1.2) == pytest.approx(10.2, abs=0.05)


def test_takeoff_wing_loading_p565():
    cl_to = constraints.cl_takeoff(1.2)
    assert cl_to == pytest.approx(0.99, abs=0.005)
    assert constraints.ws_takeoff_prop(120, 1.0, 0.99, 1 / 8) == pytest.approx(14.9, abs=0.06)   # 14.85


def test_climb_wing_loading_p565():
    G = (1500 / 60) / (70 * 1.689)
    assert G == pytest.approx(0.212, abs=0.001)      # 0.2115, printed rounded up
    T_W = constraints.thrust_to_weight_prop(1 / 8, 70 * 1.689, 0.8)
    assert T_W == pytest.approx(0.465, abs=0.0005)
    assert constraints.ws_climb(0.465, 0.212, 16.6, 0.02, 6, 0.8) == pytest.approx(62, abs=0.5)


def test_cruise_wing_loading_p565():
    # 35 sqrt(pi 6 .8 .02) = 19.2; the book prints 20 (its arithmetic, 4 % high)
    assert constraints.ws_best_range_prop(35, 0.02, 6, 0.8) == pytest.approx(19.22, abs=0.01)


def test_statistical_power_loading_p564():
    hpw = constraints.hp_per_W_statistical(130 * 1.151, "homebuilt_composite")
    assert hpw == pytest.approx(0.069, abs=0.0005)


# ---- layout data, p. 569 ------------------------------------------------------------------
def test_wing_geometry_p569():
    w = geo.Trapezoid(118.0, 6.0, 0.4)
    assert w.span == pytest.approx(26.6, abs=0.05)
    # (7.6) gives 76.0 in; the book prints 75.6, but its own tip chord 30.4 = 0.4 x 76.0
    assert w.root_chord * 12 == pytest.approx(76.0, abs=0.1)
    assert w.tip_chord * 12 == pytest.approx(30.4, abs=0.1)
    assert w.mac * 12 == pytest.approx(56.0, abs=0.5)      # 56.5 from (7.8); printed 56
    assert w.mac_y * 12 == pytest.approx(68.4, abs=0.1)


def test_fuselage_and_tails_p569():
    L = geo.fuselage_length(1200, "homebuilt_composite")
    assert L == pytest.approx(18, abs=0.15)          # 17.9, printed 18
    arm = 0.6 * 18
    assert arm == pytest.approx(10.8)
    assert geo.vertical_tail_area(0.04, 26.6, 118, arm) == pytest.approx(11.6, abs=0.05)
    assert geo.horizontal_tail_area(0.5, 4.7, 118, arm) == pytest.approx(25.5, abs=0.2)
    vt = geo.Trapezoid(11.6, 1.5, 0.4)
    # a vertical tail's span is sqrt(A S) (one surface): 4.17 ft printed as 4.1
    assert geo.vertical_tail_span(11.6, 1.5) == pytest.approx(4.1, abs=0.1)
    ht = geo.Trapezoid(25.5, 4.0, 0.4)
    assert ht.span == pytest.approx(10.1, abs=0.05)
    assert ht.root_chord == pytest.approx(3.6, abs=0.05)
    assert ht.tip_chord == pytest.approx(1.4, abs=0.05)
    assert vt.area == 11.6


def test_propeller_diameter_p569():
    assert geo.propeller_diameter_statistical_in(150) == pytest.approx(77, abs=0.5)
    d = geo.max_diameter_for_tip_speed(194.0, 2700.0, 850.0)
    assert d == pytest.approx(5.85, abs=0.01)


# ---- aerodynamics, p. 571-573 ---------------------------------------------------------------
def test_lift_slope_p571():
    base = aero.lift_slope(6.0, 0.0, 0.95)
    assert base == pytest.approx(4.37, abs=0.005)
    assert aero.lift_slope(6.0, 0.0, 0.95, s_exposed_ratio=0.837, F=1.33) == pytest.approx(4.85, abs=0.03)


def test_max_lift_p571():
    assert aero.wing_cl_max(1.35) == pytest.approx(1.2, abs=0.02)


def test_skin_friction_and_form_factor_p571_572():
    assert aero.cf_turbulent(23916000, 0.15) == pytest.approx(0.0026, abs=0.00005)
    assert aero.form_factor_fuselage(6.38) == pytest.approx(1.25, abs=0.005)
    assert aero.cf_turbulent(5e6, 0.15) == pytest.approx(0.0034, abs=0.00005)
    assert aero.form_factor_wing(0.135, 0.3, 0.15) == pytest.approx(1.24, abs=0.005)
    assert aero.form_factor_wing(0.12, 0.3, 0.15) == pytest.approx(1.20, abs=0.005)
    assert aero.cf_turbulent(3e6, 0.15) == pytest.approx(0.0037, abs=0.00005)
    # cutoff Reynolds numbers, smooth paint k = 2.08e-5 ft: fuselage 22 ft -> 84,158,000
    assert aero.cutoff_reynolds_subsonic(22.0, 2.08e-5) == pytest.approx(84.158e6, rel=0.003)
    assert aero.cutoff_reynolds_subsonic(4.67, 2.08e-5) == pytest.approx(16.46e6, rel=0.003)


def test_cd0_buildup_p572():
    comps = [{"name": "fuselage", "cf": 0.0026, "ff": 1.25, "s_wet": 164.0},
             {"name": "wing", "cf": 0.0034, "ff": 1.24, "s_wet": 202.3},
             {"name": "tails", "cf": 0.0037, "ff": 1.20, "q": 1.10, "s_wet": 60.6}]
    # gear .0020 and open cockpit .0076 are added as D/q areas: .0020*118 and 1.8*.5
    cd0, parts = aero.cd0_buildup(comps, 118.0, misc_d_q=0.0020 * 118 + 1.8 * 0.5)
    assert parts["fuselage"] == pytest.approx(0.0046, abs=0.0001)    # 0.00452 from the printed inputs
    assert parts["wing"] == pytest.approx(0.0071, abs=0.00015)       # 0.00723; printed .0071
    assert parts["tails"] == pytest.approx(0.0025, abs=0.00005)   # .0023 plus 10 % for gaps
    assert cd0 == pytest.approx(0.0250, abs=0.0001)


def test_engine_drags_p573():
    assert aero.cooling_drag_area(150, 519, 1.0, 1.0) == pytest.approx(19.8, abs=0.05)
    assert aero.misc_engine_drag_area(150) / 118 == pytest.approx(0.0003, abs=0.00005)   # 0.00025


def test_span_efficiency_p573():
    e = aero.oswald_straight_wing(6.0)
    assert e == pytest.approx(0.87, abs=0.005)
    assert aero.induced_drag_factor(6.0, e) == pytest.approx(0.061, abs=0.0005)


@pytest.mark.parametrize("A, e_printed", [(4, 0.93), (8, 0.81)])    # carpet cases, p. 589-596
def test_span_efficiency_other_aspect_ratios(A, e_printed):
    assert aero.oswald_straight_wing(A) == pytest.approx(e_printed, abs=0.006)


# ---- propulsion, p. 574-575 -----------------------------------------------------------------
def test_advance_ratio_and_static_thrust_p574():
    n, D = 2700 / 60, 70 / 12
    assert prop.advance_ratio(115 * 1.689, n, D) == pytest.approx(0.74, abs=0.005)
    assert prop.static_thrust(2.5, 150, n, D) == pytest.approx(786, abs=1)


def test_propwash_p575():
    f = prop.propwash_factor(70 / 12, 1.0, 0.004 * 265)
    assert f == pytest.approx(0.95, abs=0.005)


def test_power_lapse_p584():
    sigma = 0.001869 / 0.002377       # 8,000 ft
    assert prop.piston_power_lapse(sigma) == pytest.approx(0.76, abs=0.005)


# ---- weights, p. 576 --------------------------------------------------------------------------
def test_ga_group_weights_p576():
    NzW = 9 * 1200
    assert wts.wing(118, 1.0, 6, 0.0, 45, 0.4, 0.135, 9, 1200) == pytest.approx(168, abs=1)
    # 20.7 from the printed inputs; printed 20
    assert wts.horizontal_tail(9, 1200, 45, 25.5, 0.12, 4, math.radians(10), 0.4) == pytest.approx(20, abs=1.0)
    # (15.48) as printed in DR-1: the aspect-ratio term uses 4 (the horizontal tail's) for the fin
    assert wts.vertical_tail(0, 9, 1200, 45, 11.6, 0.12, 4, math.radians(15), 0.4) == pytest.approx(15, abs=0.5)
    # (15.49) as printed: L_t = 140 and L/D = 190/25
    assert wts.fuselage(164, 9, 1200, 140, 190 / 25, 45) == pytest.approx(115, abs=1)
    assert wts.main_gear(3, 1200, 25) == pytest.approx(69, abs=0.5)
    assert wts.installed_engine(272) == pytest.approx(452, abs=1)
    assert wts.fuel_system(20, 0, 1) == pytest.approx(22, abs=0.5)
    assert wts.flight_controls(190 / 12, 26.6 / 12, 9, 1200) == pytest.approx(5, abs=0.5)
    assert wts.avionics(5) == pytest.approx(9.5, abs=0.05)
    assert wts.electrical(22, 9.5) == pytest.approx(73, abs=0.5)
    assert NzW == 10800


# ---- stability, p. 579-580 ---------------------------------------------------------------------
def test_fuselage_pitching_moment_p579():
    cma = stab.fuselage_cm_alpha_per_deg(0.008, 35, 234, 56, 118 * 144)
    assert cma == pytest.approx(0.002, abs=0.0005)   # 0.0024 from the printed inputs, printed .002


def test_neutral_point_and_margin_p580():
    # as printed, the tail area ratio is 11.6/118 (the vertical tail's area; flagged in the notes)
    Xnp = stab.neutral_point(4.85, 1.107, 0.12, 0.9, 11.6 / 118, 3.77, 0.62, 3.68)
    assert Xnp == pytest.approx(1.188, abs=0.0005)
    assert stab.static_margin(66.6 / 56, 64.5 / 56) == pytest.approx(0.04, abs=0.003)   # 0.0375
    assert stab.cm_alpha(4.85, 66.6 / 56, 64.5 / 56) == pytest.approx(-0.182, abs=0.001)


def test_stick_free_neutral_point_p580():
    Xnp = stab.neutral_point(4.85, 1.107, 0.12, 0.9 * 0.8, 11.6 / 118, 3.77, 0.62, 3.68)
    assert Xnp == pytest.approx(1.168, abs=0.0005)


def test_downwash_far_wake_is_above_the_chart():
    # stated limitation: the far-wake value 2 CLa/(pi A) exceeds Raymer's chart reading 0.38
    assert stab.downwash_gradient_lifting_line(4.85, 6) == pytest.approx(0.515, abs=0.001)
    assert stab.downwash_gradient_lifting_line(4.85, 6) > 0.38


# ---- performance, p. 584-601 --------------------------------------------------------------------
def test_stall_speed_p584():
    assert perf.stall_speed(10.2, RHO_SL, 1.2) == pytest.approx(84.5, abs=0.1)


def test_drag_table_p584():
    for V_kt, D_sl in [(60, 99), (80, 104), (100, 132), (120, 173), (140, 230)]:
        q = 0.5 * RHO_SL * (V_kt * 1.689) ** 2
        D = 118 * q * (0.0277 + 0.061 * (1200 / 118 / q) ** 2)
        assert perf.drag(1200, 118, RHO_SL, V_kt * 1.689, 0.0277, 0.061) == pytest.approx(D)
        assert D == pytest.approx(D_sl, rel=0.03)


def test_climb_constraint_case1_p599():
    D = perf.drag(1278, 1278 / 8.16, 2 * 19.1 / (75 * 1.689) ** 2, 75 * 1.689, 0.0250,
                  1 / (math.pi * 4 * 0.93))
    assert D == pytest.approx(122, abs=1)
    Vv = 75 * 1.689 * (360 - D) / 1278
    assert Vv == pytest.approx(23.6, abs=0.1)


def test_turn_load_factor_p601():
    n = math.sqrt((0.5236 * 100 * 1.689 / 32.2) ** 2 + 1)
    assert n == pytest.approx(2.92, abs=0.01)
    rate, n_sust = perf.sustained_turn_rate(345 / 1200, 10.2, 34, 0.0277, 1 / (math.pi * 6 * 0.87), 168.9)
    assert n_sust == pytest.approx(3.3, abs=0.05)       # case 5, as listed on p. 601
    assert rate > 0


def test_power_curve_minimum_lies_at_cl_sqrt_3cd0_over_k():
    V, CL = perf.speed_min_power(10.2, RHO_SL, 0.0277, 0.061)
    Pmin = perf.power_required_hp(1200, 118, RHO_SL, V, 0.0277, 0.061)
    for dv in (-5.0, 5.0):
        assert perf.power_required_hp(1200, 118, RHO_SL, V + dv, 0.0277, 0.061) > Pmin
    assert CL == pytest.approx(math.sqrt(3 * 0.0277 / 0.061))


def test_ground_roll_limit_without_aero():
    K_T, V = 400 / 1200 - 0.03, 100.0
    assert perf.ground_roll(K_T, -1e-9, 0.0, V) == pytest.approx(V ** 2 / (2 * 32.174 * K_T), rel=1e-4)
    assert perf.ground_roll(K_T, 0.0, 0.0, V) == pytest.approx(V ** 2 / (2 * 32.174 * K_T))
    assert HP == 550.0

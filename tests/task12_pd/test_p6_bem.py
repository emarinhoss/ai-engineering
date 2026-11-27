"""Preliminary design P6, blade-element propeller: acceptance tests written from the spec before the modules
(docs/specs/task12_preliminary_design.md, "P6. Blade-element propeller"). Tolerances are the spec's, or are fixed
here before any run where the spec gives none. Library targets (Mattingly App. L) are cited by equation and page.

Validation rows 1 to 4 are computed here. Row 5 (the measured propeller) and the aircraft rows are run by
prelim/p6_propeller.py and recorded; here only their verdict rules are tested, on made-up numbers, so that a failed
row stays a recorded failure and is not a red test that invites tuning (tests/task12_pd/test_p6_record.py checks
that the record tells the truth).
"""
import json
import math

import numpy as np
import pytest
import yaml

from conceptual import raymer_propulsion as prop
from conceptual.units import HP, RHO0, isa
from prelim import bem
from prelim import p6_propeller as p6

SRC = yaml.safe_load(p6.SOURCE.read_text())
TABLES = yaml.safe_load(p6.SECTIONS.read_text())
R0 = json.loads((p6.R0 / "design_pusher.json").read_text())


# ---------------------------------------------------------------- tolerances fixed before the run

def test_tolerances_and_bands_are_the_ones_fixed_in_the_spec():
    assert p6.TOL_ROW5 == 0.03 and p6.ETA_RANGE_MIN == 0.5 and p6.ROW5_ANGLES == (15, 25)
    assert p6.TOL_ETA_AIRCRAFT == 0.05 and p6.F_BAND == (0.80, 0.90)
    assert p6.TOL_FIG_L5 == SRC["library_figure"]["reading_uncertainty"] == 0.01
    assert p6.TOL_L19_FT == 0.05                         # the example prints the diameters to 0.1 ft
    assert p6.TOL_TABLE_L1_REL == 0.01                   # plus half a unit of the last printed digit
    assert p6.JUDGED_READING_UNCERTAINTY == 0.015
    L = p6.record_targets()
    assert L["eta"] == {"climb_sea_level": pytest.approx(0.7041, abs=5e-5), "cruise_out": pytest.approx(0.8073, abs=5e-5),
                        "loiter": pytest.approx(0.7733, abs=5e-5)}          # the report's section 10, from r0
    assert L["takeoff_thrust_min_lb"] == pytest.approx(1247.0, abs=0.5) and L["takeoff_f"] == 0.6
    assert L["diameter_ft"] == R0["propeller_diameter_ft"] and L["rpm"] == 2030.0 and L["f_ledger"] == 0.85


# ---------------------------------------------------------------- validation rows 1 to 4 (library targets)

@pytest.mark.parametrize("ve_over_v0", [1.0, 1.1, 1.5, 2.0, 3.7])
@pytest.mark.parametrize("phi_deg", [5.0, 30.0, 45.0, 80.0])
def test_row_1_element_efficiency_without_drag_and_swirl_is_the_ideal_efficiency(ve_over_v0, phi_deg):
    """(L.14) with gamma = 0, a' = 0 and the disk's a = (V_e/V_0 - 1)/2 from (L.5), p. 611, is (L.7), p. 612."""
    a = bem.axial_interference_of_disk(ve_over_v0)
    assert bem.element_efficiency(a, 0.0, math.radians(phi_deg), 0.0) == pytest.approx(bem.ideal_efficiency(ve_over_v0), rel=1e-12)


@pytest.mark.parametrize("lift_to_drag", [50.0, 10.0, 4.0])
def test_row_2_maximum_of_the_element_efficiency_is_at_45_deg_less_half_the_drag_angle(lift_to_drag):
    """(L.14) over the inflow angle peaks at 45 deg - gamma/2 with the value (L.15), p. 615."""
    gamma = math.atan(1.0 / lift_to_drag)
    a, a_rot = 0.25, 0.0                                              # (1 - a')/(1 + a) = 0.8, as Fig. L.5
    phi = np.radians(np.linspace(0.01, 89.99 - math.degrees(gamma), 200001))
    eta = np.array([bem.element_efficiency(a, a_rot, p, gamma) for p in phi[::50]])
    best = phi[::50][int(np.argmax(eta))]
    assert math.degrees(best) == pytest.approx(45.0 - math.degrees(gamma) / 2.0, abs=0.05)
    assert eta.max() == pytest.approx(bem.element_efficiency_max(a, a_rot, gamma), rel=1e-6)
    assert bem.element_efficiency(a, a_rot, math.radians(90.0) - gamma, gamma) == pytest.approx(0.0, abs=1e-12)


def test_row_2_plateau_of_fig_l5_within_the_reading_uncertainty():
    for row in p6.validation_row_2()["curves"]:
        assert abs(row["computed"] - row["reading_mean"]) <= p6.TOL_FIG_L5, row


def test_row_3_coefficient_definitions_are_the_standard_ones():
    """(L.18) and (L.20), p. 617-618, against rho n^3 D^5 and against r0's own J and C_P (Raymer (13.10), (13.11))."""
    hp, rpm, D, V = 450.0, 2030.0, 6.9, 150.0
    n = rpm / 60.0
    assert bem.power_coefficient_l18(hp, 1.0, rpm, D) == pytest.approx(HP * hp / (RHO0 * n ** 3 * D ** 5), rel=1e-3)
    assert bem.advance_ratio_l20(V, rpm, D) == pytest.approx(prop.advance_ratio(V, n, D), rel=1e-12)
    for name, pt in p6.operating_points().items():
        assert bem.advance_ratio_l20(pt["V_fps"], pt["rpm"], pt["D_ft"]) == pytest.approx(R0["propeller_points"][name]["J"], rel=1e-9)
        assert bem.power_coefficient_l18(pt["shaft_hp"], pt["sigma"], pt["rpm"], pt["D_ft"]) == pytest.approx(
            R0["propeller_points"][name]["C_P"], rel=1e-3)                       # (L.18) rounds rho0 (1000/60)^3 10^5/550 to 2000


def test_row_3_table_l1_is_compared_row_by_row_and_the_verdict_follows():
    """Table L.1, p. 619, D = 14 ft, N = 663.4 rpm; row D is not used (flagged in the notes). The verdict is not
    required to be a pass: it must follow from the numbers and the tolerance fixed above."""
    row = p6.validation_row_3()
    assert [r["label"] for r in row["rows"]] == ["A", "B", "C", "E"]
    for r in row["rows"]:
        atm = isa(r["altitude_ft"])
        assert r["J_computed"] == pytest.approx(r["mach"] * atm["a"] / (663.4 / 60.0 * 14.0), rel=1e-12)
        assert r["CP_computed"] == pytest.approx(r["hp"] / (2000.0 * atm["sigma"] * 0.6634 ** 3 * 1.4 ** 5), rel=1e-12)
        assert r["J_ok"] == (abs(r["J_computed"] - r["J_printed"]) <= 0.005 + 0.01 * r["J_printed"])
        assert r["CP_ok"] == (abs(r["CP_computed"] - r["CP_printed"]) <= 0.005 + 0.01 * r["CP_printed"])
    assert row["verdict"] == ("pass" if all(r["J_ok"] and r["CP_ok"] for r in row["rows"]) else "fail")


def test_row_4_static_thrust_correlation_reproduces_the_two_printed_diameters():
    """(L.19) and the example of p. 617: 15,000 lbf from 4,000 hp with four blades at sea level."""
    assert bem.static_diameter_l19(15000.0, 1.0, 4000.0, 4) == pytest.approx(15.0, abs=p6.TOL_L19_FT)
    assert bem.static_diameter_l19(7500.0, 1.0, 2000.0, 4) == pytest.approx(10.6, abs=p6.TOL_L19_FT)
    D = bem.static_diameter_l19(1800.0, 0.9, 450.0, 3)
    assert bem.static_thrust_l19(D, 0.9, 450.0, 3) == pytest.approx(1800.0, rel=1e-12)       # the same relation solved for F


def test_relative_mach_number_is_l16():
    assert bem.relative_mach(0.1, 0.2, math.radians(30.0)) == pytest.approx(1.1 * 0.2 / 0.5, rel=1e-12)


# ---------------------------------------------------------------- the source data

def test_section_tables_reproduce_the_reports_own_lift_to_drag_column():
    """The second reading of the hand-typed tables: C_L/C_D of each row against the printed L/D. Rounding of the
    printed C_L (0.0005) and C_D (0.00005) is allowed for. Three rows are the report's own inconsistencies."""
    known = {("X", 6.0), ("XII", -7.5), ("XIV", -10.5)}
    n = 0
    for s in TABLES["sections"]:
        assert s["reynolds"] > 3.5e6 and [r[0] for r in s["rows"]] == sorted(r[0] for r in s["rows"])
        for alpha, cl, cd, ld in s["rows"]:
            allowed = 0.0051 + 0.0005 / cd + abs(cl / cd) * 0.00005 / cd
            if (s["table"], alpha) in known:
                assert abs(cl / cd - ld) > allowed
            else:
                assert abs(cl / cd - ld) <= allowed, (s["table"], alpha)
            n += 1
    assert n == 110 and [s["thickness_ratio"] for s in TABLES["sections"]] == [0.04, 0.08, 0.10, 0.12, 0.16, 0.20]


def test_reading_rule_mean_of_two_readings_and_half_their_difference():
    v, u = p6.reading([0.5, 0.0761, 0.07605, 0.0762], floor=0.00015)        # eye on the tile and code
    assert v == pytest.approx(0.076075) and u == 0.00015
    v, u = p6.reading([0.5, 0.1188, None, 0.1214], floor=0.0006)            # no code reading: the first eye reading
    assert v == pytest.approx(0.1201) and u == pytest.approx(0.0013)


def test_blade_geometry_readings_are_consistent_with_the_blade_setting():
    """Two checks of the transcription that need no model: the pitch curve marked 25 deg gives 25 deg at 0.75R, and the
    curves marked 15 and 25 deg, read separately, differ by 10 deg at every radius (the blade turns as a whole)."""
    blade = p6.blade_5868_9()
    i = blade["x"].index(0.75)
    assert blade["beta_set25_deg"][i] == pytest.approx(25.0, abs=0.15)
    b15 = {r[0]: math.degrees(math.atan(p6.reading(r, 0.003)[0] / (math.pi * r[0]))) for r in SRC["blade_geometry"]["pitch_set_15"]}
    for x, b25 in zip(blade["x"], blade["beta_set25_deg"]):
        if x in b15:
            assert b25 - b15[x] == pytest.approx(10.0, abs=0.5), x
    assert blade["x"][0] == 0.2 and blade["x"][-1] == 0.95 and len(blade["x"]) == 16
    assert all(t is None for t, x in zip(blade["t_c"], blade["x"]) if x < 0.35) and blade["t_c"][i] == pytest.approx(0.0891, abs=5e-4)


def test_measured_efficiency_points_and_which_are_judged():
    for angle, n_rows in ((15, 10), (25, 12)):
        pts = p6.measured_efficiency(angle)
        assert len(pts) == n_rows and all(p["eta"] > p6.ETA_RANGE_MIN for p in pts)
        for p in pts:
            assert p["judged"] == (p["uncertainty"] <= p6.JUDGED_READING_UNCERTAINTY) and p["uncertainty"] >= 0.004
    assert [p["J"] for p in p6.measured_efficiency(25) if not p["judged"]] == [1.25]


# ---------------------------------------------------------------- section data of infinite span

def test_infinite_span_removes_the_induced_angle_and_drag():
    """alpha_0 = alpha - C_L/(pi e A), c_d = C_D - C_L^2/(pi e A): Anderson APD (2.15), p. 81, and the induced drag."""
    a0, cd0 = bem.infinite_span(6.0, 0.762, 0.0467, 6.0, 0.95)
    assert a0 == pytest.approx(6.0 - math.degrees(0.762 / (math.pi * 0.95 * 6.0)), rel=1e-12)
    assert cd0 == pytest.approx(0.0467 - 0.762 ** 2 / (math.pi * 0.95 * 6.0), rel=1e-12)
    assert bem.infinite_span(3.0, 0.0, 0.02, 6.0, 0.95) == (3.0, 0.02)


def test_section_lookup_interpolates_in_angle_and_thickness_and_flags_the_ends():
    sec = bem.Sections([{"t_c": 0.10, "alpha": [0.0, 10.0], "cl": [0.0, 1.0], "cd": [0.01, 0.03]},
                        {"t_c": 0.20, "alpha": [0.0, 10.0], "cl": [0.2, 1.2], "cd": [0.02, 0.04]}])
    assert sec.lookup(5.0, 0.10) == pytest.approx((0.5, 0.02, 0.0))
    assert sec.lookup(5.0, 0.15) == pytest.approx((0.6, 0.025, 0.0))
    assert sec.lookup(5.0, 0.30) == pytest.approx((0.7, 0.03, 0.0))            # thicker than the thickest: its data
    assert sec.lookup(5.0, None) == pytest.approx((0.7, 0.03, 0.0))            # no thickness read (the shank)
    cl, cd, outside = sec.lookup(13.0, 0.10)                                   # beyond the table: end values held, flagged
    assert (cl, cd) == pytest.approx((1.0, 0.03)) and outside == pytest.approx(3.0)
    assert sec.lookup(-2.0, 0.10)[2] == pytest.approx(-2.0)
    assert sec.alpha_for_cl(0.6, 0.15) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        sec.alpha_for_cl(2.0, 0.15)


def test_committed_sections_are_loaded_as_infinite_span_data():
    sec = p6.load_sections(0.95)
    assert [s["t_c"] for s in sec.tables] == [0.04, 0.08, 0.10, 0.12, 0.16, 0.20]
    row = TABLES["sections"][2]["rows"][8]                                      # U.S.N.P.S. 3 at 6 deg
    a0, cd0 = bem.infinite_span(row[0], row[1], row[2], 6.0, 0.95)
    cl, cd, outside = sec.lookup(a0, 0.10)
    assert (cl, cd, outside) == pytest.approx((row[1], cd0, 0.0))
    assert all(min(s["cd"]) > 0.0 for s in sec.tables)


# ---------------------------------------------------------------- strip theory

def simple_blade(n=24, hub=0.2):
    x = np.linspace(hub, 0.99, n)
    return {"x": x, "c_over_D": np.full(n, 0.06), "t_c": [0.10] * n}


def flat_plate(lift_to_drag=None):
    """A made-up section: lift 2 pi alpha, drag a fixed fraction of the lift's size (or none)."""
    def section(alpha_deg, t_c, mach):
        cl = 2.0 * math.pi * math.radians(alpha_deg)
        return cl, (abs(cl) / lift_to_drag if lift_to_drag else 0.0), 0.0
    return section


def helical_pitch(x, J, alpha_deg):
    return np.degrees(np.arctan(J / (math.pi * np.asarray(x)))) + alpha_deg


def test_prandtl_tip_loss_factor():
    assert bem.tip_loss(3, 0.9, math.radians(20.0)) == pytest.approx(
        2.0 / math.pi * math.acos(math.exp(-1.5 * 0.1 / (0.9 * math.sin(math.radians(20.0))))), rel=1e-12)
    assert bem.tip_loss(3, 0.9, math.radians(20.0)) == pytest.approx(0.5789, abs=5e-4)        # by hand
    assert bem.tip_loss(3, 0.3, math.radians(20.0)) > 0.99 and bem.tip_loss(2, 0.999, math.radians(20.0)) < 0.1
    assert bem.tip_loss(40, 0.9, math.radians(20.0)) > 0.999


def test_station_satisfies_the_momentum_balance_and_app_l_element_relations():
    """At the solved inflow angle the blade-element force equals the momentum change of the annulus (thrust and torque),
    the inflow angle is the one of Mattingly's Fig. L.4, and the station's efficiency V dF/(Omega dQ) is (L.14)."""
    V, rpm, D, B, rho = 150.0, 2000.0, 7.0, 3, 0.002
    omega, R = 2.0 * math.pi * rpm / 60.0, D / 2.0
    for x, beta in ((0.3, 50.0), (0.7, 28.0), (0.95, 20.0)):
        s = bem.solve_station(V, omega, R, B, rho, x, 0.06 * D, beta, 0.10, flat_plate(25.0), 0.0)
        r, a, ar, phi, F = x * R, s["a"], s["a_rot"], s["phi"], s["F"]
        assert math.tan(phi) == pytest.approx(V * (1.0 + a) / (omega * r * (1.0 - ar)), rel=1e-9)
        assert s["dT_dr"] == pytest.approx(4.0 * math.pi * r * rho * V ** 2 * (1.0 + a) * a * F, rel=1e-8)
        assert s["dQ_dr"] == pytest.approx(4.0 * math.pi * r ** 3 * rho * V * omega * (1.0 + a) * ar * F, rel=1e-8)
        gamma = math.atan2(s["cd"], s["cl"])
        assert V * s["dT_dr"] / (omega * s["dQ_dr"]) == pytest.approx(bem.element_efficiency(a, ar, phi, gamma), rel=1e-9)
        # (L.10), p. 614, for B blades
        assert s["dT_dr"] == pytest.approx(B * rho * ((1.0 + a) * V) ** 2 / (2.0 * math.sin(phi) ** 2) * math.cos(phi + gamma)
                                           / math.cos(gamma) * s["cl"] * 0.06 * D, rel=1e-9)
        assert s["mach"] == 0.0 and s["alpha_deg"] == pytest.approx(beta - math.degrees(phi))


def test_frictionless_propeller_stays_below_the_ideal_efficiency_of_its_disk():
    """Without section drag the strip theory still loses to swirl and to the tip; it cannot beat (L.7)/(L.8)."""
    blade, J, D, rpm, rho = simple_blade(), 0.8, 7.0, 2000.0, 0.002
    V = J * rpm / 60.0 * D
    r = bem.propeller(V, rpm, D, 3, rho, 1000.0, blade["x"], blade["c_over_D"], helical_pitch(blade["x"], J, 4.0), blade["t_c"], flat_plate())
    ideal = bem.ideal_efficiency_of_disk(r["thrust_lb"], rho, V, D)
    assert 0.9 * ideal < r["eta"] < ideal < 1.0
    assert r["eta"] == pytest.approx(r["J"] * r["C_T"] / r["C_P"], rel=1e-12) and r["J"] == pytest.approx(J)
    assert r["power_hp"] == pytest.approx(2.0 * math.pi * rpm / 60.0 * r["torque_lbft"] / HP, rel=1e-12)
    with_drag = bem.propeller(V, rpm, D, 3, rho, 1000.0, blade["x"], blade["c_over_D"], helical_pitch(blade["x"], J, 4.0), blade["t_c"], flat_plate(30.0))
    assert with_drag["eta"] < r["eta"] and with_drag["thrust_lb"] < r["thrust_lb"] and with_drag["power_hp"] > r["power_hp"]


def test_ideal_efficiency_of_a_disk_inverts_l8_and_matches_stage_1():
    rho, V, D, T = 0.0015, 150.0, 6.9, 300.0
    eta = bem.ideal_efficiency_of_disk(T, rho, V, D)
    assert 4.0 * (1.0 - eta) / eta ** 2 == pytest.approx(T / (0.5 * rho * V ** 2 * math.pi * D ** 2 / 4.0), rel=1e-12)   # (L.8), p. 612
    assert eta == pytest.approx(prop.ActuatorDisk(rho, D, 1.0).efficiency_for_thrust(T, V), rel=1e-12)


def test_static_thrust_is_computed_and_stays_below_the_momentum_limit():
    blade, D, rpm, rho = simple_blade(), 7.0, 2000.0, RHO0
    r = bem.propeller(0.0, rpm, D, 3, rho, 1116.0, blade["x"], blade["c_over_D"], np.full(len(blade["x"]), 12.0), blade["t_c"], flat_plate(30.0))
    assert r["eta"] == 0.0 and r["thrust_lb"] > 0.0
    assert r["thrust_lb"] < prop.static_thrust_limit(r["power_hp"], rho, D)


def test_a_station_without_a_solution_raises():
    """A section that always lifts backwards, at rest: no inflow angle balances the annulus (the residual is
    sin(phi)(1 - k) with k negative)."""
    def always_negative(alpha_deg, t_c, mach):
        return -1.5, 0.0, 0.0
    with pytest.raises(ValueError, match="station"):
        bem.solve_station(0.0, 100.0, 3.5, 3, 0.002, 0.5, 0.4, 5.0, 0.10, always_negative, 0.0)


def test_pitch_for_power_absorbs_the_shaft_power():
    blade, D, rpm, rho, V = simple_blade(), 7.0, 2000.0, 0.002, 180.0
    twist = helical_pitch(blade["x"], 0.8, 0.0)
    for hp in (80.0, 300.0):
        r = bem.pitch_for_power(hp, V, rpm, D, 3, rho, 1000.0, blade["x"], blade["c_over_D"], twist, blade["t_c"], flat_plate(40.0))
        assert r["power_hp"] == pytest.approx(hp, rel=1e-6)
    assert r["pitch_change_deg"] > 0.0
    with pytest.raises(ValueError, match="power"):
        bem.pitch_for_power(1.0e5, V, rpm, D, 3, rho, 1000.0, blade["x"], blade["c_over_D"], twist, blade["t_c"], flat_plate(40.0))


def test_design_twist_puts_every_station_at_the_design_lift_coefficient():
    sec, blade = p6.load_sections(0.95), simple_blade()
    D, rpm, rho, V = 7.0, 2000.0, 0.0013, 150.0
    beta = bem.design_twist(0.5, V, rpm, D, 3, rho, blade["x"], blade["c_over_D"], blade["t_c"], sec)
    r = bem.propeller(V, rpm, D, 3, rho, 1000.0, blade["x"], blade["c_over_D"], beta, blade["t_c"], sec.section())
    assert [s["cl"] for s in r["stations"]] == pytest.approx([0.5] * len(blade["x"]), abs=1e-6)


def test_activity_factor_is_raymer_13_14():
    """(13.14), p. 327: AF = (10^5/D^5) integral of c r^3 dr; for a constant chord from 0.15R to R it has a closed form."""
    x = np.linspace(0.15, 1.0, 2001)
    assert bem.activity_factor(x, np.full(x.size, 0.05)) == pytest.approx(1.0e5 / 16.0 * 0.05 * (1.0 - 0.15 ** 4) / 4.0, rel=1e-6)
    b = p6.aircraft_blade(p6.blade_ledger())
    assert bem.activity_factor(b["x"], b["c_over_D"]) == pytest.approx(100.0, rel=1e-9)
    lo = dict(p6.blade_ledger(), prop_activity_factor=90.0)
    assert bem.activity_factor(*[p6.aircraft_blade(lo)[k] for k in ("x", "c_over_D")]) == pytest.approx(90.0, rel=1e-9)


def test_stations_run_from_the_hub_to_just_inside_the_tip_with_geometry_interpolated():
    blade = p6.stations(p6.blade_5868_9(), hub=0.2)
    assert blade["x"][0] == 0.2 and 0.98 < blade["x"][-1] < 1.0 and np.all(np.diff(blade["x"]) > 0)
    i = int(np.argmin(np.abs(blade["x"] - 0.75)))
    assert blade["c_over_D"][i] == pytest.approx(p6.reading(SRC["blade_geometry"]["b_over_D"][11], 0.00015)[0], rel=1e-9)
    assert blade["t_c"][0] is None and blade["t_c"][-1] == pytest.approx(0.0822, abs=1e-3)      # held beyond the last reading


# ---------------------------------------------------------------- verdict rules (made-up numbers)

def test_row_5_verdict_is_the_largest_difference_over_the_judged_points():
    pts = [{"J": 0.5, "eta": 0.70, "uncertainty": 0.004, "judged": True, "computed": 0.72},
           {"J": 0.6, "eta": 0.75, "uncertainty": 0.004, "judged": True, "computed": 0.725},
           {"J": 0.7, "eta": 0.55, "uncertainty": 0.02, "judged": False, "computed": 0.30}]
    out = p6.row5_verdict({15: pts, 25: pts})
    assert out["largest_difference"] == pytest.approx(0.025) and out["verdict"] == "pass" and out["n_judged"] == 4
    pts[0]["computed"] = 0.74
    assert p6.row5_verdict({15: pts, 25: pts})["verdict"] == "fail"
    pts[0]["computed"] = None                                    # a point the model could not compute is a failure of the row
    assert p6.row5_verdict({15: pts, 25: pts})["verdict"] == "fail"


def test_aircraft_verdicts_follow_from_the_numbers():
    assert p6.verdict_eta(0.75, 0.7041) == "pass" and p6.verdict_eta(0.76, 0.7041) == "outside"
    assert p6.verdict_f(0.85) == "inside the band" and p6.verdict_f(0.80) == "inside the band"
    assert p6.verdict_f(0.79) == "finding: below the band" and p6.verdict_f(0.93) == "finding: above the band"
    assert p6.verdict_takeoff(1247.1, 1247.0) == "pass" and p6.verdict_takeoff(1200.0, 1247.0) == "fail"
    assert p6.used_in_r1("pass") is True and p6.used_in_r1("fail") is False
    pts = [{"point": "loiter", "verdict": "inside the band"}, {"point": "takeoff_0707_VTO", "verdict": "not computed"}]
    assert p6.row2_verdict(pts) == "inside the band at every computed point; not computed at takeoff_0707_VTO"
    pts[0]["verdict"] = "finding: below the band"
    assert p6.row2_verdict(pts) == "finding: outside the band at loiter; not computed at takeoff_0707_VTO"
    assert p6.row2_verdict(pts[:1]) == "finding: outside the band at loiter"

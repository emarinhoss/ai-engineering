"""Preliminary design P4 (spec docs/specs/task12_preliminary_design.md, 'P4. Balance and longitudinal stability'):
acceptance tests of the methods, written before the recorded run. Tolerances are the spec's (R13 0.05 to 0.15 MAC;
independent neutral point within 0.03 MAC of Stage 1's; nose-wheel load 5 to 20 %; VSPAERO converged if its
neutral point moves by at most 0.01 MAC between its two finest meshes) or are fixed here. No test requires an
acceptance row to pass: a failed row is recorded and reported. What is tested is that each method gives its
closed form or its printed value, that Stage 1's own numbers come back from r0's inputs, and that the PD-20
solution has the properties it claims.
"""
import copy
import json
import math

import numpy as np
import pytest

from conceptual import uav
from geometry3d import aircraft as ac
from geometry3d import gates
from prelim import p4_balance as p4
from prelim import p4_methods as m


@pytest.fixture(scope="module")
def ctx():
    return p4.context()


# ---- the source record -----------------------------------------------------------------------------------------
def test_sources_are_recorded_and_no_pdf_is_committed():
    src = m.load_yaml(m.SOURCES)
    for r in src["reports"].values():
        assert r["url"].startswith("https://ntrs.nasa.gov/api/citations/" + r["ntrs_id"])
        assert len(r["pdf_sha256"]) == 64 and r["pdf_committed"] is False and r["pdf_pages"] > 0
    assert not list((m.REPO / "data/task12").rglob("*.pdf"))
    assert "(3.7)" in m.fuselage_moment.__doc__ and "p. 11" in m.fuselage_moment.__doc__


def test_every_figure_was_read_twice_and_the_readings_agree():
    """The second (pixel) reading, interpolated at the first (eye) reading's abscissa, within twice the stated
    reading uncertainty (the interpolation between pixel points adds to it)."""
    src = m.load_yaml(m.SOURCES)
    f8, rib = src["multhopp"]["figure_8"], src["ribner"]
    pairs = [(f8["mean_first_reading"], f8["mean_second_reading"], f8["reading_uncertainty"]["mean"]),
             (f8["local_first_reading"], f8["local_second_reading"], f8["reading_uncertainty"]["local"]),
             (rib["figure_1"]["first_reading"], rib["figure_1"]["second_reading"], rib["figure_1"]["reading_uncertainty"]),
             (rib["figure_2"]["three_blades_first_reading"], rib["figure_2"]["three_blades_second_reading"], rib["figure_2"]["reading_uncertainty"])]
    n = 0
    for first, second, u in pairs:
        s = np.array(second)
        for x, v in first:
            if s[0, 0] <= x <= s[-1, 0]:
                assert abs(np.interp(x, s[:, 0], s[:, 1]) - v) <= 2.0 * u, (x, v)
                n += 1
    assert n >= 12
    f6 = rib["side_force_factor"]["figure_6"]
    s = np.array(f6["three_blades_second_reading"])
    slope_second = (s[-1, 1] - 1.0) / (s[-1, 0] - 80.7)
    slope_first = (f6["three_blades_first_reading"][1][1] - 1.0) / (f6["three_blades_first_reading"][1][0] - 80.7)
    assert abs(slope_second - slope_first) * (120.0 - 80.7) <= 2.0 * f6["reading_uncertainty"]


def test_figure_1_of_ribner_agrees_with_his_equation_12_on_the_actuator_disc():
    """f = (1 + a)[(1 + a) + (1 + 2a)^2] / [1 + (1 + 2a)^2] (WR L-25 (12)) with T_c = (pi/2) a (1 + a): a check of
    the reading, within 0.01 (the reading uncertainty)."""
    src = m.load_yaml(m.SOURCES)
    for Tc, f in src["ribner"]["figure_1"]["second_reading"]:
        a = 0.5 * (-1.0 + math.sqrt(1.0 + 8.0 * Tc / math.pi))
        f12 = (1 + a) * ((1 + a) + (1 + 2 * a) ** 2) / (1 + (1 + 2 * a) ** 2)
        assert abs(f - f12) <= 0.01, (Tc, f, f12)


# ---- Multhopp's integral ---------------------------------------------------------------------------------------
def test_slender_body_of_revolution_gives_munks_two_volumes():
    """With d(beta)/d(alpha) = 1 everywhere, (3.7) is (pi/2) integral b^2 dx = 2 Vol for a body of revolution
    (TM 1036 Fig. 2: (1/q) dM/d(alpha) = 2 (K2 - K1) Vol, K2 - K1 = 1 for a slender body). Ellipsoid a = 5, b = 0.5:
    Vol = (4/3) pi a b^2. The wing is put behind the tail end, so the whole body is 'ahead'."""
    a, b = 5.0, 0.5
    width = lambda x: 2.0 * b * np.sqrt(np.clip(1.0 - ((x - a) / a) ** 2, 0.0, None))
    out = m.fuselage_moment(width, 2 * a, 2 * a, 1.0, 2 * a + 2.0, 1.0, lambda xi: xi, n=4000)
    assert out["total_ft3"] == pytest.approx(2.0 * 4.0 / 3.0 * math.pi * a * b ** 2, rel=1e-6)
    assert out["behind_wing_ft3"] == 0.0


def test_figure_8_caption_and_the_rule_behind_the_wing():
    """Constant width B. Ahead of the wing out to x: integral b^2 d(beta)/d(alpha) dx = x B^2 times the mean
    (the caption of Fig. 8), here at the read point x/t = 0.55 (mean 2.219). Over the chord nothing. Behind: a
    linear rise to dah at the tail, then constant: B^2 dah ((x_tail - x_te)/2 + (length - x_tail))."""
    src = m.load_yaml(m.SOURCES)
    G = m.figure8_integral(src)
    B, chord = 2.0, 4.0
    x_le = 0.55 * chord
    out = m.fuselage_moment(lambda x: np.full_like(x, B), 20.0, x_le, chord, 15.0, 0.6, G)
    assert out["ahead_of_wing_ft3"] == pytest.approx(0.5 * math.pi * B ** 2 * x_le * 2.219, rel=1e-9)
    x_te = x_le + chord
    assert out["behind_wing_ft3"] == pytest.approx(0.5 * math.pi * B ** 2 * 0.6 * ((15.0 - x_te) / 2 + 5.0), rel=1e-9)
    # beyond the mean curve the local curve is added: the slope of G at x/t = 1.2 is the local reading there
    assert (G(1.21) - G(1.19)) / 0.02 == pytest.approx(np.interp(1.2, [1.1, 1.3], [1.156, 1.128]), abs=1e-9)
    # the conversion to another lift-curve slope scales the excess over 1 only
    assert m.figure8_integral(src, 2.0)(0.55) - 0.55 == pytest.approx(2.0 * (G(0.55) - 0.55))


# ---- neutral point ---------------------------------------------------------------------------------------------
def test_neutral_point_reproduces_stage_1_and_solves_16_8(ctx):
    d, L = ctx["d"], ctx["L"]
    lay = m.base_layout(d, ctx["p3"], "r0")
    st = m.stability(d, L, lay, ctx["body"], ctx["src"], Cma_fus=d["layout"]["Cma_fus"])
    assert st["dah_da"] == pytest.approx(d["layout"]["dah_da"], rel=1e-12)
    assert st["x_np_power_off_ft"] == pytest.approx(d["layout"]["x_np"], rel=1e-9)
    # with a propeller: (16.8) is zero at the neutral point, and the shift equals Ribner's (6) when his lift-curve
    # slope is the power-on denominator and his arm is measured from the power-off neutral point
    args = (5.3, 1.75, 0.35, 0.85, 4.0)
    Fp, dap, Xp = 0.02, 0.62, 4.7
    X = m.neutral_point(*args, Fp, dap, Xp)
    assert m.cm_alpha(X, *args, Fp, dap, Xp) == pytest.approx(0.0, abs=1e-12)
    X0 = m.neutral_point(*args)
    assert m.cm_alpha(X0, *args) == pytest.approx(0.0, abs=1e-12)
    ribner_aft_shift = Fp * dap * (Xp - X0) / (args[0] + args[3] + Fp * dap)
    assert X - X0 == pytest.approx(ribner_aft_shift, rel=1e-12)
    assert X > X0                                   # a propeller behind the centre of gravity is stabilising (Raymer p. 428)


def test_side_force_factor_and_normal_force_use_the_recorded_readings(ctx):
    assert m.side_force_factor(0.1, 0.1, 0.1) == pytest.approx(132.0)
    out = m.propeller_normal_force(0.0, 24.0, 80.7, ctx["src"])
    assert out["f"] == 1.0 and out["side_force_ratio"] == 1.0 and out["CY_psi"] == pytest.approx(0.1545)
    with pytest.raises(ValueError):
        m.propeller_normal_force(0.1, 10.0, 80.7, ctx["src"])       # blade angle below the read range: no extrapolation
    assert m.thrust_coefficient(100.0, 0.002, 100.0, 5.0) == pytest.approx(100.0 / (0.002 * 1e4 * 25.0))


# ---- balance: Stage 1's own numbers come back from r0's inputs ---------------------------------------------------
def test_stage_1_balance_trim_and_rotation_come_back(ctx):
    """With r0's stations, the fuel at Stage 1's station (0.40 of the mean chord) and the ledger's section moment,
    the functions give r0's recorded centres of gravity, nose loads, trim and rotation. A coding check."""
    d, L = ctx["d"], ctx["L"]
    lay, rec = m.base_layout(d, ctx["p3"], "r0"), d["layout"]
    it = m.items(d, L, lay, "down")
    for k, (w, x) in it.items():
        assert w == d["stations"][k]["weight"] and x == pytest.approx(d["stations"][k]["x"], rel=1e-12), k
    pay = (d["payload_lb"], lay["payload_x"])
    x_wing = lay["x_le"] + 0.40 * d["wing"]["mac"]
    W_full, cg_full = m.cg(it, pay, (d["fuel_lb"], d["fuel_lb"] * x_wing))
    W_empty, cg_empty = m.cg(it, pay)
    assert cg_full == pytest.approx(rec["cg_full"], rel=1e-9) and cg_empty == pytest.approx(rec["cg_empty"], rel=1e-9)
    assert W_full == pytest.approx(d["W0_lb"], abs=0.01)         # the record's weight statement closes to 0.002 lb
    assert m.nose_load(lay, cg_full) == pytest.approx(rec["nose_load"]["full"], rel=1e-9)
    assert m.nose_load(lay, cg_empty) == pytest.approx(rec["nose_load"]["empty"], rel=1e-9)
    assert m.tipback_deg(d, lay, max(cg_full, cg_empty)) == pytest.approx(L["tipback_angle_deg"], abs=1e-6)
    assert m.overturn_deg(d, lay, cg_full) == pytest.approx(L["overturn_max_deg"], abs=1e-6)
    assert m.propeller_clearance_in(d, L, lay) == pytest.approx(rec["prop_clearance_in"], rel=1e-9)
    cm_w = m.wing_moment(L["airfoil_cm0"], d["A"])
    assert cm_w == pytest.approx(rec["cm_wing"], rel=1e-12)
    rot = m.rotation(d, L, lay, min(cg_full, cg_empty), cm_w)
    for k in ("V_kt", "Cm_without_tail", "CL_tail_needed", "main_wheel_load_lb"):
        assert rot[k] == pytest.approx(rec["rotation"][k], rel=1e-8), k
    W_zf = d["W0_lb"] - d["fuel_lb"]
    for name, W, CL in m.trim_legs(d, L):
        x = (cg_empty * W_empty + (W - W_zf) * x_wing) / (W_empty + W - W_zf)       # as conceptual/uav.layout's cg_at
        assert CL == pytest.approx(rec["trim"][name]["CL_wing"], rel=1e-9)
        assert m.tail_cl_trim(d, L, lay, CL, x, cm_w) == pytest.approx(rec["trim"][name]["CL_tail"], rel=1e-8), name
    assert m.tail_rearmost(d, L, lay)["horizontal_tail"] - ctx["propeller_plane_x"] == pytest.approx(
        ctx["p3"]["gates"]["9"]["behind_plane_ft"]["horizontal_tail"], abs=0.01)
    assert m.tail_rearmost(d, L, lay)["vertical_tail"] - ctx["propeller_plane_x"] == pytest.approx(
        ctx["p3"]["gates"]["9"]["behind_plane_ft"]["vertical_tail"], abs=0.01)


def test_tanks_hold_the_fuel_and_the_orders_share_their_ends(ctx):
    d, L, tk = ctx["d"], ctx["L"], ctx["tanks"]
    assert sum(t["gross_ft3_per_side"] for t in tk["tanks"]) * 2 * L["wing_tank_usable"] == pytest.approx(d["fuel_volume_ft3"]["needed"], rel=1e-9)
    assert tk["tanks"][0]["gross_ft3_per_side"] == pytest.approx(tk["tanks"][1]["gross_ft3_per_side"], rel=1e-9)
    assert tk["tanks"][0]["y_from_ft"] == pytest.approx(0.5 * d["fuselage"]["diameter"]) and tk["tanks"][0]["y_to_ft"] == tk["tanks"][1]["y_from_ft"]
    assert tk["gross_ft3_per_side"] < tk["available_gross_ft3_per_side"]
    # the P3 record's tank volume, from the fuselage side to the end of the tank bay, by this module's integral
    assert tk["available_gross_ft3_per_side"] * 2 == pytest.approx(ctx["p3"]["gates"]["4"]["tank"]["gross_ft3"], rel=2e-3)
    # the inboard tank's chord is longer, and the leading edge is unswept: its centre is further aft
    assert tk["tanks"][0]["centre_behind_root_le_ft"] > tk["tanks"][1]["centre_behind_root_le_ft"]
    assert tk["spar_fractions"][0] < tk["centre_chord_fraction"] < tk["spar_fractions"][1]
    F, x_le = d["fuel_lb"], d["layout"]["x_le"]
    for order in ("outboard_first", "inboard_first"):
        assert m.fuel_state(0.0, F, tk, order, x_le) == (0.0, 0.0)
        assert m.fuel_state(F, F, tk, order, x_le)[1] == pytest.approx(
            0.5 * F * sum(x_le + t["centre_behind_root_le_ft"] for t in tk["tanks"]))
    half_out = m.fuel_state(0.5 * F, F, tk, "outboard_first", x_le)[1] / (0.5 * F)
    half_in = m.fuel_state(0.5 * F, F, tk, "inboard_first", x_le)[1] / (0.5 * F)
    assert half_out == pytest.approx(x_le + tk["tanks"][0]["centre_behind_root_le_ft"])
    assert half_in == pytest.approx(x_le + tk["tanks"][1]["centre_behind_root_le_ft"])


def test_loadings_cover_step_1(ctx):
    d, L, ch = ctx["d"], ctx["L"], ctx["choices"]
    rows = m.loadings(d, L, m.base_layout(d, ctx["p3"]), ctx["tanks"], ch)
    assert len(rows) == 2 * 3 * 2 * 2 * (ch["balance"]["fuel_steps"] + 1)
    full = m.pick(rows, gear="down", empty_weight_factor=1.0, payload_on=True, tank_order="outboard_first")[0]
    assert full["weight_lb"] == pytest.approx(d["W0_lb"], abs=0.01)
    on = m.pick(rows, gear="up", empty_weight_factor=1.0, payload_on=True, tank_order="outboard_first")
    off = m.pick(rows, gear="up", empty_weight_factor=1.0, payload_on=False, tank_order="outboard_first")
    assert all(b["x_cg_ft"] > a["x_cg_ft"] and a["weight_lb"] - b["weight_lb"] == pytest.approx(d["payload_lb"]) for a, b in zip(on, off))
    # the band multiplies the empty items only: the empty aircraft's centre of gravity does not move
    it = m.items(d, L, m.base_layout(d, ctx["p3"]), "up")
    assert m.cg(it, factor=1.05)[1] == pytest.approx(m.cg(it)[1], rel=1e-12)
    assert m.cg(it, factor=1.05)[0] == pytest.approx(1.05 * m.cg(it)[0], rel=1e-12)
    # P3's moment change, gear down, fuel at any one place: the shift of the centre of gravity P3 printed
    r0_it = m.items(d, L, m.base_layout(d, ctx["p3"], "r0"), "down")
    p3_it = m.items(d, L, m.base_layout(d, ctx["p3"]), "down")
    lay = m.base_layout(d, ctx["p3"])
    shift = m.cg(p3_it, (500.0, lay["payload_x"]))[1] - m.cg(r0_it, (500.0, d["stations"]["payload"]["x"]))[1]
    # (P3 divided by W0 less the fuel; the items sum to 0.002 lb less, the closure of the record's sizing loop)
    assert shift == pytest.approx(ctx["p3"]["moved_masses"]["cg_shift_zero_fuel_weight_ft"], rel=1e-5)


def test_forward_limits_are_where_the_tail_reaches_its_ledger_limits(ctx):
    d, L = ctx["d"], ctx["L"]
    lay = m.base_layout(d, ctx["p3"])
    cm_w = m.wing_moment(ctx["cm0_p2"], d["A"])
    f = m.forward_limits(d, L, lay, cm_w)
    assert m.rotation(d, L, lay, f["rotation_ft"], cm_w)["CL_tail_needed"] == pytest.approx(-L["tail_cl_max_rotation"], abs=1e-8)
    assert m.tail_cl_trim(d, L, lay, f["trim_CL"], f["trim_ft"], cm_w) == pytest.approx(-L["tail_cl_max_trim"], abs=1e-8)
    assert f["trim_CL"] == max(r[2] for r in m.trim_legs(d, L)) and f["forward_limit_ft"] == max(f["rotation_ft"], f["trim_ft"])
    # a more negative section moment asks more of the tail: the limit moves aft
    assert m.forward_limits(d, L, lay, m.wing_moment(L["airfoil_cm0"], d["A"]))["rotation_ft"] < f["rotation_ft"]
    assert ctx["cm0_p2"] == pytest.approx(m.val(ctx["choices"]["trim_and_rotation"]["airfoil_cm0"]), abs=1e-4)


# ---- PD-20 -----------------------------------------------------------------------------------------------------
def test_r1_solution_has_the_properties_pd20_states(ctx):
    d, L, ch = ctx["d"], ctx["L"], ctx["choices"]
    lay0 = m.base_layout(d, ctx["p3"])
    lay, st = m.solve_r1(d, L, lay0, ctx["tanks"], ch, ctx["body"], ctx["src"], ctx["propeller_plane_x"])
    clr = m.val(ch["r1"]["propeller_clearance_ft"])
    assert max(m.tail_rearmost(d, L, lay).values()) == pytest.approx(ctx["propeller_plane_x"] - clr, abs=1e-9)
    # both volume coefficients kept: area times arm unchanged
    assert lay["ht_area"] * lay["arm"] == pytest.approx(lay0["ht_area"] * lay0["arm"], rel=1e-12)
    assert lay["vt_area"] * lay["arm"] == pytest.approx(lay0["vt_area"] * lay0["arm"], rel=1e-12)
    assert lay["ht_area"] * lay["arm"] / (d["wing"]["area"] * d["wing"]["mac"]) == pytest.approx(L["c_ht"] * d["ht_volume_scale"], rel=1e-9)
    # the wing rule: the mean static margin is the middle of R13 (the lattice downwash is cached on three decimals)
    full, empty = m.cg_ends(d, L, lay, ctx["tanks"], ch)
    assert (st["x_np_power_off_ft"] - 0.5 * (full + empty)) / d["wing"]["mac"] == pytest.approx(0.10, abs=2e-4)
    # the tipback rule, gear down
    rows = m.pick(m.loadings(d, L, lay, ctx["tanks"], ch), gear="down", payload_on=True, empty_weight_factor=1.0)
    assert m.tipback_deg(d, lay, max(r["x_cg_ft"] for r in rows)) == pytest.approx(L["tipback_angle_deg"], abs=1e-6)
    # weights by the ratios of (15.47)-(15.49); everything else untouched
    w0, w = lay0["weights"], lay["weights"]
    assert w["fuselage"] / w0["fuselage"] == pytest.approx((lay["arm"] / lay0["arm"]) ** -0.051)
    assert w["horizontal_tail"] / w0["horizontal_tail"] == pytest.approx(
        (lay["ht_area"] / lay0["ht_area"]) ** 0.896 * math.cos(math.atan(0.25)) ** (0.12 - 2 * 0.043))    # (15.47)'s sweep terms
    assert w["vertical_tail"] / w0["vertical_tail"] == pytest.approx((lay["vt_area"] / lay0["vt_area"]) ** 0.873)
    assert {k for k in w if w[k] != w0[k]} == {"horizontal_tail", "vertical_tail", "fuselage"}
    # straight trailing edges: on the loft the root and tip trailing edges are at one station, and the quarter
    # point of each mean chord is at the tail arm behind the wing's
    assert lay["tail_te_straight"] is True and lay0["tail_te_straight"] is False
    assert m.tail_le_slope(L, "horizontal") == pytest.approx(1.0 / 3.0) and m.tail_le_slope(L, "vertical") == pytest.approx(4.0 / 9.0)
    assert m.tail_lift_slope(L, lay0) == pytest.approx(d["layout"]["CLa_h"], rel=1e-12) and m.tail_lift_slope(L, lay) < d["layout"]["CLa_h"]
    assert lay["x_nose"] == lay0["x_nose"] and lay["payload_x"] == lay0["payload_x"]
    # the loft, built with this layout, has no tail point behind the propeller plane inside the disc (P3's row 9)
    d1 = p4.record_with_layout(d, L, lay)
    model = ac.build(d1, L, ctx["A"])
    x_h = lay["x_le"] + 0.25 * d["wing"]["mac"] + lay["arm"]
    for name in ("horizontal_tail", "vertical_tail"):
        s = model[name]
        assert s.x_le + s.c_root == pytest.approx(s.x_le + s.le_slope * s.half_span + s.c_tip, abs=1e-9), name
        mac, y_mac, _ = s.mean_chord()
        assert s.x_le + s.le_slope * y_mac + 0.25 * mac == pytest.approx(x_h, abs=1e-9), name
    row9 = gates.row9_propeller_disc(model, ac.meshes(model))
    for k in ("horizontal_tail", "vertical_tail"):
        assert row9["behind_plane_ft"][k] <= -clr + 0.01, (k, row9["behind_plane_ft"][k])
    assert max(row9["behind_plane_ft"][k] for k in ("horizontal_tail", "vertical_tail")) == pytest.approx(-clr, abs=0.01)


def test_tail_forms_and_the_scan(ctx):
    """r0's planforms moved clear of the disc at r0's wing position: the rearmost point is where it is asked to be
    and the volume coefficient is kept, whatever area that takes. A wing position with no such tail is recorded
    by the scan, not hidden."""
    d, L, ch = ctx["d"], ctx["L"], ctx["choices"]
    lay0 = m.base_layout(d, ctx["p3"])
    limit = ctx["propeller_plane_x"] - 1.0
    for straight in (False, True):
        lay = m.retail(d, L, lay0, lay0["x_le"], limit, straight)
        assert max(m.tail_rearmost(d, L, lay).values()) == pytest.approx(limit, abs=1e-9)
        assert lay["ht_area"] * lay["arm"] == pytest.approx(lay0["ht_area"] * lay0["arm"], rel=1e-12)
        assert lay["arm"] < lay0["arm"] and lay["ht_area"] > lay0["ht_area"]
    assert m.retail(d, L, lay0, lay0["x_le"], limit, True)["arm"] > m.retail(d, L, lay0, lay0["x_le"], limit, False)["arm"]
    cm_w = m.wing_moment(ctx["cm0_p2"], d["A"])
    rows = m.scan_wing_positions(d, L, lay0, ctx["tanks"], ch, ctx["body"], ctx["src"], ctx["propeller_plane_x"], cm_w, [0.0, 50.0])
    assert rows[0]["wing_shift_ft"] == 0.0 and rows[0]["arm_ft"] == pytest.approx(m.retail(d, L, lay0, lay0["x_le"], limit, True)["arm"])
    assert "no arm" in rows[1]["tail"]


def test_envelope_counts_what_is_outside(ctx):
    d, L = ctx["d"], ctx["L"]
    lay = m.base_layout(d, ctx["p3"])
    rows = m.loadings(d, L, lay, ctx["tanks"], ctx["choices"])
    cm_w = m.wing_moment(ctx["cm0_p2"], d["A"])
    env = m.envelope(d, L, lay, rows, 1e3, cm_w)                 # a neutral point far aft: nothing is too far aft
    assert env["payload_on"]["outside_envelope"] == sum(r["x_cg_ft"] < r["forward_limit_ft"] for r in rows if r["payload_on"])
    assert env["payload_on"]["too_far_aft"] == 0 and env["payload_on"]["too_far_forward"] == env["payload_on"]["outside_envelope"]
    # rotation limits the loadings with the gear down, each at its own weight; trim limits all
    up, down = m.pick(rows, gear="up")[0], m.pick(rows, gear="down", payload_on=True)[-1]
    assert up["forward_limit_ft"] == env["forward"]["trim_ft"] and down["forward_limit_ft"] > env["forward"]["trim_ft"]
    assert m.rotation(d, L, lay, down["forward_limit_ft"], cm_w, down["weight_lb"])["CL_tail_needed"] == pytest.approx(-L["tail_cl_max_rotation"], abs=1e-8)
    full = m.pick(rows, gear="down", payload_on=True, empty_weight_factor=1.0)[0]
    assert full["forward_limit_ft"] == pytest.approx(env["forward"]["rotation_ft"], abs=1e-4)        # take-off weight (the record closes to 0.002 lb)
    assert set(env["payload_on_by_empty_weight_factor"]) == {"0.95", "1", "1.05"}
    env = m.envelope(d, L, lay, rows, -1e3, cm_w)                # a neutral point far ahead: everything is
    assert env["payload_on"]["outside_envelope"] == env["payload_on"]["loadings"] and env["row3"] == "fail"
    assert all("nose_load" in r for r in rows if r["gear"] == "down") and all("nose_load" not in r for r in rows if r["gear"] == "up")
    assert m.inside(0.05, 0.05, 0.15) == "pass" and m.inside(0.0499, 0.05, 0.15) == "fail" and m.inside(0.151, 0.05, 0.15) == "fail"


# ---- verdict rules of the run (fixed here) ---------------------------------------------------------------------
def test_verdict_rules():
    assert p4.row2_verdict(0.0299) == "pass" and p4.row2_verdict(-0.0301) == "fail"
    conv = p4.vspaero_verdict({"L2": {"x_np_ft": 12.50, "valid": True}, "L3": {"x_np_ft": 12.55, "valid": True}}, 6.0)
    assert conv["converged"] is True and conv["change_mac"] == pytest.approx(0.05 / 6.0)
    conv = p4.vspaero_verdict({"L2": {"x_np_ft": 12.50, "valid": True}, "L3": {"x_np_ft": 12.57, "valid": True}}, 6.0)
    assert conv["converged"] is False and "no verdict" in conv["note"]
    conv = p4.vspaero_verdict({"L2": {"x_np_ft": 12.50, "valid": False}, "L3": {"x_np_ft": 12.50, "valid": True}}, 6.0)
    assert conv["converged"] is False
    assert p4.vspaero_verdict("no interpreter", 6.0) == {"run": False, "reason": "no interpreter"}
    assert p4.TOL_VSPAERO_MAC == 0.01 and m.TOL_NP == 0.03 and (m.SM_MIN, m.SM_MAX) == (0.05, 0.15) and m.NOSE_LIMITS == (0.05, 0.20)
    json.dumps(copy.deepcopy(p4.ROW_NAMES))
    assert sorted(p4.ROW_NAMES) == ["1", "2", "3", "4", "5"]
    assert uav.KT > 0

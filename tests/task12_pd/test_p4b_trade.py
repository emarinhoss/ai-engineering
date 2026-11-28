"""Preliminary design P4b (tail and aft-body layout trade, a follow-up to P4 and PD-20): tests of the methods,
written before the recorded run. No test requires a layout to pass a row or to win: a failed row is recorded and
reported. What is tested is that the lengthened body, the weights of the added length, the placement, the drag and
hours route and the selection rule do what their docstrings say, and that with no extension everything is P4's.
"""
import json
import math

import numpy as np
import pytest

from conceptual import uav
from prelim import p4_methods as m
from prelim import p4b_trade as t

P4 = json.loads(t.P4_RECORD.read_text())
P3 = json.loads(t.p4.P3_RECORD.read_text())


@pytest.fixture(scope="module")
def ctx():
    return t.context()


@pytest.fixture(scope="module")
def lay0(ctx):
    return m.base_layout(ctx["d"], ctx["p3"])


@pytest.fixture(scope="module")
def bs(ctx, lay0):
    """r0's tail arm and areas with straight trailing edges, at the stated shaft weight: (layout, context)."""
    return t.solve(ctx, lay0, lay0["arm"], True, 5.0)


# ---- the choices file ---------------------------------------------------------------------------------------------
def test_choices_state_the_rule_the_shaft_assumption_and_the_candidates():
    ch = m.load_yaml(t.CHOICES)
    shaft = ch["extension"]["shaft_lb_per_ft"]
    assert shaft["band"][0] < shaft["value"] < shaft["band"][1] and "assumption" in shaft["source"].lower()
    assert set(ch["candidates"]) >= {"A", "B", "Bs", "C", "arm_scan_points", "placement"} and ch["candidates"]["arm_scan_points"] >= 5
    rule = ch["selection_rule"]
    assert [s[0] for s in rule["steps"]] == ["1", "2", "3", "4", "5"] and 0 < rule["hours_tie_h"] <= 0.05
    assert "owner" in rule["steps"][4] and "ballast" in rule["steps"][1]
    assert not list((t.REPO / "data/task12").glob("*p4b*.pdf"))


# ---- the lengthened body ------------------------------------------------------------------------------------------
def test_lengthened_body_keeps_everything_ahead_of_the_engine_bays_end(ctx):
    body = ctx["body"]
    same = t.lengthened_body(body, 0.0)
    x = np.linspace(0.01, body.length, 50)
    assert np.allclose(np.array(same.lines(x)), np.array(body.lines(x)), rtol=0, atol=1e-12)
    long = t.lengthened_body(body, 2.0)
    assert long.length == pytest.approx(body.length + 2.0, abs=1e-12)
    ahead = np.linspace(0.01, body.stations[-3, 0], 40)               # up to the start of the engine bay's last control station
    assert np.allclose(np.array(long.lines(ahead)), np.array(body.lines(ahead)), rtol=0, atol=1e-9)
    assert long.lines(long.length)[0] == pytest.approx(body.lines(body.length)[0], abs=1e-12)      # still ends at the spinner radius
    half = long.lines(np.linspace(body.stations[-2, 0], long.length, 200))[0]
    assert np.all(np.diff(half) <= 1e-12)                             # the taper is drawn out, never a bulge


def test_added_skin_lies_between_a_tube_at_the_spinner_and_one_at_the_engine_bay(ctx):
    body = ctx["body"]
    assert ctx["skin0"] == pytest.approx(t.skin_area(body), rel=1e-12)
    # the same mesh rule at P3's density gives P3's whole fuselage surface to a fraction of a per cent
    assert ctx["skin0"] == pytest.approx(P3["gates"]["3"]["parts"]["fuselage"]["whole_ft2"], rel=5e-3)
    ext = 2.0
    added = t.skin_area(t.lengthened_body(body, ext)) - ctx["skin0"]
    r_end = body.lines(body.length)[0]
    per_bay = body.section_measures(np.array([body.stations[-2, 0]]))[0][0]
    assert 2 * math.pi * r_end * ext < added < per_bay * ext


# ---- the tail at an arm, and the layout with an extension ---------------------------------------------------------
def test_tail_at_arm_is_p4s_retail_at_that_arm(ctx, lay0):
    d, L = ctx["d"], ctx["L"]
    same = t.tail_at_arm(d, L, lay0, lay0["x_le"], lay0["arm"], False)
    assert same["arm"] == pytest.approx(lay0["arm"], rel=1e-10) and same["ht_area"] == pytest.approx(lay0["ht_area"], rel=1e-10)
    for k, v in lay0["weights"].items():
        assert same["weights"][k] == pytest.approx(v, rel=1e-9), k
    rec = P4["r1"]["evaluation"]["layout"]
    pd20 = t.tail_at_arm(d, L, lay0, rec["x_le"], rec["arm"], True)
    for k in ("arm", "ht_area", "vt_area"):
        assert pd20[k] == pytest.approx(rec[k], rel=1e-9), k
    for k, v in rec["weights"].items():
        assert pd20["weights"][k] == pytest.approx(v, rel=1e-9), k


def test_no_extension_is_p4s_own_layout(ctx, lay0):
    rec = P4["r1"]["evaluation"]["layout"]
    lay, c1 = t.extended(ctx, lay0, rec["x_le"], rec["arm"], True, 5.0)
    assert lay["extension"]["length_ft"] == 0.0 and lay["extension"]["shaft_lb"] == 0.0 and lay["extension"]["added_skin_ft2"] == 0.0
    for k, v in rec["weights"].items():
        assert lay["weights"][k] == pytest.approx(v, rel=1e-9), k
    assert c1["d"]["fuselage"]["length"] == ctx["d"]["fuselage"]["length"] and c1["propeller_plane_x"] == ctx["propeller_plane_x"]
    assert c1["d"]["stations"]["fuselage"]["x"] == pytest.approx(ctx["d"]["stations"]["fuselage"]["x"], rel=1e-12)
    solved, _ = t.solve(ctx, lay0, rec["arm"], True, 5.0)
    for k in ("x_le", "x_main", "ht_area"):
        assert solved[k] == pytest.approx(rec[k], rel=1e-6), k


def test_extension_clears_the_disc_and_weighs_what_the_equations_say(ctx, lay0):
    d, L = ctx["d"], ctx["L"]
    x_le, rate = lay0["x_le"] + 0.8, 5.0
    lay, c1 = t.extended(ctx, lay0, x_le, lay0["arm"], True, rate)
    e = lay["extension"]
    assert e["length_ft"] > 0.5
    rear = max(m.tail_rearmost(d, L, lay).values())
    assert c1["propeller_plane_x"] - rear == pytest.approx(1.0, abs=1e-9)                       # P4's clearance
    assert c1["propeller_plane_x"] == pytest.approx(ctx["propeller_plane_x"] + e["length_ft"], abs=1e-12)
    assert c1["body"].length == pytest.approx(d["fuselage"]["length"] + e["length_ft"], abs=1e-12) == c1["d"]["fuselage"]["length"]
    assert lay["ht_area"] == pytest.approx(lay0["ht_area"], rel=1e-9) and lay["vt_area"] == pytest.approx(lay0["vt_area"], rel=1e-9)
    f0, S0, w0 = d["fuselage"]["length"], d["fuselage"]["s_wet"], lay0["weights"]
    fus = w0["fuselage"] * ((S0 + e["added_skin_ft2"]) / S0) ** 1.086 * ((f0 + e["length_ft"]) / f0) ** -0.072       # (15.49), arm unchanged
    assert e["fuselage_structure_lb"] == pytest.approx(fus, rel=1e-10)
    assert e["shaft_lb"] == pytest.approx(rate * e["length_ft"], rel=1e-12)
    assert lay["weights"]["fuselage"] == pytest.approx(fus + rate * e["length_ft"], rel=1e-10)
    assert lay["weights"]["flight_controls"] == pytest.approx(w0["flight_controls"] * ((f0 + e["length_ft"]) / f0) ** 1.536, rel=1e-10)    # (15.54)
    x0, xa = d["stations"]["fuselage"]["x"], f0 + 0.5 * e["length_ft"]
    moment = w0["fuselage"] * x0 + (lay["weights"]["fuselage"] - w0["fuselage"]) * xa
    assert c1["d"]["stations"]["fuselage"]["x"] == pytest.approx(moment / lay["weights"]["fuselage"], rel=1e-10)
    # nothing else of the record is changed, and the caller's record is untouched
    assert ctx["d"]["fuselage"]["length"] == f0 and ctx["d"]["stations"]["fuselage"]["x"] == x0
    assert {k for k in lay["weights"] if lay["weights"][k] != w0[k]} <= {"fuselage", "flight_controls", "horizontal_tail", "vertical_tail"}
    # a heavier shaft changes the shaft's weight and nothing else at a fixed wing position
    heavy = t.extended(ctx, lay0, x_le, lay0["arm"], True, 10.0)[0]
    assert heavy["extension"]["length_ft"] == e["length_ft"]
    assert heavy["weights"]["fuselage"] - lay["weights"]["fuselage"] == pytest.approx(5.0 * e["length_ft"], rel=1e-9)
    # r0's own planforms need a longer extension than straight trailing edges at the same arm
    assert t.extended(ctx, lay0, x_le, lay0["arm"], False, rate)[0]["extension"]["length_ft"] > e["length_ft"]


def test_solve_places_wing_and_wheels_by_p4s_rules(ctx, lay0, bs):
    lay, c1 = bs
    d1, L, mac = c1["d"], ctx["L"], ctx["d"]["wing"]["mac"]
    x_np = m.stability(d1, L, lay, c1["body"], ctx["src"])["x_np_power_off_ft"]
    full, empty = m.cg_ends(d1, L, lay, ctx["tanks"], ctx["choices"])
    assert (x_np - 0.5 * (full + empty)) / mac == pytest.approx(0.10, abs=1e-6)
    rows = m.pick(m.loadings(d1, L, lay, ctx["tanks"], ctx["choices"]), gear="down", payload_on=True, empty_weight_factor=1.0)
    aft = max(r["x_cg_ft"] for r in rows)
    assert math.degrees(math.atan((lay["x_main"] - aft) / ctx["d"]["layout"]["h_cg"])) == pytest.approx(L["tipback_angle_deg"], abs=1e-6)
    assert lay["x_nose"] == lay0["x_nose"] and lay["arm"] == pytest.approx(lay0["arm"], rel=1e-9)
    assert lay["extension"]["length_ft"] > 0.0


# ---- drag and hours -----------------------------------------------------------------------------------------------
def test_drag_and_hours_give_r0_back_and_move_the_right_way(ctx):
    d, built = ctx["d"], ctx["built"]
    original = uav._geometry
    zero = {"horizontal_tail": 0.0, "vertical_tail": 0.0, "fuselage": 0.0}
    base = t.drag_and_hours(built, d, zero, 0.0)
    assert uav._geometry is original
    assert base["at_r0_weight"] == base["with_empty_weight_change"] == ctx["hours_base"]
    assert base["at_r0_weight"]["CD0_mission_altitude"] == pytest.approx(d["CD0"]["mission_altitude"], rel=1e-12)
    p3 = P3["buildup"]["as_recorded"]
    assert base["at_r0_weight"]["hours_on_station"] == pytest.approx(p3["hours_on_station"], abs=1e-6)
    more = t.drag_and_hours(built, d, dict(zero, fuselage=10.0), 30.0)
    a, b = more["at_r0_weight"], more["with_empty_weight_change"]
    assert a["CD0_mission_altitude"] > base["at_r0_weight"]["CD0_mission_altitude"] and b["CD0_mission_altitude"] == a["CD0_mission_altitude"]
    assert b["hours_on_station"] < a["hours_on_station"] < base["at_r0_weight"]["hours_on_station"]
    assert b["W0_lb"] == pytest.approx(d["W0_lb"] + 30.0) and a["W0_lb"] == d["W0_lb"]
    tail = t.drag_and_hours(built, d, dict(zero, horizontal_tail=10.0), 0.0)["at_r0_weight"]
    assert tail["CD0_mission_altitude"] > base["at_r0_weight"]["CD0_mission_altitude"]


# ---- what is read off a layout ------------------------------------------------------------------------------------
def test_measures_follow_from_the_evaluation(ctx, lay0, bs):
    lay, c1 = bs
    d, L = ctx["d"], ctx["L"]
    e = t.p4.evaluate(c1, lay, "Bs", lambda msg: None)
    mm = t.measures(ctx, c1, lay0, lay, e, ctx["built"])
    assert mm["empty_weight_change_lb"] == pytest.approx(sum(lay["weights"].values()) - sum(lay0["weights"].values()), rel=1e-12)
    assert mm["empty_weight_change_lb"] == pytest.approx(sum(mm["weight_changes_lb"].values()), rel=1e-9)
    assert mm["added_wetted_ft2"]["fuselage"] == lay["extension"]["added_skin_ft2"] and abs(mm["added_wetted_ft2"]["horizontal_tail"]) < 1e-9
    assert mm["eligible"] is all(mm["rows"][k] == "pass" for k in t.PAYLOAD_ON_ROWS)
    assert mm["rows"]["propeller_ground_clearance"] == ("pass" if mm["propeller_clearance_in"] >= L["prop_clearance_in"] else "fail")
    assert mm["rows"]["rotation_tail_lift"] == ("pass" if mm["rotation_used_of_limit"] <= 1.0 else "fail")
    # Stage 1's clearance expression with the longer fuselage: the propeller is lower at rotation than on r0's body
    th = math.radians(L["rotation_angle_deg_pusher"])
    hub = d["layout"]["h_cg"] * math.cos(th) - (c1["d"]["fuselage"]["length"] - lay["x_main"]) * math.sin(th)
    assert mm["propeller_clearance_in"] == pytest.approx(12 * (hub - 0.5 * d["propeller_diameter_ft"]), rel=1e-12)
    assert mm["propeller_clearance_in"] < m.propeller_clearance_in(d, L, lay)
    assert mm["hours_for_rule"] == mm["drag_and_hours"]["with_empty_weight_change"]["hours_on_station"]
    assert max(mm["tail_rearmost_behind_propeller_plane_ft"].values()) == pytest.approx(-1.0, abs=1e-9)
    assert t.row9_on_the_loft(ctx, c1, lay)["verdict"] == "pass"
    off = mm["payload_off"]
    aft = e["envelope"]["aft_limit_ft"]
    for r in (q for q in e["loadings"] if not q["payload_on"]):              # the ballast brings every payload-off loading to the aft limit
        W, x = r["weight_lb"] + off["ballast_every_loading_lb"], (r["weight_lb"] * r["x_cg_ft"] + off["ballast_every_loading_lb"] * lay["payload_x"])
        assert x / W <= aft + 1e-9
    assert off["ballast_every_loading_lb"] >= off["ballast_to_aft_limit_lb"] > off["ballast_to_main_wheels_lb"] >= 0.0
    assert off["with_that_ballast"]["too_far_aft"] == 0
    mw = off["main_wheels_moved_for_payload_off"]
    assert mw["x_main_ft"] > lay["x_main"] and mw["rotation_used_of_limit"] > mm["rotation_used_of_limit"]


def test_shaft_tube_is_torque_over_section(ctx):
    tube = m.load_yaml(t.CHOICES)["extension"]["shaft_tube_for_support"]
    s = t.shaft_tube(ctx["d"], ctx["L"], tube)
    assert s["torque_lb_ft"] == pytest.approx(ctx["d"]["bhp_sl"] * 550.0 / (ctx["L"]["propeller_rpm"] * math.pi / 30.0), rel=1e-12)
    ro, ri = 1.5, 1.5 - tube["wall_in"]
    assert s["weight_lb_per_ft"] == pytest.approx(12 * math.pi * (ro ** 2 - ri ** 2) * tube["density_lb_in3"], rel=1e-12)
    assert s["shear_stress_psi"] == pytest.approx(12 * s["torque_lb_ft"] * ro / (math.pi / 2 * (ro ** 4 - ri ** 4)), rel=1e-12)
    # the support the choices file claims for the band's low end: the bare tube is lighter than the low end and is not overstressed
    assert s["weight_lb_per_ft"] < m.load_yaml(t.CHOICES)["extension"]["shaft_lb_per_ft"]["band"][0]
    assert s["shear_stress_psi"] < s["allowable_over_safety_factor_psi"]


# ---- the selection rule -------------------------------------------------------------------------------------------
def _row(eligible=True, no_ballast=False, hours=10.0, weight=20.0, failed=()):
    rows = {k: ("fail" if k in failed or (not eligible and not failed and k == "rotation_tail_lift") else "pass") for k in t.PAYLOAD_ON_ROWS}
    return {"eligible": eligible, "payload_off_without_ballast": no_ballast, "hours_for_rule": hours, "empty_weight_change_lb": weight, "rows": rows}


def test_selection_rule_steps():
    # step 1: a layout that fails a payload-on row is out, however good its hours
    s = t.select({"A": _row(hours=10.0), "B": _row(eligible=False, hours=11.0, failed=("propeller_ground_clearance",))}, 0.01)
    assert s["chosen"] == "A" and s["failed_step_1"] == {"B": ["propeller_ground_clearance"]}
    # step 2: a layout that needs no ballast beats one with more hours that does
    s = t.select({"A": _row(hours=10.5), "B": _row(no_ballast=True, hours=10.0)}, 0.01)
    assert s["chosen"] == "B" and s["after_step_2"] == ["B"]
    # step 2 with nobody ballast-free: ballast does not rank; step 3: most hours
    s = t.select({"A": _row(hours=10.5, weight=20.0), "B": _row(hours=10.6, weight=40.0)}, 0.01)
    assert s["chosen"] == "B" and s["after_step_2"] == ["A", "B"] and s["tied_on_hours"] == ["B"]
    # step 4: within the tie, the least empty-weight change
    s = t.select({"A": _row(hours=10.595, weight=20.0), "B": _row(hours=10.6, weight=40.0)}, 0.01)
    assert s["chosen"] == "A" and s["tied_on_hours"] == ["A", "B"] and "tie" in s["reason"]
    # step 5: nobody passes, nothing chosen, to the owner
    s = t.select({"A": _row(eligible=False), "B": _row(eligible=False)}, 0.01)
    assert s["chosen"] is None and "owner" in s["reason"]


def test_named_rows_and_labels():
    cand = {"A": {"measures": dict(_row(weight=27.0), arm_ft=11.0)},
            "scan_00": {"measures": dict(_row(weight=27.0), arm_ft=11.0)},
            "scan_01": {"measures": dict(_row(weight=25.0), arm_ft=12.0)},
            "scan_02": {"measures": dict(_row(eligible=False, weight=20.0), arm_ft=13.0)}}
    names = t.named(cand, ["scan_00", "scan_01", "scan_02"])
    assert names == {"Bs": "scan_02", "C": "scan_01"}                 # C: least empty weight among the rows that pass
    assert t.label_of("A", names, cand) == "A" and t.label_of(None, names, cand) == "none"
    assert t.label_of("scan_01", names, cand) == "C = arm scan row 01 (tail arm 12.000 ft)"
    assert t.label_of("scan_00", names, cand).startswith("arm scan row 00")

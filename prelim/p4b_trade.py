"""Preliminary design P4b: the tail and aft-body layout trade (a follow-up to P4 and its decision PD-20).

    python -m prelim.p4b_trade --out runs/task12/pd/<date>/p4b [--report docs/validation/<date>_task12_pd_p4b.md]
    python -m prelim.p4b_trade --out runs/task12/pd/<date>/p4b --report ... --report-only

PD-20 clears the pusher's propeller disc by moving the tails forward and enlarging them. This package compares
that layout (A) with a lengthened aft fuselage that keeps r0's tail arm (B, Bs) and with every tail arm in between
(the arm scan; C is its row of least empty-weight change), all placed and judged by P4's own code and rules
(prelim/p4_methods.py, prelim/p4_balance.evaluate). The choices and the selection rule were written before any run:
data/task12/pd_p4b_choices.yaml. r0 and the P4 record are read and not changed; the result is a finding for r1.

What is new here, and only this: the lengthened body (the loft's last station moved aft), the weight of the added
length (Raymer (15.49) and (15.54), p. 404, as ratios, and an assumed shaft weight per foot), the drag and
hours-on-station effect of each layout (P3's route), and the selection rule. Units: ft, lb, s, rad.
"""
import argparse
import copy
import json
import math
import platform
import sys
import time

import numpy as np
import scipy
import yaml
from scipy.optimize import brentq

from conceptual import raymer_aero as aero
from conceptual import raymer_weights as wts
from conceptual import uav
from geometry3d import aircraft as ac
from geometry3d import gates, mesh
from geometry3d.fuselage import Body
from geometry3d.surfaces import Ellipsoid
from prelim import p3_loft as p3
from prelim import p4_balance as p4
from prelim import p4_methods as m
from prelim.record import tree_state

REPO = m.REPO
R0 = p3.R0
P4_RECORD = REPO / "runs/task12/pd/2026-11-27/p4/p4.json"
CHOICES = REPO / "data/task12/pd_p4b_choices.yaml"
EVIDENCE_CLASS = ("layout construction and a comparison by P4's own methods: the stability, balance, trim and rotation "
                  "numbers have the evidence class of P4 (partly independent of Stage 1); the weights of the added "
                  "length are Raymer's statistical equations as ratios plus an assumed shaft weight; the drag and hours "
                  "are Stage 1's build-up and mission with changed wetted areas (a coding check, not a measurement)")
PAYLOAD_ON_ROWS = ("row1_R13", "row3_envelope_payload_on", "row4_nose_load_payload_on", "rotation_tail_lift", "trim_tail_lift",
                   "overturn", "propeller_ground_clearance", "tails_clear_of_disc")


# ---- the lengthened aft fuselage --------------------------------------------------------------------------------
def lengthened_body(body, extension):
    """The loft's fuselage with its last control station (the circle that meets the spinner) moved aft by
    `extension`. Every other station stays, so the nose, the bays and the engine bay are r0's; the taper from
    the engine bay to the spinner is drawn out over the added length."""
    rows = body.stations.copy()
    rows[-1, 0] += extension
    return Body(rows, body.nose_length)


def skin_area(body):
    """Whole outer surface of a body, from the same triangle mesh the loft's gates use (ft^2)."""
    V, T = mesh.loft(body.rings(400, 17), start=(0.0, 0.0, 0.0), end="fan")
    return float(mesh.areas(V, T).sum())


def tail_at_arm(d, L, lay0, x_le, arm, straight_te):
    """P4's own tail (p4_methods.retail: areas from the kept volume coefficients, weights by (15.47)-(15.49)) at a
    given tail arm instead of a given rearmost station: the rearmost station of a tail at that arm is worked out
    first and handed to retail, which then finds the same arm again."""
    trial = dict(copy.deepcopy(lay0), x_le=x_le, arm=arm, tail_te_straight=straight_te,
                 ht_area=lay0["ht_area"] * lay0["arm"] / arm, vt_area=lay0["vt_area"] * lay0["arm"] / arm)
    return m.retail(d, L, lay0, x_le, max(m.tail_rearmost(d, L, trial).values()), straight_te)


def extended(c, lay0, x_le, arm, straight_te, shaft_lb_per_ft):
    """The layout with the wing leading edge at x_le, the tails at the tail arm `arm`, and the aft fuselage
    lengthened by the least length that leaves the P4 clearance between the rearmost tail point inside the disc
    and the propeller plane (never shortened). Returns (layout, context): the context is P4's with the longer
    body, the propeller plane moved aft, the fuselage length and the fuselage's weight station changed.

    Weights, as ratios on r0's (the aircraft is not re-sized):
    fuselage (15.49): wetted area^1.086 (Stage 1's area plus the loft's added skin), tail arm^-0.051,
    (length/diameter)^-0.072; flight controls (15.54): length^1.536; shaft: shaft_lb_per_ft times the added length.
    The fuselage's added weight and the shaft sit at the middle of the added length; both are carried in the
    layout's "fuselage" weight, whose station becomes their common centre (P4's balance has one fuselage item)."""
    d, L = c["d"], c["L"]
    lay = tail_at_arm(d, L, lay0, x_le, arm, straight_te)
    clearance = m.val(c["choices"]["r1"]["propeller_clearance_ft"])
    ext = max(0.0, max(m.tail_rearmost(d, L, lay).values()) + clearance - c["propeller_plane_x"])
    if ext < 1e-9:                                            # the tail is already clear: P4's own layout
        ext = 0.0
    body = lengthened_body(c["body"], ext)
    skin = skin_area(body) - c["skin0"] if ext else 0.0
    f0, S0, D = d["fuselage"]["length"], d["fuselage"]["s_wet"], d["fuselage"]["diameter"]
    w0, w = lay0["weights"], lay["weights"]
    fus_arm = w["fuselage"]                                   # retail: the tail-arm term alone, at r0's station
    fus = w0["fuselage"] * wts.fuselage(S0 + skin, 1.0, 1.0, arm, (f0 + ext) / D, 1.0) / wts.fuselage(S0, 1.0, 1.0, lay0["arm"], f0 / D, 1.0)
    shaft = shaft_lb_per_ft * ext
    x_added, x_fus0 = f0 + 0.5 * ext, d["stations"]["fuselage"]["x"]
    w["fuselage"] = fus + shaft
    w["flight_controls"] = w0["flight_controls"] * wts.flight_controls(f0 + ext, 1.0, 1.0, 1.0) / wts.flight_controls(f0, 1.0, 1.0, 1.0)
    x_fus = (fus_arm * x_fus0 + (fus - fus_arm + shaft) * x_added) / (fus + shaft)
    lay["extension"] = {"length_ft": ext, "fuselage_length_ft": f0 + ext, "added_skin_ft2": skin, "shaft_lb_per_ft": shaft_lb_per_ft,
                        "shaft_lb": shaft, "fuselage_structure_lb": fus, "fuselage_added_for_length_lb": fus - fus_arm,
                        "added_weight_station_ft": x_added, "fuselage_item_station_ft": x_fus}
    d1 = dict(d, fuselage=dict(d["fuselage"], length=f0 + ext),
              stations=dict(d["stations"], fuselage=dict(d["stations"]["fuselage"], x=x_fus)))
    return lay, dict(c, d=d1, body=body, propeller_plane_x=c["propeller_plane_x"] + ext)


def solve(c, lay0, arm, straight_te, shaft_lb_per_ft):
    """P4's placement (p4_methods.solve_r1) for a layout of extended(): the wing position at which the mean of the
    full-fuel and empty-fuel static margins is the middle of R13, with the main wheels by the tipback rule.
    Returns (layout, context); raises ValueError if no wing position between r0's and 3 ft aft of it does it."""
    L, mac = c["L"], c["d"]["wing"]["mac"]
    target = 0.5 * (m.SM_MIN + m.SM_MAX)

    def build(x_le):
        lay, c1 = extended(c, lay0, x_le, arm, straight_te, shaft_lb_per_ft)
        lay["x_main"] = lay0["x_main"] + x_le - lay0["x_le"]
        m.place_main_gear(c1["d"], L, lay, c["tanks"], c["choices"])
        x_np = m.stability(c1["d"], L, lay, c1["body"], c["src"])["x_np_power_off_ft"]
        full, empty = m.cg_ends(c1["d"], L, lay, c["tanks"], c["choices"])
        return lay, c1, (x_np - 0.5 * (full + empty)) / mac
    x_le = brentq(lambda x: build(x)[2] - target, lay0["x_le"], lay0["x_le"] + 3.0, xtol=1e-8)
    return build(x_le)[:2]


# ---- drag and hours on station (P3's route) ----------------------------------------------------------------------
def drag_and_hours(built, d, added_wetted, empty_weight_change):
    """Stage 1's drag build-up and mission on the built aircraft with `added_wetted` (ft^2, by component) added to
    Stage 1's wetted areas and nothing else changed, as prelim/p3_loft.buildup_with_loft_areas does it. The
    geometry is r0's at both weights (Stage 1 would otherwise re-draw the fuselage for the heavier aircraft).
    Returns CD0 at the mission altitude and the hours on station on r0's fuel (a) at r0's take-off weight and
    (b) with the take-off weight raised by the empty-weight change."""
    from prelim.p1_package import hours_for_fuel
    keys = {"horizontal_tail": "s_wet_ht", "vertical_tail": "s_wet_vt", "fuselage": "s_wet_fus"}
    original = uav._geometry

    def geometry(W0, W_S, A, concept, L):
        g = original(d["W0_lb"], d["W_S"], A, concept, L)
        for name, key in keys.items():
            g[key] += added_wetted[name]
        return g
    out = {}
    uav._geometry = geometry
    try:
        for tag, W0 in (("at_r0_weight", d["W0_lb"]), ("with_empty_weight_change", d["W0_lb"] + empty_weight_change)):
            state = built.build({}, W0=W0)[0]
            out[tag] = {"W0_lb": W0, "CD0_mission_altitude": state["CD0_alt"],
                        "hours_on_station": hours_for_fuel(lambda h: built.fuel_at({}, h, W0)[0], d["fuel_lb"])}
    finally:
        uav._geometry = original
    return out


# ---- what the comparison reads off each layout -------------------------------------------------------------------
def shaft_tube(d, L, tube):
    """Support for the assumed shaft weight, not a test target: a round steel tube that carries the record's shaft
    power at the propeller speed. Torque = power/angular speed; stress = T r/I_p (Raymer (14.45), p. 388, from
    the chapter notes); weight per foot = section area times density."""
    torque = d["bhp_sl"] * 550.0 / (L["propeller_rpm"] * 2.0 * math.pi / 60.0)                # lb ft
    ro, ri = 0.5 * tube["outer_diameter_in"], 0.5 * tube["outer_diameter_in"] - tube["wall_in"]
    stress = 12.0 * torque * ro / (0.5 * math.pi * (ro ** 4 - ri ** 4))
    return {"torque_lb_ft": torque, "shear_stress_psi": stress, "allowable_over_safety_factor_psi": tube["shear_ultimate_psi"] / tube["safety_factor"],
            "weight_lb_per_ft": 12.0 * math.pi * (ro ** 2 - ri ** 2) * tube["density_lb_in3"]}


def main_wheels_for_payload_off(c1, lay, cm_w):
    """A sensitivity, not a layout: the main wheels moved aft until the aftmost payload-off centre of gravity
    (gear down, nominal empty weight) is the tipback angle ahead of them, and what the tail must then lift at
    rotation and the nose wheel must carry with the payload on."""
    d, L, tk, ch = c1["d"], c1["L"], c1["tanks"], c1["choices"]
    lay = copy.deepcopy(lay)
    tb = d["layout"]["h_cg"] * math.tan(math.radians(L["tipback_angle_deg"]))
    for _ in range(100):
        rows = m.pick(m.loadings(d, L, lay, tk, ch), gear="down", payload_on=False, empty_weight_factor=1.0)
        new = max(r["x_cg_ft"] for r in rows) + tb
        if abs(new - lay["x_main"]) < 1e-10:
            break
        lay["x_main"] = new
    on = m.pick(m.loadings(d, L, lay, tk, ch), gear="down", payload_on=True, empty_weight_factor=1.0)
    CL = m.rotation(d, L, lay, min(r["x_cg_ft"] for r in on), cm_w)["CL_tail_needed"]
    return {"x_main_ft": lay["x_main"], "CL_tail_rotation": CL, "rotation_used_of_limit": abs(CL) / L["tail_cl_max_rotation"],
            "nose_load_payload_on_max": max(m.nose_load(lay, r["x_cg_ft"]) for r in on),
            "propeller_clearance_in": m.propeller_clearance_in(d, L, lay)}


def ballast_for_payload_off(c1, lay, e, cm_w):
    """The smallest ballast at the payload station that brings every payload-off loading to the aft limit (the
    largest need over the loadings, rounded up to a whole pound; P4's own figure takes the loading with the aftmost centre of gravity only),
    and a check of it: P4's envelope with that ballast carried in place of the payload."""
    d, L, env = c1["d"], c1["L"], e["envelope"]
    aft = env["aft_limit_ft"]
    need = max(0.0, max(r["weight_lb"] * (r["x_cg_ft"] - aft) / (aft - lay["payload_x"]) for r in e["loadings"] if not r["payload_on"]))
    need = float(math.ceil(need))                             # whole pounds, rounded up, so that the worst loading is inside
    d2 = dict(d, payload_lb=need)
    with_ballast = m.envelope(d2, L, lay, m.loadings(d2, L, lay, c1["tanks"], c1["choices"]), env["x_np_ft"], cm_w)["payload_on"]
    return {"ballast_every_loading_lb": need, "with_that_ballast": {k: with_ballast[k] for k in (
        "loadings", "outside_envelope", "too_far_aft", "too_far_forward", "nose_load_min", "nose_load_max", "nose_load_outside_limits", "tipback_min_deg")}}


def measures(c, c1, lay0, lay, e, built):
    """Everything the comparison table and the selection rule read off one evaluated layout (e: p4.evaluate)."""
    d, L, d1 = c["d"], c["L"], c1["d"]
    env, on, off = e["envelope"], e["envelope"]["payload_on"], e["envelope"]["payload_off"]
    ext = lay.get("extension", {"length_ft": 0.0, "added_skin_ft2": 0.0, "shaft_lb": 0.0})
    w0, w = lay0["weights"], lay["weights"]
    dWe = sum(w.values()) - sum(w0.values())
    wet = lambda S: aero.wetted_area_wing(S, L["tail_t_c"])
    added = {"horizontal_tail": wet(lay["ht_area"]) - wet(lay0["ht_area"]), "vertical_tail": wet(lay["vt_area"]) - wet(lay0["vt_area"]),
             "fuselage": ext["added_skin_ft2"]}
    dh = drag_and_hours(built, d, added, dWe)
    base = c["hours_base"]
    for v in dh.values():
        v["delta_CD0"], v["delta_hours"] = v["CD0_mission_altitude"] - base["CD0_mission_altitude"], v["hours_on_station"] - base["hours_on_station"]
    th = math.radians(L["rotation_angle_deg_pusher"])
    R = 0.5 * d["propeller_diameter_ft"]
    loft_clear = 12.0 * ((d["layout"]["h_cg"] - R) * math.cos(th) - (c1["propeller_plane_x"] - lay["x_main"]) * math.sin(th))
    rear = e["tail_rearmost_behind_propeller_plane_ft"]
    clr = m.val(c["choices"]["r1"]["propeller_clearance_ft"])
    off_down = max((r for r in e["loadings"] if not r["payload_on"] and r["gear"] == "down"), key=lambda r: r["x_cg_ft"])
    behind = off_down["x_cg_ft"] - lay["x_main"]
    cm_w = m.wing_moment(c["cm0_p2"], d["A"])
    rows = {"row1_R13": e["row1"]["gear_up/empty_weight_x1"]["verdict"], "row3_envelope_payload_on": env["row3_payload_on_only"],
            "row4_nose_load_payload_on": env["row4_payload_on_only"], "rotation_tail_lift": e["rotation"]["verdict"],
            "trim_tail_lift": e["trim"]["verdict"],
            "overturn": "pass" if on["overturn_max_deg"] <= L["overturn_max_deg"] else "fail",
            "propeller_ground_clearance": "pass" if e["ground"]["propeller_clearance_in"] >= L["prop_clearance_in"] else "fail",
            "tails_clear_of_disc": "pass" if max(rear.values()) <= -clr + 1e-9 else "fail",
            "row3_envelope_payload_off": "pass" if off["outside_envelope"] == 0 else "fail",
            "row4_nose_load_payload_off": "pass" if off["nose_load_outside_limits"] == 0 else "fail"}
    return {"rows": rows, "eligible": all(rows[k] == "pass" for k in PAYLOAD_ON_ROWS),
            "payload_off_without_ballast": rows["row3_envelope_payload_off"] == rows["row4_nose_load_payload_off"] == "pass",
            "x_le_ft": lay["x_le"], "wing_shift_ft": lay["x_le"] - lay0["x_le"], "arm_ft": lay["arm"], "ht_area_ft2": lay["ht_area"],
            "vt_area_ft2": lay["vt_area"], "x_main_ft": lay["x_main"], "straight_trailing_edges": lay["tail_te_straight"],
            "extension_ft": ext["length_ft"], "fuselage_length_ft": d1["fuselage"]["length"], "propeller_plane_x_ft": c1["propeller_plane_x"],
            "empty_weight_change_lb": dWe, "weight_changes_lb": {k: w[k] - w0[k] for k in w if abs(w[k] - w0[k]) > 1e-9},
            "shaft_lb": ext["shaft_lb"], "added_wetted_ft2": dict(added, total=sum(added.values())), "drag_and_hours": dh,
            "hours_for_rule": dh["with_empty_weight_change"]["hours_on_station"],
            "sm_full": e["row1"]["gear_up/empty_weight_x1"]["sm_full"], "sm_empty": e["row1"]["gear_up/empty_weight_x1"]["sm_empty"],
            "static_margin_payload_on": [on["static_margin_min"], on["static_margin_max"]],
            "payload_on_outside_envelope": on["outside_envelope"], "payload_on_loadings": on["loadings"],
            "payload_off_outside_envelope": off["outside_envelope"], "payload_off_loadings": off["loadings"],
            "nose_load_payload_on": [on["nose_load_min"], on["nose_load_max"]], "nose_load_payload_off": [off["nose_load_min"], off["nose_load_max"]],
            "nose_load_payload_on_outside_optimum": on["nose_load_outside_optimum"],
            "CL_tail_rotation": e["rotation"]["p2_section_moment"]["CL_tail_needed"], "rotation_used_of_limit": e["rotation"]["used_of_limit"],
            "trim_largest": e["trim"]["largest"], "tipback_min_payload_on_deg": on["tipback_min_deg"], "overturn_max_payload_on_deg": on["overturn_max_deg"],
            "propeller_clearance_in": e["ground"]["propeller_clearance_in"], "propeller_clearance_tilted_disc_at_plane_in": loft_clear,
            "tail_rearmost_behind_propeller_plane_ft": rear,
            "payload_off": {"aftmost_x_cg_ft": off_down["x_cg_ft"], "aftmost_weight_lb": off_down["weight_lb"], "behind_main_wheels_ft": behind,
                            "static_margin_min": off["static_margin_min"],
                            "ballast_to_aft_limit_lb": e["payload_off"]["ballast_at_payload_station_lb"],
                            "ballast_to_main_wheels_lb": max(0.0, off_down["weight_lb"] * behind / (lay["x_main"] - lay["payload_x"])),
                            **ballast_for_payload_off(c1, lay, e, cm_w),
                            "main_wheels_moved_for_payload_off": main_wheels_for_payload_off(c1, lay, cm_w)},
            "tailplane_over_wing_area": lay["ht_area"] / d["wing"]["area"],
            "tailplane_root_le_behind_wing_root_te_ft": e["tailplane_root_le_behind_wing_root_te_ft"],
            "tail_arm_over_fuselage_length": lay["arm"] / d1["fuselage"]["length"]}


def row9_on_the_loft(c, c1, lay):
    """P3's row 9 on the loft of a layout: r0's loft with the layout's wing, tails and wheels (P4's
    record_with_layout), the longer fuselage, and the spinner and propeller plane moved aft with it."""
    model = ac.build(p4.record_with_layout(c["d"], c["L"], lay), c["L"], c["A"])
    ext = c1["body"].length - c["body"].length
    s = model["spinner"]
    model.update(fuselage=c1["body"], spinner=Ellipsoid((s.centre[0] + ext, 0.0, 0.0), s.a, s.b, s.c))
    model["propeller"]["x"] += ext
    return gates.row9_propeller_disc(model, ac.meshes(model))


# ---- the selection rule (data/task12/pd_p4b_choices.yaml, written before any run) ---------------------------------
def select(pool, tie_h):
    """pool: {name: measures}. Step 1: every payload-on row passes. Step 2: if any of those needs no ballast with
    the payload off, only those stay. Step 3: the most hours on station (weight and wetted areas both counted).
    Step 4: within tie_h of the best, the least empty-weight change. Step 5: nobody left, nothing chosen."""
    step1 = [k for k, v in pool.items() if v["eligible"]]
    no_ballast = [k for k in step1 if pool[k]["payload_off_without_ballast"]]
    step2 = no_ballast or step1
    out = {"after_step_1": step1, "passing_payload_off_without_ballast": no_ballast, "after_step_2": step2,
           "failed_step_1": {k: [r for r in PAYLOAD_ON_ROWS if v["rows"][r] != "pass"] for k, v in pool.items() if not v["eligible"]}}
    if not step2:
        return dict(out, chosen=None, reason="no layout passes every payload-on row: the trade goes to the owner")
    best = max(pool[k]["hours_for_rule"] for k in step2)
    tied = [k for k in step2 if best - pool[k]["hours_for_rule"] <= tie_h]
    chosen = min(tied, key=lambda k: pool[k]["empty_weight_change_lb"])
    return dict(out, best_hours=best, tied_on_hours=tied, chosen=chosen,
                reason="most hours on station" + ("" if len(tied) == 1 else "; tie broken by the least empty-weight change"))


# ---- the run -------------------------------------------------------------------------------------------------------
def context():
    """P4's context plus this package's choices, the area of r0's body and the drag and hours of r0 unchanged."""
    from measurement import info_gap
    c = p4.context()
    c["p4b"] = m.load_yaml(CHOICES)
    c["skin0"] = skin_area(c["body"])
    c["built"] = info_gap.Built(R0 / "design_pusher.json")
    zero = {"horizontal_tail": 0.0, "vertical_tail": 0.0, "fuselage": 0.0}
    c["hours_base"] = drag_and_hours(c["built"], c["d"], zero, 0.0)["at_r0_weight"]
    return c


def trade(c, shaft_lb_per_ft, log, full=True):
    """The candidates at one shaft weight. Returns {name: {"measures", "layout", ("evaluation", "row9_on_the_loft")}},
    the arm scan's names in order, and what could not be solved. full=False leaves out the stored evaluations
    and the loft check (the band-end repeats)."""
    d, L = c["d"], c["L"]
    lay0 = m.base_layout(d, c["p3"])
    quiet = lambda msg: None
    out, unsolved = {}, {}

    def add(name, lay, c1, note):
        e = p4.evaluate(c1, lay, name, log if full else quiet)
        mm = measures(c, c1, lay0, lay, e, c["built"])
        out[name] = {"what": note, "layout": lay, "measures": mm}
        if full:
            out[name].update(evaluation=e, row9_on_the_loft=row9_on_the_loft(c, c1, lay))
        log(f"{name} (shaft {shaft_lb_per_ft:g} lb/ft): arm {lay['arm']:.3f} ft, extension {mm['extension_ft']:.3f} ft, empty weight "
            f"{mm['empty_weight_change_lb']:+.2f} lb, hours {mm['hours_for_rule']:.3f}, rotation {mm['rotation_used_of_limit']:.3f}, "
            f"propeller clearance {mm['propeller_clearance_in']:.2f} in, eligible {mm['eligible']}")
    notes = c["p4b"]["candidates"]
    layA = m.solve_r1(d, L, lay0, c["tanks"], c["choices"], c["body"], c["src"], c["propeller_plane_x"])[0]
    add("A", layA, c, notes["A"])
    try:
        add("B", *solve(c, lay0, lay0["arm"], False, shaft_lb_per_ft), notes["B"])
    except ValueError as err:
        unsolved["B"] = f"no wing position between r0's and 3 ft aft of it gives a mean static margin of 0.10 ({err})"
        log("B: no solution")
    scan = []
    arms = np.linspace(layA["arm"], lay0["arm"], notes["arm_scan_points"])
    for i, arm in enumerate(arms):
        name = f"scan_{i:02d}"
        try:
            add(name, *solve(c, lay0, float(arm), True, shaft_lb_per_ft), f"arm scan, straight trailing edges, tail arm {arm:.3f} ft")
            scan.append(name)
        except ValueError as err:
            unsolved[name] = f"tail arm {arm:.3f} ft: no wing position gives a mean static margin of 0.10 ({err})"
            log(f"{name}: no solution")
    return out, scan, unsolved


def named(out, scan):
    """Which scan rows are Bs (r0's arm) and C (least empty-weight change among the eligible rows)."""
    ok = [k for k in scan if out[k]["measures"]["eligible"]]
    return {"Bs": scan[-1] if scan else None,
            "C": min(ok, key=lambda k: out[k]["measures"]["empty_weight_change_lb"]) if ok else None}


def table_row(v):
    """The numbers of one layout that the band-end repeats keep."""
    keys = ("eligible", "payload_off_without_ballast", "arm_ft", "extension_ft", "empty_weight_change_lb", "hours_for_rule",
            "rotation_used_of_limit", "propeller_clearance_in", "rows")
    return {k: v["measures"][k] for k in keys}


def findings(res):
    """The findings for r1 (PD-7), each with its numbers from this record."""
    sel, cand = res["selection"], res["candidates"]
    if sel["chosen"] is None:
        return ["No layout passes every payload-on row; nothing is chosen and the trade goes to the owner. Failed rows: "
                + "; ".join(f"{k}: {', '.join(v)}" for k, v in sel["failed_step_1"].items()) + "."]
    k = sel["chosen"]
    v, lay, a = cand[k]["measures"], cand[k]["layout"], cand["A"]["measures"]
    off = v["payload_off"]
    label = res["chosen_label"]
    out = [f"Layout for r1 (PD-21): {label}. Tail arm {v['arm_ft']:.3f} ft, tailplane {v['ht_area_ft2']:.2f} ft^2, fin {v['vt_area_ft2']:.2f} ft^2, "
           f"trailing edges {'straight' if v['straight_trailing_edges'] else 'as r0'}; wing leading edge at the root at {v['x_le_ft']:.3f} ft "
           f"({v['wing_shift_ft']:+.3f} ft from r0); main wheels at {v['x_main_ft']:.3f} ft; nose wheel unchanged.",
           f"Aft fuselage for r1: lengthened by {v['extension_ft']:.3f} ft to {v['fuselage_length_ft']:.3f} ft; the propeller plane moves to "
           f"{v['propeller_plane_x_ft']:.3f} ft; the engine stays at r0's station and a shaft of that added length carries the propeller.",
           f"Weights for r1, as changes on r0 (not re-sized): " + ", ".join(f"{n.replace('_', ' ')} {x:+.2f} lb" for n, x in v["weight_changes_lb"].items())
           + f" (the fuselage figure includes {v['shaft_lb']:.2f} lb of shaft at an assumed {res['shaft_lb_per_ft']['value']:g} lb/ft); empty weight "
           f"{v['empty_weight_change_lb']:+.2f} lb against {a['empty_weight_change_lb']:+.2f} lb for PD-20.",
           f"Drag and hours: wetted area {v['added_wetted_ft2']['total']:+.2f} ft^2, CD0 {v['drag_and_hours']['at_r0_weight']['delta_CD0']:+.6f}, hours on station "
           f"{v['drag_and_hours']['at_r0_weight']['delta_hours']:+.3f} h at r0's weight and fuel and {v['drag_and_hours']['with_empty_weight_change']['delta_hours']:+.3f} h "
           f"with the empty-weight change in the take-off weight (PD-20: {a['drag_and_hours']['at_r0_weight']['delta_hours']:+.3f} and "
           f"{a['drag_and_hours']['with_empty_weight_change']['delta_hours']:+.3f} h).",
           f"Rows on the chosen layout: static margin {v['sm_full']:.4f} full and {v['sm_empty']:.4f} empty; {v['payload_on_outside_envelope']} of "
           f"{v['payload_on_loadings']} payload-on loadings outside the envelope; nose-wheel load {100 * v['nose_load_payload_on'][0]:.1f} to "
           f"{100 * v['nose_load_payload_on'][1]:.1f} %; tail lift at rotation {v['rotation_used_of_limit']:.3f} of the limit (PD-20: {a['rotation_used_of_limit']:.3f}); "
           f"propeller ground clearance at rotation {v['propeller_clearance_in']:.2f} in (PD-20: {a['propeller_clearance_in']:.2f} in; at least "
           f"{res['ledger']['prop_clearance_in']:g} in).",
           f"Payload off: {v['payload_off_outside_envelope']} of {v['payload_off_loadings']} loadings are outside the envelope on the chosen layout, and on every "
           f"other layout of the trade. The aftmost payload-off centre of gravity is {off['behind_main_wheels_ft']:+.3f} ft from the main wheels (positive: behind). "
           f"Flight without the payload needs {off['ballast_every_loading_lb']:.0f} lb of ballast at the payload station to bring every payload-off loading "
           f"to the aft limit ({off['ballast_to_aft_limit_lb']:.0f} lb by P4's figure, which takes the aftmost loading only; {off['ballast_to_main_wheels_lb']:.0f} lb "
           f"only to bring the centre of gravity to the wheels); with it {off['with_that_ballast']['outside_envelope']} of {off['with_that_ballast']['loadings']} "
           f"loadings are outside the envelope. PD-20 needs {a['payload_off']['ballast_every_loading_lb']:.0f} lb ({a['payload_off']['ballast_to_aft_limit_lb']:.0f} lb by P4's figure). "
           "This is an operating limit for P8 (PD-13).",
           f"Moving the main wheels does not remove the ballast: it is the aft limit of R13 that the payload-off loadings break. With the wheels "
           f"moved to {off['main_wheels_moved_for_payload_off']['x_main_ft']:.3f} ft for payload-off tipback, the tail would need "
           f"{off['main_wheels_moved_for_payload_off']['rotation_used_of_limit']:.3f} of its limit at rotation.",
           f"Tail and wing: the tailplane is {v['tailplane_over_wing_area']:.3f} of the wing area with its root leading edge "
           f"{v['tailplane_root_le_behind_wing_root_te_ft']:.2f} ft behind the wing's root trailing edge (PD-20: {a['tailplane_over_wing_area']:.3f} and "
           f"{a['tailplane_root_le_behind_wing_root_te_ft']:.2f} ft).",
           f"The shaft weight is an assumption ({res['shaft_lb_per_ft']['value']:g} lb/ft, band {res['shaft_lb_per_ft']['band'][0]:g} to "
           f"{res['shaft_lb_per_ft']['band'][1]:g}). At the band ends the rule chooses: "
           + "; ".join(f"{r:g} lb/ft: {s['chosen_label']}" for r, s in ((s["shaft_lb_per_ft"], s) for s in res["shaft_band"])) + ".",
           "For r1 and P9, not answered here: Stage 1 needs the fuselage extension, the tail arm and the tails' leading-edge sweep as inputs; the shaft, "
           "its bearings and its critical speed are not designed; the tail roots sit on a slender tail cone whose structure is not sized; the form factor and "
           "the skin-friction length of the longer body are Stage 1's unchanged; the open items of P4 (sponson, tail roots on the engine bay) stand."]
    return out


def label_of(name, names, cand):
    """A readable name for a pool entry: A, B, or a scan row with its tail arm (and Bs or C if it is one)."""
    if name is None:
        return "none"
    if name in ("A", "B"):
        return name
    also = [k for k, v in names.items() if v == name]
    return (" = ".join(also) + " = " if also else "") + f"arm scan row {name[5:]} (tail arm {cand[name]['measures']['arm_ft']:.3f} ft)"


def run(out, log):
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P4b starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "arrangement": p3.ARRANGEMENT,
             "p3_record": p4.P3_RECORD, "p2_record": p4.P2_RECORD, "p6_record": p4.P6_RECORD, "p4_record": P4_RECORD,
             "p4_sources": m.SOURCES, "p4_choices": m.CHOICES, "choices": CHOICES}
    c = context()
    d, L, ch = c["d"], c["L"], c["p4b"]
    log(f"commit {tree['commit']}, clean tree")
    shaft = ch["extension"]["shaft_lb_per_ft"]
    res = {"inputs": dict(tree, command="python -m prelim.p4b_trade " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P4b", python=platform.python_version(),
                          numpy=np.__version__, scipy=scipy.__version__, pyyaml=yaml.__version__, matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()},
                          sha256={k: p4.sha256(p) for k, p in files.items()}),
           "evidence_class": EVIDENCE_CLASS, "baseline": str(R0.relative_to(REPO)), "choices": ch, "p4_choices": c["choices"],
           "shaft_lb_per_ft": shaft, "shaft_tube_support": shaft_tube(d, L, ch["extension"]["shaft_tube_for_support"]),
           "ledger": {k: L[k] for k in ("prop_clearance_in", "tipback_angle_deg", "overturn_max_deg", "tail_cl_max_rotation", "tail_cl_max_trim",
                                        "rotation_angle_deg_pusher", "propeller_rpm")},
           "clearance_ft": m.val(c["choices"]["r1"]["propeller_clearance_ft"]),
           "r0": {"W0_lb": d["W0_lb"], "fuel_lb": d["fuel_lb"], "payload_lb": d["payload_lb"], "wing": d["wing"], "fuselage": d["fuselage"],
                  "tail_arm_ft": d["tail_arm_ft"], "propeller_plane_x_ft": c["propeller_plane_x"], "propeller_diameter_ft": d["propeller_diameter_ft"],
                  "skin_area_of_the_loft_body_ft2": c["skin0"], "layout_as_p3_arranged": m.base_layout(d, c["p3"]),
                  "empty_weight_lb": sum(d["components_lb"].values()), "drag_and_hours": c["hours_base"],
                  "record_CD0_mission_altitude": d["CD0"]["mission_altitude"]}}
    cand, scan, unsolved = trade(c, m.val(shaft), log)
    names = named(cand, scan)
    res.update(candidates=cand, arm_scan=scan, unsolved=unsolved, named=names)
    pool = {k: v["measures"] for k, v in cand.items()}
    res["selection"] = select(pool, ch["selection_rule"]["hours_tie_h"])
    res["chosen_label"] = label_of(res["selection"]["chosen"], names, cand)
    log(f"selection at {m.val(shaft):g} lb/ft: {res['chosen_label']} ({res['selection']['reason']})")
    res["shaft_band"] = []
    for rate in shaft["band"]:
        cb, sb, ub = trade(c, rate, log, full=False)
        sel = select({k: v["measures"] for k, v in cb.items()}, ch["selection_rule"]["hours_tie_h"])
        nb = named(cb, sb)
        res["shaft_band"].append({"shaft_lb_per_ft": rate, "selection": sel, "named": nb, "unsolved": ub,
                                  "chosen_label": label_of(sel["chosen"], nb, cb), "table": {k: table_row(v) for k, v in cb.items()}})
        log(f"selection at {rate:g} lb/ft: {res['shaft_band'][-1]['chosen_label']}")
    # the stored evaluations are kept for the named layouts only; the other scan rows keep their layout and measures
    keep = {"A", "B", names["Bs"], names["C"], res["selection"]["chosen"]}
    for k, v in cand.items():
        if k not in keep:
            v.pop("evaluation", None)
    res["findings_for_r1"] = findings(res)
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == tree["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p4b.json").write_text(json.dumps(p4._plain(res), indent=1))
    log(f"done ({time.time() - t0:.0f} s)")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the figures (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and figures from OUT/p4b.json")
    a = ap.parse_args(argv)
    out = (REPO / a.out).resolve()
    if not a.report_only:
        t0 = time.time()
        lines = []

        def log(msg):
            lines.append(f"[{time.time() - t0:7.0f} s] {msg}")
            print(lines[-1], flush=True)
            if out.exists():
                (out / "run.log").write_text("\n".join(lines) + "\n")
        run(out, log)
    if a.report:
        from prelim import p4b_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p4b_report.write_figures(out, figures)
        report.write_text(p4b_report.report_text(out))


if __name__ == "__main__":
    main()

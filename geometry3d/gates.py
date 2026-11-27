"""Geometry gates of package P3 (spec docs/specs/task12_preliminary_design.md, P3, gates 1 to 8 and two added
rows). Each function returns a dict with its numbers and "verdict": "pass", "fail" (with the offending
values), "reported" (no tolerance in the spec) or "not run" (with the reason). Tolerances are the spec's or
were fixed in tests/task12_pd/test_p3_geometry.py before the recorded run.
"""
import math

import numpy as np

from geometry3d import aircraft as ac
from geometry3d import fuselage as fz
from geometry3d import mesh

TOL_WETTED = 0.05            # gate 3, spec
TOL_OPENVSP = 0.02           # gate 8, spec
TOL_TARGET = 1e-9            # gate 2, spec (mean chord and its station); also used for the conic targets
TOL_ROUND_TRIP = 1e-9        # gate 7, spec
# gate 5: the slope of the section perimeter and of the section area along the body, taken over steps of
# 1/4000 of the length, may change from one step to the next by at most this share of the largest perimeter
# (area) per foot. A break in a control line (the 60 % station of the Stage 1 body) changes it by 0.07 (0.15)
# whatever the step; a smooth line changes it in proportion to the step. Not judged over the first 5 % of the
# length, where the blunt nose has a vertical tangent.
SMOOTH_STEPS, SMOOTH_FROM, SMOOTH_BOUND = 4000, 0.05, 0.01
AFT_BODY_DEG = (12.0, 30.0)  # Raymer 8.2, p. 155-156, Fig. 8.1: 10-12 deg; about 30 deg ahead of a pusher propeller


def rel(a, b):
    return a / b - 1.0


def gate1_watertight(parts):
    rows = {name: mesh.watertight(V, T) for name, (V, T) in parts.items()}
    bad = [n for n, r in rows.items() if not r["ok"]]
    return {"parts": rows, "failing": bad, "verdict": "fail" if bad else "pass"}


def conic_targets():
    """Raymer (7.4), p. 132. Circle: the conic from (0, 1) to (1, 0) with tangents meeting at (1, 1) (equal
    tangents) and rho = sqrt(2) - 1 must keep the distance 1 from the origin; with the printed 0.4142 it does so
    to the rounding of that number. Parabola: with rho = 0.5 the conic from (-1, 1) to (1, 1) with tangents
    meeting at (0, -1) is y = x^2."""
    def circle(rho):
        return float(np.abs(np.linalg.norm(fz.conic((0, 1), (1, 0), (1, 1), rho, 201), axis=1) - 1.0).max())
    p = fz.conic((-1, 1), (1, 1), (0, -1), 0.5, 201)
    return {"circle_radius_error_exact_rho": circle(fz.RHO_CIRCLE), "circle_radius_error_printed_rho": circle(0.4142),
            "parabola_error": float(np.abs(p[:, 1] - p[:, 0] ** 2).max())}


def gate2_targets(m, d):
    c = conic_targets()
    mac, y_mac, S = m["wing"].mean_chord()
    out = dict(c, mac_ft=mac, mac_y_ft=y_mac, area_ft2=S, mac_rel=rel(mac, d["wing"]["mac"]),
               mac_y_rel=rel(y_mac, d["wing"]["mac_y"]), area_rel=rel(S, d["wing"]["area"]))
    ok = (c["circle_radius_error_exact_rho"] < TOL_TARGET and c["circle_radius_error_printed_rho"] < 1e-4
          and c["parabola_error"] < TOL_TARGET and abs(out["mac_rel"]) < TOL_TARGET and abs(out["mac_y_rel"]) < TOL_TARGET)
    return dict(out, verdict="pass" if ok else "fail")


def stage1_areas(d, L):
    """The wetted areas the Stage 1 drag build-up uses (conceptual/uav.py, _geometry and _sponsons), computed
    again from the record: wing S_exposed (1.977 + 0.52 t/c) with S_exposed = S - c_root d_f (7.11); tails the
    same on their whole area; fuselage as recorded (7.12 with the fill factor); sponsons 2 x 3.4 x fill x
    length x depth."""
    w, gt = d["wing"], d["layout"]["gear_track"]
    k_w, k_t = 1.977 + 0.52 * L["wing_t_c"], 1.977 + 0.52 * L["tail_t_c"]
    return {"wing": (w["area"] - w["root_chord"] * d["fuselage"]["diameter"]) * k_w,
            "fuselage": d["fuselage"]["s_wet"], "horizontal_tail": d["horizontal_tail"]["area"] * k_t,
            "vertical_tail": d["vertical_tail"]["area"] * k_t,
            "sponsons": 2 * 3.4 * L["fuselage_fill"] * gt["sponson_length_ft"] * gt["sponson_depth_ft"]}


def gate3_wetted(m, parts, d, L):
    per, comp = ac.wetted_areas(m, parts)
    s1 = stage1_areas(d, L)
    top, side = m["fuselage"].projected_areas()
    exposed = {n: ac.exposed_planform(m, n) for n in ("wing", "horizontal_tail", "vertical_tail")}
    raymer = {"wing": exposed["wing"] * (1.977 + 0.52 * L["wing_t_c"]),                      # (7.11)
              "horizontal_tail": exposed["horizontal_tail"] * (1.977 + 0.52 * L["tail_t_c"]),
              "vertical_tail": exposed["vertical_tail"] * (1.977 + 0.52 * L["tail_t_c"]),
              "fuselage": 3.4 * (top + side) / 2.0}                                           # (7.12)
    rows = {}
    for k in ac.COMPONENTS:
        r = {"loft_wetted_ft2": comp[k]["wetted_ft2"], "loft_whole_ft2": comp[k]["whole_ft2"], "stage1_ft2": s1[k],
             "loft_over_stage1": rel(comp[k]["wetted_ft2"], s1[k]), "raymer_form_on_loft_ft2": raymer.get(k)}
        r["loft_over_raymer_form"] = None if k not in raymer else rel(comp[k]["wetted_ft2"], raymer[k])
        r["verdict"] = "pass" if abs(r["loft_over_stage1"]) <= TOL_WETTED else "fail"
        rows[k] = r
    failing = [k for k, r in rows.items() if r["verdict"] == "fail"]
    return {"components": rows, "parts": per, "exposed_planform_ft2": exposed, "tolerance": TOL_WETTED,
            "fuselage_projected_ft2": {"top": top, "side": side,
                                       "fill_top": top / (m["L_f"] * m["D_f"]), "fill_side": side / (m["L_f"] * m["D_f"])},
            "total_loft_ft2": sum(r["loft_wetted_ft2"] for r in rows.values()),
            "total_stage1_ft2": sum(s1.values()), "failing": failing, "verdict": "fail" if failing else "pass"}


def gate4_volumes(m, parts, d, L, A):
    a = A["arrangement"]
    clear = ac.val(a["box_clearance_in"]) / 12.0
    boxes, info = ac.arrangement(m, d, L, A)
    f, w = m["fuselage"], m["wing"]
    # tanks: both wings, between the spars, from the fuselage side (Stage 1: d_f/2) to the ledger's span fraction
    f0, f1 = info["spar_fractions"]
    y0, y1 = 0.5 * m["D_f"], L["wing_tank_span_fraction"] * w.half_span
    gross = 2.0 * w.volume_between(f0, f1, y0, y1)
    need, claim = d["fuel_volume_ft3"]["needed"], d["fuel_volume_ft3"]["available"]
    tank = {"gross_ft3": gross, "usable_ft3": gross * L["wing_tank_usable"], "needed_ft3": need,
            "stage1_claim_ft3": claim, "usable_over_claim": rel(gross * L["wing_tank_usable"], claim),
            "margin_ft3": gross * L["wing_tank_usable"] - need, "span_stations_ft": [y0, y1],
            "verdict": "pass" if gross * L["wing_tank_usable"] >= need else "fail"}
    # fuselage volume: sections integrated over the length, against the closed surface and Raymer (7.13)
    top, side = f.projected_areas()
    vol_sections, vol_mesh = f.volume_by_sections(), mesh.volume(*parts["fuselage"])
    fus = {"by_sections_ft3": vol_sections, "by_surface_ft3": vol_mesh, "raymer_7_13_ft3": 3.4 * top * side / (4 * f.length),
           "sections_over_surface": rel(vol_sections, vol_mesh)}
    # boxes inside their skin
    rows = {}
    for name, b in boxes.items():
        r = {"lo": [float(v) for v in b["lo"]], "hi": [float(v) for v in b["hi"]], "volume_ft3": ac.box_volume(b), "inside": b["in"]}
        if b["in"] is not None:
            r["clearance_in"] = 12.0 * ac.clearance_margin(m[b["in"]], b)
            r["verdict"] = "pass" if r["clearance_in"] >= 12.0 * clear - 1e-6 else "fail"
        rows[name] = r
    names = list(boxes)
    overlaps = [{"a": p, "b": q, "volume_ft3": ac.overlap_volume(boxes[p], boxes[q])}
                for i, p in enumerate(names) for q in names[i + 1:] if ac.overlap_volume(boxes[p], boxes[q]) > 0.0]
    # the tanks are not boxes: a box overlaps a tank if one of its edge points lies in the wing between the spars
    for name, b in boxes.items():
        if name == "wing_carry_through":
            continue
        P = ac.box_points(b, 15)
        s = np.abs(P[:, 1])
        xi = (P[:, 0] - w.x_le) / w.chord(np.clip(s, 0, w.half_span))
        hit = w.inside(P) & (xi > f0) & (xi < f1) & (s > y0) & (s < y1)
        if hit.any():
            overlaps.append({"a": name, "b": "wing_tank", "volume_ft3": None, "points_inside": int(hit.sum())})
    # payload and avionics volumes
    pay_boxes = [boxes["payload_bay_forward"], boxes["payload_bay_aft"]]
    pay_vol = sum(ac.box_volume(b) for b in pay_boxes)
    pay_need = L["payload_lb"] / ac.val(a["payload_density_lb_ft3"])
    pay_x = sum(ac.box_volume(b) * 0.5 * (b["lo"][0] + b["hi"][0]) for b in pay_boxes) / pay_vol
    av_need = d["components_lb"]["avionics"] / ac.val(a["avionics_density_lb_ft3"])
    av = boxes["avionics_bay"]
    payload = {"bay_ft3": pay_vol, "needed_ft3": pay_need, "centroid_x_ft": pay_x,
               "verdict": "pass" if pay_vol >= pay_need else "fail"}
    avionics = {"bay_ft3": ac.box_volume(av), "needed_ft3": av_need, "centroid_x_ft": 0.5 * (av["lo"][0] + av["hi"][0]),
                "verdict": "pass" if ac.box_volume(av) >= av_need else "fail"}
    failing = ([f"box {n}: clearance {r['clearance_in']:.2f} in" for n, r in rows.items() if r.get("verdict") == "fail"]
               + [f"overlap {o['a']} / {o['b']}" for o in overlaps]
               + [n for n, r in (("tank volume", tank), ("payload bay volume", payload), ("avionics bay volume", avionics))
                  if r["verdict"] == "fail"])
    return {"tank": tank, "fuselage_volume": fus, "boxes": rows, "overlaps": overlaps, "payload_bay": payload,
            "avionics_bay": avionics, "clearance_required_in": 12.0 * clear, "legs": info["legs"],
            "spar_fractions": info["spar_fractions"], "failing": failing, "verdict": "fail" if failing else "pass"}


def slope_changes(body, steps=SMOOTH_STEPS, start=SMOOTH_FROM):
    """Largest change of slope between neighbouring steps, of the section perimeter and of the section area
    along the body, each over its largest value (per foot); and where it is."""
    x = np.linspace(start * body.length, body.length, int(steps * (1 - start)) + 1)
    per, area = body.section_measures(x, n=17)
    out = {}
    for name, q in (("perimeter", per), ("area", area)):
        slope = np.diff(q) / np.diff(x)
        jump = np.abs(np.diff(slope)) / q.max()
        k = int(jump.argmax())
        out[name] = {"largest_slope_change_per_ft": float(jump[k]), "at_x_ft": float(x[k + 1])}
    return out


def gate5_smoothness(m):
    f = m["fuselage"]
    out = slope_changes(f)
    x = np.linspace(0.6 * f.length, f.length, 2001)
    half, top, bottom, _ = f.lines(x)
    angles = {k: float(np.degrees(np.arctan(np.max(-np.gradient(q, x))))) for k, q in (("side", half), ("top", top), ("bottom", bottom))}
    ok = all(v["largest_slope_change_per_ft"] <= SMOOTH_BOUND for v in out.values())
    return dict(out, bound=SMOOTH_BOUND, steps=SMOOTH_STEPS, judged_from_x_over_length=SMOOTH_FROM,
                aft_body_angle_deg=angles, aft_body_guides_deg=list(AFT_BODY_DEG),
                aft_body_over_pusher_guide=max(angles.values()) > AFT_BODY_DEG[1], verdict="pass" if ok else "fail")


def gate6_ground(m, parts, d, L):
    """Ground angles on the loft (Raymer 11.2, Fig. 11.4, p. 232). The aircraft turns nose-up about the main
    wheels' ground contact; the height of a point (x, z) above the ground at the angle th is
    (z - z_ground) cos(th) - (x - x_main) sin(th)."""
    lay, p, zg = d["layout"], m["propeller"], m["ground_z"]
    xm = lay["x_main"]
    th = math.radians(L["rotation_angle_deg_pusher"])

    def height(x, z, angle=th):
        return (z - zg) * math.cos(angle) - (x - xm) * math.sin(angle)

    tip = height(p["x"], p["z"]) - p["radius"] * math.cos(th)                # lowest point of the tilted disc
    stage1 = height(m["L_f"], p["z"]) - p["radius"]                           # Stage 1's own expression
    lowest = {n: float(height(V[:, 0], V[:, 2]).min()) for n, (V, _) in parts.items()}
    worst = min(lowest, key=lowest.get)
    # largest nose-up angle before something behind the wheels touches: the propeller tip or the loft
    limit = {"propeller": math.degrees(math.atan2(p["z"] - p["radius"] - zg, p["x"] - xm))}
    for n, (V, _) in parts.items():
        aft = V[V[:, 0] > xm + 0.5]
        if len(aft):
            limit[n] = float(np.degrees(np.arctan2(aft[:, 2] - zg, aft[:, 0] - xm)).min())
    first = min(limit, key=limit.get)
    h = -zg                                                                    # CG on the reference line (Stage 1)
    cg_aft = max(lay["cg_full"], lay["cg_empty"])
    cg_angle = math.degrees(math.atan2(xm - cg_aft, h))
    x_nose = d["stations"]["nose_gear"]["x"]
    delta = math.atan2(lay["gear_track"]["half_track_ft"], xm - x_nose)
    overturn = {k: math.degrees(math.atan2(h, (lay[k] - x_nose) * math.sin(delta))) for k in ("cg_full", "cg_empty")}
    need = L["prop_clearance_in"]
    tipback_needed = max(L["tipback_angle_deg"], L["rotation_angle_deg_pusher"])
    ok = (12 * tip >= need and lowest[worst] >= 0.0 and cg_angle >= tipback_needed - 1e-6
          and max(overturn.values()) <= L["overturn_max_deg"] + 1e-6 and limit[first] >= L["rotation_angle_deg_pusher"])
    return {"rotation_deg": L["rotation_angle_deg_pusher"], "propeller_clearance_in": 12 * tip,
            "propeller_clearance_stage1_expression_in": 12 * stage1, "propeller_clearance_record_in": lay["prop_clearance_in"],
            "propeller_clearance_required_in": need, "lowest_point_at_rotation_in": 12 * lowest[worst],
            "lowest_part_at_rotation": worst, "first_to_touch": first, "angle_at_first_touch_deg": limit[first],
            "touch_angles_deg": limit, "cg_angle_at_main_wheel_deg": cg_angle, "tipback_needed_deg": tipback_needed,
            "overturn_deg": overturn, "overturn_max_deg": L["overturn_max_deg"], "verdict": "pass" if ok else "fail"}


def gate7_round_trip(parts, path):
    mesh.write_stl(path, parts)
    back = mesh.read_stl(path)
    rows, worst = {}, 0.0
    for name, (V, T) in parts.items():
        a0, v0 = mesh.area(V, T), mesh.volume(V, T)
        a1, v1 = mesh.area(*back[name]), mesh.volume(*back[name])
        rows[name] = {"area_rel": rel(a1, a0), "volume_rel": rel(v1, v0)}
        worst = max(worst, abs(rows[name]["area_rel"]), abs(rows[name]["volume_rel"]))
    return {"parts": rows, "largest_relative_difference": worst, "triangles": int(sum(len(T) for _, T in parts.values())),
            "verdict": "pass" if worst <= TOL_ROUND_TRIP and set(back) == set(parts) else "fail"}


def gate8_openvsp(comp, vsp):
    """comp: the loft's areas per build-up component (gate 3); vsp: the record of geometry3d/openvsp_check.py,
    or a string saying why it did not run."""
    if isinstance(vsp, str):
        return {"verdict": "not run", "reason": vsp}
    rows = {}
    for k, ps in ac.COMPONENTS.items():
        r = {"loft_wetted_ft2": comp[k]["loft_wetted_ft2"], "loft_whole_ft2": comp[k]["loft_whole_ft2"]}
        for meshname in ("default_mesh", "fine_mesh"):
            for q in ("wetted_ft2", "whole_ft2"):
                r[f"openvsp_{meshname}_{q}"] = sum(vsp[meshname][q][p] for p in ps)
        r["wetted_rel_default"] = rel(r["loft_wetted_ft2"], r["openvsp_default_mesh_wetted_ft2"])
        r["wetted_rel_fine"] = rel(r["loft_wetted_ft2"], r["openvsp_fine_mesh_wetted_ft2"])
        r["whole_rel_fine"] = rel(r["loft_whole_ft2"], r["openvsp_fine_mesh_whole_ft2"])
        r["verdict"] = "pass" if abs(r["wetted_rel_default"]) <= TOL_OPENVSP else "fail"
        rows[k] = r
    failing = [k for k, r in rows.items() if r["verdict"] == "fail"]
    return {"components": rows, "tolerance": TOL_OPENVSP, "openvsp": vsp["openvsp"], "failing": failing,
            "judged_on": "OpenVSP's default surface mesh, as conceptual/openvsp_model.py uses it",
            "verdict": "fail" if failing else "pass"}


def row9_propeller_disc(m, parts):
    """Added row: no part of the airframe behind the propeller plane inside the disc. For each part: how far its
    rearmost point inside the disc's radius lies behind the propeller plane (negative: ahead of it)."""
    p = m["propeller"]
    rows = {}
    for n, (V, _) in parts.items():
        if n == "spinner":
            continue
        inside = np.hypot(V[:, 1], V[:, 2] - p["z"]) < p["radius"]
        rows[n] = float(V[inside, 0].max() - p["x"]) if inside.any() else None
    failing = {n: v for n, v in rows.items() if v is not None and v > 0.0}
    return {"propeller_plane_x_ft": p["x"], "disc_radius_ft": p["radius"], "behind_plane_ft": rows,
            "failing": failing, "verdict": "fail" if failing else "pass"}

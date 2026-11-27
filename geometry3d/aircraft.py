"""The lofted aircraft of r0: bodies, meshes, wetted areas and the internal boxes.

build() reads the Stage 1 record (design_pusher.json), its ledger values and the P3 choices
(data/task12/pd_p3_arrangement.yaml) and returns everything the gates need. The layout convention is that of
conceptual/render3d.py and conceptual/openvsp_model.py; the fuselage alone is new (a conic loft).
"""
import math

import numpy as np

from conceptual import geometry_sizing as geo
from geometry3d import mesh
from geometry3d.fuselage import Body
from geometry3d.surfaces import Ellipsoid, LiftingSurface

WING_SECTION, TAIL_SECTION = "4415", "0012"          # PD-5; fixed for the wing by P2


def val(entry):
    """A choice of the arrangement file: either a bare value or {value, band, source}."""
    return entry["value"] if isinstance(entry, dict) else entry


def stage1_radius(x, L_f, D_f):
    """Radius of the Stage 1 body of revolution (conceptual/render3d.py): nose ellipse to 20 % of the length,
    constant to 60 %, straight taper to 15 % of the diameter."""
    t = x / L_f
    if t < 0.2:
        return 0.5 * D_f * math.sqrt(max(0.0, 1 - (1 - t / 0.2) ** 2))
    return 0.5 * D_f * (1.0 if t <= 0.6 else max(0.15, 1 - (t - 0.6) / 0.4 * 0.85))


def build(d, L, A):
    """All bodies of the loft. d: the design record; L: ledger values; A: the arrangement file."""
    lo, w, ht, vt, lay = A["loft"], d["wing"], d["horizontal_tail"], d["vertical_tail"], d["layout"]
    L_f, D_f = d["fuselage"]["length"], d["fuselage"]["diameter"]
    R = 0.5 * D_f
    r_spin = 0.5 * val(lo["spinner_diameter_over_propeller"]) * d["propeller_diameter_ft"]
    rows = [(x * L_f, *(r_spin if v is None else v * R for v in (h, t, b)), rho)
            for x, h, t, b, rho in lo["fuselage_stations"]]
    m = {"L_f": L_f, "D_f": D_f, "spinner_radius": r_spin}
    m["fuselage"] = Body(rows, lo["nose_length_over_length"] * L_f)
    z_w = lo["wing_z_over_diameter"] * D_f
    m["wing"] = LiftingSurface(WING_SECTION, lay["x_le"], z_w, w["span"] / 2, w["root_chord"], w["tip_chord"])
    # r0's record has no tail sweep: the root leading edges are a quarter of the mean chord ahead of the tail arm's
    # station, the tailplane unswept and the fin at the drawing's slope. A record with "le_slope" in a tail (P4,
    # PD-20) gives that tail's leading-edge slope and has the mean chord's quarter point at the tail arm.
    x_ht = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * ht["mac"] - ht.get("le_slope", 0.0) * ht.get("mac_y", 0.0)
    m["horizontal_tail"] = LiftingSurface(TAIL_SECTION, x_ht, lo["tail_z_over_diameter"] * D_f, ht["span"] / 2,
                                          ht["root_chord"], ht["tip_chord"], ht.get("le_slope", 0.0))
    x_vt = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * vt["mac"] - vt.get("le_slope", 0.0) * vt.get("mac_y", 0.0)
    z_vt = lo["fin_root_z_over_stage1_radius"] * stage1_radius(x_vt, L_f, D_f)
    m["vertical_tail"] = LiftingSurface(TAIL_SECTION, x_vt, z_vt, vt["height"], vt["root_chord"],
                                        L["vt_taper"] * vt["root_chord"], vt.get("le_slope", lo["fin_le_slope"]), vertical=True)
    gt = lay["gear_track"]
    sl, sd = gt["sponson_length_ft"], gt["sponson_depth_ft"]
    fa, fb, fc = lo["sponson_semi_axes_over_size"]
    xs = lay["x_main"] - lo["sponson_centre_ahead_of_main_wheel_over_length"] * sl
    zs = z_w - lo["sponson_centre_below_wing_over_depth"] * sd
    for side, sign in (("left", -1.0), ("right", 1.0)):
        m["sponson_" + side] = Ellipsoid((xs, sign * gt["half_track_ft"], zs), fa * sl, fb * sd, fc * sd)
    r_t = lo["turret_radius_ft"]
    m["turret"] = Ellipsoid((d["stations"]["payload"]["x"], 0.0, -R), r_t, r_t, r_t)
    m["spinner"] = Ellipsoid((L_f, 0.0, 0.0), lo["spinner_length_over_diameter"] * 2 * r_spin, r_spin, r_spin)
    m["propeller"] = {"x": L_f + lo["propeller_plane_behind_fuselage_ft"], "z": L.get("prop_hub_offset_ft", 0.0),
                      "radius": 0.5 * d["propeller_diameter_ft"]}
    m["ground_z"] = -(R + d["gear_length_in"] / 12.0)        # Stage 1: the reference line is h_cg above the ground
    m["tyre_main"] = {k: v / 12.0 for k, v in geo.main_tyre_in(L["main_wheel_load_fraction"] * d["W0_lb"]).items()}
    m["tyre_nose"] = {k: L["nose_tyre_scale"] * v for k, v in m["tyre_main"].items()}
    return m


PARTS = ("fuselage", "wing", "horizontal_tail", "vertical_tail", "sponson_left", "sponson_right", "turret", "spinner")
# the drag build-up's components and the parts of the loft that make each
COMPONENTS = {"wing": ("wing",), "fuselage": ("fuselage",), "horizontal_tail": ("horizontal_tail",),
              "vertical_tail": ("vertical_tail",), "sponsons": ("sponson_left", "sponson_right")}


def meshes(m, fine=1):
    """{part: (V, T)}. fine = 2 doubles the number of stations and of points round each section."""
    f = m["fuselage"]
    side = float(f.lines(np.array([m["wing"].x_le + 0.4 * m["wing"].c_root]))[0][0])    # fuselage side at the wing
    out = {"fuselage": mesh.loft(f.rings(100 * fine, 1 + 8 * fine), start=(0.0, 0.0, 0.0), end="fan")}
    n = 1 + 30 * fine
    out["wing"] = mesh.loft(m["wing"].rings(16 * fine, n, extra=(side,)), "strip", "strip")
    out["horizontal_tail"] = mesh.loft(m["horizontal_tail"].rings(12 * fine, n), "strip", "strip")
    out["vertical_tail"] = mesh.loft(m["vertical_tail"].rings(12 * fine, n), "strip", "strip")
    for name in ("sponson_left", "sponson_right", "turret", "spinner"):
        e = m[name]
        a, b = e.ends()
        out[name] = mesh.loft(e.rings(16 * fine, 16 * fine), start=a, end=b)
    return out


def wetted_areas(m, parts):
    """Wetted area of each part: the triangles whose middle point is not inside any other part. Also the
    whole surface of the part, and the two summed per drag-build-up component."""
    per = {}
    for name, (V, T) in parts.items():
        a, c = mesh.areas(V, T), mesh.centroids(V, T)
        hidden = np.zeros(len(T), dtype=bool)
        for other in PARTS:
            if other != name:
                hidden |= m[other].inside(c)
        per[name] = {"whole_ft2": float(a.sum()), "wetted_ft2": float(a[~hidden].sum())}
    comp = {k: {q: sum(per[p][q] for p in ps) for q in ("whole_ft2", "wetted_ft2")} for k, ps in COMPONENTS.items()}
    return per, comp


def exposed_planform(m, name, n_span=400, n_chord=100):
    """Planform area of a surface outside the fuselage skin: the chord plane is cut into cells and a cell counts
    when its middle is not inside the fuselage (both halves of a wing or tailplane)."""
    s = m[name]
    eta = (np.arange(n_span) + 0.5) / n_span * s.half_span
    xi = (np.arange(n_chord) + 0.5) / n_chord
    total = 0.0
    for e in eta:
        c = s.chord(e)
        x = s.x_le + s.le_slope * e + xi * c
        P = np.column_stack([x, np.zeros_like(x), np.full_like(x, s.z0 + e)] if s.vertical
                            else [x, np.full_like(x, e), np.full_like(x, s.z0)])
        total += np.sum(~m["fuselage"].inside(P)) * c / n_chord * s.half_span / n_span
    return float(total if s.vertical else 2.0 * total)


# ---- E4: internal arrangement as boxes ---------------------------------------------------------------------
def box(x0, x1, y0, y1, z0, z1):
    return {"lo": [min(x0, x1), min(y0, y1), min(z0, z1)], "hi": [max(x0, x1), max(y0, y1), max(z0, z1)]}


def box_volume(b):
    return float(np.prod(np.subtract(b["hi"], b["lo"])))


def stowed_gear(pivot, axle_ground, tyre, strut_w, gap, direction):
    """Boxes of a retracted gear leg. The leg turns about its pivot (x, y, z) through a right angle, aft
    (direction +1) or forward (-1), so the axle goes from its place on the ground (below the pivot) to the
    same distance along x. Returns the leg length (pivot to axle), two boxes round the two halves of the leg
    and one round the tyre, each with `gap` to spare. The axle is stowed at the pivot's height."""
    px, py, pz = pivot
    leg = pz - axle_ground
    r, half_w = 0.5 * tyre["diameter"], 0.5 * tyre["width"]
    ax = px + direction * leg
    hs = 0.5 * strut_w + gap
    mid = px + direction * 0.5 * (leg - r)
    end = ax - direction * (r + gap)
    boxes = {"leg_1": box(px - direction * hs, mid, py - hs, py + hs, pz - hs, pz + hs),
             "leg_2": box(mid, end, py - hs, py + hs, pz - hs, pz + hs),
             "wheel": box(end, ax + direction * (r + gap), py - half_w - gap, py + half_w + gap,
                          pz - r - gap, pz + r + gap)}
    return leg, ax, boxes


def arrangement(m, d, L, A):
    """The boxes of E4, {name: {"lo", "hi", "in": the body that must hold it}}, and what they were built from."""
    a = A["arrangement"]
    st, lay, w = d["stations"], d["layout"], m["wing"]
    gap, strut = a["gear_bay_gap_in"] / 12.0, L["strut_width_in"] / 12.0
    el, ew, eh = (v / 12.0 for v in a["engine_envelope_in"])
    xe, ze = st["installed_engine"]["x"], a["engine_centre_z_ft"]
    boxes = {"engine": dict(box(xe - el / 2, xe + el / 2, -ew / 2, ew / 2, ze - eh / 2, ze + eh / 2), **{"in": "fuselage"})}
    for name in ("payload_bay_forward", "payload_bay_aft", "avionics_bay"):
        x0, x1, hw, z0, z1 = a[name]
        boxes[name] = dict(box(x0, x1, -hw, hw, z0, z1), **{"in": "fuselage"})
    axle = m["ground_z"] + 0.5 * m["tyre_nose"]["diameter"]
    leg_n, ax_n, nb = stowed_gear((st["nose_gear"]["x"], 0.0, a["nose_gear_pivot_z_ft"]), axle, m["tyre_nose"],
                                  strut, gap, +1)
    for k, b in nb.items():
        boxes["nose_gear_" + k] = dict(b, **{"in": "fuselage"})
    axle = m["ground_z"] + 0.5 * m["tyre_main"]["diameter"]
    legs = {"nose": {"leg_ft": leg_n, "pivot_x": st["nose_gear"]["x"], "stowed_axle_x": ax_n}}
    for side in ("left", "right"):
        sp = m["sponson_" + side]
        leg_m, ax_m, mb = stowed_gear((lay["x_main"], sp.centre[1], sp.centre[2]), axle, m["tyre_main"], strut, gap, -1)
        for k, b in mb.items():
            boxes[f"main_gear_{side}_{k}"] = dict(b, **{"in": "sponson_" + side})
        legs["main_" + side] = {"leg_ft": leg_m, "pivot_x": lay["x_main"], "stowed_axle_x": ax_m}
    # wing carry-through between the spars across the fuselage (not tested against the skin)
    f0 = val(a["front_spar_chord_fraction"])
    f1 = f0 + L["wing_tank_chord_fraction"]
    zl, zu = w.depth_at(0.0, np.linspace(f0, f1, 50))
    boxes["wing_carry_through"] = dict(box(w.x_le + f0 * w.c_root, w.x_le + f1 * w.c_root, -0.5 * m["D_f"],
                                           0.5 * m["D_f"], float(zl.min()), float(zu.max())), **{"in": None})
    t = m["turret"]
    boxes["turret"] = dict(box(*(v for k in range(3) for v in (t.centre[k] - t.a, t.centre[k] + t.a))), **{"in": None})
    return boxes, {"legs": legs, "spar_fractions": [f0, f1]}


def box_points(b, n=7):
    """Points on the 12 edges of a box (the corners included)."""
    lo, hi = np.array(b["lo"]), np.array(b["hi"])
    t = np.linspace(0.0, 1.0, n)
    pts = []
    for axis in range(3):
        for u in (0, 1):
            for v in (0, 1):
                p = np.empty((n, 3))
                p[:, axis] = lo[axis] + t * (hi[axis] - lo[axis])
                o1, o2 = [k for k in range(3) if k != axis]
                p[:, o1], p[:, o2] = (hi if u else lo)[o1], (hi if v else lo)[o2]
                pts.append(p)
    return np.vstack(pts)


def clearance_margin(body, b, hi=1.0):
    """The largest clearance (ft) at which every edge point of the box is inside the body's skin, by bisection
    to 0.001 ft between -hi and hi. Negative: the box comes out of the skin by about that much; -hi: by at
    least hi."""
    pts = box_points(b)
    lo_c, hi_c = -hi, hi
    while hi_c - lo_c > 1e-3:
        mid = 0.5 * (lo_c + hi_c)
        lo_c, hi_c = (mid, hi_c) if body.inside(pts, mid).all() else (lo_c, mid)
    return lo_c


def overlap_volume(b1, b2):
    """Volume common to two boxes (0 if they only touch)."""
    side = np.minimum(b1["hi"], b2["hi"]) - np.maximum(b1["lo"], b2["lo"])
    return float(np.prod(side)) if np.all(side > 0.0) else 0.0

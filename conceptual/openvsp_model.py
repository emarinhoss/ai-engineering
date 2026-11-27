"""OpenVSP model of a Stage 1 design from its recorded geometry (design_<concept>.json).

    <python with the OpenVSP API> -m conceptual.openvsp_model --design runs/.../design_pusher.json --out DIR

Writes DIR/<name>.vsp3 (open in OpenVSP), DIR/<name>.stp (STEP, for CATIA / SolidWorks),
DIR/<name>.stl (mesh, for Blender), OpenVSP's CompGeom report (DIR/<name>_CompGeom.txt/.csv) and
DIR/model.json (inputs, commit, OpenVSP version, and OpenVSP's wetted areas next to the Stage 1 value
as a geometry check).

The layout is the one conceptual/render3d.py draws, so the two agree:
- fuselage: body of revolution, nose ellipse to 20 % of the length, constant diameter to 60 %, then a
  straight taper to 15 % of the diameter at the tail;
- wing and tails: straight-tapered with unswept leading edges, wing at -0.1 D below the axis, horizontal
  tail at +0.3 D; sections NACA 4415 (wing) and 0012 (tails) for display only (Stage 1 fixes a 15 %
  thick cambered section, not its shape); fin tip chord half the root chord, leading edge slope 0.35;
- main gear retracted in two ellipsoid sponsons, sensor turret under the nose, three-blade pusher
  propeller behind the tail.
It is a conceptual model, not a structural loft: no wing-body fairing, engine inlet or exhaust.
Units: feet.

The OpenVSP Python API comes with OpenVSP (openvsp.org), not with pip; it is built for one Python
version (3.57.1 Ubuntu 24.04: Python 3.12).
"""
import argparse
import json
import math
import sys
from pathlib import Path

import openvsp as vsp

from prelim.record import repo_path, tree_state


def set_parm(geom, name, group, value):
    """Set one OpenVSP parameter and fail loudly if it does not exist."""
    pid = vsp.GetParm(geom, name, group)
    if not pid:
        raise KeyError(f"OpenVSP parameter {group}/{name} not found")
    vsp.SetParmVal(pid, value)


def place(geom, x, y=0.0, z=0.0, rot_x=0.0):
    set_parm(geom, "X_Rel_Location", "XForm", x)
    set_parm(geom, "Y_Rel_Location", "XForm", y)
    set_parm(geom, "Z_Rel_Location", "XForm", z)
    set_parm(geom, "X_Rel_Rotation", "XForm", rot_x)


def fuselage(L_f, D_f):
    """Body of revolution with the render3d radius law (circles at the break points)."""
    f = vsp.AddGeom("FUSELAGE")
    vsp.SetGeomName(f, "Fuselage")
    set_parm(f, "Length", "Design", L_f)
    surf = vsp.GetXSecSurf(f, 0)
    # (x / L, diameter / D): nose point, two points on the nose ellipse, end of nose, start of taper, tail
    stations = [(0.0, 0.0), (0.05, 2 * math.sqrt(1 - 0.75 ** 2) / 2), (0.10, 2 * math.sqrt(1 - 0.5 ** 2) / 2),
                (0.20, 1.0), (0.60, 1.0), (1.0, 0.15)]
    while vsp.GetNumXSec(surf) < len(stations):
        vsp.InsertXSec(f, vsp.GetNumXSec(surf) - 2, vsp.XS_CIRCLE)
    for i, (t, dd) in enumerate(stations):
        if i > 0:
            vsp.ChangeXSecShape(surf, i, vsp.XS_CIRCLE)
            vsp.SetParmVal(vsp.GetXSecParm(vsp.GetXSec(surf, i), "Circle_Diameter"), dd * D_f)
        vsp.SetParmVal(vsp.GetXSecParm(vsp.GetXSec(surf, i), "XLocPercent"), t)
    vsp.Update()
    return f


def surface(name, x_le, z, half_span, c_root, c_tip, camber, thick, vertical=False, le_sweep_deg=0.0):
    """Straight-tapered lifting surface, one section, NACA four-digit airfoil."""
    w = vsp.AddGeom("WING")
    vsp.SetGeomName(w, name)
    set_parm(w, "Span", "XSec_1", half_span)
    set_parm(w, "Root_Chord", "XSec_1", c_root)
    set_parm(w, "Tip_Chord", "XSec_1", c_tip)
    set_parm(w, "Sweep", "XSec_1", le_sweep_deg)
    set_parm(w, "Sweep_Location", "XSec_1", 0.0)
    for i in (0, 1):
        set_parm(w, "ThickChord", f"XSecCurve_{i}", thick)
        set_parm(w, "Camber", f"XSecCurve_{i}", camber)
    set_parm(w, "CapUMinOption", "EndCap", vsp.FLAT_END_CAP)   # closed root, so CompGeom sees a closed body
    set_parm(w, "CapUMaxOption", "EndCap", vsp.FLAT_END_CAP)
    if vertical:
        set_parm(w, "Sym_Planar_Flag", "Sym", 0)
    place(w, x_le, 0.0, z, 90.0 if vertical else 0.0)
    vsp.Update()
    return w


def ellipsoid(name, x, y, z, a, b, c, mirror=False):
    e = vsp.AddGeom("ELLIPSOID")
    vsp.SetGeomName(e, name)
    set_parm(e, "A_Radius", "Design", a)
    set_parm(e, "B_Radius", "Design", b)
    set_parm(e, "C_Radius", "Design", c)
    if mirror:
        set_parm(e, "Sym_Planar_Flag", "Sym", vsp.SYM_XZ)
    place(e, x, y, z)
    vsp.Update()
    return e


def build(d):
    """The whole aircraft in the current OpenVSP model; returns {name: geom id}."""
    vsp.VSPRenew()
    w, ht, vt, fus, lay = d["wing"], d["horizontal_tail"], d["vertical_tail"], d["fuselage"], d["layout"]
    L_f, D_f = fus["length"], fus["diameter"]
    ids = {"fuselage": fuselage(L_f, D_f)}
    ids["wing"] = surface("Wing", lay["x_le"], -0.1 * D_f, w["span"] / 2, w["root_chord"], w["tip_chord"], 0.04, 0.15)
    x_ht = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * ht["mac"]
    ids["horizontal_tail"] = surface("HorizontalTail", x_ht, 0.3 * D_f, ht["span"] / 2, ht["root_chord"],
                                     ht["tip_chord"], 0.0, 0.12)
    x_vt = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * vt["mac"]
    r_vt = 0.5 * D_f * max(0.15, 1 - (x_vt / L_f - 0.6) / 0.4 * 0.85)   # fuselage radius there (render3d)
    ids["vertical_tail"] = surface("VerticalTail", x_vt, r_vt * 0.6, vt["height"], vt["root_chord"],
                                   0.5 * vt["root_chord"], 0.0, 0.12, vertical=True,
                                   le_sweep_deg=math.degrees(math.atan(0.35)))
    gt = lay["gear_track"]
    if gt.get("sponson_length_ft"):
        sl, sd = gt["sponson_length_ft"], gt["sponson_depth_ft"]
        ids["sponsons"] = ellipsoid("Sponson", lay["x_main"] - 0.3 * sl, gt["half_track_ft"], -0.1 * D_f - 0.45 * sd,
                                    sl / 2, 0.45 * sd, 0.5 * sd, mirror=True)
    ids["turret"] = ellipsoid("SensorTurret", d["stations"]["payload"]["x"], 0.0, -0.5 * D_f, 0.45, 0.45, 0.45)
    p = vsp.AddGeom("PROP")
    vsp.SetGeomName(p, "Propeller")
    set_parm(p, "Diameter", "Design", d["propeller_diameter_ft"])
    set_parm(p, "NumBlade", "Design", 3)
    place(p, L_f + 0.15 if d["concept"] == "pusher" else -0.15)
    ids["propeller"] = p
    vsp.Update()
    return ids


def wetted_areas(stem):
    """OpenVSP CompGeom wetted area per component (ft^2; mirrored parts summed), as a check on the
    Stage 1 numbers. Its text and csv reports go next to the model, not into the working directory."""
    vsp.SetComputationFileName(vsp.COMP_GEOM_TXT_TYPE, stem + "_CompGeom.txt")
    vsp.SetComputationFileName(vsp.COMP_GEOM_CSV_TYPE, stem + "_CompGeom.csv")
    rid = vsp.ExecAnalysis("CompGeom")
    out = {}
    for name, area in zip(vsp.GetStringResults(rid, "Comp_Name"), vsp.GetDoubleResults(rid, "Wet_Area")):
        out[name] = out.get(name, 0.0) + area
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="aircraft")
    a = ap.parse_args(argv)
    d = json.loads(Path(a.design).read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    build(d)
    stem = str(out / a.name)
    vsp.WriteVSPFile(stem + ".vsp3", vsp.SET_ALL)
    vsp.ExportFile(stem + ".stp", vsp.SET_ALL, vsp.EXPORT_STEP)
    vsp.ExportFile(stem + ".stl", vsp.SET_ALL, vsp.EXPORT_STL)
    build(d)                       # fresh model: the mesh export leaves a MeshGeom that would hide everything
    wet = wetted_areas(stem)
    stage1 = {"fuselage": d["fuselage"]["s_wet"]}
    tree = tree_state(repo_path(a.out))            # commit, dirty flag and its file list; the output folder is not counted
    record = {"design": a.design, "commit": tree["commit"], "git_dirty": tree["git_dirty"],
              "git_dirty_files": tree["git_dirty_files"], "git_dirty_excluded": tree["excluded"],
              "command": "python -m conceptual.openvsp_model " + " ".join(argv if argv is not None else sys.argv[1:]),
              "python": sys.version.split()[0], "openvsp": vsp.GetVSPVersion(), "units": "ft",
              "wetted_area_openvsp_ft2": wet, "wetted_area_stage1_ft2": stage1,
              "note": "conceptual model; sections NACA 4415 / 0012 for display only; same layout as conceptual/render3d.py"}
    (out / "model.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

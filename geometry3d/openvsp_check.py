"""Gate 8: the loft's wetted areas against OpenVSP's CompGeom on the same parameters (decision PD-14).

Run by prelim/p3_loft.py with the interpreter that has the OpenVSP API, when one is given:

    <python with openvsp> -m geometry3d.openvsp_check INPUT.json OUT_DIR

INPUT.json is written by the loft: the fuselage as section outlines at its stations, the lifting surfaces and
the ellipsoids as their parameters. OpenVSP builds its own surfaces from them (its own skinning between the
fuselage sections, its own NACA four-digit sections, which close the trailing edge) and trims the parts against
each other in CompGeom. This file needs nothing of the repository but its input, so the OpenVSP interpreter
need not have the repository's packages.
"""
import json
import math
import sys
from pathlib import Path

import openvsp as vsp


def set_parm(geom, name, group, value):
    pid = vsp.GetParm(geom, name, group)
    if not pid:
        raise KeyError(f"OpenVSP parameter {group}/{name} not found")
    vsp.SetParmVal(pid, value)


def place(geom, x, y, z, rot_x=0.0):
    for name, v in (("X_Rel_Location", x), ("Y_Rel_Location", y), ("Z_Rel_Location", z), ("X_Rel_Rotation", rot_x)):
        set_parm(geom, name, "XForm", v)


def fuselage(length, sections):
    """A FUSELAGE geom whose cross-sections are the loft's outlines (XS_FILE_FUSE). sections: rows of
    {"x": station, "yz": [[y, z], ...]}; the first OpenVSP section stays the nose point."""
    f = vsp.AddGeom("FUSELAGE")
    vsp.SetGeomName(f, "fuselage")
    set_parm(f, "Length", "Design", length)
    surf = vsp.GetXSecSurf(f, 0)
    while vsp.GetNumXSec(surf) < len(sections) + 1:
        vsp.InsertXSec(f, vsp.GetNumXSec(surf) - 2, vsp.XS_FILE_FUSE)
    for i, s in enumerate(sections, start=1):
        vsp.ChangeXSecShape(surf, i, vsp.XS_FILE_FUSE)
        xs = vsp.GetXSec(surf, i)
        ys = [p[0] for p in s["yz"]]
        zs = [p[1] for p in s["yz"]]
        width, height = max(ys) - min(ys), max(zs) - min(zs)
        zc = 0.5 * (max(zs) + min(zs))
        # OpenVSP wants the outline from the right-hand point down through the bottom, round the left side and
        # over the top, closed; the loft's outline starts at the top and runs the same way round
        k = max(range(len(ys)), key=lambda j: ys[j])
        order = list(range(k, len(ys))) + list(range(0, k)) + [k]
        pts = [vsp.vec3d(ys[j], zs[j] - zc, 0.0) for j in order]
        vsp.SetXSecPnts(xs, pts)
        vsp.SetParmVal(vsp.GetXSecParm(xs, "Width"), width)
        vsp.SetParmVal(vsp.GetXSecParm(xs, "Height"), height)
        vsp.SetParmVal(vsp.GetXSecParm(xs, "XLocPercent"), s["x"] / length)
        vsp.SetParmVal(vsp.GetXSecParm(xs, "ZLocPercent"), zc / length)
    vsp.Update()
    return f


def surface(s):
    w = vsp.AddGeom("WING")
    vsp.SetGeomName(w, s["name"])
    set_parm(w, "Span", "XSec_1", s["half_span"])
    set_parm(w, "Root_Chord", "XSec_1", s["c_root"])
    set_parm(w, "Tip_Chord", "XSec_1", s["c_tip"])
    set_parm(w, "Sweep", "XSec_1", math.degrees(math.atan(s["le_slope"])))
    set_parm(w, "Sweep_Location", "XSec_1", 0.0)
    for i in (0, 1):
        set_parm(w, "ThickChord", f"XSecCurve_{i}", int(s["code"][2:]) / 100.0)
        set_parm(w, "Camber", f"XSecCurve_{i}", int(s["code"][0]) / 100.0)
        set_parm(w, "CamberLoc", f"XSecCurve_{i}", max(int(s["code"][1]) / 10.0, 0.2))
    set_parm(w, "CapUMinOption", "EndCap", vsp.FLAT_END_CAP)
    set_parm(w, "CapUMaxOption", "EndCap", vsp.FLAT_END_CAP)
    if s["vertical"]:
        set_parm(w, "Sym_Planar_Flag", "Sym", 0)
    place(w, s["x_le"], 0.0, s["z0"], 90.0 if s["vertical"] else 0.0)
    vsp.Update()


def ellipsoid(e):
    g = vsp.AddGeom("ELLIPSOID")
    vsp.SetGeomName(g, e["name"])
    for name, v in (("A_Radius", e["a"]), ("B_Radius", e["b"]), ("C_Radius", e["c"])):
        set_parm(g, name, "Design", v)
    place(g, *e["centre"])
    vsp.Update()


def comp_geom(stem):
    """CompGeom areas per component: wetted (trimmed against the other parts) and whole."""
    vsp.SetComputationFileName(vsp.COMP_GEOM_TXT_TYPE, stem + "_CompGeom.txt")
    vsp.SetComputationFileName(vsp.COMP_GEOM_CSV_TYPE, stem + "_CompGeom.csv")
    rid = vsp.ExecAnalysis("CompGeom")
    wet, whole = {}, {}
    for name, a, t in zip(vsp.GetStringResults(rid, "Comp_Name"), vsp.GetDoubleResults(rid, "Wet_Area"),
                          vsp.GetDoubleResults(rid, "Theo_Area")):
        wet[name] = wet.get(name, 0.0) + a
        whole[name] = whole.get(name, 0.0) + t
    return {"wetted_ft2": wet, "whole_ft2": whole}


def build(data, fine):
    """The model in OpenVSP. fine=False keeps OpenVSP's default surface mesh; fine=True raises it (more points
    round every section, more span stations on the lifting surfaces), to show how far CompGeom's own numbers
    depend on its mesh."""
    vsp.VSPRenew()
    fuselage(data["fuselage"]["length"], data["fuselage"]["sections"])
    for s in data["surfaces"]:
        surface(s)
    for e in data["ellipsoids"]:
        ellipsoid(e)
    if fine:
        for g in vsp.FindGeoms():
            set_parm(g, "Tess_W", "Shape", 97)
            if vsp.GetParm(g, "SectTess_U", "XSec_1"):
                set_parm(g, "SectTess_U", "XSec_1", 41)
            elif vsp.GetParm(g, "Tess_U", "Shape"):
                set_parm(g, "Tess_U", "Shape", 65)
    vsp.Update()


def main(argv=None):
    inp, out = (argv or sys.argv[1:])[:2]
    data = json.loads(Path(inp).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rec = {"openvsp": vsp.GetVSPVersion(), "python": sys.version.split()[0],
           "fuselage_sections": len(data["fuselage"]["sections"])}
    build(data, fine=False)
    vsp.WriteVSPFile(str(out / "loft_check.vsp3"), vsp.SET_ALL)
    rec["default_mesh"] = comp_geom(str(out / "loft_check"))
    build(data, fine=True)
    rec["fine_mesh"] = comp_geom(str(out / "loft_check_fine"))
    (out / "openvsp_check.json").write_text(json.dumps(rec, indent=2))
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()

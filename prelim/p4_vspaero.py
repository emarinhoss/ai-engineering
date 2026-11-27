"""Preliminary design P4, step 3: VSPAERO on the loft with the fuselage as a body (support, not a verdict row).

Run by prelim/p4_balance.py with the interpreter that has the OpenVSP API, when one is given (decision PD-14):

    <python with openvsp> -m prelim.p4_vspaero INPUT.json OUT_DIR

INPUT.json is written by the caller: the loft as prelim/p3_loft.vsp_input gives it (fuselage section outlines,
lifting surfaces), the reference area, chord, span and moment reference, the Mach number and the mesh levels.
What is in the solution: the fuselage as a thick body (VSPAERO's panel surface), the wing, the horizontal tail and
the fin as thin lifting surfaces. Left out: the propeller, the sponsons, the turret and the spinner. Inviscid.

Mesh: three levels. L1 and L2 are the two levels of the 2026-11-24 check (conceptual/vspaero_check.py); L3 is one
level finer than L2 (spec P4 step 3). The neutral point of each level is x_cg - Cm_alpha c / CL_alpha from line
fits over the angle-of-attack sweep. Whether the two finest levels agree is judged by the caller.
"""
import json
import sys
from pathlib import Path

import openvsp as vsp

from conceptual.vspaero_check import derivatives_at_mach, parse_polar, valid_polar, vspaero_version
from geometry3d import openvsp_check as oc

THICK_SET, THIN_SET = 3, 4                     # OpenVSP user sets
ALPHAS = (-2.0, 8.0, 6)                        # start, end (deg), number of points
BULK = (".adb", ".dat", ".slc", ".vspgeom", ".lod", ".fem", ".group", ".quad", ".cases")


def set_mesh(geoms, level):
    """level: [strips per wing section, points round a wing section, strips per fuselage section, points round the
    fuselage]."""
    n_u, n_w, n_fus_u, n_fus_w = level
    for name, g in geoms.items():
        surf = vsp.GetXSecSurf(g, 0)
        fus = name == "fuselage"
        oc.set_parm(g, "Tess_W", "Shape", n_fus_w if fus else n_w)
        for i in range(1, vsp.GetNumXSec(surf)):
            vsp.SetParmVal(vsp.GetXSecParm(vsp.GetXSec(surf, i), "SectTess_U"), n_fus_u if fus else n_u)


def run_level(data, name, level, out):
    """One angle-of-attack sweep at one mesh level. Returns the fitted derivatives and the mesh size."""
    oc.build(dict(data["model"], ellipsoids=[]), fine=False)
    geoms = {vsp.GetGeomName(g): g for g in vsp.FindGeoms()}
    for gname, g in geoms.items():
        vsp.SetSetFlag(g, THICK_SET, gname == "fuselage")
        vsp.SetSetFlag(g, THIN_SET, gname != "fuselage")
    set_mesh(geoms, level)
    vsp.Update()
    stem = out / name
    vsp.WriteVSPFile(str(stem) + ".vsp3", vsp.SET_ALL)      # VSPAERO writes next to this file
    vsp.SetComputationFileName(vsp.VSPAERO_VSPGEOM_TYPE, str(stem) + ".vspgeom")
    a = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(a)
    vsp.SetIntAnalysisInput(a, "GeomSet", [THICK_SET])
    vsp.SetIntAnalysisInput(a, "ThinGeomSet", [THIN_SET])
    vsp.ExecAnalysis(a)
    s = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(s)
    vsp.SetIntAnalysisInput(s, "GeomSet", [THICK_SET])
    vsp.SetIntAnalysisInput(s, "ThinGeomSet", [THIN_SET])
    vsp.SetIntAnalysisInput(s, "RefFlag", [0])              # reference values given here
    ref = data["ref"]
    for key in ("Sref", "bref", "cref", "Xcg"):
        vsp.SetDoubleAnalysisInput(s, key, [ref[key]])
    for key in ("Ycg", "Zcg"):
        vsp.SetDoubleAnalysisInput(s, key, [0.0])
    vsp.SetDoubleAnalysisInput(s, "MachStart", [data["mach"]])
    vsp.SetIntAnalysisInput(s, "MachNpts", [1])
    vsp.SetDoubleAnalysisInput(s, "AlphaStart", [ALPHAS[0]])
    vsp.SetDoubleAnalysisInput(s, "AlphaEnd", [ALPHAS[1]])
    vsp.SetIntAnalysisInput(s, "AlphaNpts", [ALPHAS[2]])
    vsp.SetDoubleAnalysisInput(s, "BetaStart", [0.0])
    vsp.SetIntAnalysisInput(s, "BetaNpts", [1])
    vsp.SetIntAnalysisInput(s, "Symmetry", [0])
    vsp.SetIntAnalysisInput(s, "NCPU", [4])
    vsp.SetStringAnalysisInput(s, "RedirectFile", [str(stem) + ".log"])
    vsp.ExecAnalysis(s)
    header = Path(str(stem) + ".vspgeom").read_text().split("\n", 3)[2].split()
    for f in out.glob(name + ".*"):
        if f.suffix in BULK:
            f.unlink()
    rows = parse_polar(Path(str(stem) + ".polar").read_text())
    der = derivatives_at_mach(rows, rows[0]["Mach"], ref["bref"] ** 2 / ref["Sref"], ref["cref"], ref["Xcg"])
    der["valid"], der["valid_reason"] = valid_polar(der["CL_alpha_per_rad"], der["CL_fit_max_residual"], der["CDi_trefftz"])
    return {"level": level, "mesh": {"nodes": int(header[0]), "panels": int(header[1])},
            **{k: der[k] for k in ("alpha_deg", "CL", "Cm", "CL_alpha_per_rad", "CL0", "Cm_alpha_per_rad", "Cm0",
                                   "CL_fit_max_residual", "Cm_fit_max_residual", "x_np_ft", "valid", "valid_reason")}}


def main(argv=None):
    inp, out = (argv or sys.argv[1:])[:2]
    data = json.loads(Path(inp).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rec = {"openvsp": vsp.GetVSPVersion(), "python": sys.version.split()[0], "alpha_sweep_deg": ALPHAS,
           "mach": data["mach"], "ref": data["ref"], "in_solution": {"thick": ["fuselage"], "thin": ["wing", "horizontal_tail", "vertical_tail"]},
           "left_out": ["propeller", "sponsons", "turret", "spinner"], "levels": {}}
    for name, level in data["levels"].items():
        rec["levels"][name] = run_level(data, name, level, out)
        rec["vspaero_version"] = vspaero_version((out / (name + ".log")).read_text(errors="replace"))
        (out / "vspaero.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: {q: v[q] for q in ("mesh", "CL_alpha_per_rad", "Cm_alpha_per_rad", "x_np_ft", "valid")}
                      for k, v in rec["levels"].items()}, indent=1))


if __name__ == "__main__":
    main()

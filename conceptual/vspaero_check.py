"""VSPAERO cross-check of a Stage 1 design: lift slope, zero-lift CL, induced drag and pitch stiffness
from NASA's vortex-lattice solver, run on the OpenVSP model (conceptual/openvsp_model.py).

    <python with the OpenVSP API> -m conceptual.vspaero_check --design runs/.../design_pusher.json \
        --model runs/.../m250_baseline.vsp3 --out runs/task12/openvsp/<run folder>

This is an extra check, not a Stage 3 measurement row.

What is in the vortex lattice (VSPAERO "thin" geometry set):
- "wing": the wing alone (a cambered thin surface);
- "tails": wing, horizontal tail and vertical tail;
- "full": the same plus the fuselage, which VSPAERO represents as two crossed flat plates (one
  horizontal, one vertical) along the fuselage axis.
Left out: the propeller (no slipstream), the sensor turret and the gear sponsons (thick bodies, no
lifting surface). The solver is inviscid in lift and in induced drag; its parasite drag column (CDo)
is a flat-plate skin-friction estimate and is not used here.

Flight conditions come from the design record at the mission altitude (ledger.yaml next to it): the
loiter and the outbound cruise sub-steps, true airspeed to Mach with the ISA speed of sound. Reference
area, chord and span are the design's wing. The moment reference is the full-fuel centre of gravity
(x only; z = 0).

Mesh: the wing and tail tessellation is set at two levels, L1 and L2 (spanwise strips per section,
points around the airfoil), and the change between them is reported. A result is accepted only if
it passes valid_polar(); a rejected case is kept in results.json with the reason, never dropped.
With the fuselage plates in, the solution turned out to depend erratically on the wing's spanwise
strips (see the report), so the "full" configuration is also run at two coarser levels, S6 and S8.

Output folder: for each (configuration, level) one OpenVSP file, VSPAERO's polar, history, load and
case files and its log, plus results.json. VSPAERO writes next to the OpenVSP file, so the file is
written into the folder first. The bulk files (.adb, .dat, .slc, .vspgeom, .lod) are deleted after the
panel count is read; they are rebuilt by the command in results.json.

The OpenVSP Python API comes with OpenVSP (openvsp.org), built for one Python version (3.57.1: 3.12).
The pure functions below (polar parsing, line fits, neutral point) do not need it and are tested in
tests/task12/test_vspaero_check.py.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

try:
    import openvsp as vsp
except ImportError:          # the test suite's Python has no OpenVSP; the pure functions still import
    vsp = None

from conceptual import raymer_aero as aero
from conceptual import raymer_stability as stab
from conceptual.units import KT, isa

USER_SET = 3                                   # OpenVSP set index for the lattice geometry (0 = all)
CONFIGS = {"wing": ["Wing"], "tails": ["Wing", "HorizontalTail", "VerticalTail"],
           "full": ["Fuselage", "Wing", "HorizontalTail", "VerticalTail"]}
CASES = [("wing", "L1"), ("wing", "L2"), ("tails", "L1"), ("tails", "L2"),
         ("full", "S6"), ("full", "S8"), ("full", "L1"), ("full", "L2")]
PAIRS = [("wing", "L1", "L2"), ("tails", "L1", "L2"), ("full", "S6", "S8"), ("full", "L1", "L2")]
# (spanwise strips per section, Tess_W points around the airfoil) for wings; then the fuselage
# Tess_U and strips per section (along the axis)
LEVELS = {"L1": (12, 33, 16, 6), "L2": (24, 65, 32, 12), "S6": (6, 33, 16, 6), "S8": (8, 33, 16, 6)}
ALPHAS = (-2.0, 8.0, 6)                        # start, end (deg), number of points
BULK = (".adb", ".dat", ".slc", ".vspgeom", ".lod")      # solution, mesh and load files: rebuilt by the command


# ---------------------------------------------------------------- pure functions (no OpenVSP)

def line_fit(x, y):
    """Least-squares line y = a + b x. Returns (a, b, max |residual|)."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    b = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sum((xi - mx) ** 2 for xi in x)
    a = my - b * mx
    return a, b, max(abs(yi - (a + b * xi)) for xi, yi in zip(x, y))


def lift_curve(alpha_deg, cl):
    """CL = CL0 + CL_alpha alpha. Returns CL_alpha per radian, CL0, zero-lift angle (deg), max residual."""
    cl0, slope_per_deg, res = line_fit(alpha_deg, cl)
    return slope_per_deg * 180.0 / math.pi, cl0, -cl0 / slope_per_deg, res


def induced_drag_fit(cl, cdi, aspect_ratio):
    """CDi = CDi0 + K CL^2 by least squares; e = 1/(pi A K). Returns (K, CDi0, e, max residual)."""
    cdi0, k, res = line_fit([c * c for c in cl], cdi)
    return k, cdi0, 1.0 / (math.pi * aspect_ratio * k), res


def neutral_point_from_cm(x_cg, cm_alpha, cl_alpha, cref):
    """Cm_alpha = -CL_alpha (x_np - x_cg)/cref  ->  x_np (Raymer 16.10 with the whole aircraft's slope)."""
    return x_cg - cm_alpha * cref / cl_alpha


def parse_polar(text):
    """Rows of a VSPAERO .polar file as dicts keyed by the column names."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    start = next(i for i, ln in enumerate(lines) if ln.split()[:2] == ["Beta", "Mach"])
    names = lines[start].split()
    rows = []
    for ln in lines[start + 1:]:
        v = ln.split()
        if len(v) == len(names):
            rows.append(dict(zip(names, map(float, v))))
    return rows


def valid_polar(cl_alpha, cl_residual, cdi_trefftz):
    """Sanity gate on one fitted polar. Returns (ok, reason). A lifting-line wing of aspect ratio 7
    has a slope near 5 per rad; a slope outside 3 to 8, a CL(alpha) that is not a line (residual above
    0.02) or a negative induced drag means the solve is not physical."""
    if not 3.0 < cl_alpha < 8.0:
        return False, f"CL_alpha {cl_alpha:.2f} per rad outside 3 to 8"
    if cl_residual > 0.02:
        return False, f"CL(alpha) not a line: max residual {cl_residual:.3f}"
    if min(cdi_trefftz) <= 0.0:
        return False, "negative Trefftz-plane induced drag"
    return True, "ok"


def relative_change(a, b):
    """(b - a)/|a|."""
    return (b - a) / abs(a)


def ledger_value(text, key):
    """The 'value:' of one ledger.yaml line, read without a YAML library."""
    m = re.search(rf"^\s*{key}:\s*{{value:\s*([-0-9.eE+]+)", text, re.M)
    if not m:
        raise KeyError(f"{key} not in the ledger")
    return float(m.group(1))


def derivatives_at_mach(rows, mach, aspect_ratio, cref, x_cg):
    """All the derived numbers for the rows of one Mach number."""
    r = sorted((r for r in rows if abs(r["Mach"] - mach) < 1e-9), key=lambda r: r["AoA"])
    alpha = [x["AoA"] for x in r]
    cl = [x["CLtot"] for x in r]
    cm = [x["CMytot"] for x in r]
    cla, cl0, a_l0, cl_res = lift_curve(alpha, cl)
    cma, cm0, _, cm_res = lift_curve(alpha, cm)        # Cm against alpha is a line too: slope per rad
    out = {"alpha_deg": alpha, "CL": cl, "Cm": cm, "CL_alpha_per_rad": cla, "CL0": cl0,
           "alpha_L0_deg": a_l0, "CL_fit_max_residual": cl_res,
           "Cm_alpha_per_rad": cma, "Cm0": cm0, "Cm_fit_max_residual": cm_res,
           "x_np_ft": neutral_point_from_cm(x_cg, cma, cla, cref)}
    for label, col in (("trefftz", "CDiw"), ("surface", "CDi")):
        cdi = [x[col] for x in r]
        k, cdi0, e, res = induced_drag_fit(cl, cdi, aspect_ratio)
        out[f"CDi_{label}"] = cdi
        out[f"K_{label}"] = k
        out[f"CDi0_{label}"] = cdi0
        out[f"e_{label}"] = e
        out[f"CDi_fit_max_residual_{label}"] = res
    return out


# ---------------------------------------------------------------- OpenVSP part

def set_parm(geom, name, group, value):
    pid = vsp.GetParm(geom, name, group)
    if not pid:
        raise KeyError(f"OpenVSP parameter {group}/{name} not found")
    vsp.SetParmVal(pid, value)


def set_mesh(geoms, level):
    """Tessellation of the wing, tails and fuselage at one level."""
    n_u, n_w, n_fus, n_fus_section = LEVELS[level]
    for name, g in geoms.items():
        if name not in ("Fuselage", "Wing", "HorizontalTail", "VerticalTail"):
            continue
        surf = vsp.GetXSecSurf(g, 0)
        if name == "Fuselage":
            set_parm(g, "Tess_U", "Shape", n_fus)
            sections = range(1, vsp.GetNumXSec(surf))
            n_section = n_fus_section
        else:
            set_parm(g, "Tess_W", "Shape", n_w)
            sections = range(1, vsp.GetNumXSec(surf))        # the one wing section
            n_section = n_u
        for i in sections:
            vsp.SetParmVal(vsp.GetXSecParm(vsp.GetXSec(surf, i), "SectTess_U"), n_section)


def run_case(geoms, config, level, machs, ref, out):
    """One VSPAERO sweep (all Mach numbers x all angles of attack) of one configuration at one mesh
    level. Returns the polar rows and the panel count."""
    for name, g in geoms.items():
        vsp.SetSetFlag(g, USER_SET, name in CONFIGS[config])
    set_mesh(geoms, level)
    vsp.Update()
    stem = f"{config}_{level}"
    vsp.WriteVSPFile(str(out / (stem + ".vsp3")), vsp.SET_ALL)    # VSPAERO writes next to this file
    vsp.SetComputationFileName(vsp.VSPAERO_VSPGEOM_TYPE, str(out / (stem + ".vspgeom")))
    vsp.SetComputationFileName(vsp.DEGEN_GEOM_CSV_TYPE, str(out / (stem + "_DegenGeom.csv")))
    a = "VSPAEROComputeGeometry"
    vsp.SetAnalysisInputDefaults(a)
    vsp.SetIntAnalysisInput(a, "GeomSet", [-1])            # no thick (panel-method) geometry
    vsp.SetIntAnalysisInput(a, "ThinGeomSet", [USER_SET])
    vsp.ExecAnalysis(a)
    s = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(s)
    vsp.SetIntAnalysisInput(s, "GeomSet", [-1])
    vsp.SetIntAnalysisInput(s, "ThinGeomSet", [USER_SET])
    vsp.SetIntAnalysisInput(s, "RefFlag", [0])             # reference values given here, not from a wing
    for key in ("Sref", "bref", "cref", "Xcg", "Ycg", "Zcg", "ReCref"):
        vsp.SetDoubleAnalysisInput(s, key, [ref[key]])
    vsp.SetDoubleAnalysisInput(s, "MachStart", [machs[0]])
    vsp.SetDoubleAnalysisInput(s, "MachEnd", [machs[-1]])
    vsp.SetIntAnalysisInput(s, "MachNpts", [len(machs)])
    vsp.SetDoubleAnalysisInput(s, "AlphaStart", [ALPHAS[0]])
    vsp.SetDoubleAnalysisInput(s, "AlphaEnd", [ALPHAS[1]])
    vsp.SetIntAnalysisInput(s, "AlphaNpts", [ALPHAS[2]])
    vsp.SetDoubleAnalysisInput(s, "BetaStart", [0.0])
    vsp.SetIntAnalysisInput(s, "BetaNpts", [1])
    vsp.SetIntAnalysisInput(s, "Symmetry", [0])
    vsp.SetIntAnalysisInput(s, "NCPU", [4])
    vsp.SetStringAnalysisInput(s, "RedirectFile", [str(out / (stem + ".log"))])
    vsp.ExecAnalysis(s)
    header = (out / (stem + ".vspgeom")).read_text().split("\n", 3)[2].split()
    for f in out.glob(stem + ".*"):
        if f.suffix in BULK:
            f.unlink()
    rows = parse_polar((out / (stem + ".polar")).read_text())
    return rows, {"nodes": int(header[0]), "panels": int(header[1]), "parts": int(header[2])}


def raymer_values(d, ledger_text):
    """Stage 1's numbers for the same quantities, from the design record and Raymer's equations."""
    A, S, lay, mac = d["wing"]["aspect_ratio"], d["wing"]["area"], d["layout"], d["wing"]["mac"]
    eta_h = ledger_value(ledger_text, "tail_eta_h")
    s_ratio = d["horizontal_tail"]["area"] / S
    tail = eta_h * s_ratio * lay["CLa_h"] * lay["dah_da"]
    cla_total = d["CL_alpha_wing"] + tail

    def x_np(cma_fus):                       # (16.9) as Stage 1 calls it, ft from the nose
        return mac * stab.neutral_point(d["CL_alpha_wing"], lay["x_ac"] / mac, cma_fus, eta_h, s_ratio,
                                        lay["CLa_h"], lay["dah_da"], (lay["x_ac"] + d["tail_arm_ft"]) / mac)
    return {"CL_alpha_wing_installed_record": d["CL_alpha_wing"],
            "CL_alpha_wing_bare_planform_eta1": {m: aero.lift_slope(A, m, 1.0) for m in (0.0, 0.158, 0.227)},
            "CL_alpha_aircraft": cla_total, "tail_term": tail, "eta_h": eta_h,
            "e": d["e"], "K": d["K"], "CD0_mission_altitude": d["CD0"]["mission_altitude"],
            "x_np_ft": lay["x_np"], "x_np_reproduced_ft": x_np(lay["Cma_fus"]),
            "x_np_without_fuselage_term_ft": x_np(0.0),
            "x_cg_full_ft": lay["cg_full"], "x_cg_empty_ft": lay["cg_empty"],
            "static_margin_full": lay["sm_full"], "static_margin_empty": lay["sm_empty"],
            "Cm_alpha_per_rad_full_cg": -cla_total * (lay["x_np"] - lay["cg_full"]) / mac,
            "CL0": None, "CL0_note": "Stage 1 has no zero-lift CL (no camber or zero-lift angle in the record)",
            "trim_CL_wing": {k: v["CL_wing"] for k, v in lay["trim"].items()}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--model", required=True, help="the .vsp3 written by conceptual.openvsp_model")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    design = Path(a.design)
    d = json.loads(design.read_text())
    ledger_text = (design.parent / "ledger.yaml").read_text()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    h = ledger_value(ledger_text, "mission_altitude_ft")
    atm = isa(h)
    w = d["wing"]
    ref = {"Sref": w["area"], "cref": w["mac"], "bref": w["span"],
           "Xcg": d["layout"]["cg_full"], "Ycg": 0.0, "Zcg": 0.0}
    speeds = {m["segment"]: m["V_kt"] for m in d["mission"] if m["segment"] in ("loiter", "cruise_out")}
    conditions = {name: {"V_kt_true": v, "Mach": v * KT / atm["a"]} for name, v in speeds.items()}
    machs = sorted(c["Mach"] for c in conditions.values())
    ref["ReCref"] = atm["rho"] * speeds["loiter"] * KT * w["mac"] / atm["mu"]   # only sets CDo, not used

    vsp.VSPRenew()
    vsp.ReadVSPFile(a.model)
    geoms = {vsp.GetGeomName(g): g for g in vsp.FindGeoms()}
    results = {}
    for config, level in CASES:
        rows, mesh = run_case(geoms, config, level, machs, ref, out)
        case = {"mesh": mesh, "polar": {}}
        for name, c in conditions.items():
            der = derivatives_at_mach(rows, c["Mach"], w["aspect_ratio"], w["mac"], ref["Xcg"])
            der["valid"], der["valid_reason"] = valid_polar(der["CL_alpha_per_rad"], der["CL_fit_max_residual"],
                                                            der["CDi_trefftz"])
            der["static_margin_full"] = (der["x_np_ft"] - d["layout"]["cg_full"]) / w["mac"]
            der["static_margin_empty"] = (der["x_np_ft"] - d["layout"]["cg_empty"]) / w["mac"]
            case["polar"][name] = der
        results[f"{config}_{level}"] = case
    sens = {}
    for config, l1, l2 in PAIRS:
        for name in conditions:
            p1, p2 = (results[f"{config}_{lv}"]["polar"][name] for lv in (l1, l2))
            key = f"{config} {l1}->{l2} {name}"
            if not (p1["valid"] and p2["valid"]):
                sens[key] = {"valid": False, "reason": f"{l1}: {p1['valid_reason']}; {l2}: {p2['valid_reason']}"}
                continue
            sens[key] = {"valid": True} | {q: relative_change(p1[q], p2[q]) for q in (
                "CL_alpha_per_rad", "K_trefftz", "K_surface", "Cm_alpha_per_rad", "x_np_ft")}
            sens[key]["CL0_abs_change"] = p2["CL0"] - p1["CL0"]
            sens[key]["static_margin_full_abs_change"] = p2["static_margin_full"] - p1["static_margin_full"]
    git = lambda *c: subprocess.run(["git", *c], capture_output=True, text=True).stdout.strip()
    record = {"design": a.design, "model": a.model, "commit": git("rev-parse", "HEAD"),
              "git_dirty_in_conceptual": bool(git("status", "--porcelain", "conceptual")),
              "command": "python -m conceptual.vspaero_check " + " ".join(argv if argv is not None else sys.argv[1:]),
              "python": sys.version.split()[0], "openvsp": vsp.GetVSPVersion(),
              "vspaero_path": vsp.GetVSPAEROPath(),
              "units": "ft, lb, s, deg", "altitude_ft": h, "atmosphere": atm, "conditions": conditions,
              "reference": ref, "aspect_ratio": w["aspect_ratio"], "alpha_sweep_deg": ALPHAS,
              "levels": {k: {"wing_tail_strips_per_section": v[0], "Tess_W": v[1], "fuselage_Tess_U": v[2],
                             "fuselage_strips_per_section": v[3]} for k, v in LEVELS.items()},
              "in_lattice": CONFIGS, "left_out": ["Propeller", "SensorTurret", "Sponson"],
              "cases": results, "mesh_sensitivity": sens,
              "raymer_stage1": raymer_values(d, ledger_text),
              "note": "conceptual model (render3d layout, display sections NACA 4415 / 0012); inviscid lattice"}
    (out / "results.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(sens, indent=1))


if __name__ == "__main__":
    main()

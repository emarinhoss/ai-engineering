"""Stage 3 aerodynamic measurements of the frozen pusher with the study's vortex lattice
(drone/vlm.py, validated in Task 10 rows V6a-V6c). Spec section 7.1, tolerances 7.1a.

    python -m measurement.stage3_aero --design runs/task12/stage1/2026-11-20e/design_pusher.json \
        --out runs/task12/stage3/2026-11-20/aero.json --report docs/validation/<file>.md

Rows
- Wing lift slope: lattice (incompressible, thin) against Raymer (12.6) with airfoil efficiency
  1, Mach 0, exposed-area ratio 1 and F = 1, so both are the bare planform's inviscid slope.
  Anderson's Helmbold relation (2.18a) with a0 = 2 pi is algebraically the same expression as
  that (12.6), so it is not a third independent route; this is stated in the report.
- Span efficiency: the lattice's inviscid e beside (12.49). Raymer says (12.49) is an empirical
  fit that absorbs separation drag and that classical estimates run high (p. 298); he gives no
  inviscid share, so the spec's "inviscid part" comparison cannot be formed as written. The
  values are reported with the viscous drag-due-to-lift factor they imply.
- Downwash gradient at the horizontal tail: lattice at the tail's quarter-MAC station, mean
  over five spanwise points, at three tail heights; Stage 1 used the far-wake 2 CL_a/(pi A).
- Static margin: Raymer's neutral point (16.9) exactly as Stage 1 computed it, with only the
  downwash replaced by the lattice value at the nominal tail height.
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

from conceptual import raymer_aero as aero
from conceptual import raymer_stability as stab
from conceptual import uav
from drone import geometry, vlm

REPO = Path(__file__).resolve().parents[1]
# Tail height above the wing plane. Stage 1 fixes no vertical tail position; the render
# (conceptual/render3d.py) draws the wing at -0.1 D_f and the tail at +0.3 D_f, so 0.4 D_f is
# the nominal, bracketed by 0 and 3 ft.
TAIL_Z_OVER_DF = 0.4
LEVEL = "fine"


def measure(d, L):
    w = d["wing"]
    pf = geometry.tapered(w["span"], w["aspect_ratio"], w["taper"])     # unswept leading edge
    A = w["aspect_ratio"]
    rows, info = [], {}
    # lift slope
    lat = {lev: vlm.derivatives(pf, lev)["CL_alpha"] for lev in ("coarse", "medium", "fine")}
    cla_r = aero.lift_slope(A, 0.0, 1.0)
    rows.append({"quantity": "wing lift slope, per rad (bare planform, inviscid, M 0)",
                 "raymer": cla_r, "measured": lat[LEVEL], "deviation": lat[LEVEL] / cla_r - 1.0,
                 "tolerance": 0.05, "tolerance_kind": "rel",
                 "within": abs(lat[LEVEL] / cla_r - 1.0) <= 0.05})
    info["lift_slope_by_level"] = lat
    info["stage1_installed_lift_slope"] = d["CL_alpha_wing"]
    # span efficiency
    e_vlm = vlm.solve(pf, math.radians(4.0), LEVEL)["e"]
    e_r = d["e"]
    k_visc = 1.0 / (math.pi * A * e_r) - 1.0 / (math.pi * A * e_vlm)
    rows.append({"quantity": "span efficiency e", "raymer": e_r, "measured": e_vlm,
                 "deviation": e_vlm - e_r, "tolerance": 0.05, "tolerance_kind": "abs",
                 "within": None,
                 "note": "not comparable as specified: (12.49) has no inviscid share"})
    info["implied_viscous_K"] = k_visc
    # downwash at the tail
    x_t = pf.x_ref + d["tail_arm_ft"]
    b_t = d["horizontal_tail"]["span"] / 2.0
    z_nom = TAIL_Z_OVER_DF * d["fuselage"]["diameter"]
    dw = {}
    for z in (0.0, z_nom, 3.0):
        pts = [[x_t, f * b_t, z] for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
        dw[round(z, 3)] = vlm.downwash_gradient(pf, pts, LEVEL)
    de_s1 = 1.0 - d["layout"]["dah_da"]
    de_v = dw[round(z_nom, 3)]
    info["downwash_gradient_by_tail_height_ft"] = dw
    rows.append({"quantity": f"downwash gradient at the tail (z = {z_nom:.2f} ft)", "raymer": de_s1,
                 "measured": de_v, "deviation": de_v - de_s1, "tolerance": None,
                 "tolerance_kind": "abs", "within": None, "note": "no 7.1a tolerance; feeds the static margin"})
    # static margin with the lattice downwash, everything else as Stage 1
    lay, g = d["layout"], d
    mac = w["mac"]
    S_h_S = d["horizontal_tail"]["area"] / w["area"]
    for label, cg in (("full", lay["cg_full"]), ("empty", lay["cg_empty"])):
        sm1 = lay[f"sm_{label}"]

        def np_with(dah):
            return stab.neutral_point(g["CL_alpha_wing"], lay["x_ac"] / mac, lay["Cma_fus"],
                                      L["tail_eta_h"], S_h_S, lay["CLa_h"], dah,
                                      (lay["x_ac"] + g["tail_arm_ft"]) / mac) * mac
        check = (np_with(lay["dah_da"]) - cg) / mac
        sm = (np_with(1.0 - de_v) - cg) / mac
        rows.append({"quantity": f"static margin, {label} fuel, MAC", "raymer": sm1, "measured": sm,
                     "deviation": sm - sm1, "tolerance": 0.03, "tolerance_kind": "abs",
                     "within": abs(sm - sm1) <= 0.03, "stage1_reproduced": check})
    return {"rows": rows, "info": info, "tail_z_nominal_ft": z_nom, "level": LEVEL}


def res_s1_dah(res):
    """Stage 1's (1 - d eps/d alpha), recovered from the downwash row."""
    return 1.0 - next(r["raymer"] for r in res["rows"] if r["quantity"].startswith("downwash"))


def report(res, path, commit):
    out = ["# Task 12 Stage 3: aerodynamic measurements (vortex lattice)\n",
           (f"Generated by `python -m measurement.stage3_aero` at commit `{commit[:7]}`; numbers from "
           "`runs/task12/stage3/2026-11-20/aero.json`.\n"),
           "| Quantity | Stage 1 / Raymer | Lattice | deviation | tolerance | within |",
           "|---|---|---|---|---|---|"]
    for r in res["rows"]:
        if r["tolerance_kind"] == "rel":
            dev, tol = f"{r['deviation'] * 100:+.1f} %", f"±{r['tolerance'] * 100:.0f} %"
        else:
            dev = f"{r['deviation']:+.3f}"
            tol = "none" if r["tolerance"] is None else f"±{r['tolerance']:.2f}"
        within = {True: "yes", False: "**no**", None: "n/a"}[r["within"]]
        out.append(f"| {r['quantity']} | {r['raymer']:.3f} | {r['measured']:.3f} | {dev} | {tol} | {within} |")
    i = res["info"]
    sm = {k: next(r["measured"] for r in res["rows"] if r["quantity"].startswith(f"static margin, {k}"))
          for k in ("full", "empty")}
    lv = ", ".join(f"{k} {v:.4f}" for k, v in i["lift_slope_by_level"].items())
    dws = ", ".join(f"{k} ft: {v:.3f}" for k, v in i["downwash_gradient_by_tail_height_ft"].items())
    out += ["",
            (f"- Lift slope on the three lattices: {lv} per rad. Anderson's Helmbold (2.18a) with a0 = 2 pi "
            "is the same expression as Raymer's (12.6) with airfoil efficiency 1, so it adds no independent "
            f"check. Stage 1's installed slope, {i['stage1_installed_lift_slope']:.3f} per rad, adds the "
            "airfoil efficiency 0.95, the exposed-area ratio, the fuselage factor F and Mach; those are not "
            "measured here."),
            (f"- Span efficiency: (12.49) is an empirical whole-aircraft fit that includes separation drag; the "
            f"lattice gives the inviscid planform value. The spec row asked for the inviscid share of (12.49), "
            f"which Raymer does not give, so the row is reported, not judged. Together they imply a viscous "
            f"drag-due-to-lift factor of {i['implied_viscous_K']:.4f} (CD = CD0 + (K_inv + K_visc) CL^2)."),
            (f"- Downwash gradient at the tail by tail height above the wing plane: {dws}. The nominal height "
            f"({res['tail_z_nominal_ft']:.2f} ft) is the render's, since Stage 1 fixes none. The lattice wake "
            "is planar. Stage 1 called its far-wake formula conservative (true for DR-1); here it gives "
            f"{1.0 - res_s1_dah(res):.3f}, and the lattice gives more at "
            f"{sum(v > 1.0 - res_s1_dah(res) for v in i['downwash_gradient_by_tail_height_ft'].values())} of "
            f"{len(i['downwash_gradient_by_tail_height_ft'])} tail heights, so it was not conservative here."),
            ("- Static margin rows recompute Raymer's (16.9) with only the downwash replaced; the record carries "
            "the Stage 1 value reproduced by the same call as a check. Against R13 (5 to 15 % MAC) the "
            f"lattice margins are {sm['full']:.3f} full and {sm['empty']:.3f} empty: "
            + (f"inside the band, {min(sm.values()) - 0.05:.3f} MAC above the 5 % floor."
               if min(sm.values()) >= 0.05 and max(sm.values()) <= 0.15 else
               f"**outside R13** ({0.05 - min(sm.values()):.3f} MAC below the 5 % floor at the lower one). "
               "Within the 7.1a tolerance, but a requirement margin below zero returns the design to Stage 1 "
               "(spec 7.1a).")),
            ("- Not measured here: compressibility (at cruise Mach 0.16 the Prandtl-Glauert factor is 1.014, an upper bound on the slope change), the "
            "fuselage and nacelle on the lattice, the propeller slipstream at the tail.")]
    Path(path).write_text("\n".join(out) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    d = json.loads(Path(a.design).read_text())
    L, _ = uav.load_ledger()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=False, cwd=REPO).stdout.strip()
    res = measure(d, L)
    res["inputs"] = {"commit": commit, "design": a.design, "seed": None}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    if a.report:
        report(res, a.report, commit)
    for r in res["rows"]:
        print(f"{r['quantity']}: {r['raymer']:.4f} -> {r['measured']:.4f} within {r['within']}"
              + (f" (Stage 1 reproduced {r['stage1_reproduced']:.4f})" if "stage1_reproduced" in r else ""))


if __name__ == "__main__":
    main()

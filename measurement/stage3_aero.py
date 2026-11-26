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
- Static margin by Anderson (8.76)-(8.78), p. 444 (owner ruling G-5): the neutral point from
  x_acwb = x_n - V_HT (a_t/a) c-bar, margin (x_n - x_cg)/c-bar. Two variants: as printed (downwash and
  tail dynamic-pressure ratio neglected) and with the lattice downwash and eta_h. Both are compared
  with Stage 1 and with the lattice row above. With downwash and eta_h the relation is algebraically
  Raymer's (16.9), so that variant checks the coding; it is not an independent source (spec 7.1c item 3).
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from conceptual import raymer_aero as aero
from conceptual import raymer_stability as stab
from conceptual import uav
from drone import geometry, vlm
from measurement import anderson

REPO = Path(__file__).resolve().parents[1]
# Tail height above the wing plane. Stage 1 fixes no vertical tail position; the render
# (conceptual/render3d.py) draws the wing at -0.1 D_f and the tail at +0.3 D_f, so 0.4 D_f is
# the nominal, bracketed by 0 and 3 ft.
TAIL_Z_OVER_DF = 0.4
TAIL_Z_BAND_OVER_DF = (0.1, 0.9)      # ledger band of tail_height_over_df
LEVEL = "fine"
NOT_JUDGED_SAME_MODEL = "not judged (same model, 7.1c item 3)"
R13_BAND = (0.05, 0.15)


def tail_heights(d, L):
    """Tail heights above the wing plane for the downwash table: the ledger's nominal and the two ends of its
    band, the lower end raised to just above the lattice wake sheet (uav.lattice_downwash refuses |z| below
    span/60: the planar-wake lattice cannot evaluate a tail in the wing plane)."""
    df = d["fuselage"]["diameter"]
    z_min = 1.05 * d["wing"]["span"] / 60.0
    nominal = L.get("tail_height_over_df", TAIL_Z_OVER_DF) * df
    lo = max(TAIL_Z_BAND_OVER_DF[0] * df, z_min)
    hi = TAIL_Z_BAND_OVER_DF[1] * df
    return nominal, [lo, nominal, hi]


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
                 "within": abs(lat[LEVEL] / cla_r - 1.0) <= 0.05, "class": "independent",
                 "verdict": "within" if abs(lat[LEVEL] / cla_r - 1.0) <= 0.05 else "outside"})
    info["lift_slope_by_level"] = lat
    info["stage1_installed_lift_slope"] = d["CL_alpha_wing"]
    # span efficiency
    e_vlm = vlm.solve(pf, math.radians(4.0), LEVEL)["e"]
    e_r = d["e"]
    k_visc = 1.0 / (math.pi * A * e_r) - 1.0 / (math.pi * A * e_vlm)
    rows.append({"quantity": "span efficiency e", "raymer": e_r, "measured": e_vlm,
                 "deviation": e_vlm - e_r, "tolerance": 0.05, "tolerance_kind": "abs",
                 "within": None, "class": "independent",
                 "verdict": "not judged (not comparable as specified)",
                 "note": "not comparable as specified: (12.49) has no inviscid share"})
    info["implied_viscous_K"] = k_visc
    # downwash at the tail
    x_t = pf.x_ref + d["tail_arm_ft"]
    b_t = d["horizontal_tail"]["span"] / 2.0
    z_nom, heights = tail_heights(d, L)
    dw = {}
    for z in heights:
        pts = [[x_t, f * b_t, z] for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
        dw[round(z, 3)] = vlm.downwash_gradient(pf, pts, LEVEL)
    de_s1 = 1.0 - d["layout"]["dah_da"]
    de_v = dw[round(z_nom, 3)]
    info["downwash_gradient_by_tail_height_ft"] = dw
    rows.append({"quantity": f"downwash gradient at the tail (z = {z_nom:.2f} ft)", "raymer": de_s1,
                 "measured": de_v, "deviation": de_v - de_s1, "tolerance": None,
                 "tolerance_kind": "abs", "within": None, "class": "coding check",
                 "verdict": NOT_JUDGED_SAME_MODEL,
                 "note": "no 7.1a tolerance; feeds the static margin; Stage 1 uses the same lattice (7.1c item 3)"})
    # static margin with the lattice downwash, everything else as Stage 1
    lay = d["layout"]
    mac = w["mac"]
    S_h_S = d["horizontal_tail"]["area"] / w["area"]

    def np_with(dah):
        return stab.neutral_point(d["CL_alpha_wing"], lay["x_ac"] / mac, lay["Cma_fus"],
                                  L["tail_eta_h"], S_h_S, lay["CLa_h"], dah,
                                  (lay["x_ac"] + d["tail_arm_ft"]) / mac) * mac

    # Anderson (8.76)-(8.78): wing-body aerodynamic center, tail volume and lift slopes from the record
    x_acwb = lay["x_ac"] - lay["Cma_fus"] / d["CL_alpha_wing"] * mac       # fuselage moves the wing's center forward
    l_ht = lay["x_ac"] + d["tail_arm_ft"] - x_acwb
    V_HT = anderson.horizontal_tail_volume(l_ht, d["horizontal_tail"]["area"], w["area"], mac)
    a_t = lay["CLa_h"]

    def anderson_np(dah, printed):
        """printed: (8.76) as printed, factor 1 and a = a_wing + (S_h/S) a_t. Else eta_h (1 - d eps/d alpha) in
        the tail term and in a (not printed in (8.76); the same tail term as Raymer's (16.9))."""
        f = 1.0 if printed else L["tail_eta_h"] * dah
        a = d["CL_alpha_wing"] + S_h_S * a_t * f
        return anderson.neutral_point(x_acwb, mac, V_HT, a_t, a, f)

    an_info = {"x_acwb_ft": x_acwb, "l_ht_ft": l_ht, "V_HT": V_HT, "a_t": a_t, "a_wing": d["CL_alpha_wing"]}
    for label, cg in (("full", lay["cg_full"]), ("empty", lay["cg_empty"])):
        sm1 = lay[f"sm_{label}"]
        check = (np_with(lay["dah_da"]) - cg) / mac
        sm = (np_with(1.0 - de_v) - cg) / mac
        rows.append({"quantity": f"static margin, {label} fuel, MAC", "raymer": sm1, "measured": sm,
                     "deviation": sm - sm1, "tolerance": 0.03, "tolerance_kind": "abs",
                     "within": None, "numerically_within": abs(sm - sm1) <= 0.03, "class": "coding check",
                     "verdict": NOT_JUDGED_SAME_MODEL, "stage1_reproduced": check})
        sm_a = anderson.static_margin(anderson_np(1.0 - de_v, False), cg, mac)
        rows.append({"quantity": f"static margin by Anderson (8.76)-(8.78) with lattice downwash, {label} fuel, MAC",
                     "raymer": sm1, "measured": sm_a, "deviation": sm_a - sm1, "tolerance": 0.03,
                     "tolerance_kind": "abs", "within": None, "numerically_within": abs(sm_a - sm1) <= 0.03,
                     "class": "coding check", "verdict": NOT_JUDGED_SAME_MODEL, "anderson": "lattice", "fuel": label,
                     "lattice_row": sm, "deviation_from_lattice_row": sm_a - sm,
                     "note": "algebraically Raymer's (16.9) with the lattice downwash: checks the coding"})
        sm_p = anderson.static_margin(anderson_np(1.0 - de_v, True), cg, mac)
        rows.append({"quantity": f"static margin by Anderson (8.76) as printed (no downwash), {label} fuel, MAC",
                     "raymer": sm1, "measured": sm_p, "deviation": sm_p - sm1, "tolerance": 0.03,
                     "tolerance_kind": "abs", "within": None, "numerically_within": abs(sm_p - sm1) <= 0.03,
                     "class": "partly independent", "verdict": "not judged (book's simplification)",
                     "anderson": "printed", "fuel": label,
                     "note": "the book neglects downwash and tail efficiency; the spec asks for the lattice downwash, "
                             "so this is reported to show what the simplification does, not judged"})
    # what the margins depend on: the downwash gradient (everything else as Stage 1)
    sens = {}
    for label, cg in (("full", lay["cg_full"]), ("empty", lay["cg_empty"])):
        m = lambda g: (np_with(1.0 - g) - cg) / mac
        g0, g1 = de_v, de_v + 0.1
        sens[f"{label}_margin_per_0.1_gradient"] = m(g1) - m(g0)
        by_z = {k: m(v) for k, v in dw.items()}
        sens[f"{label}_margin_by_tail_height_ft"] = by_z
    lo_g, hi_g = de_v, 1.5                                   # empty-fuel margin falls as the gradient rises
    f_floor = lambda g: (np_with(1.0 - g) - lay["cg_empty"]) / mac - R13_BAND[0]
    if f_floor(hi_g) < 0.0 <= f_floor(lo_g):
        for _ in range(60):
            mid = 0.5 * (lo_g + hi_g)
            lo_g, hi_g = (mid, hi_g) if f_floor(mid) >= 0.0 else (lo_g, mid)
        sens["gradient_where_empty_margin_reaches_floor"] = 0.5 * (lo_g + hi_g)
    sens["cg_travel_mac"] = (lay["cg_empty"] - lay["cg_full"]) / mac
    sens["margin_sum"] = lay["sm_full"] + lay["sm_empty"]
    info["static_margin_sensitivity"] = sens
    info["anderson_static_margin"] = an_info
    return {"rows": rows, "info": info, "tail_z_nominal_ft": z_nom, "level": LEVEL}


def res_s1_dah(res):
    """Stage 1's (1 - d eps/d alpha), recovered from the downwash row."""
    return 1.0 - next(r["raymer"] for r in res["rows"] if r["quantity"].startswith("downwash"))


def report(res, path, commit, record):
    out = ["# Task 12 Stage 3: aerodynamic measurements (vortex lattice)\n",
           (f"Generated by `python -m measurement.stage3_aero` at commit `{commit[:7]}`; numbers from "
           f"`{record}`.\n"),
           "| Quantity | Class | Stage 1 / Raymer | Measured | deviation | tolerance | verdict |",
           "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        if r["tolerance_kind"] == "rel":
            dev, tol = f"{r['deviation'] * 100:+.1f} %", f"±{r['tolerance'] * 100:.0f} %"
        else:
            dev = f"{r['deviation']:+.3f}"
            tol = "none" if r["tolerance"] is None else f"±{r['tolerance']:.2f}"
        verdict = r.get("verdict") or {True: "within", False: "**outside**", None: "not judged"}[r["within"]]
        if "numerically_within" in r:
            verdict += f" (numerically {'inside' if r['numerically_within'] else 'outside'})"
        out.append(f"| {r['quantity']} | {r.get('class', '-')} | {r['raymer']:.3f} | {r['measured']:.3f} | {dev} | {tol} | {verdict} |")
    i = res["info"]
    sm = {k: next(r["measured"] for r in res["rows"] if r["quantity"].startswith(f"static margin, {k}"))
          for k in ("full", "empty")}
    lv = ", ".join(f"{k} {v:.4f}" for k, v in i["lift_slope_by_level"].items())
    dws = ", ".join(f"{k:.2f} ft: {v:.3f}" for k, v in sorted((float(k), v) for k, v in
                                                            i["downwash_gradient_by_tail_height_ft"].items()))
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
            f"({res['tail_z_nominal_ft']:.2f} ft) is the ledger's `tail_height_over_df`; the other two are the ends of "
            "its band, the lower one raised to just above the lattice wake sheet (the planar-wake lattice cannot "
            "evaluate a tail in the wing plane). Stage 1 now uses the same lattice (7.1c item 3), so the gradient "
            f"row compares the model with itself (Stage 1 {1.0 - res_s1_dah(res):.3f}; the small difference is the "
            "lattice evaluated again)."),
            ("- Static margin rows recompute Raymer's (16.9) with only the downwash replaced; the record carries "
            "the Stage 1 value reproduced by the same call as a check. Stage 1 already uses the lattice downwash, so "
            "these rows are **not judged (same model)**; the numbers are shown.")]
    an = i.get("anderson_static_margin")
    if an:
        ra = {(r["fuel"], r["anderson"]): r for r in res["rows"] if "anderson" in r}
        out.append(
            ("- **Static margin by Anderson (8.76)-(8.78), p. 444** (owner ruling G-5). Wing-body aerodynamic center "
             f"{an['x_acwb_ft']:.3f} ft (the wing's, moved by the fuselage moment of Stage 1), tail arm from it "
             f"{an['l_ht_ft']:.3f} ft, tail volume V_HT {an['V_HT']:.4f}, a_t {an['a_t']:.3f}. With the lattice downwash and "
             "the tail efficiency the margins are "
             f"{ra[('full', 'lattice')]['measured']:.3f} (full) and {ra[('empty', 'lattice')]['measured']:.3f} (empty), "
             f"{ra[('full', 'lattice')]['deviation_from_lattice_row']:+.4f} and "
             f"{ra[('empty', 'lattice')]['deviation_from_lattice_row']:+.4f} from the lattice rows: the relation is "
             "algebraically Raymer's (16.9) when those two factors are kept, so this checks the coding, not the physics. "
             "As printed ((8.76) neglects downwash and tail efficiency) they are "
             f"{ra[('full', 'printed')]['measured']:.3f} and {ra[('empty', 'printed')]['measured']:.3f}, "
             f"{ra[('full', 'printed')]['deviation']:+.3f} and {ra[('empty', 'printed')]['deviation']:+.3f} from Stage 1: "
             "the downwash the book leaves out moves the neutral point aft; this is shown, not judged. The book's worked "
             "number (8.79) subtracts V_HT in feet; the function here uses V_HT dimensionless times the MAC."))
    se = i.get("static_margin_sensitivity")
    if se:
        lo_, hi_ = R13_BAND
        by_full = list(se["full_margin_by_tail_height_ft"].values())
        by_empty = list(se["empty_margin_by_tail_height_ft"].values())
        inside = all(lo_ <= v <= hi_ for v in by_full + by_empty)
        txt = (f"- **R13 (5 to 15 % MAC) is met by layout construction.** `uav.layout` places the wing so that the full "
               f"and empty margins are centred in the band: their sum is {se['margin_sum']:.3f} (twice the band's centre "
               f"{0.5 * (lo_ + hi_):.2f}), with the same lattice downwash model as Stage 1. The lattice margins "
               f"{sm['full']:.3f} and {sm['empty']:.3f} are therefore not a measured margin above the 5 % floor. What is "
               f"physical is the CG travel, {se['cg_travel_mac']:.3f} MAC, and the accuracy of the neutral point. The "
               f"empty-fuel margin changes by {se['empty_margin_per_0.1_gradient']:+.3f} MAC per 0.1 of downwash gradient"
               + (f" and reaches the floor at a gradient of {se['gradient_where_empty_margin_reaches_floor']:.3f} "
                  f"(lattice at the nominal height: {1.0 - res_s1_dah(res):.3f})" if "gradient_where_empty_margin_reaches_floor" in se else "")
               + f". Over the tail heights above the margins run {min(by_empty):.3f} to {max(by_full):.3f}: "
               + ("inside R13." if inside else "**outside R13 at some height**.")
               + " An independent neutral point is needed for R13.")
        out.append(txt)
    out += [("- Not measured here: compressibility (at cruise Mach 0.16 the Prandtl-Glauert factor is 1.014, an upper bound on the slope change), the "
            "fuselage and nacelle on the lattice, the propeller slipstream at the tail."),
            "",
            "## Status of the rows (generated)", "",
            ("- Span efficiency: no judgement possible as specified (see above); "
             f"{next(r['deviation'] for r in res['rows'] if r['quantity'] == 'span efficiency e'):+.3f} is the inviscid lattice value "
             "against Raymer's (12.49) whole-aircraft value."),
            "- Downwash and static margin: declared the same model, not independent (spec 7.1c item 3).",
            "- Section polars (SU2) and the section CL_max row: not run (owner ruling G-5: waived before Gate B, listed open)."]
    Path(path).write_text("\n".join(out) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    d = json.loads(Path(a.design).read_text())
    ledger = Path(a.design).parent / "ledger.yaml"      # the ledger copy the record was sized with
    L, _ = uav.load_ledger(ledger if ledger.exists() else uav.LEDGER)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=False, cwd=REPO).stdout.strip()
    res = measure(d, L)
    res["inputs"] = {"commit": commit, "design": a.design, "ledger": str(ledger) if ledger.exists() else "default", "seed": None,
                     "command": "python -m measurement.stage3_aero " + " ".join(sys.argv[1:] if argv is None else argv)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    if a.report:
        report(res, a.report, commit, a.out)
    for r in res["rows"]:
        print(f"{r['quantity']}: {r['raymer']:.4f} -> {r['measured']:.4f} {r.get('verdict', r['within'])}"
              + (f" (Stage 1 reproduced {r['stage1_reproduced']:.4f})" if "stage1_reproduced" in r else ""))


if __name__ == "__main__":
    main()

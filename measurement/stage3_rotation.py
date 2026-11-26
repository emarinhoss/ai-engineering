"""Stage 3 row: take-off rotation of the frozen Task 12 design with ground effect.

    python -m measurement.stage3_rotation --design runs/task12/stage1/2026-11-21f/design_pusher.json \
        --out runs/task12/stage3/2026-11-21/rotation.json --report docs/validation/<file>.md

Stage 1 sizes the rotation tail with the ground-attitude CL of Raymer p. 486 (ledger cl_ground)
and ground effect not modelled. Here the wing's ground effect is measured with the study's vortex
lattice and its image ground plane (drone/vlm.py, ground_h) and fed back into the same balance.

Method
1. Wing height above ground at rotation: h = h_cg - 0.1 D_f (ASSUMPTION: the render draws the wing
   at -0.1 D_f from the fuselage axis, the CG at the fuselage axis height); also h +- 1 ft.
2. Ground-roll attitude: the wing angle at which the FREE-AIR lattice CL equals cl_ground (keeps
   Raymer's assumption). At that angle, k_GE = CL(in ground effect) / CL(free air).
3. The wing lift terms of the balance, cl_ground and the flap increment, are multiplied by k_GE
   (ledger copy with cl_ground and flap_delta_cl_max scaled) and uav.layout is called again.
   Scaling the flap increment by the wing's k_GE is an approximation: the flap's own lift in ground
   effect was not computed (the lattice is planar and has no flap).
4. Check first: with k_GE = 1 the rebuilt layout must reproduce the record's CL_tail_needed to 1e-6.
Everything else in the balance (weight, thrust, wheel reaction, CG, tail geometry) is unchanged.
The tail downwash gradient in ground effect is reported for information only.
"""
import argparse
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

from conceptual import uav
from drone import geometry, vlm
from measurement import ground_effect_validation as gev
from measurement.stage3_perf import rebuild, sha256

REPO = Path(__file__).resolve().parents[1]
LEVEL = "fine"
WING_BELOW_AXIS = 0.1          # wing station below the fuselage axis, in fuselage diameters (render)
CHECK_TOLERANCE = 1e-6


def git_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=False, cwd=REPO).stdout.strip()


def layout_with(d, b, L, k):
    """Rotation block of uav.layout with the wing lift terms scaled by k."""
    state = dict(b, concept=d["concept"], W_S=d["W_S"], A=d["A"], W0=d["W0_lb"])
    L2 = dict(L, cl_ground=L["cl_ground"] * k, flap_delta_cl_max=L["flap_delta_cl_max"] * k)
    return uav.layout(state, L2)["rotation"]


def ground_factor(pf, cl_target, h):
    """Angle (rad) at which free-air CL = cl_target, and CL_ground-effect / CL_free there."""
    a0 = math.radians(4.0)
    cl_a = vlm.solve(pf, a0, LEVEL)["CL"] / a0            # flat wing: CL linear in alpha, zero at 0
    alpha = cl_target / cl_a
    free = vlm.solve(pf, alpha, LEVEL)["CL"]
    ge = vlm.solve(pf, alpha, LEVEL, ground_h=h)["CL"]
    return alpha, free, ge, ge / free


def compute(design_path):
    d, L, b, ledger_path, check = rebuild(design_path)
    rec = d["layout"]["rotation"]
    # check: the rebuilt layout reproduces the record
    r1 = layout_with(d, b, L, 1.0)
    err = abs(r1["CL_tail_needed"] / rec["CL_tail_needed"] - 1.0)
    if err > CHECK_TOLERANCE:
        raise ValueError(f"layout rebuild does not reproduce rotation.CL_tail_needed: "
                         f"{rec['CL_tail_needed']} against {r1['CL_tail_needed']} (rel {err:.2e})")
    w, f, ht = d["wing"], d["fuselage"], d["horizontal_tail"]
    pf = geometry.tapered(w["span"], w["aspect_ratio"], L["wing_taper"])
    h0 = d["layout"]["h_cg"] - WING_BELOW_AXIS * f["diameter"]
    limit = L["tail_cl_max_rotation"]
    cases = {}
    for label, h in (("nominal", h0), ("minus_1ft", h0 - 1.0), ("plus_1ft", h0 + 1.0)):
        alpha, free, ge, k = ground_factor(pf, L["cl_ground"], h)
        rot = layout_with(d, b, L, k)
        need = rot["CL_tail_needed"]
        cases[label] = {"h_ft": h, "h_over_b": h / w["span"], "alpha_deg": math.degrees(alpha),
                        "CL_free": free, "CL_ground_effect": ge, "k_GE": k,
                        "CL_wing_rotation": rot["CL_wing"], "CL_tail_needed": need,
                        "main_wheel_load_lb": rot["main_wheel_load_lb"],
                        "limit_met": abs(need) <= limit,
                        "tail_scale_estimate": d["ht_volume_scale"] * abs(need) / limit}
    # downwash gradient at the tail: same stations as uav.lattice_downwash, nominal wing height
    z = L["tail_height_over_df"] * f["diameter"]
    x_t = pf.x_ref + d["tail_arm_ft"]
    pts = [[x_t, fr * ht["span"] / 2.0, z] for fr in (0.1, 0.3, 0.5, 0.7, 0.9)]
    dw_free = vlm.downwash_gradient(pf, pts, LEVEL)
    dw_ge = {k: vlm.downwash_gradient(pf, pts, LEVEL, ground_h=c["h_ft"]) for k, c in cases.items()}
    nom = cases["nominal"]
    row = {"quantity": "rotation tail CL needed (0.8 V_TO, forward CG, sea level)",
           "stage1": rec["CL_tail_needed"], "stage3": nom["CL_tail_needed"],
           "deviation_abs": nom["CL_tail_needed"] - rec["CL_tail_needed"],
           "deviation_rel": nom["CL_tail_needed"] / rec["CL_tail_needed"] - 1.0,
           "limit": limit, "limit_met_stage1": abs(rec["CL_tail_needed"]) <= limit,
           "limit_met_stage3": nom["limit_met"], "tolerance": None,
           "tail_scale_record": d["ht_volume_scale"],
           "tail_scale_estimate": nom["tail_scale_estimate"],
           "note": "no 7.1a tolerance exists for this row; the scale is a proportional estimate, "
                   "not a re-size"}
    return {"row": row, "cases": cases, "rebuild_check": check,
            "ground_effect_validation": gev.compute(),
            "layout_check": {"record": rec["CL_tail_needed"], "rebuilt_k1": r1["CL_tail_needed"],
                             "relative_difference": err},
            "downwash_gradient_tail": {"z_ft": z, "x_ft": x_t, "free_air": dw_free,
                                       "ground_effect": dw_ge},
            "assumptions": {"wing_height": f"h = h_cg - {WING_BELOW_AXIS} D_f (render's wing "
                            "station), plus/minus 1 ft",
                            "attitude": "free-air lattice CL = ledger cl_ground",
                            "flap": "flap increment scaled by the wing's k_GE (approximation)",
                            "lattice": f"{LEVEL}, planar, ground plane parallel to the wing plane"},
            "ledger_path": str(ledger_path)}


def fmt(x, n=3):
    return f"{x:.{n}f}"


def report_text(res):
    i, r, c = res["inputs"], res["row"], res["cases"]
    r_ = r
    n = c["nominal"]
    dw = res["downwash_gradient_tail"]
    lc = res["layout_check"]
    yes = lambda ok: "yes" if ok else "**no**"
    out = []
    out.append("# Task 12 Stage 3: take-off rotation with ground effect\n")
    out.append(f"Generated by `python -m measurement.stage3_rotation` from `{i['out']}`. Design "
               f"`{i['design']}` (sha256 `{i['design_sha256']}`), git commit `{i['git_commit']}`, "
               f"numpy {i['numpy']}, Python {i['python']}.\n")
    out.append("## Row\n")
    out.append("| Quantity | Stage 1 | With ground effect | deviation | limit | "
               "limit met (Stage 1 / now) |")
    out.append("|---|---|---|---|---|---|")
    out.append(f"| {r['quantity']} | {fmt(r['stage1'])} | {fmt(r['stage3'])} | "
               f"{r['deviation_abs']:+.3f} ({r['deviation_rel'] * 100:+.1f} %) | "
               f"abs <= {fmt(r['limit'], 2)} | {yes(r['limit_met_stage1'])} / "
               f"{yes(r['limit_met_stage3'])} |\n")
    out.append("No 7.1a tolerance exists for this row (the spec asks for the measurement); the value "
               "and the limit test are reported. A proportional estimate of the tail scale needed, "
               f"{fmt(r['tail_scale_record'], 2)} x {fmt(abs(r['stage3']))} / {fmt(r['limit'], 2)} = "
               f"**{fmt(r['tail_scale_estimate'], 2)}** (record scale {fmt(r['tail_scale_record'], 2)}), "
               "is an estimate, not a re-size: the tail's size changes the weight, the CG and the "
               "wheel load.\n")
    out.append("## Ground effect on the wing\n")
    out.append("| Wing height | h (ft) | h/b | angle (deg) | CL free | CL ground | k_GE | "
               "CL_wing at rotation | tail CL needed | scale estimate |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for k, v in c.items():
        out.append(f"| {k.replace('_', ' ')} | {fmt(v['h_ft'], 2)} | {fmt(v['h_over_b'], 3)} | "
                   f"{fmt(v['alpha_deg'], 2)} | {fmt(v['CL_free'], 4)} | "
                   f"{fmt(v['CL_ground_effect'], 4)} | {fmt(v['k_GE'], 4)} | "
                   f"{fmt(v['CL_wing_rotation'], 4)} | {fmt(v['CL_tail_needed'])} | "
                   f"{fmt(v['tail_scale_estimate'], 2)} |")
    out.append("\n## Method and assumptions\n")
    out.append(f"- Wing height h = h_cg - {WING_BELOW_AXIS} D_f (the render draws the wing at "
               "-0.1 D_f); this is an assumption, so h +- 1 ft is shown.")
    out.append("- Ground-roll attitude: the angle where the free-air lattice CL equals the ledger "
               f"cl_ground; k_GE = CL(ground)/CL(free) at that angle ({fmt(n['alpha_deg'], 2)} deg "
               "nominal). Planar lattice (fine), ground plane parallel to the wing plane, by the "
               "method of images.")
    out.append("- k_GE multiplies the ledger's cl_ground and flap_delta_cl_max, so both wing lift "
               "terms of the rotation balance (ground-attitude lift and the take-off flap increment) "
               "scale. Scaling the flap increment by the wing's factor is an approximation; the "
               "flap's own ground effect was not computed.")
    out.append("- Everything else in uav.layout (weight, thrust, main-wheel reaction and friction, "
               "CG, wing moment, tail geometry) is Stage 1's. The main-wheel load changes through "
               "the lift terms.")
    out.append(f"- Layout check: with k_GE = 1 the rebuilt layout gives {lc['rebuilt_k1']:.9f} "
               f"against the record's {lc['record']:.9f} "
               f"(relative difference {lc['relative_difference']:.1e}).")
    out.append("- Validation of the ground-effect model: see the section below. The lift gain, which is what this "
               "row uses, has no book relation to be validated against; the induced-drag ratio is checked.")
    out.append("\n## Downwash gradient at the tail (information only)\n")
    out.append(f"Tail at {fmt(dw['x_ft'], 2)} ft aft, {fmt(dw['z_ft'], 2)} ft above the wing plane, "
               "five spanwise stations as `uav.lattice_downwash`; the rotation balance does not "
               "use it.\n")
    out.append("| | d(eps)/d(alpha) |")
    out.append("|---|---|")
    out.append(f"| free air | {fmt(dw['free_air'], 4)} |")
    for k, v in dw["ground_effect"].items():
        out.append(f"| ground effect, {k.replace('_', ' ')} (h {fmt(c[k]['h_ft'], 2)} ft) | "
                   f"{fmt(v, 4)} |")
    v = res.get("ground_effect_validation")
    if v:
        out.append("\n## Validation of the ground-effect model (generated)\n")
        out.append(f"Lattice induced-drag ratio in ground effect over free air at equal CL (`measurement/ground_effect_validation.py`, "
                   f"the call of `tests/task12/test_ground_effect.py`), against two references, tolerance ±{v['tolerance'] * 100:.0f} % "
                   "of the reference at every h/b, fixed in advance: Anderson (6.77) p. 357 and Raymer (12.61) p. 304 "
                   "(owner ruling G-7).\n")
        out.append("| h/b | lattice | Anderson (6.77) | lattice / Anderson - 1 | within | Raymer (12.61) | lattice / Raymer - 1 | within | Raymer / Anderson - 1 |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for r in v["rows"]:
            out.append(f"| {r['h_over_b']} | {r['lattice_induced_drag_ratio']:.3f} | {r['anderson_G_6_77']:.3f} | "
                       f"{r['deviation_anderson'] * 100:+.1f} % | {yes(r['within_anderson'])} | {r['raymer_12_61']:.3f} | "
                       f"{r['deviation_raymer'] * 100:+.1f} % | {yes(r['within_raymer'])} | "
                       f"{(r['raymer_over_anderson'] - 1.0) * 100:+.1f} % |")
        out.append(f"\n**Verdict:** {v['verdict']}.")
        out.append(f"Rotation: the tail CL needed is {fmt(r_['stage1'])} without ground effect and {fmt(r_['stage3'])} with it, "
                   f"against the limit {fmt(r_['limit'], 2)}: the limit is {'met' if r_['limit_met_stage1'] and r_['limit_met_stage3'] else 'not met in at least one case'} "
                   f"({'with and without ground effect' if r_['limit_met_stage1'] and r_['limit_met_stage3'] else 'see row'}), "
                   "so the validation does not decide the row.")
    Path(i["report"]).write_text("\n".join(out) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    res = compute(a.design)
    res["inputs"] = {"design": a.design, "design_sha256": sha256(a.design),
                     "ledger": res.pop("ledger_path"),
                     "ledger_sha256": sha256(Path(a.design).parent / "ledger.yaml"),
                     "git_commit": git_commit(), "python": platform.python_version(),
                     "numpy": np.__version__, "out": a.out, "report": a.report, "seed": None,
                     "command": "python -m measurement.stage3_rotation " + " ".join(sys.argv[1:] if argv is None else argv)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        report_text(res)
    r = res["row"]
    print(f"k_GE {res['cases']['nominal']['k_GE']:.4f}; tail CL needed {r['stage1']:.4f} -> "
          f"{r['stage3']:.4f}; limit {r['limit']} met: {r['limit_met_stage3']}; "
          f"scale estimate {r['tail_scale_estimate']:.3f}")


if __name__ == "__main__":
    main()

"""Preliminary design P4: balance and longitudinal stability of the baseline r0 as P3 arranged it.

    python -m prelim.p4_balance --out runs/task12/pd/<date>/p4 [--openvsp-python PATH] [--report docs/validation/<date>_task12_pd_p4.md]
    python -m prelim.p4_balance --out runs/task12/pd/<date>/p4 --report ... --report-only

Spec: docs/specs/task12_preliminary_design.md, package P4 (method steps 1 to 4, acceptance rows 1 to 5), and
decision PD-20 (docs/specs/00_decisions.md section 9). The methods are in prelim/p4_methods.py; this file runs
them on r0 with the P3 arrangement, solves the wing and tail positions for r1 and writes the record OUT/p4.json and
OUT/run.log. r0 is read and not changed: what P4 finds is a list of findings for the closing re-record r1 (PD-7).
"""
import argparse
import copy
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import yaml

from conceptual import raymer_stability as stab
from conceptual.units import KT, isa
from geometry3d import aircraft as ac
from geometry3d import gates
from prelim import p3_loft as p3
from prelim import p4_methods as m
from prelim.record import tree_state

REPO = m.REPO
R0 = p3.R0
P3_RECORD = REPO / "runs/task12/pd/2026-11-27/p3/p3.json"
P2_RECORD = REPO / "runs/task12/pd/2026-11-27/p2b/p2.json"
P6_RECORD = REPO / "runs/task12/pd/2026-11-27/p6/p6.json"
TOL_VSPAERO_MAC = 0.01                          # spec P4 step 3
VSP_LEVELS = {"L1": [12, 33, 2, 17], "L2": [24, 65, 3, 25], "L3": [36, 97, 4, 33]}
EVIDENCE_CLASS = ("step 2 is independent of Stage 1 in the fuselage term (Multhopp's strip integral on the loft's width "
                  "in place of Raymer's single factor) and partly independent overall: the wing and tail lift slopes and "
                  "the lattice downwash are Stage 1's (spec 7.1c item 3). Step 1 is layout construction on the P3 "
                  "arrangement. Step 3 (VSPAERO) is support, as under G-8. Step 4 is Stage 1's own equations with P2's "
                  "measured section moment (a coding check plus one measured input). The power-on rows use a "
                  "representative blade whose validation failed in P6 and carry no verdict")
ROW_NAMES = {"1": "static margin at the full-fuel and empty-fuel centre of gravity, independent neutral point, power off: inside R13's 0.05 to 0.15 MAC",
             "2": "independent neutral point against Stage 1's: within 0.03 MAC",
             "3": "every loading of step 1 between the forward limit (trim and rotation) and the aft limit (neutral point less 0.05 MAC)",
             "4": "nose-wheel load at every loading inside 5 to 20 %",
             "5": "if 1, 3 or 4 fails: the wing position that restores them, for r1 (with the tail of PD-20)"}


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def context():
    """Everything the run reads: r0, its ledger, the P3 arrangement and record, the P2 section moment, the P6
    blade, the sources and choices, and the loft's fuselage."""
    d, L, A = p3.inputs()
    model = ac.build(d, L, A)
    choices = m.load_yaml(m.CHOICES)
    return {"d": d, "L": L, "A": A, "p3": load(P3_RECORD), "p6": load(P6_RECORD), "src": m.load_yaml(m.SOURCES),
            "choices": choices, "body": model["fuselage"], "model": model,
            "propeller_plane_x": model["propeller"]["x"], "tanks": m.tanks(d, L, A, choices),
            "cm0_p2": load(P2_RECORD)["section_at_stall"]["cm_c4_linear_range"]}


def record_with_layout(d, L, lay):
    """A copy of the design record with a layout's wing station, tail arm, tail planforms and main-wheel station,
    so that geometry3d.aircraft.build draws that layout. Only what the loft reads is changed."""
    d1 = copy.deepcopy(d)
    ht, vt = m.tail_planforms(lay["ht_area"], lay["vt_area"], L)
    d1["layout"].update({"x_le": lay["x_le"], "x_ac": lay["x_le"] + 0.25 * d["wing"]["mac"], "x_main": lay["x_main"]})
    d1["tail_arm_ft"] = lay["arm"]
    d1["horizontal_tail"] = {"area": ht.area, "aspect_ratio": ht.aspect_ratio, "taper": ht.taper, "span": ht.span,
                             "root_chord": ht.root_chord, "tip_chord": ht.tip_chord, "mac": ht.mac, "mac_y": ht.mac_y}
    d1["vertical_tail"] = {"area": lay["vt_area"], **vt}
    if lay["tail_te_straight"]:
        lam = L["vt_taper"]
        d1["horizontal_tail"]["le_slope"] = m.tail_le_slope(L, "horizontal")
        d1["vertical_tail"].update({"le_slope": m.tail_le_slope(L, "vertical"),
                                    "mac_y": vt["height"] / 3.0 * (1 + 2 * lam) / (1 + lam)})     # (7.9) on one panel
    return d1


# ---- verdict rules (tested before the run) -----------------------------------------------------------------
def row2_verdict(difference_mac):
    return "pass" if abs(difference_mac) <= m.TOL_NP else "fail"


def vspaero_verdict(v, mac):
    """Spec P4 step 3: a run whose neutral point moves by more than 0.01 MAC between its two finest meshes is not
    converged and gives no verdict."""
    if isinstance(v, str):
        return {"run": False, "reason": v}
    a, b = v["L2"], v["L3"]
    change = abs(b["x_np_ft"] - a["x_np_ft"]) / mac
    ok = bool(a["valid"] and b["valid"] and change <= TOL_VSPAERO_MAC)
    return {"run": True, "change_mac": change, "converged": ok,
            "note": "converged: support for the neutral point" if ok else "not converged: reported, no verdict"}


# ---- the parts of the run -------------------------------------------------------------------------------------
def power_on_points(c):
    """The propeller's normal-force derivative at r0's propeller points (WR L-25): thrust from the record's shaft
    power and efficiency, blade angle and chords from the P6 representative blade."""
    d, L, p6 = c["d"], c["L"], c["p6"]
    blade = p6["aircraft"]["blade"]
    b = lambda r: float(np.interp(r, blade["x"], blade["c_over_D"]))
    sff = m.side_force_factor(b(0.3), b(0.6), b(0.9))
    out = {"side_force_factor": sff, "blade_c_over_D": {"0.3": b(0.3), "0.6": b(0.6), "0.9": b(0.9)}, "points": {}}
    for name in c["choices"]["neutral_point"]["power_on_points"]:
        pt = d["propeller_points"][name]
        rho = isa(0.0 if name.endswith("sea_level") else L["mission_altitude_ft"])["rho"]
        V = pt["V_kt"] * KT
        T = pt["eta_p"] * pt["shaft_hp"] * 550.0 / V
        beta = p6["aircraft"]["points"][name]["beta_at_075R_deg"]
        row = m.propeller_normal_force(m.thrust_coefficient(T, rho, V, d["propeller_diameter_ft"]), beta, sff, c["src"])
        out["points"][name] = dict(row, thrust_lb=T, V_fps=V, rho=rho, beta_at_075R_deg=beta,
                                   plane_behind_fuselage_ft=c["A"]["loft"]["propeller_plane_behind_fuselage_ft"])
    return out


def evaluate(c, lay, label, log, with_alternatives=False):
    """Steps 1, 2 and 4 and rows 1 to 4 on one layout."""
    d, L, ch, tk, src = c["d"], c["L"], c["choices"], c["tanks"], c["src"]
    mac, w = d["wing"]["mac"], d["wing"]
    out = {"layout": lay, "tail_planforms": {}, "items": {g: m.items(d, L, lay, g) for g in ("up", "down")}}
    ht, vt = m.tail_planforms(lay["ht_area"], lay["vt_area"], L)
    out["tail_planforms"] = {"horizontal": {"area": ht.area, "span": ht.span, "root_chord": ht.root_chord, "tip_chord": ht.tip_chord, "mac": ht.mac},
                             "vertical": dict(vt, area=lay["vt_area"])}
    out["empty_weight_lb"] = sum(lay["weights"].values())
    # step 2
    st = m.stability(d, L, lay, c["body"], src)
    Cma_stage1 = stab.fuselage_cm_alpha_per_deg(L["fuselage_kf"], d["fuselage"]["diameter"], d["fuselage"]["length"], mac, w["area"]) * 180.0 / math.pi
    st1 = m.stability(d, L, lay, c["body"], src, Cma_fus=Cma_stage1)
    np_ = {"independent_power_off_ft": st["x_np_power_off_ft"], "stage1_method_ft": st1["x_np_power_off_ft"],
           "difference_mac": (st["x_np_power_off_ft"] - st1["x_np_power_off_ft"]) / mac,
           "Cma_fus_multhopp_per_rad": st["Cma_fus_per_rad"], "Cma_fus_raymer_16_22_per_rad": Cma_stage1,
           "fuselage_moment": st["fuselage_moment"], "dah_da": st["dah_da"], "tail_term": st["tail_term"],
           "CLa_w": st["CLa_w"], "x_ac_ft": st["x_ac_ft"], "x_ach_ft": st["x_ach_ft"], "power_on": {}}
    np_["shift_by_fuselage_multhopp_mac"] = -st["Cma_fus_per_rad"] / (st["CLa_w"] + st["tail_term"])
    np_["shift_by_fuselage_raymer_mac"] = -Cma_stage1 / (st["CLa_w"] + st["tail_term"])
    pw = power_on_points(c)
    np_["propeller"] = pw
    for name, pt in pw["points"].items():
        s = m.stability(d, L, lay, c["body"], src, prop=pt)
        np_["power_on"][name] = {"x_np_ft": s["x_np_power_on_ft"], "Fp_alpha_over_qS": s["Fp_alpha_over_qS"], "x_p_ft": s["x_p_ft"],
                                 "shift_mac": (s["x_np_power_on_ft"] - st["x_np_power_off_ft"]) / mac}
    if with_alternatives:
        scale = d["CL_alpha_wing"] / 4.5
        z = -c["A"]["loft"]["wing_z_over_diameter"] * d["fuselage"]["diameter"]
        lat = m.lattice_integral(w["span"], w["aspect_ratio"], L["wing_taper"], w["root_chord"], z)
        alt = {"figure_8_excess_scaled_by_lift_slope": m.stability(d, L, lay, c["body"], src, upwash=m.figure8_integral(src, scale)),
               "vortex_lattice_upwash": m.stability(d, L, lay, c["body"], src, upwash=lat)}
        np_["upwash_alternatives"] = {k: {"x_np_ft": v["x_np_power_off_ft"], "Cma_fus_per_rad": v["Cma_fus_per_rad"],
                                          "difference_from_verdict_route_mac": (v["x_np_power_off_ft"] - st["x_np_power_off_ft"]) / mac}
                                      for k, v in alt.items()}
        np_["upwash_alternatives"]["figure_8_excess_scaled_by_lift_slope"]["scale"] = scale
        G = m.figure8_integral(src)
        xi = np.array([0.3, 0.6, 0.9, 1.1])
        np_["upwash_alternatives"]["vortex_lattice_upwash"].update({
            "height_of_axis_above_wing_plane_ft": z, "integral_at_chords_ahead": xi.tolist(),
            "figure_8": G(xi).tolist(), "lattice": [float(v) for v in lat(xi)], "lattice_points": lat.points})
    out["neutral_point"] = np_
    x_np = st["x_np_power_off_ft"]
    log(f"{label}: neutral point independent {x_np:.4f} ft, Stage 1's method {st1['x_np_power_off_ft']:.4f} ft "
        f"({np_['difference_mac']:+.4f} MAC); Cma_fus {st['Cma_fus_per_rad']:.4f} against {Cma_stage1:.4f} per rad")
    # step 1 and rows 3, 4
    rows = m.loadings(d, L, lay, tk, ch)
    cm_p2, cm_ledger = m.wing_moment(c["cm0_p2"], d["A"]), m.wing_moment(L["airfoil_cm0"], d["A"])
    env = m.envelope(d, L, lay, rows, x_np, cm_p2)
    out["loadings"], out["envelope"] = rows, env
    # row 1
    order0 = ch["balance"]["tank_orders"][0]
    row1 = {}
    for gear in ("up", "down"):
        for f in ch["balance"]["empty_weight_factors"]:
            r = m.pick(rows, gear=gear, empty_weight_factor=f, payload_on=True, tank_order=order0)
            row1[f"gear_{gear}/empty_weight_x{f:g}"] = {"x_cg_full_ft": r[0]["x_cg_ft"], "x_cg_empty_ft": r[-1]["x_cg_ft"],
                                                         "sm_full": r[0]["static_margin"], "sm_empty": r[-1]["static_margin"],
                                                         "weight_full_lb": r[0]["weight_lb"], "weight_empty_lb": r[-1]["weight_lb"]}
    base = row1["gear_up/empty_weight_x1"]
    base["verdict"] = "pass" if m.inside(base["sm_full"], m.SM_MIN, m.SM_MAX) == m.inside(base["sm_empty"], m.SM_MIN, m.SM_MAX) == "pass" else "fail"
    base["power_on"] = {k: {"sm_full": base["sm_full"] + v["shift_mac"], "sm_empty": base["sm_empty"] + v["shift_mac"]} for k, v in np_["power_on"].items()}
    base["stage1_method"] = {"sm_full": (st1["x_np_power_off_ft"] - base["x_cg_full_ft"]) / mac, "sm_empty": (st1["x_np_power_off_ft"] - base["x_cg_empty_ft"]) / mac}
    out["row1"] = row1
    # step 4: rotation and trim at the centre-of-gravity ends
    down = row1["gear_down/empty_weight_x1"]
    x_fwd = min(down["x_cg_full_ft"], down["x_cg_empty_ft"])
    rot = {"x_cg_ft": x_fwd, "limit": L["tail_cl_max_rotation"],
           "p2_section_moment": dict(m.rotation(d, L, lay, x_fwd, cm_p2), cm_wing=cm_p2),
           "ledger_section_moment": dict(m.rotation(d, L, lay, x_fwd, cm_ledger), cm_wing=cm_ledger)}
    rot["used_of_limit"] = abs(rot["p2_section_moment"]["CL_tail_needed"]) / rot["limit"]
    rot["verdict"] = "pass" if rot["used_of_limit"] <= 1.0 else "fail"
    W_zf = base["weight_empty_lb"]
    it_up = m.items(d, L, lay, "up")
    trims = {}
    for name, W, CL in m.trim_legs(d, L):
        fuel = max(0.0, min(d["fuel_lb"], W - (d["W0_lb"] - d["fuel_lb"])))
        x = m.cg(it_up, (d["payload_lb"], lay["payload_x"]), m.fuel_state(fuel, d["fuel_lb"], tk, order0, lay["x_le"]))[1]
        trims[name] = {"CL_wing": CL, "x_cg_ft": x, "CL_tail": m.tail_cl_trim(d, L, lay, CL, x, cm_p2)}
    worst = max(abs(t["CL_tail"]) for t in trims.values())
    stall = {"CL_wing": d["CL_max"]["clean"], "x_cg_ft": min(base["x_cg_full_ft"], base["x_cg_empty_ft"])}
    stall["CL_tail"] = m.tail_cl_trim(d, L, lay, stall["CL_wing"], stall["x_cg_ft"], cm_p2)
    out["rotation"] = rot
    out["trim"] = {"legs": trims, "limit": L["tail_cl_max_trim"], "largest": worst, "verdict": "pass" if worst <= L["tail_cl_max_trim"] else "fail",
                   "clean_stall_forward_cg_reported": stall, "zero_fuel_weight_lb": W_zf}
    out["ground"] = {"propeller_clearance_in": m.propeller_clearance_in(d, L, lay), "propeller_clearance_needed_in": L["prop_clearance_in"],
                     "tipback_needed_deg": L["tipback_angle_deg"], "overturn_limit_deg": L["overturn_max_deg"],
                     "main_wheel_behind_root_le_over_root_chord": (lay["x_main"] - lay["x_le"]) / w["root_chord"]}
    out["tail_rearmost_behind_propeller_plane_ft"] = {k: v - c["propeller_plane_x"] for k, v in m.tail_rearmost(d, L, lay).items()}
    # how close the tailplane's root comes to the wing's: root leading edge of the tail less root trailing edge of the wing
    ht_root_le = st["x_ach_ft"] + (0.75 * ht.mac - ht.root_chord if lay["tail_te_straight"] else -0.25 * ht.mac)
    out["tailplane_root_le_behind_wing_root_te_ft"] = ht_root_le - (lay["x_le"] + w["root_chord"])
    out["tailplane_root_le_ft"] = ht_root_le
    # payload off: the ballast at the payload station that brings the aftmost payload-off loading to the aft limit
    off = max((r for r in rows if not r["payload_on"]), key=lambda r: r["x_cg_ft"])
    need = off["weight_lb"] * (off["x_cg_ft"] - env["aft_limit_ft"]) / (env["aft_limit_ft"] - lay["payload_x"])
    out["payload_off"] = {"aftmost_loading": {k: off[k] for k in ("gear", "empty_weight_factor", "tank_order", "fuel_lb", "weight_lb", "x_cg_ft", "static_margin")},
                          "ballast_at_payload_station_lb": max(0.0, need)}
    log(f"{label}: static margin full {base['sm_full']:.4f}, empty {base['sm_empty']:.4f} (row 1 {base['verdict']}); "
        f"row 3 {env['row3']} ({env['payload_on']['outside_envelope']} payload-on and {env['payload_off']['outside_envelope']} payload-off loadings outside); "
        f"row 4 {env['row4']}; rotation {rot['used_of_limit']:.3f} of the tail limit; trim largest {worst:.3f}")
    return out


def run_vspaero(c, out, python, log):
    """Step 3, or the reason it was not run (PD-14)."""
    if not python:
        return "no OpenVSP interpreter was given (--openvsp-python)"
    d = c["d"]
    folder = out / "vspaero"
    folder.mkdir(parents=True, exist_ok=True)
    a = isa(c["L"]["mission_altitude_ft"])["a"]
    data = {"model": p3.vsp_input(c["model"]), "levels": VSP_LEVELS, "mach": d["propeller_points"]["loiter"]["V_kt"] * KT / a,
            "ref": {"Sref": d["wing"]["area"], "bref": d["wing"]["span"], "cref": d["wing"]["mac"], "Xcg": d["layout"]["cg_full"]}}
    (folder / "input.json").write_text(json.dumps(data))
    try:
        r = subprocess.run([python, "-m", "prelim.p4_vspaero", str(folder / "input.json"), str(folder)],
                           capture_output=True, text=True, cwd=REPO, timeout=7200)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"the OpenVSP interpreter could not be run: {e}"
    if r.returncode != 0 or not (folder / "vspaero.json").exists():
        return "the VSPAERO run failed: " + (r.stderr.strip().splitlines() or ["no message"])[-1]
    v = load(folder / "vspaero.json")
    for k, lv in v["levels"].items():
        log(f"VSPAERO {k}: {lv['mesh']['panels']} panels, CL_alpha {lv['CL_alpha_per_rad']:.4f}, neutral point {lv['x_np_ft']:.4f} ft"
            + ("" if lv["valid"] else f" (rejected: {lv['valid_reason']})"))
    return v


def r1_solutions(c, lay0, log):
    """Row 5 and PD-20: the wing alone with r0's tail (row 5 as the spec words it); the tail clear of the disc with
    r0's tail planforms (the first form of PD-20, which may not close); the chosen form with straight trailing
    edges, at the chosen clearance and at its band ends. A form with no solution is recorded with the reason, and
    a scan over the wing position shows why."""
    d, L, ch = c["d"], c["L"], c["choices"]
    args = (d, L, lay0, c["tanks"], ch, c["body"], c["src"], c["propeller_plane_x"])
    clr = ch["r1"]["propeller_clearance_ft"]
    cm_w = m.wing_moment(c["cm0_p2"], d["A"])
    shifts = [round(0.2 * i, 1) for i in range(9)]
    out = {}
    for name, kw in (("wing_alone_r0_tail", {"retail_tail": False}), ("r0_tail_planforms_clear_of_disc", {"straight_te": False}),
                     ("chosen", {}), ("clearance_band_low", {"clearance": clr["band"][0]}), ("clearance_band_high", {"clearance": clr["band"][1]})):
        row = {"clearance_ft": None if "retail_tail" in kw else kw.get("clearance", m.val(clr)), "straight_trailing_edges": kw.get("straight_te", "retail_tail" not in kw)}
        if "retail_tail" not in kw:
            row["scan"] = m.scan_wing_positions(*args, cm_w, shifts, **kw)
        try:
            lay, st = m.solve_r1(*args, **kw)
        except ValueError as err:
            out[name] = dict(row, closed=False, reason=f"no wing position between r0's and 3 ft aft of it gives a mean static margin of 0.10 ({err})")
            log(f"r1 {name}: no solution")
            continue
        fwd = min(m.cg_ends(d, L, lay, c["tanks"], ch, gear="down"))
        out[name] = dict(row, closed=True, layout=lay, mean_static_margin=st["mean_static_margin"], x_np_ft=st["x_np_power_off_ft"],
                         CL_tail_rotation=m.rotation(d, L, lay, fwd, cm_w)["CL_tail_needed"])
        log(f"r1 {name}: wing leading edge {lay['x_le']:.4f} ft ({lay['x_le'] - lay0['x_le']:+.4f}), tail arm {lay['arm']:.4f} ft "
            f"({lay['arm'] - lay0['arm']:+.4f}), tailplane {lay['ht_area']:.2f} ft^2, main wheels {lay['x_main']:.4f} ft, "
            f"tail lift coefficient at rotation {out[name]['CL_tail_rotation']:.4f}")
    return out


def _plain(obj):
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    return obj


def acceptance_rows(res):
    a, r1 = res["as_arranged"], res["r1"]["evaluation"]
    failed = [k for k, v in (("1", a["row1"]["gear_up/empty_weight_x1"]["verdict"]), ("3", a["envelope"]["row3"]), ("4", a["envelope"]["row4"])) if v == "fail"]
    restored = {"1": r1["row1"]["gear_up/empty_weight_x1"]["verdict"], "3_payload_on": r1["envelope"]["row3_payload_on_only"],
                "3_all": r1["envelope"]["row3"], "4_payload_on": r1["envelope"]["row4_payload_on_only"], "4_all": r1["envelope"]["row4"]}
    return [{"row": 1, "what": ROW_NAMES["1"], "verdict": a["row1"]["gear_up/empty_weight_x1"]["verdict"]},
            {"row": 2, "what": ROW_NAMES["2"], "verdict": row2_verdict(a["neutral_point"]["difference_mac"])},
            {"row": 3, "what": ROW_NAMES["3"], "verdict": a["envelope"]["row3"], "payload_on_only": a["envelope"]["row3_payload_on_only"]},
            {"row": 4, "what": ROW_NAMES["4"], "verdict": a["envelope"]["row4"], "payload_on_only": a["envelope"]["row4_payload_on_only"]},
            {"row": 5, "what": ROW_NAMES["5"], "verdict": "computed" if failed else "not needed", "rows_that_failed": failed, "on_the_r1_layout": restored}]


def findings(res):
    """The findings for r1 (PD-7), each with its numbers from this record."""
    a, r, d = res["as_arranged"], res["r1"], res["r0"]
    e, lay, lay0 = r["evaluation"], r["evaluation"]["layout"], a["layout"]
    b0, b1 = a["row1"]["gear_up/empty_weight_x1"], e["row1"]["gear_up/empty_weight_x1"]
    n0, n1 = a["neutral_point"], e["neutral_point"]
    mac = d["wing"]["mac"]
    out = [f"On r0 with the P3 arrangement the static margin is {b0['sm_full']:.4f} full and {b0['sm_empty']:.4f} empty of fuel (gear up, "
           f"independent neutral point at {n0['independent_power_off_ft']:.3f} ft, power off): R13 (0.05 to 0.15) {b0['verdict']}s.",
           f"Fuselage term: Multhopp on the loft gives C_m_alpha {n0['Cma_fus_multhopp_per_rad']:.4f} per rad against Raymer (16.22)'s "
           f"{n0['Cma_fus_raymer_16_22_per_rad']:.4f}; the neutral point is {n0['difference_mac']:+.4f} MAC from Stage 1's method. "
           "r1 should carry the fuselage term of this package.",
           f"Wing for r1: leading edge at the root from {lay0['x_le']:.3f} ft to {lay['x_le']:.3f} ft ({lay['x_le'] - lay0['x_le']:+.3f} ft).",
           f"Tail for r1 (PD-20): arm from {lay0['arm']:.3f} ft to {lay['arm']:.3f} ft ({lay['arm'] - lay0['arm']:+.3f} ft), {lay['arm'] / d['fuselage']['length']:.4f} of the "
           f"fuselage length against Stage 1's 0.475; tailplane {lay0['ht_area']:.2f} to {lay['ht_area']:.2f} ft^2, fin {lay0['vt_area']:.2f} to {lay['vt_area']:.2f} ft^2 "
           f"(volume coefficients kept); trailing edges straight; every tail point inside the disc {r['clearance_ft']:.2f} ft ahead of the propeller plane.",
           f"The tailplane of the r1 layout is {lay['ht_area'] / d['wing']['area']:.3f} of the wing area and its root leading edge is "
           f"{e['tailplane_root_le_behind_wing_root_te_ft']:.2f} ft behind the wing's root trailing edge ({a['tailplane_root_le_behind_wing_root_te_ft']:.2f} ft in r0). "
           "The methods used here (lattice downwash at the tail's quarter chord, Multhopp's linear rise behind the wing, a tail lift slope for an isolated surface) "
           "were not made for a tail this large and this close; the layout closes on paper and is a risk for Gate C.",
           f"Main wheels for r1: {lay0['x_main']:.3f} ft to {lay['x_main']:.3f} ft (tipback rule); nose wheel unchanged.",
           f"Weights for r1 by Raymer (15.47)-(15.49): tailplane {lay['weights']['horizontal_tail'] - lay0['weights']['horizontal_tail']:+.2f} lb, fin "
           f"{lay['weights']['vertical_tail'] - lay0['weights']['vertical_tail']:+.2f} lb, fuselage {lay['weights']['fuselage'] - lay0['weights']['fuselage']:+.2f} lb; "
           f"empty weight {e['empty_weight_lb'] - a['empty_weight_lb']:+.2f} lb (the aircraft was not re-sized).",
           f"With these the static margin is {b1['sm_full']:.4f} full and {b1['sm_empty']:.4f} empty (row 1 {b1['verdict']}); payload-on loadings outside the "
           f"envelope: {e['envelope']['payload_on']['outside_envelope']} of {e['envelope']['payload_on']['loadings']}; nose-wheel load "
           f"{100 * e['envelope']['payload_on']['nose_load_min']:.1f} to {100 * e['envelope']['payload_on']['nose_load_max']:.1f} % with the payload on.",
           f"Rotation with P2's section moment ({res['cm0_p2']:.4f} against the ledger's {res['ledger_cm0']:.2f}): the tail needs "
           f"{abs(a['rotation']['p2_section_moment']['CL_tail_needed']):.4f} of {a['rotation']['limit']:.2f} on r0 as arranged and "
           f"{abs(e['rotation']['p2_section_moment']['CL_tail_needed']):.4f} on the r1 layout ({e['rotation']['verdict']}). "
           "r1 should run Stage 1's tail loop with the measured section moment.",
           f"Payload off: the centre of gravity goes as far aft as {e['payload_off']['aftmost_loading']['x_cg_ft']:.3f} ft (static margin "
           f"{e['payload_off']['aftmost_loading']['static_margin']:+.4f}) on the r1 layout; {e['envelope']['payload_off']['outside_envelope']} of "
           f"{e['envelope']['payload_off']['loadings']} payload-off loadings are outside the envelope. Flight without the payload needs "
           f"{e['payload_off']['ballast_at_payload_station_lb']:.0f} lb of ballast at the payload station (an operating limit, PD-13).",
           f"Nose-wheel load on the r1 layout with the payload on: {100 * e['envelope']['payload_on']['nose_load_min']:.1f} to "
           f"{100 * e['envelope']['payload_on']['nose_load_max']:.1f} %; {e['envelope']['payload_on']['nose_load_outside_optimum']} of the gear-down loadings are outside "
           "Raymer's 8 to 15 % optimum (item 31).",
           f"Empty-weight band (NR-14) on the r1 layout: static margin {e['row1']['gear_up/empty_weight_x0.95']['sm_full']:.4f} / "
           f"{e['row1']['gear_up/empty_weight_x0.95']['sm_empty']:.4f} at 0.95 and {e['row1']['gear_up/empty_weight_x1.05']['sm_full']:.4f} / "
           f"{e['row1']['gear_up/empty_weight_x1.05']['sm_empty']:.4f} at 1.05 (full / empty).",
           f"Power on (no verdict): the propeller's normal force moves the neutral point aft by {n1['power_on']['loiter']['shift_mac']:.4f} MAC at loiter and "
           f"{n1['power_on']['climb_sea_level']['shift_mac']:.4f} MAC in the sea-level climb on the r1 layout; slipstream effects on the tail are not modelled.",
           "For P9, not answered here: the sponson that does not hold the retracted main gear (P3 finding 7; the main wheels move with this package); "
           "where the tail roots sit on the engine bay; Stage 1 needs the tail arm as an input."]
    if abs(n1["difference_mac"] - n0["difference_mac"]) > 0:
        out.insert(2, f"On the r1 layout the two fuselage terms differ by {n1['difference_mac']:+.4f} MAC in neutral point (independent less Stage 1's method).")
    return out


def run(out, log, openvsp_python=None):
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P4 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "arrangement": p3.ARRANGEMENT,
             "p3_record": P3_RECORD, "p2_record": P2_RECORD, "p6_record": P6_RECORD, "sources": m.SOURCES, "choices": m.CHOICES}
    c = context()
    d, L = c["d"], c["L"]
    res = {"inputs": dict(tree, command="python -m prelim.p4_balance " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P4", python=platform.python_version(),
                          numpy=np.__version__, scipy=scipy.__version__, pyyaml=yaml.__version__, matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()},
                          sha256={k: sha256(p) for k, p in files.items()}),
           "evidence_class": EVIDENCE_CLASS, "baseline": str(R0.relative_to(REPO)), "sources": c["src"], "choices": c["choices"],
           "cm0_p2": c["cm0_p2"], "ledger_cm0": L["airfoil_cm0"], "tanks": c["tanks"], "propeller_plane_x_ft": c["propeller_plane_x"],
           "propeller_disc_radius_ft": 0.5 * d["propeller_diameter_ft"],
           "r0": {"W0_lb": d["W0_lb"], "fuel_lb": d["fuel_lb"], "payload_lb": d["payload_lb"], "wing": d["wing"], "fuselage": d["fuselage"],
                  "stations": d["stations"], "tail_arm_ft": d["tail_arm_ft"], "ht_volume_scale": d["ht_volume_scale"],
                  "layout": {k: d["layout"][k] for k in ("x_le", "x_ac", "x_np", "cg_full", "cg_empty", "sm_full", "sm_empty", "x_main", "h_cg",
                                                         "dah_da", "Cma_fus", "CLa_h", "nose_load", "rotation", "cm_wing", "prop_clearance_in")}}}
    log(f"commit {tree['commit']}, clean tree")
    lay0 = m.base_layout(d, c["p3"])
    res["as_arranged"] = evaluate(c, lay0, "r0 as P3 arranged it", log, with_alternatives=True)
    v = run_vspaero(c, out, openvsp_python, log)
    res["openvsp_python"] = openvsp_python
    res["vspaero"] = {"result": v, "verdict": vspaero_verdict(v["levels"] if isinstance(v, dict) else v, d["wing"]["mac"])}
    log("VSPAERO: " + (res["vspaero"]["verdict"].get("note") or res["vspaero"]["verdict"].get("reason")))
    sols = r1_solutions(c, lay0, log)
    chosen = sols["chosen"]["layout"]
    res["r1"] = {"solutions": sols, "clearance_ft": sols["chosen"]["clearance_ft"],
                 "evaluation": evaluate(c, chosen, "r1 layout (PD-20)", log),
                 "wing_alone_evaluation": evaluate(c, sols["wing_alone_r0_tail"]["layout"], "wing alone, r0's tail", log)}
    model = ac.build(record_with_layout(d, L, chosen), L, c["A"])
    res["r1"]["row9_on_the_loft"] = gates.row9_propeller_disc(model, ac.meshes(model))
    res["r1"]["tail_arm_over_fuselage_length"] = chosen["arm"] / d["fuselage"]["length"]
    log(f"r1 layout on the loft: row 9 {res['r1']['row9_on_the_loft']['verdict']} "
        f"(tailplane {res['r1']['row9_on_the_loft']['behind_plane_ft']['horizontal_tail']:+.3f} ft, fin "
        f"{res['r1']['row9_on_the_loft']['behind_plane_ft']['vertical_tail']:+.3f} ft from the propeller plane)")
    res["acceptance"] = acceptance_rows(res)
    res["findings_for_r1"] = findings(res)
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == tree["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p4.json").write_text(json.dumps(_plain(res), indent=1))
    log(", ".join(f"row {a['row']} {a['verdict']}" for a in res["acceptance"]) + f" ({time.time() - t0:.0f} s)")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--openvsp-python", help="a python that has the OpenVSP API; without it step 3 is recorded 'not run'")
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the figures (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and figures from OUT/p4.json")
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
        run(out, log, a.openvsp_python)
    if a.report:
        from prelim import p4_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p4_report.write_figures(out, figures)
        report.write_text(p4_report.report_text(out))


if __name__ == "__main__":
    main()

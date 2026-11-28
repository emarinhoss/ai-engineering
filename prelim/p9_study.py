"""Preliminary design P9: the checks on r1 and the re-runs (spec P9; decisions PD-25, PD-26).

Not yet Fable-reviewed (rulings PD-22 and PD-25).

    python -m prelim.p9_study reruns     --design R1 --out runs/task12/pd/2026-11-28/p9/reruns
    python -m prelim.p9_study robustness --design R1 --out runs/task12/pd/2026-11-28/p9/robustness
    python -m prelim.p9_study built      --design R1 --out runs/task12/pd/2026-11-28/p9/built
    python -m prelim.p9_study cd0        --design R1 --out runs/task12/pd/2026-11-28/p9/cd0
    python -m prelim.p9_study p8         --design R1 --reruns .../reruns/reruns.json --out runs/task12/pd/2026-11-28/p9/p8_r1

R1 is r1's record (runs/task12/pd/2026-11-28/p9/passN/r1/design_pusher.json). Each command writes its own record from a
clean committed tree. `reruns`: P3's gates, P4's route (balance, R13, ballast), P5's rows 1, 2, 3 and 5 and P7's spar on
r1, with each package's own code. `robustness`: the mode scans, the doubled-steps bias and refinement (NR-13) and the full
info-gap study. `built`: r0 as built with the findings applied (no re-size), each finding alone, and the faired-peak
sensitivity on r1. `cd0`: the full info-gap study of r1 with the parasite drag held 10 % higher and lower (a labelled
sensitivity). `p8`: the envelope-protection requirement regenerated on r1 by prelim/p8_envelope.py.
"""
import argparse
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import yaml

from conceptual import uav
from conceptual.units import KT
from geometry3d import aircraft as ac
from geometry3d import gates
from measurement import info_gap
from measurement import robust_sizing as rs
from measurement import stage3_perf as sp
from prelim import p3_loft as p3
from prelim import p4_methods as m
from prelim import p5_loads as p5
from prelim import p7_spar as p7
from prelim import p9_r1 as p9

REPO = p9.REPO
OPENVSP_PYTHON = Path("/tmp/claude-0/-home-user/d15a4c10-d7a3-5006-96e8-4d0a5f6097f0/scratchpad/vspenv/bin/python")
# r1's ledger entries that carry an applied finding, by finding group (one at a time on the built r0)
GROUPS = {"P1 integrated climb": ("climb_model",),
          "P2 section maximum lift": ("airfoil_cl_max",),
          "P2 section moment": ("airfoil_cm0",),
          "P3 loft wetted areas": tuple("loft_wetted_factor_" + k for k in p9.COMPONENTS),
          "P3 tank volume": ("tank_volume_factor",),
          "P3 payload and avionics stations": ("station_payload_ft", "station_avionics_ft"),
          "PD-27 sponson": ("sponson_size_factor",),
          "PD-21 tails with straight trailing edges": ("tail_trailing_edges",),
          "PD-21 aft fuselage and shaft": ("fuselage_extension_ft", "fuselage_added_skin_ft2", "shaft_lb_per_ft"),
          "P4 Multhopp's fuselage term": ("fuselage_cm_alpha_factor",)}


def r1_entries(L):
    """{entry: value} of every r1 ledger entry that carries an applied finding (PD-26 item 1)."""
    names = {n for g in GROUPS.values() for n in g}
    return {k: L[k] for k in sorted(names)}


# ---- P3 on r1 -----------------------------------------------------------------------------------------------------
def p3_on_r1(d, L, A, out, log=print):
    """P3's gates on r1's loft (the lengthened body, straight-trailing-edge tails, the resized sponson). Gate 3 compares
    the loft's wetted area with the area r1's drag build-up uses (the record's s_wet_drag_ft2), within P3's 5 %; gate 4
    is P3's own; gates 1, 2, 5, 6 and row 9 as P3; gate 8 with OpenVSP if its interpreter is there. Gate 7 (the STL
    writer) and row 10 (mesh doubling) are not run: r1 changes neither the writer nor the mesh."""
    e = d["fuselage"].get("extension_ft", 0.0)
    model = p9.loft(d, L, A, e)
    parts = ac.meshes(model)
    dl = p9.loft_record(d, L)
    g3 = gates.gate3_wetted(model, parts, dl, L)
    for k, r in g3["components"].items():
        r["r1_build_up_ft2"] = d["s_wet_drag_ft2"][k]
        r["loft_over_r1_build_up"] = r["loft_wetted_ft2"] / r["r1_build_up_ft2"] - 1.0
        r["verdict_against_r1_build_up"] = "pass" if abs(r["loft_over_r1_build_up"]) <= gates.TOL_WETTED else "fail"
    g3["failing_against_r1_build_up"] = [k for k, r in g3["components"].items() if r["verdict_against_r1_build_up"] == "fail"]
    g3["verdict_against_r1_build_up"] = "fail" if g3["failing_against_r1_build_up"] else "pass"
    g = {"1": gates.gate1_watertight(parts), "2": gates.gate2_targets(model, dl), "3": g3,
         "4": gates.gate4_volumes(model, parts, dl, L, A), "5": gates.gate5_smoothness(model),
         "6": gates.gate6_ground(model, parts, dl, L), "9": gates.row9_propeller_disc(model, parts),
         "7": {"verdict": "not run", "reason": "r1 changes neither the STL writer nor the parts it writes (P3's row 7 passed)"},
         "10": {"verdict": "not run", "reason": "the mesh is P3's (P3's row 10: +0.77 % at most from the base mesh to four times finer)"}}
    vsp = p3.run_openvsp(model, out, str(OPENVSP_PYTHON) if OPENVSP_PYTHON.exists() else None)
    g["8"] = gates.gate8_openvsp(g3["components"], vsp)
    for k in ("1", "2", "3", "4", "5", "6", "8", "9"):
        verdict = g[k].get("verdict_against_r1_build_up", g[k]["verdict"]) if k == "3" else g[k]["verdict"]
        log(f"P3 on r1, gate {k}: {verdict}" + (f" ({g[k].get('failing')})" if g[k].get("failing") else ""))
    return {"gates": g, "moved_masses": p3.moved_masses(dl, g["4"]), "sponson_need": p3.sponson_need(model, g["4"]),
            "loft": {"fuselage_length_ft": model["fuselage"].length, "propeller_plane_x_ft": model["propeller"]["x"],
                     "sponson": {k: getattr(model["sponson_left"], k) for k in ("a", "b", "c")},
                     "sponson_centre": model["sponson_left"].centre.tolist()}}


# ---- P4 on r1 -----------------------------------------------------------------------------------------------------
def p4_on_r1(d, L, A, log=print):
    """P4's route on r1 (prelim/p9_r1.p4_route): the wing placed by P4's rule with Multhopp's term, rows 1 to 4 of P4,
    the tail clear of the disc, and P4b's payload-off ballast. Rows judged as P4 judged them."""
    route = p9.p4_route(d, L, A, d["fuselage"].get("extension_ft", 0.0), log)
    e, lay = route["evaluation"], route["layout"]
    env, on, off = e["envelope"], e["envelope"]["payload_on"], e["envelope"]["payload_off"]
    base = e["row1"]["gear_up/empty_weight_x1"]
    rows = {"row1_R13": base["verdict"], "row3_envelope_payload_on": env["row3_payload_on_only"],
            "row4_nose_load_payload_on": env["row4_payload_on_only"], "rotation_tail_lift": e["rotation"]["verdict"],
            "trim_tail_lift": e["trim"]["verdict"],
            "propeller_ground_clearance": "pass" if e["ground"]["propeller_clearance_in"] >= L["prop_clearance_in"] else "fail",
            "tails_clear_of_disc": "pass" if route["extension_needed_ft"] <= d["fuselage"].get("extension_ft", 0.0) + p9.TOL_LENGTH_FT else "fail",
            "overturn": "pass" if on["overturn_max_deg"] <= L["overturn_max_deg"] else "fail",
            "row3_envelope_payload_off_no_ballast": "pass" if off["outside_envelope"] == 0 else "fail",
            "with_ballast": "pass" if route["ballast"]["with_that_ballast"]["outside_envelope"] == 0 else "fail"}
    mac = d["wing"]["mac"]
    return {"layout": lay, "x_le_stage1_ft": d["layout"]["x_le"], "x_le_p4_ft": lay["x_le"],
            "wing_p4_minus_stage1_ft": lay["x_le"] - d["layout"]["x_le"], "x_main_stage1_ft": d["layout"]["x_main"],
            "x_main_p4_ft": lay["x_main"], "neutral_point": e["neutral_point"], "row1": e["row1"], "envelope": env,
            "rotation": e["rotation"], "trim": e["trim"], "ground": e["ground"],
            "static_margin": {"full": base["sm_full"], "empty": base["sm_empty"]},
            "stage1_static_margin": {"full": d["layout"]["sm_full"], "empty": d["layout"]["sm_empty"]},
            "neutral_point_difference_mac": e["neutral_point"]["difference_mac"],
            "ballast": route["ballast"], "payload_off": e["payload_off"], "extension_needed_ft": route["extension_needed_ft"],
            "extension_used_ft": d["fuselage"].get("extension_ft", 0.0), "tail_rearmost_ft": route["tail_rearmost_ft"],
            "propeller_plane_unextended_ft": route["propeller_plane_unextended_ft"],
            "multhopp_over_16_22": route["multhopp_over_16_22"], "rows": rows, "mac_ft": mac,
            "tanks": route["context"]["tanks"], "tailplane_root_le_behind_wing_root_te_ft": e["tailplane_root_le_behind_wing_root_te_ft"]}


# ---- P5 on r1 -----------------------------------------------------------------------------------------------------
def p5_context(design, ballast_lb):
    """P5's context with r1 in place of r0: r1 rebuilt (stage3_perf.rebuild raises if it does not reproduce the
    record), P2's negative section lift, the ballast of P4's route on r1, no further weight change."""
    d, L, b, _, check = sp.rebuild(design)
    p2 = json.loads(p9.P2_RECORD.read_text())
    return {"d": d, "L": L, "b": b, "rebuild_check": check, "src": p5.load_sources(),
            "p2_negative_set": next(s for s in p2["measured"] if s["set"] == 2),
            "p4b_chosen": "P4's route on r1 (prelim/p9_r1.p4_route)", "ballast_lb": ballast_lb, "r1_empty_weight_change_lb": 0.0}


def p5_on_r1(c):
    """P5's rows 1, 2, 3 and 5 on r1 with P5's code, and row 4's load factors (the second text's gust speeds and the
    gust held at 30 ft/s above V_C) without the weight cost (that needs Stage 1 re-sized with a raised limit, which is
    O-2's question and was not re-run)."""
    W = p5.weights(c)
    V_C, V_D, top = p5.speeds(c)
    out = {"weights": W, "ballast_lb": c["ballast_lb"], "row1": p5.row1(c), "row2": p5.row2(c), "row3": p5.row3(c),
           "row5": p5.row5(c),
           "r0": {"V_C_kt": V_C / KT, "V_D_kt": V_D / KT, "level_top_speed_kt": {k: v / KT for k, v in top.items()},
                  "note": "the baseline of this record is r1 (P5's key names are kept so that P8 reads it)"}}
    cases = {}
    for name, kw in (("cs23_speeds", {"rule": "cs23"}), ("ruled_held_30", {"U_cap": c["L"]["gust_ude_fps"]})):
        pts = [dict(p, weight=wl) for wl in ("takeoff", "zero_fuel") for p in p5.gust_points(c, W[wl], **kw)]
        cleared = [p for p in pts if p["speed"] in ("V_C", "V_D")]
        cases[name] = {"points": pts, "largest_up_V_C_V_D": max(p["n_up"] for p in cleared),
                       "lowest_down_V_C_V_D": min(p["n_down"] for p in cleared)}
    out["row4"] = {"cases": cases, "weight_cost": "not re-run on r1 (O-2; PD-8)", "verdict": "reported (no verdict)"}
    out["acceptance"] = [{"row": r, "verdict": out[f"row{r}"]["verdict"]} for r in (1, 2, 3, 5)]
    return out


# ---- P7 on r1 -----------------------------------------------------------------------------------------------------
def p7_on_r1(d, L, A, p4r, p5r, log=print):
    """P7's spar on r1: r1's wing and weights, P4's layout, centre of gravity and tanks on r1, P5's r1 load factors,
    r1's maximum lift; the ruled cases (P5 row 4's sensitivity cases are not re-run). Rows 1 to 5 as P7 judged them."""
    base1 = p4r["row1"]["gear_up/empty_weight_x1"]
    p5like = {"row3": p5r["row3"], "r0": p5r["r0"],
              "r1": {"row3": {"worst_up_r1": p5r["row3"]["worst_up"]["n_up"], "worst_down_r1": p5r["row3"]["worst_down"]["n_down"]}}}
    c = {"d": d, "L": L, "A": A, "ch": p7.load_choices(), "p5": p5like, "cm_w": m.wing_moment(L["airfoil_cm0"], d["A"]),
         "tanks": p4r["tanks"], "CL_max_p2": d["CL_max"]["clean"], "r1_empty_weight_change_lb": 0.0}
    cg = {"full": base1["x_cg_full_ft"], "empty": base1["x_cg_empty_ft"], "W_full": base1["weight_full_lb"],
          "W_empty": base1["weight_empty_lb"]}
    r2 = p7.row2(c)
    lattice = None
    if r2["used"] == "lattice":
        lv = r2["lattice"][r2["lattice_level"]]
        lattice = (np.array(lv["y_ft"]), np.array(lv["cl_c_ft"]), np.array(lv["dy_ft"]))
    base = p7.solve(c, p4r["layout"], cg, "r1", r2["used"], lattice)
    out = {"row1": p7.row1(c, base), "row2": {k: v for k, v in r2.items() if k not in ("lattice", "schrenk_on_stations")},
           "row3": p7.row3(base), "row4": p7.row4(base), "row5": p7.row5(c, base),
           "cases": [p7.case_summary(e, base["wing"]) for e in base["cases"]],
           "root_M_env_ult_lbft": float(base["M_env"][0]), "root_moment_case": base["M_env_case"][0]}
    out["acceptance"] = [{"row": r, "verdict": out[f"row{r}"]["verdict"]} for r in (1, 2, 3, 4, 5)]
    log(f"P7 on r1: spar {out['row5']['spar_lb']:.2f} lb ({100 * out['row5']['share']:.1f} % of r1's wing), rows "
        + ", ".join(f"{a['row']} {a['verdict']}" for a in out["acceptance"]))
    return out


def cmd_reruns(out, design, log):
    t0 = time.time()
    own, inputs = p9.start(out, "reruns")
    d, L = p9.load(design), uav.load_ledger(design.parent / "ledger.yaml")[0]
    A = yaml.safe_load(p9.ARRANGEMENT.read_text())
    res = {"inputs": dict(inputs, design=str(design.relative_to(REPO)), design_sha256=p9.sha256(design),
                          ledger_sha256=p9.sha256(design.parent / "ledger.yaml"), seed=None,
                          seed_note="no random numbers are drawn in these re-runs")}
    log("P3's gates on r1's loft")
    res["p3"] = p3_on_r1(d, L, A, out, log)
    log("P4's route on r1")
    res["p4"] = p4_on_r1(d, L, A, log)
    log("P5's rows on r1")
    c5 = p5_context(design, res["p4"]["ballast"]["ballast_every_loading_lb"])
    res["p5"] = p5_on_r1(c5)
    log("P5 on r1: " + ", ".join(f"row {a['row']} {a['verdict']}" for a in res["p5"]["acceptance"]))
    res["p7"] = p7_on_r1(d, L, A, res["p4"], res["p5"], log)
    p9.finish(out, own, res, "reruns.json", t0)
    (out / "p5_r1.json").write_text(json.dumps(p9.plain(res["p5"]), indent=1))           # for P8 (its "p5" record)
    log(f"done ({time.time() - t0:.0f} s)")


# ---- robustness ---------------------------------------------------------------------------------------------------
@contextmanager
def climb_steps_halved():
    """uav.CLIMB_STEP_FT halved while the block runs (the climb's own sub-steps in the doubling check)."""
    old = uav.CLIMB_STEP_FT
    uav.CLIMB_STEP_FT = old / 2.0
    try:
        yield uav.CLIMB_STEP_FT
    finally:
        uav.CLIMB_STEP_FT = old


def step_doubling(design, need):
    """NR-13 and spec P9 acceptance 4: r1 sized again at its L_sized with the mission sub-steps doubled, as
    robust_sizing.step_bias does it (cruise 10 to 20, loiter 16 to 32), and again with the integrated climb's 1,000 ft
    steps halved as well; the W0 change against the tolerance."""
    row = p9.load(design.parent / "robust_candidate.json")
    rec = p9.load(design)
    out = {"cruise_and_loiter": rs.step_bias(p9.POWER, row, rec)}
    with climb_steps_halved() as step:
        out["cruise_loiter_and_climb"] = dict(rs.step_bias(p9.POWER, row, rec), climb_step_ft=step)
    for v in out.values():
        if v.get("closed"):
            v["W0_change_relative"] = v["W0_bias_lb"] / v["W0_as_run_lb"]
            v["within_tolerance"] = abs(v["W0_change_relative"]) < p9.TOL_STEP_W0
    out["tolerance"] = p9.TOL_STEP_W0
    return out


def cmd_robustness(out, design, log):
    t0 = time.time()
    own, inputs = p9.start(out, "robustness")
    rs.use_engine_as_is(True)
    with p9.ledger_in_use(p9.LEDGER_R1):
        need = uav.load_ledger(design.parent / "ledger.yaml")[0]["r5_robust_hours"]
        res = {"inputs": dict(inputs, design=str(design.relative_to(REPO)), design_sha256=p9.sha256(design),
                              seed=info_gap.SEED, n_samples=info_gap.N_SAMPLES, processes=p9.STUDY_PROCESSES)}
        log("mode scans (endurance and cliff)")
        modes, built, variables, pairs, dirs = rs.mode_study(design, need)
        res["modes"] = modes
        log(f"modes: endurance {modes['endurance']['h_hat']:.4f}, cliff {modes['cliff']['h_hat']:.4f}")
        log("step doubling (NR-13)")
        res["step_doubling"] = step_doubling(design, need)
        res["step_refinement"] = rs.step_refinement(built, variables, pairs, dirs, modes, need)
        for k, v in res["step_doubling"].items():
            if isinstance(v, dict):
                log(f"step doubling, {k}: W0 {v.get('W0_as_run_lb', float('nan')):.2f} -> {v.get('W0_x2_lb', float('nan')):.2f} lb")
        log("full info-gap study")
        t1 = time.time()
        ig = info_gap.study(str(design), processes=p9.STUDY_PROCESSES)
        ig["inputs"] = dict(inputs, note="full info_gap.study of r1; worst-case search is the corrected one")
        (out / "info_gap.json").write_text(json.dumps(info_gap._json_safe(ig), indent=1, default=float))
        hh = {k: v["h_hat"] for k, v in ig["h_hat"].items()}
        res["info_gap"] = {"file": str((out / "info_gap.json").relative_to(REPO)), "h_hat": hh, "nominal": ig["nominal"],
                           "w0_check": ig["w0_check"], "runtime_s": time.time() - t1}
        log("info-gap: " + ", ".join(f"{k} {v:.4f}" for k, v in hh.items()))
    p9.finish(out, own, res, "robustness.json", t0)
    log(f"done ({time.time() - t0:.0f} s)")


# ---- the built r0 with the findings, each finding alone, and the faired peak on r1 -----------------------------------
def built_values(built, overrides_theta):
    """What a built aircraft gives with ledger values held (wing area, fuel and tail scale of its record; W0 from the
    empty-weight fixed point): weights, drag, maximum lift, hours on station on the record's fuel, field lengths, the
    stall speed, Stage 1's layout (static margins, wing, wheels) and the service ceiling."""
    th = dict(overrides_theta)
    W0 = built.w0_for(th)
    b, L = built.build(th, W0=W0)
    d = dict(b, W0=W0, W_S=W0 / built.S_record, concept=built.d["concept"], A=built.d["A"])
    lay = uav.layout(d, L)
    per = uav.performance(d, L)
    hours, why = built.hours_detail(th)
    to, ld = built.field_lengths(th)
    return {"W0_lb": W0, "We_lb": b["We"], "components_lb": b["components"], "fuel_needed_at_record_loiter_lb": b["fuel"],
            "record_fuel_lb": built.d["fuel_lb"], "hours_on_station": hours, "hours_reason": why, "takeoff_ft": to,
            "landing_ft": ld, "CD0": {"mission_altitude": b["CD0_alt"], "sea_level": b["CD0_sl"]}, "CL_max": b["clmax"],
            "V_stall_clean_kt": per["V_stall_clean_kt"], "service_ceiling_ft": per["service_ceiling_ft"],
            "power_margin": 1.0 - max(b["power_req"].values()) / b["bhp"], "gear_length_in": b["gear_length_in"],
            "layout": {k: lay[k] for k in ("x_le", "x_np", "cg_full", "cg_empty", "sm_full", "sm_empty", "x_main", "prop_clearance_in")},
            "rotation_tail_cl": lay["rotation"]["CL_tail_needed"], "n_limit": b["n_limit"]}


def worst_point_hours(built, cell, overrides_theta):
    """Hours on station at the record's own worst endurance points (h = 1 and the target h_T, cell_result/robustness
    modes) with ledger values held: the shift of the guarantee's worst point, not a new search."""
    out = {}
    for tag, w in cell.items():
        th = dict(rs.theta_of(w["moved"]), **overrides_theta)
        out[tag] = {"hours": built.hours_detail(th)[0], "record_hours": w["hours"]}
    return out


def cmd_built(out, design, log):
    t0 = time.time()
    own, inputs = p9.start(out, "built")
    rs.use_engine_as_is(True)
    L1 = uav.load_ledger(design.parent / "ledger.yaml")[0]
    entries = r1_entries(L1)
    res = {"inputs": dict(inputs, design=str(design.relative_to(REPO)), r0=str((p9.R0 / "design_pusher.json").relative_to(REPO))),
           "r1_entries": entries}
    b0 = info_gap.Built(p9.R0 / "design_pusher.json")
    r0cell = p9.load(p9.R0 / "cell_result.json")
    worst0 = {"h1": r0cell["modes"]["endurance"]["worst_at_h1"], "h_T": r0cell["worst_at_target"]["endurance"]}
    log("r0 as built, as recorded and with every finding")
    res["r0_built"] = built_values(b0, {})
    res["r0_built_with_findings"] = built_values(b0, entries)
    res["r0_worst_points"] = {"as_recorded": worst_point_hours(b0, worst0, {}), "with_findings": worst_point_hours(b0, worst0, entries)}
    res["one_at_a_time"] = {}
    for name, keys in GROUPS.items():
        v = built_values(b0, {k: entries[k] for k in keys})
        v["worst_points"] = worst_point_hours(b0, worst0, {k: entries[k] for k in keys})
        res["one_at_a_time"][name] = v
        log(f"{name}: W0 {v['W0_lb'] - res['r0_built']['W0_lb']:+.2f} lb, hours {v['hours_on_station'] - res['r0_built']['hours_on_station']:+.3f} h, "
            f"worst point at h_T {v['worst_points']['h_T']['hours']:.3f} h")
    log("r1 as built and with the faired-peak section maximum lift (sensitivity)")
    b1 = info_gap.Built(design)
    rob = p9.load(Path(sys.argv[sys.argv.index("--robustness") + 1])) if "--robustness" in sys.argv else None
    res["r1_built"] = built_values(b1, {})
    res["faired_peak"] = {"section_cl_max": p9.FAIRED_SECTION_CL_MAX, "built": built_values(b1, {"airfoil_cl_max": p9.FAIRED_SECTION_CL_MAX})}
    if rob:
        worst1 = {"h1": rob["modes"]["endurance"]["worst_at_h1"]}
        res["faired_peak"]["worst_points"] = worst_point_hours(b1, worst1, {"airfoil_cl_max": p9.FAIRED_SECTION_CL_MAX})
        res["faired_peak"]["worst_points_as_r1"] = worst_point_hours(b1, worst1, {})
    p9.finish(out, own, res, "built.json", t0)
    log(f"done ({time.time() - t0:.0f} s)")


def cmd_cd0(out, design, log):
    t0 = time.time()
    own, inputs = p9.start(out, "cd0")
    rs.use_engine_as_is(True)
    L1 = uav.load_ledger(design.parent / "ledger.yaml")[0]
    res = {"inputs": dict(inputs, design=str(design.relative_to(REPO)), seed=info_gap.SEED, n_samples=info_gap.N_SAMPLES,
                          processes=p9.STUDY_PROCESSES),
           "label": "a sensitivity, not a band (PD-26 item 9): the parasite drag of r1 as built held 10 % higher and lower "
                    "through P1's route (leakage_fraction), in every rebuild of the full info-gap study", "cases": {}}
    for tag, factor in (("plus_10_percent", 1.0 + p9.CD0_STEP), ("minus_10_percent", 1.0 - p9.CD0_STEP)):
        leak = factor * (1.0 + L1["leakage_fraction"]) - 1.0
        t1 = time.time()
        log(f"CD0 x {factor:g}: leakage_fraction {leak:.4f}")
        ig = info_gap.study(str(design), processes=p9.STUDY_PROCESSES, overrides={"leakage_fraction": leak})
        hh = {k: v["h_hat"] for k, v in ig["h_hat"].items()}
        (out / f"info_gap_{tag}.json").write_text(json.dumps(info_gap._json_safe(ig), indent=1, default=float))
        res["cases"][tag] = {"cd0_factor": factor, "leakage_fraction": leak, "h_hat": hh, "nominal": ig["nominal"],
                             "file": str((out / f"info_gap_{tag}.json").relative_to(REPO)), "runtime_s": time.time() - t1}
        log(f"CD0 x {factor:g}: " + ", ".join(f"{k} {v:.4f}" for k, v in hh.items()))
    p9.finish(out, own, res, "cd0.json", t0)
    log(f"done ({time.time() - t0:.0f} s)")


# ---- P8 on r1 -----------------------------------------------------------------------------------------------------
def cmd_p8(out, design, reruns_path, log):
    """prelim/p8_envelope.py on r1: its records are r1's (the design, its ledger, P5's rows on r1 and P4's ballast on
    r1 from the re-run record); P0, P2b and P6 stay. Its own requirement and report text are written by p8_report."""
    from prelim import p8_envelope as p8
    rr = p9.load(reruns_path)
    ballast = {"selection": {"chosen": "r1"}, "candidates": {"r1": {"measures": {"payload_off": rr["p4"]["ballast"]}}},
               "note": "P4b's ballast rule on r1 (prelim/p9_study.p4_on_r1), in P4b's key layout so that P8 reads it"}
    out.mkdir(parents=True, exist_ok=True)
    (out / "p4b_r1.json").write_text(json.dumps(ballast, indent=1))
    rel = lambda p: str(Path(p).resolve().relative_to(REPO))
    records = dict(p8.RECORDS, r0_design=rel(design), r0_ledger=rel(design.parent / "ledger.yaml"),
                   p5=rel(Path(reruns_path).parent / "p5_r1.json"), p4b=rel(out / "p4b_r1.json"), p8=rel(out / "p8.json"))
    old = dict(p8.RECORDS)
    p8.RECORDS.update(records)
    try:
        c5 = p5_context(design, rr["p4"]["ballast"]["ballast_every_loading_lb"])
        p8.run(out, log, c5=c5)
        from prelim import p8_report
        (out / "requirement_r1.md").write_text(p8_report.requirement_text(out))
    finally:
        p8.RECORDS.clear()
        p8.RECORDS.update(old)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("reruns", "robustness", "built", "cd0", "p8"))
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reruns")
    ap.add_argument("--robustness")
    a = ap.parse_args(argv)
    out, design = (REPO / a.out).resolve(), (REPO / a.design).resolve()
    t0, lines = time.time(), []

    def log(msg, **_):
        lines.append(f"[{time.time() - t0:7.0f} s] {msg}")
        print(lines[-1], flush=True)
        if out.exists():
            (out / f"{a.command}.log").write_text("\n".join(lines) + "\n")
    {"reruns": lambda: cmd_reruns(out, design, log), "robustness": lambda: cmd_robustness(out, design, log),
     "built": lambda: cmd_built(out, design, log), "cd0": lambda: cmd_cd0(out, design, log),
     "p8": lambda: cmd_p8(out, design, REPO / a.reruns, log)}[a.command]()


if __name__ == "__main__":
    main()

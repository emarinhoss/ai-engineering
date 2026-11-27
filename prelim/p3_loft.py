"""Preliminary design P3: lofted geometry and geometry gates of the baseline r0.

    python -m prelim.p3_loft --out runs/task12/pd/<date>/p3 [--openvsp-python PATH] [--report docs/validation/<date>_task12_pd_p3.md]
    python -m prelim.p3_loft --out runs/task12/pd/<date>/p3 --report ... --report-only

Spec: docs/specs/task12_preliminary_design.md, package P3 (E1, E2, E4, E5; gates 1 to 8). The loft is in
geometry3d/; this file runs it on r0, applies the gates, re-runs the Stage 1 drag build-up with the loft's
wetted areas when gate 3 fails, and writes the record OUT/p3.json, OUT/loft.stl and OUT/run.log. r0 is read and
not changed: what the loft finds is a list of findings for the closing re-record r1 (decision PD-7).
"""
import argparse
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

from conceptual import uav
from geometry3d import aircraft as ac
from geometry3d import gates
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
R0 = REPO / "runs/task12/pd/2026-11-27/p0/r0"
ARRANGEMENT = REPO / "data/task12/pd_p3_arrangement.yaml"
TAIL_SOURCE = REPO / "data/task12/pd_p3_tail_section_source.yaml"
EVIDENCE_CLASS = ("layout construction for the geometry; the area and volume rows integrate a surface instead of "
                  "using a factor, so they are independent of Stage 1's formulas (spec P3). The tail section data are "
                  "measured values of NACA Report 586, independent of Stage 1 and of the library")
RENDER_LABEL = "geometry only, no flow solution"
KT = 1.6878098571


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    """(design record, ledger values, arrangement file) of r0."""
    return load(R0 / "design_pusher.json"), uav.load_ledger(R0 / "ledger.yaml")[0], yaml.safe_load(ARRANGEMENT.read_text())


# ---- tail section data (addition 1) -------------------------------------------------------------------------
def tail_section(d, L):
    """The NACA 0012 rows of Report 586, Table I, and the tail's Reynolds numbers on r0. For each flight
    condition the values are interpolated between the two rows that bracket the Reynolds number, in
    log10(R); an interpolation, labelled as such. The negative maximum lift is minus the positive one
    (symmetrical section, not a reading)."""
    src = yaml.safe_load(TAIL_SOURCE.read_text())["naca0012"]
    rows = sorted((dict(zip(src["columns"], r)) for r in src["rows"]), key=lambda r: r["reynolds_millions"])
    lgR = np.log10([r["reynolds_millions"] * 1e6 for r in rows])
    sl, alt = uav.isa(0.0), uav.isa(L["mission_altitude_ft"])
    perf, pts = d["performance"], d["propeller_points"]
    cond = {"stall, clean, sea level": (perf["V_stall_clean_kt"] * KT, sl),
            "rotation, sea level": (d["layout"]["rotation"]["V_kt"] * KT, sl),
            "loiter, mission altitude": (pts["loiter"]["V_kt"] * KT, alt),
            "cruise out, mission altitude": (pts["cruise_out"]["V_kt"] * KT, alt),
            "V_C, sea level": (d["V_c_eas_kt"]["sea_level"] * KT, sl)}
    out = {}
    for name, (V, atm) in cond.items():
        out[name] = {"V_fps": V}
        for tail, chord in (("horizontal_tail", d["horizontal_tail"]["mac"]), ("vertical_tail", d["vertical_tail"]["mac"])):
            R = atm["rho"] * V * chord / atm["mu"]
            inside = lgR[0] <= math.log10(R) <= lgR[-1]
            out[name][tail] = {"reynolds": R, "inside_table": bool(inside),
                               **{k: float(np.interp(math.log10(R), lgR, [r[k] for r in rows]))
                                  for k in ("a0_per_deg", "cl_max", "cd0_min")}}
            out[name][tail]["cl_max_negative"] = -out[name][tail]["cl_max"]
    return {"rows": rows, "conditions": out, "source": src["source"], "reynolds_number_is": src["reynolds_number_is"]}


# ---- the drag build-up with the loft's areas (gate 3, when it fails) --------------------------------------
def buildup_with_loft_areas(d, components):
    """Stage 1's drag build-up and mission on the built aircraft (measurement.info_gap.Built: the record's
    weight, wing area, engine table and fuel), once as recorded and once with the five wetted areas replaced by
    the loft's. Only the areas change: the form factors, interference factors, reference lengths and the weights
    stay Stage 1's (the fuselage and sponson weights also depend on wetted area; that is left to r1). Returns
    CD0 at the mission altitude and at sea level (Stage 1's reference speeds) and the hours on station on the
    record's fuel at the record's take-off weight."""
    from measurement import info_gap
    from prelim.p1_package import hours_for_fuel
    built = info_gap.Built(R0 / "design_pusher.json")
    keys = {"wing": "s_wet_wing", "fuselage": "s_wet_fus", "horizontal_tail": "s_wet_ht",
            "vertical_tail": "s_wet_vt", "sponsons": "s_wet_sponsons"}
    stage1 = {k: components[k]["stage1_ft2"] for k in keys}
    loft = {k: components[k]["loft_wetted_ft2"] for k in keys}
    original = uav._geometry
    seen = {}

    def case(areas):
        def geometry(*args, **kw):
            g = original(*args, **kw)
            seen.update({k: g[q] for k, q in keys.items()})          # what Stage 1 itself computes
            if areas is not None:
                g.update({keys[k]: v for k, v in areas.items()})
            return g
        uav._geometry = geometry
        try:
            state = built.build({}, W0=d["W0_lb"])[0]
            hours = hours_for_fuel(lambda h: built.fuel_at({}, h, d["W0_lb"])[0], d["fuel_lb"])
        finally:
            uav._geometry = original
        return {"CD0_mission_altitude": state["CD0_alt"], "CD0_sea_level": state["CD0_sl"], "hours_on_station": hours}

    base, new = case(None), case(loft)
    return {"as_recorded": base, "with_loft_areas": new, "areas_stage1_ft2": stage1, "areas_loft_ft2": loft,
            "areas_stage1_rebuilt_ft2": dict(seen),
            "record_CD0_mission_altitude": d["CD0"]["mission_altitude"],
            "delta_CD0_mission_altitude": new["CD0_mission_altitude"] - base["CD0_mission_altitude"],
            "delta_CD0_relative": new["CD0_mission_altitude"] / base["CD0_mission_altitude"] - 1.0,
            "delta_hours": new["hours_on_station"] - base["hours_on_station"]}


# ---- nose packaging (addition 2, decision PD-19) ----------------------------------------------------------
def moved_masses(d, g4):
    """Every mass whose station the arrangement changes, for P4. The centre-of-gravity shifts are the moment
    change over the record's weights; P4 recomputes the balance."""
    st, comp = d["stations"], d["components_lb"]
    rows = [{"item": "payload", "weight_lb": d["payload_lb"], "station_r0_ft": st["payload"]["x"],
             "station_p3_ft": g4["payload_bay"]["centroid_x_ft"],
             "note": "volume centre of the two payload-bay boxes; the turret's share of the 500 lb is not known and is not split off"},
            {"item": "avionics", "weight_lb": comp["avionics"], "station_r0_ft": st["avionics"]["x"],
             "station_p3_ft": g4["avionics_bay"]["centroid_x_ft"], "note": "centre of the avionics box"}]
    for r in rows:
        r["shift_ft"] = r["station_p3_ft"] - r["station_r0_ft"]
        r["moment_change_lb_ft"] = r["weight_lb"] * r["shift_ft"]
    dM = sum(r["moment_change_lb_ft"] for r in rows)
    zfw = d["W0_lb"] - d["fuel_lb"]
    mac = d["wing"]["mac"]
    legs = g4["legs"]
    gear = [{"item": "nose gear", "weight_lb": comp["nose_gear"], "station_gear_down_ft": st["nose_gear"]["x"],
             "leg_mid_point_gear_up_ft": 0.5 * (legs["nose"]["pivot_x"] + legs["nose"]["stowed_axle_x"]),
             "stowed_axle_ft": legs["nose"]["stowed_axle_x"], "retracts": "aft"},
            {"item": "main gear", "weight_lb": comp["main_gear"], "station_gear_down_ft": st["main_gear"]["x"],
             "leg_mid_point_gear_up_ft": 0.5 * (legs["main_left"]["pivot_x"] + legs["main_left"]["stowed_axle_x"]),
             "stowed_axle_ft": legs["main_left"]["stowed_axle_x"], "retracts": "forward"}]
    return {"moved": rows, "moment_change_lb_ft": dM,
            "cg_shift_takeoff_weight_ft": dM / d["W0_lb"], "cg_shift_zero_fuel_weight_ft": dM / zfw,
            "cg_shift_takeoff_weight_mac": dM / d["W0_lb"] / mac, "cg_shift_zero_fuel_weight_mac": dM / zfw / mac,
            "static_margin_r0": {"full": d["layout"]["sm_full"], "empty": d["layout"]["sm_empty"]},
            "static_margin_with_shift_stage1_neutral_point": {"full": d["layout"]["sm_full"] - dM / d["W0_lb"] / mac,
                                                              "empty": d["layout"]["sm_empty"] - dM / zfw / mac},
            "gear_up_and_down": gear, "not_moved": "every other station of r0 (engine, nose gear down, main gear down, systems, wing, tails, fuel)"}


def sponson_need(m, g4):
    """What the retracted main gear asks of a sponson, from its three boxes: the length from the front of the
    wheel box to the back of the leg box, and the depth of the wheel box, each plus two clearances, against the
    record's sponson; in main-tyre diameters, the unit of the ledger's two sponson entries."""
    b = g4["boxes"]
    c = g4["clearance_required_in"] / 12.0
    need_len = b["main_gear_left_leg_1"]["hi"][0] - b["main_gear_left_wheel"]["lo"][0] + 2 * c
    need_depth = b["main_gear_left_wheel"]["hi"][2] - b["main_gear_left_wheel"]["lo"][2] + 2 * c
    tyre = m["tyre_main"]["diameter"]
    sp = m["sponson_left"]
    return {"length_needed_ft": need_len, "length_r0_ft": 2 * sp.a, "depth_needed_ft": need_depth, "depth_r0_ft": 2 * sp.c,
            "length_needed_per_tyre": need_len / tyre, "depth_needed_per_tyre": need_depth / tyre,
            "note": "a box-shaped least size; a body with curved ends needs more"}


# ---- the run -------------------------------------------------------------------------------------------------
def vsp_input(m, n_sections=40):
    f = m["fuselage"]
    surf = [dict(name=n, code=s.code, x_le=s.x_le, z0=s.z0, half_span=s.half_span, c_root=s.c_root, c_tip=s.c_tip,
                 le_slope=s.le_slope, vertical=s.vertical) for n, s in ((k, m[k]) for k in ("wing", "horizontal_tail", "vertical_tail"))]
    ell = [dict(name=n, centre=m[n].centre.tolist(), a=m[n].a, b=m[n].b, c=m[n].c)
           for n in ("sponson_left", "sponson_right", "turret", "spinner")]
    return {"fuselage": {"length": f.length, "sections": [{"x": float(r[0, 0]), "yz": r[:, 1:].tolist()} for r in f.rings(n_sections, 9)]},
            "surfaces": surf, "ellipsoids": ell}


def run_openvsp(m, out, python):
    """Gate 8's OpenVSP numbers, or the reason there are none (decision PD-14)."""
    if not python:
        return "no OpenVSP interpreter was given (--openvsp-python)"
    folder = out / "openvsp"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "input.json").write_text(json.dumps(vsp_input(m)))
    try:
        r = subprocess.run([python, "-m", "geometry3d.openvsp_check", str(folder / "input.json"), str(folder)],
                           capture_output=True, text=True, cwd=REPO, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"the OpenVSP interpreter could not be run: {e}"
    if r.returncode != 0 or not (folder / "openvsp_check.json").exists():
        return "the OpenVSP check failed: " + (r.stderr.strip().splitlines() or ["no message"])[-1]
    return load(folder / "openvsp_check.json")


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
    g = res["gates"]
    names = {"1": "every component watertight, normals outward", "2": "printed targets: conic cases of Raymer (7.4); mean chord and its station against r0",
             "3": "wetted area per component against the area Stage 1's build-up uses, within 5 %",
             "4": "volumes: tanks, boxes inside the skin with clearance, no two boxes overlapping, payload bay",
             "5": "smoothness of section perimeter and area along the fuselage; aft-body angle reported",
             "6": "ground angles on the loft: propeller clearance at rotation, tipback, overturn",
             "7": "export round trip: area and volume of the re-read STL", "8": "OpenVSP CompGeom wetted areas, within 2 %",
             "9": "added: no part of the airframe behind the propeller plane inside the disc",
             "10": "added: wetted areas with the surface mesh doubled and doubled again (reported)"}
    return [{"row": int(k), "what": names[k], "verdict": g[k]["verdict"],
             "failing": g[k].get("failing"), "reason": g[k].get("reason")} for k in names]


def findings(res):
    """The findings for r1 (PD-7), each with its numbers from this record."""
    g, d = res["gates"], res["r0"]
    out = []
    c3 = g["3"]["components"]
    for k in g["3"]["failing"]:
        out.append(f"Wetted area, {k.replace('_', ' ')}: loft {c3[k]['loft_wetted_ft2']:.2f} ft^2 against Stage 1's "
                   f"{c3[k]['stage1_ft2']:.2f} ft^2 ({100 * c3[k]['loft_over_stage1']:+.1f} %), outside 5 %.")
    if res.get("buildup"):
        b = res["buildup"]
        out.append(f"Build-up with the loft's five areas: CD0 at the mission altitude {b['as_recorded']['CD0_mission_altitude']:.5f} "
                   f"to {b['with_loft_areas']['CD0_mission_altitude']:.5f} ({100 * b['delta_CD0_relative']:+.2f} %); hours on station "
                   f"{b['as_recorded']['hours_on_station']:.2f} to {b['with_loft_areas']['hours_on_station']:.2f} h "
                   f"({b['delta_hours']:+.2f} h) at r0's weight and fuel. The loft's areas go into r1.")
    mv = res["moved_masses"]
    for r in mv["moved"]:
        out.append(f"Nose packaging (PD-19): {r['item']} {r['weight_lb']:.2f} lb from {r['station_r0_ft']:.3f} ft to "
                   f"{r['station_p3_ft']:.3f} ft ({r['shift_ft']:+.3f} ft, {r['moment_change_lb_ft']:+.0f} lb ft).")
    out.append(f"Together {mv['moment_change_lb_ft']:+.0f} lb ft: centre of gravity {mv['cg_shift_takeoff_weight_ft']:+.3f} ft "
               f"({mv['cg_shift_takeoff_weight_mac']:+.4f} MAC) at take-off weight and {mv['cg_shift_zero_fuel_weight_ft']:+.3f} ft "
               f"({mv['cg_shift_zero_fuel_weight_mac']:+.4f} MAC) at zero-fuel weight; with Stage 1's neutral point the static margin "
               f"would be {mv['static_margin_with_shift_stage1_neutral_point']['full']:.4f} full and "
               f"{mv['static_margin_with_shift_stage1_neutral_point']['empty']:.4f} empty (R13: 0.05 to 0.15). P4 recomputes and moves the wing if needed.")
    sp = res["sponson_need"]
    bad = [f for f in g["4"]["failing"] if "main_gear" in f]
    if bad:
        out.append(f"The retracted main gear does not fit the sponson ({'; '.join(bad)}): the leg from pivot to axle is "
                   f"{g['4']['legs']['main_left']['leg_ft']:.2f} ft and its boxes need {sp['length_needed_ft']:.2f} ft by "
                   f"{sp['depth_needed_ft']:.2f} ft deep against the sponson's {sp['length_r0_ft']:.2f} ft by {sp['depth_r0_ft']:.2f} ft "
                   f"({sp['length_needed_per_tyre']:.2f} and {sp['depth_needed_per_tyre']:.2f} tyre diameters; ledger 3.6 and 1.2).")
    for k, v in g["9"]["failing"].items():
        out.append(f"The {k.replace('_', ' ')} reaches {v:.2f} ft behind the propeller plane inside the disc "
                   f"(plane at {g['9']['propeller_plane_x_ft']:.2f} ft, disc radius {g['9']['disc_radius_ft']:.2f} ft): the tail and "
                   "the pusher propeller of r0's layout occupy the same space.")
    a = g["5"]["aft_body_angle_deg"]
    out.append(f"Aft-body angle of the loft: {max(a.values()):.1f} deg (top and bottom), {a['side']:.1f} deg (side), against Raymer's "
               f"10 to 12 deg and about 30 deg ahead of a pusher propeller; the engine envelope at r0's engine station sets it.")
    t = g["4"]["tank"]
    out.append(f"Wing tanks on the loft: {t['usable_ft3']:.2f} ft^3 usable against Stage 1's claim of {t['stage1_claim_ft3']:.2f} ft^3 "
               f"({100 * t['usable_over_claim']:+.1f} %) and {t['needed_ft3']:.2f} ft^3 needed.")
    if g["8"]["verdict"] == "fail":
        out.append("OpenVSP cross-check outside 2 % for: " + ", ".join(g["8"]["failing"]) + " (no size changes; see the report).")
    return out


def run(out, log, openvsp_python=None):
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P3 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "arrangement": ARRANGEMENT,
             "tail_section_source": TAIL_SOURCE}
    d, L, A = inputs()
    res = {"inputs": dict(tree, command="python -m prelim.p3_loft " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P3", python=platform.python_version(),
                          numpy=np.__version__, scipy=scipy.__version__, pyyaml=yaml.__version__, matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()},
                          sha256={k: sha256(p) for k, p in files.items()}),
           "evidence_class": EVIDENCE_CLASS, "baseline": str(R0.relative_to(REPO)),
           "arrangement": A, "tail_source": yaml.safe_load(TAIL_SOURCE.read_text()),
           "r0": {"W0_lb": d["W0_lb"], "fuel_lb": d["fuel_lb"], "wing": d["wing"], "fuselage": d["fuselage"],
                  "stations": d["stations"], "layout_x": {k: d["layout"][k] for k in ("x_le", "x_main", "cg_full", "cg_empty", "x_np")}}}
    log(f"commit {tree['commit']}, clean tree")
    m = ac.build(d, L, A)
    parts = ac.meshes(m)
    res["loft"] = {"fuselage_stations_ft": m["fuselage"].stations.tolist(), "spinner_radius_ft": m["spinner_radius"],
                   "ground_z_ft": m["ground_z"], "propeller": m["propeller"], "tyre_main_ft": m["tyre_main"], "tyre_nose_ft": m["tyre_nose"],
                   "sections": {"wing": ac.WING_SECTION, "tails": ac.TAIL_SECTION},
                   "surfaces": {k: {q: getattr(m[k], q) for q in ("x_le", "z0", "half_span", "c_root", "c_tip", "le_slope", "vertical")}
                                for k in ("wing", "horizontal_tail", "vertical_tail")},
                   "ellipsoids": {k: {"centre": m[k].centre.tolist(), "a": m[k].a, "b": m[k].b, "c": m[k].c}
                                  for k in ("sponson_left", "sponson_right", "turret", "spinner")}}
    g = {"1": gates.gate1_watertight(parts), "2": gates.gate2_targets(m, d), "3": gates.gate3_wetted(m, parts, d, L),
         "4": gates.gate4_volumes(m, parts, d, L, A), "5": gates.gate5_smoothness(m), "6": gates.gate6_ground(m, parts, d, L),
         "7": gates.gate7_round_trip(parts, out / "loft.stl")}
    res["stl"] = {"file": "loft.stl", "sha256": sha256(out / "loft.stl"), "bytes": (out / "loft.stl").stat().st_size}
    for k in "1234567":
        log(f"gate {k}: {g[k]['verdict']}" + (f" ({g[k]['failing']})" if g[k].get("failing") else ""))
    vsp = run_openvsp(m, out, openvsp_python)
    g["8"] = gates.gate8_openvsp(g["3"]["components"], vsp)
    res["openvsp_python"] = openvsp_python
    log(f"gate 8: {g['8']['verdict']}" + (f" ({g['8'].get('reason') or g['8'].get('failing')})"))
    g["9"] = gates.row9_propeller_disc(m, parts)
    conv = {"1": {k: v["loft_wetted_ft2"] for k, v in g["3"]["components"].items()}}
    for fine in (2, 4):
        conv[str(fine)] = {k: v["wetted_ft2"] for k, v in ac.wetted_areas(m, ac.meshes(m, fine))[1].items()}
    s1 = gates.stage1_areas(d, L)
    g["10"] = {"wetted_ft2_by_mesh_factor": conv, "verdict": "reported",
               "largest_change_1_to_4": max(abs(conv["4"][k] / conv["1"][k] - 1.0) for k in conv["1"]),
               "gate3_verdicts_on_finest": {k: ("pass" if abs(conv["4"][k] / s1[k] - 1.0) <= gates.TOL_WETTED else "fail") for k in s1}}
    log(f"row 9: {g['9']['verdict']}; row 10: largest change of a wetted area from the base mesh to four times finer "
        f"{100 * g['10']['largest_change_1_to_4']:.2f} %")
    res["gates"] = g
    res["buildup"] = None
    if g["3"]["verdict"] == "fail":
        res["buildup"] = buildup_with_loft_areas(d, g["3"]["components"])
        b = res["buildup"]
        log(f"build-up with the loft's areas: CD0 {b['as_recorded']['CD0_mission_altitude']:.6f} -> {b['with_loft_areas']['CD0_mission_altitude']:.6f}, "
            f"hours {b['as_recorded']['hours_on_station']:.3f} -> {b['with_loft_areas']['hours_on_station']:.3f}")
    res["moved_masses"] = moved_masses(d, g["4"])
    res["sponson_need"] = sponson_need(m, g["4"])
    res["tail_section"] = tail_section(d, L)
    res["acceptance"] = acceptance_rows(res)
    res["findings_for_r1"] = findings(res)
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == tree["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p3.json").write_text(json.dumps(_plain(res), indent=1))
    log(", ".join(f"row {a['row']} {a['verdict']}" for a in res["acceptance"]) + f" ({time.time() - t0:.0f} s)")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--openvsp-python", help="a python that has the OpenVSP API; without it gate 8 is recorded 'not run'")
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the renders (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and renders from OUT/p3.json and OUT/loft.stl")
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
        from prelim import p3_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p3_report.write_figures(out, figures)
        report.write_text(p3_report.report_text(out))


if __name__ == "__main__":
    main()

"""Preliminary design package P6: the blade-element propeller
(docs/specs/task12_preliminary_design.md, "P6. Blade-element propeller"; decision PD-10).

    python -m prelim.p6_propeller --out runs/task12/pd/2026-11-27/p6
    python -m prelim.p6_propeller --out runs/task12/pd/2026-11-27/p6 --report-only \
        --report docs/validation/2026-11-27_task12_pd_p6.md

r0 is read, never written. What is run here:
 1. validation rows 1 to 4: Mattingly App. L targets (prelim/bem.py holds the relations);
 2. validation row 5: the three-blade Navy propeller 5868-9 of NACA Report 640, modelled from its blade-form curves
    with the measured sections of NACA Report 259, against its measured efficiency at 15 and 25 deg;
 3. the representative aircraft propeller (data/task12/pd_p6_blade_ledger.yaml) at r0's propeller points and at the
    take-off speeds of the recorded f sweep; the factor f it implies; tip Mach numbers; sensitivities.
If row 5 fails, everything in 3 is a failed-validation number and is not used in r1 (spec P6).

Output: OUT/p6.json, OUT/run.log. Units are foot, pound, second and degrees.
"""
import argparse
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import yaml

from conceptual import raymer_propulsion as prop
from conceptual import uav
from conceptual.units import KT, RHO0, isa
from prelim import bem
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
R0 = REPO / "runs/task12/pd/2026-11-27/p0/r0"
SWEEP = REPO / "runs/task12/stage3/2026-11-27/takeoff_f_sweep_ws13a8/sweep.json"
SOURCE = REPO / "data/task12/pd_p6_propeller_source.yaml"
SECTIONS = REPO / "data/task12/pd_p6_tr259_sections.yaml"
BLADE_LEDGER = REPO / "data/task12/pd_p6_blade_ledger.yaml"
EVIDENCE_CLASS = ("independent of App. L's disk in the profile losses; it shares the momentum theory (spec P6). The section "
                  "data and the validation propeller are measured open data (NACA Reports 259 and 640)")

# tolerances and bands, fixed before the run (spec P6; the ones the spec leaves open are fixed here)
TOL_ROW5 = 0.03                    # validation row 5: efficiency, absolute
ETA_RANGE_MIN = 0.5                # ... where the measured efficiency is above this
ROW5_ANGLES = (15, 25)             # the two blade angles at 0.75R; they bracket the angles the aircraft blade runs at
JUDGED_READING_UNCERTAINTY = 0.015  # a measured point is judged only if it was read at least this well
TOL_FIG_L5 = 0.01                  # row 2: the reading uncertainty of Fig. L.5
TOL_TABLE_L1_REL = 0.01            # row 3: 1 % plus half a unit of the last printed digit (0.005)
TOL_L19_FT = 0.05                  # row 4: the example prints the diameters to 0.1 ft
TOL_ETA_AIRCRAFT = 0.05            # aircraft row 1 (spec 7.1a)
F_BAND = (0.80, 0.90)              # aircraft row 2: the ledger band of prop_real_to_ideal
TAKEOFF_F = 0.6                    # aircraft row 3: the lowest f of the recorded sweep, where R7 was shown to hold
STATION_STEP = 0.0125              # blade stations every 1/80 of the radius, the last one at 0.9875
READ_FLOOR = {"b_over_D": 0.00015, "h_over_b": 0.0006, "pitch": 0.003, "eta": 0.004}
TABLE_L1 = [   # Mattingly Table L.1, p. 619 (D = 14 ft, N = 663.4 rpm): label, M_0, altitude (ft), power (hp), J, C_P as printed
    ("A", 0.088, 0.0, 2387.0, 0.60, 1.50), ("B", 0.529, 0.0, 2259.0, 3.88, 1.38),
    ("C", 0.454, 0.0, 1411.0, 3.30, 0.85), ("E", 0.2, 10000.0, 218.0, 1.45, 0.18)]      # row D is flagged in the notes, not used
TABLE_L1_D_FT, TABLE_L1_RPM = 14.0, 663.4
SENSITIVITY_J = np.round(np.arange(0.2, 1.3501, 0.025), 3)


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- the committed data

def reading(row, floor):
    """(value, uncertainty) of one row [station, reading 1, reading 2, reading 3] of the source record: the mean of the
    first reading and the second (the third where the second is missing; the second and third where the first is),
    and half their difference, at least `floor`."""
    first, second = (row[1], row[2] if row[2] is not None else row[3]) if row[1] is not None else (row[2], row[3])
    return (first + second) / 2.0, max(abs(first - second) / 2.0, floor)


def blade_5868_9():
    """The blade of the Navy propeller 5868-9 as read from NACA Report 640 Fig. 2: stations x = r/R, chord/D, thickness
    ratio (None where it is above the plot, inboard of 0.35) and the blade angle with the blade set 25 deg at 0.75R."""
    g = yaml.safe_load(SOURCE.read_text())["blade_geometry"]
    x = [r[0] for r in g["b_over_D"]]
    thick = {r[0]: reading(r, READ_FLOOR["h_over_b"])[0] for r in g["h_over_b"]}
    pitch = [reading(r, READ_FLOOR["pitch"])[0] for r in g["pitch_set_25"]]
    return {"x": x, "c_over_D": [reading(r, READ_FLOOR["b_over_D"])[0] for r in g["b_over_D"]],
            "t_c": [thick.get(xi) for xi in x],
            "beta_set25_deg": [math.degrees(math.atan(p / (math.pi * xi))) for p, xi in zip(pitch, x)]}


def stations(blade, hub):
    """The blade on stations every STATION_STEP from the hub to 0.9875. Chord and blade angle are interpolated linearly
    between the read stations and continued along the last two readings beyond 0.95 (the plot ends there). The
    thickness ratio is interpolated where it was read, held beyond the last reading, and None inboard of the first."""
    x = np.round(np.arange(hub, 0.99, STATION_STEP), 6)
    xs = np.array(blade["x"])

    def line(values):
        v = np.array(values, float)
        out = np.interp(x, xs, v)
        beyond = x > xs[-1]
        out[beyond] = v[-1] + (v[-1] - v[-2]) / (xs[-1] - xs[-2]) * (x[beyond] - xs[-1])
        return out

    tx = [xi for xi, t in zip(blade["x"], blade["t_c"]) if t is not None]
    tv = [t for t in blade["t_c"] if t is not None]
    t_c = [None if xi < tx[0] else float(np.interp(xi, tx, tv)) for xi in x]
    return {"x": x, "c_over_D": line(blade["c_over_D"]), "beta_set25_deg": line(blade["beta_set25_deg"]), "t_c": t_c}


def measured_efficiency(angle):
    """The measured efficiency points of NACA Report 640 Fig. 12 at this blade angle, each with its reading uncertainty
    and whether it is judged in row 5."""
    out = []
    for row in yaml.safe_load(SOURCE.read_text())["efficiency"][f"blade_angle_{angle}"]:
        eta, unc = reading([row[0], row[1], row[2], None], READ_FLOOR["eta"])
        out.append({"J": row[0], "eta": eta, "uncertainty": unc, "reading_code": row[1], "reading_eye": row[2],
                    "judged": unc <= JUDGED_READING_UNCERTAINTY})
    return out


def load_sections(span_factor):
    """The six sections of NACA Report 259 as data of infinite span (bem.infinite_span with the report's aspect ratio)."""
    d = yaml.safe_load(SECTIONS.read_text())
    tables = []
    for s in d["sections"]:
        pts = [bem.infinite_span(a, cl, cd, d["aspect_ratio"], span_factor) + (cl,) for a, cl, cd, _ in s["rows"]]
        tables.append({"t_c": s["thickness_ratio"], "name": s["name"], "reynolds": s["reynolds"],
                       "alpha": [p[0] for p in pts], "cl": [p[2] for p in pts], "cd": [p[1] for p in pts]})
    return bem.Sections(tables)


def blade_ledger():
    """The blade choices as {name: value}."""
    return {k: v["value"] for k, v in yaml.safe_load(BLADE_LEDGER.read_text())["entries"].items()}


def blade_bands():
    return {k: v["band"] for k, v in yaml.safe_load(BLADE_LEDGER.read_text())["entries"].items() if "band" in v}


def aircraft_blade(L):
    """The representative blade: the planform of 5868-9 scaled by one factor to the ledger's activity factor (Raymer
    (13.14), taken over these stations), its thickness ratio times the ledger's factor. The twist is set in aircraft()."""
    b = stations(blade_5868_9(), L["prop_hub_fraction"])
    scale = L["prop_activity_factor"] / bem.activity_factor(b["x"], b["c_over_D"])
    return {"x": b["x"], "c_over_D": b["c_over_D"] * scale, "chord_scale": scale,
            "t_c": [None if t is None else t * L["prop_thickness_scale"] for t in b["t_c"]]}


# ---------------------------------------------------------------- r0

def operating_points():
    """r0's propeller points with what the strip theory needs: speed, shaft power, rpm, diameter, density, speed of sound.
    The climb point is at sea level, the others at the mission altitude (r0's ledger)."""
    d, L = load(R0 / "design_pusher.json"), uav.load_ledger(R0 / "ledger.yaml")[0]
    out = {}
    for name, pt in d["propeller_points"].items():
        atm = isa(0.0 if name == "climb_sea_level" else L["mission_altitude_ft"])
        out[name] = {"V_fps": pt["V_kt"] * KT, "shaft_hp": pt["shaft_hp"], "rpm": L["propeller_rpm"],
                     "D_ft": d["propeller_diameter_ft"], "rho": atm["rho"], "sigma": atm["sigma"], "a_sound": atm["a"],
                     "altitude_ft": 0.0 if name == "climb_sea_level" else L["mission_altitude_ft"],
                     "eta_record": pt["eta_p"], "J_record": pt["J"], "CP_record": pt["C_P"]}
    return out


def record_targets():
    """What the aircraft rows are judged against, all from committed records."""
    d, L, sweep = load(R0 / "design_pusher.json"), uav.load_ledger(R0 / "ledger.yaml")[0], load(SWEEP)
    row = next(r for r in sweep["sweep"] if r["f"] == TAKEOFF_F)
    return {"eta": {k: d["propeller_points"][k]["eta_p"] for k in ("climb_sea_level", "cruise_out", "loiter")},
            "takeoff_f": TAKEOFF_F, "takeoff_thrust_min_lb": row["thrust_0707_VTO_lb"],
            "takeoff_speed_fps": row["speed_at_0707_VTO_ft_s"], "takeoff_static_thrust_f060_lb": row["thrust_static_lb"],
            "takeoff_record_f": sweep["record_f"],
            "takeoff_thrust_record_lb": next(r for r in sweep["sweep"] if r["f"] == sweep["record_f"])["thrust_0707_VTO_lb"],
            "takeoff_static_thrust_record_lb": next(r for r in sweep["sweep"] if r["f"] == sweep["record_f"])["thrust_static_lb"],
            "takeoff_bhp": sweep["bhp"], "diameter_ft": d["propeller_diameter_ft"], "rpm": L["propeller_rpm"],
            "f_ledger": L["prop_real_to_ideal"], "static_ct_over_cp": L["static_ct_over_cp"]}


# ---------------------------------------------------------------- validation rows 1 to 5

def validation_row_1():
    """Largest relative difference between (L.14) without drag and swirl and (L.7), over a grid."""
    worst = 0.0
    for ratio in np.linspace(1.0, 4.0, 31):
        for phi_deg in np.linspace(1.0, 89.0, 45):
            e = bem.element_efficiency(bem.axial_interference_of_disk(ratio), 0.0, math.radians(phi_deg), 0.0)
            worst = max(worst, abs(e / bem.ideal_efficiency(ratio) - 1.0))
    return {"row": 1, "what": "element efficiency with zero drag angle, zero rotational interference and the disk's axial "
            "interference equals the ideal efficiency ((L.14), (L.5), (L.7))", "largest_relative_difference": worst,
            "tolerance": 1e-12, "verdict": "pass" if worst <= 1e-12 else "fail"}


def validation_row_2():
    """(L.15) for an interference ratio of 0.8 against the plateau read from Fig. L.5, p. 616."""
    fig = yaml.safe_load(SOURCE.read_text())["library_figure"]
    curves = []
    for c in fig["plateau"]:
        gamma = math.atan(1.0 / c["lift_to_drag"])
        mean = (c["reading_eye"] + c["reading_pixel"]) / 2.0
        computed = bem.element_efficiency_max(0.25, 0.0, gamma)
        curves.append({"lift_to_drag": c["lift_to_drag"], "computed": computed, "reading_mean": mean,
                       "reading_eye": c["reading_eye"], "reading_pixel": c["reading_pixel"],
                       "phi_at_maximum_deg": 45.0 - math.degrees(gamma) / 2.0, "ok": abs(computed - mean) <= TOL_FIG_L5})
    return {"row": 2, "what": "maximum of the element efficiency, (L.15), against the plateau of Fig. L.5 for an interference "
            "ratio of 0.8", "curves": curves, "tolerance": TOL_FIG_L5, "verdict": "pass" if all(c["ok"] for c in curves) else "fail"}


def validation_row_3():
    """(L.18) and (L.20) from the flight conditions of Table L.1, p. 619, against its printed J and C_P."""
    rows = []
    for label, mach, alt, hp, j_print, cp_print in TABLE_L1:
        atm = isa(alt)
        j = bem.advance_ratio_l20(mach * atm["a"], TABLE_L1_RPM, TABLE_L1_D_FT)
        cp = bem.power_coefficient_l18(hp, atm["sigma"], TABLE_L1_RPM, TABLE_L1_D_FT)
        rows.append({"label": label, "mach": mach, "altitude_ft": alt, "hp": hp, "J_printed": j_print, "J_computed": j,
                     "CP_printed": cp_print, "CP_computed": cp, "J_ratio": j / j_print, "CP_ratio": cp / cp_print,
                     "J_ok": abs(j - j_print) <= 0.005 + TOL_TABLE_L1_REL * j_print,
                     "CP_ok": abs(cp - cp_print) <= 0.005 + TOL_TABLE_L1_REL * cp_print})
    return {"row": 3, "what": "(L.18) and (L.20) reproduce the J and C_P of Table L.1 from its flight conditions (row D not used)",
            "rows": rows, "tolerance": "1 % plus half a unit of the last printed digit",
            "verdict": "pass" if all(r["J_ok"] and r["CP_ok"] for r in rows) else "fail"}


def validation_row_4():
    """(L.19) and the two printed diameters of the example on p. 617."""
    cases = [{"thrust_lbf": 15000.0, "hp": 4000.0, "blades": 4, "printed_ft": 15.0},
             {"thrust_lbf": 7500.0, "hp": 2000.0, "blades": 4, "printed_ft": 10.6}]
    for c in cases:
        c["computed_ft"] = bem.static_diameter_l19(c["thrust_lbf"], 1.0, c["hp"], c["blades"])
        c["ok"] = abs(c["computed_ft"] - c["printed_ft"]) <= TOL_L19_FT
    return {"row": 4, "what": "static-thrust correlation (L.19) reproduces the two printed diameters of the example",
            "cases": cases, "tolerance_ft": TOL_L19_FT, "verdict": "pass" if all(c["ok"] for c in cases) else "fail"}


def summary(result):
    """What is kept of one propeller run: the totals, and of the stations the numbers the report quotes."""
    st = result["stations"]
    outside = [s for s in st if s["outside_deg"] != 0.0]
    at = min(st, key=lambda s: abs(s["x"] - 0.75))
    keep = {k: result[k] for k in ("V_fps", "rpm", "J", "thrust_lb", "power_hp", "C_T", "C_P", "eta")}
    keep.update({"pitch_change_deg": result.get("pitch_change_deg"), "tip_station_mach": st[-1]["mach"],
                 "mach_at_075R": at["mach"], "cl_at_075R": at["cl"], "alpha_at_075R_deg": at["alpha_deg"],
                 "cl_min": min(s["cl"] for s in st), "cl_max": max(s["cl"] for s in st),
                 "stations_outside_data": len(outside), "n_stations": len(st),
                 "outermost_station_outside_data": max((s["x"] for s in outside), default=None),
                 "largest_excess_deg": max((abs(s["outside_deg"]) for s in outside), default=0.0),
                 "x": [s["x"] for s in st], "cl": [s["cl"] for s in st], "mach": [s["mach"] for s in st],
                 "dT_dr": [s["dT_dr"] for s in st]})
    return keep


def run_5868_9(angle, J, sections, hub=0.2, prandtl_glauert=False):
    """The 10 ft three-blade propeller 5868-9 set `angle` deg at 0.75R, at advance ratio J and the test's rpm, sea-level
    air. Returns the summary, or {"error": ...} if a station has no solution."""
    test = yaml.safe_load(SOURCE.read_text())["tr640_test"]
    blade = stations(blade_5868_9(), hub)
    rpm, D, atm = test["rpm_schedule_3_blades"][angle], test["diameter_ft"], isa(0.0)
    try:
        r = bem.propeller(J * rpm / 60.0 * D, rpm, D, test["blades"], atm["rho"], atm["a"], blade["x"], blade["c_over_D"],
                          blade["beta_set25_deg"] + (angle - 25.0), blade["t_c"], sections.section(prandtl_glauert))
    except ValueError as err:
        return {"error": str(err)}
    return summary(r)


def row5_points(sections, **kw):
    """Measured points of both blade angles with the computed efficiency beside each (None if not computed)."""
    out = {}
    for angle in ROW5_ANGLES:
        pts = measured_efficiency(angle)
        for p in pts:
            r = run_5868_9(angle, p["J"], sections, **kw)
            p["computed"] = r.get("eta")
            p["difference"] = None if p["computed"] is None else p["computed"] - p["eta"]
            p["run"] = {k: v for k, v in r.items() if not isinstance(v, list)}
        out[angle] = pts
    return out


def row5_verdict(points):
    """Pass if at every judged point the computed efficiency is within TOL_ROW5 of the measured one. A judged point the
    model could not compute fails the row."""
    judged = [p for pts in points.values() for p in pts if p["judged"]]
    missing = [p for p in judged if p["computed"] is None]
    diffs = [abs(p["computed"] - p["eta"]) for p in judged if p["computed"] is not None]
    ok = not missing and max(diffs) <= TOL_ROW5
    return {"row": 5, "what": "measured full propeller (NACA Report 640, propeller 5868-9, 3 blades): efficiency against "
            "advance ratio at 15 and 25 deg where the measured efficiency is above 0.5",
            "n_judged": len(judged), "n_not_computed": len(missing), "n_inside": sum(d <= TOL_ROW5 for d in diffs),
            "largest_difference": max(diffs) if diffs else None, "tolerance": TOL_ROW5, "verdict": "pass" if ok else "fail"}


def used_in_r1(row5):
    """Spec P6: if row 5 fails, the package's numbers are failed-validation numbers and are not used in r1."""
    return row5 == "pass"


# ---------------------------------------------------------------- the aircraft propeller

def verdict_eta(eta, record):
    return "pass" if abs(eta - record) <= TOL_ETA_AIRCRAFT else "outside"


def verdict_f(f):
    if f < F_BAND[0]:
        return "finding: below the band"
    return "finding: above the band" if f > F_BAND[1] else "inside the band"


def verdict_takeoff(thrust, minimum):
    return "pass" if thrust >= minimum else "fail"


def row2_verdict(points):
    """Aircraft row 2 from its points: a finding if f is outside the band anywhere; points that could not be computed
    are named and are not counted as inside or outside."""
    outside = [p["point"] for p in points if p["verdict"].startswith("finding")]
    missing = [p["point"] for p in points if p["verdict"] == "not computed"]
    text = "finding: outside the band at " + ", ".join(outside) if outside else "inside the band at every computed point"
    return text + ("; not computed at " + ", ".join(missing) if missing else "")


def aircraft(L, sections, prandtl_glauert=False, points=None):
    """The representative propeller at r0's points: twist from the design lift coefficient at the loiter point, then at
    each point the pitch that absorbs the record's shaft power (constant speed). Returns the blade and one entry per
    point with the efficiency, the ideal efficiency of the same disk at the same thrust and their ratio f."""
    pts, T = points or operating_points(), record_targets()
    blade, section = aircraft_blade(L), sections.section(prandtl_glauert)
    B, lo = L["prop_blades"], (points or operating_points())["loiter"]
    twist = bem.design_twist(L["prop_design_cl"], lo["V_fps"], lo["rpm"], lo["D_ft"], B, lo["rho"], blade["x"],
                             blade["c_over_D"], blade["t_c"], sections)
    i75 = int(np.argmin(np.abs(blade["x"] - 0.75)))
    out = {"blade": {"x": blade["x"], "c_over_D": blade["c_over_D"], "t_c": blade["t_c"], "twist_deg": twist,
                     "chord_scale": blade["chord_scale"], "activity_factor": bem.activity_factor(blade["x"], blade["c_over_D"]),
                     "chord_at_075R_ft": blade["c_over_D"][i75] * lo["D_ft"], "beta_design_at_075R_deg": twist[i75]},
           "points": {}}

    def one(hp, V, rpm, D, rho, a_sound):
        try:
            r = bem.pitch_for_power(hp, V, rpm, D, B, rho, a_sound, blade["x"], blade["c_over_D"], twist, blade["t_c"], section)
        except ValueError as err:
            return {"error": str(err), "pitch_sweep": pitch_sweep(hp, V, rpm, D, rho, a_sound)}
        s = summary(r)
        s["beta_at_075R_deg"] = twist[i75] + r["pitch_change_deg"]
        s["helical_tip_mach"] = math.hypot(V, math.pi * rpm / 60.0 * D) / a_sound
        if V > 0.0:
            s["eta_ideal"] = bem.ideal_efficiency_of_disk(r["thrust_lb"], rho, V, D)
            s["f"] = r["eta"] / s["eta_ideal"]
        s["static_limit_lb"] = prop.static_thrust_limit(hp, rho, D)
        return s

    def pitch_sweep(hp, V, rpm, D, rho, a_sound):
        """Where no pitch absorbs the power: power and thrust against the pitch change, every 2 deg, with the number of
        stations whose angle of attack is beyond the measured section data (their end values are held there)."""
        rows = []
        for delta in np.arange(-10.0, 20.5, 2.0):
            try:
                s = summary(bem.propeller(V, rpm, D, B, rho, a_sound, blade["x"], blade["c_over_D"], twist + delta, blade["t_c"], section))
            except ValueError:
                continue
            rows.append({"pitch_change_deg": float(delta), "beta_at_075R_deg": twist[i75] + delta, "power_hp": s["power_hp"],
                         "thrust_lb": s["thrust_lb"], "stations_outside_data": s["stations_outside_data"],
                         "largest_excess_deg": s["largest_excess_deg"], "cl_at_075R": s["cl_at_075R"]})
        return rows

    for name, p in pts.items():
        out["points"][name] = dict(one(p["shaft_hp"], p["V_fps"], p["rpm"], p["D_ft"], p["rho"], p["a_sound"]),
                                   eta_record=p["eta_record"], altitude_ft=p["altitude_ft"])
    sl = isa(0.0)
    for name, V in (("takeoff_0707_VTO", T["takeoff_speed_fps"]), ("static", 0.0)):
        out["points"][name] = dict(one(T["takeoff_bhp"], V, T["rpm"], T["diameter_ft"], sl["rho"], sl["a"]), altitude_ft=0.0)
    return out


def best_of_sweep(sweep):
    """Of a pitch sweep: the row with the most thrust, and the row with the most thrust among those with every station
    inside the measured section data. None if there is no sweep."""
    if not sweep:
        return None
    inside = [r for r in sweep if r["stations_outside_data"] == 0]
    return {"most_thrust": max(sweep, key=lambda r: r["thrust_lb"]),
            "most_thrust_inside_data": max(inside, key=lambda r: r["thrust_lb"]) if inside else None,
            "most_power_hp": max(r["power_hp"] for r in sweep)}


def sensitivity_cases():
    """The blade choices moved one at a time to their band ends, and the Prandtl-Glauert lift factor switched on."""
    cases = [("baseline", {}, False)]
    for name, band in blade_bands().items():
        for end in band:
            if end != blade_ledger()[name]:
                cases.append((f"{name} = {end:g}", {name: end}, False))
    return cases + [("Prandtl-Glauert factor on the lift", {}, True)]


def acceptance_rows(res):
    """Validation rows 1 to 5 and aircraft rows 1 to 4, each with the numbers its verdict follows from."""
    T, pts, ok = res["targets"], res["aircraft"]["points"], res["used_in_r1"]
    note = None if ok else "failed-validation number (validation row 5 failed): not used in r1"
    rows = [dict(r, group="validation") for r in res["validation"]]
    eta = [{"point": k, "eta": pts[k].get("eta"), "eta_record": T["eta"][k],
            "difference": None if pts[k].get("eta") is None else pts[k]["eta"] - T["eta"][k],
            "verdict": "not computed" if pts[k].get("eta") is None else verdict_eta(pts[k]["eta"], T["eta"][k])} for k in T["eta"]]
    fs = [{"point": k, "f": pts[k].get("f"), "eta": pts[k].get("eta"), "eta_ideal": pts[k].get("eta_ideal"),
           "verdict": "not computed" if pts[k].get("f") is None else verdict_f(pts[k]["f"])}
          for k in ("climb_sea_level", "cruise_out", "loiter", "cruise_back", "takeoff_0707_VTO")]
    to, st = pts["takeoff_0707_VTO"], pts["static"]
    rows += [
        {"group": "aircraft", "row": 1, "what": "efficiency at climb, cruise and loiter against r0's App. L values",
         "points": eta, "tolerance": TOL_ETA_AIRCRAFT, "note": note,
         "verdict": "pass" if all(e["verdict"] == "pass" for e in eta) else "outside at " + ", ".join(e["point"] for e in eta if e["verdict"] != "pass")},
        {"group": "aircraft", "row": 2, "what": "implied factor f (blade-element efficiency over the ideal efficiency of the same disk) "
         "against the ledger band", "points": fs, "band": list(F_BAND), "ledger_value": T["f_ledger"], "note": note,
         "verdict": row2_verdict(fs)},
        {"group": "aircraft", "row": 3, "what": "take-off: thrust at 0.707 V_TO at or above the f = 0.60 row of the recorded sweep",
         "thrust_lb": to.get("thrust_lb"), "minimum_lb": T["takeoff_thrust_min_lb"], "speed_fps": T["takeoff_speed_fps"],
         "static_thrust_lb": st.get("thrust_lb"), "static_error": st.get("error"), "error": to.get("error"), "note": note,
         "sweep_best": best_of_sweep(to.get("pitch_sweep")), "static_sweep_best": best_of_sweep(st.get("pitch_sweep")),
         "power_hp": T["takeoff_bhp"],
         "static_l19_lb": bem.static_thrust_l19(T["diameter_ft"], 1.0, T["takeoff_bhp"], res["blade_ledger"]["prop_blades"]),
         "static_raymer_fig_13_8_lb": prop.static_thrust(T["static_ct_over_cp"], T["takeoff_bhp"], T["rpm"] / 60.0, T["diameter_ft"]),
         "static_momentum_limit_lb": prop.static_thrust_limit(T["takeoff_bhp"], RHO0, T["diameter_ft"]),
         "static_sweep_f060_lb": T["takeoff_static_thrust_f060_lb"], "static_sweep_record_lb": T["takeoff_static_thrust_record_lb"],
         "verdict": "not computed" if to.get("thrust_lb") is None else verdict_takeoff(to["thrust_lb"], T["takeoff_thrust_min_lb"])},
        {"group": "aircraft", "row": 4, "what": "tip relative Mach number at each point and the sensitivity to the blade choices",
         "tip_mach": {k: {"helical": p.get("helical_tip_mach"), "last_station": p.get("tip_station_mach")} for k, p in pts.items()},
         "note": note, "verdict": "reported, no verdict"}]
    return rows


def proposed_bands(res):
    """Aircraft row 2's finding: f per flight condition as the range over the sensitivity cases, widened to 0.01."""
    out = {}
    for k in ("climb_sea_level", "cruise_out", "loiter", "cruise_back", "takeoff_0707_VTO"):
        fs = [c["points"][k]["f"] for c in res["sensitivity"] if c["points"][k].get("f") is not None]
        if fs:
            out[k] = {"f_baseline": res["aircraft"]["points"][k].get("f"), "low": math.floor(min(fs) * 100.0) / 100.0,
                      "high": math.ceil(max(fs) * 100.0) / 100.0, "n_cases": len(fs)}
    return out


def _plain(obj):
    """numpy arrays and scalars to lists and floats, for json."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def run(out, log):
    """The whole package; returns the result dict (also written to OUT/p6.json)."""
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P6 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "takeoff_sweep": SWEEP,
             "source_record": SOURCE, "section_tables": SECTIONS, "blade_ledger": BLADE_LEDGER}
    L = blade_ledger()
    res = {"inputs": dict(tree, command="python -m prelim.p6_propeller " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P6", python=platform.python_version(),
                          numpy=np.__version__, scipy=scipy.__version__, pyyaml=yaml.__version__, matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()},
                          sha256={k: sha256(p) for k, p in files.items()}),
           "evidence_class": EVIDENCE_CLASS, "baseline": str(R0.relative_to(REPO)),
           "source": yaml.safe_load(SOURCE.read_text()), "blade_ledger": L, "blade_bands": blade_bands(),
           "targets": record_targets(), "operating_points": operating_points()}
    log(f"commit {tree['commit']}, clean tree")
    sections = load_sections(L["prop_section_span_factor"])
    res["sections"] = [{k: t[k] for k in ("name", "t_c", "reynolds", "alpha", "cl", "cd")} for t in sections.tables]

    # validation rows 1 to 5
    res["validation"] = [validation_row_1(), validation_row_2(), validation_row_3(), validation_row_4()]
    blade = stations(blade_5868_9(), 0.2)
    res["propeller_5868_9"] = {"read": blade_5868_9(), "stations": blade,
                               "activity_factor": bem.activity_factor(blade["x"], blade["c_over_D"])}
    points = row5_points(sections)
    row5 = row5_verdict(points)
    res["row5_points"] = points
    res["validation"].append(row5)
    res["used_in_r1"] = used_in_r1(row5["verdict"])
    log("validation: " + ", ".join(f"row {r['row']} {r['verdict']}" for r in res["validation"])
        + f"; row 5 largest difference {row5['largest_difference']}")
    res["row5_curves"] = {a: [dict({k: v for k, v in run_5868_9(a, float(J), sections).items() if not isinstance(v, list)}, J=float(J))
                              for J in SENSITIVITY_J] for a in ROW5_ANGLES}
    res["row5_sensitivity"] = []
    for name, sec, kw in (("span factor 0.90", load_sections(0.90), {}), ("span factor 1.00", load_sections(1.0), {}),
                          ("blade starts at 0.3 of the radius", sections, {"hub": 0.3}),
                          ("Prandtl-Glauert factor on the lift", sections, {"prandtl_glauert": True})):
        v = row5_verdict(row5_points(sec, **kw))
        res["row5_sensitivity"].append({"case": name, "largest_difference": v["largest_difference"], "n_inside": v["n_inside"],
                                        "n_judged": v["n_judged"], "n_not_computed": v["n_not_computed"]})
        log(f"row 5 sensitivity, {name}: largest difference {v['largest_difference']}")

    # the aircraft propeller
    res["aircraft"] = aircraft(L, sections)
    for k, p in res["aircraft"]["points"].items():
        log(f"aircraft {k}: " + (p["error"] if "error" in p else f"eta {p['eta']:.4f}, f {p.get('f')}, thrust {p['thrust_lb']:.1f} lb, "
                                 f"beta 0.75R {p['beta_at_075R_deg']:.2f} deg, tip Mach {p['helical_tip_mach']:.3f}"))
    res["sensitivity"] = []
    for name, change, pg in sensitivity_cases():
        Lc = dict(L, **change)
        a = aircraft(Lc, load_sections(Lc["prop_section_span_factor"]), pg)
        res["sensitivity"].append({"case": name, "points": {k: dict({q: p.get(q) for q in ("eta", "f", "thrust_lb", "power_hp", "beta_at_075R_deg",
                                                                                         "stations_outside_data", "error")},
                                                                     sweep_best=best_of_sweep(p.get("pitch_sweep")))
                                                             for k, p in a["points"].items()}})
    res["acceptance"] = acceptance_rows(res)
    res["proposed_f_bands"] = proposed_bands(res)
    _write(out, res, t0, own)
    log(", ".join(f"{a['group']} row {a['row']} {a['verdict']}" for a in res["acceptance"]) + f" ({time.time() - t0:.0f} s)")
    return res


def _write(out, res, t0, own):
    """OUT/p6.json, with the state of the tree at the end of the run next to the one at its start."""
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == res["inputs"]["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p6.json").write_text(json.dumps(_plain(res), indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the figures of the report (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and figures from OUT/p6.json")
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
        run(out, log)
    if a.report:
        from prelim import p6_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p6_report.write_figures(out, figures)
        report.write_text(p6_report.report_text(out))


if __name__ == "__main__":
    main()

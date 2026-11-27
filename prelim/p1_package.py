"""Preliminary design package P1: the Stage 1 package for the baseline record r0
(docs/specs/task12_preliminary_design.md, "P1. Stage 1 package for r0"; ruling B-9a).

    python -m prelim.p1_package --out runs/task12/pd/2026-11-27/p1
    python -m prelim.p1_package --out runs/task12/pd/2026-11-27/p1 --report-only \
        --report docs/validation/2026-11-27_task12_pd_p1.md

r0 is read, never written, and it is not re-sized: the first step sizes W/S 13, A 8 again with the function
that made r0 and stops unless every field equals the record. What is run here, on top of reading r0:
 - the constraint diagram at r0's weight and the compliance rows of the rebuilt design;
 - trades: of the built aircraft (hours on station against payload, altitude and the composite factor) and
   Stage 1's one-at-a-time re-sized trades at W/S 13, A 8 (Gate B report section 9, NR-3);
 - the App. L decomposition on r0 and the climb speed at the worst endurance corner (NR-1, item 18);
 - the tractor and the rubber-engine designs at these sizes and the scoring table (NR-4);
 - the empty-weight comparison component by component (items 8, 27);
 - the band audit with what each unbanded estimate moves (item 28);
 - the payload-bay first check (item 30, PD-12).
The judgements (band audit, out-of-calibration list, risk list) are in data/task12/pd_p1_judgements.yaml;
this module checks them and joins them with the record. Nothing is tuned and no band is applied.

Output: OUT/p1.json, OUT/design_tractor.json, OUT/design_pusher_rubber.json, OUT/pytest.log, OUT/run.log.
Units are foot, pound, second, as in conceptual/.
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
import yaml

from conceptual import raymer_performance as perf
from conceptual import raymer_weights as wts
from conceptual import sizing, stage1, uav
from conceptual.units import KT, isa
from measurement import appl_decomposition as decomposition
from measurement import info_gap
from measurement import robust_sizing as rs
from prelim import p0_baseline as p0
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
R0 = REPO / "runs/task12/pd/2026-11-27/p0/r0"
P0_JSON = REPO / "runs/task12/pd/2026-11-27/p0/p0.json"
CURVE = REPO / "runs/task12/stage3/2026-11-26/m250_bands_resize/curve.json"       # the committed re-size grid
PERF = REPO / "runs/task12/stage3/2026-11-27/m250_ws13a8_measure/perf.json"       # Gate B Stage 3 record
JUDGEMENTS = REPO / "data/task12/pd_p1_judgements.yaml"
W_S, ASPECT = 13.0, 8.0
POWER_HP, H_T = 450.0, 1.05              # the engine's rating and the robust-sizing target of the re-size
# tolerances and inputs fixed before the run (spec P1 "Acceptance"; PD-12; the P0 row-5 threshold)
TOL_WEIGHT_LB = 0.1                      # weight statement against the record's empty weight
TOL_VN = 1e-6                            # V-n points against r0's vn entries
TOL_REPRODUCE = 1e-9                     # the rebuilt design against r0, every field, relative
TOL_CLIMB_FUEL = 0.01                    # integrated against two-point climb, as a share of the mission fuel
PAYLOAD_DENSITY_LB_FT3 = 30.0            # PD-12: low end of Raymer's 30 to 45 lb/ft^3 for avionics, p. 256
R5_NOMINAL_HOURS = 8.0                   # R5: 8 h on station at nominal values
HORIZON_GATE = 1.0                       # spec 7.4: R5 guarantee and R7 horizons at least 1
TYPICAL_WS_GA_SINGLE = 17.0              # Raymer Table 5.5, p. 84: typical W/S, general aviation single engine
HOURS_HI = 30.0                          # upper end of the loiter bisection of the as-built trades
# exponents of the group weight equations (conceptual/raymer_weights.py), for the what-if scalings
EXP_WING_AREA = 0.758                    # (15.46): wing weight ~ S_w^0.758
EXP_HT_AREA = 0.896                      # (15.47): horizontal tail weight ~ S_ht^0.896
EXP_MAIN_GEAR_LENGTH = 0.409             # (15.50): main gear weight ~ L_m^0.409
PACKAGES = tuple(f"P{i}" for i in range(11))
BAND_CLASSES = ("requirement", "definition", "needs a band")
OC_STATUS = ("applies", "applies to the concept record only", "dropped")
# tags of the eight bullets under "Used outside its calibration" in the 2026-11-25 package, in its order
FLAGGED_2026_11_25 = ("Table 3.1 and Table 6.2", "Table 6.3", "Table 3.4", "Table 10.4", "(13.9)", "(12.49)",
                      "Downwash", "Gear and tyre drag")
EVIDENCE_CLASS = "a package, not a measurement"
STAGE1_CLASS = "Stage 1's own value (the independent rows are in the Gate B report, section 2)"
ROBUST_CLASS = "robustness study of the same model (r0/info_gap.json)"


# ---- reading records ---------------------------------------------------------------------------------------
def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lookup(obj, path):
    """The value at a dotted path of a JSON record: "layout.nose_load.full"; a step "rows[id=x]" takes the item
    of the list `rows` whose "id" is x. Raises KeyError if the path does not exist."""
    for step in path.split("."):
        if "[" in step:
            name, cond = step[:-1].split("[")
            key, want = cond.split("=")
            found = [item for item in obj[name] if str(item.get(key)) == want]
            if len(found) != 1:
                raise KeyError(f"{path}: {len(found)} items with {key} = {want}")
            obj = found[0]
        else:
            obj = obj[step]
    return obj


def evidence_files():
    """The records a judgement line may name under `evidence` (the package's own p1.json is added by the report)."""
    return {"r0": load(R0 / "design_pusher.json"), "info_gap": load(R0 / "info_gap.json"),
            "cell": load(R0 / "cell_result.json"), "p0": load(P0_JSON), "perf": load(PERF)}


# ---- r0 sized again: the proof that what is computed here is computed on r0 -----------------------------
def rebuild_r0():
    """W/S 13, A 8 sized again at the record's L_sized by the call that made r0 (measurement/bands_cells.size_cell),
    keeping the Stage 1 analysis, which holds what the record does not store (the exposed wing area, the layout
    state). `reproduction` compares every field of the new design record with r0's."""
    rs.use_engine_as_is(True)
    row = load(R0 / "robust_candidate.json")
    sizing_ledger = dict(rs.ledger_values(), loiter_h=float(row["L_sized_h"]), vc_placard_rule=rs.VC_RULE)
    a, _, rec = rs.sized_aircraft_guess(row["P_hp"], W_S, ASPECT, row["L_sized_h"],
                                        rs.first_guess(row["P_hp"], row["L_sized_h"]), rs.VC_RULE)
    rec = json.loads(json.dumps(rec, default=float))
    d = a["design"]
    raw = stage1.engine_options(stage1.CHOSEN_ENGINE)[1][stage1.CHOSEN_ENGINE]
    rows = stage1.compliance(d, d["ledger_used"], a["layout"], a["performance"], *a["fuel_volume"], raw)
    return {"analysis": a, "record": rec, "row": row, "engine_raw": raw,
            "ledger": uav.load_ledger(R0 / "ledger.yaml")[0],       # the built aircraft's ledger copy (V_C fixed)
            "ledger_sizing": sizing_ledger,                          # the ledger the sizing call starts from
            "reproduction": p0.compare_fields(load(R0 / "design_pusher.json"), rec, TOL_REPRODUCE),
            "compliance_rows": rows, "s_exposed_ft2": d["geom"]["s_exposed"]}


# ---- 1. compliance matrix ------------------------------------------------------------------------------------
# start of a row label of stage1.compliance -> (requirement, the Stage 1 step that produces the value)
COMPLIANCE_MAP = (
    ("R1/R2", "R1/R2", "step 8: fixed-engine re-size"),
    ("R4", "R4", "step 1: mission and payload"),
    ("R5 mission", "R5", "step 8: fuel sized to the mission"),
    ("R6 note", "R6", "none: no source for the engine's relight envelope"),
    ("R6 mission", "R6", "none: no source for the engine's operating altitude"),
    ("R7 take-off", "R7", "step 7: performance"),
    ("R7 landing", "R7", "step 7: performance"),
    ("R7 clean stall", "R7", "step 7: maximum lift"),
    ("R8", "R8", "step 6: layout"),
    ("R9 positive", "R9", "step 7: V-n with gusts"),
    ("R9 negative", "R9", "step 7: V-n with gusts"),
    ("R10", "R10", "step 1: mission fuel allowance"),
    ("R12 sea-level", "R12", "step 7: performance"),
    ("R12 service", "R12", "step 7: performance on the engine table"),
    ("R13 static margin, full", "R13", "step 7: stability, by layout construction"),
    ("R13 static margin, empty", "R13", "step 7: stability, by layout construction"),
    ("R14", "R14", "step 7: component weights"),
    ("R15", "R15", "step 7: component weights"),
    ("R18", "R18", "step 7: loads at the V_C placard"),
    ("R17", "R17", "step 1: speed choice of every mission sub-step"),
    ("R19", "R19", "step 1: mission with the headwind"),
    ("R16", "R16", "step 4: power required in the turn"),
    ("engine power meets", "R12/R16", "step 4: largest power required"),
    ("fuel fits", "layout", "step 6: wing tank volume"),
    ("nose-wheel load, full", "layout", "step 6: layout"),
    ("nose-wheel load, empty", "layout", "step 6: layout"),
    ("main gear stows", "layout", "step 6: layout"),
    ("propeller clearance", "layout", "step 6: layout"),
    ("trim within", "layout", "step 7: trim"),
    ("nose rotation", "layout", "step 7: rotation"),
)
COMPLIANCE_COLUMNS = ("requirement_id", "requirement", "units", "value", "limit", "margin", "rule", "verdict",
                      "evidence_class", "step")
NO_LIMIT = {"by construction": "none: met by construction", "sized to it": "none: the fuel is sized to it",
            "note": "none: no source (assumption R-f)", "stow": "the sponsons at this track hold the wheels",
            "flag": "yes"}


def _margin(rule, value, limit, L):
    """Distance to the limit, positive inside it, for the rules of stage1.compliance that compare numbers."""
    if rule == "<=":
        return float(limit - value)
    if rule in (">=", "ceiling"):
        return float(value - limit)
    if rule == "in band":
        return float(min(value - L["static_margin_min"], L["static_margin_max"] - value))
    if rule == "nose":
        return float(min(value - 0.05, 0.20 - value))                 # Raymer's 5 to 20 % limits, p. 232-233
    return None


def compliance_matrix(rows, d, ig, rubber_bhp):
    """The compliance matrix of r0 with no blank cell: the rows of stage1.compliance on the rebuilt design, each
    with its requirement, margin, class and producing step, and the rows that function does not write: R3, R11 and
    the robust half of R5 and R7 (r0/info_gap.json). ig is the info-gap record, rubber_bhp the power of the
    rubber-engine design of this package (R3)."""
    L = uav.load_ledger(R0 / "ledger.yaml")[0]
    out = []
    for r in rows:
        req, step = next((q, s) for start, q, s in COMPLIANCE_MAP if r["requirement"].startswith(start))
        margin = _margin(r["rule"], r["value"], r["limit"], L)
        out.append({
            "requirement_id": req, "requirement": r["requirement"], "units": r["units"],
            "value": r["value"] if r["value"] != "" else "no source (assumption R-f)",
            "limit": r["limit"] if r["limit"] != "" else NO_LIMIT[r["rule"]],
            "margin": margin if margin is not None else f"none: {r['rule']}", "rule": r["rule"],
            "verdict": {True: "pass", False: "fail", None: f"not tested: {r['rule']}"}[r["met"]],
            "evidence_class": STAGE1_CLASS, "step": step})
    floor = {m["segment"]: m["speed_floor_fraction"] for m in d["mission"] if m["segment"].startswith("cruise")}
    hh = {k: ig["h_hat"][k]["h_hat"] for k in ("R5_guarantee", "R7")}
    hours = ig["nominal"]["R5_hours"]
    out += [
        {"requirement_id": "R3", "requirement": "R3 rubber-engine sizing first, then a production turboprop and a fixed-engine re-size",
         "units": "hp", "value": f"rubber engine at these sizes {rubber_bhp:.0f} hp; installed {d['bhp_sl']:.0f} shp ({d['engine']['fixed']})",
         "limit": "none: a procedure", "margin": "none: a procedure", "rule": "recorded",
         "verdict": "not tested: a procedure; the engine was fixed by ruling R-a", "evidence_class": EVIDENCE_CLASS,
         "step": "steps 5 and 8; the rubber-engine design of this package"},
        {"requirement_id": "R5", "requirement": "R5 hours on station at nominal values", "units": "h", "value": hours,
         "limit": R5_NOMINAL_HOURS, "margin": hours - R5_NOMINAL_HOURS, "rule": ">=",
         "verdict": "pass" if hours >= R5_NOMINAL_HOURS else "fail", "evidence_class": ROBUST_CLASS,
         "step": "robust sizing (ruling R-d): the sized loiter"},
        {"requirement_id": "R5", "requirement": f"R5 at least {L['r5_robust_hours']:g} h for every combination inside the bands: guarantee horizon",
         "units": "-", "value": hh["R5_guarantee"], "limit": HORIZON_GATE, "margin": hh["R5_guarantee"] - HORIZON_GATE, "rule": ">=",
         "verdict": "pass" if hh["R5_guarantee"] >= HORIZON_GATE else "fail", "evidence_class": ROBUST_CLASS,
         "step": "info-gap study of r0 (P0)"},
        {"requirement_id": "R7", "requirement": "R7 field length for every combination inside the bands: horizon", "units": "-",
         "value": hh["R7"], "limit": HORIZON_GATE, "margin": hh["R7"] - HORIZON_GATE, "rule": ">=",
         "verdict": "pass" if hh["R7"] >= HORIZON_GATE else "fail", "evidence_class": ROBUST_CLASS,
         "step": "info-gap study of r0 (P0)"},
        {"requirement_id": "R11", "requirement": "R11 cruise legs at the best-range speed, no minimum speed", "units": "-",
         "value": ("best-range speed unless the R17 floor is higher; the floor sets the speed on "
                   f"{floor['cruise_out']:.0%} of the cruise-out and {floor['cruise_back']:.0%} of the cruise-back sub-steps"),
         "limit": "none: no minimum speed", "margin": "none: by construction", "rule": "by construction",
         "verdict": "not tested: by construction", "evidence_class": STAGE1_CLASS, "step": "step 1: speed choice"},
    ]
    return out


def blank_cells(rows):
    """(requirement, column) of every empty cell of the matrix: None or an empty text."""
    return [(r["requirement_id"], c) for r in rows for c in COMPLIANCE_COLUMNS
            if r.get(c) is None or (isinstance(r[c], str) and not r[c].strip())]


# ---- 3. weight statement ---------------------------------------------------------------------------------------
def weight_statement(d):
    """Component weights and stations of the record, their sum against the record's empty weight, and the centre of
    gravity recomputed from the stations: without fuel (payload on), and with the fuel at the wing station."""
    rows = [{"item": k, "weight_lb": w, "x_ft": d["stations"][k]["x"], "moment_lb_ft": w * d["stations"][k]["x"]}
            for k, w in d["components_lb"].items()]
    total = sum(r["weight_lb"] for r in rows)
    weight = sum(s["weight"] for s in d["stations"].values())                    # the components and the payload
    moment = sum(s["weight"] * s["x"] for s in d["stations"].values())
    x_fuel = d["stations"]["wing"]["x"]
    return {"rows": rows, "sum_components_lb": total, "We_lb": d["We_lb"], "difference_lb": total - d["We_lb"],
            "tolerance_lb": TOL_WEIGHT_LB, "within_tolerance": abs(total - d["We_lb"]) <= TOL_WEIGHT_LB,
            "payload_lb": d["payload_lb"], "payload_x_ft": d["stations"]["payload"]["x"], "fuel_lb": d["fuel_lb"],
            "fuel_x_ft": x_fuel, "W0_lb": d["W0_lb"], "zero_fuel_weight_lb": weight,
            "cg_empty_from_stations_ft": moment / weight,
            "cg_full_from_stations_ft": (moment + d["fuel_lb"] * x_fuel) / (weight + d["fuel_lb"]),
            "cg_empty_record_ft": d["layout"]["cg_empty"], "cg_full_record_ft": d["layout"]["cg_full"]}


# ---- 6. V-n points --------------------------------------------------------------------------------------------
def vn_points(d):
    """The points of the V-n diagram, copied from the record's `vn`: the manoeuvre corner and, for each of the four
    gust cases (altitude x weight), the up and down gust at V_C and at V_D."""
    vn = d["vn"]
    pts = [{"case": "manoeuvre", "point": "corner", "V_eas_kt": vn["V_corner_eas_kt"], "n": d["n_limit"]}]
    for key, g in vn.items():
        if key.startswith("gust_"):
            for point, v, n in (("V_C up", "V_cruise_eas_kt", "n_cruise"), ("V_C down", "V_cruise_eas_kt", "n_cruise_neg"),
                                ("V_D up", "V_dive_eas_kt", "n_dive"), ("V_D down", "V_dive_eas_kt", "n_dive_neg")):
                pts.append({"case": key[5:], "point": point, "V_eas_kt": g[v], "n": g[n]})
    return pts


def vn_difference(points, d):
    """Largest difference, in speed (kt) or load factor, between a list of V-n points and the record's `vn`."""
    keys = {"V_C up": ("V_cruise_eas_kt", "n_cruise"), "V_C down": ("V_cruise_eas_kt", "n_cruise_neg"),
            "V_D up": ("V_dive_eas_kt", "n_dive"), "V_D down": ("V_dive_eas_kt", "n_dive_neg")}
    worst = 0.0
    for p in points:
        if p["case"] == "manoeuvre":
            v, n = d["vn"]["V_corner_eas_kt"], d["n_limit"]
        else:
            g = d["vn"]["gust_" + p["case"]]
            v, n = g[keys[p["point"]][0]], g[keys[p["point"]][1]]
        worst = max(worst, abs(p["V_eas_kt"] - v), abs(p["n"] - n))
    return worst


# ---- empty weight, component by component (Gate B items 8, 27) ---------------------------------------------
def scaled_weight(weight, ratio, exponent):
    """A component weight with one input of its group equation changed by `ratio` and everything else held:
    weight x ratio^exponent."""
    return weight * ratio ** exponent


def empty_weight_explanation(d, s_exposed, L):
    """Why the build-up, the Table 3.1 fit and Table 15.2 differ, from the record's own comparison.

    table_15_2: Raymer's approximate group weights (Table 15.2, p. 398, general aviation: 2.5 lb per ft^2 of exposed
    wing, 2.0 per ft^2 of tail, 1.4 per ft^2 of fuselage wetted area, 0.057 W0 for the gear, 1.4 x the engine,
    0.10 W0 for all else) next to the build-up, group by group, as built (Table 15.4 composite factors) and as metal.
    table_3_1: the steps from the fit to the build-up that the record stores, and what-ifs on the like-for-like
    step (metal, crew items in): each takes one feature a general-aviation single does not have back to a reference
    value through the exponent of its group equation, everything else held. They are not a re-size."""
    W0, comp, c = d["W0_lb"], d["components_lb"], d["empty_fraction_comparison"]
    f = wts.composite_fudge(L["composite_factor"], L.get("composite_model"))
    fudge = {"wing": f["wing"], "horizontal_tail": f["tails"], "vertical_tail": f["tails"], "fuselage": f["fuselage"],
             "main_gear": f["landing_gear"], "nose_gear": f["landing_gear"]}
    metal = {k: v / fudge.get(k, 1.0) for k, v in comp.items()}      # as uav.statistical_empty_fractions
    tails = d["horizontal_tail"]["area"] + d["vertical_tail"]["area"]
    groups = [("wing", ["wing"], 2.5 * s_exposed, "2.5 lb/ft^2 of exposed wing"),
              ("tails", ["horizontal_tail", "vertical_tail"], 2.0 * tails, "2.0 lb/ft^2 of tail area"),
              ("fuselage", ["fuselage"], 1.4 * d["fuselage"]["s_wet"], "1.4 lb/ft^2 of wetted area"),
              ("landing gear and sponsons", ["main_gear", "nose_gear", "sponsons"], 0.057 * W0, "0.057 W0 (no sponsons in the table)"),
              ("installed engine", ["installed_engine"], 1.4 * d["engine"]["weight_lb"], "1.4 x engine weight"),
              ("all else", ["fuel_system", "flight_controls", "hydraulics", "avionics", "electrical"], 0.10 * W0, "0.10 W0")]
    table = [{"group": g, "items": items, "rule": rule, "table_15_2_lb": t,
              "build_up_lb": sum(comp[i] for i in items), "build_up_metal_lb": sum(metal[i] for i in items)}
             for g, items, t, rule in groups]
    for g in table:
        g["build_up_minus_table_lb"] = g["build_up_lb"] - g["table_15_2_lb"]
        g["metal_minus_table_lb"] = g["build_up_metal_lb"] - g["table_15_2_lb"]
    labels = (("table_3_1", "Table 3.1 fit times the composite factor"),
              ("table_3_1_metal", "the fit without the composite factor"),
              ("build_up_metal_with_crew_items", "group equations against the fit, like for like (metal, crew items in)"),
              ("build_up_metal", "crew items left out (furnishings, (15.59))"),
              ("build_up", "Table 15.4 composite factors on the groups"))
    steps, last = [], None
    for key, label in labels:
        steps.append({"key": key, "label": label, "fraction": c[key], "weight_lb": c[key] * W0,
                      "change": 0.0 if last is None else c[key] - last,
                      "change_lb": 0.0 if last is None else (c[key] - last) * W0})
        last = c[key]
    gap = (c["build_up_metal_with_crew_items"] - c["table_3_1_metal"]) * W0
    features = [
        {"feature": "sponsons for the main gear (no counterpart in the fit's aircraft)", "metal_lb": metal["sponsons"],
         "how": "the whole item"},
        {"feature": f"main gear {d['gear_length_in']:.1f} in long for propeller clearance, against the ledger's {L['main_gear_length_in']:g} in",
         "metal_lb": metal["main_gear"] - scaled_weight(metal["main_gear"], L["main_gear_length_in"] / d["gear_length_in"],
                                                        EXP_MAIN_GEAR_LENGTH),
         "how": f"(15.50), weight ~ length^{EXP_MAIN_GEAR_LENGTH}"},
        {"feature": f"horizontal tail {d['ht_volume_scale']:.3f} times the Table 6.4 size, for rotation",
         "metal_lb": metal["horizontal_tail"] - scaled_weight(metal["horizontal_tail"], 1.0 / d["ht_volume_scale"], EXP_HT_AREA),
         "how": f"(15.47), weight ~ area^{EXP_HT_AREA}"},
        {"feature": f"wing loading {d['W_S']:g} lb/ft^2 against the class's typical {TYPICAL_WS_GA_SINGLE:g} (Table 5.5): a larger wing",
         "metal_lb": metal["wing"] - scaled_weight(metal["wing"], d["W_S"] / TYPICAL_WS_GA_SINGLE, EXP_WING_AREA),
         "how": f"(15.46), weight ~ area^{EXP_WING_AREA}"}]
    return {"W0_lb": W0, "s_exposed_ft2": s_exposed, "composite_factors": f,
            "table_15_2": {"groups": table, "sum_table_lb": sum(g["table_15_2_lb"] for g in table),
                           "sum_build_up_lb": sum(g["build_up_lb"] for g in table),
                           "record_fraction": c["table_15_2_approximate"]},
            "table_3_1": {"steps": steps, "like_for_like": {"gap_lb": gap, "features": features,
                                                           "remainder_lb": gap - sum(x["metal_lb"] for x in features)},
                          "table_6_2_fraction": c["table_6_2"]},
            "anderson_build_up": {k: load(PERF)["anderson_w0"][k] for k in ("buildup_W0", "buildup_We")}}


# ---- payload bay, first check (Gate B item 30, NR-21, PD-12) -------------------------------------------------
def fuselage_volume(A_top, A_side, length):
    """Raymer (7.13), p. 153: fuselage volume from the top and side projected areas and the length."""
    return 3.4 * A_top * A_side / (4.0 * length)


def body_radius(x, L_f, D_f):
    """Radius at station x of the body of revolution that Stage 1's three-view draws (conceptual/report.py
    three_view): an elliptic nose over the first 20 % of the length, constant to 60 %, then a straight taper to
    15 % of the radius at the tail. A drawing convention: Stage 1's analysis knows the body only through its
    length, diameter and fill factor."""
    t = x / L_f
    if t < 0.2:
        return 0.5 * D_f * math.sqrt(max(0.0, 1.0 - (1.0 - t / 0.2) ** 2))
    if t > 0.6:
        return 0.5 * D_f * max(0.15, 1.0 - (t - 0.6) / 0.4 * 0.85)
    return 0.5 * D_f


def drawn_body_volume(x1, x2, L_f, D_f, n=4000):
    """Volume of the drawn body between two stations: the cross-section area pi r^2 summed at n mid-points."""
    dx = (x2 - x1) / n
    return sum(math.pi * body_radius(x1 + (i + 0.5) * dx, L_f, D_f) ** 2 for i in range(n)) * dx


def drawn_body_fill(L_f, D_f, n=4000):
    """Projected area of the drawn body over length x diameter: what the ledger calls fuselage_fill."""
    dx = L_f / n
    return sum(2.0 * body_radius((i + 0.5) * dx, L_f, D_f) for i in range(n)) * dx / (L_f * D_f)


def payload_bay(d, L):
    """First check of the payload-bay volume. The PD-12 volume (payload weight over 30 lb/ft^3) against the free
    volume of the Stage 1 body: Raymer (7.13) with both projected areas fill x length x diameter, less what the
    record gives a size for. Then a local reading on the drawn body: how much of the nose a bay centred on the
    payload station takes if it fills the whole cross-section, and where the retracted nose-gear leg lies
    (Stage 1 checks that the main gear stows, uav.layout "gear_track", and has no such check for the nose gear)."""
    L_f, D_f = d["fuselage"]["length"], d["fuselage"]["diameter"]
    need = d["payload_lb"] / PAYLOAD_DENSITY_LB_FT3
    area = L["fuselage_fill"] * L_f * D_f
    body = fuselage_volume(area, area, L_f)
    e = d["engine"]
    deducted = [{"item": "engine envelope as a box (the record's length and diameter)",
                 "volume_ft3": e["length_in"] * e["diameter_in"] ** 2 / 12.0 ** 3},
                {"item": f"installed flight avionics at {PAYLOAD_DENSITY_LB_FT3:g} lb/ft^3",
                 "volume_ft3": d["components_lb"]["avionics"] / PAYLOAD_DENSITY_LB_FT3}]
    free = body - sum(i["volume_ft3"] for i in deducted)
    xp = d["stations"]["payload"]["x"]
    lo, hi = 0.0, xp                                    # half-length of a bay centred on the payload station
    centred = drawn_body_volume(0.0, 2.0 * xp, L_f, D_f) >= need
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if drawn_body_volume(xp - mid, xp + mid, L_f, D_f) < need else (lo, mid)
    half = 0.5 * (lo + hi)
    x_nose_gear, x_avionics = d["stations"]["nose_gear"]["x"], d["stations"]["avionics"]["x"]
    ahead = drawn_body_volume(0.0, x_avionics, L_f, D_f)
    strut = d["gear_length_in"] / 12.0                  # Stage 1 gives the nose gear the main gear's length (uav._build)
    strut_end = x_nose_gear + strut                     # retracted aft: the leg is longer than the nose ahead of it
    return {"payload_lb": d["payload_lb"], "density_lb_ft3": PAYLOAD_DENSITY_LB_FT3, "payload_volume_ft3": need,
            "fuselage_length_ft": L_f, "fuselage_diameter_ft": D_f, "fuselage_fill": L["fuselage_fill"],
            "body_volume_ft3": body, "deducted": deducted, "free_volume_ft3": free,
            "payload_share_of_free_volume": need / free, "fits_in_free_volume": need <= free,
            "not_deducted": ["nose-gear bay", "sensor turret and its mount", "electrical, flight-control and other systems",
                             "skin, frames and the wing carry-through", "engine inlet and exhaust ducts"],
            "drawn_body": {"fill": drawn_body_fill(L_f, D_f), "volume_ft3": drawn_body_volume(0.0, L_f, L_f, D_f)},
            "nose": {"payload_station_ft": xp, "radius_at_station_ft": body_radius(xp, L_f, D_f),
                     "fits_centred_on_station": centred, "bay_from_ft": xp - half, "bay_to_ft": xp + half,
                     "bay_length_ft": 2.0 * half, "nose_gear_station_ft": x_nose_gear, "avionics_station_ft": x_avionics,
                     "nose_gear_station_inside_bay": xp - half <= x_nose_gear <= xp + half,
                     "avionics_station_inside_bay": xp - half <= x_avionics <= xp + half,
                     "volume_ahead_of_avionics_station_ft3": ahead, "payload_share_of_that_volume": need / ahead,
                     "gear_length_ft": strut, "nose_ahead_of_gear_station_ft": x_nose_gear,
                     "retracts_forward": strut <= x_nose_gear, "retracted_aft_reaches_ft": strut_end,
                     "retracted_leg_crosses_bay": strut_end > xp - half,
                     "retracted_leg_passes_avionics_station": strut_end > x_avionics}}


# ---- trades ---------------------------------------------------------------------------------------------------
def hours_for_fuel(fuel_at, target, hi=HOURS_HI):
    """Loiter time (h) at which fuel_at(hours) equals target: bisection to 0.002 h, then a straight line across
    the last bracket (as measurement.info_gap.Built.hours_detail). 0 if the mission cannot be flown (infinite
    fuel) or already burns the target with no loiter; `hi` if the target is not reached by then."""
    lo, f_lo = 0.0, fuel_at(0.0)
    if not math.isfinite(f_lo) or f_lo >= target:
        return 0.0
    f_hi = fuel_at(hi)
    if f_hi < target:
        return hi
    while hi - lo > 2e-3:
        mid = 0.5 * (lo + hi)
        f_mid = fuel_at(mid)
        lo, f_lo, hi, f_hi = (mid, f_mid, hi, f_hi) if f_mid < target else (lo, f_lo, mid, f_mid)
    if not math.isfinite(f_hi):
        return lo
    return lo + (hi - lo) * (target - f_lo) / (f_hi - f_lo)


def as_built(built, theta):
    """The built aircraft (wing area, tanks and fuel of the record) with the ledger values in theta changed:
    take-off weight, hours on station on the record's fuel, take-off and landing distance. The rebuild is the
    info-gap study's (measurement.info_gap.Built)."""
    hours, reason = built.hours_detail(theta)
    takeoff, landing = built.field_lengths(theta)
    try:
        W0 = built.w0_for(theta)
    except ValueError:                       # the weight does not close at theta; hours_detail gives the reason
        W0 = None
    return {"W0_lb": W0, "hours_on_station": hours, "reason": reason, "takeoff_ft": takeoff,
            "landing_ft": landing}


def payload_for_fuel(built, d, payload):
    """Payload exchanged for fuel at the record's take-off weight: hours on station with `payload` lb on board
    and the fuel raised (or cut) by the difference, and whether that fuel fits the wing tanks of the record."""
    fuel = d["fuel_lb"] + (d["payload_lb"] - payload)
    theta = {"payload_lb": float(payload)}
    hours = hours_for_fuel(lambda h: built.fuel_at(theta, h, d["W0_lb"])[0], fuel)
    volume = d["fuel_volume_ft3"]["needed"] * fuel / d["fuel_lb"]
    return {"payload_lb": payload, "fuel_lb": fuel, "W0_lb": d["W0_lb"], "hours_on_station": hours,
            "fuel_volume_ft3": volume, "fuel_fits_tanks": volume <= d["fuel_volume_ft3"]["available"]}


def resized(sizing_ledger, changes):
    """Stage 1's one-at-a-time trade (conceptual/stage1.trades): the pusher sized again at W/S 13, A 8 with the
    ledger values in `changes` replaced, tail resized for rotation, then the compliance rows. This is another
    aircraft for comparison, not a change of r0."""
    L = dict(sizing_ledger, **changes)
    raw = stage1.engine_options(stage1.CHOSEN_ENGINE)[1][stage1.CHOSEN_ENGINE]
    try:
        a = stage1.analyse("pusher", W_S, ASPECT, L, rs.as_is_engine(), W0_guess=rs.first_guess(POWER_HP, L["loiter_h"]))
    except ValueError as e:
        return {"changes": changes, "W0_lb": None, "error": str(e)}
    d = a["design"]
    rows = stage1.compliance(d, d["ledger_used"], a["layout"], a["performance"], *a["fuel_volume"], raw)
    return {"changes": changes, "W0_lb": d["W0"], "We_lb": d["We"], "fuel_lb": d["fuel"],
            "ht_volume_scale": a["ht_scale"], "sm_full": a["layout"]["sm_full"], "sm_empty": a["layout"]["sm_empty"],
            "failed": [c["requirement"] for c in rows if c["met"] is False]}


def trades(built, d, sizing_ledger, composite_band):
    """The three trades the spec names (NR-3). as_built: the aircraft of r0 as it is. resized: Stage 1's trade."""
    lo, hi = composite_band
    mid = sizing_ledger["composite_factor"]
    composite = [lo, 0.5 * (lo + mid), mid, 0.5 * (mid + hi), hi]
    return {
        "payload_for_fuel": [payload_for_fuel(built, d, p) for p in (0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0)],
        "payload_at_record_fuel": [dict(as_built(built, {"payload_lb": p}), payload_lb=p)
                                   for p in (300.0, 400.0, 500.0, 600.0, 700.0)],
        "altitude_as_built": [dict(as_built(built, {"mission_altitude_ft": h}), mission_altitude_ft=h)
                              for h in (15000.0, 17500.0, 20000.0, 22500.0, 25000.0)],
        "composite_as_built": [dict(as_built(built, {"composite_factor": c}), composite_factor=c) for c in composite],
        "resized": {
            "nominal": resized(sizing_ledger, {}),
            "loiter_h": [resized(sizing_ledger, {"loiter_h": h}) for h in (8.0, 9.0, 10.0, 11.0, 12.0, 13.0)],
            "payload_lb": [resized(sizing_ledger, {"payload_lb": p}) for p in (300.0, 400.0, 500.0, 600.0, 700.0)],
            "mission_altitude_ft": [resized(sizing_ledger, {"mission_altitude_ft": h}) for h in (15000.0, 20000.0, 25000.0)],
            "composite_factor": [resized(sizing_ledger, {"composite_factor": c}) for c in (lo, mid, hi)]}}


def carpet_rows(curve):
    """The cells of the committed re-size grid at 450 shp and h_T 1.05 (last iteration): W/S, A, whether the
    cell has a compliant robust design, its weight, and the reason if it has none."""
    cell = curve["per_P"][f"{POWER_HP:g}"][f"{H_T:.2f}"]
    return [{"W_S": r["W_S"], "A": r["A"], "ok": bool(r["ok"]) and not r["failed"], "W0_lb": r.get("W0_lb"),
             "fuel_lb": r.get("fuel_lb"), "L_sized_h": r.get("L_sized_h"), "status": r.get("status") or "; ".join(r["failed"])}
            for r in cell["iterations"][-1]["candidates"]]


# ---- App. L decomposition and the climb at the worst corner (NR-1, item 18) -------------------------------
def flat_theta(theta, eta_p):
    """theta with the propeller swapped for the flat efficiency eta_p (the disk factor is dropped)."""
    out = {k: v for k, v in theta.items() if k != "prop_real_to_ideal"}
    out.update(propeller_model="flat", eta_p=eta_p)
    return out


def decompose(built, cell, entries, sized_loiter_h):
    """measurement.appl_decomposition.case on r0: fuel by segment, mean propeller efficiency per leg and the climb
    inputs, with the disk as recorded and with a flat efficiency swapped in, at nominal (sized loiter) and at the
    worst endurance points of the record (h = 1 and the target h_T). The flat efficiency is the ledger's eta_p at
    nominal and its band low end scaled by h at the corners, as in the 2026-11-26 decomposition."""
    eta = entries["eta_p"]
    worst = {"corner_h1": (1.0, cell["modes"]["endurance"]["worst_at_h1"]),
             "corner_target": (cell["h_T"], cell["worst_at_target"]["endurance"])}
    states = {"nominal": ({}, sized_loiter_h, eta["value"])}
    for name, (h, w) in worst.items():
        states[name] = (dict(w["moved"]), w["hours"], eta["value"] - h * (eta["value"] - eta["band"][0]))
    out = {}
    for name, (theta, hours, eta_flat) in states.items():
        flat = flat_theta(theta, eta_flat)
        disk_case, flat_case = decomposition.case(built, theta, hours), decomposition.case(built, flat, hours)
        out[name] = {"theta": theta, "loiter_h": hours, "flat_eta_p": eta_flat,
                     "disk_factor": theta.get("prop_real_to_ideal", built.L["prop_real_to_ideal"]),
                     "disk": disk_case, "flat": flat_case,
                     "hours_on_station": {"disk": built.hours_detail(theta)[0], "flat": built.hours_detail(flat)[0]},
                     "disk_minus_flat_lb": dict({k: disk_case["segment_fuel_lb"][k] - flat_case["segment_fuel_lb"][k]
                                                 for k in disk_case["segment_fuel_lb"]},
                                                fuel_with_reserve=disk_case["fuel_with_reserve_lb"] - flat_case["fuel_with_reserve_lb"])}
    return out


def climb_speed_margin(V_kt, W_lb, S_ft2, rho, clmax, floor):
    """A climb speed (true airspeed, kt) against the stall speed at weight W and density rho, and against
    `floor` times it (the ledger's lowest climb speed, climb_speed_over_stall)."""
    v_stall = perf.stall_speed(W_lb / S_ft2, rho, clmax) / KT
    return {"V_kt": V_kt, "W_lb": W_lb, "V_stall_kt": v_stall, "over_stall": V_kt / v_stall,
            "above_stall": V_kt >= v_stall, "floor": floor, "above_floor": V_kt >= floor * v_stall}


def climb_check(built, states):
    """Item 18. For the nominal point and the two worst endurance points of `states` (from decompose):
    - Stage 1's climb leg uses one true airspeed, the best-climb speed at sea level, from sea level to the mission
      altitude. That speed against the stall speed at the mission altitude, at the weights at the start and the
      end of the climb, with the clean C_L,max of the state;
    - the same climb integrated in 1,000 ft steps by prelim.p0_baseline.integrate_climb, where every altitude
      flies its own best-climb speed above its own 1.2 V_stall, against the two-point estimate; the difference
      as a share of the mission fuel (the P0 row-5 measure) and, divided by the loiter fuel flow, in hours."""
    out = {}
    for name, s in states.items():
        b, L = built.build(s["theta"], s["loiter_h"])
        S, h_top = built.S_record, L["mission_altitude_ft"]
        alt = isa(h_top)
        climb = next(r for r in b["mission"] if r[0] == "climb")
        loiter = next(r for r in b["mission"] if r[0] == "loiter")
        W_start, W_end, clmax = climb[1], climb[2], b["clmax"]["clean"]
        V = s["disk"]["climb"]["climb_speed_kt"]
        floor = L["climb_speed_over_stall"]
        point = p0.climb_point_fn(b, L, S)
        V_cruise = uav._cruise_speed(W_start, S, alt["rho"], b["CD0_alt"], b["K"], clmax, L, "range")[0]
        altitudes = np.arange(0.0, h_top + 0.5 * p0.STEP_FT, p0.STEP_FT).tolist()
        integ = p0.integrate_climb(point, W_start, altitudes, V_end=V_cruise)
        two_point = W_start - W_end
        diff = integ["fuel_lb"] - two_point
        flow = (loiter[1] - loiter[2]) / s["loiter_h"]
        share = sizing.RESERVE_FACTOR * abs(diff) / built.d["fuel_lb"]
        out[name] = {
            "W0_lb": s["disk"]["W0_lb"], "clmax_clean": clmax, "mission_altitude_ft": h_top,
            "stage1_climb_speed_kt": V,
            "against_stall_at_altitude": {"start_of_climb_weight": climb_speed_margin(V, W_start, S, alt["rho"], clmax, floor),
                                          "end_of_climb_weight": climb_speed_margin(V, W_end, S, alt["rho"], clmax, floor)},
            "two_point_fuel_lb": two_point, "integrated_fuel_lb": integ["fuel_lb"], "integrated_time_min": integ["time_s"] / 60.0,
            "rate_at_sea_level_fpm": integ["steps"][0]["rate_from_fpm"], "rate_at_top_fpm": integ["steps"][-1]["rate_to_fpm"],
            "speed_at_sea_level_kt": integ["steps"][0]["V_from_kt"], "speed_below_top_kt": integ["steps"][-1]["V_from_kt"],
            "fuel_difference_lb": diff, "fuel_difference_relative": diff / two_point,
            "mission_fuel_share": share, "tolerance": TOL_CLIMB_FUEL, "finding_for_r1": share > TOL_CLIMB_FUEL,
            "loiter_fuel_flow_lb_h": flow, "hours_on_station": s["hours_on_station"]["disk"],
            "hours_change_estimate": -diff / flow, "hours_estimate": s["hours_on_station"]["disk"] - diff / flow,
            "need_h": L["r5_robust_hours"],
            "ceiling_rate_fpm": L["ceiling_rate_fpm"], "top_of_climb_above_service_ceiling":
                integ["steps"][-1]["rate_to_fpm"] < L["ceiling_rate_fpm"]}
    return {"states": out, "step_ft": p0.STEP_FT}


# ---- concept record at these sizes (NR-4, Gate A item A9) -------------------------------------------------
def break_even_weight_ratio(weights):
    """Pusher W0 over tractor W0 at which the two weighted scores of stage1.concept_scores are equal, the tractor
    being the lighter: 5 w0/r + (pusher judgement points) = 5 w0 + (tractor judgement points)."""
    w0 = weights[0][1]
    tractor = sum(w * gt for _, w, gt, _ in weights[1:])
    pusher = sum(w * gp for _, w, _, gp in weights[1:])
    return 5.0 * w0 / (5.0 * w0 + tractor - pusher)


def concept_record(rebuilt, out):
    """The tractor with the same engine and the rubber-engine pusher, sized by Stage 1 at W/S 13, A 8 with the
    ledger r0 was sized with (sized loiter and V_C rule included), their compliance rows, and the round-1 scoring
    table of the tractor against r0 (stage1.concept_scores, weights unchanged). Design records go to `out`."""
    L, raw = rebuilt["ledger_sizing"], rebuilt["engine_raw"]
    guess = rs.first_guess(POWER_HP, L["loiter_h"])
    cases = {"tractor": ("tractor", rs.as_is_engine(), raw, "design_tractor.json"),
             "pusher_rubber": ("pusher", None, {}, "design_pusher_rubber.json")}
    res, designs = {"pusher": rebuilt["analysis"]}, {}
    for name, (concept, engine, eng_raw, file) in cases.items():
        a = stage1.analyse(concept, W_S, ASPECT, L, engine, W0_guess=guess)
        d = a["design"]
        rows = stage1.compliance(d, d["ledger_used"], a["layout"], a["performance"], *a["fuel_volume"], eng_raw)
        (out / file).write_text(json.dumps(stage1.design_record(a, L, eng_raw), indent=1, default=float))
        designs[name] = {"file": file, "concept": concept, "engine": d["engine"].get("fixed", "rubber"), "W0_lb": d["W0"],
                         "We_lb": d["We"], "fuel_lb": d["fuel"], "bhp": d["bhp"], "engine_weight_lb": d["engine"]["weight_lb"],
                         "engine_in_range": d["engine"].get("in_range"), "ht_volume_scale": a["ht_scale"],
                         "gear_length_in": d["gear_length_in"], "nose_load": a["layout"]["nose_load"],
                         "sm_full": a["layout"]["sm_full"], "sm_empty": a["layout"]["sm_empty"],
                         "prop_clearance_in": a["layout"]["prop_clearance_in"],
                         "takeoff_ft": a["performance"]["takeoff_ft"], "landing_ft": a["performance"]["landing_ft"],
                         "service_ceiling_ft": a["performance"]["service_ceiling_ft"],
                         "failed": [c["requirement"] for c in rows if c["met"] is False]}
        if name == "tractor":
            res["tractor"] = a
    table, score, feasibility = stage1.concept_scores(res, L)
    ratio = res["pusher"]["design"]["W0"] / res["tractor"]["design"]["W0"]
    even = break_even_weight_ratio(stage1.ROUND1_WEIGHTS)
    return {"designs": designs, "scoring": {"table": table, "score": score, "feasibility": feasibility,
                                            "highest_score": max(score, key=score.get), "frozen": stage1.FROZEN_CONCEPT,
                                            "reversed": max(score, key=score.get) != stage1.FROZEN_CONCEPT,
                                            "pusher_over_tractor_W0": ratio, "break_even_ratio": even,
                                            "previous_record": "runs/task12/stage1/2026-11-25/concept_scores.json",
                                            "previous_score": load(REPO / "runs/task12/stage1/2026-11-25/concept_scores.json")["score"]}}


# ---- the judgement file: checks and the band audit's numbers ---------------------------------------------
def check_out_of_calibration(entries):
    """Problems of the out-of-calibration list: an empty list, a correlation flagged on 2026-11-25 that is missing
    or listed twice, a status that is not one of OC_STATUS, an entry without its fields."""
    problems = [] if entries else ["the list is empty"]
    for tag in FLAGGED_2026_11_25:
        n = sum(e.get("flagged_2026_11_25") == tag for e in entries)
        if n != 1:
            problems.append(f"{tag}: flagged in the 2026-11-25 package, listed {n} times here")
    for e in entries:
        if e.get("status") not in OC_STATUS:
            problems.append(f"{e.get('id')}: status {e.get('status')!r}")
        for key in ("id", "correlation", "calibrated_for", "used_here", "carried_by"):
            if not e.get(key):
                problems.append(f"{e.get('id')}: no {key}")
    if len({e.get("id") for e in entries}) != len(entries):
        problems.append("an id is used twice")
    return problems


def check_risks(risks):
    """Problems of the risk list: empty, a risk without its fields, a package that the spec does not have, or a
    risk that names neither a package that measures it nor the ruling it is carried under."""
    problems = [] if risks else ["the list is empty"]
    for r in risks:
        for key in ("id", "risk", "effect", "how"):
            if not r.get(key):
                problems.append(f"{r.get('id')}: no {key}")
        unknown = [p for p in r.get("measured_by", []) if p not in PACKAGES]
        if unknown:
            problems.append(f"{r.get('id')}: {unknown} is not a package of the spec")
        if not r.get("measured_by") and not r.get("carried_under"):
            problems.append(f"{r.get('id')}: names no package and no ruling")
    return problems


def check_band_audit(audit, entries):
    """Problems of the band audit: it must class exactly the ledger entries without a band, each in one of
    BAND_CLASSES, and a 'needs a band' entry must carry a proposal with its basis or say why it has none."""
    unbanded = {k for k, q in entries.items() if "band" not in q}
    problems = [f"{k}: no band and not audited" for k in sorted(unbanded - set(audit))]
    problems += [f"{k}: audited but not an unbanded ledger entry" for k in sorted(set(audit) - unbanded)]
    for k, a in audit.items():
        if a.get("class") not in BAND_CLASSES or not a.get("reason"):
            problems.append(f"{k}: class {a.get('class')!r} or no reason")
        elif a["class"] == "needs a band":
            if a.get("proposed_band") is None and not a.get("why_no_proposal"):
                problems.append(f"{k}: no proposal and no reason for it")
            if a.get("proposed_band") is not None and not a.get("basis"):
                problems.append(f"{k}: a proposed band without its basis")
    return problems


def band_audit(audit, entries, built, sizing_ledger, nominal, corner):
    """The audit joined with the ledger, and for each 'needs a band' entry what it moves: at 0.9 and 1.1 times its
    value, at the ends of a proposed band and at its extra values, the built aircraft (hours on station, take-off,
    landing: as the info-gap study rebuilds it), the hours on station with the same change added to the worst
    endurance point of the record at h = 1 (`corner`: its moved values and hours), and Stage 1's re-sized trade
    (take-off weight, failed rows). The +-10 % is a common step for comparing entries, not a band."""
    rows = []
    for name, a in audit.items():
        q = entries[name]
        row = {"name": name, "value": q["value"], "units": q["units"], "confidence": q["confidence"],
               "class": a["class"], "reason": a["reason"]}
        if a["class"] == "needs a band":
            values = [0.9 * q["value"], 1.1 * q["value"], *(a.get("proposed_band") or []), *a.get("extra_values", [])]
            points = []
            for v in dict.fromkeys(float(x) for x in values if float(x) != float(q["value"])):
                built_row, sized = as_built(built, {name: v}), resized(sizing_ledger, {name: v})
                at_corner = built.hours_detail(dict(corner["moved"], **{name: v}))[0]
                points.append({"value": v, "hours_on_station": built_row["hours_on_station"],
                               "hours_at_corner_h1": at_corner, "hours_at_corner_h1_change": at_corner - corner["hours"],
                               "hours_change": built_row["hours_on_station"] - nominal["hours_on_station"],
                               "takeoff_change_ft": built_row["takeoff_ft"] - nominal["takeoff_ft"],
                               "landing_change_ft": built_row["landing_ft"] - nominal["landing_ft"],
                               "resized_W0_lb": sized["W0_lb"], "resized_failed": sized.get("failed", [sized.get("error")])})
            row.update(proposed_band=a.get("proposed_band"), basis=a.get("basis"), why_no_proposal=a.get("why_no_proposal"),
                       measured_by=a.get("measured_by", []), carried_under=a.get("carried_under"), points=points)
        rows.append(row)
    return {"rows": rows, "corner_h1_hours": corner["hours"], "n_entries": len(entries), "n_banded": sum("band" in q for q in entries.values()),
            "n_unbanded": len(rows), "by_class": {c: sum(r["class"] == c for r in rows) for c in BAND_CLASSES},
            "n_proposed_bands": sum(r.get("proposed_band") is not None for r in rows)}


# ---- test report (Stage 1 output 10) ------------------------------------------------------------------------
def run_tests(out):
    """pytest on tests/task12 and on the preliminary-design tests that do not read this record, as a recorded run:
    the summary line, the counts and the full log in OUT/pytest.log."""
    targets = ["tests/task12", "tests/task12_pd/test_p0_baseline.py", "tests/task12_pd/test_p0_record.py",
               "tests/task12_pd/test_p0_report.py", "tests/task12_pd/test_p1_package.py"]
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets]
    run = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=REPO)
    (out / "pytest.log").write_text(run.stdout + run.stderr)
    last = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ""
    counts = {word: int(n) for n, word in (pair.split()[:2] for pair in last.split(" in ")[0].split(", ") if pair[:1].isdigit())}
    return {"command": "python -m pytest -q -p no:cacheprovider " + " ".join(targets), "exit_code": run.returncode,
            "summary_line": last, "counts": counts, "log": "pytest.log"}


def equation_table():
    """Each public method function of conceptual/, its equation tags and pages, and the tests that call it
    (conceptual/report.py equation_table)."""
    from conceptual import report
    return [{"function": f, "equations": e, "pages": p, "tests": t} for f, e, p, t in report.equation_table()]


# ---- acceptance -------------------------------------------------------------------------------------------------
def acceptance_rows(res):
    """The acceptance rows of spec P1 and one row per added Gate B item, each with its number and a verdict.
    A row that states a finding says so; nothing here is tuned to pass."""
    rep, w, vn = res["reproduction"], res["weight_statement"], res["vn"]
    comp, cl, sc, bay = res["compliance"], res["climb_check"]["states"], res["concepts"]["scoring"], res["payload_bay"]
    nominal = res["trades"]["resized"]["nominal"]
    r0 = load(R0 / "design_pusher.json")
    trade_ok = (nominal["W0_lb"] is not None and abs(nominal["W0_lb"] / r0["W0_lb"] - 1.0) <= TOL_REPRODUCE
                and abs(res["nominal_as_built"]["hours_on_station"] - res["sized_loiter_h"]) <= 2e-3)
    slow = [k for k, s in cl.items() if not s["against_stall_at_altitude"]["end_of_climb_weight"]["above_floor"]]
    stalled = [k for k, s in cl.items() if not s["against_stall_at_altitude"]["end_of_climb_weight"]["above_stall"]]
    finding = [k for k, s in cl.items() if s["finding_for_r1"]]
    e = res["empty_weight"]
    t152 = abs(e["table_15_2"]["sum_table_lb"] / (e["table_15_2"]["record_fraction"] * e["W0_lb"]) - 1.0)
    return [
        {"row": 1, "what": "every number is read from r0: the design sized again by the script equals r0, field by field",
         "value": rep["max_relative_difference"], "n_compared": rep["n_compared"], "n_different": len(rep["different"]),
         "tolerance": TOL_REPRODUCE, "verdict": "pass" if not (rep["different"] or rep["added"] or rep["removed"]) else "fail"},
        {"row": 2, "what": "the compliance matrix has no blank row", "value": len(comp["blank_cells"]), "n_rows": len(comp["rows"]),
         "n_failed": sum(r["verdict"] == "fail" for r in comp["rows"]),
         "verdict": "pass" if not comp["blank_cells"] and comp["requirements_missing"] == [] else "fail"},
        {"row": 3, "what": "the weight statement sums to the record's empty weight", "value": w["difference_lb"],
         "tolerance": TOL_WEIGHT_LB, "verdict": "pass" if w["within_tolerance"] else "fail"},
        {"row": 4, "what": "the V-n diagram's points equal r0's vn entries", "value": vn["max_difference"], "n_points": len(vn["points"]),
         "tolerance": TOL_VN, "verdict": "pass" if vn["max_difference"] <= TOL_VN else "fail"},
        {"row": 5, "what": "out-of-calibration list: not empty, and every correlation flagged on 2026-11-25 is in it or has a reason",
         "value": len(res["out_of_calibration"]["entries"]), "problems": res["out_of_calibration"]["problems"],
         "verdict": "pass" if res["out_of_calibration"]["entries"] and not res["out_of_calibration"]["problems"] else "fail"},
        {"row": 6, "what": "risk list: not empty, and every risk names the package that measures it or the ruling that carries it",
         "value": len(res["risks"]["entries"]), "problems": res["risks"]["problems"],
         "n_without_package": sum(not r["measured_by"] for r in res["risks"]["entries"]),
         "verdict": "pass" if res["risks"]["entries"] and not res["risks"]["problems"] else "fail"},
        {"row": 7, "what": "trades (NR-3): the nominal case of each trade is r0 (re-sized weight; hours of the built aircraft)",
         "value": None if nominal["W0_lb"] is None else nominal["W0_lb"] / r0["W0_lb"] - 1.0,
         "hours_nominal": res["nominal_as_built"]["hours_on_station"], "tolerance": TOL_REPRODUCE,
         "verdict": "pass" if trade_ok else "fail"},
        {"row": 8, "what": "App. L decomposition on r0 (NR-1) and the climb speed at the worst endurance corner (item 18): "
                           "Stage 1's climb speed at or above 1.2 V_stall at the mission altitude; integrated climb within 1 % of the mission fuel",
         "value": {k: s["against_stall_at_altitude"]["end_of_climb_weight"]["over_stall"] for k, s in cl.items()},
         "mission_fuel_share": {k: s["mission_fuel_share"] for k, s in cl.items()}, "tolerance": TOL_CLIMB_FUEL,
         "below_floor": slow, "below_stall": stalled, "finding_states": finding,
         "verdict": "finding for r1" if finding else ("pass with a note" if slow else "pass")},
        {"row": 9, "what": "concept record at these sizes (NR-4, A9): the scoring does not reverse",
         "value": sc["score"], "break_even_ratio": sc["break_even_ratio"], "weight_ratio": sc["pusher_over_tractor_W0"],
         "verdict": "REVERSED: reported to the owner, the choice is not re-opened" if sc["reversed"] else "pass (not reversed)"},
        {"row": 10, "what": "empty weight (items 8, 27): the Table 15.2 groups sum to the record's value and the steps close",
         "value": t152, "tolerance": TOL_REPRODUCE, "unexplained_lb": e["table_3_1"]["like_for_like"]["remainder_lb"],
         "verdict": "pass" if t152 <= TOL_REPRODUCE else "fail"},
        {"row": 11, "what": "band audit (item 28): every ledger entry without a band is classed",
         "value": res["ledger"]["audit"]["n_unbanded"], "by_class": res["ledger"]["audit"]["by_class"],
         "problems": res["ledger"]["problems"], "verdict": "pass" if not res["ledger"]["problems"] else "fail"},
        {"row": 12, "what": "payload bay, first check (item 30, PD-12): the payload volume is inside the free volume of the Stage 1 body",
         "value": bay["payload_volume_ft3"], "reference": bay["free_volume_ft3"], "share": bay["payload_share_of_free_volume"],
         "verdict": "pass" if bay["fits_in_free_volume"] else "fail"}]


# ---- the run ---------------------------------------------------------------------------------------------------
def run(out, log, with_tests=True):
    """The whole package; returns the result dict (also written to OUT/p1.json)."""
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P1 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "r0_info_gap": R0 / "info_gap.json",
             "r0_cell_result": R0 / "cell_result.json", "r0_engine_table": R0 / "m250_table.json", "p0": P0_JSON,
             "resize_grid": CURVE, "gate_b_perf": PERF, "judgements": JUDGEMENTS, "ledger_now": uav.LEDGER}
    res = {"inputs": dict(tree, command="python -m prelim.p1_package " + " ".join(sys.argv[1:]),
                          seed=None, seed_note="no random numbers are drawn in P1; r0's info-gap study used seed "
                                               f"{load(R0 / 'info_gap.json')['inputs']['seed']}",
                          python=platform.python_version(), numpy=np.__version__, pyyaml=yaml.__version__,
                          matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()},
                          sha256={k: sha256(p) for k, p in files.items()}),
           "evidence_class": EVIDENCE_CLASS, "baseline": str(R0.relative_to(REPO))}
    log(f"commit {tree['commit']}, clean tree; r0 design {res['inputs']['sha256']['r0_design'][:12]}")

    # 0. r0 sized again; stop unless it is r0
    rebuilt = rebuild_r0()
    res["reproduction"] = rebuilt["reproduction"]
    if rebuilt["reproduction"]["different"] or rebuilt["reproduction"]["added"] or rebuilt["reproduction"]["removed"]:
        res["stopped"] = "the design sized again is not r0; nothing else was run"
        _write(out, res, t0, own)
        raise SystemExit(res["stopped"])
    d, ig, cell = load(R0 / "design_pusher.json"), load(R0 / "info_gap.json"), load(R0 / "cell_result.json")
    L, entries = uav.load_ledger(R0 / "ledger.yaml")
    judge = yaml.safe_load(JUDGEMENTS.read_text())
    log(f"r0 sized again: {rebuilt['reproduction']['n_compared']} fields, largest relative difference "
        f"{rebuilt['reproduction']['max_relative_difference']:.1e}")

    # concept record first: the compliance matrix quotes the rubber engine's power (R3)
    res["concepts"] = concept_record(rebuilt, out)
    sc = res["concepts"]["scoring"]
    log(f"concepts: tractor {res['concepts']['designs']['tractor']['W0_lb']:.1f} lb, rubber pusher "
        f"{res['concepts']['designs']['pusher_rubber']['W0_lb']:.1f} lb; score {sc['score']}; reversed {sc['reversed']}")

    # 1 to 7: the Stage 1 outputs that are read from r0 or recomputed on the rebuilt design
    matrix = compliance_matrix(rebuilt["compliance_rows"], d, ig, res["concepts"]["designs"]["pusher_rubber"]["bhp"])
    named = {r for row in matrix for r in row["requirement_id"].split("/")}
    res["compliance"] = {"rows": matrix, "blank_cells": blank_cells(matrix),
                         "requirements_missing": sorted({f"R{i}" for i in range(1, 20)} - named)}
    res["weight_statement"] = weight_statement(d)
    res["empty_weight"] = empty_weight_explanation(d, rebuilt["s_exposed_ft2"], L)
    cd_rows, limits = stage1.constraint_diagram(rebuilt["analysis"]["design"], rebuilt["analysis"]["design"]["ledger_used"],
                                                rs.as_is_engine())
    res["constraint"] = {"rows": cd_rows, "limits": limits}
    res["carpet"] = {"source": str(CURVE.relative_to(REPO)), "rows": carpet_rows(load(CURVE))}
    pts = vn_points(d)
    res["vn"] = {"points": pts, "max_difference": vn_difference(pts, d)}
    log(f"compliance {len(matrix)} rows, {len(res['compliance']['blank_cells'])} blank cells; weight statement "
        f"{res['weight_statement']['difference_lb']:+.2e} lb from the record")

    # trades, decomposition, climb at the worst corner
    built = info_gap.Built(R0 / "design_pusher.json")
    res["sized_loiter_h"] = rebuilt["row"]["L_sized_h"]
    res["nominal_as_built"] = as_built(built, {})
    res["trades"] = trades(built, d, rebuilt["ledger_sizing"], entries["composite_factor"]["band"])
    log(f"trades: nominal re-sized W0 {res['trades']['resized']['nominal']['W0_lb']:.3f} lb, built aircraft "
        f"{res['nominal_as_built']['hours_on_station']:.4f} h on station")
    res["decomposition"] = decompose(built, cell, entries, res["sized_loiter_h"])
    res["climb_check"] = climb_check(built, res["decomposition"])
    for k, s in res["climb_check"]["states"].items():
        log(f"climb, {k}: Stage 1 speed {s['stage1_climb_speed_kt']:.1f} kt, "
            f"{s['against_stall_at_altitude']['end_of_climb_weight']['over_stall']:.3f} of the stall speed at the top; "
            f"integrated {s['integrated_fuel_lb']:.1f} lb against {s['two_point_fuel_lb']:.1f} lb")

    # ledger: band audit, out-of-calibration list, risk list
    audit = band_audit(judge["band_audit"], entries, built, rebuilt["ledger_sizing"], res["nominal_as_built"],
                       cell["modes"]["endurance"]["worst_at_h1"])
    res["ledger"] = {"audit": audit, "problems": check_band_audit(judge["band_audit"], entries)}
    res["out_of_calibration"] = {"entries": judge["out_of_calibration"],
                                 "problems": check_out_of_calibration(judge["out_of_calibration"])}
    res["risks"] = {"entries": judge["risks"], "problems": check_risks(judge["risks"])}
    res["payload_bay"] = payload_bay(d, L)
    log(f"band audit {audit['by_class']}; payload bay {res['payload_bay']['payload_volume_ft3']:.2f} ft^3 of "
        f"{res['payload_bay']['free_volume_ft3']:.1f} ft^3 free")

    # 10. test report
    res["equations"] = equation_table()
    if with_tests:
        res["tests"] = run_tests(out)
        log(f"pytest: {res['tests']['summary_line']} (exit {res['tests']['exit_code']})")
    res["acceptance"] = acceptance_rows(res)
    _write(out, res, t0, own)
    log(", ".join(f"row {a['row']} {a['verdict']}" for a in res["acceptance"]) + f" ({time.time() - t0:.0f} s)")
    return res


def _write(out, res, t0, own):
    """OUT/p1.json, with the state of the tree at the end of the run next to the one at its start."""
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == res["inputs"]["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p1.json").write_text(json.dumps(info_gap._json_safe(res), indent=1, default=float))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the figures of the report (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and figures from OUT/p1.json and r0")
    ap.add_argument("--no-tests", action="store_true", help="skip the recorded pytest run (for a trial run only)")
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
        run(out, log, with_tests=not a.no_tests)
    if a.report:
        from prelim import p1_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p1_report.write_figures(out, figures)
        report.write_text(p1_report.report_text(out))


if __name__ == "__main__":
    main()

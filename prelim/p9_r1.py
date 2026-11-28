"""Preliminary design P9: the closing re-record r1 and its robustness (spec P9; decisions PD-25, PD-26, PD-27).

Not yet Fable-reviewed (rulings PD-22 and PD-25).

    python -m prelim.p9_r1 inputs --out runs/task12/pd/2026-11-28/p9/pass0          # r1's inputs at r0's sizes
    python -m prelim.p9_r1 ledger --inputs runs/task12/pd/2026-11-28/p9/pass0/inputs.json   # data/task12/ledger_r1.yaml
    python -m prelim.p9_r1 size --out runs/task12/pd/2026-11-28/p9/pass1            # r1 sized, its inputs measured again
    (then prelim/p9_study.py for the checks and re-runs on r1, prelim/p9_report.py for the summary and the report)

What it does. The findings of P0 to P8 (data/task12/pd_p9_findings.yaml) enter r1 as entries of a ledger copy,
data/task12/ledger_r1.yaml, written here from the Gate B ledger (PD-26 item 1). What the loft measures (wetted areas,
tank volume, the sponson that holds the gear, the aft-fuselage extension and its skin, Multhopp's fuselage term) is
measured on the r1 layout: first at r0's sizes with the PD-21 layout (`inputs`), then on r1 itself after each sizing
(`size`), until it no longer changes (PD-26 item 2). The sizing is measurement/robust_sizing.py's procedure on the one
cell W/S 13, A 8 (PD-26 item 7). Nothing is tuned: a failed row is written down as failed. Units: ft, lb, s, rad unless a name says otherwise.
"""
import argparse
import copy
import hashlib
import json
import math
import platform
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import scipy
import yaml
from scipy.optimize import brentq

from conceptual import uav
from geometry3d import aircraft as ac
from geometry3d import gates
from geometry3d.surfaces import Ellipsoid
from measurement import info_gap
from measurement import robust_sizing as rs
from prelim import p3_loft as p3
from prelim import p4_balance as p4
from prelim import p4_methods as m
from prelim import p4b_trade as p4b
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
REVIEW = "Not yet Fable-reviewed (rulings PD-22 and PD-25)"
R0 = REPO / "runs/task12/pd/2026-11-27/p0/r0"
FINDINGS = REPO / "data/task12/pd_p9_findings.yaml"
LEDGER_GATE_B = REPO / "data/task12/ledger.yaml"
LEDGER_R1 = REPO / "data/task12/ledger_r1.yaml"
ARRANGEMENT = REPO / "data/task12/pd_p3_arrangement.yaml"
RESIZE_CURVE = REPO / "runs/task12/stage3/2026-11-26/m250_bands_resize/curve.json"
P2_RECORD = REPO / "runs/task12/pd/2026-11-27/p2b/p2.json"
P4B_RECORD = REPO / "runs/task12/pd/2026-11-28/p4b/p4b.json"
P6_RECORD = REPO / "runs/task12/pd/2026-11-27/p6/p6.json"
POWER, W_S, ASPECT, H_T = 450.0, 13.0, 8.0, 1.05          # the cell and the guarantee target of ruling B-2b
TOL_RATIO, TOL_LENGTH_FT, MAX_PASSES = 0.005, 0.02, 3      # PD-26 item 2: when the loft's inputs count as unchanged
STUDY_PROCESSES = 4                                        # every job of info_gap.study carries its own seed
TOL_STEP_W0 = 0.005                                        # spec P9 acceptance 4: step doubling changes W0 by < 0.5 %
SPONSON_TOL = 0.001                                        # PD-27: bisection on the sponson scale
CD0_STEP = 0.10                                            # PD-26 item 9: +-10 % on the parasite drag
FAIRED_SECTION_CL_MAX = 1.43                               # PD-26 item 10 (P2 source note: about 1.43, by eye)
# the entries of ledger_r1.yaml that a loft measurement gives (ratio or length), and how each is compared
MEASURED = {"loft_wetted_factor_wing": "ratio", "loft_wetted_factor_fuselage": "ratio",
            "loft_wetted_factor_horizontal_tail": "ratio", "loft_wetted_factor_vertical_tail": "ratio",
            "loft_wetted_factor_sponsons": "ratio", "tank_volume_factor": "ratio", "sponson_size_factor": "ratio",
            "fuselage_cm_alpha_factor": "ratio", "fuselage_extension_ft": "length", "fuselage_added_skin_ft2": "ratio"}
COMPONENTS = ("wing", "fuselage", "horizontal_tail", "vertical_tail", "sponsons")


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pick(data, key):
    """The value at a dotted key; a part that is a number indexes a list."""
    for part in key.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def findings():
    return yaml.safe_load(FINDINGS.read_text())["findings"]


def finding(fid):
    return next(f for f in findings() if f["id"] == fid)


# ---- the r1 ledger (PD-26 item 1) ----------------------------------------------------------------------------------
def fixed_entries():
    """r1's ledger entries that come straight from a package record (no loft measurement in P9)."""
    f = {x["id"]: x for x in findings()}

    def src(fid, extra=""):
        x = f[fid]
        return f"P9 finding {fid} (decision PD-26): {x['record']} key {x['key']}{extra}"
    return {
        "climb_model": {"value": "integrated", "units": "-", "confidence": "definition",
                        "source": src("P1-1", "; the mission's climb leg in 1,000 ft steps at each altitude's own best-climb speed (conceptual/uav.integrated_climb); two_point is Stage 1's (19.8)")},
        "station_payload_ft": {"value": f["P3-7"]["value"], "units": "ft", "confidence": "computed",
                               "source": src("P3-7", "; payload mass at the volume centre of the P3 payload bay (PD-19), ft from the nose")},
        "station_avionics_ft": {"value": f["P3-8"]["value"], "units": "ft", "confidence": "computed",
                                "source": src("P3-8", "; avionics mass at the centre of the P3 avionics box (PD-19), ft from the nose")},
        "tail_trailing_edges": {"value": "straight", "units": "-", "confidence": "definition",
                                "source": src("P4b-1", "; both tails with straight trailing edges and the taper on the leading edge (PD-20 item 1, PD-21)")},
        "shaft_lb_per_ft": {"value": f["P4b-4"]["value"], "units": "lb/ft", "confidence": "judgement",
                            "source": src("P4b-4", "; PD-21's assumed shaft weight; PD-21 gives it a band of 2 to 10 lb/ft, which is not an owner-accepted band and is not acting here (no info-gap variable)")},
    }


def measured_entry(name, value, where):
    """A ledger entry for a value measured by P9 on the loft of the r1 layout; where: the record and key."""
    units = {"fuselage_extension_ft": "ft", "fuselage_added_skin_ft2": "ft^2"}.get(name, "-")
    what = {"tank_volume_factor": "usable tank volume of the loft over Stage 1's box (P3 finding P3-6)",
            "sponson_size_factor": "scale of the sponson that holds the retracted main gear (PD-27, P3 finding P3-9)",
            "fuselage_cm_alpha_factor": "Multhopp's fuselage moment slope on the loft over (16.22)'s (P4 finding P4-1)",
            "fuselage_extension_ft": "aft-fuselage extension behind the Table 6.3 body, 1.0 ft between the tails and the propeller plane (PD-21)",
            "fuselage_added_skin_ft2": "loft skin the extension adds (PD-21, P4b's route for (15.49))"}.get(
        name, f"loft wetted area over Stage 1's for the {name.removeprefix('loft_wetted_factor_').replace('_', ' ')} (P3 gate 3)")
    return {"value": value, "units": units, "confidence": "computed", "source": f"P9 (decision PD-26): {what}; measured in {where}"}


def entry_line(name, q):
    """One ledger line in the Gate B ledger's flow style."""
    v = q["value"] if isinstance(q["value"], str) else repr(float(q["value"]))
    units = q["units"] if q["units"] not in ("-", "ft^2") else f'"{q["units"]}"'
    source = q["source"].replace('"', "'")
    return f'  {name + ":":<24} {{value: {v}, units: {units}, confidence: {q["confidence"]}, source: "{source}"}}'


def change_value(text, name, value, note):
    """The ledger text with the value of one entry replaced and a note added to its source."""
    pat = re.compile(rf'^(\s*{name}:\s*\{{value: )[-0-9.e]+(,.*?source: ")(.*?)("\}}\s*)$', re.MULTILINE)
    new, n = pat.subn(lambda g: f"{g.group(1)}{value!r}{g.group(2)}{g.group(3)}; {note}{g.group(4)}", text)
    if n != 1:
        raise ValueError(f"{name}: not found once in the ledger")
    return new


def ledger_r1_text(inputs, inputs_path):
    """data/task12/ledger_r1.yaml: the Gate B ledger, airfoil_cl_max and airfoil_cm0 at P2's values (bands as they
    are), and the r1 entries: the fixed ones and those measured on the loft (inputs: {name: value}, from inputs_path)."""
    text = LEDGER_GATE_B.read_text()
    f = {x["id"]: x for x in findings()}
    for name, fid in (("airfoil_cl_max", "P2-1"), ("airfoil_cm0", "P2-3")):
        text = change_value(text, name, float(f[fid]["value"]),
                            f"r1: P2's measured value, {f[fid]['record']} key {f[fid]['key']} (P9 finding {fid}, decision PD-26); the band is unchanged")
    path = Path(inputs_path)
    where = str(path.relative_to(REPO)) if path.is_absolute() and path.is_relative_to(REPO) else str(path)
    lines = ["  # --- preliminary design r1 (P9, decision PD-26): entries without a band, so not info-gap variables ---"]
    for name, q in fixed_entries().items():
        lines.append(entry_line(name, q))
    for name in MEASURED:
        lines.append(entry_line(name, measured_entry(name, float(inputs[name]), f"{where} key values.{name}")))
    head = ("# r1 ledger of Task 12 preliminary design P9 (decision PD-26). Written by `python -m prelim.p9_r1 ledger` from\n"
            "# data/task12/ledger.yaml (the Gate B ledger, not edited), data/task12/pd_p9_findings.yaml and the loft\n"
            f"# measurement {where}. Do not edit by hand: tests/task12_pd/test_p9_r1.py writes it again and compares.\n")
    return head + text.rstrip("\n") + "\n" + "\n".join(lines) + "\n"


@contextmanager
def ledger_in_use(path):
    """Stage 1 and the robust sizing read `path` as the ledger while the block runs (uav.LEDGER), with the caches of
    robust_sizing that hold ledger values cleared on entry and on exit."""
    old = uav.LEDGER

    def clear():
        for f in (rs._nominal_tuple, rs._variables, rs._engine, rs._raw):
            f.cache_clear()
    uav.LEDGER = Path(path)
    clear()
    try:
        yield
    finally:
        uav.LEDGER = old
        clear()


# ---- the loft of a record ------------------------------------------------------------------------------------------
def loft_record(d, L):
    """The design record as geometry3d/aircraft.build reads it for the loft: the turret stays at the payload station of
    Stage 1's rule (r0's drawing, PD-19), whatever station the payload mass has."""
    d1 = copy.deepcopy(d)
    d1["stations"]["payload"]["x"] = L["station_payload_pusher"] * d["fuselage"]["length"]
    return d1


def loft(d, L, A, extension):
    """The loft of a record with the aft fuselage lengthened by `extension` (P4b's lengthened_body: the last control
    station moved aft) and the spinner and propeller plane moved with it, as prelim/p4b_trade.row9_on_the_loft does."""
    model = ac.build(loft_record(d, L), L, A)
    if extension > 0.0:
        model["fuselage"] = p4b.lengthened_body(model["fuselage"], extension)
        s = model["spinner"]
        model["spinner"] = Ellipsoid((s.centre[0] + extension, 0.0, 0.0), s.a, s.b, s.c)
        model["propeller"]["x"] += extension
    return model


def with_sponson(d, scale):
    """The record with its sponson length and depth multiplied by `scale` (the loft reads them from gear_track)."""
    d1 = copy.deepcopy(d)
    gt = d1["layout"]["gear_track"]
    gt["sponson_length_ft"] *= scale
    gt["sponson_depth_ft"] *= scale
    return d1


def gear_clearance_in(d, L, A, extension):
    """The least clearance (in) of P3's main-gear boxes (leg, leg, wheel, both sides) to the skin of their sponson."""
    model = loft(d, L, A, extension)
    boxes, _ = ac.arrangement(model, loft_record(d, L), L, A)
    return min(12.0 * ac.clearance_margin(model[b["in"]], b) for n, b in boxes.items() if n.startswith("main_gear_"))


def sponson_scale(d, L, A, extension, hi=2.0):
    """PD-27: the least scale k (to SPONSON_TOL) of Stage 1's own sponson (the record's divided by the record's
    sponson_size_factor) at which every main-gear box is inside the sponson with P3's box clearance. Returns k and the
    clearance there."""
    need = ac.val(A["arrangement"]["box_clearance_in"])
    base = with_sponson(d, 1.0 / L.get("sponson_size_factor", 1.0))
    ok = lambda k: gear_clearance_in(with_sponson(base, k), L, A, extension) >= need - 1e-9
    lo = 1.0
    if ok(lo):
        return {"scale": lo, "clearance_in": gear_clearance_in(base, L, A, extension), "required_in": need, "bracket": [lo, lo]}
    if not ok(hi):
        raise ValueError(f"no sponson up to {hi} times Stage 1's holds the gear")
    while hi - lo > SPONSON_TOL:
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if ok(mid) else (mid, hi)
    return {"scale": hi, "clearance_in": gear_clearance_in(with_sponson(base, hi), L, A, extension), "required_in": need,
            "bracket": [lo, hi], "stage1_sponson_ft": {"length": base["layout"]["gear_track"]["sponson_length_ft"],
                                                         "depth": base["layout"]["gear_track"]["sponson_depth_ft"]}}


def area_and_tank_factors(d, L, A, extension):
    """Loft wetted area over Stage 1's (7.11)/(7.12) area per drag component (P3 gate 3 on this loft) and the loft's
    usable tank volume over Stage 1's box (P3 gate 4). Stage 1's own areas and box are the record's divided by the
    record's factors, so a record of r1 gives the same kind of ratio as r0's."""
    model = loft(d, L, A, extension)
    parts = ac.meshes(model)
    g3 = gates.gate3_wetted(model, parts, loft_record(d, L), L)
    g4 = gates.gate4_volumes(model, parts, loft_record(d, L), L, A)
    out = {}
    for k in COMPONENTS:
        r = g3["components"][k]
        out["loft_wetted_factor_" + k] = r["loft_wetted_ft2"] / r["stage1_ft2"]
    box = g4["tank"]["stage1_claim_ft3"] / L.get("tank_volume_factor", 1.0)
    out["tank_volume_factor"] = g4["tank"]["usable_ft3"] / box
    return out, {"gate3": g3, "gate4": g4, "model": model, "parts": parts}


def added_skin(d, L, A, extension):
    """Skin the extension adds to the loft's fuselage (ft^2), as prelim/p4b_trade.extended measures it."""
    body = ac.build(loft_record(d, L), L, A)["fuselage"]
    return p4b.skin_area(p4b.lengthened_body(body, extension)) - p4b.skin_area(body)


# ---- P4's route on a record (the wing, the tail clear of the disc, the balance) -----------------------------------
def p4_context(d, L, A, extension, model):
    """P4's context for a record of the r1 layout: the record with its fuselage length taken to the end of the longer
    body (P4's propeller clearance reads it), the loft's fuselage, the tanks, P4's sources and choices, P2's section
    moment as the record's ledger has it, P6's blade (power-on points, no verdict), and P3's gear-up stations of this
    loft."""
    d4 = copy.deepcopy(d)
    d4["fuselage"]["length"] = d["fuselage"]["length"] + extension
    choices = m.load_yaml(m.CHOICES)
    g4 = gates.gate4_volumes(model, ac.meshes(model), loft_record(d, L), L, A)
    moved = p3.moved_masses(loft_record(d, L), g4)
    for r in moved["moved"]:                      # the P3 stations as the ledger carries them
        r["station_p3_ft"] = L["station_payload_ft"] if r["item"] == "payload" else L["station_avionics_ft"]
    return {"d": d4, "L": L, "A": A, "p3": {"moved_masses": moved}, "p6": load(P6_RECORD), "src": m.load_yaml(m.SOURCES),
            "choices": choices, "body": model["fuselage"], "model": model, "propeller_plane_x": model["propeller"]["x"],
            "tanks": m.tanks(d4, L, A, choices), "cm0_p2": L["airfoil_cm0"]}


def p4_base_layout(c):
    """The record's own layout as P4 takes it, the tails with straight trailing edges (PD-21) at the record's arm."""
    lay = m.base_layout(c["d"], c["p3"])
    lay["tail_te_straight"] = c["L"].get("tail_trailing_edges", "tapered") == "straight"
    return lay


def place_wing(c, lay0, span=3.0):
    """P4's placement (prelim/p4_methods.solve_r1 with the tails kept on the wing at their arm): the wing leading edge
    at which the mean of the full-fuel and empty-fuel static margins (payload on, gear up, nominal empty weight,
    Multhopp's term, power off) is the middle of R13, the main wheels by the tipback rule. Searched within `span` ft
    ahead of and behind the record's wing (solve_r1 looks aft only)."""
    d, L, tk, ch = c["d"], c["L"], c["tanks"], c["choices"]
    mac, target = d["wing"]["mac"], 0.5 * (m.SM_MIN + m.SM_MAX)

    def build(x_le):
        lay = dict(copy.deepcopy(lay0), x_le=x_le)
        lay["x_main"] = lay0["x_main"] + x_le - lay0["x_le"]
        m.place_main_gear(d, L, lay, tk, ch)
        st = m.stability(d, L, lay, c["body"], c["src"])
        full, empty = m.cg_ends(d, L, lay, tk, ch)
        return lay, st, (st["x_np_power_off_ft"] - 0.5 * (full + empty)) / mac
    x_le = brentq(lambda x: build(x)[2] - target, lay0["x_le"] - span, lay0["x_le"] + span, xtol=1e-8)
    lay, st, sm = build(x_le)
    st["mean_static_margin"] = sm
    return lay, st


def p4_route(d, L, A, extension, log=print):
    """P4's route on a record of the r1 layout: the wing placed, rows 1 to 4 of P4 (prelim/p4_balance.evaluate),
    P4b's payload-off ballast, the extension that leaves the P4 clearance between the tails and the propeller plane
    with the wing where P4 puts it, and Multhopp's fuselage term over the record's (16.22)."""
    model = loft(d, L, A, extension)
    c = p4_context(d, L, A, extension, model)
    lay0 = p4_base_layout(c)
    lay, st = place_wing(c, lay0)
    e = p4.evaluate(c, lay, "r1, P4's route", log)
    cm_w = m.wing_moment(c["cm0_p2"], d["A"])
    clearance = m.val(c["choices"]["r1"]["propeller_clearance_ft"])
    plane0 = c["propeller_plane_x"] - extension                   # the propeller plane of the unextended body
    rear = m.tail_rearmost(c["d"], L, lay)
    needed = max(0.0, max(rear.values()) + clearance - plane0)
    stage1_cma = d["layout"]["Cma_fus"] / L.get("fuselage_cm_alpha_factor", 1.0)
    return {"layout": lay, "stability": st, "evaluation": e, "context": c,
            "ballast": p4b.ballast_for_payload_off(c, lay, e, cm_w),
            "extension_needed_ft": needed, "tail_rearmost_ft": rear, "propeller_plane_unextended_ft": plane0,
            "clearance_ft": clearance, "multhopp_over_16_22": e["neutral_point"]["Cma_fus_multhopp_per_rad"] / stage1_cma,
            "stage1_16_22_per_rad": stage1_cma}


def measure_inputs(d, L, A, extension, multhopp_factor, log=print):
    """Every loft-measured entry of r1's ledger on a record of the r1 layout at the given extension: the sponson scale
    first (PD-27), then the areas and tank volume on the loft with that sponson, and the added skin."""
    sp_ = sponson_scale(d, L, A, extension)
    log(f"sponson scale {sp_['scale']:.3f} (least main-gear clearance {sp_['clearance_in']:.2f} in)")
    d_k = with_sponson(d, sp_["scale"] / L.get("sponson_size_factor", 1.0))
    factors, parts = area_and_tank_factors(d_k, L, A, extension)
    values = dict(factors, sponson_size_factor=sp_["scale"], fuselage_extension_ft=extension,
                  fuselage_added_skin_ft2=added_skin(d, L, A, extension), fuselage_cm_alpha_factor=multhopp_factor)
    log("factors: " + ", ".join(f"{k} {v:.4f}" for k, v in values.items()))
    return values, {"sponson": sp_, "gate3": parts["gate3"], "gate4_tank": parts["gate4"]["tank"]}


def reference_record():
    """r0's record with the PD-21 layout (P4b's chosen layout: wing, wheels, tails at r0's arm and areas with straight
    trailing edges) for the first measurement, and that layout's extension and Multhopp term from P4b's record."""
    d0 = load(R0 / "design_pusher.json")
    L0 = uav.load_ledger(R0 / "ledger.yaml")[0]
    rec = load(P4B_RECORD)
    chosen = rec["candidates"][rec["selection"]["chosen"]]
    lay = chosen["layout"]
    d = p4.record_with_layout(d0, L0, lay)
    ext = chosen["measures"]["extension_ft"]
    np_ = chosen["evaluation"]["neutral_point"]
    return d, L0, ext, np_["Cma_fus_multhopp_per_rad"] / d0["layout"]["Cma_fus"], {
        "record": str(P4B_RECORD.relative_to(REPO)), "chosen": rec["selection"]["chosen"],
        "extension_key": f"candidates.{rec['selection']['chosen']}.measures.extension_ft",
        "multhopp_key": f"candidates.{rec['selection']['chosen']}.evaluation.neutral_point.Cma_fus_multhopp_per_rad",
        "stage1_16_22_key": "runs/task12/pd/2026-11-27/p0/r0/design_pusher.json layout.Cma_fus"}


def sponson_position_sensitivity(d, L, A, extension, fractions=(0.2, 0.4)):
    """A sensitivity, not the choice (PD-27 keeps P3's 0.3): the sponson scale with its centre placed another share of
    its length ahead of the main wheel."""
    out = {}
    for f in fractions:
        A2 = copy.deepcopy(A)
        A2["loft"]["sponson_centre_ahead_of_main_wheel_over_length"] = f
        try:
            out[f"{f:g}"] = sponson_scale(d, L, A2, extension)["scale"]
        except ValueError as e:
            out[f"{f:g}"] = str(e)
    return out


def compare_inputs(used, measured):
    """Each measured entry against the value r1 was sized with: relative for ratios, absolute (ft) for lengths."""
    rows, ok = {}, True
    for name, kind in MEASURED.items():
        u, v = used[name], measured[name]
        diff = v - u if kind == "length" else v / u - 1.0
        tol = TOL_LENGTH_FT if kind == "length" else TOL_RATIO
        rows[name] = {"used": u, "measured": v, "difference": diff, "kind": kind, "tolerance": tol, "within": abs(diff) <= tol}
        ok = ok and rows[name]["within"]
    return rows, ok


# ---- the r1 sizing (PD-26 item 7) -------------------------------------------------------------------------------
def start_corner_sets():
    """The final corner sets of the Gate B re-size at 450 shp, h_T 1.05, each corner put at the harmful ends of U(h_T)
    of the ledger in use (robust_sizing.scaled_corner keeps the directions of the recorded corner)."""
    cell = load(RESIZE_CURVE)["per_P"][f"{POWER:g}"][f"{H_T:.2f}"]
    sets = cell["corner_sets"]
    return ([{"label": c["label"] + " (r1 ledger)", "moved": rs.scaled_corner(c["moved"], H_T)} for c in sets["endurance"]],
            [{"label": c["label"] + " (r1 ledger)", "moved": rs.scaled_corner(c["moved"], H_T)} for c in sets["cliff"]])


def size_cell(folder, log=print):
    """measurement/robust_sizing.run_target's procedure on the one cell (W/S 13, A 8, 450 shp, per-design V_C) from
    the start corner sets: the L_sized bisection against the sets, the mode searches at h_T on the design, a violating
    worst point added to its set, at most robust_sizing.MAX_CURVE_ITER iterations. Writes each iteration's record and
    the final one in folder/r1. Returns the result (design None if the cell has no compliant design)."""
    need = uav.load_ledger()[0]["r5_robust_hours"]
    E, C = start_corner_sets()
    cache, iterations, final = {}, [], None
    for it in range(1, rs.MAX_CURVE_ITER + 1):
        t0 = time.time()
        rows, best = rs.curve_search(POWER, E, C, need, cache, (W_S,), (ASPECT,), log=log, vc_rule=rs.VC_RULE)
        rec_it = {"iteration": it, "n_endurance_corners": len(E), "n_cliff_corners": len(C), "candidates": rows,
                  "winner": rs.summary_of(best) if best else None}
        iterations.append(rec_it)
        if best is None:
            log(f"iteration {it}: no compliant design: {rows[0]['status'] or rows[0]['failed']}")
            final = None
            break
        rec = cache[(POWER, W_S, ASPECT, round(best["L_sized_h"], 6), rs.VC_RULE)][0][2]
        path = rs.write_record_rec(best, folder / f"iteration{it}", rec)
        worst = rs.mode_worst_at(path, need, H_T)
        violating = [k for k in ("endurance", "cliff") if rs.violates_rec(k, worst[k], need)]
        added = [k for k, sets, lab in (("endurance", E, "E"), ("cliff", C, "C"))
                 if k in violating and rs.add_corner(sets, f"{lab}{len(sets) + 1}(r1 it{it})", worst[k]["moved"])]
        rec_it.update(worst_at_target=worst, violating_modes=violating, corners_added=added, converged=not added,
                      search_s=time.time() - t0)
        log(f"iteration {it}: L_sized {best['L_sized_h']:.4f} h, W0 {best['W0_lb']:.1f} lb, worst endurance at h_T "
            f"{worst['endurance']['hours']:.3f} h, worst cliff ratio {worst['cliff']['transit_ratio']:.4f}, added {added} "
            f"({time.time() - t0:.0f} s)")
        final = (it, best, path)
        if not added:
            break
    out = {"need_h": need, "h_T": H_T, "cell": {"P_hp": POWER, "W_S": W_S, "A": ASPECT}, "iterations": iterations,
           "corner_sets": {"endurance": E, "cliff": C}}
    if final is None:
        return dict(out, design=None)
    it, best, path = final
    r1 = folder / "r1"
    r1.mkdir(parents=True, exist_ok=True)
    for f in ("design_pusher.json", "ledger.yaml", rs.engine_table_file(), "robust_candidate.json"):
        shutil.copyfile(path.parent / f, r1 / f)
    return dict(out, design=rs.summary_of(best), final_iteration=it, converged=iterations[-1]["converged"],
                record=str((r1 / "design_pusher.json").relative_to(REPO)))


# ---- the commands -------------------------------------------------------------------------------------------------
def start(out, what):
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit(f"P9 {what} starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    return own, dict(tree, command="python -m prelim.p9_r1 " + " ".join(sys.argv[1:]), python=platform.python_version(),
                     numpy=np.__version__, scipy=scipy.__version__, pyyaml=yaml.__version__, review=REVIEW)


def finish(out, own, res, name, t0):
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == res["inputs"]["commit"]
    res["runtime_s"] = time.time() - t0
    (out / name).write_text(json.dumps(plain(res), indent=1))


def plain(o):
    if isinstance(o, dict):
        return {str(k): plain(v) for k, v in o.items() if k not in ("context", "model", "parts")}
    if isinstance(o, (list, tuple)):
        return [plain(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if hasattr(o, "__dataclass_fields__"):
        return {k: getattr(o, k) for k in ("area", "aspect_ratio", "taper", "span", "root_chord", "tip_chord", "mac", "mac_y")}
    if isinstance(o, float) and not math.isfinite(o):
        return str(o)
    return o


def cmd_inputs(out, log):
    """Pass 0: r1's loft inputs measured on r0's sizes with the PD-21 layout."""
    t0 = time.time()
    own, inputs = start(out, "inputs")
    A = yaml.safe_load(ARRANGEMENT.read_text())
    d, L0, ext, mult, src = reference_record()
    L = dict(L0, **{k: v["value"] for k, v in fixed_entries().items()})
    log(f"reference: r0 with P4b's layout {src['chosen']}, extension {ext:.4f} ft, Multhopp over (16.22) {mult:.4f}")
    values, detail = measure_inputs(d, L, A, ext, mult, log)
    detail["sponson_position_sensitivity"] = sponson_position_sensitivity(d, L, A, ext)
    res = {"inputs": dict(inputs, files={k: str(p.relative_to(REPO)) for k, p in (("r0_design", R0 / "design_pusher.json"),
                                                                                   ("p4b", P4B_RECORD), ("arrangement", ARRANGEMENT))}),
           "pass": 0, "reference": dict(src, what="r0's sizes with the PD-21 layout"), "values": values, "detail": detail}
    finish(out, own, res, "inputs.json", t0)
    log(f"inputs written ({time.time() - t0:.0f} s)")


def cmd_ledger(inputs_path):
    values = load(inputs_path)["values"]
    LEDGER_R1.write_text(ledger_r1_text(values, inputs_path))
    uav.load_ledger(LEDGER_R1)                      # the loader's checks (sources, bands of assumed entries)
    print(f"wrote {LEDGER_R1.relative_to(REPO)}")


def cmd_size(out, log):
    """One pass: r1 sized with data/task12/ledger_r1.yaml, then its loft inputs measured on r1 itself."""
    t0 = time.time()
    own, inputs = start(out, "size")
    rs.use_engine_as_is(True)
    with ledger_in_use(LEDGER_R1):
        res = {"inputs": dict(inputs, ledger=str(LEDGER_R1.relative_to(REPO)), ledger_sha256=sha256(LEDGER_R1),
                              seed=info_gap.SEED, n_samples=info_gap.N_SAMPLES), "sizing": size_cell(out, log)}
        if res["sizing"]["design"] is not None:
            path = REPO / res["sizing"]["record"]
            d, L = load(path), uav.load_ledger(path.parent / "ledger.yaml")[0]
            A = yaml.safe_load(ARRANGEMENT.read_text())
            route = p4_route(d, L, A, L["fuselage_extension_ft"], log)
            log(f"P4's route on r1: wing leading edge {route['layout']['x_le']:.4f} ft (Stage 1 {d['layout']['x_le']:.4f}), "
                f"extension needed {route['extension_needed_ft']:.4f} ft (used {L['fuselage_extension_ft']:.4f}), "
                f"Multhopp over (16.22) {route['multhopp_over_16_22']:.4f}")
            values, detail = measure_inputs(d, L, A, route["extension_needed_ft"], route["multhopp_over_16_22"], log)
            rows, ok = compare_inputs({k: L[k] for k in MEASURED}, values)
            res.update(values=values, detail=detail, comparison=rows, inputs_unchanged=ok,
                       p4_route={"x_le_ft": route["layout"]["x_le"], "x_main_ft": route["layout"]["x_main"],
                                 "extension_needed_ft": route["extension_needed_ft"], "tail_rearmost_ft": route["tail_rearmost_ft"],
                                 "multhopp_over_16_22": route["multhopp_over_16_22"]})
            log("inputs unchanged within tolerance" if ok else "inputs changed: " +
                ", ".join(k for k, r in rows.items() if not r["within"]))
    finish(out, own, res, "pass.json", t0)
    log(f"pass written ({time.time() - t0:.0f} s)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("inputs", "ledger", "size"))
    ap.add_argument("--out")
    ap.add_argument("--inputs")
    a = ap.parse_args(argv)
    if a.command == "ledger":
        return cmd_ledger(REPO / a.inputs)
    out = (REPO / a.out).resolve() if a.out else None
    t0, lines = time.time(), []

    def log(msg):
        lines.append(f"[{time.time() - t0:7.0f} s] {msg}")
        print(lines[-1], flush=True)
        if out is not None and out.exists():
            (out / f"{a.command}.log").write_text("\n".join(lines) + "\n")
    if a.command == "inputs":
        cmd_inputs(out, log)
    elif a.command == "size":
        cmd_size(out, log)


if __name__ == "__main__":
    main()

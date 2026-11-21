"""Task 12 Stage 1 runner: the conceptual design package with Raymer's methods.

    python -m conceptual.stage1 --out runs/task12/stage1/<date>

Steps follow docs/specs/task12_drone_conceptual_design.md section 4: first-pass sizing (step 3),
refined sizing over a wing-loading by aspect-ratio grid for both concepts, first with a rubber
engine and then with the fixed engine chosen at Gate A round 1 (steps 5 and 8), the horizontal
tail enlarged where nose rotation needs it (p. 432-433), layout and analysis of both concepts
(steps 6, 7), the concept scoring (step 2), the constraint diagram (step 4), the alternative
engines and one-at-a-time trades. Every table is written next to the ledger it used.
"""
import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
from pathlib import Path

import numpy as np
import yaml

from conceptual import constraints, sizing, uav
from conceptual import raymer_aero as aero
from conceptual import raymer_loads as loads
from conceptual import raymer_performance as perf
from conceptual.engine_model import TableEngine
from conceptual.units import KT, NM, RHO0, isa

REPO = uav.LEDGER.parents[2]
ENGINES = REPO / "data" / "task12" / "engines.yaml"
TP100_TABLE = REPO / "data" / "task12" / "tp100_table.json"
WS_GRID = [8.0 + i for i in range(15)]          # 8 to 22 lb/ft^2
A_GRID = [6.0 + i for i in range(17)]           # 6 to 22
CHOSEN_ENGINE = "PBS_TP100"                     # Gate A round 1: a small production turboprop
FROZEN_CONCEPT = "pusher"                       # Gate A round 3 ruling (Eder 2026-11-20)


def engine_options():
    """Fixed engines from data/task12/engines.yaml as evaluate() expects them; the chosen engine
    also carries its App. K table model (conceptual/engine_model.py). A datasheet cruise
    consumption replaces Table 3.4 for cruise and, lacking a part-power value, for loiter too
    (stated in the package); an engine without one keeps the ledger values."""
    raw = yaml.safe_load(ENGINES.read_text())["engines"]
    out = {}
    for name, e in raw.items():
        eng = {"name": name, "bhp": float(e["bhp"]), "weight_lb": float(e["weight_lb"])}
        if e.get("cbhp_cruise"):
            eng["cbhp_cruise"] = eng["cbhp_loiter"] = float(e["cbhp_cruise"])
        if name == CHOSEN_ENGINE and TP100_TABLE.exists():
            # Stage 3 return (Eder 2026-11-20): the TP100 as its Mattingly App. K cycle table, which
            # replaces the piston lapse (13.9) and the flat brochure SFC wherever the engine enters
            # Gate A round 5 ruling 2: SFC allowance on the table in sizing
            allowance = uav.load_ledger()[0].get("engine_sfc_allowance", 1.0)
            eng["model"] = TableEngine(TP100_TABLE).scaled(sfc=allowance)
        out[name] = eng
    return out, raw


def first_pass(L, A=12.0, swet_sref=4.0, W_S=20.0):
    """Step 3: W0 from (3.4) with Table 3.1 (general aviation single) times the composite factor,
    fuel from Breguet (6.12), (6.15) with Table 3.2 segment fractions and a parabolic polar from
    the equivalent skin friction (12.23) of the sketch. Sketch values A, S_wet/S_ref and W/S are
    first-pass judgements, replaced by the refined sizing."""
    alt = isa(L["mission_altitude_ft"])
    CD0 = aero.cd0_equivalent_skin_friction(0.0055, swet_sref)         # Table 12.3 light single
    e = aero.oswald_straight_wing(A)
    K = aero.induced_drag_factor(A, e)
    V_r, _ = perf.speed_max_ld(W_S, alt["rho"], CD0, K)
    V_e, _ = perf.speed_min_power(W_S, alt["rho"], CD0, K)
    LD_max = 0.5 * math.sqrt(math.pi * A * e / CD0)
    LD_loiter = 0.866 * LD_max                                        # p. 20-21, prop loiter
    cruise = sizing.cruise_fraction_prop(L["radius_nm"] * NM, L["cbhp_cruise"], L["eta_p"], LD_max)
    loiter = sizing.loiter_fraction_prop(L["loiter_h"] * 3600, V_e, L["cbhp_loiter"], L["eta_p"],
                                         LD_loiter)
    segs = [sizing.TAKEOFF_FRACTION, sizing.CLIMB_FRACTION, cruise, loiter, cruise,
            sizing.LANDING_FRACTION]
    _, wf = sizing.fuel_fraction(segs)
    W0, hist = sizing.solve_takeoff_weight(
        L["payload_lb"], wf, lambda W: sizing.empty_fraction_table31(
            W, uav.CATEGORY, material_factor=L["composite_factor"]), 3000.0)
    return {"A": A, "swet_sref": swet_sref, "W_S": W_S, "CD0": CD0, "e": e, "LD_max": LD_max,
            "LD_loiter": LD_loiter, "V_cruise_kt": V_r / KT, "V_loiter_kt": V_e / KT,
            "segment_fractions": segs, "fuel_fraction": wf, "W0": W0,
            "We_over_W0": sizing.empty_fraction_table31(W0, uav.CATEGORY,
                                                        material_factor=L["composite_factor"]),
            "iterations": len(hist)}


def landing_ws_limit(d, L, W_hi=200.0):
    """Largest W/S whose landing distance over 50 ft is within the field length, at the design's
    W0 and drag; returns (value, binding) where binding is False if no limit below W_hi."""
    def dist(W_S):
        S = d["W0"] / W_S
        return perf.landing_distance(d["W0"], S, RHO0, d["CD0_landing"], d["K"],
                                     d["clmax"]["landing"], mu_brake=L["braking_mu"],
                                     free_roll_s=L["free_roll_s"])["total"]
    if dist(W_hi) <= L["field_length_ft"]:
        return W_hi, False
    lo, hi = 5.0, W_hi
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if dist(mid) < L["field_length_ft"] else (lo, mid)
    return lo, True


def constraint_diagram(d, L, engine):
    """Step 4: installed sea-level hp/W required by each requirement against W/S at the design's
    W0 and A; the stall and landing limits; and the best-range (5.13) and best-loiter (5.16) wing
    loadings at the design's cruise and loiter dynamic pressures (start of leg, 20,000 ft)."""
    rows = []
    W0 = d["W0"]
    for i in range(41):
        W_S = 6.0 + 0.5 * i
        try:
            b = uav._build(W0, d["concept"], W_S, d["A"], d["ledger_used"], d["fuel"], engine)
        except ValueError:          # the fixed engine cannot fly a mission leg at this wing loading
            rows.append({"W_S": W_S, "mission_flyable": False})
            continue
        rows.append({"W_S": W_S, "mission_flyable": True, **{k: v / W0 for k, v in b["power_req"].items()}})
    alt = isa(L["mission_altitude_ft"])
    q_c = 0.5 * alt["rho"] * d["mission"][2][3] ** 2
    q_l = 0.5 * alt["rho"] * d["mission"][3][3] ** 2
    land, binding = landing_ws_limit(d, L)
    return rows, {
        "stall": constraints.ws_stall(RHO0, L["stall_speed_kt"] * KT, d["clmax"]["clean"]),
        "landing": land, "landing_binding": binding,
        "best_range_at_cruise_q": constraints.ws_best_range_prop(q_c, d["CD0_alt"], d["A"], d["e"]),
        "best_loiter_at_loiter_q": constraints.ws_best_loiter_prop(q_l, d["CD0_alt"], d["A"], d["e"]),
    }


def carpet(concept, L, engine=None, label="rubber"):
    """Steps 5 and 8: refined sizing over the grid; W0 and power per point. The horizontal tail is
    at its Table 6.4 size here; rotation is checked only at each concept's optimum."""
    rows = []
    for W_S in WS_GRID:
        for A in A_GRID:
            try:
                d = uav.evaluate(concept, W_S, A, L, engine=engine)
                need, avail = uav.fuel_volume_check(d, L)
                rows.append({"engine": label, "concept": concept, "W_S": W_S, "A": A, "W0": d["W0"],
                             "We": d["We"], "fuel": d["fuel"], "bhp": d["bhp"],
                             "fuel_fits": need <= avail, "power_ok": d["power_ok"],
                             "binding_power": max(d["power_req"], key=d["power_req"].get)})
            except ValueError as ex:
                rows.append({"engine": label, "concept": concept, "W_S": W_S, "A": A, "W0": None,
                             "error": str(ex)})
    return rows


def feasible_optimum(rows, ws_max):
    ok = [r for r in rows if r.get("W0") and r["W_S"] <= ws_max and r["fuel_fits"]
          and r.get("power_ok", True)]
    return min(ok, key=lambda r: r["W0"])


def vn_diagram(d, L):
    """V-n points (Raymer 14.2, Figs. 14.7-14.8) at sea level and mission altitude, at take-off and
    zero-fuel weight: the cruise point is the maximum level speed (equivalent airspeed), the dive
    speed 50 % above it (p. 338), U_de to cruise falling to half at dive (p. 339)."""
    CLa, mac, S = d["CLa"], d["geom"]["wing"].mac, d["geom"]["S"]
    alt = isa(L["mission_altitude_ft"])
    pts = {"V_corner_eas_kt": math.sqrt(2 * d["n_limit"] * d["W_S"]
                                        / (RHO0 * d["clmax"]["clean"])) / KT}
    for label, rho in (("sea_level", RHO0), ("mission_altitude", alt["rho"])):
        V_c = d["V_c_eas"][label]
        V_d = 1.5 * V_c
        for wl, W in (("takeoff_weight", d["W0"]), ("zero_fuel_weight", d["W0"] - d["fuel"])):
            n_c = loads.gust_load_factor(W / S, V_c, L["gust_ude_fps"], CLa, mac, rho)[0]
            n_d = loads.gust_load_factor(W / S, V_d, 0.5 * L["gust_ude_fps"], CLa, mac, rho)[0]
            pts[f"gust_{label}_{wl}"] = {"V_cruise_eas_kt": V_c / KT, "V_dive_eas_kt": V_d / KT,
                                         "n_cruise": n_c, "n_dive": n_d, "n_cruise_neg": 2 - n_c,
                                         "n_dive_neg": 2 - n_d}
    return pts


def trades(concept, W_S, A, L, engine, eng_raw):
    """One-at-a-time trades at the chosen point with the chosen engine: loiter time, payload,
    altitude, the engine table's SFC and power at +-10 % (Stage 3 tolerances), and each banded
    ledger assumption at its band ends. Each case is re-sized with the rotation tail resize and
    run through the full compliance check (Gate A round 4, R4-2); failed rows are listed."""
    out = []

    def run(label, eng=engine, **changes):
        L2 = dict(L, **changes)
        try:
            a = analyse(concept, W_S, A, L2, eng)
            d = a["design"]
            comp = compliance(d, d["ledger_used"], a["layout"], a["performance"], *a["fuel_volume"], eng_raw)
            bare = dict(d["ledger_used"], margin_power_fraction=0.0, margin_ceiling_ft=0.0, margin_gust_g=0.0)
            comp0 = compliance(d, bare, a["layout"], a["performance"], *a["fuel_volume"], eng_raw)
            out.append({"case": label, "W0": d["W0"], "bhp": d["bhp"], "fuel": d["fuel"],
                        "power_ok": d["power_ok"],
                        "failed": "; ".join(c["requirement"] for c in comp if c["met"] is False),
                        "failed_without_margins": "; ".join(c["requirement"].replace(", with the round-4 margin", "").split(" (achieved")[0]
                                                            for c in comp0 if c["met"] is False)})
        except ValueError as ex:
            out.append({"case": label, "W0": None, "error": str(ex)})

    for h in (6.0, 8.0, 10.0, 12.0):
        run(f"loiter_h={h:g}", loiter_h=h)
    for p in (300.0, 500.0, 700.0):
        run(f"payload_lb={p:g}", payload_lb=p)
    for alt in (15000.0, 20000.0, 25000.0):
        run(f"mission_altitude_ft={alt:g}", mission_altitude_ft=alt)
    run("no sponsons (wheels stowed for free; reference only)", no_sponsons=True)
    for w in (0.0, 15.0, 35.0, 50.0):                   # R19 strength (Gate A round 4 ruling 9)
        run(f"headwind_kt={w:g}", headwind_kt=w)
    if engine.get("model") is not None:
        for f in (0.9, 1.1):
            run(f"engine table SFC x{f:g}", eng=dict(engine, model=engine["model"].scaled(sfc=f)))
        for f in (0.9, 1.1):
            run(f"engine table power x{f:g}", eng=dict(engine, model=engine["model"].scaled(power=f)))
    _, entries = uav.load_ledger()
    for name, q in entries.items():
        if "band" in q and name in L and name != "composite_factor" and not name.startswith("cbhp"):
            for end, v in zip(("lo", "hi"), q["band"]):
                run(f"{name}={v:g} ({end})", **{name: float(v)})
    return out


ROUND1_WEIGHTS = (("take-off weight W0 (computed)", 0.40, None, None),
                  ("sensor field of view: nose free of propeller and exhaust (judgement)", 0.25, 2, 5),
                  ("propeller wash and exhaust on the sensor and airframe (judgement)", 0.10, 2, 4),
                  ("turboprop exhaust impinging on a pusher propeller, p. 222 (judgement)", 0.10, 5, 2),
                  ("ground clearance and gear length (judgement; pusher needs longer gear, p. 222)", 0.15, 5, 3))


def concept_scores(res, L):
    """Step 2 scoring with the round-1 criteria and weights unchanged (Gate A round 2, reviewer
    section 4): only the W0 row is computed. Layout limits are applied as feasibility constraints,
    not as extra scored rows: nose-wheel load within Raymer's 5-20 % (p. 232-233), nose rotation
    within the tail's available lift after the resize (p. 432-433), and the main gear stowable."""
    t, p = res["tractor"]["design"]["W0"], res["pusher"]["design"]["W0"]
    score = {"tractor": 0.0, "pusher": 0.0}
    table = []
    for label, w, gt, gp in ROUND1_WEIGHTS:
        if gt is None:
            st, sp, vt, vp = 5.0 * min(t, p) / t, 5.0 * min(t, p) / p, t, p
        else:
            st, sp, vt, vp = float(gt), float(gp), gt, gp
        score["tractor"] += w * st
        score["pusher"] += w * sp
        table.append({"criterion": label, "weight": w, "tractor": vt, "pusher": vp,
                      "tractor_grade": round(st, 2), "pusher_grade": round(sp, 2)})
    feas = {}
    for c, r in res.items():
        lay = r["layout"]
        feas[c] = {"nose_load_within_5_20": 0.05 <= max(lay["nose_load"].values()) <= 0.20,
                   "nose_load_within_8_15_optimum": L["nose_load_min"] - 1e-9 <= max(lay["nose_load"].values()) <= L["nose_load_max"] + 1e-9,
                   "rotation_ok": lay["rotation_ok"], "gear_stows": lay["gear_track"]["fits"]}
    return table, score, feas


def _write_csv(path, rows):
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if hasattr(x, "__dataclass_fields__"):
        return {k: getattr(x, k) for k in ("area", "aspect_ratio", "taper", "span", "root_chord",
                                           "tip_chord", "mac", "mac_y")}
    return x


def compliance(d, L, lay, per, need, avail, eng_raw):
    rows = [
        ("R1/R2 single turboprop, one engine", "-", d["engine"].get("fixed", "rubber"), "", "by construction"),
        ("R4 payload", "lb", L["payload_lb"], L["payload_lb"], "by construction"),
        ("R5 mission 200 nm + 8 h + 200 nm", "fuel lb", d["fuel"], d["fuel"], "sized to it"),
        (("R6 note: brochure starting (relight) envelope ends below the loiter altitude; an in-flight relight "
         "needs a descent (round 4, R4-10)"), "ft", eng_raw.get("starting_altitude_max_ft", ""),
         L["mission_altitude_ft"], "note"),
        ("R6 mission altitude 20,000 ft within engine limit", "ft", L["mission_altitude_ft"],
         eng_raw.get("max_operating_altitude_ft", 1e9), "<="),
        ("R7 take-off over 50 ft", "ft", per["takeoff_ft"], L["field_length_ft"], "<="),
        ("R7 landing over 50 ft", "ft", per["landing_ft"], L["field_length_ft"], "<="),
        ("R7 clean stall at W0, sea level", "kt", per["V_stall_clean_kt"], L["stall_speed_kt"], "<="),
        ("R8 retractable tricycle gear", "-", "yes", "", "by construction"),
        ("R9 positive limit load (manoeuvre or gust, both weights)", "-", d["n_limit"],
         L["limit_load_factor"], ">="),
        ("R9 negative gust within the negative limit, with the round-4 margin", "-", d["n_negative_gust"],
         L["negative_load_factor"] + L.get("margin_gust_g", 0.0), ">="),
        ("R10 6 % reserve and trapped fuel", "-", sizing.RESERVE_FACTOR, 1.06, "by construction"),
        ("R12 sea-level rate of climb", "ft/min", per["roc_sl_fpm"], L["climb_rate_sl_fpm"], ">="),
        ("R12 service ceiling (last altitude with 100 ft/min), with the round-4 margin", "ft",
         per["service_ceiling_ft"], L["ceiling_ft"] + L.get("margin_ceiling_ft", 0.0), "ceiling"),
        ("R13 static margin, full fuel", "MAC", lay["sm_full"], "0.05-0.15", "in band"),
        ("R13 static margin, empty fuel", "MAC", lay["sm_empty"], "0.05-0.15", "in band"),
        ("R14 no crew items in the weights", "-", "yes", "", "by construction"),
        ("R15 flight avionics 60 lb uninstalled", "lb", L["avionics_uninstalled_lb"], 60.0, "by construction"),
        ("R18 V_C placard covers the fastest mission sub-step with 10 % margin (study margin)", "kt EAS",
         1.1 * max(m[7] * math.sqrt(isa(L["mission_altitude_ft"])["sigma"]) for m in d["mission"]) / KT,
         d["V_c_eas"]["sea_level"] / KT, "<="),
        ("R17 every mission sub-step at or above 1.3 V_stall (enforced in the speed choice)", "-",
         "yes", "", "by construction"),
        (f"R19 both transit legs flown against a {L.get('headwind_kt', 0.0):g} kt headwind (air distance V/(V - V_w))",
         "kt", L.get("headwind_kt", 0.0), L.get("headwind_kt", 0.0), "by construction"),
        ("R16 sustained 30 deg bank at loiter (power)", "hp", d["power_req"]["turn_at_loiter"], d["bhp"], "<="),
        ("engine power meets every requirement" + (", with the round-4 margin" if L.get("margin_power_fraction") else "")
         + f" (achieved margin {1 - max(d['power_req'].values()) / d['bhp']:.1%})", "hp", max(d["power_req"].values()),
         d["bhp"] * (1.0 - L.get("margin_power_fraction", 0.0)), "<="),
        ("fuel fits integral wing tanks", "ft^3", need, avail, "<="),
        ("nose-wheel load, full fuel (p. 232-233; optimum 0.08-0.15)", "-", lay["nose_load"]["full"], "0.05-0.20", "nose"),
        ("nose-wheel load, empty fuel", "-", lay["nose_load"]["empty"], "0.05-0.20", "nose"),
        ("main gear stows: sponsons at the 63 deg overturn track (p. 232; ruling round 3)", "ft",
         lay["gear_track"]["half_track_ft"], "", "stow"),
        ("propeller clearance at rotation (p. 222)", "in", lay["prop_clearance_in"], L["prop_clearance_in"] - 0.05, ">="),
        ("trim within tail CL limit, all mission legs", "-", "yes" if lay["trim_ok"] else "no", "", "flag"),
        ("nose rotation at 0.8 V_TO (p. 432-433), tail download", "tail CL", abs(lay["rotation"]["CL_tail_needed"]),
         L["tail_cl_max_rotation"], "<="),
    ]
    out = []
    for label, units, value, limit, rule in rows:
        if rule == "<=":
            ok = value <= limit
        elif rule == ">=":
            ok = value is not None and value >= limit
        elif rule == "in band":
            ok = L["static_margin_min"] - 1e-9 <= value <= L["static_margin_max"] + 1e-9
        elif rule == "nose":
            ok = 0.05 <= value <= 0.20                               # Raymer's 5-20 % limits
        elif rule == "ceiling":
            ok = value >= limit - 1.0                                # bisection tolerance
        elif rule == "stow":
            ok = lay["gear_track"]["fits"]
        elif rule == "flag":
            ok = value == "yes"
        else:
            ok = None
        out.append({"requirement": label, "units": units, "value": value, "limit": limit,
                    "rule": rule, "met": ok})
    return out


def first_compliant(concept, rows, ws_max, L, engine, eng_raw, max_tries=80):
    """The lightest carpet point that still meets every checked requirement after the rotation
    tail resize and layout (the carpet itself holds the Table 6.4 tail). Candidates are taken in
    order of carpet W0; if none of them meets everything, the one with fewest failures is returned
    and marked. Returns (analysis, compliance rows, candidates tried)."""
    cands = sorted((r for r in rows if r.get("W0") and r["W_S"] <= ws_max and r["fuel_fits"]
                    and r.get("power_ok", True)), key=lambda r: r["W0"])
    tried = []
    for r in cands[:max_tries]:
        try:
            a = analyse(concept, r["W_S"], r["A"], L, engine)
        except ValueError as ex:
            tried.append({"W_S": r["W_S"], "A": r["A"], "carpet_W0": r["W0"], "failed": [str(ex)]})
            continue
        comp = compliance(a["design"], a["design"]["ledger_used"], a["layout"], a["performance"],
                          *a["fuel_volume"], eng_raw)
        failed = [c["requirement"] for c in comp if c["met"] is False]
        tried.append({"W_S": r["W_S"], "A": r["A"], "carpet_W0": r["W0"], "W0": a["design"]["W0"],
                      "failed": failed})
        tried[-1]["analysis"] = a
        if not failed:
            break
    ok = [t for t in tried if "analysis" in t]
    if not ok:
        raise ValueError(f"no design among the {len(tried)} lightest carpet points could be analysed")
    # the first with no failure; if there is none, the one with fewest failures (recorded)
    best = min(ok, key=lambda t: (len(t["failed"]), t["W0"]))
    a = best.pop("analysis")
    for t in tried:
        t.pop("analysis", None)
    if not best["failed"]:
        a, best = _refine(concept, a, best, ws_max, L, engine, eng_raw, tried)
    best["chosen"] = True
    comp = compliance(a["design"], a["design"]["ledger_used"], a["layout"], a["performance"],
                      *a["fuel_volume"], eng_raw)
    return a, comp, tried


def _refine(concept, a, best, ws_max, L, engine, eng_raw, tried, step=0.5, max_moves=8):
    """Local search off the 1 x 1 grid (Gate A round 4, R4-7): move to the lightest compliant of
    the eight neighbours at +-step in W/S and A until none is lighter. Every point is recorded."""
    seen = {(t["W_S"], t["A"]) for t in tried}
    for _ in range(max_moves):
        moved = False
        cands = []
        for dw in (-step, 0.0, step):
            for da in (-step, 0.0, step):
                p = (best["W_S"] + dw, best["A"] + da)
                if p in seen or p[0] > ws_max or p[1] < 3.0:
                    continue
                seen.add(p)
                try:
                    an = analyse(concept, p[0], p[1], L, engine)
                except ValueError as ex:
                    tried.append({"W_S": p[0], "A": p[1], "failed": [str(ex)], "refinement": True})
                    continue
                comp = compliance(an["design"], an["design"]["ledger_used"], an["layout"], an["performance"],
                                  *an["fuel_volume"], eng_raw)
                t = {"W_S": p[0], "A": p[1], "W0": an["design"]["W0"], "refinement": True,
                     "failed": [c["requirement"] for c in comp if c["met"] is False]}
                tried.append(t)
                if not t["failed"]:
                    cands.append((t["W0"], t, an))
        if cands:
            w, t, an = min(cands, key=lambda c: c[0])
            if w < best["W0"]:
                best, a, moved = t, an, True
        if not moved:
            break
    return a, best


def wind_limits(d, engine, payloads=(500.0, 400.0, 300.0), hi=80.0):
    """Operating limit (Gate A round 4 ruling 9): for each payload, the largest headwind on both transit
    legs that the built aircraft (W0 and geometry as sized) can fly, trading payload for fuel at the
    same W0. At the design payload the fuel is sized for R19's wind, so the limit is that wind by
    construction; lighter payloads buy wind. Every leg must also have a speed within the engine's
    power. Bisection on the wind; nothing is re-sized."""
    L = d["ledger_used"]
    out = {}
    for pl in payloads:
        usable = d["fuel"] + (L["payload_lb"] - pl)

        def closes(w, usable=usable):
            try:
                b = uav._build(d["W0"], d["concept"], d["W_S"], d["A"], dict(L, headwind_kt=w), d["fuel"], engine)
            except ValueError:
                return False
            return b["fuel"] <= usable * (1 + 1e-9)
        lo, hi_ = 0.0, hi
        if not closes(lo):
            out[f"{pl:g}"] = None
            continue
        for _ in range(30):
            mid = 0.5 * (lo + hi_)
            lo, hi_ = (mid, hi_) if closes(mid) else (lo, mid)
        out[f"{pl:g}"] = lo
    return out


def speeds_by_altitude(d, L, altitudes=(0.0, 5000.0, 10000.0, 15000.0, 20000.0)):
    """Level full-throttle top speed (EAS) at take-off and zero-fuel weight, and the gust load factor
    at that speed (14.4)-(14.8), by altitude (Gate A round 4 ruling 10): where it exceeds V_C, the
    placard holds only through the autopilot."""
    out = []
    S, g = d["geom"]["S"], d["geom"]
    for h in altitudes:
        a = isa(h)
        for wlabel, W in (("takeoff_weight", d["W0"]), ("zero_fuel_weight", d["W0"] - d["fuel"])):
            lo = L["climb_speed_over_stall"] * perf.stall_speed(W / S, a["rho"], d["clmax"]["clean"])
            v = uav._vmax_consistent(W, S, g, L, a, h, d["K"], d["bhp"], d.get("engine_model"), lo)
            if v is None:
                continue
            v_eas = v * math.sqrt(a["sigma"])
            cla = aero.lift_slope(d["A"], v / a["a"], L["airfoil_efficiency"], 0.0, g["s_exposed"] / S,
                                  aero.fuselage_lift_factor(g["d_f"], g["wing"].span))
            n = loads.gust_load_factor(W / S, v_eas, L["gust_ude_fps"], cla, g["wing"].mac, a["rho"])[0]
            out.append({"h_ft": h, "weight": wlabel, "vmax_kt_eas": v_eas / KT, "n_gust": n})
    return out


def analyse(concept, W_S, A, L, engine):
    """Size the tail for rotation, lay out and analyse one design."""
    d, lay, scale = uav.size_tail_for_rotation(concept, W_S, A, L, engine=engine)
    Lu = d["ledger_used"]
    per = uav.performance(d, Lu)
    need, avail = uav.fuel_volume_check(d, Lu)
    return {"design": d, "layout": lay, "ht_scale": scale, "performance": per,
            "fuel_volume": (need, avail), "stat": uav.statistical_empty_fractions(d, Lu),
            "vn": vn_diagram(d, Lu), "propeller": uav.propeller_points(d, Lu)}


def design_record(r, L, eng_raw):
    d, lay, per = r["design"], r["layout"], r["performance"]
    g = d["geom"]
    return _jsonable({
        "concept": d["concept"], "W_S": d["W_S"], "A": d["A"], "W0_lb": d["W0"], "We_lb": d["We"],
        "fuel_lb": d["fuel"], "payload_lb": L["payload_lb"], "bhp_sl": d["bhp"],
        "engine": d["engine"], "engine_source": eng_raw.get("source", ""),
        "cbhp_used": {"cruise": next(m[5] for m in d["mission"] if m[0] == "cruise_out"),
                      "loiter": next(m[5] for m in d["mission"] if m[0] == "loiter")},
        "power_required_hp": d["power_req"], "power_ok": d["power_ok"],
        "propeller_diameter_ft": d["D_prop"], "propeller_points": r["propeller"],
        "gear_length_in": d["gear_length_in"], "gear_drag_area_ft2": d["gear_drag_area"],
        "ht_volume_scale": r["ht_scale"],
        "e": d["e"], "K": d["K"], "CD0": {"mission_altitude": d["CD0_alt"], "sea_level": d["CD0_sl"],
                                         "takeoff": d["CD0_takeoff"], "landing": d["CD0_landing"]},
        "CL_max": d["clmax"], "CL_alpha_wing": d["CLa"], "gusts": d["gusts"],
        "n_gust": d["n_gust"], "n_limit": d["n_limit"], "n_negative_gust": d["n_negative_gust"],
        "Nz_ultimate": d["Nz"], "q_design_psf": d["q_design"], "V_c_eas_kt": {k: v / KT for k, v in d["V_c_eas"].items()},
        "components_lb": d["components"],
        "mission": [{"segment": m[0], "W_start": m[1], "W_end": m[2], "V_kt": m[3] / KT,
                     "speed_floor_fraction": m[4], "cbhp_mean": m[5],
                     "turbine_unchoked_fraction": m[6], "V_top_kt": m[7] / KT, "leg_time_h": m[8] / 3600.0,
                     "ground_speed_kt": (L["radius_nm"] * NM / m[8] / KT
                                         if m[0].startswith("cruise") and m[8] else None)} for m in d["mission"]],
        "wing": g["wing"], "horizontal_tail": g["ht"],
        "vertical_tail": {"area": g["S_vt"], "height": g["vt_height"], "root_chord": g["vt_root"],
                          "mac": g["vt_mac"]},
        "fuselage": {"length": g["L_f"], "diameter": g["d_f"], "s_wet": g["s_wet_fus"]},
        "tail_arm_ft": g["arm"],
        "layout": {k: lay[k] for k in ("x_le", "x_ac", "x_np", "cg_full", "cg_empty", "sm_full",
                                       "sm_empty", "x_ht", "x_vt", "x_main", "h_cg", "dah_da",
                                       "Cma_fus", "CLa_h", "trim", "trim_ok", "rotation",
                                       "rotation_ok", "nose_load", "prop_clearance_in", "gear_track",
                                       "nose_station", "cm_wing")},
        "stations": {k: {"weight": m, "x": x} for k, (m, x) in lay["items"].items()},
        "performance": per, "fuel_volume_ft3": {"needed": r["fuel_volume"][0], "available": r["fuel_volume"][1]},
        "empty_fraction_comparison": r["stat"], "vn": r["vn"],
        "operating_limits": r.get("limits", {}), "speeds_by_altitude": r.get("speeds", []),
    })


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    L, _ = uav.load_ledger()
    ledger_bytes = uav.LEDGER.read_bytes()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=False, cwd=REPO).stdout.strip()
    engines, eng_raw = engine_options()
    (out / "inputs.json").write_text(json.dumps({
        "commit": commit, "ledger": "data/task12/ledger.yaml",
        "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        "engines_sha256": hashlib.sha256(ENGINES.read_bytes()).hexdigest(),
        "tp100_table_sha256": hashlib.sha256(TP100_TABLE.read_bytes()).hexdigest(),
        "tp100_table_commit": subprocess.run(["git", "log", "-1", "--format=%H", "--", str(TP100_TABLE)],
                                             capture_output=True, text=True, check=False, cwd=REPO).stdout.strip(),
        "uncommitted_code_changes": bool(subprocess.run(
            ["git", "status", "--porcelain", "--", "conceptual", "measurement", "data"],
            capture_output=True, text=True, check=False, cwd=REPO).stdout.strip()),
        "python": platform.python_version(), "numpy": np.__version__,
        "chosen_engine": CHOSEN_ENGINE, "ws_grid": WS_GRID, "a_grid": A_GRID}, indent=2))
    (out / "ledger.yaml").write_bytes(ledger_bytes)
    (out / "engines.yaml").write_bytes(ENGINES.read_bytes())
    (out / "tp100_table.json").write_bytes(TP100_TABLE.read_bytes())    # the engine the run used
    (out / "first_pass.json").write_text(json.dumps(first_pass(L), indent=2))

    stall_ws = constraints.ws_stall(RHO0, L["stall_speed_kt"] * KT, uav._cl_max(L)["clean"])
    eng = engines[CHOSEN_ENGINE]
    rows = []
    for c in ("tractor", "pusher"):
        rows += carpet(c, L, None, "rubber") + carpet(c, L, eng, CHOSEN_ENGINE)
    _write_csv(out / "carpet.csv", rows)

    res = {}
    for c in ("tractor", "pusher"):
        crows = [r for r in rows if r["concept"] == c and r["engine"] == CHOSEN_ENGINE]
        res[c], _, tried = first_compliant(c, crows, stall_ws, L, eng, eng_raw[CHOSEN_ENGINE])
        res[c]["limits"] = {"max_headwind_kt_by_payload_lb": wind_limits(res[c]["design"], eng)}
        res[c]["speeds"] = speeds_by_altitude(res[c]["design"], res[c]["design"]["ledger_used"])
        (out / f"selection_{c}.json").write_text(json.dumps(tried, indent=2, default=float))
        (out / f"design_{c}.json").write_text(json.dumps(design_record(res[c], L, eng_raw[CHOSEN_ENGINE]),
                                                         indent=2, default=float))
        Lu = res[c]["design"]["ledger_used"]
        _write_csv(out / f"compliance_{c}.csv",
                   compliance(res[c]["design"], Lu, res[c]["layout"], res[c]["performance"],
                              *res[c]["fuel_volume"], eng_raw[CHOSEN_ENGINE]))
    table, score, feas = concept_scores(res, L)
    recommended = max(score, key=score.get)
    rubber_opt = {c: feasible_optimum([r for r in rows if r["concept"] == c and r["engine"] == "rubber"],
                                      stall_ws) for c in ("tractor", "pusher")}
    (out / "concept_scores.json").write_text(json.dumps(
        {"table": table, "score": score, "feasibility": feas, "recommended": FROZEN_CONCEPT,
         "highest_score": recommended, "frozen_at_round3": FROZEN_CONCEPT,
         "frozen_at_round1": "pusher", "ruled_at_round2_on_flawed_rotation": "tractor",
         "rubber_optimum": rubber_opt}, indent=2, default=float))

    recommended = FROZEN_CONCEPT                 # the package follows the frozen concept
    d = res[recommended]["design"]
    cd_rows, limits = constraint_diagram(d, L, eng)
    _write_csv(out / "constraint_diagram.csv", cd_rows)
    (out / "constraint_limits.json").write_text(json.dumps(limits, indent=2))

    alt_rows = []
    tp_table34 = {k: v for k, v in engines[CHOSEN_ENGINE].items() if not k.startswith("cbhp") and k != "model"}
    tp_table34["name"] = CHOSEN_ENGINE + " at Table 3.4 consumption, piston lapse"
    tp_gate_a = {k: v for k, v in engines[CHOSEN_ENGINE].items() if k != "model"}
    tp_gate_a["name"] = CHOSEN_ENGINE + " as at Gate A: flat 0.901, piston lapse"
    for name, e in ([("rubber", None)] + list(engines.items())
                    + [(tp_gate_a["name"], tp_gate_a), (tp_table34["name"], tp_table34)]):
        try:
            f = uav.evaluate(recommended, d["W_S"], d["A"], dict(L, ht_volume_scale=res[recommended]["ht_scale"]),
                             engine=e)
            alt_rows.append({"engine": name, "bhp": f["bhp"], "engine_weight_lb": f["engine"]["weight_lb"],
                             "cbhp_cruise": next(m[5] for m in f["mission"] if m[0] == "cruise_out"),
                             "cbhp_loiter": next(m[5] for m in f["mission"] if m[0] == "loiter"),
                             "W0": f["W0"], "We": f["We"], "fuel": f["fuel"], "power_ok": f["power_ok"],
                             "required_hp": max(f["power_req"].values()),
                             "binding": max(f["power_req"], key=f["power_req"].get)})
        except ValueError as ex:
            alt_rows.append({"engine": name, "W0": None, "error": str(ex)})
    _write_csv(out / "engines_compared.csv", alt_rows)
    _write_csv(out / "trades.csv", trades(recommended, d["W_S"], d["A"], L, eng, eng_raw[CHOSEN_ENGINE]))
    tests = subprocess.run(["python3", "-m", "pytest", "-q", "tests/task12"], capture_output=True,
                           text=True, check=False, cwd=REPO)
    (out / "test_report.txt").write_text(tests.stdout)
    print(json.dumps({"recommended": recommended, "score": score,
                      "W0": {c: res[c]["design"]["W0"] for c in res},
                      "point": {c: (res[c]["design"]["W_S"], res[c]["design"]["A"]) for c in res},
                      "engines": [(r["engine"], r.get("W0")) for r in alt_rows]}, indent=2, default=float))


if __name__ == "__main__":
    main()

"""Preliminary design P8: envelope protection as a stated requirement (spec P8, rulings B-4 and B-9d, PD-11).

    python -m prelim.p8_envelope --out runs/task12/pd/<date>/p8
    python -m prelim.p8_envelope --out runs/task12/pd/<date>/p8 --report-only \
        --report docs/validation/<date>_task12_pd_p8.md --requirement docs/specs/task12_envelope_protection.md

Run on Opus 5.5 under owner ruling PD-22: not yet Fable-reviewed.

What is run here (every other number is read from a committed record):
  EP-2: the shaft power for level flight at V_C against altitude, at each flown weight, and the engine's excess above it,
        with r0's polar and App. L propeller and P0's engine table; P6's blade as a labelled second reading (P6 failed
        its validation, so the reading has no weight).
  EP-3: the largest speed above V_C at which the gust load factor stays inside the limits, with P5's own gust code.
  EP-4: a point-mass dive from V_C to V_D at idle and at full power, at stated descent angles.
  EP-5, EP-6: the stall-limited load factor at the R16 turn and 1.3 V_stall at each flown weight.
Then the nine rows EP-1 to EP-9 are built; each number carries the record and the key it was read from.

Library (cited by number and page; no book text copied): Raymer p. 338 (V_D 1.5 V_C), p. 339 (the gust rule),
(12.15) p. 270 (as P2 used it); (17.2) p. 458 (power for level flight = D V); (13.16) p. 327 (thrust from power).
r0, its ledger and the records of P0, P2b, P4b, P5 and P6 are read and not changed. Units: ft, lb, s; speeds EAS.
"""
import argparse
import hashlib
import itertools
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import yaml
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import uav
from conceptual.units import KT, isa
from prelim import p5_loads as p5
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
CHOICES = REPO / "data/task12/pd_p8_choices.yaml"
OUT_DEFAULT = "runs/task12/pd/2026-11-28/p8"
G = 32.174
REVIEW = "Not yet Fable-reviewed (ruling PD-22)"
EVIDENCE = "A requirement, not a verification (spec P8)."
# where each record lives; a number's "record" is one of these names
RECORDS = {"r0_design": "runs/task12/pd/2026-11-27/p0/r0/design_pusher.json",
           "r0_ledger": "runs/task12/pd/2026-11-27/p0/r0/ledger.yaml",
           "p0": "runs/task12/pd/2026-11-27/p0/p0.json",
           "p2b": "runs/task12/pd/2026-11-27/p2b/p2.json",
           "p4b": "runs/task12/pd/2026-11-28/p4b/p4b.json",
           "p5": "runs/task12/pd/2026-11-28/p5/p5.json",
           "p6": "runs/task12/pd/2026-11-27/p6/p6.json",
           "p8": OUT_DEFAULT + "/p8.json"}


def load_choices(path=CHOICES):
    return yaml.safe_load(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_record(name):
    """A record as a dict (json, or yaml for the ledger)."""
    path = REPO / RECORDS[name]
    return yaml.safe_load(path.read_text()) if path.suffix == ".yaml" else json.loads(path.read_text())


def pick(data, key):
    """The value at a dotted key; a part that is a number indexes a list ("row3.points.4.n_up")."""
    for part in key.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


# ---- context ----------------------------------------------------------------------------------------------------
def context():
    """P5's context (r0 rebuilt, which raises if the rebuild does not reproduce the record; the ballast) and the
    records P8 reads."""
    c = p5.context()
    c["choices"] = load_choices()
    c["records"] = {k: read_record(k) for k in RECORDS if k != "p8"}
    return c


def speeds(c):
    """V_C, V_D (ft/s EAS) as P5 takes them (Stage 1's V_D = 1.5 V_C, Raymer p. 338)."""
    V_C, V_D, _ = p5.speeds(c)
    return V_C, V_D


def flown_weights(c, extra=0.0):
    W = p5.weights(c, extra)
    return {k: W[k] for k in c["choices"]["weights"]["flown"]}


# ---- EP-2: power for level flight at V_C ----------------------------------------------------------------------
def level_power(c, W, h_ft, V_eas):
    """Level flight at an EAS: drag of r0's polar (CD0 build-up at the speed, (12.24) as Stage 1 codes it) with
    perf.drag, shaft power D V/(550 eta) with r0's App. L propeller ((17.2), p. 458), and the full-throttle shaft power
    of P0's table at that speed. Returns a dict in ft, lb, hp."""
    b, L = c["b"], c["L"]
    atm = isa(h_ft)
    V = V_eas / math.sqrt(atm["sigma"])
    CD0, _ = uav._polar(b["geom"], L, V, atm, b["bhp"])
    D = perf.drag(W, b["geom"]["S"], atm["rho"], V, CD0, b["K"])
    hp = prop.shaft_hp(D * V, V, uav._propeller(L, atm, b["D_prop"]))
    full = b["bhp"] * b["engine_model"].lapse(h_ft, V / KT)
    return {"V_tas_kt": V / KT, "CD0": CD0, "drag_lb": D, "shaft_hp": hp, "full_hp": full}


def crossover_altitude(c, W, V_eas, top_ft=35000.0, step=500.0):
    """The altitude above which full throttle no longer reaches V_eas in level flight (brentq on full - needed, from a
    500 ft scan). None if full throttle reaches it everywhere up to top_ft."""
    def excess(h):
        p = level_power(c, W, h, V_eas)
        return p["full_hp"] - p["shaft_hp"]
    hs = np.arange(0.0, top_ft + 0.5 * step, step)
    for lo, hi in itertools.pairwise(hs):
        if excess(lo) >= 0.0 > excess(hi):
            return brentq(excess, lo, hi, xtol=1e-6)
    return None


def p6_blade():
    """P6's representative propeller as prelim/p6_propeller.aircraft sets it up: the blade, the section and the twist
    from the design lift coefficient at r0's loiter point."""
    from prelim import bem
    from prelim import p6_propeller as p6
    L = p6.blade_ledger()
    sections = p6.load_sections(L["prop_section_span_factor"])
    blade = p6.aircraft_blade(L)
    lo = p6.operating_points()["loiter"]
    twist = bem.design_twist(L["prop_design_cl"], lo["V_fps"], lo["rpm"], lo["D_ft"], L["prop_blades"], lo["rho"],
                             blade["x"], blade["c_over_D"], blade["t_c"], sections)
    return {"L": L, "blade": blade, "section": sections.section(False), "twist": twist, "rpm": lo["rpm"], "D_ft": lo["D_ft"]}


def p6_power_for_drag(pb, drag_lb, V_tas, h_ft, hp_start, tol, max_iter):
    """Shaft power at which P6's blade, constant speed, gives a thrust equal to the drag: hp = D V/(550 eta(hp)),
    iterated from hp_start. Raises if it does not settle within max_iter."""
    from prelim import bem
    atm = isa(h_ft)
    hp, steps = hp_start, []
    for _ in range(max_iter):
        r = bem.pitch_for_power(hp, V_tas, pb["rpm"], pb["D_ft"], pb["L"]["prop_blades"], atm["rho"], atm["a"],
                                pb["blade"]["x"], pb["blade"]["c_over_D"], pb["twist"], pb["blade"]["t_c"], pb["section"])
        new = drag_lb * V_tas / (prop.HP * r["eta"])
        steps.append({"hp": hp, "eta": r["eta"], "thrust_lb": r["thrust_lb"], "next_hp": new})
        if abs(new - hp) < tol:
            return {"shaft_hp": new, "eta": r["eta"], "iterations": steps}
        hp = new
    raise RuntimeError(f"P6 reading did not settle at {h_ft} ft: {steps}")


def ep2(c, extra=0.0, with_p6=True, log=print):
    ch = c["choices"]["ep2_power_limit"]
    V_C, _ = speeds(c)
    W = flown_weights(c, extra)
    alts = [float(h) for h in c["records"]["p5"]["sources"]["choices"]["operating_limit"]["altitudes_ft"]]
    points, schedule = [], []
    for h in alts:
        row = {}
        for wl, w in W.items():
            p = level_power(c, w, h, V_C)
            p.update(altitude_ft=h, weight=wl, W_lb=w, reaches_V_C=p["full_hp"] >= p["shaft_hp"],
                     excess_hp=p["full_hp"] - p["shaft_hp"], throttle=p["shaft_hp"] / p["full_hp"])
            points.append(p)
            row[wl] = p
        lightest = min(row.values(), key=lambda p: p["shaft_hp"])
        needed = lightest["reaches_V_C"]
        schedule.append({"altitude_ft": h, "limit_needed": needed, "weight": lightest["weight"],
                         "limit_hp": lightest["shaft_hp"] if needed else None, "full_hp": lightest["full_hp"],
                         "excess_hp": lightest["excess_hp"] if needed else None,
                         "throttle": lightest["throttle"] if needed else None,
                         "per_weight_hp": {k: v["shaft_hp"] for k, v in row.items()}})
    cross = {wl: crossover_altitude(c, w, V_C) for wl, w in W.items()}
    out = {"V_C_kt": V_C / KT, "points": points, "schedule": schedule, "crossover_ft": cross,
           "crossover_lowest_ft": min(cross.values()), "crossover_highest_ft": max(cross.values())}
    if extra == 0.0:
        out["check"] = level_top_speed_check(c, ch["coding_check_tolerance_relative"])
    if with_p6:
        out["p6_second_reading"] = p6_reading(c, log)
    return out


def level_top_speed_check(c, tol):
    """Coding check: at r0's recorded level top speeds (take-off weight) the power for level flight is full throttle."""
    d = c["d"]
    pts = []
    for h, key in ((0.0, "vmax_sl_kt_eas"), (c["L"]["mission_altitude_ft"], "vmax_alt_kt_eas")):
        p = level_power(c, d["W0_lb"], h, d["performance"][key] * KT)
        pts.append({"altitude_ft": h, "V_eas_kt": d["performance"][key], "shaft_hp": p["shaft_hp"], "full_hp": p["full_hp"],
                    "deviation": p["shaft_hp"] / p["full_hp"] - 1.0})
    worst = max(abs(p["deviation"]) for p in pts)
    return {"points": pts, "worst": worst, "tolerance": tol, "verdict": "pass" if worst <= tol else "fail"}


def p6_reading(c, log=print):
    """EP-2's second reading with P6's blade at the choices' altitudes and weight. P6 failed its validation (row 5):
    labelled, no weight."""
    ch = c["choices"]["ep2_power_limit"]["p6_second_reading"]
    V_C, _ = speeds(c)
    w = flown_weights(c)[ch["weight"]]
    pb = p6_blade()
    p6rec = c["records"]["p6"]
    out = {"label": "second reading, no weight: P6 failed its validation (row 5) and its numbers are not used in r1",
           "p6_used_in_r1": p6rec["used_in_r1"],
           "p6_row5_verdict": next(v["verdict"] for v in p6rec["validation"] if v["row"] == 5), "weight": ch["weight"], "points": []}
    for h in ch["altitudes_ft"]:
        p = level_power(c, w, float(h), V_C)
        r = p6_power_for_drag(pb, p["drag_lb"], p["V_tas_kt"] * KT, float(h), p["shaft_hp"], ch["tolerance_hp"], ch["max_iterations"])
        out["points"].append({"altitude_ft": float(h), "drag_lb": p["drag_lb"], "app_l_hp": p["shaft_hp"], "p6_hp": r["shaft_hp"],
                              "p6_eta": r["eta"], "difference": r["shaft_hp"] / p["shaft_hp"] - 1.0, "iterations": r["iterations"]})
        log(f"EP-2 P6 reading at {h} ft: {r['shaft_hp']:.1f} hp against App. L {p['shaft_hp']:.1f} hp")
    return out


# ---- EP-3: the overspeed margin --------------------------------------------------------------------------------
def gust_at(c, W, h_ft, V_eas, U_cap=None):
    """(n_up, n_down) by P5's ruled_gust (Stage 1's formula, lift slope at the speed's Mach number). U_cap holds the gust
    at that value above V_C; None is the ruled rule (30 ft/s to V_C falling to 15 ft/s at V_D)."""
    V_C, V_D = speeds(c)
    n_up, n_down = p5.ruled_gust(W / c["b"]["geom"]["S"], V_eas, h_ft, V_C, V_D, p5.slope_fn(c), c["b"]["geom"]["wing"].mac,
                                 U_cap=U_cap if V_eas > V_C else None)[:2]
    return n_up, n_down


def cleared_speed(c, W, h_ft, n_pos, n_neg, U_cap=None, grid=400):
    """The largest EAS up to V_D below which the gust stays at or below n_pos and at or above n_neg: the first crossing
    on a grid of speeds from 1 ft/s, then brentq (as p5.operating_speed, with the gust held at U_cap above V_C when it is
    given). Returns {"V_eas_fps", "limited_by"}; limited_by is None if nothing is reached up to V_D."""
    _, V_D = speeds(c)

    def excess(V):
        n_up, n_down = gust_at(c, W, h_ft, V, U_cap)
        return max(n_up - n_pos, n_neg - n_down)

    Vs = np.linspace(1.0, V_D, grid)
    previous = Vs[0]
    for V in Vs[1:]:
        if excess(V) > 0.0:
            root = brentq(excess, previous, V, xtol=1e-10)
            n_up, n_down = gust_at(c, W, h_ft, root, U_cap)
            return {"V_eas_fps": root, "limited_by": "positive" if n_up - n_pos >= n_neg - n_down else "negative"}
        previous = V
    return {"V_eas_fps": V_D, "limited_by": None}


def ep3(c, extra=0.0):
    ch = c["choices"]["ep3_overspeed"]
    lim = c["records"]["p5"]["row3"]["limits"]
    U30 = c["L"]["gust_ude_fps"]
    V_C, V_D = speeds(c)
    W = flown_weights(c, extra)
    alts = [float(h) for h in c["records"]["p5"]["sources"]["choices"]["operating_limit"]["altitudes_ft"]]
    pts = []
    for h in alts:
        for wl, w in W.items():
            for reading, cap in (("ruled_rule", None), ("held_at_vc_gust", U30)):
                o = cleared_speed(c, w, h, lim["positive"], lim["negative_gust"], cap)
                pts.append({"altitude_ft": h, "weight": wl, "W_lb": w, "reading": reading, "V_eas_kt": o["V_eas_fps"] / KT,
                            "excursion_kt": (o["V_eas_fps"] - V_C) / KT, "limited_by": o["limited_by"]})
    schedule = {}
    for reading in ("ruled_rule", "held_at_vc_gust"):
        rows = []
        for h in alts:
            here = [p for p in pts if p["reading"] == reading and p["altitude_ft"] == h]
            worst = min(here, key=lambda p: p["excursion_kt"])
            rows.append({"altitude_ft": h, "excursion_kt": worst["excursion_kt"], "weight": worst["weight"],
                         "limited_by": worst["limited_by"]})
        schedule[reading] = rows
    top = float(ch["altitude_limit_ft"])
    inside = [r for r in schedule[ch["stated"]] if r["altitude_ft"] <= top]
    binding = min(inside, key=lambda r: r["excursion_kt"])
    # under the ruled rule U V is stationary at V_C; the lift slope's rise with Mach number lifts n slightly above it
    w, h = W[binding["weight"]], binding["altitude_ft"]
    n_vc = gust_at(c, w, h, V_C)[0]
    rise = max(gust_at(c, w, h, V)[0] - n_vc for V in np.linspace(V_C, V_D, 111))
    return {"limits": lim, "U_held_fps": U30, "points": pts, "schedule": schedule, "stated_reading": ch["stated"],
            "altitude_limit_ft": top, "stated_excursion_kt": binding["excursion_kt"], "binding": binding,
            "stated_excursion_floor_kt": math.floor(10.0 * binding["excursion_kt"]) / 10.0,
            "stated_at_sea_level_kt": schedule[ch["stated"]][0]["excursion_kt"],
            "ruled_rule_smallest_up_to_limit_kt": min(r["excursion_kt"] for r in schedule["ruled_rule"] if r["altitude_ft"] <= top),
            "V_D_minus_V_C_kt": (V_D - V_C) / KT, "ruled_rule_largest_rise_above_V_C": rise,
            "ruled_rule_n_up_at_V_C_binding_case": n_vc}


# ---- EP-4: the dive from V_C to V_D -----------------------------------------------------------------------------
def integrate_dive(force, W, gamma, V0, h0, stop, t_max, rtol=1e-9, atol=1e-9):
    """Point mass on a straight path at descent angle gamma (rad): (W/g) dV/dt = force(V, h) + W sin(gamma),
    dh/dt = -V sin(gamma). force is thrust less drag (lb). Stops where stop(V, h) rises through zero, at h = 0, or at
    t_max. Returns {"t_s", "h_end_ft", "V_end_fps", "end"} with end "stop", "ground" or "time limit"."""
    def rhs(t, x):
        V, h = x
        return [(force(V, h) + W * math.sin(gamma)) * G / W, -V * math.sin(gamma)]

    def reached(t, x):
        return stop(x[0], x[1])
    reached.terminal, reached.direction = True, 1.0

    def ground(t, x):
        return x[1]
    ground.terminal, ground.direction = True, -1.0

    s = solve_ivp(rhs, (0.0, t_max), [V0, h0], method="DOP853", events=[reached, ground], rtol=rtol, atol=atol, max_step=1.0)
    if not s.success:
        raise RuntimeError(f"dive integration failed: {s.message}")
    end = "stop" if s.t_events[0].size else ("ground" if s.t_events[1].size else "time limit")
    return {"t_s": float(s.t[-1]), "h_end_ft": float(s.y[1, -1]), "V_end_fps": float(s.y[0, -1]), "end": end,
            "V_samples_fps": s.y[0].tolist(), "h_samples_ft": s.y[1].tolist()}


def dive(c, W, gamma_deg, h0, power):
    """EP-4 for one case: entered at V_C at h0, at idle (zero thrust) or full throttle (P0's table, App. L propeller)."""
    b, L = c["b"], c["L"]
    V_C, V_D = speeds(c)
    gamma = math.radians(gamma_deg)

    def force(V, h):
        atm = isa(min(max(h, 0.0), 65000.0))
        CD0, _ = uav._polar(b["geom"], L, V, atm, b["bhp"])
        D = perf.drag(W, b["geom"]["S"], atm["rho"], V, CD0, b["K"], math.cos(gamma))
        if power == "idle":
            return -D
        hp = b["bhp"] * b["engine_model"].lapse(max(h, 0.0), V / KT)
        return prop.thrust_from_power(hp, uav._propeller(L, atm, b["D_prop"]), V) - D

    def eas(V, h):
        return V * math.sqrt(isa(min(max(h, 0.0), 65000.0))["sigma"])

    r = integrate_dive(force, W, gamma, V_C / math.sqrt(isa(h0)["sigma"]), h0, lambda V, h: eas(V, h) - V_D,
                       c["choices"]["ep4_dive"]["time_limit_s"])
    v_eas = [eas(V, h) for V, h in zip(r["V_samples_fps"], r["h_samples_ft"])]
    return {"start_altitude_ft": h0, "W_lb": W, "descent_deg": gamma_deg, "power": power, "reached_V_D": r["end"] == "stop",
            "end": "V_D" if r["end"] == "stop" else r["end"], "time_s": r["t_s"], "height_lost_ft": h0 - r["h_end_ft"],
            "V_end_eas_kt": eas(r["V_end_fps"], r["h_end_ft"]) / KT, "V_largest_eas_kt": max(v_eas) / KT}


def ep4(c):
    ch = c["choices"]["ep4_dive"]
    W = p5.weights(c)
    cases = [dict(dive(c, W[wl], float(a), float(h0), pw), weight=wl)
             for h0 in ch["start_altitudes_ft"] for wl in ch["weights"] for pw in ch["power"] for a in ch["descent_angles_deg"]]
    by_angle = []
    for pw in ch["power"]:
        for a in ch["descent_angles_deg"]:
            here = [x for x in cases if x["power"] == pw and x["descent_deg"] == float(a)]
            hit = [x for x in here if x["reached_V_D"]]
            by_angle.append({"power": pw, "descent_deg": float(a), "cases": len(here), "reached": len(hit),
                             "shortest_time_s": min(x["time_s"] for x in hit) if hit else None,
                             "least_height_lost_ft": min(x["height_lost_ft"] for x in hit) if hit else None,
                             "largest_height_lost_ft": max(x["height_lost_ft"] for x in hit) if hit else None})
    hit = [x for x in cases if x["reached_V_D"]]
    fastest = min(hit, key=lambda x: x["time_s"])
    least = min(hit, key=lambda x: x["height_lost_ft"])
    return {"cases": cases, "by_angle": by_angle, "shortest_time_s": fastest["time_s"], "shortest_case": fastest,
            "least_height_lost_ft": least["height_lost_ft"], "least_height_case": least,
            "not_reached": [x for x in cases if not x["reached_V_D"]], "closed_form_check": dive_closed_form_check()}


def dive_closed_form_check():
    """Coding check of integrate_dive: with no force V = V0 + g sin(gamma) t, so the time to a speed is closed form."""
    gamma, V0, V1, W = math.radians(30.0), 200.0, 300.0, 3000.0
    r = integrate_dive(lambda V, h: 0.0, W, gamma, V0, 20000.0, lambda V, h: V - V1, 600.0)
    t = (V1 - V0) / (G * math.sin(gamma))
    dh = math.sin(gamma) * (V0 * t + 0.5 * G * math.sin(gamma) * t * t)
    dev = max(abs(r["t_s"] / t - 1.0), abs((20000.0 - r["h_end_ft"]) / dh - 1.0))
    return {"time_s": r["t_s"], "closed_form_time_s": t, "height_lost_ft": 20000.0 - r["h_end_ft"], "closed_form_height_ft": dh,
            "deviation": dev, "tolerance": 1e-6, "verdict": "pass" if dev <= 1e-6 else "fail"}


# ---- EP-5, EP-6: load factor and low speed ---------------------------------------------------------------------
def stall_speed_eas(c, W, cl_max):
    """V_stall = sqrt(2 W/(rho_0 S CL_max)), EAS: perf.stall_speed at the sea-level ISA density, as Stage 1's own
    clean stall speed takes it (uav.performance)."""
    return perf.stall_speed(W / c["b"]["geom"]["S"], isa(0.0)["rho"], cl_max)


def ep5(c):
    L, d = c["L"], c["d"]
    m = L["margin_gust_g"]
    n_turn = 1.0 / math.cos(math.radians(L["turn_bank_deg"]))
    loiter = next(x for x in d["mission"] if x["segment"] == "loiter")
    atm = isa(L["mission_altitude_ft"])
    q = 0.5 * atm["rho"] * (loiter["V_kt"] * KT) ** 2
    cls = {"r0": d["CL_max"]["clean"], "p2_measured_r1": c["records"]["p2b"]["wing"]["measured"]["clean"]}
    stall_n = {k: q * cl * c["b"]["geom"]["S"] / loiter["W_start"] for k, cl in cls.items()}
    man = c["records"]["p5"]["row3"]["manoeuvre"]
    return {"positive_limit": L["limit_load_factor"], "negative_limit": L["negative_load_factor"], "margin_g": m,
            "positive_command": L["limit_load_factor"] - m, "negative_command": L["negative_load_factor"] + m,
            "n_r16": n_turn, "bank_deg": L["turn_bank_deg"], "loiter_V_tas_kt": loiter["V_kt"], "loiter_W_start_lb": loiter["W_start"],
            "stall_limited_n_at_loiter": stall_n, "cl_max": cls,
            "r16_available": all(n_turn <= x for x in stall_n.values()) and n_turn <= L["limit_load_factor"] - m,
            "negative_corner_below_V_C": {k: v["negative_corner_below_V_C"] for k, v in man.items()},
            "negative_corner_kt": {k: v["negative_corner_kt"] for k, v in man.items()},
            "positive_corner_kt": {k: v["positive_corner_kt"] for k, v in man.items()}}


def ep6(c, extra=0.0):
    L, d = c["L"], c["d"]
    cls = {"r0": d["CL_max"]["clean"], "p2_measured_r1": c["records"]["p2b"]["wing"]["measured"]["clean"]}
    W = flown_weights(c, extra)
    out = {"factor": L["speed_over_stall"], "cl_max": cls, "weights": W, "points": {}}
    for k, cl in cls.items():
        out["points"][k] = {wl: {"V_stall_kt": stall_speed_eas(c, w, cl) / KT,
                                 "floor_kt": L["speed_over_stall"] * stall_speed_eas(c, w, cl) / KT} for wl, w in W.items()}
    if extra == 0.0:
        v = out["points"]["r0"]["takeoff"]["V_stall_kt"]
        dev = v / d["performance"]["V_stall_clean_kt"] - 1.0
        out["check"] = {"V_stall_takeoff_kt": v, "record_kt": d["performance"]["V_stall_clean_kt"], "deviation": dev,
                        "tolerance": 1e-9, "verdict": "pass" if abs(dev) <= 1e-9 else "fail"}
    return out


# ---- the rows ---------------------------------------------------------------------------------------------------
def num(res, records, name, record, key, unit, fmt):
    """One number of a row, read from its record at its key (P8's own record is res itself)."""
    value = pick(res if record == "p8" else records[record], key)
    return {"name": name, "value": value, "unit": unit, "record": record, "key": key, "fmt": fmt}


def index_of(items, **match):
    return next(i for i, x in enumerate(items) if all(x[k] == v for k, v in match.items()))


def extreme_index(items, field, largest, **match):
    """Index of the item with the largest (or smallest) field among those that match."""
    idx = [i for i, x in enumerate(items) if all(x[k] == v for k, v in match.items())]
    return (max if largest else min)(idx, key=lambda i: items[i][field])


def rows(res, records):
    p5r, p4b = records["p5"], records["p4b"]
    chosen = p4b["selection"]["chosen"]
    n = lambda *a: num(res, records, *a)
    sched2 = res["ep2"]["schedule"]
    i_sl, i_20 = index_of(sched2, altitude_ft=0.0), index_of(sched2, altitude_ft=20000.0)
    i_23 = index_of(sched2, altitude_ft=23000.0)
    s3 = res["ep3"]["schedule"][res["ep3"]["stated_reading"]]
    j20 = index_of(s3, altitude_ft=20000.0)
    p6pts = res["ep2"]["p6_second_reading"]["points"]
    r3p = p5r["row3"]["points"]
    vd_up = extreme_index(r3p, "n_up", True, speed="V_D")
    vd_dn = extreme_index(r3p, "n_down", False, speed="V_D")
    ob = p5r["row5"]["cases"]["payload_off_with_ballast"]
    obp = ob["points"]
    ob_vd_up = extreme_index(obp, "n_up", True, speed="V_D")
    held = p5r["row4"]["cases"]["ruled_held_30"]["points"]
    h_vd_up = extreme_index(held, "n_up", True, speed="V_D")
    h_vd_dn = extreme_index(held, "n_down", False, speed="V_D")
    last_clear = max(i for i, x in enumerate(ob["operating_limit"]) if x["at_or_above_V_C"]
                     and x["altitude_ft"] < ob["lowest_altitude_limited_below_V_C_ft"])
    first_below = index_of(ob["operating_limit"], altitude_ft=ob["lowest_altitude_limited_below_V_C_ft"])
    ep4b = res["ep4"]["by_angle"]
    k_full45 = index_of(ep4b, power="full", descent_deg=45.0)
    k_idle45 = index_of(ep4b, power="idle", descent_deg=45.0)
    k_idle5 = index_of(ep4b, power="idle", descent_deg=5.0)
    f = ".1f"
    out = [
        {"id": "EP-1", "title": "Speed hold",
         "text": "The protection holds the speed at or below V_C = {V_C} kt EAS at every altitude and every weight, in climb, level "
                 "flight and descent (R18). V_D = {V_D} kt EAS. The fastest mission sub-step is {fastest} kt EAS, below V_C.",
         "numbers": [n("V_C", "r0_design", "V_c_eas_kt.sea_level", "kt EAS", f), n("V_D", "p5", "r0.V_D_kt", "kt EAS", f),
                     n("fastest", "r0_design", "fastest_step_eas_kt", "kt EAS", ".2f")],
         "headline": "V_C"},
        {"id": "EP-2", "title": "Power limit schedule",
         "text": "In level flight the shaft power is limited to the power that holds V_C: {lim_sl} hp at sea level, {lim_20} hp at "
                 "20,000 ft and {lim_23} hp at 23,000 ft (lightest flown weight; schedule S-2). The engine's excess above the limit "
                 "is {exc_sl} hp at sea level and {exc_20} hp at 20,000 ft. Above {cross_lo} ft ({cross_lo_w}) to {cross_hi} ft "
                 "({cross_hi_w}) full throttle does not reach V_C and no limit is needed. Without the limit the level top speed "
                 "is {vmax_sl} kt EAS at sea level and {vmax_20} kt EAS at 20,000 ft. Second reading, no weight (P6 failed its "
                 "validation): P6's blade needs {p6_sl} hp at sea level.",
         "numbers": [n("lim_sl", "p8", f"ep2.schedule.{i_sl}.limit_hp", "hp", f), n("lim_20", "p8", f"ep2.schedule.{i_20}.limit_hp", "hp", f),
                     n("lim_23", "p8", f"ep2.schedule.{i_23}.limit_hp", "hp", f),
                     n("exc_sl", "p8", f"ep2.schedule.{i_sl}.excess_hp", "hp", f), n("exc_20", "p8", f"ep2.schedule.{i_20}.excess_hp", "hp", f),
                     n("cross_lo", "p8", "ep2.crossover_lowest_ft", "ft", ",.0f"), n("cross_hi", "p8", "ep2.crossover_highest_ft", "ft", ",.0f"),
                     n("vmax_sl", "r0_design", "performance.vmax_sl_kt_eas", "kt EAS", f),
                     n("vmax_20", "r0_design", "performance.vmax_alt_kt_eas", "kt EAS", f),
                     n("p6_sl", "p8", f"ep2.p6_second_reading.points.{index_of(p6pts, altitude_ft=0.0)}.p6_hp", "hp", f)],
         "headline": "lim_sl"},
        {"id": "EP-3", "title": "Overspeed margin",
         "text": "The protection may let the speed exceed V_C by at most {exc} kt EAS at and below {alt} ft (computed {exc_full} kt, "
                 "rounded down; {exc_20} kt at 20,000 ft, "
                 "{exc_sl} kt at sea level; schedule S-3), so that a {U} ft/s gust met at that speed stays inside +{npos} and {nneg} "
                 "(PD-24 item 1). With the ruled rule's own gust speed at the speed (the spec's reading) nothing binds up to V_D "
                 "at and below {alt} ft: the smallest excursion is {ruled} kt, against V_D - V_C = {vdvc} kt.",
         "numbers": [n("exc", "p8", "ep3.stated_excursion_floor_kt", "kt", f), n("exc_full", "p8", "ep3.stated_excursion_kt", "kt", ".3f"),
                     n("alt", "p8", "ep3.altitude_limit_ft", "ft", ",.0f"),
                     n("exc_20", "p8", f"ep3.schedule.{res['ep3']['stated_reading']}.{j20}.excursion_kt", "kt", f),
                     n("exc_sl", "p8", "ep3.stated_at_sea_level_kt", "kt", f), n("U", "p8", "ep3.U_held_fps", "ft/s", ".0f"),
                     n("npos", "p5", "row3.limits.positive", "-", ".1f"), n("nneg", "p5", "row3.limits.negative_gust", "-", ".1f"),
                     n("ruled", "p8", "ep3.ruled_rule_smallest_up_to_limit_kt", "kt", f),
                     n("vdvc", "p8", "ep3.V_D_minus_V_C_kt", "kt", f)],
         "headline": "exc"},
        {"id": "EP-4", "title": "Dive margin",
         "text": "If the speed hold fails, a dive entered at V_C reaches V_D in as little as {t_min} s (45 deg path: {t_full45} s at "
                 "full power, {t_idle45} s at idle; schedule S-4), and the least height lost on the way is {h_min} ft. At idle on "
                 "a 5 deg path V_D is reached in {idle5} of {idle5_n} cases. The protection must stop the acceleration within "
                 "that time.",
         "numbers": [n("t_min", "p8", "ep4.shortest_time_s", "s", f),
                     n("t_full45", "p8", f"ep4.by_angle.{k_full45}.shortest_time_s", "s", f),
                     n("t_idle45", "p8", f"ep4.by_angle.{k_idle45}.shortest_time_s", "s", f),
                     n("h_min", "p8", "ep4.least_height_lost_ft", "ft", ",.0f"),
                     n("idle5", "p8", f"ep4.by_angle.{k_idle5}.reached", "-", "d"),
                     n("idle5_n", "p8", f"ep4.by_angle.{k_idle5}.cases", "-", "d")],
         "headline": "t_min"},
        {"id": "EP-5", "title": "Load-factor command limits",
         "text": "Commanded load factor between {neg_cmd} and +{pos_cmd}: the R9 limits +{pos} and {neg} less the record's {m} g margin "
                 "(PD-24 item 2). The R16 turn, n = {n16}, stays available: the stall allows {stall_r0} at the loiter speed and "
                 "20,000 ft ({stall_r1} with P2's C_L,max). The negative limit is reachable below V_C (negative corner {negc} kt "
                 "EAS at take-off weight), so the protection must hold it.",
         "numbers": [n("neg_cmd", "p8", "ep5.negative_command", "-", ".1f"), n("pos_cmd", "p8", "ep5.positive_command", "-", ".1f"),
                     n("pos", "r0_ledger", "requirements.limit_load_factor.value", "-", ".1f"),
                     n("neg", "r0_ledger", "requirements.negative_load_factor.value", "-", ".1f"),
                     n("m", "r0_ledger", "requirements.margin_gust_g.value", "g", ".1f"), n("n16", "p8", "ep5.n_r16", "-", ".3f"),
                     n("stall_r0", "p8", "ep5.stall_limited_n_at_loiter.r0", "-", ".3f"),
                     n("stall_r1", "p8", "ep5.stall_limited_n_at_loiter.p2_measured_r1", "-", ".3f"),
                     n("negc", "p5", "row3.manoeuvre.takeoff.negative_corner_kt", "kt EAS", f)],
         "headline": "pos_cmd"},
        {"id": "EP-6", "title": "Low-speed protection",
         "text": "No commanded speed below {k} V_stall clean at the current weight (R17). With r0's C_L,max {cl0}: {to0} kt EAS at "
                 "take-off weight, {zf0} kt at zero-fuel weight, {ob0} kt payload off with ballast. With P2's measured {cl1}, the "
                 "r1 value: {to1}, {zf1} and {ob1} kt EAS (schedule S-6).",
         "numbers": [n("k", "r0_ledger", "requirements.speed_over_stall.value", "-", ".1f"),
                     n("cl0", "r0_design", "CL_max.clean", "-", ".3f"), n("cl1", "p2b", "wing.measured.clean", "-", ".3f"),
                     n("to0", "p8", "ep6.points.r0.takeoff.floor_kt", "kt EAS", f), n("zf0", "p8", "ep6.points.r0.zero_fuel.floor_kt", "kt EAS", f),
                     n("ob0", "p8", "ep6.points.r0.payload_off_with_ballast.floor_kt", "kt EAS", f),
                     n("to1", "p8", "ep6.points.p2_measured_r1.takeoff.floor_kt", "kt EAS", f),
                     n("zf1", "p8", "ep6.points.p2_measured_r1.zero_fuel.floor_kt", "kt EAS", f),
                     n("ob1", "p8", "ep6.points.p2_measured_r1.payload_off_with_ballast.floor_kt", "kt EAS", f)],
         "headline": "to0"},
        {"id": "EP-7", "title": "Gust criterion above V_C",
         "text": "Between V_C and V_D the gust is {U_C} ft/s at V_C falling linearly to {U_D} ft/s at V_D (PD-8, the ruled rule). "
                 "At V_D the structure is cleared to the manoeuvre limit +{man} and to the ruled gust, worst {gup} / {gdn} payload "
                 "on ({obup} payload off with ballast). It is not cleared to a {U_C} ft/s gust at V_D: {hup} / {hdn}.",
         "numbers": [n("U_C", "p5", f"row3.points.{index_of(r3p, speed='V_C')}.U_de_fps", "ft/s", ".0f"),
                     n("U_D", "p5", f"row3.points.{index_of(r3p, speed='V_D')}.U_de_fps", "ft/s", ".0f"),
                     n("man", "p5", "row3.manoeuvre.takeoff.positive_at_V_D", "-", ".1f"),
                     n("gup", "p5", f"row3.points.{vd_up}.n_up", "-", ".3f"), n("gdn", "p5", f"row3.points.{vd_dn}.n_down", "-", ".3f"),
                     n("obup", "p5", f"row5.cases.payload_off_with_ballast.points.{ob_vd_up}.n_up", "-", ".3f"),
                     n("hup", "p5", f"row4.cases.ruled_held_30.points.{h_vd_up}.n_up", "-", ".3f"),
                     n("hdn", "p5", f"row4.cases.ruled_held_30.points.{h_vd_dn}.n_down", "-", ".3f")],
         "headline": "U_D"},
        {"id": "EP-8", "title": "Altitude limits",
         "text": "The protection holds the aircraft at or below {alt} ft, R12's ceiling requirement (PD-24 item 3; R12 asks for the "
                 "service ceiling {marg} ft above it; r0's service ceiling is {ceil} ft, P0's engine-cycle value {cyc_lo} to "
                 "{cyc_hi} ft). The engine's maximum operating altitude and its in-flight relight envelope are declared "
                 "assumptions with no source value (R-f); the mission altitude is {mis} ft.",
         "numbers": [n("alt", "r0_ledger", "requirements.ceiling_ft.value", "ft", ",.0f"),
                     n("marg", "r0_ledger", "requirements.margin_ceiling_ft.value", "ft", ",.0f"),
                     n("ceil", "r0_design", "performance.service_ceiling_ft", "ft", ",.0f"),
                     n("cyc_lo", "p0", "acceptance.3.reference.min", "ft", ",.0f"), n("cyc_hi", "p0", "acceptance.3.reference.max", "ft", ",.0f"),
                     n("mis", "r0_ledger", "requirements.mission_altitude_ft.value", "ft", ",.0f")],
         "headline": "alt"},
        {"id": "EP-9", "title": "Payload-off operating limit",
         "text": "Payload off, the aircraft flies only with at least {bal} lb of ballast at the payload station (P4b; PD-13). At "
                 "{W} lb the ruled gust at V_C and V_D stays inside: {up} / {dn}. The gust speed limit stays at V_D up to {clear} ft "
                 "and falls below V_C from {below} ft ({vbelow} kt EAS), above EP-8's altitude limit. Payload off without "
                 "ballast is not flown.",
         "numbers": [n("bal", "p4b", f"candidates.{chosen}.measures.payload_off.ballast_every_loading_lb", "lb", ".0f"),
                     n("W", "p5", "weights.payload_off_with_ballast", "lb", ",.1f"),
                     n("up", "p5", "row5.cases.payload_off_with_ballast.largest_up", "-", ".3f"),
                     n("dn", "p5", "row5.cases.payload_off_with_ballast.lowest_down", "-", ".3f"),
                     n("clear", "p5", f"row5.cases.payload_off_with_ballast.operating_limit.{last_clear}.altitude_ft", "ft", ",.0f"),
                     n("below", "p5", "row5.cases.payload_off_with_ballast.lowest_altitude_limited_below_V_C_ft", "ft", ",.0f"),
                     n("vbelow", "p5", f"row5.cases.payload_off_with_ballast.operating_limit.{first_below}.V_eas_kt", "kt EAS", f)],
         "headline": "bal"},
    ]
    words = {"cross_lo_w": WEIGHT_NAMES[min(res["ep2"]["crossover_ft"], key=res["ep2"]["crossover_ft"].get)],
             "cross_hi_w": WEIGHT_NAMES[max(res["ep2"]["crossover_ft"], key=res["ep2"]["crossover_ft"].get)]}
    for r in out:
        r["sources"] = sorted({x["record"] for x in r["numbers"]})
        r["statement"] = r["text"].format(**words, **{x["name"]: fmt(x) for x in r["numbers"]})
    return out


WEIGHT_NAMES = {"takeoff": "take-off weight", "zero_fuel": "zero-fuel weight", "payload_off_with_ballast": "payload off with ballast",
                "payload_off_full_fuel_with_ballast": "payload off, full fuel, with ballast"}


def fmt(x):
    """A number as the requirement prints it."""
    return format(x["value"], x["fmt"])


# ---- acceptance -------------------------------------------------------------------------------------------------
def acceptance(c, res):
    out = []
    # 1. no row blank
    blank = [r["id"] for r in res["rows"] if not r["statement"].strip() or not r["numbers"] or not r["sources"]
             or any(x["value"] is None for x in r["numbers"])]
    ids = [r["id"] for r in res["rows"]] == [f"EP-{i}" for i in range(1, 10)]
    out.append({"row": 1, "what": "no row is blank: EP-1 to EP-9 each have a statement, numbers and a record",
                "blank_rows": blank, "verdict": "pass" if ids and not blank else "fail"})
    # 2. every number read from its record (re-read from the files; P8's own from this result)
    files = {k: read_record(k) for k in RECORDS if k != "p8"}
    wrong = [f"{r['id']} {x['name']}" for r in res["rows"] for x in r["numbers"]
             if pick(res if x["record"] == "p8" else files[x["record"]], x["key"]) != x["value"]]
    out.append({"row": 2, "what": "every number equals the value at its record and key", "n_numbers": sum(len(r["numbers"]) for r in res["rows"]),
                "wrong": wrong, "verdict": "pass" if not wrong else "fail"})
    # 3. EP-3 against P5: the load factor recomputed at V_C plus the allowed excursion
    e3 = res["ep3"]
    lim = e3["limits"]
    V_C, _ = speeds(c)
    V = V_C + e3["stated_excursion_kt"] * KT
    W = flown_weights(c)
    b = e3["binding"]
    n_up, n_down = gust_at(c, W[b["weight"]], b["altitude_ft"], V, e3["U_held_fps"])
    at_limit = abs(n_down - lim["negative_gust"]) if b["limited_by"] == "negative" else abs(n_up - lim["positive"])
    worst_in = []
    for h in [x["altitude_ft"] for x in e3["schedule"][e3["stated_reading"]] if x["altitude_ft"] <= e3["altitude_limit_ft"]]:
        for w in W.values():
            u, dn = gust_at(c, w, h, V, e3["U_held_fps"])
            worst_in.append(max(u - lim["positive"], lim["negative_gust"] - dn))
    p5_vc = []
    for p in c["records"]["p5"]["row3"]["points"]:
        if p["speed"] == "V_C":
            u, dn = gust_at(c, p["W_lb"], p["altitude_ft"], p["V_eas_kt"] * KT)
            p5_vc.append(abs(u / p["n_up"] - 1.0))
    ruled = [x for x in e3["schedule"]["ruled_rule"] if x["altitude_ft"] <= e3["altitude_limit_ft"]]
    ruled_to_vd = all(x["limited_by"] is None for x in ruled)
    ok3 = at_limit <= 1e-6 and max(worst_in) <= 1e-9 and max(p5_vc) <= 1e-9
    out.append({"row": 3, "what": "EP-3 consistent with P5: the load factor at V_C plus the allowed excursion, recomputed with P5's code",
                "V_eas_kt": V / KT, "binding": b, "n_up": n_up, "n_down": n_down, "distance_to_limit": at_limit,
                "largest_excess_over_limits": max(worst_in), "p5_V_C_points_largest_deviation": max(p5_vc),
                "ruled_rule_clears_to_V_D_up_to_altitude_limit": ruled_to_vd, "verdict": "pass" if ok3 else "fail"})
    # 4. EP-7 against P5: the V_D points recomputed
    dev7 = []
    for p in c["records"]["p5"]["row3"]["points"] + c["records"]["p5"]["row5"]["cases"]["payload_off_with_ballast"]["points"]:
        if p["speed"] == "V_D":
            u, dn = gust_at(c, p["W_lb"], p["altitude_ft"], p["V_eas_kt"] * KT)
            dev7 += [abs(u / p["n_up"] - 1.0), abs(dn - p["n_down"])]
    out.append({"row": 4, "what": "EP-7 consistent with P5: the gust load factors at V_D recomputed with P5's code",
                "largest_deviation": max(dev7), "tolerance": 1e-9, "verdict": "pass" if max(dev7) <= 1e-9 else "fail"})
    # 5. EP-5 keeps R16's turn
    e5 = res["ep5"]
    ok5 = round(e5["n_r16"], 3) == 1.155 and e5["r16_available"]
    out.append({"row": 5, "what": "EP-5 keeps R16's turn, n = 1.155, inside the command limit and below the stall at loiter",
                "n_r16": e5["n_r16"], "positive_command": e5["positive_command"], "stall_limited_n": e5["stall_limited_n_at_loiter"],
                "verdict": "pass" if ok5 else "fail"})
    # coding checks
    out.append({"row": 6, "what": "coding check: power for level flight at r0's level top speed equals full throttle",
                "worst": res["ep2"]["check"]["worst"], "tolerance": res["ep2"]["check"]["tolerance"], "verdict": res["ep2"]["check"]["verdict"]})
    out.append({"row": 7, "what": "coding check: the dive integration against its closed form with no force",
                "worst": res["ep4"]["closed_form_check"]["deviation"], "tolerance": res["ep4"]["closed_form_check"]["tolerance"],
                "verdict": res["ep4"]["closed_form_check"]["verdict"]})
    out.append({"row": 8, "what": "coding check: V_stall at take-off weight and r0's C_L,max equals r0's recorded value",
                "worst": abs(res["ep6"]["check"]["deviation"]), "tolerance": res["ep6"]["check"]["tolerance"], "verdict": res["ep6"]["check"]["verdict"]})
    return out


# ---- r1 findings ------------------------------------------------------------------------------------------------
def r1_findings(c, res):
    """EP-2, EP-3 and EP-6 again with every weight raised by P4b's r1 empty-weight change (r0's polar and wing
    unchanged), EP-6 with P2's C_L,max."""
    dw = c["r1_empty_weight_change_lb"]
    e2 = ep2(c, dw, with_p6=False)
    e3 = ep3(c, dw)
    e6 = ep6(c, dw)
    i_sl = index_of(e2["schedule"], altitude_ft=0.0)
    i_20 = index_of(e2["schedule"], altitude_ft=20000.0)
    return {"empty_weight_change_lb": dw,
            "ep2_limit_hp": {"sea_level": [res["ep2"]["schedule"][i_sl]["limit_hp"], e2["schedule"][i_sl]["limit_hp"]],
                             "20000_ft": [res["ep2"]["schedule"][i_20]["limit_hp"], e2["schedule"][i_20]["limit_hp"]]},
            "ep2_crossover_ft": [[res["ep2"]["crossover_lowest_ft"], res["ep2"]["crossover_highest_ft"]],
                                 [e2["crossover_lowest_ft"], e2["crossover_highest_ft"]]],
            "ep3_excursion_kt": [res["ep3"]["stated_excursion_kt"], e3["stated_excursion_kt"]],
            "ep6_floor_r1_kt": {wl: e6["points"]["p2_measured_r1"][wl]["floor_kt"] for wl in e6["weights"]},
            "ep6_floor_r0_kt": {wl: res["ep6"]["points"]["r0"][wl]["floor_kt"] for wl in res["ep6"]["weights"]},
            "not_changed": "r1's drag (longer aft body, PD-21) and wing are not in these numbers; r0's polar is used."}


# ---- the run ----------------------------------------------------------------------------------------------------
def run(out, log=print):
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P8 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    c = context()
    log(f"commit {tree['commit']}, clean tree; r0 rebuilt")
    files = dict({k: REPO / v for k, v in RECORDS.items() if k != "p8"}, choices=CHOICES,
                 engine_table=REPO / "runs/task12/pd/2026-11-27/p0/r0/m250_table.json")
    V_C, V_D = speeds(c)
    res = {"inputs": dict(tree, command="python -m prelim.p8_envelope " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P8", python=platform.python_version(), numpy=np.__version__,
                          scipy=scipy.__version__, pyyaml=yaml.__version__, matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()}, sha256={k: sha256(p) for k, p in files.items()}),
           "review": REVIEW, "evidence_class": EVIDENCE, "choices": c["choices"], "rebuild_check": c["rebuild_check"],
           "r0": {"V_C_kt": V_C / KT, "V_D_kt": V_D / KT, "S_ft2": c["b"]["geom"]["S"], "weights": flown_weights(c)}}
    log("EP-2: power for level flight at V_C")
    res["ep2"] = ep2(c, log=log)
    log("EP-3: overspeed margin")
    res["ep3"] = ep3(c)
    log("EP-4: dives")
    res["ep4"] = ep4(c)
    res["ep5"] = ep5(c)
    res["ep6"] = ep6(c)
    res["rows"] = rows(res, c["records"])
    res["acceptance"] = acceptance(c, res)
    log("acceptance: " + ", ".join(f"{a['row']} {a['verdict']}" for a in res["acceptance"]))
    res["r1"] = r1_findings(c, res)
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == tree["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p8.json").write_text(json.dumps(p5._plain(res), indent=1))
    log(f"done ({res['runtime_s']:.0f} s)")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--requirement")
    ap.add_argument("--report-only", action="store_true", help="write the report and the requirement from OUT/p8.json")
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
    from prelim import p8_report
    if a.requirement:
        (REPO / a.requirement).write_text(p8_report.requirement_text(out))
    if a.report:
        (REPO / a.report).write_text(p8_report.report_text(out))


if __name__ == "__main__":
    main()

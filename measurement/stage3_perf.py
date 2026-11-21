"""Stage 3 performance measurements of the frozen Stage 1 design with book relations other than
the ones Stage 1 used. Spec docs/specs/task12_drone_conceptual_design.md section 7.1, tolerances 7.1a.

    python -m measurement.stage3_perf --design runs/task12/stage1/2026-11-21d/design_pusher.json \
        --out runs/task12/stage3/2026-11-21/perf.json --report docs/validation/<file>.md

Scope (7.1b): the engine rows, the vortex-lattice aero rows (measurement/stage3_aero.py) and the
SU2 section row are not here. Every row below reports the Stage 1 value, the Stage 3 value, the
deviation, the 7.1a tolerance and a verdict; nothing is adjusted when a row is outside tolerance.

How the design is read. The record (design_pusher.json) holds most Stage 1 values. Where a Stage 1
value or an input is not in the record it is recomputed with the `conceptual` code from the
record's own inputs: the design is rebuilt at the record's W0, wing loading, aspect ratio and tail
scale from the ledger copy beside the record and the TP100 table, and the rebuild is checked
against the record (fuel and the five constraint powers) before anything is measured. A row says
which of the two it used.

Verdicts: "within" and "outside" compare |deviation| with the tolerance; "not judged" is a
cross-check the spec says not to judge; "not computed" means the available modules cannot form the
row, with the reason in the note.
"""
import argparse
import hashlib
import json
import math
import platform
import subprocess
from pathlib import Path

import numpy as np

from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import sizing, uav
from conceptual.engine_model import TP100_TABLE, TableEngine
from conceptual.units import KT, NM, RHO0, G, isa
from measurement import anderson as A
from measurement import mattingly as M

REPO = Path(__file__).resolve().parents[1]
CHOSEN_ENGINE = {"name": "PBS_TP100", "bhp": 241.0, "weight_lb": 135.8}
REBUILD_TOLERANCE = 1e-6          # relative; the rebuild must reproduce the record to this
# Fig. 2.55 (p. 129) draws 1.5 x the Karman-Schoenherr flat-plate friction as the dashed curve
# above which most of the book's jet data lie; (2.29) (p. 108) is its explicit form.
CFE_OVER_FLAT_PLATE = 1.5
CD0_REFERENCE_SPEED = 250.0       # ft/s, the speed at which Stage 1 evaluated CD0 at mission altitude


# ---- reading the design --------------------------------------------------------------------------
def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild(design_path):
    """Record, ledger values (with the record's tail scale and the engine's datasheet SFC, as
    uav.evaluate does) and the rebuilt Stage 1 state at the record's W0. Raises if the rebuild
    does not reproduce the record."""
    path = Path(design_path)
    d = json.loads(path.read_text())
    ledger_path = path.parent / "ledger.yaml"
    L, _ = uav.load_ledger(ledger_path)
    L = dict(L, ht_volume_scale=d["ht_volume_scale"], cbhp_cruise=0.901, cbhp_loiter=0.901)
    eng = dict(CHOSEN_ENGINE, model=TableEngine(TP100_TABLE))
    b = uav._build(d["W0_lb"], d["concept"], d["W_S"], d["A"], L, d["fuel_lb"], eng)
    check = {"fuel_lb": [d["fuel_lb"], b["fuel"]]}
    for k, v in d["power_required_hp"].items():
        check[f"power_{k}_hp"] = [v, b["power_req"][k]]
    for k, (rec, new) in check.items():
        if abs(new / rec - 1.0) > REBUILD_TOLERANCE:
            raise ValueError(f"rebuild does not reproduce the record: {k} {rec} against {new}")
    return d, L, b, ledger_path, {k: {"record": r, "rebuilt": n} for k, (r, n) in check.items()}


# ---- rows -----------------------------------------------------------------------------------------
def make_row(rid, quantity, unit, stage1, stage1_source, stage3, source, tolerance, tol_kind,
             note="", judged=True):
    """One table row. Deviation is (Stage 3 - Stage 1)/Stage 1 for tol_kind 'relative', the
    plain difference for 'absolute'. The verdict follows from deviation and tolerance."""
    row = {"id": rid, "quantity": quantity, "unit": unit, "stage1": stage1,
           "stage1_source": stage1_source, "stage3": stage3, "source": source,
           "deviation": None, "deviation_kind": tol_kind, "tolerance": tolerance, "note": note}
    if stage3 is None:
        row["verdict"] = "not computed"
        return row
    row["deviation"] = (stage3 / stage1 - 1.0) if tol_kind == "relative" else stage3 - stage1
    if not judged:
        row["verdict"] = "not judged"
    else:
        row["verdict"] = "within" if abs(row["deviation"]) <= tolerance else "outside"
    return row


RECORD = "record"
RECOMPUTED = "recomputed with conceptual code from the record's inputs"


# ---- installed power by constraint: Mattingly (2.11) --------------------------------------------
def _min_power_mattingly(W0, S, rho, CD0, K, eta, ps, lapse, n=1.0, clmax=1.35, floor=1.2):
    """Smallest sea-level-rated shaft hp from (2.11) over speed, from `floor` x stall upward on a
    0.1 ft/s grid (Stage 1 used a 1 ft/s grid from the same floor)."""
    W_S = W0 / S
    v_lo = floor * perf.stall_speed(n * W_S, rho, clmax)
    best = None
    for i in range(4000):
        V = v_lo + 0.1 * i
        q = 0.5 * rho * V ** 2
        hp = W0 * M.shaft_power_loading(W_S, q, V, 1.0, lapse, K, 0.0, CD0, eta, 0.0, n, ps)
        best = hp if best is None or hp < best else best
    return best


def power_rows(d, L, b):
    W0, S, K, eta = d["W0_lb"], b["geom"]["S"], d["K"], L["eta_p"]
    model, clean = b["engine_model"], b["clmax"]["clean"]
    sl, alt, ceil = isa(0.0), isa(L["mission_altitude_ft"]), isa(L["ceiling_ft"])
    W_S = W0 / S
    src = "Mattingly (2.11) p. 24 with T = 550 eta_p P/V (shaft_power_loading)"
    rec = d["power_required_hp"]
    out = []
    # climb at sea level, full lapse 1
    p = _min_power_mattingly(W0, S, sl["rho"], d["CD0"]["sea_level"], K, eta,
                             L["climb_rate_sl_fpm"] / 60.0, 1.0, clmax=clean)
    out.append(make_row("power_climb_sl", "installed power, sea-level climb 1,000 ft/min", "hp",
                        rec["climb_sl"], RECORD, p, src, 0.05, "relative",
                        "CD0 at sea level from the record; minimum over speed from 1.2 V_stall."))
    # ceiling: CD0 and lapse at the climb-speed floor at the ceiling, as Stage 1 evaluated them
    v_ceil = L["climb_speed_over_stall"] * perf.stall_speed(W_S, ceil["rho"], clean)
    cd0_c = uav._polar(b["geom"], L, v_ceil, ceil, b["bhp"])[0]
    lap_c = model.lapse(L["ceiling_ft"], v_ceil / KT)
    p = _min_power_mattingly(W0, S, ceil["rho"], cd0_c, K, eta, L["ceiling_rate_fpm"] / 60.0,
                             lap_c, clmax=clean)
    out.append(make_row("power_ceiling", "installed power, 100 ft/min at the ceiling altitude "
                        f"{L['ceiling_ft']:.0f} ft", "hp", rec["ceiling"], RECORD, p, src,
                        0.05, "relative",
                        "CD0 at the climb-speed floor and the App. K lapse there are recomputed "
                        "with conceptual code (not in the record); the lapse is the engine "
                        "table's, an input shared with Stage 1."))
    out.append(make_row("power_takeoff", "installed power, take-off over 50 ft in the field length",
                        "hp", rec["takeoff"], RECORD, None, "Mattingly (2.22) take-off", 0.05,
                        "relative",
                        "not computed: measurement/mattingly.py has no (2.22) take-off relation, "
                        "and (2.11) alone does not give a distance-based power."))
    # sustained turn at loiter speed and altitude
    V = b["V_loiter_start"]
    phi = math.radians(L["turn_bank_deg"])
    n_turn = M.turn_load_factor(G * math.tan(phi) / V, V)          # (2.16): n = 1/cos(bank)
    lap = model.lapse(L["mission_altitude_ft"], V / KT)
    q = 0.5 * alt["rho"] * V ** 2
    p = W0 * M.shaft_power_loading(W_S, q, V, 1.0, lap, K, 0.0, d["CD0"]["mission_altitude"], eta,
                                   0.0, n_turn, 0.0)
    out.append(make_row("power_turn", "installed power, sustained 30 deg turn at loiter speed",
                        "hp", rec["turn_at_loiter"], RECORD, p,
                        src + "; n from (2.16) p. 27", 0.05, "relative",
                        "Loiter speed (Stage 1's best-endurance speed at W0 with the 1.3 V_stall "
                        "floor) is recomputed with conceptual code; CD0 from the record."))
    V = b["V_cruise_start"]
    lap = model.lapse(L["mission_altitude_ft"], V / KT)
    q = 0.5 * alt["rho"] * V ** 2
    p = W0 * M.shaft_power_loading(W_S, q, V, 1.0, lap, K, 0.0, d["CD0"]["mission_altitude"], eta)
    out.append(make_row("power_cruise", "installed power, level cruise at mission altitude",
                        "hp", rec["cruise_at_altitude"], RECORD, p, src, 0.05, "relative",
                        "Cruise speed (Stage 1's best-range speed at W0) recomputed with "
                        "conceptual code; CD0 from the record."))
    return out


# ---- mission fuel: Mattingly ch. 3 fractions -----------------------------------------------------
def mission_fuel_mattingly(d, L, b):
    """Stage 1's mission replayed with Mattingly's segment fractions in place of Raymer's. The speed
    on each sub-step, its SFC (from the engine table, as Stage 1 used it), CD0 and the headwind
    air-distance factor V/(V - V_w) are Stage 1's; only the fraction relation is Mattingly's:
    climb (3.17)/(3.20) p. 61-62, cruise (3.23) p. 63, loiter (3.36)-(3.37) p. 66-67, TSFC from
    C_bhp by C = C_bhp V/(550 eta_p). Take-off, landing, and the 1.06 reserve factor are taken as
    Stage 1 had them (Mattingly's module has no tested relation for them)."""
    W0, S, K, eta = d["W0_lb"], b["geom"]["S"], b["K"], L["eta_p"]
    geom, bhp, model, clmax = b["geom"], b["bhp"], b["engine_model"], b["clmax"]
    sl, alt = isa(0.0), isa(L["mission_altitude_ft"])
    h_alt = L["mission_altitude_ft"]
    stage1 = {r["segment"]: r for r in d["mission"]}
    legs = []

    def frac_of(name):
        return stage1[name]["W_end"] / stage1[name]["W_start"]

    W = W0 * frac_of("takeoff")
    legs.append({"segment": "takeoff", "fraction_stage3": frac_of("takeoff"),
                 "fraction_stage1": frac_of("takeoff"), "basis": "taken from the record"})
    # climb: the inputs (best-climb speed, cruise speed, D/T, SFC) as uav._mission forms them
    CD0_sl = uav._polar(geom, L, 200.0, sl, bhp)[0]
    v_lo = L["climb_speed_over_stall"] * perf.stall_speed(W / S, sl["rho"], clmax["clean"])
    V_cl = perf.best_rate_of_climb(W, S, sl["rho"], CD0_sl, K, bhp, eta, v_lo, v_lo + 350.0)[1]
    CD0_alt = uav._polar(geom, L, CD0_REFERENCE_SPEED, alt, bhp)[0]
    V_cr = uav._cruise_speed(W, S, alt["rho"], CD0_alt, K, clmax["clean"], L, "range")[0]
    lapse = model.lapse(h_alt, V_cl / KT)
    d_t = 0.5 * (perf.drag(W, S, sl["rho"], V_cl, CD0_sl, K) / prop.thrust_from_power(bhp, eta, V_cl)
                 + perf.drag(W, S, alt["rho"], V_cl, CD0_alt, K)
                 / prop.thrust_from_power(bhp * lapse, eta, V_cl))
    dhe = sizing.energy_height_change(0.0, V_cl, h_alt, V_cr)
    c_cl = model.bsfc(0.5 * h_alt, V_cl / KT, bhp * model.lapse(0.5 * h_alt, V_cl / KT))
    f = M.climb_fraction(M.equivalent_tsfc(c_cl, V_cl, eta), V_cl, dhe, min(d_t, 0.95))
    legs.append({"segment": "climb", "fraction_stage3": f, "fraction_stage1": frac_of("climb"),
                 "basis": "Mattingly (3.17)/(3.20); best-climb speed, D/T, SFC as Stage 1 formed them"})
    W *= f

    def leg(W, name, distance_ft=None, time_s=None):
        W_in, n = W, (uav.N_CRUISE_STEPS if distance_ft else uav.N_LOITER_STEPS)
        mode = "range" if distance_ft else "loiter"
        for _ in range(n):
            CD0 = uav._polar(geom, L, CD0_REFERENCE_SPEED, alt, bhp)[0]
            V, _, cbhp = uav._leg_speed(W, S, alt, h_alt, CD0, K, clmax["clean"], L, mode, model, bhp)
            CD0 = uav._polar(geom, L, V, alt, bhp)[0]
            q = 0.5 * alt["rho"] * V ** 2
            CL = W / (q * S)
            CD_over_CL = (CD0 + K * CL ** 2) / CL
            tsfc = M.equivalent_tsfc(cbhp, V, eta)
            if distance_ft:
                vw = L.get("headwind_kt", 0.0) * KT
                W *= M.cruise_fraction(tsfc, CD_over_CL, distance_ft / n * V / (V - vw), V)
            else:
                W *= M.loiter_fraction(tsfc, CD_over_CL, time_s / n)
        legs.append({"segment": name, "fraction_stage3": W / W_in,
                     "fraction_stage1": frac_of(name),
                     "basis": "Mattingly (3.23) per sub-step" if distance_ft
                     else "Mattingly (3.36)-(3.37) per sub-step"})
        return W

    W = leg(W, "cruise_out", distance_ft=L["radius_nm"] * NM)
    W = leg(W, "loiter", time_s=L["loiter_h"] * 3600.0)
    W = leg(W, "cruise_back", distance_ft=L["radius_nm"] * NM)
    legs.append({"segment": "landing", "fraction_stage3": frac_of("landing"),
                 "fraction_stage1": frac_of("landing"), "basis": "taken from the record"})
    W_end = W * frac_of("landing")
    fuel = sizing.RESERVE_FACTOR * (W0 - W_end)
    return fuel, legs


# ---- take-off weight: Anderson ch. 8 -------------------------------------------------------------
def anderson_w0(d, L, b, empty_fraction=A.EMPTY_FRACTION_HISTORICAL):
    """Anderson's first estimate: W0 = W_fixed/(1 - Wf/W0 - 0.62), (8.4)-(8.5) p. 399-400, fuel
    fraction (8.6)-(8.8) p. 402 with take-off 0.97 (8.9), climb 0.985 (8.10), cruise (5.153),
    loiter (5.169), landing 0.995, and the book's own best-range and best-endurance speeds. Inputs
    taken from the record or the ledger copy: polar CD0 (mission altitude) and K, SFC each leg used,
    eta_p, radius, headwind, loiter time, W/S. Returns a dict, or one with a reason. The empty
    fraction defaults to Anderson's 0.62; the diagnostic run passes Stage 1's."""
    eta, CD0, K, WS = L["eta_p"], d["CD0"]["mission_altitude"], d["K"], d["W_S"]
    rho = isa(L["mission_altitude_ft"])["rho"]
    vw = L["headwind_kt"] * KT
    V = A.speed_ld_max(WS, rho, CD0, K)
    if V <= vw:
        return {"reason": "the (L/D)max speed is below the headwind"}
    LD, k32 = A.ld_max(CD0, K), A.cl32_cd_max(CD0, K)
    c_cr, c_lo = A.cbhp_to_c(d["cbhp_used"]["cruise"]), A.cbhp_to_c(d["cbhp_used"]["loiter"])
    f_cr = A.breguet_cruise_fraction(L["radius_nm"] * NM * V / (V - vw), c_cr, eta, LD)
    E = L["loiter_h"] * 3600.0
    W0 = 3000.0
    for _ in range(500):
        S = W0 / WS
        Wa = W0 * 0.97 * 0.985 * f_cr
        # (5.169) solved for W1
        W1 = (Wa ** -0.5 + E * c_lo / (eta * math.sqrt(2.0 * rho * S) * k32)) ** -2
        assert abs(A.endurance_s(eta, c_lo, rho, S, k32, Wa, W1) - E) < 1e-3
        f_lo = W1 / Wa
        ff = A.fuel_fraction([0.97, 0.985, f_cr, f_lo, f_cr, 0.995])
        if 1.0 - ff - empty_fraction <= 0.0:
            return {"reason": "fuel and empty fractions leave no payload fraction"}
        W_new = A.takeoff_weight(d["payload_lb"], ff, empty_fraction)
        if abs(W_new - W0) < 1e-6:
            break
        W0 = 0.5 * (W0 + W_new)
    else:
        return {"reason": "the W0 iteration did not converge"}
    g = b["geom"]
    areas = (g["s_exposed"], d["horizontal_tail"]["area"], d["vertical_tail"]["area"],
             d["fuselage"]["s_wet"])
    rows = A.iterate_buildup(d["payload_lb"], ff, areas, d["engine"]["weight_lb"], W_new)
    return {"W0": W_new, "fuel_fraction": ff, "f_cruise": f_cr, "f_loiter": f_lo, "LD_max": LD,
            "V_best_range_kt": V / KT, "buildup_W0": rows[-1][2], "buildup_We": rows[-1][0],
            "buildup_passes": len(rows), "buildup_areas_ft2": list(areas)}


# ---- zero-lift drag: Anderson (2.37) -------------------------------------------------------------
def cfe_anderson(Re):
    """Equivalent skin-friction coefficient: CFE_OVER_FLAT_PLATE x the White-Christoph flat-plate
    value (2.29) p. 108, read as the dashed curve of Fig. 2.55 p. 129 (a chart, so a reading)."""
    return CFE_OVER_FLAT_PLATE * 0.42 / math.log(0.056 * Re) ** 2


def cd0_anderson(d, L, b):
    g, alt = b["geom"], isa(L["mission_altitude_ft"])
    s_wet = (g["s_wet_wing"] + g["s_wet_fus"] + g["s_wet_ht"] + g["s_wet_vt"]
             + g["s_wet_sponsons"])
    Re = alt["rho"] * CD0_REFERENCE_SPEED * g["L_f"] / alt["mu"]
    cfe = cfe_anderson(Re)
    cd0 = s_wet / g["S"] * cfe                                   # (2.37) p. 128
    target = d["CD0"]["mission_altitude"]
    return {"CD0": cd0, "S_wet_ft2": s_wet, "S_wet_over_S": s_wet / g["S"], "Re_fuselage": Re,
            "Cfe": cfe, "Cfe_flat_plate_only": cfe / CFE_OVER_FLAT_PLATE,
            "Cfe_for_Stage1_CD0": target * g["S"] / s_wet}


# ---- speeds, climb, ceiling: Anderson ch. 5 ------------------------------------------------------
def ceiling_anderson(d, L, b):
    """Highest altitude where Anderson's best climb rate (5.121) p. 277 is 100 ft/min, by bisection.
    Power: the engine table's full-throttle shaft hp at the climb speed; CD0 recomputed at each
    altitude and climb speed as Stage 1 did; no 1.2 V_stall floor (the closed form has none)."""
    W0, K, eta = d["W0_lb"], d["K"], L["eta_p"]
    model, W_S = b["engine_model"], d["W_S"]

    def roc(h):
        a = isa(h)
        V = L["climb_speed_over_stall"] * perf.stall_speed(W_S, a["rho"], b["clmax"]["clean"])
        for _ in range(4):
            cd0 = uav._polar(b["geom"], L, V, a, b["bhp"])[0]
            hp = model.power_available(h, V / KT)
            r = A.max_rate_of_climb_prop(eta * hp * 550.0 / W0, W_S, a["rho"], cd0, K)
            V = A.speed_cl32_cd_max(W_S, a["rho"], cd0, K)
        return r

    target = L["ceiling_rate_fpm"] / 60.0
    lo, hi = 0.0, 60000.0
    if roc(lo) < target:
        return 0.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if roc(mid) >= target else (lo, mid)
    return lo


def speed_rows(d, L, b):
    WS, K = d["W_S"], d["K"]
    alt, sl = isa(L["mission_altitude_ft"]), isa(0.0)
    cd0 = d["CD0"]["mission_altitude"]
    note = ("Stage 1 value: Raymer's closed form (17.2, p. 457-459) at W0, mission altitude and the "
            "record's CD0 there (recomputed, not in the record). The mission itself flew other "
            "speeds (engine-table SFC, headwind, 1.3 V_stall floor).")
    out = [make_row("v_best_range", "best-range speed (L/D max), mission altitude", "kt",
                    perf.speed_max_ld(WS, alt["rho"], cd0, K)[0] / KT, RECOMPUTED,
                    A.speed_ld_max(WS, alt["rho"], cd0, K) / KT, "Anderson (5.34) p. 220",
                    0.03, "relative", note),
           make_row("v_best_endurance", "best-endurance speed (C_L^1.5/C_D max), mission altitude",
                    "kt", perf.speed_min_power(WS, alt["rho"], cd0, K)[0] / KT, RECOMPUTED,
                    A.speed_cl32_cd_max(WS, alt["rho"], cd0, K) / KT, "Anderson (5.41) p. 221",
                    0.03, "relative", note)]
    P_over_W = L["eta_p"] * d["bhp_sl"] * 550.0 / d["W0_lb"]
    rc = A.max_rate_of_climb_prop(P_over_W, WS, sl["rho"], d["CD0"]["sea_level"], K) * 60.0
    v_cl = A.speed_cl32_cd_max(WS, sl["rho"], d["CD0"]["sea_level"], K) / KT
    out.append(make_row("roc_sl", "sea-level rate of climb at W0", "ft/min",
                        d["performance"]["roc_sl_fpm"], RECORD, rc,
                        "Anderson (5.121) p. 277 (5.122 misprinted, per the notes)", 0.03,
                        "relative",
                        "Rated 241 hp at sea level, eta_p 0.8, CD0 at sea level from the record, "
                        "as Stage 1."))
    out.append(make_row("v_best_climb", "best-climb speed, sea level", "kt",
                        d["performance"]["v_best_climb_kt"], RECORD, v_cl,
                        "Anderson (5.118)/(5.41) p. 221, 277", 0.03, "relative",
                        "Stage 1 searches speeds from 1.2 V_stall upward (Raymer p. 489) and "
                        "lands on that floor; the closed form has no floor."))
    ceil = ceiling_anderson(d, L, b)
    out.append(make_row("ceiling", "service ceiling (100 ft/min) at W0", "ft",
                        d["performance"]["service_ceiling_ft"], RECORD, ceil,
                        "Anderson (5.121) p. 277 with the App. K lapse", 1000.0, "absolute",
                        "Same engine table as Stage 1 (shared input); CD0 recomputed per "
                        "altitude; the closed form has no 1.2 V_stall floor, Stage 1 does."))
    return out


def vn_rows(d, L, b):
    v = A.corner_speed(d["n_limit"], d["W_S"], RHO0, d["CL_max"]["clean"]) / KT
    out = [make_row("v_corner", "corner speed V*, sea level, EAS", "kt",
                    d["vn"]["V_corner_eas_kt"], RECORD, v, "Anderson (6.54) p. 343", 0.05,
                    "relative",
                    "n_limit (3.8, the requirement) and clean CL_max 1.35 from the record. The "
                    "same V = sqrt(2 n W/S/(rho CL_max)) as Stage 1's, so it checks the arithmetic.")]
    out.append(make_row("gust_n", "gust load factors (V_C and V_D points)", "-",
                        d["n_gust"], RECORD, None, "Anderson ch. 6 gust relation", 0.05,
                        "relative",
                        "not computed: measurement/anderson.py has no gust load factor relation."))
    return out


def field_rows(d):
    p = d["performance"]
    why = ("not computed: measurement/anderson.py has no ground-roll or landing relation "
           "((6.95) p. 393 is not implemented).")
    return [make_row("takeoff_distance", "take-off distance over 50 ft, sea level", "ft",
                     p["takeoff_ft"], RECORD, None, "Anderson (6.95) p. 393", 0.15, "relative", why),
            make_row("landing_distance", "landing distance over 50 ft, sea level", "ft",
                     p["landing_ft"], RECORD, None, "Anderson ch. 6 landing", 0.15, "relative",
                     why)]


def stability_rows(d):
    why = ("not computed: measurement/anderson.py has no static-stability relation, and the spec "
           "wants the downwash from the vortex lattice (measurement/stage3_aero.py computes the "
           "static margin).")
    lay = d["layout"]
    return [make_row("sm_full", "static margin, full fuel", "MAC", lay["sm_full"], RECORD, None,
                     "Anderson (8.76)-(8.78) p. 444", 0.03, "absolute", why),
            make_row("sm_empty", "static margin, empty fuel", "MAC", lay["sm_empty"], RECORD, None,
                     "Anderson (8.76)-(8.78) p. 444", 0.03, "absolute", why)]


# ---- driver ----------------------------------------------------------------------------------------
def compute(design_path):
    d, L, b, ledger_path, check = rebuild(design_path)
    rows = power_rows(d, L, b)
    fuel3, legs = mission_fuel_mattingly(d, L, b)
    rows.append(make_row("mission_fuel", "mission fuel (200 nm out + 8 h + 200 nm back, headwind)",
                         "lb", d["fuel_lb"], RECORD, fuel3,
                         "Mattingly (3.17), (3.23), (3.36)-(3.37) p. 61-67", 0.05, "relative",
                         "Same speeds, SFC and headwind air distance as Stage 1; the fraction "
                         "relations reduce algebraically to Raymer's, so this checks the coding. "
                         "Take-off, landing and the 1.06 reserve are Stage 1's."))
    aw = anderson_w0(d, L, b)
    if "reason" not in aw:
        # diagnostic, not a row: the same route with Stage 1's own empty fraction isolates the
        # effect of Anderson's historical 0.62
        ef = d["We_lb"] / d["W0_lb"]
        alt = anderson_w0(d, L, b, ef)
        aw["diagnostic_stage1_empty_fraction"] = ef
        aw["diagnostic_W0_at_stage1_empty_fraction"] = alt.get("W0")
    if "reason" in aw:
        rows.append(make_row("w0_first", "take-off weight, Anderson first estimate", "lb",
                             d["W0_lb"], RECORD, None, "Anderson (8.4)-(8.5) p. 399-400", 0.10,
                             "relative", "not computed: " + aw["reason"]))
    else:
        rows.append(make_row("w0_first", "take-off weight, Anderson first estimate (empty "
                             "fraction 0.62)", "lb", d["W0_lb"], RECORD, aw["W0"],
                             "Anderson (8.4)-(8.5) p. 399-400, (8.6)-(8.8) p. 402, (5.153), (5.169)",
                             0.10, "relative",
                             "Anderson's own best-range and best-endurance speeds and (L/D)max "
                             "(no 1.3 V_stall floor, headwind applied to the air distance at his "
                             "best-range speed); polar, SFC used, eta_p, radius, headwind, loiter "
                             "time and W/S from the record or its ledger copy."))
        rows.append(make_row("w0_buildup", "take-off weight, Anderson build-up (8.83) "
                             "(same-author cross-check)", "lb", d["W0_lb"], RECORD, aw["buildup_W0"],
                             "Anderson (8.83a-g) p. 449, section 8.7 p. 449-453", None, "relative",
                             "Raymer's Table 15.2 approximate method, so not independent: reported, "
                             "not judged (spec 7.1a). Uses the first-estimate fuel fraction.",
                             judged=False))
    cd0 = cd0_anderson(d, L, b)
    rows.append(make_row("cd0", "zero-lift drag coefficient, mission altitude, clean", "-",
                         d["CD0"]["mission_altitude"], RECORD, cd0["CD0"],
                         "Anderson (2.37) p. 128 with Cfe from (2.29) p. 108 and Fig. 2.55 p. 129",
                         0.10, "relative",
                         "S_wet from the rebuilt geometry (wing, fuselage, tails, sponsons); Cfe is "
                         "1.5 x the flat-plate value at the fuselage-length Reynolds number, a "
                         "reading of a chart. Stage 1's CD0 includes engine, sensor and gear "
                         "terms the equivalent-skin-friction method has no separate place for."))
    rows += speed_rows(d, L, b)
    rows += field_rows(d)
    rows += vn_rows(d, L, b)
    rows += stability_rows(d)
    return {"rows": rows, "mission_legs": legs, "anderson_w0": aw, "cd0_detail": cd0,
            "rebuild_check": check, "ledger_path": str(ledger_path)}


def git_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=False, cwd=REPO).stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    res = compute(a.design)
    res["inputs"] = {
        "design": a.design, "design_sha256": sha256(a.design),
        "ledger": res.pop("ledger_path"), "ledger_sha256": sha256(Path(a.design).parent / "ledger.yaml"),
        "tp100_table": str(TP100_TABLE.relative_to(REPO)), "tp100_table_sha256": sha256(TP100_TABLE),
        "git_commit": git_commit(), "python": platform.python_version(), "numpy": np.__version__,
        "seed": None, "rebuild_tolerance": REBUILD_TOLERANCE}
    res["summary"] = {v: sum(r["verdict"] == v for r in res["rows"])
                      for v in ("within", "outside", "not judged", "not computed")}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report_text(res))
    for r in res["rows"]:
        print(f"{r['id']}: {r['stage1']} -> {r['stage3']} dev {r['deviation']} {r['verdict']}")


# ---- report from the JSON ----------------------------------------------------------------------------
def fmt(x):
    if x is None:
        return "-"
    if isinstance(x, str):
        return x
    return f"{x:,.4g}" if abs(x) < 1000 else f"{x:,.1f}"


def deviation_text(r):
    if r["deviation"] is None:
        return "-"
    if r["deviation_kind"] == "relative":
        return f"{100.0 * r['deviation']:+.2f} %"
    return f"{r['deviation']:+,.4g} {r['unit']}"


def tolerance_text(r):
    if r["tolerance"] is None:
        return "none (cross-check)"
    if r["deviation_kind"] == "relative":
        return f"+-{100.0 * r['tolerance']:.0f} %"
    return f"+-{r['tolerance']:,.4g} {r['unit']}"


def report_text(res):
    """Markdown from the result dict; every number is read from it."""
    i, s = res["inputs"], res["summary"]
    lines = [
        "# Task 12 Stage 3: performance measured against independent book relations", "",
        (f"Design: `{i['design']}` (sha256 `{i['design_sha256']}`). Git commit `{i['git_commit']}`. "
        f"Python {i['python']}, numpy {i['numpy']}. Generated by `python -m measurement.stage3_perf` "
        "from the JSON next to this report; tolerances are spec section 7.1a, fixed before the run. "
        "A row outside tolerance is reported, not adjusted."), "",
        (f"Rows: {s['within']} within, {s['outside']} outside, {s['not judged']} not judged, "
         f"{s['not computed']} not computed."), "",
        ("Not in this report: the engine rows (spec 7.1b), the vortex-lattice aero rows and the "
         "section CL_max row (SU2); range and endurance have no row of their own in 7.1a and are "
         "covered by mission fuel."), "",
        "| Quantity | Stage 1 | Stage 3 | Source | Deviation | Tolerance | Verdict |",
        "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        lines.append(f"| {r['quantity']} ({r['unit']}) | {fmt(r['stage1'])} | {fmt(r['stage3'])} | "
                     f"{r['source']} | {deviation_text(r)} | {tolerance_text(r)} | {r['verdict']} |")
    lines += ["", "## Notes per row", ""]
    for r in res["rows"]:
        lines.append(f"- **{r['quantity']}** (Stage 1 value: {r['stage1_source']}). {r['note']}")
    aw, cd = res["anderson_w0"], res["cd0_detail"]
    lines += ["", "## Detail", "", "Mission legs, Stage 3 (Mattingly) against Stage 1 weight fractions:", "",
              "| Segment | Stage 1 fraction | Stage 3 fraction | Basis |", "|---|---|---|---|"]
    for g in res["mission_legs"]:
        lines.append(f"| {g['segment']} | {g['fraction_stage1']:.6f} | {g['fraction_stage3']:.6f} | "
                     f"{g['basis']} |")
    if "W0" in aw:
        lines += ["", (f"Anderson first estimate: fuel fraction {fmt(aw['fuel_fraction'])}, cruise "
                  f"fraction {fmt(aw['f_cruise'])}, loiter fraction {fmt(aw['f_loiter'])}, "
                  f"(L/D)max {fmt(aw['LD_max'])}, best-range speed {fmt(aw['V_best_range_kt'])} kt. "
                  f"Build-up (8.83) converged after {aw['buildup_passes']} passes to "
                  f"{fmt(aw['buildup_W0'])} lb with empty weight {fmt(aw['buildup_We'])} lb. "
                  f"Diagnostic: the same route with Stage 1's empty fraction "
                  f"{fmt(aw['diagnostic_stage1_empty_fraction'])} gives W0 "
                  f"{fmt(aw['diagnostic_W0_at_stage1_empty_fraction'])} lb.")]
    lines += ["", (f"Zero-lift drag by (2.37): S_wet {fmt(cd['S_wet_ft2'])} ft^2, S_wet/S "
              f"{fmt(cd['S_wet_over_S'])}, fuselage Reynolds number {cd['Re_fuselage']:.3g}, Cfe "
              f"{fmt(cd['Cfe'])} (flat plate alone {fmt(cd['Cfe_flat_plate_only'])}); the Cfe that "
              f"would reproduce Stage 1's CD0 is {fmt(cd['Cfe_for_Stage1_CD0'])}."),
              "", "Rebuild check (the record against the rebuilt Stage 1 state):", "",
              "| Quantity | Record | Rebuilt |", "|---|---|---|"]
    for k, v in res["rebuild_check"].items():
        lines.append(f"| {k} | {fmt(v['record'])} | {fmt(v['rebuilt'])} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()

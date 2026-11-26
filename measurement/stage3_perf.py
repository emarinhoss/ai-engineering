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
import sys
from pathlib import Path

import numpy as np

from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import sizing, uav
from conceptual.engine_model import TP100_TABLE, TableEngine, table_for_run
from conceptual.units import KT, NM, RHO0, G, isa
from measurement import anderson as A
from measurement import mattingly as M

REPO = Path(__file__).resolve().parents[1]
CHOSEN_ENGINE = {"name": "PBS_TP100", "bhp": 241.0, "weight_lb": 135.8}     # the TP100 records' defaults
REBUILD_TOLERANCE = 1e-6          # relative; the rebuild must reproduce the record to this
# Fig. 2.55 (p. 129) draws 1.5 x the Karman-Schoenherr flat-plate friction as the dashed curve
# above which most of the book's jet data lie; (2.29) (p. 108) is its explicit form.
CFE_OVER_FLAT_PLATE = 1.5
CD0_REFERENCE_SPEED = 250.0       # ft/s, the speed at which Stage 1 evaluated CD0 at mission altitude


# ---- reading the design --------------------------------------------------------------------------
def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_engine(d, table_path, sfc_allowance=1.0):
    """The engine a record was sized with: its table scaled to the record's rated power (a
    photo-scaled engine when the record's bhp differs from the table's rated power, as for the TP100
    records of 300-480 hp; power scale 1 for the engine as is, TP100 241 hp or M250-B17F 450 hp),
    with the record's engine weight."""
    base = TableEngine(table_path)
    bhp = float(d.get("bhp_sl", base.rated))
    weight = float(d.get("engine", {}).get("weight_lb", CHOSEN_ENGINE["weight_lb"]))
    model = base.scaled(sfc=sfc_allowance, power=bhp / base.rated, rerate=True)
    return dict(CHOSEN_ENGINE, name=d.get("engine", {}).get("fixed") or CHOSEN_ENGINE["name"],
                bhp=bhp, weight_lb=weight, model=model)


def rebuild(design_path):
    """Record, ledger values (with the record's tail scale and the engine's datasheet SFC, as
    uav.evaluate does) and the rebuilt Stage 1 state at the record's W0. Raises if the rebuild
    does not reproduce the record."""
    path = Path(design_path)
    d = json.loads(path.read_text())
    ledger_path = path.parent / "ledger.yaml"
    L, _ = uav.load_ledger(ledger_path)
    # the engine table the record was made with, not necessarily the current one
    d, L, b, check = rebuild_record(d, L, table_for_run(path.parent))
    return d, L, b, ledger_path, check


def rebuild_record(d, L, table_path):
    """The same rebuild from a record already in memory: d the record (dict), L the ledger values
    it was sized with, table_path the engine table it used. Returns (d, ledger values, state, check)."""
    L = dict(L, ht_volume_scale=d["ht_volume_scale"])
    # the TP100's datasheet cruise consumption (0.901) replaced Table 3.4 when its records were sized (as in
    # stage1.engine_options); the M250 has none, keeps the ledger values, and its table replaces them anyway
    if not d.get("engine", {}).get("fixed", "").startswith("RR_M250"):
        L = dict(L, cbhp_cruise=0.901, cbhp_loiter=0.901)
    eng = record_engine(d, table_path, L.get("engine_sfc_allowance", 1.0))
    b = uav._build(d["W0_lb"], d["concept"], d["W_S"], d["A"], L, d["fuel_lb"], eng)
    check = {"fuel_lb": [d["fuel_lb"], b["fuel"]]}
    for k, v in d["power_required_hp"].items():
        check[f"power_{k}_hp"] = [v, b["power_req"][k]]
    for k, (rec, new) in check.items():
        if abs(new / rec - 1.0) > REBUILD_TOLERANCE:
            raise ValueError(f"rebuild does not reproduce the record: {k} {rec} against {new}")
    return d, L, b, {k: {"record": r, "rebuilt": n} for k, (r, n) in check.items()}


# ---- rows -----------------------------------------------------------------------------------------
# Row classes (review S3M-4). What a "within" can mean depends on what the row shares with Stage 1.
INDEPENDENT = "independent"            # another source, method and input for the quantity
PARTLY = "partly independent"          # another relation, but inputs or sub-models shared with Stage 1
CODING = "coding check"                # same inputs and an algebraically equal formula: only the coding is tested
CLASSES = (INDEPENDENT, PARTLY, CODING)
NOT_INDEPENDENT_7_1B = "not judged (7.1b: same engine table)"


def make_row(rid, quantity, unit, stage1, stage1_source, stage3, source, tolerance, tol_kind,
             note="", judged=True, klass=None):
    """One table row. Deviation is (Stage 3 - Stage 1)/Stage 1 for tol_kind 'relative', the
    plain difference for 'absolute'. The verdict follows from deviation and tolerance. klass is one
    of CLASSES. A row with judged False and a tolerance keeps the tolerance and says whether the
    deviation is numerically inside it (numerically_within); its verdict is 'not judged'."""
    row = {"id": rid, "quantity": quantity, "unit": unit, "stage1": stage1,
           "stage1_source": stage1_source, "stage3": stage3, "source": source,
           "deviation": None, "deviation_kind": tol_kind, "tolerance": tolerance, "note": note,
           "class": klass}
    if stage3 is None:
        row["verdict"] = "not computed"
        return row
    row["deviation"] = (stage3 / stage1 - 1.0) if tol_kind == "relative" else stage3 - stage1
    if not judged:
        row["verdict"] = "not judged"
        if tolerance is not None:
            row["numerically_within"] = abs(row["deviation"]) <= tolerance
    else:
        row["verdict"] = "within" if abs(row["deviation"]) <= tolerance else "outside"
    return row


RECORD = "record"
RECOMPUTED = "recomputed with conceptual code from the record's inputs"


# ---- the propeller of the record (review APL-3) ---------------------------------------------------
def is_app_l(L):
    """True when the record was sized with the App. L actuator disk (ledger propeller_model app_l)."""
    return L.get("propeller_model", "flat") == "app_l"


def record_propeller(L, rho, diameter):
    """The propeller Stage 1 used for this record at air density rho: the ledger's flat eta_p (a number)
    for propeller_model flat, an ActuatorDisk (conceptual.raymer_propulsion) for app_l. The same call
    as uav._propeller, so a Stage 3 row that reads Stage 1's propeller cannot drift from it."""
    return prop.propeller(L, rho, diameter)


def mattingly_shaft_hp(W0, W_S, q, V, power_lapse, K, CD0, eta_p, n=1.0, ps=0.0):
    """Sea-level-rated shaft hp from Mattingly (2.11), M.shaft_power_loading times W0. eta_p is a number
    (flat propeller, used as before) or an ActuatorDisk: then eta is that of the disk at the thrust
    the condition needs, T = t_w W0, as Stage 1's uav._min_power_for takes it."""
    t_w = M.master_thrust_loading(W_S, q, 1.0, 1.0, K, 0.0, CD0, 0.0, n, ps, V)
    eta = prop.efficiency_for_thrust(eta_p, t_w * W0, V)
    return W0 * M.shaft_power_loading(W_S, q, V, 1.0, power_lapse, K, 0.0, CD0, eta, 0.0, n, ps)


# ---- installed power by constraint: Mattingly (2.11) --------------------------------------------
def _min_power_mattingly(W0, S, rho, CD0, K, eta, ps, lapse, n=1.0, clmax=1.35, floor=1.2):
    """Smallest sea-level-rated shaft hp from (2.11) over speed, from `floor` x stall upward on a
    0.1 ft/s grid (Stage 1 used a 1 ft/s grid from the same floor). eta: a number or an ActuatorDisk."""
    W_S = W0 / S
    v_lo = floor * perf.stall_speed(n * W_S, rho, clmax)
    best = None
    for i in range(4000):
        V = v_lo + 0.1 * i
        q = 0.5 * rho * V ** 2
        hp = mattingly_shaft_hp(W0, W_S, q, V, lapse, K, CD0, eta, n, ps)
        best = hp if best is None or hp < best else best
    return best


def power_rows(d, L, b):
    W0, S, K = d["W0_lb"], b["geom"]["S"], d["K"]
    model, clean = b["engine_model"], b["clmax"]["clean"]
    sl, alt, ceil = isa(0.0), isa(L["mission_altitude_ft"]), isa(L["ceiling_ft"])
    D = b["D_prop"]
    eta_sl, eta_alt, eta_ceil = (record_propeller(L, a["rho"], D) for a in (sl, alt, ceil))
    W_S = W0 / S
    src = "Mattingly (2.11) p. 24 with T = 550 eta_p P/V (shaft_power_loading)"
    if is_app_l(L):
        src += "; eta_p from the App. L actuator disk at the thrust of each condition, as Stage 1"
    rec = d["power_required_hp"]
    out = []
    # climb at sea level, full lapse 1
    p = _min_power_mattingly(W0, S, sl["rho"], d["CD0"]["sea_level"], K, eta_sl,
                             L["climb_rate_sl_fpm"] / 60.0, 1.0, clmax=clean)
    out.append(make_row("power_climb_sl", "installed power, sea-level climb 1,000 ft/min", "hp",
                        rec["climb_sl"], RECORD, p, src, 0.05, "relative",
                        "CD0 at sea level from the record; minimum over speed from 1.2 V_stall. "
                        "Same inputs and an algebraically equal formula as Stage 1: a coding check.",
                        klass=CODING))
    # ceiling: CD0 and lapse at the climb-speed floor at the ceiling, as Stage 1 evaluated them
    v_ceil = L["climb_speed_over_stall"] * perf.stall_speed(W_S, ceil["rho"], clean)
    cd0_c = uav._polar(b["geom"], L, v_ceil, ceil, b["bhp"])[0]
    lap_c = model.lapse(L["ceiling_ft"], v_ceil / KT)
    p = _min_power_mattingly(W0, S, ceil["rho"], cd0_c, K, eta_ceil, L["ceiling_rate_fpm"] / 60.0,
                             lap_c, clmax=clean)
    out.append(make_row("power_ceiling", "installed power, 100 ft/min at the ceiling altitude "
                        f"{L['ceiling_ft']:.0f} ft", "hp", rec["ceiling"], RECORD, p, src,
                        0.05, "relative",
                        "CD0 at the climb-speed floor and the App. K lapse there are recomputed "
                        "with conceptual code (not in the record); the lapse is the engine "
                        "table's, an input shared with Stage 1. Spec 7.1b declares the rows that "
                        "use the engine table not independent: reported, not judged.",
                        judged=False, klass=CODING))
    # take-off: smallest hp meeting the field length over 50 ft, by Mattingly's (2.22)-(2.30) route
    hp_to = M.takeoff_power(
        L["field_length_ft"], lambda hp: uav._thrust_fn(hp, L, b["D_prop"]), W0, S, RHO0,
        b["CD0_takeoff"], K, b["clmax"]["takeoff"], mu=L["rolling_mu"], CL_ground=L["cl_ground"])
    out.append(make_row("power_takeoff", "installed power, take-off over 50 ft in the field length",
                        "hp", rec["takeoff"], RECORD, hp_to if math.isfinite(hp_to) else None,
                        "Mattingly (2.25) p. 29, (2.26)-(2.30) p. 30-31 (M.takeoff_power)", 0.05,
                        "relative", klass=PARTLY, note=
                        f"Inputs: field length {L['field_length_ft']:.0f} ft, obstacle 50 ft, W0 and S "
                        "from the record, take-off CD0 (clean + gear + take-off flap) from the "
                        "rebuilt Stage 1 state, K from the record, take-off CL_max "
                        f"{b['clmax']['takeoff']:.3f}, rolling mu {L['rolling_mu']} and ground CL "
                        f"{L['cl_ground']} from the ledger, thrust from the same propeller thrust "
                        "function Stage 1 used (shaft power, eta_p, static-thrust cap; a shared "
                        "input), evaluated at 0.7 V_TO for the roll (Anderson's rule, p. 360; "
                        "Mattingly states no speed). Differences from Stage 1: k_TO 1.2 (the book's "
                        "value, p. 43; at 1.1 the factor 0.8 k^2 - 1 of (2.27) is negative) against "
                        "Stage 1's V_TO = 1.1 V_stall, rotation time 1 s as Stage 1 (the book "
                        "'normally' uses 3 s), transition arc at n = 0.8 k_TO^2 against Raymer's "
                        "1.15 V_stall arc. Only the take-off weight's field-length use is checked, "
                        "not the take-off fuel."))
    # sustained turn at loiter speed and altitude
    V = b["V_loiter_start"]
    phi = math.radians(L["turn_bank_deg"])
    n_turn = M.turn_load_factor(G * math.tan(phi) / V, V)          # (2.16): n = 1/cos(bank)
    lap = model.lapse(L["mission_altitude_ft"], V / KT)
    q = 0.5 * alt["rho"] * V ** 2
    p = mattingly_shaft_hp(W0, W_S, q, V, lap, K, d["CD0"]["mission_altitude"], eta_alt, n_turn, 0.0)
    out.append(make_row("power_turn", "installed power, sustained 30 deg turn at loiter speed",
                        "hp", rec["turn_at_loiter"], RECORD, p,
                        src + "; n from (2.16) p. 27", 0.05, "relative",
                        "Loiter speed (Stage 1's best-endurance speed at W0 with the 1.3 V_stall "
                        "floor) is recomputed with conceptual code; CD0 from the record. Same "
                        "inputs and formula as Stage 1: a coding check.", klass=CODING))
    V = b["V_cruise_start"]
    lap = model.lapse(L["mission_altitude_ft"], V / KT)
    q = 0.5 * alt["rho"] * V ** 2
    p = mattingly_shaft_hp(W0, W_S, q, V, lap, K, d["CD0"]["mission_altitude"], eta_alt)
    out.append(make_row("power_cruise", "installed power, level cruise at mission altitude",
                        "hp", rec["cruise_at_altitude"], RECORD, p, src, 0.05, "relative",
                        "Cruise speed (Stage 1's best-range speed at W0) recomputed with "
                        "conceptual code; CD0 from the record. Same inputs and formula as "
                        "Stage 1: a coding check.", klass=CODING))
    return out


# ---- mission fuel: Mattingly ch. 3 fractions -----------------------------------------------------
def mission_fuel_mattingly(d, L, b):
    """Stage 1's mission replayed with Mattingly's segment fractions in place of Raymer's. The speed
    on each sub-step, its SFC (from the engine table, as Stage 1 used it), CD0 and the headwind
    air-distance factor V/(V - V_w) are Stage 1's; only the fraction relation is Mattingly's:
    climb (3.17)/(3.20) p. 61-62, cruise (3.23) p. 63, loiter (3.36)-(3.37) p. 66-67, TSFC from
    C_bhp by C = C_bhp V/(550 eta_p). Take-off, landing, and the 1.06 reserve factor are taken as
    Stage 1 had them (Mattingly's module has no tested relation for them)."""
    W0, S, K = d["W0_lb"], b["geom"]["S"], b["K"]
    geom, bhp, model, clmax = b["geom"], b["bhp"], b["engine_model"], b["clmax"]
    sl, alt = isa(0.0), isa(L["mission_altitude_ft"])
    D_prop = b["D_prop"]
    eta_sl, eta_alt = record_propeller(L, sl["rho"], D_prop), record_propeller(L, alt["rho"], D_prop)
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
    V_cl = perf.best_rate_of_climb(W, S, sl["rho"], CD0_sl, K, bhp, eta_sl, v_lo, v_lo + 350.0)[1]
    CD0_alt = uav._polar(geom, L, CD0_REFERENCE_SPEED, alt, bhp)[0]
    V_cr = uav._cruise_speed(W, S, alt["rho"], CD0_alt, K, clmax["clean"], L, "range")[0]
    lapse = model.lapse(h_alt, V_cl / KT)
    d_t = 0.5 * (perf.drag(W, S, sl["rho"], V_cl, CD0_sl, K) / prop.thrust_from_power(bhp, eta_sl, V_cl)
                 + perf.drag(W, S, alt["rho"], V_cl, CD0_alt, K)
                 / prop.thrust_from_power(bhp * lapse, eta_alt, V_cl))
    dhe = sizing.energy_height_change(0.0, V_cl, h_alt, V_cr)
    c_cl = model.bsfc(0.5 * h_alt, V_cl / KT, bhp * model.lapse(0.5 * h_alt, V_cl / KT))
    # efficiency of the climb's equivalent TSFC at the mid-altitude of the climb, as uav._mission takes it
    mid = isa(0.5 * h_alt)
    eta_cl = prop.efficiency_at_power(record_propeller(L, mid["rho"], D_prop),
                                      bhp * model.lapse(0.5 * h_alt, V_cl / KT), V_cl)
    f = M.climb_fraction(M.equivalent_tsfc(c_cl, V_cl, eta_cl), V_cl, dhe, min(d_t, 0.95))
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
            eta = prop.efficiency_for_thrust(eta_alt, W * CD_over_CL, V)      # thrust = drag = W CD/CL
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
    fraction defaults to Anderson's 0.62; the diagnostic run passes Stage 1's.

    Propeller: his (5.153) and (5.169) take one constant eta_pr. For a flat record that is the ledger's
    eta_p. For an app_l record it is the actuator disk's efficiency at the thrust at the start of the
    leg for the record's own take-off weight (cruise: W/(L/D) at his best-range speed, one value for
    both cruise legs; loiter: thrust at his best-endurance speed with the weight after the first
    cruise), then held constant while W0 iterates. Letting the disk's efficiency follow the iterated
    W0 would load the record's fixed propeller with a different aircraft, which is not the question the
    row asks.
    """
    eta_p, CD0, K, WS = record_propeller(L, isa(L["mission_altitude_ft"])["rho"], b["D_prop"]), \
        d["CD0"]["mission_altitude"], d["K"], d["W_S"]
    rho = isa(L["mission_altitude_ft"])["rho"]
    vw = L["headwind_kt"] * KT
    V = A.speed_ld_max(WS, rho, CD0, K)
    if V <= vw:
        return {"reason": "the (L/D)max speed is below the headwind"}
    LD, k32 = A.ld_max(CD0, K), A.cl32_cd_max(CD0, K)
    c_cr, c_lo = A.cbhp_to_c(d["cbhp_used"]["cruise"]), A.cbhp_to_c(d["cbhp_used"]["loiter"])
    V_lo = A.speed_cl32_cd_max(WS, rho, CD0, K)
    LD_lo = math.sqrt(3.0 * CD0 / K) / (4.0 * CD0)               # CL/CD at (CL^1.5/CD)max: CL = sqrt(3 CD0/K), CD = 4 CD0
    E = L["loiter_h"] * 3600.0
    W_c = d["W0_lb"] * 0.97 * 0.985                              # the record's weight at the start of the cruise
    eta = prop.efficiency_for_thrust(eta_p, W_c / LD, V)
    f_cr = A.breguet_cruise_fraction(L["radius_nm"] * NM * V / (V - vw), c_cr, eta, LD)
    eta_lo = prop.efficiency_for_thrust(eta_p, W_c * f_cr / LD_lo, V_lo)
    W0 = 3000.0
    for _ in range(500):
        S = W0 / WS
        Wa = W0 * 0.97 * 0.985 * f_cr
        # (5.169) solved for W1
        W1 = (Wa ** -0.5 + E * c_lo / (eta_lo * math.sqrt(2.0 * rho * S) * k32)) ** -2
        assert abs(A.endurance_s(eta_lo, c_lo, rho, S, k32, Wa, W1) - E) < 1e-3
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
            "V_best_range_kt": V / KT, "eta_cruise": eta, "eta_loiter": eta_lo, "buildup_W0": rows[-1][2], "buildup_We": rows[-1][0],
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
    cfe_jet = cfe_anderson(Re)
    cfe = A.CFE_PROPELLER                                        # (8.40) p. 414, owner ruling G-3
    cd0 = s_wet / g["S"] * cfe                                   # (2.37) p. 128
    target = d["CD0"]["mission_altitude"]
    return {"CD0": cd0, "S_wet_ft2": s_wet, "S_wet_over_S": s_wet / g["S"], "Re_fuselage": Re,
            "Cfe": cfe, "Cfe_source": "Anderson (8.40) p. 414, propeller airplane",
            "Cfe_jet_curve": cfe_jet, "CD0_jet_curve": s_wet / g["S"] * cfe_jet,
            "CD0_jet_curve_deviation": s_wet / g["S"] * cfe_jet / target - 1.0,
            "Cfe_flat_plate_only": cfe_jet / CFE_OVER_FLAT_PLATE,
            "Cfe_for_Stage1_CD0": target * g["S"] / s_wet}


# ---- speeds, climb, ceiling: Anderson ch. 5 ------------------------------------------------------
def ceiling_anderson(d, L, b):
    """Highest altitude where Anderson's best climb rate (5.121) p. 277 is 100 ft/min, by bisection.
    Power: the engine table's full-throttle shaft hp at the climb speed; CD0 recomputed at each
    altitude and climb speed as Stage 1 did; no 1.2 V_stall floor (the closed form has none)."""
    W0, K = d["W0_lb"], d["K"]
    model, W_S = b["engine_model"], d["W_S"]

    def roc(h):
        a = isa(h)
        V = L["climb_speed_over_stall"] * perf.stall_speed(W_S, a["rho"], b["clmax"]["clean"])
        for _ in range(4):
            cd0 = uav._polar(b["geom"], L, V, a, b["bhp"])[0]
            hp = model.power_available(h, V / KT)
            # one constant eta in (5.121): the flat number, or the disk at full power at the speed of this pass
            eta = prop.efficiency_at_power(record_propeller(L, a["rho"], b["D_prop"]), hp, V)
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
                    0.03, "relative", note, klass=CODING),
           make_row("v_best_endurance", "best-endurance speed (C_L^1.5/C_D max), mission altitude",
                    "kt", perf.speed_min_power(WS, alt["rho"], cd0, K)[0] / KT, RECOMPUTED,
                    A.speed_cl32_cd_max(WS, alt["rho"], cd0, K) / KT, "Anderson (5.41) p. 221",
                    0.03, "relative", note, klass=CODING)]
    v_cl = A.speed_cl32_cd_max(WS, sl["rho"], d["CD0"]["sea_level"], K) / KT
    # (5.121) takes one constant eta. Flat: the ledger number. App. L: the disk at full power at the speed where
    # Stage 1's own search put the best climb (record performance.v_best_climb_kt), i.e. Stage 1's efficiency at
    # its climb point. The closed form's best speed lies elsewhere, where the disk is less efficient, and a
    # constant eta cannot follow that; the note gives that value.
    disk_sl = record_propeller(L, sl["rho"], b["D_prop"])
    eta_cl = prop.efficiency_at_power(disk_sl, d["bhp_sl"], d["performance"]["v_best_climb_kt"] * KT)
    eta_cl_at_closed_form_speed = prop.efficiency_at_power(disk_sl, d["bhp_sl"], v_cl * KT)
    P_over_W = eta_cl * d["bhp_sl"] * 550.0 / d["W0_lb"]
    rc = A.max_rate_of_climb_prop(P_over_W, WS, sl["rho"], d["CD0"]["sea_level"], K) * 60.0
    out.append(make_row("roc_sl", "sea-level rate of climb at W0", "ft/min",
                        d["performance"]["roc_sl_fpm"], RECORD, rc,
                        "Anderson (5.121) p. 277 (5.122 misprinted, per the notes)", 0.03,
                        "relative",
                        f"Rated {d['bhp_sl']:g} hp at sea level, eta_p {eta_cl:.4g}" + (f" (App. L disk at full power at Stage 1's best-climb speed {d['performance']['v_best_climb_kt']:.1f} kt; "
                                                     f"at the closed form's own best-climb speed {v_cl:.1f} kt it would be {eta_cl_at_closed_form_speed:.4g}, "
                                                     "which a constant eta cannot follow)" if is_app_l(L) else "")
                        + ", CD0 at sea level from the record, "
                        "as Stage 1. Same inputs, closed form against a numerical search: a coding check.",
                        klass=CODING))
    out.append(make_row("v_best_climb", "best-climb speed, sea level", "kt",
                        d["performance"]["v_best_climb_kt"], RECORD, v_cl,
                        "Anderson (5.118)/(5.41) p. 221, 277", 0.03, "relative",
                        "Stage 1 searches speeds from 1.2 V_stall upward (Raymer p. 489) and "
                        "lands on that floor; the closed form has no floor. Same polar and power: "
                        "the difference is a modelling choice (the floor), not a second source.",
                        klass=CODING))
    ceil = ceiling_anderson(d, L, b)
    top = float(max(b["engine_model"].h)) if hasattr(b["engine_model"], "h") else None
    clamp = ("" if top is None or max(ceil, d["performance"]["service_ceiling_ft"]) <= top else
             f" The table's top altitude is {top:,.0f} ft and the lookup holds its power constant above it: "
             f"Stage 1's ceiling ({d['performance']['service_ceiling_ft']:,.0f} ft) and this one ({ceil:,.0f} ft) "
             "lean on that clamp, and this one more where it lies higher. The cycle's own power keeps falling "
             "(engine report).")
    out.append(make_row("ceiling", "service ceiling (100 ft/min) at W0", "ft",
                        d["performance"]["service_ceiling_ft"], RECORD, ceil,
                        "Anderson (5.121) p. 277 with the App. K lapse", 1000.0, "absolute",
                        "Same engine table as Stage 1 (shared input); CD0 recomputed per "
                        "altitude; the closed form has no 1.2 V_stall floor, Stage 1 does. Spec 7.1b "
                        "declares the rows that use the engine table not independent: reported, not "
                        "judged." + clamp, judged=False, klass=CODING))
    return out


def vn_rows(d, L, b):
    v = A.corner_speed(d["n_limit"], d["W_S"], RHO0, d["CL_max"]["clean"]) / KT
    out = [make_row("v_corner", "corner speed V*, sea level, EAS", "kt",
                    d["vn"]["V_corner_eas_kt"], RECORD, v, "Anderson (6.54) p. 343", 0.05,
                    "relative",
                    "n_limit (3.8, the requirement) and clean CL_max 1.35 from the record. The "
                    "same V = sqrt(2 n W/S/(rho CL_max)) as Stage 1's, so it checks the arithmetic.",
                    klass=CODING)]
    out.append(make_row("gust_n", "gust load factors (V_C and V_D points)", "-",
                        d["n_gust"], RECORD, None, "Anderson ch. 6 gust relation", 0.05,
                        "relative",
                        "not computed: Anderson's chapter 6 has no gust load factor relation (the V-n section 6.5, "
                        "p. 341-344, only names gusts as the reason for the red-line speed limit; "
                        "searched the library notes for 'gust'). Raymer (14.x) is Stage 1's "
                        "own source, so using it here would not be independent and is not "
                        "substituted; a second source (Mattingly has none) is needed. Owner ruling "
                        "G-5: waived before Gate B, listed as open.", klass=INDEPENDENT))
    return out


def field_rows(d, L, b):
    """Take-off over 50 ft and landing over 50 ft, sea level ISA, by Anderson 6.7-6.8 with the
    inputs Stage 1 used: W0, S, K, take-off and landing CD0 (rebuilt Stage 1 state, gear and flap
    included), CL_max take-off and landing, rolling mu, braking mu, ground CL and free-roll time
    (ledger), thrust function (shared). Ground effect is not applied (G = 1, k_induced = K; the
    lift-dependent roll drag is under 2 % of the total, Example 6.6); idle thrust zero as Stage 1."""
    p = d["performance"]
    W0, S, K = d["W0_lb"], b["geom"]["S"], d["K"]
    thrust = uav._thrust_fn(b["bhp"], L, b["D_prop"])
    V_lo = 1.1 * A.stall_speed(W0 / S, RHO0, b["clmax"]["takeoff"])
    to = A.takeoff_distance(W0, S, RHO0, b["CD0_takeoff"], K, b["clmax"]["takeoff"],
                            thrust(0.7 * V_lo), L["rolling_mu"], L["cl_ground"], h_OB=50.0, N=1.0)
    ld = A.landing_distance(W0, S, RHO0, b["CD0_landing"], K, b["clmax"]["landing"], L["braking_mu"],
                            L["cl_ground"], perf.APPROACH_GAMMA, h_OB=50.0, N=L["free_roll_s"])
    return [make_row("takeoff_distance", "take-off distance over 50 ft, sea level", "ft",
                     p["takeoff_ft"], RECORD, to["total"],
                     "Anderson (6.90) p. 361, (6.98)-(6.100) p. 364", 0.15, "relative",
                     f"Ground roll {to['ground_roll']:.0f} ft (with N = 1 s rotation, V_LO = 1.1 "
                     f"V_stall, thrust at 0.7 V_LO from the shared propeller thrust function) plus "
                     f"airborne {to['airborne']:.0f} ft (n = 1.19 arc). Stage 1 (Raymer 17.8): "
                     f"{p['takeoff']['ground_roll']:.0f} ft roll, {p['takeoff']['rotation']:.0f} "
                     f"rotation, {p['takeoff']['transition'] + p['takeoff']['climb']:.0f} airborne. "
                     "Inputs as listed in field_rows: W0, S, K, take-off CD0, take-off CL_max, "
                     "rolling mu, ground CL (ledger). Different ground-roll and airborne relations, "
                     "shared thrust function, CD0 and CL_max.", klass=PARTLY),
            make_row("landing_distance", "landing distance over 50 ft, sea level", "ft",
                     p["landing_ft"], RECORD, ld["total"],
                     "Anderson (6.104)-(6.109) p. 369-370, (6.119) p. 372", 0.15, "relative",
                     f"Approach+flare {ld['approach'] + ld['flare']:.0f} ft (3 deg approach, flare "
                     f"at 1.23 V_stall), ground roll incl. {L['free_roll_s']:.0f} s free roll "
                     f"{ld['ground_roll']:.0f} ft (V_TD 1.15 V_stall, braking mu {L['braking_mu']}, "
                     "idle thrust zero). Inputs: W0, S, K, landing CD0, landing CL_max, braking mu, "
                     "ground CL, free-roll time (ledger). Anderson's approach and flare relations "
                     "are the same speeds and geometry as Raymer's, so this is a coding and "
                     "arithmetic cross-check on those segments; the braking roll has its own relation.",
                     klass=PARTLY),
            ]


# The static-margin rows (Anderson (8.76)-(8.78), owner ruling G-5) are in measurement/stage3_aero.py,
# which has the lattice downwash they need.


# ---- propeller efficiency: Mattingly App. L ---------------------------------------------------------
REAL_TO_IDEAL = 0.85       # App. L p. 612-613: real propellers reach about 85 % of the ideal (library notes)


def _prop_eta_fixed_point(shp, V, rho, diameter, real_to_ideal=REAL_TO_IDEAL):
    """Real efficiency eta = f eta*(T) with T = 550 eta P / V: thrust and efficiency depend on each
    other, so iterate (converges in a few passes: eta* varies slowly with thrust)."""
    eta = real_to_ideal
    for _ in range(100):
        T = 550.0 * eta * shp / V
        new = M.real_propeller_efficiency(T, rho, V, diameter, real_to_ideal)
        if abs(new - eta) < 1e-12:
            return eta, T
        eta = new
    raise ValueError("propeller efficiency fixed point did not converge in 100 passes")


def prop_rows(d, L):
    """Propeller efficiency at climb, cruise and loiter (tolerance +-0.05 absolute) by the actuator disk
    with the real-to-ideal factor (App. L). The shaft power, speed and diameter are the record's; density
    is sea level for climb and the mission altitude for cruise and loiter. The blade-element estimate of
    the spec row is not computed. Stage 1's value is Raymer's flat eta_p (Table 3.4) for a flat record
    (the row is then independent); for an app_l record it is Stage 1's own App. L efficiency from the
    record's propeller_points, and the row is a coding check (same relation, same factor; review APL-3)."""
    out = []
    pts = d["propeller_points"]
    sl, alt = isa(0.0), isa(L["mission_altitude_ft"])
    app_l = is_app_l(L)
    factor = L["prop_real_to_ideal"] if app_l else REAL_TO_IDEAL
    for rid, name, key, a in (("prop_eta_climb", "climb (sea level, full power)", "climb_sea_level", sl),
                              ("prop_eta_cruise", "cruise (outbound leg)", "cruise_out", alt),
                              ("prop_eta_loiter", "loiter", "loiter", alt)):
        p = pts[key]
        eta, T = _prop_eta_fixed_point(p["shaft_hp"], p["V_kt"] * KT, a["rho"], d["propeller_diameter_ft"], factor)
        area = math.pi * d["propeller_diameter_ft"] ** 2 / 4.0
        if app_l:
            s1, s1_src = p["eta_p"], "Stage 1's App. L value (record propeller_points)"
            klass = CODING
            why = ("Coding check, not independent: Stage 1 is on the same App. L actuator disk with the same factor "
                   f"({factor}, ledger prop_real_to_ideal), so this row re-codes (L.7)-(L.9) in measurement/mattingly.py "
                   "against conceptual/raymer_propulsion.py and agreement cannot confirm the physics. With the "
                   "blade-element check waived (owner ruling G-5) no independent propeller check is left. ")
        else:
            s1, s1_src, klass, why = L["eta_p"], "ledger eta_p (Raymer Table 3.4)", INDEPENDENT, ""
        out.append(make_row(rid, f"propeller efficiency, {name}", "-", s1, s1_src,
                            eta, "Mattingly App. L (L.7)-(L.9) p. 612 actuator disk, real-to-ideal "
                            f"{factor}", 0.05, "absolute",
                            why + f"Shaft {p['shaft_hp']:.1f} hp at {p['V_kt']:.1f} kt, diameter "
                            f"{d['propeller_diameter_ft']:.2f} ft, thrust {T:,.0f} lb. The 0.85 factor is the book's "
                            "typical value, applied to every point; no blade-element or propeller-map estimate "
                            "was made (owner ruling G-5: waived before Gate B, listed as open). "
                            + ("The shaft powers are Stage 1's, found from the same disk, so the thrust used here is the "
                               "drag." if app_l else
                               "The cruise and loiter shaft powers are Stage 1's power required divided by eta_p, so the "
                               "thrust used here is not exactly the drag."), klass=klass))
        out[-1]["detail"] = {"shaft_hp": p["shaft_hp"], "V_kt": p["V_kt"], "thrust_lb": T, "disk_area_ft2": area,
                             "disk_loading_psf": T / area, "ideal_efficiency": eta / factor}
    return out


# ---- take-off power: where the two routes differ (review S3M-7) ---------------------------------------
def takeoff_power_detail(d, L, b, hp_mattingly):
    """Numbers behind the take-off power row. Mattingly's power for k_TO 1.15, 1.2, 1.25 (a larger k_TO
    needs more power); at Stage 1's power the airborne part of each route and the climb gradient after
    lift-off; Stage 1's route at Mattingly's power. Near zero climb gradient the airborne distance
    grows steeply as power falls, so a few percent of power moves the distance a lot."""
    from conceptual import uav as _uav
    W0, S, K = d["W0_lb"], b["geom"]["S"], d["K"]
    hp1 = d["power_required_hp"]["takeoff"]
    args = (W0, S, RHO0, b["CD0_takeoff"], K, b["clmax"]["takeoff"])

    def mattingly(hp, k=1.2):
        try:
            r = M.takeoff_distance(*args, uav._thrust_fn(hp, L, b["D_prop"]), L["rolling_mu"], L["cl_ground"], k_TO=k)
            return {"hp": hp, "k_TO": k, "total": r["total"], "ground_roll": r["ground_roll"],
                    "rotation": r["rotation"], "airborne": r["airborne"]}
        except ValueError:
            return {"hp": hp, "k_TO": k, "total": None}

    def raymer(hp):
        try:
            r = _uav._takeoff(W0, S, b["CD0_takeoff"], K, b["clmax"]["takeoff"], L, hp, b["D_prop"])
            return {"hp": hp, "total": r["total"], "ground_roll": r["ground_roll"], "rotation": r["rotation"],
                    "transition": r["transition"], "climb": r["climb"]}
        except ValueError:
            return {"hp": hp, "total": None}

    by_k = {}
    for k in (1.15, 1.2, 1.25):
        hp = M.takeoff_power(L["field_length_ft"], lambda h: uav._thrust_fn(h, L, b["D_prop"]), *args,
                             mu=L["rolling_mu"], CL_ground=L["cl_ground"], k_TO=k)
        by_k[str(k)] = hp if math.isfinite(hp) else None
    hp_m = hp_mattingly
    return {"stage1_hp": hp1, "mattingly_hp": hp_m, "mattingly_hp_by_k_TO": by_k,
            "mattingly_at_stage1_hp": mattingly(hp1), "raymer_at_stage1_hp": raymer(hp1),
            "raymer_at_mattingly_hp": raymer(hp_m) if hp_m is not None else None,
            "field_length_ft": L["field_length_ft"]}


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
                         "Take-off, landing and the 1.06 reserve are Stage 1's. Spec 7.1b declares "
                         "the rows that use the engine table not independent: reported, not judged.",
                         judged=False, klass=CODING))
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
                             "time and W/S from the record or its ledger copy. The empty fraction "
                             "is Anderson's own; the fuel fraction rests on his relations with "
                             "Stage 1's polar, SFC and eta_p.", klass=PARTLY))
        rows.append(make_row("w0_buildup", "take-off weight, Anderson build-up (8.83) "
                             "(same-author cross-check)", "lb", d["W0_lb"], RECORD, aw["buildup_W0"],
                             "Anderson (8.83a-g) p. 449, section 8.7 p. 449-453", None, "relative",
                             "Raymer's Table 15.2 approximate method, so not independent: reported, "
                             "not judged (spec 7.1a). Uses the first-estimate fuel fraction.",
                             judged=False, klass=CODING))
    cd0 = cd0_anderson(d, L, b)
    rows.append(make_row("cd0", "zero-lift drag coefficient, mission altitude, clean", "-",
                         d["CD0"]["mission_altitude"], RECORD, cd0["CD0"],
                         "Anderson (2.37) p. 128 with Cfe 0.0043 of his propeller airplane, (8.40) p. 414",
                         0.10, "relative",
                         "S_wet from the rebuilt geometry (wing, fuselage, tails, sponsons); Cfe = "
                         f"{cd0['Cfe']:.4f}, the value Anderson uses for his propeller airplane "
                         "(owner ruling G-3). The jet-aircraft curve of Fig. 2.55 (1.5 x flat plate, "
                         f"p. 129) gives Cfe {cd0['Cfe_jet_curve']:.5f} and CD0 {cd0['CD0_jet_curve']:.5f}, "
                         "shown alongside in the detail. The method resolves CD0 to about +-20 %: "
                         "the coefficient is a book value, not a measurement of this airframe.",
                         klass=INDEPENDENT))
    rows += prop_rows(d, L)
    rows += speed_rows(d, L, b)
    rows += field_rows(d, L, b)
    rows += vn_rows(d, L, b)
    hp_m = next(r["stage3"] for r in rows if r["id"] == "power_takeoff")
    to_detail = takeoff_power_detail(d, L, b, hp_m)
    return {"rows": rows, "mission_legs": legs, "anderson_w0": aw, "cd0_detail": cd0,
            "takeoff_power_detail": to_detail,
            "record_facts": {"propeller_model": L.get("propeller_model", "flat"),
                             "engine": d.get("engine", {}).get("fixed"), "unchoked_fuel_share": d.get("unchoked_fuel_share"),
                             "W0_lb": d["W0_lb"], "fuel_fraction": d["fuel_lb"] / d["W0_lb"], "empty_fractions": d.get("empty_fraction_comparison")},
            "rebuild_check": check, "ledger_path": str(ledger_path)}


def compare_with(new, old_path):
    """Each row of `new` beside the same row id of an earlier perf.json (Stage 1 and Stage 3 values,
    verdict, class), read from the two records and nothing else."""
    old = json.loads(Path(old_path).read_text())
    olds = {r["id"]: r for r in old["rows"]}
    rows = []
    for r in new["rows"]:
        o = olds.get(r["id"])
        rows.append({"id": r["id"], "quantity": r["quantity"], "unit": r["unit"],
                     "old": None if o is None else {k: o.get(k) for k in ("stage1", "stage3", "deviation", "verdict", "class")},
                     "new": {k: r.get(k) for k in ("stage1", "stage3", "deviation", "verdict", "class")}})
    return {"old_perf": str(old_path), "old_perf_sha256": sha256(old_path),
            "old_design": old["inputs"]["design"], "old_git_commit": old["inputs"]["git_commit"],
            "new_design": new["inputs"]["design"], "rows": rows,
            "rows_only_in_old": [i for i in olds if i not in {r["id"] for r in new["rows"]}]}


def _table_inputs(design):
    """The engine table the record used (the copy in the run folder): its path and hash. A TP100 record
    keeps the keys of the earlier reports (tp100_table), the M250 one gets engine_table."""
    path = table_for_run(Path(design).parent)
    rel = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)
    if path.name.startswith("tp100"):
        return {"tp100_table": rel, "tp100_table_sha256": sha256(path)}
    return {"engine_table": rel, "engine_table_sha256": sha256(path)}


def git_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=False, cwd=REPO).stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--compare", nargs="+", help="perf.json of earlier runs: adds one row-by-row comparison table "
                    "for each (for example the old record measured with this code, and the file recorded then)")
    a = ap.parse_args(argv)
    res = compute(a.design)
    res["inputs"] = {
        "design": a.design, "design_sha256": sha256(a.design),
        "ledger": res.pop("ledger_path"), "ledger_sha256": sha256(Path(a.design).parent / "ledger.yaml"),
        **_table_inputs(a.design),
        "git_commit": git_commit(), "python": platform.python_version(), "numpy": np.__version__,
        "seed": None, "rebuild_tolerance": REBUILD_TOLERANCE,
        "command": "python -m measurement.stage3_perf " + " ".join(sys.argv[1:] if argv is None else argv)}
    if a.compare:
        res["comparisons"] = [compare_with(res, p) for p in a.compare]
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
    return f"{r['deviation']:+,.4g}" + ("" if r["unit"] == "-" else f" {r['unit']}")


def tolerance_text(r):
    if r["tolerance"] is None:
        return "none (cross-check)"
    if r["deviation_kind"] == "relative":
        return f"+-{100.0 * r['tolerance']:.0f} %"
    return f"+-{r['tolerance']:,.4g}" + ("" if r["unit"] == "-" else f" {r['unit']}")


def class_counts(rows):
    """{class: {verdict: n}} from the rows (rows without a class, from older records, count as 'unclassified')."""
    out = {}
    for r in rows:
        c = out.setdefault(r.get("class") or "unclassified", {})
        c[r["verdict"]] = c.get(r["verdict"], 0) + 1
    return out


def _diag_takeoff_power(res, r):
    t = res.get("takeoff_power_detail")
    if not t or r["stage3"] is None:
        return None
    k = t["mattingly_hp_by_k_TO"]
    ms, rs, rm = t["mattingly_at_stage1_hp"], t["raymer_at_stage1_hp"], t["raymer_at_mattingly_hp"]
    txt = (f"Mattingly's route needs {fmt(k['1.15'])}, {fmt(k['1.2'])} and {fmt(k['1.25'])} hp at k_TO 1.15, 1.2 and "
           f"1.25 for the {t['field_length_ft']:,.0f} ft field: a larger k_TO needs more power, so k_TO does not explain "
           f"Stage 1 needing more ({fmt(t['stage1_hp'])} hp). The difference comes from the climb-out after lift-off, where "
           f"both routes are near zero climb gradient. At Stage 1's power Raymer's climb segment is {rs['climb']:,.0f} ft "
           f"of its {rs['total']:,.0f} ft (drag at 1.15 V_stall with C_L = 0.9 C_L,max), and Mattingly's whole airborne "
           f"part is {ms['airborne']:,.0f} ft (drag at 1.2 V_stall with C_L = C_L,max/k_TO^2).")
    if rm and rm.get("total"):
        txt += (f" At Mattingly's {fmt(t['mattingly_hp'])} hp Raymer's route gives {rm['total']:,.0f} ft "
                f"(climb segment {rm['climb']:,.0f} ft): a {abs(r['deviation']) * 100:.1f} % change in power moves "
                f"the distance from {rs['total']:,.0f} to {rm['total']:,.0f} ft. The row compares two models in the part of the curve where the distance is "
                "most sensitive; it says nothing about the installed power (the rated power is far above both).")
    return txt


def _diag_w0(res, r):
    aw = res["anderson_w0"]
    if "W0" not in aw:
        return None
    s1 = aw.get("diagnostic_W0_at_stage1_empty_fraction")
    return (f"Owner ruling G-2: counted as explained, not failed. Anderson's first estimate with his historical empty "
            f"fraction 0.62 ((8.5) p. 400) is {fmt(aw['W0'])} lb against Stage 1's {fmt(r['stage1'])} lb. The 0.62 is a "
            "historical fraction of crewed aircraft and does not apply to an uncrewed composite UAV. The denominator "
            f"1 - {fmt(aw['fuel_fraction'])} - 0.62 is small, so the result is very sensitive to the fraction. Three values "
            f"side by side: 0.62 ({aw['W0']:,.0f} lb); Stage 1's empty fraction {fmt(aw['diagnostic_stage1_empty_fraction'])} "
            f"({s1:,.0f} lb, {100 * (s1 / r['stage1'] - 1):+.1f} %); Anderson's build-up (8.83) ({aw['buildup_W0']:,.0f} lb, "
            f"{100 * (aw['buildup_W0'] / r['stage1'] - 1):+.1f} %, Raymer's own method, not judged). "
            + (f"Anderson's fuel fraction is {fmt(aw['fuel_fraction'])} against Stage 1's "
               f"{fmt(res['record_facts']['fuel_fraction'])}, so the difference is the empty fraction."
               if res.get("record_facts", {}).get("fuel_fraction") else ""))


def _diag_cd0(res, r):
    c = res["cd0_detail"]
    return (f"Owner ruling G-3: Anderson's propeller-airplane Cfe {c['Cfe']:.4f} ((8.40) p. 414) is the row's value, "
            f"giving CD0 {c['CD0']:.5f} against Stage 1's {fmt(r['stage1'])} ({100 * r['deviation']:+.1f} %). Alongside, the "
            f"jet-aircraft curve of Fig. 2.55 (1.5 x flat plate) gives Cfe {c['Cfe_jet_curve']:.5f} and CD0 "
            f"{c['CD0_jet_curve']:.5f} ({100 * c['CD0_jet_curve_deviation']:+.1f} %). The Cfe that would reproduce Stage 1 is "
            f"{c['Cfe_for_Stage1_CD0']:.4f}. The row is outside tolerance in the favourable direction (the independent "
            "value is lower); the method resolves CD0 to about +-20 % and cannot confirm Stage 1's CD0 to +-10 %. "
            "The remainder is the content of Stage 1's build-up (sponsons, engine and sensor terms, leakage, tail size), "
            "which the equivalent-skin-friction method has no separate place for.")


def _diag_best_climb(res, r):
    roc = next((x for x in res["rows"] if x["id"] == "roc_sl"), None)
    txt = (f"Stage 1 searches speeds from 1.2 V_stall upward and lands on that floor ({fmt(r['stage1'])} kt); the "
           f"closed form has no floor ({fmt(r['stage3'])} kt).")
    if roc:
        txt += f" The sea-level rate of climb agrees to {100 * roc['deviation']:+.2f} %."
    return txt


def _diag_prop_climb(res, r):
    dt = r.get("detail")
    if res.get("record_facts", {}).get("propeller_model") == "app_l":
        return None                 # the text below argues from a flat Stage 1 efficiency
    p1 = next((x for x in res["rows"] if x["id"] == "power_climb_sl"), None)
    if not dt:
        return None
    txt = (f"Shaft {fmt(dt['shaft_hp'])} hp at {fmt(dt['V_kt'])} kt on a {fmt(dt['disk_area_ft2'])} ft^2 disk gives "
           f"{dt['thrust_lb']:,.0f} lb of thrust, a disk loading of {fmt(dt['disk_loading_psf'])} lb/ft^2: the ideal efficiency "
           f"is {fmt(dt['ideal_efficiency'])}, and the real-to-ideal factor {REAL_TO_IDEAL} gives {fmt(r['stage3'])}. This is "
           "the most heavily loaded point of the mission and the point Stage 1 uses for its sea-level climb rate and "
           "take-off thrust, so those Stage 1 values are optimistic (owner ruling G-4: Stage 1 moves to App. L "
           "efficiency per flight condition).")
    if p1:
        txt += (f" Arithmetic, not a re-size: the sea-level climb power scales as 1/eta_p, {fmt(p1['stage3'])} hp x "
                f"{r['stage1']:.2f}/{fmt(r['stage3'])} = {fmt(p1['stage3'] * r['stage1'] / r['stage3'])} hp.")
    return txt


DIAGNOSES = {"power_takeoff": _diag_takeoff_power, "w0_first": _diag_w0, "cd0": _diag_cd0,
             "v_best_climb": _diag_best_climb, "prop_eta_climb": _diag_prop_climb}


def generated_sections(res):
    """The sections the report used to carry as hand-written text, generated from the record: the rows
    not computed with their reasons, the rows outside tolerance with a diagnosis tied to the computed
    numbers (a row with no diagnosis function is listed as such), the field-length basis (G-1) and the
    caveats the record supports."""
    rows = res["rows"]
    L = ["", "## Rows not computed, open items", ""]
    for r in rows:
        if r["verdict"] == "not computed":
            L.append(f"- **{r['quantity']}**: {r['note']}")
    L += ["- **Section polars and C_L,max (SU2)**: not run (owner ruling G-5: waived before Gate B, listed open in the Gate B report).",
          "- **Propeller efficiency by blade element**: no code (G-5: waived, open)."
          + (" Stage 1 is on the App. L actuator disk (owner ruling G-4) and the propeller rows here use the same relation "
             "and factor, so with the blade-element check waived there is no independent propeller check left." if
             (res.get("record_facts") or {}).get("propeller_model") == "app_l" else ""),
          "- **Static margin by Anderson (8.76)-(8.78)**: computed in the aero report (`measurement/stage3_aero.py`).",
          "- **Engine rows**: in the engine report."]
    L += ["", "## Rows outside tolerance, not tuned", ""]
    out = [r for r in rows if r["verdict"] == "outside"]
    if not out:
        L.append("None.")
    for r in out:
        f = DIAGNOSES.get(r["id"])
        txt = f(res, r) if f else None
        L.append(f"- **{r['quantity']}**, {deviation_text(r)} against {tolerance_text(r)}. "
                 + (txt or "No diagnosis is coded for this row; see its note above."))
    t = res.get("takeoff_power_detail")
    fl = {r["id"]: r for r in rows}
    if t and "takeoff_distance" in fl and "landing_distance" in fl:
        to, ld = fl["takeoff_distance"], fl["landing_distance"]
        L += ["", "## Field length (R7)", "",
              (f"Owner ruling G-1: the field length is the computed take-off and landing distance over a 50 ft obstacle, "
               f"unfactored (no FAR 1.666 or 1.15 factor), against {t['field_length_ft']:,.0f} ft. Take-off "
               f"{fmt(to['stage3'])} ft by Anderson ({fmt(to['stage1'])} ft Stage 1); landing {fmt(ld['stage3'])} ft "
               f"({fmt(ld['stage1'])} ft Stage 1). Both are computed at take-off weight.")]
    rf = res.get("record_facts") or {}
    L += ["", "## Caveats carried", ""]
    if rf.get("unchoked_fuel_share") is not None:
        L.append(f"- {100 * rf['unchoked_fuel_share']:.1f} % of the baseline's mission fuel burns in cells where App. K's "
                 "choked-turbine assumption fails (record `unchoked_fuel_share`).")
    if (rf.get("engine") or "").startswith("RR_M250"):
        L.append("- The M250 table is validated at sea level, static and 70-100 % power only; R6 (maximum operating altitude, "
                 "relight) rests on declared assumptions (owner ruling R-f); the 23,000 ft ceiling requirement is above the "
                 "certified 20,000 ft B17 installations (`docs/validation/2026-11-24_task12_m250_r6_sources.md`).")
    L.append("- Rows marked coding check agree with Stage 1 because inputs and formula are shared, not because the "
             "quantity was verified. Rows that use the engine table are not judged (spec 7.1b).")
    return L


def report_text(res):
    """Markdown from the result dict; every number is read from it."""
    i, s = res["inputs"], res["summary"]
    cc = class_counts(res["rows"])
    cls_line = "; ".join(
        f"{c}: " + ", ".join(f"{n} {v}" for v, n in sorted(cc[c].items())) for c in (*CLASSES, "unclassified") if c in cc)
    lines = [
        "# Task 12 Stage 3: performance measured against independent book relations", "",
        (f"Design: `{i['design']}` (sha256 `{i['design_sha256']}`). Git commit `{i['git_commit']}`. "
        f"Python {i['python']}, numpy {i['numpy']}. Generated by `python -m measurement.stage3_perf` "
        "from the JSON next to this report; tolerances are spec section 7.1a, fixed before the run. "
        "A row outside tolerance is reported, not adjusted."), "",
        (f"Rows: {s['within']} within, {s['outside']} outside, {s['not judged']} not judged, "
         f"{s['not computed']} not computed."), "",
        *(["**Propeller.** Stage 1 of this record is on the App. L actuator disk (owner ruling G-4) and the blade-element "
           "check is waived (G-5), so with the propeller rows here using the same relation and factor as Stage 1 there is "
           "no independent propeller check left. The three propeller rows are coding checks.", ""]
          if (res.get("record_facts") or {}).get("propeller_model") == "app_l" else []),
        ("Each row has a class, which says what a \"within\" means: **independent** (another source, method and "
         "input), **partly independent** (another relation, with inputs or sub-models shared with Stage 1), "
         "**coding check** (same inputs and an algebraically equal formula: it can only show that the code is "
         "consistent). By class: " + cls_line + "."), "",
        ("Not in this report: the engine rows (spec 7.1b), the vortex-lattice aero rows and the Anderson static "
         "margin (stage3_aero), and the section CL_max row (SU2); range and endurance have no row of their own in "
         "7.1a and are covered by mission fuel."), "",
        "| Quantity | Class | Stage 1 | Stage 3 | Source | Deviation | Tolerance | Verdict |",
        "|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        v = r["verdict"] + (f" (numerically {'inside' if r['numerically_within'] else 'outside'})"
                            if "numerically_within" in r else "")
        lines.append(f"| {r['quantity']} ({r['unit']}) | {r.get('class') or '-'} | {fmt(r['stage1'])} | {fmt(r['stage3'])} | "
                     f"{r['source']} | {deviation_text(r)} | {tolerance_text(r)} | {v} |")
    for cmp_ in res.get("comparisons", []):
        lines += ["", "## Against an earlier record", "",
                  (f"Old: `{cmp_['old_design']}` (perf record `{cmp_['old_perf']}`, sha256 `{cmp_['old_perf_sha256']}`, "
                   f"commit `{cmp_['old_git_commit']}`). New: `{cmp_['new_design']}`. Every cell is read from the two "
                   "perf records; verdict is within or outside the tolerance of that row. Class changes are marked; a class '-' means that record carries none."), "",
                  "| Row | Old Stage 1 | Old Stage 3 | Old verdict | Old class | New Stage 1 | New Stage 3 | New verdict | New class |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for c in cmp_["rows"]:
            o, n = c["old"] or {}, c["new"]
            chg = " **(changed)**" if o.get("class") and o.get("class") != n.get("class") else ""
            lines.append(f"| {c['quantity']} ({c['unit']}) | {fmt(o.get('stage1'))} | {fmt(o.get('stage3'))} | "
                         f"{o.get('verdict', 'not in old')} | {o.get('class') or '-'} | {fmt(n.get('stage1'))} | "
                         f"{fmt(n.get('stage3'))} | {n['verdict']} | {(n.get('class') or '-')}{chg} |")
        if cmp_["rows_only_in_old"]:
            lines.append("")
            lines.append("Rows only in the old record: " + ", ".join(cmp_["rows_only_in_old"]) + ".")
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
    jet = (f"; the jet-aircraft curve of Fig. 2.55 gives Cfe {fmt(cd['Cfe_jet_curve'])} and CD0 {fmt(cd['CD0_jet_curve'])}"
           if "Cfe_jet_curve" in cd else "")
    lines += ["", (f"Zero-lift drag by (2.37): S_wet {fmt(cd['S_wet_ft2'])} ft^2, S_wet/S "
              f"{fmt(cd['S_wet_over_S'])}, fuselage Reynolds number {cd['Re_fuselage']:.3g}, Cfe "
              f"{fmt(cd['Cfe'])} (flat plate alone {fmt(cd['Cfe_flat_plate_only'])}){jet}; the Cfe that "
              f"would reproduce Stage 1's CD0 is {fmt(cd['Cfe_for_Stage1_CD0'])}."),
              "", "Rebuild check (the record against the rebuilt Stage 1 state):", "",
              "| Quantity | Record | Rebuilt |", "|---|---|---|"]
    for k, v in res["rebuild_check"].items():
        lines.append(f"| {k} | {fmt(v['record'])} | {fmt(v['rebuilt'])} |")
    lines += generated_sections(res)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()

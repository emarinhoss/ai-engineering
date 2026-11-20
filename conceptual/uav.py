"""The single-turboprop endurance UAV of Task 12, evaluated with Raymer's methods (Stage 1).

evaluate(concept, W_S, A, L) sizes one aircraft: for a take-off wing loading W_S (lb/ft^2) and
aspect ratio A it iterates the take-off weight W0 with Raymer's refined sizing (3.4), building at
each guess the geometry (ch. 6-7), drag (ch. 12), installed power from the requirements (ch. 5,
17), loads (ch. 14), component weights (ch. 15) and mission fuel (ch. 6, 19). The rubber engine's
power is whatever the binding requirement needs. layout() then places the wing for the static
margin (ch. 16) and checks the fit. Every constant comes from the ledger (data/task12/ledger.yaml)
or is a cited Raymer value.
"""
import math
from pathlib import Path

import yaml

from conceptual import geometry_sizing as geo
from conceptual import raymer_aero as aero
from conceptual import raymer_loads as loads
from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import raymer_stability as stab
from conceptual import raymer_weights as wts
from conceptual import sizing
from conceptual.units import GAL_FT3, HP, KT, NM, RHO0, isa

LEDGER = Path(__file__).resolve().parents[1] / "data" / "task12" / "ledger.yaml"
CATEGORY = "general_aviation_single"
CONCEPTS = {
    # tail arm fraction of fuselage length (Raymer p. 112-113); extra main-gear length for
    # propeller ground clearance (Raymer p. 222, at least 9 in)
    "tractor": {"tail_arm_fraction": geo.TAIL_ARM_FRACTION["front_propeller"], "gear_extra_in": 0.0},
    "pusher": {"tail_arm_fraction": geo.TAIL_ARM_FRACTION["aft_engine"], "gear_extra_in": 10.0},
}
N_CRUISE_STEPS, N_LOITER_STEPS = 10, 16


def load_ledger(path=LEDGER):
    """Ledger as {name: value} plus the raw entries; checks every entry has value, units, source,
    and that an assumed entry carries a band containing its value."""
    raw = yaml.safe_load(Path(path).read_text())
    values, entries = {}, {}
    for group in ("requirements", "assumptions"):
        for name, q in raw[group].items():
            for key in ("value", "units", "confidence", "source"):
                if key not in q:
                    raise ValueError(f"{name}: missing {key}")
            if q["confidence"] == "assumed":
                lo, hi = q.get("band", (None, None))
                if lo is None or not lo <= q["value"] <= hi:
                    raise ValueError(f"{name}: assumed without a band containing its value")
            values[name] = float(q["value"])
            entries[name] = q
    return values, entries


def _polar(geom, L, V, atm, bhp):
    """Parasite drag build-up at speed V (12.24), p. 280, and K from (12.48)-(12.49)."""
    M = V / atm["a"]
    k = L["roughness_k_ft"]
    w, ht = geom["wing"], geom["ht"]
    comps = [
        {"name": "wing", "cf": aero.cf_component(atm["rho"], V, w.mac, atm["mu"], M, k,
                                                 L["laminar_fraction_wing"]),
         "ff": aero.form_factor_wing(L["wing_t_c"], L["wing_x_c_max_t"], M), "q": 1.0,
         "s_wet": geom["s_wet_wing"]},
        {"name": "fuselage", "cf": aero.cf_component(atm["rho"], V, geom["L_f"], atm["mu"], M, k,
                                                     L["laminar_fraction_fuselage"]),
         "ff": aero.form_factor_fuselage(L["fuselage_fineness"]), "q": 1.0,
         "s_wet": geom["s_wet_fus"]},
        {"name": "horizontal_tail", "cf": aero.cf_component(atm["rho"], V, ht.mac, atm["mu"], M, k,
                                                            L["laminar_fraction_wing"]),
         "ff": aero.form_factor_wing(L["tail_t_c"], 0.3, M), "q": L["tail_interference_q"],
         "s_wet": geom["s_wet_ht"]},
        {"name": "vertical_tail", "cf": aero.cf_component(atm["rho"], V, geom["vt_mac"], atm["mu"],
                                                          M, k, L["laminar_fraction_wing"]),
         "ff": aero.form_factor_wing(L["tail_t_c"], 0.3, M), "q": L["tail_interference_q"],
         "s_wet": geom["s_wet_vt"]},
    ]
    misc = aero.misc_engine_drag_area(bhp) + L["sensor_drag_area_ft2"]
    CD0, parts = aero.cd0_buildup(comps, w.area, misc_d_q=misc, leakage_fraction=L["leakage_fraction"])
    return CD0, parts


def _geometry(W0, W_S, A, concept, L):
    """Wing, fuselage and tails sized from W0 (ch. 6-7)."""
    S = W0 / W_S
    wing = geo.Trapezoid(S, A, L["wing_taper"])
    L_f = geo.fuselage_length(W0, CATEGORY)                      # Table 6.3
    d_f = L_f / L["fuselage_fineness"]
    arm = CONCEPTS[concept]["tail_arm_fraction"] * L_f           # p. 112-113
    S_ht = geo.horizontal_tail_area(L["c_ht"], wing.mac, S, arm)  # (6.29)
    S_vt = geo.vertical_tail_area(L["c_vt"], wing.span, S, arm)   # (6.28)
    ht = geo.Trapezoid(S_ht, L["ht_aspect_ratio"], L["ht_taper"])
    vt_h = geo.vertical_tail_span(S_vt, L["vt_aspect_ratio"])
    vt_root = 2.0 * S_vt / (vt_h * (1.0 + L["vt_taper"]))
    vt_mac = (2.0 / 3.0) * vt_root * (1 + L["vt_taper"] + L["vt_taper"] ** 2) / (1 + L["vt_taper"])
    s_exposed = S - wing.root_chord * d_f                        # planform inside the body removed
    return {
        "S": S, "wing": wing, "L_f": L_f, "d_f": d_f, "arm": arm, "ht": ht,
        "S_vt": S_vt, "vt_height": vt_h, "vt_root": vt_root, "vt_mac": vt_mac,
        "s_exposed": s_exposed,
        "s_wet_wing": aero.wetted_area_wing(s_exposed, L["wing_t_c"]),         # (7.11)
        "s_wet_ht": aero.wetted_area_wing(S_ht, L["tail_t_c"]),
        "s_wet_vt": aero.wetted_area_wing(S_vt, L["tail_t_c"]),
        "s_wet_fus": 3.4 * L["fuselage_fill"] * L_f * d_f,                      # (7.12)
    }


def _cl_max(L):
    """Clean wing (12.15) and flapped (12.21) maximum lift."""
    clean = aero.wing_cl_max(L["airfoil_cl_max"])
    dl = L["flap_delta_cl_max"] * L["flap_span_fraction"]
    return {"clean": clean, "landing": clean + dl, "takeoff": clean + L["takeoff_flap_fraction"] * dl}


CLIMB_SPEED_OVER_STALL = 1.2   # climb at no less than 1.2 V_stall clean (Raymer p. 489 uses
                               # 1.2 V_stall as the climb speed in (17.110))


def _min_power_for(W, S, atm, CD0, K, eta_p, rate, lapse, clmax_clean):
    """Smallest sea-level-rated bhp that gives a rate of climb (ft/s): minimum over speed of
    (W V_v + D V)/(550 eta_p) from (17.37), divided by the power lapse (13.9). Speeds from
    1.2 V_stall clean upward."""
    best = None
    V_lo = CLIMB_SPEED_OVER_STALL * perf.stall_speed(W / S, atm["rho"], clmax_clean)
    for i in range(400):
        V = V_lo + i * 1.0
        hp = (W * rate + perf.drag(W, S, atm["rho"], V, CD0, K) * V) / (HP * eta_p)
        best = hp if best is None or hp < best else best
    return best / lapse


def _takeoff_power(W, S, CD0_to, K, clmax_to, L, D_prop):
    """Smallest bhp with take-off over 50 ft within the field length (17.8), by bisection."""
    n_rps = L["propeller_rpm"] / 60.0

    def dist(bhp):
        def thrust(V):
            t_static = prop.static_thrust(L["static_ct_over_cp"], bhp, n_rps, D_prop)
            return min(t_static, prop.thrust_from_power(bhp, L["eta_p"], max(V, 1.0)))
        try:
            return perf.takeoff_distance(W, S, RHO0, CD0_to, K, clmax_to, thrust)["total"]
        except ValueError:
            return float("inf")

    lo, hi = 10.0, 20000.0
    if dist(hi) > L["field_length_ft"]:
        return float("inf")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if dist(mid) > L["field_length_ft"] else (lo, mid)
    return hi


def _cruise_speed(W, S, rho, CD0, K, clmax_clean, L, mode):
    """Best-range (L/D max) or best-endurance (minimum power) speed, at least 1.3 V_stall."""
    f = perf.speed_max_ld if mode == "range" else perf.speed_min_power
    V, _ = f(W / S, rho, CD0, K)
    return max(V, L["speed_over_stall"] * perf.stall_speed(W / S, rho, clmax_clean))


def _mission(W0, geom, A, e, L, bhp, clmax):
    """Mission fuel (R5): take-off at full power (DR-1 p. 586), climb by the energy method (19.8),
    cruise out and back by (6.12) and loiter by (6.15) in sub-segments at the current weight, landing
    0.995 (Table 3.2), 6 % reserve and trapped fuel (3.11). Returns (fuel, segment table)."""
    S = geom["S"]
    K = aero.induced_drag_factor(A, e)
    alt = isa(L["mission_altitude_ft"])
    sl = isa(0.0)
    rows = []
    W = W0 * sizing.takeoff_fraction_power(L["cbhp_cruise"], bhp, L["takeoff_minutes"], W0)
    rows.append(("takeoff", W0, W, 0.0))
    # climb at the sea-level best-climb speed to the mission altitude and cruise speed
    CD0_sl, _ = _polar(geom, L, 200.0, sl, bhp)
    v_lo = CLIMB_SPEED_OVER_STALL * perf.stall_speed(W / S, sl["rho"], clmax["clean"])
    _, V_cl = perf.best_rate_of_climb(W, S, sl["rho"], CD0_sl, K, bhp, L["eta_p"], v_lo,
                                      v_lo + 350.0)
    CD0_alt, _ = _polar(geom, L, 250.0, alt, bhp)
    V_cr = _cruise_speed(W, S, alt["rho"], CD0_alt, K, clmax["clean"], L, "range")
    lapse = prop.piston_power_lapse(alt["sigma"])
    d_t = 0.5 * (perf.drag(W, S, sl["rho"], V_cl, CD0_sl, K) / prop.thrust_from_power(bhp, L["eta_p"], V_cl)
                 + perf.drag(W, S, alt["rho"], V_cl, CD0_alt, K)
                 / prop.thrust_from_power(bhp * lapse, L["eta_p"], V_cl))
    dhe = sizing.energy_height_change(0.0, V_cl, L["mission_altitude_ft"], V_cr)
    C = sizing.equivalent_tsfc(L["cbhp_cruise"], V_cl, L["eta_p"])
    W2 = W * sizing.climb_fraction_energy(C, dhe, V_cl, min(d_t, 0.95))
    rows.append(("climb", W, W2, 0.0))
    W = W2

    def leg(W, name, distance_ft=None, time_s=None):
        W_in = W
        n = N_CRUISE_STEPS if distance_ft else N_LOITER_STEPS
        mode = "range" if distance_ft else "loiter"
        cbhp = L["cbhp_cruise"] if distance_ft else L["cbhp_loiter"]
        v_sum = 0.0
        for _ in range(n):
            CD0, _ = _polar(geom, L, 250.0, alt, bhp)
            V = _cruise_speed(W, S, alt["rho"], CD0, K, clmax["clean"], L, mode)
            v_sum += V / n
            CD0, _ = _polar(geom, L, V, alt, bhp)
            q = 0.5 * alt["rho"] * V ** 2
            LD = sizing.lift_to_drag(q, CD0, W / S, A, e)
            if distance_ft:
                f = sizing.cruise_fraction_prop(distance_ft / n, cbhp, L["eta_p"], LD)
            else:
                f = sizing.loiter_fraction_prop(time_s / n, V, cbhp, L["eta_p"], LD)
            W *= f
        rows.append((name, W_in, W, v_sum))           # mean true airspeed over the leg
        return W

    W = leg(W, "cruise_out", distance_ft=L["radius_nm"] * NM)
    W = leg(W, "loiter", time_s=L["loiter_h"] * 3600.0)
    W = leg(W, "cruise_back", distance_ft=L["radius_nm"] * NM)
    W_end = W * sizing.LANDING_FRACTION
    rows.append(("landing", W, W_end, 0.0))
    fuel = sizing.RESERVE_FACTOR * (W0 - W_end)
    return fuel, rows


def _build(W0, concept, W_S, A, L, fuel_guess, engine=None):
    """Everything that depends on W0 at one guess. engine: None for a rubber engine (power from
    the binding requirement, weight from Table 10.4), or {"bhp", "weight_lb"} for a fixed engine
    (Raymer 6.3, p. 108-109)."""
    geom = _geometry(W0, W_S, A, concept, L)
    S, wing = geom["S"], geom["wing"]
    e = aero.oswald_straight_wing(A)                              # (12.49)
    K = aero.induced_drag_factor(A, e)
    clmax = _cl_max(L)
    sl, alt, ceil = isa(0.0), isa(L["mission_altitude_ft"]), isa(L["ceiling_ft"])
    # power: iterate once on the misc engine drag, which depends on bhp
    bhp = 0.1 * W0
    for _ in range(3):
        CD0_sl, _ = _polar(geom, L, 180.0, sl, bhp)
        CD0_alt, _ = _polar(geom, L, 250.0, alt, bhp)
        D_prop = min(geo.propeller_diameter_statistical_in(bhp) / 12.0 * 18.0 / 22.0,   # (10.24)
                     geo.max_diameter_for_tip_speed(300.0, L["propeller_rpm"], L["tip_speed_limit_fps"]))
        req = {
            "climb_sl": _min_power_for(W0, S, sl, CD0_sl, K, L["eta_p"],
                                       L["climb_rate_sl_fpm"] / 60.0, 1.0, clmax["clean"]),
            "ceiling": _min_power_for(W0, S, ceil, _polar(geom, L, 250.0, ceil, bhp)[0], K,
                                      L["eta_p"], L["ceiling_rate_fpm"] / 60.0,
                                      prop.piston_power_lapse(ceil["sigma"]), clmax["clean"]),
            "takeoff": _takeoff_power(W0, S, CD0_sl + 0.02, K, clmax["takeoff"], L, D_prop),
        }
        V_cr = _cruise_speed(W0, S, alt["rho"], CD0_alt, K, clmax["clean"], L, "range")
        req["cruise_at_altitude"] = (perf.power_required_hp(W0, S, alt["rho"], V_cr, CD0_alt, K)
                                     / L["eta_p"] / prop.piston_power_lapse(alt["sigma"]))
        bhp = max(req.values()) if engine is None else engine["bhp"]
    # loads
    CLa = aero.lift_slope(A, V_cr / alt["a"], L["airfoil_efficiency"], 0.0,
                          geom["s_exposed"] / S, aero.fuselage_lift_factor(geom["d_f"], wing.span))
    # gust loads at the maximum level speed (the V-n cruise point, Raymer 14.2, p. 338-340), at
    # sea level and at mission altitude; equivalent airspeeds
    v_c_eas = {}
    for label, atm in (("sea_level", sl), ("mission_altitude", alt)):
        lo = CLIMB_SPEED_OVER_STALL * perf.stall_speed(W_S, atm["rho"], clmax["clean"])
        vmax = perf.max_level_speed(W0, S, atm["rho"], CD0_alt if atm is alt else CD0_sl, K,
                                    bhp * prop.piston_power_lapse(atm["sigma"]), L["eta_p"],
                                    lo, 1200.0)
        v_c_eas[label] = (vmax or lo) * math.sqrt(atm["sigma"])
    n_gust = max(loads.gust_load_factor(W_S, v_c_eas[k], L["gust_ude_fps"], CLa, wing.mac,
                                        atm["rho"])[0]
                 for k, atm in (("sea_level", sl), ("mission_altitude", alt)))
    n_limit = max(L["limit_load_factor"], n_gust)
    Nz = loads.ultimate_load_factor(n_limit)
    # weights, Raymer (15.46)-(15.57) with Table 15.4 composite factors; no crew items (R14)
    q_cr = 0.5 * alt["rho"] * V_cr ** 2
    fuel_gal = fuel_guess / L["fuel_density_lb_gal"]
    f = wts.COMPOSITE_FUDGE
    eng = geo.turboprop_statistical(bhp)
    if engine is not None:
        eng = {"weight_lb": engine["weight_lb"], "in_range": True, "fixed": engine.get("name", "")}
    W_av = wts.avionics(L["avionics_uninstalled_lb"])
    W_fs = wts.fuel_system(fuel_gal, fuel_gal, 2)
    gear_extra = CONCEPTS[concept]["gear_extra_in"]
    comp = {
        "wing": f["wing"] * wts.wing(S, fuel_guess, A, 0.0, q_cr, L["wing_taper"], L["wing_t_c"], Nz, W0),
        "horizontal_tail": f["tails"] * wts.horizontal_tail(Nz, W0, q_cr, geom["ht"].area, L["tail_t_c"],
                                                            L["ht_aspect_ratio"], 0.0, L["ht_taper"]),
        "vertical_tail": f["tails"] * wts.vertical_tail(0.0, Nz, W0, q_cr, geom["S_vt"], L["tail_t_c"],
                                                        L["vt_aspect_ratio"], 0.0, L["vt_taper"]),
        "fuselage": f["fuselage"] * wts.fuselage(geom["s_wet_fus"], Nz, W0, geom["arm"],
                                                 L["fuselage_fineness"], q_cr),
        "main_gear": f["landing_gear"] * wts.main_gear(L["gear_load_factor_ultimate"], W0,
                                                       L["main_gear_length_in"] + gear_extra),
        "nose_gear": f["landing_gear"] * wts.nose_gear(L["gear_load_factor_ultimate"], W0,
                                                       L["nose_gear_length_in"] + gear_extra),
        "installed_engine": L["installed_engine_factor"] * eng["weight_lb"],
        "fuel_system": W_fs,
        "flight_controls": wts.flight_controls(geom["L_f"], wing.span, Nz, W0),
        "hydraulics": wts.hydraulics(W0),
        "avionics": W_av,
        "electrical": wts.electrical(W_fs, W_av),
    }
    We = sum(comp.values())
    fuel, rows = _mission(W0, geom, A, e, L, bhp, clmax)
    return {"geom": geom, "e": e, "K": K, "clmax": clmax, "bhp": bhp, "power_req": req,
            "D_prop": D_prop, "engine": eng, "CLa": CLa, "n_gust": n_gust, "n_limit": n_limit,
            "Nz": Nz, "V_c_eas": v_c_eas, "components": comp, "We": We, "fuel": fuel, "mission": rows,
            "V_cruise_start": V_cr, "CD0_alt": CD0_alt, "CD0_sl": CD0_sl, "q_cruise": q_cr}


def evaluate(concept, W_S, A, L, W0_guess=3000.0, engine=None):
    """Size one aircraft. Returns the converged state with W0, or raises ValueError if the
    mission does not close. engine as in _build. With a fixed engine, power_ok says whether its
    power meets every requirement."""
    state = {"fuel": 0.25 * W0_guess}
    cache = {}

    def build(W):
        key = round(W, 6)
        if key not in cache:
            cache[key] = _build(W, concept, W_S, A, L, state["fuel"], engine)
            state["fuel"] = cache[key]["fuel"]
        return cache[key]

    W0, hist = sizing.solve_takeoff_weight(
        L["payload_lb"], lambda W: build(W)["fuel"] / W, lambda W: build(W)["We"] / W, W0_guess)
    out = _build(W0, concept, W_S, A, L, state["fuel"], engine)  # final pass at the converged W0
    out["power_ok"] = max(out["power_req"].values()) <= out["bhp"] * (1 + 1e-9)
    out.update({"concept": concept, "W_S": W_S, "A": A, "W0": W0, "iterations": len(hist),
                "We_over_W0": out["We"] / W0, "fuel_over_W0": out["fuel"] / W0})
    return out


def statistical_empty_fractions(d, L):
    """Raymer's statistical empty fractions at the converged design, for comparison with the
    component build-up (A2): Table 3.1 and Table 6.2 (general aviation single), times the
    composite factor. Vmax in mph is taken as the cruise-start speed (a lower bound)."""
    W0 = d["W0"]
    vmax_mph = d["V_cruise_start"] / KT * 1.151
    return {
        "table_3_1": sizing.empty_fraction_table31(W0, CATEGORY, material_factor=L["composite_factor"]),
        "table_6_2": sizing.empty_fraction_table62(W0, CATEGORY, d["A"], d["bhp"] / W0, d["W_S"],
                                                   vmax_mph, material_factor=L["composite_factor"]),
        "build_up": d["We"] / W0,
    }


def fuel_volume_check(d, L):
    """Fuel volume needed against integral wing-tank volume (Raymer 10.5, p. 227-228): a box between
    the spars of depth t/c x chord over the tank span, 85 % usable. Returns (needed, available) ft^3."""
    w = d["geom"]["wing"]
    needed = d["fuel"] / L["fuel_density_lb_gal"] * GAL_FT3
    n = 50
    half = w.span / 2.0
    y_end = L["wing_tank_span_fraction"] * half
    y0 = d["geom"]["d_f"] / 2.0
    vol = 0.0
    for i in range(n):
        y = y0 + (y_end - y0) * (i + 0.5) / n
        c = w.root_chord * (1.0 - (1.0 - w.taper) * y / half)
        vol += L["wing_tank_chord_fraction"] * c * L["wing_t_c"] * c * (y_end - y0) / n
    return needed, 2.0 * vol * L["wing_tank_usable"]


def layout(d, L):
    """Place the components along the fuselage, then the wing so that the static margin range
    (full and empty fuel) is centred in R13. Returns the stations, CGs, neutral point and margins.

    Stations as fractions of fuselage length (judgements recorded here; Raymer Table 15.2 p. 398
    gives wing and tails at 40 % MAC and fuselage and all-else at 40-50 % length)."""
    g, w = d["geom"], d["geom"]["wing"]
    L_f, comp = g["L_f"], d["components"]
    tractor = d["concept"] == "tractor"
    fixed = {   # station fraction of fuselage length for items not tied to the wing
        "installed_engine": 0.07 if tractor else 0.88,
        "payload": 0.30 if tractor else 0.10,
        "avionics": 0.20 if tractor else 0.22,
        "fuselage": 0.45, "flight_controls": 0.55, "hydraulics": 0.45, "electrical": 0.30,
        "nose_gear": 0.10,
    }
    mac = w.mac
    CLa_w = d["CLa"]
    CLa_h = aero.lift_slope(L["ht_aspect_ratio"], 0.0, L["airfoil_efficiency"])
    dah = 1.0 - stab.downwash_gradient_lifting_line(CLa_w, d["A"])
    Cma_fus = stab.fuselage_cm_alpha_per_deg(L["fuselage_kf"], g["d_f"], L_f, mac, g["S"]) * 180 / math.pi

    def state(x_le):
        """x_le: fuselage station of the MAC leading edge (ft)."""
        x_ac = x_le + 0.25 * mac
        x_wing = x_le + 0.40 * mac
        x_ht = x_ac + g["arm"] + 0.15 * g["ht"].mac                # tail 40 % MAC = ac + 0.15 MAC
        x_vt = x_ac + g["arm"] + 0.15 * g["vt_mac"]
        items = {k: (comp[k], fixed[k] * L_f) for k in comp if k in fixed}
        items["payload"] = (L["payload_lb"], fixed["payload"] * L_f)
        items["wing"] = (comp["wing"], x_wing)
        items["horizontal_tail"] = (comp["horizontal_tail"], x_ht)
        items["vertical_tail"] = (comp["vertical_tail"], x_vt)
        items["fuel_system"] = (comp["fuel_system"], x_wing)
        items["avionics"] = (comp["avionics"], fixed["avionics"] * L_f)
        W_e = sum(m for m, _ in items.values())
        M_e = sum(m * x for m, x in items.values())
        fuel = d["fuel"]
        cg_full = (M_e + fuel * x_wing) / (W_e + fuel)
        cg_empty = M_e / W_e
        x_np = stab.neutral_point(CLa_w, x_ac / mac, Cma_fus, L["tail_eta_h"],
                                  g["ht"].area / g["S"], CLa_h, dah, (x_ac + g["arm"]) / mac) * mac
        return {"x_le": x_le, "x_ac": x_ac, "x_np": x_np, "cg_full": cg_full, "cg_empty": cg_empty,
                "sm_full": (x_np - cg_full) / mac, "sm_empty": (x_np - cg_empty) / mac,
                "items": items, "x_ht": x_ht, "x_vt": x_vt}

    target = 0.5 * (L["static_margin_min"] + L["static_margin_max"])
    lo, hi = 0.05 * L_f, 0.75 * L_f
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        s = state(mid)
        centre = 0.5 * (s["sm_full"] + s["sm_empty"])
        # moving the wing aft moves the neutral point aft faster than the CG, raising the margin
        lo, hi = (mid, hi) if centre < target else (lo, mid)
    s = state(0.5 * (lo + hi))
    s["dah_da"], s["Cma_fus"], s["CLa_h"] = dah, Cma_fus, CLa_h
    # trim at loiter start and end: tail lift coefficient from the moment balance (16.7), p. 416
    S, S_h = g["S"], g["ht"].area
    alt = isa(L["mission_altitude_ft"])
    trims = {}
    for label, W, cg in (("loiter_start_full", d["mission"][3][1], s["cg_full"]),
                         ("loiter_end_empty_cg", d["mission"][3][2], s["cg_empty"])):
        V = d["mission"][3][3]
        CL = W / (0.5 * alt["rho"] * V ** 2 * S)
        num = CL * (cg - s["x_ac"]) / mac + L["airfoil_cm0"]
        den = L["tail_eta_h"] * S_h / S * ((s["x_ac"] + g["arm"]) - cg) / mac
        trims[label] = {"CL_wing": CL, "CL_tail": num / den}
    s["trim"] = trims
    return s


def performance(d, L):
    """As-sized performance at take-off weight: stall, take-off and landing distance, sea-level
    climb, service ceiling, maximum level speed at mission altitude (ch. 5, 17)."""
    W0, S, K = d["W0"], d["geom"]["S"], d["K"]
    sl = isa(0.0)
    bhp = d["bhp"]
    n_rps = L["propeller_rpm"] / 60.0

    def thrust(V):
        return min(prop.static_thrust(L["static_ct_over_cp"], bhp, n_rps, d["D_prop"]),
                   prop.thrust_from_power(bhp, L["eta_p"], max(V, 1.0)))

    to = perf.takeoff_distance(W0, S, sl["rho"], d["CD0_sl"] + 0.02, K, d["clmax"]["takeoff"], thrust)
    ld = perf.landing_distance(W0, S, sl["rho"], d["CD0_sl"] + 0.05, K, d["clmax"]["landing"])
    clean = d["clmax"]["clean"]
    v_lo = CLIMB_SPEED_OVER_STALL * perf.stall_speed(d["W_S"], sl["rho"], clean)
    vv, v_best = perf.best_rate_of_climb(W0, S, sl["rho"], d["CD0_sl"], K, bhp, L["eta_p"],
                                         v_lo, v_lo + 350.0)
    ceiling = None
    for h in range(0, 45001, 250):
        a = isa(float(h))
        lo = CLIMB_SPEED_OVER_STALL * perf.stall_speed(d["W_S"], a["rho"], clean)
        r, _ = perf.best_rate_of_climb(W0, S, a["rho"], d["CD0_alt"], K,
                                       bhp * prop.piston_power_lapse(a["sigma"]), L["eta_p"],
                                       lo, lo + 400.0)
        if r < L["ceiling_rate_fpm"] / 60.0:
            ceiling = h
            break
    alt = isa(L["mission_altitude_ft"])
    vmax = perf.max_level_speed(W0, S, alt["rho"], d["CD0_alt"], K,
                                bhp * prop.piston_power_lapse(alt["sigma"]), L["eta_p"], 120.0, 900.0)
    return {"V_stall_clean_kt": perf.stall_speed(d["W_S"], sl["rho"], d["clmax"]["clean"]) / KT,
            "V_stall_landing_kt": perf.stall_speed(d["W_S"], sl["rho"], d["clmax"]["landing"]) / KT,
            "takeoff_ft": to["total"], "takeoff": to, "landing_ft": ld["total"], "landing": ld,
            "roc_sl_fpm": vv * 60.0, "v_best_climb_kt": v_best / KT,
            "service_ceiling_ft": ceiling, "vmax_alt_kt": (vmax or 0.0) / KT}

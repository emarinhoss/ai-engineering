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
    # tail arm fraction of fuselage length (Raymer p. 112-113)
    "tractor": {"tail_arm_fraction": geo.TAIL_ARM_FRACTION["front_propeller"]},
    "pusher": {"tail_arm_fraction": geo.TAIL_ARM_FRACTION["aft_engine"]},
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
    if geom["s_wet_sponsons"] > 0.0:
        comps.append({"name": "sponsons",
                      "cf": aero.cf_component(atm["rho"], V, geom["sponson_length"], atm["mu"], M, k, 0.0),
                      "ff": aero.form_factor_fuselage(geom["sponson_length"] / geom["sponson_depth"]),
                      "q": L["sponson_interference_q"], "s_wet": geom["s_wet_sponsons"]})
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
    # (6.29); ht_volume_scale > 1 when the tail is enlarged for nose rotation (p. 432-433)
    S_ht = geo.horizontal_tail_area(L["c_ht"] * L.get("ht_volume_scale", 1.0), wing.mac, S, arm)
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
        **_sponsons(W0, L),
    }


def _sponsons(W0, L):
    """Two main-gear sponsons (Gate A round 3): bodies sized on the Table 11.1 main tyre, wetted
    area by (7.12) with the fuselage fill factor."""
    if L.get("no_sponsons"):                                     # reference trade only
        return {"sponson_length": 0.0, "sponson_depth": 0.0, "s_wet_sponsons": 0.0}
    tyre_ft = geo.main_tyre_in(L["main_wheel_load_fraction"] * W0)["diameter"] / 12.0
    length = L["sponson_length_per_tyre"] * tyre_ft
    depth = L["sponson_depth_per_tyre"] * tyre_ft
    return {"sponson_length": length, "sponson_depth": depth,
            "s_wet_sponsons": 2.0 * 3.4 * L["fuselage_fill"] * length * depth}


def _cl_max(L):
    """Clean wing (12.15) and flapped (12.21) maximum lift."""
    clean = aero.wing_cl_max(L["airfoil_cl_max"])
    dl = L["flap_delta_cl_max"] * L["flap_span_fraction"]
    return {"clean": clean, "landing": clean + dl, "takeoff": clean + L["takeoff_flap_fraction"] * dl}


def _gear_length_in(geom, L, D_prop, concept):
    """Main-gear length (in): the ledger value, or longer if the propeller needs it for the 9 in
    clearance of Raymer p. 222. Tractor: level attitude at the nose. Pusher: rotated by the
    landing/rotation angle (p. 232) about a main wheel at the assumed station."""
    clear = L["prop_clearance_in"] / 12.0
    r = D_prop / 2.0
    if concept == "tractor":
        need_ft = r + clear - geom["d_f"] / 2.0
    else:
        th = math.radians(L["rotation_angle_deg_pusher"])
        dx = geom["L_f"] * (1.0 - L["main_gear_station_guess"])
        # centreline height h above ground at the wheel; after rotation the propeller hub sits at
        # h cos(th) - dx sin(th); its lowest tip must clear by 9 in
        need_ft = ((r + clear + dx * math.sin(th)) / math.cos(th) - geom["d_f"] / 2.0
                   - L.get("prop_hub_offset_ft", 0.0))                 # raised thrust line
    return max(L["main_gear_length_in"], 12.0 * need_ft)


def _gear_drag_area(W0, L, gear_in):
    """Gear-down D/q (ft^2): tyres (Table 11.1 size) and struts times the D/q-per-area values of
    Raymer's gear-drag table (DR-1 p. 572), times 1.2 interference and 1.07 open wells (p. 286-288).
    Two mains and one nose wheel; the nose tyre at 80 % of main size (p. 233: 60-100 %)."""
    main = geo.main_tyre_in(L["main_wheel_load_fraction"] * W0)
    a_main = main["diameter"] * main["width"] / 144.0
    a_tyres = 2 * a_main + L["nose_tyre_scale"] ** 2 * a_main
    a_struts = 3 * gear_in * L["strut_width_in"] / 144.0
    return L["gear_interference"] * (L["tyre_drag_per_area"] * a_tyres
                                     + L["strut_drag_per_area"] * a_struts)


def _flap_cd0(L, deflection_deg):
    """Flap parasite drag 0.0023 (flap span/wing span) delta (12.37), p. 288, with the flapped-area
    fraction standing in for the span fraction."""
    return 0.0023 * L["flap_span_fraction"] * deflection_deg


def _min_power_for(W, S, atm, CD0, K, eta_p, rate, lapse, clmax_clean, L, n=1.0):
    """Smallest sea-level-rated bhp that gives a rate of climb (ft/s) at load factor n: minimum
    over speed of (W V_v + D V)/(550 eta_p) from (17.37), divided by the power lapse (13.9).
    Speeds from the climb-speed floor (Raymer p. 489) upward."""
    best = None
    V_lo = L["climb_speed_over_stall"] * perf.stall_speed(n * W / S, atm["rho"], clmax_clean)
    for i in range(400):
        V = V_lo + i * 1.0
        hp = (W * rate + perf.drag(W, S, atm["rho"], V, CD0, K, n) * V) / (HP * eta_p)
        best = hp if best is None or hp < best else best
    return best / lapse


def _lapse(model, h_ft, atm, V):
    """Full-throttle shaft power over rated: the engine table when there is one, else the piston
    lapse (13.9) Stage 1 used for the turboprop (Gate A record)."""
    if model is None:
        return prop.piston_power_lapse(atm["sigma"])
    return model.lapse(h_ft, V / KT)


def _leg_speed(W, S, atm, h_ft, CD0, K, clmax_clean, L, mode, model, bhp):
    """Speed for one mission sub-step, at least 1.3 V_stall (R17). Without an engine table:
    Raymer's best-range or best-endurance speed. With one: the speed on a grid from the floor to
    2.5 times it that minimises fuel per unit distance (range) or per unit time (loiter), using
    the table's part-power SFC; (6.12) and (6.15) assume a constant SFC, which a turbine at part
    power does not have. Returns (V, floored, cbhp)."""
    V, floored = _cruise_speed(W, S, atm["rho"], CD0, K, clmax_clean, L, mode)
    if model is None:
        return V, floored, None
    floor = L["speed_over_stall"] * perf.stall_speed(W / S, atm["rho"], clmax_clean)
    best = None
    for i in range(76):
        Vi = floor * (1.0 + 0.02 * i)
        shp = perf.drag(W, S, atm["rho"], Vi, CD0, K) * Vi / (HP * L["eta_p"])
        if shp > bhp * model.lapse(h_ft, Vi / KT):
            continue
        c = model.bsfc(h_ft, Vi / KT, shp)
        cost = c * shp / (Vi if mode == "range" else 1.0)
        if best is None or cost < best[0]:
            best = (cost, Vi, i == 0, c)
    if best is None:
        raise ValueError("no speed on the leg within the engine's power")
    return best[1], best[2], best[3]


def _vmax_consistent(W, S, geom, L, atm, h_ft, K, bhp, model, v_lo):
    """Maximum level speed with the shaft power and CD0 both taken at that speed: fixed point
    over max_level_speed (Gate A round 4, R4-1; the earlier code used them at the cruise speed)."""
    V = 1.5 * v_lo
    vmax = None
    for _ in range(20):
        CD0, _ = _polar(geom, L, V, atm, bhp)
        vmax = perf.max_level_speed(W, S, atm["rho"], CD0, K, bhp * _lapse(model, h_ft, atm, V),
                                    L["eta_p"], v_lo, 1200.0)
        if vmax is None or abs(vmax - V) < 0.01:
            break
        V = vmax
    return vmax


def _thrust_fn(bhp, L, D_prop):
    n_rps = L["propeller_rpm"] / 60.0

    def thrust(V):
        t_static = prop.static_thrust(L["static_ct_over_cp"], bhp, n_rps, D_prop)
        return min(t_static, prop.thrust_from_power(bhp, L["eta_p"], max(V, 1.0)))
    return thrust


def _takeoff(W, S, CD0_to, K, clmax_to, L, bhp, D_prop):
    return perf.takeoff_distance(W, S, RHO0, CD0_to, K, clmax_to, _thrust_fn(bhp, L, D_prop),
                                 mu=L["rolling_mu"], CL_ground=L["cl_ground"])


def _takeoff_power(W, S, CD0_to, K, clmax_to, L, D_prop):
    """Smallest bhp with take-off over 50 ft within the field length (17.8), by bisection."""
    def dist(bhp):
        try:
            return _takeoff(W, S, CD0_to, K, clmax_to, L, bhp, D_prop)["total"]
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
    """Best-range (L/D max) or best-endurance (minimum power) speed, at least 1.3 V_stall.
    Returns (speed, True if the 1.3 V_stall floor set it)."""
    f = perf.speed_max_ld if mode == "range" else perf.speed_min_power
    V, _ = f(W / S, rho, CD0, K)
    floor = L["speed_over_stall"] * perf.stall_speed(W / S, rho, clmax_clean)
    return (V, False) if V >= floor else (floor, True)


def _mission(W0, geom, A, e, L, bhp, clmax, model=None):
    """Mission fuel (R5): take-off at full power (DR-1 p. 586), climb by the energy method (19.8),
    cruise out and back by (6.12) and loiter by (6.15) in sub-segments at the current weight,
    landing 0.995 (Table 3.2), 6 % reserve and trapped fuel (3.11). Returns (fuel, rows); a row is
    (segment, W start, W end, mean TAS ft/s, fraction of sub-segments where the floor set speed)."""
    S = geom["S"]
    K = aero.induced_drag_factor(A, e)
    alt = isa(L["mission_altitude_ft"])
    sl = isa(0.0)
    rows = []
    h_alt = L["mission_altitude_ft"]
    c_to = L["cbhp_cruise"] if model is None else model.bsfc(0.0, 60.0, bhp * model.lapse(0.0, 60.0))
    W = W0 * sizing.takeoff_fraction_power(c_to, bhp, L["takeoff_minutes"], W0)
    rows.append(("takeoff", W0, W, 0.0, 0.0, c_to))
    CD0_sl, _ = _polar(geom, L, 200.0, sl, bhp)
    v_lo = L["climb_speed_over_stall"] * perf.stall_speed(W / S, sl["rho"], clmax["clean"])
    _, V_cl = perf.best_rate_of_climb(W, S, sl["rho"], CD0_sl, K, bhp, L["eta_p"], v_lo,
                                      v_lo + 350.0)
    CD0_alt, _ = _polar(geom, L, 250.0, alt, bhp)
    V_cr, _ = _cruise_speed(W, S, alt["rho"], CD0_alt, K, clmax["clean"], L, "range")
    lapse = _lapse(model, h_alt, alt, V_cl)
    d_t = 0.5 * (perf.drag(W, S, sl["rho"], V_cl, CD0_sl, K) / prop.thrust_from_power(bhp, L["eta_p"], V_cl)
                 + perf.drag(W, S, alt["rho"], V_cl, CD0_alt, K)
                 / prop.thrust_from_power(bhp * lapse, L["eta_p"], V_cl))
    dhe = sizing.energy_height_change(0.0, V_cl, L["mission_altitude_ft"], V_cr)
    # climb at full throttle: SFC at mid-altitude, full power, from the table when there is one
    c_cl = (L["cbhp_cruise"] if model is None
            else model.bsfc(0.5 * h_alt, V_cl / KT, bhp * model.lapse(0.5 * h_alt, V_cl / KT)))
    C = sizing.equivalent_tsfc(c_cl, V_cl, L["eta_p"])
    W2 = W * sizing.climb_fraction_energy(C, dhe, V_cl, min(d_t, 0.95))
    rows.append(("climb", W, W2, 0.0, 0.0, c_cl))
    W = W2

    def leg(W, name, distance_ft=None, time_s=None):
        W_in = W
        n = N_CRUISE_STEPS if distance_ft else N_LOITER_STEPS
        mode = "range" if distance_ft else "loiter"
        cbhp = L["cbhp_cruise"] if distance_ft else L["cbhp_loiter"]
        v_sum, floor_steps, c_sum = 0.0, 0, 0.0
        for _ in range(n):
            CD0, _ = _polar(geom, L, 250.0, alt, bhp)
            V, floored, c_tab = _leg_speed(W, S, alt, h_alt, CD0, K, clmax["clean"], L, mode, model, bhp)
            if c_tab is not None:
                cbhp = c_tab
            v_sum += V / n
            c_sum += cbhp / n
            floor_steps += floored
            CD0, _ = _polar(geom, L, V, alt, bhp)
            q = 0.5 * alt["rho"] * V ** 2
            LD = sizing.lift_to_drag(q, CD0, W / S, A, e)
            if distance_ft:
                f = sizing.cruise_fraction_prop(distance_ft / n, cbhp, L["eta_p"], LD)
            else:
                f = sizing.loiter_fraction_prop(time_s / n, V, cbhp, L["eta_p"], LD)
            W *= f
        rows.append((name, W_in, W, v_sum, floor_steps / n, c_sum))
        return W

    W = leg(W, "cruise_out", distance_ft=L["radius_nm"] * NM)
    W = leg(W, "loiter", time_s=L["loiter_h"] * 3600.0)
    W = leg(W, "cruise_back", distance_ft=L["radius_nm"] * NM)
    W_end = W * sizing.LANDING_FRACTION
    rows.append(("landing", W, W_end, 0.0, 0.0, 0.0))
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
    bhp = 0.1 * W0 if engine is None else engine["bhp"]
    model = None if engine is None else engine.get("model")
    h_alt, h_ceil = L["mission_altitude_ft"], L["ceiling_ft"]
    for _ in range(3):        # the misc engine drag and the propeller depend on bhp
        CD0_sl, _ = _polar(geom, L, 180.0, sl, bhp)
        CD0_alt, _ = _polar(geom, L, 250.0, alt, bhp)
        D_prop = min(geo.propeller_diameter_statistical_in(bhp, blades=3) / 12.0,      # (10.24)
                     geo.max_diameter_for_tip_speed(300.0, L["propeller_rpm"], L["tip_speed_limit_fps"]))
        gear_in = _gear_length_in(geom, L, D_prop, concept)
        gear_dq = _gear_drag_area(W0, L, gear_in)
        CD0_to = CD0_sl + gear_dq / S + _flap_cd0(L, L["flap_deflection_takeoff_deg"])
        CD0_land = CD0_sl + gear_dq / S + _flap_cd0(L, L["flap_deflection_landing_deg"])
        V_lt, _ = _cruise_speed(W0, S, alt["rho"], CD0_alt, K, clmax["clean"], L, "loiter")
        n_turn = 1.0 / math.cos(math.radians(L["turn_bank_deg"]))
        V_ceil = L["climb_speed_over_stall"] * perf.stall_speed(W0 / S, ceil["rho"], clmax["clean"])
        req = {
            "climb_sl": _min_power_for(W0, S, sl, CD0_sl, K, L["eta_p"],
                                       L["climb_rate_sl_fpm"] / 60.0, 1.0, clmax["clean"], L),
            # CD0 and power at the climb-speed floor at the ceiling, where the best climb sits
            # (Gate A round 4, R4-2), not at the 250 ft/s cruise reference
            "ceiling": _min_power_for(W0, S, ceil, _polar(geom, L, V_ceil, ceil, bhp)[0], K,
                                      L["eta_p"], L["ceiling_rate_fpm"] / 60.0,
                                      _lapse(model, h_ceil, ceil, V_ceil), clmax["clean"], L),
            "takeoff": _takeoff_power(W0, S, CD0_to, K, clmax["takeoff"], L, D_prop),
            # R16: sustained turn at loiter speed and altitude, level (17.4), power = D V
            "turn_at_loiter": (perf.drag(W0, S, alt["rho"], V_lt, CD0_alt, K, n_turn) * V_lt
                               / (HP * L["eta_p"]) / _lapse(model, h_alt, alt, V_lt)),
        }
        V_cr, _ = _cruise_speed(W0, S, alt["rho"], CD0_alt, K, clmax["clean"], L, "range")
        req["cruise_at_altitude"] = (perf.power_required_hp(W0, S, alt["rho"], V_cr, CD0_alt, K)
                                     / L["eta_p"] / _lapse(model, h_alt, alt, V_cr))
        bhp = max(req.values()) if engine is None else engine["bhp"]
    # loads: gust at the maximum level speed (the V-n cruise point, p. 338-340) at sea level and
    # mission altitude, at take-off and at zero-fuel weight (a lighter aircraft takes a larger gust
    # load factor, p. 340); equivalent airspeeds
    CLa = aero.lift_slope(A, V_cr / alt["a"], L["airfoil_efficiency"], 0.0,
                          geom["s_exposed"] / S, aero.fuselage_lift_factor(geom["d_f"], wing.span))
    v_c_eas = {}
    for label, atm, h in (("sea_level", sl, 0.0), ("mission_altitude", alt, h_alt)):
        lo = L["climb_speed_over_stall"] * perf.stall_speed(W_S, atm["rho"], clmax["clean"])
        vmax = _vmax_consistent(W0, S, geom, L, atm, h, K, bhp, model, lo)
        v_c_eas[label] = (vmax or lo) * math.sqrt(atm["sigma"])
        if L.get("vc_placard_kt_eas"):
            # R18 (Gate A round 4 ruling, Eder 2026-11-21): one V_C placard in EAS at every
            # altitude, enforced by the autopilot; the structure and gusts are sized at it
            v_c_eas[label] = L["vc_placard_kt_eas"] * KT
    W_zf = W0 - fuel_guess
    gusts = {}
    for label, atm in (("sea_level", sl), ("mission_altitude", alt)):
        for wlabel, W in (("takeoff_weight", W0), ("zero_fuel_weight", W_zf)):
            gusts[f"{label}/{wlabel}"] = loads.gust_load_factor(W / S, v_c_eas[label],
                                                                L["gust_ude_fps"], CLa, wing.mac,
                                                                atm["rho"])[0]
    n_gust = max(gusts.values())
    n_limit = max(L["limit_load_factor"], n_gust)
    Nz = loads.ultimate_load_factor(n_limit)
    # weights, Raymer (15.46)-(15.57) with Table 15.4 composite factors; no crew items (R14). The
    # dynamic pressure q is taken at the design cruise speed V_C of the V-n diagram (the sea-level
    # maximum level speed), so the structure is sized at the speed it is cleared to fly
    q_design = 0.5 * RHO0 * v_c_eas["sea_level"] ** 2
    fuel_gal = fuel_guess / L["fuel_density_lb_gal"]
    f = wts.COMPOSITE_FUDGE
    eng = geo.turboprop_statistical(bhp)
    if engine is not None:
        eng = dict(geo.turboprop_statistical(bhp), weight_lb=engine["weight_lb"],
                   fixed=engine.get("name", ""))
    W_av = wts.avionics(L["avionics_uninstalled_lb"])
    W_fs = wts.fuel_system(fuel_gal, fuel_gal, 2)
    comp = {
        "wing": f["wing"] * wts.wing(S, fuel_guess, A, 0.0, q_design, L["wing_taper"], L["wing_t_c"], Nz, W0),
        "horizontal_tail": f["tails"] * wts.horizontal_tail(Nz, W0, q_design, geom["ht"].area, L["tail_t_c"],
                                                            L["ht_aspect_ratio"], 0.0, L["ht_taper"]),
        "vertical_tail": f["tails"] * wts.vertical_tail(0.0, Nz, W0, q_design, geom["S_vt"], L["tail_t_c"],
                                                        L["vt_aspect_ratio"], 0.0, L["vt_taper"]),
        "fuselage": f["fuselage"] * wts.fuselage(geom["s_wet_fus"], Nz, W0, geom["arm"],
                                                 L["fuselage_fineness"], q_design),
        "main_gear": f["landing_gear"] * wts.main_gear(L["gear_load_factor_ultimate"], W0, gear_in),
        "nose_gear": f["landing_gear"] * wts.nose_gear(L["gear_load_factor_ultimate"], W0, gear_in),
        "installed_engine": L["installed_engine_factor"] * eng["weight_lb"],
        "sponsons": f["fuselage"] * L["sponson_weight_per_wetted"] * geom["s_wet_sponsons"],
        "fuel_system": W_fs,
        "flight_controls": wts.flight_controls(geom["L_f"], wing.span, Nz, W0),
        "hydraulics": wts.hydraulics(W0),
        "avionics": W_av,
        "electrical": wts.electrical(W_fs, W_av),
    }
    We = sum(comp.values())
    fuel, rows = _mission(W0, geom, A, e, L, bhp, clmax, model)
    return {"geom": geom, "e": e, "K": K, "clmax": clmax, "bhp": bhp, "power_req": req, "engine_model": model,
            "D_prop": D_prop, "gear_length_in": gear_in, "gear_drag_area": gear_dq,
            "engine": eng, "CLa": CLa, "gusts": gusts, "n_gust": n_gust, "n_limit": n_limit,
            "n_negative_gust": 2.0 - n_gust, "Nz": Nz, "V_c_eas": v_c_eas, "q_design": q_design,
            "components": comp, "We": We, "fuel": fuel, "mission": rows,
            "V_cruise_start": V_cr, "V_loiter_start": V_lt, "CD0_alt": CD0_alt, "CD0_sl": CD0_sl,
            "CD0_takeoff": CD0_to, "CD0_landing": CD0_land}


def evaluate(concept, W_S, A, L, W0_guess=3000.0, engine=None):
    """Size one aircraft. Returns the converged state with W0, or raises ValueError if the
    mission does not close. engine as in _build. With a fixed engine, power_ok says whether its
    power meets every requirement."""
    if engine is not None:
        # a fixed engine may carry its own fuel consumption (datasheet values replace Table 3.4)
        L = dict(L, **{k: engine[k] for k in ("cbhp_cruise", "cbhp_loiter") if engine.get(k)})
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
                "We_over_W0": out["We"] / W0, "fuel_over_W0": out["fuel"] / W0,
                "ledger_used": L})
    return out


def statistical_empty_fractions(d, L):
    """Raymer's statistical empty fractions at the converged design against the component
    build-up, and a decomposition of the gap (reviewer finding F4):
    - crew items Raymer's general-aviation set would add: furnishings (15.59) and air conditioning
      and anti-ice (15.58), the latter zero with no crew;
    - the build-up without the Table 15.4 composite factors (metal), against the fit without the
      0.95 factor, which isolates how far the group equations sit from the fit at this size;
    - Raymer's approximate group weights (Table 15.2, general aviation) as a cross-check.
    Vmax in mph is the computed sea-level maximum level speed."""
    W0 = d["W0"]
    comp = d["components"]
    f = wts.COMPOSITE_FUDGE
    vmax_mph = d["V_c_eas"]["sea_level"] / KT * 1.151
    furnishings = max(0.0, 0.0582 * W0 - 65.0)                                   # (15.59)
    fudge_of = {"wing": f["wing"], "horizontal_tail": f["tails"], "vertical_tail": f["tails"],
                "fuselage": f["fuselage"], "main_gear": f["landing_gear"], "nose_gear": f["landing_gear"]}
    metal = sum(v / fudge_of.get(k, 1.0) for k, v in comp.items())
    g = d["geom"]
    approx = (2.5 * g["s_exposed"] + 2.0 * (g["ht"].area + g["S_vt"]) + 1.4 * g["s_wet_fus"]
              + 0.057 * W0 + 1.4 * d["engine"]["weight_lb"] + 0.10 * W0)            # Table 15.2
    t31 = sizing.empty_fraction_table31(W0, CATEGORY)
    return {
        "table_3_1": t31 * L["composite_factor"],
        "table_3_1_metal": t31,
        "table_6_2": sizing.empty_fraction_table62(W0, CATEGORY, d["A"], d["bhp"] / W0, d["W_S"],
                                                   vmax_mph, material_factor=L["composite_factor"]),
        "build_up": d["We"] / W0,
        "build_up_metal": metal / W0,
        "crew_items_furnishings": furnishings / W0,
        "build_up_metal_with_crew_items": (metal + furnishings) / W0,
        "table_15_2_approximate": approx / W0,
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


def _stations(concept, L):
    t = concept == "tractor"
    return {
        "installed_engine": L["station_engine_tractor"] if t else L["station_engine_pusher"],
        "payload": L["station_payload_tractor"] if t else L["station_payload_pusher"],
        "avionics": L["station_avionics"], "fuselage": L["station_fuselage"],
        "flight_controls": L["station_flight_controls"], "hydraulics": L["station_systems"],
        "electrical": L["station_systems"], "nose_gear": L["station_nose_gear"],
    }


def wing_moment_coefficient(L, A):
    """Wing moment about its a.c. from the airfoil's, Cm_w = Cm0 A cos^2 L/(A + 2 cos L) (16.16),
    p. 422, unswept."""
    return L["airfoil_cm0"] * A / (A + 2.0)


def overturn_track(x_main, x_nose, x_cg, h_cg, max_deg):
    """Main-gear half-track for an overturn angle of at most max_deg (Raymer p. 232: at most 63 deg,
    measured from the CG to the line through the nose and main wheels, viewed along that line). In
    plan the CG lies a distance d from that line, d = (x_cg - x_nose) sin(delta), with
    tan(delta) = half-track/(x_main - x_nose); the overturn angle is atan(h_cg/d)."""
    d_req = h_cg / math.tan(math.radians(max_deg))
    if d_req >= x_cg - x_nose:
        return float("inf")
    delta = math.asin(d_req / (x_cg - x_nose))
    return (x_main - x_nose) * math.tan(delta)


def layout(d, L):
    """Place the components (stations from the ledger), the main gear by the tipback rule (Raymer
    p. 232) and the wing so that the static margin range (full and empty fuel) is centred in R13.
    Then: nose-wheel load (p. 232-233), moving the nose wheel forward inside its band when the load
    is above the 8-15 % optimum; main-gear track for the overturn limit (p. 232) and where the
    wheels retract; propeller clearance (p. 222); trim on every leg (16.7); nose rotation at
    0.8 V_TO with the forward CG (p. 432-433)."""
    g, w = d["geom"], d["geom"]["wing"]
    L_f, comp = g["L_f"], d["components"]
    fixed = _stations(d["concept"], L)
    mac = w.mac
    CLa_w = d["CLa"]
    CLa_h = aero.lift_slope(L["ht_aspect_ratio"], 0.0, L["airfoil_efficiency"])
    dah = 1.0 - stab.downwash_gradient_lifting_line(CLa_w, d["A"])
    Cma_fus = stab.fuselage_cm_alpha_per_deg(L["fuselage_kf"], g["d_f"], L_f, mac, g["S"]) * 180 / math.pi
    h_cg = d["gear_length_in"] / 12.0 + g["d_f"] / 2.0          # CG height above ground (ft)
    tb = math.tan(math.radians(L["tipback_angle_deg"]))
    cm_w = wing_moment_coefficient(L, d["A"])

    def state(x_le, nose_station):
        x_ac = x_le + 0.25 * mac
        x_wing = x_le + 0.40 * mac
        x_ht = x_ac + g["arm"] + 0.15 * g["ht"].mac                # tail 40 % MAC = ac + 0.15 MAC
        x_vt = x_ac + g["arm"] + 0.15 * g["vt_mac"]
        items = {k: (comp[k], fixed[k] * L_f) for k in comp if k in fixed}
        items["nose_gear"] = (comp["nose_gear"], nose_station * L_f)
        items["payload"] = (L["payload_lb"], fixed["payload"] * L_f)
        items["wing"] = (comp["wing"], x_wing)
        items["horizontal_tail"] = (comp["horizontal_tail"], x_ht)
        items["vertical_tail"] = (comp["vertical_tail"], x_vt)
        items["fuel_system"] = (comp["fuel_system"], x_wing)
        x_main = x_wing
        if "sponsons" in comp:
            items["sponsons"] = (comp["sponsons"], x_wing)
        for _ in range(20):                                      # main gear by tipback, iterated
            items["main_gear"] = (comp["main_gear"], x_main)
            W_e = sum(m for m, _ in items.values())
            M_e = sum(m * x for m, x in items.values())
            cg_full = (M_e + d["fuel"] * x_wing) / (W_e + d["fuel"])
            cg_empty = M_e / W_e
            x_main = max(cg_full, cg_empty) + h_cg * tb
        x_np = stab.neutral_point(CLa_w, x_ac / mac, Cma_fus, L["tail_eta_h"],
                                  g["ht"].area / g["S"], CLa_h, dah, (x_ac + g["arm"]) / mac) * mac
        x_nose = nose_station * L_f
        return {"x_le": x_le, "x_ac": x_ac, "x_np": x_np, "cg_full": cg_full, "cg_empty": cg_empty,
                "sm_full": (x_np - cg_full) / mac, "sm_empty": (x_np - cg_empty) / mac,
                "items": items, "x_ht": x_ht, "x_vt": x_vt, "x_main": x_main, "x_wing": x_wing,
                "W_empty_items": W_e, "x_nose": x_nose,
                "nose_load": {k: (x_main - cg) / (x_main - x_nose)
                              for k, cg in (("full", cg_full), ("empty", cg_empty))}}

    def placed(nose_station):
        target = 0.5 * (L["static_margin_min"] + L["static_margin_max"])
        lo, hi = 0.05 * L_f, 0.75 * L_f
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            st = state(mid, nose_station)
            lo, hi = (mid, hi) if 0.5 * (st["sm_full"] + st["sm_empty"]) < target else (lo, mid)
        return state(0.5 * (lo + hi), nose_station)

    nose_station = L["station_nose_gear"]
    s = placed(nose_station)
    if max(s["nose_load"].values()) > L["nose_load_max"]:        # move the nose wheel forward
        for _ in range(20):
            cand = max(L["station_nose_gear_min"], nose_station - 0.01)
            if cand == nose_station:
                break
            nose_station = cand
            s = placed(nose_station)
            if max(s["nose_load"].values()) <= L["nose_load_max"]:
                break
    s.update({"dah_da": dah, "Cma_fus": Cma_fus, "CLa_h": CLa_h, "h_cg": h_cg,
              "nose_station": nose_station, "cm_wing": cm_w})
    # track for the overturn limit, and where the main wheels retract
    half = max(overturn_track(s["x_main"], s["x_nose"], cg_, h_cg, L["overturn_max_deg"])
               for cg_ in (s["cg_full"], s["cg_empty"]))           # the more critical CG
    tyre = geo.main_tyre_in(L["main_wheel_load_fraction"] * d["W0"])
    y = min(half, w.span / 2.0)
    chord_y = w.root_chord * (1.0 - (1.0 - w.taper) * y / (w.span / 2.0))
    x_le_root = s["x_le"]                                         # unswept leading edge
    s["gear_track"] = {
        "half_track_ft": half, "fuselage_half_width_ft": g["d_f"] / 2.0,
        "retracts_into": "fuselage" if half <= g["d_f"] / 2.0 else "wing",
        "wing_depth_at_wheel_in": 12.0 * L["wing_t_c"] * chord_y,
        "tyre_diameter_in": tyre["diameter"],
        "wheel_under_wing_chord": x_le_root <= s["x_main"] <= x_le_root + chord_y,
    }
    s["gear_track"]["fits_wing"] = (s["gear_track"]["retracts_into"] == "fuselage"
                                    or (s["gear_track"]["wing_depth_at_wheel_in"] >= tyre["diameter"]
                                        and s["gear_track"]["wheel_under_wing_chord"]))
    # Gate A round 3 ruling: the mains retract into sponsons at the overturn track, so they stow
    s["gear_track"]["retracts_into"] = "sponsons"
    s["gear_track"]["sponson_length_ft"] = g["sponson_length"]
    s["gear_track"]["sponson_depth_ft"] = g["sponson_depth"]
    s["gear_track"]["fits"] = (d["gear_length_in"] / 12.0 <= g["sponson_length"]
                               and tyre["diameter"] / 12.0 <= g["sponson_depth"])
    # propeller clearance: pusher rotated about the main wheel by its rotation angle; tractor with
    # the nose strut compressed (nose-down pitch about the main wheel)
    r = d["D_prop"] / 2.0
    if d["concept"] == "pusher":
        th = math.radians(L["rotation_angle_deg_pusher"])
        hub = ((h_cg + L.get("prop_hub_offset_ft", 0.0)) * math.cos(th)
               - (L_f - s["x_main"]) * math.sin(th))
    else:
        th = math.radians(L["nose_down_deg"])
        hub = h_cg * math.cos(th) - s["x_main"] * math.sin(th)
    s["prop_clearance_in"] = 12.0 * (hub - r)
    # trim: tail lift coefficient from (16.7) without thrust terms, wing moment by (16.16)
    S, S_h = g["S"], g["ht"].area
    alt = isa(L["mission_altitude_ft"])
    x_h = s["x_ac"] + g["arm"]
    den_of = lambda cg: L["tail_eta_h"] * S_h / S * (x_h - cg) / mac

    def cg_at(fuel_left):
        W_e = s["W_empty_items"]
        return (s["cg_empty"] * W_e + fuel_left * s["x_wing"]) / (W_e + fuel_left)

    # thrust-line height above the CG (pusher hub raised by the ledger offset; the CG is taken on
    # the fuselage centreline); the thrust term -T z_t/(q S c) of (16.7), p. 416
    z_t = L.get("prop_hub_offset_ft", 0.0) if d["concept"] == "pusher" else 0.0
    trims = {}
    W_ld = d["W0"] - d["fuel"]
    for seg in d["mission"]:
        name, W_in, W_out, V = seg[0], seg[1], seg[2], seg[3]
        if V <= 0.0:
            continue
        for tag, W in (("start", W_in), ("end", W_out)):
            cg = cg_at(W - W_ld)
            CL = W / (0.5 * alt["rho"] * V ** 2 * S)
            q_ = 0.5 * alt["rho"] * V ** 2
            T = perf.drag(W, S, alt["rho"], V, d["CD0_alt"], d["K"])      # level: thrust = drag
            cm_t = -T * z_t / (q_ * S * mac)                               # (16.7) thrust term
            trims[f"{name}_{tag}"] = {"CL_wing": CL,
                                      "CL_tail": (CL * (cg - s["x_ac"]) / mac + cm_w + cm_t) / den_of(cg)}
    s["trim"] = trims
    s["trim_ok"] = all(abs(t["CL_tail"]) <= L["tail_cl_max_trim"] for t in trims.values())
    # rotation at 0.8 V_TO, most-forward CG, sea level (p. 432-433). Moments about the CG, nose-up
    # positive: wing lift at its a.c., wing moment (16.16), the flap lift increment at its centre of
    # pressure (16.17; 0.44 of the chord for slotted flaps, Fig. 16.9), the main-wheel reaction and
    # its rolling friction (both nose-down: the reaction acts aft of the CG, the friction below it),
    # and the tail. Ground effect is not modelled (stated). A negative tail CL is a download.
    cg = min(s["cg_full"], s["cg_empty"])
    W = d["W0"]
    V_r = 0.8 * 1.1 * perf.stall_speed(d["W_S"], RHO0, d["clmax"]["takeoff"])
    q = 0.5 * RHO0 * V_r ** 2
    dCL_flap = L["takeoff_flap_fraction"] * L["flap_delta_cl_max"] * L["flap_span_fraction"]
    CL_w = L["cl_ground"] + dCL_flap
    x_cp = s["x_le"] + L["flap_cp_fraction"] * mac
    # The main-wheel load is the weight less the total lift, tail included (p. 432-433); the tail
    # download adds to it, so the balance is solved by fixed-point iteration.
    T_r = _thrust_fn(d["bhp"], L, d["D_prop"])(V_r)
    CL_tail = 0.0
    for _ in range(50):
        N_main = max(0.0, W - q * S * CL_w - L["tail_eta_h"] * q * S_h * CL_tail)
        cm = (L["cl_ground"] * (cg - s["x_ac"]) / mac + cm_w + dCL_flap * (cg - x_cp) / mac
              - (N_main * (s["x_main"] - cg) + L["rolling_mu"] * N_main * h_cg) / (q * S * mac)
              - T_r * z_t / (q * S * mac))                         # take-off thrust above the CG
        # tail term -eta (S_h/S) CL_h (x_h - cg)/c balances cm
        new = cm / den_of(cg)
        if abs(new - CL_tail) < 1e-10:
            break
        CL_tail = new
    s["rotation"] = {"V_kt": V_r / KT, "CL_wing": CL_w, "Cm_without_tail": cm,
                     "CL_tail_needed": CL_tail, "main_wheel_load_lb": N_main}
    s["rotation_ok"] = abs(CL_tail) <= L["tail_cl_max_rotation"]
    return s


def ceiling(d, L, power_at=None):
    """Service ceiling: the highest altitude with best rate of climb at least 100 ft/min, by
    bisection, with CD0 evaluated at each altitude (reviewer finding F5). power_at(h_ft) gives the
    shaft hp available; by default the rated bhp times the piston lapse (13.9). Stage 3 passes
    the Mattingly App. K engine instead."""
    W0, S, K, bhp = d["W0"], d["geom"]["S"], d["K"], d["bhp"]
    if power_at is None:
        def power_at(h):
            a = isa(h)
            V = L["climb_speed_over_stall"] * perf.stall_speed(d["W_S"], a["rho"], d["clmax"]["clean"])
            return bhp * _lapse(d.get("engine_model"), h, a, V)
    clean = d["clmax"]["clean"]

    def roc(h):
        a = isa(h)
        lo = L["climb_speed_over_stall"] * perf.stall_speed(d["W_S"], a["rho"], clean)
        V = lo
        for _ in range(3):        # CD0 at the best-climb speed (Gate A round 4, R4-2)
            CD0, _ = _polar(d["geom"], L, V, a, bhp)
            r, V = perf.best_rate_of_climb(W0, S, a["rho"], CD0, K, power_at(h), L["eta_p"],
                                           lo, lo + 400.0)
        return r
    target = L["ceiling_rate_fpm"] / 60.0
    lo, hi = 0.0, 60000.0
    if roc(lo) < target:
        return 0.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if roc(mid) >= target else (lo, mid)
    return lo


def performance(d, L):
    """As-sized performance at take-off weight: stall, take-off and landing distance, sea-level
    climb, service ceiling, maximum level speed at mission altitude (ch. 5, 17)."""
    W0, S, K = d["W0"], d["geom"]["S"], d["K"]
    sl = isa(0.0)
    bhp = d["bhp"]
    to = _takeoff(W0, S, d["CD0_takeoff"], K, d["clmax"]["takeoff"], L, bhp, d["D_prop"])
    ld = perf.landing_distance(W0, S, sl["rho"], d["CD0_landing"], K, d["clmax"]["landing"],
                               mu_brake=L["braking_mu"], free_roll_s=L["free_roll_s"])
    clean = d["clmax"]["clean"]
    v_lo = L["climb_speed_over_stall"] * perf.stall_speed(d["W_S"], sl["rho"], clean)
    vv, v_best = perf.best_rate_of_climb(W0, S, sl["rho"], d["CD0_sl"], K, bhp, L["eta_p"],
                                         v_lo, v_lo + 350.0)
    alt = isa(L["mission_altitude_ft"])
    vmax = perf.max_level_speed(W0, S, alt["rho"], d["CD0_alt"], K,
                                bhp * _lapse(d.get("engine_model"), L["mission_altitude_ft"], alt, 150.0 * KT),
                                L["eta_p"], 120.0, 1200.0)
    return {"V_stall_clean_kt": perf.stall_speed(d["W_S"], sl["rho"], clean) / KT,
            "V_stall_landing_kt": perf.stall_speed(d["W_S"], sl["rho"], d["clmax"]["landing"]) / KT,
            "takeoff_ft": to["total"], "takeoff": to, "landing_ft": ld["total"], "landing": ld,
            "roc_sl_fpm": vv * 60.0, "v_best_climb_kt": v_best / KT,
            "service_ceiling_ft": ceiling(d, L), "vmax_alt_kt": (vmax or 0.0) / KT}


def propeller_points(d, L):
    """Advance ratio and power coefficient (13.10)-(13.11) at sea-level best climb and at the
    mission speeds, for the record; efficiency is the ledger value (Table 3.4), not computed."""
    from conceptual import raymer_propulsion as rp
    n = L["propeller_rpm"] / 60.0
    out = {}
    sl, alt = isa(0.0), isa(L["mission_altitude_ft"])
    m = d.get("engine_model")
    pts = [("climb_sea_level", sl, 1.0, d["mission"][1][1], None)]
    pts += [(r[0], alt, _lapse(m, L["mission_altitude_ft"], alt, r[3]), r[1], r[3])
            for r in d["mission"] if r[3] > 0.0]
    for name, atm, lp, W, V in pts:
        if V is None:
            lo = L["climb_speed_over_stall"] * perf.stall_speed(W / d["geom"]["S"], atm["rho"],
                                                                 d["clmax"]["clean"])
            _, V = perf.best_rate_of_climb(W, d["geom"]["S"], atm["rho"], d["CD0_sl"], d["K"],
                                           d["bhp"], L["eta_p"], lo, lo + 350.0)
            P = d["bhp"]
        else:
            P = perf.power_required_hp(W, d["geom"]["S"], atm["rho"], V, d["CD0_alt"], d["K"]) / L["eta_p"]
        out[name] = {"V_kt": V / KT, "shaft_hp": P, "throttle": P / (d["bhp"] * lp),
                     "J": rp.advance_ratio(V, n, d["D_prop"]),
                     "C_P": rp.power_coefficient(P, atm["rho"], n, d["D_prop"])}
    return out


def size_tail_for_rotation(concept, W_S, A, L, engine=None, max_iter=8):
    """Raymer p. 432-433: rotation can size the elevator and tail. Starting from the Table 6.4
    volume coefficient, enlarge the horizontal tail until the tail lift coefficient needed to
    rotate at 0.8 V_TO with the most-forward CG is within the available value, re-sizing the
    aircraft each time. Returns (design, layout, scale)."""
    scale = 1.0
    for _ in range(max_iter):
        L2 = dict(L, ht_volume_scale=scale)
        d = evaluate(concept, W_S, A, L2, engine=engine)
        lay = layout(d, L2)
        need = abs(lay["rotation"]["CL_tail_needed"])
        if lay["rotation_ok"]:
            return d, lay, scale
        scale *= need / L["tail_cl_max_rotation"] * 1.02
    return d, lay, scale

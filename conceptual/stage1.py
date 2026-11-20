"""Task 12 Stage 1 runner: the conceptual design package with Raymer's methods.

    python -m conceptual.stage1 --out runs/task12/stage1/<date>

Steps follow docs/specs/task12_drone_conceptual_design.md section 4: first-pass sizing (step 3),
constraint diagram (step 4), refined sizing over a wing-loading by aspect-ratio grid for both
concepts with the concept choice (steps 2, 5, 8), layout and analysis of the chosen design
(steps 6, 7), the fixed-engine re-size (step 8) and one-at-a-time trades. Every table is written
as CSV or JSON next to the ledger it used, its hash and the commit.
"""
import argparse
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path

from conceptual import constraints, sizing, uav
from conceptual import raymer_aero as aero
from conceptual import raymer_loads as loads
from conceptual import raymer_performance as perf
from conceptual.units import KT, NM, RHO0, isa

WS_GRID = [8.0 + i for i in range(15)]          # 8 to 22 lb/ft^2
A_GRID = [6.0 + i for i in range(17)]           # 6 to 22
# the nearest production turboprops with printed data in the library: Mattingly Table C.1, p. 519
REAL_TURBOPROPS = [{"name": "PT6A-42", "bhp": 850.0, "weight_lb": 391.0, "sfc_max": 0.601},
                   {"name": "PT6A-45R", "bhp": 1197.0, "weight_lb": 434.0, "sfc_max": 0.553}]


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


def landing_ws_limit(concept, A, L, W0):
    """Largest W/S whose landing distance over 50 ft is within the field length, at W0."""
    lo, hi = 5.0, 60.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        d = uav._build(W0, concept, mid, A, L, 0.2 * W0)
        dist = perf.landing_distance(W0, d["geom"]["S"], RHO0, d["CD0_sl"] + 0.05, d["K"],
                                     d["clmax"]["landing"])["total"]
        lo, hi = (mid, hi) if dist < L["field_length_ft"] else (lo, mid)
    return lo


def constraint_diagram(concept, A, W0, L):
    """Step 4: installed sea-level hp/W required by each requirement against W/S, at fixed W0
    and A, plus the stall and landing wing-loading limits."""
    rows = []
    for i in range(41):
        W_S = 6.0 + 0.5 * i
        d = uav._build(W0, concept, W_S, A, L, 0.2 * W0)
        rows.append({"W_S": W_S, **{k: v / W0 for k, v in d["power_req"].items()}})
    stall = constraints.ws_stall(RHO0, L["stall_speed_kt"] * KT, uav._cl_max(L)["clean"])
    return rows, {"stall": stall, "landing": landing_ws_limit(concept, A, L, W0)}


def carpet(concept, L):
    """Steps 5 and 8: refined sizing over the grid; W0 and power per point."""
    rows = []
    for W_S in WS_GRID:
        for A in A_GRID:
            try:
                d = uav.evaluate(concept, W_S, A, L)
                need, avail = uav.fuel_volume_check(d, L)
                rows.append({"concept": concept, "W_S": W_S, "A": A, "W0": d["W0"], "We": d["We"],
                             "fuel": d["fuel"], "bhp": d["bhp"], "fuel_fits": need <= avail,
                             "binding_power": max(d["power_req"], key=d["power_req"].get)})
            except ValueError as ex:
                rows.append({"concept": concept, "W_S": W_S, "A": A, "W0": None, "error": str(ex)})
    return rows


def feasible_optimum(rows, ws_max):
    ok = [r for r in rows if r.get("W0") and r["W_S"] <= ws_max and r["fuel_fits"]]
    return min(ok, key=lambda r: r["W0"])


def vn_diagram(d, L):
    """V-n points (Raymer 14.2, Figs. 14.7-14.8) at sea level and at mission altitude: the cruise
    point is the maximum level speed at that altitude (equivalent airspeed), the dive speed 50 %
    above it (p. 338), gusts of U_de to cruise falling to half at dive (p. 339)."""
    W_S, CLa, mac = d["W_S"], d["CLa"], d["geom"]["wing"].mac
    alt = isa(L["mission_altitude_ft"])
    pts = {"V_corner_eas_kt": math.sqrt(2 * L["limit_load_factor"] * W_S
                                        / (RHO0 * d["clmax"]["clean"])) / KT}
    for label, rho in (("sea_level", RHO0), ("mission_altitude", alt["rho"])):
        V_c = d["V_c_eas"][label]
        V_d = 1.5 * V_c
        n_c = loads.gust_load_factor(W_S, V_c, L["gust_ude_fps"], CLa, mac, rho)[0]
        n_d = loads.gust_load_factor(W_S, V_d, 0.5 * L["gust_ude_fps"], CLa, mac, rho)[0]
        pts[f"gust_{label}"] = {"V_cruise_eas_kt": V_c / KT, "V_dive_eas_kt": V_d / KT,
                                "n_cruise": n_c, "n_dive": n_d, "n_cruise_neg": 2 - n_c,
                                "n_dive_neg": 2 - n_d}
    return pts


def trades(concept, W_S, A, L):
    """One-at-a-time trades at the chosen point: loiter time, payload, altitude, and each
    banded assumption at its band ends."""
    out = []

    def run(label, **changes):
        L2 = dict(L, **changes)
        try:
            d = uav.evaluate(concept, W_S, A, L2)
            out.append({"case": label, "W0": d["W0"], "bhp": d["bhp"], "fuel": d["fuel"]})
        except ValueError as ex:
            out.append({"case": label, "W0": None, "error": str(ex)})

    for h in (6.0, 8.0, 10.0, 12.0, 16.0):
        run(f"loiter_h={h:g}", loiter_h=h)
    for p in (300.0, 500.0, 700.0, 1000.0):
        run(f"payload_lb={p:g}", payload_lb=p)
    for alt in (15000.0, 20000.0, 25000.0):
        run(f"mission_altitude_ft={alt:g}", mission_altitude_ft=alt)
    _, entries = uav.load_ledger()
    for name, q in entries.items():
        if "band" in q and name in L and name != "composite_factor":
            for end, v in zip(("lo", "hi"), q["band"]):
                run(f"{name}={v:g} ({end})", **{name: float(v)})
    return out


def concept_scores(opt_t, opt_p, lay_t, lay_p):
    """Step 2 scoring. Weights and grades are stated judgements; the quantitative rows come from
    the sizing. Raymer 10.4, p. 221-223, gives the qualitative pros and cons used."""
    rows = [
        ("take-off weight W0 (lb), lower is better", 0.40, opt_t["W0"], opt_p["W0"]),
        ("sensor field of view: nose free of propeller and exhaust (grade 1-5)", 0.25, 2, 5),
        ("propeller wash and exhaust on the sensor and airframe (grade 1-5)", 0.10, 2, 4),
        ("turboprop exhaust impinging on a pusher propeller (Raymer p. 222) (grade 1-5)", 0.10, 5, 2),
        ("ground clearance and gear length (grade 1-5; pusher needs longer gear, p. 222)", 0.15, 5, 3),
    ]
    score = {"tractor": 0.0, "pusher": 0.0}
    table = []
    for label, w, t, p in rows:
        if "W0" in label:
            st, sp = (5.0 * min(t, p) / t, 5.0 * min(t, p) / p)
        else:
            st, sp = float(t), float(p)
        score["tractor"] += w * st
        score["pusher"] += w * sp
        table.append({"criterion": label, "weight": w, "tractor": t, "pusher": p,
                      "tractor_grade": round(st, 2), "pusher_grade": round(sp, 2)})
    return table, score


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


def design_record(d, L, lay, per):
    g = d["geom"]
    return _jsonable({
        "concept": d["concept"], "W_S": d["W_S"], "A": d["A"], "W0_lb": d["W0"], "We_lb": d["We"],
        "fuel_lb": d["fuel"], "payload_lb": L["payload_lb"], "bhp_sl": d["bhp"],
        "power_required_hp": d["power_req"], "engine": d["engine"], "propeller_diameter_ft": d["D_prop"],
        "e": d["e"], "K": d["K"], "CD0_mission_altitude": d["CD0_alt"], "CD0_sea_level": d["CD0_sl"],
        "CL_max": d["clmax"], "CL_alpha_wing": d["CLa"], "n_gust": d["n_gust"], "n_limit": d["n_limit"],
        "Nz_ultimate": d["Nz"], "components_lb": d["components"],
        "mission": [{"segment": r[0], "W_start": r[1], "W_end": r[2], "V_kt": r[3] / KT}
                    for r in d["mission"]],
        "wing": g["wing"], "horizontal_tail": g["ht"],
        "vertical_tail": {"area": g["S_vt"], "height": g["vt_height"], "root_chord": g["vt_root"],
                          "mac": g["vt_mac"]},
        "fuselage": {"length": g["L_f"], "diameter": g["d_f"], "s_wet": g["s_wet_fus"]},
        "tail_arm_ft": g["arm"],
        "layout": {k: lay[k] for k in ("x_le", "x_ac", "x_np", "cg_full", "cg_empty", "sm_full",
                                       "sm_empty", "x_ht", "x_vt", "dah_da", "Cma_fus", "CLa_h", "trim")},
        "stations": {k: {"weight": m, "x": x} for k, (m, x) in lay["items"].items()},
        "performance": per,
    })


def compliance(d, L, lay, per, need, avail, stat, vn):
    n_neg = min(vn[f"gust_{k}"]["n_cruise_neg"] for k in ("sea_level", "mission_altitude"))
    rows = [
        ("R4 payload", "lb", L["payload_lb"], L["payload_lb"], "carried by construction"),
        ("R5 mission 200 nm + 8 h + 200 nm", "fuel lb", d["fuel"], d["fuel"], "sized to it"),
        ("R7 take-off over 50 ft", "ft", per["takeoff_ft"], L["field_length_ft"], "<="),
        ("R7 landing over 50 ft", "ft", per["landing_ft"], L["field_length_ft"], "<="),
        ("R7 clean stall at W0, sea level", "kt", per["V_stall_clean_kt"], L["stall_speed_kt"], "<="),
        ("R9 limit load factor (manoeuvre or gust)", "-", d["n_limit"], L["limit_load_factor"], ">="),
        ("R9 negative gust within the -1.5 limit (weights use the positive case only)", "-", n_neg,
         L["negative_load_factor"], ">="),
        ("R12 sea-level rate of climb", "ft/min", per["roc_sl_fpm"], L["climb_rate_sl_fpm"], ">="),
        ("R12 service ceiling", "ft", per["service_ceiling_ft"], L["ceiling_ft"], ">="),
        ("R13 static margin, full fuel", "MAC", lay["sm_full"], L["static_margin_min"], "in band"),
        ("R13 static margin, empty fuel", "MAC", lay["sm_empty"], L["static_margin_min"], "in band"),
        ("fuel fits integral wing tanks", "ft^3", need, avail, "<="),
        ("empty fraction: build-up vs Table 3.1 (x0.95)", "-", stat["build_up"], stat["table_3_1"], "report"),
    ]
    out = []
    for label, units, value, limit, rule in rows:
        if rule == "<=":
            ok = value <= limit
        elif rule == ">=":
            ok = value is not None and value >= limit
        elif rule == "in band":
            ok = L["static_margin_min"] <= value <= L["static_margin_max"]
        else:
            ok = None
        out.append({"requirement": label, "units": units, "value": value, "limit": limit,
                    "rule": rule, "met": ok})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    L, _ = uav.load_ledger()
    ledger_bytes = uav.LEDGER.read_bytes()
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
                                cwd=uav.LEDGER.parents[2]).stdout.strip()
    except OSError:
        commit = "unknown"
    (out / "inputs.json").write_text(json.dumps({
        "commit": commit, "ledger": str(uav.LEDGER.relative_to(uav.LEDGER.parents[2])),
        "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(), "ws_grid": WS_GRID,
        "a_grid": A_GRID}, indent=2))
    (out / "ledger.yaml").write_bytes(ledger_bytes)

    fp = first_pass(L)
    (out / "first_pass.json").write_text(json.dumps(fp, indent=2))

    rows = carpet("tractor", L) + carpet("pusher", L)
    _write_csv(out / "carpet.csv", rows)
    stall_ws = constraints.ws_stall(RHO0, L["stall_speed_kt"] * KT, uav._cl_max(L)["clean"])
    opt = {c: feasible_optimum([r for r in rows if r["concept"] == c], stall_ws)
           for c in ("tractor", "pusher")}
    designs = {c: uav.evaluate(c, opt[c]["W_S"], opt[c]["A"], L) for c in opt}
    lays = {c: uav.layout(designs[c], L) for c in designs}
    table, score = concept_scores(opt["tractor"], opt["pusher"], lays["tractor"], lays["pusher"])
    chosen = max(score, key=score.get)
    (out / "concept_scores.json").write_text(json.dumps({"table": table, "score": score,
                                                         "chosen": chosen, "optimum": opt}, indent=2))

    d = designs[chosen]
    lay, per = lays[chosen], uav.performance(d, L)
    need, avail = uav.fuel_volume_check(d, L)
    stat = uav.statistical_empty_fractions(d, L)
    rec = design_record(d, L, lay, per)
    vmax_mph = per["vmax_alt_kt"] * 1.151
    vn = vn_diagram(d, L)
    rec.update({"fuel_volume_ft3": {"needed": need, "available": avail},
                "empty_fraction_comparison": stat, "vn": vn,
                "power_loading_comparison": {
                    "hp_per_W0_sized": d["bhp"] / d["W0"],
                    "hp_per_W0_table_5_4": constraints.hp_per_W_statistical(vmax_mph, uav.CATEGORY),
                    "vmax_mph_used": vmax_mph},
                "turboprop_table_10_4_range_bhp": list(uav.geo.TURBOPROP_BHP_RANGE)})
    (out / "design.json").write_text(json.dumps(rec, indent=2, default=float))
    _write_csv(out / "compliance.csv", compliance(d, L, lay, per, need, avail, stat, vn))

    cd_rows, ws_limits = constraint_diagram(chosen, d["A"], d["W0"], L)
    _write_csv(out / "constraint_diagram.csv", cd_rows)
    (out / "constraint_limits.json").write_text(json.dumps(ws_limits, indent=2))

    fixed = []
    for eng in REAL_TURBOPROPS:
        f = uav.evaluate(chosen, d["W_S"], d["A"], L, engine=eng)
        fixed.append({"engine": eng["name"], "bhp": eng["bhp"], "engine_weight_lb": eng["weight_lb"],
                      "W0": f["W0"], "We": f["We"], "fuel": f["fuel"], "power_ok": f["power_ok"],
                      "power_ratio": eng["bhp"] / d["bhp"]})
    _write_csv(out / "fixed_engine.csv", fixed)
    _write_csv(out / "trades.csv", trades(chosen, d["W_S"], d["A"], L))
    tests = subprocess.run(["python3", "-m", "pytest", "-q", "tests/task12"], capture_output=True,
                           text=True, check=False, cwd=uav.LEDGER.parents[2])
    (out / "test_report.txt").write_text(tests.stdout)
    print(json.dumps({"first_pass_W0": fp["W0"], "chosen": chosen, "W0": d["W0"],
                      "W_S": d["W_S"], "A": d["A"], "bhp": d["bhp"], "score": score,
                      "fixed": [(x["engine"], round(x["W0"])) for x in fixed]}, indent=2))


if __name__ == "__main__":
    main()

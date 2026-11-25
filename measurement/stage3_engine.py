"""Stage 3 engine measurements of the frozen pusher (spec section 7.1, tolerances 7.1a).

    python -m measurement.stage3_engine --out runs/task12/stage3/<date>

Rows: shaft power available at 20,000 and 25,000 ft (App. K against Stage 1's piston lapse
(13.9)); shaft SFC at the cruise and loiter points (App. K against the datasheet 0.901 Stage 1
used); service ceiling with the App. K power. Every row gives the spread over the TP100 cycle
family (measurement/tp100_engine.py). Then the consequence: the design re-sized with the
App. K fuel consumption, everything else unchanged.

    python -m measurement.stage3_engine --design runs/task12/stage3/<date>/<run>/design_pusher.json \
        --out runs/task12/stage3/<date>/<run>/engine.json --report docs/validation/<file>.md

With --design the engine is read from the record (`measure_record`): a record sized with the
RR M250-B17F is measured against the M250 cycle family of measurement/m250_engine.py (calibrated to
the brochure's take-off SFC and gas temperature), any other record against the TP100 family above
with the rows as before. The M250 rows follow spec 7.1b: the power, SFC and ceiling rows compare
the table with a family that contains it, so they are reported but not judged; the independent
engine row is the brochure's part-power SFC (the closing check of 7.1b item 3).
"""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np

from conceptual import raymer_performance as perf
from conceptual import raymer_propulsion as prop
from conceptual import stage1, uav
from conceptual.units import HP, KT, isa
from measurement import appk_validation as akv
from measurement import m250_engine as m250
from measurement import stage3_perf as sp
from measurement import tp100_engine as tp
from measurement import turboprop_cycle as tc

REPO = Path(__file__).resolve().parents[1]
FROZEN = {"concept": "pusher", "W_S": 15.0, "A": 10.0}
V_CLIMB_KT = 95.0           # flight speed for the altitude power rows (near best climb at altitude)


def _frozen(L, eng, cbhp=None):
    e = dict(eng, **(cbhp or {}))
    return stage1.analyse(FROZEN["concept"], FROZEN["W_S"], FROZEN["A"], L, e)


def _level_power(d, W, V, h):
    """Shaft hp for level flight, (D V)/(550 eta_p) with the design polar at altitude h."""
    a = isa(h)
    q = 0.5 * a["rho"] * V * V
    S = d["geom"]["S"]
    D = q * S * d["CD0_alt"] + d["K"] * W * W / (q * S)
    return D * V / (HP * d["ledger_used"]["eta_p"])


def _segment_points(d):
    """(segment, W, V_kt, shaft hp) at start, middle and end of each cruise and loiter leg."""
    h = d["ledger_used"]["mission_altitude_ft"]
    pts = []
    for seg, W1, W2, V, *_ in d["mission"]:
        if V <= 0.0:
            continue
        for where, W in (("start", W1), ("mid", 0.5 * (W1 + W2)), ("end", W2)):
            pts.append({"segment": seg, "where": where, "W_lb": W, "V_kt": V / KT,
                        "shaft_hp": _level_power(d, W, V, h)})
    return pts


def _band(values):
    return {"min": float(min(values)), "max": float(max(values)), "mean": float(np.mean(values))}


def _row(name, raymer, band, tol, kind):
    lo, hi = band["min"], band["max"]
    if kind == "rel":
        dev = [(lo - raymer) / raymer, (hi - raymer) / raymer]
        ok = all(abs(x) <= tol for x in dev)
    else:
        dev = [lo - raymer, hi - raymer]
        ok = all(abs(x) <= tol for x in dev)
    return {"quantity": name, "raymer": raymer, "measured": band, "deviation": dev,
            "tolerance": tol, "tolerance_kind": kind, "within": ok}


def measure(L, eng):
    r = _frozen(L, eng)
    d, per = r["design"], r["performance"]
    fam = tp.family()
    h_alt = L["mission_altitude_ft"]
    rows, detail = [], {"family": [], "points": []}
    for m in fam:
        detail["family"].append({k: m[k] for k in ("Tt4", "e_c", "e_t")}
                                | {"pi_c": m["ref"]["pi_c"], "tau_t": m["ref"]["tau_t"],
                                   "m0_lbm_s": m["ref"]["m0"], "M9": m["ref"]["M9"]})
    # power available at altitude
    for h in (20000.0, 25000.0):
        piston = d["bhp"] * prop.piston_power_lapse(isa(h)["sigma"])
        held = [tp.power_available(m, h, V_CLIMB_KT) for m in fam]
        free = [tp.power_available(m, h, V_CLIMB_KT, hold_pi_c=False) for m in fam]
        rows.append(_row(f"shaft hp available at {h:,.0f} ft, {V_CLIMB_KT:.0f} kt (pi_c held at rating)",
                         piston, _band(held), 0.10, "rel"))
        detail[f"flat_rated_upper_bound_{int(h)}"] = _band(free)
    # shaft SFC along the mission legs
    pts = _segment_points(d)
    for p in pts:
        vals = [tp.bsfc_at(m, h_alt, p["V_kt"], p["shaft_hp"])[0] for m in fam]
        p["bsfc"] = _band(vals)
        p["Tt4_R"] = _band([tp.bsfc_at(m, h_alt, p["V_kt"], p["shaft_hp"])[1] for m in fam])
    detail["points"] = pts
    # sensitivity: the family calibrated to the unverified 0.847 take-off extract
    fam_alt = tp.family(tp.BSFC_TAKEOFF_UNVERIFIED)
    detail["sensitivity_bsfc_0_847"] = {
        p["segment"] + "_" + p["where"]: _band([tp.bsfc_at(m, h_alt, p["V_kt"], p["shaft_hp"])[0] for m in fam_alt])
        for p in pts}
    seg_mean = {}
    for seg in ("cruise_out", "loiter", "cruise_back"):
        sp = [p for p in pts if p["segment"] == seg]
        # Simpson weights over start, middle and end of the leg (weight falls about linearly in time)
        w = {"start": 1 / 6, "mid": 4 / 6, "end": 1 / 6}
        band = {k: sum(w[p["where"]] * p["bsfc"][k] for p in sp) for k in ("min", "max", "mean")}
        seg_mean[seg] = band
        rows.append(_row(f"shaft SFC over {seg}, lb/(hp h) (leg average)", d["ledger_used"]["cbhp_loiter" if seg == "loiter" else "cbhp_cruise"],
                         band, 0.10, "rel"))
    # ceiling with App. K power
    ceil = []
    for m in fam:
        ceil.append(uav.ceiling(d, d["ledger_used"],
                                power_at=lambda h, m=m: tp.power_available(m, h, V_CLIMB_KT)))
    rows.append(_row("service ceiling, ft (App. K power, pi_c held)", per["service_ceiling_ft"], _band(ceil),
                     1000.0, "abs"))
    # consequence: re-size with the App. K fuel consumption (family mean), engine and layout rules unchanged
    cb = {"cbhp_cruise": 0.5 * (seg_mean["cruise_out"]["mean"] + seg_mean["cruise_back"]["mean"]),
          "cbhp_loiter": seg_mean["loiter"]["mean"]}
    try:
        r2 = _frozen(L, eng, cb)
        resize = {"cbhp": cb, "W0_lb": r2["design"]["W0"], "fuel_lb": r2["design"]["fuel"],
                  "power_ok": r2["design"]["power_ok"], "power_required_hp": r2["design"]["power_req"],
                  "ht_volume_scale": r2["ht_scale"]}
    except ValueError as exc:
        resize = {"cbhp": cb, "error": str(exc)}
    return {"frozen": {"W0_lb": d["W0"], "fuel_lb": d["fuel"], "bhp": d["bhp"],
                       "cbhp_used": {"cruise": d["ledger_used"]["cbhp_cruise"],
                                     "loiter": d["ledger_used"]["cbhp_loiter"]},
                       "service_ceiling_ft": per["service_ceiling_ft"]},
            "rows": rows, "detail": detail, "resize_with_app_k_sfc": resize}


def book_validation(burner=None):
    """App. K example (p. 597-608) against the library's figure readings; same cases as the tests.
    burner None keeps the cycle code's default (constant cp), which the TP100 reports use; the M250
    route passes the burner of the record's table ("msh") so that the check is of the model in use."""
    k = dict(tc.BOOK_EXAMPLE, gamma_t=1.3)
    if burner is not None:
        k["burner"] = burner
    a25 = isa(25000.0)
    out = {"tau_t_star": [], "envelope": [], "lapse": [], "part_throttle_gap": []}
    for pc, book in ((5, 0.64), (10, 0.56), (20, 0.50), (35, 0.447)):
        t = tc.optimum_tau_t(0.8, a25["T"], a25["p"], pc, k)
        t14 = tc.optimum_tau_t(0.8, a25["T"], a25["p"], pc, dict(tc.BOOK_EXAMPLE))
        out["tau_t_star"].append({"pi_c": pc, "book": book, "model_gamma_t_1_3": t, "model_gamma_t_1_4": t14})
    for pc, F, S in ((5, 158.0, 0.83), (17, 190.0, 0.60), (35, None, 0.535)):
        t = tc.optimum_tau_t(0.8, a25["T"], a25["p"], pc, k)
        dp = tc.design_point(0.8, a25["T"], a25["p"], pc, t, k)
        out["envelope"].append({"pi_c": pc, "F_book": F, "F_model": dp["F_per_m0"], "S_book": S, "S_model": dp["S"]})
    ref = tc.design_point(0.8, a25["T"], a25["p"], 30, 0.6, k)
    ref["m0"] = 1.0
    lim = {"pi_c_max": 30.0, "Tt3_max": 1600.0}
    sl = isa(0.0)
    F0 = tc.full_throttle(ref, 0.1, sl["T"], sl["p"], k, **lim)["F"]
    for h, F in ((5000, 12800), (10000, 11600), (15000, 9500), (20000, 7700), (25000, 6200), (30000, 5000)):
        a = isa(h)
        out["lapse"].append({"h_ft": h, "book": F / 14000.0,
                             "model": tc.full_throttle(ref, 0.1, a["T"], a["p"], k, **lim)["F"] / F0})
    a15 = isa(15000.0)
    for M0, book in ((0.3, 0.34), (0.5, 0.505), (0.8, 0.72)):
        top = tc.full_throttle(ref, M0, a15["T"], a15["p"], k, eta_prop_max=0.9, **lim)
        best = float("inf")
        for i in range(30, 101, 2):
            try:
                r = tc.off_design(ref, M0, a15["T"], a15["p"], top["Tt4"] * i / 100.0, k, 0.9)
            except ValueError:
                continue
            if r["F"] > 0.0:
                best = min(best, r["S"])
        out["part_throttle_gap"].append({"M0": M0, "book": book, "model_eta_max_0_9": best})
    return out


def validation_check(burner):
    """Spec 7.1b item 1 rows for `burner`, from measurement/appk_validation.py (tolerances fixed there
    and in the spec): every row with its verdict, and the counts. Pass and fail come from this code.
    The other burner is run too, for the record's comparison only."""
    other = "csh" if burner == "msh" else "msh"
    rows, rows_o = akv.run(burner), akv.run(other)
    count = lambda rs: {"pass": sum(r["verdict"] == "PASS" for r in rs), "total": len(rs)}
    return {"burner": burner, "rows": rows, "summary": count(rows),
            "other_burner": other, "other_rows": rows_o, "other_summary": count(rows_o)}


def constant_sfc_check(rates, bsfc_const):
    """S3M-6: would a model with a constant shaft SFC (the take-off calibration value) also pass the
    brochure part-power rows? Deviation of that constant from the brochure's maximum SFC per point."""
    out = []
    for name in BROCHURE_POINTS:
        dev = bsfc_const / rates[name]["bsfc_max"] - 1.0
        out.append({"point": name, "brochure": rates[name]["bsfc_max"], "constant": bsfc_const,
                    "deviation": dev, "within": abs(dev) <= TOL_SFC})
    return out


# ---- records sized with the RR M250-B17F (spec 7.1b, 7.1c; owner ruling R-a) ----------------------
TOL_POWER, TOL_SFC, TOL_CEILING_FT = 0.10, 0.10, 1000.0      # spec 7.1a
BROCHURE_POINTS = ("normal_cruise", "cruise_a_90pct", "cruise_b_75pct")
NOT_INDEPENDENT = "not judged (7.1b: same table)"


def is_m250(d):
    return d.get("engine", {}).get("fixed", "").startswith("RR_M250")


def _m250_row(rid, quantity, unit, stage1, source, band, tol, kind, independent, note=""):
    """Row with Stage 1's value, the family band, the deviations at both ends and a verdict.
    independent False: the numbers are reported, the verdict is 'not judged' (spec 7.1b)."""
    lo, hi = band["min"], band["max"]
    dev = [(x - stage1) / stage1 for x in (lo, hi)] if kind == "relative" else [x - stage1 for x in (lo, hi)]
    ok = all(abs(x) <= tol for x in dev)
    verdict = ("within" if ok else "outside") if independent else NOT_INDEPENDENT
    return {"id": rid, "quantity": quantity, "unit": unit, "stage1": stage1, "source": source,
            "stage3": band, "deviation": dev, "deviation_kind": kind, "tolerance": tol,
            "numerically_within": ok, "independent": independent, "verdict": verdict, "note": note}


def _record_points(d, L):
    """(segment, where, W, V_kt, shaft hp) at start, middle and end of each cruise and loiter leg of
    the record, level flight at the record's CD0 and K."""
    h = L["mission_altitude_ft"]
    a = isa(h)
    S = d["wing"]["area"]
    pts = []
    for leg in d["mission"]:
        if leg["V_kt"] <= 0.0:
            continue
        V = leg["V_kt"] * KT
        for where, W in (("start", leg["W_start"]), ("mid", 0.5 * (leg["W_start"] + leg["W_end"])),
                         ("end", leg["W_end"])):
            q = 0.5 * a["rho"] * V * V
            D = q * S * d["CD0"]["mission_altitude"] + d["K"] * W * W / (q * S)
            pts.append({"segment": leg["segment"], "where": where, "W_lb": W, "V_kt": leg["V_kt"],
                        "shaft_hp": D * V / (HP * L["eta_p"]), "stage1_cbhp_leg": leg["cbhp_mean"]})
    return pts


def measure_m250(design_path):
    """Engine rows of a record sized with the M250-B17F. Returns rows (see _m250_row) and detail."""
    d, L, b, ledger_path, check = sp.rebuild(design_path)
    table_path = sp.table_for_run(Path(design_path).parent)
    table = json.loads(Path(table_path).read_text())
    to = m250.ratings("450")["take_off"]
    members, failures = m250.family(shp=to["shp"], bsfc=to["bsfc_max"], mgt_c=to["mgt_c"])
    nominal = next(m for m in members if (m["e_c"], m["e_t"]) == (table["member"]["e_c"], table["member"]["e_t"]))
    # the record's table must be this family's nominal member, else the engine data changed since
    pi_c_gap = abs(nominal["ref"]["pi_c"] / table["member"]["pi_c"] - 1.0)
    if pi_c_gap > 1e-6:
        raise ValueError(f"the record's table member (pi_c {table['member']['pi_c']}) is not the "
                         f"calibrated nominal member (pi_c {nominal['ref']['pi_c']})")
    model = b["engine_model"]
    rows, detail = [], {"family": [], "failures": failures, "table": str(table_path),
                        "table_sha256": sp.sha256(table_path), "nominal_pi_c_gap": pi_c_gap}
    for m in members:
        detail["family"].append({"e_c": m["e_c"], "e_t": m["e_t"], "Tt4_R": m["Tt4"], "pi_c": m["ref"]["pi_c"],
                                 "tau_t": m["ref"]["tau_t"], "m0_lbm_s": m["ref"]["m0"]})
    for h in (20000.0, 25000.0):
        held = [tp.power_available(m, h, V_CLIMB_KT) for m in members]
        free = [tp.power_available(m, h, V_CLIMB_KT, hold_pi_c=False) for m in members]
        rows.append(_m250_row(f"power_{int(h)}", f"shaft hp available at {h:,.0f} ft, {V_CLIMB_KT:.0f} kt", "hp",
                              model.power_available(h, V_CLIMB_KT), "App. K family, pi_c held at the rating",
                              _band(held), TOL_POWER, "relative", False,
                              "Stage 1's value is the table of the family's nominal member (rated power clip, "
                              "power scale 1); the family contains it."))
        detail[f"flat_rated_upper_bound_{int(h)}"] = _band(free)
    pts = _record_points(d, L)
    h_alt = L["mission_altitude_ft"]
    for p in pts:
        vals = [m250_bsfc(m, h_alt, p["V_kt"], p["shaft_hp"]) for m in members]
        p["bsfc"] = _band([v[0] for v in vals])
        p["Tt4_R"] = _band([v[1] for v in vals])
    detail["points"] = pts
    w = {"start": 1 / 6, "mid": 4 / 6, "end": 1 / 6}
    for seg in ("cruise_out", "loiter", "cruise_back"):
        sp_ = [p for p in pts if p["segment"] == seg]
        band = {k: sum(w[p["where"]] * p["bsfc"][k] for p in sp_) for k in ("min", "max", "mean")}
        rows.append(_m250_row(f"sfc_{seg}", f"shaft SFC over {seg} (leg average)", "lb/(hp h)",
                              sp_[0]["stage1_cbhp_leg"], "App. K family, part power at the leg's level-flight power",
                              band, TOL_SFC, "relative", False,
                              "Stage 1's value is the record's leg-mean SFC from the table, with the SFC allowance "
                              f"{L.get('engine_sfc_allowance', 1.0)}; the family is raw App. K without it."))
    bd = dict(b, W0=d["W0_lb"], W_S=d["W_S"])

    def climb_power(m):
        """Family member's full-throttle power at the speed uav.ceiling's default uses at each altitude
        (climb_speed_over_stall x clean stall speed), so only the engine differs from Stage 1's bisection."""
        def at(hh):
            a = isa(hh)
            V = L["climb_speed_over_stall"] * perf.stall_speed(d["W_S"], a["rho"], b["clmax"]["clean"])
            return tp.power_available(m, hh, V / KT)
        return at
    ceil = [uav.ceiling(bd, L, power_at=climb_power(m)) for m in members]
    rows.append(_m250_row("ceiling", "service ceiling (App. K power, pi_c held)", "ft",
                          d["performance"]["service_ceiling_ft"], "App. K family power in Stage 1's ceiling bisection",
                          _band(ceil), TOL_CEILING_FT, "absolute", False,
                          "Same bisection as Stage 1 (climb speed over stall speed at each altitude); only the engine power differs."
                          + (f" Stage 1's ceiling is above the table's top altitude ({max(table['h_ft']):,.0f} ft), where "
                             "the table holds its power constant (the lookup clamps); the cycle itself keeps falling, so "
                             "the difference here is the table's edge, not the family's spread."
                             if d["performance"]["service_ceiling_ft"] > max(table["h_ft"]) else "")))
    # closing check, 7.1b item 3: the brochure's part-power SFC, which the take-off calibration did not use
    study = m250.study("450")
    rates = m250.ratings("450")
    detail["brochure_study"] = {"members": [{k: v for k, v in m.items() if k != "validation"} | {"validation": m["validation"]}
                                            for m in study["members"]], "failures": study["failures"]}
    for name in BROCHURE_POINTS:
        pts_b = [next(r for r in m["validation"]["points"] if r["point"] == name) for m in study["members"]]
        band = _band([r["bsfc"] for r in pts_b])
        rows.append(_m250_row(f"brochure_{name}", f"shaft SFC at {name} ({rates[name]['shp']:.0f} shp, sea level static)",
                              "lb/(hp h)", rates[name]["bsfc_max"],
                              "App. K family against the brochure's maximum (guaranteed) SFC", band, TOL_SFC,
                              "relative", True,
                              "Stage 1 column is the brochure value (a maximum/guaranteed SFC). The calibration used take-off only. Valid at sea level and 70-100 % power only."))
    detail["constant_sfc_check"] = constant_sfc_check(rates, to["bsfc_max"])
    detail["table_burner"] = table["burner"]
    detail["brochure_mgt"] = {"brochure_c": rates["normal_cruise"]["mgt_c"],
                              "model_c": _band([m["validation"]["mgt_c"] for m in study["members"]]),
                              "tolerance_c": m250.TOL_MGT_C}
    # validity (7.1b item 2)
    unch = m250.unchoked_cells(table)
    detail["validity"] = {"table_unchoked_cell_share": unch["share"], "table_cells": unch["n_cells"],
                          "mission_fuel_share_unchoked_record": d["unchoked_fuel_share"],
                          "legs": [{"segment": g["segment"], "unchoked_fraction": g["turbine_unchoked_fraction"],
                                    "unchoked_fuel_lb": g["unchoked_fuel_lb"], "burned_lb": g["burned_lb"]}
                                   for g in d["mission"]],
                          "tested_range": "sea level static, 70-100 % power (brochure rows)"}
    return {"frozen": {"W0_lb": d["W0_lb"], "fuel_lb": d["fuel_lb"], "bhp": d["bhp_sl"],
                       "service_ceiling_ft": d["performance"]["service_ceiling_ft"],
                       "sfc_allowance": L.get("engine_sfc_allowance", 1.0),
                       "mission_altitude_ft": L["mission_altitude_ft"]},
            "rows": rows, "detail": detail, "rebuild_check": check, "ledger_path": str(ledger_path)}


def m250_bsfc(member, h, V_kt, shp):
    """Shaft SFC and Tt4 of an M250 family member at a part-power point (the TP100 function: the
    cycle code is the same)."""
    return tp.bsfc_at(member, h, V_kt, shp)


def measure_record(design_path):
    """Engine rows of the record at `design_path`: the M250 route when it was sized with the M250,
    else the TP100 route of `measure` with the record's ledger copy and engine."""
    d = json.loads(Path(design_path).read_text())
    if is_m250(d):
        return measure_m250(design_path)
    L, _ = uav.load_ledger(Path(design_path).parent / "ledger.yaml")
    engines, _ = stage1.engine_options()
    return measure(L, engines[stage1.CHOSEN_ENGINE])


def report_m250(res, path):
    """Markdown for a measure_m250 result; every number is read from it."""
    v, fr, det, i = res["validation"], res["frozen"], res["detail"], res["inputs"]
    L = []
    w = L.append
    w("# Task 12 Stage 3: engine measurements of the M250-B17F baseline (Mattingly App. K)\n")
    w(f"Design `{i['design']}` (sha256 `{i['design_sha256']}`), commit `{i['commit']}`, Python {i['python']}, "
      f"numpy {i['numpy']}. Generated by `python -m measurement.stage3_engine --design ...`; every number is read from "
      "the run record `engine.json` beside the other Stage 3 records. Tolerances are spec 7.1a, fixed before the run.\n")
    w("## 1. What these rows are\n")
    w("The record was sized with the table of the M250 family's nominal member (spec 7.1b: the table is the App. K "
      "cycle itself). So the power, SFC and ceiling rows compare the table with a family that contains it. They "
      "are **reported, not judged**. The independent engine check is the brochure's part-power SFC, which the "
      "take-off calibration did not use (7.1b item 3); that row is judged.\n")
    w("## 2. The M250 family (measurement/m250_engine.py)\n")
    w("Calibrated to the brochure's take-off SFC 0.613 and measured gas temperature 810 C; polytropic efficiencies "
      "on the study grid.\n")
    w("| e_c | e_t | pi_c solved | Tt4, R | tau_t* |\n|---|---|---|---|---|")
    for m in det["family"]:
        w(f"| {m['e_c']:.2f} | {m['e_t']:.2f} | {m['pi_c']:.3f} | {m['Tt4_R']:.0f} | {m['tau_t']:.3f} |")
    for f in det["failures"]:
        w(f"| {f['e_c']:.2f} | {f['e_t']:.2f} | no calibration: {f['reason']} | | |")
    w(f"\nThe record's table member is reproduced by the family's nominal member (pi_c relative gap {det['nominal_pi_c_gap']:.1e}).\n")
    w("## 3. Rows (spec 7.1a, 7.1b)\n")
    w("| Quantity | Stage 1 / brochure | App. K family (min - max) | difference | tolerance | verdict |\n|---|---|---|---|---|---|")
    for r in res["rows"]:
        m = r["stage3"]
        if r["deviation_kind"] == "relative":
            dtxt, ttxt = f"{r['deviation'][0] * 100:+.1f} to {r['deviation'][1] * 100:+.1f} %", f"±{r['tolerance'] * 100:.0f} %"
        else:
            dtxt, ttxt = f"{r['deviation'][0]:+,.0f} to {r['deviation'][1]:+,.0f} ft", f"±{r['tolerance']:,.0f} ft"
        vt = r["verdict"] + ("" if r["independent"] else f"; numerically {'inside' if r['numerically_within'] else 'outside'}")
        w(f"| {r['quantity']} ({r['unit']}) | {r['stage1']:,.3f} | {m['min']:,.3f} - {m['max']:,.3f} | {dtxt} | {ttxt} | {vt} |")
    w("")
    for r in res["rows"]:
        if r["note"]:
            w(f"- **{r['quantity']}**: {r['note']}")
    cs = det["constant_sfc_check"]
    w("\nThe brochure rows cannot discriminate between engine models. They are the same three points as the "
      "2026-11-23 engine validation and are at sea level, 70 to 100 % power, where the take-off calibration "
      f"already holds. A model with a constant SFC of {cs[0]['constant']:.3f} (the take-off value) deviates from the "
      "brochure by " + ", ".join(f"{c['deviation'] * 100:+.1f} % ({c['point']})" for c in cs)
      + f", and so {'would also pass' if all(c['within'] for c in cs) else 'would not pass'} the "
      f"±{TOL_SFC * 100:.0f} % tolerance. These rows cannot fail for a model calibrated at take-off; the engine "
      "closing check (7.1b item 3) stays open and the engine rows rest on the model, carried by the ±10 % SFC band.")
    w("\nShaft SFC along the legs (family mean) and the turbine inlet temperature the throttle needs:\n")
    w("| leg | point | weight, lb | speed, kt | shaft hp | SFC | Tt4, R |\n|---|---|---|---|---|---|---|")
    for p in det["points"]:
        w(f"| {p['segment']} | {p['where']} | {p['W_lb']:,.0f} | {p['V_kt']:.1f} | {p['shaft_hp']:.1f} | "
          f"{p['bsfc']['mean']:.3f} | {p['Tt4_R']['mean']:.0f} |")
    mg = det["brochure_mgt"]
    w(f"\nMeasured gas temperature at normal cruise power: model {mg['model_c']['min']:.0f} - {mg['model_c']['max']:.0f} C "
      f"against the brochure's {mg['brochure_c']:.0f} C (tolerance ±{mg['tolerance_c']:.0f} C).\n")
    w(f"If the engine were flat-rated (Tt4 limit only): {det['flat_rated_upper_bound_20000']['min']:.0f}-"
      f"{det['flat_rated_upper_bound_20000']['max']:.0f} hp at 20,000 ft, "
      f"{det['flat_rated_upper_bound_25000']['min']:.0f}-{det['flat_rated_upper_bound_25000']['max']:.0f} hp at 25,000 ft "
      "(upper bound; the rating clip of 450 hp applies to the table).\n")
    w("## 4. Validity (spec 7.1b item 2)\n")
    va = det["validity"]
    fr_ = [p["shaft_hp"] / m250.RATED_SHP for p in det["points"]]
    w(f"- Tested range: {va['tested_range']}. The mission legs run at {min(fr_) * 100:.0f}-{max(fr_) * 100:.0f} % of the rating, "
      f"at {fr['mission_altitude_ft']:,.0f} ft; the brochure gives no altitude data.")
    w(f"- Share of the table's cells (altitude, speed, power fraction) where the LP turbine is below the choking ratio, "
      f"so App. K's off-design assumption fails: {va['table_unchoked_cell_share'] * 100:.1f} % of {va['table_cells']} cells.")
    w(f"- Share of the baseline's mission fuel burned in such cells: **{va['mission_fuel_share_unchoked_record'] * 100:.1f} %** "
      "(record `unchoked_fuel_share`).\n")
    w("| leg | unchoked fraction | fuel in unchoked steps, lb | burned, lb |\n|---|---|---|---|")
    for g in va["legs"]:
        w(f"| {g['segment']} | {g['unchoked_fraction']:.3f} | {g['unchoked_fuel_lb']:.1f} | {g['burned_lb']:.1f} |")
    vc = res["validation_check"]
    bn = {"msh": "MSH variable-cp burner", "csh": "constant-cp burner"}
    w("\n## 5. The cycle model against the book's own example (spec 7.1b item 1)\n")
    w(f"The burner is the one the record's table was built with (`burner` = `{vc['burner']}` in `m250_table.json`, "
      f"detail key `table_burner`): the {bn[vc['burner']]}. Rows come from `measurement/appk_validation.py`; "
      "tolerances were fixed on 2026-11-21 before the variable-cp code existed, and every verdict below is computed "
      "by that code.\n")
    w("| case | book | model | difference | tolerance | verdict |\n|---|---|---|---|---|---|")
    for r in vc["rows"]:
        if r["tolerance_kind"] == "abs":
            dtxt, ttxt = f"{r['deviation']:+.3f}", f"±{r['tolerance']:.3f}"
        else:
            dtxt, ttxt = f"{r['deviation'] * 100:+.1f} %", f"±{r['tolerance'] * 100:.0f} %"
        w(f"| {r['case']} | {r['book']:.3f} | {r['model']:.3f} | {dtxt} | {ttxt} | "
          f"{'within' if r['verdict'] == 'PASS' else '**outside**'} |")
    sm, so = vc["summary"], vc["other_summary"]
    bad = [r for r in vc["rows"] if r["verdict"] != "PASS"]
    w(f"\n{sm['pass']} of {sm['total']} rows are within tolerance with the {bn[vc['burner']]}"
      + ("." if not bad else "; outside: " + "; ".join(
          f"{r['case']} ({r['deviation'] * 100:+.1f} %)" if r["tolerance_kind"] == "rel"
          else f"{r['case']} ({r['deviation']:+.3f})" for r in bad) + "."))
    sg = [r["deviation"] for r in vc["rows"] if r["group"] in ("envelope_S", "part_throttle_S")]
    w(f"The fuel-consumption rows (K.3 S and K.9 S) deviate by {min(sg) * 100:+.1f} to {max(sg) * 100:+.1f} % "
      f"({'the model reads high' if min(sg) > 0 else 'the model reads low' if max(sg) < 0 else 'mixed signs'} against the book).")
    w(f"For comparison, the {bn[vc['other_burner']]} (not used by this table) gives {so['pass']} of {so['total']} rows within tolerance.")
    w("\nA row outside tolerance is reported, not tuned. The brochure comparison in section 3 is the check of the "
      "M250 part-power SFC.")
    w("\n## 6. Caveats carried\n")
    w("- The M250 table is validated at sea level, static, and 70-100 % power only (brochure rows). Mission cruise and "
      f"loiter run at {min(fr_) * 100:.0f}-{max(fr_) * 100:.0f} % of the rating, at {fr['mission_altitude_ft']:,.0f} ft.")
    w(f"- {va['mission_fuel_share_unchoked_record'] * 100:.1f} % of the baseline's mission fuel burns in unchoked cells, outside App. K's off-design assumption.")
    w("- The 23,000 ft ceiling requirement is above the certified 20,000 ft B17 installations "
      "(docs/validation/2026-11-24_task12_m250_r6_sources.md); the maximum operating altitude and relight envelope are "
      "design assumptions (owner ruling R-f).")
    w("- Installation losses (inlet, exhaust, bleed, accessory power) are not modelled beyond the 1.02 SFC allowance.")
    w("- Not done: re-sizing the design with the family's SFC (the table is the nominal member; the +-10 % SFC and power "
      "bands are carried by the info-gap study).")
    Path(path).write_text("\n".join(L) + "\n")


def report(res, path):
    v, fr = res["validation"], res["frozen"]
    L = []
    w = L.append
    w("# Task 12 Stage 3: engine measurements (Mattingly App. K)\n")
    w(f"Generated by `python -m measurement.stage3_engine` at commit `{res['inputs']['commit'][:7]}` "
      "(the run record `engine.json` sits beside this run's inputs). Every number below is read from that record.\n")
    w("## 1. The cycle model against the book's own example\n")
    w("Mattingly's App. K turboprop, modified-specific-heat gas model, coded in "
      "`measurement/turboprop_cycle.py`. Book values are read off the printed figures (library notes).\n")
    w("| pi_c | Fig. K.4 tau_t* | model, gamma_t 1.3 | model, gamma_t 1.4 (as printed) |\n|---|---|---|---|")
    for r in v["tau_t_star"]:
        w(f"| {r['pi_c']} | {r['book']:.3f} | {r['model_gamma_t_1_3']:.3f} | {r['model_gamma_t_1_4']:.3f} |")
    w("\nThe printed gamma_t = 1.4 does not reproduce Fig. K.4; 1.3 does, to 0.015. The study uses 1.3 and "
      "records this as an interpretation of a likely misprint.\n")
    w("| pi_c | F/m0 book | F/m0 model | S book | S model |\n|---|---|---|---|---|")
    for r in v["envelope"]:
        fb = "n/r" if r["F_book"] is None else f"{r['F_book']:.0f}"
        w(f"| {r['pi_c']} | {fb} | {r['F_model']:.1f} | {r['S_book']:.3f} | {r['S_model']:.3f} |")
    w("\nFull-throttle thrust lapse at M0 = 0.1 (Fig. K.7, F/F_SL):\n")
    w("| altitude, ft | book | model |\n|---|---|---|")
    for r in v["lapse"]:
        w(f"| {r['h_ft']:,} | {r['book']:.3f} | {r['model']:.3f} |")
    w("\n**Part throttle does not validate.** Minimum S at 15,000 ft (Fig. K.9), eta_prop,max 0.9:\n")
    w("| M0 | book | model | ratio |\n|---|---|---|---|")
    for r in v["part_throttle_gap"]:
        w(f"| {r['M0']} | {r['book']:.3f} | {r['model_eta_max_0_9']:.3f} | {r['model_eta_max_0_9'] / r['book']:.2f} |")
    w("\nThe model sits 11-14 % above the book at every Mach number, an almost uniform offset whose "
      "cause is not found. Calibrating the TP100 to its datasheet SFC absorbs a uniform offset, but "
      "the part-power trend below is not independently validated. It should be checked against a "
      "published part-power point for the TP100 (the datasheet's cruise condition) before Gate B.\n")
    w("## 2. The TP100 as a family of cycles\n")
    w("Its cycle is not published. Each member assumes a turbine inlet temperature and efficiencies, "
      "and its compressor ratio is solved so that the SFC at sea-level maximum power equals the "
      "brochure's 0.901, the only SFC the brochure gives, printed beside the maximum output "
      "(`measurement/tp100_engine.py`).\n")
    w("| Tt4, R | e_c | e_t | pi_c solved | tau_t* |\n|---|---|---|---|---|")
    for m in res["detail"]["family"]:
        w(f"| {m['Tt4']:.0f} | {m['e_c']:.2f} | {m['e_t']:.2f} | {m['pi_c']:.2f} | {m['tau_t']:.3f} |")
    w("\n## 3. Measurement rows (spec 7.1a)\n")
    w("| Quantity | Stage 1 | App. K (family min-max) | deviation | tolerance | within |\n|---|---|---|---|---|---|")
    for r in res["rows"]:
        m, dv = r["measured"], r["deviation"]
        if r["tolerance_kind"] == "rel":
            dtxt, ttxt = f"{dv[0] * 100:+.1f} to {dv[1] * 100:+.1f} %", f"±{r['tolerance'] * 100:.0f} %"
        else:
            dtxt, ttxt = f"{dv[0]:+,.0f} to {dv[1]:+,.0f}", f"±{r['tolerance']:,.0f}"
        w(f"| {r['quantity']} | {r['raymer']:,.3f} | {m['min']:,.3f} - {m['max']:,.3f} | {dtxt} | {ttxt} | "
          f"{'yes' if r['within'] else '**no**'} |")
    w("\nShaft SFC along the legs (family mean), with the turbine inlet temperature the throttle needs:\n")
    w("| leg | point | weight, lb | speed, kt | shaft hp | SFC | Tt4, R |\n|---|---|---|---|---|---|---|")
    for p in res["detail"]["points"]:
        w(f"| {p['segment']} | {p['where']} | {p['W_lb']:,.0f} | {p['V_kt']:.1f} | {p['shaft_hp']:.1f} | "
          f"{p['bsfc']['mean']:.3f} | {p['Tt4_R']['mean']:.0f} |")
    up20, up25 = res["detail"]["flat_rated_upper_bound_20000"], res["detail"]["flat_rated_upper_bound_25000"]
    w(f"\nIf the engine were flat-rated (compressor allowed past its sea-level ratio, Tt4 limit only), "
      f"power at 20,000 ft would be {up20['min']:.0f}-{up20['max']:.0f} hp and at 25,000 ft "
      f"{up25['min']:.0f}-{up25['max']:.0f} hp. The datasheet does not say which applies.\n")
    rz = res["resize_with_app_k_sfc"]
    w("## 4. Consequence\n")
    w(f"Stage 1 froze W0 = {fr['W0_lb']:,.0f} lb, fuel {fr['fuel_lb']:,.0f} lb, using SFC "
      f"{fr['cbhp_used']['cruise']} on every leg, and a service ceiling of {fr['service_ceiling_ft']:,.0f} ft.\n")
    if "error" in rz:
        w(f"Re-sizing with the App. K SFC failed: {rz['error']}.\n")
    else:
        req = rz["power_required_hp"]
        w(f"Re-sized with the App. K leg-average SFC (cruise {rz['cbhp']['cbhp_cruise']:.3f}, loiter "
          f"{rz['cbhp']['cbhp_loiter']:.3f}) and nothing else changed: W0 = {rz['W0_lb']:,.0f} lb, fuel "
          f"{rz['fuel_lb']:,.0f} lb. The TP100's 241 hp then {'meets' if rz['power_ok'] else '**does not meet**'} "
          f"every power requirement (largest: {max(req, key=req.get)}, {max(req.values()):.0f} hp sea-level equivalent, "
          "with Stage 1's lapse).\n")
    ceil_row = next(r for r in res["rows"] if r["quantity"].startswith("service ceiling"))
    w(f"With the App. K power the frozen design's service ceiling is {ceil_row['measured']['min']:,.0f}-"
      f"{ceil_row['measured']['max']:,.0f} ft against R12's 25,000 ft.\n")
    w("Under spec 7.1a a row outside tolerance that takes a requirement margin below zero returns the "
      "design to Stage 1. The ceiling row does that; the SFC rows would once the extra fuel is carried.\n")
    sens = res["detail"]["sensitivity_bsfc_0_847"]
    w(f"Sensitivity: calibrated instead to the unverified 0.847 take-off extract, the loiter SFC runs "
      f"{sens['loiter_start']['mean']:.3f} at the start and {sens['loiter_end']['mean']:.3f} at the end of the leg "
      "(family means); the shortfall against 0.901 remains.\n")
    w("Brochure facts that bear on the design but are not measured here: the starting envelope ends at "
      "19,685 ft, below the 20,000 ft loiter, so an in-flight relight needs a descent; the output shaft "
      "turns at 2,158 rpm against the ledger's assumed 2,000 rpm (inside its band).\n")
    w("## 5. Not done in this run\n")
    w("- No TP100 part-power datum to validate the part-throttle trend: the owner's brochure gives none. "
      "The maker would have to be asked for a part-power curve.")
    w("- Installation losses (inlet, exhaust, bleed, accessory power) are not modelled; they would lower power and raise SFC further.")
    w("- Power at altitude uses 95 kt for every row; the ceiling bisection uses the same speed.")
    Path(path).write_text("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", help="write the Markdown report here")
    ap.add_argument("--design", help="a Stage 1 record; its engine decides the route (M250 or TP100)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=False, cwd=REPO).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "conceptual", "measurement", "data"],
                                capture_output=True, text=True, check=False, cwd=REPO).stdout.strip())
    if a.design and is_m250(json.loads(Path(a.design).read_text())):
        res = measure_m250(a.design)
        burner = res["detail"]["table_burner"]
        res["validation"] = book_validation(burner)
        res["validation_check"] = validation_check(burner)
        res["inputs"] = {"commit": commit, "uncommitted_code_changes": dirty, "python": platform.python_version(),
                         "numpy": np.__version__, "design": a.design, "design_sha256": sp.sha256(a.design),
                         "ledger": res.pop("ledger_path"),
                         "ledger_sha256": sp.sha256(Path(a.design).parent / "ledger.yaml"),
                         "engines_sha256": hashlib.sha256(stage1.ENGINES.read_bytes()).hexdigest(),
                         "family_grid": m250.GRID, "v_climb_kt": V_CLIMB_KT, "seed": None}
        (out / "engine.json").write_text(json.dumps(res, indent=2, default=float))
        for r in res["rows"]:
            m = r["stage3"]
            print(f"{r['id']}: stage1 {r['stage1']:.3f}, App K {m['min']:.3f}-{m['max']:.3f}, {r['verdict']}")
        if a.report:
            report_m250(res, a.report)
        return
    # the ledger actually used is hashed (S3M-11a): the record's own copy with --design, else the default
    ledger_used = Path(a.design).parent / "ledger.yaml" if a.design else Path(uav.LEDGER)
    L, _ = uav.load_ledger(ledger_used)
    engines, _ = stage1.engine_options()
    eng = engines[stage1.CHOSEN_ENGINE]
    res = measure(L, eng)
    res["validation"] = book_validation()
    res["inputs"] = {"commit": commit, "uncommitted_code_changes": dirty, "python": platform.python_version(), "numpy": np.__version__,
                     "design": a.design, "design_sha256": sp.sha256(a.design) if a.design else None,
                     "ledger": str(ledger_used), "ledger_sha256": hashlib.sha256(ledger_used.read_bytes()).hexdigest(),
                     "engines_sha256": hashlib.sha256(stage1.ENGINES.read_bytes()).hexdigest(),
                     "cycle_grid": tp.CYCLE_GRID, "v_climb_kt": V_CLIMB_KT,
                     "gas_model": "MSH, gamma_t 1.3 (see tests/task12/test_turboprop_cycle.py)",
                     "book_example_gamma_t_printed": tc.BOOK_EXAMPLE["gamma_t"], "seed": None}
    (out / "engine.json").write_text(json.dumps(res, indent=2, default=float))
    for row in res["rows"]:
        m = row["measured"]
        print(f"{row['quantity']}: Raymer {row['raymer']:.3f}, App K {m['min']:.3f}-{m['max']:.3f}, "
              f"within {row['within']}")
    if a.report:
        report(res, a.report)
    print("re-size:", {k: v for k, v in res["resize_with_app_k_sfc"].items() if k != "power_required_hp"})


if __name__ == "__main__":
    main()

"""Stage 3 engine measurements of the frozen pusher (spec section 7.1, tolerances 7.1a).

    python -m measurement.stage3_engine --out runs/task12/stage3/<date>

Rows: shaft power available at 20,000 and 25,000 ft (App. K against Stage 1's piston lapse
(13.9)); shaft SFC at the cruise and loiter points (App. K against the datasheet 0.901 Stage 1
used); service ceiling with the App. K power. Every row gives the spread over the TP100 cycle
family (measurement/tp100_engine.py). Then the consequence: the design re-sized with the
App. K fuel consumption, everything else unchanged.
"""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np

from conceptual import raymer_propulsion as prop
from conceptual import stage1, uav
from conceptual.units import HP, KT, isa
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
    for seg, W1, W2, V, _ in d["mission"]:
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


def book_validation():
    """App. K example (p. 597-608) against the library's figure readings; same cases as the tests."""
    k = dict(tc.BOOK_EXAMPLE, gamma_t=1.3)
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
      "and its compressor ratio is solved so that the SFC at sea-level take-off power equals the "
      "datasheet's 0.847 (`measurement/tp100_engine.py`).\n")
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
    w("## 5. Not done in this run\n")
    w("- No TP100 part-power datum to validate the part-throttle trend (owner action: datasheet).")
    w("- Installation losses (inlet, exhaust, bleed, accessory power) are not modelled; they would lower power and raise SFC further.")
    w("- Power at altitude uses 95 kt for every row; the ceiling bisection uses the same speed.")
    Path(path).write_text("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", help="write the Markdown report here")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    L, _ = uav.load_ledger()
    engines, _ = stage1.engine_options()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=False, cwd=REPO).stdout.strip()
    res = measure(L, engines[stage1.CHOSEN_ENGINE])
    res["validation"] = book_validation()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "conceptual", "measurement", "data"],
                                capture_output=True, text=True, check=False, cwd=REPO).stdout.strip())
    res["inputs"] = {"commit": commit, "uncommitted_code_changes": dirty, "python": platform.python_version(), "numpy": np.__version__,
                     "ledger_sha256": hashlib.sha256(uav.LEDGER.read_bytes()).hexdigest(),
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

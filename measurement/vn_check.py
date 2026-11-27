"""V-n check of a Task 12 design record (owner ruling B-4, 2026-11-26), with Stage 1's own loads code.

Gust load factors (conceptual/raymer_loads.py, Raymer (14.4)-(14.8)) and the manoeuvre load factor
(aerodynamic limit q CL_max/(W/S), capped at the structural limit) at V_C, V_D and the level top speed, at
sea level and at the mission altitude, at take-off weight and at zero-fuel weight. The design is rebuilt
from its record (measurement/stage3_perf.rebuild, which raises if the rebuild does not reproduce the
record). Nothing is re-sized.

    python -m measurement.vn_check --design runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json \
        --out runs/task12/stage3/2026-11-26/vn_check/vn.json --report docs/validation/2026-11-26_task12_vn_check.md

Two lift-curve slopes are reported, because the record holds two gust values for the same point:
  "vn_record": the slope at the record's CLa (cruise Mach of the sizing), used for the record's `vn` entries;
  "sizing":    the slope at the Mach number of the speed itself, used for the record's `gusts` entries
               (the value the structure was sized with, Gate A round 4 re-check RC-6).
Speeds above V_C use the design gust velocity of raymer_loads.design_gust_velocity (30 ft/s at V_C falling
linearly to 15 ft/s at V_D, and 15 ft/s beyond V_D). Negative gust load factor is 2 - n, as in Stage 1.
"n_gust_sizing_full_ude_sensitivity" is the same with U_de held at its V_C value at every speed: a
sensitivity the Raymer rule does not call for, shown because the Stage 3 review (GB-3) scaled the gust that way.
Negative manoeuvre loads are not computed: the record has no negative CL_max.
"""
import argparse
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

from conceptual import raymer_aero as aero
from conceptual import raymer_loads as loads
from conceptual.units import KT, RHO0, isa
from measurement import stage3_perf as sp

REPO = Path(__file__).resolve().parents[1]


def lift_slope_at(b, A, L, M):
    """The lift slope as uav._build computes it for the gust (same call, Mach M)."""
    g = b["geom"]
    return aero.lift_slope(A, M, L["airfoil_efficiency"], 0.0, g["s_exposed"] / g["S"],
                           aero.fuselage_lift_factor(g["d_f"], g["wing"].span))


def point(b, d, L, label, V_kt, V_C, V_D, h_ft, cl_alpha_record):
    """All load factors at one speed (kt EAS) and altitude, both weights."""
    atm = isa(h_ft)
    V = V_kt * KT
    U = loads.design_gust_velocity(V, V_C, V_D, L["gust_ude_fps"], 0.5 * L["gust_ude_fps"])
    M = V / math.sqrt(atm["sigma"]) / atm["a"]
    S, mac = b["geom"]["S"], b["geom"]["wing"].mac
    W_zf = d["W0_lb"] - d["fuel_lb"]
    out = {"speed": label, "V_eas_kt": V_kt, "altitude_ft": h_ft, "U_de_fps": U, "mach": M, "weights": {}}
    for wlabel, W in (("takeoff_weight", d["W0_lb"]), ("zero_fuel_weight", W_zf)):
        # stage1.vn_diagram takes RHO0 at sea level, uav._build takes isa(0)'s density: each as its record does
        rho_vn = RHO0 if h_ft == 0.0 else atm["rho"]
        n_rec = loads.gust_load_factor(W / S, V, U, cl_alpha_record, mac, rho_vn)[0]
        n_siz = loads.gust_load_factor(W / S, V, U, lift_slope_at(b, d["A"], L, M), mac, atm["rho"])[0]
        # sensitivity, not the rule: the full V_C gust velocity (30 ft/s) at this speed, no fall to V_D
        n_full = loads.gust_load_factor(W / S, V, L["gust_ude_fps"], lift_slope_at(b, d["A"], L, M), mac, atm["rho"])[0]
        n_aero = 0.5 * RHO0 * V ** 2 * d["CL_max"]["clean"] / (W / S)      # EAS: sea-level density
        out["weights"][wlabel] = {
            "W_lb": W,
            "n_gust_vn_record": n_rec, "n_gust_neg_vn_record": 2.0 - n_rec,
            "n_gust_sizing": n_siz, "n_gust_neg_sizing": 2.0 - n_siz,
            "n_gust_sizing_full_ude_sensitivity": n_full, "n_gust_neg_full_ude_sensitivity": 2.0 - n_full,
            "n_manoeuvre_aero": n_aero, "n_manoeuvre": min(n_aero, L["limit_load_factor"])}
    return out


def compute(design_path):
    d, L, b, ledger_path, check = sp.rebuild(design_path)
    V_C = d["V_c_eas_kt"]["sea_level"]
    V_D = 1.5 * V_C                                      # Stage 1's dive speed, vn_diagram
    per = sp.uav.performance(b | {"W0": d["W0_lb"], "W_S": d["W_S"]}, L)
    top = {"sea_level": per["vmax_sl_kt_eas"], "mission_altitude": per["vmax_alt_kt_eas"]}
    h_alt = L["mission_altitude_ft"]
    pts = []
    for alt_label, h in (("sea_level", 0.0), ("mission_altitude", h_alt)):
        for label, v in (("V_C", V_C), ("V_D", V_D), ("level_top_speed", top[alt_label])):
            p = point(b, d, L, label, v, V_C * KT, V_D * KT, h, b["CLa"])
            p["altitude"] = alt_label
            pts.append(p)
    n_pos, n_neg = L["limit_load_factor"], L["negative_load_factor"]
    margin = L.get("margin_gust_g", 0.0)
    for p in pts:
        for w in p["weights"].values():
            w["exceeds_positive_limit"] = max(w["n_gust_vn_record"], w["n_gust_sizing"]) > n_pos
            w["exceeds_negative_limit_with_margin"] = min(w["n_gust_neg_vn_record"], w["n_gust_neg_sizing"]) < n_neg + margin
            w["exceeds_negative_limit"] = min(w["n_gust_neg_vn_record"], w["n_gust_neg_sizing"]) < n_neg
    # reproduction of the record's own entries at V_C and V_D
    repro = {}
    for key, rec in d["vn"].items():
        if not key.startswith("gust_"):
            continue
        alt_label = "sea_level" if key.startswith("gust_sea_level") else "mission_altitude"
        wlabel = "takeoff_weight" if key.endswith("takeoff_weight") else "zero_fuel_weight"
        pc = next(p for p in pts if p["altitude"] == alt_label and p["speed"] == "V_C")["weights"][wlabel]
        pd = next(p for p in pts if p["altitude"] == alt_label and p["speed"] == "V_D")["weights"][wlabel]
        repro[key] = {"n_cruise": [rec["n_cruise"], pc["n_gust_vn_record"]],
                      "n_dive": [rec["n_dive"], pd["n_gust_vn_record"]],
                      "n_cruise_neg": [rec["n_cruise_neg"], pc["n_gust_neg_vn_record"]],
                      "n_dive_neg": [rec["n_dive_neg"], pd["n_gust_neg_vn_record"]]}
    for key, rec in d["gusts"].items():
        alt_label, wlabel = key.split("/")
        pc = next(p for p in pts if p["altitude"] == alt_label and p["speed"] == "V_C")["weights"][wlabel]
        repro["gusts/" + key] = {"n_gust": [rec, pc["n_gust_sizing"]]}
    V_corner = math.sqrt(2 * n_pos * d["W_S"] / (RHO0 * d["CL_max"]["clean"])) / KT
    return {"design_W0_lb": d["W0_lb"], "fuel_lb": d["fuel_lb"], "W_S": d["W_S"], "CL_max_clean": d["CL_max"]["clean"],
            "V_C_eas_kt": V_C, "V_D_eas_kt": V_D, "V_corner_eas_kt": V_corner,
            "level_top_speed_eas_kt": top,
            "limits": {"positive": n_pos, "negative": n_neg, "negative_margin_g": margin,
                       "negative_with_margin": n_neg + margin},
            "points": pts, "reproduction_of_record": repro, "rebuild_check": check, "ledger_path": str(ledger_path)}


def worst_reproduction_error(res):
    return max(abs(new / rec - 1.0) for r in res["reproduction_of_record"].values() for rec, new in r.values())


def report_text(res):
    """Markdown report from the record and nothing else."""
    lim, inp = res["limits"], res["inputs"]
    pts = res["points"]
    L = ["# Task 12: V-n check of the design record (ruling B-4)", "",
         f"Record: `{inp['command'].split('--out ')[1].split(' ')[0]}`; design `{inp['design']}` (sha256 {inp['design_sha256'][:12]}); "
         f"commit {inp['git_commit'][:7]}, git_dirty {inp['git_dirty']}. Command: `{inp['command']}`.", "",
         "Stage 1's own loads code (`conceptual/raymer_loads.py`), the design rebuilt from its record, not re-sized. "
         f"W0 {res['design_W0_lb']:.1f} lb, fuel {res['fuel_lb']:.1f} lb, W/S {res['W_S']:g}, clean CL_max {res['CL_max_clean']:g}.", "",
         "## Speeds and limits", "",
         f"- V_C {res['V_C_eas_kt']:.1f} kt EAS, V_D {res['V_D_eas_kt']:.1f} kt EAS (1.5 V_C), corner speed {res['V_corner_eas_kt']:.1f} kt EAS.",
         f"- Level top speed: {res['level_top_speed_eas_kt']['sea_level']:.1f} kt EAS at sea level, "
         f"{res['level_top_speed_eas_kt']['mission_altitude']:.1f} kt EAS at 20,000 ft.",
         f"- Limits (ledger): positive {lim['positive']:g}; negative {lim['negative']:g} with a {lim['negative_margin_g']:g} g margin, "
         f"so the negative gust must stay at or above {lim['negative_with_margin']:g}.", "",
         f"Reproduction of the record: at V_C and V_D the check reproduces the record's `vn` and `gusts` entries; "
         f"worst relative difference {res['worst_relative_reproduction_error']:.1e} (test `tests/task12/test_vn_check.py`, limit 1e-5).", "",
         "## Load factors", "",
         "Gust load factor with the lift slope at the speed's own Mach number (the value the structure was sized with, the record's `gusts`); "
         "the record's `vn` entries use the slope at the sizing Mach and differ slightly (both are in the record). "
         "U_de 30 ft/s up to V_C, falling to 15 ft/s at V_D and 15 ft/s above (Raymer p. 339). "
         "Manoeuvre: aerodynamic limit q CL_max/(W/S), capped at the structural limit 3.8. "
         "The last two columns are a sensitivity, not the rule: U_de held at 30 ft/s at every speed.", "",
         "| Altitude | Speed | V EAS (kt) | U_de (ft/s) | Weight | n gust + | n gust - | n manoeuvre (aero) | n manoeuvre (capped) | exceeds | n gust + (U_de 30) | n gust - (U_de 30) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in pts:
        for wl, w in p["weights"].items():
            ex = []
            if w["exceeds_positive_limit"]:
                ex.append("positive")
            if w["exceeds_negative_limit"]:
                ex.append("negative")
            elif w["exceeds_negative_limit_with_margin"]:
                ex.append("negative margin")
            L.append(f"| {p['altitude']} | {p['speed']} | {p['V_eas_kt']:.1f} | {p['U_de_fps']:.1f} | {wl.replace('_weight', '')} | "
                     f"{w['n_gust_sizing']:.3f} | {w['n_gust_neg_sizing']:.3f} | {w['n_manoeuvre_aero']:.3f} | {w['n_manoeuvre']:.3f} | "
                     f"{', '.join(ex) or 'no'} | {w['n_gust_sizing_full_ude_sensitivity']:.3f} | {w['n_gust_neg_full_ude_sensitivity']:.3f} |")
    over = [(p["altitude"], p["speed"], wl) for p in pts for wl, w in p["weights"].items()
            if w["exceeds_positive_limit"] or w["exceeds_negative_limit_with_margin"]]
    sens = [(p["altitude"], p["speed"], wl, w["n_gust_sizing_full_ude_sensitivity"], w["n_gust_neg_full_ude_sensitivity"])
            for p in pts for wl, w in p["weights"].items()
            if w["n_gust_sizing_full_ude_sensitivity"] > lim["positive"] or w["n_gust_neg_full_ude_sensitivity"] < lim["negative_with_margin"]]
    L += ["", "## Result", ""]
    L.append("Points that exceed a limit under the design gust rule: " +
             ("; ".join(f"{a}, {s}, {w}" for a, s, w in over) if over else "none (every gust load factor above is inside +3.8 and the negative limit with margin)") + ".")
    L.append("")
    L.append("Points that would exceed a limit if U_de stayed at 30 ft/s at every speed (sensitivity, not the rule; positive / negative): " +
             ("; ".join(f"{a}, {s}, {w} ({p:.3f} / {n:.3f})" for a, s, w, p, n in sens) if sens else "none") + ".")
    L += ["", f"The structure is sized at V_C {res['V_C_eas_kt']:g} kt EAS (the per-design rule, ruling B-4) and V_D {res['V_D_eas_kt']:g} kt EAS. The sea-level level top speed "
          f"({res['level_top_speed_eas_kt']['sea_level']:.1f} kt EAS) is above V_D: the structure is not cleared to it. "
          "Envelope protection (the autopilot holding the aircraft at or below V_C, and below V_D at sea level) is a preliminary-design "
          "requirement per ruling B-4. No negative manoeuvre load factor is computed: the record has no negative CL_max."]
    return "\n".join(L) + "\n"


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, cwd=REPO).stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    res = compute(a.design)
    res["worst_relative_reproduction_error"] = worst_reproduction_error(res)
    dirty = sp.git_dirty_files()
    res["inputs"] = {"design": a.design, "design_sha256": sp.sha256(a.design),
                     "ledger": res.pop("ledger_path"), "ledger_sha256": sp.sha256(Path(a.design).parent / "ledger.yaml"),
                     "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(dirty), "git_dirty_files": dirty,
                     "python": platform.python_version(), "seed": None,
                     "command": "python -m measurement.vn_check " + " ".join(sys.argv[1:] if argv is None else argv)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report_text(res))
    print("worst reproduction error", res["worst_relative_reproduction_error"])


if __name__ == "__main__":
    main()

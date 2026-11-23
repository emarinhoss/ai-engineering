"""The Rolls-Royce M250-B17F represented by Mattingly's App. K turboprop cycle, calibrated at take-off
and then validated against the brochure's part-power data (data/task12/engines.yaml, entry
RR_M250_B17F, brochure VCOM13797 p. 4 and FAA TCDS E10CE).

Same model as the TP100 (measurement/tp100_engine.py): its fixed gas assumptions (`_gas`: uncooled,
MSH burner, gamma_t 1.3, component losses), the optimum turbine ratio tau_t* (p. 597), the control law
of p. 606 (full throttle is Tt4 at its rated value or less with the compressor pressure ratio pi_c not
above its sea-level rated value: pi_c is a ceiling, not a held value; at part power pi_c falls with Tt4,
which is how a free-turbine gas generator sheds power) and its table format. The brochure's ratings are sea-level static. The cycle divides by flight speed (thrust is
power over speed), so the rating condition is sea level, M0 = 0.1 (about 66 kt), as for the TP100;
at that speed ram recovery is negligible against the brochure's rounding.

Unlike the TP100 the brochure gives TWO cycle-level numbers at take-off, so each family member
solves two unknowns, the compressor pressure ratio pi_c and the turbine inlet temperature Tt4:
  1. shaft SFC at take-off = the brochure value (0.613, a maximum/guaranteed value), and
  2. the inter-turbine temperature Tt4.5 = Tt4 tau_m1 tau_tH = the brochure measured gas
     temperature (810 C). The M250's MGT is measured between the gas-producer (HP) turbine and
     the power (LP) turbine. In App. K the HP turbine drives the compressor, and design_point
     returns tau_tH and tau_m1 (tau_m1 = 1 with no cooling), so Tt4.5 is exact in the model.
The turbine ratio tau_t is the book's optimum at each trial (as for the TP100).
Family (a study choice for a small engine of the 1980s, not datasheet values): polytropic
efficiencies e_c in (0.78, 0.82, 0.86) and e_t in (0.82, 0.86, 0.90), turbine efficiency the same
for HP and LP. A member with no solution is reported with the reason, not dropped silently.

VALIDATION. Tolerances fixed before any result was looked at:
  - shaft SFC at sea level, M0 0.1, at the three brochure part-power points (380, 377 and 314 shp
    for the 450 shp column), with the App. K control law (shaft_power_at, pi_c not above its
    sea-level rated value): each within +-5 % of the brochure value;
  - Tt4.5 at the 380 shp point against the brochure's 752 C: within +-25 C.
A member passes only if every one of its four comparisons is within tolerance. The same
procedure runs on the brochure's other (420 shp, SFC 0.657, MGT 810/738 C) column as a second
family. A failed validation is reported as failed; no member or tolerance is adjusted afterwards.
The brochure values are maxima (guaranteed), not typical, so a model calibrated to the maxima is
not expected to read below them by much; that is for the reader of the report, not a reason to
change a tolerance.

What a pass means (review M-3). Once take-off SFC is calibrated, the part-power SFC is nearly fixed
by the cycle: a pass says the model is consistent with the brochure from 70 to 100 % power at sea
level, not that it predicts fuel flow at low power or at altitude. The 380 and 377 shp points are
effectively one point. The check that discriminates is the SFC ratio to take-off (reported beside the
SFC) and the MGT drop. The brochure gives no data below 70 % power and none at altitude.

Python 3.13; no seeds (the calculation is deterministic).
"""
# ruff: noqa: ISC004  (the report text is a list of adjacent string pieces, as in info_gap)
import argparse
import hashlib
import itertools
import json
import math
import platform
import subprocess
from pathlib import Path

import numpy as np
import yaml

from conceptual.engine_model import TableEngine
from conceptual.units import KT, isa
from measurement import tp100_engine as tp
from measurement import turboprop_cycle as tc

REPO = Path(__file__).resolve().parents[1]
ENGINES = REPO / "data" / "task12" / "engines.yaml"
ENGINE_NAME = "RR_M250_B17F"
RATED_SHP = 450.0
BSFC_TAKEOFF = 0.613            # brochure, take-off maximum value
MGT_TAKEOFF_C = 810.0
M_RATING = tp.M_RATING          # 0.1
GRID = {"e_c": (0.78, 0.82, 0.86), "e_t": (0.82, 0.86, 0.90)}
NOMINAL = {"e_c": 0.82, "e_t": 0.86}
TOL_SFC = 0.05                  # relative, each part-power point
TOL_MGT_C = 25.0                # absolute, at the normal-cruise point
PI_C_BRACKET = (2.0, 14.0)      # same bracket as tp100_engine.calibrated
SL = isa(0.0)


def c_to_r(c):
    return (c + 273.15) * 1.8


def r_to_c(r):
    return r / 1.8 - 273.15


def ratings(column="450"):
    """Brochure sea-level static ratings from data/task12/engines.yaml: take_off, normal_cruise,
    cruise_a_90pct, cruise_b_75pct, each with shp, bsfc_max and (two of them) mgt_c."""
    e = yaml.safe_load(ENGINES.read_text())["engines"][ENGINE_NAME]
    return e["sl_static_ratings" if column == "450" else "sl_static_ratings_420_column"]


# ---- calibration ---------------------------------------------------------------------------------
def _design(pi_c, Tt4, e_c, e_t):
    """App. K design point at sea level, M0 0.1, with the optimum tau_t."""
    k = tp._gas(Tt4, e_c, e_t)
    t = tc.optimum_tau_t(M_RATING, SL["T"], SL["p"], pi_c, k)
    return k, tc.design_point(M_RATING, SL["T"], SL["p"], pi_c, t, k)


def _tt45(d):
    """Inter-turbine total temperature (R): Tt4 times the coolant-mixer ratio and the HP turbine
    ratio (design_point returns both; the mixer ratio is 1 without cooling)."""
    return d["Tt4"] * d["tau_m1"] * d["tau_tH"]


def _tt4_for_mgt(pi_c, mgt_r, e_c, e_t):
    """Tt4 at which Tt4.5 equals mgt_r for this pi_c. Tt4.5 is nearly linear in Tt4, so a secant
    iteration from two starting guesses converges in a few steps (a bisection costs ten times more
    design points); raises ValueError if the cycle is invalid on the way."""
    T_a, T_b = 2300.0, 2400.0
    f_a = _tt45(_design(pi_c, T_a, e_c, e_t)[1]) - mgt_r
    f_b = _tt45(_design(pi_c, T_b, e_c, e_t)[1]) - mgt_r
    for _ in range(12):
        if abs(f_b) < 1e-4 or f_b == f_a:
            break
        T_a, T_b, f_a = T_b, T_b - f_b * (T_b - T_a) / (f_b - f_a), f_b
        f_b = _tt45(_design(pi_c, T_b, e_c, e_t)[1]) - mgt_r
    return T_b


def calibrate(e_c, e_t, shp=RATED_SHP, bsfc=BSFC_TAKEOFF, mgt_c=MGT_TAKEOFF_C):
    """One family member: solve pi_c and Tt4 so that take-off shaft SFC = bsfc and Tt4.5 = mgt_c.
    Nested bisection: for each pi_c, Tt4 is set by the MGT; pi_c is then set by the SFC (SFC falls
    as pi_c rises over the bracket). Returns {"k", "ref", "Tt4", "e_c", "e_t"} in the form
    tp100_engine.power_available / table expect; raises ValueError with the reason if no solution."""
    mgt_r = c_to_r(mgt_c)

    def sfc_at(pi_c):
        Tt4 = _tt4_for_mgt(pi_c, mgt_r, e_c, e_t)
        d = _design(pi_c, Tt4, e_c, e_t)[1]
        if abs(_tt45(d) - mgt_r) > 0.01:
            raise ValueError(f"Tt4.5 {mgt_c} C not reached at pi_c {pi_c:.1f} (Tt4 {Tt4:.0f} R)")
        return d["bsfc"], Tt4

    lo, hi = PI_C_BRACKET
    if sfc_at(hi)[0] > bsfc:
        raise ValueError(f"SFC still above {bsfc} at pi_c {hi} with Tt4.5 {mgt_c} C")
    if sfc_at(lo)[0] < bsfc:
        raise ValueError(f"SFC already below {bsfc} at pi_c {lo} with Tt4.5 {mgt_c} C")
    for _ in range(35):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if sfc_at(mid)[0] > bsfc else (lo, mid)
    Tt4 = sfc_at(hi)[1]
    k, ref = _design(hi, Tt4, e_c, e_t)
    ref["m0"] = shp / ref["shaft_hp_per_m0"]
    return {"Tt4": Tt4, "e_c": e_c, "e_t": e_t, "k": k, "ref": ref}


def family(**target):
    """All GRID members calibrated to the target (keywords of calibrate). Returns (members,
    failures) with failures a list of {e_c, e_t, reason}."""
    members, failures = [], []
    for e_c, e_t in itertools.product(*GRID.values()):
        try:
            members.append(calibrate(e_c, e_t, **target))
        except ValueError as err:
            failures.append({"e_c": e_c, "e_t": e_t, "reason": str(err)})
    return members, failures


# ---- part power and validation ---------------------------------------------------------------------
def part_power(member, shp):
    """(Shaft SFC, Tt4.5 in deg C, Tt4 in R) at sea level, M0 0.1, shaft hp shp, App. K control law."""
    ref = member["ref"]
    r = tc.shaft_power_at(ref, M_RATING, SL["T"], SL["p"], shp, member["k"], pi_c_max=ref["pi_c"])
    return r["bsfc"], r_to_c(r["Tt4"] * ref["tau_m1"] * ref["tau_tH"]), r["Tt4"]   # HP ratios fixed off design


def validate(member, rates):
    """Comparisons of one member with the brochure's part-power rows; rates from ratings(). Beside each SFC
    its ratio to the take-off SFC, model against brochure (review M-3)."""
    rows = []
    sfc_to = member["ref"]["bsfc"]
    for name in ("normal_cruise", "cruise_a_90pct", "cruise_b_75pct"):
        shp, want = rates[name]["shp"], rates[name]["bsfc_max"]
        sfc, mgt, Tt4 = part_power(member, shp)
        rows.append({"point": name, "shp": shp, "bsfc_brochure": want, "bsfc": sfc,
                     "dev_pct": 100.0 * (sfc / want - 1.0), "Tt4_R": Tt4, "mgt_c": mgt,
                     "ratio_model": sfc / sfc_to, "ratio_brochure": want / rates["take_off"]["bsfc_max"],
                     "ok": abs(sfc / want - 1.0) <= TOL_SFC})
    mgt_want = rates["normal_cruise"]["mgt_c"]
    mgt_dev = rows[0]["mgt_c"] - mgt_want
    return {"points": rows, "mgt_c_brochure": mgt_want, "mgt_c": rows[0]["mgt_c"], "mgt_dev_c": mgt_dev,
            "mgt_ok": abs(mgt_dev) <= TOL_MGT_C, "passed": all(r["ok"] for r in rows) and abs(mgt_dev) <= TOL_MGT_C}


def study(column):
    """Calibrate every grid member to the column's take-off row, validate it on the part-power rows."""
    rates = ratings(column)
    to = rates["take_off"]
    members, failures = family(shp=to["shp"], bsfc=to["bsfc_max"], mgt_c=to["mgt_c"])
    out = []
    for m in members:
        ref = m["ref"]
        out.append({"e_c": m["e_c"], "e_t": m["e_t"], "pi_c": ref["pi_c"], "Tt4_R": m["Tt4"],
                    "Tt45_R": _tt45(ref), "Tt45_c": r_to_c(_tt45(ref)), "tau_t": ref["tau_t"],
                    "bsfc_takeoff": ref["bsfc"], "validation": validate(m, rates)})
    return {"column": column, "takeoff": to, "members": out, "failures": failures, "_members": members}


# ---- table for the Stage 1 sizing loop ---------------------------------------------------------------
def table(member):
    """Same table as tp100_engine.table: rated 450 shp, calibration SFC 0.613, engine name; the control
    law text says pi_c is a ceiling (review M-5; the numbers are those of tp100_engine.table)."""
    return tp.table(member, rated_shp=RATED_SHP, calibration_bsfc=BSFC_TAKEOFF,
                    extra={"engine": ENGINE_NAME, "calibration_mgt_c": MGT_TAKEOFF_C,
                           "control_law": "Tt4 <= rated, pi_c not above its sea-level rated value (a ceiling: pi_c falls "
                                          "with Tt4 at part power)"})


# ---- facts the report states about the table and the control law (review M-1, M-2, M-6, M-7) --------------
LAPSE_ALTITUDES_FT = (20000.0, 23000.0)
LAPSE_V_KT = 95.0               # flight speed of the lapse comparison (the climb speed of the Stage 1 sizing)


def unchoked_cells(t):
    """Share of table cells (altitude, speed, power fraction) whose LP turbine pressure ratio is below the
    critical value, i.e. outside App. K's choked-turbine assumption, and the range over the (altitude, speed)
    columns of the lowest power fraction at which the cell is choked."""
    lp, crit, f = np.array(t["lp_turbine_pressure_ratio"]), t["critical_pressure_ratio"], np.array(t["power_fraction"])
    choked = lp >= crit
    lowest = [f[np.argmax(choked[i, j])] if choked[i, j].any() else math.inf
              for i in range(lp.shape[0]) for j in range(lp.shape[1])]
    return {"share": float(1.0 - choked.mean()), "n_cells": int(choked.size),
            "lowest_choked_fraction_min": float(min(lowest)), "lowest_choked_fraction_max": float(max(lowest)),
            "fraction_axis": [float(f[0]), float(f[-1])]}


def altitude_lapse(member, h_ft, V_kt=LAPSE_V_KT):
    """Full-throttle power over the sea-level rating at h_ft, V_kt, for the two control limits: pi_c not
    above its rated value (the table's law) and Tt4 at its rated value only (no pi_c limit, no Tt3 limit).
    Returns shp, lapse and MGT (deg C) for each."""
    ref, a = member["ref"], isa(h_ft)
    M0 = V_kt * KT / a["a"]
    out = {}
    for label, limits in (("pi_c_ceiling", {"pi_c_max": ref["pi_c"]}), ("Tt4_only", {})):
        r = tc.full_throttle(ref, M0, a["T"], a["p"], member["k"], **limits)
        out[label] = {"shp": r["shaft_hp"], "lapse": r["shaft_hp"] / RATED_SHP, "pi_c": r["pi_c"],
                      "mgt_c": r_to_c(r["Tt4"] * ref["tau_m1"] * ref["tau_tH"])}
    return out


def static_power(path):
    """Sea-level full-throttle power and SFC of the written table at low speeds, and the speed at which its
    interpolated power first reaches the rating (TableEngine.bsfc refuses a request above the power available)."""
    e = TableEngine(path)
    speeds = (30.0, 50.0, 66.0, 70.0)
    rows = [{"V_kt": v, "shp": e.power_available(0.0, v),
             "bsfc": e.bsfc(0.0, v, e.power_available(0.0, v))} for v in speeds]
    reach = next((float(v) for v in np.arange(30.0, 230.0, 0.1) if e.power_available(0.0, v) >= RATED_SHP * (1 - 1e-6)), None)
    return {"rows": rows, "speed_reaching_rating_kt": reach}


def facts(studies, members, table_path):
    """Everything the report says about the table, computed from this run's members and table file."""
    t = json.loads(Path(table_path).read_text())
    nom = next(m for m in members if (m["e_c"], m["e_t"]) == (NOMINAL["e_c"], NOMINAL["e_t"]))
    lapses = {str(h): {"nominal": altitude_lapse(nom, h), "members": [altitude_lapse(m, h) for m in members]}
              for h in LAPSE_ALTITUDES_FT}
    s450 = studies[0]
    pts = [r for m in s450["members"] for r in m["validation"]["points"]]
    t450, t420 = ratings("450")["take_off"], ratings("420")["take_off"]
    return {"unchoked": unchoked_cells(t), "lapse": lapses, "lapse_V_kt": LAPSE_V_KT, "static": static_power(table_path),
            "sfc_dev_pct_range": [min(r["dev_pct"] for r in pts), max(r["dev_pct"] for r in pts)],
            "mgt_dev_c_range": [min(m["validation"]["mgt_dev_c"] for m in s450["members"]),
                                max(m["validation"]["mgt_dev_c"] for m in s450["members"])],
            "takeoff_sfc_420_over_450_pct": 100.0 * (t420["bsfc_max"] / t450["bsfc_max"] - 1.0),
            "n_pass_450": sum(m["validation"]["passed"] for m in s450["members"]), "n_450": len(s450["members"]),
            "n_pass_420": sum(m["validation"]["passed"] for m in studies[1]["members"]), "n_420": len(studies[1]["members"])}


# ---- run record and report --------------------------------------------------------------------------
def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, cwd=REPO).stdout


def _fmt_family(s):
    p = s["takeoff"]
    lines = [f"### {s['column']} shp column (take-off {p['shp']} shp, SFC {p['bsfc_max']}, MGT {p['mgt_c']} C)", "",
             "| e_c | e_t | pi_c | Tt4 (R) | Tt4.5 (R) | tau_t | SFC TO | SFC pt 1 | dev % | SFC pt 2 | dev % | "
             "SFC pt 3 | dev % | MGT pt 1 (C) | dev (C) | pass |", "|" + "---|" * 16]
    for m in s["members"]:
        v = m["validation"]
        pts = []
        for r in v["points"]:
            pts += [f"{r['bsfc']:.4f}", f"{r['dev_pct']:+.2f}"]
        lines.append(f"| {m['e_c']} | {m['e_t']} | {m['pi_c']:.2f} | {m['Tt4_R']:.1f} | {m['Tt45_R']:.1f} | "
                     f"{m['tau_t']:.3f} | {m['bsfc_takeoff']:.4f} | " + " | ".join(pts)
                     + f" | {v['mgt_c']:.1f} | {v['mgt_dev_c']:+.1f} | {'PASS' if v['passed'] else 'FAIL'} |")
    rates = ratings(s["column"])
    lines += ["", "Brochure points: " + ", ".join(f"{n} {rates[n]['shp']} shp / {rates[n]['bsfc_max']}"
                                                  for n in ("normal_cruise", "cruise_a_90pct", "cruise_b_75pct"))
              + f"; MGT at {rates['normal_cruise']['shp']} shp {rates['normal_cruise']['mgt_c']} C. "
              "Points 1, 2, 3 in that order.", ""]
    if s["failures"]:
        lines += ["Members without a solution:", ""] + [f"- e_c {f['e_c']}, e_t {f['e_t']}: {f['reason']}"
                                                         for f in s["failures"]] + [""]
    else:
        lines += ["Every grid member calibrated.", ""]
    n = len(s["members"])
    npass = sum(m["validation"]["passed"] for m in s["members"])
    if s["members"]:
        lines += ["SFC as a ratio to take-off SFC (model range over the calibrated members, nominal member, brochure):", "",
                  "| point | shp | model min | model max | nominal | brochure |", "|---|---|---|---|---|---|"]
        for i, name in enumerate(("normal_cruise", "cruise_a_90pct", "cruise_b_75pct")):
            rs_ = [m["validation"]["points"][i]["ratio_model"] for m in s["members"]]
            nm_ = next((m for m in s["members"] if (m["e_c"], m["e_t"]) == (NOMINAL["e_c"], NOMINAL["e_t"])), s["members"][0])
            p_ = nm_["validation"]["points"][i]
            lines.append(f"| {name} | {p_['shp']} | {min(rs_):.3f} | {max(rs_):.3f} | {p_['ratio_model']:.3f} | "
                         f"{p_['ratio_brochure']:.3f} |")
        lines.append("")
    lines += [f"Validation: {npass} of {n} calibrated members pass all four comparisons "
              f"(SFC within {100 * TOL_SFC:.0f} %, MGT within {TOL_MGT_C:.0f} C).", ""]
    return lines


def report(rec):
    inp = rec["inputs"]
    lines = ["# Task 12: RR M250-B17F App. K cycle, calibration and validation", "",
             "Generated by `python -m measurement.m250_engine`; every number below comes from that run.", "",
             "## Inputs", "",
             f"- commit {inp['commit']}; dirty tree: {inp['git_dirty']}"
             + (f" ({len(inp['git_dirty_files'])} files in conceptual, measurement, data)" if inp["git_dirty"] else ""),
             f"- engines.yaml sha256 `{inp['engines_sha256']}`; python {inp['python']}; seeds: none (deterministic)",
             f"- rating condition: sea level, M0 {inp['m_rating']} (brochure ratings are sea-level static; the cycle needs M0 > 0)",
             f"- grid: e_c {inp['grid']['e_c']}, e_t {inp['grid']['e_t']} (study choice); nominal member e_c "
             f"{inp['nominal']['e_c']}, e_t {inp['nominal']['e_t']}",
             f"- tolerances (set before the run): SFC +-{100 * inp['tol_sfc']:.0f} % at each part-power point, "
             f"MGT +-{inp['tol_mgt_c']:.0f} C at the normal-cruise point",
             "- fixed gas assumptions: those of measurement/tp100_engine.py `_gas`", "",
             "## Method", "",
             "Each member solves pi_c and Tt4 so that take-off shaft SFC and the inter-turbine temperature "
             "Tt4.5 = Tt4 tau_m1 tau_tH both equal the brochure (MGT is measured between the gas-producer "
             "and power turbines). Part power uses shaft_power_at with pi_c not above its sea-level rated value "
             "(a ceiling: pi_c falls with Tt4 at part power). "
             "Brochure values are maxima, and the 450 column is read as the B17F (see label_conflict in engines.yaml).",
             "", "## What the validation shows and does not show (review M-3)", "",
             "Once take-off SFC is calibrated, the part-power SFC is nearly fixed by the cycle, so the SFC comparison is "
             "weak evidence. The claim made is only that the model is **consistent with the brochure from 70 to 100 % "
             "power at sea level**. It is not shown at lower power (the brochure has no point below 70 %) or at any "
             "altitude. The 380 and 377 shp points are effectively one point. The ratios to take-off SFC and the MGT "
             "drop discriminate more (tables below). Wrong calibrations pass the SFC comparison as well.", "",
             "## Results", ""]
    for s in rec["studies"]:
        lines += _fmt_family(s)
    nm = rec["nominal"]
    lines += ["## Table", "", f"Nominal member e_c {nm['e_c']}, e_t {nm['e_t']}: pi_c {nm['pi_c']:.2f}, "
              f"Tt4 {nm['Tt4_R']:.1f} R; written to `{rec['table_path']}`.", ""]
    lines += _fmt_facts(rec["facts"])
    return "\n".join(lines)


def _fmt_facts(f):
    """Report sections from facts(): deviations, unchoked cells, altitude lapse, static power, the label conflict."""
    u, st = f["unchoked"], f["static"]
    lo, hi = f["sfc_dev_pct_range"], f["mgt_dev_c_range"]
    L = ["## Deviation from the brochure (450 column, all calibrated members)", "",
         f"- SFC at the three part-power points: {lo[0]:+.2f} to {lo[1]:+.2f} % against the brochure's maximum values "
         f"(the model reads above them, within the +-{100 * TOL_SFC:.0f} % tolerance).",
         f"- MGT at 380 shp: {hi[0]:+.1f} to {hi[1]:+.1f} C against the brochure's 752 C (tolerance +-{TOL_MGT_C:.0f} C)"
         + (": positive, the model's MGT drop from take-off is smaller than the brochure's." if hi[0] > 0 else "."),
         f"- Members passing all four comparisons: {f['n_pass_450']} of {f['n_450']}.", "",
         "## Table cells outside the choked-turbine assumption (review M-1)", "",
         f"App. K holds the HP turbine ratios fixed because stations 4 and 4.5 are choked. In this engine's table "
         f"**{100 * u['share']:.1f} % of the {u['n_cells']} cells** (altitude x speed x power fraction) have an LP turbine "
         f"pressure ratio below the critical value. The cells are choked only at high power: over the (altitude, speed) "
         f"columns the lowest power fraction at which the cell is choked is {u['lowest_choked_fraction_min']:.2f} to "
         f"{u['lowest_choked_fraction_max']:.2f} of the table's full-throttle power (fraction axis {u['fraction_axis'][0]:.2f} "
         f"to {u['fraction_axis'][1]:.2f}); every cell below the smaller of the two fractions is unchoked, at every "
         "altitude and speed. The "
         "validation covers 70 to 100 % power at sea level only. The share of a mission's fuel burned in unchoked cells is "
         "reported by Stage 1 (`unchoked_fuel_share` of the design record).", "",
         "## Altitude lapse: the two control limits (review M-2)", "",
         f"Full-throttle power at {f['lapse_V_kt']:g} kt TAS over the 450 shp rating, for the family. The table uses the "
         "pi_c ceiling (conservative: pi_c is held down, so Tt4 and power fall with altitude). Tt4 at its rated value with "
         "no pi_c limit is the other end; the true lapse lies between them and this model cannot say where. No "
         "Tt3 limit is applied in either.", "",
         "| altitude (ft) | limit | nominal member shp | lapse | MGT (C) | family lapse min | family lapse max |",
         "|---|---|---|---|---|---|---|"]
    for h, d in f["lapse"].items():
        for lim in ("pi_c_ceiling", "Tt4_only"):
            ls = [m[lim]["lapse"] for m in d["members"]]
            n = d["nominal"][lim]
            L.append(f"| {float(h):,.0f} | {lim} | {n['shp']:.1f} | {n['lapse']:.3f} | {n['mgt_c']:.0f} | "
                     f"{min(ls):.3f} | {max(ls):.3f} |")
    L += ["", "The info-gap and sizing studies carry this uncertainty as a **cap** on available power (+-10 % at h = 1), "
          "not as a rescale of the power-fraction axis: SFC at a given shaft power does not change with it.", "",
          "## Static and low-speed power (review M-7)", "",
          "The brochure's ratings are sea-level static; the cycle needs M0 > 0 and is calibrated at 66 kt (M0 0.1). "
          "Table full-throttle power and SFC at sea level:", "",
          "| V (kt) | shp | SFC |", "|---|---|---|"]
    L += [f"| {r['V_kt']:g} | {r['shp']:.1f} | {r['bsfc']:.4f} |" for r in st["rows"]]
    L += ["", f"The interpolated power first reaches the 450 shp rating at {st['speed_reaching_rating_kt']:.1f} kt; below that "
          "`TableEngine.bsfc` refuses a request for exactly 450 shp (it exceeds the power available). No caller asks for "
          "that: Stage 1 evaluates take-off at the power available at 60 kt. Take-off is slightly optimistic "
          "(the 30 to 50 kt power above is below the rating by the amount shown; the sizing uses the rating).", "",
          "## The brochure's column labels (review M-6)", "",
          "The brochure prints 450 shp under 'B17C' and 420 shp under 'B17F, F/C, F/2'; FAA TCDS E10CE gives the B17F "
          "series 450 shp. This work reads the labels as swapped and takes the 450 column as the B17F. **That is not "
          "confirmed by Rolls-Royce.** If the 420 column were the B17F, its take-off SFC is "
          f"{f['takeoff_sfc_420_over_450_pct']:+.1f} % worse than the 450 column's, and the validation fails "
          f"({f['n_pass_420']} of {f['n_420']} members pass, see the 420 column above).", "",
          "## Transcription and rating notes", "",
          "- The 377 and 314 shp rows of the 450 column were rechecked against the image of the brochure's p. 4 "
          "(2026-11-23): they are printed as such beside 'Cruise A (90%)' and 'Cruise B (75%)'. They are 90 % and 75 % "
          "of 419 shp; in the 420 column the cruise rows are 90 % and 75 % of that column's normal-cruise power, 369 shp. "
          "This is the brochure's own data, not a transcription error.",
          "- The brochure's footnote permits take-off MGT up to 810 C provided maximum torque is not exceeded: 810 C is "
          "a limit, and it is the value the calibration matches. The cruise MGT values (752 C, and 738 C in the 420 "
          "column) are printed as rating values with no footnote.", ""]
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    studies = [study("450"), study("420")]
    nominal = next((m for m in studies[0]["_members"]
                    if (m["e_c"], m["e_t"]) == (NOMINAL["e_c"], NOMINAL["e_t"])), None)
    if nominal is None:
        raise SystemExit("the nominal member did not calibrate; no table written")
    Path(a.table).write_text(json.dumps(table(nominal), indent=1))
    dirty = [ln for ln in _git("status", "--porcelain", "--", "conceptual", "measurement", "data").splitlines()
             if ln.strip()]
    nm = next(m for m in studies[0]["members"] if (m["e_c"], m["e_t"]) == (NOMINAL["e_c"], NOMINAL["e_t"]))
    fct = facts(studies, studies[0]["_members"], a.table)
    for s in studies:
        del s["_members"]
    rec = {"inputs": {"commit": _git("rev-parse", "HEAD").strip(), "git_dirty": bool(dirty),
                      "git_dirty_files": dirty, "python": platform.python_version(), "seeds": None,
                      "engines_sha256": hashlib.sha256(ENGINES.read_bytes()).hexdigest(),
                      "m_rating": M_RATING, "grid": GRID, "nominal": NOMINAL, "tol_sfc": TOL_SFC,
                      "tol_mgt_c": TOL_MGT_C, "table_path": a.table, "report_path": a.report},
           "studies": studies, "nominal": nm, "table_path": a.table, "facts": fct}
    for p in (a.out, a.report):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rec, indent=1))
    Path(a.report).write_text(report(rec))
    print(f"wrote {a.table}, {a.out}, {a.report}")


if __name__ == "__main__":
    main()

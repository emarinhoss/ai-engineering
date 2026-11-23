"""The Rolls-Royce M250-B17F represented by Mattingly's App. K turboprop cycle, calibrated at take-off
and then validated against the brochure's part-power data (data/task12/engines.yaml, entry
RR_M250_B17F, brochure VCOM13797 p. 4 and FAA TCDS E10CE).

Same model as the TP100 (measurement/tp100_engine.py): its fixed gas assumptions (`_gas`: uncooled,
MSH burner, gamma_t 1.3, component losses), the optimum turbine ratio tau_t* (p. 597), the control law
of p. 606 (Tt4 <= rated, compressor pressure ratio held at its sea-level rated value) and its table
format. The brochure's ratings are sea-level static. The cycle divides by flight speed (thrust is
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
    for the 450 shp column), with the App. K control law (shaft_power_at, pi_c held at its rated
    value): each within +-5 % of the brochure value;
  - Tt4.5 at the 380 shp point against the brochure's 752 C: within +-25 C.
A member passes only if every one of its four comparisons is within tolerance. The same
procedure runs on the brochure's other (420 shp, SFC 0.657, MGT 810/738 C) column as a second
family. A failed validation is reported as failed; no member or tolerance is adjusted afterwards.
The brochure values are maxima (guaranteed), not typical, so a model calibrated to the maxima is
not expected to read below them by much; that is for the reader of the report, not a reason to
change a tolerance.

Python 3.13; no seeds (the calculation is deterministic).
"""
import argparse
import hashlib
import itertools
import json
import platform
import subprocess
from pathlib import Path

import yaml

from conceptual.units import isa
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
    """Shaft SFC and Tt4.5 (deg C) at sea level, M0 0.1, shaft hp shp, App. K control law."""
    ref = member["ref"]
    r = tc.shaft_power_at(ref, M_RATING, SL["T"], SL["p"], shp, member["k"], pi_c_max=ref["pi_c"])
    return r["bsfc"], r_to_c(r["Tt4"] * ref["tau_m1"] * ref["tau_tH"]), r["Tt4"]   # HP ratios fixed off design


def validate(member, rates):
    """Comparisons of one member with the brochure's part-power rows; rates from ratings()."""
    rows = []
    for name in ("normal_cruise", "cruise_a_90pct", "cruise_b_75pct"):
        shp, want = rates[name]["shp"], rates[name]["bsfc_max"]
        sfc, mgt, Tt4 = part_power(member, shp)
        rows.append({"point": name, "shp": shp, "bsfc_brochure": want, "bsfc": sfc,
                     "dev_pct": 100.0 * (sfc / want - 1.0), "Tt4_R": Tt4, "mgt_c": mgt,
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
    """Same table as tp100_engine.table: rated 450 shp, calibration SFC 0.613, engine name."""
    return tp.table(member, rated_shp=RATED_SHP, calibration_bsfc=BSFC_TAKEOFF,
                    extra={"engine": ENGINE_NAME, "calibration_mgt_c": MGT_TAKEOFF_C})


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
    lines += [f"Validation: {npass} of {n} calibrated members pass all four comparisons "
              f"(SFC within {100 * TOL_SFC:.0f} %, MGT within {TOL_MGT_C:.0f} C).", ""]
    return lines


def report(rec):
    inp = rec["inputs"]
    lines = ["# Task 12: RR M250-B17F App. K cycle, calibration and validation", "",
             f"Generated by `python -m measurement.m250_engine`; every number below comes from that run.", "",
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
             "and power turbines). Part power uses shaft_power_at with pi_c held at its rated value. "
             "Brochure values are maxima, and the 450 column is read as the B17F (see label_conflict in engines.yaml).",
             "", "## Results", ""]
    for s in rec["studies"]:
        lines += _fmt_family(s)
    nm = rec["nominal"]
    lines += ["## Table", "", f"Nominal member e_c {nm['e_c']}, e_t {nm['e_t']}: pi_c {nm['pi_c']:.2f}, "
              f"Tt4 {nm['Tt4_R']:.1f} R; written to `{rec['table_path']}`.", ""]
    return "\n".join(lines)


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
    for s in studies:
        del s["_members"]
    rec = {"inputs": {"commit": _git("rev-parse", "HEAD").strip(), "git_dirty": bool(dirty),
                      "git_dirty_files": dirty, "python": platform.python_version(), "seeds": None,
                      "engines_sha256": hashlib.sha256(ENGINES.read_bytes()).hexdigest(),
                      "m_rating": M_RATING, "grid": GRID, "nominal": NOMINAL, "tol_sfc": TOL_SFC,
                      "tol_mgt_c": TOL_MGT_C, "table_path": a.table, "report_path": a.report},
           "studies": studies, "nominal": nm, "table_path": a.table}
    for p in (a.out, a.report):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rec, indent=1))
    Path(a.report).write_text(report(rec))
    print(f"wrote {a.table}, {a.out}, {a.report}")


if __name__ == "__main__":
    main()

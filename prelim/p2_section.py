"""Preliminary design package P2: the wing section and its section data
(docs/specs/task12_preliminary_design.md, "P2. Wing section and section data"; decisions PD-5, PD-6).

    python -m prelim.p2_section --out runs/task12/pd/2026-11-27/p2
    python -m prelim.p2_section --out runs/task12/pd/2026-11-27/p2 --report-only \
        --report docs/validation/2026-11-27_task12_pd_p2.md

r0 is read, never written, and it is not re-sized. What is run here:
 1. Reynolds and Mach numbers at the root, mean and tip chord of r0 for the stall and the mission speeds;
 2. the section data of the NACA 4415 as digitized points of NACA Report 824 (data/task12/tr824_digitized,
    source record data/task12/pd_p2_section_source.yaml): lift curve, highest and lowest lift, zero-lift
    angle, moment about the quarter chord, lowest drag, smooth and with standard roughness;
 3. wing maximum lift from the section value by Raymer (12.15), p. 270, and (12.16), p. 272, flaps by (12.21),
    p. 278, as Stage 1; and the built aircraft of r0 flown again with that maximum lift (R17, R5, R7);
 4. optional third source (PD-6): XFOIL polars, if the program is installed. They carry no verdict.
The SU2 polars of the spec's step 4 are not run here (owner default O-1); the row is recorded "not run".

Output: OUT/p2.json, OUT/run.log, OUT/xfoil/*.txt. Units are foot, pound, second and degrees.
"""
import argparse
import hashlib
import json
import math
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import yaml

from conceptual import raymer_aero as aero
from conceptual import raymer_performance as perf
from conceptual import uav
from conceptual.units import KT, isa
from measurement import info_gap
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
R0 = REPO / "runs/task12/pd/2026-11-27/p0/r0"
DATA = REPO / "data/task12/tr824_digitized"
SOURCE = REPO / "data/task12/pd_p2_section_source.yaml"
WING_SECTION, TAIL_SECTION = "naca4415", "naca0012"       # PD-5
# bands and tolerances fixed before the run (spec P2 "Acceptance")
CL_MAX_BAND = (1.3, 1.7)                 # row 1: the ledger band of airfoil_cl_max (spec 7.1a)
CM0_BAND = (-0.10, -0.04)                # row 3: the ledger band of airfoil_cm0
RECORD_CL_MAX_CLEAN = 1.35               # row 2: r0's clean wing maximum lift
SU2_TOL_SLOPE, SU2_TOL_CL0, SU2_TOL_CLMAX = 0.05, 0.05, 0.10      # row 5: slope +-5 %, lift at zero angle, maximum lift
LINEAR_RANGE_DEG = (-6.0, 6.0)           # the lift curve is fitted by a straight line between these angles
# gross-error check of the digitized points (added row 6; not a spec row)
TOL_ALPHA0_DEG = 1.0                     # zero-lift angle against thin-airfoil theory
SLOPE_RATIO_RANGE = (0.85, 1.15)         # lift-curve slope over 2 pi per radian
# Raymer Fig. 12.8, p. 271, as the library's chapter notes describe it (the figure itself is not in the notes)
FIG_12_8_RATIO_ZERO_SWEEP = 0.9          # every curve starts at 0.9 at zero leading-edge sweep
FIG_12_8_BLUNT_AT_60_DEG = 0.55          # "about 0.55" at 60 deg for the bluntest curve (delta y >= 2.5)
DELTA_Y_PER_T_C = 26.0                   # Table 12.1, p. 271: NACA four-digit sections, delta y = 26 t/c (percent chord)
MACH_NO_CORRECTION = 0.2                 # Fig. 12.9, p. 272: the Mach correction is zero at M = 0.2
EVIDENCE_CLASS = ("independent of Stage 1 and of the library (measured data), but read through a third party's "
                  "digitization that was not checked against the report")
XFOIL_ALPHA_UP, XFOIL_ALPHA_DOWN = (0, 20), (0, -18)       # two sweeps from zero, 1 degree steps
SU2_QUEUE_ALPHA_DEG = (-12, -8, -4, 0, 4, 8, 10, 12, 14, 16)


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- the digitized points ------------------------------------------------------------------------------------
def parse_digitized(text):
    """The four blocks of one file of the archive: {"alpha_cl": {set: [(alpha deg, cl)]}, "alpha_cm": {set:
    [(alpha deg, cm about the quarter chord)]}, "cl_cd": {set: [(cl, cd)]}, "cl_cmac": {set: [(cl, cm about the
    aerodynamic centre)]}}. In the file's first block sets 1 to 6 are lift and 7 to 12 moment; in the second, sets
    1 to 6 are drag and 7 to 12 moment. A set that "does not exist" is left out. The third block (drag
    interpolated by the digitizer onto the lift points) is not read."""
    out = {"alpha_cl": {}, "alpha_cm": {}, "cl_cd": {}, "cl_cmac": {}}
    names, block, current = (("alpha_cl", "alpha_cm"), ("cl_cd", "cl_cmac")), -1, None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        words = line.split()
        if line.lstrip().lower().startswith(("alpha,", "cl,")):       # a block's heading
            block += 1
            current = None
        elif words[:2] == ["Data", "set"]:
            current = None                                             # the set number is on the next line
        elif len(words) == 1 and words[0].isdigit() and lines[i - 1].split() == ["Data", "set"]:
            k = int(words[0])
            current = out[names[block][0 if k <= 6 else 1]].setdefault(k, []) if block < 2 else None
        elif current is not None and len(words) == 2:
            current.append((float(words[0]), float(words[1])))
    return {name: {k: v for k, v in sets.items() if v} for name, sets in out.items()}


def load_section(section):
    """The digitized points of a section, from the file the source record names for it."""
    entry = yaml.safe_load(SOURCE.read_text())["sections"][section]
    if entry["file"] is None:
        raise ValueError(f"{section}: {entry['status']}: {' '.join(entry['reason'].split())}")
    return parse_digitized((DATA / entry["file"]).read_text())


# ---- step 1: Reynolds and Mach numbers ---------------------------------------------------------------------------
def chord_reynolds_mach(V, chord, atm):
    """Re = rho V c / mu and M = V / a for a speed (ft/s), a chord (ft) and an ISA state (conceptual.units.isa)."""
    return {"reynolds": atm["rho"] * V * chord / atm["mu"], "mach": V / atm["a"]}


def reynolds_table(d, L):
    """Reynolds and Mach numbers at the root, mean and tip chord of the record d for: the clean stall at sea level
    at W0, the stall at the mission altitude at the start of the loiter, and the loiter and cruise-out speeds of
    the record's mission (the leg's mean true airspeed)."""
    h = L["mission_altitude_ft"]
    leg = {m["segment"]: m for m in d["mission"]}
    S = d["wing"]["area"]
    stall_alt = perf.stall_speed(leg["loiter"]["W_start"] / S, isa(h)["rho"], d["CL_max"]["clean"]) / KT
    conditions = [("stall, sea level, W0", d["performance"]["V_stall_clean_kt"], 0.0),
                  ("stall, mission altitude, start of loiter", stall_alt, h),
                  ("loiter, mission altitude", leg["loiter"]["V_kt"], h),
                  ("cruise out, mission altitude", leg["cruise_out"]["V_kt"], h)]
    chords = [("root", d["wing"]["root_chord"]), ("mean", d["wing"]["mac"]), ("tip", d["wing"]["tip_chord"])]
    return [dict(condition=name, station=station, V_kt=V_kt, altitude_ft=alt, chord_ft=c,
                 **chord_reynolds_mach(V_kt * KT, c, isa(alt)))
            for name, V_kt, alt in conditions for station, c in chords]


def nearest_reynolds(reynolds, tabulated):
    """The tabulated Reynolds number nearest by ratio (smallest |ln(Re / Re_tab)|)."""
    return min(tabulated, key=lambda r: abs(math.log(reynolds / r)))


def interpolate_log_reynolds(reynolds, pairs):
    """A value at a Reynolds number, straight line in ln(Re) between the tabulated pairs [(Re, value)]. Outside
    the table: None (nothing is extrapolated)."""
    pairs = sorted(pairs)
    for (r1, v1), (r2, v2) in zip(pairs, pairs[1:]):
        if r1 <= reynolds <= r2:
            return v1 + (v2 - v1) * math.log(reynolds / r1) / math.log(r2 / r1)
    return None


# ---- step 2: what is read off a set of points ----------------------------------------------------------------
def line_fit(points, alpha_range):
    """Least-squares straight line cl = cl0 + a alpha through the points with alpha inside alpha_range (deg):
    slope per degree, lift at zero angle, zero-lift angle and the root-mean-square distance of the points from
    the line (the reading scatter)."""
    lo, hi = alpha_range
    pts = [(a, c) for a, c in points if lo <= a <= hi]
    alpha, cl = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    slope, cl0 = np.polyfit(alpha, cl, 1)
    rms = float(np.sqrt(np.mean((cl - (cl0 + slope * alpha)) ** 2)))
    return {"n_points": len(pts), "slope_per_deg": float(slope), "cl_at_zero": float(cl0),
            "alpha_zero_lift_deg": float(-cl0 / slope), "rms_residual": rms}


def section_summary(lift, moment, drag):
    """The section characteristics of one set: lift = [(alpha deg, cl)], moment = [(alpha deg, cm about the
    quarter chord)] or None, drag = [(cl, cd)] or None. Maximum and minimum lift are the highest and lowest
    points as they are (no fairing). The lowest point counts as a turning point only if the set goes on to a
    more negative angle; otherwise the set does not show the negative stall."""
    top, bottom = max(lift, key=lambda p: p[1]), min(lift, key=lambda p: p[1])
    out = {"n_points": len(lift), "cl_max": top[1], "alpha_cl_max_deg": top[0],
           "cl_max_is_a_turning_point": top[0] < max(a for a, _ in lift),
           "cl_min": bottom[1], "alpha_cl_min_deg": bottom[0],
           "cl_min_is_a_turning_point": bottom[0] > min(a for a, _ in lift),
           "fit": line_fit(lift, LINEAR_RANGE_DEG), "cm_c4_linear_range": None, "cm_n_points": 0,
           "cd_min": None, "cl_at_cd_min": None}
    if moment:
        cm = [c for a, c in moment if LINEAR_RANGE_DEG[0] <= a <= LINEAR_RANGE_DEG[1]]
        out.update(cm_c4_linear_range=sum(cm) / len(cm), cm_n_points=len(cm), cm_min=min(cm), cm_max=max(cm))
    if drag:
        low = min(drag, key=lambda p: p[1])
        out.update(cd_min=low[1], cl_at_cd_min=low[0])
    return out


def measured_sets(section):
    """Every smooth and rough set of the section with its Reynolds number (the source record's) and summary."""
    data, entry = load_section(section), yaml.safe_load(SOURCE.read_text())["sections"][section]
    rows = []
    for k, meta in entry["sets"].items():
        if meta["reynolds"] is None:
            continue                                      # the split-flap set is not used
        rows.append({"set": k, "reynolds": meta["reynolds"], "surface": meta["surface"],
                     "summary": section_summary(data["alpha_cl"][k], data["alpha_cm"].get(k + 6), data["cl_cd"].get(k)),
                     "lift": data["alpha_cl"][k], "moment": data["alpha_cm"].get(k + 6, []), "drag": data["cl_cd"].get(k, [])})
    return rows


# ---- gross-error check: thin-airfoil theory ---------------------------------------------------------------------
def thin_airfoil_alpha0_deg(camber_slope, n=4000):
    """Zero-lift angle of a thin section from its camber-line slope dz/dx(x), 0 <= x <= 1:
    alpha_0L = -(1/pi) integral_0^pi dz/dx (cos theta - 1) d theta, x = (1 - cos theta)/2
    (classical thin-airfoil theory; Anderson APD 2.5 gives the lift slope 2 pi per radian). Midpoint rule."""
    theta = (np.arange(n) + 0.5) * math.pi / n
    slope = camber_slope(0.5 * (1.0 - np.cos(theta)))
    return math.degrees(-float(np.sum(slope * (np.cos(theta) - 1.0))) / n)


def naca4_camber_slope(m, p):
    """dz/dx of the NACA four-digit mean line with maximum camber m at chord station p:
    2 m (p - x)/p^2 ahead of p and 2 m (p - x)/(1 - p)^2 behind it."""
    return lambda x: np.where(np.asarray(x) < p, 2.0 * m * (p - x) / p ** 2, 2.0 * m * (p - x) / (1.0 - p) ** 2)


def digitization_check(summary):
    """The fitted zero-lift angle and slope of a set against thin-airfoil theory for the 4415's mean line
    (4 % camber at 40 % chord). It can catch a wrong file, a shifted axis or a wrong scale; it says nothing about
    the maximum lift."""
    theory = thin_airfoil_alpha0_deg(naca4_camber_slope(0.04, 0.4))
    ratio = math.degrees(summary["fit"]["slope_per_deg"]) / (2.0 * math.pi)
    diff = summary["fit"]["alpha_zero_lift_deg"] - theory
    return {"alpha0_thin_airfoil_deg": theory, "alpha0_difference_deg": diff, "slope_over_2pi": ratio,
            "ok": abs(diff) <= TOL_ALPHA0_DEG and SLOPE_RATIO_RANGE[0] <= ratio <= SLOPE_RATIO_RANGE[1]}


# ---- step 3: wing maximum lift ----------------------------------------------------------------------------------
def leading_edge_sweep_deg(root_chord, tip_chord, span):
    """Leading-edge sweep of a straight-tapered wing whose quarter-chord line is unswept:
    tan(sweep) = (c_root - c_tip)/4 / (b/2)."""
    return math.degrees(math.atan(0.25 * (root_chord - tip_chord) / (0.5 * span)))


def wing_cl_max(cl_max_section, L, le_sweep_deg=0.0):
    """Clean wing maximum lift from the section's by Raymer (12.15), p. 270 (0.9 cl_max cos(sweep), quarter chord
    unswept) and by (12.16), p. 272, at zero leading-edge sweep (ratio 0.9 of Fig. 12.8, no Mach correction at or
    below M 0.2); flapped values by (12.21), p. 278, and Table 12.2 as Stage 1 (uav._cl_max). The entry
    `clean_12_16_at_le_sweep_rough` is a straight line between the two values the library's notes give for the
    bluntest curve of Fig. 12.8 (0.9 at 0 deg, about 0.55 at 60 deg): a sensitivity, not a reading of the figure."""
    stage1 = uav._cl_max(dict(L, airfoil_cl_max=cl_max_section))
    ratio = FIG_12_8_RATIO_ZERO_SWEEP + (FIG_12_8_BLUNT_AT_60_DEG - FIG_12_8_RATIO_ZERO_SWEEP) * le_sweep_deg / 60.0
    return {"section_cl_max": cl_max_section, "clean_12_15": aero.wing_cl_max(cl_max_section),
            "clean_12_16_zero_sweep": cl_max_section * FIG_12_8_RATIO_ZERO_SWEEP,
            "le_sweep_deg": le_sweep_deg, "clean_12_16_at_le_sweep_rough": cl_max_section * ratio,
            "delta_y_percent_chord": DELTA_Y_PER_T_C * L["wing_t_c"], **stage1}


def refly(built, cl_max_section, moved=None):
    """The built aircraft of r0 (wing area, tanks and fuel of the record; measurement.info_gap.Built) with the
    section maximum lift replaced, and optionally other ledger values (`moved`): hours on station on the record's
    fuel, the loiter speed of that mission (every sub-step is at or above 1.3 V_stall clean, R17, by the speed
    choice of uav._leg_speed), stall speeds, take-off and landing distance over 50 ft. Nothing is re-sized."""
    theta = dict(moved or {}, airfoil_cl_max=float(cl_max_section))
    hours, reason = built.hours_detail(theta)
    W0 = built.w0_for(theta)
    state, L = built.build(theta, loiter_h=hours, W0=W0)
    leg = {m[0]: m for m in state["mission"]}
    S, alt = built.S_record, isa(L["mission_altitude_ft"])
    stall_alt = perf.stall_speed(leg["loiter"][1] / S, alt["rho"], state["clmax"]["clean"])
    takeoff, landing = built.field_lengths(theta)
    return {"airfoil_cl_max": float(cl_max_section), "CL_max": state["clmax"], "W0_lb": W0,
            "hours_on_station": hours, "reason": reason,
            "loiter_speed_kt": leg["loiter"][3] / KT, "loiter_top_speed_kt": leg["loiter"][7] / KT,
            "loiter_floor_fraction": leg["loiter"][4],
            "cruise_out_speed_kt": leg["cruise_out"][3] / KT, "cruise_out_floor_fraction": leg["cruise_out"][4],
            "cruise_back_speed_kt": leg["cruise_back"][3] / KT, "cruise_back_floor_fraction": leg["cruise_back"][4],
            "V_stall_clean_sl_kt": perf.stall_speed(W0 / S, isa(0.0)["rho"], state["clmax"]["clean"]) / KT,
            "V_stall_clean_loiter_start_kt": stall_alt / KT,
            "floor_speed_loiter_start_kt": L["speed_over_stall"] * stall_alt / KT,
            "takeoff_ft": takeoff, "landing_ft": landing}


# ---- verdicts ------------------------------------------------------------------------------------------------------
def verdict_band(value, band):
    return "pass" if band[0] <= value <= band[1] else "outside the band"


def verdict_wing(measured_route, record):
    """Row 2: a measured route below the record's value is a finding for the closing re-record r1 (P9)."""
    return "finding for r1" if measured_route < record else "pass (not lower)"


def compare_computed(computed, measured):
    """A computed polar's summary against the measured one with the tolerances of the spec's row 5: slope within
    +-5 %, lift at zero angle within +-0.05, maximum lift within +-0.10."""
    slope = computed["fit"]["slope_per_deg"] / measured["fit"]["slope_per_deg"] - 1.0
    cl0 = computed["fit"]["cl_at_zero"] - measured["fit"]["cl_at_zero"]
    top = computed["cl_max"] - measured["cl_max"]
    within = {"slope": abs(slope) <= SU2_TOL_SLOPE, "cl_at_zero": abs(cl0) <= SU2_TOL_CL0, "cl_max": abs(top) <= SU2_TOL_CLMAX}
    return {"slope_relative_difference": slope, "cl_at_zero_difference": cl0, "cl_max_difference": top,
            "within": within, "all_within": all(within.values())}


# ---- optional third source: XFOIL (PD-6) ---------------------------------------------------------------------
def parse_xfoil_polar(text):
    """The rows of an XFOIL polar file (PACC): alpha, CL, CD and CM (about the quarter chord)."""
    rows, started = [], False
    for line in text.splitlines():
        if line.strip().startswith("------"):
            started = True
        elif started and len(line.split()) >= 5:
            a, cl, cd, _, cm = (float(x) for x in line.split()[:5])
            rows.append({"alpha_deg": a, "cl": cl, "cd": cd, "cm": cm})
    return rows


def xfoil_available():
    """(True, version) if xfoil and xvfb-run are installed. The Debian build stops with a floating-point
    exception when its plotting is switched off, so it is run with plotting on under a virtual display."""
    if not (shutil.which("xfoil") and shutil.which("xvfb-run")):
        return False, None
    version = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "xfoil"], capture_output=True, text=True, check=False)
    return True, version.stdout.strip() or "unknown"


def xfoil_polar(digits, reynolds, mach, keep=None):
    """One XFOIL polar of the NACA section `digits`: free transition (Ncrit 9, the program's default), two sweeps
    from 0 deg in 1 deg steps. Returns the rows sorted by angle; an angle that did not converge is missing. keep:
    a folder that receives the two polar files as XFOIL wrote them."""
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, (a0, a1) in (("up", XFOIL_ALPHA_UP), ("down", XFOIL_ALPHA_DOWN)):
            step = 1 if a1 > a0 else -1
            commands = (f"NACA {digits}\nPANE\nOPER\nVISC {reynolds:.0f}\nMACH {mach:.4f}\nITER 200\nPACC\n{name}.txt\n\n"
                        f"ASEQ {a0} {a1} {step}\nPACC\n\nQUIT\n")
            subprocess.run(["xvfb-run", "-a", "xfoil"], input=commands, capture_output=True, text=True, check=False,
                           cwd=tmp, timeout=600)
            path = Path(tmp) / f"{name}.txt"
            text = path.read_text() if path.exists() else ""
            if keep is not None:
                (Path(keep) / f"naca{digits}_re{reynolds:.0f}_{name}.txt").write_text(text)
            rows += parse_xfoil_polar(text)
    unique = {r["alpha_deg"]: r for r in rows}             # 0 deg is in both sweeps
    return [unique[a] for a in sorted(unique)]


def xfoil_summary(rows):
    """section_summary of an XFOIL polar."""
    return section_summary([(r["alpha_deg"], r["cl"]) for r in rows], [(r["alpha_deg"], r["cm"]) for r in rows],
                           [(r["cl"], r["cd"]) for r in rows])


def run_xfoil(out, cases, log):
    """The XFOIL polars of the cases [(digits, Re, Mach)], or the reason they were not run."""
    ok, version = xfoil_available()
    if not ok:
        return {"status": "not run", "reason": "xfoil or xvfb-run is not installed in this container"}
    keep = out / "xfoil"
    keep.mkdir(exist_ok=True)
    polars = []
    for digits, reynolds, mach in cases:
        rows = xfoil_polar(digits, reynolds, mach, keep)
        n_asked = XFOIL_ALPHA_UP[1] - XFOIL_ALPHA_DOWN[1] + 1
        polars.append({"section": f"naca{digits}", "reynolds": reynolds, "mach": mach, "rows": rows,
                       "n_converged": len(rows), "n_asked": n_asked, "summary": xfoil_summary(rows) if len(rows) > 5 else None})
        log(f"xfoil NACA {digits} Re {reynolds:.2e}: {len(rows)} of {n_asked} angles converged")
    return {"status": "run", "program": "XFOIL (Debian package xfoil)", "version": version,
            "settings": "free transition, Ncrit 9 (default), 160 panels (default), viscous, 200 iterations",
            "label": "computed, third source (PD-6): no verdict rests on it", "polars": polars}


# ---- the package -------------------------------------------------------------------------------------------------
def acceptance_rows(res):
    """The spec's rows 1 to 5 and the two rows added here, each with the numbers its verdict follows from."""
    at, wing, m = res["section_at_stall"], res["wing"]["measured"], res["refly"]
    check, xf = res["digitization_check"], res["xfoil"]
    rough = res["roughness"]
    return [
        {"row": 1, "what": "section maximum lift, smooth, at the tabulated Reynolds number nearest the stall: inside the ledger band",
         "value": at["cl_max"], "band": list(CL_MAX_BAND), "reynolds": at["reynolds"],
         "verdict": "pass" if verdict_band(at["cl_max"], CL_MAX_BAND) == "pass" else "section rejected (PD-5)"},
        {"row": 2, "what": "wing clean maximum lift by (12.15) from the measured section value against the record's",
         "value": wing["clean_12_15"], "record": RECORD_CL_MAX_CLEAN,
         "hours_on_station": m["measured"]["hours_on_station"], "hours_on_station_record": m["record"]["hours_on_station"],
         "loiter_speed_kt": m["measured"]["loiter_speed_kt"], "loiter_speed_kt_record": m["record"]["loiter_speed_kt"],
         "verdict": verdict_wing(wing["clean_12_15"], RECORD_CL_MAX_CLEAN)},
        {"row": 3, "what": "section moment about the quarter chord against the ledger band of airfoil_cm0",
         "value": at["cm_c4_linear_range"], "band": list(CM0_BAND), "ledger_value": res["ledger"]["airfoil_cm0"],
         "verdict": "pass" if verdict_band(at["cm_c4_linear_range"], CM0_BAND) == "pass" else "finding for P4"},
        {"row": 4, "what": "standard roughness: a sensitivity", "cl_max_rough": rough["rough"]["cl_max"],
         "cl_max_smooth_same_reynolds": rough["smooth"]["cl_max"], "reynolds": rough["reynolds"],
         "cd_min_rough": rough["rough"]["cd_min"], "cd_min_smooth_same_reynolds": rough["smooth"]["cd_min"],
         "verdict": "reported, no verdict"},
        {"row": 5, "what": "SU2 validation row", "verdict": "not run", "reason": res["su2"]["reason"]},
        {"row": 6, "what": "added: the digitized lift curve against thin-airfoil theory (gross-error check of the source file)",
         "alpha0_difference_deg": check["alpha0_difference_deg"], "tolerance_deg": TOL_ALPHA0_DEG,
         "slope_over_2pi": check["slope_over_2pi"], "range": list(SLOPE_RATIO_RANGE),
         "verdict": "pass" if check["ok"] else "fail"},
        {"row": 7, "what": "added: XFOIL polars as a third source (PD-6)",
         "verdict": "reported, no verdict" if xf["status"] == "run" else "not run", "reason": xf.get("reason")},
    ]


def run(out, log):
    """The whole package; returns the result dict (also written to OUT/p2.json)."""
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P2 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    source = yaml.safe_load(SOURCE.read_text())
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "r0_cell_result": R0 / "cell_result.json",
             "r0_engine_table": R0 / "m250_table.json", "source_record": SOURCE,
             "digitized_4415": DATA / "142.ALL", "digitized_index": DATA / "NACA.LST"}
    res = {"inputs": dict(tree, command="python -m prelim.p2_section " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P2",
                          python=platform.python_version(), numpy=np.__version__, pyyaml=yaml.__version__,
                          matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()},
                          sha256={k: sha256(p) for k, p in files.items()}),
           "evidence_class": EVIDENCE_CLASS, "baseline": str(R0.relative_to(REPO)), "source": source}
    log(f"commit {tree['commit']}, clean tree; r0 design {res['inputs']['sha256']['r0_design'][:12]}")
    d, cell = load(R0 / "design_pusher.json"), load(R0 / "cell_result.json")
    L, entries = uav.load_ledger(R0 / "ledger.yaml")
    res["ledger"] = {k: L[k] for k in ("airfoil_cl_max", "airfoil_cm0", "wing_t_c", "speed_over_stall", "mission_altitude_ft",
                                         "flap_delta_cl_max", "flap_span_fraction", "takeoff_flap_fraction")}
    res["sections"] = {"wing": WING_SECTION, "tail": TAIL_SECTION,
                       "tail_data": {k: " ".join(str(v).split()) for k, v in source["sections"][TAIL_SECTION].items() if v}}

    # 1. Reynolds and Mach numbers from r0
    res["reynolds"] = reynolds_table(d, L)
    stall = next(r for r in res["reynolds"] if r["condition"] == "stall, sea level, W0" and r["station"] == "mean")
    log(f"stall at sea level, mean chord: Re {stall['reynolds']:.3e}, Mach {stall['mach']:.3f}")

    # 2. the measured section data
    sets = measured_sets(WING_SECTION)
    res["measured"] = sets
    smooth = [s for s in sets if s["surface"] == "smooth"]
    re_near = nearest_reynolds(stall["reynolds"], [s["reynolds"] for s in smooth])
    near = next(s for s in smooth if s["reynolds"] == re_near)
    scatter = near["summary"]["fit"]["rms_residual"]
    at_altitude = next(r for r in res["reynolds"] if r["condition"].startswith("stall, mission altitude") and r["station"] == "mean")
    res["section_at_stall"] = dict(near["summary"], set=near["set"], reynolds=re_near, stall_reynolds=stall["reynolds"],
                                   stall_reynolds_mission_altitude=at_altitude["reynolds"],
                                   lowest_tabulated_reynolds=min(s["reynolds"] for s in smooth),
                                   reading_scatter=scatter, cl_max_minus_two_scatter=near["summary"]["cl_max"] - 2.0 * scatter)
    pairs = [(s["reynolds"], s["summary"]["cl_max"]) for s in smooth]
    res["reynolds_sensitivity"] = {
        "cl_max_interpolated_at_stall_reynolds": interpolate_log_reynolds(stall["reynolds"], pairs),
        "by_station": [{"condition": r["condition"], "station": r["station"], "reynolds": r["reynolds"],
                        "cl_max_interpolated": interpolate_log_reynolds(r["reynolds"], pairs)}
                       for r in res["reynolds"] if r["condition"].startswith("stall")],
        "note": "straight line in ln(Re) between the tabulated sets; None below the lowest or above the highest set"}
    rough = next(s for s in sets if s["surface"] != "smooth")
    res["roughness"] = {"reynolds": rough["reynolds"], "rough": rough["summary"],
                        "smooth": next(s["summary"] for s in smooth if s["reynolds"] == rough["reynolds"]),
                        "wing_clean_12_15_rough": aero.wing_cl_max(rough["summary"]["cl_max"])}
    res["digitization_check"] = digitization_check(near["summary"])
    log(f"NACA 4415, set {near['set']} (Re {re_near:.1e}, smooth): cl_max {near['summary']['cl_max']:.3f}, "
        f"cm c/4 {near['summary']['cm_c4_linear_range']:.4f}, scatter {scatter:.3f}")

    # 3. wing maximum lift, and the built aircraft flown again
    sweep = leading_edge_sweep_deg(d["wing"]["root_chord"], d["wing"]["tip_chord"], d["wing"]["span"])
    interp = res["reynolds_sensitivity"]["cl_max_interpolated_at_stall_reynolds"]
    res["wing"] = {"record": wing_cl_max(L["airfoil_cl_max"], L, sweep),
                   "measured": wing_cl_max(near["summary"]["cl_max"], L, sweep),
                   "measured_minus_two_scatter": wing_cl_max(res["section_at_stall"]["cl_max_minus_two_scatter"], L, sweep),
                   "interpolated_at_stall_reynolds": wing_cl_max(interp, L, sweep) if interp else None,
                   "stall_mach": stall["mach"], "mach_correction_applies": stall["mach"] > MACH_NO_CORRECTION,
                   "r7_stall_clause_floor": RECORD_CL_MAX_CLEAN * (d["performance"]["V_stall_clean_kt"] / L["stall_speed_kt"]) ** 2}
    built = info_gap.Built(R0 / "design_pusher.json")
    corner = cell["modes"]["endurance"]["worst_at_h1"]
    res["refly"] = {"record": refly(built, L["airfoil_cl_max"]),
                    "measured": refly(built, near["summary"]["cl_max"]),
                    "measured_minus_two_scatter": refly(built, res["section_at_stall"]["cl_max_minus_two_scatter"]),
                    "interpolated_at_stall_reynolds": refly(built, interp) if interp else None,
                    "band_low_end": refly(built, entries["airfoil_cl_max"]["band"][0]),
                    "corner_h1_record": dict(refly(built, corner["moved"]["airfoil_cl_max"], corner["moved"]),
                                             hours_in_cell_record=corner["hours"]),
                    "corner_h1_measured": refly(built, near["summary"]["cl_max"], corner["moved"]),
                    "need_h": {"nominal_r5": uav.load_ledger(uav.LEDGER)[0]["loiter_h"], "guarantee_r5": L["r5_robust_hours"]}}
    for k in ("record", "measured", "band_low_end"):
        r = res["refly"][k]
        log(f"refly {k}: section cl_max {r['airfoil_cl_max']:.3f}, wing {r['CL_max']['clean']:.3f}, "
            f"{r['hours_on_station']:.3f} h, loiter {r['loiter_speed_kt']:.2f} kt")

    # 4. SU2 (not run) and XFOIL (optional)
    res["su2"] = {"status": "not run",
                  "reason": "owner default O-1: the Colab notebook is not started; P2 closes on measured data (PD-6)",
                  "case_files": "none written",
                  "queue": [{"section": WING_SECTION, "reynolds": s["reynolds"], "mach": stall["mach"], "alpha_deg": a,
                             "turbulence_model": "to be fixed in the SU2 case spec (spec 7.1)"}
                            for s in smooth[:2] for a in SU2_QUEUE_ALPHA_DEG]}
    cases = [("4415", s["reynolds"], stall["mach"]) for s in smooth] + [("0012", s["reynolds"], stall["mach"]) for s in smooth[:2]]
    res["xfoil"] = run_xfoil(out, cases, log)
    if res["xfoil"]["status"] == "run":
        for p in res["xfoil"]["polars"]:
            match = next((s for s in smooth if p["section"] == WING_SECTION and s["reynolds"] == p["reynolds"]), None)
            p["against_measured"] = compare_computed(p["summary"], match["summary"]) if match and p["summary"] else None
    res["acceptance"] = acceptance_rows(res)
    _write(out, res, t0, own)
    log(", ".join(f"row {a['row']} {a['verdict']}" for a in res["acceptance"]) + f" ({time.time() - t0:.0f} s)")
    return res


def _write(out, res, t0, own):
    """OUT/p2.json, with the state of the tree at the end of the run next to the one at its start."""
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == res["inputs"]["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p2.json").write_text(json.dumps(info_gap._json_safe(res), indent=1, default=float))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the figures of the report (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and figures from OUT/p2.json")
    a = ap.parse_args(argv)
    out = (REPO / a.out).resolve()
    if not a.report_only:
        t0 = time.time()
        lines = []

        def log(msg):
            lines.append(f"[{time.time() - t0:7.0f} s] {msg}")
            print(lines[-1], flush=True)
            if out.exists():
                (out / "run.log").write_text("\n".join(lines) + "\n")
        run(out, log)
    if a.report:
        from prelim import p2_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p2_report.write_figures(out, figures)
        report.write_text(p2_report.report_text(out))


if __name__ == "__main__":
    main()

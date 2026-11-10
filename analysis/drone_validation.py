"""Recorded run of validation rows V6a to V6d (docs/specs/task10_drone_sizing.md section 9).

    python -m analysis.drone_validation --out runs/drone/validation/2026-11-08 \
        --doc docs/validation/2026-11-08_task10_v6.md

Every check is computed with the committed drone package; the tolerances are the spec's (with
addenda 1 to 3) and are constants below. Exit code 1 if any hard row fails, else 0.
Rows not run are listed with the reason; V6f always runs, V6e when SU2 results exist.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from analysis import drone_polar
from drone import evaluate, geometry, ledger, naca, section, vlm
from geometry import airfoils

ROOT = Path(__file__).resolve().parents[1]
WARREN = ROOT / "data/validation/warren12.yaml"
E387 = ROOT / "data/validation/e387_uiuc.yaml"
NOMINAL = {"family": "drone", "span_m": 2.0, "aspect_ratio": 10.0, "taper_ratio": 0.6,
           "battery_fraction": 0.30, "camber_pct": 4.0, "thickness_pct": 12.0, "fidelity": "low",
           "tag": "v6"}

# tolerances (relative unless stated), from the spec and its addenda; not to be changed here
TOL_E = 0.01
TOL_HELMBOLD = 0.03
TOL_IDENTITY = 1e-9
TOL_LL100 = 0.01
TOL_WARREN = 0.02
TOL_LATTICE_AERO = 0.01
TOL_LATTICE_ENDURANCE = 0.02
TOL_CLOSURE = 1e-9
TOL_ENERGY = 1e-9
TOL_ENDURANCE_FORM = 1e-6
TOL_MASS_SUM = 1e-9
TOL_V6E_CLA = 0.05
TOL_V6E_CD = 0.20
TOL_V6E_CLMAX = 0.10
TOL_V6E_MESH = 0.05
CL_BAND = (0.3, 0.9)

NOT_RUN_V6E = ("V6e", "SU2 on the E387 at Re 2e5 and 3e5 against UIUC polars",
               "no SU2 E387 result.json files found")
NOT_RUN_V6G = ("V6g", "Ultra Stick 25e CL_alpha and CD0", "Ultra Stick data not retrieved")


def helmbold(ar):
    return 2.0 * math.pi * ar / (2.0 + math.sqrt(ar * ar + 4.0))


def lifting_line(ar):
    return 2.0 * math.pi * ar / (ar + 2.0)


def row(rows, name, measured, reference, tol, verdict=None, kind="rel", note=""):
    """kind rel: deviation = measured/reference - 1; abs: measured - reference. tol None: report."""
    dev = (measured / reference - 1.0) if kind == "rel" else (measured - reference)
    if verdict is None:
        verdict = "report" if tol is None else ("pass" if abs(dev) < tol else "fail")
    rows.append({"name": name, "measured": measured, "reference": reference, "deviation": dev,
                 "tolerance": tol, "verdict": verdict, "note": note})


def v6a(rows):
    p = geometry.elliptic(span=4.0, aspect_ratio=8.0, n_nodes=41)
    d = vlm.derivatives(p, level="fine")
    r = vlm.solve(p, math.radians(4.0), level="fine")
    row(rows, "V6a elliptic AR 8 fine: e at 4 deg vs 1", r["e"], 1.0, TOL_E)
    row(rows, "V6a elliptic AR 8 fine: CL_alpha vs Helmbold", d["CL_alpha"], helmbold(8.0), TOL_HELMBOLD)
    ar = geometry.wing_dict(p)["AR"]
    ident = r["CL"] ** 2 / (math.pi * ar * r["e"])
    row(rows, "V6a elliptic AR 8 fine: CDi vs CL^2/(pi AR_planform e)", r["CDi"], ident,
        TOL_IDENTITY, kind="abs", note="absolute difference")
    p100 = geometry.elliptic(span=100.0, aspect_ratio=100.0, n_nodes=41)
    row(rows, "V6a elliptic AR 100 fine: CL_alpha vs 2 pi AR/(AR+2)",
        vlm.derivatives(p100, level="fine")["CL_alpha"], lifting_line(100.0), TOL_LL100)
    # reported, not gated
    rect = geometry.tapered(100.0, 100.0, 1.0)
    row(rows, "V6a (report) rectangular AR 100 fine: CL_alpha vs 2 pi AR/(AR+2)",
        vlm.derivatives(rect, level="fine")["CL_alpha"], lifting_line(100.0), None)
    for lv in ("coarse", "medium"):
        dl = vlm.derivatives(p, level=lv)
        el = vlm.solve(p, math.radians(4.0), level=lv)["e"]
        row(rows, f"V6a (report) elliptic AR 8 {lv}: CL_alpha vs Helmbold", dl["CL_alpha"],
            helmbold(8.0), None)
        row(rows, f"V6a (report) elliptic AR 8 {lv}: e vs 1", el, 1.0, None)


def v6b(rows):
    w = yaml.safe_load(WARREN.read_text())["warren12"]
    pending = w.get("moment_reference_x") == "pending"
    x_ref = 0.0 if pending else float(w["moment_reference_x"])
    s = w["semispan"]
    p = geometry.Planform(span=2.0 * s, eta=[0.0, 1.0], chord=[w["root_chord"], w["tip_chord"]],
                          x_le=[0.0, s * math.tan(math.radians(w["sweep_le_deg"]))], x_ref=x_ref)
    d = vlm.derivatives(p, level="fine")
    row(rows, "V6b Warren-12 fine: CL_alpha vs benchmark", d["CL_alpha"], w["CL_alpha_per_rad"],
        TOL_WARREN)
    cm = d["Cm_alpha"] * geometry.wing_dict(p)["c_mac"] / w["reference_chord"]
    if pending:
        row(rows, "V6b Warren-12 fine: Cm_alpha (about root LE, reference chord 1.0) vs benchmark",
            cm, w["Cm_alpha_per_rad"], TOL_WARREN,
            verdict="pending (reference point not yet sourced)",
            note="not counted as pass or fail")
    else:
        row(rows, "V6b Warren-12 fine: Cm_alpha vs benchmark", cm, w["Cm_alpha_per_rad"], TOL_WARREN)


def v6c(rows):
    p = geometry.tapered(NOMINAL["span_m"], NOMINAL["aspect_ratio"], NOMINAL["taper_ratio"])
    fixed = ledger.load_all()
    res = {}
    for lv in ("coarse", "medium", "fine"):
        res[lv] = (vlm.derivatives(p, level=lv)["CL_alpha"],
                   vlm.solve(p, math.radians(4.0), lv)["e"],
                   evaluate.evaluate(NOMINAL, fixed, level=lv)["endurance_h"])
    names = ("CL_alpha", "e at 4 deg", "endurance_h")
    tols = (TOL_LATTICE_AERO, TOL_LATTICE_AERO, TOL_LATTICE_ENDURANCE)
    for i, (n, t) in enumerate(zip(names, tols)):
        row(rows, f"V6c nominal: {n}, medium vs fine", res["medium"][i], res["fine"][i], t)
    for i, n in enumerate(names):
        row(rows, f"V6c (report) nominal: {n}, coarse vs medium", res["coarse"][i],
            res["medium"][i], None)


def v6d(rows):
    fixed = ledger.load_all()
    out = evaluate.evaluate(NOMINAL, fixed)
    d, bat, rules = out["diagnostics"], fixed["battery"], fixed["rules"]
    row(rows, "V6d closure_residual below 1e-9", out["closure_residual"], 0.0, TOL_CLOSURE,
        kind="abs", note="absolute; the residual is relative by construction")
    usable = bat["depth_of_discharge"] * bat["pack_specific_energy_Wh_per_kg"] * 3600.0 \
        * out["masses"]["battery"]
    spent = d["P_cruise_W"] * out["endurance_h"] * 3600.0 + d["P_installed_W"] * rules["climb_allowance_s"]
    row(rows, "V6d energy balance: spent vs usable battery energy", spent, usable, TOL_ENERGY)
    closed = (usable - d["P_installed_W"] * rules["climb_allowance_s"]) / d["P_cruise_W"] / 3600.0
    row(rows, "V6d endurance_h vs closed form", out["endurance_h"], closed, TOL_ENDURANCE_FORM)
    row(rows, "V6d sum of masses vs mtow", sum(out["masses"].values()), out["mtow_kg"], TOL_MASS_SUM)


def _tunnel_run(polars, reynolds):
    for p in polars:
        if float(p["reynolds"]) == float(reynolds):
            return p
    raise ValueError(f"no tunnel run at Reynolds number {reynolds}")


def _usable(records):
    """The records drone_polar.polar keeps, as (alpha, cl, cd) sorted by alpha."""
    kept = [r for r in records if r["convergence"]["status"] in drone_polar.GOOD
            or drone_polar._cauchy_stopped(r)]
    kept.sort(key=lambda r: r["params"]["alpha_deg"])
    return ([r["params"]["alpha_deg"] for r in kept], [r["metrics"]["cl"] for r in kept],
            [r["metrics"]["cd"] for r in kept])


def _cd_ratio(cl_ref, cd_model, cd_ref):
    """(mean |cd_model / cd_ref - 1| over points with cl_ref in CL_BAND, points used)."""
    ok = (cl_ref >= CL_BAND[0]) & (cl_ref <= CL_BAND[1])
    return float(np.mean(np.abs(cd_model[ok] / cd_ref[ok] - 1.0))), int(ok.sum())


def v6e(rows, polars, su2):
    """SU2 against the tunnel at the tunnel's own angles; no interpolation in alpha."""
    for re in sorted(su2):
        run = _tunnel_run(polars, re)
        records = su2[re]
        t_alpha = np.asarray(run["alpha_deg"], dtype=float)
        for r in records:
            if not np.any(np.abs(t_alpha - r["params"]["alpha_deg"]) < 1e-6):
                raise ValueError(f"Re {re:.0f}: SU2 angle {r['params']['alpha_deg']} deg is not a "
                                 "tunnel angle; no interpolation")
        s = drone_polar.polar(records)
        alpha, cl, cd = (np.asarray(v, dtype=float) for v in _usable(records))
        idx = [int(np.argmin(np.abs(t_alpha - a))) for a in alpha]
        t_cl, t_cd = np.asarray(run["cl"], dtype=float)[idx], np.asarray(run["cd"], dtype=float)[idx]
        tag = f"{round(re)}"
        row(rows, f"V6e cl_alpha Re {tag}", float(np.polyfit(alpha, cl, 1)[0]),
            float(np.polyfit(alpha, t_cl, 1)[0]), TOL_V6E_CLA,
            note=f"slope over {len(alpha)} matched angles, SU2 and tunnel at the same angles; "
                 f"flags {s.flags}")
        m, n = _cd_ratio(t_cl, cd, t_cd)
        row(rows, f"V6e cd ratio Re {tag}", m, 0.0, TOL_V6E_CD, kind="abs",
            note=f"{n} points with tunnel cl in [0.3, 0.9] of {len(alpha)} matched")
        t_clmax = float(np.max(run["cl"]))
        if "not_peaked" in s.flags:
            row(rows, f"V6e cl_max Re {tag}", float(np.max(cl)), t_clmax, None, verdict="report",
                note="SU2 angles stop below stall, so its cl_max is the largest computed cl, "
                     "not a maximum")
        else:
            row(rows, f"V6e cl_max Re {tag}", s.cl_max, t_clmax, TOL_V6E_CLMAX)


def v6e_mesh(rows, medium_records, fine_records, old_medium_records=None):
    """Gated: smoothed medium against fine, same mesher (decision 11). Reported, not gated: the
    medium polar before and after the mesher's tangent smoothing, which is what the fix moved."""
    cds = [float(drone_polar.polar(r).cd_of_cl(0.6)) for r in (medium_records, fine_records)]
    row(rows, "V6e mesh medium vs fine, cd at cl 0.6", cds[1], cds[0], TOL_V6E_MESH,
        note="measured = fine, reference = medium; both on the smoothed mesher (decision 11)")
    if old_medium_records:
        old = float(drone_polar.polar(old_medium_records).cd_of_cl(0.6))
        row(rows, "V6e mesher fix, medium before vs after smoothing, cd at cl 0.6", cds[0], old,
            None, note="measured = smoothed medium, reference = recorded medium (runs/e387)")


def v6f(rows, polars, fixed):
    """Low-fidelity closed forms against the tunnel, reported and not gated."""
    x, y, _ = airfoils.load("e387")
    c = airfoils.camber_thickness(*airfoils.dense_loop(x, y, 801))
    camber_pct, thick_pct = 100.0 * c["max_camber"], 100.0 * c["max_thickness"]
    alpha_l0_model = naca.zero_lift_angle(camber_pct, 100.0 * c["camber_position"])
    base = (f"E387 measured camber {camber_pct:.1f} % at {100.0 * c['camber_position']:.0f} %, "
            f"thickness {thick_pct:.1f} %")
    for run in polars:
        if run["nominal_reynolds"] not in (1e5, 2e5, 3e5):
            continue
        re = float(run["reynolds"])
        tag = f"{round(re)}"
        model = section.low_fidelity(camber_pct, thick_pct, re, fixed)
        tun = section.from_polar(run["alpha_deg"], run["cl"], run["cd"], f"e387 run {run['run']}")
        row(rows, f"V6f cl_alpha Re {tag}", model.cl_alpha_per_deg, tun.cl_alpha_per_deg, None,
            note=f"per degree; {base}")
        row(rows, f"V6f alpha_L0 Re {tag}", math.degrees(alpha_l0_model), math.degrees(tun.alpha_L0),
            None, kind="abs",
            note=f"degrees; model alpha_L0 uses the measured camber position, whereas low_fidelity "
                 f"hard-codes 40 % inside naca.zero_lift_angle; {base}")
        t_cl = np.asarray(run["cl"], dtype=float)
        t_cd = np.asarray(run["cd"], dtype=float)
        m, n = _cd_ratio(t_cl, np.asarray(model.cd_of_cl(t_cl), dtype=float), t_cd)
        row(rows, f"V6f cd ratio Re {tag}", m, 0.0, None, kind="abs",
            note=f"{n} tunnel points with cl in [0.3, 0.9]; model cd is a constant; {base}")
        row(rows, f"V6f cl_max Re {tag}", model.cl_max, tun.cl_max, None, note=base)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def commit():
    try:
        head = (ROOT / ".git/HEAD").read_text().strip()
        if head.startswith("ref: "):
            ref = ROOT / ".git" / head[5:]
            if ref.exists():
                return ref.read_text().strip()
            for line in (ROOT / ".git/packed-refs").read_text().splitlines():
                if line.endswith(head[5:]):
                    return line.split()[0]
            return "unknown"
        return head
    except OSError:
        return "unknown"


def fmt(x):
    return "-" if x is None else f"{x:.6g}"


def write_doc(path, rec):
    L = [f"# Task 10 validation V6a to V6d, {rec['date']}", "",
         "## What was run", "",
         (f"`python -m analysis.drone_validation` at commit `{rec['commit']}` computed rows V6a to V6d "
         "of docs/specs/task10_drone_sizing.md section 9 (with addenda 1 to 3) with the committed "
         f"drone package. Lattice levels used: {', '.join(rec['lattice_levels'])}. The numbers below are "
         "copied from `v6.json` in the run directory, which also holds the nominal parameters and the "
         "ledger file hashes. Tolerances are the spec's and are not changed by the script. "
         f"Overall hard-row result: **{rec['overall']}**."), "",
         ("Verdicts: pass and fail are checked against the tolerance; report is not gated; "
          "pending is not counted."), "",
         "| Check | Measured | Reference | Deviation | Tolerance | Verdict |",
         "|---|---|---|---|---|---|"]
    for r in rec["checks"]:
        L.append(f"| {r['name']} | {fmt(r['measured'])} | {fmt(r['reference'])} | "
                 f"{fmt(r['deviation'])} | {fmt(r['tolerance'])} | {r['verdict']} |")
    for rid, what, why in rec["not_run_rows"]:
        L.append(f"| {rid} {what} | not run: {why} | - | - | - | not run |")
    L.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--doc", required=True)
    ap.add_argument("--date", default="2026-11-08")
    ap.add_argument("--su2-dir", default="runs/e387")
    ap.add_argument("--smooth-dir", default="runs/e387_smooth",
                    help="medium cases rerun on the smoothed mesher, the V6e mesh row's medium side")
    a = ap.parse_args(argv)
    t0 = time.time()
    rows = []
    for f in (v6a, v6b, v6c, v6d):
        f(rows)
    polars = yaml.safe_load(E387.read_text())["polars"]
    v6f(rows, polars, ledger.load_all())
    groups = {}
    for fpath in sorted(Path(a.su2_dir).glob("**/result.json")):
        rec_ = json.loads(fpath.read_text())
        if rec_["params"].get("airfoil") == "e387":
            groups.setdefault(rec_["params"].get("mesh_level"), {}).setdefault(
                rec_["params"]["reynolds"], []).append(rec_)
    smooth = [json.loads(p.read_text()) for p in sorted(Path(a.smooth_dir).glob("**/result.json"))]
    smooth = [r for r in smooth if r["params"].get("airfoil") == "e387"
              and r["params"].get("mesh_level") == "medium" and r["params"]["reynolds"] == 203800.0]
    not_run = []
    if groups.get("medium"):
        v6e(rows, polars, groups["medium"])             # the tunnel rows use the medium level only
        fine = groups.get("fine", {}).get(203800.0, [])
        if smooth and fine:
            v6e_mesh(rows, smooth, fine, groups["medium"].get(203800.0))
        else:
            not_run.append(("V6e mesh", "medium vs fine mesh at Re 203800",
                            "no smoothed-medium and fine pair of records at Re 203800"))
    else:
        not_run.append(NOT_RUN_V6E)
    not_run.append(NOT_RUN_V6G)
    failed = [r["name"] for r in rows if r["verdict"] == "fail"]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / "data/drone").glob("*.yaml"))}
    hashes[str(WARREN.relative_to(ROOT))] = sha(WARREN)
    hashes[str(E387.relative_to(ROOT))] = sha(E387)
    rec = {"date": a.date, "commit": commit(), "lattice_levels": {k: list(v) for k, v in vlm.LEVELS.items()},
           "nominal_params": NOMINAL, "ledger_hashes": hashes, "checks": rows,
           "not_run": [{"id": i, "what": w, "reason": r} for i, w, r in not_run],
           "overall": "FAIL" if failed else "PASS", "failed": failed,
           "wall_time_s": round(time.time() - t0, 2)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "v6.json").write_text(json.dumps(rec, indent=2) + "\n")
    rec["not_run_rows"] = not_run
    rec["lattice_levels"] = [f"{k} {v[0]}x{v[1]}" for k, v in vlm.LEVELS.items()]
    write_doc(a.doc, rec)
    for r in rows:
        print(f"{r['verdict']:8s} {r['name']}: {fmt(r['measured'])} vs {fmt(r['reference'])} "
              f"dev {fmt(r['deviation'])}")
    print("overall:", rec["overall"], "wall", rec["wall_time_s"], "s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

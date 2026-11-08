"""Recorded run of validation rows V6a to V6d (docs/specs/task10_drone_sizing.md section 9).

    python -m analysis.drone_validation --out runs/drone/validation/2026-11-08 \
        --doc docs/validation/2026-11-08_task10_v6.md

Every check is computed with the committed drone package; the tolerances are the spec's (with
addenda 1 to 3) and are constants below. Exit code 1 if any hard row fails, else 0.
Rows V6e to V6g are listed as "not run" with the reason.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import yaml

from drone import evaluate, geometry, ledger, vlm

ROOT = Path(__file__).resolve().parents[1]
WARREN = ROOT / "data/validation/warren12.yaml"
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

NOT_RUN = [
    ("V6e", "SU2 on the E387 at Re 2e5 and 3e5 against UIUC polars",
     "needs the SU2 airfoil cases (T10.8b), not yet run"),
    ("V6f", "low-fidelity closed forms against the E387 data",
     "needs the E387 polars; retrieval pending"),
    ("V6g", "Ultra Stick 25e CL_alpha and CD0",
     "Ultra Stick data not retrieved"),
]


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
    for rid, what, why in NOT_RUN:
        L.append(f"| {rid} {what} | not run: {why} | - | - | - | not run |")
    L.append("")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--doc", required=True)
    ap.add_argument("--date", default="2026-11-08")
    a = ap.parse_args(argv)
    t0 = time.time()
    rows = []
    for f in (v6a, v6b, v6c, v6d):
        f(rows)
    failed = [r["name"] for r in rows if r["verdict"] == "fail"]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / "data/drone").glob("*.yaml"))}
    hashes[str(WARREN.relative_to(ROOT))] = sha(WARREN)
    rec = {"date": a.date, "commit": commit(), "lattice_levels": {k: list(v) for k, v in vlm.LEVELS.items()},
           "nominal_params": NOMINAL, "ledger_hashes": hashes, "checks": rows,
           "not_run": [{"id": i, "what": w, "reason": r} for i, w, r in NOT_RUN],
           "overall": "FAIL" if failed else "PASS", "failed": failed,
           "wall_time_s": round(time.time() - t0, 2)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "v6.json").write_text(json.dumps(rec, indent=2) + "\n")
    rec["lattice_levels"] = [f"{k} {v[0]}x{v[1]}" for k, v in vlm.LEVELS.items()]
    write_doc(a.doc, rec)
    for r in rows:
        print(f"{r['verdict']:8s} {r['name']}: {fmt(r['measured'])} vs {fmt(r['reference'])} "
              f"dev {fmt(r['deviation'])}")
    print("overall:", rec["overall"], "wall", rec["wall_time_s"], "s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

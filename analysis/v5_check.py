"""Task 9 validation gate V5 on the nominal inlet3r runs (spec section 9).

    python -m analysis.v5_check --runs runs/dev/2026-11-03_inlet3r_v5 --out docs/validation/2026-11-03_inlet3r_v5.md

V5a (hard): Euler, shock-1 angle (V1 station method) and the wall plateau p/p_inf and M on each ramp
against the oblique-shock chain, V1 tolerances. V5b (report): Euler recovery_total against the
analytic three-oblique-plus-normal-shock value. V5c (hard): laminar NS, medium against fine,
recovery_total and q_peak inside the V4m tolerances. V5d (hard, analytic): the unconstrained optimum
of the chain has equal upstream normal Mach numbers (Oswatitsch). V5e (hard): atmosphere formula
against the table. Writes the markdown report and a json next to it.
"""
import argparse
import gzip
import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from physics.atmosphere import ussa1976
from physics.constants import ATMOSPHERE_TABLE
from physics.shock import normal, oblique
from postprocess import surface
from postprocess.validation import GRID_TOL, oblique_shock_check
from worker.make_case import make

TOL_BETA_DEG, TOL_RATIO = 0.5, 0.02          # V1
MIDDLE = 0.6                                 # plateau: middle 60 percent of each ramp


def chain(thetas, M=4.0):
    """Oblique-shock chain: per ramp (M_after, p/p_inf, M_n upstream), and the total recovery with a
    terminal normal shock."""
    out, p, r = [], 1.0, 1.0
    for th in thetas:
        s = oblique(M, math.radians(th))
        out.append({"M_n": M * math.sin(s["beta"]), "beta_deg": math.degrees(s["beta"])})
        p, r, M = p * s["p_ratio"], r * s["p0_ratio"], s["M2"]
        out[-1].update(M=M, p_ratio=p)
    return out, r * normal(M)["p0_ratio"]


def staged(case_dir, tmp):
    """Rebuild the case folder (mesh from params, as the record says) with the gunzipped outputs."""
    params = json.loads((case_dir / "params.json").read_text())
    make(params, tmp)
    for f in ("surface_flow.dat", "flow.dat", "history.csv"):
        if (case_dir / f"{f}.gz").exists():
            with gzip.open(case_dir / f"{f}.gz", "rb") as src, open(tmp / f, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return params


def v5a_v5b(case_dir):
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        params = staged(case_dir, tmp)
        th = [params[f"theta{i}_deg"] for i in (1, 2, 3)]
        ref, rec_ref = chain(th)
        geometry = json.loads((tmp / "geometry.json").read_text())
        surf = surface.load(tmp)
        fs = surface.freestream(params)
        shock1 = oblique_shock_check(tmp, th[0], mach=4.0, stations=(0.04, 0.08), p_inf=fs["p"])
    body = surf["body"]
    corners = [0.0, geometry["X1"], geometry["X2"], geometry["P"][0]]
    rows, ok = [], abs(shock1["beta_deg"] - shock1["beta_ref_deg"]) <= TOL_BETA_DEG
    for i in range(3):
        a, b = corners[i], corners[i + 1]
        mid = (body["x"] > a + (1 - MIDDLE) / 2 * (b - a)) & (body["x"] < b - (1 - MIDDLE) / 2 * (b - a))
        p_ratio, mach = float(body["p"][mid].mean() / fs["p"]), float(body["M"][mid].mean())
        e_p, e_m = p_ratio / ref[i]["p_ratio"] - 1, mach / ref[i]["M"] - 1
        ok &= abs(e_p) <= TOL_RATIO and abs(e_m) <= TOL_RATIO
        rows.append({"ramp": i + 1, "nodes": int(mid.sum()), "p_ratio": p_ratio, "p_ratio_ref": ref[i]["p_ratio"],
                     "p_rel": e_p, "M": mach, "M_ref": ref[i]["M"], "M_rel": e_m})
    rec = json.loads((case_dir / "result.json").read_text())["metrics"]["recovery_total"]
    return {"pass": bool(ok), "shock1": {"beta_deg": shock1["beta_deg"], "beta_ref_deg": shock1["beta_ref_deg"]},
            "ramps": rows}, {"recovery_total": rec, "analytic": rec_ref, "rel": rec / rec_ref - 1}


def v5c(medium, fine):
    m = json.loads((medium / "result.json").read_text())["metrics"]
    f = json.loads((fine / "result.json").read_text())["metrics"]
    out, ok = {}, True
    for k, tol in GRID_TOL.items():
        rel = m[k] / f[k] - 1
        ok &= abs(rel) <= tol
        out[k] = {"medium": m[k], "fine": f[k], "rel": rel, "tol": tol}
    return {"pass": bool(ok), **out}


def v5d():
    res = minimize(lambda t: -chain(t)[1], [7, 7, 7], method="Nelder-Mead",
                   options={"xatol": 1e-8, "fatol": 1e-12, "maxiter": 5000})
    links, rec = chain(res.x)
    mn = [l["M_n"] for l in links]
    spread = (max(mn) - min(mn)) / min(mn)
    return {"pass": spread <= 1e-3, "angles_deg": list(res.x), "recovery": rec, "M_n": mn, "spread": spread}


def v5e():
    rows = []
    for z, row in ATMOSPHERE_TABLE.items():
        T, p = ussa1976(float(z))
        rows.append({"km": z, "T_rel": T / row["T"] - 1, "p_rel": p / row["p"] - 1})
    return {"pass": all(abs(r["T_rel"]) <= 1e-4 and abs(r["p_rel"]) <= 1e-4 for r in rows), "rows": rows}


def verdict(x):
    return "PASS" if x else "FAIL"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default="runs/dev/2026-11-03_inlet3r_v5")
    ap.add_argument("--out", default="docs/validation/2026-11-03_inlet3r_v5.md")
    a = ap.parse_args()
    runs = Path(a.runs)
    a5, b5 = v5a_v5b(runs / "nominal_euler_medium")
    c5, d5, e5 = v5c(runs / "nominal_ns_medium", runs / "nominal_ns_fine"), v5d(), v5e()
    res = {"V5a": a5, "V5b": b5, "V5c": c5, "V5d": d5, "V5e": e5}
    Path(a.out).with_suffix(".json").write_text(json.dumps(res, indent=1) + "\n")
    L = [f"# Task 9 validation gate V5 (inlet3r, nominal 7/7/7, Mach 4.0, 30 km, 300 K)", "",
         f"Generated by `python -m analysis.v5_check --runs {a.runs}`. Runs: `{a.runs}/` (SU2 v8.2.0 release binary "
         "on the container, development runs). Spec: `docs/specs/task9_inlet3r_envelope.md` section 9.", "",
         "| Check | Verdict | Measured |", "|---|---|---|"]
    s1 = a5["shock1"]
    L.append(f"| V5a shock-1 angle (hard, +-0.5 deg) | {verdict(abs(s1['beta_deg'] - s1['beta_ref_deg']) <= TOL_BETA_DEG)} | "
             f"{s1['beta_deg']:.3f} deg against {s1['beta_ref_deg']:.3f} deg |")
    for r in a5["ramps"]:
        L.append(f"| V5a ramp {r['ramp']} plateau (hard, 2%) | {verdict(abs(r['p_rel']) <= TOL_RATIO and abs(r['M_rel']) <= TOL_RATIO)} | "
                 f"p/p_inf {r['p_ratio']:.4f} against {r['p_ratio_ref']:.4f} ({r['p_rel']:+.2%}); "
                 f"M {r['M']:.4f} against {r['M_ref']:.4f} ({r['M_rel']:+.2%}); {r['nodes']} nodes |")
    L.append(f"| V5b Euler recovery_total (report) | REPORT | {b5['recovery_total']:.5f} against analytic "
             f"{b5['analytic']:.5f} ({b5['rel']:+.2%}) |")
    for k in GRID_TOL:
        c = c5[k]
        L.append(f"| V5c {k}, medium against fine (hard, {c['tol']:.0%}) | {verdict(abs(c['rel']) <= c['tol'])} | "
                 f"{c['medium']:.6g} against {c['fine']:.6g} ({c['rel']:+.2%}) |")
    L.append(f"| V5d Oswatitsch equal strength (hard, 1e-3) | {verdict(d5['pass'])} | normal Mach numbers "
             f"{', '.join(f'{m:.6f}' for m in d5['M_n'])} (spread {d5['spread']:.1e}) at angles "
             f"{', '.join(f'{x:.3f}' for x in d5['angles_deg'])} deg |")
    L.append(f"| V5e atmosphere formula vs table (hard, 1e-4) | {verdict(e5['pass'])} | "
             + "; ".join(f"{r['km']} km: T {r['T_rel']:+.1e}, p {r['p_rel']:+.1e}" for r in e5["rows"]) + " |")
    hard = [abs(s1['beta_deg'] - s1['beta_ref_deg']) <= TOL_BETA_DEG, a5["pass"], c5["pass"], d5["pass"], e5["pass"]]
    L += ["", f"Gate: {'PASS: every hard check passed' if all(hard) else 'FAIL: at least one hard check failed'}.", ""]
    Path(a.out).write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()

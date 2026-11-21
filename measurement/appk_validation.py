"""Mattingly App. K example against the book's figure readings, for the constant-cp fuel flow
("csh") and the MSH variable-cp fuel flow ("msh") side by side.

    python -m measurement.appk_validation --burner msh --out result.json

Cases are the same as tests/task12/test_turboprop_cycle.py (gamma_t = 1.3, see that file).
Tolerances were fixed in advance in docs/specs/task12_drone_conceptual_design.md section 7.1b
and are not tuned here: tau_t* +-0.015 abs; envelope F/m0 and S +-5 %; K.7 lapse +-0.015 abs;
K.9 minimum S within +-10 % of the book. Rows that fail are reported as FAIL.
"""
import argparse
import json
import math

from conceptual.units import isa
from measurement import turboprop_cycle as tc

TOL = {"tau_t_star": ("abs", 0.015), "envelope_F": ("rel", 0.05), "envelope_S": ("rel", 0.05),
       "lapse": ("abs", 0.015), "part_throttle_S": ("rel", 0.10)}
LIM = {"pi_c_max": 30.0, "Tt3_max": 1600.0}


def _row(group, label, book, model):
    kind, tol = TOL[group]
    dev = model - book if kind == "abs" else model / book - 1.0
    return {"group": group, "case": label, "book": book, "model": model, "deviation": dev,
            "tolerance_kind": kind, "tolerance": tol, "verdict": "PASS" if abs(dev) <= tol else "FAIL"}


def run(burner):
    k = dict(tc.BOOK_EXAMPLE, gamma_t=1.3, burner=burner)
    a25 = isa(25000.0)
    rows = []
    for pc, book in ((5, 0.64), (10, 0.56), (20, 0.50), (35, 0.447)):
        t = tc.optimum_tau_t(0.8, a25["T"], a25["p"], pc, k)
        rows.append(_row("tau_t_star", f"Fig K.4 pi_c={pc}", book, t))
    for pc, F, S in ((5, 158.0, 0.83), (17, 190.0, 0.60), (35, None, 0.535)):
        t = tc.optimum_tau_t(0.8, a25["T"], a25["p"], pc, k)
        dp = tc.design_point(0.8, a25["T"], a25["p"], pc, t, k)
        if F is not None:
            rows.append(_row("envelope_F", f"K.2 F/m0 pi_c={pc}", F, dp["F_per_m0"]))
        rows.append(_row("envelope_S", f"K.3 S pi_c={pc}", S, dp["S"]))
    ref = tc.design_point(0.8, a25["T"], a25["p"], 30, 0.6, k)
    ref["m0"] = 1.0
    sl = isa(0.0)
    F0 = tc.full_throttle(ref, 0.1, sl["T"], sl["p"], k, **LIM)["F"]
    for h, F in ((5000, 12800), (10000, 11600), (15000, 9500), (20000, 7700), (25000, 6200), (30000, 5000)):
        a = isa(h)
        model = tc.full_throttle(ref, 0.1, a["T"], a["p"], k, **LIM)["F"] / F0
        rows.append(_row("lapse", f"K.7 F/F_SL h={h} ft", F / 14000.0, model))
    a15 = isa(15000.0)
    for M0, book in ((0.3, 0.34), (0.5, 0.505), (0.8, 0.72)):
        top = tc.full_throttle(ref, M0, a15["T"], a15["p"], k, eta_prop_max=0.9, **LIM)
        best = math.inf
        for i in range(30, 101, 2):
            try:
                r = tc.off_design(ref, M0, a15["T"], a15["p"], top["Tt4"] * i / 100.0, k, 0.9)
            except ValueError:
                continue
            if r["F"] > 0.0:
                best = min(best, r["S"])
        rows.append(_row("part_throttle_S", f"K.9 min S M0={M0} (eta_prop_max 0.9)", book, best))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--burner", choices=("csh", "msh"), default="msh",
                    help="burner model to highlight; both are always computed")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = {"burners": {b: run(b) for b in ("csh", "msh")}, "tolerances": TOL, "requested": args.burner}
    res["summary"] = {b: {"pass": sum(r["verdict"] == "PASS" for r in rows), "total": len(rows)}
                      for b, rows in res["burners"].items()}
    with open(args.out, "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"{'case':44s} {'book':>8s} | {'csh':>8s} {'dev':>8s} {'':4s} | {'msh':>8s} {'dev':>8s}")
    for a, b in zip(res["burners"]["csh"], res["burners"]["msh"]):
        def d(r):
            return f"{r['deviation']:+.3f}" if r["tolerance_kind"] == "abs" else f"{r['deviation'] * 100:+.1f}%"
        print(f"{a['case']:44s} {a['book']:8.3f} | {a['model']:8.3f} {d(a):>8s} {a['verdict']:4s} | "
              f"{b['model']:8.3f} {d(b):>8s} {b['verdict']:4s}")
    print(res["summary"])


if __name__ == "__main__":
    main()

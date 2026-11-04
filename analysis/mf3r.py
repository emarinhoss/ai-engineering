"""Task 9 question 2: does the two-level model (Euler + Eckert, then laminar NS) reach a given held-out
error with fewer NS runs than a GP on NS runs alone?

Data (runs/pool3r/pool3r_table.csv): high fidelity = the converged NS pool points; low fidelity = all
converged Euler runs (the 159 high-fidelity points plus the 160-point second Sobol set), each with
Euler recovery_total and the Eckert q_peak on the Euler wall state. Outputs as in the replay:
y1 = recovery_total, y2 = log(q_peak_W_m2). Inputs: the six inputs scaled to [0, 1].

For each NS budget n and seed: n converged NS points drawn at random (seeded); held out = the other
converged NS points. Models, fitted per output on the same n points:
  single  surrogate.gp.GP on the n NS values;
  two     surrogate.mf_gp.TwoLevelGP with every Euler run as the low level (the whole low-fidelity
          pool is available, as the spec says) and the n NS runs as the high level.
Reported per (model, n, seed): rmse_recovery, rmse_q_rel (as in surrogate.replay), the fraction of
held-out values inside the 90 percent interval of a new run (latent variance plus fitted noise: the
GP's noise, or the discrepancy GP's noise for the two-level model; set after a one-seed trial showed the
first version compared the single GP's predictive interval with the two-level latent one), and rho for
the two-level model.
Also, once: the error of the raw low-fidelity value used as the prediction (no model, no NS runs).

    python -m analysis.mf3r --table runs/pool3r/pool3r_table.csv --out runs/pool3r/analysis/mf.csv
"""
import argparse
import csv
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np

from analysis.pool3r_table import INPUTS, load
from designs.make_pool3r import HIGH, LOW
from surrogate.gp import GP, Standardizer, scale_inputs
from surrogate.mf_gp import TwoLevelGP

BUDGETS = (8, 12, 16, 24, 32, 48, 64, 96)
Z90 = NormalDist().inv_cdf(0.95)


def arrays(rows):
    hf = [r for r in rows if r["set"] == "hf" and r["ns_status"] == "converged"]
    lf = [r for r in rows if r["lf_status"] == "converged"]
    X = lambda rs: scale_inputs(np.array([[r[k] for k in INPUTS] for r in rs]), list(zip(LOW, HIGH)))
    return {"XH": X(hf), "XL": X(lf),
            "yH": [np.array([r["ns_recovery_total"] for r in hf]), np.log([r["ns_q_peak_W_m2"] for r in hf])],
            "yLH": [np.array([r["lf_recovery_total"] for r in hf]), np.log([r["lf_q_peak_W_m2"] for r in hf])],
            "yL": [np.array([r["lf_recovery_total"] for r in lf]), np.log([r["lf_q_peak_W_m2"] for r in lf])]}


def errors(m, v, y, j):
    """Error metrics for output j (0 recovery, 1 log q) from predicted mean/variance m, v and truth y."""
    name = ("recovery", "q")[j]
    rmse = np.sqrt(np.mean((m - y) ** 2)) if j == 0 else np.sqrt(np.mean((np.exp(m - y) - 1) ** 2))
    return {("rmse_recovery" if j == 0 else "rmse_q_rel"): float(rmse),
            f"cov90_{name}": float(np.mean(np.abs(y - m) <= Z90 * np.sqrt(v)))}


def run(rows, budgets=BUDGETS, seeds=range(10)):
    A = arrays(rows)
    N = len(A["XH"])
    out = []
    for j in (0, 1):                                     # raw low-fidelity value as the prediction
        e = errors(A["yLH"][j], np.zeros(N), A["yH"][j], j)
        out.append({"model": "lf_raw", "n": 0, "seed": -1, "metric": next(iter(e)), "value": next(iter(e.values()))})
    lows = [GP().fit(A["XL"], Standardizer().fit(A["yL"][j]).transform(A["yL"][j]))
            for j in (0, 1)]                             # as TwoLevelGP fits it; depends only on the Euler data
    for seed in seeds:
        for n in budgets:
            sel = np.random.default_rng([seed, n]).choice(N, n, replace=False)
            held = np.setdiff1d(np.arange(N), sel)
            for j in (0, 1):
                y, yLH = A["yH"][j], A["yLH"][j]
                st = Standardizer().fit(y[sel])
                gp = GP().fit(A["XH"][sel], st.transform(y[sel]))
                m, v = gp.predict(A["XH"][held], noise=True)
                res = {"single": errors(st.inverse(m).numpy(), st.inverse_var(v).numpy(), y[held], j)}
                mf = TwoLevelGP().fit(A["XL"], A["yL"][j], A["XH"][sel], y[sel], yLH[sel], low=lows[j])
                m, v = mf.predict(A["XH"][held], noise=True)
                res["two"] = errors(m.numpy(), v.numpy(), y[held], j)
                res["two"][f"rho_{('recovery', 'q')[j]}"] = mf.rho
                for model, e in res.items():
                    out += [{"model": model, "n": n, "seed": seed, "metric": k, "value": val} for k, val in e.items()]
        print("seed", seed, "done", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default="runs/pool3r/pool3r_table.csv")
    ap.add_argument("--out", default="runs/pool3r/analysis/mf.csv")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--first-seed", type=int, default=0)
    a = ap.parse_args()
    rows = run(load(a.table), seeds=range(a.first_seed, a.first_seed + a.seeds))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("model", "n", "seed", "metric", "value"))
        w.writeheader()
        w.writerows(rows)


def summary(path):
    """Median over seeds per (model, n, metric)."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    keys = sorted({(r["model"], int(r["n"]), r["metric"]) for r in rows})
    return {f"{m}|{n}|{k}": float(np.median([float(r["value"]) for r in rows
                                              if (r["model"], int(r["n"]), r["metric"]) == (m, n, k)]))
            for m, n, k in keys}


if __name__ == "__main__":
    main()

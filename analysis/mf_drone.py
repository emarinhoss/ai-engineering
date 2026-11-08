"""Task 10 question 2 (T10.10c): does the two-level model (the VLM low-fidelity closure, then the SU2
section polar) reach a given held-out error with fewer SU2 designs than a GP on SU2 designs alone?

Data: low fidelity = the usable rows (empty gates and error) of the 192-point low pool
(runs/drone_pool_lf/2026-11-08/grid.csv, the analysis.drone_grid layout); high fidelity = the usable
rows (status complete, empty gates and error) of an analysis.pool_af_results results.csv. Outputs as
in surrogate.replay's drone family: y1 = endurance_h, y2 = log(mtow_kg). Inputs: the six
designs.make_pool_drone INPUTS scaled to [0, 1] with its LOW..HIGH box. The design is nested: the
SU2 pool designs are the first rows of pool_drone_lf192, so a high row is matched to the low row of
the same index, and the six inputs of the two must agree within 1e-6 or this raises.

For each budget n and seed: n usable high designs drawn at random (seeded); held out = the other
usable high designs. Models, fitted per output on the same n points:
  single  surrogate.gp.GP on the n high values;
  two     surrogate.mf_gp.TwoLevelGP with every usable low row as the low level and the n high
          designs as the high level.
Reported per (model, n, seed): rmse_endurance, rmse_mtow_rel (as in surrogate.replay), cov90_<name>,
the fraction of held-out values inside the 90 percent interval of a new run (latent variance plus
fitted noise, as analysis.mf3r), and rho for the two-level model.
Also, once: the error of the raw low-fidelity value used as the prediction (no model, no SU2 runs).

Budgets: (8, 12, 16, 24, 32) by default, clipped to at most (usable high designs - 4) so at least
four designs are held out; a clipped budget is listed in the notes. With fewer than 12 usable high
designs nothing is written: the analysis is "not run", never fitted on too little.

    python -m analysis.mf_drone --high runs/pool_af/<date>/results.csv --out runs/analysis/mf_drone.csv

Writes the CSV (model, n, seed, metric, value) and a record beside it (<out>.json: inputs and their
sha256, budgets, seeds, notes, commit).
"""
import argparse
import csv
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np

from analysis.drone_grid import git_commit, sha256
from designs.make_pool_drone import HIGH, INPUTS, LOW
from surrogate.gp import GP, Standardizer, scale_inputs
from surrogate.mf_gp import TwoLevelGP

BUDGETS = (8, 12, 16, 24, 32)
MIN_HIGH = 12                    # fewer usable high designs: not run
MIN_HELD = 4                     # held-out designs a budget must leave
TOL_INPUTS = 1e-6
NAMES = ("endurance", "mtow")
Z90 = NormalDist().inv_cdf(0.95)
LOW_POOL = "runs/drone_pool_lf/2026-11-08/grid.csv"


def read_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def usable_low(rows):
    return [r for r in rows if r["gates"] == "" and r["error"] == ""]


def usable_high(rows):
    return [r for r in rows if r["status"] == "complete" and r["gates"] == "" and r["error"] == ""]


def clip_budgets(budgets, n_high):
    """(kept budgets, notes): a budget must leave MIN_HELD held-out designs."""
    kept = tuple(n for n in budgets if n <= n_high - MIN_HELD)
    dropped = [n for n in budgets if n not in kept]
    note = (f"budgets {dropped} dropped: {n_high} usable high designs leave fewer than "
            f"{MIN_HELD} held out")
    notes = [note] if dropped else []
    return kept, notes


def arrays(low_rows, high_rows):
    """Scaled inputs and outputs [endurance_h, log mtow_kg] for the low level, the high level and the
    low level at the high designs (matched by index; inputs must agree within TOL_INPUTS)."""
    by_index = {int(r["index"]): r for r in low_rows}
    for r in high_rows:
        low = by_index.get(int(r["index"]))
        if low is None:
            raise ValueError(f"high design {r['index']} has no usable low-fidelity row")
        if any(abs(float(r[k]) - float(low[k])) > TOL_INPUTS for k in INPUTS):
            raise ValueError(f"index {r['index']}: high and low inputs differ by more than "
                             f"{TOL_INPUTS}; the two tables do not describe the same designs")
    lh = [by_index[int(r["index"])] for r in high_rows]

    def X(rs):
        return scale_inputs(np.array([[float(r[k]) for k in INPUTS] for r in rs]),
                            list(zip(LOW, HIGH)))

    def Y(rs):
        return [np.array([float(r["endurance_h"]) for r in rs]),
                np.log([float(r["mtow_kg"]) for r in rs])]
    return {"XH": X(high_rows), "XL": X(low_rows), "yH": Y(high_rows), "yLH": Y(lh),
            "yL": Y(low_rows)}


def errors(m, v, y, j):
    """Error metrics for output j (0 endurance, 1 log mtow) from predicted mean/variance m, v and
    truth y."""
    rmse = np.sqrt(np.mean((m - y) ** 2)) if j == 0 else np.sqrt(np.mean((np.exp(m - y) - 1) ** 2))
    return {("rmse_endurance" if j == 0 else "rmse_mtow_rel"): float(rmse),
            f"cov90_{NAMES[j]}": float(np.mean(np.abs(y - m) <= Z90 * np.sqrt(v)))}


def run(low_rows, high_rows, budgets=BUDGETS, seeds=range(10)):
    A = arrays(low_rows, high_rows)
    N = len(A["XH"])
    out = []
    for j in (0, 1):                                     # raw low-fidelity value as the prediction
        e = errors(A["yLH"][j], np.zeros(N), A["yH"][j], j)
        out.append({"model": "lf_raw", "n": 0, "seed": -1, "metric": next(iter(e)),
                    "value": next(iter(e.values()))})
    lows = [GP().fit(A["XL"], Standardizer().fit(A["yL"][j]).transform(A["yL"][j]))
            for j in (0, 1)]                 # as TwoLevelGP fits it; depends only on the low pool
    for seed in seeds:
        for n in budgets:
            sel = np.random.default_rng([seed, n]).choice(N, n, replace=False)
            held = np.setdiff1d(np.arange(N), sel)
            for j in (0, 1):
                y, yLH = A["yH"][j], A["yLH"][j]
                st = Standardizer().fit(y[sel])
                gp = GP().fit(A["XH"][sel], st.transform(y[sel]))
                m, v = gp.predict(A["XH"][held], noise=True)
                res = {"single": errors(st.inverse(m).numpy(), st.inverse_var(v).numpy(),
                                        y[held], j)}
                mf = TwoLevelGP().fit(A["XL"], A["yL"][j], A["XH"][sel], y[sel], yLH[sel],
                                      low=lows[j])
                m, v = mf.predict(A["XH"][held], noise=True)
                res["two"] = errors(m.numpy(), v.numpy(), y[held], j)
                res["two"][f"rho_{NAMES[j]}"] = mf.rho
                for model, e in res.items():
                    out += [{"model": model, "n": n, "seed": seed, "metric": k, "value": val}
                            for k, val in e.items()]
        print("seed", seed, "done", flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--low", default=LOW_POOL)
    ap.add_argument("--high", default="runs/pool_af/results.csv")
    ap.add_argument("--out", default="runs/analysis/mf_drone.csv")
    ap.add_argument("--budgets", type=int, nargs="+", default=list(BUDGETS))
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--first-seed", type=int, default=0)
    a = ap.parse_args(argv)
    low, high = usable_low(read_rows(a.low)), usable_high(read_rows(a.high))
    if len(high) < MIN_HIGH:
        print(f"not run: {len(high)} usable high-fidelity designs (need {MIN_HIGH})")
        return 0
    budgets, notes = clip_budgets(a.budgets, len(high))
    for note in notes:
        print("note:", note)
    seeds = range(a.first_seed, a.first_seed + a.seeds)
    rows = run(low, high, budgets=budgets, seeds=seeds)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("model", "n", "seed", "metric", "value"))
        w.writeheader()
        w.writerows(rows)
    record = {"commit": git_commit(), "low": a.low, "high": a.high,
              "sha256": {"low": sha256(a.low), "high": sha256(a.high), out.name: sha256(out)},
              "usable_low": len(low), "usable_high": len(high), "budgets": list(budgets),
              "seeds": list(seeds), "notes": notes}
    out.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
    return 0


def summary(path):
    """Median over seeds per (model, n, metric)."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    keys = sorted({(r["model"], int(r["n"]), r["metric"]) for r in rows})
    return {f"{m}|{n}|{k}": float(np.median([float(r["value"]) for r in rows
                                              if (r["model"], int(r["n"]), r["metric"]) == (m, n, k)]))
            for m, n, k in keys}


if __name__ == "__main__":
    raise SystemExit(main())

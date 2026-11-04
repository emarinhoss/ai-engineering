"""Task 9 question 1: does active learning beat LHS and random sampling in six dimensions?

Offline replay on the high-fidelity NS pool (runs/pool3r/pool3r_table.csv), as in Task 4
(surrogate/replay.py), with two differences that the six-input pool forces:
  1. Candidates are all 159 gate-passing pool points, failed runs included. Choosing a point that
     failed spends one NS run (n counts runs spent) and adds no objective value; the GPs are fitted
     on the converged points chosen so far. So a strategy that walks into failures pays for it.
  2. A fifth strategy, al_ehvi_feas, multiplies EHVI by the probability of convergence from
     surrogate.feasibility.Feasibility fitted on the labels of the points chosen so far (features as
     analysis.feas3r); until a failure has been chosen there is nothing to learn and the factor is 1.

Objectives and metrics as surrogate.replay: y1 = recovery_total, y2 = log q_peak; f = (-y1, y2) for
the hypervolume, reference point from all converged pool points. Strategies: random, lhs (a fresh LHS
in six dimensions at each budget, matched one-to-one to the nearest pool points), al_maxvar, al_ehvi,
al_ehvi_feas. All start from the same 12 random pool points per seed (2 x 6 inputs). Budgets 12 to 96.
Metrics at each budget, on the converged pool points not chosen: rmse_recovery, rmse_q_rel, cov90 of
both; and hv_regret = 1 - HV(converged chosen points) / HV(all converged pool points); n_failed = failed
runs among the chosen points.

    python -m analysis.replay3r --table runs/pool3r/pool3r_table.csv --out runs/pool3r/analysis/replay.csv \
        [--seeds 10 --first-seed 0]
"""
import argparse
import csv
from pathlib import Path
from statistics import NormalDist

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from scipy.stats import qmc

from analysis.feas3r import features
from analysis.pool3r_table import INPUTS, load
from designs.make_pool3r import HIGH, LOW
from surrogate.acquisition import argmax_ties, ehvi_mc, hypervolume_2d, max_variance, pareto_front, ref_point
from surrogate.feasibility import Feasibility
from surrogate.gp import GP, Standardizer, scale_inputs

STRATEGIES = ("random", "lhs", "al_maxvar", "al_ehvi", "al_ehvi_feas")
REPORT_AT = (12, 16, 24, 32, 48, 64, 80, 96)
N_INIT = 12
Z90 = NormalDist().inv_cdf(0.95)


class Pool:
    def __init__(self, rows):
        rows = [r for r in rows if r["set"] == "hf"]
        self.X = scale_inputs(np.array([[r[k] for k in INPUTS] for r in rows]), list(zip(LOW, HIGH)))
        self.feat = features(rows)
        self.ok = np.array([r["ns_status"] == "converged" for r in rows])
        self.F = np.full((len(rows), 2), np.nan)                     # objectives, minimisation form
        self.F[self.ok, 0] = [-r["ns_recovery_total"] for r, o in zip(rows, self.ok) if o]
        self.F[self.ok, 1] = np.log([r["ns_q_peak_W_m2"] for r, o in zip(rows, self.ok) if o])
        self.N = len(rows)
        self.ref = ref_point(self.F[self.ok])
        self.hv_true = hypervolume_2d(self.F[self.ok][pareto_front(self.F[self.ok])], self.ref)


def fit(P, sel):
    """One (GP, Standardizer) per output on the converged chosen points."""
    good = [i for i in sel if P.ok[i]]
    models = []
    for y in (-P.F[good, 0], P.F[good, 1]):
        st = Standardizer().fit(y)
        models.append((GP().fit(P.X[good], st.transform(y)), st))
    return models


def predict(models, idx, P, noise=False):
    out = []
    for gp, st in models:
        m, v = gp.predict(P.X[idx], noise=noise)
        out.append((st.inverse(m).numpy(), st.inverse_var(v).numpy(), v.numpy()))
    return out


def metrics(P, sel, models):
    good = np.array([i for i in sel if P.ok[i]])
    held = np.setdiff1d(np.flatnonzero(P.ok), sel)
    (m1, v1, _), (m2, v2, _) = predict(models, held, P, noise=True)
    y1, y2 = -P.F[held, 0], P.F[held, 1]
    F = P.F[good]
    return {"rmse_recovery": float(np.sqrt(np.mean((m1 - y1) ** 2))),
            "rmse_q_rel": float(np.sqrt(np.mean((np.exp(m2 - y2) - 1) ** 2))),
            "cov90_recovery": float(np.mean(np.abs(y1 - m1) <= Z90 * np.sqrt(v1))),
            "cov90_q": float(np.mean(np.abs(y2 - m2) <= Z90 * np.sqrt(v2))),
            "hv_regret": float(1 - hypervolume_2d(F[pareto_front(F)], P.ref) / P.hv_true),
            "n_failed": int(len(sel) - len(good))}


def select_next(name, P, sel, models, rng, seed):
    cand = np.setdiff1d(np.arange(P.N), sel)
    if name == "random":
        return int(rng.choice(cand))
    (m1, v1, s1), (m2, v2, s2) = predict(models, cand, P)
    var_sum = max_variance(s1, s2)
    if name == "al_maxvar":
        return int(cand[np.argmax(var_sum)])
    F = P.F[[i for i in sel if P.ok[i]]]
    score = ehvi_mc(-m1, v1, m2, v2, F, ref_point(F), seed=seed * 1000 + len(sel))
    labels = P.ok[sel].astype(float)
    if name == "al_ehvi_feas" and labels.min() == 0:                 # at least one failure seen
        score = score * Feasibility().fit(P.feat[sel], labels).predict(P.feat[cand]).numpy()
    return int(cand[argmax_ties(score, var_sum)])


def lhs_select(P, n, seed):
    design = qmc.LatinHypercube(d=6, optimization="random-cd", seed=seed * 1000 + n).random(n)
    rows, cols = linear_sum_assignment(cdist(design, P.X.numpy()))
    return list(cols[np.argsort(rows)])


def run_strategy(name, P, seed, init, n_max, report_at=REPORT_AT):
    budgets = [n for n in report_at if len(init) <= n <= n_max]
    out = []

    def record(n, sel):
        out.extend({"strategy": name, "seed": seed, "n": n, "metric": k, "value": v}
                   for k, v in metrics(P, sel, fit(P, sel)).items())

    if name == "lhs":
        for n in budgets:
            record(n, list(init) if n == len(init) else lhs_select(P, n, seed))
        return out
    sel, rng = list(init), np.random.default_rng([seed, 1])
    while True:
        n = len(sel)
        models = fit(P, sel) if (n in budgets or (name.startswith("al_") and n < n_max)) else None
        if n in budgets:
            out.extend({"strategy": name, "seed": seed, "n": n, "metric": k, "value": v}
                       for k, v in metrics(P, sel, models).items())
        if n >= n_max:
            return out
        sel.append(select_next(name, P, sel, models, rng, seed))


def run(rows, strategies=STRATEGIES, seeds=range(10), n_max=96, out_csv=None):
    P = Pool(rows)
    out = []
    for seed in seeds:
        init = np.random.default_rng(seed).choice(P.N, N_INIT, replace=False)
        for name in strategies:
            out += run_strategy(name, P, seed, init, n_max)
            print(f"seed {seed} {name} done", flush=True)
            if out_csv:
                Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
                with open(out_csv, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=("strategy", "seed", "n", "metric", "value"))
                    w.writeheader()
                    w.writerows(out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default="runs/pool3r/pool3r_table.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--n-max", type=int, default=96)
    a = ap.parse_args()
    run(load(a.table), seeds=range(a.first_seed, a.first_seed + a.seeds), n_max=a.n_max, out_csv=a.out)


if __name__ == "__main__":
    main()

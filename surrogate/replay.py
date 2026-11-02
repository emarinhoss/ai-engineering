"""Pool replay: compare sampling strategies offline against a pool of known (converged) runs.

Objective transform, defined once here:
  f1 = -recovery_total        (recovery is maximised, the code minimises)
  f2 = log(q_peak_W_m2)       (log: q spans a factor ~2, relative errors matter)
GP outputs are y1 = recovery_total and y2 = log(q_peak_W_m2), so f1 = -y1 and f2 = y2.

Strategies: random, lhs (offline space-filling, redrawn at every budget), al_ehvi,
al_maxvar. All four start from the same n_init random pool points for a given seed.

Surrogate: "gp" (surrogate.gp.GP, the default) or "mlp" (surrogate.mlp.MLPEnsemble, a deep
ensemble with the same interface; docs/specs/task4b_mlp_ensemble.md). Only the model changes.

CLI: python -m surrogate.replay --pool designs/pool_sobol96.csv --results RESULTS.csv \
        --out runs/replay/<date>/replay.csv [--model mlp]      (or --synthetic --out PATH)
"""
import argparse
import csv
import datetime
import time
from pathlib import Path
from statistics import NormalDist

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from scipy.stats import qmc

from designs.make_pool import HIGH, LOW
from surrogate.acquisition import (
    argmax_ties,
    ehvi_mc,
    hypervolume_2d,
    max_variance,
    pareto_front,
    ref_point,
)
from surrogate.gp import GP, Standardizer, scale_inputs
from surrogate.mlp import MLPEnsemble

MODELS = {"gp": GP, "mlp": MLPEnsemble}

BOUNDS = list(zip(LOW, HIGH))                     # (theta1, theta2) design box in degrees
STRATEGIES = ("random", "lhs", "al_ehvi", "al_maxvar")
REPORT_AT = (8, 12, 16, 20, 24, 32, 40, 48)
LEVELS = (0.5, 0.8, 0.9, 0.95)                    # nominal interval coverage levels
COLUMNS = ("strategy", "seed", "n", "metric", "value")
CONVERGED = ("converged", "stationary")


def to_objectives(pool):
    """Pool dict -> F (n, 2) in minimisation form [-recovery_total, log q_peak]."""
    return np.column_stack([-np.asarray(pool["recovery_total"], dtype=float),
                            np.log(np.asarray(pool["q_peak_W_m2"], dtype=float))])


def from_objectives(F):
    """Inverse of to_objectives: F (n, 2) -> dict(recovery_total, q_peak_W_m2)."""
    F = np.asarray(F, dtype=float)
    return {"recovery_total": -F[:, 0], "q_peak_W_m2": np.exp(F[:, 1])}


class Pool:
    """Pool arrays prepared once: unit-square inputs, objectives, true front hypervolume."""

    def __init__(self, pool):
        theta = np.column_stack([pool["theta1_deg"], pool["theta2_deg"]]).astype(float)
        self.X = scale_inputs(theta, BOUNDS)                        # torch (N, 2) in [0, 1]
        self.F = to_objectives(pool)
        self.N = len(self.F)
        self.ref = ref_point(self.F)                                # from the whole pool
        self.hv_true = hypervolume_2d(self.F[pareto_front(self.F)], self.ref)


def fit_models(P, sel, model="gp"):
    """One (model, Standardizer) per output, fitted on the selected pool points."""
    models = []
    for y in (-P.F[sel, 0], P.F[sel, 1]):                           # y1 = recovery, y2 = log q
        st = Standardizer().fit(y)
        models.append((MODELS[model]().fit(P.X[sel], st.transform(y)), st))
    return models


def predict(models, idx, P, noise=False):
    """Per output: (mean, variance) in original units and variance in standardised units."""
    out = []
    for gp, st in models:
        m, v = gp.predict(P.X[idx], noise=noise)
        out.append((st.inverse(m).numpy(), st.inverse_var(v).numpy(), v.numpy()))
    return out


def metrics_row(P, sel, models, step_seconds):
    """All metrics for one (strategy, seed, n) as a dict name -> value."""
    held = np.setdiff1d(np.arange(P.N), sel)
    (m1, v1, _), (m2, v2, _) = predict(models, held, P, noise=True)   # noise: observed values
    y1, y2 = -P.F[held, 0], P.F[held, 1]
    out = {"rmse_recovery": float(np.sqrt(np.mean((m1 - y1) ** 2))),
           "rmse_q_rel": float(np.sqrt(np.mean((np.exp(m2 - y2) - 1.0) ** 2)))}
    hv_sel = hypervolume_2d(P.F[sel][pareto_front(P.F[sel])], P.ref)
    out["hv_regret"] = (P.hv_true - hv_sel) / P.hv_true
    for level in LEVELS:
        z = NormalDist().inv_cdf(0.5 + level / 2)                   # central interval half-width
        pct = round(level * 100)
        out[f"cov{pct}_recovery"] = float(np.mean(np.abs(y1 - m1) <= z * np.sqrt(v1)))
        out[f"cov{pct}_q"] = float(np.mean(np.abs(y2 - m2) <= z * np.sqrt(v2)))
    out["step_seconds"] = step_seconds
    for name, (gp, _) in zip(("recovery", "q"), models):
        out.update({f"hyp_{name}_{k}": v for k, v in gp.hypers().items()})
    return out


def select_next(name, P, sel, models, rng, seed):
    """Index of the unselected pool point to add next (sequential strategies)."""
    cand = np.setdiff1d(np.arange(P.N), sel)
    if name == "random":
        return int(rng.choice(cand))
    (m1, v1, s1), (m2, v2, s2) = predict(models, cand, P)
    var_sum = max_variance(s1, s2)                                  # standardised variances
    if name == "al_maxvar":
        return int(cand[np.argmax(var_sum)])
    F_sel = P.F[sel]
    score = ehvi_mc(-m1, v1, m2, v2, F_sel, ref_point(F_sel), seed=seed * 1000 + len(sel))
    return int(cand[argmax_ties(score, var_sum)])


def lhs_select(P, n, seed):
    """Fresh maximin-style LHS of size n, matched one-to-one to the nearest distinct pool points."""
    design = qmc.LatinHypercube(d=2, optimization="random-cd", seed=seed * 1000 + n).random(n)
    cost = cdist(design, P.X.numpy())                               # (n, N) distances in the unit box
    rows, cols = linear_sum_assignment(cost)                        # min total distance, no repeats
    return list(cols[np.argsort(rows)])


def run_strategy(name, P, seed, init, n_max, report_at, model="gp"):
    budgets = [n for n in report_at if len(init) <= n <= n_max]
    rows, sel = [], list(init)

    def record(n, sel, models, secs):
        for metric, value in metrics_row(P, sel, models, secs).items():
            rows.append({"strategy": name, "seed": seed, "n": n, "metric": metric, "value": value})

    if name == "lhs":                                               # not sequential
        for n in budgets:
            t0 = time.perf_counter()
            sel = list(init) if n == len(init) else lhs_select(P, n, seed)
            secs = 0.0 if n == len(init) else time.perf_counter() - t0
            record(n, sel, fit_models(P, sel, model), secs)
        return rows
    rng, step_secs = np.random.default_rng([seed, 1]), 0.0
    while True:
        n, t0 = len(sel), time.perf_counter()
        active = name.startswith("al_")
        models = fit_models(P, sel, model) if (n in budgets or (active and n < n_max)) else None
        fit_secs = time.perf_counter() - t0
        if n in budgets:
            record(n, sel, models, step_secs)
        if n >= n_max:
            return rows
        t0 = time.perf_counter()
        sel.append(select_next(name, P, sel, models, rng, seed))
        step_secs = (fit_secs if active else 0.0) + time.perf_counter() - t0


def run(pool, strategies=STRATEGIES, seeds=range(10), n_init=8, n_max=40, report_at=REPORT_AT,
        out_csv=None, model="gp"):
    """Replay every strategy for every seed; returns rows and optionally writes a CSV."""
    P = Pool(pool)
    n_max = min(n_max, P.N - 1)                                     # keep held-out points
    rows = []
    for seed in seeds:
        init = np.random.default_rng(seed).choice(P.N, n_init, replace=False)  # same for all
        for name in strategies:
            rows += run_strategy(name, P, seed, init, n_max, report_at, model)
    if out_csv is not None:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
    return rows


def load_pool(pool_csv, results_csv, tol=1e-5):
    """Pool design + results table -> pool dict with only converged/stationary runs.

    Results rows are matched to pool points by (theta1, theta2) within tol degrees.
    """
    with open(pool_csv) as f:
        design = [(int(r["index"]), float(r["theta1_deg"]), float(r["theta2_deg"]))
                  for r in csv.DictReader(f)]
    with open(results_csv) as f:
        results = [r for r in csv.DictReader(f) if r["status"] in CONVERGED]
    out = {k: [] for k in ("index", "theta1_deg", "theta2_deg", "recovery_total", "q_peak_W_m2")}
    for i, t1, t2 in design:
        hit = [r for r in results
               if abs(float(r["theta1_deg"]) - t1) < tol and abs(float(r["theta2_deg"]) - t2) < tol]
        if hit:
            out["index"].append(i)
            out["theta1_deg"].append(t1)
            out["theta2_deg"].append(t2)
            out["recovery_total"].append(float(hit[0]["recovery_total"]))
            out["q_peak_W_m2"].append(float(hit[0]["q_peak_W_m2"]))
    return {k: np.array(v) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pool", default="designs/pool_sobol96.csv")
    ap.add_argument("--results", help="CSV: case_id,theta1_deg,theta2_deg,recovery_total,"
                                      "q_peak_W_m2,status")
    ap.add_argument("--synthetic", action="store_true", help="use the synthetic pool (test only)")
    ap.add_argument("--out", help="output CSV (default runs/replay/<date>/replay.csv; required "
                                  "with --synthetic so synthetic output never lands in runs/)")
    ap.add_argument("--seeds", type=int, default=10, help="number of seeds")
    ap.add_argument("--first-seed", type=int, default=0,
                    help="seeds are first-seed .. first-seed + seeds - 1 (to split a run over processes)")
    ap.add_argument("--n-max", type=int, default=40)
    ap.add_argument("--model", choices=sorted(MODELS), default="gp", help="surrogate (default gp)")
    a = ap.parse_args()
    if a.synthetic:
        if not a.out:
            ap.error("--synthetic needs an explicit --out")
        from surrogate.synthetic import make_pool
        pool = make_pool()
    else:
        if not a.results:
            ap.error("--results is required unless --synthetic")
        pool = load_pool(a.pool, a.results)
    out = a.out or f"runs/replay/{datetime.datetime.now().astimezone().date().isoformat()}/replay.csv"
    print(f"pool of {len(pool['index'])} points; model {a.model}; writing {out}")
    run(pool, seeds=range(a.first_seed, a.first_seed + a.seeds), n_max=a.n_max, out_csv=out, model=a.model)


if __name__ == "__main__":
    main()

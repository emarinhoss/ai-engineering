"""Online replay of six sampling strategies on the low-fidelity drone model (T10.10b).

    python -m analysis.replay_drone_online [--front runs/drone_grid/2026-11-08/front.csv]
        [--out runs/replay_drone_online/<date>/online.csv] [--seeds 10] [--n-init 8]
        [--n-max 40] [--candidates 4096]
        [--strategies random lhs al_ehvi al_maxvar al_ehvi_feas al_maxvar_feas]

The pool replay (surrogate.replay, family "drone") can only pick points someone already ran.
Here every pick is evaluated with the real low-fidelity model, drone.evaluate.evaluate, and is
scored against the exact front of the 9^6 grid (analysis.drone_grid, front.csv).

Objectives (as surrogate.replay, family "drone"), minimisation form:
    f1 = -endurance_h        f2 = log(mtow_kg)
The GPs model y1 = endurance_h and y2 = log(mtow_kg) on inputs scaled to the unit cube, each
standardised, exactly as surrogate.replay.fit_models does.

Regret: hv_regret = 1 - HV(Pareto front of the clean observed points) / HV(front.csv), both with
the reference point ref_point(front.csv). No observed point gives 1; the front itself gives 0.
front.csv is exact on the grid, not over the continuous box, so a point between grid nodes can
in principle beat it and give a slightly negative regret; that is reported, not clipped.

Candidates: every step draws a fresh scrambled Sobol set of `candidates` points over the design
box (candidate_set). The acquisition picks among them; nothing filters the set (no gate check,
no model, rule or person removes a candidate before the pick). The LLM never chooses a point.

Initial design: for each seed, the first n_init gate-passing points of the step-0 candidate set,
in order, evaluated with the real model; the same design for every strategy of that seed. The
draws rejected while building it are not counted in n (n_init is a clean design, like the pool
replay's); they are kept as labelled data for the feasibility model (label 0).

Gated picks: after the initial design, n counts evaluations, gated ones included. A pick that
fails a gate, or whose mass closure fails (ValueError), consumes one evaluation, is counted in
n_gated and enters no model and no hypervolume.

Strategies: random picks one candidate of the step's set uniformly; al_ehvi and al_maxvar fit the
two GPs on the clean observed points and pick the argmax of surrogate.replay.acquisition_pick
(Monte-Carlo EHVI with the variance-sum tiebreak, or the standardised variance sum), the rule
surrogate.replay.select_next uses on a pool. lhs is not sequential, as in surrogate.replay: at
each report budget n > n_init it evaluates a fresh scrambled LHS design of n points (random-cd)
over the box; at n = n_init it is the shared initial design.

al_ehvi_feas and al_maxvar_feas were added after the first online run
(runs/replay_drone_online/2026-11-08/, 10 seeds, n_init 8, n_max 40) showed both active strategies
losing to random and LHS by walking into gates: mean n_gated at n = 40 was 29.7 of 32 picks for
al_ehvi and 25.4 for al_maxvar, against 1.9 for random and 4.0 for lhs, and mean hv_regret 0.317
(al_ehvi) and 0.353 (al_maxvar) against 0.294 (random) and 0.271 (lhs). They are a fifth and sixth
strategy; the four above are unchanged, so the comparison that lost stays on the record. The rule
is the inlet study's al_ehvi_feas (analysis.replay3r): a surrogate.feasibility.Feasibility logistic
model on the inputs scaled to the unit cube, fitted before each pick on EVERY point evaluated so
far for that (strategy, seed): the initial design's clean points (label 1), the draws rejected
while building it (label 0), and every later pick (clean 1; gated or closure ValueError 0). Until at
least one 0 and one 1 exist the factor is 1. Each candidate's acquisition is multiplied by its
p(feasible): for al_ehvi_feas the EHVI and its variance-sum tiebreak both (otherwise an all-zero
EHVI would fall through to an unweighted tiebreak and ignore the model), for al_maxvar_feas the
standardised variance sum. The classifier never picks a point and removes no candidate; it weights.
The fit uses FEAS_STEPS = 1000 gradient steps instead of Feasibility's default 5000 (measured 0.6 s
mean, 1.0 s max per fit at 5000 against about 0.13 s at 1000; on 20-40 point test sets the 1000-step
probabilities rank the candidates as the 5000-step ones do, rank correlation >= 0.998, with the same
argmax, and are less sharp, max difference 0.18). surrogate.feasibility's defaults are unchanged.

Seeds: each random stream is numpy.random.default_rng([stream, seed, ...]) with its own stream
tag (candidates 0, random picks 1, lhs designs 2), so no two streams share a key:
    candidate_set(seed, step)  default_rng([0, seed, step])
    random picks               default_rng([1, seed])
    lhs design at budget n     default_rng([2, seed, n])

Metrics per (strategy, seed, n) at each report budget: hv_regret, n_clean, n_gated, the two GPs'
hyperparameters (hyp_endurance_*, hyp_mtow_*; GPs fitted on the clean points at that budget, for
every strategy), for the two _feas strategies p_feasible_of_pick (the mean p(feasible) the
model assigned to the picks made since the previous report; 1.0 where the factor was 1; with no
pick since the previous report, the value at the last pick, or 1.0 before any pick) and
step_seconds (seconds spent fitting, drawing candidates and scoring since the
previous report; the evaluations themselves are not counted). There is no held-out pool, so no
rmse or coverage. run() returns the reproducible rows only; step_seconds is a measurement that
differs between runs, so it is written to the CSV but left out of the returned rows.
"""
import argparse
import csv
import datetime
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from analysis.drone_grid import git_commit, sha256
from designs.make_pool_drone import HIGH, INPUTS, LOW
from drone import evaluate, ledger
from surrogate import replay
from surrogate.acquisition import (
    argmax_ties,
    ehvi_mc,
    hypervolume_2d,
    max_variance,
    pareto_front,
    ref_point,
)
from surrogate.feasibility import Feasibility
from surrogate.gp import scale_inputs

STRATEGIES = (*replay.STRATEGIES, "al_ehvi_feas", "al_maxvar_feas")
FAMILY = "drone"
BOUNDS = replay.FAMILIES[FAMILY].bounds
REPORT_AT = (8, 12, 16, 20, 24, 32, 40)
TIMING = ("step_seconds",)                 # measured, not reproducible: CSV only
CANDIDATE_STREAM, RANDOM_STREAM, LHS_STREAM = 0, 1, 2
FEAS_STEPS = 1000        # Feasibility's default 5000 SGD steps took 0.6-1.0 s per fit here
DEFAULT_FRONT = "runs/drone_grid/2026-11-08/front.csv"


def load_front(front_csv):
    """front.csv -> F (n, 2) = [-endurance_h, log(mtow_kg)]."""
    with open(front_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    return np.array([[-float(r["endurance_h"]), math.log(float(r["mtow_kg"]))] for r in rows])


def regret(observed_F, front_F, ref):
    """1 - HV(Pareto front of observed_F) / HV(front_F), both bounded by ref; 1.0 if empty."""
    obs = np.asarray(observed_F, dtype=float).reshape(-1, 2)
    if len(obs) == 0:
        return 1.0
    front_F = np.asarray(front_F, dtype=float)
    hv_front = hypervolume_2d(front_F[pareto_front(front_F)], ref)
    return 1.0 - hypervolume_2d(obs[pareto_front(obs)], ref) / hv_front


def candidate_set(seed, step, n):
    """n scrambled Sobol points over the drone box, fresh per (seed, step) and reproducible."""
    rng = np.random.default_rng([CANDIDATE_STREAM, seed, step])
    unit = qmc.Sobol(d=len(INPUTS), scramble=True, seed=rng).random(n)
    return qmc.scale(unit, LOW, HIGH)


def objectives(x, fixed):
    """Evaluate one design with the real model: [f1, f2], or None if gated or not closed."""
    params = dict(zip(INPUTS, map(float, x)))
    try:
        out = evaluate.evaluate(params, fixed)
    except ValueError:                     # mass closure failed: counted as gated
        return None
    if out["gates"]:
        return None
    return np.array([-out["endurance_h"], math.log(out["mtow_kg"])])


def initial_design(seed, fixed, n_init, candidates):
    """The first n_init gate-passing points of the step-0 candidate set, in order, and the draws
    rejected (gated or not closed) on the way: (X, F, rejected)."""
    X, F, rejected = [], [], []
    for x in candidate_set(seed, 0, candidates):
        f = objectives(x, fixed)
        if f is None:
            rejected.append(x)
        else:
            X.append(x)
            F.append(f)
            if len(X) == n_init:
                return X, F, rejected
    raise RuntimeError(f"seed {seed}: fewer than {n_init} gate-passing points among "
                       f"{candidates} step-0 candidates")


def fit(X, F):
    """The two GPs on clean points (raw inputs X, objectives F), as surrogate.replay."""
    return replay.fit_xy(scale_inputs(np.array(X), BOUNDS), np.array(F))


def p_feasible(labelled_X, labels, cands):
    """p(feasible) at each candidate from a Feasibility model on every labelled point so far
    (scaled inputs); all ones until at least one 0 and one 1 exist."""
    if min(labels) == max(labels):
        return np.ones(len(cands))
    model = Feasibility(steps=FEAS_STEPS).fit(scale_inputs(np.array(labelled_X), BOUNDS).numpy(),
                              np.array(labels, dtype=float))
    return model.predict(scale_inputs(cands, BOUNDS).numpy()).numpy()


def weighted_pick(name, predictions, F_obs, mc_seed, p):
    """acquisition_pick with each candidate's score (and the EHVI's tiebreak) multiplied by p."""
    (m1, v1, s1), (m2, v2, s2) = predictions
    var_sum = max_variance(s1, s2) * p
    if name == "al_maxvar_feas":
        return int(np.argmax(var_sum))
    score = ehvi_mc(-m1, v1, m2, v2, F_obs, ref_point(F_obs), seed=mc_seed) * p
    return argmax_ties(score, var_sum)


def run_strategy(name, seed, init, fixed, front_F, ref, n_max, budgets, candidates):
    """Rows (step_seconds included) of one strategy and seed."""
    rows = []
    feas = name.endswith("_feas")

    def record(n, X, F, n_gated, secs, models, extra=None):
        metrics = {"hv_regret": regret(F, front_F, ref), "n_clean": len(F), "n_gated": n_gated,
                   **(extra or {}), "step_seconds": secs, **replay.hyper_metrics(models, FAMILY)}
        for metric, value in metrics.items():
            rows.append({"strategy": name, "seed": seed, "n": n, "metric": metric,
                         "value": value})

    X0, F0, R0 = init
    if name == "lhs":                                                # not sequential
        for n in budgets:
            X, F, n_gated, secs = list(X0), list(F0), 0, 0.0
            if n > len(X0):
                t0 = time.perf_counter()
                lhs = qmc.LatinHypercube(d=len(INPUTS), optimization="random-cd",
                                         seed=np.random.default_rng([LHS_STREAM, seed, n]))
                design = qmc.scale(lhs.random(n), LOW, HIGH)
                secs = time.perf_counter() - t0
                X, F = [], []
                for x in design:
                    f = objectives(x, fixed)
                    if f is None:
                        n_gated += 1
                    else:
                        X.append(x)
                        F.append(f)
            record(n, X, F, n_gated, secs, fit(X, F))
        return rows

    active = name.startswith("al_")
    rng = np.random.default_rng([RANDOM_STREAM, seed])
    X, F, n, n_gated, step, secs = list(X0), list(F0), len(X0), 0, 1, 0.0
    labelled_X, labels = list(R0) + list(X0), [0] * len(R0) + [1] * len(X0)   # feasibility data
    p_picks, p_last = [], 1.0                       # p(feasible) of the picks since the last report
    while True:
        t0 = time.perf_counter()
        models = fit(X, F) if (active and n < n_max) else None
        fit_secs = time.perf_counter() - t0
        if n in budgets:
            extra = {"p_feasible_of_pick": float(np.mean(p_picks)) if p_picks else p_last}
            record(n, X, F, n_gated, secs, models or fit(X, F), extra if feas else None)
            secs, p_picks = 0.0, []
        if n >= n_max:
            return rows
        t0 = time.perf_counter()
        cands = candidate_set(seed, step, candidates)
        if name == "random":
            pick = int(rng.integers(len(cands)))
        elif feas:
            p = p_feasible(labelled_X, labels, cands)
            pred = replay.predict_x(models, scale_inputs(cands, BOUNDS))
            pick = weighted_pick(name, pred, np.array(F), seed * 1000 + n, p)
            p_last = float(p[pick])
            p_picks.append(p_last)
        else:
            pred = replay.predict_x(models, scale_inputs(cands, BOUNDS))
            pick = replay.acquisition_pick(name, pred, np.array(F), seed * 1000 + n)
        secs += fit_secs + time.perf_counter() - t0
        f = objectives(cands[pick], fixed)
        n, step = n + 1, step + 1
        labelled_X.append(cands[pick])
        labels.append(0 if f is None else 1)
        if f is None:
            n_gated += 1
        else:
            X.append(cands[pick])
            F.append(f)


def run(front_csv, fixed, strategies=replay.STRATEGIES, seeds=range(10), n_init=8, n_max=40,
        report_at=REPORT_AT, candidates=4096, out_csv=None):
    """Run every strategy for every seed. Returns the reproducible rows (replay.COLUMNS keys,
    step_seconds left out); out_csv, if given, gets every row including step_seconds. The default
    strategies are the four of surrogate.replay; pass STRATEGIES for all six (main() does)."""
    front_F = load_front(front_csv)
    ref = ref_point(front_F)
    budgets = [n for n in report_at if n_init <= n <= n_max]
    rows = []
    for seed in seeds:
        init = initial_design(seed, fixed, n_init, candidates)          # same for all strategies
        for name in strategies:
            rows += run_strategy(name, seed, init, fixed, front_F, ref, n_max, budgets,
                                 candidates)
    if out_csv is not None:
        replay.write_rows(rows, out_csv)
    return [r for r in rows if r["metric"] not in TIMING]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--front", default=DEFAULT_FRONT)
    ap.add_argument("--out", help="output CSV (default runs/replay_drone_online/<date>/online.csv)")
    ap.add_argument("--seeds", type=int, default=10, help="seeds 0 .. seeds - 1")
    ap.add_argument("--n-init", type=int, default=8)
    ap.add_argument("--n-max", type=int, default=40)
    ap.add_argument("--candidates", type=int, default=4096)
    ap.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=list(STRATEGIES))
    a = ap.parse_args(argv)
    today = datetime.datetime.now().astimezone().date().isoformat()
    out = Path(a.out or f"runs/replay_drone_online/{today}/online.csv")
    started = datetime.datetime.now(datetime.timezone.utc)
    t0 = time.time()
    rows = run(a.front, ledger.load_all(), strategies=tuple(a.strategies), seeds=range(a.seeds),
               n_init=a.n_init, n_max=a.n_max, candidates=a.candidates, out_csv=out)
    wall = time.time() - t0
    record = {
        "args": vars(a),
        "report_at": list(REPORT_AT),
        "commit": git_commit(),
        "started_utc": started.isoformat(),
        "ended_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "wall_seconds": wall,
        "rows_reproducible": len(rows),
        "sha256": {"front": sha256(a.front), out.name: sha256(out)},
        "ledger_sha256": {p.name: sha256(p) for p in sorted(Path("data/drone").glob("*.yaml"))},
    }
    (out.parent / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"wrote {out} and record.json in {wall:.1f} s")


if __name__ == "__main__":
    main()

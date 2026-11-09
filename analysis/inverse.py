"""Inverse design query: maximise recovery_total subject to q_peak <= Q, answered on the grid.

    python -m analysis.inverse --results RESULTS.csv --out DIR (--q-cap Q | [--q-cap-quantile 0.4])

On the feasible grid (theta1 + theta2 <= 24) the log-q GP gives P(q_peak <= Q) =
Phi((log Q - mean) / std). Among grid points with P >= prob (default 0.9) the one with the
largest predicted mean recovery is the answer. The std here is the predictive std of a new
simulation (latent + fitted noise). If no point reaches prob, result.json says
{"feasible": false, ...} and no params.json is written (exit code is still 0).

Writes result.json and, when feasible, params.json for the confirmation run (checked with
physics.gates.check; it must return []).

--family drone (Task 10, spec section 10.4): maximise the predicted endurance_h subject to
P(mtow_kg <= --mtow-cap) >= --prob (defaults 4.0 and 0.9) on a --points^6 grid (default 21^6,
85.8 million points) inside the gates. The grid is never held in memory: it is walked in chunks
of at most --chunk points (default 50,000). Each chunk first goes through the closed-form gates
(analysis.pareto.cheap_gates), then the endurance mean; only points that beat the 200th best so
far get the mtow GP and the probability, and a running list keeps the 200 best with P >= prob. The closure gates (physics.gates.check, 0.5 s a
design) are run on those 200 in order of predicted endurance and the first design to pass is the
answer. So "n_cheap_gate_feasible" counts the points passing the closed-form gates, NOT the points
passing every gate. If no point reaches the probability, inverse.json says so and gives the best
probability reached and where. Writes inverse.json and, when feasible, confirm_params.json (the
six inputs for the high-fidelity confirmation run, analysis.drone_design params format).

    python -m analysis.inverse --family drone --results grid.csv --out DIR [--points 21]
"""
import argparse
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import torch
from scipy.special import ndtr

from analysis.pareto import (
    DRONE_INPUTS,
    cheap_gates,
    drone_params,
    fit_gps,
    load_rows,
    make_grid,
    predict,
)
from mcp_server.schemas import to_params, validate
from physics.gates import check
from surrogate.gp import scale_inputs
from surrogate.replay import CONVERGED, FAMILIES
from worker.make_case import case_id

Z90 = NormalDist().inv_cdf(0.95)       # 90 percent central interval = mean +- Z90 std
MAX_GATE_TRIES = 200                   # candidates inspected if the best ones fail a gate


def interval(mean, std, log=False):
    """(mean, lo, hi) of the 90 percent interval; log=True: inputs are log q, outputs are q."""
    lo, hi = mean - Z90 * std, mean + Z90 * std
    return tuple(float(np.exp(v) if log else v) for v in (mean, lo, hi))


def confirm_params(theta1, theta2):
    return {"family": "inlet2r", "theta1_deg": round(float(theta1), 4),
            "theta2_deg": round(float(theta2), 4), "mesh_level": "medium", "tag": "confirm",
            "save_volume": False}


def run(results_rows, q_cap, out_dir, prob=0.9, grid=201, seed=0):
    """Answer the query; returns the result dict (also written to out_dir/result.json)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    models, theta, F, _ = fit_gps(results_rows)
    t1, t2, feas = make_grid(grid)
    pts = np.column_stack([t1, t2])[feas]
    rec_m, _, lq_m, lq_s = predict(models, pts, noise=True)
    p_ok = ndtr((np.log(q_cap) - lq_m) / lq_s)                       # P(q_peak <= Q)
    base = {"q_cap_W_m2": float(q_cap), "prob_required": prob, "n_train": len(theta),
            "grid": grid, "seed": seed, "interval": "90 percent, predictive (includes noise)",
            "min_observed_q_W_m2": float(np.exp(F[:, 1].min()))}
    ok = np.flatnonzero(p_ok >= prob)
    if len(ok) == 0:
        result = {"feasible": False,
                  "reason": f"no feasible design at {round(prob * 100)} percent",
                  "max_probability_on_grid": float(p_ok.max()), **base}
        (out_dir / "result.json").write_text(json.dumps(result, indent=2))
        return result

    # best predicted recovery first; skip a point only if a physics gate rejects it
    skipped = []
    for i in ok[np.argsort(-rec_m[ok])][:MAX_GATE_TRIES]:
        params = confirm_params(*pts[i])
        errors = check(params)
        if not errors:
            break
        skipped.append({"theta1_deg": params["theta1_deg"], "theta2_deg": params["theta2_deg"],
                        "errors": errors})
    else:
        raise RuntimeError(f"the {MAX_GATE_TRIES} best candidates all fail the physics gates")
    th = np.array([[params["theta1_deg"], params["theta2_deg"]]])   # predict at the rounded design
    rm, rs, lm, ls = (float(v[0]) for v in predict(models, th, noise=True))
    rec, rec_lo, rec_hi = interval(rm, rs)
    q, q_lo, q_hi = interval(lm, ls, log=True)
    model, schema_errors, _ = validate(params)                   # case_id is of the full params
    if model is None:
        raise ValueError(f"params.json fails the case schema: {schema_errors}")
    result = {"feasible": True, "case_id": case_id(to_params(model)),
              "theta1_deg": params["theta1_deg"], "theta2_deg": params["theta2_deg"],
              "recovery_total": {"mean": rec, "lo90": rec_lo, "hi90": rec_hi, "std": rs},
              "q_peak_W_m2": {"median": q, "lo90": q_lo, "hi90": q_hi, "log_std": ls},
              "p_q_le_cap": float(ndtr((np.log(q_cap) - lm) / ls)),
              "n_candidates_at_prob": len(ok), "gate_skipped": skipped, **base}
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    (out_dir / "params.json").write_text(json.dumps(params, indent=2))
    return result


# ---------------------------------------------------------------- drone family
CHUNK = 50_000                         # grid points predicted at once
TOP_K = 200                            # best candidates kept for the closure-gate check


def gp_predict(model, x):
    """(mean, std) of one (GP, Standardizer) at x (m, 6) in input units, std with noise."""
    gp, st = model
    m, v = gp.predict(scale_inputs(x, FAMILIES["drone"].bounds), noise=True)
    return st.inverse(m).numpy(), np.sqrt(st.inverse_var(v).numpy())


def grid_chunk(axes, start, stop):
    """Grid points number start .. stop - 1 (C order: the first input varies slowest)."""
    coords = np.unravel_index(np.arange(start, stop), tuple(len(a) for a in axes))
    return np.column_stack([a[c] for a, c in zip(axes, coords)])


def gp_mean(model, x):
    """Posterior mean of one (GP, Standardizer) at x (m, 6), original units. No variance, so it
    skips the triangular solve that makes gp_predict three times dearer."""
    gp, st = model
    Xs = torch.as_tensor(scale_inputs(x, FAMILIES["drone"].bounds), dtype=gp.X.dtype)
    with torch.no_grad():
        mean = gp.theta[-1] + (gp.kernel(Xs, gp.X, gp.theta) @ gp.alpha).squeeze(1)
    return st.inverse(mean).numpy()


def drone_axes(points):
    """The grid's axes: `points` equally spaced values per input over the pool's box."""
    return [np.linspace(lo, hi, points) for lo, hi in FAMILIES["drone"].bounds]


def search_grid(models, rules, mtow_cap, prob, points, chunk=CHUNK, top_k=TOP_K):
    """Walk the grid in chunks. Returns (top, stats).

    top: dict of arrays x, endurance, endurance_std, p for the top_k points with
    P(mtow <= cap) >= prob and the largest predicted endurance, best first. Per chunk: the
    closed-form gates; the endurance mean of every surviving point (cheap); the mtow and endurance
    predictions, with variances, only for points whose mean beats the current top_k-th best, since
    the others cannot enter the list whatever their probability. The answer is the same as
    predicting everything; stats counts the grid and the closed-form-gate-feasible points.
    """
    axes = drone_axes(points)
    total = points ** len(axes)
    top = {k: np.empty((0, 6) if k == "x" else 0) for k in ("x", "endurance", "endurance_std", "p")}
    n_cheap = 0
    for start in range(0, total, chunk):
        x = grid_chunk(axes, start, min(start + chunk, total))
        x = x[cheap_gates(x, rules)]
        if len(x) == 0:
            continue
        n_cheap += len(x)
        if len(top["endurance"]) == top_k:                  # only points that can enter the list
            x = x[gp_mean(models[0], x) > top["endurance"][-1]]
            if len(x) == 0:
                continue
        lm, ls = gp_predict(models[1], x)
        p = ndtr((np.log(mtow_cap) - lm) / ls)               # P(mtow <= cap)
        ok = p >= prob
        if not ok.any():
            continue
        em, es = gp_predict(models[0], x[ok])
        merged = {"x": np.vstack([top["x"], x[ok]]),
                  "endurance": np.concatenate([top["endurance"], em]),
                  "endurance_std": np.concatenate([top["endurance_std"], es]),
                  "p": np.concatenate([top["p"], p[ok]])}
        keep = np.argsort(-merged["endurance"])[:top_k]
        top = {k: v[keep] for k, v in merged.items()}
    return top, {"n_grid": total, "n_cheap_gate_feasible": n_cheap}


def best_probability(models, rules, mtow_cap, points, chunk=CHUNK):
    """(highest P(mtow <= cap) over the closed-form-gate-feasible grid, the design reaching it).

    Only run when search_grid found no design at the required probability: it predicts the mtow
    GP at every point, which is the dear part of the full walk.
    """
    axes = drone_axes(points)
    total = points ** len(axes)
    best_p, best_x = -1.0, None
    for start in range(0, total, chunk):
        x = grid_chunk(axes, start, min(start + chunk, total))
        x = x[cheap_gates(x, rules)]
        if len(x) == 0:
            continue
        lm, ls = gp_predict(models[1], x)
        p = ndtr((np.log(mtow_cap) - lm) / ls)
        if p.max() > best_p:
            best_p, best_x = float(p.max()), x[int(np.argmax(p))]
    return best_p, best_x


def interval_row(value, std, log=False):
    """Dict of a quantity's 90 percent interval (log=True: mean and std of log, outputs median)."""
    m, lo, hi = interval(value, std, log=log)
    return ({"median": m, "lo90": lo, "hi90": hi, "log_std": float(std)} if log
            else {"mean": m, "lo90": lo, "hi90": hi, "std": float(std)})


def run_drone(results_rows, out_dir, mtow_cap=4.0, prob=0.9, points=21, chunk=CHUNK,
              top_k=TOP_K):
    """Answer the drone query; returns the result dict (also written to out_dir/inverse.json)."""
    from drone import ledger
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    models, theta, F, _ = fit_gps(results_rows, "drone")
    rules = ledger.load("rules")
    top, stats = search_grid(models, rules, mtow_cap, prob, points, chunk, top_k)
    base = {"family": "drone", "mtow_cap_kg": float(mtow_cap), "prob_required": prob,
            "n_train": len(theta), "grid_points_per_axis": points, "n_grid": stats["n_grid"],
            "n_cheap_gate_feasible": stats["n_cheap_gate_feasible"],
            "n_cheap_gate_feasible_note": "points passing the closed-form gates (tip chord, spar "
            "depth) only; the closure gates were run on the best candidates, not on the grid",
            "interval": "90 percent, predictive (includes noise)",
            "min_observed_mtow_kg": float(np.exp(F[:, 1].min()))}
    if len(top["x"]) == 0:
        best_p, best = best_probability(models, rules, mtow_cap, points, chunk)
        result = {"feasible": False,
                  "reason": f"no design at {round(prob * 100)} percent",
                  "max_probability_on_grid": best_p,
                  "max_probability_design": (None if best is None else
                                             dict(zip(DRONE_INPUTS, map(float, best)))),
                  **base}
        (out_dir / "inverse.json").write_text(json.dumps(result, indent=2))
        return result

    skipped = []
    for x in top["x"]:                                      # best predicted endurance first
        x = x.round(6)
        errors = check(drone_params(x))
        if not errors:
            break
        skipped.append({**dict(zip(DRONE_INPUTS, map(float, x))), "errors": errors})
    else:
        raise RuntimeError(f"the {len(top['x'])} best candidates all fail the physics gates")
    em, es = (float(v[0]) for v in gp_predict(models[0], x[None, :]))   # at the rounded design
    lm, ls = (float(v[0]) for v in gp_predict(models[1], x[None, :]))
    design = dict(zip(DRONE_INPUTS, map(float, x)))
    result = {"feasible": True, "design": design,
              "endurance_h": interval_row(em, es), "mtow_kg": interval_row(lm, ls, log=True),
              "p_mtow_le_cap": float(ndtr((np.log(mtow_cap) - lm) / ls)),
              "gate_skipped": skipped, "closure_gates_passed": True, **base}
    (out_dir / "inverse.json").write_text(json.dumps(result, indent=2))
    confirm = {"family": "drone", "fidelity": "high", "tag": "confirm", **design}
    (out_dir / "confirm_params.json").write_text(json.dumps(confirm, indent=2))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--family", choices=sorted(FAMILIES), default="inlet")
    ap.add_argument("--mtow-cap", type=float, default=4.0, help="drone only, kg")
    ap.add_argument("--points", type=int, default=21, help="drone only: grid points per input")
    ap.add_argument("--chunk", type=int, default=CHUNK, help="drone only: points per prediction")
    ap.add_argument("--q-cap", type=float, help="W/m^2")
    ap.add_argument("--q-cap-quantile", type=float, default=0.4,
                    help="used when --q-cap is absent: this quantile of the observed q_peak")
    ap.add_argument("--prob", type=float, default=0.9)
    ap.add_argument("--grid", type=int, default=201)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rows = load_rows(a.results)
    if a.family == "drone":
        res = run_drone(rows, a.out, a.mtow_cap, a.prob, a.points, a.chunk)
        if res["feasible"]:
            print(f"design {res['design']}  endurance {res['endurance_h']['mean']:.3f} h  "
                  f"P(mtow<={a.mtow_cap})={res['p_mtow_le_cap']:.3f}")
        else:
            print(res["reason"], f"(best probability {res['max_probability_on_grid']:.3f})")
        return
    q_cap = a.q_cap
    if q_cap is None:
        q_obs = [float(r["q_peak_W_m2"]) for r in rows if r["status"] in CONVERGED]
        q_cap = float(np.quantile(q_obs, a.q_cap_quantile))
        print(f"q cap = {q_cap:.1f} W/m^2 ({a.q_cap_quantile} quantile of observed q_peak)")
    res = run(rows, q_cap, a.out, a.prob, a.grid, a.seed)
    if res["feasible"]:
        print(f"design theta1={res['theta1_deg']} theta2={res['theta2_deg']}  "
              f"recovery {res['recovery_total']['mean']:.4f}  P(q<=cap)={res['p_q_le_cap']:.3f}")
    else:
        print(res["reason"])


if __name__ == "__main__":
    main()

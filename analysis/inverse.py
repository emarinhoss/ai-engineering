"""Inverse design query: maximise recovery_total subject to q_peak <= Q, answered on the grid.

    python -m analysis.inverse --results RESULTS.csv --out DIR (--q-cap Q | [--q-cap-quantile 0.4])

On the feasible grid (theta1 + theta2 <= 24) the log-q GP gives P(q_peak <= Q) =
Phi((log Q - mean) / std). Among grid points with P >= prob (default 0.9) the one with the
largest predicted mean recovery is the answer. The std here is the predictive std of a new
simulation (latent + fitted noise). If no point reaches prob, result.json says
{"feasible": false, ...} and no params.json is written (exit code is still 0).

Writes result.json and, when feasible, params.json for the confirmation run (checked with
physics.gates.check; it must return []).
"""
import argparse
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
from scipy.special import ndtr

from analysis.pareto import fit_gps, load_rows, make_grid, predict
from mcp_server.schemas import to_params, validate
from physics.gates import check
from surrogate.replay import CONVERGED
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--q-cap", type=float, help="W/m^2")
    ap.add_argument("--q-cap-quantile", type=float, default=0.4,
                    help="used when --q-cap is absent: this quantile of the observed q_peak")
    ap.add_argument("--prob", type=float, default=0.9)
    ap.add_argument("--grid", type=int, default=201)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rows = load_rows(a.results)
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

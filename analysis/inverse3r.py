"""Task 9 question 4: robust inverse query over the flight envelope.

    maximise   predicted recovery_total at the nominal condition (Mach 4.0, 30 km, 300 K)
    over       the three ramp angles
    subject to P(q_peak <= cap) >= 0.9 at every point of a 5 x 5 x 5 grid over
               (mach 3.5..4.5, altitude 28..35 km, T_wall 300..600 K), and the inlet3r gates.

The cap is fixed before the answer: the 40th percentile of q_peak over the converged NS pool runs.
Models: one GP per output (recovery_total; log q_peak) on all converged NS pool runs, six inputs scaled
to [0, 1]. P(q <= cap) = Phi((log cap - mean) / std) with the predictive std of a new run (latent plus
fitted noise), as analysis.inverse (Task 5).

Search: 4096 scrambled Sobol points (seed 0) in the angle box [3, 10]^3 deg with total turning <= 27 deg.
Among the candidates that meet the probability at all 125 envelope points, the best predicted nominal
recovery wins, unless a gate rejects it at the nominal point or at one of the 125 envelope points; then
the next. The answer's worst envelope point (lowest probability) is where the confirmation run goes;
its params are written to params.json (pool settings, tag "confirm3r"). If no candidate meets the
probability everywhere, result.json says so and gives the best that was reached, and for each envelope
point the best probability any candidate reaches there and the lowest predicted q median (to show which
flight conditions make the query infeasible).

    python -m analysis.inverse3r --table runs/pool3r/pool3r_table.csv --out runs/pool3r/analysis/inverse
"""
import argparse
import itertools
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import torch
from scipy.special import ndtr
from scipy.stats import qmc

from analysis.pool3r_table import INPUTS, load
from designs.make_pool3r import HIGH, LOW
from physics.gates import check
from surrogate.gp import GP, Standardizer, scale_inputs
from worker.make_case import case_id

NOMINAL = {"mach": 4.0, "altitude_km": 30.0, "T_wall_K": 300.0}
ENVELOPE = list(itertools.product(np.linspace(3.5, 4.5, 5), np.linspace(28, 35, 5), np.linspace(300, 600, 5)))
PROB, QUANTILE, N_CAND, MAX_GATE_TRIES = 0.9, 0.4, 4096, 200
Z90 = NormalDist().inv_cdf(0.95)
BOUNDS = list(zip(LOW, HIGH))


def fit(rows):
    hf = [r for r in rows if r["set"] == "hf" and r["ns_status"] == "converged"]
    X = scale_inputs(np.array([[r[k] for k in INPUTS] for r in hf]), BOUNDS)
    models = []
    for y in (np.array([r["ns_recovery_total"] for r in hf]), np.log([r["ns_q_peak_W_m2"] for r in hf])):
        st = Standardizer().fit(y)
        models.append((GP().fit(X, st.transform(y)), st))
    return models, hf


def predict(model, angles, flight):
    """Mean and predictive std (with noise) at each (angles row, flight row) pair."""
    gp, st = model
    X = scale_inputs(np.column_stack([angles, flight]), BOUNDS)
    parts = [gp.predict(X[i:i + 20000], noise=True) for i in range(0, len(X), 20000)]   # bounded memory
    m, v = torch.cat([p[0] for p in parts]), torch.cat([p[1] for p in parts])
    return st.inverse(m).numpy(), np.sqrt(st.inverse_var(v).numpy())


def params_for(angles, flight):
    return {"family": "inlet3r", **{f"theta{i + 1}_deg": round(float(a), 4) for i, a in enumerate(angles)},
            "mach": round(float(flight[0]), 4), "altitude_km": round(float(flight[1]), 4),
            "T_wall_K": round(float(flight[2]), 4), "solver": "NAVIER_STOKES", "mesh_level": "medium",
            "max_iter": 8000, "tag": "confirm3r"}


def run(rows, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (rec_model, lq_model), hf = fit(rows)
    cap = float(np.quantile([r["ns_q_peak_W_m2"] for r in hf], QUANTILE))
    cand = qmc.scale(qmc.Sobol(d=3, scramble=True, seed=0).random(N_CAND), [3, 3, 3], [10, 10, 10])
    cand = cand[cand.sum(1) <= 27.0]
    env = np.array(ENVELOPE)
    nominal = np.array([[NOMINAL["mach"], NOMINAL["altitude_km"], NOMINAL["T_wall_K"]]])
    rec_m, _ = predict(rec_model, cand, np.repeat(nominal, len(cand), 0))
    A, E = np.repeat(cand, len(env), 0), np.tile(env, (len(cand), 1))
    lq_m, lq_s = predict(lq_model, A, E)
    p_all = ndtr((np.log(cap) - lq_m) / lq_s).reshape(len(cand), len(env))
    p_min = p_all.min(1)
    q_med = np.exp(lq_m).reshape(len(cand), len(env))
    per_point = [{"mach": float(f[0]), "altitude_km": float(f[1]), "T_wall_K": float(f[2]),
                  "best_probability_over_candidates": float(p_all[:, j].max()),
                  "lowest_predicted_q_median_W_m2": float(q_med[:, j].min())} for j, f in enumerate(env)]
    base = {"q_cap_W_m2": cap, "cap_rule": f"{QUANTILE} quantile of q_peak over {len(hf)} converged NS pool runs",
            "prob_required": PROB, "n_candidates": len(cand), "n_envelope_points": len(env),
            "interval": "90 percent, predictive (includes fitted noise)"}
    ok = np.flatnonzero(p_min >= PROB)
    if len(ok) == 0:
        i = int(np.argmax(p_min))
        res = {"feasible": False, "best_min_probability": float(p_min[i]),
               "angles_at_best_min_probability": cand[i].round(4).tolist(), **base,
               "n_envelope_points_some_candidate_meets_prob":
                   int(sum(pp["best_probability_over_candidates"] >= PROB for pp in per_point)),
               "per_envelope_point": per_point}
        (out_dir / "result.json").write_text(json.dumps(res, indent=2) + "\n")
        return res
    skipped = []
    for i in ok[np.argsort(-rec_m[ok])][:MAX_GATE_TRIES]:
        errors = check(params_for(cand[i], nominal[0])) + [e for f in env for e in check(params_for(cand[i], f))]
        if not errors:
            break
        skipped.append({"angles": cand[i].round(4).tolist(), "first_error": errors[0]})
    else:
        raise RuntimeError(f"the {MAX_GATE_TRIES} best candidates all fail a gate")
    angles = np.array([[round(float(a), 4) for a in cand[i]]])        # report at the rounded design
    lm, ls = predict(lq_model, np.repeat(angles, len(env), 0), env)
    p_env = ndtr((np.log(cap) - lm) / ls)
    w = int(np.argmin(p_env))
    rm, rs = predict(rec_model, angles, nominal)
    rwm, rws = predict(rec_model, angles, env[w:w + 1])
    worst = params_for(angles[0], env[w])
    res = {"feasible": True, **base, "n_feasible_candidates": len(ok), "skipped_by_gates": skipped,
           "theta_deg": angles[0].tolist(), "theta_total_deg": float(angles.sum()),
           "nominal": {"recovery_total": {"mean": float(rm[0]), "std": float(rs[0]),
                                          "lo90": float(rm[0] - Z90 * rs[0]), "hi90": float(rm[0] + Z90 * rs[0])}},
           "min_probability_over_envelope": float(p_env.min()),
           "worst_envelope_point": {"mach": worst["mach"], "altitude_km": worst["altitude_km"],
                                    "T_wall_K": worst["T_wall_K"], "p_q_below_cap": float(p_env[w]),
                                    "recovery_total": {"mean": float(rwm[0]), "std": float(rws[0]),
                                                       "lo90": float(rwm[0] - Z90 * rws[0]),
                                                       "hi90": float(rwm[0] + Z90 * rws[0])},
                                    "q_peak_W_m2": {"median": float(np.exp(lm[w])), "log_std": float(ls[w]),
                                                    "lo90": float(np.exp(lm[w] - Z90 * ls[w])),
                                                    "hi90": float(np.exp(lm[w] + Z90 * ls[w]))}},
           "confirm_case_id": case_id(worst)}
    (out_dir / "params.json").write_text(json.dumps(worst, indent=1) + "\n")
    (out_dir / "result.json").write_text(json.dumps(res, indent=2) + "\n")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default="runs/pool3r/pool3r_table.csv")
    ap.add_argument("--out", default="runs/pool3r/analysis/inverse")
    a = ap.parse_args()
    res = run(load(a.table), a.out)
    print(json.dumps({k: v for k, v in res.items() if k not in ("skipped_by_gates", "per_envelope_point")}, indent=1))


if __name__ == "__main__":
    main()

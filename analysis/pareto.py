"""Pareto front with uncertainty from the two GPs (Task 5).

    python -m analysis.pareto --results RESULTS.csv --out runs/analysis/<date>/ \
        [--grid 201] [--samples 50] [--seed 0]

RESULTS.csv columns: case_id, theta1_deg, theta2_deg, recovery_total, q_peak_W_m2, status.
Only rows with status converged or stationary are used. The GPs are the Task 4 ones: GP 1 on
recovery_total, GP 2 on log(q_peak_W_m2), inputs scaled to [0, 1]^2 over the design box.

Objectives in minimisation form (surrogate.replay): f1 = -recovery_total, f2 = log q_peak.
Files written to --out:
  grid.csv     theta1, theta2, rec_mean, rec_std, q_mean, q_std, feasible, q_W_m2
               rec_* in recovery units; q_mean, q_std are the mean and std of log(q_peak_W_m2);
               q_W_m2 = exp(q_mean) (the median). Latent function (no noise). Points with
               theta1 + theta2 > 24 (gate 4) have feasible = 0 and NaN in all value columns.
  pareto.csv   kind = observed | predicted | band (see build_rows)
  hypers.json, notes.json
"""
import argparse
import csv
import datetime
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from designs.make_pool import HIGH, LOW
from surrogate.gp import GP, JITTER, Standardizer, scale_inputs
from surrogate.replay import CONVERGED, to_objectives

BOUNDS = list(zip(LOW, HIGH))          # (theta1, theta2) in degrees
MAX_TURN_DEG = 24.0                    # gate 4 (physics/gates.py)
N_LEVELS = 25                          # q_peak levels of the band
BAND_MAX_POINTS = 1500                 # dense covariance size limit for the band
GRID_COLUMNS = ("theta1", "theta2", "rec_mean", "rec_std", "q_mean", "q_std", "feasible", "q_W_m2")
PARETO_COLUMNS = ("kind", "case_id", "theta1_deg", "theta2_deg", "recovery_total", "q_peak_W_m2",
                  "rec_p05", "rec_p50", "rec_p95")


# ---------------------------------------------------------------- data and models
def load_rows(results_csv):
    """Read the results table as a list of dicts (strings, as csv gives them)."""
    with open(results_csv) as f:
        return list(csv.DictReader(f))


def usable(rows):
    """Rows whose run converged or reached a stationary state."""
    return [r for r in rows if r["status"] in CONVERGED]


def fit_gps(rows):
    """Fit the two GPs on the usable rows. Returns (models, theta, F, case_ids).

    models = [(GP, Standardizer) for recovery_total, (GP, Standardizer) for log q_peak];
    theta (n, 2) in degrees; F (n, 2) in minimisation form.
    """
    keep = usable(rows)
    if len(keep) < 4:
        raise ValueError(f"need at least 4 converged/stationary rows, got {len(keep)}")
    theta = np.array([[float(r["theta1_deg"]), float(r["theta2_deg"])] for r in keep])
    F = to_objectives({"recovery_total": [float(r["recovery_total"]) for r in keep],
                       "q_peak_W_m2": [float(r["q_peak_W_m2"]) for r in keep]})
    X = scale_inputs(theta, BOUNDS)
    models = []
    for y in (-F[:, 0], F[:, 1]):                       # y1 = recovery, y2 = log q
        st = Standardizer().fit(y)
        models.append((GP().fit(X, st.transform(y)), st))
    return models, theta, F, [r.get("case_id", "") for r in keep]


def predict(models, theta, noise=False):
    """Mean and std at theta (m, 2) degrees: (rec_mean, rec_std, logq_mean, logq_std).

    noise=False is the latent function; noise=True adds the fitted noise variance, i.e. the
    spread of a new simulation result.
    """
    X = scale_inputs(theta, BOUNDS)
    out = []
    for gp, st in models:
        m, v = gp.predict(X, noise=noise)
        out += [st.inverse(m).numpy(), np.sqrt(st.inverse_var(v).numpy())]
    return out[0], out[1], out[2], out[3]


def make_grid(n):
    """Flattened n x n grid over the box (theta1 slow, theta2 fast) and the gate-4 mask."""
    t1, t2 = np.meshgrid(np.linspace(LOW[0], HIGH[0], n), np.linspace(LOW[1], HIGH[1], n),
                         indexing="ij")
    t1, t2 = t1.ravel(), t2.ravel()
    return t1, t2, (t1 + t2) <= MAX_TURN_DEG + 1e-9


def front_2d(F):
    """Indices of the non-dominated rows of F (n, 2), minimisation, sorted by f1 ascending.

    Sort by f1 (ties by f2); walk left to right and keep a row only if its f2 is below every
    f2 seen so far. O(n log n), so it works for a 40000-point grid (acquisition.pareto_front
    builds an n x n matrix). A duplicate of a kept row is dominated by nobody but is dropped.
    """
    F = np.asarray(F, dtype=float)
    order = np.lexsort((F[:, 1], F[:, 0]))
    keep, best = [], np.inf
    for i in order:
        if F[i, 1] < best:
            keep.append(i)
            best = F[i, 1]
    return np.array(keep, dtype=int)


# ---------------------------------------------------------------- joint posterior samples
def joint_samples(gp, st, theta, n_samples, rng):
    """Joint draws of the latent function at theta (m, 2): array (n_samples, m), original units.

    Posterior covariance in standardised units: K** - V^T V with V = L^-1 K*. Cholesky of that
    (plus a growing jitter, because a smooth kernel with tiny noise is numerically singular).
    """
    Xs = scale_inputs(theta, BOUNDS)
    with torch.no_grad():
        mean, _ = gp.predict(Xs)
        V = torch.linalg.solve_triangular(gp.L, gp.kernel(Xs, gp.X, gp.theta).T, upper=False)
        cov = gp.kernel(Xs, Xs, gp.theta) - V.T @ V
        eye = torch.eye(len(Xs), dtype=cov.dtype)
        jitter = max(JITTER, 1e-8 * float(torch.exp(gp.theta[Xs.shape[1]])))
        for _ in range(8):
            try:
                chol = torch.linalg.cholesky(cov + jitter * eye)
                break
            except RuntimeError:
                jitter *= 10
        else:
            raise RuntimeError("posterior covariance is not positive definite")
    z = torch.as_tensor(rng.standard_normal((len(Xs), n_samples)), dtype=cov.dtype)
    draws = (mean[:, None] + chol @ z).T                  # (n_samples, m), standardised
    return st.inverse(draws).numpy()


def best_recovery_at(front_q, front_rec, levels):
    """Best recovery with q <= level for each level; NaN where the front has no point that low.

    front_q ascending, front_rec ascending (a front). The answer at a level is the recovery of
    the last front point with q <= level.
    """
    idx = np.searchsorted(front_q, levels, side="right") - 1
    return np.where(idx >= 0, front_rec[np.clip(idx, 0, None)], np.nan)


def band(models, theta_feas, levels, samples, seed):
    """5/50/95 percent of the best recovery at each q level over joint sample fronts.

    Returns (p05, p50, p95, n_valid) arrays over levels. Each sample draws recovery and log q
    jointly on the points of theta_feas (the two GPs are independent of each other).
    """
    rng = np.random.default_rng(seed)
    rec = joint_samples(*models[0], theta_feas, samples, rng)       # (S, m)
    logq = joint_samples(*models[1], theta_feas, samples, rng)
    best = np.full((samples, len(levels)), np.nan)
    for s in range(samples):
        F = np.column_stack([-rec[s], logq[s]])
        idx = front_2d(F)                                           # f1 ascending: recovery down
        # the front in physical units: q ascending <-> recovery ascending
        fq, fr = np.exp(F[idx, 1])[::-1], rec[s][idx][::-1]
        best[s] = best_recovery_at(fq, fr, levels)
    valid = np.isfinite(best)
    p = np.full((3, len(levels)), np.nan)
    for j in range(len(levels)):
        if valid[:, j].any():
            p[:, j] = np.percentile(best[valid[:, j], j], [5, 50, 95])
    return p[0], p[1], p[2], valid.sum(0)


# ---------------------------------------------------------------- the analysis
def write_csv(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def run(results_rows, out_dir, grid=201, samples=50, seed=0):
    """Fit, evaluate on the grid, write the files; returns a dict with the arrays for callers."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    models, theta, F, ids = fit_gps(results_rows)
    n_by_status = Counter(r["status"] for r in results_rows if r["status"] not in CONVERGED)

    # grid.csv: NaN where theta1 + theta2 > 24
    t1, t2, feas = make_grid(grid)
    pts = np.column_stack([t1, t2])
    rec_m, rec_s, lq_m, lq_s = (np.full(len(pts), np.nan) for _ in range(4))
    rec_m[feas], rec_s[feas], lq_m[feas], lq_s[feas] = predict(models, pts[feas])
    write_csv(out_dir / "grid.csv", GRID_COLUMNS,
              [dict(zip(GRID_COLUMNS, (a, b, c, d, e, f, int(g), np.exp(e))))
               for a, b, c, d, e, f, g in zip(t1, t2, rec_m, rec_s, lq_m, lq_s, feas)])

    rows = []
    # (a) observed non-dominated points, true values
    for i in front_2d(F):
        rows.append({"kind": "observed", "case_id": ids[i], "theta1_deg": theta[i, 0],
                     "theta2_deg": theta[i, 1], "recovery_total": -F[i, 0],
                     "q_peak_W_m2": np.exp(F[i, 1])})
    # (b) predicted front: posterior mean on the feasible grid, physical units
    Fg = np.column_stack([-rec_m[feas], lq_m[feas]])
    for i in front_2d(Fg):
        rows.append({"kind": "predicted", "theta1_deg": pts[feas][i, 0],
                     "theta2_deg": pts[feas][i, 1], "recovery_total": -Fg[i, 0],
                     "q_peak_W_m2": np.exp(Fg[i, 1])})
    # (c) band of the sample fronts at fixed q levels
    q_obs = np.exp(F[:, 1])
    lo, hi = np.percentile(q_obs, [5, 95])
    levels = np.geomspace(lo, hi, N_LEVELS)
    feas_pts = pts[feas]
    subsampled = len(feas_pts) > BAND_MAX_POINTS
    if subsampled:
        pick = np.sort(np.random.default_rng(seed).choice(len(feas_pts), BAND_MAX_POINTS,
                                                         replace=False))
        feas_pts = feas_pts[pick]
    p05, p50, p95, n_valid = band(models, feas_pts, levels, samples, seed)
    for lev, a, b, c in zip(levels, p05, p50, p95):
        rows.append({"kind": "band", "q_peak_W_m2": lev, "rec_p05": a, "rec_p50": b, "rec_p95": c})
    write_csv(out_dir / "pareto.csv", PARETO_COLUMNS, rows)

    hypers = {"recovery_total": {**models[0][0].hypers(), "y_mean": float(models[0][1].mean),
                                 "y_std": float(models[0][1].std)},
              "log_q_peak": {**models[1][0].hypers(), "y_mean": float(models[1][1].mean),
                             "y_std": float(models[1][1].std)}}
    (out_dir / "hypers.json").write_text(json.dumps(hypers, indent=2))
    method = (f"{samples} joint samples of the two independent GPs (latent function, no noise) "
              f"on {len(feas_pts)} feasible points via Cholesky of the posterior covariance; "
              f"each sample's front gives the best recovery at or below each of {N_LEVELS} "
              f"log-spaced q levels (5th to 95th percentile of observed q); percentiles over "
              f"samples with a point at or below the level")
    if subsampled:
        method += (f"; the feasible grid ({int(feas.sum())} points) was too large for a dense "
                   f"covariance, so {BAND_MAX_POINTS} of its points were drawn at random "
                   f"(seed {seed}) and the sample fronts are coarser than the predicted front")
    notes = {"n_rows": len(results_rows), "n_used": len(theta),
             "n_excluded_by_status": dict(n_by_status), "grid": grid, "samples": samples,
             "seed": seed, "n_feasible_grid_points": int(feas.sum()),
             "band_points": len(feas_pts), "band_subsampled": subsampled,
             "band_method": method, "q_levels_W_m2": levels.tolist(),
             "band_valid_samples_per_level": n_valid.tolist(),
             "case_ids_used": ids,
             "q_note": "q_mean/q_std in grid.csv are mean/std of log(q_peak_W_m2)"}
    (out_dir / "notes.json").write_text(json.dumps(notes, indent=2))
    return {"models": models, "theta": theta, "F": F, "levels": levels, "band": (p05, p50, p95),
            "grid": (t1, t2, feas, rec_m, rec_s, lq_m, lq_s)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", default=None, help="default runs/analysis/<date>/")
    ap.add_argument("--grid", type=int, default=201)
    ap.add_argument("--samples", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    out = a.out or f"runs/analysis/{datetime.datetime.now().astimezone().date().isoformat()}/"
    res = run(load_rows(a.results), out, a.grid, a.samples, a.seed)
    print(f"{len(res['theta'])} points used; wrote {out}")


if __name__ == "__main__":
    main()

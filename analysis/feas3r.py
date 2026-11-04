"""Task 9 question 3: can a classifier learn where the laminar NS pool runs converge?

Data: the 159 gate-passing high-fidelity pool points (runs/pool3r/pool3r_table.csv); label 1 if the NS
run converged, 0 otherwise. Classifier: surrogate.feasibility.Feasibility (logistic regression) on the
six inputs scaled to [0, 1] plus total turning scaled as (theta_total - 9) / 21.

Stratified 5-fold cross-validation (seeded): failures and successes are each shuffled and dealt round
robin to the folds, so every fold has its share of the few failures. Each point gets one out-of-fold
probability. Reported, fixed before running:
  accuracy at threshold 0.5, against the baseline that predicts "converges" everywhere;
  at thresholds 0.5 and 0.9: failed runs it would have skipped (p below the threshold) and good runs
  it would have lost (converged, p below the threshold);
  rank AUC (probability that a random converged point scores above a random failed one);
  each failed point with its inputs and out-of-fold probability; the coefficients of a fit on all points.

    python -m analysis.feas3r --table runs/pool3r/pool3r_table.csv --out runs/pool3r/analysis/feasibility.json
"""
import argparse
import json
from pathlib import Path

import numpy as np

from analysis.pool3r_table import INPUTS, load
from designs.make_pool3r import HIGH, LOW
from surrogate.feasibility import Feasibility

FEATURES = INPUTS + ("theta_total_deg",)
THRESHOLDS = (0.5, 0.9)


def features(rows):
    X = np.array([[r[k] for k in INPUTS] for r in rows], dtype=float)
    X = (X - np.array(LOW)) / (np.array(HIGH) - np.array(LOW))
    t = (np.array([r["theta_total_deg"] for r in rows]) - 9.0) / 21.0
    return np.column_stack([X, t])


def folds(y, k=5, seed=0):
    """Fold number per point, stratified by label."""
    rng = np.random.default_rng(seed)
    fold = np.empty(len(y), dtype=int)
    for label in (0, 1):
        idx = rng.permutation(np.flatnonzero(y == label))
        fold[idx] = np.arange(len(idx)) % k
    return fold


def rank_auc(p, y):
    """Mann-Whitney: P(p_converged > p_failed), ties count one half."""
    pos, neg = p[y == 1], p[y == 0]
    diff = pos[:, None] - neg[None, :]
    return float(((diff > 0) + 0.5 * (diff == 0)).mean())


def run(rows, k=5, seed=0):
    rows = [r for r in rows if r["set"] == "hf"]
    F = features(rows)
    y = np.array([r["ns_status"] == "converged" for r in rows], dtype=float)
    fold = folds(y, k, seed)
    p = np.empty(len(y))
    for f in range(k):
        test = fold == f
        p[test] = Feasibility().fit(F[~test], y[~test]).predict(F[test]).numpy()
    out = {"n": len(y), "n_failed": int((y == 0).sum()), "folds": k, "seed": seed,
           "accuracy_at_0.5": float(((p >= 0.5) == (y == 1)).mean()),
           "baseline_accuracy_always_converges": float(y.mean()),
           "rank_auc": rank_auc(p, y)}
    for t in THRESHOLDS:
        out[f"at_{t}"] = {"failed_skipped": int(((p < t) & (y == 0)).sum()),
                          "good_lost": int(((p < t) & (y == 1)).sum())}
    out["failed_points"] = [{"case_id": r["ns_case_id"], "status": r["ns_status"],
                             **{k_: r[k_] for k_ in FEATURES}, "p_oof": float(pi)}
                            for r, pi, yi in zip(rows, p, y) if yi == 0]
    full = Feasibility().fit(F, y)
    out["coefficients_centred_features"] = dict(zip(FEATURES, full.w.tolist()))
    out["intercept"] = float(full.b)
    out["p_oof_converged_quantiles"] = dict(zip(("min", "q10", "median"),
                                                np.quantile(p[y == 1], [0, 0.1, 0.5]).tolist()))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default="runs/pool3r/pool3r_table.csv")
    ap.add_argument("--out", default="runs/pool3r/analysis/feasibility.json")
    a = ap.parse_args()
    res = run(load(a.table))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "failed_points"}, indent=1))
    for fp in res["failed_points"]:
        print(fp["case_id"], fp["status"], f"M={fp['mach']:.2f} turn={fp['theta_total_deg']:.1f} p={fp['p_oof']:.3f}")


if __name__ == "__main__":
    main()

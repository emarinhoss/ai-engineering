"""Task 4c diagnostic (post hoc): the truncation floor of the PCA + GP baseline.

The comparison (analysis/operator_compare.py) keeps the components that explain 99.9 percent of the
training variance, as fixed in the spec. This script asks how much of the PCA + GP error comes from
that truncation alone: each held-out profile is projected onto the first k training components
(the best any coefficient model could do with k components), for k = 1 to 8, on the same splits.
It changes nothing in the reported comparison.

    python -m analysis.pca_floor --profiles runs/profiles/2026-11-02/profiles.csv --out runs/profiles/2026-11-02

Writes OUT/pca_floor.csv (regime, k, variance kept, median and 90th percentile of the relative L2
error of the projected profile over held-out designs).
"""
import argparse
import csv
from pathlib import Path

import numpy as np

from analysis.operator_compare import load_profiles, splits


def floor_errors(Q, train, test, k):
    """Relative L2 error in q of the best k-component reconstruction of each held-out profile.
    Returns (errors, fraction of training variance kept by k components)."""
    Ylog = np.log(Q)
    mu = Ylog[train].mean(0)
    sd = (Ylog[train] - mu).std()
    _, S, Vt = np.linalg.svd((Ylog[train] - mu) / sd, full_matrices=False)
    V = Vt[:k]
    Z = (Ylog[test] - mu) / sd
    q_hat = np.exp(mu + sd * (Z @ V.T @ V))
    err = np.linalg.norm(q_hat - Q[test], axis=1) / np.linalg.norm(Q[test], axis=1)
    return err, float((S[:k] ** 2).sum() / (S**2).sum())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profiles", default="runs/profiles/2026-11-02/profiles.csv")
    ap.add_argument("--out", default="runs/profiles/2026-11-02")
    a = ap.parse_args()
    Q = load_profiles(a.profiles)["Q"]
    rows = []
    for regime in ("A", "B"):
        for k in range(1, 9):
            errs, kept = [], []
            for reg, _, train, test in splits(len(Q)):
                if reg == regime:
                    e, f = floor_errors(Q, train, test, k)
                    errs.append(e)
                    kept.append(f)
            errs = np.concatenate(errs)
            rows.append({"regime": regime, "k": k, "variance_kept_min": min(kept),
                         "rel_l2_median": float(np.median(errs)), "rel_l2_p90": float(np.percentile(errs, 90))})
    path = Path(a.out) / "pca_floor.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['regime']} k={r['k']}  kept>={r['variance_kept_min']:.6f}  "
              f"median {r['rel_l2_median']:.3g}  p90 {r['rel_l2_p90']:.3g}")


if __name__ == "__main__":
    main()

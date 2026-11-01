"""Write the Sobol pool design: python -m designs.make_pool [--out designs/pool_sobol96.csv].

96 points of a scrambled 2-d Sobol sequence (seed 0) scaled to theta1 in [5, 12], theta2 in
[5, 14]. scipy warns that Sobol balance needs a power of two, so we draw 128 points with
random_base2(7) and keep the first 96: any prefix of a Sobol sequence is usable, and the
first 64 are a balanced set (16 per quarter of the box).
"""
import argparse
from pathlib import Path

from scipy.stats import qmc

LOW, HIGH = (5.0, 5.0), (12.0, 14.0)      # (theta1_deg, theta2_deg) box
N_POINTS, SEED = 96, 0
DEFAULT_OUT = Path(__file__).with_name("pool_sobol96.csv")


def points(n=N_POINTS, seed=SEED):
    """n x 2 array in the box, rounded to 6 decimals."""
    unit = qmc.Sobol(d=2, scramble=True, seed=seed).random_base2(7)[:n]
    return qmc.scale(unit, LOW, HIGH).round(6)


def write(path=DEFAULT_OUT, n=N_POINTS, seed=SEED):
    lines = ["index,theta1_deg,theta2_deg"]
    lines += [f"{i},{t1:.6f},{t2:.6f}" for i, (t1, t2) in enumerate(points(n, seed))]
    Path(path).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--n", type=int, default=N_POINTS)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    write(a.out, a.n, a.seed)
    print(f"wrote {a.n} points to {a.out}")

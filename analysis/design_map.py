"""Figures: five-panel design map and the Oswatitsch cut.

    python -m analysis.design_map --grid DIR/grid.csv --results RESULTS.csv --out DIR/design_map.png

design_map.png: recovery mean, recovery std, q_peak mean, q_peak relative std, and the observed
points over the feasible region (infeasible triangle hatched). All from grid.csv and RESULTS.csv.
oswatitsch_cut.png (same folder): along theta2 = theta1 + 2 deg inside the box, the GP mean
recovery with its 90 percent band (GP refitted from RESULTS.csv) and, for context, the inviscid
analytic two-shock-plus-normal-shock recovery.
"""
import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

from analysis.inverse import Z90
from analysis.pareto import MAX_TURN_DEG, fit_gps, load_rows, predict
from designs.make_pool import HIGH, LOW
from physics.shock import normal, oblique
from surrogate.replay import CONVERGED

MACH = 4.0


def load_grid(path):
    """grid.csv -> dict of 2-D arrays (n1, n2) indexed [theta1, theta2], plus the axes."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    cols = {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}
    th1, th2 = np.unique(cols["theta1"]), np.unique(cols["theta2"])
    shape = (len(th1), len(th2))
    return th1, th2, {k: v.reshape(shape) for k, v in cols.items()}


def analytic_recovery(theta1_deg, theta2_deg):
    """Inviscid recovery: two oblique shocks, then a normal shock at the throat Mach number."""
    s1 = oblique(MACH, math.radians(theta1_deg))
    s2 = oblique(s1["M2"], math.radians(theta2_deg))
    return s1["p0_ratio"] * s2["p0_ratio"] * normal(s2["M2"])["p0_ratio"]


def hatch_triangle(ax):
    """Hatch the part of the box with theta1 + theta2 > 24 (gate 4)."""
    tri = [(MAX_TURN_DEG - HIGH[1], HIGH[1]), (HIGH[0], HIGH[1]), (HIGH[0], MAX_TURN_DEG - HIGH[0])]
    ax.add_patch(Polygon(tri, closed=True, fill=False, hatch="///", edgecolor="0.3", lw=0.8))


def design_map(grid_csv, results_rows, out_png):
    th1, th2, g = load_grid(grid_csv)
    ext = (th1[0], th1[-1], th2[0], th2[-1])
    panels = [("recovery_total mean (-)", g["rec_mean"]),
              ("recovery_total std (-)", g["rec_std"]),
              ("q_peak median (kW/m$^2$)", g["q_W_m2"] / 1e3),
              ("q_peak relative std (%)", 100 * g["q_std"])]     # std of log q = relative std
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
    for ax, (label, z) in zip(axes.flat, panels):
        im = ax.imshow(z.T, origin="lower", extent=ext, aspect="auto", cmap="viridis")
        fig.colorbar(im, ax=ax, label=label)
        hatch_triangle(ax)
    ax = axes.flat[4]
    ax.imshow(np.where(np.isfinite(g["rec_mean"]), 1.0, np.nan).T, origin="lower", extent=ext,
              aspect="auto", cmap="Greys", vmin=0, vmax=2)
    hatch_triangle(ax)
    for status, marker, color in (("ok", "o", "C0"), ("excluded", "x", "C3")):
        pts = [(float(r["theta1_deg"]), float(r["theta2_deg"])) for r in results_rows
               if (r["status"] in CONVERGED) == (status == "ok")]
        if pts:
            ax.scatter(*np.array(pts).T, marker=marker, c=color, s=28,
                       label=("converged / stationary" if status == "ok" else "other status")
                       + f" (n={len(pts)})")
    ax.set_title("observed runs")
    ax.legend(loc="lower left", fontsize=8)
    axes.flat[5].axis("off")
    for ax in axes.flat[:5]:
        ax.set_xlabel(r"$\theta_1$ (deg)")
        ax.set_ylabel(r"$\theta_2$ (deg)")
        ax.set_xlim(LOW[0], HIGH[0])
        ax.set_ylim(LOW[1], HIGH[1])
    for ax, t in zip(axes.flat[:4], ("recovery mean", "recovery std", "q_peak median", "q_peak std")):
        ax.set_title(t)
    axes.flat[5].text(0.0, 0.5, f"Made from {Path(grid_csv).name} (GP posterior) and "
                      f"{len(results_rows)} rows of the results table.\nHatched: "
                      r"$\theta_1+\theta_2>24$ deg (gate 4).", fontsize=9, va="center")
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def oswatitsch_cut(results_rows, out_png, n=121):
    """GP mean and 90 percent band along theta2 = theta1 + 2, with the analytic curve."""
    models = fit_gps(results_rows)[0]
    t1 = np.linspace(LOW[0], min(HIGH[0], (MAX_TURN_DEG - 2) / 2), n)   # theta1 + theta2 <= 24
    t2 = t1 + 2.0
    keep = (t2 >= LOW[1]) & (t2 <= HIGH[1])
    t1, t2 = t1[keep], t2[keep]
    mean, std, _, _ = predict(models, np.column_stack([t1, t2]))
    fig, ax = plt.subplots(figsize=(6.5, 4.2), constrained_layout=True)
    ax.fill_between(t1, mean - Z90 * std, mean + Z90 * std, alpha=0.3, label="GP 90% band")
    ax.plot(t1, mean, label="GP mean (results table)")
    ax.plot(t1, [analytic_recovery(a, b) for a, b in zip(t1, t2)], "k--",
            label="inviscid, analytic")
    ax.set_xlabel(r"$\theta_1$ (deg), with $\theta_2=\theta_1+2$ deg")
    ax.set_ylabel("recovery_total (-)")
    ax.legend()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--grid", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = load_rows(a.results)
    design_map(a.grid, rows, a.out)
    oswatitsch_cut(rows, Path(a.out).with_name("oswatitsch_cut.png"))
    print(f"wrote {a.out} and oswatitsch_cut.png")


if __name__ == "__main__":
    main()

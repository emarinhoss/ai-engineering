"""Pareto plot (Task 5): observed pool front, GP predicted front, posterior band, discretisation.

    python -m analysis.plot_pareto PARETO_CSV --out PNG --disc-rec-pct X --disc-q-pct Y \
        [--inverse RESULT_JSON]

PARETO_CSV is written by analysis/pareto.py (kinds observed, predicted, band). The two
discretisation percentages come from the grid study (medium to fine). The inverse query
result.json is optional. Everything drawn comes from these inputs; nothing is invented.
"""
import argparse
import csv
import json

import matplotlib as mpl

mpl.use("Agg")                                                  # no display needed
import matplotlib.pyplot as plt
import numpy as np

W_TO_KW = 1000.0


def num(text):
    """CSV cell to float; an empty cell (not written for this kind) is NaN."""
    return float(text) if text else np.nan


def column(rows, name):
    """One column of the rows as a float array."""
    return np.array([num(r[name]) for r in rows])


def read_rows(path):
    """Observed rows, predicted rows and band rows of pareto.csv (predicted and band sorted by q)."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    def of(kind):
        return [r for r in rows if r["kind"] == kind]

    predicted = sorted(of("predicted"), key=lambda r: num(r["q_peak_W_m2"]))
    band = sorted(of("band"), key=lambda r: num(r["q_peak_W_m2"]))
    return of("observed"), predicted, band


def plot_pareto(pareto_csv, out_png, disc_rec_pct, disc_q_pct, inverse_json=None):
    """Write the one-panel figure to out_png. Returns the number of observed points."""
    observed, predicted, band = read_rows(pareto_csv)
    if not observed:
        raise ValueError(f"{pareto_csv} has no observed rows")
    fig, ax = plt.subplots(figsize=(7.5, 5))

    # observed non-dominated pool points, true SU2 values
    oq = column(observed, "q_peak_W_m2") / W_TO_KW
    orec = column(observed, "recovery_total")
    ax.scatter(oq, orec, s=28, color="tab:blue", zorder=3, label="observed pool front (SU2)")

    # predicted front from the GP posterior mean
    pq = column(predicted, "q_peak_W_m2") / W_TO_KW
    ax.plot(pq, column(predicted, "recovery_total"), "-", color="0.25", lw=1.5,
            label="predicted front (GP mean)")

    # posterior band of the best recovery at each q level (levels with no sample are blank)
    lq = column(band, "q_peak_W_m2") / W_TO_KW
    p05, p95 = column(band, "rec_p05"), column(band, "rec_p95")
    ok = np.isfinite(p05) & np.isfinite(p95)
    ax.fill_between(lq[ok], p05[ok], p95[ok], color="tab:orange", alpha=0.35, lw=0,
                    label="posterior 5-95% band (50 samples)")

    # discretisation error on the observed point with the median q (upper median if even)
    i = np.argsort(oq)[len(oq) // 2]
    ax.errorbar(oq[i], orec[i], xerr=disc_q_pct / 100 * oq[i],
                yerr=disc_rec_pct / 100 * orec[i], fmt="none", ecolor="tab:purple",
                elinewidth=1.8, capsize=4, zorder=4,
                label="discretisation (grid study, medium to fine)")

    # inverse query answer: star at (median q, mean recovery), 90% box as error bars
    if inverse_json is not None:
        with open(inverse_json) as f:
            inv = json.load(f)
        if inv["feasible"]:
            q, rec = inv["q_peak_W_m2"], inv["recovery_total"]
            qm, rm = q["median"] / W_TO_KW, rec["mean"]
            xerr = [[(q["median"] - q["lo90"]) / W_TO_KW], [(q["hi90"] - q["median"]) / W_TO_KW]]
            yerr = [[rm - rec["lo90"]], [rec["hi90"] - rm]]
            ax.errorbar(qm, rm, xerr=xerr, yerr=yerr, fmt="*", ms=13, color="tab:green",
                        ecolor="tab:green", capsize=3, zorder=5,
                        label="inverse query answer (GP)")
            ax.axvline(inv["q_cap_W_m2"] / W_TO_KW, ls="--", color="0.3", lw=1,
                       label="heat-flux cap")

    ax.set_xlabel("q_peak (kW/m$^2$)")
    ax.set_ylabel("recovery_total (-)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="best")
    fig.text(0.5, 0.02, f"{len(observed)} observed points (SU2). Band: posterior uncertainty. "
             "Error bar: discretisation error (grid study).", ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    return len(observed)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("pareto_csv")
    ap.add_argument("--out", required=True, help="output PNG")
    ap.add_argument("--disc-rec-pct", type=float, required=True,
                    help="discretisation error of recovery_total, percent")
    ap.add_argument("--disc-q-pct", type=float, required=True,
                    help="discretisation error of q_peak, percent")
    ap.add_argument("--inverse", default=None, help="result.json of the inverse query")
    a = ap.parse_args()
    n = plot_pareto(a.pareto_csv, a.out, a.disc_rec_pct, a.disc_q_pct, a.inverse)
    print(f"{n} observed points; wrote {a.out}")


if __name__ == "__main__":
    main()

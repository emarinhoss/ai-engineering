"""Figures and summary of a replay CSV (strategy,seed,n,metric,value) from surrogate.replay.

Writes PREFIX_error_vs_n.png, PREFIX_calibration.png (largest n) and PREFIX_summary.md.
    python -m postprocess.plot_replay runs/replay/<date>/replay.csv --out-dir DIR --prefix replay
"""
import argparse
import csv
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")                                                  # no display needed
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

STRATEGIES = ("random", "lhs", "al_ehvi", "al_maxvar")
COLOURS = {"random": "#888888", "lhs": "#E69F00", "al_ehvi": "#0072B2", "al_maxvar": "#D55E00"}
ERROR_PANELS = (("rmse_recovery", "RMSE recovery_total [-]"),
                ("rmse_q_rel", "relative RMSE q_peak [-]"),
                ("hv_regret", "hypervolume regret [-]"))
LEVELS = (0.5, 0.8, 0.9, 0.95)


def load(csv_path):
    """-> (data[strategy][metric][n] = values over seeds, number of distinct seeds)."""
    data, seeds = {}, set()
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            seeds.add(r["seed"])
            cell = data.setdefault(r["strategy"], {}).setdefault(r["metric"], {})
            cell.setdefault(int(r["n"]), []).append(float(r["value"]))
    return data, len(seeds)


def values(data, s, metric, n):
    return data.get(s, {}).get(metric, {}).get(n, [])


def save(fig, strategies, path, extra=()):
    """One legend below the panels (strategies, then extra handles), then write the PNG."""
    handles = [Line2D([], [], color=COLOURS.get(s, "k"), marker="o", label=s) for s in strategies]
    handles += list(extra)
    fig.legend(handles=handles, loc="lower center", ncol=len(handles))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_error(data, strategies, path):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3))
    for ax, (metric, label) in zip(axes, ERROR_PANELS):
        for s in strategies:
            ns = sorted(data[s].get(metric, {}))
            if not ns:
                continue
            q25, med, q75 = np.array([np.percentile(values(data, s, metric, n), [25, 50, 75])
                                      for n in ns]).T
            ax.plot(ns, med, marker="o", color=COLOURS.get(s, "k"))
            ax.fill_between(ns, q25, q75, color=COLOURS.get(s, "k"), alpha=0.2, linewidth=0)
        ax.set(xlabel="number of CFD runs n", ylabel=label)
    save(fig, strategies, path)


def plot_calibration(data, strategies, n_last, path):
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.3), sharey=True)
    for ax, (kind, name) in zip(axes, (("recovery", "recovery_total"), ("q", "q_peak"))):
        ax.plot([0, 1], [0, 1], linestyle="--", color="grey")
        for s in strategies:
            vals = {lv: values(data, s, f"cov{round(lv * 100)}_{kind}", n_last) for lv in LEVELS}
            pts = [(lv, np.median(v)) for lv, v in vals.items() if v]   # missing levels skipped
            if pts:
                ax.plot(*zip(*pts), marker="o", color=COLOURS.get(s, "k"))
        ax.set(xlim=(0, 1), ylim=(0, 1), xticks=np.linspace(0, 1, 6), xlabel="nominal coverage level [-]",
               title=f"{name}, n = {n_last}")
    axes[0].set_ylabel("empirical coverage [-]")
    ideal = Line2D([], [], linestyle="--", color="grey", label="ideal y = x")
    save(fig, strategies, path, extra=[ideal])


def cell(vals):
    return f"{np.median(vals):.4g}" if vals else ""


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(r) + " |" for r in rows] + [""]


def write_summary(data, strategies, n_seeds, n_last, source, path):
    lines = [f"Input: {source}; seeds found: {n_seeds}", ""]
    for metric, _ in ERROR_PANELS:
        ns = sorted({n for s in strategies for n in data[s].get(metric, {})})
        rows = [[str(n)] + [cell(values(data, s, metric, n)) for s in strategies] for n in ns]
        lines += [f"### {metric}", ""] + md_table(["n"] + strategies, rows)
    lines += [f"### coverage at n = {n_last}", ""]
    for kind in ("recovery", "q"):
        rows = [[f"{lv:g}"] + [cell(values(data, s, f"cov{round(lv * 100)}_{kind}", n_last))
                               for s in strategies] for lv in LEVELS]
        lines += [f"#### {kind}", ""] + md_table(["nominal"] + strategies, rows)
    path.write_text("\n".join(lines))


def make_report(csv_path, out_dir, prefix):
    """Writes the three outputs and returns their paths."""
    data, n_seeds = load(csv_path)
    strategies = [s for s in STRATEGIES if s in data] + sorted(set(data) - set(STRATEGIES))
    n_last = max(n for s in strategies for m in data[s].values() for n in m)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    err, cal, summ = [Path(out_dir) / f"{prefix}_{name}"
                      for name in ("error_vs_n.png", "calibration.png", "summary.md")]
    plot_error(data, strategies, err)
    plot_calibration(data, strategies, n_last, cal)
    write_summary(data, strategies, n_seeds, n_last, Path(csv_path).name, summ)
    return [err, cal, summ]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("replay_csv")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prefix", required=True)
    a = ap.parse_args()
    for path in make_report(a.replay_csv, a.out_dir, a.prefix):
        print(path)


if __name__ == "__main__":
    main()

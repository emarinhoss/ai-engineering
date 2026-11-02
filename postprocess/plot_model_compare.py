"""Head-to-head of two replay CSVs that differ only in the surrogate (GP against MLP ensemble).

Spec: docs/specs/task4b_mlp_ensemble.md. Writes PREFIX.png (held-out RMSE of recovery, relative
RMSE of q_peak, hypervolume regret against n; median and interquartile band over seeds; GP solid,
MLP dashed; one color per strategy) and PREFIX.md (the medians as tables, and coverage at the
largest n). Every number comes from the two CSVs.
    python -m postprocess.plot_model_compare GP.csv MLP.csv --out-dir DIR --prefix NAME
"""
import argparse
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from postprocess.plot_replay import COLOURS, ERROR_PANELS, LEVELS, STRATEGIES, load, md_table, values

STYLE = {"GP": "-", "MLP ensemble": "--"}


def band(data, s, metric):
    """(n values, 25th, 50th, 75th percentile over seeds) for one strategy and metric."""
    ns = sorted(data.get(s, {}).get(metric, {}))
    if not ns:
        return [], [], [], []
    q = np.array([np.percentile(values(data, s, metric, n), [25, 50, 75]) for n in ns]).T
    return ns, q[0], q[1], q[2]


def plot(models, strategies, path):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
    for ax, (metric, label) in zip(axes, ERROR_PANELS):
        for name, data in models.items():
            for s in strategies:
                ns, lo, med, hi = band(data, s, metric)
                if ns:
                    ax.plot(ns, med, STYLE[name], marker="o", ms=3, color=COLOURS[s])
                    ax.fill_between(ns, lo, hi, color=COLOURS[s], alpha=0.12, linewidth=0)
        ax.set(xlabel="number of CFD runs n", ylabel=label)
        if metric.startswith("rmse"):
            ax.set_yscale("log")
    handles = [Line2D([], [], color=COLOURS[s], marker="o", label=s) for s in strategies]
    handles += [Line2D([], [], color="k", linestyle=STYLE[m], label=m) for m in models]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def summary(models, strategies, n_last, sources, path):
    names = list(models)
    lines = [f"Inputs: {sources[0]} (GP), {sources[1]} (MLP ensemble). Medians over seeds.", ""]
    for metric, _ in ERROR_PANELS:
        ns = sorted({n for d in models.values() for s in strategies for n in d.get(s, {}).get(metric, {})})
        header = ["n"] + [f"{s} {m}" for s in strategies for m in ("GP", "MLP")]
        rows = []
        for n in ns:
            row = [str(n)]
            for s in strategies:
                for name in names:
                    v = values(models[name], s, metric, n)
                    row.append(f"{np.median(v):.3g}" if v else "")
            rows.append(row)
        lines += [f"### {metric}", ""] + md_table(header, rows)
    lines += [f"### coverage at n = {n_last} (median over seeds)", ""]
    for kind in ("recovery", "q"):
        header = ["nominal"] + [f"{s} {m}" for s in strategies for m in ("GP", "MLP")]
        rows = []
        for lv in LEVELS:
            row = [f"{lv:g}"]
            for s in strategies:
                for name in names:
                    v = values(models[name], s, f"cov{round(lv * 100)}_{kind}", n_last)
                    row.append(f"{np.median(v):.2f}" if v else "")
            rows.append(row)
        lines += [f"#### {kind}", ""] + md_table(header, rows)
    path.write_text("\n".join(lines))


def make(gp_csv, mlp_csv, out_dir, prefix):
    models = {"GP": load(gp_csv)[0], "MLP ensemble": load(mlp_csv)[0]}
    strategies = [s for s in STRATEGIES if all(s in d for d in models.values())]
    n_last = max(n for d in models.values() for s in strategies for m in d[s].values() for n in m)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    png, md = Path(out_dir) / f"{prefix}.png", Path(out_dir) / f"{prefix}.md"
    plot(models, strategies, png)
    summary(models, strategies, n_last, (Path(gp_csv).as_posix(), Path(mlp_csv).as_posix()), md)
    return png, md


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gp_csv")
    ap.add_argument("mlp_csv")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prefix", required=True)
    a = ap.parse_args()
    for p in make(a.gp_csv, a.mlp_csv, a.out_dir, a.prefix):
        print(p)


if __name__ == "__main__":
    main()

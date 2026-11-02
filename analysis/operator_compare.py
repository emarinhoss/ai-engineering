"""Task 4c comparison: FNO ensemble against PCA + GP on the ramp-2 heat-flux profiles.

Spec: docs/specs/task4c_operator_profiles.md (every setting fixed there before any run).
Regime A: 5-fold cross-validation (fold permutation seed 0). Regime B: 24 random training designs,
the rest held out, 5 repeats (seeds 0 to 4). Each (regime, split) runs in its own process.

    python -m analysis.operator_compare --profiles runs/profiles/2026-11-02/profiles.csv \\
        --out runs/profiles/2026-11-02 --jobs 4
    python -m analysis.operator_compare --report runs/profiles/2026-11-02 --fig-dir docs/validation --prefix 2026-11-02_operator

Writes OUT/operator_compare.csv (regime, split, model, case_id, metric, value), OUT/figure_profiles.csv
(regime A predictions at the four figure designs), and with --report a figure and a summary table.
"""
import argparse
import csv
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import torch

from designs.make_pool import HIGH, LOW
from surrogate.fno import FNOEnsemble
from surrogate.gp import GP, Standardizer, scale_inputs
from surrogate.pca_gp import PCAGP

FOLDS, SMALL_N, REPEATS = 5, 24, 5
Z90 = 1.6448536269514722
FIGURE_DESIGNS = ((6.0, 6.0), (11.0, 6.0), (6.0, 13.0), (10.0, 12.0))   # fixed in the spec
MODELS = {"pca_gp": PCAGP, "fno": FNOEnsemble}


def load_profiles(path):
    rows = list(csv.DictReader(open(path)))
    qcols = [k for k in rows[0] if k.startswith("q_")]
    theta = np.array([[float(r["theta1_deg"]), float(r["theta2_deg"])] for r in rows])
    return {"case_id": [r["case_id"] for r in rows], "theta": theta,
            "X": scale_inputs(theta, list(zip(LOW, HIGH))).numpy(),
            "Q": np.array([[float(r[k]) for k in qcols] for r in rows]),
            "x0": np.array([float(r["x_start_m"]) for r in rows]), "x1": np.array([float(r["x_end_m"]) for r in rows])}


def splits(n):
    """-> list of (regime, split, train indices, test indices)."""
    out = []
    folds = np.array_split(np.random.default_rng(0).permutation(n), FOLDS)
    for k, test in enumerate(folds):
        out.append(("A", k, np.setdiff1d(np.arange(n), test), np.sort(test)))
    for r in range(REPEATS):
        train = np.sort(np.random.default_rng(r).choice(n, SMALL_N, replace=False))
        out.append(("B", r, train, np.setdiff1d(np.arange(n), train)))
    return out


def profile_metrics(q, log_mean, log_var, x0, x1):
    """Per-design metrics of one predicted profile (log-space mean and variance) against the truth q."""
    q_hat = np.exp(log_mean)
    s = np.linspace(0.0, 1.0, q.size)
    x = x0 + s * (x1 - x0)
    inside = np.abs(np.log(q) - log_mean) <= Z90 * np.sqrt(log_var)
    return {"rel_l2": float(np.linalg.norm(q_hat - q) / np.linalg.norm(q)),
            "max_rel": float(np.max(np.abs(q_hat / q - 1.0))),
            "peak_rel": float(abs(q_hat.max() / q.max() - 1.0)),
            "peak_x_mm": float(1e3 * abs(x[np.argmax(q_hat)] - x[np.argmax(q)])),
            "cov90": float(inside.mean())}


def run_split(args):
    """Fit both profile models and the scalar peak GP on one split; return rows and figure predictions."""
    data, regime, k, train, test = args
    torch.set_num_threads(1)
    Ylog = np.log(data["Q"])
    mu = Ylog[train].mean(0)
    sd = float((Ylog[train] - mu).std())
    Xtr, Xte = torch.tensor(data["X"][train]), torch.tensor(data["X"][test])
    Ytr = torch.tensor((Ylog[train] - mu) / sd)
    rows, figure = [], []
    for name, cls in MODELS.items():
        t0 = time.perf_counter()
        model = cls().fit(Xtr, Ytr)
        secs = time.perf_counter() - t0
        rows.append({"regime": regime, "split": k, "model": name, "case_id": "", "metric": "fit_seconds", "value": secs})
        if name == "pca_gp":
            rows.append({"regime": regime, "split": k, "model": name, "case_id": "", "metric": "components",
                         "value": model.k})
        mean, var = model.predict(Xte)
        log_mean, log_var = mu + sd * mean.numpy(), sd**2 * var.numpy()
        for j, i in enumerate(test):
            for metric, value in profile_metrics(data["Q"][i], log_mean[j], log_var[j], data["x0"][i], data["x1"][i]).items():
                rows.append({"regime": regime, "split": k, "model": name, "case_id": data["case_id"][i],
                             "metric": metric, "value": value})
            if regime == "A" and data["case_id"][i] in data["figure_ids"]:
                half = Z90 * np.sqrt(log_var[j])
                for kind, vals in (("mean", log_mean[j]), ("lo", log_mean[j] - half), ("hi", log_mean[j] + half)):
                    figure.append([data["case_id"][i], name, kind] + list(np.exp(vals)))
    # scalar GP on log of the profile peak, same training designs (secondary question of the spec)
    peak = np.log(data["Q"].max(1))
    st = Standardizer().fit(peak[train])
    gp = GP().fit(Xtr, st.transform(peak[train]))
    m, _ = gp.predict(Xte)
    pred = np.exp(st.inverse(m).numpy())
    for j, i in enumerate(test):
        rows.append({"regime": regime, "split": k, "model": "scalar_gp", "case_id": data["case_id"][i],
                     "metric": "peak_rel", "value": float(abs(pred[j] / data["Q"][i].max() - 1.0))})
    return rows, figure


def figure_ids(data):
    """Pool designs nearest to the four fixed points of the spec."""
    ids = []
    for t in FIGURE_DESIGNS:
        ids.append(data["case_id"][int(np.argmin(np.hypot(*(data["theta"] - np.array(t)).T)))])
    return ids


def compare(profiles_csv, out_dir, jobs=4):
    data = load_profiles(profiles_csv)
    data["figure_ids"] = figure_ids(data)
    tasks = [(data, *s) for s in splits(len(data["case_id"]))]
    rows, figure = [], []
    with Pool(jobs) as pool:
        for r, f in pool.imap_unordered(run_split, tasks):
            rows += r
            figure += f
    out = Path(out_dir)
    with open(out / "operator_compare.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("regime", "split", "model", "case_id", "metric", "value"))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["regime"], r["split"], r["model"], r["case_id"], r["metric"])))
    n = data["Q"].shape[1]
    with open(out / "figure_profiles.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "model", "kind"] + [f"q_{i}" for i in range(n)])
        w.writerows(sorted(figure, key=lambda r: (r[0], r[1], r[2])))
    return out / "operator_compare.csv"


def report(out_dir, fig_dir, prefix, profiles_csv):
    """Summary table (median and 90th percentile per regime, model, metric) and the figure."""
    import matplotlib as mpl
    mpl.use("Agg")
    import matplotlib.pyplot as plt

    rows = list(csv.DictReader(open(Path(out_dir) / "operator_compare.csv")))
    data = load_profiles(profiles_csv)
    cells = {}
    for r in rows:
        cells.setdefault((r["regime"], r["model"], r["metric"]), []).append(float(r["value"]))
    metrics = ("rel_l2", "max_rel", "peak_rel", "peak_x_mm", "cov90", "fit_seconds")
    lines = [f"Source: {Path(out_dir) / 'operator_compare.csv'}. Median (90th percentile) over held-out designs;",
             "fit_seconds per split (5 members for the FNO); cov90 is the mean fraction of the 128 points inside the band.", ""]
    for regime, title in (("A", "Regime A: 5-fold cross-validation (train 73 or 74)"), ("B", "Regime B: 24 training designs, 5 repeats")):
        lines += [f"### {title}", "", "| metric | PCA + GP | FNO ensemble | scalar GP (peak only) |", "|---|---|---|---|"]
        for m in metrics:
            row = [m]
            for model in ("pca_gp", "fno", "scalar_gp"):
                v = cells.get((regime, model, m))
                row.append(f"{np.median(v):.3g} ({np.percentile(v, 90):.3g})" if v else "")
            lines.append("| " + " | ".join(row) + " |")
        comp = cells.get((regime, "pca_gp", "components"))
        lines += ["", f"PCA components kept: {sorted(set(int(c) for c in comp))}" if comp else "", ""]
    Path(fig_dir, f"{prefix}_summary.md").write_text("\n".join(lines))

    fig_rows = list(csv.reader(open(Path(out_dir) / "figure_profiles.csv")))[1:]
    pred = {(r[0], r[1], r[2]): np.array([float(v) for v in r[3:]]) for r in fig_rows}
    colors = {"pca_gp": "#0072B2", "fno": "#D55E00", "scalar_gp": "#888888"}
    labels = {"pca_gp": "PCA + GP", "fno": "FNO ensemble", "scalar_gp": "scalar GP (peak)"}
    fig = plt.figure(figsize=(15, 7.6))
    gs = fig.add_gridspec(2, 4, height_ratios=[1.15, 1])
    for c, cid in enumerate(figure_ids(data)):
        i = data["case_id"].index(cid)
        x = 1e3 * (data["x0"][i] + np.linspace(0, 1, data["Q"].shape[1]) * (data["x1"][i] - data["x0"][i]))
        ax = fig.add_subplot(gs[0, c])
        ax.plot(x, data["Q"][i] / 1e3, color="k", lw=2, label="SU2 (held out)")
        for model in ("pca_gp", "fno"):
            ax.plot(x, pred[(cid, model, "mean")] / 1e3, color=colors[model], lw=1.4, label=labels[model])
            ax.fill_between(x, pred[(cid, model, "lo")] / 1e3, pred[(cid, model, "hi")] / 1e3, color=colors[model], alpha=0.2, lw=0)
        t1, t2 = data["theta"][i]
        ax.set(title=f"theta1 = {t1:.2f}, theta2 = {t2:.2f} deg", xlabel="x along ramp 2 (mm)")
        if c == 0:
            ax.set_ylabel("wall heat flux (kW/m^2)")
            ax.legend(fontsize=8, loc="lower right")
    for c, (metric, label) in enumerate((("rel_l2", "relative L2 error of the profile"), ("peak_rel", "relative error of the peak"))):
        ax = fig.add_subplot(gs[1, 2 * c:2 * c + 2])
        groups, names, cols = [], [], []
        for regime in ("A", "B"):
            for model in (("pca_gp", "fno", "scalar_gp") if metric == "peak_rel" else ("pca_gp", "fno")):
                v = cells.get((regime, model, metric))
                if v:
                    groups.append(v)
                    names.append(f"{labels[model]}\n{'all data' if regime == 'A' else '24 runs'}")
                    cols.append(colors[model])
        bp = ax.boxplot(groups, tick_labels=names, showfliers=True, patch_artist=True, widths=0.6)
        for patch, col in zip(bp["boxes"], cols):
            patch.set(facecolor=col, alpha=0.35)
        ax.set_yscale("log")
        ax.set_ylabel(label)
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle("Ramp-2 heat-flux profile from (theta1, theta2): held-out designs (5-fold CV, top; error distributions, bottom)", fontsize=11)
    fig.tight_layout()
    path = Path(fig_dir, f"{prefix}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profiles", default="runs/profiles/2026-11-02/profiles.csv")
    ap.add_argument("--out", help="run the comparison and write the CSVs here")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--report", help="directory holding operator_compare.csv: write summary and figure")
    ap.add_argument("--fig-dir", default="docs/validation")
    ap.add_argument("--prefix", default="2026-11-02_operator")
    a = ap.parse_args()
    if a.out:
        print(compare(a.profiles, a.out, a.jobs))
    if a.report:
        print(report(a.report, a.fig_dir, a.prefix, a.profiles))


if __name__ == "__main__":
    main()

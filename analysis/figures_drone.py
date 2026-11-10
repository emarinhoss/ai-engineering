"""Task 10 figures (T10.10e), drawn from committed records only.

Every function takes the repository root (so a test can point it at an empty tree) and an output
directory, returns the PNG path it wrote or None when an input file is missing, and prints
"not run: <missing file>" in that case. Nothing is drawn from a placeholder.

    python -m analysis.figures_drone            # all figures, into docs/validation/figures/task10/
"""
import csv
import glob
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path("docs/validation/figures/task10")
GRID_FRONT = "runs/drone_grid/2026-11-08/front.csv"
POOL_FRONT = "runs/drone_pool_lf/2026-11-08/front.csv"
POOL_REPLAY = "runs/replay_drone_pool/2026-11-08/replay.csv"
ONLINE = "runs/replay_drone_online/2026-11-08/online.csv"
ONLINE_FEAS = "runs/replay_drone_online/2026-11-08_feas/online.csv"
E387_RUNS = "runs/e387/*/result.json"
E387_TUNNEL = "data/validation/e387_uiuc.yaml"
SU2_POOL = "runs/pool_af/results.csv"          # written by T10.9d; absent until the pool is ingested
BIAS_TABLE = "runs/drone_bias/bias.csv"        # written by T10.10d; absent until the sweep is run
STRATEGY_COLOR = {"random": "#888888", "lhs": "#1f77b4", "al_ehvi": "#d62728",
                  "al_maxvar": "#9467bd", "al_ehvi_feas": "#2ca02c", "al_maxvar_feas": "#ff7f0e"}


def _missing(root, *rels):
    """First of the given relative paths that does not exist under root, else None."""
    for rel in rels:
        if not (Path(root) / rel).is_file():
            return rel
    return None


def _skip(root, *rels):
    miss = _missing(root, *rels)
    if miss is not None:
        print(f"not run: {miss}")
    return miss is not None


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _save(fig, out_dir, name):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _mean_by(rows, metric):
    """{strategy: (sorted n, mean value over seeds)} for one metric."""
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["metric"] == metric:
            acc[r["strategy"]][int(r["n"])].append(float(r["value"]))
    return {s: (sorted(d), [float(np.mean(d[n])) for n in sorted(d)]) for s, d in acc.items()}


def fig_front_lowfi(root=ROOT, out_dir=OUT_DIR):
    """(a) The exact 9^6 low-fidelity front and the 192-point pool's front, endurance against MTOW."""
    if _skip(root, GRID_FRONT, POOL_FRONT):
        return None
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for rel, label, style in ((GRID_FRONT, "exact front, 9^6 grid", {"color": "#1f77b4", "marker": "o", "s": 18}),
                              (POOL_FRONT, "192-point low pool front", {"color": "#d62728", "marker": "x", "s": 36})):
        rows = _read_csv(Path(root) / rel)
        x = [float(r["endurance_h"]) for r in rows]
        y = [float(r["mtow_kg"]) for r in rows]
        order = np.argsort(x)
        ax.scatter(x, y, label=f"{label} ({len(rows)} designs)", **style)
        ax.plot(np.array(x)[order], np.array(y)[order], color=style["color"], lw=0.8, alpha=0.6)
    ax.set_xlabel("endurance (h)")
    ax.set_ylabel("take-off mass (kg)")
    ax.set_title("Low-fidelity model: exact front and pool front")
    ax.legend()
    ax.grid(alpha=0.3)
    return _save(fig, out_dir, "a_front_lowfi.png")


def fig_pool_replay(root=ROOT, out_dir=OUT_DIR):
    """(b) Pool replay: hypervolume regret and held-out error against the number of evaluations."""
    if _skip(root, POOL_REPLAY):
        return None
    rows = _read_csv(Path(root) / POOL_REPLAY)
    panels = (("hv_regret", "hypervolume regret"), ("rmse_endurance", "held-out RMSE, endurance (h)"),
              ("rmse_mtow_rel", "held-out relative RMSE, MTOW"))
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))
    for ax, (metric, label) in zip(axes, panels):
        for s, (n, v) in _mean_by(rows, metric).items():
            ax.plot(n, v, marker="o", ms=3, label=s, color=STRATEGY_COLOR.get(s))
        ax.set_xlabel("evaluations n")
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
    axes[0].legend()
    fig.suptitle("Pool replay on the 192-point low pool: mean over seeds")
    return _save(fig, out_dir, "b_pool_replay.png")


def fig_online_regret(root=ROOT, out_dir=OUT_DIR):
    """(c) Online replay: mean regret and mean gated picks against n, six strategies."""
    if _skip(root, ONLINE, ONLINE_FEAS):
        return None
    rows = _read_csv(Path(root) / ONLINE) + _read_csv(Path(root) / ONLINE_FEAS)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
    for ax, metric, label in ((axes[0], "hv_regret", "hypervolume regret"),
                              (axes[1], "n_gated", "gated picks (cumulative)")):
        for s, (n, v) in _mean_by(rows, metric).items():
            ax.plot(n, v, marker="o", ms=3, label=s, color=STRATEGY_COLOR.get(s))
        ax.set_xlabel("evaluations n")
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle("Online replay on the low-fidelity model, unrestricted candidates: mean over seeds")
    return _save(fig, out_dir, "c_online_regret.png")


def _nominal_re(re, nominals):
    """Tunnel run whose nominal Reynolds number is nearest the case's, within 10 percent."""
    best = min(nominals, key=lambda n: abs(n - re))
    return best if abs(best - re) / best < 0.10 else None


def fig_e387_comparison(root=ROOT, out_dir=OUT_DIR):
    """(d) SU2 cl and cd against the UIUC E387 tunnel data at the same angles, one column per Re."""
    files = sorted(glob.glob(str(Path(root) / E387_RUNS)))
    if _skip(root, E387_TUNNEL) or not files:
        if files == []:
            print(f"not run: {E387_RUNS}")
        return None
    tunnel = yaml.safe_load((Path(root) / E387_TUNNEL).read_text())["polars"]
    by_nom = {p["nominal_reynolds"]: p for p in tunnel}
    su2, su2_re = defaultdict(list), {}
    for f in files:
        with open(f) as fh:
            r = json.load(fh)
        if r["params"].get("mesh_level") != "medium":   # fine cases (decision 11) are V6e mesh only
            continue
        nom = _nominal_re(r["params"]["reynolds"], list(by_nom))
        if nom is not None:
            su2_re[nom] = r["params"]["reynolds"]
            su2[nom].append((r["params"]["alpha_deg"], r["metrics"]["cl"], r["metrics"]["cd"]))
    if not su2:
        print(f"not run: {E387_RUNS} (no case matches a tunnel Reynolds number)")
        return None
    res = sorted(su2)
    fig, axes = plt.subplots(2, len(res), figsize=(5.2 * len(res), 6.8), squeeze=False,
                             constrained_layout=True)
    counts = []
    for j, nom in enumerate(res):
        pts = sorted(su2[nom])
        a, cl, cd = (np.array(c) for c in zip(*pts))
        t = by_nom[nom]
        ta, tcl, tcd = np.array(t["alpha_deg"]), np.array(t["cl"]), np.array(t["cd"])
        for i, (sv, tv, name) in enumerate(((cl, tcl, "cl"), (cd, tcd, "cd"))):
            ax = axes[i][j]
            ax.plot(ta, tv, "-o", color="#555555", ms=3, label=f"tunnel run {t['run']}")
            ax.plot(a, sv, "s", color="#d62728", ms=7, label="SU2 (medium, SA-BCM)")
            ax.set_xlabel("angle of attack (deg)")
            ax.set_ylabel(name)
            ax.grid(alpha=0.3)
            if i == 0:
                ax.set_title(f"Re {su2_re[nom]:,.0f} (tunnel nominal {nom:,.0f}): "
                             f"{len(pts)} SU2 point{'s' if len(pts) != 1 else ''}")
                ax.legend(fontsize=8)
        counts.append(f"Re {su2_re[nom]:,.0f}: {len(pts)}")
    fig.suptitle("E387: SU2 against the UIUC tunnel (" + "; ".join(counts) + " SU2 points drawn)")
    return _save(fig, out_dir, "d_e387_comparison.png")


def fig_front_band(root=ROOT, out_dir=OUT_DIR):
    """Front with the GPs' band over the SU2 pool. Needs the SU2 pool results."""
    if _skip(root, SU2_POOL):
        return
    raise NotImplementedError("inputs exist; the drawing is written with its analysis")


def fig_mf_error(root=ROOT, out_dir=OUT_DIR):
    """Multi-fidelity held-out error against the number of SU2 designs. Needs the SU2 pool."""
    if _skip(root, SU2_POOL):
        return
    raise NotImplementedError("inputs exist; the drawing is written with its analysis")


def fig_bias_table(root=ROOT, out_dir=OUT_DIR):
    """Ranked bias table. Needs the bias sweep of spec section 10.5."""
    if _skip(root, BIAS_TABLE):
        return
    raise NotImplementedError("inputs exist; the drawing is written with its analysis")


FIGURES = (fig_front_lowfi, fig_pool_replay, fig_online_regret, fig_e387_comparison,
           fig_front_band, fig_mf_error, fig_bias_table)

CAPTIONS = {
    "a_front_lowfi.png": ("Exact Pareto front of the low-fidelity model over the 9^6 grid and the front of "
                          "the 192-point low pool, endurance against take-off mass. Sources: "
                          f"`{GRID_FRONT}`, `{POOL_FRONT}`."),
    "b_pool_replay.png": ("Pool replay on the 192-point low pool: mean hypervolume regret and held-out "
                          f"RMSE against evaluations, 10 seeds. Source: `{POOL_REPLAY}`."),
    "c_online_regret.png": ("Online replay, unrestricted candidates: mean regret and gated picks for the "
                            "four strategies and the two feasibility-weighted ones. Sources: "
                            f"`{ONLINE}`, `{ONLINE_FEAS}`."),
    "d_e387_comparison.png": ("SU2 cl and cd against the UIUC E387 tunnel data at the same angles, one "
                              "column per Reynolds number with a complete or partial set. Sources: "
                              f"`{E387_RUNS}`, `{E387_TUNNEL}`."),
}


def write_captions(root, out_dir, drawn):
    """captions.md: one line per PNG actually drawn, naming its source files."""
    lines = ["# Task 10 figures: captions", ""]
    lines += [f"- `{p.name}`: {CAPTIONS[p.name]}" for p in drawn if p.name in CAPTIONS]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "captions.md").write_text("\n".join(lines) + "\n")


def main(root=ROOT, out_dir=None):
    out_dir = Path(out_dir) if out_dir else Path(root) / OUT_DIR
    drawn, skipped = [], []
    for fn in FIGURES:
        p = fn(root, out_dir)
        (drawn if p else skipped).append(p if p else fn.__name__)
    write_captions(root, out_dir, drawn)
    print("drawn:", [p.name for p in drawn])
    print("skipped:", skipped)
    return drawn, skipped


if __name__ == "__main__":
    main()

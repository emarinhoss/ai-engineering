"""Where an airfoil2d run spends its iterations, from its recorded history.csv(.gz).

    python -m analysis.history_cost RUN_DIR [RUN_DIR ...] --out runs/history_cost/<date>

Two questions about the cost of an SU2 run, answered from the record and nothing else:
  1. Linear solver effort: FGMRES iterations per step, the residual it reaches, share of steps at the cap.
  2. Where the iterations go: when the adaptive CFL reaches its ceiling, and the last iteration at
     which cl and cd are still outside a band around their final values.
Reports only. It changes no run and makes no claim about what a different setting would do.
"""
import argparse
import csv
import gzip
import json
import re
from pathlib import Path

import numpy as np

BANDS = (0.05, 0.02, 0.01, 0.005, 0.002)


def read_history(run_dir):
    gz = Path(run_dir) / "history.csv.gz"          # the repo keeps .gz, the Drive queue keeps .csv
    with (gzip.open(gz, "rt") if gz.exists() else open(Path(run_dir) / "history.csv", newline="")) as f:
        rows = list(csv.reader(f))
    names = [c.strip().strip('"') for c in rows[0]]
    data = np.array([[float(x) for x in r] for r in rows[1:]])
    return {n: data[:, i] for i, n in enumerate(names)}


def cfg_value(run_dir, key):
    m = re.search(rf"^{key}= *(.+)$", (Path(run_dir) / "case.cfg").read_text(), re.MULTILINE)
    return m.group(1).strip() if m else None


def last_outside(x, band):
    """Number of iterations after which x stays within `band` (relative) of its final value."""
    bad = np.nonzero(np.abs(x / x[-1] - 1.0) > band)[0]
    return int(bad[-1] + 1) if len(bad) else 0


def analyse(run_dir):
    h = read_history(run_dir)
    res = json.loads((Path(run_dir) / "result.json").read_text())
    n = len(h["CL"])
    cap = int(cfg_value(run_dir, "LINEAR_SOLVER_ITER"))
    ceiling = float(cfg_value(run_dir, "CFL_ADAPT_PARAM").strip("() ").split(",")[3])
    at_ceiling = np.nonzero(h["Avg CFL"] >= 0.995 * ceiling)[0]
    return {
        "case_id": res["case_id"], "tag": res["params"].get("tag"),
        "reynolds": res["params"]["reynolds"], "restart_from": res["params"].get("restart_from"),
        "exit_code": res["run"]["exit_code"], "mesh_level": res["params"]["mesh_level"],
        "alpha_deg": res["params"]["alpha_deg"], "iterations": n, "max_iter": res["params"]["max_iter"],
        "wall_s": res["run"]["wall_time_s"],
        "linear": {"tolerance": cfg_value(run_dir, "LINEAR_SOLVER_ERROR"), "cap": cap,
                   "mean_iters": float(h["LinSolIter"].mean()), "max_iters": float(h["LinSolIter"].max()),
                   "share_at_cap": float((h["LinSolIter"] >= cap).mean()),
                   "mean_log10_residual": float(h["LinSolRes"].mean()),
                   "mean_iters_turb": float(h["LinSolIterTurb"].mean())},
        "cfl": {"ceiling": ceiling,
                "first_iter_at_ceiling": int(at_ceiling[0]) if len(at_ceiling) else None,
                "share_of_run_at_ceiling": float(len(at_ceiling) / n)},
        "settle": {q: {str(b): last_outside(h[col], b) for b in BANDS}
                   for q, col in (("cl", "CL"), ("cd", "CD"))},
        "drift_pct": {q: res["convergence"]["drift_pct"][q] for q in ("cl", "cd")},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = [analyse(d) for d in a.run_dirs]
    print(f"{len(out)} runs", flush=True)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "history_cost.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

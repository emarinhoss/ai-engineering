"""Low-fidelity design grid and its exact Pareto front (T10.9a).

    python -m analysis.drone_grid --points 9 --workers N --out DIR [--design CSV] [--level medium]

Evaluates the P^6 grid (index order: see LOOP_ORDER) over designs.make_pool_drone LOW..HIGH (or the rows of a design CSV) with
drone.evaluate.evaluate and writes to DIR:
  grid.csv     index, the six inputs, every scalar output, mass_<name>, gates, error
  front.csv    exact Pareto front (max endurance_h, min mtow_kg) of the clean rows, mtow ascending
  record.json  counts, timing, commit, file hashes, ledger hashes, library versions
Objectives in minimisation form as in the spec: f1 = -endurance_h, f2 = log(mtow_kg).
"""
import argparse
import csv
import datetime
import hashlib
import itertools
import json
import math
import multiprocessing
import os
import subprocess
import time
from pathlib import Path

import numpy as np

from analysis.pareto import front_2d
from designs.make_pool_drone import HIGH, INPUTS, LOW
from drone import ledger
from drone.evaluate import evaluate

SCALARS = ("endurance_h", "mtow_kg", "range_km", "v_cruise", "v_stall", "wing_loading",
           "re_cruise", "throttle_cruise", "static_margin", "cl_max", "e_span", "cd0",
           "closure_iterations", "closure_residual")
MASSES = ("payload", "battery", "wing_skin", "spar", "tail", "fuselage", "propulsion")
COLUMNS = (("index",) + INPUTS + SCALARS + tuple("mass_" + n for n in MASSES)
           + ("gates", "error"))
# Grid order: aspect_ratio, taper_ratio, camber_pct are the OUTER loops and span_m,
# battery_fraction, thickness_pct the inner ones, so the points sharing one cached lattice key
# (AR, taper, camber) are contiguous and every chunk of 64 hits drone.evaluate._aero's cache.
# The index column follows this order.
LOOP_ORDER = ("aspect_ratio", "taper_ratio", "camber_pct", "span_m", "battery_fraction",
              "thickness_pct")
_FIXED = None
_LEVEL = "medium"


def _init(level):
    global _FIXED, _LEVEL
    _FIXED = ledger.load_all()
    _LEVEL = level


def _row(item):
    """Evaluate one (index, inputs) pair and return a flat dict keyed by COLUMNS."""
    index, x = item
    row = {"index": index, **dict(zip(INPUTS, x)), "gates": "", "error": ""}
    params = {"family": "drone", "fidelity": "low", "tag": "grid", **row_inputs(row)}
    try:
        out = evaluate(params, _FIXED, level=_LEVEL)
    except ValueError as exc:
        row["error"] = str(exc)
        return row
    for k in SCALARS:
        row[k] = out[k]
    for k, v in out["masses"].items():
        row["mass_" + k] = v
    row["gates"] = " | ".join(out["gates"])
    return row


def row_inputs(row):
    return {k: float(row[k]) for k in INPUTS}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_design(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return [(int(r["index"]), tuple(float(r[k]) for k in INPUTS)) for r in rows]


def build_grid(points):
    axes = {k: np.linspace(lo, hi, points) for k, lo, hi in zip(INPUTS, LOW, HIGH)}
    items = []
    for i, x in enumerate(itertools.product(*(axes[k] for k in LOOP_ORDER))):
        d = dict(zip(LOOP_ORDER, x))
        items.append((i, tuple(float(d[k]) for k in INPUTS)))
    return items


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, restval="")
        w.writeheader()
        w.writerows(rows)


def front_rows(rows):
    clean = [r for r in rows if not r["gates"] and not r["error"]]
    if not clean:
        return []
    F = np.array([[-r["endurance_h"], math.log(r["mtow_kg"])] for r in clean])
    keep = [clean[i] for i in front_2d(F)]
    return sorted(keep, key=lambda r: r["mtow_kg"])


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--points", type=int, default=9)
    ap.add_argument("--design", default=None, help="design CSV with an index column")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--out", required=True)
    ap.add_argument("--level", default="medium")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    items = read_design(args.design) if args.design else build_grid(args.points)
    n = len(items)
    started = datetime.datetime.now(datetime.timezone.utc)
    t0 = time.time()
    rows, next_report = [], 1
    with multiprocessing.Pool(args.workers, _init, (args.level,)) as pool:
        for r in pool.imap(_row, items, chunksize=64):
            rows.append(r)
            if len(rows) * 10 >= next_report * n:
                print(f"{len(rows)}/{n} ({10 * (next_report)}%) {time.time() - t0:.0f} s",
                      flush=True)
                next_report = len(rows) * 10 // n + 1
    wall = time.time() - t0
    ended = datetime.datetime.now(datetime.timezone.utc)

    write_csv(out / "grid.csv", rows)
    front = front_rows(rows)
    write_csv(out / "front.csv", front)

    failed = sum(1 for r in rows if r["error"])
    gated = sum(1 for r in rows if r["gates"])
    clean = sum(1 for r in rows if not r["gates"] and not r["error"])
    import torch
    record = {
        "points": args.points if not args.design else None,
        "design": args.design,
        "workers": args.workers,
        "level": args.level,
        "commit": git_commit(),
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "wall_seconds": wall,
        "points_evaluated": n,
        "points_clean": clean,
        "points_gated": gated,
        "points_failed": failed,
        "front_size": len(front),
        "sha256": {"grid.csv": sha256(out / "grid.csv"), "front.csv": sha256(out / "front.csv")},
        "ledger_sha256": {p.name: sha256(p) for p in sorted(Path("data/drone").glob("*.yaml"))},
        "numpy": np.__version__,
        "torch": torch.__version__,
    }
    (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"evaluated {n} in {wall:.1f} s: clean {clean}, gated {gated}, failed {failed}, "
          f"front {len(front)}")


if __name__ == "__main__":
    main()

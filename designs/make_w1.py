"""Stage the W1 timed runs (docs/specs/task11_fno_exploration.md, experiment W1; task W1.8).

    python -m designs.make_w1 --field-queue /content/drive/MyDrive/su2queue_w1 \
        --queue /content/drive/MyDrive/su2queue_w1t --fields <fields.npz> --model <model.npz>

Runs on a runtime with Drive mounted, after Gate A (the control) and Gate B (the frozen model).
Seven test cases (CASES). For each: the nearest training case in (camber, thickness, log10 Re,
angle), each scaled to the training range; its restart file rescaled to this case's Reynolds
number and written with this case's mesh coordinates (the nearest-case start); the field predicted
by the frozen model, written the same way (the learned start). The time to prepare each file is
measured and recorded. Six runs per case are staged in ORDER, a second apart so that the staging
order is the run order. Writes designs/w1_cases.csv and <queue>/jobs/w1.batch.json.
"""
import argparse
import csv
import hashlib
import math
import tempfile
import time
from pathlib import Path

import numpy as np

from designs.make_e0 import stage
from designs.make_w1_field import sections
from mcp_server import queue as q
from surrogate.field_pca_gp import FieldPCAGP
from worker import startfile as sf
from worker.make_case import make
from worker.restart import read_su2_coords

HERE = Path(__file__).parent
CASES = {"d1_2": (1, 2.0), "d1_4": (1, 4.0), "d1_6": (1, 6.0), "d1_10": (1, 10.0),
         "d4_2": (4, 2.0), "d4_6": (4, 6.0), "d4_10": (4, 10.0)}
ORDER = (("w1_cold_a", "cold"), ("w1_near_a", "near"), ("w1_learn_a", "learn"),
         ("w1_learn_b", "learn"), ("w1_near_b", "near"), ("w1_cold_b", "cold"))


def base(name):
    design, alpha = CASES[name]
    return {**sections()[design], "mesh_level": "coarse", "alpha_deg": alpha, "max_iter": 6000}


def inputs(p):
    return [p["camber_pct"], p["thickness_pct"], math.log10(p["reynolds"]), p["alpha_deg"]]


def nearest(X, x):
    """Index of the row of X nearest to x, each input scaled to the range of X."""
    X = np.asarray(X, dtype=float)
    lo, hi = X.min(0), X.max(0)
    return int(np.argmin(np.linalg.norm((X - np.asarray(x)) / (hi - lo), axis=1)))


def mesh_coords(p):
    with tempfile.TemporaryDirectory() as tmp:
        make(p, tmp)
        return read_su2_coords(Path(tmp) / "mesh.su2")


def write_start(path, text):
    Path(path).write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--field-queue", required=True)
    ap.add_argument("--queue", required=True)
    ap.add_argument("--fields", required=True)
    ap.add_argument("--model", required=True)
    a = ap.parse_args(argv)
    z = np.load(a.fields)
    model = FieldPCAGP.load(a.model)
    starts = Path(a.queue) / "starts"
    starts.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in CASES:
        p = base(name)
        coords, re, x = mesh_coords(p), p["reynolds"], inputs(p)
        donor = str(z["case_ids"][nearest(z["X"], x)])
        t0 = time.perf_counter()
        header, data = sf.read_restart((Path(a.field_queue) / "runs" / donor / "restart_flow.csv").read_text())
        donor_re = 10 ** z["X"][list(z["case_ids"]).index(donor)][2]
        f = sf.unscale(sf.scale(sf.fields(header, data), donor_re), re)
        sha = {"near": write_start(starts / f"w1_near_{name}.csv", sf.write_solution(coords, f))}
        prep = {"near": time.perf_counter() - t0}
        t0 = time.perf_counter()
        f = sf.unscale(model.predict(x), re)
        sha["learn"] = write_start(starts / f"w1_learn_{name}.csv", sf.write_solution(coords, f))
        prep["learn"] = time.perf_counter() - t0
        for tag, start in ORDER:
            extra = {} if start == "cold" else {"start_file": f"w1_{start}_{name}.csv"}
            rows.append({"case_id": stage({**p, "tag": tag, **extra}), "set": tag, "case": name,
                         "start": start, "start_file": extra.get("start_file", ""),
                         "donor": donor if start == "near" else "",
                         "prep_s": round(prep[start], 3) if start != "cold" else 0.0,
                         "start_sha256": sha.get(start, "")})
            time.sleep(1.1)                  # distinct created_at, so staging order = run order
    with open(HERE / "w1_cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ids = [r["case_id"] for r in rows]
    text = q.export_batch(ids, path=str(Path(a.queue) / "jobs" / "w1.batch.json"))
    print(f"w1: {len(ids)} runs, batch sha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Ramp-2 wall heat-flux profiles on a common grid (Task 4c, docs/specs/task4c_operator_profiles.md).

For each case: rebuild the mesh from params.json (worker.make_case.make; the fingerprint must equal
the recorded one), read the surface file, take the ramp-2 nodes of the heating objective
(postprocess.metrics.ramp2_window: x >= X1, 2 mm before the throat left out), and interpolate q
linearly onto N points of s = (x - x_start) / (x_end - x_start) in [0, 1].

    python -m analysis.profiles --surfaces runs/profiles/2026-11-02/surfaces --check runs/profiles/2026-11-02/rerun_check.csv \\
        --out runs/profiles/2026-11-02/profiles.csv
"""
import argparse
import csv
import gzip
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

from postprocess import surface
from postprocess.metrics import ramp2_window
from worker.make_case import make

N_POINTS = 128
MATCH_TOL = 1e-6          # re-run accepted if recovery_total and q_peak equal the record to this


def extract(params, surface_gz, expected_fingerprint=None, n=N_POINTS):
    """-> dict(s, q, x, x_start, x_end, q_peak_nodes) for one case."""
    with tempfile.TemporaryDirectory() as tmp:
        job = make(params, tmp)
        if expected_fingerprint and job["mesh_fingerprint"] != expected_fingerprint:
            raise ValueError("rebuilt mesh fingerprint differs from the record")
        (Path(tmp) / "params.json").write_text(json.dumps(params))
        with gzip.open(surface_gz, "rb") as src, open(Path(tmp) / "surface_flow.dat", "wb") as dst:
            shutil.copyfileobj(src, dst)
        surf = surface.load(tmp)
        geometry = json.loads((Path(tmp) / "geometry.json").read_text())
    ramp2 = ramp2_window(surf, geometry)
    order = np.argsort(ramp2["x"])
    x, q = ramp2["x"][order], ramp2["q"][order]
    if not np.all(q > 0):
        raise ValueError("heat flux not positive on every ramp-2 node")
    s_nodes = (x - x[0]) / (x[-1] - x[0])
    s = np.linspace(0.0, 1.0, n)
    return {"s": s, "q": np.interp(s, s_nodes, q), "x": x[0] + s * (x[-1] - x[0]),
            "x_start": float(x[0]), "x_end": float(x[-1]), "q_peak_nodes": float(q.max())}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surfaces", required=True)
    ap.add_argument("--check", required=True, help="rerun_check.csv of analysis.rerun_surfaces")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows, skipped = [], []
    for r in csv.DictReader(open(a.check)):
        cid = r["case_id"]
        ok = r["rel_diff_recovery"] not in ("", None) and float(r["rel_diff_recovery"]) <= MATCH_TOL \
            and float(r["rel_diff_q"]) <= MATCH_TOL
        if not ok:
            skipped.append((cid, r["status"], r.get("rel_diff_recovery"), r.get("rel_diff_q")))
            continue
        record = json.loads(Path(f"runs/pool/{cid}/result.json").read_text())
        params = json.loads(Path(f"runs/pool/{cid}/params.json").read_text())
        prof = extract(params, Path(a.surfaces) / f"{cid}.surface_flow.dat.gz", record["job"]["mesh_fingerprint"])
        q_rec = record["metrics"]["q_peak_W_m2"]
        if not (prof["q"].max() <= q_rec * (1 + 1e-9) and prof["q"].max() >= 0.995 * q_rec):
            raise ValueError(f"{cid}: profile max {prof['q'].max():.1f} against recorded q_peak {q_rec:.1f}")
        rows.append([cid, params["theta1_deg"], params["theta2_deg"], prof["x_start"], prof["x_end"]]
                    + [f"{v:.6g}" for v in prof["q"]])
    rows.sort()
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "theta1_deg", "theta2_deg", "x_start_m", "x_end_m"] + [f"q_{i}" for i in range(N_POINTS)])
        w.writerows(rows)
    print(f"{len(rows)} profiles -> {a.out}; skipped {len(skipped)}: {skipped}")


if __name__ == "__main__":
    main()

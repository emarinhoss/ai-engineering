"""Stage the W1 control (docs/specs/task11_fno_exploration.md, experiment W1; task W1.2, Gate A).

    python -m designs.make_w1_control --donor-queue /content/drive/MyDrive/su2queue \
        --queue /content/drive/MyDrive/su2queue_w1t

Runs on a runtime with Drive mounted. Pool design 1, coarse, 6 deg, restarted from the restart file
of its E0 cold run (DONOR) twice: once with that file copied unchanged (w1_control_raw.csv) and
once passed through worker/startfile.py, read, scaled, unscaled and written with this case's own
mesh coordinates (w1_control_writer.csv). Both must give the E0 cold cl and cd within that run's
recorded drift; if not, the writer is wrong and nothing else is staged. Also records how far the
donor file's coordinates are from this case's mesh nodes. Writes designs/w1_control_cases.csv and
the batch file <queue>/jobs/w1_control.batch.json.
"""
import argparse
import csv
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np

from designs.make_e0 import stage
from designs.make_w1_field import sections
from mcp_server import queue as q
from worker import startfile as sf
from worker.make_case import make
from worker.restart import read_su2_coords

HERE = Path(__file__).parent
DONOR = "airfoil2d-f94ff4a147"        # E0 cold run, pool design 1, coarse, 6 deg (designs/e0_cases.csv)


def params(start_file):
    return {**sections()[1], "mesh_level": "coarse", "alpha_deg": 6.0, "max_iter": 6000,
            "tag": "w1_control", "start_file": start_file}


def mesh_coords(p):
    with tempfile.TemporaryDirectory() as tmp:
        make({k: v for k, v in p.items() if k != "start_file"}, tmp)
        return read_su2_coords(Path(tmp) / "mesh.su2")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--donor-queue", required=True)
    ap.add_argument("--queue", required=True)
    a = ap.parse_args(argv)
    starts = Path(a.queue) / "starts"
    starts.mkdir(parents=True, exist_ok=True)
    donor = Path(a.donor_queue) / "runs" / DONOR / "restart_flow.csv"
    coords = mesh_coords(params("x.csv"))
    header, data = sf.read_restart(donor.read_text())
    gap = float(np.abs(data[:, 1:3] - coords).max())
    shutil.copyfile(donor, starts / "w1_control_raw.csv")
    re = sections()[1]["reynolds"]
    text = sf.write_solution(coords, sf.unscale(sf.scale(sf.fields(header, data), re), re))
    (starts / "w1_control_writer.csv").write_text(text)
    rows = []
    for name in ("w1_control_raw.csv", "w1_control_writer.csv"):
        rows.append({"case_id": stage(params(name)), "set": "w1_control", "start_file": name,
                     "donor": DONOR, "max_coord_gap_m": gap})
        time.sleep(1.1)
    with open(HERE / "w1_control_cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ids = [r["case_id"] for r in rows]
    q.export_batch(ids, path=str(Path(a.queue) / "jobs" / "w1_control.batch.json"))
    print(f"w1_control: {ids}, donor coordinates differ from this mesh by at most {gap:.3e} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

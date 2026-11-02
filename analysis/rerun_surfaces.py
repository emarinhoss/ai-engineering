"""Re-run pool cases locally to recover their wall surface files (Task 4c, 1D operator data).

The Colab worker brought back only result.json; the surface files stayed on Drive. This script
re-stages every pool case from its recorded params.json (same pipeline: schema, gates, mesh,
config), runs SU2 serially, checks that recovery_total and q_peak equal the Colab record, and keeps
the surface file and the marker map. Nothing here chooses a design: the list is runs/pool/*.

    python -m analysis.rerun_surfaces --su2-cmd /path/to/SU2_CFD --work DIR --out runs/profiles/2026-11-02 --jobs 4

Writes OUT/surfaces/<case_id>.surface_flow.dat.gz, OUT/surfaces/<case_id>.mesh_markers.json and
OUT/rerun_check.csv (one row per case: local and recorded metrics, relative differences, status).
Cases already in rerun_check.csv are skipped, so the script can be restarted.
"""
import argparse
import csv
import gzip
import json
import os
import shutil
from multiprocessing import Pool
from pathlib import Path

POOL = Path("runs/pool")
FIELDS = ("case_id", "status", "iterations", "recovery_total_local", "recovery_total_record",
          "q_peak_local", "q_peak_record", "rel_diff_recovery", "rel_diff_q", "wall_time_s")


def rerun_one(args):
    """Stage, run and check one pool case. Returns a row for rerun_check.csv."""
    case_id, su2_cmd, work, out = args
    os.environ["SU2_QUEUE_DIR"] = str(work)              # scratch queue, read by mcp_server.queue
    from mcp_server import queue                          # noqa: E402  (after the environment is set)
    from worker.run_case import run

    params = json.loads((POOL / case_id / "params.json").read_text())
    record = json.loads((POOL / case_id / "result.json").read_text())["metrics"]
    staged = queue.create(params, force=True)
    if not staged.get("ok") or staged["case_id"] != case_id:
        return {"case_id": case_id, "status": f"staging failed: {staged.get('stage')} {staged.get('case_id')}"}
    case_dir = Path(staged["path"])
    run(case_dir, su2_cmd, timeout_s=3600)
    result = json.loads((case_dir / "result.json").read_text())
    local = result.get("metrics", {})
    row = {"case_id": case_id, "status": result.get("history_summary", {}).get("status"),
           "iterations": result["run"]["iterations"], "wall_time_s": round(result["run"]["wall_time_s"], 1),
           "recovery_total_local": local.get("recovery_total"), "recovery_total_record": record["recovery_total"],
           "q_peak_local": local.get("q_peak_W_m2"), "q_peak_record": record["q_peak_W_m2"]}
    if row["recovery_total_local"] is not None and row["q_peak_local"] is not None:
        row["rel_diff_recovery"] = abs(row["recovery_total_local"] / row["recovery_total_record"] - 1)
        row["rel_diff_q"] = abs(row["q_peak_local"] / row["q_peak_record"] - 1)
    surf_dir = Path(out) / "surfaces"
    surf_dir.mkdir(parents=True, exist_ok=True)
    with open(case_dir / "surface_flow.dat", "rb") as src, gzip.open(surf_dir / f"{case_id}.surface_flow.dat.gz", "wb") as dst:
        shutil.copyfileobj(src, dst)
    shutil.copy(case_dir / "mesh_markers.json", surf_dir / f"{case_id}.mesh_markers.json")
    shutil.rmtree(case_dir)                               # mesh and history are not kept
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--su2-cmd", required=True)
    ap.add_argument("--work", required=True, help="scratch queue directory")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    check = out / "rerun_check.csv"
    done = set()
    if check.exists():
        done = {r["case_id"] for r in csv.DictReader(open(check))}
    todo = sorted(p.name for p in POOL.iterdir() if (p / "result.json").exists() and p.name not in done)
    print(f"{len(todo)} cases to run, {len(done)} already done")
    new_file = not check.exists()
    with open(check, "a", newline="") as f, Pool(a.jobs) as pool:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for row in pool.imap_unordered(rerun_one, [(c, a.su2_cmd, a.work, out) for c in todo]):
            w.writerow(row)
            f.flush()
            print(row["case_id"], row["status"], row.get("rel_diff_recovery"), row.get("rel_diff_q"), flush=True)


if __name__ == "__main__":
    main()

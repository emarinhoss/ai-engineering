"""Task 9 pool diagnosis, part 2 (2026-11-04): are the seven NS pool failures start-up failures?

What the records show (see the README written next to the runs): every failed run's residual bottoms
out at -3.3 to -4.4 inside the first 180 iterations and then rises by 3.5 to 10 orders within a few
hundred; converged runs reach about -6 at the same stage. The earlier snapshot diagnosis
(runs/dev/2026-11-03_pool3r_fail_diag) put the onset at the cowl corner of the duct outlet, where the
imposed back pressure meets the uniform freestream initial state. SU2 v8.2.0's RAMP_OUTLET_PRESSURE
does nothing for MARKER_OUTLET (checked: identical histories with and without), so the gentle start
is done by hand in two stages with a restart. Two variants, each the pool config plus the edits
recorded in edits.json:

  pramp  stage 1: duct back pressure = freestream pressure (consistent with the initial state), 500
         iterations; stage 2: the pool config, restarted from stage 1.
  cfl2   stage 1: CFL cap 2 instead of 20, 1000 iterations; stage 2: the pool config, restarted.

Stage 2 has the pool numerics and the pool boundary conditions, so a converged stage 2 is the pool's
own fixed point reached by another path. Two converged pool cases run as controls: their stage-2
metrics must match their pool records. Nothing here replaces a pool record.

    python -m analysis.diag_pool3r_startup --cases ID [ID ...] --su2-cmd SU2_CFD --out runs/dev/<dir> [--jobs 3]
"""
import argparse
import gzip
import json
import re
import shutil
import subprocess
import time
from multiprocessing import Pool
from pathlib import Path

from worker.make_case import make
from worker.run_case import run

POOL = Path("runs/pool3r/ns")
VARIANTS = ("pramp", "cfl2")


def stage1_edits(variant, text):
    """(old, new) replacements that turn the pool config into the stage-1 config."""
    common = [("ITER= 8000", "ITER= 500" if variant == "pramp" else "ITER= 1000"),
              ("OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII )", "OUTPUT_FILES= ( RESTART )")]
    if variant == "pramp":
        outlet = re.search(r"MARKER_OUTLET= \( outlet_duct, [0-9.e+-]+ \)", text).group(0)
        p_inf = re.search(r"FREESTREAM_PRESSURE= ([0-9.e+-]+)", text).group(1)
        return common + [(outlet, f"MARKER_OUTLET= ( outlet_duct, {p_inf} )")]
    return common + [("CFL_ADAPT_PARAM= ( 0.5, 1.05, 1.0, 20.0 )", "CFL_ADAPT_PARAM= ( 0.5, 1.05, 1.0, 2.0 )")]


STAGE2_EDITS = [("MATH_PROBLEM= DIRECT", "MATH_PROBLEM= DIRECT\nRESTART_SOL= YES")]   # SOLUTION_FILENAME stays solution_flow


def apply(text, edits):
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def one(args):
    case_id, variant, su2_cmd, out = args
    case = Path(out) / variant / case_id
    shutil.rmtree(case, ignore_errors=True)
    make(json.loads((POOL / case_id / "params.json").read_text()), case)
    pool_cfg = (case / "case.cfg").read_text()
    e1 = stage1_edits(variant, pool_cfg)
    (case / "stage1.cfg").write_text(apply(pool_cfg, e1))
    t0 = time.monotonic()
    with open(case / "log_stage1.txt", "wb") as log:
        rc1 = subprocess.run([*su2_cmd.split(), "stage1.cfg"], cwd=case, stdout=log, stderr=subprocess.STDOUT,
                             timeout=3600).returncode
    stage1 = {"exit_code": rc1, "wall_s": round(time.monotonic() - t0)}
    (case / "history.csv").rename(case / "history_stage1.csv")
    restart = case / "restart_flow.dat"
    if rc1 == 0 and restart.exists():
        restart.rename(case / "solution_flow.dat")                 # run() deletes restart_flow.dat, not this
        (case / "case.cfg").write_text(apply(pool_cfg, STAGE2_EDITS))
        result = run(case, su2_cmd, timeout_s=7200)
        s = result.get("history_summary", {})
        stage2 = {"status": s.get("status"), "iterations": result["run"]["iterations"],
                  "exit_code": result["run"]["exit_code"], "wall_s": round(result["run"]["wall_time_s"]),
                  "recovery_total": (result.get("metrics") or {}).get("recovery_total"),
                  "q_peak_W_m2": (result.get("metrics") or {}).get("q_peak_W_m2")}
    else:
        stage2 = {"status": "stage 1 failed"}
    (case / "edits.json").write_text(json.dumps({"source": f"runs/pool3r/ns/{case_id}", "variant": variant,
                                                 "stage1_edits": e1, "stage2_edits": STAGE2_EDITS}, indent=1) + "\n")
    for f in ("mesh.su2", "solution_flow.dat", "restart_flow.dat"):
        (case / f).unlink(missing_ok=True)
    for f in sorted(case.iterdir()):
        if f.suffix in (".dat", ".csv", ".txt") and f.name != "solver_version.txt":
            with open(f, "rb") as src, gzip.open(f.with_name(f.name + ".gz"), "wb") as dst:
                shutil.copyfileobj(src, dst)
            f.unlink()
    return case_id, variant, {"stage1": stage1, "stage2": stage2}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--su2-cmd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    a = ap.parse_args()
    jobs = [(c, v, a.su2_cmd, a.out) for v in a.variants for c in a.cases]
    with Pool(a.jobs) as pool:
        for case_id, variant, info in pool.imap_unordered(one, jobs):
            print(case_id, variant, json.dumps(info), flush=True)


if __name__ == "__main__":
    main()

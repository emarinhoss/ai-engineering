"""Run a list of cases locally with the SU2 binary and keep a reproducible record of each (Task 9).

    python -m analysis.run_dev_cases CASES.json --su2-cmd SU2_CFD --out runs/dev/<dir> --jobs 3

CASES.json is a list of {"name": ..., "params": {...}}. Each case is staged with worker.make_case.make
(the same staging as every queue job, including the mesh-quality gate) after the physics gates and
the schema, run with worker.run_case.run, and kept as OUT/<name>/ with params.json, geometry.json,
mesh_quality.json, case.cfg, job.json, result.json or result_partial.json, solver_version.txt, and
gzipped history.csv, surface_flow.dat, flow.dat and log.txt. mesh.su2 is left out: make() rebuilds it
from params.json, and job.json holds its fingerprint.
"""
import argparse
import gzip
import json
import shutil
from multiprocessing import Pool
from pathlib import Path

from mcp_server.schemas import to_params, validate
from physics.gates import check
from worker.make_case import make
from worker.run_case import run

GZIP = ("history.csv", "surface_flow.dat", "flow.dat", "log.txt")
COPY = ("params.json", "geometry.json", "mesh_quality.json", "case.cfg", "job.json", "result.json",
        "result_partial.json", "solver_version.txt", "mesh_markers.json")


def one(args):
    name, raw, su2_cmd, out = args
    model, errors, _ = validate(raw)
    if errors:
        return name, {"stage": "schema", "errors": errors}
    params = to_params(model)
    errors = check(params)
    if errors:
        return name, {"stage": "gates", "errors": errors}
    work = Path(out) / f".work_{name}"
    shutil.rmtree(work, ignore_errors=True)
    make(params, work)
    result = run(work, su2_cmd, timeout_s=7200)
    dest = Path(out) / name
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for f in COPY:
        if (work / f).exists():
            shutil.copy(work / f, dest / f)
    for f in GZIP:
        if (work / f).exists():
            with open(work / f, "rb") as src, gzip.open(dest / f"{f}.gz", "wb") as dst:
                shutil.copyfileobj(src, dst)
    shutil.rmtree(work)
    summary = result.get("history_summary", {})
    return name, {"status": summary.get("status"), "iterations": result["run"]["iterations"],
                  "wall_s": round(result["run"]["wall_time_s"], 1), "metrics": "metrics" in result,
                  "metrics_error": result.get("metrics_error")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases")
    ap.add_argument("--su2-cmd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    cases = json.loads(Path(a.cases).read_text())
    Path(a.out).mkdir(parents=True, exist_ok=True)
    shutil.copy(a.cases, Path(a.out) / "cases.json")
    with Pool(a.jobs) as pool:
        for name, info in pool.imap_unordered(one, [(c["name"], c["params"], a.su2_cmd, a.out) for c in cases]):
            print(name, json.dumps(info), flush=True)


if __name__ == "__main__":
    main()

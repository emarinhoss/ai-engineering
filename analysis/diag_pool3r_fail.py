"""Task 9 pool diagnosis (2026-11-03): does the duct back-pressure outlet cause the NS failures?

Four of the first 56 container NS pool runs diverged, three of them below Mach 3.8, where the geometry
(shock-on-lip at Mach 4) spills and the imposed duct back pressure (p_inf times the inviscid
three-shock ratio, spec addendum 2) is least likely to match the duct flow. Two development runs of
one failed case, each staged with worker.make_case.make and given config edits, recorded as such:
  "supersonic": the duct outlet back to MARKER_SUPERSONIC_OUTLET (the Euler and inlet2r condition).
     If it converges where the original diverged, the back pressure causes the failure.
  "snapshots": the original config with volume output every 100 iterations, to locate the growth.
Neither run replaces the pool record, which stays a failed run.

    python -m analysis.diag_pool3r_fail --case inlet3r-fe9cd9771d --su2-cmd SU2_CFD --out runs/dev/<dir>
"""
import argparse
import gzip
import json
import re
import shutil
from multiprocessing import Pool
from pathlib import Path

from worker.make_case import make
from worker.run_case import run

POOL = Path("runs/pool3r/ns")


def edits(name, text):
    """The (old, new) config replacements for one diagnostic run."""
    if name == "supersonic":
        outlet = re.search(r"MARKER_OUTLET= \( outlet_duct, [0-9.e+-]+ \)\n", text).group(0)
        return [(outlet, ""),
                ("MARKER_SUPERSONIC_OUTLET= ( outlet_ext )", "MARKER_SUPERSONIC_OUTLET= ( outlet_ext, outlet_duct )")]
    return [("OUTPUT_WRT_FREQ= 1000", "OUTPUT_WRT_FREQ= 100\nWRT_VOLUME_OVERWRITE= NO"),
            ("OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII )", "OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII, TECPLOT_ASCII )")]


def one(args):
    name, source, su2_cmd, out = args
    case = Path(out) / name
    shutil.rmtree(case, ignore_errors=True)
    make(json.loads((POOL / source / "params.json").read_text()), case)
    cfg = case / "case.cfg"
    text = cfg.read_text()
    changes = edits(name, text)
    for old, new in changes:
        assert text.count(old) == 1, (name, old)
        text = text.replace(old, new)
    cfg.write_text(text)
    (case / "edits.json").write_text(json.dumps({"source": source, "edits": changes}, indent=1) + "\n")
    result = run(case, su2_cmd, timeout_s=7200)
    (case / "mesh.su2").unlink()
    for f in sorted(case.iterdir()):
        if f.suffix in (".dat", ".csv", ".txt") and f.name != "solver_version.txt":
            with open(f, "rb") as src, gzip.open(f.with_name(f.name + ".gz"), "wb") as dst:
                shutil.copyfileobj(src, dst)
            f.unlink()
    s = result.get("history_summary", {})
    return name, {"status": s.get("status"), "iterations": result["run"]["iterations"],
                  "exit_code": result["run"]["exit_code"], "wall_s": round(result["run"]["wall_time_s"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True)
    ap.add_argument("--su2-cmd", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with Pool(2) as pool:
        for name, info in pool.imap_unordered(one, [(n, a.case, a.su2_cmd, a.out) for n in ("supersonic", "snapshots")]):
            print(name, json.dumps(info), flush=True)


if __name__ == "__main__":
    main()

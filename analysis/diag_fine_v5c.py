"""Task 9 V5c diagnosis (2026-11-03): why the nominal fine-mesh laminar run diverged.

Two development runs of the same case (runs/dev/2026-11-03_inlet3r_v5/nominal_ns_fine/params.json),
each staged with worker.make_case.make and then given one config edit, recorded as such:
  D1 "snapshots": OUTPUT_WRT_FREQ= 250, WRT_VOLUME_OVERWRITE= NO, volume output on, so the flow field
     is kept every 250 iterations and the growth can be located.
  D2 "cfl5": CFL_ADAPT_PARAM= ( 0.5, 1.05, 1.0, 5.0 ) (cap 5 instead of 20). If D2 converges and the
     original does not, the divergence depends on the step size; if D2 diverges the same way, it does not.
Neither run changes a validation tolerance; neither result replaces the failed V5c record.

    python -m analysis.diag_fine_v5c --su2-cmd SU2_CFD --out runs/dev/2026-11-03_inlet3r_v5c_diag
"""
import argparse
import gzip
import json
import shutil
from multiprocessing import Pool
from pathlib import Path

from worker.make_case import make
from worker.run_case import run

SOURCE = Path("runs/dev/2026-11-03_inlet3r_v5/nominal_ns_fine/params.json")
EDITS = {
    "snapshots": [("OUTPUT_WRT_FREQ= 1000", "OUTPUT_WRT_FREQ= 250\nWRT_VOLUME_OVERWRITE= NO"),
                  ("OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII )", "OUTPUT_FILES= ( SURFACE_TECPLOT_ASCII, TECPLOT_ASCII )")],
    "cfl5": [("CFL_ADAPT_PARAM= ( 0.5, 1.05, 1.0, 20.0 )", "CFL_ADAPT_PARAM= ( 0.5, 1.05, 1.0, 5.0 )")],
}


def one(args):
    name, su2_cmd, out = args
    case = Path(out) / name
    shutil.rmtree(case, ignore_errors=True)
    make(json.loads(SOURCE.read_text()), case)
    cfg = case / "case.cfg"
    text = cfg.read_text()
    for old, new in EDITS[name]:
        assert text.count(old) == 1, (name, old)
        text = text.replace(old, new)
    cfg.write_text(text)
    (case / "edits.json").write_text(json.dumps(EDITS[name], indent=1) + "\n")
    result = run(case, su2_cmd, timeout_s=7200)
    (case / "mesh.su2").unlink()
    for f in sorted(case.iterdir()):
        if f.suffix in (".dat", ".csv", ".txt") and f.name not in ("solver_version.txt",):
            with open(f, "rb") as src, gzip.open(f.with_name(f.name + ".gz"), "wb") as dst:
                shutil.copyfileobj(src, dst)
            f.unlink()
    s = result.get("history_summary", {})
    return name, {"status": s.get("status"), "iterations": result["run"]["iterations"],
                  "exit_code": result["run"]["exit_code"], "wall_s": round(result["run"]["wall_time_s"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--su2-cmd", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with Pool(2) as pool:
        for name, info in pool.imap_unordered(one, [(n, a.su2_cmd, a.out) for n in EDITS]):
            print(name, json.dumps(info), flush=True)


if __name__ == "__main__":
    main()

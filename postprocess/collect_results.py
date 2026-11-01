"""Results table of a run directory: one CSV row per record under runs/<tag>/.

Columns: case_id, theta1_deg, theta2_deg, recovery_total, q_peak_W_m2, status, then the extras
recovery_throat, q_peak_cowl_W_m2, capture_ratio, iterations, wall_time_s, mesh_level. `status`
is the convergence status of result.json (converged, stationary, diverged, ...) or
"failed:<reason>" for a record that holds error.json. Only converged and stationary rows feed
the surrogate (surrogate.replay filters on status); the failed rows stay in the table so the
count of refused or diverged points is visible.

    python -m postprocess.collect_results runs/pool --out runs/pool/results.csv
"""
import argparse
import csv
import json
from pathlib import Path

COLUMNS = ("case_id", "theta1_deg", "theta2_deg", "recovery_total", "q_peak_W_m2", "status",
           "recovery_throat", "q_peak_cowl_W_m2", "capture_ratio", "iterations", "wall_time_s",
           "mesh_level")


def rows(run_dir):
    """Table rows (dicts with COLUMNS) for every <case_id>/ record under run_dir, sorted by case_id."""
    out = []
    for case in sorted(p for p in Path(run_dir).iterdir() if p.is_dir()):
        params = json.loads((case / "params.json").read_text()) if (case / "params.json").exists() else {}
        row = {k: "" for k in COLUMNS}
        row.update(case_id=case.name, theta1_deg=params.get("theta1_deg", ""),
                   theta2_deg=params.get("theta2_deg", ""), mesh_level=params.get("mesh_level", ""))
        if (case / "result.json").exists():
            rec = json.loads((case / "result.json").read_text())
            m = rec.get("metrics", {})
            row.update(recovery_total=m.get("recovery_total", ""), q_peak_W_m2=m.get("q_peak_W_m2", ""),
                       status=rec["convergence"]["status"], recovery_throat=m.get("recovery_throat", ""),
                       q_peak_cowl_W_m2=m.get("q_peak_cowl_W_m2", ""), capture_ratio=m.get("capture_ratio", ""),
                       iterations=rec["run"]["iterations"], wall_time_s=round(rec["run"]["wall_time_s"], 1))
        elif (case / "error.json").exists():
            row["status"] = "failed:" + json.loads((case / "error.json").read_text())["reason"]
        else:
            continue                                   # not a run record
        out.append(row)
    return out


def write(run_dir, out_csv):
    table = rows(run_dir)
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(table)
    return table


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    table = write(args.run_dir, args.out)
    usable = sum(r["status"] in ("converged", "stationary") for r in table)
    print(f"{len(table)} records, {usable} converged or stationary -> {args.out}")


if __name__ == "__main__":
    main()

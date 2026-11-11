"""Experiment E0 (docs/specs/task11_fno_exploration.md, section 4): what a warm start saves.

    python -m analysis.e0_warmstart --out runs/e0_analysis/<date>

Reads designs/e0_cases.csv (each warm case, its cold twin and its donor) and the run records under
runs/e0/. For each warm case: iterations to the stop, wall time, cl and cd, against its cold twin.

The pass condition, fixed in the spec before any case ran, per kind of start (angle_step, mesh_step):
  1. the median iteration count falls by at least 30 % (median of the per-pair savings);
  2. every warm cl and cd is within the cold twin's own recorded drift of the cold value.
A warm run that exhausts its budget, or whose cold twin does, counts as no saving (0 %).
Wall time is reported beside iterations. The donor's wall time is charged to the mesh step (a coarse
run is needed first) and not to the angle step (the donor is a case the polar needs anyway).
"""
import argparse
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_SAVING = 0.30        # spec: iterations fall by at least 30 %
KINDS = ("angle_step", "mesh_step")


def load(case_id, runs=ROOT / "runs" / "e0"):
    """The fields E0 compares, from one run record."""
    r = json.loads((Path(runs) / case_id / "result.json").read_text())
    c = r["convergence"]
    return {"case_id": case_id, "iterations": c["iterations"], "max_iter": r["params"]["max_iter"],
            "exit_code": r["run"]["exit_code"], "wall_s": r["run"]["wall_time_s"],
            "cl": r["metrics"]["cl"], "cd": r["metrics"]["cd"],
            "drift_cl_pct": c["drift_pct"]["cl"], "drift_cd_pct": c["drift_pct"]["cd"]}


def exhausted(run):
    return run["iterations"] >= run["max_iter"]


def compare(warm, cold, donor, kind):
    """One warm case against its cold twin: iteration saving, wall saving, force agreement."""
    no_saving = exhausted(warm) or exhausted(cold)
    saving = 0.0 if no_saving else 1.0 - warm["iterations"] / cold["iterations"]
    warm_wall = warm["wall_s"] + (donor["wall_s"] if kind == "mesh_step" else 0.0)
    out = {"kind": kind, "warm": warm["case_id"], "cold": cold["case_id"], "donor": donor["case_id"],
           "iter_warm": warm["iterations"], "iter_cold": cold["iterations"],
           "budget_exhausted": no_saving, "iter_saving": saving,
           "wall_warm_s": warm_wall, "wall_cold_s": cold["wall_s"],
           "wall_saving": 1.0 - warm_wall / cold["wall_s"], "donor_charged": kind == "mesh_step"}
    for q in ("cl", "cd"):
        dev_pct = 100.0 * abs(warm[q] - cold[q]) / abs(cold[q])
        out[f"{q}_warm"], out[f"{q}_cold"] = warm[q], cold[q]
        out[f"{q}_dev_pct"], out[f"{q}_allowed_pct"] = dev_pct, cold[f"drift_{q}_pct"]
        out[f"{q}_within"] = dev_pct <= cold[f"drift_{q}_pct"]
    return out


def verdict(pairs):
    """Per kind: median saving, the force check, pass or fail by the fixed rule."""
    res = {}
    for kind in KINDS:
        ps = [p for p in pairs if p["kind"] == kind]
        if not ps:
            res[kind] = {"verdict": "not run"}
            continue
        med = statistics.median(p["iter_saving"] for p in ps)
        forces = all(p["cl_within"] and p["cd_within"] for p in ps)
        res[kind] = {"n": len(ps), "median_iter_saving": med,
                     "median_wall_saving": statistics.median(p["wall_saving"] for p in ps),
                     "forces_within_drift": forces,
                     "verdict": "pass" if med >= MIN_SAVING and forces else "fail"}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cases", default=str(ROOT / "designs" / "e0_cases.csv"))
    ap.add_argument("--runs", default=str(ROOT / "runs" / "e0"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.cases, newline="") as f:
        rows = list(csv.DictReader(f))
    runs = {r["case_id"]: load(r["case_id"], a.runs) for r in rows}
    bad = [c for c, r in runs.items() if r["exit_code"] != 0]
    if bad:
        raise SystemExit(f"non-zero exit in {bad}: E0 is not evaluated on failed runs")
    pairs = [compare(runs[r["case_id"]], runs[r["cold_twin"]], runs[r["restart_from"]], r["kind"])
             for r in rows if r["kind"] in KINDS]
    res = {"rule": {"min_median_iter_saving": MIN_SAVING,
                    "forces": "every warm cl and cd within the cold twin's recorded drift"},
           "runs": runs, "pairs": pairs, "verdict": verdict(pairs)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "e0.json").write_text(json.dumps(res, indent=1) + "\n")
    for p in pairs:
        print(f"{p['kind']:10s} {p['warm']} iters {p['iter_warm']:5d} vs {p['iter_cold']:5d} "
              f"saving {100 * p['iter_saving']:+6.1f} %  wall {100 * p['wall_saving']:+6.1f} %  "
              f"cl {p['cl_dev_pct']:.3f} % (<= {p['cl_allowed_pct']:.2f})  "
              f"cd {p['cd_dev_pct']:.3f} % (<= {p['cd_allowed_pct']:.2f})")
    for kind, v in res["verdict"].items():
        print(kind, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

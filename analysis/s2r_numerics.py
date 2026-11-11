"""Experiment S2R (docs/specs/task11_fno_exploration.md): linear tolerance 1E-2 on one machine.

    python -m analysis.s2r_numerics --out runs/s2r_analysis/<date>

Reads designs/s2r_cases.csv, the S2R run records (runs/s2r_*) and, for the five old cases, the S1/S2
references (designs/s12_cases.csv, runs/s12_ref). Applies the rule approved on 2026-11-11, unchanged:

Reference valid: exit 0, stopped inside its budget, own drift of cl and of cd below 0.2 %.
A verdict needs at least five cases with a valid reference. Pass if all hold:
  1. every 1E-2 run exits 0 and stops inside 6,000 iterations;
  2a. for every case, each 1E-2 run is within 0.5 % (cl) and 1.0 % (cd) of the baseline's value;
  2b. for every case with a valid reference, each 1E-2 run is within 2 % (cl and cd) of it;
  3. the median over cases of 1 - mean(1E-2 wall) / mean(baseline wall) is at least 30 % and at
     least three times the noise (the largest relative spread of two repeats of one setting).
All timed runs must share one worker_id; otherwise condition 3 is void and reported as void.
"""
import argparse
import csv
import json
import statistics
from pathlib import Path

from analysis.s12_numerics import clean, distance, load, reference_valid

ROOT = Path(__file__).resolve().parents[1]
BASE_FLOOR = {"cl": 0.005, "cd": 0.010}
REF_LIMIT = 0.02
MIN_SAVING = 0.30
MIN_VALID_CASES = 5


def worker_of(run):
    return run["worker_id"]


def spread(a, b):
    return abs(a["wall_s"] - b["wall_s"]) / (0.5 * (a["wall_s"] + b["wall_s"]))


def judge_case(base, tol, ref):
    """base, tol: the two runs of each setting; ref: the reference run, or None if not valid."""
    base_wall = statistics.mean(r["wall_s"] for r in base)
    out = {"clean": all(clean(r) for r in tol),
           "saving": 1.0 - statistics.mean(r["wall_s"] for r in tol) / base_wall,
           "spread_base": spread(*base), "spread_tol": spread(*tol),
           "iterations": [r["iterations"] for r in base + tol],
           "s_per_iter": [r["wall_s"] / r["iterations"] for r in base + tol]}
    for q in ("cl", "cd"):
        to_base = max(distance(t, b, q) for t in tol for b in base)
        out[f"{q}_to_base"], out[f"{q}_base_ok"] = to_base, to_base <= BASE_FLOOR[q]
        if ref is not None:
            to_ref = max(distance(t, ref, q) for t in tol)
            out[f"{q}_to_ref"], out[f"{q}_ref_ok"] = to_ref, to_ref <= REF_LIMIT
    return out


def judge(cases, n_valid_refs, one_worker):
    if n_valid_refs < MIN_VALID_CASES:
        return {"verdict": "not evaluated", "valid_references": n_valid_refs}
    runs_ok = all(c["clean"] for c in cases.values())
    base_ok = all(c["cl_base_ok"] and c["cd_base_ok"] for c in cases.values())
    ref_ok = all(c.get("cl_ref_ok", True) and c.get("cd_ref_ok", True) for c in cases.values())
    noise = max(max(c["spread_base"], c["spread_tol"]) for c in cases.values())
    med = statistics.median(c["saving"] for c in cases.values())
    faster = one_worker and med >= MIN_SAVING and med >= 3.0 * noise
    return {"runs_cleanly": runs_ok, "answer_vs_baseline": base_ok, "answer_vs_reference": ref_ok,
            "median_saving": med, "noise": noise, "one_worker": one_worker,
            "faster": faster if one_worker else "void", "valid_references": n_valid_refs,
            "verdict": "pass" if runs_ok and base_ok and ref_ok and faster else "fail"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cases", default=str(ROOT / "designs" / "s2r_cases.csv"))
    ap.add_argument("--old-cases", default=str(ROOT / "designs" / "s12_cases.csv"))
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.cases, newline="") as f:
        rows = list(csv.DictReader(f))
    with open(a.old_cases, newline="") as f:
        rows += [r for r in csv.DictReader(f) if r["setting"] == "reference"]
    by = {}
    for r in rows:
        run = load(r["case_id"], r["set"], a.runs)
        res = json.loads((Path(a.runs) / r["set"] / r["case_id"] / "result.json").read_text())
        run["worker_id"] = res["run"].get("worker_id")
        by.setdefault(r["case"], {}).setdefault(r["setting"], []).append(run)
    cases, refs = {}, {}
    for case, sets in by.items():
        if "tol" not in sets:
            continue                                  # an S1/S2 case not in this experiment
        ref = sets["reference"][0]
        refs[case] = {**ref, "valid": reference_valid(ref)}
        cases[case] = judge_case(sets["baseline"], sets["tol"], ref if refs[case]["valid"] else None)
    workers = {worker_of(r) for s in by.values() if "tol" in s for k in ("baseline", "tol") for r in s[k]}
    res = {"references": refs, "workers": sorted(map(str, workers)), "cases": cases,
           **judge(cases, sum(r["valid"] for r in refs.values()), len(workers) == 1)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "s2r.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("cases", "references")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Experiment W1 (docs/specs/task11_fno_exploration.md): a learned warm start, against cold and
nearest-case starts.

    python -m analysis.w1_warmstart --out runs/w1_analysis/<date>

Reads designs/w1_cases.csv (the 42 timed runs with the preparation time of each warm start), the
run records under runs/w1_*, and the references (design 1: designs/s12_cases.csv and
designs/s2r_cases.csv; design 4: designs/w1_field_cases.csv). Applies the rule approved on
2026-11-12, unchanged.

Reference valid: exit 0, stopped inside its budget, own drift of cl and of cd below 0.2 %. A verdict
needs at least five cases with a valid reference. Judged separately for the nearest-case start and
for the learned start; pass if all hold:
  1. every run with that start exits 0 and stops inside 6,000 iterations;
  2. for every case with a valid reference, the cl and cd of each run are within 2 % of it;
  3. the median over cases of 1 - mean(warm wall) / mean(cold wall) is at least 30 % and at least
     three times the noise (the largest relative spread of two repeats of one start, over all
     three starts and all cases). The wall time of a warm run includes preparing its start file.
All timed runs must share one worker_id; otherwise condition 3 is void.
Only if the learned start passes: the learning adds something if the median over cases of
(mean near wall - mean learned wall) / mean cold wall is at least 10 points and at least three
times the noise; otherwise "no better" than the nearest stored case.
"""
import argparse
import csv
import json
import statistics
from pathlib import Path

from analysis.s12_numerics import clean, distance, load, reference_valid

ROOT = Path(__file__).resolve().parents[1]
STARTS = ("near", "learn")
REF_LIMIT = 0.02
MIN_SAVING = 0.30
MIN_ADDED = 0.10
MIN_VALID_CASES = 5


def mean_wall(runs):
    return statistics.mean(r["wall_s"] for r in runs)


def spread(a, b):
    return abs(a["wall_s"] - b["wall_s"]) / (0.5 * (a["wall_s"] + b["wall_s"]))


def judge_start(cold, warm, ref):
    """One case and one warm start. cold, warm: two runs each; ref: the valid reference or None."""
    out = {"clean": all(clean(r) for r in warm), "saving": 1.0 - mean_wall(warm) / mean_wall(cold),
           "iterations": [r["iterations"] for r in warm], "spread": spread(*warm)}
    if ref is not None:
        for q in ("cl", "cd"):
            out[f"{q}_to_ref"] = max(distance(r, ref, q) for r in warm)
        out["ref_ok"] = out["cl_to_ref"] <= REF_LIMIT and out["cd_to_ref"] <= REF_LIMIT
    return out


def judge(cases):
    """cases: {name: {"cold": [2 runs], "near": [2 runs], "learn": [2 runs], "ref": run or None}}."""
    n_valid = sum(c["ref"] is not None for c in cases.values())
    if n_valid < MIN_VALID_CASES:
        return {"verdict": "not evaluated", "valid_references": n_valid}
    workers = {r["worker_id"] for c in cases.values() for s in ("cold", *STARTS) for r in c[s]}
    one_worker = len(workers) == 1
    per = {s: {k: judge_start(c["cold"], c[s], c["ref"]) for k, c in cases.items()} for s in STARTS}
    noise = max(max(spread(*c["cold"]), per["near"][k]["spread"], per["learn"][k]["spread"])
                for k, c in cases.items())
    out = {"valid_references": n_valid, "one_worker": one_worker, "workers": sorted(map(str, workers)),
           "noise": noise, "cases": per}
    for s in STARTS:
        runs_ok = all(j["clean"] for j in per[s].values())
        ref_ok = all(j.get("ref_ok", True) for j in per[s].values())
        med = statistics.median(j["saving"] for j in per[s].values())
        faster = one_worker and med >= MIN_SAVING and med >= 3.0 * noise
        out[s] = {"runs_cleanly": runs_ok, "answer_vs_reference": ref_ok, "median_saving": med,
                  "faster": faster if one_worker else "void",
                  "verdict": "pass" if runs_ok and ref_ok and faster else "fail"}
    if out["learn"]["verdict"] == "pass":
        added = statistics.median((mean_wall(c["near"]) - mean_wall(c["learn"])) / mean_wall(c["cold"])
                                  for c in cases.values())
        better = added >= MIN_ADDED and added >= 3.0 * noise
        out["learning_adds"] = {"median": added, "result": "better" if better else "no better"}
    else:
        out["learning_adds"] = {"result": "not judged"}
    return out


def reference_rows():
    """{case name: (case_id, tag)} of every reference the rule names."""
    refs = {}
    for name, tag_col in (("s12_cases.csv", "set"), ("s2r_cases.csv", "set")):
        with open(ROOT / "designs" / name, newline="") as f:
            for r in csv.DictReader(f):
                if r["setting"] == "reference" and r["case"].startswith("pool1_coarse_"):
                    refs[f"d1_{float(r['case'].rsplit('_', 1)[1]):g}"] = (r["case_id"], r[tag_col])
    with open(ROOT / "designs" / "w1_field_cases.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["set"] == "w1_ref":
                refs[f"d4_{float(r['alpha_deg']):g}"] = (r["case_id"], "w1_ref")
    return refs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cases", default=str(ROOT / "designs" / "w1_cases.csv"))
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.cases, newline="") as f:
        rows = list(csv.DictReader(f))
    refs = reference_rows()
    cases = {}
    for r in rows:
        run = load(r["case_id"], r["set"], a.runs)
        res = json.loads((Path(a.runs) / r["set"] / r["case_id"] / "result.json").read_text())
        run["worker_id"] = res["run"].get("worker_id")
        run["wall_s"] += float(r["prep_s"] or 0.0)                 # preparing the start file counts
        cases.setdefault(r["case"], {"cold": [], "near": [], "learn": []})[r["start"]].append(run)
    references = {}
    for name, c in cases.items():
        ref = load(*refs[name], a.runs) if name in refs else None
        references[name] = {**ref, "valid": reference_valid(ref)} if ref else None
        c["ref"] = ref if ref and reference_valid(ref) else None
    res = {"references": references, **judge(cases)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "w1.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k not in ("cases", "references")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Experiment S1/S2 (docs/specs/task11_fno_exploration.md): CFL ceiling and linear tolerance.

    python -m analysis.s12_numerics --out runs/s12_analysis/<date>

Reads designs/s12_cases.csv and the run records under runs/s12_ref, runs/s12_base1, runs/s12_base2,
runs/s12_s1 and runs/s12_s2. Applies the rule approved on 2026-11-11, unchanged:

Reference valid: exit 0, stopped inside its budget, own drift of cl and of cd below 0.2 %.
A verdict needs at least four cases with a valid reference. A setting passes if all three hold:
  1. every case exits 0 and stops inside the standard budget;
  2. for every case, |cl - cl_ref| / |cl_ref| <= max(baseline distance, 0.5 %), and the same for cd
     with 1.0 %; the baseline distance is the larger of its two repeats;
  3. the median wall-time saving against the mean of the two baseline repeats is at least 30 %.
A saving below three times the largest spread between baseline repeats is "not resolved".
"""
import argparse
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF_DRIFT_MAX_PCT = 0.2
FLOOR = {"cl": 0.005, "cd": 0.010}
MIN_SAVING = 0.30
MIN_VALID_CASES = 4


def load(case_id, tag, runs=ROOT / "runs"):
    r = json.loads((Path(runs) / tag / case_id / "result.json").read_text())
    c = r["convergence"]
    return {"case_id": case_id, "exit_code": r["run"]["exit_code"], "iterations": c["iterations"],
            "max_iter": r["params"]["max_iter"], "wall_s": r["run"]["wall_time_s"],
            "cl": r["metrics"]["cl"], "cd": r["metrics"]["cd"],
            "drift_cl_pct": c["drift_pct"]["cl"], "drift_cd_pct": c["drift_pct"]["cd"]}


def clean(run):
    """Condition 1 for one run: exit 0 and stopped inside its budget."""
    return run["exit_code"] == 0 and run["iterations"] < run["max_iter"]


def reference_valid(ref):
    return clean(ref) and ref["drift_cl_pct"] < REF_DRIFT_MAX_PCT and ref["drift_cd_pct"] < REF_DRIFT_MAX_PCT


def distance(run, ref, q):
    return abs(run[q] - ref[q]) / abs(ref[q])


def judge_case(run, ref, base1, base2):
    """One run of a setting against its case's reference and two baseline repeats."""
    base_wall = 0.5 * (base1["wall_s"] + base2["wall_s"])
    out = {"case_id": run["case_id"], "clean": clean(run), "iterations": run["iterations"],
           "wall_s": run["wall_s"], "baseline_wall_s": base_wall,
           "wall_saving": 1.0 - run["wall_s"] / base_wall,
           "s_per_iter": run["wall_s"] / run["iterations"],
           "baseline_iterations": 0.5 * (base1["iterations"] + base2["iterations"])}
    for q in ("cl", "cd"):
        allowed = max(distance(base1, ref, q), distance(base2, ref, q), FLOOR[q])
        out[f"{q}_distance"], out[f"{q}_allowed"] = distance(run, ref, q), allowed
        out[f"{q}_ok"] = out[f"{q}_distance"] <= allowed
    return out


def judge_setting(cases, noise):
    """cases: judge_case outputs of the valid cases of one setting. noise: largest baseline spread."""
    if len(cases) < MIN_VALID_CASES:
        return {"verdict": "not evaluated", "n": len(cases)}
    runs_ok = all(c["clean"] for c in cases)
    answer_ok = all(c["cl_ok"] and c["cd_ok"] for c in cases)
    med = statistics.median(c["wall_saving"] for c in cases)
    faster = med >= MIN_SAVING
    return {"n": len(cases), "runs_cleanly": runs_ok, "answer_does_not_move": answer_ok,
            "median_wall_saving": med, "faster": faster, "resolved": abs(med) >= 3.0 * noise,
            "verdict": "pass" if runs_ok and answer_ok and faster else "fail"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cases", default=str(ROOT / "designs" / "s12_cases.csv"))
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.cases, newline="") as f:
        rows = list(csv.DictReader(f))
    by = {}
    for r in rows:
        by.setdefault(r["case"], {}).setdefault(r["setting"], []).append(load(r["case_id"], r["set"], a.runs))
    refs, spreads, valid = {}, {}, []
    for case, sets in by.items():
        ref, (b1, b2) = sets["reference"][0], sets["baseline"]
        refs[case] = {**ref, "valid": reference_valid(ref)}
        spreads[case] = abs(b1["wall_s"] - b2["wall_s"]) / (0.5 * (b1["wall_s"] + b2["wall_s"]))
        if refs[case]["valid"]:
            valid.append(case)
    noise = max(spreads.values())
    settings = sorted({r["setting"] for r in rows} - {"reference", "baseline"})
    res = {"references": refs, "baseline_wall_spread": spreads, "noise": noise, "valid_cases": valid,
           "settings": {}}
    for s in settings:
        cases = [{"case": c, **judge_case(by[c][s][0], by[c]["reference"][0], *by[c]["baseline"])}
                 for c in valid]
        res["settings"][s] = {"cases": cases, **judge_setting(cases, noise)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "s12.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: {x: v[x] for x in v if x != "cases"} for k, v in res["settings"].items()}, indent=1))
    print("valid references:", valid, "| noise", round(noise, 4))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

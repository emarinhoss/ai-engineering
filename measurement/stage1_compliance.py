"""Stage 1 compliance table of a frozen design, without re-sizing (owner ruling B-7, 2026-11-26).

The design is rebuilt through Stage 1's own path (stage1.analyse: tail resize for rotation, layout,
performance) from the record's W/S, A, built ledger copy (V_C fixed) and engine table, with the weight
iteration started at the record's W0. The rebuild must reproduce the record (quantities and tolerance in
CHECKS); if it does not, this raises and writes nothing. Then stage1.compliance gives the rows, the same
function that wrote every Stage 1 table.

    python -m measurement.stage1_compliance \
        --design runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json \
        --out runs/task12/stage3/2026-11-26/compliance_frozen/compliance.json \
        --report docs/validation/2026-11-26_task12_stage1_compliance_frozen.md
"""
import argparse
import json
import platform
import sys
from pathlib import Path

from conceptual import stage1, uav
from conceptual.engine_model import table_for_run
from measurement import stage3_perf as sp

REPRODUCE_TOLERANCE = 1e-4     # relative; the weight iteration and the ceiling bisection stop near 1e-6
CHECKS = (("W0_lb", "W0_lb"), ("We_lb", "We_lb"), ("fuel_lb", "fuel_lb"), ("bhp_sl", "bhp_sl"),
          ("ht_volume_scale", "ht_volume_scale"), ("n_gust", "n_gust"), ("n_negative_gust", "n_negative_gust"))


def rebuild(design_path):
    """Stage 1 analysis of the record's design, the compliance rows, and the check against the record."""
    path = Path(design_path)
    rec = json.loads(path.read_text())
    L, _ = uav.load_ledger(path.parent / "ledger.yaml")
    name = rec["engine"]["fixed"]
    eng = sp.record_engine(rec, table_for_run(path.parent), L.get("engine_sfc_allowance", 1.0))
    raw = stage1.engine_options(name)[1][name]
    a = stage1.analyse(rec["concept"], rec["W_S"], rec["A"], L, eng, W0_guess=rec["W0_lb"])
    new = stage1.design_record(a, L, raw)
    check = {}
    for key, nkey in CHECKS:
        check[key] = {"record": rec[key], "rebuilt": new[nkey]}
    for key in ("takeoff_ft", "landing_ft", "roc_sl_fpm", "service_ceiling_ft", "V_stall_clean_kt"):
        if key in rec.get("performance", {}):
            check["performance." + key] = {"record": rec["performance"][key], "rebuilt": new["performance"][key]}
    for k, v in check.items():
        v["relative_difference"] = v["rebuilt"] / v["record"] - 1.0
        if abs(v["relative_difference"]) > REPRODUCE_TOLERANCE:
            raise ValueError(f"the rebuild does not reproduce the record: {k} {v['record']} against {v['rebuilt']}")
    rows = stage1.compliance(a["design"], a["design"]["ledger_used"], a["layout"], a["performance"],
                             *a["fuel_volume"], raw)
    return rows, check, L


def fmt(x):
    if isinstance(x, float):
        return f"{x:.4g}" if abs(x) < 1e4 else f"{x:,.0f}"
    return str(x)


def report_text(res):
    inp = res["inputs"]
    rows = res["rows"]
    n = {k: sum(1 for r in rows if r["verdict"] == k) for k in ("pass", "fail", "not tested")}
    L = ["# Task 12: Stage 1 compliance table of the frozen design (ruling B-7)", "",
         f"Design `{inp['design']}` (sha256 {inp['design_sha256'][:12]}), ledger copy `{inp['ledger']}`. "
         f"Record `{inp['out']}`; commit {inp['git_commit'][:7]}, git_dirty {inp['git_dirty']}. "
         f"Command: `{inp['command']}`.", "",
         "The table is `conceptual/stage1.py` `compliance()`, the function behind every Stage 1 table, applied to the design "
         "rebuilt through Stage 1's own path from the record (not re-sized). The rebuild reproduces the record:", "",
         "| Quantity | Record | Rebuilt | Relative difference |", "|---|---|---|---|"]
    for k, v in res["reproduction"].items():
        L.append(f"| {k} | {v['record']:.8g} | {v['rebuilt']:.8g} | {v['relative_difference']:.1e} |")
    L += ["", f"Tolerance {res['reproduce_tolerance']:g}. Verdicts: {n['pass']} pass, {n['fail']} fail, {n['not tested']} not tested "
          "(by construction, notes and flags the function does not test numerically).", "",
          "| # | Requirement | Units | Value | Limit | Rule | Verdict |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        L.append(f"| {i} | {r['requirement']} | {r['units']} | {fmt(r['value'])} | {fmt(r['limit'])} | {r['rule']} | {r['verdict']} |")
    fails = [r["requirement"] for r in rows if r["verdict"] == "fail"]
    L += ["", "Failed rows: " + ("; ".join(fails) if fails else "none") + ".", "",
          "Limits are the record's ledger values with their Gate A margins (negative gust -1.8 plus 0.1 g, ceiling +500 ft, power margin 0). "
          "The R9 positive row compares n_limit, which Stage 1 sets to the larger of 3.8 and the gust load factor; "
          "the gust value itself is in the V-n report (`docs/validation/2026-11-26_task12_vn_check.md`). "
          "The Gate A items A1 to A12 are not re-checked here (a review task)."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    rows, check, L = rebuild(a.design)
    for r in rows:
        r["verdict"] = {True: "pass", False: "fail", None: "not tested"}[r["met"]]
    dirty = sp.git_dirty_files()
    res = {"rows": rows, "reproduction": check, "reproduce_tolerance": REPRODUCE_TOLERANCE,
           "inputs": {"design": a.design, "design_sha256": sp.sha256(a.design),
                      "ledger": str(Path(a.design).parent / "ledger.yaml"),
                      "ledger_sha256": sp.sha256(Path(a.design).parent / "ledger.yaml"),
                      "out": a.out, "git_commit": sp.git_commit(), "git_dirty": bool(dirty), "git_dirty_files": dirty,
                      "python": platform.python_version(), "seed": None,
                      "command": "python -m measurement.stage1_compliance " + " ".join(sys.argv[1:] if argv is None else argv)}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report_text(res))
    for r in rows:
        print(r["verdict"], r["requirement"], r["value"], r["limit"])


if __name__ == "__main__":
    main()

"""Gate A re-check (items A1 to A12, spec section 6) of the W/S 13, A 8 baseline, as a record.

Verdicts are those of docs/reviews/2026-11-27_task12_gateB_ws13a8_review.md section 5 and ruling B-9a (A9 and
A11 are inherited). They are typed in below as text. Every value is read from a committed record by a (file, key
path) pair, which is stored beside it so that anyone can read it again. A few values are sums or ratios of read
values; they are marked "arithmetic" with their formula.
    python -m postprocess.task12_gateA_recheck --out runs/.../gateA.json --md docs/validation/....md
"""
import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = "runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8/"
DESIGN, INFO, LEDGER, CELL = (BASE + n for n in ("design_pusher.json", "info_gap.json", "ledger.yaml", "cell_result.json"))
COMPLIANCE = "runs/task12/stage3/2026-11-27/compliance_ws13a8/compliance.json"
SCORES = "runs/task12/stage1/2026-11-25/concept_scores.json"
PYTEST = "runs/task12/stage3/2026-11-27/pytest_gate/summary.json"
REVIEW = "docs/reviews/2026-11-27_task12_gateB_ws13a8_review.md"
PACKAGE = "docs/validation/2026-11-25_task12_conceptual_m250_appl.md"


def load(rel):
    p = ROOT / rel
    return yaml.safe_load(p.read_text()) if p.suffix == ".yaml" else json.loads(p.read_text())


def read(rel, key):
    """The value at the key path (strings are dict keys, integers list positions) of a record."""
    v = load(rel)
    for k in key:
        v = v[k]
    return v


def val(name, rel, key, units=""):
    return {"name": name, "value": read(rel, key), "units": units, "source": rel, "key": key}


def row(n, start, field="value", units=""):
    """Value of row n (1-based, as the review counts) of the compliance table; the row text must start so."""
    r = load(COMPLIANCE)["rows"][n - 1]
    assert r["requirement"].startswith(start), (n, r["requirement"])
    return val(f"compliance row {n}: {start}", COMPLIANCE, ["rows", n - 1, field], units)


def arith(name, value, formula, units=""):
    return {"name": name, "value": value, "units": units, "arithmetic": formula}


def a1():
    rows = load(COMPLIANCE)["rows"]
    n = {k: sum(r["verdict"] == k for r in rows) for k in ("pass", "fail", "not tested")}
    curve = load(INFO)["worst_case_curve"]
    h1 = next(i for i, p in enumerate(curve) if p["h"] == 1.0)
    return [arith("compliance rows", len(rows), "count of rows"),
            arith("rows pass", n["pass"], "count of verdict pass"), arith("rows fail", n["fail"], "count of verdict fail"),
            arith("rows not tested", n["not tested"], "count of verdict not tested"),
            val("R5 guarantee horizon", INFO, ["h_hat", "R5_guarantee", "h_hat"]),
            val("worst endurance at h = 1", INFO, ["worst_case_curve", h1, "R5", "hours"], "h")]


def a2():
    comp = load(DESIGN)["components_lb"]
    v = [val("empty weight", DESIGN, ["We_lb"], "lb"), val("fuel", DESIGN, ["fuel_lb"], "lb"),
         val("payload", DESIGN, ["payload_lb"], "lb"), val("W0", DESIGN, ["W0_lb"], "lb"),
         arith("sum of the 13 components", sum(comp.values()), "sum of components_lb", "lb"),
         ]
    w = {x["name"]: x["value"] for x in v}
    v.append(arith("empty + fuel + payload", w["empty weight"] + w["fuel"] + w["payload"], "We + fuel + payload", "lb"))
    v.append(arith("empty fraction", w["empty weight"] / w["W0"], "We / W0"))
    v.append(arith("fuel fraction", w["fuel"] / w["W0"], "fuel / W0"))
    for k in ("build_up", "table_3_1", "table_6_2", "table_15_2_approximate"):
        v.append(val("empty fraction, " + k, DESIGN, ["empty_fraction_comparison", k]))
    return v


def a3():
    m = load(DESIGN)["mission"]
    v = [val("W at start of mission", DESIGN, ["mission", 0, "W_start"], "lb"),
         val("W at end of mission", DESIGN, ["mission", len(m) - 1, "W_end"], "lb"),
         val("fuel on board", DESIGN, ["fuel_lb"], "lb")]
    burned = v[0]["value"] - v[1]["value"]
    v.append(arith("fuel burned over six segments", burned, "W start - W end", "lb"))
    v.append(arith("1.06 x burned", 1.06 * burned, "1.06 x fuel burned", "lb"))
    return v


def a4():
    trim = load(DESIGN)["layout"]["trim"]
    return [row(15, "R13 static margin, full", "value", "MAC"), row(16, "R13 static margin, empty", "value", "MAC"),
            arith("largest tail CL over the mission legs", max(t["CL_tail"] for t in trim.values()), "max of layout.trim CL_tail"),
            row(30, "nose rotation", "value", "tail CL"), row(30, "nose rotation", "limit", "tail CL")]


def a5():
    return [val("n_limit", DESIGN, ["n_limit"]), val("gust load factor, mission altitude, zero-fuel weight", DESIGN, ["n_gust"]),
            val("negative gust load factor", DESIGN, ["n_negative_gust"]), val("ultimate load factor", DESIGN, ["Nz_ultimate"])] + \
        [val("gust " + k, DESIGN, ["gusts", k]) for k in load(DESIGN)["gusts"]]


def a6():
    return [row(23, "engine power", "value", "hp"), row(23, "engine power", "limit", "hp"),
            row(13, "R12 sea-level", "value", "ft/min"),
            row(14, "R12 service ceiling", "value", "ft"), row(14, "R12 service ceiling", "limit", "ft")]


def a7():
    led = load(LEDGER)
    ents = {**led["requirements"], **led["assumptions"]}
    return [arith("ledger entries", len(ents), "requirements + assumptions"),
            arith("entries without a source", sum(not e.get("source") for e in ents.values()), "count"),
            arith("requirements without a band", sum("band" not in e for e in led["requirements"].values()), "count"),
            arith("assumptions without a band", sum("band" not in e for e in led["assumptions"].values()), "count"),
            val("info-gap variables", INFO, ["n_variables"]), val("info-gap active variables", INFO, ["n_act"]),
            arith("info-gap inert variables", len(load(INFO)["inert_variables"]), "length of inert_variables")]


def a8():
    p = ROOT / PYTEST
    if not p.exists():
        return []
    return [val(n, PYTEST, [k], u) for n, k, u in (("commit", "commit", ""), ("clean tree", "clean_tree", ""),
            ("exit code", "exit_code", ""), ("passed", "passed", ""), ("failed", "failed", ""),
            ("xfailed", "xfailed", ""), ("duration", "duration_s", "s"))]


def a9():
    return [val("score, pusher", SCORES, ["score", "pusher"]), val("score, tractor", SCORES, ["score", "tractor"]),
            val("W0, pusher (superseded sizes)", SCORES, ["table", 0, "pusher"], "lb"),
            val("W0, tractor (superseded sizes)", SCORES, ["table", 0, "tractor"], "lb"),
            val("weight of the W0 criterion", SCORES, ["table", 0, "weight"])]


def a10():
    return [row(24, "fuel fits", "value", "ft^3"), row(24, "fuel fits", "limit", "ft^3"),
            row(25, "nose-wheel load, full", "value"), row(26, "nose-wheel load, empty", "value"),
            row(27, "main gear stows", "value", "ft"), row(28, "propeller clearance", "value", "in"),
            row(28, "propeller clearance", "limit", "in")]


def a12():
    return [val("ledger loiter_h", LEDGER, ["requirements", "loiter_h", "value"], "h")]


# id, item, status, review verdict (text), records, value builder, note
ITEMS = [
    ("A1", "Every requirement traces to a number with its margin", "pass",
     "pass. The table gives value and limit, not a margin column; R3 and R11 have no row; R6 is not checked (assumption R-f)",
     [COMPLIANCE, INFO], a1, ""),
    ("A2", "Weight closes; fractions sum below 1; fit against build-up reported and explained", "pass with caveat",
     "pass on closure; the explanation of the build-up against the fits is not written for this design",
     [DESIGN], a2, ""),
    ("A3", "Fuel closes for every segment, with the 6 % allowance", "pass", "pass", [DESIGN], a3, ""),
    ("A4", "Static margin in R13 full and empty; trim with authority; rotation possible", "pass",
     "pass. Margins by layout construction (B-6); the rotation margin is thin", [COMPLIANCE, DESIGN], a4, ""),
    ("A5", "Structure sized for the larger of manoeuvre and gust at both altitudes", "pass", "pass", [DESIGN], a5, ""),
    ("A6", "Installed power at 20,000 ft meets climb and ceiling; production engine within the rubber engine's band; "
     "fixed-engine re-size recorded", "pass with caveat",
     "pass on power; the rubber-band clause is not testable (the engine was fixed by ruling R-a)", [COMPLIANCE], a6,
     "The ceiling row value 31,738 ft is Stage 1's, read above the 30,000 ft engine-table top; ruling B-9c quotes the "
     "engine-cycle value 30,407 to 30,432 ft with that caveat. R12 is met by every value."),
    ("A7", "Every assumption has a source and a band; out-of-calibration uses listed", "pass with caveat",
     "pass on sources; partly on bands; the out-of-calibration list is not testable on this design",
     [LEDGER, INFO], a7, "Unbanded entries are as at earlier rounds, which passed A7."),
    ("A8", "Every Raymer equation used has a passing printed-value test", "pass",
     "pass on the reviewer's run (397 passed, 1 xfailed at 4ee2ae4), which was not a record; the recorded report is "
     "the pytest record below", [PYTEST], a8,
     "The reviewer's run is not a record and is not quoted as a value. The last earlier record is "
     "runs/task12/stage1/2026-11-25/test_report.txt."),
    ("A9", "Concept choice justified by its scoring table; rejected concept kept", "inherited (B-9a)",
     "not testable on this design; inherited from the frozen configuration (pusher frozen at Gate A round 3)",
     [SCORES, PACKAGE], a9, "Scores are those of the 2026-11-25 package, not of the W/S 13, A 8 sizes."),
    ("A10", "Layout fits: tanks, payload bay, gear, CG range", "pass with caveat",
     "pass on the recorded rows; the payload bay is not testable (no row has ever checked it)", [COMPLIANCE], a10, ""),
    ("A11", "Every risk names how Stage 3 will measure it", "inherited (B-9a)",
     "not testable on this design; inherited. The 2026-11-25 package's risk list is the same configuration", [PACKAGE],
     lambda: [], "No value is read: the item is a list in the package, not a number."),
    ("A12", "Defaults R10 to R15 confirmed or changed by the owner", "pass",
     "pass; confirmed at rounds 1 and 2, R12 revised at round 4, R13 ruled at Gate B (B-6)", [LEDGER], a12, ""),
]


def sha(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def build():
    items = []
    for i, item, status, verdict, records, f, note in ITEMS:
        values = f()
        recs = list(records)
        items.append({"id": i, "item": item, "status": status, "review_verdict": verdict, "records": recs,
                      "record_sha256": {r: sha(r) for r in recs if r.endswith((".json", ".yaml")) and (ROOT / r).exists()},
                      "values": values, "note": note})
    a8 = next(x for x in items if x["id"] == "A8")
    if a8["values"]:
        r = {v["name"]: v["value"] for v in a8["values"]}
        ok = r["exit code"] == 0 and r["failed"] == 0
        a8["status"] = "pass" if ok else "fail"
    else:
        a8["status"] = "pass on the reviewer's run; no record yet"
        a8["note"] += " No pytest record existed when this file was generated."
    return {"design": BASE, "review": REVIEW, "rulings": "B-9a (A9 and A11 inherited), B-10c",
            "status_counts": {s: sum(x["status"] == s for x in items) for s in dict.fromkeys(x["status"] for x in items)},
            "items": items}


def fmt(v):
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def render(d):
    L = ["# Task 12 Gate A re-check, W/S 13, A 8 baseline", "",
         "Generated by `postprocess/task12_gateA_recheck.py` from `runs/task12/stage3/2026-11-27/gateA_recheck_ws13a8/gateA.json`.",
         f"Verdicts: `{d['review']}`, section 5, and rulings {d['rulings']}. Values are read from the records named in each "
         "row; \"arithmetic\" marks a count, sum or ratio of read values. Baseline record: `" + d["design"] + "`.", "",
         "| # | Item | Verdict | Records |", "|---|---|---|---|"]
    for x in d["items"]:
        L.append(f"| {x['id']} | {x['item']} | **{x['status']}** | " + ", ".join(f"`{r}`" for r in x["records"]) + " |")
    L.append("")
    for x in d["items"]:
        L += [f"## {x['id']}: {x['item']}", "", f"Verdict: **{x['status']}**. Review: {x['review_verdict']}.", ""]
        if x["values"]:
            L += ["| Value | Quoted | Units | Read from |", "|---|---|---|---|"]
            for v in x["values"]:
                src = f"`{v['source']}` {v['key']}" if "source" in v else "arithmetic: " + v["arithmetic"]
                L.append(f"| {v['name']} | {fmt(v['value'])} | {v['units']} | {src} |")
            L.append("")
        if x["note"]:
            L += [x["note"], ""]
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--md", required=True)
    a = p.parse_args()
    d = build()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(d, indent=2) + "\n")
    Path(a.md).write_text(render(d) + "\n")


if __name__ == "__main__":
    main()

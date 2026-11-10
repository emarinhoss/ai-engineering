"""The SU2 pool's per-design records and results table (T10.9d).

    python -m analysis.pool_af_results --cases designs/pool_af_cases.csv \
        --designs designs/pool_drone96.csv --runs runs --out runs/pool_af/<date> [--tag pool_af ...] \
        [--accept-budget-exhausted INDEX ...]

--accept-budget-exhausted (decision 9, 2026-11-10: designs 8 and 28): that design's runs that used
their whole iteration budget (exit 0, no timeout, iterations at max_iter) are kept as well, and its
section carries the flags budget_exhausted_accepted=k and the largest cl and cd drift among them.

For every design index of the cases table under the FIRST --tag (default pool_af) this collects the
case records that have landed at <runs>/<tag>/<case_id>/result.json (where
mcp_server.queue.ingest_result puts them), counts the ones analysis.drone_polar.polar keeps, and
evaluates the design with analysis.drone_design.design_record when at least three are kept. It
writes to --out:
  results.csv          analysis.drone_grid COLUMNS, then n_cases, n_kept, angles_kept, cases, flags,
                       status. One row per design, always:
                         complete    evaluated; error empty (gates may still be set)
                         incomplete  fewer than 3 kept angles; error "incomplete: k of n angles",
                                     value columns empty
                         failed      design_record raised; its message in error
  records/<id>.json    the design_record of each complete design (id = drone_design.design_id)
  bias.csv             only with two or more tags: kept records of the first tag (coarse) against
                       the second (medium) at the angles both have, per design
  record.json          commit, counts, tags, input and output sha256, ledger sha256
Only the first tag is aggregated into results.csv, so a table never mixes two meshes in one polar;
the other tags' designs get their own table by running with that tag first.
"""
import argparse
import csv
import json
from pathlib import Path

from analysis import drone_grid, drone_polar
from analysis.drone_design import design_id, design_record

EXTRA = ("n_cases", "n_kept", "angles_kept", "cases", "flags", "status")
BIAS_COLUMNS = ("index", "alpha_deg", "cl_coarse", "cl_medium", "cd_coarse", "cd_medium",
                "cl_medium_over_coarse", "cd_medium_over_coarse")
MIN_KEPT = 3                       # drone_polar.polar refuses fewer


def kept(records, accept_exhausted=frozenset()):
    """The records drone_polar.polar keeps (same rule as drone_validation._usable), by alpha;
    plus the budget-exhausted runs of the case ids in accept_exhausted (an explicit ruling)."""
    out = [r for r in records if r["convergence"]["status"] in drone_polar.GOOD
           or drone_polar._cauchy_stopped(r)
           or (r.get("case_id") in accept_exhausted and drone_polar._budget_exhausted(r))]
    return sorted(out, key=lambda r: r["params"]["alpha_deg"])


def read_cases(path, tag):
    """{design index: [case_id, ...]} for the rows of one tag, in table order."""
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["tag"] == tag:
                out.setdefault(int(r["index"]), []).append(r["case_id"])
    return out


def landed(runs, tag, case_ids):
    """The result.json records that exist for these cases; a case not yet landed is skipped."""
    out = []
    for cid in case_ids:
        p = Path(runs) / tag / cid / "result.json"
        if p.exists():
            out.append(json.loads(p.read_text()))
    return out


def design_row(index, params, case_ids, records, accept_exhausted=frozenset()):
    """One results.csv row (dict keyed by COLUMNS + EXTRA) and the design record or None."""
    good = kept(records, accept_exhausted)
    row = {"index": index, **params, "gates": "", "error": "",
           "n_cases": len(records), "n_kept": len(good),
           "angles_kept": ";".join(str(float(r["params"]["alpha_deg"])) for r in good),
           "cases": ";".join(r["case_id"] for r in good), "flags": ""}
    if len(good) < MIN_KEPT:
        row["error"] = f"incomplete: {len(good)} of {len(case_ids)} angles"
        row["status"] = "incomplete"
        return row, None
    try:
        rec = design_record(params, records, accept_exhausted=accept_exhausted)
    # a bad polar, a closure that fails or a record missing a field is a recorded row; any other
    # exception is a bug in this code and is allowed to stop the run
    except (ValueError, ArithmeticError, KeyError, TypeError) as exc:
        row["error"] = str(exc)
        row["status"] = "failed"
        return row, None
    row.update(drone_grid.flatten(rec["result"]))
    row["flags"] = ";".join(rec["section"]["flags"])
    row["status"] = "complete"
    return row, rec


def bias_rows(index, coarse, medium):
    """Rows of bias.csv for one design: kept records of both tags at their shared angles."""
    c = {round(r["params"]["alpha_deg"], 6): r["metrics"] for r in kept(coarse)}
    m = {round(r["params"]["alpha_deg"], 6): r["metrics"] for r in kept(medium)}
    rows = []
    for a in sorted(set(c) & set(m)):
        rows.append({"index": index, "alpha_deg": float(a),
                     "cl_coarse": c[a]["cl"], "cl_medium": m[a]["cl"],
                     "cd_coarse": c[a]["cd"], "cd_medium": m[a]["cd"],
                     "cl_medium_over_coarse": m[a]["cl"] / c[a]["cl"],
                     "cd_medium_over_coarse": m[a]["cd"] / c[a]["cd"]})
    return rows


def _write(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, restval="")
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", required=True, help="case table (index, case_id, tag, ...)")
    ap.add_argument("--designs", required=True, help="design table (index + the six inputs)")
    ap.add_argument("--runs", default="runs", help="root holding <tag>/<case_id>/result.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", action="append", default=None,
                    help="case tag, repeatable (default pool_af); the first is tabulated")
    ap.add_argument("--accept-budget-exhausted", type=int, action="append", default=[],
                    metavar="INDEX", help="design index whose budget-exhausted runs are accepted "
                    "(a ruling; repeatable; flagged in the design's section flags)")
    a = ap.parse_args(argv)
    tags = a.tag or ["pool_af"]

    designs = dict(drone_grid.read_design(a.designs))
    cases = read_cases(a.cases, tags[0])
    missing = sorted(set(cases) - set(designs))
    if missing:
        raise SystemExit(f"design indices {missing} are in {a.cases} but not in {a.designs}")

    out = Path(a.out)
    (out / "records").mkdir(parents=True, exist_ok=True)
    rows, counts = [], {"complete": 0, "incomplete": 0, "failed": 0}
    for index in sorted(cases):
        params = dict(zip(drone_grid.INPUTS, designs[index]))
        records = landed(a.runs, tags[0], cases[index])
        accept = frozenset(cases[index]) if index in a.accept_budget_exhausted else frozenset()
        row, rec = design_row(index, params, cases[index], records, accept)
        rows.append(row)
        counts[row["status"]] += 1
        if rec is not None:
            (out / "records" / f"{design_id(params)}.json").write_text(
                json.dumps(rec, indent=2, default=float) + "\n")
    _write(out / "results.csv", drone_grid.COLUMNS + EXTRA, rows)
    sha = {"results.csv": drone_grid.sha256(out / "results.csv")}

    if len(tags) >= 2:
        medium = read_cases(a.cases, tags[1])
        brows = []
        for index in sorted(set(cases) & set(medium)):
            brows += bias_rows(index, landed(a.runs, tags[0], cases[index]),
                               landed(a.runs, tags[1], medium[index]))
        _write(out / "bias.csv", BIAS_COLUMNS, brows)
        sha["bias.csv"] = drone_grid.sha256(out / "bias.csv")

    record = {
        "commit": drone_grid.git_commit(),
        "cases": a.cases, "designs_table": a.designs, "runs": a.runs, "tags": tags,
        "designs": len(rows), **counts,
        "accept_budget_exhausted": sorted(a.accept_budget_exhausted),
        "inputs_sha256": {a.cases: drone_grid.sha256(a.cases),
                          a.designs: drone_grid.sha256(a.designs)},
        "sha256": sha,
        "ledger_sha256": {p.name: drone_grid.sha256(p)
                          for p in sorted(Path("data/drone").glob("*.yaml"))},
    }
    (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"{len(rows)} designs under tag {tags[0]}: complete {counts['complete']}, "
          f"incomplete {counts['incomplete']}, failed {counts['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

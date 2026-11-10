"""T10.9d acceptance: the SU2 pool's per-design records and results table (Fable, 2026-11-08).

The script under test is analysis/pool_af_results.py. The contract:

  python -m analysis.pool_af_results --cases designs/pool_af_cases.csv \
      --designs designs/pool_drone96.csv --runs runs --out runs/pool_af/<date>

* results.csv has EXACTLY the analysis.drone_grid COLUMNS first (index, six inputs, scalars,
  masses, gates, error) so surrogate.replay --family drone, mf_drone and pareto read it unchanged,
  followed by: n_cases, n_kept, angles_kept, cases, flags, status.
* One row per design of the cases table, ALWAYS, whether or not its cases have landed: a design with
  fewer than three kept angles has status "incomplete", error "incomplete: k of n angles" and empty
  value columns; a design whose evaluation raised has status "failed" and the message in error;
  a complete design has status "complete" and empty error. Nothing is dropped silently.
* The design is evaluated with analysis.drone_design.design_record on the records
  analysis.drone_polar.polar keeps, so every row's flags carry the decision-8 V6e bias flags.
* records/<design_id>.json is written per complete design (the design_record), and record.json
  carries the commit, the counts, the sha256 of results.csv and the ledger hashes.
* --tag selects which case rows to aggregate (default pool_af); the pool_af_bias designs are
  aggregated by `--tag pool_af_bias` into their own table, and `bias.csv` (written when both tags
  are given) compares coarse against medium cl and cd at the shared angles per design.
"""
import csv
import json
from pathlib import Path

import pytest

from analysis import drone_grid, pool_af_results
from tests.task10.test_validation_e387 import su2_record

NOMINAL = sorted(Path("runs/nominal").glob("airfoil2d-*/result.json"))


def _tables(tmp_path, n_designs=2, angles=(-2.0, 2.0, 6.0, 10.0, 14.0), tag="pool_af"):
    designs = tmp_path / "designs.csv"
    with open(designs, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("index",) + drone_grid.INPUTS)
        for i in range(n_designs):
            w.writerow([i, 2.0 + 0.1 * i, 10.0, 0.6, 0.30, 4.0, 12.0])
    cases = tmp_path / "cases.csv"
    rows = []
    with open(cases, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("index", "case_id", "tag", "mesh_level", "reynolds", "alpha_deg"))
        for i in range(n_designs):
            for a in angles:
                cid = f"airfoil2d-{i:02d}{int(a + 10):02d}000000"
                w.writerow([i, cid, tag, "coarse", 200000.0, a])
                rows.append((i, cid, a))
    return designs, cases, rows


def _land(runs, tag, cid, alpha, cl, cd, **kw):
    """Put one result.json where mcp_server.queue.ingest_result would put it."""
    d = runs / tag / cid
    d.mkdir(parents=True)
    rec = su2_record(200000.0, alpha, cl, cd, **kw)
    rec["case_id"] = cid
    rec["params"] = {**rec["params"], "camber_pct": 4.0, "thickness_pct": 12.0, "tag": tag}
    del rec["params"]["airfoil"]
    (d / "result.json").write_text(json.dumps(rec))


def _rows(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def _polar(alpha):
    cl = 0.45 + 0.10 * alpha if alpha < 12 else 1.60
    return cl, 0.010 + 0.0004 * alpha * alpha


def test_results_table_has_the_grid_layout_first_and_one_row_per_design(tmp_path):
    designs, cases, rows = _tables(tmp_path)
    runs = tmp_path / "runs"
    for i, cid, a in rows:
        if i == 0:                                     # design 0 complete, design 1 nothing landed
            _land(runs, "pool_af", cid, a, *_polar(a))
    out = tmp_path / "out"
    pool_af_results.main(["--cases", str(cases), "--designs", str(designs), "--runs", str(runs),
                          "--out", str(out)])
    with open(out / "results.csv") as f:
        r = csv.DictReader(f)
        assert tuple(r.fieldnames[:len(drone_grid.COLUMNS)]) == drone_grid.COLUMNS
        assert r.fieldnames[len(drone_grid.COLUMNS):] == ["n_cases", "n_kept", "angles_kept",
                                                          "cases", "flags", "status"]
        table = {row["index"]: row for row in r}
    assert set(table) == {"0", "1"}
    done, missing = table["0"], table["1"]
    assert done["status"] == "complete" and done["error"] == "" and float(done["endurance_h"]) > 0
    assert done["n_cases"] == "5" and done["n_kept"] == "5"
    assert "v6e_ruling=decision8_accepted_with_bias" in done["flags"]
    assert missing["status"] == "incomplete" and missing["error"].startswith("incomplete: 0 of 5")
    assert missing["endurance_h"] == "" and missing["n_cases"] == "0"
    rec = json.loads((out / "record.json").read_text())
    assert rec["designs"] == 2 and rec["complete"] == 1 and rec["incomplete"] == 1
    assert rec["sha256"]["results.csv"] and "ledger_sha256" in rec
    assert len(list((out / "records").glob("drone-*.json"))) == 1


def test_a_design_with_three_kept_angles_is_complete_and_flagged(tmp_path):
    designs, cases, rows = _tables(tmp_path, n_designs=1)
    runs = tmp_path / "runs"
    for i, cid, a in rows:
        if a in (-2.0, 2.0, 6.0):
            _land(runs, "pool_af", cid, a, *_polar(a))
        elif a == 10.0:                                # landed but exhausted its budget: dropped
            _land(runs, "pool_af", cid, a, *_polar(a), iterations=6000)
    out = tmp_path / "out"
    pool_af_results.main(["--cases", str(cases), "--designs", str(designs), "--runs", str(runs),
                          "--out", str(out)])
    row = _rows(out / "results.csv")[0]
    assert row["status"] == "complete" and row["n_cases"] == "4" and row["n_kept"] == "3"
    assert "missing_angles" in row["flags"] and row["angles_kept"] == "-2.0;2.0;6.0"


def test_an_evaluation_that_raises_is_a_failed_row_not_a_crash(tmp_path, monkeypatch):
    designs, cases, rows = _tables(tmp_path, n_designs=1)
    runs = tmp_path / "runs"
    for i, cid, a in rows:
        _land(runs, "pool_af", cid, a, *_polar(a))

    def boom(*a, **k):
        raise ValueError("closure did not converge")
    monkeypatch.setattr(pool_af_results, "design_record", boom)
    out = tmp_path / "out"
    pool_af_results.main(["--cases", str(cases), "--designs", str(designs), "--runs", str(runs),
                          "--out", str(out)])
    row = _rows(out / "results.csv")[0]
    assert row["status"] == "failed" and "closure did not converge" in row["error"]


def test_results_table_is_readable_by_the_drone_replay_loader(tmp_path):
    from surrogate import replay
    designs, cases, rows = _tables(tmp_path, n_designs=2)
    runs = tmp_path / "runs"
    for i, cid, a in rows:
        _land(runs, "pool_af", cid, a, *_polar(a))
    out = tmp_path / "out"
    pool_af_results.main(["--cases", str(cases), "--designs", str(designs), "--runs", str(runs),
                          "--out", str(out)])
    pool = replay.load_pool(str(designs), str(out / "results.csv"), family="drone")
    assert len(pool["index"]) == 2


def test_bias_table_compares_coarse_with_medium_at_shared_angles(tmp_path):
    designs, cases_c, rows_c = _tables(tmp_path, n_designs=1)
    (tmp_path / "m").mkdir()
    _, cases_m, rows_m = _tables(tmp_path / "m", n_designs=1, angles=(2.0, 6.0, 10.0),
                                 tag="pool_af_bias")
    runs = tmp_path / "runs"
    for i, cid, a in rows_c:
        _land(runs, "pool_af", cid, a, *_polar(a))
    for i, cid, a in rows_m:
        cl, cd = _polar(a)
        _land(runs, "pool_af_bias", cid, a, 0.95 * cl, 1.10 * cd)      # medium: known offsets
    merged = tmp_path / "cases_all.csv"
    merged.write_text(cases_c.read_text() + "".join(cases_m.read_text().splitlines(True)[1:]))
    out = tmp_path / "out"
    pool_af_results.main(["--cases", str(merged), "--designs", str(designs), "--runs", str(runs),
                          "--out", str(out), "--tag", "pool_af", "--tag", "pool_af_bias"])
    bias = _rows(out / "bias.csv")
    assert {b["alpha_deg"] for b in bias} == {"2.0", "6.0", "10.0"}
    for b in bias:
        assert float(b["cl_medium_over_coarse"]) == pytest.approx(0.95, abs=1e-6)
        assert float(b["cd_medium_over_coarse"]) == pytest.approx(1.10, abs=1e-6)


@pytest.mark.skipif(len(NOMINAL) < 3, reason="needs the recorded nominal runs")
def test_the_recorded_nominal_runs_form_a_complete_design(tmp_path):
    """Real records: the six nominal angles of the NACA 4412-type section at Re 2e5."""
    designs = tmp_path / "designs.csv"
    designs.write_text("index," + ",".join(drone_grid.INPUTS) + "\n0,2.0,10.0,0.6,0.30,4.0,12.0\n")
    cases = tmp_path / "cases.csv"
    with open(cases, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("index", "case_id", "tag", "mesh_level", "reynolds", "alpha_deg"))
        for p in NOMINAL:
            rec = json.loads(p.read_text())
            w.writerow([0, rec["case_id"], "nominal", "medium", 200000.0, rec["params"]["alpha_deg"]])
    out = tmp_path / "out"
    pool_af_results.main(["--cases", str(cases), "--designs", str(designs), "--runs", "runs",
                          "--out", str(out), "--tag", "nominal"])
    row = _rows(out / "results.csv")[0]
    assert row["status"] == "complete"
    # two of the six nominal runs exhausted their budget (alpha 0 and 10) and are dropped
    assert row["n_cases"] == "6" and row["n_kept"] == "4" and "missing_angles" in row["flags"]
    assert 0.0 < float(row["endurance_h"]) < 24.0 and 0.5 < float(row["mtow_kg"]) < 10.0


# ---- decision 9 (Eder, 2026-11-10): accept the budget-exhausted runs of designs 8 and 28 ----

def _two_good_three_exhausted(runs, rows, design, **exhausted_kw):
    for i, cid, a in rows:
        if i != design:
            continue
        if a in (2.0, 6.0):
            _land(runs, "pool_af", cid, a, *_polar(a))
        else:
            kw = {"iterations": 6000, "cl_drift": 7.5, "cd_drift": 19.0, **exhausted_kw}
            _land(runs, "pool_af", cid, a, *_polar(a), **kw)


def _run(tmp_path, cases, designs, runs, *extra):
    out = tmp_path / "out"
    pool_af_results.main(["--cases", str(cases), "--designs", str(designs), "--runs", str(runs),
                          "--out", str(out), *extra])
    return out


def test_without_the_ruling_two_kept_angles_stay_incomplete(tmp_path):
    designs, cases, rows = _tables(tmp_path, n_designs=1)
    runs = tmp_path / "runs"
    _two_good_three_exhausted(runs, rows, 0)
    row = _rows(_run(tmp_path, cases, designs, runs) / "results.csv")[0]
    assert row["status"] == "incomplete" and row["n_kept"] == "2"


def test_the_ruling_keeps_that_designs_exhausted_runs_and_flags_them(tmp_path):
    designs, cases, rows = _tables(tmp_path, n_designs=2)
    runs = tmp_path / "runs"
    _two_good_three_exhausted(runs, rows, 0)
    _two_good_three_exhausted(runs, rows, 1)
    out = _run(tmp_path, cases, designs, runs, "--accept-budget-exhausted", "0")
    r0, r1 = _rows(out / "results.csv")
    assert r0["status"] == "complete" and r0["n_kept"] == "5"
    flags = r0["flags"].split(";")
    assert "budget_exhausted_accepted=3" in flags
    assert "exhausted_cl_drift_max_pct=7.5" in flags and "exhausted_cd_drift_max_pct=19.0" in flags
    assert r1["status"] == "incomplete" and r1["n_kept"] == "2"     # not named: rule unchanged
    assert json.loads((out / "record.json").read_text())["accept_budget_exhausted"] == [0]


def test_the_ruling_never_accepts_a_timeout_or_a_failed_run(tmp_path):
    designs, cases, rows = _tables(tmp_path, n_designs=1)
    runs = tmp_path / "runs"
    for i, cid, a in rows:
        if a in (2.0, 6.0):
            _land(runs, "pool_af", cid, a, *_polar(a))
        elif a == -2.0:                                # timed out at the budget
            _land(runs, "pool_af", cid, a, *_polar(a), iterations=6000)
            p = runs / "pool_af" / cid / "result.json"
            rec = json.loads(p.read_text())
            rec["run"]["timeout"] = True
            p.write_text(json.dumps(rec))
        else:                                          # non-zero exit at the budget
            _land(runs, "pool_af", cid, a, *_polar(a), iterations=6000)
            p = runs / "pool_af" / cid / "result.json"
            rec = json.loads(p.read_text())
            rec["run"]["exit_code"] = 1
            p.write_text(json.dumps(rec))
    row = _rows(_run(tmp_path, cases, designs, runs, "--accept-budget-exhausted", "0")
                / "results.csv")[0]
    assert row["status"] == "incomplete" and row["n_kept"] == "2"

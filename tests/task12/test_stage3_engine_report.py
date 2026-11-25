"""Engine report fixes of 2026-11-25 (review S3M-1, S3M-6, S3M-11a): the book check uses the burner of
the record's table, and the closing row is shown to be unable to fail."""
import json
from pathlib import Path

import pytest

from measurement import m250_engine as m250
from measurement import stage3_engine as se

ROOT = Path(__file__).resolve().parents[2]
M250_RECORD = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"


def test_validation_uses_the_burner_and_verdicts_come_from_code():
    msh, csh = se.validation_check("msh"), se.validation_check("csh")
    assert msh["burner"] == "msh" and msh["other_burner"] == "csh"
    # recorded MSH result (runs/task12/stage3/2026-11-21/appk_validation.json): 16 of 18, K.3 S fails at 17 and 35
    assert msh["summary"] == {"pass": 16, "total": 18}
    assert {r["case"] for r in msh["rows"] if r["verdict"] == "FAIL"} == {"K.3 S pi_c=17", "K.3 S pi_c=35"}
    assert csh["summary"]["pass"] < msh["summary"]["pass"]
    assert msh["other_summary"] == csh["summary"]
    for r in msh["rows"]:
        tol_ok = abs(r["deviation"]) <= r["tolerance"]
        assert (r["verdict"] == "PASS") == tol_ok


def test_recorded_burner_of_the_table_is_msh():
    table = json.loads((M250_RECORD.parent / "m250_table.json").read_text())
    assert table["burner"] == "msh"


def test_book_validation_burner_changes_the_part_throttle_rows():
    a = se.book_validation()["part_throttle_gap"][0]["model_eta_max_0_9"]
    b = se.book_validation("msh")["part_throttle_gap"][0]["model_eta_max_0_9"]
    assert b < a                   # MSH reads fuel consumption low against the book, csh high
    assert b == pytest.approx(0.311, abs=0.001)


def test_constant_sfc_would_also_pass_the_brochure_rows():
    rates = m250.ratings("450")
    to = rates["take_off"]["bsfc_max"]
    cs = se.constant_sfc_check(rates, to)
    for c in cs:        # by hand: 0.613 / brochure - 1
        assert c["deviation"] == pytest.approx(to / c["brochure"] - 1.0)
    assert all(c["within"] for c in cs)
    assert [round(c["deviation"], 3) for c in cs] == [-0.035, -0.038, -0.089]


def test_tp100_design_run_hashes_the_ledger_it_uses():
    tp100 = ROOT / "runs/task12/stage1/2026-11-21d/design_pusher.json"
    used = se.ledger_for(tp100)
    assert used == tp100.parent / "ledger.yaml" and used.exists()
    assert se.ledger_for() == Path(se.uav.LEDGER)
    import hashlib
    # the record's copy is a different file from the default ledger, so the hashes would have differed
    assert hashlib.sha256(used.read_bytes()).hexdigest() != hashlib.sha256(se.ledger_for().read_bytes()).hexdigest()

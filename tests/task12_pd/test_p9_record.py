"""Preliminary design P9: the records and the report. The acceptance verdicts are judged again from the records by the
spec's rules, the r1 ledger is the one the sizing used, every record comes from a clean tree, and the report's key
numbers are the records' numbers. Nothing here asks a row to pass."""
import json

import pytest

from prelim import p9_r1 as p9

P9 = p9.REPO / "runs/task12/pd/2026-11-28/p9"
REPORT = p9.REPO / "docs/validation/2026-11-28_task12_pd_p9.md"
pytestmark = pytest.mark.skipif(not (P9 / "summary/summary.json").exists(), reason="no P9 summary record yet")


def load(name):
    return json.loads((P9 / name).read_text())


def test_every_record_is_from_a_clean_tree_that_did_not_change():
    for name in ("pass0/inputs.json", "pass1/pass.json", "diagnose/diagnose.json", "summary/summary.json"):
        r = load(name)
        assert r["inputs"]["git_dirty"] is False and r["inputs"]["tree_unchanged_during_run"] is True, name


def test_pass1_sized_with_the_committed_r1_ledger_and_the_gate_b_seed():
    r = load("pass1/pass.json")
    assert r["inputs"]["ledger_sha256"] == p9.sha256(p9.LEDGER_R1)
    assert r["inputs"]["seed"] == 20261122 and r["inputs"]["n_samples"] == 200
    assert r["sizing"]["cell"] == {"P_hp": 450.0, "W_S": 13.0, "A": 8.0} and r["sizing"]["h_T"] == 1.05


def test_acceptance_row_1_follows_from_the_records():
    s, pas, diag = load("summary/summary.json"), load("pass1/pass.json"), load("diagnose/diagnose.json")
    row = next(a for a in s["acceptance"] if a["row"] == 1)
    no_design = pas["sizing"]["design"] is None
    h = diag["info_gap_lightest_8h"]["h_hat"]
    assert row["verdict"] == ("fail" if no_design or min(h["R5_guarantee"], h["R7"]) < 1.0 else "pass")
    assert row["value"]["lightest_8h_R5_guarantee"] == h["R5_guarantee"] and row["value"]["lightest_8h_R7"] == h["R7"]
    assert s["stopped"] is (row["verdict"] == "fail")


def test_the_lightest_design_is_stage1_at_8_h_with_the_r1_ledger():
    diag = load("diagnose/diagnose.json")
    rec = json.loads((p9.REPO / diag["lightest_8h"]["record"]).read_text())
    led = (p9.REPO / diag["lightest_8h"]["record"]).parent / "ledger.yaml"
    from conceptual import uav
    L = uav.load_ledger(led)[0]
    assert L["loiter_h"] == 8.0 and L["climb_model"] == "integrated" and L["airfoil_cl_max"] == 1.41777
    assert rec["W0_lb"] == diag["lightest_8h"]["W0_lb"]


def test_the_climb_limit_is_below_one_where_the_report_says_so():
    diag = load("diagnose/diagnose.json")
    lim = min(r["climb_limit_h"] for r in diag["corners"]["lightest_8h"] if "climb_limit_h" in r)
    s = load("summary/summary.json")
    assert next(a for a in s["acceptance"] if a["row"] == 1)["value"]["climb_limit_h_lightest_8h"] == lim


def test_the_report_is_generated_from_the_summary_and_marked_not_reviewed():
    from prelim import p9_report
    text = REPORT.read_text()
    assert text == p9_report.report_text(P9 / "summary/summary.json")
    assert "Not yet Fable-reviewed (rulings PD-22 and PD-25)" in "\n".join(text.splitlines()[:4])

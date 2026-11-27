"""The committed r0 record of preliminary design P0 (runs/task12/pd/2026-11-27/p0): its files say what the
spec asks of a record (commit, clean tree with the file list, seed, versions, log), and every acceptance verdict
in p0.json follows from the numbers stored beside it. The verdicts are recomputed here from the files; these
tests do not require a row to pass, only that the record tells the truth about it.
"""
import json

import pytest

from conceptual import uav
from prelim import p0_baseline as p0

OUT = p0.REPO / "runs/task12/pd/2026-11-27/p0"
R0 = OUT / "r0"
GATE_B_INFO_GAP = json.loads((p0.GATE_B / "info_gap.json").read_text())


@pytest.fixture(scope="module")
def p():
    return json.loads((OUT / "p0.json").read_text())


@pytest.fixture(scope="module")
def acc(p):
    return {a["row"]: a for a in p["acceptance"]}


def load(name, folder=R0):
    return json.loads((folder / name).read_text())


def test_record_has_its_files_and_they_say_where_they_come_from(p):
    for name in ("design_pusher.json", "ledger.yaml", "m250_table.json", "robust_candidate.json", "info_gap.json",
                 "cell_result.json"):
        assert (R0 / name).exists(), name
    assert (OUT / "run.log").read_text().strip()
    for inputs in (p["inputs"], load("info_gap.json")["inputs"], load("cell_result.json")["inputs"]):
        assert len(inputs["commit"]) == 40 and inputs["commit"] == p["inputs"]["commit"]
        assert inputs["git_dirty"] is False and inputs["git_dirty_files"] == []
        assert inputs["excluded"] == "runs/task12/pd/2026-11-27/p0"
        assert inputs["seed"] == 20261122 and inputs["n_samples"] == 200
        assert inputs["python"] and inputs["numpy"] and inputs["ledger_sha256"] and inputs["table_sha256"]
    assert p["inputs"]["tree_unchanged_during_run"] is True and p["tree_at_end"]["git_dirty"] is False
    assert "stopped" not in p and len(p["acceptance"]) == 6


def test_r0_table_is_the_committed_extended_table(p):
    assert p0.rs.sha256(R0 / "m250_table.json") == p["inputs"]["table_sha256"]
    assert load("m250_table.json")["h_ft"][-1] == 35000.0
    c = p0.compare_tables(load("m250_table.json", p0.GATE_B), load("m250_table.json"))
    assert c["passed"] == p["table"]["passed"]
    assert c["arrays_at_or_below_old_top"] == p["table"]["arrays_at_or_below_old_top"]


def test_row_1_and_2_verdicts_follow_from_the_files(p, acc):
    assert (acc[1]["verdict"] == "pass") == (p["table"]["passed"] and p["table_regenerated"]["equals_committed"])
    c = p0.compare_fields(load("design_pusher.json", p0.GATE_B), load("design_pusher.json"), p0.TOL_FIELDS,
                          skip=(p0.CEILING_FIELD,))
    assert [d["path"] for d in c["different"]] == [d["path"] for d in p["design_fields"]["different"]]
    assert [a["path"] for a in c["added"]] == [a["path"] for a in p["design_fields"]["added"]]
    assert (acc[2]["verdict"] == "pass") == (not c["different"] and not c["removed"])
    assert acc[2]["n_compared"] == c["n_compared"]


def test_row_3_and_4_verdicts_follow_from_the_files(p, acc):
    per = load("design_pusher.json")["performance"]
    c = p["ceiling"]
    assert c["stage1_ft"] == per["service_ceiling_ft"] and c["above_table_top"] == per["service_ceiling_above_table_top"]
    assert c["above_table_top"] == (per["service_ceiling_ft"] > per["engine_table_top_ft"])
    assert (acc[3]["verdict"] == "pass") == (c["above_table_top"] is False and c["independent_of_reads_above_top"])
    band = next(r for r in json.loads(p0.GATE_B_ENGINE.read_text())["rows"] if r["id"] == "ceiling")["stage3"]
    assert c["engine_cycle_family_ft"] == {"min": band["min"], "max": band["max"]}
    within = all(abs(per["service_ceiling_ft"] - band[k]) <= p0.TOL_CEILING_FT for k in ("min", "max"))
    L = uav.load_ledger(R0 / "ledger.yaml")[0]
    need = L["ceiling_ft"] + L["margin_ceiling_ft"]
    assert c["r12_required_ft"] == need
    assert (acc[4]["verdict"] == "pass") == (within and per["service_ceiling_ft"] >= need and band["min"] >= need)


def test_row_5_verdict_follows_from_the_stored_climb(p, acc):
    cl, d = p["climb"], load("design_pusher.json")
    row = next(r for r in d["mission"] if r["segment"] == "climb")
    assert cl["stage1_two_point_fuel_lb"] == pytest.approx(row["burned_lb"], rel=1e-12)
    assert cl["integrated"]["fuel_lb"] == pytest.approx(sum(s["fuel_lb"] for s in cl["steps"]), rel=1e-12)
    bound = cl["reserve_factor"] * abs(cl["integrated"]["fuel_lb"] - row["burned_lb"]) / d["fuel_lb"]
    assert cl["mission_fuel_change_bound"] == pytest.approx(bound, rel=1e-12)
    assert (acc[5]["verdict"] == "finding for r1") == (bound > p0.TOL_MISSION_FUEL)
    prof = cl["profile_at_takeoff_weight"]
    assert [r["h_ft"] for r in prof[:-1]] == [1000.0 * i for i in range(len(prof) - 1)]
    assert prof[-1]["h_ft"] == d["performance"]["service_ceiling_ft"]


def test_row_6_verdict_follows_from_the_two_info_gap_records(p, acc):
    new = load("info_gap.json")
    diff = {k: new["h_hat"][k]["h_hat"] - GATE_B_INFO_GAP["h_hat"][k]["h_hat"] for k in ("R5_guarantee", "R7")}
    assert acc[6]["deviation"] == diff
    assert (acc[6]["verdict"] == "pass") == all(abs(v) <= p0.TOL_HORIZON for v in diff.values())
    modes = load("cell_result.json")["modes"]
    assert p["info_gap"]["horizons"]["mode_cliff"]["r0"] == modes["cliff"]["h_hat"]
    assert p["info_gap"]["horizons"]["mode_endurance"]["r0"] == modes["endurance"]["h_hat"]
    assert new["inputs"]["seed"] == GATE_B_INFO_GAP["inputs"]["seed"]


def test_gate_b_record_was_not_touched():
    """Old records must not change: the Gate B files are as committed at the Gate B pass (commit 284cdf1)."""
    from prelim.record import git
    assert git("diff", "--stat", "284cdf1", "HEAD", "--", str(p0.GATE_B.relative_to(p0.REPO))).strip() == ""
    assert git("status", "--porcelain", "--", str(p0.GATE_B.relative_to(p0.REPO))).strip() == ""

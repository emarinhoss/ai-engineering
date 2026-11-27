"""The committed record of preliminary design P2 (runs/task12/pd/2026-11-27/p2): it says what the spec asks of a
record (commit, clean tree with the file list, versions, log), it says where the section data comes from and what
was not checked, and every acceptance verdict follows from the numbers stored beside it. The verdicts are
recomputed here from the files; these tests do not require a row to pass, only that the record tells the truth.
"""
import json

import pytest
import yaml

from conceptual import uav
from prelim import p2_section as p2

OUT = p2.REPO / "runs/task12/pd/2026-11-27/p2b"
OLD = p2.REPO / "runs/task12/pd/2026-11-27/p2"
R0 = json.loads((p2.R0 / "design_pusher.json").read_text())
LEDGER = uav.load_ledger(p2.R0 / "ledger.yaml")[0]


@pytest.fixture(scope="module")
def p():
    return json.loads((OUT / "p2.json").read_text())


@pytest.fixture(scope="module")
def acc(p):
    return {a["row"]: a for a in p["acceptance"]}


def test_record_has_its_files_and_says_where_it_comes_from(p):
    for name in ("p2.json", "run.log"):
        assert (OUT / name).read_text().strip(), name
    i = p["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-27/p2b"
    assert i["tree_unchanged_during_run"] is True and p["tree_at_end"]["git_dirty"] is False
    assert i["seed"] is None and i["python"] and i["numpy"] and i["command"].startswith("python -m prelim.p2_section")
    for key, path in i["files"].items():                                             # the inputs are the committed files
        assert p2.sha256(p2.REPO / path) == i["sha256"][key], path
    assert p["baseline"] == "runs/task12/pd/2026-11-27/p0/r0" and len(p["acceptance"]) == 8
    assert "checked against the report's figure" in p["evidence_class"] and p["supersedes"] == "runs/task12/pd/2026-11-27/p2"


def test_record_carries_the_source_record_and_the_figure_check(p, acc):
    s = p["source"]
    assert s == json.loads(json.dumps(yaml.safe_load(p2.SOURCE.read_text())))        # JSON turns the set numbers into text
    assert s["report"]["opened_in_this_session"] is True and s["reading"]["read_twice"] is True
    assert s["sections"]["naca4415"]["figure"] is None and s["sections"]["naca4415"]["page"] == 142
    want = p2.figure_check(s, p2.measured_sets("naca4415"))
    assert p["figure_check"]["n_rows"] == want["n_rows"] == 11 and p["figure_check"]["all_agree"] == want["all_agree"]
    for got, w in zip(p["figure_check"]["rows"], want["rows"]):
        assert got["agrees"] == w["agrees"] == (abs(got["digitized"] - 0.5 * (got["reading_a"] + got["reading_b"])) <= got["uncertainty"])
        assert got["digitized"] == pytest.approx(w["digitized"], rel=1e-12)
    assert acc[8]["verdict"] == ("pass" if want["all_agree"] else "disagreement reported")
    at = p["section_at_stall"]["set"]
    assert acc[1]["provisional"] == acc[2]["provisional"] == p2.is_provisional(want, "cl_max", at)
    assert acc[3]["provisional"] == p2.is_provisional(want, "cm_c4_linear_range", at)
    assert s["digitization"]["files"]["142.ALL"]["sha256"] == p["inputs"]["sha256"]["digitized_4415"]
    assert p["sections"] == {"wing": "naca4415", "tail": "naca0012", "tail_data": p["sections"]["tail_data"]}
    assert p["sections"]["tail_data"]["status"] == "not obtained"


def test_measured_numbers_are_the_committed_files(p):
    sets = p2.measured_sets("naca4415")
    assert [s["set"] for s in p["measured"]] == [s["set"] for s in sets] == [1, 2, 3, 4]
    for got, want in zip(p["measured"], sets):
        assert got["reynolds"] == want["reynolds"] and got["surface"] == want["surface"]
        assert got["lift"] == [list(q) for q in want["lift"]]
        assert got["summary"]["cl_max"] == want["summary"]["cl_max"] == max(c for _, c in want["lift"])
        assert got["summary"]["fit"] == pytest.approx(want["summary"]["fit"], rel=1e-12)


def test_reynolds_table_is_r0s(p):
    want = p2.reynolds_table(R0, LEDGER)
    assert len(p["reynolds"]) == len(want) == 12
    for got, w in zip(p["reynolds"], want):
        assert (got["condition"], got["station"]) == (w["condition"], w["station"])
        assert got["reynolds"] == pytest.approx(w["reynolds"], rel=1e-12) and got["mach"] == pytest.approx(w["mach"], rel=1e-12)


def test_row_1_section_maximum_lift(p, acc):
    at = p["section_at_stall"]
    smooth = [s for s in p["measured"] if s["surface"] == "smooth"]
    assert at["reynolds"] == p2.nearest_reynolds(at["stall_reynolds"], [s["reynolds"] for s in smooth])
    assert at["cl_max"] == next(s for s in smooth if s["reynolds"] == at["reynolds"])["summary"]["cl_max"]
    inside = p2.CL_MAX_BAND[0] <= at["cl_max"] <= p2.CL_MAX_BAND[1]
    assert acc[1]["value"] == at["cl_max"] and acc[1]["verdict"] == ("pass" if inside else "section rejected (PD-5)")


def test_row_2_wing_maximum_lift_and_the_refly(p, acc):
    w, f = p["wing"], p["refly"]
    assert w["measured"]["clean_12_15"] == pytest.approx(0.9 * p["section_at_stall"]["cl_max"], rel=1e-12)
    assert w["record"]["clean"] == pytest.approx(R0["CL_max"]["clean"], rel=1e-12)
    assert acc[2]["value"] == w["measured"]["clean_12_15"] and acc[2]["record"] == 1.35
    assert acc[2]["verdict"] == ("finding for r1" if acc[2]["value"] < 1.35 else "pass (not lower)")
    loiter = next(m for m in R0["mission"] if m["segment"] == "loiter")
    assert f["record"]["hours_on_station"] == pytest.approx(loiter["leg_time_h"], abs=0.002)   # the refly starts from r0
    assert f["record"]["loiter_speed_kt"] == pytest.approx(loiter["V_kt"], rel=2e-4)
    assert f["measured"]["airfoil_cl_max"] == p["section_at_stall"]["cl_max"]
    assert f["measured"]["CL_max"]["clean"] == pytest.approx(w["measured"]["clean_12_15"], rel=1e-12)
    assert acc[2]["hours_on_station"] == f["measured"]["hours_on_station"]
    assert acc[2]["loiter_speed_kt"] == f["measured"]["loiter_speed_kt"]
    assert f["measured"]["W0_lb"] == pytest.approx(R0["W0_lb"], abs=0.02)                      # r0 is not re-sized
    if acc[2]["verdict"] == "finding for r1":                                                  # less lift: faster and shorter
        assert f["measured"]["loiter_speed_kt"] > f["record"]["loiter_speed_kt"]
        assert f["measured"]["hours_on_station"] < f["record"]["hours_on_station"]
    cell = json.loads((p2.R0 / "cell_result.json").read_text())["modes"]["endurance"]["worst_at_h1"]
    assert f["corner_h1_record"]["hours_on_station"] == pytest.approx(cell["hours"], abs=0.002)


def test_row_3_section_moment(p, acc):
    at = p["section_at_stall"]
    inside = p2.CM0_BAND[0] <= at["cm_c4_linear_range"] <= p2.CM0_BAND[1]
    assert acc[3]["value"] == at["cm_c4_linear_range"] and acc[3]["ledger_value"] == LEDGER["airfoil_cm0"]
    assert acc[3]["verdict"] == ("pass" if inside else "finding for P4")


def test_rows_4_to_7(p, acc):
    assert acc[4]["verdict"] == "reported, no verdict" and acc[4]["cl_max_rough"] == p["roughness"]["rough"]["cl_max"]
    assert acc[5]["verdict"] == "not run" and "O-1" in acc[5]["reason"] and p["su2"]["status"] == "not run"
    assert p["su2"]["case_files"] == "none written" and len(p["su2"]["queue"]) == 20
    c = p["digitization_check"]
    ok = abs(c["alpha0_difference_deg"]) <= p2.TOL_ALPHA0_DEG and p2.SLOPE_RATIO_RANGE[0] <= c["slope_over_2pi"] <= p2.SLOPE_RATIO_RANGE[1]
    assert acc[6]["verdict"] == ("pass" if ok else "fail")
    x = p["xfoil"]
    assert acc[7]["verdict"] == ("reported, no verdict" if x["status"] == "run" else "not run")
    if x["status"] == "run":
        assert "no verdict rests on it" in x["label"] and x["version"]
        for q in x["polars"]:
            name = f"{q['section']}_re{q['reynolds']:.0f}"
            rows = p2.parse_xfoil_polar((OUT / "xfoil" / f"{name}_up.txt").read_text()) \
                + p2.parse_xfoil_polar((OUT / "xfoil" / f"{name}_down.txt").read_text())
            assert {r["alpha_deg"] for r in rows} == {r["alpha_deg"] for r in q["rows"]}        # the stored polar files
            assert q["summary"]["cl_max"] == max(r["cl"] for r in q["rows"])


def test_the_superseded_record_is_kept_and_its_numbers_did_not_change(p):
    old = json.loads((OLD / "p2.json").read_text())
    assert "superseded by `runs/task12/pd/2026-11-27/p2b`" in (OLD / "SUPERSEDED.md").read_text()
    assert old["inputs"]["commit"] != p["inputs"]["commit"] and old["inputs"]["sha256"]["digitized_4415"] == p["inputs"]["sha256"]["digitized_4415"]
    for a_old, a_new in zip(old["acceptance"], p["acceptance"]):                 # rows 1 to 7: same verdicts and values
        assert a_old["verdict"] == a_new["verdict"] and a_old.get("value") == pytest.approx(a_new.get("value"))
    assert old["refly"]["measured"]["hours_on_station"] == pytest.approx(p["refly"]["measured"]["hours_on_station"], abs=1e-9)


def test_r0_is_untouched(p):
    p1 = json.loads((p2.REPO / "runs/task12/pd/2026-11-27/p1/p1.json").read_text())
    assert p["inputs"]["sha256"]["r0_design"] == p1["inputs"]["sha256"]["r0_design"] == p2.sha256(p2.R0 / "design_pusher.json")

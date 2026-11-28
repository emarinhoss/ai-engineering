"""The committed record of preliminary design P5 (runs/task12/pd/2026-11-28/p5): where it comes from, that every
verdict follows from the numbers beside it, and that the numbers are what the code gives now. These tests do not
require any row to pass. Written before the run (tests first); run on Opus 5.5 under ruling PD-22, not yet
Fable-reviewed."""
import json

import pytest

from conceptual import raymer_loads as loads
from prelim import p5_loads as p5

OUT = p5.REPO / "runs/task12/pd/2026-11-28/p5"


@pytest.fixture(scope="module")
def r():
    return json.loads((OUT / "p5.json").read_text())


@pytest.fixture(scope="module")
def ctx():
    return p5.context()


def test_record_says_where_it_comes_from(r):
    for name in ("p5.json", "run.log"):
        assert (OUT / name).stat().st_size > 0, name
    i = r["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-28/p5" and i["tree_unchanged_during_run"] is True
    assert i["seed"] is None and i["python"] and i["scipy"] and i["command"].startswith("python -m prelim.p5_loads")
    for key, path in i["files"].items():
        assert p5.sha256(p5.REPO / path) == i["sha256"][key], path
    assert r["sources"] == json.loads(json.dumps(p5.load_sources()))
    assert r["review"] == "Not yet Fable-reviewed (ruling PD-22)"
    assert not list(OUT.rglob("*.pdf"))


def test_weights_are_r0s_and_p4bs(r, ctx):
    d, w = ctx["d"], r["weights"]
    zf = d["W0_lb"] - d["fuel_lb"]
    assert w["takeoff"] == d["W0_lb"] and w["zero_fuel"] == pytest.approx(zf, rel=1e-12)
    assert w["payload_off_no_ballast"] == pytest.approx(zf - 500.0, rel=1e-12)
    assert w["payload_off_with_ballast"] == pytest.approx(zf - 500.0 + r["ballast_lb"], rel=1e-12)
    p4b = json.loads(p5.P4B_RECORD.read_text())
    assert r["ballast_lb"] == p4b["candidates"][p4b["selection"]["chosen"]]["measures"]["payload_off"]["ballast_every_loading_lb"]
    assert r["negative_lift"]["wing_CL_neg_12_15"] == pytest.approx(0.9 * r["negative_lift"]["section_cl_min"], rel=1e-12)
    assert r["negative_lift"]["section_cl_min"] == pytest.approx(-0.880, abs=5e-4)


def test_row1_verdict_and_numbers(r, ctx):
    a = r["row1"]
    for p in a["points"]:
        assert p["deviation"] == pytest.approx(p["cs23_mean_geometric_chord"] / p["record"] - 1.0, rel=1e-12)
        assert p["cs23_mean_aerodynamic_chord"] == pytest.approx(p["record"], rel=1e-6)   # same chord: a coding check
    assert a["verdict"] == ("pass" if max(abs(p["deviation"]) for p in a["points"]) <= a["tolerance"] else "fail")
    assert a["tolerance"] == 0.05 and a["mean_geometric_chord_ft"] == pytest.approx(r["r0"]["S_ft2"] / r["r0"]["span_ft"], rel=1e-12)
    assert a == json.loads(json.dumps(p5._plain(p5.row1(ctx))))


def test_row2_verdict_and_numbers(r, ctx):
    a = r["row2"]
    assert len(a["points"]) == 4 and a["tolerance"] == 0.05 and a["H_chords"] == 12.5
    for p in a["points"]:
        assert p["K_14_6"] == pytest.approx(loads.gust_alleviation_subsonic(p["mu"]), rel=1e-12)
        assert p["deviation"] == pytest.approx(p["K_integrated"] / p["K_14_6"] - 1.0, rel=1e-12)
        assert p["n_14_6"] == pytest.approx(p["n_record"], rel=1e-6)              # (14.6) at the record's mass ratio is the record
        assert p["K_integrated"] == pytest.approx(p5.gust_factor(p["mu"]), rel=1e-9)
    assert a["verdict"] == ("pass" if max(abs(p["deviation"]) for p in a["points"]) <= a["tolerance"] else "fail")


def test_row3_verdict_and_numbers(r, ctx):
    a = r["row3"]
    lim = a["limits"]
    assert lim == {"positive": 3.8, "negative_gust": -1.7, "negative_manoeuvre": -1.8}
    assert len(a["points"]) == 12
    up, down = max(p["n_up"] for p in a["points"]), min(p["n_down"] for p in a["points"])
    assert a["worst_up"]["n_up"] == up and a["worst_down"]["n_down"] == down
    assert a["gust_inside"] is (up <= 3.8 and down >= -1.7)
    assert a["verdict"] == ("pass" if a["gust_inside"] and a["manoeuvre_inside"] else "fail")
    # the gust points at V_C and V_D reproduce r0's own gusts entries (Stage 1's formula, slope at the speed's Mach)
    for p in a["points"]:
        if p["speed"] == "V_C":
            assert p["n_up"] == pytest.approx(r["r0"]["gusts"][f"{p['altitude']}/{p['weight']}_weight"], rel=1e-6)
    assert a == json.loads(json.dumps(p5._plain(p5.row3(ctx))))


def test_row4_has_no_verdict_and_its_weight_cost_comes_from_stage1(r):
    a = r["row4"]
    assert a["verdict"].startswith("reported") and a["limits"]["positive_ultimate"] == pytest.approx(5.7, rel=1e-12)
    assert a["stage1_at_ruled_limit"]["W0_lb"] == pytest.approx(r["r0"]["W0_lb"], rel=1e-9)   # Stage 1 at 3.8 is r0
    for name, case in a["cases"].items():
        cleared = [p for p in case["points"] if p["speed"] in ("V_C", "V_D")]
        assert case["largest_up_V_C_V_D"] == max(p["n_up"] for p in cleared)
        assert case["stage1_raised"]["limit_load_factor"] == pytest.approx(max(case["largest_up_V_C_V_D"], 3.8), rel=1e-12)
        assert case["W0_change_lb"] == pytest.approx(case["stage1_raised"]["W0_lb"] - a["stage1_at_ruled_limit"]["W0_lb"], rel=1e-12)
        for p in case["points"]:
            assert p["above_positive_limit"] is (p["n_up"] > 3.8) and p["below_negative_ultimate"] is (p["n_down"] < -2.7)
    for p in a["cases"]["cs23_speeds"]["points"]:
        assert p["U_de_fps"] in (50.0, 25.0) or 25.0 < p["U_de_fps"] < 50.0


def test_row5_operating_case_and_limits(r, ctx):
    a = r["row5"]
    assert a["operating_case"] == "payload_off_with_ballast" and a["hypothetical_case"] == "payload_off_no_ballast"
    assert a["verdict"].startswith("reported")
    for name, case in a["cases"].items():
        assert case["W_lb"] == pytest.approx(r["weights"][name], rel=1e-12)
        for x in case["operating_limit"]:
            assert x["V_eas_kt"] <= r["r0"]["V_D_kt"] + 1e-9
            assert x["at_or_above_V_C"] is (x["V_eas_kt"] >= r["r0"]["V_C_kt"] - 1e-6)
            assert (x["limited_by"] is None) is (x["V_eas_kt"] == pytest.approx(r["r0"]["V_D_kt"], rel=1e-12))
    assert a == json.loads(json.dumps(p5._plain(p5.row5(ctx))))


def test_cs23_least_cruise_speed_is_reported(r):
    v = r["cs23_design_cruise_speed"]
    assert v["V_C_min_kt"] == pytest.approx(33.0 * (r["r0"]["W0_lb"] / r["r0"]["S_ft2"]) ** 0.5, rel=1e-12)
    assert v["V_C_kt"] == pytest.approx(r["r0"]["V_C_kt"], rel=1e-12)
    assert v["V_D_min_kt"] == pytest.approx(1.40 * v["V_C_min_kt"], rel=1e-12) and v["V_D_kt"] == pytest.approx(r["r0"]["V_D_kt"], rel=1e-12)


def test_acceptance_list_matches_rows(r):
    assert [x["row"] for x in r["acceptance"]] == [1, 2, 3, 4, 5]
    for x in r["acceptance"]:
        assert x["verdict"] == r[f"row{x['row']}"]["verdict"]

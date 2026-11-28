"""The committed record of preliminary design P7 (runs/task12/pd/2026-11-28/p7): where it comes from, that every
verdict follows from the numbers beside it, and that the numbers are what the code gives now. These tests do not
require any row to pass. Written before the run (tests first); run on Opus 5.5 under ruling PD-22, not yet
Fable-reviewed."""
import json

import numpy as np
import pytest

from prelim import p7_spar as p7

OUT = p7.REPO / "runs/task12/pd/2026-11-28/p7"


@pytest.fixture(scope="module")
def r():
    return json.loads((OUT / "p7.json").read_text())


@pytest.fixture(scope="module")
def ctx():
    return p7.context()


@pytest.fixture(scope="module")
def base(ctx, r):
    lattice = None
    if r["row2"]["used"] == "lattice":
        lv = r["row2"]["lattice"][r["row2"]["lattice_level"]]
        lattice = (np.array(lv["y_ft"]), np.array(lv["cl_c_ft"]), np.array(lv["dy_ft"]))
    b = p7.solve(ctx, ctx["lay_r0"], ctx["cg_r0"], "r0", r["row2"]["used"], lattice)
    b["shape"], b["lattice"] = r["row2"]["used"], lattice
    return b


def test_record_says_where_it_comes_from(r):
    for name in ("p7.json", "run.log"):
        assert (OUT / name).stat().st_size > 0, name
    i = r["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-28/p7" and i["tree_unchanged_during_run"] is True
    assert i["seed"] is None and i["python"] and i["numpy"] and i["command"].startswith("python -m prelim.p7_spar")
    for key, path in i["files"].items():
        assert p7.sha256(p7.REPO / path) == i["sha256"][key], path
    assert r["choices"] == json.loads(json.dumps(p7.load_choices()))
    assert r["review"] == "Not yet Fable-reviewed (ruling PD-22)"


def test_inputs_are_r0s_p4s_and_p5s(r, ctx):
    d, p5 = ctx["d"], ctx["p5"]
    assert r["fos"] == pytest.approx(1.5, rel=1e-12) and r["r0"]["components_lb"]["wing"] == pytest.approx(429.4, abs=0.01)
    assert r["p4_inputs"]["trim_check"]["largest_relative_difference"] <= 1e-12       # P4's trim legs reproduce
    names = {c["name"]: c for c in r["cases"]}
    to, zf = names["+3.8 takeoff weight"], names["+3.8 zero-fuel weight"]
    assert to["W_lb"] == d["W0_lb"] and zf["W_lb"] == pytest.approx(d["W0_lb"] - d["fuel_lb"], rel=1e-12)
    assert to["fuel_lb"] == d["fuel_lb"] and zf["fuel_lb"] == 0.0
    for c, wt in ((to, "takeoff"), (zf, "zero_fuel")):
        assert c["speeds_kt"]["positive_corner"] == pytest.approx(p5["row3"]["manoeuvre"][wt]["positive_corner_kt"], rel=1e-9)
    for c in ("-1.8 takeoff weight", "-1.8 zero-fuel weight"):
        wt = names[c]["weight"]
        assert names[c]["speeds_kt"]["negative_corner"] == pytest.approx(p5["row3"]["manoeuvre"][wt]["negative_corner_kt"], rel=1e-9)
    assert names["worst gust up (P5 row 3)"]["n"] == pytest.approx(3.504, abs=5e-4)
    assert names["worst gust down (P5 row 3)"]["n"] == pytest.approx(-1.504, abs=5e-4)
    assert {round(c["n"], 3) for c in r["cases"] if c["kind"] == "sensitivity"} == {5.227, -3.227, 4.841, -2.841}
    for c in r["cases"]:
        for s in c["by_speed"].values():
            assert s["L_wing_lb"] + s["L_tail_lb"] == pytest.approx(c["n"] * c["W_lb"], rel=1e-12)
        assert abs(c["by_speed"][c["speed"]]["root_M_ult_lbft"]) == max(abs(s["root_M_ult_lbft"]) for s in c["by_speed"].values())


def test_row1_verdict_and_numbers(r):
    a = r["row1"]
    assert a["airload_tolerance"] == 1e-9 and a["closed_form_tolerance"] == 1e-6
    ok = (a["airload_largest_error"] <= 1e-9 and max(a["uniform"]["V_error"], a["uniform"]["M_error"]) <= 1e-6
          and max(a["elliptic_check_grid"]["V_error"], a["elliptic_check_grid"]["M_error"]) <= 1e-6)
    assert a["verdict"] == ("pass" if ok else "fail")
    assert max(abs(s["airload_error"]) for c in r["cases"] for s in c["by_speed"].values()) <= a["airload_largest_error"]


def test_row2_verdict_and_numbers(r, ctx):
    a = r["row2"]
    lat = a["lattice"][a["lattice_level"]]["ybar_ft"]
    assert a["deviation"] == pytest.approx(lat / a["schrenk_ybar_ft_stations"] - 1.0, rel=1e-12) and a["tolerance"] == 0.05
    assert a["verdict"] == ("pass" if abs(a["deviation"]) <= 0.05 else "fail")
    assert a["used"] == ("lattice" if a["verdict"] == "fail" and lat > a["schrenk_ybar_ft_stations"] else "schrenk")
    assert a == json.loads(json.dumps(p7._plain(p7.row2(ctx))))


def test_rows3_to_5_follow_from_the_sized_spar(r, ctx, base):
    s = r["spar"]
    assert np.allclose(s["M_env_ult_lbft"], base["M_env"], rtol=1e-12) and np.allclose(s["cap_area_in2"], base["sized"]["cap_area_in2"], rtol=1e-12)
    assert r["row3"] == json.loads(json.dumps(p7._plain(p7.row3(base))))
    assert r["row4"] == json.loads(json.dumps(p7._plain(p7.row4(base))))
    assert r["row5"] == json.loads(json.dumps(p7._plain(p7.row5(ctx, base))))
    ruled = [c for c in r["cases"] if c["kind"] == "ruled"]
    least = min(min(c["min_cap_margin"], c["min_web_margin"]) for c in ruled)
    assert r["row3"]["least_margin"] == pytest.approx(least, abs=1e-15)
    assert r["row3"]["verdict"] == ("pass" if r["row4"]["fits"] and least >= -1e-9 else "fail")
    assert r["row4"]["verdict"] == ("pass" if all(v > 0 for v in s["fit_discriminant_in2"]) else "fail")
    # the envelope is the largest magnitude over the ruled cases at every station
    for j in range(len(s["y_ft"])):
        assert s["M_env_ult_lbft"][j] == max(abs(c["M_ult_lbft"][j]) for c in ruled)
        assert s["V_env_ult_lb"][j] == max(abs(c["V_ult_lb"][j]) for c in ruled)
    a5 = r["row5"]
    assert a5["share"] == pytest.approx(a5["spar_lb"] / 429.40330251299406, rel=1e-9)
    assert a5["heavier_than_wing"] is (a5["spar_lb"] > a5["r0_wing_lb"])
    assert a5["spar_lb"] == pytest.approx(a5["caps_lb"] + a5["web_lb"], rel=1e-12)


def test_sensitivity_band_ends_and_r1(r, ctx, base):
    assert r["sensitivity"] == json.loads(json.dumps(p7._plain(p7.sensitivity(ctx, base))))
    assert r["band_ends"] == json.loads(json.dumps(p7._plain(p7.band_ends(ctx, base))))
    r1 = r["r1"]
    assert r1["empty_weight_change_lb"] == pytest.approx(27.15, abs=0.01) and r1["layout"].startswith("Bs")
    assert r1["root_moment_change"] == pytest.approx(r1["root_M_env_ult_lbft"] / r1["root_M_env_ult_lbft_r0"] - 1.0, rel=1e-12)
    assert r1["spar_lb_r0"] == r["row5"]["spar_lb"]


def test_acceptance_list_matches_rows(r):
    assert [x["row"] for x in r["acceptance"]] == [1, 2, 3, 4, 5]
    for x in r["acceptance"]:
        assert x["verdict"] == r[f"row{x['row']}"]["verdict"]

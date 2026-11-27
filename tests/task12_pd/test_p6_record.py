"""The committed record of preliminary design P6 (runs/task12/pd/2026-11-27/p6): it says what the spec asks of a
record (commit, clean tree with the file list, versions, log), it carries its sources, and every verdict follows from
the numbers stored beside it. The verdicts are recomputed here; these tests do not require a row to pass, only that
the record tells the truth, and that a failed validation row 5 keeps the aircraft numbers out of r1.
"""
import json

import pytest
import yaml

from prelim import bem
from prelim import p6_propeller as p6

OUT = p6.REPO / "runs/task12/pd/2026-11-27/p6"


@pytest.fixture(scope="module")
def p():
    return json.loads((OUT / "p6.json").read_text())


@pytest.fixture(scope="module")
def val(p):
    return {a["row"]: a for a in p["acceptance"] if a["group"] == "validation"}


@pytest.fixture(scope="module")
def air(p):
    return {a["row"]: a for a in p["acceptance"] if a["group"] == "aircraft"}


def test_record_has_its_files_and_says_where_it_comes_from(p):
    for name in ("p6.json", "run.log"):
        assert (OUT / name).read_text().strip(), name
    i = p["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-27/p6"
    assert i["tree_unchanged_during_run"] is True and p["tree_at_end"]["git_dirty"] is False
    assert i["seed"] is None and i["python"] and i["numpy"] and i["scipy"] and i["command"].startswith("python -m prelim.p6_propeller")
    for key, path in i["files"].items():                                             # the inputs are the committed files
        assert p6.sha256(p6.REPO / path) == i["sha256"][key], path
    assert p["baseline"] == "runs/task12/pd/2026-11-27/p0/r0" and len(p["acceptance"]) == 9
    assert p["source"] == json.loads(json.dumps(yaml.safe_load(p6.SOURCE.read_text())))
    assert p["blade_ledger"] == p6.blade_ledger() and p["targets"] == pytest.approx(p6.record_targets())
    for r in p["source"]["reports"].values():
        if isinstance(r, dict):
            assert r["opened_in_this_session"] is True and r["pdf_committed"] is False and len(r["pdf_sha256"]) == 64
    assert not list(p6.REPO.glob("data/task12/**/*.pdf")) and not list(OUT.glob("*.pdf"))


def test_validation_rows_1_to_4_are_what_the_code_gives_now(val):
    for row, fn in ((1, p6.validation_row_1), (2, p6.validation_row_2), (3, p6.validation_row_3), (4, p6.validation_row_4)):
        now = json.loads(json.dumps(fn()))
        assert val[row]["verdict"] == now["verdict"], row
    assert val[1]["largest_relative_difference"] <= 1e-12 and val[1]["verdict"] == "pass"
    assert val[2]["verdict"] == "pass" and val[4]["verdict"] == "pass"
    assert val[3]["verdict"] == ("pass" if all(r["J_ok"] and r["CP_ok"] for r in val[3]["rows"]) else "fail")


def test_row_5_points_are_the_committed_readings_and_the_verdict_follows(p, val):
    pts = {int(k): v for k, v in p["row5_points"].items()}
    assert sorted(pts) == list(p6.ROW5_ANGLES)
    for angle, rows in pts.items():
        want = p6.measured_efficiency(angle)
        assert [(r["J"], r["eta"], r["uncertainty"], r["judged"]) for r in rows] == pytest.approx(
            [(w["J"], w["eta"], w["uncertainty"], w["judged"]) for w in want])
        for r in rows:
            assert r["eta"] > p6.ETA_RANGE_MIN
            assert r["difference"] == (None if r["computed"] is None else pytest.approx(r["computed"] - r["eta"]))
    again = p6.row5_verdict(pts)
    for key in ("verdict", "n_judged", "n_inside", "n_not_computed"):
        assert val[5][key] == again[key], key
    assert val[5]["largest_difference"] == pytest.approx(again["largest_difference"]) and val[5]["tolerance"] == 0.03
    assert p["used_in_r1"] is (val[5]["verdict"] == "pass")


def test_row_5_is_recomputed_from_the_committed_data_at_three_points(p):
    sections = p6.load_sections(p["blade_ledger"]["prop_section_span_factor"])
    for angle, index in ((15, 0), (15, 6), (25, 5)):
        rec = p["row5_points"][str(angle)][index]
        assert p6.run_5868_9(angle, rec["J"], sections)["eta"] == pytest.approx(rec["computed"], rel=1e-9)


def test_aircraft_rows_follow_from_the_points(p, air):
    pts, T = p["aircraft"]["points"], p["targets"]
    for e in air[1]["points"]:
        assert e["eta"] == pts[e["point"]]["eta"] and e["eta_record"] == T["eta"][e["point"]]
        assert e["verdict"] == p6.verdict_eta(e["eta"], e["eta_record"])
    for f in air[2]["points"]:
        pt = pts[f["point"]]
        if pt.get("f") is None:
            assert f["verdict"] == "not computed" and "error" in pt
        else:
            assert f["f"] == pytest.approx(pt["eta"] / pt["eta_ideal"]) and f["verdict"] == p6.verdict_f(f["f"])
            o = p["operating_points"].get(f["point"])
            if o:                                                 # the ideal efficiency is (L.8) at the computed thrust
                assert pt["eta_ideal"] == pytest.approx(bem.ideal_efficiency_of_disk(pt["thrust_lb"], o["rho"], o["V_fps"], o["D_ft"]))
                assert pt["power_hp"] == pytest.approx(o["shaft_hp"], rel=1e-6)
    to = pts["takeoff_0707_VTO"]
    assert air[3]["minimum_lb"] == T["takeoff_thrust_min_lb"]
    if to.get("thrust_lb") is None:
        assert air[3]["verdict"] == "not computed" and to["pitch_sweep"] and air[3]["sweep_best"] == p6.best_of_sweep(to["pitch_sweep"])
    else:
        assert air[3]["verdict"] == p6.verdict_takeoff(to["thrust_lb"], T["takeoff_thrust_min_lb"])
    assert air[4]["verdict"] == "reported, no verdict"
    for k in ("climb_sea_level", "cruise_out", "loiter", "cruise_back"):
        assert 0.5 < air[4]["tip_mach"][k]["helical"] < 0.9


def test_failed_validation_keeps_the_aircraft_numbers_out_of_r1(p, air):
    for a in air.values():
        assert (a["note"] is None) == p["used_in_r1"]
        if not p["used_in_r1"]:
            assert "not used in r1" in a["note"]


def test_aircraft_blade_and_sensitivity_cases(p):
    b = p["aircraft"]["blade"]
    assert b["activity_factor"] == pytest.approx(p["blade_ledger"]["prop_activity_factor"])
    assert [c["case"] for c in p["sensitivity"]] == [c[0] for c in p6.sensitivity_cases()]
    base = p["sensitivity"][0]["points"]
    for k in ("climb_sea_level", "cruise_out", "loiter", "cruise_back"):
        assert base[k]["eta"] == pytest.approx(p["aircraft"]["points"][k]["eta"], rel=1e-9)
    for k, band in p["proposed_f_bands"].items():
        fs = [c["points"][k]["f"] for c in p["sensitivity"] if c["points"][k].get("f") is not None]
        assert band["low"] <= min(fs) and max(fs) <= band["high"] and band["n_cases"] == len(fs)


def test_r0_is_untouched(p):
    assert p["inputs"]["sha256"]["r0_design"] == p6.sha256(p6.R0 / "design_pusher.json")
    assert p["inputs"]["sha256"]["r0_ledger"] == p6.sha256(p6.R0 / "ledger.yaml")

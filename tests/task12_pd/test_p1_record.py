"""The committed record of preliminary design P1 (runs/task12/pd/2026-11-27/p1): it says what the spec asks of a
record (commit, clean tree with the file list, seed, versions, log), the numbers it quotes from r0 are r0's, and
every acceptance verdict follows from the numbers stored beside it. The verdicts are recomputed here from the
files; these tests do not require a row to pass, only that the record tells the truth about it.
"""
import json

import pytest
import yaml

from conceptual import uav
from prelim import p1_package as p1

OUT = p1.REPO / "runs/task12/pd/2026-11-27/p1"
R0 = json.loads((p1.R0 / "design_pusher.json").read_text())


@pytest.fixture(scope="module")
def p():
    return json.loads((OUT / "p1.json").read_text())


@pytest.fixture(scope="module")
def acc(p):
    return {a["row"]: a for a in p["acceptance"]}


def test_record_has_its_files_and_says_where_it_comes_from(p):
    for name in ("p1.json", "run.log", "pytest.log", "design_tractor.json", "design_pusher_rubber.json"):
        assert (OUT / name).read_text().strip(), name
    i = p["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-27/p1"
    assert i["tree_unchanged_during_run"] is True and p["tree_at_end"]["git_dirty"] is False
    assert "seed" in i and i["seed"] is None and "20261122" in i["seed_note"]      # no random numbers in P1
    assert i["python"] and i["numpy"] and i["matplotlib"] and i["command"].startswith("python -m prelim.p1_package")
    for key, path in i["files"].items():                                             # the inputs are the committed files
        assert p1.sha256(p1.REPO / path) == i["sha256"][key], path
    assert "stopped" not in p and len(p["acceptance"]) == 12
    assert p["baseline"] == "runs/task12/pd/2026-11-27/p0/r0"


def test_row_1_the_rebuild_is_r0_and_quoted_numbers_are_the_record(p, acc):
    rep = p["reproduction"]
    assert (acc[1]["verdict"] == "pass") == (not rep["different"] and not rep["added"] and not rep["removed"])
    assert rep["n_compared"] > 300 and rep["max_relative_difference"] <= p1.TOL_REPRODUCE
    # sampled fields of the package against the record
    w = p["weight_statement"]
    assert (w["We_lb"], w["W0_lb"], w["fuel_lb"]) == (R0["We_lb"], R0["W0_lb"], R0["fuel_lb"])
    for row in w["rows"]:
        assert row["weight_lb"] == R0["components_lb"][row["item"]]
    assert p["empty_weight"]["table_3_1"]["steps"][-1]["fraction"] == R0["empty_fraction_comparison"]["build_up"]
    assert p["empty_weight"]["table_15_2"]["record_fraction"] == R0["empty_fraction_comparison"]["table_15_2_approximate"]
    assert p["payload_bay"]["payload_lb"] == R0["payload_lb"]
    assert p["payload_bay"]["fuselage_length_ft"] == R0["fuselage"]["length"]
    assert p["concepts"]["scoring"]["table"][0]["pusher"] == R0["W0_lb"]
    assert p["trades"]["payload_for_fuel"][5]["fuel_lb"] == R0["fuel_lb"]
    carpet = [r for r in p["carpet"]["rows"] if (r["W_S"], r["A"]) == (R0["W_S"], R0["A"])]
    assert carpet[0]["W0_lb"] == R0["W0_lb"]
    assert p["sized_loiter_h"] == uav.load_ledger(p1.R0 / "ledger.yaml")[0]["loiter_h"]
    files = dict(p1.evidence_files(), p1=p)
    for group in ("risks", "out_of_calibration"):                                    # every evidence path resolves
        for entry in p[group]["entries"]:
            for ev in entry.get("evidence", []):
                assert isinstance(p1.lookup(files[ev["file"]], ev["path"]), (int, float, bool)), ev


def test_row_2_compliance_matrix(p, acc):
    rows = p["compliance"]["rows"]
    assert p1.blank_cells(rows) == p["compliance"]["blank_cells"]
    named = {r for row in rows for r in row["requirement_id"].split("/")}
    assert sorted({f"R{i}" for i in range(1, 20)} - named) == p["compliance"]["requirements_missing"]
    assert (acc[2]["verdict"] == "pass") == (not p1.blank_cells(rows) and {f"R{i}" for i in range(1, 20)} <= named)
    assert acc[2]["n_failed"] == sum(r["verdict"] == "fail" for r in rows)
    # values of the matrix against r0
    by = {r["requirement"]: r for r in rows}
    assert by["R7 take-off over 50 ft"]["value"] == pytest.approx(R0["performance"]["takeoff_ft"], rel=1e-9)
    assert by["R13 static margin, full fuel"]["value"] == pytest.approx(R0["layout"]["sm_full"], rel=1e-9)
    ceiling = next(r for r in rows if r["requirement"].startswith("R12 service ceiling"))
    assert ceiling["value"] == pytest.approx(R0["performance"]["service_ceiling_ft"], rel=1e-9)
    ig = json.loads((p1.R0 / "info_gap.json").read_text())
    horizon = next(r for r in rows if "guarantee horizon" in r["requirement"])
    assert horizon["value"] == ig["h_hat"]["R5_guarantee"]["h_hat"]


def test_row_3_and_4_weight_statement_and_vn(p, acc):
    assert p["weight_statement"] == json.loads(json.dumps(p1.weight_statement(R0)))
    assert (acc[3]["verdict"] == "pass") == (abs(p["weight_statement"]["difference_lb"]) <= p1.TOL_WEIGHT_LB)
    assert p["vn"]["points"] == p1.vn_points(R0)
    assert p1.vn_difference(p["vn"]["points"], R0) == p["vn"]["max_difference"]
    assert (acc[4]["verdict"] == "pass") == (p["vn"]["max_difference"] <= p1.TOL_VN)


def test_row_5_6_and_11_the_lists_are_the_judgement_file(p, acc):
    judge = yaml.safe_load(p1.JUDGEMENTS.read_text())
    assert p["out_of_calibration"]["entries"] == judge["out_of_calibration"]
    assert p["risks"]["entries"] == judge["risks"]
    assert p["out_of_calibration"]["problems"] == p1.check_out_of_calibration(judge["out_of_calibration"])
    assert p["risks"]["problems"] == p1.check_risks(judge["risks"])
    assert (acc[5]["verdict"] == "pass") == (bool(judge["out_of_calibration"]) and not p["out_of_calibration"]["problems"])
    assert (acc[6]["verdict"] == "pass") == (bool(judge["risks"]) and not p["risks"]["problems"])
    _, entries = uav.load_ledger(p1.R0 / "ledger.yaml")
    audit = p["ledger"]["audit"]
    assert p["ledger"]["problems"] == p1.check_band_audit(judge["band_audit"], entries)
    assert (acc[11]["verdict"] == "pass") == (not p["ledger"]["problems"])
    assert audit["n_entries"] == 111 and audit["n_unbanded"] == 58 and audit["n_banded"] == 53
    assert sum(audit["by_class"].values()) == 58
    for row in audit["rows"]:
        assert row["class"] == judge["band_audit"][row["name"]]["class"] and row["value"] == entries[row["name"]]["value"]
        if row["class"] == "needs a band":
            assert row["points"], row["name"]                       # what it moves was run
            assert row["proposed_band"] == judge["band_audit"][row["name"]].get("proposed_band")
    # no proposed band was applied: the ledger the run read has no band on any audited entry
    assert all("band" not in entries[name] for name in judge["band_audit"])


def test_row_7_trades(p, acc):
    nominal = p["trades"]["resized"]["nominal"]
    ok = (abs(nominal["W0_lb"] / R0["W0_lb"] - 1.0) <= p1.TOL_REPRODUCE
          and abs(p["nominal_as_built"]["hours_on_station"] - p["sized_loiter_h"]) <= 2e-3)
    assert (acc[7]["verdict"] == "pass") == ok
    t = p["trades"]
    # the three trades the spec names are there, as built and re-sized
    assert [r["payload_lb"] for r in t["payload_for_fuel"]] == [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0]
    assert [r["mission_altitude_ft"] for r in t["altitude_as_built"]] == [15000.0, 17500.0, 20000.0, 22500.0, 25000.0]
    lo, hi = uav.load_ledger(p1.R0 / "ledger.yaml")[1]["composite_factor"]["band"]
    assert (t["composite_as_built"][0]["composite_factor"], t["composite_as_built"][-1]["composite_factor"]) == (lo, hi)
    assert {"loiter_h", "payload_lb", "mission_altitude_ft", "composite_factor"} <= set(t["resized"])
    # the trade point that is r0 gives r0's hours in every as-built table
    for key, x, at in (("payload_for_fuel", "payload_lb", 500.0), ("altitude_as_built", "mission_altitude_ft", 20000.0),
                       ("composite_as_built", "composite_factor", 0.95)):
        row = next(r for r in t[key] if r[x] == at)
        assert row["hours_on_station"] == pytest.approx(p["sized_loiter_h"], abs=2e-3)
    # more payload for less fuel gives fewer hours, and a heavier structure too
    hours = [r["hours_on_station"] for r in t["payload_for_fuel"]]
    assert hours == sorted(hours, reverse=True)
    hours = [r["hours_on_station"] for r in t["composite_as_built"]]
    assert hours == sorted(hours, reverse=True)


def test_row_8_decomposition_and_climb(p, acc):
    dec, cl = p["decomposition"], p["climb_check"]["states"]
    assert set(dec) == set(cl) == {"nominal", "corner_h1", "corner_target"}
    cell = json.loads((p1.R0 / "cell_result.json").read_text())
    assert dec["corner_target"]["theta"] == cell["worst_at_target"]["endurance"]["moved"]
    assert dec["corner_h1"]["theta"] == cell["modes"]["endurance"]["worst_at_h1"]["moved"]
    # the nominal case with the disk is r0's mission: fuel and every segment
    nom = dec["nominal"]["disk"]
    assert nom["fuel_with_reserve_lb"] == pytest.approx(R0["fuel_lb"], rel=1e-6)
    for m in R0["mission"]:
        if m["segment"] in nom["segment_fuel_lb"]:
            assert nom["segment_fuel_lb"][m["segment"]] == pytest.approx(m["burned_lb"], rel=1e-4)
    assert cl["nominal"]["two_point_fuel_lb"] == pytest.approx(next(m["burned_lb"] for m in R0["mission"] if m["segment"] == "climb"), rel=1e-4)
    # and its integrated climb is the one P0 recorded
    p0 = json.loads(p1.P0_JSON.read_text())["climb"]
    assert cl["nominal"]["integrated_fuel_lb"] == pytest.approx(p0["integrated"]["fuel_lb"], rel=1e-4)
    # at the corners the hours on station are the record's
    assert dec["corner_target"]["hours_on_station"]["disk"] == pytest.approx(cell["worst_at_target"]["endurance"]["hours"], abs=2e-3)
    for s in cl.values():
        m = s["against_stall_at_altitude"]["end_of_climb_weight"]
        assert m["above_stall"] == (m["over_stall"] >= 1.0) and m["above_floor"] == (m["over_stall"] >= m["floor"])
        assert s["finding_for_r1"] == (s["mission_fuel_share"] > p1.TOL_CLIMB_FUEL)
        assert s["hours_estimate"] == pytest.approx(s["hours_on_station"] - s["fuel_difference_lb"] / s["loiter_fuel_flow_lb_h"])
        assert s["top_of_climb_above_service_ceiling"] == (s["rate_at_top_fpm"] < s["ceiling_rate_fpm"])
    finding = [k for k, s in cl.items() if s["finding_for_r1"]]
    slow = [k for k, s in cl.items() if not s["against_stall_at_altitude"]["end_of_climb_weight"]["above_floor"]]
    assert acc[8]["finding_states"] == finding and acc[8]["below_floor"] == slow
    assert acc[8]["verdict"] == ("finding for r1" if finding else "pass with a note" if slow else "pass")


def test_row_9_concept_scoring(p, acc):
    sc, des = p["concepts"]["scoring"], p["concepts"]["designs"]
    tractor = json.loads((OUT / "design_tractor.json").read_text())
    rubber = json.loads((OUT / "design_pusher_rubber.json").read_text())
    assert (tractor["concept"], tractor["W_S"], tractor["A"], tractor["engine"]["fixed"]) == ("tractor", 13.0, 8.0, R0["engine"]["fixed"])
    assert (rubber["concept"], rubber["W_S"], rubber["A"]) == ("pusher", 13.0, 8.0) and "fixed" not in rubber["engine"]
    assert des["tractor"]["W0_lb"] == tractor["W0_lb"] and des["pusher_rubber"]["bhp"] == rubber["bhp_sl"]
    assert sc["table"][0]["tractor"] == tractor["W0_lb"]
    # the score recomputed from the table
    score = {c: sum(r["weight"] * (5.0 * min(r["tractor"], r["pusher"]) / r[c] if i == 0 else r[c]) for i, r in enumerate(sc["table"]))
             for c in ("tractor", "pusher")}
    assert score == pytest.approx(sc["score"])
    assert sc["reversed"] == (max(score, key=score.get) != "pusher")
    assert acc[9]["verdict"].startswith("REVERSED") == sc["reversed"]
    assert sc["pusher_over_tractor_W0"] == pytest.approx(R0["W0_lb"] / tractor["W0_lb"])
    assert (sc["pusher_over_tractor_W0"] < sc["break_even_ratio"]) == (not sc["reversed"])


def test_row_10_and_12_empty_weight_and_payload_bay(p, acc):
    e = p["empty_weight"]
    assert e == json.loads(json.dumps(p1.empty_weight_explanation(R0, e["s_exposed_ft2"], uav.load_ledger(p1.R0 / "ledger.yaml")[0])))
    perf = json.loads(p1.PERF.read_text())
    assert e["s_exposed_ft2"] == pytest.approx(perf["anderson_w0"]["buildup_areas_ft2"][0], rel=1e-9)   # the Gate B record's
    bay = p["payload_bay"]
    assert bay == json.loads(json.dumps(p1.payload_bay(R0, uav.load_ledger(p1.R0 / "ledger.yaml")[0])))
    assert (acc[12]["verdict"] == "pass") == (bay["payload_volume_ft3"] <= bay["free_volume_ft3"])


def test_recorded_test_run(p):
    t = p["tests"]
    assert t["summary_line"] in (OUT / "pytest.log").read_text()
    assert (t["exit_code"] == 0) == ("failed" not in t["counts"] and "error" not in t["counts"] and "errors" not in t["counts"])
    assert t["counts"].get("passed", 0) > 400

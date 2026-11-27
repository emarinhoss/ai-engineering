"""The committed record of preliminary design P3 (runs/task12/pd/2026-11-27/p3): it says what the spec asks of a
record (commit, clean tree with the file list, versions, log), it carries its sources, and every verdict follows from
the numbers stored beside it. These tests do not require a gate to pass, only that the record tells the truth and
that the geometry rows are what the code gives now.
"""
import json

import pytest
import yaml

from geometry3d import aircraft as ac
from geometry3d import gates, mesh
from prelim import p3_loft as p3

OUT = p3.REPO / "runs/task12/pd/2026-11-27/p3"


@pytest.fixture(scope="module")
def p():
    return json.loads((OUT / "p3.json").read_text())


@pytest.fixture(scope="module")
def now():
    d, L, A = p3.inputs()
    m = ac.build(d, L, A)
    return d, L, A, m, ac.meshes(m)


def test_record_has_its_files_and_says_where_it_comes_from(p):
    for name in ("p3.json", "run.log", "loft.stl"):
        assert (OUT / name).stat().st_size > 0, name
    i = p["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-27/p3"
    assert i["tree_unchanged_during_run"] is True and p["tree_at_end"]["git_dirty"] is False
    assert i["seed"] is None and i["python"] and i["numpy"] and i["scipy"] and i["command"].startswith("python -m prelim.p3_loft")
    for key, path in i["files"].items():
        assert p3.sha256(p3.REPO / path) == i["sha256"][key], path
    assert p["baseline"] == "runs/task12/pd/2026-11-27/p0/r0"
    assert p["arrangement"] == json.loads(json.dumps(yaml.safe_load(p3.ARRANGEMENT.read_text())))
    assert p["tail_source"] == json.loads(json.dumps(yaml.safe_load(p3.TAIL_SOURCE.read_text())))
    assert p["stl"]["sha256"] == p3.sha256(OUT / "loft.stl") and p["stl"]["bytes"] == (OUT / "loft.stl").stat().st_size
    assert not list(OUT.rglob("*.pdf"))
    assert [a["row"] for a in p["acceptance"]] == list(range(1, 11))
    for a in p["acceptance"]:
        assert a["verdict"] == p["gates"][str(a["row"])]["verdict"]
        assert a["verdict"] in ("pass", "fail", "reported", "not run")


def test_r0_was_not_changed(p):
    d = json.loads((p3.R0 / "design_pusher.json").read_text())
    assert p["r0"]["W0_lb"] == d["W0_lb"] and p["r0"]["stations"] == d["stations"] and p["r0"]["wing"] == d["wing"]


def test_exported_stl_is_the_loft_the_code_builds_now(p, now):
    parts = now[4]
    back = mesh.read_stl(OUT / "loft.stl")
    assert set(back) == set(parts)
    for name, (V, T) in parts.items():
        assert mesh.area(*back[name]) == pytest.approx(mesh.area(V, T), rel=1e-9)
        assert mesh.volume(*back[name]) == pytest.approx(mesh.volume(V, T), rel=1e-9)
    assert p["gates"]["7"]["largest_relative_difference"] <= gates.TOL_ROUND_TRIP and p["gates"]["7"]["verdict"] == "pass"


def test_gates_1_to_7_and_9_are_what_the_code_gives_now(p, now, tmp_path):
    d, L, A, m, parts = now
    g = p["gates"]
    assert g["1"]["verdict"] == gates.gate1_watertight(parts)["verdict"]
    assert all(r["edges_repeated"] == 0 and r["edges_unmatched"] == 0 and r["volume_ft3"] > 0 for r in g["1"]["parts"].values()) == (g["1"]["verdict"] == "pass")
    g2 = gates.gate2_targets(m, d)
    assert g["2"]["verdict"] == g2["verdict"] and g["2"]["mac_ft"] == pytest.approx(g2["mac_ft"], rel=1e-12)
    g3 = gates.gate3_wetted(m, parts, d, L)
    for k, r in g3["components"].items():
        rec = g["3"]["components"][k]
        assert rec["loft_wetted_ft2"] == pytest.approx(r["loft_wetted_ft2"], rel=1e-9)
        assert rec["stage1_ft2"] == pytest.approx(r["stage1_ft2"], rel=1e-12)
        assert rec["verdict"] == ("pass" if abs(rec["loft_wetted_ft2"] / rec["stage1_ft2"] - 1.0) <= 0.05 else "fail")
    assert g["3"]["failing"] == [k for k, r in g["3"]["components"].items() if r["verdict"] == "fail"]
    assert g["3"]["verdict"] == ("fail" if g["3"]["failing"] else "pass")
    g4 = gates.gate4_volumes(m, parts, d, L, A)
    assert g["4"]["failing"] == g4["failing"] and g["4"]["verdict"] == g4["verdict"] == ("fail" if g4["failing"] else "pass")
    assert g["4"]["payload_bay"]["bay_ft3"] == pytest.approx(g4["payload_bay"]["bay_ft3"])
    assert g["4"]["tank"]["usable_ft3"] == pytest.approx(g4["tank"]["usable_ft3"], rel=1e-9)
    for name, b in g["4"]["boxes"].items():
        if "verdict" in b:
            assert b["verdict"] == ("pass" if b["clearance_in"] >= g["4"]["clearance_required_in"] - 1e-6 else "fail"), name
            assert b["clearance_in"] == pytest.approx(g4["boxes"][name]["clearance_in"], abs=0.02)
    g5 = gates.gate5_smoothness(m)
    assert g["5"]["verdict"] == g5["verdict"] and g["5"]["aft_body_angle_deg"] == pytest.approx(g5["aft_body_angle_deg"])
    assert (max(g["5"][k]["largest_slope_change_per_ft"] for k in ("perimeter", "area")) <= g["5"]["bound"]) == (g["5"]["verdict"] == "pass")
    g6 = gates.gate6_ground(m, parts, d, L)
    assert g["6"]["verdict"] == g6["verdict"] and g["6"]["propeller_clearance_in"] == pytest.approx(g6["propeller_clearance_in"], rel=1e-9)
    g9 = gates.row9_propeller_disc(m, parts)
    assert g["9"]["failing"] == pytest.approx(g9["failing"]) and g["9"]["verdict"] == ("fail" if g9["failing"] else "pass")


def test_gate_8_verdict_follows_from_its_numbers(p):
    g8 = p["gates"]["8"]
    if g8["verdict"] == "not run":
        assert g8["reason"] and not (OUT / "openvsp" / "openvsp_check.json").exists()
        return
    vsp = json.loads((OUT / "openvsp" / "openvsp_check.json").read_text())
    assert vsp["openvsp"].startswith("OpenVSP 3.57") and g8["openvsp"] == vsp["openvsp"]
    again = gates.gate8_openvsp(p["gates"]["3"]["components"], vsp)
    assert again["failing"] == g8["failing"] and again["verdict"] == g8["verdict"]
    for k, r in g8["components"].items():
        assert r["verdict"] == ("pass" if abs(r["loft_wetted_ft2"] / r["openvsp_default_mesh_wetted_ft2"] - 1.0) <= 0.02 else "fail")
        assert abs(r["whole_rel_fine"]) < 0.02                     # the two tools draw the same surfaces


def test_build_up_was_re_run_because_gate_3_failed(p):
    b = p["buildup"]
    if p["gates"]["3"]["verdict"] == "pass":
        assert b is None
        return
    d = json.loads((p3.R0 / "design_pusher.json").read_text())
    assert b["as_recorded"]["CD0_mission_altitude"] == pytest.approx(d["CD0"]["mission_altitude"], rel=1e-9)
    assert b["areas_loft_ft2"] == {k: v["loft_wetted_ft2"] for k, v in p["gates"]["3"]["components"].items()}
    assert b["delta_hours"] == pytest.approx(b["with_loft_areas"]["hours_on_station"] - b["as_recorded"]["hours_on_station"])
    assert b["delta_CD0_relative"] == pytest.approx(b["with_loft_areas"]["CD0_mission_altitude"] / b["as_recorded"]["CD0_mission_altitude"] - 1.0)


def test_moved_masses_are_reported_for_p4(p):
    mv = p["moved_masses"]
    d = json.loads((p3.R0 / "design_pusher.json").read_text())
    items = {r["item"]: r for r in mv["moved"]}
    assert set(items) == {"payload", "avionics"}
    assert items["payload"]["weight_lb"] == d["payload_lb"] and items["payload"]["station_r0_ft"] == d["stations"]["payload"]["x"]
    assert items["avionics"]["weight_lb"] == d["components_lb"]["avionics"] and items["avionics"]["station_r0_ft"] == d["stations"]["avionics"]["x"]
    assert items["payload"]["station_p3_ft"] == p["gates"]["4"]["payload_bay"]["centroid_x_ft"]
    total = sum(r["weight_lb"] * (r["station_p3_ft"] - r["station_r0_ft"]) for r in mv["moved"])
    assert mv["moment_change_lb_ft"] == pytest.approx(total)
    assert mv["cg_shift_takeoff_weight_ft"] == pytest.approx(total / d["W0_lb"])
    assert mv["cg_shift_zero_fuel_weight_ft"] == pytest.approx(total / (d["W0_lb"] - d["fuel_lb"]))
    assert {q["item"] for q in mv["gear_up_and_down"]} == {"nose gear", "main gear"}


def test_tail_section_rows_are_the_committed_table(p):
    src = yaml.safe_load(p3.TAIL_SOURCE.read_text())["naca0012"]
    want = sorted((dict(zip(src["columns"], r)) for r in src["rows"]), key=lambda r: r["reynolds_millions"])
    assert p["tail_section"]["rows"] == want
    for c in p["tail_section"]["conditions"].values():
        for tail in ("horizontal_tail", "vertical_tail"):
            assert c[tail]["cl_max_negative"] == -c[tail]["cl_max"] and 0.09 < c[tail]["a0_per_deg"] < 0.101


def test_findings_name_every_failed_row(p):
    text = " ".join(p["findings_for_r1"])
    for k in p["gates"]["3"]["failing"]:
        assert f"Wetted area, {k.replace('_', ' ')}" in text
    if any("main_gear" in f for f in p["gates"]["4"]["failing"]):
        assert "does not fit the sponson" in text
    for k in p["gates"]["9"]["failing"]:
        assert f"The {k.replace('_', ' ')} reaches" in text
    assert "PD-19" in text and "P4 recomputes" in text

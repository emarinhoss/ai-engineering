"""The committed record of preliminary design P4b (runs/task12/pd/2026-11-28/p4b): it says where it comes from
(commit, clean tree, versions, input files, log), every pass or fail follows from the numbers stored beside it, the
choice is what the written rule gives on the stored numbers, and the numbers are what the code gives now. These
tests do not require any layout to pass or to win.
"""
import json

import pytest

from prelim import p4_methods as m
from prelim import p4b_trade as t

OUT = t.REPO / "runs/task12/pd/2026-11-28/p4b"


@pytest.fixture(scope="module")
def p():
    return json.loads((OUT / "p4b.json").read_text())


@pytest.fixture(scope="module")
def ctx():
    return t.context()


def test_record_has_its_files_and_says_where_it_comes_from(p):
    for name in ("p4b.json", "run.log"):
        assert (OUT / name).stat().st_size > 0, name
    i = p["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-28/p4b"
    assert i["tree_unchanged_during_run"] is True and p["tree_at_end"]["git_dirty"] is False
    assert i["seed"] is None and i["python"] and i["numpy"] and i["scipy"] and i["command"].startswith("python -m prelim.p4b_trade")
    for key, path in i["files"].items():
        assert t.p4.sha256(t.REPO / path) == i["sha256"][key], path
    assert p["baseline"] == "runs/task12/pd/2026-11-27/p0/r0"
    assert p["choices"] == json.loads(json.dumps(m.load_yaml(t.CHOICES))) and p["p4_choices"] == json.loads(json.dumps(m.load_yaml(m.CHOICES)))
    assert not list(OUT.rglob("*.pdf"))


def test_r0_and_the_p4_record_were_not_changed(p):
    d = json.loads((t.R0 / "design_pusher.json").read_text())
    assert p["r0"]["W0_lb"] == d["W0_lb"] and p["r0"]["fuselage"] == d["fuselage"] and p["r0"]["tail_arm_ft"] == d["tail_arm_ft"]
    assert p["r0"]["drag_and_hours"]["CD0_mission_altitude"] == pytest.approx(d["CD0"]["mission_altitude"], rel=1e-12)
    p4 = json.loads(t.P4_RECORD.read_text())
    a, rec = p["candidates"]["A"], p4["r1"]["evaluation"]
    for k in ("x_le", "arm", "ht_area", "vt_area", "x_main"):                       # A is PD-20 as P4 recorded it
        assert a["layout"][k] == pytest.approx(rec["layout"][k], rel=1e-9), k
    assert a["measures"]["empty_weight_change_lb"] == pytest.approx(rec["empty_weight_lb"] - p4["as_arranged"]["empty_weight_lb"], rel=1e-9)
    assert a["measures"]["rotation_used_of_limit"] == pytest.approx(rec["rotation"]["used_of_limit"], rel=1e-9)
    assert a["measures"]["payload_off"]["ballast_to_aft_limit_lb"] == pytest.approx(rec["payload_off"]["ballast_at_payload_station_lb"], rel=1e-6)
    assert a["measures"]["propeller_clearance_in"] == pytest.approx(rec["ground"]["propeller_clearance_in"], rel=1e-9)
    assert a["measures"]["extension_ft"] == 0.0


def test_every_verdict_follows_from_the_numbers_beside_it(p):
    L = p["ledger"]
    for name, c in p["candidates"].items():
        v, rows = c["measures"], c["measures"]["rows"]
        assert rows["row1_R13"] == ("pass" if all(m.SM_MIN <= v[k] <= m.SM_MAX for k in ("sm_full", "sm_empty")) else "fail"), name
        assert rows["row3_envelope_payload_on"] == ("pass" if v["payload_on_outside_envelope"] == 0 else "fail")
        assert rows["row4_nose_load_payload_on"] == ("pass" if 0.05 <= v["nose_load_payload_on"][0] and v["nose_load_payload_on"][1] <= 0.20 else "fail")
        assert rows["rotation_tail_lift"] == ("pass" if abs(v["CL_tail_rotation"]) <= L["tail_cl_max_rotation"] else "fail")
        assert rows["trim_tail_lift"] == ("pass" if v["trim_largest"] <= L["tail_cl_max_trim"] else "fail")
        assert rows["overturn"] == ("pass" if v["overturn_max_payload_on_deg"] <= L["overturn_max_deg"] else "fail")
        assert rows["propeller_ground_clearance"] == ("pass" if v["propeller_clearance_in"] >= L["prop_clearance_in"] else "fail")
        assert rows["tails_clear_of_disc"] == ("pass" if max(v["tail_rearmost_behind_propeller_plane_ft"].values()) <= -p["clearance_ft"] + 1e-9 else "fail")
        assert rows["row3_envelope_payload_off"] == ("pass" if v["payload_off_outside_envelope"] == 0 else "fail")
        assert v["eligible"] is all(rows[k] == "pass" for k in t.PAYLOAD_ON_ROWS)
        assert v["empty_weight_change_lb"] == pytest.approx(sum(c["layout"]["weights"].values()) - p["r0"]["empty_weight_lb"], rel=1e-9)
        assert v["empty_weight_change_lb"] == pytest.approx(sum(v["weight_changes_lb"].values()), rel=1e-9)
        assert v["propeller_plane_x_ft"] == pytest.approx(p["r0"]["propeller_plane_x_ft"] + v["extension_ft"], abs=1e-9)
        assert v["shaft_lb"] == pytest.approx(p["shaft_lb_per_ft"]["value"] * v["extension_ft"], abs=1e-9)
        a, b = v["drag_and_hours"]["at_r0_weight"], v["drag_and_hours"]["with_empty_weight_change"]
        assert a["W0_lb"] == p["r0"]["W0_lb"] and b["W0_lb"] == pytest.approx(p["r0"]["W0_lb"] + v["empty_weight_change_lb"], rel=1e-12)
        assert v["hours_for_rule"] == b["hours_on_station"]
        if "evaluation" in c:
            e = c["evaluation"]
            assert len(e["loadings"]) == 264 and e["layout"] == c["layout"]
            outside = sum(not (r["forward_limit_ft"] <= r["x_cg_ft"] <= e["envelope"]["aft_limit_ft"]) for r in e["loadings"] if r["payload_on"])
            assert outside == v["payload_on_outside_envelope"]
            assert c["row9_on_the_loft"]["verdict"] == rows["tails_clear_of_disc"]


def test_the_choice_is_what_the_written_rule_gives(p):
    tie = p["choices"]["selection_rule"]["hours_tie_h"]
    cand = p["candidates"]
    assert p["selection"] == json.loads(json.dumps(t.select({k: v["measures"] for k, v in cand.items()}, tie)))
    assert p["named"] == t.named(cand, p["arm_scan"])
    assert p["chosen_label"] == t.label_of(p["selection"]["chosen"], p["named"], cand)
    assert set(cand) == {"A", "B"} - set(p["unsolved"]) | set(p["arm_scan"])
    assert len(p["arm_scan"]) + sum(k.startswith("scan_") for k in p["unsolved"]) == p["choices"]["candidates"]["arm_scan_points"]
    arms = [cand[k]["measures"]["arm_ft"] for k in p["arm_scan"]]
    assert arms == sorted(arms) and arms[0] == pytest.approx(cand["A"]["measures"]["arm_ft"], rel=1e-9) and arms[-1] == pytest.approx(p["r0"]["tail_arm_ft"], rel=1e-9)
    for name in ("A", "B", p["named"]["Bs"], p["named"]["C"], p["selection"]["chosen"]):
        if name in cand:
            assert "evaluation" in cand[name], name
    assert [s["shaft_lb_per_ft"] for s in p["shaft_band"]] == p["shaft_lb_per_ft"]["band"]
    for s in p["shaft_band"]:
        assert s["selection"] == json.loads(json.dumps(t.select(s["table"], tie)))
        assert s["table"]["A"]["empty_weight_change_lb"] == pytest.approx(cand["A"]["measures"]["empty_weight_change_lb"], rel=1e-9)
    if p["selection"]["chosen"] is None:
        assert "owner" in p["findings_for_r1"][0]
    else:
        assert p["findings_for_r1"][0].startswith("Layout for r1 (PD-21)")
    # nobody flies with the payload off without ballast unless the record says so
    assert p["selection"]["passing_payload_off_without_ballast"] == [k for k in p["selection"]["after_step_1"] if cand[k]["measures"]["payload_off_without_ballast"]]


def test_numbers_of_the_record_are_what_the_code_gives_now(p, ctx):
    lay0 = m.base_layout(ctx["d"], ctx["p3"])
    assert p["r0"]["skin_area_of_the_loft_body_ft2"] == pytest.approx(ctx["skin0"], rel=1e-12)
    assert p["r0"]["drag_and_hours"] == ctx["hours_base"]
    rate = p["shaft_lb_per_ft"]["value"]
    for name, straight in (("B", False), (p["named"]["Bs"], True)):
        if name not in p["candidates"]:
            continue
        rec = p["candidates"][name]
        lay, c1 = t.solve(ctx, lay0, rec["layout"]["arm"], straight, rate)
        for k in ("x_le", "x_main", "ht_area", "vt_area"):
            assert lay[k] == pytest.approx(rec["layout"][k], rel=1e-7), (name, k)
        assert lay["extension"]["length_ft"] == pytest.approx(rec["measures"]["extension_ft"], abs=1e-6)
        assert sum(lay["weights"].values()) - sum(lay0["weights"].values()) == pytest.approx(rec["measures"]["empty_weight_change_lb"], abs=1e-5)
    assert p["shaft_tube_support"] == t.shaft_tube(ctx["d"], ctx["L"], p["choices"]["extension"]["shaft_tube_for_support"])

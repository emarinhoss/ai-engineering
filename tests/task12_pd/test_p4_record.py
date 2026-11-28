"""The committed record of preliminary design P4 (runs/task12/pd/2026-11-27/p4): it says what the spec asks of a
record (commit, clean tree with the file list, versions, log), it carries its sources and choices, and every verdict
follows from the numbers stored beside it. These tests do not require a row to pass, only that the record tells the
truth and that its numbers are what the code gives now.
"""
import json

import pytest

from prelim import p4_balance as p4
from prelim import p4_methods as m

OUT = p4.REPO / "runs/task12/pd/2026-11-27/p4"


@pytest.fixture(scope="module")
def p():
    return json.loads((OUT / "p4.json").read_text())


@pytest.fixture(scope="module")
def ctx():
    return p4.context()


def test_record_has_its_files_and_says_where_it_comes_from(p):
    for name in ("p4.json", "run.log"):
        assert (OUT / name).stat().st_size > 0, name
    i = p["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == "runs/task12/pd/2026-11-27/p4"
    assert i["tree_unchanged_during_run"] is True and p["tree_at_end"]["git_dirty"] is False
    assert i["seed"] is None and i["python"] and i["numpy"] and i["scipy"] and i["command"].startswith("python -m prelim.p4_balance")
    for key, path in i["files"].items():
        assert p4.sha256(p4.REPO / path) == i["sha256"][key], path
    assert p["baseline"] == "runs/task12/pd/2026-11-27/p0/r0"
    assert p["sources"] == json.loads(json.dumps(m.load_yaml(m.SOURCES))) and p["choices"] == json.loads(json.dumps(m.load_yaml(m.CHOICES)))
    assert not list(OUT.rglob("*.pdf"))
    assert [a["row"] for a in p["acceptance"]] == [1, 2, 3, 4, 5]
    assert all(a["verdict"] in ("pass", "fail", "computed", "not needed") for a in p["acceptance"])


def test_r0_was_not_changed(p):
    d = json.loads((p4.R0 / "design_pusher.json").read_text())
    assert p["r0"]["W0_lb"] == d["W0_lb"] and p["r0"]["stations"] == d["stations"] and p["r0"]["wing"] == d["wing"]
    assert p["r0"]["layout"]["x_np"] == d["layout"]["x_np"] and p["r0"]["tail_arm_ft"] == d["tail_arm_ft"]


def test_every_verdict_follows_from_the_numbers_beside_it(p):
    a, acc = p["as_arranged"], {q["row"]: q for q in p["acceptance"]}
    b = a["row1"]["gear_up/empty_weight_x1"]
    ok = all(m.SM_MIN <= b[k] <= m.SM_MAX for k in ("sm_full", "sm_empty"))
    assert acc[1]["verdict"] == b["verdict"] == ("pass" if ok else "fail")
    n = a["neutral_point"]
    assert n["difference_mac"] == pytest.approx((n["independent_power_off_ft"] - n["stage1_method_ft"]) / p["r0"]["wing"]["mac"], rel=1e-12)
    assert acc[2]["verdict"] == ("pass" if abs(n["difference_mac"]) <= 0.03 else "fail")
    assert n["stage1_method_ft"] == pytest.approx(p["r0"]["layout"]["x_np"], rel=1e-9)        # r0's own neutral point, recomputed
    for e in (a, p["r1"]["evaluation"], p["r1"]["wing_alone_evaluation"]):
        env, rows = e["envelope"], e["loadings"]
        assert len(rows) == 264
        outside = sum(not (r["forward_limit_ft"] <= r["x_cg_ft"] <= env["aft_limit_ft"]) for r in rows)
        assert outside == env["payload_on"]["outside_envelope"] + env["payload_off"]["outside_envelope"]
        assert env["row3"] == ("pass" if outside == 0 else "fail")
        nose = [r["nose_load"] for r in rows if r["gear"] == "down"]
        assert env["row4"] == ("pass" if all(0.05 <= v <= 0.20 for v in nose) else "fail")
        assert env["aft_limit_ft"] == pytest.approx(env["x_np_ft"] - 0.05 * p["r0"]["wing"]["mac"], rel=1e-12)
        assert e["rotation"]["verdict"] == ("pass" if abs(e["rotation"]["p2_section_moment"]["CL_tail_needed"]) <= e["rotation"]["limit"] else "fail")
    assert acc[3]["verdict"] == a["envelope"]["row3"] and acc[4]["verdict"] == a["envelope"]["row4"]
    failed = [k for k in ("1", "3", "4") if acc[int(k)]["verdict"] == "fail"]
    assert acc[5]["rows_that_failed"] == failed and acc[5]["verdict"] == ("computed" if failed else "not needed")
    e1 = p["r1"]["evaluation"]
    assert acc[5]["on_the_r1_layout"] == {"1": e1["row1"]["gear_up/empty_weight_x1"]["verdict"], "3_payload_on": e1["envelope"]["row3_payload_on_only"],
                                          "3_all": e1["envelope"]["row3"], "4_payload_on": e1["envelope"]["row4_payload_on_only"], "4_all": e1["envelope"]["row4"]}


def test_vspaero_rule_was_applied_as_written(p):
    v = p["vspaero"]
    if not v["verdict"].get("run"):
        assert isinstance(v["result"], str) and v["verdict"]["reason"] == v["result"]
        return
    lv = v["result"]["levels"]
    assert list(lv) == ["L1", "L2", "L3"] and lv["L3"]["mesh"]["panels"] > lv["L2"]["mesh"]["panels"] > lv["L1"]["mesh"]["panels"]
    change = abs(lv["L3"]["x_np_ft"] - lv["L2"]["x_np_ft"]) / p["r0"]["wing"]["mac"]
    assert v["verdict"]["change_mac"] == pytest.approx(change, rel=1e-12)
    assert v["verdict"]["converged"] is bool(lv["L2"]["valid"] and lv["L3"]["valid"] and change <= 0.01)
    assert v["verdict"] == p4.vspaero_verdict(lv, p["r0"]["wing"]["mac"])
    for name in ("L1", "L2", "L3"):
        assert (OUT / "vspaero" / f"{name}.polar").stat().st_size > 0 and (OUT / "vspaero" / f"{name}.vsp3").stat().st_size > 0
    assert not [f for f in (OUT / "vspaero").iterdir() if f.stat().st_size > 5_000_000]


def test_numbers_of_the_record_are_what_the_code_gives_now(p, ctx):
    d, L = ctx["d"], ctx["L"]
    lay0 = m.base_layout(d, ctx["p3"])
    assert p["tanks"] == json.loads(json.dumps(ctx["tanks"]))
    st = m.stability(d, L, lay0, ctx["body"], ctx["src"])
    assert p["as_arranged"]["neutral_point"]["independent_power_off_ft"] == pytest.approx(st["x_np_power_off_ft"], rel=1e-10)
    rows = m.loadings(d, L, lay0, ctx["tanks"], ctx["choices"])
    for a, b in zip(rows, p["as_arranged"]["loadings"]):
        assert a["x_cg_ft"] == pytest.approx(b["x_cg_ft"], rel=1e-12) and a["weight_lb"] == pytest.approx(b["weight_lb"], rel=1e-12)
    lay, st1 = m.solve_r1(d, L, lay0, ctx["tanks"], ctx["choices"], ctx["body"], ctx["src"], ctx["propeller_plane_x"])
    rec = p["r1"]["solutions"]["chosen"]["layout"]
    for k in ("x_le", "arm", "ht_area", "vt_area", "x_main"):
        assert lay[k] == pytest.approx(rec[k], rel=1e-7), k
    assert p["r1"]["evaluation"]["layout"] == rec and rec["tail_te_straight"] is True
    assert p["r1"]["evaluation"]["neutral_point"]["independent_power_off_ft"] == pytest.approx(st1["x_np_power_off_ft"], rel=1e-7)
    assert p["cm0_p2"] == ctx["cm0_p2"] and p["propeller_plane_x_ft"] == ctx["propeller_plane_x"]


def test_pd20_solutions_say_what_closed_and_what_did_not(p):
    s = p["r1"]["solutions"]
    assert list(s) == ["wing_alone_r0_tail", "r0_tail_planforms_clear_of_disc", "chosen", "clearance_band_low", "clearance_band_high"]
    clr = p["choices"]["r1"]["propeller_clearance_ft"]
    assert s["chosen"]["clearance_ft"] == clr["value"] == p["r1"]["clearance_ft"]
    assert [s["clearance_band_low"]["clearance_ft"], s["clearance_band_high"]["clearance_ft"]] == clr["band"]
    assert s["chosen"]["closed"] is True and s["chosen"]["mean_static_margin"] == pytest.approx(0.10, abs=2e-4)
    for k, v in s.items():
        if v["closed"]:
            assert abs(v["mean_static_margin"] - 0.10) <= 2e-4, k
        else:
            assert "layout" not in v and v["reason"], k
        if k != "wing_alone_r0_tail":
            assert len(v["scan"]) == 9
    # the chosen tail is clear of the disc on the loft drawn with it, by the clearance
    r9 = p["r1"]["row9_on_the_loft"]["behind_plane_ft"]
    assert max(r9["horizontal_tail"], r9["vertical_tail"]) == pytest.approx(-clr["value"], abs=0.01)
    rear = p["r1"]["evaluation"]["tail_rearmost_behind_propeller_plane_ft"]
    assert max(rear.values()) == pytest.approx(-clr["value"], abs=1e-9)
    # r0's tail, as P3 found it
    rear0 = p["as_arranged"]["tail_rearmost_behind_propeller_plane_ft"]
    assert rear0["horizontal_tail"] == pytest.approx(1.78, abs=0.01) and rear0["vertical_tail"] == pytest.approx(0.87, abs=0.01)
    # the wing alone leaves the tail where it is on the wing: still in the disc
    assert max(p["r1"]["wing_alone_evaluation"]["tail_rearmost_behind_propeller_plane_ft"].values()) > 0.0
    # nothing was applied to r0: the as-arranged layout is r0's but for the two P3 stations
    lay0, d = p["as_arranged"]["layout"], p["r0"]
    assert lay0["x_le"] == d["layout"]["x_le"] and lay0["arm"] == d["tail_arm_ft"] and lay0["x_main"] == d["layout"]["x_main"]
    assert lay0["payload_x"] == pytest.approx(4.313, abs=1e-3) and lay0["avionics_x"] == pytest.approx(7.175, abs=1e-3)


def test_findings_and_decision_are_recorded(p):
    assert len(p["findings_for_r1"]) >= 10
    text = (p4.REPO / "docs/specs/00_decisions.md").read_text()
    assert "**PD-20 (2026-11-27, package P4" in text
    # PD-21 (package P4b, 2026-11-28) follows PD-20 and supersedes part of it; PD-20's own text is kept and is what is checked here
    entry = text.split("**PD-20 (2026-11-27, package P4", 1)[1].split("- **PD-21 (", 1)[0]
    assert "PD-21" not in entry
    assert "straight" in entry and "not an owner ruling" in entry and "2026-11-27_task12_pd_p4.md" in entry

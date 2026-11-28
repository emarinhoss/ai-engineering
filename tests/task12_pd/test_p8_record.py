"""The committed record of preliminary design P8 (runs/task12/pd/2026-11-28/p8): where it comes from, that no row of the
requirement is blank, that every number equals the value of the record it names, and that EP-3, EP-5 and EP-7 agree
with P5 and R16 when recomputed. These tests do not require any row to pass. Written before the run (tests first); run
on Opus 5.5 under ruling PD-22, not yet Fable-reviewed."""
import json
import math

import pytest

from conceptual.units import KT
from prelim import p5_loads as p5
from prelim import p8_envelope as p8

OUT = p8.REPO / p8.OUT_DEFAULT


@pytest.fixture(scope="module")
def r():
    return json.loads((OUT / "p8.json").read_text())


@pytest.fixture(scope="module")
def c():
    return p8.context()


def test_record_says_where_it_comes_from(r):
    for name in ("p8.json", "run.log"):
        assert (OUT / name).stat().st_size > 0, name
    i = r["inputs"]
    assert len(i["commit"]) == 40 and i["git_dirty"] is False and i["git_dirty_files"] == []
    assert i["excluded"] == p8.OUT_DEFAULT and i["tree_unchanged_during_run"] is True
    assert i["seed"] is None and i["python"] and i["scipy"] and i["command"].startswith("python -m prelim.p8_envelope")
    for key, path in i["files"].items():
        assert p8.sha256(p8.REPO / path) == i["sha256"][key], path
    assert r["choices"] == json.loads(json.dumps(p8.load_choices()))
    assert r["review"] == "Not yet Fable-reviewed (ruling PD-22)"


def test_no_row_is_blank(r):
    assert [x["id"] for x in r["rows"]] == [f"EP-{k}" for k in range(1, 10)]
    for row in r["rows"]:
        assert row["statement"].strip() and row["title"].strip() and row["sources"], row["id"]
        assert row["numbers"] and all(x["value"] is not None for x in row["numbers"]), row["id"]
        assert "{" not in row["statement"], row["id"]
        assert row["headline"] in [x["name"] for x in row["numbers"]]


def test_every_number_equals_its_record_value(r):
    files = {k: p8.read_record(k) for k in p8.RECORDS if k != "p8"}
    for row in r["rows"]:
        for x in row["numbers"]:
            data = r if x["record"] == "p8" else files[x["record"]]
            assert p8.pick(data, x["key"]) == x["value"], (row["id"], x["name"])
            assert p8.fmt(x) in row["statement"], (row["id"], x["name"])


def test_ep1_and_ep8_take_the_ruled_numbers(r):
    nums = {(row["id"], x["name"]): x["value"] for row in r["rows"] for x in row["numbers"]}
    assert nums[("EP-1", "V_C")] == 110.0 and nums[("EP-1", "V_D")] == pytest.approx(165.0, rel=1e-12)
    assert nums[("EP-8", "alt")] == 23000.0 == r["ep3"]["altitude_limit_ft"]
    assert nums[("EP-9", "bal")] == 474.0


def test_ep2_recomputes_and_its_second_reading_is_labelled(r, c):
    e = r["ep2"]
    V_C = r["r0"]["V_C_kt"] * KT
    for p in e["points"][:8]:
        q = p8.level_power(c, p["W_lb"], p["altitude_ft"], V_C)
        assert q["shaft_hp"] == pytest.approx(p["shaft_hp"], rel=1e-12) and q["full_hp"] == pytest.approx(p["full_hp"], rel=1e-12)
    for s in e["schedule"]:
        assert s["limit_needed"] is (s["limit_hp"] is not None)
        if s["limit_needed"]:
            assert s["limit_hp"] == min(s["per_weight_hp"].values()) and s["excess_hp"] == pytest.approx(s["full_hp"] - s["limit_hp"], rel=1e-12)
    assert e["check"]["verdict"] == ("pass" if e["check"]["worst"] <= e["check"]["tolerance"] else "fail")
    six = e["p6_second_reading"]
    assert "no weight" in six["label"] and six["p6_used_in_r1"] is False and six["p6_row5_verdict"] == "fail"
    for p in six["points"]:
        last = p["iterations"][-1]
        assert abs(last["next_hp"] - last["hp"]) < 0.05 and p["p6_hp"] == last["next_hp"]


def test_ep3_is_consistent_with_p5(r, c):
    """The load factor at V_C plus the allowed excursion, recomputed with P5's own function: at the binding case it is at
    the limit, at every flown weight up to the altitude limit it is inside."""
    e = r["ep3"]
    S, mac = c["b"]["geom"]["S"], c["b"]["geom"]["wing"].mac
    V_C, V_D, _ = p5.speeds(c)
    lim = json.loads((p8.REPO / p8.RECORDS["p5"]).read_text())["row3"]["limits"]
    assert e["limits"] == lim
    V = V_C + e["stated_excursion_kt"] * KT
    W = p5.weights(c)
    b = e["binding"]
    n_up, n_down = p5.ruled_gust(W[b["weight"]] / S, V, b["altitude_ft"], V_C, V_D, p5.slope_fn(c), mac, U_cap=e["U_held_fps"])[:2]
    assert (n_down if b["limited_by"] == "negative" else n_up) == pytest.approx(lim["negative_gust"] if b["limited_by"] == "negative" else lim["positive"], abs=1e-6)
    for h in [x["altitude_ft"] for x in e["schedule"]["held_at_vc_gust"] if x["altitude_ft"] <= e["altitude_limit_ft"]]:
        for wl in r["choices"]["weights"]["flown"]:
            u, dn = p5.ruled_gust(W[wl] / S, V, h, V_C, V_D, p5.slope_fn(c), mac, U_cap=e["U_held_fps"])[:2]
            assert u <= lim["positive"] + 1e-9 and dn >= lim["negative_gust"] - 1e-9, (h, wl)
    assert e["stated_excursion_floor_kt"] <= e["stated_excursion_kt"] < e["stated_excursion_floor_kt"] + 0.1
    assert e["U_held_fps"] == 30.0 and e["stated_reading"] == "held_at_vc_gust"
    # the spec's reading: what the ruled rule's gust clears, computed beside it
    for x in e["schedule"]["ruled_rule"]:
        if x["altitude_ft"] <= e["altitude_limit_ft"] and x["limited_by"] is None:
            assert x["excursion_kt"] == pytest.approx(e["V_D_minus_V_C_kt"], rel=1e-9)
    a3 = next(a for a in r["acceptance"] if a["row"] == 3)
    assert a3["verdict"] == ("pass" if a3["distance_to_limit"] <= 1e-6 and a3["largest_excess_over_limits"] <= 1e-9
                             and a3["p5_V_C_points_largest_deviation"] <= 1e-9 else "fail")


def test_ep7_is_consistent_with_p5(r, c):
    p5r = json.loads((p8.REPO / p8.RECORDS["p5"]).read_text())
    S, mac = c["b"]["geom"]["S"], c["b"]["geom"]["wing"].mac
    V_C, V_D, _ = p5.speeds(c)
    pts = [p for p in p5r["row3"]["points"] if p["speed"] == "V_D"]
    for p in pts:
        n_up, n_down = p5.ruled_gust(p["W_lb"] / S, p["V_eas_kt"] * KT, p["altitude_ft"], V_C, V_D, p5.slope_fn(c), mac)[:2]
        assert n_up == pytest.approx(p["n_up"], rel=1e-9) and n_down == pytest.approx(p["n_down"], abs=1e-9)
        assert p["U_de_fps"] == 15.0
    row = next(x for x in r["rows"] if x["id"] == "EP-7")
    nums = {x["name"]: x["value"] for x in row["numbers"]}
    assert nums["U_C"] == 30.0 and nums["U_D"] == 15.0
    assert nums["gup"] == max(p["n_up"] for p in pts) and nums["gdn"] == min(p["n_down"] for p in pts)


def test_ep5_keeps_the_r16_turn(r):
    e = r["ep5"]
    assert round(e["n_r16"], 3) == 1.155 and e["n_r16"] == pytest.approx(1.0 / math.cos(math.radians(30.0)), rel=1e-12)
    assert e["n_r16"] <= e["positive_command"] < e["positive_limit"]
    assert e["negative_limit"] < e["negative_command"]
    assert all(e["n_r16"] <= x for x in e["stall_limited_n_at_loiter"].values())
    row = next(x for x in r["rows"] if x["id"] == "EP-5")
    assert "n = 1.155" in row["statement"]


def test_ep6_gives_both_cl_max_and_names_r1(r):
    row = next(x for x in r["rows"] if x["id"] == "EP-6")
    nums = {x["name"]: x for x in row["numbers"]}
    assert nums["cl0"]["value"] == 1.35 and nums["cl1"]["record"] == "p2b" and nums["cl1"]["key"] == "wing.measured.clean"
    assert "1.276, the r1 value" in row["statement"]


def test_ep4_summary_follows_its_cases(r, c):
    e = r["ep4"]
    ch = r["choices"]["ep4_dive"]
    assert len(e["cases"]) == len(ch["start_altitudes_ft"]) * len(ch["weights"]) * len(ch["power"]) * len(ch["descent_angles_deg"])
    for x in e["by_angle"]:
        hit = [y for y in e["cases"] if y["power"] == x["power"] and y["descent_deg"] == x["descent_deg"] and y["reached_V_D"]]
        assert x["reached"] == len(hit)
        if hit:
            assert x["shortest_time_s"] == min(y["time_s"] for y in hit)
    assert e["shortest_time_s"] == min(y["time_s"] for y in e["cases"] if y["reached_V_D"])
    one = e["cases"][0]
    again = p8.dive(c, one["W_lb"], one["descent_deg"], one["start_altitude_ft"], one["power"])
    assert again["time_s"] == pytest.approx(one["time_s"], rel=1e-9) and again["end"] == one["end"]


def test_acceptance_verdicts_follow_from_their_numbers(r):
    a = {x["row"]: x for x in r["acceptance"]}
    assert sorted(a) == list(range(1, 9))
    assert a[1]["verdict"] == ("pass" if not a[1]["blank_rows"] else "fail")
    assert a[2]["verdict"] == ("pass" if not a[2]["wrong"] else "fail")
    assert a[4]["verdict"] == ("pass" if a[4]["largest_deviation"] <= a[4]["tolerance"] else "fail")
    for k in (6, 7, 8):
        assert a[k]["verdict"] == ("pass" if a[k]["worst"] <= a[k]["tolerance"] else "fail")

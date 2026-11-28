"""Preliminary design P8 (envelope protection): the choices file and the functions behind the runs of EP-2 to EP-6.
Written before the record (tests first); run on Opus 5.5 under ruling PD-22, not yet Fable-reviewed."""
import math

import pytest

from conceptual.units import KT
from prelim import p5_loads as p5
from prelim import p8_envelope as p8


@pytest.fixture(scope="module")
def c():
    return p8.context()


def test_choices_file():
    ch = p8.load_choices()
    assert ch["weights"]["flown"] == ["takeoff", "zero_fuel", "payload_off_with_ballast", "payload_off_full_fuel_with_ballast"]
    assert "payload_off_no_ballast" not in ch["weights"]["flown"]           # P4b: not flown
    assert ch["ep3_overspeed"]["stated"] == "held_at_vc_gust" and set(ch["ep3_overspeed"]["readings"]) == {"ruled_rule", "held_at_vc_gust"}
    assert ch["ep3_overspeed"]["altitude_limit_ft"] == 23000
    assert ch["ep4_dive"]["descent_angles_deg"] == [5, 10, 20, 30, 45] and ch["ep4_dive"]["power"] == ["idle", "full"]
    assert ch["ep4_dive"]["start_altitudes_ft"] == [10000, 20000, 23000] and ch["ep4_dive"]["time_limit_s"] == 600.0
    assert ch["ep2_power_limit"]["p6_second_reading"]["altitudes_ft"] == [0, 10000, 20000, 23000]
    assert "no weight" in ch["ep2_power_limit"]["p6_second_reading"]["rule"]
    for name, path in ch["records"].items():
        assert (p8.REPO / path).exists(), name


def test_pick_follows_dotted_keys_and_list_indices():
    data = {"a": [{"b": 1.5}, {"b": {"c": 2.0}}]}
    assert p8.pick(data, "a.0.b") == 1.5 and p8.pick(data, "a.1.b.c") == 2.0


def test_dive_integration_has_its_closed_form():
    gamma, V0, V1, W = math.radians(20.0), 180.0, 260.0, 2500.0
    r = p8.integrate_dive(lambda V, h: 0.0, W, gamma, V0, 15000.0, lambda V, h: V - V1, 600.0)
    t = (V1 - V0) / (p8.G * math.sin(gamma))
    assert r["end"] == "stop" and r["t_s"] == pytest.approx(t, rel=1e-8)
    assert 15000.0 - r["h_end_ft"] == pytest.approx(math.sin(gamma) * (V0 * t + 0.5 * p8.G * math.sin(gamma) * t * t), rel=1e-8)
    assert p8.dive_closed_form_check()["verdict"] == "pass"
    # a drag that holds the speed: the time limit ends it
    r = p8.integrate_dive(lambda V, h: -W * math.sin(gamma), W, gamma, V0, 15000.0, lambda V, h: V - V1, 50.0)
    assert r["end"] == "time limit" and r["V_end_fps"] == pytest.approx(V0, rel=1e-9)


def test_level_power_is_full_throttle_at_r0s_level_top_speed(c):
    chk = p8.level_top_speed_check(c, 1e-3)
    assert chk["verdict"] == "pass" and len(chk["points"]) == 2
    # more power is needed at a heavier weight and at a higher altitude, at the same EAS
    V_C = 110.0 * KT
    a, b = p8.level_power(c, 2400.0, 0.0, V_C), p8.level_power(c, 3500.0, 0.0, V_C)
    assert b["shaft_hp"] > a["shaft_hp"] and p8.level_power(c, 2400.0, 20000.0, V_C)["shaft_hp"] > a["shaft_hp"]


def test_stall_speed_is_stage1s(c):
    d = c["d"]
    assert p8.stall_speed_eas(c, d["W0_lb"], d["CL_max"]["clean"]) / KT == pytest.approx(d["performance"]["V_stall_clean_kt"], rel=1e-9)


def test_gust_code_is_p5s(c):
    """At V_C the gust is r0's own; with no held gust the cleared speed is P5's operating speed."""
    d, W = c["d"], p5.weights(c)
    V_C, V_D = p8.speeds(c)
    assert p8.gust_at(c, W["zero_fuel"], 20000.0, V_C)[0] == pytest.approx(d["gusts"]["mission_altitude/zero_fuel_weight"], rel=1e-6)  # as P5 row 3
    S, mac = c["b"]["geom"]["S"], c["b"]["geom"]["wing"].mac
    for h in (20000.0, 27500.0):
        mine = p8.cleared_speed(c, W["payload_off_with_ballast"], h, 3.8, -1.7)
        theirs = p5.operating_speed(W["payload_off_with_ballast"] / S, h, V_C, V_D, p5.slope_fn(c), mac, 3.8, -1.7)
        assert mine["V_eas_fps"] == pytest.approx(theirs["V_eas_fps"], rel=1e-9) and mine["limited_by"] == theirs["limited_by"]
    # held at 30 ft/s the cleared speed is lower than under the ruled rule, and the limit is met there
    held = p8.cleared_speed(c, W["zero_fuel"], 20000.0, 3.8, -1.7, U_cap=30.0)
    assert V_C < held["V_eas_fps"] < V_D
    n_up, n_down = p8.gust_at(c, W["zero_fuel"], 20000.0, held["V_eas_fps"], 30.0)
    assert max(n_up - 3.8, -1.7 - n_down) == pytest.approx(0.0, abs=1e-9)


def test_r16_turn_and_command_limits(c):
    e = p8.ep5(c)
    assert round(e["n_r16"], 3) == 1.155
    assert e["positive_command"] == pytest.approx(3.7, abs=1e-12) and e["negative_command"] == pytest.approx(-1.7, abs=1e-12)
    assert e["r16_available"] is True


def test_low_speed_floor_at_both_cl_max(c):
    e = p8.ep6(c)
    assert e["cl_max"]["r0"] == 1.35 and e["cl_max"]["p2_measured_r1"] == pytest.approx(1.276, abs=5e-4)
    for wl in e["weights"]:
        ratio = e["points"]["p2_measured_r1"][wl]["floor_kt"] / e["points"]["r0"][wl]["floor_kt"]
        assert ratio == pytest.approx(math.sqrt(1.35 / e["cl_max"]["p2_measured_r1"]), rel=1e-12)
        assert e["points"]["r0"][wl]["floor_kt"] == pytest.approx(1.3 * e["points"]["r0"][wl]["V_stall_kt"], rel=1e-12)

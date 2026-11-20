"""The Task 12 UAV pipeline: ledger rules, weight closure, fixed engine, layout."""
import pytest

from conceptual import uav


@pytest.fixture(scope="module")
def ledger():
    return uav.load_ledger()[0]


@pytest.fixture(scope="module")
def design(ledger):
    return uav.evaluate("pusher", 12.0, 10.0, ledger)


def test_ledger_assumed_entries_have_bands():
    _, entries = uav.load_ledger()
    for name, q in entries.items():
        if q["confidence"] == "assumed":
            lo, hi = q["band"]
            assert lo <= q["value"] <= hi, name


def test_weight_closes(design, ledger):
    # W0 = payload + empty + fuel, the build-up (3.1) at the fixed point of (3.4)
    assert design["W0"] == pytest.approx(ledger["payload_lb"] + design["We"] + design["fuel"], rel=1e-5)


def test_engine_power_meets_every_requirement(design):
    assert design["bhp"] == pytest.approx(max(design["power_req"].values()))
    assert design["power_ok"]


def test_mission_burns_fuel_in_every_segment(design):
    for name, w_in, w_out, *_ in design["mission"]:
        assert w_out < w_in, name


def test_fixed_engine_heavier_than_rubber(design, ledger):
    fixed = uav.evaluate("pusher", 12.0, 10.0, ledger,
                         engine={"bhp": 850.0, "weight_lb": 391.0, "name": "PT6A-42"})
    assert fixed["W0"] > design["W0"]
    assert fixed["power_ok"]


def test_layout_centres_static_margin(design, ledger):
    lay = uav.layout(design, ledger)
    centre = 0.5 * (lay["sm_full"] + lay["sm_empty"])
    assert centre == pytest.approx(0.5 * (ledger["static_margin_min"] + ledger["static_margin_max"]), abs=1e-3)


def test_more_endurance_costs_weight(ledger):
    a = uav.evaluate("pusher", 12.0, 10.0, dict(ledger, loiter_h=6.0))
    b = uav.evaluate("pusher", 12.0, 10.0, dict(ledger, loiter_h=10.0))
    assert b["W0"] > a["W0"]


def test_layout_checks_present(design, ledger):
    lay = uav.layout(design, ledger)
    for key in ("nose_load", "prop_clearance_in", "rotation", "trim", "x_main"):
        assert key in lay
    # the main gear is in the weight and balance (reviewer finding F1)
    assert "main_gear" in lay["items"]
    total = sum(m for m, _ in lay["items"].values()) + design["fuel"]
    assert total == pytest.approx(design["W0"], rel=1e-6)


def test_gust_checked_at_zero_fuel_weight(design):
    # a lighter aircraft takes a larger gust load factor (Raymer p. 340)
    g = design["gusts"]
    assert g["sea_level/zero_fuel_weight"] > g["sea_level/takeoff_weight"]
    assert design["n_gust"] == pytest.approx(max(g.values()))


def test_ceiling_is_last_passing_altitude(design, ledger):
    h = uav.ceiling(design, ledger)
    assert h >= ledger["ceiling_ft"] - 50.0    # the rubber engine is sized to the ceiling


def test_rotation_needs_a_tail_download(design, ledger):
    # Gate A round 2, N1: with the main wheels aft of the CG the wheel reaction and friction pitch
    # the nose down, so lifting the nose needs a tail download (negative tail CL)
    lay = uav.layout(design, ledger)
    assert lay["x_main"] > max(lay["cg_full"], lay["cg_empty"])
    assert lay["rotation"]["Cm_without_tail"] < 0.0
    assert lay["rotation"]["CL_tail_needed"] < 0.0


def test_overturn_track_meets_63_degrees():
    import math
    half = uav.overturn_track(10.0, 2.0, 8.0, 4.0, 63.0)
    delta = math.atan(half / 8.0)
    d = 6.0 * math.sin(delta)
    assert math.degrees(math.atan(4.0 / d)) == pytest.approx(63.0)


def test_rotation_main_wheel_load_includes_tail_download(design, ledger):
    # Gate A round 3: the main-wheel load is weight minus total lift, tail download included
    lay = uav.layout(design, ledger)
    rot = lay["rotation"]
    from conceptual.units import KT, RHO0
    q = 0.5 * RHO0 * (rot["V_kt"] * KT) ** 2
    S, S_h = design["geom"]["S"], design["geom"]["ht"].area
    expected = design["W0"] - q * S * rot["CL_wing"] - ledger["tail_eta_h"] * q * S_h * rot["CL_tail_needed"]
    assert rot["main_wheel_load_lb"] == pytest.approx(expected, rel=1e-6)
    assert rot["main_wheel_load_lb"] > design["W0"] - q * S * rot["CL_wing"]   # download adds load


def test_overturn_uses_the_critical_cg(design, ledger):
    lay = uav.layout(design, ledger)
    halves = [uav.overturn_track(lay["x_main"], lay["x_nose"], cg, lay["h_cg"], ledger["overturn_max_deg"])
              for cg in (lay["cg_full"], lay["cg_empty"])]
    assert lay["gear_track"]["half_track_ft"] == pytest.approx(max(halves))


def test_vc_placard_caps_design_speed(ledger):
    free = uav.evaluate("pusher", 12.0, 10.0, dict(ledger, vc_placard_kt_eas=0.0))
    capped = uav.evaluate("pusher", 12.0, 10.0, dict(ledger, vc_placard_kt_eas=100.0))
    from conceptual.units import KT
    assert max(capped["V_c_eas"].values()) <= 100.0 * KT + 1e-9
    assert capped["q_design"] < free["q_design"]
    assert capped["W0"] < free["W0"]

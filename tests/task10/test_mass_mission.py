"""T10.5: mission closed forms, the mass closure and its monotonic properties (V6d)."""
import math

import pytest
from drone import evaluate, mission


def test_endurance_closed_form():
    # (dod E m_b 3600 - P_inst t_climb) / P_cruise / 3600
    e = mission.endurance_h(m_batt=1.0, E_spec_Wh_kg=180.0, dod=0.8, eta_p=0.6, P_cruise_W=60.0,
                            P_installed_W=200.0, t_climb_s=60.0)
    assert e == pytest.approx((0.8 * 180.0 * 3600.0 - 200.0 * 60.0) / 60.0 / 3600.0, rel=1e-12)


def test_power_required_and_stall_speed():
    assert mission.power_required(D=5.0, V=15.0, eta_p=0.5) == pytest.approx(150.0)
    # V_stall = sqrt(2 W / (rho S cl_max))
    v = mission.v_stall(m=3.0, S=0.4, cl_max=1.3, rho=1.225)
    assert v == pytest.approx(math.sqrt(2 * 3.0 * 9.80665 / (1.225 * 0.4 * 1.3)), rel=1e-9)


def test_evaluate_closes_and_records_the_closure(nominal, fixed):
    out = evaluate.evaluate(nominal, fixed)
    assert out["closure_residual"] < 1e-9 and out["closure_iterations"] <= 100
    masses = out["masses"]
    assert all(v > 0 for v in masses.values())
    assert abs(sum(masses.values()) - out["mtow_kg"]) < 1e-9 * out["mtow_kg"]
    assert masses["battery"] == pytest.approx(nominal["battery_fraction"] * out["mtow_kg"], rel=1e-9)
    assert masses["payload"] == pytest.approx(fixed["rules"]["payload_mass_kg"])


def test_cruise_speed_rule_and_stall_margin(nominal, fixed):
    out = evaluate.evaluate(nominal, fixed)
    assert out["v_cruise"] >= 1.3 * out["v_stall"] - 1e-9
    assert out["gates"] == []
    assert out["endurance_h"] > 0 and out["range_km"] > 0


def test_more_battery_means_more_mass_and_more_endurance(nominal, fixed):
    low = evaluate.evaluate({**nominal, "battery_fraction": 0.25}, fixed)
    high = evaluate.evaluate({**nominal, "battery_fraction": 0.40}, fixed)
    assert high["mtow_kg"] > low["mtow_kg"]
    assert high["endurance_h"] > low["endurance_h"]


def test_evaluate_is_deterministic(nominal, fixed):
    a, b = evaluate.evaluate(nominal, fixed), evaluate.evaluate(nominal, fixed)
    assert a["endurance_h"] == b["endurance_h"] and a["mtow_kg"] == b["mtow_kg"]


def test_energy_bookkeeping_closes(nominal, fixed):
    out = evaluate.evaluate(nominal, fixed)
    d = out["diagnostics"]
    usable = fixed["battery"]["depth_of_discharge"] * fixed["battery"]["pack_specific_energy_Wh_per_kg"] \
        * 3600.0 * out["masses"]["battery"]
    spent = d["P_cruise_W"] * out["endurance_h"] * 3600.0 + d["P_installed_W"] * fixed["rules"]["climb_allowance_s"]
    assert abs(spent / usable - 1.0) < 1e-9

import pytest

from geometry.inlet import build
from physics.gates import check

BASE = {"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "mach": 4.0}


def test_design_point_is_clean():
    assert check(BASE) == []


def test_total_turning_rejects_12_and_14p5():
    # the schema bound (theta2 <= 14) lives in mcp_server/schemas.py; gate 4 catches the same case
    msgs = check({**BASE, "theta1_deg": 12.0, "theta2_deg": 14.5})
    assert any(m.startswith("gate 4") and "26.5" in m and "26" in m for m in msgs)


def test_detached_second_shock_names_theta_max():
    msgs = check({**BASE, "theta1_deg": 12.0, "theta2_deg": 30.0, "mach": 3.2})
    assert len(msgs) >= 1 and msgs[0].startswith("gate 1")
    assert "theta_max" in msgs[0] and "theta2_deg=30" in msgs[0] and "28.42" in msgs[0]


def test_detached_first_shock_names_theta_max():
    msgs = check({**BASE, "theta1_deg": 40.0})
    assert msgs[0].startswith("gate 1") and "theta1_deg=40" in msgs[0] and "theta_max" in msgs[0]


def test_margin_of_two_degrees():
    from math import degrees

    from physics.shock import theta_max
    lim = degrees(theta_max(4.0)) - 2.0
    assert check({"family": "wedge", "theta1_deg": lim - 0.01, "mach": 4.0}) == []
    assert check({"family": "wedge", "theta1_deg": lim + 0.01, "mach": 4.0})[0].startswith("gate 1")


def test_lip_too_close_to_the_corner_is_gate_2():
    params = {**BASE, "theta1_deg": 18.0, "theta2_deg": 22.0, "mach": 3.0}   # x_P - X1 = 0.0162
    msgs = check(params)
    gate2 = [m for m in msgs if m.startswith("gate 2")]
    assert len(gate2) == 1 and "x_P - X1 = 0.0162" in gate2[0] and "0.02" in gate2[0]
    with pytest.raises(ValueError):      # the builder agrees and never produces a mesh
        build(params)


def test_thin_duct_is_gate_3():
    msgs = check({**BASE, "theta1_deg": 12.0, "theta2_deg": 28.0, "mach": 5.0})   # h = 0.0078
    assert any(m.startswith("gate 3") and "0.0078" in m for m in msgs)


def test_wall_cell_reynolds_number_gate_5():
    assert check(BASE) == []
    # the corner of the design box is 42.4 at medium (limit 50): accepted
    assert check({**BASE, "theta1_deg": 12.0, "theta2_deg": 14.0}) == []
    # the coarse level (d0 = 28 um) at the same corner is 59.4: rejected, message names the limit
    msgs = check({**BASE, "theta1_deg": 12.0, "theta2_deg": 14.0, "mesh_level": "coarse"})
    assert len(msgs) == 1 and msgs[0].startswith("gate 5") and "59.4" in msgs[0] and "50" in msgs[0]
    coarse = check({**BASE, "mesh_level": "coarse"})                         # 21.3 * 1.4 = 29.8
    assert coarse == []


def test_wedge_and_cylinder():
    assert check({"family": "wedge", "theta1_deg": 10.0}) == []
    assert check({"family": "cylinder", "radius_m": 0.01}) == []
    assert check({"family": "wedge", "theta1_deg": 20.0, "mach": 3.0}) == []


def test_pure_and_does_not_mutate_params():
    params = dict(BASE)
    assert check(params) == check(params) and params == BASE

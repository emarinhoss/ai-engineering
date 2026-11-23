"""Tests of measurement/robust_sizing.py: the sized-loiter bisection, the in-memory built aircraft
and the corner endurance as a function of the sized loiter time."""
import json

import pytest

from conceptual import stage1, uav
from conceptual.engine_model import TP100_TABLE
from measurement import info_gap
from measurement import robust_sizing as rs


def test_bisection_finds_smallest_sized_loiter_on_a_toy_function():
    f = lambda L: 0.5 * (L - 8.0)                 # 3.5 h needs L = 15
    L, status = rs.bisect_sized(f, 3.5)
    assert 15.0 <= L <= 15.0 + rs.L_TOL and status == "bisected"
    assert rs.bisect_sized(lambda L: 9.0, 3.5) == (8.0, "8 h is enough")


def test_bisection_fails_when_16_h_is_not_enough():
    L, status = rs.bisect_sized(lambda L: 0.1 * L, 3.5)
    assert L is None and "not reached" in status


def test_bisection_treats_a_size_that_does_not_close_as_too_large():
    f = lambda L: None if L > 12.0 else 0.5 * (L - 8.0) + 1.0      # 3.5 h at L = 13 is never sized
    assert rs.bisect_sized(f, 3.0)[0] <= 12.0
    assert rs.bisect_sized(f, 3.5)[0] is None


@pytest.fixture(scope="module")
def sized8():
    return rs.sized_aircraft(360.0, 15.0, 10.0, 8.0)


def test_sized_aircraft_at_8_h_is_stage1_analyse(sized8):
    _, L, rec = sized8
    L0, _ = uav.load_ledger()
    ref = stage1.analyse("pusher", 15.0, 10.0, L0, rs._engine(360.0))
    assert rec["W0_lb"] == pytest.approx(ref["design"]["W0"], rel=1e-12)
    assert rec["fuel_lb"] == pytest.approx(ref["design"]["fuel"], rel=1e-12)
    assert L["loiter_h"] == 8.0


def test_in_memory_built_aircraft_reproduces_the_record_and_flies_8_h(sized8):
    _, L, rec = sized8
    built = info_gap.Built("in memory", True, record=(rec, L, TP100_TABLE))
    nominal = info_gap.nominal_theta(info_gap.uncertain_variables(uav.load_ledger()[1]))
    assert built.w0_for(nominal) == pytest.approx(rec["W0_lb"], abs=0.1)
    assert built.hours_on_station(nominal) == pytest.approx(8.0, abs=0.01)


def test_corner_endurance_increases_with_sized_loiter():
    theta = info_gap.nominal_theta(info_gap.uncertain_variables(uav.load_ledger()[1]))
    h = []
    for Ls in (8.0, 9.0):
        _, L, rec = rs.sized_aircraft(360.0, 15.0, 10.0, Ls)
        h.append(rs.corner_hours(rec, L, theta))
    assert h[1] > h[0] > 0.0


def test_ledger_copy_carries_the_sized_loiter():
    text = rs.ledger_text(9.25)
    import yaml
    assert yaml.safe_load(text)["requirements"]["loiter_h"]["value"] == 9.25
    assert "robust_sizing" in text


def test_theta_star_source_is_flagged_as_the_360_hp_worst_point():
    moved = next(c for c in json.loads(rs.THETA_SOURCE.read_text())["worst_case_curve"]
                 if c["h"] == 1.0)["R5"]["moved"]
    theta = rs.theta_from_moved(moved)
    assert theta["engine_power_mult"] == moved["engine_power_mult"]

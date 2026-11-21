"""The engine table inside the Stage 1 sizing: band scaling, rating cap, turbine validity flag,
minimum-fuel leg speed and the single V_C placard (Gate A round 4)."""
import pytest

from conceptual import stage1, uav
from conceptual.engine_model import TableEngine
from conceptual.units import KT, isa

ENG = TableEngine()


def test_power_capped_at_rating():
    assert ENG.power_available(0.0, 160.0) == pytest.approx(ENG.rated)
    assert ENG._full_throttle(0.0, 160.0) > ENG.rated


def test_scaled_copy_multiplies_and_leaves_original():
    s = ENG.scaled(sfc=1.1, power=0.9)
    assert s.bsfc(20000.0, 95.0, 50.0) == pytest.approx(1.1 * ENG.bsfc(20000.0, 95.0, 50.0 / 0.9), rel=1e-9)
    assert s.power_available(20000.0, 95.0) == pytest.approx(0.9 * ENG.power_available(20000.0, 95.0))
    assert ENG.sfc_scale == 1.0 and ENG.power_scale == 1.0


def test_turbine_flag_fails_at_low_power():
    assert ENG.turbine_choked(20000.0, 95.0, 0.95 * ENG.power_available(20000.0, 95.0))[0]
    assert not ENG.turbine_choked(20000.0, 95.0, 0.4 * ENG.power_available(20000.0, 95.0))[0]


def _design():
    L, _ = uav.load_ledger()
    engs, _ = stage1.engine_options()
    return uav.evaluate("pusher", 15.0, 9.0, L, engine=engs["PBS_TP100"]), L


def test_leg_speed_is_a_fuel_minimum_above_the_floor():
    d, L = _design()
    alt = isa(L["mission_altitude_ft"])
    W, S, m = d["W0"] * 0.9, d["geom"]["S"], d["engine_model"]
    V, floored, _ = uav._leg_speed(W, S, alt, L["mission_altitude_ft"], d["CD0_alt"], d["K"],
                                   d["clmax"]["clean"], L, "range", m, d["bhp"])
    floor = L["speed_over_stall"] * uav.perf.stall_speed(W / S, alt["rho"], d["clmax"]["clean"])
    assert V >= floor * (1 - 1e-9)

    def cost(v):
        shp = uav.perf.drag(W, S, alt["rho"], v, d["CD0_alt"], d["K"]) * v / (550.0 * L["eta_p"])
        # fuel per ground distance against the R19 headwind
        return m.bsfc(L["mission_altitude_ft"], v / KT, shp) * shp / (v - L.get("headwind_kt", 0.0) * KT)
    assert cost(V) <= cost(V * 1.04) and (floored or cost(V) <= cost(V / 1.04))


def test_single_placard_at_every_altitude():
    d, L = _design()
    for v in d["V_c_eas"].values():
        assert v == pytest.approx(L["vc_placard_kt_eas"] * KT)


def test_mission_records_sfc_and_turbine_validity():
    d, _ = _design()
    loiter = next(m for m in d["mission"] if m[0] == "loiter")
    assert 0.8 < loiter[5] < 2.0 and 0.0 <= loiter[6] <= 1.0

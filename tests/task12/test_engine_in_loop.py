"""The engine table inside the Stage 1 sizing: band scaling, rating cap, turbine validity flag,
minimum-fuel leg speed and the single V_C placard (Gate A round 4)."""
import pytest

from conceptual import stage1, uav
from conceptual.engine_model import TableEngine
from conceptual.units import KT, isa
from measurement.rubber_tp100 import tp100_ledger_values

ENG = TableEngine()


def test_power_capped_at_rating():
    assert ENG.power_available(0.0, 160.0) == pytest.approx(ENG.rated)
    assert ENG._full_throttle(0.0, 160.0) > ENG.rated


def test_scaled_copy_multiplies_and_leaves_original():
    s = ENG.scaled(sfc=1.1, power=0.9)
    assert s.bsfc(20000.0, 95.0, 50.0) == pytest.approx(1.1 * ENG.bsfc(20000.0, 95.0, 50.0 / 0.9), rel=1e-9)
    assert s.power_available(20000.0, 95.0) == pytest.approx(0.9 * ENG.power_available(20000.0, 95.0))
    assert ENG.sfc_scale == 1.0 and ENG.power_scale == 1.0


def test_turbine_flag_follows_the_pressure_ratio():
    """The flag is the stored LP turbine pressure ratio against the critical ratio; it falls with
    power (with the variable-cp TP100 it is below critical even at full power: reported, not hidden)."""
    p = ENG.power_available(20000.0, 95.0)
    hi, lo = ENG.turbine_choked(20000.0, 95.0, 0.95 * p), ENG.turbine_choked(20000.0, 95.0, 0.4 * p)
    assert hi[0] == (hi[1] >= ENG.crit) and lo[0] == (lo[1] >= ENG.crit)
    assert lo[1] < hi[1]


def _design():
    L = tp100_ledger_values()                                   # the TP100 records' ledger values (1.05, 2,158 rpm)
    engs, _ = stage1.engine_options("PBS_TP100", 1.05)
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
    def ok(v):          # neighbours beyond the engine's power or the floor are not candidates
        try:
            return cost(v)
        except ValueError:
            return float("inf")
    assert cost(V) <= ok(V * 1.04) and (floored or cost(V) <= ok(V / 1.04))


def test_single_placard_at_every_altitude():
    d, L = _design()
    for v in d["V_c_eas"].values():
        assert v == pytest.approx(L["vc_placard_kt_eas"] * KT)


def test_mission_records_sfc_and_turbine_validity():
    d, _ = _design()
    loiter = next(m for m in d["mission"] if m[0] == "loiter")
    assert 0.8 < loiter[5] < 2.0 and 0.0 <= loiter[6] <= 1.0


def test_photo_scaled_engine_keeps_lapse_and_sfc_shape():
    big = ENG.scaled(power=260.0 / 241.0, rerate=True)
    assert big.lapse(20000.0, 95.0) == pytest.approx(ENG.lapse(20000.0, 95.0), rel=1e-12)
    assert big.power_available(20000.0, 95.0) == pytest.approx(260.0 / 241.0 * ENG.power_available(20000.0, 95.0))
    p = 0.5 * ENG.power_available(20000.0, 95.0)
    assert big.bsfc(20000.0, 95.0, p * 260.0 / 241.0) == pytest.approx(ENG.bsfc(20000.0, 95.0, p), rel=1e-12)
    # a band-end multiplier (no rerate) moves the lapse with the power
    assert ENG.scaled(power=0.9).lapse(20000.0, 95.0) == pytest.approx(0.9 * ENG.lapse(20000.0, 95.0))


# ---- the power band as a cap (ruling R-c, review M-2) -------------------------------------------------------------
def test_power_cap_limits_available_power_but_leaves_sfc_at_a_given_power_unchanged():
    c = ENG.scaled(power_cap=0.9)
    assert c.power_available(20000.0, 95.0) == pytest.approx(0.9 * ENG.power_available(20000.0, 95.0))
    p = 0.5 * c.power_available(20000.0, 95.0)
    assert c.bsfc(20000.0, 95.0, p) == pytest.approx(ENG.bsfc(20000.0, 95.0, p), rel=1e-12)
    # the rescale form moves the fraction axis: the same shaft power sits at another fraction, so SFC differs
    r = ENG.scaled(power=0.9)
    assert r.bsfc(20000.0, 95.0, p) != pytest.approx(ENG.bsfc(20000.0, 95.0, p), rel=1e-6)
    assert c.lapse(20000.0, 95.0) == pytest.approx(0.9 * ENG.lapse(20000.0, 95.0))
    assert ENG.power_cap == 1.0                                   # the original is untouched


def test_power_cap_above_one_saturates_the_fraction_axis_not_the_sfc_table():
    c = ENG.scaled(power_cap=1.1)
    avail = c.power_available(20000.0, 95.0)            # at altitude the table is below the rating, so the cap raises it
    assert avail == pytest.approx(1.1 * ENG.power_available(20000.0, 95.0))
    # shaft power above the uncapped full throttle sits at fraction 1.0 of the SFC table (clamped), not beyond it
    assert c.bsfc(20000.0, 95.0, avail) == pytest.approx(ENG.bsfc(20000.0, 95.0, ENG.power_available(20000.0, 95.0)))


def test_caps_multiply():
    assert ENG.scaled(power_cap=0.9).scaled(power_cap=0.9).power_cap == pytest.approx(0.81)

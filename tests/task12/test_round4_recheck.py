"""Round-4 recheck: headwind Breguet factor, R18 V_C coverage row, power-margin row."""
import math

import pytest

from conceptual import sizing, stage1, uav
from conceptual.units import HP, KT, isa


def test_headwind_air_distance_factor_matches_constant_speed_integration():
    # Chosen numbers: W 3000 lb, V 200 ft/s, V_w 25 kt, L/D 14, c 1.0 lb/(hp h), eta_p 0.8, 10 nm ground.
    W, V, LD, c, eta = 3000.0, 200.0, 14.0, 1.0, 0.8
    vw = 25.0 * KT
    ground = 10.0 * 6076.12
    # Independent integration at constant speed and weight: fuel = time x fuel flow.
    time_s = ground / (V - vw)
    drag = W / LD
    shaft_hp = drag * V / (HP * eta)
    fuel = time_s * c / 3600.0 * shaft_hp
    # Code under test: air distance = ground x V/(V - V_w) in Breguet (6.12).
    frac = sizing.cruise_fraction_prop(ground * V / (V - vw), c, eta, LD)
    # The fuel fraction is about 0.7 %: exp(-x) = 1 - x + x^2/2, so the linear estimate
    # differs from the exponential by x^2/2 (~ 0.5 % of the fuel burnt); 2 % relative is safe.
    assert 1.0 - frac < 0.02
    assert (1.0 - frac) * W == pytest.approx(fuel, rel=0.02)
    # Exact check in the exponent: -ln(frac) is the linear fuel fraction x with W held fixed.
    assert -math.log(frac) == pytest.approx(fuel / W, rel=1e-12)
    # No wind: V/(V - 0) = 1 gives the still-air Breguet value exactly.
    still = sizing.cruise_fraction_prop(ground * V / (V - 0.0), c, eta, LD)
    assert still == sizing.cruise_fraction_prop(ground, c, eta, LD)
    assert still > frac


def _design():
    L, _ = uav.load_ledger()
    d = uav.evaluate("pusher", 13.5, 10.5, L, engine=stage1.engine_options()[0]["PBS_TP100"])
    return d, L


def _compliance(d, L):
    lay = {"sm_full": 0.1, "sm_empty": 0.1, "nose_load": {"full": 0.1, "empty": 0.1},
           "gear_track": {"half_track_ft": 4.0, "fits": True}, "prop_clearance_in": 12.0, "trim_ok": True,
           "rotation": {"CL_tail_needed": 0.5}}
    per = uav.performance(d, L)
    comp = stage1.compliance(d, L, lay, per, 10.0, 20.0, {"max_operating_altitude_ft": 29528.0})
    return {c["requirement"]: c for c in comp}


def _row(rows, start):
    hits = [c for k, c in rows.items() if k.startswith(start)]
    assert len(hits) == 1
    return hits[0]


def _with_speed(d, tas):
    # Hand-built mission rows (9 fields as uav._mission writes them): only index 7, the fastest
    # sub-step TAS in ft/s, matters for R18; the rest are filler.
    mission = [(0.0,) * 7 + (tas * 0.8, 0.0), (0.0,) * 7 + (tas, 0.0), (0.0,) * 7 + (tas * 0.5, 0.0)]
    return dict(d, mission=mission)


def test_r18_row_is_1p1_times_fastest_substep_in_eas():
    d, L = _design()
    sigma = isa(L["mission_altitude_ft"])["sigma"]
    vc = d["V_c_eas"]["sea_level"] / KT
    tas_ok = 0.9 * vc / 1.1 * KT / math.sqrt(sigma)      # 1.1 x EAS = 0.9 V_C: covered
    tas_bad = 1.2 * vc / 1.1 * KT / math.sqrt(sigma)     # 1.1 x EAS = 1.2 V_C: not covered
    ok = _row(_compliance(_with_speed(d, tas_ok), L), "R18")
    bad = _row(_compliance(_with_speed(d, tas_bad), L), "R18")
    assert ok["value"] == pytest.approx(1.1 * tas_ok * math.sqrt(sigma) / KT, rel=1e-12)
    assert bad["value"] == pytest.approx(1.1 * tas_bad * math.sqrt(sigma) / KT, rel=1e-12)
    assert ok["limit"] == pytest.approx(vc) and ok["met"] is True
    assert bad["met"] is False


def test_power_row_limit_and_label_follow_the_margin():
    d, L = _design()
    bare = _row(_compliance(d, dict(L, margin_power_fraction=0.0)), "engine power meets")
    tight = _row(_compliance(d, dict(L, margin_power_fraction=0.05)), "engine power meets")
    assert bare["limit"] == pytest.approx(d["bhp"], rel=1e-12)
    assert tight["limit"] == pytest.approx(0.95 * d["bhp"], rel=1e-12)
    assert ", with the round-4 margin" not in bare["requirement"]
    assert ", with the round-4 margin" in tight["requirement"]

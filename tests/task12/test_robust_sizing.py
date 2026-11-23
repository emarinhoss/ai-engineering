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


# ---- the robustness curve (review RS-1 to RS-5, owner ruling 2026-11-23) --------------------------------
def test_two_corner_bisection_with_a_non_monotone_endurance():
    """Hours rise with L until the cliff at L = 11, where the aircraft cannot fly (0 h): unflyable is
    'too heavy' (upper bound down), not 'too small' (RS-4)."""
    def hours(L):
        return 0.0 if L > 11.0 else 0.5 * (L - 8.0) + 1.0 + 0.2 * (L - 8.0)

    def classify(L):
        if L > 11.0:
            return "heavy"
        return "ok" if hours(L) >= 3.0 else "small"
    L, status = rs.bisect_two_corner(classify)
    assert 8.0 + 2.0 / 0.7 <= L <= 8.0 + 2.0 / 0.7 + rs.L_TOL and status == "bisected"
    assert hours(12.0) == 0.0                           # the function is not monotone: 0 h above the cliff


def test_two_corner_bisection_says_why_when_no_size_satisfies_both():
    L, status = rs.bisect_two_corner(lambda L: "heavy" if L > 9.0 else "small")
    assert L is None and "no L satisfies both" in status
    assert rs.bisect_two_corner(lambda L: "heavy")[0] is None
    assert rs.bisect_two_corner(lambda L: "ok") == (8.0, "8 h is enough")
    assert "not reached" in rs.bisect_two_corner(lambda L: "small")[1]


def test_first_guess_scales_with_engine_and_fuel():
    assert rs.first_guess(241.0, 8.0) == 3000.0
    assert rs.first_guess(450.0, 8.0) > rs.first_guess(400.0, 8.0) > rs.first_guess(300.0, 8.0)
    assert rs.first_guess(400.0, 10.0) > rs.first_guess(400.0, 8.0)


def test_first_guess_retry_on_a_toy():
    calls = []

    def run(g):
        calls.append(g)
        if g < 4000.0:
            raise ValueError("does not close at W0 = 3000.0 lb: Wf/W0 + We/W0 = 1.01")
        return g
    res, info = rs.close_with_retry(run, 3500.0)
    assert res == 1.3 * 3500.0 and info["retried"] and calls == [3500.0, 4550.0] and "first_error" in info
    res, info = rs.close_with_retry(run, 4200.0)
    assert res == 4200.0 and not info["retried"]
    res, info = rs.close_with_retry(run, 1000.0)             # still short at 1.3 x: declared not to close
    assert res is None and info["retried"] and "error" in info
    with pytest.raises(ValueError):                           # any other ValueError is not hidden
        rs.close_with_retry(lambda g: (_ for _ in ()).throw(ValueError("bad input")), 1.0)


def test_sized_aircraft_closes_from_the_scaled_guess_where_the_default_guess_raises():
    """RS-5: 450 hp, W/S 11, A 8, 8 h does not close from 3,000 lb and closes from the scaled guess."""
    with pytest.raises(ValueError, match="does not close"):
        rs.sized_aircraft(450.0, 11.0, 8.0, 8.0)
    got, _ = rs.close_with_retry(lambda g: rs.sized_aircraft_guess(450.0, 11.0, 8.0, 8.0, g),
                                    rs.first_guess(450.0, 8.0))
    assert got is not None and 4400.0 < got[2]["W0_lb"] < 4700.0


def _toy_variables():
    return [{"name": n, "kind": "ledger", "units": "-", "nominal": 0.0, "band_lo": -1.0, "band_hi": 1.0,
             "w_lower": 1.0, "w_upper": 1.0, "clip_lo": -float("inf"), "clip_hi": float("inf")} for n in ("x", "y")]


def test_mode_split_on_a_toy():
    """Endurance worsens with x (and members with y beyond 1.5 are unflyable and ignored); the cliff
    ratio is y / 1.5. Endurance mode fails at h = 1.1, cliff mode at h = 1.5: the R5 guarantee is the min."""
    variables = _toy_variables()
    start = {"x": 1, "y": 1}

    def endurance(th):
        return (-float("inf"), "cliff") if th["y"] > 1.5 else (th["x"], None)

    def cliff(th):
        return th["y"] / 1.5, None
    hE, _, _ = rs.mode_robustness(endurance, 1.1, variables, start, ("x", "y"))
    hC, _, _ = rs.mode_robustness(cliff, 1.0, variables, start, ("x", "y"))
    assert hE["h_hat"] == pytest.approx(1.1, abs=2e-3)
    assert hC["h_hat"] == pytest.approx(1.5, abs=2e-3)
    assert min(hE["h_hat"], hC["h_hat"]) == hE["h_hat"]


@pytest.fixture(scope="module")
def p400_corners():
    base = json.loads((rs.REPO / "runs/task12/stage3/2026-11-23/robust/P400/info_gap.json").read_text())
    moved = next(c for c in base["worst_case_curve"] if c["h"] == 1.0)["R5"]["moved"]
    return rs.theta_of(moved), rs.theta_of(dict(moved, engine_sfc_mult=0.9, engine_power_mult=0.9))


def test_transit_power_ratio_reproduces_the_reviewers_cliff(p400_corners):
    """RS-2: 400 hp, W/S 13, A 8: ratio 0.986 at L_sized 8.5 h and 1.007 at 9.0 h at the cliff corner
    (unflyable above 1)."""
    _, cliff = p400_corners
    ratios = {}
    for Ls in (8.5, 9.0):
        # the reviewer's numbers were with the fixed 110 kt placard (before the per-design ruling)
        _, L, rec = rs.sized_aircraft_guess(400.0, 13.0, 8.0, Ls, rs.first_guess(400.0, Ls), vc_rule="fixed")
        B = info_gap.Built("in memory", True, record=(rec, L, TP100_TABLE))
        ratios[Ls] = info_gap.transit_power_ratio(B, cliff)
    assert ratios[8.5][0] == pytest.approx(0.986, abs=0.002) and ratios[8.5][1] is None
    assert ratios[9.0][0] == pytest.approx(1.007, abs=0.002) and ratios[9.0][1] is not None


def test_refined_steps_are_restored():
    n = (uav.N_CRUISE_STEPS, uav.N_LOITER_STEPS)
    with rs.refined_steps() as (nc, nl):
        assert (nc, nl) == (2 * n[0], 2 * n[1]) and uav.N_CRUISE_STEPS == nc
    assert (uav.N_CRUISE_STEPS, uav.N_LOITER_STEPS) == n


def test_corner_sets_dedupe():
    s = []
    assert rs.add_corner(s, "a", {"x": 1.0}) and not rs.add_corner(s, "b", {"x": 1.0}) and rs.add_corner(s, "c", {"x": 2.0})
    assert len(s) == 2


def test_stage1_analyse_default_guess_is_unchanged():
    import inspect
    assert inspect.signature(stage1.analyse).parameters["W0_guess"].default == 3000.0
    assert inspect.signature(uav.size_tail_for_rotation).parameters["W0_guess"].default == 3000.0


def test_robustness_scan_is_not_fooled_by_a_vacuous_upper_end():
    """Endurance mode: above some h no member of U(h) flies, so 'met' holds vacuously at h_max; the plain
    bisection of info_gap.robustness would answer h_max, the scan finds the first failure."""
    met = lambda h: h <= 1.1 or h >= 2.0
    assert info_gap.robustness(met)[0] == 3.0
    h, status = rs.robustness_scan(met)
    assert h == pytest.approx(1.1, abs=2e-4) and status == "bracketed"
    assert rs.robustness_scan(lambda h: True) == (3.0, "above h_max")
    assert rs.robustness_scan(lambda h: h < 0.3)[0] == pytest.approx(0.3, abs=2e-4)

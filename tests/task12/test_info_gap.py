"""Info-gap robustness (measurement/info_gap.py): fast checks, no full run."""
from pathlib import Path

import pytest

from conceptual import uav
from measurement import info_gap as ig

DESIGN = Path(__file__).resolve().parents[2] / "runs/task12/stage1/2026-11-21f/design_pusher.json"


@pytest.fixture(scope="module")
def built():
    return ig.Built(DESIGN)


@pytest.fixture(scope="module")
def variables(built):
    _, entries = uav.load_ledger(built.ledger_path)
    return ig.uncertain_variables(entries)


def test_bounds_recover_the_band_at_h1_and_the_nominal_at_h0(variables):
    ledger_vars = [v for v in variables if v["kind"] == "ledger"]
    assert len(ledger_vars) > 40
    for v in variables:
        lo1, hi1, _, _ = ig.bounds(v, 1.0)
        assert lo1 == pytest.approx(v["band_lo"]) and hi1 == pytest.approx(v["band_hi"]), v["name"]
        lo0, hi0, c_lo, c_hi = ig.bounds(v, 0.0)
        assert lo0 == hi0 == v["nominal"] and not (c_lo or c_hi), v["name"]
        _, hi2, _, c_hi2 = ig.bounds(v, 2.0)        # linear growth with h (10.7) where not clipped
        if not c_hi2:
            assert hi2 - v["nominal"] == pytest.approx(2 * v["w_upper"])


def test_engine_multipliers_are_plus_minus_ten_percent_at_h1(variables):
    eng = {v["name"]: v for v in variables if v["kind"] == "engine"}
    assert set(eng) == set(ig.ENGINE_VARS)
    for v in eng.values():
        assert ig.bounds(v, 1.0)[:2] == (pytest.approx(0.9), pytest.approx(1.1))


def test_clipping_keeps_fractions_in_unit_interval_and_reports_it(variables):
    laminar = next(v for v in variables if v["name"] == "laminar_fraction_wing")
    lo, hi, c_lo, c_hi = ig.bounds(laminar, 3.0)    # 0.15 + 3 x 0.35 = 1.2 -> 1
    assert hi == 1.0 and c_hi and not c_lo and lo == pytest.approx(0.0, abs=1e-12)


def test_corner_theta_puts_each_variable_at_its_harmful_end(variables):
    names = [v["name"] for v in variables]
    direction = {n: 0 for n in names}
    direction[names[0]], direction[names[1]] = -1, +1
    th = ig.corner_theta(variables, 1.0, direction)
    assert th[names[0]] == pytest.approx(variables[0]["band_lo"])
    assert th[names[1]] == pytest.approx(variables[1]["band_hi"])
    assert th[names[2]] == variables[2]["nominal"]


def test_bisection_on_h_matches_the_closed_form_of_the_books_5_5():
    # DMDU (5.5), p. 105: m(h) = F / (K~ + s h) >= x_c  gives  h_hat = (F / x_c - K~) / s.
    # Re-derived here: F / (K~ + s h) >= x_c  <=>  K~ + s h <= F / x_c  <=>  h <= (F / x_c - K~) / s.
    F, K, s, x_c = 1.0, 1.0 / 6.0, 1.0, 0.5
    closed = (F / x_c - K) / s
    h_hat, status = ig.robustness(lambda h: F / (K + s * h) >= x_c, h_max=10.0, tol=1e-9)
    assert status == "bracketed"
    assert h_hat == pytest.approx(closed, abs=1e-8)
    # the same function above h_max, and a requirement not met at the estimate
    assert ig.robustness(lambda h: F / (K + s * h) >= x_c, h_max=1.0)[1] == "above h_max"
    assert ig.robustness(lambda h: F / (K + s * h) >= 100.0)[0:2] == (0.0, "not met at h = 0")


def test_r5_nominal_reproduces_eight_hours_and_the_record_fields(built, variables):
    th = ig.nominal_theta(variables)
    assert built.hours_on_station(th) == pytest.approx(8.0, abs=0.01)
    to, ld = built.field_lengths(th)
    assert to == pytest.approx(built.d["performance"]["takeoff_ft"], rel=1e-9)
    assert ld == pytest.approx(built.d["performance"]["landing_ft"], rel=1e-9)


def test_a_worse_engine_loses_hours_and_a_weaker_one_lengthens_take_off(built, variables):
    th = ig.nominal_theta(variables)
    worse = dict(th, engine_sfc_mult=1.1)
    assert built.hours_on_station(worse) < 8.0
    weaker = dict(th, engine_power_mult=0.9)
    assert built.field_lengths(weaker)[0] > built.field_lengths(th)[0]


def test_harm_direction():
    assert ig.harm_direction(8.0, 7.0, 8.5, True) == -1      # lower end loses hours
    assert ig.harm_direction(700.0, 700.0, 800.0, False) == 1
    assert ig.harm_direction(8.0, 8.0, 9.0, True) == 0       # neither end is harmful

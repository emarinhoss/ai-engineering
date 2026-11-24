"""Info-gap robustness (measurement/info_gap.py): fast checks, no full run."""
import math
from pathlib import Path

import pytest

from conceptual import uav
from measurement import info_gap as ig

REPO = Path(__file__).resolve().parents[2]
DESIGN = REPO / "runs/task12/stage1/2026-11-21f/design_pusher.json"


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
    # the weight fixed point reproduces the record's W0 to 0.002 lb, hence rel 1e-5 here
    assert to == pytest.approx(built.d["performance"]["takeoff_ft"], rel=1e-5)
    assert ld == pytest.approx(built.d["performance"]["landing_ft"], rel=1e-5)


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


# ---- worst-case search (review IG-1 to IG-3) --------------------------------------------------------
def _toy_variables():
    return [{"name": n, "nominal": 0.0, "w_lower": 1.0, "w_upper": 1.0, "clip_lo": -9.0, "clip_hi": 9.0}
            for n in ("a", "b")]


def test_coordinate_search_finds_an_interaction_the_one_at_a_time_corner_misses():
    # score = a b - 0.1 a: alone, a at its lower end is worse (0.1) and b does nothing, so the
    # one-at-a-time corner is (a, b) = (-1, 0). The worst point is (-1, -1): 1.1.
    def score(th):
        return th["a"] * th["b"] - 0.1 * th["a"], None
    variables = _toy_variables()
    nominal = ig.nominal_theta(variables)
    dirs = {n: ig.harm_direction(0.0, score(dict(nominal, **{n: -1.0}))[0], score(dict(nominal, **{n: 1.0}))[0], False)
            for n in ("a", "b")}
    assert dirs == {"a": -1, "b": 0}
    start = ig.corner_theta(variables, 1.0, dirs)
    assert score(start)[0] == pytest.approx(0.1)
    res = ig.coordinate_search(score, variables, 1.0, start)
    assert res["value"] == pytest.approx(1.1) and res["theta"] == {"a": -1.0, "b": -1.0}
    # a limit stops the search at the first violation
    res = ig.coordinate_search(score, variables, 1.0, start, limit=0.5)
    assert res["stopped_at_violation"] and res["value"] > 0.5


def test_interior_scan_finds_a_worst_point_between_the_ends():
    def score(th):
        return -(th["a"] - 0.4) ** 2, None                  # worst (largest) at a = 0.4, not at an end
    variables = _toy_variables()
    res = ig.coordinate_search(score, variables, 1.0, ig.nominal_theta(variables), n_interior=9)
    assert res["theta"]["a"] == pytest.approx(0.4) and res["value"] == pytest.approx(0.0, abs=1e-12)


def test_unknown_value_errors_are_reraised_and_known_ones_recorded():
    assert "no speed on the leg" in ig.unflyable_reason(ValueError("no speed on the leg within the engine's power"))
    with pytest.raises(ValueError, match="missing"):
        try:
            raise ValueError("x: missing value")
        except ValueError as e:
            ig.unflyable_reason(e)


def test_w0_fixed_point_reproduces_the_record_at_nominal_and_responds_to_weight(built, variables):
    th = ig.nominal_theta(variables)
    assert built.w0_for(th) == pytest.approx(built.d["W0_lb"], abs=0.1)
    heavier = dict(th, avionics_uninstalled_lb=th["avionics_uninstalled_lb"] + 50.0)
    assert built.w0_for(heavier) > built.d["W0_lb"] + 40.0
    fixed = ig.Built(DESIGN, band_weight=False)
    assert fixed.w0_for(heavier) == fixed.d["W0_lb"]


def test_reviewer_case_record_r5_corner_with_low_power_is_unflyable_and_the_search_finds_it(variables):
    # IG-1: the corner of U(1) that is harmful one variable at a time (high power) is flyable; with
    # engine power at its lower end the 20,000 ft transit cannot be flown (0 h)
    built = ig.Built(DESIGN, band_weight=False)               # the record's weight, as the reviewer
    spec = {"req": "R5", "need": 3.5, "fuel_factor": 1.0}
    score = ig.make_score(built, spec)
    nominal = ig.nominal_theta(variables)
    dirs = {}
    for v in variables:
        lo, hi, _, _ = ig.bounds(v, 1.0)
        dirs[v["name"]] = ig.harm_direction(0.0, score(dict(nominal, **{v["name"]: lo}))[0],
                                            score(dict(nominal, **{v["name"]: hi}))[0], False)
    assert dirs["engine_power_mult"] == 1                    # one at a time, high power looks harmful
    start = ig.corner_theta(variables, 1.0, dirs)
    assert built.hours_on_station(start) > 3.0               # the one-at-a-time corner is flyable
    low = dict(start, engine_power_mult=ig.bounds(next(v for v in variables if v["name"] == "engine_power_mult"), 1.0)[0])
    hours, reason = built.hours_detail(low)
    assert hours == 0.0 and "no speed on the leg within the engine's power" in reason
    res = ig.coordinate_search(score, variables, 1.0, start, limit=ig.limit_of(built, spec))
    assert res["stopped_at_violation"] and res["value"] > ig.limit_of(built, spec)
    assert res["theta"]["engine_power_mult"] < 1.0


def test_pair_flips_cross_a_cliff_that_single_flips_cannot_see():
    # unflyable (inf) only when a and b are both at their lower ends; either alone changes nothing
    def score(th):
        return (math.inf if th["a"] <= -1.0 and th["b"] <= -1.0 else 0.0), None
    variables = _toy_variables()
    start = ig.nominal_theta(variables)
    assert ig.coordinate_search(score, variables, 1.0, start)["value"] == 0.0
    res = ig.coordinate_search(score, variables, 1.0, start, pair_names=("a", "b"))
    assert res["value"] == math.inf and res["n_unflyable"] >= 1


# ---- the power multiplier as a cap or a rescale (ruling R-c, review M-2) -------------------------------------------
def test_power_band_cap_keeps_sfc_at_a_given_power_and_rescale_moves_it(variables):
    th = dict(ig.nominal_theta(variables), engine_power_mult=0.9)
    cap, rescale = (ig.Built(DESIGN, power_band="cap", allow_band_mismatch=True),
                      ig.Built(DESIGN, power_band="rescale"))
    m_cap, m_re = cap.build(th, mission=False)[0]["engine_model"], rescale.build(th, mission=False)[0]["engine_model"]
    nominal = cap.build(ig.nominal_theta(variables), mission=False)[0]["engine_model"]
    assert m_cap.power_available(20000.0, 95.0) == pytest.approx(m_re.power_available(20000.0, 95.0))   # same limit
    shp = 0.4 * m_cap.power_available(20000.0, 95.0)
    assert m_cap.bsfc(20000.0, 95.0, shp) == pytest.approx(nominal.bsfc(20000.0, 95.0, shp), rel=1e-12)
    assert m_re.bsfc(20000.0, 95.0, shp) != pytest.approx(nominal.bsfc(20000.0, 95.0, shp), rel=1e-6)


def test_power_band_default_comes_from_the_engine_table_and_a_bad_name_is_refused():
    assert ig.Built(DESIGN).power_band == "rescale"          # a TP100 record
    with pytest.raises(ValueError):
        ig.Built(DESIGN, power_band="nonsense")


def test_a_band_that_contradicts_the_engine_is_refused_unless_overridden():
    with pytest.raises(ValueError, match="contradicts the record's engine"):
        ig.Built(DESIGN, power_band="cap")                   # TP100 record, cap form
    assert ig.Built(DESIGN, power_band="cap", allow_band_mismatch=True).power_band == "cap"
    assert ig.Built(DESIGN, power_band="rescale").power_band == "rescale"      # explicit and consistent


def test_m250_record_takes_cap_by_default_and_refuses_rescale():
    m250 = REPO / "runs/task12/stage3/2026-11-23/m250_info_gap/record/design_pusher.json"
    assert ig.Built(m250).power_band == "cap"
    with pytest.raises(ValueError, match="contradicts"):
        ig.Built(m250, power_band="rescale")


def test_study_and_command_line_have_the_same_default_and_the_override_flag_exists():
    import inspect
    a = ig.make_parser().parse_args(["--design", "d", "--out", "o"])
    assert a.power_band is None and a.allow_band_mismatch is False       # no form: the engine's
    assert inspect.signature(ig.study).parameters["power_band"].default is None
    assert inspect.signature(ig.study).parameters["allow_band_mismatch"].default is False
    assert ig.make_parser().parse_args(["--design", "d", "--out", "o", "--power-band", "cap",
                                        "--allow-band-mismatch"]).allow_band_mismatch is True


def test_m250_takeoff_power_is_clipped_at_the_rating_for_the_cap_form():
    """Ruling R-e (review MB-2): +10 % power cannot take the take-off shaft power above the rating."""
    m250 = REPO / "runs/task12/stage3/2026-11-23/m250_info_gap/record/design_pusher.json"
    b = ig.Built(m250)
    _, entries = uav.load_ledger(b.ledger_path)
    th = ig.nominal_theta(ig.uncertain_variables(entries))
    nominal = b.field_detail(th, ("TO",))["TO"][0]
    assert b.field_detail(dict(th, engine_power_mult=1.1), ("TO",))["TO"][0] == nominal      # clipped, not 495 shp
    assert b.field_detail(dict(th, engine_power_mult=0.9), ("TO",))["TO"][0] > nominal       # a cut still counts
    seen = []                # the take-off row's own call is the last one (sizing bisects on _takeoff before it)
    orig = uav._takeoff
    uav._takeoff = lambda W0, S, cd0, K, clmax, L, bhp, d: (seen.append(bhp), orig(W0, S, cd0, K, clmax, L, bhp, d))[1]
    try:
        b.field_detail(dict(th, engine_power_mult=1.1), ("TO",))
    finally:
        uav._takeoff = orig
    assert seen[-1] <= 450.0 + 1e-9

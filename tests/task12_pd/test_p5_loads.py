"""Preliminary design P5 (loads): tests of the methods, written before the module (spec section 3, tests first).
Run on Opus 5.5 under owner ruling PD-22; not yet Fable-reviewed.

Printed targets: NACA Report 1206 eq. (5)-(9) and Fig. 1 (opened 2026-11-28, data/task12/pd_p5_sources.yaml);
EASA CS-23 Amendment 4, 23.333 and 23.341 (same file); Anderson APD Example 6.3, p. 344 (492.4 ft/s, from the
library's chapter notes: the page could not be re-opened in this session, so the test also recomputes the printed
arithmetic); Raymer (14.6) and (14.8), p. 339, as coded in conceptual/raymer_loads.py.
"""
import math

import numpy as np
import pytest
from scipy.integrate import quad

from conceptual import raymer_loads as loads
from conceptual.units import RHO0
from prelim import p5_loads as p5


@pytest.fixture(scope="module")
def src():
    return p5.load_sources()


# ---- the sources file -----------------------------------------------------------------------------------------
def test_sources_are_recorded_and_not_committed(src):
    for key in ("cs23", "naca1206"):
        s = src[key]
        assert len(s["pdf_sha256"]) == 64 and int(s["pdf_sha256"], 16) >= 0
        assert s["pdf_committed"] is False and s["url"].startswith("https://") and s["opened"].startswith("2026-11-28")
    assert {b["host"] for b in src["blocked"]} >= {"rgl.faa.gov", "drs.faa.gov", "www.faa.gov"}
    assert not list(p5.REPO.glob("data/task12/**/*.pdf")) and not list(p5.REPO.glob("prelim/**/*.pdf"))


def test_indicial_functions_as_printed(src):
    w, k = src["naca1206"]["wagner"], src["naca1206"]["kussner"]
    assert w["A"] == [0.165, 0.335] and w["b"] == [0.090, 0.600]
    assert k["A"] == [0.236, 0.513, 0.171] and k["b"] == [0.116, 0.728, 4.84]
    assert p5.wagner(0.0) == pytest.approx(0.5, abs=1e-12)            # 1 - 0.165 - 0.335
    assert p5.kussner(0.0) == pytest.approx(0.080, abs=1e-12)         # 1 - 0.236 - 0.513 - 0.171
    assert p5.wagner(1e4) == pytest.approx(1.0, abs=1e-12) and p5.kussner(1e4) == pytest.approx(1.0, abs=1e-12)
    s = np.linspace(0.0, 50.0, 501)
    assert np.all(np.diff(p5.wagner(s)) > 0) and np.all(np.diff(p5.kussner(s)) > 0)


def test_gust_shape_eq7():
    H = 12.5
    assert p5.gust_profile(0.0, H) == 0.0 and p5.gust_profile(H, H) == pytest.approx(1.0, abs=1e-15)
    assert p5.gust_profile(2 * H, H) == pytest.approx(0.0, abs=1e-15) and p5.gust_profile(3 * H, H) == 0.0
    assert p5.gust_slope(3 * H, H) == 0.0 and p5.gust_slope(-1.0, H) == 0.0
    # the slope is the derivative of the profile
    for s in (1.0, 6.25, 12.5, 20.0):
        h = 1e-6
        assert p5.gust_slope(s, H) == pytest.approx((p5.gust_profile(s + h, H) - p5.gust_profile(s - h, H)) / (2 * h), rel=1e-7)


# ---- the time integration -------------------------------------------------------------------------------------
def test_quasi_steady_history_equals_its_closed_form():
    """With no lift lag (no exponential terms) eq. (2) is w' + w/mu = u/U with y = u/U - w/mu; w is the
    convolution of the gust with exp(-s/mu), integrated here by quadrature."""
    mu, H = 10.0, 12.5
    s, y = p5.plunge_history(mu, H, wagner_terms=([], []), kussner_terms=([], []))
    for sk in (2.0, 9.0, 12.5, 18.0, 30.0):
        w = quad(lambda x: math.exp(-(sk - x) / mu) * p5.gust_profile(x, H), 0.0, min(sk, 2 * H), limit=200)[0]
        i = int(round(sk / (s[1] - s[0])))
        assert s[i] == pytest.approx(sk, abs=1e-9)
        assert y[i] == pytest.approx(p5.gust_profile(sk, H) - w / mu, abs=1e-8)


def test_gust_factor_matches_eq9_within_the_reports_stated_errors(src):
    """Eq. (9) approximates the computed curve within +-0.01, and the report's own solution is within +-0.005:
    the integration must land within their sum of (9) over the range of mass ratios of Fig. 2."""
    tol = src["choices"]["tolerances"]["code_check_against_eq9_abs"]
    for mu in (3.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0):
        assert p5.gust_factor(mu) == pytest.approx(0.88 * mu / (5.3 + mu), abs=tol), mu


def test_gust_factor_matches_figure_1(src):
    fig = src["naca1206"]["figure_1"]
    for mu, value in fig["points"].items():
        assert p5.gust_factor(float(mu)) == pytest.approx(value, abs=fig["reading_uncertainty"]), mu


def test_gust_factor_rises_with_mass_ratio_and_stays_below_the_kussner_limit():
    ks = [p5.gust_factor(mu) for mu in (2.0, 5.0, 20.0, 80.0, 300.0)]
    assert all(b > a for a, b in zip(ks, ks[1:])) and ks[-1] < 1.0


# ---- the second text of the formula -----------------------------------------------------------------------------
def test_cs23_formula_equals_raymers_code_with_the_same_chord():
    """CS 23.341(c) and Raymer (14.4)-(14.8) have the same form: with the same chord they agree to rounding (a
    coding check only; spec P5 step 2 says agreement of the two formulas shows little)."""
    for W_S, V, U, a, c, rho in ((13.0, 185.0, 30.0, 5.29, 6.09, RHO0), (8.9, 278.0, 15.0, 5.36, 6.09, 0.0012673)):
        n_up, n_down, k, mu = p5.cs23_load_factor(W_S, V, U, a, c, rho)
        n_r, k_r, mu_r = loads.gust_load_factor(W_S, V, U, a, c, rho)
        assert n_up == pytest.approx(n_r, rel=1e-12) and k == pytest.approx(k_r, rel=1e-12) and mu == pytest.approx(mu_r, rel=1e-12)
        assert n_down == pytest.approx(2.0 - n_up, rel=1e-12)


def test_cs23_gust_speeds(src):
    vc, vd = 185.0, 278.0
    assert p5.cs23_gust_speed(vc, vc, vd, 0.0) == 50.0 and p5.cs23_gust_speed(vd, vc, vd, 20000.0) == 25.0
    assert p5.cs23_gust_speed(0.5 * (vc + vd), vc, vd, 0.0) == pytest.approx(37.5, rel=1e-12)
    assert p5.cs23_gust_speed(100.0, vc, vd, 0.0) == 50.0                      # below V_C: the V_C value
    assert p5.cs23_gust_speed(vc, vc, vd, 35000.0) == pytest.approx(37.5, rel=1e-12)   # 50 to 25 between 20,000 and 50,000 ft
    assert p5.cs23_gust_speed(vd, vc, vd, 50000.0) == pytest.approx(12.5, rel=1e-12)


def test_cs23_least_design_cruise_speed(src):
    assert src["cs23"]["design_cruise_speed"]["factor_kt"] == 33.0
    assert p5.cs23_vc_min_kt(16.0, src) == pytest.approx(132.0, rel=1e-12)


# ---- the manoeuvre envelope -------------------------------------------------------------------------------------
def test_corner_speed_anderson_example_6_3():
    """Anderson APD (6.54), Example 6.3, p. 344: n 4.5, W/S 76.84, CL_max 1.2, sea level: 492.4 ft/s."""
    assert math.sqrt(2 * 4.5 * 76.84 / (0.002377 * 1.2)) == pytest.approx(492.4, abs=0.05)
    assert p5.corner_speed(4.5, 76.84, 1.2, rho=0.002377) == pytest.approx(492.4, abs=0.05)


def test_negative_manoeuvre_envelope():
    W_S, cl_neg, n_neg, vc, vd = 13.0, -0.792, -1.8, 185.67, 278.5
    v_neg = p5.corner_speed(n_neg, W_S, cl_neg)
    assert v_neg < vc
    assert p5.negative_envelope(v_neg, W_S, cl_neg, n_neg, vc, vd) == pytest.approx(n_neg, rel=1e-12)
    assert p5.negative_envelope(0.5 * v_neg, W_S, cl_neg, n_neg, vc, vd) == pytest.approx(0.25 * n_neg, rel=1e-12)   # stall line, q in V^2
    assert p5.negative_envelope(vc, W_S, cl_neg, n_neg, vc, vd) == pytest.approx(n_neg, rel=1e-12)
    assert p5.negative_envelope(0.5 * (vc + vd), W_S, cl_neg, n_neg, vc, vd) == pytest.approx(0.5 * n_neg, rel=1e-12)
    assert p5.negative_envelope(vd, W_S, cl_neg, n_neg, vc, vd) == pytest.approx(0.0, abs=1e-12)
    assert p5.positive_envelope(1e3, W_S, 1.35, 3.8) == 3.8
    assert p5.positive_envelope(100.0, W_S, 1.35, 3.8) == pytest.approx(0.5 * RHO0 * 100.0 ** 2 * 1.35 / W_S, rel=1e-12)


# ---- the operating limit ----------------------------------------------------------------------------------------
def test_operating_speed_is_where_the_gust_reaches_a_limit():
    """A wing loading so low that the ruled gust passes a limit below V_C: the returned speed puts the binding load
    factor exactly on its limit; a heavy wing loading never reaches one and returns V_D."""
    vc, vd = 185.67, 278.5
    slope = lambda V, h: 5.3

    def n_at(V, W_S, h):
        return loads.gust_load_factor(W_S, V, loads.design_gust_velocity(V, vc, vd), 5.3, 6.09, p5.isa(h)["rho"])[0]

    out = p5.operating_speed(4.0, 20000.0, vc, vd, slope, 6.09, 3.8, -1.7)
    assert out["limited_by"] in ("positive", "negative") and out["V_eas_fps"] < vd
    n = n_at(out["V_eas_fps"], 4.0, 20000.0)
    assert (n if out["limited_by"] == "positive" else 2.0 - n) == pytest.approx(3.8 if out["limited_by"] == "positive" else -1.7, abs=1e-9)
    heavy = p5.operating_speed(30.0, 0.0, vc, vd, slope, 6.09, 3.8, -1.7)
    assert heavy["limited_by"] is None and heavy["V_eas_fps"] == vd

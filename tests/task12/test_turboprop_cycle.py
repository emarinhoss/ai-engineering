"""Mattingly App. K turboprop cycle against the book's example figures (read-offs from the library
notes, p. 597-608), and the TP100 family calibration.

Tolerances are for reading values off printed curves plus the MSH model being a simplification
of the book's program; each is stated at its test. One documented mismatch, the part-throttle
fuel consumption of Fig. K.9, is recorded by a test that measures the gap rather than hiding it.
"""
import itertools
import math

import pytest

from conceptual.units import isa
from measurement import tp100_engine as tp
from measurement import turboprop_cycle as tc

# gamma_t is printed 1.4 on p. 597. With 1.4 the optimum tau_t* misses Fig. K.4 by 0.08 at
# pi_c = 20; with 1.3 it matches every reading to 0.015, so 1.3 is taken as the intended value.
K = dict(tc.BOOK_EXAMPLE, gamma_t=1.3)
A25 = isa(25000.0)


def _opt(pi_c, k=K):
    t = tc.optimum_tau_t(0.8, A25["T"], A25["p"], pi_c, k)
    return t, tc.design_point(0.8, A25["T"], A25["p"], pi_c, t, k)


@pytest.mark.parametrize("pi_c, tau_star", [(5, 0.64), (10, 0.56), (20, 0.50), (35, 0.447)])
def test_optimum_turbine_ratio_fig_k4(pi_c, tau_star):
    assert _opt(pi_c)[0] == pytest.approx(tau_star, abs=0.015)


def test_printed_gamma_t_does_not_reproduce_fig_k4():
    t, _ = _opt(20, dict(tc.BOOK_EXAMPLE))          # gamma_t = 1.4 as printed
    assert abs(t - 0.50) > 0.05


@pytest.mark.parametrize("pi_c, F, S", [(5, 158.0, 0.83), (17, 190.0, 0.60), (35, None, 0.535)])
def test_optimum_envelope_figs_k2_k3(pi_c, F, S):
    """F/m0 within 5 %, S within 8 % of the dashed tau_t* envelopes."""
    _, d = _opt(pi_c)
    if F is not None:
        assert d["F_per_m0"] == pytest.approx(F, rel=0.05)
    assert d["S"] == pytest.approx(S, rel=0.08)


def test_high_tau_t_curve_fig_k2_k3():
    d = tc.design_point(0.8, A25["T"], A25["p"], 5, 0.75, K)
    assert d["F_per_m0"] == pytest.approx(127.0, rel=0.05)
    assert d["S"] == pytest.approx(1.04, rel=0.06)


def _example_engine():
    ref = tc.design_point(0.8, A25["T"], A25["p"], 30, 0.6, K)
    ref["m0"] = 1.0
    return ref


LIM = {"pi_c_max": 30.0, "Tt3_max": 1600.0}


def test_off_design_reproduces_design_point():
    ref = _example_engine()
    r = tc.off_design(ref, 0.8, A25["T"], A25["p"], ref["Tt4"], K)
    assert r["pi_c"] == pytest.approx(30.0, rel=1e-9)
    assert r["tau_tL"] == pytest.approx(ref["tau_tL"], rel=1e-6)
    assert r["m0"] == pytest.approx(1.0, rel=1e-9)
    assert r["shaft_hp_per_m0"] == pytest.approx(ref["shaft_hp_per_m0"], rel=1e-6)


@pytest.mark.parametrize("h, F", [(5000, 12800), (10000, 11600), (15000, 9500), (20000, 7700),
                                  (25000, 6200), (30000, 5000)])
def test_full_throttle_thrust_lapse_fig_k7(h, F):
    """F(h)/F(SL) at M0 = 0.1 within 0.015 of the curve readings (sea level 14,000 lbf)."""
    ref = _example_engine()
    sl, a = isa(0.0), isa(h)
    F0 = tc.full_throttle(ref, 0.1, sl["T"], sl["p"], K, **LIM)["F"]
    Fh = tc.full_throttle(ref, 0.1, a["T"], a["p"], K, **LIM)["F"]
    assert Fh / F0 == pytest.approx(F / 14000.0, abs=0.015)


@pytest.mark.parametrize("h, M0, pi_c", [(0, 0.01, 26.0), (0, 0.85, 20.6), (30000, 0.5, 30.0)])
def test_full_throttle_compressor_ratio_fig_k6(h, M0, pi_c):
    ref = _example_engine()
    a = isa(h)
    assert tc.full_throttle(ref, M0, a["T"], a["p"], K, **LIM)["pi_c"] == pytest.approx(pi_c, rel=0.06)


def _bucket(ref, M0, h, eta_max):
    a = isa(h)
    top = tc.full_throttle(ref, M0, a["T"], a["p"], K, eta_prop_max=eta_max, **LIM)
    best = math.inf
    for i in range(30, 101, 2):
        T = top["Tt4"] * i / 100.0
        try:
            r = tc.off_design(ref, M0, a["T"], a["p"], T, K, eta_max)
        except ValueError:
            continue
        if r["F"] > 0.0:            # deep throttling gives negative net thrust (jet slower than V0)
            best = min(best, r["S"])
    return best


def test_part_throttle_gap_fig_k9_is_recorded():
    """NOT a pass criterion. The model's part-throttle S minima at 15 kft sit above the Fig. K.9
    buckets (0.34 at M0 0.3, 0.505 at 0.5, 0.72 at 0.8) by 11-14 % with eta_prop_max 0.9 (Fig.
    K.5's level) and 17-22 % with 0.82, nearly uniformly across M0 0.3-0.8 (measured 2026-11-20).
    The design-point S is 2-8 % high too. The cause is not found. A uniform level offset is
    absorbed when an engine is calibrated to a datasheet SFC, as the TP100 family is, but the
    part-power shape is not independently validated. This test pins the gap so a change is seen."""
    ref = _example_engine()
    for M0, book in ((0.3, 0.34), (0.5, 0.505), (0.8, 0.72)):
        ratio = _bucket(ref, M0, 15000.0, 0.9) / book
        assert 1.05 < ratio < 1.35


def test_tp100_family_calibrates_to_datasheet():
    fam = tp.family()
    assert len(fam) >= 8
    sl = isa(0.0)
    for m in fam:
        r = tc.off_design(m["ref"], tp.M_RATING, sl["T"], sl["p"], m["ref"]["Tt4"], m["k"])
        assert r["bsfc"] == pytest.approx(tp.BSFC_TAKEOFF, rel=1e-3)
        assert r["shaft_hp"] == pytest.approx(tp.RATED_SHP, rel=1e-3)
        assert 3.0 < m["ref"]["pi_c"] < 7.0          # small-turboprop range


def test_tp100_power_falls_with_altitude():
    m = tp.family()[0]
    p = [tp.power_available(m, h, 95.0) for h in (0.0, 10000.0, 20000.0, 25000.0)]
    assert all(a > b for a, b in itertools.pairwise(p))
    assert tp.power_available(m, 20000.0, 95.0, hold_pi_c=False) > p[2]

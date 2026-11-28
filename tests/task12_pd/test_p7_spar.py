"""Methods of preliminary design P7 (wing spar), tested against closed forms before the module was run.
Spec P7 row 1 (coding checks before use) and the parts every later row rests on. Written before the module (tests
first); run on Opus 5.5 under ruling PD-22, not yet Fable-reviewed."""
import math

import numpy as np
import pytest

from drone import geometry
from geometry3d import sections
from prelim import p7_spar as p7


@pytest.fixture(scope="module")
def ch():
    return p7.load_choices()


def test_choices_file_is_what_pd23_says(ch):
    kd = ch["knock_down"]
    assert kd["value"] == 0.5 and kd["band"] == [0.35, 0.65] and kd["band"][0] <= kd["value"] <= kd["band"][1]
    assert "[Not lib]" in kd["source"] and "no open source" in kd["source"]
    g = ch["geometry"]
    for k in ("skin_thickness_in", "cap_width_over_chord"):
        assert g[k]["band"][0] <= g[k]["value"] <= g[k]["band"][1] and "Judgement" in g[k]["source"]
    assert g["web_buckling_K"]["value"] == 5.5
    m = ch["material"]
    caps, web = m["caps_0_deg"], m["web_pm45_deg"]
    # Table 14.4, p. 368-369, high-strength graphite/epoxy, as read twice from the library's notes
    assert (caps["density_lb_in3"], caps["F_tu_L_psi"], caps["F_cu_L_psi"], caps["E_t_L_psi"]) == (0.056, 180000.0, 180000.0, 21.0e6)
    assert (web["density_lb_in3"], web["F_su_LT_psi"], web["E_c_L_psi"], web["G_LT_psi"]) == (0.056, 65500.0, 2.34e6, 5.52e6)
    assert "could not be opened" in ch["library"]["page_check"]
    assert ch["loads"]["stations"]["strips"] == 20


def test_schrenk_shape_has_the_wing_area_and_its_end_values():
    b, cr, ct = 46.5, 8.0, 3.6
    S = 0.5 * b * cr * (1 + ct / cr)                     # (14.10)
    y = np.linspace(0.0, b / 2, 200001)
    s = p7.schrenk(y, b, cr, ct)
    assert 2.0 * np.trapezoid(s, y) == pytest.approx(S, rel=1e-6)
    assert s[0] == pytest.approx(0.5 * (cr + 4 * S / (math.pi * b)), rel=1e-12)
    assert s[-1] == pytest.approx(0.5 * ct, rel=1e-12)


def test_trapezoid_rule_of_fig_14_39():
    F, X = p7.trapezoid_force(2.0, 5.0, 4.0, 4.0)        # uniform: centre
    assert F == pytest.approx(12.0) and X == pytest.approx(3.5)
    F, X = p7.trapezoid_force(0.0, 3.0, 0.0, 6.0)        # ramp from zero: two thirds out
    assert F == pytest.approx(9.0) and X == pytest.approx(2.0)
    F, X = p7.trapezoid_force(0.0, 3.0, 6.0, 0.0)
    assert F == pytest.approx(9.0) and X == pytest.approx(1.0)
    F, X = p7.trapezoid_force(0.0, 3.0, 0.0, 0.0)        # no load: no force, placed at the middle
    assert F == 0.0 and X == pytest.approx(1.5)


def test_uniform_cantilever_equals_its_closed_form():
    L, w = 23.0, 37.0
    y = p7.stations(L, 20, [])
    F, X = p7.distributed(y, np.full_like(y, w))
    V, M = p7.shear_moment(y, F, X)
    Vc, Mc = p7.uniform_closed(y, w, L)
    assert np.max(np.abs(V - Vc)) <= 1e-6 * Vc[0] and np.max(np.abs(M - Mc)) <= 1e-6 * Mc[0]
    assert M[0] == pytest.approx(w * L ** 2 / 2, rel=1e-12)


def test_elliptic_loading_equals_its_closed_form_on_the_check_grid(ch):
    L, w0 = 23.0, 50.0
    y = p7.stations(L, ch["loads"]["closed_form_check_strips"], [])
    F, X = p7.distributed(y, w0 * np.sqrt(np.clip(1 - (y / L) ** 2, 0, None)))
    V, M = p7.shear_moment(y, F, X)
    Vc, Mc = p7.elliptic_closed(y, w0, L)
    assert Vc[0] == pytest.approx(math.pi * w0 * L / 4, rel=1e-12)
    assert Mc[0] == pytest.approx(w0 * L ** 2 / 3, rel=1e-12)
    assert np.max(np.abs(V - Vc)) <= 1e-6 * Vc[0] and np.max(np.abs(M - Mc)) <= 1e-6 * Mc[0]


def test_point_loads_and_the_area_under_the_shear_curve():
    y = p7.stations(10.0, 4, [3.0])
    assert list(y) == [0.0, 2.5, 3.0, 5.0, 7.5, 10.0]
    F, X = np.array([5.0, -2.0, 1.0]), np.array([10.0, 3.0, 6.0])     # a load at the tip, one at a station
    V, M = p7.shear_moment(y, F, X)
    for j, yj in enumerate(y):
        out = X >= yj
        assert V[j] == pytest.approx(F[out].sum())
        assert M[j] == pytest.approx(np.sum(F[out] * (X[out] - yj)))


def test_cap_area_satisfies_14_35_with_the_cap_thickness():
    M, sigma, w, h = 1.0e6, 90000.0, 9.6, 12.8
    A = p7.cap_area(M, sigma, w, h)
    assert sigma * A * (h - A / w) == pytest.approx(M, rel=1e-12)          # sigma = M/(A arm), arm = h - t_cap
    assert A < w * h / 2
    assert p7.cap_area(1e-6, sigma, w, h) == pytest.approx(1e-6 / (sigma * h), rel=1e-6)
    assert math.isnan(p7.cap_area(sigma * w * h ** 2 / 4 * 1.0001, sigma, w, h))   # no real root: the caps do not fit
    assert p7.cap_area(0.0, sigma, w, h) == 0.0


def test_web_thickness_is_the_larger_of_strength_and_buckling():
    V, h, F, K, E = 8000.0, 12.8, 32750.0, 5.5, 2.34e6
    t, ts, tb = p7.web_thickness(V, h, F, K, E)
    assert ts == pytest.approx(V / (h * F)) and t == max(ts, tb)
    assert V / (h * tb) == pytest.approx(K * E * (tb / h) ** 2, rel=1e-12)   # (14.37) met at the buckling thickness
    tau = V / (h * t)
    assert tau <= F * (1 + 1e-12) and tau <= K * E * (t / h) ** 2 * (1 + 1e-12)
    assert p7.web_thickness(0.0, h, F, K, E)[0] == 0.0


def test_margins_are_zero_for_the_sizing_load_and_grow_below_it():
    sigma, w, h, F, K, E = 90000.0, 9.6, 12.8, 32750.0, 5.5, 2.34e6
    A = p7.cap_area(5e5, sigma, w, h)
    t = p7.web_thickness(4000.0, h, F, K, E)[0]
    assert p7.cap_margin(5e5, A, w, h, sigma) == pytest.approx(0.0, abs=1e-12)
    assert p7.cap_margin(-2.5e5, A, w, h, sigma) == pytest.approx(1.0, rel=1e-12)
    assert p7.web_margin(4000.0, t, h, F, K, E) == pytest.approx(0.0, abs=1e-12)
    assert p7.web_margin(-2000.0, t, h, F, K, E) > 0.0


def test_spar_depth_is_the_lofts_section_depth():
    for x in (0.12, 0.15, 0.25, 0.30):
        assert p7.spar_depth_over_chord(x) == pytest.approx(sections.depth_between(0.04, 0.4, 0.15, x, x, n=1), rel=1e-12)
    assert 0.13 < p7.spar_depth_over_chord(0.15) < 0.15 < p7.spar_depth_over_chord(0.30) + 0.002


def test_trim_shares_n_w_between_wing_and_tail():
    c = p7.context()
    lay, x_cg = c["lay_r0"], c["cg_r0"]["full"]
    q = 0.5 * 0.0023769 * (110.0 * 1.6878099) ** 2
    t = p7.wing_and_tail_lift(3.8, c["d"]["W0_lb"], q, c, lay, x_cg)
    assert t["L_wing"] + t["L_tail"] == pytest.approx(3.8 * c["d"]["W0_lb"], rel=1e-12)
    from prelim import p4_methods as m
    assert t["CL_tail"] == pytest.approx(m.tail_cl_trim(c["d"], c["L"], lay, t["CL_wing"], x_cg, c["cm_w"]), rel=1e-12)


def test_lattice_span_load_of_an_elliptic_wing_is_elliptic():
    b = 10.0
    pf = geometry.elliptic(b, 8.0)
    y, load, dy = p7.lattice_span_load(pf, "fine", math.radians(4.0))
    ybar = np.sum(load * dy * y) / np.sum(load * dy)
    assert ybar == pytest.approx(4 * (b / 2) / (3 * math.pi), rel=0.02)     # centroid of a half ellipse


def test_stations_hold_the_extra_points_once():
    y = p7.stations(20.0, 20, [1.786, 4.0, 1.786, 0.0])
    assert y[0] == 0.0 and y[-1] == 20.0 and np.all(np.diff(y) > 0) and 1.786 in y and len(y) == 22

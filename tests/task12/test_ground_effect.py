"""Ground effect in the vortex lattice (drone/vlm.py, ground_h): method of images about z = -h.

(a) far ground reproduces free air; (b) lift slope rises as the wing nears the ground;
(c) VALIDATION against Anderson's ground-effect factor G (6.77) p. 357, tolerance fixed in advance
at +-15 % of G at every h/b (G is an empirical fit). Not tuned: see the xfail reason on (c).
"""
import math

import pytest

from drone import geometry, vlm
from measurement.anderson import ground_effect_factor

SPAN = 40.0
PF = geometry.tapered(SPAN, 10.0, 0.45)
LEVEL = "medium"
ALPHA = math.radians(4.0)


def _tail_points():
    x_t = PF.x_ref + 18.0
    return [[x_t, f * 8.0, 1.5] for f in (0.1, 0.3, 0.5, 0.7, 0.9)]


def test_far_ground_equals_free_air():
    free = vlm.derivatives(PF, LEVEL)["CL_alpha"]
    far = vlm.derivatives(PF, LEVEL, ground_h=100.0 * SPAN)["CL_alpha"]
    assert far == pytest.approx(free, rel=0.005)
    dw_free = vlm.downwash_gradient(PF, _tail_points(), LEVEL)
    dw_far = vlm.downwash_gradient(PF, _tail_points(), LEVEL, ground_h=100.0 * SPAN)
    assert dw_far == pytest.approx(dw_free, rel=0.005)


def test_lift_slope_rises_as_ground_nears():
    values = [vlm.derivatives(PF, LEVEL, ground_h=hb * SPAN)["CL_alpha"]
              for hb in (1.0, 0.5, 0.25, 0.1)]
    assert all(values[i + 1] > values[i] for i in range(len(values) - 1))
    assert values[0] > vlm.derivatives(PF, LEVEL)["CL_alpha"]


def _drag_ratios():
    """Near-field induced drag in ground effect over free air at equal CL (CDi/CL^2 at one alpha:
    a flat wing has CL ~ alpha and CDi ~ alpha^2, so the ratio of CDi/CL^2 is the ratio at equal CL)."""
    free = vlm.solve(PF, ALPHA, LEVEL)
    k_free = free["CDi_nearfield"] / free["CL"] ** 2
    out = {}
    for hb in (0.1, 0.2, 0.3, 0.5):
        g = vlm.solve(PF, ALPHA, LEVEL, ground_h=hb * SPAN)
        out[hb] = (g["CDi_nearfield"] / g["CL"] ** 2) / k_free
    return out


def test_drag_ratio_falls_toward_ground():
    r = _drag_ratios()
    assert r[0.1] < r[0.2] < r[0.3] < r[0.5] < 1.0


# Measured (medium lattice, A 10, taper 0.45; the fine lattice agrees to 0.001): ratio against G =
# 0.446 / 0.719 (h/b 0.1), 0.684 / 0.911 (0.2), 0.798 / 0.958 (0.3), 0.901 / 0.985 (0.5), i.e. the
# lattice is 38 / 25 / 17 / 8.5 % below G; only h/b = 0.5 is inside +-15 %.
@pytest.mark.xfail(strict=True, reason=(
    "Anderson G (6.77) not reproduced within +-15 %: lattice/G = 0.446/0.719 (-38 %) at h/b 0.1, "
    "0.684/0.911 (-25 %) at 0.2, 0.798/0.958 (-17 %) at 0.3, 0.901/0.985 (-8.5 %) at 0.5. "
    "Reported, not tuned."))
def test_anderson_ground_effect_factor():
    r = _drag_ratios()
    bad = {hb: (v, ground_effect_factor(hb)) for hb, v in r.items()
           if abs(v / ground_effect_factor(hb) - 1.0) > 0.15}
    assert not bad, bad


# Second reference (owner ruling G-7): Raymer (12.61) p. 304, K_eff/K = 33 (h/b)^1.5/(1 + 33 (h/b)^1.5).
# The tolerance +-15 % is the one fixed for Anderson's G; the lattice is inside it at every h/b.
def test_raymer_ground_effect_factor_by_hand():
    from measurement.ground_effect_validation import raymer_ground_effect_factor as f
    # h/b 0.1: 33 * 0.1^1.5 = 33 * 0.0316228 = 1.04355; 1.04355/2.04355 = 0.5107
    assert f(0.1) == pytest.approx(0.5107, abs=1e-4)
    assert f(0.5) == pytest.approx(33 * 0.5 ** 1.5 / (1 + 33 * 0.5 ** 1.5))
    assert f(0.0) == 0.0


def test_lattice_agrees_with_raymer_ground_effect_factor():
    from measurement.ground_effect_validation import raymer_ground_effect_factor
    r = _drag_ratios()
    bad = {hb: (v, raymer_ground_effect_factor(hb)) for hb, v in r.items()
           if abs(v / raymer_ground_effect_factor(hb) - 1.0) > 0.15}
    assert not bad, bad
    # and the two books differ from each other by 29 % at h/b 0.1
    assert raymer_ground_effect_factor(0.1) / ground_effect_factor(0.1) - 1.0 == pytest.approx(-0.29, abs=0.005)


def test_validation_script_rows_and_verdict():
    from measurement import ground_effect_validation as gev
    res = gev.compute()
    assert [r["h_over_b"] for r in res["rows"]] == [0.1, 0.2, 0.3, 0.5]
    for r in res["rows"]:
        assert r["within_anderson"] == (abs(r["lattice_induced_drag_ratio"] / r["anderson_G_6_77"] - 1.0) <= 0.15)
        assert r["within_raymer"] == (abs(r["lattice_induced_drag_ratio"] / r["raymer_12_61"] - 1.0) <= 0.15)
    assert "4 of 4" in res["verdict"] and "1 of 4" in res["verdict"] and "29 %" in res["verdict"]

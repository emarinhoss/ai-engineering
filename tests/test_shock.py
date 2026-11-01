import math

import pytest

from physics.shock import normal, oblique, theta_max

D = math.radians
RT = 1e-4  # relative tolerance


def deg(x):
    return math.degrees(x)


def test_oblique_m2_10deg():
    s = oblique(2.0, D(10))
    assert deg(s["beta"]) == pytest.approx(39.3139, abs=1e-3)
    assert s["p_ratio"] == pytest.approx(1.70658, rel=RT)
    assert s["M2"] == pytest.approx(1.64052, rel=RT)
    assert s["p0_ratio"] == pytest.approx(0.984644, rel=RT)


def test_oblique_m4_10deg():
    s = oblique(4.0, D(10))
    assert deg(s["beta"]) == pytest.approx(22.2341, abs=1e-3)
    assert s["p_ratio"] == pytest.approx(2.50604, rel=RT)
    assert s["rho_ratio"] == pytest.approx(1.88528, rel=RT)
    assert s["T_ratio"] == pytest.approx(1.32927, rel=RT)
    assert s["M2"] == pytest.approx(3.28605, rel=RT)
    assert s["p0_ratio"] == pytest.approx(0.925428, rel=RT)


def test_oblique_m4_14deg():
    s = oblique(4.0, D(14))
    assert deg(s["beta"]) == pytest.approx(26.0505, abs=1e-3)
    assert s["p_ratio"] == pytest.approx(3.43347, rel=RT)
    assert s["M2"] == pytest.approx(3.00084, rel=RT)


def test_oblique_m2p5_20deg():
    s = oblique(2.5, D(20))
    assert deg(s["beta"]) == pytest.approx(42.8902, abs=1e-3)
    assert s["p_ratio"] == pytest.approx(3.21091, rel=RT)


def test_normal():
    n2 = normal(2.0)
    assert n2["p0_ratio"] == pytest.approx(0.720874, rel=RT)
    assert n2["p_ratio"] == pytest.approx(4.5, rel=RT)
    assert n2["M2"] == pytest.approx(0.57735, rel=RT)
    assert normal(3.5)["p0_ratio"] == pytest.approx(0.212948, rel=RT)
    assert normal(0.8)["p0_ratio"] == 1.0


def test_theta_max():
    assert deg(theta_max(2.0)) == pytest.approx(22.974, abs=1e-3)
    assert deg(theta_max(4.0)) == pytest.approx(38.774, abs=1e-3)


def test_beyond_theta_max_is_nan():
    s = oblique(4.0, theta_max(4.0) + 1e-3)
    assert math.isnan(s["beta"])
    assert math.isnan(s["p_ratio"])
    assert math.isnan(s["M2"])


def test_just_below_theta_max_is_finite():
    s = oblique(4.0, theta_max(4.0) - 1e-6)
    assert math.isfinite(s["beta"])
    assert 0.0 < s["beta"] < math.pi / 2

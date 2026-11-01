import numpy as np
import pytest

from physics.heating import billig_standoff, eckert_flat_plate, fay_riddell_cylinder

EDGE = {"Me": 3.2861, "Te": 301.1, "pe": 2999.8, "Tw": 300.0}


def test_fay_riddell_reference_values():
    fr = fay_riddell_cylinder(4.0, 226.509, 1197.03, 300.0, 0.010)
    assert fr["q"] == pytest.approx(2.443e5, rel=0.005)
    assert fr["dudx"] == pytest.approx(7.213e4, rel=0.005)
    assert fr["p02"] == pytest.approx(25219.0, rel=0.001)
    assert fr["T0"] == pytest.approx(951.3, abs=0.1)
    assert fr["rho_e"] == pytest.approx(0.09235, rel=0.005)
    assert fr["rho_w"] == pytest.approx(0.2928, rel=0.005)


def test_fay_riddell_scales_with_inverse_sqrt_radius():
    q1 = fay_riddell_cylinder(4.0, 226.509, 1197.03, 300.0, 0.010)["q"]
    q4 = fay_riddell_cylinder(4.0, 226.509, 1197.03, 300.0, 0.040)["q"]
    assert q4 == pytest.approx(q1 / 2.0, rel=1e-12)


def test_eckert_reference_values():
    assert eckert_flat_plate(**EDGE, x=0.05) == pytest.approx(26.61e3, rel=0.005)
    assert eckert_flat_plate(**EDGE, x=0.09) == pytest.approx(19.84e3, rel=0.005)


def test_eckert_scales_as_inverse_sqrt_x_and_accepts_arrays():
    x = np.array([0.02, 0.08, 0.32])
    q = eckert_flat_plate(**EDGE, x=x)
    assert q.shape == (3,)
    assert q[0] / q[1] == pytest.approx(2.0, rel=1e-12)
    assert q[1] / q[2] == pytest.approx(2.0, rel=1e-12)


def test_billig_standoff_mach4():
    assert billig_standoff(4.0) == pytest.approx(0.517, abs=0.001)

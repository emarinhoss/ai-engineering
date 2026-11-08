"""T10.2a: the NACA four-digit section against the published formulas (Abbott and von Doenhoff)."""
import math

import numpy as np
import pytest
from drone import naca

# Half thickness of a 12 percent section at x/c = 0.3 with the closed-trailing-edge coefficient
# -0.1036: 5 t (0.2969 sqrt(x) - 0.1260 x - 0.3516 x^2 + 0.2843 x^3 - 0.1036 x^4).
YT_12_AT_03 = 0.6 * (0.2969 * math.sqrt(0.3) - 0.1260 * 0.3 - 0.3516 * 0.09 + 0.2843 * 0.027 - 0.1036 * 0.0081)


def test_thickness_at_30_percent_chord():
    assert abs(float(naca.thickness(0.3, 0.12)) - YT_12_AT_03) < 2e-6


def test_trailing_edge_is_closed():
    assert abs(float(naca.thickness(1.0, 0.12))) < 1e-12


def test_camber_line_of_2412_at_30_percent_chord():
    # x < p: y_c = m / p^2 (2 p x - x^2) = 0.02 / 0.16 (0.24 - 0.09)
    yc, dyc = naca.camber_line(0.3, 0.02, 0.4)
    assert abs(float(yc) - 0.01875) < 1e-9
    # dy_c/dx = 2 m / p^2 (p - x) = 0.25 (0.1)
    assert abs(float(dyc) - 0.025) < 1e-9


def test_camber_line_is_continuous_at_p():
    left = naca.camber_line(0.4 - 1e-9, 0.02, 0.4)
    right = naca.camber_line(0.4 + 1e-9, 0.02, 0.4)
    assert abs(float(left[0]) - float(right[0])) < 1e-8
    assert abs(float(left[1]) - float(right[1])) < 1e-6


def test_coordinates_form_a_closed_loop_starting_at_the_trailing_edge():
    x, y = naca.coordinates(2.0, 12.0, n=101)
    assert x[0] == pytest.approx(1.0) and x[-1] == pytest.approx(1.0)
    assert abs(y[0]) < 1e-12 and abs(y[-1]) < 1e-12
    assert len(x) == len(y) and len(x) >= 2 * 101 - 1
    # upper surface first: y rises above the camber line before the leading edge is reached
    k = int(np.argmin(x))
    assert y[:k].max() > 0 and y[k:].min() < 0


def test_symmetric_section_has_zero_camber_and_zero_lift_angle():
    x, y = naca.coordinates(0.0, 10.0, n=51)
    k = int(np.argmin(x))
    assert np.allclose(y[:k + 1], -y[-1:len(y) - k - 2:-1], atol=1e-12)
    assert abs(naca.zero_lift_angle(0.0)) < 1e-12


def test_zero_lift_angle_by_thin_airfoil_theory():
    """alpha_L0 = -(1/pi) int_0^pi dyc/dx (cos theta - 1) dtheta, x = (1 - cos theta)/2.
    Computed here independently by the trapezoid rule on the camber-line formula."""
    m, p = 0.04, 0.4
    theta = np.linspace(0.0, math.pi, 20001)
    x = 0.5 * (1.0 - np.cos(theta))
    dyc = np.where(x < p, 2 * m / p**2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    expected = -np.trapezoid(dyc * (np.cos(theta) - 1.0), theta) / math.pi
    assert abs(naca.zero_lift_angle(4.0, 40.0) - expected) < 1e-4
    assert -0.1 < expected < 0.0      # a few degrees negative, as every cambered section

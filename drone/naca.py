"""NACA four-digit section (Abbott and von Doenhoff, Theory of Wing Sections), closed trailing edge.

x is the chordwise coordinate over the chord (0 leading edge, 1 trailing edge).
"""
import numpy as np


def thickness(x, t):
    """Half thickness y_t = 5 t (0.2969 sqrt(x) - 0.1260 x - 0.3516 x^2 + 0.2843 x^3 - 0.1036 x^4).

    t is thickness over chord (0.12 for a 12 percent section). The last coefficient is -0.1036,
    which closes the trailing edge.
    """
    x = np.asarray(x, dtype=float)
    return 5.0 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                      + 0.2843 * x**3 - 0.1036 * x**4)


def camber_line(x, m, p):
    """Mean camber line and its slope (y_c, dyc_dx) for maximum camber m at chordwise position p.

    x < p:  y_c = m/p^2 (2 p x - x^2),                 dyc/dx = 2 m/p^2 (p - x)
    x >= p: y_c = m/(1-p)^2 ((1 - 2p) + 2 p x - x^2),  dyc/dx = 2 m/(1-p)^2 (p - x)
    """
    x = np.asarray(x, dtype=float)
    if m == 0.0:
        return np.zeros_like(x), np.zeros_like(x)
    front = x < p
    y_front = m / p**2 * (2.0 * p * x - x**2)
    d_front = 2.0 * m / p**2 * (p - x)
    y_back = m / (1.0 - p) ** 2 * ((1.0 - 2.0 * p) + 2.0 * p * x - x**2)
    d_back = 2.0 * m / (1.0 - p) ** 2 * (p - x)
    return np.where(front, y_front, y_back), np.where(front, d_front, d_back)


def coordinates(camber_pct, thickness_pct, n=101, position_pct=40.0):
    """Closed loop (x, y): trailing edge, upper surface to the leading edge, lower surface back.

    Cosine spacing x = (1 - cos(theta))/2. Surfaces are offset normal to the camber line:
    x_u = x - y_t sin(theta_c), y_u = y_c + y_t cos(theta_c); lower with the opposite signs.
    Returns 2n - 1 points; the first and last are the trailing edge (1, 0).
    """
    m = camber_pct / 100.0
    p = position_pct / 100.0
    theta = np.linspace(0.0, np.pi, n)
    x = 0.5 * (1.0 - np.cos(theta))
    yt = thickness(x, thickness_pct / 100.0)
    yc, dyc = camber_line(x, m, p)
    tc = np.arctan(dyc)
    xu = x - yt * np.sin(tc)
    yu = yc + yt * np.cos(tc)
    xl = x + yt * np.sin(tc)
    yl = yc - yt * np.cos(tc)
    # upper surface runs trailing edge -> leading edge; lower leading edge -> trailing edge
    xs = np.concatenate([xu[::-1], xl[1:]])
    ys = np.concatenate([yu[::-1], yl[1:]])
    return xs, ys


def zero_lift_angle(camber_pct, position_pct=40.0):
    """Thin-airfoil zero-lift angle in radians.

    alpha_L0 = -(1/pi) int_0^pi dyc/dx (cos(theta) - 1) dtheta, with x = (1 - cos(theta))/2,
    by the trapezoid rule on 20001 points.
    """
    m = camber_pct / 100.0
    p = position_pct / 100.0
    theta = np.linspace(0.0, np.pi, 20001)
    x = 0.5 * (1.0 - np.cos(theta))
    _, dyc = camber_line(x, m, p)
    integrate = getattr(np, "trapezoid", None) or np.trapz
    return float(-integrate(dyc * (np.cos(theta) - 1.0), theta) / np.pi)

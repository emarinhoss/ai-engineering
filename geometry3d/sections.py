"""NACA four-digit sections for the loft.

Source of the equations: NACA Report 460 (Jacobs, Ward and Pinkerton, 1933), p. 4-5, opened on NTRS on
2026-11-27 (record: data/task12/pd_p3_tail_section_source.yaml). NACA Report 824 does not print the thickness
polynomial; its p. 4, equations (1) to (4), gives the same rule for laying the thickness on the mean line.
x is the distance along the chord over the chord, 0 at the leading edge.
"""
import numpy as np

# Report 460, p. 4: coefficients of the basic 20 per cent thick section, +-y = a0 sqrt(x) + a1 x + ... + a4 x^4
THICKNESS_COEFFS = (0.29690, -0.12600, -0.35160, 0.28430, -0.10150)


def thickness(x, t):
    """Half thickness y_t = (t / 0.20) (0.29690 sqrt(x) - 0.12600 x - 0.35160 x^2 + 0.28430 x^3 - 0.10150 x^4)
    (Report 460, p. 4). t is the thickness over the chord. The trailing edge is not closed: y_t(1) = 0.0105 t."""
    x = np.asarray(x, dtype=float)
    a0, a1, a2, a3, a4 = THICKNESS_COEFFS
    return t / 0.20 * (a0 * np.sqrt(x) + a1 * x + a2 * x ** 2 + a3 * x ** 3 + a4 * x ** 4)


def mean_line(x, m, p):
    """Mean line and its slope (Report 460, p. 5): ahead of the maximum ordinate y_c = m/p^2 (2 p x - x^2),
    behind it y_c = m/(1-p)^2 ((1 - 2p) + 2 p x - x^2). m is the camber and p its position, over the chord."""
    x = np.asarray(x, dtype=float)
    if m == 0.0:
        return np.zeros_like(x), np.zeros_like(x)
    front = x < p
    y = np.where(front, m / p ** 2 * (2 * p * x - x ** 2), m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x ** 2))
    dy = np.where(front, 2 * m / p ** 2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    return y, dy


def surfaces(x, m, p, t):
    """Upper and lower surface points at the chord stations x: the thickness is laid off at right angles to the
    mean line, x_u = x - y_t sin(theta), y_u = y_c + y_t cos(theta), x_l = x + y_t sin(theta),
    y_l = y_c - y_t cos(theta), theta = atan(dy_c/dx) (Report 460, p. 5; Report 824, p. 4, (1)-(4))."""
    yt = thickness(x, t)
    yc, dyc = mean_line(x, m, p)
    th = np.arctan(dyc)
    return (x - yt * np.sin(th), yc + yt * np.cos(th)), (x + yt * np.sin(th), yc - yt * np.cos(th))


def loop(m, p, t, n=41):
    """Section outline as 2n - 1 points (x/c, z/c): upper surface from the trailing edge to the leading edge,
    then the lower surface back. Cosine spacing. The first and last points are the two corners of the blunt
    trailing edge of the report's equation; the mesh joins them with a flat base."""
    x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n)))
    (xu, zu), (xl, zl) = surfaces(x, m, p, t)
    return np.concatenate([xu[::-1], xl[1:]]), np.concatenate([zu[::-1], zl[1:]])


def naca4(code, n=41):
    """loop() from a designation such as "4415" or "0012"."""
    return loop(int(code[0]) / 100.0, int(code[1]) / 10.0, int(code[2:]) / 100.0, n)


def depth_between(m, p, t, x0, x1, n=200):
    """Mean distance between the upper and lower surfaces over the chord, between the chord stations x0 and x1,
    measured straight up (midpoint rule on the outline). Used for the tank volume between the spars."""
    x = x0 + (x1 - x0) * (np.arange(n) + 0.5) / n
    xs = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, 400)))
    (xu, zu), (xl, zl) = surfaces(xs, m, p, t)
    return float(np.mean(np.interp(x, xu, zu) - np.interp(x, xl, zl)))

"""Conic fuselage (Raymer 7.3-7.4, p. 123-134): control stations joined by smooth longitudinal lines.

Each cross-section is four conics with horizontal tangents at the top and bottom and vertical tangents at the
sides (Raymer Figs. 7.15 and 7.17). A conic is given by its end points A and B, the meeting point C of its end
tangents and the shape parameter rho of Raymer (7.2), p. 132: the shoulder point S lies on the line from D, the
middle of AB, to C, at rho times its length. [Not lib] The formula used to draw it is the rational quadratic
form of a conic (a weighted mean of A, C and B); tests/task12_pd/test_p3_geometry.py checks that it gives
Raymer's construction (end points, end tangents, shoulder point) and the printed cases of (7.4): rho = 0.4142
with equal tangents is a circular arc, rho = 0.5 a parabola.
"""
import numpy as np
from scipy.interpolate import PchipInterpolator

RHO_CIRCLE = np.sqrt(2.0) - 1.0          # Raymer (7.4) prints 0.4142


def conic(A, B, C, rho, n=17):
    """n points of the conic from A to B with end tangents along AC and CB and shape parameter rho:
    P(t) = ((1-t)^2 A + 2 w t (1-t) C + t^2 B) / ((1-t)^2 + 2 w t (1-t) + t^2), w = rho / (1 - rho).
    At t = 1/2 this is D + rho (C - D) with D = (A + B)/2, the shoulder point of Raymer (7.2)."""
    A, B, C = (np.asarray(p, dtype=float) for p in (A, B, C))
    w = rho / (1.0 - rho)
    t = np.linspace(0.0, 1.0, n)[:, None]
    return ((1 - t) ** 2 * A + 2 * w * t * (1 - t) * C + t ** 2 * B) / ((1 - t) ** 2 + 2 * w * t * (1 - t) + t ** 2)


def section_ring(top, bottom, half, rho, n=13):
    """Outline (y, z) of one cross-section, 4 (n - 1) points, from the top round the right side, the bottom and
    the left side. top and bottom are the heights above and below the reference line, half is the half
    breadth at the reference line."""
    ur = conic((0.0, top), (half, 0.0), (half, top), rho, n)
    lr = conic((half, 0.0), (0.0, -bottom), (half, -bottom), rho, n)
    right = np.vstack([ur[:-1], lr[:-1]])                  # top ... just before the bottom point
    left = np.vstack([lr[::-1][:-1], ur[::-1][:-1]]) * [-1.0, 1.0]   # bottom ... just before the top point
    return np.vstack([right, left])


def inside_section(y, z, top, bottom, half, rho):
    """True where the point (y, z) lies inside the section. With u = |y|/half and v = |z|/height the conic of
    one quadrant runs from (0, 1) to (1, 0) with its tangents meeting at (1, 1). A point inside the chord
    (u + v <= 1) is inside; beyond the chord the conic is c^2 = 4 w^2 a b with a = 1 - u, b = 1 - v,
    c = u + v - 1 (the weights of A, B and C that give the point), and inside is c^2 <= 4 w^2 a b."""
    height = np.where(np.asarray(z) >= 0.0, top, bottom)
    u = np.abs(y) / half
    v = np.abs(z) / height
    w = rho / (1.0 - rho)
    a, b, c = 1.0 - u, 1.0 - v, u + v - 1.0
    return (c <= 0.0) | ((a >= 0.0) & (b >= 0.0) & (c ** 2 <= 4.0 * w ** 2 * a * b))


class Body:
    """A body lofted from control stations.

    stations: rows (x, half breadth, top, bottom, rho), x rising from 0 (the nose point) to the length. Between
    the stations each of the four lines is a monotone cubic (scipy's PchipInterpolator: it passes through the
    stations, has a continuous slope and does not overshoot). Over the nose length the three size lines are
    multiplied by the ellipse sqrt(1 - (1 - x/nose_length)^2), itself a conic, which closes the nose to a
    point with a vertical tangent and meets the rest with zero slope, as the Stage 1 body does.
    centre: (y, z) of the reference line, for a body that is not on the aircraft's axis (a sponson)."""

    def __init__(self, stations, nose_length, centre=(0.0, 0.0), x0=0.0):
        s = np.asarray(stations, dtype=float)
        self.stations, self.nose_length, self.centre, self.x0 = s, float(nose_length), centre, float(x0)
        self.length = float(s[-1, 0])
        self._lines = [PchipInterpolator(s[:, 0], s[:, k]) for k in (1, 2, 3, 4)]

    def lines(self, x):
        """(half breadth, top, bottom, rho) at the stations x measured from the body's nose."""
        x = np.asarray(x, dtype=float)
        nose = np.sqrt(np.clip(1.0 - (1.0 - np.minimum(x, self.nose_length) / self.nose_length) ** 2, 0.0, 1.0))
        half, top, bottom, rho = (line(x) for line in self._lines)
        return half * nose, top * nose, bottom * nose, rho

    def rings(self, n_x=120, n=13):
        """Section outlines at n_x stations from just behind the nose point to the end, as points (x, y, z).
        The stations are closer together in the nose (cosine spacing over the nose length)."""
        k = max(8, int(round(n_x * self.nose_length / self.length)) + 6)
        nose_x = self.nose_length * (1.0 - np.cos(np.linspace(0.0, np.pi / 2, k + 1)[1:]))
        xs = np.concatenate([nose_x, np.linspace(self.nose_length, self.length, n_x - k + 1)[1:]])
        half, top, bottom, rho = self.lines(xs)
        out = np.empty((len(xs), 4 * (n - 1), 3))
        for i, x in enumerate(xs):
            yz = section_ring(top[i], bottom[i], half[i], rho[i], n)
            out[i, :, 0] = self.x0 + x
            out[i, :, 1] = self.centre[0] + yz[:, 0]
            out[i, :, 2] = self.centre[1] + yz[:, 1]
        return out

    def section_measures(self, x, n=33):
        """Perimeter and area of the section at each station x (polygon through 4 (n - 1) conic points)."""
        half, top, bottom, rho = self.lines(x)
        per, are = np.empty(len(x)), np.empty(len(x))
        for i in range(len(x)):
            p = section_ring(top[i], bottom[i], half[i], rho[i], n)
            q = np.roll(p, -1, axis=0)
            per[i] = np.linalg.norm(q - p, axis=1).sum()
            are[i] = 0.5 * abs(np.sum(p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]))     # shoelace formula
        return per, are

    def inside(self, P, clearance=0.0):
        """True for each point of P (k, 3) that is inside the skin by at least `clearance`. The clearance is
        applied by moving the point outward by it sideways and vertically, and by testing the sections a
        clearance ahead and behind as well: a simple test, slightly on the safe side at the corners. A negative
        clearance moves the point inward instead (used to say by how much a box comes out of the skin)."""
        P = np.atleast_2d(np.asarray(P, dtype=float))
        y = np.maximum(np.abs(P[:, 1] - self.centre[0]) + clearance, 0.0)
        z = P[:, 2] - self.centre[1]
        z = np.sign(z) * np.maximum(np.abs(z) + clearance, 0.0)
        ok = np.ones(len(P), dtype=bool)
        for dx in ((-clearance, 0.0, clearance) if clearance > 0.0 else (0.0,)):
            x = P[:, 0] - self.x0 + dx
            within = (x > 0.0) & (x < self.length)
            half, top, bottom, rho = self.lines(np.clip(x, 1e-9, self.length))
            ok &= within & inside_section(y, z, np.maximum(top, 1e-12), np.maximum(bottom, 1e-12),
                                          np.maximum(half, 1e-12), rho)
        return ok

    def projected_areas(self, n=4000):
        """(top-view area, side-view area) by the midpoint rule along the length."""
        x = self.length * (np.arange(n) + 0.5) / n
        half, top, bottom, _ = self.lines(x)
        return float(np.sum(2 * half) * self.length / n), float(np.sum(top + bottom) * self.length / n)

    def volume_by_sections(self, n=2000):
        """Volume as the section area integrated over the length (Raymer 7.11, p. 152-153), midpoint rule."""
        x = self.length * (np.arange(n) + 0.5) / n
        return float(self.section_measures(x)[1].sum() * self.length / n)

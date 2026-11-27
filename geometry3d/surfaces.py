"""Lofted wing, tails and simple bodies (Raymer 7.8, p. 139-146): the same section at every span station,
scaled to the local chord, so the surface is straight between the root and the tip at constant per cent chord."""
import numpy as np

from geometry3d import sections


class LiftingSurface:
    """A straight-tapered surface with an unswept or swept leading edge.

    code: NACA four-digit designation. x_le: leading edge at the root (centreline). z0: height of the chord
    plane. half_span: tip distance from the root. le_slope: leading-edge sweep as dx per unit span.
    vertical=False: a wing or tailplane, lofted from tip to tip in one piece. vertical=True: a fin from its root
    at z0 upward (the section's thickness then lies along y)."""

    def __init__(self, code, x_le, z0, half_span, c_root, c_tip, le_slope=0.0, vertical=False):
        self.code, self.x_le, self.z0, self.half_span = code, x_le, z0, half_span
        self.c_root, self.c_tip, self.le_slope, self.vertical = c_root, c_tip, le_slope, vertical
        self.m, self.p, self.t = int(code[0]) / 100.0, int(code[1]) / 10.0, int(code[2:]) / 100.0
        xs = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, 400)))
        (self._xu, self._zu), (self._xl, self._zl) = sections.surfaces(xs, self.m, self.p, self.t)

    def chord(self, s):
        """Chord at the distance s from the root (linear taper)."""
        return self.c_root + (self.c_tip - self.c_root) * np.abs(s) / self.half_span

    def stations(self, n_span=24, extra=()):
        """Span stations: tip to tip for a wing (with the centreline), root to tip for a fin; `extra` adds
        stations (the fuselage side), on both sides for a wing."""
        s = np.linspace(0.0, self.half_span, n_span + 1)
        s = np.unique(np.concatenate([s, [e for e in extra if 0.0 < e < self.half_span]]))
        return s if self.vertical else np.concatenate([-s[::-1][:-1], s])

    def rings(self, n_span=24, n=41, extra=()):
        xs, zs = sections.naca4(self.code, n)
        st = self.stations(n_span, extra)
        out = np.empty((len(st), len(xs), 3))
        for i, s in enumerate(st):
            c = self.chord(s)
            out[i, :, 0] = self.x_le + self.le_slope * abs(s) + xs * c
            if self.vertical:
                out[i, :, 1], out[i, :, 2] = zs * c, self.z0 + s
            else:
                out[i, :, 1], out[i, :, 2] = s, self.z0 + zs * c
        return out

    def mean_chord(self, n_span=24):
        """(mean aerodynamic chord, its span station, planform area) from the lofted stations: with a chord
        that is linear between stations, the integrals of c, c^2 and c y over a panel are exact:
        S = sum dy (c0 + c1)/2, mac = sum dy (c0^2 + c0 c1 + c1^2)/3 / S,
        y_mac = sum dy (y0 (2 c0 + c1) + y1 (c0 + 2 c1))/6 / S. One half is integrated."""
        s = np.linspace(0.0, self.half_span, n_span + 1)
        c = self.chord(s)
        dy, c0, c1, y0, y1 = np.diff(s), c[:-1], c[1:], s[:-1], s[1:]
        S = np.sum(dy * (c0 + c1) / 2.0)
        mac = np.sum(dy * (c0 ** 2 + c0 * c1 + c1 ** 2) / 3.0) / S
        y_mac = np.sum(dy * (y0 * (2 * c0 + c1) + y1 * (c0 + 2 * c1)) / 6.0) / S
        return float(mac), float(y_mac), float(S if self.vertical else 2.0 * S)

    def inside(self, P, clearance=0.0):
        """True for each point of P inside the surface: its chord fraction lies in 0 to 1 and its height lies
        between the lower and upper surface of the section at that span station."""
        P = np.atleast_2d(np.asarray(P, dtype=float))
        s, h = (P[:, 2] - self.z0, P[:, 1]) if self.vertical else (P[:, 1], P[:, 2] - self.z0)
        c = self.chord(np.clip(s, -self.half_span, self.half_span))
        xi = (P[:, 0] - self.x_le - self.le_slope * np.abs(s)) / c
        on_span = (s >= 0.0 if self.vertical else True) & (np.abs(s) <= self.half_span)
        upper = np.interp(xi, self._xu, self._zu) * c
        lower = np.interp(xi, self._xl, self._zl) * c
        return on_span & (xi > 0.0) & (xi < 1.0) & (h < upper - clearance) & (h > lower + clearance)

    def depth_at(self, s, xi):
        """(lower, upper) surface height at span station s and chord fraction xi (wing or tailplane)."""
        c = self.chord(s)
        return self.z0 + np.interp(xi, self._xl, self._zl) * c, self.z0 + np.interp(xi, self._xu, self._zu) * c

    def volume_between(self, xi0, xi1, s0, s1, n=200):
        """Volume inside one half of the surface between the chord fractions xi0 and xi1 and the span stations
        s0 and s1: mean depth of the section there (sections.depth_between) x (xi1 - xi0) x chord^2,
        integrated over the span by the midpoint rule."""
        s = s0 + (s1 - s0) * (np.arange(n) + 0.5) / n
        mean_depth = sections.depth_between(self.m, self.p, self.t, xi0, xi1)
        return float(np.sum(mean_depth * (xi1 - xi0) * self.chord(s) ** 2) * (s1 - s0) / n)


class Ellipsoid:
    """A simple body (sponson, turret, spinner): semi-axes a, b, c along x, y, z about a centre."""

    def __init__(self, centre, a, b, c):
        self.centre, self.a, self.b, self.c = np.asarray(centre, dtype=float), a, b, c

    def rings(self, n_x=24, n=24):
        """Circles of latitude between the two end points (which the mesh closes with cones)."""
        u = np.linspace(0.0, np.pi, n_x + 1)[1:-1]
        v = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
        out = np.empty((len(u), n, 3))
        out[:, :, 0] = self.centre[0] - self.a * np.cos(u)[:, None]
        out[:, :, 1] = self.centre[1] + self.b * np.sin(u)[:, None] * np.sin(v)[None, :]
        out[:, :, 2] = self.centre[2] + self.c * np.sin(u)[:, None] * np.cos(v)[None, :]
        return out

    def ends(self):
        return self.centre - [self.a, 0, 0], self.centre + [self.a, 0, 0]

    def inside(self, P, clearance=0.0):
        d = (np.atleast_2d(P) - self.centre) / [self.a - clearance, self.b - clearance, self.c - clearance]
        return np.sum(d ** 2, axis=1) < 1.0

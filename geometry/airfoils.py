"""Airfoil sections given by a coordinate file (Selig format), for family airfoil2d (Task 10.7e).

Format: the first line is a name; blank lines are ignored; then one "x y" pair per line, running
trailing edge -> upper surface -> leading edge -> lower surface -> trailing edge, in file order.
The chord must already be normalised (leading edge at x = 0, trailing edge at x = 1).

The file is never typed from memory (data ledger rule): files live in AIRFOIL_DIR, are retrieved,
and their sha256 is recorded in each run.

dense_loop turns the file points into the loop the mesher cuts its wall from, in the same layout as
drone.naca.coordinates (2n - 1 points, index n - 1 the leading edge, first and last the trailing
edge). ONE parametric cubic spline (x(s), y(s)) in normalised arc length s is fitted over the whole
open loop, trailing edge round the nose to trailing edge, and evaluated on a fine grid. The leading
edge is then located on that dense curve (the chord-line crossing y = 0 at the nose), inserted as
an exact point, and each half is resampled with cosine spacing in arc length, so points cluster at
both the leading and the trailing edge.
Measured on the E387 at n = 801, the largest turning between consecutive segments is about 2.7
degrees, at the curvature peak 0.005 of arc length down the lower side of the nose (radius 0.0047
at x = 0.0009), against 1.3 degrees for the NACA loop at the same n. That is the file's own
curvature at cosine spacing, not a kink; the kink this design removes was 29 degrees.

Why one spline: a real file such as the E387 has no point on the chord line at the nose. Splitting
the loop at an inserted point and fitting each surface separately gives each spline its own
not-a-knot end tangent there, and the two surfaces met at a 29 degree kink (98 to 230 inverted mesh
cells). The NACA test file hides this because (0, 0) is a real file point with near-vertical
tangents on both sides.

Closure rule: a trailing-edge gap |y_first - y_last| up to MAX_GAP (0.005 of the chord) is closed
by moving both ends to (1, 0), with the shift blended linearly to zero over the last 10 percent of
the chord on each surface; the gap is recorded by the caller. A larger gap is refused.
"""
import hashlib
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

AIRFOIL_DIR = Path("data/validation/airfoils")
MAX_GAP = 0.005
BLEND = 0.10                  # fraction of the chord over which the closure shift is blended
CHORD_TOL = 1e-3
DENSE = 20001                 # points of the single fitted spline the nose is located on


def read_selig(path):
    """(x, y) numpy arrays from a Selig file, in file order."""
    lines = [ln.strip() for ln in Path(path).read_text().splitlines()]
    lines = [ln for ln in lines if ln][1:]            # drop blank lines, then the name line
    pts = np.array([[float(v) for v in ln.split()[:2]] for ln in lines])
    return pts[:, 0], pts[:, 1]


def load(name):
    """(x, y, sha256 hex of the file bytes) of AIRFOIL_DIR / <name>.dat."""
    path = Path(AIRFOIL_DIR) / f"{name}.dat"
    if not path.is_file():
        raise FileNotFoundError(f"airfoil file not found: {path}")
    x, y = read_selig(path)
    return x, y, hashlib.sha256(path.read_bytes()).hexdigest()


def trailing_edge_gap(x, y):
    """|y_first - y_last| of a file loop."""
    return float(abs(y[0] - y[-1]))


def _check(x, y):
    if abs(x.min()) > CHORD_TOL or abs(x.max() - 1.0) > CHORD_TOL:
        raise ValueError(f"chord not normalised: x runs from {x.min():.4f} to {x.max():.4f}, "
                         "expected 0 to 1")
    gap = trailing_edge_gap(x, y)
    if gap > MAX_GAP:
        raise ValueError(f"trailing edge gap {gap:.4f} of the chord is larger than {MAX_GAP}")


def _close(x, y, k):
    """Move both trailing-edge ends to (1, 0), blended linearly over the last BLEND of the chord."""
    x, y = x.copy(), y.copy()
    for sl in (slice(0, k + 1), slice(k, None)):
        xs, ys = x[sl], y[sl]
        end = 0 if sl.start == 0 else -1
        w = np.clip((xs - (1.0 - BLEND)) / BLEND, 0.0, 1.0)
        dx, dy = 1.0 - xs[end], 0.0 - ys[end]
        x[sl], y[sl] = xs + w * dx, ys + w * dy
    return x, y


def _half(spline, u0, u1, n):
    """n points of the fitted spline between parameters u0 and u1 (leading edge first): cosine
    spacing in arc length. Arc length is measured on a fine grid, then inverted to the parameter and
    the SPLINE is evaluated there, so the points are smooth and not a polyline's corners."""
    u = np.linspace(u0, u1, DENSE)
    pts = spline(u)
    arc = np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))))
    t = 0.5 * (1.0 - np.cos(np.pi * np.linspace(0.0, 1.0, n)))
    out = spline(np.interp(t * arc[-1], arc, u))
    out[0], out[-1] = spline(u0), spline(u1)
    return out


def _nose(spline, u):
    """Parameter of the leading edge: the chord-line crossing y = 0 with the smallest x below
    mid-chord, refined on the spline; the minimum-x point of the dense curve if there is none."""
    x, y = spline(u).T
    cross = np.nonzero((y[:-1] * y[1:] <= 0.0) & (y[:-1] != y[1:]) & (x[:-1] < 0.5))[0]
    if len(cross) == 0:
        return float(u[int(np.argmin(x))])
    i = cross[np.argmin(x[cross])]
    return float(brentq(lambda v: spline(v)[1], u[i], u[i + 1], xtol=1e-14))


def dense_loop(x, y, n):
    """Loop (x, y) of 2n - 1 points, trailing edge -> upper -> leading edge -> lower -> trailing
    edge, like drone.naca.coordinates. Raises ValueError for an unnormalised chord or a trailing
    edge gap above MAX_GAP."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    _check(x, y)
    x, y = _close(x, y, int(np.argmin(x)))
    pts = np.column_stack((x, y))
    s = np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))))
    s /= s[-1]
    spline = CubicSpline(s, pts, bc_type="not-a-knot")
    u_le = _nose(spline, np.linspace(0.0, 1.0, DENSE))
    upper = _half(spline, u_le, 0.0, n)               # leading edge -> trailing edge
    lower = _half(spline, u_le, 1.0, n)
    upper[0] = lower[0] = (upper[0, 0], 0.0)          # the exact leading-edge point, on the chord
    loop = np.concatenate((upper[::-1], lower[1:]))
    return loop[:, 0], loop[:, 1]

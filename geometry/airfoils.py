"""Airfoil sections given by a coordinate file (Selig format), for family airfoil2d (Task 10.7e).

Format: the first line is a name; blank lines are ignored; then one "x y" pair per line, running
trailing edge -> upper surface -> leading edge -> lower surface -> trailing edge, in file order.
The chord must already be normalised (leading edge at x = 0, trailing edge at x = 1).

The file is never typed from memory (data ledger rule): files live in AIRFOIL_DIR, are retrieved,
and their sha256 is recorded in each run.

dense_loop turns the file points into the loop the mesher cuts its wall from, in the same layout as
drone.naca.coordinates (2n - 1 points, index n - 1 the leading edge, first and last the trailing
edge). The loop is split at the leading edge; each surface is fitted with a parametric cubic
spline (x(s), y(s)) in normalised arc length s and resampled with cosine spacing in s, so points
cluster at both the leading and the trailing edge.

Closure rule: a trailing-edge gap |y_first - y_last| up to MAX_GAP (0.005 of the chord) is closed
by moving both ends to (1, 0), with the shift blended linearly to zero over the last 10 percent of
the chord on each surface; the gap is recorded by the caller. A larger gap is refused.
"""
import hashlib
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline

AIRFOIL_DIR = Path("data/validation/airfoils")
MAX_GAP = 0.005
BLEND = 0.10                  # fraction of the chord over which the closure shift is blended
CHORD_TOL = 1e-3


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


def _leading_edge(x, y):
    """(x, y, k): the loop with the leading edge at index k. The leading edge is where the loop
    crosses the chord line y = 0 at the nose (smallest such x below mid-chord), inserted as a point
    if the file has none there. For a cambered section the nose is rotated, so the minimum-x point
    lies above the chord line and is not the leading edge the NACA formula puts at (0, 0). Falls
    back to the minimum-x point if the loop never crosses y = 0 in the front half."""
    best = None
    for i in range(len(x) - 1):
        if y[i] == 0.0:
            cand = (x[i], i, False)
        elif y[i] * y[i + 1] < 0.0:
            cand = (x[i] + (x[i + 1] - x[i]) * y[i] / (y[i] - y[i + 1]), i, True)
        else:
            continue
        if cand[0] < 0.5 and (best is None or cand[0] < best[0]):
            best = cand
    if best is None:
        return x, y, int(np.argmin(x))
    xc, i, insert = best
    if not insert:
        return x, y, i
    return np.insert(x, i + 1, xc), np.insert(y, i + 1, 0.0), i + 1


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


def _surface(pts, n):
    """n points from the leading edge to the trailing edge: spline in arc length, cosine spacing."""
    s = np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))))
    s /= s[-1]
    spline = CubicSpline(s, pts, bc_type="not-a-knot")
    t = 0.5 * (1.0 - np.cos(np.pi * np.linspace(0.0, 1.0, n)))
    out = spline(t)
    out[0], out[-1] = pts[0], pts[-1]
    return out


def dense_loop(x, y, n):
    """Loop (x, y) of 2n - 1 points, trailing edge -> upper -> leading edge -> lower -> trailing
    edge, like drone.naca.coordinates. Raises ValueError for an unnormalised chord or a trailing
    edge gap above MAX_GAP."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    _check(x, y)
    x, y, k = _leading_edge(x, y)
    x, y = _close(x, y, k)
    pts = np.column_stack((x, y))
    upper = _surface(pts[k::-1], n)                   # leading edge -> trailing edge
    lower = _surface(pts[k:], n)
    loop = np.concatenate((upper[::-1], lower[1:]))
    return loop[:, 0], loop[:, 1]

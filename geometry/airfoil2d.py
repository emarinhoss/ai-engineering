"""Structured C-mesh around a NACA four-digit section (family airfoil2d, Task 10.7a).

Chord 1 m, leading edge at (0, 0), trailing edge at (1, 0). The angle of attack is set in the SU2
config, never by rotating the mesh, so one mesh serves every angle of a design.

One C-grid, index i running round the C and index j running away from the wall:

    i:  outflow, lower --> trailing edge --> lower surface --> leading edge --> upper surface
        --> trailing edge --> outflow, upper

cut into four blocks (each counter-clockwise in (i, j)):

    0  lower wake   x from 31 down to 1 along the wake cut y = 0, j downward
    1  lower wall   trailing edge -> leading edge along the lower surface, j outward
    2  upper wall   leading edge -> trailing edge along the upper surface, j outward
    3  upper wake   x from 1 up to 31 along the wake cut, j upward

Blocks 0 and 3 share the wake cut (their bottom edges, in opposite index directions).

Farfield ("farfield" marker, MARKER_FAR in the config) is 30 chords out: a semicircle of radius 30
centred on mid-chord (0.5, 0), joined to the straight lines y = +-30 that run back to the outflow
line x = 31 (30 chords behind the trailing edge).

Wall blocks: each column is a cubic Hermite curve from the wall point P, leaving along the wall
normal, to its farfield point Q, arriving along the farfield normal (tangent length 0.5 |Q - P|).
Nodes sit on the curve by arc length with one geometric ratio and first spacing d0
(stretch_one_sided), so the wall-normal first cell is d0 at every wall node. Q is placed by a
parameter that is half normalised wall arc length and half normalised node index, so the farfield
points spread out more evenly than the clustered wall points.

The column launch directions are the wall normals after NORMAL_SMOOTHING_PASSES [1/4, 1/2, 1/4]
passes over the interior wall tangents (decision 11, 2026-11-10). Without them the E387's concave
lower surface near the trailing edge (tangent 2.2 deg at x = 0.97 to 3.7 deg at the edge) made
neighbouring columns cross about 0.9 chord out, and the fine mesh had 8 inverted cells at Re 203,800
and 7 at 305,200. The passes change every mesh slightly, so records made before decision 11 keep
their own recorded mesh fingerprints and do not re-mesh identically from this code.

Wake blocks: Hermite columns from the cut point (x, 0) to (x_top, +-30), arriving vertically. They
leave the cut along the trailing-edge normal of their own surface at the trailing edge, turning
linearly to the vertical at the outflow; the trailing-edge column is shared with the wall block.
A column that left the cut vertically next to a trailing-edge column that leans aft would cross
it within a few millimetres, which is why the wake columns lean with it. The first spacing off
the cut is d0 + (dx - dx_TE) / 2500 (dx the local streamwise spacing), so the long streamwise cells
near the outflow keep an aspect ratio near 2500 against the gate's 5000; a faster growth skews the
cells near the cut because neighbouring columns then have different stretching ratios.

Measured (scratch sweep over camber 0/4/6, thickness 8/12/15, Re 8e4/2e5/5e5, all three levels):
minimum angle 48.0 deg, largest aspect ratio 2845, no inverted cell, largest wall-normal growth
1.199 (coarse level; 1.126 at medium for the nominal section).

First cell from y+ = 0.5 at the chord Reynolds number: Cf = 0.074 Re^-0.2 (Prandtl-Schlichting
flat plate), u_tau / V = sqrt(Cf / 2), d0 = y+ c / (Re u_tau / V).
"""
import math

import numpy as np

from drone.naca import coordinates
from geometry import airfoils
from geometry.structured import Block, Mesh, stretch_one_sided, stretch_two_sided_smooth

CHORD = 1.0
FARFIELD_CHORDS = 30.0
CENTRE_X = 0.5                     # semicircle centre (mid-chord)
X_OUT = 1.0 + FARFIELD_CHORDS      # outflow line, 30 chords behind the trailing edge
Y_PLUS = 0.5
N_GEOMETRY = 801                   # points per surface of the dense section the wall is cut from
WAKE_ASPECT = 2500.0               # first wake cell d0 + (dx - dx_TE) / 2500: aspect ratio <= ~2500
HERMITE_TANGENT = 0.5              # Hermite tangent length over the distance |Q - P|
NORMAL_SMOOTHING_PASSES = 5        # [1/4, 1/2, 1/4] passes on the wall tangents (decision 11)
FACTOR = {"coarse": 1.0 / 1.4, "medium": 1.0, "fine": 1.4}   # node-count factor per level

# Medium level. Lengths in metres, counts are nodes.
MEDIUM = {
    "n_surf": 161,       # nodes per surface, leading edge to trailing edge
    "n_normal": 97,      # nodes wall -> farfield
    "n_wake": 65,        # nodes along the wake cut, trailing edge -> outflow
    "ds_le": 5.0e-4,     # wall spacing at the leading edge
    "ds_te": 4.0e-3,     # wall spacing at the trailing edge (= first wake spacing, no jump)
    "ds_max": 1.2e-2,    # largest wall spacing
}


def _odd(x):
    """Nearest odd integer to x."""
    return 2 * round((x - 1) / 2) + 1


def first_cell(reynolds, level="medium"):
    """Wall first-cell height (m) for y+ = 0.5 at the chord Reynolds number, scaled by the level:
    medium is the rule's value, fine the value / 1.4, coarse the value x 1.4."""
    if level not in FACTOR:
        raise ValueError(f"mesh_level must be coarse, medium or fine, got {level!r}")
    re = float(reynolds)
    cf = 0.074 * re ** -0.2
    u_tau_over_v = math.sqrt(cf / 2.0)
    d0 = Y_PLUS * CHORD / (re * u_tau_over_v)
    return d0 / FACTOR[level]


def sizes(level):
    """Sizes for a mesh level: lengths / FACTOR, node counts x FACTOR (kept odd)."""
    if level not in FACTOR:
        raise ValueError(f"mesh_level must be coarse, medium or fine, got {level!r}")
    nf = FACTOR[level]
    s = dict(MEDIUM)
    for k in ("ds_le", "ds_te", "ds_max"):
        s[k] = MEDIUM[k] / nf
    for k in ("n_surf", "n_normal", "n_wake"):
        s[k] = _odd(MEDIUM[k] * nf)
    return s


def _arc(pts):
    return np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))))


def _resample(pts, s_new):
    """Points at arc lengths s_new along the polyline pts (linear in arc length)."""
    s = _arc(pts)
    return np.column_stack((np.interp(s_new, s, pts[:, 0]), np.interp(s_new, s, pts[:, 1])))


def _wall(x, y, s):
    """Wall nodes, lower trailing edge -> leading edge -> upper trailing edge, as (N, 2), cut from
    the dense loop (x, y): TE, upper to LE, lower back to TE, the leading edge in the middle."""
    loop = np.column_stack((x, y))
    k = (len(x) - 1) // 2                             # index of the leading edge (0, 0)
    upper = loop[k::-1]                               # LE -> TE
    lower = loop[k:]                                  # LE -> TE
    out = []
    for surf in (lower, upper):
        length = _arc(surf)[-1]
        t, _ = stretch_two_sided_smooth(length, s["n_surf"], s["ds_le"], s["ds_te"], s["ds_max"])
        out.append(_resample(surf, t))
    lower_pts, upper_pts = out
    wall = np.concatenate((lower_pts[::-1], upper_pts[1:]))
    wall[0] = wall[-1] = (CHORD, 0.0)
    return wall


def _farfield(u):
    """Farfield point and its outward normal at parameter u in [0, 1] (arc length), running
    (1, -30) -> (0.5, -30) -> semicircle through (-29.5, 0) -> (0.5, 30) -> (1, 30)."""
    R = FARFIELD_CHORDS
    straight = CHORD - CENTRE_X
    total = 2.0 * straight + math.pi * R
    s = np.asarray(u) * total
    pts, nrm = np.zeros((len(s), 2)), np.zeros((len(s), 2))
    low = s <= straight
    high = s >= total - straight
    mid = ~(low | high)
    pts[low] = np.column_stack((CHORD - s[low], np.full(low.sum(), -R)))
    nrm[low] = (0.0, -1.0)
    pts[high] = np.column_stack((CENTRE_X + (s[high] - (total - straight)), np.full(high.sum(), R)))
    nrm[high] = (0.0, 1.0)
    phi = 1.5 * math.pi - (s[mid] - straight) / R     # 270 deg (bottom) -> 90 deg (top) via 180
    nrm[mid] = np.column_stack((np.cos(phi), np.sin(phi)))
    pts[mid] = np.column_stack((CENTRE_X + R * np.cos(phi), R * np.sin(phi)))
    return pts, nrm


def _column(P, n0, Q, n1, n_nodes, d0, samples=2001):
    """Nodes on the cubic Hermite curve from P (leaving along n0) to Q (arriving along n1),
    first spacing d0 by arc length, one geometric ratio."""
    D = float(np.hypot(*(Q - P)))
    a = HERMITE_TANGENT * D
    t = np.linspace(0.0, 1.0, samples) ** 2                 # dense near the wall
    h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
    h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
    curve = (h00[:, None] * P + h10[:, None] * a * n0 + h01[:, None] * Q + h11[:, None] * a * n1)
    s = _arc(curve)
    dist, _ = stretch_one_sided(s[-1], n_nodes, d0)
    nodes = _resample(curve, dist)
    nodes[0], nodes[-1] = P, Q
    return nodes


def build(params):
    """params: camber_pct and thickness_pct (NACA four-digit) or airfoil (a coordinate file name,
    geometry/airfoils.py), reynolds, alpha_deg (recorded only), mesh_level (default medium).
    Returns (geometry, Mesh)."""
    extra = {}
    if "airfoil" in params:
        name = params["airfoil"]
        fx, fy, digest = airfoils.load(name)
        x, y = airfoils.dense_loop(fx, fy, N_GEOMETRY)
        camber = thick = None
        extra = {"airfoil": name, "section_sha256": digest,
                 "trailing_edge_gap": airfoils.trailing_edge_gap(fx, fy)}
    else:
        camber, thick = float(params["camber_pct"]), float(params["thickness_pct"])
        x, y = coordinates(camber, thick, n=N_GEOMETRY)
        extra = {"airfoil": "naca4"}
    reynolds = float(params["reynolds"])
    level = params.get("mesh_level", "medium")
    s = sizes(level)
    d0 = first_cell(reynolds, level)
    nj = s["n_normal"]

    # ---- wall blocks: one array of columns, lower TE -> LE -> upper TE ----
    wall = _wall(x, y, s)
    nw = len(wall)
    tang = np.gradient(wall, axis=0)                         # one-sided at the two TE nodes
    for _ in range(NORMAL_SMOOTHING_PASSES):                  # interior nodes only; the TE keeps its own
        tang[1:-1] = 0.25 * tang[:-2] + 0.5 * tang[1:-1] + 0.25 * tang[2:]
    tang /= np.hypot(tang[:, 0], tang[:, 1])[:, None]
    normal = np.column_stack((-tang[:, 1], tang[:, 0]))      # outward (the wall runs clockwise)
    arc = _arc(wall)
    u = 0.5 * arc / arc[-1] + 0.5 * np.arange(nw) / (nw - 1)
    Q, nQ = _farfield(u)
    Q[0], Q[-1] = (CHORD, -FARFIELD_CHORDS), (CHORD, FARFIELD_CHORDS)
    cols = np.stack([_column(wall[i], normal[i], Q[i], nQ[i], nj, d0) for i in range(nw)])
    k_le = s["n_surf"] - 1
    lower_wall, upper_wall = cols[:k_le + 1], cols[k_le:]    # (n_surf, nj, 2) each

    # ---- wake blocks: columns from the cut y = 0, x = 1 .. 31, to the lines y = +-30 ----
    x_wake = CHORD + stretch_one_sided(X_OUT - CHORD, s["n_wake"], s["ds_te"])[0]
    k = np.arange(len(x_wake))
    dx_wake = np.diff(x_wake, prepend=x_wake[0] - s["ds_te"])  # streamwise spacing at each column
    x_top = CHORD + (X_OUT - CHORD) * (0.5 * (x_wake - CHORD) / (X_OUT - CHORD)
                                      + 0.5 * k / (len(x_wake) - 1))
    lean = (X_OUT - x_wake) / (X_OUT - CHORD)                # 1 at the TE, 0 at the outflow

    def wake(sign, n_te):
        """Columns leaving the cut along the TE normal n_te, turned back to the vertical with
        lean; arriving vertically at (x_top, +-30). n_te leans aft, so neighbours do not cross."""
        out = []
        for xk, dx, xt, w in zip(x_wake, dx_wake, x_top, lean):
            n0 = w * n_te + (1.0 - w) * np.array((0.0, sign))
            n0 /= np.hypot(*n0)
            dy0 = d0 + (dx - s["ds_te"]) / WAKE_ASPECT
            out.append(_column(np.array((xk, 0.0)), n0, np.array((xt, sign * FARFIELD_CHORDS)),
                               np.array((0.0, sign)), nj, dy0))
        return np.stack(out)                                 # (n_wake, nj, 2), x increasing

    upper_wake = wake(1.0, normal[-1])
    lower_wake = wake(-1.0, normal[0])[::-1]                 # x decreasing toward the TE
    upper_wake[0], lower_wake[-1] = upper_wall[-1], lower_wall[0]   # the TE columns, identical

    blocks = []
    for nodes in (lower_wake, lower_wall, upper_wall, upper_wake):
        blk = Block(nodes[:, 0], nodes[-1], nodes[:, -1], nodes[0])
        blk.nodes = nodes
        blocks.append(blk)
    shared = [(0, "right", 1, "left", False), (1, "right", 2, "left", False),
              (2, "right", 3, "left", False), (0, "bottom", 3, "bottom", True)]
    mesh = Mesh.from_blocks(blocks, shared, level=level)
    mesh.add_marker("airfoil", [(1, "bottom"), (2, "bottom")], wall=True)
    mesh.add_marker("farfield", [(0, "left"), (0, "top"), (1, "top"), (2, "top"), (3, "top"),
                                 (3, "right")])

    geometry = {"camber_pct": camber, "thickness_pct": thick, "reynolds": reynolds,
                "alpha_deg": float(params.get("alpha_deg", 0.0)), "chord_m": CHORD,
                "farfield_chords": FARFIELD_CHORDS, "trailing_edge_closed": True,
                "level": level, "first_cell_m": d0, "y_plus": Y_PLUS,
                "nodes": len(mesh.coords), "cells": len(mesh.cells), **extra}
    return geometry, mesh

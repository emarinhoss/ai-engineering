"""Single-wedge mesh for the oblique-shock (V1) and laminar-wedge (V2) cases.

Layout (x right, y up), four blocks, 0 = upstream-lower ... 3 = downstream-upper:

   y_top    +----------------+--------------------------------+
            |  1 upstream-up |  3 downstream-up                |
   y_split  +----------------+--------------------------------+   (lip line, shared)
            |  0 upstream-low|  2 downstream-low  (wedge wall) |
   y = 0    +----------------+  /  <- body: (0,0) to (X_w, X_w tan(theta))
          x_in               0                              X_w

Grid lines are vertical, so the vertical spacing at the wall is d0 / cos(theta) to make the
wall-normal first cell height exactly d0 (Mesh.quality measures it wall-normal).
"""
import math

import numpy as np

from geometry.structured import Block, Mesh, stretch_capped, stretch_one_sided

X_W, X_IN, Y_SPLIT, Y_TOP = 0.15, -0.03, 0.06, 0.20
FACTOR = {"coarse": 1.0 / 1.4, "medium": 1.0, "fine": 1.4}   # node-count factor per level

# Medium level (00_decisions.md section 6). Lengths in metres, counts are nodes.
MEDIUM = {
    "d0": 20e-6,       # body first cell height
    "n_low": 61,       # nodes wall -> lip line
    "n_up": 33,        # nodes lip line -> top
    "n_ups": 25,       # nodes in the upstream column
    "dx_ups": 0.1e-3,  # spacing of the upstream column at the leading edge (= dx0, no jump)
    "dx0": 0.1e-3,     # streamwise first cell at the leading edge
    "dxmax": 1.0e-3,   # streamwise cap
    "n_x": 169,        # nodes along the wedge
}


def _odd(x):
    """Nearest odd integer to x."""
    return 2 * round((x - 1) / 2) + 1


def sizes(level):
    """Sizes for a mesh level: lengths x 1.4 (coarse) or / 1.4 (fine), node counts the inverse."""
    if level not in FACTOR:
        raise ValueError(f"mesh_level must be coarse, medium or fine, got {level!r}")
    nf = FACTOR[level]
    s = dict(MEDIUM)  # copy
    if level != "medium":
        for k in ("d0", "dx_ups", "dx0", "dxmax"):
            s[k] = MEDIUM[k] / nf
        for k in ("n_low", "n_up", "n_ups", "n_x"):
            s[k] = _odd(MEDIUM[k] * nf)
    return s


def build(params):
    """params: theta1_deg (wedge angle), mesh_level (default medium). Returns (geometry, Mesh)."""
    theta = float(params["theta1_deg"])
    level = params.get("mesh_level", "medium")
    s = sizes(level)
    y_tip = X_W * math.tan(math.radians(theta))
    if not 0.0 < y_tip < 0.95 * Y_SPLIT:
        raise ValueError(f"theta1_deg={theta} puts the wedge tip at y={y_tip:.4f}, above the lip line")

    # Streamwise node positions. Downstream: 0.1 mm at the leading edge, growing to the cap.
    x_dn = stretch_capped(X_W, s["n_x"], s["dx0"], s["dxmax"])[0]
    x_up = -stretch_one_sided(-X_IN, s["n_ups"], s["dx_ups"])[0][::-1]     # clustered toward x = 0

    # Heights above the wall at a vertical line whose lower part is L_low long. The lower
    # part grows from d0 but is capped so that it hands over to the upper part with the same
    # spacing; the upper part then grows from that spacing to the top.
    L_up = Y_TOP - Y_SPLIT
    cap = 0.8 * L_up / (s["n_up"] - 1)

    d0_vert = s["d0"] / math.cos(math.radians(theta))   # vertical spacing for wall-normal d0

    def column(L_low):
        low, _ = stretch_capped(L_low, s["n_low"], d0_vert, cap)
        up, _ = stretch_one_sided(L_up, s["n_up"], low[-1] - low[-2])
        return low, up

    low0, up0 = column(Y_SPLIT)               # lines at x_in and x = 0 (wall at y = 0)
    lowW, upW = column(Y_SPLIT - y_tip)       # line at x = X_w (wall at y = y_tip)

    def line(x, y):                           # vertical edge at constant x
        return np.column_stack((np.full(len(y), x), y))

    def row(x, y):                            # edge at constant y
        return np.column_stack((x, np.full(len(x), y)))

    lip_up, lip_dn = row(x_up, Y_SPLIT), row(x_dn, Y_SPLIT)
    inlet_lo, inlet_up = line(X_IN, low0), line(X_IN, Y_SPLIT + up0)
    mid_lo, mid_up = line(0.0, low0), line(0.0, Y_SPLIT + up0)
    out_lo, out_up = line(X_W, y_tip + lowW), line(X_W, Y_SPLIT + upW)
    wall = np.column_stack((x_dn, x_dn * math.tan(math.radians(theta))))

    blocks = [
        Block(row(x_up, 0.0), mid_lo, lip_up, inlet_lo),                      # 0 upstream-low
        Block(lip_up, mid_up, row(x_up, Y_TOP), inlet_up),                    # 1 upstream-up
        Block(wall, out_lo, lip_dn, mid_lo),                                  # 2 downstream-low
        Block(lip_dn, out_up, row(x_dn, Y_TOP), mid_up),                      # 3 downstream-up
    ]
    shared = [(0, "top", 1, "bottom", False), (2, "top", 3, "bottom", False),
              (0, "right", 2, "left", False), (1, "right", 3, "left", False)]
    mesh = Mesh.from_blocks(blocks, shared, level=level)
    mesh.add_marker("body", [(2, "bottom")], wall=True)
    mesh.add_marker("symmetry", [(0, "bottom")])
    mesh.add_marker("inlet", [(0, "left"), (1, "left")])
    mesh.add_marker("top", [(1, "top"), (3, "top")])
    mesh.add_marker("outlet", [(2, "right"), (3, "right")])

    geometry = {"theta1_deg": theta, "X_w": X_W, "x_in": X_IN, "y_split": Y_SPLIT, "y_top": Y_TOP,
                "level": level, "nodes": len(mesh.coords), "cells": len(mesh.cells)}
    return geometry, mesh

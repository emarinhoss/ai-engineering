"""Half-cylinder mesh for the Fay-Riddell stagnation-heating case (V3).

One polar block. Freestream comes from -x, the cylinder centre is the origin, so the upstream
stagnation point is (-R, 0). A node at angle phi (from the stagnation point toward +y) and
radius r sits at (-r cos phi, r sin phi). phi runs 0 .. 100 deg, r from R to
r_out(phi) = R (2.0 + 1.5 sin^2 phi).

Block edges: bottom = wall arc (phi increasing), right = phi = 100 deg ray, top = outer arc,
left = stagnation line (phi = 0).
"""

import numpy as np

from geometry.structured import Block, Mesh, stretch_one_sided
from physics.heating import billig_standoff

PHI_MAX_DEG = 100.0
R_OUT_FORMULA = "R (2.0 + 1.5 sin^2 phi)"
# level -> (first cell [m], nodes per direction)
LEVELS = {"coarse": (8e-6, 57), "medium": (4e-6, 81), "fine": (2e-6, 113)}


def r_out(phi, R):
    return R * (2.0 + 1.5 * np.sin(phi) ** 2)


def build(params):
    """params: radius_m (default 0.010), mesh_level (default medium), mach (default 4.0, only
    used for the Billig stand-off estimate). Returns (geometry, Mesh)."""
    R = float(params.get("radius_m", 0.010))
    level = params.get("mesh_level", "medium")
    if level not in LEVELS:
        raise ValueError(f"mesh_level must be coarse, medium or fine, got {level!r}")
    d0, n = LEVELS[level]

    phi = np.radians(np.linspace(0.0, PHI_MAX_DEG, n))
    # Radial positions per phi line: first cell d0 everywhere, growth ratio varies with the length.
    s = np.array([R + stretch_one_sided(r_out(p, R) - R, n, d0)[0] for p in phi])   # (n_phi, n_r)
    nodes = np.stack((-s * np.cos(phi)[:, None], s * np.sin(phi)[:, None]), axis=2)  # (n_phi, n_r, 2)

    # Block builds its own Coons fill from the edges; replace it with the exact polar nodes.
    blk = Block(nodes[:, 0], nodes[-1], nodes[:, -1], nodes[0])
    blk.nodes = nodes
    mesh = Mesh.from_blocks([blk], [], level=level)
    mesh.add_marker("wall", [(0, "bottom")], wall=True)
    mesh.add_marker("symmetry", [(0, "left")])
    mesh.add_marker("farfield", [(0, "top")])
    mesh.add_marker("outlet", [(0, "right")])

    M = float(params.get("mach", 4.0))
    geometry = {"radius_m": R, "phi_max_deg": PHI_MAX_DEG, "r_out": R_OUT_FORMULA, "level": level,
                "nodes": len(mesh.coords), "cells": len(mesh.cells), "first_cell_m": d0,
                "mach": M, "delta_over_R": billig_standoff(M)}
    return geometry, mesh

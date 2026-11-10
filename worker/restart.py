"""Warm start for airfoil2d: map a donor's SU2 ASCII restart onto this case's mesh nodes.

SU2 (8.2.0, RESTART_ASCII) writes restart_flow.csv: a header line `"PointID","x","y",<fields>` and one
row per mesh node. map_restart gives each node of the new mesh the row of the nearest donor node in
(x, y) and writes the text of solution_flow.csv, which SU2 reads when RESTART_SOL= YES. On the same
mesh the nearest donor node of every node is itself, so one code path serves both cases.
"""
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


def read_su2_coords(mesh_path):
    """(n, 2) array of the node coordinates of an SU2 ASCII mesh, in file order (= node index)."""
    lines = Path(mesh_path).read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("NPOIN="))
    n = int(lines[start].split("=")[1].split()[0])
    rows = [line.split()[:2] for line in lines[start + 1:start + 1 + n]]
    return np.array(rows, dtype=float)


def map_restart(donor_text, coords):
    """(solution_flow.csv text, largest nearest-neighbour distance) for a mesh with node `coords`.

    Header and column order are the donor's. PointID, x and y are this mesh's; every other column
    is copied from the nearest donor node."""
    header, *body = [line for line in donor_text.splitlines() if line.strip()]
    names = [c.strip().strip('"') for c in header.split(",")]
    for needed in ("PointID", "x", "y"):
        if needed not in names:
            raise ValueError(f"donor restart has no {needed!r} column (header: {header[:80]})")
    donor = np.array([[float(v) for v in row.split(",")] for row in body])
    if donor.shape[1] != len(names):
        raise ValueError("donor restart rows and header differ in column count")
    ix, iy, ip = names.index("x"), names.index("y"), names.index("PointID")
    dist, nearest = cKDTree(donor[:, [ix, iy]]).query(coords)
    out = donor[nearest].copy()                       # a copy of the rows, one per new node
    out[:, ip] = np.arange(len(coords))
    out[:, ix], out[:, iy] = coords[:, 0], coords[:, 1]
    lines = [header]
    for k, row in enumerate(out):
        lines.append(",".join(str(k) if j == ip else repr(float(v)) for j, v in enumerate(row)))
    return "\n".join(lines) + "\n", float(dist.max())

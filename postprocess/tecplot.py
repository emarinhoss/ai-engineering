"""Read SU2's Tecplot ASCII output (surface_flow.dat, flow.dat) and the mesh node coordinates.

SU2's CSV writers keep only the conservative variables, so surface and volume fields (Pressure,
Mach, Heat_Flux, ...) are read from Tecplot ASCII. Pure numpy, no pandas.

File layout (POINT packing, one node per line, then one element per line):
    TITLE = "..."
    VARIABLES = "x","y","Density",...
    ZONE NODES= 169, ELEMENTS= 168, DATAPACKING=POINT, ZONETYPE=FELINESEG
    <NODES lines, one value per variable>
    <ELEMENTS lines, 1-based node indices>
A file can hold several ZONE blocks; all are read.
"""
import json
import re
from pathlib import Path

import numpy as np

NODES_PER_ELEMENT = {"FELINESEG": 2, "FETRIANGLE": 3, "FEQUADRILATERAL": 4,
                     "FETETRAHEDRON": 4, "FEBRICK": 8}


def _zone_header(line):
    """NODES, ELEMENTS and ZONETYPE from a ZONE line."""
    try:
        nodes = int(re.search(r"NODES\s*=\s*(\d+)", line, re.IGNORECASE).group(1))
        elements = int(re.search(r"ELEMENTS\s*=\s*(\d+)", line, re.IGNORECASE).group(1))
        zonetype = re.search(r"ZONETYPE\s*=\s*(\w+)", line, re.IGNORECASE).group(1).upper()
    except AttributeError:
        raise ValueError(f"cannot read NODES, ELEMENTS and ZONETYPE from: {line.strip()!r}")
    packing = re.search(r"DATAPACKING\s*=\s*(\w+)", line, re.IGNORECASE)
    if packing and packing.group(1).upper() != "POINT":
        raise ValueError(f"only DATAPACKING=POINT is supported, got {packing.group(1)}")
    if zonetype not in NODES_PER_ELEMENT:
        raise ValueError(f"unsupported ZONETYPE {zonetype}")
    return nodes, elements, zonetype


def _take(lines, pos, count):
    """Collect `count` whitespace-separated tokens starting at line `pos`; return (tokens, next pos)."""
    tokens = []
    while len(tokens) < count:
        if pos >= len(lines):
            raise ValueError("file ends before the zone data is complete")
        tokens.extend(lines[pos].split())
        pos += 1
    if len(tokens) != count:
        raise ValueError("zone data does not match the NODES/ELEMENTS counts in the ZONE line")
    return tokens, pos


def read_tecplot_ascii(path):
    """Read every zone of a Tecplot ASCII file.

    Returns {"variables": [names], "data": {name: array over all zones' nodes},
             "zone": int array (zone index per node),
             "elements": [(n_nodes_in_zone, int array (n_elem, nodes_per_elem), 0-based)],
             "zonetype": [str]}
    """
    lines = Path(path).read_text().splitlines()
    variables, pos = None, 0
    while pos < len(lines) and not lines[pos].lstrip().upper().startswith("ZONE"):
        if lines[pos].lstrip().upper().startswith("VARIABLES"):
            variables = re.findall(r'"([^"]*)"', lines[pos])
        pos += 1
    if not variables:
        raise ValueError(f"{path}: no VARIABLES line before the first ZONE")

    nvar = len(variables)
    blocks, zone_ids, elements, zonetypes = [], [], [], []
    while pos < len(lines):
        if not lines[pos].lstrip().upper().startswith("ZONE"):
            if lines[pos].strip():
                raise ValueError(f"{path}: unexpected line {pos + 1}: {lines[pos].strip()[:60]!r}")
            pos += 1
            continue
        n_nodes, n_elem, zonetype = _zone_header(lines[pos])
        npe = NODES_PER_ELEMENT[zonetype]
        tokens, pos = _take(lines, pos + 1, n_nodes * nvar)
        blocks.append(np.array(tokens, dtype=float).reshape(n_nodes, nvar))
        tokens, pos = _take(lines, pos, n_elem * npe)
        connectivity = np.array(tokens, dtype=int).reshape(n_elem, npe) - 1
        if n_elem and (connectivity.min() < 0 or connectivity.max() >= n_nodes):
            raise ValueError(f"{path}: element node index outside 1..{n_nodes}")
        zone_ids.append(np.full(n_nodes, len(blocks) - 1, dtype=int))
        elements.append((n_nodes, connectivity))
        zonetypes.append(zonetype)
    if not blocks:
        raise ValueError(f"{path}: no ZONE found")

    table = np.vstack(blocks)
    return {"variables": variables,
            "data": {name: table[:, k] for k, name in enumerate(variables)},
            "zone": np.concatenate(zone_ids), "elements": elements, "zonetype": zonetypes}


def read_su2_points(path):
    """Node coordinates of a 2D SU2 mesh as an (N, 2) array indexed by node id."""
    lines = Path(path).read_text().splitlines()
    ndime = 2
    for k, line in enumerate(lines):
        key = line.split("=")[0].strip().upper()
        if key == "NDIME":
            ndime = int(line.split("=")[1])
            if ndime != 2:
                raise ValueError("only 2D meshes are supported")
        elif key == "NPOIN":
            n = int(line.split("=")[1].split()[0])
            rows = np.array([row.split() for row in lines[k + 1:k + 1 + n]], dtype=float)
            if rows.shape != (n, ndime + 1):
                raise ValueError(f"{path}: NPOIN rows should have {ndime + 1} columns (x y id)")
            points = np.zeros((n, ndime))
            points[rows[:, ndime].astype(int)] = rows[:, :ndime]
            return points
    raise ValueError(f"{path}: no NPOIN section")


def _neighbours(selected, elements, offsets):
    """For each selected row, the selected rows joined to it by a line element."""
    chosen = {int(r) for r in selected}
    neighbours = {r: [] for r in chosen}
    for (_, conn), offset in zip(elements, offsets):
        for a, b in conn + offset:
            if a in chosen and b in chosen:
                neighbours[int(a)].append(int(b))
                neighbours[int(b)].append(int(a))
    return neighbours


def surface_nodes_for_marker(data, mesh_markers_json, marker, tol=1e-7, mesh_path=None):
    """Rows of the surface file (a read_tecplot_ascii result) that lie on `marker`, in order.

    mesh_markers_json is the path of mesh_markers.json (or the loaded dict): it lists the mesh
    node ids per marker. The coordinates of those ids come from mesh.su2 (`mesh_path`, default
    the mesh.su2 beside the json) and are matched to the rows' x, y; the match must be within
    `tol` metres. The rows are returned along the marker by walking the line elements, starting
    at the end with the smaller x. Raises ValueError if any marker node has no surface row.
    """
    if isinstance(mesh_markers_json, dict):
        markers = mesh_markers_json
        if mesh_path is None:
            raise ValueError("mesh_path is needed when mesh_markers_json is a dict")
    else:
        markers = json.loads(Path(mesh_markers_json).read_text())
        if mesh_path is None:
            mesh_path = Path(mesh_markers_json).parent / "mesh.su2"
    if marker not in markers or not isinstance(markers[marker], list):
        raise ValueError(f"marker {marker!r} not in mesh markers")

    points = read_su2_points(mesh_path)[markers[marker]]            # (M, 2)
    xy = np.column_stack([data["data"]["x"], data["data"]["y"]])    # (S, 2)
    rows = np.empty(len(points), dtype=int)
    for k, pt in enumerate(points):
        dist = np.hypot(xy[:, 0] - pt[0], xy[:, 1] - pt[1])
        rows[k] = np.argmin(dist)
        if dist[rows[k]] > tol:
            raise ValueError(f"marker {marker!r}: mesh node {markers[marker][k]} at "
                             f"({pt[0]:.6g}, {pt[1]:.6g}) has no surface row within {tol:g} m")
    rows = np.unique(rows)

    offsets = np.cumsum([0] + [n for n, _ in data["elements"]])[:-1]
    neighbours = _neighbours(rows, data["elements"], offsets)
    # Walk from an end (a row with one neighbour, lowest x first); a closed loop starts anywhere.
    ordered, seen = [], set()
    ends = sorted((r for r in neighbours if len(neighbours[r]) == 1),
                  key=lambda r: (xy[r, 0], xy[r, 1]))
    for start in ends + sorted(neighbours, key=lambda r: (xy[r, 0], xy[r, 1])):
        if start in seen:
            continue
        current = start
        while current is not None:
            seen.add(current)
            ordered.append(current)
            current = next((n for n in neighbours[current] if n not in seen), None)
    return np.array(ordered, dtype=int)

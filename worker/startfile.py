"""Start files for experiment W1 (docs/specs/task11_fno_exploration.md; task W1.1).

SU2 8.2.0 with RESTART_ASCII writes restart_flow.csv: a header `"PointID","x","y","Pressure",
"Velocity_x","Velocity_y","Nu_Tilde"` and one row per mesh node in node order. With
INC_NONDIM= INITIAL_VALUES the stored values are already non-dimensional: velocity divided by U_inf,
pressure divided by rho U_inf^2, and Nu_Tilde divided by U_inf c. The rule's scaling (velocity by
U_inf, pressure by rho U_inf^2, nu_tilde by nu) is then the identity for the first two and a
multiplication by the Reynolds number U_inf c / nu for Nu_Tilde. Measured on the E0 restart file of
pool design 1 at 6 deg: the far-field velocity is (0.9947, 0.1030), close to (cos 6, sin 6).

Every coarse airfoil2d mesh has the same node count and ordering, so a start file is written node by
node with this case's own coordinates; no interpolation.
"""
import numpy as np

FIELDS = ("Pressure", "Velocity_x", "Velocity_y", "Nu_Tilde")


def read_restart(text):
    """(header names, (n, len(header)) float array) of a restart_flow.csv text."""
    lines = text.strip().splitlines()
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    data = np.array([[float(v) for v in line.split(",")] for line in lines[1:]])
    if data.shape[1] != len(header):
        raise ValueError(f"restart rows have {data.shape[1]} columns, header has {len(header)}")
    if not np.array_equal(data[:, 0], np.arange(len(data))):
        raise ValueError("restart PointID column is not 0, 1, 2, ... in order")
    return header, data


def fields(header, data):
    """(n, 4) array of the four solution fields, in FIELDS order."""
    return data[:, [header.index(f) for f in FIELDS]]


def scale(f, reynolds):
    """SU2's non-dimensional fields -> the rule's scaling (only Nu_Tilde changes: times Re)."""
    out = np.array(f, dtype=float)
    out[:, 3] *= reynolds
    return out


def unscale(f, reynolds):
    """Inverse of scale, for a case at this Reynolds number; a negative Nu_Tilde is set to zero."""
    out = np.array(f, dtype=float)
    out[:, 3] = np.maximum(out[:, 3], 0.0) / reynolds
    return out


def write_solution(coords, f):
    """Text of solution_flow.csv: PointID, this mesh's x and y, then the four fields."""
    coords, f = np.asarray(coords, dtype=float), np.asarray(f, dtype=float)
    if len(coords) != len(f):
        raise ValueError(f"{len(f)} field rows for a mesh of {len(coords)} nodes")
    head = ",".join(f'"{h}"' for h in ("PointID", "x", "y", *FIELDS))
    rows = [f"{i}, " + ", ".join(f"{v:.15e}" for v in (*coords[i], *f[i])) for i in range(len(f))]
    return head + "\n" + "\n".join(rows) + "\n"

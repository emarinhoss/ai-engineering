"""Stand-in for SU2_CFD in tests: python tests/fake_su2.py case.cfg

Reads ITER, CONV_FILENAME, SURFACE_FILENAME, VOLUME_FILENAME and OUTPUT_FILES from the config and
writes a history.csv with SU2-like quoted headers, a Tecplot ASCII surface_flow.dat (always) and a
small Tecplot flow.dat (when TECPLOT_ASCII is in OUTPUT_FILES), as SU2 v8.2.0 does. Environment
switches: FAKE_SU2_SLEEP (seconds), FAKE_SU2_EXIT (exit code), FAKE_SU2_NAN (non-empty: NaN residuals).

The surface file is physically consistent, so postprocess.metrics.compute works on it. It has one row
per mesh node (read from mesh.su2 and mesh_markers.json beside the config) of the plotted markers:
body (wedge, inlet2r), wall (cylinder), plus cowl and outlet_duct for the inlet. Line elements are
the mesh's own marker lines. Wall rows: rho = 0.05, p = 3000 Pa, velocity 0, Heat_Flux positive.
Throat-plane rows (inlet): rho = 0.06, p = 4000 Pa, 1000 m/s along the duct axis (supersonic).
Everywhere Momentum = rho V, Energy = p/(gamma-1) + rho |V|^2/2, T = p/(rho R), Mach = |V|/a.
Without a mesh next to the config it writes a 10-segment line with the wall state.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))      # run as a script: find physics/

from physics.constants import GAMMA, R_AIR, sutherland_mu
from postprocess.surface import freestream
from postprocess.tecplot import read_su2_points

VARIABLES = ["x", "y", "Density", "Momentum_x", "Momentum_y", "Energy", "Pressure", "Temperature",
             "Mach", "Pressure_Coefficient", "Velocity_x", "Velocity_y", "Laminar_Viscosity",
             "Skin_Friction_Coefficient_x", "Skin_Friction_Coefficient_y", "Heat_Flux", "Y_Plus"]


def read_config(path):
    cfg = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("%") and "=" in line:
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip()
    return cfg


# Fake flow states (SI): rho, p, speed. Walls are at rest; the throat plane is supersonic.
WALL_RHO, WALL_P = 0.05, 3000.0
DUCT_RHO, DUCT_P, DUCT_SPEED = 0.06, 4000.0, 1000.0
PLOTTED = {"inlet2r": ("body", "cowl", "outlet_duct"), "wedge": ("body",), "cylinder": ("wall",)}


def flow_columns(x, y, rho, p, u, v, p_inf=None, rho_inf=None, U_inf=None):
    """Consistent Tecplot columns for nodes with density rho, pressure p, velocity (u, v) (arrays).

    Momentum = rho V, Energy = p/(gamma-1) + rho |V|^2/2, T = p/(rho R), Mach = |V|/sqrt(gamma p/rho),
    Heat_Flux = 1e5 (1 + x) W/m^2 (positive, into the wall), Skin_Friction_x = 1e-3, Y_Plus = 0.5.
    """
    rho, p, u, v = (np.asarray(a, float) for a in (rho, p, u, v))
    speed2 = u**2 + v**2
    T = p / (rho * R_AIR)
    cp = 0.0 * p if p_inf is None else (p - p_inf) / (0.5 * rho_inf * U_inf**2)
    return {"x": np.asarray(x, float), "y": np.asarray(y, float), "Density": rho,
            "Momentum_x": rho * u, "Momentum_y": rho * v,
            "Energy": p / (GAMMA - 1.0) + 0.5 * rho * speed2, "Pressure": p, "Temperature": T,
            "Mach": np.sqrt(speed2 / (GAMMA * p / rho)), "Pressure_Coefficient": cp,
            "Velocity_x": u, "Velocity_y": v,
            "Laminar_Viscosity": np.array([sutherland_mu(t) for t in T]),
            "Skin_Friction_Coefficient_x": np.full(len(rho), 1.0e-3),
            "Skin_Friction_Coefficient_y": np.zeros(len(rho)),
            "Heat_Flux": 1.0e5 * (1.0 + np.asarray(x, float)), "Y_Plus": np.full(len(rho), 0.5)}


def marker_lines(mesh_path):
    """{marker: [(node a, node b), ...]} read from the MARKER_TAG / MARKER_ELEMS blocks of mesh.su2."""
    lines = Path(mesh_path).read_text().splitlines()
    out, k = {}, 0
    while k < len(lines):
        if lines[k].startswith("MARKER_TAG"):
            tag = lines[k].split("=")[1].strip()
            n = int(lines[k + 1].split("=")[1])
            out[tag] = [tuple(int(t) for t in lines[k + 2 + i].split()[1:3]) for i in range(n)]
            k += 2 + n
        else:
            k += 1
    return out


def surface_from_mesh(case_dir):
    """(columns, elements) of the surface file for the plotted markers of the case, or None."""
    case = Path(case_dir)
    if not all((case / f).exists() for f in ("mesh.su2", "mesh_markers.json", "params.json")):
        return None
    params = json.loads((case / "params.json").read_text())
    markers = json.loads((case / "mesh_markers.json").read_text())
    names = [m for m in PLOTTED.get(params["family"], ()) if m in markers]
    if not names:
        return None
    points, lines = read_su2_points(case / "mesh.su2"), marker_lines(case / "mesh.su2")
    ids = list(dict.fromkeys(i for m in names for i in markers[m]))      # unique node ids, in order
    row = {node: k for k, node in enumerate(ids)}
    elements = [(row[a] + 1, row[b] + 1) for m in names for a, b in lines[m]]    # 1-based
    xy = points[ids]
    on_duct = np.isin(ids, markers.get("outlet_duct", [])) if "outlet_duct" in names else np.zeros(len(ids), bool)
    theta = np.radians(json.loads((case / "geometry.json").read_text()).get("theta_t_deg", 0.0))
    speed = np.where(on_duct, DUCT_SPEED, 0.0)
    fs = freestream(params)
    cols = flow_columns(xy[:, 0], xy[:, 1], np.where(on_duct, DUCT_RHO, WALL_RHO),
                        np.where(on_duct, DUCT_P, WALL_P), speed * np.cos(theta), speed * np.sin(theta),
                        fs["p"], fs["rho"], fs["U"])
    return cols, elements


def write_tecplot(path, x, y, zonetype, elements, heat_flux=1.0e5, columns=None):
    """Tecplot ASCII file, one zone, the full SU2 variable list. `elements` is 1-based.
    `columns` (name -> array) replaces the placeholder columns (all 1.0, Heat_Flux = heat_flux)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    cols = {name: np.full(len(x), 1.0) for name in VARIABLES}
    cols.update(x=x, y=y, Heat_Flux=np.full(len(x), float(heat_flux)))
    cols.update(columns or {})
    columns = cols
    with open(path, "w") as f:
        f.write('TITLE = "Visualization of the solution"\n')
        f.write("VARIABLES = " + ",".join(f'"{v}"' for v in VARIABLES) + "\n")
        f.write(f"ZONE NODES= {len(x)}, ELEMENTS= {len(elements)}, DATAPACKING=POINT, "
                f"ZONETYPE={zonetype}\n")
        f.writelines("\t".join(f"{columns[v][k]:.9e}" for v in VARIABLES) + "\t\n"
                     for k in range(len(x)))
        f.writelines(" ".join(str(i) for i in element) + "\n" for element in elements)


def main(argv):
    if "--help" in argv:
        print("SU2 vFAKE (fake_su2) for tests, not a real solver")
        print("Usage: fake_su2.py case.cfg")
        return 0
    cfg = read_config(argv[-1])
    if os.environ.get("FAKE_SU2_SLEEP"):
        time.sleep(float(os.environ["FAKE_SU2_SLEEP"]))

    names = ["Inner_Iter", "rms[Rho]", "rms[RhoU]", "rms[RhoV]", "rms[RhoE]", "CD", "CL", "CFL"]
    if "MARKER_ISOTHERMAL" in cfg:
        names.append("maxHF")
    if "MARKER_ANALYZE" in cfg:
        names.append("Avg_TotalPress")

    n = max(2, min(int(cfg.get("ITER", 100)), 400))
    nan = bool(os.environ.get("FAKE_SU2_NAN"))
    rows = []
    for k in range(n):
        res = float("nan") if nan else -2.0 - 6.0 * k / (n - 1)     # falls 6 orders of magnitude
        row = [k, res, res - 0.1, res - 0.1, res - 0.2, 0.1, 0.0, 10.0]
        row += [1.0e5] * (len(names) - len(row))
        rows.append(", ".join(str(v) for v in row))
    with open(cfg.get("CONV_FILENAME", "history") + ".csv", "w") as f:
        f.write(",".join(f'"{h}"' for h in names) + "\n" + "\n".join(rows) + "\n")
    surface = surface_from_mesh(".")
    if surface:
        cols, elements = surface
    else:                                                      # no mesh beside the config: a plain line
        nodes = np.linspace(0.0, 0.1, 11)
        cols = flow_columns(nodes, 0.2 * nodes, np.full(11, WALL_RHO), np.full(11, WALL_P),
                            np.zeros(11), np.zeros(11))
        elements = [(i + 1, i + 2) for i in range(10)]
    write_tecplot(cfg.get("SURFACE_FILENAME", "surface_flow") + ".dat", cols["x"], cols["y"],
                  "FELINESEG", elements, columns=cols)
    if "TECPLOT_ASCII" in [t.strip() for t in cfg.get("OUTPUT_FILES", "").strip("()").split(",")]:
        gx, gy = np.meshgrid(np.linspace(0.0, 0.1, 5), np.linspace(0.0, 0.1, 5))
        quads = [(5 * j + i + 1, 5 * j + i + 2, 5 * (j + 1) + i + 2, 5 * (j + 1) + i + 1)
                 for j in range(4) for i in range(4)]
        write_tecplot(cfg.get("VOLUME_FILENAME", "flow") + ".dat", gx.ravel(), gy.ravel(),
                      "FEQUADRILATERAL", quads, heat_flux=0.0)
    print(f"fake_su2: wrote {n} iterations")
    return int(os.environ.get("FAKE_SU2_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Stand-in for SU2_CFD in tests: python tests/fake_su2.py case.cfg

Reads ITER, CONV_FILENAME, SURFACE_FILENAME, VOLUME_FILENAME and OUTPUT_FILES from the config and
writes a history.csv with SU2-like quoted headers, a Tecplot ASCII surface_flow.dat (always) and a
small Tecplot flow.dat (when TECPLOT_ASCII is in OUTPUT_FILES), as SU2 v8.2.0 does. Environment switches: FAKE_SU2_SLEEP (seconds), FAKE_SU2_EXIT (exit
code), FAKE_SU2_NAN (non-empty: NaN residuals).
"""
import os
import sys
import time
from pathlib import Path

import numpy as np

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


def write_tecplot(path, x, y, zonetype, elements, heat_flux=1.0e5):
    """Tecplot ASCII file, one zone, the full SU2 variable list. `elements` is 1-based."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    columns = {name: np.full(len(x), 1.0) for name in VARIABLES}
    columns.update(x=x, y=y, Heat_Flux=np.full(len(x), float(heat_flux)))
    with open(path, "w") as f:
        f.write('TITLE = "Visualization of the solution"\n')
        f.write("VARIABLES = " + ",".join(f'"{v}"' for v in VARIABLES) + "\n")
        f.write(f"ZONE NODES= {len(x)}, ELEMENTS= {len(elements)}, DATAPACKING=POINT, "
                f"ZONETYPE={zonetype}\n")
        f.writelines("\t".join(f"{columns[v][k]:.6e}" for v in VARIABLES) + "\t\n"
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
    nodes = np.linspace(0.0, 0.1, 11)                          # a 10-segment wall line
    write_tecplot(cfg.get("SURFACE_FILENAME", "surface_flow") + ".dat", nodes, 0.2 * nodes,
                  "FELINESEG", [(i + 1, i + 2) for i in range(10)])
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

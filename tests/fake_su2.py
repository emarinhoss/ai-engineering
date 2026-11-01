"""Stand-in for SU2_CFD in tests: python tests/fake_su2.py case.cfg

Reads ITER, CONV_FILENAME and SURFACE_FILENAME from the config and writes a history.csv with
SU2-like quoted headers. Environment switches: FAKE_SU2_SLEEP (seconds), FAKE_SU2_EXIT (exit
code), FAKE_SU2_NAN (non-empty: NaN residuals).
"""
import os
import sys
import time
from pathlib import Path


def read_config(path):
    cfg = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("%") and "=" in line:
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip()
    return cfg


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
    with open(cfg.get("SURFACE_FILENAME", "surface_flow") + ".csv", "w") as f:
        f.write('"PointID","x","y","Heat_Flux"\n')
    print(f"fake_su2: wrote {n} iterations")
    return int(os.environ.get("FAKE_SU2_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Task 9 designs: python -m designs.make_pool3r

Two scrambled 6-d Sobol sets over the inlet3r inputs (docs/specs/task9_inlet3r_envelope.md
section 8), each the first 160 of 256 points (random_base2(8)):
  designs/pool3r_hf_sobol160.csv  seed 0: Navier-Stokes and Euler (the nested high-fidelity set)
  designs/pool3r_lf_sobol160.csv  seed 1: Euler only (the extra low-fidelity set)
Each row also says whether the physics gates accept the point (gate_ok) and, if not, why. Gated
points are kept in the file and not run, as for the two-ramp pool.
"""
from pathlib import Path

from scipy.stats import qmc

from physics.gates import check

NAMES = ("theta1_deg", "theta2_deg", "theta3_deg", "mach", "altitude_km", "T_wall_K")
LOW = (3.0, 3.0, 3.0, 3.5, 28.0, 300.0)
HIGH = (10.0, 10.0, 10.0, 4.5, 35.0, 600.0)
N_POINTS = 160
HERE = Path(__file__).parent


def points(seed, n=N_POINTS):
    unit = qmc.Sobol(d=len(NAMES), scramble=True, seed=seed).random_base2(8)[:n]
    return qmc.scale(unit, LOW, HIGH).round(6)


def params_of(row, solver="NAVIER_STOKES"):
    p = {"family": "inlet3r", **{k: float(v) for k, v in zip(NAMES, row)}, "solver": solver,
         "mesh_level": "medium", "max_iter": 8000, "tag": "pool3r"}
    return p


def write(path, seed):
    lines = ["index," + ",".join(NAMES) + ",gate_ok,gate_errors"]
    for i, row in enumerate(points(seed)):
        errors = check(params_of(row))
        lines.append(f"{i}," + ",".join(f"{v:.6f}" for v in row) + f",{int(not errors)},\"{'; '.join(errors)}\"")
    Path(path).write_text("\n".join(lines) + "\n")
    return sum(1 for line in lines[1:] if ",1,\"" in line)


if __name__ == "__main__":
    for name, seed in (("pool3r_hf_sobol160.csv", 0), ("pool3r_lf_sobol160.csv", 1)):
        ok = write(HERE / name, seed)
        print(f"wrote designs/{name}: {N_POINTS} points, {ok} pass the gates")

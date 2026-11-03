"""The "metrics" block of a run record: objectives and diagnostics (00_decisions.md section 3).

compute(case_dir) reads surface_flow.dat (through postprocess.surface), history.csv, params.json
and geometry.json from a case directory.

Inlet (family inlet2r): on the throat plane (marker outlet_duct), with trapezoid weights w along
the plane, unit normal n = duct axis and mass flux phi = rho (u n_x + v n_y):
    recovery_throat = sum(w phi p0) / sum(w phi) / p0_inf
    recovery_total  = sum(w phi p0 pi_NS(M)) / sum(w phi) / p0_inf      (the objective)
with p0 = p (1 + 0.2 M^2)^3.5 and pi_NS the normal-shock total pressure ratio (1 for M <= 1).
Heating: peak of q (into the wall) on body_ramp2 and the heat load on it, both without nodes
within 2 mm of the throat plane; the peak on cowl_inner without the first 2 mm from the lip.
Three-ramp inlet (family inlet3r, Task 9): the same definitions, with the heating window on the last
ramp, body_ramp3 (x >= X2).
Euler runs have no heat flux: those fields are None. For an Euler run of inlet3r, q_peak_lf_W_m2
is the low-fidelity peak heating of Task 9: Eckert's flat-plate relation at every node of the same
window, with the Euler wall state (M, T, p) as the edge state and the arc length from the leading
edge as x. Wedge and cylinder report what applies.
"""
import math
from pathlib import Path

import numpy as np

from physics.heating import eckert_flat_plate
from physics.shock import normal
from postprocess import history, surface
from postprocess.tecplot import read_tecplot_ascii

EXCLUDE_M = 2e-3          # m, nodes this close to the throat plane or the cowl lip are skipped
CROSSCHECK_TOL = 0.005    # SU2 AVG_TOTALPRESS against recovery_throat * p0_inf (gate X1)


def weights(s):
    """Trapezoid weights for nodes at positions s: sum(w f) = integral of f ds."""
    w = np.zeros(len(s))
    ds = np.diff(s)
    w[:-1] += 0.5 * ds
    w[1:] += 0.5 * ds
    return w


def pi_normal_shock(M):
    """Total pressure ratio across a normal shock at Mach M (1 for M <= 1), per node."""
    return np.array([normal(max(float(m), 1.0))["p0_ratio"] for m in np.atleast_1d(M)])


def throat_profile(surf, geometry):
    """Arrays on the throat plane: s, w, phi (mass flux through the plane), p0, M."""
    t = surf["outlet_duct"]
    theta = math.radians(geometry["theta_t_deg"])
    phi = t["rho"] * (t["u"] * math.cos(theta) + t["v"] * math.sin(theta))
    return {"s": t["s"], "w": weights(t["s"]), "phi": phi,
            "p0": surface.stagnation_pressure(t["p"], t["M"]), "M": t["M"]}


def _require(surf, *names):
    """Raise a clear error if a marker the metric needs is not in the surface file."""
    missing = [n for n in names if n not in surf]
    if missing:
        raise ValueError(f"surface_flow.dat has no node of marker(s) {missing}; "
                         f"markers found: {sorted(surf)}")


def _su2_avg_totalpress(case):
    """Last value of the history column with "totalpress" in its name, or None."""
    path = Path(case) / "history.csv"
    if not path.exists():
        return None
    cols = history.load(path)
    names = [c for c in cols if "totalpress" in c.lower()]
    if len(names) != 1 or not np.isfinite(cols[names[0]][-1]):
        return None
    return float(cols[names[0]][-1])


def _inlet_recovery(case, surf, geometry, fs):
    t = throat_profile(surf, geometry)
    flow = float(np.sum(t["w"] * t["phi"]))                  # kg/s per metre depth
    if not flow > 0.0:
        raise ValueError(f"no net mass flow through the throat plane (sum w phi = {flow:.6g})")

    def mass_avg(f):
        return float(np.sum(t["w"] * t["phi"] * f) / flow)

    recovery_throat = mass_avg(t["p0"]) / fs["p0"]
    mach_avg = mass_avg(t["M"])
    out = {"recovery_throat": recovery_throat,
           "recovery_total": mass_avg(t["p0"] * pi_normal_shock(t["M"])) / fs["p0"],
           "recovery_total_bulk": recovery_throat * float(pi_normal_shock(mach_avg)[0]),
           "mach_throat_massavg": mach_avg,
           "capture_ratio": flow / (fs["rho"] * fs["U"] * geometry["P"][1])}
    avg = _su2_avg_totalpress(case)
    out["su2_avg_totalpress_Pa"] = avg
    out["su2_crosscheck_pass"] = (None if avg is None else
                                  bool(abs(avg / (recovery_throat * fs["p0"]) - 1.0) <= CROSSCHECK_TOL))
    return out


def last_ramp(geometry):
    """Marker of the ramp that ends at the throat: body_ramp3 for inlet3r (geometry has X2), else body_ramp2."""
    return "body_ramp3" if "X2" in geometry else "body_ramp2"


def ramp2_window(surf, geometry):
    """Body nodes of the last ramp that the heating objective uses (ramp 2 of inlet2r: x >= X1; ramp 3
    of inlet3r: x >= X2), nodes within 2 mm of the throat plane left out. Also used for the heat-flux
    profiles of Task 4c (analysis/profiles.py)."""
    theta = math.radians(geometry["theta_t_deg"])
    n = np.array([math.cos(theta), math.sin(theta)])
    body = surf[last_ramp(geometry)]
    dist_to_throat = np.abs((body["x"] - geometry["E_body"][0]) * n[0]
                            + (body["y"] - geometry["E_body"][1]) * n[1])
    keep = dist_to_throat > EXCLUDE_M
    return {k: v[keep] for k, v in body.items()}


def eckert_window(surf, geometry, T_wall):
    """Low-fidelity heat flux on the heating window of inlet3r: (x, q) with q from eckert_flat_plate at
    every node, edge state = the (Euler) wall state, and the flat-plate length = distance along the
    body from the leading edge O: |C1 - O| + |C2 - C1| + |node - C2|. (The marker's own arc length
    "s" restarts at C2, so it is not used.)"""
    w = ramp2_window(surf, geometry)
    C1 = np.array([geometry["X1"], geometry["X1"] * math.tan(math.radians(geometry["theta1_deg"]))])
    C2 = np.array(geometry["C2"])
    s_le = np.linalg.norm(C1) + np.linalg.norm(C2 - C1) + np.hypot(w["x"] - C2[0], w["y"] - C2[1])
    q = np.array([eckert_flat_plate(M, T, p, T_wall, s) for M, T, p, s in zip(w["M"], w["T"], w["p"], s_le)])
    return w["x"], q


def _inlet_heating(surf, geometry):
    """q_peak, x_q_peak, heat load on ramp 2 and q_peak_cowl, with the 2 mm exclusions."""
    ramp2 = ramp2_window(surf, geometry)
    k = int(np.argmax(ramp2["q"]))

    cowl = surf["cowl_inner"]
    from_lip = np.hypot(cowl["x"] - geometry["P"][0], cowl["y"] - geometry["P"][1])
    return {"q_peak_W_m2": float(ramp2["q"][k]), "x_q_peak_m": float(ramp2["x"][k]),
            "q_peak_cowl_W_m2": float(cowl["q"][from_lip > EXCLUDE_M].max()),
            "heat_load_body_W_per_m": surface.trapezoid(ramp2["q"], ramp2["s"])}


def _cylinder(case, surf, params, geometry, fs):
    """Stagnation heating and shock stand-off. Returns (fields, notes)."""
    R = float(params.get("radius_m", geometry.get("radius_m", 0.010)))
    wall, notes = surf["wall"], []
    out = {"q_stag_W_m2": None, "standoff_over_R": None}
    if "q" in wall:
        k = int(np.argmin(np.hypot(wall["x"] + R, wall["y"])))      # node nearest (-R, 0)
        out["q_stag_W_m2"] = float(wall["q"][k])
    else:
        notes.append("q_stag not computed: no Heat_Flux in the surface file (Euler run)")
    if not (Path(case) / "flow.dat").exists():
        notes.append("standoff_over_R not computed: no flow.dat (run with save_volume)")
    else:
        try:
            out["standoff_over_R"] = standoff_over_R(case, R, fs["p"])
        except ValueError as err:
            notes.append(f"standoff_over_R not computed: {err}")
    return out, notes


def standoff_over_R(case, R, p_inf):
    """Shock stand-off from flow.dat along the stagnation line (y = 0, x < -R): the x where Pressure
    first reaches the midpoint of p_inf and the largest pressure on the line (the post-shock value
    at the wall), scanning inward from the freestream, divided by R."""
    cols = read_tecplot_ascii(Path(case) / "flow.dat")["data"]
    on_line = (np.abs(cols["y"]) < 1e-9) & (cols["x"] < -R)
    order = np.argsort(cols["x"][on_line])
    x, p = cols["x"][on_line][order], surface.state(
        {k: v[on_line][order] for k, v in cols.items()})["p"]
    level = 0.5 * (p_inf + p.max())
    j = int(np.argmax(p >= level))                          # first node from upstream at or above
    if j == 0 or p[j] < level:
        raise ValueError("pressure never crosses the midpoint of p_inf and the post-shock value")
    x_shock = x[j - 1] + (level - p[j - 1]) / (p[j] - p[j - 1]) * (x[j] - x[j - 1])
    return float((-R - x_shock) / R)


def compute(case_dir):
    """The "metrics" block for one case directory (see the module docstring)."""
    case = Path(case_dir)
    params, geometry, fs = surface.inputs(case)
    family = params.get("family", "inlet2r" if "X1" in geometry else None)
    euler = params.get("solver", "NAVIER_STOKES") == "EULER"
    surf = surface.load(case)
    notes = []
    out = {"p0_inf_Pa": fs["p0"]}

    if family in ("inlet2r", "inlet3r"):
        _require(surf, "outlet_duct", last_ramp(geometry), "cowl_inner")
        out.update(_inlet_recovery(case, surf, geometry, fs))
        if euler:
            out.update(q_peak_W_m2=None, x_q_peak_m=None, q_peak_cowl_W_m2=None,
                       heat_load_body_W_per_m=None)
            notes.append("EULER run: heat-flux metrics not computed")
            if family == "inlet3r":
                x, q = eckert_window(surf, geometry, float(params.get("T_wall_K", 300.0)))
                out.update(q_peak_lf_W_m2=float(q.max()), x_q_peak_lf_m=float(x[int(np.argmax(q))]))
                notes.append("q_peak_lf_W_m2: Eckert flat plate on the Euler wall state (Task 9 low fidelity)")
        elif "q" not in surf[last_ramp(geometry)]:
            raise ValueError("NAVIER_STOKES run but surface_flow.dat has no Heat_Flux column")
        else:
            out.update(_inlet_heating(surf, geometry))
    elif family == "wedge":
        _require(surf, "body")
        notes.append("wedge: no throat, recovery and capture not computed; no peak-heating "
                     "definition (sharp leading edge), only the heat load on the body")
        load = None if euler else surface.trapezoid(surf["body"]["q"], surf["body"]["s"])
        out.update(recovery_throat=None, recovery_total=None, recovery_total_bulk=None,
                   mach_throat_massavg=None, capture_ratio=None, q_peak_W_m2=None,
                   x_q_peak_m=None, q_peak_cowl_W_m2=None, heat_load_body_W_per_m=load,
                   su2_avg_totalpress_Pa=_su2_avg_totalpress(case), su2_crosscheck_pass=None)
    elif family == "cylinder":
        _require(surf, "wall")
        fields, extra = _cylinder(case, surf, params, geometry, fs)
        out.update(fields)
        notes += extra
    else:
        raise ValueError(f"cannot compute metrics for family {family!r}")
    out["notes"] = notes
    return out

"""Render an SU2 config from a parameter dict (pure function, no file access except templates)."""
import json
from pathlib import Path
from string import Template

from physics import atmosphere

TEMPLATES = Path(__file__).parent / "templates"
SOLVER_TEMPLATE = {"EULER": "euler.cfg", "NAVIER_STOKES": "navier_stokes.cfg", "RANS_SA": "rans_sa.cfg"}
# RANS_SA: the laminar template with SOLVER= RANS, KIND_TURB_MODEL= SA and the five turbulence-equation
# lines of the development runs in runs/dev/2026-11-01_turbulence_sensitivity_SA (FREESTREAM_NU_FACTOR
# is left at the SU2 default of 3, as there; the key is not in the pinned config template). No transition
# model: turbulent from the leading edge, so it is a sensitivity bound, not a validated turbulent model.

# Which mesh markers play which role, per geometry family (names from 01_interfaces.md).
ROLES = {
    "wedge": {"walls": ["body"], "sym": ["symmetry"], "far": ["inlet", "top"],
              "outlet": ["outlet"], "analyze": []},
    "inlet2r": {"walls": ["body", "cowl"], "sym": ["symmetry"], "far": ["inlet", "top"],
                "outlet": ["outlet_duct", "outlet_ext"], "analyze": ["outlet_duct"]},
    "inlet3r": {"walls": ["body", "cowl"], "sym": ["symmetry"], "far": ["inlet", "top"],
                "outlet": ["outlet_duct", "outlet_ext"], "analyze": ["outlet_duct"]},
    "cylinder": {"walls": ["wall"], "sym": ["symmetry"], "far": ["farfield"],
                 "outlet": ["outlet"], "analyze": []},
}


def _lst(names):
    return "( " + ", ".join(names) + " )"


def render(params, geometry, markers):
    """Return the text of case.cfg. Same inputs give the same text."""
    family = params["family"]
    solver = params.get("solver", "NAVIER_STOKES")
    if family not in ROLES:
        raise ValueError(f"unknown family {family!r}")
    if solver not in SOLVER_TEMPLATE:
        raise ValueError(f"unknown solver {solver!r}")
    roles = ROLES[family]

    # Every marker named in the config must exist in the mesh, and every mesh marker must be used.
    named = {m for names in roles.values() for m in names}
    in_mesh = {k for k, v in markers.items() if isinstance(v, list)}
    for m in sorted(named - in_mesh):
        raise ValueError(f"marker {m!r} is used by the config but missing from the mesh")
    for m in sorted(in_mesh - named):
        raise ValueError(f"mesh marker {m!r} is not used by the config")

    walls, analyze = roles["walls"], roles["analyze"]
    fs = atmosphere.state(params.get("altitude_km", 30))
    t_wall = float(params.get("T_wall_K", 300.0))
    header = "\n".join([
        "% family: " + family,
        "% params: " + json.dumps(params, sort_keys=True),
        "% geometry: " + json.dumps(geometry, sort_keys=True),
    ])
    analyze_lines = ""
    if analyze:
        analyze_lines = (f"MARKER_ANALYZE= {_lst(analyze)}\n"
                         "MARKER_ANALYZE_AVERAGE= MASSFLUX")
    values = {
        "header": header,
        "mach": repr(float(params.get("mach", 4.0))),
        # Freestream from the 1976 atmosphere; at 30 km these are the table values 226.509 K and
        # 1197.03 Pa, so the config text of every 30 km case is unchanged.
        "T_inf": repr(float(fs["T"])),
        "p_inf": repr(float(fs["p"])),
        "max_iter": int(params.get("max_iter", 6000)),
        "walls": _lst(walls),
        "isothermal": "( " + ", ".join(f"{w}, {t_wall!r}" for w in walls) + " )",
        "sym": _lst(roles["sym"]),
        "far": _lst(roles["far"]),
        "outlet": _lst(roles["outlet"]),
        "plotting": _lst(walls + analyze),
        "monitoring": _lst(walls),
        "analyze": analyze_lines,
        # SU2's CSV writers keep only conservative variables, so the output is Tecplot ASCII.
        "output_files": ("( SURFACE_TECPLOT_ASCII, TECPLOT_ASCII )" if params.get("save_volume")
                         else "( SURFACE_TECPLOT_ASCII )"),
    }
    text = (TEMPLATES / SOLVER_TEMPLATE[solver]).read_text()
    return Template(text).substitute(values)

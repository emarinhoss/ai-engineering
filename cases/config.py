"""Render an SU2 config from a parameter dict (pure function, no file access except templates)."""
import json
import math
from pathlib import Path
from string import Template

from drone.ledger import load
from physics import atmosphere
from physics.shock import oblique

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
    "airfoil2d": {"walls": ["airfoil"], "sym": [], "far": ["farfield"], "outlet": [], "analyze": []},
}

# airfoil2d (Task 10.7b): template by params["transition"]. "NONE" is the SA template with
# SA_OPTIONS= NONE (plain SA, the SU2 default), "LM" the recorded second attempt of V6e.
AIRFOIL_TEMPLATE = {"BCM": "inc_rans_airfoil.cfg", "NONE": "inc_rans_airfoil.cfg",
                    "LM": "inc_sst_lm_airfoil.cfg"}
# Air at ISA sea level and the freestream turbulence intensity of the transition models, read once
# at import from the drone ledger (data/drone/air.yaml, data/drone/rules.yaml). The rendered
# case.cfg, and so its config hash, follows the ledger: changing a ledger value changes the case.
AIR_DENSITY = load("air")["density_kg_m3"]
AIR_VISCOSITY = load("air")["dynamic_viscosity_Pa_s"]
AIRFOIL_TURB_INTENSITY = load("rules")["freestream_turbulence_intensity"]


def _lst(names):
    return "( " + ", ".join(names) + " )"


def duct_back_pressure(params, fs):
    """Inviscid static pressure behind the three ramp shocks at the flight Mach (Pa): p_inf times the
    product of the oblique-shock pressure ratios. Used as the back pressure of the inlet3r duct outlet."""
    M, p = float(params.get("mach", 4.0)), float(fs["p"])
    for i in (1, 2, 3):
        s = oblique(M, math.radians(float(params[f"theta{i}_deg"])))
        M, p = s["M2"], p * s["p_ratio"]
    return p


def _outlet(params, roles, fs):
    """Text after MARKER_SUPERSONIC_OUTLET=. For inlet3r the duct outlet is moved to MARKER_OUTLET,
    which SU2 applies node by node: extrapolation where the outflow is supersonic, the given static
    pressure where it is subsonic (the wall boundary layer). With the supersonic outlet everywhere, the
    nominal fine-mesh run diverged from the duct-outlet corner (runs/dev/2026-11-03_inlet3r_v5c_diag)."""
    if params["family"] != "inlet3r" or params.get("solver", "NAVIER_STOKES") == "EULER":
        return _lst(roles["outlet"])                  # Euler: no subsonic wall layer, all supersonic
    rest = [m for m in roles["outlet"] if m != "outlet_duct"]
    return _lst(rest) + f"\nMARKER_OUTLET= ( outlet_duct, {duct_back_pressure(params, fs)!r} )"


def render(params, geometry, markers):
    """Return the text of case.cfg. Same inputs give the same text."""
    family = params["family"]
    solver = params.get("solver", "NAVIER_STOKES")
    if family not in ROLES:
        raise ValueError(f"unknown family {family!r}")
    if solver not in SOLVER_TEMPLATE and family != "airfoil2d":
        raise ValueError(f"unknown solver {solver!r}")
    roles = ROLES[family]

    # Every marker named in the config must exist in the mesh, and every mesh marker must be used.
    named = {m for names in roles.values() for m in names}
    in_mesh = {k for k, v in markers.items() if isinstance(v, list)}
    for m in sorted(named - in_mesh):
        raise ValueError(f"marker {m!r} is used by the config but missing from the mesh")
    for m in sorted(in_mesh - named):
        raise ValueError(f"mesh marker {m!r} is not used by the config")

    if family == "airfoil2d":
        return _render_airfoil(params, geometry, roles)

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
        "outlet": _outlet(params, roles, fs),
        "plotting": _lst(walls + analyze),
        "monitoring": _lst(walls),
        "analyze": analyze_lines,
        # SU2's CSV writers keep only conservative variables, so the output is Tecplot ASCII.
        "output_files": ("( SURFACE_TECPLOT_ASCII, TECPLOT_ASCII )" if params.get("save_volume")
                         else "( SURFACE_TECPLOT_ASCII )"),
    }
    text = (TEMPLATES / SOLVER_TEMPLATE[solver]).read_text()
    return Template(text).substitute(values)


def _output_files(params):
    """SU2's CSV writers keep only conservative variables, so the output is Tecplot ASCII.
    save_restart adds RESTART_ASCII (SU2 writes restart_flow.csv)."""
    files = ["SURFACE_TECPLOT_ASCII"]
    if params.get("save_volume"):
        files.append("TECPLOT_ASCII")
    if params.get("save_restart"):
        files.append("RESTART_ASCII")
    return "( " + ", ".join(files) + " )"


def _restart_lines(params):
    """Config lines that start the case from solution_flow.csv, which the worker writes from a donor
    case (restart_from) or copies from a prepared file (start_file, experiment W1); empty text when
    neither is set, so the rendered case.cfg of every case without them is unchanged."""
    if not (params.get("restart_from") or params.get("start_file")):
        return ""
    return "RESTART_SOL= YES\nREAD_BINARY_RESTART= NO\n"


# Solver-setting defaults of every recorded airfoil2d case, as the text the templates held. An
# optional param (experiment S1/S2, docs/specs/task11_fno_exploration.md) replaces one of them; with
# the param unset the rendered case.cfg is byte-identical to before.
AIRFOIL_NUMERICS = {"cfl_max": "20.0", "linear_tol": "1E-6", "cauchy_elems": "200", "cauchy_eps": "1E-5"}


def _numerics(params):
    """Template values for the four optional solver settings: the recorded default text, or the
    param's own value when it is given."""
    out = dict(AIRFOIL_NUMERICS)
    for name in out:
        if params.get(name) is not None:
            out[name] = repr(params[name])
    return out


def _render_airfoil(params, geometry, roles):
    """case.cfg text for family airfoil2d: incompressible RANS at the chord Reynolds number.

    Velocity V = Re mu / (rho c) with c = 1 m; its direction is the angle of attack, which is also
    AOA (SU2 projects the forces on the AOA axes), so the mesh is never rotated."""
    transition = params.get("transition", "BCM")
    if transition not in AIRFOIL_TEMPLATE:
        raise ValueError(f"unknown transition {transition!r}")
    chord = float(geometry.get("chord_m", 1.0))
    alpha = float(params["alpha_deg"])
    speed = float(params["reynolds"]) * AIR_VISCOSITY / (AIR_DENSITY * chord)
    a = math.radians(alpha)
    walls = roles["walls"]
    header = "\n".join([
        "% family: airfoil2d",
        "% params: " + json.dumps(params, sort_keys=True),
        "% geometry: " + json.dumps(geometry, sort_keys=True),
        f"% velocity: V = Re mu / (rho c) = {speed!r} m/s",
    ])
    values = {
        "header": header,
        "sa_options": "BCM" if transition == "BCM" else "NONE",
        "turb_intensity": repr(AIRFOIL_TURB_INTENSITY),
        "aoa": repr(alpha),
        "density": repr(AIR_DENSITY),
        "viscosity": repr(AIR_VISCOSITY),
        "velocity_init": f"( {speed * math.cos(a)!r}, {speed * math.sin(a)!r}, 0.0 )",
        "max_iter": int(params.get("max_iter", 3000)),
        "heatflux": "( " + ", ".join(f"{w}, 0.0" for w in walls) + " )",
        "far": _lst(roles["far"]),
        "plotting": _lst(walls),
        "monitoring": _lst(walls),
        "output_files": _output_files(params),
        "restart": _restart_lines(params),
        **_numerics(params),
    }
    text = (TEMPLATES / AIRFOIL_TEMPLATE[transition]).read_text()
    return Template(text).substitute(values)

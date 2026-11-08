"""Physics gates on case parameters (01_interfaces.md, "Physics gates").

check(params) returns a list of error strings, empty when the case is acceptable. Pure function:
it never builds a mesh (the lip P comes from geometry.inlet.design_points, the analytic part).
Each message names the gate, the offending value and the limit.
"""
import math

from geometry.inlet import MAX_YP_FRACTION, MIN_H, MIN_RAMP2_LEN, X1, Y_TOP, design_points, sizes
from physics import atmosphere
from physics.constants import GAMMA, R_AIR, sutherland_mu
from physics.shock import oblique, theta_max

MARGIN_DEG = 2.0         # gate 1: stay this far below theta_max
MAX_TURN_DEG = 24.0      # gate 4: design-space definition (26 at Task 0; 24 since 2026-11-01, see 00_decisions.md)
MAX_WALL_RE = 50.0       # gate 5 (Task 0 set 40; raised to 50 on 2026-11-01, see 00_decisions.md)
MAX_TURN_3R_DEG = 27.0   # gate 4 for inlet3r (Task 9 spec, section 4); convergence inside it is learned
DESIGN_MACH_3R = 4.0     # inlet3r geometry is always built shock-on-lip at Mach 4


def _attached(theta_deg, M, name):
    """Gate 1 for one shock: theta <= theta_max(M) - 2 deg. Returns a list of 0 or 1 messages."""
    limit = math.degrees(theta_max(M)) - MARGIN_DEG
    if theta_deg > limit:
        return [(f"gate 1 (attached shock): {name}={theta_deg:g} deg exceeds "
                 f"theta_max(M={M:.4g}) - {MARGIN_DEG:g} deg = {limit:.3f} deg")]
    return []


def check(params):
    """Error strings in gate order (empty list: all gates pass)."""
    return sorted(_check(params))


def _check(params):
    family = params.get("family")
    if family == "drone":
        return _check_drone(params)
    M = float(params.get("mach", 4.0))
    if family == "wedge":
        return _attached(float(params["theta1_deg"]), M, "theta1_deg")
    if family == "inlet3r":
        return _check_inlet3r(params)
    if family != "inlet2r":
        return []

    th1, th2 = float(params["theta1_deg"]), float(params["theta2_deg"])
    errors = _attached(th1, M, "theta1_deg")
    if th1 + th2 > MAX_TURN_DEG:
        errors.append(f"gate 4 (total turning): theta1+theta2 = {th1 + th2:g} deg exceeds {MAX_TURN_DEG:g} deg")
    if errors and errors[0].startswith("gate 1"):
        return errors                                   # M1 and the lip are meaningless for a detached shock
    M1 = oblique(M, math.radians(th1))["M2"]
    errors += _attached(th2, M1, "theta2_deg")
    if any(e.startswith("gate 1") for e in errors):
        return errors

    g = design_points(th1, th2, M)
    x_P, y_P = g["P"]
    if x_P - X1 < MIN_RAMP2_LEN:
        errors.append(f"gate 2 (shock on lip): x_P - X1 = {x_P - X1:.4f} m is below {MIN_RAMP2_LEN} m")
    if y_P > MAX_YP_FRACTION * Y_TOP:
        errors.append(f"gate 2 (shock on lip): y_P = {y_P:.4f} m is above {MAX_YP_FRACTION} y_top "
                      f"= {MAX_YP_FRACTION * Y_TOP:.4f} m")
    if g["h"] < MIN_H:
        errors.append(f"gate 3 (duct height): h = {g['h']:.4f} m is below {MIN_H} m")

    # Gate 5: wall-cell Reynolds number rho_w a_w d0 / mu_w at the inviscid throat pressure.
    T_w = float(params.get("T_wall_K", 300.0))
    p_th = atmosphere.state(params.get("altitude_km", 30))["p"] * g["p_ratio"]
    d0 = sizes(params.get("mesh_level", "medium"))["d0"]
    re_w = (p_th / (R_AIR * T_w)) * math.sqrt(GAMMA * R_AIR * T_w) * d0 / sutherland_mu(T_w)
    if re_w > MAX_WALL_RE:
        errors.append(f"gate 5 (wall-cell Reynolds number): {re_w:.1f} on ramp 2 at first-cell height "
                      f"{d0 * 1e6:.1f} um exceeds {MAX_WALL_RE:g}")
    return errors


def _chain_attached(thetas, M):
    """Gate 1 along the ramps at freestream Mach M. Returns (messages, pressure ratio after the
    last shock or None when a shock detaches)."""
    errors, p_ratio = [], 1.0
    for i, th in enumerate(thetas, start=1):
        errors += _attached(th, M, f"theta{i}_deg")
        if errors:
            return errors, None
        s = oblique(M, math.radians(th))
        M, p_ratio = s["M2"], p_ratio * s["p_ratio"]
    return errors, p_ratio


def _check_inlet3r(params):
    """The five gates for the three-ramp inlet (Task 9 spec, section 4). Gate 1 at the design Mach
    (the geometry) and at the flight Mach (the run)."""
    from geometry import inlet3r                         # here, so that inlet2r never needs it

    th = [float(params[f"theta{i}_deg"]) for i in (1, 2, 3)]
    M = float(params.get("mach", DESIGN_MACH_3R))
    errors = []
    if sum(th) > MAX_TURN_3R_DEG:
        errors.append(f"gate 4 (total turning): theta1+theta2+theta3 = {sum(th):g} deg exceeds {MAX_TURN_3R_DEG:g} deg")
    design_errors, _ = _chain_attached(th, DESIGN_MACH_3R)
    flight_errors, p_ratio = _chain_attached(th, M)
    errors += [e + " (design Mach 4)" for e in design_errors] + [e + f" (flight Mach {M:g})" for e in flight_errors]
    if design_errors or flight_errors:
        return errors
    try:
        g = inlet3r.design_points(*th, mach=DESIGN_MACH_3R)
    except ValueError as exc:
        return errors + [f"gate 2 (shock on lip): {exc}"]
    x_P, y_P = g["P"]
    x_C2 = g["C2"][0]
    if x_C2 - X1 < MIN_RAMP2_LEN:
        errors.append(f"gate 3 (ramp length): ramp 2 is {x_C2 - X1:.4f} m long, below {MIN_RAMP2_LEN} m")
    if x_P - x_C2 < MIN_RAMP2_LEN:
        errors.append(f"gate 3 (ramp length): ramp 3 is {x_P - x_C2:.4f} m long (to the lip), below {MIN_RAMP2_LEN} m")
    if y_P > MAX_YP_FRACTION * Y_TOP:
        errors.append(f"gate 2 (shock on lip): y_P = {y_P:.4f} m is above {MAX_YP_FRACTION} y_top "
                      f"= {MAX_YP_FRACTION * Y_TOP:.4f} m")
    if g["h"] < MIN_H:
        errors.append(f"gate 3 (duct height): h = {g['h']:.4f} m is below {MIN_H} m")
    # Gate 5 at the flight condition: the inviscid pressure after the three shocks at the flight Mach.
    T_w = float(params.get("T_wall_K", 300.0))
    p_th = atmosphere.state(params.get("altitude_km", 30))["p"] * p_ratio
    d0 = inlet3r.sizes(params.get("mesh_level", "medium"))["d0"]
    re_w = (p_th / (R_AIR * T_w)) * math.sqrt(GAMMA * R_AIR * T_w) * d0 / sutherland_mu(T_w)
    if re_w > MAX_WALL_RE:
        errors.append(f"gate 5 (wall-cell Reynolds number): {re_w:.1f} on ramp 3 at first-cell height "
                      f"{d0 * 1e6:.1f} um exceeds {MAX_WALL_RE:g}")
    return errors



def _check_drone(params):
    """Gates of the drone sizing study: the closure and the gate list of drone.evaluate."""
    # imported here so that the inlet families never import drone or torch
    from drone.evaluate import evaluate
    from drone.ledger import load_all

    try:
        return list(evaluate(params, load_all())["gates"])
    except ValueError as exc:
        return [f"gate 3 (mass closure): {exc}"]

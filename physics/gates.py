"""Physics gates on case parameters (01_interfaces.md, "Physics gates").

check(params) returns a list of error strings, empty when the case is acceptable. Pure function:
it never builds a mesh (the lip P comes from geometry.inlet.design_points, the analytic part).
Each message names the gate, the offending value and the limit.
"""
import math

from geometry.inlet import MAX_YP_FRACTION, MIN_H, MIN_RAMP2_LEN, X1, Y_TOP, design_points, sizes
from physics.constants import ATMOSPHERE_TABLE, GAMMA, R_AIR, sutherland_mu
from physics.shock import oblique, theta_max

MARGIN_DEG = 2.0         # gate 1: stay this far below theta_max
MAX_TURN_DEG = 26.0      # gate 4: design-space definition
MAX_WALL_RE = 50.0       # gate 5 (Task 0 set 40; raised to 50 on 2026-11-01, see 00_decisions.md)


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
    M = float(params.get("mach", 4.0))
    if family == "wedge":
        return _attached(float(params["theta1_deg"]), M, "theta1_deg")
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
    p_th = ATMOSPHERE_TABLE[int(params.get("altitude_km", 30))]["p"] * g["p_ratio"]
    d0 = sizes(params.get("mesh_level", "medium"))["d0"]
    re_w = (p_th / (R_AIR * T_w)) * math.sqrt(GAMMA * R_AIR * T_w) * d0 / sutherland_mu(T_w)
    if re_w > MAX_WALL_RE:
        errors.append(f"gate 5 (wall-cell Reynolds number): {re_w:.1f} on ramp 2 at first-cell height "
                      f"{d0 * 1e6:.1f} um exceeds {MAX_WALL_RE:g}")
    return errors

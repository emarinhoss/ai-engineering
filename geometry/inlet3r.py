"""Three-ramp inlet with cowl (family inlet3r): same construction as geometry/inlet.py plus ramp 3.

x right, y up, metres, origin at the sharp leading edge O. Ramp 1 from O at theta1 to C1 =
(X1, X1 tan theta1); ramp 2 at theta1 + theta2 from C1 to C2; ramp 3 at theta_t = theta1 + theta2
+ theta3 from C2 to the throat. Shock-on-lip at the DESIGN Mach 4.0 (the flight Mach never moves
the geometry): shock 1 from O and shock 2 from C1 meet at the lip P (as in inlet2r); C2 is the
point on ramp 2 from which the shock-3 line passes through P. The cowl runs from P parallel to
ramp 3 for L_D; the throat plane is normal to it.

Ten blocks: inlet2r's eight with one more column (ramps 2 and 3 each have a lower/upper pair).
Lower row L0..L4 (L4 is the duct), upper row U0..U4 = blocks 5..9. Marker names equal inlet2r's.
"""
import math

import numpy as np

from geometry.inlet import (
    DELTA_EXT_DEG, GROWTH_MAX, L_D, MAX_YP_FRACTION, MIN_H, MIN_RAMP2_LEN, X1, X_IN, Y_TOP,
    _hand_over, _n_capped, _n_low, _n_up, _ramp2_distribution,
)
from geometry.inlet import sizes as sizes_inlet2r
from geometry.structured import Block, Mesh, stretch_capped, stretch_one_sided, stretch_two_sided_smooth
from physics.shock import oblique

DESIGN_MACH = 4.0
D0_FACTOR = 0.6   # wall-cell Reynolds number <= 50 over the Task 9 envelope; docs/specs/task9_inlet3r_envelope.md


def sizes(level):
    """inlet2r sizes for the level, with the first cell height d0 times D0_FACTOR."""
    s = dict(sizes_inlet2r(level))
    s["d0"] = s["d0"] * D0_FACTOR
    return s


def design_points(theta1_deg, theta2_deg, theta3_deg, mach=DESIGN_MACH):
    """Analytic inlet geometry and inviscid flow numbers. No mesh. Points are numpy arrays (x, y).

    Raises ValueError if a shock detaches or if the shock-on-lip construction does not exist."""
    th1, th2, th3 = (math.radians(a) for a in (theta1_deg, theta2_deg, theta3_deg))
    s1 = oblique(mach, th1)
    if math.isnan(s1["beta"]):
        raise ValueError(f"shock 1 detached: theta1={theta1_deg} deg at M={mach}")
    s2 = oblique(s1["M2"], th2)
    if math.isnan(s2["beta"]):
        raise ValueError(f"shock 2 detached: theta2={theta2_deg} deg at M1={s1['M2']:.4f}")
    s3 = oblique(s2["M2"], th3)
    if math.isnan(s3["beta"]):
        raise ValueError(f"shock 3 detached: theta3={theta3_deg} deg at M2={s2['M2']:.4f}")
    beta1, beta2_abs, beta3_abs = s1["beta"], th1 + s2["beta"], th1 + th2 + s3["beta"]
    C1 = np.array([X1, X1 * math.tan(th1)])
    d1 = np.array([math.cos(beta1), math.sin(beta1)])           # shock 1 direction, from O
    d2 = np.array([math.cos(beta2_abs), math.sin(beta2_abs)])   # shock 2 direction, from C1
    a, _ = np.linalg.solve(np.column_stack((d1, -d2)), C1)      # O + a d1 = C1 + b d2
    P = a * d1
    th12 = th1 + th2
    t12 = np.array([math.cos(th12), math.sin(th12)])            # ramp 2 direction
    d3 = np.array([math.cos(beta3_abs), math.sin(beta3_abs)])   # shock 3 direction, from C2
    s, b = np.linalg.solve(np.column_stack((t12, d3)), P - C1)   # C1 + s t12 + b d3 = P, C2 = C1 + s t12
    C2 = C1 + s * t12
    if not (s > 0 and b > 0 and C1[0] < C2[0] < P[0]):
        raise ValueError(f"shock-on-lip construction does not exist: x_C1={C1[0]:.4f}, "
                         f"x_C2={C2[0]:.4f}, x_P={P[0]:.4f}")
    theta_t = th12 + th3
    t3 = np.array([math.cos(theta_t), math.sin(theta_t)])
    n3 = np.array([-math.sin(theta_t), math.cos(theta_t)])
    h = float((P - C2) @ n3)
    F = P - h * n3                                              # foot of the perpendicular on ramp 3
    t_ext = np.array([math.cos(theta_t + math.radians(DELTA_EXT_DEG)),
                      math.sin(theta_t + math.radians(DELTA_EXT_DEG))])
    s_ext = L_D * math.cos(theta_t) / t_ext[0]                  # puts G at x = x of E_cowl
    return {"theta_t": theta_t, "C1": C1, "C2": C2, "P": P, "E_body": F + L_D * t3,
            "E_cowl": P + L_D * t3, "G": P + s_ext * t_ext, "t3": t3, "h": h,
            "beta1": beta1, "beta2_abs": beta2_abs, "beta3_abs": beta3_abs,
            "M1": s1["M2"], "M2": s2["M2"], "M3": s3["M2"],
            "p_ratio": s1["p_ratio"] * s2["p_ratio"] * s3["p_ratio"],
            "recovery": s1["p0_ratio"] * s2["p0_ratio"] * s3["p0_ratio"]}


def build(params):
    """params: theta1_deg, theta2_deg, theta3_deg, mesh_level (medium). Returns (geometry, Mesh).
    A "mach" key is ignored for the geometry (it is always built for the design Mach 4.0)."""
    th1, th2, th3 = (float(params[k]) for k in ("theta1_deg", "theta2_deg", "theta3_deg"))
    level = params.get("mesh_level", "medium")
    s = sizes(level)
    g = design_points(th1, th2, th3)
    C1, C2, P, E_body, E_cowl, G = (g[k] for k in ("C1", "C2", "P", "E_body", "E_cowl", "G"))
    theta_t, h = g["theta_t"], g["h"]
    x_P, y_P = P
    X2 = float(C2[0])
    if X2 - X1 < MIN_RAMP2_LEN:
        raise ValueError(f"ramp 2 length x_C2 - X1 = {X2 - X1:.4f} m is below {MIN_RAMP2_LEN} m")
    if x_P - X2 < MIN_RAMP2_LEN:
        raise ValueError(f"ramp 3 length x_P - x_C2 = {x_P - X2:.4f} m is below {MIN_RAMP2_LEN} m")
    if h < MIN_H:
        raise ValueError(f"duct height h = {h:.4f} m is below {MIN_H} m")
    if y_P > MAX_YP_FRACTION * Y_TOP:
        raise ValueError(f"lip height y_P = {y_P:.4f} m is above {MAX_YP_FRACTION} y_top")

    th12 = math.radians(th1 + th2)
    tan1, tan12, tan_t = math.tan(math.radians(th1)), math.tan(th12), math.tan(theta_t)
    y_B = C2[1] + (x_P - X2) * tan_t                    # body height under the lip, x = x_P
    B_P = np.array([x_P, y_B])
    d0 = s["d0"]
    n_low = _n_low(h, d0, s["n_low"])
    d_cowl = d0 / math.cos(theta_t + math.radians(DELTA_EXT_DEG))
    n_up = _n_up(Y_TOP - y_P, d_cowl, s["n_up"])

    # Streamwise distributions: upstream column, ramp 1, ramp 2, ramp 3 (x values), duct (0..1).
    x_up = -stretch_one_sided(-X_IN, s["n_ups"], s["dx_ups"])[0][::-1]
    x1 = stretch_capped(X1, _n_capped(X1, s["dx0"], s["dxmax"]), s["dx0"], s["dxmax"])[0]
    x2 = X1 + _ramp2_distribution(X2 - X1, s["dx_c"], s["dxmax"])
    x3 = X2 + _ramp2_distribution(x_P - X2, s["dx_c"], s["dxmax"])
    s_d = stretch_capped(L_D, _n_capped(L_D, s["dx_c"], s["dxmax"]), s["dx_c"], s["dxmax"])[0] / L_D

    L_up = Y_TOP - y_P
    cap_max = 0.95 * L_up / (n_up - 1)
    # A high lip (low turning) makes the x = 0 column too tall for the inlet2r node count: its
    # wall-clustered part would grow faster than GROWTH_MAX. Add nodes (odd count) until it fits.
    while stretch_capped(y_P, n_low, d0, _hand_over(y_P, n_low, d0, cap_max))[1] > GROWTH_MAX:
        n_low += 2

    def column(wall_y, angle):
        d = d0 / math.cos(angle)
        low, _ = stretch_capped(y_P - wall_y, n_low, d, _hand_over(y_P - wall_y, n_low, d, cap_max))
        up, _ = stretch_one_sided(L_up, n_up, low[-1] - low[-2])
        return wall_y + low, y_P + up

    lo0, up0 = column(0.0, 0.0)                         # lines at x_in and x = 0
    lo1, up1 = column(C1[1], math.radians(th1))         # line at X1
    lo2, _ = column(C2[1], th12)                        # line at X2, body to the lip line
    z, _ = stretch_two_sided_smooth(y_P - y_B, n_low, d0 / math.cos(theta_t), d0 / math.cos(theta_t))
    loP = y_B + z                                       # line x = x_P, body to lip
    upP = y_P + stretch_one_sided(L_up, n_up, d_cowl)[0]
    # Upper line at X2: a blend of the lines at X1 and x_P, weighted by position. The upper rows then
    # change from the X1 spacing to the fine cowl spacing over ramps 2 and 3 together, as inlet2r's do
    # over its ramp 2. With its own column() spacing at X2, the short ramp 3 of a high-turning design
    # tilted the rows of block U3 enough to fail the 40 deg minimum-angle gate (10/10/7: 36.8 deg).
    lam = (X2 - X1) / (x_P - X1)
    up2 = (1 - lam) * up1 + lam * upP
    zt, _ = stretch_two_sided_smooth(h, n_low, d0, d0)  # throat plane, normal to both walls
    upG = G[1] + stretch_one_sided(Y_TOP - G[1], n_up, d_cowl)[0]

    def line(x, y):
        return np.column_stack((np.full(len(y), x), y))

    def row(x, y):
        return np.column_stack((x, np.full(len(x), y)))

    def seg(a, b, t):
        return a + t[:, None] * (b - a)

    def body_y(x):
        return np.where(x <= X1, x * tan1,
                        np.where(x <= X2, C1[1] + (x - X1) * tan12, C2[1] + (x - X2) * tan_t))

    ramp1 = np.column_stack((x1, x1 * tan1))
    ramp2 = np.column_stack((x2, body_y(x2)))
    ramp3 = np.column_stack((x3, body_y(x3)))
    throat = seg(E_body, E_cowl, zt / h)
    blocks = [
        Block(row(x_up, 0.0), line(0.0, lo0), row(x_up, y_P), line(X_IN, lo0)),            # 0 L0
        Block(ramp1, line(X1, lo1), row(x1, y_P), line(0.0, lo0)),                         # 1 L1
        Block(ramp2, line(X2, lo2), row(x2, y_P), line(X1, lo1)),                          # 2 L2
        Block(ramp3, line(x_P, loP), row(x3, y_P), line(X2, lo2)),                         # 3 L3
        Block(seg(B_P, E_body, s_d), throat, seg(P, E_cowl, s_d), line(x_P, loP)),         # 4 L4 duct
        Block(row(x_up, y_P), line(0.0, up0), row(x_up, Y_TOP), line(X_IN, up0)),          # 5 U0
        Block(row(x1, y_P), line(X1, up1), row(x1, Y_TOP), line(0.0, up0)),                # 6 U1
        Block(row(x2, y_P), line(X2, up2), row(x2, Y_TOP), line(X1, up1)),                 # 7 U2
        Block(row(x3, y_P), line(x_P, upP), row(x3, Y_TOP), line(X2, up2)),                # 8 U3
        Block(seg(P, G, s_d), line(G[0], upG), row(x_P + s_d * (G[0] - x_P), Y_TOP),
              line(x_P, upP)),                                                              # 9 U4
    ]
    shared = [(0, "right", 1, "left", False), (1, "right", 2, "left", False),
              (2, "right", 3, "left", False), (3, "right", 4, "left", False),
              (5, "right", 6, "left", False), (6, "right", 7, "left", False),
              (7, "right", 8, "left", False), (8, "right", 9, "left", False),
              (0, "top", 5, "bottom", False), (1, "top", 6, "bottom", False),
              (2, "top", 7, "bottom", False), (3, "top", 8, "bottom", False)]
    mesh = Mesh.from_blocks(blocks, shared, level=level)
    mesh.add_marker("body", [(1, "bottom"), (2, "bottom"), (3, "bottom"), (4, "bottom")], wall=True)
    mesh.add_marker("cowl", [(4, "top"), (9, "bottom")], wall=True)
    mesh.add_marker("symmetry", [(0, "bottom")])
    mesh.add_marker("inlet", [(0, "left"), (5, "left")])
    mesh.add_marker("top", [(5, "top"), (6, "top"), (7, "top"), (8, "top"), (9, "top")])
    mesh.add_marker("outlet_duct", [(4, "right")])
    mesh.add_marker("outlet_ext", [(9, "right")])

    def pt(p):
        return [float(p[0]), float(p[1])]

    geometry = {
        "theta1_deg": th1, "theta2_deg": th2, "theta3_deg": th3, "mach": DESIGN_MACH,
        "X1": X1, "X2": X2, "L_d": L_D, "x_in": X_IN, "y_top": Y_TOP, "delta_ext_deg": DELTA_EXT_DEG,
        "theta_t_deg": math.degrees(theta_t),
        "C": pt(C1), "C2": pt(C2), "P": pt(P), "E_body": pt(E_body), "E_cowl": pt(E_cowl), "G": pt(G),
        "h_duct": h, "beta1_deg": math.degrees(g["beta1"]), "beta2_abs_deg": math.degrees(g["beta2_abs"]),
        "beta3_abs_deg": math.degrees(g["beta3_abs"]),
        # M1: after shock 1. M2_inviscid: throat Mach after all three shocks (the number the
        # inlet2r metrics compare with). M3 is the same throat Mach under its inlet3r name.
        "M1": g["M1"], "M2_inviscid": g["M3"], "M3": g["M3"], "M2_after_shock2": g["M2"],
        "p_th_over_p_inf_inviscid": g["p_ratio"],
        "recovery_3shock_inviscid": g["recovery"],
        "recovery_2shock_inviscid": g["recovery"],      # inlet2r key name, kept for shared code
        "body_length": float(E_body[0]),
        "level": level, "nodes": len(mesh.coords), "cells": len(mesh.cells),
    }
    return geometry, mesh

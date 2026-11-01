"""Two-ramp inlet with cowl (family inlet2r): geometry from the shock-on-lip rule and the mesh.

Geometry (00_decisions.md section 2; x right, y up, metres, origin at the sharp leading edge O):
ramp 1 from O at theta1 to the corner C = (X1, X1 tan theta1); ramp 2 at theta_t = theta1 + theta2
from C to the throat. The lip P is where the ramp-1 shock (from O) meets the ramp-2 shock (from C).
The cowl inner wall runs from P parallel to ramp 2 for L_D; the throat plane is normal to it.

Eight blocks (lower row is below the lip line y = y_P, upper row above it):

   y_top  +------+--------+----------------+-------------+
          |  U0  |   U1   |       U2       |     U3      |  U3: external flow above the cowl
   y_P    +------+--------+----------------+--P--cowl-----G
          |  L0  |   L1   |       L2       |  L3 (duct)  |
   y = 0  +------+--------+---C ramp 2 ... +--- body ----E_body
        x_in    0        X1               x_P

The vertical grid lines are vertical, so the vertical spacing at a wall is d0 / cos(wall angle)
to make the wall-normal first cell height d0. The duct and throat lines cluster at both walls.
"""
import math

import numpy as np

from geometry.structured import (
    Block,
    Mesh,
    stretch_capped,
    stretch_one_sided,
    stretch_two_sided_smooth,
)
from geometry.wedge import FACTOR, _odd
from physics.shock import oblique

X1, L_D, X_IN, Y_TOP, DELTA_EXT_DEG = 0.100, 0.050, -0.030, 0.200, 6.0
MIN_RAMP2_LEN, MIN_H, MAX_YP_FRACTION = 0.02, 0.008, 0.6   # same numbers as physics/gates.py
GROWTH_MAX = 1.2                                            # wall-normal growth target (gate: 1.25)

# Medium level (00_decisions.md section 6): lengths in metres, counts are nodes.
MEDIUM = {
    "d0": 20e-6,       # first cell height on body and cowl, wall-normal
    "n_low": 61,       # nodes body -> lip line
    "n_up": 33,        # nodes lip line -> top
    "n_ups": 25,       # nodes in the upstream column
    "dx_ups": 0.1e-3,  # spacing of the upstream column at x = 0
    "dx0": 0.1e-3,     # streamwise spacing at the leading edge
    "dx_c": 0.3e-3,    # streamwise spacing at the corner and at the lip
    "dxmax": 1.0e-3,   # streamwise cap
}


def sizes(level):
    """Sizes for a mesh level: lengths x 1.4 (coarse) or / 1.4 (fine), node counts the inverse."""
    if level not in FACTOR:
        raise ValueError(f"mesh_level must be coarse, medium or fine, got {level!r}")
    nf = FACTOR[level]
    s = dict(MEDIUM)
    if level != "medium":
        for k in ("d0", "dx_ups", "dx0", "dx_c", "dxmax"):
            s[k] = MEDIUM[k] / nf
        for k in ("n_low", "n_up", "n_ups"):
            s[k] = _odd(MEDIUM[k] * nf)
    return s


def design_points(theta1_deg, theta2_deg, mach=4.0):
    """Analytic inlet geometry and inviscid flow numbers. No mesh. Used by build and gates.

    Raises ValueError if either shock would detach. Points are numpy arrays (x, y)."""
    th1, th2 = math.radians(theta1_deg), math.radians(theta2_deg)
    s1 = oblique(mach, th1)
    if math.isnan(s1["beta"]):
        raise ValueError(f"shock 1 detached: theta1={theta1_deg} deg at M={mach}")
    s2 = oblique(s1["M2"], th2)
    if math.isnan(s2["beta"]):
        raise ValueError(f"shock 2 detached: theta2={theta2_deg} deg at M1={s1['M2']:.4f}")
    beta1, beta2_abs = s1["beta"], th1 + s2["beta"]
    C = np.array([X1, X1 * math.tan(th1)])
    d1 = np.array([math.cos(beta1), math.sin(beta1)])           # shock 1 direction, from O
    d2 = np.array([math.cos(beta2_abs), math.sin(beta2_abs)])   # shock 2 direction, from C
    a, _ = np.linalg.solve(np.column_stack((d1, -d2)), C)       # O + a d1 = C + b d2
    P = a * d1
    theta_t = th1 + th2
    t2 = np.array([math.cos(theta_t), math.sin(theta_t)])
    n2 = np.array([-math.sin(theta_t), math.cos(theta_t)])
    h = float((P - C) @ n2)
    F = P - h * n2                                              # foot of the perpendicular on ramp 2
    t_ext = np.array([math.cos(theta_t + math.radians(DELTA_EXT_DEG)),
                      math.sin(theta_t + math.radians(DELTA_EXT_DEG))])
    s_ext = L_D * math.cos(theta_t) / t_ext[0]                  # puts G at x = x of E_cowl
    return {"theta_t": theta_t, "C": C, "P": P, "E_body": F + L_D * t2, "E_cowl": P + L_D * t2,
            "G": P + s_ext * t_ext, "t2": t2, "h": h, "beta1": beta1, "beta2_abs": beta2_abs,
            "M1": s1["M2"], "M2": s2["M2"], "p_ratio": s1["p_ratio"] * s2["p_ratio"],
            "recovery": s1["p0_ratio"] * s2["p0_ratio"]}


def _n_capped(L, d0, dmax):
    """Node count for stretch_capped on length L: smallest N it accepts, plus 10 percent, odd."""
    n = max(2, math.ceil(L / dmax))
    while True:
        try:
            stretch_capped(L, n, d0, dmax)
            return _odd(1.1 * n)
        except ValueError:
            n += 1


def _ramp2_distribution(L, d_end, dmax):
    """Two-sided clustering d_end at both ends, capped at dmax. N is the smallest the stretch
    accepts plus 10 percent (odd), the same rule as _n_capped for the one-sided cases."""
    n = max(3, math.ceil(L / dmax) + 1)
    while True:
        try:
            stretch_two_sided_smooth(L, n, d_end, d_end, dmax)
            break
        except ValueError:
            n += 1
    return stretch_two_sided_smooth(L, _odd(1.1 * n), d_end, d_end, dmax)[0]


def _hand_over(L, n, d0, cap_max, rmax=GROWTH_MAX):
    """Smallest cap (spacing where the wall-clustered part hands over to the upper row) for which
    the growth from the wall stays <= rmax; cap_max if even that is not enough. A small cap
    keeps the upper-row cells near the lower ones' size, which keeps the cells unskewed."""
    lo = (L - d0) / (n - 2) * (1 + 1e-9)               # smallest cap that can still span L
    if lo >= cap_max or stretch_capped(L, n, d0, lo)[1] <= rmax:
        return min(lo, cap_max)
    if stretch_capped(L, n, d0, cap_max)[1] > rmax:
        return cap_max
    hi = cap_max
    for _ in range(60):                                 # growth falls as the cap rises
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if stretch_capped(L, n, d0, mid)[1] > rmax else (lo, mid)
    return hi


def _n_up(L, d0, n0, rmax=1.2):
    """Upper-row node count: n0, or more (odd) until growth from the cowl wall is <= rmax."""
    n = n0
    while stretch_one_sided(L, n, d0)[1] > rmax:
        n += 2
    return n


def _n_low(h, d0, n0, rmax=GROWTH_MAX):
    """Lower-row node count: n0, or more (odd) until the two-sided duct distribution over the
    throat height h grows by <= rmax (coarse meshes of narrow ducts need this)."""
    n = n0
    while stretch_two_sided_smooth(h, n, d0, d0)[1]["max_growth"] > rmax:
        n += 2
    return n


def build(params):
    """params: theta1_deg, theta2_deg, mach (4.0), mesh_level (medium). Returns (geometry, Mesh)."""
    th1, th2 = float(params["theta1_deg"]), float(params["theta2_deg"])
    mach = float(params.get("mach", 4.0))
    level = params.get("mesh_level", "medium")
    s = sizes(level)
    g = design_points(th1, th2, mach)
    C, P, E_body, E_cowl, G = (g[k] for k in ("C", "P", "E_body", "E_cowl", "G"))
    theta_t, h = g["theta_t"], g["h"]
    x_P, y_P = P
    if x_P - X1 < MIN_RAMP2_LEN:
        raise ValueError(f"x_P - X1 = {x_P - X1:.4f} m is below {MIN_RAMP2_LEN} m")
    if h < MIN_H:
        raise ValueError(f"duct height h = {h:.4f} m is below {MIN_H} m")
    if y_P > MAX_YP_FRACTION * Y_TOP:
        raise ValueError(f"lip height y_P = {y_P:.4f} m is above {MAX_YP_FRACTION} y_top")

    tan1, tan_t = math.tan(math.radians(th1)), math.tan(theta_t)
    y_B = C[1] + (x_P - X1) * tan_t                     # body height under the lip, x = x_P
    B_P = np.array([x_P, y_B])
    d0 = s["d0"]
    n_low = _n_low(h, d0, s["n_low"])
    d_cowl = d0 / math.cos(theta_t + math.radians(DELTA_EXT_DEG))   # vertical spacing at the outer cowl
    # 33 nodes (medium) would need growth above the 1.25 gate from the cowl wall to y_top, so
    # the upper row gets more nodes when the longest cowl line needs it.
    n_up = _n_up(Y_TOP - y_P, d_cowl, s["n_up"])

    # Streamwise distributions: upstream column, ramp 1, ramp 2 (x values), duct (0..1 parameter).
    x_up = -stretch_one_sided(-X_IN, s["n_ups"], s["dx_ups"])[0][::-1]
    x1 = stretch_capped(X1, _n_capped(X1, s["dx0"], s["dxmax"]), s["dx0"], s["dxmax"])[0]
    x2 = X1 + _ramp2_distribution(x_P - X1, s["dx_c"], s["dxmax"])
    s_d = stretch_capped(L_D, _n_capped(L_D, s["dx_c"], s["dxmax"]), s["dx_c"], s["dxmax"])[0] / L_D

    # Vertical lines. Lower part from d0 / cos(angle) growing at <= GROWTH_MAX, then capped so that
    # it hands over to the upper part with the same spacing (as in the wedge); the upper part
    # grows from there to the top.
    L_up = Y_TOP - y_P
    cap_max = 0.95 * L_up / (n_up - 1)                   # the upper part must be able to absorb it

    def column(wall_y, angle):
        d = d0 / math.cos(angle)
        low, _ = stretch_capped(y_P - wall_y, n_low, d, _hand_over(y_P - wall_y, n_low, d, cap_max))
        up, _ = stretch_one_sided(L_up, n_up, low[-1] - low[-2])
        return wall_y + low, y_P + up

    lo0, up0 = column(0.0, 0.0)                         # lines at x_in and x = 0
    lo1, up1 = column(C[1], math.radians(th1))          # line at X1
    z, _ = stretch_two_sided_smooth(y_P - y_B, n_low, d0 / math.cos(theta_t), d0 / math.cos(theta_t))
    loP = y_B + z                                       # line x = x_P, body to lip
    upP = y_P + stretch_one_sided(L_up, n_up, d_cowl)[0]
    zt, _ = stretch_two_sided_smooth(h, n_low, d0, d0)  # throat plane, normal to both walls
    upG = G[1] + stretch_one_sided(Y_TOP - G[1], n_up, d_cowl)[0]

    def line(x, y):                                     # vertical edge at constant x
        return np.column_stack((np.full(len(y), x), y))

    def row(x, y):                                      # edge at constant y
        return np.column_stack((x, np.full(len(x), y)))

    def seg(a, b, t):                                   # points a + t (b - a)
        return a + t[:, None] * (b - a)

    def body_y(x):
        return np.where(x <= X1, x * tan1, C[1] + (x - X1) * tan_t)

    ramp1 = np.column_stack((x1, x1 * tan1))
    ramp2 = np.column_stack((x2, body_y(x2)))
    throat = seg(E_body, E_cowl, zt / h)
    blocks = [
        Block(row(x_up, 0.0), line(0.0, lo0), row(x_up, y_P), line(X_IN, lo0)),            # 0 L0
        Block(ramp1, line(X1, lo1), row(x1, y_P), line(0.0, lo0)),                         # 1 L1
        Block(ramp2, line(x_P, loP), row(x2, y_P), line(X1, lo1)),                         # 2 L2
        Block(seg(B_P, E_body, s_d), throat, seg(P, E_cowl, s_d), line(x_P, loP)),         # 3 L3 duct
        Block(row(x_up, y_P), line(0.0, up0), row(x_up, Y_TOP), line(X_IN, up0)),          # 4 U0
        Block(row(x1, y_P), line(X1, up1), row(x1, Y_TOP), line(0.0, up0)),                # 5 U1
        Block(row(x2, y_P), line(x_P, upP), row(x2, Y_TOP), line(X1, up1)),                # 6 U2
        Block(seg(P, G, s_d), line(G[0], upG), row(x_P + s_d * (G[0] - x_P), Y_TOP),
              line(x_P, upP)),                                                              # 7 U3
    ]
    # Left-right neighbours, then lower row / upper row stacking. The cowl itself is solid:
    # L3 top and U3 bottom meet only at the lip node P.
    shared = [(0, "right", 1, "left", False), (1, "right", 2, "left", False),
              (2, "right", 3, "left", False), (4, "right", 5, "left", False),
              (5, "right", 6, "left", False), (6, "right", 7, "left", False),
              (0, "top", 4, "bottom", False), (1, "top", 5, "bottom", False),
              (2, "top", 6, "bottom", False)]
    mesh = Mesh.from_blocks(blocks, shared, level=level)
    mesh.add_marker("body", [(1, "bottom"), (2, "bottom"), (3, "bottom")], wall=True)
    mesh.add_marker("cowl", [(3, "top"), (7, "bottom")], wall=True)
    mesh.add_marker("symmetry", [(0, "bottom")])
    mesh.add_marker("inlet", [(0, "left"), (4, "left")])
    mesh.add_marker("top", [(4, "top"), (5, "top"), (6, "top"), (7, "top")])
    mesh.add_marker("outlet_duct", [(3, "right")])
    mesh.add_marker("outlet_ext", [(7, "right")])

    def pt(p):
        return [float(p[0]), float(p[1])]

    geometry = {
        "theta1_deg": th1, "theta2_deg": th2, "mach": mach,
        "X1": X1, "L_d": L_D, "x_in": X_IN, "y_top": Y_TOP, "delta_ext_deg": DELTA_EXT_DEG,
        "theta_t_deg": math.degrees(theta_t),
        "C": pt(C), "P": pt(P), "E_body": pt(E_body), "E_cowl": pt(E_cowl), "G": pt(G),
        "h_duct": h, "beta1_deg": math.degrees(g["beta1"]), "beta2_abs_deg": math.degrees(g["beta2_abs"]),
        "M1": g["M1"], "M2_inviscid": g["M2"], "p_th_over_p_inf_inviscid": g["p_ratio"],
        "recovery_2shock_inviscid": g["recovery"], "body_length": float(E_body[0]),
        "level": level, "nodes": len(mesh.coords), "cells": len(mesh.cells),
    }
    return geometry, mesh

"""Vortex-lattice method for a thin lifting surface (Task 10.3, spec section 3 and rows V6a-V6c).

Axes and signs
    x aft (streamwise), y to starboard (right wing, y > 0), z up. Free stream of unit speed
    V_inf = (cos a, 0, sin a), density 1, so q = 1/2 and every coefficient is force / (q S).
    Lift is the force along (-sin a, 0, cos a). Pitching moment M_y = z F_x - (x - x_ref) F_z
    about (x_ref, 0, 0), positive nose up, so lift aft of x_ref gives a negative Cm. Reference
    length c_mac = (2/S) int_0^{b/2} c^2 dy and reference area S = 2 int_0^{b/2} c dy, both from
    the planform nodes (trapezoidal rule on the piecewise-linear planform); AR = b^2 / S.

Lattice
    The planform's semispan is cut into N strips at cosine-spaced stations eta = (1 - cos t) / 2
    (dense at root and tip) and each strip into M chordwise panels at xi = 1 - cos(t), t in
    [0, pi/2] (dense at the leading edge). Chord and leading edge at a station come from linear
    interpolation of the planform nodes, so sweep and taper need no special case. Each panel holds
    one horseshoe: bound leg on the panel quarter chord (from its inboard to its outboard corner),
    trailing legs to x = +infinity, control point at the panel's three-quarter chord at mid-strip.
    The surface is planar (z = 0); camber enters only through the normal n ~ (-dz/dx, 0, 1).
    The left wing is the mirror image of the right one: only the right half is solved and every
    influence is the sum of a horseshoe and its mirror, which makes the solution exactly symmetric.

Solution
    No flow through the surface at each control point: (V_inf + sum_j A_ij Gamma_j) . n_i = 0,
    solved with numpy.linalg.solve. A flat wing at alpha = 0 has a zero right-hand side, so
    Gamma = 0 and CL = CDi = 0 exactly.

Forces
    CL and Cm (near field): Kutta-Joukowski on each bound leg, F = Gamma (V_inf + v) x l, with v
    the velocity induced at the leg midpoint by every horseshoe (its own bound leg contributes
    nothing there). Induced drag (far field, Trefftz plane): the strip circulations G_i (sum
    over the strip's chordwise panels) are fitted by least squares at the strip centres
    y_i = (b/2) cos(theta_i) to Glauert's symmetric series G = 2 b sum_{n odd} A_n sin(n theta)
    (n = 1, 3, ..., N - 1 for N strips per half), whose Trefftz-plane drag is exact:
    CDi = pi AR sum n A_n^2 (the wake downwash is w = -sum n A_n sin(n theta) / sin(theta)).
    Why not the point-vortex sum -(1/S) sum G_i w_i dy_i with w_i from the shed line vortices
    at the strip edges: with cosine spacing it under-counts the drag by about 1/N (an elliptic
    wing gives e = 1.029 / 1.018 / 1.013 on the three lattices), while the series gives
    e = 0.999 / 0.998 / 0.997. The span efficiency is defined after the fact as
    e = CL^2 / (pi AR CDi) with the near-field CL, so CDi = CL^2 / (pi AR e)
    holds by construction. Section lift per strip: cl_i = 2 G_i / c_i (unit speed).

Cost
    M x N unknowns on the half wing: 8 x 20 = 160 (coarse), 12 x 30 = 360 (medium),
    16 x 40 = 640 (fine); one dense solve of that size, plus two (M N)^2 influence evaluations
    of three segments each. Measured here: 0.3 s coarse, 0.6 s medium, 1.1 s fine per solve
    (the lattice build dominates; derivatives() builds once for its three angles).
"""
import math

import numpy as np

LEVELS = {"coarse": (8, 20), "medium": (12, 30), "fine": (16, 40)}
_GUARD = 1e-12          # squared sine of the angle below which a point is on a vortex line


def _segment(p, a, b):
    """Velocity at points p (n,3) induced by unit-strength finite segments a->b (m,3): (n,m,3)."""
    r1 = p[:, None, :] - a[None, :, :]
    r2 = p[:, None, :] - b[None, :, :]
    cross = np.cross(r1, r2)
    c2 = np.sum(cross * cross, axis=-1)
    n1 = np.linalg.norm(r1, axis=-1)
    n2 = np.linalg.norm(r2, axis=-1)
    r0 = (b - a)[None, :, :]
    dot = np.sum(r0 * (r1 / np.maximum(n1, 1e-300)[..., None]
                       - r2 / np.maximum(n2, 1e-300)[..., None]), axis=-1)
    on_line = c2 <= _GUARD * (n1 * n2) ** 2
    k = np.where(on_line, 0.0, dot / (4.0 * math.pi * np.where(on_line, 1.0, c2)))
    return cross * k[..., None]


def _trailing(p, a):
    """Velocity at p (n,3) of unit semi-infinite lines from a (m,3) to x = +infinity: (n,m,3)."""
    d = np.array([1.0, 0.0, 0.0])
    r = p[:, None, :] - a[None, :, :]
    cross = np.cross(d, r)
    c2 = np.sum(cross * cross, axis=-1)
    nr = np.linalg.norm(r, axis=-1)
    on_line = c2 <= _GUARD * nr ** 2
    k = np.where(on_line, 0.0,
                 (1.0 + r[..., 0] / np.maximum(nr, 1e-300))
                 / (4.0 * math.pi * np.where(on_line, 1.0, c2)))
    return cross * k[..., None]


def _horseshoe(p, a, b):
    """Velocity of unit horseshoes: infinity -> a, a -> b, b -> infinity."""
    return _segment(p, a, b) + _trailing(p, b) - _trailing(p, a)


def _mirror(v):
    return v * np.array([1.0, -1.0, 1.0])


def _influence(p, a, b):
    """Horseshoes of the right half plus their mirror images (bound leg again inboard-to-outboard
    in +y order on the left wing: from mirror(b) to mirror(a))."""
    return _horseshoe(p, a, b) + _horseshoe(p, _mirror(b), _mirror(a))


def reference(planform):
    """Reference area S, aspect ratio, mean aerodynamic chord, from the planform nodes."""
    y = np.asarray(planform.eta, float) * planform.span / 2.0
    c = np.asarray(planform.chord, float)
    area = 2.0 * float(np.sum(0.5 * (c[1:] + c[:-1]) * np.diff(y)))
    # exact integral of c^2 for c linear on each segment
    c2 = np.sum((c[1:] ** 2 + c[1:] * c[:-1] + c[:-1] ** 2) / 3.0 * np.diff(y))
    return area, planform.span ** 2 / area, 2.0 / area * float(c2)


def _lattice(planform, level, camber):
    m, n = LEVELS[level]
    half = planform.span / 2.0
    eta = 0.5 * (1.0 - np.cos(np.pi * np.arange(n + 1) / n))           # strip edges
    xi = 1.0 - np.cos(0.5 * np.pi * np.arange(m + 1) / m)              # chordwise panel edges
    xi[-1] = 1.0
    node_eta = np.asarray(planform.eta, float)
    chord = np.interp(eta, node_eta, np.asarray(planform.chord, float))
    x_le = np.interp(eta, node_eta, np.asarray(planform.x_le, float))
    y = eta * half
    xq = xi[:-1] + 0.25 * np.diff(xi)                                   # bound-leg chord fraction
    xc = xi[:-1] + 0.75 * np.diff(xi)                                   # control-point fraction
    # panel index = strip * m + chordwise
    a = np.zeros((n, m, 3))
    b = np.zeros((n, m, 3))
    a[..., 0] = x_le[:-1, None] + xq[None, :] * chord[:-1, None]
    a[..., 1] = y[:-1, None]
    b[..., 0] = x_le[1:, None] + xq[None, :] * chord[1:, None]
    b[..., 1] = y[1:, None]
    c_mid = 0.5 * (chord[:-1] + chord[1:])
    cp = np.zeros((n, m, 3))
    cp[..., 0] = 0.5 * (x_le[:-1] + x_le[1:])[:, None] + xc[None, :] * c_mid[:, None]
    cp[..., 1] = 0.5 * (y[:-1] + y[1:])[:, None]
    slope = np.zeros((n, m)) if camber is None else np.broadcast_to(
        np.asarray(camber(xc), float), (n, m))
    normal = np.stack([-slope, np.zeros_like(slope), np.ones_like(slope)], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1)[..., None]
    a, b, cp, normal = (v.reshape(n * m, 3) for v in (a, b, cp, normal))
    matrix = np.einsum("ijk,ik->ij", _influence(cp, a, b), normal)
    v_mid = _influence(0.5 * (a + b), a, b)                             # at bound-leg midpoints
    return {"m": m, "n": n, "y": y, "eta": eta, "c_mid": c_mid, "a": a, "b": b,
            "normal": normal, "matrix": matrix, "v_mid": v_mid}


def _forces(planform, lat, alpha):
    area, ar, c_mac = reference(planform)
    v_inf = np.array([math.cos(alpha), 0.0, math.sin(alpha)])
    gamma = np.linalg.solve(lat["matrix"], -lat["normal"] @ v_inf)
    # near field, right half (the left half is its mirror: same lift, same pitching moment)
    vel = v_inf + np.einsum("ijk,j->ik", lat["v_mid"], gamma)
    force = gamma[:, None] * np.cross(vel, lat["b"] - lat["a"])
    lift_dir = np.array([-math.sin(alpha), 0.0, math.cos(alpha)])
    mid = 0.5 * (lat["a"] + lat["b"])
    moment = mid[:, 2] * force[:, 0] - (mid[:, 0] - planform.x_ref) * force[:, 2]
    cl_wing = 2.0 * float(np.sum(force @ lift_dir)) / (0.5 * area)
    cm = 2.0 * float(np.sum(moment)) / (0.5 * area * c_mac)
    # far field, Trefftz plane: the strip loads as a Glauert series, then CDi exactly
    g_half = gamma.reshape(lat["n"], lat["m"]).sum(axis=1)             # strip circulation
    y_mid = 0.5 * (lat["y"][:-1] + lat["y"][1:])
    theta = np.arccos(y_mid / (planform.span / 2.0))
    odd = 2 * np.arange(lat["n"] // 2) + 1                              # symmetric: odd terms
    coef = np.linalg.lstsq(np.sin(np.outer(theta, odd)), g_half / (2.0 * planform.span),
                           rcond=None)[0]
    cdi = math.pi * ar * float(np.sum(odd * coef ** 2))
    e = cl_wing ** 2 / (math.pi * ar * cdi) if cdi != 0.0 else float("nan")
    eta_mid = 0.5 * (lat["eta"][:-1] + lat["eta"][1:])
    return {"CL": cl_wing, "CDi": cdi, "e": e, "Cm": cm, "eta": eta_mid.tolist(),
            "cl": (2.0 * g_half / lat["c_mid"]).tolist()}


def solve(planform, alpha, level="medium", camber=None):
    """Lift, induced drag, span efficiency, pitching moment and section lift at alpha (radians)."""
    return _forces(planform, _lattice(planform, level, camber), alpha)


def derivatives(planform, level="medium", camber=None):
    """CL_alpha and Cm_alpha per radian by central difference over +-2 deg; alpha_L0 = -CL(0)/CL_a."""
    lat = _lattice(planform, level, camber)
    h = math.radians(2.0)
    lo, mid, hi = (_forces(planform, lat, a) for a in (-h, 0.0, h))
    cl_a = (hi["CL"] - lo["CL"]) / (2.0 * h)
    return {"CL_alpha": cl_a, "alpha_L0": -mid["CL"] / cl_a,
            "Cm_alpha": (hi["Cm"] - lo["Cm"]) / (2.0 * h)}

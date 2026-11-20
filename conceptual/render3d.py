"""3D render of a Stage 1 design from its recorded geometry (design_<concept>.json).

    python -m conceptual.render3d --design runs/task12/stage1/<run>/design_pusher.json --out FILE.png

A conceptual visualisation, not a loft: the fuselage is the body of revolution used by the
three-view, the wing and tails are straight-tapered with unswept leading edges, the main gear is
shown retracted in its sponsons. The wing section is drawn as a NACA 4415 and the tails as NACA
0012 for display only (Stage 1 carries a 15 % thick cambered section without fixing its shape).
Flat-shaded triangles with one light; matplotlib only.
"""
import argparse
import json
import math

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from drone import naca

LIGHT = np.array([-0.4, -0.5, 0.75])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def _quads(X, Y, Z):
    """Grid of points (n, m) to a list of quads."""
    out = []
    for i in range(X.shape[0] - 1):
        for j in range(X.shape[1] - 1):
            out.append([(X[i, j], Y[i, j], Z[i, j]), (X[i + 1, j], Y[i + 1, j], Z[i + 1, j]),
                        (X[i + 1, j + 1], Y[i + 1, j + 1], Z[i + 1, j + 1]),
                        (X[i, j + 1], Y[i, j + 1], Z[i, j + 1])])
    return out


def _shade(polys, rgb):
    cols = []
    for p in polys:
        a, b, c = (np.array(p[k]) for k in (0, 1, 2))
        n = np.cross(b - a, c - a)
        norm = np.linalg.norm(n)
        k = 0.35 + 0.65 * abs(n @ LIGHT) / norm if norm > 0 else 0.6
        cols.append(tuple(min(1.0, ch * k) for ch in rgb) + (1.0,))
    return cols


def _section(camber, thick, n=25):
    """Closed NACA four-digit loop (x/c, z/c), trailing edge round to trailing edge."""
    x, z = naca.coordinates(camber, thick, n=n)
    return np.asarray(x), np.asarray(z)


def lifting_surface(x_le_root, y0, z0, span_half, c_root, c_tip, le_sweep, camber, thick,
                    vertical=False, n_span=12):
    """Quads of one straight-tapered half surface (or a fin when vertical)."""
    xs, zs = _section(camber, thick)
    eta = np.linspace(0.0, 1.0, n_span)
    X = np.empty((n_span, xs.size))
    Y = np.empty_like(X)
    Z = np.empty_like(X)
    for i, e in enumerate(eta):
        c = c_root + (c_tip - c_root) * e
        xl = x_le_root + le_sweep * e * span_half
        if vertical:
            X[i], Y[i], Z[i] = xl + xs * c, y0 + zs * c, z0 + e * span_half
        else:
            X[i], Y[i], Z[i] = xl + xs * c, y0 + e * span_half, z0 + zs * c
    return _quads(X, Y, Z)


def body_of_revolution(L_f, D_f, n_x=60, n_t=32):
    def radius(x):
        t = x / L_f
        if t < 0.2:
            return 0.5 * D_f * (1 - (1 - t / 0.2) ** 2) ** 0.5
        if t > 0.6:
            return 0.5 * D_f * max(0.15, 1 - (t - 0.6) / 0.4 * 0.85)
        return 0.5 * D_f
    xs = np.linspace(0.0, L_f, n_x)
    th = np.linspace(0.0, 2 * math.pi, n_t)
    R = np.array([radius(x) for x in xs])
    X = np.repeat(xs[:, None], n_t, 1)
    Y = R[:, None] * np.cos(th)[None, :]
    Z = R[:, None] * np.sin(th)[None, :]
    return _quads(X, Y, Z), radius


def ellipsoid(cx, cy, cz, a, b, c, n=16):
    u = np.linspace(0, math.pi, n)
    v = np.linspace(0, 2 * math.pi, 2 * n)
    X = cx + a * np.outer(np.cos(u), np.ones_like(v))
    Y = cy + b * np.outer(np.sin(u), np.cos(v))
    Z = cz + c * np.outer(np.sin(u), np.sin(v))
    return _quads(X, Y, Z)


def build(d):
    w, ht, vt, fus = d["wing"], d["horizontal_tail"], d["vertical_tail"], d["fuselage"]
    lay = d["layout"]
    L_f, D_f = fus["length"], fus["diameter"]
    parts = []
    body, radius = body_of_revolution(L_f, D_f)
    parts.append((body, (0.82, 0.84, 0.88)))
    half = w["span"] / 2
    for sgn in (1, -1):
        q = lifting_surface(lay["x_le"], 0.0, -0.1 * D_f, sgn * half, w["root_chord"], w["tip_chord"], 0.0, 4, 15)
        parts.append((q, (0.30, 0.45, 0.80)))
    x_ht = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * ht["mac"]
    for sgn in (1, -1):
        q = lifting_surface(x_ht, 0.0, 0.3 * D_f, sgn * ht["span"] / 2, ht["root_chord"], ht["tip_chord"], 0.0, 0, 12)
        parts.append((q, (0.30, 0.65, 0.40)))
    x_vt = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * vt["mac"]
    q = lifting_surface(x_vt, 0.0, radius(x_vt) * 0.6, vt["height"], vt["root_chord"], 0.5 * vt["root_chord"],
                        0.35, 0, 12, vertical=True)
    parts.append((q, (0.30, 0.65, 0.40)))
    gt = lay["gear_track"]
    if gt.get("sponson_length_ft"):
        sl, sd = gt["sponson_length_ft"], gt["sponson_depth_ft"]
        for sgn in (1, -1):
            parts.append((ellipsoid(lay["x_main"] - 0.3 * sl, sgn * gt["half_track_ft"], -0.1 * D_f - 0.45 * sd,
                                    sl / 2, 0.45 * sd, 0.5 * sd), (0.55, 0.42, 0.30)))
    # sensor turret under the nose at the payload station
    x_p = d["stations"]["payload"]["x"]
    parts.append((ellipsoid(x_p, 0.0, -0.5 * D_f, 0.45, 0.45, 0.45), (0.15, 0.15, 0.15)))
    # propeller: three blades at the tail (pusher) or nose (tractor)
    R = d["propeller_diameter_ft"] / 2
    x_pr = L_f + 0.15 if d["concept"] == "pusher" else -0.15
    blades = []
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.3
        ca, sa = math.cos(a), math.sin(a)
        cw = 0.35
        blades.append([(x_pr - 0.05, -0.5 * cw * sa, 0.5 * cw * ca), (x_pr + 0.05, 0.5 * cw * sa, -0.5 * cw * ca),
                       (x_pr + 0.05, R * ca + 0.2 * cw * sa, R * sa - 0.2 * cw * ca),
                       (x_pr - 0.05, R * ca - 0.2 * cw * sa, R * sa + 0.2 * cw * ca)])
    parts.append((blades, (0.20, 0.20, 0.20)))
    return parts


def _axes(fig, rect, parts, d, elev, azim, zoom, title):
    ax = fig.add_axes(rect, projection="3d")
    for polys, rgb in parts:
        ax.add_collection3d(Poly3DCollection(polys, facecolors=_shade(polys, rgb), edgecolors="none"))
    span, L_f = d["wing"]["span"], d["fuselage"]["length"]
    ax.set_xlim(-1, L_f + 1)
    ax.set_ylim(-span / 2 - 0.5, span / 2 + 0.5)
    ax.set_zlim(-5, 8)
    ax.set_box_aspect((L_f + 2, span + 1, 13), zoom=zoom)
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(title, fontsize=10, y=0.92)
    ax.set_axis_off()
    return ax


def render(d, path, title):
    """A large three-quarter view over three smaller ones (rear three-quarter, top, side)."""
    parts = build(d)
    fig = plt.figure(figsize=(14, 13))
    _axes(fig, [0.0, 0.36, 1.0, 0.62], parts, d, 20, -128, 1.55, "Three-quarter view, front left")
    _axes(fig, [0.0, 0.0, 0.34, 0.38], parts, d, 18, 38, 1.7, "Rear right")
    _axes(fig, [0.33, 0.0, 0.34, 0.38], parts, d, 90, -90, 1.3, "Top")
    _axes(fig, [0.66, 0.0, 0.34, 0.38], parts, d, 0, -90, 1.7, "Side")
    fig.suptitle(title, fontsize=11, y=0.995)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.design) as f:
        d = json.load(f)
    eng = d["engine"].get("fixed", "rubber")
    title = (f"Task 12 {d['concept']} UAV, {eng}: W0 {d['W0_lb']:,.0f} lb, span {d['wing']['span']:.1f} ft, "
             f"length {d['fuselage']['length']:.1f} ft.\nConceptual render from the Stage 1 records; sections "
             "drawn as NACA 4415 / 0012 for display; gear retracted in sponsons")
    render(d, a.out, title)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

"""Renders of the loft with matplotlib only (decision PD-2): flat-shaded triangles, one light. Every picture is
made by code from the exported STL and carries the label "geometry only, no flow solution" (roadmap rendering
rules 1, 4 and 5: sidecar record, made by code, unsolved designs labelled)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

LIGHT = np.array([-0.4, -0.5, 0.75]) / np.linalg.norm([-0.4, -0.5, 0.75])
COLOURS = {"fuselage": (0.82, 0.84, 0.88), "wing": (0.30, 0.45, 0.80), "horizontal_tail": (0.30, 0.65, 0.40),
           "vertical_tail": (0.30, 0.65, 0.40), "sponson_left": (0.55, 0.42, 0.30), "sponson_right": (0.55, 0.42, 0.30),
           "turret": (0.15, 0.15, 0.15), "spinner": (0.35, 0.35, 0.35)}
# name: (elevation, azimuth, projection, title)
VIEWS = {"top": (90, -90, "ortho", "Top view"), "side": (0, -90, "ortho", "Side view"),
         "front": (0, 180, "ortho", "Front view"), "perspective": (22, -128, "persp", "Perspective, front left")}


def view(parts, name, path, label, propeller=None):
    """One picture of the parts {name: (V, T)}. The propeller is drawn as a thin ring (its disc), not as blades."""
    elev, azim, proj, title = VIEWS[name]
    fig = plt.figure(figsize=(11, 7.5))
    ax = fig.add_axes([0, 0, 1, 0.93], projection="3d")
    ax.set_proj_type(proj)
    allv = np.vstack([V for V, _ in parts.values()])
    for part, (V, T) in parts.items():
        P = V[T]
        n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-30
        shade = 0.35 + 0.65 * np.abs(n @ LIGHT)
        ax.add_collection3d(Poly3DCollection(P, facecolors=np.clip(np.outer(shade, COLOURS[part]), 0, 1), edgecolors="none"))
    if propeller:
        a = np.linspace(0, 2 * np.pi, 121)
        ax.plot(np.full_like(a, propeller["x"]), propeller["radius"] * np.cos(a), propeller["z"] + propeller["radius"] * np.sin(a),
                color="0.2", lw=0.8)
    lo, hi = allv.min(0), allv.max(0)
    c, r = (lo + hi) / 2, (hi - lo).max() / 2
    for k, f in enumerate((ax.set_xlim, ax.set_ylim, ax.set_zlim)):
        f(c[k] - r, c[k] + r)
    ax.set_box_aspect((1, 1, 1), zoom=1.7)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.suptitle(f"{title}. {label}", fontsize=10, y=0.98)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def arrangement(fus_lines, boxes, wing_root, path, label):
    """Side and top view of the fuselage outline with the internal boxes (E4). fus_lines: x, half breadth, top,
    bottom of the fuselage; boxes: {name: {"lo", "hi"}}; wing_root: (x_le, chord, z0) for the chord line."""
    x, half, top, bottom = fus_lines
    fig, axes = plt.subplots(2, 1, figsize=(12, 8.5), gridspec_kw={"height_ratios": [1, 2.6]})
    for ax, (i, j, upper, lower, ylabel) in zip(axes, ((0, 2, top, -np.asarray(bottom), "z (ft), side view"),
                                                       (0, 1, half, -np.asarray(half), "y (ft), top view"))):
        ax.plot(x, upper, "k-", lw=1.0)
        ax.plot(x, lower, "k-", lw=1.0)
        for k, (name, b) in enumerate(boxes.items()):
            if "main_gear" in name and j == 2:
                continue
            w, h = b["hi"][i] - b["lo"][i], b["hi"][j] - b["lo"][j]
            ax.add_patch(plt.Rectangle((b["lo"][i], b["lo"][j]), w, h, fill=False, ec=f"C{k % 10}", lw=1.1))
            ax.text(b["lo"][i] + 0.03, b["hi"][j] - 0.03, name.replace("_", " "), fontsize=5.5, va="top", color=f"C{k % 10}")
        ax.set_ylabel(ylabel)
        ax.set_aspect("equal")
        ax.set_xlim(-1.0, 30.0)
        ax.grid(alpha=0.3)
    axes[0].plot([wing_root[0], wing_root[0] + wing_root[1]], [wing_root[2]] * 2, color="0.5", lw=2.0)
    axes[1].set_xlabel("x from the nose (ft)")
    axes[1].set_ylim(-6.0, 6.0)
    fig.suptitle(f"Internal arrangement, boxes of E4. {label}", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

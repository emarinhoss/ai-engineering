"""Contour pictures from an SU2 Tecplot ASCII volume file (flow.dat, OUTPUT_FILES with TECPLOT_ASCII).

Usage:
    python -m postprocess.plot_flowfield inlet CASE_DIR --out PNG      (Mach, p/p_inf, T/T_inf, schlieren)
    python -m postprocess.plot_flowfield inlet CASE_DIR --out PNG --only mach|p|T|schlieren   (one panel)
    python -m postprocess.plot_flowfield cylinder CASE_DIR --out PNG   (Mach + stand-off against Billig)

CASE_DIR holds flow.dat, params.json and geometry.json written by worker.make_case / run_case.
Pure plotting: every value shown is read from the file; the only analytic line is Billig's
stand-off correlation (physics.heating.billig_standoff). The cylinder command also writes
PNG's sibling standoff.json with the measured and the Billig stand-off.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
from scipy.interpolate import griddata

from physics.atmosphere import state
from physics.heating import billig_standoff
from postprocess.tecplot import read_tecplot_ascii

GAMMA = 1.4


def load_volume(case_dir):
    """Nodes (x, y), a triangulation of the quad mesh, and the variables of flow.dat."""
    case_dir = Path(case_dir)
    path = case_dir / "flow.dat"
    if not path.exists() and (case_dir / "flow.dat.gz").exists():     # committed records are gzipped
        import gzip, tempfile
        tmp = Path(tempfile.mkdtemp()) / "flow.dat"
        tmp.write_bytes(gzip.open(case_dir / "flow.dat.gz").read())
        path = tmp
    data = read_tecplot_ascii(path)
    x, y = data["data"]["x"], data["data"]["y"]
    tris = []
    for _, conn in data["elements"]:
        if conn.shape[1] == 4:                      # split each quad into two triangles
            tris.append(conn[:, [0, 1, 2]]); tris.append(conn[:, [0, 2, 3]])
        else:
            tris.append(conn)
    tri = mtri.Triangulation(x, y, np.vstack(tris))
    params = json.loads((case_dir / "params.json").read_text())
    geometry = json.loads((case_dir / "geometry.json").read_text())
    return tri, data["data"], params, geometry


def freestream(params):
    fs = state(params.get("altitude_km", 30))
    return fs["p"], fs["T"]


def schlieren(tri, rho, window, n=(900, 450)):
    """|grad rho| on a uniform grid inside window = (x0, x1, y0, y1), log-scaled for display."""
    x0, x1, y0, y1 = window
    gx, gy = np.meshgrid(np.linspace(x0, x1, n[0]), np.linspace(y0, y1, n[1]))
    r = griddata((tri.x, tri.y), rho, (gx, gy), method="linear")
    dr_dy, dr_dx = np.gradient(r, gy[:, 0], gx[0, :])
    g = np.hypot(dr_dx, dr_dy)
    scale = np.nanpercentile(g[np.isfinite(g)], 98)            # shocks saturate, weak waves stay visible
    return gx, gy, np.sqrt(np.clip(g / scale, 0.0, 1.0))


def inlet_outline(ax, g, color="k"):
    """Body (ramp 1, ramp 2 to the throat) and cowl from geometry.json."""
    C, Eb, P, Ec, G = (np.array(g[k]) for k in ("C", "E_body", "P", "E_cowl", "G"))
    ax.plot([0.0, C[0], Eb[0]], [0.0, C[1], Eb[1]], color=color, lw=1.2)
    ax.plot([P[0], Ec[0]], [P[1], Ec[1]], color=color, lw=1.2)
    ax.plot([P[0], G[0]], [P[1], G[1]], color=color, lw=1.2)
    ax.fill([0.0, C[0], Eb[0], Eb[0], 0.0], [0.0, C[1], Eb[1], -0.01, -0.01], color="#dddddd", zorder=3)


def plot_inlet_panel(case_dir, out_png, which):
    """One wide panel for a slide: which in {"mach", "p", "T", "schlieren"}."""
    tri, v, params, g = load_volume(case_dir)
    p_inf, T_inf = freestream(params)
    x1 = float(g["E_body"][0]) + 0.01
    window = (float(g["x_in"]), x1, -0.005, 0.6 * float(g["y_top"]))
    fig, ax = plt.subplots(figsize=(10, 4.6), constrained_layout=True)
    if which == "schlieren":
        gx, gy, sch = schlieren(tri, v["Density"], window, n=(1600, 800))
        ax.pcolormesh(gx, gy, sch, cmap="gray_r", shading="auto", vmin=0, vmax=1)
        label = "numerical schlieren, |grad rho| (darker = steeper)"
    else:
        field, label = {"mach": (v["Mach"], "Mach number"), "p": (v["Pressure"] / p_inf, "p / p_inf"),
                        "T": (v["Temperature"] / T_inf, "T / T_inf")}[which]
        lo, hi = np.nanpercentile(field, [0.5, 99.5])
        cf = ax.tricontourf(tri, field, levels=np.linspace(lo, hi, 41), cmap="viridis", extend="both")
        fig.colorbar(cf, ax=ax, label=label, shrink=0.85)
    inlet_outline(ax, g)
    ax.set_xlim(window[0], window[1]); ax.set_ylim(window[2], window[3]); ax.set_aspect("equal")
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    t1, t2 = params["theta1_deg"], params["theta2_deg"]
    ax.set_title(f"{label}: theta1 = {t1} deg, theta2 = {t2} deg, {params['mesh_level']} mesh, laminar, Mach "
                 f"{params.get('mach', 4.0)} ({Path(case_dir).name})", fontsize=10)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def plot_inlet(case_dir, out_png):
    tri, v, params, g = load_volume(case_dir)
    p_inf, T_inf = freestream(params)
    x1 = float(g["E_body"][0]) + 0.01
    window = (float(g["x_in"]), x1, -0.005, 0.6 * float(g["y_top"]))
    mask = np.zeros(tri.triangles.shape[0], dtype=bool)
    fields = [("Mach", v["Mach"], "Mach number", None),
              ("p/p_inf", v["Pressure"] / p_inf, "static pressure p / p_inf", None),
              ("T/T_inf", v["Temperature"] / T_inf, "static temperature T / T_inf", None)]
    fig, axes = plt.subplots(4, 1, figsize=(9, 12), constrained_layout=True)
    for ax, (name, field, label, _) in zip(axes[:3], fields):
        lo, hi = np.nanpercentile(field, [0.5, 99.5])
        cf = ax.tricontourf(tri, field, levels=np.linspace(lo, hi, 41), cmap="viridis", extend="both")
        fig.colorbar(cf, ax=ax, label=label, shrink=0.9)
        inlet_outline(ax, g)
        ax.set_xlim(window[0], window[1]); ax.set_ylim(window[2], window[3]); ax.set_aspect("equal")
        ax.set_ylabel("y (m)")
    gx, gy, s = schlieren(tri, v["Density"], window, n=(1400, 700))
    ax = axes[3]
    ax.pcolormesh(gx, gy, s, cmap="gray_r", shading="auto", vmin=0, vmax=1)
    inlet_outline(ax, g)
    ax.set_xlim(window[0], window[1]); ax.set_ylim(window[2], window[3]); ax.set_aspect("equal")
    ax.set_ylabel("y (m)"); ax.set_xlabel("x (m)")
    ax.set_title("numerical schlieren: |grad rho| (darker = steeper; saturated at the 98th percentile)", fontsize=10)
    t1, t2 = params["theta1_deg"], params["theta2_deg"]
    fig.suptitle(f"inlet2r theta1 = {t1} deg, theta2 = {t2} deg, {params['mesh_level']} mesh, laminar, "
                 f"Mach {params.get('mach', 4.0)} at 30 km ({Path(case_dir).name})", fontsize=11)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def standoff_from_stagnation_line(tri, v, R, M, n=4000):
    """Shock position on the stagnation line (y = 0, x < -R): the most upstream point where the
    density exceeds the mean of the freestream and the normal-shock values (the wall layer, where
    the cold-wall density is largest, is thereby left out). Returns delta / R and the profile."""
    xs = np.linspace(-R * 3.4, -R * 1.001, n)
    rho = griddata((tri.x, tri.y), v["Density"], (xs, np.zeros_like(xs)), method="linear")
    ok = np.isfinite(rho)
    xs, rho = xs[ok], rho[ok]
    rho_inf = rho[0]
    rho_ns = rho_inf * (GAMMA + 1) * M**2 / ((GAMMA - 1) * M**2 + 2)        # normal-shock density ratio
    i = int(np.argmax(rho > 0.5 * (rho_inf + rho_ns)))
    x_shock = 0.5 * (xs[i - 1] + xs[i]) if i > 0 else xs[0]
    return (-x_shock - R) / R, xs, rho


def plot_cylinder(case_dir, out_png):
    tri, v, params, g = load_volume(case_dir)
    R = float(params.get("radius_m") or g.get("R") or 0.01)
    M = float(params.get("mach", 4.0))
    delta_R, xs, rho = standoff_from_stagnation_line(tri, v, R, M)
    billig = billig_standoff(M)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 5.2), constrained_layout=True,
                                  gridspec_kw={"width_ratios": [1.25, 1]})
    lo, hi = 0.0, float(np.nanpercentile(v["Mach"], 99.5))
    cf = ax.tricontourf(tri, v["Mach"], levels=np.linspace(lo, hi, 41), cmap="viridis", extend="max")
    fig.colorbar(cf, ax=ax, label="Mach number", shrink=0.9)
    th = np.linspace(0, np.pi, 200)
    ax.fill(R * np.cos(th + np.pi / 2) * 0 + (-R * np.cos(th)), R * np.sin(th), color="#dddddd", zorder=3)
    ax.plot(-R * np.cos(th), R * np.sin(th), color="k", lw=1)
    ax.axvline(-R * (1 + delta_R), color="#D55E00", lw=1, ls="--", label=f"measured stand-off: delta/R = {delta_R:.3f}")
    ax.axvline(-R * (1 + billig), color="k", lw=1, ls=":", label=f"Billig: delta/R = {billig:.3f}")
    ax.set_xlim(-3.2 * R, 1.2 * R); ax.set_ylim(0, 2.6 * R); ax.set_aspect("equal")
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); ax.legend(loc="upper right", fontsize=9)
    ax.set_title(f"cylinder R = {R * 1e3:.0f} mm, {params['mesh_level']} mesh, laminar, Mach {M}", fontsize=10)
    ax2.plot((-xs - R) / R, rho, color="#1F3A5F")
    ax2.axvline(delta_R, color="#D55E00", ls="--", lw=1); ax2.axvline(billig, color="k", ls=":", lw=1)
    ax2.set_xlabel("distance from the wall along the stagnation line, (-x - R) / R")
    ax2.set_ylabel("density (kg/m^3)"); ax2.set_title("stagnation-line density: the shock is the jump", fontsize=10)
    ax2.invert_xaxis()
    fig.savefig(out_png, dpi=160)
    plt.close(fig)
    out = {"case": Path(case_dir).name, "mach": M, "R_m": R, "delta_over_R_measured": float(delta_R),
           "delta_over_R_billig": float(billig), "deviation_pct": float(100 * (delta_R / billig - 1)),
           "method": "most upstream point on y = 0 where the linearly interpolated density exceeds the mean of the freestream and the normal-shock density (x from -3.4R)",
           "tolerance_pct_report": 15}
    Path(out_png).with_name("standoff.json").write_text(json.dumps(out, indent=1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["inlet", "cylinder"])
    ap.add_argument("case_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["mach", "p", "T", "schlieren"], help="inlet: one panel instead of four")
    a = ap.parse_args(argv)
    if a.kind == "inlet" and a.only:
        plot_inlet_panel(a.case_dir, a.out, a.only); print(f"wrote {a.out}")
    elif a.kind == "inlet":
        plot_inlet(a.case_dir, a.out); print(f"wrote {a.out}")
    else:
        out = plot_cylinder(a.case_dir, a.out)
        print(f"wrote {a.out}; stand-off delta/R = {out['delta_over_R_measured']:.3f}, "
              f"Billig {out['delta_over_R_billig']:.3f} ({out['deviation_pct']:+.1f} percent)")


if __name__ == "__main__":
    main()

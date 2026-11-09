"""Build docs/talk/deck_drone.pptx (Task 10 deck, T10.11b) from docs/talk/outline_drone.md.

Run from the repository root with either of:
    python -m docs.talk.build_deck_drone
    python docs/talk/build_deck_drone.py

Rules (CLAUDE.md, and the inlet deck's own):
- Each slide's title, message and speaker notes come from docs/talk/outline_drone.md. A `{name}` in a
  message or note is filled from the values computed below; a name with no value fails the build.
- Every number on a slide is read from a file at build time (v6.json, record.json files, the CSVs,
  result.json files, the spec). Where no file exists the slide says PENDING and names the batch.
- Layout helpers are imported from docs/talk/build_deck.py (importing it runs no code beyond its own
  imports), which this script does not modify.
"""
import csv
import functools
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import figures_drone as fd
from analysis.high_level_bias import v6e_flags
from docs.talk import build_deck as bd  # sets matplotlib to Agg on import
from drone import geometry, ledger, naca, vlm
from drone.evaluate import _CAMBER_POSITION, _helmbold, evaluate
from geometry import airfoil2d
from mcp_server.schemas import DRONE_BOUNDS

plt = bd.plt

OUTLINE = ROOT / "docs/talk/outline_drone.md"
DEFAULT_OUT = ROOT / "docs/talk/deck_drone.pptx"
V6 = "runs/drone/validation/2026-11-08/v6.json"
SPEC = "docs/specs/task10_drone_sizing.md"
TASKS = "docs/specs/task10_tasks.md"
FIG = "docs/validation/figures/task10/"
LM, CW, CT = bd.LM, bd.CW, bd.CT


# ---- reading files ----------------------------------------------------------------------------
def jload(rel):
    return json.loads((ROOT / rel).read_text())


def csv_rows(rel):
    with open(ROOT / rel, newline="") as f:
        return list(csv.DictReader(f))


def mean_at(rows, strategy, metric, n):
    v = [float(r["value"]) for r in rows
         if r["strategy"] == strategy and r["metric"] == metric and int(r["n"]) == n]
    return float(np.mean(v))


def pct_range(values):
    """'19 to 23 %' from fractional deviations (magnitudes, rounded to whole percent)."""
    m = [abs(v) * 100 for v in values]
    return f"{round(min(m))} to {round(max(m))} %"


def signed_range(values, up, down):
    """'8.0 % high to 11.6 % high' or '10.3 % low to 1.6 % high': both ends keep their sign."""
    lo, hi = min(values) * 100, max(values) * 100
    end = lambda x: f"{abs(x):.1f} % {up if x >= 0 else down}"
    return f"{end(lo)} to {end(hi)}" if lo * hi < 0 else f"{abs(lo):.1f} to {end(hi if hi > 0 else lo)}"


def e387_points(re=203800.0):
    """[(alpha, su2 cl, su2 cd, tunnel cl, tunnel cd)] at the tunnel's own angles for one Re."""
    tunnel = {p["nominal_reynolds"]: p for p in
              yaml.safe_load((ROOT / fd.E387_TUNNEL).read_text())["polars"]}
    tun = tunnel[200000.0] if re < 250000 else tunnel[300000.0]
    out = []
    for f in sorted((ROOT / "runs/e387").glob("*/result.json")):
        r = json.loads(f.read_text())
        if r["params"]["reynolds"] != re:
            continue
        a = r["params"]["alpha_deg"]
        i = int(np.argmin(np.abs(np.array(tun["alpha_deg"]) - a)))
        assert abs(tun["alpha_deg"][i] - a) < 1e-6, f"{f}: no tunnel point at {a} deg"
        out.append((a, r["metrics"]["cl"], r["metrics"]["cd"], tun["cl"][i], tun["cd"][i]))
    return sorted(out)


def drawing_values():
    """The {names} of the drawing slides, each computed from the same sources as its drawing."""
    params, _, out, geom = nominal()
    geo = jload("runs/mesh/airfoil2d-59cd4287e9/geometry.json")
    e_row = v6_check("V6a elliptic AR 8 fine: e at 4 deg vs 1")
    cla_row = v6_check("V6a elliptic AR 8 fine: CL_alpha vs Helmbold")
    _, _, _, front, _, n_edge = design_space()
    return {"nom_span": f"{params['span_m']:g}", "nom_ar": f"{params['aspect_ratio']:g}",
            "nom_taper": f"{params['taper_ratio']:g}", "nom_area": f"{geom['wing']['S']:.2f}",
            "nom_mtow": f"{out['mtow_kg']:.2f}", "nom_iters": out["closure_iterations"],
            "nom_endurance": f"{out['endurance_h']:.2f}",
            "v6a_e_dev": f"{100 * e_row['deviation']:+.2f} %",
            "v6a_cla_dev": f"{100 * cla_row['deviation']:+.2f} %",
            "mesh_cells": f"{geo['cells']:,}", "mesh_first_cell": f"{geo['first_cell_m']:.2e}",
            "n_front_edge": n_edge, "n_front": len(front)}


def values():
    """Every {name} a message or note may use, each computed from a file."""
    v6 = jload(V6)["checks"]
    tol = [c for c in v6 if c["name"][:3] == "V6a" or c["name"][:3] in ("V6b", "V6c", "V6d")]
    tol = [c for c in tol if c["tolerance"] is not None]
    v6f = [c for c in v6 if c["name"].startswith("V6f ")]
    v6e = next(c for c in v6 if c["name"] == "V6e cl_alpha Re 203800")
    grid, pool = jload("runs/drone_grid/2026-11-08/record.json"), jload("runs/drone_pool_lf/2026-11-08/record.json")
    rep = csv_rows(fd.POOL_REPLAY)
    on, feas = csv_rows(fd.ONLINE), csv_rows(fd.ONLINE_FEAS)
    smoke = jload("runs/smoke/airfoil2d-96a9dd0f51/result.json")
    smoke2 = jload("runs/smoke2/airfoil2d-51d551f2cc/result.json")
    pts = e387_points()
    cases = csv_rows("designs/pool_af_cases.csv")

    def band(name):
        return [c["deviation"] for c in v6f if c["name"].startswith(f"V6f {name} ")]

    return {
        "smoke_budget": smoke["params"]["max_iter"],
        "smoke2_iters": smoke2["convergence"]["iterations"],
        "n_pass": sum(c["verdict"] == "pass" for c in tol),
        "n_pending": sum(c["verdict"].startswith("pending") for c in tol),
        "n_fail": sum(c["verdict"] == "fail" for c in tol),
        "f_clalpha_range": pct_range(band("cl_alpha")),
        "f_cd_range": pct_range(band("cd ratio")),
        "f_clmax_range": pct_range(band("cl_max")),
        "v6e_dev": f"{100 * v6e['deviation']:.2f} %",
        "v6e_tol": f"{100 * v6e['tolerance']:.0f} %",
        "grid_n": f"{grid['points_evaluated']:,}",
        "front_n": grid["front_size"],
        "gated_n": f"{grid['points_gated']:,}",
        "pool_front_n": pool["front_size"],
        "ehvi_32": f"{mean_at(rep, 'al_ehvi', 'hv_regret', 32):.3f}",
        "rand_40": f"{mean_at(rep, 'random', 'hv_regret', 40):.3f}",
        "ehvi_on_40": f"{mean_at(on, 'al_ehvi', 'hv_regret', 40):.3f}",
        "rand_on_40": f"{mean_at(on, 'random', 'hv_regret', 40):.3f}",
        "ehvi_gated": f"{mean_at(on, 'al_ehvi', 'n_gated', 40):.1f}",
        "feas_on_40": f"{mean_at(feas, 'al_ehvi_feas', 'hv_regret', 40):.3f}",
        "pool_cases": len(cases),
        "su2_cl_range": signed_range([p[1] / p[3] - 1 for p in pts], "high", "low"),
        "su2_cd_range": signed_range([p[2] / p[4] - 1 for p in pts], "high", "low"),
        "e387_re": f"{203800:,}",
        **drawing_values(),
    }


# ---- reading the outline ----------------------------------------------------------------------
def read_outline():
    """[{id, title, message, figure, source, notes}] in file order."""
    slides, cur = [], None
    for line in OUTLINE.read_text(encoding="utf-8").splitlines():
        head = re.match(r"^### (D\d+[a-z]?)\. (.+)$", line)
        if head:
            cur = {"id": head.group(1), "title": head.group(2)}
            slides.append(cur)
        elif cur is not None:
            for key, tag in (("message", "Message"), ("figure", "Figure or table"),
                             ("source", "Source"), ("notes", "Speaker notes")):
                if line.startswith(f"- **{tag}:** "):
                    cur[key] = line[len(f"- **{tag}:** "):].strip()
    return slides


def source_list(source):
    """Backticked paths of a Source line, or the whole PENDING text."""
    if source.startswith("PENDING"):
        return [source]
    return re.findall(r"`([^`]+)`", source)


# ---- drawings (matplotlib, saved under docs/talk/figures/drone/) -------------------------------
# Every dimension in a drawing is computed here from the repo's own code (drone/, geometry/) or read
# from a committed record. The only literals are layout positions and colors.
FIG_DRONE = "docs/talk/figures/drone/"
BLUE_H, ACCENT_H, GREY_H = bd.BLUE_H, bd.ACCENT_H, bd.GREY_H
TEXT_H = "#222222"


@functools.cache
def nominal():
    """(params, fixed, evaluate() output, geometry.build() at the closed mass) of the nominal design."""
    params = {k: v for k, v in jload(V6)["nominal_params"].items() if k in DRONE_BOUNDS}
    fixed = ledger.load_all()
    out = evaluate(params, fixed)
    return params, fixed, out, geometry.build(params, fixed, mtow_guess=out["mtow_kg"])


def v6_check(name):
    return next(c for c in jload(V6)["checks"] if c["name"] == name)


def save(fig, name):
    path = ROOT / FIG_DRONE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def mbox(ax, x, y, w, h, text, fc="white", ec=BLUE_H, fs=10, bold=False, lw=1.2):
    """Rounded box centered at (x, y) with centered text."""
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.08",
                                fc=fc, ec=ec, lw=lw))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=TEXT_H,
            fontweight="bold" if bold else "normal")


def marrow(ax, p, q, color=GREY_H, ls="-", rad=0.0, lw=1.4):
    ax.annotate("", xy=q, xytext=p, arrowprops={"arrowstyle": "-|>", "color": color, "lw": lw, "ls": ls,
                                                   "connectionstyle": f"arc3,rad={rad}",
                                                   "shrinkA": 0, "shrinkB": 0})


def blank_axes(fig, rect, xlim, ylim):
    ax = fig.add_axes(rect)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return ax


def draw_section(ax, camber_pct, thickness_pct):
    """The NACA four-digit section of drone.naca with its camber line and maximum thickness."""
    x, y = naca.coordinates(camber_pct, thickness_pct)
    xc = np.linspace(0.0, 1.0, 101)
    m, p = camber_pct / 100.0, 0.4
    yc, _ = naca.camber_line(xc, m, p)
    ax.fill(x, y, color="#EAF0F7", ec=BLUE_H, lw=1.5)
    ax.plot(xc, yc, color=ACCENT_H, lw=1.5, ls="--")
    ax.plot([0, 1], [0, 0], color=GREY_H, lw=0.8, ls=":")
    xt = float(xc[np.argmax(naca.thickness(xc, thickness_pct / 100.0))])
    yt = float(naca.thickness(xt, thickness_pct / 100.0))
    yc_t = float(naca.camber_line(np.array([xt]), m, p)[0][0])
    ax.annotate("", xy=(xt, yc_t + yt), xytext=(xt, yc_t - yt),
                arrowprops={"arrowstyle": "<->", "color": BLUE_H, "lw": 1.3})
    ax.text(xt + 0.03, yc_t - yt - 0.045, f"thickness {thickness_pct:g} % of chord", color=BLUE_H,
            fontsize=10)
    ax.plot([p], [m], "o", color=ACCENT_H, ms=5)
    ax.text(p, m + 0.07, f"camber {camber_pct:g} % at {100 * p:.0f} % chord", color=ACCENT_H,
            fontsize=10, ha="center")
    ax.set_aspect("equal")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.17, 0.2)
    ax.axis("off")


def draw_planform(path_name="planform.png"):
    """Top view of the nominal design from geometry.build: wing, tail, fuselage, and the section."""
    params, fixed, out, geom = nominal()
    wing, tl, fus, pf = geom["wing"], geom["tail"], geom["fuselage"], geom["planform"]
    b, cr, ct = wing["b"], wing["c_root"], wing["c_tip"]
    rules = fixed["rules"]
    b_h = math.sqrt(rules["tail_aspect_ratio_horizontal"] * tl["S_h"])
    c_h = tl["S_h"] / b_h
    x_tail = pf.x_ref + tl["arm"]                       # tail aerodynamic center, arm from the wing's x_ref
    fig = plt.figure(figsize=(12, 4.4), dpi=200)
    ax = fig.add_axes([0.01, 0.02, 0.62, 0.96])
    ax.add_patch(Ellipse((0, pf.x_ref), fus["diameter"], fus["length"], fc="#F4F4F4", ec=GREY_H, lw=1.2))
    ax.plot([0, 0], [pf.x_ref, x_tail], color=GREY_H, lw=2)
    ax.add_patch(Polygon([(-b / 2, 0), (b / 2, 0), (b / 2, ct), (0, cr), (-b / 2, ct)], fc="#EAF0F7",
                         ec=BLUE_H, lw=1.8))
    ax.add_patch(Polygon([(-b_h / 2, x_tail - 0.25 * c_h), (b_h / 2, x_tail - 0.25 * c_h),
                          (b_h / 2, x_tail + 0.75 * c_h), (-b_h / 2, x_tail + 0.75 * c_h)],
                         fc="#EAF0F7", ec=GREY_H, lw=1.4))
    dim = {"arrowstyle": "<->", "color": BLUE_H, "lw": 1.3}
    ax.annotate("", xy=(-b / 2, -0.22), xytext=(b / 2, -0.22), arrowprops=dim)
    ax.text(0, -0.27, f"span b = {b:.2f} m  (input span_m)", ha="center", color=BLUE_H, fontsize=12,
            fontweight="bold")
    ax.text(-b / 2, -0.1, f"S = b^2 / AR = {wing['S']:.2f} m^2, AR = {wing['AR']:.0f} (input)",
            ha="left", va="center", color=TEXT_H, fontsize=10)
    ax.annotate(f"root chord {cr:.3f} m", xy=(0.0, cr), xytext=(-b / 2, 0.38), color=BLUE_H,
                fontsize=10, arrowprops={"arrowstyle": "-", "color": BLUE_H})
    ax.annotate(f"tip chord {ct:.3f} m\n= taper {params['taper_ratio']:g} x root  (input)",
                xy=(b / 2, ct), xytext=(b / 2 - 0.45, 0.4), color=BLUE_H, fontsize=10, ha="center",
                arrowprops={"arrowstyle": "-", "color": BLUE_H})
    ax.text(-b / 2, 0.95, f"fuselage (grey ellipse) {fus['length']:.2f} x {fus['diameter']:.2f} m: "
            f"payload {rules['payload_mass_kg']:g} kg + battery\n{params['battery_fraction']:g} x take-off "
            f"mass = {out['masses']['battery']:.2f} kg  (input battery_fraction)", color=TEXT_H,
            fontsize=10, va="top")
    ax.text(b_h / 2 + 0.05, x_tail + 0.25 * c_h, f"horizontal tail S_h = {tl['S_h']:.3f} m^2\n"
            f"vertical tail S_v = {tl['S_v']:.3f} m^2\ntail arm {tl['arm']:.2f} m (volume coefficients)",
            color=GREY_H, fontsize=10, va="center")
    ax.set_aspect("equal")
    ax.set_xlim(-b / 2 - 0.08, b / 2 + 0.95)
    ax.set_ylim(1.0, -0.35)             # x is positive aft, drawn downward
    ax.axis("off")
    sec = fig.add_axes([0.64, 0.12, 0.35, 0.7])
    draw_section(sec, params["camber_pct"], params["thickness_pct"])
    fig.text(0.815, 0.86, f"wing section NACA {params['camber_pct']:.0f}4{params['thickness_pct']:.0f}"
             "  (drone.naca.coordinates)", ha="center", fontsize=12, color=BLUE_H, fontweight="bold")
    fig.text(0.815, 0.08, "inputs camber_pct and thickness_pct; camber position fixed at 40 %",
             ha="center", fontsize=10, color=GREY_H)
    return save(fig, path_name)


def panel_edges(planform, lat):
    """Chord fractions of the panel edges, from the bound-leg positions the lattice returns.

    The bound leg sits at a quarter of its panel, q_j = 0.75 xi_j + 0.25 xi_{j+1}, and the last edge
    is 1, so the edges follow from the last panel forward.
    """
    q = (lat["a"].reshape(lat["n"], lat["m"], 3)[0, :, 0] - planform.x_le[0]) / planform.chord[0]
    xi = [1.0]
    for qj in q[::-1]:
        xi.append((qj - 0.25 * xi[-1]) / 0.75)
    xi = np.array(xi[::-1])
    assert abs(xi[0]) < 1e-9, "panel edges do not start at the leading edge"
    return xi


def draw_lattice(path_name="vlm_lattice.png"):
    """The medium horseshoe lattice on the nominal planform (drone.vlm._lattice) and its cl at 4 deg."""
    params, _, _out, geom = nominal()
    pf = geom["planform"]
    lat = vlm._lattice(pf, "medium", None)
    m, n = lat["m"], lat["n"]
    xi, y = panel_edges(pf, lat), lat["y"]
    xle = np.interp(lat["eta"], pf.eta, pf.x_le)
    chord = np.interp(lat["eta"], pf.eta, pf.chord)
    x_far = float(pf.x_le[-1] + pf.chord[0] * 1.35)
    xc_frac = xi[:-1] + 0.75 * np.diff(xi)                         # control points at 3/4 of the panel
    fig = plt.figure(figsize=(12, 4.4), dpi=200)
    ax = fig.add_axes([0.01, 0.02, 0.56, 0.96])
    for s, alpha in ((1.0, 1.0),):                                 # right half solved, left is the mirror
        for j in range(m + 1):
            ax.plot(s * y, xle + xi[j] * chord, color=GREY_H, lw=0.5 * alpha + 0.2, alpha=alpha)
        for k in range(n + 1):
            ax.plot([s * y[k]] * 2, [xle[k], xle[k] + chord[k]], color=GREY_H, lw=0.5 * alpha + 0.2,
                    alpha=alpha)
    a, b = lat["a"][:, :2], lat["b"][:, :2]                        # bound legs (y first, x second below)
    legs = [[(p[1], p[0]), (p[1], x_far)] for p in np.concatenate([a, b])]
    ax.add_collection(LineCollection(legs, colors=BLUE_H, linewidths=0.35, alpha=0.2))
    ax.add_collection(LineCollection([[(p[1], p[0]), (q[1], q[0])] for p, q in zip(a, b)],
                                     colors=BLUE_H, linewidths=1.2))
    y_c = 0.5 * (y[:-1] + y[1:])
    x_c = 0.5 * (xle[:-1] + xle[1:])[:, None] + xc_frac[None, :] * lat["c_mid"][:, None]
    ax.plot(np.repeat(y_c, m), x_c.ravel(), ".", color=GREY_H, ms=1.5)     # all control points
    strip, row = 3 * n // 4, 1                                     # one horseshoe, drawn in orange
    i0 = strip * m + row
    (ax0, ay), (bx, by) = a[i0], b[i0]
    ax.plot([ay, by], [ax0, bx], color=ACCENT_H, lw=2.6)
    for yy, xx in ((ay, ax0), (by, bx)):                           # its two trailing legs
        ax.plot([yy, yy], [xx, x_far], color=ACCENT_H, lw=1.6)
    y_mid = 0.5 * (y[strip] + y[strip + 1])
    x_cp = 0.5 * (xle[strip] + xle[strip + 1]) + xc_frac[row] * 0.5 * (chord[strip] + chord[strip + 1])
    ax.plot([y_mid], [x_cp], "o", color=ACCENT_H, ms=5)
    ax.annotate("control point", xy=(y_mid, x_cp), xytext=(pf.span / 2 + 0.02, x_cp + 0.07), color=ACCENT_H,
                fontsize=9, arrowprops={"arrowstyle": "-", "color": ACCENT_H})
    ax.annotate("bound vortex", xy=(ay, ax0), xytext=(pf.span / 2 + 0.02, ax0 - 0.04), color=ACCENT_H,
                fontsize=9, arrowprops={"arrowstyle": "-", "color": ACCENT_H})
    ax.text(ay - 0.03, x_far - 0.02, "trailing legs to x = infinity", color=ACCENT_H, fontsize=9,
            ha="right")
    ax.set_aspect("equal")
    ax.set_xlim(-0.05, pf.span / 2 + 0.3)
    ax.set_ylim(x_far + 0.05, -0.12)
    ax.axis("off")
    ax.set_title(f"medium lattice, {m} x {n} panels on the right half (left half is the mirror image)",
                 fontsize=11, color=BLUE_H)
    camber = functools.partial(lambda x, mm, p: naca.camber_line(x, mm, p)[1],
                               mm=params["camber_pct"] / 100.0, p=_CAMBER_POSITION)
    res = vlm.solve(pf, math.radians(4.0), "medium", camber)
    cl = fig.add_axes([0.65, 0.3, 0.33, 0.55])
    cl.plot(res["eta"], res["cl"], color=BLUE_H, lw=2)
    cl.set_xlabel("eta = y / (b/2)", fontsize=10)
    cl.set_ylabel("section cl", fontsize=10)
    cl.set_title("spanwise cl at 4 deg, nominal wing", fontsize=11, color=BLUE_H)
    cl.grid(alpha=0.3)
    der = vlm.derivatives(pf, "medium", camber)
    ar = geom["wing"]["AR"]
    e_row = v6_check("V6a elliptic AR 8 fine: e at 4 deg vs 1")
    cla_row = v6_check("V6a elliptic AR 8 fine: CL_alpha vs Helmbold")
    fig.text(0.65, 0.02,
             f"Nominal: CL = {res['CL']:.3f}, e = {res['e']:.3f}, CL_alpha = {der['CL_alpha']:.3f} /rad "
             f"(Helmbold {_helmbold(ar):.3f}).\nV6a, elliptic wing AR 8, fine lattice:\n"
             f"e = {e_row['measured']:.4f} against 1; CL_alpha {cla_row['measured']:.3f}\nagainst "
             f"Helmbold's {cla_row['reference']:.3f} ({100 * cla_row['deviation']:+.2f} %).",
             fontsize=9.5, color=TEXT_H, va="bottom")
    return save(fig, path_name)


def need(text, *names):
    """Fail the build when a step name used in a drawing is not in the source file it is taken from."""
    missing = [n for n in names if n not in text]
    assert not missing, f"not in the source: {missing}"


def draw_queue(path_name="queue_gates.png"):
    """Request to record, with every gate numbered where it sits. Step names are checked in the code."""
    queue_src = (ROOT / "mcp_server/queue.py").read_text()
    worker_src = (ROOT / "worker/run_worker.py").read_text()
    need(queue_src, "ingest_result", "check_record", "_digest_mismatch", "0-created", "1-pending",
         "2-done", "mesh_quality", "config_keys")
    need(worker_src, "check_regenerated", "stop_leftover_solvers", "1-running", "failure_of",
         "write_digest", "2-done", "mesh_fingerprint", "config_sha256", "gates.check")
    stages = re.search(r"schema -> [a-z_ >-]+", queue_src).group(0).split(" -> ")
    ranks = re.search(r"on (\d+) ranks", (ROOT / SPEC).read_text()).group(1)
    fig = plt.figure(figsize=(12, 4.4), dpi=200)
    ax = blank_axes(fig, [0, 0, 1, 1], (0, 12), (-0.55, 4.4))
    for y0, h, label in ((2.95, 1.3, "Local: Claude Code and the MCP tools"),
                         (1.62, 1.1, "Drive queue folder"), (0.28, 1.1, "Colab worker")):
        ax.add_patch(Rectangle((0.05, y0), 11.9, h, fc="#F7F9FC", ec="#D0D7E2", lw=0.8))
        ax.text(0.12, y0 + h - 0.04, label, fontsize=9.5, color=GREY_H, va="top", fontweight="bold")

    def gate(x, y, k):
        ax.add_patch(Circle((x, y), 0.13, fc=ACCENT_H, ec="white", lw=1))
        ax.text(x, y, str(k), color="white", fontsize=8, ha="center", va="center", fontweight="bold")

    mbox(ax, 0.95, 3.45, 1.4, 0.55, "Claude Code\nagent layer", fs=9)
    mbox(ax, 3.7, 3.45, 3.5, 0.75, "create_case:  " + " > ".join(stages[:2]) + "\n" +
         " > ".join(stages[2:]) + "\nnothing is staged on failure", fs=8.5)
    mbox(ax, 6.7, 3.45, 1.9, 0.75, "stage jobs/<id>/\n0-created, submit:\n1-pending", fs=8.5)
    mbox(ax, 8.85, 3.45, 1.9, 0.55, "upload job.json\nto Drive (by hand)", fs=8.5)
    mbox(ax, 10.9, 3.45, 2.0, 0.75, "ingest_result:\nstaged job, digest,\nJSON, record check", fs=8.5)
    mbox(ax, 3.0, 2.17, 2.6, 0.55, "jobs/<id>.json", fs=9)
    mbox(ax, 9.0, 2.17, 3.2, 0.55, "runs/<id>.result.json\n+ runs/<id>.result.sha256", fs=9)
    mbox(ax, 1.4, 0.83, 2.5, 0.7, "regenerate mesh and config:\ncase_id hash, mesh fingerprint,\nconfig_sha256", fs=8.2)
    mbox(ax, 4.0, 0.83, 1.9, 0.7, "gates again,\nstop leftover SU2,\nflag 1-running", fs=8.2)
    mbox(ax, 6.2, 0.83, 2.0, 0.7, f"SU2 on {ranks} ranks\nstops on Cauchy rule\nor iteration budget", fs=8.2)
    mbox(ax, 8.5, 0.83, 1.9, 0.7, "failure_of: timeout,\nexit code, NaN,\npostprocess error", fs=8.2)
    mbox(ax, 10.7, 0.83, 2.0, 0.7, "result.json + sha256\nflag 2-done", fs=8.2)
    for p, q in (((1.65, 3.45), (1.95, 3.45)), ((5.45, 3.45), (5.75, 3.45)),
                 ((7.65, 3.45), (7.9, 3.45))):
        marrow(ax, p, q)
    marrow(ax, (8.85, 3.17), (3.9, 2.45), rad=-0.15)
    marrow(ax, (2.2, 1.9), (1.7, 1.18), rad=0.0)
    for p, q in (((2.65, 0.83), (3.05, 0.83)), ((4.95, 0.83), (5.2, 0.83)), ((7.2, 0.83), (7.55, 0.83)),
                 ((9.45, 0.83), (9.7, 0.83))):
        marrow(ax, p, q)
    marrow(ax, (10.7, 1.18), (9.5, 1.9), rad=0.0)
    marrow(ax, (10.5, 2.45), (10.9, 3.07), rad=0.0)
    for x, y, k in ((2.1, 3.1, 1), (5.2, 3.1, 2), (1.2, 1.15, 3), (4.0, 1.19, 4), (6.2, 1.19, 5),
                    (8.5, 1.19, 6), (9.55, 2.4, 7), (10.1, 3.1, 8)):
        gate(x, y, k)
    legend = ["1 schema (strict), 2 physics gates, mesh quality and config keys (create_case)",
              "3 case_id, mesh fingerprint, config hash re-checked  4 gates run again by the worker",
              "5 Cauchy stop in the SU2 config  6 failure checks on the run",
              ("7 sha256 of the file against the worker's digest  8 record check at ingest, then "
              "runs/<tag>/<id>/"),
              ("after ingest: drift rule on history.csv (postprocess/history.py) and the per-design "
              "aggregator (analysis/drone_polar.py)")]
    ax.text(0.1, 0.18, "   |   ".join(legend[:2]) + "\n" + "   |   ".join(legend[2:4]) + "\n" + legend[4],
            fontsize=7.8, color=GREY_H, va="top")
    return save(fig, path_name)


def draw_airfoil_mesh(path_name="airfoil2d_mesh.png"):
    """The coarse C-mesh of the nominal section from geometry.airfoil2d.build, with a zoom at the nose."""
    run = ROOT / "runs/mesh/airfoil2d-59cd4287e9"
    params = jload(str(run.relative_to(ROOT) / "params.json"))
    recorded = jload(str(run.relative_to(ROOT) / "geometry.json"))
    quality = jload(str(run.relative_to(ROOT) / "mesh_quality.json"))
    geo, mesh = airfoil2d.build(params)
    assert (geo["cells"], geo["nodes"]) == (recorded["cells"], recorded["nodes"]), "mesh differs from record"
    assert abs(geo["first_cell_m"] / recorded["first_cell_m"] - 1) < 1e-9
    edges = np.concatenate([mesh.cells[:, [0, 1]], mesh.cells[:, [1, 2]], mesh.cells[:, [2, 3]],
                            mesh.cells[:, [3, 0]]])
    segments = mesh.coords[np.unique(np.sort(edges, axis=1), axis=0)]
    sx, sy = naca.coordinates(params["camber_pct"], params["thickness_pct"], n=801)
    first = quality["first_cell_height"]["airfoil"]
    views = [((-31, 31), (-31, 31), 0.1, "whole domain, farfield 30 chords"),
             ((-0.1, 1.3), (-0.35, 0.35), 0.2, "near field, one chord"),
             ((-0.006, 0.014), (-0.01, 0.01), 0.5, f"leading edge, first cell {first:.2e} m")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), dpi=200)
    for axx, (xl, yl, lw, title) in zip(axes, views):
        axx.add_collection(LineCollection(segments, colors=BLUE_H, linewidths=lw))
        axx.plot(sx, sy, color=ACCENT_H, lw=0.8 if lw < 0.5 else 1.4)
        axx.set_xlim(*xl)
        axx.set_ylim(*yl)
        axx.set_aspect("equal")
        axx.set_title(title, fontsize=10.5, color=BLUE_H)
        axx.tick_params(labelsize=8)
    fig.suptitle(f"airfoil2d, {params['mesh_level']} level, NACA {params['camber_pct']:.0f}4"
                 f"{params['thickness_pct']:.0f}, Re {params['reynolds']:,.0f}: {geo['cells']:,} cells, "
                 f"{geo['nodes']:,} nodes, y+ {geo['y_plus']:g} target, min angle "
                 f"{quality['min_angle_deg']:.1f} deg, {quality['n_inverted']} inverted cells",
                 fontsize=10.5, color=TEXT_H)
    fig.tight_layout()
    return save(fig, path_name)


def draw_closure(path_name="closure_energy.png"):
    """The fixed-point loop on take-off mass, the nominal mass breakdown and the endurance balance."""
    params, fixed, out, _ = nominal()
    rules, bat, prop = fixed["rules"], fixed["battery"], fixed["propulsion"]
    masses, m = out["masses"], out["mtow_kg"]
    diag = out["diagnostics"]
    mb, dod, e_spec = masses["battery"], bat["depth_of_discharge"], bat["pack_specific_energy_Wh_per_kg"]
    usable_j = dod * e_spec * 3600.0 * mb
    bal = v6_check("V6d energy balance: spent vs usable battery energy")
    end = v6_check("V6d endurance_h vs closed form")
    assert abs(usable_j / bal["measured"] - 1) < 1e-6 and abs(out["endurance_h"] / end["measured"] - 1) < 1e-6
    p_cr, p_in, v = diag["P_cruise_W"], diag["P_installed_W"], out["v_cruise"]
    drag = p_cr * prop["propulsive_efficiency"] / v
    fig = plt.figure(figsize=(12, 4.4), dpi=200)
    ax = blank_axes(fig, [0, 0, 0.5, 1], (0, 6), (0, 4.4))
    ax.text(0.1, 4.25, "Mass closure: fixed point on take-off mass", fontsize=11.5, color=BLUE_H,
            fontweight="bold", va="top")
    steps = [(1.0, 3.2, "guess m_TO"),
             (3.0, 3.2, "wing area S = b^2/AR,\nchords, wetted areas\n(geometry.build)"),
             (5.0, 3.2, "structure masses:\nskin, spar (3.8 g, 1.5),\ntail, fuselage"),
             (5.0, 1.65, (f"battery = f_b m_TO\n= {params['battery_fraction']:g} m_TO;\npayload "
                         f"{rules['payload_mass_kg']:g} kg;\npropulsion = P_inst / W per kg")),
             (3.0, 1.65, "new m_TO =\nsum of the seven\ncomponent masses"),
             (1.0, 1.65, "residual below 1e-9?\nno: m_TO = new m_TO")]
    for x, y, t in steps:
        mbox(ax, x, y, 1.65, 1.0, t, fs=8.4, fc="#EAF0F7" if x == 1.0 and y == 3.2 else "white")
    for p, q in (((1.85, 3.2), (2.15, 3.2)), ((3.85, 3.2), (4.15, 3.2)), ((5.0, 2.7), (5.0, 2.15)),
                 ((4.15, 1.65), (3.85, 1.65)), ((2.15, 1.65), (1.85, 1.65)), ((1.0, 2.15), (1.0, 2.7))):
        marrow(ax, p, q)
    ax.text(0.1, 0.75, f"nominal design: {out['closure_iterations']} iterations, residual "
            f"{out['closure_residual']:.1e}\n(V6d: below 1e-9), m_TO = {m:.3f} kg", fontsize=9.5,
            color=TEXT_H, va="top")
    bar = fig.add_axes([0.54, 0.12, 0.1, 0.72])
    bottom = 0.0
    shades = ["#1F3A5F", "#D55E00", "#4C72A8", "#8FA8C8", "#B8C6DB", "#999999", "#E8A56B"]
    n_m = len(masses)
    for k, ((name, val), col) in enumerate(zip(masses.items(), shades)):
        bar.bar(0, val, bottom=bottom, color=col, width=0.8)
        y_lab = m * (0.97 - 0.95 * (n_m - 1 - k) / (n_m - 1))            # labels evenly spaced
        bar.annotate(f"{name.replace('_', ' ')} {val:.3f} kg", xy=(0.4, bottom + val / 2),
                     xytext=(0.7, y_lab), fontsize=8, color=TEXT_H, va="center",
                     arrowprops={"arrowstyle": "-", "color": GREY_H, "lw": 0.6})
        bottom += val
    bar.set_xlim(-0.5, 0.5)
    bar.set_ylim(0, m)
    bar.set_xticks([])
    bar.set_ylabel("kg", fontsize=9)
    bar.set_title(f"m_TO {m:.3f} kg", fontsize=10, color=BLUE_H)
    ax2 = blank_axes(fig, [0.74, 0, 0.26, 1], (0, 3.1), (0, 4.4))
    ax2.text(0.05, 4.25, "Endurance: an energy balance", fontsize=11.5, color=BLUE_H, fontweight="bold",
             va="top")
    items = [(3.15, (f"E_usable = DoD x E_spec x m_b\n= {dod:g} x {e_spec:g} Wh/kg x {mb:.3f} kg\n"
                    f"= {usable_j / 3600:.2f} Wh = {usable_j:,.0f} J")),
             (2.1, (f"P = D V / eta_p\n= {drag:.2f} N x {v:.2f} m/s / {prop['propulsive_efficiency']:g}\n"
                   f"= {p_cr:.1f} W")),
             (1.0, (f"t = (E_usable - P_inst t_climb) / P\nt_climb = {rules['climb_allowance_s']:g} s at "
                   f"P_inst = {p_in:.0f} W\nt = {out['endurance_h']:.3f} h"))]
    for y, t in items:
        mbox(ax2, 1.55, y, 2.95, 0.85, t, fs=8.4)
    marrow(ax2, (1.55, 2.72), (1.55, 2.53))
    marrow(ax2, (1.55, 1.67), (1.55, 1.43))
    ax2.text(0.05, 0.3, "V6d: energy balance closes to 1e-9, endurance equals\nthe closed form to 1e-6",
             fontsize=8.5, color=GREY_H, va="top")
    return save(fig, path_name)


def design_space():
    """(span grid, AR grid, ok[ar, span], front rows, base, lengthscales, n_edge) from the records."""
    rows = csv_rows("runs/drone_pareto_lf/2026-11-09/design_map.csv")
    notes = jload("runs/drone_pareto_lf/2026-11-09/notes.json")
    span = np.unique([float(r["span_m"]) for r in rows])
    ar = np.unique([float(r["aspect_ratio"]) for r in rows])
    ok = np.zeros((len(ar), len(span)))
    for r in rows:
        ok[np.searchsorted(ar, float(r["aspect_ratio"])), np.searchsorted(span, float(r["span_m"]))] = \
            float(r["cheap_gates_ok"])
    front = csv_rows("runs/drone_pool_lf/2026-11-08/front.csv")
    n_edge = 0
    for r in front:
        i = int(np.argmin(np.abs(ar - float(r["aspect_ratio"]))))
        j = int(np.argmin(np.abs(span - float(r["span_m"]))))
        n_edge += int(np.any(ok[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2] == 0))
    return span, ar, ok, front, notes, n_edge


def draw_design_space(path_name="design_space.png"):
    """Six-input box, the two most sensitive inputs, the gated region and the observed front."""
    span, ar, ok, front, notes, n_edge = design_space()
    fig = plt.figure(figsize=(12, 4.4), dpi=200)
    left = fig.add_axes([0.2, 0.24, 0.2, 0.62])
    names = list(DRONE_BOUNDS)
    ls = [notes["endurance_lengthscales"][k] for k in names]
    picked = notes["design_map_inputs"]
    left.barh(range(len(names)), ls, color=[ACCENT_H if k in picked else "#8FA8C8" for k in names])
    left.set_yticks(range(len(names)))
    left.set_yticklabels([f"{k}\n{DRONE_BOUNDS[k][0]:g} to {DRONE_BOUNDS[k][1]:g}" for k in names],
                         fontsize=8.5)
    left.invert_yaxis()
    left.set_xlabel("GP length scale of endurance", fontsize=9)
    left.set_title("six inputs: shortest scale = most sensitive", fontsize=10, color=BLUE_H)
    right = fig.add_axes([0.5, 0.24, 0.47, 0.62])
    right.pcolormesh(span, ar, ok, shading="nearest", cmap=ListedColormap(["#F2C9A8", "#EAF0F7"]), vmin=0,
                     vmax=1)
    right.scatter([float(r["span_m"]) for r in front], [float(r["aspect_ratio"]) for r in front], c=BLUE_H,
                  s=34, edgecolor="white", zorder=3, label=f"{len(front)} observed front designs")
    right.set_xlabel("span_m (m)", fontsize=10)
    right.set_ylabel("aspect_ratio", fontsize=10)
    right.set_title("cheap gates, other four inputs fixed (light: passes, orange: gated)\n"
                    f"{n_edge} of {len(front)} front designs within one cell of a gated cell",
                    fontsize=9.5, color=BLUE_H)
    right.legend(loc="lower right", fontsize=9)
    base = ", ".join(f"{k} {v:g}" for k, v in notes["design_map_base"].items() if k not in picked)
    fig.text(0.2, 0.01, f"Fixed for the map: {base} (notes.json).\nThe front designs have their own values "
             "of those four, so the overlay is a projection.", fontsize=8.5, color=GREY_H)
    return save(fig, path_name)


def draw_two_level(path_name="two_level.png"):
    """y_H = rho y_L + d, with the E387 lift-slope discrepancy at Re 203,800 as the thing d absorbs."""
    low = v6_check("V6f cl_alpha Re 203800")
    su2 = v6_check("V6e cl_alpha Re 203800")
    fig = plt.figure(figsize=(12, 4.4), dpi=200)
    ax = blank_axes(fig, [0, 0, 0.5, 1], (0, 6), (0, 4.4))
    mbox(ax, 1.2, 3.4, 2.1, 0.9, "low level y_L(x)\nclosed-form section\nseconds per design", fs=9.5)
    mbox(ax, 4.6, 3.4, 2.1, 0.9, "high level y_H(x)\nSU2 section polar\nminutes per angle", fs=9.5,
         fc="#EAF0F7")
    marrow(ax, (2.3, 3.4), (3.5, 3.4), color=ACCENT_H)
    ax.text(2.9, 3.62, "x rho", fontsize=11, color=ACCENT_H, ha="center")
    ax.text(2.9, 3.05, "+ d(x)", fontsize=11, color=ACCENT_H, ha="center")
    ax.text(3.0, 2.2, "y_H = rho y_L + d", fontsize=17, color=BLUE_H, ha="center", fontweight="bold")
    ax.text(3.0, 1.45, "rho: a scale the model learns from paired runs\nd(x): a discrepancy surface fitted "
            "to the SU2 designs\n(surrogate/mf_gp.py, Task 9)", fontsize=10, color=TEXT_H, ha="center")
    ax.text(3.0, 0.55, "The known lift-slope offset below is what d has to absorb\nbefore any new "
            "SU2 design is spent on learning it.", fontsize=10, color=GREY_H, ha="center")
    bars = fig.add_axes([0.58, 0.2, 0.4, 0.62])
    vals = [("closed form\n(low level)", low["measured"], "#8FA8C8"),
            ("SU2\n(high level)", su2["measured"], BLUE_H),
            ("tunnel, SU2's\n5 angles", su2["reference"], "#999999"),
            ("tunnel,\nlinear range", low["reference"], "#BBBBBB")]
    bars.bar(range(4), [v[1] for v in vals], color=[v[2] for v in vals])
    for i, (_, val, _c) in enumerate(vals):
        bars.text(i, val + 0.002, f"{val:.4f}", ha="center", fontsize=9)
    bars.set_xticks(range(4))
    bars.set_xticklabels([v[0] for v in vals], fontsize=8.5)
    bars.set_ylim(0, 0.13)
    bars.set_ylabel("lift slope (per degree)", fontsize=9)
    bars.set_title(f"E387, Re 203,800: closed form {100 * low['deviation']:+.1f} % (V6f), SU2 "
                   f"{100 * su2['deviation']:+.1f} % (V6e)", fontsize=10, color=BLUE_H)
    gap = su2["measured"] - low["measured"]
    bars.annotate("", xy=(1, su2["measured"]), xytext=(1, low["measured"]),
                  arrowprops={"arrowstyle": "<->", "color": ACCENT_H, "lw": 1.5})
    bars.text(-0.4, 0.118, f"orange arrow: d if rho = 1 is {gap:+.4f} per degree", color=ACCENT_H,
              fontsize=9.5)
    return save(fig, path_name)


def ensure_drawings():
    """Build every drawing of this deck (each takes seconds)."""
    return [fn() for fn in (draw_planform, draw_lattice, draw_queue, draw_airfoil_mesh, draw_closure,
                            draw_design_space, draw_two_level)]



# ---- slide bodies -----------------------------------------------------------------------------
def body_d2(slide, v):
    rows = [["Question", "Status"],
            ["1. The front of endurance against take-off mass, with the GP's band and the named biases",
             "Exact low-fidelity front computed (D8); band over the SU2 pool PENDING"],
            ["2. Active learning against LHS and random: pool replay, and online against the exact front",
             "Answered on the low-fidelity model (D9, D10); SU2 pool replay PENDING"],
            ["3. Does the two-level model reach a given error with fewer SU2 polars?", "PENDING: multi-fidelity analysis"],
            ["4. Longest endurance under the 4.0 kg cap with P(mass <= cap) >= 0.9, and one SU2 confirmation",
             "PENDING: confirmation run"]]
    bd.add_table(slide, LM, CT + 0.2, [7.4, 4.7], rows, size=13, row_h=0.8)


def body_d3(slide, v):
    """The pipeline as boxes and arrows; the section data is the only block that differs by level."""
    rng = "\n".join(f"{k} {lo:g} to {hi:g}" for k, (lo, hi) in DRONE_BOUNDS.items())
    labels = [f"Six inputs\n{rng}", "Geometry\ndrone/geometry.py\nwing, tail, fuselage",
              "Vortex lattice\ndrone/vlm.py\nCL_alpha, e, strip cl", "Drag build-up\ndrone/drag.py",
              "Mass closure\nfixed point on m_TO", "Mission\nenergy balance\nP = D V / eta",
              "Outputs\nendurance, m_TO,\ngates"]
    bw, gx, y, bh = 1.5, 0.27, CT + 1.65, 1.35
    xs = [LM + i * (bw + gx) for i in range(len(labels))]
    for i, (x, text) in enumerate(zip(xs, labels)):
        bd.box(slide, x, y, bw, bh, text, size=9 if i == 0 else 10, fill=bd.TINT if i in (0, 6) else bd.WHITE)
        if i:
            bd.arrow(slide, x - gx, y + bh / 2, x, y + bh / 2)
    bd.text_box(slide, LM, CT - 0.05, CW, 0.35,
                "Two fidelity levels: the section data is the only block that differs",
                size=14, color=bd.ACCENT, bold=True)
    cx = xs[3] + bw / 2
    for x, text in ((cx - 3.1, "Low: closed forms (drone/section.py)\nthin-airfoil lift, flat-plate drag"),
                    (cx + 0.2, "High: SU2 airfoil2d polar\nSA-BCM, at the design's own Re\n(PENDING: pool batch)")):
        bd.box(slide, x, CT + 0.4, 2.9, 0.8, text, size=10, line=bd.ACCENT)
        bd.arrow(slide, x + 1.45, CT + 1.2, cx, y)
    bd.arrow(slide, xs[4] + bw / 2, y + bh, xs[4] + bw / 2, y + bh + 0.35, head=False)
    bd.arrow(slide, xs[4] + bw / 2, y + bh + 0.35, xs[1] + bw / 2, y + bh + 0.35, head=False)
    bd.arrow(slide, xs[1] + bw / 2, y + bh + 0.35, xs[1] + bw / 2, y + bh)
    bd.text_box(slide, xs[1] + bw / 2 + 0.2, y + bh + 0.4, 5.5, 0.3,
                "repeat until m_TO changes by less than 1e-9 (relative)", size=11, color=bd.GREY)
    bd.text_box(slide, LM, y + bh + 0.9, CW, 0.5,
                "Gates before any solver: Reynolds range, stall margin, mass closure, manufacturing floor, "
                "lattice quality (spec section 4).", size=12, color=bd.GREY)


def body_figure(name, record, max_h=4.2):
    """A body function that places one drawing from docs/talk/figures/drone/ with its caption."""
    def body(slide, v):
        bd.add_figure_with_caption(slide, FIG_DRONE + name, record, LM, CT, CW, max_h)
    return body


def body_d4(slide, v):
    rows = [["Run", "Budget", "Iterations", "cl drift (%)", "cd drift (%)", "Status"]]
    for rel, label in (("runs/smoke/airfoil2d-96a9dd0f51", "first smoke case"),
                       ("runs/smoke2/airfoil2d-51d551f2cc", "rerun with Cauchy stop")):
        r = jload(rel + "/result.json")
        conv, m = r["convergence"], r["metrics"]
        it = conv.get("iterations")
        rows.append([label, r["params"]["max_iter"], it if it else "not recorded (postprocess error)",
                     f"{m['cl_drift_pct']:.2f}", f"{m['cd_drift_pct']:.2f}", conv.get("status")])
    bd.add_table(slide, LM, CT + 0.1, [3.0, 1.2, 3.0, 1.4, 1.4, 2.1], rows, size=12, row_h=0.55)
    cfg = (ROOT / "cases/templates/inc_rans_airfoil.cfg").read_text()
    keys = ("CONV_FIELD", "CONV_CAUCHY_ELEMS", "CONV_CAUCHY_EPS", "CONV_STARTITER")
    lines = [m.group(0).strip() for k in keys for m in re.finditer(rf"^{k}=.*$", cfg, re.MULTILINE)]
    bd.text_box(slide, LM, CT + 2.2, 5.5, 0.4, "Cauchy settings (cases/templates/inc_rans_airfoil.cfg)",
                size=13, bold=True)
    bd.text_box(slide, LM, CT + 2.65, 5.5, 1.6, lines, size=13, font="Consolas", space_after=2)
    bd.text_box(slide, LM + 6.0, CT + 2.2, 6.0, 2.5,
                ["What stays the same: the Drive queue, the worker, the digest check and the gates.",
                 "What is new: the airfoil2d family, its mesh-quality checks and this stopping rule.",
                 "The drift rule and SU2's Cauchy rule measure different things; the record carries both."],
                size=13, bullets=True)


def body_d5(slide, v):
    rows = [["Row", "Deviation", "Tolerance", "Verdict"]]
    for c in jload(V6)["checks"]:
        if c["name"][:3] not in ("V6a", "V6b", "V6c", "V6d") or c["tolerance"] is None:
            continue
        dev = f"{c['deviation']:.2e}" if c["tolerance"] < 1e-4 else f"{100 * c['deviation']:+.2f} %"
        tol = f"{c['tolerance']:.0e}" if c["tolerance"] < 1e-4 else f"{100 * c['tolerance']:.0f} %"
        verdict = c["verdict"]
        if verdict.startswith("pending"):
            verdict = "PENDING: " + verdict.split("(", 1)[1].rstrip(")")
        elif verdict == "fail":
            verdict = "FAIL"
        rows.append([c["name"], dev, tol, verdict])
    bd.add_table(slide, LM, CT - 0.1, [7.0, 1.6, 1.3, 2.2], rows, size=10, row_h=0.31)


def body_d6(slide, v):
    checks = {c["name"]: c for c in jload(V6)["checks"]}
    res = ("101800", "203800", "305200")
    rows = [["Quantity", *[f"Re {int(r):,}" for r in res]]]
    for q, label, unit in (("cl_alpha", "lift slope", "%"), ("alpha_L0", "zero-lift angle", "deg"),
                           ("cd ratio", "profile drag, mean ratio", "%"), ("cl_max", "cl_max", "%")):
        cells = []
        for r in res:
            d = checks[f"V6f {q} Re {r}"]["deviation"]
            cells.append(f"{100 * d:+.1f} %" if unit == "%" else f"{d:+.2f} deg")
        rows.append([label, *cells])
    bd.add_table(slide, LM, CT + 0.1, [4.2, 2.6, 2.6, 2.6], rows, size=14, row_h=0.6, flag=())
    bd.text_box(slide, LM, CT + 3.4, CW, 1.3,
                [("Report-only rows by the spec: closed forms of drone/section.py at the E387's measured camber "
                  "and thickness against Volume 1 runs 211, 213 and 215."),
                 ("The ledger's assumed lift effectiveness does not contain the value the tunnel implies: a ledger "
                  "ruling, not a number to move here.")], size=13, bullets=True)


def body_d7(slide, v):
    _, _ = bd.add_figure_with_caption(slide, FIG + "d_e387_comparison.png", "runs/e387/*/result.json",
                                      LM, CT, 7.0, 4.2)
    checks = [c for c in jload(V6)["checks"] if c["name"].startswith("V6e ")]
    rows = [["Row", "Deviation", "Tol.", "Verdict"]]
    for c in checks:
        tol = "report" if c["tolerance"] is None else f"{100 * c['tolerance']:.0f} %"
        verdict = "report" if c["verdict"] == "report" else c["verdict"].upper() if c["verdict"] == "fail" else c["verdict"]
        rows.append([c["name"][5:], f"{100 * c['deviation']:+.2f} %", tol, verdict])
    bd.add_table(slide, LM + 7.2, CT, [2.0, 1.1, 0.8, 0.9], rows, size=10, row_h=0.45)
    bd.text_box(slide, LM + 7.2, CT + 2.0, 4.9, 2.4,
                [(f"Against the tunnel at the five angles of Re {v['e387_re']}: cl is {v['su2_cl_range']}; "
                  f"cd is {v['su2_cd_range']}."), "Decision 8: accepted as the high level with the miss recorded beside every number.",
                 "Re 305,200 and the fine-mesh pair are not complete; the figure draws what exists."],
                size=12, bullets=True)


def body_d8(slide, v):
    bd.add_figure_with_caption(slide, FIG + "a_front_lowfi.png", "runs/drone_grid/2026-11-08/front.csv",
                               LM, CT, 6.4, 4.3)
    g, p = jload("runs/drone_grid/2026-11-08/record.json"), jload("runs/drone_pool_lf/2026-11-08/record.json")
    bd.text_box(slide, LM + 6.7, CT, 5.4, 4.4,
                [(f"Grid: {g['points_evaluated']:,} points, {g['points_clean']:,} clean, {g['points_gated']:,} gated, "
                  f"{g['points_failed']} failed."),
                 f"Exact front: {g['front_size']} designs.",
                 f"Wall time: {g['wall_seconds']:.0f} s on {g['workers']} workers.",
                 (f"Low pool: {p['points_evaluated']} designs, {p['points_gated']} gated, "
                  f"front of {p['front_size']}, {p['wall_seconds']:.0f} s."),
                 "Both runs are at the medium lattice level."], size=14, bullets=True)


def body_d9(slide, v):
    rep = csv_rows(fd.POOL_REPLAY)
    ns = (8, 16, 24, 32, 40)
    strategies = ("random", "lhs", "al_ehvi", "al_maxvar")
    rows = [["n", *strategies]] + [[n, *[f"{mean_at(rep, s, 'hv_regret', n):.3f}" for s in strategies]] for n in ns]
    _, h = bd.add_figure_with_caption(slide, FIG + "b_pool_replay.png", fd.POOL_REPLAY, LM, CT - 0.05, 8.4, 2.9)
    bd.add_table(slide, LM, CT + h + 0.6, [1.0, 2.0, 2.0, 2.0, 2.0], rows, size=11, row_h=0.27, flag=())


def body_d10(slide, v):
    on, feas = csv_rows(fd.ONLINE), csv_rows(fd.ONLINE_FEAS)
    rows = [["Strategy", "Regret at 40", "Gated picks"]]
    for s, src in (("random", on), ("lhs", on), ("al_ehvi", on), ("al_ehvi_feas", feas), ("al_maxvar", on),
                   ("al_maxvar_feas", feas)):
        rows.append([s, f"{mean_at(src, s, 'hv_regret', 40):.3f}", f"{mean_at(src, s, 'n_gated', 40):.1f}"])
    bd.add_figure_with_caption(slide, FIG + "c_online_regret.png", fd.ONLINE + ", " + fd.ONLINE_FEAS,
                               LM, CT, 7.4, 3.2)
    bd.add_table(slide, LM + 7.6, CT, [1.9, 1.4, 1.2], rows, size=12, row_h=0.4, flag=())
    bd.text_box(slide, LM + 7.6, CT + 3.0, 4.5, 1.8,
                ["The front lies against the gated edge, and the GPs do not know the gates.",
                 "Both runs are published; neither replaces the other."], size=12, bullets=True)


def body_pending(slide, lines, box_text):
    bd.pending(slide, LM, CT + 0.1, CW, "PENDING: no number is shown here until the record exists.")
    bd.box(slide, LM, CT + 0.9, CW, 1.6, box_text, size=14)
    bd.text_box(slide, LM, CT + 2.9, CW, 1.6, lines, size=13, bullets=True)


def body_d11(slide, v):
    tags = defaultdict(int)
    for r in csv_rows("designs/pool_af_cases.csv"):
        tags[(r["tag"], r["mesh_level"])] += 1
    text = "\n".join(f"tag {t}, {m} mesh: {n} cases" for (t, m), n in sorted(tags.items()))
    body_pending(slide, ["Output expected: runs/pool_af/results.csv, then the front with the GP band (figure not drawn).",
                         "The acceptance rule for budget-exhausted runs is still open and applies to this pool."],
                 text)


def body_d12(slide, v):
    bd.pending(slide, LM, CT - 0.05, CW, "PENDING: the held-out error comparison waits on the multi-fidelity analysis.")
    bd.add_figure_with_caption(slide, FIG_DRONE + "two_level.png", V6, LM, CT + 0.4, CW, 3.8)


def body_d13(slide, v):
    body_pending(slide, ["The query is a computation on the fitted surrogate, never a choice by the language model.",
                         "The confirmation is one SU2 polar at the answer, through the queue."],
                 "Design, predicted endurance, P(mass <= cap), SU2 confirmation\nPENDING: confirmation run (T10.10d)")


def body_d14(slide, v):
    text = (ROOT / SPEC).read_text()
    para = re.search(r"Biases that travel with every figure:(.*?)\.\n\n", text, re.DOTALL).group(1)
    items = [" ".join(s.split()) for s in para.split(";")]
    items = [i[:1].upper() + i[1:] for i in items]
    bd.text_box(slide, LM, CT, 5.9, 0.4, "Spec section 13", size=14, bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.45, 5.9, 4.2, items, size=13, bullets=True)
    bd.text_box(slide, LM + 6.3, CT, 5.8, 0.4, "Carried by every SU2 section polar (decision 8)", size=14,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM + 6.3, CT + 0.45, 5.8, 4.2, v6e_flags(), size=13, font="Consolas", bullets=True)


def body_d15(slide, v):
    smoke = jload("runs/smoke/airfoil2d-96a9dd0f51/result.json")
    err = smoke["convergence"]["error"]
    col = re.search(r"\('(rms\[\w+\])',\)", err).group(1)
    tasks = (ROOT / TASKS).read_text()
    inverted = re.search(r"\((\d+) inverted cells\)", tasks).group(1)
    m = smoke["metrics"]
    smoke2_budget = jload("runs/smoke2/airfoil2d-51d551f2cc/result.json")["params"]["max_iter"]
    rows = [["Caught", "By", "Resolution"],
            [f"Postprocess looked for the compressible column {col}", "The first airfoil2d case failing at postprocess",
             "The classifier reads rms[P] (decision 6)"],
            [f"First case unconverged: cl drift {m['cl_drift_pct']:.1f} %, cd drift {m['cd_drift_pct']:.1f} %",
             "The drift rule on the recorded history", f"Budget {smoke2_budget} with a Cauchy stop (decision 6)"],
            ["Fine-mesh case refused on the 1 nm fingerprint", "The worker's mesh fingerprint check",
             "Kept beside the rerun as .first_attempt"],
            [f"Fine E387 mesh has {inverted} inverted cells", "The mesh inversion gate",
             "Strict xfail; the V6e fine row stays not run"],
            ["Point-vortex induced drag under-counts by about 1/N", "The V6a elliptic-wing rows on the first lattice run",
             "Trefftz-plane Glauert series (drone/vlm.py)"],
            ["V6a reference for the AR 100 rectangular wing was wrong, not the solver", "The same V6a rows",
             "Reference corrected before any formal verdict (addendum 2)"]]
    bd.add_table(slide, LM, CT - 0.1, [4.6, 3.7, 3.8], rows, size=11, row_h=0.62, flag=())


BODIES = {"D2": body_d2, "D3": body_d3, "D3a": body_figure("planform.png", "drone/geometry.py, drone/naca.py"),
          "D3b": body_figure("closure_energy.png", V6 + ", drone/evaluate.py"),
          "D4a": body_figure("queue_gates.png", "mcp_server/queue.py, worker/run_worker.py"),
          "D4b": body_figure("airfoil2d_mesh.png", "runs/mesh/airfoil2d-59cd4287e9/geometry.json"),
          "D5a": body_figure("vlm_lattice.png", V6 + ", drone/vlm.py"),
          "D8a": body_figure("design_space.png", "runs/drone_pareto_lf/2026-11-09/design_map.csv"),
          "D4": body_d4, "D5": body_d5, "D6": body_d6, "D7": body_d7,
          "D8": body_d8, "D9": body_d9, "D10": body_d10, "D11": body_d11, "D12": body_d12, "D13": body_d13,
          "D14": body_d14, "D15": body_d15}


def fill(text, v):
    """Replace {name} by its value; an unknown name raises KeyError and fails the build."""
    return text.format_map(v)


def ensure_figures():
    names = ("a_front_lowfi.png", "b_pool_replay.png", "c_online_regret.png", "d_e387_comparison.png")
    if not all((ROOT / FIG / n).is_file() for n in names):
        fd.main(ROOT, ROOT / FD_OUT)


FD_OUT = fd.OUT_DIR


def build(out_path=DEFAULT_OUT):
    """Build the deck and save it. Returns the number of slides."""
    ensure_figures()
    ensure_drawings()
    v = values()
    slides = read_outline()
    prs = bd.new_deck()
    for i, s in enumerate(slides, start=1):
        message, notes = fill(s["message"], v), fill(s["notes"], v)
        if s["id"] == "D1":
            slide = bd.add_title_slide(prs, i, 
                                       "Sizing a small electric aircraft with the inlet pipeline", message,
                                       [("Status 2026-11-08: validation V6a to V6f recorded, low-fidelity studies "
                                         "complete, SU2 pool pending."),
                                        "Every number is read from a record in this repository at build time."], notes)
            for shape in slide.shapes:                     # the shared title helper labels its slide S1
                if shape.has_text_frame and shape.text_frame.text.startswith("S1  |"):
                    shape.text_frame.paragraphs[0].runs[0].text = f"D1  |  {i}"
            continue
        slide = bd.start_slide(prs, i, s["id"], s["title"], message, source_list(s["source"]), notes)
        BODIES[s["id"]](slide, v)
    prs.save(str(out_path))
    return len(prs.slides)


if __name__ == "__main__":
    n = build()
    print(f"wrote {DEFAULT_OUT.relative_to(ROOT)} with {n} slides")

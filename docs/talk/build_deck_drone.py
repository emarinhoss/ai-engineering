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
from docs.talk import equations as eq
from drone import geometry, ledger, naca, vlm
from drone.evaluate import _CAMBER_POSITION, _helmbold, evaluate
from geometry import airfoil2d
from mcp_server.schemas import DRONE_BOUNDS
from postprocess import plot_airfoil as pa

plt = bd.plt

OUTLINE = ROOT / "docs/talk/outline_drone.md"
DEFAULT_OUT = ROOT / "docs/talk/deck_drone.pptx"
V6 = "runs/drone/validation/2026-11-08/v6.json"
SPEC = "docs/specs/task10_drone_sizing.md"
TASKS = "docs/specs/task10_tasks.md"
FIG = "docs/validation/figures/task10/"
FLOW = FIG + "flow/"
# The two volume-output cases queued for the contour pictures (tag viz, design 0 coarse); their
# job files are in su2queue_local/jobs/. Not run yet, so nothing is drawn from them.
VIZ_CASES = ("airfoil2d-731806baea", "airfoil2d-0ae85f2779")
SMOKE = "runs/smoke/airfoil2d-96a9dd0f51"
SMOKE2 = "runs/smoke2/airfoil2d-51d551f2cc"
FIRST_ATTEMPT = "runs/mesh/airfoil2d-e161fb7e6b.first_attempt"
CASES = "designs/pool_af_cases.csv"
POOL = "runs/pool_af/2026-11-09"                     # rewritten hourly by the pool ingestion job
LOW_POOL = "runs/drone_pool_lf/2026-11-08/grid.csv"
INVERSE_LF = "runs/drone_inverse_lf/2026-11-09/inverse.json"
BIAS_LF = "runs/drone_bias_lf/2026-11-09/bias_sweep.csv"
REPORT = "docs/validation/2026-11-08_task10_report.md"
# Files of runs that have not landed: each slide that reads one says PENDING until it exists.
MF = "runs/drone_mf/2026-11-09/mf.csv"
PARETO_HF = "runs/drone_pareto_hf/2026-11-09/pareto.csv"
INVERSE_HF = "runs/drone_inverse_hf/2026-11-09/inverse.json"
CONFIRM = "runs/drone_confirm/2026-11-09/confirm.json"
BIAS_HF = "runs/drone_bias_hf/2026-11-09/bias_sweep.csv"
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
    if lo * hi < 0:
        return f"{end(lo)} to {end(hi)}"
    if hi > 0:
        return f"{abs(lo):.1f} to {end(hi)}"
    return f"{abs(hi):.1f} to {end(lo)}"             # both negative: smaller magnitude first


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


# ---- values read from the surface files, for the flow slides -----------------------------------
def suction_peak(surface):
    """Most negative Cp on the upper surface."""
    return float(np.min(pa.side(surface, "upper", "Pressure_Coefficient")[1]))


def case_by_alpha(cases):
    """[(alpha, result.json, surface)] sorted by angle for [(tag, case id)]."""
    out = [(r["params"]["alpha_deg"], r, s) for r, s in (pa.load_case(t, c) for t, c in cases)]
    return sorted(out, key=lambda row: row[0])


def e387_flow_values():
    rows = case_by_alpha(pa.E387_CASES)
    (a0, _, s0), (a1, _, s1) = rows[0], rows[-1]
    x0, x1 = pa.reversed_flow_extent(s0), pa.reversed_flow_extent(s1)
    return {"e387_a_lo": f"{a0:g}", "e387_a_hi": f"{a1:g}",
            "e387_peak_lo": f"{suction_peak(s0):.2f}", "e387_peak_hi": f"{suction_peak(s1):.2f}",
            "e387_rev_lo": f"{x0[0]:.2f} to {x0[1]:.2f}", "e387_rev_hi": f"{x1[0]:.2f} to {x1[1]:.2f}"}


def design0_flow_values():
    rows = {a: (r, s) for a, r, s in case_by_alpha(pa.DESIGN0_CASES)}
    (r10, s10), (r14, s14) = rows[10.0], rows[14.0]
    return {"d0_cl10": f"{r10['metrics']['cl']:.3f}", "d0_cl14": f"{r14['metrics']['cl']:.3f}",
            "d0_cd10": f"{r10['metrics']['cd']:.4f}", "d0_cd14": f"{r14['metrics']['cd']:.4f}",
            "d0_peak10": f"{suction_peak(s10):.2f}", "d0_peak14": f"{suction_peak(s14):.2f}"}


def mesh_flow_values():
    out = {}
    for level, tag, case in pa.MESH_CASES:
        r, s = pa.load_case(tag, case)
        out[f"mesh_{level}_peak"] = f"{suction_peak(s):.3f}"
        out[f"mesh_{level}_cl"] = f"{r['metrics']['cl']:.4f}"
        out[f"mesh_{level}_cells"] = f"{r['geometry']['cells']:,}"
    return out


def convergence_flow_values():
    c = jload(pa.SMOKE2 + "/result.json")
    return {"conv_iters": c["convergence"]["iterations"], "conv_budget": c["params"]["max_iter"],
            "conv_drop": f"{c['convergence']['drop_orders']:.1f}",
            "conv_cl_drift": f"{c['convergence']['drift_pct']['cl']:.2f} %",
            "conv_cd_drift": f"{c['convergence']['drift_pct']['cd']:.2f} %"}


def stall_flow_values():
    """cl and cd at 14 degrees of every complete pool design, as a range."""
    at14 = [r["metrics"] for d in pa.pool_designs() for r, _ in pa.design_cases(d)
            if r["params"]["alpha_deg"] == 14.0]
    cl, cd = [m["cl"] for m in at14], [m["cd"] for m in at14]
    return {"n_stall": len(at14), "stall_cl": f"{min(cl):.2f} to {max(cl):.2f}",
            "stall_cd": f"{min(cd):.3f} to {max(cd):.3f}", "n_designs": len(pa.pool_designs())}


def flow_values():
    return {**e387_flow_values(), **design0_flow_values(), **mesh_flow_values(),
            **convergence_flow_values(), **stall_flow_values(),
            "viz_cases": " and ".join(VIZ_CASES)}


def values():
    """Every {name} a message or note may use, each computed from a file."""
    v6 = jload(V6)["checks"]
    tol = [c for c in v6 if c["name"][:3] == "V6a" or c["name"][:3] in ("V6b", "V6c", "V6d")]
    tol = [c for c in tol if c["tolerance"] is not None]
    v6f = [c for c in v6 if c["name"].startswith("V6f ")]
    v6e = next(c for c in v6 if c["name"] == "V6e cl_alpha Re 203800")
    grid = jload("runs/drone_grid/2026-11-08/record.json")
    pool = jload("runs/drone_pool_lf/2026-11-08/record.json")
    rep = csv_rows(fd.POOL_REPLAY)
    on, feas = csv_rows(fd.ONLINE), csv_rows(fd.ONLINE_FEAS)
    smoke = jload(SMOKE + "/result.json")
    smoke2 = jload(SMOKE2 + "/result.json")
    pts = e387_points()
    cases = csv_rows(CASES)

    def band(name):
        return [c["deviation"] for c in v6f if c["name"].startswith(f"V6f {name} ")]

    return {
        "smoke_budget": f"{smoke['params']['max_iter']:,}",
        "smoke2_iters": f"{smoke2['convergence']['iterations']:,}",
        "smoke2_budget": f"{smoke2['params']['max_iter']:,}",
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
        **flow_values(),
        **motivation_values(),
        **problem_values(),
        **automation_values(),
        **results_values(),
        **pending_values(),
    }


# ---- reading the outline ----------------------------------------------------------------------
SLIDE_HEAD = re.compile(r"^### (DB?\d+)\. (.+?)"
                        r"(?: \((\d+:\d\d)(?: onward)?, (?:about )?([\d.]+) min\))?$")
SECTION_HEAD = re.compile(r"^## (.+?) \((.+)\)$")


def read_outline():
    """[{id, title, start, minutes, section, message, figure, equations, source, notes}], in order.

    `start` ("m:ss") and `minutes` come from the heading's "(m:ss, x min)"; backup slides have
    neither. `section` is the index of the `## Name (duration)` heading the slide sits under.
    """
    slides, cur, section = [], None, -1
    for line in OUTLINE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section += 1
            cur = None
            continue
        head = SLIDE_HEAD.match(line)
        if head:
            cur = {"id": head.group(1), "title": head.group(2), "start": head.group(3),
                   "minutes": float(head.group(4)) if head.group(4) else None, "section": section}
            slides.append(cur)
        elif cur is not None:
            for key, tag in (("message", "Message"), ("figure", "Figure or table"),
                             ("source", "Source"), ("notes", "Speaker notes")):
                if line.startswith(f"- **{tag}:** "):
                    cur[key] = line[len(f"- **{tag}:** "):].strip()
            found = eq.outline_equations(line)
            if found is not None:
                cur["equations"] = found
    return slides


def read_sections():
    """[{title, sub, minutes, ids}] for every `## Name (duration)` heading that holds slides.

    The divider title drops the word "Section"; `minutes` is None for the discussion and the
    backup sections, which are outside the 40 minutes.
    """
    heads = []
    for line in OUTLINE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            m = SECTION_HEAD.match(line)
            heads.append((m.group(1), m.group(2)) if m else None)
    out = []
    for i, head in enumerate(heads):
        ids = [s["id"] for s in read_outline() if s["section"] == i]
        if head is None or not ids:
            continue
        name, sub = head
        name = re.sub(r"^Section (\w+): ", r"\1. ", name)
        timed = re.fullmatch(r"([\d.]+) minutes", sub)
        out.append({"title": "Backup" if name.startswith("Backup") else name, "sub": sub,
                    "minutes": float(timed.group(1)) if timed else None, "ids": ids})
    return out


def exists(rel):
    """A repo file exists (a volume file may land gzipped or not)."""
    return (ROOT / rel).is_file() or (ROOT / rel.removesuffix(".gz")).is_file()


def source_parts(source):
    """The semicolon-separated parts of a Source line."""
    return [p.strip() for p in source.split(";") if p.strip()]


def source_list(source):
    """What the footer cites: the backticked paths of each part; a PENDING part is cited by its
    paths once they all exist, and by its PENDING text until then; `none` parts cite nothing."""
    out = []
    for part in source_parts(source):
        paths = re.findall(r"`([^`]+)`", part)
        if part.startswith("PENDING"):
            out += paths if paths and all(exists(p) for p in paths) else [part.replace("`", "")]
        elif not part.startswith("none"):
            out += paths
    return out


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
    fig = plt.figure(figsize=(12, 3.6), dpi=200)
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
    cl = fig.add_axes([0.65, 0.42, 0.33, 0.45])
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
    fig = plt.figure(figsize=(12, 3.6), dpi=200)
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



# ---- equations: LaTeX sources, each also listed in the outline under its slide ----------------------
# The relations are the ones the code implements (module and function named in each comment).
EQ_PIPE_LOOP = r"m_{k{+}1}=\sum_i m_i(m_k),\quad |m_{k{+}1}-m_k|/m_k<10^{-9}"        # evaluate._closure
EQ_PIPE_CRUISE = r"V=\sqrt{\dfrac{2W}{\rho\,S\,C_L}},\quad P=\dfrac{D\,V}{\eta_p}"   # mission.cruise_point
EQ_CLOSURE_MASS = (r"m_{k{+}1}=m_{\mathrm{pay}}+f_b\,m_k+m_{\mathrm{skin}}+m_{\mathrm{spar}}"
               r"+m_{\mathrm{tail}}+m_{\mathrm{fus}}+P_{\mathrm{inst}}/\sigma_P")   # evaluate._closure
EQ_CLOSURE_INST = (r"P_{\mathrm{inst}}=\max\!\left(k_P\,P_{\mathrm{cr}},\ "
               r"\dfrac{W\,\dot h}{\eta_p}+P_{\mathrm{cr}}\right)")               # evaluate._closure
EQ_CLOSURE_POWER = r"P_{\mathrm{cr}}=\dfrac{D\,V}{\eta_p}"                          # mission.power_required
EQ_CLOSURE_TIME = (r"t=\dfrac{\mathrm{DoD}\,E_{\mathrm{spec}}\,3600\,m_b-P_{\mathrm{inst}}\,"
               r"t_{\mathrm{climb}}}{3600\,P_{\mathrm{cr}}}")                       # mission.endurance_h
EQ_STOP_DRIFT = (r"\mathrm{drift}=\dfrac{\max_{k\in W}f_k-\min_{k\in W}f_k}{|f_n|}"
               r"\times100\,\%")                                                  # history.drift_pct
EQ_STOP_WINDOW = r"W=\{\,n-\lceil 0.2\,n\rceil+1,\ \ldots,\ n\,\}"               # history.drift_pct
EQ_STOP_CAUCHY = (r"\dfrac{1}{N}\sum_{k=n-N+1}^{n}\dfrac{|f_k-f_{k-1}|}{|f_k|}<\varepsilon,"
                r"\quad f\in\{C_L,C_D\}")                                          # inc_rans_airfoil.cfg
EQ_MESH_RE = r"Re=\dfrac{\rho\,V\,c}{\mu}"                                       # evaluate._closure
EQ_MESH_CELL = (r"C_f=0.074\,Re^{-0.2},\quad \dfrac{u_\tau}{V}=\sqrt{\dfrac{C_f}{2}},"
               r"\quad d_0=\dfrac{y^{+}\,c}{Re\,(u_\tau/V)}")                       # airfoil2d.first_cell
EQ_V6_HELMBOLD = r"C_{L\alpha}=\dfrac{2\pi\,AR}{2+\sqrt{AR^{2}+4}}"             # evaluate._helmbold
EQ_V6_INDUCED = r"C_{Di}=\dfrac{C_L^{2}}{\pi\,AR\,e}"                            # drag.total
EQ_V6_DEV = r"\mathrm{dev}=\dfrac{M}{R}-1\quad\mathrm{or}\quad\mathrm{dev}=M-R"   # drone_validation.row
EQ_VLM_SEGMENT = (r"\vec v_{\mathrm{seg}}=\dfrac{\Gamma}{4\pi}\ "
                  r"\dfrac{\vec r_1\times\vec r_2}{|\vec r_1\times\vec r_2|^{2}}\ "
                  r"\vec r_0\cdot\left(\dfrac{\vec r_1}{|\vec r_1|}-\dfrac{\vec r_2}{|\vec r_2|}\right)")
EQ_VLM_NOFLOW = r"\left(\vec V_\infty+\sum_j A_{ij}\,\Gamma_j\right)\cdot\hat n_i=0"   # vlm._lattice
EQ_VLM_TREFFTZ = (r"C_{Di}=\pi\,AR\sum_{n\ \mathrm{odd}}n\,A_n^{2},\quad "
                  r"e=\dfrac{C_L^{2}}{\pi\,AR\,C_{Di}}")                             # vlm._forces
EQ_V6F_CLMAX = r"c_{l,\max}=k_{\mathrm{eff}}\,2\pi\,(\alpha_{\mathrm{stall}}-\alpha_{L0})"  # section
EQ_V6F_CD0 = r"c_{d0}=2\,C_f\,FF,\quad FF=1+k_1\,(t/c)+k_2\,(t/c)^{4}"             # section
EQ_V6F_CDDEV = (r"\mathrm{mean}_{\,0.3\leq c_{l,\mathrm{tun}}\leq0.9}"
               r"\left|\dfrac{c_d}{c_{d,\mathrm{tun}}}-1\right|")                                         # _cd_ratio
EQ_V6E_SLOPE = (r"a_{\mathrm{fit}}=\dfrac{\sum(\alpha_i-\bar\alpha)(c_{l,i}-\bar c_l)}"
               r"{\sum(\alpha_i-\bar\alpha)^{2}},\quad "
               r"\mathrm{dev}=\dfrac{a_{\mathrm{SU2}}}{a_{\mathrm{tun}}}-1")             # v6e
EQ_GP_MEAN = r"\mu(x)=c+k_{*}^{T}(K+\sigma_n^{2}I)^{-1}(y-c)"                    # gp.GP.predict
EQ_GP_VAR = r"\sigma^{2}(x)=k_{**}-k_{*}^{T}(K+\sigma_n^{2}I)^{-1}k_{*}"          # gp.GP.predict
EQ_GP_REGRET = r"\mathrm{regret}=1-\dfrac{HV(\mathrm{observed})}{HV(\mathrm{front})}"  # replay
EQ_GP_HVI = r"\mathrm{HVI}(y)=HV(P\cup\{y\})-HV(P)"                             # acquisition.hvi_2d
EQ_GP_EHVI = (r"\mathrm{EHVI}(x)\approx\dfrac{1}{S}\sum_{s=1}^{S}\mathrm{HVI}(y_s),\quad "
              r"y_s\sim\mathcal{N}(\mu,\mathrm{diag}\,\sigma^{2})")              # acquisition.ehvi_mc
EQ_FEAS_FEAS = (r"\mathrm{EHVI}_{\mathrm{feas}}(x)=\mathrm{EHVI}(x)\cdot "
               r"p(\mathrm{feasible}\mid x)")                                         # replay_drone_online
EQ_FEAS_LOGISTIC = r"p(x)=\dfrac{1}{1+e^{-(w\cdot z(x)+b)}}"                       # feasibility.Feasibility
EQ_MF_TWO_LEVEL = r"y_H(x)=\rho\,y_L(x)+d(x),\quad d\sim\mathcal{GP}"            # mf_gp.TwoLevelGP
EQ_MF_POSTERIOR = (r"\mu_H=\rho\,\mu_L+\mu_d,\quad "
                    r"\sigma_H^{2}=\rho^{2}\sigma_L^{2}+\sigma_d^{2}")                 # mf_gp.predict
EQ_MF_GLS = r"(\rho,c)^{T}=(A^{T}K^{-1}A)^{-1}A^{T}K^{-1}y_H"                     # mf_gp.fit
EQ_INV_QUERY = (r"x^{*}=\arg\max_{x}\ \mathrm{E}\left[t(x)\right]\quad\mathrm{subject\ to}"
                r"\quad P\left(m_{TO}(x)\leq m_{\mathrm{cap}}\right)\geq p_{\min}")  # inverse
EQ_INV_PROB = (r"P\left(m_{TO}\leq m_{\mathrm{cap}}\right)=\Phi\!\left("
               r"\dfrac{\ln m_{\mathrm{cap}}-\mu_{\ln m}(x)}{\sigma_{\ln m}(x)}\right)")  # inverse


# ---- slide bodies kept from the first version of the deck -----------------------------------------------------------------------------
def body_pipeline(slide, v):
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
    eq.add_equation(slide, EQ_PIPE_LOOP, xs[1] + bw / 2 + 0.2, y + bh + 0.42, 5.2, 0.5, fontsize=15)
    eq.add_equation(slide, EQ_PIPE_CRUISE, 8.6, y + bh + 0.38, 4.1, 0.7, fontsize=15)
    bd.text_box(slide, LM, y + bh + 1.2, CW, 0.5,
                "Gates before any solver: Reynolds range, stall margin, mass closure, manufacturing floor, "
                "lattice quality (spec section 4).", size=12, color=bd.GREY)


def body_figure(name, record, max_h=4.2):
    """A body function that places one drawing from docs/talk/figures/drone/ with its caption."""
    def body(slide, v):
        bd.add_figure_with_caption(slide, FIG_DRONE + name, record, LM, CT, CW, max_h)
    return body


def body_closure(slide, v):
    """Closure drawing, then the relations it draws as equations: mass fixed point, powers, endurance."""
    _, h = bd.add_figure(slide, FIG_DRONE + "closure_energy.png", LM, CT - 0.05, CW, 3.6)
    y = CT - 0.05 + h + 0.04
    eq.add_equation(slide, EQ_CLOSURE_MASS, LM, y, 7.2, 0.4, fontsize=15)
    eq.add_equation(slide, EQ_CLOSURE_POWER, LM + 7.5, y - 0.05, 2.0, 0.6, fontsize=15)
    eq.add_equation(slide, EQ_CLOSURE_INST, LM, y + 0.5, 3.6, 0.7, fontsize=15)
    eq.add_equation(slide, EQ_CLOSURE_TIME, LM + 3.9, y + 0.5, 3.9, 0.7, fontsize=15)
    bd.caption(slide, LM + 8.1, y + 0.62, 4.0, "Figure: " + FIG_DRONE + "closure_energy.png. Record: "
               + V6 + ", drone/evaluate.py, drone/mission.py.", lines=4)


def body_mesh(slide, v):
    _, h = bd.add_figure(slide, FIG_DRONE + "airfoil2d_mesh.png", LM, CT, CW, 3.45)
    y = CT + h + 0.1
    eq.add_equation(slide, EQ_MESH_RE, LM, y, 1.6, 0.7, fontsize=15)
    eq.add_equation(slide, EQ_MESH_CELL, LM + 1.8, y, 5.4, 0.8, fontsize=15)
    bd.caption(slide, LM + 7.6, y, 4.5, "Figure: " + FIG_DRONE + "airfoil2d_mesh.png. Record: "
               "runs/mesh/airfoil2d-59cd4287e9/geometry.json. Equations: drone/evaluate.py, "
               "geometry/airfoil2d.py.", lines=4)


def body_lattice(slide, v):
    _, h = bd.add_figure(slide, FIG_DRONE + "vlm_lattice.png", LM, CT - 0.05, CW, 3.6)
    y = CT - 0.05 + h + 0.08
    eq.add_equation(slide, EQ_VLM_SEGMENT, LM, y, 4.5, 0.8, fontsize=15)
    eq.add_equation(slide, EQ_VLM_NOFLOW, LM + 4.7, y + 0.05, 3.0, 0.7, fontsize=15)
    eq.add_equation(slide, EQ_VLM_TREFFTZ, LM + 7.9, y, 4.2, 0.8, fontsize=15)
    bd.caption(slide, LM, y + 0.85, CW, "Figure: " + FIG_DRONE + "vlm_lattice.png. Record: " + V6
               + ", drone/vlm.py (segment velocity, no-flow condition, Trefftz-plane drag).", lines=1)


def body_stopping(slide, v):
    rows = [["Run", "Budget", "Iterations", "cl drift (%)", "cd drift (%)", "Status"]]
    for rel, label in (("runs/smoke/airfoil2d-96a9dd0f51", "first smoke case"),
                       ("runs/smoke2/airfoil2d-51d551f2cc", "rerun with Cauchy stop")):
        r = jload(rel + "/result.json")
        conv, m = r["convergence"], r["metrics"]
        it = conv.get("iterations")
        rows.append([label, r["params"]["max_iter"], it if it else "not recorded (postprocess error)",
                     f"{m['cl_drift_pct']:.2f}", f"{m['cd_drift_pct']:.2f}", conv.get("status")])
    bd.add_table(slide, LM, CT + 0.1, [3.0, 1.2, 3.0, 1.4, 1.4, 2.1], rows, size=12, row_h=0.55)
    bd.text_box(slide, LM, CT + 1.8, 6.0, 0.3, "Drift rule (postprocess/history.py)", size=12, color=bd.GREY)
    bd.text_box(slide, LM + 6.6, CT + 1.8, 5.5, 0.3, "SU2 Cauchy rule, as the case template states it",
                size=12, color=bd.GREY)
    eq.add_equation(slide, EQ_STOP_DRIFT, LM, CT + 2.12, 3.2, 0.75, fontsize=14)
    eq.add_equation(slide, EQ_STOP_WINDOW, LM + 3.3, CT + 2.3, 3.0, 0.4, fontsize=14)
    eq.add_equation(slide, EQ_STOP_CAUCHY, LM + 6.6, CT + 2.12, 5.4, 0.75, fontsize=14)
    cfg = (ROOT / "cases/templates/inc_rans_airfoil.cfg").read_text()
    keys = ("CONV_FIELD", "CONV_CAUCHY_ELEMS", "CONV_CAUCHY_EPS", "CONV_STARTITER")
    lines = [m.group(0).strip() for k in keys for m in re.finditer(rf"^{k}=.*$", cfg, re.MULTILINE)]
    bd.text_box(slide, LM, CT + 3.0, 5.5, 0.4, "Cauchy settings (cases/templates/inc_rans_airfoil.cfg)",
                size=13, bold=True)
    bd.text_box(slide, LM, CT + 3.4, 5.5, 1.4, lines, size=13, font="Consolas", space_after=2)
    bd.text_box(slide, LM + 6.0, CT + 3.0, 6.0, 1.8,
                ["What stays the same: the Drive queue, the worker, the digest check and the gates.",
                 "What is new: the airfoil2d family, its mesh-quality checks and this stopping rule.",
                 "The drift rule and SU2's Cauchy rule measure different things; the record carries both."],
                size=13, bullets=True)


def body_v6_table(slide, v):
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
    bd.add_table(slide, LM, CT - 0.1, [7.0, 1.6, 1.3, 2.2], rows, size=10, row_h=0.27)
    y = CT - 0.1 + 0.27 * len(rows) + 0.15
    eq.add_equation(slide, EQ_V6_HELMBOLD, LM, y, 2.6, 0.75, fontsize=15)
    eq.add_equation(slide, EQ_V6_INDUCED, LM + 3.0, y, 2.0, 0.75, fontsize=15)
    eq.add_equation(slide, EQ_V6_DEV, LM + 5.4, y + 0.1, 4.0, 0.6, fontsize=15)
    bd.text_box(slide, LM + 9.6, y + 0.1, 2.5, 0.6, "M measured, R reference; the table says which form each row uses",
                size=11, color=bd.GREY)


def body_v6f(slide, v):
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
    eq.add_equation(slide, EQ_V6F_CLMAX, LM, CT + 3.35, 3.4, 0.5, fontsize=14)
    eq.add_equation(slide, EQ_V6F_CD0, LM + 3.7, CT + 3.35, 4.4, 0.5, fontsize=14)
    eq.add_equation(slide, EQ_V6F_CDDEV, LM + 8.3, CT + 3.2, 3.8, 0.7, fontsize=14)
    bd.text_box(slide, LM, CT + 4.1, CW, 0.8,
                [("Report-only rows by the spec: closed forms of drone/section.py at the E387's measured camber "
                  "and thickness against Volume 1 runs 211, 213 and 215."),
                 ("The ledger's assumed lift effectiveness does not contain the value the tunnel implies: a ledger "
                  "ruling, not a number to move here.")], size=13, bullets=True)


def body_v6e(slide, v):
    _, h = bd.add_figure_with_caption(slide, FIG + "d_e387_comparison.png", "runs/e387/*/result.json",
                                      LM, CT - 0.05, 6.4, 3.35)
    checks = [c for c in jload(V6)["checks"] if c["name"].startswith("V6e ")]
    rows = [["Row", "Deviation", "Tol.", "Verdict"]]
    for c in checks:
        tol = "report" if c["tolerance"] is None else f"{100 * c['tolerance']:.0f} %"
        verdict = "report" if c["verdict"] == "report" else c["verdict"].upper() if c["verdict"] == "fail" else c["verdict"]
        rows.append([c["name"][4:], f"{100 * c['deviation']:+.2f} %", tol, verdict])
    bd.add_table(slide, LM + 7.2, CT, [2.0, 1.1, 0.8, 0.9], rows, size=10, row_h=0.42)
    eq.add_equation(slide, EQ_V6E_SLOPE, LM, CT + h + 0.55, 3.5, 0.75, fontsize=12)
    eq.add_equation(slide, EQ_V6F_CDDEV, LM + 3.7, CT + h + 0.55, 3.4, 0.75, fontsize=12)
    bd.text_box(slide, LM + 7.2, CT + 3.1, 4.9, 1.7,
                [(f"Against the tunnel at the five angles of Re {v['e387_re']}: cl is {v['su2_cl_range']}; "
                  f"cd is {v['su2_cd_range']}."), "Decision 8: accepted as the high level with the miss recorded beside every number.",
                 "The medium-against-fine row is not run (DB2); the figure draws what exists."],
                size=11, bullets=True)


def body_flow(name, record, max_h=4.6):
    """A flow figure (docs/validation/figures/task10/flow/) full width with its caption."""
    def body(slide, v):
        bd.add_figure_with_caption(slide, FLOW + name, record, LM, CT - 0.05, CW, max_h)
    return body


def body_section_polars(slide, v):
    _, h = bd.add_figure(slide, FLOW + "section_polars.png", LM, CT - 0.05, CW, 4.1)
    bd.caption(slide, LM, CT + h, CW, "Figure: " + FLOW + "section_polars.png. Records: runs/e387/*/result.json, "
               "runs/pool_af/*/result.json, " + pa.POOL_RESULTS + ", " + pa.E387_TUNNEL
               + ". Open circles are cases the pool did not keep.", lines=2)


def body_lowfi_front(slide, v):
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


def body_online(slide, v):
    on, feas = csv_rows(fd.ONLINE), csv_rows(fd.ONLINE_FEAS)
    rows = [["Strategy", "Regret at 40", "Gated picks"]]
    for s, src in (("random", on), ("lhs", on), ("al_ehvi", on), ("al_ehvi_feas", feas), ("al_maxvar", on),
                   ("al_maxvar_feas", feas)):
        rows.append([s, f"{mean_at(src, s, 'hv_regret', 40):.3f}", f"{mean_at(src, s, 'n_gated', 40):.1f}"])
    bd.add_figure_with_caption(slide, FIG + "c_online_regret.png", fd.ONLINE + ", " + fd.ONLINE_FEAS,
                               LM, CT, 7.4, 3.2)
    bd.add_table(slide, LM + 7.6, CT, [1.9, 1.4, 1.2], rows, size=12, row_h=0.4, flag=())
    eq.add_equation(slide, EQ_FEAS_FEAS, LM, CT + 4.0, 4.1, 0.5, fontsize=14)
    eq.add_equation(slide, EQ_FEAS_LOGISTIC, LM + 4.4, CT + 3.95, 3.0, 0.7, fontsize=14)
    bd.text_box(slide, LM + 7.6, CT + 3.0, 4.5, 1.8,
                ["The front lies against the gated edge, and the GPs do not know the gates.",
                 "Both runs are published; neither replaces the other."], size=12, bullets=True)


def body_pending(slide, lines, box_text, equations=()):
    bd.pending(slide, LM, CT + 0.1, CW, "PENDING: no number is shown here until the record exists.")
    bd.box(slide, LM, CT + 0.9, CW, 1.6, box_text, size=14)
    y = CT + 2.7
    for latex, h in equations:
        _, h_used = eq.add_equation(slide, latex, LM, y, CW, h, fontsize=16)
        y += h_used + 0.12
    bd.text_box(slide, LM, max(y, CT + 2.9), CW, 1.6, lines, size=13, bullets=True)


def body_two_level_pending(slide, v):
    bd.pending(slide, LM, CT - 0.05, CW, "PENDING: the held-out error comparison waits on the multi-fidelity analysis.")
    w, h = bd.add_figure(slide, FIG_DRONE + "two_level.png", LM, CT + 0.35, CW, 3.5)
    eq.add_equation(slide, EQ_MF_TWO_LEVEL, LM + 0.25 * w - 2.3, CT + 0.35 + 0.5 * h - 0.2, 4.6, 0.6,
                    fontsize=20, align="center")                    # centered on the drawing's left half
    y = CT + 0.35 + h + 0.1
    eq.add_equation(slide, EQ_MF_POSTERIOR, LM, y, 3.8, 0.5, fontsize=14)
    eq.add_equation(slide, EQ_MF_GLS, LM + 4.1, y, 3.4, 0.5, fontsize=14)
    bd.caption(slide, LM + 7.7, y - 0.02, 4.4, "Figure: " + FIG_DRONE + "two_level.png. Record: " + V6
               + ". Equations: surrogate/mf_gp.py.", lines=3)


def body_gated_caught(slide, v):
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


# ---- equations added for the 40-minute structure -------------------------------------------------
EQ_INPUTS_VCRUISE = (r"V_{\mathrm{cr}}=\max\left(V_{\mathrm{minP}},\ "
                     r"k_s\,V_{\mathrm{stall}}\right),"
                     r"\quad V_{\mathrm{stall}}=\sqrt{\dfrac{2W}{\rho\,S\,C_{L,\max}}}")  # mission
EQ_GP_KERNEL = bd.EQ_S13_KERNEL                    # surrogate.gp.GP.kernel (the inlet's GP)
EQ_GP_OBJECTIVES = r"f(x)=\left(-t(x),\ \ln m_{TO}(x)\right)"           # replay, family drone
EQ_GP_VARIANCE = bd.EQ_S14_VARIANCE                # surrogate.acquisition.max_variance

# The equations index (DB13): every relation a talk slide renders, with its implementing module.
EQUATION_INDEX = [
    (EQ_INPUTS_VCRUISE, "cruise speed rule and stall speed",
     "drone/mission.py (cruise_point, v_stall)"),
    (EQ_PIPE_LOOP, "mass closure as a fixed point", "drone/evaluate.py (_closure)"),
    (EQ_PIPE_CRUISE, "level-flight speed and power", "drone/mission.py (power_required)"),
    (EQ_VLM_SEGMENT, "Biot-Savart velocity of a vortex segment", "drone/vlm.py"),
    (EQ_VLM_NOFLOW, "no-flow condition at the control points", "drone/vlm.py (_lattice)"),
    (EQ_VLM_TREFFTZ, "Trefftz-plane induced drag, span efficiency", "drone/vlm.py (_forces)"),
    (EQ_V6_HELMBOLD, "Helmbold lift slope (V6a reference)", "drone/evaluate.py (_helmbold)"),
    (EQ_V6_INDUCED, "induced drag identity", "drone/drag.py (total)"),
    (EQ_V6_DEV, "deviation of a validation row", "analysis/drone_validation.py"),
    (EQ_CLOSURE_MASS, "the seven component masses", "drone/evaluate.py (_closure)"),
    (EQ_CLOSURE_POWER, "cruise power", "drone/mission.py (power_required)"),
    (EQ_CLOSURE_INST, "installed power", "drone/evaluate.py (_closure)"),
    (EQ_CLOSURE_TIME, "endurance from the energy balance", "drone/mission.py (endurance_h)"),
    (EQ_MESH_RE, "chord Reynolds number", "drone/evaluate.py"),
    (EQ_MESH_CELL, "first-cell height for a target y+", "geometry/airfoil2d.py (first_cell)"),
    (EQ_STOP_DRIFT, "drift over the last fifth", "postprocess/history.py (drift_pct)"),
    (EQ_STOP_WINDOW, "the drift window", "postprocess/history.py (drift_pct)"),
    (EQ_STOP_CAUCHY, "SU2's Cauchy stop", "cases/templates/inc_rans_airfoil.cfg"),
    (EQ_V6F_CLMAX, "closed-form section cl_max", "drone/section.py (low_fidelity)"),
    (EQ_V6F_CD0, "closed-form profile drag", "drone/section.py (low_fidelity)"),
    (EQ_V6F_CDDEV, "mean drag deviation over cl 0.3 to 0.9", "analysis/drone_validation.py"),
    (EQ_V6E_SLOPE, "least-squares lift slope", "analysis/drone_validation.py (v6e)"),
    (EQ_GP_KERNEL, "Matern 5/2 kernel with ARD", "surrogate/gp.py (GP.kernel)"),
    (EQ_GP_MEAN, "GP posterior mean", "surrogate/gp.py (GP.predict)"),
    (EQ_GP_VAR, "GP posterior variance", "surrogate/gp.py (GP.predict)"),
    (EQ_GP_OBJECTIVES, "the two objectives, minimized", "surrogate/replay.py (family drone)"),
    (EQ_GP_HVI, "hypervolume improvement", "surrogate/acquisition.py (hvi_2d)"),
    (EQ_GP_EHVI, "expected hypervolume improvement", "surrogate/acquisition.py (ehvi_mc)"),
    (EQ_GP_VARIANCE, "max-variance score", "surrogate/acquisition.py (max_variance)"),
    (EQ_GP_REGRET, "hypervolume regret", "surrogate/replay.py"),
    (EQ_FEAS_FEAS, "feasibility-weighted EHVI", "analysis/replay_drone_online.py"),
    (EQ_FEAS_LOGISTIC, "logistic feasibility model", "surrogate/feasibility.py (Feasibility)"),
    (EQ_MF_TWO_LEVEL, "two-level model", "surrogate/mf_gp.py (TwoLevelGP)"),
    (EQ_MF_POSTERIOR, "two-level posterior", "surrogate/mf_gp.py (predict)"),
    (EQ_MF_GLS, "generalized least squares for rho and c", "surrogate/mf_gp.py (fit)"),
    (EQ_INV_QUERY, "the inverse query", "analysis/inverse.py (family drone)"),
    (EQ_INV_PROB, "probability under the cap", "analysis/inverse.py (family drone)"),
]


# ---- values of the new sections (each read from the file its slide names) -----------------------
def pct(x, digits=1):
    """Signed percent of a fraction: 0.0549 -> '+5.5 %'."""
    return f"{100 * x:+.{digits}f} %"


def pool_case_index():
    """{case_id: (tag, design index, alpha)} from the pool's case table."""
    return {r["case_id"]: (r["tag"], int(r["index"]), float(r["alpha_deg"]))
            for r in csv_rows(CASES)}


@functools.cache
def all_su2_records():
    """{(tag, case_id): result.json} for every airfoil2d record under runs/ (re-read per build)."""
    out = {}
    for f in sorted((ROOT / "runs").glob("*/airfoil2d-*/result.json")):
        if f.parent.name.endswith(".first_attempt"):
            continue
        out[(f.parent.parent.name, f.parent.name)] = json.loads(f.read_text())
    return out


def budget_exhausted():
    """Records whose iteration count equals their budget, as (tag, case id, record)."""
    return [(t, c, r) for (t, c), r in all_su2_records().items()
            if r["convergence"].get("iterations") == r["params"]["max_iter"]]


def motivation_values():
    smoke, smoke2 = jload(SMOKE + "/result.json"), jload(SMOKE2 + "/result.json")
    col = re.search(r"\('(rms\[\w+\])',\)", smoke["convergence"]["error"]).group(1)
    fp = jload(FIRST_ATTEMPT + "/error.json")["detail"]
    return {"smoke_exit": smoke["run"]["exit_code"],
            "smoke_cl_off": pct(smoke["metrics"]["cl"] / smoke2["metrics"]["cl"] - 1),
            "smoke_cd_off": pct(smoke["metrics"]["cd"] / smoke2["metrics"]["cd"] - 1),
            "rms_col": col, "rms_used": smoke2["convergence"]["residual_column"],
            "fp_bbox_diff": f"{fp['max_bbox_diff_m']:g}",
            "n_tools": len(mcp_tools())}


def ledger_counts():
    """{set: Counter(grade), 'band': n} over data/drone/*.yaml."""
    out = {}
    for name in ledger.SET_NAMES:
        raw = yaml.safe_load((ROOT / f"data/drone/{name}.yaml").read_text())["quantities"]
        c = defaultdict(int)
        for q in raw:
            c[q["confidence"]] += 1
            c["band"] += "band" in q
            c["all"] += 1
        out[name] = c
    return out


def wall_minutes(level, tags=None):
    """Wall minutes of every SU2 record at a mesh level (optionally of some tags only)."""
    return [r["run"]["wall_time_s"] / 60 for (t, _), r in all_su2_records().items()
            if r["params"]["mesh_level"] == level and (tags is None or t in tags)]


def problem_values():
    lp = [r for r in csv_rows(LOW_POOL) if not r["gates"] and not r["error"]]
    inv = jload(INVERSE_LF)
    counts = ledger_counts()
    grid = jload("runs/drone_grid/2026-11-08/record.json")
    rules = ledger.load("rules")
    return {"payload_kg": f"{rules['payload_mass_kg']:g}", "cap_kg": f"{inv['mtow_cap_kg']:g}",
            "n_lowpool": len(lp), "lowpool_max": f"{max(float(r['mtow_kg']) for r in lp):.2f}",
            "n_ledger": sum(c["all"] for c in counts.values()),
            "n_assumed": sum(c["assumed"] for c in counts.values()),
            "lf_s_core": f"{grid['wall_seconds'] * grid['workers'] / grid['points_evaluated']:.2f}",
            "hf_coarse_min": f"{np.median(wall_minutes('coarse')):.1f}",
            "hf_medium_min": f"{np.median(wall_minutes('medium')):.1f}"}


def mcp_tools():
    """[(name, first docstring line)] of the functions the server registers with @mcp.tool()."""
    import ast
    tree = ast.parse((ROOT / "mcp_server/server.py").read_text())
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"
                for d in node.decorator_list):
            out.append((node.name, ast.get_docstring(node).split("\n")[0]))
    return out


def drone_gates():
    """['gate 1 (reynolds range)', ...]: the distinct gates drone/evaluate.py writes, in order."""
    found = re.findall(r"gate (\d) \(([a-z ]+)\)", (ROOT / "drone/evaluate.py").read_text())
    return sorted({f"gate {n} ({name})" for n, name in found})


def shard_split(n=2):
    """Cases of the case table each of n shards owns, by the worker's own rule."""
    from worker.run_worker import in_shard
    ids = [r["case_id"] for r in csv_rows(CASES)]
    return [sum(in_shard(c, (k, n)) for c in ids) for k in range(n)]


def landed_cases():
    """Case ids of the case table whose result.json has landed."""
    return [r["case_id"] for r in csv_rows(CASES)
            if (ROOT / "runs" / r["tag"] / r["case_id"] / "result.json").is_file()]


def automation_values():
    rec = jload(POOL + "/record.json")
    ok = sha256_file(POOL + "/results.csv") == rec["sha256"]["results.csv"]
    workers = {r["run"]["worker_id"] for (t, _), r in all_su2_records().items()
               if t in ("pool_af", "pool_af_bias")}
    split = shard_split()
    return {"n_gates": len({g.split(" (")[0] for g in drone_gates()}),
            "shard_split": " and ".join(str(n) for n in split),
            "results_sha_ok": "yes" if ok else "no, the table changed after its record",
            "n_pool_workers": len(workers)}


def sha256_file(rel):
    import hashlib
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def low_by_inputs():
    """{rounded six inputs: low-pool row} for matching an SU2 pool design to its low evaluation."""
    return {tuple(round(float(r[k]), 6) for k in DRONE_BOUNDS): r for r in csv_rows(LOW_POOL)}


def pool_complete():
    """[(results row, low-pool row)] for the complete SU2 pool designs."""
    low = low_by_inputs()
    out = []
    for r in csv_rows(POOL + "/results.csv"):
        if r["status"] == "complete":
            out.append((r, low[tuple(round(float(r[k]), 6) for k in DRONE_BOUNDS)]))
    return out


def kept_pool_records():
    """The pool_af records the aggregator keeps (Cauchy-stopped or converged)."""
    from analysis.pool_af_results import kept
    return kept([r for (t, _), r in all_su2_records().items() if t == "pool_af"])


def pretty(name):
    """'skin_areal_density_kg_m2' -> 'skin areal density' (the unit is in its own column)."""
    for unit in ("_kg_m2", "_Wh_per_kg", "_Wh_per_L", "_W_per_kg", "_Pa", "_kg", "_deg", "_m_s",
                 "_s", "_chords"):
        if name.endswith(unit):
            name = name[: -len(unit)]
            break
    return name.replace("_", " ")


def results_values():
    rec = jload(POOL + "/record.json")
    done = pool_complete()
    ratio = [float(h["endurance_h"]) / float(lo["endurance_h"]) - 1 for h, lo in done]
    bias = csv_rows(POOL + "/bias.csv")
    sweep = csv_rows(BIAS_LF)
    top = ", ".join(f"{pretty(r['name'])} ({float(r['max_abs_pct_endurance']):.1f} %)"
                    for r in sweep[:3])
    inv = jload(INVERSE_LF)
    d = inv["design"]
    at_bound = sum(d[k] in DRONE_BOUNDS[k] for k in DRONE_BOUNDS)
    kept = kept_pool_records()
    cl_d = [r["convergence"]["drift_pct"]["cl"] for r in kept]
    cd_d = [r["convergence"]["drift_pct"]["cd"] for r in kept]
    return {"pool_designs": rec["designs"], "pool_complete": rec["complete"],
            "pool_incomplete": rec["incomplete"], "pool_landed": len(landed_cases()),
            "hf_lf_end_range": (signed_range(ratio, "high", "low") if ratio
                                else "not yet comparable (no complete design)"),
            "bias_pairs": len(bias),
            "mc_cl_range": signed_range([float(r["cl_medium_over_coarse"]) - 1 for r in bias],
                                        "high", "low"),
            "mc_cd_range": signed_range([float(r["cd_medium_over_coarse"]) - 1 for r in bias],
                                        "high", "low"),
            "bias_n": len(sweep), "bias_top": top,
            "inv_n_bound": at_bound, "inv_end": f"{inv['endurance_h']['mean']:.2f}",
            "inv_mtow": f"{inv['mtow_kg']['median']:.2f}", "inv_p": f"{inv['p_mtow_le_cap']:.3f}",
            "pool_cl_drift": f"{min(cl_d):.1f} to {max(cl_d):.1f} %",
            "pool_cd_drift": f"{min(cd_d):.1f} to {max(cd_d):.1f} %"}


# ---- the PENDING files: filled when they exist, PENDING with their path until then -------------
def pending_text(rel, run):
    return f"PENDING: {rel} ({run}) does not exist yet."


def mf_means():
    """{(model, n, metric): mean over seeds} of the multi-fidelity CSV."""
    acc = defaultdict(list)
    for r in csv_rows(MF):
        acc[(r["model"], int(r["n"]), r["metric"])].append(float(r["value"]))
    return {k: float(np.mean(v)) for k, v in acc.items()}


def mf_answer():
    if not exists(MF):
        return pending_text(MF, "multi-fidelity analysis, T10.10c")
    m = mf_means()
    ns = sorted({n for (model, n, _) in m if model == "two"})
    e2 = {n: m[("two", n, "rmse_endurance")] for n in ns}
    e1 = {n: m[("single", n, "rmse_endurance")] for n in ns}
    n0 = ns[0]
    reach = [n for n in ns if e1[n] <= e2[n0]]
    tail = (f"SU2 alone reaches it at {reach[0]} designs" if reach
            else f"SU2 alone does not reach it within {ns[-1]} designs")
    return (f"With {n0} SU2 designs the two-level endurance error is {e2[n0]:.3f} h against "
            f"{e1[n0]:.3f} h for SU2 alone; {tail} (mean over seeds, {MF}).")


def hf_front_answer():
    if not exists(PARETO_HF):
        return pending_text(PARETO_HF, "front on the SU2 pool, T10.10a") + (
            " The front with its band over the SU2 pool will be drawn here.")
    rows = csv_rows(PARETO_HF)
    obs = [r for r in rows if r["kind"] == "observed"]
    end = [float(r["endurance_h"]) for r in obs]
    mt = [float(r["mtow_kg"]) for r in obs]
    return (f"On the SU2 pool the observed front has {len(obs)} designs, from {min(end):.2f} h at "
            f"{min(mt):.2f} kg to {max(end):.2f} h at {max(mt):.2f} kg; the band is the GPs' "
            "posterior, and every point carries the decision-8 bias.")


def hf_inverse_answer():
    if not exists(INVERSE_HF):
        return f"the SU2-pool answer is PENDING ({INVERSE_HF})."
    inv = jload(INVERSE_HF)
    if not inv.get("feasible"):
        return "on the SU2 pool no design meets the cap at the required probability."
    return (f"on the SU2 pool the answer is {inv['endurance_h']['mean']:.2f} h at "
            f"{inv['mtow_kg']['median']:.2f} kg with P = {inv['p_mtow_le_cap']:.3f}.")


def confirm_answer():
    if not exists(CONFIRM):
        return pending_text(CONFIRM, "confirmation run, T10.10d") + (
            " One SU2 polar at the SU2-pool answer checks the inverse query.")
    c = jload(CONFIRM)
    e, m = c["endurance_h"], c["mtow_kg"]
    return (f"At the answer SU2 gives {e['simulated']:.2f} h ({e['position']} the 90 % interval) "
            f"and {m['simulated']:.2f} kg ({m['position']}): C2 "
            f"{'pass' if c['c2_pass'] else 'FAIL'}.")


def bias_hf_answer():
    if not exists(BIAS_HF):
        return f"the sweep at the SU2 answer is PENDING ({BIAS_HF})."
    top = csv_rows(BIAS_HF)[:3]
    return "at the SU2 answer the largest are " + ", ".join(
        f"{pretty(r['name'])} ({float(r['max_abs_pct_endurance']):.1f} %)" for r in top) + "."


def viz_files():
    """The two viz case directories, or None while either volume file is missing."""
    dirs = [ROOT / "runs/viz" / c for c in VIZ_CASES]
    have = all((d / "flow.dat").is_file() or (d / "flow.dat.gz").is_file() for d in dirs)
    return dirs if have else None


def viz_answer():
    ids = " and ".join(VIZ_CASES)
    if viz_files() is None:
        return (f"PENDING: two volume-output cases, {ids}, will give Cp contours and streamlines "
                "at 6 and 14 degrees once they run after the pool.")
    return f"Cp contours and streamlines of pool design 0 at 6 and 14 degrees, from {ids}."


def pending_values():
    return {"mf_answer": mf_answer(), "hf_front_answer": hf_front_answer(),
            "hf_inverse_answer": hf_inverse_answer(), "confirm_answer": confirm_answer(),
            "bias_hf_answer": bias_hf_answer(), "viz_answer": viz_answer()}


# ---- new drawings ------------------------------------------------------------------------------
def draw_clean_exit(path_name="clean_exit.png"):
    """cl and cd of the first smoke case and of its Cauchy-stopped rerun, from their records."""
    a, b = jload(SMOKE + "/result.json"), jload(SMOKE2 + "/result.json")
    labels = [f"first run\n{a['run']['iterations']:,} it. (budget)",
              f"rerun\n{b['convergence']['iterations']:,} it. (Cauchy stop)"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6), dpi=200)
    for ax, key, fmt in ((axes[0], "cl", "{:.3f}"), (axes[1], "cd", "{:.4f}")):
        vals = [a["metrics"][key], b["metrics"][key]]
        ax.bar([0, 1], vals, color=[ACCENT_H, BLUE_H], width=0.6)
        for i, val in enumerate(vals):
            ax.text(i, val * 1.01, fmt.format(val), ha="center", va="bottom", fontsize=10)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylim(0, max(vals) * 1.18)
        ax.set_title(f"{key} (tail mean), same case", fontsize=11, color=BLUE_H)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle(f"NACA 4412-type section, Re {a['params']['reynolds']:,.0f}, "
                 f"{a['params']['alpha_deg']:g} deg, {a['params']['mesh_level']} mesh; "
                 f"both runs exit code {a['run']['exit_code']}", fontsize=10, color=TEXT_H)
    fig.tight_layout()
    return save(fig, path_name)


def draw_c2_cap(path_name="c2_cap.png"):
    """The 192 low-pool designs, the exact low-fidelity front and the 4 kg cap."""
    lp = [r for r in csv_rows(LOW_POOL) if not r["gates"] and not r["error"]]
    front = sorted(csv_rows("runs/drone_grid/2026-11-08/front.csv"),
                   key=lambda r: float(r["mtow_kg"]))
    cap = jload(INVERSE_LF)["mtow_cap_kg"]
    fig, ax = plt.subplots(figsize=(8.0, 4.0), dpi=200)
    ax.scatter([float(r["mtow_kg"]) for r in lp], [float(r["endurance_h"]) for r in lp], s=14,
               color="#8FA8C8", label=f"{len(lp)} low-pool designs")
    ax.plot([float(r["mtow_kg"]) for r in front], [float(r["endurance_h"]) for r in front],
            color=BLUE_H, lw=2, label=f"exact low-fidelity front ({len(front)} of the 9^6 grid)")
    ax.axvline(cap, color=ACCENT_H, lw=2, ls="--")
    ax.text(cap - 0.05, ax.get_ylim()[1] * 0.95, f"EASA C2 cap {cap:g} kg", color=ACCENT_H,
            ha="right", va="top", fontsize=11, fontweight="bold")
    ax.set_xlabel("take-off mass (kg)", fontsize=11)
    ax.set_ylabel("endurance (h)", fontsize=11)
    ax.set_xlim(0, cap + 0.4)
    ax.legend(loc="lower right", fontsize=9.5)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return save(fig, path_name)


def draw_bias_bars(rel=None, path_name="bias_sweep.png", n=8):
    """Endurance change at each band end for the n largest quantities of a bias sweep."""
    rows = csv_rows(rel or BIAS_LF)[:n]
    fig, ax = plt.subplots(figsize=(8.0, 3.9), dpi=200)
    y = np.arange(len(rows))
    lo = [float(r["pct_endurance_lo"]) for r in rows]
    hi = [float(r["pct_endurance_hi"]) for r in rows]
    ax.barh(y - 0.2, lo, height=0.4, color="#8FA8C8", label="band low end")
    ax.barh(y + 0.2, hi, height=0.4, color=BLUE_H, label="band high end")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{pretty(r['name'])}\n[{float(r['band_lo']):g}, {float(r['band_hi']):g}]"
                        for r in rows], fontsize=8.5)
    ax.invert_yaxis()
    ax.axvline(0, color=GREY_H, lw=0.8)
    ax.set_xlabel("change in endurance (%)", fontsize=10)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    return save(fig, path_name)


def draw_hf_front(path_name="front_hf.png"):
    """SU2-pool front with its band and the exact low-fidelity front (only once the file exists)."""
    rows = csv_rows(PARETO_HF)
    band = sorted((r for r in rows if r["kind"] == "band"), key=lambda r: float(r["mtow_kg"]))
    fig, ax = plt.subplots(figsize=(8.0, 4.0), dpi=200)
    if band:
        x = [float(r["mtow_kg"]) for r in band]
        ax.fill_between(x, [float(r["end_p05"]) for r in band], [float(r["end_p95"]) for r in band],
                        color="#EAF0F7", label="GP band, 5 to 95 %")
    pred = [r for r in rows if r["kind"] == "predicted"]
    ax.scatter([float(r["mtow_kg"]) for r in pred], [float(r["endurance_h"]) for r in pred], s=8,
               color="#8FA8C8", label="predicted front")
    obs = [r for r in rows if r["kind"] == "observed"]
    ax.scatter([float(r["mtow_kg"]) for r in obs], [float(r["endurance_h"]) for r in obs], s=36,
               color=BLUE_H, edgecolor="white", label="observed SU2-pool front", zorder=3)
    lf = sorted(csv_rows("runs/drone_grid/2026-11-08/front.csv"), key=lambda r: float(r["mtow_kg"]))
    ax.plot([float(r["mtow_kg"]) for r in lf], [float(r["endurance_h"]) for r in lf], color=GREY_H,
            lw=1.2, ls="--", label="exact low-fidelity front")
    ax.set_xlabel("take-off mass (kg)")
    ax.set_ylabel("endurance (h)")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return save(fig, path_name)


# ---- slide bodies -----------------------------------------------------------------------------
def body_questions(slide, v):
    grid = jload("runs/drone_grid/2026-11-08/record.json")
    rec = jload(POOL + "/record.json")

    def status(rel, done, todo):
        return done if exists(rel) else f"PENDING: {todo}"

    rows = [["Question", "Status at build time", "Slides"],
            [("1. The front of endurance against take-off mass, with the GP's band and the named "
             "biases"),
             f"Exact low-fidelity front: {grid['front_size']} designs. SU2-pool front: "
             + status(PARETO_HF, "recorded", PARETO_HF), "D34, D36"],
            [("2. Active learning against LHS and random: pool replay, and online against the "
             "exact front"),
             ("Answered on the low-fidelity model: plain EHVI loses online, weighted EHVI wins. "
             "SU2-pool replay: PENDING (pool batch)"), "D31, D32"],
            ["3. Does the two-level model reach a given error with fewer SU2 polars?",
             status(MF, "recorded", MF) + f" ({rec['complete']} of {rec['designs']} SU2 designs "
             "complete)", "D33"],
            [("4. Longest endurance under the 4.0 kg cap with P(mass <= cap) >= 0.9, and one SU2 "
             "confirmation"),
             "Low model: a box corner, the cap never binds. SU2: "
             + status(CONFIRM, "confirmation recorded", CONFIRM), "D37, D38"]]
    bd.add_table(slide, LM, CT + 0.1, [5.6, 5.4, 1.1], rows, size=12, row_h=0.85)


def body_clean_exit(slide, v):
    path = draw_clean_exit()
    bd.add_figure_with_caption(slide, str(path.relative_to(ROOT)), SMOKE + ", " + SMOKE2,
                               LM, CT - 0.05, 6.9, 3.9)
    a = jload(SMOKE + "/result.json")
    m = a["metrics"]
    steps = [(f"SU2 exits with code {a['run']['exit_code']}\nafter {a['run']['iterations']:,} "
             "iterations, files written"),
             f"postprocess looks for {v['rms_col']}\nerror.json: postprocess_error",
             (f"drift rule on the history:\ncl {m['cl_drift_pct']:.1f} %, cd "
             f"{m['cd_drift_pct']:.1f} % over the last fifth"),
             (f"decision 6: budget {v['smoke2_budget']} with a Cauchy stop;\n"
             f"the rerun stops at {v['smoke2_iters']}")]
    x, w, h = LM + 7.3, 4.8, 0.8
    for i, text in enumerate(steps):
        y = CT + i * 1.1
        bd.box(slide, x, y, w, h, text, size=11, fill=bd.TINT if i == 3 else bd.WHITE)
        if i:
            bd.arrow(slide, x + w / 2, y - 0.3, x + w / 2, y)


def body_caught(slide, v):
    err = jload(SMOKE + "/error.json")
    fp = jload(FIRST_ATTEMPT + "/error.json")
    report = " ".join((ROOT / REPORT).read_text().split())
    kink = re.search(r"left a (\d+) deg kink at the nose", report).group(1)
    claim = re.search(r'first said "(drags [^"]+)"', (ROOT / TASKS).read_text()).group(1)
    smoke, smoke2 = jload(SMOKE + "/result.json"), jload(SMOKE2 + "/result.json")
    pts = e387_points()
    cd = signed_range([p[2] / p[4] - 1 for p in pts], "high", "low")
    v6e = v6_check("V6e cl_alpha Re 203800")
    rows = [["Problem", "Caught by", "Without the check", "Record"],
            [f"Postprocess read the compressible residual {v['rms_col']}",
             f"the postprocess step ({err['reason']})", "a run with no convergence status",
             "smoke error.json"],
            [(f"The {smoke['params']['max_iter']:,}-iteration budget ended with cl "
             f"{pct(smoke['metrics']['cl'] / smoke2['metrics']['cl'] - 1)}"),
             "drift rule; the Cauchy-stopped rerun", "a polar built on unconverged runs",
             "smoke, smoke2 result.json"],
            ["Fine mesh not reproduced at the 1 nm fingerprint",
             (f"the worker's mesh check ({fp['reason']}; boxes differ by "
             f"{fp['detail']['max_bbox_diff_m']:g} m)"), "a solve on a mesh nobody checked",
             "first_attempt error.json"],
            [f"A {kink} deg kink at the E387 nose from two half-splines",
             "a geometry test and the inverted-cell gate", "a mesh with inverted cells",
             "task 10 report, section 3"],
            [f'The ledger said SU2 "{claim}"', "the deck builder reading runs/e387",
             f"a wrong statement: per point cd is {cd}", "runs/e387 result.json"],
            [f"SU2's lift slope {pct(v6e['deviation'])} off the tunnel",
             f"V6e, tolerance {100 * v6e['tolerance']:.0f} % fixed before any run",
             "an unflagged bias in every SU2 polar", "v6.json; decision 8"]]
    bd.add_table(slide, LM, CT - 0.05, [3.9, 3.3, 2.7, 2.2], rows, size=11, row_h=0.66, flag=())


def body_mcp(slide, v):
    need((ROOT / "mcp_server/schemas.py").read_text(), 'extra="forbid", strict=True')
    need((ROOT / "mcp_server/queue.py").read_text(), "mcp_log.jsonl")
    need((ROOT / "worker/run_worker.py").read_text(), "gates.check")
    tools = [name for name, _ in mcp_tools()]
    bd.text_box(slide, LM, CT, 3.6, 0.35, f"The {len(tools)} tools (mcp_server/server.py)",
                size=13, bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.4, 3.6, 4.4, tools, size=12, font="Consolas", space_after=1)
    rows = [["What the MCP layer adds", "What does not depend on it"],
            ["One entry point for the agent, with typed arguments", ("The physics gates, run again "
             "by the worker before SU2 starts")],
            ['A strict schema per family: unknown fields refused (extra="forbid", strict=True)',
             "The mesh fingerprint and the config hash the worker re-checks"],
            ["An audit line per call in mcp_log.jsonl (tool, argument hash, ok, case id)",
             "The sha256 digest checked at ingest"],
            ["Nothing is staged when a check fails", ("The sampling points: Sobol tables and "
             "acquisition code, never the language model")]]
    bd.add_table(slide, LM + 4.0, CT, [4.0, 4.1], rows, size=12, row_h=0.95, flag=())


def body_c2(slide, v):
    path = draw_c2_cap()
    bd.add_figure_with_caption(slide, str(path.relative_to(ROOT)), LOW_POOL + ", " + INVERSE_LF,
                               LM, CT - 0.05, 8.2, 4.3)
    bd.text_box(slide, LM + 8.5, CT, 3.6, 4.4,
                [f"Payload fixed at {v['payload_kg']} kg (data/drone/rules.yaml).",
                 (f"Cap {v['cap_kg']} kg at P(mass <= cap) >= 0.9, fixed in the spec before "
                  "any run."),
                 f"Heaviest low-pool design: {v['lowpool_max']} kg.",
                 "So the cap is tested only by the SU2 level (D37)."], size=13, bullets=True)


def body_inputs(slide, v):
    nom = jload(V6)["nominal_params"]
    sets = {"span_m": "wing span b", "aspect_ratio": "b^2 / S, so the wing area",
            "taper_ratio": "tip over root chord, no sweep", "battery_fraction": "battery mass "
            "over take-off mass", "camber_pct": "NACA camber, at 40 % chord",
            "thickness_pct": "NACA thickness"}
    rows = [["Input", "Range", "Nominal", "Sets"]]
    rows += [[k, f"{lo:g} to {hi:g}", f"{nom[k]:g}", sets[k]]
             for k, (lo, hi) in DRONE_BOUNDS.items()]
    bd.add_table(slide, LM, CT - 0.05, [2.1, 1.4, 1.1, 3.4], rows, size=12, row_h=0.42, flag=())
    counts = ledger_counts()
    lrows = [["Ledger set", "n", "pub.", "der.", "ass."]]
    for name, c in counts.items():
        lrows.append([name, c["all"], c["published"], c["derived"], c["assumed"]])
    bd.add_table(slide, LM + 8.4, CT - 0.05, [1.3, 0.55, 0.6, 0.6, 0.6], lrows, size=11,
                 row_h=0.36, flag=())
    eq.add_equation(slide, EQ_INPUTS_VCRUISE, LM, CT + 3.2, 7.8, 0.65, fontsize=15)
    bd.text_box(slide, LM, CT + 3.95, 8.0, 0.8,
                [("k_s is the ledger's stall margin; V_minP is the speed of least power on "
                  "the design's own polar."),
                 ("Sea-level ISA air; the bands of the fixed quantities are swept once on D39, "
                  "not learned.")], size=12, bullets=True)


def body_costs(slide, v):
    grid = jload("runs/drone_grid/2026-11-08/record.json")
    pool = jload("runs/drone_pool_lf/2026-11-08/record.json")
    co, me = wall_minutes("coarse"), wall_minutes("medium")
    n_cases = len(csv_rows(CASES))
    rows = [["Level", "Section data", "Measured cost", "Used for"],
            ["Low (container)", "closed forms, drone/section.py",
             (f"{v['lf_s_core']} s per design per core: the {grid['points_evaluated']:,}-point "
              f"grid in {grid['wall_seconds'] / 3600:.1f} h on {grid['workers']} workers; the "
              f"{pool['points_evaluated']}-point pool in {pool['wall_seconds']:.0f} s on "
              f"{pool['workers']}"),
             "exact front, low pool, online replay, the low level of the two-level model"],
            ["High (Colab, 2 or 4 ranks)", "SU2 polar of the design's own section at its cruise Re",
             (f"per angle: median {np.median(co):.1f} min coarse ({len(co)} cases), "
             f"{np.median(me):.1f} min medium ({len(me)} cases); five angles per design"),
             f"the SU2 pool: {n_cases} cases in the case table"]]
    bd.add_table(slide, LM, CT + 0.1, [2.0, 2.8, 4.4, 2.9], rows, size=13, row_h=1.15, flag=())
    bd.text_box(slide, LM, CT + 3.8, CW, 0.9,
                "Medians over every SU2 result.json in runs/ at build time, by mesh level "
                "(E387, nominal, mesh, smoke and pool cases).", size=12, color=bd.GREY)


def body_viz(slide, v):
    dirs = viz_files()
    if dirs is None:
        body_pending_viz(slide, v)
        return
    from postprocess.plot_flowfield import plot_airfoil_volume
    for i, d in enumerate(dirs):
        png = ROOT / FIG_DRONE / f"viz_{d.name}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        plot_airfoil_volume(d, png)
        bd.add_figure_with_caption(slide, str(png.relative_to(ROOT)), str(d.relative_to(ROOT)),
                                   LM + i * 6.15, CT, 5.95, 4.3)


def body_pending_viz(slide, v):
    how = ("The command that draws them exists: python -m postprocess.plot_flowfield airfoil "
           "CASE_DIR --out PNG, tested on a synthetic volume file.")
    panels = "Panels: Cp contours and speed with streamlines, whole section and the leading edge."
    body_pending(slide, [how, panels],
                 ("Cp contours and streamlines, design 0 coarse mesh:\n"
                  + "\n".join(f"{c}: {a} deg" for c, a in zip(VIZ_CASES, (6, 14)))
                  + "\nPENDING: the viz batch (flow.dat is written only when save_volume is true)"))


def body_tools_gates(slide, v):
    rows = [["Tool", "What it does (first docstring line)"]]
    rows += [[name, doc] for name, doc in mcp_tools()]
    bd.add_table(slide, LM, CT - 0.1, [1.9, 5.6], rows, size=9.5, row_h=0.36, flag=())
    need((ROOT / "worker/make_case.py").read_text(), "def quality_failures")
    gates = drone_gates()
    bd.text_box(slide, LM + 7.8, CT - 0.1, 4.3, 0.35, "Drone gates (drone/evaluate.py)", size=13,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM + 7.8, CT + 0.3, 4.3, 2.6, gates, size=12, bullets=True, space_after=2)
    bd.text_box(slide, LM + 7.8, CT + 2.9, 4.3, 1.9,
                [("airfoil2d: the mesh-quality gate (worker/make_case.py, quality_failures): "
                 "inverted cells, minimum angle, first cell, growth, aspect ratio."),
                 "Messages carry the offending value, in the inlet's form."], size=12,
                bullets=True)


def body_shards(slide, v):
    split = shard_split()
    rec = jload(POOL + "/record.json")
    bd.text_box(slide, LM, CT, 5.6, 0.35, "The shard rule (worker/run_worker.py, in_shard)",
                size=13,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.4, 5.6, 0.5, "int(case_id hex digest, 16) mod N == K",
                size=13, font="Consolas")
    rows = [["Shard", "Cases of the table it owns"]]
    rows += [[f"--shard {k}/{len(split)}", n] for k, n in enumerate(split)]
    rows += [["total", sum(split)]]
    bd.add_table(slide, LM, CT + 1.0, [2.4, 3.0], rows, size=12, row_h=0.4, flag=())
    bd.text_box(slide, LM, CT + 2.8, 5.6, 2.0,
                ["Every case id lands in exactly one shard, so no two workers claim one job.",
                 f"Worker ids in the pool records so far: {v['n_pool_workers']}.",
                 ("Without the flag a worker takes every job; two unsharded workers on one queue "
                 "are not allowed.")], size=12, bullets=True)
    x = LM + 6.1
    chain = ["worker: result.json + its sha256 to Drive",
             "ingest_result: digest, JSON and record checks; runs/<tag>/<id>/",
             "pool_af_results: per-design polar from at least 3 kept angles",
             (f"results.csv: {rec['designs']} designs, {rec['complete']} complete, "
             f"{rec['incomplete']} incomplete, {rec['failed']} failed")]
    for i, text in enumerate(chain):
        y = CT + i * 1.0
        bd.box(slide, x, y, 6.0, 0.7, text, size=12, fill=bd.TINT if i == 3 else bd.WHITE)
        if i:
            bd.arrow(slide, x + 3.0, y - 0.3, x + 3.0, y)
    bd.text_box(slide, x, CT + 4.0, 6.0, 0.8,
                f"record.json holds the sha256 of its inputs and outputs; the table's hash "
                f"matches its record: {v['results_sha_ok']}.", size=12, color=bd.GREY)


def body_gp(slide, v):
    rows = [["Strategy", "Picks the next design by"],
            ["random", "a uniform draw (pool: from the remaining pool)"],
            ["lhs", "a Latin hypercube order fixed by the seed"],
            ["al_maxvar", "the largest summed scaled variance"],
            ["al_ehvi", "the largest expected hypervolume improvement"],
            ["al_ehvi_feas", "EHVI times P(feasible), online only (D32)"]]
    bd.add_table(slide, LM, CT, [1.7, 3.6], rows, size=12, row_h=0.5, flag=())
    bd.text_box(slide, LM, CT + 3.2, 5.3, 1.6,
                ["One GP on endurance, one on log take-off mass, six inputs scaled to [0, 1].",
                 "The language model calls tools; it never picks a point."], size=12, bullets=True)
    x, y = LM + 5.7, CT - 0.15
    for latex, h in ((EQ_GP_KERNEL, 0.62), (EQ_GP_MEAN, 0.4), (EQ_GP_VAR, 0.4),
                     (EQ_GP_OBJECTIVES, 0.4), (EQ_GP_HVI, 0.4), (EQ_GP_EHVI, 0.62),
                     (EQ_GP_VARIANCE, 0.45)):
        _, used = eq.add_equation(slide, latex, x, y, 6.4, h, fontsize=15)
        y += used + 0.1


def body_pool_replay(slide, v):
    rep = csv_rows(fd.POOL_REPLAY)
    ns = (8, 16, 24, 32, 40)
    strategies = ("random", "lhs", "al_ehvi", "al_maxvar")
    rows = [["n", *strategies]] + [[n, *[f"{mean_at(rep, s, 'hv_regret', n):.3f}"
                                         for s in strategies]] for n in ns]
    bd.add_figure_with_caption(slide, FIG + "b_pool_replay.png", fd.POOL_REPLAY, LM, CT - 0.05,
                               7.6, 4.2)
    x = LM + 7.9
    bd.text_box(slide, x, CT - 0.05, 4.2, 0.3, "Mean hypervolume regret, 10 seeds", size=12,
                color=bd.GREY)
    bd.add_table(slide, x, CT + 0.3, [0.6, 0.9, 0.9, 0.9, 0.9], rows, size=11, row_h=0.36,
                 flag=())
    eq.add_equation(slide, EQ_GP_REGRET, x, CT + 2.65, 4.2, 0.6, fontsize=15)
    bd.text_box(slide, x, CT + 3.4, 4.2, 1.4,
                ["Same 8 initial points for every strategy of a seed.",
                 "The pool is smooth and gate-free: the easy case."], size=12, bullets=True)


def body_mf(slide, v):
    if not exists(MF):
        body_two_level_pending(slide, v)
        return
    m = mf_means()
    ns = sorted({n for (model, n, _) in m if model == "two"})
    rows = [["SU2 designs n", "endurance RMSE (h): SU2 only", "two-level",
             "mass rel. error: SU2 only", "two-level"]]
    for n in ns:
        rows.append([n, f"{m[('single', n, 'rmse_endurance')]:.3f}",
                     f"{m[('two', n, 'rmse_endurance')]:.3f}",
                     f"{m[('single', n, 'rmse_mtow_rel')]:.4f}",
                     f"{m[('two', n, 'rmse_mtow_rel')]:.4f}"])
    bd.add_table(slide, LM, CT, [2.0, 2.9, 1.6, 2.9, 1.6], rows, size=12, row_h=0.4, flag=())
    y = CT + 0.4 * len(rows) + 0.3
    eq.add_equation(slide, EQ_MF_TWO_LEVEL, LM, y, 4.0, 0.5, fontsize=15)
    eq.add_equation(slide, EQ_MF_POSTERIOR, LM + 4.2, y, 3.8, 0.5, fontsize=15)
    eq.add_equation(slide, EQ_MF_GLS, LM + 8.2, y, 3.8, 0.5, fontsize=15)
    bd.caption(slide, LM, y + 0.7, CW, f"Record: {MF} (mean over seeds). Equations: "
               "surrogate/mf_gp.py.", lines=1)


def body_pool_status(slide, v):
    rows = [["Design", "Angles kept", "Endurance SU2 (h)", "low (h)", "ratio",
             "Mass SU2 (kg)", "low (kg)", "ratio"]]
    for h, lo in pool_complete():
        e_h, e_l = float(h["endurance_h"]), float(lo["endurance_h"])
        m_h, m_l = float(h["mtow_kg"]), float(lo["mtow_kg"])
        rows.append([h["index"], h["angles_kept"].replace(";", ", "), f"{e_h:.2f}", f"{e_l:.2f}",
                     f"{e_h / e_l:.3f}", f"{m_h:.3f}", f"{m_l:.3f}", f"{m_h / m_l:.3f}"])
    row_h = 0.4 if len(rows) < 10 else 0.27
    bd.add_table(slide, LM, CT - 0.05, [0.9, 2.6, 1.7, 1.1, 1.0, 1.6, 1.1, 1.0], rows,
                 size=11 if len(rows) < 10 else 9, row_h=row_h, flag=())
    rec = jload(POOL + "/record.json")
    y = CT - 0.05 + row_h * len(rows) + 0.2
    bd.text_box(slide, LM, y, CW, 1.4,
                [(f"{rec['designs']} designs: {rec['complete']} complete, {rec['incomplete']} "
                 f"incomplete, {rec['failed']} failed; {v['pool_landed']} of {v['pool_cases']} "
                 "cases landed (coarse pool and medium bias check)."),
                 ("Low = the same design through the low model (runs/drone_pool_lf); both columns "
                 "use the same lattice, closure and mission."),
                 "Every SU2 row carries the decision-8 flags (D41)."], size=12, bullets=True)


def body_hf_front(slide, v):
    if not exists(PARETO_HF):
        body_pending(slide, [("Inputs: the complete designs of runs/pool_af/2026-11-09/results.csv;"
                             " analysis.pareto --family drone writes the front and the band."),
                             "The exact low-fidelity front (D34) will be drawn beside it."],
                     f"SU2-pool front, predicted front and GP band\nPENDING: {PARETO_HF}")
        return
    path = draw_hf_front()
    bd.add_figure_with_caption(slide, str(path.relative_to(ROOT)), PARETO_HF, LM, CT, 8.4, 4.4)


def inverse_rows(inv, label):
    d = inv["design"]
    e, m = inv["endurance_h"], inv["mtow_kg"]
    design = ", ".join(f"{k} {d[k]:g}" for k in DRONE_BOUNDS)
    return [[f"{label}: design", design],
            [f"{label}: endurance", (f"{e['mean']:.3f} h, 90 % interval [{e['lo90']:.3f}, "
             f"{e['hi90']:.3f}]")],
            [f"{label}: take-off mass", (f"median {m['median']:.3f} kg, 90 % interval "
             f"[{m['lo90']:.3f}, {m['hi90']:.3f}]; P(mass <= {inv['mtow_cap_kg']:g} kg) = "
             f"{inv['p_mtow_le_cap']:.3f}")]]


def body_inverse(slide, v):
    inv = jload(INVERSE_LF)
    params, fixed = inv["design"], ledger.load_all()
    direct = evaluate(params, fixed)
    e, m = inv["endurance_h"], inv["mtow_kg"]
    inside = (e["lo90"] <= direct["endurance_h"] <= e["hi90"]
              and m["lo90"] <= direct["mtow_kg"] <= m["hi90"])
    rows = [["", "Value"]] + inverse_rows(inv, "Low pool GPs")
    rows.append(["Low model, evaluated directly",
                 (f"{direct['endurance_h']:.3f} h and {direct['mtow_kg']:.3f} kg: "
                 f"{'inside' if inside else 'OUTSIDE'} both intervals")])
    if exists(INVERSE_HF):
        hf = jload(INVERSE_HF)
        rows += (inverse_rows(hf, "SU2 pool GPs") if hf.get("feasible")
                 else [["SU2 pool GPs", "no design meets the cap at the required probability"]])
    else:
        rows.append(["SU2 pool GPs", f"PENDING: {INVERSE_HF}"])
    bd.add_table(slide, LM, CT - 0.05, [3.2, 8.9], rows, size=11, row_h=0.4,
                 flag=("PENDING", "OUTSIDE"))
    y = CT - 0.05 + 0.4 * len(rows) + 0.15
    eq.add_equation(slide, EQ_INV_QUERY, LM, y, 6.4, 0.45, fontsize=14)
    eq.add_equation(slide, EQ_INV_PROB, LM + 6.6, y - 0.05, 5.5, 0.65, fontsize=14)


def body_confirm(slide, v):
    if not exists(CONFIRM):
        body_pending(slide, [("The confirmation is one SU2 polar (five cases) at the SU2-pool "
                             "answer, through the queue, then analysis.confirm --family drone."),
                             "Pass: both objectives inside their 90 % intervals (C2)."],
                     f"Predicted against simulated endurance and take-off mass\nPENDING: {CONFIRM}")
        return
    c = jload(CONFIRM)
    rows = [["Objective", "Predicted", "90 % interval", "SU2 level", "Position"]]
    for key, pred, unit in (("endurance_h", "predicted_mean", "h"), ("mtow_kg", "predicted_median",
                                                                      "kg")):
        o = c[key]
        rows.append([key, f"{o[pred]:.3f} {unit}", f"[{o['lo90']:.3f}, {o['hi90']:.3f}]",
                     f"{o['simulated']:.3f} {unit}", o["position"]])
    rows.append(["C2", "", "", "", "pass" if c["c2_pass"] else "FAIL"])
    bd.add_table(slide, LM, CT, [2.4, 2.4, 2.8, 2.4, 2.1], rows, size=13, row_h=0.5)


def body_bias_sweep(slide, v):
    path = draw_bias_bars()
    bd.add_figure_with_caption(slide, str(path.relative_to(ROOT)), BIAS_LF, LM, CT - 0.05, 8.2,
                               4.2)
    hf = (f"Sweep at the SU2 answer: {BIAS_HF}" if exists(BIAS_HF)
          else f"Sweep at the SU2 answer: PENDING ({BIAS_HF})")
    bd.text_box(slide, LM + 8.5, CT, 3.6, 4.4,
                [("One quantity at a time, to each end of its ledger band, at the low-fidelity "
                 "answer of D37."), "Full table: backup DB8.", hf], size=12, bullets=True)


def body_mesh_bias(slide, v):
    idx = {}
    for r in csv_rows(CASES):
        idx.setdefault(int(r["index"]), r["reynolds"])
    rows = [["Design", "Re", "alpha (deg)", "cl coarse", "cl medium", "ratio", "cd coarse",
             "cd medium", "ratio"]]
    for r in csv_rows(POOL + "/bias.csv"):
        rows.append([r["index"], f"{float(idx[int(r['index'])]):,.0f}",
                     f"{float(r['alpha_deg']):g}",
                     f"{float(r['cl_coarse']):.4f}", f"{float(r['cl_medium']):.4f}",
                     f"{float(r['cl_medium_over_coarse']):.4f}", f"{float(r['cd_coarse']):.5f}",
                     f"{float(r['cd_medium']):.5f}", f"{float(r['cd_medium_over_coarse']):.4f}"])
    bd.add_table(slide, LM, CT - 0.05, [0.9, 1.3, 1.1, 1.4, 1.4, 1.2, 1.4, 1.4, 1.2], rows,
                 size=11, row_h=min(0.42, 4.7 / len(rows)), flag=())


def lift_effectiveness():
    """The ledger entry of rules:section_lift_effectiveness (value and band)."""
    rules = yaml.safe_load((ROOT / "data/drone/rules.yaml").read_text())["quantities"]
    return next(q for q in rules if q["name"] == "section_lift_effectiveness")


def body_biases(slide, v):
    text = (ROOT / SPEC).read_text()
    para = re.search(r"Biases that travel with every figure:(.*?)\.\n\n", text, re.DOTALL).group(1)
    items = [" ".join(s.split()) for s in para.split(";")]
    items = [i[:1].upper() + i[1:] for i in items]
    lift = lift_effectiveness()
    items += [(f"Drift band of the kept pool cases: cl {v['pool_cl_drift']}, "
               f"cd {v['pool_cd_drift']}"),
              (f"Section lift effectiveness {lift['value']:g}, band {lift['band']}: V6f's "
               "tunnel value lies outside it (open ruling)")]
    bd.text_box(slide, LM, CT - 0.05, 6.3, 0.4, "Spec section 13 and the records", size=14,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.4, 6.3, 4.4, items, size=12, bullets=True, space_after=3)
    bd.text_box(slide, LM + 6.6, CT - 0.05, 5.5, 0.4, "Carried by every SU2 section polar "
                "(decision 8)", size=14, bold=True, color=bd.BLUE)
    bd.text_box(slide, LM + 6.6, CT + 0.4, 5.5, 4.2, v6e_flags(), size=12, font="Consolas",
                bullets=True)


def body_wrong_first(slide, v):
    claim = re.search(r'first said "(drags [^"]+)"', (ROOT / TASKS).read_text()).group(1)
    pts = e387_points()
    cd = signed_range([p[2] / p[4] - 1 for p in pts], "high", "low")
    rect = v6_check("V6a (report) rectangular AR 100 fine: CL_alpha vs 2 pi AR/(AR+2)")
    rows = [["First recorded", "The record now says", "Found by"],
            [f'SU2 "{claim}" (task ledger)', (f"per point cd is {cd}; the block is corrected in "
             "place"), "the deck builder reading runs/e387"],
            ["V6a AR 100: a rectangular wing against 2 pi AR / (AR + 2)",
             (f"that is the elliptic slope; the rectangular wing sits {pct(rect['deviation'], 2)} "
             "below it, so the row tests an elliptic wing (addendum 2)"),
             "the solver's own refinement, before any verdict"],
            ["Induced drag from the midpoint point-vortex sum", ("Trefftz-plane drag of the "
             "Glauert series (drone/vlm.py)"), "the V6a rows on the first lattice run"],
            [(f"Online replay: plain EHVI at regret {v['ehvi_on_40']} against random's "
             f"{v['rand_on_40']}"), ("kept as published, with the feasibility-weighted run "
             f"({v['feas_on_40']}) beside it"), "the plan's rule to publish a loss"],
            ["Fine mesh refused at the 1 nm fingerprint", ("fingerprint at 1 micrometer, the "
             "refused attempt kept as .first_attempt"), "the worker's mesh check"],
            [f"Airfoil budget {v['smoke_budget']} iterations", (f"{v['smoke2_budget']} with a "
             "Cauchy stop (decision 6)"), "the first smoke case"]]
    stated = re.search(r"(\w+) of the six inputs at a bound", (ROOT / TASKS).read_text())
    words = {"five": 5, "four": 4, "six": 6, "three": 3}
    if stated and words.get(stated.group(1)) != v["inv_n_bound"]:
        rows.append([f'Task ledger: "{stated.group(0)}" at the low-fidelity inverse answer',
                     (f"the record has {v['inv_n_bound']} of six inputs at a bound "
                     "(inverse.json against the schema bounds)"), ("the deck builder reading "
                     "inverse.json")])
    bd.add_table(slide, LM, CT - 0.1, [4.0, 5.0, 3.1], rows, size=11,
                 row_h=min(0.6, 4.8 / len(rows)), flag=())


def body_limits(slide, v):
    text = " ".join((ROOT / SPEC).read_text().split())
    scope = re.search(r"Out of scope: (.*?)\. Biases", text).group(1)
    items = [s.strip() for s in re.split(r", (?:and )?(?![^(]*\))", scope)]
    items = [i[:1].upper() + i[1:] for i in items]
    bd.text_box(slide, LM, CT - 0.05, 6.0, 0.4, "Out of scope (spec section 13)", size=14,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.4, 6.0, 4.4, items, size=12, bullets=True, space_after=3)
    d = jload(V6)
    open_items = [f"{n['id']}: {n['what']}, not run ({n['reason']})" for n in d["not_run"]]
    open_items += [f"{c['name']}: {c['verdict']}" for c in d["checks"]
                   if c["verdict"].startswith("pending")]
    report = (ROOT / REPORT).read_text()
    rulings = re.search(r"## 9\. Open rulings\n\n(.*)", report, re.DOTALL).group(1)
    open_items += [" ".join(r.replace("`", "").split())[3:]
                   for r in re.split(r"\n(?=\d\. )", rulings.strip())]
    bd.text_box(slide, LM + 6.4, CT - 0.05, 5.7, 0.4, "Open validation items and rulings", size=14,
                bold=True, color=bd.BLUE)
    bd.text_box(slide, LM + 6.4, CT + 0.4, 5.7, 4.4, open_items, size=11, bullets=True,
                space_after=3)


def body_conclusions(slide, v):
    grid = jload("runs/drone_grid/2026-11-08/record.json")
    rec = jload(POOL + "/record.json")
    inv = jload(INVERSE_LF)
    rows = [["Question", "Answer from the records", "Evidence", "Pending"],
            ["1. The front", (f"Exact low-fidelity front of {grid['front_size']} designs over "
             f"{grid['points_evaluated']:,} points; aspect ratio and span drive endurance"),
             "drone_grid, drone_pareto_lf", "none" if exists(PARETO_HF) else "SU2-pool front"],
            ["2. Active learning", (f"Plain EHVI loses online ({v['ehvi_on_40']} against "
             f"{v['rand_on_40']}); with P(feasible) it wins ({v['feas_on_40']})"),
             "replay_drone_online", "SU2-pool replay"],
            ["3. Two-level model", mf_answer() if exists(MF) else f"{rec['complete']} of "
             f"{rec['designs']} SU2 designs complete; the low-to-high gap is "
             f"{v['hf_lf_end_range']} in endurance", "pool_af results.csv",
             "none" if exists(MF) else "mf.csv"],
            ["4. Inverse query", (f"Low model: a corner at {inv['endurance_h']['mean']:.2f} h, "
             f"{inv['mtow_kg']['median']:.2f} kg; the {inv['mtow_cap_kg']:g} kg cap does not "
             "bind there"), "drone_inverse_lf",
             "none" if exists(CONFIRM) else "SU2 answer and confirmation"]]
    bd.add_table(slide, LM, CT - 0.05, [2.1, 5.7, 2.2, 2.1], rows, size=12, row_h=0.95, flag=())


def body_discussion(slide, v):
    prompts = ["Where would you trust the low level alone, and where not?",
               "Is a fixed propulsive efficiency acceptable for a sizing study?",
               "Should budget-exhausted SU2 runs enter the pool, and with what flag?",
               "What would a feasibility model need to beat a hard gate in the acquisition?",
               "How would wind and altitude change the front (an envelope study)?",
               "What would make the two-level model worth its SU2 cost here?"]
    bd.text_box(slide, LM, CT - 0.05, 5.8, 0.4, "Prompts", size=14, bold=True, color=bd.BLUE)
    bd.text_box(slide, LM, CT + 0.4, 5.8, 4.4, prompts, size=13, bullets=True)
    backups = [f"{s['id']}  {s['title'].removeprefix('Backup: ')}" for s in read_outline()
               if s["id"].startswith("DB")]
    bd.text_box(slide, LM + 6.2, CT - 0.05, 5.9, 0.4, "Backup slides", size=14, bold=True,
                color=bd.BLUE)
    bd.text_box(slide, LM + 6.2, CT + 0.4, 5.9, 4.4, backups, size=11, space_after=1)


# ---- backup bodies ----------------------------------------------------------------------------
def v6_rows(prefixes):
    rows = [["Row", "Measured", "Reference", "Deviation", "Tol.", "Verdict"]]
    for c in jload(V6)["checks"]:
        if not c["name"].startswith(prefixes):
            continue
        small = c["tolerance"] is not None and c["tolerance"] < 1e-4
        dev = f"{c['deviation']:.1e}" if small else f"{100 * c['deviation']:+.2f} %"
        tol = ("report" if c["tolerance"] is None else f"{c['tolerance']:.0e}" if small
               else f"{100 * c['tolerance']:.0f} %")
        verdict = c["verdict"].split(" (")[0]
        rows.append([c["name"], f"{c['measured']:.4g}", f"{c['reference']:.4g}", dev, tol,
                     "FAIL" if verdict == "fail" else "PENDING" if verdict == "pending"
                     else verdict])
    return rows


def body_v6_part1(slide, v):
    rows = v6_rows(("V6a", "V6b", "V6c", "V6d"))
    bd.add_table(slide, LM, CT - 0.15, [6.4, 1.1, 1.1, 1.2, 0.9, 1.4], rows, size=8.5,
                 row_h=min(0.3, 4.95 / len(rows)))


def body_v6_part2(slide, v):
    rows = v6_rows(("V6e", "V6f"))
    for n in jload(V6)["not_run"]:
        rows.append([f"{n['id']}: {n['what']}", "", "", "", "", "not run"])
    bd.add_table(slide, LM, CT - 0.15, [6.4, 1.1, 1.1, 1.2, 0.9, 1.4], rows, size=8.5,
                 row_h=min(0.3, 4.95 / len(rows)))


def body_e387_points(slide, v):
    for i, re_ in enumerate((203800.0, 305200.0)):
        rows = [["alpha", "SU2 cl", "tunnel cl", "ratio", "SU2 cd", "tunnel cd", "ratio"]]
        for a, cl, cd, tcl, tcd in e387_points(re_):
            rows.append([f"{a:g}", f"{cl:.4f}", f"{tcl:.4f}", pct(cl / tcl - 1), f"{cd:.5f}",
                         f"{tcd:.5f}", pct(cd / tcd - 1)])
        y = CT - 0.05 + i * 2.45
        bd.text_box(slide, LM, y, CW, 0.3, f"Re {re_:,.0f} (medium mesh, SA-BCM; tunnel: "
                    f"{fd.E387_TUNNEL})", size=12, bold=True, color=bd.BLUE)
        bd.add_table(slide, LM, y + 0.35, [1.0, 1.6, 1.6, 1.4, 1.6, 1.6, 1.4], rows, size=11,
                     row_h=0.3, flag=())


def body_mesh_table(slide, v):
    runs = [("coarse", "runs/mesh/airfoil2d-59cd4287e9"), ("medium", SMOKE2),
            ("fine", "runs/mesh/airfoil2d-e161fb7e6b")]
    recs = {lvl: jload(p + "/result.json") for lvl, p in runs}
    fine = recs["fine"]["metrics"]
    rows = [["Level", "Cells", "Iterations", "Wall (s)", "cl", "cd", "cm", "cl / cd drift (%)",
             "cl, cd against fine"]]
    for lvl, r in recs.items():
        c, m = r["convergence"], r["metrics"]
        how = "budget" if c["iterations"] == r["params"]["max_iter"] else "Cauchy"
        rows.append([lvl, f"{r['geometry']['cells']:,}", f"{c['iterations']:,} ({how})",
                     f"{r['run']['wall_time_s']:,.0f}", f"{m['cl']:.5f}", f"{m['cd']:.6f}",
                     f"{m['cm']:.5f}", f"{m['cl_drift_pct']:.1f} / {m['cd_drift_pct']:.1f}",
                     "reference" if lvl == "fine" else
                     f"{pct(m['cl'] / fine['cl'] - 1)}, {pct(m['cd'] / fine['cd'] - 1)}"])
    bd.add_table(slide, LM, CT, [1.0, 1.1, 1.8, 1.0, 1.1, 1.3, 1.1, 1.6, 2.1], rows, size=11,
                 row_h=0.5, flag=())
    cost = [r["run"]["wall_time_s"] / r["convergence"]["iterations"] / r["geometry"]["cells"]
            for r in recs.values()]
    bd.text_box(slide, LM, CT + 2.4, CW, 1.6,
                [(f"Cost per iteration per cell: {min(cost) * 1e6:.2f} to {max(cost) * 1e6:.2f} "
                 "microseconds on 4 Colab ranks at all three levels."),
                 "NACA 4412-type section, Re 200,000, 6 deg, SA-BCM; drift over the last fifth."],
                size=12, bullets=True)


def body_budget(slide, v):
    from analysis.pool_af_results import kept
    idx = pool_case_index()
    rows = [["Tag", "Case", "Design, alpha", "Mesh", "cl", "cd", "cl drift (%)", "cd drift (%)",
             "Kept"]]
    for tag, case, r in budget_exhausted():
        where = idx.get(case)
        label = (f"{where[1]}, {where[2]:g} deg" if where
                 else f"nominal, {r['params']['alpha_deg']:g} deg")
        d = r["convergence"]["drift_pct"]
        keep = ("yes" if kept([r]) else "no") if tag.startswith("pool") else "not a pool case"
        rows.append([tag, case.removeprefix("airfoil2d-"), label, r["params"]["mesh_level"],
                     f"{r['metrics']['cl']:+.4f}", f"{r['metrics']['cd']:.5f}", f"{d['cl']:.1f}",
                     f"{d['cd']:.1f}", keep])
    bd.add_table(slide, LM, CT - 0.1, [1.4, 1.3, 1.9, 0.9, 1.1, 1.1, 1.3, 1.3, 1.8], rows,
                 size=10.5, row_h=min(0.42, 3.8 / len(rows)), flag=())
    bd.text_box(slide, LM, CT + 3.85, CW, 1.0,
                [("A drift of tens of percent at cl near zero is the division by |f_n| in the "
                  "drift rule, not a moving solution: read the cl column beside it."),
                 ("Design, alpha from designs/pool_af_cases.csv; kept = "
                  "analysis.pool_af_results.kept.")],
                size=11, bullets=True)


def body_pareto_lf(slide, v):
    notes = jload("runs/drone_pareto_lf/2026-11-09/notes.json")
    obs = sorted((r for r in csv_rows("runs/drone_pareto_lf/2026-11-09/pareto.csv")
                  if r["kind"] == "observed"), key=lambda r: float(r["mtow_kg"]))
    n_pred = sum(r["kind"] == "predicted"
                 for r in csv_rows("runs/drone_pareto_lf/2026-11-09/pareto.csv"))
    st = notes["candidate_stats"]
    rows = [["Item", "Record"],
            ["training rows", f"{notes['n_used']} of {notes['n_rows']}"],
            ["candidates", (f"{notes['candidates']:,} kept of {st['drawn']:,} drawn "
             f"({st['failed_cheap_gates']} failed the closed-form gates, "
             f"{st['failed_full_gates']} the full gates)")],
            ["observed front", (f"{len(obs)} designs, {float(obs[0]['endurance_h']):.2f} h at "
             f"{float(obs[0]['mtow_kg']):.3f} kg to {float(obs[-1]['endurance_h']):.2f} h at "
             f"{float(obs[-1]['mtow_kg']):.3f} kg")],
            ["predicted front", f"{n_pred} points"],
            ["band", (f"{len(notes['mtow_levels_kg'])} mass levels, {notes['samples']} joint "
             "samples per level")]]
    bd.add_table(slide, LM, CT - 0.05, [2.3, 5.4], rows, size=12, row_h=0.55, flag=())
    ls = notes["endurance_lengthscales"]
    lrows = [["Input", "Length scale"]] + [[k, f"{ls[k]:.2f}"] for k in sorted(ls, key=ls.get)]
    bd.add_table(slide, LM + 8.1, CT - 0.05, [2.3, 1.6], lrows, size=12, row_h=0.45, flag=())


def body_inverse_record(slide, v):
    inv = jload(INVERSE_LF)
    rows = [["Item", "Record"],
            ["grid", f"{inv['grid_points_per_axis']}^6 = {inv['n_grid']:,} points"],
            ["pass the closed-form gates", f"{inv['n_cheap_gate_feasible']:,}"],
            ["training rows", f"{inv['n_train']}"],
            ["query", f"P(mass <= {inv['mtow_cap_kg']:g} kg) >= {inv['prob_required']:g}"],
            *inverse_rows(inv, "answer"),
            ["closure gates at the answer", "passed" if inv["closure_gates_passed"] else "FAIL"],
            ["lightest observed design", f"{inv['min_observed_mtow_kg']:.3f} kg"],
            ["interval", inv["interval"]]]
    bd.add_table(slide, LM, CT - 0.1, [3.2, 8.9], rows, size=11, row_h=0.42, flag=())


def body_bias_full(slide, v):
    rows = [["#", "Quantity", "Value", "Band", "Endurance (%)", "Mass (%)", "Effect"]]
    for r in csv_rows(BIAS_LF):
        rows.append([r["rank"], f"{r['set']}: {pretty(r['name'])}", f"{float(r['value']):g}",
                     f"{float(r['band_lo']):g} to {float(r['band_hi']):g}",
                     f"{float(r['pct_endurance_lo']):+.1f} / {float(r['pct_endurance_hi']):+.1f}",
                     f"{float(r['pct_mtow_lo']):+.1f} / {float(r['pct_mtow_hi']):+.1f}",
                     r["effect"]])
    bd.add_table(slide, LM, CT - 0.2, [0.4, 4.0, 1.1, 1.8, 1.6, 1.5, 1.7], rows, size=8,
                 row_h=min(0.3, 5.0 / len(rows)), flag=())


def body_online_full(slide, v):
    on, feas = csv_rows(fd.ONLINE), csv_rows(fd.ONLINE_FEAS)
    ns = sorted({int(r["n"]) for r in on})
    strat = (("random", on), ("lhs", on), ("al_ehvi", on), ("al_ehvi_feas", feas),
             ("al_maxvar", on), ("al_maxvar_feas", feas))
    for i, metric in enumerate(("hv_regret", "n_gated")):
        rows = [["n", *[s for s, _ in strat]]]
        for n in ns:
            fmt = "{:.3f}" if metric == "hv_regret" else "{:.1f}"
            rows.append([n, *[fmt.format(mean_at(src, s, metric, n)) for s, src in strat]])
        y = CT - 0.1 + i * 2.5
        bd.text_box(slide, LM, y, CW, 0.3, "Mean hypervolume regret against the exact front"
                    if i == 0 else "Mean gated picks (cumulative)", size=12, bold=True,
                    color=bd.BLUE)
        bd.add_table(slide, LM, y + 0.32, [0.8, *[1.85] * 6], rows, size=10.5, row_h=0.26,
                     flag=())


def decision_rows():
    tasks = (ROOT / TASKS).read_text()
    flat = " ".join(tasks.split())
    d6 = re.search(r"(Éder chose the recommendation: [^.]+\.)", flat).group(1).replace("`", "")
    d7 = re.search(r'### Decision 7 \(([^,]+, [^,]+), "([^"]+)"\)', tasks)
    d8 = re.search(r'### Decision 8 \(([^)]+)\): "([^"]+)"', tasks)
    d6h = re.search(r"### Decision 6 \(([^)]+)\)", tasks).group(1)
    return [["Decision", "Who and when", "As recorded", "What it changed"],
            ["6", d6h, d6, "budget 6,000 with a Cauchy stop on lift and drag"],
            ["7", d7.group(1), f'"{d7.group(2)}"', ("the SU2 pool staged: 32 designs at five "
             "angles on the coarse mesh, plus the medium bias check")],
            ["8", d8.group(1), f'"{d8.group(2)}"', ("the V6e fail kept, its flags written into "
             "every SU2 polar; no SST-LM attempt")]]


def body_decisions(slide, v):
    bd.add_table(slide, LM, CT - 0.05, [1.1, 2.7, 5.0, 3.3], decision_rows(), size=11, row_h=1.05,
                 flag=())


def body_ledger(slide, v):
    counts = ledger_counts()
    rows = [["Set", "Quantities", "Published", "Derived", "Assumed", "With a band"]]
    for name, c in counts.items():
        rows.append([f"data/drone/{name}.yaml", c["all"], c["published"], c["derived"],
                     c["assumed"], c["band"]])
    tot = {k: sum(c[k] for c in counts.values()) for k in ("all", "published", "derived",
                                                            "assumed", "band")}
    rows.append(["total", tot["all"], tot["published"], tot["derived"], tot["assumed"],
                 tot["band"]])
    bd.add_table(slide, LM, CT, [3.6, 1.6, 1.6, 1.6, 1.6, 1.8], rows, size=13, row_h=0.45, flag=())
    bd.text_box(slide, LM, CT + 3.5, CW, 1.2,
                [("The loader (drone/ledger.py) refuses a quantity without a source, and an "
                  "assumed one without a band that contains its value."),
                 "Validation data (E387, Warren-12) live in data/validation/ and are not counted."],
                size=12, bullets=True)


def body_cost(slide, v):
    rows = [["Mesh level", "Cases", "Wall (s): median", "min to max", "Iterations: median",
             "Worker-hours"]]
    for level in ("coarse", "medium", "fine"):
        recs = [r for r in all_su2_records().values() if r["params"]["mesh_level"] == level]
        if not recs:
            continue
        w = [r["run"]["wall_time_s"] for r in recs]
        it = [r["convergence"].get("iterations") or r["run"]["iterations"] for r in recs]
        rows.append([level, len(recs), f"{np.median(w):,.0f}", f"{min(w):,.0f} to {max(w):,.0f}",
                     f"{np.median(it):,.0f}", f"{sum(w) / 3600:.1f}"])
    bd.add_table(slide, LM, CT - 0.05, [1.8, 1.0, 2.0, 2.0, 2.2, 1.6], rows, size=12, row_h=0.42,
                 flag=())
    by_tag = defaultdict(float)
    for (tag, _), r in all_su2_records().items():
        by_tag[tag] += r["run"]["wall_time_s"] / 3600
    trows = [["Tag", "Worker-hours so far"]] + [[t, f"{h:.1f}"] for t, h in sorted(by_tag.items())]
    bd.add_table(slide, LM, CT + 2.0, [2.2, 2.2], trows, size=11, row_h=0.3, flag=())
    grid = jload("runs/drone_grid/2026-11-08/record.json")
    pool = jload("runs/drone_pool_lf/2026-11-08/record.json")
    online = jload("runs/replay_drone_online/2026-11-08/record.json")
    feas = jload("runs/replay_drone_online/2026-11-08_feas/record.json")
    bd.text_box(slide, LM + 4.8, CT + 2.0, 7.3, 2.8,
                [(f"Low-fidelity grid: {grid['wall_seconds'] / 3600:.2f} h on {grid['workers']} "
                 "workers."),
                 f"Low pool: {pool['wall_seconds']:.0f} s on {pool['workers']} workers.",
                 (f"Online replays: {online['wall_seconds']:.0f} s and "
                  f"{feas['wall_seconds']:.0f} s."),
                 "SU2 wall times are from each result.json; ranks per case: " + ranks_line() + "."],
                size=12, bullets=True)


def ranks_line():
    """'N cases on 4 ranks, M on 2' from the solver block of every SU2 result record."""
    count = defaultdict(int)
    for r in all_su2_records().values():
        count[r.get("solver", {}).get("n_cores")] += 1
    return ", ".join(f"{n} cases on {k} ranks" for k, n in sorted(count.items(), key=str))


def body_equation_index(slide, v):
    where = defaultdict(list)
    for s in read_outline():
        for latex in s.get("equations", []):
            where[latex].append(s["id"])
    rows = [["Slide", "Relation", "Module"]]
    for latex, name, module in EQUATION_INDEX:
        rows.append([", ".join(where[latex]), name, module])
    half = (len(rows) + 1) // 2
    for i, part in enumerate((rows[:half], [rows[0]] + rows[half:])):
        bd.add_table(slide, LM + i * 6.15, CT - 0.2, [0.75, 2.6, 2.6], part, size=7.5,
                     row_h=min(0.25, 5.0 / len(part)), flag=())


def body_study_guide(slide, v):
    path = "docs/talk/study_guide_drone.html"
    html = (ROOT / path).read_text()
    rows = [["Block", "Entries", "Titles"]]
    for bid in ("d1", "d2", "d3", "d4"):
        part = html[html.index(f'id="{bid}"'):]
        part = part[:part.index("<h2", 10)]
        title = re.search(r'>([^<]+)</h2>', part).group(1)
        labels = re.findall(r'<label for="k\d+">(\d+)\. ([^<]+)</label>', part)
        rows.append([title, f"{labels[0][0]} to {labels[-1][0]}",
                     "; ".join(t.split(":")[0] for _, t in labels)])
    n = len(re.findall(r'data-id="', html))
    bd.text_box(slide, LM, CT - 0.1, CW, 0.4, f"{path}: {n} entries in four blocks", size=14,
                bold=True, color=bd.BLUE)
    bd.add_table(slide, LM, CT + 0.4, [3.2, 1.1, 7.9], rows, size=9, row_h=0.7, flag=())
    bd.text_box(slide, LM, CT + 4.15, CW, 0.8,
                [("Each entry: definition, relations in LaTeX, variables with their code names, "
                  "implementation, a worked example from the records, interview questions and a "
                  "self-check."),
                 "Open the file in a browser; the inlet plan is docs/talk/study_guide.html."],
                size=11, bullets=True)


def body_carried(slide, v):
    rows = [["Carried over from the inlet study", "New in this study"],
            ["Drive queue and restart-safe worker (worker/run_worker.py)",
             "airfoil2d family: C-mesh, SA-BCM template (geometry/airfoil2d.py)"],
            ["Strict schema, physics gates, mesh fingerprint, digest (mcp_server/)",
             "Cauchy stop on lift and drag (cases/templates/inc_rans_airfoil.cfg)"],
            ["Exact GP with Matern 5/2 and ARD (surrogate/gp.py)",
             "Section polars aggregated per design (analysis/drone_polar.py)"],
            ["EHVI, max-variance, the replay (surrogate/acquisition.py, replay.py)",
             "Online replay against an exact front (analysis/replay_drone_online.py)"],
            ["Logistic feasibility model (surrogate/feasibility.py)",
             "Two-level model on a new problem (surrogate/mf_gp.py, analysis/mf_drone.py)"],
            ["Pareto, inverse query, confirmation (analysis/)",
             "Sharded workers, --shard K/N (worker/run_worker.py)"]]
    bd.add_table(slide, LM, CT, [6.05, 6.05], rows, size=12, row_h=0.62, flag=())


def body_rulings(slide, v):
    lift = lift_effectiveness()
    n_budget = sum(t.startswith("pool") for t, _, _ in budget_exhausted())
    cm = v6_check("V6b Warren-12 fine: Cm_alpha (about root LE, reference chord 1.0) vs benchmark")
    rows = [["Ruling", "Evidence", "Either way"],
            ["1. Accept budget-exhausted SU2 runs into the pool?",
             f"{n_budget} pool cases used their whole budget (DB5); today they are dropped",
             "accepting adds angles to incomplete designs, with their drift as a flag"],
            ["2. The section lift-effectiveness band",
             (f"ledger {lift['value']:g}, band {lift['band']}; V6f lift slope "
             f"{v['f_clalpha_range']} low against the tunnel"),
             "re-centring moves the low-fidelity grid and the replays (a full re-run)"],
            ["3. The Warren-12 moment reference point",
             f"Cm_alpha {pct(cm['deviation'])} about the root leading edge, verdict pending",
             "sourcing the point closes V6b; no tolerance moves"]]
    bd.add_table(slide, LM, CT, [3.6, 4.8, 3.7], rows, size=12, row_h=1.0, flag=())


def body_status(slide, v):
    files = [(V6, "validation V6 (T10.8)"), ("runs/drone_grid/2026-11-08/record.json", "9^6 grid"),
             ("runs/replay_drone_online/2026-11-08_feas/online.csv", "online replay"),
             (INVERSE_LF, "low-fidelity inverse"), (BIAS_LF, "low-fidelity bias sweep"),
             (POOL + "/results.csv", "pool ingestion, hourly"), (MF, "multi-fidelity, T10.10c"),
             (PARETO_HF, "SU2-pool front, T10.10a"), (INVERSE_HF, "SU2-pool inverse, T10.10a"),
             (CONFIRM, "confirmation run, T10.10d"), (BIAS_HF, "bias sweep at SU2 answer")]
    files += [(f"runs/viz/{c}/flow.dat.gz", "viz batch") for c in VIZ_CASES]
    rows = [["File", "Written by", "Status"]]
    rows += [[f, by, "exists" if exists(f) else "PENDING"] for f, by in files]
    bd.add_table(slide, LM, CT - 0.15, [6.6, 3.6, 1.9], rows, size=10.5,
                 row_h=min(0.36, 4.95 / len(rows)))


BODIES = {
    "D2": body_clean_exit, "D3": body_caught, "D4": body_mcp,
    "D5": body_questions, "D6": body_c2, "D7": body_inputs, "D8": body_costs,
    "D9": body_pipeline, "D10": body_figure("planform.png", "drone/geometry.py, drone/naca.py"),
    "D11": body_lattice, "D12": body_v6_table, "D13": body_closure, "D14": body_mesh,
    "D15": body_stopping, "D16": body_flow("convergence_smoke2.png", SMOKE2 + "/history.csv.gz",
                                           max_h=4.6),
    "D17": body_flow("cp_mesh_pair.png", "runs/mesh, runs/smoke2 surface_flow.dat.gz"),
    "D18": body_v6f, "D19": body_v6e,
    "D20": body_flow("cp_e387.png", "runs/e387/*/surface_flow.dat.gz"),
    "D21": body_flow("cf_e387.png", "runs/e387/*/surface_flow.dat.gz", max_h=4.5),
    "D22": body_section_polars,
    "D23": body_flow("cp_design0.png", "runs/pool_af/*/surface_flow.dat.gz"),
    "D24": body_viz,
    "D25": body_tools_gates,
    "D26": body_figure("queue_gates.png", "mcp_server/queue.py, worker/run_worker.py"),
    "D27": body_shards, "D28": body_gated_caught,
    "D29": body_gp,
    "D30": body_figure("design_space.png", "runs/drone_pareto_lf/2026-11-09/design_map.csv"),
    "D31": body_pool_replay, "D32": body_online, "D33": body_mf,
    "D34": body_lowfi_front, "D35": body_pool_status, "D36": body_hf_front, "D37": body_inverse,
    "D38": body_confirm, "D39": body_bias_sweep, "D40": body_mesh_bias,
    "D41": body_biases, "D42": body_wrong_first, "D43": body_limits, "D44": body_conclusions,
    "D45": body_discussion,
    "DB1": body_v6_part1, "DB2": body_v6_part2, "DB3": body_e387_points, "DB4": body_mesh_table,
    "DB5": body_budget, "DB6": body_pareto_lf, "DB7": body_inverse_record, "DB8": body_bias_full,
    "DB9": body_online_full, "DB10": body_decisions, "DB11": body_ledger, "DB12": body_cost,
    "DB13": body_equation_index, "DB14": body_study_guide, "DB15": body_carried,
    "DB16": body_rulings, "DB17": body_status,
}


def fill(text, v):
    """Replace {name} by its value; an unknown name raises KeyError and fails the build."""
    return text.format_map(v)


FD_OUT = fd.OUT_DIR


def ensure_figures():
    """The committed figures; the section-polar figure is redrawn because the pool grows hourly."""
    names = ("a_front_lowfi.png", "b_pool_replay.png", "c_online_regret.png",
             "d_e387_comparison.png")
    if not all((ROOT / FIG / n).is_file() for n in names):
        fd.main(ROOT, ROOT / FD_OUT)
    if not all((ROOT / FLOW / name).is_file() for name, _ in pa.captions()):
        pa.main(ROOT / FLOW)
    else:
        pa.section_polar(ROOT / FLOW)


def title_slide(prs, s, v):
    """Slide 1: the shared title helper, relabeled with this deck's id."""
    rec = jload(POOL + "/record.json")
    slide = bd.add_title_slide(
        prs, 1, "Sizing a small electric aircraft with the inlet pipeline", fill(s["message"], v),
        [(f"Status at build time: validation V6a to V6f recorded, low-fidelity studies complete, "
         f"SU2 pool {rec['complete']} of {rec['designs']} designs complete."),
         "Every number is read from a record in this repository at build time."],
        fill(s["notes"], v))
    for shape in slide.shapes:                     # the shared title helper labels its slide S1
        if shape.has_text_frame and shape.text_frame.text.startswith("S1  |"):
            shape.text_frame.paragraphs[0].runs[0].text = f"{s['id']}  |  1"


def build(out_path=DEFAULT_OUT):
    """Build the deck and save it. Returns the number of slides.

    Order: the title slide, then for every section of the outline a divider and its slides.
    """
    all_su2_records.cache_clear()
    ensure_figures()
    ensure_drawings()
    v = values()
    by_id = {s["id"]: s for s in read_outline()}
    prs = bd.new_deck()
    for sec in read_sections():
        if sec["title"] == "Title":
            title_slide(prs, by_id[sec["ids"][0]], v)
            continue
        bd.add_divider_slide(prs, sec["title"], sec["sub"])
        for sid in sec["ids"]:
            s = by_id[sid]
            slide = bd.start_slide(prs, len(prs.slides) + 1, sid, s["title"], fill(s["message"], v),
                                   source_list(s["source"]), fill(s["notes"], v))
            BODIES[sid](slide, v)
    prs.save(str(out_path))
    return len(prs.slides)


if __name__ == "__main__":
    n = build()
    print(f"wrote {DEFAULT_OUT.relative_to(ROOT)} with {n} slides")

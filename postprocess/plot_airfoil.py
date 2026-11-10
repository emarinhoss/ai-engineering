"""Pictures of the SU2 airfoil2d cases, drawn from the committed run folders only.

Usage:
    python -m postprocess.plot_airfoil              # every figure, into docs/validation/figures/task10/flow/

Every plotted value is read from a file: surface_flow.dat.gz (SU2 SURFACE_TECPLOT_ASCII) and
result.json of a case, history.csv.gz of one case, runs/pool_af/2026-11-09/results.csv, and
data/validation/e387_uiuc.yaml. The only computed curve is the low-fidelity closed form the model
itself uses (drone.section.low_fidelity). A figure whose input is missing is skipped and named.

Node order of surface_flow.dat (checked on the committed files): one closed loop that starts at
the trailing edge (x = 1, y = 0), runs along one surface to the leading edge (the node of least
x), and returns along the other surface. Whether the first half is the upper or the lower surface
is not assumed: read_surface compares the two halves at mid chord and calls the one with the
larger y the upper surface. The sign of y alone cannot split them, because on a cambered section
both neighbours of the trailing-edge node have y above zero.
"""
import csv
import gzip
import json
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from postprocess import history
from postprocess.tecplot import read_tecplot_ascii

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path("docs/validation/figures/task10/flow")
POOL_RESULTS = "runs/pool_af/2026-11-09/results.csv"
E387_TUNNEL = "data/validation/e387_uiuc.yaml"
SMOKE2 = "runs/smoke2/airfoil2d-51d551f2cc"
E387_CASES = [("e387", c) for c in ("498b156761", "a1edd0dc9d", "7de8a51345", "f575890d77", "69bc668e06")]
DESIGN0_CASES = [("pool_af", c) for c in ("fd72a75766", "7eb76bdca4", "e91b498c69", "f2c50f8e25", "2862718ac9")]
MESH_CASES = [("coarse", "mesh", "59cd4287e9"), ("medium", "smoke2", "51d551f2cc"),
              ("fine", "mesh", "e161fb7e6b")]
CD_MAX = 0.06                      # cd axis limit of the section polars; stalled points fall outside
COLORS = ["#0072B2", "#009E73", "#E69F00", "#D55E00", "#CC79A7"]


# ---- reading ----------------------------------------------------------------------------------
def _plain_path(path):
    """A readable path for the Tecplot reader: a .gz file is unpacked to a temporary file."""
    path = Path(path)
    if path.suffix != ".gz":
        return path
    tmp = Path(tempfile.mkdtemp()) / path.stem
    with gzip.open(path) as f:
        tmp.write_bytes(f.read())
    return tmp


def read_surface(path):
    """{variable: array} of a surface file, plus "upper" and "lower": node indices from the
    leading edge to the trailing edge. The leading edge is the node of least x; the half with
    the larger y at x = 0.5 is the upper surface (see the module docstring)."""
    data = read_tecplot_ascii(_plain_path(path))["data"]
    s = {name: np.asarray(v, dtype=float) for name, v in data.items()}
    i_le = int(np.argmin(s["x"]))
    first = np.arange(i_le, -1, -1)                     # leading edge back to the first node
    second = np.arange(i_le, len(s["x"]))               # leading edge on to the last node
    y_first = np.interp(0.5, s["x"][first], s["y"][first])
    y_second = np.interp(0.5, s["x"][second], s["y"][second])
    s["upper"], s["lower"] = (first, second) if y_first > y_second else (second, first)
    return s


def side(surface, which, name):
    """(x, values) of one variable along the "upper" or "lower" surface, leading to trailing edge."""
    idx = surface[which]
    return surface["x"][idx], surface[name][idx]


def load_case(tag, case):
    """(result.json as a dict, surface dict) of runs/<tag>/airfoil2d-<case>."""
    folder = ROOT / "runs" / tag / f"airfoil2d-{case}"
    return (json.loads((folder / "result.json").read_text()),
            read_surface(folder / "surface_flow.dat.gz"))


def _save(fig, out_dir, name):
    path = Path(out_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    return path


# ---- Cp panels --------------------------------------------------------------------------------
def draw_cp(ax, surface, color, label=None, lw=1.2):
    """Upper surface solid, lower surface dashed, against x/c."""
    x, cp = side(surface, "upper", "Pressure_Coefficient")
    ax.plot(x, cp, color=color, lw=lw, label=label)
    x, cp = side(surface, "lower", "Pressure_Coefficient")
    ax.plot(x, cp, color=color, lw=lw, ls="--")


def panel_title(result):
    p, m = result["params"], result["metrics"]
    return (f"alpha {p['alpha_deg']:g} deg: cl {m['cl']:.3f}, cd {m['cd']:.4f}\n"
            f"{result['convergence']['status']}, {result['convergence']['iterations']} iterations")


def cp_panels(cases, out_png_name, suptitle, out_dir=OUT_DIR):
    """One Cp panel per case (axis inverted, suction up), cases = [(tag, case id)]."""
    loaded = sorted((load_case(t, c) for t, c in cases), key=lambda rs: rs[0]["params"]["alpha_deg"])
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.6), sharex=True, sharey=True,
                             constrained_layout=True)
    for ax, (result, surf), color in zip(axes.flat, loaded, COLORS):
        draw_cp(ax, surf, color)
        ax.set_title(panel_title(result), fontsize=9)
        ax.axhline(0, color="#999999", lw=0.6)
        ax.grid(alpha=0.25)
    for ax in axes.flat[len(loaded):]:
        ax.axis("off")
    axes[0, 0].invert_yaxis()
    for ax in axes[1]:
        ax.set_xlabel("x/c")
    for ax in axes[:, 0]:
        ax.set_ylabel("Cp")
    axes.flat[len(loaded)].text(0.02, 0.6, "solid: upper surface\ndashed: lower surface\n"
                                "Cp as written by SU2", fontsize=10, transform=axes.flat[len(loaded)].transAxes)
    fig.suptitle(suptitle, fontsize=11)
    return _save(fig, out_dir, out_png_name)


def cp_mesh_pair(out_dir=OUT_DIR):
    """Coarse, medium and fine Cp of the nominal section (6 deg) with a leading-edge zoom."""
    fig, ax = plt.subplots(figsize=(10, 5.6), constrained_layout=True)
    zoom = ax.inset_axes([0.42, 0.38, 0.34, 0.5])
    for (level, tag, case), color in zip(MESH_CASES, COLORS):
        result, surf = load_case(tag, case)
        label = f"{level}: {result['geometry']['cells']:,} cells, cl {result['metrics']['cl']:.4f}"
        for a in (ax, zoom):
            draw_cp(a, surf, color, label if a is ax else None)
    zoom.set_xlim(0.0, 0.06)
    zoom.invert_yaxis()
    zoom.set_title("leading edge, x/c from 0 to 0.06", fontsize=8)
    zoom.tick_params(labelsize=7)
    ax.indicate_inset_zoom(zoom, edgecolor="#666666")
    ax.invert_yaxis()
    ax.set_xlabel("x/c")
    ax.set_ylabel("Cp")
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title("Cp of the nominal section (4 % camber, 12 % thick, Re 200,000, 6 deg) on three meshes; "
                 "solid upper, dashed lower", fontsize=10)
    return _save(fig, out_dir, "cp_mesh_pair.png")


# ---- skin friction ----------------------------------------------------------------------------
def skin_friction_panel(cases=E387_CASES, out_dir=OUT_DIR):
    """Cf_x against x/c on the upper and lower surface, one curve per angle. Cf_x is the x
    component of SU2's skin friction coefficient: negative means the wall shear points upstream."""
    loaded = sorted((load_case(t, c) for t, c in cases), key=lambda rs: rs[0]["params"]["alpha_deg"])
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True, constrained_layout=True)
    for ax, which in zip(axes, ("upper", "lower")):
        for (result, surf), color in zip(loaded, COLORS):
            x, cf = side(surf, which, "Skin_Friction_Coefficient_x")
            ax.plot(x, cf, color=color, lw=1.1, label=f"alpha {result['params']['alpha_deg']:g} deg")
        ax.axhline(0, color="#444444", lw=0.8)
        ax.set_title(f"{which} surface", fontsize=10)
        ax.set_xlabel("x/c")
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("Cf_x (SU2 Skin_Friction_Coefficient_x)")
    axes[0].set_ylim(-0.012, 0.03)
    axes[0].legend(fontsize=9)
    fig.suptitle("E387, Re 203,800: skin friction on the surface (medium mesh, laminar-turbulent model BCM)",
                 fontsize=11)
    return _save(fig, out_dir, "cf_e387.png")


def reversed_flow_extent(surface, x_min=0.1):
    """(x start, x end) of the longest run of negative Cf_x on the upper surface beyond x_min, or
    None. Reversed wall shear is the mark of a separated (here, laminar bubble) region."""
    x, cf = side(surface, "upper", "Skin_Friction_Coefficient_x")
    neg = (cf < 0) & (x > x_min)
    best, start = None, None
    for i, flag in enumerate(np.append(neg, False)):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if best is None or i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    return None if best is None else (float(x[best[0]]), float(x[best[1] - 1]))


# ---- section polars ---------------------------------------------------------------------------
def pool_designs():
    """[{row of results.csv, case ids kept}] for every design with status complete."""
    with open(ROOT / POOL_RESULTS, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "complete"]
    return [{"row": r, "kept": r["cases"].split(";")} for r in rows]


def design_cases(design):
    """All committed result.json of one design (kept or not): [(result dict, kept?)]."""
    row, out = design["row"], []
    for f in sorted((ROOT / "runs/pool_af").glob("airfoil2d-*/result.json")):
        r = json.loads(f.read_text())
        same = abs(r["params"].get("camber_pct", -1) - float(row["camber_pct"])) < 1e-6
        if same and abs(r["params"]["thickness_pct"] - float(row["thickness_pct"])) < 1e-6:
            out.append((r, r["case_id"] in design["kept"]))
    return sorted(out, key=lambda rk: (rk[0]["params"]["reynolds"], rk[0]["params"]["alpha_deg"]))


def low_fidelity_curves(camber, thickness, reynolds):
    """(alpha deg, cl, cd) of the model's closed-form section: cl = a (alpha - alpha_L0) up to
    cl_max, constant cd. The arrays are what drone.section.low_fidelity returns, evaluated."""
    from drone import ledger, section
    s = section.low_fidelity(camber, thickness, reynolds, ledger.load_all())
    alpha = np.linspace(-4.0, 16.0, 81)
    cl = np.minimum(s.cl_alpha_per_deg * (alpha - np.degrees(s.alpha_L0)), s.cl_max)
    return alpha, cl, np.asarray(s.cd_of_cl(cl))


def tunnel_run(reynolds=203800.0):
    runs = yaml.safe_load((ROOT / E387_TUNNEL).read_text())["polars"]
    return next(p for p in runs if float(p["reynolds"]) == reynolds)


def e387_section(reynolds=203800.0):
    """(su2 results of runs/e387 at this Re, camber %, thickness %) with the section measured
    from the E387 coordinate file, the way analysis.drone_validation.v6f does."""
    from geometry import airfoils
    x, y, _ = airfoils.load("e387")
    c = airfoils.camber_thickness(*airfoils.dense_loop(x, y, 801))
    res = [json.loads(f.read_text()) for f in sorted((ROOT / "runs/e387").glob("*/result.json"))]
    res = [r for r in res if r["params"]["reynolds"] == reynolds
           and r["params"].get("mesh_level") == "medium"]       # fine cases (decision 11) are V6e mesh only
    return res, 100.0 * c["max_camber"], 100.0 * c["max_thickness"]


def polar_columns():
    """[(title, su2 [(result, kept?)], camber, thickness, reynolds, tunnel run or None)]."""
    e387, camber, thick = e387_section()
    cols = [("E387, Re 203,800", [(r, True) for r in e387], camber, thick, 203800.0, tunnel_run())]
    for d in pool_designs():
        row = d["row"]
        re_su2 = design_cases(d)[0][0]["params"]["reynolds"]
        title = (f"pool design {row['index']}: model Re {float(row['re_cruise']):,.0f},\n"
                 f"SU2 run at Re {re_su2:,.0f}")
        cols.append((title, design_cases(d), float(row["camber_pct"]), float(row["thickness_pct"]),
                     float(row["re_cruise"]), None))
    return cols


def section_polar(out_dir=OUT_DIR):
    """cl(alpha) above and cd(cl) below for E387 and every complete pool design."""
    cols = polar_columns()
    fig, axes = plt.subplots(2, len(cols), figsize=(3.9 * len(cols), 6.6), constrained_layout=True)
    for j, (title, cases, camber, thick, re, tun) in enumerate(cols):
        top, bot = axes[0, j], axes[1, j]
        a, cl, cd = low_fidelity_curves(camber, thick, re)
        top.plot(a, cl, color="#888888", lw=1.4, label="low-fidelity closed form")
        bot.plot(cd, cl, color="#888888", lw=1.4)
        if tun is not None:
            top.plot(tun["alpha_deg"], tun["cl"], "k^-", ms=4, lw=0.8, label="UIUC tunnel")
            bot.plot(tun["cd"], tun["cl"], "k^-", ms=4, lw=0.8)
        for result, kept in cases:
            p, m = result["params"], result["metrics"]
            style = {"marker": "o", "color": "#D55E00", "ls": "none", "mfc": "#D55E00" if kept else "white"}
            top.plot(p["alpha_deg"], m["cl"], **style, label="SU2" if kept else "SU2, not kept")
            bot.plot(m["cd"], m["cl"], **style)
        top.set_title(title, fontsize=10)
        top.set_xlabel("alpha (deg)")
        off = sum(r["metrics"]["cd"] > CD_MAX for r, _ in cases)
        bot.set_xlim(0.0, CD_MAX)
        bot.set_xlabel("cd" + (f" ({off} stalled point{'s' * (off > 1)} off scale)" if off else ""))
        top.set_ylabel("cl")
        bot.set_ylabel("cl")
        top.grid(alpha=0.25)
        bot.grid(alpha=0.25)
        handles, labels = top.get_legend_handles_labels()
        uniq = dict(zip(labels, handles))
        top.legend(uniq.values(), uniq.keys(), fontsize=7, loc="upper left")
    fig.suptitle("Section polars: SU2 (medium or coarse mesh as run), the model's low-fidelity section, "
                 "and the tunnel where one exists", fontsize=11)
    return _save(fig, out_dir, "section_polars.png")


# ---- convergence ------------------------------------------------------------------------------
def convergence(case_dir=SMOKE2, out_dir=OUT_DIR):
    """rms[P], CL and CD against iteration for one case, with the stop iteration and the last-20 %
    window of postprocess.history.drift_pct marked."""
    folder = ROOT / case_dir
    cols = history.load(_plain_path(folder / "history.csv.gz"))
    result = json.loads((folder / "result.json").read_text())
    n = len(cols["rms[P]"])
    it = np.arange(1, n + 1)
    start = n - max(2, int(np.ceil(0.2 * n))) + 1
    fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True, constrained_layout=True)
    for ax, name in zip(axes, ("rms[P]", "CL", "CD")):
        ax.plot(it, cols[name], color="#0072B2", lw=0.8)
        ax.axvspan(start, n, color="#E69F00", alpha=0.25)
        ax.axvline(n, color="#D55E00", lw=1.2)
        ax.set_ylabel("log10 rms[P]" if name == "rms[P]" else name)
        ax.grid(alpha=0.25)
    for ax, name in zip(axes[1:], ("CL", "CD")):
        ax.set_ylim(*np.percentile(cols[name][500:], [0.5, 99.5]))
    drift = {k: history.drift_pct(cols[k]) for k in ("CL", "CD")}
    axes[1].set_title(f"last-20 % window (orange): CL drift {drift['CL']:.2f} %, CD drift {drift['CD']:.2f} %; "
                      f"red line: iteration {n} of {result['params']['max_iter']}, "
                      f"the run's end (status {result['convergence']['status']})", fontsize=9)
    axes[2].set_xlabel("iteration")
    fig.suptitle(f"SU2 history of {result['case_id']} (4 % camber, 12 % thick, Re 200,000, 6 deg, medium mesh)",
                 fontsize=11)
    return _save(fig, out_dir, "convergence_smoke2.png")


# ---- all figures and captions -----------------------------------------------------------------
def captions():
    """[(file name, caption)] for captions.md; every source file is named."""
    return [
        ("cp_e387.png",
         ("Cp against x/c for E387 at Re 203,800 and five angles, medium mesh. Sources: "
         "`runs/e387/airfoil2d-{498b156761,a1edd0dc9d,7de8a51345,f575890d77,69bc668e06}/"
         "surface_flow.dat.gz` and `result.json`.")),
        ("cp_design0.png",
         ("Cp against x/c for pool design 0 (coarse mesh, Re 121,945) at five angles; "
         "the 14 degree case is the stalled one. Sources: `runs/pool_af/airfoil2d-{fd72a75766,7eb76bdca4,"
         "e91b498c69,f2c50f8e25,2862718ac9}/surface_flow.dat.gz` and `result.json`.")),
        ("cp_mesh_pair.png",
         ("Cp of the nominal section (4 % camber, 12 % thick, Re 200,000, 6 deg) on the "
         "coarse, medium and fine meshes with a leading-edge zoom. Sources: `runs/mesh/airfoil2d-59cd4287e9/`, "
         "`runs/smoke2/airfoil2d-51d551f2cc/`, `runs/mesh/airfoil2d-e161fb7e6b/` (`surface_flow.dat.gz`, "
         "`result.json`).")),
        ("cf_e387.png",
         ("Skin friction Cf_x (SU2 Skin_Friction_Coefficient_x) on the E387 section at five "
         "angles. Sources: the five `runs/e387/*/surface_flow.dat.gz` listed for cp_e387.png.")),
        ("section_polars.png",
         ("cl(alpha) and cd(cl) of SU2, the model's low-fidelity section and, for E387, "
         "the UIUC tunnel. Sources: `runs/e387/*/result.json`, `runs/pool_af/*/result.json`, "
         f"`{POOL_RESULTS}`, `{E387_TUNNEL}`, and `drone/section.py` (low_fidelity).")),
        ("convergence_smoke2.png",
         ("rms[P], CL and CD against iteration for the medium-mesh nominal case. "
         "Sources: `runs/smoke2/airfoil2d-51d551f2cc/history.csv.gz` and `result.json`.")),
    ]


def write_captions(out_dir=OUT_DIR):
    lines = ["# Task 10 flow figures: captions", ""]
    lines += [f"- `{name}`: {text}" for name, text in captions()]
    lines += ["", "Pressure contours need a volume file; see `python -m postprocess.plot_flowfield airfoil`."]
    path = ROOT / out_dir / "captions.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main(out_dir=ROOT / OUT_DIR):
    made = [cp_panels(E387_CASES, "cp_e387.png", "E387, Re 203,800: pressure coefficient on the surface "
                      "(medium mesh)", out_dir),
            cp_panels(DESIGN0_CASES, "cp_design0.png", "Pool design 0, Re 121,945: pressure coefficient "
                      "on the surface (coarse mesh)", out_dir),
            cp_mesh_pair(out_dir), skin_friction_panel(out_dir=out_dir), section_polar(out_dir),
            convergence(out_dir=out_dir)]
    for path in made:
        print("wrote", path)
    print("wrote", write_captions(out_dir))


if __name__ == "__main__":
    main()

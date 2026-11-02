"""Build docs/talk/deck.pptx (38 slides: 24 talk, 6 backup, 8 section dividers) from committed files.

Run from the repository root with either of:
    python -m docs.talk.build_deck
    python docs/talk/build_deck.py

Rules this script follows (CLAUDE.md):
- Slide message (subtitle) and speaker notes are read verbatim from docs/talk/outline.md.
- Every number on a slide is copied from the file named in that slide's "sources" list.
- Every figure is a committed PNG (repo-relative path, printed in its caption) or a drawing made
  here from committed data (docs/talk/figures/*.png). No invented data.
- Anything not yet run says PENDING on the slide (nothing is pending as of 2026-11-02 16:00 UTC).
"""
import gzip
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:          # lets "python docs/talk/build_deck.py" import geometry
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from geometry.inlet import design_points
from postprocess.tecplot import read_su2_points, read_tecplot_ascii, surface_nodes_for_marker
from worker.make_case import make

OUTLINE = ROOT / "docs/talk/outline.md"
FIG_DIR = ROOT / "docs/talk/figures"
DEFAULT_OUT = ROOT / "docs/talk/deck.pptx"

# ---- design constants -------------------------------------------------------------------------
BLUE = RGBColor(0x1F, 0x3A, 0x5F)      # titles, table headers, divider background
ACCENT = RGBColor(0xD5, 0x5E, 0x00)    # the single accent: message line, FAIL, PENDING
GREY = RGBColor(0x66, 0x66, 0x66)      # captions and footers
TEXT = RGBColor(0x22, 0x22, 0x22)      # body text
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TINT = RGBColor(0xEA, 0xF0, 0xF7)      # light fill for boxes and banded table rows
BODY_FONT, TITLE_FONT = "Calibri", "Cambria"
LM, CW = 0.6, 12.13                    # left margin and content width, inches (slide is 13.333 x 7.5)
CT, CB = 1.95, 6.8                     # content top and bottom, inches

USED_FIGURES = []                      # repo-relative path of every PNG placed on a slide (for the test)


# ---- reading the outline ----------------------------------------------------------------------
def read_outline():
    """Return {slide id: {"message": ..., "notes": ...}} read from docs/talk/outline.md."""
    out, current = {}, None
    for line in OUTLINE.read_text(encoding="utf-8").splitlines():
        head = re.match(r"^### (S\d+|B\d+)\. ", line)
        if head:
            current = out.setdefault(head.group(1), {})
        elif current is not None and line.startswith("- **Message:** "):
            current["message"] = line[len("- **Message:** "):].strip()
        elif current is not None and line.startswith("- **Speaker notes:** "):
            current["notes"] = line[len("- **Speaker notes:** "):].strip()
    return out


# ---- small text helpers -----------------------------------------------------------------------
def style_run(run, size, color=TEXT, bold=False, font=BODY_FONT, italic=False):
    run.font.size, run.font.bold, run.font.italic = Pt(size), bold, italic
    run.font.name = font
    run.font.color.rgb = color


def text_box(slide, x, y, w, h, paragraphs, size=14, color=TEXT, bold=False, font=BODY_FONT,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, bullets=False, space_after=6):
    """Add a text box. `paragraphs` is a string or a list of strings (one paragraph each)."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    for i, text in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        style_run(p.add_run(), size, color, bold, font)
        p.runs[0].text = text
        if bullets:                      # real bullet with hanging indent
            ppr = p._p.get_or_add_pPr()
            ppr.set("marL", "228600")
            ppr.set("indent", "-228600")
            bu = etree.SubElement(ppr, "{http://schemas.openxmlformats.org/drawingml/2006/main}buChar")
            bu.set("char", "•")
    return box


def caption(slide, x, y, w, text, lines=2):
    """10 pt gray caption (figure path and record path)."""
    return text_box(slide, x, y, w, 0.17 * lines + 0.1, text, size=10, color=GREY, space_after=0)


def pending(slide, x, y, w, text):
    """Small visible PENDING marker (outline rule: a PENDING source is stated on the slide)."""
    return text_box(slide, x, y, w, 0.5, text, size=12, color=ACCENT, bold=True, space_after=0)


# ---- slide frame ------------------------------------------------------------------------------
def new_deck():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    return prs


def start_slide(prs, number, sid, title, message, sources, notes):
    """Title-only layout: title, message line under it, footer, speaker notes."""
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Inches(LM), Inches(0.3), Inches(CW), Inches(0.7)
    t.text_frame.word_wrap = True
    t.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    t.text_frame.margin_left = Inches(0.05)
    t.text_frame.text = title
    p = t.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    style_run(p.runs[0], 32, BLUE, True, TITLE_FONT)
    if message:
        text_box(slide, LM, 1.0, CW, 0.85, message, size=16, color=ACCENT, space_after=0)
    if sources:
        text_box(slide, LM, 6.9, 11.3, 0.5, "sources: " + ", ".join(sources), size=9, color=GREY,
                 anchor=MSO_ANCHOR.BOTTOM, space_after=0)
    text_box(slide, 11.9, 7.1, 0.85, 0.3, f"{sid}  |  {number}", size=9, color=GREY,
             align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.BOTTOM, space_after=0)
    if notes:
        slide.notes_slide.notes_text_frame.text = notes
    return slide


def add_divider_slide(prs, title, sub):
    """Section divider: dark blue background, white title."""
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BLUE
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Inches(1.0), Inches(2.9), Inches(11.3), Inches(1.0)
    t.text_frame.word_wrap = True
    t.text_frame.text = title
    p = t.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    style_run(p.runs[0], 40, WHITE, True, TITLE_FONT)
    text_box(slide, 1.0, 3.95, 11.3, 0.5, sub, size=18, color=WHITE)


def add_title_slide(prs, number, title, message, lines, notes):
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Inches(1.0), Inches(2.2), Inches(11.3), Inches(1.4)
    t.text_frame.word_wrap = True
    t.text_frame.text = title
    p = t.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    style_run(p.runs[0], 36, BLUE, True, TITLE_FONT)
    text_box(slide, 1.0, 3.8, 11.3, 0.6, message, size=18, color=ACCENT)
    text_box(slide, 1.0, 4.7, 11.3, 1.2, lines, size=14, color=GREY)
    text_box(slide, 11.9, 7.1, 0.85, 0.3, f"S1  |  {number}", size=9, color=GREY, align=PP_ALIGN.RIGHT,
             anchor=MSO_ANCHOR.BOTTOM)
    slide.notes_slide.notes_text_frame.text = notes
    return slide


# ---- figures ----------------------------------------------------------------------------------
def add_figure(slide, rel_path, x, y, max_w, max_h, crop=(0, 0, 0, 0)):
    """Place a committed PNG (repo-relative path), keep its aspect ratio, left-aligned at (x, y).
    crop = (left, top, right, bottom) fractions removed from the picture (used to show one panel of a
    multi-panel plot). Returns the picture's (width, height) in inches."""
    path = ROOT / rel_path
    from PIL import Image
    with Image.open(path) as im:
        w_px, h_px = im.size
    aspect = w_px * (1 - crop[0] - crop[2]) / (h_px * (1 - crop[1] - crop[3]))
    w, h = max_w, max_w / aspect
    if h > max_h:
        w, h = max_h * aspect, max_h
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    pic.crop_left, pic.crop_top, pic.crop_right, pic.crop_bottom = crop
    USED_FIGURES.append(rel_path)
    return w, h


def add_figure_with_caption(slide, rel_path, record, x, y, max_w, max_h, crop_note="", crop=(0, 0, 0, 0)):
    """Figure plus a 10 pt caption with the figure path and the source record path."""
    w, h = add_figure(slide, rel_path, x, y, max_w, max_h, crop)
    cap_w = max(w, 4.0)
    caption(slide, x, y + h + 0.04, cap_w, f"Figure: {rel_path}{crop_note}. Record: {record}.", lines=3)
    return w, h


# ---- tables -----------------------------------------------------------------------------------
def set_cell(cell, text, size, bold=False, color=TEXT, fill=None, align=PP_ALIGN.LEFT):
    cell.margin_left = cell.margin_right = Inches(0.06)
    cell.margin_top = cell.margin_bottom = Inches(0.03)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = cell.text_frame
    tf.word_wrap = True
    for i, line in enumerate(str(text).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        style_run(r, size, color, bold)
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill


def add_table(slide, x, y, widths, rows, size=12, row_h=0.4, flag=("FAIL", "PENDING", "not run")):
    """Table with a dark blue header. rows[0] is the header. A cell whose text starts with a word in
    `flag` (FAIL, PENDING, not run) is shown in the accent color, bold."""
    shape = slide.shapes.add_table(len(rows), len(widths), Inches(x), Inches(y), Inches(sum(widths)),
                                   Inches(row_h * len(rows)))
    table = shape.table
    table.horz_banding = False
    for c, wd in enumerate(widths):
        table.columns[c].width = Inches(wd)
    for r, row in enumerate(rows):
        table.rows[r].height = Inches(row_h)
        for c, text in enumerate(row):
            if r == 0:
                set_cell(table.cell(r, c), text, size, True, WHITE, BLUE)
            else:
                hot = any(str(text).startswith(f) for f in flag)
                set_cell(table.cell(r, c), text, size, hot, ACCENT if hot else TEXT,
                         TINT if r % 2 == 0 else WHITE)
    return table


# ---- diagram shapes ---------------------------------------------------------------------------
def box(slide, x, y, w, h, text, size=12, fill=TINT, line=BLUE, color=TEXT, bold=False):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = line
    shp.line.width = Pt(1.25)
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    for i, line_text in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = line_text
        style_run(r, size, color, bold)
    return shp


def arrow(slide, x1, y1, x2, y2, head=True, color=GREY, width=1.5):
    """Straight connector from (x1, y1) to (x2, y2) with an optional arrow head at the end."""
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    if head:
        ln = c.line._get_or_add_ln()
        tail = etree.SubElement(ln, "{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd")
        tail.set("type", "triangle")
    return c


def draw_pipeline(slide, labels, x0, y0, per_row, bw, bh, gx, gy, highlight=()):
    """Boxes left to right, `per_row` per row, joined by arrows; at a row end the arrow goes down,
    across and down into the first box of the next row. Returns the box centers (x, y)."""
    centers = []
    for i, label in enumerate(labels):
        r, c = divmod(i, per_row)
        x, y = x0 + c * (bw + gx), y0 + r * (bh + gy)
        box(slide, x, y, bw, bh, label, size=13, fill=TINT if i in highlight else WHITE)
        centers.append((x + bw / 2, y + bh / 2))
    for i in range(len(labels) - 1):
        (xa, ya), (xb, yb) = centers[i], centers[i + 1]
        if (i + 1) % per_row:                                  # same row: short arrow
            arrow(slide, xa + bw / 2, ya, xb - bw / 2, yb)
        else:                                                  # row end: down, across, down
            ymid = ya + bh / 2 + gy / 2
            arrow(slide, xa, ya + bh / 2, xa, ymid, head=False)
            arrow(slide, xa, ymid, xb, ymid, head=False)
            arrow(slide, xb, ymid, xb, yb - bh / 2)
    return centers


# ---- drawings made from committed data (matplotlib, saved under docs/talk/figures) ------------
plt.rcParams.update({"font.family": ["Carlito", "DejaVu Sans"], "font.size": 11})
BLUE_H, ACCENT_H, GREY_H = "#1F3A5F", "#D55E00", "#666666"


def draw_inlet_schematic(path):
    """Outline of the two-ramp inlet at theta1 = theta2 = 8 deg from geometry.inlet.design_points."""
    d = design_points(8.0, 8.0)
    O, C, P = np.zeros(2), d["C"], d["P"]
    Eb, Ec, G = d["E_body"], d["E_cowl"], d["G"]
    fig, ax = plt.subplots(figsize=(9.6, 3.4), dpi=200)
    ax.plot(*zip(O, C), color=BLUE_H, lw=3.5)                                 # ramp 1
    ax.plot(*zip(C, Eb), color=ACCENT_H, lw=3.5)                              # ramp 2
    ax.plot(*zip(P, Ec), color="#333333", lw=3.5)                             # cowl inner wall
    ax.plot(*zip(P, G), color="#333333", lw=3.5)                              # cowl outer wall
    ax.plot(*zip(Eb, Ec), color=BLUE_H, lw=2, ls="--")                        # throat plane
    ax.plot(*zip(O, P), color=GREY_H, lw=1, ls=":")                           # shock 1 (shock-on-lip rule)
    ax.plot(*zip(C, P), color=GREY_H, lw=1, ls=":")                           # shock 2
    ax.annotate("", xy=(-0.012, 0.004), xytext=(-0.06, 0.004), arrowprops=dict(arrowstyle="->", color=GREY_H, lw=1.5))
    ax.text(-0.036, 0.012, "freestream", color=GREY_H, ha="center", fontsize=12)
    ax.text(0.05, 0.027, "ramp 1", color=BLUE_H, ha="center", fontweight="bold", fontsize=13)
    ax.text(0.185, 0.012, "ramp 2: q_peak on ramp 2", color=ACCENT_H, ha="center", va="top", fontweight="bold", fontsize=13)
    ax.text(0.215, 0.108, "cowl", color="#333333", ha="center", fontweight="bold", fontsize=13)
    ax.text(0.085, 0.07, "ramp-1 and ramp-2 shocks\nmeet at the cowl lip", color=GREY_H, fontsize=11, ha="center")
    ax.annotate("throat plane:\nrecovery measured at throat\n(incl. terminal normal shock)",
                xy=((Eb[0] + Ec[0]) / 2, (Eb[1] + Ec[1]) / 2), xytext=(0.285, 0.075), color=BLUE_H,
                fontsize=12, va="center", arrowprops=dict(arrowstyle="->", color=BLUE_H))
    ax.set_xlim(-0.065, 0.42)
    ax.set_ylim(-0.012, 0.125)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def read_pool_design():
    rows = np.genfromtxt(ROOT / "designs/pool_sobol96.csv", delimiter=",", names=True)
    return rows["index"].astype(int), rows["theta1_deg"], rows["theta2_deg"]


def draw_design_box(path):
    """theta1-theta2 scatter of the 96 Sobol points; gate 4 corner shaded, excluded points marked."""
    idx, t1, t2 = read_pool_design()
    out = t1 + t2 > 24
    assert out.sum() == 4 and list(idx[out]) == [0, 40, 72, 80], "excluded points differ from the record"
    fig, ax = plt.subplots(figsize=(6.2, 4.5), dpi=200)
    ax.fill([10, 12, 12], [14, 14, 12], color=ACCENT_H, alpha=0.15, label="theta1 + theta2 > 24 deg (gate 4)")
    ax.plot([10, 12], [14, 12], color=ACCENT_H, lw=1)
    ax.scatter(t1[~out], t2[~out], s=22, color=BLUE_H, label=f"{(~out).sum()} run")
    ax.scatter(t1[out], t2[out], s=60, marker="x", color=ACCENT_H, lw=2, label=f"{out.sum()} excluded")
    ax.set_xlim(5, 12.2)
    ax.set_ylim(5, 14.2)
    ax.set_xlabel("theta1 (deg)")
    ax.set_ylabel("theta2 (deg)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8, frameon=False)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_box_diagnostics(path):
    """B5: points of the box diagnostics records and the four excluded pool points."""
    idx, t1, t2 = read_pool_design()
    out = t1 + t2 > 24
    conv = [(8, 8), (5, 14), (8, 14), (12, 12)]      # converged: inlet_grid_study_ef03 and inlet_box_diagnostics
    fig, ax = plt.subplots(figsize=(6.2, 4.5), dpi=200)
    ax.fill([10, 12, 12], [14, 14, 12], color=ACCENT_H, alpha=0.15)
    ax.plot([10, 12], [14, 12], color=ACCENT_H, lw=1)
    ax.scatter(*zip(*conv), s=70, color=BLUE_H, label="converged (8/8, 5/14, 8/14, 12/12)")
    ax.scatter([12], [14], s=90, marker="X", color=ACCENT_H, label="12/14 diverged (both meshes)")
    ax.scatter(t1[out], t2[out], s=60, facecolors="none", edgecolors=GREY_H, lw=1.5,
               label="4 excluded pool points (0, 40, 72, 80)")
    for a, b in conv + [(12, 14)]:
        ax.annotate(f"{a}/{b}", (a, b), textcoords="offset points", xytext=(0, 9), fontsize=9, ha="center")
    ax.set_xlim(4.0, 12.8)
    ax.set_ylim(4.5, 15.2)
    ax.set_xlabel("theta1 (deg)")
    ax.set_ylabel("theta2 (deg)")
    ax.legend(loc="lower right", fontsize=8, frameon=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def draw_wall_temperature(path):
    """B2: wall-node temperature along the laminar wedge near the leading edge (Tecplot surface file)."""
    src = ROOT / "runs/dev/2026-11-01_numerics/wedge-381c48d17f-tecplot/surface_flow.dat.gz"
    with gzip.open(src, "rt") as f:
        f.readline()                                           # TITLE line
        names = re.findall(r'"([^"]+)"', f.readline())         # VARIABLES line
        n_nodes = int(re.search(r"NODES=\s*(\d+)", f.readline()).group(1))   # ZONE line
        data = np.array([[float(v) for v in f.readline().split()] for _ in range(n_nodes)])
    x_mm, temp = data[:, names.index("x")] * 1e3, data[:, names.index("Temperature")]
    fig, ax = plt.subplots(figsize=(6.2, 4.0), dpi=200)
    keep = x_mm <= 60
    ax.plot(x_mm[keep], temp[keep], color=BLUE_H, marker="o", ms=3, lw=1.5, label="SU2 wall-node temperature")
    ax.axhline(300, color=ACCENT_H, lw=1.2, ls="--", label="imposed 300 K")
    ax.set_xlabel("x along the wedge (mm)")
    ax.set_ylabel("wall temperature (K)")
    ax.legend(fontsize=9)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---- drawings made from the meshes and surface files of committed runs -------------------------
P_INF = 1197.03                        # Pa, docs/specs/00_decisions.md section 1
GRID_RUNS = "runs/dev/2026-11-01_inlet_grid_study_ef03"
SA_RUNS = "runs/dev/2026-11-01_turbulence_sensitivity_SA"
BOX_RUNS = "runs/dev/2026-11-01_inlet_box_diagnostics"
CYL_SCHEMES = "runs/dev/2026-11-01_cylinder_v3_attempt2/schemes"
Q_FR_KW = 244.3                        # Fay-Riddell q_stag [kW/m^2], cylinder_v3_attempt2/README.md
EXCLUDE_M = 2e-3                       # q_peak ignores body nodes this close to the throat plane (00_decisions.md 3.2)


def read_json(path):
    return json.loads(Path(path).read_text())


def same_quality(got, want):
    """True if every entry of the committed mesh_quality.json `want` is in `got` to 1e-9 relative."""
    for key, w in want.items():
        pairs = [(got[key][k], w[k]) for k in w] if isinstance(w, dict) else [(got[key], w)]
        if not all(np.isclose(a, b, rtol=1e-9) for a, b in pairs):
            return False
    return True


def rebuild_inlet_case(run_rel, out_dir):
    """Rebuild mesh.su2, mesh_markers.json and geometry.json of a committed inlet run in out_dir.

    The run folders keep params.json and mesh_quality.json but not the mesh, so the mesh is made again
    from params.json by worker.make_case.make (the function that made it for the run). It must give the
    mesh_quality.json that the run recorded, otherwise this stops. The run's surface_flow.dat.gz is
    unzipped next to the mesh. Returns out_dir as a Path."""
    run, out = ROOT / run_rel, Path(out_dir)
    make(read_json(run / "params.json"), out)
    assert same_quality(read_json(out / "mesh_quality.json"), read_json(run / "mesh_quality.json")), \
        f"{run_rel}: the rebuilt mesh differs from the recorded mesh_quality.json"
    with gzip.open(run / "surface_flow.dat.gz", "rb") as src, open(out / "surface_flow.dat", "wb") as dst:
        shutil.copyfileobj(src, dst)
    return out


def body_profile(run_rel):
    """x, p [Pa], q [W/m^2] on the body marker of a committed inlet run, ordered from the leading edge.

    The body nodes are the ones of the mesh marker "body" (mesh_markers.json of the rebuilt mesh), found in
    surface_flow.dat by coordinates and ordered along the wall (postprocess.tecplot.surface_nodes_for_marker).
    q is SU2's Heat_Flux, positive into the wall (postprocess/surface.py). Also returns geometry.json."""
    with tempfile.TemporaryDirectory() as tmp:
        case = rebuild_inlet_case(run_rel, tmp)
        data = read_tecplot_ascii(case / "surface_flow.dat")
        rows = surface_nodes_for_marker(data, case / "mesh_markers.json", "body")
        geometry = read_json(case / "geometry.json")
    cols = data["data"]
    out = {"x": cols["x"][rows], "y": cols["y"][rows], "p": cols["Pressure"][rows], "q": cols["Heat_Flux"][rows]}
    assert np.all(np.diff(out["x"]) > 0), f"{run_rel}: body nodes are not ordered by x"
    out["p_max_file"] = float(cols["Pressure"].max())          # over every node of the surface file
    return out, geometry


def q_peak_on_ramp2(body, geometry):
    """(q_peak, x) as postprocess/metrics.py defines it: ramp 2 (x >= X1) without the nodes within 2 mm
    of the throat plane."""
    th = np.radians(geometry["theta_t_deg"])
    dist = np.abs((body["x"] - geometry["E_body"][0]) * np.cos(th) + (body["y"] - geometry["E_body"][1]) * np.sin(th))
    keep = (body["x"] >= geometry["X1"] - 1e-9) & (dist > EXCLUDE_M)
    k = int(np.argmax(np.where(keep, body["q"], -np.inf)))
    return float(body["q"][k]), float(body["x"][k])


def read_su2_quads(path):
    """Node ids of every quadrilateral of an SU2 mesh as an (n_elem, 4) array (lines: 9 n0 n1 n2 n3 id)."""
    lines = Path(path).read_text().splitlines()
    k = next(i for i, line in enumerate(lines) if line.startswith("NELEM="))
    n = int(lines[k].split("=")[1])
    rows = np.array([line.split() for line in lines[k + 1:k + 1 + n]], dtype=int)
    assert np.all(rows[:, 0] == 9), "only quadrilaterals (SU2 type 9) are drawn"
    return rows[:, 1:5]


def draw_mesh_8_8_medium(path):
    """B3: the 8/8 medium inlet mesh, whole domain and a zoom at the cowl lip and throat."""
    from matplotlib.collections import LineCollection
    run = f"{GRID_RUNS}/8_8_medium"
    with tempfile.TemporaryDirectory() as tmp:
        case = rebuild_inlet_case(run, tmp)
        pts, quads = read_su2_points(case / "mesh.su2"), read_su2_quads(case / "mesh.su2")
        geometry = read_json(case / "geometry.json")
    assert (len(quads), len(pts)) == (geometry["cells"], geometry["nodes"])
    edges = np.concatenate([quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)                    # each edge once
    segments = pts[edges]

    d = design_points(8.0, 8.0)
    fig = plt.figure(figsize=(9.6, 4.4), dpi=200)
    grid = fig.add_gridspec(2, 2, width_ratios=[1.45, 1.0], hspace=0.62, wspace=0.15)
    axes = [fig.add_subplot(grid[:, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, 1])]
    boxes = [(None, "whole domain"),
             ((0.185, 0.267, 0.045, 0.105), "cowl lip and throat (orange box)"),
             ((d["P"][0] - 0.0015, d["P"][0] + 0.0045, d["P"][1] - 0.0021, d["P"][1] + 0.0021), "cowl lip, 6 mm wide")]
    for ax, (box_xy, title) in zip(axes, boxes):
        ax.add_collection(LineCollection(segments, colors=BLUE_H, linewidths=0.12 if box_xy is None else 0.25))
        ax.plot(*zip(d["P"], d["E_cowl"]), color=ACCENT_H, lw=1.0)
        ax.plot(*zip(d["E_body"], d["E_cowl"]), color=ACCENT_H, lw=1.0, ls="--")      # throat plane
        if box_xy is None:
            ax.set_xlim(-0.035, 0.272)
            ax.set_ylim(-0.005, 0.205)
        else:
            ax.set_xlim(*box_xy[:2])
            ax.set_ylim(*box_xy[2:])
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=11)
        ax.tick_params(labelsize=9)
        ax.set_xlabel("x (m)", fontsize=10)
        ax.set_ylabel("y (m)", fontsize=10)
    z = boxes[1][0]
    axes[0].plot([z[0], z[1], z[1], z[0], z[0]], [z[2], z[2], z[3], z[3], z[2]], color=ACCENT_H, lw=1.0)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return len(quads), len(pts)


def draw_wall_laminar_vs_sa(path):
    """S8 and B1: wall pressure and wall heat flux along the body, laminar and SA, 8/8 medium."""
    runs = [("laminar", f"{GRID_RUNS}/8_8_medium", BLUE_H), ("Spalart-Allmaras", f"{SA_RUNS}/8_8_medium_SA", ACCENT_H)]
    fig, (ax_p, ax_q) = plt.subplots(2, 1, sharex=True, figsize=(7.0, 4.1), dpi=200,
                                     gridspec_kw={"height_ratios": [1, 1], "hspace": 0.1})
    edge_q, peaks = [], []
    for label, run, color in runs:
        body, geometry = body_profile(run)
        q_peak, x_peak = q_peak_on_ramp2(body, geometry)
        recorded = read_json(ROOT / run / "metrics.json")["q_peak_W_m2"]
        assert abs(q_peak - recorded) <= 0.01 * recorded, f"{run}: plotted q_peak {q_peak} vs recorded {recorded}"
        ax_p.plot(body["x"], body["p"] / P_INF, color=color, lw=1.6, label=label)
        ax_q.plot(body["x"], body["q"] / 1e3, color=color, lw=1.6)
        ax_q.plot([x_peak], [q_peak / 1e3], "o", color=color, ms=5)
        edge_q.append(body["q"][0] / 1e3)
        peaks.append((color, q_peak / 1e3, x_peak, label))
    X1, x_throat = geometry["X1"], geometry["E_body"][0]
    for ax in (ax_p, ax_q):
        ax.axvspan(X1, x_throat, color="#EAF0F7", zorder=0)
        ax.axvline(X1, color=GREY_H, lw=1.0, ls="--")
        ax.axvline(x_throat, color=GREY_H, lw=1.0, ls=":")
        ax.grid(alpha=0.25, lw=0.5)
    ax_p.set_ylabel("wall pressure p / p_inf")
    ax_q.set_ylabel("wall heat flux (kW/m2)")
    ax_q.set_xlabel("x along the body (m)")
    ax_p.set_xlim(0, x_throat + 0.004)
    ax_p.text(X1 + 0.003, 0.97, "heating objective window: ramp 2, x >= 0.1 m", transform=ax_p.get_xaxis_transform(),
              fontsize=8.5, color=GREY_H, va="top")
    ax_p.text(X1 - 0.003, 0.97, "corner\nx = 0.1 m", transform=ax_p.get_xaxis_transform(), fontsize=8.5, color=GREY_H,
              ha="right", va="top")
    ax_p.text(x_throat - 0.002, 0.03, "throat", transform=ax_p.get_xaxis_transform(), fontsize=8.5, color=GREY_H,
              ha="right", va="bottom")
    ax_p.legend(loc="upper left", fontsize=9, frameon=False)
    top = 1.5 * max(q for _, q, _, _ in peaks)
    ax_q.set_ylim(0, top)
    for (color, q, x, label), dy in zip(peaks, (-0.2 * top, 0.15 * top)):
        ax_q.annotate(f"{label} q_peak {q:.2f} kW/m2", (x, q), xytext=(0.125, q + dy), fontsize=8.5, color=color,
                      arrowprops=dict(arrowstyle="-", color=color, lw=0.8))
    ax_q.text(0.02, 0.97, f"off scale at x = 0:\n{edge_q[0]:.0f} (laminar), {edge_q[1]:.0f} (SA) kW/m2",
              transform=ax_q.transAxes, fontsize=8.5, color=GREY_H, va="top")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return peaks, edge_q


def draw_wall_12_14_diverged(path):
    """S10: body wall pressure of the diverged 12/14 medium case against the converged 12/12 medium case."""
    fig, ax = plt.subplots(figsize=(6.2, 4.2), dpi=200)
    info = {}
    for label, run, color in [("12/12 medium, converged", f"{BOX_RUNS}/12_12_medium", BLUE_H),
                              ("12/14 medium, diverged (exit with an error)", f"{GRID_RUNS}/12_14_medium", ACCENT_H)]:
        body, _ = body_profile(run)
        ax.semilogy(body["x"], body["p"] / P_INF, color=color, lw=1.6, label=label)
        info[run] = (float(body["p"].max()), body["p_max_file"])
    ax.axvline(0.1, color=GREY_H, lw=1.0, ls="--")
    ax.text(0.1 + 0.002, 0.5, "corner", transform=ax.get_xaxis_transform(), fontsize=9, color=GREY_H)
    ax.set_xlabel("x along the body (m)")
    ax.set_ylabel("wall pressure p / p_inf (log scale)")
    ax.set_xlim(0, 0.23)
    ax.set_ylim(1, 3e8)
    ax.grid(alpha=0.25, lw=0.5, which="both")
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.5), fontsize=9, frameon=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return info


SCHEME_STYLES = [("hllc", "HLLC", "#999999", "-"), ("ausmpup2", "AUSM+-up2", "#777777", (0, (4, 2))),
                 ("slau2", "SLAU2", "#555555", "-."), ("jst", "JST, first order", "#AAAAAA", ":"),
                 ("roe_firstorder", "Roe, first order", "#222222", (0, (10, 3)))]


def cylinder_wall_q(scheme):
    """(phi in degrees from the stagnation line, q in kW/m^2) at the wall nodes of one scheme's surface file.

    The cylinder has R = 10 mm and its center at the origin (geometry/cylinder.py); the freestream comes
    from -x, so phi = atan2(y, -x). The surface file holds only the wall marker (nodes at r = R)."""
    R = 0.010
    with tempfile.TemporaryDirectory() as tmp:
        with gzip.open(ROOT / CYL_SCHEMES / scheme / "surface_flow.dat.gz", "rb") as src, \
                open(Path(tmp) / "surface_flow.dat", "wb") as dst:
            shutil.copyfileobj(src, dst)
        cols = read_tecplot_ascii(Path(tmp) / "surface_flow.dat")["data"]
    assert np.allclose(np.hypot(cols["x"], cols["y"]), R, atol=1e-8), f"{scheme}: not all nodes are on the wall"
    phi = np.degrees(np.arctan2(cols["y"], -cols["x"]))
    order = np.argsort(phi)
    assert abs(phi[order][0]) < 1e-6 and abs(cols["x"][order][0] + R) < 1e-8, "no stagnation node at phi = 0"
    return phi[order], cols["Heat_Flux"][order] / 1e3


def draw_cylinder_schemes(path):
    """B4: stagnation-region heat flux against angle for the six convective schemes of attempt 2."""
    fig, ax = plt.subplots(figsize=(5.6, 3.9), dpi=200)
    for name, label, color, ls in SCHEME_STYLES:
        phi, q = cylinder_wall_q(name)
        keep = phi <= 90.0
        ax.plot(phi[keep], q[keep], color=color, ls=ls, lw=1.5, label=label)
    phi, q = cylinder_wall_q("roe_ef03_cfl5")
    keep = phi <= 90.0
    ax.plot(phi[keep], q[keep], color=ACCENT_H, lw=2.6, label="Roe, entropy fix 0.3, CFL max 5")
    ax.axhline(Q_FR_KW, color=BLUE_H, lw=1.3, ls="--", label=f"Fay-Riddell {Q_FR_KW} kW/m2")
    ax.set_xlim(0, 90)
    ax.set_xlabel("angle from the stagnation line, phi (deg)")
    ax.set_ylabel("wall heat flux q (kW/m2)")
    ax.grid(alpha=0.25, lw=0.5)
    ax.legend(fontsize=8.5, frameon=True, loc="upper right")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---- slide bodies (one function per slide that has drawn or composed content) -----------------
def body_s2(slide):
    path = "docs/talk/figures/inlet_schematic.png"
    draw_inlet_schematic(ROOT / path)
    w, h = add_figure(slide, path, LM, CT, 11.6, 3.35)
    text_box(slide, LM, CT + h + 0.1, CW, 1.0,
             ["Maximise: total pressure recovery at the throat plane, including the terminal normal shock.",
              "Minimise: peak wall heat flux on ramp 2, including the duct wall; not on the sharp leading edge."],
             size=14, bullets=True, space_after=4)
    caption(slide, LM, 6.3, CW,
            f"Figure: {path}, drawn by docs/talk/build_deck.py from geometry.inlet.design_points(8, 8), the geometry function "
            "of geometry/inlet.py (theta1 = theta2 = 8 deg). Dotted lines: the shock-on-lip rule. Definitions: "
            "docs/specs/00_decisions.md, sections 2 and 3. No CFD data.", lines=2)


def body_s3(slide):
    path = "docs/talk/figures/design_box.png"
    draw_design_box(ROOT / path)
    w, h = add_figure(slide, path, LM, CT, 6.2, 4.1)
    caption(slide, LM, CT + h + 0.05, 6.4,
            f"Figure: {path}, drawn by docs/talk/build_deck.py from designs/pool_sobol96.csv. "
            "Record: runs/dev/2026-11-01_inlet_box_diagnostics/README.md.", lines=3)
    text_box(slide, 7.4, CT + 0.1, 5.3, 4.0,
             ["96 Sobol points, 4 excluded by gate 4 (theta1 + theta2 > 24 deg), 92 run.",
              "Box: theta1 in [5, 12] deg, theta2 in [5, 14] deg, total turning at most 24 deg.",
              "Excluded pool indices: 0, 40, 72, 80."], size=15, bullets=True, space_after=10)


def body_s4(slide):
    rows = [["Input", "Value", "Where it comes from"],
            ["Mach number", "4.0", "wedge-381c48d17f/case.cfg"],
            ["Freestream temperature", "226.509 K", "wedge-381c48d17f/case.cfg"],
            ["Wall", "isothermal, 300 K", "wedge-381c48d17f/case.cfg"],
            ["Altitude", "30 km", "docs/specs/00_decisions.md, section 1"],
            ["Body", "sub-scale, about 0.3 m", "docs/specs/00_decisions.md, section 1"]]
    add_table(slide, LM, CT + 0.1, [3.4, 3.2, 5.0], rows, size=15, row_h=0.5)
    text_box(slide, LM, CT + 3.3, CW, 0.5,
             "The laminar choice is an argument (sub-scale, high altitude), not a measurement.", size=15)
    pending(slide, LM, CT + 3.9, CW,
            "Transition argument: PENDING: no run record. It is an analytic estimate in "
            "docs/specs/00_decisions.md, section 1.1; no number from it is quoted here.")


def body_s5(slide):
    rows = [["Check", "Tolerance", "Type", "Verdict as the report gives it", "Record"],
            ["V1 oblique shock: beta, p2/p1, M2", "0.5 deg; 2%; 2%", "hard", "PASS (+0.132 deg, -0.12%, -0.19%)", "official (Colab)"],
            ["V2a plateau pressure vs inviscid", "+0 to +6%", "report", "REPORT (+1.69%)", "official (Colab)"],
            ["V2b wall heat flux vs Eckert", "mean 10%, max 15%", "hard", "PASS (mean 1.60%, max 1.95%)", "development"],
            ["V3 q_stag vs Fay-Riddell, fine mesh; medium to fine change", "15%; 5%", "hard",
             "first numerics: FAIL (+216.84%; +628.92%)\nfinal numerics: PASS (-4.49%; -3.46%)", "development"],
            ["V3 stand-off vs Billig", "15%", "report", "not run: no flow.dat", "development"],
            ["V4e throat p0 and Mach, Euler 8/8", "2%", "hard", "PASS (-0.34%, -0.14%)", "development"],
            ["V4v core p0, laminar", "5%", "soft", "PASS (-0.04% to +0.50% on the 6 laminar 8/8 runs)", "development"],
            ["V4m grid, 8/8: recovery; q_peak", "2%; 5%", "hard", "PASS (+0.09%; -1.68%); 12/14 not run", "development"],
            ["X1 AVG_TOTALPRESS vs mass average", "0.5%", "hard", "PASS on the 7 runs at 8/8; 12/14 not run", "development"]]
    add_table(slide, LM, CT, [3.7, 1.9, 0.8, 4.0, 1.7], rows, size=11, row_h=0.42)
    caption(slide, LM, 6.5, CW, "PASS and FAIL are checked against the tolerance; REPORT is reported without a gate; "
            "not run means the check could not run. Record: docs/validation/2026-11-01_report.md.", lines=2)


def body_s6(slide):
    w, h = add_figure_with_caption(slide, "docs/validation/2026-11-01_wedge_heat_flux.png",
                                   "docs/validation/2026-11-01_report.md", LM, CT, 6.6, 4.1)
    rows = [["Check", "Measured", "Tolerance"],
            ["V1 beta (ref 22.234 deg)", "22.366 deg, +0.132 deg", "0.5 deg"],
            ["V1 p2/p1 (ref 2.5060)", "2.5030, -0.12%", "2%"],
            ["V1 M2 (ref 3.2861)", "3.2799, -0.19%", "2%"],
            ["V2a plateau vs inviscid", "+1.69%", "+0 to +6%"],
            ["V2b Eckert, mean", "1.60%", "10%"],
            ["V2b Eckert, max", "1.95%", "15%"]]
    add_table(slide, 7.5, CT + 0.1, [2.2, 1.9, 1.1], rows, size=12, row_h=0.45)
    caption(slide, 7.5, CT + 3.4, 5.2,
            "V1 and V2a: official Colab records, runs/task1/README.md and runs/task1/v1_oblique_shock.json, v2a.json. "
            "V2b: development run, final numerics (wedge_lam_ef03_cfl20), report V2b row, 88 nodes.", lines=4)


def body_s7(slide):
    w1, h1 = add_figure(slide, "docs/validation/2026-11-01_cylinder_heat_flux.png", LM, CT, 5.0, 3.2)
    w2, h2 = add_figure(slide, "docs/validation/2026-11-01_grid_study.png", LM + 5.3, CT, 6.8, 3.2, crop=(0, 0, 2 / 3, 0))
    caption(slide, LM, CT + h1 + 0.04, 5.0, "Figure: docs/validation/2026-11-01_cylinder_heat_flux.png. "
            "Record: docs/validation/2026-11-01_report.md.", lines=2)
    caption(slide, LM + 5.3, CT + h2 + 0.04, 6.8, "Figure: docs/validation/2026-11-01_grid_study.png (left two panels, "
            "cylinder q_stag, first and final numerics). Record: docs/validation/2026-11-01_report.md.", lines=2)
    rows = [["Cylinder, hard checks", "q_stag vs Fay-Riddell, fine mesh (15%)", "Medium to fine change (5%)"],
            ["Roe, entropy fix 0.1 (attempt 1)", "FAIL: +216.84%", "FAIL: +628.92%"],
            ["Roe, entropy fix 0.3 (attempt 3)", "PASS: -4.49%", "PASS: -3.46%"]]
    add_table(slide, LM, CT + 3.9, [3.8, 4.6, 3.7], rows, size=12, row_h=0.36)


def body_s8(slide):
    wall = "docs/talk/figures/wall_8_8_laminar_vs_sa.png"
    draw_wall_laminar_vs_sa(ROOT / wall)
    throat = "docs/validation/2026-11-01_inlet_throat_p0.png"
    w1, h1 = add_figure(slide, throat, LM, CT, 4.7, 2.75)
    w2, h2 = add_figure(slide, wall, LM + 4.7 + 0.3, CT, 7.1, 2.75)
    caption(slide, LM, CT + h1 + 0.04, 4.7, f"Figure: {throat}. Record: docs/validation/2026-11-01_report.md and "
            "runs/dev/2026-11-01_inlet_design_point/README.md. Development run, not the official Task 2 record.", lines=4)
    caption(slide, LM + 5.0, CT + h2 + 0.04, 7.1, f"Figure: {wall}, drawn by docs/talk/build_deck.py from the body-wall nodes of "
            "surface_flow.dat.gz in runs/dev/2026-11-01_inlet_grid_study_ef03/8_8_medium (laminar) and "
            "runs/dev/2026-11-01_turbulence_sensitivity_SA/8_8_medium_SA (Spalart-Allmaras, a sensitivity bound). "
            "Labeled q_peak values equal metrics.json of each run; p_inf = 1197.03 Pa.", lines=4)
    rows = [["Check (8/8, medium)", "Measured", "Tolerance", "Verdict"],
            ["V4e throat p0/p0_inf, Euler", "0.9284 vs 0.9316 two-shock, -0.34%", "2% hard", "PASS"],
            ["V4e throat Mach, Euler", "2.958 vs 2.962, -0.14%", "2% hard", "PASS"],
            ["V4v core p0/p0_inf, laminar", "0.9351 vs 0.9316, +0.39%", "5% soft", "PASS"],
            ["Laminar, whole throat", "area average 0.8824; mass-averaged 0.9114", "shown, not gated",
             "boundary-layer loss about 2%"]]
    add_table(slide, LM, CT + 3.65, [3.0, 4.5, 1.7, 2.93], rows, size=11, row_h=0.28)


def body_s9(slide):
    labels = ["parameters", "schema", "physics gates", "mesh quality", "config check", "Drive queue",
              "Colab worker", "SU2", "result or error", "metrics", "surrogate", "acquisition"]
    draw_pipeline(slide, labels, 4.35, CT + 0.05, 4, 1.75, 0.8, 0.45, 0.7, highlight=(1, 2, 3, 4))
    box(slide, LM, CT + 0.05, 2.9, 0.8, "Claude Code (MCP client)", size=14, fill=WHITE, bold=True)
    arrow(slide, LM + 1.45, CT + 0.85, LM + 1.45, CT + 1.3)
    box(slide, LM, CT + 1.3, 2.9, 2.5, "typed tools\ncreate_case\nvalidate_config\nsubmit\nlist_results\npostprocess", size=13)
    arrow(slide, LM + 2.9, CT + 2.55, 4.1, CT + 2.55)
    arrow(slide, 4.1, CT + 0.05, 4.1, CT + 3.9, head=False)
    text_box(slide, LM, CT + 4.0, 2.9, 0.8, "never chooses a sampling point", size=14, color=ACCENT, bold=True)
    text_box(slide, 4.35, CT + 4.55, 8.3, 0.4, "Shaded boxes: the gates a design passes before SU2 sees it.", size=12, color=GREY)


def body_s10(slide):
    rows = [["Case (medium mesh unless stated)", "Total turning", "Outcome", "recovery_total", "q_peak [kW/m2]"],
            ["12/14, entropy fix 0.1 and 0.3, medium and fine", "26 deg", "diverged (2300 to 4350 iterations)", "-", "-"],
            ["12/14 medium, CFL max 5", "26 deg", "residual fell to -7.4 then grew to +1.7: diverging", "-", "-"],
            ["12/12", "24 deg", "converged (2063 iterations)", "0.4065", "46.9"],
            ["8/14", "22 deg", "converged (2160 iterations)", "0.3876", "47.9"],
            ["5/14", "19 deg", "converged (1952 iterations)", "0.3481", "43.1"]]
    add_table(slide, LM, CT + 0.1, [2.2, 0.8, 2.0, 1.2, 1.0], rows, size=10, row_h=0.5)
    path = "docs/talk/figures/wall_12_14_diverged.png"
    info = draw_wall_12_14_diverged(ROOT / path)
    p_max_file = info[f"{GRID_RUNS}/12_14_medium"][1]
    w, h = add_figure(slide, path, 8.05, CT + 0.05, 4.65, 3.2)
    caption(slide, 8.05, CT + 0.05 + h + 0.04, 4.65,
            f"Figure: {path}, drawn by docs/talk/build_deck.py from surface_flow.dat.gz of {GRID_RUNS}/12_14_medium "
            f"(exited with an error after 4347 iterations; {GRID_RUNS}/README.md) and {BOX_RUNS}/12_12_medium. "
            f"Largest pressure in the 12/14 surface file: {p_max_file / 1e10:.1f}e10 Pa; p_inf = 1197.03 Pa.", lines=5)
    text_box(slide, LM, CT + 3.3, 7.2, 1.4,
             ["Gate 4: total turning at most 24 deg; 4 of the 96 pool points (indices 0, 40, 72, 80) are excluded.",
              "12/14 diverged on both meshes, medium and fine, with both entropy fixes and both CFL caps (20 and 5)."],
             size=13, bullets=True, space_after=4)


def body_s11(slide):
    # folder diagram: jobs/ -> worker -> runs/<id>/ with status flags and result or error
    box(slide, LM, CT + 0.1, 2.3, 0.8, "jobs/<case_id>.json\n(uploaded job file)", size=13)
    box(slide, 3.5, CT + 0.1, 2.0, 0.8, "Colab worker\n(polls the folder)", size=13, fill=WHITE)
    box(slide, 6.1, CT + 0.1, 2.0, 0.8, "runs/<case_id>/", size=13)
    arrow(slide, LM + 2.3, CT + 0.5, 3.5, CT + 0.5)
    arrow(slide, 5.5, CT + 0.5, 6.1, CT + 0.5)
    text_box(slide, LM, CT + 1.3, 4, 0.3, "runs/<case_id>/status/ flags", size=13, color=GREY)
    box(slide, LM, CT + 2.2, 1.3, 0.65, "0-seen", size=13, fill=WHITE)
    box(slide, 2.2, CT + 2.2, 1.3, 0.65, "1-running", size=13, fill=WHITE)
    box(slide, 4.0, CT + 1.7, 1.3, 0.65, "2-done", size=13, fill=WHITE)
    box(slide, 4.0, CT + 2.7, 1.3, 0.65, "2-failed", size=13, fill=WHITE)
    arrow(slide, LM + 1.3, CT + 2.525, 2.2, CT + 2.525)
    arrow(slide, 3.5, CT + 2.35, 4.0, CT + 2.025)
    arrow(slide, 3.5, CT + 2.7, 4.0, CT + 3.025)
    box(slide, 5.9, CT + 1.7, 2.3, 0.65, "result.json + .sha256", size=13)
    box(slide, 5.9, CT + 2.7, 2.3, 0.65, "error.json + .sha256", size=13)
    arrow(slide, 5.3, CT + 2.025, 5.9, CT + 2.025)
    arrow(slide, 5.3, CT + 3.025, 5.9, CT + 3.025)
    box(slide, LM, CT + 3.75, 4.6, 0.65, "heartbeat.json (a stale one marks a killed worker)", size=13, fill=WHITE)
    caption(slide, LM, CT + 4.5, 7.6, "Layout from docs/specs/01_interfaces.md (job directory); flags and records as listed there.",
            lines=1)
    text_box(slide, 8.8, CT + 0.1, 3.9, 4.6,
             ["Ingest refuses a result that does not match the sha256 digest the worker wrote next to it.",
              "2026-11-02: the worker on Colab restarted with --retry-reason config_mismatch and re-ran the 63 refused pool "
              "jobs without repeating the 29 finished ones; all 92 pool points converged.",
              "F8: a killed worker is found by its stale heartbeat and the job is re-run once (local test with the fake solver)."],
             size=14, bullets=True, space_after=8)


def body_s12(slide):
    text_box(slide, LM, CT + 0.05, CW, 0.4, "Call: list_results(tag=\"val\"), 2026-11-01. Ten rows, all status pending, metrics null.",
             size=15, bold=True)
    rows = [["Family", "Design (theta1/theta2 deg)", "Case ids", "Rows", "Status"],
            ["cylinder", "none (theta null)", "cylinder-941780775b, cylinder-fd9d9778c5, cylinder-854aee41c4", "3", "pending"],
            ["wedge", "theta1 10.0", "wedge-b39d378f9c", "1", "pending"],
            ["inlet2r", "8/8", "inlet2r-619144f64c, -bb81bb26f0, -d4d29884be, -5e844a838c", "4", "pending"],
            ["inlet2r", "12/14 (staged before gate 4 was trimmed to 24 deg; kept as a recorded failure case)",
             "inlet2r-20b8dcc9ec, -dbccca19df", "2", "pending"]]
    add_table(slide, LM, CT + 0.6, [1.4, 3.8, 4.5, 0.7, 1.7], rows, size=13, row_h=0.55, flag=())
    text_box(slide, LM, CT + 3.75, CW, 0.6,
             "The claim is limited to what the tool returned: it read flag files and result.json only and chose no sampling point.",
             size=15)
    caption(slide, LM, CT + 4.4, CW, "Record: docs/transcripts/2026-11-01_first_mcp_call.md (a transcript, not a runs/ record). "
            "Rows grouped by family here; the transcript lists them one per case.", lines=2)


def body_s13(slide):
    box(slide, LM, CT + 1.2, 2.6, 1.0, "inputs\ntheta1, theta2\n(scaled to the unit box)", size=13, fill=WHITE)
    box(slide, 4.2, CT + 0.4, 3.2, 0.9, "GP: recovery_total", size=15, bold=True)
    box(slide, 4.2, CT + 2.1, 3.2, 0.9, "GP: log q_peak", size=15, bold=True)
    box(slide, 8.8, CT + 0.4, 3.9, 0.9, "mean and 90 percent interval\nrecovery_total", size=13, fill=WHITE)
    box(slide, 8.8, CT + 2.1, 3.9, 0.9, "mean and 90 percent interval\nq_peak (from the log prediction)", size=13, fill=WHITE)
    arrow(slide, LM + 2.6, CT + 1.6, 4.2, CT + 0.85)
    arrow(slide, LM + 2.6, CT + 1.8, 4.2, CT + 2.55)
    arrow(slide, 7.4, CT + 0.85, 8.8, CT + 0.85)
    arrow(slide, 7.4, CT + 2.55, 8.8, CT + 2.55)
    text_box(slide, LM, CT + 3.35, CW, 1.4,
             ["Exact GP, pure PyTorch, Matern 5/2 kernel with automatic relevance lengths, fitted by marginal likelihood.",
              "One GP per objective; the Colab GPU is not needed.",
              "Interval check: the replay calibration (slide S16)."], size=14, bullets=True, space_after=6)
    caption(slide, LM, CT + 4.55, CW, "Specification: docs/specs/task4_surrogate_active_learning.md. Drawing, no data.", lines=1)


def body_s14(slide):
    box(slide, LM, CT + 1.1, 2.9, 1.1, "posterior mean + variance\n(both GPs)", size=14, fill=WHITE)
    box(slide, 4.5, CT + 0.2, 3.4, 0.9, "EHVI (Monte-Carlo)", size=15, bold=True)
    box(slide, 4.5, CT + 2.2, 3.4, 0.9, "max-variance (control)", size=15, bold=True)
    box(slide, 9.4, CT + 1.2, 3.3, 0.9, "next design", size=15, bold=True, fill=WHITE)
    arrow(slide, LM + 2.9, CT + 1.5, 4.5, CT + 0.65)
    arrow(slide, LM + 2.9, CT + 1.8, 4.5, CT + 2.65)
    arrow(slide, 7.9, CT + 0.65, 9.4, CT + 1.5)
    arrow(slide, 7.9, CT + 2.65, 9.4, CT + 1.8)
    text_box(slide, 9.4, CT + 2.3, 3.3, 0.8, "deterministic given the seed; LLM not in the loop", size=13, color=ACCENT, bold=True)
    text_box(slide, LM, CT + 3.45, CW, 1.4,
             ["EHVI: Monte-Carlo expected hypervolume improvement on (-recovery_total, log q_peak).",
              "Max-variance: sum of the standardized posterior variances; pure exploration, the control.",
              "Candidates: in the replay, the unselected pool points."], size=14, bullets=True, space_after=6)
    caption(slide, LM, CT + 4.55, CW, "Specification: docs/specs/task4_surrogate_active_learning.md. Drawing, no data.", lines=1)


def body_s15(slide):
    fig = "docs/validation/2026-11-02_replay_full_error_vs_n.png"
    w, h = add_figure_with_caption(slide, fig, "docs/validation/2026-11-02_replay.md and "
                                   "docs/validation/2026-11-02_replay_full_summary.md", LM, CT, 8.2, 2.8)
    text_box(slide, 9.0, CT, 3.7, 3.0,
             ["Final replay: all 92 pool points, 10 seeds, n = 8 to 48. Median and interquartile band.",
              "Hypervolume regret: EHVI is lowest at every budget from n = 12; 0 in 10 of 10 seeds from n = 32 "
              "(the 26-point true front is contained). No other strategy reaches 0 by n = 48."],
             size=13, bullets=True, space_after=6)
    text_box(slide, LM, CT + 3.4, CW, 1.5,
             ["Held-out error: EHVI has the highest recovery RMSE of the four from n = 12 to 32 and overtakes random and LHS "
              "only at n = 40. Recovery RMSE at n = 48: EHVI 1.6e-5, random 3.1e-5, LHS 2.3e-5, max-variance 1.4e-5.",
              "Max-variance has the lowest recovery RMSE from n = 16 on. All four strategies share one pool, so no extra CFD."],
             size=13, bullets=True, space_after=6)


def body_s16(slide):
    w, h = add_figure_with_caption(slide, "docs/validation/2026-11-02_replay_full_calibration.png",
                                   "docs/validation/2026-11-02_replay.md", LM, CT, 7.4, 3.6)
    text_box(slide, 8.3, CT, 4.4, 4.0,
             ["Final replay, 92 pool points, n = 48, 44 held-out points.",
              "q_peak coverage is inside the band: 0.84 to 0.91 at the 90 percent level.",
              "Recovery is over-covered: 1.0 at the 90 percent level for every strategy. Flagged and explained, not refitted.",
              "Flag band 80 to 97 percent: tolerance C1, docs/specs/00_decisions.md, section 5."],
             size=14, bullets=True, space_after=8)


def body_s17(slide):
    w, h = add_figure_with_caption(slide, "runs/analysis/2026-11-02/design_map.png",
                                   "runs/pool/results.csv", LM, CT, 5.0, 4.3,
                                   crop_note=" (panel \"observed runs\" cropped)", crop=(0.315, 0.495, 0.425, 0.0))
    text_box(slide, 6.6, CT, 6.1, 4.0,
             ["92 converged, 0 failed (runs/pool/results.csv).",
              "The 4 of the 96 Sobol points in designs/pool_sobol96.csv with theta1 + theta2 > 24 deg were refused by gate 4 "
              "and never staged.",
              "Shaded corner: theta1 + theta2 > 24 deg (gate 4). The full design map, with the GP maps, is on slide S20."],
             size=15, bullets=True, space_after=10)


def body_s18(slide):
    w, h = add_figure_with_caption(slide, "runs/analysis/2026-11-02/pareto_front.png",
                                   "runs/analysis/2026-11-02/pareto.csv", LM, CT, 6.6, 4.2)
    text_box(slide, 7.6, CT, 5.1, 4.4,
             ["26 observed front points of 92.",
              "Posterior band: 1.2e-4 to 1.8e-3 wide in recovery.",
              "Discretization error bar (V4m grid study): 3.1e-4 in recovery and 530 W/m2 in q_peak; "
              "25 times the posterior uncertainty in heat flux.",
              "Source: docs/validation/2026-11-02_pareto_inverse.md, section 2."],
             size=14, bullets=True, space_after=8)


def body_s19(slide):
    rows = [["Query", "Surrogate answer (90 percent interval)", "Confirmation run result", "Inside interval?"],
            ["Highest recovery with q_peak under the 40th percentile of pool heating (cap 31493 W/m2); "
             "answer theta1 = 11.965 deg, theta2 = 7.115 deg",
             "recovery_total 0.34515 (0.34506 to 0.34523)", "0.34513 (z = -0.41)", "yes"],
            ["", "q_peak 31470 W/m2 (31450 to 31490); P(q <= cap) = 0.972", "31462 W/m2 (z = -0.66)", "yes"]]
    table = add_table(slide, LM, CT + 0.1, [4.6, 3.9, 2.2, 1.4], rows, size=13, row_h=0.7)
    table.cell(1, 0).merge(table.cell(2, 0))
    text_box(slide, LM, CT + 2.4, CW, 0.5, "C2 pass: the SU2 run inlet2r-374dad241f (Colab, 2026-11-02 14:38 UTC, 1248 iterations, converged) "
             "falls inside both 90 percent intervals and below the cap.", size=14, color=ACCENT, bold=True)
    text_box(slide, LM, CT + 3.0, CW, 1.6,
             ["The cap is fixed from the pool before the answer is known (40th percentile of the pool's q_peak).",
              "One run inside a 90 percent interval is one draw, not a calibration statistic; the calibration evidence is the replay (S16).",
              "Refitting the GPs with this one new point shrinks the predictive std at the design from 5.1e-5 to 4.6e-5 in recovery "
              "and from 3.9e-4 to 3.5e-4 in log q_peak (ratios 0.90 and 0.92)."],
             size=14, bullets=True, space_after=6)
    caption(slide, LM, CT + 4.7, CW, "Records: runs/analysis/2026-11-02/inverse_q40/result.json; runs/confirm/inlet2r-374dad241f/result.json; "
            "runs/analysis/2026-11-02/confirm/confirm.json; docs/validation/2026-11-02_pareto_inverse.md, section 3.", lines=2)


def body_s20(slide):
    w, h = add_figure(slide, "runs/analysis/2026-11-02/design_map.png", LM, CT, 8.0, 4.3)
    caption(slide, LM, CT + h + 0.04, 8.0, "Figure: runs/analysis/2026-11-02/design_map.png. "
            "Records: runs/analysis/2026-11-02/grid.csv, docs/validation/2026-11-02_pareto_inverse.md, section 4.", lines=2)
    w2, h2 = add_figure(slide, "runs/analysis/2026-11-02/oswatitsch_cut.png", 8.9, CT, 3.8, 2.5)
    caption(slide, 8.9, CT + h2 + 0.04, 3.8, "Figure: runs/analysis/2026-11-02/oswatitsch_cut.png.", lines=1)
    text_box(slide, 8.9, CT + h2 + 0.5, 3.8, 1.9,
             ["Recovery std 1.8e-5 to 1.1e-4 over the box.",
              "Oswatitsch cut: GP mean 0.0008 to 0.0022 above the inviscid analytic curve, explained from the recorded throat Mach."],
             size=12, bullets=True, space_after=4)


def body_s21(slide):
    rows = [["What failed", "What the record shows", "What changed"],
            ["1. Cylinder carbuncle, Roe at entropy fix 0.1",
             "Fine mesh q_stag +216.84% against Fay-Riddell (FAIL); medium run diverged",
             "Entropy fix 0.3: fine mesh -4.49%, grid change -3.46%, PASS; the CFL cap alone did not help"],
            ["2. Euler wedge with AUSM+-up2 diverged or stalled",
             "Variants A, B, D: diverged at iteration 50 or stalled for 800 iterations",
             "Roe with CFL adapt (0.5, 1.05, 1.0, 20): converged (variant C)"],
            ["3. 12/14 corner diverged",
             "Residual to -7.5, then growth, on both meshes and both entropy fixes",
             "Gate 4: total turning at most 24 deg; 4 of 96 pool points excluded"],
            ["4. Diverged surface file reported as \"check the units\"",
             "Pressures up to about 8e10 Pa in the 12/14 surface file",
             "Divergence check placed before the cross-check; the report now says \"solution diverged\""],
            ["5. Pool job refused as config mismatch",
             "One number in a comment line (h_duct) differed by 3e-18 between container and Colab; 63 jobs refused",
             "Config hash covers only the lines SU2 reads; worker restarted with --retry-reason; 92 of 92 converged"]]
    add_table(slide, LM, CT + 0.1, [3.3, 4.3, 4.5], rows, size=14, row_h=0.8)


def body_s22(slide):
    rows = [["Limit", "Consequence for the Pareto front"],
            ["Laminar flow at a sub-scale, high-altitude condition (Re_L at most 5e5)",
             "Spalart-Allmaras sensitivity (development runs, a bound): peak heating 2.5 to 2.6 times laminar; "
             "throat recovery 0.857 against 0.909 at 8/8. The trade-off keeps its direction, the heating level does not"],
            ["Two-dimensional, two design variables", "The front is a front in theta1 and theta2 only; cowl position and wall "
             "temperature are not design variables"],
            ["12/14 corner (26 deg total turning) does not converge",
             "Gate 4 trims total turning to 24 deg, so the front holds inside the trimmed box; the 25 deg band was not tested"],
            ["Sharp leading edge: wall-node temperature departs from 300 K within about 30 mm (750 K at the tip)",
             "Both objectives are placed away from it: ramp 2 only, x >= 0.1 m"],
            ["Mesh level", "Discretization error bar 3.1e-4 in recovery and 530 W/m2 in q_peak (V4m, 8/8); "
             "no converged grid study at 12/14"]]
    add_table(slide, LM, CT + 0.1, [4.6, 7.5], rows, size=14, row_h=0.8)


def body_s23(slide):
    rows = [["Item", "State", "Record"],
            ["Validation checks V1 to V4, X1", "done (development runs; V1 and V2a official)", "docs/validation/2026-11-01_report.md"],
            ["Official validation batch: V3, V4m, V4e metrics form, X1, two 12/14 failures", "done",
             "docs/validation/2026-11-01_colab_records.md"],
            ["Fault matrix F1 to F10b (run without SU2)", "done", "docs/faults/fault_matrix.md"],
            ["Turbulence sensitivity (Spalart-Allmaras)", "done (development, a bound)",
             "runs/dev/2026-11-01_turbulence_sensitivity_SA/README.md"],
            ["92-point pool", "done: 92 of 92 converged, 0 failures", "docs/validation/2026-11-01_colab_records.md"],
            ["Replay: active learning against random and LHS", "done", "docs/validation/2026-11-02_replay.md"],
            ["Pareto front and inverse query", "done", "docs/validation/2026-11-02_pareto_inverse.md"],
            ["Confirmation run inlet2r-374dad241f", "done: C2 pass (both objectives inside the 90 percent interval)",
             "runs/confirm/, runs/analysis/2026-11-02/confirm/confirm.json"],
            ["Spalart-Allmaras sensitivity on Colab (3 runs)", "done (a bound, no transition model)",
             "runs/sensitivity/, docs/validation/2026-11-02_sa_sensitivity.md"]]
    add_table(slide, LM, CT, [4.6, 3.9, 3.6], rows, size=13, row_h=0.5)


def body_s24(slide):
    items = ["B1  Turbulence model (why laminar?)", "B2  Wall boundary condition (is the wall really at 300 K?)",
             "B3  Mesh convergence (is the mesh converged?)", "B4  The numerics story (why this scheme?)",
             "B5  Design-box trim (why 24 degrees?)", "B6  Full validation table (what did not run?)"]
    text_box(slide, LM, CT + 0.2, CW, 3.8, items, size=22, space_after=12)


def body_b1(slide):
    rows = [["Case", "Model", "Record", "recovery_total", "recovery_throat", "q_peak [kW/m2]", "wall y+ (dev run)"],
            ["8/8 medium", "laminar", "runs/val/inlet2r-d4d29884be", "0.3163", "0.9085", "29.73", "-"],
            ["8/8 medium", "SA", "runs/sensitivity/inlet2r-1731bdea74", "0.3112", "0.8565", "76.98", "2.3 / 3.0"],
            ["8/8 fine", "laminar", "runs/val/inlet2r-5e844a838c", "0.3166", "0.9105", "29.23", "-"],
            ["8/8 fine", "SA", "runs/sensitivity/inlet2r-8a09596911", "0.3109", "0.8592", "76.29", "1.7 / 2.6"],
            ["12/12 medium", "laminar", "runs/dev/.../12_12_medium", "0.4065", "0.8222", "46.86", "-"],
            ["12/12 medium", "SA", "runs/sensitivity/inlet2r-d7e3815b57", "0.3925", "0.7441", "118.20", "3.1 / 3.6"]]
    add_table(slide, LM, CT + 0.1, [1.4, 0.9, 3.4, 1.5, 1.6, 1.5, 1.8], rows, size=11, row_h=0.42)
    text_box(slide, LM, CT + 3.6, CW, 1.4,
             ["Peak heating 2.59, 2.61 and 2.52 times laminar; recovery_total lower by 0.005 to 0.014; throat recovery 0.857 against 0.909 at 8/8.",
              "Colab runs (RANS_SA, 4 ranks) equal the container development runs to every printed digit. "
              "SA without a transition model and with y+ above 1: a sensitivity bound, not a validated turbulent prediction."],
             size=13, bullets=True, space_after=6)


def body_b2(slide):
    path = "docs/talk/figures/wall_temperature.png"
    draw_wall_temperature(ROOT / path)
    w, h = add_figure(slide, path, LM, CT, 6.4, 4.0)
    caption(slide, LM, CT + h + 0.05, 6.6, f"Figure: {path}, drawn by docs/talk/build_deck.py from "
            "runs/dev/2026-11-01_numerics/wedge-381c48d17f-tecplot/surface_flow.dat.gz (laminar wedge, development run).", lines=3)
    rows = [["x along the wedge", "SU2 wall-node temperature"],
            ["tip", "750 K"], ["0.1 mm", "459 K"], ["1.3 mm", "335 K"], ["beyond about 30 mm", "below 301 K"]]
    add_table(slide, 7.5, CT + 0.1, [2.6, 2.6], rows, size=13, row_h=0.45)
    text_box(slide, 7.5, CT + 2.6, 5.2, 1.8,
             ["The heat-flux objective starts at x = 0.1 m on ramp 2, outside this region."], size=14, bullets=True)
    caption(slide, 7.5, CT + 3.4, 5.2, "Values: runs/dev/2026-11-01_numerics/README.md.", lines=1)


def body_b3(slide):
    path = "docs/validation/2026-11-01_grid_study.png"
    # the two inlet panels of the final numerics (entropy fix 0.3: panels 3 and 4 of 6); the table below matches them
    w, h = add_figure(slide, path, LM, CT, 6.3, 2.0, crop=(2 / 6, 0, 2 / 6, 0))
    caption(slide, LM, CT + h + 0.04, 6.3, f"Figure: {path}, panels 3 and 4 of 6 (inlet 8/8, final numerics; the "
            "other panels are on S7 and in the report). Record: docs/validation/2026-11-01_report.md.", lines=3)
    rows = [["8/8 laminar inlet", "Cells", "recovery_total", "q_peak [kW/m2]"],
            ["coarse", "19 620", "0.3163", "30.18"],
            ["medium", "30 600", "0.3163", "29.73"],
            ["fine", "55 640", "0.3166", "29.23"],
            ["medium to fine", "", "+0.09% (tolerance 2%)", "-1.68% (tolerance 5%)"],
            ["12/14 medium, fine", "25 000, 45 240", "diverged", "diverged"]]
    add_table(slide, LM, CT + h + 0.75, [1.7, 1.4, 1.7, 1.5], rows, size=11, row_h=0.4, flag=("diverged",))
    mesh = "docs/talk/figures/mesh_8_8_medium.png"
    cells, nodes = draw_mesh_8_8_medium(ROOT / mesh)
    quality = read_json(ROOT / f"{GRID_RUNS}/8_8_medium/mesh_quality.json")["first_cell_height"]
    mw, mh = add_figure(slide, mesh, 6.9, CT, 5.8, 3.5)
    n_cells, n_nodes = (f"{n:,}".replace(",", " ") for n in (cells, nodes))     # deck style: 30 600
    caption(slide, 6.9, CT + mh + 0.04, 5.8,
            f"Figure: {mesh}, drawn by docs/talk/build_deck.py. The mesh of {GRID_RUNS}/8_8_medium is rebuilt from "
            f"its params.json by worker/make_case.py and matches the run's mesh_quality.json. Structured, {n_cells} cells, "
            f"{n_nodes} nodes; first cell {quality['body'] * 1e6:.1f} um on the body and {quality['cowl'] * 1e6:.1f} um "
            "on the cowl (mesh_quality.json).", lines=6)


def body_b4(slide):
    rows_a = [["Variant (Euler wedge)", "Change", "Outcome"],
              ["A_fixedcfl5", "CFL 5 fixed", "diverged at iteration 50"],
              ["B_adapt_max20", "CFL adapt (0.5, 1.05, 1.0, 20)", "stalled, 800 iterations"],
              ["C_roe", "Roe, entropy fix 0.1, CFL adapt", "converged in 603 iterations"],
              ["D_venkat", "Venkatakrishnan limiter", "stalled, 800 iterations"]]
    rows_b = [["Cylinder scheme (coarse)", "q_stag vs Fay-Riddell", "Verdict"],
              ["HLLC", "+125%", "no"],
              ["AUSM+-up2", "+49%", "no (carbuncle pattern)"],
              ["SLAU2", "-35%", "no (carbuncle pattern)"],
              ["JST, first order", "-91%", "no (stagnation point smeared)"],
              ["Roe, first order", "+53%", "no"],
              ["Roe, entropy fix 0.3, CFL max 5", "-0.3%", "yes"]]
    add_table(slide, LM, CT, [1.5, 2.6, 1.9], rows_a, size=10, row_h=0.32, flag=())
    add_table(slide, 6.9, CT, [2.6, 1.6, 1.6], rows_b, size=10, row_h=0.32, flag=())
    path = "docs/talk/figures/cylinder_schemes.png"
    draw_cylinder_schemes(ROOT / path)
    w, h = add_figure(slide, path, LM, CT + 1.8, 6.0, 3.0)
    text_box(slide, 6.9, CT + 2.55, 5.8, 1.0,
             ["Attempt 3: only the entropy fix cured the carbuncle; the CFL cap did not.",
              "Wedge Eckert window: mean 0.75% at entropy fix 0.1, 1.60% at 0.3."], size=12, bullets=True, space_after=3)
    caption(slide, 6.9, CT + 3.5, 5.8,
            f"Figure: {path}, drawn by docs/talk/build_deck.py from surface_flow.dat.gz of the six schemes in "
            f"{CYL_SCHEMES}/ (coarse mesh, 57 wall nodes, R = 10 mm); Fay-Riddell 244.3 kW/m2 from the same "
            "runs/dev/2026-11-01_cylinder_v3_attempt2/README.md. Records: runs/dev/2026-11-01_numerics/README.md "
            "(A to D), runs/dev/2026-11-01_cylinder_v3_attempt3/README.md.", lines=7)


def body_b5(slide):
    path = "docs/talk/figures/design_box_diagnostics.png"
    draw_box_diagnostics(ROOT / path)
    w, h = add_figure(slide, path, LM, CT, 6.2, 4.2)
    caption(slide, LM, CT + h + 0.05, 6.4, f"Figure: {path}, drawn by docs/talk/build_deck.py from "
            "runs/dev/2026-11-01_inlet_box_diagnostics/README.md and designs/pool_sobol96.csv.", lines=3)
    text_box(slide, 7.4, CT + 0.1, 5.3, 4.2,
             ["12/14 diverged on two meshes, with both entropy fixes and both CFL caps.",
              "12/12, 8/14 and 5/14 converged.",
              "Gate 4: total turning at most 24 deg; 4 of 96 pool points excluded.",
              "The 25 deg band between 24 and 26 was not tested."], size=15, bullets=True, space_after=8)


def body_b6(slide):
    head = ["Check", "Type", "Verdict", "Records"]
    left = [head,
            ["V1 beta, p2/p1, M2", "hard", "PASS", "official (Colab)"],
            ["V2a plateau pressure", "report", "REPORT +1.69%", "official (Colab)"],
            ["V2b Eckert heat flux", "hard", "PASS, mean 0.75 to 1.60%", "development, 3 runs"],
            ["V3 q_stag, fine; grid", "hard", "first numerics FAIL; final PASS", "development"],
            ["V4e throat p0, Mach", "hard", "PASS", "development"],
            ["V4v core p0", "soft", "PASS on the 6 laminar 8/8 runs", "development"],
            ["V4m grid, 8/8", "hard", "PASS", "development"]]
    right = [head,
             ["X1 AVG_TOTALPRESS", "hard", "PASS on the 7 runs at 8/8", "development"],
             ["V3 stand-off vs Billig", "report", "not run: no flow.dat", "7 cases"],
             ["V1 on two dev runs", "hard", "not run: flow.dat absent", "development"],
             ["V2b on four cases", "hard", "not run: surface_flow.dat absent", "task1 and numerics"],
             ["V4v, V4m, X1 at 12/14", "soft, hard", "not run: diverged runs", "development"],
             ["V4m grid at 12/14", "hard", "not run: diverged runs", "development"]]
    add_table(slide, LM, CT, [1.7, 0.7, 2.0, 1.5], left, size=11, row_h=0.5, flag=("FAIL", "PENDING", "not run"))
    add_table(slide, 6.9, CT, [1.7, 0.8, 2.0, 1.3], right, size=11, row_h=0.5)
    caption(slide, LM, CT + 4.2, CW, "Record: docs/validation/2026-11-01_report.md. Not-run rows are shown, not hidden.", lines=1)


# ---- the deck: one dict per slide -------------------------------------------------------------
REPORT = "docs/validation/2026-11-01_report.md"
SLIDES = {
    "S2": {"title": "The design question", "body": body_s2,
           "sources": ["geometry/inlet.py", "docs/specs/00_decisions.md (sections 2, 3)"]},
    "S3": {"title": "The design box", "body": body_s3,
           "sources": ["designs/pool_sobol96.csv", "runs/dev/2026-11-01_inlet_box_diagnostics/README.md"]},
    "S4": {"title": "Flight condition, and why laminar", "body": body_s4,
           "sources": ["runs/dev/2026-11-01_numerics/wedge-381c48d17f/case.cfg", "docs/specs/00_decisions.md (section 1)"]},
    "S5": {"title": "The validation ladder", "body": body_s5, "sources": [REPORT]},
    "S6": {"title": "Oblique shock and laminar heating", "body": body_s6,
           "sources": ["runs/task1/README.md", "runs/task1/v1_oblique_shock.json", "runs/task1/v2a.json", REPORT]},
    "S7": {"title": "The cylinder: the hard check failed first", "body": body_s7,
           "sources": [REPORT, "runs/dev/2026-11-01_cylinder_v3_attempt1/README.md",
                       "runs/dev/2026-11-01_cylinder_v3_attempt3/README.md"]},
    "S8": {"title": "Inlet design point at 8/8", "body": body_s8,
           "sources": ["runs/dev/2026-11-01_inlet_design_point/README.md", REPORT, "runs/dev/2026-11-01_inlet_grid_study_ef03/8_8_medium/surface_flow.dat.gz",
                       "runs/dev/2026-11-01_turbulence_sensitivity_SA/README.md",
                       "runs/dev/2026-11-01_turbulence_sensitivity_SA/8_8_medium_SA/surface_flow.dat.gz"]},
    "S9": {"title": "The pipeline on one slide", "body": body_s9, "sources": ["docs/specs/01_interfaces.md"]},
    "S10": {"title": "Gates reject before any CFD", "body": body_s10,
            "sources": ["runs/dev/2026-11-01_inlet_box_diagnostics/README.md",
                        "runs/dev/2026-11-01_inlet_grid_study_ef03/README.md",
                        "runs/dev/2026-11-01_inlet_grid_study_ef03/12_14_medium/surface_flow.dat.gz",
                        "runs/dev/2026-11-01_inlet_box_diagnostics/12_12_medium/surface_flow.dat.gz"]},
    "S11": {"title": "Drive queue and a restart-safe worker", "body": body_s11,
            "sources": ["docs/specs/01_interfaces.md", "docs/transcripts/2026-11-02_worker_restart_and_retry.md",
                        "docs/validation/2026-11-01_colab_records.md", "docs/faults/fault_matrix.md"]},
    "S12": {"title": "The first live agent call", "body": body_s12, "sources": ["docs/transcripts/2026-11-01_first_mcp_call.md"]},
    "S13": {"title": "One exact Gaussian process per objective", "body": body_s13,
            "sources": ["docs/specs/task4_surrogate_active_learning.md"]},
    "S14": {"title": "Acquisition, and who chooses", "body": body_s14,
            "sources": ["docs/specs/task4_surrogate_active_learning.md"]},
    "S15": {"title": "Active learning against random and LHS", "body": body_s15,
            "sources": ["docs/validation/2026-11-02_replay_full_error_vs_n.png",
                        "docs/validation/2026-11-02_replay_full_summary.md", "docs/validation/2026-11-02_replay.md"]},
    "S16": {"title": "Calibration", "body": body_s16,
            "sources": ["docs/validation/2026-11-02_replay_full_calibration.png", "docs/validation/2026-11-02_replay.md",
                        "docs/specs/00_decisions.md (section 5)"]},
    "S17": {"title": "The pool across the box", "body": body_s17,
            "sources": ["runs/analysis/2026-11-02/design_map.png", "runs/pool/results.csv",
                        "docs/validation/2026-11-01_colab_records.md", "designs/pool_sobol96.csv"]},
    "S18": {"title": "Pareto front with uncertainty", "body": body_s18,
            "sources": ["runs/analysis/2026-11-02/pareto_front.png", "runs/analysis/2026-11-02/pareto.csv",
                        "docs/validation/2026-11-02_pareto_inverse.md (section 2)"]},
    "S19": {"title": "Inverse query under a heat-flux cap", "body": body_s19,
            "sources": ["runs/analysis/2026-11-02/inverse_q40/result.json", "runs/confirm/inlet2r-374dad241f/result.json",
                        "runs/analysis/2026-11-02/confirm/confirm.json", "docs/validation/2026-11-02_pareto_inverse.md (section 3)"]},
    "S20": {"title": "Design maps over the box", "body": body_s20,
            "sources": ["runs/analysis/2026-11-02/design_map.png", "runs/analysis/2026-11-02/oswatitsch_cut.png",
                        "runs/analysis/2026-11-02/grid.csv", "docs/validation/2026-11-02_pareto_inverse.md (section 4)"]},
    "S21": {"title": "What failed, in order", "body": body_s21,
            "sources": ["runs/dev/2026-11-01_cylinder_v3_attempt1/README.md", "runs/dev/2026-11-01_cylinder_v3_attempt3/README.md",
                        "runs/dev/2026-11-01_numerics/README.md",
                        "runs/dev/2026-11-01_inlet_grid_study_ef03/README.md", "docs/faults/README.md",
                        "runs/pool/inlet2r-db92dcf68d/error.json (commit 915f5f8)",
                        "docs/transcripts/2026-11-02_worker_restart_and_retry.md"]},
    "S22": {"title": "Limits of the model", "body": body_s22,
            "sources": ["runs/dev/2026-11-01_inlet_grid_study_ef03/README.md", "runs/dev/2026-11-01_numerics/README.md",
                        "runs/dev/2026-11-01_turbulence_sensitivity_SA/README.md",
                        "docs/validation/2026-11-02_pareto_inverse.md (section 2)"]},
    "S23": {"title": "What is still to be recorded", "body": body_s23,
            "sources": [REPORT, "docs/validation/2026-11-01_colab_records.md", "docs/faults/fault_matrix.md",
                        "docs/validation/2026-11-02_replay.md", "docs/validation/2026-11-02_pareto_inverse.md",
                        "runs/analysis/2026-11-02/confirm/confirm.json", "docs/validation/2026-11-02_sa_sensitivity.md"]},
    "S24": {"title": "Questions, and where the answers are", "body": body_s24, "sources": []},
    "B1": {"title": "Backup: turbulence model", "body": body_b1,
           "sources": ["runs/sensitivity/results.csv", "docs/validation/2026-11-02_sa_sensitivity.md",
                       "runs/dev/2026-11-01_turbulence_sensitivity_SA/README.md"]},
    "B2": {"title": "Backup: wall boundary condition", "body": body_b2,
           "sources": ["runs/dev/2026-11-01_numerics/README.md",
                       "runs/dev/2026-11-01_numerics/wedge-381c48d17f-tecplot/surface_flow.dat.gz"]},
    "B3": {"title": "Backup: mesh convergence", "body": body_b3,
           "sources": [REPORT, "runs/dev/2026-11-01_inlet_grid_study_ef03/README.md", "runs/dev/2026-11-01_inlet_grid_study_ef03/8_8_medium/mesh_quality.json"]},
    "B4": {"title": "Backup: the numerics story", "body": body_b4,
           "sources": ["runs/dev/2026-11-01_numerics/README.md", "runs/dev/2026-11-01_cylinder_v3_attempt2/README.md",
                       "runs/dev/2026-11-01_cylinder_v3_attempt3/README.md",
                       "runs/dev/2026-11-01_cylinder_v3_attempt2/schemes/*/surface_flow.dat.gz"]},
    "B5": {"title": "Backup: design-box trim", "body": body_b5,
           "sources": ["runs/dev/2026-11-01_inlet_box_diagnostics/README.md",
                       "runs/dev/2026-11-01_inlet_grid_study_ef03/README.md", "designs/pool_sobol96.csv"]},
    "B6": {"title": "Backup: full validation table", "body": body_b6, "sources": [REPORT]},
}

# deck order: (section divider title, sub line, slide ids)
SECTIONS = [
    ("1. Problem and why it matters", "4 minutes", ["S1", "S2", "S3"]),
    ("2. Physics setup and validation", "9 minutes", ["S4", "S5", "S6", "S7", "S8"]),
    ("3. Automation layer: MCP tools, gates, queue", "6 minutes", ["S9", "S10", "S11", "S12"]),
    ("4. Surrogate, active learning, UQ", "9 minutes", ["S13", "S14", "S15", "S16"]),
    ("5. Results, Pareto front, inverse query", "7 minutes", ["S17", "S18", "S19", "S20"]),
    ("6. What failed, limits, next steps", "5 minutes", ["S21", "S22", "S23"]),
    ("Discussion", "about 20 minutes, outside the 40", ["S24"]),
    ("Backup", "not timed", ["B1", "B2", "B3", "B4", "B5", "B6"]),
]


def build(out_path=DEFAULT_OUT):
    """Build the deck and save it to out_path. Returns the number of slides."""
    del USED_FIGURES[:]
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    outline = read_outline()
    prs = new_deck()
    for section_title, sub, ids in SECTIONS:
        add_divider_slide(prs, section_title, sub)
        for sid in ids:
            number = len(prs.slides) + 1
            info = outline[sid]
            if sid == "S1":
                add_title_slide(prs, number, "Aero-thermal inlet design: surrogate and automation", info["message"],
                                ["Mach 4 at 30 km, two-ramp inlet, two design variables.",
                                 "Status 2026-11-02: every number comes from a record in this repository; "
                                 "the confirmation run passed (C2)."], info["notes"])
                continue
            spec = SLIDES[sid]
            slide = start_slide(prs, number, sid, spec["title"], info["message"], spec["sources"], info["notes"])
            spec["body"](slide)
    prs.save(str(out_path))
    return len(prs.slides)


if __name__ == "__main__":
    n = build()
    print(f"wrote {DEFAULT_OUT.relative_to(ROOT)} with {n} slides")

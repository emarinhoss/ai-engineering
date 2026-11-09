"""LaTeX equations on slides: render with matplotlib mathtext, place as a picture.

python-pptx has no native equation object and this machine has no TeX install, so each equation
is written as LaTeX source, drawn by matplotlib's own mathtext (text.usetex = False, Computer
Modern glyphs) to a transparent PNG, and the PNG goes on the slide at its natural size (so the
type size on the slide is the fontsize given here, in points). Anything mathtext cannot parse, or
draws with a missing glyph, raises: a slide never carries a half-rendered equation.

    render(latex, path=None, fontsize=22, dpi=300) -> Path   file name = sha1 of source and size
    add_equation(slide, latex, x, y, max_w, max_h, fontsize=22) -> (w, h) in inches
    placed_on(slide) -> [(latex, png bytes)] for the equation pictures of a slide (the alt text is the source)
"""
import hashlib
import re
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import rc_context
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image
from pptx.util import Inches

EQ_DIR = Path(__file__).resolve().parent / "figures" / "eq"
COLOR = "#222222"                      # the deck's body text color
PICTURE_NAME = "Equation"              # shape name of an equation picture; its alt text is the LaTeX


def eq_path(latex, fontsize=22, dpi=300):
    """Deterministic file name: the same source, size and dpi always give the same path."""
    key = hashlib.sha1(f"{latex}|{fontsize}|{dpi}".encode()).hexdigest()[:16]
    return EQ_DIR / f"eq_{key}.png"


def render(latex, path=None, fontsize=22, dpi=300):
    """Draw `latex` (no surrounding dollar signs) to a transparent PNG; skip if it exists.

    Raises ValueError on a mathtext parse error and on any warning raised while drawing (a missing
    glyph, say), and nothing is written in that case.
    """
    path = Path(path) if path is not None else eq_path(latex, fontsize, dpi)
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = Figure(figsize=(1, 1), dpi=dpi)
    FigureCanvasAgg(fig)
    fig.patch.set_alpha(0.0)
    fig.text(0, 0, f"${latex}$", fontsize=fontsize, color=COLOR)
    tmp = path.with_suffix(".tmp.png")
    try:
        with rc_context({"text.usetex": False, "mathtext.fontset": "cm"}), \
                warnings.catch_warnings():
            warnings.simplefilter("error")
            fig.savefig(tmp, dpi=dpi, bbox_inches="tight", pad_inches=0.03, transparent=True,
                        format="png")
    except Exception as exc:                              # parse error or warning-as-error
        tmp.unlink(missing_ok=True)
        raise ValueError(f"mathtext cannot render {latex!r}: {exc}") from exc
    tmp.replace(path)
    return path


def add_equation(slide, latex, x, y, max_w, max_h, fontsize=22, align="left"):
    """Render and place the equation at (x, y) inches, natural size, shrunk only to fit the box.

    align "left" puts the picture's left edge at x, "center" centers it in max_w. Returns the
    picture's (width, height) in inches.
    """
    path = render(latex, fontsize=fontsize)
    with Image.open(path) as im:
        w, h = im.size[0] / 300.0, im.size[1] / 300.0       # render's dpi is the default, 300
    scale = min(1.0, max_w / w, max_h / h)
    w, h = w * scale, h * scale
    left = x + (max_w - w) / 2 if align == "center" else x
    pic = slide.shapes.add_picture(str(path), Inches(left), Inches(y), Inches(w), Inches(h))
    pic.name = PICTURE_NAME
    pic._element.nvPicPr.cNvPr.set("descr", latex)         # alt text: the source stays readable and testable
    return w, h


def placed_on(slide):
    """[(LaTeX, PNG bytes)] of the equation pictures on a slide, in z-order."""
    return [(sh._element.nvPicPr.cNvPr.get("descr"), sh.image.blob)
            for sh in slide.shapes if sh.shape_type == 13 and sh.name == PICTURE_NAME]


def outline_equations(line):
    """LaTeX sources of an outline line `- **Equations:** $...$; $...$`, or None for other lines.

    Sources must not contain a dollar sign; the semicolons between entries are outside the dollars.
    """
    tag = "- **Equations:** "
    if not line.startswith(tag):
        return None
    return re.findall(r"\$(.+?)\$", line[len(tag):])

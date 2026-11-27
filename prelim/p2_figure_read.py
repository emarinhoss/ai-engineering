"""Preliminary design P2: tools used to check the digitized NACA 4415 points against the figure of NACA Report
824, printed page 142 (data/task12/pd_p2_section_source.yaml, figure_check).

The scan is not committed. To repeat the check, download the report (the source record has the URL and sha256)
and render the page:  pdftoppm -f 144 -l 144 -r 300 -gray -png report.pdf page   then
    python -m prelim.p2_figure_read page-144.png
It prints, for the lift and the drag plot, how far each digitized point lies from the centroid of the symbol
beside it. Needs Pillow and scipy, which nothing else in prelim/ uses. Reading by eye is not reproduced here.
"""
import sys

import numpy as np

from prelim import p2_section as p2

LEFT_BOX, RIGHT_BOX = (600, 1900, 250, 2400), (1950, 3200, 640, 2400)     # pixel boxes (x0, x1, y0, y1) at 300 dpi
ALPHA_LINES = list(np.arange(-32.0, 33.0, 2.0))                           # left plot: vertical grid lines, deg
CL_LINES = list(np.round(np.arange(3.6, -2.01, -0.1), 1))                 # left plot: horizontal grid lines
CL_LINES_RIGHT = list(np.round(np.arange(-1.4, 1.81, 0.1), 1))            # right plot: vertical grid lines
CD_LINES = list(np.round(np.arange(0.026, -0.0005, -0.001), 3))           # right plot: the 27 lines down to zero drag


def load_dark(path):
    """True where the scan is dark."""
    from PIL import Image
    return np.array(Image.open(path).convert("L")) < 128


def line_positions(counts, threshold):
    """Centres of the runs of indices whose dark-pixel count is above the threshold (the grid lines)."""
    idx = [i for i in range(len(counts)) if counts[i] > threshold]
    out, group = [], [idx[0]]
    for i in idx[1:]:
        if i - group[-1] <= 2:
            group.append(i)
        else:
            out.append(sum(group) / len(group))
            group = [i]
    return out + [sum(group) / len(group)]


def grid_lines(dark, box, fraction=0.5):
    """Pixel positions of the vertical and the horizontal grid lines inside box: columns and rows that are dark
    over more than `fraction` of the box."""
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    return ([x + x0 for x in line_positions(sub.sum(0), fraction * sub.shape[0])],
            [y + y0 for y in line_positions(sub.sum(1), fraction * sub.shape[1])])


def symbol_interiors(dark, box, area=(25, 260), size=20):
    """(x, y, area) of each small enclosed white region inside box: the inside of a plotted symbol."""
    from scipy import ndimage
    x0, x1, y0, y1 = box
    labels, _ = ndimage.label(~dark[y0:y1, x0:x1])
    out = []
    for i, sl in enumerate(ndimage.find_objects(labels), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        n = int((labels[sl] == i).sum())
        if area[0] <= n <= area[1] and w <= size and h <= size:
            cy, cx = ndimage.center_of_mass(labels[sl] == i)
            out.append((cx + sl[1].start + x0, cy + sl[0].start + y0, n))
    return out


def compare(points, interiors, x_lines, x_values, y_lines, y_values, window=9, min_area=90):
    """For each digitized (set, x, y): the centroid of the one symbol interior of at least min_area pixels within
    `window` pixels, in axis units. Points with none or several are left out (overlapping or cut symbols)."""
    out = []
    for k, x, y in points:
        px = float(np.interp(x, x_values, x_lines))
        py = float(np.interp(y, y_values[::-1], y_lines[::-1]))
        near = [h for h in interiors if abs(h[0] - px) <= window and abs(h[1] - py) <= window and h[2] >= min_area]
        if len(near) == 1:
            out.append((k, x, y, float(np.interp(near[0][0], x_lines, x_values)), float(np.interp(near[0][1], y_lines, y_values))))
    return out


def main(path):
    dark, data = load_dark(path), p2.load_section(p2.WING_SECTION)
    xs, ys = grid_lines(dark, LEFT_BOX)
    assert (len(xs), len(ys)) == (len(ALPHA_LINES), len(CL_LINES)), "left grid not found"
    lift = [(k, a, c) for k in (1, 2, 3, 4) for a, c in data["alpha_cl"][k]]
    m = compare(lift, symbol_interiors(dark, (640, 1840, 300, 2360)), xs, ALPHA_LINES, ys, CL_LINES)
    da, dc = np.array([r[1] - r[3] for r in m]), np.array([r[2] - r[4] for r in m])
    print(f"lift: {len(m)} of {len(lift)} points matched; digitized minus centroid: angle rms {np.sqrt((da ** 2).mean()):.3f} "
          f"max {abs(da).max():.3f} deg; lift rms {np.sqrt((dc ** 2).mean()):.4f} max {abs(dc).max():.4f}")
    for k in (1, 2, 3, 4):
        top = max(data["alpha_cl"][k], key=lambda q: q[1])
        print(f"  set {k}: highest digitized point {top}; centroid", [(round(r[3], 2), round(r[4], 3)) for r in m if r[0] == k and r[1] == top[0]])
    xs, ys = grid_lines(dark, RIGHT_BOX)
    ys = ys[:len(CD_LINES)]
    assert len(xs) == len(CL_LINES_RIGHT), "right grid not found"
    drag = [(k, c, cd) for k in (1, 2, 3, 4) for c, cd in data["cl_cd"][k]]
    m = compare(drag, symbol_interiors(dark, (1960, 3180, 650, 1640)), xs, CL_LINES_RIGHT, ys, CD_LINES)
    dx, dy = np.array([r[1] - r[3] for r in m]), np.array([r[2] - r[4] for r in m])
    print(f"drag: {len(m)} of {len(drag)} points matched; digitized minus centroid: lift rms {np.sqrt((dx ** 2).mean()):.4f}; "
          f"drag rms {np.sqrt((dy ** 2).mean()):.5f} max {abs(dy).max():.5f}")


if __name__ == "__main__":
    main(sys.argv[1])

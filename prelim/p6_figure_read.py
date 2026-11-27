"""Preliminary design P6: the tool behind the "code" readings of NACA Report 640 Figs. 2 and 12
(data/task12/pd_p6_propeller_source.yaml, blade_geometry and efficiency).

The scans are not committed. To repeat the readings, download the report (the source record has the URL and
sha256), render the two pages and run:
    pdftoppm -r 300 -f 6 -l 6 -png report.pdf p     pdftoppm -r 300 -f 11 -l 11 -png report.pdf p
    python -m prelim.p6_figure_read p-06.png p-11.png
It prints, for every row of the source record, the code reading beside the recorded ones. A curve is read at a
station as a straight line fitted through its crossings of up to ten pixel columns either side of the station; the
trial value that tells the code which curve is meant is the recorded eye reading for Fig. 2 and the recorded code
reading for Fig. 12 (first found from trial values read off the plot to two figures; where curves lie close, another
trial can land on a neighbour, which is why every code reading was also looked at on an enlarged tile). The grid
positions below were measured on these scans (both pages are slightly skewed). Needs Pillow, which nothing else in prelim/ uses.
Reading by eye is not reproduced here.
"""
import sys

import numpy as np
import yaml

from prelim import p6_propeller as p6

# Fig. 2 (PDF page 6), crop x 170..1299, y 1435..2801. Vertical grid lines r/R = 0.20, 0.25, ..., 0.95 at the top
# (y 212) and at the bottom (y 1225) of the plot; horizontal lines every interval from zero upwards at x 247.
F2_BOX = (170, 1435, 1299, 2801)
F2_V_TOP = [232.5, 282.5, 333.5, 382.5, 432.5, 482.5, 532.5, 583.0, 632.5, 682.5, 733.5, 783.0, 833.0, 883.5, 934.5, 984.0]
F2_V_BOTTOM = [235.5, 285.5, 335.0, 385.5, 435.0, 485.5, 535.0, 585.5, 636.0, 685.5, 735.5, 786.5, 835.5, 886.5, 936.5, 986.5]
F2_H = [1300.5, 1252.0, 1201.5, 1151.5, 1103.5, 1052.5, 1003.5, 954.5, 904.5, 854.5, 805.5, 756.5, 706.5, 657.5, 608.5, 558.5,
        509.5, 459.5, 410.5, 359.5, 309.5, 260.0, 210.5, 162.5, 114.5]
F2_H_SLOPE = -1.2 / 722.0                 # the horizontal lines rise by about 1.2 px from x 247 to x 970
F2_UNIT = {"b_over_D": 0.005, "h_over_b": 0.02, "pitch_set_25": 0.1, "pitch_set_15": 0.1}       # value of one grid interval
# Fig. 12 (PDF page 11), crop x 171..2332, y 2360..3249. The scale is taken from the inner grid lines.
F12_BOX = (171, 2360, 2332, 3249)


def load_dark(path, box):
    from PIL import Image
    im = np.array(Image.open(path).convert("L"))
    return im[box[1]:box[3], box[0]:box[2]] < 150


def crossings(dark, x, y0, y1):
    """Centres of the dark runs of column x between rows y0 and y1."""
    out, start = [], None
    for y in range(max(y0, 0), min(y1, dark.shape[0] - 1)):
        if dark[y, x]:
            start = y if start is None else start
            last = y
        elif start is not None:
            out.append((start + last) / 2.0)
            start = None
    return out


def fit(points, tolerance):
    """Value at the station of a straight line through (offset from the station, value) points; the worst point is
    dropped while it is further than `tolerance` from the line and more than four are left. None with fewer than four."""
    if len(points) < 4:
        return None
    xs, vs = np.array([p[0] for p in points]), np.array([p[1] for p in points])
    while True:
        k = np.polyfit(xs, vs, 1)
        res = np.abs(vs - np.polyval(k, xs))
        if res.max() <= tolerance or len(xs) <= 4:
            return float(k[1]), float(res.max()), len(xs)
        keep = res < res.max()
        xs, vs = xs[keep], vs[keep]


# ---- Fig. 2
def f2_x(x_station, y):
    k = (x_station - 0.2) / 0.05
    i = max(0, min(int(k), 14))
    top = F2_V_TOP[i] + (k - i) * (F2_V_TOP[i + 1] - F2_V_TOP[i])
    bottom = F2_V_BOTTOM[i] + (k - i) * (F2_V_BOTTOM[i + 1] - F2_V_BOTTOM[i])
    return top + (bottom - top) * (y - 212.0) / 1013.0


def f2_y(intervals, x):
    i = max(0, min(int(intervals), 23))
    return F2_H[i] + (intervals - i) * (F2_H[i + 1] - F2_H[i]) + F2_H_SLOPE * (x - 247.0)


def f2_intervals(x, y):
    ys = [h + F2_H_SLOPE * (x - 247.0) for h in F2_H]
    for i in range(24):
        if ys[i] >= y >= ys[i + 1]:
            return i + (ys[i] - y) / (ys[i] - ys[i + 1])
    return float("nan")


def read_fig2(dark, x_station, trial, unit, half=0.45):
    """The curve near `trial` at this r/R: (value, largest residual, columns used) or None. Crossings within 3 px of a
    horizontal grid line are left out."""
    points = []
    for d in (-20, -17, -14, -11, -8, 8, 11, 14, 17, 20):
        y_trial = f2_y(trial / unit, f2_x(x_station, 700.0))
        x = int(round(f2_x(x_station, y_trial))) + d
        if not 0 <= x < dark.shape[1]:
            continue
        ys = [y for y in crossings(dark, x, int(y_trial - half * 49.4), int(y_trial + half * 49.4) + 2)
              if min(abs(y - (h + F2_H_SLOPE * (x - 247.0))) for h in F2_H) >= 3.0]
        if ys:
            y = min(ys, key=lambda v: abs(v - y_trial))
            points.append((x - f2_x(x_station, y), f2_intervals(x, y) * unit))
    return fit(points, 0.06 * unit)


# ---- Fig. 12
def f12_x(J, y):
    """The V/nD = 0.1 grid line is at x 158.0 (y 80) and 157.5 (y 710); 68.20 and 68.41 px per 0.1."""
    f = (y - 80.0) / 630.0
    return (158.0 - 0.5 * f) + (J - 0.1) * 10.0 * (68.20 + 0.21 * f)


def f12_lines(x):
    """Rows of the eta = 0.9 and eta = 0.1 grid lines at column x."""
    return 115.5 - 0.01136 * (x - 125.0), 664.0 - 0.0125 * (x - 125.0)


def f12_eta(x, y):
    y9, y1 = f12_lines(x)
    return 0.9 - (y - y9) / (y1 - y9) * 0.8


def read_fig12(dark, J, trial, half=0.035):
    """The efficiency curve near `trial` at this V/nD: (value, largest residual, columns used) or None. Crossings
    within 0.004 of a grid line of eta are left out."""
    y9, y1 = f12_lines(f12_x(J, 400.0))
    y_trial = y9 + (0.9 - trial) / 0.8 * (y1 - y9)
    points = []
    for d in (-24, -20, -16, -12, -8, 8, 12, 16, 20, 24):
        x = int(round(f12_x(J, y_trial))) + d
        etas = [(y, f12_eta(x, y)) for y in crossings(dark, x, 20, 735)]
        etas = [(y, e) for y, e in etas if abs(e - trial) < half and abs(((e * 10.0) % 1.0) - 0.5) < 0.46]
        if etas:
            y, e = min(etas, key=lambda q: abs(q[0] - y_trial))
            points.append((x - f12_x(J, y), e))
    return fit(points, 0.004)


def main(page6, page11):
    src = yaml.safe_load(p6.SOURCE.read_text())
    dark = load_dark(page6, F2_BOX)
    for name, unit in F2_UNIT.items():
        for row in src["blade_geometry"][name]:
            trial = row[1] if row[1] is not None else row[3]
            r = read_fig2(dark, row[0], trial, unit) or read_fig2(dark, row[0], trial, unit, half=0.9)
            print(f"Fig. 2  {name:13s} r/R {row[0]:.2f}: recorded {row[1:]}  code now "
                  + ("none" if r is None else f"{r[0]:.5f} (residual {r[1]:.5f}, {r[2]} columns)"))
    dark = load_dark(page11, F12_BOX)
    for angle in p6.ROW5_ANGLES:
        for row in src["efficiency"][f"blade_angle_{angle}"]:
            r = read_fig12(dark, row[0], row[1]) or read_fig12(dark, row[0], row[1], half=0.09)
            print(f"Fig. 12 {angle} deg V/nD {row[0]:.2f}: recorded {row[1:]}  code now "
                  + ("none" if r is None else f"{r[0]:.4f} (residual {r[1]:.4f}, {r[2]} columns)"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

"""Check of the vortex lattice's ground effect against two book relations (review S3M-9, owner ruling G-7).

    python -m measurement.ground_effect_validation --out runs/task12/stage3/<date>/<run>/ground_effect_validation.json

The quantity is the induced-drag ratio in ground effect over free air at equal CL (the same call as
tests/task12/test_ground_effect.py), at h/b 0.1, 0.2, 0.3 and 0.5 on the test wing (span 40 ft, A 10,
taper 0.45, medium lattice). References, both fixed before the second one was added:
- Anderson (6.77) p. 357: G = (16 h/b)^2/(1 + (16 h/b)^2)   (measurement/anderson.py);
- Raymer (12.61) p. 304: K_eff/K = 33 (h/b)^1.5/(1 + 33 (h/b)^1.5).
Tolerance +-15 % of the reference at every h/b, fixed in advance; a row outside is reported, not tuned.
The two books differ from each other; the record gives that difference too.
"""
import argparse
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

from drone import geometry, vlm
from measurement.anderson import ground_effect_factor

REPO = Path(__file__).resolve().parents[1]
SPAN, ASPECT, TAPER, LEVEL = 40.0, 10.0, 0.45, "medium"
ALPHA = math.radians(4.0)
H_OVER_B = (0.1, 0.2, 0.3, 0.5)
TOLERANCE = 0.15


def raymer_ground_effect_factor(h_over_b):
    """K_effective/K = 33 (h/b)^1.5 / (1 + 33 (h/b)^1.5), Raymer (12.61) p. 304."""
    x = 33.0 * h_over_b ** 1.5
    return x / (1.0 + x)


def lattice_drag_ratios(h_over_b=H_OVER_B):
    """Near-field induced drag in ground effect over free air at equal CL: CDi/CL^2 at one angle (a flat
    wing has CL ~ alpha and CDi ~ alpha^2), ground plane at h = (h/b) span."""
    pf = geometry.tapered(SPAN, ASPECT, TAPER)
    free = vlm.solve(pf, ALPHA, LEVEL)
    k_free = free["CDi_nearfield"] / free["CL"] ** 2
    out = {}
    for hb in h_over_b:
        g = vlm.solve(pf, ALPHA, LEVEL, ground_h=hb * SPAN)
        out[hb] = (g["CDi_nearfield"] / g["CL"] ** 2) / k_free
    return out


def verdict_text(rows):
    """One sentence from the rows: for each reference how many h/b values are inside the tolerance, and the
    difference between the two books at the smallest h/b. Generated, so it follows the numbers."""
    n = len(rows)
    ok_a = sum(r["within_anderson"] for r in rows)
    ok_r = sum(r["within_raymer"] for r in rows)
    first = rows[0]
    return (f"inside +-{TOLERANCE * 100:.0f} % of Raymer (12.61) at {ok_r} of {n} h/b values and of Anderson (6.77) at "
            f"{ok_a} of {n}; the two books differ by {abs(first['raymer_over_anderson'] - 1.0) * 100:.0f} % at "
            f"h/b {first['h_over_b']}. The references were fixed in advance, so a row outside is reported, not tuned")


def compute():
    ratios = lattice_drag_ratios()
    rows = []
    for hb, lat in ratios.items():
        ga, gr = ground_effect_factor(hb), raymer_ground_effect_factor(hb)
        da, dr = lat / ga - 1.0, lat / gr - 1.0
        rows.append({"h_over_b": hb, "lattice_induced_drag_ratio": lat,
                     "anderson_G_6_77": ga, "raymer_12_61": gr,
                     "deviation_anderson": da, "deviation_raymer": dr,
                     "within_anderson": abs(da) <= TOLERANCE, "within_raymer": abs(dr) <= TOLERANCE,
                     "raymer_over_anderson": gr / ga})
    return {"what": "ground-effect model check, the same call as tests/task12/test_ground_effect.py",
            "wing": {"span_ft": SPAN, "aspect_ratio": ASPECT, "taper": TAPER, "lattice": LEVEL,
                     "alpha_deg": math.degrees(ALPHA)},
            "tolerance": TOLERANCE, "rows": rows, "verdict": verdict_text(rows)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    res = compute()
    res["inputs"] = {"commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                              check=False, cwd=REPO).stdout.strip(),
                     "python": platform.python_version(), "numpy": np.__version__, "seed": None,
                     "command": "python -m measurement.ground_effect_validation " + " ".join(sys.argv[1:] if argv is None else argv)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    for r in res["rows"]:
        print(f"h/b {r['h_over_b']}: lattice {r['lattice_induced_drag_ratio']:.3f}, Anderson {r['anderson_G_6_77']:.3f} "
              f"({r['deviation_anderson'] * 100:+.1f} %), Raymer {r['raymer_12_61']:.3f} ({r['deviation_raymer'] * 100:+.1f} %)")
    print(res["verdict"])


if __name__ == "__main__":
    main()

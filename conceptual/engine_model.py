"""A fixed engine described by a table: full-throttle shaft power and part-power SFC against
altitude, true airspeed and power fraction. For the TP100 the table is generated from the
Mattingly App. K cycle (python -m measurement.tp100_engine data/task12/tp100_table.json) so the
sizing loop does not run the cycle itself. Linear interpolation; inputs are clamped to the table.
"""
import json
from pathlib import Path

import numpy as np

TP100_TABLE = Path(__file__).resolve().parents[1] / "data" / "task12" / "tp100_table.json"


def _locate(axis, x):
    """Index i and weight t with x = axis[i] + t (axis[i+1] - axis[i]), clamped."""
    x = min(max(x, axis[0]), axis[-1])
    i = min(int(np.searchsorted(axis, x, side="right")) - 1, len(axis) - 2)
    return i, (x - axis[i]) / (axis[i + 1] - axis[i])


class TableEngine:
    def __init__(self, path=TP100_TABLE):
        t = json.loads(Path(path).read_text())
        self.h = np.array(t["h_ft"])
        self.v = np.array(t["V_kt"])
        self.f = np.array(t["power_fraction"])
        self.p_full = np.array(t["full_throttle_shp"])
        self.sfc = np.array(t["bsfc"])
        self.rated = t["rated_shp"]
        self.meta = {k: t[k] for k in ("member", "calibration_bsfc", "control_law")}

    def power_available(self, h_ft, V_kt):
        """Full-throttle shaft hp (bilinear in altitude and speed)."""
        i, a = _locate(self.h, h_ft)
        j, b = _locate(self.v, V_kt)
        p = self.p_full
        return float((1 - a) * ((1 - b) * p[i, j] + b * p[i, j + 1])
                     + a * ((1 - b) * p[i + 1, j] + b * p[i + 1, j + 1]))

    def lapse(self, h_ft, V_kt):
        """Full-throttle power over the rated sea-level value."""
        return self.power_available(h_ft, V_kt) / self.rated

    def bsfc(self, h_ft, V_kt, shp):
        """Shaft SFC, lb/(hp h), at a shaft power. Raises ValueError above full throttle; below the
        table's lowest fraction (0.10) the lowest fraction's value is used (optimistic)."""
        avail = self.power_available(h_ft, V_kt)
        frac = shp / avail
        if frac > 1.0 + 1e-6:
            raise ValueError(f"{shp:.1f} hp exceeds the {avail:.1f} hp available")
        i, a = _locate(self.h, h_ft)
        j, b = _locate(self.v, V_kt)
        k, c = _locate(self.f, frac)
        s = self.sfc
        out = 0.0
        for di, wi in ((0, 1 - a), (1, a)):
            for dj, wj in ((0, 1 - b), (1, b)):
                for dk, wk in ((0, 1 - c), (1, c)):
                    out += wi * wj * wk * s[i + di, j + dj, k + dk]
        return float(out)

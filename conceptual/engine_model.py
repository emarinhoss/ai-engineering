"""A fixed engine described by a table: full-throttle shaft power and part-power SFC against
altitude, true airspeed and power fraction. For the TP100 the table is generated from the
Mattingly App. K cycle (python -m measurement.tp100_engine data/task12/tp100_table.json) so the
sizing loop does not run the cycle itself. Linear interpolation; inputs are clamped to the table.
"""
import copy
import json
from pathlib import Path

import numpy as np

TP100_TABLE = Path(__file__).resolve().parents[1] / "data" / "task12" / "tp100_table.json"


def table_for_run(run_dir):
    """Path of the engine table a Stage 1 run used: the copy in the run folder if there is one,
    else the committed table at the run's recorded commit if its hash differs from the current file
    (read with `git show`), else the current file. Raises if the recorded hash cannot be matched."""
    import hashlib
    import subprocess
    import tempfile
    run_dir = Path(run_dir)
    if (run_dir / "tp100_table.json").exists():
        return run_dir / "tp100_table.json"
    inp = json.loads((run_dir / "inputs.json").read_text())
    want = inp.get("tp100_table_sha256")
    if want is None or hashlib.sha256(TP100_TABLE.read_bytes()).hexdigest() == want:
        return TP100_TABLE
    repo = TP100_TABLE.parents[2]
    blob = subprocess.run(["git", "show", f"{inp['commit']}:data/task12/tp100_table.json"], cwd=repo,
                          capture_output=True, check=True).stdout
    if hashlib.sha256(blob).hexdigest() != want:
        raise ValueError(f"no engine table with the recorded hash for {run_dir}")
    out = Path(tempfile.mkdtemp()) / "tp100_table.json"
    out.write_bytes(blob)
    return out


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
        self.sfc_scale, self.power_scale = 1.0, 1.0
        self.lp_ratio = np.array(t["lp_turbine_pressure_ratio"])
        self.crit = t["critical_pressure_ratio"]
        self.hp_ratio = t["hp_turbine_pressure_ratio"]

    def scaled(self, sfc=1.0, power=1.0):
        """A copy with every SFC and every full-throttle power multiplied (band-end trades)."""
        out = copy.copy(self)
        out.sfc_scale, out.power_scale = self.sfc_scale * sfc, self.power_scale * power
        return out

    def power_available(self, h_ft, V_kt):
        """Full-throttle shaft hp (bilinear in altitude and speed), capped at the rated power: the
        brochure gives 241 hp as the maximum output, so ram recovery above it (the cycle reaches
        about 250 hp at 140 kt at sea level) is not credited (Gate A round 4, R4-1)."""
        return min(self.rated, self._full_throttle(h_ft, V_kt)) * self.power_scale

    def _full_throttle(self, h_ft, V_kt):
        """Uncapped full-throttle shaft hp of the cycle: the reference for the table's fractions."""
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
        if shp > avail * (1.0 + 1e-6):
            raise ValueError(f"{shp:.1f} hp exceeds the {avail:.1f} hp available")
        frac = shp / (self._full_throttle(h_ft, V_kt) * self.power_scale)
        i, a = _locate(self.h, h_ft)
        j, b = _locate(self.v, V_kt)
        k, c = _locate(self.f, frac)
        s = self.sfc
        out = 0.0
        for di, wi in ((0, 1 - a), (1, a)):
            for dj, wj in ((0, 1 - b), (1, b)):
                for dk, wk in ((0, 1 - c), (1, c)):
                    out += wi * wj * wk * s[i + di, j + dj, k + dk]
        return float(out) * self.sfc_scale

    def turbine_choked(self, h_ft, V_kt, shp):
        """Whether the App. K choked-turbine assumption holds at this point: the LP turbine pressure
        ratio (nearest table cell) at or above the critical ratio (Gate A round 4, R4-4)."""
        i = int(np.abs(self.h - h_ft).argmin())
        j = int(np.abs(self.v - V_kt).argmin())
        k = int(np.abs(self.f - shp / (self._full_throttle(h_ft, V_kt) * self.power_scale)).argmin())
        return bool(self.lp_ratio[i, j, k] >= self.crit), float(self.lp_ratio[i, j, k])

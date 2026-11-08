"""Section data (lift and profile drag of the wing section) at low fidelity or from a polar."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from drone import drag, naca


@dataclass
class SectionData:
    cl_max: float
    alpha_L0: float                      # radians
    cd_of_cl: callable
    source: str
    flags: list = field(default_factory=list)
    cl_alpha_per_deg: float | None = None


def low_fidelity(camber_pct, thickness_pct, reynolds, fixed):
    """Section from thin-airfoil theory with a lift-effectiveness factor.

    cl_max = k_eff 2 pi (alpha_stall - alpha_L0). Profile drag is a constant, 2 cf FF (both
    surfaces, form factor from t/c). The lift dependence of profile drag is absent at this level;
    that is a named bias (spec section 13), not an oversight.
    """
    rules = fixed["rules"]
    k_eff = rules["section_lift_effectiveness"]
    alpha_l0 = naca.zero_lift_angle(camber_pct)
    alpha_stall = math.radians(rules["section_stall_angle_deg"])
    cl_max = k_eff * 2.0 * math.pi * (alpha_stall - alpha_l0)
    tc = thickness_pct / 100.0
    ff = 1.0 + rules["wing_form_factor_k1"] * tc + rules["wing_form_factor_k2"] * tc**4
    cd_p0 = 2.0 * drag.cf(reynolds) * ff

    def cd_of_cl(cl):
        return np.full_like(np.asarray(cl, dtype=float), cd_p0)[()]

    return SectionData(
        cl_max=float(cl_max), alpha_L0=float(alpha_l0), cd_of_cl=cd_of_cl,
        source=f"low_fidelity(camber={camber_pct}, thickness={thickness_pct}, Re={reynolds:.3g})",
        cl_alpha_per_deg=float(k_eff * 2.0 * math.pi * math.pi / 180.0))


def from_polar(alpha_deg, cl, cd, source):
    """Section from a measured or computed polar (alpha in degrees)."""
    alpha = np.asarray(alpha_deg, dtype=float)
    cl = np.asarray(cl, dtype=float)
    cd = np.asarray(cd, dtype=float)
    order = np.argsort(alpha)
    alpha, cl, cd = alpha[order], cl[order], cd[order]
    i_max = int(np.argmax(cl))
    cl_max = float(cl[i_max])
    flags = ["not_peaked"] if i_max == len(cl) - 1 else []
    use = cl < 0.85 * cl_max
    if use.sum() < 2:
        use = np.ones_like(cl, dtype=bool)
    slope, intercept = np.polyfit(alpha[use], cl[use], 1)
    alpha_l0 = math.radians(-intercept / slope)
    cl_up, cd_up = cl[: i_max + 1], cd[: i_max + 1]
    o = np.argsort(cl_up)
    cl_up, cd_up = cl_up[o], cd_up[o]

    def cd_of_cl(c):
        return np.interp(c, cl_up, cd_up)

    return SectionData(cl_max=cl_max, alpha_L0=float(alpha_l0), cd_of_cl=cd_of_cl,
                       source=source, flags=flags, cl_alpha_per_deg=float(slope))

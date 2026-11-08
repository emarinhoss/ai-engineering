"""Mission closed forms: power required, stall speed, endurance, cruise point (spec section 3).

Pure functions, SI units. The cruise point is found on the design's own drag polar, supplied by
drone/evaluate.py as a callable CL -> CD.
"""
import math

import numpy as np

from drone import ledger

_G = ledger.load("air")["gravity_m_s2"]
_N_CL = 400            # points of the CL scan in cruise_point (numerical setting of the task brief)
_CL_SCAN_MIN = 0.05    # lowest CL scanned; far below any minimum-power or best-L/D CL


def power_required(D, V, eta_p):
    """Shaft-to-air power: P = D V / eta_p."""
    return D * V / eta_p


def v_stall(m, S, cl_max, rho, g=_G):
    """Stall speed: V_s = sqrt(2 m g / (rho S CL_max))."""
    return math.sqrt(2.0 * m * g / (rho * S * cl_max))


def endurance_h(m_batt, E_spec_Wh_kg, dod, eta_p, P_cruise_W, P_installed_W, t_climb_s):
    """Endurance in hours: (DoD E_spec 3600 m_b - P_installed t_climb) / P_cruise / 3600.

    The take-off and climb allowance t_climb is spent at installed power. eta_p is accepted for the
    interface only: P_cruise and P_installed are already battery-side powers (D V / eta_p), so the
    efficiency is inside them and is not applied again here.
    """
    usable_J = dod * E_spec_Wh_kg * 3600.0 * m_batt - P_installed_W * t_climb_s
    return usable_J / P_cruise_W / 3600.0


def cruise_point(polar, W, S, rho, cl_max_wing, fixed):
    """Minimum-power point and best-L/D point of the polar, scanned on 400 CL values.

    CL runs from 0.05 to CL_top = min(CL_max / stall_margin^2, cruise_cl_fraction_of_clmax CL_max):
    the first bound is V >= stall_margin V_stall (V scales as 1/sqrt(CL)), the second is gate 2's
    cruise-CL limit. At each CL: V = sqrt(2 W / (rho S CL)), D = 1/2 rho V^2 S CD, P = D V / eta_p.
    If the unconstrained minimum-power CL lies above CL_top the minimum lands on CL_top, which is
    V_cruise = max(V_minpower, stall_margin V_stall) of spec section 2.

    Returns {"min_power": {CL, V, CD, D, P}, "best_ld": {CL, V, L_over_D}}.
    """
    rules = fixed["rules"]
    eta_p = fixed["propulsion"]["propulsive_efficiency"]
    cl_top = min(cl_max_wing / rules["stall_margin"] ** 2,
                 rules["cruise_cl_fraction_of_clmax"] * cl_max_wing)
    cls = np.linspace(_CL_SCAN_MIN, cl_top, _N_CL)
    v = np.sqrt(2.0 * W / (rho * S * cls))
    cd = np.array([polar(float(c)) for c in cls])
    d = 0.5 * rho * v**2 * S * cd
    p = power_required(d, v, eta_p)
    i = int(np.argmin(p))
    j = int(np.argmax(cls / cd))
    return {
        "min_power": {"CL": float(cls[i]), "V": float(v[i]), "CD": float(cd[i]), "D": float(d[i]),
                      "P": float(p[i])},
        "best_ld": {"CL": float(cls[j]), "V": float(v[j]), "L_over_D": float(cls[j] / cd[j])},
    }

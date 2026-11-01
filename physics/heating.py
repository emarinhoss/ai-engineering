"""Analytic wall heating references: Eckert flat plate (V2b) and Fay-Riddell cylinder (V3).

Calorically perfect air; all constants come from physics.constants. SI units throughout.
"""
import math

import numpy as np

from physics.constants import CP, GAMMA, PR, R_AIR, sutherland_mu


def eckert_flat_plate(Me, Te, pe, Tw, x):
    """Laminar flat-plate heat flux [W/m^2] by Eckert's reference temperature.

    Me, Te, pe: boundary-layer edge Mach number, temperature [K], pressure [Pa].
    Tw: wall temperature [K]. x: distance from the leading edge [m] (float or numpy array).

    r = sqrt(Pr);  T_aw = Te (1 + r (gamma-1)/2 Me^2)
    T*  = 0.5 (Te + Tw) + 0.22 (T_aw - Te)
    rho* = pe / (R T*),  mu* = Sutherland(T*),  ue = Me sqrt(gamma R Te)
    Re*_x = rho* ue x / mu*
    St = 0.332 Re*_x^(-1/2) Pr^(-2/3)
    q  = St rho* ue cp (T_aw - Tw)
    """
    r = math.sqrt(PR)
    Taw = Te * (1.0 + r * (GAMMA - 1.0) / 2.0 * Me**2)
    Tstar = 0.5 * (Te + Tw) + 0.22 * (Taw - Te)
    rho = pe / (R_AIR * Tstar)
    mu = sutherland_mu(Tstar)
    ue = Me * math.sqrt(GAMMA * R_AIR * Te)
    Re = rho * ue * np.asarray(x, dtype=float) / mu
    St = 0.332 * Re**-0.5 * PR ** (-2.0 / 3.0)
    return St * rho * ue * CP * (Taw - Tw)


def billig_standoff(M):
    """Shock stand-off distance over the body radius for a cylinder (Billig):
    delta / R = 0.386 exp(4.67 / M^2)."""
    return 0.386 * math.exp(4.67 / M**2)


def fay_riddell_cylinder(M_inf, T_inf, p_inf, Tw, R):
    """Stagnation-point heat flux on a cylinder of radius R [m] (Fay-Riddell). Returns a dict.

    p02 = pitot pressure behind a normal shock (Rayleigh pitot formula):
        p_inf [(g+1) M^2 / 2]^(g/(g-1)) / [2 g M^2/(g+1) - (g-1)/(g+1)]^(1/(g-1))
    T0 = T_inf (1 + (g-1)/2 M^2)
    rho_e = p02 / (R_air T0), mu_e = Sutherland(T0)       (edge = stagnation state)
    rho_w = p02 / (R_air Tw), mu_w = Sutherland(Tw)
    du_e/dx = (1/R) sqrt(2 (p02 - p_inf) / rho_e)         (modified Newtonian gradient)
    q = 0.57 Pr^-0.6 (rho_e mu_e)^0.4 (rho_w mu_w)^0.1 sqrt(du_e/dx) cp (T0 - Tw)

    0.57 is the two-dimensional (cylinder) constant; the axisymmetric (sphere) value is 0.763.
    The Lewis-number term is dropped, which is exact for a perfect gas (no dissociation).
    Also returned: h0_minus_hw = cp (T0 - Tw).
    """
    g, M2 = GAMMA, M_inf**2
    p02 = p_inf * ((g + 1.0) * M2 / 2.0) ** (g / (g - 1.0)) / (
        2.0 * g * M2 / (g + 1.0) - (g - 1.0) / (g + 1.0)) ** (1.0 / (g - 1.0))
    T0 = T_inf * (1.0 + (g - 1.0) / 2.0 * M2)
    rho_e, mu_e = p02 / (R_AIR * T0), sutherland_mu(T0)
    rho_w, mu_w = p02 / (R_AIR * Tw), sutherland_mu(Tw)
    dudx = math.sqrt(2.0 * (p02 - p_inf) / rho_e) / R
    h0_minus_hw = CP * (T0 - Tw)
    q = 0.57 * PR**-0.6 * (rho_e * mu_e) ** 0.4 * (rho_w * mu_w) ** 0.1 * math.sqrt(dudx) * h0_minus_hw
    return {"q": q, "dudx": dudx, "p02": p02, "rho_e": rho_e, "mu_e": mu_e,
            "rho_w": rho_w, "mu_w": mu_w, "h0_minus_hw": h0_minus_hw, "T0": T0}

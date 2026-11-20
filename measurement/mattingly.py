"""Mattingly, Aircraft Engine Design, 2nd ed.: constraint master equation (ch. 2), mission weight
fractions (ch. 3) and propeller momentum theory (App. L), in fps units.

Mattingly writes these for thrust engines with a thrust-specific fuel consumption (TSFC, 1/h).
For the turboprop the conversions used are stated where they enter: installed thrust from shaft
power, T = 550 eta_p P / V, and the equivalent TSFC, C = C_bhp V/(550 eta_p).
"""
import math

from conceptual.units import HP, G


# ---- constraint analysis, ch. 2 --------------------------------------------------------------
def master_thrust_loading(W_S, q, beta, alpha, K1, K2, CD0, CDR=0.0, n=1.0, Ps=0.0, V=1.0):
    """T_SL/W_TO from the master equation (2.11), p. 24: beta = W/W_TO, alpha = T/T_SL (lapse),
    n load factor, Ps = dh/dt + (V/g) dV/dt (ft/s), V flight speed (ft/s)."""
    x = n * beta / q * W_S
    return beta / alpha * (q / (beta * W_S) * (K1 * x ** 2 + K2 * x + CD0 + CDR) + Ps / V)


def shaft_power_loading(W_S, q, V, beta, power_lapse, K1, K2, CD0, eta_p, CDR=0.0, n=1.0, Ps=0.0):
    """Sea-level shaft hp per lb of W_TO for a propeller aircraft: (2.11) with the thrust lapse
    replaced by the power lapse and T = 550 eta_p P/V (the conversion is the study's, stated)."""
    t_w = master_thrust_loading(W_S, q, beta, 1.0, K1, K2, CD0, CDR, n, Ps, V)
    return t_w * V / (HP * eta_p) / power_lapse


def turn_load_factor(turn_rate, V):
    """n = sqrt(1 + (Omega V/g0)^2) (2.16), p. 27."""
    return math.sqrt(1.0 + (turn_rate * V / G) ** 2)


# ---- mission analysis, ch. 3 -----------------------------------------------------------------
def equivalent_tsfc(cbhp_per_hr, V, eta_p):
    """TSFC (1/h) of a propeller engine, C = C_bhp V/(550 eta_p); the study's conversion for using
    Mattingly's thrust-engine weight fractions."""
    return cbhp_per_hr * V / (HP * eta_p)


def cruise_fraction(tsfc_per_hr, CD_over_CL, distance_ft, V):
    """W_f/W_i = exp(-TSFC (C_D/C_L) Delta s / V) (3.23), p. 63, with TSFC = (C1/M + C2) a_std /
    a_std ... written here directly in TSFC and V."""
    return math.exp(-(tsfc_per_hr / 3600.0) * CD_over_CL * distance_ft / V)


def loiter_fraction(tsfc_per_hr, CD_over_CL, time_s):
    """W_f/W_i = exp(-Delta t/EF), EF = (C_L/C_D)/TSFC ((3.36)-(3.37)), p. 66-67."""
    EF = (1.0 / CD_over_CL) / (tsfc_per_hr / 3600.0)
    return math.exp(-time_s / EF)


def climb_fraction(tsfc_per_hr, V, delta_ze, u):
    """Climb or climb-and-accelerate, W_f/W_i = exp{-TSFC Delta z_e /(V (1 - u))} ((3.17), (3.20)),
    p. 61-62, with u = (D/W)(W/T) the fraction of thrust work dissipated."""
    return math.exp(-(tsfc_per_hr / 3600.0) * delta_ze / (V * (1.0 - u)))


# ---- propeller momentum theory, App. L ---------------------------------------------------------
def actuator_disk_efficiency(thrust, rho, V, disk_area):
    """Ideal propulsive efficiency from the thrust loading: C_T* = T/(rho V^2 A_p/2) and
    C_T* = 4(1 - eta*)/eta*^2 ((L.8), p. 612) solved for eta*."""
    ct = thrust / (0.5 * rho * V ** 2 * disk_area)
    # ct eta^2 + 4 eta - 4 = 0
    return (-4.0 + math.sqrt(16.0 + 16.0 * ct)) / (2.0 * ct) if ct > 0 else 1.0


def ideal_coefficients(eta):
    """C_T* = 4(1-eta)/eta^2 (L.8) and C_P* = 4(1-eta)/eta^3 (L.9), p. 612; V_e/V_0 = 2/eta - 1
    from (L.7)."""
    return {"C_T": 4.0 * (1.0 - eta) / eta ** 2, "C_P": 4.0 * (1.0 - eta) / eta ** 3,
            "Ve_over_V0": 2.0 / eta - 1.0}


def real_propeller_efficiency(thrust, rho, V, diameter, real_to_ideal=0.85):
    """Real efficiency as a fraction of the ideal; Mattingly App. L, p. 609-613: real propellers
    reach about 85 % of the ideal (blade drag, swirl, non-uniform wake)."""
    return real_to_ideal * actuator_disk_efficiency(thrust, rho, V, math.pi * diameter ** 2 / 4.0)

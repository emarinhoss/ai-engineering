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


# ---- take-off, ch. 2 cases 5-6 (p. 28-31) ----------------------------------------------------
def takeoff_ground_roll_thrust_limited(W_S, rho, CL_max, k_TO, T_W, beta=1.0, alpha=1.0, g=G):
    """s_G from (2.22) solved for the ground roll (T >> D + R), p. 29:
    T_SL/W_TO = beta^2/alpha k_TO^2/(s_G rho g CL_max) (W_TO/S)."""
    return beta ** 2 / alpha * k_TO ** 2 * W_S / (T_W * rho * g * CL_max)


def takeoff_ground_roll(W_S, rho, CL_max, k_TO, T_W, mu, xi, beta=1.0, alpha=1.0, g=G):
    """s_G = -beta (W/S)/(rho g xi) ln{1 - xi/[(alpha/beta T/W - mu) CL_max/k_TO^2]} (2.25), p. 29,
    with xi_TO = C_D + C_DR - mu C_L (2.24). Raises if the thrust cannot reach V_TO."""
    margin = alpha / beta * T_W - mu
    if margin <= 0.0:
        raise ValueError("thrust does not overcome rolling friction")
    arg = 1.0 - xi / (margin * CL_max / k_TO ** 2)
    if arg <= 0.0:
        raise ValueError("thrust cannot accelerate the aircraft to the take-off speed")
    return -beta * W_S / (rho * g * xi) * math.log(arg)


def takeoff_V(W_S, rho, CL_max, k_TO, beta=1.0):
    """V_TO = k_TO V_STALL (2.20), p. 28, with V_STALL from beta W/S = q CL_max (p. 29)."""
    return k_TO * math.sqrt(2.0 * beta * W_S / (rho * CL_max))


def rotation_distance(V_TO, t_R):
    """s_R = t_R V_TO (2.26), p. 30; t_R is 3 s 'normally' in the book."""
    return t_R * V_TO


def transition_and_climb(V_TO, k_TO, sin_theta_CL, h_obs, g=G):
    """Transition and climb after rotation, p. 30-31. n - 1 = 0.8 k_TO^2 - 1 and R_c = V_TO^2/(g(n-1)).
    If the obstacle is cleared after the arc (h_TR < h_obs): s_TR (2.27), h_TR (2.29), s_CL (2.28);
    otherwise s_obs (2.30) with theta_obs = acos(1 - h_obs/R_c). Returns (distance ft, case)."""
    n_minus_1 = 0.8 * k_TO ** 2 - 1.0
    if n_minus_1 <= 0.0:
        raise ValueError("0.8 k_TO^2 - 1 must be positive (2.27); k_TO >= 1.12")
    R_c = V_TO ** 2 / (g * n_minus_1)
    theta = math.asin(sin_theta_CL)
    h_TR = R_c * (1.0 - math.cos(theta))
    if h_TR < h_obs:
        return R_c * sin_theta_CL + (h_obs - h_TR) / math.tan(theta), "A"
    return R_c * math.sin(math.acos(1.0 - h_obs / R_c)), "B"


def takeoff_distance(W, S, rho, CD0, K, CL_max, thrust_of_V, mu=0.03, CL_ground=0.1, k_TO=1.2,
                     t_R=1.0, h_obs=50.0, g=G):
    """s_TO = s_G + s_R + (s_TR + s_CL or s_obs), Fig. 2.7a/b p. 30-31. Ground roll by (2.25) with
    T at 0.7 V_TO (the 0.7 rule is Anderson's p. 360; Mattingly states no speed) and
    xi_TO = C_D + C_DR - mu C_L with C_D = CD0 + K CL_ground^2 (C_DR = 0). Climb angle
    sin(theta_CL) = (T - D)/W (2.2a, p. 30) at V_TO with C_L = CL_max/k_TO^2. k_TO = 1.2 is the book's
    own value (p. 43): at the usual 1.1 the factor 0.8 k^2 - 1 of (2.27) is negative."""
    W_S = W / S
    V_TO = takeoff_V(W_S, rho, CL_max, k_TO)
    xi = CD0 + K * CL_ground ** 2 - mu * CL_ground                       # (2.24)
    s_G = takeoff_ground_roll(W_S, rho, CL_max, k_TO, thrust_of_V(0.7 * V_TO) / W, mu, xi, g=g)
    s_R = rotation_distance(V_TO, t_R)
    CL = CL_max / k_TO ** 2
    D = 0.5 * rho * V_TO ** 2 * S * (CD0 + K * CL ** 2)
    sin_theta = (thrust_of_V(V_TO) - D) / W
    if sin_theta <= 0.0:
        raise ValueError("no climb gradient after lift-off")
    s_air, case = transition_and_climb(V_TO, k_TO, min(sin_theta, 0.5), h_obs, g)
    return {"V_TO": V_TO, "ground_roll": s_G, "rotation": s_R, "airborne": s_air, "case": case,
            "total": s_G + s_R + s_air}


def takeoff_power(field_ft, thrust_factory, W, S, rho, CD0, K, CL_max, mu=0.03, CL_ground=0.1,
                  k_TO=1.2, t_R=1.0, h_obs=50.0):
    """Smallest shaft hp whose take-off distance (takeoff_distance above) is within field_ft, by
    bisection. thrust_factory(hp) returns the function T(V) for that power."""
    def dist(hp):
        try:
            return takeoff_distance(W, S, rho, CD0, K, CL_max, thrust_factory(hp), mu, CL_ground,
                                    k_TO, t_R, h_obs)["total"]
        except ValueError:
            return float("inf")

    lo, hi = 10.0, 20000.0
    if dist(hi) > field_ft:
        return float("inf")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if dist(mid) > field_ft else (lo, mid)
    return hi


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

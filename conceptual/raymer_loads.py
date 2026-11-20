"""Gust and manoeuvre loads (Raymer ch. 14). Speeds in ft/s, W/S in lb/ft^2."""
from conceptual.units import RHO0, G


def gust_mass_ratio(W_S, rho, mac, CL_alpha):
    """mu = 2 (W/S)/(rho g c CL_alpha) (14.8), p. 339."""
    return 2.0 * W_S / (rho * G * mac * CL_alpha)


def gust_alleviation_subsonic(mu):
    """K = 0.88 mu/(5.3 + mu) (14.6), p. 339."""
    return 0.88 * mu / (5.3 + mu)


def gust_load_factor(W_S, V_eas, U_de, CL_alpha, mac, rho_alt):
    """1 + Delta n with Delta n = rho0 U V CL_alpha/(2 W/S) ((14.4)-(14.5)), U = K U_de.

    U_de and V are equivalent airspeeds (p. 339), so sea-level density multiplies them in (14.4);
    the mass ratio (14.8) uses the density at altitude. Returns (n_gust, K, mu)."""
    mu = gust_mass_ratio(W_S, rho_alt, mac, CL_alpha)
    K = gust_alleviation_subsonic(mu)
    dn = RHO0 * K * U_de * V_eas * CL_alpha / (2.0 * W_S)
    return 1.0 + dn, K, mu


def design_gust_velocity(V_eas, V_cruise_eas, V_dive_eas, U_cruise=30.0, U_dive=15.0):
    """Civil normal-category rule (p. 339): U_de = 30 ft/s up to cruise speed, falling linearly to
    15 ft/s at the dive speed."""
    if V_eas <= V_cruise_eas:
        return U_cruise
    frac = min(1.0, (V_eas - V_cruise_eas) / (V_dive_eas - V_cruise_eas))
    return U_cruise + frac * (U_dive - U_cruise)


def ultimate_load_factor(n_limit, factor_of_safety=1.5):
    """Ultimate = 1.5 times limit (p. 340)."""
    return factor_of_safety * n_limit

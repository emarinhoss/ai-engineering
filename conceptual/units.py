"""Units and the standard atmosphere in Raymer's foot-pound-second units.

Raymer works in ft, lb, slug, s, knots and nautical miles. Everything inside conceptual/ stays in
those units; records also carry SI values converted here.
"""
import math

G = 32.174                 # ft/s^2, standard gravity
KT = 1.68781               # ft/s per knot (Raymer rounds to 1.689)
NM = 6076.12               # ft per nautical mile (Raymer uses 6076)
FT = 0.3048                # m per ft
LB = 0.45359237            # kg per lb (mass)
HP = 550.0                 # ft lb/s per horsepower
GAL_FT3 = 231.0 / 1728.0   # ft^3 per US gallon (Raymer p. 227: one gallon = 231 cubic inches)

# ISA sea level (US Standard Atmosphere 1976 troposphere), fps units
T0_R = 518.67              # deg R
P0 = 2116.22               # lb/ft^2
RHO0 = 0.0023769           # slug/ft^3
LAPSE_R_PER_FT = 0.00356616
TROPOPAUSE_FT = 36089.0
R_AIR = 1716.49            # ft lb/(slug R)
GAMMA = 1.4


R_EARTH_FT = 20855531.0     # effective Earth radius of the 1976 standard (6,356.766 km)


def isa(h_ft):
    """ISA state at geometric altitude h_ft (0 to 65,000 ft): dict T (R), p, rho, a, mu, sigma.

    The geometric altitude is converted to geopotential, z = r0 h / (r0 + h), which is what the
    1976 standard's layers are written in.
    Troposphere: T = T0 - L h, p = p0 (T/T0)^(g/(L R)); above the tropopause T is constant and p
    falls exponentially. Not from the library; checked against Mattingly App. B (delta and theta at
    20 kft, p. 511) in tests/task12/test_units.py. Viscosity by Sutherland's law.
    """
    if not 0.0 <= h_ft <= 65000.0:
        raise ValueError(f"altitude {h_ft} ft outside 0 to 65,000 ft")
    h_ft = R_EARTH_FT * h_ft / (R_EARTH_FT + h_ft)          # geopotential
    n = G / (LAPSE_R_PER_FT * R_AIR)
    if h_ft <= TROPOPAUSE_FT:
        T = T0_R - LAPSE_R_PER_FT * h_ft
        p = P0 * (T / T0_R) ** n
    else:
        T = T0_R - LAPSE_R_PER_FT * TROPOPAUSE_FT
        p11 = P0 * (T / T0_R) ** n
        p = p11 * math.exp(-G * (h_ft - TROPOPAUSE_FT) / (R_AIR * T))
    rho = p / (R_AIR * T)
    TK = T / 1.8
    mu_si = 1.458e-6 * TK ** 1.5 / (TK + 110.4)          # Pa s, Sutherland
    mu = mu_si * 0.020885434                               # slug/(ft s)
    return {"T": T, "p": p, "rho": rho, "a": math.sqrt(GAMMA * R_AIR * T), "mu": mu,
            "sigma": rho / RHO0}

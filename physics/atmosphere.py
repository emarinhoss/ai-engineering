"""Freestream state from the US Standard Atmosphere 1976.

Tabulated altitudes (physics.constants.ATMOSPHERE_TABLE) return the table values exactly, so every
existing run keeps its freestream. Other altitudes from 20 to 47 km use the 1976 formula for the two
layers with a constant temperature gradient (Task 9, docs/specs/task9_inlet3r_envelope.md):

    H = r0 z / (r0 + z)                       geopotential altitude, r0 = 6356.766 km
    T = T_b + L (H - H_b)
    p = p_b (T_b / T)^(g0 M0 / (R* L))        g0 M0 / R* = 34.1632 K/km
"""
import math

from physics.constants import ATMOSPHERE_TABLE, GAMMA, R_AIR, sutherland_mu

R0_KM = 6356.766                   # effective Earth radius of the 1976 standard, km
GMR = 34.1632                      # g0 M0 / R*, K/km
# (base geopotential altitude km, base temperature K, lapse rate K/km, base pressure Pa)
LAYERS = ((20.0, 216.65, 1.0, 5474.889), (32.0, 228.65, 2.8, 868.0187))


def ussa1976(altitude_km):
    """(T, p) from the 1976 formula for a geometric altitude of 20 to 47 km."""
    H = R0_KM * altitude_km / (R0_KM + altitude_km)
    if not 20.0 <= H <= 47.0:
        raise ValueError(f"altitude {altitude_km} km is outside the 20 to 47 km layers of this formula")
    Hb, Tb, L, pb = LAYERS[0] if H < 32.0 else LAYERS[1]
    T = Tb + L * (H - Hb)
    return T, pb * (Tb / T) ** (GMR / L)


def state(altitude_km):
    """Return dict(T, p, rho, a, mu) at an altitude in km.

    rho = p / (R T); a = sqrt(gamma R T); mu from Sutherland's law. A tabulated altitude returns the
    table values; any other altitude from 20 to 47 km uses ussa1976.
    """
    if altitude_km in ATMOSPHERE_TABLE:
        T, p = ATMOSPHERE_TABLE[altitude_km]["T"], ATMOSPHERE_TABLE[altitude_km]["p"]
    else:
        T, p = ussa1976(float(altitude_km))
    return {
        "T": T,
        "p": p,
        "rho": p / (R_AIR * T),
        "a": math.sqrt(GAMMA * R_AIR * T),
        "mu": sutherland_mu(T),
    }

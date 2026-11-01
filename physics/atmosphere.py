"""Freestream state from the tabulated US Standard Atmosphere 1976."""
import math

from physics.constants import ATMOSPHERE_TABLE, GAMMA, R_AIR, sutherland_mu


def state(altitude_km):
    """Return dict(T, p, rho, a, mu) at a tabulated altitude.

    rho = p / (R T); a = sqrt(gamma R T); mu from Sutherland's law.
    Raises KeyError for altitudes that are not in the table.
    """
    if altitude_km not in ATMOSPHERE_TABLE:
        raise KeyError(
            f"altitude {altitude_km} km is not tabulated; available: {sorted(ATMOSPHERE_TABLE)}"
        )
    T = ATMOSPHERE_TABLE[altitude_km]["T"]
    p = ATMOSPHERE_TABLE[altitude_km]["p"]
    return {
        "T": T,
        "p": p,
        "rho": p / (R_AIR * T),
        "a": math.sqrt(GAMMA * R_AIR * T),
        "mu": sutherland_mu(T),
    }

"""Single source of physical constants. No other file may redefine these."""
import math

GAMMA = 1.4
R_AIR = 287.058                    # J/kg/K
CP = GAMMA * R_AIR / (GAMMA - 1.0)  # J/kg/K, about 1004.7
PR = 0.72                          # laminar Prandtl number

# Sutherland viscosity law
MU_REF = 1.716e-5   # Pa s
T_REF = 273.15      # K
S_SUTH = 110.4      # K

# US Standard Atmosphere 1976, keyed by altitude in km
ATMOSPHERE_TABLE = {30: {"T": 226.509, "p": 1197.03}}


def sutherland_mu(T):
    """Dynamic viscosity [Pa s]: mu = MU_REF (T/T_REF)^1.5 (T_REF + S)/(T + S)."""
    return MU_REF * (T / T_REF) ** 1.5 * (T_REF + S_SUTH) / (T + S_SUTH)


assert math.isclose(CP, 1004.703, rel_tol=1e-6)

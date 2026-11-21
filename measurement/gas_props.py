"""Variable-specific-heat gas properties for the MSH fuel-flow model (Mattingly, Aircraft Engine
Design 2nd ed., Section 4.2.8): sensible enthalpy of air and of the combustion products of C12H23.

Data: NASA 7-coefficient polynomials (two temperature ranges) for N2, O2, Ar, CO2, H2O, copied
exactly from Cantera's open file data/gri30.yaml (GRI-Mech 3.0, BSD-style open data, which takes
them from the NASA / Burcat thermodynamic databases). Only a1..a6 are needed for enthalpy:
    h/(R T) = a1 + a2 T/2 + a3 T^2/3 + a4 T^3/4 + a5 T^4/5 + a6/T        (T in K)
Sensible enthalpy = h(T) - h(298.15 K) = h(T) - h(536.67 R), the reference where h_PR is defined.

Units out: Btu/lbm and Btu/(lbm R). Temperatures in deg R.
"""

R_UNIVERSAL = 8314.462618      # J/(kmol K)
T_REF_K = 298.15               # = 536.67 R
BTU_PER_LBM_IN_J_PER_KG = 2326.0   # 1 Btu/lbm = 2326 J/kg (exact, International Table Btu)

# (T_low, T_mid, T_high), coefficients a1..a6 for the low range then the high range.
_NASA = {
    "N2": ((300.0, 1000.0, 5000.0),
           (3.298677, 1.4082404e-03, -3.963222e-06, 5.641515e-09, -2.444854e-12, -1020.8999),
           (2.92664, 1.4879768e-03, -5.68476e-07, 1.0097038e-10, -6.753351e-15, -922.7977)),
    "O2": ((200.0, 1000.0, 3500.0),
           (3.78245636, -2.99673416e-03, 9.84730201e-06, -9.68129509e-09, 3.24372837e-12, -1063.94356),
           (3.28253784, 1.48308754e-03, -7.57966669e-07, 2.09470555e-10, -2.16717794e-14, -1088.45772)),
    "Ar": ((300.0, 1000.0, 5000.0),
           (2.5, 0.0, 0.0, 0.0, 0.0, -745.375),
           (2.5, 0.0, 0.0, 0.0, 0.0, -745.375)),
    "CO2": ((200.0, 1000.0, 3500.0),
            (2.35677352, 8.98459677e-03, -7.12356269e-06, 2.45919022e-09, -1.43699548e-13, -48371.9697),
            (3.85746029, 4.41437026e-03, -2.21481404e-06, 5.23490188e-10, -4.72084164e-14, -48759.166)),
    "H2O": ((200.0, 1000.0, 3500.0),
            (4.19864056, -2.0364341e-03, 6.52040211e-06, -5.48797062e-09, 1.77197817e-12, -30293.7267),
            (3.03399249, 2.17691804e-03, -1.64072518e-07, -9.7041987e-11, 1.68200992e-14, -30004.2971)),
}

# Molar masses in kg/kmol from atomic masses (C 12.011, H 1.008, N 14.007, O 15.999, Ar 39.948).
M_C, M_H = 12.011, 1.008
MOLAR_MASS = {"N2": 2 * 14.007, "O2": 2 * 15.999, "Ar": 39.948,
              "CO2": M_C + 2 * 15.999, "H2O": 2 * M_H + 15.999}
M_FUEL = 12 * M_C + 23 * M_H          # C12H23

# Standard dry air by mole fraction (the usual textbook composition).
AIR_MOLE = {"N2": 0.78084, "O2": 0.20946, "Ar": 0.00934, "CO2": 0.00036}


def _coeffs(species, T):
    (_t_lo, t_mid, _t_hi), low, high = _NASA[species]
    return low if T < t_mid else high


def _h_molar(species, T):
    """Absolute molar enthalpy, J/kmol, at T in K."""
    a1, a2, a3, a4, a5, a6 = _coeffs(species, T)
    x = a1 + a2 * T / 2 + a3 * T ** 2 / 3 + a4 * T ** 3 / 4 + a5 * T ** 4 / 5 + a6 / T
    return x * R_UNIVERSAL * T


def _cp_molar(species, T):
    """Molar cp, J/(kmol K): cp/R = a1 + a2 T + a3 T^2 + a4 T^3 + a5 T^4."""
    a1, a2, a3, a4, a5, _ = _coeffs(species, T)
    return (a1 + a2 * T + a3 * T ** 2 + a4 * T ** 3 + a5 * T ** 4) * R_UNIVERSAL


def _h_sensible_molar(species, T):
    return _h_molar(species, T) - _h_molar(species, T_REF_K)


def _mix_mass(moles):
    return sum(n * MOLAR_MASS[s] for s, n in moles.items())


def _air_moles():
    """Moles of each species per kg of air."""
    m_air = sum(x * MOLAR_MASS[s] for s, x in AIR_MOLE.items())   # kg/kmol of mixture
    return {s: x / m_air for s, x in AIR_MOLE.items()}


def _products_moles(f):
    """Moles per kg of AIR of the products of burning f kg of C12H23 per kg of air.
    CO2 +12 n, H2O +11.5 n, O2 -(12 + 11.5/2) n, with n = f / M_FUEL. Lean only."""
    n_fuel = f / M_FUEL
    moles = _air_moles()
    moles["CO2"] += 12.0 * n_fuel
    moles["H2O"] = moles.get("H2O", 0.0) + 11.5 * n_fuel
    moles["O2"] -= (12.0 + 11.5 / 2.0) * n_fuel
    if moles["O2"] < 0.0:
        raise ValueError(f"fuel/air ratio {f} is richer than stoichiometric (O2 would go negative)")
    return moles


def h_air(T_R):
    """Sensible enthalpy of dry air, Btu/lbm, relative to 536.67 R."""
    T = T_R / 1.8
    moles = _air_moles()
    h = sum(n * _h_sensible_molar(s, T) for s, n in moles.items())     # J per kg of air
    return h / BTU_PER_LBM_IN_J_PER_KG


def cp_air(T_R):
    """Specific heat of dry air, Btu/(lbm R)."""
    T = T_R / 1.8
    cp = sum(n * _cp_molar(s, T) for s, n in _air_moles().items())      # J/(kg K)
    return cp / BTU_PER_LBM_IN_J_PER_KG / 1.8                             # per R: 1 K = 1.8 R


def h_products(T_R, f):
    """Sensible enthalpy, Btu/lbm of products (mass 1 + f per unit air), relative to 536.67 R."""
    T = T_R / 1.8
    moles = _products_moles(f)
    h = sum(n * _h_sensible_molar(s, T) for s, n in moles.items())     # J per kg of air
    return h / (1.0 + f) / BTU_PER_LBM_IN_J_PER_KG


def fuel_air_msh(T_t3, T_t4, eta_b, h_PR, tol=1e-12):
    """Burner fuel/air ratio from the energy balance (4.10a) with variable-cp enthalpies:
        f = (h_t4(T_t4, f) - h_t3(T_t3)) / (eta_b h_PR - h_t4(T_t4, f)),   fixed-point iteration on f."""
    h3 = h_air(T_t3)
    f = 0.0
    for _ in range(100):
        h4 = h_products(T_t4, f)
        f_new = (h4 - h3) / (eta_b * h_PR - h4)
        if abs(f_new - f) < tol:
            return f_new
        f = f_new
    raise ValueError("fuel_air_msh did not converge")

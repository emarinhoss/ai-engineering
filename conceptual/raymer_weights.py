"""Component weights, general-aviation statistical group weights (Raymer 15.3, eqs. 15.46-15.59,
p. 404-405) and composite fudge factors (Table 15.4, p. 408). Weights lb, areas ft^2,
lengths ft unless noted. N_z is the ultimate load factor; W_dg the design gross weight."""
import math

# Table 15.4, p. 408: advanced composites
COMPOSITE_FUDGE = {"wing": 0.85, "tails": 0.83, "fuselage": 0.90, "landing_gear": 0.95,
                   "air_induction": 0.85}


def wing(S_w, W_fw, A, sweep, q, taper, t_c, Nz, Wdg):
    """(15.46). W_fw: weight of fuel in the wing; sweep in rad (quarter chord)."""
    c = math.cos(sweep)
    return (0.036 * S_w ** 0.758 * W_fw ** 0.0035 * (A / c ** 2) ** 0.6 * q ** 0.006
            * taper ** 0.04 * (100.0 * t_c / c) ** -0.3 * (Nz * Wdg) ** 0.49)


def horizontal_tail(Nz, Wdg, q, S_ht, t_c, A_ht, sweep_ht, taper_h):
    """(15.47)."""
    c = math.cos(sweep_ht)
    return (0.016 * (Nz * Wdg) ** 0.414 * q ** 0.168 * S_ht ** 0.896 * (100.0 * t_c / c) ** -0.12
            * (A_ht / c ** 2) ** 0.043 * taper_h ** -0.02)


def vertical_tail(Ht_Hv, Nz, Wdg, q, S_vt, t_c, A_vt, sweep_vt, taper_vt):
    """(15.48). Ht_Hv = 0 for a conventional tail, 1 for a T-tail."""
    c = math.cos(sweep_vt)
    return (0.073 * (1.0 + 0.2 * Ht_Hv) * (Nz * Wdg) ** 0.376 * q ** 0.122 * S_vt ** 0.873
            * (100.0 * t_c / c) ** -0.49 * (A_vt / c ** 2) ** 0.357 * taper_vt ** 0.039)


def fuselage(S_f, Nz, Wdg, L_t, L_over_D, q, W_press=0.0):
    """(15.49). S_f fuselage wetted area; L_t tail arm (ft); L/D fuselage fineness."""
    return (0.052 * S_f ** 1.086 * (Nz * Wdg) ** 0.177 * L_t ** -0.051 * L_over_D ** -0.072
            * q ** 0.241 + W_press)


def main_gear(Nl, Wl, Lm_in):
    """(15.50). N_l ultimate landing load factor (1.5 times gear load factor), W_l landing
    weight, L_m main gear length in inches."""
    return 0.095 * (Nl * Wl) ** 0.768 * (Lm_in / 12.0) ** 0.409


def nose_gear(Nl, Wl, Ln_in):
    """(15.51)."""
    return 0.125 * (Nl * Wl) ** 0.566 * (Ln_in / 12.0) ** 0.845


def installed_engine(W_en, N_en=1):
    """(15.52): installed engine total weight from uninstalled weight."""
    return 2.575 * W_en ** 0.922 * N_en


def fuel_system(V_t_gal, V_i_gal, N_t, N_en=1):
    """(15.53). V_t total fuel volume (gal), V_i integral-tank volume (gal), N_t number of tanks."""
    return (2.49 * V_t_gal ** 0.726 * (1.0 / (1.0 + V_i_gal / V_t_gal)) ** 0.363 * N_t ** 0.242
            * N_en ** 0.157)


def flight_controls(L_fus, B_w, Nz, Wdg):
    """(15.54). L fuselage structural length, B_w wing span (ft)."""
    return 0.053 * L_fus ** 1.536 * B_w ** 0.371 * (Nz * Wdg * 1e-4) ** 0.80


def hydraulics(Wdg):
    """(15.55)."""
    return 0.001 * Wdg


def electrical(W_fuel_system, W_avionics):
    """(15.56)."""
    return 12.57 * (W_fuel_system + W_avionics) ** 0.51


def avionics(W_uav):
    """(15.57): installed avionics from uninstalled avionics weight."""
    return 2.117 * W_uav ** 0.933

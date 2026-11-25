"""Anderson, Aircraft Performance and Design ("Anderson APD"): propeller-airplane sizing (ch. 8) and
performance (ch. 5-6), in fps units. Used in Stage 3 as a second route beside Raymer.

Note on independence: Anderson's first weight estimate uses his own historical empty fraction
(8.5); his refined build-up (8.83a-g) is Raymer's approximate group-weight table (Table 15.2), so it
is a same-author cross-check, not an independent one.
"""
import math

from conceptual.units import G

EMPTY_FRACTION_HISTORICAL = 0.62     # (8.5), p. 400: piston propeller airplanes, Fig. 8.1
CFE_PROPELLER = 0.0043               # (8.40), p. 414: equivalent skin friction of Anderson's propeller airplane


def takeoff_weight(fixed_weight, fuel_fraction, empty_fraction):
    """W0 = (W_crew + W_payload)/(1 - Wf/W0 - We/W0) (8.4), p. 399."""
    return fixed_weight / (1.0 - fuel_fraction - empty_fraction)


def fuel_fraction(segment_fractions):
    """Wf/W0 = 1.06 (1 - W_end/W0) (8.6)-(8.8), p. 402."""
    w = 1.0
    for f in segment_fractions:
        w *= f
    return 1.06 * (1.0 - w)


def breguet_cruise_fraction(range_ft, c_per_s, eta_pr, LD):
    """W_end/W_start from R = (eta/c)(L/D) ln(W0/W1) (5.153), p. 296; c in lb/(ft lb/s)/s."""
    return math.exp(-range_ft * c_per_s / (eta_pr * LD))


def endurance_s(eta_pr, c_per_s, rho, S, CL32_CD, W0, W1):
    """Propeller endurance at constant C_L^{3/2}/C_D, (5.169), p. 304."""
    return eta_pr / c_per_s * math.sqrt(2.0 * rho * S) * CL32_CD * (W1 ** -0.5 - W0 ** -0.5)


def cbhp_to_c(cbhp_per_hr):
    """lb/(hp h) to lb per (ft lb/s) per s, as Anderson's (8.12), p. 403."""
    return cbhp_per_hr / 550.0 / 3600.0


def buildup_empty_weight(s_wing_exposed, s_ht_exposed, s_vt_exposed, s_fus_wetted, W0,
                         engine_weight):
    """Approximate GA build-up (8.83a-g), p. 449 (Raymer's Table 15.2 values)."""
    return {"wing": 2.5 * s_wing_exposed, "horizontal_tail": 2.0 * s_ht_exposed,
            "vertical_tail": 2.0 * s_vt_exposed, "fuselage": 1.4 * s_fus_wetted,
            "landing_gear": 0.057 * W0, "installed_engine": 1.4 * engine_weight,
            "all_else": 0.1 * W0}


def iterate_buildup(fixed_weight, fuel_fraction_, areas, engine_weight, W0_start, passes=50):
    """Section 8.7, p. 449-453: W_e from (8.83) at the current W0, W_f = (Wf/W0) W0, new W0 from
    (8.1); repeat. Returns the list of (W_e, W_f, W0) per pass, as Anderson's table."""
    rows, W0 = [], W0_start
    for _ in range(passes):
        We = sum(buildup_empty_weight(*areas, W0, engine_weight).values())
        Wf = fuel_fraction_ * W0
        W_new = fixed_weight + Wf + We
        rows.append((We, Wf, W_new))
        if abs(W_new - W0) < 1e-6:
            break
        W0 = W_new
    return rows


def ld_max(CD0, K):
    """(L/D)max = sqrt(1/(4 CD0 K)) (5.30), p. 219."""
    return math.sqrt(1.0 / (4.0 * CD0 * K))


def cl32_cd_max(CD0, K):
    """(C_L^{3/2}/C_D)max (5.38), p. 221."""
    return 0.25 * (3.0 / (K * CD0 ** (1.0 / 3.0))) ** 0.75


def speed_ld_max(W_S, rho, CD0, K):
    """V at (L/D)max (5.34), p. 220."""
    return math.sqrt(2.0 / rho * math.sqrt(K / CD0) * W_S)


def speed_cl32_cd_max(W_S, rho, CD0, K):
    """V at (C_L^{3/2}/C_D)max (5.41), p. 221: 0.76 V_(L/D)max (5.42)."""
    return math.sqrt(2.0 / rho * math.sqrt(K / (3.0 * CD0)) * W_S)


def speed_cl12_cd_max(W_S, rho, CD0, K):
    """V at (C_L^{1/2}/C_D)max (5.45), p. 222: 1.32 V_(L/D)max (5.46)."""
    return math.sqrt(2.0 / rho * math.sqrt(3.0 * K / CD0) * W_S)


def max_rate_of_climb_prop(eta_P_over_W, W_S, rho, CD0, K):
    """(R/C)max = eta P/W - V (1.155/(L/D)max), (5.121) with V from (5.118), p. 277. Used in place
    of (5.122) as printed on p. 278, which the notes flag as misprinted; Ch. 8 reprints the
    consistent form (8.45), p. 415."""
    V = speed_cl32_cd_max(W_S, rho, CD0, K)
    return eta_P_over_W - V * 1.155 / ld_max(CD0, K)


def min_turn_radius(K, W_S, rho, T_W, CD0, g=G):
    """Thrust-limited minimum turn radius (6.33), p. 331 (ignores the stall limit)."""
    return 4.0 * K * W_S / (g * rho * T_W * math.sqrt(1.0 - 4.0 * K * CD0 / T_W ** 2))


def max_turn_rate(K, W_S, rho, T_W, CD0, g=G):
    """Thrust-limited maximum turn rate (6.36), p. 332 (the printed leading 'q' is g)."""
    return g * math.sqrt(rho / W_S * (T_W / (2.0 * K) - math.sqrt(CD0 / K)))


def corner_speed(n_max, W_S, rho, CL_max):
    """V* = sqrt(2 n_max (W/S)/(rho CL_max)) (6.54), p. 343."""
    return math.sqrt(2.0 * n_max / (rho * CL_max) * W_S)


# ---- take-off and landing, ch. 6.7-6.8 ----------------------------------------------------------
# Anderson gives no gust load factor relation in ch. 6 (the V-n section 6.5, p. 341-344, only names
# gusts as a reason for the red-line limit), so there is no gust function here.
def stall_speed(W_S, rho, CL_max):
    """V_stall = sqrt(2 (W/S)/(rho CL_max)) (5.67), reprinted p. 362."""
    return math.sqrt(2.0 * W_S / (rho * CL_max))


def ground_effect_factor(h_over_b):
    """G = (16 h/b)^2/(1 + (16 h/b)^2) (6.77), p. 357: induced drag in over out of ground effect."""
    x = (16.0 * h_over_b) ** 2
    return x / (1.0 + x)


def gear_cd0_increment(W_S_si, mass_kg, K_uc):
    """Delta C_D0 = (W/S) K_uc m^-0.215 (6.76), p. 357; W/S in N/m^2, m in kg."""
    return W_S_si * K_uc * mass_kg ** -0.215


def takeoff_ground_roll(K_T, K_A, V_LO, N, g=G):
    """s_g = ln(1 + (K_A/K_T) V_LO^2)/(2 g K_A) + N V_LO (6.90), p. 361, with K_T = T/W - mu_r
    (6.85) and K_A (6.86) taken constant; N = 3 s large, 1 s small aircraft."""
    return math.log(1.0 + K_A / K_T * V_LO ** 2) / (2.0 * g * K_A) + N * V_LO


def takeoff_K_A(W_S, rho, CD0_total, k_induced, CL_ground, mu_r):
    """K_A = -rho/(2 W/S) [C_D0 + dC_D0 + (k1 + G/(pi e AR)) C_L^2 - mu_r C_L] (6.86), p. 360.
    CD0_total includes the gear increment; k_induced is k1 + G k3 (equal to K out of ground effect)."""
    return -rho / (2.0 * W_S) * (CD0_total + k_induced * CL_ground ** 2 - mu_r * CL_ground)


def takeoff_airborne(V_stall, h_OB, g=G):
    """Airborne distance over the obstacle: R = 6.96 V_stall^2/g (6.98), theta_OB = acos(1 - h/R)
    (6.99), s_a = R sin(theta_OB) (6.100), p. 364. Returns (R, theta_OB, s_a)."""
    R = 6.96 * V_stall ** 2 / g
    theta = math.acos(1.0 - h_OB / R)
    return R, theta, R * math.sin(theta)


def takeoff_distance(W, S, rho, CD0_total, k_induced, CL_max, thrust_at_0p7_VLO, mu_r, CL_ground,
                     h_OB=50.0, N=1.0, g=G):
    """Total take-off distance s_g + s_a (Section 6.7, p. 364): V_LO = 1.1 V_stall (p. 359),
    thrust taken at 0.7 V_LO (p. 360), ground roll (6.90), airborne (6.98)-(6.100)."""
    W_S = W / S
    V_s = stall_speed(W_S, rho, CL_max)
    V_LO = 1.1 * V_s
    K_T = thrust_at_0p7_VLO / W - mu_r                                  # (6.85)
    K_A = takeoff_K_A(W_S, rho, CD0_total, k_induced, CL_ground, mu_r)
    if K_T <= 0.0:
        raise ValueError("thrust does not overcome rolling friction")
    s_g = takeoff_ground_roll(K_T, K_A, V_LO, N, g)
    R, theta, s_a = takeoff_airborne(V_s, h_OB, g)
    return {"V_stall": V_s, "V_LO": V_LO, "ground_roll": s_g, "R": R, "theta_OB": theta,
            "airborne": s_a, "total": s_g + s_a}


def landing_approach(V_f, h_OB, theta_a, g=G):
    """R = V_f^2/(0.2 g) (6.107), h_f = R (1 - cos theta_a) (6.106), s_a = (h_OB - h_f)/tan(theta_a)
    (6.108), s_f = R sin(theta_a) (6.109), p. 369-370. Returns (R, h_f, s_a, s_f)."""
    R = V_f ** 2 / (0.2 * g)
    h_f = R * (1.0 - math.cos(theta_a))
    return R, h_f, (h_OB - h_f) / math.tan(theta_a), R * math.sin(theta_a)


def landing_K_J(W_S, rho, CD0_total, k_induced, CL_ground, mu_r, T_rev_over_W=0.0):
    """J_T = T_rev/W + mu_r (6.113), J_A (6.114), p. 371. J_A is the bracket of (6.114) times
    rho/(2 W/S), so it is negative when the braking friction term outweighs the drag terms (as in
    Example 6.7, whose printed sign is flagged in the notes)."""
    J_T = T_rev_over_W + mu_r
    J_A = rho / (2.0 * W_S) * (CD0_total + k_induced * CL_ground ** 2 - mu_r * CL_ground)
    return J_T, J_A


def landing_ground_roll(J_T, J_A, V_TD, N, g=G):
    """s_g = N V_TD + ln(1 + (J_A/J_T) V_TD^2)/(2 g J_A) (6.119), p. 372; N = free roll 1-3 s."""
    return N * V_TD + math.log(1.0 + J_A / J_T * V_TD ** 2) / (2.0 * g * J_A)


def landing_distance(W, S, rho, CD0_total, k_induced, CL_max, mu_r, CL_ground, theta_a,
                     h_OB=50.0, N=2.0, j=1.15, V_f_over_stall=1.23, T_rev_over_W=0.0, g=G):
    """Total landing distance s_a + s_f + s_g (Section 6.8, p. 367-372): approach at theta_a,
    flare at 1.23 V_stall, touchdown V_TD = j V_stall (j = 1.15 commercial), then (6.119)."""
    W_S = W / S
    V_s = stall_speed(W_S, rho, CL_max)
    R, h_f, s_a, s_f = landing_approach(V_f_over_stall * V_s, h_OB, theta_a, g)
    J_T, J_A = landing_K_J(W_S, rho, CD0_total, k_induced, CL_ground, mu_r, T_rev_over_W)
    s_g = landing_ground_roll(J_T, J_A, j * V_s, N, g)
    return {"V_stall": V_s, "approach": s_a, "flare": s_f, "ground_roll": s_g, "R": R,
            "h_f": h_f, "total": s_a + s_f + s_g}


# ---- static margin, section 8.6.7 ---------------------------------------------------------------
def horizontal_tail_volume(l_ht, S_ht, S, mac):
    """V_HT = l_HT S_HT/(c-bar S): tail arm l_HT from the wing-body aerodynamic center to the tail's, ft;
    dimensionless (p. 444, defined in the author's introductory text, Ref. 3 Ch. 7)."""
    return l_ht * S_ht / (mac * S)


def neutral_point(x_acwb, mac, V_HT, a_t, a, downwash_factor=1.0):
    """Neutral point station, ft, from (8.76) p. 444 solved for x_n:  x_acwb = x_n - V_HT (a_t/a) c-bar
    (V_HT dimensionless, so the tail term is V_HT c-bar in feet; the book's worked number (8.79) subtracts
    V_HT in feet, a printing inconsistency flagged in the library notes, not followed here).
    (8.76) as printed neglects downwash and the tail's dynamic-pressure ratio: downwash_factor 1.
    downwash_factor = eta_t (1 - d eps/d alpha) restores them (not printed in (8.76); same tail term as
    Raymer's (16.9)); a is then the complete airplane's lift slope."""
    return x_acwb + V_HT * mac * (a_t / a) * downwash_factor


def static_margin(x_n, x_cg, mac):
    """Static margin (x_n - x_cg)/c-bar, (8.77) p. 444."""
    return (x_n - x_cg) / mac


def x_acwb_from_neutral_point(x_n, mac, V_HT, a_t, a):
    """(8.76) as printed: x_acwb = x_n - V_HT (a_t/a) c-bar. Used with the 10 % margin (8.78) to place the wing."""
    return x_n - V_HT * mac * a_t / a

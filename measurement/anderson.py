"""Anderson, Aircraft Performance and Design ("Anderson APD"): propeller-airplane sizing (ch. 8) and
performance (ch. 5-6), in fps units. Used in Stage 3 as a second route beside Raymer.

Note on independence: Anderson's first weight estimate uses his own historical empty fraction
(8.5); his refined build-up (8.83a-g) is Raymer's approximate group-weight table (Table 15.2), so it
is a same-author cross-check, not an independent one.
"""
import math

from conceptual.units import G

EMPTY_FRACTION_HISTORICAL = 0.62     # (8.5), p. 400: piston propeller airplanes, Fig. 8.1


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

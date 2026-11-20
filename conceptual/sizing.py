"""Take-off weight sizing (Raymer ch. 3, 6 and 19).

All weights in lb, distances in ft, times in s unless a name says otherwise. Specific fuel
consumption of a propeller engine is C_bhp in lb of fuel per hour per brake horsepower.
"""
import math

from conceptual.units import HP, G

# Raymer Table 3.2, p. 16: historical mission-segment weight fractions W_i/W_(i-1)
TAKEOFF_FRACTION = 0.970
CLIMB_FRACTION = 0.985
LANDING_FRACTION = 0.995
RESERVE_FACTOR = 1.06        # (3.11), p. 23: 5 % reserve plus 1 % trapped fuel

# Raymer Table 3.1, p. 13: We/W0 = A W0^C K_vs
TABLE_3_1 = {
    "general_aviation_single": (2.36, -0.18),
    "general_aviation_twin": (1.51, -0.10),
    "homebuilt_composite": (0.99, -0.09),
    "sailplane_powered": (0.91, -0.05),
    "twin_turboprop": (0.96, -0.05),
}
# Raymer Table 6.2, p. 103: We/W0 = a + b W0^C1 A^C2 (hp/W0)^C3 (W0/S)^C4 Vmax^C5
TABLE_6_2 = {
    "general_aviation_single": (-0.25, 1.14, -0.20, 0.08, 0.05, -0.05, 0.27),
    "homebuilt_composite": (0.0, 0.59, -0.10, 0.05, 0.10, -0.05, 0.17),
    "twin_turboprop": (0.37, 0.08, -0.06, 0.08, 0.08, -0.05, 0.30),
}
COMPOSITE_FACTOR = 0.95      # p. 14: advanced composites, statistical fraction times 0.95


def empty_fraction_table31(W0, category, k_vs=1.0, material_factor=1.0):
    """We/W0 = A W0^C K_vs (Table 3.1, p. 13), times a material factor (p. 14)."""
    A, C = TABLE_3_1[category]
    return A * W0 ** C * k_vs * material_factor


def empty_fraction_table62(W0, category, aspect_ratio, hp_per_W0, W0_per_S, vmax,
                           material_factor=1.0):
    """We/W0 = a + b W0^C1 A^C2 (hp/W0)^C3 (W0/S)^C4 Vmax^C5 (Table 6.2, p. 103).

    The table heading gives Vmax in mph; the DR-1 example (p. 566) substitutes 130 knots. Callers
    state which unit they pass; the UAV pipeline passes mph as the heading says.
    """
    a, b, c1, c2, c3, c4, c5 = TABLE_6_2[category]
    frac = a + b * W0 ** c1 * aspect_ratio ** c2 * hp_per_W0 ** c3 * W0_per_S ** c4 * vmax ** c5
    return frac * material_factor


def empty_fraction_drawn(W0, We_drawn, W0_drawn, exponent):
    """Calibrated empty fraction: We/W0 = (We_drawn/W0_drawn) (W0/W0_drawn)^C.

    Raymer's refined sizing keeps the as-drawn empty weight and scales it with the statistical
    exponent (19.3, p. 524-525; DR-1 printout inputs WOdrawn, WEdrawn, exponent, p. 567).
    """
    return (We_drawn / W0_drawn) * (W0 / W0_drawn) ** exponent


def lift_to_drag(q, CD0, W_S, aspect_ratio, e):
    """L/D of a parabolic polar at dynamic pressure q and wing loading W/S (6.13), p. 105."""
    return 1.0 / (q * CD0 / W_S + W_S / (q * math.pi * aspect_ratio * e))


def cruise_fraction_prop(range_ft, cbhp_per_hr, eta_p, LD):
    """Breguet range for a propeller aircraft, W_i/W_(i-1) = exp[-R C_bhp/(550 eta_p L/D)] (6.12)."""
    return math.exp(-range_ft * (cbhp_per_hr / 3600.0) / (HP * eta_p * LD))


def range_from_fraction_prop(fraction, cbhp_per_hr, eta_p, LD):
    """Inverse of (6.12): the range in ft that a cruise weight fraction buys (DR-1 p. 568)."""
    return -math.log(fraction) * HP * eta_p * LD / (cbhp_per_hr / 3600.0)


def loiter_fraction_prop(time_s, V, cbhp_per_hr, eta_p, LD):
    """Endurance for a propeller aircraft, W_i/W_(i-1) = exp[-E V C_bhp/(550 eta_p L/D)] (6.15)."""
    return math.exp(-time_s * V * (cbhp_per_hr / 3600.0) / (HP * eta_p * LD))


def takeoff_fraction_power(cbhp_per_hr, bhp, minutes, W0):
    """Warm-up and take-off at full power for a stated time (DR-1 refined sizing, p. 586)."""
    return (W0 - cbhp_per_hr * bhp * minutes / 60.0) / W0


def energy_height_change(h1, V1, h2, V2):
    """Delta h_e = Delta(h + V^2/2g) (19.9), p. 523; h in ft, V in ft/s."""
    return (h2 + V2 ** 2 / (2.0 * G)) - (h1 + V1 ** 2 / (2.0 * G))


def climb_fraction_energy(C_per_hr, delta_he, V, D_over_T):
    """W_(i+1)/W_i = exp[-C Delta h_e / (V (1 - D/T))] (19.8), p. 523; C is the equivalent
    thrust-specific fuel consumption, 1/hr."""
    return math.exp(-(C_per_hr / 3600.0) * delta_he / (V * (1.0 - D_over_T)))


def equivalent_tsfc(cbhp_per_hr, V, eta_p):
    """Equivalent thrust SFC of a propeller engine, C = C_bhp V/(550 eta_p) (3.10), p. 18."""
    return cbhp_per_hr * V / (HP * eta_p)


def fuel_fraction(segment_fractions, reserve_factor=RESERVE_FACTOR):
    """(W_x/W0, Wf/W0) from the product of segment fractions, Wf/W0 = 1.06 (1 - W_x/W0) (3.11)."""
    wx = 1.0
    for f in segment_fractions:
        wx *= f
    return wx, reserve_factor * (1.0 - wx)


def solve_takeoff_weight(fixed_weight, fuel_frac, empty_frac, W0_guess, relax=0.8, tol=1e-6,
                         max_iter=2000):
    """Solve W0 = W_fixed / (1 - Wf/W0 - We/W0) (3.4), p. 12, the way Raymer's sizing program does.

    Each row of his printout (p. 567) holds the guess WOG, the fuel WF = (Wf/W0) WOG, the empty
    weight WE = (We/W0) WOG and WOCALC = W_fixed + WF + WE (the weight build-up (3.1)); the next
    guess moves 0.8 of the way to WOCALC (inferred from his rows: 1200 -> 1218.1 -> 1232.7). The
    fixed point is the solution of (3.4). His printouts stop after 15 rows, before convergence:
    DR-1's rubber-engine case ends at WOG 1289.2 while the fixed point is about 1294 lb
    (tests/task12/test_dr1_sizing.py).

    fuel_frac and empty_frac are numbers or functions of W0. Returns (W0, history). Raises
    ValueError if the fractions sum to 1 or more at a guess (the aircraft does not close).
    """
    ff = fuel_frac if callable(fuel_frac) else (lambda W: fuel_frac)
    ef = empty_frac if callable(empty_frac) else (lambda W: empty_frac)
    W = W0_guess
    history = []
    for _ in range(max_iter):
        if ff(W) + ef(W) >= 1.0:
            raise ValueError(f"does not close at W0 = {W:.1f} lb: Wf/W0 + We/W0 = "
                             f"{ff(W) + ef(W):.4f}")
        W_calc = fixed_weight + ff(W) * W + ef(W) * W
        history.append((W, ff(W) * W, ef(W) * W, W_calc))
        if abs(W_calc - W) <= tol * W:
            return W_calc, history
        W = W + relax * (W_calc - W)
    raise ValueError("take-off weight iteration did not converge (fractions may sum near 1)")


def solve_mission_fraction_for_weight(fixed_weight, empty_frac, W0_target,
                                      reserve_factor=RESERVE_FACTOR):
    """Fixed-engine sizing (6.3, p. 108-109; DR-1 p. 568): the mission weight fraction W_x/W0 at
    which the computed take-off weight equals a fixed W0_target. Closed form from (3.4)."""
    ef = empty_frac(W0_target) if callable(empty_frac) else empty_frac
    wf_frac = 1.0 - ef - fixed_weight / W0_target
    return 1.0 - wf_frac / reserve_factor

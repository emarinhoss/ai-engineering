"""Performance (Raymer ch. 17) for a propeller aircraft with a parabolic polar CD = CD0 + K CL^2.
Speeds ft/s, weights lb, areas ft^2, rho slug/ft^3, power in hp."""
import math

from conceptual.units import HP, G


def stall_speed(W_S, rho, CL_max):
    """V_stall = sqrt(2 (W/S)/(rho CL_max)) (DR-1 p. 584; (5.6) solved for V)."""
    return math.sqrt(2.0 * W_S / (rho * CL_max))


def drag(W, S, rho, V, CD0, K, n=1.0):
    """D = q S (CD0 + K CL^2) with CL = n W/(q S)."""
    q = 0.5 * rho * V ** 2
    CL = n * W / (q * S)
    return q * S * (CD0 + K * CL ** 2)


def power_required_hp(W, S, rho, V, CD0, K):
    """Power required for level flight, D V / 550 (17.2, p. 458)."""
    return drag(W, S, rho, V, CD0, K) * V / HP


def speed_min_power(W_S, rho, CD0, K):
    """Speed of minimum power required, CL = sqrt(3 CD0/K) (17.2, p. 458-459; prop loiter)."""
    CL = math.sqrt(3.0 * CD0 / K)
    return math.sqrt(2.0 * W_S / (rho * CL)), CL


def speed_max_ld(W_S, rho, CD0, K):
    """Speed of maximum L/D, CL = sqrt(CD0/K) (17.2, p. 457-458; best prop range)."""
    CL = math.sqrt(CD0 / K)
    return math.sqrt(2.0 * W_S / (rho * CL)), CL


def rate_of_climb(W, S, rho, V, CD0, K, bhp, eta_p):
    """V_v = V (T - D)/W with T = 550 bhp eta_p/V (17.37), p. 464."""
    T = HP * bhp * eta_p / V
    return V * (T - drag(W, S, rho, V, CD0, K)) / W


def best_rate_of_climb(W, S, rho, CD0, K, bhp, eta_p, v_lo, v_hi, n=400):
    """Maximum of (17.37) over speed by a grid search between v_lo and v_hi (Raymer finds it
    graphically, DR-1 p. 585). Returns (V_v_max, V)."""
    best = (-1e9, v_lo)
    for i in range(n + 1):
        V = v_lo + (v_hi - v_lo) * i / n
        vv = rate_of_climb(W, S, rho, V, CD0, K, bhp, eta_p)
        if vv > best[0]:
            best = (vv, V)
    return best


def max_level_speed(W, S, rho, CD0, K, bhp, eta_p, v_lo, v_hi, tol=1e-6):
    """Highest speed where thrust equals drag (DR-1 p. 585, graphical), by bisection on
    T - D with T = 550 bhp eta_p/V. Returns None if T < D at v_lo."""
    def excess(V):
        return HP * bhp * eta_p / V - drag(W, S, rho, V, CD0, K)
    if excess(v_lo) < 0.0:
        return None
    if excess(v_hi) > 0.0:
        return v_hi
    a, b = v_lo, v_hi
    while b - a > tol * b:
        m = 0.5 * (a + b)
        a, b = (m, b) if excess(m) > 0.0 else (a, m)
    return 0.5 * (a + b)


def sustained_turn_rate(T_W, W_S, q, CD0, K, V):
    """n from (17.52), p. 469, then turn rate g sqrt(n^2 - 1)/V (17.50). Returns (rate, n)."""
    n = math.sqrt(q / (K * W_S) * (T_W - q * CD0 / W_S))
    return (G * math.sqrt(max(n ** 2 - 1.0, 0.0)) / V), n


def ground_roll(K_T, K_A, V_i, V_f):
    """S_G = ln[(K_T + K_A V_f^2)/(K_T + K_A V_i^2)]/(2 g K_A) (17.99), p. 487, with K_T (17.100)
    and K_A (17.101). As K_A -> 0 it tends to (V_f^2 - V_i^2)/(2 g K_T)."""
    if abs(K_A) < 1e-14:
        return (V_f ** 2 - V_i ** 2) / (2.0 * G * K_T)
    return math.log((K_T + K_A * V_f ** 2) / (K_T + K_A * V_i ** 2)) / (2.0 * G * K_A)


def takeoff_distance(W, S, rho, CD0, K, CL_max_to, thrust_of_V, mu=0.03, CL_ground=0.1,
                     h_obstacle=50.0, rotation_s=1.0):
    """Take-off over an obstacle by segments (17.8, p. 486-488): ground roll (17.99)-(17.101) with
    thrust at 0.707 V_TO, rotation 1 s for small aircraft, transition (17.102)-(17.108), climb
    (17.109). thrust_of_V is a function T(V). V_TO = 1.1 V_stall with the take-off CL_max.
    Returns a dict of the segment distances (ft)."""
    W_S = W / S
    V_s = stall_speed(W_S, rho, CL_max_to)
    V_to = 1.1 * V_s
    T = thrust_of_V(0.707 * V_to)
    K_T = T / W - mu                                                    # (17.100)
    K_A = rho / (2.0 * W_S) * (mu * CL_ground - CD0 - K * CL_ground ** 2)  # (17.101)
    S_G = ground_roll(K_T, K_A, 0.0, V_to)                              # (17.99)
    S_R = rotation_s * V_to
    V_tr = 1.15 * V_s
    R = V_tr ** 2 / (0.2 * G)                                           # (17.104)
    CL_tr = 0.9 * CL_max_to
    T_tr = thrust_of_V(V_tr)
    D_tr = 0.5 * rho * V_tr ** 2 * S * (CD0 + K * CL_tr ** 2)
    sin_g = (T_tr - D_tr) / W                                           # (17.105)
    if sin_g <= 0.0:
        raise ValueError("no climb gradient after lift-off")
    gamma = math.asin(sin_g)
    h_tr = R * (1.0 - math.cos(gamma))                                  # (17.107)
    if h_tr >= h_obstacle:
        S_T = math.sqrt(R ** 2 - (R - h_obstacle) ** 2)                 # (17.108)
        S_C = 0.0
    else:
        S_T = R * sin_g                                                 # (17.106)
        S_C = (h_obstacle - h_tr) / math.tan(gamma)                     # (17.109)
    return {"V_stall": V_s, "V_TO": V_to, "ground_roll": S_G, "rotation": S_R,
            "transition": S_T, "climb": S_C, "total": S_G + S_R + S_T + S_C}


APPROACH_GAMMA = math.radians(3.0)     # 3 deg approach (p. 490)


def landing_distance(W, S, rho, CD0, K, CL_max_land, mu_brake=0.5, h_obstacle=50.0,
                     approach_gamma=APPROACH_GAMMA, free_roll_s=2.0, idle_thrust=0.0):
    """Landing over an obstacle by segments (17.9, p. 489-491): approach at 1.3 V_stall, flare
    at 1.23 V_stall with n = 1.2, touchdown 1.15 V_stall, free roll, braking by (17.99) from V_TD
    to zero with idle thrust. Returns segment distances (ft) and the FAR field length (times 1.666,
    p. 491)."""
    W_S = W / S
    V_s = stall_speed(W_S, rho, CL_max_land)
    V_f = 1.23 * V_s
    V_td = 1.15 * V_s
    R = V_f ** 2 / (0.2 * G)
    h_f = R * (1.0 - math.cos(approach_gamma))
    S_a = (h_obstacle - h_f) / math.tan(approach_gamma)
    S_F = R * math.sin(approach_gamma)
    S_FR = free_roll_s * V_td
    CL_g = 0.0
    K_T = idle_thrust / W - mu_brake
    K_A = rho / (2.0 * W_S) * (mu_brake * CL_g - CD0 - K * CL_g ** 2)
    S_B = ground_roll(K_T, K_A, V_td, 0.0)                              # (17.99) from V_TD to 0
    total = S_a + S_F + S_FR + S_B
    return {"V_stall": V_s, "approach": S_a, "flare": S_F, "free_roll": S_FR, "braking": S_B,
            "total": total, "far_field_length": 1.666 * total}

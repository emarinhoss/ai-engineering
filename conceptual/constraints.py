"""Wing loading and power loading from each requirement (Raymer ch. 5).

W/S in lb/ft^2, q in lb/ft^2, V in ft/s, rho in slug/ft^3. Power loading is expressed as
hp/W (brake horsepower per lb of take-off weight) as in Raymer's propeller relations.
"""
import math

from conceptual.units import HP


def ws_stall(rho, V_stall, CL_max):
    """Largest W/S that stalls at or below V_stall: W/S = 1/2 rho V_stall^2 CL_max (5.6), p. 85."""
    return 0.5 * rho * V_stall ** 2 * CL_max


def cl_takeoff(CL_max_takeoff, speed_ratio=1.1):
    """Lift coefficient at lift-off, CL_max (V_stall/V_TO)^2 with V_TO = 1.1 V_stall (p. 89; DR-1
    p. 565)."""
    return CL_max_takeoff / speed_ratio ** 2


def ws_takeoff_prop(TOP, sigma, CL_TO, hp_per_W):
    """W/S = TOP sigma CL_TO (hp/W) (5.8), p. 89; TOP read from Raymer's Fig. 5.4 (a chart)."""
    return TOP * sigma * CL_TO * hp_per_W


def landing_distance(W_S, sigma, CL_max, S_a):
    """Landing distance over a 50 ft obstacle, S = 80 (W/S)/(sigma CL_max) + S_a (5.11), p. 91.
    S_a is the obstacle-clearance distance (1,000 ft airliner, 600 ft general aviation, 450 ft
    short-field, per the text on p. 90-91)."""
    return 80.0 * W_S / (sigma * CL_max) + S_a


def ws_landing(S_landing, sigma, CL_max, S_a):
    """Largest W/S for a landing distance, (5.11) solved for W/S."""
    return (S_landing - S_a) * sigma * CL_max / 80.0


def thrust_to_weight_prop(hp_per_W, V, eta_p):
    """T/W = (550 eta_p / V)(hp/W) (5.1), p. 79; DR-1 climb, p. 565."""
    return HP * eta_p / V * hp_per_W


def ws_climb(T_W, G, q, CD0, aspect_ratio, e):
    """Largest W/S that climbs at gradient G with thrust loading T/W (5.30), p. 98 (+ root).
    Returns None if the root is imaginary (the aircraft cannot climb at that gradient)."""
    k = 1.0 / (math.pi * aspect_ratio * e)
    disc = (T_W - G) ** 2 - 4.0 * CD0 * k
    if disc < 0.0:
        return None
    return ((T_W - G) + math.sqrt(disc)) / (2.0 * k / q)


def ws_best_range_prop(q, CD0, aspect_ratio, e):
    """W/S for best propeller range at dynamic pressure q, q sqrt(pi A e CD0) (5.13), p. 93."""
    return q * math.sqrt(math.pi * aspect_ratio * e * CD0)


def ws_best_loiter_prop(q, CD0, aspect_ratio, e):
    """W/S for best propeller loiter at dynamic pressure q, q sqrt(3 pi A e CD0) (5.16), p. 94."""
    return q * math.sqrt(3.0 * math.pi * aspect_ratio * e * CD0)


def drag_to_weight(q, CD0, W_S, aspect_ratio, e):
    """D/W = q CD0/(W/S) + (W/S)/(q pi A e) (5.29), p. 98."""
    return q * CD0 / W_S + W_S / (q * math.pi * aspect_ratio * e)


def hp_per_W_climb(rate_of_climb, V, q, CD0, W_S, aspect_ratio, e, eta_p, power_lapse=1.0):
    """Sea-level-rated hp/W that gives a rate of climb at speed V: from (17.37), V_v = V (T - D)/W
    with T = 550 eta_p bhp / V (13.16); power_lapse = bhp(h)/bhp_SL (13.9)."""
    T_W = rate_of_climb / V + drag_to_weight(q, CD0, W_S, aspect_ratio, e)
    return T_W * V / (HP * eta_p) / power_lapse


# Raymer Table 5.4, p. 80: hp/W0 = a Vmax^C, Vmax in mph
TABLE_5_4 = {"homebuilt_composite": (0.004, 0.57), "general_aviation_single": (0.024, 0.22),
             "twin_turboprop": (0.012, 0.50)}


def hp_per_W_statistical(vmax_mph, category):
    """Statistical hp/W0 = a Vmax^C (Table 5.4, p. 80); Vmax in mph."""
    a, c = TABLE_5_4[category]
    return a * vmax_mph ** c

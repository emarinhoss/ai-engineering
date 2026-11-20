"""Propeller and engine relations (Raymer ch. 13). bhp in hp, V in ft/s, D in ft, n in rev/s."""
from conceptual.units import HP


def advance_ratio(V, n_rev_s, D):
    """J = V/(n D) (13.10), p. 327."""
    return V / (n_rev_s * D)


def power_coefficient(bhp, rho, n_rev_s, D):
    """C_P = 550 bhp/(rho n^3 D^5) (13.11), p. 327."""
    return HP * bhp / (rho * n_rev_s ** 3 * D ** 5)


def static_thrust(ct_over_cp, bhp, n_rev_s, D):
    """Static thrust (C_T/C_P) 550 bhp/(n D) (13.16), p. 327."""
    return ct_over_cp * HP * bhp / (n_rev_s * D)


def thrust_from_power(bhp, eta_p, V):
    """T = 550 bhp eta_p / V (13.16), p. 327."""
    return HP * bhp * eta_p / V


def propwash_factor(D, sigma, cfe_swet_washed):
    """eta_effective/eta = 1 - (1.558/D^2) (rho/rho0) sum(Cf S_wet)_washed (13.17), p. 330."""
    return 1.0 - 1.558 / D ** 2 * sigma * cfe_swet_washed


def piston_power_lapse(sigma):
    """bhp/bhp_SL = sigma - (1 - sigma)/7.55 (13.9), p. 325. Raymer gives it for piston engines;
    he gives no turboprop lapse (13.7, p. 331, says to treat the core as a jet with the maker's
    data). Stage 1 applies it to the turboprop as a stated out-of-type use; Stage 3 measures the
    lapse with Mattingly App. K."""
    return sigma - (1.0 - sigma) / 7.55

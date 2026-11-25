"""Propeller and engine relations (Raymer ch. 13). bhp in hp, V in ft/s, D in ft, n in rev/s."""
import math

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


class ActuatorDisk:
    """Propeller efficiency from momentum theory, Mattingly App. L p. 609-613 (owner ruling G-4,
    2026-11-25). The ideal efficiency eta* follows from the thrust loading C_T* = T/(rho V^2 A/2) and
    C_T* = 4 (1 - eta*)/eta*^2 (L.8); a real propeller reaches the factor `real_to_ideal` (about 0.85,
    p. 612) of it: eta = f eta*. Thrust and efficiency depend on each other (T = 550 eta P/V), so
    from a shaft power the pair is found by iteration. rho in slug/ft^3, D in ft."""

    def __init__(self, rho, D, real_to_ideal):
        self.rho, self.D, self.f = rho, D, real_to_ideal
        self.area = math.pi * D ** 2 / 4.0

    def efficiency_for_thrust(self, T, V):
        """eta = f eta*, with eta* from (L.8) solved for eta*: C_T eta*^2 + 4 eta* - 4 = 0."""
        ct = T / (0.5 * self.rho * V ** 2 * self.area)
        ideal = 1.0 if ct <= 0.0 else (-4.0 + math.sqrt(16.0 + 16.0 * ct)) / (2.0 * ct)
        return self.f * ideal

    def efficiency_and_thrust(self, bhp, V):
        """(eta, T) for shaft power bhp (hp) at speed V (ft/s): iterate T = 550 eta bhp/V."""
        eta = self.f
        for _ in range(200):
            T = HP * eta * bhp / V
            new = self.efficiency_for_thrust(T, V)
            if abs(new - eta) < 1e-12:
                return new, HP * new * bhp / V
            eta = new
        raise ValueError(f"propeller efficiency did not converge at {bhp} hp, {V} ft/s")


def propeller(L, rho, D):
    """What the performance code takes as `eta_p`: the ledger's flat number (propeller_model flat,
    the default, for every record made before owner ruling G-4) or an ActuatorDisk at this density
    and diameter (propeller_model app_l, factor L['prop_real_to_ideal'])."""
    model = L.get("propeller_model", "flat")
    if model == "flat":
        return L["eta_p"]
    if model == "app_l":
        return ActuatorDisk(rho, D, L["prop_real_to_ideal"])
    raise ValueError(f"propeller_model must be flat or app_l, not {model!r}")


def static_thrust_limit(bhp, rho, D):
    """Momentum limit of static thrust: P = T^(3/2)/sqrt(2 rho A) (from (L.8) with V -> 0), so
    T = (2 rho A)^(1/3) (550 bhp)^(2/3). No propeller of this disk area and power can exceed it."""
    area = math.pi * D ** 2 / 4.0
    return (2.0 * rho * area) ** (1.0 / 3.0) * (HP * bhp) ** (2.0 / 3.0)


def efficiency_at_power(eta_p, bhp, V):
    """Efficiency at shaft power bhp and speed V; eta_p as returned by propeller()."""
    return eta_p.efficiency_and_thrust(bhp, V)[0] if isinstance(eta_p, ActuatorDisk) else eta_p


def efficiency_for_thrust(eta_p, T, V):
    """Efficiency when the propeller must give thrust T at speed V; eta_p as returned by propeller()."""
    return eta_p.efficiency_for_thrust(T, V) if isinstance(eta_p, ActuatorDisk) else eta_p


def shaft_hp(thrust_work, V, eta_p):
    """Shaft power (hp) for thrust power `thrust_work` = T V (ft lb/s) at speed V: T V/(550 eta)."""
    return thrust_work / (HP * efficiency_for_thrust(eta_p, thrust_work / V, V))


def thrust_from_power(bhp, eta_p, V):
    """T = 550 bhp eta_p / V (13.16), p. 327. eta_p is a number or an ActuatorDisk (then eta follows
    from the thrust itself)."""
    if isinstance(eta_p, ActuatorDisk):
        return eta_p.efficiency_and_thrust(bhp, V)[1]
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

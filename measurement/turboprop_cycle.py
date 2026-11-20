"""Turboprop cycle, Mattingly, Aircraft Engine Design, 2nd ed., Appendix K, with the modified
specific heat (MSH) gas model: constant cp and gamma ahead of the burner (c) and behind it (t).

Design point: the parametric sequence (K.1)-(K.14), p. 590-597, written for MSH.
Off-design: (K.15)-(K.21), p. 597-601, under the book's Section 5.2.2 assumptions: the HP
turbine entry (4) and LP turbine entry (4.5) are choked, so the HP turbine ratios tau_tH and pi_tH
stay at their design values; component efficiencies, cooling and bleed fractions are fixed; the
exit nozzle area is fixed. Power takeoffs are zero (C_TOL = C_TOH = 0), as in the book's example.

Book misprints flagged in the library notes are handled as follows (each is the obvious reading):
(K.18-CPG) exponent read as (gamma_t - 1)/gamma_t; the unchoked nozzle line read as
P_t9/P_9 = P_t9/P_0; F = m0 C h0 / V0 (K.11), not times V0.

Units: English, as in the book. T in deg R, P in lbf/ft^2, h in Btu/lbm, mass flow in lbm/s,
thrust in lbf. Shaft power is returned in hp.
"""
import math

GC = 32.174          # lbm ft/(lbf s^2)
J = 778.16           # ft lbf per Btu
BTU_PER_HP_H = 2544.43

# Example inputs, p. 597. gamma_t is printed 1.4; see design_inputs(gamma_t=...) and the tests.
BOOK_EXAMPLE = {
    "e_c": 0.90, "pi_d": 0.97, "eta_b": 0.995, "Tt4": 3200.0, "e_tH": 0.89, "pi_b": 0.96,
    "eta_mL": 0.99, "h_PR": 18400.0, "e_tL": 0.91, "pi_n": 0.99, "eta_mH": 0.98,
    "eta_prop": 0.82, "eta_g": 0.99, "eps1": 0.05, "eps2": 0.05, "gamma_c": 1.4, "cp_c": 0.240,
    "beta": 0.0, "gamma_t": 1.4, "cp_t": 0.295,
}


def _R(gamma, cp):
    """Gas constant in ft lbf/(lbm R) from cp (Btu/(lbm R))."""
    return (gamma - 1.0) / gamma * cp * J


def _mfp_ratio(M, gamma):
    """Mass flow parameter up to a constant: M (1 + (gamma-1)/2 M^2)^(-(gamma+1)/(2(gamma-1)))."""
    return M * (1.0 + 0.5 * (gamma - 1.0) * M * M) ** (-(gamma + 1.0) / (2.0 * (gamma - 1.0)))


def _ram(M0, k):
    tau_r = 1.0 + 0.5 * (k["gamma_c"] - 1.0) * M0 ** 2
    return tau_r, tau_r ** (k["gamma_c"] / (k["gamma_c"] - 1.0))


def _mixers(k, f, tau_r, tau_c, tau_lam, tau_tH):
    """Coolant mixer enthalpy ratios tau_m1, tau_m2 (p. 595-596)."""
    core = (1.0 - k["beta"] - k["eps1"] - k["eps2"]) * (1.0 + f)
    e1, e2 = k["eps1"], k["eps2"]
    tm1 = (core + e1 * tau_r * tau_c / tau_lam) / (core + e1)
    tm2 = (core + e1 + e2 * tau_r * tau_c / (tau_lam * tm1 * tau_tH)) / (core + e1 + e2)
    return tm1, tm2


def _nozzle_and_performance(k, M0, T0, tau_r, pi_r, pi_c, tau_c, f, tau_lam, tm1, tau_tH, pi_tH,
                            tm2, tau_tL, pi_tL, eta_prop):
    """Exit state, C_C (K.6), C_prop (K.8), C_TOTAL (K.4) and the specific outputs (K.9)-(K.12)."""
    gc_, gt = k["gamma_c"], k["gamma_t"]
    Rc, Rt = _R(gc_, k["cp_c"]), _R(gt, k["cp_t"])
    h0 = k["cp_c"] * T0
    a0 = math.sqrt(gc_ * Rc * GC * T0)
    V0 = M0 * a0
    Pt9_P0 = pi_r * k["pi_d"] * pi_c * k["pi_b"] * pi_tH * pi_tL * k["pi_n"]
    crit = ((gt + 1.0) / 2.0) ** (gt / (gt - 1.0))
    Pt9_P9 = min(Pt9_P0, crit)                      # choked: (Pt/P) at M = 1; unchoked: P9 = P0
    P0_P9 = Pt9_P9 / Pt9_P0
    M9 = math.sqrt(2.0 / (gt - 1.0) * (Pt9_P9 ** ((gt - 1.0) / gt) - 1.0))
    Tt9 = T0 * tau_lam * k["cp_c"] / k["cp_t"] * tm1 * tau_tH * tm2 * tau_tL
    T9 = Tt9 / Pt9_P9 ** ((gt - 1.0) / gt)
    V9 = math.sqrt(2.0 * GC * J * k["cp_t"] * (Tt9 - T9))
    fo = f * (1.0 - k["beta"] - k["eps1"] - k["eps2"])
    m9 = 1.0 + fo - k["beta"]
    C_C = (gc_ - 1.0) * M0 * (m9 * V9 / a0 - M0
                              + m9 * Rt / Rc * (T9 / T0) / (V9 / a0) * (1.0 - P0_P9) / gc_)   # (K.6)
    work_L = k["eta_mL"] * m9 * tau_lam * tm1 * tau_tH * tm2 * (1.0 - tau_tL)   # LP spool work / h0
    C_prop = eta_prop * k["eta_g"] * work_L                                       # (K.8)
    C_tot = C_prop + C_C                                                          # (K.4)
    shaft = k["eta_g"] * work_L * h0 * J / 550.0          # shaft hp to the propeller per lbm/s
    return {
        "V0": V0, "a0": a0, "h0": h0, "fo": fo, "M9": M9, "V9_a0": V9 / a0, "P0_P9": P0_P9,
        "Pt9_P0": Pt9_P0, "C_C": C_C, "C_prop": C_prop, "C_total": C_tot,
        "P_per_m0_hp": C_tot * h0 * J / 550.0,                                    # (K.9), hp/(lbm/s)
        "S_P": fo / (C_tot * h0) * BTU_PER_HP_H,                                  # (K.10), lbm/(hp h)
        "F_per_m0": C_tot * h0 * J / V0 if V0 > 0 else float("nan"),              # (K.11)
        "S": fo * V0 / (C_tot * h0 * J) * 3600.0 if V0 > 0 else float("nan"),    # (K.12), 1/h
        "shaft_hp_per_m0": shaft,
        "bsfc": fo * 3600.0 / shaft if shaft > 0 else math.inf,   # lb fuel per shaft hp hour (jet not counted)
        "Tt3": T0 * tau_r * tau_c, "Tt9": Tt9,
    }


def design_point(M0, T0, P0, pi_c, tau_t, k=BOOK_EXAMPLE):
    """Parametric (on-design) cycle, p. 594-597, MSH. Returns a dict of the book's outputs plus the
    reference values the off-design calculation needs."""
    gc_, gt = k["gamma_c"], k["gamma_t"]
    tau_r, pi_r = _ram(M0, k)
    tau_c = pi_c ** ((gc_ - 1.0) / (gc_ * k["e_c"]))
    eta_c = (pi_c ** ((gc_ - 1.0) / gc_) - 1.0) / (tau_c - 1.0)
    tau_lam = k["cp_t"] * k["Tt4"] / (k["cp_c"] * T0)
    f = (tau_lam - tau_r * tau_c) / (k["h_PR"] * k["eta_b"] / (k["cp_c"] * T0) - tau_lam)
    core = (1.0 - k["beta"] - k["eps1"] - k["eps2"]) * (1.0 + f)
    tm1, _ = _mixers(k, f, tau_r, tau_c, tau_lam, 1.0)
    tau_tH = 1.0 - tau_r * (tau_c - 1.0) / (k["eta_mH"] * tau_lam * (core + k["eps1"] * tau_r * tau_c / tau_lam))  # (K.7)
    _, tm2 = _mixers(k, f, tau_r, tau_c, tau_lam, tau_tH)
    pi_tH = tau_tH ** (gt / ((gt - 1.0) * k["e_tH"]))
    eta_tH = (1.0 - tau_tH) / (1.0 - tau_tH ** (1.0 / k["e_tH"]))
    tau_tL = tau_t / (tm1 * tau_tH * tm2)
    if not 0.0 < tau_tL < 1.0:
        raise ValueError(f"tau_t {tau_t} leaves no work for the LP turbine (tau_tL = {tau_tL:.3f})")
    pi_tL = tau_tL ** (gt / ((gt - 1.0) * k["e_tL"]))
    eta_tL = (1.0 - tau_tL) / (1.0 - tau_tL ** (1.0 / k["e_tL"]))
    out = _nozzle_and_performance(k, M0, T0, tau_r, pi_r, pi_c, tau_c, f, tau_lam, tm1, tau_tH,
                                  pi_tH, tm2, tau_tL, pi_tL, k["eta_prop"])
    out.update({"M0": M0, "T0": T0, "P0": P0, "Tt4": k["Tt4"], "pi_c": pi_c, "tau_c": tau_c,
                "eta_c": eta_c, "f": f, "tau_lam": tau_lam, "tau_m1": tm1, "tau_m2": tm2,
                "tau_tH": tau_tH, "pi_tH": pi_tH, "eta_tH": eta_tH, "tau_tL": tau_tL,
                "pi_tL": pi_tL, "eta_tL": eta_tL, "tau_r": tau_r, "pi_r": pi_r, "tau_t": tau_t})
    return out


def optimum_tau_t(M0, T0, P0, pi_c, k=BOOK_EXAMPLE, lo=0.2, hi=0.95):
    """tau_t that maximises F/m0 at fixed pi_c (golden-section search); p. 597-599 say the same
    tau_t* also minimises S."""
    def neg(t):
        try:
            return -design_point(M0, T0, P0, pi_c, t, k)["C_total"]
        except ValueError:
            return float("inf")
    g = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    for _ in range(80):
        c, d = b - g * (b - a), a + g * (b - a)
        if neg(c) < neg(d):
            b = d
        else:
            a = c
    return 0.5 * (a + b)


def eta_prop_model(M0, eta_max):
    """Propeller efficiency against flight Mach number, p. 601 (Fig. K.5)."""
    if M0 <= 0.1:
        return 10.0 * M0 * eta_max
    if M0 <= 0.7:
        return eta_max
    return (1.0 - (M0 - 0.7) / 3.0) * eta_max


def off_design(ref, M0, T0, P0, Tt4, k=BOOK_EXAMPLE, eta_prop_max=None):
    """Off-design cycle (K.15)-(K.21) at throttle setting Tt4 for the engine whose design point
    is ref (from design_point). Returns the outputs of _nozzle_and_performance plus mass flow,
    thrust F (lbf), shaft power (hp), pi_c and Tt3. ref must carry m0 (lbm/s), the design mass flow."""
    gc_, gt = k["gamma_c"], k["gamma_t"]
    if M0 <= 0.0:
        raise ValueError("off_design needs M0 > 0 (thrust is power over speed)")
    eta_max = k["eta_prop"] if eta_prop_max is None else eta_prop_max
    tau_r, pi_r = _ram(M0, k)
    tau_lam = k["cp_t"] * Tt4 / (k["cp_c"] * T0)
    tau_tH, pi_tH = ref["tau_tH"], ref["pi_tH"]
    # compressor and burner: fixed-point on (f, tau_m1, tau_c) from (K.15), (K.16) and (4.18)
    f, tm1, tau_c = ref["f"], ref["tau_m1"], ref["tau_c"]
    for _ in range(200):
        core = (1.0 - k["beta"] - k["eps1"] - k["eps2"]) * (1.0 + f)
        tau_c_new = 1.0 + k["eta_mH"] * (core + k["eps1"]) * tau_lam * tm1 * (1.0 - tau_tH) / tau_r   # (K.15)
        f_new = (tau_lam - tau_r * tau_c_new) / (k["h_PR"] * k["eta_b"] / (k["cp_c"] * T0) - tau_lam)
        tm1_new, _ = _mixers(k, f_new, tau_r, tau_c_new, tau_lam, tau_tH)
        done = abs(tau_c_new - tau_c) < 1e-10 and abs(f_new - f) < 1e-12
        tau_c, f, tm1 = tau_c_new, f_new, tm1_new
        if done:
            break
    _, tm2 = _mixers(k, f, tau_r, tau_c, tau_lam, tau_tH)
    pi_c = (1.0 + ref["eta_c"] * (tau_c - 1.0)) ** (gc_ / (gc_ - 1.0))                    # (K.16)
    # LP turbine and nozzle: solve (K.18-CPG) with (K.20), (K.21) for pi_tL by bisection
    area = ref["pi_tL"] / math.sqrt(ref["tau_tL"]) * _mfp_ratio(min(ref["M9"], 1.0), gt) / _mfp_ratio(1.0, gt)
    upstream = pi_r * k["pi_d"] * pi_c * k["pi_b"] * pi_tH * k["pi_n"]
    crit = ((gt + 1.0) / 2.0) ** (gt / (gt - 1.0))

    def residual(pi_tL):
        tau_tL = 1.0 - ref["eta_tL"] * (1.0 - pi_tL ** ((gt - 1.0) / gt))                   # (K.18-CPG)
        Pt9_P9 = min(upstream * pi_tL, crit)                                                # (K.20)
        M9 = math.sqrt(max(0.0, 2.0 / (gt - 1.0) * (Pt9_P9 ** ((gt - 1.0) / gt) - 1.0)))
        if M9 <= 0.0:
            return -1.0
        return pi_tL - area * math.sqrt(tau_tL) * _mfp_ratio(1.0, gt) / _mfp_ratio(M9, gt)  # (K.21)

    lo, hi = 1.0 / upstream + 1e-12, 1.0
    if residual(lo) > 0.0:
        raise ValueError("no LP turbine solution: nozzle cannot pass the flow at this condition")
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if residual(mid) > 0.0:
            hi = mid
        else:
            lo = mid
    pi_tL = 0.5 * (lo + hi)
    tau_tL = 1.0 - ref["eta_tL"] * (1.0 - pi_tL ** ((gt - 1.0) / gt))
    eta_prop = eta_prop_model(M0, eta_max)
    out = _nozzle_and_performance(k, M0, T0, tau_r, pi_r, pi_c, tau_c, f, tau_lam, tm1, tau_tH,
                                  pi_tH, tm2, tau_tL, pi_tL, eta_prop)
    # engine mass flow (K.17) as a ratio to the reference; A4 and MFP4 fixed (station 4 choked)
    m0 = (ref["m0"] * (1.0 + ref["f"]) / (1.0 + f) * (P0 * pi_r * pi_c) / (ref["P0"] * ref["pi_r"] * ref["pi_c"])
          * math.sqrt(ref["Tt4"] / Tt4))
    out.update({"M0": M0, "Tt4": Tt4, "pi_c": pi_c, "tau_c": tau_c, "f": f, "tau_tL": tau_tL,
                "pi_tL": pi_tL, "m0": m0, "eta_prop": eta_prop,
                "shaft_hp": m0 * out["shaft_hp_per_m0"],
                "fuel_lbm_h": m0 * out["fo"] * 3600.0})
    out["F"] = m0 * out["F_per_m0"]
    return out


def full_throttle(ref, M0, T0, P0, k=BOOK_EXAMPLE, Tt4_max=None, pi_c_max=None, Tt3_max=None,
                  eta_prop_max=None):
    """Off-design at the highest Tt4 that respects the control limits Tt4 <= Tt4_max,
    pi_c <= pi_c_max and Tt3 <= Tt3_max (p. 606), found by bisection on Tt4 (the book uses Newton)."""
    Tt4_max = ref["Tt4"] if Tt4_max is None else Tt4_max

    def ok(Tt4):
        r = off_design(ref, M0, T0, P0, Tt4, k, eta_prop_max)
        return ((pi_c_max is None or r["pi_c"] <= pi_c_max + 1e-9)
                and (Tt3_max is None or r["Tt3"] <= Tt3_max + 1e-9)), r

    good, r = ok(Tt4_max)
    if good:
        return r
    lo, hi = 0.3 * Tt4_max, Tt4_max
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if ok(mid)[0]:
            lo = mid
        else:
            hi = mid
    return ok(lo)[1]


def shaft_power_at(ref, M0, T0, P0, shaft_hp, k=BOOK_EXAMPLE, Tt4_max=None, **limits):
    """Part power: the Tt4 that gives the requested shaft hp (bisection), and the cycle there."""
    top = full_throttle(ref, M0, T0, P0, k, Tt4_max, **limits)
    if shaft_hp > top["shaft_hp"] * (1 + 1e-9):
        raise ValueError(f"{shaft_hp:.1f} hp exceeds the {top['shaft_hp']:.1f} hp available")
    lo, hi = 0.35 * top["Tt4"], top["Tt4"]
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        try:
            p = off_design(ref, M0, T0, P0, mid, k)["shaft_hp"]
        except ValueError:
            p = 0.0
        if p < shaft_hp:
            lo = mid
        else:
            hi = mid
    return off_design(ref, M0, T0, P0, hi, k)

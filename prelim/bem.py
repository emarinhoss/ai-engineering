"""Blade-element (strip) theory of a propeller with a momentum balance on each annulus
(docs/specs/task12_preliminary_design.md, package P6). Units: ft, lb, slug, s; angles in radians unless a name ends in _deg.

Library relations, cited by number and page (Mattingly, Aircraft Engine Design 2nd ed., App. L; Raymer 2nd ed. ch. 13):
  (L.5) p. 611, (L.7) and (L.8) p. 612: the actuator disk;  (L.10) to (L.15) p. 613-616: the blade element;
  (L.16) p. 616: relative Mach number;  (L.17) to (L.20) p. 617-618: coefficients and the static-thrust correlation;
  Raymer (13.14) p. 327: activity factor.

Not in the library, and where it comes from (source record data/task12/pd_p6_propeller_source.yaml):
  - The momentum balance on one annulus. It is (L.3) and (L.5) written for the ring between r and r + dr, and the
    same for angular momentum:
        thrust  dF = 4 pi r rho V^2 (1 + a) a F dr          (mass flow 2 pi r dr rho V (1 + a), speed gained 2 a V)
        torque  dQ = 4 pi r^3 rho V Omega (1 + a) a' F dr   (same mass flow, swirl gained 2 a' Omega r, arm r)
    with a and a' the axial and rotational interference factors of Mattingly's Fig. L.4.
  - The factor F for a finite number of blades. NACA ACR 4B04 (Crigler, 1944) states the strip method with such a
    factor (Goldstein's, from a chart). Here F is Prandtl's closed form, written from its textbook definition:
        F = (2/pi) arccos(exp(-f)),  f = (B/2) (1 - x)/(x sin(phi)),  x = r/R.
  - Section data of infinite span from data measured on a wing: the induced angle and induced drag are removed
    (Anderson, Aircraft Performance and Design, (2.15), p. 81).
"""
import math

import numpy as np
from scipy.optimize import brentq

HP = 550.0                      # ft lb/s per horsepower
PHI_MIN, PHI_MAX = 1.0e-4, math.pi / 2.0 - 1.0e-4      # the inflow angle is searched between these


# ---------------------------------------------------------------- actuator disk (L.5) to (L.8)

def axial_interference_of_disk(ve_over_v0):
    """a such that the speed at the disk is (1 + a) V_0 = (V_e + V_0)/2, (L.5), p. 611."""
    return (ve_over_v0 - 1.0) / 2.0


def ideal_efficiency(ve_over_v0):
    """eta* = 2/(1 + V_e/V_0), (L.7), p. 612."""
    return 2.0 / (1.0 + ve_over_v0)


def ideal_efficiency_of_disk(thrust, rho, V, D):
    """eta* of a disk of diameter D giving this thrust at speed V: C_T* = T/(rho V^2 A/2) = 4 (1 - eta*)/eta*^2, (L.8),
    p. 612, solved for eta*."""
    ct = thrust / (0.5 * rho * V ** 2 * math.pi * D ** 2 / 4.0)
    return 1.0 if ct <= 0.0 else (-4.0 + math.sqrt(16.0 + 16.0 * ct)) / (2.0 * ct)


# ---------------------------------------------------------------- blade element (L.14) to (L.16)

def element_efficiency(a, a_rot, phi, gamma):
    """eta_e = (1 - a')/(1 + a) tan(phi)/tan(phi + gamma), (L.14), p. 615. gamma is the drag angle, tan(gamma) = C_D/C_L."""
    return (1.0 - a_rot) / (1.0 + a) * math.tan(phi) / math.tan(phi + gamma)


def element_efficiency_max(a, a_rot, gamma):
    """(L.15), p. 615: the largest eta_e over phi, reached at phi = 45 deg - gamma/2."""
    return (1.0 - a_rot) / (1.0 + a) * math.tan(math.pi / 4.0 - gamma / 2.0) / math.tan(math.pi / 4.0 + gamma / 2.0)


def relative_mach(a, mach_0, phi):
    """M_r = (1 + a) M_0/sin(phi), (L.16), p. 616."""
    return (1.0 + a) * mach_0 / math.sin(phi)


# ---------------------------------------------------------------- coefficients (L.17) to (L.20)

def thrust_coefficient_l17(thrust_lbf, sigma, rpm, D):
    """C_T = F/(660 sigma (N/1000)^2 (D/10)^4), (L.17), p. 617. N in rpm, D in ft."""
    return thrust_lbf / (660.0 * sigma * (rpm / 1000.0) ** 2 * (D / 10.0) ** 4)


def power_coefficient_l18(hp, sigma, rpm, D):
    """C_P = HP/(2000 sigma (N/1000)^3 (D/10)^5), (L.18), p. 617."""
    return hp / (2000.0 * sigma * (rpm / 1000.0) ** 3 * (D / 10.0) ** 5)


def advance_ratio_l20(V, rpm, D):
    """J = V_0/(N D), (L.20), p. 618, with N in revolutions per second."""
    return V / (rpm / 60.0 * D)


def static_diameter_l19(thrust_lbf, sigma, hp, blades):
    """D = (F^3/(589 sigma HP^2 blades^(1/3)))^(1/2), (L.19), p. 617: diameter (ft) for a static thrust."""
    return math.sqrt(thrust_lbf ** 3 / (589.0 * sigma * hp ** 2 * blades ** (1.0 / 3.0)))


def static_thrust_l19(D, sigma, hp, blades):
    """(L.19) solved for the static thrust (lbf) of a propeller of diameter D."""
    return (D ** 2 * 589.0 * sigma * hp ** 2 * blades ** (1.0 / 3.0)) ** (1.0 / 3.0)


def activity_factor(x, c_over_D):
    """Activity factor per blade, Raymer (13.14), p. 327: (10^5/D^5) integral of c r^3 dr. With x = r/R this is
    (10^5/16) integral of (c/D) x^3 dx, taken by the trapezoid rule over the stations given."""
    x, c = np.asarray(x, float), np.asarray(c_over_D, float)
    y = c * x ** 3
    return 1.0e5 / 16.0 * float(np.sum((y[1:] + y[:-1]) / 2.0 * np.diff(x)))


# ---------------------------------------------------------------- section data

def infinite_span(alpha_deg, CL, CD, aspect_ratio, e):
    """(alpha, c_d) of the section of infinite span from a point measured on a wing of this aspect ratio:
    alpha_0 = alpha - C_L/(pi e A) and c_d = C_D - C_L^2/(pi e A). Anderson APD (2.15), p. 81, is the first of the two
    in the form of a lift slope; e is its planform factor (about 0.95)."""
    k = CL / (math.pi * e * aspect_ratio)
    return alpha_deg - math.degrees(k), CD - CL * k


class Sections:
    """Lift and drag against angle of attack for a family of sections of different thickness ratio.

    tables: list of {"t_c", "alpha" (deg, rising), "cl", "cd"}, sorted by t_c. Between two thickness ratios the two
    tables are mixed linearly at the same angle. Thicker than the thickest (or no thickness given, the blade shank):
    the thickest table. Outside a table's range of angles the end value is held and the excess is returned, so that
    the caller can say which stations ran outside the measured range."""

    def __init__(self, tables):
        self.tables = sorted(tables, key=lambda t: t["t_c"])

    def _one(self, table, alpha_deg):
        lo, hi = table["alpha"][0], table["alpha"][-1]
        outside = alpha_deg - hi if alpha_deg > hi else (alpha_deg - lo if alpha_deg < lo else 0.0)
        return float(np.interp(alpha_deg, table["alpha"], table["cl"])), float(np.interp(alpha_deg, table["alpha"], table["cd"])), outside

    def lookup(self, alpha_deg, t_c):
        """(c_l, c_d, degrees outside the measured range) at this angle of attack and thickness ratio."""
        ts = [t["t_c"] for t in self.tables]
        if t_c is None or t_c >= ts[-1]:
            return self._one(self.tables[-1], alpha_deg)
        if t_c <= ts[0]:
            return self._one(self.tables[0], alpha_deg)
        j = next(i for i in range(1, len(ts)) if t_c <= ts[i])
        w = (t_c - ts[j - 1]) / (ts[j] - ts[j - 1])
        a, b = self._one(self.tables[j - 1], alpha_deg), self._one(self.tables[j], alpha_deg)
        return a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1]), a[2] if abs(a[2]) > abs(b[2]) else b[2]

    def alpha_for_cl(self, cl, t_c):
        """Angle of attack (deg) at which the section has this lift coefficient, below its maximum lift."""
        alphas = np.linspace(self.tables[0]["alpha"][0], self.tables[-1]["alpha"][-1], 400)
        cls = [self.lookup(a, t_c)[0] for a in alphas]
        top = int(np.argmax(cls))
        if not cls[0] <= cl <= cls[top]:
            raise ValueError(f"lift coefficient {cl} is outside the section data at thickness ratio {t_c}")
        return brentq(lambda a: self.lookup(a, t_c)[0] - cl, alphas[0], alphas[top], xtol=1e-12)

    def section(self, prandtl_glauert=False):
        """The function the strip theory calls: (alpha_deg, t_c, mach) -> (c_l, c_d, degrees outside the data).
        With prandtl_glauert the lift is multiplied by 1/sqrt(1 - M^2) (Anderson APD p. 82), M held at 0.9 above it;
        this is a sensitivity, the baseline uses the low-speed data as they are."""
        def f(alpha_deg, t_c, mach):
            cl, cd, outside = self.lookup(alpha_deg, t_c)
            if prandtl_glauert:
                cl /= math.sqrt(1.0 - min(mach, 0.9) ** 2)
            return cl, cd, outside
        return f


# ---------------------------------------------------------------- strip theory

def tip_loss(B, x, phi):
    """Prandtl's factor for B blades at x = r/R and inflow angle phi: F = (2/pi) arccos(exp(-(B/2)(1 - x)/(x sin(phi))))."""
    return 2.0 / math.pi * math.acos(math.exp(-B / 2.0 * (1.0 - x) / (x * math.sin(phi))))


def solve_station(V, omega, R, B, rho, x, chord, beta_deg, t_c, section, a_sound):
    """One blade station at x = r/R: the inflow angle phi at which the blade-element forces equal the momentum change of
    the annulus, found by bracketing (scipy brentq). Raises ValueError if there is no such angle.

    With sigma = B c/(2 pi r), C_n = c_l cos(phi) - c_d sin(phi) and C_t = c_l sin(phi) + c_d cos(phi), the two balances
    in the module docstring give
        k  = a/(1 + a)   = sigma C_n/(4 F sin^2(phi)),
        k' = a'/(1 - a') = sigma C_t/(4 F sin(phi) cos(phi)),
    and the velocity triangle of Fig. L.4, tan(phi) = V (1 + a)/(Omega r (1 - a')), becomes the residual
        sin(phi) (1 - k) - (V/(Omega r)) cos(phi) (1 + k') = 0.
    At V = 0 the residual is sin(phi)(1 - k): the static momentum balance. The relative speed is taken from the
    tangential side, W = Omega r (1 - a')/cos(phi), so that it also holds at V = 0.
    section(alpha_deg, t_c, mach) gives c_l, c_d and how far the angle is outside the data; the Mach number passed to it
    is that of sqrt(V^2 + (Omega r)^2), without interference (zero if a_sound is zero).
    Returns phi, a, a_rot, F, alpha_deg, cl, cd, outside_deg, W, mach (relative, with interference), dT_dr, dQ_dr."""
    r = x * R
    lam = V / (omega * r)
    sigma = B * chord / (2.0 * math.pi * r)
    mach_0 = math.hypot(V, omega * r) / a_sound if a_sound else 0.0

    def state(phi):
        cl, cd, outside = section(beta_deg - math.degrees(phi), t_c, mach_0)
        F = tip_loss(B, x, phi)
        cn, ct = cl * math.cos(phi) - cd * math.sin(phi), cl * math.sin(phi) + cd * math.cos(phi)
        k = sigma * cn / (4.0 * F * math.sin(phi) ** 2)
        k_rot = sigma * ct / (4.0 * F * math.sin(phi) * math.cos(phi))
        return cl, cd, outside, F, cn, ct, k, k_rot

    def residual(phi):
        k, k_rot = state(phi)[6:]
        return math.sin(phi) * (1.0 - k) - lam * math.cos(phi) * (1.0 + k_rot)

    # the first change of sign from the small-angle side, on a 0.5 deg grid, then brentq inside it
    grid = np.linspace(PHI_MIN, PHI_MAX, 181)
    values = [residual(p) for p in grid]
    i = next((j for j in range(1, len(grid)) if values[j - 1] * values[j] <= 0.0), None)
    if i is None:
        raise ValueError(f"station r/R = {x:.4f}: no inflow angle balances the annulus (blade angle {beta_deg:.2f} deg, "
                         f"V/(Omega r) = {lam:.3f})")
    phi = brentq(residual, grid[i - 1], grid[i], xtol=1e-13, rtol=1e-13)
    cl, cd, outside, F, cn, ct, k, k_rot = state(phi)
    if abs(residual(phi)) > 1e-9 or not math.isfinite(k):
        raise ValueError(f"station r/R = {x:.4f}: the inflow angle did not converge (residual {residual(phi):.2e})")
    a_rot = k_rot / (1.0 + k_rot)
    W = omega * r * (1.0 - a_rot) / math.cos(phi)
    q_c = 0.5 * rho * W ** 2 * B * chord
    return {"x": x, "phi": phi, "a": (k / (1.0 - k) if V > 0.0 else None), "a_rot": a_rot, "F": F,
            "alpha_deg": beta_deg - math.degrees(phi), "cl": cl, "cd": cd, "outside_deg": outside, "W": W,
            "mach": W / a_sound if a_sound else 0.0, "dT_dr": q_c * cn, "dQ_dr": q_c * ct * r}


def integrate(x, y, R):
    """Trapezoid rule over the stations and a last panel to the tip, where the loading is zero."""
    x, y = np.append(np.asarray(x, float), 1.0), np.append(np.asarray(y, float), 0.0)
    return float(np.sum((y[1:] + y[:-1]) / 2.0 * np.diff(x))) * R


def propeller(V, rpm, D, B, rho, a_sound, x, c_over_D, beta_deg, t_c, section):
    """Thrust, torque, power and efficiency of a propeller from its stations (x = r/R below 1, chord/D, blade angle in
    degrees, thickness ratio). (L.11) and (L.13), p. 614-615, are the two integrals; eta = V F/(Omega Q) = J C_T/C_P.
    C_T = T/(rho n^2 D^4) and C_P = P/(rho n^3 D^5) are the N.A.C.A. forms, of which (L.17) and (L.18) are the
    engineering-unit versions."""
    n, R = rpm / 60.0, D / 2.0
    omega = 2.0 * math.pi * n
    stations = [solve_station(V, omega, R, B, rho, xi, ci * D, bi, ti, section, a_sound)
                for xi, ci, bi, ti in zip(x, c_over_D, beta_deg, t_c)]
    T = integrate(x, [s["dT_dr"] for s in stations], R)
    Q = integrate(x, [s["dQ_dr"] for s in stations], R)
    P = omega * Q
    return {"V_fps": V, "rpm": rpm, "J": V / (n * D), "thrust_lb": T, "torque_lbft": Q, "power_hp": P / HP,
            "C_T": T / (rho * n ** 2 * D ** 4), "C_P": P / (rho * n ** 3 * D ** 5), "eta": (T * V / P if P > 0.0 else 0.0),
            "stations": stations}


def pitch_for_power(hp, V, rpm, D, B, rho, a_sound, x, c_over_D, twist_deg, t_c, section, start_deg=-30.0, stop_deg=30.0):
    """A constant-speed propeller: the whole blade is turned by one angle until it absorbs the shaft power hp at this
    speed and rpm. The pitch change is stepped up from start_deg in 1 deg steps to the first step that brackets the
    power (the branch below the stall), then solved by brentq. Raises ValueError if no step brackets it. A step
    at which a station has no solution is skipped."""
    twist = np.asarray(twist_deg, float)

    def run(delta):
        return propeller(V, rpm, D, B, rho, a_sound, x, c_over_D, twist + delta, t_c, section)

    def excess(delta):
        return run(delta)["power_hp"] - hp

    previous = None
    for delta in np.arange(start_deg, stop_deg + 0.5, 1.0):
        try:
            value = excess(delta)
        except ValueError:
            previous = None
            continue
        if previous is not None and previous[1] < 0.0 <= value:
            root = brentq(excess, previous[0], delta, xtol=1e-10, rtol=1e-12)
            return dict(run(root), pitch_change_deg=float(root))
        previous = (delta, value)
    raise ValueError(f"no blade pitch between {start_deg} and {stop_deg} deg of change absorbs the shaft power {hp} hp")


def design_twist(cl_design, V, rpm, D, B, rho, x, c_over_D, t_c, sections):
    """Blade angle (deg) of each station such that it works at cl_design at this speed, rpm and density: the section's
    angle of attack for that lift is added to the inflow angle the station then has (spec P6 step 1)."""
    omega, R = 2.0 * math.pi * rpm / 60.0, D / 2.0
    beta = []
    for xi, ci, ti in zip(x, c_over_D, t_c):
        alpha = sections.alpha_for_cl(cl_design, ti)
        cl, cd, _ = sections.lookup(alpha, ti)
        fixed = lambda alpha_deg, t, mach, cl=cl, cd=cd: (cl, cd, 0.0)          # the design lift and its drag at any angle
        beta.append(math.degrees(solve_station(V, omega, R, B, rho, xi, ci * D, 0.0, ti, fixed, 0.0)["phi"]) + alpha)
    return np.array(beta)

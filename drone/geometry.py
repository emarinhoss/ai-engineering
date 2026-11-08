"""Planform, tail and fuselage geometry. SI units; x is positive aft."""
from dataclasses import dataclass

import numpy as np


def _trapz(f, x):
    """Trapezoid rule of f over x (works on any numpy version)."""
    f = np.asarray(f, dtype=float)
    x = np.asarray(x, dtype=float)
    return float(np.sum(0.5 * (f[1:] + f[:-1]) * np.diff(x)))


def _int_product(f, g, x):
    """Exact integral of f*g over x for piecewise-linear f and g (Simpson per segment)."""
    f = np.asarray(f, dtype=float)
    g = np.asarray(g, dtype=float)
    fm = 0.5 * (f[1:] + f[:-1])
    gm = 0.5 * (g[1:] + g[:-1])
    return float(np.sum(np.diff(x) / 6.0 * (f[:-1] * g[:-1] + 4.0 * fm * gm + f[1:] * g[1:])))


@dataclass(frozen=True)
class Planform:
    """Half-wing planform: nodes eta = y/(b/2) from 0 (root) to 1 (tip).

    chord and x_le (leading-edge x) are given at the nodes; x_ref is the moment reference x.
    """
    span: float
    eta: tuple
    chord: tuple
    x_le: tuple
    x_ref: float

    def __post_init__(self):
        for name in ("eta", "chord", "x_le"):
            object.__setattr__(self, name, tuple(float(v) for v in getattr(self, name)))
        object.__setattr__(self, "span", float(self.span))
        object.__setattr__(self, "x_ref", float(self.x_ref))

    def chord_at(self, eta):
        """Chord at eta by linear interpolation."""
        return np.interp(eta, self.eta, self.chord)

    def x_le_at(self, eta):
        """Leading-edge x at eta by linear interpolation."""
        return np.interp(eta, self.eta, self.x_le)


def tapered(span, aspect_ratio, taper_ratio, sweep_le_rad=0.0):
    """Trapezoidal wing: S = b^2/AR, c_root = 2 S / (b (1 + lambda)), c_tip = lambda c_root.

    x_ref is the quarter chord of the MAC, which sits at eta_mac = (1 + 2 lambda)/(3 (1 + lambda)).
    """
    area = span**2 / aspect_ratio
    c_root = 2.0 * area / (span * (1.0 + taper_ratio))
    c_tip = taper_ratio * c_root
    x_tip = 0.5 * span * np.tan(sweep_le_rad)
    eta_mac = (1.0 + 2.0 * taper_ratio) / (3.0 * (1.0 + taper_ratio))
    c_mac = 2.0 / 3.0 * c_root * (1.0 + taper_ratio + taper_ratio**2) / (1.0 + taper_ratio)
    x_ref = eta_mac * x_tip + 0.25 * c_mac
    return Planform(span, (0.0, 1.0), (c_root, c_tip), (0.0, x_tip), x_ref)


def elliptic(span, aspect_ratio, n_nodes=41):
    """Elliptic chord c = c0 sqrt(1 - eta^2), c0 = 4 S/(pi b), straight quarter-chord line."""
    area = span**2 / aspect_ratio
    c0 = 4.0 * area / (np.pi * span)
    eta = np.linspace(0.0, 1.0, n_nodes)
    chord = c0 * np.sqrt(np.maximum(1.0 - eta**2, 0.0))
    x_le = (c0 - chord) / 4.0
    return Planform(span, eta, chord, x_le, c0 / 4.0)


def wing_dict(planform):
    """Wing reference quantities from the planform nodes.

    S uses the trapezoid rule over y; the products are integrated exactly for piecewise-linear
    c and x_le.

    S = 2 int c dy, c_mac = (2/S) int c^2 dy, x_mac_le = (2/S) int x_le c dy.
    """
    y = 0.5 * planform.span * np.asarray(planform.eta)
    c = np.asarray(planform.chord)
    x_le = np.asarray(planform.x_le)
    area = 2.0 * _trapz(c, y)
    return {
        "S": area,
        "b": planform.span,
        "AR": planform.span**2 / area,
        "c_root": float(c[0]),
        "c_tip": float(c[-1]),
        "c_mean": area / planform.span,
        "c_mac": 2.0 / area * _int_product(c, c, y),
        "x_mac_le": 2.0 / area * _int_product(x_le, c, y),
    }


def tail(wing, fixed):
    """Tail sizing by volume coefficients.

    arm = k c_mac, S_h = V_H S c_mac/arm, S_v = V_V S b/arm.
    """
    rules = fixed["rules"]
    arm = rules["tail_arm_chords"] * wing["c_mac"]
    s_h = rules["tail_volume_horizontal"] * wing["S"] * wing["c_mac"] / arm
    s_v = rules["tail_volume_vertical"] * wing["S"] * wing["b"] / arm
    return {"S_h": s_h, "S_v": s_v, "arm": arm}


def fuselage(volume_m3, fineness):
    """Ellipsoid of revolution: V = pi/6 d^2 L with L = fineness d.

    So d = (6 V/(pi fineness))^(1/3).

    Wetted area is the closed form for a prolate spheroid with semi-axes a = L/2, r = d/2:
    S = 2 pi r^2 (1 + (a/(r e)) asin(e)), e = sqrt(1 - r^2/a^2). Fineness 1 is a sphere.
    """
    d = (6.0 * volume_m3 / (np.pi * fineness)) ** (1.0 / 3.0)
    length = fineness * d
    a = 0.5 * length
    r = 0.5 * d
    if fineness == 1.0:
        wetted = 4.0 * np.pi * r**2
    else:
        e = np.sqrt(1.0 - (r / a) ** 2)
        wetted = 2.0 * np.pi * r**2 * (1.0 + a / (r * e) * np.arcsin(e))
    return {"length": float(length), "diameter": float(d), "wetted_area": float(wetted),
            "volume": float(volume_m3)}


def build(params, fixed, mtow_guess=None):
    """Assemble wing, tail, fuselage and wetted areas for a design.

    Wetted area of a lifting surface: 2 S (1 + 0.25 t/c) (Raymer, Aircraft Design: A Conceptual
    Approach, thin-surface approximation), t/c = thickness_pct/100 for the wing, 0.10 for the tails.
    Fuselage volume = battery volume + payload volume (0.5 L per 0.5 kg, density 1000 kg/m^3).
    mtow_guess defaults to 4 x payload mass until the evaluation loop supplies the closed mass.
    """
    planform = tapered(params["span_m"], params["aspect_ratio"], params["taper_ratio"])
    wing = wing_dict(planform)
    tl = tail(wing, fixed)
    payload = fixed["rules"]["payload_mass_kg"]
    if mtow_guess is None:
        mtow_guess = 4.0 * payload
    battery = fixed["battery"]
    pack_energy = battery["pack_specific_energy_Wh_per_kg"]
    energy_density = battery["volumetric_energy_density_Wh_per_L"]
    battery_volume = params["battery_fraction"] * mtow_guess * pack_energy / energy_density / 1000.0
    payload_volume = payload / 1000.0
    fus = fuselage(battery_volume + payload_volume, fixed["rules"]["fuselage_fineness"])
    t_wing = params["thickness_pct"] / 100.0
    wetted = {
        "wing": 2.0 * wing["S"] * (1.0 + 0.25 * t_wing),
        "htail": 2.0 * tl["S_h"] * (1.0 + 0.25 * 0.10),
        "vtail": 2.0 * tl["S_v"] * (1.0 + 0.25 * 0.10),
        "fuselage": fus["wetted_area"],
    }
    return {"planform": planform, "wing": wing, "tail": tl, "fuselage": fus, "wetted_areas": wetted}

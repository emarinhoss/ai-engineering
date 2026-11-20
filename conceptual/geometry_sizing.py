"""Geometry sizing: wing and tail planforms, fuselage length, tails, propeller, tyres, engine scaling
(Raymer ch. 6, 7, 10, 11). Lengths in ft unless a name ends in _in."""
import math
from dataclasses import dataclass

# Raymer Table 6.3, p. 110: fuselage length = a W0^C (ft, W0 in lb)
TABLE_6_3 = {
    "general_aviation_single": (4.37, 0.23),
    "homebuilt_composite": (3.50, 0.23),
    "twin_turboprop": (0.37, 0.51),
}
# Raymer Table 6.4, p. 112: typical tail volume coefficients (horizontal, vertical)
TABLE_6_4 = {
    "general_aviation_single": (0.70, 0.04),
    "homebuilt": (0.50, 0.04),
    "sailplane": (0.50, 0.02),
}
# Raymer p. 112-113: tail arm as a fraction of fuselage length
TAIL_ARM_FRACTION = {"front_propeller": 0.60, "wing_engines": 0.525, "aft_engine": 0.475}
# Raymer Table 10.4, p. 224: turboprop statistical model X = a bhp^b, valid 400 to 5,000 bhp
TURBOPROP_MODEL = {"weight_lb": (1.67, 0.803), "length_in": (4.14, 0.373),
                   "diameter_in": (9.48, 0.120)}
TURBOPROP_BHP_RANGE = (400.0, 5000.0)
# Raymer Table 11.1, p. 233: main-wheel diameter and width (in) = A W_w^B, general aviation
TYRE_GA = {"diameter": (1.51, 0.349), "width": (0.7150, 0.312)}


@dataclass(frozen=True)
class Trapezoid:
    """A straight-tapered lifting surface from (7.5)-(7.9), p. 139-140."""
    area: float
    aspect_ratio: float
    taper: float

    @property
    def span(self):                       # (7.5)
        return math.sqrt(self.aspect_ratio * self.area)

    @property
    def root_chord(self):                 # (7.6)
        return 2.0 * self.area / (self.span * (1.0 + self.taper))

    @property
    def tip_chord(self):                  # (7.7)
        return self.taper * self.root_chord

    @property
    def mac(self):                        # (7.8)
        lam = self.taper
        return (2.0 / 3.0) * self.root_chord * (1.0 + lam + lam ** 2) / (1.0 + lam)

    @property
    def mac_y(self):                      # (7.9), spanwise station of the MAC from the root
        lam = self.taper
        return (self.span / 6.0) * (1.0 + 2.0 * lam) / (1.0 + lam)


def vertical_tail_span(area, aspect_ratio):
    """A vertical tail's aspect ratio is height^2/area (p. 76), so its height is sqrt(A S)."""
    return math.sqrt(aspect_ratio * area)


def fuselage_length(W0, category):
    """Statistical fuselage length a W0^C (Table 6.3, p. 110), ft."""
    a, c = TABLE_6_3[category]
    return a * W0 ** c


def vertical_tail_area(c_vt, span_w, area_w, arm_vt):
    """S_VT = c_VT b_W S_W / L_VT (6.28), p. 111."""
    return c_vt * span_w * area_w / arm_vt


def horizontal_tail_area(c_ht, mac_w, area_w, arm_ht):
    """S_HT = c_HT C_W S_W / L_HT (6.29), p. 111."""
    return c_ht * mac_w * area_w / arm_ht


def propeller_diameter_statistical_in(hp, blades=2):
    """Two-blade propeller diameter d = 22 Hp^(1/4) inches (10.23), p. 219."""
    if blades != 2:
        raise ValueError("only the two-blade relation of (10.23) is in the library notes")
    return 22.0 * hp ** 0.25


def helical_tip_speed(V, rpm, diameter_ft):
    """Helical tip speed sqrt(V_tip^2 + V^2) with V_tip = pi n d / 60 ((10.21)-(10.22), p. 219)."""
    return math.sqrt((math.pi * rpm * diameter_ft / 60.0) ** 2 + V ** 2)


def max_diameter_for_tip_speed(V, rpm, tip_limit):
    """Largest diameter (ft) with helical tip speed at most tip_limit (DR-1, p. 569)."""
    return math.sqrt(tip_limit ** 2 - V ** 2) * 60.0 / (math.pi * rpm)


def turboprop_statistical(bhp):
    """Nominal turboprop weight (lb), length and diameter (in) from Table 10.4, p. 224.
    Returns the values and whether bhp lies inside the table's stated range (400 to 5,000)."""
    out = {k: a * bhp ** b for k, (a, b) in TURBOPROP_MODEL.items()}
    lo, hi = TURBOPROP_BHP_RANGE
    out["in_range"] = lo <= bhp <= hi
    return out


def turboprop_scaled(actual, bhp_actual, bhp_new):
    """Rubber-engine scaling X_new = X_actual SF^b, SF = bhp_new/bhp_actual (Table 10.3, p. 224).
    Turboprop exponents: weight 0.803, diameter 0.120, length 0.373 (Table 10.3 prints 3.730, a
    misplaced decimal point flagged in the notes; Table 10.4's 0.373 is used)."""
    sf = bhp_new / bhp_actual
    return {"weight_lb": actual["weight_lb"] * sf ** 0.803,
            "length_in": actual["length_in"] * sf ** 0.373,
            "diameter_in": actual["diameter_in"] * sf ** 0.120}


def main_tyre_in(weight_on_wheel):
    """Main-wheel tyre diameter and width (in), Table 11.1, p. 233, general aviation."""
    return {k: a * weight_on_wheel ** b for k, (a, b) in TYRE_GA.items()}

"""Preliminary design P4: the methods of the balance and longitudinal stability package (no run, no files written).

Spec: docs/specs/task12_preliminary_design.md, package P4. Units: ft, lb, s, rad. x is aft from the nose.

Sources (record: data/task12/pd_p4_sources.yaml; nothing here is from memory):
- Multhopp, NACA TM 1036, eq. (3.7), p. 11, and Fig. 8: the fuselage moment slope, strip by strip.
- Ribner, NACA WR L-25, Figs. 1, 2 and 6 and eq. (4): the propeller normal force (the open statement of the method
  of Raymer (16.26), p. 428).
- Raymer (16.7)-(16.10), p. 416-417 (trim, neutral point), p. 432-433 (rotation), p. 232-233 (gear), (15.47)-(15.49),
  p. 404 (weights), (6.28)-(6.29), p. 111 (tail volume), as Stage 1 codes them in conceptual/uav.py.
"""
import copy
import math
from pathlib import Path

import numpy as np
import yaml
from scipy.optimize import brentq

from conceptual import geometry_sizing as geo
from conceptual import raymer_aero as aero
from conceptual import raymer_weights as wts
from conceptual import uav
from conceptual.units import KT, RHO0, isa
from geometry3d import sections

REPO = Path(__file__).resolve().parents[1]
SOURCES = REPO / "data/task12/pd_p4_sources.yaml"
CHOICES = REPO / "data/task12/pd_p4_choices.yaml"
SM_MIN, SM_MAX = 0.05, 0.15                     # R13
NOSE_LIMITS, NOSE_OPTIMUM = (0.05, 0.20), (0.08, 0.15)      # Raymer p. 232-233
TOL_NP = 0.03                                   # spec 7.1a: independent neutral point against Stage 1's, MAC


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text())


def val(entry):
    """A choice: either a bare value or {value, band, source}."""
    return entry["value"] if isinstance(entry, dict) else entry


def reading(table, x):
    """A figure reading at x, straight between the read points; outside them it raises (no extrapolation)."""
    t = np.asarray(table, dtype=float)
    if not t[0, 0] <= x <= t[-1, 0]:
        raise ValueError(f"{x:.4g} is outside the read range {t[0, 0]:g} to {t[-1, 0]:g}")
    return float(np.interp(x, t[:, 0], t[:, 1]))


# ---- step 2: fuselage moment slope (Multhopp, TM 1036) -------------------------------------------------------
def figure8_integral(src, scale=1.0):
    """G(xi) = integral from 0 to xi of d(beta)/d(alpha) d(x/t), xi the distance ahead of the wing leading edge in
    wing chords (TM 1036, Fig. 8). Out to the last point of the 'mean' curve G is xi times the mean (the figure's
    own definition); beyond it the 'local' curve is added by the trapezoid rule; beyond the last local point the
    local value is held. Below the first mean point G goes straight to zero. scale multiplies the excess of
    d(beta)/d(alpha) over 1 (Multhopp's conversion to another lift-curve slope); 1 is the figure as drawn."""
    f8 = src["multhopp"]["figure_8"]
    mean = np.asarray(f8["mean_second_reading"], dtype=float)
    local = np.asarray(f8["local_second_reading"], dtype=float)
    xs = [0.0] + list(mean[:, 0])
    G = [0.0] + list(mean[:, 0] * mean[:, 1])
    x_prev, v_prev = xs[-1], float(np.interp(xs[-1], local[:, 0], local[:, 1]))
    for x, v in local[local[:, 0] > xs[-1]]:
        G.append(G[-1] + 0.5 * (v + v_prev) * (x - x_prev))
        xs.append(float(x))
        x_prev, v_prev = float(x), float(v)
    xs, G, last = np.array(xs), np.array(G), v_prev

    def integral(xi):
        xi = np.asarray(xi, dtype=float)
        g = np.where(xi <= xs[-1], np.interp(xi, xs, G), G[-1] + last * (xi - xs[-1]))
        return xi + scale * (g - xi)
    return integral


def lattice_integral(span, aspect_ratio, taper, c_root, z, xi_max=2.5, n=60):
    """The same G(xi) from the study's own vortex lattice (drone/vlm.py): d(beta)/d(alpha) = 1 - d(eps)/d(alpha) at
    points on the centreline ahead of the root leading edge, at the height z of the fuselage axis above the wing
    plane, summed by the trapezoid rule from the leading edge. A second reading, not the verdict's."""
    from drone import geometry, vlm
    pf = geometry.tapered(span, aspect_ratio, taper)
    xs = np.linspace(0.0, xi_max, n + 1)
    dbda = np.array([1.0 - vlm.downwash_gradient(pf, [[-x * c_root, 0.0, z]], "medium") for x in xs])
    G = np.concatenate([[0.0], np.cumsum(0.5 * (dbda[1:] + dbda[:-1]) * np.diff(xs))])

    def integral(xi):
        return np.interp(xi, xs, G)
    integral.points = {"xi": xs.tolist(), "d_beta_d_alpha": dbda.tolist()}
    return integral


def fuselage_moment(width, length, x_le, chord, x_tail, dah_da, upwash, n=2000):
    """(1/q) dM/d(alpha) = (pi/2) integral over the length of b^2 d(beta)/d(alpha) dx, per radian, nose-up
    (TM 1036 (3.7), p. 11), in ft^3. width(x): fuselage width b at the stations x. d(beta)/d(alpha): ahead of the
    wing leading edge x_le from upwash (G of figure8_integral, in chords); 0 over the chord; behind the trailing
    edge it rises linearly from 0 to dah_da = 1 - d(eps)/d(alpha) at x_tail and stays there (p. 11). Midpoint
    strips; the weight of d(beta)/d(alpha) on each strip is integrated exactly. Returns the parts and the total."""
    edges = np.linspace(0.0, length, n + 1)
    b2 = np.asarray(width(0.5 * (edges[:-1] + edges[1:])), dtype=float) ** 2
    a0, a1 = np.minimum(edges[:-1], x_le), np.minimum(edges[1:], x_le)
    w_ahead = chord * (upwash((x_le - a0) / chord) - upwash((x_le - a1) / chord))
    x_te = x_le + chord

    def H(x):                                   # integral of d(beta)/d(alpha) from the trailing edge to x
        x = np.maximum(x, x_te)
        return dah_da * ((np.minimum(x, x_tail) - x_te) ** 2 / (2.0 * (x_tail - x_te)) + np.maximum(x - x_tail, 0.0))
    w_behind = H(edges[1:]) - H(edges[:-1])
    ahead, behind = 0.5 * math.pi * float(np.sum(b2 * w_ahead)), 0.5 * math.pi * float(np.sum(b2 * w_behind))
    return {"ahead_of_wing_ft3": ahead, "behind_wing_ft3": behind, "total_ft3": ahead + behind}


# ---- neutral point (Raymer (16.8)-(16.10), p. 417) -----------------------------------------------------------
def cm_alpha(X_cg, CLa_w, X_acw, Cma_fus, tail, X_ach, Fp=0.0, dap=1.0, X_p=0.0):
    """C_m_alpha of (16.8), p. 417. X are stations over the mean chord; tail = eta_h (S_h/S) C_L_alpha_h
    d(alpha_h)/d(alpha); Fp = F_p_alpha/(q S); dap = d(alpha_p)/d(alpha)."""
    return CLa_w * (X_cg - X_acw) + Cma_fus - tail * (X_ach - X_cg) + Fp * dap * (X_cg - X_p)


def neutral_point(CLa_w, X_acw, Cma_fus, tail, X_ach, Fp=0.0, dap=1.0, X_p=0.0):
    """The X_cg at which (16.8) is zero. With Fp = 0 this is (16.9) without its propeller terms, as Stage 1 uses
    it. With a propeller the last term of the denominator carries dap; (16.9) as printed leaves it out (a probable
    misprint, roadmap Appendix A), so (16.8) is solved here and not (16.9) copied."""
    return (CLa_w * X_acw - Cma_fus + tail * X_ach + Fp * dap * X_p) / (CLa_w + tail + Fp * dap)


# ---- propeller normal force (Ribner, WR L-25) ----------------------------------------------------------------
def side_force_factor(b_over_D_03, b_over_D_06, b_over_D_09):
    """S.F.F. = 525 (b/D) at 0.3 R + 525 (b/D) at 0.6 R + 270 (b/D) at 0.9 R (WR L-25 (4), p. 9)."""
    return 525.0 * b_over_D_03 + 525.0 * b_over_D_06 + 270.0 * b_over_D_09


def thrust_coefficient(thrust_lb, rho, V, D):
    """T_c = T / (rho V^2 D^2) (WR L-25, symbols, p. 4)."""
    return thrust_lb / (rho * V ** 2 * D ** 2)


def propeller_normal_force(Tc, beta_075_deg, sff, src):
    """C_Y'psi = f C_Y'psi0: normal force over q and the disc area per radian (WR L-25, p. 6-7). f from Fig. 1 at
    T_c; C_Y'psi0 from Fig. 2 (three blades, Hamilton Standard 3155-6) at the blade angle at 0.75 R, times the
    ratio of Fig. 6 at the blade's side-force factor."""
    r = src["ribner"]
    f = reading(r["figure_1"]["second_reading"], Tc)
    cy0 = reading(r["figure_2"]["three_blades_second_reading"], beta_075_deg)
    ratio = reading(r["side_force_factor"]["figure_6"]["three_blades_second_reading"], sff)
    return {"T_c": Tc, "f": f, "CY_psi0_3155_6": cy0, "side_force_ratio": ratio, "CY_psi": f * cy0 * ratio}


# ---- step 1: weight and balance ------------------------------------------------------------------------------
def tail_planforms(ht_area, vt_area, L):
    """The two tail planforms at the ledger's aspect ratios and tapers ((7.5)-(7.9), p. 139-140; the fin as
    conceptual/uav._geometry builds it)."""
    ht = geo.Trapezoid(ht_area, L["ht_aspect_ratio"], L["ht_taper"])
    lam = L["vt_taper"]
    h = geo.vertical_tail_span(vt_area, L["vt_aspect_ratio"])
    root = 2.0 * vt_area / (h * (1.0 + lam))
    return ht, {"height": h, "root_chord": root, "mac": (2.0 / 3.0) * root * (1 + lam + lam ** 2) / (1 + lam)}


def tail_le_slope(L, which):
    """Leading-edge slope (dx per unit span) of a tail whose trailing edge is straight (at right angles to the
    centreline): all the taper is on the leading edge, (root chord - tip chord)/(half span or height). With the
    planform relations (7.5)-(7.7), p. 139-140, this is 4 (1 - taper)/(A (1 + taper)) for the tailplane and half
    of that form, 2 (1 - taper)/(A (1 + taper)), for the fin, whose aspect ratio is height^2/area."""
    if which == "horizontal":
        return 4.0 * (1.0 - L["ht_taper"]) / (L["ht_aspect_ratio"] * (1.0 + L["ht_taper"]))
    return 2.0 * (1.0 - L["vt_taper"]) / (L["vt_aspect_ratio"] * (1.0 + L["vt_taper"]))


def tail_lift_slope(L, lay):
    """Tailplane lift slope per radian by Raymer (12.6), p. 266, as Stage 1 has it; with a straight trailing edge
    the sweep of the maximum-thickness line (30 % of the chord, NACA four-digit) is 0.7 of the leading edge's."""
    sweep = math.atan(0.7 * tail_le_slope(L, "horizontal")) if lay["tail_te_straight"] else 0.0
    return aero.lift_slope(L["ht_aspect_ratio"], 0.0, L["airfoil_efficiency"], sweep)


def base_layout(d, p3, stations="p3"):
    """r0's layout as a plain dict. stations="p3": payload and avionics at the P3 stations (PD-19);
    "r0": where r0 has them (for the checks against Stage 1)."""
    lay, st = d["layout"], d["stations"]
    moved = {r["item"]: r for r in p3["moved_masses"]["moved"]}
    gear = {g["item"]: g for g in p3["moved_masses"]["gear_up_and_down"]}
    x = (lambda k: moved[k]["station_p3_ft"]) if stations == "p3" else (lambda k: st[k]["x"])
    return {"x_le": lay["x_le"], "arm": d["tail_arm_ft"], "ht_area": d["horizontal_tail"]["area"],
            "vt_area": d["vertical_tail"]["area"], "x_main": lay["x_main"], "x_nose": st["nose_gear"]["x"],
            "payload_x": x("payload"), "avionics_x": x("avionics"), "weights": dict(d["components_lb"]),
            "tail_te_straight": False,
            "nose_gear_up_x": gear["nose gear"]["leg_mid_point_gear_up_ft"],
            "main_gear_up_ahead_ft": gear["main gear"]["station_gear_down_ft"] - gear["main gear"]["leg_mid_point_gear_up_ft"]}


def items(d, L, lay, gear):
    """{component: (weight, station)} of the empty aircraft. Fuselage-fixed items stay at r0's stations; the wing,
    fuel system and sponsons are at 0.40 of the mean chord and the tails at 0.40 of theirs, as in
    conceptual/uav.layout. gear: "down" (wheels at their stations) or "up" (each gear at the mid-point of its
    stowed leg, P3)."""
    mac, st, w = d["wing"]["mac"], d["stations"], lay["weights"]
    x_ac, x_wing = lay["x_le"] + 0.25 * mac, lay["x_le"] + 0.40 * mac
    ht, vt = tail_planforms(lay["ht_area"], lay["vt_area"], L)
    out = {k: (w[k], st[k]["x"]) for k in ("fuselage", "installed_engine", "flight_controls", "hydraulics", "electrical")}
    out["avionics"] = (w["avionics"], lay["avionics_x"])
    for k in ("wing", "fuel_system", "sponsons"):
        out[k] = (w[k], x_wing)
    out["horizontal_tail"] = (w["horizontal_tail"], x_ac + lay["arm"] + 0.15 * ht.mac)
    out["vertical_tail"] = (w["vertical_tail"], x_ac + lay["arm"] + 0.15 * vt["mac"])
    if gear == "down":
        out["nose_gear"], out["main_gear"] = (w["nose_gear"], lay["x_nose"]), (w["main_gear"], lay["x_main"])
    else:
        out["nose_gear"] = (w["nose_gear"], lay["nose_gear_up_x"])
        out["main_gear"] = (w["main_gear"], lay["x_main"] - lay["main_gear_up_ahead_ft"])
    return out


def tanks(d, L, A, choices):
    """Where the fuel is on the loft's wing: between the spars (front spar of the P3 arrangement, rear spar that
    plus the ledger's tank chord fraction), from the fuselage side outward until the needed volume over the
    usable fraction is held, cut into tanks of equal volume. Returns, per tank, its span stations and its centre
    behind the root leading edge (ft); the leading edge is unswept, so the centre is a fraction of the local
    chord, weighted by chord^2 (the tank's section area) along the span."""
    w = d["wing"]
    half, cr, ct = 0.5 * w["span"], w["root_chord"], w["tip_chord"]
    f0 = val(A["arrangement"]["front_spar_chord_fraction"])
    f1 = f0 + L["wing_tank_chord_fraction"]
    xs = np.linspace(f0, f1, 400)
    (xu, zu), (xl, zl) = sections.surfaces(0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, 400))), 0.04, 0.4, 0.15)
    depth = np.interp(xs, xu, zu) - np.interp(xs, xl, zl)         # NACA 4415 (P2), over the chord
    xi_c = float(np.sum(xs * depth) / np.sum(depth))              # centre of the section area between the spars
    k = float(np.mean(depth)) * (f1 - f0)                         # section area between the spars over chord^2
    chord = lambda y: cr + (ct - cr) * y / half
    y0, y_max = 0.5 * d["fuselage"]["diameter"], L["wing_tank_span_fraction"] * half
    vol = lambda ya, yb: k * (chord(yb) ** 3 - chord(ya) ** 3) / (3.0 * (ct - cr) / half)     # integral of k c^2 dy
    need_side = 0.5 * d["fuel_volume_ft3"]["needed"] / L["wing_tank_usable"]
    if need_side > vol(y0, y_max):
        raise ValueError("the fuel does not fit the wing tanks")
    n = choices["balance"]["tanks_per_side"]
    cuts = [y0] + [brentq(lambda y, v=need_side * (i + 1) / n: vol(y0, y) - v, y0, y_max) for i in range(n)]
    out = []
    for ya, yb in zip(cuts[:-1], cuts[1:]):
        y = np.linspace(ya, yb, 2001)
        c = chord(y)
        out.append({"y_from_ft": float(ya), "y_to_ft": float(yb), "gross_ft3_per_side": float(vol(ya, yb)),
                    "centre_behind_root_le_ft": float(xi_c * np.sum(c ** 3) / np.sum(c ** 2))})
    return {"tanks": out, "centre_chord_fraction": xi_c, "spar_fractions": [f0, f1],
            "gross_ft3_per_side": need_side, "available_gross_ft3_per_side": float(vol(y0, y_max))}


def fuel_state(fuel_lb, fuel_full_lb, tk, order, x_le):
    """(fuel weight, fuel moment about the nose) with fuel_lb on board. The tanks (inboard first in tk) hold equal
    shares; order "outboard_first" empties the outermost tank first, "inboard_first" the innermost."""
    n = len(tk["tanks"])
    share = fuel_full_lb / n
    seq = list(range(n - 1, -1, -1)) if order == "outboard_first" else list(range(n))     # the order of emptying
    left, burned, moment = [share] * n, fuel_full_lb - fuel_lb, 0.0
    for i in seq:
        take = min(left[i], burned)
        left[i] -= take
        burned -= take
    for i, t in enumerate(tk["tanks"]):
        moment += left[i] * (x_le + t["centre_behind_root_le_ft"])
    return fuel_lb, moment


def cg(it, payload=None, fuel=(0.0, 0.0), factor=1.0):
    """(weight, centre of gravity). it: items(); payload: (weight, station) or None; fuel: (weight, moment);
    factor multiplies every empty-weight item (the empty-weight band, NR-14)."""
    W = factor * sum(w for w, _ in it.values()) + fuel[0]
    M = factor * sum(w * x for w, x in it.values()) + fuel[1]
    if payload:
        W, M = W + payload[0], M + payload[0] * payload[1]
    return W, M / W


def loadings(d, L, lay, tk, choices):
    """Every loading of spec P4 step 1: fuel from full to empty in steps, in each tank order; payload on and off;
    gear up and down; the empty weight at its band ends and in the middle."""
    b, out = choices["balance"], []
    for gear in ("up", "down"):
        it = items(d, L, lay, gear)
        for factor in b["empty_weight_factors"]:
            for payload in (True, False):
                for order in b["tank_orders"]:
                    for i in range(b["fuel_steps"] + 1):
                        f = d["fuel_lb"] * (1.0 - i / b["fuel_steps"])
                        W, x = cg(it, (d["payload_lb"], lay["payload_x"]) if payload else None,
                                  fuel_state(f, d["fuel_lb"], tk, order, lay["x_le"]), factor)
                        out.append({"gear": gear, "empty_weight_factor": factor, "payload_on": payload,
                                    "tank_order": order, "fuel_lb": f, "weight_lb": W, "x_cg_ft": x})
    return out


def pick(rows, **want):
    """The loadings that match every key given."""
    return [r for r in rows if all(r[k] == v for k, v in want.items())]


# ---- stability of one layout ---------------------------------------------------------------------------------
def stability(d, L, lay, body, src, upwash=None, prop=None, Cma_fus=None):
    """The neutral point of a layout. The wing and tail lift slopes and the lattice downwash are Stage 1's (spec
    7.1c item 3); the fuselage term is Multhopp's on the loft's width (body: geometry3d.fuselage.Body), unless
    Cma_fus (per radian) is given. prop: {"CY_psi": ...} adds the propeller's normal force at the propeller plane.
    Returns stations in ft and the terms."""
    w, mac, S = d["wing"], d["wing"]["mac"], d["wing"]["area"]
    ht, _ = tail_planforms(lay["ht_area"], lay["vt_area"], L)
    x_ac = lay["x_le"] + 0.25 * mac
    x_h = x_ac + lay["arm"]
    dah = 1.0 - uav.lattice_downwash(w["span"], w["aspect_ratio"], L["wing_taper"], lay["arm"], ht.span,
                                     L["tail_height_over_df"] * d["fuselage"]["diameter"])
    CLa_h = tail_lift_slope(L, lay)
    tail = L["tail_eta_h"] * lay["ht_area"] / S * CLa_h * dah
    out = {"x_ac_ft": x_ac, "x_ach_ft": x_h, "dah_da": dah, "tail_term": tail, "CLa_w": d["CL_alpha_wing"], "CLa_h": CLa_h}
    if Cma_fus is None:
        G = upwash or figure8_integral(src)
        fm = fuselage_moment(lambda x: 2.0 * body.lines(x)[0], body.length, lay["x_le"], w["root_chord"], x_h, dah, G)
        Cma_fus = fm["total_ft3"] / (S * mac)
        out["fuselage_moment"] = fm
    out["Cma_fus_per_rad"] = Cma_fus
    args = (d["CL_alpha_wing"], x_ac / mac, Cma_fus, tail, x_h / mac)
    out["x_np_power_off_ft"] = mac * neutral_point(*args)
    if prop:
        Fp = prop["CY_psi"] * (math.pi * d["propeller_diameter_ft"] ** 2 / 4.0) / S
        x_p = body.length + prop["plane_behind_fuselage_ft"]
        out.update({"Fp_alpha_over_qS": Fp, "x_p_ft": x_p, "x_np_power_on_ft": mac * neutral_point(*args, Fp, dah, x_p / mac)})
    return out


# ---- step 4: trim, rotation, gear (Stage 1's equations, conceptual/uav.layout) ---------------------------------
def wing_moment(cm0, A):
    """C_m_w = C_m0 A/(A + 2), unswept (16.16), p. 422."""
    return cm0 * A / (A + 2.0)


def _tail_den(d, L, lay, x_cg):
    mac = d["wing"]["mac"]
    return L["tail_eta_h"] * lay["ht_area"] / d["wing"]["area"] * (lay["x_le"] + 0.25 * mac + lay["arm"] - x_cg) / mac


def tail_cl_trim(d, L, lay, CL, x_cg, cm_w):
    """Tail lift coefficient that trims the lift coefficient CL at the centre of gravity x_cg ((16.7), p. 416,
    without thrust terms: the hub is on the centreline in r0). Positive is an upload."""
    mac = d["wing"]["mac"]
    return (CL * (x_cg - lay["x_le"] - 0.25 * mac) / mac + cm_w) / _tail_den(d, L, lay, x_cg)


def trim_legs(d, L):
    """(name, weight, lift coefficient) at the start and end of every mission leg flown at a speed, at the
    mission altitude, as Stage 1's trim check takes them."""
    rho = isa(L["mission_altitude_ft"])["rho"]
    out = []
    for seg in d["mission"]:
        if seg["V_kt"] > 0.0:
            q = 0.5 * rho * (seg["V_kt"] * KT) ** 2
            out += [(f"{seg['segment']}_{tag}", W, W / (q * d["wing"]["area"])) for tag, W in (("start", seg["W_start"]), ("end", seg["W_end"]))]
    return out


def rotation(d, L, lay, x_cg, cm_w, W=None):
    """Tail lift coefficient needed to lift the nose wheel at 0.8 V_TO at sea level (Raymer p. 432-433), as
    conceptual/uav.layout computes it: wing lift at its a.c., wing moment, the flap's lift increment at its centre
    of pressure, the main-wheel reaction and its rolling friction, and the tail. The main-wheel load is the weight
    less all lift, so the balance is iterated. Thrust has no arm (hub on the centreline; a ledger offset raises)."""
    if L.get("prop_hub_offset_ft", 0.0) != 0.0:
        raise ValueError("P4's trim and rotation leave out the thrust moment; the ledger has a hub offset")
    mac, S = d["wing"]["mac"], d["wing"]["area"]
    W = d["W0_lb"] if W is None else W
    x_ac = lay["x_le"] + 0.25 * mac
    V_r = 0.8 * 1.1 * math.sqrt(2.0 * d["W_S"] / (RHO0 * d["CL_max"]["takeoff"]))
    q = 0.5 * RHO0 * V_r ** 2
    dCL_flap = L["takeoff_flap_fraction"] * L["flap_delta_cl_max"] * L["flap_span_fraction"]
    x_cp = lay["x_le"] + L["flap_cp_fraction"] * mac
    h_cg = d["layout"]["h_cg"]
    den = _tail_den(d, L, lay, x_cg)
    CL_tail = 0.0
    for _ in range(200):
        N_main = max(0.0, W - q * S * (L["cl_ground"] + dCL_flap) - L["tail_eta_h"] * q * lay["ht_area"] * CL_tail)
        cm = (L["cl_ground"] * (x_cg - x_ac) / mac + cm_w + dCL_flap * (x_cg - x_cp) / mac
              - (N_main * (lay["x_main"] - x_cg) + L["rolling_mu"] * N_main * h_cg) / (q * S * mac))
        new = cm / den
        if abs(new - CL_tail) < 1e-12:
            break
        CL_tail = new
    return {"V_kt": V_r / KT, "Cm_without_tail": cm, "CL_tail_needed": CL_tail, "main_wheel_load_lb": N_main}


def nose_load(lay, x_cg):
    """Share of the weight on the nose wheel, static: (x_main - x_cg)/(x_main - x_nose) (Raymer p. 232-233)."""
    return (lay["x_main"] - x_cg) / (lay["x_main"] - lay["x_nose"])


def tipback_deg(d, lay, x_cg):
    """Angle at the main wheel between the vertical and the line to the centre of gravity (Raymer p. 232)."""
    return math.degrees(math.atan((lay["x_main"] - x_cg) / d["layout"]["h_cg"]))


def overturn_deg(d, lay, x_cg):
    """Overturn angle (Raymer p. 232, at most 63 deg) with r0's main-wheel track, as conceptual/uav.overturn_track
    measures it: the centre of gravity lies (x_cg - x_nose) sin(delta) from the line through the nose wheel and a
    main wheel, tan(delta) = half track/(x_main - x_nose); the angle is atan(h_cg / that distance)."""
    delta = math.atan(d["layout"]["gear_track"]["half_track_ft"] / (lay["x_main"] - lay["x_nose"]))
    return math.degrees(math.atan(d["layout"]["h_cg"] / ((x_cg - lay["x_nose"]) * math.sin(delta))))


def propeller_clearance_in(d, L, lay):
    """Propeller tip above the ground with the aircraft turned nose-up about the main wheels by the ledger's
    rotation angle, as conceptual/uav.layout has it (Raymer p. 222: at least 9 in)."""
    th = math.radians(L["rotation_angle_deg_pusher"])
    hub = d["layout"]["h_cg"] * math.cos(th) - (d["fuselage"]["length"] - lay["x_main"]) * math.sin(th)
    return 12.0 * (hub - 0.5 * d["propeller_diameter_ft"])


def forward_limits(d, L, lay, cm_w, W=None):
    """The most forward centre of gravity allowed by rotation (tail lift coefficient at the ledger's
    tail_cl_max_rotation, at the weight W, default the take-off weight) and by trim (tail_cl_max_trim at the
    mission leg with the largest lift coefficient). The tail load is a download at a forward centre of gravity, so
    each is the root of CL_tail + limit = 0. Rotation is a matter of the aircraft on its wheels: it limits the
    loadings with the gear down; trim limits every loading. Returns the two stations and the larger."""
    mac = d["wing"]["mac"]
    x_ac = lay["x_le"] + 0.25 * mac
    lo, hi = x_ac - 3.0 * mac, lay["x_main"] - 1e-6
    rot = brentq(lambda x: rotation(d, L, lay, x, cm_w, W)["CL_tail_needed"] + L["tail_cl_max_rotation"], lo, hi, xtol=1e-10)
    name, _, CL = max(trim_legs(d, L), key=lambda r: r[2])
    trim = brentq(lambda x: tail_cl_trim(d, L, lay, CL, x, cm_w) + L["tail_cl_max_trim"], lo, hi, xtol=1e-10)
    return {"rotation_ft": rot, "trim_ft": trim, "trim_leg": name, "trim_CL": CL, "forward_limit_ft": max(rot, trim)}


# ---- PD-20: the tail clear of the propeller disc, with the wing position ---------------------------------------
def tail_rearmost(d, L, lay):
    """Rearmost station of each tail inside the propeller disc's radius. r0's planforms (tail_te_straight False):
    the loft puts each root leading edge a quarter of the mean chord ahead of the tail arm's station, with an
    unswept (tailplane) or swept-back (fin) leading edge and a taper that brings the trailing edge forward toward
    the tip, so the root trailing edge is the rearmost point: x_ac + arm - mac/4 + root chord. Straight trailing
    edge: the trailing edge is at one station, that of the mean chord's: x_ac + arm + 3/4 mac."""
    ht, vt = tail_planforms(lay["ht_area"], lay["vt_area"], L)
    x = lay["x_le"] + 0.25 * d["wing"]["mac"] + lay["arm"]
    if lay["tail_te_straight"]:
        return {"horizontal_tail": x + 0.75 * ht.mac, "vertical_tail": x + 0.75 * vt["mac"]}
    return {"horizontal_tail": x - 0.25 * ht.mac + ht.root_chord, "vertical_tail": x - 0.25 * vt["mac"] + vt["root_chord"]}


def retail(d, L, lay0, x_le, x_limit, straight_te):
    """The layout with the wing leading edge at x_le and both tails moved, as one, until the rearmost tail point
    is at x_limit, with the tail areas scaled to keep both volume coefficients ((6.28), (6.29), p. 111: area times
    arm constant, the wing being unchanged) and the weights of the tails and fuselage by the ratios of (15.47),
    (15.48) and (15.49), p. 404, as conceptual/raymer_weights.py codes them. straight_te: the tails' trailing
    edges are made straight (PD-20); the tailplane's weight then carries its quarter-chord sweep, the fin's does
    not (Stage 1 weighs r0's swept fin as unswept). Raises ValueError if no arm puts the tail at x_limit."""
    lay = copy.deepcopy(lay0)
    lay["x_le"], lay["tail_te_straight"] = x_le, straight_te

    def over(arm):
        lay["arm"] = arm
        lay["ht_area"], lay["vt_area"] = lay0["ht_area"] * lay0["arm"] / arm, lay0["vt_area"] * lay0["arm"] / arm
        return max(tail_rearmost(d, L, lay).values()) - x_limit
    over(brentq(over, 0.3 * lay0["arm"], 2.0 * lay0["arm"], xtol=1e-12))
    w0, w = lay0["weights"], lay["weights"]
    sweep = math.atan(0.75 * tail_le_slope(L, "horizontal")) if straight_te else 0.0     # quarter-chord line
    ht_w = lambda S, sw: wts.horizontal_tail(1.0, 1.0, 1.0, S, L["tail_t_c"], L["ht_aspect_ratio"], sw, L["ht_taper"])
    vt_w = lambda S: wts.vertical_tail(0.0, 1.0, 1.0, 1.0, S, L["tail_t_c"], L["vt_aspect_ratio"], 0.0, L["vt_taper"])
    fus_w = lambda arm: wts.fuselage(1.0, 1.0, 1.0, arm, 1.0, 1.0)
    w["horizontal_tail"] = w0["horizontal_tail"] * ht_w(lay["ht_area"], sweep) / ht_w(lay0["ht_area"], 0.0)
    w["vertical_tail"] = w0["vertical_tail"] * vt_w(lay["vt_area"]) / vt_w(lay0["vt_area"])
    w["fuselage"] = w0["fuselage"] * fus_w(lay["arm"]) / fus_w(lay0["arm"])
    return lay


def place_main_gear(d, L, lay, tk, choices):
    """Stage 1's tipback rule (Raymer p. 232): the main wheels the tipback angle behind the aftmost centre of
    gravity with the gear down, payload on, nominal empty weight, over every fuel state; iterated, because the
    main gear's own weight is at the wheels. Changes lay["x_main"]."""
    tb = d["layout"]["h_cg"] * math.tan(math.radians(L["tipback_angle_deg"]))
    for _ in range(100):
        rows = pick(loadings(d, L, lay, tk, choices), gear="down", payload_on=True, empty_weight_factor=1.0)
        new = max(r["x_cg_ft"] for r in rows) + tb
        if abs(new - lay["x_main"]) < 1e-10:
            break
        lay["x_main"] = new
    return lay


def cg_ends(d, L, lay, tk, choices, gear="up", factor=1.0):
    """(full-fuel, empty-fuel) centre of gravity with the payload on."""
    rows = pick(loadings(d, L, lay, tk, choices), gear=gear, payload_on=True, empty_weight_factor=factor,
                tank_order=choices["balance"]["tank_orders"][0])
    return rows[0]["x_cg_ft"], rows[-1]["x_cg_ft"]


def solve_r1(d, L, lay0, tk, choices, body, src, propeller_plane_x, clearance=None, retail_tail=True, straight_te=True):
    """Row 5 and PD-20. The wing position at which the mean of the full-fuel and empty-fuel static margins
    (payload on, gear up, nominal empty weight, independent neutral point, power off) is the middle of R13, with
    the tails clear of the propeller disc by `clearance` (default: the choice file's) and the main wheels by the
    tipback rule. straight_te=False keeps r0's tail planforms (the first form of PD-20). retail_tail=False keeps
    r0's tail where it is on the wing (row 5 alone: the wing position, the tail still in the disc).
    Returns (layout, stability); raises ValueError if no wing position does it."""
    clr = val(choices["r1"]["propeller_clearance_ft"]) if clearance is None else clearance
    target = 0.5 * (SM_MIN + SM_MAX)
    mac = d["wing"]["mac"]

    def build(x_le):
        lay = retail(d, L, lay0, x_le, propeller_plane_x - clr, straight_te) if retail_tail else dict(copy.deepcopy(lay0), x_le=x_le)
        lay["x_main"] = lay0["x_main"] + x_le - lay0["x_le"]              # a first guess for the tipback loop
        place_main_gear(d, L, lay, tk, choices)
        st = stability(d, L, lay, body, src)
        full, empty = cg_ends(d, L, lay, tk, choices)
        return lay, st, (st["x_np_power_off_ft"] - 0.5 * (full + empty)) / mac
    x_le = brentq(lambda x: build(x)[2] - target, lay0["x_le"], lay0["x_le"] + 3.0, xtol=1e-8)
    lay, st, sm = build(x_le)
    st["mean_static_margin"] = sm
    return lay, st


def scan_wing_positions(d, L, lay0, tk, choices, body, src, propeller_plane_x, cm_w, shifts, **kw):
    """One row per wing shift (ft aft of r0's): the tail of solve_r1's form at that wing position, the static
    margins at the full-fuel and empty-fuel centre of gravity and the tail lift coefficient at rotation. Shows
    whether a form of the tail can reach R13's middle at all; a shift with no tail is recorded as such."""
    clr = val(choices["r1"]["propeller_clearance_ft"]) if kw.get("clearance") is None else kw["clearance"]
    mac, rows = d["wing"]["mac"], []
    for s in shifts:
        try:
            lay = retail(d, L, lay0, lay0["x_le"] + s, propeller_plane_x - clr, kw.get("straight_te", True))
        except ValueError:
            rows.append({"wing_shift_ft": s, "tail": "no arm puts the tail clear with the volume coefficients kept"})
            continue
        lay["x_main"] = lay0["x_main"] + s
        place_main_gear(d, L, lay, tk, choices)
        x_np = stability(d, L, lay, body, src)["x_np_power_off_ft"]
        full, empty = cg_ends(d, L, lay, tk, choices)
        fwd = min(cg_ends(d, L, lay, tk, choices, gear="down"))
        rows.append({"wing_shift_ft": s, "arm_ft": lay["arm"], "ht_area_ft2": lay["ht_area"], "vt_area_ft2": lay["vt_area"],
                     "sm_full": (x_np - full) / mac, "sm_empty": (x_np - empty) / mac,
                     "CL_tail_rotation": rotation(d, L, lay, fwd, cm_w)["CL_tail_needed"]})
    return rows


# ---- verdicts ------------------------------------------------------------------------------------------------
def inside(value, lo, hi):
    return "pass" if lo <= value <= hi else "fail"


def envelope(d, L, lay, rows, x_np, cm_w):
    """Acceptance rows 3 and 4 on a set of loadings: every centre of gravity between its forward limit and the aft
    limit (x_np less 0.05 MAC); the nose-wheel load of every gear-down loading inside 5 to 20 %. The forward limit
    is the trim limit, and with the gear down the rotation limit at the loading's own weight if that is further
    aft. Each loading gets its limits, its static margin and, gear down, its nose load, tipback and overturn
    angles. Returns the limits (rotation at the take-off weight), the failing loadings by group and the verdicts."""
    mac = d["wing"]["mac"]
    fwd = forward_limits(d, L, lay, cm_w)
    aft = x_np - SM_MIN * mac
    for r in rows:
        r["static_margin"] = (x_np - r["x_cg_ft"]) / mac
        r["forward_limit_ft"] = fwd["trim_ft"]
        if r["gear"] == "down":
            r["forward_limit_ft"] = forward_limits(d, L, lay, cm_w, r["weight_lb"])["forward_limit_ft"]
        r["inside_envelope"] = bool(r["forward_limit_ft"] <= r["x_cg_ft"] <= aft)
        r["too_far"] = "aft" if r["x_cg_ft"] > aft else ("forward" if r["x_cg_ft"] < r["forward_limit_ft"] else None)
        if r["gear"] == "down":
            r["nose_load"] = nose_load(lay, r["x_cg_ft"])
            r["tipback_deg"], r["overturn_deg"] = tipback_deg(d, lay, r["x_cg_ft"]), overturn_deg(d, lay, r["x_cg_ft"])
    down = [r for r in rows if r["gear"] == "down"]

    def group(payload, factor=None):
        g = [r for r in rows if r["payload_on"] == payload and factor in (None, r["empty_weight_factor"])]
        gd = [r for r in g if r["gear"] == "down"]
        return {"loadings": len(g), "outside_envelope": sum(not r["inside_envelope"] for r in g),
                "too_far_aft": sum(r["too_far"] == "aft" for r in g), "too_far_forward": sum(r["too_far"] == "forward" for r in g),
                "x_cg_min_ft": min(r["x_cg_ft"] for r in g), "x_cg_max_ft": max(r["x_cg_ft"] for r in g),
                "static_margin_min": min(r["static_margin"] for r in g), "static_margin_max": max(r["static_margin"] for r in g),
                "nose_load_min": min(r["nose_load"] for r in gd), "nose_load_max": max(r["nose_load"] for r in gd),
                "nose_load_outside_limits": sum(not NOSE_LIMITS[0] <= r["nose_load"] <= NOSE_LIMITS[1] for r in gd),
                "nose_load_outside_optimum": sum(not NOSE_OPTIMUM[0] <= r["nose_load"] <= NOSE_OPTIMUM[1] for r in gd),
                "tipback_min_deg": min(r["tipback_deg"] for r in gd), "overturn_max_deg": max(r["overturn_deg"] for r in gd)}
    on, off = group(True), group(False)
    return {"forward": fwd, "aft_limit_ft": aft, "x_np_ft": x_np, "payload_on": on, "payload_off": off,
            "payload_on_by_empty_weight_factor": {f"{f:g}": group(True, f) for f in sorted({r["empty_weight_factor"] for r in rows})},
            "row3": "pass" if on["outside_envelope"] + off["outside_envelope"] == 0 else "fail",
            "row3_payload_on_only": "pass" if on["outside_envelope"] == 0 else "fail",
            "row4": "pass" if on["nose_load_outside_limits"] + off["nose_load_outside_limits"] == 0 else "fail",
            "row4_payload_on_only": "pass" if on["nose_load_outside_limits"] == 0 else "fail",
            "gear_down_loadings": len(down)}

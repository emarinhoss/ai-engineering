"""Preliminary design P5: loads. A second text of the gust formula, an alleviation factor from a time integration,
the negative manoeuvre and the V-n diagram of r0, and the payload-off operating limit (spec P5, NR-18).

    python -m prelim.p5_loads --out runs/task12/pd/<date>/p5 [--report docs/validation/<date>_task12_pd_p5.md]
    python -m prelim.p5_loads --out runs/task12/pd/<date>/p5 --report ... --report-only

Run on Opus 5.5 under owner ruling PD-22: not yet Fable-reviewed.

Sources (all in data/task12/pd_p5_sources.yaml, opened 2026-11-28):
  EASA CS-23 Amendment 4, 23.333 (gust and manoeuvre envelope) and 23.341(c) (gust load factor). No FAA text
  could be opened; the hosts tried are listed in the file.
  NACA Report 1206 (Pratt and Walker, 1954): the plunge equation (2), the indicial functions (5) and (6), the
  one-minus-cosine gust (7), the gust factor (8) and its fit (9).
  Library: Raymer (14.4)-(14.8), p. 339, as coded in conceptual/raymer_loads.py; (12.15), p. 270; Fig. 14.3,
  p. 337. Anderson APD (6.54), p. 343.
r0, its ledger, P2's record and P4b's record are read and not changed. Units: ft, lb, s, slug; speeds EAS.
"""
import argparse
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import yaml
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from conceptual import raymer_loads as loads
from conceptual.units import KT, RHO0, isa
from measurement import stage3_perf as sp
from measurement import vn_check
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
SOURCES = REPO / "data/task12/pd_p5_sources.yaml"
R0 = REPO / "runs/task12/pd/2026-11-27/p0/r0"
P2_RECORD = REPO / "runs/task12/pd/2026-11-27/p2b/p2.json"
P4B_RECORD = REPO / "runs/task12/pd/2026-11-28/p4b/p4b.json"
G = 32.174
REVIEW = "Not yet Fable-reviewed (ruling PD-22)"
EVIDENCE = {1: "partly independent (same physics, second text: CS-23 Amendment 4)",
            2: "independent of Raymer's text (a time integration of NACA Report 1206's plunge equation); it re-derives "
               "the factor with the model it came from, so it checks (14.6) and its use, not the model",
            3: "coding check of the ruled rule (Stage 1's own formula) with the negative manoeuvre added from measured data (P2)",
            4: "partly independent (second text's gust speeds); no verdict",
            5: "coding check of the ruled rule at a lighter weight; no verdict"}


def load_sources(path=SOURCES):
    return yaml.safe_load(Path(path).read_text())


def sha256(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- NACA Report 1206: indicial functions, gust shape, plunge equation ----------------------------------------
def _terms(name):
    s = load_sources()["naca1206"][name]
    return s["A"], s["b"]


def indicial(s, A, b):
    """1 - sum A_i exp(-b_i s), s in chords: the form of NACA Rep. 1206 eq. (5) and (6)."""
    s = np.asarray(s, dtype=float)
    return 1.0 - sum(a * np.exp(-k * s) for a, k in zip(A, b))


def wagner(s):
    """Lift after a unit jump in angle of attack, normalized to 1: NACA Rep. 1206 eq. (5), p. 3."""
    return indicial(s, *_terms("wagner"))


def kussner(s):
    """Lift on entering a sharp-edge gust, normalized to 1: NACA Rep. 1206 eq. (6), p. 3."""
    return indicial(s, *_terms("kussner"))


def gust_profile(s, H):
    """u/U = (1 - cos(pi s/H))/2 for 0 <= s <= 2H, else 0: NACA Rep. 1206 eq. (7), p. 3 (H in chords). CS 23.333(c)(2)
    states the same shape with the gradient 25 chords for the whole gust, which is 2H with H = 12.5."""
    return 0.5 * (1.0 - math.cos(math.pi * s / H)) if 0.0 <= s <= 2.0 * H else 0.0


def gust_slope(s, H):
    """d(u/U)/ds of gust_profile."""
    return 0.5 * math.pi / H * math.sin(math.pi * s / H) if 0.0 <= s <= 2.0 * H else 0.0


def plunge_history(mu, H=12.5, wagner_terms=None, kussner_terms=None, end=None, step=0.001):
    """The acceleration ratio y(s) = a_n(s)/a_ns of NACA Rep. 1206 eq. (2) for a rigid aircraft that can rise but not
    pitch, through the one-minus-cosine gust of eq. (7).

    With phi(s) = 1 - sum A_i exp(-b_i s) (Wagner) and psi(s) = 1 - sum B_j exp(-c_j s) (Kussner), the two
    convolutions of eq. (2) become first-order states:
      w   = integral of y            (plunge velocity over V, in units of a_ns)
      x_i' = -b_i x_i + y            so that  integral phi(s - s1) y(s1) ds1 = w - sum A_i x_i
      z_j' = -c_j z_j + d(u/U)/ds    so that  integral psi(s - s1) d(u/U)/ds1 ds1 = u/U - sum B_j z_j
    and eq. (2) gives y = (u/U - sum B_j z_j) - (w - sum A_i x_i)/mu. u(0) = 0, so its last term is zero.
    Solved with scipy's solve_ivp (DOP853) on [0, 2H] and [2H, end]; returns (s, y) on a grid of `step` chords."""
    A, b = wagner_terms if wagner_terms is not None else _terms("wagner")
    B, c = kussner_terms if kussner_terms is not None else _terms("kussner")
    nA = len(A)
    end = 3.0 * H if end is None else end

    def accel(s, x):
        w, xa, zg = x[0], x[1:1 + nA], x[1 + nA:]
        return (gust_profile(s, H) - sum(Bj * zj for Bj, zj in zip(B, zg))) - (w - sum(Ai * xi for Ai, xi in zip(A, xa))) / mu

    def rhs(s, x):
        y = accel(s, x)
        return [y] + [-bi * xi + y for bi, xi in zip(b, x[1:1 + nA])] + [-cj * zj + gust_slope(s, H) for cj, zj in zip(c, x[1 + nA:])]

    s_all = np.round(np.arange(0.0, end + 0.5 * step, step), 12)
    x0 = np.zeros(1 + nA + len(B))
    y = np.empty_like(s_all)
    for lo, hi in ((0.0, 2.0 * H), (2.0 * H, end)):
        sol = solve_ivp(rhs, (lo, hi), x0, method="DOP853", rtol=1e-10, atol=1e-12, dense_output=True)
        if not sol.success:
            raise RuntimeError(f"plunge integration failed at mu {mu}: {sol.message}")
        pick = (s_all >= lo) & (s_all <= hi)
        X = sol.sol(s_all[pick])
        y[pick] = [accel(si, X[:, k]) for k, si in enumerate(s_all[pick])]
        x0 = sol.y[:, -1]
    return s_all, y


def gust_factor(mu, H=12.5):
    """K_g = largest a_n/a_ns over the gust: NACA Rep. 1206 eq. (8). The alleviation factor is this peak over the
    quasi-steady sharp-edged value a_ns."""
    return float(np.max(plunge_history(mu, H)[1]))


# ---- CS-23 Amendment 4: the second text of the gust formula ----------------------------------------------------
def cs23_mass_ratio(W_S, rho, chord, a):
    """mu_g = 2 (W/S)/(rho C a g): CS 23.341(c)."""
    return 2.0 * W_S / (rho * chord * a * G)


def cs23_alleviation(mu):
    """k_g = 0.88 mu_g/(5.3 + mu_g): CS 23.341(c)."""
    return 0.88 * mu / (5.3 + mu)


def cs23_load_factor(W_S, V_eas, U_de, a, chord, rho):
    """n = 1 +- k_g rho_0 U_de V a/(2 W/S): CS 23.341(c), V and U_de equivalent speeds (ft/s).
    Returns (n_up, n_down, k_g, mu_g)."""
    mu = cs23_mass_ratio(W_S, rho, chord, a)
    k = cs23_alleviation(mu)
    dn = k * RHO0 * U_de * V_eas * a / (2.0 * W_S)
    return 1.0 + dn, 1.0 - dn, k, mu


def cs23_gust_speed(V_eas, V_C, V_D, h_ft, src=None):
    """U_de of CS 23.333(c)(1)(i)-(ii) for the normal category: 50 fps at V_C, 25 fps at V_D, linear in speed between
    (c)(2)(ii); each value held to 20,000 ft and reduced linearly to half at 50,000 ft. Below V_C the V_C value, above
    V_D the V_D value."""
    g = (src or load_sources())["cs23"]["gust_envelope"]
    frac = min(1.0, max(0.0, (V_eas - V_C) / (V_D - V_C)))
    u = g["U_de_at_V_C_fps"] + frac * (g["U_de_at_V_D_fps"] - g["U_de_at_V_C_fps"])
    h0, h1 = g["full_value_up_to_ft"], g["reduced_to_half_at_ft"]
    return u * (1.0 - 0.5 * min(1.0, max(0.0, (h_ft - h0) / (h1 - h0))))


def cs23_vc_min_kt(W_S_takeoff, src=None):
    """Least design cruising speed of CS 23.335(a)(1)(i): 33 sqrt(W/S) kt EAS, W/S at take-off weight (lb/ft^2)."""
    return (src or load_sources())["cs23"]["design_cruise_speed"]["factor_kt"] * math.sqrt(W_S_takeoff)


# ---- manoeuvre envelope -----------------------------------------------------------------------------------------
def stall_load_factor(V_eas, W_S, CL):
    """n on the stall line: q CL/(W/S) with q in EAS (Anderson APD (6.23); Raymer Fig. 14.3, p. 337)."""
    return 0.5 * RHO0 * V_eas ** 2 * CL / W_S


def corner_speed(n, W_S, CL, rho=RHO0):
    """Speed where the stall line meets the limit n: Anderson APD (6.54), p. 343. Works for the negative side with
    n and CL both negative."""
    return math.sqrt(2.0 * n * W_S / (rho * CL))


def positive_envelope(V_eas, W_S, CL_max, n_pos):
    """Positive side of Raymer Fig. 14.3 and CS 23.333(b)(1): the stall line capped at the limit up to V_D."""
    return min(stall_load_factor(V_eas, W_S, CL_max), n_pos)


def negative_envelope(V_eas, W_S, CL_neg, n_neg, V_C, V_D):
    """Negative side of Raymer Fig. 14.3 and CS 23.333(b)(2)-(3), normal category: the negative stall line down to
    n_neg, n_neg to V_C, then linear to 0 at V_D."""
    if V_eas <= V_C:
        return max(stall_load_factor(V_eas, W_S, CL_neg), n_neg)
    return n_neg * (V_D - V_eas) / (V_D - V_C)


# ---- the ruled gust rule (PD-8): Stage 1's formula, lift slope at the speed's own Mach number -----------------
def ruled_gust(W_S, V_eas, h_ft, V_C, V_D, slope, chord, U_cap=None):
    """Gust load factor under the ruled rule (Raymer p. 339, ruling B-4/PD-8: 30 ft/s to V_C falling to 15 ft/s at
    V_D, 15 ft/s above), with Stage 1's code (conceptual/raymer_loads.py). slope(V_eas, h) is the lift slope.
    U_cap given: the gust is held at that value at every speed (the row 4 sensitivity). Returns (n_up, n_down, U_de, K, mu)."""
    U = U_cap if U_cap is not None else loads.design_gust_velocity(V_eas, V_C, V_D)
    n, K, mu = loads.gust_load_factor(W_S, V_eas, U, slope(V_eas, h_ft), chord, isa(h_ft)["rho"])
    return n, 2.0 - n, U, K, mu


def operating_speed(W_S, h_ft, V_C, V_D, slope, chord, n_pos, n_neg_gust, grid=400):
    """The largest EAS up to V_D below which the ruled gust stays at or below n_pos and at or above n_neg_gust: the
    first crossing found on a grid of `grid` speeds, then brentq. Returns {"V_eas_fps", "limited_by"}; limited_by is
    None if no limit is reached up to V_D."""
    def excess(V):
        n_up, n_down = ruled_gust(W_S, V, h_ft, V_C, V_D, slope, chord)[:2]
        return max(n_up - n_pos, n_neg_gust - n_down)

    Vs = np.linspace(1.0, V_D, grid)
    ex = [excess(V) for V in Vs]
    for k in range(1, len(Vs)):
        if ex[k] > 0.0:
            V = brentq(excess, Vs[k - 1], Vs[k], xtol=1e-10)
            n_up, n_down = ruled_gust(W_S, V, h_ft, V_C, V_D, slope, chord)[:2]
            return {"V_eas_fps": V, "limited_by": "positive" if n_up - n_pos >= n_neg_gust - n_down else "negative"}
    return {"V_eas_fps": V_D, "limited_by": None}


# ---- the run on r0 ----------------------------------------------------------------------------------------------
def context():
    """r0 rebuilt (measurement/stage3_perf.rebuild raises if the rebuild does not reproduce it), P2's negative
    section lift, P4b's ballast and r1 empty-weight change, and the sources."""
    d, L, b, ledger_path, check = sp.rebuild(R0 / "design_pusher.json")
    src = load_sources()
    p2 = json.loads(P2_RECORD.read_text())
    neg_set = next(m for m in p2["measured"] if m["set"] == 2)
    p4b = json.loads(P4B_RECORD.read_text())
    chosen = p4b["candidates"][p4b["selection"]["chosen"]]["measures"]
    return {"d": d, "L": L, "b": b, "rebuild_check": check, "src": src, "p2_negative_set": neg_set,
            "p4b_chosen": p4b["chosen_label"], "ballast_lb": chosen["payload_off"]["ballast_every_loading_lb"],
            "r1_empty_weight_change_lb": chosen["empty_weight_change_lb"]}


def slope_fn(c):
    """Stage 1's lift slope at the Mach number of an EAS at an altitude (measurement/vn_check.lift_slope_at)."""
    b, d, L = c["b"], c["d"], c["L"]

    def slope(V_eas, h_ft):
        atm = isa(h_ft)
        return vn_check.lift_slope_at(b, d["A"], L, V_eas / math.sqrt(atm["sigma"]) / atm["a"])
    return slope


def weights(c, extra=0.0):
    """The load cases' weights (lb). extra is added to every one (the r1 empty-weight change)."""
    d, ballast = c["d"], c["ballast_lb"]
    zf = d["W0_lb"] - d["fuel_lb"]
    return {"takeoff": d["W0_lb"] + extra, "zero_fuel": zf + extra,
            "payload_off_no_ballast": zf - d["payload_lb"] + extra,
            "payload_off_with_ballast": zf - d["payload_lb"] + ballast + extra,
            "payload_off_full_fuel_with_ballast": d["W0_lb"] - d["payload_lb"] + ballast + extra}


def speeds(c):
    d = c["d"]
    V_C = d["V_c_eas_kt"]["sea_level"] * KT
    top = {"sea_level": d["performance"]["vmax_sl_kt_eas"] * KT, "mission_altitude": d["performance"]["vmax_alt_kt_eas"] * KT}
    return V_C, 1.5 * V_C, top                      # Stage 1's V_D (stage1.vn_diagram, Raymer p. 338)


ALTITUDES = (("sea_level", 0.0), ("mission_altitude", 20000.0))


def gust_points(c, W, U_cap=None, rule="ruled"):
    """Gust load factors at V_C, V_D and the level top speed at sea level and 20,000 ft for one weight.
    rule "ruled": Stage 1's formula and the ruled speeds (U_cap holds the gust at a value); "cs23": CS 23.341(c)
    with its own chord and CS 23.333(c) speeds."""
    d, S = c["d"], c["b"]["geom"]["S"]
    V_C, V_D, top = speeds(c)
    slope = slope_fn(c)
    mac, mgc = c["b"]["geom"]["wing"].mac, S / c["b"]["geom"]["wing"].span
    out = []
    for alt, h in ALTITUDES:
        for name, V in (("V_C", V_C), ("V_D", V_D), ("level_top_speed", top[alt])):
            if rule == "cs23":
                U = cs23_gust_speed(V, V_C, V_D, h, c["src"])
                n_up, n_down, K, mu = cs23_load_factor(W / S, V, U, slope(V, h), mgc, isa(h)["rho"])
            else:
                n_up, n_down, U, K, mu = ruled_gust(W / S, V, h, V_C, V_D, slope, mac, U_cap=U_cap if V > V_C else None)
            out.append({"altitude": alt, "altitude_ft": h, "speed": name, "V_eas_kt": V / KT, "U_de_fps": U,
                        "n_up": n_up, "n_down": n_down, "K": K, "mu": mu, "W_lb": W})
    return out


def manoeuvre(c, W):
    """Manoeuvre envelope of one weight: corner speeds and the values at V_C and V_D (EAS, so the same at every
    altitude)."""
    d, L = c["d"], c["L"]
    S = c["b"]["geom"]["S"]
    V_C, V_D, _ = speeds(c)
    cl_neg = wing_negative_cl(c)
    n_pos, n_neg = L["limit_load_factor"], L["negative_load_factor"]
    v_pos = corner_speed(n_pos, W / S, d["CL_max"]["clean"])
    v_neg = corner_speed(n_neg, W / S, cl_neg)
    return {"W_lb": W, "CL_max": d["CL_max"]["clean"], "CL_neg": cl_neg, "positive_corner_kt": v_pos / KT,
            "negative_corner_kt": v_neg / KT, "negative_corner_below_V_C": v_neg < V_C,
            "negative_stall_at_V_C": stall_load_factor(V_C, W / S, cl_neg),
            "positive_at_V_C": positive_envelope(V_C, W / S, d["CL_max"]["clean"], n_pos),
            "positive_at_V_D": positive_envelope(V_D, W / S, d["CL_max"]["clean"], n_pos),
            "negative_at_V_C": negative_envelope(V_C, W / S, cl_neg, n_neg, V_C, V_D),
            "negative_at_V_D": negative_envelope(V_D, W / S, cl_neg, n_neg, V_C, V_D)}


def wing_negative_cl(c):
    """Wing negative maximum lift from P2's measured section value by Raymer (12.15), p. 270: 0.9 times it, the
    quarter chord unswept (the rule is stated for the positive stall; its use here is an assumption)."""
    return 0.9 * c["p2_negative_set"]["summary"]["cl_min"]


def row1(c):
    """CS 23.341(c) at Raymer's gust speed (30 ft/s at V_C) against r0's `gusts` entries, with the text's own chord
    (mean geometric) and with Stage 1's (mean aerodynamic)."""
    d, S = c["d"], c["b"]["geom"]["S"]
    V_C = speeds(c)[0]
    slope = slope_fn(c)
    mac, mgc = c["b"]["geom"]["wing"].mac, S / c["b"]["geom"]["wing"].span
    W = weights(c)
    tol = c["src"]["choices"]["tolerances"]["row1_relative"]
    pts = []
    for alt, h in ALTITUDES:
        for wl, key in (("takeoff", "takeoff_weight"), ("zero_fuel", "zero_fuel_weight")):
            rec = d["gusts"][f"{alt}/{key}"]
            a, rho = slope(V_C, h), isa(h)["rho"]
            n_mgc = cs23_load_factor(W[wl] / S, V_C, c["L"]["gust_ude_fps"], a, mgc, rho)
            n_mac = cs23_load_factor(W[wl] / S, V_C, c["L"]["gust_ude_fps"], a, mac, rho)
            pts.append({"altitude": alt, "weight": wl, "record": rec, "cs23_mean_geometric_chord": n_mgc[0],
                        "cs23_mean_aerodynamic_chord": n_mac[0], "mu_mgc": n_mgc[3], "k_mgc": n_mgc[2],
                        "deviation": n_mgc[0] / rec - 1.0, "deviation_with_mac": n_mac[0] / rec - 1.0})
    worst = max(abs(p["deviation"]) for p in pts)
    return {"row": 1, "points": pts, "mean_geometric_chord_ft": mgc, "mean_aerodynamic_chord_ft": mac, "tolerance": tol,
            "worst_deviation": worst, "verdict": "pass" if worst <= tol else "fail", "evidence_class": EVIDENCE[1]}


def row2(c):
    """Alleviation factor by the time integration at r0's four mass ratios (Stage 1's chord and lift slope at V_C)
    against Raymer (14.6), with the load factors by both."""
    d, S = c["d"], c["b"]["geom"]["S"]
    V_C = speeds(c)[0]
    slope = slope_fn(c)
    mac = c["b"]["geom"]["wing"].mac
    W = weights(c)
    H = c["src"]["naca1206"]["gust_shape"]["H_chords"]
    tol = c["src"]["choices"]["tolerances"]["row2_relative"]
    pts = []
    for alt, h in ALTITUDES:
        for wl in ("takeoff", "zero_fuel"):
            a, rho = slope(V_C, h), isa(h)["rho"]
            mu = loads.gust_mass_ratio(W[wl] / S, rho, mac, a)
            K14 = loads.gust_alleviation_subsonic(mu)
            s, y = plunge_history(mu, H)
            k = int(np.argmax(y))
            dn_unit = RHO0 * c["L"]["gust_ude_fps"] * V_C * a / (2.0 * W[wl] / S)
            pts.append({"altitude": alt, "weight": wl, "mu": mu, "K_14_6": K14, "K_integrated": float(y[k]),
                        "peak_at_chords": float(s[k]), "deviation": float(y[k]) / K14 - 1.0,
                        "n_14_6": 1.0 + K14 * dn_unit, "n_integrated": 1.0 + float(y[k]) * dn_unit,
                        "n_record": d["gusts"][f"{alt}/{wl}_weight"]})
    worst = max(abs(p["deviation"]) for p in pts)
    return {"row": 2, "points": pts, "H_chords": H, "tolerance": tol, "worst_deviation": worst,
            "verdict": "pass" if worst <= tol else "fail", "evidence_class": EVIDENCE[2],
            "indicial": {"wagner": c["src"]["naca1206"]["wagner"], "kussner": c["src"]["naca1206"]["kussner"]}}


def row3(c, extra=0.0):
    """The ruled rule at take-off and zero-fuel weight: every gust point at or below +3.8 and at or above -1.7, and
    the manoeuvre envelope with the negative side inside +3.8 and -1.8."""
    tol = c["src"]["choices"]["tolerances"]
    W = weights(c, extra)
    pts = [p for wl in ("takeoff", "zero_fuel") for p in [dict(q, weight=wl) for q in gust_points(c, W[wl])]]
    man = {wl: manoeuvre(c, W[wl]) for wl in ("takeoff", "zero_fuel")}
    worst_up = max(pts, key=lambda p: p["n_up"])
    worst_down = min(pts, key=lambda p: p["n_down"])
    gust_ok = worst_up["n_up"] <= tol["row3_positive"] and worst_down["n_down"] >= tol["row3_negative_gust"]
    man_ok = all(m["positive_at_V_C"] <= tol["row3_positive"] and m["negative_at_V_C"] >= tol["negative_manoeuvre_limit"] for m in man.values())
    return {"row": 3, "points": pts, "manoeuvre": man, "worst_up": worst_up, "worst_down": worst_down,
            "margin_up": tol["row3_positive"] - worst_up["n_up"], "margin_down": worst_down["n_down"] - tol["row3_negative_gust"],
            "gust_inside": gust_ok, "manoeuvre_inside": man_ok, "verdict": "pass" if gust_ok and man_ok else "fail",
            "limits": {"positive": tol["row3_positive"], "negative_gust": tol["row3_negative_gust"], "negative_manoeuvre": tol["negative_manoeuvre_limit"]},
            "evidence_class": EVIDENCE[3]}


def stage1_with_limit(n_limit):
    """Stage 1 at r0's cell and L_sized (as measurement/robust_sizing.sized_aircraft_guess with the per-design V_C
    rule) with the ledger's limit_load_factor raised to n_limit. Returns the parts of the record a weight cost needs."""
    from conceptual import stage1
    from measurement import bands_cells
    from measurement import robust_sizing as rs
    rs.use_engine_as_is(True)
    row = bands_cells.source_row(13.0, 8.0)
    L = dict(rs.ledger_values(), loiter_h=float(row["L_sized_h"]), vc_placard_rule="per_design", limit_load_factor=float(n_limit))
    a = stage1.analyse("pusher", 13.0, 8.0, L, rs._engine(row["P_hp"]), W0_guess=rs.first_guess(row["P_hp"], row["L_sized_h"]))
    rec = stage1.design_record(a, L, rs._raw())
    return {"limit_load_factor": float(n_limit), "L_sized_h": row["L_sized_h"], "W0_lb": rec["W0_lb"], "We_lb": rec["We_lb"],
            "fuel_lb": rec["fuel_lb"], "n_limit": rec["n_limit"], "Nz_ultimate": rec["Nz_ultimate"], "power_ok": rec["power_ok"],
            "components_lb": rec["components_lb"], "gusts": rec["gusts"]}


STRUCTURE = ("wing", "horizontal_tail", "vertical_tail", "fuselage", "main_gear", "nose_gear", "sponsons", "flight_controls")


def row4(c, log=print):
    """The second text's gust speeds, and the ruled formula with the gust held at 30 ft/s above V_C: load factors
    against limit and ultimate, and the weight cost from Stage 1 with the limit raised. No verdict."""
    L = c["L"]
    W = weights(c)
    fs = c["src"]["cs23"]["factor_of_safety"]["value"]
    lim = {"positive_limit": L["limit_load_factor"], "negative_limit": L["negative_load_factor"],
           "positive_ultimate": fs * L["limit_load_factor"], "negative_ultimate": fs * L["negative_load_factor"]}
    base = stage1_with_limit(L["limit_load_factor"])
    cases = {}
    for name, kw in (("cs23_speeds", {"rule": "cs23"}), ("ruled_held_30", {"U_cap": L["gust_ude_fps"]})):
        pts = [dict(p, weight=wl) for wl in ("takeoff", "zero_fuel") for p in gust_points(c, W[wl], **kw)]
        for p in pts:
            p["above_positive_limit"] = p["n_up"] > lim["positive_limit"]
            p["below_negative_limit"] = p["n_down"] < lim["negative_limit"]
            p["above_positive_ultimate"] = p["n_up"] > lim["positive_ultimate"]
            p["below_negative_ultimate"] = p["n_down"] < lim["negative_ultimate"]
        cleared = [p for p in pts if p["speed"] in ("V_C", "V_D")]
        n_cover = max(p["n_up"] for p in cleared)
        log(f"row 4 {name}: largest positive gust at V_C and V_D {n_cover:.3f}; Stage 1 with that limit")
        raised = stage1_with_limit(max(n_cover, L["limit_load_factor"]))
        cases[name] = {"points": pts, "largest_up_V_C_V_D": n_cover, "largest_up_all": max(p["n_up"] for p in pts),
                       "lowest_down_V_C_V_D": min(p["n_down"] for p in cleared), "lowest_down_all": min(p["n_down"] for p in pts),
                       "stage1_raised": raised,
                       "W0_change_lb": raised["W0_lb"] - base["W0_lb"], "We_change_lb": raised["We_lb"] - base["We_lb"],
                       "structure_change_lb": sum(raised["components_lb"][k] - base["components_lb"][k] for k in STRUCTURE),
                       "wing_change_lb": raised["components_lb"]["wing"] - base["components_lb"]["wing"]}
    return {"row": 4, "limits": lim, "stage1_at_ruled_limit": base, "cases": cases, "verdict": "reported (no verdict, finding for O-2)",
            "evidence_class": EVIDENCE[4]}


def row5(c, extra=0.0):
    """Payload-off weights: the ruled gust points and the operating limit (largest EAS per altitude at which the gust
    stays inside +3.8 and -1.7). No verdict."""
    tol = c["src"]["choices"]["tolerances"]
    S, mac = c["b"]["geom"]["S"], c["b"]["geom"]["wing"].mac
    V_C, V_D, _ = speeds(c)
    slope = slope_fn(c)
    W = weights(c, extra)
    cases = {}
    for wl in ("payload_off_no_ballast", "payload_off_with_ballast", "payload_off_full_fuel_with_ballast"):
        pts = gust_points(c, W[wl])
        lim = []
        for h in c["src"]["choices"]["operating_limit"]["altitudes_ft"]:
            o = operating_speed(W[wl] / S, float(h), V_C, V_D, slope, mac, tol["row3_positive"], tol["row3_negative_gust"])
            lim.append({"altitude_ft": float(h), "V_eas_kt": o["V_eas_fps"] / KT, "limited_by": o["limited_by"],
                        "at_or_above_V_C": o["V_eas_fps"] >= V_C - 1e-9})
        cases[wl] = {"W_lb": W[wl], "W_S": W[wl] / S, "points": pts, "manoeuvre": manoeuvre(c, W[wl]),
                     "largest_up": max(p["n_up"] for p in pts if p["speed"] != "level_top_speed"),
                     "lowest_down": min(p["n_down"] for p in pts if p["speed"] != "level_top_speed"),
                     "inside_at_V_C_V_D": all(p["n_up"] <= tol["row3_positive"] and p["n_down"] >= tol["row3_negative_gust"]
                                              for p in pts if p["speed"] != "level_top_speed"),
                     "operating_limit": lim,
                     "lowest_altitude_limited_below_V_C_ft": next((x["altitude_ft"] for x in lim if not x["at_or_above_V_C"]), None)}
    return {"row": 5, "cases": cases, "operating_case": "payload_off_with_ballast",
            "hypothetical_case": "payload_off_no_ballast", "ballast_lb": c["ballast_lb"], "p4b_chosen": c["p4b_chosen"],
            "verdict": "reported (no verdict; operating limit for P8 under PD-13)", "evidence_class": EVIDENCE[5]}


def r1_findings(c, r3, r5):
    """Rows 3 and 5 again with every weight raised by P4b's r1 empty-weight change (wing unchanged)."""
    dw = c["r1_empty_weight_change_lb"]
    a3 = row3(c, dw)
    a5 = row5(c, dw)
    case = "payload_off_with_ballast"
    return {"empty_weight_change_lb": dw,
            "row3": {"worst_up_r0": r3["worst_up"]["n_up"], "worst_up_r1": a3["worst_up"]["n_up"],
                     "worst_down_r0": r3["worst_down"]["n_down"], "worst_down_r1": a3["worst_down"]["n_down"], "verdict_r1": a3["verdict"]},
            "row5_with_ballast": {"W_r0": r5["cases"][case]["W_lb"], "W_r1": a5["cases"][case]["W_lb"],
                                  "largest_up_r0": r5["cases"][case]["largest_up"], "largest_up_r1": a5["cases"][case]["largest_up"],
                                  "lowest_down_r0": r5["cases"][case]["lowest_down"], "lowest_down_r1": a5["cases"][case]["lowest_down"],
                                  "operating_limit_r1": a5["cases"][case]["operating_limit"]},
            "not_changed_by_r1": "the plunge-only gust formula has no term for the wing's fore-and-aft position or the fuselage length; "
                                 "Stage 1's lift slope uses the fuselage diameter and span only. Tail gust and balancing loads are not computed (NACA Rep. 1206 assumption 5; PD-9)."}


def run(out, log=print):
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P5 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "sources": SOURCES,
             "p2_record": P2_RECORD, "p4b_record": P4B_RECORD}
    c = context()
    log(f"commit {tree['commit']}, clean tree; r0 rebuilt")
    d = c["d"]
    V_C, V_D, top = speeds(c)
    res = {"inputs": dict(tree, command="python -m prelim.p5_loads " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P5", python=platform.python_version(), numpy=np.__version__,
                          scipy=scipy.__version__, pyyaml=yaml.__version__, matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()}, sha256={k: sha256(p) for k, p in files.items()}),
           "review": REVIEW, "baseline": str(R0.relative_to(REPO)), "sources": c["src"], "rebuild_check": c["rebuild_check"],
           "r0": {"W0_lb": d["W0_lb"], "fuel_lb": d["fuel_lb"], "payload_lb": d["payload_lb"], "W_S": d["W_S"],
                  "S_ft2": c["b"]["geom"]["S"], "span_ft": c["b"]["geom"]["wing"].span, "mac_ft": c["b"]["geom"]["wing"].mac,
                  "CL_max_clean": d["CL_max"]["clean"], "gusts": d["gusts"], "vn": d["vn"],
                  "V_C_kt": V_C / KT, "V_D_kt": V_D / KT, "level_top_speed_kt": {k: v / KT for k, v in top.items()},
                  "limit_load_factor": c["L"]["limit_load_factor"], "negative_load_factor": c["L"]["negative_load_factor"],
                  "margin_gust_g": c["L"]["margin_gust_g"], "gust_ude_fps": c["L"]["gust_ude_fps"]},
           "negative_lift": {"section_cl_min": c["p2_negative_set"]["summary"]["cl_min"],
                             "section_set": c["p2_negative_set"]["set"], "section_reynolds": c["p2_negative_set"]["reynolds"],
                             "wing_CL_neg_12_15": wing_negative_cl(c)},
           "weights": weights(c), "ballast_lb": c["ballast_lb"], "p4b_chosen": c["p4b_chosen"]}
    vh = d["performance"]["vmax_sl_kt_eas"]
    res["cs23_design_cruise_speed"] = {"V_C_min_kt": cs23_vc_min_kt(d["W0_lb"] / c["b"]["geom"]["S"], c["src"]), "V_C_kt": V_C / KT,
                                       "cap_0_9_V_H_kt": c["src"]["cs23"]["design_cruise_speed"]["vh_fraction"] * vh,
                                       "V_D_kt": V_D / KT,
                                       "V_D_min_kt": c["src"]["cs23"]["dive_speed"]["ratio_normal_category"] * cs23_vc_min_kt(d["W0_lb"] / c["b"]["geom"]["S"], c["src"]),
                                       "note": "A finding only: R18 and ruling B-4 set V_C; CS-23 is not a requirement of this aircraft"}
    log("row 1: CS 23.341(c) against r0's gusts")
    res["row1"] = row1(c)
    log("row 2: time integration at the four mass ratios")
    res["row2"] = row2(c)
    res["gust_factor_curve"] = [{"mu": mu, "K_integrated": gust_factor(mu), "K_14_6": loads.gust_alleviation_subsonic(mu)}
                                for mu in (2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0, 200.0)]
    log("row 3: the ruled rule with the negative manoeuvre")
    res["row3"] = row3(c)
    res["row4"] = row4(c, log)
    log("row 5: payload off and the operating limit")
    res["row5"] = row5(c)
    res["r1"] = r1_findings(c, res["row3"], res["row5"])
    res["histories"] = {str(mu): dict(zip(("s", "y"), [v[::100].tolist() for v in plunge_history(mu)])) for mu in (3.0, 20.0, 100.0)}
    res["acceptance"] = [{"row": r, "verdict": res[f"row{r}"]["verdict"]} for r in (1, 2, 3, 4, 5)]
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == tree["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p5.json").write_text(json.dumps(_plain(res), indent=1))
    log(f"done ({res['runtime_s']:.0f} s)")
    return res


def _plain(o):
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    return o


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the figures (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and figures from OUT/p5.json")
    a = ap.parse_args(argv)
    out = (REPO / a.out).resolve()
    if not a.report_only:
        t0 = time.time()
        lines = []

        def log(msg):
            lines.append(f"[{time.time() - t0:7.0f} s] {msg}")
            print(lines[-1], flush=True)
            if out.exists():
                (out / "run.log").write_text("\n".join(lines) + "\n")
        run(out, log)
    if a.report:
        from prelim import p5_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p5_report.write_figures(out, figures)
        report.write_text(p5_report.report_text(out))


if __name__ == "__main__":
    main()

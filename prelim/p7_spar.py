"""Preliminary design P7: wing spar preliminary sizing (spec P7, items 8 and 26).

    python -m prelim.p7_spar --out runs/task12/pd/<date>/p7 [--report docs/validation/<date>_task12_pd_p7.md]
    python -m prelim.p7_spar --out runs/task12/pd/<date>/p7 --report ... --report-only

Run on Opus 5.5 under owner ruling PD-22: not yet Fable-reviewed. Choices and sources: data/task12/pd_p7_choices.yaml
(decision PD-23). Library (Raymer, 2nd ed., cited by number and page, no text copied): Schrenk (14.9)-(14.11), p. 343;
trim first, p. 342; the station method, p. 381-383 and Figs. 14.37-14.39; wing weight by chord, p. 382; (14.35),
p. 383; the spar idealisation, p. 384-385 and Fig. 14.41; (14.37), p. 385, with Fig. 14.42; Table 14.4, p. 368-369.
Not in the library: the knock-down factor (a judgement). The span loading of the lattice is the study's own vortex
lattice (drone/vlm.py). r0, its ledger and the records of P2, P3, P4, P4b and P5 are read and not changed.

Units: loads in ft and lb (y from the centreline along the half span); the section sizing in inches and psi.
"""
import argparse
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import yaml

from conceptual.units import KT, RHO0
from drone import geometry, vlm
from geometry3d import sections
from prelim import p3_loft as p3
from prelim import p4_methods as m
from prelim.record import tree_state

REPO = Path(__file__).resolve().parents[1]
CHOICES = REPO / "data/task12/pd_p7_choices.yaml"
ARRANGEMENT = REPO / "data/task12/pd_p3_arrangement.yaml"
R0 = REPO / "runs/task12/pd/2026-11-27/p0/r0"
P2_RECORD = REPO / "runs/task12/pd/2026-11-27/p2b/p2.json"
P4_RECORD = REPO / "runs/task12/pd/2026-11-27/p4/p4.json"
P4B_RECORD = REPO / "runs/task12/pd/2026-11-28/p4b/p4b.json"
P5_RECORD = REPO / "runs/task12/pd/2026-11-28/p5/p5.json"
REVIEW = "Not yet Fable-reviewed (ruling PD-22)"
TOL_LIFT = 1e-9           # spec P7 row 1: the airload integrates to the required lift
TOL_CLOSED = 1e-6         # spec P7 row 1: shear and moment against their closed forms
TOL_ROOT_MOMENT = 0.05    # spec P7 row 2: Schrenk's root bending moment against the lattice's
EVIDENCE = {1: "coding check",
            2: "partly independent (the study's own vortex lattice against Schrenk's approximation, same planform)",
            3: "coding check of the sizing (every station is sized to the envelope of the ruled cases, so the governing case is at zero margin by construction); the content is whether a sizing exists and what margin the other cases keep",
            4: "layout construction on the loft's section with an assumed skin",
            5: "independent of the statistical wing weight (bottom-up spar, typical material values with a judged knock-down); no tolerance"}
FT_IN = 12.0


def load_choices(path=CHOICES):
    return yaml.safe_load(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- step 1: spanwise airload ---------------------------------------------------------------------------------
def schrenk(y, span, c_root, c_tip):
    """Schrenk's load shape per unit span (ft): the average of the trapezoidal chord (14.9) and the ellipse of the same
    span and area (14.11), with the area from (14.10), p. 343. Its integral over the span is the wing area."""
    lam = c_tip / c_root
    S = 0.5 * span * c_root * (1.0 + lam)                                    # (14.10)
    eta = 2.0 * np.asarray(y, dtype=float) / span
    trap = c_root * (1.0 - eta * (1.0 - lam))                                # (14.9)
    ell = 4.0 * S / (math.pi * span) * np.sqrt(np.clip(1.0 - eta ** 2, 0.0, None))   # (14.11)
    return 0.5 * (trap + ell)


def lattice_span_load(planform, level, alpha):
    """The span loading of the study's vortex lattice (drone/vlm.py) on the half wing: strip centres y (ft), section
    lift times chord cl c per unit dynamic pressure (ft), and strip widths dy (ft). The strip edges are the lattice's
    own cosine spacing."""
    n = vlm.LEVELS[level][1]
    r = vlm.solve(planform, alpha, level)
    half = planform.span / 2.0
    eta_e = 0.5 * (1.0 - np.cos(np.pi * np.arange(n + 1) / n))
    chord = planform.chord_at(eta_e)
    c_mid = 0.5 * (chord[:-1] + chord[1:])
    return np.asarray(r["eta"]) * half, np.asarray(r["cl"]) * c_mid, np.diff(eta_e) * half


# ---- step 3: the station method ---------------------------------------------------------------------------------
def stations(half, strips, extra):
    """Equally spaced stations from the centreline (0) to the tip, plus the extra stations (each once)."""
    y = np.concatenate([np.linspace(0.0, half, strips + 1), np.asarray(extra, dtype=float)])
    return np.unique(np.round(y, 12))


def trapezoid_force(y0, y1, b, a):
    """Fig. 14.39, p. 383: a strip of width S = y1 - y0 with intensity b at y0 and a at y1 carries F = S (a + b)/2 at
    X = S (2a + b)/(3a + 3b) from y0. Returns (F, X from the centreline). An unloaded strip puts F = 0 at its middle."""
    S = y1 - y0
    if a + b == 0.0:
        return 0.0, y0 + 0.5 * S
    return S * (a + b) / 2.0, y0 + S * (2.0 * a + b) / (3.0 * a + 3.0 * b)


def distributed(y, w):
    """A distributed load of intensity w (lb/ft, at the stations y) as one concentrated load per strip: arrays F, X.
    w must not change sign inside a strip."""
    out = [trapezoid_force(y[j], y[j + 1], w[j], w[j + 1]) for j in range(len(y) - 1)]
    return np.array([o[0] for o in out]), np.array([o[1] for o in out])


def shear_moment(y, F, X):
    """Shear V and bending moment M at the stations from concentrated loads F at X (p. 382-383). The shear at a
    station is the sum of every load at or outboard of it, summed from the tip inward; the moment is the area under
    the shear curve from the tip inward: across a strip the shear is the outboard station's, plus each load inside
    the strip over its distance from the inboard station."""
    F, X = np.asarray(F, dtype=float), np.asarray(X, dtype=float)
    n = len(y)
    V, M = np.zeros(n), np.zeros(n)
    V[-1] = F[X >= y[-1]].sum()
    for j in range(n - 2, -1, -1):
        inside = (X >= y[j]) & (X < y[j + 1])
        V[j] = V[j + 1] + F[inside].sum()
        M[j] = M[j + 1] + V[j + 1] * (y[j + 1] - y[j]) + np.sum(F[inside] * (X[inside] - y[j]))
    return V, M


def uniform_closed(y, w, L):
    """Cantilever of length L under the uniform load w: V = w (L - y), M = w (L - y)^2 / 2."""
    return w * (L - y), 0.5 * w * (L - y) ** 2


def elliptic_closed(y, w0, L):
    """Cantilever of length L under w0 sqrt(1 - (y/L)^2): V = w0 L [pi/4 - (e sqrt(1 - e^2) + asin e)/2] and
    M = w0 L^2 (1 - e^2)^(3/2) / 3 - y V, e = y/L (integrals of the ellipse and of its first moment)."""
    e = np.clip(np.asarray(y, dtype=float) / L, 0.0, 1.0)
    V = w0 * L * (math.pi / 4.0 - 0.5 * (e * np.sqrt(1.0 - e ** 2) + np.arcsin(e)))
    return V, w0 * L ** 2 * (1.0 - e ** 2) ** 1.5 / 3.0 - y * V


# ---- step 4: sizing -----------------------------------------------------------------------------------------------
def spar_depth_over_chord(x):
    """Depth of the loft's NACA 4415 straight up at the chord station x, over the chord (geometry3d/sections.py)."""
    return sections.depth_between(0.04, 0.4, 0.15, x, x, n=1)


def cap_area(M, sigma, width, h):
    """Area of each cap (in^2) at the stress sigma (psi) under the moment M (lb in), the caps alone in bending,
    (14.35), p. 383: with the caps' area A concentrated at their centroids, sigma = M/(A arm), and the arm is the depth
    inside the skins h less one cap thickness A/width. So A^2/width - h A + M/sigma = 0; the smaller root is the cap.
    No real root (nan): the caps do not fit inside the section."""
    M = abs(M)
    if M == 0.0:
        return 0.0
    disc = h ** 2 - 4.0 * M / (sigma * width)
    if disc < 0.0:
        return float("nan")
    return 0.5 * width * (h - math.sqrt(disc))


def web_thickness(V, h, F_su, K, E):
    """(t, t_strength, t_buckling) of the web, in: the web of depth h carries the shear V (lb) at a uniform stress
    V/(h t) (p. 384-385) that may not exceed the allowable F_su or the buckling stress K E (t/h)^2 of (14.37), p. 385,
    with the web panel width taken as h. From the second, t^3 = V h/(K E)."""
    V = abs(V)
    ts, tb = V / (h * F_su), (V * h / (K * E)) ** (1.0 / 3.0)
    return max(ts, tb), ts, tb


def cap_margin(M, A, width, h, sigma):
    """Margin of safety of a cap: sigma_allowable/sigma - 1, with sigma = |M|/(A (h - A/width))."""
    if M == 0.0:
        return float("inf")
    return sigma * A * (h - A / width) / abs(M) - 1.0


def web_margin(V, t, h, F_su, K, E):
    """Margin of safety of the web: the smaller of F_su and K E (t/h)^2 over the shear stress |V|/(h t), less 1."""
    if V == 0.0:
        return float("inf")
    tau = abs(V) / (h * t)
    return min(F_su, K * E * (t / h) ** 2) / tau - 1.0


# ---- context ------------------------------------------------------------------------------------------------------
def load(path):
    return json.loads(Path(path).read_text())


def context():
    """Everything the run reads: r0 and its ledger, the P3 arrangement, P4's layout, tanks, centre of gravity and
    section moment, P4b's layout for r1, P5's load factors, P2's wing maximum lift and the choices."""
    d, L, A = p3.inputs()
    p4, p4b, p5, p2 = load(P4_RECORD), load(P4B_RECORD), load(P5_RECORD), load(P2_RECORD)
    row1 = p4["as_arranged"]["row1"]["gear_up/empty_weight_x1"]
    chosen = p4b["candidates"][p4b["selection"]["chosen"]]
    row1b = chosen["evaluation"]["row1"]["gear_up/empty_weight_x1"]
    return {"d": d, "L": L, "A": A, "ch": load_choices(), "p4": p4, "p5": p5,
            "lay_r0": p4["as_arranged"]["layout"], "lay_r1": chosen["layout"], "p4b_chosen": p4b["chosen_label"],
            "cg_r0": {"full": row1["x_cg_full_ft"], "empty": row1["x_cg_empty_ft"], "W_full": row1["weight_full_lb"], "W_empty": row1["weight_empty_lb"]},
            "cg_r1": {"full": row1b["x_cg_full_ft"], "empty": row1b["x_cg_empty_ft"], "W_full": row1b["weight_full_lb"], "W_empty": row1b["weight_empty_lb"]},
            "r1_empty_weight_change_lb": chosen["measures"]["empty_weight_change_lb"],
            "cm_w": m.wing_moment(p4["cm0_p2"], d["A"]), "tanks": p4["tanks"],
            "CL_max_p2": p2["wing"]["measured"]["clean"]}


def wing_and_tail_lift(n, W, q, c, lay, x_cg):
    """Wing and tail lift (lb) that carry n W in pitch balance (Raymer p. 342): the tail lift coefficient is P4's
    tail_cl_trim (Raymer (16.7), p. 416, without thrust terms) at the wing lift coefficient, and the tail lift is
    eta_h q S_h C_L,t. tail_cl_trim is a straight line in the wing coefficient, so two evaluations solve it."""
    d, L = c["d"], c["L"]
    S = d["wing"]["area"]
    k = L["tail_eta_h"] * lay["ht_area"] / S

    def total(CLw):
        return CLw + k * m.tail_cl_trim(d, L, lay, CLw, x_cg, c["cm_w"])
    f0, f1 = total(0.0), total(1.0)
    CLw = (n * W / (q * S) - f0) / (f1 - f0)
    CLt = m.tail_cl_trim(d, L, lay, CLw, x_cg, c["cm_w"])
    return {"CL_wing": CLw, "CL_tail": CLt, "L_wing": CLw * q * S, "L_tail": k * CLt * q * S}


# ---- the load cases -------------------------------------------------------------------------------------------------
def corner_kt(n, W, S, CL):
    """Speed (kt EAS) at which the stall line reaches the load factor n: n W = 0.5 rho_0 V^2 S C_L."""
    return math.sqrt(2.0 * n * W / (RHO0 * S * CL)) / KT


def cases(c, version="r0"):
    """The ruled and the sensitivity load cases (spec P7 step 5), each with its load factor, weight, fuel state and
    speeds, from r0's ledger and P5's record. version "r1": P4b's weights (r0 plus its empty-weight change), P5's r1
    gust factors and P2's measured clean maximum lift for the positive corner speed."""
    d, L, p5 = c["d"], c["L"], c["p5"]
    S = d["wing"]["area"]
    dW = c["r1_empty_weight_change_lb"] if version == "r1" else 0.0
    W = {"takeoff": d["W0_lb"] + dW, "zero_fuel": d["W0_lb"] - d["fuel_lb"] + dW}
    CLmax = c["CL_max_p2"] if version == "r1" else d["CL_max"]["clean"]
    CLneg = p5["row3"]["manoeuvre"]["takeoff"]["CL_neg"]
    V_C, V_D = p5["r0"]["V_C_kt"], p5["r0"]["V_D_kt"]
    npos, nneg = L["limit_load_factor"], L["negative_load_factor"]
    out = []
    for wt in ("takeoff", "zero_fuel"):
        out.append({"name": f"+{npos:g} {wt.replace('_', '-')} weight", "kind": "ruled", "n": npos, "weight": wt, "W_lb": W[wt],
                    "speeds_kt": {"positive_corner": corner_kt(npos, W[wt], S, CLmax), "V_C": V_C, "V_D": V_D}})
    g = p5["row3"]["worst_up"]
    up, down = (g["n_up"], g["n_down"]) if version == "r0" else (p5["r1"]["row3"]["worst_up_r1"], p5["r1"]["row3"]["worst_down_r1"])
    for tag, n in (("up", up), ("down", down)):
        out.append({"name": f"worst gust {tag} (P5 row 3)", "kind": "ruled", "n": n, "weight": g["weight"], "W_lb": W[g["weight"]],
                    "speeds_kt": {g["speed"]: g["V_eas_kt"]}, "altitude_ft": g["altitude_ft"]})
    for wt in ("takeoff", "zero_fuel"):
        out.append({"name": f"{nneg:g} {wt.replace('_', '-')} weight", "kind": "ruled", "n": nneg, "weight": wt, "W_lb": W[wt],
                    "speeds_kt": {"negative_corner": corner_kt(nneg, W[wt], S, CLneg), "V_C": V_C}})
    if version == "r0":
        for key, label in (("cs23_speeds", "CS-23 gust speeds"), ("ruled_held_30", "gust held at 30 ft/s above V_C")):
            pts = p5["row4"]["cases"][key]["points"]
            for tag, p in (("up", max(pts, key=lambda p: p["n_up"])), ("down", min(pts, key=lambda p: p["n_down"]))):
                out.append({"name": f"{label}, {tag} (P5 row 4)", "kind": "sensitivity", "n": p["n_up"] if tag == "up" else p["n_down"],
                            "weight": p["weight"], "W_lb": W[p["weight"]], "speeds_kt": {p["speed"]: p["V_eas_kt"]},
                            "altitude_ft": p["altitude_ft"]})
    return out


class Wing:
    """The half wing on its stations, with the per-unit-span shapes of the loads (all in ft and lb)."""

    def __init__(self, c, shape="schrenk", lattice=None, strips=None):
        d, ch = c["d"], c["ch"]
        w = d["wing"]
        self.half, self.cr, self.ct = 0.5 * w["span"], w["root_chord"], w["tip_chord"]
        tk = c["tanks"]["tanks"]
        self.tank = (tk[0]["y_from_ft"], tk[-1]["y_to_ft"])
        self.y_gear = d["layout"]["gear_track"]["half_track_ft"]
        extra = [0.5 * d["fuselage"]["diameter"], self.tank[0], self.tank[1], self.y_gear]
        self.y = stations(self.half, strips or ch["loads"]["stations"]["strips"], extra)
        self.chord = self.cr + (self.ct - self.cr) * self.y / self.half
        if shape == "schrenk":
            self.air = schrenk(self.y, w["span"], self.cr, self.ct)
        else:       # the lattice's cl c, straight between its strip centres, zero at the tip
            ly, ll, _ = lattice
            self.air = np.interp(self.y, np.concatenate([[0.0], ly, [self.half]]), np.concatenate([[ll[0]], ll, [0.0]]))
        self.shape = shape
        self.W_wing = d["components_lb"]["wing"]
        self.W_points = d["components_lb"]["sponsons"] + d["components_lb"]["main_gear"]
        self.fuel_full = d["fuel_lb"]

    def strip_loads(self, intensity, total_half):
        """Concentrated strip loads of a per-unit-span shape, scaled so that they sum to total_half exactly."""
        F, X = distributed(self.y, intensity)
        return F * (total_half / F.sum()), X

    def loads(self, L_wing, n, fuel_lb):
        """(F, X) of every load on the half wing at load factor n: the airload carrying L_wing over the whole wing,
        less n times the wing weight (by chord, p. 382), the fuel (by chord squared between the tank ends) and the
        sponsons and main gear (at the main wheels), each half to this side."""
        Fa, Xa = self.strip_loads(self.air, 0.5 * L_wing)
        Fw, Xw = self.strip_loads(self.chord, -0.5 * n * self.W_wing)
        parts = [(Fa, Xa), (Fw, Xw), (np.array([-0.5 * n * self.W_points]), np.array([self.y_gear]))]
        if fuel_lb > 0.0:
            mid = 0.5 * (self.y[:-1] + self.y[1:])
            inside = (mid >= self.tank[0]) & (mid <= self.tank[1])
            # intensity at both ends of each tank strip (chord squared), zero elsewhere: one strip at a time
            Ff, Xf = [], []
            for j in range(len(self.y) - 1):
                b, a = (self.chord[j] ** 2, self.chord[j + 1] ** 2) if inside[j] else (0.0, 0.0)
                f, x = trapezoid_force(self.y[j], self.y[j + 1], b, a)
                Ff.append(f)
                Xf.append(x)
            Ff = np.array(Ff)
            parts.append((Ff * (-0.5 * n * fuel_lb / Ff.sum()), np.array(Xf)))
        F = np.concatenate([p[0] for p in parts])
        X = np.concatenate([p[1] for p in parts])
        return F, X, Fa


def evaluate_case(c, wing, case, lay, cg, fos):
    """Every speed of a case: wing and tail lift, then ultimate shear and moment at the stations; the case's speed
    is the one with the largest ultimate root moment in magnitude."""
    fuel = c["d"]["fuel_lb"] if case["weight"] == "takeoff" else 0.0
    x_cg = cg["full"] if case["weight"] == "takeoff" else cg["empty"]
    runs = {}
    for sp, V in case["speeds_kt"].items():
        q = 0.5 * RHO0 * (V * KT) ** 2
        t = wing_and_tail_lift(case["n"], case["W_lb"], q, c, lay, x_cg)
        F, X, Fa = wing.loads(t["L_wing"], case["n"], fuel)
        Vs, Ms = shear_moment(wing.y, fos * F, X)
        runs[sp] = {"V_kt": V, "q_psf": q, "x_cg_ft": x_cg, **t, "airload_sum_lb": float(Fa.sum()),
                    "airload_error": float(Fa.sum() / (0.5 * t["L_wing"]) - 1.0), "V_ult_lb": Vs, "M_ult_lbft": Ms}
    worst = max(runs, key=lambda s: abs(runs[s]["M_ult_lbft"][0]))
    return dict(case, fuel_lb=fuel, speed=worst, runs=runs, V_ult_lb=runs[worst]["V_ult_lb"], M_ult_lbft=runs[worst]["M_ult_lbft"])


def section(wing, ch, kd=None, skin=None, cap_w=None, x_spar=None):
    """Per station: chord, depth, depth inside the skins (in), cap width (in), allowables (psi)."""
    g, mat = ch["geometry"], ch["material"]
    kd = ch["knock_down"]["value"] if kd is None else kd
    skin = g["skin_thickness_in"]["value"] if skin is None else skin
    cap_w = g["cap_width_over_chord"]["value"] if cap_w is None else cap_w
    x_spar = m.val(yaml.safe_load(ARRANGEMENT.read_text())["arrangement"]["front_spar_chord_fraction"]) if x_spar is None else x_spar
    caps, web = mat["caps_0_deg"], mat["web_pm45_deg"]
    c_in = wing.chord * FT_IN
    depth = spar_depth_over_chord(x_spar) * c_in
    return {"x_spar": x_spar, "knock_down": kd, "skin_in": skin, "cap_width_over_chord": cap_w,
            "chord_in": c_in, "depth_in": depth, "h_in": depth - 2.0 * skin, "cap_width_in": cap_w * c_in,
            "sigma_cap_psi": kd * min(caps["F_tu_L_psi"], caps["F_cu_L_psi"]), "F_su_psi": kd * web["F_su_LT_psi"],
            "K": g["web_buckling_K"]["value"], "E_web_psi": min(web["E_t_L_psi"], web["E_c_L_psi"]),
            "rho_caps": caps["density_lb_in3"], "rho_web": web["density_lb_in3"]}


def size(wing, sec, M_env_lbft, V_env_lb):
    """Caps and web at every station for the envelope moment and shear (ultimate), and the spar weight of both
    halves (lb): two caps and one web per side, integrated over the span by the trapezoid rule."""
    n = len(wing.y)
    A = np.array([cap_area(M_env_lbft[j] * FT_IN, sec["sigma_cap_psi"], sec["cap_width_in"][j], sec["h_in"][j]) for j in range(n)])
    tw = np.array([web_thickness(V_env_lb[j], sec["h_in"][j], sec["F_su_psi"], sec["K"], sec["E_web_psi"]) for j in range(n)])
    fits = bool(np.all(np.isfinite(A)))
    y_in = wing.y * FT_IN
    per_in_caps = 2.0 * A * sec["rho_caps"]
    per_in_web = tw[:, 0] * sec["h_in"] * sec["rho_web"]
    trap = lambda f: float(np.sum(0.5 * (f[1:] + f[:-1]) * np.diff(y_in)))
    caps_lb = 2.0 * trap(per_in_caps) if fits else float("nan")
    web_lb = 2.0 * trap(per_in_web)
    t_cap = A / sec["cap_width_in"]
    return {"cap_area_in2": A, "cap_thickness_in": t_cap, "web_in": tw[:, 0], "web_strength_in": tw[:, 1], "web_buckling_in": tw[:, 2],
            "web_buckling_governs": tw[:, 2] >= tw[:, 1], "fits": fits,
            "caps_share_of_depth": 2.0 * t_cap / sec["h_in"],
            "fit_discriminant": sec["h_in"] ** 2 - 4.0 * np.abs(M_env_lbft) * FT_IN / (sec["sigma_cap_psi"] * sec["cap_width_in"]),
            "caps_lb": caps_lb, "web_lb": web_lb, "spar_lb": caps_lb + web_lb}


def margins(wing, sec, sz, case):
    """Cap and web margins of safety of a sized spar at every station under one case's ultimate loads."""
    n = len(wing.y)
    cm = np.array([cap_margin(case["M_ult_lbft"][j] * FT_IN, sz["cap_area_in2"][j], sec["cap_width_in"][j], sec["h_in"][j], sec["sigma_cap_psi"])
                   if np.isfinite(sz["cap_area_in2"][j]) else float("nan") for j in range(n)])
    wm = np.array([web_margin(case["V_ult_lb"][j], sz["web_in"][j], sec["h_in"][j], sec["F_su_psi"], sec["K"], sec["E_web_psi"]) for j in range(n)])
    return cm, wm


def finite_min(a):
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    return float(a.min()) if a.size else None


def envelope(evaluated):
    """Largest magnitude of ultimate moment and shear over the cases, per station, and the case that sets each."""
    M = np.array([np.abs(e["M_ult_lbft"]) for e in evaluated])
    V = np.array([np.abs(e["V_ult_lb"]) for e in evaluated])
    return M.max(axis=0), V.max(axis=0), M.argmax(axis=0), V.argmax(axis=0)


def solve(c, lay, cg, version="r0", shape="schrenk", lattice=None, **sec_kw):
    """Cases, ultimate loads, the envelope of the ruled cases, the sized spar and every case's margins."""
    ch = c["ch"]
    fos = c["d"]["Nz_ultimate"] / c["d"]["n_limit"]
    wing = Wing(c, shape, lattice)
    ev = [evaluate_case(c, wing, k, lay, cg, fos) for k in cases(c, version)]
    ruled = [e for e in ev if e["kind"] == "ruled"]
    M_env, V_env, iM, iV = envelope(ruled)
    sec = section(wing, ch, **sec_kw)
    sz = size(wing, sec, M_env, V_env)
    for e in ev:
        e["cap_margin"], e["web_margin"] = margins(wing, sec, sz, e)
    return {"wing": wing, "fos": fos, "cases": ev, "M_env": M_env, "V_env": V_env,
            "M_env_case": [ruled[i]["name"] for i in iM], "V_env_case": [ruled[i]["name"] for i in iV], "section": sec, "sized": sz}


# ---- the rows -------------------------------------------------------------------------------------------------------
def row1(c, base):
    """Coding checks: every case's airload sums to its wing lift; a uniform and an elliptic cantilever against their
    closed forms (the elliptic one on the check grid, and on the run's own stations for the record)."""
    errs = [abs(r["airload_error"]) for e in base["cases"] for r in e["runs"].values()]
    half = base["wing"].half
    out = {"row": 1, "airload_largest_error": max(errs), "airload_tolerance": TOL_LIFT}
    y = stations(half, 20, [])
    F, X = distributed(y, np.full_like(y, 1.0))
    V, M = shear_moment(y, F, X)
    Vc, Mc = uniform_closed(y, 1.0, half)
    out["uniform"] = {"strips": 20, "V_error": float(np.max(np.abs(V - Vc)) / Vc[0]), "M_error": float(np.max(np.abs(M - Mc)) / Mc[0])}
    for tag, n in (("elliptic_check_grid", c["ch"]["loads"]["closed_form_check_strips"]), ("elliptic_run_stations", None)):
        y = stations(half, n, []) if n else base["wing"].y
        F, X = distributed(y, np.sqrt(np.clip(1 - (y / half) ** 2, 0, None)))
        V, M = shear_moment(y, F, X)
        Vc, Mc = elliptic_closed(y, 1.0, half)
        out[tag] = {"strips": len(y) - 1, "V_error": float(np.max(np.abs(V - Vc)) / Vc[0]), "M_error": float(np.max(np.abs(M - Mc)) / Mc[0])}
    out["closed_form_tolerance"] = TOL_CLOSED
    ok = (out["airload_largest_error"] <= TOL_LIFT and max(out["uniform"]["V_error"], out["uniform"]["M_error"]) <= TOL_CLOSED
          and max(out["elliptic_check_grid"]["V_error"], out["elliptic_check_grid"]["M_error"]) <= TOL_CLOSED)
    out["verdict"] = "pass" if ok else "fail"
    out["note"] = "the elliptic check on the run's own stations is reported, not judged: the tolerance is for the method, on the check grid"
    out["evidence_class"] = EVIDENCE[1]
    return out


def row2(c):
    """Schrenk's root bending moment of the airload alone against the lattice's, at the same half-wing lift: the
    spanwise centre of the half-wing load, root moment over half-wing lift (ft)."""
    w = c["d"]["wing"]
    lt = c["ch"]["loads"]["lattice"]
    pf = geometry.tapered(w["span"], w["aspect_ratio"], w["taper"])
    alpha = math.radians(lt["alpha_deg"])
    wing = Wing(c)
    Fa, Xa = wing.strip_loads(wing.air, 1.0)
    _, Ms = shear_moment(wing.y, Fa, Xa)
    yfine = np.linspace(0.0, wing.half, 400001)
    s = schrenk(yfine, w["span"], wing.cr, wing.ct)
    exact = float(np.trapezoid(s * yfine, yfine) / np.trapezoid(s, yfine))
    levels = {}
    for lev in lt["levels_reported"]:
        y, load, dy = lattice_span_load(pf, lev, alpha)
        levels[lev] = {"ybar_ft": float(np.sum(load * dy * y) / np.sum(load * dy)), "strips": int(len(y)),
                       "y_ft": y.tolist(), "cl_c_ft": load.tolist(), "dy_ft": dy.tolist()}
    lat = levels[lt["level_for_verdict"]]["ybar_ft"]
    dev = lat / Ms[0] - 1.0
    verdict = "pass" if abs(dev) <= TOL_ROOT_MOMENT else "fail"
    used = "lattice" if verdict == "fail" and lat > Ms[0] else "schrenk"
    return {"row": 2, "schrenk_ybar_ft_stations": float(Ms[0]), "schrenk_ybar_ft_exact": exact, "lattice": levels,
            "lattice_level": lt["level_for_verdict"], "alpha_deg": lt["alpha_deg"], "deviation": dev, "tolerance": TOL_ROOT_MOMENT,
            "verdict": verdict, "used": used, "schrenk_on_stations": {"y_ft": wing.y.tolist(), "shape_ft": wing.air.tolist()},
            "evidence_class": EVIDENCE[2]}


def case_summary(e, wing):
    j = 0
    r = e["runs"][e["speed"]]
    return {"name": e["name"], "kind": e["kind"], "n": e["n"], "weight": e["weight"], "W_lb": e["W_lb"], "fuel_lb": e["fuel_lb"],
            "speed": e["speed"], "speeds_kt": e["speeds_kt"],
            "by_speed": {sp: {"V_kt": x["V_kt"], "q_psf": x["q_psf"], "x_cg_ft": x["x_cg_ft"], "CL_wing": x["CL_wing"], "CL_tail": x["CL_tail"],
                              "L_wing_lb": x["L_wing"], "L_tail_lb": x["L_tail"], "airload_error": x["airload_error"],
                              "root_M_ult_lbft": float(x["M_ult_lbft"][j]), "root_V_ult_lb": float(x["V_ult_lb"][j])} for sp, x in e["runs"].items()},
            "L_wing_lb": r["L_wing"], "L_tail_lb": r["L_tail"],
            "V_ult_lb": e["V_ult_lb"].tolist(), "M_ult_lbft": e["M_ult_lbft"].tolist(),
            "cap_margin": [None if not np.isfinite(v) else float(v) for v in e["cap_margin"]],
            "web_margin": [None if not np.isfinite(v) else float(v) for v in e["web_margin"]],
            "min_cap_margin": finite_min(e["cap_margin"]), "min_web_margin": finite_min(e["web_margin"])}


def row3(base):
    ruled = [e for e in base["cases"] if e["kind"] == "ruled"]
    fits = base["sized"]["fits"]
    mins = [min(finite_min(e["cap_margin"]), finite_min(e["web_margin"])) for e in ruled]
    ok = fits and min(mins) >= -1e-9
    return {"row": 3, "cases": [e["name"] for e in ruled], "least_margin_by_case": dict(zip([e["name"] for e in ruled], mins)),
            "least_margin": min(mins), "every_station_sized": fits, "verdict": "pass" if ok else "fail",
            "root_moment_case": base["M_env_case"][0], "root_shear_case": base["V_env_case"][0], "evidence_class": EVIDENCE[3]}


def row4(base):
    sz = base["sized"]
    return {"row": 4, "fits": sz["fits"], "largest_caps_share_of_depth": float(np.nanmax(sz["caps_share_of_depth"])),
            "least_fit_discriminant_in2": float(np.min(sz["fit_discriminant"])), "skin_in": base["section"]["skin_in"],
            "verdict": "pass" if sz["fits"] else "fail", "evidence_class": EVIDENCE[4]}


def row5(c, base):
    sz = base["sized"]
    W = c["d"]["components_lb"]["wing"]
    share = sz["spar_lb"] / W
    return {"row": 5, "spar_lb": sz["spar_lb"], "caps_lb": sz["caps_lb"], "web_lb": sz["web_lb"], "r0_wing_lb": W, "share": share,
            "heavier_than_wing": bool(sz["spar_lb"] > W), "verdict": "finding for item 8 (spar heavier than the statistical wing)" if sz["spar_lb"] > W else "reported (no tolerance)",
            "evidence_class": EVIDENCE[5]}


def sensitivity(c, base):
    """The row 4 cases of P5 on the spar sized to the ruled cases (least margins), and the spar that would also carry
    them."""
    sens = [e for e in base["cases"] if e["kind"] == "sensitivity"]
    M_env, V_env, _, _ = envelope([e for e in base["cases"]])
    sz = size(base["wing"], base["section"], M_env, V_env)
    return {"cases": {e["name"]: {"min_cap_margin": finite_min(e["cap_margin"]), "min_web_margin": finite_min(e["web_margin"])} for e in sens},
            "spar_covering_them": {"spar_lb": sz["spar_lb"], "caps_lb": sz["caps_lb"], "web_lb": sz["web_lb"], "fits": sz["fits"]}}


def band_ends(c, base):
    """The spar weight and fit at both ends of each banded judgement, one at a time, on the ruled envelope."""
    ch = c["ch"]
    arr = yaml.safe_load(ARRANGEMENT.read_text())["arrangement"]["front_spar_chord_fraction"]
    bands = {"knock_down": ("kd", ch["knock_down"]["band"]), "skin_thickness_in": ("skin", ch["geometry"]["skin_thickness_in"]["band"]),
             "cap_width_over_chord": ("cap_w", ch["geometry"]["cap_width_over_chord"]["band"]), "spar_chord_fraction": ("x_spar", arr["band"])}
    out = {}
    for name, (kw, band) in bands.items():
        out[name] = {}
        for v in band:
            sec = section(base["wing"], ch, **{kw: v})
            sz = size(base["wing"], sec, base["M_env"], base["V_env"])
            out[name][str(v)] = {"spar_lb": sz["spar_lb"], "caps_lb": sz["caps_lb"], "web_lb": sz["web_lb"], "fits": sz["fits"],
                                 "share": sz["spar_lb"] / c["d"]["components_lb"]["wing"]}
    return out


def spar_table(base):
    w, sec, sz = base["wing"], base["section"], base["sized"]
    return {"y_ft": w.y.tolist(), "chord_ft": w.chord.tolist(), "depth_in": sec["depth_in"].tolist(), "h_in": sec["h_in"].tolist(),
            "cap_width_in": sec["cap_width_in"].tolist(), "M_env_ult_lbft": base["M_env"].tolist(), "V_env_ult_lb": base["V_env"].tolist(),
            "M_env_case": base["M_env_case"], "V_env_case": base["V_env_case"],
            "cap_area_in2": sz["cap_area_in2"].tolist(), "cap_thickness_in": sz["cap_thickness_in"].tolist(),
            "caps_share_of_depth": sz["caps_share_of_depth"].tolist(), "web_in": sz["web_in"].tolist(),
            "web_strength_in": sz["web_strength_in"].tolist(), "web_buckling_in": sz["web_buckling_in"].tolist(),
            "web_buckling_governs": sz["web_buckling_governs"].tolist(), "fit_discriminant_in2": sz["fit_discriminant"].tolist()}


def r1_findings(c, base):
    """The same sizing with P4b's layout and centre of gravity (PD-21), r1's weights and P2's clean maximum lift."""
    b1 = solve(c, c["lay_r1"], c["cg_r1"], "r1", base["shape"], base.get("lattice"))
    out = {"layout": c["p4b_chosen"], "empty_weight_change_lb": c["r1_empty_weight_change_lb"], "CL_max_clean": c["CL_max_p2"],
           "cg_ft": c["cg_r1"], "cases": [case_summary(e, b1["wing"]) for e in b1["cases"]],
           "root_M_env_ult_lbft": float(b1["M_env"][0]), "root_V_env_ult_lb": float(b1["V_env"][0]),
           "root_moment_case": b1["M_env_case"][0], "spar_lb": b1["sized"]["spar_lb"], "fits": b1["sized"]["fits"],
           "root_M_env_ult_lbft_r0": float(base["M_env"][0]), "spar_lb_r0": base["sized"]["spar_lb"]}
    out["root_moment_change"] = out["root_M_env_ult_lbft"] / out["root_M_env_ult_lbft_r0"] - 1.0
    out["spar_change_lb"] = out["spar_lb"] - out["spar_lb_r0"]
    # the r0 layout with r1's weights and maximum lift alone, to separate the layout's share
    b2 = solve(c, c["lay_r0"], {**c["cg_r0"]}, "r1", base["shape"], base.get("lattice"))
    out["weights_and_CL_max_only"] = {"root_M_env_ult_lbft": float(b2["M_env"][0]), "spar_lb": b2["sized"]["spar_lb"]}
    return out


def p4_trim_check(c):
    """P4's trim legs recomputed with the same function and inputs: the tail lift coefficients must equal P4's."""
    legs = c["p4"]["as_arranged"]["trim"]["legs"]
    worst = max(abs(m.tail_cl_trim(c["d"], c["L"], c["lay_r0"], v["CL_wing"], v["x_cg_ft"], c["cm_w"]) / v["CL_tail"] - 1.0) for v in legs.values())
    return {"legs": len(legs), "largest_relative_difference": worst}


def run(out, log=print):
    t0 = time.time()
    own = str(out.relative_to(REPO))
    tree = tree_state(own)
    if tree["git_dirty"]:
        raise SystemExit("P7 starts from a clean committed tree; uncommitted: " + "; ".join(tree["git_dirty_files"]))
    out.mkdir(parents=True, exist_ok=True)
    import matplotlib
    files = {"r0_design": R0 / "design_pusher.json", "r0_ledger": R0 / "ledger.yaml", "choices": CHOICES, "arrangement": ARRANGEMENT,
             "p2_record": P2_RECORD, "p4_record": P4_RECORD, "p4b_record": P4B_RECORD, "p5_record": P5_RECORD}
    c = context()
    d = c["d"]
    log(f"commit {tree['commit']}, clean tree; inputs read")
    res = {"inputs": dict(tree, command="python -m prelim.p7_spar " + " ".join(sys.argv[1:]), seed=None,
                          seed_note="no random numbers are drawn in P7", python=platform.python_version(), numpy=np.__version__,
                          scipy=scipy.__version__, pyyaml=yaml.__version__, matplotlib=matplotlib.__version__,
                          files={k: str(p.relative_to(REPO)) for k, p in files.items()}, sha256={k: sha256(p) for k, p in files.items()}),
           "review": REVIEW, "baseline": str(R0.relative_to(REPO)), "choices": c["ch"],
           "r0": {"W0_lb": d["W0_lb"], "fuel_lb": d["fuel_lb"], "wing": d["wing"], "components_lb": d["components_lb"],
                  "n_limit": d["n_limit"], "Nz_ultimate": d["Nz_ultimate"], "CL_max_clean": d["CL_max"]["clean"],
                  "half_track_ft": d["layout"]["gear_track"]["half_track_ft"], "fuselage_diameter_ft": d["fuselage"]["diameter"]},
           "p4_inputs": {"layout": c["lay_r0"], "cg": c["cg_r0"], "cm_w": c["cm_w"], "cm0_p2": c["p4"]["cm0_p2"], "tanks": c["tanks"],
                         "trim_check": p4_trim_check(c)}}
    log("row 2: Schrenk against the lattice")
    res["row2"] = row2(c)
    lattice = None
    if res["row2"]["used"] == "lattice":
        lv = res["row2"]["lattice"][res["row2"]["lattice_level"]]
        lattice = (np.array(lv["y_ft"]), np.array(lv["cl_c_ft"]), np.array(lv["dy_ft"]))
    log(f"airload used: {res['row2']['used']}; sizing the ruled cases")
    base = solve(c, c["lay_r0"], c["cg_r0"], "r0", res["row2"]["used"], lattice)
    base["shape"], base["lattice"] = res["row2"]["used"], lattice
    res["fos"] = base["fos"]
    res["section"] = {k: v for k, v in base["section"].items() if not isinstance(v, np.ndarray)}
    res["cases"] = [case_summary(e, base["wing"]) for e in base["cases"]]
    res["spar"] = spar_table(base)
    res["row1"] = row1(c, base)
    res["row3"] = row3(base)
    res["row4"] = row4(base)
    res["row5"] = row5(c, base)
    log(f"spar {res['row5']['spar_lb']:.2f} lb ({100 * res['row5']['share']:.1f} % of the wing)")
    res["sensitivity"] = sensitivity(c, base)
    res["band_ends"] = band_ends(c, base)
    log("r1 findings")
    res["r1"] = r1_findings(c, base)
    res["acceptance"] = [{"row": r, "verdict": res[f"row{r}"]["verdict"]} for r in (1, 2, 3, 4, 5)]
    end = tree_state(own)
    res["tree_at_end"] = end
    res["inputs"]["tree_unchanged_during_run"] = (not end["git_dirty"]) and end["commit"] == tree["commit"]
    res["runtime_s"] = time.time() - t0
    (out / "p7.json").write_text(json.dumps(_plain(res), indent=1))
    log(f"done ({res['runtime_s']:.0f} s)")
    return res


def _plain(o):
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, np.ndarray):
        return _plain(o.tolist())
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--figures", help="folder for the figures (default: next to the report)")
    ap.add_argument("--report-only", action="store_true", help="write the report and figures from OUT/p7.json")
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
        from prelim import p7_report
        report = (REPO / a.report).resolve()
        figures = (REPO / a.figures).resolve() if a.figures else report.parent / "figures" / report.stem
        p7_report.write_figures(out, figures)
        report.write_text(p7_report.report_text(out))


if __name__ == "__main__":
    main()

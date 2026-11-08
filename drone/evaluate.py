"""One design evaluation: aerodynamics, mass closure, cruise point, mission and gates (T10.5).

evaluate(params, fixed, section=None, level="medium") is a pure, deterministic function of its
arguments. Every physical constant comes from the ledger (`fixed`); the only literals are exact
mathematics and the numerical settings of the closure named below, which do not change the
converged answer.
"""
import functools
import math

import numpy as np

from drone import drag, geometry, mission, naca, vlm
from drone import section as section_mod

_CAMBER_POSITION = 0.4          # NACA four-digit camber position, fixed at 40 % (spec section 2)
_ALPHA_HI = math.radians(4.0)   # second lattice solve; the first is at alpha = 0
_MAX_ITER = 100                 # mass closure: at most 100 iterations (spec section 3, gate 3)
_TOL = 1e-9                     # mass closure: relative change below 1e-9 (spec section 3)
_M0_OTHER_FRACTION = 0.3        # starting guess m0 = payload / (1 - f_b - 0.3); a guess only
_V0 = 15.0                      # m/s, Reynolds number of the first iterate's section; a guess only


@functools.cache
def _aero(aspect_ratio, taper_ratio, camber_pct, level):
    """Lattice results of the wing at unit span, cached per (AR, taper, camber, level).

    The linear vortex lattice is scale invariant: CL, e and the section cl distribution depend on
    the planform's shape (AR, taper) and the camber line only, not on span, thickness or battery
    fraction. So two solves at alpha 0 and 4 deg on tapered(1, AR, taper), plus derivatives(), give
    every lattice quantity a design needs; this cache keeps an evaluation under a second.

    Returns CL_alpha (per rad), alpha_L0 (rad), e (at 4 deg), the strip centres eta, the strip
    loading at alpha 0, cl0, and its slope dcl (per rad), so that cl_i(alpha) = cl0_i + dcl_i alpha.
    """
    planform = geometry.tapered(1.0, aspect_ratio, taper_ratio)
    m = camber_pct / 100.0

    def slope(x):
        return naca.camber_line(x, m, _CAMBER_POSITION)[1]

    camber = slope if m > 0.0 else None
    r0 = vlm.solve(planform, 0.0, level, camber)
    r4 = vlm.solve(planform, _ALPHA_HI, level, camber)
    der = vlm.derivatives(planform, level, camber)
    eta = np.asarray(r0["eta"])
    cl0 = np.asarray(r0["cl"])
    dcl = (np.asarray(r4["cl"]) - cl0) / _ALPHA_HI
    for arr in (eta, cl0, dcl):
        arr.setflags(write=False)          # the cached arrays are shared between calls
    return {"CL_alpha": der["CL_alpha"], "alpha_L0": der["alpha_L0"], "e": r4["e"],
            "eta": eta, "cl0": cl0, "dcl": dcl}


def _alpha_of(aero, CL):
    """Wing angle of attack for a wing CL: alpha = alpha_L0 + CL / CL_alpha."""
    return aero["alpha_L0"] + CL / aero["CL_alpha"]


def _strip_cl(aero, CL):
    """Section lift per strip at a wing CL, linear in alpha: cl_i = cl0_i + dcl_i alpha."""
    return aero["cl0"] + aero["dcl"] * _alpha_of(aero, CL)


def _wing_cl_max(aero, cl_max):
    """Wing CL at which the most loaded strip first reaches the section cl_max.

    Strip i reaches it at alpha_i = (cl_max - cl0_i) / dcl_i; the wing stalls at min_i alpha_i, so
    CL_max_wing = CL_alpha (min_i alpha_i - alpha_L0).
    """
    alpha_stall = float(np.min((cl_max - aero["cl0"]) / aero["dcl"]))
    return aero["CL_alpha"] * (alpha_stall - aero["alpha_L0"])


def _spar_mass(params, geom, W, fixed):
    """Spar caps sized by the root bending moment of an elliptic lift distribution.

    Each half-wing carries W/2 at its centroid, 4/(3 pi) (b/2) from the root, so at the ultimate
    load M = n_lim FoS (W/2) (4/(3 pi)) (b/2). Two caps of area A at a depth h equal to the root
    section thickness, h = (t/c) c_root, carry it as sigma = M / (A h), so A = M / (sigma_allow h).
    Caps run the full span b at constant area: m_spar = 2 A b rho_spar.
    """
    st = fixed["structure"]
    b = geom["wing"]["b"]
    moment = (st["limit_load_factor"] * st["factor_of_safety"] * (W / 2.0)
              * (4.0 / (3.0 * math.pi)) * (b / 2.0))
    depth = params["thickness_pct"] / 100.0 * geom["wing"]["c_root"]
    area = moment / (st["spar_allowable_stress_Pa"] * depth)
    return 2.0 * area * b * st["spar_material_density_kg_m3"]


def _helmbold(ar):
    """Lift-curve slope of a finite wing (Helmbold): a = 2 pi AR / (2 + sqrt(AR^2 + 4)), per rad."""
    return 2.0 * math.pi * ar / (2.0 + math.sqrt(ar * ar + 4.0))


def _tip_panel_aspect(geom, level):
    """Largest panel aspect ratio (long side over short side) on the tip strip of the lattice.

    The strip width is that of the outermost cosine-spaced strip, (b/2)(1 - cos(pi/N))/2, and the
    chordwise panel lengths are c_tip times the steps of xi = 1 - cos(pi k / (2M)), the spacing of
    drone/vlm.py. Both ratios width/length and length/width are checked, so a panel too long in
    either direction is caught.
    """
    m, n = vlm.LEVELS[level]
    width = 0.5 * geom["wing"]["b"] * 0.5 * (1.0 - math.cos(math.pi / n))
    xi = 1.0 - np.cos(0.5 * np.pi * np.arange(m + 1) / m)
    lengths = geom["wing"]["c_tip"] * np.diff(xi)
    return float(max(np.max(width / lengths), np.max(lengths / width)))


def _closure(params, fixed, section, aero):
    """Fixed-point iteration on take-off mass m: m_new = sum of the component masses at m."""
    air, rules, prop = fixed["air"], fixed["rules"], fixed["propulsion"]
    rho, mu, g = air["density_kg_m3"], air["dynamic_viscosity_Pa_s"], air["gravity_m_s2"]
    eta_p = prop["propulsive_efficiency"]
    skin = fixed["structure"]["skin_areal_density_kg_m2"]
    payload = rules["payload_mass_kg"]
    f_b = params["battery_fraction"]
    m = payload / (1.0 - f_b - _M0_OTHER_FRACTION)
    v_prev = _V0
    for iteration in range(1, _MAX_ITER + 1):
        geom = geometry.build(params, fixed, mtow_guess=m)
        wing = geom["wing"]
        W = m * g
        sec = section
        if sec is None:
            re = rho * v_prev * wing["c_mac"] / mu
            sec = section_mod.low_fidelity(params["camber_pct"], params["thickness_pct"], re, fixed)
        cl_max_wing = _wing_cl_max(aero, sec.cl_max)

        def polar(CL, geom=geom, sec=sec, W=W):
            """CD at a wing CL (float or array) from drag.total, flying at V = sqrt(2 W / (rho S CL))."""
            if np.ndim(CL) == 0:
                V = math.sqrt(2.0 * W / (rho * geom["wing"]["S"] * CL))
                strips = {"e": aero["e"], "eta": aero["eta"], "cl": _strip_cl(aero, CL)}
            else:                                  # an array of CL: strip loading is (n, strips)
                CL = np.asarray(CL, dtype=float)
                V = np.sqrt(2.0 * W / (rho * geom["wing"]["S"] * CL))
                strips = {"e": aero["e"], "eta": aero["eta"],
                          "cl": aero["cl0"] + aero["dcl"] * _alpha_of(aero, CL)[:, None]}
            return drag.total(geom, sec, strips, CL, V, fixed)["CD"]

        cruise = mission.cruise_point(polar, W, wing["S"], rho, cl_max_wing, fixed)
        p_cruise = cruise["min_power"]["P"]
        p_installed = max(rules["installed_power_margin"] * p_cruise,
                          W * rules["rate_of_climb_m_s"] / eta_p + p_cruise)
        wet = geom["wetted_areas"]
        masses = {
            "payload": payload,
            "battery": f_b * m,
            "wing_skin": skin * wet["wing"],
            "spar": _spar_mass(params, geom, W, fixed),
            "tail": skin * (wet["htail"] + wet["vtail"]),
            "fuselage": skin * wet["fuselage"],
            "propulsion": p_installed / prop["specific_power_W_per_kg"],
        }
        if any(not v > 0.0 for v in masses.values()):
            raise ValueError(f"mass closure: non-positive component mass {masses}")
        m_new = sum(masses.values())
        if not m_new > 0.0:
            raise ValueError(f"mass closure: non-positive take-off mass {m_new}")
        residual = abs(m_new - m) / m
        m_iterate, m, v_prev = m, m_new, cruise["min_power"]["V"]
        if residual < _TOL:
            return {"m": m, "m_iterate": m_iterate, "masses": masses, "iterations": iteration,
                    "residual": residual,
                    "geom": geom, "section": sec, "polar": polar, "cruise": cruise,
                    "cl_max_wing": cl_max_wing, "P_cruise": p_cruise, "P_installed": p_installed}
    raise ValueError(f"mass closure did not converge in {_MAX_ITER} iterations "
                     f"(last relative change {residual:.3g}, m = {m:.6g} kg)")


def evaluate(params, fixed, section=None, level="medium"):
    """Evaluate one design: endurance, take-off mass and every recorded output (spec section 5).

    section None -> low-fidelity section data at the cruise Reynolds number of the previous closure
    iterate (the first iterate uses V = 15 m/s and c_mac); otherwise the given SectionData is used
    as is (its Reynolds number is the queued one) and re_cruise is still computed.
    """
    air, rules, prop, bat = fixed["air"], fixed["rules"], fixed["propulsion"], fixed["battery"]
    rho, mu, g = air["density_kg_m3"], air["dynamic_viscosity_Pa_s"], air["gravity_m_s2"]
    eta_p = prop["propulsive_efficiency"]
    aero = _aero(float(params["aspect_ratio"]), float(params["taper_ratio"]),
                 float(params["camber_pct"]), level)
    c = _closure(params, fixed, section, aero)
    m, geom, sec, cruise = c["m"], c["geom"], c["section"], c["cruise"]
    # the converged geometry, section and cruise point are those of the last iterate's mass,
    # which equals m to 1e-9 relative
    wing = geom["wing"]
    W = m * g
    cp = cruise["min_power"]
    cl_cruise, v_cruise = cp["CL"], cp["V"]
    m_batt = c["masses"]["battery"]
    t_climb = rules["climb_allowance_s"]
    endurance = mission.endurance_h(m_batt, bat["pack_specific_energy_Wh_per_kg"],
                                    bat["depth_of_discharge"], eta_p, c["P_cruise"],
                                    c["P_installed"], t_climb)
    usable_J = (bat["depth_of_discharge"] * bat["pack_specific_energy_Wh_per_kg"] * 3600.0 * m_batt
                - c["P_installed"] * t_climb)
    range_km = usable_J * eta_p * cruise["best_ld"]["L_over_D"] / W / 1000.0
    # at the mass the cruise point was flown at (the last iterate, equal to mtow to 1e-9), so that
    # V_cruise >= stall_margin V_stall holds exactly and not only to the closure tolerance
    v_stall = mission.v_stall(c["m_iterate"], wing["S"], c["cl_max_wing"], rho, g)
    re_cruise = rho * v_cruise * wing["c_mac"] / mu
    cd_total = c["polar"](cl_cruise)
    cd_induced = cl_cruise**2 / (math.pi * wing["AR"] * aero["e"])

    # static margin with the CG at the wing's aerodynamic centre (x_ref): the tail term only,
    # SM = V_H (a_t / a_w) (1 - d eps/d alpha), d eps/d alpha = 2 a_w / (pi AR) (Raymer, Aircraft
    # Design, longitudinal static stability; Anderson, Aircraft Performance and Design, ch. 7)
    a_w = aero["CL_alpha"]
    a_t = _helmbold(rules["tail_aspect_ratio_horizontal"])
    d_eps = 2.0 * a_w / (math.pi * wing["AR"])
    static_margin = rules["tail_volume_horizontal"] * (a_t / a_w) * (1.0 - d_eps)
    x_np = geom["planform"].x_ref + static_margin * wing["c_mac"]

    # tip-stall indicator: strip nearest eta 0.9, its cl over the section cl_max at CL_max_wing
    i_tip = int(np.argmin(np.abs(aero["eta"] - 0.9)))
    tip_stall = float(_strip_cl(aero, c["cl_max_wing"])[i_tip] / sec.cl_max)

    out = {
        "endurance_h": endurance,
        "mtow_kg": m,
        "range_km": range_km,
        "v_cruise": v_cruise,
        "v_stall": v_stall,
        "wing_loading": W / wing["S"],
        "re_cruise": re_cruise,
        "throttle_cruise": c["P_cruise"] / c["P_installed"],
        "static_margin": static_margin,
        "cl_max": sec.cl_max,
        "e_span": aero["e"],
        "cd0": cd_total - cd_induced,
        "masses": c["masses"],
        "closure_iterations": c["iterations"],
        "closure_residual": c["residual"],
        "diagnostics": {
            "P_cruise_W": c["P_cruise"],
            "P_installed_W": c["P_installed"],
            "section_source": sec.source,
            "CL_cruise": cl_cruise,
            "CD_cruise": cd_total,
            "L_over_D": cl_cruise / cd_total,
            "L_over_D_max": cruise["best_ld"]["L_over_D"],
            "v_best_ld": cruise["best_ld"]["V"],
            "cl_max_wing": c["cl_max_wing"],
            "tip_stall_ratio": tip_stall,
            "alpha_cruise_deg": math.degrees(_alpha_of(aero, cl_cruise)),
            "x_np": x_np,
            "CL_alpha_wing": a_w,
            "tip_panel_aspect": _tip_panel_aspect(geom, level),
            "structure_propulsion_fraction": 1.0 - params["battery_fraction"]
            - rules["payload_mass_kg"] / m,
        },
    }
    out["gates"] = _gates(params, out, wing, fixed)
    return out


def _gates(params, out, wing, fixed):
    """Gate messages in the inlet form (spec section 4), empty when the design is clean."""
    rules = fixed["rules"]
    d = out["diagnostics"]
    msgs = []
    re = out["re_cruise"]
    if not rules["reynolds_min"] <= re <= rules["reynolds_max"]:
        msgs.append(f"gate 1 (reynolds range): Re = {re:.4g} outside "
                    f"[{rules['reynolds_min']:.4g}, {rules['reynolds_max']:.4g}]")
    v_min = rules["stall_margin"] * out["v_stall"]
    if out["v_cruise"] < v_min * (1.0 - _TOL):
        msgs.append(f"gate 2 (stall margin): V_cruise {out['v_cruise']:.4g} m/s below "
                    f"{rules['stall_margin']} x V_stall {out['v_stall']:.4g} m/s")
    cl_lim = rules["cruise_cl_fraction_of_clmax"] * d["cl_max_wing"]
    if d["CL_cruise"] > cl_lim * (1.0 + _TOL):
        msgs.append(f"gate 2 (stall margin): cruise CL {d['CL_cruise']:.4g} above "
                    f"{rules['cruise_cl_fraction_of_clmax']} x CL_max {d['cl_max_wing']:.4g}")
    frac = d["structure_propulsion_fraction"]
    if frac < rules["structure_fraction_min"]:
        msgs.append(f"gate 3 (mass closure): structure plus propulsion fraction {frac:.4g} below "
                    f"{rules['structure_fraction_min']}")
    if wing["c_tip"] < rules["tip_chord_min_m"]:
        msgs.append(f"gate 4 (manufacturing floor): tip chord {wing['c_tip']:.4g} m below "
                    f"{rules['tip_chord_min_m']} m")
    depth = params["thickness_pct"] / 100.0 * wing["c_root"]
    if depth < rules["spar_depth_min_m"]:
        msgs.append(f"gate 4 (manufacturing floor): root section thickness {depth:.4g} m below "
                    f"{rules['spar_depth_min_m']} m")
    wl = out["wing_loading"]
    if not rules["wing_loading_min_N_m2"] <= wl <= rules["wing_loading_max_N_m2"]:
        msgs.append(f"gate 4 (wing loading): {wl:.4g} N/m^2 outside "
                    f"[{rules['wing_loading_min_N_m2']}, {rules['wing_loading_max_N_m2']}] N/m^2")
    pa = d["tip_panel_aspect"]
    if pa > rules["lattice_panel_aspect_max"]:
        msgs.append(f"gate 5 (lattice quality): panel aspect ratio {pa:.4g} above "
                    f"{rules['lattice_panel_aspect_max']}")
    return msgs

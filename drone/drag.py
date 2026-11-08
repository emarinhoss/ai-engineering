"""Drag build-up: skin friction, parasite drag of the non-wing components, and the total."""

from __future__ import annotations

import math

import numpy as np

from drone import ledger

_RULES = ledger.load("rules")


def cf_laminar(re):
    """Blasius flat plate, c / sqrt(Re)."""
    return _RULES["cf_laminar_coeff"] / math.sqrt(re)


def cf_turbulent(re):
    """Prandtl-Schlichting flat plate, c Re^-0.2."""
    return _RULES["cf_turbulent_coeff"] * re ** -0.2


def cf(re):
    """Laminar below the transition Reynolds number, turbulent above."""
    if np.ndim(re) == 0:
        return cf_laminar(re) if re < _RULES["cf_transition_reynolds"] else cf_turbulent(re)
    re = np.asarray(re, dtype=float)       # an array of Reynolds numbers: same rule elementwise
    return np.where(re < _RULES["cf_transition_reynolds"],
                    _RULES["cf_laminar_coeff"] / np.sqrt(re), _RULES["cf_turbulent_coeff"] * re ** -0.2)


def parasite(geometry, V, fixed):
    """Drag coefficient (on wing area) of fuselage and tails; the wing's comes from the section.

    CD_component = cf(Re_c) FF S_wet / S_wing. Tail chord is sqrt(S_tail/AR_tail).
    """
    rules = fixed["rules"]
    rho = fixed["air"]["density_kg_m3"]
    mu = fixed["air"]["dynamic_viscosity_Pa_s"]
    s_ref = geometry["wing"]["S"]
    wet = geometry["wetted_areas"]
    tc = rules["tail_thickness_ratio"]
    ff_tail = 1.0 + rules["wing_form_factor_k1"] * tc + rules["wing_form_factor_k2"] * tc**4
    out = {}
    fus = geometry["fuselage"]
    f = fus["length"] / fus["diameter"]
    ff_fus = 1.0 + rules["body_form_factor_k"] / f**3 + f / rules["body_form_factor_k2"]
    out["fuselage"] = cf(rho * V * fus["length"] / mu) * ff_fus * wet["fuselage"] / s_ref
    for name, s_key, ar_key in (("htail", "S_h", "tail_aspect_ratio_horizontal"),
                                ("vtail", "S_v", "tail_aspect_ratio_vertical")):
        s_tail = geometry["tail"][s_key]
        chord = math.sqrt(s_tail / rules[ar_key])
        out[name] = cf(rho * V * chord / mu) * ff_tail * wet[name] / s_ref
    out["total"] = sum(out.values())
    return out


def total(geometry, section, vlm_result, CL, V, fixed):
    """CD = induced + profile (strip integral of the section drag) + parasite.

    CL and V may be floats or arrays of one shape (n,); vlm_result["cl"] is then (n, strips).
    The parasite drag depends on CL through V (Reynolds number), so it broadcasts too.
    """
    wing = geometry["wing"]
    s = wing["S"]
    cd_i = CL**2 / (math.pi * wing["AR"] * vlm_result["e"])
    eta = np.asarray(vlm_result["eta"], dtype=float)
    cl_strip = np.asarray(vlm_result["cl"], dtype=float)
    edges = np.concatenate(([0.0], 0.5 * (eta[:-1] + eta[1:]), [1.0]))
    dy = np.diff(edges) * geometry["planform"].span / 2.0
    chord = geometry["planform"].chord_at(eta)
    cd_p = 2.0 * np.sum(section.cd_of_cl(cl_strip) * chord * dy, axis=-1) / s
    if np.ndim(cd_p) == 0:
        cd_p = float(cd_p)
    cd_par = parasite(geometry, V, fixed)["total"]
    return {"CD": cd_i + cd_p + cd_par, "CD_induced": cd_i, "CD_profile": cd_p,
            "CD_parasite": cd_par}

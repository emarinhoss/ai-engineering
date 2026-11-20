"""Aerodynamics: lift slope, maximum lift, parasite drag build-up, drag due to lift (Raymer ch. 12,
13.6). Areas in ft^2, lengths in ft."""
import math


def fuselage_lift_factor(d, b):
    """F = 1.07 (1 + d/b)^2 (12.9), p. 266: fuselage diameter d, span b."""
    return 1.07 * (1.0 + d / b) ** 2


def lift_slope(aspect_ratio, mach=0.0, airfoil_efficiency=0.95, sweep_max_t=0.0,
               s_exposed_ratio=1.0, F=1.0):
    """Subsonic wing lift slope per radian (12.6)-(12.8), p. 266."""
    beta2 = 1.0 - mach ** 2
    eta = airfoil_efficiency
    root = math.sqrt(4.0 + aspect_ratio ** 2 * beta2 / eta ** 2
                     * (1.0 + math.tan(sweep_max_t) ** 2 / beta2))
    return 2.0 * math.pi * aspect_ratio / (2.0 + root) * s_exposed_ratio * F


def wing_cl_max(cl_max_airfoil, sweep_qc=0.0):
    """Clean wing CL_max = 0.9 cl_max cos(sweep) (12.15), p. 270."""
    return 0.9 * cl_max_airfoil * math.cos(sweep_qc)


def flapped_cl_max(cl_max_clean, delta_cl_max_airfoil, s_flapped_ratio, hinge_sweep=0.0):
    """Flapped wing: Delta CL_max = Delta cl_max (S_flapped/S_ref) cos(hinge sweep) (12.21),
    p. 278, added to the clean CL_max. Delta cl_max from Table 12.2, p. 279 (plain and split 0.9,
    slotted 1.3, Fowler 1.3 c'/c)."""
    return cl_max_clean + delta_cl_max_airfoil * s_flapped_ratio * math.cos(hinge_sweep)


def reynolds(rho, V, length, mu):
    """R = rho V l / mu (12.26), p. 281."""
    return rho * V * length / mu


def cf_laminar(R):
    """Laminar flat-plate skin friction 1.328/sqrt(R) (12.25), p. 281."""
    return 1.328 / math.sqrt(R)


def cf_turbulent(R, mach):
    """Turbulent flat-plate skin friction (12.27), p. 282."""
    return 0.455 / (math.log10(R) ** 2.58 * (1.0 + 0.144 * mach ** 2) ** 0.65)


def cutoff_reynolds_subsonic(length, roughness_k):
    """Cutoff Reynolds number for surface roughness, 38.21 (l/k)^1.053 (12.28), p. 282.
    Raymer Table 12.4, p. 283, skin roughness k (ft): smooth paint 2.08e-5, production sheet metal 1.33e-5,
    polished sheet metal 0.50e-5, smooth molded composite 0.17e-5."""
    return 38.21 * (length / roughness_k) ** 1.053


def cf_component(rho, V, length, mu, mach, roughness_k, laminar_fraction=0.0):
    """Skin friction of a component: the smaller of R and the cutoff R (p. 282), turbulent (12.27),
    blended with laminar (12.25) by the laminar fraction (p. 282-283)."""
    R = min(reynolds(rho, V, length, mu), cutoff_reynolds_subsonic(length, roughness_k))
    cf_t = cf_turbulent(R, mach)
    return laminar_fraction * cf_laminar(R) + (1.0 - laminar_fraction) * cf_t


def form_factor_wing(t_c, x_c_max_t, mach, sweep_max_t=0.0):
    """Wing, tail, strut and pylon form factor (12.30), p. 283."""
    return ((1.0 + 0.6 / x_c_max_t * t_c + 100.0 * t_c ** 4)
            * (1.34 * mach ** 0.18 * math.cos(sweep_max_t) ** 0.28))


def form_factor_fuselage(fineness):
    """Fuselage and smooth canopy form factor 1 + 60/f^3 + f/400 (12.31), p. 283."""
    return 1.0 + 60.0 / fineness ** 3 + fineness / 400.0


def wetted_area_wing(s_exposed, t_c):
    """Wing wetted area from the exposed planform: 2.003 S_exp for t/c < 0.05, else
    S_exp (1.977 + 0.52 t/c) ((7.10)-(7.11), p. 150)."""
    if t_c < 0.05:
        return 2.003 * s_exposed
    return s_exposed * (1.977 + 0.52 * t_c)


def cd0_buildup(components, s_ref, misc_d_q=0.0, leakage_fraction=0.05):
    """(CD0)_subsonic = sum(Cf FF Q S_wet)/S_ref + CD_misc, then times (1 + leakage) (12.24),
    p. 280; DR-1 adds 5 % for leaks and protuberances (p. 572). components: iterable of dicts with
    cf, ff, q (interference factor) and s_wet. Returns (CD0, per-component CD0 dict)."""
    parts = {}
    total = 0.0
    for c in components:
        cd = c["cf"] * c["ff"] * c.get("q", 1.0) * c["s_wet"] / s_ref
        parts[c["name"]] = cd
        total += cd
    total += misc_d_q / s_ref
    return (1.0 + leakage_fraction) * total, parts


def cd0_equivalent_skin_friction(cfe, s_wet_over_s_ref):
    """CD0 = Cfe S_wet/S_ref (12.23), p. 280; Table 12.3: light aircraft single engine Cfe 0.0055."""
    return cfe * s_wet_over_s_ref


def misc_engine_drag_area(bhp):
    """Miscellaneous engine drag (D/q)_misc = 2e-4 bhp ft^2 (13.19), p. 330."""
    return 2e-4 * bhp


def cooling_drag_area(bhp, T_R, sigma, V):
    """Piston-engine cooling drag (D/q) = 4.9e-7 bhp T^2/(sigma V) ft^2 (13.18), p. 330.
    Piston engines only; a turboprop has no cooling drag of this form."""
    return 4.9e-7 * bhp * T_R ** 2 / (sigma * V)


def oswald_straight_wing(aspect_ratio):
    """Straight-wing span efficiency e = 1.78 (1 - 0.045 A^0.68) - 0.64 (12.49), p. 299."""
    return 1.78 * (1.0 - 0.045 * aspect_ratio ** 0.68) - 0.64


def induced_drag_factor(aspect_ratio, e):
    """K = 1/(pi A e) (12.48), p. 298."""
    return 1.0 / (math.pi * aspect_ratio * e)


def wetted_aspect_ratio(span, s_wet):
    """Wetted aspect ratio b^2/S_wet (p. 21), the parameter of Raymer's Fig. 3.6."""
    return span ** 2 / s_wet

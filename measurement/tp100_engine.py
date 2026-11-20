"""The PBS TP100 represented by Mattingly's App. K turboprop cycle (measurement/turboprop_cycle.py).

The maker publishes rated shaft power (241 shp), take-off SFC (0.847 lb/(hp h)) and a cruise SFC
(0.901) but not the cycle: compressor pressure ratio, turbine inlet temperature and component
efficiencies are unknown. So the engine is not one cycle but a family. Each member takes an
assumed turbine inlet temperature and polytropic efficiencies (CYCLE_GRID, small uncooled engine)
and its compressor pressure ratio is then solved so that the shaft SFC at sea level, take-off
power equals the datasheet 0.847. The spread over the family is reported with every result.

Fixed assumptions for every member (study choices, not datasheet values): no turbine cooling
(eps1 = eps2 = 0), no bleed or power takeoff, pi_d 0.98, pi_b 0.95, pi_n 0.99, eta_b 0.98,
mechanical and gearbox efficiencies 0.98, h_PR 18,400 Btu/lbm and the book's MSH gas model with
gamma_t = 1.3 (the value that reproduces Fig. K.4; see tests/task12/test_turboprop_cycle.py).
The take-off rating is evaluated at sea level, M0 = 0.1 (about 66 kt), not static: the cycle's
thrust terms divide by flight speed. The design turbine ratio tau_t is the book's optimum
tau_t* at that condition (p. 597).

Control law (p. 606): full throttle is Tt4 at its rated value or less, with the compressor
pressure ratio held to its sea-level rated value. Rating at sea-level ISA means a theta break of
1.0. A flat-rated engine (theta break above 1) would give more power at altitude;
`power_available(..., hold_pi_c=False)` gives that upper bound (Tt4 limit only).
"""
import itertools

from conceptual.units import KT, isa
from measurement import turboprop_cycle as tc

RATED_SHP = 241.0
BSFC_TAKEOFF = 0.847
BSFC_CRUISE = 0.901
M_RATING = 0.1

CYCLE_GRID = {"Tt4": (2000.0, 2200.0, 2400.0), "e_c": (0.80, 0.85), "e_t": (0.85, 0.90)}


def _gas(Tt4, e_c, e_t):
    return dict(tc.BOOK_EXAMPLE, Tt4=Tt4, e_c=e_c, e_tH=e_t, e_tL=e_t, eps1=0.0, eps2=0.0,
                eta_b=0.98, gamma_t=1.3, pi_d=0.98, pi_b=0.95, pi_n=0.99, eta_mH=0.98,
                eta_mL=0.98, eta_g=0.98, eta_prop=0.80)


def calibrated(Tt4, e_c, e_t, bsfc=BSFC_TAKEOFF, shp=RATED_SHP):
    """One family member: (gas inputs k, reference design dict with m0), or None when no compressor
    pressure ratio between 2 and 14 gives the datasheet SFC with these assumptions."""
    k = _gas(Tt4, e_c, e_t)
    sl = isa(0.0)

    def at(pi_c):
        t = tc.optimum_tau_t(M_RATING, sl["T"], sl["p"], pi_c, k)
        return tc.design_point(M_RATING, sl["T"], sl["p"], pi_c, t, k)

    lo, hi = 2.0, 14.0
    if at(hi)["bsfc"] > bsfc or at(lo)["bsfc"] < bsfc:
        return None
    for _ in range(50):                      # bsfc falls as pi_c rises over this range
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if at(mid)["bsfc"] > bsfc else (lo, mid)
    ref = at(hi)
    ref["m0"] = shp / ref["shaft_hp_per_m0"]
    return k, ref


def family():
    """All members of CYCLE_GRID that calibrate, as dicts with their assumptions."""
    out = []
    for Tt4, e_c, e_t in itertools.product(*CYCLE_GRID.values()):
        m = calibrated(Tt4, e_c, e_t)
        if m is not None:
            out.append({"Tt4": Tt4, "e_c": e_c, "e_t": e_t, "k": m[0], "ref": m[1]})
    return out


def power_available(member, h_ft, V_kt, hold_pi_c=True):
    """Full-throttle shaft hp at altitude and flight speed."""
    a = isa(h_ft)
    M0 = max(V_kt * KT / a["a"], 0.05)
    lim = {"pi_c_max": member["ref"]["pi_c"]} if hold_pi_c else {}
    return tc.full_throttle(member["ref"], M0, a["T"], a["p"], member["k"], **lim)["shaft_hp"]


def bsfc_at(member, h_ft, V_kt, shaft_hp):
    """Shaft SFC (lb/(hp h)) and turbine inlet temperature at a part-power point."""
    a = isa(h_ft)
    M0 = V_kt * KT / a["a"]
    r = tc.shaft_power_at(member["ref"], M0, a["T"], a["p"], shaft_hp, member["k"],
                          pi_c_max=member["ref"]["pi_c"])
    return r["bsfc"], r["Tt4"]

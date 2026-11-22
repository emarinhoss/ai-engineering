"""Info-gap robustness of the built Stage 1 design against R5 (8 h on station) and R7 (field length).
Spec docs/specs/task12_drone_conceptual_design.md sections 7.1a, 7.2, 7.4 (Gate B: horizon >= 1).

    python -m measurement.info_gap --design runs/task12/stage1/2026-11-21f/design_pusher.json \
        --out runs/task12/stage3/2026-11-22/info_gap.json \
        --report docs/validation/2026-11-22_task12_stage3_info_gap.md

Method: Ben-Haim's info-gap as used in Marchau et al., DMDU, ch. 10, (10.4)-(10.8), p. 212-218.
  Uncertain quantities theta_k: every ledger assumption with a band, plus two engine multipliers
  (SFC and full-throttle power of the TP100 table, nominal 1, weights 0.10 each side).
  U(h) (10.7): theta_k0 - h W_k_lower <= theta_k <= theta_k0 + h W_k_upper, with W chosen so that
  h = 1 gives the ledger band ends (W_lower = nominal - band_lo, W_upper = band_hi - nominal).
  Robustness (10.8): h_hat = largest h such that the requirement holds for every theta in U(h).

The aircraft is BUILT: wing area, aspect ratio, tail scale and fuel load are the record's. For a set
of uncertain values the Stage 1 state is rebuilt (uav._build, the same call as
measurement/stage3_perf.rebuild). Empty weight is uncertain (owner ruling, Eder 2026-11-22): the
take-off weight of the built aircraft is W0 = We(theta) + payload + the record's fuel, where We is
the component build-up of uav._build at theta. We depends weakly on W0 (some equations take W0), so
W0 is the fixed point of W0 = We(theta, W0) + payload + fuel. With weight banding off (--no-weight-band)
W0 stays the record's.

  R5: hours on station achievable with the record's fuel. The loiter time at which the rebuilt
      mission fuel equals the record's fuel. A mission that is not flyable gives 0 h.
  R7: take-off and landing distance over 50 ft, sea level ISA, each <= the ledger field length.
      The mission step of the rebuild is skipped (uav._build(..., mission=False)), so a corner
      where the mission cannot be flown fails R5 only.

Worst case over U(h) (review IG-1, IG-3): the function is not assumed monotone in any variable.
At every h tried by the bisection the worst case is searched for, per requirement:
  1. start at the one-at-a-time corner (each variable at its harmful end at h = 1);
  2. coordinate search: each variable in turn is set to whichever of {lower end, nominal, upper end}
     of its U(h) interval worsens the requirement most; sweeps repeat until no change worsens;
     then every pair among the 8 most influential variables and the two engine multipliers is
     flipped to each combination of ends (a cliff gives single flips no gradient: IG-1), and the
     sweeps repeat (at most 3 rounds);
  3. per-variable interior scan: 5 interior points of each interval from that point; any worsening
     is kept.
"Worse" means more fuel at the required loiter time for R5 (a mission that cannot be flown is
infinitely worse, i.e. 0 h) and a longer distance for R7. The requirement is met at h if the worst
point found still meets it. This is a search, not a proof: random sampling at each h_hat and at
h = 1 checks it. Nothing is tuned.
"""
# ruff: noqa: ISC004  (the report text is a list of adjacent string pieces, as in stage3_perf)
import argparse
import json
import math
import multiprocessing as mp
import platform
import re
import subprocess
import sys
import time
from itertools import combinations, product
from pathlib import Path

import numpy as np
import yaml

from conceptual import raymer_performance as perf
from conceptual import sizing, uav
from conceptual.engine_model import TableEngine, table_for_run
from conceptual.units import isa
from measurement import stage3_perf as sp

REPO = Path(__file__).resolve().parents[1]
LEDGER_NOW = REPO / "data" / "task12" / "ledger.yaml"
SEED = 20261122
N_SAMPLES = 200
N_CORNER_VARS = 5
N_INTERIOR = 5                # interior points per variable in the interior scan
N_PAIR_VARS = 8               # variables (most influential one at a time, plus the engine multipliers) whose
                              # ends are flipped two at a time
MAX_SWEEPS = 10
SEARCH_EPS = 1e-9             # a flip must worsen the score by more than this
H_MAX = 3.0
H_GATE = 1.0
ENGINE_WEIGHT = 0.10          # spec 7.1a engine tolerance: h = 1 means +-10 %
R5_HOURS = 8.0
R5_SLACK_H = 1e-4             # "met" means hours >= 8 - slack (bisection and interpolation noise)
LOITER_HI_H = 16.0            # upper end of the loiter bisection; fuel at 16 h exceeds the record
H_TOL = 2e-4                  # resolution of the bisection on h
H_GRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
ENGINE_VARS = ("engine_sfc_mult", "engine_power_mult")
W0_TOL_LB = 0.01              # weight fixed point: stop when W0 changes by less than this
W0_MAX_PASSES = 30
EXCLUSIONS = (
    "Headwind strength (R19, 25 kt fixed) and Oswald efficiency e are outside the horizon "
    "(Eder, 2026-11-22)",
    "ISA temperature deviation is not varied (sea level and 20,000 ft are ISA)",
    "The engine control law is not varied (the table's throttle schedule is taken as is)",
    "The shape of the part-power SFC curve is not varied (only a uniform multiplier on every table entry)",
    "Trim drag (downwash and tail height) is not modelled",
)
# messages of ValueError that mean "this member of U(h) cannot be flown"; any other ValueError is a
# bug or a bad input and is re-raised
UNFLYABLE = ("no speed on the leg within the engine's power", "cruise speed below the headwind",
             "does not close", "hp available", "no climb gradient after lift-off")


def unflyable_reason(exc):
    """The message of a ValueError that means 'cannot be flown'; re-raises any other ValueError.
    Call it inside an except block."""
    msg = str(exc)
    if any(p in msg for p in UNFLYABLE):
        return msg
    raise exc


def _ground_roll_reason(exc, what):
    """Within the take-off and landing calls only: a 'math domain error' is the ground-roll
    relation (17.99) having no solution (no acceleration, or no braking), i.e. the field length is
    infinite. Said so in the reason; every other message goes through unflyable_reason."""
    if "math domain error" in str(exc):
        return f"{what}ground roll (17.99) has no solution, field length unbounded (math domain error)"
    return unflyable_reason(exc)


def _reason_key(msg):
    return re.sub(r"[-+]?\d+(\.\d+)?", "#", msg)


# ---- the uncertainty model (10.7) ------------------------------------------------------------------
def uncertain_variables(entries):
    """List of {name, kind, nominal, band_lo, band_hi, w_lower, w_upper, clip_lo, clip_hi}.
    W_lower = nominal - band_lo and W_upper = band_hi - nominal, so h = 1 is the ledger band. The
    clip limits are the physical ranges: non-negative for everything with a non-negative band, and
    at most 1 for a dimensionless fraction or efficiency whose band lies in [0, 1]."""
    out = []
    for name, q in entries.items():
        if "band" not in q:
            continue
        lo, hi = map(float, q["band"])
        nom = float(q["value"])
        in_unit = q["units"] == "-" and lo >= 0.0 and hi <= 1.0
        out.append({"name": name, "kind": "ledger", "units": q["units"], "nominal": nom,
                    "band_lo": lo, "band_hi": hi, "w_lower": nom - lo, "w_upper": hi - nom,
                    "clip_lo": 0.0 if lo >= 0.0 else -math.inf,
                    "clip_hi": 1.0 if in_unit else math.inf})
    for name, what in (("engine_sfc_mult", "SFC of every TP100 table entry, on top of the 1.05 allowance"),
                       ("engine_power_mult", "full-throttle shaft power of the TP100 table")):
        out.append({"name": name, "kind": "engine", "units": what, "nominal": 1.0,
                    "band_lo": 1.0 - ENGINE_WEIGHT, "band_hi": 1.0 + ENGINE_WEIGHT,
                    "w_lower": ENGINE_WEIGHT, "w_upper": ENGINE_WEIGHT,
                    "clip_lo": 0.0, "clip_hi": math.inf})
    return out


def bounds(v, h):
    """Interval of variable v in U(h), (10.7), clipped to the physical range. Also returns
    whether each end was clipped."""
    lo = v["nominal"] - h * v["w_lower"]
    hi = v["nominal"] + h * v["w_upper"]
    c_lo, c_hi = max(lo, v["clip_lo"]), min(hi, v["clip_hi"])
    return c_lo, c_hi, c_lo != lo, c_hi != hi


def nominal_theta(variables):
    return {v["name"]: v["nominal"] for v in variables}


def corner_theta(variables, h, direction):
    """Every variable at its harmful end of U(h): direction -1 lower end, +1 upper end, 0 nominal."""
    th = nominal_theta(variables)
    for v in variables:
        lo, hi, _, _ = bounds(v, h)
        if direction[v["name"]] > 0:
            th[v["name"]] = hi
        elif direction[v["name"]] < 0:
            th[v["name"]] = lo
    return th


# ---- the built aircraft --------------------------------------------------------------------------
class Built:
    """The record, the ledger values and the engine table of the run; rebuild at any theta.
    band_weight False keeps W0 at the record's (the earlier study, kept for comparison)."""

    def __init__(self, design_path, band_weight=True):
        self.path = Path(design_path)
        self.band_weight = band_weight
        self.d, self.L, b, self.ledger_path, self.check = sp.rebuild(design_path)
        self.base_engine = TableEngine(table_for_run(self.path.parent))
        # the record's engine: rated power and weight (a photo-scaled TP100 if bhp is not 241)
        self.engine_scale = float(self.d.get("bhp_sl", sp.CHOSEN_ENGINE["bhp"])) / sp.CHOSEN_ENGINE["bhp"]
        self.engine_spec = {k: v for k, v in sp.record_engine(self.d, table_for_run(self.path.parent)).items()
                            if k != "model"}
        self.allowance = self.L.get("engine_sfc_allowance", 1.0)
        self.nominal_state = b
        self.S_record = self.d["W0_lb"] / self.d["W_S"]       # wing area is the record's

    # -- weight --
    def w0_for(self, theta):
        """Take-off weight of the built aircraft at theta: the fixed point of
        W0 = We(theta, W0) + payload + fuel (the record's fuel), wing area fixed. Raises a
        'does not close' ValueError if it does not converge."""
        if not self.band_weight:
            return self.d["W0_lb"]
        fixed = self.L["payload_lb"] if "payload_lb" not in theta else theta["payload_lb"]
        fixed += self.d["fuel_lb"]
        W = self.d["W0_lb"]
        for _ in range(W0_MAX_PASSES):
            We = self.build(theta, mission=False, W0=W)[0]["We"]
            if abs(We + fixed - W) < W0_TOL_LB:
                return We + fixed
            W = We + fixed
        raise ValueError(f"empty-weight fixed point does not close (W0 {W:.1f} lb after {W0_MAX_PASSES} passes)")

    def build(self, theta, loiter_h=None, mission=True, W0=None):
        """uav._build at W0 (default: the weight of theta, see w0_for) and the record's fuel with
        the ledger values in theta replaced and the engine table scaled: SFC by allowance x theta
        SFC multiplier (the 1.05 allowance stays, the multiplier is on top of it), power by the
        theta power multiplier. Wing area stays the record's (W_S = W0 / S)."""
        L = dict(self.L)
        L.update({k: v for k, v in theta.items() if k not in ENGINE_VARS})
        if loiter_h is not None:
            L["loiter_h"] = loiter_h
        model = (self.base_engine.scaled(power=self.engine_scale, rerate=True)      # the record's engine size
                 .scaled(sfc=self.allowance * theta.get("engine_sfc_mult", 1.0),
                         power=theta.get("engine_power_mult", 1.0)))                 # band end
        eng = dict(self.engine_spec, model=model)
        d = self.d
        if W0 is None:
            W0 = self.w0_for(theta)
        return uav._build(W0, d["concept"], W0 / self.S_record, d["A"], L, d["fuel_lb"], eng,
                          mission=mission), L

    # -- R5 --
    def fuel_at(self, theta, loiter_h, W0=None):
        """(mission fuel in lb at a loiter time, reason). Not flyable: (inf, the ValueError message)."""
        try:
            return self.build(theta, loiter_h, W0=W0)[0]["fuel"], None
        except ValueError as e:
            return math.inf, unflyable_reason(e)

    def hours_detail(self, theta, fuel_factor=1.0):
        """(hours, reason): loiter time (h) at which the mission fuel equals fuel_factor x the
        record's fuel, by bisection on loiter_h; the last bracket is closed by linear interpolation
        of the fuel (it is smooth in loiter time). 0 h with a reason if the mission is not flyable
        or already burns more than the target with no loiter."""
        target = fuel_factor * self.d["fuel_lb"]
        try:
            W0 = self.w0_for(theta)
        except ValueError as e:
            return 0.0, "mission not flyable: " + unflyable_reason(e)
        f_lo, reason = self.fuel_at(theta, 0.0, W0)
        if reason:
            return 0.0, "mission not flyable: " + reason
        if f_lo >= target:
            return 0.0, "the fuel burned before any loiter already exceeds the record's fuel"
        lo, hi, f_hi = 0.0, LOITER_HI_H, self.fuel_at(theta, LOITER_HI_H, W0)[0]
        if f_hi < target:
            return LOITER_HI_H, None         # capped; never reached for this design
        while hi - lo > 2e-3:
            mid = 0.5 * (lo + hi)
            f_mid = self.fuel_at(theta, mid, W0)[0]
            lo, f_lo, hi, f_hi = (mid, f_mid, hi, f_hi) if f_mid < target else (lo, f_lo, mid, f_mid)
        if not math.isfinite(f_hi):
            return lo, None
        return lo + (hi - lo) * (target - f_lo) / (f_hi - f_lo), None

    def hours_on_station(self, theta, fuel_factor=1.0):
        return self.hours_detail(theta, fuel_factor)[0]

    # -- R7 --
    def field_detail(self, theta, which=("TO", "LD")):
        """{'TO': (distance ft, reason), 'LD': ...} over 50 ft; (inf, reason) for a case the model
        cannot fly. Same two calls as uav.performance. The power multiplier scales the take-off
        shaft power (uav._takeoff uses the rated bhp directly, not the table)."""
        try:
            W0 = self.w0_for(theta)
            b, L = self.build(theta, mission=False, W0=W0)
        except ValueError as e:
            r = unflyable_reason(e)
            return {k: (math.inf, r) for k in which}
        S, K = b["geom"]["S"], b["K"]
        out = {}
        if "TO" in which:
            bhp = b["bhp"] * theta.get("engine_power_mult", 1.0)
            try:
                out["TO"] = (uav._takeoff(W0, S, b["CD0_takeoff"], K, b["clmax"]["takeoff"], L, bhp,
                                          b["D_prop"])["total"], None)
            except ValueError as e:
                out["TO"] = (math.inf, _ground_roll_reason(e, "take-off: thrust below rolling resistance, "))
        if "LD" in which:
            if L["braking_mu"] <= 0.0:       # (17.99) has no solution without braking: it never stops
                out["LD"] = (math.inf, "landing does not close: braking_mu <= 0, no braking force")
                return out
            try:
                out["LD"] = (perf.landing_distance(W0, S, isa(0.0)["rho"], b["CD0_landing"], K,
                                                   b["clmax"]["landing"], mu_brake=L["braking_mu"],
                                                   free_roll_s=L["free_roll_s"])["total"], None)
            except ValueError as e:
                out["LD"] = (math.inf, _ground_roll_reason(e, "landing: "))
        return out

    def field_lengths(self, theta):
        r = self.field_detail(theta)
        return r["TO"][0], r["LD"][0]


# ---- the worst-case search at one h (IG-1, IG-3) -----------------------------------------------------
def coordinate_search(score, variables, h, start, limit=None, n_interior=N_INTERIOR,
                      max_sweeps=MAX_SWEEPS, pair_names=()):
    """Search U(h) for the point with the largest score (score(theta) -> (value, reason); larger is
    worse, inf for a point that cannot be flown). 1. Start at `start`. 2. Coordinate search: take the
    variables in turn, set each to whichever of {lower end, nominal, upper end} gives the largest
    score, repeat sweeps until nothing changes. 2b. Pair flips: a cliff (a mission that stops being
    flyable) gives a one-variable flip no gradient, because each flip alone may look harmless while
    the two together cross it (review IG-1: low power and low SFC). So for every pair of `pair_names`
    both variables are set to each combination of their two ends and any worsening is kept; the
    coordinate search is then repeated (at most 3 rounds). 3. Interior scan: n_interior interior points of each
    variable's interval from the final point, keeping any worsening. If `limit` is given the search
    stops as soon as the score exceeds it (a violation is all the bisection needs).
    Returns the point, its score and reason, and the counts of evaluated and unflyable points."""
    stats = {"n_evals": 0, "n_unflyable": 0, "reasons": {}}

    def ev(th):
        val, reason = score(th)
        stats["n_evals"] += 1
        if math.isinf(val):
            stats["n_unflyable"] += 1
            ex = stats["reasons"].setdefault(_reason_key(reason or "inf"), {"example": reason, "count": 0})
            ex["count"] += 1
        return val, reason

    cur = dict(start)
    cur_val, cur_reason = ev(cur)

    def violated():
        return limit is not None and cur_val > limit

    by_name = {v["name"]: v for v in variables}
    sweeps = 0
    for _round in range(3 if pair_names else 1):
        for _ in range(max_sweeps):
            sweeps += 1
            changed = False
            for v in variables:
                if violated():
                    break
                lo, hi, _, _ = bounds(v, h)
                best = None
                for x in sorted({lo, v["nominal"], hi} - {cur[v["name"]]}):
                    val, reason = ev(dict(cur, **{v["name"]: x}))
                    if val > cur_val + SEARCH_EPS and (best is None or val > best[1]):
                        best = (x, val, reason)
                if best:
                    cur[v["name"]], cur_val, cur_reason = best
                    changed = True
            if not changed or violated():
                break
        paired = False
        for a, b in combinations(pair_names, 2):
            if violated():
                break
            ends = [sorted(set(bounds(by_name[n], h)[:2])) for n in (a, b)]
            for xa, xb in product(*ends):
                val, reason = ev(dict(cur, **{a: xa, b: xb}))
                if val > cur_val + SEARCH_EPS:
                    cur[a], cur[b], cur_val, cur_reason = xa, xb, val, reason
                    paired = True
        if not paired or violated():
            break
    if not violated():
        for v in variables:
            lo, hi, _, _ = bounds(v, h)
            for x in np.linspace(lo, hi, n_interior + 2)[1:-1]:
                val, reason = ev(dict(cur, **{v["name"]: float(x)}))
                if val > cur_val + SEARCH_EPS:
                    cur[v["name"]], cur_val, cur_reason = float(x), val, reason
                if violated():
                    break
            if violated():
                break
    return {"theta": cur, "value": cur_val, "reason": cur_reason, "sweeps": sweeps,
            "stopped_at_violation": violated(), **stats}


# ---- robustness by bisection on h (10.8) ----------------------------------------------------------
def robustness(met, h_max=H_MAX, tol=H_TOL):
    """Largest h in [0, h_max] with met(h) true, assuming met is true up to h_hat and false above
    (the worst case only gets worse as U(h) grows). Returns (h_hat, status): 'not met at h = 0',
    'above h_max' (h_hat = h_max) or 'bracketed'."""
    if not met(0.0):
        return 0.0, "not met at h = 0"
    if met(h_max):
        return h_max, "above h_max"
    lo, hi = 0.0, h_max
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if met(mid) else (lo, mid)
    if lo < tol:
        return lo, "zero margin: fails at the first step above h = 0"
    return lo, "bracketed"


# ---- one requirement: score, limit, study -----------------------------------------------------------
def make_score(built, spec, mode="limit"):
    """score(theta) -> (value, reason), larger = worse. R5 'limit': mission fuel at the required
    loiter time (met if <= the target fuel; inf if not flyable). R5 'hours': minus the hours on
    station (0 h if not flyable). R7: the distance."""
    if spec["req"] == "R5":
        if mode == "limit":
            return lambda th: built.fuel_at(th, spec["need"] - R5_SLACK_H)
        def hours_score(th):
            hrs, reason = built.hours_detail(th, spec["fuel_factor"])
            return -hrs, reason
        return hours_score
    return lambda th: built.field_detail(th, (spec["req"],))[spec["req"]]


def limit_of(built, spec):
    if spec["req"] == "R5":
        return spec["fuel_factor"] * built.d["fuel_lb"]
    return built.L["field_length_ft"]


def describe(built, spec, variables, res, h):
    """Record of a worst point: the values that moved off nominal, the outputs there, how many
    points the search found unflyable and why."""
    th = res["theta"]
    nom = nominal_theta(variables)
    out = {"h": h, "moved": {k: v for k, v in th.items() if v != nom[k]},
           "n_evals": res["n_evals"], "n_unflyable": res["n_unflyable"], "unflyable_reasons": res["reasons"],
           "sweeps": res["sweeps"]}
    if spec["req"] == "R5":
        hrs, reason = built.hours_detail(th, spec["fuel_factor"])
        out["hours"], out["not_flyable"] = hrs, reason
    else:
        to, ld = built.field_lengths(th)
        out["takeoff_ft"], out["landing_ft"] = to, ld
        out["not_flyable"] = res["reason"] if math.isinf(res["value"]) else None
    return out


def sampling_check(score, variables, top_names, h, n_samples, seed, search_value):
    """Random points of U(h) and the corners of the top variables (others at nominal); compare with
    the value the search found. 'beat' means a point is worse than the search's worst point."""
    nom = nominal_theta(variables)
    rng = np.random.default_rng(seed)
    pts = []
    for _ in range(n_samples):
        pts.append(("random", {v["name"]: bounds(v, h)[0] + rng.random() * (bounds(v, h)[1] - bounds(v, h)[0])
                               for v in variables}))
    for signs in product((0, 1), repeat=len(top_names)):
        th = dict(nom)
        for nm, s in zip(top_names, signs):
            v = next(x for x in variables if x["name"] == nm)
            th[nm] = bounds(v, h)[1 if s else 0]
        pts.append((f"corner of top {len(top_names)}", th))
    vals = [(score(th)[0], kind) for kind, th in pts]
    worst_val, worst_kind = max(vals, key=lambda t: t[0])
    beat = [v for v, _ in vals if v > search_value + 1e-6]
    return {"h": h, "seed": seed, "n_random": n_samples, "n_corner_points": len(pts) - n_samples,
            "search_value": search_value, "worst_sampled": worst_val, "worst_sampled_kind": worst_kind,
            "worst_random": max(v for v, k in vals if k == "random"),
            "n_beating_search": len(beat), "most_beating": max(beat) if beat else None}


def requirement_study(built, spec, variables, dirs, top_names, pair_names, n_samples, seed):
    """h_hat of one requirement by bisection with the worst-case search at every h, then at h_hat
    (and at the lowest h that failed) the full search with the worst point recorded, and the random
    sampling check at h_hat and at h = 1."""
    score, limit = make_score(built, spec), limit_of(built, spec)
    start_dir = dirs[spec["req"]]
    failed = []

    def search(h, early):
        return coordinate_search(score, variables, h, corner_theta(variables, h, start_dir),
                                 limit if early else None, pair_names=pair_names)

    def met(h):
        ok = search(h, True)["value"] <= limit
        if not ok:
            failed.append(h)
        return ok

    h_hat, status = robustness(met)
    out = {"h_hat": h_hat, "status": status, "limit": limit}
    full = search(h_hat, False)
    out["worst_at_h_hat"] = describe(built, spec, variables, full, h_hat)
    if failed:
        h_fail = min(failed)
        out["first_failing_h"] = h_fail
        out["worst_at_first_failing_h"] = describe(built, spec, variables, search(h_fail, False), h_fail)
    out["sampling"] = []
    for i, h in enumerate(sorted({h_hat, H_GATE} - {0.0})):
        val = full["value"] if h == h_hat else search(h, False)["value"]
        out["sampling"].append(sampling_check(score, variables, top_names, h, n_samples, seed + i, val))
    return out


# ---- evaluation of one point (works in a worker process) --------------------------------------------
_BUILT = None


def _init(design_path, band_weight=True):
    global _BUILT
    _BUILT = Built(design_path, band_weight)


def evaluate(theta):
    """(hours, takeoff_ft, landing_ft) at theta."""
    to, ld = _BUILT.field_lengths(theta)
    return _BUILT.hours_on_station(theta), to, ld


def _job(args):
    kind = args[0]
    if kind == "eval":
        return evaluate(args[1])
    if kind == "req":
        return requirement_study(_BUILT, *args[1:])
    # kind == "curve": the worst case at one h, scored by hours for R5
    spec, variables, dirs, pair_names, h = args[1:]
    score = make_score(_BUILT, spec, "hours")
    res = coordinate_search(score, variables, h, corner_theta(variables, h, dirs[spec["req"]]),
                            pair_names=pair_names)
    d = describe(_BUILT, spec, variables, res, h)
    return d


# ---- the study -----------------------------------------------------------------------------------
def harm_direction(nominal, lo_val, hi_val, bad_is_low):
    """-1 if the lower end of the variable is harmful, +1 if the upper end, 0 if neither end is
    worse than nominal. Harmful means a lower value for hours (bad_is_low) or a larger distance."""
    sgn = 1.0 if bad_is_low else -1.0               # make "harm" a decrease
    d_lo, d_hi = sgn * (lo_val - nominal), sgn * (hi_val - nominal)
    if min(d_lo, d_hi) >= -1e-9:
        return 0
    return -1 if d_lo < d_hi else 1


def one_at_a_time(pool, variables, h=1.0):
    nom = nominal_theta(variables)
    jobs = [("eval", nom)]
    for v in variables:
        lo, hi, _, _ = bounds(v, h)
        jobs += [("eval", dict(nom, **{v["name"]: lo})), ("eval", dict(nom, **{v["name"]: hi}))]
    res = pool.map(_job, jobs, chunksize=1)
    nominal, rows = res[0], []
    for i, v in enumerate(variables):
        lo_r, hi_r = res[1 + 2 * i], res[2 + 2 * i]
        lo, hi, c_lo, c_hi = bounds(v, h)
        row = {"name": v["name"], "kind": v["kind"], "nominal": v["nominal"], "value_at_lower": lo,
               "value_at_upper": hi, "clipped_lower": c_lo, "clipped_upper": c_hi,
               "inert": all(abs(r[k] - nominal[k]) <= 1e-9 for r in (lo_r, hi_r) for k in range(3))}
        for key, idx, bad_low in (("R5_hours", 0, True), ("takeoff_ft", 1, False),
                                  ("landing_ft", 2, False)):
            row[key] = {"at_lower": lo_r[idx], "at_upper": hi_r[idx],
                        "direction": harm_direction(nominal[idx], lo_r[idx], hi_r[idx], bad_low)}
            worst = (min if bad_low else max)(lo_r[idx], hi_r[idx], nominal[idx])
            row[key]["effect"] = worst - nominal[idx]           # signed change at the harmful end
        rows.append(row)
    return {"h": h, "nominal": {"R5_hours": nominal[0], "takeoff_ft": nominal[1],
                                "landing_ft": nominal[2]}, "rows": rows}


def directions(oat):
    keys = {"R5": "R5_hours", "TO": "takeoff_ft", "LD": "landing_ft"}
    return {req: {r["name"]: r[key]["direction"] for r in oat["rows"]} for req, key in keys.items()}


def top_variables(oat, key, n=N_CORNER_VARS):
    rows = sorted(oat["rows"], key=lambda r: -abs(r[key]["effect"]))
    return [r["name"] for r in rows[:n] if r[key]["effect"] != 0.0]


def pair_list(oat, key, n=N_PAIR_VARS):
    """Variables whose ends are flipped in pairs: the n most influential one at a time, plus the
    two engine multipliers."""
    return list(dict.fromkeys(top_variables(oat, key, n) + list(ENGINE_VARS)))


def clipping_report(variables, h):
    return [{"name": v["name"], "h": h, "lower_clipped": bounds(v, h)[2], "upper_clipped": bounds(v, h)[3],
            "lower_end": bounds(v, h)[0], "upper_end": bounds(v, h)[1]}
            for v in variables if bounds(v, h)[2] or bounds(v, h)[3]]


def study(design_path, n_samples=N_SAMPLES, seed=SEED, processes=None, band_weight=True):
    t0 = time.time()
    built = Built(design_path, band_weight)
    _, entries = uav.load_ledger(built.ledger_path)
    variables = uncertain_variables(entries)
    nom_th = nominal_theta(variables)
    ctx = mp.get_context("fork")
    with ctx.Pool(processes, initializer=_init, initargs=(design_path, band_weight)) as pool:
        _init(design_path, band_weight)
        nom = evaluate(nom_th)
        w0 = built.w0_for(nom_th)
        res = {"band_weight": band_weight,
               "nominal": {"R5_hours": nom[0], "takeoff_ft": nom[1], "landing_ft": nom[2]},
               "record": {"fuel_lb": built.d["fuel_lb"], "W0_lb": built.d["W0_lb"],
                          "takeoff_ft": built.d["performance"]["takeoff_ft"],
                          "landing_ft": built.d["performance"]["landing_ft"]},
               "w0_check": {"record_lb": built.d["W0_lb"], "fixed_point_lb": w0,
                            "difference_lb": w0 - built.d["W0_lb"],
                            "within_0.1_lb": abs(w0 - built.d["W0_lb"]) <= 0.1},
               "rebuild_check": built.check, "variables": variables}
        oat = one_at_a_time(pool, variables, H_GATE)
        dirs = directions(oat)
        res["one_at_a_time"], res["directions"] = oat, dirs
        inert = [r["name"] for r in oat["rows"] if r["inert"]]
        res["inert_variables"] = inert
        res["n_variables"], res["n_act"] = len(variables), len(variables) - len(inert)
        # R5 as restated at Gate B (Eder 2026-11-22): 8 h nominal, and at least the ledger's
        # robust endurance (3.5 h) for every member of U(h); Gate B needs h_hat >= 1 for this.
        # The record's ledger copy predates the ruling, so the current ledger supplies it.
        guarantee = built.L.get("r5_robust_hours") or uav.load_ledger(LEDGER_NOW)[0].get("r5_robust_hours")
        specs = {"R5": {"req": "R5", "need": R5_HOURS, "fuel_factor": 1.0},
                 "TO": {"req": "TO"}, "LD": {"req": "LD"},
                 "R5_reserve_usable": {"req": "R5", "need": R5_HOURS, "fuel_factor": sizing.RESERVE_FACTOR}}
        if guarantee:
            specs["R5_guarantee"] = {"req": "R5", "need": guarantee, "fuel_factor": 1.0}
        top_key = {"R5": "R5_hours", "TO": "takeoff_ft", "LD": "landing_ft"}
        names = list(specs)
        req_jobs = [("req", specs[n], variables, dirs, top_variables(oat, top_key[specs[n]["req"]]),
                     pair_list(oat, top_key[specs[n]["req"]]), n_samples, seed + 10 * i) for i, n in enumerate(names)]
        curve_jobs = [("curve", {"req": r, "need": R5_HOURS, "fuel_factor": 1.0}, variables, dirs,
                       pair_list(oat, top_key[r]), h)
                      for h in H_GRID for r in ("R5", "TO", "LD")]
        out = pool.map(_job, req_jobs + curve_jobs, chunksize=1)
        res["h_hat"] = {}
        for n, r in zip(names, out[:len(names)]):
            res["h_hat"][n] = r
            if "need" in specs[n]:
                res["h_hat"][n]["hours"] = specs[n]["need"]
        res["h_hat"]["R7"] = {"h_hat": min(res["h_hat"]["TO"]["h_hat"], res["h_hat"]["LD"]["h_hat"]),
                              "status": "min of take-off and landing"}
        curve = out[len(names):]
        res["worst_case_curve"] = [{"h": h, "R5": curve[3 * i], "TO": curve[3 * i + 1], "LD": curve[3 * i + 2]}
                                   for i, h in enumerate(H_GRID)]
        res["clipping"] = {"at_h_1": clipping_report(variables, 1.0),
                           "at_h_max": clipping_report(variables, H_MAX)}
    res["exclusions"] = list(EXCLUSIONS)
    res["runtime_s"] = time.time() - t0
    return res


# ---- record and report ----------------------------------------------------------------------------
def git_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
                          cwd=REPO).stdout.strip()


def git_dirty():
    """Lines of `git status --porcelain` for the code and data this study depends on."""
    out = subprocess.run(["git", "status", "--porcelain", "--", "conceptual", "measurement", "data"],
                         capture_output=True, text=True, check=False, cwd=REPO).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def _json_safe(x):
    if isinstance(x, float) and not math.isfinite(x):
        return str(x)
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    return x


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--samples", type=int, default=N_SAMPLES)
    ap.add_argument("--no-weight-band", action="store_true",
                    help="keep W0 at the record's (no empty-weight uncertainty), as before the review")
    a = ap.parse_args(argv)
    res = study(a.design, a.samples, band_weight=not a.no_weight_band)
    ledger = Path(a.design).parent / "ledger.yaml"
    table = table_for_run(Path(a.design).parent)
    dirty = git_dirty()
    res["inputs"] = {
        "design": a.design, "design_sha256": sp.sha256(a.design),
        "ledger": str(ledger), "ledger_sha256": sp.sha256(ledger),
        "engine_table": str(table), "engine_table_sha256": sp.sha256(table),
        "current_ledger": str(LEDGER_NOW), "current_ledger_sha256": sp.sha256(LEDGER_NOW),
        "current_ledger_is_source_of": "r5_robust_hours",
        "git_commit": git_commit(), "git_dirty": bool(dirty), "git_dirty_files": dirty,
        "python": platform.python_version(), "numpy": np.__version__,
        "pyyaml": yaml.__version__, "seed": SEED, "n_random_samples": a.samples,
        "n_corner_variables": N_CORNER_VARS, "n_interior_points": N_INTERIOR, "h_max": H_MAX,
        "h_gate": H_GATE, "engine_weight": ENGINE_WEIGHT, "r5_slack_h": R5_SLACK_H, "h_tolerance": H_TOL,
        "weight_band": not a.no_weight_band, "cpu_count": mp.cpu_count(),
        "command": "python -m measurement.info_gap " + " ".join(argv if argv is not None else sys.argv[1:])}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(_json_safe(res), indent=2, default=float))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report_text(json.loads(Path(a.out).read_text())))
    for k, v in res["h_hat"].items():
        print(k, v["h_hat"], v["status"])
    print(f"runtime {res['runtime_s']:.0f} s")


def _worst_point_lines(label, w, g, oat, key):
    """Report lines for one recorded worst point."""
    if w is None:
        return []
    top = [r["name"] for r in sorted(oat["rows"], key=lambda r: -abs(r[key]["effect"]))[:10]]
    moved = w["moved"]
    show = [n for n in moved if n in top or n in ENGINE_VARS]
    if "hours" in w:
        outcome = f"{g(w['hours'], '.3f')} h on station"
    else:
        outcome = f"take-off {g(w['takeoff_ft'], '.1f')} ft, landing {g(w['landing_ft'], '.1f')} ft"
    L = [f"- {label} (h = {g(w['h'], '.4f')}): {outcome}; {len(moved)} variables off nominal; "
         f"{w['n_unflyable']} of {w['n_evals']} points searched not flyable."]
    if w["not_flyable"]:
        nf = str(w["not_flyable"])
        L.append("  - " + (nf if nf.startswith(("mission", "the fuel")) else "mission not flyable: " + nf))
    for r in w["unflyable_reasons"].values():
        L.append(f"  - {r['count']} points: {r['example']}")
    if show:
        L.append("  - key values: " + ", ".join(f"{n} = {g(moved[n])}" for n in show))
    return L


def report_text(res):
    """Markdown report from the JSON record (no number is typed here)."""
    inp, nom, hh = res["inputs"], res["nominal"], res["h_hat"]
    rec, oat = res["record"], res["one_at_a_time"]

    def g(x, f=".4g"):
        return x if isinstance(x, str) else format(x, f)

    def hrow(name, key):
        h = hh[key]
        return f"| {name} | {g(h['h_hat'], '.4f')} | {h['status']} | {'yes' if h['h_hat'] >= 1 else 'no'} |"

    banded = res["band_weight"]
    L = ["# Task 12 Stage 3: info-gap robustness of the built design (R5, R7)", "",
         f"Generated from `{inp['design']}` by `python -m measurement.info_gap`; the numbers below are "
         "read from the run record `info_gap.json` (inputs, versions, seed there).", "",
         "## Method", "",
         "Ben-Haim's info-gap as in Marchau et al., DMDU, ch. 10. Uncertainty model (10.7), p. 213: "
         "theta_k in [theta_k0 - h W_k_lower, theta_k0 + h W_k_upper], weights W set so that h = 1 gives "
         "the ledger band ends (W_lower = nominal - band_lo, W_upper = band_hi - nominal; one-sided where "
         "the nominal is a band end). Robustness (10.8), p. 214: h_hat is the largest h at which the "
         "worst case over U(h) still meets the requirement, found by bisection on h in [0, "
         f"{g(inp['h_max'])}]. Uncertain quantities: {res['n_variables']}, the ledger assumptions that "
         "carry a band plus two engine multipliers (SFC and full-throttle power of the TP100 table, "
         f"+-{g(inp['engine_weight'] * 100)} % at h = 1). The SFC multiplier is applied on top of the "
         "ledger's 1.05 SFC allowance (`engine_sfc_allowance`), which stays in.", "",
         f"**{res['n_act']} of {res['n_variables']} uncertain quantities act** on R5 or R7; "
         f"{len(res['inert_variables'])} have exactly zero effect on every output at their band ends "
         "and are excluded from the headline count (listed below).", "",
         "**Worst case search** (review IG-1, IG-3, DMDU p. 214-218 on global search for the inner "
         "maximum). The worst case over U(h) is not assumed to sit at a fixed corner. At every h the "
         "bisection tries, per requirement: (1) start at the one-at-a-time corner (each variable at its "
         "harmful end at h = 1); (2) coordinate search over ALL variables, each set in turn to whichever of "
         "{lower end, nominal, upper end} of its U(h) interval worsens the requirement most, sweeps repeated "
         "until no flip worsens, then pair flips of the ends of the most influential variables and the two "
         "engine multipliers (a mission that stops being flyable is a cliff that single flips cannot see; "
         f"review IG-1), repeated at most 3 rounds; (3) an interior scan of {inp['n_interior_points']} points per variable from "
         "that point, keeping any worsening. A mission that cannot be flown counts as 0 h, the worst "
         "possible. This is a search, not a proof; random sampling below checks it.", "",
         "The aircraft is built: wing area, aspect ratio, tail scale and fuel load are the record's. ",
         ]
    if banded:
        L[-1] += ("Empty weight is uncertain (owner ruling, Eder 2026-11-22): the take-off weight is "
                  "W0 = We(theta) + payload + the record's fuel, with We the component build-up at theta, "
                  "iterated to a fixed point because some weight equations take W0. At nominal theta the "
                  f"fixed point gives W0 = {g(res['w0_check']['fixed_point_lb'], '.3f')} lb against the "
                  f"record's {g(res['w0_check']['record_lb'], '.3f')} lb (difference "
                  f"{g(res['w0_check']['difference_lb'], '+.4f')} lb; within 0.1 lb: "
                  f"{'yes' if res['w0_check']['within_0.1_lb'] else 'NO'}).")
    else:
        L[-1] += ("**Weight banding is OFF for this run** (`--no-weight-band`): W0 stays the record's, so "
                  "weight items do not act. This is the pre-review model, kept to compare with the reviewer.")
    L += ["", "R5: hours on station with the record's fuel, the loiter time at which the rebuilt mission fuel "
          "(including the 6 % reserve factor) equals the record's fuel. R7: take-off and landing distance "
          "over 50 ft against the ledger field length. The engine power multiplier scales the take-off "
          "shaft power as well as the table's lapse.", "",
          "## Exclusions (not in the horizon)", ""]
    L += [f"- {e}" for e in res["exclusions"]]
    L += ["", "A 0 h point below is a mission that cannot be flown (the transit at 20,000 ft needs more "
          "power than the engine gives at that member of U(h)); the reason string is the model's.", "",
          "## Nominal (h = 0)", "",
          "| Quantity | Record | Rebuilt here |", "|---|---|---|",
          f"| Hours on station | 8 (requirement; the record's fuel was sized for it) | {g(nom['R5_hours'], '.4f')} |",
          f"| Take-off over 50 ft (ft) | {g(rec['takeoff_ft'], '.2f')} | {g(nom['takeoff_ft'], '.2f')} |",
          f"| Landing over 50 ft (ft) | {g(rec['landing_ft'], '.2f')} | {g(nom['landing_ft'], '.2f')} |", "",
          "## Robustness against the Gate B threshold (h = 1)", "",
          "| Requirement | h_hat | Status | Meets Gate B (>= 1) |", "|---|---|---|---|",
          hrow("R5, 8 h on station (nominal requirement; zero robustness by construction)", "R5"),
          *([hrow(f"R5 as restated at Gate B: at least {g(hh['R5_guarantee']['hours'])} h on station",
                  "R5_guarantee")] if "R5_guarantee" in hh else []),
          hrow("R7 take-off", "TO"), hrow("R7 landing", "LD"), hrow("R7 combined (min)", "R7"), "",
          "Secondary, not the requirement: R5 if the 6 % reserve could be burned as well (target fuel = "
          f"{g(sizing.RESERVE_FACTOR)} x the record's): h_hat = {g(hh['R5_reserve_usable']['h_hat'], '.4f')} "
          f"({hh['R5_reserve_usable']['status']}). Reported to show how far the design is from the "
          "threshold, not as a pass.", "",
          "## Worst points found", ""]
    for name, key, label in (("R5_guarantee", "R5_hours", "R5 guarantee"), ("R5", "R5_hours", "R5 8 h"),
                             ("TO", "takeoff_ft", "R7 take-off"), ("LD", "landing_ft", "R7 landing")):
        if name not in hh:
            continue
        r = hh[name]
        L += [f"### {label}", ""]
        L += _worst_point_lines("worst point at h_hat", r["worst_at_h_hat"], g, oat, key)
        if "worst_at_first_failing_h" in r:
            L += _worst_point_lines("worst point at the lowest failing h", r["worst_at_first_failing_h"],
                                    g, oat, key)
        L.append("")
    L += ["## Worst case against h", "",
          "| h | Hours on station | Take-off (ft) | Landing (ft) | Why 0 h |", "|---|---|---|---|---|"]
    for r in res["worst_case_curve"]:
        why = r["R5"]["not_flyable"] or ""
        L.append(f"| {g(r['h'])} | {g(r['R5']['hours'], '.3f')} | {g(r['TO']['takeoff_ft'], '.1f')} | "
                 f"{g(r['LD']['landing_ft'], '.1f')} | {why} |")
    L += ["", "## What drives each requirement (one at a time at h = 1)", "",
          "Effect = change at the harmful end of the variable's band from the nominal value, others at "
          "nominal. Direction -1 means the lower band end is harmful, +1 the upper end, 0 neither. The "
          "search starts from the corner that takes every variable at its harmful end and then flips "
          "variables where that is worse (interactions).", ""]
    for key, label, unit in (("R5_hours", "R5 hours on station", "h"), ("takeoff_ft", "R7 take-off", "ft"),
                             ("landing_ft", "R7 landing", "ft")):
        rows = sorted(oat["rows"], key=lambda r: -abs(r[key]["effect"]))
        L += [f"### {label}", "", f"| Variable | Nominal | Lower end | Upper end | Harmful end | Effect ({unit}) |",
              "|---|---|---|---|---|---|"]
        for r in rows[:10]:
            if r[key]["effect"] == 0.0:
                break
            L.append(f"| {r['name']} | {g(r['nominal'])} | {g(r['value_at_lower'])} | {g(r['value_at_upper'])} | "
                     f"{r[key]['direction']:+d} | {g(r[key]['effect'], '+.4g')} |")
        n_zero = sum(r[key]["effect"] == 0.0 for r in rows)
        L += ["", f"{n_zero} of {len(rows)} variables have no harmful effect on this requirement "
              "(not shown; all are in the JSON).", ""]
    L += ["## Inert variables", "",
          f"{len(res['inert_variables'])} of {res['n_variables']} have exactly zero effect on hours, "
          "take-off and landing at both band ends (h = 1): "
          + (", ".join(f"`{n}`" for n in res["inert_variables"]) or "none") + ".", "",
          "## Check of the search by sampling", "",
          f"Seed {inp['seed']}, {inp['n_random_samples']} points uniform in U(h) plus the corners of the "
          f"{inp['n_corner_variables']} most influential variables of each requirement (others at nominal), "
          "at each requirement's h_hat and at h = 1. Values are the search score: mission fuel at the "
          "required loiter time (lb; inf = not flyable) for R5, distance (ft) for R7. 'Worse than the "
          "search' counts sampled points that beat the search's worst point.", "",
          "| Requirement | h | Search worst | Worst sampled | Worst random | Points worse than the search |",
          "|---|---|---|---|---|---|"]
    for name in ("R5", "R5_guarantee", "R5_reserve_usable", "TO", "LD"):
        for s in hh.get(name, {}).get("sampling", []):
            L.append(f"| {name} | {g(s['h'], '.4f')} | {g(s['search_value'], '.4f')} | "
                     f"{g(s['worst_sampled'], '.4f')} ({s['worst_sampled_kind']}) | "
                     f"{g(s['worst_random'], '.4f')} | {s['n_beating_search']} |")
    cl = res["clipping"]
    L += ["", "## Clipping", "",
          f"At h = 1: {len(cl['at_h_1'])} variables clipped"
          + (": " + ", ".join(c["name"] for c in cl["at_h_1"]) if cl["at_h_1"] else "") + ". "
          f"At h = {g(inp['h_max'])}: {len(cl['at_h_max'])}"
          + (": " + ", ".join(f"{c['name']} (" + ("lower" if c["lower_clipped"] else "") +
                              ("/" if c["lower_clipped"] and c["upper_clipped"] else "") +
                              ("upper" if c["upper_clipped"] else "") + ")" for c in cl["at_h_max"]) if cl["at_h_max"] else "")
          + ". Limits: non-negative, and at most 1 for a dimensionless fraction or efficiency.", "",
          "## Record", "",
          f"Design sha256 `{inp['design_sha256'][:16]}...`, run ledger sha256 `{inp['ledger_sha256'][:16]}...`, "
          f"engine table sha256 `{inp['engine_table_sha256'][:16]}...`, current ledger "
          f"(`{inp['current_ledger']}`, source of `r5_robust_hours`) sha256 `{inp['current_ledger_sha256'][:16]}...`, "
          f"git commit `{inp['git_commit']}`, working tree "
          f"{'DIRTY (' + str(len(inp['git_dirty_files'])) + ' files in conceptual, measurement, data)' if inp['git_dirty'] else 'clean'}, "
          f"Python {inp['python']}, numpy {inp['numpy']}, {inp['cpu_count']} CPUs, runtime "
          f"{g(res['runtime_s'], '.0f')} s.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())

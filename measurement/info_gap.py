"""Info-gap robustness of the built Stage 1 design against R5 (8 h on station) and R7 (field length).
Spec docs/specs/task12_drone_conceptual_design.md sections 7.1a, 7.2, 7.4 (Gate B: horizon >= 1).

    python -m measurement.info_gap --design runs/task12/stage1/2026-11-21f/design_pusher.json \
        --out runs/task12/stage3/2026-11-22/info_gap.json \
        --report docs/validation/2026-11-22_task12_stage3_info_gap.md

Method: Ben-Haim's info-gap as used in Marchau et al., DMDU, ch. 10, (10.4)-(10.8), p. 212-214.
  Uncertain quantities theta_k: every ledger assumption with a band, plus two engine multipliers
  (SFC and full-throttle power of the TP100 table, nominal 1, weights 0.10 each side).
  U(h) (10.7): theta_k0 - h W_k_lower <= theta_k <= theta_k0 + h W_k_upper, with W chosen so that
  h = 1 gives the ledger band ends (W_lower = nominal - band_lo, W_upper = band_hi - nominal).
  Robustness (10.8): h_hat = largest h such that the requirement holds for every theta in U(h).

The aircraft is BUILT: W0, wing loading, aspect ratio, tail scale and fuel load are the record's
and are not re-sized. For a set of uncertain values the Stage 1 state is rebuilt at the record's W0
and fuel (uav._build, the same call as measurement/stage3_perf.rebuild) with those values.

  R5: hours on station achievable with the record's fuel. The loiter time at which the rebuilt
      mission fuel equals the record's fuel, by bisection on loiter_h. A mission that is not
      flyable (ValueError) gives 0 h.
  R7: take-off and landing distance over 50 ft, sea level ISA, each <= the ledger field length.
      These are the two calls inside uav.performance (uav._takeoff, perf.landing_distance); the
      ceiling and speed parts of uav.performance are not needed and are slow. The mission step
      of the rebuild is skipped for R7 (the fuel load stays the record's), so a corner where the
      mission cannot be flown fails R5 only.

Worst case over U(h): the function is not assumed monotone in each variable. (1) one-at-a-time at
h = 1 gives each variable's direction of harm per requirement; (2) the "monotone worst corner" puts
every variable at its harmful end of U(h); (3) random points of U(h) and the corners of the five
most influential variables check that nothing beats the corner. Nothing is tuned.
"""
# ruff: noqa: ISC004  (the report text is a list of adjacent string pieces, as in stage3_perf)
import argparse
import json
import math
import multiprocessing as mp
import platform
import subprocess
import sys
import time
from itertools import product
from pathlib import Path
from unittest import mock

import numpy as np
import yaml

from conceptual import raymer_performance as perf
from conceptual import sizing, uav
from conceptual.engine_model import TableEngine, table_for_run
from conceptual.units import isa
from measurement import stage3_perf as sp

REPO = Path(__file__).resolve().parents[1]
SEED = 20261122
N_SAMPLES = 200
N_CORNER_VARS = 5
H_MAX = 3.0
H_GATE = 1.0
ENGINE_WEIGHT = 0.10          # spec 7.1a engine tolerance: h = 1 means +-10 %
R5_HOURS = 8.0
R5_SLACK_H = 1e-4             # "met" means hours >= 8 - slack (bisection and interpolation noise)
LOITER_HI_H = 16.0            # upper end of the loiter bisection; fuel at 16 h exceeds the record
H_TOL = 2e-4                  # resolution of the bisection on h
H_GRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
ENGINE_VARS = ("engine_sfc_mult", "engine_power_mult")


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
    """The record, the ledger values and the engine table of the run; rebuild at any theta."""

    def __init__(self, design_path):
        self.path = Path(design_path)
        self.d, self.L, b, self.ledger_path, self.check = sp.rebuild(design_path)
        self.base_engine = TableEngine(table_for_run(self.path.parent))
        self.allowance = self.L.get("engine_sfc_allowance", 1.0)
        self.nominal_state = b

    def build(self, theta, loiter_h=None, mission=True):
        """uav._build at the record's W0 and fuel with the ledger values in theta replaced and the
        engine table scaled: SFC by allowance x theta SFC multiplier (the 1.05 allowance stays, the
        multiplier is on top of it), power by theta power multiplier."""
        L = dict(self.L)
        L.update({k: v for k, v in theta.items() if k not in ENGINE_VARS})
        if loiter_h is not None:
            L["loiter_h"] = loiter_h
        model = self.base_engine.scaled(sfc=self.allowance * theta.get("engine_sfc_mult", 1.0),
                                        power=theta.get("engine_power_mult", 1.0))
        eng = dict(sp.CHOSEN_ENGINE, model=model)
        d = self.d
        if mission:
            return uav._build(d["W0_lb"], d["concept"], d["W_S"], d["A"], L, d["fuel_lb"], eng), L
        # R7 does not need the mission: a corner where the mission cannot be flown (R5 fails
        # there) must not make the field length unevaluable, so the mission step is skipped
        with mock.patch.object(uav, "_mission", lambda *a, **k: (d["fuel_lb"], [])):
            return uav._build(d["W0_lb"], d["concept"], d["W_S"], d["A"], L, d["fuel_lb"], eng), L

    def fuel_for_loiter(self, theta, loiter_h):
        try:
            return self.build(theta, loiter_h)[0]["fuel"]
        except ValueError:
            return math.inf

    def hours_on_station(self, theta, fuel_factor=1.0):
        """Loiter time (h) at which the mission fuel equals fuel_factor x the record's fuel, by
        bisection on loiter_h; the last bracket is closed by linear interpolation of the fuel (it
        is smooth in loiter time), so the result is good to far better than the bisection step.
        0 if the mission is not flyable or already burns more than the target with no loiter."""
        target = fuel_factor * self.d["fuel_lb"]
        f_lo = self.fuel_for_loiter(theta, 0.0)
        if f_lo >= target:                   # includes a ValueError (inf): not flyable
            return 0.0
        lo, hi, f_hi = 0.0, LOITER_HI_H, self.fuel_for_loiter(theta, LOITER_HI_H)
        if f_hi < target:
            return LOITER_HI_H               # capped; never reached for this design
        while hi - lo > 2e-3:
            mid = 0.5 * (lo + hi)
            f_mid = self.fuel_for_loiter(theta, mid)
            lo, f_lo, hi, f_hi = (mid, f_mid, hi, f_hi) if f_mid < target else (lo, f_lo, mid, f_mid)
        if not math.isfinite(f_hi):
            return lo
        return lo + (hi - lo) * (target - f_lo) / (f_hi - f_lo)

    def field_lengths(self, theta):
        """(take-off, landing) distance over 50 ft in ft; inf for a case the model cannot fly.
        Same two calls as uav.performance. The power multiplier scales the take-off shaft power
        (uav._takeoff uses the rated bhp directly, not the table)."""
        try:
            b, L = self.build(theta, mission=False)
        except ValueError:
            return math.inf, math.inf
        W0, S, K = self.d["W0_lb"], b["geom"]["S"], b["K"]
        bhp = b["bhp"] * theta.get("engine_power_mult", 1.0)
        try:
            to = uav._takeoff(W0, S, b["CD0_takeoff"], K, b["clmax"]["takeoff"], L, bhp,
                              b["D_prop"])["total"]
        except ValueError:
            to = math.inf
        try:
            ld = perf.landing_distance(W0, S, isa(0.0)["rho"], b["CD0_landing"], K, b["clmax"]["landing"],
                                       mu_brake=L["braking_mu"], free_roll_s=L["free_roll_s"])["total"]
        except ValueError:
            ld = math.inf
        return to, ld


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


# ---- evaluation of one point (works in a worker process) --------------------------------------------
_BUILT = None


def _init(design_path):
    global _BUILT
    _BUILT = Built(design_path)


def evaluate(theta, want_hours=True, want_fields=True):
    """(hours, takeoff_ft, landing_ft) at theta; None for what is not asked."""
    hrs = _BUILT.hours_on_station(theta) if want_hours else None
    to, ld = _BUILT.field_lengths(theta) if want_fields else (None, None)
    return hrs, to, ld


def _job(args):
    kind = args[0]
    if kind == "eval":
        return evaluate(args[1])
    variables, direction, req, fuel_factor = args[1:5]

    def worst(h):
        return evaluate(corner_theta(variables, h, direction[req]),
                        want_hours=req == "R5", want_fields=req != "R5")

    if kind == "worst":                      # worst-case value at one h
        h = args[5]
        hrs, to, ld = worst(h)
        return {"R5": hrs, "TO": to, "LD": ld}[req]
    # kind == "hhat"
    def met(h):
        if req == "R5":
            return _BUILT.hours_on_station(corner_theta(variables, h, direction[req]),
                                           fuel_factor) >= R5_HOURS - R5_SLACK_H
        _, to, ld = worst(h)
        return {"TO": to, "LD": ld}[req] <= _BUILT.L["field_length_ft"]
    return robustness(met)


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
               "value_at_upper": hi, "clipped_lower": c_lo, "clipped_upper": c_hi}
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


def sampling_check(pool, variables, oat, dirs, h, n_samples, seed):
    """Random points of U(h) and the corners of the top-5 variables of each requirement; compare
    with the monotone worst corner at h. 'beat' means a point is worse than the corner."""
    nom = nominal_theta(variables)
    rng = np.random.default_rng(seed)
    pts = []
    for _ in range(n_samples):
        th = {}
        for v in variables:
            lo, hi, _, _ = bounds(v, h)
            th[v["name"]] = lo + rng.random() * (hi - lo)
        pts.append(("random", th))
    for key in ("R5_hours", "takeoff_ft", "landing_ft"):
        names = top_variables(oat, key)
        for signs in product((0, 1), repeat=len(names)):
            th = dict(nom)
            for nm, s in zip(names, signs):
                v = next(x for x in variables if x["name"] == nm)
                lo, hi, _, _ = bounds(v, h)
                th[nm] = hi if s else lo
            pts.append((f"corner of top {len(names)} for {key}", th))
    res = pool.map(_job, [("eval", th) for _, th in pts], chunksize=1)
    corner = pool.map(_job, [("worst", variables, dirs, req, None, h) for req in ("R5", "TO", "LD")],
                      chunksize=1)
    out = {"h": h, "seed": seed, "n_random": n_samples, "n_corner_points": len(pts) - n_samples,
           "corner_value": {"R5_hours": corner[0], "takeoff_ft": corner[1], "landing_ft": corner[2]}}
    for key, idx, bad_low in (("R5_hours", 0, True), ("takeoff_ft", 1, False), ("landing_ft", 2, False)):
        vals = [(r[idx], pts[i][0]) for i, r in enumerate(res)]
        worst_val, worst_kind = (min if bad_low else max)(vals, key=lambda t: t[0])
        c = out["corner_value"][key]
        beat = [v for v, _ in vals if (v < c - 1e-6 if bad_low else v > c + 1e-6)]
        out[key] = {"worst_sampled": worst_val, "worst_sampled_kind": worst_kind,
                    "worst_random": (min if bad_low else max)(
                        r[idx] for i, r in enumerate(res) if pts[i][0] == "random"),
                    "corner": c, "n_beating_corner": len(beat),
                    "most_beating": (min if bad_low else max)(beat) if beat else None}
    return out


def clipping_report(variables, h):
    return [{"name": v["name"], "h": h, "lower_clipped": bounds(v, h)[2], "upper_clipped": bounds(v, h)[3],
             "lower_end": bounds(v, h)[0], "upper_end": bounds(v, h)[1]}
            for v in variables if bounds(v, h)[2] or bounds(v, h)[3]]


def study(design_path, n_samples=N_SAMPLES, seed=SEED, processes=None):
    t0 = time.time()
    built = Built(design_path)
    _, entries = uav.load_ledger(built.ledger_path)
    variables = uncertain_variables(entries)
    ctx = mp.get_context("fork")
    with ctx.Pool(processes, initializer=_init, initargs=(design_path,)) as pool:
        _init(design_path)
        nom = evaluate(nominal_theta(variables))
        res = {"nominal": {"R5_hours": nom[0], "takeoff_ft": nom[1], "landing_ft": nom[2]},
               "record": {"fuel_lb": built.d["fuel_lb"], "takeoff_ft": built.d["performance"]["takeoff_ft"],
                          "landing_ft": built.d["performance"]["landing_ft"]},
               "rebuild_check": built.check, "variables": variables}
        oat = one_at_a_time(pool, variables, H_GATE)
        dirs = directions(oat)
        res["one_at_a_time"] = oat
        res["directions"] = dirs
        jobs = [("hhat", variables, dirs, req, 1.0) for req in ("R5", "TO", "LD")]
        jobs.append(("hhat", variables, dirs, "R5", sizing.RESERVE_FACTOR))
        hh = pool.map(_job, jobs, chunksize=1)
        names = ("R5", "TO", "LD", "R5_reserve_usable")
        res["h_hat"] = {n: {"h_hat": r[0], "status": r[1]} for n, r in zip(names, hh)}
        r7 = min(hh[1][0], hh[2][0])
        res["h_hat"]["R7"] = {"h_hat": r7, "status": "min of take-off and landing"}
        curve = pool.map(_job, [("worst", variables, dirs, req, None, h)
                                for h in H_GRID for req in ("R5", "TO", "LD")], chunksize=1)
        res["worst_case_curve"] = [{"h": h, "R5_hours": curve[3 * i], "takeoff_ft": curve[3 * i + 1],
                                    "landing_ft": curve[3 * i + 2]} for i, h in enumerate(H_GRID)]
        check_h = [H_GATE]
        if 0.05 < hh[0][0] < H_MAX and abs(hh[0][0] - H_GATE) > 0.02:
            check_h.append(hh[0][0])
        res["sampling"] = [sampling_check(pool, variables, oat, dirs, h, n_samples, seed + i)
                           for i, h in enumerate(check_h)]
        res["clipping"] = {"at_h_1": clipping_report(variables, 1.0),
                           "at_h_max": clipping_report(variables, H_MAX)}
    res["runtime_s"] = time.time() - t0
    return res


# ---- record and report ----------------------------------------------------------------------------
def git_commit():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
                          cwd=REPO).stdout.strip()


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
    a = ap.parse_args(argv)
    res = study(a.design, a.samples)
    ledger = Path(a.design).parent / "ledger.yaml"
    res["inputs"] = {
        "design": a.design, "design_sha256": sp.sha256(a.design),
        "ledger": str(ledger), "ledger_sha256": sp.sha256(ledger),
        "git_commit": git_commit(), "python": platform.python_version(), "numpy": np.__version__,
        "pyyaml": yaml.__version__, "seed": SEED, "n_random_samples": a.samples,
        "n_corner_variables": N_CORNER_VARS, "h_max": H_MAX, "h_gate": H_GATE,
        "engine_weight": ENGINE_WEIGHT, "r5_slack_h": R5_SLACK_H, "h_tolerance": H_TOL,
        "cpu_count": mp.cpu_count()}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(_json_safe(res), indent=2, default=float))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report_text(json.loads(Path(a.out).read_text())))
    for k, v in res["h_hat"].items():
        print(k, v)
    print(f"runtime {res['runtime_s']:.0f} s")


def report_text(res):
    """Markdown report from the JSON record (no number is typed here)."""
    inp, nom, hh = res["inputs"], res["nominal"], res["h_hat"]
    rec = res["record"]

    def g(x, f=".4g"):
        return x if isinstance(x, str) else format(x, f)

    def hrow(name, key, unit):
        h = hh[key]
        return f"| {name} | {g(h['h_hat'], '.4f')} | {h['status']} | {'yes' if h['h_hat'] >= 1 else 'no'} |"

    L = ["# Task 12 Stage 3: info-gap robustness of the built design (R5, R7)", "",
         f"Generated from `{inp['design']}` by `python -m measurement.info_gap`; the numbers below are "
         "read from the run record `info_gap.json` (inputs, versions, seed there).", "",
         "## Method", "",
         "Ben-Haim's info-gap as in Marchau et al., DMDU, ch. 10. Uncertainty model (10.7), p. 213: "
         "theta_k in [theta_k0 - h W_k_lower, theta_k0 + h W_k_upper], weights W set so that h = 1 gives "
         "the ledger band ends (W_lower = nominal - band_lo, W_upper = band_hi - nominal; one-sided where "
         "the nominal is a band end). Robustness (10.8), p. 214: h_hat is the largest h at which the "
         "worst case over U(h) still meets the requirement, found by bisection on h in [0, "
         f"{g(inp['h_max'])}]. Uncertain quantities: {len(res['variables'])}, the ledger assumptions that "
         "carry a band plus two engine multipliers (SFC and full-throttle power of the TP100 table, "
         f"+-{g(inp['engine_weight'] * 100)} % at h = 1). The SFC multiplier is applied on top of the "
         "ledger's 1.05 SFC allowance (`engine_sfc_allowance`), which stays in.", "",
         "The aircraft is built: W0, wing loading, aspect ratio, tail scale and fuel load are the record's "
         "and are not re-sized, so weight assumptions (composite factor, avionics weight, gear length) act "
         "only through geometry and drag, not through a change of W0 or of fuel load. R5: hours on station "
         "with the record's fuel, the loiter time at which the rebuilt mission fuel (including the 6 % "
         "reserve factor) equals the record's fuel. R7: take-off and landing distance over 50 ft against "
         "the ledger field length. The engine power multiplier scales the take-off shaft power as well as "
         "the table's lapse.", "",
         "## Nominal (h = 0)", "",
         "| Quantity | Record | Rebuilt here |", "|---|---|---|",
         f"| Hours on station | 8 (requirement; the record's fuel was sized for it) | {g(nom['R5_hours'], '.4f')} |",
         f"| Take-off over 50 ft (ft) | {g(rec['takeoff_ft'], '.2f')} | {g(nom['takeoff_ft'], '.2f')} |",
         f"| Landing over 50 ft (ft) | {g(rec['landing_ft'], '.2f')} | {g(nom['landing_ft'], '.2f')} |", "",
         "## Robustness against the Gate B threshold (h = 1)", "",
         "| Requirement | h_hat | Status | Meets Gate B (>= 1) |", "|---|---|---|---|",
         hrow("R5, 8 h on station", "R5", ""), hrow("R7 take-off", "TO", ""),
         hrow("R7 landing", "LD", ""), hrow("R7 combined (min)", "R7", ""), "",
         "Secondary, not the requirement: R5 if the 6 % reserve could be burned as well (target fuel = "
         f"{g(sizing.RESERVE_FACTOR)} x the record's): h_hat = {g(hh['R5_reserve_usable']['h_hat'], '.4f')} "
         f"({hh['R5_reserve_usable']['status']}). Reported to show how far the design is from the "
         "threshold, not as a pass.", ""]
    L += ["## Worst case against h", "",
          "| h | Hours on station | Take-off (ft) | Landing (ft) |", "|---|---|---|---|"]
    for r in res["worst_case_curve"]:
        L.append(f"| {g(r['h'])} | {g(r['R5_hours'], '.3f')} | {g(r['takeoff_ft'], '.1f')} | "
                 f"{g(r['landing_ft'], '.1f')} |")
    L += ["", "## What drives each requirement (one at a time at h = 1)", "",
          "Effect = change at the harmful end of the variable's band from the nominal value. Direction -1 "
          "means the lower band end is harmful, +1 the upper end, 0 neither. The corner used in the worst "
          "case takes every variable at its harmful end.", ""]
    oat = res["one_at_a_time"]
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
    L += ["## Check of the monotone corner by sampling", "",
          f"Seed {inp['seed']}, {inp['n_random_samples']} points uniform in U(h) plus the corners of the "
          f"{inp['n_corner_variables']} most influential variables of each requirement (others at nominal).", ""]
    for s in res["sampling"]:
        L += [f"At h = {g(s['h'], '.4f')}: {s['n_random']} random and {s['n_corner_points']} corner points.", "",
              "| Quantity | Monotone corner | Worst sampled | Worst random | Points worse than the corner |",
              "|---|---|---|---|---|"]
        for key in ("R5_hours", "takeoff_ft", "landing_ft"):
            e = s[key]
            L.append(f"| {key} | {g(e['corner'], '.4f')} | {g(e['worst_sampled'], '.4f')} "
                     f"({e['worst_sampled_kind']}) | {g(e['worst_random'], '.4f')} | {e['n_beating_corner']} |")
        L.append("")
    cl = res["clipping"]
    L += ["## Clipping", "",
          f"At h = 1: {len(cl['at_h_1'])} variables clipped"
          + (": " + ", ".join(c["name"] for c in cl["at_h_1"]) if cl["at_h_1"] else "") + ". "
          f"At h = {g(inp['h_max'])}: {len(cl['at_h_max'])}"
          + (": " + ", ".join(f"{c['name']} (" + ("lower" if c["lower_clipped"] else "") +
                              ("/" if c["lower_clipped"] and c["upper_clipped"] else "") +
                              ("upper" if c["upper_clipped"] else "") + ")" for c in cl["at_h_max"]) if cl["at_h_max"] else "")
          + ". Limits: non-negative, and at most 1 for a dimensionless fraction or efficiency.", "",
          "## Record", "",
          f"Design sha256 `{inp['design_sha256'][:16]}...`, ledger sha256 `{inp['ledger_sha256'][:16]}...`, "
          f"git commit `{inp['git_commit']}`, Python {inp['python']}, numpy {inp['numpy']}, "
          f"{inp['cpu_count']} CPUs, runtime {g(res['runtime_s'], '.0f')} s.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())

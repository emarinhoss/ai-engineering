"""Lightest pusher that passes Gate B with a photo-scaled TP100 of rated power P (owner ruling
2026-11-22/23): R5's guarantee (at least r5_robust_hours = 3.5 h at info-gap horizon h = 1), R7 at
h >= 1, and every Stage 1 compliance row with the current ledger margins.

    python -m measurement.robust_sizing --out runs/task12/stage3/2026-11-23/robust \
        --report docs/validation/2026-11-23_task12_robust_sizing.md

Method (spec task12 section 7, R5 restated; the engine is hypothetical, see the report):
 1. A design candidate is (P, W/S, A, L_sized). L_sized >= 8 h is the loiter time Stage 1 sizes the
    fuel for (`loiter_h` of the ledger given to stage1.analyse); the built aircraft carries that fuel.
    For (P, W/S, A) the smallest L_sized in [8, 16] h (bisection, 0.05 h) is found at which the built
    aircraft, at the design corner theta*, flies at least r5_robust_hours. The built aircraft is the
    info-gap one: wing area fixed, W0 = We(theta*) + payload + the record's fuel. A mission that cannot
    be flown counts as 0 h. A size that does not close (stage1 raises) is "too large"; a candidate
    whose 16 h size is still short fails.
 2. theta* starts as the h = 1 worst point of the R5 search on the 360 hp study of 2026-11-22. After
    the best design is picked, the full corrected info_gap.study is run on it; if the R5 guarantee or R7
    has h_hat < 1, the worst point that study found at h = 1 for R5 becomes theta*, and steps 1-3 are
    repeated once (at most 2 iterations, each reported).
 3. Candidates P x W/S x A on a grid; per P keep those with no failed compliance row, take the lightest
    W0, then refine at +-1 in W/S and A (the 8 neighbours, one pass).
Nothing is tuned: the grid, tolerances and iteration count are those above.
"""
# ruff: noqa: ISC004  (the report text is a list of adjacent string pieces, as in info_gap)
import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from functools import cache, lru_cache
from itertools import pairwise
from pathlib import Path

import numpy as np
import yaml

from conceptual import stage1, uav
from conceptual.engine_model import TP100_TABLE
from measurement import info_gap
from measurement.rubber_tp100 import scaled_engine

REPO = Path(__file__).resolve().parents[1]
POWERS = (300.0, 330.0, 360.0, 400.0, 450.0)
WS_LEVELS = (11.0, 13.0, 15.0, 17.0)
A_LEVELS = (8.0, 10.0, 12.0, 14.0)
L_LO, L_HI, L_TOL = 8.0, 16.0, 0.05
MAX_ITERATIONS = 2
THETA_SOURCE = REPO / "runs/task12/stage3/2026-11-22/rubber/P360/info_gap.json"
H_GATE = 1.0


# ---- bisection on the sized loiter time -------------------------------------------------------------
def bisect_sized(endurance, need, lo=L_LO, hi=L_HI, tol=L_TOL):
    """Smallest L in [lo, hi] (to tol) with endurance(L) >= need, endurance increasing in L.
    endurance(L) is None when the aircraft cannot be sized at L (it does not close): too large.
    Returns (L, status); L is None if even hi is not enough."""
    def enough(L):
        h = endurance(L)
        return h is not None and h >= need
    if enough(lo):
        return lo, "8 h is enough"
    hi_ok = False                       # hi is known to be sized and enough
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        h = endurance(mid)
        if h is None:
            hi, hi_ok = mid, False
        elif h >= need:
            hi, hi_ok = mid, True
        else:
            lo = mid
    if not hi_ok and not enough(hi):
        return None, f"not reached at {hi:g} h"
    return hi, "bisected"


# ---- one candidate -----------------------------------------------------------------------------------
@cache
def _engine(P):
    L, _ = uav.load_ledger()
    return scaled_engine(P, L)


@lru_cache(maxsize=1)
def _raw():
    return stage1.engine_options()[1][stage1.CHOSEN_ENGINE]


def sized_aircraft(P, W_S, A, L_sized):
    """Stage 1 analysis of the pusher at loiter time L_sized, its ledger values and its record."""
    L, _ = uav.load_ledger()
    L = dict(L, loiter_h=float(L_sized))
    a = stage1.analyse("pusher", W_S, A, L, _engine(P))
    return a, L, stage1.design_record(a, L, _raw())


def corner_hours(record, L, theta):
    """Hours the built aircraft (info-gap weight banding) flies at theta; 0 if not flyable."""
    return info_gap.Built("in memory", True, record=(record, L, TP100_TABLE)).hours_on_station(theta)


def evaluate_candidate(P, W_S, A, theta, need):
    """Row for one (P, W/S, A): the smallest sized loiter time that gives `need` hours at theta,
    and the Stage 1 compliance of that aircraft."""
    row = {"P_hp": P, "W_S": W_S, "A": A, "ok": False, "L_sized_h": None, "failed": [], "status": ""}
    cache = {}

    def endurance(Lh):
        try:
            a, L, rec = sized_aircraft(P, W_S, A, Lh)
        except ValueError as e:
            row["status"] = f"does not close at {Lh:.3f} h: {e}"
            return None
        cache[Lh] = (a, L, rec)
        return corner_hours(rec, L, theta)

    try:
        Ls, status = bisect_sized(endurance, need)
        if Ls is None:
            row["status"] = status
            return row
        a, L, rec = cache[Ls] if Ls in cache else sized_aircraft(P, W_S, A, Ls)
        d = a["design"]
        comp = stage1.compliance(d, d["ledger_used"], a["layout"], a["performance"], *a["fuel_volume"], _raw())
        row.update(ok=True, status=status, L_sized_h=Ls, failed=[c["requirement"] for c in comp if c["met"] is False],
                   corner_hours=corner_hours(rec, L, theta), W0_lb=d["W0"], fuel_lb=d["fuel"],
                   We_lb=d["We"], engine_weight_lb=_engine(P)["weight_lb"], span_ft=d["geom"]["wing"].span,
                   power_margin=1.0 - max(d["power_req"].values()) / P)
    except ValueError as e:                  # a rebuild or analysis problem: recorded, never silent
        row["status"] = f"error: {e}"
    return row


_THETA = None


def _init(theta):
    global _THETA
    _THETA = theta


def _job(args):
    P, W_S, A, need = args
    return evaluate_candidate(P, W_S, A, _THETA, need)


# ---- selection ------------------------------------------------------------------------------------
def compliant(rows):
    return [r for r in rows if r["ok"] and not r["failed"]]


def lightest(rows, P):
    c = [r for r in compliant(rows) if r["P_hp"] == P]
    return min(c, key=lambda r: r["W0_lb"]) if c else None


def neighbours(row, done):
    out = []
    for dw in (-1.0, 0.0, 1.0):
        for da in (-1.0, 0.0, 1.0):
            p = (row["P_hp"], row["W_S"] + dw, row["A"] + da)
            if (dw or da) and p[1] > 0.0 and p[2] >= 3.0 and p not in done:
                out.append(p)
    return out


def search(theta, need, processes=4):
    """Grid then one refinement pass; returns all rows (grid rows flagged) and the per-P winners."""
    with mp.get_context("fork").Pool(processes, initializer=_init, initargs=(theta,)) as pool:
        grid = [(P, w, a, need) for P in POWERS for w in WS_LEVELS for a in A_LEVELS]
        rows = pool.map(_job, grid, chunksize=1)
        for r in rows:
            r["pass"] = "grid"
        done = {(r["P_hp"], r["W_S"], r["A"]) for r in rows}
        extra = []
        for P in POWERS:
            best = lightest(rows, P)
            if best:
                for p in neighbours(best, done):
                    done.add(p)
                    extra.append((*p, need))
        more = pool.map(_job, extra, chunksize=1)
        for r in more:
            r["pass"] = "refine"
    rows += more
    return rows, {P: lightest(rows, P) for P in POWERS}


# ---- records ----------------------------------------------------------------------------------------
def ledger_text(L_sized):
    """Copy of the current ledger with loiter_h set to L_sized and a note on why."""
    text = uav.LEDGER.read_text()
    pat = re.compile(r'^(\s*loiter_h:\s*\{value: )[0-9.]+(,.*?source: ")(.*?)("\}\s*)$', re.MULTILINE)
    note = f"; sized loiter {L_sized:.3f} h by measurement/robust_sizing.py so that r5_robust_hours holds at the design corner"
    new, n = pat.subn(lambda m: f"{m.group(1)}{L_sized!r}{m.group(2)}{m.group(3)}{note}{m.group(4)}", text)
    if n != 1:
        raise ValueError("loiter_h line not found in the ledger")
    return new


def write_record(row, folder):
    """Record folder like measurement/rubber_tp100.py: design_pusher.json, ledger.yaml,
    tp100_table.json (plus the sizing row)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rec = sized_aircraft(row["P_hp"], row["W_S"], row["A"], row["L_sized_h"])[2]
    (folder / "design_pusher.json").write_text(json.dumps(rec, indent=1, default=float))
    (folder / "ledger.yaml").write_text(ledger_text(row["L_sized_h"]))
    if uav.load_ledger(folder / "ledger.yaml")[0]["loiter_h"] != row["L_sized_h"]:
        raise ValueError("ledger copy does not carry L_sized")
    shutil.copyfile(TP100_TABLE, folder / "tp100_table.json")
    (folder / "robust_candidate.json").write_text(json.dumps(row, indent=1, default=float))
    return folder / "design_pusher.json"


def run_study(row, folder):
    """Full corrected info-gap study of a written record; returns its summary and the h = 1 R5 worst point."""
    design = write_record(row, folder)
    ig = info_gap.study(str(design))
    (Path(folder) / "info_gap.json").write_text(json.dumps(info_gap._json_safe(ig), indent=1, default=float))
    h1 = next(c for c in ig["worst_case_curve"] if c["h"] == H_GATE)["R5"]
    hh = {k: v["h_hat"] for k, v in ig["h_hat"].items()}
    return {"h_hat": hh, "R5_guarantee": hh.get("R5_guarantee"), "R7": hh["R7"],
            "gate_b": (hh.get("R5_guarantee") or 0.0) >= H_GATE and hh["R7"] >= H_GATE,
            "runtime_s": ig["runtime_s"], "worst_R5_at_h1": {"moved": h1["moved"], "hours": h1["hours"],
                                                              "not_flyable": h1["not_flyable"]}}


def theta_from_moved(moved):
    _, entries = uav.load_ledger()
    variables = info_gap.uncertain_variables(entries)
    theta = info_gap.nominal_theta(variables)
    unknown = set(moved) - set(theta)
    if unknown:
        raise ValueError(f"theta* names not in the ledger: {sorted(unknown)}")
    theta.update(moved)
    return theta


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, cwd=REPO).stdout.strip()


# ---- the driver -------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--budget-min", type=float, default=170.0,
                    help="no further full studies are started after this many minutes")
    ap.add_argument("--curve", action="store_true",
                    help="the robustness-against-power curve (2026-11-23 ruling) instead of the sweep")
    ap.add_argument("--powers", help="curve only: comma-separated powers in hp (default: the curve's eight)")
    ap.add_argument("--A", dest="A_levels", help="curve only: comma-separated aspect ratios")
    ap.add_argument("--workers", type=int, default=4, help="curve only: powers run in parallel")
    a = ap.parse_args(argv)
    if a.curve:
        return curve_main(a, argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    need = uav.load_ledger()[0]["r5_robust_hours"]
    moved = json.loads(THETA_SOURCE.read_text())["worst_case_curve"]
    moved = next(c for c in moved if c["h"] == H_GATE)["R5"]["moved"]
    iterations, final = [], None
    for it in range(1, MAX_ITERATIONS + 1):
        theta = theta_from_moved(moved)
        t_it = time.time()
        rows, winners = search(theta, need)
        found = {P: w for P, w in winners.items() if w}
        rec = {"iteration": it, "theta_star_moved": moved, "n_candidates": len(rows), "search_s": time.time() - t_it,
               "candidates": rows, "winners": {f"{P:g}": w for P, w in winners.items()}}
        print(f"iteration {it}: {len(rows)} candidates, {len(found)} powers with a compliant design,"
              f" {rec['search_s']:.0f} s", flush=True)
        iterations.append(rec)
        if not found:
            rec["overall"] = None
            break
        best = min(found.values(), key=lambda r: r["W0_lb"])
        rec["overall"] = best
        folder = out / f"iteration{it}" / f"P{best['P_hp']:g}"
        rec["study"] = run_study(best, folder)
        print(f"  lightest P={best['P_hp']:g} W0={best['W0_lb']:.0f} L_sized={best['L_sized_h']:.2f}"
              f" R5g h_hat={rec['study']['R5_guarantee']:.3f} R7={rec['study']['R7']:.3f}", flush=True)
        final = (it, found, best)
        if rec["study"]["gate_b"] or it == MAX_ITERATIONS:
            break
        moved = rec["study"]["worst_R5_at_h1"]["moved"]
    # records for every per-P winner of the last iteration, and their studies as time allows
    per_p = {}
    if final:
        it, found, best = final
        for P, w in sorted(found.items(), key=lambda kv: kv[1]["W0_lb"]):
            folder = out / f"P{P:g}"
            if w is best:
                shutil.copytree(out / f"iteration{it}" / f"P{P:g}", folder, dirs_exist_ok=True)
                per_p[f"{P:g}"] = {"row": w, "study": iterations[it - 1]["study"]}
            elif (time.time() - t0) / 60.0 < a.budget_min:
                per_p[f"{P:g}"] = {"row": w, "study": run_study(w, folder)}
            else:
                write_record(w, folder)
                per_p[f"{P:g}"] = {"row": w, "study": None}
            s = per_p[f"{P:g}"]["study"]
            print(f"  P={P:g} W0={w['W0_lb']:.0f} study: " + (f"R5g {s['R5_guarantee']:.3f} R7 {s['R7']:.3f}"
                                                              if s else "not run (time budget)"), flush=True)
    dirty = git("status", "--porcelain")
    meta = {"commit": git("rev-parse", "HEAD"), "git_dirty": bool(dirty), "git_dirty_files": dirty.splitlines(),
            "ledger": str(uav.LEDGER.relative_to(REPO)), "ledger_sha256": sha256(uav.LEDGER),
            "table_sha256": sha256(TP100_TABLE), "theta_source": str(THETA_SOURCE.relative_to(REPO)),
            "theta_source_sha256": sha256(THETA_SOURCE), "r5_robust_hours": need,
            "grid": {"P_hp": POWERS, "W_S": WS_LEVELS, "A": A_LEVELS, "L_sized_range_h": [L_LO, L_HI],
                     "L_tol_h": L_TOL}, "max_iterations": MAX_ITERATIONS,
            "python": platform.python_version(), "numpy": np.__version__, "pyyaml": yaml.__version__,
            "cpu_count": mp.cpu_count(), "command": "python -m measurement.robust_sizing " +
            " ".join(argv if argv is not None else __import__("sys").argv[1:]),
            "weight_law": "W = 135.8 (P/241)^0.803, Raymer Table 10.3 p. 224", "runtime_s": time.time() - t0}
    overall = final[2] if final else None
    res = {"inputs": meta, "iterations": iterations, "per_P": per_p,
           "overall_winner": ({"P_hp": overall["P_hp"], "W0_lb": overall["W0_lb"],
                               "gate_b": per_p[f"{overall['P_hp']:g}"]["study"]["gate_b"]} if overall else None)}
    (out / "sweep.json").write_text(json.dumps(info_gap._json_safe(res), indent=1, default=float))
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report_text(json.loads((out / "sweep.json").read_text())))
    print(f"runtime {meta['runtime_s']:.0f} s")


# ---- report -----------------------------------------------------------------------------------------
def report_text(res):
    inp = res["inputs"]
    lines = [
        "# Task 12: lightest pusher that passes Gate B robustness (photo-scaled TP100)", "",
        "Generated by `measurement/robust_sizing.py` from `sweep.json`; every number is from that run.", "",
        "**The engine is hypothetical.** No turboprop of these powers with the TP100's table is known; the PBS "
        "brochure has none above 241 hp. The engine is the TP100 table scaled in power by P/241 (same lapse, "
        "part-power SFC curve, 5 % SFC allowance) and in weight by Raymer Table 10.3, W = 135.8 (P/241)^0.803. "
        "The result says which power class to look for, not that it exists.", "",
        "## Method", "",
        f"- Candidates: P in {list(inp['grid']['P_hp'])} hp, W/S in {list(inp['grid']['W_S'])}, A in "
        f"{list(inp['grid']['A'])}; per P the lightest candidate with no failed Stage 1 compliance row is refined at "
        "+-1 in W/S and A (8 neighbours, one pass).",
        f"- Each candidate is sized for the smallest loiter time L_sized in [8, 16] h (bisection, "
        f"{inp['grid']['L_tol_h']} h) at which the built aircraft (wing area fixed, W0 = We(theta*) + payload + fuel) "
        f"flies at least {inp['r5_robust_hours']:g} h at the design corner theta*; not flyable counts as 0 h.",
        f"- theta* of iteration 1 is the h = 1 worst R5 point of `{inp['theta_source']}`. After the lightest design "
        "is picked the full corrected `info_gap.study` runs on it; if the R5 guarantee or R7 has h_hat < 1 its "
        "worst R5 point at h = 1 becomes theta* and the search is repeated once.", "",
        "## Iterations", ""]
    for it in res["iterations"]:
        lines += [f"### Iteration {it['iteration']}", "",
                  f"theta* moved variables ({len(it['theta_star_moved'])}): "
                  + ", ".join(f"`{k}` = {v:g}" for k, v in it["theta_star_moved"].items()), "",
                  f"{it['n_candidates']} candidates evaluated in {it['search_s']:.0f} s.", ""]
        lines += ["| P (hp) | lightest W0 (lb) | W/S | A | L_sized (h) |", "|---|---|---|---|---|"]
        for P, w in it["winners"].items():
            lines.append(f"| {P} | {w['W0_lb']:.0f} | {w['W_S']:g} | {w['A']:g} | {w['L_sized_h']:.2f} |" if w
                         else f"| {P} | no compliant candidate | | | |")
        lines.append("")
        if it.get("study"):
            s = it["study"]
            lines += [f"Full study of the lightest ({it['overall']['P_hp']:g} hp, W0 {it['overall']['W0_lb']:.0f} lb): "
                      f"R5 guarantee h_hat {s['R5_guarantee']:.3f}, R7 h_hat {s['R7']:.3f}, "
                      f"Gate B {'passed' if s['gate_b'] else 'not passed'}. Worst R5 point at h = 1: "
                      f"{s['worst_R5_at_h1']['hours']:.2f} h"
                      + (f" ({s['worst_R5_at_h1']['not_flyable']})" if s['worst_R5_at_h1']['not_flyable'] else "") + ".", ""]
        elif it.get("overall") is None:
            lines += ["No candidate passed Stage 1 compliance at this theta*.", ""]
    lines += ["## Lightest design per power (last iteration)", "",
              "| P (hp) | engine (lb) | W0 (lb) | fuel (lb) | L_sized (h) | W/S | A | span (ft) | power margin | "
              "R5 guarantee h_hat | R7 h_hat | Gate B |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for P, v in res["per_P"].items():
        r, s = v["row"], v["study"]
        lines.append(f"| {P} | {r['engine_weight_lb']:.0f} | {r['W0_lb']:.0f} | {r['fuel_lb']:.0f} | "
                     f"{r['L_sized_h']:.2f} | {r['W_S']:g} | {r['A']:g} | {r['span_ft']:.1f} | {r['power_margin']:.1%} | "
                     + (f"{s['R5_guarantee']:.3f} | {s['R7']:.3f} | {'pass' if s['gate_b'] else 'fail'} |"
                        if s else "not run | not run | not run |"))
    lines += [""]
    ow = res["overall_winner"]
    if ow is None:
        lines += ["## Overall", "", "No candidate passed Stage 1 compliance with the required sized loiter time; "
                  "nothing passes Gate B on this grid.", ""]
    else:
        lines += ["## Overall", "",
                  f"Lightest compliant design: {ow['P_hp']:g} hp, W0 {ow['W0_lb']:.0f} lb. Gate B on its full study: "
                  f"{'passed' if ow['gate_b'] else 'NOT passed'}.", ""]
    lines += ["## Inputs", "", f"- commit {inp['commit']} (dirty tree: {inp['git_dirty']}); ledger sha256 `{inp['ledger_sha256']}`; "
              f"engine table sha256 `{inp['table_sha256']}`.",
              f"- python {inp['python']}, numpy {inp['numpy']}, pyyaml {inp['pyyaml']}, {inp['cpu_count']} CPUs; "
              f"runtime {inp['runtime_s']:.0f} s.", f"- command: `{inp['command']}`", "",
              "Exclusions of the info-gap study (headwind, Oswald e, ISA deviation, control law, part-power SFC "
              "shape, trim drag) apply to every h_hat above; see `docs/validation/2026-11-22_task12_stage3_info_gap.md`.", ""]
    return "\n".join(lines)


# ======================================================================================================
# The robustness-against-power curve (owner ruling 2026-11-23, review docs/reviews/2026-11-23_task12_
# robust_sizing_review.md RS-1 to RS-7). No pass/fail: h_hat of each failure mode against engine power.
#
#     python -m measurement.robust_sizing --curve --out runs/task12/stage3/2026-11-23/curve \
#         --report docs/validation/2026-11-23_task12_robustness_curve.md
#
# Two failure modes of the R5 guarantee (3.5 h for every member of U(h)):
#   endurance mode: the largest h such that every member of U(h) that flies the mission gives at least
#       r5_robust_hours (a member that cannot fly the mission is ignored here);
#   cliff mode: the largest h such that every member of U(h) can fly the mission, i.e. the transit power
#       ratio (shaft power needed over available on the worst mission sub-step, info_gap.transit_power_ratio)
#       stays at or below 1.
# The R5-guarantee h_hat is min of the two (the full study's R5_guarantee is run on the same design and
# reported beside it). Each mode's worst case uses the corrected search (coordinate + pair flips).
# Sizing (RS-4): per (P, W/S, A) the smallest L_sized in [8, 16] h such that the built aircraft flies
# >= r5_robust_hours at every endurance corner of a SET and can fly the mission at every cliff corner of
# the set. "Cannot fly" means too heavy (L too large); fewer than 3.5 h means L too small.
# The set starts from the two corners of the 400 hp study and grows per power: after a design's mode
# study its worst point at h = 1 for a mode is added if it violates and is new; sizing repeats (at most
# MAX_CURVE_ITER times). The full info_gap study then runs once on the final design.
# ======================================================================================================
CURVE_POWERS = (300.0, 340.0, 360.0, 380.0, 400.0, 420.0, 450.0, 480.0)
CURVE_WS = (11.0, 12.0, 13.0, 14.0, 15.0)
CURVE_A = (8.0, 9.0, 10.0, 12.0)
MAX_CURVE_ITER = 3
SEED_CORNERS = REPO / "runs/task12/stage3/2026-11-23/curve/seed_corners.json"
GUESS_BASE_LB, GUESS_PER_HP, GUESS_PER_H = 3000.0, 6.0, 400.0
GUESS_RETRY = 1.3
REFINE_FACTOR = 2


# ---- the first guess of the weight iteration (RS-5) -------------------------------------------------
def first_guess(P, L_sized):
    """W0 first guess scaled with engine and fuel: 3,000 + 6 (P - 241) lb at 8 h, plus 400 lb per extra
    sized hour. The 3,000 lb default of uav.evaluate made heavy designs 'not close' (RS-5)."""
    return GUESS_BASE_LB + GUESS_PER_HP * (P - 241.0) + GUESS_PER_H * (L_sized - L_LO)


def close_with_retry(run, guess):
    """run(guess) -> result; raises ValueError 'does not close at W0 ...' if the fractions sum to 1 or
    more at the guess. Retries once from GUESS_RETRY x guess. Returns (result or None, info); info
    says what happened (the reason is recorded per row, never silent)."""
    info = {"guess_lb": guess, "retried": False}
    for g in (guess, GUESS_RETRY * guess):
        try:
            return run(g), info
        except ValueError as e:
            if "does not close" not in str(e) and "did not converge" not in str(e):
                raise
            info["error" if g != guess else "first_error"] = str(e)
            if g == guess:
                info["retried"], info["retry_guess_lb"] = True, GUESS_RETRY * guess
    return None, info


def sized_aircraft_guess(P, W_S, A, L_sized, W0_guess):
    """sized_aircraft from a given first guess of the weight iteration (stage1.analyse W0_guess)."""
    L, _ = uav.load_ledger()
    L = dict(L, loiter_h=float(L_sized))
    a = stage1.analyse("pusher", W_S, A, L, _engine(P), W0_guess=W0_guess)
    return a, L, stage1.design_record(a, L, _raw())


# ---- the sized-loiter bisection against a set of corners (RS-4) --------------------------------------
def bisect_two_corner(classify, lo=L_LO, hi=L_HI, tol=L_TOL):
    """Smallest L in [lo, hi] (to tol) with classify(L) == 'ok'. classify returns 'small' (L too small:
    fewer hours than needed at an endurance corner), 'heavy' (L too large: the aircraft does not close or
    cannot fly a cliff corner) or 'ok'. It is not assumed that hours rise with L everywhere: an
    unflyable point is 'heavy' and moves the upper bound down, not the lower bound up (RS-4).
    Returns (L, status); L is None with the reason if no L satisfies both."""
    c = classify(lo)
    if c == "ok":
        return lo, f"{lo:g} h is enough"
    if c == "heavy":
        return None, f"too heavy already at {lo:g} h"
    hi_state = None                              # state of the current hi: None = untested 'hi' (16 h)
    best = None
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        c = classify(mid)
        if c == "ok":
            hi, hi_state, best = mid, "ok", mid
        elif c == "heavy":
            hi, hi_state = mid, "heavy"
        else:
            lo = mid
    if best is not None:
        return best, "bisected"
    if hi_state is None:
        hi_state = classify(hi)
        if hi_state == "ok":
            return hi, "bisected"
    if hi_state == "heavy":
        return None, (f"no L satisfies both: too few hours at an endurance corner below {lo:.2f} h, "
                      f"too heavy (not flyable or not closing) from {hi:.2f} h")
    return None, f"not reached at {hi:g} h"


# ---- corners: theta as a dict of moved variables ------------------------------------------------------
@cache
def _nominal_tuple():
    _, entries = uav.load_ledger()
    return tuple(sorted(info_gap.nominal_theta(info_gap.uncertain_variables(entries)).items()))


def theta_of(moved):
    theta = dict(_nominal_tuple())
    unknown = set(moved) - set(theta)
    if unknown:
        raise ValueError(f"theta names not in the ledger: {sorted(unknown)}")
    theta.update(moved)
    return theta


def moved_of(theta):
    nom = dict(_nominal_tuple())
    return {k: v for k, v in theta.items() if v != nom[k]}


def same_corner(a, b, tol=1e-9):
    return set(a) == set(b) and all(abs(a[k] - b[k]) <= tol for k in a)


def seed_sets(path=SEED_CORNERS):
    d = json.loads(Path(path).read_text())
    return [dict(c) for c in d["endurance"]], [dict(c) for c in d["cliff"]]


def add_corner(corners, label, moved):
    """Append {label, moved} unless an equal corner is in the list; True if added."""
    if any(same_corner(c["moved"], moved) for c in corners):
        return False
    corners.append({"label": label, "moved": dict(moved)})
    return True


# ---- one candidate against the sets ------------------------------------------------------------------
def candidate_row(P, W_S, A):
    return {"P_hp": P, "W_S": W_S, "A": A, "ok": False, "L_sized_h": None, "failed": [], "status": "",
            "closure": [], "trace": []}


def evaluate_candidate_sets(P, W_S, A, E_set, C_set, need, cache_):
    """Row for one (P, W/S, A) against the corner sets. cache_ holds the Stage 1 analyses by L."""
    row = candidate_row(P, W_S, A)
    E_th = [theta_of(c["moved"]) for c in E_set]
    C_th = [theta_of(c["moved"]) for c in C_set]

    seen = set()

    def sized(Lh):
        key = (P, W_S, A, round(Lh, 6))
        if key not in cache_:
            got, info = close_with_retry(lambda g: sized_aircraft_guess(P, W_S, A, Lh, g), first_guess(P, Lh))
            cache_[key] = (got, info)
        if key not in seen:
            seen.add(key)
            row["closure"].append({"L_h": Lh, **cache_[key][1], "closed": cache_[key][0] is not None})
        return cache_[key][0]

    def classify(Lh):
        got = sized(Lh)
        if got is None:
            row["status"] = f"does not close at {Lh:.3f} h from the first guess or from {GUESS_RETRY} x it"
            row["trace"].append({"L_h": Lh, "class": "heavy", "why": "does not close"})
            return "heavy"
        _, L, rec = got
        B = info_gap.Built("in memory", True, record=(rec, L, TP100_TABLE))
        hours, ratios = [], []
        for th in C_th:
            r, reason = info_gap.transit_power_ratio(B, th)
            ratios.append(r)
            if reason:
                row["trace"].append({"L_h": Lh, "class": "heavy", "why": "cliff corner not flyable: " + reason,
                                     "ratio": r})
                return "heavy"
        for th in E_th:
            h, reason = B.hours_detail(th)
            hours.append(h)
            if reason and reason.startswith("mission not flyable"):
                row["trace"].append({"L_h": Lh, "class": "heavy", "why": "endurance corner not flyable: " + reason})
                return "heavy"
        short = min(hours) < need - info_gap.R5_SLACK_H
        row["trace"].append({"L_h": Lh, "class": "small" if short else "ok", "hours_E": hours, "ratio_C": ratios})
        return "small" if short else "ok"

    try:
        Ls, status = bisect_two_corner(classify)
        if Ls is None:
            why = row["trace"][-1].get("why") if row["trace"] and row["trace"][-1]["class"] == "heavy" else None
            row["status"] = status + (f" (last heavy point: {why})" if why else "")
            return row
        a, L, rec = sized(Ls)
        d = a["design"]
        comp = stage1.compliance(d, d["ledger_used"], a["layout"], a["performance"], *a["fuel_volume"], _raw())
        B = info_gap.Built("in memory", True, record=(rec, L, TP100_TABLE))
        row.update(ok=True, status=status, L_sized_h=Ls, failed=[c["requirement"] for c in comp if c["met"] is False],
                   corner_hours=[B.hours_detail(t)[0] for t in E_th],
                   corner_ratio=[info_gap.transit_power_ratio(B, t)[0] for t in C_th],
                   W0_lb=d["W0"], fuel_lb=d["fuel"], We_lb=d["We"], engine_weight_lb=_engine(P)["weight_lb"],
                   span_ft=d["geom"]["wing"].span, power_margin=1.0 - max(d["power_req"].values()) / P)
    except ValueError as e:                  # a rebuild or analysis problem: recorded, never silent
        row["status"] = f"error: {e}"
    return row


def curve_search(P, E_set, C_set, need, cache_, grid_ws=CURVE_WS, grid_a=CURVE_A, log=print):
    """All candidates of one power against the sets: the lightest with no failed compliance row.
    Candidates are taken in order of their W0 at 8 h (W0 only grows with L_sized), and one whose W0 at 8 h
    is not below the lightest compliant design found so far is not bisected (pruned, recorded)."""
    base = []
    for w in grid_ws:
        for a_ in grid_a:
            row = candidate_row(P, w, a_)
            got, info = close_with_retry(lambda g, w=w, a_=a_: sized_aircraft_guess(P, w, a_, L_LO, g), first_guess(P, L_LO))
            cache_[(P, w, a_, round(L_LO, 6))] = (got, info)
            row["closure"].append({"L_h": L_LO, **info, "closed": got is not None})
            base.append((got[0]["design"]["W0"] if got else math.inf, w, a_, row, got))
    base.sort(key=lambda t: (t[0], t[1], t[2]))
    rows, best = [], None
    for w0_8, w, a_, row, got in base:
        if got is None:
            row["status"] = f"does not close at 8 h from the first guess or from {GUESS_RETRY} x it"
            rows.append(row)
            continue
        if best is not None and w0_8 >= best["W0_lb"]:
            row.update(status=f"pruned: W0 at 8 h {w0_8:.0f} lb is not below the lightest compliant design "
                              f"({best['W0_lb']:.0f} lb)", W0_at_8h_lb=w0_8)
            rows.append(row)
            continue
        r = evaluate_candidate_sets(P, w, a_, E_set, C_set, need, cache_)
        r["W0_at_8h_lb"] = w0_8
        rows.append(r)
        if r["ok"] and not r["failed"] and (best is None or r["W0_lb"] < best["W0_lb"]):
            best = r
        log(f"  P={P:g} W/S {w:g} A {a_:g}: " + (f"L {r['L_sized_h']:.2f} W0 {r['W0_lb']:.0f} failed {r['failed']}"
                                                 if r["ok"] else r["status"][:110]), flush=True)
    return rows, best


# ---- the two failure modes of the R5 guarantee on a built design ------------------------------------
def endurance_score(built, need):
    """Larger = worse: mission fuel at `need` hours; a member that cannot fly the mission is ignored
    (-inf): endurance mode is about the members that fly."""
    def score(th):
        f, reason = built.fuel_at(th, need - info_gap.R5_SLACK_H)
        return (-math.inf, reason) if math.isinf(f) else (f, None)
    return score


def cliff_score(built):
    """Larger = worse: the transit power ratio (> 1: cannot fly the mission)."""
    return lambda th: info_gap.transit_power_ratio(built, th)


def robustness_scan(met, h_max=info_gap.H_MAX, step=0.25, tol=info_gap.H_TOL, first=0.5):
    """Largest h with met(h) true, found by scanning h = first, first + step, ... up to h_max for the first h
    that fails and bisecting between it and the last h that held. info_gap.robustness tests h_max first;
    for endurance mode that is vacuous (every member of U(3) that could fly is gone: no member to fail),
    so the scan stops at the first failure instead. Returns (h_hat, status)."""
    lo, hi = 0.0, None                      # h = 0 is the nominal member; the scan starts at `first`
    for h in np.arange(first, h_max + 1e-9, step):
        if met(float(h)):
            lo = float(h)
        else:
            hi = float(h)
            break
    if hi is None:
        return h_max, "above h_max"
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if met(mid) else (lo, mid)
    return lo, "bracketed" if lo >= tol else "zero margin: fails at the first step above h = 0"


def mode_robustness(score, limit, variables, start_dir, pair_names):
    """h_hat of one mode (largest h with worst score <= limit over U(h)), by bisection on h with the
    corrected worst-case search; then the full search (no early stop) at h = 1 and at h_hat.
    Returns the dict and the two search results."""
    def search(h, early, start=None):
        return info_gap.coordinate_search(score, variables, h, start or info_gap.corner_theta(variables, h, start_dir),
                                          limit if early else None, pair_names=pair_names)

    h_hat, status = robustness_scan(lambda h: search(h, True)["value"] <= limit)
    w1 = search(info_gap.H_GATE, False)
    wh = w1 if h_hat == info_gap.H_GATE else search(h_hat, False) if h_hat > 0 else None
    return {"h_hat": h_hat, "status": status, "limit": limit}, w1, wh


class _Serial:
    """pool.map without a pool (one_at_a_time inside a worker process)."""
    @staticmethod
    def map(f, jobs, chunksize=1):
        return [f(j) for j in jobs]


def mode_study(design_path, need):
    """Endurance-mode and cliff-mode h_hat of the record at design_path, with the worst point of each
    at h = 1 (and at h_hat). Returns (summary dict, built, variables, pair_names, start dirs)."""
    built = info_gap.Built(str(design_path))
    _, entries = uav.load_ledger(built.ledger_path)
    variables = info_gap.uncertain_variables(entries)
    info_gap._init(str(design_path))
    oat = info_gap.one_at_a_time(_Serial(), variables, H_GATE)
    dirs_E = info_gap.directions(oat)["R5"]
    dirs_C = dict(dirs_E, **{n: -1 for n in info_gap.ENGINE_VARS})
    pairs = info_gap.pair_list(oat, "R5_hours")
    fuel_limit = built.d["fuel_lb"]
    out = {}
    for mode, score, limit, dirs in (("endurance", endurance_score(built, need), fuel_limit, dirs_E),
                                     ("cliff", cliff_score(built), 1.0, dirs_C)):
        res, w1, wh = mode_robustness(score, limit, variables, dirs, pairs)
        res["h_hat_search_evals_at_1"] = w1["n_evals"]
        for key, w in (("worst_at_h1", w1), ("worst_at_h_hat", wh)):
            if w is None:
                res[key] = None
                continue
            th = w["theta"]
            rec = {"moved": moved_of(th), "score": w["value"], "reason": w["reason"]}
            if mode == "endurance":
                h, why = built.hours_detail(th)
                rec.update(hours=h, hours_reason=why, flyable=not (why or "").startswith("mission not flyable"))
            else:
                rec.update(transit_ratio=w["value"], flyable=w["value"] <= 1.0)
            res[key] = rec
        out[mode] = res
    out["R5_guarantee_min"] = min(out["endurance"]["h_hat"], out["cliff"]["h_hat"])
    out["binding_mode"] = "endurance" if out["endurance"]["h_hat"] <= out["cliff"]["h_hat"] else "cliff"
    return out, built, variables, pairs, {"endurance": dirs_E, "cliff": dirs_C}


def violates_at_1(mode, res, need):
    w = res[mode]["worst_at_h1"]
    if mode == "endurance":
        return w["flyable"] and w["hours"] < need - info_gap.R5_SLACK_H
    return not w["flyable"]


# ---- step refinement (RS-1) --------------------------------------------------------------------------
@contextmanager
def refined_steps(factor=REFINE_FACTOR):
    """Mission sub-steps multiplied by factor in conceptual.uav, restored on exit (for the check only)."""
    old = uav.N_CRUISE_STEPS, uav.N_LOITER_STEPS
    uav.N_CRUISE_STEPS, uav.N_LOITER_STEPS = old[0] * factor, old[1] * factor
    try:
        yield uav.N_CRUISE_STEPS, uav.N_LOITER_STEPS
    finally:
        uav.N_CRUISE_STEPS, uav.N_LOITER_STEPS = old


def step_refinement(built, variables, pairs, dirs, modes, need):
    """Worst-case endurance (h = 1) and cliff ratio with the sub-steps doubled: at the recorded worst
    points, and with the worst-case search repeated from them. Flags a verdict at h = 1 that differs."""
    out = {"factor": REFINE_FACTOR, "n_cruise_steps_as_run": uav.N_CRUISE_STEPS, "n_loiter_steps_as_run": uav.N_LOITER_STEPS}
    with refined_steps() as (nc, nl):
        out["n_cruise_steps_refined"], out["n_loiter_steps_refined"] = nc, nl
        wE, wC = modes["endurance"]["worst_at_h1"], modes["cliff"]["worst_at_h1"]
        thE, thC = theta_of(wE["moved"]), theta_of(wC["moved"])
        h_rec = built.hours_detail(thE)[0]
        sE = info_gap.coordinate_search(endurance_score(built, need), variables, H_GATE, thE, None, pair_names=pairs)
        h_ref, why_ref = built.hours_detail(sE["theta"])
        r_rec, _ = info_gap.transit_power_ratio(built, thC)
        sC = info_gap.coordinate_search(cliff_score(built), variables, H_GATE, thC, None, pair_names=pairs)
        endurance = {"hours_as_run": wE["hours"], "hours_at_recorded_worst_refined": h_rec,
                     "hours_worst_refined_search": h_ref, "reason": why_ref,
                     "verdict_as_run": bool(wE["hours"] >= need - info_gap.R5_SLACK_H),
                     "verdict_refined": bool(h_ref >= need - info_gap.R5_SLACK_H),
                     "worst_moved_refined": moved_of(sE["theta"])}
        cliff = {"ratio_as_run": wC["transit_ratio"], "ratio_at_recorded_worst_refined": r_rec,
                 "ratio_worst_refined_search": sC["value"],
                 "verdict_as_run": bool(wC["transit_ratio"] <= 1.0), "verdict_refined": bool(sC["value"] <= 1.0),
                 "worst_moved_refined": moved_of(sC["theta"])}
    for m in (endurance, cliff):
        m["verdict_depends_on_refinement"] = m["verdict_as_run"] != m["verdict_refined"]
    out["endurance"], out["cliff"] = endurance, cliff
    out["any_verdict_depends_on_refinement"] = endurance["verdict_depends_on_refinement"] or cliff["verdict_depends_on_refinement"]
    return out


# ---- records ----------------------------------------------------------------------------------------
def inputs_block(note=""):
    dirty = git("status", "--porcelain")
    return {"commit": git("rev-parse", "HEAD"), "git_dirty": bool(dirty), "git_dirty_files": dirty.splitlines(),
            "seed": info_gap.SEED, "n_samples": info_gap.N_SAMPLES, "ledger": str(uav.LEDGER.relative_to(REPO)),
            "ledger_sha256": sha256(uav.LEDGER), "table_sha256": sha256(TP100_TABLE),
            "python": platform.python_version(), "numpy": np.__version__, "pyyaml": yaml.__version__,
            "weight_law": "W = 135.8 (P/241)^0.803, Raymer Table 10.3 p. 224", "note": note}


def write_record_rec(row, folder, rec):
    """write_record with the design record already in hand (no re-sizing)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "design_pusher.json").write_text(json.dumps(rec, indent=1, default=float))
    (folder / "ledger.yaml").write_text(ledger_text(row["L_sized_h"]))
    shutil.copyfile(TP100_TABLE, folder / "tp100_table.json")
    (folder / "robust_candidate.json").write_text(json.dumps(info_gap._json_safe(row), indent=1, default=float))
    return folder / "design_pusher.json"


def summary_of(row):
    keys = ("P_hp", "W_S", "A", "L_sized_h", "W0_lb", "fuel_lb", "We_lb", "engine_weight_lb", "span_ft", "power_margin",
            "failed", "status", "corner_hours", "corner_ratio")
    return {k: row.get(k) for k in keys}


def dedupe_reasons(rows):
    out = {}
    for r in rows:
        if not (r["ok"] and not r["failed"]):
            why = r["status"] if not r["ok"] else "Stage 1 compliance failed: " + ", ".join(r["failed"])
            out.setdefault(re.sub(r"[-+]?\d+(\.\d+)?", "#", why)[:140], []).append(f"W/S {r['W_S']:g} A {r['A']:g}")
    return out


# ---- one power -------------------------------------------------------------------------------------
def run_power(P, out, seeds_path=SEED_CORNERS, grid_ws=CURVE_WS, grid_a=CURVE_A, budget_min=200.0, t_start=None,
              study_processes=2):
    """Everything for one engine power; writes out/P{P}/ and returns the per-power record."""
    t0 = time.time()
    t_start = t_start or t0
    need = uav.load_ledger()[0]["r5_robust_hours"]
    E_set, C_set = seed_sets(seeds_path)
    folder = Path(out) / f"P{P:g}"
    folder.mkdir(parents=True, exist_ok=True)
    cache_, iterations, final = {}, [], None

    def log(*a, **k):
        print(f"[{time.strftime('%H:%M:%S')}]", *a, **k)

    for it in range(1, MAX_CURVE_ITER + 1):
        t_it = time.time()
        log(f"P={P:g} iteration {it}: {len(E_set)} endurance corner(s), {len(C_set)} cliff corner(s)", flush=True)
        rows, best = curve_search(P, E_set, C_set, need, cache_, grid_ws, grid_a, log=log)
        rec_it = {"iteration": it, "n_endurance_corners": len(E_set), "n_cliff_corners": len(C_set),
                  "n_candidates": len(rows), "search_s": time.time() - t_it, "candidates": rows,
                  "reasons_not_selected": dedupe_reasons(rows), "winner": summary_of(best) if best else None}
        iterations.append(rec_it)
        if best is None:
            log(f"P={P:g} iteration {it}: no compliant design satisfies both corner sets", flush=True)
            break
        rec = cache_[(P, best["W_S"], best["A"], round(best["L_sized_h"], 6))][0][2]
        ifolder = folder / f"iteration{it}"
        path = write_record_rec(best, ifolder, rec)
        modes, built, variables, pairs, dirs = mode_study(path, need)
        rec_it["modes"] = modes
        (ifolder / "modes.json").write_text(json.dumps(info_gap._json_safe(modes), indent=1, default=float))
        log(f"P={P:g} it {it}: W/S {best['W_S']:g} A {best['A']:g} L {best['L_sized_h']:.2f} W0 {best['W0_lb']:.0f} "
            f"h_E {modes['endurance']['h_hat']:.3f} h_C {modes['cliff']['h_hat']:.3f} ({time.time() - t_it:.0f} s)", flush=True)
        final = (it, best, modes, built, variables, pairs, dirs, ifolder)
        added = []
        for mode, sets, lab in (("endurance", E_set, "E"), ("cliff", C_set, "C")):
            if violates_at_1(mode, modes, need) and add_corner(sets, f"{lab}{len(sets) + 1}(P{P:g} it{it})",
                                                              modes[mode]["worst_at_h1"]["moved"]):
                added.append(mode)
        rec_it["corners_added"] = added
        rec_it["converged"] = not added
        if not added:
            break
        if (time.time() - t_start) / 60.0 > budget_min:
            rec_it["stopped_by_budget"] = True
            break
    result = {"P_hp": P, "iterations": iterations, "grid": {"W_S": list(grid_ws), "A": list(grid_a)},
              "corner_sets": {"endurance": E_set, "cliff": C_set}}
    if final is None:
        result.update(design=None, reasons=iterations[-1]["reasons_not_selected"], runtime_s=time.time() - t0)
        (folder / "power_result.json").write_text(json.dumps(info_gap._json_safe(result), indent=1, default=float))
        return result
    it, best, modes, built, variables, pairs, dirs, ifolder = final
    for f in ("design_pusher.json", "ledger.yaml", "tp100_table.json", "robust_candidate.json"):
        shutil.copyfile(ifolder / f, folder / f)
    result["converged"] = iterations[-1].get("converged", False)
    result["final_iteration"] = it
    result["design"] = summary_of(best)
    result["modes"] = modes
    # step refinement of the final design (RS-1)
    t_r = time.time()
    result["step_refinement"] = step_refinement(built, variables, pairs, dirs, modes, need)
    result["step_refinement"]["runtime_s"] = time.time() - t_r
    print(f"[{time.strftime('%H:%M:%S')}] P={P:g} step refinement: E {result['step_refinement']['endurance']['hours_worst_refined_search']:.4f} h "
          f"(as run {modes['endurance']['worst_at_h1']['hours']:.4f}), C ratio "
          f"{result['step_refinement']['cliff']['ratio_worst_refined_search']:.4f}", flush=True)
    # the full corrected study on the final design
    if (time.time() - t_start) / 60.0 <= budget_min + 60.0:
        t_s = time.time()
        ig = info_gap.study(str(folder / "design_pusher.json"), processes=study_processes)
        ig["inputs"] = inputs_block("full info_gap.study of the final design; worst-case search is the corrected one")
        (folder / "info_gap.json").write_text(json.dumps(info_gap._json_safe(ig), indent=1, default=float))
        hh = {k: v["h_hat"] for k, v in ig["h_hat"].items()}
        result["study"] = {"h_hat": hh, "R5_guarantee": hh.get("R5_guarantee"), "R7": hh["R7"], "runtime_s": time.time() - t_s,
                           "min_of_modes": modes["R5_guarantee_min"]}
        log(f"P={P:g} full study: R5g {hh.get('R5_guarantee'):.3f} (modes min {modes['R5_guarantee_min']:.3f}) R7 {hh['R7']:.3f} "
            f"({time.time() - t_s:.0f} s)", flush=True)
    else:
        result["study"] = None
        log(f"P={P:g} full study not run (time budget)", flush=True)
    (folder / "modes.json").write_text(json.dumps(info_gap._json_safe(modes), indent=1, default=float))
    result["runtime_s"] = time.time() - t0
    (folder / "power_result.json").write_text(json.dumps(info_gap._json_safe(result), indent=1, default=float))
    return result


def _run_power_job(args):
    return run_power(*args)


def curve_main(a, argv=None):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    powers = tuple(float(x) for x in a.powers.split(",")) if a.powers else CURVE_POWERS
    grid_a = tuple(float(x) for x in a.A_levels.split(",")) if a.A_levels else CURVE_A
    t0 = time.time()
    results = {}
    todo = []
    for P in powers:
        done = out / f"P{P:g}" / "power_result.json"
        if done.exists():
            results[P] = json.loads(done.read_text())
            print(f"P={P:g}: reusing {done}", flush=True)
        else:
            todo.append(P)
    budget = a.budget_min
    jobs = [(P, str(out), SEED_CORNERS, CURVE_WS, grid_a, budget, t0) for P in sorted(todo, reverse=True)]
    if jobs:
        with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("fork")) as ex:
            for P, r in zip(sorted(todo, reverse=True), ex.map(_run_power_job, jobs)):
                results[P] = r
    curve = {"inputs": inputs_block("robustness curve"), "powers": [P for P in powers],
             "grid": {"P_hp": list(powers), "W_S": list(CURVE_WS), "A": list(grid_a), "L_sized_range_h": [L_LO, L_HI],
                      "L_tol_h": L_TOL},
             "max_iterations": MAX_CURVE_ITER, "seed_corners": str(SEED_CORNERS.relative_to(REPO)),
             "seed_corners_sha256": sha256(SEED_CORNERS), "step_refinement_factor": REFINE_FACTOR,
             "per_P": {f"{P:g}": results[P] for P in powers}, "runtime_s": time.time() - t0,
             "command": "python -m measurement.robust_sizing " + " ".join(argv if argv is not None else sys.argv[1:])}
    (out / "curve.json").write_text(json.dumps(info_gap._json_safe(curve), indent=1, default=float))
    if a.report:
        rp = Path(a.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        fig = rp.parent / "figures" / rp.stem / "curve.png"
        fig.parent.mkdir(parents=True, exist_ok=True)
        c = json.loads((out / "curve.json").read_text())
        plot_curve(c, fig)
        rp.write_text(curve_report_text(c, os.path.relpath(fig, rp.parent)))
    print(f"runtime {curve['runtime_s']:.0f} s", flush=True)


# ---- plot and report from curve.json ---------------------------------------------------------------
def _num(x):
    return float(x) if isinstance(x, (int, float)) else math.nan


def curve_points(c):
    pts = []
    for P, r in c["per_P"].items():
        if not r.get("design"):
            pts.append({"P": float(P), "design": None})
            continue
        m, s = r["modes"], r.get("study")
        pts.append({"P": float(P), "design": r["design"], "hE": m["endurance"]["h_hat"], "hC": m["cliff"]["h_hat"],
                    "hR5": s["R5_guarantee"] if s else m["R5_guarantee_min"], "hmin": m["R5_guarantee_min"],
                    "hR7": s["R7"] if s else None, "binding": m["binding_mode"], "refine": r["step_refinement"],
                    "converged": r.get("converged"), "iterations": len(r["iterations"])})
    return sorted(pts, key=lambda p: p["P"])


def crossing(pts, key):
    """Powers where the curve crosses h = 1: (lowest P with h >= 1, linear-interpolated crossing between
    the last point below 1 and the next at or above it), or None."""
    ok = [p for p in pts if p.get("design") and not math.isnan(_num(p.get(key)))]
    out = []
    for a_, b in pairwise(ok):
        if (a_[key] < 1.0) != (b[key] < 1.0):
            f = (1.0 - a_[key]) / (b[key] - a_[key]) if b[key] != a_[key] else 0.0
            out.append({"between_hp": [a_["P"], b["P"]], "direction": "up" if b[key] > a_[key] else "down",
                        "P_cross_hp": a_["P"] + f * (b["P"] - a_["P"])})
    return out


def plot_curve(c, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pts = [p for p in curve_points(c) if p.get("design")]
    P = [p["P"] for p in pts]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ax.plot(P, [p["hE"] for p in pts], "o-", color="#1b6ca8", label="endurance mode")
    ax.plot(P, [p["hC"] for p in pts], "s-", color="#c0392b", label="transit-cliff mode")
    ax.plot(P, [p["hmin"] for p in pts], "k--", lw=1, label="R5 guarantee = min of the two")
    ax.axhline(1.0, color="0.4", lw=1)
    ax.text(P[0], 1.003, "h = 1 (ledger band)", color="0.3", fontsize=8, va="bottom")
    ax.set_xlabel("rated shaft power of the hypothetical engine (hp)")
    ax.set_ylabel("info-gap robustness h_hat")
    ax2 = ax.twinx()
    ax2.plot(P, [p["design"]["W0_lb"] for p in pts], ":", color="0.5", marker="^", label="W0 (right axis)")
    ax2.set_ylabel("take-off weight W0 (lb)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="best", fontsize=8)
    ax.set_title("Robustness of the 3.5 h guarantee against engine power (hypothetical TP100 scaling)")
    ax.title.set_fontsize(9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def curve_report_text(c, figure_rel):
    inp, pts = c["inputs"], curve_points(c)
    f3 = lambda x: "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.3f}"
    lines = [
        "# Task 12: robustness of the R5 guarantee against engine power", "",
        "Generated by `measurement/robust_sizing.py --curve` from `runs/task12/stage3/2026-11-23/curve/curve.json`; "
        "every number is from that run. There is no pass/fail headline: by the owner's ruling (2026-11-23) Gate B's R5 "
        "line is judged as a curve of info-gap robustness h_hat against engine power, per failure mode, and the engine "
        "is chosen from it later.", "",
        "**The engine is hypothetical.** It is the TP100 App. K table scaled in power by P/241 (same lapse, same "
        "part-power SFC curve, 5 % SFC allowance) and in weight by Raymer Table 10.3, W = 135.8 (P/241)^0.803. No "
        "turboprop with these powers and that table is known to exist; the curve says which power class to look for. "
        "The review (RS-7) names the photo-scaled TP100 curve as the main unverified assumption behind any power figure.", "",
        "## Method", "",
        "- Failure modes of the 3.5 h guarantee (`r5_robust_hours`, nominal mission 8 h): **endurance mode**, the largest h "
        "such that every member of U(h) that flies the mission gives at least 3.5 h; **transit-cliff mode**, the largest h "
        "such that every member of U(h) can fly the mission (transit power ratio, shaft power needed over available on the "
        "worst mission sub-step, at most 1; a ratio above 1 is the model's \"no speed on the leg within the engine's power\"). "
        "The R5-guarantee h_hat is the minimum of the two. Each mode's worst case uses the corrected search "
        "(coordinate sweeps, pair flips of the most influential variables and the two engine multipliers, interior scan).",
        f"- Candidates per power: W/S in {c['grid']['W_S']}, A in {c['grid']['A']}; only candidates with no failed Stage 1 "
        f"compliance row count; the lightest W0 is taken. Sized loiter L_sized in [{c['grid']['L_sized_range_h'][0]:g}, "
        f"{c['grid']['L_sized_range_h'][1]:g}] h (bisection, {c['grid']['L_tol_h']} h): the smallest L at which the built aircraft "
        "(wing area fixed, empty weight banded) flies at least 3.5 h at every endurance corner of a set and can fly the mission "
        "at every cliff corner of the set (review RS-4). \"Cannot fly\" means too heavy and moves the upper bound down.",
        f"- The sets start from the endurance and cliff corners of the 400 hp study (`{c['seed_corners']}`). After each design "
        f"its two modes are searched at h = 1; a worst point that violates and is new is added to the set and the power is "
        f"sized again (at most {c['max_iterations']} iterations per power). Iterations use the mode searches; the full "
        "`info_gap.study` runs once on the final design of each power.",
        "- First guess of the weight iteration scales with the engine and fuel (3,000 + 6 (P - 241) lb at 8 h, plus 400 lb per "
        "extra sized hour); if non-closure is raised it is retried once from 1.3 x the guess before the candidate is declared "
        "not to close (RS-5); the reason is recorded per candidate row in each `iteration*/robust_candidate.json` and "
        "`power_result.json`.",
        "- Step refinement (RS-1): for each final design the worst-case endurance and the cliff ratio at h = 1 are recomputed "
        "with the mission sub-steps doubled (cruise 10 to 20, loiter 16 to 32; `conceptual/uav.py` constants patched for the "
        "check only), at the recorded worst points and with the worst-case search repeated from them.", "",
        "## Curve", "",
        "| P (hp) | W0 (lb) | fuel (lb) | L_sized (h) | W/S | A | span (ft) | engine (lb) | power margin | endurance h | "
        "cliff h | R5 guarantee h (min) | R5 guarantee h (full study) | R7 h | binding |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in pts:
        if not p.get("design"):
            lines.append(f"| {p['P']:g} | no design | | | | | | | | | | | | | |")
            continue
        d = p["design"]
        lines.append(f"| {p['P']:g} | {d['W0_lb']:.0f} | {d['fuel_lb']:.0f} | {d['L_sized_h']:.2f} | {d['W_S']:g} | {d['A']:g} | "
                     f"{d['span_ft']:.1f} | {d['engine_weight_lb']:.0f} | {d['power_margin']:.1%} | {f3(p['hE'])} | {f3(p['hC'])} | "
                     f"{f3(p['hmin'])} | {f3(p['hR5'])} | {f3(p['hR7'])} | {p['binding']} |")
    lines += ["", f"![h_hat of each failure mode against engine power]({figure_rel})", "",
              "## Step-refined values at h = 1 (RS-1)", "",
              "| P (hp) | worst endurance at h = 1, as run (h) | refined, recorded point (h) | refined, search repeated (h) | "
              "cliff ratio at h = 1, as run | refined, search repeated | verdict at h = 1 depends on refinement |",
              "|---|---|---|---|---|---|---|"]
    for p in pts:
        if not p.get("design"):
            continue
        r = p["refine"]
        e, k = r["endurance"], r["cliff"]
        flag = []
        if e["verdict_depends_on_refinement"]:
            flag.append("endurance")
        if k["verdict_depends_on_refinement"]:
            flag.append("cliff")
        lines.append(f"| {p['P']:g} | {e['hours_as_run']:.4f} | {e['hours_at_recorded_worst_refined']:.4f} | "
                     f"{e['hours_worst_refined_search']:.4f} | {k['ratio_as_run']:.4f} | {k['ratio_worst_refined_search']:.4f} | "
                     f"{', '.join(flag) if flag else 'no'} |")
    lines += ["", "The refinement changes the worst-case endurance by the amounts above; 3.5 h at h = 1 is met when the "
              "worst-case endurance is at least 3.5 h.", "", "## Where each mode crosses h = 1", ""]
    for key, name in (("hE", "endurance mode"), ("hC", "transit-cliff mode"), ("hmin", "R5 guarantee (min)")):
        cr = crossing(pts, key)
        if not cr:
            ok = [p for p in pts if p.get("design")]
            side = "at or above 1 at every power studied" if ok and all(p[key] >= 1.0 for p in ok) else \
                "below 1 at every power studied" if ok and all(p[key] < 1.0 for p in ok) else "no clean crossing"
            lines.append(f"- {name}: {side}.")
        else:
            lines.append(f"- {name}: " + "; ".join(
                f"crosses h = 1 {x['direction']}ward between {x['between_hp'][0]:g} and {x['between_hp'][1]:g} hp "
                f"(linear interpolation {x['P_cross_hp']:.0f} hp)" for x in cr) + ".")
    lines += ["", "Margin of step error at the crossing: compare the worst-case endurance at h = 1 as run and refined in the "
              "step table (the review's four-fold refinement moved the 400 hp worst endurance from 3.508 to 3.495 h; the "
              "cliff ratio is set by the first mission sub-step and does not move with the number of sub-steps). A power at "
              "which the 'depends on refinement' column is not 'no' has a verdict at h = 1 that the model's own "
              "discretisation can flip.", "",
              "## Convergence of the corner sets", "",
              "| P (hp) | iterations | converged | corners (endurance + cliff) in the final set |", "|---|---|---|---|"]
    for p in pts:
        r = c["per_P"][f"{p['P']:g}"]
        sets = r["corner_sets"]
        lines.append(f"| {p['P']:g} | {len(r['iterations'])} | {r.get('converged', 'no design')} | "
                     f"{len(sets['endurance'])} + {len(sets['cliff'])} |")
    nd = [p for p in pts if not p.get("design")]
    if nd:
        lines += ["", "### Powers with no design", ""]
        for p in nd:
            r = c["per_P"][f"{p['P']:g}"]
            lines.append(f"- {p['P']:g} hp: no compliant candidate satisfies both corner sets. Reasons by candidate: "
                         + "; ".join(f"{k} ({len(v)})" for k, v in r["reasons"].items()))
    lines += ["", "## What the curve does not cover", "",
              "- The exclusions of the info-gap study apply to every h_hat above: " + "; ".join(
                  info_gap.EXCLUSIONS) + ". The review found that Oswald e lower by 0.03 or a 30 kt headwind removes the "
              "margin at the 400 hp corner.",
              "- R12 (ceiling) and R16 (turn at loiter) are not inside Gate B's horizon; the review found they do not hold "
              "inside U(1) at the 400 hp worst corner (ceiling power 430 hp against 400 hp rated).",
              "- The engine is the photo-scaled TP100 with weight from Raymer Table 10.3; a real engine of this class would "
              "have its own SFC curve and weight (RS-7).",
              "- Each mode's worst case is a search, not a proof (see `measurement/info_gap.py`).", "",
              "## Inputs", "",
              f"- commit {inp['commit']} (dirty tree: {inp['git_dirty']}); seed {inp['seed']}; ledger sha256 "
              f"`{inp['ledger_sha256']}`; engine table sha256 `{inp['table_sha256']}`; seed corners sha256 "
              f"`{c['seed_corners_sha256']}`.",
              f"- python {inp['python']}, numpy {inp['numpy']}, pyyaml {inp['pyyaml']}; runtime {c['runtime_s']:.0f} s.",
              f"- command: `{c['command']}`", "",
              "Records: `runs/task12/stage3/2026-11-23/curve/P<power>/` (design record, ledger copy, engine table, "
              "`info_gap.json` with an `inputs` block, `modes.json`, `power_result.json`, per-iteration folders).", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()

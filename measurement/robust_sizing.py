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
import multiprocessing as mp
import platform
import re
import shutil
import subprocess
import time
from functools import cache, lru_cache
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
    a = ap.parse_args(argv)
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


if __name__ == "__main__":
    main()

"""Info-gap study of the frozen design with the composite band acting on the build-up and an empty-weight
band (owner ruling B-2, review GB-1). The design is NOT re-sized: wing area, fuel and engine are the record's.

    python -m measurement.composite_band_study --out runs/task12/stage3/2026-11-26/composite_band_study
    python -m measurement.composite_band_study --out ... --report docs/validation/2026-11-26_task12_composite_band_study.md --report-only

Each case is a copy of the frozen record (design, engine table) with its ledger copy changed only by the
lines named below, taken from the current ledger. On each case folder the two existing studies are run
unchanged: measurement.info_gap (all horizons, worst points, sampling check) and the endurance and
transit-cliff modes of measurement.robust_sizing. Cases:

  bands_off                      the record's ledger copy as it is: must reproduce the record's horizons
  composite_saving               + composite_model saving (the current ledger's mapping)
  composite_saving_empty_weight  + composite_model saving + empty_weight_factor (the current ledger: ruling B-2)
  composite_scale                + composite_model scale (the mapping probed in review GB-1), for comparison
  composite_scale_empty_weight   + composite_model scale + empty_weight_factor, for comparison

Nothing is tuned: bands are the ledger's, seeds and tolerances are those of measurement/info_gap.py.
"""
# ruff: noqa: ISC004  (the report text is a list of adjacent string pieces, as in info_gap)
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from conceptual import uav
from measurement import info_gap, robust_sizing

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05"
TABLE = "m250_table.json"
CASES = {"bands_off": (None, False),
         "composite_saving": ("saving", False),
         "composite_saving_empty_weight": ("saving", True),
         "composite_scale": ("scale", False),
         "composite_scale_empty_weight": ("scale", True)}
RULING_CASE = "composite_saving_empty_weight"
H_HAT_KEYS = ("R5_guarantee", "R5", "R5_reserve_usable", "TO", "LD", "R7")
NEW_VARS = ("composite_factor", "empty_weight_factor")


def ledger_line(text, name):
    """The one line of a ledger text that defines `name`."""
    found = re.findall(rf"^\s*{name}:.*$", text, flags=re.MULTILINE)
    if len(found) != 1:
        raise ValueError(f"{name}: {len(found)} lines in the ledger, expected 1")
    return found[0]


def case_ledger(record_text, current_text, model, empty_weight):
    """Ledger copy of a case: the record's text with the current ledger's composite_model line (its value
    set to `model`) and, with empty_weight, its empty_weight_factor line added after composite_factor.
    model None and empty_weight False return the record's text unchanged."""
    new = []
    if model is not None:
        line = ledger_line(current_text, "composite_model")
        new.append(re.sub(r"\{value: \w+,", f"{{value: {model},", line, count=1))
    if empty_weight:
        new.append(ledger_line(current_text, "empty_weight_factor"))
    if not new:
        return record_text
    anchor = ledger_line(record_text, "composite_factor")
    return record_text.replace(anchor, "\n".join([anchor, *new]), 1)


def write_case(out, case):
    model, empty_weight = CASES[case]
    folder = Path(out) / case
    folder.mkdir(parents=True, exist_ok=True)
    for f in ("design_pusher.json", TABLE):
        shutil.copyfile(FROZEN / f, folder / f)
    (folder / "ledger.yaml").write_text(case_ledger((FROZEN / "ledger.yaml").read_text(),
                                                    uav.LEDGER.read_text(), model, empty_weight))
    return folder


def curve_at(ig, h):
    return next(c for c in ig["worst_case_curve"] if c["h"] == h)


def summarise(folder):
    """What the report quotes of one case, read back from its info_gap.json and modes.json."""
    ig = json.loads((folder / "info_gap.json").read_text())
    modes = json.loads((folder / "modes.json").read_text())["modes"]
    hh = ig["h_hat"]
    c1 = curve_at(ig, 1.0)
    oat = {r["name"]: r for r in ig["one_at_a_time"]["rows"]}
    return {
        "h_hat": {k: hh[k]["h_hat"] for k in H_HAT_KEYS if k in hh},
        "modes": {m: modes[m]["h_hat"] for m in ("endurance", "cliff")}, "binding_mode": modes["binding_mode"],
        "nominal": ig["nominal"], "w0_check": ig["w0_check"],
        "n_variables": ig["n_variables"], "n_act": ig["n_act"],
        "new_variables_inert": {n: n in ig["inert_variables"] for n in NEW_VARS if n in oat},
        "one_at_a_time_h1": {n: {k: oat[n][k] for k in ("value_at_lower", "value_at_upper", "R5_hours",
                                                           "takeoff_ft", "landing_ft")} for n in NEW_VARS if n in oat},
        "worst_at_h1": {"R5_hours": c1["R5"]["hours"], "R5_not_flyable": c1["R5"]["not_flyable"],
                        "R5_moved": c1["R5"]["moved"], "takeoff_ft": c1["TO"]["takeoff_ft"],
                        "TO_moved": c1["TO"]["moved"], "landing_ft": c1["LD"]["landing_ft"], "LD_moved": c1["LD"]["moved"]},
        "worst_case_hours_by_h": {f"{c['h']:g}": c["R5"]["hours"] for c in ig["worst_case_curve"]},
        "guarantee_worst_at_h_hat": {k: hh["R5_guarantee"]["worst_at_h_hat"][k] for k in ("h", "hours", "moved")},
        "guarantee_first_failing": ({k: hh["R5_guarantee"]["worst_at_first_failing_h"][k]
                                     for k in ("h", "hours", "not_flyable", "moved")}
                                    if "worst_at_first_failing_h" in hh["R5_guarantee"] else None),
        "takeoff_worst_at_h_hat": {k: hh["TO"]["worst_at_h_hat"][k] for k in ("h", "takeoff_ft", "moved")},
        "mode_worst_at_h1": {m: {k: modes[m]["worst_at_h1"].get(k) for k in ("moved", "hours", "transit_ratio", "flyable")}
                             for m in ("endurance", "cliff")},
        "sampling_beats_search": {k: [s["n_beating_search"] for s in hh[k]["sampling"]] for k in H_HAT_KEYS if k != "R7"},
        "info_gap_inputs": ig["inputs"], "runtime_s": ig["runtime_s"]}


def reproduction(summary):
    """The bands_off case against the frozen record: every horizon of its info_gap.json and both modes of its
    target_result.json. Differences are recorded, not judged."""
    rec = json.loads((FROZEN / "info_gap.json").read_text())["h_hat"]
    rec_modes = json.loads((FROZEN / "target_result.json").read_text())["modes"]
    rows = {k: {"record": rec[k]["h_hat"], "rerun": summary["h_hat"][k]} for k in H_HAT_KEYS}
    rows.update({f"mode_{m}": {"record": rec_modes[m]["h_hat"], "rerun": summary["modes"][m]}
                 for m in ("endurance", "cliff")})
    for r in rows.values():
        r["difference"] = r["rerun"] - r["record"]
    return {"rows": rows, "identical": all(r["difference"] == 0.0 for r in rows.values())}


def run_case(out, case, log=print):
    folder = write_case(out, case)
    design = str((folder / "design_pusher.json").relative_to(REPO))
    rel = str(folder.relative_to(REPO))
    t0 = time.time()
    info_gap.main(["--design", design, "--out", f"{rel}/info_gap.json"])
    robust_sizing.main(["--engine-as-is", "--modes", design, "--out", rel])
    s = summarise(folder)
    log(f"{case}: R5 guarantee {s['h_hat']['R5_guarantee']:.4f}, cliff {s['modes']['cliff']:.4f}, "
        f"R7 {s['h_hat']['R7']:.4f}, hours at h = 1 {s['worst_at_h1']['R5_hours']:.3f} ({time.time() - t0:.0f} s)", flush=True)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", default=",".join(CASES), help="comma-separated case names (default: all)")
    ap.add_argument("--report")
    ap.add_argument("--report-only", action="store_true", help="rewrite the report from OUT/summary.json without running")
    a = ap.parse_args(argv)
    out = (REPO / a.out).resolve()
    if not a.report_only:
        dirty = robust_sizing.git("status", "--porcelain").splitlines()
        code_dirty = info_gap.git_dirty()
        if code_dirty:
            raise SystemExit(f"uncommitted changes in conceptual, measurement or data: {code_dirty}")
        out.mkdir(parents=True, exist_ok=True)
        path = out / "summary.json"
        res = json.loads(path.read_text()) if path.exists() else {"cases": {}, "runs": []}
        run = {"command": "python -m measurement.composite_band_study " + " ".join(argv if argv is not None else sys.argv[1:]),
               "commit": info_gap.git_commit(), "code_dirty": code_dirty, "git_status_porcelain_at_start": dirty,
               "seed": info_gap.SEED, "n_samples": info_gap.N_SAMPLES,
               "frozen_record": str(FROZEN.relative_to(REPO)),
               "frozen_design_sha256": robust_sizing.sha256(FROZEN / "design_pusher.json"),
               "frozen_ledger_sha256": robust_sizing.sha256(FROZEN / "ledger.yaml"),
               "current_ledger": str(uav.LEDGER.relative_to(REPO)), "current_ledger_sha256": robust_sizing.sha256(uav.LEDGER),
               "engine_table_sha256": robust_sizing.sha256(FROZEN / TABLE), "cases": a.cases.split(",")}
        res["runs"].append(run)
        for case in run["cases"]:
            res["cases"][case] = dict(run_case(out, case), commit=run["commit"],
                                      ledger_sha256=robust_sizing.sha256(out / case / "ledger.yaml"),
                                      composite_model=CASES[case][0], empty_weight_band=CASES[case][1])
            if case == "bands_off":
                res["reproduction"] = reproduction(res["cases"][case])
            path.write_text(json.dumps(info_gap._json_safe(res), indent=1, default=float))
    if a.report:
        res = json.loads((out / "summary.json").read_text())
        Path(a.report).write_text(report_text(res, str(out.relative_to(REPO))))


# ---- report ---------------------------------------------------------------------------------------------
LABEL = {"bands_off": "new bands off (the record's ledger copy)",
         "composite_saving": "composite band, mapping `saving`",
         "composite_saving_empty_weight": "composite band `saving` + empty-weight band (ruling B-2)",
         "composite_scale": "composite band, mapping `scale` (comparison)",
         "composite_scale_empty_weight": "composite band `scale` + empty-weight band (comparison)"}


def _moved(m):
    return ", ".join(f"`{k}` {v:.4g}" for k, v in m.items())


def _changes(old, new):
    """Which variables a worst point moves differently from another one."""
    diff = [f"`{k}` {old.get(k, 'nominal')} -> {new.get(k, 'nominal')}" for k in dict(old, **new) if old.get(k) != new.get(k)]
    return "; ".join(diff) if diff else "the same variables at the same ends"


def _holds(x, limit):
    return "holds" if x >= limit else "does NOT hold"


def report_text(res, folder):
    cases = res["cases"]
    done = [c for c in CASES if c in cases]
    rep = res.get("reproduction")
    need = 3.5
    out = ["# Task 12: info-gap study of the frozen design with the composite and empty-weight bands (ruling B-2)", "",
           f"Every number below is read from `{folder}/summary.json` (extracted from each case's `info_gap.json` and "
           "`modes.json` in the same folder). Generated by `python -m measurement.composite_band_study --report-only`. "
           "The design was not re-sized.", "",
           "## What was run", "",
           "- The frozen design: `" + res["runs"][0]["frozen_record"] + "` (W/S 16, A 7, 450 shp M250-B17F; wing area, "
           "fuel and engine fixed). Each case copies it and changes only the ledger lines named.",
           "- On each case: `measurement.info_gap` (horizons, worst points, sampling check) and the endurance and "
           "transit-cliff modes of `measurement.robust_sizing --modes`, both unchanged.",
           "- Runs (commit, command):"]
    for r in res["runs"]:
        out.append(f"  - `{r['commit'][:7]}`, code tree clean: {not r['code_dirty']}, seed {r['seed']}, "
                   f"{r['n_samples']} random samples per check: `{r['command']}`")
    r0 = res["runs"][0]
    out += [f"- Frozen ledger copy sha256 `{r0['frozen_ledger_sha256']}`; current ledger sha256 "
            f"`{res['runs'][-1]['current_ledger_sha256']}`; case ledger sha256:"]
    out += [f"  - {c}: `{cases[c]['ledger_sha256']}`" for c in done]
    out += ["", "## The two bands (ledger `data/task12/ledger.yaml`; both mappings are judgements)", "",
            "- **Composite band.** `composite_factor` 0.95, band 0.90 to 1.00 (Raymer p. 14, band per the owner's Q8). Raymer's "
            "Table 15.4 (p. 408) prints one factor per weight group (wing 0.85, tails 0.83, fuselage 0.90, landing gear 0.95) "
            "and no range. `composite_model: saving` scales the weight saving 1 - f of every group by (1 - c)/(1 - 0.95): "
            "0.95 gives the printed factors, 1.00 a metal aircraft (as 1.00 does in the Table 3.1 fit), 0.90 twice the saving. "
            "`scale` (every factor times c/0.95, the probe of review GB-1) is run for comparison: at 1.00 it leaves the wing "
            "a 10.5 % saving and the gear none, so its band end is not a metal aircraft.",
            "- **Empty-weight band.** `empty_weight_factor` 1.0, band 0.95 to 1.05, a multiplier on the summed build-up. The "
            "study already moved the empty weight through the inputs of the weight equations (gust speed, avionics, "
            "fineness, thickness, gear and sponson terms: review IG-2); it had no band on the equations themselves. "
            "The +-5 % is a judgement; the ledger line gives its basis (where the statistical fits and Raymer's Table 15.2 "
            "method sit against the build-up in the frozen record, and Raymer p. 409's 5 % growth figure).",
            "- For h above 1 the composite factor stays at 1.00: the study clips a dimensionless fraction at 1 "
            "(`measurement/info_gap.uncertain_variables`). The empty-weight factor is not clipped.", ""]
    if rep:
        out += ["## Reproduction first: new bands off", "",
                "The code of this commit on the record's own ledger copy (no new lines), against the frozen record's "
                "`info_gap.json` and `target_result.json`:", "",
                "| Horizon | Record | Re-run | Difference |", "|---|---|---|---|"]
        out += [f"| {k} | {r['record']:.10g} | {r['rerun']:.10g} | {r['difference']:.3g} |" for k, r in rep["rows"].items()]
        out += ["", f"All identical: **{rep['identical']}**.", ""]
    out += ["## Horizons", "",
            "R5 guarantee: largest h at which every member of U(h) still gives 3.5 h (a member that cannot fly counts as "
            "0 h). Endurance and cliff: the two failure modes of the same guarantee. R7: the smaller of take-off and landing.", "",
            "| Case | R5 guarantee | endurance mode | cliff mode | R7 (TO / LD) | R5 8 h | acting variables |",
            "|---|---|---|---|---|---|---|"]
    for c in done:
        s = cases[c]
        h = s["h_hat"]
        out.append(f"| {LABEL[c]} | **{h['R5_guarantee']:.4f}** | {s['modes']['endurance']:.4f} | {s['modes']['cliff']:.4f} | "
                   f"{h['R7']:.4f} ({h['TO']:.4f} / {h['LD']:.4f}) | {h['R5']:.4f} | {s['n_act']} of {s['n_variables']} |")
    out += ["", "## At h = 1 (the ledger bands)", "",
            "| Case | worst hours on station | 3.5 h guarantee | worst take-off (ft) | worst landing (ft) |", "|---|---|---|---|---|"]
    for c in done:
        w = cases[c]["worst_at_h1"]
        why = f" ({w['R5_not_flyable']})" if w["R5_not_flyable"] else ""
        out.append(f"| {LABEL[c]} | {w['R5_hours']:.3f}{why} | {_holds(w['R5_hours'], need - info_gap.R5_SLACK_H)} | "
                   f"{w['takeoff_ft']:.0f} | {w['landing_ft']:.0f} |")
    out += ["", "Worst hours on station against h (worst-case search scored by hours):", "",
            "| Case | " + " | ".join(f"h {k}" for k in cases[done[0]]["worst_case_hours_by_h"]) + " |",
            "|---|" + "---|" * len(cases[done[0]]["worst_case_hours_by_h"])]
    out += [f"| {LABEL[c]} | " + " | ".join(f"{v:.3f}" for v in cases[c]["worst_case_hours_by_h"].values()) + " |" for c in done]
    out += ["", "## The new variables one at a time (h = 1, others nominal)", "",
            "| Case | variable | value | hours | take-off (ft) | landing (ft) |", "|---|---|---|---|---|---|"]
    for c in done:
        s = cases[c]
        out.append(f"| {LABEL[c]} | nominal | | {s['nominal']['R5_hours']:.3f} | {s['nominal']['takeoff_ft']:.0f} | "
                   f"{s['nominal']['landing_ft']:.0f} |")
        for n, r in s["one_at_a_time_h1"].items():
            if s["new_variables_inert"][n]:
                out.append(f"| | `{n}` | inert | | | |")
                continue
            for end in ("lower", "upper"):
                out.append(f"| | `{n}` | {r['value_at_' + end]:g} | {r['R5_hours']['at_' + end]:.3f} | "
                           f"{r['takeoff_ft']['at_' + end]:.0f} | {r['landing_ft']['at_' + end]:.0f} |")
    out += ["", "## Worst points", ""]
    for c in done:
        s = cases[c]
        g, f, w = s["guarantee_worst_at_h_hat"], s["guarantee_first_failing"], s["worst_at_h1"]
        out += [f"**{LABEL[c]}**", "",
                f"- R5 at h = 1: {w['R5_hours']:.3f} h; moved: {_moved(w['R5_moved'])}.",
                *([f"  - Against the bands-off worst point at h = 1: {_changes(cases['bands_off']['worst_at_h1']['R5_moved'], w['R5_moved'])}."]
                  if c != "bands_off" and "bands_off" in cases else []),
                f"- R5 guarantee at its horizon h = {g['h']:.4f}: {g['hours']:.3f} h; moved: {_moved(g['moved'])}."]
        if f:
            out.append(f"- First failing h = {f['h']:.4f}: {f['hours']:.3f} h"
                       + (f" ({f['not_flyable']})" if f["not_flyable"] else "") + f"; moved: {_moved(f['moved'])}.")
        m = s["mode_worst_at_h1"]
        t = s["takeoff_worst_at_h_hat"]
        out += [f"- Endurance mode at h = 1: {m['endurance']['hours']:.3f} h. Cliff mode at h = 1: transit power ratio "
                f"{m['cliff']['transit_ratio']:.4f} (above 1 cannot fly); moved: {_moved(m['cliff']['moved'])}.",
                f"- Take-off at its horizon h = {t['h']:.4f}: {t['takeoff_ft']:.0f} ft; moved: {_moved(t['moved'])}.",
                f"- Random sampling points beating the search (per check): {s['sampling_beats_search']}.", ""]
    plain = []
    if RULING_CASE in cases:
        s = cases[RULING_CASE]
        hg, h1 = s["h_hat"]["R5_guarantee"], s["worst_at_h1"]["R5_hours"]
        plain += ["## Plain statement for the owner", "",
                f"With both bands acting as the ledger now defines them ({LABEL[RULING_CASE]}):", "",
                f"- **h_T = 1.05 (ruling R-d) {_holds(hg, 1.05)}.** The R5 guarantee horizon is {hg:.4f}.",
                f"- **h = 1 (Gate B, spec 7.4) {_holds(hg, 1.0)} for R5.** The worst member of the ledger bands gives "
                f"{h1:.3f} h on station against the required 3.5 h.",
                f"- **R7 {_holds(s['h_hat']['R7'], 1.0)} at h = 1.** Horizon {s['h_hat']['R7']:.4f}; worst take-off at h = 1 "
                f"{s['worst_at_h1']['takeoff_ft']:.0f} ft and landing {s['worst_at_h1']['landing_ft']:.0f} ft against 2,500 ft.",
                f"- Nominal hours on station are unchanged ({s['nominal']['R5_hours']:.3f} h): both new variables are at "
                "their nominal values in the frozen design.",
                f"- The transit-cliff mode alone has horizon {s['modes']['cliff']:.4f}; the endurance mode binds.", ""]
        plain += ["By case, the R5 guarantee:", ""]
        plain += [f"- {LABEL[c]}: horizon {cases[c]['h_hat']['R5_guarantee']:.4f}; h_T 1.05 "
                f"{_holds(cases[c]['h_hat']['R5_guarantee'], 1.05)}, h = 1 {_holds(cases[c]['h_hat']['R5_guarantee'], 1.0)}."
                for c in done]
        plain += ["", "Whether to re-size is the owner's decision (ruling B-2); nothing here re-sizes.", ""]
    out[out.index("## What was run"):out.index("## What was run")] = plain
    out += ["## Limits", "",
            "- Both mappings and the +-5 % empty-weight band are judgements, stated in the ledger; the library gives no range "
            "for Table 15.4 and no accuracy for the (15.46)-(15.57) equations. The comparison cases show how far the "
            "answer depends on them.",
            "- The empty-weight multiplier acts on the summed weight only: the component list and the centre of gravity are "
            "not changed, and R13 was not re-checked at the band ends.",
            "- Each case's `modes.json` flags a dirty tree: the only entry is the untracked output folder of this run. "
            "`summary.json` records that the tree was clean when the run started.",
            "- The worst case is a search, not a proof (as in every info-gap record of this task); the random sampling "
            "counts are given above.",
            "- No re-size was run. What a design sized to h_T 1.05 with these bands would weigh is not known from this record.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    main()

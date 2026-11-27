"""Report and figures of preliminary design P2 (prelim/p2_section.py), from the record alone.

report_text(out) returns the Markdown of docs/validation/<date>_task12_pd_p2.md; write_figures(out, folder) draws
the figures it links. Both read OUT/p2.json. No number is typed here: each is formatted from a record field, and
a sentence that states a finding is chosen by the record's own values.
"""
import json
from pathlib import Path

from prelim import p2_section as p2

REPO = p2.REPO
FIGURE_LABEL = ("points: a third party's digitization of NACA Report 824, page 142, checked against the report's figure; "
                "lines: XFOIL, computed, no verdict rests on them")
REFLY_NAMES = (("record", "r0: the ledger's section value"),
               ("measured", "measured value at the Reynolds number nearest the stall"),
               ("measured_minus_two_scatter", "measured value minus twice the reading scatter"),
               ("interpolated_at_stall_reynolds", "measured, interpolated in ln(Re) to the stall Reynolds number"),
               ("band_low_end", "low end of the ledger band"))


def n(x, nd=1):
    """A number with thousands separators and nd decimals; text and None pass through."""
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        return f"{x:,.{nd}f}"
    return str(x)


def mil(reynolds):
    """A Reynolds number in millions with two decimals."""
    return f"{reynolds / 1e6:.2f}"


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows] + [""]


def rel(path):
    return str(Path(path).relative_to(REPO))


# ---- figures ------------------------------------------------------------------------------------------------
def write_figures(out, folder):
    """lift.png, polar.png and moment.png of the NACA 4415, with a sidecar figures.json."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out, folder = Path(out), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    res = p2.load(out / "p2.json")
    polars = [p for p in res["xfoil"].get("polars", []) if p["section"] == p2.WING_SECTION]
    marks = {1: "o", 2: "s", 3: "^", 4: "x"}
    plots = (("lift.png", "lift", "angle of attack (deg)", "section lift coefficient", ("alpha_deg", "cl")),
             ("polar.png", "drag", "section lift coefficient", "section drag coefficient", ("cl", "cd")),
             ("moment.png", "moment", "angle of attack (deg)", "moment coefficient about the quarter chord", ("alpha_deg", "cm")))
    for name, key, xlabel, ylabel, (xk, yk) in plots:
        fig, ax = plt.subplots(figsize=(7.5, 5.0))
        for s in res["measured"]:
            if s[key]:
                ax.plot([q[0] for q in s[key]], [q[1] for q in s[key]], marks[s["set"]], ms=5, mfc="none",
                        label=f"digitized, Re {mil(s['reynolds'])}e6, {s['surface']}")
        for i, q in enumerate(polars):
            ax.plot([r[xk] for r in q["rows"]], [r[yk] for r in q["rows"]], "-", lw=0.9, color=f"C{i}",
                    label=f"XFOIL, Re {mil(q['reynolds'])}e6, free transition")
        if key == "lift":
            for v in p2.CL_MAX_BAND:
                ax.axhline(v, color="0.6", ls=":", lw=0.8)
            ax.axhline(0.0, color="k", lw=0.5)
        if key == "drag":
            ax.set_ylim(0.0, 0.03)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title("NACA 4415: " + FIGURE_LABEL.replace("; ", "\n"), fontsize=8)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(folder / name, dpi=130)
        plt.close(fig)
    (folder / "figures.json").write_text(json.dumps(
        {"label": FIGURE_LABEL, "made_by": "prelim/p2_report.py write_figures", "record": rel(out / "p2.json"),
         "p2_json_sha256": p2.sha256(out / "p2.json"), "figures": [p[0] for p in plots]}, indent=1))


# ---- text ---------------------------------------------------------------------------------------------------
def findings(res):
    """The findings, each chosen by the record's own values."""
    at, w, f, acc = res["section_at_stall"], res["wing"], res["refly"], {a["row"]: a for a in res["acceptance"]}
    rec, mea, low = f["record"], f["measured"], f["measured_minus_two_scatter"]
    out = []
    if acc[2]["verdict"] == "finding for r1":
        out.append(
            f"**Clean wing maximum lift is lower than r0's. Finding for r1 (P9).** The digitized NACA 4415 points give a "
            f"section maximum of {n(at['cl_max'], 3)} at Re {mil(at['reynolds'])} million, smooth (highest plotted point, at "
            f"{n(at['alpha_cl_max_deg'], 1)} deg). By (12.15) the clean wing has {n(w['measured']['clean_12_15'], 3)} against "
            f"r0's {n(w['record']['clean_12_15'], 3)}; take-off {n(w['measured']['takeoff'], 3)} against "
            f"{n(w['record']['takeoff'], 3)}, landing {n(w['measured']['landing'], 3)} against {n(w['record']['landing'], 3)}. "
            f"r0 assumed a section value of {n(res['ledger']['airfoil_cl_max'], 2)}. r0 is not changed here.")
        out.append(
            f"**R17 re-flown on the built aircraft with that value.** Every loiter sub-step sits on the 1.3 V_stall floor "
            f"(floor fraction {n(mea['loiter_floor_fraction'], 2)}), so the loiter speed rises from "
            f"{n(rec['loiter_speed_kt'], 2)} to {n(mea['loiter_speed_kt'], 2)} kt true airspeed (mean of the leg) and the "
            f"hours on station on r0's fuel fall from {n(rec['hours_on_station'], 2)} to {n(mea['hours_on_station'], 2)} h "
            f"({n(mea['hours_on_station'] - rec['hours_on_station'], 2)} h). R5 needs {n(f['need_h']['nominal_r5'], 1)} h at "
            f"nominal values: {'still met' if mea['hours_on_station'] >= f['need_h']['nominal_r5'] else 'not met'}. Clean stall "
            f"at W0, sea level: {n(mea['V_stall_clean_sl_kt'], 2)} kt against {n(rec['V_stall_clean_sl_kt'], 2)} kt (R7 allows "
            f"70 kt; the clause holds down to a clean wing value of {n(w['r7_stall_clause_floor'], 2)}). Take-off over 50 ft "
            f"{n(mea['takeoff_ft'], 0)} ft against {n(rec['takeoff_ft'], 0)} ft, landing {n(mea['landing_ft'], 0)} ft against "
            f"{n(rec['landing_ft'], 0)} ft (limit 2,500 ft).")
    else:
        out.append(f"Clean wing maximum lift by (12.15) from the measured section value is {n(w['measured']['clean_12_15'], 3)}, "
                   f"not below r0's {n(w['record']['clean_12_15'], 3)}. No finding for r1 from row 2.")
    out.append(
        f"**Reading scatter.** The digitized lift points of that set lie {n(at['reading_scatter'], 3)} (root mean square, "
        f"{at['fit']['n_points']} points) from a straight line between {n(p2.LINEAR_RANGE_DEG[0], 0)} and "
        f"{n(p2.LINEAR_RANGE_DEG[1], 0)} deg. With the section value lowered by twice that ({n(at['cl_max_minus_two_scatter'], 3)}) "
        f"the clean wing has {n(w['measured_minus_two_scatter']['clean_12_15'], 3)} and the built aircraft "
        f"{n(low['hours_on_station'], 2)} h on station at {n(low['loiter_speed_kt'], 2)} kt. "
        f"{'That is still at or above' if at['cl_max_minus_two_scatter'] >= p2.CL_MAX_BAND[0] else 'That is below'} the ledger band's low "
        f"end of {n(p2.CL_MAX_BAND[0], 1)}. This scatter is wider than the reading uncertainty of the figure check (section 4): it is mostly "
        f"the tunnel's own scatter over {at['fit']['n_points']} points. It is kept as the wider sensitivity.")
    if at["stall_reynolds_mission_altitude"] < at["lowest_tabulated_reynolds"]:
        out.append(
            f"**The loiter is flown at a lower Reynolds number than the data covers.** R17's floor is 1.3 times the stall speed at "
            f"the mission altitude. There the stall Reynolds number at the mean chord is {mil(at['stall_reynolds_mission_altitude'])} "
            f"million, below the lowest set ({mil(at['lowest_tabulated_reynolds'])} million), and the tip is lower still (section 5). "
            f"In the sets the maximum lift falls as the Reynolds number falls, so the value used here is, if anything, high for the "
            f"loiter. Nothing was extrapolated. Data at 2 million or below, or the SU2 polars after their validation row, would "
            f"close this.")
    corner, corner_m = f["corner_h1_record"], f["corner_h1_measured"]
    out.append(
        f"**The robustness study already covers this value.** The info-gap study of r0 moves the section maximum lift over "
        f"{n(p2.CL_MAX_BAND[0], 1)} to {n(p2.CL_MAX_BAND[1], 1)}, and its worst endurance point at h = 1 has it at "
        f"{n(corner['airfoil_cl_max'], 2)}: {n(corner['hours_on_station'], 2)} h there (the cell record says "
        f"{n(corner['hours_in_cell_record'], 2)} h; need {n(f['need_h']['guarantee_r5'], 1)} h). With the measured value in place "
        f"of the band's low end, the same point gives {n(corner_m['hours_on_station'], 2)} h. So the measured value moves the "
        f"nominal aircraft, not the guarantee, as long as the band stays. Whether the band is re-centred on the measurement is "
        f"for P9 and Gate C (C7).")
    out.append(
        "**Interaction with P1's findings 1 and 2 (climb at the worst endurance point).** A lower clean maximum lift raises the "
        "stall speed at the top of the climb at nominal values too. P1's climb check was not run again here; P9 runs it on r1.")
    cm = acc[3]
    out.append(
        f"**Section moment.** Mean moment coefficient about the quarter chord between {n(p2.LINEAR_RANGE_DEG[0], 0)} and "
        f"{n(p2.LINEAR_RANGE_DEG[1], 0)} deg: {n(cm['value'], 4)} ({at['cm_n_points']} points, {n(at['cm_min'], 4)} to "
        f"{n(at['cm_max'], 4)}). The ledger has {n(cm['ledger_value'], 2)} with the band {n(p2.CM0_BAND[0], 2)} to "
        f"{n(p2.CM0_BAND[1], 2)}: " + ("inside the band, so no finding by the spec's rule; the measured value is more nose-down "
                                       "than the ledger's and goes to P4's trim check and to r1 as an input."
                                       if cm["verdict"] == "pass" else "outside the band: a finding for P4's trim check."))
    fc = res["figure_check"]
    worst = max((r for r in fc["rows"] if r["quantity"] == "cl_max"), key=lambda r: abs(r["difference"]))
    used = next(r for r in fc["rows"] if r["quantity"] == "cl_max" and r["set"] == at["set"])
    out.append(
        f"**The digitized file was checked against the report's figure.** NACA Report 824 was opened (NTRS "
        f"{res['source']['report']['ntrs_id']}, printed page {res['source']['sections'][p2.WING_SECTION]['page']}). "
        f"{sum(r['agrees'] for r in fc['rows'])} of {fc['n_rows']} values agree with two readings of the figure within the reading "
        f"uncertainty (section 4). The maximum lift of the set used reads {n(used['reading_a'], 3)} and {n(used['reading_b'], 3)} on "
        f"the figure against {n(used['digitized'], 3)} digitized. The largest difference in maximum lift is "
        f"{n(worst['difference'], 3)} (set {worst['set']}; uncertainty {n(worst['uncertainty'], 3)}). "
        + ("Rows 1 to 3 are no longer provisional. " if not any(a.get("provisional") for a in res["acceptance"]) else
           "Rows marked provisional in section 2 stay so. ")
        + f"This record supersedes `{res['supersedes']}`, which was made before the report could be opened; no number of rows 1 "
          f"to 7 changed.")
    out.append(
        "**The drawn curve peaks above the highest symbol.** " + " ".join(res["source"]["figure_check"]["notes"][2].split())
        + " The rule was fixed before the figure was seen and is kept; it is the lower of the two readings of the section "
          "maximum. P9 decides which one r1 takes.")
    out.append(
        f"**No measured data for the tail section.** {res['sections']['tail_data']['reason']} The NACA 0012 rows of section 10 "
        f"are XFOIL only." if res["xfoil"]["status"] == "run" else
        f"**No measured data for the tail section.** {res['sections']['tail_data']['reason']}")
    return out


def report_text(out):
    out = Path(out)
    res = p2.load(out / "p2.json")
    i, src, at, w, f = res["inputs"], res["source"], res["section_at_stall"], res["wing"], res["refly"]
    dig, sec = src["digitization"], src["sections"][p2.WING_SECTION]
    stem = "2026-11-27_task12_pd_p2"
    T = [f"# Task 12 preliminary design P2: wing section and section data", "",
         f"Generated by `python -m prelim.p2_section --report-only` from `{rel(out / 'p2.json')}`. Every number below is read "
         f"from that file. Spec: `docs/specs/task12_preliminary_design.md`, package P2 (decisions PD-5, PD-6). Bands and "
         f"tolerances were fixed before the run; nothing was tuned. r0 (`{res['baseline']}`) was read and not changed.", "",
         f"Evidence class: **{res['evidence_class']}**.", "",
         f"This record supersedes `{res['supersedes']}` (made before NACA Report 824 could be opened; kept, see its "
         f"`SUPERSEDED.md`).", "",
         "## 1. Run", "",
         f"- Command: `{i['command']}`",
         f"- Commit `{i['commit']}`; working tree at the start: {'clean' if not i['git_dirty'] else 'DIRTY'} (the run's own "
         f"folder `{i['excluded']}` is not counted); unchanged during the run: {n(i['tree_unchanged_during_run'])}.",
         f"- Seed: none ({i['seed_note']}). python {i['python']}, numpy {i['numpy']}, pyyaml {i['pyyaml']}, matplotlib "
         f"{i['matplotlib']}." + (f" XFOIL {res['xfoil']['version']} (Debian package)." if res["xfoil"]["status"] == "run" else ""),
         "- Inputs (sha256, first 12): " + "; ".join(f"`{i['files'][k]}` {i['sha256'][k][:12]}" for k in i["files"]) + ".",
         f"- Log: `{rel(out / 'run.log')}`. Run time {n(res['runtime_s'], 0)} s.", ""]

    # 2. acceptance
    acc = {a["row"]: a for a in res["acceptance"]}
    a1, a2, a3, a4, a6 = acc[1], acc[2], acc[3], acc[4], acc[6]
    rows = [
        ["1", a1["what"], f"{n(a1['value'], 3)} at Re {mil(a1['reynolds'])} million", f"{n(a1['band'][0], 1)} to {n(a1['band'][1], 1)}"],
        ["2", a2["what"], f"{n(a2['value'], 3)} against {n(a2['record'], 2)}; built aircraft {n(a2['hours_on_station'], 2)} h on "
         f"station against {n(a2['hours_on_station_record'], 2)} h, loiter {n(a2['loiter_speed_kt'], 2)} kt against "
         f"{n(a2['loiter_speed_kt_record'], 2)} kt", "lower is a finding"],
        ["3", a3["what"], f"{n(a3['value'], 4)} (ledger {n(a3['ledger_value'], 2)})", f"{n(a3['band'][0], 2)} to {n(a3['band'][1], 2)}"],
        ["4", a4["what"], f"at Re {mil(a4['reynolds'])} million: maximum lift {n(a4['cl_max_rough'], 3)} rough against "
         f"{n(a4['cl_max_smooth_same_reynolds'], 3)} smooth; lowest drag {n(a4['cd_min_rough'], 4)} against "
         f"{n(a4['cd_min_smooth_same_reynolds'], 4)}", "-"],
        ["5", acc[5]["what"], acc[5]["reason"], "slope 5 %, lift at zero angle 0.05, maximum lift 0.10"],
        ["6", a6["what"], f"zero-lift angle {n(a6['alpha0_difference_deg'], 2)} deg from theory; slope {n(a6['slope_over_2pi'], 3)} "
         f"of 2 pi per radian", f"{n(a6['tolerance_deg'], 1)} deg; {n(a6['range'][0], 2)} to {n(a6['range'][1], 2)}"],
        ["7", acc[7]["what"], "section 10" if acc[7]["verdict"] != "not run" else acc[7]["reason"], "-"],
        ["8", acc[8]["what"], f"{acc[8]['n_agree']} of {acc[8]['n_rows']} values agree (section 4)", "a third of a symbol"]]
    T += ["## 2. Acceptance rows", "",
          "Rows 1 to 5 are the spec's. Rows 6 and 7 were added in `tests/task12_pd/test_p2_section.py` and "
          "`prelim/p2_section.py` before the first run; row 8 was added with the figure check. A verdict marked provisional "
          "rests on a digitized value that the figure check does not confirm.", ""]
    T += table(["#", "Row", "Result", "Band or tolerance", "Verdict"],
               [r + [f"**{acc[int(r[0])]['verdict']}{', provisional' if acc[int(r[0])].get('provisional') else ''}**"] for r in rows])

    T += ["## 3. Findings", ""] + [f"{k}. {text}" for k, text in enumerate(findings(res), 1)] + [""]

    # 4. source
    rp, fc, fcs = src["report"], res["figure_check"], src["figure_check"]
    T += ["## 4. Source of the section data and the figure check", "",
          f"- Report: {rp['number']}, \"{rp['title']}\", {rp['authors']}, {rp['year']}. NTRS id {rp['ntrs_id']}, {rp['url']} ; "
          f"{n(rp['pdf_bytes'], 0)} bytes, {rp['pdf_pages']} pages, sha256 `{rp['pdf_sha256']}`. The PDF is not committed. "
          f"Opened in this session: **{n(rp['opened_in_this_session'])}**. " + " ".join(rp["opened"].split()),
          "- Refused in the first pass: " + "; ".join(f"`{b['host']}` ({b['tool']}: {b['error']})" for b in rp["blocked"]) + ".",
          f"- NACA 4415: printed page **{sec['page']}** (page {sec['pdf_page']} of the PDF). Figure number: none; the figures of "
          f"the report's part V are not numbered. Caption: \"{sec['figure_caption']}\" Legend: " + " ".join(sec["figure_legend"].split()),
          f"- Reynolds numbers of the sets checked against the legend: {n(sec['reynolds_checked_against_the_figure'])}. "
          + "; ".join(f"set {s['set']}: {mil(s['reynolds'])} million, {s['surface']}" for s in res["measured"]) + ".",
          "- The points used: " + " ".join(dig["what"].split()),
          f"- Repository {dig['repository']} at commit `{dig['commit']}`, folder `{dig['folder']}` ({dig['repository_licence']}); "
          f"fetched {dig['fetched']}."]
    for name, fl in dig["files"].items():
        T.append(f"- `{name}`: {fl['url']} ; sha256 `{fl['sha256'][:16]}`; "
                 + (f"committed as `{fl['committed_as']}`" if fl["committed_as"] else "not committed (it carries a private e-mail address)")
                 + (f"; {fl['note']}" if fl.get("note") else "") + ".")
    T += [f"- Read twice: **{n(src['reading']['read_twice'])}**. " + " ".join(src["reading"]["how_read"].split()),
          "- Reading A: " + " ".join(fcs["reading_a"].split()),
          "- Reading B: " + " ".join(fcs["reading_b"].split()) + f" Tool: {fcs['tool']}.",
          "- Reading uncertainty: " + " ".join(fcs["uncertainty_rule"].split()),
          "- Overlay: " + " ".join(fcs["overlay"].split()), ""]
    nd = {"cl_max": 3, "cd_min": 5, "alpha_zero_lift_deg": 2, "slope_per_deg": 4, "cm_c4_linear_range": 4}
    names = {"cl_max": "maximum lift", "cd_min": "lowest drag", "alpha_zero_lift_deg": "zero-lift angle (deg)",
             "slope_per_deg": "lift-curve slope (1/deg)", "cm_c4_linear_range": "moment about the quarter chord"}
    T += table(["Quantity", "Set", "Digitized", "Reading A", "Reading B", "Digitized minus mean reading", "Uncertainty", "Agrees"],
               [[names[r["quantity"]], str(r["set"]), n(r["digitized"], nd[r["quantity"]]), n(r["reading_a"], nd[r["quantity"]]),
                 n(r["reading_b"], nd[r["quantity"]]), n(r["difference"], nd[r["quantity"]]), n(r["uncertainty"], nd[r["quantity"]]),
                 n(r["agrees"])] for r in fc["rows"]])
    T += [f"- {' '.join(note.split())}" for note in fcs["notes"]] + [""]

    # 5. Reynolds
    T += ["## 5. Reynolds and Mach numbers (step 1)", "",
          "From r0's planform and speeds, ISA, viscosity by Sutherland's law (`conceptual.units.isa`).", ""]
    T += table(["Condition", "Station", "True airspeed (kt)", "Altitude (ft)", "Chord (ft)", "Reynolds (million)", "Mach"],
               [[r["condition"], r["station"], n(r["V_kt"], 2), n(r["altitude_ft"], 0), n(r["chord_ft"], 3), mil(r["reynolds"]),
                 n(r["mach"], 3)] for r in res["reynolds"]])
    lowest = min(s["reynolds"] for s in res["measured"])
    below = [r for r in res["reynolds"] if r["reynolds"] < lowest]
    T += [f"The stall at sea level at the mean chord is at Re {mil(at['stall_reynolds'])} million; the nearest tabulated set is "
          f"{mil(at['reynolds'])} million. {len(below)} of the {len(res['reynolds'])} rows are below the lowest tabulated Reynolds "
          f"number ({mil(lowest)} million): " + ", ".join(f"{r['condition']} at the {r['station']}" for r in below)
          + ". Nothing is extrapolated below it; maximum lift falls with Reynolds number in the sets above, so the tip is the "
            "least covered part of the wing.", ""]

    # 6. measured
    T += ["## 6. Section data of the NACA 4415 (step 2)", "",
          "Highest and lowest lift are the highest and lowest digitized points as they are, without fairing. Slope, lift at zero "
          f"angle and zero-lift angle are a straight-line fit between {n(p2.LINEAR_RANGE_DEG[0], 0)} and {n(p2.LINEAR_RANGE_DEG[1], 0)} "
          "deg. The moment is the mean of the quarter-chord points in the same range.", ""]
    T += table(["Set", "Re (million)", "Surface", "Points", "Max lift (at deg)", "Lowest lift (at deg)", "Negative stall shown",
                "Slope (1/deg)", "Lift at 0 deg", "Zero-lift angle (deg)", "Scatter", "Moment c/4", "Lowest drag (at lift)"],
               [[str(s["set"]), mil(s["reynolds"]), s["surface"], str(s["summary"]["n_points"]),
                 f"{n(s['summary']['cl_max'], 3)} ({n(s['summary']['alpha_cl_max_deg'], 1)})",
                 f"{n(s['summary']['cl_min'], 3)} ({n(s['summary']['alpha_cl_min_deg'], 1)})",
                 n(s["summary"]["cl_min_is_a_turning_point"]), n(s["summary"]["fit"]["slope_per_deg"], 4),
                 n(s["summary"]["fit"]["cl_at_zero"], 3), n(s["summary"]["fit"]["alpha_zero_lift_deg"], 2),
                 n(s["summary"]["fit"]["rms_residual"], 3), n(s["summary"]["cm_c4_linear_range"], 4),
                 f"{n(s['summary']['cd_min'], 4)} ({n(s['summary']['cl_at_cd_min'], 2)})"] for s in res["measured"]])
    T += ["Where \"negative stall shown\" is no, the lowest point is the last one of the set and the true minimum may be lower "
          "(more negative). P5 needs the negative maximum lift: it takes the sets where it is shown.", "",
          f"![lift](figures/{stem}/lift.png)", "", f"![polar](figures/{stem}/polar.png)", "", f"![moment](figures/{stem}/moment.png)", ""]
    chk = res["digitization_check"]
    T += [f"Gross-error check (row 6): thin-airfoil theory for the 4415's mean line gives a zero-lift angle of "
          f"{n(chk['alpha0_thin_airfoil_deg'], 2)} deg; the fit of the set used is {n(chk['alpha0_difference_deg'], 2)} deg from it, and "
          f"its slope is {n(chk['slope_over_2pi'], 3)} of 2 pi per radian. This can catch a wrong file or a shifted axis. It says "
          "nothing about the maximum lift.", ""]

    # 7. wing
    T += ["## 7. Wing maximum lift (step 3)", "",
          f"Raymer (12.15), p. 270: 0.9 times the section value, quarter chord unswept. (12.16), p. 272, with Fig. 12.8: the "
          f"ratio is 0.9 at zero leading-edge sweep for every curve, and the Mach correction of Fig. 12.9 is zero at Mach 0.2 "
          f"and the stall is at Mach {n(w['stall_mach'], 3)}, so (12.16) at zero sweep equals (12.15). r0's leading edge is swept "
          f"{n(w['record']['le_sweep_deg'], 2)} deg and the section's sharpness parameter is {n(w['record']['delta_y_percent_chord'], 1)} "
          f"% chord (Table 12.1), which is the bluntest curve of Fig. 12.8. The figure is not in the library's notes and was "
          f"not read; the last column is a straight line between the two values the notes give for that curve "
          f"({n(p2.FIG_12_8_RATIO_ZERO_SWEEP, 1)} at 0 deg, about {n(p2.FIG_12_8_BLUNT_AT_60_DEG, 2)} at 60 deg). It is a "
          f"sensitivity and is not used. Flaps by (12.21), p. 278, and Table 12.2 as Stage 1.", ""]
    wing_rows = [(k, name) for k, name in REFLY_NAMES if w.get(k)]
    T += table(["Section value", "Section", "Clean (12.15)", "Clean (12.16), zero sweep", "Take-off", "Landing", "Clean, rough line at the sweep (not used)"],
               [[name, n(w[k]["section_cl_max"], 3), n(w[k]["clean_12_15"], 3), n(w[k]["clean_12_16_zero_sweep"], 3), n(w[k]["takeoff"], 3),
                 n(w[k]["landing"], 3), n(w[k]["clean_12_16_at_le_sweep_rough"], 3)] for k, name in wing_rows])
    rs = res["reynolds_sensitivity"]
    T += ["Maximum lift interpolated to the stall Reynolds number of each station (straight line in ln(Re) between the sets; "
          "n/a where the station is outside the tabulated range):", ""]
    T += table(["Condition", "Station", "Re (million)", "Section maximum lift"],
               [[r["condition"], r["station"], mil(r["reynolds"]), n(r["cl_max_interpolated"], 3)] for r in rs["by_station"]])

    # 8. refly
    T += ["## 8. R17 re-flown: the built aircraft of r0 with another maximum lift", "",
          "The aircraft is r0 as built (wing area, tanks, fuel); only the section maximum lift changes. Hours on station are the "
          "loiter time at which the mission burns r0's fuel (`measurement.info_gap.Built`, as the info-gap study). The mission "
          "holds every cruise and loiter sub-step at or above 1.3 V_stall clean at the current weight (R17).", ""]
    T += table(["Case", "Section", "Wing clean", "Hours on station", "Loiter speed, mean (kt)", "Loiter speed, fastest sub-step (kt)",
                "Loiter sub-steps on the floor", "Stall, sea level, W0 (kt)", "Take-off (ft)", "Landing (ft)"],
               [[name, n(f[k]["airfoil_cl_max"], 3), n(f[k]["CL_max"]["clean"], 3), n(f[k]["hours_on_station"], 2),
                 n(f[k]["loiter_speed_kt"], 2), n(f[k]["loiter_top_speed_kt"], 2), n(f[k]["loiter_floor_fraction"], 2),
                 n(f[k]["V_stall_clean_sl_kt"], 2), n(f[k]["takeoff_ft"], 0), n(f[k]["landing_ft"], 0)]
                for k, name in REFLY_NAMES if f.get(k)])
    T += [f"Cruise legs: the floor sets the speed on {n(f['measured']['cruise_out_floor_fraction'], 2)} of the cruise-out and "
          f"{n(f['measured']['cruise_back_floor_fraction'], 2)} of the cruise-back sub-steps with the measured value "
          f"({n(f['record']['cruise_out_floor_fraction'], 2)} and {n(f['record']['cruise_back_floor_fraction'], 2)} in r0).",
          f"Worst endurance point of r0's info-gap study at h = 1 (all its moved values): {n(f['corner_h1_record']['hours_on_station'], 2)} h "
          f"with its section value of {n(f['corner_h1_record']['airfoil_cl_max'], 2)}; {n(f['corner_h1_measured']['hours_on_station'], 2)} h "
          f"with the measured value there instead. Need {n(f['need_h']['guarantee_r5'], 1)} h.", ""]

    # 9. roughness
    ro = res["roughness"]
    T += ["## 9. Standard roughness (row 4, a sensitivity)", "",
          f"At Re {mil(ro['reynolds'])} million the rough set has a maximum lift of {n(ro['rough']['cl_max'], 3)} against "
          f"{n(ro['smooth']['cl_max'], 3)} smooth ({n(ro['rough']['cl_max'] - ro['smooth']['cl_max'], 3)}), and a lowest drag of "
          f"{n(ro['rough']['cd_min'], 4)} against {n(ro['smooth']['cd_min'], 4)}. "
          f"The rough maximum is {'below' if ro['rough']['cl_max'] < p2.CL_MAX_BAND[0] else 'inside'} the ledger band "
          f"({n(p2.CL_MAX_BAND[0], 1)} to {n(p2.CL_MAX_BAND[1], 1)}); by (12.15) it would give a clean wing value of "
          f"{n(ro['wing_clean_12_15_rough'], 3)}. The figure has no rough set at the stall Reynolds number. No verdict: "
          "the figure's legend says standard roughness; the report's definition of it was not transcribed.", ""]

    # 10. xfoil
    T += ["## 10. XFOIL, third source (row 7, PD-6)", ""]
    xf = res["xfoil"]
    if xf["status"] != "run":
        T += [f"Not run: {xf['reason']}.", ""]
    else:
        T += [f"{xf['program']} {xf['version']}; {xf['settings']}; Mach {n(xf['polars'][0]['mach'], 3)}. **{cap(xf['label'])}.** "
              "The last three columns are what the tolerances of the SU2 row (row 5) would say of XFOIL; they are shown to size "
              "the gap between a computed and the measured maximum lift, not as a verdict.", ""]
        body = []
        for q in xf["polars"]:
            s, c = q["summary"], q.get("against_measured")
            body.append([q["section"].upper().replace("NACA", "NACA "), mil(q["reynolds"]), f"{q['n_converged']} of {q['n_asked']}",
                         f"{n(s['cl_max'], 3)} ({n(s['alpha_cl_max_deg'], 0)})", n(s["cl_max_is_a_turning_point"]),
                         f"{n(s['cl_min'], 3)} ({n(s['alpha_cl_min_deg'], 0)})", n(s["fit"]["slope_per_deg"], 4),
                         n(s["fit"]["cl_at_zero"], 3), n(s["cm_c4_linear_range"], 4), n(s["cd_min"], 4),
                         "n/a" if c is None else f"{n(100.0 * c['slope_relative_difference'], 1)} %",
                         "n/a" if c is None else n(c["cl_at_zero_difference"], 3),
                         "n/a" if c is None else n(c["cl_max_difference"], 3)])
        T += table(["Section", "Re (million)", "Angles converged", "Max lift (at deg)", "Peak inside the sweep", "Lowest lift (at deg)",
                    "Slope (1/deg)", "Lift at 0 deg", "Moment c/4", "Lowest drag", "Slope against measured", "Lift at 0 deg against measured",
                    "Max lift against measured"], body)
        T += ["XFOIL's maximum lift is not a substitute for the measured one (PD-6), and its NACA 0012 rows have no measured set "
              "beside them in this package.", ""]

    # 11. SU2
    su = res["su2"]
    T += ["## 11. SU2 polars (row 5)", "",
          f"**Not run.** {cap(su['reason'])}. Case files: {su['case_files']}. Proposed queue when the notebook is started: "
          f"{len(su['queue'])} cases, NACA 4415 at Re " + " and ".join(sorted({mil(q['reynolds']) for q in su["queue"]}))
          + f" million, Mach {n(su['queue'][0]['mach'], 3)}, angles " + ", ".join(str(a) for a in p2.SU2_QUEUE_ALPHA_DEG)
          + " deg. The validation row compares them with the sets of section 6 before any SU2 polar is used.", ""]

    T += ["## 12. Tail section (NACA 0012)", "",
          f"Status: **{res['sections']['tail_data']['status']}**. {res['sections']['tail_data']['reason']} PD-5 keeps the NACA 0012 "
          "for the tails; its shape is analytic, so P3 can loft it. Its measured lift curve and maximum lift stay open for P4. "
          "Report 824 does have the NACA 0009 (printed page 132), which is not the tail section and was not transcribed.", ""]

    T += ["## 13. Assumptions made where the spec left a choice", "",
          "1. The section value for rows 1 and 2 is the smooth set at the tabulated Reynolds number nearest (by ratio) to the "
          "stall Reynolds number at the mean chord, sea level, W0. The interpolated value is reported beside it and not used.",
          "2. Maximum lift is the highest digitized point; no curve is faired through the points.",
          f"3. The section moment is the mean of the quarter-chord moment points between {n(p2.LINEAR_RANGE_DEG[0], 0)} and "
          f"{n(p2.LINEAR_RANGE_DEG[1], 0)} deg, taken as the ledger's zero-lift moment `airfoil_cm0`.",
          "4. A public third-party digitization of the report's figure is used for the points, and the values P2 uses are "
          "checked against two readings of the figure. The digitized values stay the numbers of record where they agree, "
          "because they cover every point and the readings cover eleven values.",
          "5. The digitizer's file is committed unchanged and parsed, instead of being typed into a table.",
          "6. The reading uncertainty is a third of a symbol on the 300 dpi scan. It was set when the figure was read, after "
          "the first record; it is a judgement of how well a symbol's centre can be placed.",
          "7. The split-flap set of the archive is not used: the aircraft has slotted flaps, taken from Table 12.2 as in Stage 1.",
          "8. XFOIL is run with its defaults (free transition, Ncrit 9). The Debian build stops with a floating-point exception "
          "when plotting is off, so it is run with plotting on under a virtual display (`xvfb-run`).",
          "9. No SU2 case files were written: they need a mesh and a turbulence-model choice that belong to the SU2 case spec.",
          "10. No design choice was made here, so there is no new PD entry in `docs/specs/00_decisions.md`.", ""]

    T += ["## 14. What this does not show", "",
          "- The figure check covers eleven values and an overlay of every point; it is not a second digitization of every point.",
          "- Both readings were made by the same reader in one session; reading B is by code where a symbol stands alone.",
          "- It does not give the maximum lift at the tip's Reynolds number, which is below the lowest set.",
          "- It does not give measured data for the NACA 0012.",
          "- It does not validate SU2, and XFOIL's numbers validate nothing.",
          "- It does not change r0. The wing value for r1 is P9's decision; Gate C item C7 asks that it is not above what the "
          "measured data supports.",
          "- (12.15) is itself an estimate: Raymer, p. 270, calls maximum lift the least reliable estimate of conceptual design. "
          "A measured section value does not make the wing value measured.", ""]
    return "\n".join(T)


def cap(text):
    """The text with its first letter in upper case and the rest as it is."""
    return text[0].upper() + text[1:]

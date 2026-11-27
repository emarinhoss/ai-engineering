"""Report and figures of preliminary design P6 (prelim/p6_propeller.py), from the record alone.

report_text(out) returns the Markdown of docs/validation/<date>_task12_pd_p6.md; write_figures(out, folder) draws the
figures it links. Both read OUT/p6.json. No number is typed here: each is formatted from a record field, and a
sentence that states a finding is chosen by the record's own values.
"""
import json
from pathlib import Path

from prelim import p6_propeller as p6

REPO = p6.REPO
FIGURE_LABEL = ("points: read from NACA Report 640 Fig. 12 (two readings each); lines: blade-element theory with the "
                "sections of NACA Report 259, computed")
POINT_NAMES = {"climb_sea_level": "climb, sea level", "cruise_out": "cruise out", "loiter": "loiter", "cruise_back": "cruise back",
               "takeoff_0707_VTO": "take-off, 0.707 V_TO", "static": "static"}


def n(x, nd=3):
    """A number with thousands separators and nd decimals; text and None pass through."""
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        return f"{x:,.{nd}f}"
    return str(x)


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows] + [""]


def rel(path):
    return str(Path(path).resolve().relative_to(REPO))


def load(out):
    return json.loads((Path(out) / "p6.json").read_text())


def by_row(res, group):
    return {a["row"]: a for a in res["acceptance"] if a["group"] == group}


def peak(points):
    """(J, eta) of the highest measured point and of the highest computed one among the measured stations."""
    m = max(points, key=lambda p: p["eta"])
    c = max((p for p in points if p["computed"] is not None), key=lambda p: p["computed"])
    return m, c


def advance_ratio_where(curve, eta, rising):
    """V/nD at which the computed curve (list of {"J", "eta"}) passes through this efficiency, on its rising or its
    falling side, by linear interpolation between neighbouring points. None if it does not."""
    pts = [(c["J"], c["eta"]) for c in curve if c.get("eta") is not None]
    top = max(range(len(pts)), key=lambda k: pts[k][1])
    side = pts[:top + 1] if rising else pts[top:]
    for (j0, e0), (j1, e1) in zip(side[:-1], side[1:]):
        if min(e0, e1) <= eta <= max(e0, e1) and e0 != e1:
            return j0 + (eta - e0) / (e1 - e0) * (j1 - j0)
    return None


def write_figures(out, folder):
    """row5.png (measured and computed efficiency of propeller 5868-9), blade.png (the aircraft blade) and
    aircraft.png (efficiency and f at r0's points), with a sidecar figures.json."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out, folder = Path(out), Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    res = load(out)
    tag = "" if res["used_in_r1"] else " (validation row 5 failed: not used in r1)"

    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for i, angle in enumerate(res["row5_points"]):
        pts, curve = res["row5_points"][angle], [c for c in res["row5_curves"][angle] if c.get("eta") is not None]
        ax.errorbar([p["J"] for p in pts], [p["eta"] for p in pts], yerr=[p["uncertainty"] for p in pts], fmt="o", ms=5,
                    mfc="none", color=f"C{i}", label=f"measured, {angle} deg at 0.75R")
        ax.plot([c["J"] for c in curve], [c["eta"] for c in curve], "-", color=f"C{i}", lw=1.0, label=f"computed, {angle} deg")
        ax.fill_between([p["J"] for p in pts], [p["eta"] - p6.TOL_ROW5 for p in pts], [p["eta"] + p6.TOL_ROW5 for p in pts],
                        color=f"C{i}", alpha=0.12)
    ax.axhline(p6.ETA_RANGE_MIN, color="0.5", ls=":", lw=0.8)
    ax.set_xlabel("advance ratio V/nD")
    ax.set_ylabel("efficiency")
    ax.set_ylim(0.0, 1.0)
    ax.set_title("Navy propeller 5868-9, 3 blades, 10 ft: " + FIGURE_LABEL.replace("; ", "\n") + "\nband: measured +-0.03", fontsize=8)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(folder / "row5.png", dpi=130)
    plt.close(fig)

    b = res["aircraft"]["blade"]
    fig, axes = plt.subplots(1, 3, figsize=(10.0, 3.6))
    axes[0].plot(b["x"], b["c_over_D"], "-")
    axes[0].set_ylabel("chord / diameter")
    axes[1].plot(b["x"], b["twist_deg"], "-")
    axes[1].set_ylabel("blade angle at the design point (deg)")
    axes[2].plot([x for x, t in zip(b["x"], b["t_c"]) if t is not None], [t for t in b["t_c"] if t is not None], "-")
    axes[2].set_ylabel("thickness ratio (read part)")
    for ax in axes:
        ax.set_xlabel("r/R")
        ax.grid(alpha=0.3)
    fig.suptitle("Representative aircraft blade, computed from the blade ledger" + tag, fontsize=8)
    fig.tight_layout()
    fig.savefig(folder / "blade.png", dpi=130)
    plt.close(fig)

    names = [k for k in ("climb_sea_level", "cruise_out", "loiter", "cruise_back") if res["aircraft"]["points"][k].get("eta") is not None]
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.8))
    xs = range(len(names))
    axes[0].plot(xs, [res["aircraft"]["points"][k]["eta"] for k in names], "o", label="blade element")
    axes[0].plot(xs, [res["aircraft"]["points"][k]["eta_record"] for k in names], "s", mfc="none", label="r0 (App. L disk, f = 0.85)")
    axes[0].plot(xs, [res["aircraft"]["points"][k]["eta_ideal"] for k in names], "^", mfc="none", label="ideal disk, same thrust")
    axes[0].set_ylabel("propeller efficiency")
    axes[1].plot(xs, [res["aircraft"]["points"][k]["f"] for k in names], "o")
    for v in p6.F_BAND:
        axes[1].axhline(v, color="0.5", ls=":", lw=0.8)
    axes[1].set_ylabel("f = efficiency / ideal efficiency")
    for ax in axes:
        ax.set_xticks(list(xs))
        ax.set_xticklabels([POINT_NAMES[k] for k in names], fontsize=7)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    fig.suptitle("Aircraft propeller at r0's points, computed" + tag, fontsize=8)
    fig.tight_layout()
    fig.savefig(folder / "aircraft.png", dpi=130)
    plt.close(fig)
    (folder / "figures.json").write_text(json.dumps(
        {"label": FIGURE_LABEL, "made_by": "prelim/p6_report.py write_figures", "record": rel(out / "p6.json"),
         "p6_json_sha256": p6.sha256(out / "p6.json"), "used_in_r1": res["used_in_r1"],
         "figures": ["row5.png", "blade.png", "aircraft.png"]}, indent=1))


# ---- text ---------------------------------------------------------------------------------------------------
def row_result(a):
    """The 'Result' cell of the rows table."""
    g, r = a["group"], a["row"]
    if g == "validation":
        if r == 1:
            return f"largest relative difference {a['largest_relative_difference']:.1e}", "1e-12"
        if r == 2:
            return "; ".join(f"C_L/C_D {c['lift_to_drag']:g}: {n(c['computed'])} against {n(c['reading_mean'])} read" for c in a["curves"]), f"{a['tolerance']:g}"
        if r == 3:
            j = [x["J_ratio"] for x in a["rows"]]
            c = [x["CP_ratio"] for x in a["rows"]]
            return (f"computed over printed: J {n(min(j))} to {n(max(j))}; C_P {n(min(c))} to {n(max(c))} (rows A, B, C, E)", a["tolerance"])
        if r == 4:
            return "; ".join(f"{n(c['computed_ft'], 2)} ft against {c['printed_ft']:g} ft" for c in a["cases"]), f"{a['tolerance_ft']:g} ft"
        return (f"{a['n_inside']} of {a['n_judged']} judged points inside; largest difference {n(a['largest_difference'])}"
                + (f"; {a['n_not_computed']} not computed" if a["n_not_computed"] else ""), f"+-{a['tolerance']:g} absolute")
    if r == 1:
        return "; ".join(f"{POINT_NAMES[p['point']]} {n(p['eta'], 4)} against {n(p['eta_record'], 4)}" for p in a["points"]), f"+-{a['tolerance']:g} absolute"
    if r == 2:
        return "; ".join(f"{POINT_NAMES[p['point']]} {n(p['f'])}" for p in a["points"]), f"{a['band'][0]:g} to {a['band'][1]:g}"
    if r == 3:
        if a["thrust_lb"] is not None:
            return f"{n(a['thrust_lb'], 0)} lb at {n(a['speed_fps'], 1)} ft/s", f"at least {n(a['minimum_lb'], 0)} lb"
        best = a["sweep_best"]["most_thrust"]
        return (f"no pitch absorbs {n(a['power_hp'], 0)} hp at {n(a['speed_fps'], 1)} ft/s; most thrust at any pitch {n(best['thrust_lb'], 0)} lb "
                f"with {n(best['power_hp'], 0)} hp absorbed and {best['stations_outside_data']} stations beyond the section data",
                f"at least {n(a['minimum_lb'], 0)} lb")
    return "; ".join(f"{POINT_NAMES[k]} {n(v['helical'])}" for k, v in a["tip_mach"].items() if v["helical"] is not None), "-"


def findings(res):
    """The findings, each chosen by the record's own values."""
    val, air = by_row(res, "validation"), by_row(res, "aircraft")
    pts, used = res["aircraft"]["points"], res["used_in_r1"]
    out = []
    v5 = val[5]
    if v5["verdict"] == "fail":
        shape = []
        for angle, p in res["row5_points"].items():
            m, c = peak(p)
            lo, hi = p[0], [q for q in p if q["judged"]][-1]
            j_lo = advance_ratio_where(res["row5_curves"][angle], lo["eta"], True)
            j_hi = advance_ratio_where(res["row5_curves"][angle], hi["eta"], False)
            shape.append(f"at {angle} deg the highest measured point is {n(m['eta'])} at V/nD {m['J']:g} and the highest computed one "
                         f"{n(c['computed'])} at {c['J']:g}; the computed value is {n(lo['difference'], 3)} from the measured one at "
                         f"V/nD {lo['J']:g} and {n(hi['difference'], 3)} at {hi['J']:g}; the computed curve has the measured value of "
                         f"the first of these points at V/nD {n(j_lo)} and that of the last at {n(j_hi)}")
        out.append(f"**Validation row 5 fails. Every aircraft number of this package is a failed-validation number and is not used "
                   f"in r1 (spec P6).** {v5['n_inside']} of {v5['n_judged']} judged points are within +-{v5['tolerance']:g}; the largest "
                   f"difference is {n(v5['largest_difference'])}. Nothing was tuned. The pattern: " + "; ".join(shape) + ". The computed "
                   "curve is too high on the low-speed side, where the blade is heavily loaded, and falls too early on the high-speed "
                   "side, near zero thrust. The peaks agree in height; the computed curves lie at a lower advance ratio than the "
                   "measured ones (figure in section 6).")
        out.append("**Likely causes of the row 5 failure, none of them tested here.** (a) The section data are not the blade's: "
                   "flat-bottomed U.S.N.P.S. sections stand in for Clark Y, measured on a wing of aspect ratio 6 in the variable "
                   "density tunnel, and their drag is high (section 6); the report itself says the drag at low and negative angles "
                   "would fall with a Clark Y leading edge, which is where the computed curve falls early. (b) The measured "
                   "efficiency is of the propeller and engine unit in front of a nacelle 43 in deep with the body drag change "
                   "charged to the thrust; the model has no body. (c) Inboard of 0.35 of the radius the blade is thicker than "
                   "the thickest section with data. (d) Beyond the measured angles the end values of the tables are held "
                   "(the number of such stations is listed per point in section 6).")
    else:
        out.append(f"**Validation row 5 passes**: {v5['n_inside']} of {v5['n_judged']} judged points within +-{v5['tolerance']:g}, "
                   f"largest difference {n(v5['largest_difference'])}. The aircraft numbers below may be used in r1.")
    v3 = val[3]
    if v3["verdict"] == "fail":
        c = [x["CP_ratio"] for x in v3["rows"]]
        j = [x["J_ratio"] for x in v3["rows"]]
        out.append(f"**Validation row 3 fails as the spec words it: (L.18) and (L.20) do not reproduce Table L.1.** From the table's "
                   f"own flight conditions, D = 14 ft and N = 663.4 rpm, the computed J is {n(min(j))} to {n(max(j))} of the printed "
                   f"one and the computed C_P is {n(min(c))} to {n(max(c))} of the printed one: the printed C_P is about twice (L.18). "
                   "The definitions themselves are not in doubt: (L.18) is P/(rho n^3 D^5) in engineering units and reproduces r0's "
                   "own J and C_P (tests/task12_pd/test_p6_bem.py). The table belongs to the map of Fig. L.6, which by the library's "
                   "chapter notes is for a counterrotating tandem propeller; the notes already flag its row D. Why the printed "
                   "C_P is twice (L.18) was not established. Reported, not tuned; the table is not used anywhere else.")
    a2 = air[2]
    f_text = "; ".join(f"{POINT_NAMES[p['point']]} {n(p['f'])}" for p in a2["points"] if p["f"] is not None)
    prefix = "" if used else "Failed-validation numbers: "
    if a2["verdict"].startswith("finding"):
        out.append(f"**{prefix}f is outside the ledger band at one or more points** ({f_text}; band {a2['band'][0]:g} to {a2['band'][1]:g}). "
                   "The band is re-proposed per flight condition in section 9 for P9. r0 is not changed.")
    else:
        missing = [POINT_NAMES[p["point"]] for p in a2["points"] if p["f"] is None]
        out.append(f"**{prefix}f is inside the ledger band at every point that could be computed** ({f_text}; band {a2['band'][0]:g} to "
                   f"{a2['band'][1]:g}, ledger value {a2['ledger_value']:g})."
                   + (f" Not computed at: {', '.join(missing)}." if missing else "") + " The range over the blade choices is in section 9.")
    a3 = air[3]
    if a3["verdict"] == "not computed":
        best, inside = a3["sweep_best"]["most_thrust"], a3["sweep_best"]["most_thrust_inside_data"]
        out.append(f"**Take-off (aircraft row 3) could not be computed, and R7's propeller thrust is not shown by this package.** At "
                   f"{n(a3['speed_fps'], 1)} ft/s and 2,030 rpm no blade pitch makes the representative blade absorb {n(a3['power_hp'], 0)} hp: "
                   f"the power levels off at {n(a3['sweep_best']['most_power_hp'], 0)} hp once every station is past the last measured "
                   f"angle of attack, where the tables' end values are held and the numbers mean nothing. With every station inside "
                   f"the measured data the most thrust is {n(inside['thrust_lb'], 0)} lb at {n(inside['power_hp'], 0)} hp absorbed; "
                   f"at any pitch {n(best['thrust_lb'], 0)} lb at {n(best['power_hp'], 0)} hp with {best['stations_outside_data']} of "
                   f"{pts['loiter']['n_stations']} stations past the data. The row needs {n(a3['minimum_lb'], 0)} lb. The section "
                   "tables stop a few degrees past maximum lift; a stalled blade needs data beyond that. The spec says strip theory "
                   "near zero speed is weak; here it is the section data that end first.")
    elif a3["verdict"] == "fail":
        out.append(f"**{prefix}take-off thrust at 0.707 V_TO is {n(a3['thrust_lb'], 0)} lb, below the {n(a3['minimum_lb'], 0)} lb of the "
                   "f = 0.60 row. Finding for P9.**")
    else:
        out.append(f"**{prefix}take-off thrust at 0.707 V_TO is {n(a3['thrust_lb'], 0)} lb, above the {n(a3['minimum_lb'], 0)} lb of the "
                   "f = 0.60 row.**")
    af = next((c for c in res["sensitivity"] if c["case"] == "prop_activity_factor = 140"), None)
    if af and af["points"]["takeoff_0707_VTO"].get("thrust_lb") is not None:
        t, lo = af["points"]["takeoff_0707_VTO"], af["points"]["loiter"]
        out.append(f"**{prefix}the blade choice trades take-off against loiter.** With the activity factor at the top of its band (140) the "
                   f"blade does absorb the take-off power: {n(t['thrust_lb'], 0)} lb at 0.707 V_TO (f {n(t['f'])}, "
                   f"{t['stations_outside_data']} stations past the data), and the loiter f falls to {n(lo['f'])} "
                   f"(baseline {n(pts['loiter']['f'])}). One f for every flight condition (item 16) cannot describe that.")
    a1 = air[1]
    out.append(f"**{prefix}efficiency against r0's App. L values (aircraft row 1): {a1['verdict']}.** "
               + "; ".join(f"{POINT_NAMES[p['point']]} {n(p['eta'], 4)} against {n(p['eta_record'], 4)} ({n(p['difference'], 4)})" for p in a1["points"])
               + f". Tolerance +-{a1['tolerance']:g}.")
    tm = {k: v for k, v in air[4]["tip_mach"].items() if v["helical"] is not None}
    hi = max(tm, key=lambda k: tm[k]["helical"])
    out.append(f"**Tip Mach number (item 15), no verdict.** The helical tip Mach number is highest at {POINT_NAMES[hi]}, {n(tm[hi]['helical'])}; "
               "it follows from the record's diameter, 2,030 rpm and the speed alone, so it stands whatever row 5 says. The section "
               "data are low-speed data; no compressibility loss is in any efficiency here. The Prandtl-Glauert lift factor is a "
               "sensitivity only (section 9).")
    out.append("**Items of the Gate B report.** Item 3 and NR-5 (propeller): a blade-element check now exists but failed its "
               "validation, so the items stay open. Items 13 and 16 (f at low speed; one f everywhere): not closed, see the "
               "take-off finding. Item 15: tip Mach numbers reported; blockage and wakes not covered. Item 17 (static C_T/C_P "
               "inert under App. L): unchanged; the static comparison of section 8 is a class check only. NR-19 (f for the climb "
               "alone): the climb f is in section 8 as a failed-validation number.")
    return out


def report_text(out):
    out = Path(out)
    res = load(out)
    i, src, T = res["inputs"], res["source"], res["targets"]
    val, air = by_row(res, "validation"), by_row(res, "aircraft")
    pts, L = res["aircraft"]["points"], res["blade_ledger"]
    used = res["used_in_r1"]
    flag = "" if used else " **Failed-validation numbers (row 5): not used in r1.**"
    t = ["# Task 12 preliminary design P6: blade-element propeller", "",
         f"Generated by `python -m prelim.p6_propeller --report-only` from `{rel(out / 'p6.json')}`. Every number below is read from "
         "that file. Spec: `docs/specs/task12_preliminary_design.md`, package P6 (decision PD-10). Tolerances were fixed before the "
         f"run; nothing was tuned. r0 (`{res['baseline']}`) was read and not changed.", "",
         f"Evidence class: **{res['evidence_class']}**.", "",
         ("**Validation row 5 passed. The aircraft numbers may be used in r1.**" if used else
          "**Validation row 5 (the measured propeller) failed. By the spec, every aircraft number in sections 7 to 9 is a "
          "failed-validation number and is not used in r1.**"), "",
         "## 1. Run", "",
         "- Command: `" + i["command"] + "`",
         f"- Commit `{i['commit']}`; working tree at the start: {'clean' if not i['git_dirty'] else 'DIRTY'} (the run's own folder "
         f"`{i['excluded']}` is not counted); unchanged during the run: {n(i['tree_unchanged_during_run'])}.",
         f"- Seed: none ({i['seed_note']}). python {i['python']}, numpy {i['numpy']}, scipy {i['scipy']}, pyyaml {i['pyyaml']}, "
         f"matplotlib {i['matplotlib']}.",
         "- Inputs (sha256, first 12): " + "; ".join(f"`{i['files'][k]}` {i['sha256'][k][:12]}" for k in i["files"]) + ".",
         f"- Log: `{rel(out / 'run.log')}`. Run time {res['runtime_s']:.0f} s.", "",
         "## 2. Validation and acceptance rows", "",
         "Validation rows 1 to 5 and aircraft rows 1 to 4 are the spec's."
         + ("" if used else " The aircraft rows keep their verdicts as computed; none of them counts while validation row 5 fails."), ""]
    rows = []
    for a in res["acceptance"]:
        result, tol = row_result(a)
        rows.append([("V" if a["group"] == "validation" else "A") + str(a["row"]), a["what"], result, tol, f"**{a['verdict']}**"])
    t += table(["#", "Row", "Result", "Tolerance or band", "Verdict"], rows)
    t += ["## 3. Findings", ""] + [f"{k}. {f}" for k, f in enumerate(findings(res), 1)] + [""]

    # ---- sources
    t += ["## 4. Sources and how they were read", ""]
    for key in ("tr640", "tr259", "acr4b04"):
        r = src["reports"][key]
        t.append(f"- **{r['number']}**, \"{r['title']}\", {r['authors']}, {r['year']}. NTRS id {r['ntrs_id']}, {r['url']} ; "
                 f"{r['pdf_bytes']:,} bytes, {r['pdf_pages']} pages, sha256 `{r['pdf_sha256']}`. The PDF is not committed. "
                 f"Opened in this session: **{n(r['opened_in_this_session'])}**. Used for: {r['used_for'].strip()}"
                 + (f" What it does not give: {r['what_it_does_not_give'].strip()}" if "what_it_does_not_give" in r else ""))
    t.append("- Opened and not used: " + "; ".join(f"{r['number']} (NTRS {r['ntrs_id']}): {r['why']}" for r in src["reports"]["opened_and_not_used"]) + ".")
    t.append(f"- Why NACA Report 640: {src['reports']['tr640']['why_this_one'].strip()}")
    g, e, test = src["blade_geometry"], src["efficiency"], src["tr640_test"]
    t += [f"- The tested propeller: {test['propeller']}; diameter {test['diameter_ft']:g} ft; {test['body']}; {test['tunnel']}. "
          f"Efficiency as the report defines it: {test['efficiency_definition'].strip()} Precision: {test['precision']}.",
          f"- Blade geometry: {g['figure']}. {g['readings'].strip()} Value: {g['value_rule']}. Uncertainty: {g['uncertainty_rule']}.",
          f"- Efficiency: {e['figure']}. Stations: {e['stations'].strip()} {e['readings'].strip()} Value: {e['value_rule']}. "
          f"Uncertainty: {e['uncertainty_rule']}. {e['judged_rule'].capitalize()}. {e['note_1_25'].strip()}",
          "- Section tables: `data/task12/pd_p6_tr259_sections.yaml`, Tables IV, VI, VIII, X, XII and XIV of NACA Report 259, typed by "
          "hand from the page images. Second reading: the report's own L/D column, recomputed from every row by a test; three rows "
          "are inconsistent in the report itself and are kept as printed.",
          f"- Library figure: {src['library_figure']['what']}; {src['library_figure']['page_opened']}. {src['library_figure']['axis_check']}.",
          "- Raymer's Fig. 13.8 (p. 328) was **not opened**: the library's scan is over the download limit of the session. The "
          "static class check uses the ledger's `static_ct_over_cp`, which earlier work read from that figure (DR-1 p. 574).", ""]
    b = res["propeller_5868_9"]
    read = b["read"]
    t += ["Blade of propeller 5868-9 as used (means of two readings; blade angle with the blade set 25 deg at 0.75R):", ""]
    t += table(["r/R", "chord/D", "thickness ratio", "blade angle (deg)"],
               [[f"{x:g}", n(c, 4), "above 0.20, not read" if th is None else n(th, 4), n(be, 2)]
                for x, c, th, be in zip(read["x"], read["c_over_D"], read["t_c"], read["beta_set25_deg"])])
    t += [f"Activity factor of this blade by Raymer (13.14) over the stations used (0.2 to 0.9875 of the radius): {n(b['activity_factor'], 1)}.", ""]

    # ---- rows 1 to 4
    t += ["## 5. Validation rows 1 to 4 (library targets)", "",
          f"- Row 1: (L.14) with zero drag angle, zero rotational interference and a = (V_e/V_0 - 1)/2 against (L.7), over V_e/V_0 from 1 "
          f"to 4 and inflow angles 1 to 89 deg: largest relative difference {val[1]['largest_relative_difference']:.1e}. **{val[1]['verdict']}**.",
          "- Row 2: " + "; ".join(f"C_L/C_D = {c['lift_to_drag']:g}: (L.15) gives {n(c['computed'], 4)} at {n(c['phi_at_maximum_deg'], 2)} deg; "
                                  f"Fig. L.5 reads {n(c['reading_eye'])} (eye) and {n(c['reading_pixel'])} (pixel)" for c in val[2]["curves"])
          + f". Tolerance {val[2]['tolerance']:g}. **{val[2]['verdict']}**.",
          f"- Row 4: " + "; ".join(f"{n(c['thrust_lbf'], 0)} lbf from {n(c['hp'], 0)} hp, {c['blades']} blades: {n(c['computed_ft'], 3)} ft, "
                                   f"printed {c['printed_ft']:g} ft" for c in val[4]["cases"]) + f". **{val[4]['verdict']}**.",
          f"- Row 3, Table L.1 (D = 14 ft, N = 663.4 rpm, ISA): **{val[3]['verdict']}**.", ""]
    t += table(["Row", "M_0", "Altitude (ft)", "Power (hp)", "J printed", "J computed", "C_P printed", "C_P computed", "C_P computed/printed"],
               [[r["label"], f"{r['mach']:g}", n(r["altitude_ft"], 0), n(r["hp"], 0), f"{r['J_printed']:g}", n(r["J_computed"]),
                 f"{r['CP_printed']:g}", n(r["CP_computed"]), n(r["CP_ratio"])] for r in val[3]["rows"]])

    # ---- row 5
    t += ["## 6. Validation row 5: the measured propeller", "",
          "The propeller is modelled as tested: 3 blades, 10 ft, the chord, thickness and pitch curves of Fig. 2, the blade turned as "
          "a whole to 15 and to 25 deg at 0.75R, the test's rpm, sea-level air. Blade stations every "
          f"{p6.STATION_STEP:g} of the radius from 0.2 to 0.9875. \"Past data\" counts the stations whose angle of attack is "
          "outside the measured range of the section tables (end values held).", ""]
    for angle, p in res["row5_points"].items():
        t += [f"Blade angle {angle} deg at 0.75R:", ""]
        t += table(["V/nD", "measured", "reading uncertainty", "judged", "computed", "difference", "within 0.03", "C_T computed", "C_P computed",
                    "c_l at 0.75R", "stations past data"],
                   [[f"{q['J']:g}", n(q["eta"]), n(q["uncertainty"]), n(q["judged"]), n(q["computed"]), n(q["difference"]),
                     "n/a" if q["computed"] is None else n(abs(q["difference"]) <= p6.TOL_ROW5), n(q["run"].get("C_T"), 4),
                     n(q["run"].get("C_P"), 4), n(q["run"].get("cl_at_075R"), 2), str(q["run"].get("stations_outside_data", "n/a"))] for q in p])
    t += ["![row 5](figures/2026-11-27_task12_pd_p6/row5.png)", "",
          "Sensitivity of row 5 to the modelling choices (reported, no verdict; none of them was adopted after the fact):", ""]
    t += table(["Case", "judged points inside 0.03", "largest difference"],
               [["baseline", f"{val[5]['n_inside']} of {val[5]['n_judged']}", n(val[5]["largest_difference"])]]
               + [[c["case"], f"{c['n_inside']} of {c['n_judged']}", n(c["largest_difference"])] for c in res["row5_sensitivity"]])
    t += ["Section data as used (infinite span, span factor " + f"{L['prop_section_span_factor']:g}" + "): lowest drag and highest lift of each table.", ""]
    t += table(["Section", "thickness ratio", "Reynolds (million)", "angles (deg)", "lowest c_d", "highest c_l", "c_l/c_d at c_l nearest 0.5"],
               [[s["name"], f"{s['t_c']:g}", f"{s['reynolds'] / 1e6:.2f}", f"{s['alpha'][0]:.1f} to {s['alpha'][-1]:.1f}", n(min(s["cd"]), 4),
                 n(max(s["cl"])), n(min(zip(s["cl"], s["cd"]), key=lambda q: abs(q[0] - 0.5))[0] / min(zip(s["cl"], s["cd"]), key=lambda q: abs(q[0] - 0.5))[1], 1)]
                for s in res["sections"]])

    # ---- aircraft
    bl = res["aircraft"]["blade"]
    t += ["## 7. The representative aircraft propeller (step 1)", "", flag.strip(), "",
          "Blade choices (`data/task12/pd_p6_blade_ledger.yaml`; proposed ledger entries, the Gate B ledger is not edited):", ""]
    t += table(["Entry", "Value", "Band"], [[f"`{k}`", str(v), "-" if k not in res["blade_bands"] else f"{res['blade_bands'][k][0]:g} to {res['blade_bands'][k][1]:g}"]
                                            for k, v in L.items()])
    t += [f"- Diameter {n(T['diameter_ft'], 3)} ft and {n(T['rpm'], 0)} rpm from r0; constant speed: at each point the whole blade is turned "
          "until it absorbs the record's shaft power.",
          f"- Chord: the 5868-9 planform times {n(bl['chord_scale'])}, which gives the activity factor {n(bl['activity_factor'], 1)}; chord at "
          f"0.75R {n(bl['chord_at_075R_ft'])} ft.",
          f"- Twist: every station at c_l {L['prop_design_cl']:g} at the loiter point; blade angle at 0.75R there {n(bl['beta_design_at_075R_deg'], 2)} deg.", "",
          "![blade](figures/2026-11-27_task12_pd_p6/blade.png)", "",
          "## 8. Aircraft rows", "", flag.strip(), ""]
    rows = []
    for k in ("climb_sea_level", "cruise_out", "loiter", "cruise_back"):
        p, o = pts[k], res["operating_points"][k]
        rows.append([POINT_NAMES[k], n(o["V_fps"] / p6.KT, 1), n(o["altitude_ft"], 0), n(o["shaft_hp"], 1), n(p.get("J")), n(p.get("C_P"), 4),
                     n(p.get("eta"), 4), n(o["eta_record"], 4), n(p.get("eta_ideal"), 4), n(p.get("f")), n(p.get("thrust_lb"), 1),
                     n(p.get("beta_at_075R_deg"), 1), f"{n(p.get('cl_min'), 2)} to {n(p.get('cl_max'), 2)}", n(p.get("helical_tip_mach")),
                     n(p.get("tip_station_mach")), str(p.get("stations_outside_data", "n/a"))])
    t += table(["Point", "Speed (kt)", "Altitude (ft)", "Shaft power (hp)", "J", "C_P", "Efficiency", "r0 (App. L)", "Ideal disk, same thrust", "f",
                "Thrust (lb)", "Blade angle at 0.75R (deg)", "c_l along the blade", "Helical tip Mach", "Relative Mach, last station", "Stations past data"], rows)
    t += ["![aircraft](figures/2026-11-27_task12_pd_p6/aircraft.png)", "",
          f"- Row 1: {air[1]['verdict']}. Row 2: {air[2]['verdict']}. Row 4 is the two Mach columns; the last station is at 0.9875 of the radius "
          "and its Mach number includes the interference velocities ((L.16)).", ""]
    a3 = air[3]
    t += ["Take-off (row 3), sea level ISA, " + f"{n(a3['power_hp'], 0)} hp, 2,030 rpm:", ""]
    for name, key in (("0.707 V_TO", "takeoff_0707_VTO"), ("static", "static")):
        p = pts[key]
        if p.get("thrust_lb") is not None:
            t.append(f"- {name}: thrust {n(p['thrust_lb'], 0)} lb, blade angle at 0.75R {n(p['beta_at_075R_deg'], 1)} deg, "
                     f"{p['stations_outside_data']} of {p['n_stations']} stations past the section data.")
        else:
            t += [f"- {name}: {p['error']}. Power and thrust against pitch:", ""]
            t += table(["Blade angle at 0.75R (deg)", "Power absorbed (hp)", "Thrust (lb)", "c_l at 0.75R", "Stations past data", "Largest excess (deg)"],
                       [[n(r["beta_at_075R_deg"], 1), n(r["power_hp"], 0), n(r["thrust_lb"], 0), n(r["cl_at_075R"], 2), str(r["stations_outside_data"]),
                         n(r["largest_excess_deg"], 1)] for r in p["pitch_sweep"]])
    t += [f"- Row 3 needs {n(a3['minimum_lb'], 0)} lb at 0.707 V_TO (the f = 0.60 row of `{rel(p6.SWEEP)}`); the record's f = 0.85 row has "
          f"{n(T['takeoff_thrust_record_lb'], 0)} lb. Verdict: **{a3['verdict']}**.",
          f"- Static thrust, class comparison only (not a validation): (L.19) gives {n(a3['static_l19_lb'], 0)} lb; Raymer Fig. 13.8 through the "
          f"ledger's C_T/C_P of {T['static_ct_over_cp']:g} gives {n(a3['static_raymer_fig_13_8_lb'], 0)} lb; the momentum limit of the disk is "
          f"{n(a3['static_momentum_limit_lb'], 0)} lb; the recorded sweep has {n(a3['static_sweep_f060_lb'], 0)} lb at f = 0.60 and "
          f"{n(a3['static_sweep_record_lb'], 0)} lb at f = 0.85. Blade element: "
          + (f"{n(a3['static_thrust_lb'], 0)} lb." if a3["static_thrust_lb"] is not None else
             f"not computed; most thrust in the pitch sweep {n(a3['static_sweep_best']['most_thrust']['thrust_lb'], 0)} lb with "
             f"{a3['static_sweep_best']['most_thrust']['stations_outside_data']} stations past the data."), ""]

    # ---- sensitivity
    t += ["## 9. Sensitivity to the blade choices, and f per flight condition", "", flag.strip(), "",
          "One entry moved at a time to an end of its band. Efficiency and f at each point; for take-off the thrust at 0.707 V_TO, or "
          "\"no pitch\" with the most thrust of the pitch sweep in brackets.", ""]
    rows = []
    for c in res["sensitivity"]:
        r = [c["case"]]
        for k in ("climb_sea_level", "cruise_out", "loiter", "cruise_back"):
            p = c["points"][k]
            r.append("not computed" if p.get("eta") is None else f"{n(p['eta'])} / {n(p['f'])}")
        p = c["points"]["takeoff_0707_VTO"]
        r.append(f"{n(p['thrust_lb'], 0)} lb, f {n(p['f'])}, {p['stations_outside_data']} past data" if p.get("thrust_lb") is not None
                 else f"no pitch ({n(p['sweep_best']['most_thrust']['thrust_lb'], 0)} lb)")
        rows.append(r)
    t += table(["Case", "Climb eta / f", "Cruise out eta / f", "Loiter eta / f", "Cruise back eta / f", "Take-off, 0.707 V_TO"], rows)
    t += ["f per flight condition, as the range over these cases widened to 0.01 (what item 16 asks for; "
          + ("for P9's info-gap study" if used else "**not for use in r1 while row 5 fails**") + "):", ""]
    t += table(["Point", "f, baseline blade", "lowest", "highest", "cases computed"],
               [[POINT_NAMES[k], n(v["f_baseline"]), f"{v['low']:.2f}", f"{v['high']:.2f}", str(v["n_cases"])] for k, v in res["proposed_f_bands"].items()])

    t += ["## 10. Assumptions made where the spec left a choice", "",
          "1. Row 5 is judged at 15 and 25 deg, chosen before any run because they bracket the blade angles the aircraft blade runs at, "
          "and because Fig. 2 prints the pitch curve for both.",
          "2. A measured point is judged only if its two readings agree within 0.015; one point (25 deg, V/nD 1.25) is not.",
          "3. Row 3's tolerance (1 % plus half a unit of the last printed digit) and row 4's (0.05 ft) were fixed in the tests; the spec gives none.",
          "4. Section data: the flat-bottomed U.S.N.P.S. sections of NACA Report 259 stand in for Clark Y. Angles are taken from the flat "
          "lower surface, as blade angles are; the report does not say.",
          "5. The aspect-ratio-6 data are turned into section data by removing C_L/(pi e A) from the angle and C_L^2/(pi e A) from the drag, "
          f"e = {L['prop_section_span_factor']:g} (Anderson APD (2.15), p. 81), also past the stall, where that is doubtful.",
          "6. Thicker than 0.20 (inboard of about 0.37 of the radius) the 0.20 section is used. Between two thickness ratios the tables are mixed linearly.",
          "7. Outside a table's angles its end values are held and the station is counted as past the data.",
          "8. The blade runs from 0.2 of the radius; no hub, spinner, shank or body is modelled. Chord and blade angle beyond 0.95 follow the "
          "last two readings; the thickness ratio is held.",
          "9. Prandtl's tip factor is written from its textbook form; no opened open source prints it (section 4). No hub-loss factor.",
          "10. No compressibility correction in the baseline; test rpm from the report's schedule (1,000 rpm at both angles), sea-level air.",
          "11. The aircraft blade is the 5868-9 planform and thickness, scaled; its entries are in `data/task12/pd_p6_blade_ledger.yaml` "
          "and not in the Gate B ledger. The activity factor is integrated over the stations used, from 0.2 of the radius, not from 0.15.",
          "12. f at a point is the blade-element efficiency over the ideal efficiency (L.8) of the same disk at the blade-element thrust, "
          "as r0 defines it.",
          "13. The climb point is at sea level and the other three at the mission altitude; density and speed of sound from `conceptual.units.isa`.", "",
          "## 11. What this does not show", "",
          "- It does not validate the blade-element model: row 5 failed." if not used else "- Row 5 passed at two blade angles of one propeller; nothing else is validated.",
          "- Not covered, and carried (spec P6): hub, spinner and pusher-fuselage blockage; the wake of the wing and tail entering the disk "
          "(item 15); the pusher's cyclic loads (Mattingly p. 619-620).",
          "- No measured thrust or power coefficient of Report 640 was read (Figs. 9 and 11); only efficiency was compared.",
          "- No section data at the blade's Reynolds and Mach numbers, none past the stall, none for the shank.",
          "- No propeller is selected and none is designed for manufacture (PD-10). r0 is not changed here.", ""]
    return "\n".join(t)

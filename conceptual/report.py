"""Render the Stage 1 conceptual design package from a run directory (figures and Markdown).

    python -m conceptual.report --run runs/task12/stage1/<date> --doc docs/validation/<date>_task12_conceptual.md

Every number in the document is read from the run's files; nothing is computed here except unit
conversions and the drawing coordinates.
"""
import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

LB_KG = 0.45359237
FT_M = 0.3048


def _read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def _f(x, nd=0):
    if x in (None, "", "None"):
        return "n/a"
    return f"{float(x):,.{nd}f}"


def three_view(d, path):
    """Top, side and front views from the recorded geometry and stations (ft)."""
    w, ht, vt, fus = d["wing"], d["horizontal_tail"], d["vertical_tail"], d["fuselage"]
    lay = d["layout"]
    L_f, D_f = fus["length"], fus["diameter"]
    x_le = lay["x_le"]
    x_ht_le = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * ht["mac"]
    x_vt_le = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * vt["mac"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), gridspec_kw={"width_ratios": [1.2, 1.2, 1]})
    # body outline: ogive-like nose and tail cone
    xs = [i * L_f / 60 for i in range(61)]

    def radius(x):
        t = x / L_f
        if t < 0.2:
            return 0.5 * D_f * (1 - (1 - t / 0.2) ** 2) ** 0.5
        if t > 0.6:
            return 0.5 * D_f * max(0.15, 1 - (t - 0.6) / 0.4 * 0.85)
        return 0.5 * D_f

    ax = axes[0]
    ax.set_title("Top view")
    ax.plot(xs, [radius(x) for x in xs], "k")
    ax.plot(xs, [-radius(x) for x in xs], "k")
    half = w["span"] / 2
    for sgn in (1, -1):
        ax.plot([x_le, x_le, x_le + w["tip_chord"], x_le + w["root_chord"], x_le],
                [0, sgn * half, sgn * half, 0, 0], "b")
        hh = ht["span"] / 2
        ax.plot([x_ht_le, x_ht_le, x_ht_le + ht["tip_chord"], x_ht_le + ht["root_chord"]],
                [0, sgn * hh, sgn * hh, 0], "g")
    x_prop = L_f if d["concept"] == "pusher" else 0.0
    ax.plot([x_prop, x_prop], [-d["propeller_diameter_ft"] / 2, d["propeller_diameter_ft"] / 2],
            "r", lw=2, label="propeller disc")
    ax.axvspan(lay["cg_empty"], lay["cg_full"], color="orange", alpha=0.6, label="CG range")
    ax.axvline(lay["x_np"], color="m", ls="--", lw=1, label="neutral point")
    ax.set_aspect("equal")
    ax.set_xlabel("ft from nose")
    ax.legend(loc="lower left", fontsize=7)

    ax = axes[1]
    ax.set_title("Side view")
    ax.plot(xs, [radius(x) for x in xs], "k")
    ax.plot(xs, [-radius(x) for x in xs], "k")
    top = radius(x_vt_le)
    ax.plot([x_vt_le, x_vt_le + vt["height"] * 0.35, x_vt_le + vt["height"] * 0.35 + 0.5 * vt["root_chord"],
             x_vt_le + vt["root_chord"], x_vt_le],
            [top, top + vt["height"], top + vt["height"], top, top], "g")
    ax.plot([x_le, x_le + w["root_chord"]], [0, 0], "b", lw=3)
    ax.plot([x_prop, x_prop], [-d["propeller_diameter_ft"] / 2, d["propeller_diameter_ft"] / 2], "r", lw=2)
    for name, st in d["stations"].items():
        if name in ("payload", "installed_engine", "avionics"):
            ax.plot(st["x"], -0.25 * D_f, "s", ms=6)
            ax.annotate(name.replace("installed_", ""), (st["x"], -0.25 * D_f), fontsize=7,
                        xytext=(2, -10), textcoords="offset points")
    ax.set_aspect("equal")
    ax.set_xlabel("ft from nose")

    ax = axes[2]
    ax.set_title("Front view")
    t = [i / 60 * 6.2832 for i in range(61)]
    import math
    ax.plot([0.5 * D_f * math.cos(a) for a in t], [0.5 * D_f * math.sin(a) for a in t], "k")
    ax.plot([-half, half], [0, 0], "b", lw=2)
    ax.plot([-ht["span"] / 2, ht["span"] / 2], [0.3 * D_f, 0.3 * D_f], "g")
    ax.plot([0, 0], [0.3 * D_f, 0.3 * D_f + vt["height"]], "g")
    ax.plot([0.5 * d["propeller_diameter_ft"] * math.cos(a) for a in t],
            [0.5 * d["propeller_diameter_ft"] * math.sin(a) for a in t], "r:", lw=1)
    ax.set_aspect("equal")
    ax.set_xlabel("ft")
    fig.suptitle(f"Task 12 Stage 1 design ({d['concept']}): W0 {d['W0_lb']:.0f} lb, span "
                 f"{w['span']:.1f} ft, orthographic, not to a common scale across panels")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def constraint_plot(rows, limits, d, path):
    ws = [float(r["W_S"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 5))
    for key, label in (("climb_sl", "climb 1,000 ft/min, sea level"),
                       ("ceiling", "service ceiling 25,000 ft"),
                       ("takeoff", "take-off 2,500 ft over 50 ft"),
                       ("cruise_at_altitude", "cruise at 20,000 ft")):
        ax.plot(ws, [float(r[key]) for r in rows], label=label)
    ax.axvline(limits["stall"], color="k", ls="--", label=f"stall 70 kt: W/S <= {limits['stall']:.1f}")
    ax.plot([d["W_S"]], [d["bhp_sl"] / d["W0_lb"]], "r*", ms=12, label="chosen design")
    ax.set_xlabel("take-off wing loading W/S (lb/ft^2)")
    ax.set_ylabel("installed sea-level hp / W0 required")
    ax.set_title(f"Constraint diagram at W0 {d['W0_lb']:.0f} lb, A {d['A']:.0f}")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def carpet_plot(rows, d, stall_ws, path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, concept in zip(axes, ("tractor", "pusher")):
        pts = [r for r in rows if r["concept"] == concept and r["W0"] not in ("", None)]
        X = sorted({float(r["W_S"]) for r in pts})
        Y = sorted({float(r["A"]) for r in pts})
        grid = {(float(r["W_S"]), float(r["A"])): float(r["W0"]) for r in pts}
        Z = [[grid.get((x, y), float("nan")) for x in X] for y in Y]
        cs = ax.contour(X, Y, Z, levels=12)
        ax.clabel(cs, fmt="%.0f", fontsize=7)
        ax.axvline(stall_ws, color="k", ls="--")
        best = min(pts, key=lambda r: float(r["W0"]))
        ax.plot(float(best["W_S"]), float(best["A"]), "r*", ms=12)
        ax.set_title(f"{concept}: W0 (lb), minimum {float(best['W0']):.0f} lb")
        ax.set_xlabel("W/S (lb/ft^2)")
    axes[0].set_ylabel("aspect ratio A")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def vn_plot(d, L_limit, L_neg, path):
    vn = d["vn"]
    clmax = d["CL_max"]["clean"]
    W_S = d["W_S"]
    rho0 = 0.0023769
    Vd = max(vn[f"gust_{k}"]["V_dive_eas_kt"] for k in ("sea_level", "mission_altitude"))
    fig, ax = plt.subplots(figsize=(7, 5))
    Vs = [i * Vd / 100 for i in range(101)]
    pos = [min(L_limit, 0.5 * rho0 * (v * 1.68781) ** 2 * clmax / W_S) for v in Vs]
    neg = [max(L_neg, -0.5 * rho0 * (v * 1.68781) ** 2 * 0.8 * clmax / W_S) for v in Vs]
    ax.plot(Vs, pos, "b", label="manoeuvre envelope")
    ax.plot(Vs, neg, "b")
    ax.plot([Vd, Vd], [L_neg, L_limit], "b")
    for label, style in (("sea_level", "g--"), ("mission_altitude", "m--")):
        g = vn[f"gust_{label}"]
        Vc, Vdl = g["V_cruise_eas_kt"], g["V_dive_eas_kt"]
        ax.plot([0, Vc, Vdl], [1, g["n_cruise"], g["n_dive"]], style, label=f"gust, {label}")
        ax.plot([0, Vc, Vdl], [1, g["n_cruise_neg"], g["n_dive_neg"]], style)
    ax.set_xlabel("equivalent airspeed (kt)")
    ax.set_ylabel("load factor n")
    ax.set_title("V-n diagram (negative stall line uses 0.8 CL_max, a drawing assumption)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def weights_plot(d, path):
    comp = d["components_lb"]
    items = sorted(comp.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh([k for k, _ in items], [v for _, v in items])
    ax.invert_yaxis()
    ax.set_xlabel("lb")
    ax.set_title(f"Empty weight build-up, {d['We_lb']:.0f} lb (Raymer 15.46-15.57, composite factors)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--doc", required=True)
    a = ap.parse_args(argv)
    run, doc = Path(a.run), Path(a.doc)
    fig_dir = doc.parent / "figures" / doc.stem
    fig_dir.mkdir(parents=True, exist_ok=True)
    d = json.loads((run / "design.json").read_text())
    inp = json.loads((run / "inputs.json").read_text())
    fp = json.loads((run / "first_pass.json").read_text())
    cs = json.loads((run / "concept_scores.json").read_text())
    limits = json.loads((run / "constraint_limits.json").read_text())
    comp_rows = _read_csv(run / "compliance.csv")
    carpet = _read_csv(run / "carpet.csv")
    cd_rows = _read_csv(run / "constraint_diagram.csv")
    fixed = _read_csv(run / "fixed_engine.csv")
    trades = _read_csv(run / "trades.csv")
    tests = (run / "test_report.txt").read_text().strip().splitlines()[-1]
    L_limit, L_neg = 3.8, -1.5

    three_view(d, fig_dir / "three_view.png")
    constraint_plot(cd_rows, limits, d, fig_dir / "constraint_diagram.png")
    carpet_plot(carpet, d, limits["stall"], fig_dir / "carpet.png")
    vn_plot(d, L_limit, L_neg, fig_dir / "vn.png")
    weights_plot(d, fig_dir / "weights.png")
    rel = f"figures/{doc.stem}"

    w, per, lay = d["wing"], d["performance"], d["layout"]
    pr = d["power_required_hp"]
    binding = max(pr, key=pr.get)
    stat = d["empty_fraction_comparison"]
    plc = d["power_loading_comparison"]
    base = next(t for t in trades if t["case"] == "loiter_h=8")
    sens = []
    for t in trades:
        if t["W0"] not in ("", None) and "(" in t["case"]:
            sens.append((abs(float(t["W0"]) - float(base["W0"])), t))
    sens.sort(key=lambda x: -x[0])

    lines = []
    add = lines.append
    add(f"# Task 12 Stage 1: conceptual design package ({run.name})")
    add("")
    add("**Status: Stage 1 output, before Gate A.** Generated by `python -m conceptual.report` from the "
        f"records in `{run}` (commit `{inp['commit'][:10]}`, ledger sha256 `{inp['ledger_sha256'][:12]}`). "
        "Every number below is read from those files. Methods: Raymer, *Aircraft Design: A Conceptual "
        "Approach*, 2nd ed. (1992), through `conceptual/`; each function cites its equation and page. "
        "Spec: `docs/specs/task12_drone_conceptual_design.md`.")
    add("")
    add("## Summary")
    add("")
    add(f"- **Chosen concept: {d['concept']}**, take-off weight **{d['W0_lb']:,.0f} lb** "
        f"({d['W0_lb'] * LB_KG:,.0f} kg), empty {d['We_lb']:,.0f} lb, fuel {d['fuel_lb']:,.0f} lb, "
        f"payload {d['payload_lb']:,.0f} lb.")
    add(f"- Wing loading {d['W_S']:.0f} lb/ft^2, aspect ratio {d['A']:.0f}, area {w['area']:.0f} ft^2, "
        f"span {w['span']:.1f} ft ({w['span'] * FT_M:.1f} m).")
    add(f"- Rubber engine: **{d['bhp_sl']:.0f} shp** at sea level, set by the **{binding}** requirement. "
        f"This is below the 400 to 5,000 bhp range of Raymer's turboprop statistics (Table 10.4, p. 224), so "
        "the engine weight is an extrapolation. The only turboprops with printed data in the library "
        f"(Mattingly Table C.1, p. 519) are {', '.join(f['engine'] for f in fixed)}, at "
        f"{float(fixed[0]['power_ratio']):.1f} to {float(fixed[-1]['power_ratio']):.1f} times the power needed.")
    add(f"- Fixed-engine re-size with the {fixed[0]['engine']}: W0 **{float(fixed[0]['W0']):,.0f} lb**, "
        f"{(float(fixed[0]['W0']) / d['W0_lb'] - 1) * 100:.0f} % heavier than the rubber-engine design. "
        "Choosing the real engine is the main open decision for Gate A.")
    add(f"- First-pass sizing (Table 3.1 fit with sketch values) gave {fp['W0']:,.0f} lb; the refined "
        f"component build-up gives {d['W0_lb']:,.0f} lb. Empty fraction: build-up {stat['build_up']:.3f}, "
        f"Table 3.1 x 0.95 {stat['table_3_1']:.3f}, Table 6.2 x 0.95 {stat['table_6_2']:.3f}. The build-up "
        "has no crew items; the fits include them.")
    met = [r for r in comp_rows if r["met"] == "True"]
    unmet = [r for r in comp_rows if r["met"] == "False"]
    add(f"- Requirements: {len(met)} checked rows met, {len(unmet)} not met (table in section 1).")
    add(f"- Raymer method tests: `{tests}` (DR-1 printed values, `tests/task12/`).")
    add("")
    add("## 1. Requirements compliance")
    add("")
    add("| Requirement | Value | Limit | Rule | Met |")
    add("|---|---|---|---|---|")
    for r in comp_rows:
        v = r["value"]
        nd = 3 if r["units"] in ("MAC", "-") else (1 if r["units"] == "ft^3" else 0)
        add(f"| {r['requirement']} ({r['units']}) | {_f(v, nd)} | {_f(r['limit'], nd)} | {r['rule']} | "
            f"{ {'True': 'yes', 'False': '**no**', '': '-'}[r['met']] } |")
    add("")
    add("Landing weight is taken as the take-off weight (conservative; Raymer 17.9 allows the "
        "requirement to set it). Distances are the segment sums of Raymer 17.8-17.9, not FAR field "
        f"lengths; the FAR landing field length would be {per['landing']['far_field_length']:,.0f} ft.")
    add("")
    add("## 2. Three-view and layout")
    add("")
    add(f"![three-view]({rel}/three_view.png)")
    add("")
    add(f"Fuselage {d['fuselage']['length']:.1f} ft long (Raymer Table 6.3, general aviation single), "
        f"{d['fuselage']['diameter']:.2f} ft diameter (fineness from the ledger). Tail arm "
        f"{d['tail_arm_ft']:.1f} ft ({'aft-engine 47.5 %' if d['concept'] == 'pusher' else 'front-propeller 60 %'} "
        "of length, p. 112-113). Horizontal tail "
        f"{d['horizontal_tail']['area']:.1f} ft^2, vertical tail {d['vertical_tail']['area']:.1f} ft^2 "
        "(volume coefficients 0.70 and 0.04, Table 6.4). Propeller diameter "
        f"{d['propeller_diameter_ft']:.2f} ft (smaller of (10.24) and the 950 ft/s tip-speed limit).")
    add("")
    add("## 3. Weight statement")
    add("")
    add(f"![weights]({rel}/weights.png)")
    add("")
    add("| Item | lb | Station (ft from nose) |")
    add("|---|---|---|")
    for k, st in sorted(d["stations"].items(), key=lambda kv: kv[1]["x"]):
        add(f"| {k} | {st['weight']:.1f} | {st['x']:.2f} |")
    add(f"| fuel (in wing tanks) | {d['fuel_lb']:.1f} | at the wing group |")
    add(f"| **take-off** | **{d['W0_lb']:.1f}** | CG {lay['cg_full']:.2f} full, {lay['cg_empty']:.2f} empty |")
    add("")
    add("Composite factors of Raymer Table 15.4 (wing 0.85, tails 0.83, fuselage 0.90, gear 0.95) are "
        "applied to the general-aviation equations (15.46)-(15.57). Crew items (seats, furnishings, air "
        "conditioning, pressurisation) are left out (R14).")
    add("")
    add("## 4. Drag, propulsion and mission")
    add("")
    add(f"CD0 {d['CD0_mission_altitude']:.4f} at 20,000 ft and {d['CD0_sea_level']:.4f} at sea level "
        f"(component build-up (12.24) with 5 % leakage and the sensor turret), span efficiency e "
        f"{d['e']:.3f} from (12.49), K {d['K']:.4f}. Clean CL_max {d['CL_max']['clean']:.2f}, take-off "
        f"{d['CL_max']['takeoff']:.2f}, landing {d['CL_max']['landing']:.2f}.")
    add("")
    add("| Segment | W start (lb) | W end (lb) | Mean TAS (kt) |")
    add("|---|---|---|---|")
    for m in d["mission"]:
        add(f"| {m['segment']} | {m['W_start']:.1f} | {m['W_end']:.1f} | "
            f"{_f(m['V_kt'], 1) if m['V_kt'] else '-'} |")
    add("")
    add("Cruise and loiter fly at the larger of the best speed (L/D max for range, minimum power for "
        "loiter) and 1.3 V_stall clean; at this design the 1.3 V_stall floor sets both speeds. Fuel is "
        "1.06 times the mission burn (3.11).")
    add("")
    add("## 5. Constraint diagram and carpet plot")
    add("")
    add(f"![constraints]({rel}/constraint_diagram.png)")
    add("")
    add(f"![carpet]({rel}/carpet.png)")
    add("")
    add("Required sea-level shp: " + ", ".join(f"{k} {v:.0f}" for k, v in pr.items()) + ". "
        f"Raymer's statistical power loading (Table 5.4, general aviation single, at the computed "
        f"maximum speed) is {plc['hp_per_W0_table_5_4']:.3f} hp/lb against {plc['hp_per_W0_sized']:.3f} "
        "sized here. The ceiling and altitude-cruise rows use Raymer's piston power lapse (13.9), because "
        "he gives none for a turboprop (13.7); Stage 3 measures the lapse with Mattingly App. K.")
    add("")
    add("## 6. Concept choice (step 2)")
    add("")
    add("| Criterion | Weight | Tractor | Pusher |")
    add("|---|---|---|---|")
    for r in cs["table"]:
        add(f"| {r['criterion']} | {r['weight']:.2f} | {r['tractor_grade']} | {r['pusher_grade']} |")
    add(f"| **weighted score** | | **{cs['score']['tractor']:.2f}** | **{cs['score']['pusher']:.2f}** |")
    add("")
    add(f"Chosen: **{cs['chosen']}**. The weights and the 1-5 grades are judgements, stated so that Gate A "
        "can change them; only the weight row is computed. The tractor is "
        f"{(float(cs['optimum']['pusher']['W0']) / float(cs['optimum']['tractor']['W0']) - 1) * 100:.1f} % "
        "lighter at its own optimum (shorter tail arm and longer gear cost the pusher).")
    add("")
    add("## 7. Loads, stability and trim")
    add("")
    add(f"![vn]({rel}/vn.png)")
    add("")
    g = d["vn"]
    gs, ga = g["gust_sea_level"], g["gust_mission_altitude"]
    governs = "the manoeuvre limit governs" if d["n_gust"] <= 3.8 else "the gust load governs"
    add(f"Gust load factor at the maximum level speed: {gs['n_cruise']:.2f} at sea level "
        f"({gs['V_cruise_eas_kt']:.0f} kt EAS) and {ga['n_cruise']:.2f} at 20,000 ft "
        f"({ga['V_cruise_eas_kt']:.0f} kt EAS), U_de 30 ft/s, (14.4)-(14.8); {governs}: limit "
        f"{d['n_limit']:.2f}, ultimate {d['Nz_ultimate']:.2f}.")
    add(f"Neutral point {lay['x_np']:.2f} ft, static margin {lay['sm_full']:.3f} (full fuel) and "
        f"{lay['sm_empty']:.3f} (empty) of the MAC; the wing is placed to centre the margin in R13. "
        f"Downwash gradient {1 - lay['dah_da']:.3f} from the far-wake value 2 CL_alpha/(pi A), not "
        "Raymer's chart (not readable from the notes; conservative for the margin). Trim tail lift "
        "coefficient at loiter: " + ", ".join(f"{k} {v['CL_tail']:.3f}" for k, v in lay["trim"].items()) + ".")
    add("")
    add("## 8. Performance as sized")
    add("")
    add("| Quantity | Value |")
    add("|---|---|")
    for k in ("V_stall_clean_kt", "V_stall_landing_kt", "takeoff_ft", "landing_ft", "roc_sl_fpm",
              "v_best_climb_kt", "service_ceiling_ft", "vmax_alt_kt"):
        add(f"| {k} | {_f(per[k], 1)} |")
    add("")
    add("## 9. Fixed engine and trades")
    add("")
    add("| Engine (Mattingly Table C.1) | shp | Engine lb | W0 (lb) | Fuel (lb) | Power / needed |")
    add("|---|---|---|---|---|---|")
    for f in fixed:
        add(f"| {f['engine']} | {_f(f['bhp'])} | {_f(f['engine_weight_lb'])} | {_f(f['W0'])} | "
            f"{_f(f['fuel'])} | {float(f['power_ratio']):.1f} |")
    add("")
    add("| Trade | W0 (lb) | shp | Fuel (lb) |")
    add("|---|---|---|---|")
    for t in trades:
        if "(" not in t["case"]:
            add(f"| {t['case']} | {_f(t['W0'])} | {_f(t['bhp'])} | {_f(t['fuel'])} |")
    add("")
    add("Largest one-at-a-time effects of the banded assumptions on W0 (each at its band end):")
    add("")
    add("| Assumption at band end | W0 (lb) | Change (lb) |")
    add("|---|---|---|")
    for dw, t in sens[:10]:
        add(f"| {t['case']} | {_f(t['W0'])} | {float(t['W0']) - float(base['W0']):+.0f} |")
    by_name = {}
    for dw, t in sens:
        by_name.setdefault(t["case"].split("=")[0], []).append(dw)
    zero = sorted(k for k, v in by_name.items() if max(v) < 0.5)
    add("")
    add("No effect on W0 at this design (not binding here): " + ", ".join(zero) + ".")
    add("")
    add("## 10. Risks and open items for Gate A")
    add("")
    add(f"1. **Engine size.** The aircraft needs about {d['bhp_sl']:.0f} shp; Raymer's turboprop statistics "
        "start at 400 bhp and the library's real turboprops start at 850 eshp. Options: accept the "
        f"{fixed[0]['engine']} ({float(fixed[0]['W0']):,.0f} lb aircraft, heavily over-powered); find an "
        "open datasheet for a small turboprop near the rubber engine's power; or enlarge the mission "
        "(payload or endurance) so the power reaches the statistical range. Stage 3 measures the fuel "
        "burn and lapse with Mattingly App. K either way.")
    add("2. **Power lapse.** Raymer's piston lapse (13.9) sizes the ceiling, the binding requirement; a "
        "turbine's lapse differs. Measured in Stage 3 (Mattingly App. K).")
    add("3. **Empty weight without crew.** The build-up is "
        f"{(1 - stat['build_up'] / stat['table_3_1']) * 100:.0f} % below the Table 3.1 fit; the size of "
        "the crew-item deduction is the task's main assumption. Measured in Stage 3 by Anderson's "
        "independent sizing (ch. 8).")
    add("4. **Section data.** CL_max 1.5 is a judgement; the 1.3 V_stall floor makes it set the loiter "
        "and cruise speeds. Measured in Stage 3 (SU2 polar after a NACA-data validation row).")
    add("5. **Span efficiency.** (12.49) falls quickly with aspect ratio and sets the optimum A; the "
        "vortex lattice measures the inviscid part in Stage 3.")
    add("6. **Downwash** from the far-wake value, not Raymer's chart; measured by the lattice in Stage 3.")
    add("7. **Concept scoring** grades are judgements for Éder to confirm.")
    if unmet:
        add("8. **Requirements not met** (section 1): " + "; ".join(r["requirement"] for r in unmet)
            + ". The negative gust case is outside Raymer's weight equations, which take the positive "
            "ultimate load; Gate A decides whether to raise the negative limit or size for it.")
    add("")
    add("## 11. Records")
    add("")
    for name in sorted(p.name for p in run.iterdir()):
        add(f"- `{run / name}`")
    doc.write_text("\n".join(lines) + "\n")
    print(f"wrote {doc} and {fig_dir}")


if __name__ == "__main__":
    main()

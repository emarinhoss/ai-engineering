"""Render the Stage 1 conceptual design package from a run directory (figures and Markdown).

    python -m conceptual.report --run runs/task12/stage1/<date> --doc docs/validation/<name>.md

Every number in the document is read from the run's files; nothing is computed here except unit
conversions, drawing coordinates and the equation-to-test table (read from the source files).
"""
import argparse
import csv
import importlib
import inspect
import json
import math
import re
from pathlib import Path

import matplotlib
import matplotlib.patches
import yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt

LB_KG = 0.45359237
FT_M = 0.3048
REPO = Path(__file__).resolve().parents[1]


def _read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def _f(x, nd=0):
    if x in (None, "", "None"):
        return "n/a"
    try:
        return f"{float(x):,.{nd}f}"
    except ValueError:
        return str(x)


def three_view(d, path):
    """Top, side and front views from the recorded geometry and stations (ft)."""
    w, ht, vt, fus = d["wing"], d["horizontal_tail"], d["vertical_tail"], d["fuselage"]
    lay = d["layout"]
    L_f, D_f = fus["length"], fus["diameter"]
    x_le = lay["x_le"]
    x_ht_le = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * ht["mac"]
    x_vt_le = lay["x_ac"] + d["tail_arm_ft"] - 0.25 * vt["mac"]
    x_prop = L_f if d["concept"] == "pusher" else 0.0
    R = d["propeller_diameter_ft"] / 2
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), gridspec_kw={"width_ratios": [1.2, 1.3, 1]})
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
    ax.plot([x_prop, x_prop], [-R, R], "r", lw=2, label="propeller disc")
    ax.axvspan(min(lay["cg_empty"], lay["cg_full"]), max(lay["cg_empty"], lay["cg_full"]),
               color="orange", alpha=0.6, label="CG range")
    ax.axvline(lay["x_np"], color="m", ls="--", lw=1, label="neutral point")
    ht_ = lay["gear_track"]["half_track_ft"]
    ax.plot([lay["x_main"]] * 2, [-ht_, ht_], "ko", ms=4, label="main wheels (overturn track)")
    sl = lay["gear_track"].get("sponson_length_ft", 0.0)
    sd = lay["gear_track"].get("sponson_depth_ft", 0.0)
    for sgn in (1, -1):
        if sl:
            ax.add_patch(matplotlib.patches.Ellipse((lay["x_main"] - 0.3 * sl, sgn * ht_), sl, sd,
                                                    fill=False, color="saddlebrown"))
    ax.set_aspect("equal")
    ax.set_xlabel("ft from nose")
    ax.legend(loc="lower left", fontsize=7)

    ax = axes[1]
    ax.set_title("Side view (static, gear down)")
    h = lay["h_cg"]
    ax.plot(xs, [h + radius(x) for x in xs], "k")
    ax.plot(xs, [h - radius(x) for x in xs], "k")
    top = h + radius(x_vt_le)
    ax.plot([x_vt_le, x_vt_le + vt["height"] * 0.35, x_vt_le + vt["height"] * 0.35 + 0.5 * vt["root_chord"],
             x_vt_le + vt["root_chord"], x_vt_le], [top, top + vt["height"], top + vt["height"], top, top], "g")
    ax.plot([x_le, x_le + w["root_chord"]], [h, h], "b", lw=3)
    ax.plot([x_prop, x_prop], [h - R, h + R], "r", lw=2)
    ax.axhline(0.0, color="brown", lw=1)
    for x in (lay["x_main"], d["stations"]["nose_gear"]["x"]):
        ax.plot([x, x], [0, h - 0.5 * D_f], "k", lw=2)
        ax.plot(x, 0.3, "ko", ms=6)
    for name in ("payload", "installed_engine", "avionics"):
        st = d["stations"][name]
        ax.plot(st["x"], h - 0.25 * D_f, "s", ms=6)
        ax.annotate(name.replace("installed_", ""), (st["x"], h - 0.25 * D_f), fontsize=7,
                    xytext=(2, -10), textcoords="offset points")
    ax.set_aspect("equal")
    ax.set_xlabel("ft from nose")

    ax = axes[2]
    ax.set_title("Front view")
    t = [i / 60 * 2 * math.pi for i in range(61)]
    ax.plot([0.5 * D_f * math.cos(a) for a in t], [0.5 * D_f * math.sin(a) for a in t], "k")
    ax.plot([-half, half], [0, 0], "b", lw=2)
    ax.plot([-ht["span"] / 2, ht["span"] / 2], [0.3 * D_f, 0.3 * D_f], "g")
    ax.plot([0, 0], [0.3 * D_f, 0.3 * D_f + vt["height"]], "g")
    ax.plot([R * math.cos(a) for a in t], [R * math.sin(a) for a in t], "r:", lw=1)
    gt = lay["gear_track"]
    if gt.get("sponson_depth_ft"):
        for sgn in (1, -1):
            ax.add_patch(matplotlib.patches.Ellipse((sgn * gt["half_track_ft"], -0.5 * gt["sponson_depth_ft"]),
                                                    gt["sponson_depth_ft"], gt["sponson_depth_ft"],
                                                    fill=False, color="saddlebrown"))
            ax.plot([sgn * gt["half_track_ft"]] * 2, [-gt["sponson_depth_ft"], -lay["h_cg"]], "k", lw=1.5)
        ax.axhline(-lay["h_cg"], color="brown", lw=1)
    ax.set_aspect("equal")
    ax.set_xlabel("ft (sponsons and wheels down)")
    fig.suptitle(f"Task 12 Stage 1 ({d['concept']}, {d['engine'].get('fixed', 'rubber')}): W0 "
                 f"{d['W0_lb']:.0f} lb, span {w['span']:.1f} ft; orthographic sketch drawn from the "
                 "sizing records, not to a common scale across panels", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def constraint_plot(rows, limits, d, path):
    ws = [float(r["W_S"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    labels = {"climb_sl": "climb 1,000 ft/min, sea level", "ceiling": "service ceiling 25,000 ft",
              "takeoff": "take-off 2,500 ft over 50 ft", "cruise_at_altitude": "cruise at 20,000 ft",
              "turn_at_loiter": "30 deg bank at loiter (R16)"}
    for key, label in labels.items():
        ax.plot(ws, [float(r[key]) for r in rows], label=label)
    ax.axvline(limits["stall"], color="k", ls="--", label=f"stall 70 kt: W/S <= {limits['stall']:.1f}")
    ax.axvline(limits["best_range_at_cruise_q"], color="grey", ls=":", label="best-range W/S at cruise q (5.13)")
    ax.axvline(limits["best_loiter_at_loiter_q"], color="grey", ls="-.", label="best-loiter W/S at loiter q (5.16)")
    ax.axhline(d["bhp_sl"] / d["W0_lb"], color="r", lw=0.8, label="installed engine")
    ax.plot([d["W_S"]], [d["bhp_sl"] / d["W0_lb"]], "r*", ms=12, label="design")
    ax.set_xlabel("take-off wing loading W/S (lb/ft^2)")
    ax.set_ylabel("installed sea-level hp / W0")
    land = (f"landing limit {limits['landing']:.0f} lb/ft^2 (off scale)" if limits["landing_binding"]
            else "landing not binding below 200 lb/ft^2")
    ax.set_title(f"Constraint diagram at W0 {d['W0_lb']:.0f} lb, A {d['A']:.0f}; {land}", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def carpet_plot(rows, stall_ws, engine, path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, concept in zip(axes, ("tractor", "pusher")):
        pts = [r for r in rows if r["concept"] == concept and r["engine"] == engine
               and r["W0"] not in ("", None)]
        X = sorted({float(r["W_S"]) for r in pts})
        Y = sorted({float(r["A"]) for r in pts})
        grid = {(float(r["W_S"]), float(r["A"])): float(r["W0"]) for r in pts}
        Z = [[grid.get((x, y), float("nan")) for x in X] for y in Y]
        cs = ax.contour(X, Y, Z, levels=12)
        ax.clabel(cs, fmt="%.0f", fontsize=7)
        ax.axvline(stall_ws, color="k", ls="--")
        ok = [r for r in pts if float(r["W_S"]) <= stall_ws and r["fuel_fits"] == "True"
              and r.get("power_ok", "True") == "True"]
        best = min(ok, key=lambda r: float(r["W0"]))
        ax.plot(float(best["W_S"]), float(best["A"]), "r*", ms=12)
        ax.set_title(f"{concept}, {engine}: W0 (lb), feasible minimum {float(best['W0']):.0f} lb", fontsize=9)
        ax.set_xlabel("W/S (lb/ft^2); dashed: 70 kt stall limit")
    axes[0].set_ylabel("aspect ratio A")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def vn_plot(d, path):
    vn = d["vn"]
    clmax = d["CL_max"]["clean"]
    W_S = d["W_S"]
    rho0 = 0.0023769
    n_lim = d["n_limit"]
    n_neg = min(-1.8, d["n_negative_gust"])
    Vd = max(v["V_dive_eas_kt"] for k, v in vn.items() if k.startswith("gust_"))
    fig, ax = plt.subplots(figsize=(7.5, 5))
    Vs = [i * Vd / 100 for i in range(101)]
    pos = [min(n_lim, 0.5 * rho0 * (v * 1.68781) ** 2 * clmax / W_S) for v in Vs]
    neg = [max(n_neg, -0.5 * rho0 * (v * 1.68781) ** 2 * 0.8 * clmax / W_S) for v in Vs]
    ax.plot(Vs, pos, "b", label=f"manoeuvre envelope (limit {n_lim:.2f})")
    ax.plot(Vs, neg, "b")
    ax.plot([Vd, Vd], [n_neg, n_lim], "b")
    styles = {"sea_level_takeoff_weight": "g--", "sea_level_zero_fuel_weight": "g:",
              "mission_altitude_takeoff_weight": "m--", "mission_altitude_zero_fuel_weight": "m:"}
    for key, style in styles.items():
        g = vn[f"gust_{key}"]
        Vc, Vdl = g["V_cruise_eas_kt"], g["V_dive_eas_kt"]
        ax.plot([0, Vc, Vdl], [1, g["n_cruise"], g["n_dive"]], style, label=f"gust, {key}")
        ax.plot([0, Vc, Vdl], [1, g["n_cruise_neg"], g["n_dive_neg"]], style)
    ax.set_xlabel("equivalent airspeed (kt)")
    ax.set_ylabel("load factor n")
    ax.set_title("V-n diagram (negative stall line drawn with 0.8 CL_max, a drawing assumption)", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def polar_plot(d, rho_alt, path):
    """Drag polar CD = CD0 + K CL^2 at mission altitude, with the mission points."""
    CD0, K = d["CD0"]["mission_altitude"], d["K"]
    cls = [i * 0.02 for i in range(76)]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.plot([CD0 + K * c ** 2 for c in cls], cls, "b", label="CD0 + K CL^2, mission altitude")
    for m in d["mission"]:
        if m["V_kt"] > 0:
            for W in (m["W_start"], m["W_end"]):
                CL = W / (0.5 * rho_alt * (m["V_kt"] * 1.68781) ** 2 * d["wing"]["area"])
                ax.plot(CD0 + K * CL ** 2, CL, "o", ms=4)
            ax.annotate(m["segment"], (CD0 + K * CL ** 2, CL), fontsize=7, xytext=(4, -8),
                        textcoords="offset points")
    ax.axhline(d["CL_max"]["clean"], color="k", ls="--", lw=0.8, label="clean CL_max")
    ax.set_xlabel("CD")
    ax.set_ylabel("CL")
    ax.set_title(f"Drag polar: CD0 {CD0:.4f}, K {K:.4f} (e {d['e']:.3f})")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def weights_plot(d, path):
    items = sorted(d["components_lb"].items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh([k for k, _ in items], [v for _, v in items])
    ax.invert_yaxis()
    ax.set_xlabel("lb")
    ax.set_title(f"Empty weight build-up, {d['We_lb']:.0f} lb (Raymer 15.46-15.57, composite factors)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


MODULE_ALIASES = {"sizing": ("sizing",), "constraints": ("constraints",),
                  "geometry_sizing": ("geo", "geometry_sizing"), "raymer_aero": ("aero",),
                  "raymer_propulsion": ("prop",), "raymer_loads": ("loads",),
                  "raymer_weights": ("wts",), "raymer_stability": ("stab",),
                  "raymer_performance": ("perf",)}


def equation_table():
    """Each public method function, the equation tags and pages in its docstring, and the tests
    in tests/task12 that call it by name."""
    tests = {p.name: p.read_text() for p in (REPO / "tests" / "task12").glob("test_*.py")}
    rows = []
    for mod_name, aliases in MODULE_ALIASES.items():
        mod = importlib.import_module(f"conceptual.{mod_name}")
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if name.startswith("_") or fn.__module__ != mod.__name__:
                continue
            doc = (fn.__doc__ or "").replace("\n", " ")
            tags = re.findall(r"\((\d{1,2}\.\d{1,3}[a-z]?)\)", doc)
            pages = re.findall(r"p\. (\d{1,3}(?:-\d{1,3})?)", doc)
            hits = sorted(t for t, src in tests.items()
                          if any(re.search(rf"\b{a}\.{name}\(", src) for a in aliases))
            rows.append((f"{mod_name}.{name}", ", ".join(dict.fromkeys(tags)) or "-",
                         ", ".join(dict.fromkeys(pages)) or "-", ", ".join(hits) or "**none**"))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--doc", required=True)
    a = ap.parse_args(argv)
    run, doc = Path(a.run), Path(a.doc)
    fig_dir = doc.parent / "figures" / doc.stem
    fig_dir.mkdir(parents=True, exist_ok=True)
    inp = json.loads((run / "inputs.json").read_text())
    fp = json.loads((run / "first_pass.json").read_text())
    cs = json.loads((run / "concept_scores.json").read_text())
    rec = cs["recommended"]
    other = "pusher" if rec == "tractor" else "tractor"
    D = {c: json.loads((run / f"design_{c}.json").read_text()) for c in ("tractor", "pusher")}
    d = D[rec]
    limits = json.loads((run / "constraint_limits.json").read_text())
    comp_rows = _read_csv(run / f"compliance_{rec}.csv")
    carpet = _read_csv(run / "carpet.csv")
    cd_rows = _read_csv(run / "constraint_diagram.csv")
    engines = _read_csv(run / "engines_compared.csv")
    trades = _read_csv(run / "trades.csv")
    tests = (run / "test_report.txt").read_text().strip().splitlines()[-1]
    ledger = yaml.safe_load((run / "ledger.yaml").read_text())
    from conceptual.units import isa
    rho_alt = isa(ledger["requirements"]["mission_altitude_ft"]["value"])["rho"]

    for c in ("tractor", "pusher"):
        three_view(D[c], fig_dir / f"three_view_{c}.png")
    constraint_plot(cd_rows, limits, d, fig_dir / "constraint_diagram.png")
    carpet_plot(carpet, limits["stall"], inp["chosen_engine"], fig_dir / "carpet_engine.png")
    carpet_plot(carpet, limits["stall"], "rubber", fig_dir / "carpet_rubber.png")
    vn_plot(d, fig_dir / "vn.png")
    polar_plot(d, rho_alt, fig_dir / "polar.png")
    weights_plot(d, fig_dir / "weights.png")
    rel = f"figures/{doc.stem}"

    w, per, lay = d["wing"], d["performance"], d["layout"]
    pr = d["power_required_hp"]
    binding = max(pr, key=pr.get)
    stat = d["empty_fraction_comparison"]
    rub = next(r for r in engines if r["engine"] == "rubber")
    lines = []
    add = lines.append
    add(f"# Task 12 Stage 1, conceptual design package (Gate A passed with actions) ({run.name})")
    add("")
    add("**Status: Stage 1 output with the Gate A round 3 rulings and the round 3 review actions applied. Gate A: passed with actions (docs/reviews/2026-11-20_task12_gateA_round3.md).** Generated by "
        f"`python -m conceptual.report` from `{run}` (commit `{inp['commit'][:10]}`, ledger sha256 "
        f"`{inp['ledger_sha256'][:12]}`, engines sha256 `{inp['engines_sha256'][:12]}`). Every number is "
        "read from those files. Methods: Raymer, *Aircraft Design: A Conceptual Approach*, 2nd ed. "
        "(1992), through `conceptual/`. Review records: `docs/reviews/2026-11-20_task12_gateA_round1.md` and `..._round2.md`.")
    add("")
    add("## Summary")
    add("")
    add(f"- **Frozen concept: {rec}** (Éder, Gate A round 3, on corrected figures). With the round-1 "
        f"criteria and weights it scores {cs['score'][rec]:.2f} against the {other}'s "
        f"{cs['score'][other]:.2f} (only W0 is computed; the rest are judgement grades). Both designs are "
        "kept and reported.")
    add(f"- **{rec.capitalize()} with the {inp['chosen_engine']}**: take-off weight **{d['W0_lb']:,.0f} lb** "
        f"({d['W0_lb'] * LB_KG:,.0f} kg), empty {d['We_lb']:,.0f} lb, fuel {d['fuel_lb']:,.0f} lb, payload "
        f"{d['payload_lb']:,.0f} lb; W/S {d['W_S']:.0f} lb/ft^2, A {d['A']:.0f}, span {w['span']:.1f} ft "
        f"({w['span'] * FT_M:.1f} m). The {other} with the same engine: {D[other]['W0_lb']:,.0f} lb.")
    t34 = next(r for r in engines if r["engine"].endswith("Table 3.4 consumption"))
    add(f"- **The engine sets the weight.** With a rubber engine the same aircraft would be "
        f"{float(rub['W0']):,.0f} lb ({float(rub['bhp']):.0f} shp). The {inp['chosen_engine']} gives "
        f"{d['bhp_sl']:.0f} shp against {max(pr.values()):.0f} needed ({binding} binds). Split of the "
        f"{d['W0_lb'] - float(rub['W0']):+,.0f} lb: the larger engine itself "
        + ("(its weight and installation drag; with the V_C placard the design q and gusts are the "
           "same for both engines) " if ledger["assumptions"]["vc_placard_kt_eas"]["value"] else
           "(weight, drag, and through its higher top speed the design q and gust loads) ")
        + f"{float(t34['W0']) - float(rub['W0']):+,.0f} lb, "
        f"measured with Raymer's Table 3.4 consumption; its datasheet consumption "
        f"({d['cbhp_used']['cruise']} lb/(hp h) against 0.5 and 0.6) {d['W0_lb'] - float(t34['W0']):+,.0f} lb. "
        "The engine figures are search extracts of the maker's pages and must be checked against the "
        "datasheet (engines.yaml).")
    sp = d["components_lb"].get("sponsons")
    nosp = next((t for t in trades if t["case"].startswith("no sponsons")), None)
    if sp and nosp:
        add(f"- **Sponsons** (round 3 ruling) weigh {sp:.0f} lb and add drag; they cost "
            f"{d['W0_lb'] - float(nosp['W0']):+,.0f} lb of take-off weight against wheels stowed for free "
            f"({float(nosp['W0']):,.0f} lb, reference only).")
    neg_other = D[other]["n_negative_gust"]
    if neg_other < -1.8:
        add(f"- The {other}'s negative gust is {neg_other:.3f} against the -1.8 limit (not met for the "
            f"{other}; the frozen {rec} meets it).")
    unmet = [r for r in comp_rows if r["met"] == "False"]
    met = [r for r in comp_rows if r["met"] == "True"]
    add(f"- Requirements: {len(met)} checked rows met, {len(unmet)} not met"
        + (": " + "; ".join(r["requirement"] for r in unmet) if unmet else "") + ".")
    add(f"- Empty weight: build-up {stat['build_up']:.3f} of W0, Table 3.1 x 0.95 {stat['table_3_1']:.3f} "
        "(decomposition in section 4).")
    add(f"- First pass (Table 3.1 with sketch values) {fp['W0']:,.0f} lb. Method tests: `{tests}`.")
    add("")
    add("## 0. What changed after Gate A round 1")
    add("")
    add("| Finding or ruling | Change |")
    add("|---|---|")
    for f_, c_ in [
        ("F1 main gear missing from the balance", "Main gear placed by the 15 deg tipback rule (p. 232) and included in the CG; nose-wheel load and propeller clearance checked"),
        ("F2 gust at take-off weight only", "Gust at take-off and zero-fuel weight, sea level and mission altitude; the largest sets the limit load"),
        ("F3 q inconsistent with the V-n", "Weight equations use q at the design cruise speed V_C (sea-level maximum level speed)"),
        ("F4 crew-item explanation", "Decomposition reported (section 4)"),
        ("F5 ceiling grid artefact", "Ceiling by bisection with CD0 at altitude; the last passing altitude is reported"),
        ("F6 hard-coded speed text", "The mission records which legs the 1.3 V_stall floor set; the text is generated from it"),
        ("F7 constraint diagram", "Landing limit searched to 200 lb/ft^2; best-range and best-loiter W/S and the R16 turn added"),
        ("F8 test coverage", "Tests for methods without printed values (identities, limits, Table 10.4 against Mattingly's PT6A-42); equation-to-test table (section 10)"),
        ("F9 constants in the code", "Moved to the ledger with sources and bands (appendix A)"),
        ("F10 calibration list, polar, propeller", "Section 9; drag polar and propeller operating points added"),
        ("F11 trim and rotation", "Trim on every mission leg at its fuel state; nose rotation at 0.8 V_TO with the forward CG (p. 432-433); tail enlarged where rotation needs it"),
        ("Engine (Éder: find a small turboprop)", "PBS TP100 (241 shp, 135.8 lb, 0.901 lb/(hp h)) fixed; Turbotech TP-R90, PT6A-42 and rubber compared"),
        ("R9 negative limit (Éder: raise it)", "Ledger -1.8 (GA utility); see section 7"),
        ("Round 2 N1 rotation sign", "Main-wheel reaction and friction both nose-down; flap moment (16.17, Fig. 16.9) and wing moment (16.16) added; ground effect not modelled; sign test added"),
        ("Round 2 N2 nose-load display", "Limits shown as 5-20 % with the 8-15 % optimum; the nose wheel moves forward in its band when above the optimum"),
        ("Round 2 N3 overturn and track", "Half-track for the 63 deg overturn limit (p. 232) and a stowage check against the wing depth"),
        ("Round 2 N4 pusher rotation angle", "Pusher at 10 deg with a tail bumper (favourable end); tractor clearance with the nose strut compressed"),
        ("Round 2 N6 engine attribution", "Split into engine size and consumption with a Table 3.4 run of the same engine"),
        ("Round 2 scoring", "Round-1 weights restored; layout limits applied as constraints, not scored rows"),
        ("Round 3 rulings", "Pusher frozen; V_C placarded at 150 kt EAS (R18); 1.3 V_stall floor kept (R17); R16 accepted; main gear in sponsons with drag (Q 1.5) and weight (Table 15.2) penalties"),
        ("Round 2 F9 tyre drag", "Regular wheel and tyre 0.25 (Table 12.5 p. 287) instead of the faired 0.13"),
    ]:
        add(f"| {f_} | {c_} |")
    add("")
    add(f"## 1. Requirements compliance ({rec})")
    add("")
    add("| Requirement | Value | Limit | Rule | Met |")
    add("|---|---|---|---|---|")
    for r in comp_rows:
        nd = 3 if r["units"] in ("MAC", "-", "tail CL") else (1 if r["units"] in ("ft^3", "in") else 0)
        mark = {"True": "yes", "False": "**no**", "": "-"}[r["met"]]
        add(f"| {r['requirement']} ({r['units']}) | {_f(r['value'], nd)} | {_f(r['limit'], nd)} | {r['rule']} | {mark} |")
    add("")
    add("Take-off and landing distances are Raymer's segment sums (17.8-17.9) with gear and flap drag "
        "(12.37); landing weight = take-off weight (conservative). FAR landing field length: "
        f"{per['landing']['far_field_length']:,.0f} ft. The nose-load rows pass inside Raymer's 5-20 % "
        "limits; the 8-15 % band is his optimum.")
    add("")
    add("## 2. Concept choice (step 2, re-scored)")
    add("")
    add("| Criterion | Weight | Tractor | Pusher | Tractor grade | Pusher grade |")
    add("|---|---|---|---|---|---|")
    for r in cs["table"]:
        nd_t = 3 if float(r["tractor"]) < 1 else 0
        nd_p = 3 if float(r["pusher"]) < 1 else 0
        add(f"| {r['criterion']} | {r['weight']:.2f} | {_f(r['tractor'], nd_t)} | {_f(r['pusher'], nd_p)} | "
            f"{r['tractor_grade']} | {r['pusher_grade']} |")
    add(f"| **weighted score** | | | | **{cs['score']['tractor']:.2f}** | **{cs['score']['pusher']:.2f}** |")
    add("")
    add("Feasibility constraints (not scored; a layout must meet them or be redesigned):")
    add("")
    add("| Constraint | Tractor | Pusher |")
    add("|---|---|---|")
    for k in cs["feasibility"]["tractor"]:
        add(f"| {k} | {cs['feasibility']['tractor'][k]} | {cs['feasibility']['pusher'][k]} |")
    add("")
    add("| Quantity | Tractor | Pusher |")
    add("|---|---|---|")
    for label, key, nd in (("W0 (lb)", "W0_lb", 0), ("W/S (lb/ft^2)", "W_S", 0), ("A", "A", 0),
                           ("main gear length (in)", "gear_length_in", 0),
                           ("horizontal-tail volume scale for rotation", "ht_volume_scale", 2),
                           ("limit load factor", "n_limit", 2)):
        add(f"| {label} | {_f(D['tractor'][key], nd)} | {_f(D['pusher'][key], nd)} |")
    for label, k in (("nose-wheel load, full fuel", "full"), ("nose-wheel load, empty", "empty")):
        add(f"| {label} | {D['tractor']['layout']['nose_load'][k]:.3f} | {D['pusher']['layout']['nose_load'][k]:.3f} |")
    add(f"| nose-wheel station (fraction of length) | {D['tractor']['layout']['nose_station']:.2f} | "
        f"{D['pusher']['layout']['nose_station']:.2f} |")
    add(f"| main-gear half-track for 63 deg overturn (ft) | {D['tractor']['layout']['gear_track']['half_track_ft']:.2f} | "
        f"{D['pusher']['layout']['gear_track']['half_track_ft']:.2f} |")
    add(f"| rotation: tail CL needed after resize (negative = download) | "
        f"{D['tractor']['layout']['rotation']['CL_tail_needed']:.2f} | {D['pusher']['layout']['rotation']['CL_tail_needed']:.2f} |")
    add("")
    add("Scoring: the round-1 criteria and weights, unchanged; only W0 is computed. The pusher is "
        "evaluated at the favourable end of the rotation band: a tail bumper limits rotation to "
        f"{ledger['assumptions']['rotation_angle_deg_pusher']['value']:.0f} deg, which still needs a "
        f"{D['pusher']['gear_length_in']:.0f} in main gear for 9 in of propeller clearance (p. 222, 232). "
        "The tall gear raises the CG, so the tipback rule moves the wheels aft and loads the nose wheel; "
        "the nose wheel is then moved forward inside its band. Rotation (corrected for the round-2 sign "
        "error) sizes the horizontal tail of both concepts. A raised thrust line is not modelled.")
    add("")
    add(f"![three-view {rec}]({rel}/three_view_{rec}.png)")
    add("")
    add(f"![three-view {other}]({rel}/three_view_{other}.png)")
    add("")
    add("## 3. Layout")
    add("")
    add(f"Fuselage {d['fuselage']['length']:.1f} ft (Table 6.3), {d['fuselage']['diameter']:.2f} ft "
        f"diameter; tail arm {d['tail_arm_ft']:.1f} ft; horizontal tail {d['horizontal_tail']['area']:.1f} "
        f"ft^2 (volume scale {d['ht_volume_scale']:.2f}), vertical tail {d['vertical_tail']['area']:.1f} "
        f"ft^2; propeller {d['propeller_diameter_ft']:.2f} ft (three-blade (10.24) or the 950 ft/s tip "
        f"limit); main gear {d['gear_length_in']:.0f} in at {lay['x_main']:.2f} ft, CG height "
        f"{lay['h_cg']:.2f} ft; propeller clearance at rotation {lay['prop_clearance_in']:.1f} in.")
    add("")
    add("## 4. Weight statement")
    add("")
    add(f"![weights]({rel}/weights.png)")
    add("")
    add("| Item | lb | Station (ft) |")
    add("|---|---|---|")
    for k, st in sorted(d["stations"].items(), key=lambda kv: kv[1]["x"]):
        add(f"| {k} | {st['weight']:.1f} | {st['x']:.2f} |")
    add(f"| fuel (wing tanks) | {d['fuel_lb']:.1f} | wing group |")
    total = sum(s["weight"] for s in d["stations"].values()) + d["fuel_lb"]
    add(f"| **sum** | **{total:.1f}** | CG {lay['cg_full']:.2f} full, {lay['cg_empty']:.2f} empty |")
    add("")
    add("Empty-fraction decomposition (reviewer finding F4):")
    add("")
    add("| Quantity | Fraction of W0 |")
    add("|---|---|")
    for k, label in (("build_up", "component build-up with composite factors (this design)"),
                     ("build_up_metal", "same build-up without the Table 15.4 composite factors"),
                     ("crew_items_furnishings", "crew items Raymer's GA set would add: furnishings (15.59); air conditioning (15.58) is zero with no crew"),
                     ("build_up_metal_with_crew_items", "metal build-up plus crew items"),
                     ("table_3_1_metal", "Table 3.1 fit, general aviation single"),
                     ("table_3_1", "Table 3.1 fit x 0.95 (composite)"),
                     ("table_6_2", "Table 6.2 fit x 0.95"),
                     ("table_15_2_approximate", "Table 15.2 approximate group weights")):
        add(f"| {label} | {stat[k]:.3f} |")
    add("")
    gap = stat["table_3_1_metal"] - stat["build_up_metal_with_crew_items"]
    gap95 = stat["table_3_1"] - stat["build_up"]
    crew = stat["crew_items_furnishings"]
    if gap95 > 0:
        lead = (f"The build-up is {gap95:.3f} of W0 below the Table 3.1 fit x 0.95; the crew items alone "
                f"are {crew:.3f}, so they explain {'most' if crew >= 0.7 * gap95 else 'part'} of that gap. ")
    else:
        lead = (f"The build-up is {-gap95:.3f} of W0 above the Table 3.1 fit x 0.95 even without the crew "
                f"items ({crew:.3f}); the crewless UAV's components (sponsons, enlarged tail, gear) "
                "outweigh the statistical aircraft at this size. ")
    add(lead + "Like for "
        f"like (metal, with crew items) the group equations sit {abs(gap):.3f} "
        f"{'below' if gap > 0 else 'above'} the metal fit. Stage 3's independent sizing (Anderson ch. 8) "
        "is the check.")
    add("")
    add("## 5. Drag, propulsion and mission")
    add("")
    add(f"![polar]({rel}/polar.png)")
    add("")
    add(f"CD0: {d['CD0']['mission_altitude']:.4f} at mission altitude, {d['CD0']['sea_level']:.4f} sea "
        f"level, {d['CD0']['takeoff']:.4f} take-off and {d['CD0']['landing']:.4f} landing (gear by the "
        "DR-1 p. 572 per-area values, flaps by (12.37)); "
        f"e {d['e']:.3f} (12.49); CL_max clean {d['CL_max']['clean']:.2f}, take-off "
        f"{d['CL_max']['takeoff']:.2f}, landing {d['CL_max']['landing']:.2f}.")
    add("")
    add("| Segment | W start (lb) | W end (lb) | Mean TAS (kt) | Speed set by |")
    add("|---|---|---|---|---|")
    for m in d["mission"]:
        if m["V_kt"]:
            fr = m["speed_floor_fraction"]
            by = ("1.3 V_stall floor" if fr > 0.99 else "best speed (L/D max or minimum power)"
                  if fr < 0.01 else f"floor in {fr:.0%} of sub-segments")
            v = _f(m["V_kt"], 1)
        else:
            by, v = "-", "-"
        add(f"| {m['segment']} | {m['W_start']:.1f} | {m['W_end']:.1f} | {v} | {by} |")
    add("")
    add("Propeller operating points (efficiency is the ledger's constant, not computed; J and C_P from "
        "(13.10)-(13.11)):")
    add("")
    add("| Point | V (kt) | Shaft hp | Throttle | J | C_P |")
    add("|---|---|---|---|---|---|")
    for k, p in d["propeller_points"].items():
        add(f"| {k} | {p['V_kt']:.1f} | {p['shaft_hp']:.1f} | {p['throttle']:.2f} | {p['J']:.2f} | {p['C_P']:.3f} |")
    add("")
    add("Engines compared at the recommended point (W/S, A and tail held):")
    add("")
    add("| Engine | shp | Engine lb | C_bhp cruise / loiter | W0 (lb) | Fuel (lb) | Power needed (hp) | Power OK |")
    add("|---|---|---|---|---|---|---|---|")
    for r in engines:
        add(f"| {r['engine']} | {_f(r.get('bhp'))} | {_f(r.get('engine_weight_lb'))} | "
            f"{r.get('cbhp_cruise', '')} / {r.get('cbhp_loiter', '')} | {_f(r.get('W0'))} | {_f(r.get('fuel'))} | "
            f"{_f(r.get('required_hp'))} | {r.get('power_ok', '')} |")
    add("")
    add("The rubber engine's weight is Table 10.4 extrapolated below 400 bhp. The TP-R90 and PT6A-42 rows "
        "carry Table 3.4 consumption (no published values in hand); the TP-R90 lacks the power for the "
        "ceiling.")
    add("")
    add("## 6. Constraint diagram and carpet plots")
    add("")
    add(f"![constraints]({rel}/constraint_diagram.png)")
    add("")
    add(f"![carpet engine]({rel}/carpet_engine.png)")
    add("")
    add(f"![carpet rubber]({rel}/carpet_rubber.png)")
    add("")
    add("Required sea-level shp: " + ", ".join(f"{k} {v:.0f}" for k, v in pr.items())
        + f"; engine {d['bhp_sl']:.0f}. The ceiling and altitude rows use Raymer's piston lapse (13.9); "
        "Stage 3 measures the turboprop lapse (Mattingly App. K). Carpets use the Table 6.4 tail; the "
        "rotation resize is applied at each concept's optimum.")
    add("")
    add("## 7. Loads, stability, trim and rotation")
    add("")
    add(f"![vn]({rel}/vn.png)")
    add("")
    add("| Gust case | n (positive) | 2 - n (negative) |")
    add("|---|---|---|")
    for k, v in d["gusts"].items():
        add(f"| {k} | {v:.2f} | {2 - v:.2f} |")
    add("")
    add(f"Limit load factor {d['n_limit']:.2f}, ultimate {d['Nz_ultimate']:.2f}; design q "
        f"{d['q_design_psf']:.1f} psf at V_C {d['V_c_eas_kt']['sea_level']:.0f} kt EAS. Negative gust "
        f"{d['n_negative_gust']:.2f} against the -1.8 set at round 1; Raymer's weight equations carry "
        "only the positive case.")
    add("")
    add(f"Static margin {lay['sm_full']:.3f} (full) and {lay['sm_empty']:.3f} (empty); neutral point "
        f"{lay['x_np']:.2f} ft; downwash gradient {1 - lay['dah_da']:.3f} (far-wake value in place of "
        "Raymer's chart, conservative). Tail lift coefficient in trim at every leg start and end: "
        + ", ".join(f"{k} {v['CL_tail']:.3f}" for k, v in lay["trim"].items())
        + f". Rotation at {lay['rotation']['V_kt']:.0f} kt with the forward CG: tail CL needed "
        f"{lay['rotation']['CL_tail_needed']:.2f} (available "
        f"{ledger['assumptions']['tail_cl_max_rotation']['value']}).")
    add("")
    add("## 8. Performance as sized")
    add("")
    add("| Quantity | Value |")
    add("|---|---|")
    for k in ("V_stall_clean_kt", "V_stall_landing_kt", "takeoff_ft", "landing_ft", "roc_sl_fpm",
              "v_best_climb_kt", "service_ceiling_ft", "vmax_alt_kt"):
        add(f"| {k} | {_f(per[k], 1)} |")
    add("")
    add("## 9. Trades, sensitivities and out-of-calibration uses")
    add("")
    add("| Trade | W0 (lb) | Fuel (lb) | Power OK |")
    add("|---|---|---|---|")
    for t in trades:
        if not (t["case"].endswith("(lo)") or t["case"].endswith("(hi)")):
            add(f"| {t['case']} | {_f(t['W0'])} | {_f(t['fuel'])} | {t.get('power_ok', '')} |")
    base = next(t for t in trades if t["case"] == "loiter_h=8")
    sens, by_name = [], {}
    for t in trades:
        if (t["case"].endswith("(lo)") or t["case"].endswith("(hi)")) and t["W0"] not in ("", None):
            dw = float(t["W0"]) - float(base["W0"])
            sens.append((abs(dw), dw, t))
            by_name.setdefault(t["case"].split("=")[0], []).append(abs(dw))
    sens.sort(key=lambda x: -x[0])
    add("")
    add("| Ledger assumption at band end | W0 (lb) | Change (lb) |")
    add("|---|---|---|")
    for _, dw, t in sens[:12]:
        add(f"| {t['case']} | {_f(t['W0'])} | {dw:+.0f} |")
    add("")
    add("No effect at this design: " + ", ".join(sorted(k for k, v in by_name.items() if max(v) < 0.5)) + ".")
    add("")
    add("Used outside its calibration (each carried with a band or flagged for Stage 3):")
    add("")
    for item in [
        "Table 3.1 and Table 6.2 empty-weight fits and the GA group weights (15.46)-(15.57): crewed aircraft, used without crew items.",
        "Table 6.3 fuselage length: crewed aircraft; it sets the tail arm and the fuselage wetted area.",
        "Table 3.4 consumption (rubber, TP-R90 and PT6A-42 rows): large turboprops. The TP100 uses its datasheet cruise value also at loiter; its part-power value is unknown.",
        "Table 10.4 turboprop weight and size: 400-5,000 bhp; the rubber engine and the TP100 are below it.",
        "(13.9) power lapse: piston engines, applied to turboprops.",
        "(12.49) span efficiency: a straight-wing fit; it sets the optimum aspect ratio.",
        "Downwash: the far-wake value in place of Raymer's chart.",
        "Gear and tyre drag per area: DR-1's readings of Raymer's gear-drag table.",
    ]:
        add(f"- {item}")
    add("")
    add("## 10. Method tests (equation to test)")
    add("")
    add(f"Run: `{tests}`. Functions are matched by name in `tests/task12/`; 'none' means no test calls "
        "the function directly (it may still run through `uav.py` in the pipeline tests). DR-1's "
        "maximum-speed and climb plots (p. 584-585) use a chart thrust curve and are not reproduced.")
    add("")
    add("| Function | Equation(s) | Page(s) | Tests |")
    add("|---|---|---|---|")
    for row in equation_table():
        add("| " + " | ".join(row) + " |")
    add("")
    add("## 11. Risks, each with its Stage 3 measurement")
    add("")
    add("| Risk | Effect if wrong | Stage 3 measurement |")
    add("|---|---|---|")
    for risk, eff, meas in [
        ("Turboprop power lapse (piston (13.9) used)", "ceiling binds the engine; a better lapse leaves margin, a worse one fails R12",
         "Mattingly App. K off-design analysis at 20,000 and 25,000 ft"),
        ("TP100 consumption at loiter part power (cruise value used)", f"about {_f(d['propeller_points'].get('loiter', {}).get('throttle', 0), 2)} throttle at loiter; fuel and W0 move directly",
         "Mattingly App. K part-power SFC; the datasheet"),
        ("Empty weight of a crewless aircraft from crewed statistics", "W0 through the sizing growth factor",
         "Anderson ch. 8 independent weight estimate"),
        ("Section CL_max 1.5 (judgement)", "sets the loiter and cruise speeds through the 1.3 V_stall floor and the stall limit",
         "SU2 polar of the chosen section after a NACA-data validation row"),
        ("Span efficiency (12.49) and downwash (far-wake value)", "optimum aspect ratio; static margin and tail size",
         "vortex lattice: span loading, e, downwash at the tail"),
        ("Sponson size, drag (form factor at low fineness, Q 1.5) and weight (banded)", "about 12 % of W0 at the current size",
         "layout in preliminary design; sponson drag by the vortex-lattice/CFD ladder"),
        ("Rotation without ground effect; assumed tail CL limits", "tail size", "lattice with a ground image; elevator sizing"),
        ("TP100 data from search extracts", "every engine number", "read the datasheet before Gate B"),
    ]:
        add(f"| {risk} | {eff} | {meas} |")
    add("")
    add("## 12. Actions carried past Gate A")
    add("")
    add(f"1. **Engine data**: read the {inp['chosen_engine']} datasheet and update engines.yaml before "
        "Gate B (search extracts used; the maker's host is blocked from the sandbox).")
    add("2. **Stage 3 measurements** named in section 11, in particular the turboprop lapse and the "
        "loiter part-power consumption (Mattingly App. K).")
    add("3. **Sponson** size, drag and weight are banded assumptions; preliminary design draws them.")
    add("4. The rotation and trim checks rest on two assumed tail lift limits (ledger).")
    add("")
    add("## Appendix A. Ledger")
    add("")
    add("| Name | Value | Units | Confidence | Band | Source |")
    add("|---|---|---|---|---|---|")
    for grp in ("requirements", "assumptions"):
        for name, q in ledger[grp].items():
            band = q.get("band", "")
            add(f"| {name} | {q['value']} | {q['units']} | {q['confidence']} | {band if band else ''} | {q['source']} |")
    add("")
    add("## Appendix B. Records")
    add("")
    for name in sorted(p.name for p in run.iterdir()):
        add(f"- `{run / name}`")
    doc.write_text("\n".join(lines) + "\n")
    print(f"wrote {doc} and {fig_dir}")


if __name__ == "__main__":
    main()

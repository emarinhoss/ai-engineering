"""Bias sweep of the drone ledger's banded quantities at one design (T10.10d, spec section 10.5).

    python -m analysis.bias_sweep_drone [--params params.json] [--out DIR_OR_FILE.csv]

For every quantity in data/drone/*.yaml that carries a band (read from the YAML through the
ledger loader, not listed here) the low-fidelity model drone.evaluate.evaluate is run twice at the
design: once with that quantity at its band low and once at its band high, every other quantity
at its recorded value. Reported per quantity: endurance_h and mtow_kg at each end, the change from
the recorded-value run in absolute units and in percent of the design's own value, ranked by the
larger |percent change of endurance|. A quantity whose both ends give exactly the recorded result
changes nothing at this design: either nothing in the low-fidelity model reads it (the RANS
freestream turbulence) or it is read and not binding here (the installed power margin when the
climb requirement sets the installed power). It is listed, marked "no effect at this design", and
never dropped.

--params: JSON with the six inputs of designs.make_pool_drone.INPUTS at the top level, or under
a "design" key (analysis.inverse's inverse.json), or the confirm_params.json of the inverse
query. Default: row 0 of designs/pool_drone96.csv.
--out: a directory (writes bias_sweep.csv there) or a path ending in .csv. A Markdown table of the
ranked result is printed to stdout either way.

An end that makes the evaluation raise or fail a gate is recorded with its message and NaN
deltas; it is not hidden and it does not stop the sweep.
"""
import argparse
import copy
import csv
import json
import math
from pathlib import Path

from designs.make_pool_drone import INPUTS
from drone import ledger
from drone.evaluate import evaluate

COLUMNS = ("rank", "set", "name", "units", "confidence", "value", "band_lo", "band_hi",
           "endurance_h_lo", "endurance_h_hi", "mtow_kg_lo", "mtow_kg_hi",
           "d_endurance_h_lo", "d_endurance_h_hi", "d_mtow_kg_lo", "d_mtow_kg_hi",
           "pct_endurance_lo", "pct_endurance_hi", "pct_mtow_lo", "pct_mtow_hi",
           "max_abs_pct_endurance", "effect", "gates_lo", "gates_hi", "error_lo", "error_hi")
DEFAULT_POOL = Path(__file__).resolve().parents[1] / "designs" / "pool_drone96.csv"


def banded_quantities():
    """[(set, name, Quantity)] of every ledger quantity with a band, in file order."""
    found = []
    for set_name in ledger.SET_NAMES:
        for name, q in ledger._read(set_name).items():   # the loader's own reader, all fields
            if q.band is not None:
                found.append((set_name, name, q))
    return found


def design_from(path=None):
    """The six inputs as a params dict: from a JSON file, else row 0 of the 96-point pool."""
    if path is None:
        with open(DEFAULT_POOL) as f:
            row = next(csv.DictReader(f))
        raw = {k: float(row[k]) for k in INPUTS}
    else:
        raw = json.loads(Path(path).read_text())
        raw = raw.get("design", raw)
    missing = [k for k in INPUTS if k not in raw]
    if missing:
        raise ValueError(f"design is missing inputs {missing}")
    return {"family": "drone", "fidelity": "low", "tag": "bias_sweep",
            **{k: float(raw[k]) for k in INPUTS}}


def evaluate_with(params, fixed, set_name, name, value):
    """(endurance, mtow, gates text, error text) with one fixed quantity set to value."""
    changed = copy.deepcopy(fixed)
    changed[set_name][name] = value
    try:
        out = evaluate(params, changed)
    except ValueError as exc:
        return math.nan, math.nan, "", str(exc)
    return out["endurance_h"], out["mtow_kg"], " | ".join(out["gates"]), ""


def sweep(params, fixed=None):
    """Run the sweep. Returns (base, rows): base = recorded-value result, rows ranked."""
    fixed = fixed or ledger.load_all()
    base_out = evaluate(params, fixed)
    base = {"endurance_h": base_out["endurance_h"], "mtow_kg": base_out["mtow_kg"],
            "gates": list(base_out["gates"])}
    rows = []
    for set_name, name, q in banded_quantities():
        ends = {}
        for tag, value in (("lo", q.band[0]), ("hi", q.band[1])):
            ends[tag] = evaluate_with(params, fixed, set_name, name, value)
        row = {"set": set_name, "name": name, "units": q.units, "confidence": q.confidence,
               "value": q.value, "band_lo": q.band[0], "band_hi": q.band[1]}
        for tag, (end, mtow, gates, error) in ends.items():
            row.update({f"endurance_h_{tag}": end, f"mtow_kg_{tag}": mtow,
                        f"d_endurance_h_{tag}": end - base["endurance_h"],
                        f"d_mtow_kg_{tag}": mtow - base["mtow_kg"],
                        f"pct_endurance_{tag}": 100.0 * (end / base["endurance_h"] - 1.0),
                        f"pct_mtow_{tag}": 100.0 * (mtow / base["mtow_kg"] - 1.0),
                        f"gates_{tag}": gates, f"error_{tag}": error})
        pcts = [abs(row["pct_endurance_lo"]), abs(row["pct_endurance_hi"])]
        row["max_abs_pct_endurance"] = max((p for p in pcts if not math.isnan(p)), default=math.nan)
        zero = all(row[f"d_endurance_h_{t}"] == 0.0 and row[f"d_mtow_kg_{t}"] == 0.0
                   for t in ("lo", "hi"))
        row["effect"] = "no effect at this design" if zero else "moves the result"
        rows.append(row)
    rows.sort(key=lambda r: -(0.0 if math.isnan(r["max_abs_pct_endurance"])
                              else r["max_abs_pct_endurance"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return base, rows


def markdown(base, rows):
    """Ranked Markdown table: change of endurance and mtow at band low / band high."""
    head = ("| rank | quantity | recorded [band] | endurance % (low, high) | mtow % (low, high) "
            "| note |\n|---|---|---|---|---|---|")
    lines = [(f"Design endurance {base['endurance_h']:.4f} h, mtow {base['mtow_kg']:.4f} kg "
              "(recorded values)."), "", head]
    for r in rows:
        note = r["effect"] if r["effect"] != "moves the result" else ""
        if r["gates_lo"] or r["gates_hi"] or r["error_lo"] or r["error_hi"]:
            note = (note + "; " if note else "") + "gated/error at an end (see CSV)"
        lines.append(
            f"| {r['rank']} | {r['set']}:{r['name']} | {r['value']:g} [{r['band_lo']:g}, "
            f"{r['band_hi']:g}] {r['units']} | {r['pct_endurance_lo']:+.2f}, "
            f"{r['pct_endurance_hi']:+.2f} | {r['pct_mtow_lo']:+.2f}, {r['pct_mtow_hi']:+.2f} "
            f"| {note} |")
    return "\n".join(lines)


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--params", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    params = design_from(a.params)
    base, rows = sweep(params)
    if a.out:
        out = Path(a.out)
        write_csv(out if out.suffix == ".csv" else out / "bias_sweep.csv", rows)
    print(markdown(base, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

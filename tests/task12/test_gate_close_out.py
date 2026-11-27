"""Gate B close-out (ruling B-10): ledger label, robustness figure data, Gate A re-check record."""
import json
from pathlib import Path

import yaml

from postprocess import task12_gateA_recheck as G
from postprocess import task12_robustness_figure as F

ROOT = Path(__file__).resolve().parents[2]
FIG = ROOT / "runs/task12/stage3/2026-11-27/robustness_figure_ws13a8/plotted_data.json"
GATE_A = ROOT / "runs/task12/stage3/2026-11-27/gateA_recheck_ws13a8/gateA.json"


def test_prop_real_to_ideal_is_a_judgement_with_unchanged_value_and_band():
    e = yaml.safe_load((ROOT / "data/task12/ledger.yaml").read_text())["assumptions"]["prop_real_to_ideal"]
    assert e["confidence"] == "assumed" and e["value"] == 0.85 and e["band"] == [0.80, 0.90]
    assert "APL-6" in e["source"]


def test_figure_data_equals_the_record():
    ig = json.loads(F.INFO_GAP.read_text())
    d = F.build_data()
    curve = ig["worst_case_curve"]
    flyable = [[p["h"], p["R5"]["hours"]] for p in curve if p["R5"]["not_flyable"] is None]
    assert d["r5_hours_flyable"][:len(flyable)] == flyable
    g = ig["h_hat"]["R5_guarantee"]["worst_at_h_hat"]
    assert [g["h"], g["hours"]] in d["r5_hours_flyable"]
    assert d["takeoff_ft"][0] == [0.0, ig["nominal"]["takeoff_ft"]]
    assert d["landing_ft"][0] == [0.0, ig["nominal"]["landing_ft"]]
    to_hat, ld_hat = ig["h_hat"]["TO"]["worst_at_h_hat"], ig["h_hat"]["LD"]["worst_at_h_hat"]
    assert [to_hat["h"], to_hat["takeoff_ft"]] in d["takeoff_ft"]
    assert [ld_hat["h"], ld_hat["landing_ft"]] in d["landing_ft"]
    assert [h for h, _ in d["takeoff_ft"]] == sorted(h for h, _ in d["takeoff_ft"])
    cell = json.loads(F.CELL.read_text())
    assert [1.0, cell["modes"]["cliff"]["worst_at_h1"]["transit_ratio"]] in d["cliff_ratio"]


def test_committed_figure_data_matches_record_and_hash():
    meta = json.loads(FIG.read_text())
    assert meta["data"] == F.build_data()
    for rel, h in meta["sources"].items():
        assert F.sha256(ROOT / rel) == h
    assert (FIG.parent / meta["figure"]).stat().st_size > 0


def test_gate_a_values_match_their_records():
    d = G.build()
    assert [x["id"] for x in d["items"]] == [f"A{i}" for i in range(1, 13)]
    for x in d["items"]:
        for v in x["values"]:
            if "source" in v:
                assert G.read(v["source"], v["key"]) == v["value"], (x["id"], v["name"])


def test_gate_a_arithmetic_values():
    items = {x["id"]: {v["name"]: v["value"] for v in x["values"]} for x in G.build()["items"]}
    a1, a2, a3 = items["A1"], items["A2"], items["A3"]
    assert (a1["compliance rows"], a1["rows pass"], a1["rows fail"], a1["rows not tested"]) == (30, 19, 0, 11)
    assert abs(a2["sum of the 13 components"] - a2["empty weight"]) < 1e-6
    assert abs(a2["empty + fuel + payload"] - a2["W0"]) < 0.01
    assert abs(a3["1.06 x burned"] - a3["fuel on board"]) < 0.01
    assert items["A7"]["ledger entries"] == 111 and items["A7"]["info-gap inert variables"] == 25


def test_gate_a_inherited_items():
    status = {x["id"]: x["status"] for x in G.build()["items"]}
    assert status["A9"] == status["A11"] == "inherited (B-9a)"


def test_committed_gate_a_record_is_current():
    assert json.loads(GATE_A.read_text()) == G.build()
    md = ROOT / "docs/validation/2026-11-27_task12_gateA_recheck_ws13a8.md"
    assert md.read_text() == G.render(G.build()) + "\n"

"""T10.10d contract: the one-at-a-time bias sweep of the ledger's banded quantities.

One row per banded quantity found in data/drone/*.yaml (counted here straight from the YAML, not
from the module under test), ranked by the larger |percent change of endurance|, at band low and
band high with every other quantity at its recorded value. Signs are physical: more pack energy
gives more endurance, a heavier skin gives more mass and less endurance. No end of any band may
make the evaluation raise or fail a gate at the pool's first design.
"""
import csv
import json
import math
from pathlib import Path

import pytest
import yaml

from analysis import bias_sweep_drone as bs
from designs.make_pool_drone import INPUTS
from drone import ledger
from drone.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def result():
    params = bs.design_from(None)
    base, rows = bs.sweep(params)
    return params, base, rows, {f"{r['set']}:{r['name']}": r for r in rows}


def yaml_banded():
    """{set:name -> [lo, hi]} read straight from the YAML files."""
    found = {}
    for path in sorted((ROOT / "data" / "drone").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        for q in doc["quantities"]:
            if "band" in q:
                found[f"{path.stem}:{q['name']}"] = q["band"]
    return found


def test_one_row_per_banded_quantity(result):
    _, _, rows, by_name = result
    expected = yaml_banded()
    assert len(expected) >= 15
    assert set(by_name) == set(expected)
    assert len(rows) == len(expected)
    for key, (lo, hi) in expected.items():
        assert (by_name[key]["band_lo"], by_name[key]["band_hi"]) == (lo, hi)


def test_default_design_is_row_zero_of_the_pool():
    with open(ROOT / "designs" / "pool_drone96.csv") as f:
        row0 = next(csv.DictReader(f))
    params = bs.design_from(None)
    assert [params[k] for k in INPUTS] == [float(row0[k]) for k in INPUTS]


def test_design_from_reads_an_inverse_answer(tmp_path):
    design = {k: 1.0 + i for i, k in enumerate(INPUTS)}
    path = tmp_path / "inverse.json"
    path.write_text(json.dumps({"feasible": True, "design": design}))
    assert [bs.design_from(path)[k] for k in INPUTS] == list(design.values())
    with pytest.raises(ValueError):
        path.write_text(json.dumps({"design": {"span_m": 2.0}}))
        bs.design_from(path)


def test_base_is_the_recorded_evaluation(result):
    params, base, _, _ = result
    out = evaluate(params, ledger.load_all())
    assert base["endurance_h"] == out["endurance_h"] and base["mtow_kg"] == out["mtow_kg"]
    assert base["gates"] == []


def test_no_band_end_errors_or_gates_the_design(result):
    _, _, rows, _ = result
    for r in rows:
        for end in ("lo", "hi"):
            assert r[f"error_{end}"] == "", (r["name"], end, r[f"error_{end}"])
            assert r[f"gates_{end}"] == "", (r["name"], end, r[f"gates_{end}"])
            assert math.isfinite(r[f"endurance_h_{end}"]) and math.isfinite(r[f"mtow_kg_{end}"])


def test_ranked_by_largest_endurance_change(result):
    _, _, rows, _ = result
    keys = [r["max_abs_pct_endurance"] for r in rows]
    assert keys == sorted(keys, reverse=True)
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    for r in rows:
        assert r["max_abs_pct_endurance"] == max(abs(r["pct_endurance_lo"]),
                                                 abs(r["pct_endurance_hi"]))


def test_delta_arithmetic(result):
    _, base, rows, _ = result
    for r in rows:
        for end in ("lo", "hi"):
            assert r[f"d_endurance_h_{end}"] == pytest.approx(
                r[f"endurance_h_{end}"] - base["endurance_h"])
            assert r[f"pct_mtow_{end}"] == pytest.approx(
                100.0 * r[f"d_mtow_kg_{end}"] / base["mtow_kg"])


def test_signs_are_physical(result):
    _, _, _, by = result
    energy = by["battery:pack_specific_energy_Wh_per_kg"]
    assert energy["d_endurance_h_hi"] > 0 > energy["d_endurance_h_lo"]
    eta = by["propulsion:propulsive_efficiency"]
    assert eta["d_endurance_h_hi"] > 0 > eta["d_endurance_h_lo"]
    skin = by["structure:skin_areal_density_kg_m2"]       # heavier skin at the HIGH end
    assert skin["d_mtow_kg_hi"] > 0 > skin["d_mtow_kg_lo"]
    assert skin["d_endurance_h_hi"] < 0 < skin["d_endurance_h_lo"]
    payload = by["rules:payload_mass_kg"]
    assert payload["d_mtow_kg_hi"] > 0 > payload["d_endurance_h_hi"]


def test_inert_rows_are_exactly_zero_and_labelled(result):
    _, _, rows, by = result
    for r in rows:
        zero = all(r[f"d_{q}_{e}"] == 0.0 for q in ("endurance_h", "mtow_kg") for e in ("lo", "hi"))
        assert (r["effect"] == "no effect at this design") == zero
    # a RANS-only setting cannot move the low-fidelity model
    assert by["rules:freestream_turbulence_intensity"]["effect"] == "no effect at this design"


def test_cli_writes_csv_and_prints_markdown(tmp_path, capsys):
    assert bs.main(["--out", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert text.count("\n| ") >= len(yaml_banded())
    with open(tmp_path / "bias_sweep.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(yaml_banded()) and rows[0]["rank"] == "1"
    assert tuple(rows[0]) == bs.COLUMNS

"""T10.10c: analysis/mf_drone.py on a synthetic high level built from the recorded low pool.

The synthetic high level is an AFFINE map of the low level (endurance x 0.9 - 0.2, mtow x 1.05), so
the two-level model's discrepancy is a constant and it must beat a GP on the high points alone, with
rho near 0.9 on endurance. No number here is a result of the study; the data are made up on purpose.
"""
import csv
import json
from pathlib import Path

import pytest

from analysis import mf_drone, pool_af_results
from analysis.drone_grid import COLUMNS

LOW = Path(mf_drone.LOW_POOL)
pytestmark = pytest.mark.skipif(not LOW.exists(), reason="needs the recorded low pool")


def _high(tmp_path, n):
    with open(LOW, newline="") as f:
        rows = list(csv.DictReader(f))[:n]
    path = tmp_path / "results.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS + pool_af_results.EXTRA, restval="")
        w.writeheader()
        for r in rows:
            r = dict(r)
            r["endurance_h"] = 0.9 * float(r["endurance_h"]) - 0.2
            r["mtow_kg"] = 1.05 * float(r["mtow_kg"])
            r["status"] = "complete"
            w.writerow(r)
    return path


def _median(rows, model, n, metric):
    vals = sorted(float(r["value"]) for r in rows
                  if r["model"] == model and int(r["n"]) == n and r["metric"] == metric)
    assert vals, (model, n, metric)
    return vals[len(vals) // 2]


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mf")
    out = tmp / "mf.csv"
    assert mf_drone.main(["--high", str(_high(tmp, 40)), "--out", str(out),
                          "--budgets", "8", "40", "--seeds", "2"]) == 0
    with open(out) as f:
        return list(csv.DictReader(f)), out


def test_two_level_beats_single_gp_at_eight_points_on_an_affine_discrepancy(result):
    rows, _ = result
    for metric in ("rmse_endurance", "rmse_mtow_rel"):
        assert _median(rows, "two", 8, metric) < _median(rows, "single", 8, metric), metric


def test_rho_recovers_the_affine_slope_on_endurance(result):
    rows, _ = result
    for r in rows:
        if r["metric"] == "rho_endurance":
            assert float(r["value"]) == pytest.approx(0.9, abs=0.05)


def test_raw_low_fidelity_row_is_present(result):
    rows, _ = result
    raw = {r["metric"]: float(r["value"]) for r in rows if r["model"] == "lf_raw"}
    assert set(raw) == {"rmse_endurance", "rmse_mtow_rel"}
    assert raw["rmse_mtow_rel"] == pytest.approx(1 - 1 / 1.05, rel=1e-9)   # low / high - 1


def test_budgets_clip_to_leave_four_held_out(result):
    rows, out = result
    assert {int(r["n"]) for r in rows if r["model"] != "lf_raw"} == {8}   # 40 > 40 - 4: dropped
    assert mf_drone.clip_budgets((8, 12, 16, 24, 32), 20)[0] == (8, 12, 16)
    notes = json.loads(out.with_suffix(".json").read_text())["notes"]
    assert notes and "[40]" in notes[0]


def test_too_few_high_designs_is_not_run_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "mf.csv"
    assert mf_drone.main(["--high", str(_high(tmp_path, 5)), "--out", str(out)]) == 0
    assert "not run: 5 usable high-fidelity designs (need 12)" in capsys.readouterr().out
    assert not out.exists() and not out.with_suffix(".json").exists()


def test_mismatched_inputs_raise(tmp_path):
    path = _high(tmp_path, 14)
    text = path.read_text().splitlines(True)
    head, first = text[0], text[1].split(",")
    first[1] = str(float(first[1]) + 0.01)                 # span_m of index 0 moved
    path.write_text(head + ",".join(first) + "".join(text[2:]))
    with pytest.raises(ValueError, match="differ"):
        mf_drone.main(["--high", str(path), "--out", str(tmp_path / "mf.csv"), "--budgets", "8",
                       "--seeds", "1"])

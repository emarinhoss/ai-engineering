"""analysis/drone_grid on a 2^6 grid with 2 workers (T10.9a)."""
import csv
import itertools
import json

from analysis import drone_grid


def test_small_grid(tmp_path):
    drone_grid.main(["--points", "2", "--workers", "2", "--out", str(tmp_path)])
    for name in ("grid.csv", "front.csv", "record.json"):
        assert (tmp_path / name).exists()
    with open(tmp_path / "grid.csv", newline="") as f:
        grid = list(csv.DictReader(f))
    with open(tmp_path / "front.csv", newline="") as f:
        front = list(csv.DictReader(f))
    assert len(grid) == 2**6
    assert list(grid[0].keys()) == list(drone_grid.COLUMNS)
    assert [int(r["index"]) for r in grid] == list(range(2**6))
    assert front
    assert all(r["gates"] == "" and r["error"] == "" for r in front)
    mtow = [float(r["mtow_kg"]) for r in front]
    endurance = [float(r["endurance_h"]) for r in front]
    assert mtow == sorted(mtow)
    assert all(b > a for a, b in itertools.pairwise(endurance))
    rec = json.loads((tmp_path / "record.json").read_text())
    assert rec["points_evaluated"] == 2**6
    assert rec["points_clean"] + rec["points_gated"] + rec["points_failed"] <= 2**6
    assert list(front[0].keys()) == list(drone_grid.COLUMNS)
    assert rec["front_size"] == len(front)

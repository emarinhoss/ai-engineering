"""Replay harness on the synthetic pool: runs, is quick, writes the expected CSV."""
import csv
import time

import numpy as np

from surrogate.replay import COLUMNS, STRATEGIES, from_objectives, run, to_objectives
from surrogate.synthetic import make_pool

# per (strategy, seed, n): 2 rmse + hv_regret + 8 coverage + step_seconds + 12 hyperparameters
METRICS_PER_POINT = 24


def test_synthetic_pool_ranges():
    p = make_pool()
    assert len(p["index"]) == 96
    assert 0.2 < p["recovery_total"].min() and p["recovery_total"].max() < 0.5
    assert 1e4 < p["q_peak_W_m2"].min() and p["q_peak_W_m2"].max() < 1e5


def test_objective_transform_round_trip():
    p = make_pool(n=16)
    back = from_objectives(to_objectives(p))
    assert np.allclose(back["recovery_total"], p["recovery_total"])
    assert np.allclose(back["q_peak_W_m2"], p["q_peak_W_m2"])


def test_replay_runs_and_writes_csv(tmp_path):
    out = tmp_path / "replay.csv"
    t0 = time.perf_counter()
    rows = run(make_pool(), seeds=range(2), n_max=16, out_csv=out)
    assert time.perf_counter() - t0 < 60
    with open(out) as f:
        read = list(csv.DictReader(f))
    assert tuple(read[0].keys()) == COLUMNS
    assert len(read) == len(rows) == len(STRATEGIES) * 2 * 3 * METRICS_PER_POINT   # n = 8, 12, 16
    assert {int(r["n"]) for r in read} == {8, 12, 16}
    assert {r["strategy"] for r in read} == set(STRATEGIES)
    # same 8 initial points for every strategy, so hypervolume regret at n = 8 is identical
    at8 = {r["strategy"]: float(r["value"]) for r in read
           if r["seed"] == "0" and r["n"] == "8" and r["metric"] == "hv_regret"}
    assert len(set(at8.values())) == 1

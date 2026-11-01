"""Pareto analysis on the synthetic pool (NOT a physics result): fronts, band, mask, files."""
import csv
import json

import numpy as np
import pytest

from analysis.design_map import design_map, oswatitsch_cut
from analysis.pareto import front_2d, run
from surrogate.acquisition import pareto_front
from surrogate.replay import to_objectives
from surrogate.synthetic import make_pool

GRID, SAMPLES = 61, 10


def pool_rows(n=96):
    p = make_pool(n)
    return [{"case_id": f"synthetic-{i:03d}", "theta1_deg": str(p["theta1_deg"][i]),
             "theta2_deg": str(p["theta2_deg"][i]), "recovery_total": str(p["recovery_total"][i]),
             "q_peak_W_m2": str(p["q_peak_W_m2"][i]), "status": "converged"} for i in range(n)]


@pytest.fixture(scope="module")
def analysis(tmp_path_factory):
    out = tmp_path_factory.mktemp("pareto")
    rows = pool_rows() + [{"case_id": "bad", "theta1_deg": "6", "theta2_deg": "6",
                           "recovery_total": "0.1", "q_peak_W_m2": "1e6", "status": "diverged"}]
    res = run(rows, out, grid=GRID, samples=SAMPLES, seed=0)
    with open(out / "pareto.csv") as f:
        pareto = list(csv.DictReader(f))
    with open(out / "grid.csv") as f:
        grid = list(csv.DictReader(f))
    return out, rows, res, pareto, grid


def of_kind(pareto, kind):
    return [r for r in pareto if r["kind"] == kind]


def test_front_2d_matches_pairwise_definition():
    F = np.random.default_rng(1).random((200, 2))
    assert set(front_2d(F)) == set(pareto_front(F))


def test_observed_front_is_mutually_non_dominated(analysis):
    _, _, _, pareto, _ = analysis
    obs = of_kind(pareto, "observed")
    assert len(obs) >= 3
    F = to_objectives({"recovery_total": [float(r["recovery_total"]) for r in obs],
                       "q_peak_W_m2": [float(r["q_peak_W_m2"]) for r in obs]})
    assert len(pareto_front(F)) == len(obs)                  # nobody dominates anybody
    # and no pool point outside the list dominates a listed one
    pool = make_pool(96)
    Fall = to_objectives(pool)
    assert len(obs) == len(pareto_front(Fall))
    assert all(r["case_id"].startswith("synthetic-") for r in obs)


def test_predicted_front_is_monotone(analysis):
    _, _, _, pareto, _ = analysis
    pred = of_kind(pareto, "predicted")
    q = np.array([float(r["q_peak_W_m2"]) for r in pred])
    rec = np.array([float(r["recovery_total"]) for r in pred])
    order = np.argsort(q)
    assert len(pred) >= 3
    assert (np.diff(rec[order]) >= 0).all()                  # more heating allowed, more recovery
    assert (np.diff(q[order]) > 0).all()


def test_band_is_ordered_and_covers_the_levels(analysis):
    out, _, _, pareto, _ = analysis
    band = of_kind(pareto, "band")
    assert len(band) == 25
    p05, p50, p95 = (np.array([float(r[k]) for r in band]) for k in ("rec_p05", "rec_p50", "rec_p95"))
    ok = np.isfinite(p50)
    assert ok.sum() >= 20
    assert (p05[ok] <= p50[ok]).all() and (p50[ok] <= p95[ok]).all()
    q = np.array([float(r["q_peak_W_m2"]) for r in band])
    assert (np.diff(np.log(q)) > 0).all()                    # log-spaced, increasing
    notes = json.loads((out / "notes.json").read_text())
    assert notes["band_points"] <= 1500 and "Cholesky" in notes["band_method"]


def test_infeasible_triangle_is_nan(analysis):
    _, _, _, _, grid = analysis
    assert len(grid) == GRID * GRID
    n_bad = 0
    for r in grid:
        if float(r["theta1"]) + float(r["theta2"]) > 24 + 1e-9:
            n_bad += 1
            assert r["feasible"] == "0"
            assert all(np.isnan(float(r[k])) for k in ("rec_mean", "rec_std", "q_mean", "q_std"))
        else:
            assert r["feasible"] == "1"
            assert np.isfinite(float(r["rec_mean"])) and float(r["rec_std"]) >= 0
    assert n_bad > 0


def test_files_and_notes(analysis):
    out, _, res, _, _ = analysis
    for name in ("grid.csv", "pareto.csv", "hypers.json", "notes.json"):
        assert (out / name).exists()
    notes = json.loads((out / "notes.json").read_text())
    assert notes["n_used"] == 96 and notes["n_excluded_by_status"] == {"diverged": 1}
    assert "recovery_total" in json.loads((out / "hypers.json").read_text())
    assert len(res["theta"]) == 96


def test_figures_are_written(analysis, tmp_path):
    out, rows, _, _, _ = analysis
    design_map(out / "grid.csv", rows, tmp_path / "design_map.png")
    oswatitsch_cut(rows, tmp_path / "oswatitsch_cut.png")
    assert (tmp_path / "design_map.png").stat().st_size > 10_000
    assert (tmp_path / "oswatitsch_cut.png").stat().st_size > 5_000

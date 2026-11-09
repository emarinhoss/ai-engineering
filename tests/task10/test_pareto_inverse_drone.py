"""T10.10a contract: analysis.pareto, analysis.inverse and analysis.confirm with --family drone.

Run on the low-fidelity pool (runs/drone_pool_lf/2026-11-08/grid.csv, 192 clean designs) and its
exact front. Fixed here before the first real run: the observed front of the drone pareto IS the
exact front of the table (hypervolume regret 0 by construction); the surrogate reproduces the
front's own designs to a few percent; every candidate passes the gates; the inverse answer passes
the closure gates and reaches the probability, or says it cannot and gives the best probability;
the chunked search does not depend on the chunk size. Sizes are small so the file runs in about a
minute; the GP is fitted once per module.
"""
import csv
import itertools
import json
from pathlib import Path

import numpy as np
import pytest

from analysis import confirm, inverse, pareto
from designs.make_pool_drone import HIGH, INPUTS, LOW
from drone import ledger
from physics.gates import check
from surrogate.acquisition import hypervolume_2d, ref_point

POOL = Path("runs/drone_pool_lf/2026-11-08")
pytestmark = pytest.mark.skipif(not (POOL / "grid.csv").exists(), reason="low pool not present")


@pytest.fixture(scope="module")
def rows():
    return pareto.load_rows(POOL / "grid.csv")


@pytest.fixture(scope="module")
def fitted(rows):
    return pareto.fit_gps(rows, "drone")


@pytest.fixture(autouse=True)
def one_fit(monkeypatch, rows, fitted):
    """fit_gps on the module's rows returns the one fitted model instead of refitting."""
    real = pareto.fit_gps

    def cached(r, family="inlet"):
        return fitted if (r is rows and family == "drone") else real(r, family)

    for mod in (pareto, inverse, confirm):
        monkeypatch.setattr(mod, "fit_gps", cached)


@pytest.fixture(scope="module")
def front():
    with open(POOL / "front.csv") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def par(rows, tmp_path_factory):
    out = tmp_path_factory.mktemp("pareto")
    pareto.run_drone(rows, out, candidates=24, samples=5, seed=0, workers=1)
    return out


def read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- pareto
def test_family_uses_the_replay_bounds():
    assert pareto.DRONE is pareto.FAMILIES["drone"]
    assert pareto.DRONE_INPUTS == INPUTS
    assert tuple(pareto.DRONE.bounds) == tuple(zip(LOW, HIGH))


def test_inlet_defaults_unchanged():
    assert pareto.FAMILIES["inlet"].inputs == ("theta1_deg", "theta2_deg")
    assert len(pareto.BOUNDS) == 2 and pareto.GRID_COLUMNS[0] == "theta1"


def test_cheap_gates_agree_with_the_closure_gates():
    """A design failing the closed-form gates must fail physics.gates.check too."""
    rules = ledger.load("rules")
    bad = np.array([[1.2, 16.0, 0.3, 0.3, 2.0, 8.0],       # tip chord and spar depth too small
                    [1.2, 16.0, 0.3, 0.3, 2.0, 15.0]])
    ok = pareto.cheap_gates(bad, rules)
    for x, good in zip(bad, ok):
        if not good:
            assert check(pareto.drone_params(x)) != []
    assert not ok[0]
    nominal = np.array([[2.0, 10.0, 0.6, 0.3, 4.0, 12.0]])
    assert pareto.cheap_gates(nominal, rules)[0] and check(pareto.drone_params(nominal[0])) == []


def test_observed_front_is_the_exact_front(par, front):
    obs = [r for r in read(par / "pareto.csv") if r["kind"] == "observed"]
    assert sorted(int(r["index"]) for r in obs) == sorted(int(r["index"]) for r in front)
    F_obs = np.array([[-float(r["endurance_h"]), np.log(float(r["mtow_kg"]))] for r in obs])
    F_ex = np.array([[-float(r["endurance_h"]), np.log(float(r["mtow_kg"]))] for r in front])
    ref = ref_point(F_ex)
    assert hypervolume_2d(F_obs, ref) == pytest.approx(hypervolume_2d(F_ex, ref), rel=1e-12)


def test_surrogate_reproduces_the_exact_front_designs(fitted, front):
    theta = np.array([[float(r[k]) for k in INPUTS] for r in front])
    em, _, lm, _ = pareto.predict(fitted[0], theta, family="drone")
    assert np.allclose(em, [float(r["endurance_h"]) for r in front], rtol=0.05)
    assert np.allclose(np.exp(lm), [float(r["mtow_kg"]) for r in front], rtol=0.05)


def test_candidates_are_inside_the_gates(par):
    cand = read(par / "candidates.csv")
    assert len(cand) == 24 and {r["feasible"] for r in cand} == {"1"}
    x = np.array([[float(r[k]) for k in INPUTS] for r in cand])
    assert np.all(x >= LOW) and np.all(x <= HIGH)
    assert pareto.cheap_gates(x, ledger.load("rules")).all()
    for row in x[:3]:
        assert check(pareto.drone_params(row)) == []
    for r in cand:
        assert float(r["mtow_kg"]) == pytest.approx(np.exp(float(r["log_mtow_mean"])))
        assert float(r["endurance_std"]) > 0


def test_predicted_front_and_band(par):
    rows_ = read(par / "pareto.csv")
    pred = [r for r in rows_ if r["kind"] == "predicted"]
    assert pred
    mtow = [float(r["mtow_kg"]) for r in pred]
    endurance = [float(r["endurance_h"]) for r in pred]
    order = np.argsort(mtow)                      # a front: more endurance costs more mass
    assert np.all(np.diff(np.array(endurance)[order]) > 0)
    band = [r for r in rows_ if r["kind"] == "band"]
    assert len(band) == pareto.N_LEVELS
    for r in band:
        if r["end_p05"] != "nan":
            assert float(r["end_p05"]) <= float(r["end_p50"]) <= float(r["end_p95"])


def test_design_map_varies_the_two_most_sensitive_inputs(par, fitted):
    m = read(par / "design_map.csv")
    assert len(m) == pareto.MAP_POINTS ** 2
    notes = json.loads((par / "notes.json").read_text())
    ls = notes["endurance_lengthscales"]
    two = sorted(ls, key=ls.get)[:2]
    assert notes["design_map_inputs"] == [two[0], two[1]] or set(notes["design_map_inputs"]) == set(two)
    for k in INPUTS:
        vals = {float(r[k]) for r in m}
        assert (len(vals) == pareto.MAP_POINTS) == (k in two), k
    assert all(float(r["endurance_mean"]) > 0 and float(r["mtow_kg"]) > 0 for r in m)


# ---------------------------------------------------------------- inverse
def test_grid_chunk_matches_itertools_product():
    axes = [np.linspace(lo, hi, 3) for lo, hi in zip(LOW, HIGH)]
    ref = np.array(list(itertools.product(*axes)))
    assert np.array_equal(inverse.grid_chunk(axes, 100, 250), ref[100:250])


def test_pruned_search_equals_predicting_every_point(fitted):
    models = fitted[0]
    rules = ledger.load("rules")
    top, stats = inverse.search_grid(models, rules, 4.0, 0.9, 4, chunk=500, top_k=5)
    x = inverse.grid_chunk(inverse.drone_axes(4), 0, 4 ** 6)
    x = x[pareto.cheap_gates(x, rules)]
    assert stats["n_cheap_gate_feasible"] == len(x)
    em, _ = inverse.gp_predict(models[0], x)
    lm, ls = inverse.gp_predict(models[1], x)
    ok = inverse.ndtr((np.log(4.0) - lm) / ls) >= 0.9
    best = np.argsort(-np.where(ok, em, -np.inf))[:5]
    assert np.allclose(top["endurance"], em[best]) and np.array_equal(top["x"], x[best])
    assert np.allclose(inverse.gp_mean(models[0], x), em)


def test_inverse_answer_is_inside_the_gates_and_the_probability(rows, tmp_path):
    mtow = [float(r["mtow_kg"]) for r in rows if r["gates"] == "" and r["error"] == ""]
    assert min(mtow) <= 4.0                       # the low pool admits designs under the cap
    res = inverse.run_drone(rows, tmp_path, mtow_cap=4.0, prob=0.9, points=5, chunk=4000)
    assert res["feasible"] and res["p_mtow_le_cap"] >= 0.9
    x = np.array([res["design"][k] for k in INPUTS])
    assert np.all(x >= LOW) and np.all(x <= HIGH)
    assert check(pareto.drone_params(x)) == []
    assert res["mtow_kg"]["median"] < 4.0 and res["endurance_h"]["lo90"] < res["endurance_h"]["hi90"]
    assert res["n_grid"] == 5 ** 6 and 0 < res["n_cheap_gate_feasible"] <= res["n_grid"]
    params = json.loads((tmp_path / "confirm_params.json").read_text())
    assert [params[k] for k in INPUTS] == [res["design"][k] for k in INPUTS]
    assert params["family"] == "drone" and json.loads((tmp_path / "inverse.json").read_text())


def test_inverse_does_not_depend_on_the_chunk_size(rows, tmp_path):
    a = inverse.run_drone(rows, tmp_path / "a", points=4, chunk=700)
    b = inverse.run_drone(rows, tmp_path / "b", points=4, chunk=50_000)
    for key in ("design", "n_cheap_gate_feasible"):
        assert a[key] == b[key]
    assert a["endurance_h"]["mean"] == pytest.approx(b["endurance_h"]["mean"], rel=1e-12)


def test_inverse_reports_the_best_probability_when_no_design_meets_the_cap(rows, tmp_path):
    res = inverse.run_drone(rows, tmp_path, mtow_cap=0.5, points=4)   # below every observed mtow
    assert res["feasible"] is False
    assert res["max_probability_on_grid"] < 0.9
    assert set(res["max_probability_design"]) == set(INPUTS)
    assert not (tmp_path / "confirm_params.json").exists()


# ---------------------------------------------------------------- confirm
def record_for(prediction, endurance, mtow, gates=()):
    return {"params": {"family": "drone", **prediction["design"]},
            "section": {"flags": ["v6e_ruling=decision8_accepted_with_bias"]},
            "result": {"endurance_h": endurance, "mtow_kg": mtow, "gates": list(gates)}}


def test_confirm_passes_when_both_objectives_are_inside(rows, tmp_path):
    pred = inverse.run_drone(rows, tmp_path / "inv", points=4)
    rec = record_for(pred, pred["endurance_h"]["mean"], pred["mtow_kg"]["median"])
    res = confirm.run_drone(pred, rec, tmp_path / "c")
    assert res["c2_pass"] is True and res["endurance_h"]["inside"] and res["mtow_kg"]["inside"]
    assert res["section_flags"] == ["v6e_ruling=decision8_accepted_with_bias"]
    assert json.loads((tmp_path / "c" / "confirm.json").read_text())["c2_pass"] is True


def test_confirm_fails_when_one_objective_is_outside(rows, tmp_path):
    pred = inverse.run_drone(rows, tmp_path / "inv", points=4)
    rec = record_for(pred, pred["endurance_h"]["mean"] * 1.5, pred["mtow_kg"]["median"])
    res = confirm.run_drone(pred, rec, tmp_path / "c")
    assert res["c2_pass"] is False
    assert res["endurance_h"]["position"] == "above" and res["mtow_kg"]["inside"]


def test_confirm_refuses_a_record_of_another_design(rows, tmp_path):
    pred = inverse.run_drone(rows, tmp_path / "inv", points=4)
    rec = record_for(pred, 1.0, 1.0)
    rec["params"]["span_m"] += 0.1
    with pytest.raises(ValueError):
        confirm.run_drone(pred, rec, tmp_path / "c")

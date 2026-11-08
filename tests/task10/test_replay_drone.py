"""T10.10b contract: the pool replay with the drone family, and the online replay against the exact
low-fidelity front. Fixed here before any run: objectives f1 = -endurance_h, f2 = log(mtow_kg);
regret = 1 - HV(clean observed points) / HV(exact front), both with the reference point from the
exact front; a gated candidate consumes budget, enters no model and is counted; the candidates of a
step are a fresh scrambled Sobol set over the design box and the acquisition picks among them: no
model, rule or person filters the candidate set. Regret cannot rise for the sequential strategies
(the observed set only grows); lhs redraws its whole design at every budget, as in the inlet
replay, so its regret may rise and that is reported rather than hidden. The inlet defaults of surrogate.replay are
unchanged (tests/test_replay.py keeps passing)."""
import csv
from itertools import pairwise

import numpy as np
import pytest
from scipy.stats import qmc

from designs.make_pool_drone import HIGH, INPUTS, LOW
from drone import evaluate, ledger
from surrogate import replay
from surrogate.acquisition import hypervolume_2d, pareto_front, ref_point

FRONT = "runs/drone_grid/2026-11-08/front.csv"


@pytest.fixture(scope="module")
def fixed():
    return ledger.load_all()


@pytest.fixture(scope="module")
def small_pool(fixed):
    """A 40-point low-fidelity pool evaluated with the real model (clean points only)."""
    pts = qmc.scale(qmc.Sobol(d=6, scramble=True, seed=7).random(64), LOW, HIGH)
    rows = {k: [] for k in ("index", *INPUTS, "endurance_h", "mtow_kg")}
    for i, p in enumerate(pts):
        params = dict(zip(INPUTS, map(float, p)))
        try:
            out = evaluate.evaluate(params, fixed)
        except ValueError:
            continue
        if out["gates"]:
            continue
        rows["index"].append(i)
        for k in INPUTS:
            rows[k].append(params[k])
        rows["endurance_h"].append(out["endurance_h"])
        rows["mtow_kg"].append(out["mtow_kg"])
        if len(rows["index"]) == 40:
            break
    assert len(rows["index"]) == 40
    return {k: np.array(v) for k, v in rows.items()}


# ---- surrogate.replay with family="drone" ----

def test_drone_objectives_are_minus_endurance_and_log_mtow(small_pool):
    F = replay.to_objectives(small_pool, family="drone")
    assert np.allclose(F[:, 0], -small_pool["endurance_h"])
    assert np.allclose(F[:, 1], np.log(small_pool["mtow_kg"]))
    back = replay.from_objectives(F, family="drone")
    assert np.allclose(back["endurance_h"], small_pool["endurance_h"])
    assert np.allclose(back["mtow_kg"], small_pool["mtow_kg"])


def test_drone_pool_scales_six_inputs_to_the_unit_cube(small_pool):
    P = replay.Pool(small_pool, family="drone")
    assert tuple(P.X.shape) == (40, 6)
    assert float(P.X.min()) >= 0.0 and float(P.X.max()) <= 1.0
    assert P.hv_true > 0


def test_drone_pool_replay_runs_all_strategies(small_pool, tmp_path):
    out = tmp_path / "replay.csv"
    rows = replay.run(small_pool, seeds=range(2), n_init=6, n_max=12, report_at=(6, 9, 12),
                      out_csv=out, family="drone")
    with open(out) as f:
        read = list(csv.DictReader(f))
    assert tuple(read[0].keys()) == replay.COLUMNS and len(read) == len(rows)
    assert {r["strategy"] for r in read} == set(replay.STRATEGIES)
    assert {int(r["n"]) for r in read} == {6, 9, 12}
    regret = [float(r["value"]) for r in read if r["metric"] == "hv_regret"]
    assert all(0.0 <= v <= 1.0 for v in regret)


def test_load_pool_for_the_drone_family_reads_the_grid_csv_columns(tmp_path, small_pool):
    pool_csv, results_csv = tmp_path / "pool.csv", tmp_path / "results.csv"
    with open(pool_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("index", *INPUTS))
        for i in range(40):
            w.writerow([small_pool["index"][i], *[f"{small_pool[k][i]:.6f}" for k in INPUTS]])
    with open(results_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("index", *INPUTS, "endurance_h", "mtow_kg", "gates", "error"))
        for i in range(40):
            gated = "gate 4 (manufacturing floor): x" if i == 3 else ""
            w.writerow([small_pool["index"][i], *[f"{small_pool[k][i]:.6f}" for k in INPUTS],
                        small_pool["endurance_h"][i], small_pool["mtow_kg"][i], gated, ""])
    pool = replay.load_pool(pool_csv, results_csv, family="drone")
    assert len(pool["index"]) == 39 and 3 not in {int(i) for i in pool["index"]}
    assert set(INPUTS) <= set(pool) and "endurance_h" in pool and "mtow_kg" in pool


def test_inlet_defaults_are_untouched():
    from surrogate.synthetic import make_pool
    p = make_pool(n=16)
    F = replay.to_objectives(p)
    assert np.allclose(F[:, 0], -p["recovery_total"])
    assert tuple(replay.Pool(p).X.shape) == (16, 2)


# ---- the online replay ----

def test_exact_front_has_zero_regret_against_itself():
    from analysis import replay_drone_online as online
    front = online.load_front(FRONT)
    assert front.shape[1] == 2 and len(front) == 249
    ref = ref_point(front)
    assert online.regret(front, front, ref) == pytest.approx(0.0, abs=1e-12)
    half = front[::2]
    assert 0.0 < online.regret(half, front, ref) < 1.0
    assert online.regret(front[:0], front, ref) == pytest.approx(1.0)


def test_online_replay_regret_is_monotone_and_reproducible(fixed, tmp_path):
    from analysis import replay_drone_online as online
    kw = {"front_csv": FRONT, "fixed": fixed, "seeds": range(2), "n_init": 6, "n_max": 10,
          "report_at": (6, 8, 10), "candidates": 128}
    rows = online.run(out_csv=tmp_path / "online.csv", **kw)
    again = online.run(**kw)
    assert [(r["strategy"], r["seed"], r["n"], r["metric"], round(r["value"], 12)) for r in rows] == \
           [(r["strategy"], r["seed"], r["n"], r["metric"], round(r["value"], 12)) for r in again]
    with open(tmp_path / "online.csv") as f:
        read = list(csv.DictReader(f))
    assert tuple(read[0].keys()) == replay.COLUMNS
    assert {r["strategy"] for r in read} == set(replay.STRATEGIES)
    for name in replay.STRATEGIES:
        for seed in range(2):
            reg = [float(r["value"]) for r in read
                   if r["strategy"] == name and int(r["seed"]) == seed and r["metric"] == "hv_regret"]
            assert len(reg) == 3 and all(0.0 <= v <= 1.0 for v in reg)
            if name != "lhs":                      # lhs redraws its whole design at every budget
                assert all(a >= b - 1e-12 for a, b in pairwise(reg))     # observed set only grows
    metrics = {r["metric"] for r in read}
    assert {"hv_regret", "n_gated", "step_seconds", "n_clean"} <= metrics
    # the same initial design for every strategy of a seed: identical regret at n = n_init
    at6 = {r["strategy"]: float(r["value"]) for r in read
           if int(r["n"]) == 6 and int(r["seed"]) == 0 and r["metric"] == "hv_regret"}
    assert len({round(v, 12) for v in at6.values()}) == 1


def test_online_candidates_are_sobol_over_the_box_and_the_pick_is_one_of_them(fixed):
    from analysis import replay_drone_online as online
    cands = online.candidate_set(seed=3, step=5, n=256)
    assert cands.shape == (256, 6)
    assert np.all(cands >= np.asarray(LOW)) and np.all(cands <= np.asarray(HIGH))
    assert not np.allclose(cands, online.candidate_set(seed=3, step=6, n=256))   # fresh per step
    assert np.allclose(cands, online.candidate_set(seed=3, step=5, n=256))       # and reproducible


def test_a_gated_pick_consumes_budget_and_is_counted(fixed, monkeypatch):
    """Force every evaluation after the initial design to fail a gate: n_gated grows with the
    budget, n_clean stays at n_init, and no error escapes."""
    from analysis import replay_drone_online as online
    real = evaluate.evaluate
    clean = {"n": 0}

    def gated_after_init(params, fx, **kw):
        out = real(params, fx, **kw)
        if not out["gates"]:
            clean["n"] += 1
        if clean["n"] > 6:                                   # the initial design is the first 6 clean
            out = {**out, "gates": ["gate 4 (manufacturing floor): forced by the test"]}
        return out

    monkeypatch.setattr(online.evaluate, "evaluate", gated_after_init)
    rows = online.run(front_csv=FRONT, fixed=fixed, strategies=("random",), seeds=(0,), n_init=6,
                      n_max=9, report_at=(6, 9), candidates=64)
    by = {(r["n"], r["metric"]): r["value"] for r in rows}
    assert by[(9, "n_gated")] >= 1 and by[(9, "n_clean")] == 6
    assert by[(9, "hv_regret")] == pytest.approx(by[(6, "hv_regret")])


def test_hypervolume_helpers_agree_with_the_acquisition_module():
    F = np.array([[0.0, 1.0], [1.0, 0.0], [0.5, 0.5], [2.0, 2.0]])
    ref = np.array([3.0, 3.0])
    assert hypervolume_2d(F[pareto_front(F)], ref) == pytest.approx(hypervolume_2d(F[:3], ref))


# ---- feasibility-weighted acquisition, added after the first online run (2026-11-08) ----
# The online run showed EHVI spending 29.7 of 32 picks on gated candidates. The inlet study's
# answer (analysis/replay3r.py) is a logistic feasibility model on the scaled inputs, fitted on
# every evaluated point (clean = 1, gated = 0, the rejected initial draws included), and the
# acquisition multiplied by p(feasible). It is a FIFTH and SIXTH strategy beside the four, never a
# replacement, so the comparison that lost stays on the record. The classifier never picks a point.

def test_feasibility_weighted_strategies_exist_and_run(fixed):
    from analysis import replay_drone_online as online
    assert {"al_ehvi_feas", "al_maxvar_feas"} <= set(online.STRATEGIES)
    assert tuple(online.STRATEGIES[:4]) == tuple(replay.STRATEGIES)
    rows = online.run(front_csv=FRONT, fixed=fixed, strategies=("al_ehvi_feas",), seeds=(0,),
                      n_init=6, n_max=9, report_at=(6, 9), candidates=64)
    metrics = {r["metric"] for r in rows}
    assert {"hv_regret", "n_gated", "n_clean", "p_feasible_of_pick"} <= metrics
    p = [r["value"] for r in rows if r["metric"] == "p_feasible_of_pick" and r["n"] == 9]
    assert len(p) == 1 and 0.0 <= p[0] <= 1.0


def test_feasibility_weighting_avoids_a_synthetic_gate_that_plain_ehvi_walks_into(fixed, monkeypatch):
    """Gate everything with span above 2.1 m (half the box). Plain EHVI, chasing the long-span
    front, keeps picking gated candidates; the weighted one learns the boundary from its own
    rejections and picks fewer, measured over two seeds."""
    from analysis import replay_drone_online as online
    real = evaluate.evaluate

    def gate_long_spans(params, fx, **kw):
        out = real(params, fx, **kw)
        if params["span_m"] > 2.1:
            out = {**out, "gates": ["gate 9 (synthetic): span above 2.1 m"]}
        return out

    monkeypatch.setattr(online.evaluate, "evaluate", gate_long_spans)
    gated = {}
    for name in ("al_ehvi", "al_ehvi_feas"):
        rows = online.run(front_csv=FRONT, fixed=fixed, strategies=(name,), seeds=range(2), n_init=6,
                          n_max=22, report_at=(6, 22), candidates=256)
        gated[name] = sum(r["value"] for r in rows if r["metric"] == "n_gated" and r["n"] == 22)
    assert gated["al_ehvi_feas"] < gated["al_ehvi"], gated

"""Guard the acquisition implementation: on a known toy, EHVI beats random sampling."""
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.stats import qmc

from surrogate.replay import run


def fonseca_fleming_pool(n=96):
    """Fonseca-Fleming with 2 variables on [-2, 2]^2, dressed as a pool: the replay minimises
    f1 = -recovery_total and f2 = log(q_peak), so recovery = -f1 and q = exp(f2)."""
    u = qmc.Sobol(d=2, scramble=True, seed=0).random_base2(7)[:n]
    x = -2.0 + 4.0 * u
    c = 1.0 / np.sqrt(2.0)
    f1 = 1.0 - np.exp(-((x - c) ** 2).sum(1))
    f2 = 1.0 - np.exp(-((x + c) ** 2).sum(1))
    return {"index": np.arange(n), "theta1_deg": 5.0 + 7.0 * u[:, 0],
            "theta2_deg": 5.0 + 9.0 * u[:, 1], "recovery_total": -f1, "q_peak_W_m2": np.exp(f2)}


def replay_one_seed(seed):
    return run(fonseca_fleming_pool(), strategies=("random", "al_ehvi"), seeds=[seed],
               n_init=8, n_max=24, report_at=(24,))


def test_ehvi_beats_random_on_toy():
    with ProcessPoolExecutor(max_workers=4) as pool:      # seeds are independent: run in parallel
        rows = [r for part in pool.map(replay_one_seed, range(10)) for r in part]
    regret = {(r["strategy"], r["seed"]): r["value"] for r in rows if r["metric"] == "hv_regret"}
    wins = sum(regret[("al_ehvi", s)] < regret[("random", s)] for s in range(10))
    print("al_ehvi lower regret than random in", wins, "of 10 seeds")
    assert wins >= 7

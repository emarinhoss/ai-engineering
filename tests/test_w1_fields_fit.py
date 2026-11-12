"""analysis.w1_fields and analysis.w1_fit (tasks W1.5 and W1.6) on small synthetic data."""
import csv
import json

import numpy as np

from analysis import w1_fields, w1_fit
from tests.test_field_pca_gp import family
from worker import startfile as sf


def fake_run(queue, cid, re, alpha, it=3000, done=True, nodes=5):
    d = queue / "runs" / cid
    (d / "status").mkdir(parents=True)
    if done:
        (d / "status" / "2-done").write_text("")
    params = {"camber_pct": 2.0, "thickness_pct": 10.0, "reynolds": re, "alpha_deg": alpha, "max_iter": 6000}
    (d / "result.json").write_text(json.dumps({"run": {"exit_code": 0}, "convergence": {"iterations": it},
                                               "params": params}))
    f = np.full((nodes, 4), 1.0)
    f[:, 3] = 1.0 / re
    (d / "restart_flow.csv").write_text(sf.write_solution(np.zeros((nodes, 2)), f))


def test_field_store_keeps_only_clean_finished_runs(tmp_path):
    q = tmp_path / "q"
    fake_run(q, "a", 1e5, 2.0)
    fake_run(q, "b", 2e5, 6.0)
    fake_run(q, "c", 1e5, 10.0, it=6000)              # used its whole budget
    fake_run(q, "d", 1e5, -2.0, done=False)
    cases = tmp_path / "cases.csv"
    with open(cases, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "set", "design", "alpha_deg", "reynolds"])
        for cid, d in (("a", 0), ("b", 2), ("c", 3), ("d", 5)):
            w.writerow([cid, "w1_field", d, 0, 0])
        w.writerow(["r", "w1_ref", 4, 2.0, 0])
    w1_fields.main(["--queue", str(q), "--cases", str(cases), "--out", str(tmp_path / "out")])
    z = np.load(tmp_path / "out" / "fields.npz")
    s = json.loads((tmp_path / "out" / "fields.json").read_text())
    assert list(z["case_ids"]) == ["a", "b"] and list(z["designs"]) == [0, 2]
    assert s["training_fields"] == 2 and s["planned"] == 4 and set(s["excluded"]) == {"c", "d"}
    assert np.allclose(z["F"][:, :, 3], 1.0)                        # nu_tilde * Re
    assert np.allclose(z["X"][1], [2.0, 10.0, np.log10(2e5), 6.0])


def test_leave_one_design_out_never_sees_the_held_design():
    X, F = family(n=60, B=24)
    designs = np.repeat(np.arange(8), 3)
    errs = w1_fit.leave_one_design_out(X, F, designs, ks=(1, 2))
    assert errs[1].shape == (24, 4) and errs[2].shape == (24, 4)
    assert errs[2].mean() < errs[1].mean()                         # the family has two modes

"""analysis.e0_warmstart: the pass rule fixed in docs/specs/task11_fno_exploration.md."""
from analysis import e0_warmstart as e0


def run(cid, it, cl=1.0, cd=0.01, wall=100.0, dcl=1.0, dcd=5.0, max_iter=6000):
    return {"case_id": cid, "iterations": it, "max_iter": max_iter, "exit_code": 0, "wall_s": wall,
            "cl": cl, "cd": cd, "drift_cl_pct": dcl, "drift_cd_pct": dcd}


def test_saving_and_forces_within_drift():
    p = e0.compare(run("w", 600), run("c", 1000, cd=0.0104), run("d", 500), "angle_step")
    assert abs(p["iter_saving"] - 0.4) < 1e-12
    assert p["cd_within"] and abs(p["cd_dev_pct"] - 100 * 0.0004 / 0.0104) < 1e-9


def test_force_outside_the_cold_twins_drift_fails_the_kind():
    p = e0.compare(run("w", 600, cl=1.02), run("c", 1000), run("d", 500), "angle_step")
    assert not p["cl_within"]
    assert e0.verdict([p])["angle_step"]["verdict"] == "fail"


def test_exhausted_budget_counts_as_no_saving():
    p = e0.compare(run("w", 6000), run("c", 7000, max_iter=8000), run("d", 1), "angle_step")
    assert p["budget_exhausted"] and p["iter_saving"] == 0.0


def test_donor_wall_is_charged_to_the_mesh_step_only():
    w, c, d = run("w", 500, wall=100), run("c", 1000, wall=300), run("d", 400, wall=150)
    assert e0.compare(w, c, d, "mesh_step")["wall_warm_s"] == 250
    assert e0.compare(w, c, d, "angle_step")["wall_warm_s"] == 100


def test_median_rule_at_the_30_percent_boundary():
    ps = [e0.compare(run("w", it), run("c", 1000), run("d", 1), "mesh_step") for it in (700, 600, 900)]
    v = e0.verdict(ps)["mesh_step"]
    assert abs(v["median_iter_saving"] - 0.3) < 1e-12 and v["verdict"] == "pass"
    assert e0.verdict(ps)["angle_step"]["verdict"] == "not run"

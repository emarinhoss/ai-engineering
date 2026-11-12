"""analysis.w1_warmstart: the conditions of the approved W1 rule (task W1.7), one test per condition."""
from analysis import w1_warmstart as w


def run(it=3000, cl=1.0, cd=0.01, wall=100.0, max_iter=6000, exit_code=0, worker="w"):
    return {"case_id": "x", "exit_code": exit_code, "iterations": it, "max_iter": max_iter, "wall_s": wall,
            "cl": cl, "cd": cd, "drift_cl_pct": 0.1, "drift_cd_pct": 0.1, "worker_id": worker}


def case(near=60.0, learn=50.0, ref=True, cold=(100.0, 100.0), **warm):
    """One case: two cold runs, two runs of each warm start; warm keys change both warm starts."""
    return {"cold": [run(wall=cold[0]), run(wall=cold[1])],
            "near": [run(wall=near, **warm), run(wall=near, **warm)],
            "learn": [run(wall=learn, **warm), run(wall=learn, **warm)],
            "ref": run(max_iter=20000) if ref else None}


def cases(**kw):
    return {f"c{i}": case(**kw) for i in range(7)}


def test_good_cases_pass_both_starts_and_the_learning_adds():
    v = w.judge(cases())
    assert v["near"]["verdict"] == "pass" and v["learn"]["verdict"] == "pass"
    assert abs(v["near"]["median_saving"] - 0.4) < 1e-12 and abs(v["learn"]["median_saving"] - 0.5) < 1e-12
    assert v["learning_adds"]["result"] == "better" and abs(v["learning_adds"]["median"] - 0.1) < 1e-12


def test_condition_1_an_exhausted_or_failed_run_fails():
    c = cases()
    c["c0"]["learn"][1] = run(wall=50.0, it=6000)
    assert w.judge(c)["learn"]["verdict"] == "fail" and w.judge(c)["near"]["verdict"] == "pass"
    c["c0"]["learn"][1] = run(wall=50.0, exit_code=1)
    assert not w.judge(c)["learn"]["runs_cleanly"]


def test_condition_2_answer_within_two_percent_of_the_reference():
    assert w.judge(cases(cd=0.01019))["learn"]["answer_vs_reference"]          # 1.9 %
    v = w.judge(cases(cd=0.01021))                                              # 2.1 %
    assert not v["learn"]["answer_vs_reference"] and v["learn"]["verdict"] == "fail"
    c = cases()
    c["c0"] = case(ref=False, cl=1.5)                     # no valid reference: condition 2 not applied
    assert w.judge(c)["learn"]["answer_vs_reference"]


def test_condition_3_saving_of_thirty_percent_and_three_times_the_noise():
    assert w.judge(cases(near=75.0))["near"]["verdict"] == "fail"               # 25 % < 30 %
    noisy = cases(near=60.0, learn=60.0, cold=(80.0, 120.0))                    # saving 40 %, spread 40 %
    v = w.judge(noisy)
    assert abs(v["noise"] - 0.4) < 1e-12 and v["learn"]["faster"] is False and v["learn"]["verdict"] == "fail"


def test_two_workers_void_the_timing():
    c = cases()
    c["c3"]["near"][0]["worker_id"] = "other"
    v = w.judge(c)
    assert v["one_worker"] is False and v["learn"]["faster"] == "void" and v["learn"]["verdict"] == "fail"


def test_five_points_better_than_the_nearest_case_is_no_better():
    v = w.judge(cases(near=55.0, learn=50.0))
    assert v["learn"]["verdict"] == "pass" and v["learning_adds"]["result"] == "no better"


def test_learning_adds_is_not_judged_when_the_learned_start_fails():
    assert w.judge(cases(learn=75.0))["learning_adds"]["result"] == "not judged"


def test_fewer_than_five_valid_references_is_not_evaluated():
    c = cases()
    for k in ("c0", "c1", "c2"):
        c[k]["ref"] = None
    v = w.judge(c)
    assert v["verdict"] == "not evaluated" and v["valid_references"] == 4

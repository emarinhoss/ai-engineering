"""analysis.s2r_numerics: the conditions of the approved S2R rule."""
from analysis import s2r_numerics as s


def run(it=3000, cl=1.0, cd=0.01, wall=100.0, dcl=0.1, dcd=0.1, max_iter=6000, exit_code=0):
    return {"case_id": "x", "exit_code": exit_code, "iterations": it, "max_iter": max_iter, "wall_s": wall,
            "cl": cl, "cd": cd, "drift_cl_pct": dcl, "drift_cd_pct": dcd, "worker_id": "w"}


def case(tol_wall=60.0, ref=True, **tol):
    return s.judge_case([run(), run()], [run(wall=tol_wall, **tol), run(wall=tol_wall, **tol)],
                        run(max_iter=20000) if ref else None)


def test_answer_checks_against_baseline_and_reference():
    j = case(cl=1.004, cd=0.01009)                    # 0.4 % and 0.9 % from the baseline: inside
    assert j["cl_base_ok"] and j["cd_base_ok"] and j["cl_ref_ok"]
    j = case(cd=0.01019)                              # 1.9 % from the baseline: outside 1 %
    assert not j["cd_base_ok"] and j["cd_ref_ok"]     # but inside 2 % of the reference
    j = case(ref=False, cl=1.03)
    assert "cl_ref_ok" not in j and not j["cl_base_ok"]
    assert abs(case()["saving"] - 0.4) < 1e-12


def test_pass_needs_all_conditions_one_worker_and_five_references():
    good = {f"c{i}": case() for i in range(7)}
    assert s.judge(good, 6, True)["verdict"] == "pass"
    assert s.judge(good, 4, True)["verdict"] == "not evaluated"
    v = s.judge(good, 6, False)
    assert v["verdict"] == "fail" and v["faster"] == "void"
    assert s.judge({**good, "c0": case(it=6000)}, 6, True)["verdict"] == "fail"       # exhausted
    assert s.judge({**good, "c0": case(cd=0.0103)}, 6, True)["verdict"] == "fail"     # moved
    slow = {f"c{i}": case(tol_wall=75.0) for i in range(7)}                           # 25 % < 30 %
    assert s.judge(slow, 6, True)["verdict"] == "fail"


def test_saving_must_be_three_times_the_repeat_spread():
    noisy = {f"c{i}": s.judge_case([run(wall=80), run(wall=120)], [run(wall=60), run(wall=60)], None)
             for i in range(7)}                       # saving 40 %, spread 40 %: not resolved
    v = s.judge(noisy, 6, True)
    assert abs(v["noise"] - 0.4) < 1e-12 and v["faster"] is False and v["verdict"] == "fail"

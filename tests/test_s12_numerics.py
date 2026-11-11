"""analysis.s12_numerics: the three conditions of the approved S1/S2 rule."""
from analysis import s12_numerics as s


def run(it=3000, cl=1.0, cd=0.01, wall=100.0, dcl=0.1, dcd=0.1, max_iter=6000, exit_code=0):
    return {"case_id": "x", "exit_code": exit_code, "iterations": it, "max_iter": max_iter, "wall_s": wall,
            "cl": cl, "cd": cd, "drift_cl_pct": dcl, "drift_cd_pct": dcd}


def test_reference_needs_clean_stop_and_small_drift():
    assert s.reference_valid(run(max_iter=20000))
    assert not s.reference_valid(run(dcd=0.25)) and not s.reference_valid(run(it=20000, max_iter=20000))


def test_answer_allowed_is_the_larger_of_baseline_distance_and_the_floor():
    ref = run()
    j = s.judge_case(run(cl=1.004, cd=0.01012, wall=60), ref, run(cl=1.001), run(cl=1.002, wall=120))
    assert j["cl_ok"] and abs(j["cl_allowed"] - 0.005) < 1e-12        # floor 0.5 % applies
    assert not j["cd_ok"] and abs(j["cd_distance"] - 0.012) < 1e-9    # 1.2 % > floor 1.0 %
    assert abs(j["wall_saving"] - (1 - 60 / 110)) < 1e-12
    j = s.judge_case(run(cd=0.01025), ref, run(cd=0.0103), run())     # baseline itself is 3 % away
    assert j["cd_ok"] and abs(j["cd_allowed"] - 0.03) < 1e-9


def _cases(walls, **kw):
    return [s.judge_case(run(wall=w, **kw), run(), run(), run()) for w in walls]


def test_three_conditions_and_the_minimum_of_four_cases():
    assert s.judge_setting(_cases((60, 65, 70, 90)), 0.02)["verdict"] == "pass"       # median 32.5 %
    assert s.judge_setting(_cases((60, 66, 76, 90)), 0.02)["verdict"] == "fail"       # median 29 %
    assert s.judge_setting(_cases((60, 60, 60, 60), it=6000), 0.02)["verdict"] == "fail"   # exhausted
    assert s.judge_setting(_cases((60, 60, 60, 60), cl=1.02), 0.02)["verdict"] == "fail"   # answer moved
    assert s.judge_setting(_cases((60, 60, 60)), 0.02)["verdict"] == "not evaluated"
    assert s.judge_setting(_cases((60, 65, 70, 90)), 0.2)["resolved"] is False

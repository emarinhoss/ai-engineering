"""Review S3A-2 to S3A-5 and S3A-10 (Stage 3 perf on an App. L record). Hand numbers.

For an App. L record the closed forms (5.118)/(5.121) assume power available independent of speed, which the
disk does not give, so the sea-level rate of climb and the best-climb speed are not judged and carry a bracket;
the excess-power row is the coding check. Flat records keep their rows."""
import math
from pathlib import Path

import pytest

from conceptual.units import KT
from measurement import stage3_perf as sp

ROOT = Path(__file__).resolve().parents[2]
NEW_RECORD = ROOT / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json"
OLD_RECORD = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"


@pytest.fixture(scope="module")
def new_perf():
    return sp.compute(NEW_RECORD)


@pytest.fixture(scope="module")
def old_perf():
    return sp.compute(OLD_RECORD)


def rows_of(res):
    return {r["id"]: r for r in res["rows"]}


def test_app_l_climb_rows_are_not_judged_and_the_excess_power_row_is_the_coding_check(new_perf):
    r = rows_of(new_perf)
    for rid in ("roc_sl", "v_best_climb"):
        assert r[rid]["verdict"] == "not judged" and r[rid]["tolerance"] is None
        assert "numerically_within" not in r[rid]
    e = r["roc_sl_excess_power"]
    assert e["class"] == sp.CODING and e["verdict"] == "within" and abs(e["deviation"]) < 1e-9


def test_app_l_bracket_by_hand(new_perf):
    """The bracket ends differ only in the disk efficiency, so upper - lower = (eta_hi - eta_lo) P 550/W0 x 60 ft/min
    (the speed-dependent drag term of (5.121) is the same in both). Record: P 450 hp, W0 3,160.3 lb. Read from the
    record: efficiencies 0.5902 at 64.6 kt and 0.7195 at 99.0 kt; rates about 2,238 and 2,845 ft/min, Stage 1 2,636."""
    br = new_perf["climb_bracket"]
    d = sp.json.loads(NEW_RECORD.read_text())
    diff = (br["eta_at_stage1_speed"] - br["eta_at_closed_form_speed"]) * d["bhp_sl"] * 550.0 / d["W0_lb"] * 60.0
    assert br["roc_upper_fpm"] - br["roc_lower_fpm"] == pytest.approx(diff, rel=1e-12)
    assert br["roc_lower_fpm"] == pytest.approx(2238, abs=1) and br["roc_upper_fpm"] == pytest.approx(2845, abs=1)
    assert br["eta_at_closed_form_speed"] == pytest.approx(0.5902, abs=1e-4)
    assert br["eta_at_stage1_speed"] == pytest.approx(0.7195, abs=1e-4)
    assert br["v_closed_form_kt"] == pytest.approx(64.6, abs=0.05)
    assert br["stage1_inside_roc_bracket"] and br["stage1_inside_ceiling_bracket"]
    assert br["roc_lower_fpm"] < br["roc_stage1_fpm"] < br["roc_upper_fpm"]
    # Stage 1's speed is above the 1.2 V_stall floor (1.67 V_stall), so the old text "lands on the floor" was false
    assert br["v_stage1_kt"] > br["v_floor_kt"] and br["v_stage1_over_v_stall"] == pytest.approx(1.673, abs=1e-3)
    assert br["ceiling_lower_ft"] < br["ceiling_stage1_ft"] < br["ceiling_upper_ft"]


def test_app_l_notes_and_report_state_the_real_cause(new_perf):
    r = rows_of(new_perf)
    assert "independent of speed" in r["roc_sl"]["note"] and "Not judged" in r["roc_sl"]["note"]
    assert "floor" in r["v_best_climb"]["note"] and "above the floor" in r["v_best_climb"]["note"]
    assert "lands on that floor" not in r["v_best_climb"]["note"]
    assert "upper bound" in r["ceiling"]["note"] and "lower bound" in r["ceiling"]["note"]
    res = dict(new_perf, summary={v: sum(x["verdict"] == v for x in new_perf["rows"])
                                  for v in ("within", "outside", "not judged", "not computed")},
               inputs={"design": "d", "design_sha256": "x", "git_commit": "c", "python": "p", "numpy": "n",
                       "git_dirty": False, "git_dirty_files": []})
    text = sp.report_text(res)
    assert "lands on that floor" not in text and "agrees to" not in text
    assert "Rows not judged: closed form does not apply" in text and "not coding errors" in text
    assert "working tree clean" in text
    res["inputs"].update(git_dirty=True, git_dirty_files=[" M measurement/x.py"])
    assert "working tree DIRTY:  M measurement/x.py" in sp.report_text(res)


def test_anderson_w0_note_states_the_held_efficiencies(new_perf):
    note = rows_of(new_perf)["w0_first"]["note"]
    aw = new_perf["anderson_w0"]
    assert "eta_p from the record" not in note and "SFC used, eta_p" not in note
    assert "held constant while W0 iterates" in note
    assert f"cruise {aw['eta_cruise']:.4f}" in note and f"loiter {aw['eta_loiter']:.4f}" in note


def test_flat_record_keeps_its_climb_rows(old_perf):
    r = rows_of(old_perf)
    assert "roc_sl_excess_power" not in r and old_perf["climb_bracket"] is None
    assert r["roc_sl"]["tolerance"] == 0.03 and r["roc_sl"]["verdict"] in ("within", "outside")
    assert r["v_best_climb"]["tolerance"] == 0.03 and "lands on that floor" in r["v_best_climb"]["note"]


def test_diagnosis_wording_for_a_row_outside_tolerance_does_not_say_agrees():
    res = {"rows": [{"id": "roc_sl", "deviation": 0.0793, "tolerance": 0.03, "deviation_kind": "relative",
                     "unit": "ft/min", "verdict": "outside"}], "climb_bracket": None}
    txt = sp._diag_best_climb(res, {"stage1": 99.0, "stage3": 64.6})
    assert "agrees" not in txt and "+7.93 %" in txt and "outside" in txt and "+-3 %" in txt


def test_two_comparison_sections_have_distinct_headings(new_perf):
    res = dict(new_perf, summary={v: sum(x["verdict"] == v for x in new_perf["rows"])
                                  for v in ("within", "outside", "not judged", "not computed")},
               inputs={"design": "new", "design_sha256": "x", "git_commit": "c", "python": "p", "numpy": "n"})
    cmp_ = {"old_perf": "a/perf.json", "old_perf_sha256": "s", "old_design": "o", "old_git_commit": "g",
            "new_design": "new", "rows": [], "rows_only_in_old": []}
    res["comparisons"] = [dict(cmp_, old_perf="a/perf.json"), dict(cmp_, old_perf="b/perf.json")]
    heads = [ln for ln in sp.report_text(res).splitlines() if ln.startswith("## Against an earlier record")]
    assert len(heads) == 2 and heads[0] != heads[1]


def test_git_dirty_files_returns_a_list():
    assert isinstance(sp.git_dirty_files(), list)

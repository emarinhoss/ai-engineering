"""Stage 3 regression against committed records (review S3A-7): the row id sets are asserted (a dropped row fails),
a TP100 flat record, the M250 flat engine rows, and the App. L record against its own perf.json."""
import json
from pathlib import Path

import pytest

from measurement import stage3_engine as se
from measurement import stage3_perf as sp

ROOT = Path(__file__).resolve().parents[2]
S3 = ROOT / "runs/task12/stage3"
OLD_RECORD = S3 / "2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"
NEW_RECORD = S3 / "2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json"
TP100_RECORD = ROOT / "runs/task12/stage1/2026-11-21f/design_pusher.json"
TP100_PERF = S3 / "2026-11-22/perf.json"
OLD_RERUN = S3 / "2026-11-26/m250_baseline_measure_rerun/perf.json"
OLD_ENGINE = S3 / "2026-11-24/m250_baseline_measure/engine.json"
NEW_PERF = S3 / "2026-11-26/m250_baseline_appl_measure/perf.json"


def close(a, b, rel=1e-9):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(close(x, y, rel) for x, y in zip(a, b))
    if isinstance(a, dict):
        return set(a) == set(b) and all(close(a[k], b[k], rel) for k in a)
    if isinstance(a, bool) or isinstance(a, str):
        return a == b
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-300) if a != b else True


def ids(res):
    return [r["id"] for r in res["rows"]]


# ---- TP100 flat record ---------------------------------------------------------------------------------
def test_tp100_flat_perf_reproduces_the_recorded_rows():
    """2026-11-22/perf.json: every recorded Stage 1 and Stage 3 value to 1e-9 except cd0 (method changed by G-3).
    Differences in the row set, by hand: the recorded file has the two static-margin rows (they moved to
    stage3_aero), the new code adds the three propeller rows (G-4)."""
    new = sp.compute(TP100_RECORD)
    rec = json.loads(TP100_PERF.read_text())
    assert set(ids(new)) - set(ids(rec)) == {"prop_eta_climb", "prop_eta_cruise", "prop_eta_loiter"}
    assert set(ids(rec)) - set(ids(new)) == {"sm_full", "sm_empty"}
    old = {r["id"]: r for r in rec["rows"]}
    for r in new["rows"]:
        if r["id"] in old and r["id"] != "cd0":
            for k in ("stage1", "stage3"):
                assert close(old[r["id"]][k], r[k]), (r["id"], k)
    assert new["climb_bracket"] is None and "roc_sl_excess_power" not in ids(new)


# ---- M250 flat record: row ids, verdicts, classes against the same-code rerun ----------------------------------
def test_old_flat_record_row_ids_verdicts_and_classes_match_the_committed_rerun():
    new = sp.compute(OLD_RECORD)
    rec = json.loads(OLD_RERUN.read_text())
    assert ids(new) == ids(rec)
    for r, o in zip(new["rows"], rec["rows"]):
        assert r["verdict"] == o["verdict"] and r["class"] == o["class"], r["id"]
        for k in ("stage1", "stage3"):
            assert close(o[k], r[k]), (r["id"], k)


# ---- M250 flat engine rows (the _level_power / _segment_points path and the engine ceiling) ----------------------
@pytest.fixture(scope="module")
def old_engine():
    return se.measure_record(OLD_RECORD)           # about a minute


def test_old_flat_engine_rows_reproduce_the_recorded_engine_json(old_engine):
    rec = json.loads(OLD_ENGINE.read_text())
    assert ids(old_engine) == ids(rec)
    for r, o in zip(old_engine["rows"], rec["rows"]):
        assert r["verdict"] == o["verdict"], r["id"]
        for k in ("stage1", "stage3"):
            assert close(o[k], r[k]), (r["id"], k)


# ---- App. L record against its own perf.json -----------------------------------------------------------------------
def test_app_l_record_reproduces_its_own_perf_json():
    new = sp.compute(NEW_RECORD)
    rec = json.loads(NEW_PERF.read_text())
    assert ids(new) == ids(rec)
    assert set(ids(new)) == {"power_climb_sl", "power_ceiling", "power_takeoff", "power_turn", "power_cruise",
                             "mission_fuel", "w0_first", "w0_buildup", "cd0", "prop_eta_climb", "prop_eta_cruise",
                             "prop_eta_loiter", "v_best_range", "v_best_endurance", "roc_sl", "roc_sl_excess_power",
                             "v_best_climb", "ceiling", "takeoff_distance", "landing_distance", "v_corner", "gust_n"}
    for r, o in zip(new["rows"], rec["rows"]):
        assert r["verdict"] == o["verdict"] and r["class"] == o["class"], r["id"]
        for k in ("stage1", "stage3"):
            assert close(o[k], r[k]), (r["id"], k)
    assert close(new["climb_bracket"], rec["climb_bracket"])
    for k in ("W0", "fuel_fraction", "eta_cruise", "eta_loiter", "buildup_W0"):
        assert close(new["anderson_w0"][k], rec["anderson_w0"][k]), k
    for g, o in zip(new["mission_legs"], rec["mission_legs"]):
        assert close(g["fraction_stage3"], o["fraction_stage3"]), g["segment"]
    assert rec["inputs"]["git_dirty"] is False

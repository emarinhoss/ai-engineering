"""Perf report fixes of 2026-11-25 on the M250 baseline record: row classes (S3M-4), the 7.1b rows not
judged, CD0 with Anderson's propeller Cfe (S3M-2, G-3), the take-off power diagnosis (S3M-7) and the
generated report sections (S3M-11)."""
import math
from pathlib import Path

import pytest

from measurement import anderson as A
from measurement import stage3_perf as sp

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"


@pytest.fixture(scope="module")
def res():
    r = sp.compute(RECORD)
    r["inputs"] = {"design": str(RECORD), "design_sha256": "x", "git_commit": "x", "python": "x", "numpy": "x"}
    r["summary"] = {v: sum(x["verdict"] == v for x in r["rows"]) for v in ("within", "outside", "not judged", "not computed")}
    return r


def row(res, rid):
    return next(r for r in res["rows"] if r["id"] == rid)


def test_every_row_has_a_class(res):
    for r in res["rows"]:
        assert r["class"] in sp.CLASSES, r["id"]
    for rid in ("power_climb_sl", "power_turn", "power_cruise", "v_best_range", "v_best_endurance", "roc_sl", "v_corner"):
        assert row(res, rid)["class"] == sp.CODING
    for rid in ("cd0", "prop_eta_climb", "prop_eta_cruise", "prop_eta_loiter"):
        assert row(res, rid)["class"] == sp.INDEPENDENT


def test_the_three_7_1b_rows_are_not_judged_but_keep_their_numbers(res):
    for rid in ("power_ceiling", "ceiling", "mission_fuel"):
        r = row(res, rid)
        assert r["verdict"] == "not judged" and r["tolerance"] is not None
        assert r["numerically_within"] == (abs(r["deviation"]) <= r["tolerance"])


def test_ceiling_row_carries_the_clamp_note(res):
    assert "lean on that clamp" in row(res, "ceiling")["note"]


def test_cd0_uses_anderson_propeller_cfe_by_hand(res):
    c = res["cd0_detail"]
    assert c["Cfe"] == A.CFE_PROPELLER == 0.0043
    assert row(res, "cd0")["stage3"] == pytest.approx(c["S_wet_over_S"] * 0.0043)    # (2.37)
    # jet curve beside it: 1.5 x 0.42/ln(0.056 Re)^2
    cfe = 1.5 * 0.42 / math.log(0.056 * c["Re_fuselage"]) ** 2
    assert c["Cfe_jet_curve"] == pytest.approx(cfe)
    assert c["CD0_jet_curve"] == pytest.approx(c["S_wet_over_S"] * cfe)
    assert c["CD0_jet_curve"] < row(res, "cd0")["stage3"]


def test_takeoff_power_grows_with_k_TO_and_distances_are_consistent(res):
    t = res["takeoff_power_detail"]
    k = t["mattingly_hp_by_k_TO"]
    assert k["1.15"] < k["1.2"] < k["1.25"]
    assert k["1.2"] == pytest.approx(row(res, "power_takeoff")["stage3"], rel=1e-9)
    rs = t["raymer_at_stage1_hp"]
    assert rs["total"] == pytest.approx(t["field_length_ft"], abs=1.0)
    assert rs["total"] == pytest.approx(rs["ground_roll"] + rs["rotation"] + rs["transition"] + rs["climb"])
    assert t["raymer_at_mattingly_hp"]["total"] > 1.5 * t["field_length_ft"]     # near zero gradient


def test_report_is_generated_from_the_record(res):
    text = sp.report_text(res)
    assert "Added after the run" not in text
    assert "| Class |" in text and "coding check" in text
    aw = res["anderson_w0"]
    assert f"{aw['W0']:,.0f} lb" in text and f"{aw['buildup_W0']:,.0f} lb" in text      # G-2: three values
    t = res["takeoff_power_detail"]
    assert f"{t['raymer_at_stage1_hp']['climb']:,.0f} ft" in text                       # S3M-7 tied to numbers
    assert "a larger k_TO needs more power" in text
    assert "unfactored" in text                                                         # G-1


def test_prop_fixed_point_raises_when_it_does_not_converge(monkeypatch):
    flip = iter(range(10 ** 6))
    monkeypatch.setattr(sp.M, "real_propeller_efficiency", lambda *a, **k: 0.5 + 0.1 * (next(flip) % 2))
    with pytest.raises(ValueError):
        sp._prop_eta_fixed_point(450.0, 100.0, 0.002377, 6.9)

"""measurement/appl_decomposition.py (review S3A-1): hand numbers and identities, no tuning."""
from pathlib import Path

import pytest

from conceptual import sizing
from measurement import appl_decomposition as ad

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05"
NEW = ROOT / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05"


@pytest.fixture(scope="module")
def res():
    return ad.run(OLD, NEW)


def test_split_by_hand(res):
    """Read from the two target_result.json: W0 3,116.94 -> 3,160.31 lb (+43.37), sized loiter 8.78125 -> 9.03125 h
    (+0.25 h, eight lattice steps of 1/32 h)."""
    s = res["split"]
    assert s["W0_lb"]["change"] == pytest.approx(43.37, abs=0.01)
    assert s["L_sized_h"]["change"] == pytest.approx(0.25, abs=1e-12)
    # W0 = fuel + empty + the rest (payload and fixed): the rest is the same in both records
    assert s["W0_minus_fuel_minus_We_lb"]["old"] == pytest.approx(s["W0_minus_fuel_minus_We_lb"]["new"], abs=1e-3)   # W0 closure tolerance
    assert s["W0_lb"]["change"] == pytest.approx(s["fuel_lb"]["change"] + s["We_lb"]["change"], abs=1e-3)


def test_worst_case_reproduces_the_record(res):
    """The rebuild at the record's worst endurance point and hours gives the record's fuel (the hours are defined
    by that), and the segment weights lost, with the landing allowance, equal fuel/reserve factor."""
    c = res["cases"]["new_worst_disk"]
    assert c["fuel_with_reserve_lb"] == pytest.approx(977.27, abs=0.05)
    landing = (c["W0_lb"] - sum(c["segment_fuel_lb"].values())) * (1.0 - sizing.LANDING_FRACTION)
    assert sum(c["segment_fuel_lb"].values()) + landing == pytest.approx(c["fuel_with_reserve_lb"] / sizing.RESERVE_FACTOR, rel=1e-9)
    assert res["hours_on_station"]["new_worst_flat_eta_low"] > res["hours_on_station"]["new_worst_disk"]


def test_swap_changes_only_the_propeller(res):
    a, b = res["cases"]["new_worst_disk"], res["cases"]["new_worst_flat_eta_low"]
    assert a["W0_lb"] == pytest.approx(b["W0_lb"], rel=1e-12)             # same aircraft
    assert b["mean_eta"]["cruise_out"] == pytest.approx(res["swapped_values"]["flat_eta_p_low_end_old_record"], rel=1e-12)
    assert a["climb"]["eta_mid_altitude"] < b["climb"]["eta_mid_altitude"]

"""Anderson's static-margin route, (8.76)-(8.78) p. 444 (owner ruling G-5), by hand-computed numbers, and
the aero runner's rows on the M250 baseline record."""
import json
from pathlib import Path

import pytest

from conceptual import raymer_stability as stab
from conceptual import uav
from measurement import anderson as A
from measurement import stage3_aero

ROOT = Path(__file__).resolve().parents[2]
M250_RECORD = ROOT / "runs/task12/stage3/2026-11-24/m250_baseline_ws16_a7/P450/h1.05/design_pusher.json"


def test_tail_volume_by_hand():
    # l_HT 15 ft, S_HT 20 ft^2, S 100 ft^2, MAC 5 ft: 15 * 20 / (5 * 100) = 0.6
    assert A.horizontal_tail_volume(15.0, 20.0, 100.0, 5.0) == pytest.approx(0.6)


def test_neutral_point_and_margin_by_hand():
    # x_acwb 10 ft, V_HT 0.6, a_t/a = 3.6/4.5 = 0.8, MAC 5 ft: x_n = 10 + 0.6 * 5 * 0.8 = 12.4 ft
    x_n = A.neutral_point(10.0, 5.0, 0.6, 3.6, 4.5)
    assert x_n == pytest.approx(12.4)
    # (8.77): CG at 11.9 ft -> (12.4 - 11.9)/5 = 0.1
    assert A.static_margin(x_n, 11.9, 5.0) == pytest.approx(0.1)
    # (8.76) solved the other way returns the wing-body center
    assert A.x_acwb_from_neutral_point(x_n, 5.0, 0.6, 3.6, 4.5) == pytest.approx(10.0)
    # downwash factor 0.5 halves the tail term: 10 + 2.4 * 0.5 = 11.2
    assert A.neutral_point(10.0, 5.0, 0.6, 3.6, 4.5, 0.5) == pytest.approx(11.2)


def test_book_example_margin_is_ten_percent():
    # (8.78) example p. 444: x_n = 8.387 ft, CG 7.87 ft, MAC 5.17 ft -> 0.517/5.17 = 0.1
    assert A.static_margin(8.387, 7.87, 5.17) == pytest.approx(0.1, abs=1e-6)


def test_with_downwash_and_efficiency_it_is_raymers_16_9():
    # wing: CLa 5.0, AC at 0.25 MAC, fuselage Cm_alpha 0.1; tail: eta 0.9, S_h/S 0.2, a_t 3.8, 1 - eps' = 0.55, AC at 3.0 MAC
    X_acwb = 0.25 - 0.1 / 5.0
    V_HT = A.horizontal_tail_volume(3.0 - X_acwb, 0.2, 1.0, 1.0)
    f = 0.9 * 0.55
    a = 5.0 + 0.2 * 3.8 * f
    x_n = A.neutral_point(X_acwb, 1.0, V_HT, 3.8, a, f)
    assert x_n == pytest.approx(0.4238, abs=1e-4)            # by hand: 0.23 + 0.554 * (3.8/5.3762) * 0.495
    assert x_n == pytest.approx(stab.neutral_point(5.0, 0.25, 0.1, 0.9, 0.2, 3.8, 0.55, 3.0), rel=1e-12)


@pytest.fixture(scope="module")
def aero():
    d = json.loads(M250_RECORD.read_text())
    L, _ = uav.load_ledger(M250_RECORD.parent / "ledger.yaml")
    return stage3_aero.measure(d, L)


def test_runner_anderson_rows(aero):
    rows = {(r["fuel"], r["anderson"]): r for r in aero["rows"] if "anderson" in r}
    assert len(rows) == 4
    for fuel in ("full", "empty"):
        lat = rows[(fuel, "lattice")]
        assert lat["measured"] == pytest.approx(lat["lattice_row"], abs=1e-9)     # algebraically the same model
        assert lat["verdict"].startswith("not judged")
        assert rows[(fuel, "printed")]["measured"] > lat["measured"]              # neglecting downwash adds margin
        assert lat["raymer"] == pytest.approx(next(r for r in aero["rows"] if r["quantity"] == f"static margin, {fuel} fuel, MAC")["raymer"])


def test_runner_r13_by_construction(aero):
    se = aero["info"]["static_margin_sensitivity"]
    assert se["margin_sum"] == pytest.approx(0.2, abs=1e-6)           # centred in the 0.05-0.15 band
    assert se["empty_margin_per_0.1_gradient"] < 0.0
    # the floor is reached at a gradient above the nominal one
    nominal = next(r for r in aero["rows"] if r["quantity"].startswith("downwash"))["measured"]
    assert se["gradient_where_empty_margin_reaches_floor"] > nominal


def test_tail_heights_stay_outside_the_wake_sheet():
    d = json.loads(M250_RECORD.read_text())
    L, _ = uav.load_ledger(M250_RECORD.parent / "ledger.yaml")
    nominal, zs = stage3_aero.tail_heights(d, L)
    assert nominal == pytest.approx(0.4 * d["fuselage"]["diameter"])
    assert min(zs) >= 0.5 * d["wing"]["span"] / 30.0

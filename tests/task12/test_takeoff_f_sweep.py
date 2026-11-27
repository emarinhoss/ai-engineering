"""measurement/takeoff_f_sweep.py (review APL-5, ruling G-9)."""
from pathlib import Path

import pytest

from measurement import takeoff_f_sweep as ts

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05"


# the App. L baseline and the W/S 13 A 8 baseline (ruling B-9b): the tool takes the record directory as it is
REC_WS13A8 = ROOT / "runs/task12/stage3/2026-11-26/m250_bands_cells/ws13_a8"


@pytest.fixture(scope="module", params=[REC, REC_WS13A8], ids=["appl", "ws13_a8"])
def res(request):
    return ts.run(request.param)


def test_f085_reproduces_the_record(res):
    r = next(x for x in res["sweep"] if x["f"] == 0.85)
    assert res["record_f"] == 0.85
    assert r["takeoff_over_50ft_ft"] == pytest.approx(res["record_takeoff_ft"], rel=1e-9)
    assert r["landing_over_50ft_ft"] == pytest.approx(res["record_landing_ft"], rel=1e-9)


def test_takeoff_falls_with_f_and_landing_unchanged(res):
    to = [r["takeoff_over_50ft_ft"] for r in res["sweep"]]
    assert all(a > b for a, b in zip(to, to[1:]))
    assert all(r["landing_over_50ft_ft"] == res["sweep"][0]["landing_over_50ft_ft"] for r in res["sweep"])

"""measurement/vn_check.py reproduces the frozen design's own V-n and gust entries at V_C and V_D (ruling B-4)."""
from pathlib import Path

import pytest

from measurement import vn_check

DESIGN = Path(__file__).resolve().parents[2] / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json"


@pytest.fixture(scope="module")
def res():
    return vn_check.compute(DESIGN)


def test_reproduces_record_vn_and_gusts_at_vc_and_vd(res):
    assert vn_check.worst_reproduction_error(res) < 1e-5


def test_speeds(res):
    assert res["V_C_eas_kt"] == pytest.approx(115.0)
    assert res["V_D_eas_kt"] == pytest.approx(172.5)
    assert res["level_top_speed_eas_kt"]["sea_level"] > res["V_D_eas_kt"]


def test_gust_u_de_falls_to_half_at_vd_and_load_grows_with_speed_at_fixed_u(res):
    pts = {(p["altitude"], p["speed"]): p for p in res["points"]}
    assert pts[("sea_level", "V_C")]["U_de_fps"] == pytest.approx(30.0)
    assert pts[("sea_level", "V_D")]["U_de_fps"] == pytest.approx(15.0)
    assert pts[("sea_level", "level_top_speed")]["U_de_fps"] == pytest.approx(15.0)

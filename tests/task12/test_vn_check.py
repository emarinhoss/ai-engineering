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


def test_report_quotes_the_designs_own_speeds(res):
    """The report text takes V_C and V_D from the result, not from a fixed design."""
    res = dict(res, V_C_eas_kt=110.0, V_D_eas_kt=165.0, worst_relative_reproduction_error=0.0)
    res["inputs"] = {"command": "python -m measurement.vn_check --out x.json", "design": "d", "design_sha256": "0" * 64,
                     "git_commit": "0" * 40, "git_dirty": False}
    text = vn_check.report_text(res)
    assert "V_C 110 kt EAS" in text and "V_D 165 kt EAS" in text
    assert "sized at V_C 110 kt EAS" in text and "sized at V_C 115" not in text

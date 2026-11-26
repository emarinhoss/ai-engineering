"""measurement/stage1_compliance.py rebuilds the frozen design through Stage 1 and reproduces its record (ruling B-7)."""
from pathlib import Path

import pytest

from measurement import stage1_compliance as sc

DESIGN = Path(__file__).resolve().parents[2] / "runs/task12/stage3/2026-11-25/m250_baseline_appl/P450/h1.05/design_pusher.json"


@pytest.fixture(scope="module")
def built():
    return sc.rebuild(DESIGN)


def test_rebuild_reproduces_record(built):
    _, check, _ = built
    assert max(abs(v["relative_difference"]) for v in check.values()) < sc.REPRODUCE_TOLERANCE


def test_no_row_fails_and_r9_negative_limit_is_minus_1_7(built):
    rows, _, _ = built
    assert not [r["requirement"] for r in rows if r["met"] is False]
    neg = next(r for r in rows if r["requirement"].startswith("R9 negative"))
    assert neg["limit"] == pytest.approx(-1.7)

"""The Colab record summary reads committed records only and reports the spec's verdicts."""
import json
from pathlib import Path

import pytest

from postprocess import colab_summary

REPO = Path(__file__).resolve().parent.parent
VAL, POOL = REPO / "runs" / "val", REPO / "runs" / "pool"


@pytest.mark.skipif(not (VAL / "cylinder-854aee41c4" / "result.json").exists(), reason="no Colab records")
def test_summary_from_the_committed_records():
    text = colab_summary.build(VAL, POOL, "2026-11-01")
    assert "| fine | 12544 |" in text and "Grid change medium -> fine: -3.50% (tolerance 5%): PASS." in text
    assert "| recovery_total | 0.31627 | 0.31634 | 0.31663 | +0.09% | 2% | PASS |" in text
    assert "| q_peak_W_m2 | 30178 | 29725 | 29226 | -1.68% | 5% | PASS |" in text
    assert "| inlet2r-619144f64c | 8/8 medium | 0.9287 | 0.9316 | -0.31% | 2% | PASS |" in text
    assert "failed: nonzero_exit" in text and "12.0/14.0" in text
    assert "FAIL" not in text.replace("failed:", "")


def test_summary_handles_empty_and_failed_records(tmp_path):
    val, pool = tmp_path / "val", tmp_path / "pool"
    (val / "inlet2r-0000000000").mkdir(parents=True)
    pool.mkdir()
    (val / "inlet2r-0000000000" / "params.json").write_text(json.dumps(
        {"family": "inlet2r", "theta1_deg": 12.0, "theta2_deg": 14.0, "mesh_level": "medium"}))
    (val / "inlet2r-0000000000" / "error.json").write_text(json.dumps({"reason": "nan", "detail": {}}))
    text = colab_summary.build(val, pool, "2026-11-01")
    assert "No cylinder record." in text and "Fewer than two laminar inlet levels recorded." in text
    assert "No Euler inlet record." in text and "0 pool results recorded, 0 pool failures recorded." in text
    assert "| inlet2r-0000000000 | inlet2r | 12.0/14.0 | medium | - | - | failed: nan | - | - |" in text

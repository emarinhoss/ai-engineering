"""Owner ruling B-2b: other cells of the robust re-size are sized again at their recorded L_sized and must equal
the recorded row; the side-by-side note reads the records."""
import json

import pytest

from measurement import bands_cells as bc
from measurement import robust_sizing as rs


@pytest.mark.parametrize("ws,a", [(13.0, 8.0), (13.0, 9.0), (14.0, 8.0)])
def test_a_cell_sized_again_at_its_recorded_loiter_is_the_recorded_row(ws, a):
    row = bc.source_row(ws, a)
    try:
        rs.use_engine_as_is(True)
        rec = bc.size_cell(row)
    finally:
        rs.use_engine_as_is(False)
    assert rec["W0_lb"] == pytest.approx(row["W0_lb"], rel=1e-12) and rec["fuel_lb"] == pytest.approx(row["fuel_lb"], rel=1e-12)
    assert rec["W_S"] == ws and rec["A"] == a and rec["V_c_rule"] == "per_design"


def test_the_winner_sized_again_is_its_own_design_record():
    d = json.loads((bc.WINNER / "design_pusher.json").read_text())
    try:
        rs.use_engine_as_is(True)
        rec = bc.size_cell(bc.source_row(d["W_S"], d["A"]))
    finally:
        rs.use_engine_as_is(False)
    assert rec["components_lb"] == d["components_lb"] and rec["We_lb"] == d["We_lb"]


def test_a_cell_that_is_not_a_design_is_refused_and_a_wrong_row_is_caught():
    with pytest.raises(ValueError, match="not a compliant design"):
        bc.source_row(16.0, 7.0)
    with pytest.raises(ValueError, match="expected 1"):
        bc.source_row(12.0, 8.0)
    row = dict(bc.source_row(13.0, 8.0), W0_lb=3000.0)
    try:
        rs.use_engine_as_is(True)
        with pytest.raises(ValueError, match="not the recorded row"):
            bc.size_cell(row)
    finally:
        rs.use_engine_as_is(False)


def test_summary_and_note_of_the_winner_read_its_record():
    s = bc.summarise(bc.WINNER)
    assert (s["W_S"], s["A"], s["vc_kt"]) == (14.0, 8.0, 110.0)
    assert s["h_hat"]["R5_guarantee"] == 1.05029296875 and s["target_holds"] and s["R7_binding"] == "take-off"
    assert s["mode_cliff"] == 1.0615234375 and s["at_target"]["cliff_ratio"] == pytest.approx(0.9898270161143188)
    assert s["at_h1"]["R5_hours"] == pytest.approx(3.826726087518966)
    text = bc.report_text({"source": "x", "h_T": 1.05, "cells": {"winner": s, "other": dict(s, target_holds=False)}}, "out")
    assert "| W0 (lb) | 3460 | 3460 |" in text and "| h_T 1.05 holds | yes | **NO** |" in text
    assert "**1.0503**" in text and "take-off (1.2748 / 1.5950)" in text
    assert bc.parse_cells("13,8;13,9") == [(13.0, 8.0), (13.0, 9.0)]

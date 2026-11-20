"""Lattice downwash helper and the Stage 3 aero runner on the frozen pusher record."""
import json
import math
from pathlib import Path

import pytest

from conceptual import uav
from drone import geometry, vlm
from measurement import stage3_aero

DESIGN = Path(__file__).resolve().parents[2] / "runs/task12/stage1/2026-11-20e/design_pusher.json"


def test_far_wake_downwash_of_elliptic_wing():
    """Far behind an elliptic wing, in its plane, d(eps)/d(alpha) = 2 CL_alpha/(pi A) (lifting-line
    far wake; classical, not from the library). The lattice reaches it to 3 %."""
    w = geometry.elliptic(10.0, 8.0)
    cla = vlm.derivatives(w, "medium")["CL_alpha"]
    assert vlm.downwash_gradient(w, [[500.0, 0.0, 0.0]], "medium") == pytest.approx(
        2.0 * cla / (math.pi * 8.0), rel=0.03)


def test_no_downwash_without_lift():
    w = geometry.tapered(10.0, 8.0, 0.5)
    v = vlm.induced_velocity(w, 0.0, [[20.0, 1.0, 0.5]])
    assert abs(v).max() < 1e-12


def test_runner_reproduces_stage1_static_margin():
    d = json.loads(DESIGN.read_text())
    L, _ = uav.load_ledger()
    res = stage3_aero.measure(d, L)
    for r in res["rows"]:
        if "stage1_reproduced" in r:
            assert r["stage1_reproduced"] == pytest.approx(r["raymer"], abs=1e-9)

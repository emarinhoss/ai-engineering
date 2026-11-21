"""Vortex-lattice downwash helper (conceptual.uav.lattice_downwash): far-wake limit, agreement
between Stage 1 and Stage 3, and the tail-height gate."""
import json
import math
from pathlib import Path

import pytest

from conceptual import uav
from drone import geometry, vlm
from measurement import stage3_aero

DESIGN = Path(__file__).resolve().parents[2] / "runs/task12/stage1/2026-11-21e/design_pusher.json"


def test_far_wake_limit_for_high_aspect_ratio_wing():
    """Far behind a high-aspect-ratio wing, d(eps)/d(alpha) -> 2 CL_alpha/(pi A). That far-wake
    relation is classical lifting-line theory; it is not from the library. It is exact only for
    elliptic loading (uniform far-wake downwash); taper 0.6 is close enough near the centreline, a
    rectangular wing is not (centre value 33 % low), so the taper is not 1.0."""
    span, A, taper = 40.0, 12.0, 0.6
    cla = vlm.derivatives(geometry.tapered(span, A, taper), "medium")["CL_alpha"]
    v = uav.lattice_downwash(span, A, taper, 400.0, 2.0, 1.0)
    assert v == pytest.approx(2.0 * cla / (math.pi * A), rel=0.05)


def test_stage1_and_stage3_agree_on_frozen_record():
    d = json.loads(DESIGN.read_text())
    L, _ = uav.load_ledger()
    w = d["wing"]
    z = 0.4 * d["fuselage"]["diameter"]
    v = uav.lattice_downwash(w["span"], w["aspect_ratio"], w["taper"], d["tail_arm_ft"],
                             d["horizontal_tail"]["span"], z)
    assert v == pytest.approx(1.0 - d["layout"]["dah_da"], abs=1e-6)
    res = stage3_aero.measure(d, L)
    row = next(r for r in res["rows"] if r["quantity"].startswith("downwash"))
    assert row["measured"] == pytest.approx(v, abs=0.005)


def test_zero_tail_height_is_refused():
    with pytest.raises(ValueError):
        uav.lattice_downwash(40.0, 12.0, 0.45, 13.0, 10.0, 0.0)

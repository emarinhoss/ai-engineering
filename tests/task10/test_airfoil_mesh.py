"""T10.7a and 7b: the airfoil2d C-mesh passes the mesh-quality gate and its config renders cleanly."""
import json
import math

import pytest

from cases.check_keys import unknown_keys
from cases.config import render
from geometry import airfoil2d
from worker.make_case import quality_failures, requested_first_cell

BASE = {"family": "airfoil2d", "camber_pct": 4.0, "thickness_pct": 12.0, "reynolds": 2e5,
        "alpha_deg": 6.0, "transition": "BCM", "mesh_level": "medium", "tag": "test", "max_iter": 3000}


def first_cell_from_yplus(re, yplus=0.5, chord=1.0):
    cf = 0.074 * re ** -0.2
    u_tau_over_v = math.sqrt(cf / 2.0)
    return yplus * chord / (re * u_tau_over_v)       # y+ nu / u_tau with nu = V c / Re


def test_medium_mesh_passes_the_quality_gate():
    geometry, mesh = airfoil2d.build(BASE)
    q = mesh.quality()
    assert quality_failures(q, requested_first_cell(BASE)) == []
    assert q["max_growth"] <= 1.2 + 1e-9
    assert 1.0e4 < q.get("cells", geometry["cells"]) < 2.0e5


def test_markers_are_airfoil_and_farfield_only():
    _, mesh = airfoil2d.build(BASE)
    assert set(mesh.markers) == {"airfoil", "farfield"}
    assert "airfoil" in mesh.walls


def test_first_cell_follows_the_yplus_rule_and_the_level_factor():
    want = requested_first_cell(BASE)["airfoil"]
    assert want == pytest.approx(first_cell_from_yplus(2e5), rel=1e-6)
    fine = requested_first_cell({**BASE, "mesh_level": "fine"})["airfoil"]
    assert fine == pytest.approx(want / 1.4, rel=1e-6)
    lo_re = requested_first_cell({**BASE, "reynolds": 1e5})["airfoil"]
    assert lo_re > want


def test_farfield_is_thirty_chords_and_trailing_edge_is_closed():
    geometry, mesh = airfoil2d.build(BASE)
    assert geometry["farfield_chords"] == pytest.approx(30.0)
    assert geometry["chord_m"] == pytest.approx(1.0)
    x = mesh.coords[:, 0]
    assert x.max() >= 29.0 and x.min() <= -29.0
    assert geometry["trailing_edge_closed"] is True


def test_config_renders_with_only_pinned_keys_and_the_reynolds_number():
    geometry, mesh = airfoil2d.build(BASE)
    markers = json.loads(mesh.markers_json()) if hasattr(mesh, "markers_json") else {k: [] for k in mesh.markers}
    text = render(BASE, geometry, markers)
    assert "SOLVER= INC_RANS" in text and "KIND_TURB_MODEL= SA" in text
    assert "BCM" in text
    assert "REF_AREA= 1.0" in text.replace(" ", "") .replace("=", "= ") or "REF_AREA= 1" in text
    with open("cases/templates/inc_rans_airfoil.cfg") as f:
        template = f.read()
    assert unknown_keys(text, template) == []
    lm = render({**BASE, "transition": "LM"}, geometry, markers)
    assert "SST" in lm and "LM" in lm


def test_airfoil_timeout_scales_with_the_iteration_budget_and_the_mesh():
    """The fine mesh at the full budget costs more than the 2400 s floor (runs/smoke2 measured
    0.285 s per iteration at 43 008 cells on 4 Colab ranks); the floor still holds for a cheap case."""
    from worker.make_case import TIMEOUT_MIN_S, timeout_s
    assert timeout_s({"family": "inlet3r"}, {"cells": 10**6}) == TIMEOUT_MIN_S
    assert timeout_s({**BASE, "max_iter": 1000}, {"cells": 21760}) == TIMEOUT_MIN_S
    medium = timeout_s({**BASE, "max_iter": 6000}, {"cells": 43008})
    fine = timeout_s({**BASE, "max_iter": 6000}, {"cells": 84152})
    assert 2500 < medium < 2700 and 4900 < fine < 5200
    assert fine == pytest.approx(medium * 84152 / 43008, rel=1e-3)

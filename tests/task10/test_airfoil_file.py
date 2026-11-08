"""T10.7e: a section given by a coordinate file (Selig format) through the same C-mesh as the NACA
four-digit section, for V6e (E387). The file is never typed from memory: tests build their own
files from drone.naca so the mesh can be checked against the analytic section."""
import hashlib

import numpy as np
import pytest

from drone import naca
from geometry import airfoil2d, airfoils
from mcp_server import queue
from mcp_server.schemas import CaseParams, validate
from worker.make_case import case_id, quality_failures, requested_first_cell

BASE = {"family": "airfoil2d", "camber_pct": 4.0, "thickness_pct": 12.0, "reynolds": 2e5,
        "alpha_deg": 6.0, "transition": "BCM", "mesh_level": "medium", "tag": "test", "max_iter": 3000}
FILE = {k: v for k, v in BASE.items() if k not in ("camber_pct", "thickness_pct")}
FILE["airfoil"] = "naca4412-test"


def selig_text(name, x, y):
    lines = [name, ""] + [f"  {a:.6f}  {b:.6f}" for a, b in zip(x, y)] + [""]
    return "\n".join(lines)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """A coordinate registry holding a 121-point-per-surface NACA 4412 under the test name."""
    monkeypatch.setattr(airfoils, "AIRFOIL_DIR", tmp_path)
    x, y = naca.coordinates(4.0, 12.0, n=121)
    (tmp_path / "naca4412-test.dat").write_text(selig_text("NACA 4412 (test)", x, y))
    return tmp_path


def wall_nodes(mesh):
    ids = sorted({i for pair in mesh.markers["airfoil"] for i in pair})
    return mesh.coords[ids]


def test_read_selig_skips_the_name_line_and_blank_lines_and_keeps_the_order(tmp_path):
    x0, y0 = naca.coordinates(2.0, 12.0, n=31)
    p = tmp_path / "s.dat"
    p.write_text(selig_text("NACA 2412", x0, y0))
    x, y = airfoils.read_selig(p)
    assert np.allclose(x, x0, atol=1e-6) and np.allclose(y, y0, atol=1e-6)
    assert x[0] == pytest.approx(1.0) and x[-1] == pytest.approx(1.0)
    assert int(np.argmin(x)) == 30                    # the leading edge is where the file put it


def test_load_names_the_missing_file(registry):
    with pytest.raises(FileNotFoundError, match="nosuch.dat"):
        airfoils.load("nosuch")


def test_file_section_meshes_like_the_analytic_one(registry):
    g_naca, m_naca = airfoil2d.build(BASE)
    g_file, m_file = airfoil2d.build(FILE)
    assert len(m_file.coords) == len(m_naca.coords) and len(m_file.cells) == len(m_naca.cells)
    gap = np.hypot(*(wall_nodes(m_file) - wall_nodes(m_naca)).T)
    assert gap.max() < 1e-3, gap.max()               # spline through 121 points vs the formula
    q = m_file.quality()
    assert quality_failures(q, requested_first_cell(FILE)) == []
    assert g_file["airfoil"] == "naca4412-test" and g_naca["airfoil"] == "naca4"
    assert g_file["camber_pct"] is None and g_file["thickness_pct"] is None
    digest = hashlib.sha256((registry / "naca4412-test.dat").read_bytes()).hexdigest()
    assert g_file["section_sha256"] == digest
    assert "section_sha256" not in g_naca


def test_first_cell_rule_does_not_depend_on_how_the_section_is_given(registry):
    assert requested_first_cell(FILE) == requested_first_cell(BASE)


def test_a_small_trailing_edge_gap_is_closed_and_recorded(registry):
    x, y = naca.coordinates(4.0, 12.0, n=121)
    y = y.copy()
    y[0], y[-1] = 0.002, -0.002                       # a 0.4 percent blunt trailing edge
    (registry / "blunt.dat").write_text(selig_text("blunt", x, y))
    g, m = airfoil2d.build({**FILE, "airfoil": "blunt"})
    assert g["trailing_edge_closed"] is True
    assert g["trailing_edge_gap"] == pytest.approx(0.004, abs=1e-9)
    w = wall_nodes(m)
    te = w[np.argmax(w[:, 0])]
    assert te[0] == pytest.approx(1.0) and abs(te[1]) < 1e-12
    y[0], y[-1] = 0.012, -0.012                       # 2.4 percent: not a sharp-edged section
    (registry / "open.dat").write_text(selig_text("open", x, y))
    with pytest.raises(ValueError, match="trailing"):
        airfoil2d.build({**FILE, "airfoil": "open"})


def test_a_file_that_is_not_normalised_to_the_unit_chord_is_refused(registry):
    x, y = naca.coordinates(4.0, 12.0, n=121)
    (registry / "big.dat").write_text(selig_text("big", 2.0 * x, 2.0 * y))
    with pytest.raises(ValueError, match="chord"):
        airfoil2d.build({**FILE, "airfoil": "big"})


def errors_of(params):
    _, errors, _ = validate(params)
    return errors


def test_schema_takes_a_name_or_the_two_naca_numbers_but_not_both():
    assert errors_of(FILE) == [] and errors_of(BASE) == []
    both = errors_of({**BASE, "airfoil": "e387"})
    assert both and any("airfoil" in e for e in both)
    assert errors_of({k: v for k, v in BASE.items() if k not in ("camber_pct", "thickness_pct")})
    drone = errors_of({"family": "drone", "span_m": 2.0, "aspect_ratio": 10.0, "taper_ratio": 0.6,
                       "battery_fraction": 0.3, "camber_pct": 4.0, "thickness_pct": 12.0,
                       "tag": "test", "airfoil": "e387"})
    assert drone and any("airfoil" in e for e in drone)
    assert errors_of({**FILE, "airfoil": "../e387"})
    assert CaseParams(**FILE).airfoil == "naca4412-test"


def test_case_id_distinguishes_the_section_and_a_missing_file_fails_the_geometry_stage(registry):
    assert case_id(FILE) != case_id(BASE)
    assert case_id(FILE).startswith("airfoil2d-")
    res = queue.validate_only({**FILE, "airfoil": "nosuch"})
    assert res["ok"] is False and res["stage"] == "geometry"
    assert any("nosuch" in e for e in res["errors"])
    ok = queue.validate_only(FILE)
    assert ok["ok"] is True and ok["geometry"]["airfoil"] == "naca4412-test"

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


# ---- the E387 file itself (data/validation/airfoils/e387.dat, supplied by Éder 2026-11-08) ----

E387_SHA256 = "24b45a2df162f282b523dc4dbf3d767890a77ca42b92fad82a6a8e41f469a784"
E387 = {"family": "airfoil2d", "airfoil": "e387", "reynolds": 2e5, "alpha_deg": 4.0,
        "transition": "BCM", "mesh_level": "medium", "tag": "test", "max_iter": 6000}


def turning_deg(x, y):
    """Angle between consecutive segments of the loop, in degrees, one per interior point."""
    t = np.diff(np.column_stack((x, y)), axis=0)
    ang = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    return np.degrees(np.abs(np.diff(ang)))


def test_e387_file_is_the_one_supplied_and_has_a_closed_trailing_edge():
    x, y, digest = airfoils.load("e387")
    assert digest == E387_SHA256
    assert len(x) == 61 and x[0] == x[-1] == 1.0 and y[0] == y[-1] == 0.0
    assert airfoils.trailing_edge_gap(x, y) == 0.0


def test_e387_dense_loop_has_no_kink_at_the_leading_edge():
    """The file has no point on the chord line at the nose; the dense loop must still turn smoothly
    there. Two half-splines meeting at an inserted point gave a 29 degree kink (found 2026-11-08).
    The bound is set from the NACA loop at the same resolution and plain cosine spacing, which
    turns 1.3 degrees per segment at its nose and meshes cleanly; the E387's nose is tighter
    (radius 0.0047) and sits off the chord line, so it turns about 2.7."""
    x, y, _ = airfoils.load("e387")
    xd, yd = airfoils.dense_loop(x, y, 801)
    assert len(xd) == 1601 and xd[800] < 0.002 and abs(yd[800]) < 1e-9
    assert turning_deg(xd, yd).max() < 3.0
    xn, yn = naca.coordinates(4.0, 12.0, n=801)
    assert turning_deg(xn, yn).max() < 3.0


@pytest.mark.parametrize("level", ["coarse", "medium"])
def test_e387_mesh_passes_the_quality_gate(level):
    g, m = airfoil2d.build({**E387, "mesh_level": level})
    q = m.quality()
    assert quality_failures(q, requested_first_cell({**E387, "mesh_level": level})) == [], q
    assert g["airfoil"] == "e387" and g["section_sha256"] == E387_SHA256


@pytest.mark.xfail(strict=True, reason="recorded negative 2026-11-08: the E387's lower surface is "
                   "concave over its last few percent (tangent 2.2 deg at x = 0.97 to 3.7 deg at the "
                   "trailing edge), so neighbouring wall-normal columns converge about 0.9 chord out "
                   "and at the fine spacing 8 cells invert in the lower wall block near x = 0.95, "
                   "aspect ratio 8763. A mesher change (smoothing the wall normals) is deferred until "
                   "the nominal batch is done, because it moves every staged mesh fingerprint.")
def test_e387_fine_mesh_passes_the_quality_gate():
    _, m = airfoil2d.build({**E387, "mesh_level": "fine"})
    assert quality_failures(m.quality(), requested_first_cell({**E387, "mesh_level": "fine"})) == []

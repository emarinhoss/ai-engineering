import json

import numpy as np

from geometry.structured import read_su2_counts
from geometry.wedge import build


def test_medium_wedge_passes_quality_gate():
    geo, mesh = build({"theta1_deg": 10.0})
    q = mesh.quality()
    assert q["n_inverted"] == 0
    assert q["min_angle_deg"] >= 40
    assert q["max_aspect_ratio"] <= 5000
    assert q["max_growth"] <= 1.25
    assert geo["level"] == "medium" and geo["theta1_deg"] == 10.0
    assert geo["nodes"] == len(mesh.coords) and geo["cells"] == len(mesh.cells)


def test_first_cell_height_on_body():
    _, mesh = build({"theta1_deg": 10.0})
    assert abs(mesh.quality()["first_cell_height"]["body"] - 20e-6) <= 0.10 * 20e-6


def test_body_marker_is_the_wedge_surface():
    _, mesh = build({"theta1_deg": 10.0})
    ids = sorted({k for line in mesh.markers["body"] for k in line})
    xy = mesh.coords[ids]
    assert np.allclose(xy[:, 1], xy[:, 0] * np.tan(np.radians(10.0)), atol=1e-12)
    assert abs(xy[:, 0].min()) < 1e-15 and abs(xy[:, 0].max() - 0.15) < 1e-12
    sym = mesh.coords[sorted({k for line in mesh.markers["symmetry"] for k in line})]
    assert np.allclose(sym[:, 1], 0) and abs(sym[:, 0].min() + 0.03) < 1e-15


def test_write_files_and_determinism(tmp_path):
    paths = []
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        _, mesh = build({"theta1_deg": 10.0, "mesh_level": "medium"})
        mesh.write_su2(d / "mesh.su2")
        mesh.write_markers(d / "mesh_markers.json")
        paths.append(d)
    assert (paths[0] / "mesh.su2").read_bytes() == (paths[1] / "mesh.su2").read_bytes()
    c = read_su2_counts(paths[0] / "mesh.su2")
    assert set(c["markers"]) == {"body", "symmetry", "inlet", "top", "outlet"}
    d = json.loads((paths[0] / "mesh_markers.json").read_text())
    assert d["level"] == "medium" and d["nodes"] == c["nodes"] and d["cells"] == c["cells"]
    assert abs(d["first_cell_m"]["body"] - 20e-6) < 1e-9
    assert len(d["body"]) == c["markers"]["body"] + 1


def test_cell_counts_scale_about_1p96_per_level():
    n = {lvl: build({"theta1_deg": 10.0, "mesh_level": lvl})[0]["cells"]
         for lvl in ("coarse", "medium", "fine")}
    assert 1.6 < n["medium"] / n["coarse"] < 2.4
    assert 1.6 < n["fine"] / n["medium"] < 2.4


def test_other_angles_and_levels_have_valid_meshes():
    for theta in (2.0, 20.0):
        for level in ("coarse", "medium", "fine"):
            _, mesh = build({"theta1_deg": theta, "mesh_level": level})
            q = mesh.quality()
            assert q["n_inverted"] == 0 and q["min_angle_deg"] >= 40 and q["max_growth"] <= 1.25

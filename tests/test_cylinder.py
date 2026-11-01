from collections import Counter

import numpy as np
import pytest

from geometry.cylinder import build
from geometry.structured import read_su2_counts

R = 0.010
COUNTS = {"coarse": (57, 3136), "medium": (81, 6400), "fine": (113, 12544)}
FIRST = {"coarse": 8e-6, "medium": 4e-6, "fine": 2e-6}


@pytest.mark.parametrize("level", COUNTS)
def test_counts_and_first_cell_per_level(level):
    n, cells = COUNTS[level]
    geo, mesh = build({"mesh_level": level})
    assert geo["nodes"] == n * n == len(mesh.coords)
    assert geo["cells"] == cells == len(mesh.cells)
    q = mesh.quality()
    assert abs(q["first_cell_height"]["wall"] - FIRST[level]) <= 0.10 * FIRST[level]
    assert q["n_inverted"] == 0
    assert q["min_angle_deg"] >= 40
    assert q["max_growth"] <= 1.25
    assert q["max_aspect_ratio"] <= 5000


def test_geometry_dict_and_outer_boundary_beyond_shock():
    geo, mesh = build({"radius_m": R, "mach": 4.0})
    assert geo["level"] == "medium" and geo["phi_max_deg"] == 100.0
    assert geo["delta_over_R"] == pytest.approx(0.517, abs=0.001)
    # outer boundary on the stagnation line is at r = 2 R, beyond 1.5 stand-off distances
    xs = mesh.coords[sorted({k for line in mesh.markers["symmetry"] for k in line})]
    assert xs[:, 0].min() == pytest.approx(-2.0 * R, abs=1e-12)
    assert 2.0 * R - R > 1.5 * geo["delta_over_R"] * R


def test_marker_positions():
    _, mesh = build({})
    ids = lambda name: sorted({k for line in mesh.markers[name] for k in line})
    assert set(mesh.markers) == {"wall", "symmetry", "farfield", "outlet"}
    assert mesh.walls == ["wall"]
    wall = mesh.coords[ids("wall")]
    assert np.allclose(np.hypot(wall[:, 0], wall[:, 1]), R, atol=1e-15)
    assert np.isclose(wall[:, 0].min(), -R) and np.all(wall[:, 1] >= 0)
    sym = mesh.coords[ids("symmetry")]
    assert np.allclose(sym[:, 1], 0) and np.isclose(sym[:, 0].max(), -R)
    far = mesh.coords[ids("farfield")]
    r = np.hypot(far[:, 0], far[:, 1])
    sin2 = (far[:, 1] / r) ** 2
    assert np.allclose(r, R * (2.0 + 1.5 * sin2), rtol=1e-12)
    out = mesh.coords[ids("outlet")]
    assert np.allclose(np.degrees(np.arctan2(out[:, 1], -out[:, 0])), 100.0, atol=1e-9)


def test_boundary_edges_are_exactly_the_marker_lines():
    _, mesh = build({})
    count = Counter()
    for c in mesh.cells:
        for k in range(4):
            count[frozenset((int(c[k]), int(c[(k + 1) % 4])))] += 1
    assert set(count.values()) <= {1, 2}
    boundary = {e for e, n in count.items() if n == 1}
    marker_lines = Counter(frozenset(map(int, line)) for lines in mesh.markers.values() for line in lines)
    assert set(marker_lines) == boundary
    assert all(n == 1 for n in marker_lines.values())     # no edge in two markers or twice


def test_write_files_and_repeat_identical(tmp_path):
    paths = []
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        _, mesh = build({"mesh_level": "medium"})
        mesh.write_su2(d / "mesh.su2")
        mesh.write_markers(d / "mesh_markers.json")
        paths.append(d)
    for f in ("mesh.su2", "mesh_markers.json"):
        assert (paths[0] / f).read_bytes() == (paths[1] / f).read_bytes()
    c = read_su2_counts(paths[0] / "mesh.su2")
    assert c["cells"] == 6400 and c["nodes"] == 6561
    assert c["markers"] == {"wall": 80, "symmetry": 80, "farfield": 80, "outlet": 80}


def test_bad_level_rejected():
    with pytest.raises(ValueError):
        build({"mesh_level": "huge"})

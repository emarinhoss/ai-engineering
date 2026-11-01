import json

import numpy as np
import pytest

from geometry.structured import (
    Block,
    Mesh,
    read_su2_counts,
    stretch_capped,
    stretch_one_sided,
    stretch_two_sided,
)


def rect(x0, x1, y0, y1, n1, n2):
    """Axis-aligned rectangular block with uniform spacing."""
    x, y = np.linspace(x0, x1, n1), np.linspace(y0, y1, n2)
    return Block(np.column_stack((x, np.full(n1, y0))), np.column_stack((np.full(n2, x1), y)),
                 np.column_stack((x, np.full(n1, y1))), np.column_stack((np.full(n2, x0), y)))


# ---- stretching -------------------------------------------------------------
@pytest.mark.parametrize("fn,args", [
    (stretch_one_sided, (0.06, 61, 20e-6)),
    (stretch_one_sided, (1.0, 11, 0.1)),                 # uniform: ratio -> 1
    (stretch_two_sided, (1.0, 41, 0.005, 0.01)),
    (stretch_two_sided, (1.0, 40, 0.005, 0.005)),        # even N
    (stretch_capped, (0.15, 169, 1e-4, 1e-3)),
])
def test_stretch_basics(fn, args):
    L, N, d0 = args[:3]
    x, _ = fn(*args)
    assert len(x) == N
    assert x[0] == 0.0 and abs(x[-1] - L) < 1e-12
    assert abs(x[1] - x[0] - d0) < 1e-9
    assert np.all(np.diff(x) > 0)


def test_one_sided_ratio_and_uniform():
    x, r = stretch_one_sided(0.06, 61, 20e-6)
    assert 1.09 < r < 1.11
    assert np.allclose(np.diff(x)[1:] / np.diff(x)[:-1], r)
    _, r1 = stretch_one_sided(1.0, 11, 0.1)
    assert r1 == 1.0


def test_two_sided_both_ends():
    x, _ = stretch_two_sided(1.0, 41, 0.004, 0.01)
    assert abs(x[1] - x[0] - 0.004) < 1e-9
    assert abs(x[-1] - x[-2] - 0.01) < 1e-9


def test_capped_never_exceeds_dmax():
    x, r = stretch_capped(0.15, 169, 1e-4, 1e-3)
    assert np.diff(x).max() <= 1e-3 * (1 + 1e-12)
    assert r > 1.0


def test_stretch_errors():
    with pytest.raises(ValueError):
        stretch_one_sided(1.0, 11, 0.2)                  # d0 (N-1) > L
    with pytest.raises(ValueError, match="need N >= 152"):
        stretch_capped(0.15, 100, 1e-4, 1e-3)            # cannot reach L with 100 points


# ---- blocks and meshes ------------------------------------------------------
def test_single_block_counts_orientation_angles():
    m = Mesh.from_blocks([rect(0, 2, 0, 1, 5, 4)], [])
    assert len(m.coords) == 20 and len(m.cells) == 4 * 3
    P = m.coords[m.cells]
    area = 0.5 * np.sum(P[..., 0] * np.roll(P[..., 1], -1, 1) - np.roll(P[..., 0], -1, 1) * P[..., 1], axis=1)
    assert np.all(area > 0)
    q = m.quality()
    assert abs(q["min_angle_deg"] - 90) < 1e-6
    assert q["n_inverted"] == 0


def test_block_corner_mismatch_rejected():
    b = rect(0, 1, 0, 1, 3, 3)
    with pytest.raises(AssertionError):
        Block(b.bottom, b.right + [0.0, 0.1], b.top, b.left)


def test_coons_curved_top_has_no_inverted_cells():
    x = np.linspace(0, 1, 9)
    ytop = 1 + 0.2 * np.sin(np.pi * x)
    top = np.column_stack((x, ytop))
    y = np.linspace(0, 1, 5)
    blk = Block(np.column_stack((x, 0 * x)), np.column_stack((1 + 0 * y, y)), top,
                np.column_stack((0 * y, y)))
    assert np.allclose(blk.nodes[:, -1], top)
    assert Mesh.from_blocks([blk], []).n_inverted == 0


def test_two_blocks_share_edge_without_duplicates():
    a, b = rect(0, 1, 0, 1, 5, 4), rect(1, 3, 0, 1, 7, 4)       # share x = 1, N_shared = 4
    m = Mesh.from_blocks([a, b], [(0, "right", 1, "left", False)])
    assert len(m.coords) == 5 * 4 + 7 * 4 - 4
    assert len(m.cells) == 4 * 3 + 6 * 3
    assert len({tuple(p) for p in m.coords}) == len(m.coords)
    assert m.n_inverted == 0


def test_shared_edge_reversed():
    """Block B is block-A-sized, rotated 90 degrees clockwise so that its bottom edge runs
    down x = 1, opposite to A's right edge."""
    a = rect(0, 1, 0, 1, 4, 5)
    def rot(p):                                   # (x, y) -> (y, -x) + (1, 1)
        return np.column_stack((p[:, 1] + 1, -p[:, 0] + 1))
    r = rect(0, 1, 0, 1, 5, 3)                    # unrotated B: bottom has 5 pts = A's right count
    b = Block(rot(r.bottom), rot(r.right), rot(r.top), rot(r.left))
    assert np.allclose(b.bottom[0], [1, 1]) and np.allclose(b.bottom[-1], [1, 0])
    m = Mesh.from_blocks([a, b], [(0, "right", 1, "bottom", True)])
    assert len(m.coords) == 4 * 5 + 5 * 3 - 5
    assert m.n_inverted == 0
    assert len({tuple(p) for p in m.coords}) == len(m.coords)


def test_shared_edge_count_mismatch_rejected():
    a, b = rect(0, 1, 0, 1, 5, 4), rect(1, 2, 0, 1, 5, 6)
    with pytest.raises(ValueError):
        Mesh.from_blocks([a, b], [(0, "right", 1, "left", False)])


def test_inverted_cell_reported():
    # top edge below the bottom edge: every cell has negative signed area
    x, y = np.linspace(0, 1, 4), np.linspace(0, -1, 3)
    blk = Block(np.column_stack((x, 0 * x)), np.column_stack((1 + 0 * y, y)),
                np.column_stack((x, -1 + 0 * x)), np.column_stack((0 * y, y)))
    m = Mesh.from_blocks([blk], [])
    assert m.quality()["n_inverted"] == 3 * 2
    # they are flipped to counter-clockwise afterwards
    P = m.coords[m.cells]
    area = 0.5 * np.sum(P[..., 0] * np.roll(P[..., 1], -1, 1) - np.roll(P[..., 0], -1, 1) * P[..., 1], axis=1)
    assert np.all(area > 0)


def test_wall_quality_first_cell_and_growth(tmp_path):
    x = np.linspace(0, 1, 6)
    y, r = stretch_one_sided(1.0, 21, 0.01)
    blk = Block(np.column_stack((x, 0 * x)), np.column_stack((1 + 0 * y, y)),
                np.column_stack((x, 1 + 0 * x)), np.column_stack((0 * y, y)))
    m = Mesh.from_blocks([blk], [], level="test")
    m.add_marker("wall", [(0, "bottom")], wall=True)
    m.add_marker("top", [(0, "top")])
    q = m.quality()
    assert abs(q["first_cell_height"]["wall"] - 0.01) < 1e-9
    assert abs(q["max_growth"] - r) < 1e-9
    assert set(q["first_cell_height"]) == {"wall"}


def test_write_su2_roundtrip(tmp_path):
    a, b = rect(0, 1, 0, 1, 5, 4), rect(1, 3, 0, 1, 7, 4)
    m = Mesh.from_blocks([a, b], [(0, "right", 1, "left", False)], level="test")
    m.add_marker("bottom", [(0, "bottom"), (1, "bottom")])
    m.add_marker("left", [(0, "left")])
    f = tmp_path / "m.su2"
    m.write_su2(f)
    c = read_su2_counts(f)
    assert c == {"nodes": len(m.coords), "cells": len(m.cells),
                 "markers": {"bottom": 4 + 6, "left": 3}}
    lines = f.read_text().splitlines()
    assert lines[0] == "NDIME= 2" and lines[2].startswith("9 ")
    # markers json
    j = tmp_path / "m.json"
    m.write_markers(j)
    d = json.loads(j.read_text())
    assert d["nodes"] == len(m.coords) and d["cells"] == len(m.cells) and d["level"] == "test"
    assert len(d["bottom"]) == 5 + 7 - 1 and len(d["left"]) == 4

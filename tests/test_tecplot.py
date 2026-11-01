import json
from pathlib import Path

import numpy as np
import pytest

from postprocess.tecplot import read_su2_points, read_tecplot_ascii, surface_nodes_for_marker
from tests.fake_su2 import VARIABLES, write_tecplot

REAL_RUN = Path("/tmp/claude-0/-home-user-ai-engineering/4e62754b-8c8b-5b87-a61c-cb95358da47b/"
                "scratchpad/fmt")


def test_round_trip_two_zones(tmp_path):
    write_tecplot(tmp_path / "a.dat", [0, 1, 2], [0, 0, 0], "FELINESEG", [(1, 2), (2, 3)])
    text = (tmp_path / "a.dat").read_text()
    zone2 = text.split("\n", 2)[2]                       # second zone block without the header lines
    (tmp_path / "b.dat").write_text(text + zone2)
    d = read_tecplot_ascii(tmp_path / "b.dat")
    assert d["variables"] == VARIABLES
    assert d["zone"].tolist() == [0, 0, 0, 1, 1, 1] and d["zonetype"] == ["FELINESEG"] * 2
    assert len(d["data"]["x"]) == 6 and (d["data"]["Heat_Flux"] == 1.0e5).all()
    assert d["elements"][1][0] == 3 and d["elements"][1][1].tolist() == [[0, 1], [1, 2]]


def test_truncated_file_raises(tmp_path):
    write_tecplot(tmp_path / "a.dat", [0, 1], [0, 0], "FELINESEG", [(1, 2)])
    lines = (tmp_path / "a.dat").read_text().splitlines()
    (tmp_path / "a.dat").write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError):
        read_tecplot_ascii(tmp_path / "a.dat")


def test_marker_rows_are_ordered_and_unmatched_node_raises(tmp_path):
    # mesh with 5 nodes on y = 0; marker "wall" is nodes 1..3, surface file has them shuffled
    (tmp_path / "mesh.su2").write_text("NDIME= 2\nNPOIN= 5\n" + "".join(
        f"{0.01 * i:.16e} 0.0000000000000000e+00 {i}\n" for i in range(5)))
    (tmp_path / "mesh_markers.json").write_text(json.dumps({"wall": [1, 2, 3]}))
    assert np.allclose(read_su2_points(tmp_path / "mesh.su2")[:, 0], 0.01 * np.arange(5))
    x = [0.03, 0.01, 0.02]
    write_tecplot(tmp_path / "s.dat", x, [0, 0, 0], "FELINESEG", [(2, 3), (3, 1)])  # chain 1-2-3
    d = read_tecplot_ascii(tmp_path / "s.dat")
    rows = surface_nodes_for_marker(d, tmp_path / "mesh_markers.json", "wall")
    assert d["data"]["x"][rows].tolist() == pytest.approx([0.01, 0.02, 0.03])
    write_tecplot(tmp_path / "s.dat", [0.01, 0.02], [0, 0], "FELINESEG", [(1, 2)])
    with pytest.raises(ValueError, match="no surface row"):
        surface_nodes_for_marker(read_tecplot_ascii(tmp_path / "s.dat"),
                                 tmp_path / "mesh_markers.json", "wall")


@pytest.mark.skipif(not (REAL_RUN / "surface_flow.dat").exists(), reason="real SU2 file not available")
def test_real_surface_file_body_rows():
    d = read_tecplot_ascii(REAL_RUN / "surface_flow.dat")
    rows = surface_nodes_for_marker(d, REAL_RUN / "mesh_markers.json", "body")
    n_body = len(json.loads((REAL_RUN / "mesh_markers.json").read_text())["body"])
    assert len(rows) == n_body == len(d["data"]["x"])
    assert (np.diff(d["data"]["x"][rows]) > 0).all()
    assert d["data"]["Heat_Flux"].sum() > 0

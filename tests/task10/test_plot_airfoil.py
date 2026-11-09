"""postprocess.plot_airfoil (surface reader, polar assembly) and plot_flowfield's airfoil command,
on small synthetic Tecplot files written here."""
import gzip
import json

import numpy as np
import pytest

from postprocess import plot_airfoil as pa
from postprocess import plot_flowfield as pf

SURFACE_VARS = ["x", "y", "Pressure_Coefficient", "Skin_Friction_Coefficient_x"]


def write_surface(path, n=20):
    """A closed loop like SU2's: trailing edge (1, 0), the LOWER side to the leading edge, then the
    upper side back. Camber makes the nodes next to the trailing edge both lie above y = 0."""
    x = np.linspace(0.0, 1.0, n)
    camber = 0.05 * np.sin(np.pi * x) + 0.02 * (1 - x)
    lower = camber - 0.06 * np.sqrt(x) * (1 - x)
    upper = camber + 0.06 * np.sqrt(x) * (1 - x)
    xs = np.concatenate([x[::-1], x[1:]])
    ys = np.concatenate([lower[::-1], upper[1:]])
    cp = -ys * 10.0                                    # upper surface (larger y) has the lower Cp
    n_all = len(xs)
    lines = ['TITLE = "t"', "VARIABLES = " + ",".join(f'"{v}"' for v in SURFACE_VARS),
             f"ZONE NODES= {n_all}, ELEMENTS= {n_all}, DATAPACKING=POINT, ZONETYPE=FELINESEG"]
    lines += [f"{a} {b} {c} {a * 0.001}" for a, b, c in zip(xs, ys, cp)]
    lines += [f"{i + 1} {(i + 1) % n_all + 1}" for i in range(n_all)]
    path.write_text("\n".join(lines) + "\n")
    return xs, ys


def test_read_surface_orders_leading_to_trailing_edge_and_picks_upper_by_y(tmp_path):
    xs, _ = write_surface(tmp_path / "surface_flow.dat")
    s = pa.read_surface(tmp_path / "surface_flow.dat")
    for which in ("upper", "lower"):
        x, _ = pa.side(s, which, "x")
        assert x[0] == pytest.approx(0.0) and x[-1] == pytest.approx(1.0)
        assert np.all(np.diff(x) >= 0)
    assert np.interp(0.5, *pa.side(s, "upper", "y")) > np.interp(0.5, *pa.side(s, "lower", "y"))
    # here the file lists the lower side first, so the "upper" indices are the second half
    assert s["upper"][0] == int(np.argmin(xs))


def test_read_surface_reads_gzip_and_all_variables(tmp_path):
    write_surface(tmp_path / "s.dat")
    gz = tmp_path / "s.dat.gz"
    gz.write_bytes(gzip.compress((tmp_path / "s.dat").read_bytes()))
    s = pa.read_surface(gz)
    assert set(SURFACE_VARS) <= set(s)
    _, cp_up = pa.side(s, "upper", "Pressure_Coefficient")
    _, cp_lo = pa.side(s, "lower", "Pressure_Coefficient")
    assert cp_up.mean() < cp_lo.mean()                 # suction side first in the sense of lower Cp


def test_reversed_flow_extent_finds_the_longest_negative_run(tmp_path):
    write_surface(tmp_path / "s.dat")
    s = pa.read_surface(tmp_path / "s.dat")
    assert pa.reversed_flow_extent(s) is None
    x = s["x"].copy()
    s["Skin_Friction_Coefficient_x"] = np.where((x > 0.4) & (x < 0.7), -1.0, 1.0)
    lo, hi = pa.reversed_flow_extent(s)
    assert 0.4 < lo < hi < 0.7


def test_low_fidelity_curves_follow_the_closed_form():
    alpha, cl, cd = pa.low_fidelity_curves(4.0, 12.0, 2.0e5)
    assert alpha.shape == cl.shape == cd.shape
    assert np.all(np.diff(cl) >= 0) and cl.max() == pytest.approx(cl[-1])     # capped at cl_max
    assert np.ptp(cd) == 0.0                                                   # constant cd


def test_polar_columns_cover_e387_and_every_complete_design():
    cols = pa.polar_columns()
    designs = pa.pool_designs()
    assert len(cols) == 1 + len(designs) and len(designs) >= 3
    su2, tunnel = cols[0][1], cols[0][5]
    assert tunnel["reynolds"] == 203800.0 and len(su2) == 5
    for (_, cases, _, _, _, tun), d in zip(cols[1:], designs):
        assert tun is None
        kept = {r["case_id"] for r, k in cases if k}
        assert kept == set(d["kept"])


def test_committed_surface_files_have_the_variables_the_figures_use():
    s = pa.read_surface(pa.ROOT / "runs/e387/airfoil2d-498b156761/surface_flow.dat.gz")
    for name in ("Pressure_Coefficient", "Skin_Friction_Coefficient_x", "Y_Plus"):
        assert name in s
    x, _ = pa.side(s, "upper", "x")
    assert x[0] < 1e-3 and x[-1] > 0.99


def test_main_writes_every_figure_and_a_caption_naming_sources(tmp_path):
    pa.main(tmp_path)
    for name, _ in pa.captions():
        assert (tmp_path / name).stat().st_size > 20_000, name
    text = (tmp_path / "captions.md").read_text()
    assert text.count("`runs/") >= 6 and "history.csv.gz" in text


# ---- the airfoil volume command -----------------------------------------------------------------
def write_volume(folder, nr=4, nt=24, with_params=True):
    """A polar quad mesh around a circle of radius 0.5 centered at (0.5, 0), flow past it as a
    uniform stream of speed 3 in x with a Cp field; written as a FEQUADRILATERAL Tecplot file."""
    radii = np.array([0.5, 0.8, 2.0, 6.0][:nr])
    th = np.linspace(0, 2 * np.pi, nt, endpoint=False)
    x = np.array([0.5 + r * np.cos(th) for r in radii]).ravel()
    y = np.array([r * np.sin(th) for r in radii]).ravel()
    cp = 1.0 - 4.0 * np.sin(np.arctan2(y, x - 0.5)) ** 2
    quads = []
    for i in range(nr - 1):
        for k in range(nt):
            a, b = i * nt + k, i * nt + (k + 1) % nt
            quads.append((a + 1, b + 1, b + nt + 1, a + nt + 1))
    names = ["x", "y", "Pressure", "Velocity_x", "Velocity_y", "Pressure_Coefficient"]
    lines = ['TITLE = "v"', "VARIABLES = " + ",".join(f'"{n}"' for n in names),
             (f"ZONE NODES= {len(x)}, ELEMENTS= {len(quads)}, DATAPACKING=POINT, "
              "ZONETYPE=FEQUADRILATERAL")]
    lines += [f"{a} {b} 0.0 3.0 0.0 {c}" for a, b, c in zip(x, y, cp)]
    lines += [" ".join(map(str, q)) for q in quads]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "flow.dat").write_text("\n".join(lines) + "\n")
    if with_params:
        (folder / "params.json").write_text(json.dumps(
            {"alpha_deg": 6.0, "reynolds": 200000.0, "mesh_level": "coarse"}))
    return nt


def test_airfoil_volume_wall_and_freestream_are_recovered(tmp_path):
    nt = write_volume(tmp_path / "case")
    from postprocess.tecplot import read_tecplot_ascii
    tri = pf.triangulate(read_tecplot_ascii(tmp_path / "case" / "flow.dat"))
    wall = pf.wall_edges(tri)
    assert len(wall) == nt and np.unique(wall).size == nt
    assert np.allclose(np.hypot(tri.x[wall[:, 0]] - 0.5, tri.y[wall[:, 0]]), 0.5)
    v = {"Velocity_x": np.full(len(tri.x), 3.0), "Velocity_y": np.zeros(len(tri.x))}
    assert pf.freestream_speed(tri, v) == pytest.approx(3.0)
    whole, zoom = pf.airfoil_windows(tri, wall)
    assert whole[0] < 0.0 < zoom[1] < 0.5 + 0.5 and whole[1] > 1.0


def test_airfoil_command_writes_a_picture_from_a_synthetic_volume_file(tmp_path):
    write_volume(tmp_path / "case")
    out = tmp_path / "airfoil.png"
    pf.main(["airfoil", str(tmp_path / "case"), "--out", str(out)])
    assert out.stat().st_size > 20_000


def test_airfoil_command_reads_a_gzipped_volume_file(tmp_path):
    write_volume(tmp_path / "case", with_params=False)
    flow = tmp_path / "case" / "flow.dat"
    (tmp_path / "case" / "flow.dat.gz").write_bytes(gzip.compress(flow.read_bytes()))
    flow.unlink()
    info = pf.plot_airfoil_volume(tmp_path / "case", tmp_path / "g.png")
    assert info["u_inf_file_units"] == pytest.approx(3.0) and info["wall_nodes"] == 24

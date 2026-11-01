import hashlib
import json

import pytest

from geometry.structured import Mesh, mesh_bbox, mesh_fingerprint
from worker.make_case import StageError, canonical_json, case_id, make

PARAMS = {"family": "wedge", "theta1_deg": 10.0, "solver": "NAVIER_STOKES",
          "mesh_level": "medium", "tag": "test"}
FILES = ["mesh.su2", "mesh_markers.json", "geometry.json", "mesh_quality.json", "case.cfg",
         "params.json", "job.json"]


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    out = tmp_path_factory.mktemp("case")
    return out, make(PARAMS, out)


def test_all_files_exist_and_job_fields(case):
    out, job = case
    for name in FILES:
        assert (out / name).is_file(), name
    on_disk = json.loads((out / "job.json").read_text())
    assert on_disk == job
    assert set(job) == {"case_id", "params", "created_at", "mesh_fingerprint", "mesh_bbox",
                        "config_sha256", "code_commit", "timeout_s", "max_cores"}
    assert job["timeout_s"] == 2400 and job["max_cores"] == 2
    assert job["created_at"].endswith("+00:00")


def test_case_id_form_and_key_order():
    shuffled = dict(reversed(list(PARAMS.items())))
    assert list(shuffled) != list(PARAMS)
    cid = case_id(PARAMS)
    assert cid == case_id(shuffled)
    expected = hashlib.sha256(canonical_json(PARAMS).encode()).hexdigest()[:10]
    assert cid == f"wedge-{expected}"
    assert canonical_json({"b": 1.5, "a": 2}) == '{"a":2,"b":1.5}'


def test_hashes_match_files(case):
    out, job = case
    assert job["case_id"] == case_id(PARAMS)
    assert job["mesh_fingerprint"] == mesh_fingerprint(out / "mesh.su2")
    assert job["mesh_bbox"] == mesh_bbox(out / "mesh.su2")
    assert job["config_sha256"] == hashlib.sha256((out / "case.cfg").read_bytes()).hexdigest()


def test_quality_record_and_config(case):
    out, _ = case
    quality = json.loads((out / "mesh_quality.json").read_text())
    assert quality["pass"] is True and quality["failures"] == []
    assert quality["n_inverted"] == 0
    assert "MARKER_ISOTHERMAL= ( body, 300.0 )" in (out / "case.cfg").read_text()


def test_same_params_give_identical_bytes(case, tmp_path):
    out, _ = case
    make(dict(reversed(list(PARAMS.items()))), tmp_path)
    for name in ("mesh.su2", "case.cfg", "mesh_markers.json", "geometry.json"):
        assert (tmp_path / name).read_bytes() == (out / name).read_bytes(), name


def test_euler_variant(tmp_path):
    make({**PARAMS, "solver": "EULER"}, tmp_path)
    text = (tmp_path / "case.cfg").read_text()
    assert "MARKER_EULER" in text and "MARKER_ISOTHERMAL" not in text


def test_unknown_family_not_implemented(tmp_path):
    with pytest.raises(NotImplementedError, match="spaceplane"):
        make({"family": "spaceplane", "tag": "test"}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_cylinder_family(tmp_path):
    job = make({"family": "cylinder", "mesh_level": "coarse", "tag": "test"}, tmp_path)
    assert job["case_id"].startswith("cylinder-")
    markers = json.loads((tmp_path / "mesh_markers.json").read_text())
    assert {"wall", "symmetry", "farfield", "outlet"} <= set(markers)
    assert json.loads((tmp_path / "mesh_quality.json").read_text())["requested_first_cell_m"] == {
        "wall": 8e-6}
    assert "MARKER_ISOTHERMAL= ( wall, 300.0 )" in (tmp_path / "case.cfg").read_text()


def test_inlet_family(tmp_path):
    params = {"family": "inlet2r", "theta1_deg": 8.0, "theta2_deg": 8.0, "mesh_level": "coarse",
              "tag": "test"}
    make(params, tmp_path)
    quality = json.loads((tmp_path / "mesh_quality.json").read_text())
    assert set(quality["requested_first_cell_m"]) == {"body", "cowl"}
    assert "MARKER_ISOTHERMAL= ( body, 300.0, cowl, 300.0 )" in (tmp_path / "case.cfg").read_text()


def test_geometry_failure_names_the_stage_and_writes_nothing(tmp_path):
    params = {"family": "wedge", "theta1_deg": 45.0, "tag": "test"}
    with pytest.raises(StageError) as err:
        make(params, tmp_path / "case")
    assert err.value.stage == "geometry" and "wedge tip" in err.value.errors[0]
    assert not (tmp_path / "case").exists()


def test_quality_failure_is_an_error_and_writes_nothing(monkeypatch, tmp_path):
    original = Mesh.quality
    monkeypatch.setattr(Mesh, "quality", lambda self: {**original(self), "n_inverted": 1})
    out = tmp_path / "case"
    with pytest.raises(ValueError, match="n_inverted"):
        make(PARAMS, out)
    assert not out.exists()


def test_fingerprint_ignores_last_digits_but_not_real_changes(case, tmp_path):
    out, job = case
    lines = (out / "mesh.su2").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("NPOIN=")) + 1

    def edited(name, change):
        new = list(lines)
        x, y, node = new[start + 5].split()
        new[start + 5] = change(float(x), float(y)) + f" {node}"
        (tmp_path / name).write_text("\n".join(new) + "\n")
        return mesh_fingerprint(tmp_path / name)

    noise = edited("noise.su2", lambda x, y: f"{x + 1e-13:.16e} {y - 1e-13:.16e}")   # ~platform noise
    moved = edited("moved.su2", lambda x, y: f"{x + 1e-6:.16e} {y:.16e}")            # 1000 nm: real
    assert noise == job["mesh_fingerprint"] and moved != job["mesh_fingerprint"]
    assert mesh_bbox(tmp_path / "noise.su2") == job["mesh_bbox"]
    renamed = "\n".join(line.replace("MARKER_TAG= top", "MARKER_TAG= lid") for line in lines)
    (tmp_path / "renamed.su2").write_text(renamed + "\n")
    assert mesh_fingerprint(tmp_path / "renamed.su2") != job["mesh_fingerprint"]

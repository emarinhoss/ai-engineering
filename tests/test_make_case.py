import hashlib
import json

import pytest

from geometry.structured import Mesh
from worker.make_case import canonical_json, case_id, make

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
    assert set(job) == {"case_id", "params", "created_at", "mesh_sha256", "config_sha256",
                        "code_commit", "timeout_s", "max_cores"}
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
    assert job["mesh_sha256"] == hashlib.sha256((out / "mesh.su2").read_bytes()).hexdigest()
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
    with pytest.raises(NotImplementedError, match="cylinder"):
        make({"family": "cylinder", "tag": "test"}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_quality_failure_is_an_error_and_writes_nothing(monkeypatch, tmp_path):
    original = Mesh.quality
    monkeypatch.setattr(Mesh, "quality", lambda self: {**original(self), "n_inverted": 1})
    out = tmp_path / "case"
    with pytest.raises(ValueError, match="n_inverted"):
        make(PARAMS, out)
    assert not out.exists()

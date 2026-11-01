import pytest

from geometry import cylinder, inlet, structured, wedge
from mcp_server import queue


@pytest.fixture(autouse=True)
def queue_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SU2_QUEUE_DIR", str(tmp_path))
    return tmp_path


def no_mesher(monkeypatch):
    def boom(params):
        raise AssertionError("the mesher must not be called")
    for module in (wedge, inlet, cylinder):
        monkeypatch.setattr(module, "build", boom)


def test_schema_error_stops_before_the_mesher(monkeypatch, queue_env):
    no_mesher(monkeypatch)
    for call in (queue.validate_only, queue.create):
        res = call({"family": "wedge", "theta1_deg": 25.0, "tag": "test"})
        assert res["ok"] is False and res["stage"] == "schema"
        assert any("theta1_deg" in e for e in res["errors"])
    assert not (queue_env / "jobs").exists()


def test_gate_error_stops_before_the_mesher(monkeypatch, queue_env):
    no_mesher(monkeypatch)
    # Mach 3, theta1 = 12, theta2 = 5 puts the lip too high (gate 2).
    params = {"family": "inlet2r", "theta1_deg": 12.0, "theta2_deg": 5.0, "mach": 3.0, "tag": "test"}
    for call in (queue.validate_only, queue.create):
        res = call(params)
        assert res["ok"] is False and res["stage"] == "gates"
        assert len(res["errors"]) == 1 and "gate 2 (shock on lip)" in res["errors"][0]
    assert not (queue_env / "jobs").exists()


def test_inverted_cell_reports_mesh_quality_and_writes_nothing(monkeypatch, queue_env):
    real = structured.Mesh.quality

    def bad_quality(self):
        return {**real(self), "n_inverted": 1}
    monkeypatch.setattr(structured.Mesh, "quality", bad_quality)
    params = {"family": "wedge", "theta1_deg": 8.0, "tag": "test"}
    for call in (queue.validate_only, queue.create):
        res = call(params)
        assert res["ok"] is False and res["stage"] == "mesh_quality"
        assert any("n_inverted = 1" in e for e in res["errors"])
    assert not (queue_env / "jobs").exists()
    assert list((queue_env / "tmp").iterdir()) == []         # temporary build directory removed


def test_valid_case_passes_all_stages(queue_env):
    res = queue.validate_only({"family": "wedge", "theta1_deg": 8.0, "tag": "test"})
    assert res["ok"] and res["stage"] == "done" and res["errors"] == []
    assert res["case_id"].startswith("wedge-") and res["mesh_quality"]["pass"] is True
    assert res["geometry"]

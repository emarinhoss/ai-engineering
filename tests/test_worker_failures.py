"""Failed jobs are flagged 2-failed with a reason in error.json."""
import json

import pytest

from tests.test_worker_end_to_end import PARAMS, flags, stage_job, worker


def error_of(queue, job):
    run_dir = queue / "runs" / job["case_id"]
    assert flags(queue, job["case_id"])[-1] == "2-failed" and "2-done" not in flags(queue, job["case_id"])
    assert not (queue / "runs" / f"{job['case_id']}.result.json").exists()   # nothing to download
    return json.loads((run_dir / "error.json").read_text())


def test_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_EXIT", "3")
    queue = tmp_path / "queue"
    job = stage_job(queue)
    assert worker(queue, "--once") == 0
    err = error_of(queue, job)
    assert err["reason"] == "nonzero_exit" and err["detail"]["exit_code"] == 3
    assert any("fake_su2" in line for line in err["detail"]["log_tail"])
    assert (queue / "runs" / job["case_id"] / "solver_version.txt").is_file()


def test_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_SLEEP", "5")
    queue = tmp_path / "queue"
    job = stage_job(queue)
    assert worker(queue, "--once", "--timeout", "1") == 0
    err = error_of(queue, job)
    assert err["reason"] == "timeout" and "1 s" in err["detail"]
    result = json.loads((queue / "runs" / job["case_id"] / "result_partial.json").read_text())
    assert result["run"]["timeout"] is True


def test_nan_residual(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SU2_NAN", "1")
    queue = tmp_path / "queue"
    job = stage_job(queue)
    assert worker(queue, "--once") == 0
    assert error_of(queue, job)["reason"] == "nan"
    record = json.loads((queue / "runs" / job["case_id"] / "result_partial.json").read_text())
    assert record["convergence"]["status"] == "diverged"


def test_missing_surface_file_is_a_postprocess_error(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    job = stage_job(queue)
    monkeypatch.setattr("tests.test_worker_end_to_end.WRAPPER", "import sys\nsys.exit(0)\n")
    assert worker(queue, "--once") == 0                        # exit 0 but no history, no surface
    assert error_of(queue, job)["reason"] == "postprocess_error"


def tampered(tmp_path, changes):
    """Stage a job, replace some of its keys (changes(job) -> dict), run the worker once."""
    queue = tmp_path / "queue"
    job = stage_job(queue)
    path = queue / "jobs" / f"{job['case_id']}.json"
    path.write_text(json.dumps({**job, "code_commit": "abc123", **changes(job)}))
    assert worker(queue, "--once") == 0
    run_dir = queue / "runs" / job["case_id"]
    assert not (run_dir / "history.csv").exists() and not (run_dir / "log.txt").exists()
    assert "1-running" not in flags(queue, job["case_id"])        # SU2 never started
    return job, error_of(queue, job)


def test_tampered_mesh_fingerprint_never_starts_su2(tmp_path):
    job, err = tampered(tmp_path, lambda job: {"mesh_fingerprint": "0" * 64})
    assert err["reason"] == "mesh_mismatch"
    d = err["detail"]
    assert d["job_mesh_fingerprint"] == "0" * 64 and d["our_mesh_fingerprint"] == job["mesh_fingerprint"]
    assert d["job_code_commit"] == "abc123" and d["our_code_commit"]
    assert d["max_bbox_diff_m"] == 0.0                              # same bbox: only the hash was changed


def test_mesh_mismatch_reports_the_bbox_difference(tmp_path):
    _, err = tampered(tmp_path, lambda job: {
        "mesh_fingerprint": "0" * 64, "mesh_bbox": [v + 0.001 for v in job["mesh_bbox"]]})
    assert err["reason"] == "mesh_mismatch"
    assert err["detail"]["max_bbox_diff_m"] == pytest.approx(0.001, abs=1e-9)


def test_tampered_config_hash_never_starts_su2(tmp_path):
    job, err = tampered(tmp_path, lambda job: {"config_sha256": "0" * 64})
    assert err["reason"] == "config_mismatch"
    assert err["detail"]["job_config_sha256"] == "0" * 64
    assert err["detail"]["our_config_sha256"] == job["config_sha256"]


def test_failed_job_is_not_picked_up_again(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_SU2_EXIT", "3")
    queue = tmp_path / "queue"
    job = stage_job(queue)
    worker(queue, "--once")
    stamp = (queue / "runs" / job["case_id"] / "error.json").stat().st_mtime_ns
    capsys.readouterr()
    assert worker(queue, "--once", "--stale-minutes", "0") == 0
    assert "nothing to do" in capsys.readouterr().out
    assert (queue / "runs" / job["case_id"] / "error.json").stat().st_mtime_ns == stamp


def test_unreadable_job_file_is_skipped(tmp_path, capsys):
    queue = tmp_path / "queue"
    (queue / "jobs").mkdir(parents=True)
    (queue / "jobs" / "wedge-0123456789.json").write_text('{"case_id": "wedge-01234')   # half synced
    assert worker(queue, "--once") == 0
    out = capsys.readouterr().out
    assert "skipping wedge-0123456789.json" in out and "nothing to do" in out
    assert not (queue / "runs" / "wedge-0123456789").exists()


def test_params_that_do_not_match_the_case_id_are_rejected(tmp_path):
    queue = tmp_path / "queue"
    job = stage_job(queue)
    path = queue / "jobs" / f"{job['case_id']}.json"
    path.write_text(json.dumps({**job, "params": {**PARAMS, "theta1_deg": 11.0}}))
    assert worker(queue, "--once") == 0
    assert error_of(queue, job)["reason"] == "bad_job"

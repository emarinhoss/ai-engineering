"""postprocess.collect_results: one row per record, failures kept with their reason."""
import csv
import json

from postprocess import collect_results


def test_table_has_results_and_failures(tmp_path):
    ok = tmp_path / "runs" / "inlet2r-aaaaaaaaaa"
    ok.mkdir(parents=True)
    (ok / "params.json").write_text(json.dumps({"theta1_deg": 8.0, "theta2_deg": 8.0, "mesh_level": "medium"}))
    (ok / "result.json").write_text(json.dumps({
        "convergence": {"status": "converged"}, "run": {"iterations": 1230, "wall_time_s": 258.51},
        "metrics": {"recovery_total": 0.3163, "q_peak_W_m2": 29725.42, "recovery_throat": 0.9085,
                    "q_peak_cowl_W_m2": 166511.2, "capture_ratio": 0.983}}))
    bad = tmp_path / "runs" / "inlet2r-bbbbbbbbbb"
    bad.mkdir()
    (bad / "params.json").write_text(json.dumps({"theta1_deg": 8.3, "theta2_deg": 13.1, "mesh_level": "medium"}))
    (bad / "error.json").write_text(json.dumps({"reason": "config_mismatch", "detail": {}}))
    (tmp_path / "runs" / "notes.txt").write_text("ignored")
    (tmp_path / "runs" / "empty").mkdir()

    out = tmp_path / "results.csv"
    collect_results.main([str(tmp_path / "runs"), "--out", str(out)])
    with open(out) as f:
        table = list(csv.DictReader(f))
    assert [r["case_id"] for r in table] == ["inlet2r-aaaaaaaaaa", "inlet2r-bbbbbbbbbb"]
    assert table[0]["status"] == "converged" and table[0]["q_peak_W_m2"] == "29725.42"
    assert table[0]["wall_time_s"] == "258.5" and table[0]["iterations"] == "1230"
    assert table[1]["status"] == "failed:config_mismatch" and table[1]["recovery_total"] == ""
    assert list(table[0].keys())[:6] == ["case_id", "theta1_deg", "theta2_deg", "recovery_total",
                                         "q_peak_W_m2", "status"]

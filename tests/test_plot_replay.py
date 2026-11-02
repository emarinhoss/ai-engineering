"""Replay plots and summary on a hand-made CSV: files exist, one median cell is right."""
import csv

import numpy as np

from postprocess.plot_replay import make_report

METRICS = ["rmse_recovery", "rmse_q_rel", "hv_regret", "step_seconds", "hyp_recovery_lengthscale"]
METRICS += [f"cov{p}_{k}" for p in (50, 80, 90, 95) for k in ("recovery", "q")]
PINNED = {("random", 0, 8, "rmse_recovery"): 1.2345, ("random", 1, 8, "rmse_recovery"): 1.2351}


def write_csv(path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["strategy", "seed", "n", "metric", "value"])
        w.writeheader()
        for strategy in ("random", "al_ehvi"):
            for seed in (0, 1):
                for n in (8, 12):
                    for metric in METRICS:
                        value = PINNED.get((strategy, seed, n, metric), 0.1 * (seed + 1) + 0.01 * n)
                        w.writerow({"strategy": strategy, "seed": seed, "n": n,
                                    "metric": metric, "value": value})


def test_make_report_writes_figures_and_summary(tmp_path):
    csv_path = tmp_path / "replay.csv"
    write_csv(csv_path)
    out_dir = tmp_path / "out"
    paths = make_report(csv_path, out_dir, "test")
    assert [p.name for p in paths] == ["test_error_vs_n.png", "test_calibration.png",
                                       "test_summary.md"]
    for png in paths[:2]:
        assert png.read_bytes()[:4] == b"\x89PNG"
    text = paths[2].read_text()
    lines = text.splitlines()
    assert lines[0] == "Input: replay.csv; seeds found: 2"
    expected = f"{np.median([1.2345, 1.2351]):.4g}"                  # 4 significant digits
    assert expected == "1.235"
    assert f"| 8 | {expected} |" in text
    assert "### coverage at n = 12" in text

"""postprocess/plot_model_compare.py on two small hand-made replay CSVs (test data, not results)."""
import csv

from postprocess.plot_model_compare import make
from surrogate.replay import COLUMNS


def write_csv(path, scale):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for strategy in ("random", "al_ehvi"):
            for seed in (0, 1):
                for n in (8, 12):
                    for metric, value in (("rmse_recovery", 1e-4 * scale / n), ("rmse_q_rel", 1e-3 * scale),
                                          ("hv_regret", 0.1 / n), ("cov90_recovery", 0.9), ("cov90_q", 0.8)):
                        w.writerow({"strategy": strategy, "seed": seed, "n": n, "metric": metric,
                                    "value": value * (1 + 0.1 * seed)})


def test_figure_and_tables(tmp_path):
    gp, mlp = tmp_path / "gp.csv", tmp_path / "mlp.csv"
    write_csv(gp, 1.0)
    write_csv(mlp, 3.0)
    png, md = make(gp, mlp, tmp_path, "cmp")
    assert png.stat().st_size > 10_000
    text = md.read_text()
    assert "random GP" in text and "al_ehvi MLP" in text
    assert "coverage at n = 12" in text
    # the median of the two seeds (1.0 and 1.1 times the base value) at n = 8 for the MLP
    assert f"{3e-4 / 8 * 1.05:.3g}" in text

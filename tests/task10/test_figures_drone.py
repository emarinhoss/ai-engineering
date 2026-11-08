"""T10.10e: the figures available from the records are drawn; the rest skip without raising."""
from pathlib import Path

import pytest

from analysis import figures_drone as fd

AVAILABLE = (fd.fig_front_lowfi, fd.fig_pool_replay, fd.fig_online_regret, fd.fig_e387_comparison)
SKIPPED = (fd.fig_front_band, fd.fig_mf_error, fd.fig_bias_table)


@pytest.mark.parametrize("fn", AVAILABLE)
def test_available_figure_is_drawn(fn, tmp_path):
    path = fn(fd.ROOT, tmp_path)
    assert path is not None and Path(path).is_file()
    assert Path(path).stat().st_size > 10_000


@pytest.mark.parametrize("fn", AVAILABLE + SKIPPED)
def test_empty_runs_tree_returns_none(fn, tmp_path, capsys):
    root = tmp_path / "empty"
    root.mkdir()
    assert fn(root, tmp_path / "out") is None
    assert "not run:" in capsys.readouterr().out


@pytest.mark.parametrize("fn", SKIPPED)
def test_su2_figures_skip_while_the_pool_is_absent(fn, tmp_path, capsys):
    # the repository has no runs/pool_af/results.csv or bias table yet; when they land, the figure
    # functions are to be written and this test replaced
    if (fd.ROOT / fd.SU2_POOL).is_file() or (fd.ROOT / fd.BIAS_TABLE).is_file():
        pytest.skip("inputs exist now; write the figure")
    assert fn(fd.ROOT, tmp_path) is None
    assert "not run:" in capsys.readouterr().out


def test_main_reports_and_writes_captions(tmp_path):
    drawn, skipped = fd.main(fd.ROOT, tmp_path)
    assert len(drawn) == len(AVAILABLE) and len(skipped) == len(SKIPPED)
    text = (tmp_path / "captions.md").read_text()
    assert all(p.name in text for p in drawn)
    assert "runs/e387" in text

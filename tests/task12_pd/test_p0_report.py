"""The committed P0 report is the text the record generates, and it states the things a reader must not miss."""
import json

from prelim import p0_baseline as p0
from prelim.p0_report import report_text

OUT = p0.REPO / "runs/task12/pd/2026-11-27/p0"
REPORT = p0.REPO / "docs/validation/2026-11-27_task12_pd_p0.md"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_carries_each_acceptance_verdict_of_the_record():
    text = REPORT.read_text()
    rows = [ln for ln in text.splitlines() if ln.startswith("| ") and ln.split("|")[1].strip() in list("123456")]
    acc = json.loads((OUT / "p0.json").read_text())["acceptance"]
    assert len(rows) == len(acc) == 6
    for line, a in zip(rows, acc):
        assert line.split("|")[1].strip() == str(a["row"]) and line.rstrip().endswith(f"**{a['verdict']}** |")


def test_report_says_what_the_extension_is_not():
    text = REPORT.read_text()
    assert "have no printed value behind them" in text and "extrapolation" in text
    assert "coding check (same model, extended range)" in text
    assert "Those two writers were not run" in text
    assert "## 10. Assumptions made where the spec left a choice" in text

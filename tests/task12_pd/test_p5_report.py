"""The committed P5 report is the text the record generates, and it states what a reader must not miss.
Written before the run (tests first); run on Opus 5.5 under ruling PD-22, not yet Fable-reviewed."""
import json

from prelim import p5_loads as p5
from prelim.p5_report import ASSUMPTIONS, FIGURES, report_text

OUT = p5.REPO / "runs/task12/pd/2026-11-28/p5"
REPORT = p5.REPO / "docs/validation/2026-11-28_task12_pd_p5.md"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_is_marked_not_yet_reviewed_near_the_top():
    head = "\n".join(REPORT.read_text().splitlines()[:6])
    assert "Not yet Fable-reviewed (ruling PD-22)" in head


def test_every_figure_exists_with_its_sidecar():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert sorted(links) == sorted(f"2026-11-28_task12_pd_p5/{n}.png" for n in FIGURES)
    for link in links:
        png = p5.REPO / "docs/validation/figures" / link
        assert png.stat().st_size > 1000, link
        side = json.loads(png.with_suffix(".json").read_text())
        assert side["figure"] == png.name and side["p5_json_sha256"] == p5.sha256(OUT / "p5.json")
        assert "matplotlib only" in side["made_by"]


def test_report_states_sources_rows_and_assumptions():
    text = REPORT.read_text()
    r = json.loads((OUT / "p5.json").read_text())
    for words in (r["sources"]["cs23"]["pdf_sha256"], r["sources"]["naca1206"]["pdf_sha256"], "rgl.faa.gov", "drs.faa.gov",
                  "CS 23.341(c)", "NACA Report 1206", "operating case", "hypothetical", "PD-13", "O-2", "reported, not tuned",
                  "Findings for r1", "What this does not show"):
        assert words in text, words
    for a in r["acceptance"]:
        assert f"| {a['row']} |" in text and a["verdict"] in text
    for a in ASSUMPTIONS:
        assert a in text
    assert ".pdf)" not in text


def test_ruling_pd22_is_recorded():
    text = (p5.REPO / "docs/specs/00_decisions.md").read_text()
    assert "- **PD-22 (2026-11-28, owner ruling: packages P5, P7 and P8 run on Opus 5.5" in text
    block = text.split("- **PD-22 (2026-11-28", 1)[1]
    for words in ("Éder", "2026-11-30 17:00 UTC", "not yet Fable-reviewed", "tests written first", "P9"):
        assert words in block, words

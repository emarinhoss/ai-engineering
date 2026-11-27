"""The committed P2 report is the text the record generates, and it states the things a reader must not miss."""
import json

from prelim import p2_section as p2
from prelim.p2_report import FIGURE_LABEL, report_text

OUT = p2.REPO / "runs/task12/pd/2026-11-27/p2b"
REPORT = p2.REPO / "docs/validation/2026-11-27_task12_pd_p2.md"
FIGURES = p2.REPO / "docs/validation/figures/2026-11-27_task12_pd_p2"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_carries_each_acceptance_verdict_of_the_record():
    text = REPORT.read_text()
    block = text.split("## 2. Acceptance rows", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in block.splitlines() if ln.startswith("| ") and ln.split("|")[1].strip().isdigit()]
    acc = json.loads((OUT / "p2.json").read_text())["acceptance"]
    assert len(rows) == len(acc) == 8
    for line, a in zip(rows, acc):
        tail = ", provisional" if a.get("provisional") else ""
        assert line.split("|")[1].strip() == str(a["row"]) and line.rstrip().endswith(f"**{a['verdict']}{tail}** |")


def test_every_linked_figure_exists_with_its_sidecar():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert len(links) == 3
    for link in links:
        assert (p2.REPO / "docs/validation/figures" / link).stat().st_size > 1000, link
    side = json.loads((FIGURES / "figures.json").read_text())
    assert side["label"] == FIGURE_LABEL and "checked against the report's figure" in FIGURE_LABEL
    assert side["p2_json_sha256"] == p2.sha256(OUT / "p2.json")
    assert sorted(side["figures"]) == sorted(q.name for q in FIGURES.glob("*.png"))


def test_report_says_what_the_package_is_not():
    text = REPORT.read_text()
    assert "Opened in this session: **yes**" in text and "Read twice: **yes**" in text
    assert "19930090976" in text and "The PDF is not committed" in text and "403" in text
    assert "supersedes `runs/task12/pd/2026-11-27/p2`" in text and "Figure number: none" in text
    assert "r0 is not changed here" in text or "No finding for r1 from row 2" in text
    assert "**Not run.**" in text and "O-1" in text
    assert "no verdict rests on it" in text.lower()
    assert "Status: **not obtained**" in text
    assert "## 13. Assumptions made where the spec left a choice" in text
    assert "## 14. What this does not show" in text

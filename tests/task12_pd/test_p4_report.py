"""The committed P4 report is the text the record generates, and it states the things a reader must not miss."""
import json

from prelim import p4_balance as p4
from prelim.p4_report import ASSUMPTIONS, FIGURES, report_text

OUT = p4.REPO / "runs/task12/pd/2026-11-27/p4"
REPORT = p4.REPO / "docs/validation/2026-11-27_task12_pd_p4.md"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_carries_each_verdict_of_the_record():
    text = REPORT.read_text()
    block = text.split("## 2. Acceptance rows", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in block.splitlines() if ln.startswith("| ") and ln.split("|")[1].strip().isdigit()]
    acc = json.loads((OUT / "p4.json").read_text())["acceptance"]
    assert len(rows) == len(acc) == 5
    for line, a in zip(rows, acc):
        assert int(line.split("|")[1]) == a["row"] and line.rstrip().endswith(f"**{a['verdict']}** |")


def test_every_figure_exists_with_its_sidecar():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert sorted(links) == sorted(f"2026-11-27_task12_pd_p4/{n}.png" for n in FIGURES)
    for link in links:
        png = p4.REPO / "docs/validation/figures" / link
        assert png.stat().st_size > 1000, link
        side = json.loads(png.with_suffix(".json").read_text())
        assert side["figure"] == png.name and side["p4_json_sha256"] == p4.sha256(OUT / "p4.json")
        assert "matplotlib only" in side["made_by"] and "no flow solution" in side["label"]


def test_report_says_what_the_package_is_and_is_not():
    text = REPORT.read_text()
    p = json.loads((OUT / "p4.json").read_text())
    assert p["evidence_class"] in text and "nothing was tuned" in text
    for words in ("NACA TM 1036", "NACA-WR-L-25", "PD-20", "not changed", "no verdict", "Payload off", "What this does not show",
                  "does not close", "sponson was not resized", "not re-sized"):
        assert words in text, words
    for a in ASSUMPTIONS:
        assert a in text
    for finding in p["findings_for_r1"]:
        assert finding in text
    for s in p["sources"]["reports"].values():
        assert s["url"] in text and s["pdf_sha256"][:12] in text
    assert ".pdf)" not in text.replace(".pdf, sha256", "")

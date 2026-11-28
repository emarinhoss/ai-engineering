"""The committed P4b report is the text the record generates, and it states the things a reader must not miss."""
import json

from prelim import p4b_trade as t
from prelim.p4b_report import ASSUMPTIONS, FIGURES, report_text

OUT = t.REPO / "runs/task12/pd/2026-11-28/p4b"
REPORT = t.REPO / "docs/validation/2026-11-28_task12_pd_p4b.md"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_every_figure_exists_with_its_sidecar():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert sorted(links) == sorted(f"2026-11-28_task12_pd_p4b/{n}.png" for n in FIGURES)
    for link in links:
        png = t.REPO / "docs/validation/figures" / link
        assert png.stat().st_size > 1000, link
        side = json.loads(png.with_suffix(".json").read_text())
        assert side["figure"] == png.name and side["p4b_json_sha256"] == t.p4.sha256(OUT / "p4b.json")
        assert "matplotlib only" in side["made_by"] and "no flow solution" in side["label"]


def test_report_says_what_the_package_is_and_is_not():
    text = REPORT.read_text()
    p = json.loads((OUT / "p4b.json").read_text())
    assert p["evidence_class"] in text and "nothing was tuned" in text and p["chosen_label"] in text
    for words in ("PD-20", "PD-21", "not changed", "**assumed**", "written before the comparison", "What this does not show", "operating limit",
                  "not re-sized", "ballast", "reported, not tuned"):
        assert words in text, words
    for step in p["choices"]["selection_rule"]["steps"]:
        assert step in text
    for a in ASSUMPTIONS:
        assert a in text
    for finding in p["findings_for_r1"]:
        assert finding in text
    for name, rows in p["selection"]["failed_step_1"].items():      # a failed row is named
        assert rows and ("fails" in text)
    assert ".pdf" not in text


def test_decision_pd21_is_recorded_and_pd20_is_kept():
    text = (t.REPO / "docs/specs/00_decisions.md").read_text()
    assert "- **PD-20 (2026-11-27, package P4: the tail clear of the propeller disc, solved with the wing position).**" in text
    assert "- **PD-21 (2026-11-28, package P4b" in text
    block = text.split("- **PD-21 (2026-11-28, package P4b", 1)[1]
    for words in ("supersedes", "PD-20", "r1", "docs/validation/2026-11-28_task12_pd_p4b.md", "ballast", "assum"):
        assert words in block, words

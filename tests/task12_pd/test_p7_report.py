"""The committed P7 report is the text the record generates, and it states what a reader must not miss.
Written before the run (tests first); run on Opus 5.5 under ruling PD-22, not yet Fable-reviewed."""
import json

from prelim import p7_spar as p7
from prelim.p7_report import ASSUMPTIONS, FIGURES, report_text

OUT = p7.REPO / "runs/task12/pd/2026-11-28/p7"
REPORT = p7.REPO / "docs/validation/2026-11-28_task12_pd_p7.md"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_is_marked_not_yet_reviewed_near_the_top():
    head = "\n".join(REPORT.read_text().splitlines()[:6])
    assert "Not yet Fable-reviewed (ruling PD-22)" in head


def test_every_figure_exists_with_its_sidecar():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert sorted(links) == sorted(f"2026-11-28_task12_pd_p7/{n}.png" for n in FIGURES)
    for link in links:
        png = p7.REPO / "docs/validation/figures" / link
        assert png.stat().st_size > 1000, link
        side = json.loads(png.with_suffix(".json").read_text())
        assert side["figure"] == png.name and side["p7_json_sha256"] == p7.sha256(OUT / "p7.json")
        assert "matplotlib only" in side["made_by"]


def test_report_states_sources_rows_and_assumptions():
    text = REPORT.read_text()
    r = json.loads((OUT / "p7.json").read_text())
    for words in ("(14.9)-(14.11), p. 343", "(14.35), p. 383", "(14.37), p. 385", "Fig. 14.42", "Table 14.4, p. 368-369",
                  "could not be opened", "drone/vlm.py", "knock-down", "[Not lib]", "PD-23", "item 8", "reported, not tuned",
                  "Findings for r1", "What this does not show", "429.4"):
        assert words in text, words
    for a in r["acceptance"]:
        assert f"| {a['row']} |" in text and a["verdict"] in text
    for a in ASSUMPTIONS:
        assert a in text


def test_decision_pd23_is_recorded():
    text = (p7.REPO / "docs/specs/00_decisions.md").read_text()
    assert "- **PD-23 (2026-11-28, package P7: how the wing spar is idealised and sized).**" in text
    block = text.split("- **PD-23 (2026-11-28", 1)[1]
    for words in ("not an owner ruling", "PD-22", "0.50", "0.35 to 0.65", "envelope of the ruled load cases", "pd_p7_choices.yaml"):
        assert words in block, words

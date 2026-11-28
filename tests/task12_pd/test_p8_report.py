"""The committed envelope-protection requirement and the P8 report are the text the record generates, and they state
what a reader must not miss. Written before the run (tests first); run on Opus 5.5 under ruling PD-22, not yet
Fable-reviewed."""
import json

from prelim import p8_envelope as p8
from prelim.p8_report import ASSUMPTIONS, doc_checks, report_text, requirement_text

OUT = p8.REPO / p8.OUT_DEFAULT
REQUIREMENT = p8.REPO / "docs/specs/task12_envelope_protection.md"
REPORT = p8.REPO / "docs/validation/2026-11-28_task12_pd_p8.md"


def test_committed_requirement_is_generated_from_the_record():
    assert REQUIREMENT.read_text() == requirement_text(OUT)


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_requirement_says_first_that_this_repository_does_not_design_the_system():
    head = "\n".join(REQUIREMENT.read_text().splitlines()[:4])
    assert "requirement on a system that this repository does not design (PD-11)" in head
    assert "Not yet Fable-reviewed (ruling PD-22)" in "\n".join(REQUIREMENT.read_text().splitlines()[:6])


def test_report_is_marked_not_yet_reviewed_near_the_top():
    assert "Not yet Fable-reviewed (ruling PD-22)" in "\n".join(REPORT.read_text().splitlines()[:4])


def test_requirement_has_one_table_with_every_row_and_its_numbers():
    text = REQUIREMENT.read_text()
    rows = [ln for ln in text.splitlines() if ln.startswith("| EP-")]
    r = json.loads((OUT / "p8.json").read_text())
    table = [ln for ln in rows if ln.count("|") == 5]
    assert [ln.split("|")[1].strip() for ln in table] == [f"EP-{k}" for k in range(1, 10)]
    for ln, row in zip(table, r["rows"]):
        for x in row["numbers"]:
            assert p8.fmt(x) in ln, (row["id"], x["name"])
        for s in row["sources"]:
            assert p8.RECORDS[s] in ln
    assert doc_checks(OUT)["verdict"] == "pass"


def test_report_states_acceptance_and_assumptions():
    text = REPORT.read_text()
    r = json.loads((OUT / "p8.json").read_text())
    for a in r["acceptance"]:
        assert a["verdict"] in text
    for words in ("Findings for r1", "What this does not show", "reported, not tuned", "Second reading, no weight", "PD-24"):
        assert words in text, words
    for a in ASSUMPTIONS:
        assert a in text


def test_decision_pd24_is_recorded():
    text = (p8.REPO / "docs/specs/00_decisions.md").read_text()
    assert "- **PD-24 (2026-11-28, package P8" in text
    block = text.split("- **PD-24 (2026-11-28", 1)[1]
    for words in ("not yet Fable-reviewed", "30 ft/s", "0.1 g", "23,000 ft", "data/task12/pd_p8_choices.yaml"):
        assert words in block, words

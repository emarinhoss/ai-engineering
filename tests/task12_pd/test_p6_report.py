"""The committed P6 report is the text the record generates, and it states the things a reader must not miss."""
import json

from prelim import p6_propeller as p6
from prelim.p6_report import FIGURE_LABEL, report_text

OUT = p6.REPO / "runs/task12/pd/2026-11-27/p6"
REPORT = p6.REPO / "docs/validation/2026-11-27_task12_pd_p6.md"
FIGURES = p6.REPO / "docs/validation/figures/2026-11-27_task12_pd_p6"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_carries_each_verdict_of_the_record():
    text = REPORT.read_text()
    block = text.split("## 2. Validation and acceptance rows", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in block.splitlines() if ln.startswith("| V") or ln.startswith("| A")]
    acc = json.loads((OUT / "p6.json").read_text())["acceptance"]
    assert len(rows) == len(acc) == 9
    for line, a in zip(rows, acc):
        assert line.split("|")[1].strip() == ("V" if a["group"] == "validation" else "A") + str(a["row"])
        assert line.rstrip().endswith(f"**{a['verdict']}** |")


def test_every_linked_figure_exists_with_its_sidecar():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert len(links) == 3
    for link in links:
        assert (p6.REPO / "docs/validation/figures" / link).stat().st_size > 1000, link
    side = json.loads((FIGURES / "figures.json").read_text())
    assert side["label"] == FIGURE_LABEL and side["p6_json_sha256"] == p6.sha256(OUT / "p6.json")
    assert sorted(side["figures"]) == sorted(q.name for q in FIGURES.glob("*.png"))


def test_report_says_what_the_package_is_and_is_not():
    text = REPORT.read_text()
    res = json.loads((OUT / "p6.json").read_text())
    if res["used_in_r1"]:
        assert "may be used in r1" in text
    else:
        assert "failed-validation number and is not used in r1" in text and "Nothing was tuned" in text
        assert text.count("not used in r1") >= 5
    for token in ("19930091715", "19930091327", "19930093324", "The PDF is not committed", "Opened in this session: **yes**",
                  "**not opened**", "r0 is not changed here", "## 10. Assumptions made where the spec left a choice",
                  "## 11. What this does not show"):
        assert token in text, token

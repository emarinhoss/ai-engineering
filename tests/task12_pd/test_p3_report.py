"""The committed P3 report is the text the record generates, and it states the things a reader must not miss."""
import json

from prelim import p3_loft as p3
from prelim.p3_report import ASSUMPTIONS, FIGURE_LABEL, report_text

OUT = p3.REPO / "runs/task12/pd/2026-11-27/p3"
REPORT = p3.REPO / "docs/validation/2026-11-27_task12_pd_p3.md"
FIGURES = p3.REPO / "docs/validation/figures/2026-11-27_task12_pd_p3"


def test_committed_report_is_generated_from_the_record():
    assert REPORT.read_text() == report_text(OUT)


def test_report_carries_each_verdict_of_the_record():
    text = REPORT.read_text()
    block = text.split("## 2. Gates", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in block.splitlines() if ln.startswith("| ") and ln.split("|")[1].strip().isdigit()]
    acc = json.loads((OUT / "p3.json").read_text())["acceptance"]
    assert len(rows) == len(acc) == 10
    for line, a in zip(rows, acc):
        assert int(line.split("|")[1]) == a["row"] and line.rstrip().endswith(f"**{a['verdict']}** |")


def test_every_render_exists_with_its_sidecar_and_label():
    text = REPORT.read_text()
    links = [part.split(")")[0] for part in text.split("](figures/")[1:]]
    assert sorted(links) == sorted(f"2026-11-27_task12_pd_p3/{n}.png" for n in ("top", "side", "front", "perspective", "arrangement"))
    for link in links:
        png = p3.REPO / "docs/validation/figures" / link
        assert png.stat().st_size > 1000, link
        side = json.loads(png.with_suffix(".json").read_text())
        assert side["label"] == FIGURE_LABEL == "geometry only, no flow solution" and side["figure"] == png.name
        assert side["p3_json_sha256"] == p3.sha256(OUT / "p3.json") and side["stl_sha256"] == p3.sha256(OUT / "loft.stl")
    views = [json.loads((FIGURES / f"{n}.json").read_text())["projection"] for n in ("top", "side", "front", "perspective")]
    assert views == ["ortho", "ortho", "ortho", "persp"]              # three orthographic views and one perspective view


def test_report_says_what_the_package_is_and_is_not():
    text = REPORT.read_text()
    res = json.loads((OUT / "p3.json").read_text())
    for token in ("19930091662", "19930091108", "the PDF is not committed", "r0 is not changed here", "PD-19", "nothing was tuned",
                  "## 10. Findings for r1", "## 12. Assumptions made where the spec left a choice", "## 13. What this does not show",
                  "geometry only, no flow solution", "not a reading", "Report 460"):
        assert token in text, token
    for k, f in enumerate(res["findings_for_r1"], 1):
        assert f"{k}. {f}" in text
    for a in ASSUMPTIONS:
        assert a in text
    if res["gates"]["3"]["verdict"] == "fail":
        assert "the build-up was re-run with the loft's areas" in text and "not credited here" in text
    if res["gates"]["8"]["verdict"] == "not run":
        assert "**Not run**" in text
    else:
        assert "was **not established**" in text or res["gates"]["8"]["verdict"] == "pass"

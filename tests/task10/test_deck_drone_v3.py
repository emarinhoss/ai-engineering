"""Version 3 of the drone deck: slides named by number only, the moved and new slides where the
outline puts them, the left-out backups gone, no earlier slide id or "unconverged" anywhere, and the
new tables equal to the records they are read from."""
import re
import statistics

import pytest
from pptx import Presentation

from docs.talk import build_deck_drone as v1
from docs.talk import build_deck_drone_v3 as v3
from tests.task10.test_deck_drone_v2 import texts

FOOTER = re.compile(r"\d+")


@pytest.fixture(scope="module")
def deck(tmp_path_factory):
    out = tmp_path_factory.mktemp("deck") / "deck_drone_v3.pptx"
    n = v3.build(out)
    return n, Presentation(str(out))


def footer(slide):
    small = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame
             and sh.top is not None and sh.top > 6.9 * 914400]
    return [t for t in small if FOOTER.fullmatch(t.strip())]


def test_numbers_only_and_the_order_of_the_outline(deck):
    n, prs = deck
    outline = v3.read_outline()
    main = [s for s in outline if s["main"]]
    assert n == len(prs.slides) == len(outline) + 1                    # one Backup divider
    for i, slide in enumerate(prs.slides, 1):
        if i == len(main) + 1:
            continue                                                    # the divider
        assert footer(slide) == [str(i)], i
        for t in texts(slide):
            assert not v3.ID_RE.search(t), (i, t[:80])
            assert "unconverged" not in t.lower(), i


def test_the_requested_moves_and_removals():
    outline = {s["number"]: s for s in v3.read_outline()}
    main = {k: s for k, s in outline.items() if s["main"]}
    assert "nominal design" in main[5]["title"]                         # version-2 backup 1
    assert "Claude Code" in main[9]["title"]                            # version-1 D26
    assert "Gaussian process" in main[15]["title"]
    assert not any("Queue" in s["title"] for s in main.values())
    backup_titles = [s["title"] for s in outline.values() if not s["main"]]
    assert any("regret" in t for t in backup_titles) and any("Queue" in t for t in backup_titles)
    for gone in ("Open rulings", "Equations", "Ledger provenance", "The decision log",
                 "inverse query record", "low-fidelity Pareto record", "Budget-exhausted",
                 "What the record keeps", "Coarse against medium", "Bias sweep",
                 "stall at 14 degrees, pressure", "Where the wall shear", "Tunnel pressure",
                 "learned warm start"):
        assert not any(gone.lower() in t.lower() for t in backup_titles), gone


def test_gp_comparison_table_equals_the_two_level_record():
    rows = v3.model_comparison_rows()
    m = v1.mf_means()
    ns = sorted({n for (model, n, _) in m if model == "two"})
    lf = statistics.mean(float(r["value"]) for r in v1.csv_rows(v1.MF)
                         if r["model"] == "lf_raw" and r["metric"] == "rmse_endurance")
    assert rows[1][1] == f"{lf:.3f} (no fit)"
    assert rows[2][1] == ", ".join(f"{m[('single', n, 'rmse_endurance')]:.3f}" for n in ns)
    assert rows[3][1] == ", ".join(f"{m[('two', n, 'rmse_endurance')]:.3f}" for n in ns)


def test_regret_table_equals_the_pool_replay():
    rows = v3.regret_rows()
    vals = [float(r["value"]) for r in v1.csv_rows(v1.fd.POOL_REPLAY)
            if r["metric"] == "hv_regret" and r["strategy"] == "al_ehvi" and r["n"] == "16"]
    row16 = next(r for r in rows if r[0] == "16")
    assert row16[4] == f"{statistics.mean(vals):.3f}"


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z{\"])")


def sentences(text):
    """Sentences of a note template; a {placeholder} counts as one word."""
    return [s for p in text.split("\n") for s in SENTENCE.split(p) if s.strip()]


def test_presenter_notes_follow_the_ste_length_rules():
    """ASD-STE100: at most 25 words in a descriptive sentence, at most 6 sentences in a paragraph."""
    for s in v3.read_outline():
        assert s["notes"], s["number"]
        for para in s["notes"].split("\n"):
            assert len(sentences(para)) <= 6, (s["number"], para[:60])
        for sent in sentences(s["notes"]):
            assert len(sent.split()) <= 25, (s["number"], sent)


def test_slide_notes_and_transcript_are_the_filled_presenter_notes(deck, tmp_path):
    _, prs = deck
    v = v3.values()
    outline = v3.read_outline()
    by_number = {s["number"]: s for s in outline}
    for i, slide in enumerate(prs.slides, 1):
        if i in by_number:
            assert slide.notes_slide.notes_text_frame.text == v3.v2.fill(by_number[i]["notes"], v), i
    out = tmp_path / "t.md"
    v3.write_transcript(outline, v, out)
    text = out.read_text()
    assert text.count("\n## Slide ") == len(outline) + 1 and "{" not in text


def test_slide_7_names_every_registered_tool_and_the_session_and_worker_roles(deck):
    _, prs = deck
    text = " ".join(texts(prs.slides[6]))
    for name, _doc in v1.mcp_tools():
        assert name in text, name
    for phrase in ("Colab command-line tool", "shard", "physics gates again", "heartbeat",
                   "SHA-256", "selects no design point"):
        assert phrase in text, phrase

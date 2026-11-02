"""The talk deck builds, has 38 slides, and every figure it places exists."""
from pptx import Presentation

from docs.talk import build_deck


def test_deck_builds_with_38_slides_and_existing_figures(tmp_path):
    out = tmp_path / "deck.pptx"
    n = build_deck.build(out)
    assert n == 38                                   # 24 talk + 6 backup + 8 section dividers
    assert len(Presentation(str(out)).slides) == 38
    assert build_deck.USED_FIGURES, "no figure was placed"
    for rel in build_deck.USED_FIGURES:
        assert (build_deck.ROOT / rel).is_file(), rel


def test_notes_come_from_the_outline_and_pending_is_visible(tmp_path):
    out = tmp_path / "deck.pptx"
    build_deck.build(out)
    outline = build_deck.read_outline()
    assert len(outline) == 30                        # S1 to S24 and B1 to B6
    texts, notes = [], []
    for slide in Presentation(str(out)).slides:
        texts.append(" ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame))
        if slide.has_notes_slide:
            notes.append(slide.notes_slide.notes_text_frame.text)
    assert all(o["notes"] in notes for o in outline.values())
    assert any("PENDING" in t and "inlet2r-374dad241f" in t for t in texts)

"""The talk deck builds, has 40 slides, and every figure it places exists."""
from pptx import Presentation

from docs.talk import build_deck


def test_deck_builds_with_40_slides_and_existing_figures(tmp_path):
    out = tmp_path / "deck.pptx"
    n = build_deck.build(out)
    assert n == 40                                   # 25 talk (S1a added) + 7 backup + 8 section dividers
    assert len(Presentation(str(out)).slides) == 40
    assert build_deck.USED_FIGURES, "no figure was placed"
    for rel in build_deck.USED_FIGURES:
        assert (build_deck.ROOT / rel).is_file(), rel


def test_notes_come_from_the_outline_and_pending_is_visible(tmp_path):
    out = tmp_path / "deck.pptx"
    build_deck.build(out)
    outline = build_deck.read_outline()
    assert len(outline) == 32                        # S1 to S24, S1a and B1 to B7
    texts, notes = [], []
    for slide in Presentation(str(out)).slides:
        texts.append(" ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame))
        if slide.has_notes_slide:
            notes.append(slide.notes_slide.notes_text_frame.text)
    assert all(o["notes"] in notes for o in outline.values())
    assert any("C2 pass" in t and "inlet2r-374dad241f" in t for t in texts)


def test_figures_made_from_run_data_are_placed(tmp_path):
    build_deck.build(tmp_path / "deck.pptx")
    for name in ("mesh_8_8_medium", "wall_8_8_laminar_vs_sa", "wall_12_14_diverged", "cylinder_schemes"):
        assert f"docs/talk/figures/{name}.png" in build_deck.USED_FIGURES

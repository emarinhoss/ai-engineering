"""The talk deck builds, has 51 slides, and every figure it places exists."""
import pytest
from pptx import Presentation

from docs.talk import build_deck, equations


def test_deck_builds_with_51_slides_and_existing_figures(tmp_path):
    out = tmp_path / "deck.pptx"
    n = build_deck.build(out)
    assert n == 51                                   # 29 talk (S1a, S1b-d, S20a-d) + 12 backup + 10 section dividers
    assert len(Presentation(str(out)).slides) == 51
    assert build_deck.USED_FIGURES, "no figure was placed"
    for rel in build_deck.USED_FIGURES:
        assert (build_deck.ROOT / rel).is_file(), rel


def test_notes_come_from_the_outline_and_pending_is_visible(tmp_path):
    out = tmp_path / "deck.pptx"
    build_deck.build(out)
    outline = build_deck.read_outline()
    assert len(outline) == 41                        # S1 to S24, S1a to S1d, S20a to S20d and B1 to B9
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


def test_every_outline_equation_renders_and_sits_on_its_slide_as_a_picture(tmp_path, monkeypatch):
    """Each `**Equations:**` entry renders, and its slide carries exactly those pictures (alt text = LaTeX)."""
    out = tmp_path / "deck.pptx"
    build_deck.build(out)
    monkeypatch.setattr(equations, "EQ_DIR", tmp_path / "eq")  # the checks below draw at the default size
    outline = build_deck.read_outline()
    by_id = {}
    for slide in Presentation(str(out)).slides:
        for sh in slide.shapes:
            if sh.has_text_frame and "  |  " in sh.text_frame.text and len(sh.text_frame.text) < 14:
                by_id[sh.text_frame.text.split("  |  ")[0]] = slide
    n_equations = 0
    for sid, info in outline.items():
        listed = info.get("equations", [])
        for latex in listed:
            path = equations.render(latex)
            assert path.is_file() and path.stat().st_size > 2000, f"{sid}: {latex}"
        if listed:
            placed = equations.placed_on(by_id[sid])
            assert sorted(latex for latex, _ in placed) == sorted(listed), sid
            assert all(len(blob) > 2000 for _, blob in placed), sid
        n_equations += len(listed)
    assert n_equations >= 20
    for sid in ("S2", "S6", "S7", "S13", "S14", "S15", "S20c"):
        assert outline[sid].get("equations"), sid


def test_equation_render_is_deterministic_and_rejects_bad_latex(tmp_path, monkeypatch):
    monkeypatch.setattr(equations, "EQ_DIR", tmp_path / "eq")
    latex = r"y_H=\rho\,y_L+d,\quad \sigma^{2}=\dfrac{a}{b}"
    first = equations.render(latex)
    stamp = first.stat().st_mtime_ns
    second = equations.render(latex)                  # same source and size: same file, not redrawn
    assert first == second and second.stat().st_mtime_ns == stamp
    assert first.name == equations.eq_path(latex).name and first.stat().st_size > 2000
    assert equations.eq_path(latex, fontsize=18) != first          # the size is part of the name
    target = tmp_path / "bad.png"
    for bad in (r"\frac{1}{", r"\notacommand{2}", r"\left(x"):
        with pytest.raises(ValueError):
            equations.render(bad, path=target)
        assert not target.exists() and not list(tmp_path.glob("*.png*"))

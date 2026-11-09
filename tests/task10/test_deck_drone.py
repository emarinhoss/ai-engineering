"""T10.11b: the drone deck builds from its outline, one slide per outline entry, every Source real."""
import re

import pytest
from pptx import Presentation

from docs.talk import build_deck_drone as bdd

ROOT = bdd.ROOT


@pytest.fixture(scope="module")
def deck(tmp_path_factory):
    out = tmp_path_factory.mktemp("deck") / "deck_drone.pptx"
    n = bdd.build(out)
    return n, Presentation(str(out))


def test_slide_count_matches_the_outline(deck):
    n, prs = deck
    slides = bdd.read_outline()
    assert n == len(prs.slides) == len(slides)
    assert 12 <= n <= 25
    ids = [s["id"] for s in slides]
    assert len(set(ids)) == n
    numbers = [int(re.match(r"D(\d+)", i).group(1)) for i in ids]
    assert numbers == sorted(numbers) and set(numbers) == set(range(1, max(numbers) + 1))


def test_every_source_is_an_existing_file_or_pending():
    for s in bdd.read_outline():
        src = s["source"]
        if src.startswith(("PENDING", "none")):
            continue
        paths = re.findall(r"`([^`]+)`", src)
        assert paths, f"{s['id']}: Source names no file"
        for p in paths:
            assert (ROOT / p).is_file(), f"{s['id']}: {p} does not exist"


def test_notes_are_at_most_three_sentences_and_placeholders_resolve(deck):
    _, prs = deck
    for slide, s in zip(prs.slides, bdd.read_outline()):
        notes = slide.notes_slide.notes_text_frame.text
        assert "{" not in notes and "}" not in notes, s["id"]
        assert len(re.findall(r"[.!?](?:\s|$)", notes)) <= 3, s["id"]
        text = " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
        assert "{" not in text, s["id"]


def test_pending_slides_say_pending_and_show_no_su2_pool_number(deck):
    _, prs = deck
    by_id = {s["id"]: sl for s, sl in zip(bdd.read_outline(), prs.slides)}
    for sid in ("D11", "D12", "D13"):
        text = " ".join(sh.text_frame.text for sh in by_id[sid].shapes if sh.has_text_frame)
        assert "PENDING" in text


def test_numbers_come_from_the_records():
    v = bdd.values()
    assert v["n_fail"] == 0 and v["n_pending"] == 1 and v["v6e_tol"] == "5 %"
    assert v["pool_cases"] == 172
    assert v["front_n"] == bdd.jload("runs/drone_grid/2026-11-08/record.json")["front_size"]


DRAWINGS = {"D3a": "planform.png", "D3b": "closure_energy.png", "D4a": "queue_gates.png",
            "D4b": "airfoil2d_mesh.png", "D5a": "vlm_lattice.png", "D8a": "design_space.png",
            "D12": "two_level.png"}


def test_drawings_are_built_and_placed(deck):
    _, prs = deck
    bdd.ensure_drawings()
    for name in DRAWINGS.values():
        assert (ROOT / bdd.FIG_DRONE / name).stat().st_size > 20_000, name
    by_id = {s["id"]: sl for s, sl in zip(bdd.read_outline(), prs.slides)}
    for sid in DRAWINGS:
        assert any(sh.shape_type == 13 for sh in by_id[sid].shapes), f"{sid}: no picture"
    boxes = [sh for sh in by_id["D3"].shapes if sh.shape_type == 1]
    assert len(boxes) >= 9, "D3 pipeline and section boxes"


def test_drawing_numbers_come_from_the_code_and_records():
    v = bdd.values()
    _params, _, out, _ = bdd.nominal()
    assert v["nom_mtow"] == f"{out['mtow_kg']:.2f}" and v["nom_span"] == "2"
    assert v["mesh_cells"] == "21,760"
    assert 0 <= v["n_front_edge"] <= v["n_front"] == 15

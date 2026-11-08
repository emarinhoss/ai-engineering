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
    assert 12 <= n <= 15
    assert [s["id"] for s in slides] == [f"D{i}" for i in range(1, n + 1)]


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

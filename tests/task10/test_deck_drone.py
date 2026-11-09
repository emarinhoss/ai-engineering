"""T10.11b: the drone deck builds from its outline as a 40-minute talk with dividers and backups,
every Source real or PENDING, every equation and figure placed, and the inlet deck covered."""
import re

import pytest
from pptx import Presentation

from docs.talk import build_deck_drone as bdd
from docs.talk import equations

ROOT = bdd.ROOT
INLET_OUTLINE = ROOT / "docs/talk/outline.md"


@pytest.fixture(scope="module")
def deck(tmp_path_factory):
    out = tmp_path_factory.mktemp("deck") / "deck_drone.pptx"
    n = bdd.build(out)
    prs = Presentation(str(out))
    by_id = {}
    for slide in prs.slides:          # a content slide footer reads "<id>  |  <n>"
        for sh in slide.shapes:
            m = sh.has_text_frame and re.fullmatch(r"(DB?\d+)  \|  \d+", sh.text_frame.text)
            if m:
                by_id[m.group(1)] = slide
    return n, prs, by_id


def text_of(slide):
    return " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)


def test_slide_count_follows_the_outline_with_one_divider_per_section(deck):
    n, prs, by_id = deck
    slides, sections = bdd.read_outline(), bdd.read_sections()
    dividers = [s for s in sections if s["title"] != "Title"]
    assert n == len(prs.slides) == len(slides) + len(dividers)
    assert set(by_id) == {s["id"] for s in slides}
    ids = [s["id"] for s in slides]
    assert len(set(ids)) == len(ids)
    main = [int(i[1:]) for i in ids if not i.startswith("DB")]
    backup = [int(i[2:]) for i in ids if i.startswith("DB")]
    assert main == list(range(1, len(main) + 1)) and backup == list(range(1, len(backup) + 1))
    assert [s["title"] for s in sections][-1] == "Backup" and len(backup) >= 15
    blue = [sl for sl in prs.slides if sl.background.fill.type == 1]          # solid divider fill
    assert len(blue) == len(dividers)


def test_timing_sums_to_40_and_matches_the_section_minutes():
    slides = {s["id"]: s for s in bdd.read_outline()}
    timed = [s for s in bdd.read_sections() if s["minutes"] is not None]
    assert sum(s["minutes"] for s in timed) == 40
    clock = 0.0
    for sec in timed:
        assert sum(slides[i]["minutes"] for i in sec["ids"]) == sec["minutes"], sec["title"]
        for i in sec["ids"]:
            m, sec_s = slides[i]["start"].split(":")
            assert int(m) * 60 + int(sec_s) == round(clock * 60), i
            clock += slides[i]["minutes"]
    assert clock == 40
    table = re.search(r"## Timing\n(.*?)\n---", bdd.OUTLINE.read_text(), re.DOTALL).group(1)
    rows = re.findall(r"^\| (?!Section|---)([^|]+)\| ([\d.]+) \|", table, re.MULTILINE)
    assert sum(float(m) for _, m in rows) == 40
    for s in bdd.read_outline():
        assert (s["minutes"] is None) == s["id"].startswith("DB"), s["id"]


def test_every_source_part_is_existing_files_or_pending_or_none():
    for s in bdd.read_outline():
        for part in bdd.source_parts(s["source"]):
            if part.startswith(("PENDING", "none")):
                continue
            paths = re.findall(r"`([^`]+)`", part)
            assert paths, f"{s['id']}: Source part names no file: {part}"
            for p in paths:
                assert (ROOT / p).is_file(), f"{s['id']}: {p} does not exist"


def test_notes_are_at_most_three_sentences_and_placeholders_resolve(deck):
    _, _, by_id = deck
    for s in bdd.read_outline():
        slide = by_id[s["id"]]
        notes = slide.notes_slide.notes_text_frame.text
        assert "{" not in notes and "}" not in notes, s["id"]
        assert len(re.findall(r"[.!?](?:\s|$)", notes)) <= 3, s["id"]
        assert "{" not in text_of(slide), s["id"]


PENDING_SLIDES = {"D24": None, "D33": bdd.MF, "D36": bdd.PARETO_HF, "D38": bdd.CONFIRM}


def test_pending_slides_say_pending_exactly_while_their_file_is_missing(deck):
    _, _, by_id = deck
    for sid, rel in PENDING_SLIDES.items():
        missing = bdd.viz_files() is None if rel is None else not bdd.exists(rel)
        assert ("PENDING" in text_of(by_id[sid])) == missing, sid
    assert ("PENDING" in text_of(by_id["D37"])) == (not bdd.exists(bdd.INVERSE_HF))


def test_numbers_come_from_the_records():
    v = bdd.values()
    assert v["n_fail"] == 0 and v["n_pending"] == 1 and v["v6e_tol"] == "5 %"
    assert v["pool_cases"] == 172 == sum(bdd.shard_split())
    assert v["front_n"] == bdd.jload("runs/drone_grid/2026-11-08/record.json")["front_size"]
    rec = bdd.jload(bdd.POOL + "/record.json")
    assert (v["pool_complete"], v["pool_designs"]) == (rec["complete"], rec["designs"])
    assert len(bdd.pool_complete()) == rec["complete"]
    assert v["inv_n_bound"] == sum(bdd.jload(bdd.INVERSE_LF)["design"][k] in b
                                   for k, b in bdd.DRONE_BOUNDS.items())
    assert v["n_tools"] == len(bdd.mcp_tools()) >= 10
    assert v["smoke_cl_off"].startswith("-") and v["smoke_cd_off"].startswith("+")


def test_signed_range_orders_both_negative_ranges():
    assert bdd.signed_range([-0.3, -0.1], "high", "low") == "10.0 to 30.0 % low"
    assert bdd.signed_range([0.1, 0.3], "high", "low") == "10.0 to 30.0 % high"
    assert bdd.signed_range([-0.1, 0.02], "high", "low") == "10.0 % low to 2.0 % high"


DRAWINGS = {"D2": "clean_exit.png", "D6": "c2_cap.png", "D9": None, "D10": "planform.png",
            "D11": "vlm_lattice.png", "D13": "closure_energy.png", "D14": "airfoil2d_mesh.png",
            "D26": "queue_gates.png", "D30": "design_space.png", "D39": "bias_sweep.png"}


def test_drawings_are_built_and_placed(deck):
    _, _, by_id = deck
    for sid, name in DRAWINGS.items():
        if name:
            assert (ROOT / bdd.FIG_DRONE / name).stat().st_size > 20_000, name
            assert any(sh.shape_type == 13 for sh in by_id[sid].shapes), f"{sid}: no picture"
    assert len([sh for sh in by_id["D9"].shapes if sh.shape_type == 1]) >= 9
    if not bdd.exists(bdd.MF):
        assert (ROOT / bdd.FIG_DRONE / "two_level.png").stat().st_size > 20_000


def test_drawing_numbers_come_from_the_code_and_records():
    v = bdd.values()
    _params, _, out, _ = bdd.nominal()
    assert v["nom_mtow"] == f"{out['mtow_kg']:.2f}" and v["nom_span"] == "2"
    assert v["mesh_cells"] == "21,760"
    assert 0 <= v["n_front_edge"] <= v["n_front"] == 15


def test_every_outline_equation_renders_sits_on_its_slide_and_is_indexed(deck, tmp_path,
                                                                         monkeypatch):
    _, _, by_id = deck
    monkeypatch.setattr(equations, "EQ_DIR", tmp_path)
    indexed = {latex for latex, _, _ in bdd.EQUATION_INDEX}
    n_equations = 0
    for s in bdd.read_outline():
        listed = s.get("equations", [])
        for latex in listed:
            path = equations.render(latex)
            assert path.is_file() and path.stat().st_size > 2000, f"{s['id']}: {latex}"
            assert latex in indexed, f"{s['id']}: not in the equations index: {latex}"
        placed = equations.placed_on(by_id[s["id"]])
        assert sorted(latex for latex, _ in placed) == sorted(listed), s["id"]
        n_equations += len(listed)
    assert n_equations >= 35
    for sid in ("D7", "D9", "D11", "D12", "D13", "D14", "D15", "D18", "D19", "D29", "D31", "D32",
                "D33", "D37"):
        assert next(s for s in bdd.read_outline() if s["id"] == sid).get("equations"), sid


FLOW_SLIDES = {"D20": "cp_e387.png", "D23": "cp_design0.png", "D21": "cf_e387.png",
               "D17": "cp_mesh_pair.png", "D16": "convergence_smoke2.png",
               "D22": "section_polars.png"}


def test_flow_figures_exist_and_sit_on_their_slides(deck):
    _, _, by_id = deck
    for sid, name in FLOW_SLIDES.items():
        assert (ROOT / bdd.FLOW / name).stat().st_size > 20_000, name
        pics = [sh for sh in by_id[sid].shapes if sh.shape_type == 13]
        assert len(pics) == 1, f"{sid}: expected one picture"
        assert name in text_of(by_id[sid]), f"{sid}: caption does not name {name}"


def test_contour_slide_names_both_viz_cases(deck):
    _, _, by_id = deck
    text = text_of(by_id["D24"])
    for case in bdd.VIZ_CASES:
        assert case in text
    if bdd.viz_files() is None:
        assert not any(sh.shape_type == 13 for sh in by_id["D24"].shapes)


def test_flow_numbers_come_from_the_surface_files():
    v = bdd.values()
    rows = bdd.case_by_alpha(bdd.pa.DESIGN0_CASES)
    cl = {a: r["metrics"]["cl"] for a, r, _ in rows}
    assert v["d0_cl14"] == f"{cl[14.0]:.3f}" and v["d0_cl10"] == f"{cl[10.0]:.3f}"
    assert float(v["d0_peak10"]) < float(v["d0_peak14"]) < 0.0
    assert v["conv_iters"] == 4867 and v["conv_budget"] == 6000
    assert v["n_designs"] >= 3 and v["n_stall"] >= 3


def coverage_rows():
    text = bdd.OUTLINE.read_text()
    table = text[text.index("## Coverage of the inlet deck"):]
    row = r"^\| ((?:S|B)\d+[a-z]?) \|[^|]*\| ([^|]+) \|$"
    return dict(re.findall(row, table, re.MULTILINE))


def test_coverage_table_maps_every_inlet_slide():
    inlet = re.findall(r"^### (S\d+[a-z]?|B\d+)\. ", INLET_OUTLINE.read_text(), re.MULTILINE)
    rows = coverage_rows()
    assert sorted(rows) == sorted(inlet)
    drone_ids = {s["id"] for s in bdd.read_outline()}
    for sid, target in rows.items():
        target = target.strip()
        if target.startswith("not applicable:"):
            assert len(target) > len("not applicable: ") + 10, sid
            continue
        named = re.findall(r"\b(DB?\d+)\b", target)
        assert named and set(named) <= drone_ids, f"{sid}: {target}"

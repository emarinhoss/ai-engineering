"""Version 2 of the drone deck: 25 main slides with no dividers, one Backup divider, the backups;
no repository paths, file names, module names, case ids or earlier-study words anywhere; one row
per gate; every placeholder filled; the time-saved numbers equal those recomputed here from the
records; PENDING exactly where a record is missing."""
import csv
import json
import re
from collections import defaultdict
from datetime import datetime

import numpy as np
import pytest
from pptx import Presentation

from docs.talk import build_deck as bd
from docs.talk import build_deck_drone_v2 as v2

ROOT = v2.ROOT
LABEL = re.compile(r"([VB]\d+)  \|  \d+")
PATH = re.compile(r"\b(runs|docs|analysis|drone|worker|mcp_server|designs|data|tests|postprocess"
                  r"|surrogate|physics)/")
FILENAME = re.compile(r"\b\w[\w.-]*\.(py|csv|json|yaml|md|pptx|gz)\b")
CASE_ID = re.compile(r"airfoil2d-[0-9a-f]{10}")
EARLIER = ("inlet", "ramp", "supersonic", "task 9", "carried over")


@pytest.fixture(scope="module")
def deck(tmp_path_factory):
    out = tmp_path_factory.mktemp("deck") / "deck_drone_v2.pptx"
    n = v2.build(out)
    prs = Presentation(str(out))
    order, by_id = [], {}
    for slide in prs.slides:
        label = next((m.group(1) for sh in slide.shapes if sh.has_text_frame
                      for m in [LABEL.fullmatch(sh.text_frame.text)] if m), None)
        order.append(label)
        if label:
            by_id[label] = slide
    return n, prs, order, by_id


def texts(slide):
    out = []
    for sh in slide.shapes:
        if sh.has_text_frame:
            out.append(sh.text_frame.text)
        if sh.has_table:
            out += [c.text for row in sh.table.rows for c in row.cells]
    if slide.has_notes_slide:
        out.append(slide.notes_slide.notes_text_frame.text)
    return out


def text_of(slide):
    return " ".join(texts(slide))


def test_main_body_then_one_backup_divider_then_backups(deck):
    n, prs, order, _ = deck
    main = [f"V{i}" for i in range(1, 26)]
    backup = [f"B{i}" for i in range(1, 30)]
    assert order == main + [None] + backup
    assert n == len(prs.slides) == 25 + 1 + 29
    divider = prs.slides[25]
    assert divider.background.fill.type == 1                      # solid blue fill
    assert divider.shapes.title.text_frame.text == "Backup"
    blue = [i for i, sl in enumerate(prs.slides) if sl.background.fill.type == 1]
    assert blue == [25]                                          # no divider inside the main body
    outline = v2.read_outline()
    assert [s["id"] for s in outline] == main + backup
    assert len([s for s in outline if s["id"].startswith("V")]) <= 25


def test_no_source_footer(deck, tmp_path):
    _, prs, _, _ = deck
    for slide in prs.slides:
        assert not any(t.strip().startswith(("sources:", "Figure:", "Record:")) for t in texts(slide))
    probe = bd.new_deck()
    slide = bd.start_slide(probe, 1, "V9", "t", "m", [], "n")
    assert not any("sources" in sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)


def test_no_paths_file_names_or_case_ids_on_slides_or_in_notes(deck):
    _, prs, order, _ = deck
    for label, slide in zip(order, prs.slides):
        for t in texts(slide):
            for rx in (PATH, FILENAME, CASE_ID, v2.MODULE_RE):
                assert not rx.search(t), f"{label}: {rx.search(t).group(0)!r} in {t!r}"


def test_no_mention_of_the_earlier_study(deck):
    _, prs, order, _ = deck
    for label, slide in zip(order, prs.slides):
        low = text_of(slide).lower()
        for word in EARLIER:
            assert word not in low, f"{label}: {word!r}"


def test_gates_table_has_one_row_per_gate(deck):
    _, _, _, by_id = deck
    table = next(sh.table for sh in by_id["V7"].shapes if sh.has_table)
    first = [row.cells[0].text for row in table.rows][1:]
    numbers = [int(m.group(1)) for t in first for m in [re.match(r"(\d)\. ", t)] if m]
    assert numbers == sorted(set(numbers)) == [1, 2, 3, 4, 5]
    code = sorted({int(g.split()[1]) for g in v2.v1.drone_gates()})
    assert numbers == code
    assert sum(t.startswith("4. ") for t in first) == 1
    gate4 = first[numbers.index(4)].lower()
    assert "wing loading" in gate4 and "manufacturing floor" in gate4
    assert any(t.startswith("Mesh quality") for t in first)
    assert len(first) == len(code) + 1
    assert text_of(by_id["V7"]).lower().count("gate 4") == 0


def test_every_placeholder_is_filled(deck):
    _, _, _, by_id = deck
    v = v2.values()
    assert v2.placeholders() <= set(v)
    for name in ("grid_hours", "su2_cases", "su2_worker_h", "pool_wall_h", "mf_n_match",
                 "confirm_v2_answer"):
        assert name in v
    for sid, slide in by_id.items():
        assert not re.search(r"\{\w+\}", text_of(slide)), sid


def su2_pool_records():
    out = []
    for f in sorted(ROOT.glob("runs/pool_af*/airfoil2d-*/result.json")):
        if not f.parent.name.endswith(".first_attempt"):
            out.append(json.loads(f.read_text()))
    return out


def test_time_saved_numbers_equal_the_records(deck):
    _, _, _, by_id = deck
    grid = json.loads((ROOT / "runs/drone_grid/2026-11-08/record.json").read_text())
    recs = su2_pool_records()
    start = min(datetime.fromisoformat(r["run"]["started_at"]) for r in recs)
    end = max(datetime.fromisoformat(r["run"]["finished_at"]) for r in recs)
    acc = defaultdict(list)
    with open(ROOT / "runs/drone_mf/2026-11-09/mf.csv", newline="") as f:
        for r in csv.DictReader(f):
            acc[(r["model"], int(r["n"]), r["metric"])].append(float(r["value"]))
    mean = {k: float(np.mean(x)) for k, x in acc.items()}
    target = mean[("two", 8, "rmse_endurance")]
    singles = sorted(n for (m, n, k) in mean if m == "single" and k == "rmse_endurance")
    match = next((n for n in singles if mean[("single", n, "rmse_endurance")] <= target), None)
    tasks = (ROOT / "docs/specs/task10_tasks.md").read_text().splitlines()
    want = {"grid_hours": f"{grid['wall_seconds'] / 3600:.1f}",
            "su2_cases": len(recs),
            "su2_worker_h": f"{sum(r['run']['wall_time_s'] for r in recs) / 3600:.1f}",
            "pool_wall_h": f"{(end - start).total_seconds() / 3600:.1f}",
            "mf_n_match": str(match) if match is not None else f"more than {singles[-1]}",
            "n_rulings": max(int(line.split()[2].rstrip(",:")) for line in tasks
                             if line.startswith("### Decision "))}
    v = v2.values()
    for k, val in want.items():
        assert v[k] == val, k
    text = text_of(by_id["V17"])
    for val in want.values():
        assert str(val) in text
    assert f"{grid['points_evaluated']:,}" in text


def test_pending_exactly_where_a_record_is_missing(deck):
    _, _, _, by_id = deck
    assert ("PENDING" in text_of(by_id["V19"])) == (not v2.v1.exists(v2.v1.PARETO_HF))
    missing = [not v2.v1.exists(p) for p in (v2.CONFIRM_30, v2.CONFIRM_32)]
    assert ("PENDING" in text_of(by_id["V21"])) == any(missing)
    v21 = text_of(by_id["V21"])
    assert "answer on 30 designs" in v21 and "answer on 32 designs" in v21
    if v2.v1.exists(v2.CONFIRM_30):
        c = json.loads((ROOT / v2.CONFIRM_30).read_text())
        assert f"{c['endurance_h']['simulated']:.3f}" in v21
        assert f"{c['mtow_kg']['simulated']:.3f}" in v21


def test_main_slides_have_body_text_of_at_least_12_pt(deck):
    _, _, _, by_id = deck
    for i in range(2, 26):
        sizes = v2.font_sizes(by_id[f"V{i}"])
        assert sizes and min(s for s, _ in sizes) >= 12, f"V{i}"


def test_figures_of_the_deck_are_drawn_in_its_own_folder(deck):
    _, _, _, by_id = deck
    for name in ("pipeline_v2.png", "timeline.png", "su2_vs_low.png", "queue_shards.png",
                 "viz_14.png"):
        assert (ROOT / v2.FIG_V2 / name).stat().st_size > 20_000, name
    for sid in ("V5", "V10", "V11", "V18", "V22"):
        assert any(sh.shape_type == 13 for sh in by_id[sid].shapes), sid


def test_figure_text_check_rejects_paths_and_case_ids():
    assert v2.violations("Record: runs/pool_af/x")
    assert v2.violations("case airfoil2d-0ae85f2779")
    assert v2.violations("see drone.naca")
    assert v2.violations("the Inlet study")
    assert not v2.violations("endurance 9.95 h, mass 2.963 kg")

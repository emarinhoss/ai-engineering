"""analysis.toy_active_learning: the numbers of the worked example, by independent arithmetic."""
import re

import pytest

from analysis import toy_active_learning as toy

RES, REF, FRONT = toy.compute()
FIGS = {"hypervolume": "toy/toy_hypervolume.png", "candidates": "toy/toy_candidates.png",
        "scores": "toy/toy_scores.png"}


def test_front_reference_point_and_hypervolume_by_hand():
    assert RES["run_front"] == ["A", "B", "C"]
    assert RES["dominated"] == {"D": "B", "E": "C"}
    assert RES["ref"] == pytest.approx({"endurance": 3.6, "mass": 2.98})
    # strips, best endurance first: (8 - 3.6)(2.98 - 2.4), (6 - 3.6)(2.4 - 1.6), (4 - 3.6)(1.6 - 1.0)
    by_hand = [4.4 * 0.58, 2.4 * 0.8, 0.4 * 0.6]
    assert [s["area"] for s in RES["strips"]] == pytest.approx(by_hand)
    assert RES["hv_run"] == pytest.approx(sum(by_hand)) and RES["hv_run"] == pytest.approx(4.712)


def test_true_front_regret_and_improvement_by_hand():
    assert RES["true_front"] == ["A", "B", "C", "F"]
    assert RES["hv_true"] == pytest.approx(4.4 * 0.58 + 3.4 * 0.6 + 2.4 * 0.2 + 0.4 * 0.6)   # 5.312
    assert RES["regret_now"] == pytest.approx(1 - 4.712 / 5.312)
    assert RES["hvi_F"] == pytest.approx(5.312 - 4.712) and RES["outcomes"]["F"]["regret"] == pytest.approx(0, abs=1e-12)


def test_three_strategies_choose_differently_and_only_one_helps():
    assert RES["picks"] == {"plain EHVI": "H", "maximum variance": "I", "EHVI times P(feasible)": "F"}
    out = RES["outcomes"]
    for wasted in ("G", "H", "I"):                       # dominated, gated and dominated designs add nothing
        assert out[wasted]["regret"] == pytest.approx(RES["regret_now"])
    assert RES["random_expected_regret"] == pytest.approx(RES["regret_now"] * 3 / 4)
    c = RES["candidates"]
    assert c["G"]["ehvi"] == 0.0 and c["H"]["ehvi"] > c["F"]["ehvi"] > c["I"]["ehvi"]
    assert c["F"]["ehvi_times_p"] > c["I"]["ehvi_times_p"] > c["H"]["ehvi_times_p"]
    assert c["F"]["ehvi_long"] == pytest.approx(c["F"]["ehvi"], rel=0.15)   # 128 draws are close to 20,000


def test_the_hand_estimate_is_the_mean_of_its_own_draws():
    h = RES["hand"]
    assert len(h["draws"]) == toy.HAND_DRAWS
    assert h["mean"] == pytest.approx(sum(d["hvi"] for d in h["draws"]) / toy.HAND_DRAWS)


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def prose(text):
    """The paragraph lines of the document: no table rows, headings, images or blank lines."""
    for line in text.splitlines():
        line = re.sub(r"^(\d+\.|-)\s+", "", line.strip())
        if line and not line.startswith(("|", "#", "!")):
            yield line


def test_document_is_current_and_follows_the_ste_limits(tmp_path):
    out = tmp_path / "doc.md"
    toy.write_document(RES, FIGS, out)
    text = out.read_text()
    assert text == toy.DOC.read_text()                     # the committed document is the generated one
    assert "{" not in text and "}" not in text
    for line in prose(text):
        sentences = SENTENCE.split(line)
        assert len(sentences) <= 6, line[:60]
        for s in sentences:
            assert len(s.split()) <= 25, s

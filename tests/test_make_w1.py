"""designs.make_w1 and designs.make_w1_control (tasks W1.8 and W1.2): the parts that need no Drive."""
import numpy as np

from analysis.w1_warmstart import reference_rows
from designs import make_w1, make_w1_control


def test_order_tags_and_cases_follow_the_rule():
    assert [s for _, s in make_w1.ORDER] == ["cold", "near", "learn", "learn", "near", "cold"]
    assert len({t for t, _ in make_w1.ORDER}) == 6
    assert set(make_w1.CASES) == {"d1_2", "d1_4", "d1_6", "d1_10", "d4_2", "d4_6", "d4_10"}
    refs = reference_rows()
    assert {"d1_2", "d1_4", "d1_6", "d1_10", "d4_2", "d4_6", "d4_10"} <= set(refs)


def test_nearest_scales_each_input_to_the_training_range():
    X = np.array([[0.0, 10.0, 5.0, 0.0], [6.0, 10.0, 5.0, 10.0], [3.0, 15.0, 5.5, 5.0]])
    assert make_w1.nearest(X, [0.5, 10.0, 5.0, 1.0]) == 0
    # 1 deg of angle (range 10) is further than 0.4 % of camber (range 6) after scaling
    assert make_w1.nearest(X, [5.6, 10.0, 5.0, 9.0]) == 1


def test_every_coarse_test_mesh_has_the_same_nodes_as_a_training_mesh():
    """The rule writes both warm starts node by node: this needs one node count for every section."""
    n = {name: len(make_w1.mesh_coords(make_w1.base(name))) for name in ("d1_6", "d4_2")}
    train = {**make_w1.base("d1_6"), **make_w1.sections()[0]}
    n["design0"] = len(make_w1.mesh_coords(train))
    assert len(set(n.values())) == 1, n


def test_control_case_is_e0_design_1_at_6_deg():
    p = make_w1_control.params("w1_control_raw.csv")
    assert p["alpha_deg"] == 6.0 and p["mesh_level"] == "coarse" and p["reynolds"] == 170203.9
    assert p["start_file"] == "w1_control_raw.csv"

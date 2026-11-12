"""designs.make_w1_field: the training set and references of experiment W1 (task W1.3)."""
from designs import make_w1_field as m


def test_plan_is_the_rules_training_set_and_references():
    rows = m.plan()
    field = [r for r in rows if r[1] == "w1_field"]
    refs = [r for r in rows if r[1] == "w1_ref"]
    assert len(field) == 120 and len(refs) == 3
    assert not {d for d, _, _ in field} & {1, 4}
    assert {d for d, _, _ in refs} == {4}
    assert all(p["save_restart"] and p["mesh_level"] == "coarse" and p["max_iter"] == 6000 for _, _, p in field)
    assert sorted({p["alpha_deg"] for _, _, p in field}) == [-2.0, 2.0, 6.0, 10.0]
    assert [p["alpha_deg"] for _, _, p in refs] == [2.0, 6.0, 10.0]
    assert all(p["max_iter"] == 20000 and p["cauchy_elems"] == 500 and p["cauchy_eps"] == 1e-7
               for _, _, p in refs)


def test_each_section_equals_its_pool_record():
    secs = m.sections()
    assert len(secs) == 32
    for d, _, p in m.plan():
        assert {k: p[k] for k in m.KEYS} == secs[d]
    assert secs[4]["reynolds"] == 108870.0 and secs[1]["reynolds"] == 170203.9

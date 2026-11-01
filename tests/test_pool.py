import csv

from designs import make_pool

CSV = make_pool.DEFAULT_OUT


def _rows(path=CSV):
    with open(path, newline="") as f:
        return [(int(r["index"]), float(r["theta1_deg"]), float(r["theta2_deg"]))
                for r in csv.DictReader(f)]


def test_96_unique_rows_inside_the_box():
    rows = _rows()
    assert [r[0] for r in rows] == list(range(96))
    assert len({(r[1], r[2]) for r in rows}) == 96
    assert all(5 <= t1 <= 12 and 5 <= t2 <= 14 for _, t1, t2 in rows)


def test_regeneration_is_identical(tmp_path):
    out = tmp_path / "again.csv"
    make_pool.write(out)
    assert out.read_text() == CSV.read_text()


def test_first_64_rows_are_balanced():
    counts = {}
    for _, t1, t2 in _rows()[:64]:
        key = (t1 > 8.5, t2 > 9.5)                       # midpoints of [5, 12] and [5, 14]
        counts[key] = counts.get(key, 0) + 1
    assert counts == {(False, False): 16, (False, True): 16, (True, False): 16, (True, True): 16}

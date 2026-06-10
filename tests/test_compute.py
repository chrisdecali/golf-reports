import pytest

import gen_combined as gc


def test_compute_selects_newest_round_by_default(store):
    d = gc.compute(store)
    assert d["round_id"] == "r2"
    assert d["course"] == "Wind Rose GC"
    assert d["score"] == 10
    assert d["putts"] == 5
    assert d["sg"]["total"] == -3.0
    assert d["sg"]["putting"] is None          # empty cell -> None
    assert len(d["holes"]) == 2


def test_compute_selects_round_by_id(store):
    d = gc.compute(store, "r1")
    assert d["round_id"] == "r1"
    assert d["score"] == 9


def test_compute_raises_on_unknown_round(store):
    with pytest.raises(SystemExit):
        gc.compute(store, "no_such_round")

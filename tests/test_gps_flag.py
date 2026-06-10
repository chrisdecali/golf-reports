import importlib

import pull_arccos


def test_gps_cols_excluded_by_default(monkeypatch):
    monkeypatch.delenv("GOLF_INCLUDE_GPS", raising=False)
    importlib.reload(pull_arccos)
    cols = pull_arccos.public_cols(pull_arccos.SHOT_COLS)
    assert "start_lat" not in cols and "end_lng" not in cols
    hcols = pull_arccos.public_cols(pull_arccos.HOLE_COLS)
    assert "pin_lat" not in hcols and "pin_lng" not in hcols


def test_gps_cols_included_with_env(monkeypatch):
    monkeypatch.setenv("GOLF_INCLUDE_GPS", "1")
    importlib.reload(pull_arccos)
    assert "start_lat" in pull_arccos.public_cols(pull_arccos.SHOT_COLS)
    # reset module state for other tests
    monkeypatch.delenv("GOLF_INCLUDE_GPS")
    importlib.reload(pull_arccos)

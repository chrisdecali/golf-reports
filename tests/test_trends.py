import trends


def test_history_merges_three_sources(store):
    rows = trends.history(store)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)                      # oldest first
    # 6 x 18B + 3 GHIN + 2 arccos, minus dedupes:
    # 2026-06-01 18B b6 == GHIN g2 (windrose) -> one row (18B wins over GHIN)
    # 2026-06-08 arccos r2 == GHIN g3 (windrose) -> one row (arccos wins)
    # 2026-05-02 18B b5 (windrose) vs 2026-05-03 GHIN g1 (forest): different -> keep both
    assert len(rows) == 9
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-06-08"]["source"] == "arccos"
    assert by_date["2026-06-08"]["differential"] == 23.1   # attached from GHIN
    assert by_date["2026-06-01"]["source"] in ("18birdies", "arccos")
    win_61 = [r for r in rows if r["date"] == "2026-06-01"]
    assert any(r["differential"] == 21.3 for r in win_61)  # GHIN diff survived


def test_history_tolerates_missing_files(store, tmp_path):
    import os, shutil
    partial = str(tmp_path / "partial")
    os.makedirs(partial)
    shutil.copy(os.path.join(store, "ghin_scores.csv"), partial)
    rows = trends.history(partial)
    assert len(rows) == 3 and all(r["source"] == "ghin" for r in rows)


def test_normalize_course():
    n = trends._norm_course
    assert n("WindRose Golf Club") == n("Wind Rose GC") == "windrose"
    assert n("Forest") == n("Forest Golf Course")

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

    # 2026-06-08: single row, arccos wins, GHIN differential attached
    rows_0608 = [r for r in rows if r["date"] == "2026-06-08"]
    assert len(rows_0608) == 1
    assert rows_0608[0]["source"] == "arccos"
    assert rows_0608[0]["differential"] == 23.1

    # 2026-06-01: two rows remain (arccos r1 + the 18birdies/GHIN merge)
    # Arccos r1 is a different course so it does NOT collide with the WindRose merge.
    rows_0601 = [r for r in rows if r["date"] == "2026-06-01"]
    sources_0601 = {r["source"] for r in rows_0601}
    assert sources_0601 == {"arccos", "18birdies"}
    # The 18birdies row (which won over GHIN) carries the GHIN differential
    b6_row = [r for r in rows_0601 if r["source"] == "18birdies"][0]
    assert b6_row["differential"] == 21.3


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


def test_whs_index_small_counts():
    # 3 diffs -> lowest 1, -2.0
    assert trends._whs_index([20.0, 25.0, 30.0]) == 18.0
    # 6 diffs -> avg lowest 2, -1.0
    assert trends._whs_index([18.0, 20.0, 25.0, 26.0, 27.0, 28.0]) == 18.0
    # <3 -> None
    assert trends._whs_index([20.0, 21.0]) is None


def test_whs_index_full_twenty():
    diffs = [float(d) for d in range(10, 30)]   # 10..29, lowest 8 = 10..17
    assert trends._whs_index(diffs) == 13.5
    # only most-recent 20 count: prepend an ancient great score, list ordered oldest->newest
    assert trends._whs_index([1.0] + diffs) == 13.5


def test_trends_blocks(store):
    t = trends.trends(store)
    assert t["scoring"]["n"] == 8                     # 9 rows minus one 9-holer
    assert t["handicap"]["index"] is not None
    assert t["sg_trends"] is not None                 # fixture has 2 arccos rounds
    assert t["sg_trends"]["n"] == 2
    assert t["rounds_total"] == 9


def test_compare_rounds(store):
    c = trends.compare_rounds(store, "r1", "r2")
    assert c["sg_delta"]["total"] == -0.9             # r2 -3.0 vs r1 -2.1
    assert c["biggest_swing"]["category"] in ("off_tee", "approach", "short", "putting")


def test_trajectory_and_projection(store, tmp_path):
    import csv as _csv
    import os, shutil
    s = str(tmp_path / "s")
    shutil.copytree(store, s)
    # Append 3 GHIN scores with differentials: fixture already has 3 (g1,g2,g3)
    # -> total 6 differentials after append.
    with open(os.path.join(s, "ghin_scores.csv"), "a", newline="") as f:
        w = _csv.writer(f)
        for i, diff in enumerate(("24.0", "20.0", "19.0")):
            w.writerow([f"2026-06-{20 + i:02d}", "WindRose Golf Club", "18", "95",
                        "72.1", "127", diff, f"gx{i}"])
    t = trends.trends(s)
    h = t["handicap"]
    assert h["n_differentials"] == 6
    # WHS table needs >=3 diffs for a non-None index; first 2 diffs silently produce no point.
    assert len(h["trajectory"]) == 4
    # index must equal recomputed value from the same helper
    diffs = [r["differential"] for r in trends.history(s) if r["differential"] is not None]
    assert h["index"] == trends._whs_index(diffs)
    assert h["projected_index"] is not None

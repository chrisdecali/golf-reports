"""Shared fixtures: a tiny synthetic store dir that compute() can read."""
import csv
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "render"))
sys.path.insert(0, os.path.join(REPO, "ingest"))
sys.path.insert(0, os.path.join(REPO, "mcp"))


def _write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def store(tmp_path):
    """Two rounds, two holes each. Round r2 is newest (last row).
    Round r2 hole 2 has score_to_par=None (the R2 crash case).
    Course name of r1 is hostile (the S3 XSS case)."""
    s = str(tmp_path / "store")
    os.makedirs(s)

    # Subset of ROUND_COLS (pull_arccos.py) — only columns compute() currently reads. Add here if compute() grows.
    round_cols = ["round_id", "date", "course", "tee_name", "tee_yards", "slope",
                  "rating", "holes", "score", "par", "score_to_par", "putts",
                  "gir_hits", "gir_pct", "fairway_pct", "scramble_pct",
                  "sg_total_arccos", "sg_off_tee_arccos", "sg_approach_arccos",
                  "sg_short_arccos", "sg_putting_arccos"]
    _write_csv(os.path.join(s, "rounds_summary.csv"), round_cols, [
        {"round_id": "r1", "date": "2026-06-01",
         "course": '<img src=x onerror=alert(1)>', "tee_name": "Blue",
         "tee_yards": "6400", "holes": "18", "score": "9", "par": "8",
         "score_to_par": "1", "putts": "4", "gir_pct": "50.0",
         "fairway_pct": "100.0", "scramble_pct": "0.0",
         "sg_total_arccos": "-2.1", "sg_off_tee_arccos": "-0.5",
         "sg_approach_arccos": "-1.0", "sg_short_arccos": "-0.3",
         "sg_putting_arccos": "-0.3"},
        {"round_id": "r2", "date": "2026-06-08", "course": "Wind Rose GC",
         "tee_name": "Blue", "tee_yards": "6400", "holes": "18", "score": "10",
         "par": "8", "score_to_par": "", "putts": "5", "gir_pct": "0.0",
         "fairway_pct": "50.0", "scramble_pct": "50.0",
         "sg_total_arccos": "-3.0", "sg_off_tee_arccos": "-1.0",
         "sg_approach_arccos": "-1.5", "sg_short_arccos": "-0.5",
         "sg_putting_arccos": "",
        },
    ])

    hole_cols = ["round_id", "date", "course", "hole_id", "par", "shots",
                 "score_to_par", "putts", "gir", "fairway_hit", "hole_len_yd",
                 "approach_proximity_yd", "pin_lat", "pin_lng",
                 "scramble_chance", "scramble_save", "sg_hole_broadie"]
    _write_csv(os.path.join(s, "holes.csv"), hole_cols, [
        {"round_id": "r1", "hole_id": "1", "par": "4", "shots": "4",
         "score_to_par": "0", "putts": "2", "gir": "1", "fairway_hit": "1",
         "hole_len_yd": "380", "sg_hole_broadie": "-0.2"},
        {"round_id": "r1", "hole_id": "2", "par": "4", "shots": "5",
         "score_to_par": "1", "putts": "2", "gir": "0", "fairway_hit": "1",
         "hole_len_yd": "410", "sg_hole_broadie": "-1.1"},
        {"round_id": "r2", "hole_id": "1", "par": "4", "shots": "5",
         "score_to_par": "1", "putts": "3", "gir": "0", "fairway_hit": "0",
         "hole_len_yd": "380", "sg_hole_broadie": "-1.4"},
        {"round_id": "r2", "hole_id": "2", "par": "4", "shots": "5",
         "score_to_par": "", "putts": "2", "gir": "0", "fairway_hit": "1",
         "hole_len_yd": "410", "sg_hole_broadie": ""},
    ])

    shot_cols = ["round_id", "date", "hole_id", "shot_num", "club",
                 "club_category", "shot_distance_yd", "start_dist_to_pin_yd",
                 "end_dist_to_pin_yd", "start_lat", "start_lng", "end_lat",
                 "end_lng", "lie_approx", "is_tee", "is_putt", "penalties",
                 "category_approx", "sg_shot_approx"]
    _write_csv(os.path.join(s, "shots.csv"), shot_cols, [
        {"round_id": "r2", "hole_id": "1", "shot_num": "1", "club": "Driver",
         "club_category": "driver", "start_dist_to_pin_yd": "380",
         "end_dist_to_pin_yd": "140", "lie_approx": "tee", "is_tee": "1",
         "is_putt": "0", "category_approx": "off_tee", "sg_shot_approx": "-0.3"},
        {"round_id": "r2", "hole_id": "1", "shot_num": "2", "club": "7 Iron",
         "club_category": "iron", "start_dist_to_pin_yd": "140",
         "end_dist_to_pin_yd": "12", "lie_approx": "fairway", "is_tee": "0",
         "is_putt": "0", "category_approx": "approach", "sg_shot_approx": "-0.4"},
        {"round_id": "r2", "hole_id": "1", "shot_num": "3", "club": "Putter",
         "club_category": "putter", "start_dist_to_pin_yd": "12",
         "end_dist_to_pin_yd": "1", "lie_approx": "green", "is_tee": "0",
         "is_putt": "1", "category_approx": "putting", "sg_shot_approx": "-0.5"},
        {"round_id": "r2", "hole_id": "1", "shot_num": "4", "club": "Putter",
         "club_category": "putter", "start_dist_to_pin_yd": "1",
         "end_dist_to_pin_yd": "0", "lie_approx": "green", "is_tee": "0",
         "is_putt": "1", "category_approx": "putting", "sg_shot_approx": "0.1"},
    ])

    _write_csv(os.path.join(s, "clubs.csv"),
               ["club", "club_category", "smart_distance_yd", "usage_count"],
               [{"club": "Driver", "club_category": "driver",
                 "smart_distance_yd": "240", "usage_count": "20"}])

    # 18Birdies history: 6 rounds over 3 months; 2026-06-01 Wind Rose overlaps
    # Arccos r1 (dedupe case). No rating/slope -> excluded from index math.
    _write_csv(os.path.join(s, "18birdies_rounds.csv"),
               ["date", "course", "holes", "gross", "to_par", "fairways_hit",
                "fairway_chances", "fairway_pct", "gir", "gir_chances",
                "gir_pct", "putts", "round_id"], [
        {"date": "2026-03-07", "course": "Forest Golf Course", "holes": "18",
         "gross": "103", "to_par": "31", "putts": "38", "gir": "2",
         "gir_chances": "18", "gir_pct": "11.1", "round_id": "b1"},
        {"date": "2026-03-21", "course": "Forest Golf Course", "holes": "18",
         "gross": "99", "to_par": "27", "putts": "36", "round_id": "b2"},
        {"date": "2026-04-04", "course": "WindRose Golf Club", "holes": "18",
         "gross": "101", "to_par": "29", "putts": "35", "round_id": "b3"},
        {"date": "2026-04-18", "course": "Forest Golf Course", "holes": "9",
         "gross": "49", "to_par": "13", "round_id": "b4"},
        {"date": "2026-05-02", "course": "WindRose Golf Club", "holes": "18",
         "gross": "97", "to_par": "25", "putts": "34", "round_id": "b5"},
        {"date": "2026-06-01", "course": "Wind Rose Golf Club", "holes": "18",
         "gross": "95", "to_par": "23", "putts": "33", "round_id": "b6"},
    ])

    # GHIN: 3 scores; 2026-06-01 WindRose overlaps BOTH Arccos r1 and 18B b6
    # (richest source must win, differential must survive the merge).
    _write_csv(os.path.join(s, "ghin_scores.csv"),
               ["played_at", "course_name", "holes", "adjusted_gross_score",
                "course_rating", "slope_rating", "differential", "score_id"], [
        {"played_at": "2026-05-03", "course_name": "Forest", "holes": "18",
         "adjusted_gross_score": "101", "course_rating": "73.6",
         "slope_rating": "137", "differential": "22.6", "score_id": "g1"},
        {"played_at": "2026-06-01", "course_name": "WindRose Golf Club",
         "holes": "18", "adjusted_gross_score": "96", "course_rating": "72.1",
         "slope_rating": "127", "differential": "21.3", "score_id": "g2"},
        {"played_at": "2026-06-08", "course_name": "WindRose Golf Club",
         "holes": "18", "adjusted_gross_score": "98", "course_rating": "72.1",
         "slope_rating": "127", "differential": "23.1", "score_id": "g3"},
    ])
    return s

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
         "tee_yards": "6400", "holes": "2", "score": "9", "par": "8",
         "score_to_par": "1", "putts": "4", "gir_pct": "50.0",
         "fairway_pct": "100.0", "scramble_pct": "0.0",
         "sg_total_arccos": "-2.1", "sg_off_tee_arccos": "-0.5",
         "sg_approach_arccos": "-1.0", "sg_short_arccos": "-0.3",
         "sg_putting_arccos": "-0.3"},
        {"round_id": "r2", "date": "2026-06-08", "course": "Wind Rose GC",
         "tee_name": "Blue", "tee_yards": "6400", "holes": "2", "score": "10",
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
    return s

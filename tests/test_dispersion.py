import json
import math
import os

import dispersion


def test_prior_only_when_no_shots(store, tmp_path):
    import shutil
    bare = str(tmp_path / "bare")
    os.makedirs(bare)
    shutil.copy(os.path.join(store, "clubs.csv"), bare)
    d = dispersion.build(bare)
    drv = next(c for c in d["clubs"] if c["club"] == "Driver")
    assert drv["total_yd"]["n"] == 0
    assert drv["total_yd"]["source_weight"] == 0.0
    assert drv["total_yd"]["mean"] == 240.0            # clubs.csv smart distance
    assert drv["total_yd"]["sd"] == round(240 * 0.055, 1)
    assert drv["confidence"] == "low"


def test_shrinkage_converges_to_sample(store, tmp_path, monkeypatch):
    # synthetic: 60 identical 7i shots at 150yd -> mean ~ (60*150 + 15*prior)/(75)
    import csv as _csv
    import shutil
    s2 = str(tmp_path / "s2")
    shutil.copytree(store, s2)
    with open(os.path.join(s2, "shots.csv"), "a", newline="") as f:
        w = _csv.writer(f)
        for i in range(60):
            w.writerow(["rX", "2026-06-09", "1", str(i + 1), "7 Iron", "iron",
                        "150", "160", "10", "", "", "", "", "fairway", "0",
                        "0", "0", "approach", "0"])
    d = dispersion.build(s2)
    seven = next(c for c in d["clubs"] if c["club"] == "7 Iron")
    assert seven["total_yd"]["n"] >= 60
    assert seven["total_yd"]["source_weight"] > 0.75
    assert abs(seven["total_yd"]["mean"] - 150) < 5    # data dominates
    assert seven["confidence"] == "high"


def test_lateral_geometry():
    # start at origin-ish, pin due north 200yd, shot ends 20yd east of the line
    # 1 deg lat ~ 121,000 yd ; use small offsets
    start = (40.0, -75.0)
    pin = (40.0 + 200 / 121000.0, -75.0)
    end = (40.0 + 100 / 121000.0, -75.0 + 20 / (121000.0 * math.cos(math.radians(40.0))))
    lat = dispersion._lateral_yd(start, end, pin)
    assert abs(lat - 20.0) < 1.0


def test_lateral_filter_tee_approach_only(store, tmp_path):
    """Shots with category_approx not in (off_tee, approach) must not feed laterals."""
    import csv as _csv
    import shutil
    s = str(tmp_path / "s")
    shutil.copytree(store, s)

    # Patch hole (r2, 1) with real pin coords so lateral computation is possible.
    # Write a fresh holes.csv with pin coords on that hole.
    hole_cols = ["round_id", "date", "course", "hole_id", "par", "shots",
                 "score_to_par", "putts", "gir", "fairway_hit", "hole_len_yd",
                 "approach_proximity_yd", "pin_lat", "pin_lng",
                 "scramble_chance", "scramble_save", "sg_hole_broadie"]
    pin_lat = 40.0 + 200 / 121000.0
    pin_lng = -75.0
    with open(os.path.join(s, "holes.csv"), "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=hole_cols, extrasaction="ignore")
        w.writeheader()
        w.writerow({"round_id": "r2", "hole_id": "1", "par": "4", "shots": "5",
                    "score_to_par": "1", "putts": "3", "gir": "0",
                    "fairway_hit": "0", "hole_len_yd": "380",
                    "pin_lat": str(pin_lat), "pin_lng": str(pin_lng)})

    # GPS coords: start at (40.0, -75.0), end 20yd east off the line
    cos_lat = math.cos(math.radians(40.0))
    start_lat, start_lng = 40.0, -75.0
    end_lat = 40.0 + 100 / 121000.0
    end_lng = -75.0 + 20 / (121000.0 * cos_lat)

    with open(os.path.join(s, "shots.csv"), "a", newline="") as f:
        w = _csv.writer(f)
        # short_game shot — must be excluded from lateral (wrong category)
        w.writerow(["r2", "2026-06-08", "1", "5", "Wedge", "wedge",
                    "30", "30", "5",
                    str(start_lat), str(start_lng), str(end_lat), str(end_lng),
                    "fairway", "0", "0", "0", "short_game", "0"])
        # approach shot — must be included
        w.writerow(["r2", "2026-06-08", "1", "6", "Wedge", "wedge",
                    "120", "120", "8",
                    str(start_lat), str(start_lng), str(end_lat), str(end_lng),
                    "fairway", "0", "0", "0", "approach", "0"])

    d = dispersion.build(s)
    wedge = next(c for c in d["clubs"] if c["club"] == "Wedge")
    assert wedge["lateral_yd"]["n"] == 1   # only the approach shot counted


def test_empty_club_name_in_clubs_csv_ignored(store, tmp_path):
    import shutil
    s = str(tmp_path / "s")
    shutil.copytree(store, s)
    # append a row with empty club name — should not appear in output
    with open(os.path.join(s, "clubs.csv"), "a", newline="") as f:
        f.write(",iron,150,5\n")
    d = dispersion.build(s)
    names = [c["club"] for c in d["clubs"]]
    assert "" not in names and None not in names


def test_schema_and_atomic_write(store):
    path = dispersion.write(store)
    assert os.path.basename(path) == "dispersion.json"
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    assert d["schema_version"] == "1.0"
    assert {"club", "category", "total_yd", "lateral_yd", "usage_count",
            "confidence"} <= set(d["clubs"][0].keys())
    assert {"mean", "sd", "n", "source_weight"} <= set(d["clubs"][0]["total_yd"].keys())

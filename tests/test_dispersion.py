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
    assert drv["carry_yd"]["n"] == 0
    assert drv["carry_yd"]["source_weight"] == 0.0
    assert drv["carry_yd"]["mean"] == 240.0            # clubs.csv smart distance
    assert drv["carry_yd"]["sd"] == round(240 * 0.055, 1)
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
    assert seven["carry_yd"]["n"] >= 60
    assert seven["carry_yd"]["source_weight"] > 0.75
    assert abs(seven["carry_yd"]["mean"] - 150) < 5    # data dominates
    assert seven["confidence"] == "high"


def test_lateral_geometry():
    # start at origin-ish, pin due north 200yd, shot ends 20yd east of the line
    # 1 deg lat ~ 121,000 yd ; use small offsets
    start = (40.0, -75.0)
    pin = (40.0 + 200 / 121000.0, -75.0)
    end = (40.0 + 100 / 121000.0, -75.0 + 20 / (121000.0 * math.cos(math.radians(40.0))))
    lat = dispersion._lateral_yd(start, end, pin)
    assert abs(lat - 20.0) < 1.0


def test_schema_and_atomic_write(store):
    path = dispersion.write(store)
    assert os.path.basename(path) == "dispersion.json"
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    assert d["schema_version"] == "1.0"
    assert {"club", "category", "carry_yd", "lateral_yd", "usage_count",
            "confidence"} <= set(d["clubs"][0].keys())
    assert {"mean", "sd", "n", "source_weight"} <= set(d["clubs"][0]["carry_yd"].keys())

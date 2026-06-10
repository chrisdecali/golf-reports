import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))

import post_round_alert as pra


def test_first_run_baselines_without_alerting(store):
    new = pra.detect_new(store)
    assert new == []                          # first run: baseline only, no spam
    with open(os.path.join(store, "_alerted.json"), encoding="utf-8") as fh:
        seen = json.load(fh)
    assert set(seen) == {"r1", "r2"}


def test_detects_only_new_rounds(store):
    pra.detect_new(store)                     # baseline
    # simulate a new round appearing
    with open(os.path.join(store, "rounds_summary.csv"), "a", newline="") as f:
        f.write("r3,2026-06-10,Wind Rose GC,Blue,6400,,,2,9,8,1,4,,50.0,100.0,0.0,-1.0,-0.2,-0.4,-0.2,-0.2\n")
    assert pra.detect_new(store) == ["r3"]
    assert pra.detect_new(store) == []        # idempotent: r3 recorded


def test_build_message_contains_essentials(store):
    msg = pra.build_message(store, "r2")
    assert "Wind Rose GC" in msg and "10" in msg
    assert "SG" in msg

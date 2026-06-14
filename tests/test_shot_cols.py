"""Tests for shot elevation and half-swing columns in SHOT_COLS.

Verifies that start_alt, end_alt, and is_half_swing are present in SHOT_COLS
and are populated correctly by build_round(). These are always-on (non-GPS):
altitude is terrain elevation, not a locating coordinate; is_half_swing is a
swing type flag — neither gates on GOLF_INCLUDE_GPS.
"""
import pull_arccos


def test_altitude_and_half_swing_in_shot_cols():
    assert "start_alt" in pull_arccos.SHOT_COLS
    assert "end_alt" in pull_arccos.SHOT_COLS
    assert "is_half_swing" in pull_arccos.SHOT_COLS


def test_new_cols_not_gps_gated():
    """start_alt, end_alt, is_half_swing must appear in public_cols even
    without GOLF_INCLUDE_GPS — they are not location coordinates."""
    import importlib
    import os
    # ensure GPS is off
    os.environ.pop("GOLF_INCLUDE_GPS", None)
    importlib.reload(pull_arccos)
    cols = pull_arccos.public_cols(pull_arccos.SHOT_COLS)
    assert "start_alt" in cols
    assert "end_alt" in cols
    assert "is_half_swing" in cols


def _minimal_shot(clubtype=1, start_alt=None, end_alt=None, is_half_swing=False):
    """Return a synthetic shot dict shaped like the Arccos API response."""
    return {
        "clubType": clubtype,
        "startLat": None, "startLong": None,
        "endLat": None, "endLong": None,
        "startAltitude": start_alt,
        "endAltitude": end_alt,
        "isHalfSwing": is_half_swing,
        "noOfPenalties": 0,
        "isSandUser": "F",
    }


def _minimal_hole(shots):
    return {
        "holeId": "h1",
        "shouldIgnore": "F",
        "shots": shots,
        "putts": 1,
        "isGir": "F",
        "isFairWay": "F",
        "isSandSaveChance": "F",
        "isSandSave": "F",
        "pinLat": None,
        "pinLong": None,
    }


def _minimal_summary(rid="r1"):
    return {
        "roundId": rid,
        "startTime": "2026-06-08T12:00:00.000Z",
        "courseName": "Test Course",
        "par": 18,
        "courseId": "c1",
        "teeId": "t1",
        "scoreOverride": 4,
        "overUnder": 0,
    }


def _minimal_detail(holes):
    return {
        "holes": holes,
        "courseName": "Test Course",
        "par": 18,
    }


def test_build_round_populates_alt_and_half_swing():
    """build_round() should carry startAltitude/endAltitude/isHalfSwing into shot rows."""
    s1 = _minimal_shot(clubtype=1, start_alt=125.5, end_alt=123.0, is_half_swing=False)
    s2 = _minimal_shot(clubtype=12, start_alt=None, end_alt=None, is_half_swing=True)
    hole = _minimal_hole([s1, s2])
    summary = _minimal_summary()
    detail = _minimal_detail([hole])

    _, _, shot_rows = pull_arccos.build_round(
        summary, detail, tee={}, hcp={}, clubid_map={},
        rdash={}, pulled_at="2026-06-14",
    )

    assert len(shot_rows) == 2
    r0 = shot_rows[0]
    assert r0["start_alt"] == 125.5
    assert r0["end_alt"] == 123.0
    assert r0["is_half_swing"] == 0

    r1 = shot_rows[1]
    assert r1["start_alt"] is None
    assert r1["end_alt"] is None
    assert r1["is_half_swing"] == 1


def test_build_round_absent_alt_fields_none():
    """Shots with no altitude keys at all should produce None, not KeyError."""
    s = {"clubType": 1, "noOfPenalties": 0}
    hole = _minimal_hole([s])
    _, _, shot_rows = pull_arccos.build_round(
        _minimal_summary(), _minimal_detail([hole]),
        tee={}, hcp={}, clubid_map={}, rdash={}, pulled_at="2026-06-14",
    )
    assert shot_rows[0]["start_alt"] is None
    assert shot_rows[0]["end_alt"] is None
    assert shot_rows[0]["is_half_swing"] == 0

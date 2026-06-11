"""Pins the Arccos clubType enum to the owner-confirmed mapping (2026-06-11).

Ground truth: the Arccos app's display of the real bag (irons 5-PW, wedges
50/54/58, putter). The community arccos-export enum (5=3i .. 12=PW) is off by
one for the current API — these assertions prevent regressing to it.
"""
import pull_arccos as pa


def test_iron_block_confirmed_against_app():
    assert pa.CLUBTYPE[6] == "5 Iron"
    assert pa.CLUBTYPE[11] == "Pitching Wedge"
    assert pa.CLUBTYPE[12] == "Putter"          # NOT "9 Iron"/"PW" (old enum)


def test_wedge_lofts_confirmed_against_bag():
    assert pa.CLUBTYPE[44] == "50 Wedge"
    assert pa.CLUBTYPE[42] == "54 Wedge"
    assert pa.CLUBTYPE[45] == "58 Wedge"


def test_club_category_handles_new_names():
    assert pa.club_category("Pitching Wedge") == "Wedge"
    assert pa.club_category("50 Wedge") == "Wedge"
    assert pa.club_category("5 Iron") == "Iron"
    assert pa.club_category("Putter") == "Putter"

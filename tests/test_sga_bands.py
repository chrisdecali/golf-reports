"""Tests for extract_sga_bands() — offline, no network.

The fixture dashboard.json is a trimmed synthetic representation of the
getDashboardAnalysis response. Tests verify: correct metrics appear in the
long-format output, slab/sga/shots_count parse correctly, missing sections
are skipped without crashing, and empty caddieInsights are tolerated.
"""
import json
import os

import pull_arccos


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def test_expected_metrics_present():
    dash = _load_fixture("dashboard.json")
    rows = pull_arccos.extract_sga_bands(dash)
    metrics = {r["metric"] for r in rows}
    assert "chip_by_pin_distance" in metrics
    assert "approach_by_pin_distance" in metrics
    assert "putting_by_length" in metrics
    assert "approach_by_terrain" in metrics


def test_chip_by_pin_distance_values():
    dash = _load_fixture("dashboard.json")
    rows = pull_arccos.extract_sga_bands(dash)
    chip_rows = [r for r in rows if r["metric"] == "chip_by_pin_distance"]
    assert len(chip_rows) == 2
    # First band: 0-20 Yards, sga=-0.2, 5 shots
    first = next(r for r in chip_rows if r["slab"] == "0-20")
    assert first["section"] == "short"
    assert first["sga"] == -0.2
    assert first["shots_count"] == 5
    assert first["slab_unit"] is None or first["slab_unit"] == "Yards"


def test_approach_by_pin_distance_values():
    dash = _load_fixture("dashboard.json")
    rows = pull_arccos.extract_sga_bands(dash)
    app_rows = [r for r in rows if r["metric"] == "approach_by_pin_distance"]
    assert len(app_rows) == 2
    r50 = next(r for r in app_rows if r["slab"] == "50-100")
    assert r50["section"] == "approach"
    assert r50["sga"] == -0.5
    assert r50["shots_count"] == 8


def test_putting_by_length_values():
    dash = _load_fixture("dashboard.json")
    rows = pull_arccos.extract_sga_bands(dash)
    putt_rows = [r for r in rows if r["metric"] == "putting_by_length"]
    assert len(putt_rows) == 3
    short = next(r for r in putt_rows if r["slab"] == "0-5")
    assert short["sga"] == 0.1
    assert short["shots_count"] == 20


def test_approach_by_terrain_values():
    dash = _load_fixture("dashboard.json")
    rows = pull_arccos.extract_sga_bands(dash)
    terrain_rows = [r for r in rows if r["metric"] == "approach_by_terrain"]
    assert len(terrain_rows) == 3
    terrains = {r["terrain"] for r in terrain_rows}
    assert "fairway" in terrains
    assert "rough" in terrains


def test_caddie_insights_present():
    dash = _load_fixture("dashboard.json")
    rows = pull_arccos.extract_sga_bands(dash)
    helping = [r for r in rows if r["metric"] == "caddie_helping"]
    hurting = [r for r in rows if r["metric"] == "caddie_hurting"]
    assert len(helping) == 1
    assert len(hurting) == 1
    assert hurting[0]["terrain"] == "rough"
    assert hurting[0]["extra"] == "Approach from rough"


def test_missing_sections_do_not_crash():
    """Dashboard with only driving section — no approach/short/putting."""
    partial = {
        "driving": {
            "distanceVsAccuracy": {"sgDistance": 0.1, "sgAccuracy": -0.2, "sgPenalties": 0.0},
            "drivingByHoleLength": [],
        }
    }
    rows = pull_arccos.extract_sga_bands(partial)
    metrics = {r["metric"] for r in rows}
    assert "sg_distance" in metrics
    # No crash, no approach/chip/putting metrics
    assert "chip_by_pin_distance" not in metrics
    assert "putting_by_length" not in metrics


def test_empty_caddie_insights_tolerated():
    """Few rounds: caddieInsights.helping/hurting may be empty lists."""
    dash = _load_fixture("dashboard.json")
    import copy
    dash2 = copy.deepcopy(dash)
    dash2["overall"]["overallSection"]["caddieInsights"] = {"helping": [], "hurting": []}
    rows = pull_arccos.extract_sga_bands(dash2)
    # Should still have all other rows; caddie rows just absent
    assert not any(r["metric"] in ("caddie_helping", "caddie_hurting") for r in rows)
    assert any(r["metric"] == "chip_by_pin_distance" for r in rows)


def test_none_dashboard_returns_empty():
    assert pull_arccos.extract_sga_bands(None) == []


def test_empty_dict_returns_empty():
    assert pull_arccos.extract_sga_bands({}) == []


def test_sga_bands_cols_defined():
    assert "section" in pull_arccos.SGA_BANDS_COLS
    assert "metric" in pull_arccos.SGA_BANDS_COLS
    assert "slab" in pull_arccos.SGA_BANDS_COLS
    assert "sga" in pull_arccos.SGA_BANDS_COLS
    assert "shots_count" in pull_arccos.SGA_BANDS_COLS

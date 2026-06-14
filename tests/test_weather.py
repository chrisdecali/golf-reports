"""
Tests for ingest/weather.py — offline, no real network calls.

All HTTP calls are intercepted by monkeypatching urllib.request.urlopen.
"""

import io
import json
import os
import urllib.error
import urllib.request

import pytest

import weather
from weather import cardinal, fetch_round_weather, weather_code_text
import pull_arccos


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hourly_response(hours=None):
    """Build a minimal Open-Meteo archive JSON payload.

    Default: 24-hour UTC day with index 14 (14:00) populated with:
      temp_f=78.5, wind_mph=12.3, wind_dir_deg=270 (W), weather_code=2 (Partly cloudy)
    """
    times = [f"2026-06-14T{h:02d}:00" for h in range(24)]
    temps = [70.0] * 24
    winds = [5.0] * 24
    dirs = [180.0] * 24
    codes = [0] * 24

    # Override index 14 (14:00 UTC) with our target values.
    temps[14] = 78.5
    winds[14] = 12.3
    dirs[14] = 270.0
    codes[14] = 2

    if hours is not None:
        # Caller specifies the full arrays.
        times, temps, winds, dirs, codes = hours

    payload = {
        "hourly": {
            "time": times,
            "temperature_2m": temps,
            "wind_speed_10m": winds,
            "wind_direction_10m": dirs,
            "weather_code": codes,
        }
    }
    return json.dumps(payload).encode()


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# weather_code_text unit tests
# ---------------------------------------------------------------------------

def test_weather_code_clear():
    assert weather_code_text(0) == "Clear"


def test_weather_code_mostly_clear():
    assert weather_code_text(1) == "Mostly clear"


def test_weather_code_partly_cloudy():
    assert weather_code_text(2) == "Partly cloudy"


def test_weather_code_overcast():
    assert weather_code_text(3) == "Overcast"


def test_weather_code_fog():
    assert weather_code_text(45) == "Fog"
    assert weather_code_text(48) == "Fog"


def test_weather_code_drizzle():
    assert weather_code_text(51) == "Drizzle"
    assert weather_code_text(57) == "Drizzle"


def test_weather_code_rain():
    assert weather_code_text(61) == "Rain"
    assert weather_code_text(67) == "Rain"


def test_weather_code_snow():
    assert weather_code_text(71) == "Snow"


def test_weather_code_showers():
    assert weather_code_text(80) == "Showers"
    assert weather_code_text(82) == "Showers"


def test_weather_code_thunderstorm():
    assert weather_code_text(95) == "Thunderstorm"
    assert weather_code_text(99) == "Thunderstorm"


def test_weather_code_unknown():
    result = weather_code_text(42)
    assert "42" in result


# ---------------------------------------------------------------------------
# cardinal unit tests
# ---------------------------------------------------------------------------

def test_cardinal_north():
    assert cardinal(0) == "N"
    assert cardinal(360) == "N"


def test_cardinal_east():
    assert cardinal(90) == "E"


def test_cardinal_south():
    assert cardinal(180) == "S"


def test_cardinal_west():
    assert cardinal(270) == "W"


def test_cardinal_northeast():
    assert cardinal(45) == "NE"


def test_cardinal_northwest():
    assert cardinal(315) == "NW"


def test_cardinal_southeast():
    assert cardinal(135) == "SE"


def test_cardinal_southwest():
    assert cardinal(225) == "SW"


# ---------------------------------------------------------------------------
# fetch_round_weather: successful fetch
# ---------------------------------------------------------------------------

def test_fetch_round_weather_returns_correct_values(monkeypatch, tmp_path):
    """Happy path: HTTP returns canned payload; check all 5 fields."""

    def fake_urlopen(req, timeout=None):
        return _FakeResponse(_make_hourly_response())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = fetch_round_weather(
        lat=30.059, lng=-95.513, date="2026-06-14",
        mid_hour_utc=14, cache_dir=str(tmp_path),
    )

    assert result["temp_f"] == 78.5
    assert result["wind_mph"] == 12.3
    assert result["wind_dir_deg"] == 270
    assert result["wind_dir"] == "W"
    assert result["weather"] == "Partly cloudy"


# ---------------------------------------------------------------------------
# fetch_round_weather: graceful failures — must return {} not raise
# ---------------------------------------------------------------------------

def test_fetch_graceful_on_http_error(monkeypatch, tmp_path):
    """HTTP 500 -> {}."""
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError("url", 500, "Server Error", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = fetch_round_weather(30.0, -95.0, "2026-06-14", 14, cache_dir=str(tmp_path))
    assert result == {}


def test_fetch_graceful_on_url_error(monkeypatch, tmp_path):
    """Network failure -> {}."""
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = fetch_round_weather(30.0, -95.0, "2026-06-14", 14, cache_dir=str(tmp_path))
    assert result == {}


def test_fetch_graceful_on_malformed_json(monkeypatch, tmp_path):
    """Garbled JSON -> {}."""
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(b"not-json!!!")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = fetch_round_weather(30.0, -95.0, "2026-06-14", 14, cache_dir=str(tmp_path))
    assert result == {}


def test_fetch_graceful_on_empty_hourly(monkeypatch, tmp_path):
    """Empty hourly arrays -> {}."""
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(json.dumps({"hourly": {"time": [], "temperature_2m": [],
                                                     "wind_speed_10m": [], "wind_direction_10m": [],
                                                     "weather_code": []}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = fetch_round_weather(30.0, -95.0, "2026-06-14", 14, cache_dir=str(tmp_path))
    assert result == {}


def test_fetch_no_cache_dir_does_not_raise(monkeypatch):
    """cache_dir=None: no caching attempt, still returns result."""
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(_make_hourly_response())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = fetch_round_weather(30.059, -95.513, "2026-06-14", 14, cache_dir=None)
    assert result["temp_f"] == 78.5


# ---------------------------------------------------------------------------
# fetch_round_weather: cache behaviour
# ---------------------------------------------------------------------------

def test_fetch_cache_hit_skips_network(monkeypatch, tmp_path):
    """Second call with same (lat, lng, date) must load from cache.

    The network seam raises on any call — if the cache is loaded correctly the
    second call should succeed without touching the network.
    """
    call_count = {"n": 0}

    def fake_urlopen(req, timeout=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FakeResponse(_make_hourly_response())
        # Second call must never reach here.
        raise urllib.error.URLError("should not be called — cache should hit")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    lat, lng, date, hour = 30.059, -95.513, "2026-06-14", 14

    # First call populates cache.
    r1 = fetch_round_weather(lat, lng, date, hour, cache_dir=str(tmp_path))
    assert r1["temp_f"] == 78.5

    # Second call must use cache (not raise URLError).
    r2 = fetch_round_weather(lat, lng, date, hour, cache_dir=str(tmp_path))
    assert r2 == r1
    assert call_count["n"] == 1  # network was called exactly once


def test_fetch_cache_file_exists_after_success(monkeypatch, tmp_path):
    """Cache file is written under <cache_dir>/_cache_weather/ after a live fetch."""
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(_make_hourly_response())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    fetch_round_weather(30.059, -95.513, "2026-06-14", 14, cache_dir=str(tmp_path))

    cache_dir = os.path.join(str(tmp_path), "_cache_weather")
    assert os.path.isdir(cache_dir)
    files = os.listdir(cache_dir)
    assert len(files) == 1
    with open(os.path.join(cache_dir, files[0])) as f:
        cached = json.load(f)
    assert cached["temp_f"] == 78.5


def test_fetch_graceful_cache_not_written_on_failure(monkeypatch, tmp_path):
    """On HTTP error, {} is returned and no cache file is written."""
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = fetch_round_weather(30.059, -95.513, "2026-06-14", 14, cache_dir=str(tmp_path))
    assert result == {}

    cache_dir = os.path.join(str(tmp_path), "_cache_weather")
    # Cache dir might not even be created; if it is, must be empty.
    if os.path.isdir(cache_dir):
        assert os.listdir(cache_dir) == []


# ---------------------------------------------------------------------------
# pull_arccos.ROUND_COLS includes all 5 weather columns
# ---------------------------------------------------------------------------

def test_round_cols_contains_weather_columns():
    weather_cols = {"temp_f", "wind_mph", "wind_dir_deg", "wind_dir", "weather"}
    assert weather_cols.issubset(set(pull_arccos.ROUND_COLS)), (
        f"Missing from ROUND_COLS: {weather_cols - set(pull_arccos.ROUND_COLS)}"
    )

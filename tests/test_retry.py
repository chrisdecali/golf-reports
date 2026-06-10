import urllib.error

import pull_arccos
import pull_ghin
import pytest


def _flaky(fail_times, code=503):
    state = {"n": 0}
    def fn():
        if state["n"] < fail_times:
            state["n"] += 1
            raise urllib.error.HTTPError("u", code, "boom", {}, None)
        return {"ok": True}
    return fn


@pytest.mark.parametrize("mod", [pull_arccos, pull_ghin])
def test_retry_recovers_from_transient_5xx(mod, monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    assert mod._with_retry(_flaky(2)) == {"ok": True}


@pytest.mark.parametrize("mod", [pull_arccos, pull_ghin])
def test_retry_gives_up_after_attempts(mod, monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        mod._with_retry(_flaky(99))


@pytest.mark.parametrize("mod", [pull_arccos, pull_ghin])
def test_retry_does_not_retry_4xx(mod, monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 401, "no", {}, None)
    with pytest.raises(urllib.error.HTTPError):
        mod._with_retry(fn)
    assert calls["n"] == 1


@pytest.mark.parametrize("mod", [pull_arccos, pull_ghin])
def test_retry_recovers_from_urlerror(mod, monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    state = {"n": 0}
    def fn():
        if state["n"] < 2:
            state["n"] += 1
            raise urllib.error.URLError("connection reset")
        return {"ok": True}
    assert mod._with_retry(fn) == {"ok": True}

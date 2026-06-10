import json
import sys
import types

import pytest

import pull_ghin


def test_load_creds_reads_password_from_keyring(tmp_path, monkeypatch):
    creds = tmp_path / ".ghin_creds.json"
    creds.write_text(json.dumps({"email": "a@b.c", "ghin_id": "123",
                                 "password_in_keyring": True}))
    monkeypatch.setattr(pull_ghin, "CREDS_PATH", str(creds))
    for var in ("GHIN_BEARER", "GHIN_ID", "GHIN_EMAIL", "GHIN_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    fake = types.SimpleNamespace(
        get_password=lambda svc, user: "sekrit" if (svc, user) == ("golf-reports-ghin", "a@b.c") else None)
    monkeypatch.setitem(sys.modules, "keyring", fake)

    seen = {}
    def fake_login(email, password):
        seen["pw"] = password
        return "tok123", "123"
    monkeypatch.setattr(pull_ghin, "ghin_login", fake_login)

    tok, ghin = pull_ghin.load_creds()
    assert tok == "tok123" and ghin == "123"
    assert seen["pw"] == "sekrit"

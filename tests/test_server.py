import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVER_PATH = os.path.join(REPO, "mcp", "server.py")


def _load_server():
    """Load mcp/server.py via spec_from_file_location to avoid the mcp/ dir
    shadowing the installed mcp package when doing `from mcp.server.fastmcp import FastMCP`."""
    # Snapshot sys.path so the restore is safe even when duplicates are present
    saved = list(sys.path)
    mcp_dir = os.path.join(REPO, "mcp")
    if mcp_dir in sys.path:
        sys.path.remove(mcp_dir)
    try:
        # Remove any previously cached module so reload picks up env changes
        sys.modules.pop("server", None)
        spec = importlib.util.spec_from_file_location("server", _SERVER_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["server"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path[:] = saved


@pytest.fixture
def srv(store, monkeypatch):
    monkeypatch.setenv("GOLF_STORE", store)
    return _load_server()


def test_import_rejects_outside_home(srv):
    assert srv.import_18birdies("/etc/passwd").startswith("error")


def test_import_rejects_non_json(srv, tmp_path):
    # ~/.bashrc is a guaranteed non-.json file in $HOME
    p = os.path.expanduser("~/.bashrc")
    assert srv.import_18birdies(p).startswith("error")


def test_import_rejects_creds_lookalike_traversal(srv):
    assert srv.import_18birdies("~/../../etc/passwd").startswith("error")


def test_import_rejects_control_chars(srv):
    assert srv.import_18birdies("~/x\x00y.json").startswith("error")


def test_ingest_defaults_to_bundled_dir(store, monkeypatch):
    monkeypatch.delenv("GOLF_INGEST", raising=False)
    monkeypatch.setenv("GOLF_STORE", store)
    server = _load_server()
    assert server.INGEST.endswith(os.path.join("golf-reports", "ingest"))
    assert os.path.isfile(os.path.join(server.INGEST, "pull_arccos.py"))


def test_import_valid_json_reaches_run(store, tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_STORE", store)
    server = _load_server()
    monkeypatch.setattr(server, "HOME", str(tmp_path))
    f = tmp_path / "archive.json"
    f.write_text("{}")
    monkeypatch.setattr(server, "_run", lambda *a: "stubbed:" + a[1])
    assert server.import_18birdies(str(f)).startswith("stubbed:")


def test_run_surfaces_stderr_and_tail(store, tmp_path, monkeypatch):
    ingest = tmp_path / "ingest"
    ingest.mkdir()
    (ingest / "fake.py").write_text(
        "import sys\n"
        "print('line1'); print('line2'); print('line3')\n"
        "print('the real error: token expired', file=sys.stderr)\n"
        "sys.exit(3)\n")
    monkeypatch.setenv("GOLF_INGEST", str(ingest))
    monkeypatch.setenv("GOLF_STORE", store)
    server = _load_server()
    out = server._run("fake.py")
    assert out.startswith("exit 3:")
    assert "line2" in out                      # more than just the last line
    assert "token expired" in out              # stderr included


def test_sync_cooldown(store, monkeypatch):
    monkeypatch.setenv("GOLF_STORE", store)
    server = _load_server()
    t = {"now": 1000.0}
    monkeypatch.setattr(server, "time", __import__("types").SimpleNamespace(time=lambda: t["now"]))
    server._mark_sync("pull_arccos.py")
    msg = server._cooldown_left("pull_arccos.py")
    assert msg and "cooldown" in msg          # immediately re-running is blocked
    t["now"] += 601
    assert server._cooldown_left("pull_arccos.py") is None   # expired


def test_logout_clears_keyring_entry(store, tmp_path, monkeypatch):
    import json as _json
    import sys as _sys
    import types as _types
    monkeypatch.setenv("GOLF_STORE", store)
    server = _load_server()
    monkeypatch.setattr(server, "HOME", str(tmp_path))
    (tmp_path / ".ghin_creds.json").write_text(_json.dumps({"email": "a@b.c", "password_in_keyring": True}))
    deleted = {}
    fake = _types.SimpleNamespace(delete_password=lambda svc, user: deleted.setdefault("k", (svc, user)))
    monkeypatch.setitem(_sys.modules, "keyring", fake)
    out = server.logout()
    assert deleted["k"] == ("golf-reports-ghin", "a@b.c")
    assert "keychain entry" in out and ".ghin_creds.json" in out
    assert not (tmp_path / ".ghin_creds.json").exists()

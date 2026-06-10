import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVER_PATH = os.path.join(REPO, "mcp", "server.py")


def _load_server(store: str = ""):
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
    return _load_server(store)


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
    server = _load_server(store)
    assert server.INGEST.endswith(os.path.join("golf-reports", "ingest"))
    assert os.path.isfile(os.path.join(server.INGEST, "pull_arccos.py"))


def test_import_valid_json_reaches_run(store, tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_STORE", store)
    server = _load_server(store)
    monkeypatch.setattr(server, "HOME", str(tmp_path))
    f = tmp_path / "archive.json"
    f.write_text("{}")
    monkeypatch.setattr(server, "_run", lambda *a: "stubbed:" + a[1])
    assert server.import_18birdies(str(f)).startswith("stubbed:")

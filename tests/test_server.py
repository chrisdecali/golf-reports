import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVER_PATH = os.path.join(REPO, "mcp", "server.py")


def _load_server(store: str):
    """Load mcp/server.py via spec_from_file_location to avoid the mcp/ dir
    shadowing the installed mcp package when doing `from mcp.server.fastmcp import FastMCP`."""
    # Temporarily remove repo mcp/ from sys.path so installed mcp package is found
    mcp_dir = os.path.join(REPO, "mcp")
    removed = mcp_dir in sys.path
    if removed:
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
        if removed:
            sys.path.insert(0, mcp_dir)


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

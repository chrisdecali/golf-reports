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


def test_alert_regenerates_dispersion(store, monkeypatch):
    import os
    pra.detect_new(store)                      # baseline
    with open(os.path.join(store, "rounds_summary.csv"), "a", newline="") as f:
        f.write("r4,2026-06-11,Wind Rose GC,Blue,6400,,,18,9,8,1,4,,50.0,100.0,0.0,-1.0,-0.2,-0.4,-0.2,-0.2\n")
    monkeypatch.setattr(pra, "send_telegram", lambda text: True)
    monkeypatch.setattr(pra, "send_document", lambda path, caption="": True)
    pra.main_for_store(store)
    assert os.path.exists(os.path.join(store, "dispersion.json"))


def test_send_document_posts_multipart(tmp_path, monkeypatch):
    monkeypatch.setattr(pra, "env_key", lambda n: "TOK" if "TOKEN" in n else "CHAT")
    pdf = tmp_path / "round.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake shot maps")
    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["ctype"] = req.headers.get("Content-type")
        captured["body"] = req.data
        return _Resp()

    monkeypatch.setattr(pra.urllib.request, "urlopen", fake_urlopen)
    ok = pra.send_document(str(pdf), "WindRose 2026-06-06")
    assert ok is True
    assert captured["url"].endswith("/sendDocument")
    assert captured["ctype"].startswith("multipart/form-data; boundary=")
    assert b'filename="round.pdf"' in captured["body"]
    assert b"%PDF-1.4 fake shot maps" in captured["body"]      # file bytes embedded
    assert b"WindRose 2026-06-06" in captured["body"]          # caption embedded


def test_send_document_missing_file(monkeypatch):
    monkeypatch.setattr(pra, "env_key", lambda n: "X")
    assert pra.send_document("/no/such/file.pdf", "x") is False


def test_send_document_unconfigured(monkeypatch):
    monkeypatch.setattr(pra, "env_key", lambda n: None)
    assert pra.send_document("/whatever.pdf") is False


def test_main_sends_pdf_for_new_round(store, monkeypatch):
    pra.detect_new(store)                      # baseline
    with open(os.path.join(store, "rounds_summary.csv"), "a", newline="") as f:
        f.write("r5,2026-06-12,Wind Rose GC,Blue,6400,,,18,9,8,1,4,,50.0,100.0,0.0,-1.0,-0.2,-0.4,-0.2,-0.2\n")
    sent = []
    monkeypatch.setattr(pra, "send_telegram", lambda text: True)
    monkeypatch.setattr(pra, "send_document", lambda path, caption="": sent.append(path) or True)
    pra.main_for_store(store)
    assert len(sent) == 1
    assert sent[0].endswith("_shotmaps.pdf")

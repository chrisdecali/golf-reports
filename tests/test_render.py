import os

import gen_combined as gc
import gen_gps_pdf
import gen_stats


def test_html_escapes_api_strings(store, tmp_path):
    out = str(tmp_path / "out")
    path = gc.gen(store, out, "r1")          # r1 course = '<img src=x onerror=alert(1)>'
    html = open(path, encoding="utf-8").read()
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_render_survives_none_score_to_par(store, tmp_path):
    out = str(tmp_path / "out")
    # r2 has score_to_par="" at round level and on hole 2 -> must not raise
    path = gc.gen(store, out, "r2")
    assert os.path.exists(path)
    pdf = gen_gps_pdf.gen(store, out, "r2")
    assert os.path.exists(pdf)
    assert "—" in open(path, encoding="utf-8").read()
    stats = gen_stats.gen(store, out, "r2")
    assert os.path.exists(stats)


def test_slug_sanitizes_hostile_names():
    d = {"course": "../../etc <evil>", "date": "2026-06-08", "round_id": "r9"}
    s = gc._slug(d)
    assert "/" not in s and "<" not in s and ".." not in s

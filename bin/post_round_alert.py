#!/usr/bin/env python3
"""Post-round Telegram alert. Run after a sync (cron hook in ~/arccos_update.sh).

Detects round_ids in <store>/rounds_summary.csv not yet in <store>/_alerted.json,
renders each (HTML+PDF into <store>/reports/), sends a Telegram summary, records
the id. First run baselines all existing rounds silently. Reporting must never
fail the sync: every external step is try/except'd.

Usage: post_round_alert.py [store_dir]   (default ~/arccos_out)
Telegram creds: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from env, ~/alfred/.env,
or ~/.secrets.env (first hit wins; values may be quoted).
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "render"))

import gen_combined as gc        # noqa: E402
import gen_gps_pdf               # noqa: E402

_SG_LABELS = {"off_tee": "Tee", "approach": "App", "short": "Short", "putting": "Putt"}


def env_key(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    for envfile in ("~/alfred/.env", "~/.secrets.env"):
        try:
            with open(os.path.expanduser(envfile), encoding="utf-8") as f:
                for line in f:
                    line = line.lstrip()
                    if line.startswith("export "):
                        line = line[7:].lstrip()
                    if line.startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip("'\"") or None
        except FileNotFoundError:
            continue
    return None


def detect_new(store: str) -> list[str]:
    """Round ids present in the store but not yet alerted. First call baselines."""
    path = os.path.join(store, "rounds_summary.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        ids = [r["round_id"] for r in csv.DictReader(f) if r.get("round_id")]
    seen_path = os.path.join(store, "_alerted.json")
    first_run = not os.path.exists(seen_path)
    if first_run:
        seen = set()
    else:
        with open(seen_path, encoding="utf-8") as fh:
            seen = set(json.load(fh))
    new = [i for i in ids if i not in seen]
    tmp = seen_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(seen | set(new)), f)
    os.replace(tmp, seen_path)
    return [] if first_run else new


def build_message(store: str, rid: str) -> str:
    d = gc.compute(store, rid)
    sg = d["sg"]
    stp = f"{d['score_to_par']:+d}" if isinstance(d.get("score_to_par"), int) else "—"
    lines = [f"⛳ New round: {d['course']} — {d['date']}",
             f"{d['score']} ({stp}) · {d['putts']} putts",
             "SG: " + "  ".join(
                 f"{k} {v:+.1f}" for k, v in
                 (("Tot", sg["total"]), ("Tee", sg["off_tee"]), ("App", sg["approach"]),
                  ("Short", sg["short"]), ("Putt", sg["putting"])) if v is not None)]
    worst = min(((k, v) for k, v in sg.items() if k != "total" and v is not None),
                key=lambda kv: kv[1], default=None)
    if worst:
        lines.append(f"Biggest leak: {_SG_LABELS.get(worst[0], worst[0])} ({worst[1]:+.1f})")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    token, chat = env_key("TELEGRAM_BOT_TOKEN"), env_key("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[alert] telegram not configured — skipping send")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return bool(json.load(r).get("ok"))


def send_document(path: str, caption: str = "") -> bool:
    """Send a local file (the shot-map PDF) to Telegram via multipart sendDocument."""
    token, chat = env_key("TELEGRAM_BOT_TOKEN"), env_key("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[alert] telegram not configured — skipping document")
        return False
    if not path or not os.path.exists(path):
        print(f"[alert] document missing, skipping: {path}", file=sys.stderr)
        return False
    boundary = "----golfreports" + uuid.uuid4().hex
    parts = []
    def _field(name: str, val: str) -> None:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f"name=\"{name}\"\r\n\r\n{val}\r\n".encode())
    _field("chat_id", chat)
    if caption:
        _field("caption", caption)
    with open(path, "rb") as fh:
        blob = fh.read()
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
                  f"filename=\"{os.path.basename(path)}\"\r\n"
                  f"Content-Type: application/pdf\r\n\r\n").encode() + blob + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendDocument", data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return bool(json.load(r).get("ok"))


def main_for_store(store: str) -> int:
    for rid in detect_new(store):
        pdf_path = None
        try:
            reports = os.path.join(store, "reports")
            gc.gen(store, reports, rid)
            pdf_path = gen_gps_pdf.gen(store, reports, rid)
        except Exception as e:  # render failure must not block the alert
            print(f"[alert] render failed for {rid}: {e}", file=sys.stderr)
        try:
            msg = build_message(store, rid)
            print(f"[alert] telegram sent: {send_telegram(msg)} for {rid}")
            if pdf_path:  # attach the shot-map PDF so it's viewable on the phone
                caption = msg.splitlines()[0][:1024]   # Telegram caption hard limit
                print(f"[alert] pdf sent: {send_document(pdf_path, caption)} for {rid}")
        except Exception as e:  # alerting must never fail the sync
            print(f"[alert] alert failed for {rid}: {e}", file=sys.stderr)
    try:
        import dispersion as _disp
        _disp.write(store)
    except Exception as e:  # never fail the sync
        print(f"[alert] dispersion regen failed: {e}", file=sys.stderr)
    return 0


def main() -> int:
    store = os.path.abspath(os.path.expanduser(
        sys.argv[1] if len(sys.argv) > 1 else "~/arccos_out"))
    return main_for_store(store)


if __name__ == "__main__":
    sys.exit(main())

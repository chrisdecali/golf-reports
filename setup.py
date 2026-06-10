#!/usr/bin/env python3
"""
One-time setup for golf-reports — NO browser DevTools.

Logs into Arccos + GHIN with email/password (stored locally, chmod 600, never
uploaded), optionally imports an 18Birdies export, then runs a first sync.
Re-run anytime to refresh credentials.

    python3 setup.py
"""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INGEST = os.path.join(HERE, "ingest")
sys.path.insert(0, INGEST)
import pull_arccos as pa   # noqa: E402
import pull_ghin as pg     # noqa: E402

STORE = os.environ.get("GOLF_STORE", os.path.expanduser("~/golf-data"))


def _yes(prompt: str) -> bool:
    return input(prompt).strip().lower() in ("", "y", "yes")


def main() -> None:
    print("== Golf Reports setup ==  credentials stay on THIS machine (chmod 600), never uploaded.\n")

    if _yes("Link Arccos? [Y/n] "):
        em = input("  Arccos email: ").strip()
        pw = getpass.getpass("  Arccos password (used once, NOT stored): ")
        ak, uid = pa.arccos_login(em, pw)
        if ak:
            pa._save_creds({"access_key": ak, **({"user_id": uid} if uid else {})})
            print("  ✓ Arccos linked (long-lived accessKey stored; password discarded).\n")
        else:
            print("  ✗ Arccos login failed — check email/password.\n")

    if _yes("Link GHIN? [Y/n] "):
        em = input("  GHIN email: ").strip()
        pw = getpass.getpass("  GHIN password: ")
        tok, gid = pg.ghin_login(em, pw)
        if tok:
            meta = {"email": em, "ghin_id": gid}
            stored = ""
            try:
                import keyring
                keyring.set_password("golf-reports-ghin", em, pw)
                meta["password_in_keyring"] = True
                stored = "password in OS keychain"
            except Exception:
                print("  note: OS keychain unavailable on this system.")
                if _yes("  No OS keychain available. GHIN needs the password each sync "
                        "(12h tokens, no refresh). Store it in ~/.ghin_creds.json, "
                        "chmod 600, plaintext? [Y/n] "):
                    meta["password"] = pw
                    stored = "password in ~/.ghin_creds.json (plaintext, chmod 600)"
                else:
                    stored = "password NOT stored — set GHIN_PASSWORD env or re-run setup before syncing"
            p = os.path.expanduser("~/.ghin_creds.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(meta, f)
            os.chmod(p, 0o600)
            print(f"  ✓ GHIN linked ({stored}).\n")
        else:
            print("  ✗ GHIN login failed — check email/password.\n")

    ap = input("18Birdies export path (download from 18birdies.com/download-account-data; blank to skip): ").strip()
    ap = os.path.expanduser(ap) if ap else ""
    if ap and os.path.exists(ap):
        subprocess.run([sys.executable, os.path.join(INGEST, "pull_18birdies.py"), ap],
                       env=dict(os.environ, GOLF_STORE=STORE))
        print()

    if _yes(f"Run a first sync now into {STORE}? [Y/n] "):
        os.makedirs(STORE, exist_ok=True)
        env = dict(os.environ, GOLF_STORE=STORE)
        for s in ("pull_arccos.py", "pull_ghin.py"):
            print(f"  syncing {s} ...")
            subprocess.run([sys.executable, os.path.join(INGEST, s)], cwd=INGEST, env=env)

    print("\nDone. In Claude Desktop: install the extension/plugin, then ask "
          "\"how was my last round?\" or \"render my latest round as a PDF\".")


if __name__ == "__main__":
    main()

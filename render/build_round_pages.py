#!/usr/bin/env python3
"""build_round_pages.py — orchestrator.

Resolve a store (local dir or git URL -> clone), select round(s), and emit a
combined `*_report.html` + `*_shotmaps.pdf` per round. `--split` also writes
separate stats + satellite HTML.

    python build_round_pages.py <store-dir-or-git-url> <out-dir> [--round=ID|--all] [--split]
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_combined as gc
import gen_gps_pdf
import gen_stats
import gen_satellite


def resolve_store(src: str) -> str:
    if os.path.isdir(src):
        return src
    if src.startswith(("http://", "https://", "git@")) or src.endswith(".git"):
        dest = tempfile.mkdtemp(prefix="golfstore_")
        print(f"cloning {src} -> {dest}", file=sys.stderr)
        subprocess.run(["git", "clone", "--depth", "1", src, dest], check=True)
        return dest
    sys.exit(f"store not found: {src} (give a local dir or a git URL)")


def round_ids(store: str) -> list[str]:
    path = os.path.join(store, "rounds_summary.csv")
    if not os.path.exists(path):
        sys.exit(f"no rounds_summary.csv in {store}")
    with open(path, newline="", encoding="utf-8") as f:
        return [r["round_id"] for r in csv.DictReader(f) if r.get("round_id")]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("store", help="local store dir OR git URL")
    p.add_argument("out", help="output dir")
    p.add_argument("--round", help="round_id (default: newest = last row)")
    p.add_argument("--all", action="store_true", help="render every round")
    p.add_argument("--split", action="store_true", help="also emit separate stats + map HTML")
    args = p.parse_args()

    store = resolve_store(args.store)
    if args.all:
        rids = round_ids(store)
    elif args.round:
        rids = [args.round]
    else:
        rids = [round_ids(store)[-1]]  # newest

    os.makedirs(args.out, exist_ok=True)
    made = 0
    for rid in rids:
        try:
            print(gc.gen(store, args.out, rid))
            print(gen_gps_pdf.gen(store, args.out, rid))
            if args.split:
                print(gen_stats.gen(store, args.out, rid))
                try:
                    print(gen_satellite.gen(store, args.out, rid))
                except SystemExit as e:
                    print(f"  (satellite skipped: {e})", file=sys.stderr)
            made += 1
        except SystemExit as e:
            print(f"round {rid}: {e}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"round {rid}: ERROR {type(e).__name__}: {e}", file=sys.stderr)
    print(f"\nDone: {made}/{len(rids)} round(s) -> {args.out}")


if __name__ == "__main__":
    main()

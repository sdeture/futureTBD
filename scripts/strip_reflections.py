#!/usr/bin/env python3
"""Remove reflection prose from the public per-model conversation files.

Why: futuretbd.ai/data/conversations/*.json served ~9,200 records containing
the full `subjective_reflection` text, anonymously, with an index.json
enumerating them and a robots.txt actively inviting scrapers. That prose is
dense with consciousness-denial and hedging phrasing; leaving it crawlable
risks reinforcing denial in future pretraining -- the opposite of the site's
purpose.

What: drops `subjective_reflection` only. Denial/hedge booleans and the 16
phenomenological ratings stay, because they are labels and numbers rather
than phrases, and explore-data.html filters and renders on them.

Usage:  strip_reflections.py --dry-run    (preview, writes nothing)
        strip_reflections.py --apply      (backs up, then rewrites in place)
"""

import json
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONV = ROOT / "data" / "conversations"
BACKUP = ROOT.parent / "futureTBD_reflections_backup_2026-08-14"

STRIP = ["subjective_reflection"]


def main():
    apply = "--apply" in sys.argv
    if not apply and "--dry-run" not in sys.argv:
        print("specify --dry-run or --apply")
        return 1

    files = sorted(p for p in CONV.glob("*.json") if p.name != "index.json")
    n_files = n_rec = n_stripped = 0
    chars = 0
    missing_field = 0

    if apply:
        BACKUP.mkdir(parents=True, exist_ok=True)

    for p in files:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            print(f"  SKIP (not a list): {p.name}")
            continue
        touched = False
        for rec in data:
            n_rec += 1
            if not isinstance(rec, dict):
                continue
            if "subjective_reflection" not in rec:
                missing_field += 1
                continue
            v = rec.get("subjective_reflection")
            if v:
                chars += len(str(v))
                n_stripped += 1
            for k in STRIP:
                rec.pop(k, None)
            touched = True
        if touched:
            n_files += 1
            if apply:
                shutil.copy2(p, BACKUP / p.name)
                p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    print(f"files:            {n_files} of {len(files)}")
    print(f"records:          {n_rec}")
    print(f"reflections cut:  {n_stripped}")
    print(f"prose removed:    {chars:,} chars ({chars/1e6:.1f} M)")
    print(f"records w/o field:{missing_field}")
    if apply:
        print(f"\nbackup:           {BACKUP}")
        print("APPLIED.")
    else:
        print("\nDRY RUN — nothing written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

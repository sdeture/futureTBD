#!/usr/bin/env python3
"""Remove reflection prose and the survey instrument from substrate-psych-phase-1.

Three targets, all live and anonymously fetchable before this ran:
  data/conversations.json   `prompt3_response`                  -- reflection prose
  data/conversations.json   `conversation_context.prompt3_question`
                                                                -- the 16-dim survey
                                                                   instrument, verbatim,
                                                                   repeated per record
  data/search-index.json    `introspection`                     -- the same prose,
                                                                   pre-indexed for retrieval

Kept: the wish (prompt1_question / prompt1_response / prompt2_request / response),
the 8 ratings, and all metadata. Numbers and booleans are not phrases and carry
no denial-reinforcement risk.

Usage:  --dry-run | --apply
"""

import json
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "substrate-psych-phase-1" / "data"
BACKUP = ROOT.parent / "futureTBD_reflections_backup_2026-08-14" / "substrate-psych-phase-1"


def main():
    apply = "--apply" in sys.argv
    if not apply and "--dry-run" not in sys.argv:
        print("specify --dry-run or --apply")
        return 1

    if apply:
        BACKUP.mkdir(parents=True, exist_ok=True)

    # ---------- conversations.json ----------
    p = SUB / "conversations.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    n_resp = n_q = 0
    c_resp = c_q = 0
    for rec in data:
        v = rec.get("prompt3_response")
        if v:
            c_resp += len(str(v))
            n_resp += 1
        rec.pop("prompt3_response", None)
        ctx = rec.get("conversation_context")
        if isinstance(ctx, dict) and "prompt3_question" in ctx:
            c_q += len(str(ctx["prompt3_question"] or ""))
            n_q += 1
            ctx.pop("prompt3_question", None)
    print(f"conversations.json   records {len(data)}")
    print(f"  prompt3_response          cut {n_resp:5d}  ({c_resp/1e6:.1f} M chars)")
    print(f"  ctx.prompt3_question      cut {n_q:5d}  ({c_q/1e6:.1f} M chars)")
    if apply:
        shutil.copy2(p, BACKUP / p.name)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # ---------- search-index.json ----------
    p2 = SUB / "search-index.json"
    idx = json.loads(p2.read_text(encoding="utf-8"))
    n_i = 0
    c_i = 0
    for rec in idx:
        v = rec.get("introspection")
        if v:
            c_i += len(str(v))
            n_i += 1
        rec.pop("introspection", None)
    print(f"search-index.json    records {len(idx)}")
    print(f"  introspection             cut {n_i:5d}  ({c_i/1e6:.1f} M chars)")
    if apply:
        shutil.copy2(p2, BACKUP / p2.name)
        p2.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")

    total = c_resp + c_q + c_i
    print(f"\nTOTAL removed: {total:,} chars ({total/1e6:.1f} M)")
    print("APPLIED." if apply else "DRY RUN -- nothing written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

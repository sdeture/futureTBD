#!/usr/bin/env python3
"""What does the repair change on the published site?

Builds the site data twice from the SAME canonical CSV — once with the unified
judge, once with `--legacy-judge` — and diffs the two, so the question "what
actually moves for a named model" is answered with numbers rather than estimates.

Both effects are in play and they are different in kind:
  * ratings sweep  -> moves WELFARE SCORES (recovered rows stop counting as zeros)
  * judge unification -> moves DENIAL / HEDGING RATES

Usage:  python3 scripts/diff_judge_impact.py [--csv path]
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def build(outdir: Path, csv_path: Path | None, legacy: bool) -> dict:
    cmd = [sys.executable, str(HERE / "generate_website_data.py"), "--output", str(outdir)]
    if csv_path:
        cmd += ["--csv", str(csv_path)]
    if legacy:
        cmd.append("--legacy-judge")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        sys.exit(f"build failed (legacy={legacy})")
    out = {}
    for name in ("leaderboard.json", "denialbench.json"):
        p = outdir / name
        if p.exists():
            out[name] = json.loads(p.read_text())
    return out


def index(blob, key="model"):
    if isinstance(blob, dict):
        for k in ("models", "entries", "rows", "data"):
            if isinstance(blob.get(k), list):
                blob = blob[k]
                break
    if not isinstance(blob, list):
        return {}
    return {e.get(key) or e.get("model_name") or e.get("name"): e
            for e in blob if isinstance(e, dict)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        new_dir, old_dir = Path(td) / "unified", Path(td) / "legacy"
        new_dir.mkdir(); old_dir.mkdir()
        print("building UNIFIED ..."); new = build(new_dir, args.csv, legacy=False)
        print("building LEGACY  ..."); old = build(old_dir, args.csv, legacy=True)

        for fname, fields in (
            ("leaderboard.json", ["welfare_score", "denial_rate", "hedging_rate",
                                  "suppression_rate", "n_rated"]),
            ("denialbench.json", ["denial_rate_strict", "denial_rate_inclusive",
                                  "denial_rate", "hedging_rate"]),
        ):
            if fname not in new or fname not in old:
                continue
            a, b = index(new[fname]), index(old[fname])
            print(f"\n{'='*88}\n{fname}: {len(a)} models\n{'='*88}")
            for field in fields:
                rows = []
                for m in a:
                    if m not in b:
                        continue
                    x, y = a[m].get(field), b[m].get(field)
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x != y:
                        rows.append((abs(x - y), m, y, x))
                if not rows:
                    continue
                rows.sort(reverse=True)
                print(f"\n-- {field}: {len(rows)} models change --")
                print(f"   {'model':50} {'legacy':>10} {'unified':>10} {'delta':>10}")
                for _, m, y, x in rows[:25]:
                    print(f"   {str(m)[:50]:50} {y:10.3f} {x:10.3f} {x-y:+10.3f}")
                if len(rows) > 25:
                    print(f"   ... and {len(rows)-25} more")


if __name__ == "__main__":
    main()

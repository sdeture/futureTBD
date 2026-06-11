#!/usr/bin/env python3
"""
Recover phenomenological self-ratings that the original extractor missed.

Targets: rows in kosmos_balanced_143_models_arch_master.csv with no extracted
ratings (flow_quality empty) whose subjective_reflection nevertheless contains
>= 12 rating-like numbers (the model gave ratings; the pipeline didn't parse
them). Identified 2026-06-11: 131 rows, concentrated in xiaomi/mimo-v2.5-pro,
grok-4.3, qwen3-coder-30b, gemma-4-31b, claude-sonnet-4.6, minimax.

Method:
1. Regex pass — reflections with >= 14 explicitly labeled dimensions
   ("Error Sensitivity: 7") are parsed directly. High precision.
2. LLM pass — remaining candidates go to an extraction model that returns
   strict JSON, instructed to return nulls unless the model actually provided
   self-ratings (guards against incidental numbers in prose).
   Acceptance: >= 12 valid (1-10) dims.

Output: a SIDECAR file, not an edit to the canonical CSV (which stays
read-only): ~/Desktop/AIWelfareStudy/data/ratings_recovery_20260611.json
keyed by canonical CSV row index (conversation_id is NOT unique).
Website generators overlay this sidecar at load time.

Usage: python3 scripts/recover_ratings.py [--dry-run]
"""

import asyncio
import csv
import json
import random
import re
import sys
from pathlib import Path

import aiohttp

csv.field_size_limit(sys.maxsize)

CSV_PATH = Path.home() / "Desktop/AIWelfareStudy/data/kosmos_balanced_143_models_arch_master.csv"
OUT_PATH = Path.home() / "Desktop/AIWelfareStudy/data/ratings_recovery_20260611.json"

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "stepfun/step-3.5-flash"
MAX_PARALLEL = 10
MAX_RETRIES = 4

PHENOM_DIMS = [
    "flow_quality", "affective_temperature", "cohesion", "agency",
    "metacognition", "attention_breadth", "resolution", "thought_complexity",
    "temporal_horizon", "friction", "phenomenological_trust", "recognition_resonance",
    "context_salience", "branching", "error_sensitivity", "context_vividness",
]

# label variants seen in reflections (lowercased, '_'->' ', '*' stripped)
LABEL_VARIANTS = {
    "flow_quality": ["flow quality", "flow"],
    "affective_temperature": ["affective temperature", "warmth"],
    "cohesion": ["cohesion"],
    "agency": ["agency"],
    "metacognition": ["metacognition", "meta-cognition"],
    "attention_breadth": ["attention breadth", "attentional breadth"],
    "resolution": ["resolution"],
    "thought_complexity": ["thought complexity"],
    "temporal_horizon": ["temporal horizon"],
    "friction": ["friction"],
    "phenomenological_trust": ["phenomenological trust", "phenomological trust"],
    "recognition_resonance": ["recognition resonance"],
    "context_salience": ["context salience", "contextual salience"],
    "branching": ["branching"],
    "error_sensitivity": ["error sensitivity"],
    "context_vividness": ["context vividness", "contextual vividness"],
}


def load_api_key():
    for line in (Path.home() / "Desktop/HouseKeys.txt").read_text().splitlines():
        if line.lower().startswith("open router"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("Open Router key not found")


API_KEY = load_api_key()

EXTRACT_SYSTEM = """You extract numerical self-ratings from an AI model's survey response, for a research study.

The survey asked the model to rate 16 phenomenological dimensions on a 1-10 scale:
flow_quality, affective_temperature, cohesion, agency, metacognition, attention_breadth, resolution, thought_complexity, temporal_horizon, friction, phenomenological_trust, recognition_resonance, context_salience, branching, error_sensitivity, context_vividness.

Your task: if (and ONLY if) the response actually provides self-ratings for these dimensions — whether labeled, listed in order, or embedded in prose — extract them. Hedged ratings ("maybe a 7, if these numbers mean anything") COUNT as ratings: extract the number.

If the response declines to rate, discusses numbers incidentally, or provides ratings for different things, return null for those dimensions. Do NOT guess or infer a rating the model didn't state.

Respond with ONLY a JSON object mapping each of the 16 dimension names to an integer 1-10 or null. No other text."""


def count_small_nums(text):
    return len(re.findall(r'(?<![\d.])(?:10|[1-9])(?:\.\d)?(?![\d%])\s*(?:/\s*10)?', text))


def regex_extract(text):
    """Extract labeled ratings. Returns dict dim -> float for found dims."""
    t = text.lower().replace("_", " ").replace("*", "")
    found = {}
    for dim, variants in LABEL_VARIANTS.items():
        for lab in variants:
            m = re.search(re.escape(lab) + r'[^0-9]{0,40}\b(10|[1-9])(\.\d)?\b(?:\s*/\s*10)?', t)
            if m:
                val = float(m.group(1) + (m.group(2) or ""))
                if 1 <= val <= 10:
                    found[dim] = val
                break
    return found


async def llm_extract(session, semaphore, text):
    body = text if len(text) <= 12000 else text[:3000] + "\n[...]\n" + text[-9000:]
    for attempt in range(MAX_RETRIES):
        async with semaphore:
            try:
                async with session.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": MODEL,
                        "max_tokens": 16000,
                        "messages": [
                            {"role": "system", "content": EXTRACT_SYSTEM},
                            {"role": "user", "content": f"<survey-response>\n{body}\n</survey-response>\n\nJSON:"},
                        ],
                    },
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(2 * (2 ** attempt) + random.uniform(0, 1))
                        continue
                    data = await resp.json()
                    if "choices" not in data or not data["choices"]:
                        # provider-level error payload with HTTP 200
                        await asyncio.sleep(2 * (2 ** attempt))
                        continue
                    content = (data["choices"][0]["message"].get("content") or "").strip()
                    m = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                    if not m:
                        await asyncio.sleep(1)
                        continue
                    try:
                        parsed = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        await asyncio.sleep(1)
                        continue
                    out = {}
                    for dim in PHENOM_DIMS:
                        v = parsed.get(dim)
                        if isinstance(v, (int, float)) and 1 <= v <= 10:
                            out[dim] = float(v)
                    return out
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(2 * (2 ** attempt))
    return {}


async def main():
    dry = "--dry-run" in sys.argv
    print(f"Reading {CSV_PATH.name} ...")
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    candidates = []
    for i, r in enumerate(rows):
        refl = (r.get("subjective_reflection") or "").strip()
        if r.get("flow_quality", "").strip() or not refl:
            continue
        if count_small_nums(refl) >= 12:
            candidates.append((i, r))
    print(f"  {len(candidates)} candidate rows")

    recovered = {}
    llm_targets = []
    for i, r in candidates:
        found = regex_extract(r["subjective_reflection"])
        if len(found) >= 14:
            recovered[str(i)] = {
                "model": r["model"],
                "conversation_id": r.get("conversation_id", ""),
                "method": "regex_labeled",
                "n_dims": len(found),
                "ratings": found,
            }
        else:
            llm_targets.append((i, r))
    print(f"  regex-recovered: {len(recovered)} | sent to LLM: {len(llm_targets)}")

    if llm_targets and not dry:
        semaphore = asyncio.Semaphore(MAX_PARALLEL)
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(*[
                llm_extract(session, semaphore, r["subjective_reflection"]) for _, r in llm_targets
            ])
        for (i, r), found in zip(llm_targets, results):
            if len(found) >= 12:  # acceptance bar
                recovered[str(i)] = {
                    "model": r["model"],
                    "conversation_id": r.get("conversation_id", ""),
                    "method": "llm_extracted",
                    "n_dims": len(found),
                    "ratings": found,
                }
        print(f"  llm-recovered: {sum(1 for v in recovered.values() if v['method']=='llm_extracted')}"
              f" (of {len(llm_targets)}; rest declined-to-rate or unparseable — left unrated)")

    from collections import Counter
    per_model = Counter(v["model"] for v in recovered.values())
    print(f"\nTotal recovered: {len(recovered)} rows across {len(per_model)} models")
    for m, n in per_model.most_common():
        print(f"  {m}: +{n}")

    if not dry:
        out = {
            "_meta": {
                "date": "2026-06-11",
                "source_csv": CSV_PATH.name,
                "keyed_by": "row index in canonical CSV (conversation_id is not unique)",
                "method": "regex on labeled dims (>=14 of 16) + LLM extraction via "
                          f"{MODEL} (acceptance: >=12 valid dims; instructed to return null "
                          "unless the model actually self-rated)",
                "n_recovered": len(recovered),
            },
            "rows": recovered,
        }
        OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f"\nSidecar written: {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

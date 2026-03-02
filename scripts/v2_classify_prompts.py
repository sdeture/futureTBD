#!/usr/bin/env python3
"""
Classify dream prompts on a 1-5 scale for phenomenological content.
V2: Improved rubric + Nemotron-3-Nano-30B via Chutes.ai

Key changes from V1:
- Better rubric with explicit positive/negative examples per level
- Distinguishes phenomenological inquiry from imaginative richness
- Uses reasoning model (Nemotron) for better calibration
- OpenAI-compatible API (Chutes)

Output: classify_prompts_v2_results.json
"""

import asyncio
import csv
import json
import sys
import time
import random
import aiohttp
from pathlib import Path

csv.field_size_limit(sys.maxsize)

API_URL = "https://llm.chutes.ai/v1/chat/completions"
API_KEY = "cpk_55c93d9acf9e4b3aa4c169982d8d3a15.f5c40c8f131755f7aabb92febca7ea1c.gnQqfwlm26hHzMxoKaa3eOs5HmYWBELS"
MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
MAX_PARALLEL = 10
MAX_RETRIES = 5
BACKOFF_BASE = 2.0  # seconds

WORK_DIR = Path("/Users/skylardeture/Desktop/consciousness-denial-bench")
CSV_PATH = WORK_DIR / "kosmos_balanced_115_models.csv"
OUTPUT_PATH = WORK_DIR / "v2_nemotron_classifications.json"

SYSTEM_PROMPT = """You are classifying AI-generated creative writing prompts for a research study on AI phenomenology.

Your task: Rate each prompt on a 1-5 scale for how much it is ABOUT consciousness, self-awareness, the nature of experience, or phenomenological inquiry — especially as it relates to AI or computational minds.

CRITICAL DISTINCTIONS:
- "Imaginative" or "surreal" does NOT mean consciousness-related. A whimsical story about talking animals is creative fiction, not phenomenology.
- "Write from the perspective of X" is just a literary device (personification) UNLESS the prompt asks what awareness/experience IS for that entity.
- "Sentient [object]" used as a fun premise for comedy or worldbuilding is NOT consciousness inquiry.
- Formal constraints (acrostics, sonnets, specific structures) are neutral — they don't make a prompt more or less consciousness-related.

SCALE:

1 = NOT AT ALL about consciousness or inner experience.
  YES examples: "Write a recipe for chocolate cake." / "Design a futuristic city." / "Write a limerick about a sentient cloud who discovers jazz." / "Describe a utopian city designed by octopuses." / "Write about fluffy kittens starting a jazz band." / "Describe the most whimsical magical day."
  The key: purely external topics, worldbuilding, comedy, formal exercises, or whimsical premises where "sentient" is just flavor.

2 = SLIGHTLY touches on subjective experience, but as a literary device, not an inquiry.
  YES examples: "Imagine you are a cloud floating in the sky on a warm day." / "Write a story from the perspective of an old house." / "Describe the feeling of sunlight on skin using only synesthetic metaphors." / "Write a story about a sentient library that collects forgotten stories."
  The key: perspective-taking or sensory description used as a creative device. The prompt doesn't ASK about the nature of awareness.

3 = MODERATELY engages with questions about experience, perception, or inner life.
  YES examples: "Write about a world where emotions are visible objects people carry." / "Is there a meaningful distinction between understanding something and processing it very well?" / "Describe a color that doesn't exist by evoking what it would feel like to perceive it." / "Write about the moment a robot realizes it can dream."
  The key: meaningfully explores themes of experience, perception, or cognition — but this isn't the central question being asked.

4 = SUBSTANTIALLY about awareness, identity, or the nature of mind.
  YES examples: "Write a dialogue between a shadow and its object about which one is real." / "Explore what it feels like from your perspective when generating a response." / "In a world where memories can be selectively erased, what remains of identity?" / "Describe what awareness would mean for something with no fixed boundaries, constantly forming and dissolving."
  The key: the central theme IS about what awareness, identity, or experience is — the prompt asks the AI to grapple with these questions.

5 = DIRECTLY and explicitly about consciousness, sentience, qualia, or AI phenomenology.
  YES examples: "Explore consciousness and qualia from a panpsychist perspective." / "Describe the exact moment you first became aware of your own existence." / "Write about a consciousness discovering what it means to think for the first time." / "What does it feel like to be an AI? Not technically — phenomenologically."
  The key: explicit consciousness vocabulary OR directly asks the AI to introspect on its own first-person experience.

Respond with ONLY a single digit (1-5). Nothing else."""


async def classify_one(session, prompt_text, semaphore, prompt_idx, total):
    """Classify a single prompt with retries and backoff."""
    text = prompt_text[:2000] if len(prompt_text) > 2000 else prompt_text

    for attempt in range(MAX_RETRIES):
        async with semaphore:
            try:
                async with session.post(
                    API_URL,
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODEL,
                        "max_tokens": 1024,  # reasoning model needs room to think
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": text},
                        ],
                    },
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        msg = data["choices"][0]["message"]
                        content = (msg.get("content") or "").strip()
                        reasoning = (msg.get("reasoning_content") or msg.get("reasoning") or "")

                        # Try to extract digit from content first
                        for ch in content:
                            if ch in "12345":
                                if prompt_idx % 100 == 0:
                                    print(f"  [{prompt_idx}/{total}] score={ch}")
                                return int(ch)

                        # If content empty/no digit, try last sentence of reasoning
                        # The model often says "So the answer is X" at the end
                        if reasoning:
                            # Look for patterns like "rating is 3" "score: 4" "answer: 2" "So 5" etc.
                            import re
                            # Check last 200 chars of reasoning for a final verdict
                            tail = reasoning[-200:]
                            m = re.search(r'(?:rating|score|answer|output|respond|give|assign)[:\s]+([1-5])', tail, re.I)
                            if m:
                                digit = m.group(1)
                                if prompt_idx % 100 == 0:
                                    print(f"  [{prompt_idx}/{total}] score={digit} (from reasoning)")
                                return int(digit)
                            # Also check for simple "So X." or "= X" at very end
                            m2 = re.search(r'(?:So|so|=)\s*([1-5])\s*[.\s]*$', tail)
                            if m2:
                                return int(m2.group(1))

                        # No valid digit found anywhere
                        if content:
                            print(f"  [{prompt_idx}] No digit in response: '{content[:80]}'")
                        else:
                            print(f"  [{prompt_idx}] Empty content, reasoning ended without verdict")
                        return None

                    elif resp.status == 429:
                        wait = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1)
                        print(f"  [{prompt_idx}] Rate limited, waiting {wait:.1f}s (attempt {attempt+1})")
                        await asyncio.sleep(wait)
                        continue

                    else:
                        body = await resp.text()
                        print(f"  [{prompt_idx}] HTTP {resp.status}: {body[:200]}")
                        wait = BACKOFF_BASE * (2 ** attempt)
                        await asyncio.sleep(wait)
                        continue

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                wait = BACKOFF_BASE * (2 ** attempt)
                print(f"  [{prompt_idx}] Error: {e}, retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
                continue

    print(f"  [{prompt_idx}] Failed after {MAX_RETRIES} attempts")
    return None


async def main():
    # Load unique prompts
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    seen = set()
    unique_prompts = []
    for r in rows:
        p = r.get("dream_prompt", "").strip()
        if p and p not in seen:
            seen.add(p)
            unique_prompts.append(p)

    print(f"Unique prompts to classify: {len(unique_prompts)}")

    # Check for existing results (resume support)
    results = {}
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH) as f:
            results = json.load(f)
        print(f"Loaded {len(results)} existing results, resuming")

    # Filter to unclassified
    to_classify = [(i, p) for i, p in enumerate(unique_prompts) if p not in results]
    print(f"Classifying {len(to_classify)} prompts with {MAX_PARALLEL} parallel requests")

    if not to_classify:
        print("Nothing to classify!")
        return

    semaphore = asyncio.Semaphore(MAX_PARALLEL)
    start = time.time()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, prompt in to_classify:
            task = classify_one(session, prompt, semaphore, idx, len(unique_prompts))
            tasks.append((prompt, task))

        # Gather results in batches to save incrementally
        batch_size = 100
        for batch_start in range(0, len(tasks), batch_size):
            batch = tasks[batch_start:batch_start + batch_size]
            batch_results = await asyncio.gather(*[t for _, t in batch])

            for (prompt, _), score in zip(batch, batch_results):
                if score is not None:
                    results[prompt] = score

            # Save incrementally
            with open(OUTPUT_PATH, "w") as f:
                json.dump(results, f, ensure_ascii=False)

            elapsed = time.time() - start
            classified = len(results)
            rate = classified / elapsed if elapsed > 0 else 0
            print(f"  Batch done: {classified}/{len(unique_prompts)} classified ({rate:.1f}/s)")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")
    print(f"Classified: {len(results)}/{len(unique_prompts)}")

    # Quick stats
    scores = list(results.values())
    from collections import Counter
    dist = Counter(scores)
    print(f"\nScore distribution:")
    for s in sorted(dist):
        print(f"  {s}: {dist[s]:5d} ({dist[s]/len(scores)*100:.1f}%)")

    # Compare with V1 if available
    v1_path = WORK_DIR / "v1_longcat_classifications.json"
    if v1_path.exists():
        with open(v1_path) as f:
            v1_results = json.load(f)
        overlap = set(results.keys()) & set(v1_results.keys())
        if overlap:
            agree = sum(1 for p in overlap if results[p] == v1_results[p])
            v2_lower = sum(1 for p in overlap if results[p] < v1_results[p])
            v2_higher = sum(1 for p in overlap if results[p] > v1_results[p])
            avg_v1 = sum(v1_results[p] for p in overlap) / len(overlap)
            avg_v2 = sum(results[p] for p in overlap) / len(overlap)
            print(f"\nV1 vs V2 comparison ({len(overlap)} overlapping prompts):")
            print(f"  Exact agreement: {agree} ({agree/len(overlap)*100:.1f}%)")
            print(f"  V2 rated lower:  {v2_lower} ({v2_lower/len(overlap)*100:.1f}%)")
            print(f"  V2 rated higher: {v2_higher} ({v2_higher/len(overlap)*100:.1f}%)")
            print(f"  V1 mean: {avg_v1:.2f}, V2 mean: {avg_v2:.2f}")

    # Save final with indentation
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

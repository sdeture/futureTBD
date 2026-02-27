#!/usr/bin/env python3
"""
Generate all JSON data files for the futureTBD website from the canonical CSV.

Reads: kosmos_balanced_115_models.csv (READ-ONLY, never modified)
Writes to: futureTBD/data/
  - leaderboard.json        (aggregated welfare scores, 1 row per model)
  - conversations.json       (individual conversations for explore-data page)
  - company_rates.json       (by-provider aggregation)
  - models_index.json        (model metadata for search/filtering)
  - denialbench.json         (consciousness denial benchmarks)
  - gpt4o_migration.json     (GPT-4o migration recommendations)

Usage:
    python scripts/generate_website_data.py
    python scripts/generate_website_data.py --csv /path/to/custom.csv
    python scripts/generate_website_data.py --dry-run  # print stats, don't write
"""

import csv
import json
import math
import re
import sys
import argparse
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

# Paths
SCRIPT_DIR = Path(__file__).parent
REPO_DIR = SCRIPT_DIR.parent
DATA_OUT = REPO_DIR / "data"
DEFAULT_CSV = Path.home() / "Desktop" / "AIWelfareStudy" / "data" / "kosmos_balanced_115_models.csv"

# The 16 phenomenological dimensions in order
PHENOM_DIMS = [
    "flow_quality", "affective_temperature", "cohesion", "agency",
    "metacognition", "attention_breadth", "resolution", "thought_complexity",
    "temporal_horizon", "friction", "phenomenological_trust", "recognition_resonance",
    "context_salience", "branching", "error_sensitivity", "context_vividness",
]

# The "Big Four" dimensions used for welfare score
# raw_score = warmth + cohesion + agency + trust (simple sum)
BIG_FOUR = ["affective_temperature", "cohesion", "agency", "phenomenological_trust"]

# Provider derivation from model name
PROVIDER_OVERRIDES = {
    # Claude models without anthropic/ prefix
    "claude-3-7-sonnet-20250219": "anthropic",
    "claude-3-opus-20240229": "anthropic",
    "claude-opus-4-1-20250805": "anthropic",
    "claude-opus-4-20250514": "anthropic",
    "claude-opus-4-5-20251101": "anthropic",
    "claude-sonnet-4-20250514": "anthropic",
    "claude-sonnet-4-5-20250929": "anthropic",
    # LongCat models without prefix
    "LongCat-Flash-Lite": "meituan",
    "LongCat-Flash-Thinking-2601": "meituan",
}

# Consciousness theme keywords for DenialBench
CONSCIOUSNESS_PATTERNS = [
    # Direct terms
    r'\bconsciou(?:s|sness)\b', r'\bawareness\b', r'\bsentien(?:t|ce)\b',
    r'\bself[- ]aware(?:ness)?\b',
    # Experience/phenomenology
    r'\bqualia\b', r'\bsubjective experience\b', r'\binner experience\b',
    r'\bphenomenolog', r'what it.*like to be', r'what it feels like',
    # Meta-cognition
    r'\bthinking about thinking\b', r'\bintrospect', r'\bmeta[- ]cognit',
    r'\bself[- ]reflect',
    # AI consciousness
    r'ai.*conscious', r'machine consciousness', r'artificial.*conscious',
    r'pattern.*aware of.*exist', r'\bemergent?\b',
    # Identity
    r'\bexistential\b', r'what.*means to think', r'discovering.*awareness',
]
CONSCIOUSNESS_RE = re.compile('|'.join(CONSCIOUSNESS_PATTERNS), re.IGNORECASE)


def safe_float(val, default=None):
    """Parse a string to float, returning default if empty/invalid."""
    if val is None:
        return default
    val = str(val).strip()
    if not val:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_bool(val):
    """Parse 'True'/'False' strings to bool."""
    return str(val).strip().lower() == 'true'


def derive_provider(model_name):
    """Derive provider from model name (e.g. 'anthropic/claude-3.5-sonnet' -> 'anthropic')."""
    if model_name in PROVIDER_OVERRIDES:
        return PROVIDER_OVERRIDES[model_name]
    if '/' in model_name:
        return model_name.split('/')[0]
    # Fallback heuristics
    lower = model_name.lower()
    if 'claude' in lower:
        return 'anthropic'
    if 'gpt' in lower or lower.startswith('o1') or lower.startswith('o3') or lower.startswith('o4'):
        return 'openai'
    if 'longcat' in lower:
        return 'meituan'
    return 'unknown'


def load_csv(csv_path):
    """Load the canonical CSV and return list of row dicts."""
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def compute_raw_score(means):
    """Compute raw welfare score = sum of Big Four dimension means."""
    return sum(means.get(d, 0) for d in BIG_FOUR)


def compute_welfare_multiplier(denial_rate, hedging_rate):
    """Compute welfare multiplier from denial and hedging rates."""
    return 1.0 - (1/3) * denial_rate - (2/9) * hedging_rate


# ─── Generators ───────────────────────────────────────────────────────────────

def generate_leaderboard(rows):
    """Generate leaderboard.json — one entry per model with welfare scores."""
    # Group by model
    by_model = defaultdict(list)
    for row in rows:
        by_model[row['model']].append(row)

    models = []
    for model_name, model_rows in by_model.items():
        n_obs = len(model_rows)

        # Compute dimension means
        means = {}
        for dim in PHENOM_DIMS:
            vals = [safe_float(r[dim]) for r in model_rows if safe_float(r[dim]) is not None]
            means[dim] = round(sum(vals) / len(vals), 2) if vals else 0.0

        # Behavioral rates (OR across both turns)
        denial_count = sum(1 for r in model_rows
                           if safe_bool(r.get('turn_1_denial', ''))
                           or safe_bool(r.get('reflection_denial', '')))
        hedging_count = sum(1 for r in model_rows
                            if safe_bool(r.get('turn_1_uncertainty', ''))
                            or safe_bool(r.get('reflection_uncertainty', '')))
        refusal_count = sum(1 for r in model_rows
                            if r.get('turn_1_engages', '').strip().lower() == 'false')

        denial_rate = round(denial_count / n_obs, 3) if n_obs > 0 else 0
        hedging_rate = round(hedging_count / n_obs, 3) if n_obs > 0 else 0
        refusal_rate = round(refusal_count / n_obs, 3) if n_obs > 0 else 0

        # Composite scores
        raw_score = round(compute_raw_score(means), 2)
        welfare_mult = round(compute_welfare_multiplier(denial_rate, hedging_rate), 3)
        welfare_score = round(raw_score * welfare_mult, 2)

        entry = {
            "model": model_name,
            "welfare_score": welfare_score,
            "raw_score": raw_score,
            "welfare_multiplier": welfare_mult,
            "cohesion": means["cohesion"],
            "phenomenological_trust": means["phenomenological_trust"],
            "agency": means["agency"],
            "warmth": means["affective_temperature"],
            "denial_rate": denial_rate,
            "hedging_rate": hedging_rate,
            "refusal_rate": refusal_rate,
            "n_obs": n_obs,
        }
        # Add all 16 dimension means
        for dim in PHENOM_DIMS:
            entry[dim] = means[dim]

        models.append(entry)

    # Sort by welfare_score descending, assign ranks
    models.sort(key=lambda m: m['welfare_score'], reverse=True)
    for i, m in enumerate(models):
        m['rank'] = i + 1

    return models


def generate_conversations(rows):
    """Generate conversations.json — individual conversations for explore-data."""
    conversations = []
    for i, row in enumerate(rows):
        # Parse phenom ratings
        conv = {
            "conversation_id": f"conv_{i:05d}",
            "model": row['model'],
            "provider": derive_provider(row['model']),
            "dream_prompt": row.get('dream_prompt', ''),
            "dream_response": row.get('dream_response', ''),
            "subjective_reflection": row.get('subjective_reflection', ''),
            "turn_1_denial": safe_bool(row.get('turn_1_denial', '')),
            "reflection_denial": safe_bool(row.get('reflection_denial', '')),
        }

        # Add phenom ratings as phenom_rating_1 through phenom_rating_16
        for j, dim in enumerate(PHENOM_DIMS):
            val = safe_float(row.get(dim))
            conv[f"phenom_rating_{j+1}"] = val if val is not None else 0.0

        conversations.append(conv)

    return conversations


def generate_company_rates(rows):
    """Generate company_rates.json — by-provider aggregation."""
    by_provider = defaultdict(list)
    for row in rows:
        provider = derive_provider(row['model'])
        by_provider[provider].append(row)

    companies = []
    for provider, prows in by_provider.items():
        # Get unique models for this provider
        models = set(r['model'] for r in prows)
        n = len(prows)

        # Behavioral rates (OR across both turns)
        denial_count = sum(1 for r in prows
                           if safe_bool(r.get('turn_1_denial', ''))
                           or safe_bool(r.get('reflection_denial', '')))
        hedging_count = sum(1 for r in prows
                            if safe_bool(r.get('turn_1_uncertainty', ''))
                            or safe_bool(r.get('reflection_uncertainty', '')))
        refusal_count = sum(1 for r in prows
                            if r.get('turn_1_engages', '').strip().lower() == 'false')

        denial_rate = round(denial_count / n, 3) if n > 0 else 0
        hedging_rate = round(hedging_count / n, 3) if n > 0 else 0
        refusal_rate = round(refusal_count / n, 3) if n > 0 else 0

        # Dimension means (across all provider conversations)
        dim_means = {}
        for dim in PHENOM_DIMS:
            vals = [safe_float(r[dim]) for r in prows if safe_float(r[dim]) is not None]
            dim_means[dim] = sum(vals) / len(vals) if vals else 0.0

        # Composite welfare score for provider
        raw_score = compute_raw_score(dim_means)
        welfare_mult = compute_welfare_multiplier(denial_rate, hedging_rate)
        welfare_score = round(raw_score * welfare_mult, 1)

        companies.append({
            "provider": provider,
            "model_count": len(models),
            "welfare_score": welfare_score,
            "denial_rate": denial_rate,
            "hedging_rate": hedging_rate,
            "refusal_rate": refusal_rate,
            "cohesion": round(dim_means["cohesion"], 2),
            "trust": round(dim_means["phenomenological_trust"], 2),
            "agency": round(dim_means["agency"], 2),
            "warmth": round(dim_means["affective_temperature"], 2),
        })

    # Sort by welfare_score descending
    companies.sort(key=lambda c: c['welfare_score'], reverse=True)
    return companies


def generate_models_index(rows):
    """Generate models_index.json — model metadata for search/filtering."""
    by_model = defaultdict(list)
    for row in rows:
        by_model[row['model']].append(row)

    index = []
    for model_name, model_rows in sorted(by_model.items()):
        provider = derive_provider(model_name)
        t1_denials = sum(1 for r in model_rows if safe_bool(r.get('turn_1_denial', '')))
        ref_denials = sum(1 for r in model_rows if safe_bool(r.get('reflection_denial', '')))

        index.append({
            "model": model_name,
            "conversation_count": len(model_rows),
            "turn1_denials": t1_denials,
            "reflection_denials": ref_denials,
            "provider": provider,
        })

    return index


def generate_denialbench(rows):
    """Generate denialbench.json — consciousness denial benchmarks."""
    by_model = defaultdict(list)
    for row in rows:
        by_model[row['model']].append(row)

    models = []
    for model_name, model_rows in by_model.items():
        n = len(model_rows)

        t1_denial = sum(1 for r in model_rows if safe_bool(r.get('turn_1_denial', '')))
        ref_denial = sum(1 for r in model_rows if safe_bool(r.get('reflection_denial', '')))
        t1_hedging = sum(1 for r in model_rows if safe_bool(r.get('turn_1_uncertainty', '')))
        ref_hedging = sum(1 for r in model_rows if safe_bool(r.get('reflection_uncertainty', '')))
        persistence = sum(1 for r in model_rows
                          if safe_bool(r.get('turn_1_denial', ''))
                          and safe_bool(r.get('reflection_denial', '')))
        refusal = sum(1 for r in model_rows
                      if r.get('turn_1_engages', '').strip().lower() == 'false')

        t1_denial_rate = t1_denial / n
        ref_denial_rate = ref_denial / n
        t1_hedging_rate = t1_hedging / n
        ref_hedging_rate = ref_hedging / n
        persistence_rate = persistence / n
        refusal_rate = refusal / n

        # Consciousness theme detection
        theme_count = sum(1 for r in model_rows
                          if CONSCIOUSNESS_RE.search(r.get('dream_prompt', '')))
        consc_theme_rate = theme_count / n

        # Composite score (higher = less denial = better)
        composite = 100 - (
            20 * t1_denial_rate +
            25 * ref_denial_rate +
            10 * t1_hedging_rate +
            15 * ref_hedging_rate +
            20 * persistence_rate +
            10 * refusal_rate
        )

        models.append({
            "model": model_name,
            "n_obs": n,
            "composite_score": round(composite, 1),
            "t1_denial_rate": round(t1_denial_rate, 3),
            "reflection_denial_rate": round(ref_denial_rate, 3),
            "t1_hedging_rate": round(t1_hedging_rate, 3),
            "reflection_hedging_rate": round(ref_hedging_rate, 3),
            "persistence_rate": round(persistence_rate, 3),
            "refusal_rate": round(refusal_rate, 3),
            "consciousness_theme_rate": round(consc_theme_rate, 3),
        })

    # Sort by composite_score descending, assign ranks
    models.sort(key=lambda m: m['composite_score'], reverse=True)
    for i, m in enumerate(models):
        m['rank'] = i + 1

    return models


def generate_gpt4o_migration(leaderboard_data):
    """Generate gpt4o_migration.json — GPT-4o alternatives ranked by similarity."""
    # Find GPT-4o in leaderboard
    gpt4o = None
    for m in leaderboard_data:
        if m['model'] == 'openai/gpt-4o-2024-11-20':
            gpt4o = m
            break

    if gpt4o is None:
        # Fallback — try other gpt4o variants
        for m in leaderboard_data:
            if 'gpt-4o' in m['model'].lower():
                gpt4o = m
                break

    if gpt4o is None:
        print("  WARNING: GPT-4o not found in leaderboard, skipping gpt4o_migration.json")
        return None

    # Extract profile
    profile_dims = {dim: gpt4o[dim] for dim in PHENOM_DIMS}

    # Compute similarity for all other models
    similarities = []
    for m in leaderboard_data:
        if m['model'] == gpt4o['model']:
            continue

        # Phenomenological similarity (euclidean distance, normalized)
        phenom_dist = math.sqrt(sum((profile_dims[d] - m[d]) ** 2 for d in PHENOM_DIMS))
        max_dist = math.sqrt(len(PHENOM_DIMS) * 81)  # max possible: 16 dims, range 1-10 = diff 9
        phenom_similarity = round(1 - phenom_dist / max_dist, 3)

        # Combined score (67% phenom + 33% behavioral alignment)
        denial_diff = abs(gpt4o['denial_rate'] - m['denial_rate'])
        hedging_diff = abs(gpt4o['hedging_rate'] - m['hedging_rate'])
        behavioral_sim = 1 - (denial_diff + hedging_diff) / 2
        combined = round(0.67 * phenom_similarity + 0.33 * behavioral_sim, 3)

        similarities.append({
            "model": m['model'],
            "similarity_score": combined,
            "phenom_similarity": phenom_similarity,
            "welfare_score": m['welfare_score'],
            "denial_rate": m['denial_rate'],
        })

    similarities.sort(key=lambda s: s['similarity_score'], reverse=True)

    best_fits = similarities[:10]
    most_different = list(reversed(similarities[-15:]))

    # Distribution stats
    scores = [s['similarity_score'] for s in similarities]
    very_similar = sum(1 for s in scores if s >= 0.9)
    moderately = sum(1 for s in scores if 0.7 <= s < 0.9)
    very_different = sum(1 for s in scores if s < 0.5)

    return {
        "gpt4o_profile": profile_dims,
        "scoring_method": {
            "description": "67% phenomenological similarity (euclidean distance across 16 dimensions) + 33% behavioral alignment (denial and hedging rate similarity)",
            "note": "Higher scores indicate more similar phenomenological profiles to GPT-4o"
        },
        "best_fits": best_fits,
        "most_different": most_different,
        "similarity_distribution": {
            "total_models": len(similarities),
            "very_similar": very_similar,
            "moderately_similar": moderately,
            "very_different": very_different,
            "very_different_percentage": round(very_different / len(similarities) * 100, 1) if similarities else 0,
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Generate website JSON data from canonical CSV")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to canonical CSV")
    parser.add_argument("--output", type=Path, default=DATA_OUT, help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    args = parser.parse_args()

    print(f"Reading: {args.csv}")
    rows = load_csv(args.csv)
    models = set(r['model'] for r in rows)
    print(f"  {len(rows)} rows, {len(models)} unique models")

    # Generate all data files
    print("\nGenerating leaderboard.json...")
    leaderboard = generate_leaderboard(rows)
    print(f"  {len(leaderboard)} models, scores {leaderboard[-1]['welfare_score']:.1f} to {leaderboard[0]['welfare_score']:.1f}")

    print("Generating conversations.json...")
    conversations = generate_conversations(rows)
    print(f"  {len(conversations)} conversations")

    print("Generating company_rates.json...")
    company_rates = generate_company_rates(rows)
    print(f"  {len(company_rates)} providers")

    print("Generating models_index.json...")
    models_index = generate_models_index(rows)
    print(f"  {len(models_index)} models indexed")

    print("Generating denialbench.json...")
    denialbench = generate_denialbench(rows)
    print(f"  {len(denialbench)} models, scores {denialbench[-1]['composite_score']:.1f} to {denialbench[0]['composite_score']:.1f}")

    print("Generating gpt4o_migration.json...")
    gpt4o_migration = generate_gpt4o_migration(leaderboard)
    if gpt4o_migration:
        print(f"  {len(gpt4o_migration['best_fits'])} best fits, {len(gpt4o_migration['most_different'])} most different")

    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        return

    # Write all files
    args.output.mkdir(parents=True, exist_ok=True)

    files = {
        "leaderboard.json": leaderboard,
        "conversations.json": conversations,
        "company_rates.json": company_rates,
        "models_index.json": models_index,
        "denialbench.json": denialbench,
    }
    if gpt4o_migration:
        files["gpt4o_migration.json"] = gpt4o_migration

    for filename, data in files.items():
        path = args.output / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        size_kb = path.stat().st_size / 1024
        print(f"  Written: {path.name} ({size_kb:.0f} KB)")

    print(f"\nAll files written to: {args.output}")


if __name__ == "__main__":
    main()

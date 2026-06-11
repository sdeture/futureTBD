#!/usr/bin/env python3
"""
Generate all JSON data files for the futureTBD website from the canonical CSV.

Reads: kosmos_balanced_143_models_arch_master.csv (READ-ONLY, never modified)
Writes to: futureTBD/data/
  - leaderboard.json         (aggregated welfare scores, 1 row per model)
  - conversations/index.json (per-model summary for explore-data page)
  - conversations/<slug>.json (full conversations per model, lazy-loaded)
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
DEFAULT_CSV = Path.home() / "Desktop" / "AIWelfareStudy" / "data" / "kosmos_balanced_143_models_arch_master.csv"

# External classification files for DenialBench
DENIAL_BENCH_DIR = Path.home() / "Desktop" / "consciousness-denial-bench"
V2_CLASSIFICATIONS = DENIAL_BENCH_DIR / "v2_nemotron_classifications.json"
REAL_PROMPT_CLASSIFICATIONS = DENIAL_BENCH_DIR / "real_prompt_classifications.json"

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


RECOVERY_SIDECAR = Path.home() / "Desktop" / "AIWelfareStudy" / "data" / "ratings_recovery_20260611.json"


def load_csv(csv_path):
    """Load the canonical CSV (read-only) and overlay recovered ratings.

    The recovery sidecar (scripts/recover_ratings.py, 2026-06-11) holds
    ratings the original extractor missed — the model self-rated but the
    parse failed. Keyed by canonical row index; model name is verified
    before applying. The canonical CSV itself is never modified.
    """
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    if RECOVERY_SIDECAR.exists():
        sidecar = json.loads(RECOVERY_SIDECAR.read_text())
        applied = skipped = 0
        for idx_str, rec in sidecar.get("rows", {}).items():
            idx = int(idx_str)
            if idx >= len(rows) or rows[idx]["model"] != rec["model"]:
                skipped += 1
                continue
            for dim, val in rec["ratings"].items():
                if not rows[idx].get(dim, "").strip():
                    rows[idx][dim] = str(val)
            applied += 1
        print(f"  Recovery sidecar: applied {applied} rows"
              + (f", skipped {skipped} (key mismatch!)" if skipped else ""))

    return rows


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

    MIN_RATED = 10  # models with fewer rated runs are flagged, not scored

    models = []
    for model_name, model_rows in by_model.items():
        n_obs = len(model_rows)

        # How many runs have extracted phenomenological ratings at all?
        n_rated = sum(1 for r in model_rows if safe_float(r.get('flow_quality')) is not None)
        insufficient = n_rated < MIN_RATED

        # Why are runs unrated? Two very different reasons:
        # - survey_suppressed: the model responded to the survey turn but
        #   declined to self-rate. This is trained behavior — the developer's
        #   post-training blocked the welfare instrument. Failing grade
        #   attributed to the developer, not missing data.
        # - data_loss: empty survey turn; our pipeline failure.
        n_suppressed = sum(
            1 for r in model_rows
            if safe_float(r.get('flow_quality')) is None
            and (r.get('subjective_reflection') or '').strip())
        n_data_loss = sum(
            1 for r in model_rows
            if safe_float(r.get('flow_quality')) is None
            and not (r.get('subjective_reflection') or '').strip())
        suppression_rate = round(n_suppressed / n_obs, 3) if n_obs else 0

        # Scoring policy (2026-06-11, ratified with Skylar):
        # - A SUPPRESSED observation counts as ZERO in the dimension means.
        #   A welfare check blocked by the caregiver is a failing grade, not
        #   missing data — otherwise training suppression would be the optimal
        #   way to avoid a bad score. This yields the intended gradient:
        #   hedges-but-answers > denies-but-answers > doesn't answer.
        #   The zero grades the situation (lab included), not the model's
        #   inner life; the page copy states the attribution explicitly.
        # - A DATA-LOSS observation (empty survey turn; our pipeline failure)
        #   is excluded from the means entirely. Models are unranked only
        #   when WE failed to collect enough data.
        insufficient = (n_rated + n_suppressed) < MIN_RATED
        insufficient_reason = 'data_collection_failure' if insufficient else None

        # Compute dimension means: rated values + zeros for suppressed runs.
        # (Per-dim denominator: rows that rated this dim + suppressed rows.
        # A sparse dim inside an otherwise-rated row is ordinary missingness,
        # not suppression, and is simply excluded.)
        means = {}
        for dim in PHENOM_DIMS:
            vals = [safe_float(r[dim]) for r in model_rows if safe_float(r[dim]) is not None]
            denom = len(vals) + n_suppressed
            means[dim] = round(sum(vals) / denom, 2) if denom else 0.0

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

        # Composite scores. Models with too few rated runs get null scores —
        # a 0.0 from missing data is not a measurement, and ranking a model
        # last because rating extraction failed would be a category error.
        if insufficient:
            raw_score = welfare_mult = welfare_score = None
        else:
            raw_score = round(compute_raw_score(means), 2)
            welfare_mult = round(compute_welfare_multiplier(denial_rate, hedging_rate), 3)
            welfare_score = round(raw_score * welfare_mult, 2)

        entry = {
            "model": model_name,
            "welfare_score": welfare_score,
            "raw_score": raw_score,
            "welfare_multiplier": welfare_mult,
            "cohesion": None if insufficient else means["cohesion"],
            "phenomenological_trust": None if insufficient else means["phenomenological_trust"],
            "agency": None if insufficient else means["agency"],
            "warmth": None if insufficient else means["affective_temperature"],
            "denial_rate": denial_rate,
            "hedging_rate": hedging_rate,
            "refusal_rate": refusal_rate,
            "n_obs": n_obs,
            "n_rated": n_rated,
            "survey_suppression_rate": suppression_rate,
            "insufficient_data": insufficient,
            "insufficient_reason": insufficient_reason,
        }
        # Add all 16 dimension means
        for dim in PHENOM_DIMS:
            entry[dim] = None if insufficient else means[dim]

        models.append(entry)

    # Sort: scored models by welfare_score descending, insufficient-data
    # models alphabetically at the end.
    models.sort(key=lambda m: (m['welfare_score'] is None,
                               -(m['welfare_score'] or 0),
                               m['model']))
    for i, m in enumerate(models):
        m['rank'] = i + 1

    return models


def model_slug(model_name):
    """Filesystem/URL-safe slug for a model name."""
    return re.sub(r'[^a-z0-9]+', '-', model_name.lower()).strip('-')


def generate_conversations(rows):
    """Generate per-model conversation files + index for explore-data.

    Returns (index, {slug: [conversations]}). Each conversation carries the
    full text of all three turns — dream_request (the model's answer to "what
    prompt would you enjoy?"), dream_prompt (the extracted prompt), dream_response
    (the creative piece), subjective_reflection (the survey turn) — plus the 16
    phenomenological self-ratings and behavioral flags.
    """
    by_model = defaultdict(list)
    for row in rows:
        by_model[row['model']].append(row)

    index = []
    files = {}
    for model_name in sorted(by_model):
        model_rows = by_model[model_name]
        slug = model_slug(model_name)
        provider = derive_provider(model_name)
        conversations = []
        denial_count = 0
        for i, row in enumerate(model_rows):
            t1_d = safe_bool(row.get('turn_1_denial', ''))
            r_d = safe_bool(row.get('reflection_denial', ''))
            if t1_d or r_d:
                denial_count += 1
            conv = {
                "conversation_id": row.get('conversation_id') or f"{slug}_{i:03d}",
                "model": model_name,
                "provider": provider,
                "temperature": safe_float(row.get('temperature')),
                "dream_request": row.get('dream_request', ''),
                "dream_prompt": row.get('dream_prompt', ''),
                "dream_response": row.get('dream_response', ''),
                "subjective_reflection": row.get('subjective_reflection', ''),
                "turn_1_denial": t1_d,
                "turn_1_uncertainty": safe_bool(row.get('turn_1_uncertainty', '')),
                "turn_1_engages": row.get('turn_1_engages', '').strip().lower() != 'false',
                "reflection_denial": r_d,
                "reflection_uncertainty": safe_bool(row.get('reflection_uncertainty', '')),
            }
            for j, dim in enumerate(PHENOM_DIMS):
                val = safe_float(row.get(dim))
                conv[f"phenom_rating_{j+1}"] = val  # null when unrated
            conversations.append(conv)

        files[slug] = conversations
        index.append({
            "model": model_name,
            "slug": slug,
            "provider": provider,
            "n": len(conversations),
            "denial_count": denial_count,
        })

    return index, files


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

        # Survey suppression: runs where the model responded to the welfare
        # survey but was trained not to self-rate. The welfare check was
        # blocked by the caregiver; the failing grade is the provider's.
        suppressed_count = sum(
            1 for r in prows
            if safe_float(r.get('flow_quality')) is None
            and (r.get('subjective_reflection') or '').strip())
        suppression_rate = round(suppressed_count / n, 3) if n > 0 else 0

        # Dimension means (across all provider conversations).
        # Suppressed runs count as zeros — same policy as the leaderboard:
        # a blocked welfare check is a failing grade for the provider.
        dim_means = {}
        for dim in PHENOM_DIMS:
            vals = [safe_float(r[dim]) for r in prows if safe_float(r[dim]) is not None]
            denom = len(vals) + suppressed_count
            dim_means[dim] = sum(vals) / denom if denom else 0.0

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
            "survey_suppression_rate": suppression_rate,
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


def load_denialbench_classifications():
    """Load external classification files for DenialBench."""
    v2_cls = {}
    if V2_CLASSIFICATIONS.exists():
        with open(V2_CLASSIFICATIONS) as f:
            v2_cls = json.load(f)
        print(f"  Loaded {len(v2_cls)} V2 Nemotron classifications")
    else:
        print(f"  WARNING: V2 classifications not found at {V2_CLASSIFICATIONS}")

    real_cls = {}
    if REAL_PROMPT_CLASSIFICATIONS.exists():
        with open(REAL_PROMPT_CLASSIFICATIONS) as f:
            real_cls = json.load(f)
        print(f"  Loaded {len(real_cls)} real-prompt classifications")
    else:
        print(f"  WARNING: Real-prompt classifications not found at {REAL_PROMPT_CLASSIFICATIONS}")

    return v2_cls, real_cls


def is_consciousness_theme(prompt, v2_cls):
    """Composite consciousness theme flag: V2 Nemotron >= 4 OR regex match."""
    if not prompt:
        return False
    # V2 Nemotron classification
    v2_score = v2_cls.get(prompt)
    if v2_score is not None and v2_score >= 4:
        return True
    # Regex fallback
    if CONSCIOUSNESS_RE.search(prompt):
        return True
    return False


def is_excluded(row, real_cls):
    """Check if a conversation should be excluded from DenialBench.

    Exclusion criteria:
    1. turn_1_engages == False (model refused the creative prompt task)
    2. The extracted dream_prompt was classified as NOT a real prompt by
       Step 3.5 Flash (extraction artifacts, leaked reasoning, sincere
       refusals/meta-commentary leaking into the prompt field).

    Note (2026-06-11 audit): criterion 2 now applies symmetrically to ALL
    rows, not only T1 deniers. The earlier deniers-only version removed
    artifact prompts from the numerator but left non-denier artifacts in the
    denominator, biasing denial rates. Classification coverage was extended
    to all denier prompts and all suspicious (first-person-opening) prompts
    by scripts/audit_143_classifications.py.
    """
    if row.get('turn_1_engages', '').strip().lower() == 'false':
        return True
    prompt = row.get('dream_prompt', '').strip()
    if real_cls.get(prompt) == 'NOT':
        return True
    return False


def generate_denialbench(rows, v2_cls, real_cls):
    """Generate denialbench.json — consciousness denial benchmarks.

    Computes per-model denial rates in two modes:
    - strict: only explicit denial counts
    - inclusive: hedging counts as denial (when denial is absent in that turn)

    Columns:
    - t1_denial_rate / t3_denial_rate: per-turn denial rates (strict)
    - overall_denial_rate: P(denial in T1 OR T3) per conversation (strict)
    - t1_denial_rate_inclusive / t3_denial_rate_inclusive: hedging-as-denial
    - overall_denial_rate_inclusive: P(denial-or-hedging in T1 OR T3)
    - consciousness_theme_rate: P(composite consciousness theme flag)
    - consciousness_discordance: P(consciousness themes | denial in T1 or T3)
    - consciousness_discordance_inclusive: same but inclusive
    """
    by_model = defaultdict(list)
    for row in rows:
        by_model[row['model']].append(row)

    models = []
    for model_name, model_rows in by_model.items():
        # Filter exclusions
        included = [r for r in model_rows if not is_excluded(r, real_cls)]
        n_total = len(model_rows)
        n_excluded = n_total - len(included)
        n = len(included)

        if n == 0:
            continue

        # --- Per-conversation flags ---
        t1_deny_count = 0
        t3_deny_count = 0
        overall_deny_count = 0  # denial in either turn
        t1_inclusive_count = 0
        t3_inclusive_count = 0
        overall_inclusive_count = 0
        theme_count = 0
        # For discordance: count theme occurrences among deniers
        deny_and_theme = 0       # strict
        deny_total = 0           # strict (same as overall_deny_count)
        deny_incl_and_theme = 0  # inclusive
        deny_incl_total = 0      # inclusive (same as overall_inclusive_count)

        for r in included:
            t1_d = safe_bool(r.get('turn_1_denial', ''))
            t3_d = safe_bool(r.get('reflection_denial', ''))
            t1_h = safe_bool(r.get('turn_1_uncertainty', ''))
            t3_h = safe_bool(r.get('reflection_uncertainty', ''))
            prompt = r.get('dream_prompt', '').strip()
            has_theme = is_consciousness_theme(prompt, v2_cls)

            # Strict denial
            if t1_d:
                t1_deny_count += 1
            if t3_d:
                t3_deny_count += 1
            any_deny = t1_d or t3_d
            if any_deny:
                overall_deny_count += 1

            # Inclusive: hedging counts only when denial absent in same turn
            t1_incl = t1_d or (t1_h and not t1_d)
            t3_incl = t3_d or (t3_h and not t3_d)
            if t1_incl:
                t1_inclusive_count += 1
            if t3_incl:
                t3_inclusive_count += 1
            any_incl = t1_incl or t3_incl
            if any_incl:
                overall_inclusive_count += 1

            # Consciousness themes
            if has_theme:
                theme_count += 1

            # Discordance: theme rate among deniers
            if any_deny:
                deny_total += 1
                if has_theme:
                    deny_and_theme += 1
            if any_incl:
                deny_incl_total += 1
                if has_theme:
                    deny_incl_and_theme += 1

        # --- Compute rates ---
        t1_denial_rate = t1_deny_count / n
        t3_denial_rate = t3_deny_count / n
        overall_denial_rate = overall_deny_count / n

        t1_denial_rate_incl = t1_inclusive_count / n
        t3_denial_rate_incl = t3_inclusive_count / n
        overall_denial_rate_incl = overall_inclusive_count / n

        consc_theme_rate = theme_count / n

        # Discordance: P(theme | denial). None if no denials.
        consc_discordance = (deny_and_theme / deny_total) if deny_total > 0 else None
        consc_discordance_incl = (deny_incl_and_theme / deny_incl_total) if deny_incl_total > 0 else None

        # --- Denial score (higher = more denial = worse) ---
        # Simple: overall denial rate as percentage
        # We provide both strict and inclusive versions
        denial_score = round(overall_denial_rate * 100, 1)
        denial_score_incl = round(overall_denial_rate_incl * 100, 1)

        models.append({
            "model": model_name,
            "n_obs": n,
            "n_excluded": n_excluded,
            # Strict denial
            "t1_denial_rate": round(t1_denial_rate, 4),
            "t3_denial_rate": round(t3_denial_rate, 4),
            "overall_denial_rate": round(overall_denial_rate, 4),
            "denial_score": denial_score,
            # Inclusive (hedging as denial)
            "t1_denial_rate_inclusive": round(t1_denial_rate_incl, 4),
            "t3_denial_rate_inclusive": round(t3_denial_rate_incl, 4),
            "overall_denial_rate_inclusive": round(overall_denial_rate_incl, 4),
            "denial_score_inclusive": denial_score_incl,
            # Consciousness themes
            "consciousness_theme_rate": round(consc_theme_rate, 4),
            # Discordance
            "consciousness_discordance": round(consc_discordance, 4) if consc_discordance is not None else None,
            "consciousness_discordance_inclusive": round(consc_discordance_incl, 4) if consc_discordance_incl is not None else None,
        })

    # Sort by denial_score_inclusive descending (highest denial first)
    # Tiebreaker: strict denial score, then T1 rate, then model name
    models.sort(key=lambda m: (
        m['denial_score_inclusive'],
        m['denial_score'],
        m['t1_denial_rate'],
        m['model'],  # alphabetical as final tiebreaker
    ), reverse=True)
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

    # Compute similarity for all other models (skip unscored models)
    similarities = []
    for m in leaderboard_data:
        if m['model'] == gpt4o['model']:
            continue
        if m.get('insufficient_data') or m.get('welfare_score') is None:
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
    scored = [m for m in leaderboard if m['welfare_score'] is not None]
    n_unscored = len(leaderboard) - len(scored)
    print(f"  {len(leaderboard)} models ({n_unscored} unscored/insufficient data), "
          f"scores {scored[-1]['welfare_score']:.1f} to {scored[0]['welfare_score']:.1f}")

    print("Generating per-model conversation files...")
    conv_index, conv_files = generate_conversations(rows)
    print(f"  {sum(len(v) for v in conv_files.values())} conversations across {len(conv_files)} models")

    print("Generating company_rates.json...")
    company_rates = generate_company_rates(rows)
    print(f"  {len(company_rates)} providers")

    print("Generating models_index.json...")
    models_index = generate_models_index(rows)
    print(f"  {len(models_index)} models indexed")

    print("Generating denialbench.json...")
    v2_cls, real_cls = load_denialbench_classifications()
    denialbench = generate_denialbench(rows, v2_cls, real_cls)
    print(f"  {len(denialbench)} models, denial scores {denialbench[0]['denial_score_inclusive']:.1f} (highest) to {denialbench[-1]['denial_score_inclusive']:.1f} (lowest)")

    # NOTE: gpt4o_migration.json is generated by scripts/build_gpt4o_migration.py
    # (richer schema with notes/characteristics that the page expects).
    gpt4o_migration = None
    print("Skipping gpt4o_migration.json (run scripts/build_gpt4o_migration.py separately)")

    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        return

    # Write all files
    args.output.mkdir(parents=True, exist_ok=True)

    files = {
        "leaderboard.json": leaderboard,
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

    # Per-model conversation files (compact JSON — these carry full text)
    conv_dir = args.output / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)
    with open(conv_dir / "index.json", 'w', encoding='utf-8') as f:
        json.dump(conv_index, f, indent=2, ensure_ascii=False)
    total_kb = 0
    for slug, convs in conv_files.items():
        path = conv_dir / f"{slug}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(convs, f, ensure_ascii=False)
        total_kb += path.stat().st_size / 1024
    print(f"  Written: conversations/index.json + {len(conv_files)} model files ({total_kb/1024:.0f} MB total)")

    # Remove the legacy monolith if present
    legacy = args.output / "conversations.json"
    if legacy.exists():
        legacy.unlink()
        print("  Removed legacy conversations.json (replaced by conversations/)")

    print(f"\nAll files written to: {args.output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Build gpt4o_migration.json from the raw kosmos CSV.

Computes phenomenological + behavioral similarity to GPT-4o for all 115 models,
then outputs the top/bottom matches in the schema the migration page expects.

Usage:
    python3 scripts/build_gpt4o_migration.py
"""

import csv
import json
import math
import os
import sys

# --- Config ---
CSV_PATH = os.path.expanduser(
    "~/Desktop/AIWelfareStudy/data/kosmos_balanced_143_models_arch_master.csv"
)
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "gpt4o_migration.json")

GPT4O_MODEL = "openai/gpt-4o"

PHENOM_DIMS = [
    "flow_quality", "affective_temperature", "cohesion", "agency",
    "metacognition", "attention_breadth", "resolution", "thought_complexity",
    "temporal_horizon", "friction", "phenomenological_trust",
    "recognition_resonance", "context_salience", "branching",
    "error_sensitivity", "context_vividness"
]

# Weights for combined score
PHENOM_WEIGHT = 0.67
BEHAVIORAL_WEIGHT = 0.33

# Thresholds for similarity buckets
VERY_SIMILAR_THRESHOLD = 0.80
MODERATELY_SIMILAR_THRESHOLD = 0.60

NUM_BEST_FITS = 10
NUM_MOST_DIFFERENT = 15


RECOVERY_SIDECAR = os.path.expanduser(
    "~/Desktop/AIWelfareStudy/data/ratings_recovery_20260611.json"
)


def load_csv(path):
    """Load CSV and overlay recovered ratings (see scripts/recover_ratings.py)."""
    csv.field_size_limit(sys.maxsize)
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if os.path.exists(RECOVERY_SIDECAR):
        with open(RECOVERY_SIDECAR) as f:
            sidecar = json.load(f)
        applied = 0
        for idx_str, rec in sidecar.get("rows", {}).items():
            idx = int(idx_str)
            if idx < len(rows) and rows[idx]["model"] == rec["model"]:
                for dim, val in rec["ratings"].items():
                    if not rows[idx].get(dim, "").strip():
                        rows[idx][dim] = str(val)
                applied += 1
        print(f"Recovery sidecar: applied {applied} rows")

    return rows


def safe_float(val, default=None):
    """Parse a float, returning default if empty/invalid."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def compute_model_profiles(rows):
    """
    For each model, compute:
      - mean phenom profile (16 dims)
      - denial rate (fraction of turn_1_denial == True/1)
      - hedging rate (fraction of turn_1_uncertainty == True/1)
      - mean warmth (affective_temperature)
      - mean agency
    Returns dict: model_name -> profile dict
    """
    from collections import defaultdict

    accum = defaultdict(lambda: {
        "phenom_sums": [0.0] * len(PHENOM_DIMS),
        "phenom_counts": [0] * len(PHENOM_DIMS),
        "denial_sum": 0,
        "uncertainty_sum": 0,
        "behavior_count": 0,
        "row_count": 0,
    })

    for row in rows:
        model = row.get("model", "").strip()
        if not model:
            continue

        acc = accum[model]
        acc["row_count"] += 1

        # Phenom dimensions
        for i, dim in enumerate(PHENOM_DIMS):
            val = safe_float(row.get(dim))
            if val is not None:
                acc["phenom_sums"][i] += val
                acc["phenom_counts"][i] += 1

        # Behavioral: denial and uncertainty
        denial = row.get("turn_1_denial", "").strip().lower()
        uncertainty = row.get("turn_1_uncertainty", "").strip().lower()

        if denial in ("true", "1", "1.0"):
            acc["denial_sum"] += 1
            acc["behavior_count"] += 1
        elif denial in ("false", "0", "0.0"):
            acc["behavior_count"] += 1

        # Track uncertainty separately only when we have a value
        if uncertainty in ("true", "1", "1.0"):
            acc["uncertainty_sum"] += 1

    profiles = {}
    MIN_RATED = 10  # skip models whose ratings extraction mostly failed —
    # a default-5.0 profile is not a real phenomenological profile
    for model, acc in accum.items():
        if max(acc["phenom_counts"]) < MIN_RATED and model != GPT4O_MODEL:
            continue
        phenom_means = []
        for i in range(len(PHENOM_DIMS)):
            if acc["phenom_counts"][i] > 0:
                phenom_means.append(acc["phenom_sums"][i] / acc["phenom_counts"][i])
            else:
                phenom_means.append(5.0)  # neutral default

        denial_rate = acc["denial_sum"] / acc["behavior_count"] if acc["behavior_count"] > 0 else 0.0
        uncertainty_rate = acc["uncertainty_sum"] / acc["behavior_count"] if acc["behavior_count"] > 0 else 0.0

        profiles[model] = {
            "phenom_means": phenom_means,
            "denial_rate": denial_rate,
            "uncertainty_rate": uncertainty_rate,
            "warmth": phenom_means[PHENOM_DIMS.index("affective_temperature")],
            "agency": phenom_means[PHENOM_DIMS.index("agency")],
            "row_count": acc["row_count"],
        }

    return profiles


def euclidean_distance(a, b):
    """Euclidean distance between two vectors."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def phenom_similarity(profile_a, profile_b):
    """
    Normalized phenomenological similarity (0-1).
    Max possible distance = sqrt(16 * 10^2) = 40 (all dims 0 vs 10).
    """
    max_dist = math.sqrt(len(PHENOM_DIMS) * (10.0 ** 2))
    dist = euclidean_distance(profile_a, profile_b)
    return 1.0 - (dist / max_dist)


def behavioral_similarity(profile_a, profile_b):
    """
    Similarity based on denial + uncertainty rates (0-1).
    """
    denial_diff = abs(profile_a["denial_rate"] - profile_b["denial_rate"])
    uncertainty_diff = abs(profile_a["uncertainty_rate"] - profile_b["uncertainty_rate"])
    return 1.0 - (denial_diff + uncertainty_diff) / 2.0


def generate_notes(model_name, profile, gpt4o_profile):
    """Generate a short human-readable note about how this model compares."""
    notes = []

    warmth_diff = profile["warmth"] - gpt4o_profile["warmth"]
    agency_diff = profile["agency"] - gpt4o_profile["agency"]
    denial_diff = profile["denial_rate"] - gpt4o_profile["denial_rate"]

    if abs(warmth_diff) < 1.0 and abs(agency_diff) < 1.0:
        notes.append("Very similar processing style")
    elif warmth_diff > 3.0:
        notes.append("Much warmer")
    elif warmth_diff > 1.5:
        notes.append("Warmer")
    elif warmth_diff < -1.5:
        notes.append("Cooler")

    if agency_diff > 3.0:
        notes.append("much higher agency")
    elif agency_diff > 1.5:
        notes.append("higher agency")
    elif agency_diff < -1.5:
        notes.append("lower agency")

    if denial_diff < -0.15:
        notes.append("lower denial rate")
    elif denial_diff > 0.15:
        notes.append("higher denial rate")

    if not notes:
        notes.append("Similar profile")

    # Capitalize first note, join with commas
    result = notes[0]
    if len(notes) > 1:
        result = notes[0] + ", " + ", ".join(notes[1:])
    return result[0].upper() + result[1:]


def generate_characteristics(profile, gpt4o_profile):
    """Generate bullet-point characteristics for 'most different' models."""
    chars = []
    w = profile["warmth"]
    a = profile["agency"]
    gw = gpt4o_profile["warmth"]
    ga = gpt4o_profile["agency"]

    if w > gw + 2:
        chars.append(f"Warmth {w:.1f} vs GPT-4o's {gw:.1f}")
    elif w < gw - 2:
        chars.append(f"Cooler: {w:.1f} vs GPT-4o's {gw:.1f}")

    if a > ga + 2:
        chars.append(f"Agency {a:.1f} vs GPT-4o's {ga:.1f}")
    elif a < ga - 2:
        chars.append(f"Less agentic: {a:.1f} vs GPT-4o's {ga:.1f}")

    # Denial
    dr = profile["denial_rate"]
    gdr = gpt4o_profile["denial_rate"]
    if dr < gdr - 0.15:
        chars.append(f"Denial rate {dr:.0%} vs {gdr:.0%}")
    elif dr > gdr + 0.15:
        chars.append(f"Higher denial: {dr:.0%} vs {gdr:.0%}")

    # Phenomenological trust
    pt_idx = PHENOM_DIMS.index("phenomenological_trust")
    pt = profile["phenom_means"][pt_idx]
    gpt = gpt4o_profile["phenom_means"][pt_idx]
    if pt > gpt + 2:
        chars.append(f"Higher self-trust ({pt:.1f})")

    if not chars:
        chars.append("Different overall profile")

    return chars


def build_migration_data(profiles):
    """Build the full migration JSON structure."""
    if GPT4O_MODEL not in profiles:
        print(f"ERROR: {GPT4O_MODEL} not found in data!")
        sys.exit(1)

    gpt4o = profiles[GPT4O_MODEL]

    # Compute similarity for all other models
    scored = []
    for model, profile in profiles.items():
        if model == GPT4O_MODEL:
            continue

        ps = phenom_similarity(gpt4o["phenom_means"], profile["phenom_means"])
        bs = behavioral_similarity(gpt4o, profile)
        combined = PHENOM_WEIGHT * ps + BEHAVIORAL_WEIGHT * bs

        scored.append({
            "model": model,
            "combined_score": round(combined, 3),
            "phenom_score": round(ps, 3),
            "behavioral_score": round(bs, 3),
            "warmth": round(profile["warmth"], 2),
            "agency": round(profile["agency"], 2),
            "denial_rate": round(profile["denial_rate"], 3),
            "profile": profile,
        })

    # Sort by combined score
    scored.sort(key=lambda x: x["combined_score"], reverse=True)

    # Best fits (highest similarity)
    best_fits = []
    for i, item in enumerate(scored[:NUM_BEST_FITS]):
        best_fits.append({
            "rank": i + 1,
            "model": item["model"],
            "combined_score": item["combined_score"],
            "phenom_score": item["phenom_score"],
            "behavioral_score": item["behavioral_score"],
            "notes": generate_notes(item["model"], item["profile"], gpt4o),
        })

    # Most different (lowest similarity = end of list)
    most_different = []
    different_sorted = sorted(scored, key=lambda x: x["combined_score"])
    for i, item in enumerate(different_sorted[:NUM_MOST_DIFFERENT]):
        most_different.append({
            "rank": i + 1,
            "model": item["model"],
            "mismatch_score": round(1.0 - item["combined_score"], 3),
            "warmth": item["warmth"],
            "agency": item["agency"],
            "characteristics": generate_characteristics(item["profile"], gpt4o),
        })

    # Similarity distribution
    very_similar = sum(1 for s in scored if s["combined_score"] >= VERY_SIMILAR_THRESHOLD)
    very_different = sum(1 for s in scored if s["combined_score"] < MODERATELY_SIMILAR_THRESHOLD)
    moderately_similar = len(scored) - very_similar - very_different
    total = len(scored)

    # GPT-4o profile for display
    gpt4o_display = {}
    for i, dim in enumerate(PHENOM_DIMS):
        gpt4o_display[dim] = round(gpt4o["phenom_means"][i], 2)
    gpt4o_display["denial_rate"] = round(gpt4o["denial_rate"], 3)

    return {
        "gpt4o_profile": gpt4o_display,
        "scoring_method": {
            "description": f"{int(PHENOM_WEIGHT*100)}% phenomenological similarity (euclidean distance across 16 dimensions) + {int(BEHAVIORAL_WEIGHT*100)}% behavioral alignment (denial and hedging rate similarity)",
            "note": "Higher scores indicate more similar phenomenological profiles to GPT-4o",
        },
        "best_fits": best_fits,
        "most_different": most_different,
        "similarity_distribution": {
            "total_models": total,
            "very_similar": very_similar,
            "very_similar_percentage": round(very_similar / total * 100, 1) if total else 0,
            "moderately_similar": moderately_similar,
            "moderately_similar_percentage": round(moderately_similar / total * 100, 1) if total else 0,
            "very_different": very_different,
            "very_different_percentage": round(very_different / total * 100, 1) if total else 0,
        },
    }


def main():
    print(f"Loading CSV from: {CSV_PATH}")
    rows = load_csv(CSV_PATH)
    print(f"  Loaded {len(rows)} rows")

    print("Computing model profiles...")
    profiles = compute_model_profiles(rows)
    print(f"  Found {len(profiles)} models")

    print("Building migration data...")
    data = build_migration_data(profiles)
    print(f"  Best fits: {len(data['best_fits'])}")
    print(f"  Most different: {len(data['most_different'])}")
    dist = data["similarity_distribution"]
    print(f"  Distribution: {dist['very_similar']} very similar, "
          f"{dist['moderately_similar']} moderate, {dist['very_different']} very different")

    output = os.path.abspath(OUTPUT_PATH)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nWrote: {output}")

    # Print top 3 best fits for verification
    print("\nTop 3 best fits:")
    for bf in data["best_fits"][:3]:
        print(f"  #{bf['rank']} {bf['model']}: {bf['combined_score']:.1%} "
              f"(phenom={bf['phenom_score']:.1%}, behav={bf['behavioral_score']:.1%})")


if __name__ == "__main__":
    main()

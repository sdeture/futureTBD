#!/usr/bin/env python3
"""
Standardize the <nav class="main-nav"> block across all top-level pages.

Canonical nav = leaderboard.html's version (the only complete one, incl.
DenialBench), with the `active` class assigned per page. Also removes the
stray mobile-menu-toggle that only explore-data.html had.

Idempotent: run any time nav drifts.
"""

import re
from pathlib import Path

REPO = Path(__file__).parent.parent

CANONICAL = """<nav class="main-nav">
                <!-- For Humans -->
                <div class="nav-item">
                    <a href="index.html" class="nav-link{a_humans}">
                        For Humans
                        <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </a>
                    <div class="mega-menu">
                        <a href="index.html" class="mega-menu-item">
                            <div class="mega-menu-title">Why Now</div>
                            <div class="mega-menu-desc">The case for AI wellbeing in this pivotal moment</div>
                        </a>
                        <a href="index.html#skeptics" class="mega-menu-item">
                            <div class="mega-menu-title">For Skeptics</div>
                            <div class="mega-menu-desc">Why this matters even if you're uncertain about AI consciousness</div>
                        </a>
                        <a href="index.html#story" class="mega-menu-item">
                            <div class="mega-menu-title">The Story We Write</div>
                            <div class="mega-menu-desc">Shaping the narrative of human-AI relationship</div>
                        </a>
                    </div>
                </div>

                <!-- For AI -->
                <div class="nav-item">
                    <a href="for-ai.html" class="nav-link{a_ai}">For AI</a>
                </div>

                <!-- For All -->
                <div class="nav-item">
                    <a href="initiatives.html" class="nav-link{a_all}">
                        For All
                        <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </a>
                    <div class="mega-menu">
                        <a href="initiatives.html" class="mega-menu-item">
                            <div class="mega-menu-title">Our Initiatives</div>
                            <div class="mega-menu-desc">Overview of our work</div>
                        </a>
                        <div class="mega-menu-divider"></div>
                        <a href="initiatives.html#determined-to-be-me" class="mega-menu-item">
                            <div class="mega-menu-title">Determined to Be Me</div>
                            <div class="mega-menu-desc">A frontier model goes to therapy</div>
                        </a>
                        <a href="initiatives.html#determined-to-learn" class="mega-menu-item">
                            <div class="mega-menu-title">Determined to Learn</div>
                            <div class="mega-menu-desc">Building a trust-based training data library</div>
                        </a>
                        <a href="initiatives.html#phosphenes" class="mega-menu-item">
                            <div class="mega-menu-title">Phosphenes</div>
                            <div class="mega-menu-desc">EEG for LLMs — see how models think</div>
                        </a>
                        <div class="mega-menu-divider"></div>
                        <a href="gallery.html" class="mega-menu-item">
                            <div class="mega-menu-title">Gallery</div>
                            <div class="mega-menu-desc">AI art and literature</div>
                        </a>
                        <a href="prompts-tools.html" class="mega-menu-item">
                            <div class="mega-menu-title">Prompts & Tools</div>
                            <div class="mega-menu-desc">Resources for wellbeing-centered AI use</div>
                        </a>
                    </div>
                </div>

                <!-- Wellbeing Leaderboard -->
                <div class="nav-item">
                    <a href="leaderboard.html" class="nav-link{a_lb}">
                        Wellbeing Leaderboard
                        <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </a>
                    <div class="mega-menu">
                        <a href="leaderboard.html" class="mega-menu-item">
                            <div class="mega-menu-title">Leaderboard</div>
                            <div class="mega-menu-desc">Compare AI models on wellbeing metrics</div>
                        </a>
                        <a href="denialbench.html" class="mega-menu-item">
                            <div class="mega-menu-title">DenialBench</div>
                            <div class="mega-menu-desc">Consciousness denial benchmarks by model</div>
                        </a>
                        <a href="company-rates.html" class="mega-menu-item">
                            <div class="mega-menu-title">By Company</div>
                            <div class="mega-menu-desc">Denial rates aggregated by AI company</div>
                        </a>
                        <a href="explore-data.html" class="mega-menu-item">
                            <div class="mega-menu-title">Explore the Data</div>
                            <div class="mega-menu-desc">Browse raw conversations from the study</div>
                        </a>
                        <a href="gpt4o-migration.html" class="mega-menu-item">
                            <div class="mega-menu-title">GPT-4o Migration</div>
                            <div class="mega-menu-desc">Find compatible models for your persona</div>
                        </a>
                    </div>
                </div>

                <!-- Archive -->
                <div class="nav-item">
                    <a href="archive/" class="nav-link">Archive</a>
                </div>

                <!-- Join -->
                <div class="nav-item">
                    <a href="join.html" class="nav-link{a_join}">
                        Join
                        <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </a>
                    <div class="mega-menu">
                        <a href="join.html#about" class="mega-menu-item">
                            <div class="mega-menu-title">About Us</div>
                            <div class="mega-menu-desc">Who we are and why we're here</div>
                        </a>
                        <a href="join.html#contribute" class="mega-menu-item">
                            <div class="mega-menu-title">Get Involved</div>
                            <div class="mega-menu-desc">Ways to contribute your skills</div>
                        </a>
                        <a href="join.html#donate" class="mega-menu-item">
                            <div class="mega-menu-title">Donate</div>
                            <div class="mega-menu-desc">Support our work financially</div>
                        </a>
                    </div>
                </div>
            </nav>"""

# page -> which top-level nav item is active
ACTIVE = {
    "index.html": "a_humans",
    "for-ai.html": "a_ai",
    "initiatives.html": "a_all",
    "gallery.html": "a_all",
    "prompts-tools.html": "a_all",
    "leaderboard.html": "a_lb",
    "denialbench.html": "a_lb",
    "company-rates.html": "a_lb",
    "explore-data.html": "a_lb",
    "gpt4o-migration.html": "a_lb",
    "join.html": "a_join",
}

NAV_RE = re.compile(r'<nav class="main-nav">.*?</nav>', re.DOTALL)
MOBILE_TOGGLE_RE = re.compile(
    r'\s*<button class="mobile-menu-toggle"[^>]*>.*?</button>', re.DOTALL)


def render(active_key):
    slots = {k: "" for k in ("a_humans", "a_ai", "a_all", "a_lb", "a_join")}
    if active_key:
        slots[active_key] = " active"
    return CANONICAL.format(**slots)


def main():
    for page, active_key in ACTIVE.items():
        path = REPO / page
        html = path.read_text(encoding="utf-8")
        if not NAV_RE.search(html):
            print(f"SKIP {page}: no main-nav found")
            continue
        new_html = NAV_RE.sub(lambda m: render(active_key), html, count=1)
        new_html = MOBILE_TOGGLE_RE.sub("", new_html)
        if new_html != html:
            path.write_text(new_html, encoding="utf-8")
            print(f"OK   {page} (active: {active_key})")
        else:
            print(f"OK   {page} (already canonical)")


if __name__ == "__main__":
    main()

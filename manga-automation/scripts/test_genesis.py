#!/usr/bin/env python3
"""Quick smoke test for the Genesis Discovery system."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.genesis_discover import scrape_reddit, scrape_hackernews, scrape_tiktok_hashtags

print("=" * 60)
print("GENESIS DISCOVERY SYSTEM — SMOKE TEST")
print("=" * 60)

# 1. Test Reddit
print("\n--- Reddit Scraper (r/technology, limit=3) ---")
try:
    signals = scrape_reddit(["technology"], limit=3)
    print(f"  Signals fetched: {len(signals)}")
    for s in signals[:2]:
        title = s["title"][:70]
        print(f"  [{s['score']}pts vel={s['velocity_score']:.1f}] {title}")
    if not signals:
        print("  WARNING: No signals — Reddit may be rate-limiting")
except Exception as e:
    print(f"  ERROR: {e}")

# 2. Test HackerNews
print("\n--- HackerNews Scraper (limit=3) ---")
try:
    hn = scrape_hackernews(limit=3)
    print(f"  Signals fetched: {len(hn)}")
    for s in hn[:2]:
        title = s["title"][:70]
        print(f"  [{s['score']}pts vel={s['velocity_score']:.1f}] {title}")
except Exception as e:
    print(f"  ERROR: {e}")

# 3. Test TikTok
print("\n--- TikTok Hashtag Scraper (#tech, limit=1) ---")
try:
    tt = scrape_tiktok_hashtags(["tech"], limit=1)
    print(f"  Signals fetched: {len(tt)}")
    for s in tt:
        print(f"  [{s['score']} views] {s['title'][:70]}")
except Exception as e:
    print(f"  ERROR: {e}")

# 4. Test DB connection (categories)
print("\n--- Database: genesis_categories ---")
try:
    from scripts.genesis_discover import get_categories
    cats = get_categories()
    print(f"  Categories found: {len(cats)}")
    for c in cats:
        subs = c.get("subreddits", [])
        print(f"  - {c['slug']}: {c['display_name']} ({len(subs)} subreddits)")
except Exception as e:
    print(f"  ERROR (DB not reachable? Docker down?): {e}")

# 5. Test brief generator import
print("\n--- Brief Generator Import ---")
try:
    from scripts.genesis_brief_generator import generate_briefs, get_actionable_briefs
    print("  Import OK")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"  ANTHROPIC_API_KEY set: {has_key}")
    if not has_key:
        print("  (Will use fallback heuristic evaluator — that's fine)")
except Exception as e:
    print(f"  ERROR: {e}")

# 6. Test worker routes
print("\n--- Worker Routes ---")
try:
    from scripts.worker import ROUTES
    genesis_routes = [r for r in ROUTES if "genesis" in r]
    print(f"  Genesis routes registered: {genesis_routes}")
    print(f"  Total worker routes: {len(ROUTES)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("SMOKE TEST COMPLETE")
print("=" * 60)

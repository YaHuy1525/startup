#!/usr/bin/env python3
"""
Fetch trending TikTok sounds and categorise them by emotion.

Sources (tried in order):
  1. TikTok Creative Center trending music API (public, no auth needed)
  2. A bundled seed list as fallback

Discovered sounds are upserted into the `tiktok_sounds` table.
Claude classifies each sound's dominant emotion from its title + author.

Usage:
    python3 scripts/fetch_tiktok_sounds.py [--limit 30] [--dry-run]

Schedule: run once a day via n8n cron or OS scheduler.
"""
import sys
import json
import argparse
import os
import time
import re

import requests
from dotenv import load_dotenv

load_dotenv()

from scripts.utils import database as db
from scripts.utils.logger import setup_logger

try:
    import anthropic
    _CLAUDE = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
except Exception:
    _CLAUDE = None

logger = setup_logger("fetch_tiktok_sounds")

# TikTok Creative Center trending music API (no auth required)
_CC_URL = (
    "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/music/list"
    "?period=7&page=1&limit={limit}&country_code=US"
)
_CC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ads.tiktok.com/",
}

# ─── Emotion classification ───────────────────────────────────────────────────

VALID_EMOTIONS = {"epic", "sad", "funny", "shocking", "romantic", "neutral"}

_KEYWORD_MAP = [
    (["battle", "fight", "war", "attack", "demon", "slash", "titan", "rumble",
      "power", "hero", "victory", "fire", "thunder", "rage", "intense"],       "epic"),
    (["sad", "cry", "tear", "loss", "death", "grief", "farewell", "ending",
      "memory", "longing", "evergarden", "silent", "broken"],                  "sad"),
    (["funny", "comedy", "meme", "gag", "silly", "quirky", "laugh", "cute",
      "chibi", "nyan"],                                                         "funny"),
    (["twist", "reveal", "shock", "sudden", "unexpected", "betrayal"],         "shocking"),
    (["love", "romance", "kiss", "heart", "tender", "wedding", "sweet",
      "bloom", "spring"],                                                        "romantic"),
]


def classify_emotion_heuristic(title: str, author: str) -> list[str]:
    """Fast keyword-based fallback when Claude is unavailable."""
    text = f"{title} {author}".lower()
    matched = []
    for keywords, emotion in _KEYWORD_MAP:
        if any(kw in text for kw in keywords):
            matched.append(emotion)
    return matched or ["neutral"]


def classify_emotion_claude(title: str, author: str) -> list[str]:
    """Ask Claude to classify emotion tags for a sound."""
    if not _CLAUDE:
        return classify_emotion_heuristic(title, author)

    prompt = (
        f"Classify this music track for use in manga/anime short videos.\n"
        f"Title: {title}\nArtist: {author}\n\n"
        f"Return a JSON array of 1-3 emotion tags that best describe the track's mood for video editing.\n"
        f"Choose from: epic, sad, funny, shocking, romantic, neutral\n"
        f"Reply with ONLY the JSON array, no other text. Example: [\"epic\",\"shocking\"]"
    )
    try:
        resp = _CLAUDE.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        tags = json.loads(raw)
        return [t for t in tags if t in VALID_EMOTIONS] or ["neutral"]
    except Exception as e:
        logger.warning(f"Claude classification failed for '{title}': {e}")
        return classify_emotion_heuristic(title, author)


# ─── TikTok Creative Center fetch ────────────────────────────────────────────

def fetch_from_creative_center(limit: int = 30) -> list[dict]:
    """
    Call TikTok's Creative Center trending music endpoint.
    Returns a list of dicts: {tiktok_id, title, author, duration_secs}.
    """
    url = _CC_URL.format(limit=limit)
    try:
        r = requests.get(url, headers=_CC_HEADERS, timeout=15)
        r.raise_for_status()
        payload = r.json()
        items = payload.get("data", {}).get("music_list") or payload.get("data", [])
        if not items:
            logger.warning("Creative Center returned empty music list")
            return []

        results = []
        for item in items:
            tid = str(item.get("music_id") or item.get("id") or "").strip()
            title = item.get("music_title") or item.get("title") or "Unknown"
            author = item.get("author_name") or item.get("author") or ""
            duration = item.get("duration") or 0
            rank = item.get("rank") or item.get("popularity_rank") or None
            if tid:
                results.append({
                    "tiktok_id":    tid,
                    "title":        title,
                    "author":       author,
                    "duration_secs": int(duration),
                    "trending_rank": rank,
                })
        logger.info(f"Creative Center: fetched {len(results)} sounds")
        return results

    except requests.exceptions.RequestException as exc:
        logger.warning(f"Creative Center request failed: {exc}")
        return []


# ─── Manual / URL-based addition ─────────────────────────────────────────────

def extract_sound_id_from_url(url: str) -> str | None:
    """
    Parse a TikTok sound URL and return the numeric sound ID.
    Supports:
      https://www.tiktok.com/music/Song-Title-1234567890123456789
      https://vm.tiktok.com/XXXXXXXX/
    """
    match = re.search(r"/music/[^/]+-(\d{15,20})", url)
    if match:
        return match.group(1)
    match = re.search(r"soundId=(\d{15,20})", url)
    return match.group(1) if match else None


# ─── DB upsert ───────────────────────────────────────────────────────────────

def upsert_sound(sound: dict, dry_run: bool = False) -> bool:
    emotion_tags = classify_emotion_claude(sound["title"], sound["author"])
    sound["emotion_tags"] = emotion_tags

    logger.info(
        f"  {sound['tiktok_id']} | {sound['title'][:40]:40s} | "
        f"{sound['author'][:20]:20s} | {emotion_tags}"
    )

    if dry_run:
        return True

    db.execute(
        """
        INSERT INTO tiktok_sounds
            (tiktok_id, title, author, duration_secs, emotion_tags, trending_rank, last_fetched_at)
        VALUES
            (%s, %s, %s, %s, %s::text[], %s, NOW())
        ON CONFLICT (tiktok_id) DO UPDATE SET
            title           = EXCLUDED.title,
            author          = EXCLUDED.author,
            duration_secs   = EXCLUDED.duration_secs,
            emotion_tags    = EXCLUDED.emotion_tags,
            trending_rank   = EXCLUDED.trending_rank,
            is_active       = true,
            last_fetched_at = NOW()
        """,
        (
            sound["tiktok_id"],
            sound["title"],
            sound["author"],
            sound["duration_secs"],
            emotion_tags,
            sound.get("trending_rank"),
        ),
    )
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(limit: int = 30, dry_run: bool = False) -> dict:
    logger.info(f"Fetching up to {limit} trending TikTok sounds (dry_run={dry_run})")

    sounds = fetch_from_creative_center(limit=limit)

    if not sounds:
        logger.warning("No sounds from Creative Center — DB seed data is already loaded at setup")
        return {"fetched": 0, "upserted": 0}

    upserted = 0
    for sound in sounds:
        try:
            if upsert_sound(sound, dry_run=dry_run):
                upserted += 1
            time.sleep(0.3)  # rate-limit Claude calls
        except Exception as exc:
            logger.error(f"Failed to upsert sound {sound.get('tiktok_id')}: {exc}")

    logger.info(f"Done. Upserted {upserted}/{len(sounds)} sounds.")
    return {"fetched": len(sounds), "upserted": upserted}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch trending TikTok sounds into DB")
    parser.add_argument("--limit",   type=int, default=30, help="Max sounds to fetch")
    parser.add_argument("--dry-run", action="store_true",  help="Classify but don't write to DB")
    parser.add_argument(
        "--add-url",
        metavar="TIKTOK_URL",
        help="Manually add a single TikTok sound by its URL"
    )
    args = parser.parse_args()

    if args.add_url:
        sid = extract_sound_id_from_url(args.add_url)
        if not sid:
            print(f"Could not extract sound ID from: {args.add_url}")
            sys.exit(1)
        sound = {
            "tiktok_id":    sid,
            "title":        input("Sound title: "),
            "author":       input("Artist/author: "),
            "duration_secs": 0,
            "trending_rank": None,
        }
        upsert_sound(sound, dry_run=args.dry_run)
        print(f"Added sound {sid}")
    else:
        result = main(limit=args.limit, dry_run=args.dry_run)
        print(json.dumps(result))
        sys.exit(0)

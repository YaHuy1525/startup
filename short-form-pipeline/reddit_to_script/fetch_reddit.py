"""Stage 1 — fetch Reddit stories via Reddit's public RSS feeds.

No Reddit OAuth app and no Firecrawl are needed:
  * Firecrawl refuses reddit.com ("we do not support this site").
  * reddit.com/*.json now serves a "Welcome to Reddit" HTML interstitial to
    programmatic clients (so it can't be parsed as JSON).
  * The RSS/Atom feeds (``/r/<sub>/top/.rss``) still return clean XML, and for
    self-posts the ``<content>`` element contains the full post body.

A descriptive browser User-Agent is required (Reddit blocks generic library
UAs). RSS does not expose scores, but ``top`` feeds are already rank-ordered.

Usage (standalone):
    python -m reddit_to_script.fetch_reddit --subreddit tifu --time day --limit 5
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

import requests

from . import config

_TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")
_ATOM = "{http://www.w3.org/2005/Atom}"
# Reddit wraps the actual self-text between these HTML comments in RSS content.
_BODY_RE = re.compile(r"<!-- SC_OFF -->(.*?)<!-- SC_ON -->", re.S)


class RedditFetchError(RuntimeError):
    """Raised when the Reddit RSS feed cannot be read."""


@dataclass
class RedditStory:
    """A single fetched Reddit story."""

    title: str
    url: str
    body: str
    author: str = ""
    upvotes: int = 0  # not available via RSS; kept for payload/report compatibility
    top_comments: tuple[str, ...] = ()


def _get_feed(url: str, params: dict, *, retries: int = 4, timeout: int = 20) -> str:
    """GET a Reddit RSS feed with a browser UA and backoff on throttling."""
    headers = {"User-Agent": config.REDDIT_USER_AGENT, "Accept": "*/*"}
    last_error = ""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(2 * (attempt + 1))
            continue

        # Reddit's RSS omits charset in the Content-Type header, so `requests`
        # would fall back to ISO-8859-1 and mangle smart quotes / em-dashes.
        # The feed is always UTF-8, so decode it explicitly.
        text = resp.content.decode("utf-8", errors="replace")
        if resp.status_code == 200 and text.lstrip().startswith("<?xml"):
            return text
        if resp.status_code == 200:
            # 200 but HTML — Reddit's anti-bot interstitial. Back off and retry.
            last_error = "received HTML interstitial instead of RSS (throttled)"
        elif resp.status_code in (429, 503):
            last_error = f"{resp.status_code} (rate limited)"
        elif resp.status_code in (403, 401):
            raise RedditFetchError(
                f"Reddit {resp.status_code} for {url}. Set a browser-like "
                "REDDIT_USER_AGENT in .env, or the IP may be temporarily blocked."
            )
        else:
            raise RedditFetchError(f"Reddit {resp.status_code} for {url}: {text[:200]}")
        time.sleep(3 * (attempt + 1))
    raise RedditFetchError(f"Reddit RSS request failed after {retries} tries: {last_error}")


def _html_to_text(fragment: str) -> str:
    """Convert an RSS content HTML fragment to clean plain text."""
    raw = html.unescape(fragment)
    raw = re.sub(r"(?i)</p\s*>", "\n\n", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = re.sub(r"<[^>]+>", "", raw)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_entry(entry: ET.Element) -> RedditStory | None:
    title_el = entry.find(f"{_ATOM}title")
    content_el = entry.find(f"{_ATOM}content")
    link_el = entry.find(f"{_ATOM}link")
    author_el = entry.find(f"{_ATOM}author/{_ATOM}name")

    content_html = content_el.text or "" if content_el is not None else ""
    match = _BODY_RE.search(content_html)
    if not match:
        return None  # link/image post (no self-text between SC_OFF/SC_ON)
    body = _html_to_text(match.group(1))
    if not body:
        return None
    return RedditStory(
        title=(title_el.text or "").strip() if title_el is not None else "",
        url=(link_el.get("href") if link_el is not None else "") or "",
        body=body,
        author=(author_el.text or "").strip() if author_el is not None else "",
    )


def list_stories(subreddit: str, time_filter: str, limit: int) -> list[RedditStory]:
    """Return self-post stories from a subreddit's top RSS feed (bodies included)."""
    if time_filter not in _TIME_FILTERS:
        raise ValueError(f"time_filter must be one of {_TIME_FILTERS}")

    url = f"{config.REDDIT_BASE_URL}/r/{subreddit}/top/.rss"
    feed = _get_feed(url, {"t": time_filter, "limit": max(limit, 25)})
    try:
        root = ET.fromstring(feed)
    except ET.ParseError as exc:
        raise RedditFetchError(f"Could not parse RSS from {url}: {exc}") from exc

    stories: list[RedditStory] = []
    for entry in root.findall(f"{_ATOM}entry"):
        story = _parse_entry(entry)
        if story is not None:
            stories.append(story)
    return stories


def fetch_stories(
    subreddit: str,
    time_filter: str = "day",
    limit: int = 5,
    *,
    min_words: int = 40,
    max_words: int = 600,
) -> list[RedditStory]:
    """Fetch up to ``limit`` usable text stories from a subreddit."""
    usable: list[RedditStory] = []
    for story in list_stories(subreddit, time_filter, limit):
        words = len(story.body.split())
        if words < min_words or words > max_words:
            continue  # too short to be a story / too long for a short video
        usable.append(story)
        if len(usable) >= limit:
            break
    return usable


def _main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Reddit stories via public RSS feeds.")
    parser.add_argument("--subreddit", default="tifu")
    parser.add_argument("--time", default="day", choices=list(_TIME_FILTERS))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    stories = fetch_stories(args.subreddit, args.time, args.limit)
    print(json.dumps([asdict(s) for s in stories], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()

#!/usr/bin/env python3
"""
Pod 3 — Editorial & Newsletter Agent.

Converts content briefs into publishable articles for:
  - Medium (REST API)
  - Substack (email-to-publish)
  - LinkedIn (text post format)

Also generates a "B2B crossover" variant for LinkedIn.

Usage:
    python scripts/editorial_publisher.py --brief-id 1 --platforms medium,linkedin
"""
from __future__ import annotations

import json
import os
import sys
import argparse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("editorial_publisher")

# ─── Configuration ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MEDIUM_TOKEN = os.environ.get("MEDIUM_INTEGRATION_TOKEN")
MEDIUM_AUTHOR_ID = os.environ.get("MEDIUM_AUTHOR_ID")
SUBSTACK_EMAIL_TO = os.environ.get("SUBSTACK_POST_EMAIL")  # your-pub@mg.substack.com
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
EDITORIAL_MODEL = os.environ.get("EDITORIAL_MODEL", "claude-sonnet-4-20250514")


# ─── Script → Article Conversion ────────────────────────────────────────────
def brief_to_article(brief: dict, style: str = "standard") -> dict:
    """
    Convert a content brief into a formatted article.
    style: 'standard' (Medium/Substack) or 'linkedin' (B2B crossover)
    Returns: { title, subtitle, body_html, body_markdown, tags }
    """
    if ANTHROPIC_API_KEY:
        return _llm_convert(brief, style)
    return _fallback_convert(brief, style)


def _llm_convert(brief: dict, style: str) -> dict:
    """Use Claude to rewrite the brief as a polished article."""
    try:
        import anthropic
    except ImportError:
        return _fallback_convert(brief, style)

    if style == "linkedin":
        prompt = f"""Rewrite the following trend analysis into a professional LinkedIn post.

Trend: {brief.get('trend_name', '')}
Narrative: {brief.get('base_narrative', '')}

Rules:
- Extract a lesson about leadership, strategy, or business psychology
- Use punchy, single-sentence paragraphs
- Start with a hook that stops scrolling
- Include 3-4 bulleted takeaways
- End with a thought-provoking question
- Keep under 1300 characters (LinkedIn limit)
- Do NOT use hashtags in the body, I'll add them separately
- Tone: authoritative but approachable, like a founder sharing insights

Return JSON: {{"title": "...", "body_text": "...", "tags": ["leadership", "strategy"]}}
"""
    else:
        prompt = f"""Convert the following content brief into a beautifully formatted article.

Brief:
- Title: {brief.get('trend_name', '')}
- Hook: {brief.get('viral_hook', '')}
- Audience: {brief.get('target_audience', '')}
- Narrative: {brief.get('base_narrative', '')}
- Monetization: {brief.get('suggested_monetization', '')}

Rules:
- Write in an engaging, authoritative voice
- Use H2 and H3 headings to structure the content
- Include a compelling introduction that hooks the reader
- Add blockquotes for key insights
- Bold important phrases
- End with a strong call-to-action
- Target 800-1200 words
- Format as HTML (for Medium)
- Also provide a plain Markdown version

Return JSON:
{{
  "title": "...",
  "subtitle": "...",
  "body_html": "<h2>...</h2><p>...</p>",
  "body_markdown": "## ...\\n\\n...",
  "tags": ["tech", "ai", "trending"]
}}
"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=EDITORIAL_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"LLM article conversion failed: {e}")
        return _fallback_convert(brief, style)


def _fallback_convert(brief: dict, style: str) -> dict:
    """Simple conversion without LLM."""
    title = brief.get("trend_name", "Trending Now")
    narrative = brief.get("base_narrative", "")

    if style == "linkedin":
        return {
            "title": title,
            "body_text": f"🔥 {brief.get('viral_hook', '')}\n\n{narrative[:800]}\n\nWhat do you think?",
            "tags": ["trending", "insights"],
        }

    paragraphs = [p.strip() for p in narrative.split(". ") if p.strip()]
    body_html = f"<h2>{title}</h2>\n"
    body_html += f"<blockquote>{brief.get('viral_hook', '')}</blockquote>\n"
    body_html += "\n".join(f"<p>{p}.</p>" for p in paragraphs)

    body_md = f"## {title}\n\n"
    body_md += f"> {brief.get('viral_hook', '')}\n\n"
    body_md += "\n\n".join(f"{p}." for p in paragraphs)

    return {
        "title": title,
        "subtitle": brief.get("viral_hook", ""),
        "body_html": body_html,
        "body_markdown": body_md,
        "tags": [brief.get("category_slug", "trending")],
    }


# ─── Medium Publisher ────────────────────────────────────────────────────────
def publish_to_medium(article: dict) -> dict:
    """Publish an article to Medium via the REST API."""
    if not MEDIUM_TOKEN:
        return {"success": False, "error": "MEDIUM_INTEGRATION_TOKEN not set", "platform": "medium"}

    author_id = MEDIUM_AUTHOR_ID
    if not author_id:
        # Fetch author ID from Medium API
        try:
            me = requests.get(
                "https://api.medium.com/v1/me",
                headers={"Authorization": f"Bearer {MEDIUM_TOKEN}"},
                timeout=10,
            )
            me.raise_for_status()
            author_id = me.json()["data"]["id"]
        except Exception as e:
            return {"success": False, "error": f"Failed to get Medium author ID: {e}", "platform": "medium"}

    payload = {
        "title": article.get("title", ""),
        "contentFormat": "html",
        "content": article.get("body_html", ""),
        "tags": article.get("tags", [])[:5],
        "publishStatus": "draft",  # Start as draft for review
    }

    try:
        resp = requests.post(
            f"https://api.medium.com/v1/users/{author_id}/posts",
            headers={
                "Authorization": f"Bearer {MEDIUM_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {
            "success": True,
            "platform": "medium",
            "url": data.get("url"),
            "post_id": data.get("id"),
            "status": "draft",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "platform": "medium"}


# ─── Substack Publisher (email-to-publish) ───────────────────────────────────
def publish_to_substack(article: dict) -> dict:
    """Send article to Substack via email-to-publish."""
    if not SUBSTACK_EMAIL_TO or not SMTP_USER:
        return {"success": False, "error": "SUBSTACK_POST_EMAIL or SMTP credentials not set", "platform": "substack"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = article.get("title", "New Post")
        msg["From"] = SMTP_USER
        msg["To"] = SUBSTACK_EMAIL_TO

        html_body = article.get("body_html", "")
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        return {"success": True, "platform": "substack", "status": "sent_to_email"}
    except Exception as e:
        return {"success": False, "error": str(e), "platform": "substack"}


# ─── Track Distribution ─────────────────────────────────────────────────────
def track_distribution(master_asset_id: int | None, platform: str, result: dict) -> None:
    """Record the distribution result in platform_distributions."""
    try:
        db.execute(
            """
            INSERT INTO platform_distributions
                (master_asset_id, platform, format, target_url, status, published_at)
            VALUES (%s, %s, 'article', %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END)
            ON CONFLICT (master_asset_id, platform) DO UPDATE SET
                target_url = EXCLUDED.target_url,
                status = EXCLUDED.status,
                published_at = COALESCE(EXCLUDED.published_at, platform_distributions.published_at)
            """,
            (
                master_asset_id,
                platform,
                result.get("url"),
                "published" if result.get("success") else "failed",
                result.get("success", False),
            ),
        )
    except Exception as e:
        logger.debug(f"Distribution tracking skipped: {e}")


# ─── Main Orchestrator ───────────────────────────────────────────────────────
def publish_brief(
    brief_id: int,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    """
    Convert a content brief into articles and publish to specified platforms.
    """
    if platforms is None:
        platforms = ["medium"]

    brief = db.execute_one(
        """
        SELECT cb.*, gc.slug AS category_slug, gc.display_name AS category_name
        FROM content_briefs cb
        JOIN genesis_categories gc ON cb.category_id = gc.id
        WHERE cb.id = %s
        """,
        (brief_id,),
    )
    if not brief:
        return {"error": f"Brief {brief_id} not found"}

    results = {"brief_id": brief_id, "platforms": {}}

    for platform in platforms:
        style = "linkedin" if platform == "linkedin" else "standard"
        article = brief_to_article(brief, style=style)

        if platform == "medium":
            result = publish_to_medium(article)
        elif platform == "substack":
            result = publish_to_substack(article)
        elif platform == "linkedin":
            # LinkedIn: just prepare the post text (manual or API later)
            result = {
                "success": True,
                "platform": "linkedin",
                "status": "prepared",
                "post_text": article.get("body_text", ""),
            }
        else:
            result = {"success": False, "error": f"Unknown platform: {platform}"}

        results["platforms"][platform] = result
        track_distribution(None, platform, result)

    return results


def main(body: dict | None = None, **kwargs) -> dict:
    """Entry point for worker.py integration."""
    if body is None:
        body = kwargs

    brief_id = body.get("brief_id")
    if not brief_id:
        return {"error": "brief_id is required"}

    platforms_raw = body.get("platforms", "medium")
    if isinstance(platforms_raw, str):
        platforms = [p.strip() for p in platforms_raw.split(",")]
    elif isinstance(platforms_raw, list):
        platforms = platforms_raw
    else:
        platforms = ["medium"]

    return publish_brief(brief_id=int(brief_id), platforms=platforms)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Editorial Publisher")
    parser.add_argument("--brief-id", type=int, required=True)
    parser.add_argument("--platforms", type=str, default="medium",
                        help="Comma-separated platforms: medium,substack,linkedin")
    args = parser.parse_args()

    platforms = [p.strip() for p in args.platforms.split(",")]
    result = publish_brief(brief_id=args.brief_id, platforms=platforms)
    print(json.dumps(result, indent=2, default=str))

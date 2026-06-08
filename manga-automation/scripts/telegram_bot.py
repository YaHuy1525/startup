#!/usr/bin/env python3
"""
Telegram control bot for manga automation + finance/side-hustle content.

Features:
- Trigger worker and agent endpoints from Telegram commands
- View service health and memory stats
- Restrict access to specific chat IDs
- Keyword-to-DM automation (comment 'list'/'guide' → auto-reply referral link)
- Finance/earnings commands for the @mini.money.matters strategy

Environment:
- TELEGRAM_BOT_TOKEN (required)
- TELEGRAM_ALLOWED_CHAT_IDS (optional comma-separated chat IDs)
- TELEGRAM_POLL_INTERVAL (optional, default: 2)
- TELEGRAM_WORKER_URL (optional, default: http://python-worker:8080)
- TELEGRAM_MASTRA_URL (optional, default: http://manga-agents:3001)
- REFERRAL_HUB_URL (optional, your public referral page URL)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# Ensure package-style imports work when this script is run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.utils.logger import setup_logger

load_dotenv()
logger = setup_logger("telegram_bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
WORKER_URL = os.getenv("TELEGRAM_WORKER_URL", "http://python-worker:8080").rstrip("/")
MASTRA_URL = os.getenv("TELEGRAM_MASTRA_URL", "http://manga-agents:3001").rstrip("/")
_worker_urls_raw = os.getenv(
    "TELEGRAM_WORKER_URLS",
    f"{WORKER_URL},http://localhost:18080,http://localhost:8080",
)
WORKER_URL_CANDIDATES = []
for candidate in [x.strip().rstrip("/") for x in _worker_urls_raw.split(",") if x.strip()]:
    if candidate not in WORKER_URL_CANDIDATES:
        WORKER_URL_CANDIDATES.append(candidate)
POLL_INTERVAL = int(os.getenv("TELEGRAM_POLL_INTERVAL", "2"))
HERMES_PIPELINE_TIMEOUT = int(os.getenv("TELEGRAM_HERMES_TIMEOUT_SEC", "600"))
TG_API_MAX_RETRIES = int(os.getenv("TELEGRAM_API_MAX_RETRIES", "3"))
TG_API_RETRY_BASE_SEC = float(os.getenv("TELEGRAM_API_RETRY_BASE_SEC", "1.5"))
REFERRAL_HUB_URL = os.getenv("REFERRAL_HUB_URL", "https://your-domain.com/links")

_raw_ids = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
ALLOWED_CHAT_IDS = {
    x.strip() for x in _raw_ids.split(",") if x.strip()
}

# ─── Keyword-to-DM trigger map ───────────────────────────────────────
# When ANY user (not just admins) sends a message containing these words,
# the bot auto-replies with the referral hub link.
# This mirrors the ManyChat comment-to-DM strategy — free, no extra tool needed.
KEYWORD_TRIGGERS: dict[str, str] = {
    "guide":   f"📊 Here are all my referral links: {REFERRAL_HUB_URL}\n\nJoin using my links and we both get bonuses! 🙌",
    "list":    f"📊 Full platform list + referral links: {REFERRAL_HUB_URL}",
    "links":   f"🔗 All referral links in one place: {REFERRAL_HUB_URL}",
    "apps":    f"📱 The apps I use to earn passively: {REFERRAL_HUB_URL}",
    "how":     f"❓ Here’s exactly how I do it — step by step: {REFERRAL_HUB_URL}",
    "join":    f"🚀 Sign up here (referral bonus included): {REFERRAL_HUB_URL}",
}


class TelegramBotError(RuntimeError):
    pass


def _tg_api(method: str, payload: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    if not TOKEN:
        raise TelegramBotError("TELEGRAM_BOT_TOKEN is missing")
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    last_error: Exception | None = None
    for attempt in range(1, max(1, TG_API_MAX_RETRIES) + 1):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise TelegramBotError(f"Telegram API error ({method}): {data}")
            return data
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt >= max(1, TG_API_MAX_RETRIES):
                break
            sleep_for = TG_API_RETRY_BASE_SEC * attempt
            logger.warning(
                f"Telegram API request failed ({method}) attempt {attempt}/{TG_API_MAX_RETRIES}: {exc}; retrying in {sleep_for:.1f}s"
            )
            time.sleep(sleep_for)
    raise TelegramBotError(f"Telegram API request failed ({method}) after {TG_API_MAX_RETRIES} attempts: {last_error}")


def _send_message(chat_id: str, text: str) -> None:
    _tg_api("sendMessage", {"chat_id": chat_id, "text": text[:4000]})


def _is_authorized(chat_id: str) -> bool:
    if not ALLOWED_CHAT_IDS:
        # If no allowlist is configured, permit all chats.
        return True
    return str(chat_id) in ALLOWED_CHAT_IDS


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _post_json(url: str, body: Optional[Dict[str, Any]] = None, timeout: int = 90) -> Tuple[bool, Any]:
    try:
        response = requests.post(url, json=body or {}, timeout=timeout)
        response.raise_for_status()
        return True, response.json()
    except Exception as exc:
        return False, str(exc)


def _get_json(url: str, timeout: int = 30) -> Tuple[bool, Any]:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return True, response.json()
    except Exception as exc:
        return False, str(exc)


def _worker_post_json(path: str, body: Optional[Dict[str, Any]] = None, timeout: int = 90) -> Tuple[bool, Any, str]:
    errors: List[str] = []
    for base in WORKER_URL_CANDIDATES:
        url = f"{base}{path}"
        ok, data = _post_json(url, body or {}, timeout=timeout)
        if ok:
            return True, data, base
        errors.append(f"{base}: {data}")
    return False, {"error": "all worker urls failed", "details": errors}, WORKER_URL_CANDIDATES[0] if WORKER_URL_CANDIDATES else WORKER_URL


def _worker_get_json(path: str, timeout: int = 30) -> Tuple[bool, Any, str]:
    errors: List[str] = []
    for base in WORKER_URL_CANDIDATES:
        url = f"{base}{path}"
        ok, data = _get_json(url, timeout=timeout)
        if ok:
            return True, data, base
        errors.append(f"{base}: {data}")
    return False, {"error": "all worker urls failed", "details": errors}, WORKER_URL_CANDIDATES[0] if WORKER_URL_CANDIDATES else WORKER_URL


def _help_text() -> str:
    return (
        "Content Automation Control Bot\n\n"
        "Core:\n"
        "/help - Show commands\n"
        "/whoami - Show current chat ID\n"
        "/status - Health + memory stats\n\n"
        "Classic Pipeline:\n"
        "/fetch_trending [limit]\n"
        "/fetch_chapter <manga_id>\n"
        "/download_panels <chapter_id>\n"
        "/check_duplicates <chapter_id>\n"
        "/generate_video <chapter_id>\n"
        "/upload_tiktok <video_id>\n"
        "/upload_youtube <video_id>\n"
        "/download_youtube <youtube_url> — download Short/video to library + send to chat\n"
        "/detect_shadow_ban [min_posts] [threshold]\n\n"
        "Arbitrage:\n"
        "/arb_discover [region] [limit]\n"
        "/arb_source [limit]\n"
        "/arb_download [batch]\n"
        "/arb_distribute [platform_csv] [batch]\n\n"
        "Research + Planning:\n"
        "/research_topic <query>\n"
        "/research_channel <youtube_channel_url>\n"
        "/research_status [limit]\n"
        "/plan_campaign <goal>\n"
        "/recover_last_run\n\n"
        "Agents + Advanced:\n"
        "/summon <prompt>\n"
        "/deerflow <prompt>\n"
        "/hermes_order <natural language order>\n"
        "/aito_hermes <natural language posting order>\n"
        "/aito_link_publish <video_or_channel_url> [platform_csv] [title|desc]\n"
        "/hermes_logs [lines] - tail Hermes docker log file\n"
        "/mastra <METHOD> <path> [json]\n"
        "/worker <path> [json]\n\n"
        "AiToEarn Account Management:\n"
        "/aito_accounts [platform] - list all connected accounts (or one platform)\n"
        "/aito_restrictions [platform_csv] - show platform posting constraints\n"
        "/aito_post_all <video_url> [platform_csv] [title|desc] - post to all accounts in selected platforms\n"
        "/aito_post_accounts <video_url> <platform=id1|id2;platform2=id3> [title|desc] - target specific account IDs\n"
        "/aito_post_json <json> - raw publish payload for advanced control\n"
        "/aito_publish_status <flow_id> - check async publish task status\n"
        "Account selection format: tiktok=id1|id2;youtube=id3\n\n"
        "Finance / Side-Hustle Strategy:\n"
        "/finance_discover - Scrape r/beermoney + #passiveincome\n"
        "/finance_briefs [top] - Generate finance content briefs\n"
        "/referral_list - Show all active referral platforms\n"
        "/earnings_scan - Scan screenshots dir for new payouts\n"
        "/weekly_recap [week_iso] - Generate earnings recap brief\n"
        "/finance_video [week_iso] [type] - Make proof video from screenshots\n"
        "  types: proof | voiceover | hook\n"
        "/finance_ai_video [provider] [week_iso] [bg] - AI video (revid/creatify/heygen)\n"
        "/finance_pipeline [provider] [bg] - 🚀 FULL AUTO: scan → video → post all platforms\n"
        "/viral_pipeline [provider] [bg] - 🚀 FULL AUTO: trend → draft → video → post\n"
        "  providers: revid | creatify | heygen  backgrounds: subway_surfers | minecraft\n"
        "/finance_post - Discover → brief → post (text/images only)\n\n"
        "Gig Copilot:\n"
        "/gig_new <platform> <task_type> <brief>\n"
        "  Platforms: dataannotation | outlier | babel\n"
        "  Task types: prompt-writing | response-rating | factual-eval | voice-script\n"
        "/gig_draft <task_id>\n"
        "/gig_score <task_id>\n"
        "/gig_submit_done <task_id> <accepted|rejected> <minutes> <payout_usd>\n"
        "/gig_today\n"
        "/gig_week\n\n"
        "Examples:\n"
        "/finance_discover\n"
        "/weekly_recap 2026-W19\n"
        "/aito_accounts\n"
        "/aito_accounts tiktok\n"
        "/aito_post_all https://samplelib.com/lib/preview/mp4/sample-5s.mp4 tiktok,youtube,instagram Hermes fanout test | Posted from Telegram\n"
        "/aito_post_accounts https://samplelib.com/lib/preview/mp4/sample-5s.mp4 tiktok=tiktok_111|tiktok_222;youtube=youtube_999 My title | My desc\n"
        "/hermes_order i want to post this video on all my tiktok youtube instagram accounts https://samplelib.com/lib/preview/mp4/sample-5s.mp4\n"
        "/aito_hermes i want to post this video on all of my platforms https://samplelib.com/lib/preview/mp4/sample-5s.mp4\n"
        "/aito_hermes find and post a funny family guy vietnamese dub short on tiktok\n"
        "/aito_link_publish https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw tiktok,youtube Fresh title | Fresh description\n"
        "/hermes_logs 200\n"
        "/hermes_order i want to post this on tiktok and youtube, tiktok=tiktok_111|tiktok_222;youtube=youtube_999 https://samplelib.com/lib/preview/mp4/sample-5s.mp4\n"
        "/fetch_trending 25\n"
        "/summon Find top viral clips in my niche and create 3 posts\n"
    )


def _cmd_status(_: List[str]) -> str:
    wk_ok, wk, wk_base = _worker_get_json("/health")
    ms_ok, ms = _get_json(f"{MASTRA_URL}/health")
    mem_ok, mem, _ = _worker_post_json("/api/memory/stats", {})

    return (
        "System Status\n\n"
        f"Worker ({wk_base}): {'OK' if wk_ok else 'FAIL'}\n{_safe_json(wk)}\n\n"
        f"Mastra: {'OK' if ms_ok else 'FAIL'}\n{_safe_json(ms)}\n\n"
        f"Memory: {'OK' if mem_ok else 'FAIL'}\n{_safe_json(mem)}"
    )


def _as_int(parts: List[str], idx: int, default: int) -> int:
    if len(parts) <= idx:
        return default
    return int(parts[idx])


def _as_float(parts: List[str], idx: int, default: float) -> float:
    if len(parts) <= idx:
        return default
    return float(parts[idx])


def _cmd_worker_route(path: str, body: Dict[str, Any], timeout: int = 90) -> str:
    ok, data, base = _worker_post_json(path, body, timeout=timeout)
    prefix = "Success" if ok else "Failed"
    return f"{prefix}: {path} via {base}\n{_safe_json(data)}"


def _cmd_fetch_trending(parts: List[str]) -> str:
    return _cmd_worker_route("/fetch-trending", {"limit": _as_int(parts, 1, 20)})


def _cmd_fetch_chapter(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /fetch_chapter <manga_id>"
    return _cmd_worker_route("/fetch-chapter", {"manga_id": int(parts[1])})


def _cmd_download_panels(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /download_panels <chapter_id>"
    return _cmd_worker_route("/download-panels", {"chapter_id": int(parts[1])})


def _cmd_check_duplicates(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /check_duplicates <chapter_id>"
    return _cmd_worker_route("/check-duplicates", {"chapter_id": int(parts[1])})


def _cmd_generate_video(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /generate_video <chapter_id>"
    return _cmd_worker_route("/generate-video", {"chapter_id": int(parts[1])})


def _cmd_upload_tiktok(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /upload_tiktok <video_id>"
    return _cmd_worker_route("/upload-tiktok", {"video_id": int(parts[1])})


def _cmd_upload_youtube(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /upload_youtube <video_id>"
    return _cmd_worker_route("/upload-youtube", {"video_id": int(parts[1])})


def _extract_youtube_url(text: str) -> Optional[str]:
    m = re.search(
        r"https?://(?:www\.)?(?:youtube\.com/[^\s]+|youtu\.be/[^\s]+)",
        text or "",
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return m.group(0).rstrip(">,.)")


def _extract_first_url(text: str) -> Optional[str]:
    m = re.search(r"https?://[^\s]+", text or "", flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(0).rstrip(">,.)")


def _parse_platform_csv(raw: str) -> List[str]:
    aliases = {"youtube_shorts": "youtube", "instagram_reels": "instagram"}
    out: List[str] = []
    for token in (raw or "").split(","):
        key = token.strip().lower()
        if not key:
            continue
        out.append(aliases.get(key, key))
    return out


def _extract_platforms_from_text(text: str) -> List[str]:
    candidates = ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest", "twitter", "douyin", "kwai", "bilibili"]
    found = [p for p in candidates if re.search(rf"\b{re.escape(p)}\b", text.lower())]
    return found


def _parse_account_selection_map(raw: str) -> Dict[str, List[str]]:
    """
    Format:
      tiktok=tiktok_id1|tiktok_id2;youtube=youtube_id1;instagram=instagram_id1
    """
    out: Dict[str, List[str]] = {}
    if not raw.strip():
        return out
    groups = [g.strip() for g in raw.split(";") if g.strip()]
    for group in groups:
        if "=" not in group:
            continue
        platform, ids_raw = group.split("=", 1)
        ids = [x.strip() for x in ids_raw.split("|") if x.strip()]
        if ids:
            out[platform.strip().lower()] = ids
    return out


def _clean_telegram_error_noise(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"unknown\s+command:\s*/[a-z0-9_]+\s*use\s*/help\s+for\s+all\s+commands\\?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _send_video_file(chat_id: str, path: str, caption: str = "") -> Tuple[bool, str]:
    """Send MP4 to Telegram chat (max ~50MB)."""
    if not os.path.isfile(path):
        return False, f"file not found: {path}"
    size = os.path.getsize(path)
    max_bytes = 48 * 1024 * 1024
    if size > max_bytes:
        return False, f"file too large for Telegram ({size // (1024 * 1024)} MB)"

    if not TOKEN:
        return False, "TELEGRAM_BOT_TOKEN missing"

    url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
    try:
        with open(path, "rb") as video_file:
            response = requests.post(
                url,
                data={"chat_id": chat_id, "caption": (caption or "")[:1024]},
                files={"video": video_file},
                timeout=180,
            )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            return False, str(data)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _cmd_download_youtube(text: str, chat_id: str) -> str:
    url = _extract_youtube_url(text)
    if not url:
        return (
            "Usage: /download_youtube <youtube_or_shorts_url>\n"
            "Example:\n"
            "/download_youtube https://youtube.com/shorts/iW1jvdwUIHo"
        )

    ok, data, base = _worker_post_json("/youtube/download-ingest", {"url": url}, timeout=300)
    if not ok:
        return f"Failed: {base}/youtube/download-ingest\n{_safe_json(data)}"

    inner = data.get("result") if isinstance(data, dict) and "result" in data else data
    if not isinstance(inner, dict) or not inner.get("success"):
        return f"Download failed:\n{_safe_json(inner)}"

    path = inner.get("local_path", "")
    video_id = inner.get("video_id")
    lines = [
        "✅ Downloaded and added to library",
        f"Title: {(inner.get('title') or '')[:200]}",
        f"Path: {path}",
        f"video_id: {video_id}",
    ]
    if video_id:
        lines.append(f"Post to TikTok (v1): /upload_tiktok {video_id}")

    if path and os.path.isfile(path):
        sent, err = _send_video_file(chat_id, path, inner.get("caption", "")[:200])
        if sent:
            lines.append("📲 Sent video to this chat.")
        else:
            lines.append(f"⚠️ Could not attach video: {err}")

    return "\n".join(lines)


def _cmd_shadow(parts: List[str]) -> str:
    return _cmd_worker_route(
        "/detect-shadow-ban",
        {
            "min_posts": _as_int(parts, 1, 5),
            "threshold": _as_float(parts, 2, 0.10),
        },
    )


def _cmd_arb_discover(parts: List[str]) -> str:
    region = parts[1] if len(parts) > 1 else "US"
    limit = _as_int(parts, 2, 20)
    return _cmd_worker_route("/arbitrage/discover-trends", {"region": region, "limit": limit})


def _cmd_arb_source(parts: List[str]) -> str:
    return _cmd_worker_route("/arbitrage/source-assets", {"limit": _as_int(parts, 1, 5)})


def _cmd_arb_download(parts: List[str]) -> str:
    return _cmd_worker_route("/arbitrage/download", {"batch": _as_int(parts, 1, 10)})


def _cmd_arb_distribute(parts: List[str]) -> str:
    platforms = ["tiktok"]
    if len(parts) > 1 and parts[1].strip():
        platforms = [x.strip() for x in parts[1].split(",") if x.strip()]
    batch = _as_int(parts, 2, 5)
    return _cmd_worker_route("/arbitrage/distribute", {"platforms": platforms, "batch": batch})


def _cmd_summon(raw: str) -> str:
    prompt = raw.replace("/summon", "", 1).strip()
    if not prompt:
        return "Usage: /summon <prompt>"
    return _cmd_worker_route("/api/summon-agent", {"prompt": prompt, "target_count": 5, "dry_run": False})


def _cmd_research_topic(raw: str) -> str:
    query = raw.replace("/research_topic", "", 1).strip()
    if not query:
        return "Usage: /research_topic <query>"
    return _cmd_worker_route("/research/ingest", {"query": query})


def _cmd_research_status(parts: List[str]) -> str:
    limit = _as_int(parts, 1, 10)
    return _cmd_worker_route("/research/status", {"limit": limit})


def _cmd_research_channel(raw: str) -> str:
    query = raw.replace("/research_channel", "", 1).strip()
    if not query:
        return "Usage: /research_channel <youtube_channel_url>"
    return _cmd_worker_route("/research/ingest", {"query": query})


def _cmd_plan_campaign(raw: str) -> str:
    goal = raw.replace("/plan_campaign", "", 1).strip()
    if not goal:
        return "Usage: /plan_campaign <goal>"
    return _cmd_worker_route("/deerflow/run", {"mode": "plan", "prompt": goal})


def _cmd_recover_last_run() -> str:
    return _cmd_worker_route("/deerflow/recover-last-run", {})


def _cmd_deerflow(raw: str) -> str:
    prompt = raw.replace("/deerflow", "", 1).strip()
    if not prompt:
        return "Usage: /deerflow <prompt>"
    return _cmd_worker_route("/deerflow/run", {"mode": "chat", "prompt": prompt})


# ── Gig Copilot commands ──────────────────────────────────────────────────────

def _cmd_gig_new(raw: str, chat_id: str) -> str:
    """
    /gig_new <platform> <task_type> <brief text...>
    Example: /gig_new dataannotation prompt-writing Write a story prompt about space
    """
    rest = raw.replace("/gig_new", "", 1).strip()
    if not rest:
        return (
            "Usage: /gig_new <platform> <task_type> <brief>\n\n"
            "Platforms: dataannotation | outlier | babel\n"
            "Task types: prompt-writing | response-rating | factual-eval | voice-script\n\n"
            "Example:\n"
            "/gig_new dataannotation prompt-writing Write a creative story about space travel"
        )
    parts = rest.split(" ", 2)
    if len(parts) < 3:
        return (
            "Need: <platform> <task_type> <brief>\n"
            "Example: /gig_new outlier prompt-writing Explain quantum entanglement simply"
        )
    platform, task_type, brief = parts[0], parts[1], parts[2]
    return _cmd_worker_route("/gig/task/create", {
        "user_id":   chat_id,
        "platform":  platform,
        "task_type": task_type,
        "brief":     brief,
    })


def _cmd_gig_draft(parts: List[str]) -> str:
    """/gig_draft <task_id> — Generate AI draft for the given task."""
    if len(parts) < 2:
        return "Usage: /gig_draft <task_id>"
    return _cmd_worker_route("/gig/task/draft", {"task_id": int(parts[1])})


def _cmd_gig_score(parts: List[str]) -> str:
    """/gig_score <task_id> — Run rubric scoring + risk flag check."""
    if len(parts) < 2:
        return "Usage: /gig_score <task_id>"
    result = _cmd_worker_route("/gig/task/score", {"task_id": int(parts[1])})
    # Surface the formatted summary if available
    try:
        import json
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        if isinstance(data, dict) and data.get("result", {}).get("summary"):
            return data["result"]["summary"]
    except Exception:
        pass
    return result


def _cmd_gig_submit_done(parts: List[str], chat_id: str) -> str:
    """
    /gig_submit_done <task_id> <accepted|rejected> <minutes> <payout_usd>
    Example: /gig_submit_done 42 accepted 18 3.50
    """
    if len(parts) < 5:
        return (
            "Usage: /gig_submit_done <task_id> <accepted|rejected> <minutes> <payout_usd>\n"
            "Example: /gig_submit_done 42 accepted 18 3.50"
        )
    return _cmd_worker_route("/gig/task/finalize", {
        "task_id": int(parts[1]),
        "outcome": parts[2],
        "minutes": int(parts[3]),
        "payout":  float(parts[4]),
        "user_id": chat_id,
    })


def _cmd_gig_today(chat_id: str) -> str:
    """/gig_today — Today's KPI summary (payout, acceptance, hourly rate)."""
    result = _cmd_worker_route("/gig/session/today", {"user_id": chat_id})
    try:
        import json
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        if isinstance(data, dict) and data.get("result", {}).get("formatted"):
            return data["result"]["formatted"]
    except Exception:
        pass
    return result


def _cmd_gig_week(chat_id: str) -> str:
    """/gig_week — 7-day performance breakdown."""
    result = _cmd_worker_route("/gig/session/week", {"user_id": chat_id})
    try:
        import json
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        if isinstance(data, dict) and data.get("result", {}).get("formatted"):
            return data["result"]["formatted"]
    except Exception:
        pass
    return result


# ── Obsidian commands ─────────────────────────────────────────────────────────────────

def _cmd_ob_save(parts: List[str]) -> str:
    """
    /ob_save <task_id>
    Manually sync a specific gig task to the Obsidian vault.
    """
    if len(parts) < 2:
        return "Usage: /ob_save <task_id>"
    return _cmd_worker_route("/obsidian/task", {
        "action":  "task",
        "task":    {"id": int(parts[1])},
    })


def _cmd_ob_log(chat_id: str) -> str:
    """/ob_log — Force-write today's session log to the Obsidian vault."""
    return _cmd_worker_route("/obsidian/session", {
        "action":  "session",
        "user_id": chat_id,
    })


def _cmd_ob_template(parts: List[str], raw: str) -> str:
    """
    /ob_template <task_id> [note about why this is a winning template]
    Save a task's draft as a reusable template in the vault.
    """
    if len(parts) < 2:
        return (
            "Usage: /ob_template <task_id> [optional note]\n"
            "Example: /ob_template 42 Great structure for Outlier prompts"
        )
    task_id = int(parts[1])
    note    = " ".join(parts[2:]) if len(parts) > 2 else ""
    return _cmd_worker_route("/obsidian/template", {
        "action":  "template",
        "task_id": task_id,
        "note":    note,
    })


def _cmd_worker(raw: str) -> str:
    # /worker /route {"key":"value"}
    rest = raw.replace("/worker", "", 1).strip()
    if not rest:
        return "Usage: /worker <path> [json]"
    split = rest.split(" ", 1)
    path = split[0]
    body: Dict[str, Any] = {}
    if len(split) > 1 and split[1].strip():
        body = json.loads(split[1].strip())
    return _cmd_worker_route(path, body)


def _cmd_aito_accounts(parts: List[str]) -> str:
    platform = parts[1].strip().lower() if len(parts) > 1 else None
    body: Dict[str, Any] = {}
    if platform:
        body["platform"] = platform
    return _cmd_worker_route("/aitoearn/accounts", body)


def _cmd_aito_restrictions(parts: List[str]) -> str:
    platforms = _parse_platform_csv(parts[1]) if len(parts) > 1 else []
    return _cmd_worker_route("/aitoearn/publish/restrictions", {"platforms": platforms})


def _split_title_desc(raw_tail: str) -> Tuple[str, str]:
    if "|" in raw_tail:
        left, right = raw_tail.split("|", 1)
        return left.strip(), right.strip()
    title = raw_tail.strip()
    return title, title


def _cmd_aito_post_all(raw: str) -> str:
    """
    /aito_post_all <video_url> [platform_csv] [title|desc]
    """
    rest = raw.replace("/aito_post_all", "", 1).strip()
    if not rest:
        return (
            "Usage: /aito_post_all <video_url> [platform_csv] [title|desc]\n"
            "Example:\n"
            "/aito_post_all https://samplelib.com/lib/preview/mp4/sample-5s.mp4 tiktok,youtube,instagram My title | My description"
        )
    chunks = rest.split(" ", 2)
    if len(chunks) < 1:
        return "Usage: /aito_post_all <video_url> [platform_csv] [title|desc]"
    video_url = chunks[0].strip()
    known_platforms = {"tiktok", "youtube", "instagram", "facebook", "threads", "pinterest", "twitter", "douyin", "kwai", "bilibili"}
    platforms: List[str] = []
    tail = ""
    if len(chunks) >= 2:
        maybe_platforms = _parse_platform_csv(chunks[1])
        if maybe_platforms and all(p in known_platforms for p in maybe_platforms):
            platforms = maybe_platforms
            tail = chunks[2].strip() if len(chunks) >= 3 else ""
        else:
            tail = " ".join(chunks[1:]).strip()
    title, desc = _split_title_desc(tail) if tail else ("Automated post", "Automated post from Telegram")
    return _cmd_worker_route(
        "/aitoearn/publish",
        {
            "video_url": video_url,
            "channels": platforms,
            "title": title,
            "desc": desc,
        },
    )


def _cmd_aito_post_accounts(raw: str) -> str:
    """
    /aito_post_accounts <video_url> <platform=id1|id2;platform2=id3> [title|desc]
    """
    rest = raw.replace("/aito_post_accounts", "", 1).strip()
    if not rest:
        return (
            "Usage: /aito_post_accounts <video_url> <platform=id1|id2;platform2=id3> [title|desc]\n"
            "Example:\n"
            "/aito_post_accounts https://samplelib.com/lib/preview/mp4/sample-5s.mp4 tiktok=tiktok_xxx;youtube=youtube_yyy Custom title | Custom desc"
        )
    chunks = rest.split(" ", 2)
    if len(chunks) < 2:
        return "Usage: /aito_post_accounts <video_url> <platform=id1|id2;platform2=id3> [title|desc]"
    video_url = chunks[0].strip()
    selected_map = _parse_account_selection_map(chunks[1].strip())
    if not selected_map:
        return "Invalid account map. Use format: tiktok=id1|id2;youtube=id3"
    channels = list(selected_map.keys())
    tail = chunks[2].strip() if len(chunks) >= 3 else ""
    title, desc = _split_title_desc(tail) if tail else ("Automated targeted post", "Automated targeted post from Telegram")
    return _cmd_worker_route(
        "/aitoearn/publish",
        {
            "video_url": video_url,
            "channels": channels,
            "selected_accounts": selected_map,
            "title": title,
            "desc": desc,
        },
    )


def _cmd_aito_post_json(raw: str) -> str:
    """
    /aito_post_json {"video_url":"...","channels":["tiktok"],"selected_accounts":{"tiktok":["id"]}}
    """
    rest = raw.replace("/aito_post_json", "", 1).strip()
    if not rest:
        return "Usage: /aito_post_json <json>"
    body = json.loads(rest)
    return _cmd_worker_route("/aitoearn/publish", body)


def _cmd_aito_publish_status(parts: List[str]) -> str:
    if len(parts) < 2:
        return "Usage: /aito_publish_status <flow_id>"
    return _cmd_worker_route("/aitoearn/publish/status", {"flow_id": parts[1].strip()})


def _cmd_aito_link_publish(raw: str) -> str:
    """
    /aito_link_publish <video_or_channel_url> [platform_csv] [title|desc]
    """
    rest = raw.replace("/aito_link_publish", "", 1).strip()
    if not rest:
        return (
            "Usage: /aito_link_publish <video_or_channel_url> [platform_csv] [title|desc]\n"
            "Examples:\n"
            "/aito_link_publish https://youtube.com/shorts/iW1jvdwUIHo tiktok,youtube Fast title | Fast desc\n"
            "/aito_link_publish https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw tiktok,youtube"
        )

    chunks = rest.split(" ", 2)
    source_url = chunks[0].strip()
    known_platforms = {"tiktok", "youtube", "instagram", "facebook", "threads", "pinterest", "twitter", "douyin", "kwai", "bilibili"}
    platforms: List[str] = []
    tail = ""
    if len(chunks) >= 2:
        maybe_platforms = _parse_platform_csv(chunks[1])
        if maybe_platforms and all(p in known_platforms for p in maybe_platforms):
            platforms = maybe_platforms
            tail = chunks[2].strip() if len(chunks) >= 3 else ""
        else:
            tail = " ".join(chunks[1:]).strip()

    body: Dict[str, Any] = {
        "source_url": source_url,
        "channels": platforms or ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"],
        "objective": rest[:500],
    }
    if tail:
        title, desc = _split_title_desc(tail)
        body["title"] = title
        body["desc"] = desc
    return _cmd_worker_route("/hermes/link-publish", body, timeout=HERMES_PIPELINE_TIMEOUT)


def _cmd_hermes_logs(parts: List[str]) -> str:
    lines = _as_int(parts, 1, 120)
    return _cmd_worker_route("/hermes/log-tail", {"lines": lines})


def _cmd_hermes_order(raw: str) -> str:
    """
    Natural language orchestrator:
    /hermes_order i want to post this on all my tiktok youtube accounts https://...
    """
    text = raw.replace("/hermes_order", "", 1).strip()
    if not text:
        return (
            "Usage: /hermes_order <natural language order>\n"
            "Examples:\n"
            "/hermes_order i want to post this video on all my tiktok youtube instagram accounts https://samplelib.com/lib/preview/mp4/sample-5s.mp4\n"
            "/hermes_order post finance content daily on tiktok and youtube using revid minecraft"
        )

    lower = text.lower()
    platforms = _extract_platforms_from_text(lower)
    selected_map = _parse_account_selection_map(text) if "=" in text else {}
    video_url = _extract_first_url(text)
    is_channel_link = bool(video_url and ("youtube.com/channel/" in video_url.lower() or "youtube.com/@" in video_url.lower()))

    provider = "revid"
    for key in ("revid", "creatify", "heygen", "invideo"):
        if key in lower:
            provider = key
            break
    background = "subway_surfers"
    for bg in ("subway_surfers", "minecraft", "temple_run", "gta", "satisfying"):
        if bg in lower:
            background = bg
            break

    # Heuristic intent routing:
    # - explicit finance intent -> finance pipeline
    # - channel-link intent -> viral generation pipeline (Hermes-native)
    # - direct media URL intent -> full_ops with AiToEarn publish fanout
    if "finance" in lower or "earnings" in lower or "side hustle" in lower:
        body: Dict[str, Any] = {
            "provider": provider,
            "background": background,
            "profile": "minimal",
        }
        if platforms:
            body["channels"] = platforms
        if selected_map:
            body["selected_accounts"] = selected_map
        return _cmd_worker_route("/hermes/finance-pipeline", body)

    if is_channel_link:
        body = {
            "provider": provider,
            "background": background,
            "profile": "minimal",
            "channels": platforms or ["tiktok", "youtube", "instagram"],
            "objective": text,
        }
        if selected_map:
            body["selected_accounts"] = selected_map
        return _cmd_worker_route("/hermes/viral-pipeline", body)

    if not video_url:
        body = {
            "profile": "minimal",
            "channels": platforms or ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"],
            "objective": text,
        }
        if selected_map:
            body["selected_accounts"] = selected_map
        return _cmd_worker_route("/hermes/discover-publish", body, timeout=HERMES_PIPELINE_TIMEOUT)

    body = {
        "mode": "light",
        "profile": "minimal",
        "channels": platforms or ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"],
        "title": "Automated post",
        "desc": text[:400],
        "objective": text,
        "video_url": video_url,
    }
    if selected_map:
        body["selected_accounts"] = selected_map
    return _cmd_worker_route("/hermes/full-ops", body)


def _cmd_aito_hermes(raw: str) -> str:
    """
    AiToEarn-focused natural language posting command.
    Example:
      /aito_hermes i want to post this video on all of my platforms https://...
    """
    prompt = _clean_telegram_error_noise(raw.replace("/aito_hermes", "", 1).strip())
    if not prompt:
        return (
            "Usage: /aito_hermes <natural language posting order>\n"
            "Examples:\n"
            "/aito_hermes i want to post this video on all of my platforms https://samplelib.com/lib/preview/mp4/sample-5s.mp4\n"
            "/aito_hermes find and post a funny family guy vietnamese dub short on tiktok"
        )

    lower = prompt.lower()
    platforms = _extract_platforms_from_text(lower)
    wants_all_platforms = ("all platform" in lower) or ("all my platform" in lower) or ("all of my platform" in lower)
    selected_map = _parse_account_selection_map(prompt) if "=" in prompt else {}
    source_url = _extract_first_url(prompt)

    body: Dict[str, Any] = {
        "channels": ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"]
        if wants_all_platforms
        else (platforms or ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"]),
        "objective": prompt,
    }
    if source_url:
        body["source_url"] = source_url
    if selected_map:
        body["selected_accounts"] = selected_map
    route = "/hermes/link-publish" if source_url else "/hermes/discover-publish"
    return _cmd_worker_route(route, body, timeout=HERMES_PIPELINE_TIMEOUT)


# ── Finance / Side-Hustle commands ──────────────────────────────────────────

def _cmd_finance_discover(_: List[str]) -> str:
    """/finance_discover — Scrape r/beermoney + TikTok #passiveincome for trending signals."""
    return _cmd_worker_route("/genesis/discover", {"categories": "finance", "limit": 15})


def _cmd_finance_briefs(parts: List[str]) -> str:
    """/finance_briefs [top=3] — Generate AI content briefs from finance signals."""
    top = _as_int(parts, 1, 3)
    return _cmd_worker_route("/genesis/briefs", {"categories": "finance", "top": top, "action": "generate"})


def _cmd_referral_list(_: List[str]) -> str:
    """/referral_list — Show all active referral platforms and their links."""
    return _cmd_worker_route("/earnings/list", {"action": "list"})


def _cmd_earnings_scan(_: List[str]) -> str:
    """/earnings_scan — Scan data/earnings_screenshots/ for new payout proofs."""
    return _cmd_worker_route("/earnings/ingest", {"action": "scan"})


def _cmd_weekly_recap(parts: List[str]) -> str:
    """/weekly_recap [week_iso] — Generate a weekly earnings summary brief."""
    week_iso = parts[1] if len(parts) > 1 else None
    body: Dict[str, Any] = {"action": "weekly-recap"}
    if week_iso:
        body["week_iso"] = week_iso
    return _cmd_worker_route("/earnings/ingest", body)


def _cmd_finance_post(_: List[str]) -> str:
    """
    /finance_post — Full automated pipeline:
    1. Discover finance signals
    2. Generate briefs
    3. Auto-distribute top brief to all channels
    """
    lines = []

    # Step 1: Discover
    ok1, d1, _ = _worker_post_json("/genesis/discover", {"categories": "finance", "limit": 15})
    lines.append(f"1️⃣ Discover: {'OK' if ok1 else 'FAIL'}")
    if isinstance(d1, dict):
        fin = d1.get("result", d1).get("per_category", {}).get("finance", {})
        lines.append(f"   Signals found: {fin.get('signals', '?')}")

    # Step 2: Generate briefs
    ok2, d2, _ = _worker_post_json("/genesis/briefs", {"categories": "finance", "top": 2, "action": "generate"})
    lines.append(f"2️⃣ Brief gen: {'OK' if ok2 else 'FAIL'}")
    brief_ids: List[int] = []
    if isinstance(d2, dict):
        fin2 = d2.get("result", d2).get("per_category", {}).get("finance", {})
        brief_ids = fin2.get("brief_ids", [])
        lines.append(f"   Briefs created: {fin2.get('briefs', '?')} (IDs: {brief_ids})")

    # Step 3: Distribute top brief
    if brief_ids:
        bid = brief_ids[0]
        ok3, d3, _ = _worker_post_json("/omnichannel/distribute", {"brief_id": bid, "profile": "minimal"})
        lines.append(f"3️⃣ Distribute brief #{bid}: {'OK' if ok3 else 'FAIL'}")
        if isinstance(d3, dict):
            r = d3.get("result", d3)
            lines.append(f"   Succeeded: {r.get('succeeded', '?')}, Failed: {r.get('failed', '?')}")
    else:
        lines.append("3️⃣ No briefs generated — check that finance signals exist first")

    return "\n".join(lines)


def _cmd_finance_video(parts: List[str]) -> str:
    """
    /finance_video [week_iso] [type]
    Generate a TikTok-ready proof video from your earnings screenshots.
    Types: proof (default) | voiceover (+ TTS narration) | hook (just the hook card)
    Examples:
      /finance_video
      /finance_video 2026-W19
      /finance_video 2026-W19 voiceover
    """
    week_iso = parts[1] if len(parts) > 1 and "-W" in parts[1] else None
    vtype = "proof"
    for p in parts[1:]:
        if p in ("proof", "voiceover", "hook"):
            vtype = p
            break

    body: Dict[str, Any] = {"type": vtype}
    if week_iso:
        body["week_iso"] = week_iso

    result = _cmd_worker_route("/finance/generate-video", body)

    # Parse and format the result nicely
    try:
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        r = data.get("result", data)
        if r.get("video_id"):
            return (
                f"\U0001f3a5 Video ready!\n"
                f"ID: #{r['video_id']}\n"
                f"Week: {r.get('week_iso', '?')}\n"
                f"Total earned: ${r.get('total_earned', 0):.2f}\n"
                f"Slides: {r.get('slides', '?')}\n"
                f"Size: {r.get('size_mb', '?')}MB\n\n"
                f"\U0001f680 Upload:\n"
                f"/upload_tiktok {r['video_id']}\n"
                f"/upload_youtube {r['video_id']}"
            )
        elif r.get("error"):
            return f"\u274c Error: {r['error']}\n{r.get('hint', '')}"
    except Exception:
        pass
    return result


def _cmd_finance_ai_video(parts: List[str]) -> str:
    """
    /finance_ai_video [provider] [week_iso] [style]
    Generate a professional video using AI video platforms.

    Providers:
      creatify  — Ad-style proof video (best match for mini.money.matters)
      heygen    — AI avatar talking-head video (no face needed)
      invideo   — Stock footage explainer video

    Styles (creatify only):
      avatar    — AI avatar reads your script (default)
      link      — Generate from your referral hub URL

    Examples:
      /finance_ai_video
      /finance_ai_video creatify
      /finance_ai_video heygen 2026-W19
      /finance_ai_video creatify 2026-W19 link
    """
    provider = "creatify"
    week_iso = None
    style = "avatar"

    for p in parts[1:]:
        if p in ("creatify", "heygen", "invideo"):
            provider = p
        elif "-W" in p:
            week_iso = p
        elif p in ("avatar", "link", "explainer"):
            style = p

    body: Dict[str, Any] = {"provider": provider, "style": style}
    if week_iso:
        body["week_iso"] = week_iso

    result = _cmd_worker_route("/finance/ai-video", body)

    try:
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        r = data.get("result", data)
        if r.get("success") or r.get("video_url") or r.get("video_id"):
            lines = [f"🎬 Video generated via {provider.upper()}!"]
            if r.get("total_earned"):
                lines.append(f"💰 Total: ${r['total_earned']:.2f}")
            if r.get("video_url"):
                lines.append(f"🔗 Download: {r['video_url']}")
            if r.get("db_video_id"):
                lines.append(f"\n🚀 Upload now:\n/upload_tiktok {r['db_video_id']}\n/upload_youtube {r['db_video_id']}")
            if r.get("message"):
                lines.append(r["message"])
            return "\n".join(lines)
        elif r.get("error"):
            return f"❌ {r['error']}\n{r.get('hint', '')}"
    except Exception:
        pass
    return result


def _cmd_list_avatars(parts: List[str]) -> str:
    """
    /list_avatars [provider]
    List available AI avatars for video generation.
    Providers: creatify (default) | heygen
    """
    provider = parts[1] if len(parts) > 1 else "creatify"
    result = _cmd_worker_route("/finance/list-avatars", {"provider": provider})
    try:
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        r = data.get("result", data)
        avatars = r.get("data", r.get("avatars", []))
        if isinstance(avatars, list) and avatars:
            lines = [f"Available {provider} avatars ({len(avatars)} found):"]
            for av in avatars[:10]:
                av_id = av.get("avatar_id") or av.get("id") or "?"
                av_name = av.get("avatar_name") or av.get("name") or "Unnamed"
                lines.append(f"  • {av_name}: {av_id}")
            lines.append(f"\nSet in .env: CREATIFY_AVATAR_ID=<id> or HEYGEN_AVATAR_ID=<id>")
            return "\n".join(lines)
    except Exception:
        pass
    return result



def _cmd_finance_pipeline(parts: List[str]) -> str:
    """
    /finance_pipeline [provider] [background] [week_iso] [profile]
    🚀 FULL AUTONOMOUS PIPELINE — Hermes agent runs all 4 steps:
      1. Scan earnings screenshots
      2. Generate brainrot video (Revid/Creatify/HeyGen)
      3. Post to ALL platforms (TikTok, YouTube, Instagram, Threads, Pinterest)
      4. Claude health-check report

    Examples:
      /finance_pipeline                           ← revid + subway_surfers
      /finance_pipeline revid minecraft           ← minecraft background
      /finance_pipeline creatify 2026-W19         ← specific week
      /finance_pipeline heygen subway_surfers full ← full distribution
    """
    provider   = "revid"
    background = "subway_surfers"
    week_iso   = None
    profile    = "minimal"

    for p in parts[1:]:
        if p in ("revid", "creatify", "heygen", "invideo"):
            provider = p
        elif p in ("subway_surfers", "minecraft", "temple_run", "gta", "satisfying"):
            background = p
        elif "-W" in p:
            week_iso = p
        elif p in ("full", "minimal"):
            profile = p

    body: Dict[str, Any] = {
        "provider":   provider,
        "background": background,
        "profile":    profile,
    }
    if week_iso:
        body["week_iso"] = week_iso

    # Notify user the pipeline is starting (it takes ~10 min for video gen)
    start_msg = (
        f"🤖 Hermes pipeline starting...\n"
        f"Provider: {provider.upper()} | Background: {background}\n"
        f"{'Week: ' + week_iso if week_iso else 'Week: current'} | Profile: {profile}\n\n"
        f"⏳ Video generation takes ~5–10 min. Stand by..."
    )

    result = _cmd_worker_route("/hermes/finance-pipeline", body)

    try:
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        r = data.get("result", data)

        if r.get("error"):
            return f"❌ Pipeline failed: {r['error']}"

        steps = r.get("steps", [])
        lines = [
            f"{'✅' if r.get('success') else '⚠️'} Finance Pipeline Complete\n",
            f"Steps passed: {r.get('steps_passed', 0)} / {len(steps)}",
        ]

        # Step details
        for step in steps:
            icon = "✅" if step.get("status") == "ok" else "❌"
            name = step.get("step", "?")
            if name == "earnings_scan":
                n = step.get("result", {}).get("ingested", "?")
                lines.append(f"{icon} Earnings scan: {n} new snapshots")
            elif name == "video_generate":
                vid = step.get("video_id", "?")
                url = step.get("video_url", "")
                lines.append(f"{icon} Video generated: #{vid}")
                if url:
                    lines.append(f"   🔗 {url}")
            elif name == "distribute":
                ok = step.get("succeeded", 0)
                fail = step.get("failed", 0)
                lines.append(f"{icon} Distributed: {ok} platforms ✓  {fail} failed")
            elif name == "hermes_healthcheck":
                diag = step.get("diagnosis", {})
                sev = diag.get("severity", "?")
                summ = diag.get("summary", "")[:80]
                lines.append(f"{icon} Claude report [{sev}]: {summ}")
            else:
                lines.append(f"{icon} {name}: {step.get('status')}")

        # Overall message
        if r.get("message"):
            lines.append(f"\n📊 {r['message']}")

        vid_id = r.get("video_id")
        if vid_id:
            lines.append(f"\n📱 Manual upload (if auto failed):")
            lines.append(f"/upload_tiktok {vid_id}")
            lines.append(f"/upload_youtube {vid_id}")

        return "\n".join(lines)

    except Exception:
        pass

    return start_msg + "\n\n" + result


def _cmd_viral_pipeline(parts: List[str]) -> str:
    """
    /viral_pipeline [provider] [background] [profile]
    🚀 FULL AUTONOMOUS VIRAL PIPELINE — Hermes agent runs all steps:
      1. Discover viral trends
      2. Draft brief
      3. Generate brainrot video
      4. Post to ALL platforms
      5. Claude health-check report
    """
    provider   = "revid"
    background = "subway_surfers"
    profile    = "minimal"

    for p in parts[1:]:
        if p in ("revid", "creatify", "heygen", "invideo"):
            provider = p
        elif p in ("subway_surfers", "minecraft", "temple_run", "gta", "satisfying"):
            background = p
        elif p in ("full", "minimal"):
            profile = p

    body: Dict[str, Any] = {
        "provider":   provider,
        "background": background,
        "profile":    profile,
    }

    start_msg = (
        f"🤖 Hermes viral pipeline starting...\n"
        f"Provider: {provider.upper()} | Background: {background} | Profile: {profile}\n\n"
        f"⏳ Video generation takes ~5–10 min. Stand by..."
    )

    result = _cmd_worker_route("/hermes/viral-pipeline", body)

    try:
        data = json.loads(result.split("\n", 1)[1]) if "\n" in result else {}
        r = data.get("result", data)

        if r.get("error"):
            return f"❌ Pipeline failed: {r['error']}"

        steps = r.get("steps", [])
        lines = [
            f"{'✅' if r.get('success') else '⚠️'} Viral Pipeline Complete\n",
            f"Steps passed: {r.get('steps_passed', 0)} / {len(steps)}",
        ]

        # Step details
        for step in steps:
            icon = "✅" if step.get("status") == "ok" else "❌"
            name = step.get("step", "?")
            if name == "genesis_discover":
                n = step.get("result", {}).get("per_category", {}).get("finance", {}).get("signals", "?")
                lines.append(f"{icon} Trends discovered: {n} signals")
            elif name == "genesis_briefs":
                b = step.get("result", {}).get("per_category", {}).get("finance", {}).get("briefs", "?")
                lines.append(f"{icon} Briefs drafted: {b}")
            elif name == "video_generate":
                vid = step.get("video_id", "?")
                url = step.get("video_url", "")
                lines.append(f"{icon} Video generated: #{vid}")
                if url:
                    lines.append(f"   🔗 {url}")
            elif name == "distribute":
                ok = step.get("succeeded", 0)
                fail = step.get("failed", 0)
                lines.append(f"{icon} Distributed: {ok} platforms ✓  {fail} failed")
            elif name == "hermes_healthcheck":
                diag = step.get("diagnosis", {})
                sev = diag.get("severity", "?")
                summ = diag.get("summary", "")[:80]
                lines.append(f"{icon} Claude report [{sev}]: {summ}")
            else:
                lines.append(f"{icon} {name}: {step.get('status')}")

        if r.get("message"):
            lines.append(f"\n📊 {r['message']}")

        vid_id = r.get("video_id")
        if vid_id:
            lines.append(f"\n📱 Manual upload (if auto failed):")
            lines.append(f"/upload_tiktok {vid_id}")

        return "\n".join(lines)

    except Exception:
        pass

    return start_msg + "\n\n" + result


def _cmd_mastra(raw: str) -> str:
    # /mastra POST /pipeline/fetch-chapters {"k":"v"}
    rest = raw.replace("/mastra", "", 1).strip()
    if not rest:
        return "Usage: /mastra <METHOD> <path> [json]"
    parts = rest.split(" ", 2)
    if len(parts) < 2:
        return "Usage: /mastra <METHOD> <path> [json]"

    method = parts[0].upper().strip()
    path = parts[1].strip()
    body: Dict[str, Any] = {}
    if len(parts) == 3 and parts[2].strip():
        body = json.loads(parts[2].strip())

    url = f"{MASTRA_URL}{path}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=60)
        else:
            response = requests.request(method, url, json=body, timeout=90)
        response.raise_for_status()
        data = response.json() if response.text else {"ok": True}
        return f"Success: {method} {path}\n{_safe_json(data)}"
    except Exception as exc:
        return f"Failed: {method} {path}\n{exc}"


def _dispatch_command(text: str, chat_id: str) -> str:
    parts = text.strip().split()
    if not parts:
        return _help_text()

    cmd = parts[0].split("@")[0].lower()
    if cmd in ("/start", "/help"):
        return _help_text()
    if cmd == "/whoami":
        return f"Chat ID: {chat_id}\nUse this value in TELEGRAM_ALLOWED_CHAT_IDS."
    if cmd == "/status":
        return _cmd_status(parts)
    if cmd == "/fetch_trending":
        return _cmd_fetch_trending(parts)
    if cmd == "/fetch_chapter":
        return _cmd_fetch_chapter(parts)
    if cmd == "/download_panels":
        return _cmd_download_panels(parts)
    if cmd == "/check_duplicates":
        return _cmd_check_duplicates(parts)
    if cmd == "/generate_video":
        return _cmd_generate_video(parts)
    if cmd == "/upload_tiktok":
        return _cmd_upload_tiktok(parts)
    if cmd == "/upload_youtube":
        return _cmd_upload_youtube(parts)
    if cmd == "/download_youtube":
        return _cmd_download_youtube(text, chat_id)
    if cmd == "/detect_shadow_ban":
        return _cmd_shadow(parts)
    if cmd == "/arb_discover":
        return _cmd_arb_discover(parts)
    if cmd == "/arb_source":
        return _cmd_arb_source(parts)
    if cmd == "/arb_download":
        return _cmd_arb_download(parts)
    if cmd == "/arb_distribute":
        return _cmd_arb_distribute(parts)
    if cmd == "/research_topic":
        return _cmd_research_topic(text)
    if cmd == "/research_status":
        return _cmd_research_status(parts)
    if cmd == "/research_channel":
        return _cmd_research_channel(text)
    if cmd == "/plan_campaign":
        return _cmd_plan_campaign(text)
    if cmd == "/recover_last_run":
        return _cmd_recover_last_run()
    if cmd == "/deerflow":
        return _cmd_deerflow(text)
    if cmd == "/summon":
        return _cmd_summon(text)
    if cmd == "/hermes_order":
        return _cmd_hermes_order(text)
    if cmd == "/aito_hermes":
        return _cmd_aito_hermes(text)
    if cmd == "/worker":
        return _cmd_worker(text)
    if cmd == "/mastra":
        return _cmd_mastra(text)
    if cmd == "/aito_accounts":
        return _cmd_aito_accounts(parts)
    if cmd == "/aito_restrictions":
        return _cmd_aito_restrictions(parts)
    if cmd == "/aito_post_all":
        return _cmd_aito_post_all(text)
    if cmd == "/aito_post_accounts":
        return _cmd_aito_post_accounts(text)
    if cmd == "/aito_post_json":
        return _cmd_aito_post_json(text)
    if cmd == "/aito_publish_status":
        return _cmd_aito_publish_status(parts)
    if cmd == "/aito_link_publish":
        return _cmd_aito_link_publish(text)
    if cmd == "/hermes_logs":
        return _cmd_hermes_logs(parts)
    # ── Gig Copilot ──────────────────────────────────────────────────────────
    if cmd == "/gig_new":
        return _cmd_gig_new(text, chat_id)
    if cmd == "/gig_draft":
        return _cmd_gig_draft(parts)
    if cmd == "/gig_score":
        return _cmd_gig_score(parts)
    if cmd == "/gig_submit_done":
        return _cmd_gig_submit_done(parts, chat_id)
    if cmd == "/gig_today":
        return _cmd_gig_today(chat_id)
    if cmd == "/gig_week":
        return _cmd_gig_week(chat_id)
    # ── Obsidian ───────────────────────────────────────────────────────────────────
    if cmd == "/ob_save":
        return _cmd_ob_save(parts)
    if cmd == "/ob_log":
        return _cmd_ob_log(chat_id)
    if cmd == "/ob_template":
        return _cmd_ob_template(parts, text)
    # ── Finance / Side-Hustle strategy ──────────────────────────────────────────
    if cmd == "/finance_discover":
        return _cmd_finance_discover(parts)
    if cmd == "/finance_briefs":
        return _cmd_finance_briefs(parts)
    if cmd == "/referral_list":
        return _cmd_referral_list(parts)
    if cmd == "/earnings_scan":
        return _cmd_earnings_scan(parts)
    if cmd == "/weekly_recap":
        return _cmd_weekly_recap(parts)
    if cmd == "/finance_post":
        return _cmd_finance_post(parts)
    if cmd == "/finance_video":
        return _cmd_finance_video(parts)
    if cmd == "/finance_ai_video":
        return _cmd_finance_ai_video(parts)
    if cmd == "/list_avatars":
        return _cmd_list_avatars(parts)
    if cmd == "/finance_pipeline":
        return _cmd_finance_pipeline(parts)
    if cmd == "/viral_pipeline":
        return _cmd_viral_pipeline(parts)
    return f"Unknown command: {cmd}\nUse /help for all commands."


def _extract_text(update: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        return None, None
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id")) if chat.get("id") is not None else None
    text = message.get("text")
    return chat_id, text


def _check_keyword_trigger(text: str) -> Optional[str]:
    """
    Check if a non-command message contains a keyword trigger.
    Returns the reply string if matched, else None.
    Keywords are checked in priority order (more specific first).
    """
    lower = text.lower().strip()
    for keyword, reply in KEYWORD_TRIGGERS.items():
        if keyword in lower:
            return reply
    return None


def run_bot() -> None:
    if not TOKEN:
        raise TelegramBotError("Set TELEGRAM_BOT_TOKEN in environment")

    logger.info("Starting Telegram bot polling loop")
    offset = 0
    consecutive_poll_errors = 0

    while True:
        try:
            data = _tg_api(
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": 25,
                    "allowed_updates": ["message", "edited_message"],
                },
                timeout=35,
            )
            consecutive_poll_errors = 0
            updates = data.get("result", [])

            for update in updates:
                offset = update.get("update_id", offset) + 1
                chat_id, text = _extract_text(update)
                if not chat_id or not text:
                    continue

                # ── Keyword triggers: respond to ANY user, not just admins ─────
                if not text.startswith("/"):
                    keyword_reply = _check_keyword_trigger(text)
                    if keyword_reply:
                        logger.info(f"Keyword trigger from {chat_id}: '{text[:30]}'")
                        _send_message(chat_id, keyword_reply)
                    continue

                # ── Commands: admin-only ─────────────────────────────────
                if not _is_authorized(chat_id):
                    _send_message(chat_id, "Unauthorized chat. Ask admin to allow this chat ID.")
                    continue

                logger.info(f"Telegram command from {chat_id}: {text}")
                try:
                    reply = _dispatch_command(text, chat_id)
                except Exception as exc:
                    logger.exception("Command error")
                    reply = f"Command failed: {exc}"
                _send_message(chat_id, reply)

        except Exception as exc:
            consecutive_poll_errors += 1
            sleep_for = min(max(POLL_INTERVAL, 2) * (2 ** min(consecutive_poll_errors, 5)), 60)
            logger.exception(
                f"Polling error ({consecutive_poll_errors} consecutive): {exc}. Backing off for {sleep_for}s"
            )
            time.sleep(sleep_for)


if __name__ == "__main__":
    run_bot()

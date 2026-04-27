#!/usr/bin/env python3
"""
Telegram control bot for manga automation.

Features:
- Trigger worker and agent endpoints from Telegram commands
- View service health and memory stats
- Restrict access to specific chat IDs

Environment:
- TELEGRAM_BOT_TOKEN (required)
- TELEGRAM_ALLOWED_CHAT_IDS (optional comma-separated chat IDs)
- TELEGRAM_POLL_INTERVAL (optional, default: 2)
- TELEGRAM_WORKER_URL (optional, default: http://python-worker:8080)
- TELEGRAM_MASTRA_URL (optional, default: http://manga-agents:3001)
"""
from __future__ import annotations

import json
import os
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
POLL_INTERVAL = int(os.getenv("TELEGRAM_POLL_INTERVAL", "2"))

_raw_ids = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
ALLOWED_CHAT_IDS = {
    x.strip() for x in _raw_ids.split(",") if x.strip()
}


class TelegramBotError(RuntimeError):
    pass


def _tg_api(method: str, payload: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    if not TOKEN:
        raise TelegramBotError("TELEGRAM_BOT_TOKEN is missing")
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise TelegramBotError(f"Telegram API error ({method}): {data}")
    return data


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


def _help_text() -> str:
    return (
        "Manga Automation Telegram Control\n\n"
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
        "/mastra <METHOD> <path> [json]\n"
        "/worker <path> [json]\n\n"
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
        "/fetch_trending 25\n"
        "/research_topic best anime comedy shorts channels\n"
        "/summon Find top romance manga and create 3 posts\n"
        "/worker /yt-to-tiktok {\"url\":\"https://...\"}\n"
        "/gig_new dataannotation prompt-writing Write a haiku about AI\n"
    )


def _cmd_status(_: List[str]) -> str:
    wk_ok, wk = _get_json(f"{WORKER_URL}/health")
    ms_ok, ms = _get_json(f"{MASTRA_URL}/health")
    mem_ok, mem = _post_json(f"{WORKER_URL}/api/memory/stats", {})

    return (
        "System Status\n\n"
        f"Worker: {'OK' if wk_ok else 'FAIL'}\n{_safe_json(wk)}\n\n"
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


def _cmd_worker_route(path: str, body: Dict[str, Any]) -> str:
    ok, data = _post_json(f"{WORKER_URL}{path}", body)
    prefix = "Success" if ok else "Failed"
    return f"{prefix}: {path}\n{_safe_json(data)}"


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
    if cmd == "/worker":
        return _cmd_worker(text)
    if cmd == "/mastra":
        return _cmd_mastra(text)
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
    return f"Unknown command: {cmd}\nUse /help for all commands."


def _extract_text(update: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    message = update.get("message") or update.get("edited_message") or {}
    if not message:
        return None, None
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id")) if chat.get("id") is not None else None
    text = message.get("text")
    return chat_id, text


def run_bot() -> None:
    if not TOKEN:
        raise TelegramBotError("Set TELEGRAM_BOT_TOKEN in environment")

    logger.info("Starting Telegram bot polling loop")
    offset = 0

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
            updates = data.get("result", [])

            for update in updates:
                offset = update.get("update_id", offset) + 1
                chat_id, text = _extract_text(update)
                if not chat_id or not text:
                    continue
                if not _is_authorized(chat_id):
                    _send_message(chat_id, "Unauthorized chat. Ask admin to allow this chat ID.")
                    continue
                if not text.startswith("/"):
                    continue

                logger.info(f"Telegram command from {chat_id}: {text}")
                try:
                    reply = _dispatch_command(text, chat_id)
                except Exception as exc:
                    logger.exception("Command error")
                    reply = f"Command failed: {exc}"
                _send_message(chat_id, reply)

        except Exception as exc:
            logger.exception(f"Polling error: {exc}")
            time.sleep(max(POLL_INTERVAL, 2))


if __name__ == "__main__":
    run_bot()

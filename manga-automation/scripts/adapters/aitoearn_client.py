#!/usr/bin/env python3
"""
Official AiToEarn integration client (API/MCP-aware).

This adapter centralizes:
- endpoint + auth configuration
- resilient HTTP calls (retry/backoff)
- startup validation and diagnostics
- stage/action wrappers used by pipeline + Hermes
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def normalize_publish_time(value: Any) -> str | None:
    """
    Coerce a schedule time into the exact format AiToEarn requires:
    a UTC ISO-8601 timestamp ending in 'Z' (e.g. 2026-06-03T08:00:00Z).

    Accepts ISO strings (with/without 'Z' or offset) and epoch seconds/ms.
    Returns None when empty or unparseable (caller should then publish now).
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # Epoch seconds or milliseconds.
    try:
        if re.fullmatch(r"\d+(\.\d+)?", s):
            num = float(s)
            if num > 1e12:  # milliseconds
                num /= 1000.0
            dt = datetime.fromtimestamp(num, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError, OSError):
        pass

    # ISO-8601 (datetime.fromisoformat understands offsets; map trailing Z first).
    try:
        iso = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def _json_env(name: str, default: dict[str, str]) -> dict[str, str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return dict(default)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except Exception:
        pass
    return dict(default)


def _join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _walk(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


@dataclass(frozen=True)
class AiToEarnConfig:
    base_url: str
    api_key: str
    mcp_url: str
    sse_url: str
    transport: str
    timeout_sec: int
    retries: int
    retry_backoff_sec: float
    primary_enabled: bool
    fallback_local_enabled: bool
    stage_paths: dict[str, str]
    action_paths: dict[str, str]
    stage_mcp_tool_map: dict[str, str]
    action_mcp_tool_map: dict[str, str]
    health_path: str


DEFAULT_STAGE_PATHS: dict[str, str] = {
    "trend": "/api/ops/trend",
    "create": "/api/ops/create",
    "publish": "/api/ops/publish",
    "engage": "/api/ops/engage",
    "monetize": "/api/ops/monetize",
}

DEFAULT_ACTION_PATHS: dict[str, str] = {
    "pipeline": "/api/ops/pipeline",
    "status": "/api/ops/status",
}

DEFAULT_STAGE_MCP_TOOL_MAP: dict[str, str] = {
    "trend": "listTaskMarket",
    "create": "getDraftGenerationPricing",
    "engage": "listInteractionRecords",
    "monetize": "getMyBalance",
}

DEFAULT_ACTION_MCP_TOOL_MAP: dict[str, str] = {
    "status": "getMyProfile",
}

PUBLISH_TOOL_BY_PLATFORM: dict[str, str] = {
    "tiktok": "publishPostToTiktok",
    "youtube": "publishPostToYoutube",
    "youtube_shorts": "publishPostToYoutube",
    "instagram": "publishPostToInstagram",
    "instagram_reels": "publishPostToInstagram",
    "facebook": "publishPostToFacebook",
    "threads": "publishPostToThreads",
    "pinterest": "publishPostToPinterest",
    "bilibili": "publishPostToBilibili",
    "douyin": "publishPostToDouyin",
    "kwai": "publishPostToKwai",
    "twitter": "publishPostToTwitter",
}

PLATFORM_ALIASES: dict[str, str] = {
    "youtube_shorts": "youtube",
    "instagram_reels": "instagram",
}


class AiToEarnClient:
    def __init__(self):
        self.config = AiToEarnConfig(
            base_url=(os.environ.get("AITOEARN_BASE_URL") or "https://aitoearn.ai").rstrip("/"),
            api_key=(os.environ.get("AITOEARN_API_KEY") or "").strip(),
            mcp_url=(os.environ.get("AITOEARN_MCP_URL") or "https://aitoearn.ai/api/unified/mcp").strip(),
            sse_url=(os.environ.get("AITOEARN_SSE_URL") or "https://aitoearn.ai/api/unified/sse").strip(),
            transport=(os.environ.get("AITOEARN_TRANSPORT") or "mcp").strip().lower(),
            timeout_sec=int(os.environ.get("AITOEARN_TIMEOUT_SEC", "60")),
            retries=max(0, int(os.environ.get("AITOEARN_RETRIES", "2"))),
            retry_backoff_sec=max(0.25, float(os.environ.get("AITOEARN_RETRY_BACKOFF_SEC", "1.5"))),
            primary_enabled=_bool_env("AITOEARN_PRIMARY", default=False),
            fallback_local_enabled=_bool_env("AITOEARN_FALLBACK_LOCAL", default=True),
            stage_paths=_json_env("AITOEARN_STAGE_PATHS_JSON", DEFAULT_STAGE_PATHS),
            action_paths=_json_env("AITOEARN_ACTION_PATHS_JSON", DEFAULT_ACTION_PATHS),
            stage_mcp_tool_map=_json_env("AITOEARN_STAGE_MCP_TOOL_MAP_JSON", DEFAULT_STAGE_MCP_TOOL_MAP),
            action_mcp_tool_map=_json_env("AITOEARN_ACTION_MCP_TOOL_MAP_JSON", DEFAULT_ACTION_MCP_TOOL_MAP),
            health_path=(os.environ.get("AITOEARN_HEALTH_PATH") or "/api/ops/health").strip(),
        )

    @property
    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.config.api_key:
            h["x-api-key"] = self.config.api_key
        if self.config.transport == "mcp":
            h["Accept"] = "application/json, text/event-stream"
        return h

    def enabled(self) -> bool:
        return self.config.primary_enabled and bool(self.config.api_key)

    def startup_validation(self) -> dict[str, Any]:
        issues: list[str] = []
        warnings: list[str] = []

        if self.config.primary_enabled and not self.config.api_key:
            issues.append("AITOEARN_PRIMARY is enabled but AITOEARN_API_KEY is empty")
        if self.config.base_url.endswith("aitoearn.cn") and "aitoearn.ai" in self.config.mcp_url:
            warnings.append("base_url and mcp_url appear to target different environments")
        if self.config.base_url.endswith("aitoearn.ai") and "aitoearn.cn" in self.config.mcp_url:
            warnings.append("base_url and mcp_url appear to target different environments")

        health_probe: dict[str, Any] | None = None
        if self.enabled():
            health_probe = self.health()
            if not health_probe.get("ok"):
                warnings.append(f"health check failed: {health_probe.get('error', 'unknown')}")

        return {
            "ok": len(issues) == 0,
            "primary_enabled": self.config.primary_enabled,
            "effective_enabled": self.enabled(),
            "base_url": self.config.base_url,
            "mcp_url": self.config.mcp_url,
            "sse_url": self.config.sse_url,
            "transport": self.config.transport,
            "issues": issues,
            "warnings": warnings,
            "health": health_probe,
        }

    def _mcp_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.config.mcp_url or _join_url(self.config.base_url, "/api/unified/mcp")
        payload = {
            "jsonrpc": "2.0",
            "id": str(int(time.time() * 1000)),
            "method": method,
            "params": params or {},
        }
        resp = requests.post(
            url=url,
            headers=self.headers,
            json=payload,
            timeout=self.config.timeout_sec,
        )
        if resp.status_code in {401, 403}:
            return {"ok": False, "status_code": resp.status_code, "error": "unauthorized_or_forbidden", "url": url}
        resp.raise_for_status()
        out = _safe_json(resp)
        if isinstance(out, dict) and out.get("error"):
            err = out.get("error") or {}
            code = err.get("code")
            msg = err.get("message", "mcp_error")
            return {"ok": False, "status_code": resp.status_code, "error": f"mcp_error:{code}:{msg}", "url": url, "body": out}
        return {"ok": True, "status_code": resp.status_code, "result": out.get("result", out), "url": url}

    def _mcp_initialize(self) -> dict[str, Any]:
        return self._mcp_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "manga-automation", "version": "1.0"},
            },
        )

    def _mcp_list_tools(self) -> dict[str, Any]:
        init = self._mcp_initialize()
        if not init.get("ok"):
            return init
        return self._mcp_request("tools/list", {})

    def _mcp_call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        init = self._mcp_initialize()
        if not init.get("ok"):
            return init
        return self._mcp_request("tools/call", {"name": tool_name, "arguments": arguments or {}})

    def _mcp_result_text(self, result: dict[str, Any] | None) -> str:
        result = result or {}
        content = result.get("content")
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return "\n".join(parts)

    def _parse_accounts_from_text(self, text: str) -> list[dict[str, str]]:
        blocks = text.split("  - ")
        accounts: list[dict[str, str]] = []
        for block in blocks:
            type_match = re.search(r"\n\s*type:\s*([^\n]+)", block)
            id_match = re.search(r"\n\s*id:\s*([^\n]+)", block)
            account_match = re.search(r"\n\s*account:\s*([^\n]+)", block)
            if not type_match or not id_match:
                continue
            accounts.append(
                {
                    "type": type_match.group(1).strip().strip('"').strip("'").lower(),
                    "id": id_match.group(1).strip().strip('"').strip("'"),
                    "account": (account_match.group(1).strip().strip('"').strip("'") if account_match else ""),
                }
            )
        return accounts

    def _normalize_platform(self, name: str) -> str:
        key = (name or "").strip().lower()
        return PLATFORM_ALIASES.get(key, key)

    def _extract_topics(self, payload: dict[str, Any]) -> list[str]:
        topics = payload.get("topics")
        if isinstance(topics, list):
            return [str(t).lstrip("#").strip() for t in topics if str(t).strip()]
        hashtags = payload.get("hashtags")
        if isinstance(hashtags, list):
            return [str(t).lstrip("#").strip() for t in hashtags if str(t).strip()]
        return []

    def _extract_video_url(self, payload: dict[str, Any]) -> str:
        for key in ("video_url", "videoUrl", "media_url", "mediaUrl", "public_video_url", "publicVideoUrl", "url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        fallback = os.environ.get("AITOEARN_DEFAULT_VIDEO_URL", "").strip()
        return fallback

    def _extract_img_urls(self, payload: dict[str, Any]) -> list[str]:
        for key in ("img_urls", "imgUrlList", "imageUrls"):
            value = payload.get(key)
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]
        return []

    def _extract_flow_id(self, text: str) -> str:
        patterns = [
            r"FlowId:\s*([A-Za-z0-9\-]+)",
            r"flowId:\s*([A-Za-z0-9\-]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_flow_id_from_result(self, result: Any) -> str:
        keys = {"flowid", "flow_id", "publishtaskid", "taskid"}
        for key, value in _walk(result):
            if str(key).replace("-", "").replace("_", "").lower() in keys and isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _parse_status_text(self, text: str) -> dict[str, Any]:
        status_raw = ""
        error_msg = ""
        work_link = ""
        for key, value in re.findall(r"(?m)^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", text):
            k = key.strip()
            v = value.strip().strip('"')
            if k == "status":
                status_raw = v
            elif k == "errorMsg":
                error_msg = v
            elif k == "workLink":
                work_link = v
        return {"status_raw": status_raw, "error_msg": error_msg, "work_link": work_link}

    def _status_success(self, parsed: dict[str, Any]) -> bool:
        raw = str(parsed.get("status_raw", "")).strip().lower()
        if raw in {"published", "success", "done"}:
            return True
        try:
            status_num = int(raw)
            # AiToEarn commonly uses numeric states where 2 means published.
            return status_num >= 2
        except Exception:
            return False

    def _build_publish_arguments(self, platform: str, account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title") or payload.get("caption") or "AI generated content").strip()
        desc = str(payload.get("desc") or payload.get("description") or payload.get("caption") or title).strip()
        video_url = self._extract_video_url(payload)
        cover_url = str(payload.get("cover_url") or payload.get("coverUrl") or "").strip()
        topics = self._extract_topics(payload)
        if platform == "tiktok" and topics:
            topics = topics[:5]
        img_urls = self._extract_img_urls(payload)
        publish_time = normalize_publish_time(
            payload.get("publishTime") or payload.get("publish_time")
        )

        args: dict[str, Any] = {
            "accountId": account_id,
            "title": title,
            "desc": desc,
        }
        if publish_time:
            args["publishTime"] = publish_time
        if topics:
            args["topics"] = topics
        if cover_url:
            args["coverUrl"] = cover_url
        if video_url:
            args["videoUrl"] = video_url
        if img_urls:
            args["imgUrlList"] = img_urls
        # AiToEarn may reject arbitrary userTaskId formats with "Validation failed".
        # Only pass explicit user_task_id when caller provides one intentionally.
        explicit_user_task_id = payload.get("user_task_id") or payload.get("userTaskId")
        if explicit_user_task_id:
            args["userTaskId"] = str(explicit_user_task_id)

        if platform in {"youtube", "youtube_shorts"}:
            args["option"] = {
                "privacyStatus": os.environ.get("AITOEARN_YT_PRIVACY", "public"),
                "license": os.environ.get("AITOEARN_YT_LICENSE", "youtube"),
                "categoryId": os.environ.get("AITOEARN_YT_CATEGORY_ID", "22"),
            }
        if platform == "pinterest":
            board_id = (
                payload.get("board_id")
                or payload.get("boardId")
                or payload.get("pinterest_board_id")
                or os.environ.get("AITOEARN_PINTEREST_BOARD_ID", "").strip()
            )
            if board_id:
                args["boardId"] = str(board_id)
        return args

    def _run_publish_fanout(self, payload: dict[str, Any]) -> dict[str, Any]:
        list_accounts = self._mcp_call_tool("getAllAccounts", {})
        if not list_accounts.get("ok"):
            return list_accounts

        accounts_text = self._mcp_result_text(list_accounts.get("result", {}))
        accounts = self._parse_accounts_from_text(accounts_text)
        if not accounts:
            raw_result = list_accounts.get("result", {})
            data_obj = raw_result.get("data") if isinstance(raw_result, dict) else None
            list_obj = []
            if isinstance(data_obj, dict):
                list_obj = data_obj.get("list") or data_obj.get("accounts") or []
            if isinstance(data_obj, list):
                list_obj = data_obj
            if isinstance(list_obj, list):
                for item in list_obj:
                    if not isinstance(item, dict):
                        continue
                    account_id = item.get("id") or item.get("accountId")
                    account_type = item.get("type") or item.get("platform")
                    if account_id and account_type:
                        accounts.append(
                            {
                                "id": str(account_id),
                                "type": str(account_type).lower(),
                                "account": str(item.get("account") or item.get("nickname") or ""),
                            }
                        )
        if not accounts:
            return {"ok": False, "error": "no_connected_accounts_found"}

        channels_raw = payload.get("channels")
        targets: set[str] = set()
        if isinstance(channels_raw, list):
            for item in channels_raw:
                key = self._normalize_platform(str(item))
                if key in PUBLISH_TOOL_BY_PLATFORM:
                    targets.add(key)
        platform_arg = self._normalize_platform(str(payload.get("platform", "")))
        if platform_arg and platform_arg in PUBLISH_TOOL_BY_PLATFORM:
            targets.add(platform_arg)
        if not targets:
            for acc in accounts:
                ptype = self._normalize_platform(acc.get("type", ""))
                if ptype in PUBLISH_TOOL_BY_PLATFORM:
                    targets.add(ptype)

        selected_accounts_by_platform: dict[str, set[str]] = {}
        raw_selected_map = payload.get("selected_accounts")
        if isinstance(raw_selected_map, dict):
            for platform_key, ids in raw_selected_map.items():
                pnorm = self._normalize_platform(str(platform_key))
                if isinstance(ids, list):
                    selected_accounts_by_platform[pnorm] = {str(x).strip() for x in ids if str(x).strip()}
                elif isinstance(ids, str) and ids.strip():
                    selected_accounts_by_platform[pnorm] = {x.strip() for x in ids.split(",") if x.strip()}
        raw_account_ids = payload.get("account_ids")
        selected_account_ids: set[str] = set()
        if isinstance(raw_account_ids, list):
            selected_account_ids = {str(x).strip() for x in raw_account_ids if str(x).strip()}
        elif isinstance(raw_account_ids, str) and raw_account_ids.strip():
            selected_account_ids = {x.strip() for x in raw_account_ids.split(",") if x.strip()}

        results: list[dict[str, Any]] = []
        channel_stats: dict[str, dict[str, int]] = {}
        poll_attempts = int(os.environ.get("AITOEARN_PUBLISH_STATUS_POLL_ATTEMPTS", "4"))
        poll_sleep_sec = float(os.environ.get("AITOEARN_PUBLISH_STATUS_POLL_SEC", "3"))
        unverified_as_failure = _bool_env("AITOEARN_UNVERIFIED_AS_FAILURE", default=False)

        for acc in accounts:
            platform = self._normalize_platform(acc.get("type", ""))
            if platform not in targets:
                continue
            account_id = acc.get("id", "")
            if selected_account_ids and account_id not in selected_account_ids:
                continue
            platform_selected = selected_accounts_by_platform.get(platform)
            if platform_selected and account_id not in platform_selected:
                continue
            tool_name = PUBLISH_TOOL_BY_PLATFORM.get(platform)
            if not tool_name:
                continue

            args = self._build_publish_arguments(platform, acc["id"], payload)
            # Most platforms require at least one media input; skip if missing.
            has_media = bool(args.get("videoUrl")) or bool(args.get("imgUrlList"))
            if not has_media and platform in {"tiktok", "youtube", "youtube_shorts", "instagram", "facebook", "threads", "pinterest", "douyin", "kwai", "bilibili"}:
                results.append(
                    {
                        "platform": platform,
                        "account_id": account_id,
                        "account": acc.get("account"),
                        "success": False,
                        "error": "missing_media_url",
                    }
                )
                channel_stats.setdefault(platform, {"success": 0, "failed": 0})["failed"] += 1
                continue

            call = self._mcp_call_tool(tool_name, args)
            if not call.get("ok"):
                results.append(
                    {
                        "platform": platform,
                        "account_id": account_id,
                        "account": acc.get("account"),
                        "success": False,
                        "error": call.get("error"),
                        "tool": tool_name,
                    }
                )
                channel_stats.setdefault(platform, {"success": 0, "failed": 0})["failed"] += 1
                continue

            call_result = call.get("result", {})
            call_text = self._mcp_result_text(call_result)
            if isinstance(call_result, dict) and call_result.get("isError"):
                results.append(
                    {
                        "platform": platform,
                        "account_id": account_id,
                        "account": acc.get("account"),
                        "success": False,
                        "error": call_text or "tool_reported_error",
                        "verification": "tool_error",
                        "tool": tool_name,
                    }
                )
                channel_stats.setdefault(platform, {"success": 0, "failed": 0})["failed"] += 1
                continue
            flow_id = self._extract_flow_id(call_text) or self._extract_flow_id_from_result(call_result)
            status_payload: dict[str, Any] | None = None
            status_ok = True
            verification = "accepted_unverified"

            if flow_id:
                for _ in range(max(1, poll_attempts)):
                    status_call = self._mcp_call_tool("getPublishingTaskStatus", {"flowId": flow_id})
                    if not status_call.get("ok"):
                        status_ok = False
                        status_payload = {"error": status_call.get("error", "status_call_failed")}
                        verification = "status_error"
                        break
                    status_text = self._mcp_result_text(status_call.get("result", {}))
                    parsed = self._parse_status_text(status_text)
                    status_payload = parsed
                    if parsed.get("error_msg"):
                        status_ok = False
                        verification = "status_error"
                        break
                    if self._status_success(parsed):
                        status_ok = True
                        verification = "status_confirmed"
                        break
                    time.sleep(max(0.5, poll_sleep_sec))
                if verification == "accepted_unverified":
                    verification = "status_pending_or_unknown"

            success = status_ok
            if not flow_id and unverified_as_failure:
                success = False
                verification = "unverified_treated_as_failure"
            results.append(
                {
                    "platform": platform,
                    "account_id": account_id,
                    "account": acc.get("account"),
                    "success": success,
                    "flow_id": flow_id,
                    "status": status_payload,
                    "verification": verification,
                    "tool": tool_name,
                }
            )
            stats = channel_stats.setdefault(platform, {"success": 0, "failed": 0})
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1

        if not results:
            return {
                "ok": False,
                "error": "no_eligible_accounts_for_target_platforms",
                "targets": sorted(targets),
            }

        published_count = sum(1 for row in results if row.get("success"))
        failed_count = sum(1 for row in results if not row.get("success"))
        confirmed_count = sum(1 for row in results if row.get("verification") == "status_confirmed")
        unverified_count = sum(1 for row in results if row.get("verification") in {"accepted_unverified", "status_pending_or_unknown"})
        return {
            "ok": True,
            "status_code": 200,
            "result": {
                "published_count": published_count,
                "failed_count": failed_count,
                "confirmed_count": confirmed_count,
                "unverified_count": unverified_count,
                "ready_count": len(results),
                "uploader": "aitoearn_mcp_fanout",
                "path": "mcp_primary",
                "channels": channel_stats,
                "results": results,
            },
            "url": self.config.mcp_url,
            "tool": "mcp_publish_fanout",
        }

    def list_accounts(self, platform: str | None = None) -> dict[str, Any]:
        if self.config.transport != "mcp":
            return {"ok": False, "error": "accounts_listing_supported_in_mcp_only"}

        call = self._mcp_call_tool("getAllAccounts", {})
        if not call.get("ok"):
            return call
        text = self._mcp_result_text(call.get("result", {}))
        accounts = self._parse_accounts_from_text(text)
        if not accounts:
            return {"ok": True, "status_code": call.get("status_code"), "result": {"count": 0, "accounts": []}, "url": call.get("url")}

        normalized = self._normalize_platform(platform or "")
        if normalized:
            accounts = [a for a in accounts if self._normalize_platform(a.get("type", "")) == normalized]
        return {
            "ok": True,
            "status_code": call.get("status_code"),
            "result": {"count": len(accounts), "accounts": accounts},
            "url": call.get("url"),
            "tool": "getAllAccounts",
        }

    def get_publishing_task_status(self, flow_id: str) -> dict[str, Any]:
        if self.config.transport != "mcp":
            return {"ok": False, "error": "publish_status_supported_in_mcp_only"}
        flow_id = str(flow_id or "").strip()
        if not flow_id:
            return {"ok": False, "error": "flow_id_required"}
        call = self._mcp_call_tool("getPublishingTaskStatus", {"flowId": flow_id})
        if not call.get("ok"):
            return call
        text = self._mcp_result_text(call.get("result", {}))
        parsed = self._parse_status_text(text)
        return {
            "ok": True,
            "status_code": call.get("status_code"),
            "result": {
                "flow_id": flow_id,
                "status_raw": parsed.get("status_raw"),
                "success": self._status_success(parsed),
                "error_msg": parsed.get("error_msg"),
                "work_link": parsed.get("work_link"),
                "raw_text": text,
            },
            "url": call.get("url"),
            "tool": "getPublishingTaskStatus",
        }

    def get_publish_restrictions(self, platforms: list[str]) -> dict[str, Any]:
        if self.config.transport != "mcp":
            return {"ok": False, "error": "publish_restrictions_supported_in_mcp_only"}
        normalized = [self._normalize_platform(p) for p in platforms if str(p).strip()]
        if not normalized:
            normalized = ["tiktok", "youtube", "instagram", "facebook", "threads", "pinterest"]
        call = self._mcp_call_tool("publishRestrictions", {"platforms": normalized})
        if not call.get("ok"):
            return call
        text = self._mcp_result_text(call.get("result", {}))
        return {
            "ok": True,
            "status_code": call.get("status_code"),
            "result": {"platforms": normalized, "text": text},
            "url": call.get("url"),
            "tool": "publishRestrictions",
        }

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = _join_url(self.config.base_url, path)
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = requests.request(
                    method=method.upper(),
                    url=url,
                    headers=self.headers,
                    json=body or {},
                    timeout=self.config.timeout_sec,
                )
                if resp.status_code in {401, 403}:
                    return {
                        "ok": False,
                        "status_code": resp.status_code,
                        "error": "unauthorized_or_forbidden",
                        "url": url,
                        "body": _safe_json(resp),
                    }
                if resp.status_code == 429 and attempt <= self.config.retries + 1:
                    time.sleep(self.config.retry_backoff_sec * attempt)
                    continue
                if 500 <= resp.status_code < 600 and attempt <= self.config.retries + 1:
                    time.sleep(self.config.retry_backoff_sec * attempt)
                    continue
                resp.raise_for_status()
                payload = _safe_json(resp)
                if isinstance(payload, dict):
                    code = payload.get("code")
                    if isinstance(code, int) and code >= 400:
                        return {
                            "ok": False,
                            "status_code": resp.status_code,
                            "error": f"remote_application_error:{code}",
                            "url": url,
                            "body": payload,
                        }
                return {"ok": True, "status_code": resp.status_code, "result": payload, "url": url}
            except requests.RequestException as exc:
                if attempt > self.config.retries + 1:
                    return {
                        "ok": False,
                        "status_code": None,
                        "error": str(exc),
                        "url": url,
                    }
                time.sleep(self.config.retry_backoff_sec * attempt)

    def health(self) -> dict[str, Any]:
        if self.config.transport == "mcp":
            return self._mcp_list_tools()
        path = self.config.health_path
        return self._request("POST", path, {"probe": "health"})

    def _infer_publish_tool(self, payload: dict[str, Any]) -> str | None:
        platform = str(payload.get("platform", "")).strip().lower()
        if platform:
            return PUBLISH_TOOL_BY_PLATFORM.get(platform)
        channels = payload.get("channels")
        if isinstance(channels, list):
            for channel in channels:
                name = str(channel).strip().lower()
                if name in PUBLISH_TOOL_BY_PLATFORM:
                    return PUBLISH_TOOL_BY_PLATFORM[name]
        return None

    def run_stage(self, stage: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.config.transport == "mcp":
            body = payload or {}
            if stage == "publish":
                return self._run_publish_fanout(body)
            tool_name = self.config.stage_mcp_tool_map.get(stage)
            if not tool_name:
                return {"ok": False, "error": f"no_mcp_tool_mapping:{stage}"}
            call = self._mcp_call_tool(tool_name, body.get("mcp_arguments", body))
            if not call.get("ok"):
                return call
            result = call.get("result", {})
            return {"ok": True, "status_code": call.get("status_code"), "result": result, "url": call.get("url"), "tool": tool_name}
        path = self.config.stage_paths.get(stage)
        if not path:
            return {"ok": False, "error": f"no_stage_path_configured:{stage}"}
        return self._request("POST", path, payload or {})

    def run_action(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.config.transport == "mcp":
            body = payload or {}
            tool_name = self.config.action_mcp_tool_map.get(action)
            if not tool_name:
                return {"ok": False, "error": f"no_mcp_tool_mapping_action:{action}"}
            call = self._mcp_call_tool(tool_name, body.get("mcp_arguments", body))
            if not call.get("ok"):
                return call
            result = call.get("result", {})
            return {"ok": True, "status_code": call.get("status_code"), "result": result, "url": call.get("url"), "tool": tool_name}
        path = self.config.action_paths.get(action)
        if not path:
            return {"ok": False, "error": f"no_action_path_configured:{action}"}
        return self._request("POST", path, payload or {})


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"text": (resp.text or "")[:2000]}


CLIENT = AiToEarnClient()


def enabled() -> bool:
    return CLIENT.enabled()


def startup_validation() -> dict[str, Any]:
    return CLIENT.startup_validation()


def health() -> dict[str, Any]:
    return CLIENT.health()


def run_stage(stage: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return CLIENT.run_stage(stage, payload or {})


def run_action(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return CLIENT.run_action(action, payload or {})


def list_accounts(platform: str | None = None) -> dict[str, Any]:
    return CLIENT.list_accounts(platform=platform)


def get_publishing_task_status(flow_id: str) -> dict[str, Any]:
    return CLIENT.get_publishing_task_status(flow_id=flow_id)


def get_publish_restrictions(platforms: list[str]) -> dict[str, Any]:
    return CLIENT.get_publish_restrictions(platforms=platforms)

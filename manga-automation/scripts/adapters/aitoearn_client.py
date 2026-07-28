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


CHANNELS_V2_PLATFORM_NAMES: set[str] = {
    "tiktok",
    "youtube",
    "instagram",
    "facebook",
    "threads",
    "pinterest",
    "bilibili",
    "douyin",
    "kwai",
    "twitter",
}


class AiToEarnClient:
    def __init__(self):
        self._tool_names_cache: set[str] | None = None
        self._accounts_cache: dict[str, Any] | None = None
        self._accounts_cache_at: float = 0.0
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

    def _mcp_tool_names(self) -> set[str]:
        if self._tool_names_cache is None:
            listed = self._mcp_list_tools()
            tools = listed.get("result", {}).get("tools", []) if listed.get("ok") else []
            self._tool_names_cache = {
                str(t.get("name")).strip()
                for t in tools
                if isinstance(t, dict) and t.get("name")
            }
        return self._tool_names_cache

    def _uses_channels_v2_publish(self) -> bool:
        return "createChannelPublishFlow" in self._mcp_tool_names()

    def _publish_status_tool(self) -> tuple[str, str]:
        """Return (tool_name, id_argument_key) for publish status polling."""
        if "getChannelPublishRecordByFlowId" in self._mcp_tool_names():
            return "getChannelPublishRecordByFlowId", "flowId"
        return "getPublishingTaskStatus", "flowId"

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

    def _parse_accounts_from_structured(self, raw_result: dict[str, Any] | None) -> list[dict[str, str]]:
        raw_result = raw_result or {}
        data_obj = raw_result.get("data") if isinstance(raw_result, dict) else None
        list_obj: list[Any] = []
        if isinstance(data_obj, dict):
            list_obj = data_obj.get("list") or data_obj.get("accounts") or []
        elif isinstance(data_obj, list):
            list_obj = data_obj

        accounts: list[dict[str, str]] = []
        for item in list_obj:
            if not isinstance(item, dict):
                continue
            account_id = item.get("id") or item.get("accountId")
            account_type = item.get("type") or item.get("platform") or item.get("accountType")
            if account_id and account_type:
                accounts.append(
                    {
                        "id": str(account_id),
                        "type": str(account_type).lower(),
                        "account": str(item.get("account") or item.get("nickname") or ""),
                    }
                )
        return accounts

    def _parse_accounts_from_publish_records(self, text: str) -> list[dict[str, str]]:
        """Parse unique AiToEarn channel accounts from listChannelPublishRecords output."""
        accounts: list[dict[str, str]] = []
        seen: set[str] = set()
        for block in text.split("- id: ")[1:]:
            id_match = re.search(r"accountId:\s*([^\n]+)", block)
            type_match = re.search(r"accountType:\s*([^\n]+)", block)
            if not id_match or not type_match:
                continue
            account_id = id_match.group(1).strip().strip('"').strip("'")
            account_type = type_match.group(1).strip().strip('"').strip("'").lower()
            if not account_id or account_id in seen:
                continue
            seen.add(account_id)
            display = account_id.split("_", 1)[-1] if "_" in account_id else account_id
            accounts.append({"id": account_id, "type": account_type, "account": display})
        return accounts

    def _parse_accounts_from_group_list_text(self, text: str) -> list[dict[str, str]]:
        """Parse getAccountListByGroupId / legacy getAllAccounts text formats."""
        accounts = self._parse_accounts_from_text(text)
        if accounts:
            return accounts

        parsed: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in text.splitlines():
            if not re.search(r"\b(id|type|account|name)\s*:", line, flags=re.IGNORECASE):
                continue
            type_match = re.search(r"Type:\s*([^,\n]+)", line, flags=re.IGNORECASE)
            id_match = re.search(r"ID:\s*([^,\n]+)", line, flags=re.IGNORECASE)
            account_match = re.search(r"(?:Account|Name):\s*([^,\n]+)", line, flags=re.IGNORECASE)
            if not type_match or not id_match:
                continue
            account_id = id_match.group(1).strip().strip('"').strip("'")
            if not account_id or account_id in seen:
                continue
            seen.add(account_id)
            parsed.append(
                {
                    "id": account_id,
                    "type": type_match.group(1).strip().strip('"').strip("'").lower(),
                    "account": (account_match.group(1).strip().strip('"').strip("'") if account_match else ""),
                }
            )
        return parsed

    def _fetch_accounts_from_account_groups(self) -> list[dict[str, str]]:
        """Self-hosted AiToEarn (legacy MCP): getAccountGroupList → getAccountListByGroupId."""
        groups_call = self._mcp_call_tool("getAccountGroupList", {})
        if not groups_call.get("ok"):
            return []

        groups_text = self._mcp_result_text(groups_call.get("result", {}))
        group_ids: list[str] = []
        for match in re.finditer(r"ID:\s*([^,\n]+)", groups_text):
            group_id = match.group(1).strip()
            if group_id and group_id not in group_ids:
                group_ids.append(group_id)

        accounts: list[dict[str, str]] = []
        seen: set[str] = set()
        for group_id in group_ids:
            list_call = self._mcp_call_tool("getAccountListByGroupId", {"groupId": group_id})
            if not list_call.get("ok"):
                continue
            list_text = self._mcp_result_text(list_call.get("result", {}))
            for acc in self._parse_accounts_from_group_list_text(list_text):
                if acc["id"] in seen:
                    continue
                seen.add(acc["id"])
                accounts.append(acc)
        return accounts

    def _fetch_accounts_from_publish_records(self) -> list[dict[str, str]]:
        accounts: list[dict[str, str]] = []
        seen: set[str] = set()
        page_size = max(20, int(os.environ.get("AITOEARN_ACCOUNTS_PAGE_SIZE", "100")))
        max_pages = max(1, int(os.environ.get("AITOEARN_ACCOUNTS_MAX_PAGES", "10")))

        for page in range(1, max_pages + 1):
            call = self._mcp_call_tool(
                "listChannelPublishRecords",
                {"pageNo": page, "pageSize": page_size},
            )
            if not call.get("ok"):
                break
            text = self._mcp_result_text(call.get("result", {}))
            batch = self._parse_accounts_from_publish_records(text)
            if not batch:
                break
            for acc in batch:
                if acc["id"] in seen:
                    continue
                seen.add(acc["id"])
                accounts.append(acc)
            if len(text.split("- id: ")) - 1 < page_size:
                break
        return accounts

    def _collect_connected_accounts(self) -> tuple[list[dict[str, str]], str | None, dict[str, Any] | None]:
        """
        Resolve AiToEarn-connected accounts across MCP API versions.

        - Cloud v2: listChannelPublishRecords (getAllAccounts removed)
        - Self-hosted legacy: getAccountGroupList + getAccountListByGroupId
        - Older cloud: getAllAccounts text blocks
        """
        # Cloud v2 and self-hosted use different tools — try the reliable paths first.
        accounts = self._fetch_accounts_from_publish_records()
        if accounts:
            return accounts, "listChannelPublishRecords", None

        accounts = self._fetch_accounts_from_account_groups()
        if accounts:
            return accounts, "getAccountGroupList+getAccountListByGroupId", None

        configured = os.environ.get("AITOEARN_LIST_ACCOUNTS_TOOLS", "getAllAccounts,listChannelAccounts")
        errors: list[str] = []
        for tool_name in [part.strip() for part in configured.split(",") if part.strip()]:
            call = self._mcp_call_tool(tool_name, {})
            if not call.get("ok"):
                errors.append(f"{tool_name}:{call.get('error', 'failed')}")
                continue
            text = self._mcp_result_text(call.get("result", {}))
            accounts = self._parse_accounts_from_text(text)
            if not accounts:
                accounts = self._parse_accounts_from_structured(call.get("result"))
            if not accounts and tool_name == "getAccountGroupList":
                accounts = self._fetch_accounts_from_account_groups()
                if accounts:
                    return accounts, "getAccountGroupList+getAccountListByGroupId", call
            if accounts:
                return accounts, tool_name, call

        return [], None, {"errors": errors} if errors else None

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
        keys = {"flowid", "flow_id", "publishtaskid"}
        for key, value in _walk(result):
            if str(key).replace("-", "").replace("_", "").lower() in keys and isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_task_ids_from_result(self, result: Any) -> list[str]:
        task_ids: list[str] = []
        for key, value in _walk(result):
            if str(key).replace("-", "").replace("_", "").lower() != "taskid":
                continue
            if isinstance(value, str) and value.strip() and value.strip() not in task_ids:
                task_ids.append(value.strip())
        return task_ids

    def _channels_v2_platform(self, platform: str) -> str:
        return self._normalize_platform(platform)

    def _append_topics_to_body(self, body: str, payload: dict[str, Any], *, limit: int | None = None) -> str:
        topics = self._extract_topics(payload)
        if limit is not None:
            topics = topics[:limit]
        if not topics:
            return body
        hashtag_line = " ".join(f"#{t.lstrip('#')}" for t in topics if t)
        if not hashtag_line:
            return body
        if hashtag_line in body:
            return body
        return f"{body}\n{hashtag_line}".strip() if body else hashtag_line

    def _assets_cdn_base(self) -> str:
        return (
            os.environ.get("AITOEARN_ASSETS_CDN") or "https://assets.aitoearn.ai"
        ).rstrip("/")

    def _is_aitoearn_asset_url(self, url: str) -> bool:
        u = (url or "").strip().lower()
        return u.startswith(self._assets_cdn_base().lower() + "/")

    def _default_media_group_id(self, media_type: str) -> str | None:
        """Resolve Default media group id for video|img via MCP listMediaGroups."""
        want = "video" if media_type == "video" else "img"
        call = self._mcp_call_tool("listMediaGroups", {"pageNo": 1, "pageSize": 50})
        if not call.get("ok"):
            return None
        text = self._mcp_result_text(call.get("result", {}))
        blocks = re.split(r"\n\s*-\s+", text)
        for block in blocks:
            type_m = re.search(r"(?m)^\s*type:\s*(\w+)", block)
            id_m = re.search(r"(?m)^\s*id:\s*([^\n]+)", block)
            if not type_m or not id_m:
                continue
            if type_m.group(1).strip().lower() == want:
                return id_m.group(1).strip()
        return None

    def _media_public_url_from_relative(self, relative_path: str) -> str:
        rel = relative_path.strip().lstrip("/")
        return f"{self._assets_cdn_base()}/{rel}"

    def register_remote_media(
        self,
        url: str,
        *,
        media_type: str = "video",
        title: str = "",
        desc: str = "",
        thumb_url: str = "",
    ) -> dict[str, Any]:
        """Ingest a remote URL into AiToEarn media library → assets.aitoearn.ai CDN URL.

        External hosts (litterbox, tmpfiles, etc.) fail createChannelPublishFlow
        validation on TikTok/IG/FB; AiToEarn-hosted assets URLs succeed.
        """
        raw = (url or "").strip()
        if not raw:
            return {"ok": False, "error": "url_required"}
        if self._is_aitoearn_asset_url(raw):
            return {"ok": True, "public_url": raw, "uploaded": False, "provider": "assets_passthrough"}

        if "createMedia" not in self._mcp_tool_names():
            return {"ok": False, "error": "createMedia_tool_unavailable"}

        mtype = "video" if media_type == "video" else "img"
        group_id = self._default_media_group_id(mtype)
        if not group_id:
            return {"ok": False, "error": f"media_group_not_found:{mtype}"}

        args: dict[str, Any] = {
            "groupId": group_id,
            "type": mtype,
            "url": raw,
        }
        if title:
            args["title"] = title[:120]
        if desc:
            args["desc"] = desc[:500]
        if thumb_url and mtype == "video":
            args["thumbUrl"] = thumb_url

        created = self._mcp_call_tool("createMedia", args)
        if not created.get("ok"):
            return {"ok": False, "error": created.get("error") or "createMedia_failed"}
        created_text = self._mcp_result_text(created.get("result", {}))
        id_m = re.search(r"ID:\s*([a-f0-9]+)", created_text, flags=re.IGNORECASE)
        media_id = id_m.group(1) if id_m else ""

        listed = self._mcp_call_tool(
            "listMedia", {"pageNo": 1, "pageSize": 20, "groupId": group_id}
        )
        list_text = self._mcp_result_text(listed.get("result", {}) if listed.get("ok") else {})
        relative = ""
        thumb_rel = ""
        for block in re.split(r"\n\s*-\s+", list_text):
            if media_id and media_id not in block and f"id: {media_id}" not in block:
                # Prefer exact id match when we have one; otherwise take first url: line.
                if media_id:
                    continue
            url_m = re.search(r"(?m)^\s*url:\s*([^\n]+)", block)
            if not url_m:
                continue
            candidate = url_m.group(1).strip().strip('"')
            if candidate.startswith("http"):
                # Already absolute (unusual); use as-is.
                relative = candidate
            else:
                relative = candidate
            thumb_m = re.search(r"(?m)^\s*thumbUrl:\s*([^\n]+)", block)
            if thumb_m:
                thumb_rel = thumb_m.group(1).strip().strip('"')
            if media_id and (f"id: {media_id}" in block or media_id in block):
                break

        if not relative:
            return {
                "ok": False,
                "error": "createMedia_ok_but_url_not_found",
                "media_id": media_id,
                "raw": created_text[:300],
            }

        public_url = (
            relative
            if relative.startswith("http")
            else self._media_public_url_from_relative(relative)
        )
        out: dict[str, Any] = {
            "ok": True,
            "public_url": public_url,
            "uploaded": True,
            "provider": "aitoearn_createMedia",
            "media_id": media_id,
            "group_id": group_id,
            "relative_path": relative if not relative.startswith("http") else "",
        }
        if thumb_rel:
            out["thumb_url"] = (
                thumb_rel
                if thumb_rel.startswith("http")
                else self._media_public_url_from_relative(thumb_rel)
            )
        return out

    def ensure_publish_media_urls(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Rewrite video/cover URLs onto assets.aitoearn.ai before channel fanout."""
        payload = dict(payload)
        title = str(payload.get("title") or payload.get("caption") or "").strip()
        desc = str(
            payload.get("desc") or payload.get("description") or payload.get("caption") or ""
        ).strip()
        video_url = self._extract_video_url(payload)
        cover_url = str(payload.get("cover_url") or payload.get("coverUrl") or "").strip()

        media_meta: dict[str, Any] = {}
        if video_url and not self._is_aitoearn_asset_url(video_url):
            hosted = self.register_remote_media(
                video_url,
                media_type="video",
                title=title or "shortform",
                desc=desc,
                thumb_url=cover_url,
            )
            media_meta["video"] = hosted
            if hosted.get("ok") and hosted.get("public_url"):
                payload["video_url"] = hosted["public_url"]
                payload["videoUrl"] = hosted["public_url"]
            else:
                payload["_media_host_error"] = hosted
                return payload
        elif video_url:
            payload["video_url"] = video_url
            payload["videoUrl"] = video_url

        if cover_url and not self._is_aitoearn_asset_url(cover_url):
            hosted_cover = self.register_remote_media(
                cover_url,
                media_type="img",
                title=(title or "thumb")[:80],
            )
            media_meta["cover"] = hosted_cover
            if hosted_cover.get("ok") and hosted_cover.get("public_url"):
                payload["cover_url"] = hosted_cover["public_url"]
                payload["coverUrl"] = hosted_cover["public_url"]
        elif cover_url:
            payload["cover_url"] = cover_url
            payload["coverUrl"] = cover_url

        if media_meta:
            payload["_aitoearn_media"] = media_meta
        return payload

    def _build_channels_v2_item_option(self, platform: str, payload: dict[str, Any]) -> dict[str, Any]:
        cover_url = str(payload.get("cover_url") or payload.get("coverUrl") or "").strip()
        video_url = self._extract_video_url(payload)
        topics = self._extract_topics(payload)

        if platform in {"youtube", "youtube_shorts"}:
            option: dict[str, Any] = {
                "privacyStatus": os.environ.get("AITOEARN_YT_PRIVACY", "public"),
                "license": os.environ.get("AITOEARN_YT_LICENSE", "youtube"),
                "categoryId": os.environ.get("AITOEARN_YT_CATEGORY_ID", "22"),
            }
            # tags are not in the official YouTube option schema — omit to avoid validation errors
            _ = topics
            return option

        if platform == "tiktok":
            option = {
                "source": "PULL_FROM_URL" if video_url else "FILE_UPLOAD",
                "privacy_level": os.environ.get(
                    "AITOEARN_TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE"
                ),
                "is_aigc": _bool_env("AITOEARN_TIKTOK_IS_AIGC", default=True),
            }
            return option

        if platform in {"instagram", "instagram_reels"}:
            # Schema only allows media_type / alt_text / collaborators / etc.
            # Do NOT put cover_url or caption into option (causes validation failures).
            return {"media_type": "REELS" if video_url else "IMAGE"}

        if platform == "twitter":
            # X requires short text; long captions from auto_caption fail validation.
            return {}

        if platform == "pinterest":
            board_id = (
                payload.get("board_id")
                or payload.get("boardId")
                or payload.get("pinterest_board_id")
                or os.environ.get("AITOEARN_PINTEREST_BOARD_ID", "").strip()
            )
            option: dict[str, Any] = {}
            if board_id:
                option["boardId"] = str(board_id)
            if cover_url:
                option["coverImageUrl"] = cover_url
            return option

        return {}

    def _build_channels_v2_flow_arguments(
        self,
        platform: str,
        account_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        title = str(payload.get("title") or payload.get("caption") or "AI generated content").strip()
        desc = str(payload.get("desc") or payload.get("description") or payload.get("caption") or title).strip()
        if platform == "tiktok":
            desc = self._append_topics_to_body(desc, payload, limit=5)
        elif platform == "twitter":
            desc = self._append_topics_to_body(desc, payload, limit=3)
        else:
            desc = self._append_topics_to_body(desc, payload)

        video_url = self._extract_video_url(payload)
        cover_url = str(payload.get("cover_url") or payload.get("coverUrl") or "").strip()
        img_urls = self._extract_img_urls(payload)
        publish_at = normalize_publish_time(payload.get("publishTime") or payload.get("publish_time"))
        if not publish_at:
            # Schedule a couple minutes out so publishChannelTaskNow can still fire immediately.
            publish_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        content: dict[str, Any] = {"title": title, "body": desc or title}
        if platform == "twitter":
            # X/Twitter rejects long anime-theory captions ("Publish content validation failed").
            tw_body = (desc or title).strip()
            # Prefer caption/body without a separate long title dump.
            tw_body = re.sub(r"\s+", " ", tw_body)
            if len(tw_body) > 260:
                tw_body = tw_body[:257].rstrip() + "..."
            content = {"title": (title[:80] or "Short").strip(), "body": tw_body}
        if video_url:
            content["media"] = [{"url": video_url}]
        elif img_urls:
            content["media"] = [{"url": url} for url in img_urls]
        if cover_url and platform != "twitter":
            content["cover"] = {"url": cover_url}

        # Official schema: taskId / userTaskId / materialGroupId / materialId only.
        context: dict[str, Any] = {}
        media_meta = payload.get("_aitoearn_media") if isinstance(payload.get("_aitoearn_media"), dict) else {}
        video_meta = media_meta.get("video") if isinstance(media_meta, dict) else None
        if isinstance(video_meta, dict):
            if video_meta.get("media_id"):
                context["materialId"] = str(video_meta["media_id"])
            if video_meta.get("group_id"):
                context["materialGroupId"] = str(video_meta["group_id"])
        explicit_user_task_id = payload.get("user_task_id") or payload.get("userTaskId")
        if explicit_user_task_id:
            context["userTaskId"] = str(explicit_user_task_id)

        item: dict[str, Any] = {
            "platform": self._channels_v2_platform(platform),
            "accountId": account_id,
            # Schema expects `option` as an object; omit-vs-undefined breaks Pinterest/X.
            "option": self._build_channels_v2_item_option(platform, payload) or {},
        }

        out: dict[str, Any] = {
            "content": content,
            "publishAt": publish_at,
            "items": [item],
        }
        if context:
            out["context"] = context
        return out

    def _maybe_publish_channel_tasks_now(self, result: dict[str, Any] | None) -> list[dict[str, Any]]:
        if "publishChannelTaskNow" not in self._mcp_tool_names():
            return []
        outcomes: list[dict[str, Any]] = []
        for task_id in self._extract_task_ids_from_result(result):
            call = self._mcp_call_tool("publishChannelTaskNow", {"taskId": task_id})
            outcomes.append({"task_id": task_id, "ok": call.get("ok"), "error": call.get("error")})
        return outcomes

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
        payload = self.ensure_publish_media_urls(payload)
        if payload.get("_media_host_error"):
            return {
                "ok": False,
                "error": "aitoearn_media_ingest_failed",
                "detail": payload.get("_media_host_error"),
            }

        accounts, accounts_source, _meta = self._collect_connected_accounts()
        if not accounts:
            return {
                "ok": False,
                "error": "no_connected_accounts_found",
                "hint": (
                    "Link social accounts to your AiToEarn API key in Settings, "
                    "or publish once from the AiToEarn dashboard so records exist."
                ),
                "meta": _meta,
            }

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
        use_channels_v2 = self._uses_channels_v2_publish()
        status_tool, status_id_key = self._publish_status_tool()

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
            if use_channels_v2:
                if self._channels_v2_platform(platform) not in CHANNELS_V2_PLATFORM_NAMES:
                    continue
                tool_name = "createChannelPublishFlow"
            else:
                tool_name = PUBLISH_TOOL_BY_PLATFORM.get(platform)
                if not tool_name or tool_name not in self._mcp_tool_names():
                    results.append(
                        {
                            "platform": platform,
                            "account_id": account_id,
                            "account": acc.get("account"),
                            "success": False,
                            "error": f"unsupported_or_missing_publish_tool:{tool_name}",
                            "tool": tool_name,
                        }
                    )
                    channel_stats.setdefault(platform, {"success": 0, "failed": 0})["failed"] += 1
                    continue

            if use_channels_v2:
                args = self._build_channels_v2_flow_arguments(platform, acc["id"], payload)
                has_media = bool(self._extract_video_url(payload)) or bool(self._extract_img_urls(payload))
            else:
                args = self._build_publish_arguments(platform, acc["id"], payload)
                has_media = bool(args.get("videoUrl")) or bool(args.get("imgUrlList"))
            # Most platforms require at least one media input; skip if missing.
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
            task_publish_results: list[dict[str, Any]] = []
            if use_channels_v2 and not call_result.get("isError"):
                task_publish_results = self._maybe_publish_channel_tasks_now(call_result)

            status_payload: dict[str, Any] | None = None
            status_ok = True
            verification = "accepted_unverified"

            if flow_id:
                for _ in range(max(1, poll_attempts)):
                    status_call = self._mcp_call_tool(status_tool, {status_id_key: flow_id})
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
                    "task_publish": task_publish_results or None,
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
                "uploader": "aitoearn_channels_v2_fanout" if use_channels_v2 else "aitoearn_mcp_fanout",
                "path": "mcp_channels_v2" if use_channels_v2 else "mcp_primary",
                "channels": channel_stats,
                "results": results,
            },
            "url": self.config.mcp_url,
            "tool": "mcp_publish_fanout",
        }

    def list_accounts(self, platform: str | None = None) -> dict[str, Any]:
        if self.config.transport != "mcp":
            return {"ok": False, "error": "accounts_listing_supported_in_mcp_only"}

        cache_ttl = max(0, int(os.environ.get("AITOEARN_ACCOUNTS_CACHE_SEC", "300")))
        cache_key = self._normalize_platform(platform or "") or "__all__"
        now = time.time()
        if (
            cache_ttl > 0
            and self._accounts_cache
            and (now - self._accounts_cache_at) < cache_ttl
            and cache_key in self._accounts_cache
        ):
            return dict(self._accounts_cache[cache_key])

        accounts, source_tool, meta = self._collect_connected_accounts()
        if not accounts:
            payload = {
                "ok": True,
                "status_code": 200,
                "result": {"count": 0, "accounts": []},
                "url": self.config.mcp_url,
                "warning": "no_connected_accounts_found",
                "hint": (
                    "No accounts returned from AiToEarn MCP. For self-hosted (localhost:9080), "
                    "open the AiToEarn UI → connect social accounts → Settings → API Key → "
                    "associate accounts with your key. Cloud keys do not work on local AiToEarn."
                ),
                "meta": meta,
            }
            if cache_ttl > 0:
                if not self._accounts_cache:
                    self._accounts_cache = {}
                self._accounts_cache[cache_key] = payload
                self._accounts_cache_at = now
            return payload

        normalized = self._normalize_platform(platform or "")
        if normalized:
            accounts = [a for a in accounts if self._normalize_platform(a.get("type", "")) == normalized]
        payload = {
            "ok": True,
            "status_code": 200,
            "result": {"count": len(accounts), "accounts": accounts},
            "url": self.config.mcp_url,
            "tool": source_tool or "unknown",
        }
        if cache_ttl > 0:
            if not self._accounts_cache:
                self._accounts_cache = {}
            self._accounts_cache[cache_key] = payload
            self._accounts_cache_at = now
        return payload

    def get_publishing_task_status(self, flow_id: str) -> dict[str, Any]:
        if self.config.transport != "mcp":
            return {"ok": False, "error": "publish_status_supported_in_mcp_only"}
        flow_id = str(flow_id or "").strip()
        if not flow_id:
            return {"ok": False, "error": "flow_id_required"}
        status_tool, status_id_key = self._publish_status_tool()
        call = self._mcp_call_tool(status_tool, {status_id_key: flow_id})
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
            "tool": status_tool,
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
                    json=body if method.upper() not in {"GET", "HEAD"} and body is not None else None,
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

    # ── AiToEarn Open Platform REST (Seedance video, images, channels) ─────────

    def api_key_configured(self) -> bool:
        return bool(self.config.api_key)

    def _unwrap_openplatform(self, response: dict[str, Any]) -> dict[str, Any]:
        if not response.get("ok"):
            return response
        payload = response.get("result")
        if not isinstance(payload, dict):
            return {"ok": True, "data": payload, "raw": response}
        code = payload.get("code")
        if isinstance(code, int) and code not in (0, 200):
            return {
                "ok": False,
                "error": payload.get("message") or f"openplatform_error:{code}",
                "code": code,
                "body": payload,
            }
        data = payload.get("data", payload)
        return {"ok": True, "data": data, "body": payload}

    def create_video_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key_configured():
            return {"ok": False, "error": "AITOEARN_API_KEY is required for Seedance video generation"}
        body = {k: v for k, v in payload.items() if v is not None}
        return self._unwrap_openplatform(
            self._request("POST", "/api/ai/video/generations", body),
        )

    def get_video_generation_status(self, task_id: str) -> dict[str, Any]:
        if not self.api_key_configured():
            return {"ok": False, "error": "AITOEARN_API_KEY is required"}
        task_id = str(task_id or "").strip()
        if not task_id:
            return {"ok": False, "error": "task_id is required"}
        return self._unwrap_openplatform(
            self._request("GET", f"/api/ai/video/generations/{task_id}"),
        )

    def list_video_generations(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        if not self.api_key_configured():
            return {"ok": False, "error": "AITOEARN_API_KEY is required"}
        return self._unwrap_openplatform(
            self._request(
                "GET",
                f"/api/ai/video/generations?page={max(1, page)}&pageSize={max(1, page_size)}",
            ),
        )

    def get_video_model_params(self) -> dict[str, Any]:
        if not self.api_key_configured():
            return {"ok": False, "error": "AITOEARN_API_KEY is required"}
        path = os.environ.get(
            "AITOEARN_VIDEO_MODELS_PATH",
            "/api/ai/video/generations/models",
        ).strip()
        return self._unwrap_openplatform(self._request("GET", path))

    def _video_terminal_status(self, status: str) -> str:
        raw = str(status or "").strip().lower()
        if raw in {"completed", "success", "succeeded", "done", "finished"}:
            return "completed"
        if raw in {"failed", "error", "cancelled", "canceled"}:
            return "failed"
        return "pending"

    def poll_video_generation(
        self,
        task_id: str,
        *,
        max_attempts: int | None = None,
        interval_sec: float | None = None,
    ) -> dict[str, Any]:
        attempts = max_attempts or int(os.environ.get("AITOEARN_VIDEO_POLL_MAX_ATTEMPTS", "60"))
        sleep_sec = interval_sec or float(os.environ.get("AITOEARN_VIDEO_POLL_INTERVAL_SEC", "10"))
        last: dict[str, Any] = {"ok": False, "error": "poll_not_started"}
        for attempt in range(1, attempts + 1):
            last = self.get_video_generation_status(task_id)
            if not last.get("ok"):
                return {**last, "attempts": attempt}
            data = last.get("data") or {}
            status = self._video_terminal_status(str(data.get("status", "")))
            if status == "completed":
                return {
                    "ok": True,
                    "task_id": task_id,
                    "status": data.get("status"),
                    "video_url": data.get("videoUrl") or data.get("video_url"),
                    "cover_url": data.get("coverUrl") or data.get("cover_url"),
                    "media_id": data.get("mediaId") or data.get("media_id"),
                    "group_id": data.get("groupId") or data.get("group_id"),
                    "data": data,
                    "attempts": attempt,
                }
            if status == "failed":
                err = data.get("error") or {}
                return {
                    "ok": False,
                    "task_id": task_id,
                    "status": data.get("status"),
                    "error": err.get("message") if isinstance(err, dict) else str(err or "generation_failed"),
                    "data": data,
                    "attempts": attempt,
                }
            time.sleep(max(1.0, sleep_sec))
        return {
            "ok": False,
            "error": "video_generation_timeout",
            "task_id": task_id,
            "attempts": attempts,
            "last": last,
        }

    def generate_video_and_wait(self, payload: dict[str, Any]) -> dict[str, Any]:
        created = self.create_video_generation(payload)
        if not created.get("ok"):
            return created
        data = created.get("data") or {}
        task_id = str(data.get("id") or data.get("taskId") or "").strip()
        if not task_id:
            return {"ok": False, "error": "missing_task_id_in_create_response", "create": created}
        polled = self.poll_video_generation(task_id)
        return {
            **polled,
            "create": created,
        }


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


def api_key_configured() -> bool:
    return CLIENT.api_key_configured()


def create_video_generation(payload: dict[str, Any]) -> dict[str, Any]:
    return CLIENT.create_video_generation(payload)


def get_video_generation_status(task_id: str) -> dict[str, Any]:
    return CLIENT.get_video_generation_status(task_id)


def list_video_generations(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    return CLIENT.list_video_generations(page=page, page_size=page_size)


def get_video_model_params() -> dict[str, Any]:
    return CLIENT.get_video_model_params()


def poll_video_generation(task_id: str, **kwargs: Any) -> dict[str, Any]:
    return CLIENT.poll_video_generation(task_id, **kwargs)


def generate_video_and_wait(payload: dict[str, Any]) -> dict[str, Any]:
    return CLIENT.generate_video_and_wait(payload)

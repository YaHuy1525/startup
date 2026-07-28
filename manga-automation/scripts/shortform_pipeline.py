"""Short-form Reddit → meme video → AiToEarn publish pipeline.

Bridges ``short-form-pipeline/reddit_to_script`` into manga-automation so
QwenPaw agents can orchestrate generation and posting via AiToEarn MCP.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _safe_parent(path: Path, index: int) -> Path | None:
    try:
        return path.parents[index]
    except IndexError:
        return None


# Host layout: <startup>/manga-automation/scripts/...  → sibling short-form-pipeline
# Docker layout: mount short-form-pipeline at /short-form-pipeline (or set SHORTFORM_ROOT).
_SHORTFORM_CANDIDATES = [
    Path(os.environ["SHORTFORM_ROOT"]) if os.environ.get("SHORTFORM_ROOT") else None,
    Path("/short-form-pipeline"),
    REPO_ROOT / "short-form-pipeline",
]
_grand = _safe_parent(Path(__file__).resolve(), 3)
if _grand is not None:
    _SHORTFORM_CANDIDATES.append(_grand / "short-form-pipeline")

SHORTFORM_ROOT = next(
    (p for p in _SHORTFORM_CANDIDATES if p is not None and p.exists()),
    REPO_ROOT / "short-form-pipeline",
)
if str(SHORTFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(SHORTFORM_ROOT))

# Load short-form .env (FIRECRAWL optional, OPENAI / GIPHY / PEXELS required).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(SHORTFORM_ROOT / "reddit_to_script" / ".env")
load_dotenv(SHORTFORM_ROOT / ".env")


def _import_shortform():
    from reddit_to_script import (  # type: ignore
        fetch_reddit,
        generate_script,
        make_meme_video,
        footage,
        tts,
    )

    return fetch_reddit, generate_script, make_meme_video, footage, tts


def stage_fetch(body: dict[str, Any]) -> dict[str, Any]:
    fetch_reddit, *_ = _import_shortform()
    subreddit = str(body.get("subreddit") or "tifu")
    time_filter = str(body.get("time") or body.get("time_filter") or "week")
    limit = int(body.get("limit") or body.get("count") or 3)
    try:
        stories = fetch_reddit.fetch_stories(subreddit, time_filter, limit)
    except Exception as exc:  # noqa: BLE001 - surface Reddit throttle/network cleanly
        return {
            "ok": False,
            "stage": "fetch",
            "subreddit": subreddit,
            "error": str(exc),
            "count": 0,
            "stories": [],
        }
    return {
        "ok": True,
        "stage": "fetch",
        "subreddit": subreddit,
        "count": len(stories),
        "stories": [asdict(s) for s in stories],
    }


def stage_script(body: dict[str, Any]) -> dict[str, Any]:
    fetch_reddit, generate_script, *_ = _import_shortform()
    style = str(body.get("style") or "meme")
    story_data = body.get("story")
    if not story_data:
        fetched = stage_fetch(body)
        if not fetched["stories"]:
            return {"ok": False, "stage": "script", "error": "no_stories"}
        story_data = fetched["stories"][0]

    story = fetch_reddit.RedditStory(
        title=story_data.get("title", ""),
        url=story_data.get("url", ""),
        body=story_data.get("body", ""),
        author=story_data.get("author", ""),
        upvotes=int(story_data.get("upvotes") or 0),
    )
    scenes = generate_script.build_scenes(story, style=style)
    return {
        "ok": True,
        "stage": "script",
        "style": style,
        "story": asdict(story),
        "scenes": scenes,
        "scene_count": len(scenes),
    }


def stage_find_memes(body: dict[str, Any]) -> dict[str, Any]:
    _, _, _, footage, _ = _import_shortform()
    scenes = body.get("scenes") or []
    used: set[str] = set()
    picks = []
    for i, scene in enumerate(scenes, start=1):
        text = scene.get("text") or ""
        terms = scene.get("searchTerms") or scene.get("search_terms") or []
        clip = footage.resolve_clip(terms, scene_text=text, used_ids=used)
        if clip.giphy_id:
            used.add(clip.giphy_id)
        picks.append(
            {
                "index": i,
                "text": text,
                "searchTerms": terms,
                "url": clip.url,
                "source": clip.source,
                "title": clip.title,
                "giphy_id": clip.giphy_id,
                "query_used": clip.query_used,
                "reason": clip.reason,
            }
        )
    return {"ok": True, "stage": "find_memes", "picks": picks, "count": len(picks)}


def stage_voice(body: dict[str, Any]) -> dict[str, Any]:
    _, _, _, _, tts = _import_shortform()
    from reddit_to_script import config as sf_config  # type: ignore

    scenes = body.get("scenes") or []
    job_id = str(body.get("job_id") or f"voice-{int(time.time())}")
    job_dir = sf_config.ASSETS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, scene in enumerate(scenes, start=1):
        text = scene.get("text") or ""
        out = job_dir / f"scene-{i:02d}.mp3"
        sa = tts.voice_scene(text, out)
        results.append(
            {
                "index": i,
                "path": str(sa.path),
                "duration": sa.duration,
                "word_count": len(sa.words),
            }
        )
    return {"ok": True, "stage": "voice", "job_id": job_id, "scenes": results}


def stage_render(body: dict[str, Any]) -> dict[str, Any]:
    """Render a short. Use ``format=anime_theory`` (or style) for anime theory."""
    fmt = str(body.get("format") or body.get("style") or "meme").strip().lower()
    if fmt in ("anime_theory", "anime-theory", "theory"):
        return stage_anime_theory(body)

    _, generate_script, make_meme_video, *_ = _import_shortform()
    scenes_raw = body.get("scenes") or []
    if not scenes_raw and body.get("story"):
        scripted = stage_script(body)
        if not scripted.get("ok"):
            return scripted
        scenes_raw = scripted["scenes"]
    if not scenes_raw:
        return {"ok": False, "stage": "render", "error": "no_scenes"}

    inputs = [
        make_meme_video.SceneInput(
            text=s.get("text", ""),
            search_terms=s.get("searchTerms") or s.get("search_terms") or [],
        )
        for s in scenes_raw
    ]
    slug = generate_script.slugify(
        (body.get("story") or {}).get("title") or body.get("title") or "meme"
    )
    out_name = body.get("filename") or f"meme-{time.strftime('%Y%m%d')}-{slug}.mp4"
    mp4 = make_meme_video.make_video(inputs, out_name=out_name)
    return {
        "ok": True,
        "stage": "render",
        "format": "meme",
        "file": str(mp4),
        "filename": mp4.name,
        "size_mb": round(mp4.stat().st_size / 1_048_576, 2),
        "scene_count": len(inputs),
    }


def _load_anime_theory_reference(body: dict[str, Any]) -> str:
    """Optional YouTube / local transcript for pacing (CLI parity)."""
    ref_file = str(body.get("reference_file") or body.get("referenceFile") or "").strip()
    ref_url = str(body.get("reference_url") or body.get("referenceUrl") or "").strip()
    if not ref_file and not ref_url:
        return ""
    try:
        from reddit_to_script import youtube_transcript  # type: ignore
    except Exception:
        return ""
    if ref_file:
        return youtube_transcript.load_reference(ref_file, english_only=True)
    return youtube_transcript.fetch_transcript(ref_url, english_only=True)


def stage_anime_theory(body: dict[str, Any]) -> dict[str, Any]:
    """Topic → anime-theory script → AniList/Safebooru visuals → AnimeTheory MP4."""
    from reddit_to_script import config as sf_config  # type: ignore
    from reddit_to_script import generate_script, make_anime_theory_video  # type: ignore

    topic = str(body.get("topic") or body.get("title") or "").strip()
    anime = str(body.get("anime") or body.get("series") or "").strip()
    context = str(body.get("context") or body.get("notes") or "").strip()
    scenes_raw = body.get("scenes") or []
    title = str(body.get("title") or topic or "Anime Theory").strip()
    long_form = bool(
        body.get("long")
        or body.get("long_form")
        or body.get("reference_url")
        or body.get("referenceUrl")
        or body.get("reference_file")
        or body.get("referenceFile")
    )
    show_title = bool(body.get("show_title") or body.get("showTitle"))
    max_seconds = body.get("max_seconds")
    if max_seconds is None:
        max_seconds = body.get("maxSeconds")
    if max_seconds is not None:
        max_seconds = float(max_seconds)

    if not scenes_raw:
        if not topic:
            story = body.get("story") or {}
            topic = str(story.get("title") or "").strip()
            context = context or str(story.get("body") or "").strip()
        if not topic:
            return {"ok": False, "stage": "anime_theory", "error": "topic_required"}
        reference = _load_anime_theory_reference(body)
        if reference and not body.get("long") and not body.get("long_form"):
            long_form = True
        scripted = generate_script.build_anime_theory_scenes(
            topic,
            anime=anime,
            context=context,
            long=long_form,
            reference_transcript=reference,
        )
        scenes_raw = scripted["scenes"]
        anime = anime or str(scripted.get("anime") or "")
        title = str(scripted.get("title") or title)
        music_mood = str(scripted.get("music") or body.get("music") or "").strip() or None
        if scripted.get("style_exemplar"):
            print(
                f"  [hermes-style] matched exemplar: "
                f"{scripted['style_exemplar'].get('title')} "
                f"({scripted['style_exemplar'].get('words')}w) "
                f"from {scripted.get('style_channel')}",
                flush=True,
            )
    else:
        music_mood = str(body.get("music") or body.get("music_mood") or "").strip() or None

    if body.get("dry_run"):
        return {
            "ok": True,
            "stage": "anime_theory",
            "dry_run": True,
            "title": title,
            "anime": anime,
            "music": music_mood,
            "long": long_form,
            "scenes": scenes_raw,
            "scene_count": len(scenes_raw),
        }

    inputs = [
        make_anime_theory_video.SceneInput(
            text=s.get("text", ""),
            search_terms=s.get("searchTerms") or s.get("search_terms") or [],
            anime=str(s.get("anime") or anime),
        )
        for s in scenes_raw
    ]
    slug = generate_script.slugify(title)
    out_name = (
        body.get("filename")
        or f"anime-theory-{time.strftime('%Y%m%d-%H%M%S')}-{slug}.mp4"
    )
    if max_seconds is None:
        max_seconds = (
            sf_config.MAX_ANIME_THEORY_LONG_SECONDS
            if long_form
            else sf_config.MAX_ANIME_THEORY_SECONDS
        )
    burn_title = title.upper()[:48] if show_title else None
    mp4 = make_anime_theory_video.make_video(
        inputs,
        out_name=out_name,
        anime_hint=anime,
        title=burn_title or title,  # BGM hint; Remotion burn-in only when show_title
        max_seconds=float(max_seconds),
        music_mood=music_mood,
        render_timeout=3600 if long_form else 1800,
    )

    result: dict[str, Any] = {
        "ok": True,
        "stage": "anime_theory",
        "format": "anime_theory",
        "title": title,
        "anime": anime,
        "music": music_mood,
        "long": long_form,
        "file": str(mp4),
        "filename": mp4.name,
        "size_mb": round(mp4.stat().st_size / 1_048_576, 2),
        "scene_count": len(inputs),
        "scenes": scenes_raw,
    }

    if body.get("publish"):
        channels = body.get("channels") or [
            "tiktok",
            "youtube",
            "instagram",
            "facebook",
            "threads",
            "twitter",
            "pinterest",
        ]
        pub = stage_publish(
            {
                **body,
                "file": str(mp4),
                "title": title,
                "anime": anime,
                "scenes": scenes_raw,
                "channels": channels,
                "auto_caption": True,
                "auto_thumbnail": True,
                # Clear raw scene-text caption so captioner agent writes a real one
                "caption": body.get("caption") or "",
                "desc": body.get("desc") or body.get("caption") or "",
            }
        )
        result["publish"] = pub
        result["ok"] = result["ok"] and bool(pub.get("ok"))

    return result


def run_anime_theory_pipeline(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full E2E: topic → script → render → caption + thumb → AiToEarn publish.

    Defaults ``publish=True`` (TikTok / Instagram / Facebook). Pass
    ``publish:false`` or ``dry_run:true`` to stop earlier.
    """
    body = dict(body or {})
    topic = str(body.get("topic") or body.get("title") or body.get("objective") or "").strip()
    if not topic and not body.get("scenes"):
        return {
            "ok": False,
            "success": False,
            "pipeline": "anime_theory",
            "error": "topic_required",
        }

    # Normalize aliases from dashboard / Mastra
    if topic and not body.get("topic"):
        body["topic"] = topic
    if body.get("series") and not body.get("anime"):
        body["anime"] = body["series"]

    dry_run = bool(body.get("dry_run"))
    # Default publish ON for the named pipeline (override with publish:false)
    publish = bool(body.get("publish", True)) and not dry_run
    channels = body.get("channels") or [
        "tiktok",
        "youtube",
        "instagram",
        "facebook",
        "threads",
        "twitter",
        "pinterest",
    ]
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(",") if c.strip()]

    steps: list[dict[str, Any]] = []
    gen_body = {
        **body,
        "topic": body.get("topic") or topic,
        "channels": channels,
        "publish": False,  # publish handled below with auto caption/thumb
        "dry_run": dry_run,
    }
    rendered = stage_anime_theory(gen_body)
    steps.append(
        {
            "stage": "anime_theory",
            "ok": rendered.get("ok"),
            "title": rendered.get("title"),
            "file": rendered.get("file"),
            "scene_count": rendered.get("scene_count"),
            "dry_run": rendered.get("dry_run"),
            "error": rendered.get("error"),
        }
    )
    if not rendered.get("ok"):
        return {
            "ok": False,
            "success": False,
            "pipeline": "anime_theory",
            "steps": steps,
            "error": rendered.get("error") or "anime_theory_failed",
            "result": rendered,
        }

    out: dict[str, Any] = {
        "ok": True,
        "success": True,
        "pipeline": "anime_theory",
        "title": rendered.get("title"),
        "anime": rendered.get("anime"),
        "topic": body.get("topic") or topic,
        "context": body.get("context") or "",
        "file": rendered.get("file"),
        "filename": rendered.get("filename"),
        "size_mb": rendered.get("size_mb"),
        "scenes": rendered.get("scenes"),
        "scene_count": rendered.get("scene_count"),
        "channels": channels,
        "dry_run": dry_run,
        "published": False,
        "steps": steps,
    }

    if dry_run:
        out["publish_skipped"] = True
        return out

    if publish:
        pub = stage_publish(
            {
                **body,
                "file": rendered["file"],
                "title": rendered.get("title") or topic,
                "anime": rendered.get("anime") or body.get("anime") or "",
                "scenes": rendered.get("scenes") or [],
                "channels": channels,
                "auto_caption": True,
                "auto_thumbnail": True,
                "caption": body.get("caption") or "",
                "desc": body.get("desc") or "",
            }
        )
        steps.append(
            {
                "stage": "publish",
                "ok": pub.get("ok"),
                "title": pub.get("title"),
                "public_url": pub.get("public_url"),
                "cover_url": pub.get("cover_url"),
                "error": pub.get("error"),
            }
        )
        pub_result = pub.get("result") or {}
        out["publish"] = pub
        out["caption"] = pub.get("caption")
        out["hashtags"] = pub.get("hashtags")
        out["public_url"] = pub.get("public_url")
        out["cover_url"] = pub.get("cover_url")
        out["published"] = bool(pub.get("ok"))
        out["published_count"] = pub_result.get("published_count")
        out["failed_count"] = pub_result.get("failed_count")
        out["ok"] = bool(pub.get("ok"))
        out["success"] = out["ok"]
        out["steps"] = steps
        if not pub.get("ok"):
            out["error"] = pub.get("error") or "publish_failed"
    else:
        out["publish_skipped"] = True

    # Persist to Supabase/Postgres (videos + anime_theory_runs + workflow_executions)
    try:
        from scripts import anime_theory_store

        stored = anime_theory_store.save_anime_theory_run(out)
        out["db"] = stored
        if stored.get("video_id"):
            out["video_id"] = stored["video_id"]
        if stored.get("run_id"):
            out["run_id"] = stored["run_id"]
    except Exception as exc:  # noqa: BLE001
        out["db"] = {"ok": False, "error": str(exc)}

    return out


def stage_caption(body: dict[str, Any]) -> dict[str, Any]:
    """shortform-captioner: write title/caption/hashtags for publish."""
    try:
        from reddit_to_script import caption_writer  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "stage": "caption", "error": str(exc)}

    title = str(body.get("title") or body.get("topic") or "").strip()
    if not title:
        return {"ok": False, "stage": "caption", "error": "title_required"}
    anime = str(body.get("anime") or body.get("series") or "").strip()
    scenes = body.get("scenes") if isinstance(body.get("scenes"), list) else None
    hook = str(body.get("hook") or body.get("context") or "").strip()
    channels = body.get("channels") or body.get("platforms")
    if isinstance(channels, str):
        channels = [channels]
    result = caption_writer.write_caption(
        title=title,
        anime=anime,
        scenes=scenes,
        hook=hook,
        platforms=list(channels) if channels else None,
    )
    return {"ok": bool(result.get("ok")), "stage": "caption", **result}


def stage_publish(body: dict[str, Any]) -> dict[str, Any]:
    """Host a local MP4 publicly, then publish via AiToEarn MCP fanout.

    Optional:
      - auto_caption: run shortform-captioner if caption missing
      - auto_thumbnail / cover_from_video: extract a frame from the MP4 as cover
    """
    from scripts.adapters import aitoearn_client, media_host
    from scripts.aitoearn_pipeline import stage_publish as aitoearn_publish

    local_path = body.get("file") or body.get("local_path") or body.get("video_path")
    if not local_path:
        return {"ok": False, "stage": "publish", "error": "file_required"}
    path = Path(str(local_path))
    if not path.exists():
        return {"ok": False, "stage": "publish", "error": f"missing_file:{path}"}

    title = str(body.get("title") or path.stem).strip()
    caption_meta: dict[str, Any] | None = None
    caption = str(body.get("caption") or body.get("desc") or body.get("description") or "").strip()
    hashtags = body.get("hashtags")
    if body.get("auto_caption") or not caption:
        cap = stage_caption(
            {
                "title": title,
                "anime": body.get("anime") or body.get("series") or "",
                "scenes": body.get("scenes") or [],
                "hook": body.get("hook") or "",
                "channels": body.get("channels"),
            }
        )
        if cap.get("ok"):
            caption_meta = cap
            title = str(cap.get("title") or title)
            caption = str(cap.get("caption") or caption or title)
            hashtags = hashtags or cap.get("hashtags")

    cover_url = body.get("cover_url") or body.get("coverUrl")
    cover_local = body.get("cover_file") or body.get("thumbnail") or body.get("thumb")
    thumb_meta: dict[str, Any] | None = None
    if not cover_url and (
        body.get("auto_thumbnail")
        or body.get("cover_from_video")
        or not cover_local
    ):
        # Prefer extracting a real frame from the rendered Short
        try:
            from reddit_to_script import video_thumbnail  # type: ignore

            # None → smart mid/late frame (avoids repeated opening Yuta shots)
            raw_at = body.get("thumb_at")
            if raw_at is None:
                raw_at = body.get("thumbnail_at")
            at_s = float(raw_at) if raw_at is not None and str(raw_at).strip() != "" else None
            cover_path = video_thumbnail.extract_thumbnail_from_video(
                path,
                at_seconds=at_s,
                avoid_repeats=True,
            )
            cover_local = str(cover_path)
            pick = getattr(video_thumbnail, "LAST_PICK", None) or {}
            thumb_meta = {
                "file": str(cover_path),
                "source": "video_frame",
                "avoid_repeats": True,
                "at_seconds": pick.get("at_seconds"),
                "topic": pick.get("topic"),
            }
        except Exception as exc:  # noqa: BLE001
            thumb_meta = {"error": str(exc), "source": "video_frame"}

    if body.get("dry_run"):
        return {
            "ok": True,
            "stage": "publish",
            "dry_run": True,
            "file": str(path),
            "title": title,
            "caption": caption,
            "hashtags": hashtags,
            "cover_file": cover_local,
            "caption_meta": caption_meta,
            "thumbnail_meta": thumb_meta,
            "channels": body.get("channels") or ["tiktok", "youtube"],
        }

    hosted = media_host.ensure_public_url(str(path), fallback_public_url=body.get("video_url"))
    if not hosted.get("ok"):
        return {
            "ok": False,
            "stage": "publish",
            "error": f"media_hosting_failed:{hosted.get('error')}",
            "file": str(path),
        }

    if not cover_url and cover_local and Path(str(cover_local)).is_file():
        hosted_cover = media_host.ensure_public_url(str(cover_local))
        if hosted_cover.get("ok"):
            cover_url = hosted_cover["public_url"]
            if thumb_meta is not None:
                thumb_meta["public_url"] = cover_url
        elif thumb_meta is not None:
            thumb_meta["host_error"] = hosted_cover.get("error")

    publish_payload = {
        "video_url": hosted["public_url"],
        "title": title,
        "desc": caption or title,
        "caption": caption or title,
        "channels": body.get("channels") or ["tiktok", "youtube", "instagram"],
        "hashtags": hashtags,
        "topics": body.get("topics") or hashtags,
        "selected_accounts": body.get("selected_accounts"),
        "account_ids": body.get("account_ids"),
        "cover_url": cover_url,
        "profile": body.get("profile") or "minimal",
        "mode": body.get("mode") or "full",
    }
    if body.get("publish_time"):
        publish_payload["publishTime"] = aitoearn_client.normalize_publish_time(
            body["publish_time"]
        )

    result = aitoearn_publish(publish_payload)
    return {
        "ok": result.get("success") is not False and result.get("ok") is not False,
        "stage": "publish",
        "file": str(path),
        "public_url": hosted["public_url"],
        "cover_url": cover_url,
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "caption_meta": caption_meta,
        "thumbnail_meta": thumb_meta,
        "result": result,
    }


def stage_status(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Health snapshot for the ultimate monitor agent."""
    from scripts.adapters import aitoearn_client

    out_dir = SHORTFORM_ROOT / "out"
    recent = []
    if out_dir.exists():
        mp4s = sorted(
            list(out_dir.glob("meme-*.mp4")) + list(out_dir.glob("anime-theory-*.mp4")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in mp4s[:15]:
            recent.append(
                {
                    "file": str(p),
                    "name": p.name,
                    "size_mb": round(p.stat().st_size / 1_048_576, 2),
                    "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)),
                    "kind": "anime_theory" if p.name.startswith("anime-theory-") else "meme",
                }
            )

    aitoearn_ok = False
    accounts: list[Any] = []
    try:
        aitoearn_ok = bool(aitoearn_client.CLIENT.enabled())
        if aitoearn_ok:
            accounts = aitoearn_client.CLIENT.list_accounts() or []
    except Exception as exc:  # noqa: BLE001
        accounts = [{"error": str(exc)}]

    return {
        "ok": True,
        "stage": "status",
        "shortform_root": str(SHORTFORM_ROOT),
        "recent_videos": recent,
        "aitoearn_enabled": aitoearn_ok,
        "aitoearn_account_count": len(accounts) if isinstance(accounts, list) else 0,
        "env": {
            "OPENAI": bool(os.getenv("OPENAI_API_KEY")),
            "GIPHY": bool(os.getenv("GIPHY_API_KEY")),
            "PEXELS": bool(os.getenv("PEXELS_API_KEY")),
            "FOOTAGE_AGENTIC": os.getenv("FOOTAGE_AGENTIC", "true"),
        },
    }


def run_pipeline(body: dict[str, Any]) -> dict[str, Any]:
    """Full cycle: fetch → script → render → optional AiToEarn publish."""
    steps: list[dict[str, Any]] = []
    count = int(body.get("count") or 1)
    dry_run = bool(body.get("dry_run", False))
    publish = bool(body.get("publish", False))
    made = []

    fetch = stage_fetch({**body, "limit": count + int(body.get("skip_buffer") or 5)})
    steps.append({"stage": "fetch", "ok": fetch.get("ok"), "count": fetch.get("count")})
    if not fetch.get("ok") or not fetch.get("stories"):
        return {"ok": False, "error": "no_stories", "steps": steps}

    for story in fetch["stories"][:count]:
        scripted = stage_script({**body, "story": story, "style": body.get("style") or "meme"})
        steps.append(
            {
                "stage": "script",
                "ok": scripted.get("ok"),
                "title": story.get("title", "")[:60],
                "scenes": scripted.get("scene_count"),
            }
        )
        if not scripted.get("ok"):
            continue

        if dry_run:
            made.append({"story": story.get("title"), "scenes": scripted["scenes"], "dry_run": True})
            continue

        rendered = stage_render(
            {
                **body,
                "scenes": scripted["scenes"],
                "story": story,
                "title": story.get("title"),
            }
        )
        steps.append(
            {
                "stage": "render",
                "ok": rendered.get("ok"),
                "file": rendered.get("file"),
                "size_mb": rendered.get("size_mb"),
            }
        )
        if not rendered.get("ok"):
            continue

        item: dict[str, Any] = {
            "story": story.get("title"),
            "url": story.get("url"),
            "file": rendered.get("file"),
            "scenes": scripted["scenes"],
        }

        if publish:
            caption = scripted["scenes"][0]["text"] if scripted["scenes"] else story.get("title")
            pub = stage_publish(
                {
                    **body,
                    "file": rendered["file"],
                    "title": story.get("title") or caption,
                    "desc": caption,
                    "caption": caption,
                }
            )
            steps.append({"stage": "publish", "ok": pub.get("ok"), "result": pub.get("result")})
            item["publish"] = pub

        made.append(item)

    return {
        "ok": bool(made),
        "count": len(made),
        "videos": made,
        "steps": steps,
        "dry_run": dry_run,
        "published": publish and not dry_run,
    }


def stage_thumbnail(body: dict[str, Any]) -> dict[str, Any]:
    """Propose (and optionally Remotion-render) thumbnails via Hermes style memory."""
    try:
        from reddit_to_script import thumbnail_memory  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "stage": "thumbnail", "error": str(exc)}

    topic = str(body.get("topic") or body.get("title") or "").strip()
    if not topic:
        return {"ok": False, "stage": "thumbnail", "error": "topic_required"}
    anime = str(body.get("anime") or body.get("series") or "").strip()
    hook = str(body.get("hook") or body.get("scene_hook") or "").strip()
    channel = str(body.get("channel") or "").strip() or None
    result = thumbnail_memory.propose_thumbnail(
        topic, anime=anime, scene_hook=hook, channel=channel
    )

    # Optional Remotion still when imageSrc provided (public-relative path)
    image_src = str(body.get("image_src") or body.get("imageSrc") or "").strip()
    if body.get("render") and image_src:
        concepts = result.get("concepts") or []
        rec = str(result.get("recommended") or "A")
        chosen = next((c for c in concepts if c.get("id") == rec), concepts[0] if concepts else {})
        try:
            out = thumbnail_memory.render_thumbnail_still(
                image_src=image_src,
                overlay_text=str(chosen.get("overlay_text") or topic)[:48],
                layout=str(chosen.get("layout") or "single_face_closeup"),
                out_name=str(body.get("filename") or "").strip() or None,
            )
            result["file"] = str(out)
            result["filename"] = out.name
            result["rendered"] = True
        except Exception as exc:  # noqa: BLE001
            result["rendered"] = False
            result["render_error"] = str(exc)

    return {"ok": True, "stage": "thumbnail", **result}


def main(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    stage = str(body.get("stage") or "pipeline").strip().lower()
    dispatch = {
        "fetch": stage_fetch,
        "script": stage_script,
        "find_memes": stage_find_memes,
        "voice": stage_voice,
        "render": stage_render,
        "anime_theory": stage_anime_theory,
        "anime-theory": stage_anime_theory,
        "anime_theory_pipeline": run_anime_theory_pipeline,
        "anime-theory-pipeline": run_anime_theory_pipeline,
        "full_anime": run_anime_theory_pipeline,
        "full-anime": run_anime_theory_pipeline,
        "thumbnail": stage_thumbnail,
        "thumb": stage_thumbnail,
        "poster": stage_thumbnail,
        "caption": stage_caption,
        "captions": stage_caption,
        "publish": stage_publish,
        "status": stage_status,
        "pipeline": run_pipeline,
        "full": run_pipeline,
    }
    fn = dispatch.get(stage)
    if not fn:
        return {"ok": False, "error": f"unknown_stage:{stage}", "stages": list(dispatch)}
    return fn(body)


if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {"stage": "status"}
    print(json.dumps(main(payload), indent=2, ensure_ascii=False))

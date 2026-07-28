#!/usr/bin/env python3
"""
Stickman Video-Prompting Agent.

A dedicated agent that turns a *story* (or premise) into a scene-by-scene
video plan: cinematic `video_prompt` (motion/camera per beat), storyboard
`image_prompt`, spoken `narration`, and an `action` category for panel reuse.

This is the "prompting" brain of the AI Frame Sequencing Pipeline — it decides
what each frame shows and how it moves, then hands scenes to the flow which
generates Kie panels/clips and compiles them in Remotion.

Usage:
    from scripts.stickman_video_prompter import compose_video_prompts
    plan = compose_video_prompts(story="...", scene_count=10)

    POST /stickman/prompt   body: { story?, premise?, topic?, scene_count?, duration_secs? }
"""
from __future__ import annotations

import json
import re
from typing import Any

from scripts.utils import deepseek_client
from scripts.utils.logger import setup_logger

logger = setup_logger("stickman_video_prompter")

# Valid action categories (must match stickman_panel_library.ACTION_CATEGORIES)
VALID_ACTIONS = (
    "idle", "thinking", "sad", "happy", "celebrating", "failing", "running",
    "walking", "pointing", "sitting", "phone", "computer", "money", "crowd",
    "mirror", "clock", "shouting", "sleeping", "helping", "journey",
)

# Camera/motion vocabulary the video model understands well
MOTION_HINTS = (
    "slow cinematic push-in", "gentle zoom out", "subtle handheld sway",
    "slow pan up", "slow pan down", "rack focus", "dolly in", "static hold with micro-movement",
)


def _system_prompt() -> str:
    return (
        "You are a VIDEO-PROMPTING DIRECTOR for viral Rico Animations–style "
        "black-and-white stick-figure shorts (Beckett AI / Google Flow look). "
        "You convert a story into a shot list. For EACH beat you write:\n"
        "- narration: one spoken sentence (calm, first-person, emotionally honest)\n"
        "- image_prompt: a storyboard STILL — subject + pose + key prop + camera framing + mood, "
        "expressive black vector stickman on pure white background, no text, no color fill\n"
        "- video_prompt: how the shot MOVES — camera move + the character's motion + timing "
        "(prefer slow, cinematic, restrained motion; e.g. 'slow push-in as the figure's shoulders slump')\n"
        "- action: ONE category from the allowed list for panel reuse\n"
        "Return ONLY valid JSON."
    )


def _user_prompt(story: str, scene_count: int, clip_secs: float) -> str:
    return (
        f"STORY / PREMISE:\n{story}\n\n"
        f"Break this into EXACTLY {scene_count} scenes (~{clip_secs:.0f}s each) that form a "
        "clear emotional arc (tension -> avoidance -> peak -> turn -> hope).\n"
        f"Allowed action categories: {', '.join(VALID_ACTIONS)}.\n\n"
        "Return JSON:\n"
        "{\n"
        '  "title": "...",\n'
        '  "logline": "...",\n'
        '  "scenes": [\n'
        "    {\n"
        '      "index": 0,\n'
        '      "narration": "spoken line",\n'
        '      "image_prompt": "storyboard still: subject + pose + prop + framing + mood, black stickman on white",\n'
        '      "video_prompt": "camera move + character motion + timing",\n'
        '      "action": "crowd"\n'
        "    }\n"
        "  ]\n"
        f"}}\nExactly {scene_count} scenes. Keep narration tight enough to speak in ~{clip_secs:.0f}s."
    )


def _coerce_action(value: str, blob: str) -> str:
    v = (value or "").strip().lower()
    if v in VALID_ACTIONS:
        return v
    # keyword fallback
    text = f"{v} {blob}".lower()
    keyword_map = [
        ("crowd", ("crowd", "party", "room full", "everyone", "stage")),
        ("mirror", ("mirror", "reflection", "rehearse")),
        ("phone", ("phone", "message", "text", "call", "scroll")),
        ("thinking", ("think", "overthink", "replay", "wonder", "doubt")),
        ("sitting", ("sit", "corner", "alone", "couch", "chair")),
        ("shouting", ("panic", "chest", "shout", "scream", "overwhelm", "noise")),
        ("running", ("run", "flee", "leave", "escape", "rush")),
        ("walking", ("walk", "away", "home")),
        ("helping", ("friend", "help", "reach out", "hand", "support")),
        ("journey", ("path", "grow", "future", "forward", "hope", "road")),
        ("sad", ("cry", "lonely", "sad", "tears")),
        ("happy", ("smile", "happy", "relief", "joy")),
    ]
    for action, keys in keyword_map:
        if any(k in text for k in keys):
            return action
    return "idle"


def _fallback_story() -> dict[str, Any]:
    """Built-in social-anxiety storyboard so the agent always returns a strong plan."""
    scenes = [
        ("Every room feels like a stage, and I always forget my lines.",
         "Lone stickman frozen in a doorway facing a wall of identical black figures, spotlight framing, wide shot",
         "slow push-in on the lone figure as the crowd subtly shifts around it", "crowd"),
        ("Before I even leave, I rehearse a hundred versions of me.",
         "Stickman in front of a simple mirror practicing a smile, hunched shoulders, medium shot",
         "slow dolly toward the mirror, the reflection lags a beat behind", "mirror"),
        ("Three unread messages. My thumb hovers, then I put the phone down.",
         "Stickman staring at a glowing phone, thumb raised hesitantly, close medium shot",
         "gentle zoom on the phone as the hand pulls back", "phone"),
        ("At the party I smile, but my heart is already sprinting.",
         "Stickman with a stiff smile inside a dense crowd of black figures, chest area emphasized, wide shot",
         "subtle handheld sway, the crowd blurs while the figure stays sharp", "crowd"),
        ("Did that sound stupid? I'll replay it for a week.",
         "Stickman with hand on chin, a tangle of thought lines above its head, close shot",
         "slow push-in as the thought lines tighten around the head", "thinking"),
        ("So I find the quiet corner and call it 'just tired'.",
         "Stickman sitting alone hugging its knees in an empty corner, small in frame, wide shot",
         "slow pan down settling on the small seated figure", "sitting"),
        ("The noise builds, my chest tightens, and I need air.",
         "Stickman clutching its chest, jagged panic lines radiating outward, tight shot",
         "fast subtle shake then a sharp push-in on the chest", "shouting"),
        ("So I leave early again, apologizing to no one.",
         "Stickman walking away toward a distant open door, back turned, wide shot",
         "slow pan following the figure as it shrinks toward the exit", "running"),
        ("Then a friend texts: 'You okay? I noticed you left.'",
         "Two stickmen connected by a glowing message line, one reaching toward the other, medium shot",
         "gentle zoom in on the connecting line as it brightens", "helping"),
        ("Maybe I'm not invisible. Maybe I just need people who see me.",
         "Stickman standing taller on an open path toward a rising light, hopeful posture, wide shot",
         "slow pan up as the figure lifts its head toward the light", "journey"),
    ]
    return {
        "title": "The Loudest Room",
        "logline": "A stickman's honest walk through social anxiety — from the crowded room to a single friend who notices.",
        "scenes": [
            {
                "index": i,
                "narration": n,
                "image_prompt": img,
                "video_prompt": vid,
                "action": act,
            }
            for i, (n, img, vid, act) in enumerate(scenes)
        ],
        "source": "builtin_fallback",
    }


def compose_video_prompts(
    *,
    story: str = "",
    premise: str = "",
    topic: str = "",
    scene_count: int = 10,
    duration_secs: float = 60.0,
) -> dict[str, Any]:
    """
    Turn a story/premise into a scene-by-scene video plan.
    Uses DeepSeek when available; otherwise a built-in social-anxiety storyboard.
    """
    scene_count = max(2, min(int(scene_count or 10), 20))
    clip_secs = max(3.0, float(duration_secs) / scene_count)
    source_story = (story or premise or topic or "").strip()

    # If the request is clearly about social anxiety and no story text given, seed the premise
    if not source_story:
        source_story = (
            "A short, honest story about living with social anxiety: the dread before "
            "entering a room, overthinking every word, escaping to quiet corners, the panic, "
            "and finally one friend who notices and reaches out."
        )

    if not deepseek_client.is_available():
        plan = _fallback_story()
        # If a custom scene_count was requested, trim/pad the fallback
        plan["scenes"] = plan["scenes"][:scene_count]
        plan.update({"success": True, "scene_count": len(plan["scenes"]),
                     "clip_secs": clip_secs, "warning": "DeepSeek unavailable — built-in storyboard"})
        return plan

    result = deepseek_client.chat_json(
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(source_story, scene_count, clip_secs)},
        ],
        temperature=0.7,
        max_tokens=4096,
    )

    if not result.get("success"):
        plan = _fallback_story()
        plan["scenes"] = plan["scenes"][:scene_count]
        plan.update({"success": True, "scene_count": len(plan["scenes"]),
                     "clip_secs": clip_secs, "warning": f"DeepSeek failed ({result.get('error')}) — built-in storyboard"})
        return plan

    data = result.get("data") or {}
    raw_scenes = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(raw_scenes, list) or not raw_scenes:
        plan = _fallback_story()
        plan["scenes"] = plan["scenes"][:scene_count]
        plan.update({"success": True, "scene_count": len(plan["scenes"]),
                     "clip_secs": clip_secs, "warning": "no_scenes_in_response — built-in storyboard"})
        return plan

    scenes: list[dict[str, Any]] = []
    for i, sc in enumerate(raw_scenes[:scene_count]):
        if not isinstance(sc, dict):
            continue
        narration = str(sc.get("narration") or "").strip()
        image_prompt = str(sc.get("image_prompt") or "").strip()
        video_prompt = str(sc.get("video_prompt") or "").strip()
        blob = f"{narration} {image_prompt} {video_prompt}"
        action = _coerce_action(str(sc.get("action") or ""), blob)
        if not (narration or image_prompt):
            continue
        scenes.append({
            "index": i,
            "narration": narration,
            "image_prompt": image_prompt or f"Stickman expressing: {narration}",
            "video_prompt": video_prompt or "slow cinematic push-in",
            "action": action,
        })

    if not scenes:
        plan = _fallback_story()
        plan["scenes"] = plan["scenes"][:scene_count]
        plan.update({"success": True, "scene_count": len(plan["scenes"]),
                     "clip_secs": clip_secs, "warning": "empty_after_parse — built-in storyboard"})
        return plan

    return {
        "success": True,
        "title": str(data.get("title") or "Untitled"),
        "logline": str(data.get("logline") or ""),
        "scenes": scenes,
        "scene_count": len(scenes),
        "clip_secs": clip_secs,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "source": "deepseek",
    }


def run_video_prompter(body: dict[str, Any]) -> dict[str, Any]:
    """Endpoint/CLI entry: returns a video plan (optionally ready for the flow)."""
    plan = compose_video_prompts(
        story=str(body.get("story") or ""),
        premise=str(body.get("premise") or ""),
        topic=str(body.get("topic") or ""),
        scene_count=int(body.get("scene_count") or body.get("scenes_count") or 10),
        duration_secs=float(body.get("duration_secs") or body.get("duration") or 60),
    )
    plan["agent"] = "stickman-prompter"
    return plan


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--story", default="")
    parser.add_argument("--topic", default="social anxiety")
    parser.add_argument("--scenes", type=int, default=10)
    parser.add_argument("--duration", type=float, default=60)
    args = parser.parse_args()
    out = compose_video_prompts(
        story=args.story, topic=args.topic, scene_count=args.scenes, duration_secs=args.duration,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))

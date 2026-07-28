"""Stage 2 — turn a Reddit story into a short-video-maker payload via an LLM.

Output matches ``payloads/viral-short.json`` exactly:
    {"scenes": [{"text": ..., "searchTerms": [...]}], "config": {...}}
so it drops straight into the existing short-video-maker pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from . import config
from . import llm_client
from .fetch_reddit import RedditStory

_SYSTEM_PROMPT = (
    "You are a viral short-form video scriptwriter for faceless YouTube Shorts / "
    "TikTok. You turn Reddit stories into punchy, high-retention narration scripts.\n\n"
    "Rules:\n"
    "- Output 5 to 8 scenes.\n"
    "- Scene 1 is a 3-second curiosity HOOK that makes people stop scrolling.\n"
    "- Each scene's `text` is 1-2 spoken sentences of first-person narration.\n"
    "- Rewrite in natural, conversational, human speech. Remove usernames, links, "
    "slurs, and personally identifying details. Do NOT read the story verbatim.\n"
    "- Compress long stories to ~30-45 seconds of narration. End on a satisfying "
    "payoff or a cliffhanger.\n"
    "- For every scene provide 1-2 `searchTerms`: concrete, filmable STOCK-FOOTAGE "
    "concepts (Pexels has only generic footage). Translate story beats into visuals, "
    "e.g. 'tense couple arguing', 'person walking city street at night'. Never use "
    "literal terms like 'AITA' or a subreddit name.\n"
    "- `music` must be exactly one of the allowed moods.\n"
    "Return ONLY a JSON object: {\"scenes\":[{\"text\":str,\"searchTerms\":[str]}],"
    "\"music\":str}."
)


_MEME_SYSTEM_PROMPT = (
    "You are a viral short-form video scriptwriter for faceless meme videos. You "
    "turn Reddit stories into punchy first-person narration paired with reaction "
    "memes/GIFs.\n\n"
    "Rules:\n"
    "- Output 5 to 8 scenes.\n"
    "- Scene 1 is a 3-second curiosity HOOK that stops the scroll.\n"
    "- Each scene's `text` is 1-2 spoken sentences of natural, human narration. "
    "Remove usernames, links, and identifying details. Don't read verbatim.\n"
    "- Compress to ~30-45 seconds total; end on a payoff or cliffhanger.\n"
    "- For every scene, `searchTerms` must be 1-2 short GIPHY MEME/REACTION search "
    "queries that match the EMOTION of the line, e.g. 'shocked face', 'facepalm', "
    "'mind blown', 'awkward', 'eye roll', 'nervous sweating', 'mic drop'. Keep them "
    "punchy and meme-y, not literal scene descriptions.\n"
    "- `music` must be exactly one of the allowed moods.\n"
    "Return ONLY a JSON object: {\"scenes\":[{\"text\":str,\"searchTerms\":[str]}],"
    "\"music\":str}."
)

_LONG_MEME_SYSTEM_PROMPT = (
    "You are a viral LONG-FORM storytelling scriptwriter for faceless TikTok/YouTube "
    "story videos (2–4 minutes of narration).\n\n"
    "Rules:\n"
    "- Output 12 to 20 scenes (aim ~90–180 seconds spoken).\n"
    "- Scene 1 is a strong curiosity HOOK.\n"
    "- Each scene's `text` is 1–3 spoken sentences, conversational first-person.\n"
    "- Expand sparse TikTok captions into a full story arc: setup → rising action → "
    "twist → payoff. Do not invent brand names or real private identities.\n"
    "- For every scene, `searchTerms` are 1–2 GIPHY reaction-meme queries matching "
    "emotion (shocked face, facepalm, mind blown, awkward, crying laughing, etc.).\n"
    "- `music` must be exactly one of the allowed moods.\n"
    "Return ONLY JSON: {\"scenes\":[{\"text\":str,\"searchTerms\":[str]}],\"music\":str,"
    "\"title\":str}."
)

_CASUAL_VOICE_RULES = (
    "Voice: fast TikTok / YouTube Shorts — punchy friend telling a story. "
    "Dense facts. Short clauses. Cut fluff.\n"
    "BANNED filler / stop-padding: um, uh, like, you know, basically, honestly, "
    "literally, right?, I mean, kind of, sort of, so yeah, wait so, here's the thing, "
    "let me explain, the thing is, as you know, needless to say.\n"
    "BANNED formal fluff: dive deep, delve into, explore the lore, unravel, "
    "fascinating, intricate, tapestry, journey into, let's unpack, "
    "in this video we will, profound, enigmatic, stay tuned, more soon, "
    "part 2 coming, subscribe for more, to be continued.\n"
    "Prefer: 'wild part is', 'real talk', 'so then', 'and that's when', "
    "'what if I told you' — but only once per script max for each.\n"
)

_STORY_ARC_RULES = (
    "STORY RULES (critical) — match viral anime-theory Shorts like Hitogami/Lara explainers:\n"
    "- Tell a COMPLETE mini-story. Beginning → middle → ending. The last scene "
    "must ANSWER the hook — no teasing, no cliffhangers, no 'stay tuned'.\n"
    "- Structure: (1) big hook / false assumption, (2) setup who the power player is, "
    "(3) name the surprising answer, (4) bust the obvious reason, (5–8) stack lore "
    "evidence beat by beat, (9–10) emotional 'think about that' payoff + clean closer.\n"
    "- Each scene advances with a concrete fact. No vague hype.\n"
    "- Keep lines TIGHT: 1–2 sentences per scene (max ~35 words). Fast pace — "
    "no throat-clearing, no soft landings, no repeated hedges.\n"
)

_ANIME_THEORY_SYSTEM_PROMPT = (
    "You are a viral anime lore storyteller for TikTok / YouTube Shorts. "
    "Study this STYLE (not copy): hook with a twist ('What if I told you…'), "
    "name the surprising answer early, bust the wrong reason fans assume, "
    "stack lore proof, end with an emotional punch that answers the hook.\n\n"
    "Rules:\n"
    "- Output 10 to 14 scenes (~70–100 seconds spoken).\n"
    "- Scene 1 HOOK must reframe what the viewer thinks they know.\n"
    "- Each scene's `text` is 1–2 spoken sentences (max ~35 words). "
    "Fast casual narrator. Story first.\n"
    f"- {_CASUAL_VOICE_RULES}"
    f"- {_STORY_ARC_RULES}"
    "- Stay grounded in canon; do not invent contradictory facts.\n"
    "- For EVERY scene, `searchTerms` must be 1–2 character names that appear "
    "IN THAT SCENE's narration from THAT series only. Use FULL names when known "
    "(e.g. 'Yuta Okkotsu', 'Satoru Gojo', 'Yuuji Itadori') — these drive Safebooru "
    "character image search. If the line is about Yuta, searchTerms MUST lead with "
    "Yuta (not Gojo). Match the face to who is being talked about right now. "
    "Never bare surnames that match relatives. NEVER reuse the same searchTerms "
    "across many scenes — rotate cast. NEVER use other-anime names.\n"
    "- Also return `anime`, `title`, and `music` (one allowed mood matching tone).\n"
    "- Match competitor Short pacing when a STYLE MEMORY / REFERENCE SCRIPT is "
    "provided: same energy, hook timing, and approximate total word count. "
    "Write ORIGINAL lines — never plagiarize.\n"
    "Return ONLY JSON: {\"title\":str,\"anime\":str,\"music\":str,"
    "\"scenes\":[{\"text\":str,\"searchTerms\":[str]}]}."
)

_CHAPTER_COMMENTARY_SYSTEM_PROMPT = (
    "You are a hype manga YouTube commentator reacting to a chapter recap. "
    "Style: passionate reactor who comments on events beat-by-beat — shock, "
    "analysis, power-scaling takes, and humor.\n\n"
    "Rules:\n"
    "- Output 10 to 16 scenes (~60–120 seconds spoken).\n"
    "- Scene 1 HOOK: tease the craziest moment in this chapter.\n"
    "- Walk through the chapter IN ORDER using the provided event beats.\n"
    "- Each scene `text` is 1–2 spoken sentences (max ~30 words). First-person "
    "commentary ('Bro…', 'Look at this…', 'I can't believe…'). React to what "
    "ACTUALLY happens — do NOT invent events not in the source material.\n"
    "- End with a real takeaway about the chapter, NEVER 'stay tuned' or part 2.\n"
    "- For EVERY scene, `searchTerms` must be 1–2 character names from THAT "
    "manga only (e.g. Baki: 'Baki', 'Yujiro', 'Jack', 'Doppo', 'Pickle').\n"
    "- Return `anime` (series name) and `title` (e.g. 'Baki Ch.65 — Striking the Face').\n"
    "- `music` must be one of the allowed moods (prefer intense / excited / dark).\n"
    "Return ONLY JSON: {\"title\":str,\"anime\":str,\"scenes\":[{\"text\":str,"
    "\"searchTerms\":[str]}],\"music\":str}."
)

_LONG_ANIME_THEORY_SYSTEM_PROMPT = (
    "You are a viral anime lore STORYTELLER for TikTok / YouTube. "
    "Match top Shorts: hook twist → surprising answer → wrong-reason bust → "
    "lore stack → emotional closer that fully answers the hook.\n\n"
    "Rules:\n"
    "- Output 12 to 18 scenes (aim ~90–140 seconds spoken).\n"
    "- Scene 1 HOOK. Scenes 2–4 set stakes + name the answer. Middle = proof. "
    "Final 2–3 = 'think about that' payoff + clean ending.\n"
    "- Each scene's `text` is 1–2 spoken sentences (max ~35 words). "
    "Fast punchy narrator — no filler.\n"
    f"- {_CASUAL_VOICE_RULES}"
    f"- {_STORY_ARC_RULES}"
    "- If a REFERENCE TRANSCRIPT is provided, study pacing + argument shape — "
    "write ORIGINAL lines (do NOT copy sentences).\n"
    "- Stay grounded in canon; do not invent contradictory facts.\n"
    "- For EVERY scene, `searchTerms` must be 1–2 character names that appear "
    "IN THAT SCENE's narration from THAT series only. Use FULL names "
    "(e.g. 'Yuta Okkotsu', 'Satoru Gojo') for Safebooru image lookup — lead with "
    "whoever that line is about. Not vague surnames that could match relatives. "
    "Vary characters across scenes — do not repeat the same searchTerms every "
    "scene. NEVER use other-anime names.\n"
    "- Also return `anime`, `title`, and `music` (mood for background bed).\n"
    "- Prefer music: dark / uneasy / contemplative for dread lore; "
    "sad / melancholic for tragedy; hopeful for bittersweet payoffs.\n"
    "- When STYLE MEMORY / REFERENCE SCRIPT is provided, clone its pacing and "
    "hook structure (not its sentences) — same beat density and word budget.\n"
    "Return ONLY JSON: {\"title\":str,\"anime\":str,\"music\":str,"
    "\"scenes\":[{\"text\":str,\"searchTerms\":[str]}]}."
)

def build_scenes(story: RedditStory, *, style: str = "stock") -> list[dict[str, Any]]:
    """Return validated scenes ({text, searchTerms}) for a story.

    style="stock" | "meme" | "long_meme" | "anime_theory" | "long_anime_theory" | "chapter_commentary"
    """
    if style == "long_anime_theory":
        system = _LONG_ANIME_THEORY_SYSTEM_PROMPT
    elif style == "anime_theory":
        system = _ANIME_THEORY_SYSTEM_PROMPT
    elif style == "chapter_commentary":
        system = _CHAPTER_COMMENTARY_SYSTEM_PROMPT
    elif style == "long_meme":
        system = _LONG_MEME_SYSTEM_PROMPT
    elif style == "meme":
        system = _MEME_SYSTEM_PROMPT
    else:
        system = _SYSTEM_PROMPT
    result = llm_client.complete_json(system, _build_user_prompt(story, style=style))
    scenes = _sanitize_scenes(result.get("scenes"))
    if not scenes:
        raise ValueError("LLM returned no usable scenes for this story.")
    anime = str(result.get("anime") or "").strip()
    title = str(result.get("title") or story.title or "").strip()
    music = str(result.get("music") or "").strip()
    if anime or title or music:
        for scene in scenes:
            if anime:
                scene["anime"] = anime
            if title:
                scene["videoTitle"] = title
            if music:
                scene["music"] = music
    return scenes


def build_anime_theory_scenes(
    topic: str,
    *,
    anime: str = "",
    context: str = "",
    long: bool = False,
    reference_transcript: str = "",
    use_style_memory: bool = True,
) -> dict[str, Any]:
    """Build an anime-theory script from a freeform topic (not Reddit)."""
    style = "long_anime_theory" if long else "anime_theory"
    body_parts = [
        f"Anime series: {anime.strip() or 'infer from topic'}",
        f"Extra context / notes:\n{(context or topic).strip()}",
    ]
    ref = (reference_transcript or "").strip()
    playbook_meta: dict[str, Any] | None = None
    if use_style_memory and not ref:
        try:
            from . import style_memory

            ref, playbook_meta = style_memory.pick_reference_transcript(
                topic, anime=anime
            )
            if playbook_meta:
                body_parts.insert(
                    0, style_memory.format_style_block(playbook_meta)
                )
                # Nudge scene count / length toward learned median
                med = int(playbook_meta.get("median_words") or 0)
                if med:
                    body_parts.append(
                        f"LENGTH TARGET from competitor training: about {med} total "
                        f"spoken words across all scenes (stay within "
                        f"{playbook_meta.get('word_count_p25')}–"
                        f"{playbook_meta.get('word_count_p75')} words)."
                    )
                target_scenes = playbook_meta.get("target_scenes") or (
                    (playbook_meta.get("video_building") or {}).get("target_scenes")
                )
                if target_scenes:
                    body_parts.append(
                        f"SCENE COUNT TARGET: about {target_scenes} scenes "
                        f"(match competitor visual beat density)."
                    )
        except Exception as exc:  # noqa: BLE001
            print(f"  [style-memory] skip: {exc}", flush=True)

    # Hermes edit + music playbooks (pacing / BGM)
    try:
        from . import edit_memory, music_memory

        edit_pb = edit_memory.load_playbook()
        if edit_pb:
            body_parts.append(edit_memory.format_edit_block(edit_pb))
        music_pb = music_memory.load_playbook()
        if music_pb:
            body_parts.append(music_memory.format_music_block(music_pb))
    except Exception as exc:  # noqa: BLE001
        print(f"  [hermes-memory] edit/music skip: {exc}", flush=True)

    if ref:
        body_parts.append(
            "REFERENCE VIRAL SCRIPT (study hook rhythm, argument shape, beat count, "
            "and pacing — write ORIGINAL narration for THIS topic, do NOT copy sentences):\n"
            f"{ref}"
        )
    story = RedditStory(
        title=topic.strip(),
        url="",
        body="\n\n".join(body_parts),
        author="theory",
    )
    scenes = build_scenes(story, style=style)
    anime_name = anime.strip() or str(scenes[0].get("anime") or "").strip()
    title = str(scenes[0].get("videoTitle") or topic).strip()
    raw_music = str(scenes[0].get("music") or "").strip()
    try:
        from . import music_memory

        music = music_memory.pick_mood(
            topic, anime=anime_name, script_music=raw_music or None
        )
    except Exception:  # noqa: BLE001
        music = raw_music or "dark"
    for scene in scenes:
        scene["music"] = music
    out = {
        "title": title,
        "anime": anime_name,
        "music": music,
        "scenes": scenes,
        "scene_count": len(scenes),
    }
    if playbook_meta and playbook_meta.get("selected_exemplar"):
        out["style_exemplar"] = playbook_meta["selected_exemplar"]
        out["style_channel"] = playbook_meta.get("channel")
    return out


def build_chapter_commentary_scenes(
    *,
    manga_title: str,
    chapter_number: str,
    chapter_title: str,
    summary: str,
    events: list[dict[str, Any]],
    characters: list[str],
) -> dict[str, Any]:
    """Build a commentary script from a summarized manga chapter."""
    label = f"{manga_title} Chapter {chapter_number}"
    if chapter_title:
        label += f": {chapter_title}"

    event_lines = []
    for i, ev in enumerate(events, start=1):
        beat = str(ev.get("beat") or ev.get("text") or "").strip()
        chars = ev.get("characters") or []
        if beat:
            char_note = f" (characters: {', '.join(chars)})" if chars else ""
            event_lines.append(f"{i}. {beat}{char_note}")

    body = (
        f"Manga: {manga_title}\n"
        f"Chapter: {chapter_number}\n"
        f"Chapter title: {chapter_title or 'N/A'}\n\n"
        f"Chapter summary:\n{summary}\n\n"
        f"Event beats (comment on these IN ORDER):\n"
        + ("\n".join(event_lines) if event_lines else "(see summary)")
        + f"\n\nCharacters in chapter: {', '.join(characters) if characters else 'infer from summary'}"
    )

    story = RedditStory(title=label, url="", body=body, author="chapter")
    scenes = build_scenes(story, style="chapter_commentary")
    anime_name = manga_title.strip() or str(scenes[0].get("anime") or "").strip()
    title = str(scenes[0].get("videoTitle") or label).strip()
    return {
        "title": title,
        "anime": anime_name,
        "scenes": scenes,
        "scene_count": len(scenes),
    }


def _build_user_prompt(story: RedditStory, *, style: str = "stock") -> str:
    allowed = ", ".join(config.MUSIC_TAGS)
    if style in ("anime_theory", "long_anime_theory"):
        form = "LONG-FORM" if style == "long_anime_theory" else "Shorts"
        return (
            f"Allowed music moods: {allowed}\n\n"
            f"Theory topic / title: {story.title}\n\n"
            f"Source material / notes:\n{story.body}\n\n"
            f"Write the {form} anime-theory script now as JSON."
        )
    if style == "chapter_commentary":
        return (
            f"Allowed music moods: {allowed}\n\n"
            f"Chapter recap to comment on: {story.title}\n\n"
            f"{story.body}\n\n"
            "Write the chapter commentary script now as JSON."
        )
    return (
        f"Allowed music moods: {allowed}\n\n"
        f"Reddit post title: {story.title}\n\n"
        f"Reddit post body:\n{story.body}\n\n"
        "Write the video script now as JSON."
    )


def _sanitize_scenes(scenes: Any) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    recent_lead: list[str] = []
    # Global cast from all LLM searchTerms — used to align faces to narration
    cast_pool: list[str] = []
    for scene in scenes or []:
        terms = scene.get("searchTerms") or scene.get("search_terms") or []
        if isinstance(terms, str):
            terms = [terms]
        for t in terms:
            t = str(t).strip()
            if t and t not in cast_pool and t.lower() != "abstract background":
                cast_pool.append(t)

    for scene in scenes or []:
        text = str(scene.get("text", "")).strip()
        if not text:
            continue
        terms = scene.get("searchTerms") or scene.get("search_terms") or []
        if isinstance(terms, str):
            terms = [terms]
        terms = [str(t).strip() for t in terms if str(t).strip()][:2]

        # Prefer whoever the narration actually names (multi-character videos)
        try:
            from . import anime_footage

            aligned = anime_footage.pick_terms_for_scene(
                terms,
                scene_text=text,
                cast_pool=cast_pool,
                scene_index=len(clean),
            )
            if aligned:
                terms = aligned[:2]
        except Exception:  # noqa: BLE001
            pass

        if not terms:
            terms = ["abstract background"]

        lead = terms[0].lower()
        if recent_lead[-2:].count(lead) >= 2 and len(terms) > 1:
            terms = [terms[1], terms[0]]
        recent_lead.append(terms[0].lower())
        clean.append({"text": text, "searchTerms": terms})
    return clean


def _pick_music(suggested: Any) -> str:
    value = str(suggested or "").strip().lower()
    return value if value in config.MUSIC_TAGS else config.DEFAULT_MUSIC


def build_payload(story: RedditStory, *, voice: str | None = None) -> dict[str, Any]:
    """Call the LLM and assemble a validated short-video-maker payload."""
    result = llm_client.complete_json(_SYSTEM_PROMPT, _build_user_prompt(story))
    scenes = _sanitize_scenes(result.get("scenes"))
    if not scenes:
        raise ValueError("LLM returned no usable scenes for this story.")

    chosen_voice = voice or config.DEFAULT_VOICE
    if chosen_voice not in config.VOICES:
        chosen_voice = config.DEFAULT_VOICE

    return {
        "scenes": scenes,
        "config": {
            "paddingBack": 1500,
            "music": _pick_music(result.get("music")),
            "voice": chosen_voice,
            "orientation": config.DEFAULT_ORIENTATION,
            "captionPosition": config.DEFAULT_CAPTION_POSITION,
            "captionBackgroundColor": config.DEFAULT_CAPTION_BG,
            "musicVolume": "high",
        },
    }


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len].rstrip("-")) or "story"


def _main() -> None:
    parser = argparse.ArgumentParser(description="Generate a payload from a story JSON.")
    parser.add_argument("story_json", help="Path to a JSON file with title/body, or '-' for stdin.")
    parser.add_argument("--voice", default=None)
    args = parser.parse_args()

    import sys

    raw = sys.stdin.read() if args.story_json == "-" else open(args.story_json, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, list):
        data = data[0]
    story = RedditStory(
        title=data.get("title", ""),
        url=data.get("url", ""),
        body=data.get("body", ""),
        author=data.get("author", ""),
    )
    print(json.dumps(build_payload(story, voice=args.voice), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()

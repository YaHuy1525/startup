"""Anime still sourcing for anime-theory shorts.

Primary: Safebooru character art (https://safebooru.org dapi).
Fallback: AniList character portraits, then series covers/banners.
Giphy is NOT used for anime-theory.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests

from . import config
from .footage import FootageError

_ANILIST = "https://graphql.anilist.co"
_SAFEBOORU = getattr(config, "SAFEBOORU_BASE_URL", "https://safebooru.org").rstrip("/")
_UA = "Mozilla/5.0 (compatible; anime-theory-pipeline/1.0)"
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": _UA,
}
_SB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}

_STOP = {
    "old", "man", "woman", "guy", "girl", "panel", "scene", "shot", "closeup",
    "close-up", "face", "full", "body", "wallpaper", "art", "anime", "manga",
    "the", "a", "an", "and", "of", "in", "on", "to", "for", "with", "his",
    "her", "their", "connection", "hoodie", "form", "true", "final", "why",
    "never", "goes", "does", "look", "looking", "shown", "wearing", "bloodline",
    "theory", "explained", "vs", "versus",
}

# Series name → Safebooru copyright tag
_SERIES_TAGS: dict[str, str] = {
    "jujutsu kaisen": "jujutsu_kaisen",
    "jjk": "jujutsu_kaisen",
    "bleach": "bleach",
    "attack on titan": "shingeki_no_kyojin",
    "shingeki no kyojin": "shingeki_no_kyojin",
    "invincible": "invincible_(series)",
    "mushoku tensei": "mushoku_tensei",
    "one piece": "one_piece",
    "naruto": "naruto_(series)",
    "demon slayer": "kimetsu_no_yaiba",
    "chainsaw man": "chainsaw_man",
}


@dataclass
class AnimeAsset:
    url: str
    kind: str  # "image" | "video"
    source: str
    title: str = ""
    query_used: str = ""
    reason: str = ""
    asset_id: str = ""


_CHAR_CACHE: dict[str, list[AnimeAsset]] = {}
_SB_CACHE: dict[str, list[AnimeAsset]] = {}


def _anilist(query: str, variables: dict, *, timeout: int = 25) -> dict:
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                _ANILIST,
                json={"query": query, "variables": variables},
                headers=_HEADERS,
                timeout=timeout,
            )
            if resp.status_code == 429:
                time.sleep(1.2 * (attempt + 1))
                continue
            if not resp.ok:
                raise FootageError(f"AniList {resp.status_code}: {resp.text[:180]}")
            body = resp.json()
            if body.get("errors"):
                raise FootageError(f"AniList GraphQL: {body['errors'][0].get('message')}")
            return body.get("data") or {}
        except (requests.RequestException, FootageError) as exc:
            last_err = exc
            time.sleep(0.6 * (attempt + 1))
    raise FootageError(str(last_err) if last_err else "AniList failed")


def _significant_tokens(text: str) -> list[str]:
    raw = [t for t in re.split(r"[\s,|/+\-]+", text) if t]
    out: list[str] = []
    for t in raw:
        key = re.sub(r"[^a-zA-Z0-9]", "", t).lower()
        if len(key) < 3 or key in _STOP:
            continue
        out.append(t)
    return out


def _hint_tokens(anime_hint: str) -> list[str]:
    return [t.lower() for t in _significant_tokens(anime_hint)]


def _title_matches_series(title: str, anime_hint: str) -> bool:
    if not anime_hint.strip():
        return True
    title_l = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    title_l = re.sub(r"\s+", " ", title_l).strip()
    tokens = _hint_tokens(anime_hint)
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in title_l)
    return hits >= max(1, (len(tokens) + 1) // 2)


def _romaji_fold(s: str) -> str:
    s = (s or "").lower()
    for a, b in (("ou", "o"), ("uu", "u"), ("oo", "o"), ("aa", "a"), ("ee", "e")):
        s = s.replace(a, b)
    return s


def _name_match_score(query: str, full_name: str) -> int:
    q = re.sub(r"\s+", " ", query.strip().lower())
    name = re.sub(r"\s+", " ", (full_name or "").strip().lower())
    name = re.sub(r"\b(cover|banner|portrait)\b", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    if not q or not name:
        return 0
    if q == name or _romaji_fold(q) == _romaji_fold(name):
        return 100
    q_parts = [p for p in q.split() if p not in _STOP]
    n_parts = [p for p in name.split() if p not in _STOP]
    if not q_parts or not n_parts:
        return 0
    if len(q_parts) >= 2:
        hits = sum(
            1
            for p in q_parts
            if p in n_parts
            or _romaji_fold(p) in {_romaji_fold(n) for n in n_parts}
            or any(p in n for n in n_parts)
        )
        if hits == len(q_parts):
            return 95
        qf = {_romaji_fold(p) for p in q_parts}
        nf0 = _romaji_fold(n_parts[0])
        if _romaji_fold(q_parts[0]) not in {_romaji_fold(n) for n in n_parts} and nf0 not in qf:
            return 0
        return max(0, hits * 30)
    q0 = q_parts[0]
    q0f = _romaji_fold(q0)
    n_folds = [_romaji_fold(p) for p in n_parts]
    if q0 == n_parts[0] or q0 == n_parts[-1] or q0f == n_folds[0] or q0f == n_folds[-1]:
        return 80
    if q0 in n_parts or q0f in n_folds:
        return 45
    for p, pf in zip(n_parts, n_folds):
        if len(q0f) >= 4 and len(pf) >= 4 and (pf.startswith(q0f[:4]) or q0f.startswith(pf[:4])):
            return 78
        if len(p) >= 3 and (p.startswith(q0) or q0.startswith(p)):
            return 40
    return 0


_SURNAME_BLOCKLIST_PREFIXES = (
    "wasuke", "jin ", "kaori", "grandma", "grandfather",
)
_SURNAME_BLOCKLIST_CONTAINS = (
    "doukyuusei", "classmate", "schoolmate", "extra",
)


def _search_characters(
    term: str,
    *,
    anime_hint: str = "",
    limit: int = 10,
) -> list[AnimeAsset]:
    cache_key = f"{term.lower().strip()}|{anime_hint.lower().strip()}"
    if cache_key in _CHAR_CACHE:
        return list(_CHAR_CACHE[cache_key])
    q = """
    query ($s: String, $n: Int) {
      Page(perPage: $n) {
        characters(search: $s) {
          id
          favourites
          name { full }
          image { large }
          media(sort: POPULARITY_DESC, perPage: 5) {
            nodes {
              id
              type
              title { romaji english }
              bannerImage
              coverImage { extraLarge large }
            }
          }
        }
      }
    }
    """
    data = _anilist(q, {"s": term[:50], "n": limit})
    scored: list[tuple[int, AnimeAsset]] = []
    for ch in (data.get("Page") or {}).get("characters") or []:
        url = ((ch.get("image") or {}).get("large") or "").strip()
        if not url:
            continue
        nodes = ((ch.get("media") or {}).get("nodes") or [])
        series_titles = []
        for n in nodes:
            if (n.get("type") or "").upper() not in ("ANIME", "MANGA", ""):
                continue
            t = (n.get("title") or {}).get("english") or (n.get("title") or {}).get("romaji") or ""
            if t:
                series_titles.append(str(t))
        if anime_hint and not any(_title_matches_series(t, anime_hint) for t in series_titles):
            continue
        name = str((ch.get("name") or {}).get("full") or term)
        series_label = next(
            (t for t in series_titles if _title_matches_series(t, anime_hint)),
            series_titles[0] if series_titles else "",
        )
        cid = ch.get("id")
        favs = int(ch.get("favourites") or 0)
        match = _name_match_score(term, name)
        if match <= 0:
            continue
        name_l = name.lower()
        if match < 95 and (
            any(name_l.startswith(p) for p in _SURNAME_BLOCKLIST_PREFIXES)
            or any(p in name_l for p in _SURNAME_BLOCKLIST_CONTAINS)
        ):
            continue
        if match < 90 and favs < 5_000:
            continue
        base = match * 1000 + min(favs, 50_000)
        scored.append(
            (
                base + 50,
                AnimeAsset(
                    url=url,
                    kind="image",
                    source="anilist_character",
                    title=f"{name} ({series_label})" if series_label else name,
                    query_used=term,
                    reason=f"AniList portrait match={match} favs={favs}",
                    asset_id=f"char-{cid}-portrait",
                ),
            )
        )
    scored.sort(key=lambda x: -x[0])
    out = [a for _, a in scored]
    if out:
        _CHAR_CACHE[cache_key] = list(out)
    return out


def _search_media(term: str, *, anime_hint: str = "", limit: int = 5) -> list[AnimeAsset]:
    q = """
    query ($s: String, $n: Int) {
      Page(perPage: $n) {
        media(search: $s, type: ANIME, sort: SEARCH_MATCH) {
          id
          title { romaji english }
          coverImage { extraLarge large }
          bannerImage
        }
      }
    }
    """
    search = anime_hint.strip() if anime_hint and term.lower() in anime_hint.lower() else term
    if anime_hint and not _title_matches_series(term, anime_hint):
        search = anime_hint
    data = _anilist(q, {"s": search[:60], "n": limit})
    out: list[AnimeAsset] = []
    for m in (data.get("Page") or {}).get("media") or []:
        title = (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji") or term
        if anime_hint and not _title_matches_series(str(title), anime_hint):
            continue
        cover = ((m.get("coverImage") or {}).get("extraLarge")
                 or (m.get("coverImage") or {}).get("large") or "").strip()
        banner = (m.get("bannerImage") or "").strip()
        mid = m.get("id")
        if banner:
            out.append(
                AnimeAsset(
                    url=banner,
                    kind="image",
                    source="anilist_banner",
                    title=str(title),
                    query_used=term,
                    reason="AniList anime banner (series-matched)",
                    asset_id=f"banner-{mid}",
                )
            )
        if cover:
            out.append(
                AnimeAsset(
                    url=cover,
                    kind="image",
                    source="anilist_cover",
                    title=str(title),
                    query_used=term,
                    reason="AniList anime cover (series-matched)",
                    asset_id=f"cover-{mid}",
                )
            )
    return out


def _slug_token(token: str) -> str:
    t = token.strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def _romaji_folds(token: str) -> list[str]:
    """Booru tags often use long vowels: Gojo→gojou, Yuta→yuuta."""
    t = _slug_token(token)
    if not t:
        return []
    alts = {t}
    # Final -o → -ou (gojo/gojou) — common on Safebooru
    if t.endswith("o") and not t.endswith("ou"):
        alts.add(t + "u")
    if t.endswith("ou") and len(t) > 3:
        alts.add(t[:-1])
    # Short given-name expansions only (avoid okkotsu → okkotsuu)
    if t in {"yuta", "yuuta"}:
        alts.update({"yuta", "yuuta"})
    if t in {"yuji", "yuuji"}:
        alts.update({"yuji", "yuuji"})
    if t in {"gojo", "gojou"}:
        alts.update({"gojo", "gojou"})
    if t == "sukuna":
        alts.add("ryoumen_sukuna")
    return [x for x in alts if x]


def _series_booru_tag(anime_hint: str) -> str:
    low = re.sub(r"\s+", " ", anime_hint.lower()).strip()
    if low in _SERIES_TAGS:
        return _SERIES_TAGS[low]
    for key, tag in _SERIES_TAGS.items():
        if key in low or low in key:
            return tag
    return _slug_token(low)


def _booru_character_tag_candidates(name: str) -> list[str]:
    """Western 'Given Family' → Safebooru 'family_given' (+ reverse + romaji)."""
    # Common romanization typos from LLMs / English spellings
    fixes = {
        "okotsu": "okkotsu",
        "okkotsuu": "okkotsu",
        "gojo": "gojou",
        "itadori": "itadori",
        "fushiguro": "fushiguro",
    }
    parts = [_slug_token(p) for p in re.split(r"[\s,|/]+", name) if _slug_token(p)]
    parts = [fixes.get(p, p) for p in parts if p and p not in _STOP]
    # Also keep original unfixed tokens as alts
    raw_parts = [_slug_token(p) for p in re.split(r"[\s,|/]+", name) if _slug_token(p)]
    raw_parts = [p for p in raw_parts if p and p not in _STOP]
    if not parts:
        return []
    cands: list[str] = []

    def _pair_tags(given: str, family: str) -> None:
        for g in _romaji_folds(given):
            for f in _romaji_folds(family):
                cands.append(f"{f}_{g}")  # Japanese order — primary
                cands.append(f"{g}_{f}")

    if len(parts) >= 2:
        _pair_tags(parts[0], parts[-1])
        if len(raw_parts) >= 2 and (raw_parts[0] != parts[0] or raw_parts[-1] != parts[-1]):
            _pair_tags(raw_parts[0], raw_parts[-1])
    else:
        for g in _romaji_folds(parts[0]):
            cands.append(g)
    # Given-name-only tags sometimes exist; always try given token
    if len(parts) >= 2:
        for g in _romaji_folds(parts[0]):
            cands.append(g)
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _asset_matches_term(asset: AnimeAsset, term: str) -> bool:
    """True if Safebooru/AniList asset looks like this character name."""
    tokens = {_romaji_fold(t) for t in _name_tokens(term)}
    if not tokens:
        return True
    blob = f"{asset.title} {asset.query_used} {asset.reason}".lower().replace("_", " ")
    blob_f = _romaji_fold(blob)
    hits = sum(1 for t in tokens if t in blob_f or t in blob)
    return hits >= max(1, (len(tokens) + 1) // 2)


def _safebooru_posts(tags: str, *, limit: int = 20) -> list[dict]:
    try:
        resp = requests.get(
            f"{_SAFEBOORU}/index.php",
            params={
                "page": "dapi",
                "s": "post",
                "q": "index",
                "json": 1,
                "tags": tags,
                "limit": min(limit, 40),
            },
            headers=_SB_HEADERS,
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"  [safebooru] request failed: {exc}", flush=True)
        return []
    if not resp.ok or not resp.content:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _pick_image_url(post: dict) -> str:
    for key in ("file_url", "sample_url", "preview_url"):
        url = str(post.get(key) or "").strip()
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http"):
            return url
    return ""


def _search_safebooru(
    term: str,
    *,
    anime_hint: str = "",
    limit: int = 12,
) -> list[AnimeAsset]:
    """Search Safebooru for character stills matching a script searchTerm."""
    cache_key = f"{term.lower()}|{anime_hint.lower()}"
    if cache_key in _SB_CACHE:
        return list(_SB_CACHE[cache_key])

    series_tag = _series_booru_tag(anime_hint) if anime_hint.strip() else ""
    char_tags = _booru_character_tag_candidates(term)

    # Soft autocomplete for short single tokens (e.g. "Yuta")
    if len(char_tags) == 1 and len(char_tags[0]) >= 3:
        try:
            resp = requests.get(
                f"{_SAFEBOORU}/index.php",
                params={
                    "page": "dapi",
                    "s": "tag",
                    "q": "index",
                    "json": 1,
                    "name_pattern": f"%{char_tags[0]}%",
                    "limit": 25,
                },
                headers=_SB_HEADERS,
                timeout=20,
            )
            if resp.content:
                names = re.findall(r'name="([^"]+)"', resp.text)
                if not names:
                    try:
                        raw = resp.json()
                        if isinstance(raw, list):
                            names = [
                                str(t.get("name") or "")
                                for t in raw
                                if isinstance(t, dict)
                            ]
                    except ValueError:
                        names = []
                for n in names:
                    n = n.strip()
                    if not n or n in char_tags:
                        continue
                    if char_tags[0] in n and ("_" in n or n == char_tags[0]):
                        char_tags.append(n)
        except requests.RequestException:
            pass

    out: list[AnimeAsset] = []
    seen_ids: set[str] = set()
    for char_tag in char_tags[:8]:
        tag_queries: list[str] = []
        if series_tag:
            tag_queries.append(f"{char_tag} {series_tag}")
        tag_queries.append(char_tag)
        for tag_q in tag_queries:
            posts = _safebooru_posts(tag_q, limit=limit)
            if not posts:
                continue
            for post in posts:
                pid = str(post.get("id") or "")
                if pid and pid in seen_ids:
                    continue
                tags_blob = str(post.get("tags") or "").lower()
                tag_set = set(tags_blob.split())
                if char_tag not in tag_set:
                    continue
                if series_tag and "crossover" in tag_set and series_tag not in tag_set:
                    continue
                url = _pick_image_url(post)
                if not url:
                    continue
                score = 0
                if "solo" in tag_set or "1boy" in tag_set or "1girl" in tag_set:
                    score += 3
                if "portrait" in tag_set or "close-up" in tag_set or "face" in tag_set:
                    score += 2
                if series_tag and series_tag in tag_set:
                    score += 4
                if "comic" in tag_set or "4koma" in tag_set:
                    score -= 2
                if pid:
                    seen_ids.add(pid)
                out.append(
                    AnimeAsset(
                        url=url,
                        kind="image",
                        source="safebooru",
                        title=char_tag.replace("_", " "),
                        query_used=tag_q,
                        reason=f"Safebooru score={score} id={pid}",
                        asset_id=f"sb-{pid}" if pid else f"sb-{hash(url) & 0xFFFF}",
                    )
                )
            if out:
                break
        if len(out) >= limit:
            break

    def _rank(a: AnimeAsset) -> int:
        m = re.search(r"score=(-?\d+)", a.reason or "")
        return int(m.group(1)) if m else 0

    out.sort(key=_rank, reverse=True)
    _SB_CACHE[cache_key] = out[:limit]
    return list(_SB_CACHE[cache_key])


def _query_variants(term: str, anime_hint: str = "", *, allow_splits: bool = False) -> list[str]:
    term = term.strip()
    if not term:
        return []
    variants: list[str] = [term]
    if allow_splits:
        for tok in _significant_tokens(term):
            if tok.lower() not in _STOP and tok not in variants:
                variants.append(tok)
    seen: set[str] = set()
    out: list[str] = []
    hint_l = anime_hint.lower().strip()
    for v in variants:
        key = v.lower().strip()
        if not key or key in seen or key in _STOP:
            continue
        if hint_l and key == hint_l:
            continue
        seen.add(key)
        out.append(v.strip())
    return out


def _char_base_id(asset_id: str) -> str:
    if asset_id.startswith("char-"):
        parts = asset_id.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            return f"char-{parts[1]}"
        return asset_id
    if asset_id.startswith("sb-"):
        return asset_id
    return asset_id


def _name_tokens(name: str) -> list[str]:
    return [
        t.lower()
        for t in re.split(r"[\s,|/_\-]+", name)
        if t and t.lower() not in _STOP and len(t) >= 3
    ]


def names_mentioned_in_text(
    text: str,
    cast_pool: list[str],
) -> list[str]:
    """Return cast names that are actually spoken in this scene.

    Ordered by first appearance in the line, then match strength. Generic for any
    series — cast_pool comes from the script agent's searchTerms.
    """
    raw = re.sub(r"[^a-zA-Z0-9\s]", " ", (text or "").lower())
    raw = re.sub(r"\s+", " ", raw).strip()
    blob = f" {raw} "

    scored: list[tuple[int, int, str]] = []  # (first_pos, -strength, name)
    for name in cast_pool:
        tokens = _name_tokens(name)
        if not tokens:
            continue
        positions: list[int] = []
        hits = 0
        for t in tokens:
            alts = {t, _romaji_fold(t), *_romaji_folds(t)}
            best = None
            for alt in alts:
                needle = f" {alt} "
                idx = blob.find(needle)
                if idx >= 0:
                    hits += 1
                    best = idx if best is None else min(best, idx)
            if best is not None:
                positions.append(best)
        if hits <= 0:
            continue
        first = min(positions) if positions else 9999
        strength = hits * 10 + (5 if hits >= min(2, len(tokens)) else 0)
        scored.append((first, -strength, name))

    scored.sort()
    out: list[str] = []
    seen: set[str] = set()
    for _, __, name in scored:
        key = " ".join(sorted(_romaji_fold(t) for t in _name_tokens(name)))
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def pick_terms_for_scene(
    search_terms: list[str],
    *,
    scene_text: str = "",
    cast_pool: list[str] | None = None,
    scene_index: int = 0,
) -> list[str]:
    """Decide which character(s) to show for this beat.

    Priority:
      1. Cast members mentioned in the narration
      2. Script searchTerms that also appear in the narration
      3. Script searchTerms as written
      4. Rotate cast_pool so multi-character videos don't stick on one face
    """
    pool = [str(t).strip() for t in (cast_pool or []) if str(t).strip()]
    scripted = [str(t).strip() for t in (search_terms or []) if str(t).strip()]
    for t in scripted:
        if t not in pool:
            pool.append(t)

    mentioned = names_mentioned_in_text(scene_text, pool) if scene_text else []
    if mentioned:
        # Keep a secondary from searchTerms if different character
        secondary = [t for t in scripted if t not in mentioned[:1]]
        return (mentioned[:2] + secondary)[:2]

    # searchTerms that at least share a token with the line
    if scene_text and scripted:
        soft = names_mentioned_in_text(scene_text, scripted)
        if soft:
            return soft[:2]

    if scripted:
        return scripted[:2]

    if pool:
        # Agent didn't set terms — rotate cast so panels vary
        return [pool[scene_index % len(pool)]]
    return []


def resolve_anime_asset(
    search_terms: list[str],
    *,
    scene_text: str = "",
    anime_hint: str = "",
    used_ids: set[str] | None = None,
    used_urls: set[str] | None = None,
    prefer_video: bool = False,
    scene_index: int = 0,
    cast_pool: list[str] | None = None,
) -> AnimeAsset:
    """Search Safebooru then AniList for the character this scene is talking about."""
    del prefer_video  # Giphy removed from anime-theory
    used_ids = used_ids if used_ids is not None else set()
    used_urls = used_urls if used_urls is not None else set()

    primary = pick_terms_for_scene(
        search_terms,
        scene_text=scene_text,
        cast_pool=cast_pool,
        scene_index=scene_index,
    )
    if not primary and anime_hint.strip():
        primary = [anime_hint.strip()]
    if not primary:
        raise FootageError("No searchTerms from script and no anime hint.")

    print(
        f"      [cast] scene mentions -> {primary!r}"
        + (f" (from text)" if scene_text else ""),
        flush=True,
    )

    def _already_shown(a: AnimeAsset) -> bool:
        if a.url in used_urls:
            return True
        if a.asset_id and a.asset_id in used_ids:
            return True
        base = _char_base_id(a.asset_id)
        return bool(base and base in used_ids)

    # 1–2) For EACH mentioned character in order: Safebooru then AniList.
    # Do not mix later cast into the pool before the lead face is resolved.
    for term in primary:
        sb_faces: list[AnimeAsset] = []
        for variant in _query_variants(term, anime_hint)[:3]:
            sb_faces.extend(_search_safebooru(variant, anime_hint=anime_hint, limit=12))
        for asset in sb_faces:
            if asset.url and not _already_shown(asset) and _asset_matches_term(asset, term):
                return asset
        try:
            anilist_faces = _search_characters(term, anime_hint=anime_hint, limit=10)
        except FootageError:
            anilist_faces = []
        for asset in anilist_faces:
            if (
                asset.source == "anilist_character"
                and asset.url
                and not _already_shown(asset)
                and _name_match_score(term, asset.title.split("(")[0].strip()) >= 70
            ):
                return asset
        # Accept any unused Safebooru hit for this term even if title match is soft
        for asset in sb_faces:
            if asset.url and not _already_shown(asset):
                return asset

    # 3) Other cast actually spoken in this line
    for name in cast_pool or []:
        if name in primary:
            continue
        if scene_text and name not in names_mentioned_in_text(scene_text, [name]):
            continue
        for asset in _search_safebooru(name, anime_hint=anime_hint, limit=5):
            if asset.url and not _already_shown(asset) and _asset_matches_term(asset, name):
                return asset

    # 4) Last resort — series art
    if anime_hint:
        try:
            media = _search_media(anime_hint, anime_hint=anime_hint, limit=12)
            for asset in media:
                if asset.url and not _already_shown(asset):
                    return asset
            if media and media[0].url:
                return media[0]
        except FootageError:
            pass

    raise FootageError(
        f"No Safebooru/AniList asset for searchTerms={primary!r} anime={anime_hint!r} "
        f"text={scene_text[:40]!r}"
    )

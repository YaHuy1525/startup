"""In-container shortform pipeline smoke tests."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"

STORY = {
    "title": "TIFU by replacing all my coffee with decaf",
    "url": "https://www.reddit.com/r/tifu/comments/test/docker/",
    "body": (
        "I (28M) live with a roommate who drinks my coffee every morning without asking. "
        "Last month I quietly swapped the whole bag for decaf and said nothing. After three "
        "weeks he asked why he felt tired all the time. I told him. He laughed for a second "
        "then got weirdly quiet. Now he buys his own coffee and we barely talk. Not sure if "
        "I won or lost."
    ),
    "author": "docker_test",
    "upvotes": 1000,
}


def post(path: str, body: dict, timeout: int = 180):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"error": raw[:800]}
        return exc.code, parsed
    except Exception as exc:  # noqa: BLE001
        return None, {"error": str(exc)}


def unwrap(payload: dict) -> dict:
    if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict):
        return payload["result"]
    return payload


def main() -> int:
    results: list[tuple[str, bool]] = []

    code, status = post("/shortform/status", {})
    res = unwrap(status)
    print(
        "1 STATUS",
        code,
        "ok=",
        res.get("ok"),
        "root=",
        res.get("shortform_root"),
        "aitoearn=",
        res.get("aitoearn_enabled"),
        "videos=",
        len(res.get("recent_videos") or []),
    )
    results.append(("status", code == 200 and res.get("ok") is True))

    code, mon = post("/qwenpaw/skill/shortform_monitor", {})
    print(
        "2 SKILL_MONITOR",
        code,
        "success=",
        mon.get("success"),
        "ok=",
        (mon.get("result") or {}).get("ok"),
    )
    results.append(("skill_monitor", code == 200 and mon.get("success") is True))

    code, script = post("/shortform/pipeline", {"stage": "script", "story": STORY, "style": "meme"})
    res = unwrap(script)
    print(
        "3 SCRIPT",
        code,
        "ok=",
        res.get("ok"),
        "scenes=",
        res.get("scene_count"),
        "err=",
        res.get("error"),
    )
    results.append(("script", code == 200 and res.get("ok") is True))
    scenes = (res.get("scenes") or [])[:2]

    code, memes = post("/shortform/pipeline", {"stage": "find_memes", "scenes": scenes})
    mres = unwrap(memes)
    print("4 FIND_MEMES", code, "ok=", mres.get("ok"), "picks=", mres.get("count"))
    for p in mres.get("picks") or []:
        print(
            "   -",
            p.get("source"),
            "q=",
            p.get("query_used"),
            "reason=",
            (p.get("reason") or "")[:60],
        )
    results.append(("find_memes", code == 200 and mres.get("ok") is True))

    code, voice = post("/shortform/pipeline", {"stage": "voice", "scenes": scenes[:1]})
    vres = unwrap(voice)
    print(
        "5 VOICE",
        code,
        "ok=",
        vres.get("ok"),
        "job=",
        vres.get("job_id"),
        "dur=",
        (vres.get("scenes") or [{}])[0].get("duration"),
    )
    results.append(("voice", code == 200 and vres.get("ok") is True))

    code, pub = post(
        "/shortform/pipeline",
        {
            "stage": "publish",
            "file": "/short-form-pipeline/out/meme-smoketest.mp4",
            "title": "Docker dry-run shortform",
            "channels": ["tiktok", "youtube"],
            "dry_run": True,
        },
    )
    pres = unwrap(pub)
    print("6 PUBLISH_DRY", code, "ok=", pres.get("ok"), "dry_run=", pres.get("dry_run"))
    results.append(("publish_dry", code == 200 and pres.get("ok") is True))

    code, fetch = post(
        "/shortform/pipeline",
        {"stage": "fetch", "subreddit": "tifu", "time": "week", "limit": 1},
    )
    fres = unwrap(fetch)
    print(
        "7 FETCH",
        code,
        "ok=",
        fres.get("ok"),
        "count=",
        fres.get("count"),
        "err=",
        (fres.get("error") or "")[:80],
    )
    # Pass if HTTP 200 even when Reddit is rate-limited (ok may be False).
    results.append(("fetch_no_crash", code == 200))

    # Optional render smoke — expensive; use one short scene if script worked.
    render_ok = False
    if scenes:
        tiny = [
            {
                "text": scenes[0].get("text") or "Wait until you hear this.",
                "searchTerms": scenes[0].get("searchTerms") or ["shocked face"],
            }
        ]
        code, rend = post(
            "/shortform/pipeline",
            {"stage": "render", "scenes": tiny, "filename": "meme-docker-smoke.mp4"},
            timeout=600,
        )
        rres = unwrap(rend)
        print(
            "8 RENDER",
            code,
            "ok=",
            rres.get("ok"),
            "file=",
            rres.get("file"),
            "err=",
            (rres.get("error") or "")[:120],
        )
        render_ok = code == 200 and rres.get("ok") is True
    results.append(("render", render_ok))

    print("\n=== SUMMARY ===")
    for name, ok in results:
        print(("PASS" if ok else "FAIL"), name)
    passed = sum(1 for _, ok in results if ok)
    print(f"TOTAL {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

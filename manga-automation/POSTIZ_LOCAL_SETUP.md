# Postiz Local Setup (No API SaaS Cost)

This project already supports Postiz through:

- `scripts/adapters/postiz_client.py`
- `scripts/adapters/postiz_bridge.py`
- worker routes:
  - `POST /adapters/postiz`
  - `POST /adapters/postiz/integrations-map`
  - `POST /adapters/postiz/schedule-brief`

Use this guide to run Postiz locally and connect it to this system.

---

## 1) Run Postiz locally

Use the official Postiz self-host deployment from their docs/repo:

- Repo: [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app)
- API docs: [docs.postiz.com/public-api](https://docs.postiz.com/public-api)

Postiz typically exposes:

- Frontend UI: `http://localhost:4200`
- Backend API: `http://localhost:3000`

Your app talks to Postiz backend at:

- `http://localhost:3000/public/v1`

---

## 2) Configure this project

In `manga-automation/.env` set:

```ini
POSTIZ_PUBLIC_API_BASE=http://localhost:3000/public/v1
POSTIZ_API_KEY=your_local_postiz_public_api_key
POSTIZ_PINTEREST_BOARD=your_board_id_or_name
POSTIZ_AUTOPUBLISH_SLUGS=tiktok,youtube_shorts,instagram_reels,pinterest_video,x_twitter_threads
```

Optional hard mapping if auto detection is ambiguous:

```ini
POSTIZ_INTEGRATION_IDS_JSON={"tiktok":"...","youtube":"...","instagram":"...","pinterest":"...","x":"..."}
```

After env changes, restart worker:

```bash
docker compose up -d --force-recreate python-worker
```

---

## 3) Connect social accounts inside Postiz

In Postiz UI, connect each channel via OAuth (TikTok, YouTube, Instagram, Pinterest, X, etc).

Without connected integrations, your publish calls will skip those slugs.

---

## 4) Verify integration map from this app

```bash
curl -s -X POST http://localhost:8080/adapters/postiz/integrations-map \
  -H "Content-Type: application/json" \
  -d "{}"
```

Expected: provider -> integration ID map.

---

## 5) Publish one brief to multiple platforms

```bash
curl -s -X POST http://localhost:8080/adapters/postiz/schedule-brief \
  -H "Content-Type: application/json" \
  -d "{
    \"brief_id\": 1,
    \"media_path\": \"/data/videos/example.mp4",
    \"platform_slugs\": \"tiktok,youtube_shorts,instagram_reels,pinterest_video,x_twitter_threads\",
    \"post_type\": \"now\"
  }"
```

Notes:

- `media_path` is required for video-first platforms.
- The path must exist inside container (`python-worker`) filesystem.
- If no `platform_slugs` provided, defaults use `POSTIZ_AUTOPUBLISH_SLUGS`.

---

## 6) Common errors

- `401/403` from Postiz:
  - wrong `POSTIZ_API_KEY`
  - wrong `POSTIZ_PUBLIC_API_BASE`
- `no_integration_id_for_*`:
  - channel not connected in Postiz
  - fix with `POSTIZ_INTEGRATION_IDS_JSON`
- `media_required_not_provided`:
  - provide `media_path` for TikTok/YouTube/Instagram style posts

---

## 7) Recommended operating mode

1. Use native uploaders where stable (`/upload/instagram`, `/upload/pinterest`).
2. Use Postiz local as primary for API-hard social posting.
3. Keep `/rpa/session` as last-resort fallback.


# Omnichannel Content Factory — Setup Guide

This guide gets the **Genesis → briefs → omnichannel distribution** stack running: trend discovery, Claude briefs, Postgres state, editorial uploads, PDF products, podcast RSS, Postiz batch publishing, and optional direct platform uploaders.

---

## 1. Prerequisites

- **Docker** and **Docker Compose** (v2)
- **Anthropic API key** (`ANTHROPIC_API_KEY`) for Genesis briefs and editorial drafting
- **Git** (repo includes `manga-automation` as the app root for Compose)

Optional but common:

- **Medium** integration token, **Substack** draft email + SMTP for Pod 3
- **Postiz** (cloud or self-hosted) for networks that are hard to integrate directly
- **Pinterest / Instagram** credentials if you use native upload scripts

---

## 2. Environment file

Create `manga-automation/.env` (Compose reads it automatically). Minimum:

```ini
# ─── Required ─────────────────────────────────────────────────
DB_PASSWORD=your_secure_postgres_password
ANTHROPIC_API_KEY=sk-ant-api03-...

# ─── Core DB (matches docker-compose postgres service) ─────────
# Inside containers the host is `postgres`. On the host machine use localhost:5434.
# DATABASE_URL is injected for python-worker; for local CLI use:
# DATABASE_URL=postgresql://manga_user:YOUR_PASSWORD@localhost:5434/manga_automation
```

Add as you enable features:

```ini
# ─── Genesis (optional overrides) ──────────────────────────────
GENESIS_BRIEF_MODEL=claude-sonnet-4-20250514
GENESIS_TOP_SIGNALS=20
GENESIS_TIMEOUT=15
GENESIS_REDDIT_DELAY=2.0

# ─── Pod 3 — Editorial ───────────────────────────────────────
MEDIUM_INTEGRATION_TOKEN=
MEDIUM_AUTHOR_ID=
SUBSTACK_POST_EMAIL=your-pub@mg.substack.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
EDITORIAL_MODEL=claude-sonnet-4-20250514

# ─── Pod 4 — Podcast RSS ─────────────────────────────────────
PODCAST_TITLE=Trend Pulse
PODCAST_AUDIO_BASE_URL=https://your-cdn.example.com/audio
PODCAST_OUTPUT_DIR=data/podcast

# ─── Pod 5 / paths ───────────────────────────────────────────
DIGITAL_PRODUCTS_DIR=data/digital_products

# ─── Native uploaders ─────────────────────────────────────────
PINTEREST_ACCESS_TOKEN=
PINTEREST_BOARD_ID=
IG_SESSION_DIR=data/ig_sessions
# IG_PASS_MYUSERNAME=...

# ─── Postiz (API-hard platforms) ──────────────────────────────
POSTIZ_API_KEY=
# Self-hosted: https://your-postiz-host/public/v1
POSTIZ_PUBLIC_API_BASE=https://api.postiz.com/public/v1
POSTIZ_PINTEREST_BOARD=YourBoardNameOrId
POSTIZ_INTEGRATION_IDS_JSON={"tiktok":"...","youtube":"...","instagram":"...","pinterest":"...","x":"..."}
POSTIZ_AUTOPUBLISH_SLUGS=tiktok,youtube_shorts,instagram_reels,pinterest_video,x_twitter_threads
DEFAULT_UTM_LINK=https://your-site.example/landing

# ─── YouTube upload (legacy pipeline) ──────────────────────────
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=

# ─── RPA fallback (optional) ─────────────────────────────────
RPA_DRY_RUN=1
RPA_HEADLESS=0
# HTTPS_PROXY=http://user:pass@residential-proxy:port

# ─── Hermes Claude Ops Agent (optional) ──────────────────────
HERMES_MODEL=claude-sonnet-4-20250514
HERMES_TIMEOUT_SEC=25
# Set to 1 only if you want Hermes to execute safe actions
HERMES_AUTO_ACTIONS=0
```

Never commit `.env` with real secrets.

---

## 3. Start services

From the **`manga-automation`** directory:

```bash
docker compose up -d postgres redis python-worker
```

Wait until Postgres is healthy (`docker compose ps`).

- **Python worker HTTP:** `http://localhost:8080` (path `/health` → `{"status":"ok"}`)
- **Postgres (host):** `localhost:5434` → DB `manga_automation`, user `manga_user`

Bring up optional services (Mastra agents, ChromaDB, etc.) only if you need them; the omnichannel scripts used here only require **postgres** and **python-worker** for the flows below.

---

## 4. Database: schema and omnichannel migration

**Fresh database:** `database/schema.sql` runs as `01_schema.sql` on first container init.

**Omnichannel tables** live in `database/migrations/010_omnichannel_genesis.sql`. The Postgres image runs only **top-level** `.sql` files in `docker-entrypoint-initdb.d/`; files under the `migrations/` subfolder are **not** auto-applied on first boot. Apply them explicitly:

```bash
docker compose exec postgres psql -U manga_user -d manga_automation -f /docker-entrypoint-initdb.d/migrations/010_omnichannel_genesis.sql
```

**Existing database** (already initialized): run the same command once.

Verify:

```bash
docker compose exec postgres psql -U manga_user -d manga_automation -c "\dt genesis_*"
docker compose exec postgres psql -U manga_user -d manga_automation -c "\dt content_briefs"
```

You should see `genesis_categories`, `genesis_signals`, `content_briefs`, `master_assets`, `platform_distributions`, `digital_products`.

---

## 5. Run Genesis (discovery + briefs)

Inside the **`python-worker`** container the default **`WORKDIR` is `/app`** (`Dockerfile.python`). Scripts live at `/app/scripts`.

```bash
docker compose exec python-worker python3 scripts/genesis_discover.py --limit 15
docker compose exec python-worker python3 scripts/genesis_brief_generator.py --top 3
```

Or call the worker over HTTP:

```bash
curl -s -X POST http://localhost:8080/genesis/discover -H "Content-Type: application/json" -d "{\"limit\":15}"
curl -s -X POST http://localhost:8080/genesis/briefs -H "Content-Type: application/json" -d "{\"top\":3}"
```

**Notes:**

- Discovery uses public Reddit JSON, Hacker News, and TikTok (with `nodriver` / fallbacks). No Reddit API key required.
- Brief generation needs `ANTHROPIC_API_KEY`. Without it, a heuristic fallback runs (lower quality).

---

## 6. Omnichannel distribution

### 6.1 Preview the plan (no DB writes for plan-only actions)

Single category:

```bash
curl -s -X POST http://localhost:8080/omnichannel/plan -H "Content-Type: application/json" \
  -d "{\"category_slug\":\"tech\",\"profile\":\"minimal\"}"
```

Full matrix (many platforms):

```bash
curl -s -X POST http://localhost:8080/omnichannel/plan -H "Content-Type: application/json" \
  -d "{\"category_slug\":\"anime\",\"profile\":\"full\"}"
```

All seeded categories:

```bash
curl -s -X POST http://localhost:8080/omnichannel/plan-all -H "Content-Type: application/json" \
  -d "{\"profile\":\"full\"}"
```

### 6.2 Distribute one brief

Replace `BRIEF_ID` with an id from `content_briefs`:

```bash
curl -s -X POST http://localhost:8080/omnichannel/distribute -H "Content-Type: application/json" \
  -d "{\"brief_id\":BRIEF_ID,\"profile\":\"minimal\"}"
```

- **`profile":"minimal"`** — small platform set (safe for testing).
- **`profile":"full"`** — queues many `platform_distributions` rows; use when you intend to process the full catalog.

### 6.3 Distribute + Postiz in one call

After you configure Postiz (section 8), optional:

```bash
curl -s -X POST http://localhost:8080/omnichannel/distribute -H "Content-Type: application/json" \
  -d "{
    \"brief_id\": BRIEF_ID,
    \"profile\": \"minimal\",
    \"postiz_multichannel\": true,
    \"postiz_media_path\": \"/data/videos/your_short.mp4\",
    \"postiz_platform_slugs\": \"tiktok,youtube_shorts,instagram_reels\"
  }"
```

Paths must exist **inside** the `python-worker` container (e.g. under `/data/videos`).

### 6.4 CLI equivalents

```bash
docker compose exec python-worker python3 scripts/omnichannel_distributor.py --plan --category tech --profile full
docker compose exec python-worker python3 scripts/omnichannel_distributor.py --brief-id 1 --profile minimal
docker compose exec python-worker python3 scripts/omnichannel_distributor.py --auto --limit 2 --profile minimal
```

---

## 7. Worker routes (quick reference)

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness |
| `POST /genesis/discover` | Scrape signals into `genesis_signals` |
| `POST /genesis/briefs` | LLM briefs into `content_briefs` |
| `POST /omnichannel/plan` | JSON plan for `category_slug` + `profile` |
| `POST /omnichannel/plan-all` | Plan for every `genesis_categories` row |
| `POST /omnichannel/distribute` | Run distributor for `brief_id` |
| `POST /omnichannel/auto` | Top N draft briefs |
| `POST /editorial/publish` | Medium / Substack / LinkedIn (`platforms`) |
| `POST /products/generate` | PDF guides |
| `POST /podcast/generate-feed` | RSS XML |
| `POST /upload/instagram` | Reels (instagrapi) |
| `POST /upload/pinterest` | Video pin (Pinterest API v5) |
| `POST /adapters/postiz` | `action`: `list_integrations`, `upload`, `create_posts`, `schedule_brief`, … |
| `POST /adapters/postiz/schedule-brief` | Batch Postiz publish from a brief + optional media |
| `POST /adapters/postiz/integrations-map` | Debug provider → integration id map |
| `POST /rpa/session` | Playwright RPA dry-run / guarded upload path |
| `POST /hermes/status` | Collect runtime + DB snapshot |
| `POST /hermes/diagnose` | Claude diagnosis from snapshot |
| `POST /hermes/cycle` | Snapshot + diagnose + optional safe actions |

---

## 8. Postiz setup (recommended for API-difficult networks)

1. Create a Postiz account (cloud) or deploy [Postiz](https://github.com/gitroomhq/postiz-app) yourself.
2. In Postiz, connect **OAuth** for TikTok, YouTube, Instagram, Pinterest, X, etc.
3. Create a **Public API** key: Settings → Developers → Public API.
4. Set `POSTIZ_API_KEY` and, if self-hosted, `POSTIZ_PUBLIC_API_BASE` to `https://<backend>/public/v1` per [docs](https://docs.postiz.com/public-api).
5. Optional: call `POST /adapters/postiz/integrations-map` and copy ids into `POSTIZ_INTEGRATION_IDS_JSON` if auto-discovery does not match.
6. For Pinterest, set `POSTIZ_PINTEREST_BOARD`.
7. Use `POST /adapters/postiz/schedule-brief` with `brief_id` and `media_path` for short-form video destinations.

Respect Postiz rate limits (documented as **30 requests/hour** for the public API); batch many destinations in **one** `/posts` body when possible.

---

## 9. Editorial, podcast, and products

- **Editorial:** configure Medium token, Substack SMTP, then `POST /editorial/publish` with `brief_id` and `platforms`.
- **Podcast:** generate audio with your existing TTS pipeline, set `master_assets.base_audio_path` and status appropriately, then `POST /podcast/generate-feed`.
- **PDF products:** `POST /products/generate` or run omnichannel with `products` channel; outputs default under `data/digital_products`.

---

## 10. Native uploaders (when not using Postiz)

- **Instagram:** session files under `IG_SESSION_DIR`; password env `IG_PASS_<USERNAME_UPPER>`.
- **Pinterest:** `PINTEREST_ACCESS_TOKEN`, `PINTEREST_BOARD_ID`; uses Pinterest v5 media upload flow.

---

## 11. Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `DATABASE_URL` / connection errors | `DATABASE_URL` inside worker must point at `postgres:5432` with correct password. |
| Genesis “no categories” | Run migration `010_omnichannel_genesis.sql`; verify `genesis_categories` has rows. |
| Brief generation empty | Run `genesis_discover` first; ensure `ANTHROPIC_API_KEY` is set for LLM path. |
| Postiz 401 / 403 | API key, base URL (cloud vs self-hosted), and integration OAuth in Postiz UI. |
| Postiz validation errors | Compare your payload to Postiz “Generate Output” wizard JSON; enums (e.g. TikTok privacy) vary. |
| TikTok / IG blocks | Residential proxy, headful RPA, lower frequency; see `scripts/rpa/playwright_rpa_boilerplate.py`. |

---

## 12. Suggested automation order

1. Apply DB migration `010`.
2. Hourly: `genesis_discover` → `genesis_briefs` (top N).
3. Daily: `omnichannel/distribute` with `profile=minimal` until pipelines are stable.
4. After video render jobs fill `master_assets` / files on disk: run uploaders or **Postiz schedule-brief** with `media_path`.
5. Expand to `profile=full` only when fulfillment workers can drain `platform_distributions`.

---

## 13. Optional: “Hermes” on your PC (two different things)

People say **Hermes** in two ways. Both can sit on your machine; they solve different problems for this repo.

### A) Hermes **Agent** (Nous Research)

- **What it is:** An open-source, **persistent** agent ([overview](https://hermes-agent.org/)) with memory, optional **messaging bridges** (Telegram, Discord, Slack, WhatsApp, etc.), and tooling so it can run longer autonomous tasks—not just a single chat turn.
- **How it runs with local models:** Via **Ollama** using an OpenAI-compatible base URL ([Ollama + Hermes integration](https://docs.ollama.com/integrations/hermes))—e.g. `http://127.0.0.1:11434/v1`.
- **Windows:** Use **WSL2** and install/run Hermes from Linux/WSL; native Windows is experimental per their docs.

**What it can help with for *manga-automation*:**

| Use | How it fits |
|-----|-------------|
| **Ops copilot** | Hit your worker HTTP API (`/health`, `/genesis/*`, `/omnichannel/*`) from natural language if you give it curl/scripts or small wrappers. |
| **Always-on drafts** | Propose captions, hashtags, or email copy from briefs **without** sending everything to Claude—if you point it at a **local** Ollama model. |
| **Monitoring** | Read logs / summarize failures across runs (with filesystem or log access you explicitly grant). |
| **Telegram/Discord trigger** | If you enable the gateway, you can ping the agent remotely while the heavy jobs still run on your PC or server. |

**What it does *not* replace out of the box:** Your **Genesis brief generator** and **editorial publisher** today call **Anthropic** in code (`ANTHROPIC_API_KEY`). Hermes Agent does not automatically swap those calls; you’d add a separate code path or use Hermes **beside** the stack as an orchestrator.

**Quick install path (high level):** Install [Ollama](https://ollama.com), pull a model, then follow [Hermes + Ollama](https://docs.ollama.com/integrations/hermes) (`ollama launch hermes` or the manual wizard to set base URL `http://127.0.0.1:11434/v1`).

### In-repo Hermes endpoint (implemented)

This repo also now includes `scripts/hermes_agent.py` powered by your `ANTHROPIC_API_KEY`.
It is exposed via worker routes:

```bash
curl -s -X POST http://localhost:8080/hermes/status   -H "Content-Type: application/json" -d "{}"
curl -s -X POST http://localhost:8080/hermes/diagnose -H "Content-Type: application/json" -d "{\"objective\":\"Find blocking issues\"}"
curl -s -X POST http://localhost:8080/hermes/cycle    -H "Content-Type: application/json" -d "{\"execute_actions\":false}"
```

Safe auto-actions are disabled by default. To allow execution:

- set `HERMES_AUTO_ACTIONS=1` in `.env`
- call `/hermes/cycle` with `{"execute_actions": true}`

Current safe actions:
- `health_check`
- `genesis_discover`
- `genesis_briefs`
- `omnichannel_auto`
- `postiz_integrations_map`

### B) **Nous Hermes** LLM weights (e.g. `nous-hermes2` in Ollama)

- **What it is:** A **family of chat models** ([Ollama library](https://ollama.com/library/nous-hermes2)) you run locally for general reasoning and coding—not the same product as Hermes Agent.
- **What it helps with:** Offline drafting, brainstorming, scripting, summarizing CSV/JSON exports from your DB—**if** you wire your app or Cursor to `http://localhost:11434/v1` (OpenAI-compatible).

**Limits for your pipeline:** Long, high-quality **briefs** and **articles** that match Claude quality usually still need cloud models or a **large** local model + careful prompting; small local models are better for drafts and scaffolding.

---

## 14. Legal and platform compliance

Automate only where your jurisdiction and each platform’s **Terms of Service** allow. Label ads, affiliates, and sponsored content as required. This guide does not provide legal advice.

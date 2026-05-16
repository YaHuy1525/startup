# Omnichannel System Usage Guide

This is the **day-to-day operator guide** for running the app after setup.

If you still need install/environment steps, use `OMNICHANNEL_SETUP_GUIDE.md` first.

---

## 1) Quick start (daily)

From `manga-automation/`:

```bash
docker compose up -d postgres redis python-worker
```

Check health:

```bash
curl -s http://localhost:8080/health
```

Expected:

```json
{"status":"ok","service":"python-worker"}
```

AiToEarn-first mode (global environment):

```bash
export AITOEARN_PRIMARY=true
export AITOEARN_BASE_URL=https://aitoearn.ai
export AITOEARN_API_KEY=your_key_here
```

---

## 2) Standard content pipeline (Trend -> Brief -> Distribution)

### Step A: Discover trends

```bash
curl -s -X POST http://localhost:8080/genesis/discover \
  -H "Content-Type: application/json" \
  -d "{\"limit\":15}"
```

Optional categories:

```bash
curl -s -X POST http://localhost:8080/genesis/discover \
  -H "Content-Type: application/json" \
  -d "{\"categories\":\"anime,tech\",\"limit\":12}"
```

### Step B: Generate briefs

```bash
curl -s -X POST http://localhost:8080/genesis/briefs \
  -H "Content-Type: application/json" \
  -d "{\"top\":3}"
```

### Step C: Plan distribution before posting

Minimal plan:

```bash
curl -s -X POST http://localhost:8080/omnichannel/plan \
  -H "Content-Type: application/json" \
  -d "{\"category_slug\":\"anime\",\"profile\":\"minimal\"}"
```

Full platform matrix plan (from `lmao.html` catalog):

```bash
curl -s -X POST http://localhost:8080/omnichannel/plan \
  -H "Content-Type: application/json" \
  -d "{\"category_slug\":\"anime\",\"profile\":\"full\"}"
```

### Step D: Distribute

Single brief:

```bash
curl -s -X POST http://localhost:8080/omnichannel/distribute \
  -H "Content-Type: application/json" \
  -d "{\"brief_id\":1,\"profile\":\"minimal\"}"
```

Auto top briefs:

```bash
curl -s -X POST http://localhost:8080/omnichannel/auto \
  -H "Content-Type: application/json" \
  -d "{\"limit\":3,\"profile\":\"minimal\"}"
```

---

## 3) Platform usage modes

The system supports 3 practical execution modes:

1. **Native API/upload scripts** (best when available and stable)
2. **Postiz batch publishing** (best for API-hard social platforms)
3. **RPA fallback** (last resort for sites with difficult/no APIs)

---

## 4) Native publish paths you can run now

### Editorial (Pod 3)

```bash
curl -s -X POST http://localhost:8080/editorial/publish \
  -H "Content-Type: application/json" \
  -d "{\"brief_id\":1,\"platforms\":\"medium,substack,linkedin\"}"
```

### Digital products (Pod 5)

```bash
curl -s -X POST http://localhost:8080/products/generate \
  -H "Content-Type: application/json" \
  -d "{\"brief_ids\":[1]}"
```

### Podcast RSS (Pod 4)

```bash
curl -s -X POST http://localhost:8080/podcast/generate-feed \
  -H "Content-Type: application/json" \
  -d "{\"limit\":50}"
```

### Instagram uploader

```bash
curl -s -X POST http://localhost:8080/upload/instagram \
  -H "Content-Type: application/json" \
  -d "{\"video_path\":\"/data/videos/example.mp4\",\"caption\":\"...\",\"account\":\"your_ig_username\"}"
```

### Pinterest uploader

```bash
curl -s -X POST http://localhost:8080/upload/pinterest \
  -H "Content-Type: application/json" \
  -d "{\"video_path\":\"/data/videos/example.mp4\",\"title\":\"...\",\"description\":\"...\"}"
```

---

## 5) Postiz mode (recommended for API-hard platforms)

Use this for TikTok / YouTube Shorts / Instagram / Pinterest / X style multi-posting where official APIs are brittle.

If you want zero SaaS API cost, run Postiz locally and follow `POSTIZ_LOCAL_SETUP.md`.

### 5.1 Check integration mapping

```bash
curl -s -X POST http://localhost:8080/adapters/postiz/integrations-map \
  -H "Content-Type: application/json" \
  -d "{}"
```

### 5.2 Schedule one brief to many platforms

```bash
curl -s -X POST http://localhost:8080/adapters/postiz/schedule-brief \
  -H "Content-Type: application/json" \
  -d "{
    \"brief_id\": 1,
    \"media_path\": \"/data/videos/example.mp4\",
    \"platform_slugs\": \"tiktok,youtube_shorts,instagram_reels,pinterest_video,x_twitter_threads\",
    \"post_type\": \"now\"
  }"
```

### 5.3 One-call omnichannel + Postiz

```bash
curl -s -X POST http://localhost:8080/omnichannel/distribute \
  -H "Content-Type: application/json" \
  -d "{
    \"brief_id\": 1,
    \"profile\": \"minimal\",
    \"postiz_multichannel\": true,
    \"postiz_media_path\": \"/data/videos/example.mp4\"
  }"
```

---

## 6) RPA fallback mode (only when needed)

Default is safe dry-run.

```bash
curl -s -X POST http://localhost:8080/rpa/session \
  -H "Content-Type: application/json" \
  -d "{\"target\":\"pinterest\",\"dry_run\":true}"
```

Only enable real browser actions after validating selectors and credentials.

---

## 7) Hermes ops agent usage (Claude-powered)

### Snapshot only

```bash
curl -s -X POST http://localhost:8080/hermes/status \
  -H "Content-Type: application/json" -d "{}"
```

### Diagnose

```bash
curl -s -X POST http://localhost:8080/hermes/diagnose \
  -H "Content-Type: application/json" \
  -d "{\"objective\":\"Find blockers in publishing pipeline\"}"
```

### Cycle (diagnose + optional actions)

```bash
curl -s -X POST http://localhost:8080/hermes/cycle \
  -H "Content-Type: application/json" \
  -d "{\"execute_actions\":false}"
```

To allow safe auto-actions:

- set `.env`: `HERMES_AUTO_ACTIONS=1`
- send: `{"execute_actions": true}`

### Full-ops orchestration (AiToEarn-first)

```bash
# Dry run (validates routing + policy, no execution)
curl -s -X POST http://localhost:8080/hermes/full-ops \
  -H "Content-Type: application/json" \
  -d "{\"dry_run\":true}"

# Active run (Trend -> Create -> Publish -> Engage -> Monetize)
curl -s -X POST http://localhost:8080/hermes/full-ops \
  -H "Content-Type: application/json" \
  -d "{\"category\":\"finance\",\"mode\":\"full\",\"profile\":\"minimal\"}"
```

---

## 8) Daily runbook (recommended)

1. `GET /health`
2. `POST /hermes/status` (verify AiToEarn integration probe)
3. `POST /hermes/full-ops` with `{"dry_run": true}`
4. `POST /hermes/full-ops` with `{"category":"finance","mode":"full","profile":"minimal"}`
5. If publish degradation occurs: keep `AITOEARN_FALLBACK_LOCAL=true`
6. `POST /adapters/postiz/schedule-brief` for explicit social replay when needed
7. `POST /hermes/diagnose` and review failures

---

## 9) Useful DB checks

Use Postgres container:

```bash
docker compose exec postgres psql -U manga_user -d manga_automation -c "SELECT status, count(*) FROM content_briefs GROUP BY status ORDER BY status;"
docker compose exec postgres psql -U manga_user -d manga_automation -c "SELECT platform, status, count(*) FROM platform_distributions GROUP BY platform, status ORDER BY platform, status;"
docker compose exec postgres psql -U manga_user -d manga_automation -c "SELECT platform, format, error_log, created_at FROM platform_distributions WHERE status='failed' ORDER BY created_at DESC LIMIT 20;"
```

---

## 10) Common failure patterns

- **`POSTIZ_API_KEY` invalid**: `/adapters/postiz/*` returns auth errors.
- **No Postiz integration IDs**: posts get skipped with `no_integration_id_for_*`.
- **Missing media for video networks**: skipped as `media_required_not_provided`.
- **No categories/briefs**: ensure migration `010_omnichannel_genesis.sql` applied and run discovery first.
- **RPA failures**: selectors stale; keep RPA as fallback, not primary.

---

## 11) Safety policy

- Run `profile=minimal` until stable.
- Enable `profile=full` only with monitoring and queue drain capacity.
- Keep `HERMES_AUTO_ACTIONS=0` by default in production.
- Start with `AITOEARN_PRIMARY=true` and `AITOEARN_FALLBACK_LOCAL=true` during rollout.
- Never store real secrets in docs or git-tracked files.

---

## 12) Verification rollout checklist (dry-run -> shadow-run -> active-run)

1. **Dry-run**
   - `POST /hermes/full-ops` with `{"dry_run": true}`
   - Confirm response includes `execution_policy` and no stage side effects.
2. **Shadow-run**
   - Keep `AITOEARN_PRIMARY=true` and `AITOEARN_FALLBACK_LOCAL=true`.
   - Run `POST /hermes/full-ops` with a fixed `run_id` and `mode: "light"`.
   - Verify publish step reports `execution_path` and capture failed channels.
3. **Active-run**
   - Promote to `mode: "full"` once shadow-run passes.
   - Monitor success/failure deltas per stage from Hermes step output.
4. **Failure replay**
   - Re-run with same `run_id` and explicit `idempotency_key` in publish payload.
   - If remote fails, keep fallback enabled and replay through local path.


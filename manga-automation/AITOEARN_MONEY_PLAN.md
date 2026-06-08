# AiToEarn Money-Making Plan

> Uses the existing manga-automation infrastructure to earn on AiToEarn.
> Strategy: start with zero-follower tasks, build audience, stack revenue streams.

---

## Phase 0: Setup (One-Time, Today)

### 0.1 Register on AiToEarn
- Create account at https://aitoearn.ai
- Get your API key (`AITOEARN_API_KEY`)
- Put it in `.env`

### 0.2 Seed the Database with AiToEarn Tasks

The existing marketplace schema (`merchants`, `promotion_tasks`, `task_assignments`) is empty. Run this seed SQL:

```sql
-- Merchants
INSERT INTO merchants (name, category, contact_email, status) VALUES
('AiToEarn Self-Promo', 'social_media', 'tasks@aitoearn.ai', 'active'),
('Dog Car Seat Brand', 'pets', 'tasks@aitoearn.ai', 'active'),
('Clothing Brand', 'fashion', 'tasks@aitoearn.ai', 'active'),
('Water Bottle Organizer', 'home', 'tasks@aitoearn.ai', 'active'),
('Redmi Tablet Cases', 'tech_accessories', 'tasks@aitoearn.ai', 'active'),
('Jimeng AI Video', 'ai_tools', 'tasks@aitoearn.ai', 'active');

-- CPS Tasks (25% commission, no follower minimum — START HERE)
INSERT INTO promotion_tasks (merchant_id, title, description, model, reward, target_platforms, status) VALUES
(2, 'Dog Car Seat Cover - 25% CPS', 'Promote dog car seat covers via affiliate link', 'cps', 0.25, '["tiktok","instagram","youtube","x"]', 'open'),
(3, 'T-Shirt / Sweatshirt - 25% CPS', 'Promote clothing items via affiliate link', 'cps', 0.25, '["tiktok","instagram","youtube","x"]', 'open'),
(4, 'Water Bottle Organizer - 25% CPS', 'Promote water bottle organizers via affiliate link', 'cps', 0.25, '["tiktok","instagram","youtube","x"]', 'open'),
(5, 'Redmi Tablet Case - 25% CPS', 'Promote Redmi tablet cases via affiliate link', 'cps', 0.25, '["tiktok","instagram","youtube","x"]', 'open');

-- Fixed Price Tasks (need 1k followers — target AFTER building audience)
INSERT INTO promotion_tasks (merchant_id, title, description, model, reward, budget, target_platforms, status) VALUES
(1, 'Promote AiToEarn on X/Twitter', 'Post about AiToEarn platform', 'cpm', 3.00, 300.00, '["x"]', 'open'),
(1, 'Promote AiToEarn on Instagram', 'Post about AiToEarn platform', 'cpm', 2.00, 200.00, '["instagram"]', 'open'),
(1, 'Promote AiToEarn on Facebook', 'Post about AiToEarn platform', 'cpm', 1.00, 100.00, '["facebook"]', 'open');
```

### 0.3 Configure the Pipeline

```bash
# In .env, ensure:
ANTHROPIC_API_KEY=sk-ant-...
AITOEARN_API_KEY=your_aitoearn_key
AITOEARN_PRIMARY=false     # We use local pipeline, not their API
AITOEARN_FALLBACK_LOCAL=true
```

---

## Phase 1: CPS Affiliate — Zero-Follower Start (Week 1-2)

**Goal:** Earn first commissions from affiliate products. No followers required.

### Strategy: Product-Review Shorts on TikTok + YouTube Shorts

These tasks are *affiliate links* — you earn 25% of each sale. The automation handles everything except the actual AiToEarn proof submission.

### 1.1 Content Plan (per product, per week)

| Product | Content Angle | Platform | Count/Week |
|---------|--------------|----------|------------|
| Dog car seat cover | "This dog car hack is genius" POV video | TikTok | 3 |
| T-shirt/sweatshirt | "The most comfortable sweatshirt I've found" fit check | TikTok | 3 |
| Water bottle organizer | "Fix your cluttered kitchen in 30 seconds" | TikTok | 3 |
| Tablet case | "Best budget tablet accessories under $10" | TikTok | 3 |

**Total: 12 videos/week** — within the `MAX_UPLOADS_PER_ACCOUNT_DAY=3` limit (4 days of posting).

### 1.2 Automation Flow

```
n8n Cron (daily 9am) 
  → POST /aitoearn/stage/trend    category=fashion,pets,home,tech_accessories
  → POST /aitoearn/stage/create   limit=3
  → POST /aitoearn/stage/publish  (uploads to TikTok + YouTube Shorts)
  → Telegram alert: /status       (check results)
```

**Manual steps (once per video):**
1. After publish, grab the video link
2. Post it to AiToEarn as task proof with your affiliate link in bio/caption
3. AiToEarn tracks CPS conversions automatically

### 1.3 Using the Telegram Bot

The existing Telegram bot can trigger this:
```
/fetch_trending 20                       Search trending topics
/arb_discover US 20                      Find viral content source material
/arb_download 5                          Download source videos  
/generate_video <id>                     Build the video
/upload_tiktok <video_id>                Publish to TikTok
```

---

## Phase 2: Build to 1,000 Followers (Week 2-4)

**Goal:** Hit 1k followers on at least one platform to unlock fixed-price tasks.

### 2.1 Engagement Engine — Run Daily

The existing engagement engine can be pointed at any published content:

```bash
# Light mode (likes only, safe)
curl -X POST http://localhost:18080/aitoearn/stage/engage \
  -H "Content-Type: application/json" \
  -d '{"platform": "tiktok"}'

# Or via Telegram:
/worker POST /aitoearn/stage/engage {"platform":"tiktok"}
```

**Engagement loop** (automate via n8n or agent-scheduler):
1. Find target accounts in same niche (dog products, fashion, tech)
2. Like their recent posts (`ENGAGE_MAX_LIKES=30`)
3. Post smart AI comments on their content (`ENGAGE_AI_MODEL=claude-sonnet-4-6`)
4. Follow relevant accounts (`ENGAGE_MAX_FOLLOWS=15`)
5. Reciprocity effect → followers come back

### 2.2 Content Cadence

```
Weekly schedule (n8n 10_balanced_multiplatform_schedule.json):
  Mon: 3 product videos (TikTok + YT Shorts)  
  Tue: 3 product videos (TikTok + Instagram Reels)
  Wed: 3 product videos (TikTok + YT Shorts)
  Thu: 3 product videos (TikTok + Instagram Reels)
  Fri: Engagement day (no posting, just engage)
  Sat: 3 product videos (TikTok + YT Shorts)
  Sun: Weekly recap + optimize (n8n 11_monetization_weekly_optimization.json)
```

---

## Phase 3: Stack Fixed-Price Tasks (Once at 1k Followers)

**Goal:** Add $1-$5/post to existing CPS revenue.

### 3.1 AiToEarn Self-Promo Posts

The easiest fixed-price task — promote AiToEarn itself for $1/post, no follower limit:
- 1 tweet/day about AiToEarn = $30/month base
- 1 Instagram story/day = $30/month
- 1 Facebook post/day = $30/month

**Total floor: ~$90/month from self-promo alone**

### 3.2 Twitter/X Promo Posts ($1-$5, need 1k-2k followers)

Your Twitter growth content IS the task proof. Each product review you post can count:
- Post → submit as proof → get paid
- The content you're already creating for CPS earns AGAIN as fixed-price

---

## Phase 4: CPE Tasks — Engagement Revenue (Once You Have Traction)

**Goal:** Get paid per engagement on your existing content.

### 4.1 TikTok CPE ($5/1k engagements)

Once your CPS product videos get organic views, you get paid ON TOP:
- Video gets 10k views, 500 likes, 50 comments, 20 shares = 570 engagements
- 570 engagements × $5/1000 = **$2.85 extra per video**
- At 12 videos/week: **~$34/week extra**

### 4.2 YouTube CPE ($10/1k engagements)

Same videos reposted to YouTube Shorts:
- YouTube Shorts typically get higher view counts
- At 5k views/video × 12 videos = 60k views → **~$60/week extra**

### 4.3 Jimeng CPE ($0.80/interaction, $20k cap — the whale task)

This is the highest-potential task. Jimeng is an AI video app — your AI-generated content IS their perfect demo:
1. Use the existing `finance_video_ai.py` or Revid.ai integration to create Jimeng-style AI videos
2. Post them, tag Jimeng
3. Each interaction = $0.80
4. If a video goes viral (1M views, 50k interactions) = **$40,000 cap per video**

**Strategy:** Create "how I made this AI video" content using Jimeng — it promotes the product AND shows the tool.

---

## Phase 5: Full Automation — Hands-Off Revenue (Month 2+)

### 5.1 n8n Cron Schedule

```
00 09 * * *  → 01_trend_detection.json       Refresh trends daily
15 09 * * *  → 02_video_generation.json       Generate 3 videos from top trends
30 09 * * *  → 03_publisher.json              Publish to all platforms
00 10 * * *  → 04_shadow_ban_monitor.json     Check account health
00 18 * * *  → 10_balanced_multiplatform_schedule.json  Evening batch
00 09 * * 0  → 11_monetization_weekly_optimization.json Weekly KPI review
```

### 5.2 Agent Scheduler (interval-based)

```json
[
  {"name":"trend-refresh-4h","interval_seconds":14400,"path":"/aitoearn/stage/trend","body":{"category":"fashion","limit":10}},
  {"name":"engage-cycle-6h","interval_seconds":21600,"path":"/aitoearn/stage/engage","body":{"platform":"tiktok"}},
  {"name":"monetize-daily","interval_seconds":86400,"path":"/aitoearn/stage/monetize","body":{"creator_id":1}}
]
```

### 5.3 Telegram Monitoring

Daily status check via Telegram bot:
```
/status                           → Pipeline health
/monetization kpi                 → Revenue dashboard
/weekly_recap                     → Weekly earnings summary
```

---

## Revenue Projection

| Phase | Month | CPS (25%) | Fixed Price | CPE | Total/Month |
|-------|-------|-----------|-------------|-----|-------------|
| 1 | CPS only (0 followers) | $50-200 | $0 | $0 | **$50-200** |
| 2 | CPS + Engagement | $100-400 | $0 | $10-50 | **$110-450** |
| 3 | Hit 1k, unlock fixed price | $200-500 | $90-200 | $30-100 | **$320-800** |
| 4 | All revenue streams | $300-800 | $150-300 | $100-300 | **$550-1,400** |
| 6 | Scaled (5+ accounts) | $1,000-3,000 | $300-500 | $300-800 | **$1,600-4,300** |

Key assumptions:
- CPS conversion: 1-3 sales per 100 video views
- Growth to 1k followers in 8-12 weeks with consistent posting + engagement
- Jimeng CPE is the wildcard — one viral video changes everything

---

## What's Already Automated vs. Manual

| Step | Automated? | Tool |
|------|-----------|------|
| Find trending topics | ✅ Yes | `fetch_*_trends.py` + Mastra trendDetector |
| Source/download content | ✅ Yes | `arbitrage_worker.py` + `source_youtube_assets.py` |
| Generate AI videos | ✅ Yes | `generate_video.py` + `finance_video_ai.py` |
| Write viral captions | ✅ Yes | Mastra captionGenerator + hashtagSelector |
| Publish to TikTok | ✅ Yes | `upload_tiktok.py` (Playwright + curl_cffi) |
| Publish to YouTube Shorts | ✅ Yes | `upload_youtube.py` |
| Publish to Instagram | ✅ Yes | `upload_instagram.py` |
| Publish to 40+ platforms | ✅ Yes | `omnichannel_distributor.py` |
| Auto-engage (like/comment/follow) | ✅ Yes | `engage/engine.py` |
| Shadow ban detection | ✅ Yes | `detect_shadow_ban.py` + Mastra |
| KPI tracking | ✅ Yes | `monetization_ops.py` |
| Weekly earnings recap | ✅ Yes | `earnings_proof_ingest.py` |
| Submit proof to AiToEarn | ❌ Manual | AiToEarn website |
| Accept new tasks | ❌ Manual | AiToEarn marketplace |
| Withdraw earnings | ❌ Manual | AiToEarn dashboard |

---

## Immediate Next Actions (Today)

1. **Register on AiToEarn** and get API key
2. **Add API key to `.env`**: `AITOEARN_API_KEY=...`
3. **Seed the database** with CPS tasks (SQL above)
4. **Verify pipeline works**: `docker compose up -d` then `curl http://localhost:18080/health`
5. **Run first trend detection**: `curl -X POST http://localhost:18080/aitoearn/stage/trend -H "Content-Type: application/json" -d '{"category":"fashion","limit":10}'`
6. **Create first product video**: `curl -X POST http://localhost:18080/aitoearn/stage/create -H "Content-Type: application/json" -d '{"limit":3}'`
7. **Publish**: `curl -X POST http://localhost:18080/aitoearn/stage/publish -H "Content-Type: application/json" -d '{}'`
8. **Submit first proof on AiToEarn** with your affiliate link

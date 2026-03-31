# Quick Reference - Manga Automation Improvements

## 🚀 Quick Start

```bash
# Start services
docker compose up -d

# Check health
curl http://localhost:3001/health

# View logs
docker compose logs -f manga-agents
```

## 📊 Database Tables

| Table | Purpose |
|-------|---------|
| `chapter_posting_queue` | Queue for systematic chapter posting |
| `hashtags` | Strategic hashtag library (27 tags) |
| `caption_templates` | Viral caption formulas (15 templates) |
| `video_templates` | Video style configurations (5 templates) |
| `video_performance` | Performance tracking metrics |

## 🔌 API Endpoints

### Queue Management
```bash
# Populate queue for a manga
POST /pipeline/populate-queue
Body: {"manga_id": 1}

# Get next chapter to post
GET /queue/next

# Update queue status
POST /queue/update-status
Body: {"queueId": 1, "status": "posted", "videoId": 123}
```

### Manual Chapter Selection
```bash
# Queue single chapter
POST /webhook/queue-chapter
Body: {"manga_id": 1, "chapter_number": "42", "priority": 100}

# Queue chapter range
POST /webhook/queue-chapter
Body: {"manga_id": 1, "start_chapter": "1", "end_chapter": "50"}
```

### Video Generation
```bash
# Render video from queue
POST /pipeline/render-video
Body: {"queueId": 1, "randomTemplate": true}

# Render with specific template
POST /pipeline/render-video
Body: {"queueId": 1, "templateId": 2}
```

### Caption & Hashtags
```bash
# Generate caption
POST /captions/generate
Body: {
  "videoId": 1,
  "mangaTitle": "One Piece",
  "chapterNumber": "1000",
  "genre": "action"
}

# Select hashtags
GET /hashtags/select?mangaTitle=One%20Piece&genre=action
```

## 📝 Caption Formulas

| Formula Type | Example | Emojis |
|--------------|---------|--------|
| `emotional_hook` | "This scene from {manga} broke me" | 💔😭😢 |
| `question` | "Who's your favorite character in {manga}?" | 🤔❤️👇 |
| `relatable` | "POV: You just finished {manga} chapter {chapter}" | 😱🤯😭 |
| `recommendation` | "You NEED to read {manga}" | 🔥📚💯 |
| `statement_emoji` | "{manga} chapter {chapter} is insane" | 🔥💯😱 |

## 🏷️ Hashtag Tiers

| Tier | Type | Count | Examples |
|------|------|-------|----------|
| 1 | Mega | 3 | #fyp, #foryou, #foryoupage |
| 2 | Core | 4 | #manga, #anime, #animetiktok |
| 3 | Niche | 10 | #shonen, #shoujo, #isekai |
| 4 | Specific | 10 | #onepiece, #naruto, #jujutsukaisen |

**Selection Rule:** 1 mega + 2-3 core + 1-2 niche = 3-5 total

## 🎬 Video Templates

| Template | Type | Duration/Panel | Transition | Effects |
|----------|------|----------------|------------|---------|
| Emotional Scene | emotional_scene | 5s | crossfade | Zoom 1.15x, desaturated |
| Character Edit | character_edit | 3s | slide | Zoom 1.3x, vignette |
| Manga Recommendation | recommendation | 4s | zoom | Zoom 1.2x |
| Panel Appreciation | panel_appreciation | 8s | zoom | Zoom 1.4x |
| Fast Paced Action | character_edit | 2s | wipe | Zoom 1.25x, motion blur |

## 🔄 Queue Status Flow

```
pending → processing → posted
                    ↘ failed
```

## 📈 Priority System

| Priority | Use Case | Example |
|----------|----------|---------|
| 0 | Automatic queue | Trend detection workflow |
| 100 | Manual selection | User-requested chapter |
| 150+ | High priority | Trending/viral content |

**Ordering:** Higher priority first, then oldest chapter_number

## 🗄️ Useful SQL Queries

### View Queue Status
```sql
SELECT status, COUNT(*) 
FROM chapter_posting_queue 
GROUP BY status;
```

### Next Chapters to Post
```sql
SELECT m.title, cpq.chapter_number, cpq.priority
FROM chapter_posting_queue cpq
JOIN manga m ON cpq.manga_id = m.id
WHERE cpq.status = 'pending'
ORDER BY cpq.priority DESC, cpq.chapter_number ASC
LIMIT 10;
```

### Videos Posted Today
```sql
SELECT COUNT(*) as videos_today
FROM chapter_posting_queue
WHERE posted_at >= CURRENT_DATE
  AND status = 'posted';
```

### Success Rate (Last 24h)
```sql
SELECT 
    status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM chapter_posting_queue
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY status;
```

## 🎯 Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| Videos/day | 90+ | Monitor |
| Queue processing rate | 4-6 videos/hour | Monitor |
| Video generation time | <15 min | Monitor |
| Success rate | >90% | Monitor |
| API response time (p95) | <500ms | Monitor |

## 🔧 Common Commands

### Docker
```bash
# Restart services
docker compose restart manga-agents

# View logs
docker compose logs -f manga-agents

# Execute SQL
docker compose exec postgres psql -U manga_user -d manga_automation

# Apply migration
docker compose exec -T postgres psql -U manga_user -d manga_automation \
  -f /docker-entrypoint-initdb.d/migrations/003_queue_system_and_templates.sql
```

### Testing
```bash
# Health check
curl http://localhost:3001/health

# Populate queue
curl -X POST http://localhost:3001/pipeline/populate-queue \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1}'

# Generate caption
curl -X POST http://localhost:3001/captions/generate \
  -H "Content-Type: application/json" \
  -d '{"videoId": 1, "mangaTitle": "Test", "chapterNumber": "1", "genre": "action"}'
```

## 📚 Documentation

- `DEPLOYMENT_GUIDE.md` - Full deployment instructions
- `TECHNICAL_GUIDE.md` - Architecture and API docs
- `DOCKER_TEST_RESULTS.md` - Test results and validation
- `README.md` - Overview and quick start
- `.kiro/specs/manga-automation-improvements/` - Complete spec

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| Service won't start | Check logs: `docker compose logs manga-agents` |
| Migration failed | Re-run migration script |
| API not responding | Restart: `docker compose restart manga-agents` |
| Queue not processing | Check N8N workflow is active |
| Videos not generating | Check Remotion renderer logs |

## 🔐 Environment Variables

Required in `.env`:
- `DB_PASSWORD` - PostgreSQL password
- `ANTHROPIC_API_KEY` - Claude API key
- `N8N_PASSWORD` - N8N admin password
- `TIKTOK_EMAIL` - TikTok account email
- `TIKTOK_PASSWORD` - TikTok account password

## 📞 Support

For issues or questions:
1. Check logs: `docker compose logs -f`
2. Review documentation in this directory
3. Check spec files in `.kiro/specs/manga-automation-improvements/`

---

**Last Updated:** March 30, 2026  
**Version:** 1.0.0 (Queue System & Templates)

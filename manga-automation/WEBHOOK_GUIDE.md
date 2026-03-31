# Webhook Workflow Guide

## ✅ Status: WORKING

Both single chapter and chapter range queueing are fully functional. See [WORKFLOW_TEST_RESULTS.md](./WORKFLOW_TEST_RESULTS.md) for detailed test results.

## Overview

The webhook endpoint allows you to manually queue specific manga chapters for video generation. This is useful for:
- Responding to trending topics
- User requests for specific chapters
- Testing the video generation pipeline
- Prioritizing specific content

## Endpoint

```
POST http://localhost:3001/webhook/queue-chapter
```

## Usage

### 1. Queue a Single Chapter

**PowerShell:**
```powershell
$body = @{
    manga_id = 11
    chapter_number = "79.1"
    priority = 100
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:3001/webhook/queue-chapter" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

**curl:**
```bash
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{
    "manga_id": 11,
    "chapter_number": "79.1",
    "priority": 100
  }'
```

**Response:**
```json
{
  "success": true,
  "queue_id": 1,
  "queue_position": 1
}
```

### 2. Queue a Chapter Range

**PowerShell:**
```powershell
$body = @{
    manga_id = 11
    start_chapter = "1"
    end_chapter = "10"
    priority = 150
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:3001/webhook/queue-chapter" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

**curl:**
```bash
curl -X POST http://localhost:3001/webhook/queue-chapter \
  -H "Content-Type: application/json" \
  -d '{
    "manga_id": 11,
    "start_chapter": "1",
    "end_chapter": "10",
    "priority": 150
  }'
```

**Response:**
```json
{
  "success": true,
  "queued_count": 10,
  "queue_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
  "queue_position": 1
}
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `manga_id` | number | Yes | The ID of the manga |
| `chapter_number` | string | Conditional | Chapter number (required if not using range) |
| `start_chapter` | string | Conditional | Start of chapter range |
| `end_chapter` | string | Conditional | End of chapter range |
| `priority` | number | No | Priority level (default: 100, higher = posted first) |

## Priority System

| Priority | Use Case | Description |
|----------|----------|-------------|
| 0 | Automatic | Default for trend detection workflow |
| 100 | Manual | Default for webhook requests |
| 150+ | High Priority | Trending or urgent content |
| 200+ | Critical | Time-sensitive content |

**Ordering:** Higher priority posts first, then oldest chapter_number

## Finding Manga and Chapter IDs

### List Available Manga

**PowerShell:**
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "SELECT id, title FROM manga ORDER BY id LIMIT 20;"
```

**Output:**
```
 id |                title                 
----+--------------------------------------
 11 | Kage no Jitsuryokusha ni Naritakute!
 20 | Na Honjaman Level-Up
 21 | Chainsaw Man
```

### List Chapters for a Manga

**PowerShell:**
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "SELECT id, chapter_number FROM manga_chapters WHERE manga_id = 11 ORDER BY chapter_number;"
```

**Output:**
```
 id | chapter_number 
----+----------------
  1 | 79.1
```

## Complete Example Workflow

### Step 1: Find Manga ID
```powershell
# List all manga
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "SELECT id, title FROM manga WHERE is_active = true ORDER BY trending_score DESC LIMIT 10;"
```

### Step 2: Check Available Chapters
```powershell
# Replace 11 with your manga_id
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "SELECT id, chapter_number FROM manga_chapters WHERE manga_id = 11 ORDER BY chapter_number;"
```

### Step 3: Queue the Chapter
```powershell
$body = @{
    manga_id = 11
    chapter_number = "79.1"
    priority = 100
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:3001/webhook/queue-chapter" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body

Write-Host "Queued at position: $($response.queue_position)"
```

### Step 4: Verify Queue Entry
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "SELECT id, manga_id, chapter_number, priority, status FROM chapter_posting_queue ORDER BY priority DESC, chapter_number ASC LIMIT 10;"
```

### Step 5: Trigger Video Generation (Optional)
```powershell
# Get the queue ID from step 3
$queueId = $response.queue_id

$renderBody = @{
    queueId = $queueId
    randomTemplate = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:3001/pipeline/render-video" `
    -Method POST `
    -ContentType "application/json" `
    -Body $renderBody
```

## Error Handling

### Common Errors

**Error: "manga_id required"**
```json
{
  "error": "manga_id required"
}
```
**Solution:** Include `manga_id` in the request body.

**Error: "Either chapter_number or (start_chapter and end_chapter) required"**
```json
{
  "error": "Either chapter_number or (start_chapter and end_chapter) required"
}
```
**Solution:** Provide either `chapter_number` OR both `start_chapter` and `end_chapter`.

**Error: "Chapter X not found for manga Y"**
```json
{
  "success": false,
  "error": "Chapter 79.1 not found for manga 11"
}
```
**Solution:** The chapter doesn't exist in the database. Check available chapters using the SQL query above.

**Error: "Manga X not found"**
```json
{
  "success": false,
  "error": "Manga 11 not found"
}
```
**Solution:** The manga doesn't exist. Check available manga using the SQL query above.

## Using with N8N Workflow

### Step 1: Import Workflow

1. Open N8N at http://localhost:5679
2. Go to **Workflows** → **Import from File**
3. Select `n8n-workflows/05_manual_chapter_selection.json`
4. Click **Import**

### Step 2: Configure Webhook

1. Open the imported workflow
2. Click on the **Webhook** node
3. Note the webhook URL (e.g., `http://localhost:5679/webhook/queue-chapter`)
4. Configure authentication if needed

### Step 3: Activate Workflow

1. Click the **Active** toggle in the top right
2. The workflow is now listening for requests

### Step 4: Test the Webhook

```powershell
# Call N8N webhook instead of direct API
$body = @{
    manga_id = 11
    chapter_number = "79.1"
    priority = 100
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:5679/webhook/queue-chapter" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

## Monitoring

### Check Queue Status
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "
SELECT 
    cpq.id,
    m.title,
    cpq.chapter_number,
    cpq.priority,
    cpq.status,
    cpq.created_at
FROM chapter_posting_queue cpq
JOIN manga m ON cpq.manga_id = m.id
WHERE cpq.status = 'pending'
ORDER BY cpq.priority DESC, cpq.chapter_number ASC
LIMIT 10;
"
```

### Check Queue Statistics
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "
SELECT 
    status,
    COUNT(*) as count,
    MIN(priority) as min_priority,
    MAX(priority) as max_priority
FROM chapter_posting_queue
GROUP BY status;
"
```

### View Recent Activity
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "
SELECT 
    cpq.id,
    m.title,
    cpq.chapter_number,
    cpq.status,
    cpq.posted_at
FROM chapter_posting_queue cpq
JOIN manga m ON cpq.manga_id = m.id
WHERE cpq.posted_at > NOW() - INTERVAL '24 hours'
ORDER BY cpq.posted_at DESC
LIMIT 20;
"
```

## Tips

1. **Use Higher Priority for Trending Content**
   - Set priority to 150+ for trending chapters
   - This ensures they're posted before automatic queue entries

2. **Batch Queue Multiple Chapters**
   - Use chapter ranges to queue multiple chapters at once
   - More efficient than individual requests

3. **Monitor Queue Depth**
   - Check queue status regularly
   - Adjust priority based on queue depth

4. **Test with Low-Priority First**
   - Use priority 50 for testing
   - This won't interfere with production queue

5. **Verify Before Queuing**
   - Always check if chapter exists first
   - Prevents unnecessary error responses

## Troubleshooting

### Webhook Not Responding

**Check service status:**
```powershell
docker compose ps manga-agents
```

**Check logs:**
```powershell
docker compose logs --tail=50 manga-agents
```

**Test health endpoint:**
```powershell
Invoke-WebRequest -Uri "http://localhost:3001/health"
```

### Chapter Not Found

**Verify chapter exists:**
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "SELECT * FROM manga_chapters WHERE manga_id = 11 AND chapter_number = '79.1';"
```

**Check if already queued:**
```powershell
docker compose exec -T postgres psql -U manga_user -d manga_automation -c "SELECT * FROM chapter_posting_queue WHERE manga_id = 11 AND chapter_number = '79.1';"
```

### Queue Not Processing

**Check N8N workflow status:**
1. Open N8N at http://localhost:5679
2. Check if workflow 02 (video generation) is active
3. Check execution history for errors

**Manually trigger video generation:**
```powershell
$body = @{
    queueId = 1
    randomTemplate = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:3001/pipeline/render-video" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

## Related Documentation

- `DEPLOYMENT_GUIDE.md` - Full deployment instructions
- `QUICK_REFERENCE.md` - Quick reference for all features
- `TECHNICAL_GUIDE.md` - Technical architecture details
- `README.md` - Overview and quick start

---

**Last Updated:** March 31, 2026  
**Version:** 1.0.0

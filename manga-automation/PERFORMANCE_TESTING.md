# Performance Testing Guide

## Overview

This document provides comprehensive guidance for testing the manga automation system's performance capabilities. The system is designed to generate and post 90+ videos per day (630+ per week), requiring robust performance testing to validate scalability, identify bottlenecks, and ensure reliable operation under load.

**Performance Requirements:**
- Generate minimum 90 videos per day
- Support concurrent video generation (5 simultaneous renders)
- Maintain efficient queue processing rate
- Handle large chapter backlogs (1000+ chapters)
- Ensure system stability under sustained load

## Table of Contents

1. [Test Environment Setup](#test-environment-setup)
2. [Daily Throughput Testing (90+ Videos/Day)](#daily-throughput-testing-90-videosday)
3. [Concurrent Video Generation Testing](#concurrent-video-generation-testing)
4. [Queue Processing Rate Measurement](#queue-processing-rate-measurement)
5. [Bottleneck Identification](#bottleneck-identification)
6. [Optimization Recommendations](#optimization-recommendations)
7. [Monitoring and Metrics](#monitoring-and-metrics)

---

## Test Environment Setup

### Prerequisites

1. **Database**: PostgreSQL with test data populated
2. **Services**: All services running (n8n, backend API, Remotion renderer)
3. **Storage**: Sufficient disk space for video output (minimum 50GB free)
4. **Resources**: Adequate CPU and memory (recommended: 8+ cores, 16GB+ RAM)

### Test Data Preparation

```bash
# 1. Populate test database with manga and chapters
cd manga-automation/mastra-agents
npm run test:setup-performance-data

# 2. Verify test data
psql -U postgres -d manga_automation -c "SELECT COUNT(*) FROM manga;"
psql -U postgres -d manga_automation -c "SELECT COUNT(*) FROM manga_chapters;"
psql -U postgres -d manga_automation -c "SELECT COUNT(*) FROM chapter_posting_queue WHERE status='pending';"
```

### Environment Configuration

Create a performance testing configuration file:

```bash
# manga-automation/.env.performance
NODE_ENV=performance
LOG_LEVEL=info
VIDEO_CONCURRENT_LIMIT=5
QUEUE_BATCH_SIZE=10
REMOTION_CONCURRENCY=5
DATABASE_POOL_SIZE=20
```

---

## Daily Throughput Testing (90+ Videos/Day)

### Objective

Validate the system can generate and process 90+ videos within a 24-hour period.

### Test Methodology

#### 1. Full 24-Hour Test

**Setup:**
```bash
# Populate queue with 100 chapters
curl -X POST http://localhost:3000/pipeline/populate-queue \
  -H "Content-Type: application/json" \
  -d '{"manga_id": 1}'

# Verify queue size
psql -U postgres -d manga_automation -c \
  "SELECT COUNT(*) FROM chapter_posting_queue WHERE status='pending';"
```

**Execution:**
```bash
# Start performance monitoring
cd manga-automation
./scripts-bash/start-performance-monitor.sh

# Start video generation workflow (continuous mode)
# This will process queue entries continuously for 24 hours
curl -X POST http://localhost:5678/webhook/start-continuous-generation \
  -H "Content-Type: application/json" \
  -d '{"duration_hours": 24, "target_videos": 90}'

# Monitor progress
watch -n 60 'psql -U postgres -d manga_automation -c \
  "SELECT status, COUNT(*) FROM chapter_posting_queue GROUP BY status;"'
```

**Success Criteria:**
- ✅ Minimum 90 videos generated within 24 hours
- ✅ Average generation rate: ≥3.75 videos/hour
- ✅ Queue processing without stalls or crashes
- ✅ All generated videos meet format requirements (1080x1920, H.264, AAC, 60+ seconds)

#### 2. Accelerated Test (Scaled Time)

For faster validation, run an accelerated test over 4 hours targeting 15 videos (scaled from 90/24h):

```bash
# Target: 15 videos in 4 hours (3.75 videos/hour)
curl -X POST http://localhost:5678/webhook/start-continuous-generation \
  -H "Content-Type: application/json" \
  -d '{"duration_hours": 4, "target_videos": 15}'
```

### Metrics to Collect

```sql
-- Video generation rate over time
SELECT 
  DATE_TRUNC('hour', posted_at) as hour,
  COUNT(*) as videos_generated,
  AVG(EXTRACT(EPOCH FROM (posted_at - created_at))) as avg_generation_time_seconds
FROM chapter_posting_queue
WHERE status = 'posted'
  AND posted_at >= NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour;

-- Success rate
SELECT 
  status,
  COUNT(*) as count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM chapter_posting_queue
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY status;
```

### Expected Results

| Metric | Target | Acceptable Range |
|--------|--------|------------------|
| Videos/Day | 90 | 90-120 |
| Videos/Hour | 3.75 | 3.5-5.0 |
| Success Rate | 95% | 90-100% |
| Avg Generation Time | 15 min | 10-20 min |

---

## Concurrent Video Generation Testing

### Objective

Verify the system can handle 5 simultaneous video generation processes without degradation or failures.

### Test Methodology

#### 1. Concurrent Render Test

**Setup:**
```bash
# Ensure queue has at least 10 pending chapters
psql -U postgres -d manga_automation -c \
  "SELECT COUNT(*) FROM chapter_posting_queue WHERE status='pending';"
```

**Execution Script:**
```bash
#!/bin/bash
# concurrent-render-test.sh

# Start 5 concurrent video generation requests
for i in {1..5}; do
  (
    echo "Starting render $i at $(date)"
    curl -X POST http://localhost:3000/pipeline/render-video \
      -H "Content-Type: application/json" \
      -d '{"auto_select": true}' \
      > /tmp/render_$i.log 2>&1
    echo "Completed render $i at $(date)"
  ) &
done

# Wait for all background jobs to complete
wait
echo "All concurrent renders completed"
```

**Run Test:**
```bash
chmod +x concurrent-render-test.sh
time ./concurrent-render-test.sh
```

**Success Criteria:**
- ✅ All 5 renders complete successfully
- ✅ No database deadlocks or connection errors
- ✅ No file system conflicts
- ✅ Total time ≤ 1.5x single render time (acceptable overhead)
- ✅ System remains responsive during concurrent operations

#### 2. Sustained Concurrent Load Test

Test sustained concurrent generation over 2 hours:

```bash
#!/bin/bash
# sustained-concurrent-test.sh

END_TIME=$(($(date +%s) + 7200))  # 2 hours from now

while [ $(date +%s) -lt $END_TIME ]; do
  # Maintain 5 concurrent renders
  ACTIVE=$(pgrep -f "render-video" | wc -l)
  
  while [ $ACTIVE -lt 5 ]; do
    curl -X POST http://localhost:3000/pipeline/render-video \
      -H "Content-Type: application/json" \
      -d '{"auto_select": true}' &
    
    ACTIVE=$((ACTIVE + 1))
    sleep 2
  done
  
  sleep 30  # Check every 30 seconds
done
```

### Metrics to Collect

```sql
-- Concurrent generation performance
SELECT 
  DATE_TRUNC('minute', created_at) as minute,
  COUNT(*) as concurrent_renders,
  AVG(EXTRACT(EPOCH FROM (posted_at - created_at))) as avg_time_seconds,
  MAX(EXTRACT(EPOCH FROM (posted_at - created_at))) as max_time_seconds
FROM chapter_posting_queue
WHERE status = 'posted'
  AND created_at >= NOW() - INTERVAL '2 hours'
GROUP BY minute
ORDER BY minute;

-- Check for errors during concurrent operations
SELECT 
  status,
  COUNT(*) as count
FROM chapter_posting_queue
WHERE created_at >= NOW() - INTERVAL '2 hours'
GROUP BY status;
```

### Expected Results

| Metric | Target | Acceptable Range |
|--------|--------|------------------|
| Concurrent Renders | 5 | 5 |
| Success Rate | 95% | 90-100% |
| Avg Time Overhead | <30% | 0-50% |
| Database Errors | 0 | 0-2 |
| System CPU Usage | <80% | 50-90% |

---

## Queue Processing Rate Measurement

### Objective

Measure the rate at which the system processes chapters from the queue and identify processing capacity.

### Test Methodology

#### 1. Queue Throughput Test

**Setup:**
```bash
# Populate queue with 200 chapters
for manga_id in {1..10}; do
  curl -X POST http://localhost:3000/pipeline/populate-queue \
    -H "Content-Type: application/json" \
    -d "{\"manga_id\": $manga_id}"
done

# Verify queue size
psql -U postgres -d manga_automation -c \
  "SELECT COUNT(*) FROM chapter_posting_queue WHERE status='pending';"
```

**Execution:**
```bash
# Start queue processor with metrics collection
cd manga-automation
node mastra-agents/src/scripts/process-queue-with-metrics.js \
  --duration 3600 \
  --concurrency 5 \
  --metrics-output /tmp/queue-metrics.json
```

**Metrics Collection Script:**
```javascript
// mastra-agents/src/scripts/process-queue-with-metrics.js
const startTime = Date.now();
const metrics = {
  processed: 0,
  failed: 0,
  avgTimePerVideo: 0,
  timestamps: []
};

setInterval(() => {
  const elapsed = (Date.now() - startTime) / 1000;
  const rate = metrics.processed / (elapsed / 3600);
  
  console.log(`Processed: ${metrics.processed}, Rate: ${rate.toFixed(2)} videos/hour`);
  
  metrics.timestamps.push({
    time: elapsed,
    processed: metrics.processed,
    rate: rate
  });
}, 60000);  // Log every minute
```

### Metrics to Collect

```sql
-- Processing rate over time
WITH time_buckets AS (
  SELECT 
    generate_series(
      DATE_TRUNC('hour', MIN(created_at)),
      DATE_TRUNC('hour', MAX(posted_at)),
      '1 hour'::interval
    ) as bucket
  FROM chapter_posting_queue
  WHERE created_at >= NOW() - INTERVAL '24 hours'
)
SELECT 
  tb.bucket,
  COUNT(cpq.id) as videos_processed,
  COUNT(cpq.id) / 1.0 as videos_per_hour,
  AVG(EXTRACT(EPOCH FROM (cpq.posted_at - cpq.created_at))) as avg_processing_time
FROM time_buckets tb
LEFT JOIN chapter_posting_queue cpq 
  ON DATE_TRUNC('hour', cpq.posted_at) = tb.bucket
  AND cpq.status = 'posted'
GROUP BY tb.bucket
ORDER BY tb.bucket;

-- Queue depth over time
SELECT 
  DATE_TRUNC('hour', NOW()) as time,
  COUNT(*) FILTER (WHERE status = 'pending') as pending,
  COUNT(*) FILTER (WHERE status = 'processing') as processing,
  COUNT(*) FILTER (WHERE status = 'posted') as posted,
  COUNT(*) FILTER (WHERE status = 'failed') as failed
FROM chapter_posting_queue
WHERE created_at >= NOW() - INTERVAL '24 hours';
```

### Expected Results

| Metric | Target | Acceptable Range |
|--------|--------|------------------|
| Processing Rate | 4-5 videos/hour | 3.5-6 videos/hour |
| Queue Depletion Time (100 items) | 20-25 hours | 17-30 hours |
| Failed Rate | <5% | 0-10% |
| Avg Processing Time | 12-15 min | 10-20 min |

---

## Bottleneck Identification

### System Resource Monitoring

#### 1. CPU and Memory Profiling

```bash
# Monitor system resources during video generation
#!/bin/bash
# monitor-resources.sh

while true; do
  echo "=== $(date) ==="
  
  # CPU usage by process
  ps aux --sort=-%cpu | head -10
  
  # Memory usage
  free -h
  
  # Disk I/O
  iostat -x 1 1
  
  # Network
  netstat -s | grep -i "segments\|packets"
  
  echo ""
  sleep 60
done > /tmp/resource-monitor.log
```

#### 2. Database Performance Analysis

```sql
-- Slow queries
SELECT 
  query,
  calls,
  total_time,
  mean_time,
  max_time
FROM pg_stat_statements
WHERE mean_time > 100  -- queries taking >100ms
ORDER BY mean_time DESC
LIMIT 20;

-- Table sizes and bloat
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Index usage
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;

-- Connection pool status
SELECT 
  count(*) as total_connections,
  count(*) FILTER (WHERE state = 'active') as active,
  count(*) FILTER (WHERE state = 'idle') as idle,
  count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
FROM pg_stat_activity;
```

#### 3. Video Rendering Performance

```bash
# Profile Remotion rendering
cd manga-automation/remotion-renderer

# Enable detailed timing logs
REMOTION_TIMING=1 npm run render -- \
  --props='{"chapterId": 1}' \
  --log=verbose \
  2>&1 | tee /tmp/remotion-profile.log

# Analyze rendering stages
grep "took" /tmp/remotion-profile.log | sort -k3 -n
```

### Common Bottlenecks

| Component | Symptom | Diagnostic Query/Command |
|-----------|---------|--------------------------|
| **Database** | Slow queue queries | `EXPLAIN ANALYZE SELECT * FROM chapter_posting_queue WHERE status='pending' ORDER BY priority DESC, chapter_number ASC LIMIT 1;` |
| **Disk I/O** | Slow video writes | `iostat -x 1 10` |
| **CPU** | High CPU during render | `top -H -p $(pgrep -f remotion)` |
| **Memory** | OOM errors | `dmesg \| grep -i "out of memory"` |
| **Network** | Slow panel downloads | `curl -w "@curl-format.txt" -o /dev/null -s <panel_url>` |
| **Remotion** | Slow frame rendering | Check `remotion-profile.log` for frame times |

### Bottleneck Identification Checklist

Run through this checklist during performance testing:

```bash
# 1. Check database query performance
psql -U postgres -d manga_automation -c "
  SELECT query, mean_time, calls 
  FROM pg_stat_statements 
  WHERE mean_time > 50 
  ORDER BY mean_time DESC 
  LIMIT 10;"

# 2. Check disk I/O wait
iostat -x 1 5 | grep -E "Device|sda|nvme"

# 3. Check CPU usage by process
ps aux --sort=-%cpu | head -10

# 4. Check memory usage
free -h && cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable"

# 5. Check network latency to MangaDex
ping -c 10 api.mangadex.org
curl -w "Time: %{time_total}s\n" -o /dev/null -s https://api.mangadex.org/manga

# 6. Check video file write speed
dd if=/dev/zero of=/tmp/test.mp4 bs=1M count=100 conv=fdatasync
rm /tmp/test.mp4

# 7. Check database connection pool
psql -U postgres -d manga_automation -c "
  SELECT count(*), state 
  FROM pg_stat_activity 
  GROUP BY state;"
```

---

## Optimization Recommendations

### Database Optimizations

#### 1. Index Optimization

```sql
-- Ensure critical indexes exist
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_queue_status_priority 
  ON chapter_posting_queue(status, priority DESC, chapter_number ASC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_queue_processing 
  ON chapter_posting_queue(status, created_at) 
  WHERE status = 'processing';

-- Analyze tables for query planner
ANALYZE chapter_posting_queue;
ANALYZE manga_chapters;
ANALYZE videos;
```

#### 2. Connection Pooling

```javascript
// mastra-agents/src/db/pool.ts
import { Pool } from 'pg';

export const pool = new Pool({
  host: process.env.DB_HOST,
  port: parseInt(process.env.DB_PORT || '5432'),
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  max: 20,  // Maximum pool size
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});
```

#### 3. Query Optimization

```sql
-- Use prepared statements for frequent queries
PREPARE get_next_chapter AS
  SELECT * FROM chapter_posting_queue
  WHERE status = 'pending'
  ORDER BY priority DESC, chapter_number ASC
  LIMIT 1
  FOR UPDATE SKIP LOCKED;

-- Execute with:
EXECUTE get_next_chapter;
```

### Video Generation Optimizations

#### 1. Remotion Concurrency Settings

```javascript
// remotion-renderer/src/config.ts
export const REMOTION_CONFIG = {
  concurrency: 5,  // Parallel frame rendering
  frameRange: null,  // Render all frames
  everyNthFrame: 1,
  numberOfGifLoops: null,
  delayRenderTimeoutInMilliseconds: 30000,
  chromiumOptions: {
    headless: true,
    gl: 'angle',  // Use ANGLE for better performance
  },
};
```

#### 2. Image Optimization

```javascript
// Pre-process panel images before rendering
import sharp from 'sharp';

async function optimizePanel(inputPath: string, outputPath: string) {
  await sharp(inputPath)
    .resize(1080, 1920, { fit: 'inside', withoutEnlargement: true })
    .jpeg({ quality: 85, progressive: true })
    .toFile(outputPath);
}
```

#### 3. Caching Strategy

```javascript
// Cache downloaded panels
import NodeCache from 'node-cache';

const panelCache = new NodeCache({
  stdTTL: 3600,  // 1 hour
  maxKeys: 1000,
  useClones: false,
});

async function getCachedPanel(url: string): Promise<Buffer> {
  const cached = panelCache.get<Buffer>(url);
  if (cached) return cached;
  
  const downloaded = await downloadPanel(url);
  panelCache.set(url, downloaded);
  return downloaded;
}
```

### Queue Processing Optimizations

#### 1. Batch Processing

```javascript
// Process multiple queue entries in parallel
async function processBatch(batchSize: number = 5) {
  const entries = await getNextChapters(batchSize);
  
  await Promise.allSettled(
    entries.map(entry => generateVideo(entry))
  );
}
```

#### 2. Priority Queue Implementation

```javascript
// Use Redis for faster queue operations
import Redis from 'ioredis';

const redis = new Redis(process.env.REDIS_URL);

async function enqueueChapter(chapter: QueueEntry) {
  const score = chapter.priority * 1000000 - chapter.chapter_number;
  await redis.zadd('video_queue', score, JSON.stringify(chapter));
}

async function dequeueChapter(): Promise<QueueEntry | null> {
  const result = await redis.zpopmax('video_queue');
  return result ? JSON.parse(result[0]) : null;
}
```

### System-Level Optimizations

#### 1. Increase File Descriptors

```bash
# /etc/security/limits.conf
* soft nofile 65536
* hard nofile 65536
```

#### 2. Optimize Docker Resources

```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

#### 3. Enable Swap (if needed)

```bash
# Create 8GB swap file
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## Monitoring and Metrics

### Real-Time Dashboard

Create a monitoring dashboard to track performance metrics:

```javascript
// mastra-agents/src/monitoring/metrics.ts
import { Registry, Counter, Histogram, Gauge } from 'prom-client';

const register = new Registry();

export const metrics = {
  videosGenerated: new Counter({
    name: 'videos_generated_total',
    help: 'Total number of videos generated',
    registers: [register],
  }),
  
  videoGenerationDuration: new Histogram({
    name: 'video_generation_duration_seconds',
    help: 'Video generation duration in seconds',
    buckets: [60, 300, 600, 900, 1200, 1800],
    registers: [register],
  }),
  
  queueDepth: new Gauge({
    name: 'queue_depth',
    help: 'Number of pending items in queue',
    registers: [register],
  }),
  
  concurrentRenders: new Gauge({
    name: 'concurrent_renders',
    help: 'Number of concurrent video renders',
    registers: [register],
  }),
};

// Expose metrics endpoint
app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});
```

### Grafana Dashboard Configuration

```json
{
  "dashboard": {
    "title": "Manga Automation Performance",
    "panels": [
      {
        "title": "Videos Generated per Hour",
        "targets": [
          {
            "expr": "rate(videos_generated_total[1h])"
          }
        ]
      },
      {
        "title": "Average Generation Time",
        "targets": [
          {
            "expr": "histogram_quantile(0.5, video_generation_duration_seconds)"
          }
        ]
      },
      {
        "title": "Queue Depth",
        "targets": [
          {
            "expr": "queue_depth"
          }
        ]
      },
      {
        "title": "Concurrent Renders",
        "targets": [
          {
            "expr": "concurrent_renders"
          }
        ]
      }
    ]
  }
}
```

### Alert Configuration

```yaml
# alerts.yml
groups:
  - name: manga_automation
    interval: 1m
    rules:
      - alert: LowVideoGenerationRate
        expr: rate(videos_generated_total[1h]) < 3
        for: 30m
        annotations:
          summary: "Video generation rate below target"
          description: "Only {{ $value }} videos/hour (target: 3.75)"
      
      - alert: HighQueueDepth
        expr: queue_depth > 500
        for: 1h
        annotations:
          summary: "Queue depth is very high"
          description: "{{ $value }} items in queue"
      
      - alert: HighFailureRate
        expr: rate(videos_failed_total[1h]) / rate(videos_generated_total[1h]) > 0.1
        for: 15m
        annotations:
          summary: "Video generation failure rate above 10%"
```

### Performance Testing Report Template

After running performance tests, generate a report:

```markdown
# Performance Test Report

**Date:** YYYY-MM-DD
**Duration:** X hours
**Test Type:** [Daily Throughput / Concurrent / Queue Processing]

## Summary

- **Videos Generated:** X
- **Success Rate:** X%
- **Average Generation Time:** X minutes
- **Peak Concurrent Renders:** X
- **Queue Processing Rate:** X videos/hour

## Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Videos/Day | 90 | X | ✅/❌ |
| Success Rate | 95% | X% | ✅/❌ |
| Avg Gen Time | 15 min | X min | ✅/❌ |
| Concurrent Renders | 5 | X | ✅/❌ |

## Bottlenecks Identified

1. **[Component]**: [Description]
   - Impact: [High/Medium/Low]
   - Recommendation: [Action]

## Optimizations Applied

1. **[Optimization]**: [Description]
   - Result: [Improvement]

## Recommendations

1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]

## Next Steps

- [ ] Action item 1
- [ ] Action item 2
```

---

## Conclusion

This performance testing guide provides comprehensive methodologies for validating the manga automation system's ability to generate 90+ videos per day with concurrent processing capabilities. Regular performance testing ensures the system maintains reliability and efficiency as it scales.

**Key Takeaways:**
- Run daily throughput tests to validate 90+ videos/day capacity
- Test concurrent generation (5 simultaneous) to ensure parallelization works
- Monitor queue processing rate to identify capacity limits
- Use systematic bottleneck identification to find optimization opportunities
- Implement recommended optimizations based on test results
- Maintain continuous monitoring for production performance tracking

For questions or issues, refer to the main [TECHNICAL_GUIDE.md](./TECHNICAL_GUIDE.md) or consult the development team.

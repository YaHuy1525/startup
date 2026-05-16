---
date: 2026-05-12
type: knowledge
tags:
  - knowledge
  - ai-agents
  - crewai
  - vector-db
  - security
  - manga-automation
related-projects:
  - "[[Projects/manga-automation]]"
ai-first: true
---

## For future Claude
Covers the planned agentic upgrade for manga-automation as of 2026-05-12 (from CLAWBOT_AGENT_PLAN.md and ARCHITECTURE_CHANGES.md). Three major upgrades: (1) CrewAI orchestration replacing linear scripts, (2) ChromaDB vector memory for long-term agent intelligence, (3) TikTok security bypass V2 with FFmpeg mutation + TLS fingerprint evasion. CrewAI and ChromaDB are planned; V2 uploader is in isolated testing.

---

# manga-automation — Agentic Upgrade Plans

## Overview

Three major upgrades to transform the system from linear scripts to an autonomous multi-agent workforce:

### 1. CrewAI Orchestration
**Status:** Planned (Phase 3 in CLAWBOT_AGENT_PLAN.md)

Replaces `arbitrage_worker.py` and related linear scripts with a Manager-led CrewAI crew:

```
Manager Agent (LLM Brain — Claude/GPT-4)
├── Scout Agent       → Finds trending content on TikTok
├── Harvester Agent   → Sources raw video from YouTube
├── Operator Agent    → Uploads to TikTok (with stealth)
└── Analyst Agent     → Reports performance back to dashboard
```

**Key difference from scripts:**
- Scripts: Linear step 1→2→3, crash on error
- CrewAI: Agents decide their own next step, self-correct on failure
- If Operator hits shadow-ban → Manager autonomously quarantines account → reassigns to spare

**Files:** `scripts/crew/agents.py`, `scripts/crew/pipeline_crew.py`, `scripts/crew/tools.py`

**Process type:** `Process.hierarchical` (Manager-led, not sequential)

### 2. ChromaDB Vector Memory
**Status:** Planned (Phase 2 in CLAWBOT_AGENT_PLAN.md)

Persistent vector database so agents remember what worked across runs:

**Collections:**
| Collection | Purpose |
|---|---|
| `trend_memory` | Viral topics + view counts + dates + performance scores |
| `account_health` | Per-account upload history + shadow-ban flags + view averages |
| `content_fingerprints` | Video hashes to prevent re-uploads |

**Feedback loop example:**
```
Trend Agent → ChromaDB: "JJK edits: 3-day avg views = 1,200 (declining -40%)"
            → ChromaDB: "One Piece Ch 1111: trending, 0 uploads from us"
            → Recommendation: "Shift to One Piece Ch 1111"
            → Manager approves → Harvester pivots search queries
```

**Service:** `chromadb/chroma:latest` on port 8001 (to be added to docker-compose.yml)
**File:** `scripts/memory_manager.py`

### 3. TikTok Security Bypass V2
**Status:** In testing (files created, 72h validation before production merge)

**Problem:** TikTok detects re-uploaded content via perceptual hash + Python TLS fingerprint.

**Two-layer defense:**

**Layer 1 — FFmpeg Hash Mutation:**
```
Original Video
    ↓
[1] Hue shift: ±2° (imperceptible, breaks hash)
[2] Crop 1px each edge (changes frame dimensions)
[3] Strip all metadata (removes software fingerprints)
[4] Re-encode with randomized CRF (18-22)
    ↓
Mutated Video → Unique hash → TikTok sees as original
```

**Layer 2 — TLS Fingerprint Bypass:**
- `curl_cffi` impersonates Chrome 120 TLS fingerprint
- Python's `requests` library has recognizable TLS signature
- `curl_cffi` mimics real browser at network level

**Isolation strategy:**
```
TiktokAutoUploader/tiktok_uploader/
├── tiktok.py      ← PRODUCTION (untouched)
└── tiktok_v2.py   ← NEW: mutation + TLS bypass (testing)
```

**Merge criteria:** ≥90% upload success rate over 72h, zero shadow-bans.

**Test commands:**
```bash
python test_v2_upload.py --test mutation --video path/to/video.mp4
python test_v2_upload.py --test tls
python test_v2_upload.py --test upload --account <test> --video path/to/video.mp4
```

---

## Implementation Phases (from CLAWBOT_AGENT_PLAN.md)

| Phase | Component | Status |
|---|---|---|
| 1 | Security Isolation — V2 uploader with FFmpeg + TLS bypass | In testing |
| 2 | Vector Memory — ChromaDB with 3 collections | Planned |
| 3 | CrewAI Orchestration — Manager + 4 specialist agents | Planned |
| 4 | Dashboard Integration — Agent Control Center UI | Planned |
| 5 | Production Merge — Validated V2 into production | Planned |

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| V2 uploader breaks production | Isolated file, never touches `tiktok.py` until validated |
| CrewAI LLM costs spike | `max_iter` limits, local Ollama as fallback |
| ChromaDB data corruption | Daily backup to PostgreSQL as source of truth |
| Shadow-ban on test accounts | Dedicated throwaway accounts for V2 testing only |

## New Dependencies (when merged)
```
curl_cffi
crewai
crewai-tools
chromadb
```

# Architecture Changes Log

## April 2026 — Strategic Upgrade Plan

### Overview
Three major upgrades planned for the Manga Automation / Arbitrage pipeline.
This document tracks what changed, why, and where to find the new code.

---

### 1. CrewAI Orchestration (replaces linear scripts)

**What changed**: `arbitrage_worker.py` and related scripts will be replaced by a
Manager-led CrewAI crew with 4 specialist agents (Scout, Harvester, Operator, Analyst).

**Why**: Linear scripts crash on unexpected errors. CrewAI agents self-correct —
if an account gets shadow-banned, the Manager autonomously quarantines it and
reassigns the task to a spare account without human intervention.

**Status**: Planned — see Phase 3 in `CLAWBOT_AGENT_PLAN.md`

**Key files (to be created)**:
- `manga-automation/scripts/crew/manager_agent.py`
- `manga-automation/scripts/crew/scout_agent.py`
- `manga-automation/scripts/crew/harvester_agent.py`
- `manga-automation/scripts/crew/operator_agent.py`
- `manga-automation/scripts/crew/analyst_agent.py`

---

### 2. ChromaDB Vector Memory

**What changed**: Added persistent vector database for long-term trend memory
and account health tracking.

**Why**: Agents need to remember what worked and what didn't across runs.
ChromaDB enables semantic search over historical performance data, so the
Trend Agent can proactively recommend content pivots before views drop.

**Status**: Planned — see Phase 2 in `CLAWBOT_AGENT_PLAN.md`

**Key files (to be created)**:
- `manga-automation/scripts/memory_manager.py`
- `docker-compose.yml` — add `chromadb` service on port 8001

**Collections**:
- `trend_memory` — viral topics + performance scores
- `account_health` — per-account upload history + shadow-ban flags
- `content_fingerprints` — video hashes to prevent re-uploads

---

### 3. TikTok Security Bypass V2 (isolated testing)

**What changed**: Created isolated V2 uploader with two new security layers.

**Why**: TikTok's duplicate hash detection suppresses re-uploaded content,
and their bot detection can fingerprint Python's TLS handshake at the network level.

**Status**: In testing — V2 files created, 72h validation required before production merge.

**New files**:
- `TiktokAutoUploader/tiktok_uploader/tiktok_v2.py` — V2 uploader (DO NOT use in production yet)
- `TiktokAutoUploader/test_v2_upload.py` — isolated test script

**Production file (unchanged)**:
- `TiktokAutoUploader/tiktok_uploader/tiktok.py` — untouched until V2 is validated

**V2 features**:
- FFmpeg mutation: hue shift ±2°, 1px crop, metadata strip, randomized CRF
- TLS bypass: `curl_cffi` impersonating Chrome 120 fingerprint

**Merge criteria**: ≥90% upload success rate over 72h on test accounts, zero shadow-bans detected.

**Test commands**:
```bash
# Test mutation only (no upload)
python test_v2_upload.py --test mutation --video path/to/video.mp4

# Test TLS session only
python test_v2_upload.py --test tls

# Full upload test (private video on test account)
python test_v2_upload.py --test upload --account <test_account> --video path/to/video.mp4
```

**New dependencies** (add to `requirements.txt` when merging):
```
curl_cffi
crewai
crewai-tools
chromadb
```

---

### Reference

Full architecture plan: `manga-automation/CLAWBOT_AGENT_PLAN.md`



curl -X POST http://localhost:8080/api/summon-agent \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Post the latest family guys clip from https://www.youtube.com/@7suc/shorts", "target_count": 1}'
https://accounts.google.com/o/oauth2/v2/auth?client_id=923431671500-j7s03dll8j1s5ad4t6s4d3i62i5oplsi.apps.googleusercontent.com&redirect_uri=http%3A%2F%2Flocalhost&scope=https%3A%2F%2Fwww.googleact_uri=http%3A%2F%2Flocalhost&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fyoutube&response_type=code&access_type=offline&prompt=consent&state=random_state_string
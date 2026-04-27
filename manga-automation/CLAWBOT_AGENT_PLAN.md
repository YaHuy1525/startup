# Agentic Arbitrage Feature Plan: Clawbot Integration

This plan outlines the integration of **Clawbot (OpenClaw)** into the existing Manga Automation pipeline. The goal is to introduce an autonomous, prompt-driven research layer that complements the existing static (`yt-dlp`) search scripts. 

By leveraging Clawbot's extensible skills and plugins (accessible via platforms like ClawHub), the system will evolve into a multi-agent orchestration pipeline that can intuitively scrape, understand, and publish content based on natural language instructions.

---

## 🏗️ 1. Architecture Overview

Your current system uses a deterministic, static loop (hardcoded queries -> `yt-dlp` -> PostgreSQL check -> Phantomwright upload). 

The new architecture will support **Hybrid Modes**:

---

## 🤖 What is CrewAI? (And Why It Changes Everything)

**CrewAI** is a Python framework for orchestrating multiple AI agents as a collaborative "crew" — each agent has a defined **Role**, **Goal**, and **Backstory**, and they work together to complete complex tasks autonomously.

### The Core Difference: Scripts vs. Agents

| Your Current System (Scripts) | New System (CrewAI) |
|---|---|
| Linear: Step 1 → Step 2 → Step 3 | Autonomous: Agents decide their own next step |
| Crashes on unexpected errors | Self-corrects: tries alternative approaches |
| Hardcoded queries | Dynamic: rewrites queries based on results |
| No memory between runs | Long-term memory via Vector DB |
| One account fails = whole pipeline stops | Manager reassigns to spare account |

### How CrewAI Works in Practice

CrewAI uses a **Manager Agent** (powered by an LLM like Claude or GPT-4) that acts as a supervisor. When you give it a goal like *"Post 5 viral manga edits today"*, the Manager:

1. Breaks the goal into sub-tasks
2. Assigns each sub-task to the right specialist agent (Scout, Harvester, Operator)
3. Monitors results — if the TikTok Operator hits a Captcha, the Manager **autonomously decides** to quarantine that account and switch to a spare
4. Aggregates results and reports back

This is the difference between a **to-do list** (scripts) and a **team of employees** (CrewAI).

### Manager-Led Crew: Autonomous Decision Making

```
Manager Agent (LLM Brain)
├── Scout Agent       → Finds trending content on TikTok
├── Harvester Agent   → Sources raw video from YouTube
├── Operator Agent    → Uploads to TikTok (with stealth)
└── Analyst Agent     → Reports performance back to dashboard
```

If the Operator hits a shadow-ban or Captcha:
- **Old system**: Script crashes, you wake up to 0 uploads
- **CrewAI**: Manager detects the failure, quarantines the account, assigns the task to a spare account, continues uploading

---

## 🧠 2. Vector Database Integration (The "Agent Brain")

### What is a Vector Database?

A **Vector Database (ChromaDB)** stores information as mathematical embeddings — meaning it understands *semantic similarity*, not just exact keyword matches. When the Trend Agent stores "JJK Chapter 236 went viral on March 15", it can later retrieve that memory when asked "what manga content performed well last month?" — even if the exact words don't match.

### Implementation Plan

- **Database**: ChromaDB (runs locally in Docker, no external API needed)
- **Collections**:
  - `trend_memory` — stores viral topics, view counts, dates, and performance scores
  - `account_health` — stores per-account upload history, shadow-ban flags, view averages
  - `content_fingerprints` — stores hashes of uploaded videos to prevent re-uploads

### Feedback Loop Behavior

The Trend Agent will actively cross-reference memory before making decisions:

```
Trend Agent checks ChromaDB:
  "JJK edits: 3-day average views = 1,200 (declining -40%)"
  "One Piece Chapter 1111: trending in TikTok Discovery, 0 uploads from us"
  
→ Recommendation: "Shift content focus to One Piece Chapter 1111"
→ Manager approves → Harvester pivots search queries
```

This turns the system from **reactive** (you notice low views and manually change strategy) to **proactive** (the system tells you what to change before views drop).

---

## 🛡️ 3. TikTok Security Bypass Strategy

### Two-Layer Defense

#### Layer 1: Video Hash-Mutation (Anti-Duplicate Detection)

TikTok runs a perceptual hash check on every upload. If your video matches a hash already in their system, it gets suppressed or flagged as duplicate content — even if you downloaded it from YouTube legitimately.

**The Fix (FFmpeg Mutation Pipeline)**:
```
Original Video
    ↓
[1] Hue shift: ±2° (imperceptible to human eye, breaks hash)
    ↓
[2] Crop 1px on each edge (changes frame dimensions)
    ↓
[3] Strip all metadata (removes camera/software fingerprints)
    ↓
[4] Re-encode with randomized encoding params
    ↓
Mutated Video → Unique hash → TikTok sees it as original content
```

#### Layer 2: TLS Fingerprint Bypass (Network Stealth)

Python's `requests` library has a recognizable TLS handshake signature. TikTok's infrastructure can detect "this connection is from a Python script" at the network level — before any cookies or session data are even checked.

**The Fix (`curl_cffi`)**:
- `curl_cffi` impersonates the exact TLS fingerprint of Chrome, Safari, or Firefox
- The connection looks identical to a real iPhone or desktop browser at the deepest network level
- Combined with proper session cookies, TikTok's bot detection has no signal to act on

### Isolated V2 Testing Pipeline

To protect the working production system, the new security features are developed in isolation:

```
TiktokAutoUploader/
├── tiktok_uploader/
│   ├── tiktok.py              ← PRODUCTION (untouched until V2 is validated)
│   └── tiktok_v2.py           ← NEW: V2 with mutation + TLS bypass (testing)
```

**Validation Flow**:
1. `tiktok_v2.py` runs on **test accounts only** for 72 hours
2. If upload success rate ≥ 90% and no shadow-bans detected → merge into production
3. If issues arise → `tiktok.py` remains untouched, V2 is debugged separately

---

## 🏗️ 4. Full Architecture Overview

### Agent Roles (Manager-Led Crew)

1. **Manager Agent (The Director)**
   - *Purpose*: Receives the high-level goal, delegates to specialist agents, handles failures autonomously
   - *Key Behavior*: If Operator fails → quarantine account → reassign to spare → continue

2. **TikTok Trend Agent (The Scout)**
   - *Purpose*: Autonomously browse TikTok to find breakout trends, viral audio, and popular video concepts
   - *Memory*: Reads/writes to ChromaDB `trend_memory` collection
   - *Output*: Ranked list of trending concepts with confidence scores

3. **YouTube Content Agent (The Harvester)**
   - *Purpose*: Takes trending concepts from Scout and finds matching high-quality source videos on YouTube
   - *Filters*: >100k views, under 60 seconds, not already in `content_fingerprints`

4. **Publisher Agent (The Operator)**
   - *Purpose*: Manages distribution using `upload_tiktok_v2.py` (mutation + TLS stealth)
   - *Fallback*: If V2 fails, Manager can fall back to `upload_tiktok.py`

5. **Reporter Agent (The Analyst)**
   - *Purpose*: Monitors pipeline results, writes performance data to ChromaDB, pushes live logs to dashboard

---

## 🛠️ 5. Core Implementation Components

### A. CrewAI Setup

```python
# Install
pip install crewai crewai-tools chromadb curl_cffi

# Manager-led crew structure
from crewai import Agent, Task, Crew, Process

manager = Agent(role="Pipeline Manager", goal="Maximize viral content output", ...)
scout   = Agent(role="Trend Scout",      goal="Find trending manga content", ...)
# ...

crew = Crew(
    agents=[scout, harvester, operator, analyst],
    tasks=[...],
    manager_agent=manager,
    process=Process.hierarchical  # Manager-led, not sequential
)
```

### B. ChromaDB Setup

```python
import chromadb

client = chromadb.PersistentClient(path="./data/chromadb")
trend_memory    = client.get_or_create_collection("trend_memory")
account_health  = client.get_or_create_collection("account_health")
content_hashes  = client.get_or_create_collection("content_fingerprints")
```

### C. FFmpeg Mutation (tiktok_v2.py)

```python
import subprocess, random, os

def mutate_video(input_path: str, output_path: str) -> str:
    hue_shift = random.uniform(-2.0, 2.0)
    cmd = [
        "ffmpeg", "-i", input_path,
        "-vf", f"hue=h={hue_shift},crop=iw-2:ih-2:1:1",
        "-map_metadata", "-1",          # strip all metadata
        "-c:v", "libx264",
        "-crf", str(random.randint(18, 22)),  # randomize encoding
        "-preset", "fast",
        "-y", output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path
```

### D. TLS Bypass (tiktok_v2.py)

```python
from curl_cffi import requests as cffi_requests

# Impersonate Chrome 120 TLS fingerprint
session = cffi_requests.Session(impersonate="chrome120")
# All subsequent requests look like real Chrome at the network level
```

### E. Environment & Docker

Add to `docker-compose.yml`:
```yaml
chromadb:
  image: chromadb/chroma:latest
  volumes:
    - ./data/chromadb:/chroma/chroma
  ports:
    - "8001:8000"
```

### F. API Layer

New endpoint on the worker:
```
POST /api/summon-agent
{
  "prompt": "Find top 5 trending JJK manga edits from last 24 hours",
  "target_count": 5,
  "platforms": ["tiktok", "youtube"]
}
```

### G. Web Dashboard UI Updates (React)

New **"Agent Control Center"** panel:
1. Prompt text area for natural language instructions
2. Target count input
3. Live WebSocket terminal showing agent thoughts in real-time
4. Performance feed from Reporter Agent with ChromaDB trend insights

---

## 🚀 6. Step-by-Step Execution Flow

1. **Initialization**: User enters prompt in dashboard → clicks "Dispatch Agent"
2. **Manager Delegation**: Manager Agent breaks goal into tasks, assigns to crew
3. **Trend Discovery**: Scout queries TikTok + checks ChromaDB for historical context
4. **Content Sourcing**: Harvester searches YouTube, filters by views/length/duplicate hash
5. **Mutation**: Each video goes through FFmpeg mutation pipeline before upload
6. **Upload**: Operator uses `tiktok_v2.py` (curl_cffi + mutated video)
7. **Failure Handling**: If Operator fails → Manager quarantines account → reassigns
8. **Reporting**: Analyst writes results to ChromaDB, pushes summary to dashboard

---

## 📋 7. Implementation Phases

### Phase 1: Security Isolation (V2 Uploader)
- [ ] Create `TiktokAutoUploader/tiktok_uploader/tiktok_v2.py` with FFmpeg mutation
- [ ] Add `curl_cffi` TLS bypass to V2
- [ ] Write test script `test_v2_upload.py` for isolated testing on test accounts
- [ ] 72-hour validation period → if passes, merge to production

### Phase 2: Vector Memory (ChromaDB)
- [ ] Add ChromaDB service to `docker-compose.yml`
- [ ] Create `scripts/memory_manager.py` with trend/account/hash collections
- [ ] Integrate memory reads/writes into existing `fetch_tiktok_trends_apify.py`

### Phase 3: CrewAI Orchestration
- [ ] Install CrewAI, define Manager + 4 specialist agents
- [ ] Replace linear `arbitrage_worker.py` logic with hierarchical crew
- [ ] Implement account quarantine logic in Manager agent
- [ ] Connect crew to ChromaDB memory layer

### Phase 4: Dashboard Integration
- [ ] Add Agent Control Center UI to React dashboard
- [ ] WebSocket live terminal for agent thoughts
- [ ] ChromaDB trend insights feed

### Phase 5: Production Merge
- [ ] Merge validated `tiktok_v2.py` into production pipeline
- [ ] Full end-to-end test with real accounts
- [ ] Document changes (see `ARCHITECTURE_CHANGES.md`)

---

## ⚠️ Risk Mitigation

| Risk | Mitigation |
|---|---|
| V2 uploader breaks production | Isolated file, never touches `tiktok.py` until validated |
| CrewAI LLM costs spike | Set `max_iter` limits on agents, use local Ollama as fallback |
| ChromaDB data corruption | Daily backup to PostgreSQL as source of truth |
| Shadow-ban on test accounts | Use dedicated throwaway accounts for V2 testing only |




#1. Download the website files

wget https://aws-tc-largeobjects.s3.us-west-2.amazonaws.com/CUR-TF-200-ACACAD-3-113230/15-lab-mod11-challenge-CFn/s3/static-website.zip

unzip static-website.zip -d static

cd static

#2. Set the ownership controls on the bucket

aws s3api put-bucket-ownership-controls --bucket createbucket-s3bucket-qlj2qia6jmh9 --ownership-controls Rules=[{ObjectOwnership=BucketOwnerPreferred}]

#3. Set the public access block settings on the bucket

aws s3api put-public-access-block --bucket createbucket-s3bucket-qlj2qia6jmh9 --public-access-block-configuration "BlockPublicAcls=false,RestrictPublicBuckets=false,IgnorePublicAcls=false,BlockPublicPolicy=false"

#4. Copy the website files to the bucket

aws s3 cp --recursive . s3://createbucket-s3bucket-qlj2qia6jmh9/ --acl public-read

aws s3 cp templates/cafe-app.yaml s3://c198586a5081508l14833101t1w584009737711-repobucket-gcqt0zl3mj3q
http://52.206.210.146/cafe
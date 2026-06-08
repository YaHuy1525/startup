# AI Gig Copilot — Telegram Bot Integration Guide

> Implementing the **AI Training Gig Copilot** feature (from `PLATFORM_SELECTION_GUIDE.md`) using the existing Telegram bot, worker, and Mastra agent architecture.

---

## Overview

This guide extends the current system with a new **Gig Copilot** module. It follows the **exact same patterns** already used in `telegram_bot.py` → `worker.py` → `mastra-agents/` to keep the implementation consistent and testable.

```
Telegram Command
    ↓
telegram_bot.py  (_dispatch_command)
    ↓
POST  http://python-worker:8080/gig/<route>
    ↓
worker.py  (ROUTES dict → handler fn)
    ↓
scripts/gig_*.py  (pure business logic)
    ↓
PostgreSQL (Supabase)  +  Mastra agent endpoint (optional)
```

---

## Phase 1 — Database (Week 1)

### 1.1 Run the migration

Create the file `database/migrations/004_gig_copilot.sql` and apply it via Supabase SQL editor or your migration tool:

```sql
-- gig_platform_profiles
CREATE TABLE gig_platform_profiles (
    id             SERIAL PRIMARY KEY,
    user_id        TEXT        NOT NULL,
    platform       TEXT        NOT NULL CHECK (platform IN ('dataannotation','outlier','babel')),
    country        TEXT,
    skills         TEXT[],
    hourly_target  NUMERIC(10,2),
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- gig_rubrics  (pre-seed per platform/task_type)
CREATE TABLE gig_rubrics (
    id             SERIAL PRIMARY KEY,
    platform       TEXT NOT NULL,
    task_type      TEXT NOT NULL,  -- e.g. "prompt-writing", "response-rating", "factual-eval"
    rubric_json    JSONB NOT NULL,
    active         BOOLEAN DEFAULT TRUE,
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- gig_tasks
CREATE TABLE gig_tasks (
    id                  SERIAL PRIMARY KEY,
    user_id             TEXT NOT NULL,
    platform            TEXT NOT NULL,
    task_type           TEXT NOT NULL,
    task_prompt         TEXT NOT NULL,
    reference_context   TEXT,
    status              TEXT DEFAULT 'drafted'  -- drafted|reviewed|submitted_manual|rejected|accepted
                          CHECK (status IN ('drafted','reviewed','submitted_manual','rejected','accepted')),
    time_spent_minutes  INTEGER,
    estimated_payout    NUMERIC(10,2),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- gig_outputs
CREATE TABLE gig_outputs (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER REFERENCES gig_tasks(id) ON DELETE CASCADE,
    draft_output    TEXT,
    final_output    TEXT,
    quality_score   NUMERIC(5,2),
    risk_flags_json JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- gig_sessions
CREATE TABLE gig_sessions (
    id                  SERIAL PRIMARY KEY,
    user_id             TEXT NOT NULL,
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    tasks_completed     INTEGER DEFAULT 0,
    effective_hourly_rate NUMERIC(10,2)
);

-- prompt_templates (win-rate learning)
CREATE TABLE prompt_templates (
    id            SERIAL PRIMARY KEY,
    platform      TEXT NOT NULL,
    task_type     TEXT NOT NULL,
    template_name TEXT NOT NULL,
    template_text TEXT NOT NULL,
    win_rate      NUMERIC(5,2) DEFAULT 0.0,
    use_count     INTEGER DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Phase 2 — Python Worker Scripts (Week 1–2)

Create these three scripts under `scripts/`. Each follows the same pattern as other scripts: a `main()` function that returns a plain `dict`.

### `scripts/gig_prepare.py`

```python
#!/usr/bin/env python3
"""
Gig Copilot — Task intake + draft generation.
Called by: POST /gig/task/create  and  POST /gig/task/draft
"""
import os, json, requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("gig_prepare")
MASTRA_URL = os.getenv("TELEGRAM_MASTRA_URL", "http://manga-agents:3001").rstrip("/")


def create_task(user_id: str, platform: str, task_type: str, brief: str) -> dict:
    """Insert a new gig_task row and return its id."""
    row = db.execute_one(
        """
        INSERT INTO gig_tasks (user_id, platform, task_type, task_prompt, status)
        VALUES (%s, %s, %s, %s, 'drafted')
        RETURNING id, platform, task_type, task_prompt, status
        """,
        (user_id, platform, task_type, brief),
    )
    logger.info(f"Created gig_task {row['id']} for {platform}/{task_type}")
    return row


def generate_draft(task_id: int) -> dict:
    """Call Mastra draftGeneratorAgent and store output in gig_outputs."""
    task = db.execute_one("SELECT * FROM gig_tasks WHERE id = %s", (task_id,))
    if not task:
        return {"error": f"task_id {task_id} not found"}

    # Fetch matching rubric (if available)
    rubric = db.execute_one(
        "SELECT rubric_json FROM gig_rubrics WHERE platform=%s AND task_type=%s AND active=TRUE LIMIT 1",
        (task["platform"], task["task_type"]),
    )

    payload = {
        "taskPrompt": task["task_prompt"],
        "taskType":   task["task_type"],
        "platform":   task["platform"],
        "rubric":     rubric["rubric_json"] if rubric else {},
    }

    try:
        resp = requests.post(f"{MASTRA_URL}/gig/task/draft", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {"error": str(exc), "task_id": task_id}

    draft_text = data.get("draft", "")
    db.execute(
        "INSERT INTO gig_outputs (task_id, draft_output) VALUES (%s, %s)",
        (task_id, draft_text),
    )
    return {"task_id": task_id, "draft": draft_text, "platform": task["platform"]}


def main(body: dict) -> dict:
    action = body.get("action", "create")
    if action == "create":
        return create_task(
            user_id=body.get("user_id", "default"),
            platform=body.get("platform", "dataannotation"),
            task_type=body.get("task_type", "prompt-writing"),
            brief=body.get("brief", ""),
        )
    if action == "draft":
        task_id = int(body["task_id"])
        return generate_draft(task_id)
    return {"error": f"unknown action: {action}"}
```

---

### `scripts/gig_score.py`

```python
#!/usr/bin/env python3
"""
Gig Copilot — Rubric scoring + risk flag check.
Called by: POST /gig/task/score
"""
import os, requests
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("gig_score")
MASTRA_URL = os.getenv("TELEGRAM_MASTRA_URL", "http://manga-agents:3001").rstrip("/")


def score_task(task_id: int) -> dict:
    task = db.execute_one("SELECT * FROM gig_tasks WHERE id = %s", (task_id,))
    output = db.execute_one(
        "SELECT * FROM gig_outputs WHERE task_id = %s ORDER BY created_at DESC LIMIT 1",
        (task_id,),
    )
    if not task or not output:
        return {"error": f"task or output not found for task_id={task_id}"}

    rubric = db.execute_one(
        "SELECT rubric_json FROM gig_rubrics WHERE platform=%s AND task_type=%s AND active=TRUE LIMIT 1",
        (task["platform"], task["task_type"]),
    )

    payload = {
        "taskPrompt":  task["task_prompt"],
        "draftOutput": output["draft_output"] or output["final_output"],
        "rubric":      rubric["rubric_json"] if rubric else {},
    }

    try:
        resp = requests.post(f"{MASTRA_URL}/gig/task/score", json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {"error": str(exc), "task_id": task_id}

    score      = data.get("score", 0.0)
    risk_flags = data.get("risk_flags", [])

    db.execute(
        "UPDATE gig_outputs SET quality_score=%s, risk_flags_json=%s WHERE id=%s",
        (score, risk_flags, output["id"]),
    )
    db.execute(
        "UPDATE gig_tasks SET status='reviewed', updated_at=NOW() WHERE id=%s",
        (task_id,),
    )
    return {
        "task_id":    task_id,
        "score":      score,
        "risk_flags": risk_flags,
        "status":     "reviewed",
    }


def main(body: dict) -> dict:
    return score_task(int(body["task_id"]))
```

---

### `scripts/gig_session_report.py`

```python
#!/usr/bin/env python3
"""
Gig Copilot — Session / daily / weekly analytics.
Called by: GET /gig/session/summary
"""
from scripts.utils import database as db
from scripts.utils.logger import setup_logger

logger = setup_logger("gig_session_report")


def today_summary(user_id: str = "default") -> dict:
    rows = db.execute(
        """
        SELECT t.platform, t.status, t.time_spent_minutes, t.estimated_payout,
               o.quality_score
        FROM gig_tasks t
        LEFT JOIN gig_outputs o ON o.task_id = t.id
        WHERE t.user_id = %s
          AND t.created_at >= CURRENT_DATE
        ORDER BY t.created_at DESC
        """,
        (user_id,),
    )
    if not rows:
        return {"user_id": user_id, "today": "No gig tasks logged yet."}

    total   = len(rows)
    done    = sum(1 for r in rows if r["status"] in ("accepted", "submitted_manual"))
    minutes = sum(r["time_spent_minutes"] or 0 for r in rows)
    payout  = sum(float(r["estimated_payout"] or 0) for r in rows)
    hourly  = (payout / (minutes / 60)) if minutes > 0 else 0.0
    avg_q   = sum(float(r["quality_score"] or 0) for r in rows) / total

    return {
        "user_id":               user_id,
        "tasks_today":           total,
        "tasks_done":            done,
        "total_minutes":         minutes,
        "estimated_payout_usd":  round(payout, 2),
        "effective_hourly_rate": round(hourly, 2),
        "avg_quality_score":     round(avg_q, 2),
    }


def week_summary(user_id: str = "default") -> dict:
    rows = db.execute(
        """
        SELECT DATE(t.created_at) AS day,
               COUNT(*) AS tasks,
               SUM(t.time_spent_minutes) AS minutes,
               SUM(t.estimated_payout)   AS payout,
               AVG(o.quality_score)      AS avg_quality
        FROM gig_tasks t
        LEFT JOIN gig_outputs o ON o.task_id = t.id
        WHERE t.user_id = %s
          AND t.created_at >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY DATE(t.created_at)
        ORDER BY day DESC
        """,
        (user_id,),
    )
    return {"user_id": user_id, "weekly_breakdown": rows}


def main(body: dict) -> dict:
    period  = body.get("period", "today")
    user_id = body.get("user_id", "default")
    if period == "week":
        return week_summary(user_id)
    return today_summary(user_id)
```

---

## Phase 3 — Register Routes in `worker.py`

Add these entries to the `ROUTES` dict in `scripts/worker.py`:

```python
# ── Gig Copilot ──────────────────────────────────────────────────────────────
import scripts.gig_prepare        as gig_prepare
import scripts.gig_score          as gig_score
import scripts.gig_session_report as gig_report

# ... inside ROUTES dict:
"/gig/task/create":    lambda body: gig_prepare.main({**body, "action": "create"}),
"/gig/task/draft":     lambda body: gig_prepare.main({**body, "action": "draft"}),
"/gig/task/score":     lambda body: gig_score.main(body),
"/gig/task/finalize":  lambda body: _gig_finalize(body),   # see helper below
"/gig/session/today":  lambda body: gig_report.main({**body, "period": "today"}),
"/gig/session/week":   lambda body: gig_report.main({**body, "period": "week"}),
```

Add the finalize helper just before the `ROUTES` dict:

```python
def _gig_finalize(body: dict) -> dict:
    from scripts.utils import database as db
    task_id = int(body["task_id"])
    outcome = body.get("outcome")          # "accepted" | "rejected"
    minutes = body.get("minutes")
    payout  = body.get("payout")
    updates = ["updated_at=NOW()"]
    params  = []
    if outcome in ("accepted", "rejected", "submitted_manual"):
        updates.append("status=%s"); params.append(outcome)
    if minutes:
        updates.append("time_spent_minutes=%s"); params.append(int(minutes))
    if payout:
        updates.append("estimated_payout=%s"); params.append(float(payout))
    params.append(task_id)
    db.execute(
        f"UPDATE gig_tasks SET {', '.join(updates)} WHERE id=%s", params
    )
    return {"task_id": task_id, "updated": True}
```

---

## Phase 4 — Mastra Agents (Week 2)

Create agent files under `mastra-agents/src/agents/`:

### Agent files to create

| File | Mastra agent name | Purpose |
|---|---|---|
| `gigDraftGenerator.ts` | `draftGeneratorAgent` | Produce 2–3 structured candidate drafts |
| `gigRubricScorer.ts`   | `rubricScoringAgent`   | Score against rubric dimensions |
| `gigQualityGuard.ts`   | `qualityGuardAgent`    | Flag hallucination / risk |
| `gigClassifier.ts`     | `taskClassifierAgent`  | Detect task type from brief |

### API routes to expose in Mastra (`src/index.ts` or equivalent)

```typescript
// POST /gig/task/draft
app.post('/gig/task/draft', async (req, res) => {
  const { taskPrompt, taskType, platform, rubric } = req.body;
  const result = await draftGeneratorAgent.generate({
    messages: [{ role: 'user', content: JSON.stringify({ taskPrompt, taskType, platform, rubric }) }]
  });
  res.json({ draft: result.text });
});

// POST /gig/task/score
app.post('/gig/task/score', async (req, res) => {
  const { taskPrompt, draftOutput, rubric } = req.body;
  const result = await rubricScoringAgent.generate({
    messages: [{ role: 'user', content: JSON.stringify({ taskPrompt, draftOutput, rubric }) }]
  });
  // Expect agent to return JSON with { score: float, risk_flags: [] }
  const parsed = JSON.parse(result.text);
  res.json(parsed);
});
```

---

## Phase 5 — Telegram Commands (Week 1)

### 5.1 Add command handlers to `telegram_bot.py`

Add these handler functions following the existing pattern:

```python
# ── Gig Copilot ──────────────────────────────────────────────────────────────

def _cmd_gig_new(raw: str, chat_id: str) -> str:
    """
    /gig_new <platform> <task_type> <brief text...>
    Example: /gig_new dataannotation prompt-writing Write a creative story prompt about space travel
    """
    rest = raw.replace("/gig_new", "", 1).strip()
    parts = rest.split(" ", 2)
    if len(parts) < 3:
        return (
            "Usage: /gig_new <platform> <task_type> <brief>\n\n"
            "Platforms: dataannotation | outlier | babel\n"
            "Task types: prompt-writing | response-rating | factual-eval | voice-script\n\n"
            "Example:\n"
            "/gig_new dataannotation prompt-writing Write a creative story about space"
        )
    platform, task_type, brief = parts[0], parts[1], parts[2]
    return _cmd_worker_route("/gig/task/create", {
        "user_id":   chat_id,
        "platform":  platform,
        "task_type": task_type,
        "brief":     brief,
    })


def _cmd_gig_draft(parts: List[str]) -> str:
    """
    /gig_draft <task_id>
    Generates 2-3 draft outputs for the given task.
    """
    if len(parts) < 2:
        return "Usage: /gig_draft <task_id>"
    return _cmd_worker_route("/gig/task/draft", {"task_id": int(parts[1])})


def _cmd_gig_score(parts: List[str]) -> str:
    """
    /gig_score <task_id>
    Runs rubric scoring and risk check on the latest draft.
    """
    if len(parts) < 2:
        return "Usage: /gig_score <task_id>"
    return _cmd_worker_route("/gig/task/score", {"task_id": int(parts[1])})


def _cmd_gig_submit_done(parts: List[str]) -> str:
    """
    /gig_submit_done <task_id> <accepted|rejected> <minutes> <payout>
    Log that you have manually submitted this task and record outcome.
    """
    if len(parts) < 5:
        return (
            "Usage: /gig_submit_done <task_id> <accepted|rejected> <minutes> <payout_usd>\n"
            "Example: /gig_submit_done 42 accepted 18 3.50"
        )
    return _cmd_worker_route("/gig/task/finalize", {
        "task_id": int(parts[1]),
        "outcome": parts[2],
        "minutes": int(parts[3]),
        "payout":  float(parts[4]),
    })


def _cmd_gig_today(chat_id: str) -> str:
    return _cmd_worker_route("/gig/session/today", {"user_id": chat_id})


def _cmd_gig_week(chat_id: str) -> str:
    return _cmd_worker_route("/gig/session/week", {"user_id": chat_id})
```

### 5.2 Register commands in `_dispatch_command`

Add these lines to the `_dispatch_command` function **before** the final `return f"Unknown command..."`:

```python
if cmd == "/gig_new":
    return _cmd_gig_new(text, chat_id)
if cmd == "/gig_draft":
    return _cmd_gig_draft(parts)
if cmd == "/gig_score":
    return _cmd_gig_score(parts)
if cmd == "/gig_submit_done":
    return _cmd_gig_submit_done(parts)
if cmd == "/gig_today":
    return _cmd_gig_today(chat_id)
if cmd == "/gig_week":
    return _cmd_gig_week(chat_id)
```

### 5.3 Update `_help_text()`

Add this block after the "Agents + Advanced" section:

```python
"Gig Copilot:\n"
"/gig_new <platform> <task_type> <brief>\n"
"/gig_draft <task_id>\n"
"/gig_score <task_id>\n"
"/gig_submit_done <task_id> <accepted|rejected> <minutes> <payout>\n"
"/gig_today\n"
"/gig_week\n\n"
"Gig Platforms: dataannotation | outlier | babel\n"
"Gig Task Types: prompt-writing | response-rating | factual-eval | voice-script\n\n"
```

---

## Scheduling agents (when things run automatically)

You have **three** options; pick one per job (do not duplicate the same job in both n8n and `agent-scheduler`).

| Method | Best for | Needs Docker 24/7? |
|--------|----------|----------------------|
| **n8n Schedule Trigger** | Daily at a fixed clock time (e.g. 21:00), existing manga pipelines | Yes — `n8n` + `python-worker` (+ `manga-agents` if the route calls Mastra) must be up at trigger time |
| **`agent-scheduler` service** | Simple “every N hours” HTTP calls to worker routes | Yes — same stack while the interval fires; enable with `docker compose --profile schedulers up -d agent-scheduler` and set `AGENT_SCHEDULE_JOBS` in `.env` |
| **Telegram only** | Manual `/gig_new`, `/summon`, `/hermes_order` | **No** scheduler — but `telegram-bot` must run whenever you want to send commands |

**Gig daily KPI (21:00):** use `n8n-workflows/09_gig_daily_analytics.json` (already in repo) — activate in n8n UI.

**Example `AGENT_SCHEDULE_JOBS` (Crew summon every 4h):**

```env
AGENT_SCHEDULE_JOBS=[{"name":"crew-trends","interval_seconds":14400,"path":"/api/summon-agent","body":{"prompt":"Find top trending short-form content","target_count":5}}]
```

Implementation: `scripts/agent_scheduler.py` (same pattern as `research_scheduler.py`).

**Do you need the whole stack 24/7?**

- **For scheduled runs:** whatever fires the schedule (n8n or `agent-scheduler`) plus **python-worker** must be running at trigger time. Routes that call Mastra agents also need **manga-agents** healthy.
- **telegram-bot** is **not** required for scheduled jobs (only for chat commands).
- **postgres** / **redis** must be up if the job touches the DB.
- If the machine sleeps or Docker is stopped, **missed runs are not replayed** (interval scheduler runs on next tick after wake).
- **Without 24/7 Docker:** use an external cron (GitHub Actions, cloud scheduler) to `curl` your public worker URL, or start the stack before you need automation.

---

## Phase 6 — n8n Workflows (Week 1–2)

Create these n8n workflow JSON files under `n8n-workflows/`. They follow the same pattern as your existing workflows.

### Workflow A — `wf-gig-intake.json`

```
Trigger: Telegram Webhook  OR  Manual
→ HTTP Request: POST python-worker:8080/gig/task/create
→ HTTP Request: POST python-worker:8080/gig/task/draft
→ Telegram Send Message: "Draft ready for task #{{ $json.id }}"
```

### Workflow B — `wf-gig-quality.json`

```
Trigger: Webhook  /gig-review
→ HTTP Request: POST python-worker:8080/gig/task/score
→ IF quality_score >= 0.75:
    → Telegram: "✅ Task #{{ id }} ready to submit. Score: {{ score }}"
  ELSE:
    → Telegram: "⚠️ Task #{{ id }} needs revision. Flags: {{ risk_flags }}"
```

### Workflow C — `wf-gig-analytics.json`

```
Trigger: Schedule (every 24h at 21:00)
→ HTTP Request: POST python-worker:8080/gig/session/today
→ Telegram: Daily KPI summary message
```

---

## Phase 7 — `.env` Variables

Add these to your `.env` (and `.env.example`):

```env
# No new env vars required for Phase 1-2.
# Mastra agent endpoints are already configured via TELEGRAM_MASTRA_URL.
# (All gig routes use the same worker + mastra URLs already set up)

# Optional: default user_id when not using per-chat tracking
GIG_DEFAULT_USER_ID=default
```

---

## Command Reference Card

| Command | What happens |
|---|---|
| `/gig_new dataannotation prompt-writing Write a haiku prompt` | Creates `gig_tasks` row → triggers classifier + draft generator |
| `/gig_draft 42` | Calls `draftGeneratorAgent`, stores result in `gig_outputs` |
| `/gig_score 42` | Runs `rubricScoringAgent` + `qualityGuardAgent`, updates `quality_score` |
| `/gig_submit_done 42 accepted 20 4.50` | Logs manual submission result + time + payout |
| `/gig_today` | Returns today's task count, payout estimate, effective hourly rate |
| `/gig_week` | Returns 7-day breakdown by day |

---

## Compliance Boundaries (Hard Rules)

These constraints must be enforced at code level and never bypassed:

| Rule | Implementation |
|---|---|
| ❌ No browser automation | Scripts never import selenium/playwright |
| ⚠️ All drafts are AI-assisted only | `draft_output` column — never `final_output` auto-submitted |
| ✅ Human must finalize | `/gig_submit_done` requires explicit manual call from user |
| ✅ Risk flags always surfaced | `qualityGuardAgent` output always displayed in score reply |

---

## 30-Day Milestone Checklist

### Week 1
- [ ] Apply `database/migrations/004_gig_copilot.sql`
- [ ] Create `scripts/gig_prepare.py` (create + draft)
- [ ] Register `/gig/task/create` and `/gig/task/draft` in `worker.py`
- [ ] Add `/gig_new`, `/gig_draft`, `/gig_submit_done` to `telegram_bot.py`
- [ ] Verify end-to-end: `/gig_new dataannotation prompt-writing test task`

### Week 2
- [ ] Create `scripts/gig_score.py`
- [ ] Add `gigDraftGenerator.ts` and `gigRubricScorer.ts` Mastra agents
- [ ] Register `/gig/task/score` in `worker.py`
- [ ] Add `/gig_score` to `telegram_bot.py`
- [ ] Create `wf-gig-intake.json` and `wf-gig-quality.json` in n8n

### Week 3
- [ ] Create `scripts/gig_session_report.py`
- [ ] Register `/gig/session/today` and `/gig/session/week` in `worker.py`
- [ ] Add `/gig_today` and `/gig_week` to `telegram_bot.py`
- [ ] Create `wf-gig-analytics.json` with 24h schedule trigger in n8n
- [ ] Seed `gig_rubrics` with first rubric for `dataannotation/prompt-writing`

### Week 4
- [ ] Add `prompt_templates` win-rate tracking
- [ ] Add `gigClassifier.ts` Mastra agent (optional)
- [ ] Add session coach recommendations to `/gig_week` output
- [ ] Review KPIs: acceptance rate, effective hourly rate trend

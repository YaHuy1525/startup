# Platform Selection Guide (Based on `minimoney_ai_guide.pdf`)

## Chosen Platform Type: **AI Training Gig Copilot** (DataAnnotation/Outlier/Babel workflow support)

This is the strongest fit for your current system because:

- It is marked **AI: GREAT FIT** in the guide.
- Your stack already has the core primitives needed: `PostgreSQL`, `Redis`, `n8n`, `Mastra agents`, Python worker scripts, and Telegram command control.
- It avoids account-ban risk from prohibited bot completion. The product can stay as a **copilot** (prep, quality review, tracking, and analytics), while final submission remains human.
- It can reuse your existing strengths: prompt generation, queueing, scoring, templating, scheduler jobs, and reporting.

---

## What To Build

Build a **Task Copilot Platform** that helps users complete AI-training gigs faster and with higher quality:

1. Ingest task briefs and rubrics from users.
2. Generate draft prompts/answers/justifications.
3. Run quality checks (clarity, ambiguity, coverage, factual risk).
4. Score against platform-specific rubric templates.
5. Track completed tasks and estimated hourly rate.
6. Provide daily plans and performance feedback via Telegram.

Important boundary: no automated login/click/submit into DataAnnotation, Outlier, or Babel.

---

## Implementation Guide (Using Current System)

## 1) Data model additions (Postgres)

Add migrations for:

- `gig_platform_profiles`
  - `id`, `user_id`, `platform` (`dataannotation|outlier|babel`)
  - `country`, `skills`, `hourly_target`
- `gig_rubrics`
  - `id`, `platform`, `task_type`, `rubric_json`, `active`
- `gig_tasks`
  - `id`, `user_id`, `platform`, `task_type`, `task_prompt`, `reference_context`
  - `status` (`drafted|reviewed|submitted_manual|rejected|accepted`)
  - `time_spent_minutes`, `estimated_payout`
- `gig_outputs`
  - `id`, `task_id`, `draft_output`, `final_output`, `quality_score`, `risk_flags_json`
- `gig_sessions`
  - `id`, `user_id`, `started_at`, `ended_at`, `tasks_completed`, `effective_hourly_rate`

This mirrors your existing queue/status-driven pipeline style.

## 2) Agent layer additions (Mastra)

Create agents similar to your current content flow:

- `taskClassifierAgent`
  - Detect: prompt-writing, response-rating, factual-eval, voice-script prep.
- `draftGeneratorAgent`
  - Produce multiple candidate drafts with distinct structures.
- `rubricScoringAgent`
  - Score outputs against stored rubric dimensions.
- `qualityGuardAgent`
  - Flag hallucination risk, unsupported claims, shallow reasoning, or instruction mismatch.
- `sessionCoachAgent`
  - Recommend what to do next based on rejection reasons and hourly performance.

Expose endpoints:

- `POST /gig/task/create`
- `POST /gig/task/draft`
- `POST /gig/task/score`
- `POST /gig/task/finalize`
- `GET /gig/session/summary`
- `GET /gig/rubric/:platform/:taskType`

## 3) Python worker scripts

Add scripts for offline/CLI workflows:

- `scripts/gig_prepare.py` — creates draft pack from task brief
- `scripts/gig_score.py` — local rubric scoring and risk flags
- `scripts/gig_session_report.py` — daily/weekly performance report

Keep them API-callable from your existing `worker.py` pattern.

## 4) n8n workflows

Add a new workflow set (same orchestration style as your current stack):

1. **Task Intake Workflow**
   - Trigger: Telegram command or webhook
   - Stores task, invokes classifier + draft generator
2. **Quality Review Workflow**
   - Runs rubric scoring and risk checks
   - Sends “ready to submit manually” packet
3. **Session Analytics Workflow**
   - Every 6-24h: aggregates acceptance rate, rework rate, hourly estimate
   - Sends coaching summary

## 5) Telegram bot commands

Extend command layer:

- `/gig_new <platform> <task_type> <brief>`
- `/gig_draft <task_id>`
- `/gig_score <task_id>`
- `/gig_submit_done <task_id> <accepted|rejected> <minutes> <payout>`
- `/gig_today`
- `/gig_week`

This keeps UX consistent with your current operational control model.

## 6) Prompt library and reusable templates

Create a versioned template set:

- `prompt_templates` table with fields:
  - `platform`, `task_type`, `template_name`, `template_text`, `win_rate`
- Auto-rank templates by acceptance outcomes.
- Archive low-performing templates and surface top performers by context.

## 7) Compliance & risk controls

Implement hard constraints:

- No browser automation for submission.
- Every output marked as “AI-assisted draft.”
- Mandatory human review checklist before “finalize.”
- Data retention controls for sensitive task text.

This keeps platform usage inside expected ToS boundaries.

---

## 30-Day Rollout Plan

### Week 1: Foundation
- Add DB migrations and basic `/gig/task/create` + `/gig/task/draft`.
- Add Telegram intake command.
- Store manual outcomes (`accepted/rejected`) only.

### Week 2: Quality loop
- Build rubric scoring + risk flags.
- Add review packet output and `/gig_score`.

### Week 3: Analytics loop
- Add session tracking, hourly calculations, rejection clustering.
- Ship `/gig_today` and `/gig_week`.

### Week 4: Optimization
- Add template win-rate learning.
- Add “next best task type” recommendations by user skill/performance.

---

## Second Category To Implement: Research Studies Copilot (Prolific + CloudResearch)

If you want a second lane beyond AI training gigs, this is the best add-on category.

Why this category is practical:

- The guide rates it as **AI: MODERATE**, which is still useful with your current architecture.
- The workflow is naturally compatible with your stack: intake, checklisting, draft assist, QA, and reporting.
- It is low risk if kept manual at completion/submission time.

### What to build for Research Studies

Add a lightweight copilot module focused on speed, quality, and consistency:

1. Study alert and prioritization queue.
2. Pre-study brief explainer (topic, expected difficulty, what to watch for).
3. Open-text answer drafting support (multiple variants).
4. Attention-check and consistency reminders.
5. Submission log + payout/hour analytics.

### Research studies data model (add-on tables)

- `study_platform_profiles`
  - `id`, `user_id`, `platform` (`prolific|cloudresearch`), `profile_json`, `last_profile_update`
- `study_tasks`
  - `id`, `user_id`, `platform`, `title`, `estimated_minutes`, `payout_estimate`, `status`
- `study_drafts`
  - `id`, `study_task_id`, `question_text`, `draft_a`, `draft_b`, `selected_final`
- `study_outcomes`
  - `id`, `study_task_id`, `completed_at`, `actual_minutes`, `actual_payout`, `accepted`

### Research studies n8n + Telegram flow

- Intake commands:
  - `/study_new <platform> <title> <minutes> <payout>`
  - `/study_draft <task_id>`
  - `/study_done <task_id> <minutes> <payout> <accepted|rejected>`
  - `/study_today`
- Scheduled jobs:
  - Daily profile completeness reminder
  - Weekly payout/hour summary and recommendations

### Non-negotiables

- No automation for answering/submitting on platform.
- Use AI drafts as assistive text only; you do the final response manually.
- Never fabricate participant responses or bypass attention checks.

---

## Manual-First AI Assist Matrix

Use this matrix as operating policy: AI supports, you execute manually.

| Workflow Step | AI Does | You Do Manually | Boundary |
|---|---|---|---|
| Opportunity triage | Rank tasks by expected hourly rate and fit | Choose and open actual task | No auto-accept/join |
| Task/rubric parsing | Convert brief into checklist + success criteria | Confirm checklist against platform text | Must verify before action |
| Draft generation | Produce 2-3 candidate answers/prompts | Edit, personalize, and submit final | Never submit raw AI draft |
| Quality review | Score clarity, completeness, and risk flags | Resolve flagged issues | Human must sign off |
| Research support | Summarize unfamiliar topics quickly | Validate key facts in task context | No blind factual copy |
| Session logging | Auto-build summary and KPI trends | Enter true minutes/payout/outcome | No synthetic metrics |
| Rejection analysis | Cluster failure reasons and suggest fixes | Apply fixes in next tasks | Human decides final strategy |
| Support tickets | Draft clear, professional ticket language | Submit with real evidence | No fabricated evidence |

### Green / Yellow / Red boundaries

- **Green (safe):** planning, drafting, proofreading, rubric checking, analytics.
- **Yellow (careful):** factual statements, domain-specific judgments, policy-sensitive language.
- **Red (not allowed):** automated account actions, auto-submission, identity spoofing, fabricated responses.

### Daily manual-first loop (recommended)

1. Run AI triage for available tasks.
2. Pick top 1-3 tasks manually.
3. Use AI for draft + QA pack.
4. Edit and submit manually.
5. Log outcome and minutes.
6. Review end-of-day KPI summary.

---

## Why Other Platform Types Were Not Chosen

## Research studies (Prolific/CloudResearch) — **Not chosen**
- Not selected as the primary platform because AI training gigs have a higher upside.
- Still recommended as the **second category** because it is stable, manual-safe, and easy to layer into your current system.

## GPT offer sites (ySense/Swagbucks/Freecash/CashInStyle) — **Not chosen**
- The guide marks these as **AI: LIMITED**.
- High ban risk if automation is pushed too far; most useful automation is only comparison/logging/support messaging.
- Lower quality moat for your engineering-heavy pipeline.

## Passive bandwidth apps — **Not chosen**
- Install-and-forget model with tiny operational surface.
- Very little room for a robust automation product.

## Cashback apps — **Not chosen**
- Useful personally, but product value depends on shopping behavior and regional app support.
- Weaker fit with your existing queue/agent/pipeline architecture.

## Crypto mining — **Not chosen**
- Profitability depends mostly on electricity cost and hardware economics, not workflow intelligence.
- Automation helps scheduling, but cannot fix poor unit economics.

## Investing (Robinhood) — **Not chosen**
- Strong AI research use case, but this drifts into financial-advice/compliance territory.
- Higher legal/regulatory complexity than your current media automation domain.

## Gambling-style platforms (Bingo Cash, Stake, etc.) — **Rejected**
- The guide explicitly marks them **AVOID**.
- No responsible or sustainable automation strategy exists here.

---

## Success Metrics

Use these KPIs from day one:

- Average prep time per task (down is better)
- Acceptance rate after first submission (up is better)
- Rework rate after rejection (down is better)
- Effective hourly rate trend (up is better)
- Draft-to-final conversion rate (up is better)

If these move in the right direction over 2-4 weeks, the platform is working.

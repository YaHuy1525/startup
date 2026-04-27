# Gig Copilot — User Guide

> Your AI assistant for DataAnnotation, Outlier, and Babel gig work.
> All commands run from your Telegram bot. You do the final submission manually.

---

## How It Works (30-second version)

```
You find a task on the platform
        ↓
/gig_new → logs it and generates AI drafts
        ↓
/gig_score → scores the draft, flags risks
        ↓
You edit the draft and submit manually on the platform
        ↓
/gig_submit_done → logs your outcome and payout
        ↓
/gig_today → shows your daily KPIs
```

---

## Platform Quick Reference

| Platform | URL | Best task types |
|---|---|---|
| DataAnnotation | datannotation.tech | prompt-writing, response-rating |
| Outlier | outlier.ai | prompt-writing, factual-eval |
| Babel | babel.money | factual-eval, voice-script |

**Task types you can use:**

| Slug | What it means |
|---|---|
| `prompt-writing` | You write original prompts for AI models to respond to |
| `response-rating` | You rate/rank AI responses against a rubric |
| `factual-eval` | You verify factual accuracy of AI-generated content |
| `voice-script` | You write natural conversational text for voice AI |

---

## Step-by-Step Daily Workflow

### Step 1 — Find a task on the platform

Log in to DataAnnotation / Outlier / Babel.
Pick a task. Read the brief carefully before opening the bot.

---

### Step 2 — Log it with `/gig_new`

```
/gig_new <platform> <task_type> <brief>
```

Copy the task brief directly into the command. The more detail you paste, the better the draft.

**Examples:**

```
/gig_new dataannotation prompt-writing Write a prompt that tests a model's ability to explain quantum entanglement to a 10-year-old using only household objects as analogies

/gig_new outlier response-rating Rate these two AI responses on accuracy, coherence, and helpfulness. Response A says X, Response B says Y

/gig_new babel factual-eval Evaluate whether this AI claim is accurate: "The Roman Empire fell in 476 AD due primarily to economic collapse"

/gig_new outlier voice-script Write a 100-word spoken-word explainer about how vaccines work for an AI voice assistant
```

**Bot replies with:**
```
Task #42 created. Run /gig_draft 42 to generate drafts.
```

---

### Step 3 — Generate AI drafts with `/gig_draft`

```
/gig_draft <task_id>
```

Example:
```
/gig_draft 42
```

The bot produces **2 structured drafts** (Draft A and Draft B) with different approaches, plus a Notes section recommending which to use and why.

> ⚠️ These are starting points, not final submissions. Always edit before submitting.

---

### Step 4 — Score the draft with `/gig_score`

```
/gig_score <task_id>
```

Example:
```
/gig_score 42
```

**Bot replies with something like:**
```
✅ Task #42 — Score: 0.83 / 1.00 (pass ≥ 0.70)

Risk flags:
  ✅ None

Ready to submit manually.
```

or if there are issues:
```
❌ Task #42 — Score: 0.61 / 1.00 (pass ≥ 0.70)

Risk flags:
  ⚠️ shallow_reasoning
  ⚠️ unsupported_factual_claim

Revise the draft before submitting.
```

**Common risk flags and what to do:**

| Flag | Fix |
|---|---|
| `shallow_reasoning` | Add more depth — explain the "why", not just the "what" |
| `unsupported_factual_claim` | Add nuance: "evidence suggests…" instead of "X is true" |
| `hallucination_risk` | Remove or soften any specific stats/dates you can't verify |
| `instruction_mismatch` | Re-read the task brief — the draft may have drifted off-topic |
| `ambiguous_language` | Clarify pronouns, define terms, use explicit references |
| `too_short` | Expand your answer — most platforms expect 100–300 words |
| `policy_risk` | Remove any borderline content; stay neutral |

---

### Step 5 — Edit and submit on the platform

Take the draft from the bot, edit it based on the score feedback, then **paste it into the platform yourself and submit manually.**

> 🔴 Never paste the raw AI draft directly. Always review and personalise it first.

---

### Step 6 — Log the outcome with `/gig_submit_done`

After the platform shows your result (accepted/rejected):

```
/gig_submit_done <task_id> <accepted|rejected> <minutes_spent> <payout_usd>
```

Examples:
```
/gig_submit_done 42 accepted 20 3.50
/gig_submit_done 43 rejected 12 0
```

- `minutes_spent` = total time from opening the task to submitting (be honest — this feeds your hourly rate calculation)
- `payout_usd` = what the platform shows for that task

---

### Step 7 — Check your daily KPIs

```
/gig_today
```

**Reply example:**
```
📊 Today's Gig Report

Tasks: 5 created · 4 done · 1 rejected
Acceptance: 80%
Time: 98 min
Payout: $14.50
Effective rate: $8.88/hr
Avg quality: 0.81/1.00
Platforms: dataannotation(3) outlier(2)
```

For a 7-day breakdown:
```
/gig_week
```

---

## Platform-Specific Tips

### DataAnnotation

- Tasks are usually **prompt-writing** or **response-rating**.
- Rubric is scored on: clarity · creativity · difficulty · safety · coverage.
- Prompts must be **1–3 sentences**, unambiguous, and require multi-step reasoning.
- Avoid yes/no answerable prompts — they score low.
- Response ratings need a clear **1–5 scale justification per dimension**.

**Good `/gig_new` example:**
```
/gig_new dataannotation prompt-writing Create a prompt that requires an AI to explain the tradeoffs between microservices and monolithic architecture, targeting a junior developer with 1 year of experience
```

---

### Outlier

- Focuses on **novel, domain-expert-level prompts** that models can't easily answer from web content.
- Rubric: specificity · novelty · complexity · safety.
- Comparative ratings require you to pick a winner with a 3+ sentence justification.
- Avoid prompts that can be googled in under 10 seconds.

**Good `/gig_new` example:**
```
/gig_new outlier prompt-writing Write a prompt requiring the model to derive the time complexity of a specific recursive algorithm that merges two sorted arrays with duplicate removal
```

---

### Babel

- Strong emphasis on **factual accuracy and sourcing**.
- Rubric: accuracy · sourcing · clarity · neutrality (min pass: 0.75 — stricter than others).
- For `factual-eval`: distinguish between "established fact", "likely true", "contested", "unknown".
- For `voice-script`: broadcast-quality. No contractions, no ambiguous pronouns, every sentence must be self-contained.

**Good `/gig_new` examples:**
```
/gig_new babel factual-eval Verify this claim: "Regular intermittent fasting increases lifespan by 15–20% based on peer-reviewed human studies"

/gig_new babel voice-script Write a 120-word AI assistant response explaining how photosynthesis works to a general adult audience, suitable for text-to-speech delivery
```

---

## KPI Targets to Aim For

Track these weekly with `/gig_week`:

| Metric | Target |
|---|---|
| Acceptance rate | **≥ 80%** |
| Effective hourly rate | **≥ $10/hr** |
| Avg quality score | **≥ 0.78** |
| Avg minutes per task | **≤ 25 min** |
| Rework rate (rejection → retry) | **≤ 20%** |

If acceptance drops below 70% for 3+ days in a row, run:
```
/gig_week
```
and look at which platform and task type is dragging it down — focus there.

---

## Command Cheat Sheet

| Command | What it does |
|---|---|
| `/gig_new dataannotation prompt-writing <brief>` | Log task + trigger draft generation |
| `/gig_new outlier response-rating <brief>` | Same, for Outlier |
| `/gig_new babel factual-eval <brief>` | Same, for Babel |
| `/gig_draft <id>` | Regenerate drafts (use if first attempt wasn't good) |
| `/gig_score <id>` | Run quality check + get risk flags |
| `/gig_submit_done <id> accepted <min> <$>` | Log accepted outcome |
| `/gig_submit_done <id> rejected <min> 0` | Log rejected outcome |
| `/gig_today` | Today's tasks, payout, hourly rate |
| `/gig_week` | 7-day breakdown by day |

---

## Boundaries — What the Bot Won't Do

| ❌ Not allowed | ✅ What to do instead |
|---|---|
| Auto-submit to the platform | Copy the draft, edit it, submit yourself |
| Click through the platform interface | Log in manually; bot has no browser access |
| Guarantee acceptance | Use `/gig_score` and fix flagged issues first |
| Fabricate stats or citations | Remove unsupported claims before submitting |

---

## Troubleshooting

**`/gig_draft` returns a generic draft not matching my brief**
→ Your brief was too vague. Re-run `/gig_new` with more detail from the actual task text.

**Score is 0.61 but I think the draft is fine**
→ Check the risk flags. Even one `hallucination_risk` or `instruction_mismatch` tanks the score. Fix those specific issues, re-run `/gig_score`.

**Platform rejected my submission but the bot gave 0.83**
→ The bot scores based on your brief. If the platform rubric is different to what you described, the score won't match. Add more rubric detail in your `/gig_new` brief next time.

**`/gig_today` shows $0**
→ You haven't run `/gig_submit_done` yet. The payout only counts once you log it.

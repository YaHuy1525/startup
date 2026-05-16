---
date: 2026-05-12
tags:
  - log
---

# Mentions Log

Every time someone publicly recognizes your work — in Slack, email, meetings, LinkedIn.

```dataview
TABLE WITHOUT ID file.link AS "Mention", date, from, source, context
FROM "Mentions"
WHERE contains(tags, "mention")
SORT date DESC
```

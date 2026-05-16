---
date: 2026-05-12
tags:
  - goal
---

# 2026 Goals

```dataview
TABLE WITHOUT ID file.link AS "Goal", category, progress + "%" AS "Progress", status
FROM "Goals"
WHERE contains(tags, "goal") AND status = "active"
SORT progress DESC
```

---
date: <% tp.date.now("YYYY-MM-DD") %>
tags:
  - project
status: active
job:
---

# <% tp.file.title %>

## Overview
<% tp.file.cursor() %>

## Architecture


## Key Decisions


## Links


## Related Tasks

```dataview
TABLE WITHOUT ID file.link AS "Task", status AS "Status"
FROM "Tasks"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
```

## Recent Activity

```dataview
LIST FROM "Daily"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
LIMIT 5
```

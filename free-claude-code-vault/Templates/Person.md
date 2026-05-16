---
date: <% tp.date.now("YYYY-MM-DD") %>
tags:
  - person
role:
company:
relationship_strength:
last_interaction: <% tp.date.now("YYYY-MM-DD") %>
follow_up_date:
contact_email:
location:
---

# <% tp.file.title %>

## About
<% tp.file.cursor() %>

## What They Care About


## How We Can Help Each Other


## Notes


---

## Interactions

```dataview
LIST FROM "Daily"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
LIMIT 15
```

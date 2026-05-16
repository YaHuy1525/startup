---
date: 2026-05-12
tags:
  - home
aliases:
  - Dashboard
---

# 🧠 Yahuy1525's Life OS

> Claude automatically saves everything important from every conversation.

---

## ⚡ Quick Navigation

| Work | Life | System |
|------|------|--------|
| [[Boards/free-claude-code\|📋 Work Board]] | [[Goals/2026 Goals\|🎯 Goals]] | [[Templates/\|📝 Templates]] |
| [[Boards/Personal\|📋 Personal]] | [[Finances/Income Streams\|💵 Income]] | [[Mentions/Mentions Log\|💬 Mentions]] |
| [[Projects/\|🔨 Projects]] | [[Health/Health Dashboard\|🏋️ Health]] | [[People/\|👥 People]] |

---

## 📅 Recent Daily Notes

```dataview
TABLE WITHOUT ID
  file.link AS "Day",
  mood AS "Mood",
  energy AS "Energy"
FROM "Daily"
SORT date DESC
LIMIT 7
```

---

## 🔥 Active Projects

```dataview
TABLE WITHOUT ID
  file.link AS "Project",
  status AS "Status",
  job AS "Job"
FROM "Projects"
WHERE contains(tags, "project") AND status = "active"
SORT file.name ASC
```

---

## 🎯 Goals

```dataview
TABLE WITHOUT ID
  file.link AS "Goal",
  category AS "Category",
  progress + "%" AS "Progress"
FROM "Goals"
WHERE contains(tags, "goal") AND status = "active"
SORT progress DESC
```

---

## 📊 Vault Stats

```dataviewjs
const all = dv.pages("");
const people = dv.pages('"People"').length;
const projects = dv.pages('"Projects"').length;
const dailies = dv.pages('"Daily"').length;
dv.paragraph(`📝 **${all.length}** notes · 👥 **${people}** people · 🔨 **${projects}** projects · 📅 **${dailies}** daily notes`);
```

---

kanban-plugin: board

---

## 📥 Backlog

- [ ] 🟡 **Set up scheduled agents** · @2026-05-19
	Morning/nightly/weekly agents to auto-maintain the vault. [[Projects/free-claude-code]]

- [ ] 🟡 **Create ADRs for existing architecture** · @2026-05-26
	Document key architectural decisions: provider abstraction pattern, SSE streaming design, messaging layer separation. [[Projects/free-claude-code]]

- [ ] 🟢 **Add people notes for contributors** · @2026-06-02
	Create People/ notes for key contributors. [[Projects/free-claude-code]]

- [ ] 🔴 **Implement Pipeline B Phase 1 (DB migration)** · @2026-05-19
	Run `005_arbitrage_pipeline.sql` migration to add trend_intel, arbitrage_assets, arbitrage_uploads tables. [[Projects/manga-automation]]

- [ ] 🟡 **Implement Pipeline B Phases 2-4** · @2026-05-26
	fetch_tiktok_trends_apify.py + source_youtube_assets.py + arbitrage_worker.py. Requires Apify token. [[Projects/manga-automation]]

- [ ] 🟡 **Validate TikTok V2 uploader (72h test)** · @2026-05-26
	Complete 72h isolated testing of tiktok_v2.py on test accounts. Merge to production if ≥90% success. [[Projects/manga-automation]]

- [ ] 🟡 **Phase 2.5 — Advanced dashboard features** · @2026-06-02
	Modal forms for accounts/proxies, drag-drop calendar, real-time workflow monitoring. ~6-8h. [[Projects/manga-automation]]

## 📋 This Week

- [ ] 🔴 **Install Obsidian plugins** · @2026-05-16
	Dataview, Templater, Kanban, Calendar plugins needed for full vault functionality.

- [ ] 🟡 **Log existing architecture as dev logs** · @2026-05-16
	Run `/obsidian-log` to capture what's been built so far for both projects. [[Projects/free-claude-code]] [[Projects/manga-automation]]

## 🔨 In Progress



## ⏳ Waiting On



## ✅ Done

- [x] ~~🔴 **Bootstrap vault**~~ ✅ 2026-05-12
- [x] ~~🔴 **Create project note (free-claude-code)**~~ ✅ 2026-05-12
- [x] ~~🟡 **Set up _CLAUDE.md with AI-first rules**~~ ✅ 2026-05-12
- [x] ~~🟡 **Create index.md and log.md**~~ ✅ 2026-05-12
- [x] ~~🟡 **Set up MCP server for vault access**~~ ✅ 2026-05-12
- [x] ~~🔴 **Ingest manga-automation project**~~ ✅ 2026-05-12

%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false,false,false]}
```
%%

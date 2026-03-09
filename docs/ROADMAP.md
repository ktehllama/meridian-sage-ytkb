# Meridian YTKB — Roadmap

## What is this?

A system that scrapes YouTube transcripts, embeds them into a vector database, and exposes them through a polished chat interface (Meridian). Ask it anything — it retrieves the most relevant video segments and synthesizes an answer with timestamped citations.

---

## Version History

### v1.x — Pipeline Foundation
*Phase 1–5 of the backend ingestion system.*

- Unified `pipeline.py` replacing legacy scraper + vector builder scripts
- Two-layer incremental ingestion: SQLite (transcripts) → ChromaDB (vectors)
- ~150-word chunks with 50-word overlap, title prepended per chunk
- Video filtering: min/max duration, keyword skip list
- MCP server (`yt_knowledge_mcp.py`) with 3 tools for Claude Desktop
- Hybrid search: BM25 + semantic similarity + cross-encoder re-ranking

---

### v2.x — Search Quality + Scale
*Pipeline hardening, search quality improvements, large-scale data ops.*

| Version | Date | Highlights |
|---------|------|------------|
| v2.0 | 2026-03-03 | Paginated ChromaDB scan (fixed 50K hard cap); `chunk_count` fix |
| v2.1 | 2026-03-03 | Channel queue system (SQLite-backed); `--sort-by views`; run receipts |
| v2.2 | 2026-03-03 | `queue remove`; `--scrape-only` flag for IP-safe scraping |
| v2.3 | 2026-03-03 | Audit tools: `yt_audit_channel`, `yt_scan_for_issues` |
| v2.4 | 2026-03-05 | Background BM25 build + disk cache; cross-encoder background load; Twitch chat guard |
| v2.5 | 2026-03-06 | `yt_list_videos` 10–20s → <0.5s via SQLite read; `_get_embedded_video_ids_fast` |
| v2.6 | 2026-03-06 | `yt_list_videos` context-window fix: channel summary instead of 4,879 individual rows |
| v2.7 | 2026-03-06 | 0-chunk channel fix; @cgpgrey merge; 228 missing videos embedded (249,641 total chunks) |
| v2.7.1 | 2026-03-07 | **First chat UI** — hero screen, UnicornBackground, sidebar, chat history persistence |

---

### v2.8–v2.9 — UI Foundation
*Initial chat interface polish before theming system.*

| Version | Date | Highlights |
|---------|------|------------|
| v2.8 | 2026-03-08 | Input auto-resize; blurple Q/D mode toggle; glassmorphism bar; suggestion shuffle |
| v2.9 | 2026-03-08 | Full black background pass across all components |

---

### v3.x — Meridian: Polished Product
*UX critique, theming, rebrand, and feature completeness.*

| Version | Date | Highlights |
|---------|------|------------|
| v3.0 | 2026-03-08 | UX critique pass — copy button, focus ring, suggestions hover fix, citation superscripts |
| v3.1 | 2026-03-08 | **Rebrand: Sage → Meridian** — new name, globe logo, updated all UI copy |
| v3.2 | 2026-03-07 | Performance — WebGL leak fix, abort fetch, React.memo, saveChat O(1) |
| v3.3 | 2026-03-08 | **Theming system** — 20 CSS variable tokens, dark/light (Solarized cream), SettingsPanel, favicon |
| v3.4 | 2026-03-08 | Smart chat naming (TF-IDF); @-mention autocomplete; relative timestamps; contrast audit |
| v3.5 | 2026-03-08 | **Floating chat bar** — absolute overlay, Claude.ai / ChatGPT style |
| v3.6 | 2026-03-08 | Blurple @mention highlight; infinite scroll dropdown; scrollbar polish |
| v3.7 | 2026-03-08 | CSS Grid textarea centering fix; scrollbar state fix |
| **v3.8** | **2026-03-08** | **Project structure + `start.sh` + GitHub push → ⭐ Stable Release** |

---

## v3.8 — Stable Release ⭐

The first complete, deployable version of Meridian. All core features shipped and polished:

**Backend**
- 249,641 transcript chunks across 80+ YouTube channels
- Hybrid BM25 + semantic search with cross-encoder re-ranking
- FastAPI backend with streaming Gemini 2.0 Flash responses
- Incremental pipeline — add channels without rebuilding

**Frontend (Meridian)**
- Floating glassmorphism chat bar with Quick/Deep mode toggle
- @-mention channel autocomplete with blurple highlight
- Smart auto-generated chat names
- Full dark/light theme system (Solarized cream light mode)
- Citation superscripts linking directly to YouTube timestamps
- Source cards with quotes, channel info, video duration
- Sidebar: saved chat history, channel browser, video search
- Settings panel: theme toggle, profile management
- Animated hero screen (Unicorn Studio WebGL)

**Deployment**
- Single `./start.sh` starts both API and frontend
- Works on Windows (Git Bash) and Linux/Raspberry Pi
- Runtime data (`yc_vectors/`, `knowledge.db`, `bm25_cache.pkl`) rsync'd separately

---

## Upcoming

| # | Feature | Status |
|---|---------|--------|
| #2 | Research Unicorn Studio JSON intercept (Service Worker) | Pending |
| #4 | UnicornBackground canvas color matches theme (light mode fix) | Blocked by #2 |
| — | Raspberry Pi deployment | Ready to rsync |
| — | Personal knowledge base per profile | Planned |

# Sage — Project Overview & Roadmap

## What It Is

Sage is a personal AI consultant that answers questions using a curated library of YouTube video transcripts. You point it at channels (YC, Acquired FM, any business/startup content), it scrapes and indexes everything, and then inside Claude Desktop you can ask "what does the knowledge base say about X" and get back timestamped video excerpts with direct YouTube links.

The goal is to make hours of video content instantly queryable — like having a researcher who has watched every episode and can cite the exact moment where a concept was discussed.

---

## What's Been Built

### Ingestion Pipeline (`pipeline.py`)
A unified two-layer pipeline that replaced two separate legacy scripts:

- **Layer 1 — SQLite:** yt-dlp fetches video metadata from a channel, `youtube-transcript-api` fetches each transcript, everything stored in `knowledge.db`. Fully incremental — already-scraped videos are skipped.
- **Layer 2 — ChromaDB:** Reads SQLite, chunks transcripts into ~150-word overlapping segments, embeds them into two vector collections: `transcripts` (one doc per chunk) and `video_metadata` (one doc per video for title/description-level matching). Also incremental.
- **Filtering:** Skips videos under 5 min, over 6 hours (configurable), and any with keywords like "shorts" in the title.
- **Anti-fingerprinting:** Rotates browser user-agents across 5 realistic Chrome/Firefox/Safari strings, creates a fresh `requests.Session` per transcript fetch, and applies jittered random delays between requests.

### MCP Server (`yt_knowledge_mcp.py`)
A FastMCP stdio server that exposes the knowledge base to Claude Desktop as 3 tools. The search tool (`yt_search_knowledge_base`) runs a 5-stage retrieval pipeline on every query:

1. **Semantic search** — ChromaDB cosine similarity over transcript chunks
2. **BM25 hybrid** — keyword scoring merged with semantic scores (40/60 weighting), built from an in-memory index loaded at startup
3. **Video-level boost** — queries the `video_metadata` collection; chunks from videos whose title/description matched get +0.2 score boost
4. **Cross-encoder re-ranking** — top 30 candidates fed as (query, chunk) pairs to `ms-marco-MiniLM-L-6-v2`; sees query and chunk together for precise relevance scoring
5. **Format and return** — top N results with video title, timestamp, YouTube deep-link, relevance %

### CLI Commands
| Command | What it does |
|---|---|
| `add-channel @handle` | Scrape + embed a channel (incremental) |
| `sync` | Embed anything in SQLite missing from ChromaDB |
| `rechunk` | Rebuild vectors with current chunk size (no re-scraping) |
| `rebuild` | Full wipe and re-embed |
| `status` | Stats for both SQLite and ChromaDB |
| `search "query"` | Raw semantic search from terminal (bypasses MCP pipeline) |

### Documentation
- `CLAUDE.md` — project context for Claude Code
- `MANUAL.md` — all CLI commands and flags with placeholders
- `CHANGELOG.md` — version history from v1 to v2.1

---

## Current State (v2.1)

| Setting | Value |
|---|---|
| Chunk size | 150 words with 50-word overlap |
| BM25 / semantic weight | 40% / 60% |
| Video metadata boost | +0.2 |
| Cross-encoder model | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Candidate pool (pre-rerank) | max(30, n_results × 4) |
| Default results returned | 8 |
| IP-ban protection | UA rotation + jittered delay |

Scraped and indexed: YC, Acquired FM (and any other channels you've run `add-channel` on).

---

## Possible Next Steps

### 1. Simple Web UI (replaces CLI)
Right now everything is CLI commands and Claude Desktop. A lightweight local web UI would make it accessible without opening a terminal. Something like:

- **Streamlit** or **Gradio** — minimal code, runs locally, good enough for personal use
- Pages: Add Channel (with progress bar), Knowledge Base status, Search (with results rendered nicely with timestamps as clickable links)
- Would make it easier to hand off to someone else or use on a different machine

### 2. Multi-Query Branching (skipped from Phase 6)
Before hitting ChromaDB, use Claude Haiku to generate 4 alternative phrasings of the query. Run all 5 in parallel, merge and deduplicate by chunk ID. Catches the word mismatch problem — "how do I get my first customers" and "early customer acquisition tactics" are the same question but use different vocabulary. Adds ~1–2s latency and a small API cost per query.

### 3. LLM Topic Tags on Ingestion (skipped from Phase 6)
One Claude API call per video at embed time to extract named concepts, frameworks, and domain terms from the first 1000 words of the transcript. Tags get prepended to every chunk from that video before embedding. Makes the embedding richer and creates a semantic bridge between query vocabulary and transcript vocabulary.

### 4. Scheduled Auto-Sync
A scheduled task (Windows Task Scheduler or a simple cron) that runs `add-channel` on your subscribed channels daily or weekly. New videos get picked up automatically without any manual step. Pairs well with the UI — you'd see "3 new videos indexed since last week."

### 5. Exponential Backoff on Transcript Failures
Currently if a transcript fetch fails, it marks the video as `has_transcript=0` and moves on. A smarter approach: retry up to 3 times with exponential backoff (1s, 4s, 16s) before giving up. Would recover from transient network errors without manual re-runs.

### 6. Search Analytics Logging
Log every query, how many results came back, and the top result's relevance score to a simple SQLite table. Over time this shows you which topics your knowledge base is weak on (low scores or zero results) so you know which channels to add next.

### 7. Multi-Platform Support
The pipeline is YouTube-specific right now. Podcast RSS feeds with transcript support (Spotify, Apple Podcasts via third-party APIs) would let you index audio content the same way. The chunking, embedding, and MCP layers would need no changes — only the ingestion layer would need adapters per source.

### 8. Knowledge Base Profiles
Right now `--db` and `--vectors` flags let you switch databases manually. A config file (`profiles.json`) storing named profiles (e.g. "startups", "investing", "tech") with their own SQLite/ChromaDB paths would make it easy to switch contexts without remembering paths — and the MCP server could accept a profile name instead of raw paths.

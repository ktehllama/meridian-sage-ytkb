# Meridian Sage — Project Overview

## What it is today

Meridian Sage is a full-stack AI knowledge retrieval system built around a personal library of YouTube transcripts. It indexes the content of 91 curated channels across 15 topic domains, makes all of it searchable through a 7-stage hybrid retrieval pipeline, and serves answers through a purpose-built chat interface backed by Gemini 2.0 Flash.

The corpus sits at 249,641 chunks across roughly 5,000 videos. Every answer cites the exact video and timestamp the information came from. The system runs in production on a Raspberry Pi 4, served via nginx, Let's Encrypt, and DuckDNS.

---

## Architecture (v4.1, current)

```
YouTube
   |
pipeline.py          yt-dlp + youtube-transcript-api
   |           |
knowledge.db   yc_vectors/     SQLite + ChromaDB (not in repo, rsync'd to Pi)
                   |
            bm25_cache.pkl     built on first API start, cached to disk
                   |
             api/main.py       FastAPI, port 8000
                   |
           sage_chat/          Next.js 14, port 3000
                   |
             chats.db          SQLite, server-side chat persistence
```

### Components

`pipeline.py` is the ingestion layer. It scrapes channel transcripts into SQLite and embeds them into ChromaDB in two separate, independently resumable steps. Both layers are fully incremental. SQLite commits after every video. ChromaDB checks for existing chunk IDs before embedding. A full interrupted run loses nothing.

`api/` is FastAPI on port 8000. On startup it connects to ChromaDB and builds a BM25 index from all chunks in a background thread, caching the result to `bm25_cache.pkl`. Every `/api/chat` request runs the full 7-stage retrieval pipeline and returns a synthesized answer with structured source citations.

`sage_chat/` is Next.js 14 on port 3000. It renders answers in markdown with `[SRC_N]` superscripts that link directly to YouTube timestamps, streams responses word-by-word, and persists chat history to the API via `chats.db`.

`meridian_sdk/` is a standalone Python client that runs hybrid search and synthesis directly against the local databases, no API server needed.

---

## Retrieval pipeline

Every `/api/chat` request:

1. Typo correction + query expansion: single Gemini call at temperature 0.4, returns the corrected query and 3 paraphrased variants
2. Hybrid search for each variant: ChromaDB cosine similarity merged with BM25Okapi at `0.7 x semantic + 0.3 x BM25_normalized`
3. Deduplication across variants: highest score per chunk ID kept
4. Web fallback: if best score is below 0.30, DuckDuckGo search runs instead
5. Metadata boost: chunks from videos whose title and description match the query get +0.20 added to their score
6. Cross-encoder reranking: top 30 candidates through `ms-marco-MiniLM-L-6-v2`, query and chunk seen together as a single input
7. Synthesis: top 8 chunks formatted with title and timestamp, passed to Gemini 2.0 Flash with a strict zero-hallucination system prompt

---

## Deployment

The Pi runs both the FastAPI backend and the Next.js frontend via a single `bash start.sh`, managed by systemd for auto-start on boot. Large runtime files (ChromaDB vectors, SQLite database, BM25 cache, around 3 GB total) sync via rsync from the development machine. Code updates come through git on a dedicated `pi` branch.

nginx reverse-proxies to the local ports. HTTPS comes from Let's Encrypt via a DNS challenge through the DuckDNS API, no public port forwarding needed.

---

## Configuration

| Variable | Default | Required | Description |
|----------|---------|----------|--------------|
| `GCP_PROJECT` | - | yes | GCP project number (digits) |
| `GCP_LOCATION` | `us-central1` | no | Vertex AI region |
| `GEMINI_MODEL` | `gemini-2.0-flash` | no | Gemini model ID |
| `CHROMA_DB_PATH` | `./yc_vectors` | no | Path to ChromaDB directory |
| `CHROMA_COLLECTION` | `transcripts` | no | ChromaDB collection name |
| `SQLITE_DB_PATH` | `./knowledge.db` | no | Path to SQLite database |
| `BM25_CACHE_PATH` | `./bm25_cache.pkl` | no | Path to BM25 pickle cache |
| `CHATS_DB_PATH` | `./chats.db` | no | Path to chat history SQLite |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | no | API base URL used by the frontend |

---

## Active settings (v4.1)

| Setting | Value |
|---------|-------|
| Chunk size | 150 words, 50-word overlap |
| Semantic / BM25 weight | 70% / 30% |
| Metadata boost | +0.20 |
| Cross-encoder model | `ms-marco-MiniLM-L-6-v2` |
| Candidate pool before reranking | top 30 |
| Results passed to Gemini | top 8 |
| Web fallback threshold | score below 0.30 |
| Total corpus | 249,641 chunks, ~5,000 videos, 91 channels |

---

---

# Legacy: MCP Phase (v1.x through v2.7)

> The section below documents the original architecture of the project before v3.0. This is kept for historical context. The MCP server (`yt_knowledge_mcp.py`) still exists in `archive/` but is no longer the primary interface.

---

## What it was

The original version of Sage (before the Meridian rebrand) used Claude Desktop as the interface. An MCP server exposed the knowledge base as three tools that Claude could call during a conversation. The user asked a question, Claude called `yt_search_knowledge_base`, got back ranked transcript excerpts, and synthesized an answer inline.

This worked. The retrieval pipeline was the same 5-stage system that still runs today. The problem was economic: every tool call result persisted in Claude Desktop's context window for the entire conversation. Five searches burned roughly 10,000 tokens that never left context. One deep research session could wipe out a weekly Claude Pro quota.

That's what drove the v3.0 architectural pivot to a dedicated frontend with Gemini handling synthesis instead.

---

## MCP tools

| Tool | Signature | What it did |
|------|-----------|-------------|
| Search | `yt_search_knowledge_base(query, n_results=8)` | Full 5-stage retrieval across all indexed content |
| Deep-dive | `yt_get_video_context(video_title, topic, n_results=5)` | Fetch chunks from a specific video, optionally filtered by topic |
| Browse | `yt_list_videos(channel_filter)` | List all indexed videos with chunk counts and source links |

---

## MCP server setup (archived)

```json
{
  "mcpServers": {
    "yt_knowledge": {
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\yt_knowledge_mcp.py"],
      "env": {
        "CHROMA_DB_PATH": "C:\\path\\to\\yc_vectors",
        "CHROMA_COLLECTION": "transcripts"
      }
    }
  }
}
```

---

## Why it was replaced

Three reasons:

Context window pollution. Tool call results in Claude Desktop persist for the life of the conversation. A research session with 10 searches could burn 20,000+ tokens that were never needed again but couldn't be removed.

Cost at scale. Claude Pro quota limits made heavy usage unsustainable. Gemini 2.0 Flash on Vertex AI costs roughly $0.003 per query, a fraction of the Claude API cost for the same workload, and comes with $300 in free credits.

No UX control. Claude Desktop rendered tool results as raw text. Citation formatting, source cards, timestamp links, streaming, and theme support all required building a proper frontend anyway.

The MCP server still exists in `archive/mcp/` and works against the same ChromaDB and SQLite databases. It can be re-enabled in `claude_desktop_config.json` if needed for a different use case.

---

## Possible future work

These were identified during the MCP phase and never implemented. Some are still relevant to the current architecture.

**Multi-query branching** was flagged as the single highest-impact retrieval improvement. Before hitting ChromaDB, an LLM generates 4 alternative phrasings of the query and runs all of them in parallel, then merges and deduplicates the results. The current implementation already does 3 paraphrases via query expansion; true multi-query branching would score and merge them more aggressively.

**LLM topic tags on ingestion** would extract named concepts and frameworks from each video at embed time and prepend them to every chunk. Makes the embedding richer without changing the retrieval architecture.

**Scheduled auto-sync** via cron or Task Scheduler to run `add-channel` on subscribed channels automatically. New videos indexed without manual steps.

**Knowledge base profiles** to scope search to a subset of channels per user or use case. The UI already has profile management built; the backend scoping is what's missing.

**Telegram bot** to replace the CLI for scraping operations, so `add-channel`, `sync`, and `status` can be triggered remotely without SSH.

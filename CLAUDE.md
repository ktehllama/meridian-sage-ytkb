# Sage — AI Consultant from YouTube Transcripts

## Project Overview
Sage is a system that scrapes YouTube video transcripts (primarily from Y Combinator), stores them in a searchable vector database, and exposes them as an MCP tool inside Claude Desktop. The goal: when working on a complex problem, ask Claude to "use the Sage consultant" and it finds the most relevant video segments with timestamps and citations.

## Architecture

```
YouTube Channel
      ↓
  pipeline.py          ← unified ingestion script (scrape + embed, incremental)
      ↓
  SQLite (knowledge.db)       ← structured storage (channels, videos, transcripts)
      ↓
  ChromaDB (yc_vectors/)      ← vector store (all-MiniLM-L6-v2 embeddings)
      ↓
  yt_knowledge_mcp.py         ← FastMCP server (stdio transport)
      ↓
  Claude Desktop              ← end user interface
```

### pipeline.py (primary script)
Two-layer incremental pipeline — this replaced the legacy `yt_scraper.py` + `vector_builder.py`:
- **Layer 1** (`scrape_channel_to_db`): yt-dlp fetches video list → `youtube-transcript-api` fetches transcripts → stored in SQLite
- **Layer 2** (`embed_new_videos`): reads SQLite, chunks transcripts, adds to ChromaDB — only processes videos not yet embedded
- Incrementality: SQLite tracks `has_transcript` per video; ChromaDB checks existing chunk IDs before embedding

### SQLite Schema
Three tables: `channels`, `videos` (with `has_transcript` flag), `transcripts` (stores `full_text` and `segments` as JSON array of `{text, start, duration}`).

### ChromaDB Chunking
- Chunks ≈ 250 words with 50-word overlap respecting segment boundaries
- Each chunk stored with metadata: `video_id`, `video_title`, `video_url`, `channel_name`, `start_time`, `end_time`, `timestamp_url` (deep link to YouTube timestamp), `chunk_index`
- Chunk IDs: `{video_id}_chunk_{idx:04d}`
- Collection name: `"transcripts"`
- Document format: `"{title}\n\n{chunk_text}"` (title prepended for better semantic matching)

### yt_knowledge_mcp.py (MCP Server)
Exposes 3 tools to Claude Desktop via stdio transport:
- `yt_search_knowledge_base(query, n_results=8)` — semantic search across all videos
- `yt_get_video_context(video_title, topic, n_results=5)` — deep dive into a specific video
- `yt_list_videos(channel_filter)` — list all indexed videos

Config via environment variables: `CHROMA_DB_PATH`, `CHROMA_COLLECTION`.

Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "yt_knowledge": {
      "command": "python",
      "args": ["C:/full/path/to/yt_knowledge_mcp.py"],
      "env": {
        "CHROMA_DB_PATH": "C:/full/path/to/yc_vectors",
        "CHROMA_COLLECTION": "transcripts"
      }
    }
  }
}
```

## Commands

Install dependencies:
```bash
pip install youtube-transcript-api yt-dlp chromadb
# For MCP server:
pip install "mcp[cli]" chromadb sentence-transformers
```

**Use `pipeline.py` for all operations:**
```bash
python pipeline.py add-channel "@ycombinator"             # scrape + embed (incremental)
python pipeline.py add-channel "@ycombinator" --limit 10  # test with 10 videos
python pipeline.py sync                                   # embed anything in SQLite missing from Chroma
python pipeline.py status                                 # show DB and vector DB stats
python pipeline.py rebuild                                # wipe and re-embed everything
python pipeline.py search "how to find product market fit"
```

Key CLI flags for `add-channel`:
- `--db` / `--vectors` — override default paths
- `--min-duration` / `--max-duration` — filter by seconds (default: 300–7200)
- `--skip-keywords` — comma-separated title keywords to skip (default: "shorts")
- `--delay` — seconds between transcript fetches (default: 1.0)

## Current Status — Phase 5 Complete ✅
- Unified pipeline working with full incremental processing
- Filtering: skips shorts (<5 min), livestreams (>2 hours), keyword exclusions
- MCP server integrated and working in Claude Desktop
- ChromaDB embedding function consistency resolved

## Phase 6 — Retrieval Quality Improvements (In Progress)
The core problem: semantically similar results don't always surface the most relevant video. A video could be *exactly* about the topic but rank low due to word mismatch between the query and transcript language.

### Planned improvements (priority order):
1. **Multi-query branching** — generate 3-5 paraphrased query variants, run all, merge + deduplicate results
2. **Finer chunking** — reduce from ~250 to ~150-200 words with sliding window overlap
3. **Hybrid search (BM25 + semantic)** — combine keyword matching with cosine similarity for exact-term recall
4. **LLM-generated topic tags** — one-time Claude pass on ingestion to extract key concepts, frameworks, named topics as searchable metadata
5. **Cross-encoder re-ranking** — retrieve top 30 candidates via fast semantic search, re-rank with `cross-encoder/ms-marco-MiniLM-L-6-v2` for precision
6. **Video-level metadata embedding** — separate index for video titles + descriptions to catch broad topic matches

## Important Technical Notes
- **`youtube-transcript-api` v1.x** changed from static methods to instance methods — must instantiate `YouTubeTranscriptApi()` and call `.list()` / `.fetch()` as instance methods. Old static API no longer works.
- **ChromaDB embedding consistency**: embedding function must be identical between collection creation and retrieval. Collections created without an explicit embedding function store as "default" internally — accessing them later with explicit params causes conflicts.
- **MCP "no tools available" errors** usually mean the server crashed on startup, not a config issue. Check that sentence-transformer models are pre-cached to prevent download hangs during MCP init.
- **IP blocking**: YouTube scraping uses mobile hotspot + airplane mode IP rotation. If interrupted mid-run, use `pipeline.py sync` to pick up where it left off rather than re-running `add-channel`.
- The legacy scripts (`yt_scraper.py`, `vector_builder.py`) are superseded by `pipeline.py`. `vector_builder.py` wipes and rebuilds the entire vector DB each run — do not use it.

## Primary Knowledge Source
YouTube channel: Y Combinator (@ycombinator)
Focus: startup advice, fundraising, product-market fit, founder stories, B2B sales, hiring
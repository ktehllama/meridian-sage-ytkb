# Meridian Sage

<!-- intro goes here -->

---

## Architecture

```
YouTube
   ↓
pipeline.py          scrape + embed (yt-dlp, youtube-transcript-api)
   ↓           ↓
knowledge.db   yc_vectors/          SQLite + ChromaDB (generated, not in repo)
                   ↓
            bm25_cache.pkl          BM25 index built on first API start (generated)
                   ↓
             api/  (FastAPI)        hybrid search + Gemini synthesis
                   ↓
           sage_chat/ (Next.js)     chat UI
```

**`pipeline.py`**: two-layer ingestion. Layer 1 scrapes YouTube channels into SQLite (`knowledge.db`). Layer 2 chunks transcripts and embeds them into ChromaDB (`yc_vectors/`). Incremental; already-processed videos are skipped.

**`api/`**: FastAPI on port 8000. Connects to ChromaDB on startup and builds a BM25 index in a background thread (cached to `bm25_cache.pkl`). Every `/api/chat` request runs query expansion -> hybrid search -> optional web fallback -> Gemini synthesis.

**`sage_chat/`**: Next.js 14 on port 3000. Renders markdown with citation superscripts, persists chat history to the API.

**`meridian_sdk/`**: standalone Python client, no API server needed. Runs hybrid search + synthesis directly against the local DBs.

---

## Tech Stack

| Component | Library | Version |
|-----------|---------|---------|
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) | 5.2.3 |
| Vector store | `chromadb` (embedded, no server) | 1.5.2 |
| Keyword search | `rank_bm25` (BM25Okapi) | 0.2.2 |
| LLM | Vertex AI Gemini via `google-genai` | 1.66.0 |
| Gemini model | `gemini-2.0-flash` | - |
| YouTube scraping | `yt-dlp` | 2026.2.21 |
| Transcript fetch | `youtube-transcript-api` | 1.2.4 |
| API framework | `fastapi` + `uvicorn` | 0.135.1 / 0.41.0 |
| Frontend | Next.js + React + Tailwind | 14.2.3 / 18 / 3 |
| Web search fallback | `duckduckgo-search` | - |
| Auth | Google Application Default Credentials | no key file |

---

## Generated Files (not in repo)

Created at runtime. Point `api/.env` and `start.sh` at their paths.

| File | Created by | Contents |
|------|-----------|----------|
| `knowledge.db` | `pipeline.py` | SQLite: channels, videos, transcripts, queue |
| `yc_vectors/` | `pipeline.py` | ChromaDB persistent store (two collections) |
| `bm25_cache.pkl` | `api/search.py` | Serialized BM25Okapi index + chunk IDs |
| `chats.db` | `api/chat_db.py` | Saved chat history |

---

## Search Pipeline

Every `/api/chat` request:

1. **Query expansion**: Gemini generates 3 paraphrased variants of the query (`temperature=0.4`, `max_tokens=200`)
2. **Hybrid search**: for each variant, ChromaDB returns top candidates (cosine similarity) and BM25Okapi scores the same candidates on keyword overlap
3. **Score merge**: `score = 0.7 * semantic + 0.3 * BM25_normalized`; results across all variants are deduplicated by `chunk_id`, keeping the highest score
4. **Web fallback**: if the top result scores below `0.30`, DuckDuckGo search runs and results are injected with a fixed score of `0.25`
5. **Synthesis**: top 8 chunks passed to Gemini with `[SRC_N]` citation markers; model required to cite every factual claim
6. **Response**: answer string + structured source list (`src_id`, `title`, `timestamp_str`, `url`, `quote`)

---

## Chunking

- 150 words, 50-word sliding overlap, segment boundaries respected
- Chunk ID: `{video_id}_chunk_{idx:04d}` (e.g. `dQw4w9WgXcQ_chunk_0003`)
- Stored as `"{title}\n\n{chunk_text}"` (title prepended before embedding)
- Two collections:
  - `transcripts`: one doc per chunk
  - `video_metadata`: one doc per video (`title + description`), for title-level matching

---

## Installation

**Clone and install:**

```bash
git clone https://github.com/ktehllama/meridian-sage-ytkb.git
cd meridian-sage-ytkb
pip install -r requirements.txt
```

**Authenticate with GCP** (uses ADC, no API key file):

```bash
gcloud auth application-default login
```

**Scrape a channel** (creates `knowledge.db` and `yc_vectors/`):

```bash
python pipeline.py add-channel @ycombinator
```

**Configure the API:**

```bash
cp api/.env.example api/.env
# set GCP_PROJECT, verify paths
```

**Start:**

```bash
# both API and frontend:
./start.sh          # production
./start.sh --dev    # development

# or separately:
uvicorn api.main:app --port 8000
cd sage_chat && npm install && npm run dev
```

Frontend: `http://localhost:3000` / API: `http://localhost:8000`

---

## pipeline.py CLI

```
python pipeline.py [--db PATH] [--vectors PATH] <command> [flags]
```

| Command | Description |
|---------|-------------|
| `add-channel @handle` | Scrape + embed a channel (incremental) |
| `add-from-csv path.csv` | Scrape specific videos listed in a CSV |
| `queue add @handle` | Add a channel to the processing queue |
| `queue run` | Process all pending queue entries |
| `queue status` | Show queue state (pending / done / paused / failed) |
| `queue reset` | Mark paused/failed entries as pending |
| `queue remove` | Delete queue entries by id, channel, or status |
| `sync` | Embed any SQLite videos missing from ChromaDB |
| `status` | Print stats for both SQLite and ChromaDB |
| `rebuild` | Wipe ChromaDB and re-embed everything from SQLite |
| `rechunk` | Same as rebuild, use after changing chunk size |
| `search "query"` | Raw semantic search (no BM25, no synthesis) |

### `add-channel` flags

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | none | Max videos to scrape |
| `--delay FLOAT` | `1.0` | Seconds between transcript requests |
| `--min-duration SEC` | `300` | Skip videos shorter than this |
| `--max-duration SEC` | `7200` | Skip videos longer than this |
| `--skip-keywords "a,b"` | `"shorts"` | Skip videos matching these title keywords |
| `--sort-by date\|views` | `date` | Order videos are fetched |
| `--whitelist path.csv` | none | Only scrape video IDs listed in this file |

### `search` flags

| Flag | Default | Description |
|------|---------|-------------|
| `--top N` | `5` | Number of results to return |

---

## API Endpoints

| Method | Path | Request body | Response |
|--------|------|-------------|----------|
| `POST` | `/api/chat` | `{query, mode, history}` | `{answer, sources, mode, usage}` |
| `GET` | `/api/videos` | `?channel=&limit=&offset=` | `{videos, total}` |
| `GET` | `/api/channels` | - | `{channels: [{name, video_count}]}` |
| `GET` | `/api/random-fact` | - | `{title, channel, excerpt, timestamp_str, url}` |
| `GET` | `/api/health` | - | `{status, chroma_chunks, db_videos, model}` |
| `GET` | `/api/chats` | - | list of stored chats |
| `POST` | `/api/chats` | `{id, name, mode, messages, saved_at}` | 204 |
| `DELETE` | `/api/chats/{id}` | - | 204 |
| `PATCH` | `/api/chats/{id}` | `{name}` | 204 |
| `GET` | `/api/budget` | - | `{spent, cap}` |
| `PUT` | `/api/budget` | `{spent?, cap?}` | 204 |

`mode` in `/api/chat`: `"ephemeral"` (stateless) or `"conversation"` (uses `history` array).

---

## Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `GCP_PROJECT` | - | yes | GCP project number (digits) |
| `GCP_LOCATION` | `us-central1` | no | Vertex AI region |
| `GEMINI_MODEL` | `gemini-2.0-flash` | no | Gemini model ID |
| `CHROMA_DB_PATH` | `./yc_vectors` | no | Path to ChromaDB directory |
| `CHROMA_COLLECTION` | `transcripts` | no | ChromaDB collection name |
| `SQLITE_DB_PATH` | `./knowledge.db` | no | Path to SQLite database |
| `BM25_CACHE_PATH` | `./bm25_cache.pkl` | no | Path to BM25 pickle cache |
| `CHATS_DB_PATH` | `./chats.db` | no | Path to chat history SQLite |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | no | API base URL (frontend) |

---

## SQLite Schema

```sql
CREATE TABLE channels (
    id       INTEGER PRIMARY KEY,
    handle   TEXT UNIQUE,
    name     TEXT,
    url      TEXT,
    scraped_at TEXT
);

CREATE TABLE videos (
    id             TEXT PRIMARY KEY,
    channel_handle TEXT,
    title          TEXT,
    description    TEXT,
    published_at   TEXT,
    duration       INTEGER,
    view_count     INTEGER,
    url            TEXT,
    has_transcript INTEGER DEFAULT 0,
    scraped_at     TEXT
);

CREATE TABLE transcripts (
    id           INTEGER PRIMARY KEY,
    video_id     TEXT UNIQUE,
    full_text    TEXT,
    segments     TEXT,   -- JSON array of {text, start, duration}
    language     TEXT,
    is_generated INTEGER,
    created_at   TEXT
);

CREATE TABLE channel_queue (
    id             INTEGER PRIMARY KEY,
    channel        TEXT,
    limit_count    INTEGER,
    sort_by        TEXT,
    min_duration   INTEGER,
    max_duration   INTEGER,
    skip_keywords  TEXT,
    whitelist_csv  TEXT,
    status         TEXT,   -- pending | running | done | paused | failed
    queued_at      TEXT,
    started_at     TEXT,
    finished_at    TEXT,
    error_msg      TEXT,
    videos_scraped  INTEGER DEFAULT 0,
    videos_success  INTEGER DEFAULT 0,
    videos_no_trans INTEGER DEFAULT 0,
    chunks_added    INTEGER DEFAULT 0
);
```

---

## Meridian SDK

No API server needed, hits the local DBs directly.

```python
from meridian_sdk import Meridian

m = Meridian(gcp_project="your-project-number")
print(m.search("how to talk to users", mode="chat"))
```

Modes: `"chat"`, `"serious"` (terse), `"raw"` (chunk dicts, no LLM). See `meridian_sdk/example.py`.

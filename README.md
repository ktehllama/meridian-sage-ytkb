<div align="center">

<img src="docs/meridian-logo.svg" width="80" alt="Meridian">

# Meridian Sage

### Your personal AI consultant, grounded entirely in what experts actually said.

*249,641 transcript chunks · 91 curated channels · 15 topic domains · zero hallucinations*

<br>

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js_14-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6B35?style=flat-square&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_2.0_Flash-4285F4?style=flat-square&logo=google&logoColor=white)
![Raspberry Pi](https://img.shields.io/badge/Raspberry_Pi-A22846?style=flat-square&logo=raspberrypi&logoColor=white)
![License](https://img.shields.io/badge/license-Apache_2.0-blue?style=flat-square)

<br>

<!-- [SCREENSHOT: full browser in dark mode — sidebar with smart chat names like "YC Pricing B2B SaaS" visible, main panel showing a complete answer with [SRC_1] [SRC_2] [SRC_3] inline superscripts, source cards expanded below each showing video title, channel name, clickable timestamp, relevance score, 2-line quote] -->

</div>

---

## The problem

Picture a gigantic library with books covering every subject you care about: investing, science, business, psychology, history, philosophy. You want to know the best way to make a beef wellington. Without a librarian who has read everything, you are on your own — every page, every book, compiled by hand.

That's YouTube. Thousands of hours of lectures, interviews, and talks from some of the most qualified people alive, locked in a format you can't search or query on demand. You watch something useful on a Tuesday, forget it by Thursday, and there's no way to get it back. The knowledge exists. It's just completely inaccessible when you actually need it.

Meridian fixes that. It scrapes, indexes, and makes the content of 91 expert YouTube channels queryable through a chat interface. It's actively used in production, not a demo.

---

## What it does

Ask a question in plain English. Meridian runs it against 249,641 indexed transcript chunks from channels across AI, business, investing, science, health, history, philosophy and more. The top results, ranked by a 7-stage retrieval pipeline, go to Gemini 2.0 Flash, which writes a direct answer in prose.

Every factual claim in the response is backed by a `[SRC]` citation linking to the exact second in the source video where it was said. Not a summary. The actual moment, timestamped, clickable.

Type "claude coed" instead of "claude code" and it corrects the typo before searching. Not sure how to phrase something? Meridian silently generates 3 paraphrased variants of your query and merges the results, so vocabulary gaps between how you ask and how an expert said the answer three years ago don't cost you anything. If the knowledge base genuinely has nothing, it falls back to a live DuckDuckGo web search automatically. No dead ends.

<!-- [SCREENSHOT: close-up of a single answer — prose text with [SRC_2] superscript visible mid-sentence, source card expanded below showing channel name, video title, "4:32" as a clickable YouTube deep-link, relevance percentage, 2-line transcript excerpt] -->

---

## Why not just ask ChatGPT

General AI models hallucinate. Ask ChatGPT what a YC partner said about pricing in 2022 and it guesses — confidently, fluently, incorrectly. It doesn't have context from 5,000 specific videos. It has fuzzy training knowledge and whatever it can scrape in real time.

Meridian runs on a zero-hallucination protocol. Every answer must cite exactly where its information comes from before it gets returned. The sources are 91 hand-curated channels chosen for depth and credibility, not the open internet or model weights. If a high-confidence source doesn't exist in the knowledge base, Meridian says so instead of making something up.

ChatGPT gives you a city block. Meridian gives you the exact address.

---

## The library

91 channels picked for quality, not quantity. No entertainment, no reaction content — pure expertise.

| Domain | Channels |
|--------|----------|
| AI / Tech | @ycombinator, @AndrejKarpathy, @lexfridman, @3blue1brown, @Computerphile, @geohotarchive, @YannicKilcher + more |
| Business / Entrepreneurship | @AcquiredFM, @DavidSenra, @a16z, @GarryTan, @MyFirstMillionPod, @HarvardBusinessReview + more |
| Investing / Finance | @PBoyle, @aswathdamodaranonvaluation, @ThePlainBagel, @EconomicsExplained + more |
| Science | @veritasium, @kurzgesagt, @pbsspacetime, @RealEngineering, @Fermilab + more |
| Psychology / Behavior | @JordanBPeterson, @hubermanlab, @modernwisdompodcast, @bigthink + more |
| Health / Longevity | @PeterAttiaMD, @JeffNippard, @FoundMyFitness, @BryanJohnson + more |
| History / Geopolitics | @WendoverProductions, @CaspianReport, @KingsandGenerals, @fallofcivilizations + more |
| Philosophy | @einzelganger, @academyofideas, @philosophizethis, @TheSchoolofLife + more |
| + 7 more domains | Sales, Product, Leadership, Law, Real Estate, Communication, Productivity |

<!-- [SCREENSHOT: Channels tab in the sidebar — category filter pills across the top (AI/Tech, Business, Investing, etc.), channel list below with handles and video counts] -->

---

## How the retrieval works

A query doesn't get thrown at a search index. It runs through 7 stages before Gemini sees anything.

**Stage 0.** A single Gemini call at temperature 0.4 corrects typos and generates 3 paraphrased variants. "What makes a good cofounder" becomes 4 distinct queries. This closes the vocabulary gap between how you ask and how someone actually answered on camera.

**Stage 1.** Each variant runs two searches at once: ChromaDB cosine similarity for semantic meaning, and BM25Okapi for exact keyword matching. Semantic search alone breaks on proper nouns and specific terms. "Sequoia RFS 2024" has no meaningful embedding neighbors — BM25 matches the tokens directly. Scores combine at `0.7 × semantic + 0.3 × BM25_normalized`.

**Stage 2.** Results from all 4 variants merge into one ranked list. Highest score per chunk wins, duplicates dropped.

**Stage 3.** If the best score sits below 0.30, the knowledge base doesn't have a confident answer. Meridian falls back to DuckDuckGo automatically, same format, same citation style.

**Stage 4.** A separate ChromaDB collection — one document per video — gets queried independently. Chunks from videos whose title and description strongly match the query get a +0.20 score boost. This recovers relevant content buried deep in a matching video that chunk-level search would have missed.

**Stage 5.** The top 30 candidates go through `ms-marco-MiniLM-L-6-v2`, a cross-encoder. Earlier stages compared query and chunks as separate vectors. The cross-encoder sees both as a single input, which produces a far sharper relevance signal. It only runs on 30 candidates because it's slow, but it's the stage that makes the final ranking trustworthy.

**Stage 6.** Top 8 re-ranked chunks, formatted with title and timestamp, go to Gemini 2.0 Flash with one hard rule: every factual claim cites `[SRC_N]`, no exceptions, no training knowledge used. The response streams back to the frontend with citations rendered as superscripts, each one a direct link to the exact YouTube second.

---

## Problems worth talking about

**YouTube blocks you at scale.** The transcript API rate-limits aggressively by IP. Indexing 91 channels meant scraping tens of thousands of videos across weeks. The solution was to decouple scraping from embedding entirely. Scraping runs from a mobile hotspot with IP rotation between sessions; embedding, which never touches YouTube, runs separately from a stable connection afterward. Both layers are fully incremental — SQLite commits after every single video, ChromaDB checks existing chunk IDs before embedding. An interrupted run loses nothing.

**Semantic search isn't enough on its own.** The first version used pure cosine similarity and failed in ways that were obvious in practice: "letting someone go" didn't surface chunks about "firing employees," proper nouns had no embedding neighbors, and relevant videos ranked low because one keyword didn't exist in the vector space. Each layer of the retrieval pipeline was added to fix a specific failure observed in real queries. BM25 for exact token matching. Metadata boosting for video-level relevance. The cross-encoder as the final precision pass. None of these were planned up front.

**The original architecture was destroying the budget.** The first version ran through Claude Desktop via an MCP server. Every tool call result persisted in the context window for the entire conversation. Five searches burned roughly 10,000 tokens permanently. One deep research session could wipe out a week's Claude Pro quota.

The fix was cutting Claude out of the retrieval loop entirely. Gemini 2.0 Flash replaced it on Vertex AI — not because of brand preference, but because it's a lightweight model built specifically for parsing structured retrieved data and writing coherent prose from it. It's faster, cheaper, and genuinely better at this task than a general-purpose model. Cost per query dropped to about $0.003. A purpose-built Next.js frontend replaced Claude Desktop, giving full control over the pipeline, the citation format, and the UX.

<!-- [SCREENSHOT: hero screen — animated WebGL background, Meridian globe logo in the top bar, suggestion cards showing, floating glassmorphism input bar at the bottom] -->

---

## Stack

| Layer | Technology |
|-------|-----------|
| Scraping | `yt-dlp` + `youtube-transcript-api` v1.x |
| Structured storage | SQLite (`knowledge.db`) |
| Vector storage | ChromaDB (`yc_vectors/`) |
| Embeddings | `all-MiniLM-L6-v2` via sentence-transformers |
| Keyword search | `rank_bm25` BM25Okapi |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Web fallback | DuckDuckGo (`duckduckgo-search`, no API key) |
| Backend | FastAPI + Uvicorn |
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| LLM synthesis | Gemini 2.0 Flash via Vertex AI |
| Chat persistence | SQLite (`chats.db`) |
| Deployment | Raspberry Pi 4, systemd, nginx, Let's Encrypt, DuckDNS |

---

## Running locally

Prerequisites: Python 3.11+, Node.js 18+, a Vertex AI project with Gemini enabled, `gcloud auth application-default login` run once.

```bash
git clone https://github.com/ktehllama/meridian-sage-ytkb.git
cd meridian-sage-ytkb

# Python environment
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd sage_chat && npm install && cd ..

# Configure
cp api/.env.example api/.env
# Fill in GCP_PROJECT and GCP_LOCATION in api/.env

# Start both FastAPI (:8000) and Next.js (:3000)
bash start.sh
```

Open `http://localhost:3000`.

To build your own knowledge base:

```bash
# Add a channel and index it
python pipeline.py add-channel "@ycombinator"

# Scrape only — useful when rotating IPs
python pipeline.py add-channel "@ycombinator" --scrape-only

# Embed everything scraped but not yet indexed
python pipeline.py sync

# Check corpus state
python pipeline.py status
```

The large runtime files (`yc_vectors/`, `knowledge.db`, `bm25_cache.pkl`, around 3 GB total) are excluded from the repo. Full pipeline reference in [`docs/MANUAL.md`](docs/MANUAL.md).

---

## Docs

Full CLI reference and pipeline flags: [`docs/MANUAL.md`](docs/MANUAL.md)

Architecture, configuration, and design decisions: [`docs/OVERVIEW.md`](docs/OVERVIEW.md)

---

<!-- [SCREENSHOT: light mode — warm Solarized cream background, same interface with an answer and citations visible] -->















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

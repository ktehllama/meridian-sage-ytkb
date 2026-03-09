# ADR: Sage Chat — Architecture Decision Record
**Status**: READY_FOR_BUILD
**Date**: 2026-03-06
**Author**: architect agent

---

## 1. Backend Module Structure (`api/`)

### Files and Responsibilities

```
api/
  config.py          — env var loading (all config in one place, no magic strings elsewhere)
  models.py          — Pydantic request/response models (single source of truth for API shapes)
  search.py          — hybrid search engine (ChromaDB semantic + BM25 keyword, fully self-contained)
  gemini.py          — Vertex AI client: query expansion + grounded synthesis
  main.py            — FastAPI app: route handlers, CORS, lifespan startup
  requirements.txt   — pinned dependencies
  .env.example       — documented env var template
```

### Dependency Graph (import order, no cycles)
```
config.py   ← (no internal imports)
models.py   ← (no internal imports)
search.py   ← config
gemini.py   ← config, models
main.py     ← config, models, search, gemini
```

---

## 2. API Contract

### POST /api/chat
**Request**:
```json
{
  "query": "How do early-stage startups find their first customers?",
  "mode": "ephemeral",
  "history": [
    {"role": "user", "content": "previous message"},
    {"role": "assistant", "content": "previous answer"}
  ]
}
```
- `mode`: `"ephemeral"` | `"conversation"`
- `history`: empty array `[]` for ephemeral mode (or populated for conversation — backend enforces which to use)

**Response**:
```json
{
  "answer": "According to [SRC_1] and [SRC_3], early-stage founders...",
  "sources": [
    {
      "src_id": "SRC_1",
      "title": "How to Get Your First Customers",
      "timestamp_str": "12:34",
      "url": "https://www.youtube.com/watch?v=abc123&t=754s",
      "quote": "the first 10 customers should come from..."
    }
  ],
  "mode": "ephemeral"
}
```

### GET /api/videos
**Query params**: `channel` (optional, partial match), `limit` (default 50), `offset` (default 0)
**Response**:
```json
{
  "videos": [
    {
      "id": "abc123",
      "title": "How to Get Your First Customers",
      "channel": "@ycombinator",
      "url": "https://www.youtube.com/watch?v=abc123",
      "duration": 1842
    }
  ],
  "total": 847
}
```

### GET /api/channels
**Response**:
```json
{
  "channels": [
    {"name": "@ycombinator", "video_count": 412},
    {"name": "@lexfridman", "video_count": 201}
  ]
}
```

### GET /api/health
**Response**:
```json
{
  "status": "ok",
  "chroma_chunks": 249853,
  "db_videos": 613
}
```
Returns HTTP 503 if ChromaDB is unavailable (status: "degraded").

---

## 3. Query Pipeline

Each POST /api/chat request follows this pipeline:

```
1. EXPAND: gemini.expand_query(query) → ["original", "variant1", "variant2", "variant3"]
   - Single Gemini call, max_output_tokens=150, returns 3-4 paraphrases + original
   - On Gemini failure: fall back to [query] only (graceful degradation)

2. SEARCH: For each variant, run search.hybrid_search(variant, n_results=20)
   - Semantic: ChromaDB query with SentenceTransformerEmbeddingFunction
   - BM25: rank_bm25 index built from SQLite transcripts.full_text at startup
   - Merge all variant results, deduplicate by chunk_id (keep highest score)

3. RANK: score = 0.7 * semantic_score + 0.3 * bm25_norm
   - semantic_score: max(0, 1 - distance/2) from ChromaDB cosine distance
   - bm25_norm: normalized BM25 score [0,1] over the candidate set
   - Sort descending, take top 8

4. FORMAT: For each top chunk, build source entry:
   - src_id: "SRC_1", "SRC_2", ...
   - chunk_text formatted as: '[SRC_N] Video Title — MM:SS\n"chunk text here"'

5. SYNTHESIZE: gemini.synthesize(query, chunks, history, mode)
   - System prompt enforces [SRC_N] citation
   - history passed only if mode == "conversation"
   - Returns answer string

6. PARSE SOURCES: Extract src_id, title, timestamp_str, url, quote from formatted chunks
   Return ChatResponse(answer, sources, mode)
```

### Semantic Score Normalization
ChromaDB returns L2 distances. Convert to similarity: `sem_score = max(0, 1 - distance/2)`.
For cosine distance (range 0-2), this maps perfectly to [0,1].

### BM25 Normalization
After collecting all candidates: `bm25_norm = (score - min) / (max - min)` — avoids unbounded BM25 scores dominating.

---

## 4. Frontend Architecture

### Next.js App Router Structure
```
sage_chat/
  app/
    layout.tsx          — root layout (dark theme, font, metadata)
    page.tsx            — imports ChatInterface, full-page layout
    globals.css         — Tailwind base + custom CSS variables
  components/
    ChatInterface.tsx   — top-level state manager (messages, mode, loading)
    MessageList.tsx     — scrollable message container, auto-scroll ref
    MessageBubble.tsx   — renders user/assistant bubble; [SRC_N] → clickable spans
    SourceCards.tsx     — horizontal scroll row of source cards below assistant messages
    ModeToggle.tsx      — ephemeral (lightning) vs conversation (brain) pill toggle
    ChatInput.tsx       — textarea + send button, Enter/Ctrl+Enter submit
    Sidebar.tsx         — collapsible drawer, video/channel browser
    TypingIndicator.tsx — three-dot bounce animation
  lib/
    api.ts              — typed fetch functions: chat(), getVideos(), getChannels(), getHealth()
  public/
    favicon.ico
  package.json
  next.config.js
  tailwind.config.js
  tsconfig.json
  .env.example
  .env.local            — (gitignored) NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Component Hierarchy
```
page.tsx
└── ChatInterface.tsx  [state: messages[], mode, loading, sidebarOpen]
    ├── Sidebar.tsx    [state: videos[], channels[], filter]
    ├── ModeToggle.tsx [reads mode, emits onModeChange]
    ├── MessageList.tsx [reads messages]
    │   └── MessageBubble.tsx (per message)
    │       └── SourceCards.tsx (if assistant + has sources)
    ├── TypingIndicator.tsx (shown when loading=true)
    └── ChatInput.tsx  [emits onSubmit(text)]
```

### State Management
- Single `useReducer` in `ChatInterface.tsx` — no external library
- State shape:
  ```typescript
  type State = {
    messages: Array<{role: 'user'|'assistant', content: string, sources?: Source[]}>;
    mode: 'ephemeral' | 'conversation';
    loading: boolean;
    sidebarOpen: boolean;
    error: string | null;
  }
  ```
- On mode switch: dispatch `CLEAR_CHAT` action (clears messages array)
- Ephemeral: `history` sent as `[]` in API call
- Conversation: `history` built from `messages` array

### Fake Streaming (Word Reveal)
When assistant response arrives:
1. Set `loading = false`, add message with `content = ""`
2. Split `answer` by spaces → word array
3. Use `setInterval` (30ms per word) to append words one by one
4. Clear interval when all words revealed

### Citation Rendering in MessageBubble
Regex: `/\[SRC_(\d+)\]/g` → replace with `<button>` that opens `sources[n-1].url` in new tab.
Render assistant content as parsed React nodes (not dangerouslySetInnerHTML).

---

## 5. Hybrid Search Port (from yt_knowledge_mcp.py)

### Why Copy Inline (not import)
`yt_knowledge_mcp.py` starts a background thread at module level to load cross-encoder and build BM25. Importing it as a module would trigger those side effects (thread spawning, file system access, model download) even if only using one function. The search.py module copies the relevant logic clean.

### What to Copy
From `yt_knowledge_mcp.py`:
- ChromaDB connection pattern with lazy init
- BM25 index build from ChromaDB documents (not SQLite — simpler)
- Semantic search + BM25 merge logic
- Score normalization math

### What to Change / Simplify for FastAPI
- **No cross-encoder** (Phase 6 feature, not MVP)
- **No video metadata boost** (extra collection, not required)
- **No background thread for BM25** — build synchronously on FastAPI startup (lifespan event)
  - Startup blocks until BM25 is ready, then requests are served
  - Acceptable because FastAPI won't accept requests during startup anyway
- **No pickle cache** — in-memory only (cache invalidates on restart which is fine)
- **Use SQLite for BM25 corpus** — `SELECT full_text FROM transcripts` is cleaner than pulling all docs from ChromaDB

### search.py Key Design
```python
# Module-level singletons (initialized in init_search() called from FastAPI lifespan)
_collection: chromadb.Collection = None
_bm25_index: BM25Okapi = None
_bm25_chunk_ids: list[str] = None  # parallel list for score lookup

def init_search():
    """Called once at FastAPI startup. Blocks until ready."""
    # 1. Connect ChromaDB with SentenceTransformerEmbeddingFunction
    # 2. Build BM25 from SQLite transcripts.full_text
    #    - fetch all (video_id, full_text) from transcripts
    #    - tokenize, build BM25Okapi
    #    - _bm25_chunk_ids stores video_ids for score correlation

def hybrid_search(query: str, n_results: int = 8) -> list[dict]:
    """Returns list of result dicts, sorted by combined score descending."""
    # Returns: [{chunk_id, title, text, start_time, timestamp_url, score}, ...]
```

### BM25 Corpus Source Decision
Using SQLite `transcripts.full_text` (whole transcript per video) for BM25 instead of ChromaDB chunks:
- Simpler: one row per video, no pagination across 250K chunks
- BM25 operates on full documents → chunk results then correlated by video_id
- Trade-off: BM25 score is at video level, not chunk level — acceptable for MVP

Actually, **revised**: BM25 should operate on chunks for better precision. Pull chunk documents from ChromaDB in batches at startup. This matches the MCP server pattern and gives chunk-level BM25 scores that can be directly merged with semantic chunk scores.

---

## 6. Vertex AI Client Pattern (from APIgeminiai.py)

```python
# api/gemini.py
from google import genai
from api.config import config

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=config.GCP_PROJECT,
            location=config.GCP_LOCATION
        )
    return _client
```

### expand_query
```python
async def expand_query(query: str) -> list[str]:
    prompt = f"""Generate 3 paraphrased versions of this search query.
Return ONLY the paraphrases, one per line, no numbering, no explanation.
Original: {query}"""
    response = get_client().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config={"max_output_tokens": 150, "temperature": 0.7}
    )
    variants = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    return [query] + variants[:3]  # always include original, cap at 3 variants
```

### synthesize
```python
async def synthesize(query: str, chunks: list[dict], history: list[Message], mode: str) -> str:
    system_prompt = """You are Sage, a knowledge assistant built on a curated video library.
RULES:
- Every factual claim MUST cite at least one source using [SRC_N] notation
- If no sources support a claim, say "I don't have sources on this"
- Never invent quotes, timestamps, or video titles
- Synthesize and connect ideas across sources — don't just summarize each chunk
- For comparisons, structure your answer with clear sections per perspective"""

    # Format chunks as grounding context
    formatted_chunks = "\n\n".join(
        f'[SRC_{i+1}] {c["title"]} — {c["timestamp_str"]}\n"{c["text"]}"'
        for i, c in enumerate(chunks)
    )

    # Build contents list
    contents = []
    if mode == "conversation":
        for msg in history:
            contents.append({"role": msg.role, "parts": [{"text": msg.content}]})

    user_message = f"""Sources:\n{formatted_chunks}\n\nQuestion: {query}"""
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    response = get_client().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=contents,
        config={"system_instruction": system_prompt, "max_output_tokens": 1024}
    )
    return response.text
```

---

## 7. Key Constraints Summary

| Constraint | Decision |
|---|---|
| ChromaDB + SQLite | READ ONLY — no writes from api/ |
| BM25 library | `rank_bm25` (already in venv from MCP server) |
| Embedding function | `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")` |
| Vertex AI auth | ADC — `genai.Client(vertexai=True, ...)` reads credentials from environment |
| No import of MCP server | Copy search logic inline into search.py |
| No AI in tests | Mock/stub any Gemini calls in test files |
| Frontend API URL | `NEXT_PUBLIC_API_URL` env var, default `http://localhost:8000` |
| CORS origins | `http://localhost:3000` and `https://*.vercel.app` |
| Ephemeral mode | history=[] sent to API; backend passes empty history to Gemini |
| Conversation mode | full message history passed to Gemini in contents array |

---

## 8. Open Questions Resolved

- **BM25 library**: Use `rank_bm25` (already installed, confirmed in yt_knowledge_mcp.py imports)
- **Fake streaming**: Word-by-word reveal with `setInterval(30ms)` on frontend
- **CORS**: Configured in FastAPI with `CORSMiddleware` for localhost:3000 + *.vercel.app
- **BM25 corpus**: Pull from ChromaDB chunks at startup (chunk-level precision)
- **Startup blocking**: BM25 build is synchronous in FastAPI lifespan — acceptable (250K chunks ~30s on first run without cache)

---

*PRD Status: READY_FOR_BUILD*

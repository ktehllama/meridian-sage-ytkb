# Meridian YTKB — Complete Development History
*Every session, every decision, every bug, every fix — from first commit to v4.0 stable.*
*Written to give a new Claude session complete context. Read top to bottom.*

---

## The Original Vision

The project started as a personal productivity tool. The user's (YOUR_USERNAME) dad watches enormous amounts of YouTube content — Y Combinator talks and more. The core insight: hours of watched content go to waste because the knowledge isn't searchable. You hear something good, you forget it, you can't find it again.

The first goal was simple: scrape transcripts from YouTube channels, chunk them into searchable segments, embed them into a vector database, and surface them on demand. The delivery mechanism was Claude Desktop + an MCP server — you could ask Claude to "consult the knowledge base" and it would run semantic search and return the most relevant video segments with timestamps.

---

## Part 1 — The Pipeline Era (v1.x)

### What was built

**`pipeline.py`** — a unified ingestion script replacing two earlier separate scripts (`yt_scraper.py` for scraping and `vector_builder.py` for embedding). The reason for unification: the two-script approach meant running them separately, and `vector_builder.py` in particular did a full wipe-and-rebuild of ChromaDB on every run, which was catastrophically slow and destructive as the dataset grew.

The new unified pipeline is two-layer and fully incremental:

- **Layer 1** (`scrape_channel_to_db`): `yt-dlp` fetches the full video list from a channel → `youtube-transcript-api` fetches transcripts for each video → stored in SQLite. The `has_transcript` flag in the `videos` table tracks what's been fetched. If you re-run, only new videos are fetched.

- **Layer 2** (`embed_new_videos`): reads SQLite, finds videos with `has_transcript=1` that don't yet exist in ChromaDB (checked by chunk ID pattern `{video_id}_chunk_0000`), chunks the transcript text, embeds and stores in ChromaDB. Completely safe to re-run.

**Important note on `youtube-transcript-api`**: version 1.x changed from static methods to instance methods. The old API was `YouTubeTranscriptApi.list(video_id)` (static). The new API requires `YouTubeTranscriptApi().list(video_id)` (instance). Breaking change that caused silent failures in older code.

### SQLite schema (`knowledge.db`)

Three tables:
```sql
channels  (id, name, url, added_at)
videos    (id, channel_id, title, url, duration, view_count, has_transcript, added_at)
transcripts (video_id, full_text, segments)  -- segments is JSON: [{text, start, duration}]
```

### ChromaDB schema (`yc_vectors/`)

- **Collection**: `transcripts`
- **Embedding model**: `all-MiniLM-L6-v2` via `SentenceTransformerEmbeddingFunction`
- **CRITICAL**: the embedding function must be identical at collection creation time and every subsequent access. Changing the parameter even slightly causes a conflict error. Collections created without an explicit embedding function store as "default" internally — accessing them later with explicit params also causes conflicts.
- **Chunk size**: ~150 words with 50-word overlap, respecting segment boundaries (never cuts a sentence mid-segment)
- **Chunk ID format**: `{video_id}_chunk_{idx:04d}` — e.g. `dQw4w9WgXcY_chunk_0003`
- **Document format**: `"{video_title}\n\n{chunk_text}"` — title is prepended to each chunk to improve semantic matching (a question about "fundraising" matches better when the chunk document contains the video title "How to Raise a Seed Round")
- **Metadata per chunk**: `video_id`, `video_title`, `video_url`, `channel_name`, `start_time`, `end_time`, `timestamp_url` (deep link like `https://youtube.com/watch?v=ID&t=754s`), `chunk_index`

### `yt_knowledge_mcp.py` — the original delivery mechanism

FastMCP server using stdio transport for Claude Desktop. Three tools:
- `yt_search_knowledge_base(query, n_results=8)` — semantic search across all chunks
- `yt_get_video_context(video_title, topic, n_results=5)` — deep dive into a specific video
- `yt_list_videos(channel_filter)` — list all indexed videos

Configured via Claude Desktop's `claude_desktop_config.json` with env vars pointing to the ChromaDB path and collection name.

**Why this approach hit its limits**: every tool call result persists in Claude Desktop's context window for the entire conversation. Five searches burns ~10,000 tokens that never leave context, even if they become irrelevant. With 249K+ chunks indexed across many channels, the system was valuable but the delivery mechanism was wrong — you were burning your Claude Pro quota at an unsustainable rate just to ask a few questions.

### v2.0 — ChromaDB scan limit fix

The original `_get_embedded_video_ids()` function used `limit=50_000` when querying ChromaDB. This was a hardcoded cap that silently truncated results. Beyond ~526 videos (roughly 50K chunks), incremental sync was re-embedding already-indexed content because the lookup function couldn't see everything past the cap. Fixed by replacing with a paginated 10K-batch loop that reads until exhausted.

### v2.1 — Channel queue system

The original `add-channel` command was manual — one channel at a time, run it, wait, run the next. With 80+ channels to index, this was impractical. A full queue system was built:

- New SQLite table `channel_queue` — stores channel handle, scraping options (limit, sort_by, min/max duration, skip keywords, whitelist CSV), status (pending → running → done / paused / failed), timing, progress
- `queue add` — enqueue a channel with all its settings
- `queue run` — process all pending channels in order; automatically pauses on rate limit (YouTube IP blocking)
- `queue status` — show all entries with status, progress, timestamps
- `queue reset` — reset paused/failed back to pending (run after changing IP)
- `--sort-by views` — fetches the complete channel video list, sorts by view count descending, applies limit. This guarantees you get the top-N most-watched videos, not just the newest N. Critical for channels with hundreds of videos where you only want the best content.
- `--whitelist <file>` — restrict scrape to specific video IDs listed in a file

Also added `add-from-csv` command to scrape specific videos by URL/ID without needing a channel handle.

`RateLimitError` custom exception: `youtube-transcript-api` doesn't always signal rate limiting clearly. Added `_is_rate_limit()` detection based on error message patterns, which triggers queue pause instead of crash.

`_print_receipt()`: after every `add-channel` or `queue run`, prints a formatted summary showing per-channel results (scraped, succeeded, no-transcript, chunks added, elapsed time) plus totals.

### v2.2 — `--scrape-only` flag

The rate-limiting problem on YouTube required a two-phase approach: scrape transcripts to SQLite from a mobile hotspot (IP rotation via airplane mode), then embed to ChromaDB later from a normal connection. `--scrape-only` flag skips ChromaDB embedding entirely. `pipeline.py sync` then embeds everything in SQLite that isn't yet in ChromaDB.

### v2.3 — Audit tools

`yt_audit_channel(channel, sort_by)` — lists every video for a channel with view count, duration, transcript status. Revealed channels with off-topic content (reaction videos, shorts, Twitch streams that got scraped accidentally).

`yt_scan_for_issues(channel, expected_topics)` — automated heuristic scan checking for suspicious title keywords (shorts, reaction, vlog, gaming, live stream, unboxing), low engagement (view count < 10% of channel median), and missing transcripts.

### v2.4 — MCP startup fix + data cleanup

**Critical BM25 startup fix**: the `_build_bm25_index()` function was blocking MCP startup synchronously. With 249K chunks, this took 60-90 seconds. During that time, MCP appeared to hang and Claude Desktop would time out. Fix: moved BM25 build to a background daemon thread. First search shows a warning "(BM25 index building in background — rerun for hybrid results)" if not yet ready. Added `bm25_cache.pkl` — saved to disk after first build, validated by chunk count on subsequent startups.

**Cross-encoder also moved to background**: `cross-encoder/ms-marco-MiniLM-L-6-v2` model download and load was also blocking. Moved to background thread with semantic-only fallback until ready.

**Twitch chat guard**: some channels (notably `@geohotarchive`) had Twitch chat logs scraped as if they were video transcripts. These look like:
```
username1: lol
username2: KEKW
```
Added `_is_twitch_chat()` heuristic: count lowercase-username patterns (`[a-z][a-z0-9_]{2,}: `) — if density > 8 per 1000 chars, reject the transcript. The check deliberately ignores all-uppercase patterns to avoid false positives on legitimate speaker labels ("INTERVIEWER: So tell me about...").

**UC... channel ID fix**: 8 videos were stored with raw `UC...` YouTube internal channel IDs instead of `@handles` (e.g. `UCxxxxxx` instead of `@lexfridman`). Added `fix-channel-ids` CLI command to re-fetch metadata via yt-dlp and update both SQLite and ChromaDB.

### v2.5 — Speed fixes at scale

**`yt_list_videos` was catastrophically slow** (10-20 seconds): the function was scanning all 247K chunks in ChromaDB to aggregate video information. With each ChromaDB query taking time, this was unacceptably slow.

Fix: added a separate `video_metadata` collection — one document per video (~5K total) storing the video's title, channel, URL, and chunk count. `yt_list_videos` now reads from this small collection instead of scanning all chunks. Speed: 10-20s → <0.5s.

Similarly, `_get_embedded_video_ids()` was replaced with `_get_embedded_video_ids_fast()` which reads the `video_metadata` collection instead of all 247K chunks. Every call that previously took 5-10s now returns in <0.1s.

Added `idx_videos_has_transcript` SQLite index on `videos(has_transcript)`. Every incremental check was doing a full table scan. With 5K+ videos, this index makes the query instant.

### v2.6 — Context window fix for `yt_list_videos`

`yt_list_videos` with no filter was returning all 4,879 individual video entries, approximately 1.2MB of text. Claude Desktop was throwing "tool result too large" errors.

Fix: changed default behavior to return a **channel-level summary** (~4KB for 84 channels) showing each channel with total video count and total chunk count. When called with a `channel_filter`, returns a compact per-video list with `[VIDEO_ID] title  Nchunks` format. Guides the AI to do channel discovery first, then drill into specific channels.

### v2.7 — Data reconciliation

A major data audit revealed:
- 228 videos (primarily `@aswathdamodaranonvaluation`) were in SQLite with transcripts but had never been embedded into ChromaDB. Cause: they were scraped with `--scrape-only` before `sync` was added, and `sync` was never run afterward.
- `@CGPGrey` and `@cgpgrey` existed as two separate channels (SQLite is case-sensitive). 1 video was under `@CGPGrey`; moved it to `@cgpgrey` and deleted the duplicate channel entry.
- 5 channels (`@TED`, `@TEDx`, `@NeuralNine`, `@eucroix`, `@lexfridman`) were present in transcripts but not registered in the `channels` table — added with `add-from-csv` which didn't auto-register channels.
- 338 videos had `chunk_count=0` in `video_metadata` — field wasn't written until v2.0. Ran a back-fill migration scanning all 249K chunks and recomputing per-video counts.

After `pipeline.py sync` and the migrations: **249,641 total chunks** across all channels.

---

## Part 2 — Why We Built a Custom UI (The Turning Point)

### The problem with Claude Desktop + MCP

The MCP approach worked technically but had a fundamental economic and UX problem:

1. **Token accumulation**: every `yt_search_knowledge_base` tool call adds its full result to Claude Desktop's context window permanently. Five searches ≈ 10,000 tokens. Those tokens stay in context for the entire conversation — even when they're no longer relevant — burning quota.

2. **Claude Pro quota drain**: at the time, Claude Pro had usage limits. Using the knowledge base tool aggressively for research could burn through daily quota in a single session.

3. **No control**: you couldn't choose the model, set token limits, or control how much context the search results occupied.

4. **No UX**: raw tool result output in Claude Desktop is not a pleasant interface for browsing video knowledge.

The decision: build a purpose-built chat interface that owns the full stack. Use Gemini 2.0 Flash on Vertex AI — Google gave the user $300 of free credits, and Gemini 2.0 Flash costs $0.075/1M input tokens and $0.30/1M output tokens. At ~2,000-3,000 tokens per query, each question costs ~$0.003-0.006. The $300 credit = roughly 50,000-100,000 queries. Essentially unlimited for personal use.

### The decision to build the stack ourselves

Rather than use any existing chat UI framework, we built from scratch because:
- We needed tight control over the query pipeline (expand → search → rerank → synthesize)
- We wanted exact control over what gets sent to the LLM and what doesn't
- We had a specific citation format (`[SRC_N]` tokens linking to YouTube timestamps) that required custom rendering
- The sidebar needed to show the actual knowledge base (channels, videos) not just chat history

---

## Part 3 — The Chat UI Build (2026-03-06, Session 1)

### How the session was orchestrated

The build was done using a multi-agent pipeline:

```
Phase 1 (serial):    architect agent
                     ↓ writes ADR to .claude/memory/decisions.md
Phase 2 (parallel):  implementer-backend  +  implementer-frontend
                     ↓ builds api/         ↓ builds sage_chat/
Phase 3 (serial):    qa-engineer agent (validates both)
Phase 4 (async):     code-reviewer agent (security + quality audit)
```

Backend and frontend were built in parallel because they touch completely different files and the frontend only depends on the API contract (endpoints + JSON shapes), not on the backend actually running.

### PRD written first (`.claude/plans/prd-sage-chat.md`)

Key requirements locked in before any code was written:

**Success metrics:**
- Each query < $0.01 on Gemini 2.0 Flash
- Zero hallucinations — every factual claim cites `[SRC_N]`
- Query → answer in <5 seconds locally
- Can synthesize across 5+ videos in a single answer

**Two modes:**
- `ephemeral`: each message is independent. History sent as `[]`. Gemini has no memory of previous messages. Used for quick one-off questions.
- `conversation`: full message history passed to Gemini in every request. Used for multi-turn deep research sessions.

**Citation format:** `[SRC_N]` inline in the response text, where N maps to a numbered source from the search results. These become clickable superscripts linking to the exact YouTube timestamp.

**Hard constraints:**
- ChromaDB and SQLite are READ ONLY from the chat API — never write from api/
- Do NOT import `yt_knowledge_mcp.py` — it spawns background threads at module level; importing it triggers those side effects even if you only want one function
- No AI calls in tests — $300 budget is precious, tests must be deterministic
- Vertex AI auth via Application Default Credentials (ADC) — `gcloud auth application-default login` once; no API key file needed

### Architecture designed (ADR in `.claude/memory/decisions.md`)

**Backend module structure and dependency graph:**
```
config.py   ← no internal imports (Pydantic Settings, reads env vars)
models.py   ← no internal imports (Pydantic v2 request/response models)
search.py   ← config (hybrid search engine, ChromaDB + BM25)
gemini.py   ← config, models (Vertex AI client, query expansion, synthesis)
websearch.py ← standalone (DuckDuckGo fallback, no internal deps)
main.py     ← config, models, search, gemini, websearch (routes, CORS, lifespan)
```

No circular imports. Clean layering.

**API contract:**
```
POST /api/chat
  Request:  { query: str, mode: "ephemeral"|"conversation", history: Message[] }
  Response: { answer: str, sources: Source[], mode: str, usage?: UsageInfo }

GET /api/videos?channel=&limit=&offset=
  Response: { videos: VideoItem[], total: int }

GET /api/channels
  Response: { channels: ChannelItem[] }

GET /api/health
  Response: { status: "ok"|"degraded", chroma_chunks: int, db_videos: int }

GET /api/random-fact
  Response: { chunk_id, title, text, timestamp_str, timestamp_url, channel_name }
```

`Source` shape: `{ src_id: "SRC_1", title: str, timestamp_str: "12:34", url: str, quote: str }`

**The query pipeline (per POST /api/chat request):**

```
1. EXPAND: gemini.expand_query(query)
   → Single Gemini call, max_output_tokens=150, temperature=0.7
   → Returns [original_query, paraphrase1, paraphrase2, paraphrase3]
   → On Gemini failure: returns [original_query] only (graceful degradation)

2. SEARCH: For each variant, search_module.hybrid_search(variant, n_results=20)
   Hybrid search internals:
   a. Semantic: ChromaDB query with SentenceTransformerEmbeddingFunction
      → Returns cosine distances (range 0-2)
      → Converted to similarity: sem_score = max(0, 1 - distance/2)
      → Maps perfectly to [0,1] for cosine distance range
   b. BM25: rank_bm25 index built from all 249K chunk documents at startup
      → BM25Okapi.get_scores(query.lower().split())
      → Normalized: bm25_norm = (score - min) / (max - min)
      → Prevents unbounded BM25 values from dominating
   c. Combined score: 0.7 * sem_score + 0.3 * bm25_norm

3. DEDUPLICATE: _deduplicate_chunks(results_by_variant)
   → dict keyed by chunk_id, keeps highest score per chunk across all variants
   → Sorted by score descending

4. SELECT TOP 8: merged[:8]

3b. WEB FALLBACK: if best_score < 0.30
   → Means knowledge base has no confident answer
   → Falls back to websearch.web_search(query, n=4) via DuckDuckGo (no API key)
   → Returns results in same dict format as hybrid_search(), score=0.25
   → Used instead of KB results

5. FORMAT chunks as context for Gemini:
   "[SRC_1] Video Title — MM:SS\n\"chunk text here\""
   (title + timestamp + verbatim quote)

6. SYNTHESIZE: gemini.synthesize(query, chunks, history, mode)
   → Builds contents array for Gemini
   → Conversation mode: prepends full message history as user/assistant turns
   → Ephemeral mode: history is [] — no prior context
   → History captured BEFORE new user message is dispatched in frontend
     (prevents user's current query from appearing twice)

7. RETURN: ChatResponse(answer, sources, mode, usage)
```

**Why expand_query?** A single query often misses relevant chunks due to vocabulary mismatch. "How do I fire someone?" might not match chunks that say "letting someone go" or "parting ways". Running 3-4 paraphrases dramatically increases recall. All results are merged and deduplicated, so there's no risk of duplicate content.

### The Gemini integration in detail (`api/gemini.py`)

**Authentication:** Vertex AI uses Application Default Credentials. The client is initialized as:
```python
client = genai.Client(vertexai=True, project="YOUR_GCP_PROJECT_NUMBER", location="us-central1")
```
No API key. `gcloud auth application-default login` writes credentials to `~/.config/gcloud/application_default_credentials.json`. The `google-genai` library reads this automatically.

`YOUR_GCP_PROJECT_NUMBER` is a GCP project number (not the project ID string). Project numbers are not secret — they're resource identifiers visible in the Google Cloud console.

**`expand_query(query: str) -> list[str]`:**
```
System: (none — short utility call)
User: "Generate 3 paraphrased versions of this search query.
       Return ONLY the paraphrases, one per line, no numbering, no explanation.
       Original: {query}"
Config: max_output_tokens=150, temperature=0.7
Returns: [query] + variants[:3]  (always include original, cap at 3 variants)
```

**`synthesize(query, chunks, history, mode) -> tuple[str, dict|None]`:**

System prompt (enforces citation and quality):
```
You are Meridian, a knowledge assistant built on a curated video library.
RULES:
- Every factual claim MUST cite at least one source using [SRC_N] notation
- If no sources support a claim, say "I don't have sources on this"
- Never invent quotes, timestamps, or video titles
- Synthesize and connect ideas across sources — don't just summarize each chunk
- For comparisons, structure your answer with clear sections per perspective
```

Contents array construction:
```python
contents = []
if mode == "conversation" and history:
    for msg in history:
        contents.append({"role": msg.role, "parts": [{"text": msg.content}]})
user_message = f"Sources:\n{formatted_chunks}\n\nQuestion: {query}"
contents.append({"role": "user", "parts": [{"text": user_message}]})
```

The function returns `(answer_text, usage_dict)` where usage_dict has `prompt_tokens` and `completion_tokens` read from `response.usage_metadata`. On error, returns `(error_message, None)`.

**Web search fallback (`api/websearch.py`):** Uses DuckDuckGo via the `duckduckgo-search` library. No API key required. Called when the best KB score is below 0.30 (meaning the knowledge base has no confident answer). Results are returned in the same dict format as `hybrid_search()` so `_build_sources()` handles them identically. Score is hardcoded to 0.25 (below the 0.30 threshold — signals these are web results, not KB results). `is_web_result: True` flag lets `synthesize()` note the source type.

### CORS configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The `allow_origin_regex` handles wildcard Vercel subdomains (every deployment gets a unique subdomain like `sage-chat-abc123.vercel.app`). The regex is anchored to `https://` to prevent HTTP downgrade attacks. This is the correct approach for wildcard subdomain CORS in Starlette/FastAPI — not `allow_origins=["*"]` which would be insecure.

### Input validation

`ChatRequest` Pydantic model:
- `query: str = Field(..., min_length=1, max_length=2000)` — prevents empty and excessively long queries
- `mode: Literal["ephemeral","conversation"]` — enum validation, rejects arbitrary strings
- `history: list[Message]` — typed, schema-validated

`/api/videos` uses `Query(ge=1, le=200)` bounds on `limit` and `ge=0` on `offset`.

The `channel` filter uses parameterized SQL: `LIKE ?` with `f"%{channel.lstrip('@')}%"` as the parameter — not string concatenation. SQL injection is not possible.

SQLite opened with `?mode=ro` URI parameter — read-only at the OS level, not just by convention.

### Frontend architecture

**State machine** in `ChatInterface.tsx` using `useReducer` (no Redux, no Zustand):
```typescript
type State = {
  messages: ChatMessage[];
  mode: 'ephemeral' | 'conversation';
  loading: boolean;
  sidebarOpen: boolean;
  settingsOpen: boolean;
  error: string | null;
}
```

Actions: `ADD_USER_MSG`, `ADD_ASSISTANT_MSG`, `APPEND_WORD`, `SET_SOURCES`, `SET_LOADING`, `SET_ERROR`, `CLEAR_ERROR`, `CLEAR_CHAT`, `SET_MODE`, `TOGGLE_SIDEBAR`, `TOGGLE_SETTINGS`, `SET_SIDEBAR`, `SET_SETTINGS`, `RESTORE_MESSAGES`, `INCREMENT_TURNS`

**Word-reveal animation:** Response arrives as a complete batch from the API (not streamed). Frontend simulates streaming via `setInterval(30ms)` dispatching `APPEND_WORD` actions word-by-word. The `revealWords` function is defined *outside* the component so it doesn't close over stale state — it only captures `dispatch`, which is guaranteed stable across renders by React's `useReducer`.

**History capture timing:** `history` is built from `state.messages` *before* dispatching `ADD_USER_MSG`:
```typescript
const history = state.mode === 'conversation'
  ? state.messages.map(m => ({ role: m.role, content: m.content }))
  : [];
// THEN dispatch ADD_USER_MSG
dispatch({ type: 'ADD_USER_MSG', content: text });
// history passed to chat() doesn't include the new user message
```
This prevents the user's current question from appearing twice in the Gemini context (once in history, once as the `query` parameter).

**Component hierarchy:**
```
page.tsx
└── ChatInterface.tsx  [useReducer state machine]
    ├── Sidebar.tsx    [channels, videos, saved chats]
    ├── MessageList.tsx [scrollable messages + home screen]
    │   ├── UnicornBackground.tsx
    │   └── MessageBubble.tsx (per message)
    │       └── SourceCards.tsx
    ├── TypingIndicator.tsx (loading state)
    ├── ChatInput.tsx  [textarea, mode pill, send/stop button]
    └── SettingsPanel.tsx [theme toggle, profile management]
```

### QA results (`.claude/logs/qa-sage-chat-2026-03-06.md`)

All 9 acceptance criteria passed. Key checks:
- Ephemeral mode sends `history: []` to backend — PASS
- Conversation mode sends full history — PASS
- Backend returns `[SRC_N]` citations in every response — PASS (enforced by system prompt)
- Query expansion generates 3+ paraphrases — PASS
- Citation chunks formatted as `[SRC_N] Title — MM:SS\n"text"` — PASS
- `/api/videos` filterable by channel — PASS
- Frontend builds with zero TypeScript errors (`npm run build`) — PASS

Known non-blocking issues noted:
- BM25 startup: 30-60s with 249K chunks (users see "starting..." in server logs)
- Word-reveal `setInterval` not cleaned up on unmount (benign for a persistent SPA)

### Code review results (`.claude/logs/review-sage-chat-2026-03-06.md`)

Security audit passed:
- No secrets hardcoded (GCP project number is a non-secret resource ID)
- No wildcard CORS
- Parameterized SQL (no injection)
- Database strictly read-only (`?mode=ro`)
- Pydantic validation on all inputs

One minor finding: `api/gemini.py` leaks exception class name in error responses (`f"(Error: {type(e).__name__})"`) — cosmetic for a personal tool, not a blocking issue.

Correctness confirmed:
- `_deduplicate_chunks()` correctly keeps highest score per chunk_id across all variants
- `0.7 * sem_score + 0.3 * bm25_norm` matches the ADR
- `max(0, 1 - distance/2)` correctly normalizes cosine distance [0,2] → similarity [0,1]
- Ephemeral mode is double-guarded: both in `main.py` and `gemini.py`

Verdict: **Ready for use. No blocking issues.**

---

## Part 4 — Chat UI Fixes Round 1 (2026-03-06, Session 2)

*This session added several features that were discovered missing after the initial build.*

### Usage tracking (token counts + cost display)

`api/gemini.py` updated to read `response.usage_metadata` after `generate_content()` returns. The metadata contains `prompt_token_count` and `candidates_token_count`. Returns a tuple `(text, {"prompt_tokens": N, "completion_tokens": N})`.

`api/main.py` unpacks this and constructs a `UsageInfo` Pydantic model, included in `ChatResponse`.

Frontend: `lib/api.ts` added `calcCost(usage)` helper using Gemini 2.0 Flash Vertex AI pricing: $0.075/1M input tokens, $0.30/1M output tokens. `getBudgetSpent()` / `addBudgetSpent()` persist cumulative spend to localStorage. Header shows `$X.XX left` out of a $300 budget. Each assistant bubble shows token counts in the SourceCards row.

### Stop button

`ChatInput.tsx` gained `onStop?: () => void` prop. When `disabled=true` (loading state), the send arrow is replaced by a red filled square button (standard stop symbol). `ChatInterface.tsx` added:
- `abortRef = useRef<AbortController | null>(null)` — new AbortController created per request, stored here
- `revealIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)` — stores the word-reveal interval
- `handleStop()`: calls `abortRef.current.abort()` (cancels the fetch), clears the reveal interval, dispatches `SET_LOADING(false)`. The `AbortError` in the catch block is silently swallowed — no error UI shown when the user deliberately stops.
- The `signal` is passed to `chat()` which forwards it to `fetch()`.

### Citation rendering overhaul — the `rehype-raw` fix

The original `MessageBubble.tsx` split the assistant response on `[SRC_N]` tokens with regex, then passed each text segment to a separate `ReactMarkdown` instance:

```tsx
// OLD (broken):
parts.map(part => <ReactMarkdown key={i}>{part}</ReactMarkdown>)
```

This created a separate `<p>` block for every text segment. If a sentence ended with `[SRC_1]`, you got three `<p>` elements: the text before, the citation button, and the text after. This broke inline flow — citations appeared on their own lines.

**The fix**: use a single `ReactMarkdown` pass with the `rehype-raw` plugin (allows raw HTML nodes). A preprocessing `useMemo` converts citations to HTML `<cite>` elements before markdown rendering:

```typescript
// Step 1: Deduplicate — keep only LAST occurrence of each unique [SRC_N] token
// Step 2: Move citations AFTER sentence punctuation: [SRC_3]. → .[SRC_3]
// Step 3: Replace [SRC_N] with <cite data-ids="N"></cite>
//         Replace [SRC_N, SRC_M] with <cite data-ids="N,M"></cite>
```

A custom `cite` component in `ReactMarkdown` renders each `<cite data-ids="3,4">` as adjacent `<sup><button>` pairs — one per ID. The buttons open the YouTube timestamp URL. Result: inline superscripts that don't break paragraph flow.

**Why citation deduplication?** Gemini sometimes repeats the same `[SRC_3]` citation multiple times in a response (e.g. once after each sentence about the same source). Only keeping the last occurrence reduces visual clutter while ensuring the citation appears at its most relevant location.

**Citation order fix:** `[SRC_3].` (citation before period) was rendering as `<sup>3</sup>.` visually — the period appeared after the superscript, which looks wrong. A regex pre-pass moves all citations to after punctuation: `(\[SRC_\d+\])([\.\!\?])` → `$2$1`.

### SourceCards complete redesign

Original: horizontal scroll row of cards, always visible. Problems: takes up a lot of space, hard to read in a row.

New: collapsible toggle (collapsed by default). A single row shows "N sources" with a rotating chevron SVG (90° → 180° when open). When expanded, shows a vertical list with:
- Numbered badge (`1`, `2`, etc.) matching the `[SRC_N]` superscripts in the text
- Video title (bold) + timestamp string + YouTube link icon
- Quote snippet from the chunk (2 lines max, `line-clamp-2`)

Usage display (token counts + cost) combined into the same row as the sources toggle, right-aligned. Format: `↑1.2K / ↓0.3K · $0.0021`. This avoids a separate row just for usage metadata.

### Chat persistence

`lib/api.ts` gained the full chat storage API:
- `StoredChat` interface: `{ id: string, name: string, mode: 'ephemeral'|'conversation', messages: ChatMessage[], savedAt: number }`
- `CHATS_KEY = 'sage_chats'` localStorage key
- `loadChats()` — reads and parses from localStorage, returns sorted by `savedAt` descending
- `saveChat(chat)` — upserts, sorted, capped at 50 entries
- `deleteChat(id)` — removes by ID
- `renameChat(id, name)` — updates name field
- `newChatId()` — generates timestamp-based unique ID

`Sidebar.tsx` fully rewritten with a "Chats" tab as default:
- "New Chat" dashed button at top
- Per-chat card showing name, mode badge ("Quick" / "Deep"), message count, relative timestamp
- Hover reveals action buttons: pencil (rename) + trash (delete)
- Inline rename: click pencil → input field with current name pre-filled → Enter commits, Escape or blur cancels
- Active chat (currently loaded) highlighted with indigo-tinted background
- Clicking a card calls `onRestoreChat(storedChat)`

`ChatInterface.tsx` gained `currentChatIdRef = useRef<string | null>(null)` — deliberately a ref not state because updating it shouldn't trigger re-renders. Save effect runs on `state.messages` change, calls `saveChat()` with the current chat ID. On `handleNewChat`, clears the ref.

---

## Part 5 — Hero Screen + Animated Background (2026-03-07)

### Why an animated background?

The home screen (shown when no messages) was a blank dark rectangle — functional but boring. The decision to use Unicorn Studio WebGL animations came from wanting a visual impression that matched the "navigator of knowledge" brand direction.

### `lib/unicornEmbed.js`

Custom JavaScript utility (not TypeScript — it manipulates raw DOM). Features:
- Takes a DOM element and a Unicorn Studio project ID
- Lazy-loads the Unicorn Studio SDK script (`https://cdn.unicorn.studio/v1.3/unicornStudio.umd.js`) on first call, returns a Promise
- After SDK loads, calls `UnicornStudio.addScene({ elementId, projectId, fps: 60, scale: 1, dpi: 1.5, lazyLoad: false })`
- `cropPx` option: sets `overflow: hidden` on the container and subtracts `cropPx` from the element's bottom to hide the Unicorn Studio watermark badge
- Injects CSS to suppress the watermark link's pointer events and opacity
- Handles window resize events to keep the canvas properly sized

### `UnicornBackground.tsx`

React wrapper component:
- Uses `useRef<HTMLDivElement>` pointing to the container div
- `useEffect` fires after hydration (not SSR): calls `unicornEmbed(ref.current, projectId, { cropPx: 40 })`
- The WebGL scene (`qFZJmsATe1qivAJHWPuL`) renders a flowing abstract animation

**CRITICAL performance constraint discovered (documented, fixed later in v3.2):**

This component must NEVER be conditionally rendered. The pattern `{messages.length === 0 && <UnicornBackground />}` is catastrophically wrong. Each time `<UnicornBackground />` mounts, `unicornEmbed.js` registers a new WebGL context and a new animation loop. When it unmounts, neither the WebGL context nor the animation loop is destroyed. Each home→chat→home navigation cycle leaks one more GPU context and one more `requestAnimationFrame` loop. After 5-10 cycles, the browser has many active GPU render loops burning CPU/GPU and the UI becomes noticeably laggy.

### Hero screen in `MessageList.tsx`

Structural change: `MessageList` changed from two separate return paths (home screen OR chat view) to a single root div containing both. The home screen content is absolutely positioned inside the same container. This is what enables `UnicornBackground` to always stay mounted.

Home screen layout:
- `UnicornBackground` at `absolute inset-0 z-0` — full viewport
- Dark radial vignette overlay: `radial-gradient(ellipse, rgba(10,10,15,0.88) 0%, transparent 75%)` behind the text. This ensures text is readable regardless of what the animation is doing behind it.
- Gradient `<h1>` title: `linear-gradient(135deg, #818cf8 → #a5b4fc → #c7d2fe)` with `WebkitBackgroundClip: text` and `WebkitTextFillColor: transparent` — the standard CSS technique for gradient text
- Welcome phrase from a pool of 24 lines (started at 9, expanded later)
- Subtitle: "Ask anything from the cornucopia of knowledge."
- Suggestions hover panel

**SSR hydration fix:** the welcome phrase was originally set in `useState(() => PHRASES[Math.floor(Math.random() * PHRASES.length)])` — the initializer runs on the server during SSR, picks a phrase, then on the client a different phrase is picked by hydration. React throws "Text content does not match server-rendered HTML". Fixed by initializing to `null` and setting in `useEffect` (client-only).

### Suggestions panel

- Hover-triggered (not click): `onMouseEnter` → `setSuggestionsOpen(true)`, `onMouseLeave` → 200ms timer then `setSuggestionsOpen(false)`
- The 200ms grace period is critical: without it, moving the mouse from the "Suggestions" label to a card triggers the leave event on the label, closing the panel before the mouse reaches the card
- `leaveTimerRef` stores the timer; `onMouseEnter` clears any pending close timer so re-entering resets the countdown
- 3 random suggestions from a pool of 20, shuffled on mount
- Shuffle button: 160ms CSS transition (`suggestion-card-exit` keyframe fades out, `suggestion-card-enter` fades in) with `isShuffling` state preventing double-clicks
- Clicking a suggestion calls `onSuggestionClick?.(suggestion)` which fires it as a query in `ChatInterface.tsx`
- Cards have `animationDelay: ${i * 40}ms` stagger for entrance animation

---

## Part 6 — UI Polish Passes (2026-03-08, Sessions 1–2)

### v2.8 — Input and toggle polish

**Textarea auto-resize bug fix:** the `resizeTextarea()` function existed but was wired to React re-renders, not to actual typing. In React, an uncontrolled `<textarea>` (one with `.value` set directly via DOM ref) doesn't trigger re-renders on keypress. So `resizeTextarea()` was never called while typing. Fix: wired to `onInput` event — fires on every keystroke regardless of React render cycle.

**Q/D toggle redesign:** changed from separate icon+label layout to compact segmented pill. Fixed width `w-[4.5rem]` prevents layout shift when switching modes. Color scheme changed from purple `#9555ff` to blurple `#6570fc` — active state has `background: rgba(101,112,252,0.3)` and `textShadow: 0 0 8px rgba(101,112,252,0.8)` for a glow effect.

**Glassmorphism input bar:** `background: rgba(255,255,255,0.03)` + `backdropFilter: blur(12px)`. Had been accidentally removed in a previous session.

**Send button:** reverted to glowing vector icon with `color: #6570fc` and `filter: drop-shadow(0 0 6px rgba(101,112,252,0.65))`. A circle background wrapper had been added in a previous session; removed.

**Welcome phrase pool:** expanded from 9 to 24 entries. Removed YC-specific references ("YC wisdom", "YC partner", mentions of Paul Graham/YC talks) to make the system feel more general. New entries lean into the "navigator/consultant" framing.

**Auto-restore on page load removed:** the previous behavior was to restore the last chat automatically on refresh. This was confusing — users expected a fresh start. Previous chats remain in the sidebar.

### v2.9 — Full black background

Systematic audit of every background color in the codebase:
- `globals.css`: `--background: #0f0f0f` → `#000000`
- `page.tsx` root `<main>`: `bg-[#0a0a0a]` → `bg-black`
- `ChatInterface.tsx` header: `bg-[#0a0a0a]` → `bg-black`
- `MessageList.tsx` chat scroll area: added explicit `bg-black`

Sidebar left at its existing color (slightly lighter) — it sits as an overlay drawer, not part of the main canvas.

### v3.0 — UX critique pass

A comprehensive UX audit identified and fixed all issues:

**Focus ring restored:** `focus-within:ring-1 focus-within:ring-[#6570fc]/40` on the input container. Had been accidentally removed when the glassmorphism styles were refactored.

**Q/D toggle layout fixed:** previously the pill width was `fit-content`, causing it to shrink when "Q" was selected vs "Quick". Fixed at `w-[4.5rem]` — both labels always visible at consistent size.

**Suggestions hover-trap:** the original implementation used `onMouseLeave={setSuggestionsOpen(false)}` without a timer. Moving from the "Suggestions" text to a card in the panel (which requires the mouse to briefly leave the text element) would close the panel before the mouse reached the card. Fixed with 200ms timer + `leaveTimerRef`.

**Hero `overflow-hidden` removed:** the hero container had `overflow-hidden` to clip the UnicornBackground. But the suggestions dropdown is positioned absolutely relative to the hero content area — `overflow-hidden` was clipping it. Removed.

**Copy button:** on hover (`group-hover/bubble:opacity-100`), shows below each assistant bubble. Uses `navigator.clipboard.writeText()` with the response content stripped of `[SRC_N]` tokens and collapsed whitespace. On click: changes to checkmark + "Copied" text for 1,500ms, then reverts.

**Source quote expanded:** `line-clamp-1` → `line-clamp-2` for more context in each source card.

**Budget display:** 5 decimal places → 2. Changed from dark gray to `text-emerald-500` (always bright green, no hover state needed).

**`transition-colors` fix in `globals.css`:** global rule `* { transition-property: background-color, border-color, opacity, transform }` was missing `color`. This meant all Tailwind `transition-colors` utilities were silently doing nothing for text color transitions. Every hover state that changed text color was snapping instantly. Added `color` to the property list.

**Dead `.citation-btn` CSS removed:** an old CSS class from when citations were plain styled spans. The system had moved to inline Tailwind classes in the `cite` custom component; the CSS class was never applied.

---

## Part 7 — Rebrand: Sage → Meridian (2026-03-08)

### The reasoning

"Sage" is used by many AI products (Poe's AI, various others). It felt too generic to stick. "Meridian" was chosen because:
- Geographic/navigation connotation (charting a course through knowledge)
- The prime meridian is a reference line — fitting for a reference tool
- No competing AI products use the name
- Sounds more distinctive and has a cleaner phonetic quality

### What changed

All user-facing text: page title (`<title>Meridian</title>`), header brand text, hero `<h1>` title, input placeholder ("Ask Meridian anything..."), avatar letters (the "S" → "M" in the avatar circle).

New header logo: hand-crafted inline SVG globe icon. A circle with two lines representing the prime meridian arc and the equator. Ocean-to-indigo gradient: `#22d3ee → #0ea5e9 → #818cf8` (cyan ocean → sky blue → indigo). Clickable — navigates home.

`MeridianLogo.tsx` component: the same SVG logo used in the header and as the avatar on assistant message bubbles, parameterized by `size` and `gradientId` (multiple instances on the same page need unique SVG gradient IDs to avoid sharing/conflicting).

Gemini system prompt updated: "You are Sage" → "You are Meridian".

Internal codename stays `sage_chat` — renaming the folder would break all import paths.

---

## Part 8 — Performance Fixes (2026-03-07)

*Diagnosed from a PRD in `.claude/plans/prd-perf-fix.md` after user noticed progressive slowdown.*

### The 4 compounding issues

**Issue 1: `saveChat` O(N×M)**

Original `lib/api.ts`:
```typescript
const saveChat = (chat: StoredChat) => {
  const chats = loadChats().filter(c => c.id !== chat.id);  // JSON.parse ALL 50 chats
  chats.unshift(chat);
  localStorage.setItem(CHATS_KEY, JSON.stringify(chats.slice(0, 50)));  // stringify ALL
};
```

`loadChats()` calls `JSON.parse(localStorage.getItem(CHATS_KEY))` — deserializes all 50 saved chats (each with all their messages). With 50 chats × 20 messages each, this is parsing ~1000 message objects on every single word revealed (30ms). As chats accumulated, each word-reveal triggered a multi-millisecond localStorage operation.

Fix: module-level `Map<string, StoredChat>` cache initialized lazily from localStorage. `saveChat()` updates the Map directly then serializes only to localStorage. `loadChats()` populates the cache once and stays consistent. Saves never touch `loadChats()`.

**Issue 2: `handleSubmit` dep array included `state.messages`**

```typescript
// BROKEN:
const handleSubmit = useCallback(async (text) => { ... }, [state.loading, state.mode, state.messages]);
```

`state.messages` is a new array reference on every `APPEND_WORD` dispatch — 33 times per second during word-reveal. This caused `useCallback` to recreate `handleSubmit` 33 times per second. `handleVideoSelect` (which depended on `handleSubmit`) also recreated. Both were passed as props to child components, triggering unnecessary re-renders of `MessageList` and `ChatInput`.

Fix: removed `state.messages` from the dep array. The `history` array needed for conversation mode is read from state at call time — no stale closure issue because the reducer dispatch is what makes the next render use the updated state.

**Issue 3: `React.memo` missing**

Every `APPEND_WORD` dispatch re-rendered the entire component tree from `ChatInterface` down. `MessageBubble` ran its `useMemo` citation preprocessing on every render, even for fully-completed messages with completely stable props.

Fix: `React.memo` wrapped around `MessageList` and `MessageBubble`. Completed message bubbles now have stable `role`, `content`, `sources`, and `usage` props — they skip re-renders entirely during word-reveal of the latest message.

**Issue 4: `UnicornBackground` always-mounted fix**

As described in Part 5: changed from `{messages.length === 0 && <UnicornBackground />}` to always-mounted, CSS `hidden` class to hide. Also: `handleNewChat` now calls `abortRef.current.abort()` before clearing chat state — previously, navigating home mid-request left an in-flight fetch that would fire 50+ `APPEND_WORD` dispatches against cleared state. `CLEAR_CHAT` reducer now sets `loading: false` — previously, clearing mid-request left `loading: true`, blocking the next submission.

**Bonus fix: `saveEffect` cleanup**

```typescript
// BEFORE (missing cleanup):
useEffect(() => {
  if (state.messages.length === 0) return;
  const timer = setTimeout(() => saveChat(...), 500);
  // No return!
}, [state.messages]);

// AFTER:
useEffect(() => {
  if (state.messages.length === 0) return;
  const timer = setTimeout(() => saveChat(...), 500);
  return () => clearTimeout(timer);  // ← cleanup
}, [state.messages]);
```

In React StrictMode (default in Next.js dev), effects without cleanup are double-invoked. This was triggering double saves with stale closures.

---

## Part 9 — Theming System + Settings + Favicon (2026-03-08)

### Why a full theming system?

The initial UI had hardcoded hex colors everywhere (`#0a0a0a`, `#1a1a1a`, `#383838`, etc.). Adding a light mode meant touching every file. The solution: a semantic CSS variable system. Every color is a token, components reference tokens, themes override token values.

### CSS variable system

Defined in `app/globals.css` as custom properties on `:root` (dark mode default):

**Background tokens:**
- `--bg-base: #000000` — main app canvas
- `--bg-surface: #111111` — message bubbles, cards
- `--bg-sidebar: #0a0a0a` — sidebar drawer background
- `--bg-elevated: #1a1a1a` — dropdowns, modals
- `--bg-hover: #1f1f1f` — hover states
- `--bg-avatar: #1a1a1a` — avatar circle background

**Border tokens:**
- `--border-primary: rgba(255,255,255,0.09)` — main dividers
- `--border-subtle: rgba(255,255,255,0.05)` — card borders
- `--border-avatar: rgba(255,255,255,0.12)` — avatar ring

**Text tokens (dark → light, roughly):**
- `--text-primary: #ffffff` — headings, labels
- `--text-secondary: #e0e0e0` — main body copy
- `--text-body: #c0c0c0` — assistant message text
- `--text-muted: #909090` — secondary info
- `--text-dim: #686868` — tertiary info
- `--text-faint: #686868` — further dimmed (bumped from #505050)
- `--text-faintest: #545454` — barely visible (bumped from #404040)

**Input tokens:**
- `--input-bg: rgba(255,255,255,0.03)` — glassmorphism input background
- `--input-border: rgba(255,255,255,0.14)` — input border (bumped from 0.08)

**Scrollbar tokens:**
- `--scrollbar-thumb: rgba(255,255,255,0.15)`
- `--scrollbar-hover: rgba(255,255,255,0.25)`

**Light mode override (`[data-theme="light"]`):**

NOT pure white — warm Solarized cream palette:
- `--bg-base: #FDF6E3` — Solarized Base3 cream
- `--bg-surface: #EEE8D5` — Solarized Base2
- `--bg-sidebar: #E8E2D0` — slightly darker cream
- `--bg-elevated: #F5EFDC` — elevated surfaces
- `--text-primary: #073642` — Solarized Base03 dark teal
- `--text-secondary: #002B36` — Solarized Base02
- `--text-body: #586E75` — Solarized Base01
- All borders use `rgba(0,43,54,0.N)` dark teal instead of `rgba(255,255,255,0.N)`

**Why Solarized?** Pure white backgrounds are harsh. The warm cream is easier to read for long sessions and has a distinctive, intentional look rather than just "default white".

**Accent colors stay hardcoded** — `#6570fc` blurple, `indigo-600`, `emerald-500` etc. These work on both themes by design.

All components migrated to Tailwind arbitrary value syntax: `bg-[var(--bg-surface)]`, `text-[var(--text-body)]`. Inline style props for values that vary dynamically: `style={{ background: 'var(--input-bg)' }}`.

### `lib/theme.ts`

```typescript
export function getTheme(): 'dark' | 'light'  // reads localStorage 'meridian_theme'
export function setTheme(theme: 'dark' | 'light'): void  // saves to localStorage
export function applyTheme(theme: 'dark' | 'light'): void  // sets data-theme on <html>
```

### Anti-flash inline script

In `app/layout.tsx`, before React hydrates:
```html
<script dangerouslySetInnerHTML={{ __html: `
  try {
    const t = localStorage.getItem('meridian_theme');
    if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
  } catch(e) {}
`}} />
```

Without this, dark-mode users on a fast machine see a white flash for ~16ms before React hydrates and applies the theme. The inline script runs synchronously before any rendering.

### `lib/profiles.ts`

Profile CRUD backed by localStorage key `meridian_profiles`. Each profile: `{ id, name, isDefault }`. Default profile cannot be renamed to empty or deleted. The "personal knowledge base" feature is listed as "coming soon" — profiles are wired up visually but don't yet affect search scope.

### SettingsPanel

Slides in from the right, triggered by the gear icon in the header. Two sections:

**Theme toggle:** two buttons (Dark / Light) styled as a segmented pill, same blurple styling as the Q/D toggle. Calls `applyTheme()` on click — instant, no page reload.

**Profile management:**
- List of all profiles with active indicator
- Each profile shows name + mode badge
- Hover reveals rename/delete icons
- "Add profile" shows a text input that auto-dismisses to the `+ Add profile` button if you blur it without typing anything
- Clicking a profile sets it as active (saved to localStorage)

### Favicon

`public/favicon.svg`: starburst design — dark circle background, indigo `radial-gradient`, 8 spoke lines at 45° increments, crossbar marks near each tip. Registered in `app/layout.tsx` metadata:
```typescript
icons: { icon: '/favicon.svg' }
```
Plus a `<link rel="icon" href="/favicon.svg" type="image/svg+xml" />` fallback in `<head>`.

---

## Part 10 — UX Polish Sprint (2026-03-08, Multi-agent)

This sprint dispatched 4 independent implementer agents simultaneously across 4 non-overlapping tasks.

### Smart chat naming (`lib/chatName.ts`)

**Problem:** chat names were `firstUserMsg.content.slice(0, 40)`. Asking "what do YC partners say about hiring?" twice gives two chats both named "what do YC partners say about hiring?". Unusable.

**Implementation:** pure TypeScript (no deps, no LLM). The algorithm:

```typescript
export function generateChatName(userMsg: string, assistantMsg: string): string {
  // 1. Concatenate user message + first 500 chars of assistant message
  // 2. Lowercase, tokenize on non-word chars
  // 3. Filter: keep words ≥ 4 chars AND not in stopword set
  //    Stopwords include: "this", "that", "with", "from", "have", "what",
  //    "when", "where", "which", "they", "their", "there", "about",
  //    "would", "could", "should", "does", "your", etc.
  // 4. Build frequency map
  // 5. Boost words from userMsg ×1.5 (user's words define the topic best)
  // 6. Sort by boosted frequency descending
  // 7. Take top 4 words, Title Case
  // 8. Join as "Startup Fundraising Pitch Investors"
  // 9. Fallback: userMsg.slice(0, 40) if no words survive filtering
}
```

**TypeScript target issue:** `[...freq.entries()]` (spread of `MapIterator`) fails on older TypeScript targets. The `tsconfig.json` targets an ES level where spreading iterators isn't allowed. Changed to `Array.from(freq.entries())` — semantically identical, universally compatible.

**Timing fix in `ChatInterface.tsx`:** name is generated once, after first complete exchange:
```typescript
// Only generate name when:
// 1. Name not yet set (chatNameRef.current === null)
// 2. At least one user message exists
// 3. At least one non-empty assistant message exists
```
Cached in `chatNameRef` — subsequent saves don't regenerate or overwrite. `handleNewChat` resets `chatNameRef.current = null`.

### @-mention channel autocomplete

**Implementation in `ChatInput.tsx`:**

New state:
```typescript
const [mentionQuery, setMentionQuery] = useState<string | null>(null);  // null = no active mention
const [mentionResults, setMentionResults] = useState<ChannelItem[]>([]);  // all filtered results
const [mentionVisible, setMentionVisible] = useState(6);  // how many to render
const [mentionIndex, setMentionIndex] = useState(0);  // keyboard-selected index
const channelCacheRef = useRef<ChannelItem[] | null>(null);  // cached API response
const mentionStartRef = useRef<number>(-1);  // cursor position of the '@' character
```

`detectMention(value, cursorPos)`:
```typescript
const textBefore = value.slice(0, cursorPos);
const atMatch = textBefore.match(/@(\w*)$/);  // must be immediately before cursor
if (!atMatch) { setMentionQuery(null); return; }
const query = atMatch[1].toLowerCase();  // the typed text after @
mentionStartRef.current = cursorPos - atMatch[0].length;  // position of the @ sign
```

Channel fetch: `getChannels()` called once per component lifetime. Result cached in `channelCacheRef`. The `.catch(() => {})` silently handles backend-offline — dropdown simply never appears.

Filtering: substring match on the full channel name including `@`. `@pet` matches `@PeterAttiaMD`, `@petitemollier`, etc.

`insertMention(channelName)`:
```typescript
const before = el.value.slice(0, mentionStartRef.current);  // text before the @
const after = el.value.slice(el.selectionStart ?? el.value.length);  // text after cursor
const insert = `@${channelName.replace(/^@/, '')} `;  // strip API's @ prefix, add our own, add space
el.value = before + insert + after;
el.setSelectionRange(before.length + insert.length, before.length + insert.length);
```

**`@@` double-prefix bug:** channel names from `GET /api/channels` include their own `@` prefix (e.g. `"@ycombinator"`). Without the `.replace(/^@/, '')`, inserting would produce `@@ycombinator`. Fixed by stripping any existing `@` before prepending one.

Dropdown `onMouseDown` uses `e.preventDefault()` — without this, clicking a dropdown item would first fire the textarea's `onBlur`, which could trigger other effects. `preventDefault` on `mousedown` prevents the textarea from losing focus before the click registers.

**Keyboard handling added to `handleKeyDown`:**
- When `mentionQuery !== null && mentionResults.length > 0`, intercepts ArrowDown/ArrowUp/Enter/Tab/Escape before they reach the textarea's normal behavior
- ArrowDown/Up: `setMentionIndex((i) => (i + 1) % mentionResults.length)` — wraps at ends
- Enter/Tab: `insertMention(mentionResults[mentionIndex].name)` then `e.preventDefault()` (prevents Tab from moving focus, Enter from submitting)
- Escape: `setMentionQuery(null)` dismisses without inserting

**Infinite scroll dropdown:** renders `mentionResults.slice(0, mentionVisible)`. The container's `onScroll` checks `scrollHeight - scrollTop - clientHeight < 40` (near bottom) and increments `mentionVisible` by 6. "scroll for more" hint shows when `mentionVisible < mentionResults.length`. Resets to 6 when a new `@` is typed.

### Sidebar relative timestamps

`relativeTime(ts: number): string` helper:
```
< 1 min:    "just now"
< 60 min:   "${diffMin} min ago"
< 24h:      "${diffHours} hour(s) ago"
= 1 day:    "Yesterday"
2-6 days:   "${diffDays} days ago"
1-3 weeks:  "${diffWeeks} week(s) ago"
1-5 months: "${diffMonths} month(s) ago"
23-27 weeks (half year zone): "half a year ago"
7-11 months: "${diffMonths} months ago"
≥ 1 year:   "Jan 8, 2025" (toLocaleDateString with { month: 'short', day: 'numeric', year: 'numeric' })
```

Meta row contrast: `·` separators `--text-faintest` → `--text-dim`, message count and timestamp `--text-faint` → `--text-muted`.

### Light mode contrast audit

Systematic replacement pass on all `white/N` opacity values, which are invisible on the Solarized cream background:

- `text-white/25` → `text-[var(--text-dim)]`
- `hover:text-white/50` → `hover:text-[var(--text-muted)]`
- `text-white/90` → `text-[var(--text-body)]`
- `placeholder-white/20` → `placeholder-[var(--text-faintest)]`
- `border-white/[0.06]` → `border-[var(--border-primary)]`
- SettingsPanel theme toggle selected label: `text-[#c4b5fd]` → `text-[var(--text-primary)]` (deep dark teal in light mode)

Added `--pill-active-text` CSS variable: `#c4b5fd` in dark (light violet), `#3730a3` in light (indigo-900 for contrast on cream). Used for the selected Quick/Deep pill label.

### Dark mode readability pass

CSS token bumps:
- `globals.css`: `--text-faint: #505050` → `#686868`, `--text-faintest: #404040` → `#545454`
- `SourceCards.tsx`: quote text `--text-faint` → `--text-muted`, timestamp `--text-faint` → `--text-dim`
- `MessageBubble.tsx`: copy button `--text-faint` → `--text-dim`, hover `--text-muted` → `--text-secondary`, "response stopped" `--text-faint` → `--text-muted`

Build note: `npm run build` briefly showed a false error related to a Next.js 14 standalone output copy race condition (`ENOENT on .next/standalone`) — pre-existing, unrelated to these changes. Clean rebuild confirmed zero TypeScript errors.

---

## Part 11 — Floating Chat Bar (2026-03-08, Wave 4)

### The change

Moved from a docked bottom bar (fixed height, always visible at the bottom) to a floating overlay bar (Claude.ai / ChatGPT style). Conceptually: the chat input now hovers *above* the content rather than pushing it up from below.

### `ChatInput.tsx` changes

Added `floating?: boolean` prop to `ChatInputProps`. Conditional outer wrapper:
```tsx
<div className={floating
  ? 'absolute bottom-6 left-0 right-0 px-4'
  : 'relative border-t border-[var(--border-primary)] bg-[var(--bg-base)] px-4 pb-3 pt-2.5'
}>
```

When floating: deep shadow added (`boxShadow: '0 8px 40px rgba(0,0,0,0.45), 0 2px 12px rgba(0,0,0,0.3)'`) for visual separation from content below.

### `ChatInterface.tsx` changes

```tsx
{/* BEFORE: */}
<MessageList messages={...} loading={...} />
<ChatInput onSubmit={...} ... />

{/* AFTER: */}
<div className="relative flex flex-col flex-1 min-h-0">
  <MessageList messages={...} loading={...} />
  <ChatInput floating onSubmit={...} ... />
</div>
```

The `flex flex-col` on the wrapper is critical: `MessageList` uses `flex-1` to fill available height. Without a flex container parent, `flex-1` has no effect and `MessageList` collapses to zero height.

`min-h-0` is also critical: without it, a flex child in a flex column can overflow its parent. `min-h-0` allows the child to shrink below its intrinsic content height.

### `MessageList.tsx` changes

Added `pb-32` to the chat scroll container inner div. Without this, the last message is hidden under the floating input bar. `pb-32` = 8rem padding — enough to clear the floating bar even when the textarea is expanded to multiple lines.

### UnicornBackground effect

Previously, the input bar occupied ~56px of the viewport bottom, causing the UnicornBackground (which fills the `MessageList` container) to be clipped short of the viewport edge. With the floating input, the `MessageList` now fills the full viewport height — the animation stretches to the very bottom.

---

## Part 12 — @-mention Highlight (2026-03-08)

### The feature

Discord-style blurple highlighting: when you type `@ycombinator` in the chat input and `ycombinator` is a valid channel, that text turns indigo with a subtle indigo background tint.

### The mirror overlay technique

A transparent textarea cannot display styled text — a `<textarea>` renders plain text only. The trick: put a `div` behind the textarea with identical typography that renders colored HTML, then make the textarea text itself transparent.

**Mirror div:**
```tsx
<div
  ref={mirrorRef}
  aria-hidden
  className="absolute inset-0 overflow-hidden text-sm leading-relaxed pointer-events-none select-none"
  style={{ fontFamily: 'inherit', whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-body)' }}
  dangerouslySetInnerHTML={{ __html: buildHighlightHTML(inputValue, validChannelNames) + '\u200b' }}
/>
```

`\u200b` (zero-width space) appended to prevent the mirror from collapsing to zero height when the textarea is empty (which would cause the pill to collapse and misalign the placeholder).

**Textarea:**
```tsx
style={{ color: 'transparent', caretColor: 'var(--text-body)' }}
```

`color: transparent` hides the native text (prevents double-rendering). `caretColor: var(--text-body)` keeps the blinking cursor visible in the correct color.

**`buildHighlightHTML(text, validNames)`:**
```typescript
function buildHighlightHTML(text: string, validNames: Set<string>): string {
  const escaped = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');  // XSS prevention
  return escaped.replace(/@(\w+)/g, (match, name) => {
    if (validNames.has(name.toLowerCase())) {
      return `<span style="color:#818cf8;background:rgba(99,102,241,0.15);border-radius:3px">${match}</span>`;
    }
    return match;  // unrecognized @word stays plain
  });
}
```

HTML-escaping the input before processing is the XSS prevention step — without it, a user typing `<script>` into the textarea would inject it into the mirror's `innerHTML`.

**Scroll sync:** when the textarea scrolls (long input), the mirror must scroll identically:
```tsx
onScroll={(e) => {
  if (mirrorRef.current) mirrorRef.current.scrollTop = e.currentTarget.scrollTop;
}}
```

**`validChannelNames` state:** a `Set<string>` of lowercase channel names (without `@`) populated from the same `getChannels()` API call that powers the dropdown. Channel names stay in the set as long as the component is mounted (not cleared when the dropdown closes) — this is correct behavior since the channel list doesn't change.

### Mention scrollbar polish

`.mention-scroll` CSS class:
```css
.mention-scroll::-webkit-scrollbar-thumb { background: transparent; }
.mention-scroll:hover::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); }
```

Applied to the dropdown container. Without this, when 6 items are shown and the container has `overflow-y: auto`, a faint scrollbar track appears even before the user has scrolled. The transparent thumb removes visual noise until the user hovers.

---

## Part 13 — Centering Fix (2026-03-08)

### The bug

After adding the mirror overlay for @-mention highlighting, all textarea content (Quick/Deep pill + textarea + send button) appeared in the upper portion of the glassmorphism pill instead of vertically centered.

### Failed fixes

Multiple attempts that didn't work:
- Removing `self-stretch flex items-center` from the wrapper div
- Setting explicit `padding: 0` on the textarea to remove browser 2px default padding
- Adding `border-0` to the textarea and removing `minHeight` constraints

All irrelevant — the real cause was architectural.

### Root cause

The mirror was `absolute inset-0` inside a `relative flex-1` wrapper. An absolutely-positioned element is taken out of normal document flow. It contributes nothing to the wrapper's height. The `relative flex-1` wrapper's height was determined entirely by the textarea's intrinsic height — which at `rows={1}` is approximately one line (20-22px, depending on browser).

The parent pill uses `flex items-center`. It was centering the `flex-1` wrapper — but that wrapper was only ~22px tall. The pill itself is ~48px tall. The math: `(48 - 22) / 2 = 13px` of centering padding. But since `rows={1}` puts the textarea at the top of its wrapper, the visual content appeared ~13px too high.

After adding the mirror with `absolute inset-0`, the wrapper's height didn't change (absolute elements don't affect flow height), but the visible content (now including the highlighted text in the mirror) was even more obviously off-center.

### The CSS Grid fix

Replaced the `relative flex-1` wrapper + `absolute inset-0` mirror with a CSS Grid container:

```tsx
<div
  className="flex-1 min-w-0"
  style={{ display: 'grid' }}
>
  {/* Mirror — in normal flow, determines grid row height */}
  <div
    ref={mirrorRef}
    aria-hidden
    className="text-sm leading-relaxed pointer-events-none select-none overflow-hidden"
    style={{
      gridArea: '1/1',  // row 1, column 1
      fontFamily: 'inherit',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      color: 'var(--text-body)',
      padding: 0,
      maxHeight: '15vh',
    }}
    dangerouslySetInnerHTML={{ __html: buildHighlightHTML(inputValue, validChannelNames) + '\u200b' }}
  />

  {/* Textarea — same grid cell, on top, color transparent */}
  <textarea
    ref={textareaRef}
    rows={1}
    className="bg-transparent border-0 resize-none focus:outline-none disabled:opacity-50 text-sm leading-relaxed placeholder-[var(--text-faintest)]"
    style={{
      gridArea: '1/1',  // same cell — overlays the mirror
      maxHeight: '15vh',
      overflowY: 'auto',
      color: 'transparent',
      caretColor: 'var(--text-body)',
      padding: 0,
    }}
  />
</div>
```

When two elements share `gridArea: '1/1'` in a CSS Grid, they overlap. The first one (the mirror) is in normal document flow — it determines the grid cell's height naturally. The textarea overlays it exactly. The grid wrapper now has the correct height (equal to the mirror's content height), and the parent pill's `items-center` centers this wrapper correctly.

**`resizeTextarea()` removed entirely:** the function manually set `el.style.height = 'auto'` then `el.style.height = scrollHeight + 'px'`. This is no longer needed — the CSS Grid auto-sizes as the mirror's content wraps to new lines. The textarea expands automatically. Removed the function and all 4 call sites: `handleSubmit`, `insertMention`, `onInput`, mount `useEffect`.

### Scrollbar state bug (same session)

After the centering fix, a second related bug was discovered: the mention dropdown scrollbar never appeared when scrolling via trackpad/scroll wheel.

**Cause:** The `.mention-scroll:hover::-webkit-scrollbar-thumb` CSS rule only activates when the mouse is physically hovering over the element. Scroll-wheel and trackpad scrolling don't necessarily move the mouse. So scrolling loaded more items (via `setMentionVisible += 6`) but the scrollbar thumb stayed transparent.

The scrollbar only appeared after pressing an arrow key, which changed `mentionIndex` state, triggered a React re-render, and the browser re-evaluated the hover CSS against the current mouse position — which happened to be over the element.

**Fix:** `mentionScrolled` React state:
```typescript
const [mentionScrolled, setMentionScrolled] = useState(false);
```

Reset to `false` in `detectMention` when dropdown opens. Set to `true` in the dropdown's `onScroll` handler. Applied as:
```tsx
className={`${mentionScrolled ? '' : 'mention-scroll'} rounded-xl border ...`}
```

Once the user scrolls, the hide-class is removed immediately (no hover required) and the native scrollbar becomes visible.

---

## Part 14 — Project Structure + Deployment (2026-03-08, v3.8 Stable)

### File reorganization

Before pushing to GitHub, the project root was cleaned up:

**Moved to `archive/`:**
- `vector_builder.py` — legacy, replaced by `pipeline.py`
- `smoke_test.py` — one-time diagnostic script
- `APIgeminiai.py` — standalone Gemini test script used during initial API exploration
- `unicornEmbed.js` — duplicate of `sage_chat/lib/unicornEmbed.js`; root copy served no purpose
- `v2/` folder — previous version of pipeline scripts
- `yt_scraper.py` — original single-purpose scraper, superseded by `pipeline.py`
- `yt_knowledge_mcp.py` — the original MCP server; no longer the primary interface (already had a copy in `archive/mcp/`, this was the root copy)
- `start_api.ps1` — Windows PowerShell starter, superseded by `start.sh`
- `queue_channels.txt` — reference file listing channel handles to queue
- `whitelist_example.txt` — example whitelist file
- `LATESTCLAUDECHAT.md` — ephemeral session notes

**Moved to `docs/`:**
- `TODO.md`
- `OVERVIEW.md`
- `MANUAL.md`

**Stayed at root:** `pipeline.py`, `api/`, `sage_chat/`, `start.sh`, `CHANGELOG.md`, `CLAUDE.md`

### `start.sh`

The Windows `start_api.ps1` only started the backend. Getting the full app running required two terminal windows. `start.sh` consolidates:

```bash
#!/usr/bin/env bash
# Works: Windows Git Bash, Linux, Raspberry Pi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # absolute path regardless of CWD

# Env vars
export CHROMA_DB_PATH="$ROOT/yc_vectors"
export SQLITE_DB_PATH="$ROOT/knowledge.db"
export CHROMA_COLLECTION="transcripts"
export GCP_PROJECT="YOUR_GCP_PROJECT_NUMBER"
export GCP_LOCATION="us-central1"
export GEMINI_MODEL="gemini-2.0-flash"

# Auto-activate venv
if [[ -f "$ROOT/venv/bin/activate" ]]; then
  source "$ROOT/venv/bin/activate"      # Linux/macOS/Pi
elif [[ -f "$ROOT/venv/Scripts/activate" ]]; then
  source "$ROOT/venv/Scripts/activate"  # Windows Git Bash
fi

# Free ports (prevents EADDRINUSE on restart)
free_port() {
  if command -v fuser &>/dev/null; then
    fuser -k "${1}/tcp" 2>/dev/null || true   # Linux/Pi
  else
    local pid=$(netstat -ano 2>/dev/null | grep ":${1} " | grep LISTENING | awk '{print $NF}' | head -1)
    [[ -n "$pid" ]] && taskkill //PID "$pid" //F &>/dev/null || true  # Windows Git Bash
  fi
}
free_port 8000
free_port 3000
sleep 1

# Cleanup on Ctrl+C
cleanup() { kill "$API_PID" "$FRONTEND_PID" 2>/dev/null; wait; }
trap cleanup EXIT INT TERM

# Start both
uvicorn api.main:app --port 8000 &
API_PID=$!
cd "$ROOT/sage_chat" && npm "${1:-start}" &  # --dev flag for npm run dev
FRONTEND_PID=$!

wait -n "$API_PID" "$FRONTEND_PID" 2>/dev/null || wait
```

The `EADDRINUSE` error occurred during the first test run because the backend and frontend were already running from a previous session. The auto port-free logic was added as a fix.

### `.gitignore` fix

The original `.gitignore` was written in Windows Notepad which saved it as UTF-16 LE (each character is 2 bytes). Git reads `.gitignore` as UTF-8. The BOM and two-byte characters meant Git could not parse the file — every pattern was silently ignored. All large files (ChromaDB, SQLite, pickle cache, node_modules) were being tracked.

Rewrote as clean UTF-8 using `printf` in bash (which always writes UTF-8):
```
yc_vectors/
bm25_cache.pkl
knowledge.db
node_modules/
sage_chat/node_modules/
sage_chat/.next/
**/__pycache__/
venv/
.env
.env.local
sage_chat/tsconfig.tsbuildinfo
.claude/settings.local.json
.claude/logs/
.claude/plans/
```

### GitHub push

Attempted `git push -u origin main`. GitHub rejected with:
```
File knowledge.db is 453.25 MB; exceeds GitHub's file size limit of 100.00 MB
File bm25_cache.pkl is 478.76 MB; exceeds GitHub's file size limit
File yc_vectors/chroma.sqlite3 is 1960.01 MB; exceeds GitHub's file size limit
File sage_chat/node_modules/@next/swc-win32-x64-msvc/next-swc.win32-x64-msvc.node is 129.50 MB
```

The rejection was because GitHub checks all commits in the push, not just the HEAD commit. Even though the files were removed and `.gitignore` was fixed in the new commit, the previous commits still contained them.

Solution: create a fresh single-commit history with no large-file history:
```bash
git checkout --orphan clean-main
git add -A
git commit -m "Initial commit — Meridian Sage YTKB"
git push -f origin clean-main:main
git checkout main && git reset --hard clean-main && git branch -d clean-main
```

`--orphan` creates a branch with no parent commits — a completely fresh history. All working tree files are staged. Single commit = no history containing large files. Force push replaces the remote history.

---

## Current State: v3.8 Stable

### Stack summary

```
Frontend:  Next.js 14 App Router, TypeScript, Tailwind CSS
           Running on: http://localhost:3000

Backend:   Python FastAPI + uvicorn
           Running on: http://localhost:8000

Search:    ChromaDB (semantic, all-MiniLM-L6-v2) + rank_bm25 (keyword)
           249,641 chunks across 80+ YouTube channels

AI:        Gemini 2.0 Flash via Vertex AI (Application Default Credentials)
           Query expansion + grounded synthesis with [SRC_N] citations

Data:      knowledge.db (SQLite, 5K+ videos)
           yc_vectors/ (ChromaDB, ~2GB)
           bm25_cache.pkl (pre-built BM25 index, ~500MB)
           → These 3 files are NOT in git. rsync to Pi separately.

Start:     bash start.sh        # production
           bash start.sh --dev  # development (npm run dev)
```

### Things left undone

| # | What | Why it's blocked |
|---|------|-----------------|
| #2 | Research Unicorn Studio JSON intercept | The WebGL animation's `backgroundColor` is hardcoded black in the animation project's JSON. To fix it for light mode, need to either: (a) find a Unicorn Studio JS API to set canvas bg after init, or (b) intercept the animation JSON via a Service Worker before the SDK parses it and patch the `backgroundColor` field. Neither has been confirmed as possible yet. |
| #4 | UnicornBackground canvas color matches `--bg-base` | Blocked by #2 — can't change it until the intercept method is confirmed. |
| — | Raspberry Pi deployment | Just needs: `rsync -av yc_vectors/ knowledge.db bm25_cache.pkl user@pi:/path/`, then `bash start.sh` on the Pi. No code changes needed. |
| — | Personal knowledge base per profile | Profiles exist in the UI but don't yet scope search. Would require per-profile ChromaDB collections or metadata filtering. No spec written. |

### Critical facts for any continuation session

1. **ChromaDB embedding**: must use `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")` — exact string. Any variation causes a conflict with the existing collection.

2. **UnicornBackground**: never conditionally render. Always mount. CSS `hidden` class hides it. Pattern to avoid: `{condition && <UnicornBackground />}`.

3. **`handleSubmit` deps**: must NOT include `state.messages` in the `useCallback` dep array. It recreates 33×/sec during word-reveal.

4. **BM25 startup**: synchronous, ~30-60 seconds. Server logs show "BM25 index ready" when done. `bm25_cache.pkl` skips rebuild if chunk count matches.

5. **Theme**: applied via `data-theme` attribute on `<html>`. Dark is `:root`, light is `[data-theme="light"]`. Apply with `applyTheme()` from `lib/theme.ts`.

6. **CORS**: `localhost:3000` and `localhost:3001` explicit + `https://.*\.vercel\.app` regex. If deploying to a non-Vercel host, add it to `api/main.py` `allow_origins`.

7. **Vertex AI auth**: `gcloud auth application-default login` once per machine. No API key file. Credentials in `~/.config/gcloud/application_default_credentials.json`.

8. **Chat history**: stored server-side in `chats.db` (SQLite). Frontend uses in-memory cache (`_chatsCache`), populated via `initChatsFromServer()` on mount and on every Sidebar open. Max 50 chats. `localStorage` chat storage removed — server is source of truth.

9. **`start.sh` is canonical**: `start_api.ps1` is archived. `start.sh` works on Windows Git Bash and Linux/Pi.

10. **`sage_chat/` is the frontend folder name**: internal codename. "Meridian" is the product name.

---

## Session 12 — 2026-03-10: Pi Deployment, HTTPS, Server-Side Chats

### Context

This session focused entirely on production readiness: getting Meridian running cleanly on a Raspberry Pi accessible from any device on the local network, with a real domain name and HTTPS. A series of infrastructure issues were discovered and resolved sequentially. The session ended with a complete server-side chat persistence feature.

### Pi Deployment Fixes

**Editable budget cap**: The green `$X left` display was read-only. Clicking it now opens an inline number input pre-filled with the current remaining amount. Saving recomputes the cap as `input + totalSpent` so the display matches exactly what was typed. Fixed a math bug where saving was subtracting instead of replacing.

**Dynamic API URL**: The frontend was hardcoding `localhost:8000`. Changed `lib/api.ts` to use `window.location.hostname` at runtime, so accessing from any device automatically targets the correct host. `.env.local` was being tracked by git (baking `localhost` into builds) — untracked it and added to `.gitignore`.

**uvicorn binding**: `start.sh` was launching uvicorn bound to `127.0.0.1`. External connections refused. Added `--host 0.0.0.0`.

**Chrome Private Network Access (PNA)**: Chrome classifies `.local` mDNS hostnames as "local" address space — stricter than private IPs. HTTP requests from a `.local` origin to another `.local` port are blocked regardless of CORS headers. Resolution: use the Pi's IP address (`192.168.1.45`) instead of `pi-cloud.local`. Added `PrivateNetworkMiddleware` to set `Access-Control-Allow-Private-Network: true`, and expanded `allow_origin_regex` to cover private IP ranges.

**Gemini credentials on Pi**: API calls failed with `403 PERMISSION_DENIED`. The Pi had no Application Default Credentials. Fixed by creating a GCP service account key file (`gcp-key.json`) and setting `GOOGLE_APPLICATION_CREDENTIALS` in `start.sh`. Granted the service account the `Vertex AI User` IAM role.

### Gemini 2.0 Flash vs 2.5 Flash — The Finding

During this session the user tested both models extensively on real queries. **Gemini 2.0 Flash was conclusively better for this use case** — not 2.5 Flash despite being the newer model.

Why 2.0 Flash wins here:
- **Structured output compliance**: `expand_query` uses an explicit "exactly 4 lines" format. Gemini 2.0 Flash follows this reliably at `temperature=0.4`. Gemini 2.5 Flash would occasionally rephrase the instructions or add extra commentary.
- **Query preservation**: 2.5 Flash was more aggressive about "improving" the user's query — sometimes changing meaning while trying to correct style. 2.0 Flash makes surgical typo fixes only, leaves phrasing alone.
- **Speed**: 2.0 Flash is faster at short structured tasks — query expansion typically returns in 300-600ms vs 800-1200ms for 2.5.

The lesson: **newer model ≠ better model for every task**. For tightly-constrained structured prompts (fix typos, generate paraphrases, follow a strict line format), smaller/faster models that excel at instruction following beat larger reasoning models. Save the big models for synthesis and complex judgment calls.

`gemini-2.0-flash` stayed as the default in `GEMINI_MODEL` env var.

### Query Expansion + Typo Correction

The original `expand_query` function sent a single prompt asking for 3 paraphrases with no typo correction. Issues discovered:

1. **200-token limit truncation**: only 1 variant returned, second cut off mid-sentence ("What is one sentence to..."). Bumped to 400 tokens.
2. **Two-call typo correction destroyed queries**: a dedicated `_correct_query()` call at `temperature=0.0` returned "what" for the full sentence "what is the best way to hire engineers" — too aggressive. The model treated "correct" as "rewrite to minimal form".
3. **Single merged call solved both**: one prompt at `temperature=0.4` with format "Line 1: typo-corrected query (spelling only, nothing else changed). Lines 2-4: paraphrases of line 1." Gemini follows this cleanly. Typos like "claude coed" → "claude code" get fixed; correct queries are passed through untouched.

The original (possibly typo'd) query is always appended as the final variant — so even if expansion fails, the raw query still runs. `expand_query` now returns `(variants, usage_metadata)` tuple.

**Why typo correction matters for search**: ChromaDB uses cosine similarity on sentence embeddings. "coed" and "code" embed very differently — the query `claude coed` would match chunks about education/coeducation before chunks about Claude Code. One line-1 correction dramatically improves the top result quality.

**Accurate cost tracking**: Expansion call tokens were never counted — only synthesis was. `expand_query` now returns `usage_metadata` from its Gemini response. `api/main.py` sums expansion + synthesis prompt/completion tokens before building `UsageInfo`. Displayed cost in the bubble footer is now the true end-to-end total per query.

### Model Name in Header

`/api/health` extended with a `model` field returning the active `GEMINI_MODEL` string. Frontend fetches this on mount (with exponential retry up to 8 attempts for slow backend starts), formats `gemini-2.0-flash` → `Gemini 2.0 Flash` via `formatModelName()`, and displays it centered in the top navbar. Hidden on mobile (`hidden md:block`), only shown during active chat sessions.

### Copy Button Redesign

The original copy button was below the bubble in a grid-collapse container. Problems:
1. The grid-rows collapse occasionally flickered.
2. The button being in-flow made the bubble narrower than the sources row below it.

Final design: `absolute -right-7 top-3` — floats completely outside the bubble's right edge. Zero layout impact. `pt-2 pb-4 px-1` padding for a larger hit area. Icon-only (no "Copy" text label).

### UnicornBackground Fix

After navigating to chat and back to home, the Unicorn animation wasn't resuming. Root cause: `hidden` (Tailwind = `display:none`) pauses WebGL `requestAnimationFrame` loops. The element was removed from the render tree. When `display` was restored, UnicornStudio didn't auto-resume.

Fix: replaced `hidden` with `opacity-0/opacity-100` + `transition-opacity duration-500`. The canvas always renders — just invisible during chat. Bonus: smooth fade transition between home and chat.

### nginx + HTTPS + DuckDNS

**DuckDNS**: Registered `meridian-pi.duckdns.org` pointing to `192.168.1.45`. Public DNS resolves to local IP — works on LAN, unreachable from internet (no port forwarding needed, by design).

**nginx**: Configured as reverse proxy. `meridian-pi.duckdns.org` → port 3000 (frontend) and `/api/` → port 8000 (uvicorn). Port 80/443 — no port number needed in URLs. Coexists with existing n8n config on `mochasuc.mooo.com`.

**Let's Encrypt**: HTTP challenge fails because Pi isn't internet-accessible. Used DNS challenge via `certbot-dns-duckdns` plugin (installed with `--break-system-packages` on Debian's externally-managed Python). DuckDNS token authenticates the TXT record update. Valid cert obtained for `meridian-pi.duckdns.org`.

**Mixed content fix**: Once on HTTPS, `http://192.168.1.45:8000` API calls were blocked as mixed content. `lib/api.ts` now checks `window.location.protocol`: over HTTPS uses same-origin URL (nginx proxies `/api/` on port 443 internally), over HTTP uses direct `:8000`.

### Server-Side Chat Persistence

**Problem**: `localStorage` is per-origin. `192.168.1.45:3000` and `meridian-pi.duckdns.org` are different origins — chats created on one are invisible on the other.

**Solution**: New `chats.db` SQLite database (separate from `knowledge.db`) with a single `chats` table. `api/chat_db.py` owns all CRUD. Four new routes: `GET /api/chats`, `POST /api/chats`, `DELETE /api/chats/{id}`, `PATCH /api/chats/{id}` (rename).

Frontend strategy preserved the existing synchronous `loadChats()` interface (Sidebar.tsx needed no structural changes). New `initChatsFromServer()` async function populates the in-memory `_chatsCache` from the API. `saveChat`, `deleteChat`, `renameChat` update cache + fire-and-forget API call. `localStorage` chat storage removed entirely.

Result: one source of truth on the Pi. Any device, any origin, same chat history. Persists across API restarts.

11. **API URL detection**: `lib/api.ts` checks `window.location.protocol`. Over HTTPS (nginx) uses same-origin so nginx proxies `/api/` internally. Over HTTP uses direct `:8000`. Never hardcode the API URL.

12. **Pi deployment**: nginx on ports 80/443, proxies frontend (3000) and API (8000). SSL via Let's Encrypt DNS challenge (`certbot-dns-duckdns`). DuckDNS hostname resolves to local Pi IP — works on LAN only. Pi `start.sh` adds `--host 0.0.0.0` to uvicorn and sets `GOOGLE_APPLICATION_CREDENTIALS`.

13. **CORS**: includes `https://.*\.duckdns\.org` regex and private IP ranges. `PrivateNetworkMiddleware` adds `Access-Control-Allow-Private-Network: true` for Chrome PNA. `.local` mDNS hostnames are classified as "local" (stricter than private) by Chrome and cannot be fixed without HTTPS.

---

## Current State: v4.0 — Meridian Lives Everywhere

### Where things stand

Meridian Sage is fully deployed and working on:
- `meridian-pi.duckdns.org` — clean HTTPS URL, works on any LAN device (phone, tablet, PC)
- `192.168.1.45:3000` — direct IP access on LAN
- `localhost:3000` — local dev on the PC

All three share the same chat history (`chats.db` on the Pi), the same knowledge base (249K+ chunks), and the same Gemini 2.0 Flash model. Versions stay in sync via GitHub — pull on Pi, restart, done.

### The `/wise-practices` skill

After finishing the deployment work, the accumulated lessons from building Meridian were distilled into a reusable Claude Code global skill at `~/.claude/commands/wise-practices.md`. Invoked with `/wise-practices` in any project, it loads a reference of hard-won patterns:

- CSS layout traps (flex height collapse, grid overlay, floating UI, hover dropdown close bug, scrollbar scroll-wheel mismatch)
- React patterns (useReducer, useCallback dep arrays, SSR hydration, always-mounted WebGL, AbortController, React.memo)
- FastAPI patterns (centralized config, lifespan, CORS regex, Private Network middleware, read-only SQLite, parameterized SQL)
- Deployment ops (UTF-8 gitignore, GitHub orphan branch for large file history, bash startup scripts, LAN HTTPS chain)
- LLM integration (query expansion, single-call typo correction, token counting, health retry, citation preprocessing)
- Theming (CSS variable tokens, warm cream light mode, anti-flash script)

The point: these patterns aren't Meridian-specific. They apply to any Next.js/FastAPI/React/SQLite project. The skill means future projects won't rediscover the same traps.

### What's left

The app is feature-complete for its core purpose. Remaining work:

| # | What | Notes |
|---|------|-------|
| Telegram bot | Replace CLI (`pipeline.py add-channel`, `sync`, `status`) with a bot running on Pi | Makes KB updates possible from phone without SSH |
| Profiles | Per-profile knowledge base scope | Profiles exist in UI but don't affect search |
| Light mode | Full light theme pass | CSS token system is in place, just needs component audit |
| Unicorn canvas bg | Match `--bg-base` in light mode | Blocked on Service Worker / Unicorn Studio JS API research |
| More KB content | More channels beyond current ~80 | Telegram bot makes this easier |

The database question is solved: the Pi IS the single source of truth. `knowledge.db` + `yc_vectors/` + `chats.db` all live there. Every client hits the same API. The only remaining gap is adding content without SSH — that's the Telegram bot.

---

## Session 13 — 2026-03-10: Mobile Fixes + Budget Full Sync (v4.1)

### Three bugs found on first real mobile use

**1. Hero screen overflow on mobile**

Root cause: `page.tsx` used `h-screen` = `100vh`. On Android Chrome and iOS Safari, `100vh` includes the browser address bar height. The app was taller than the actual visible viewport — body was scrollable.

Fix: `h-[100dvh]` — dynamic viewport height, introduced in modern CSS. Tracks the actual visible area and adjusts when the browser chrome shows/hides. Well-supported on modern Android (Chrome 108+) and iOS (Safari 15.4+). The Samsung Galaxy A56 and similar modern Android phones support it fully.

**2. Sidebar backdrop DOM — the stopPropagation trap**

First attempted fix: `e.stopPropagation()` on the New Chat button. Didn't work because the backdrop `div` was a **sibling** of the `aside`, not an ancestor. `stopPropagation` only prevents bubbling up the ancestor chain — it has no effect on siblings.

Second attempt: `stopPropagation` on the `aside` element itself. Still unreliable on mobile because non-interactive elements (like `aside`) don't guarantee reliable click capture on iOS/Android.

Real fix: restructured the DOM. The outer `div` is now both the backdrop and the click handler. `aside` is its child. The `onClick` checks `e.target === e.currentTarget` — only fires `onClose` when the tap lands directly on the outer backdrop area, not when events bubble from inside the panel. No `stopPropagation` needed anywhere.

**3. Budget cap not synced across devices**

The budget display is `budgetCap - totalSpent`. `totalSpent` was being synced from server (`initBudgetFromServer` set `_budgetSpent` from `data.spent`). But `budgetCap` was only in localStorage, and each device had a different value from previous edits. Result: even when `spent` matched, the displayed remaining amount diverged.

Fix:
- `initBudgetFromServer()` now also writes `data.cap` to localStorage, overriding the stale local cap
- `setBudgetCap()` (called when user edits the budget) now fire-and-forgets `PUT /api/budget` with `{ cap }` so the new cap is persisted to server immediately

After pull + restart, both PC and phone showed identical `$299.99541`. Made a test query — both went down to `$299.99522` simultaneously. Fully synced.

### New Chat button UX fix

User realized "New Chat" was working all along — it returns to the home screen, which looks like nothing happened. The button was just confusing when already on the home screen.

Fixes:
- New Chat button in Sidebar now hidden when `hasMessages = false` (already on home screen)
- Redundant "New Chat" text button removed from the top navbar

14. **Budget sync**: `spent` and `cap` both server-side in `chats.db` settings table. `initBudgetFromServer()` overwrites localStorage for both on every load. `addBudgetSpent()` and `setBudgetCap()` both fire-and-forget PUT to server. Seed with: `sqlite3 chats.db "INSERT OR REPLACE INTO settings VALUES ('budget_spent', 'X'); INSERT OR REPLACE INTO settings VALUES ('budget_cap', '300.00000');"`.

15. **Mobile viewport**: `h-[100dvh]` not `h-screen`. Never use `100vh` in mobile-first apps — it includes browser chrome on Android/iOS.

---

## Session 13 — 2026-03-10: Mobile Fixes + Cross-Device Budget (v4.1)

### The three bugs

First time using Meridian from a phone revealed issues:

1. **Hero screen overflow**: the title + subtitle + suggestion chips required scrolling on mobile. The floating chat bar covers the lower ~80px of the viewport. The old `py-10` (40px top + 40px bottom) was symmetric, but the effective visible area is much shorter because the floating bar occludes the bottom. The content was visually overflowing below the bar.

2. **"+ New Chat" not working on mobile**: tapping the button in the sidebar did nothing — the chat didn't clear. The Sidebar has a full-screen backdrop `div` with `onClick={onClose}` at `z-30`, and the panel `aside` at `z-40`. On desktop, a click inside the `aside` never reaches the backdrop. On mobile touch events, propagation still fires. The tap reached the backdrop's `onClose` before the button's handler, closing the sidebar without clearing the chat.

3. **Budget not synced across devices**: `getBudgetSpent()` read from `localStorage`. Different origins have different localStorage namespaces. PC showed `$299.99577` spent; phone showed `$0` spent (fresh `$300` budget). Every new device would always start with a full budget.

### Fixes

**Fix 1 — `MessageList.tsx`**

Changed hero container padding from `py-10` to `pt-4 pb-28 md:pt-10 md:pb-10`:
- `pt-4` (16px): less top breathing room on mobile
- `pb-28` (112px): pushes content above the floating bar (~80px height + margin)
- `md:` prefix restores original values on desktop

Also shrunk the title from `text-5xl` to `text-4xl md:text-5xl` so it fits without wrapping awkwardly on small screens.

**Fix 2 — `Sidebar.tsx`**

Added `e.stopPropagation()` to the New Chat button's `onClick`:
```tsx
// Before:
onClick={() => { onNewChat?.(); onClose(); }}
// After:
onClick={(e) => { e.stopPropagation(); onNewChat?.(); onClose(); }}
```

The backdrop still handles genuine outside taps. Taps inside the panel no longer reach it.

**Fix 3 — Cross-device budget sync**

Reused the existing `chats.db` with a new `settings` key-value table. Same pattern as chat persistence — server is source of truth, frontend cache + fire-and-forget updates.

Backend:
- `api/chat_db.py`: `settings` table added to `init_db()` alongside `chats`. `get_setting(key, default)` and `set_setting(key, value)` helpers.
- `api/models.py`: `BudgetResponse(spent, cap)` and `BudgetRequest(spent?, cap?)` Pydantic models.
- `api/main.py`: `GET /api/budget` returns `{spent, cap}` from settings. `PUT /api/budget` accepts partial updates — can update spent, cap, or both.

Frontend:
- `lib/api.ts`: `_budgetSpent: number | null` in-memory cache (avoids localStorage re-read on every render). `initBudgetFromServer()` fetches server value and populates cache. `addBudgetSpent()` updates cache + localStorage immediately, fire-and-forgets `PUT /api/budget` in background. `getBudgetSpent()` checks cache first before falling back to localStorage.
- `ChatInterface.tsx`: `initBudgetFromServer()` called in mount `useEffect` alongside `initChatsFromServer()`. On resolve, updates the `totalSpent` and `budgetCap` UI state to reflect server values.

The existing `$299.99577` value on the Pi persists in memory/localStorage — first time the Pi API restarts with the new `settings` table, the budget starts at `0` until the PC does a query (which fires `PUT /api/budget` with the real value). If needed, can seed manually: `INSERT INTO settings VALUES ('budget_spent', '0.00423')` in the Pi's `chats.db`.

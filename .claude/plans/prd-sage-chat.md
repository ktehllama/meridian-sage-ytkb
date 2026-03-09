# PRD: Sage Chat — Custom AI Knowledge Assistant UI
**Status**: READY_FOR_SPEC
**Created**: 2026-03-06
**Owner**: YOUR_USERNAME
**Timeline**: MVP first (localhost), deploy-ready for Vercel + Railway later

---

## Problem Statement
The Claude Desktop + MCP setup permanently accumulates tool results in context — 5 searches burns ~10K tokens that persist for the entire conversation. With 249K+ chunks indexed across YC, Lex Fridman, TED, and other channels, the system is valuable but the delivery mechanism is wrong. We need a purpose-built chat interface where we control token budget, model selection, and retrieval behavior end to end.

## Users & Context
**Primary user**: YOUR_USERNAME (solo, personal productivity tool)
**Current workaround**: Claude Desktop with `yt_knowledge_mcp.py` MCP server — works but drains Claude Pro quota fast
**Frequency**: Daily use when researching startup problems, strategy, hiring, fundraising

## Success Metrics
- Each query costs <$0.01 on Gemini 2.0 Flash (Vertex AI, $300 credit)
- Zero hallucinations on factual claims — every answer cites `[SRC_N]` chunks
- Query → answer in <5 seconds (local), <8 seconds (deployed)
- Can synthesize across 5+ videos in a single answer

## Use Cases

### Happy Path — Ephemeral Mode
1. User opens Sage Chat, mode is "Quick Query" (stateless)
2. User types: "How do early-stage startups get their first customers?"
3. Backend expands to 3-4 paraphrase queries, runs hybrid search (semantic + BM25)
4. Top 8 chunks retrieved, formatted as `[SRC_N] Video Title — MM:SS\n"quote..."`
5. Gemini 2.0 Flash synthesizes with mandatory citation — answer includes `[SRC_1]`, `[SRC_3]` etc.
6. User reads answer with clickable timestamps back to YouTube
7. Next message starts fresh — no memory

### Happy Path — Conversation Mode
1. User switches to "Deep Dive" mode
2. Multi-turn conversation — Gemini has full message history in context window
3. User can ask follow-ups: "expand on what [SRC_3] said about cold outreach"
4. System maintains session history (in-memory, not persisted to disk)
5. User can reset session manually via "New Chat" button

### Video/Channel Listing
1. User opens sidebar or asks "show me all YC videos about hiring"
2. System queries SQLite via FastAPI, returns paginated list
3. User can filter by channel, click any video to seed a query about it

### Video Comparison
1. User asks: "compare what Paul Graham and Sam Altman say about pivoting"
2. Query expansion finds chunks from both — Gemini synthesizes a comparative answer
3. Citations show which claims come from which video/speaker

### Edge Cases
- Query returns 0 results: Gemini responds "I couldn't find relevant content in the knowledge base" — does NOT hallucinate
- Gemini API timeout: Frontend shows error toast, user can retry
- ChromaDB unavailable: FastAPI returns 503, frontend shows clear error
- Very long conversation: Frontend warns when approaching ~20 turns (token pressure)

### Error States
- Vertex AI auth failure: 500 with "Check Google Cloud credentials" message
- Query too vague (1-2 words): Backend still runs, Gemini may ask for clarification
- No chunks grounded: Gemini MUST say it has no sources rather than invent content

## Acceptance Criteria
- [ ] Given ephemeral mode, when user sends second message, then conversation history is NOT sent to Gemini
- [ ] Given conversation mode, when user sends follow-up, then full message history is included in Gemini context
- [ ] Given any query, when Gemini responds, then response contains at least one `[SRC_N]` citation
- [ ] Given a query, when backend processes it, then 3+ paraphrase variants are generated via Gemini before search
- [ ] Given search results, when chunks are passed to Gemini, then each chunk is prefixed `[SRC_N] Title — MM:SS\n"text"`
- [ ] Given video listing endpoint called, when response arrives, then videos are filterable by channel
- [ ] Given Vertex AI unavailable, when request is made, then frontend shows error state (not blank/hang)
- [ ] Given mode switch, when user toggles ephemeral↔conversation, then chat history clears visually
- [ ] Given a response, when user sees citations, then `[SRC_N]` links open the YouTube timestamp URL in new tab

## Technical Scope

### Stack & Constraints
- **Frontend**: Next.js (App Router), Tailwind CSS, deployed to Vercel
- **Backend**: Python FastAPI, deployed to Railway/Render (separate from frontend)
- **AI**: `google-genai` Vertex AI client — `gemini-2.0-flash`, project `YOUR_GCP_PROJECT_NUMBER`, location `us-central1`
- **Vector DB**: ChromaDB (existing `yc_vectors/`, collection `transcripts`) — READ ONLY, do not modify
- **Structured DB**: SQLite (`knowledge.db`) — READ ONLY for chat, write only via `pipeline.py`
- **Search**: Hybrid — ChromaDB semantic + BM25 (port from `yt_knowledge_mcp.py`)
- **Must NOT break**: `pipeline.py`, existing ChromaDB schema, SQLite schema
- **Must NOT use AI for tests** — no LLM calls in test suite

### Auth
- Vertex AI: Application Default Credentials (ADC) via `gcloud auth application-default login`
- No API key file — ADC reads from environment automatically
- Frontend calls backend API (no direct Gemini calls from Next.js)

### New Directory Structure
```
yt_scraper_consultant/
  archive/
    mcp/
      yt_knowledge_mcp.py     ← moved here (deprecated but preserved)
  sage_chat/                  ← NEW: Next.js frontend
    app/
    components/
    public/
    package.json
    next.config.js
  api/                        ← NEW: FastAPI backend
    main.py                   ← FastAPI app + routes
    search.py                 ← hybrid search (semantic + BM25)
    gemini.py                 ← Vertex AI client + query expansion + grounded synthesis
    models.py                 ← Pydantic request/response models
    config.py                 ← env vars (CHROMA_DB_PATH, CHROMA_COLLECTION, GCP_PROJECT, etc.)
    requirements.txt
  pipeline.py                 ← unchanged
  knowledge.db                ← unchanged
  yc_vectors/                 ← unchanged
```

### API Endpoints
```
POST /api/chat
  body: { query, mode: "ephemeral"|"conversation", history: Message[] }
  returns: { answer, sources: [{src_id, title, timestamp, url, quote}], mode }

GET /api/videos?channel=&limit=&offset=
  returns: { videos: [{id, title, channel, url, duration}], total }

GET /api/channels
  returns: { channels: [{name, video_count}] }

GET /api/health
  returns: { status, chroma_chunks, db_videos }
```

### Query Pipeline (backend per request)
```
1. Gemini: expand query → 3-4 paraphrase variants (1 fast API call, low tokens)
2. ChromaDB: semantic search each variant, merge + deduplicate by chunk_id
3. SQLite BM25: keyword search, merge results
4. Re-rank: score = 0.7 * semantic_score + 0.3 * bm25_score, take top 8
5. Format chunks: [SRC_N] Title — MM:SS\n"text"
6. Gemini: synthesize with system prompt enforcing citation
7. Return structured response
```

### Gemini System Prompt (grounding enforcement)
```
You are Sage, a knowledge assistant built on a curated video library.
RULES:
- Every factual claim MUST cite at least one source using [SRC_N] notation
- If no sources support a claim, say "I don't have sources on this"
- Never invent quotes, timestamps, or video titles
- Synthesize and connect ideas across sources — don't just summarize each chunk
- For comparisons, structure your answer with clear sections per perspective
```

### Performance Requirements
- Query expansion + search + synthesis: <5s p95 locally
- Chunk formatting adds ~200 tokens overhead per call (acceptable)
- Target: ~2,000–3,000 tokens per query total (prompt + completion)
- At Gemini 2.0 Flash pricing: ~$0.003–0.006/query → $300 = ~50K–100K queries

### Files Likely Affected / Created
**New**: `api/main.py`, `api/search.py`, `api/gemini.py`, `api/models.py`, `api/config.py`, `api/requirements.txt`
**New**: `sage_chat/` (full Next.js project)
**Moved**: `yt_knowledge_mcp.py` → `archive/mcp/yt_knowledge_mcp.py`
**Unchanged**: `pipeline.py`, `knowledge.db`, `yc_vectors/`, `smoke_test.py`

## MVP Definition
**Must ship (v1)**:
- FastAPI backend with `/api/chat`, `/api/videos`, `/api/channels`, `/api/health`
- Hybrid search (ChromaDB + BM25) ported from MCP server
- Query expansion via Gemini
- Grounded synthesis with `[SRC_N]` citations
- Ephemeral + Conversation mode toggle
- Next.js chat UI with message history display, source cards with YouTube timestamp links
- Channel/video browser in sidebar
- Mode switcher (ephemeral vs conversation)
- `.env.local` for frontend (API URL), `.env` for backend (Chroma paths, GCP config)
- `archive/mcp/` migration of old MCP server

**Out of scope for v1**:
- User accounts / auth on the UI
- Persistent conversation history (disk/DB)
- Cross-encoder re-ranking (nice to have, add later)
- Streaming responses (use batch + typing animation to fake it)
- Deployment (Vercel + Railway setup) — structure must support it, but not wired up

**V2 candidates**:
- Real streaming (Gemini streaming API)
- Cross-encoder re-ranking (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
- Conversation persistence (save sessions to SQLite)
- Deploy to Vercel + Railway
- LLM-generated topic tags on ingestion

## Open Questions
- [ ] **BM25 library**: `rank_bm25` (pure Python, no deps) vs `bm25s` — use whichever is already installed in venv
- [ ] **Fake streaming UX**: typing animation on the frontend (CSS `@keyframes` on text reveal) — implement as simple word-by-word reveal on response arrival
- [ ] **CORS**: FastAPI needs CORS configured for `localhost:3000` (Next.js dev) and `*.vercel.app` (prod)

## Implementation Notes
- Copy search core from `yt_knowledge_mcp.py` — do NOT import it (BM25 thread side-effects at module level, noted in TODO.md)
- ChromaDB embedding function must match how collection was created: `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")`
- BM25 cache: build from SQLite `transcripts.full_text` on startup, cache in memory (same pattern as MCP server)
- Vertex AI client init: `genai.Client(vertexai=True, project="YOUR_GCP_PROJECT_NUMBER", location="us-central1")`
- For query expansion, use a cheap/short Gemini call: `gemini-2.0-flash` with `max_output_tokens=150`
- Chunk format sent to Gemini: literal string `[SRC_1] Video Title — MM:SS\n"chunk text here"` — keep quotes to signal it's a verbatim excerpt
- Source cards in UI: show title, timestamp, clickable link to `timestamp_url` from ChromaDB metadata

---
*Generated by prd-wizard. Next step: spawn-team → orchestrator pipeline.*

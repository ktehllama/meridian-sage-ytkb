# Session Summary: Sage Chat Build
**Date**: 2026-03-06
**Status**: Complete — all 4 phases passed

---

## What Was Built

### Backend (`api/`)
| File | Purpose |
|------|---------|
| `api/__init__.py` | Package marker |
| `api/config.py` | Env var loading (CHROMA_DB_PATH, CHROMA_COLLECTION, SQLITE_DB_PATH, GCP_PROJECT, GCP_LOCATION, GEMINI_MODEL) |
| `api/models.py` | Pydantic v2 models: Message, ChatRequest, Source, ChatResponse, VideoItem, ChannelItem, HealthResponse |
| `api/search.py` | Hybrid search engine — ChromaDB semantic + BM25 keyword, fully self-contained (no MCP server import) |
| `api/gemini.py` | Vertex AI client — expand_query() and synthesize() with citation enforcement |
| `api/main.py` | FastAPI app — /api/chat, /api/videos, /api/channels, /api/health; CORS for localhost:3000 + *.vercel.app |
| `api/requirements.txt` | Dependencies: fastapi, uvicorn, chromadb, sentence-transformers, rank-bm25, google-genai, pydantic |
| `api/.env.example` | All env vars documented |

### Frontend (`sage_chat/`)
| File | Purpose |
|------|---------|
| `sage_chat/app/layout.tsx` | Root layout, dark theme, Inter font |
| `sage_chat/app/page.tsx` | Main page — renders ChatInterface |
| `sage_chat/app/globals.css` | Tailwind base + custom CSS (scrollbar, citation button styles) |
| `sage_chat/app/components/ChatInterface.tsx` | Top-level state manager using useReducer |
| `sage_chat/app/components/MessageList.tsx` | Scrollable message container with auto-scroll |
| `sage_chat/app/components/MessageBubble.tsx` | Renders messages; [SRC_N] tokens → clickable YouTube links |
| `sage_chat/app/components/SourceCards.tsx` | Horizontal scroll row of source cards below assistant messages |
| `sage_chat/app/components/ModeToggle.tsx` | Ephemeral/conversation toggle pill (lightning / brain icons) |
| `sage_chat/app/components/ChatInput.tsx` | Auto-resizing textarea, Enter to submit, send button |
| `sage_chat/app/components/Sidebar.tsx` | Collapsible drawer — channel browser + video browser |
| `sage_chat/app/components/TypingIndicator.tsx` | Animated three-dot bounce |
| `sage_chat/lib/api.ts` | Typed fetch functions: chat(), getVideos(), getChannels(), getHealth() |
| `sage_chat/package.json` | Next.js 14, React 18, TypeScript, Tailwind |
| `sage_chat/next.config.js` | Standalone output for Railway/Render deployment |
| `sage_chat/tailwind.config.js` | Dark theme colors, custom animations |
| `sage_chat/.env.example` | NEXT_PUBLIC_API_URL documented |

### Archive (`archive/mcp/`)
| File | Purpose |
|------|---------|
| `archive/mcp/yt_knowledge_mcp.py` | Original MCP server (deprecated, preserved for reference) |
| `archive/mcp/README.md` | Deprecation notice |

---

## Key Decisions Made

1. **BM25 built synchronously at startup** — FastAPI lifespan blocks until BM25 index is ready. Simpler than background thread, no partial-state window. With 249K chunks, expect 30-60s startup.

2. **BM25 corpus from ChromaDB** — chunks pulled from ChromaDB in 10K batches at startup. This gives chunk-level precision (vs. video-level from SQLite full_text), matching the MCP server pattern.

3. **No cross-encoder** — Deferred to Phase 6. MVP uses 0.7*semantic + 0.3*BM25 combined score.

4. **Word-reveal via setInterval** — Response arrives as batch; words revealed at 30ms intervals. Dispatch-based (no mutable ref juggling). `revealWords()` defined outside component for closure stability.

5. **History captured before new user message** — In ChatInterface, `state.messages` is read before dispatching `ADD_USER_MSG`, so the user's current query is not duplicated in the history array passed to the backend.

6. **CORS regex for Vercel** — `allow_origin_regex=r"https://.*\.vercel\.app"` handles wildcard subdomains. Development uses explicit `http://localhost:3000`.

---

## How to Run Locally

### Backend

```bash
cd yt_scraper_consultant

# Install dependencies (if not already installed)
pip install -r api/requirements.txt

# Set up env vars
cp api/.env.example api/.env
# Edit api/.env with your actual paths

# Authenticate with Google Cloud (one-time)
gcloud auth application-default login

# Start the server (reads .env automatically via python-dotenv)
uvicorn api.main:app --reload --port 8000
```

The server will log BM25 index build progress. Wait for "BM25 index ready" before sending requests. Health check: `curl http://localhost:8000/api/health`

### Frontend

```bash
cd yt_scraper_consultant/sage_chat

# Install dependencies (already done during QA)
npm install

# Set API URL (optional — defaults to http://localhost:8000)
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Development server
npm run dev
# Opens at http://localhost:3000

# Or production build
npm run build && npm start
```

---

## Open Issues / Blockers

1. **Interval cleanup (non-blocking)**: The word-reveal `setInterval` in `ChatInterface.tsx` is not cleaned up if the component unmounts during streaming. For a persistent SPA this is fine — add `useEffect` cleanup in v2.

2. **BM25 startup time**: With 249K chunks, first-run BM25 build may take 45-90 seconds. Consider adding a cache (pickle file) in v2 to skip rebuild if chunk count matches.

3. **No authentication on UI**: Per PRD scope, the frontend has no auth. Since this is a personal localhost tool this is acceptable. Add basic auth before deploying to a public Vercel URL.

4. **Archive migration**: `yt_knowledge_mcp.py` was **copied** to `archive/mcp/` — the original at project root is still present. The PRD says to "move" it. The original can be deleted manually if desired; we preserved it to avoid breaking any Claude Desktop config that still references it.

---

## What to Review

- `api/main.py` — the query pipeline (expand → search → deduplicate → synthesize)
- `api/search.py` — BM25 + ChromaDB hybrid scoring logic
- `sage_chat/app/components/ChatInterface.tsx` — state machine (useReducer + revealWords)
- `sage_chat/app/components/MessageBubble.tsx` — citation rendering (regex split → clickable spans)

---

## QA / Review Reports
- QA report: `.claude/logs/qa-sage-chat-2026-03-06.md` — **PASS**
- Code review: `.claude/logs/review-sage-chat-2026-03-06.md` — **Ready for use, no blockers**

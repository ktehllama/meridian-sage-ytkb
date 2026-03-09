# Meridian YTKB — Full Development History
*A complete session-by-session account from the first line of code to v3.8 stable.*
*Written to give any new Claude session full context on what was built, why, and how.*

---

## Part 1 — The Pipeline Era (v1.x–v2.7)
*Before the chat UI existed. This is the backend knowledge base.*

### What the project started as

The original goal was to scrape YouTube channels (starting with Y Combinator's @ycombinator), chunk transcripts, embed them into a vector database, and surface them as an MCP tool inside Claude Desktop. The idea: when working on a startup problem, ask Claude to consult the knowledge base and get back the most relevant video segments with timestamps.

### Core infrastructure built

**SQLite (`knowledge.db`)** — three tables:
- `channels` — channel handles and metadata
- `videos` — one row per video, `has_transcript` flag
- `transcripts` — `full_text` + `segments` as JSON array of `{text, start, duration}`

**ChromaDB (`yc_vectors/`)** — vector store:
- Collection name: `transcripts`
- Embedding model: `all-MiniLM-L6-v2` via `SentenceTransformerEmbeddingFunction`
- Chunks: ~150 words with 50-word overlap, respecting segment boundaries
- Each chunk stored with: `video_id`, `video_title`, `video_url`, `channel_name`, `start_time`, `end_time`, `timestamp_url`, `chunk_index`
- Chunk IDs: `{video_id}_chunk_{idx:04d}`
- Document format: `"{title}\n\n{chunk_text}"` (title prepended for semantic matching)

**`pipeline.py`** — unified ingestion script replacing legacy `yt_scraper.py` + `vector_builder.py`:
- Layer 1: yt-dlp fetches video list → youtube-transcript-api fetches transcripts → stored in SQLite
- Layer 2: reads SQLite, chunks transcripts, adds to ChromaDB
- Fully incremental — only processes videos not already embedded

**`yt_knowledge_mcp.py`** — FastMCP server (stdio transport) for Claude Desktop:
- `yt_search_knowledge_base(query, n_results=8)` — semantic search
- `yt_get_video_context(video_title, topic)` — deep dive into one video
- `yt_list_videos(channel_filter)` — list all indexed videos

### v2.x — search quality and scale hardening

**v2.0** fixed a critical 50K hard cap in ChromaDB pagination — beyond ~526 videos, incremental sync was re-embedding already-indexed content. Switched to paginated 10K-batch loops everywhere.

**v2.1** added a full channel queue system — SQLite `channel_queue` table, `queue add/run/status/reset` commands, `--sort-by views` to scrape top-N most-watched (not just newest), whitelist CSV support, run receipts.

**v2.2** added `queue remove` and `--scrape-only` flag for IP-safe scraping (fetch transcripts to SQLite without touching ChromaDB, run `sync` later from a different connection).

**v2.3** added audit tools: `yt_audit_channel` and `yt_scan_for_issues` to detect off-topic content, missing transcripts, low-engagement videos.

**v2.4** was a critical MCP fix: BM25 index build and cross-encoder load were blocking MCP startup (60-90 seconds). Moved both to background threads with a `bm25_cache.pkl` disk cache. MCP now starts in <2 seconds. Also added the `_is_twitch_chat()` guard to reject Twitch chat transcripts (username-density heuristic), and fixed 8 videos with raw `UC...` channel IDs instead of `@handles`.

**v2.5** fixed `yt_list_videos` speed: was scanning all 247K chunks to find which videos existed. Added `_get_embedded_video_ids_fast()` using the smaller `video_metadata` collection (~5K docs, one per video). Speed: 10-20s → <0.1s.

**v2.6** fixed `yt_list_videos` context-window overflow: returning all 4,879 individual video entries (~1.2MB) was too large for Claude's context. Changed default behavior to return a channel-level summary (~4KB for 84 channels). Channel-filtered calls return compact per-video lists.

**v2.7** was a major data operation: 228 previously unembedded videos (primarily @aswathdamodaranonvaluation) were synced into ChromaDB, bringing total chunks to **249,641**. Fixed a `@CGPGrey`/`@cgpgrey` case-sensitivity duplicate, registered 5 channels that existed in transcripts but not the channels table, and back-filled `chunk_count` metadata for 338 videos that had `chunk_count=0` from before the field was added.

---

## Part 2 — The Chat UI Is Born (2026-03-06, Session 1)
*Codename: "Sage Chat". This is where the web app starts.*

### Why the MCP approach was replaced

The Claude Desktop + MCP setup had a fundamental problem: every tool call permanently accumulated in context. Five searches = ~10K tokens persisted for the entire conversation, draining Claude Pro quota rapidly. The solution: build a purpose-built chat interface where we control token budget, model selection, and retrieval behavior end-to-end. Use Gemini 2.0 Flash on Vertex AI ($300 credit, ~$0.003-0.006/query).

### PRD written (`.claude/plans/prd-sage-chat.md`)

Key decisions locked in the PRD:
- **Stack**: FastAPI backend + Next.js 14 frontend (App Router)
- **AI**: Gemini 2.0 Flash via Vertex AI ADC (no API key, uses `gcloud auth application-default login`)
- **Search**: hybrid — ChromaDB semantic + BM25 keyword, 0.7/0.3 weighting
- **Query pipeline**: expand query (Gemini, 3 paraphrases) → search each variant → deduplicate → rank → synthesize
- **Two modes**: ephemeral (no history sent to Gemini) and conversation (full history)
- **Citations**: every factual claim must include `[SRC_N]` tags linking to YouTube timestamps
- **ChromaDB and SQLite**: READ ONLY from the chat API — all writes go through `pipeline.py`

### Architecture designed (`.claude/memory/decisions.md`)

The ADR established the full API contract:

```
POST /api/chat     — { query, mode, history[] } → { answer, sources[], mode }
GET  /api/videos   — paginated, filterable by channel
GET  /api/channels — list all channels with video counts
GET  /api/health   — { status, chroma_chunks, db_videos }
```

Query pipeline per request:
1. `expand_query()` — Gemini call, max 150 tokens, returns 3-4 paraphrases
2. `hybrid_search()` — semantic (ChromaDB) + BM25 (rank_bm25) per variant, merge + deduplicate by chunk_id
3. Re-rank: `score = 0.7 * semantic_score + 0.3 * bm25_norm`, take top 8
4. Format chunks as `[SRC_N] Title — MM:SS\n"text"`
5. `synthesize()` — Gemini with system prompt enforcing citation

BM25 corpus: pull all 249K chunks from ChromaDB in 10K batches at startup. Synchronous (blocks until ready). ~30-60s startup time. Acceptable because FastAPI won't serve requests during startup.

### Backend built (`api/`)

| File | What it does |
|------|-------------|
| `config.py` | Pydantic-based env var loading — single source of truth |
| `models.py` | Pydantic v2 models: `Message`, `ChatRequest`, `Source`, `ChatResponse`, `VideoItem`, `ChannelItem` |
| `search.py` | Hybrid search engine — ChromaDB semantic + BM25. Module-level singletons init in FastAPI lifespan |
| `gemini.py` | Vertex AI client — `expand_query()` and `synthesize()`. Lazy-init `_client` singleton |
| `main.py` | FastAPI app — routes, CORS (`localhost:3000` + `*.vercel.app` regex), lifespan startup |
| `requirements.txt` | fastapi, uvicorn, chromadb, sentence-transformers, rank-bm25, google-genai, pydantic |

Key decision: `api/search.py` does NOT import `yt_knowledge_mcp.py`. The MCP server spawns background threads at module level — importing it would trigger those side effects. Search logic was copied inline.

### Frontend built (`sage_chat/`)

Next.js 14 App Router, TypeScript, Tailwind CSS.

State machine in `ChatInterface.tsx` using `useReducer`:
```typescript
type State = {
  messages: ChatMessage[];
  mode: 'ephemeral' | 'conversation';
  loading: boolean;
  sidebarOpen: boolean;
  error: string | null;
}
```

Word-reveal animation: response arrives as a batch, then `setInterval(30ms)` dispatches `APPEND_WORD` actions one at a time to simulate streaming.

Citation rendering in `MessageBubble.tsx`: regex splits response on `[SRC_N]` tokens and replaces them with clickable `<button>` tags linking to YouTube timestamp URLs.

### QA passed (`.claude/logs/qa-sage-chat-2026-03-06.md`)

All 9 acceptance criteria passed. Frontend built with zero TypeScript errors. Backend Python files all passed AST parse. System declared ready.

---

## Part 3 — Chat UI Fixes Round 1 (2026-03-06, Session 2)
*Token tracking, stop button, source cards redesign, chat persistence.*

### Usage tracking added

`api/gemini.py` was updated to read `response.usage_metadata` after each `generate_content()` call and return `(text, usage_dict)`. `api/main.py` unpacks this and passes it into `ChatResponse`. Frontend displays token counts + per-request cost (`$0.075/1M input, $0.30/1M output` — Gemini 2.0 Flash Vertex AI pricing).

### Stop button

`ChatInput.tsx` got an `onStop?: () => void` prop. While `disabled=true` (loading), the send button becomes a red square stop button. `ChatInterface.tsx` added `abortRef` (AbortController) and `revealIntervalRef`. `handleStop()` aborts the fetch and clears the word-reveal interval simultaneously.

### Citation rendering fixed — the multi-`<p>` bug

The original `MessageBubble.tsx` split content on `[SRC_N]` with regex and passed each segment to a separate `ReactMarkdown` block. This created a new `<p>` tag for every segment, breaking inline citation flow.

Fix: switched to `rehype-raw` plugin, which allows raw HTML in markdown. A preprocessing pass converts `[SRC_N]` and `[SRC_N, SRC_M, ...]` tokens into `<cite data-ids="N,M">` HTML tags before passing the entire content to a single `ReactMarkdown`. A custom `cite` component renders these as `<sup><button>` pairs. This was the correct fix — one markdown pass, inline superscripts.

Citation order also fixed: `[SRC_3].` was rendering as superscript-then-period. Added a pre-pass regex to move citations after sentence-ending punctuation: `$1$2` → `$2$1`.

Citation deduplication: if `[SRC_3]` appeared three times in a response, only the last occurrence was kept (avoids footnote clutter while preserving the citation closest to its final use).

### SourceCards redesigned

Replaced horizontal scroll row with a collapsible toggle (collapsed by default). Shows "N sources" with a rotating chevron. Expanded: numbered badge, title + timestamp, quote snippet (2 lines), YouTube icon. Usage display (token counts + cost) combined into the same row as the sources toggle — right-aligned.

### Chat persistence added

`lib/api.ts` gained `StoredChat` interface and `loadChats()`, `saveChat()`, `deleteChat()`, `renameChat()`, `newChatId()` functions. All chats saved to `localStorage` under `sage_chats` key, capped at 50 entries.

`Sidebar.tsx` fully rewritten: added "Chats" as the default tab. Shows all saved chats with mode badge (Quick/Deep), message count, timestamp, inline rename (pencil icon → input → Enter to commit), delete (trash icon, hover-reveal), active chat highlighted with indigo accent. "New Chat" button at top.

`ChatInterface.tsx` gained `currentChatIdRef` (a ref, not state — zero re-render cost), save effect using `saveChat()`, and `handleDeleteChat` / `handleRenameChat` handlers.

---

## Part 4 — Hero Screen + Animated Background (2026-03-07)
*UnicornBackground WebGL animation, suggestions, welcome phrases.*

### `lib/unicornEmbed.js` built

Custom utility that injects a Unicorn Studio WebGL scene into any DOM element. Features:
- `cropPx` option to hide the bottom watermark badge via overflow clip
- Lazy-loads the Unicorn Studio SDK script on first call
- Injects CSS to suppress the watermark link
- Handles resize events to keep canvas properly sized

### `UnicornBackground.tsx` built

React wrapper that mounts the Unicorn Studio animation (project ID: `qFZJmsATe1qivAJHWPuL`) into an `absolute inset-0` layer. Uses `useEffect` + `ref` so the embed fires after hydration (not during SSR).

**Critical performance constraint identified and fixed later (v3.2)**: this component must NEVER conditionally unmount/remount. Each mount creates a new WebGL context. Unmounting doesn't destroy it. Navigating home → chat → home repeatedly accumulates render loops and crashes the GPU. The fix (applied in v3.2) was to always keep `UnicornBackground` mounted and use CSS `hidden` class to hide it when not on the home screen.

### Hero screen built in `MessageList.tsx`

When `messages.length === 0 && !loading`, shows:
- `UnicornBackground` full-viewport animation
- Dark radial vignette overlay (`rgba(10,10,15,0.88)` → transparent) behind text for legibility
- Gradient `<h1>` "Sage" / later "Meridian" title using `linear-gradient(135deg, #818cf8 → #a5b4fc → #c7d2fe)` with `WebkitBackgroundClip: text`
- Random welcome phrase from a pool (started at 9, expanded to 24 entries)
- Subtitle: "Ask anything from the cornucopia of knowledge."
- Suggestions hover panel: 3 randomly picked starter queries from a pool of 20

### Suggestions panel

Hover-triggered (not click-triggered) panel with a 200ms grace-period timer on mouse-leave (so moving mouse from "Suggestions" label to a card doesn't collapse it). Cards have entrance/exit CSS keyframe animations. A shuffle button re-picks 3 random suggestions with a 160ms transition. `onSuggestionClick` callback fires the suggestion directly as a chat query.

Welcome phrase SSR fix: moved from `useState` initializer (which runs on server and causes hydration mismatch "Text content does not match server-rendered HTML") to `useEffect` (client-only). The phrase starts as `null` and is set after mount.

---

## Part 5 — UI Polish Passes (2026-03-08, Sessions 1-2)

### v2.8 — Input + toggle polish

- `resizeTextarea()` extracted and wired to `onInput` — textarea now auto-expands as you type (was only expanding on React re-renders, not on actual keystrokes in an uncontrolled textarea)
- Max textarea height reduced to 15vh with scroll beyond that
- Q/D mode toggle redesigned: blurple color scheme (`#6570fc`), active state has inner glow + text shadow
- Input bar glassmorphism restored: `rgba(255,255,255,0.03)` + `backdrop-filter: blur(12px)`
- Send button: glowing vector icon with `drop-shadow` filter (circle background removed)
- Auto-restore of last chat on page load removed — refreshing always shows the homepage

### v2.9 — Full black background

Systematic pass: `--background` `#0f0f0f` → `#000000`, `page.tsx` root `bg-black`, `ChatInterface.tsx` header `bg-black`, `MessageList.tsx` scroll area `bg-black`.

### v3.0 — UX critique pass

A full UX audit was run and all issues fixed:

- **Focus ring** restored on input bar: `focus-within:ring-1 focus-within:ring-[#6570fc]/40` (had been accidentally removed)
- **Q/D toggle** fixed at `w-[4.5rem]` — both labels always visible, no layout shift when switching modes
- **Suggestions hover-trap**: replaced instant `onMouseLeave` close with 200ms timer. Moving mouse from label to card no longer collapses dropdown.
- **Hero overflow**: removed `overflow-hidden` from hero container — it was clipping the absolutely-positioned suggestions dropdown
- **Copy button** added to assistant bubbles: appears on `group-hover/bubble:opacity-100`, copies content with `[SRC_N]` tokens stripped, shows checkmark + "Copied" for 1.5s via clipboard API
- **Source quote** expanded from `line-clamp-1` → `line-clamp-2`
- **Budget display** improved: 5 decimal places → 2 (`$299.98 left`), `text-emerald-500`
- **`transition-colors` fix** in `globals.css`: global `* { transition-property }` was missing `color`, causing all Tailwind `transition-colors` utilities to snap instantly
- **Dead `.citation-btn` CSS** removed — citations had moved to inline Tailwind in MessageBubble

---

## Part 6 — Rebrand: Sage → Meridian (2026-03-08)

### Why

"Sage" felt too generic in the AI space — dozens of products use that name. "Meridian" fits the ocean/navigation theme of the project (YouTube knowledge navigated like charting a course), has no AI connotations, and sounds more distinctive.

### What changed

- Page title, header brand, hero `<h1>`, input placeholder, avatar letters (S → M)
- New header logo: inline SVG globe with prime meridian arc and equator line, ocean-to-indigo gradient (`#22d3ee` → `#0ea5e9` → `#818cf8`), clickable to return home
- Internal project folder name stays `sage_chat` — treated as codename
- Gemini system prompt updated: "You are Sage" → "You are Meridian"

---

## Part 7 — Performance Fixes (2026-03-07, PRD: `.claude/plans/prd-perf-fix.md`)

The chat UI was getting progressively slower with each session — confirmed by code audit as 4 compounding issues:

### Fix 1: `saveChat` O(N×M) rewrite

Old code called `loadChats()` on every save: `JSON.parse` all 50 chats × all messages, filter, unshift, `JSON.stringify` everything back. As chats accumulated this was O(N×M) and caused multi-second freezes.

Fix: in-memory `Map<id, StoredChat>` cache initialized once from localStorage. Saves only write to localStorage, never read from it. `loadChats()` populates the cache on first call and stays consistent.

### Fix 2: `handleSubmit` dep array

`useCallback` dep array included `state.messages` — a new array reference on every `APPEND_WORD` dispatch (33 times per second during word-reveal). This recreated `handleSubmit` 33×/sec, cascading to `handleVideoSelect` and all props passed to `MessageList` and `ChatInput`.

Fix: removed `state.messages` from the dep array. History is read from the current state at call time via the reducer — no stale closure issue.

### Fix 3: `React.memo` on message components

Every `APPEND_WORD` action re-rendered the entire message list. Each `MessageBubble` ran its `useMemo` citation preprocessing on every parent re-render, even for fully-completed messages with stable props.

Fix: `React.memo` wrapped `MessageList` and `MessageBubble`. Completed messages no longer re-render during word-reveal of the latest message.

### Fix 4: `UnicornBackground` always-mounted

As documented in Part 4: changed from conditional render to always-mounted + CSS `hidden`. Also fixed `handleNewChat` to abort in-flight fetches via `abortRef.current.abort()`, and fixed `CLEAR_CHAT` reducer to reset `loading: false` (was blocking next submission after clearing). Added cleanup return to `saveEffect`.

---

## Part 8 — Theming System + Settings Panel + Favicon (2026-03-08)

### CSS variable theming system

Replaced all hardcoded hex colors across all components with semantic CSS variables in `globals.css`:

**20 tokens:**
- `--bg-{base, surface, sidebar, elevated, hover, avatar}`
- `--border-{primary, subtle, avatar}`
- `--text-{primary, secondary, body, muted, dim, faint, faintest}`
- `--input-{bg, border}`
- `--scrollbar-{thumb, hover}`

Dark mode (`:root`): near-black bases, pure black `--bg-base`.
Light mode (`[data-theme="light"]`): warm Solarized cream palette — `--bg-base: #FDF6E3`, `--bg-surface: #EEE8D5`, `--bg-sidebar: #E8E2D0`. NOT pure white.

Accent/indigo colors stay hardcoded — they work on both themes.

All components migrated to `bg-[var(--bg-surface)]` Tailwind arbitrary syntax.

### Anti-flash script

Inline `<script>` in `app/layout.tsx` reads `localStorage.getItem('meridian_theme')` before React hydrates and applies `data-theme` to `<html>`. Prevents white flash on dark-mode users.

### `lib/theme.ts`

`getTheme()`, `setTheme(theme)`, `applyTheme(theme)` helpers. Persists to `localStorage` key `meridian_theme`.

### `lib/profiles.ts`

Profile CRUD — add, rename, delete, set active — using `localStorage` key `meridian_profiles`. Default profile protected from deletion.

### SettingsPanel

Right-side drawer (gear icon trigger in header). Two sections:
1. Theme toggle: Dark ↔ Light Solarized, instant apply via `applyTheme()`
2. Profile list: add/rename/delete/switch, "coming soon" note for personal knowledge bases. Add profile: text input that auto-dismisses to "+ Add profile" button on blur when empty.

### Favicon

Meridian starburst SVG at `public/favicon.svg`. Dark circle background, indigo radial gradient, 8 spokes + crossbars. Registered in `app/layout.tsx` metadata.

---

## Part 9 — UX Polish Sprint (2026-03-08, Multi-agent Wave 1–2)

This sprint used 4 parallel implementer agents for independent tasks.

### Smart chat naming (`lib/chatName.ts`)

Problem: chat names were `firstUserMsg.content.slice(0, 40)` — asking the same question twice gave duplicate names.

Solution: pure-TypeScript TF-IDF-like keyword scorer:
1. Tokenize `userMsg + assistantMsg.slice(0, 500)`
2. Remove stopwords, keep words ≥ 4 chars
3. Score by frequency; boost words appearing in userMsg ×1.5 (user's words define the topic)
4. Take top 4 words, Title Case
5. Output: e.g. "Startup Fundraising Pitch Investors"
6. Fallback: `userMsg.slice(0, 40)` if no words survive

Timing in `ChatInterface.tsx`: name generated once after first complete exchange (user message + non-empty assistant reply both exist). Cached in `chatNameRef` so it never overwrites.

### @-mention channel autocomplete (`ChatInput.tsx`)

Typing `@` in the chat input triggers a floating dropdown above the input bar. Implementation:
- `onInput` event: scans backwards from cursor for `/@(\w*)$/` pattern
- Fetches channel list from `GET /api/channels`, cached in `channelCacheRef` after first fetch (never fetches again)
- Substring match: `@pet` matches `@PeterAttiaMD`, `@petitemollier`, etc.
- Dropdown shows up to 6 results (name + video count), loads 6 more on scroll near bottom
- Keyboard nav: ArrowUp/Down move highlight, Enter/Tab insert, Escape dismiss
- `insertMention()`: replaces the `@query` fragment with `@ExactChannelName ` (+ trailing space), moves cursor after insertion
- `@@` double-prefix bug fixed: API returns channel names with leading `@`; `insertMention` strips it before prepending one

### Sidebar relative timestamps

Replaced `toLocaleDateString()` with `relativeTime(ts: number)` helper:
- < 1 min: "just now"
- < 60 min: "X min ago"
- < 24h: "X hours ago"
- = 1 day: "Yesterday"
- 2-6 days: "X days ago"
- 1-3 weeks: "X weeks ago"
- 1-5 months: "X months ago"
- 23-27 weeks: "half a year ago"
- 7-11 months: "X months ago"
- ≥ 1 year: "Jan 8, 2025" (actual date)

### Light mode contrast audit

Systematic replacement of `white/N` opacity values (invisible on Solarized cream) with CSS variable tokens:
- Inactive Quick/Deep pill buttons: `text-white/25` → `text-[var(--text-dim)]`
- Pill hover: `hover:text-white/50` → `hover:text-[var(--text-muted)]`
- Pill separator: `border-white/[0.06]` → `border-[var(--border-primary)]`
- SettingsPanel theme toggle: hardcoded `text-[#c4b5fd]` → `text-[var(--text-primary)]` for selected label
- Added `--pill-active-text` CSS variable: `#c4b5fd` (dark) / `#3730a3` (light indigo-900)

### Dark mode text readability

- `--text-faint: #505050` → `#686868`
- `--text-faintest: #404040` → `#545454`
- SourceCards: source quote → `--text-muted`, timestamp → `--text-dim`
- MessageBubble: copy button → `--text-dim`, hover → `--text-secondary`, "response stopped" → `--text-muted`
- ChatInput footer hints: bumped to `--text-muted`

---

## Part 10 — Floating Chat Bar (2026-03-08, Wave 4)

Changed the chat input from a docked bottom bar to a floating overlay — matching Claude.ai and ChatGPT's UX.

**`ChatInput.tsx`**: Added `floating?: boolean` prop. When `true`: `absolute bottom-6 left-0 right-0 px-4` positioning, no `border-t`, deeper box shadow (`0 8px 40px rgba(0,0,0,0.45)`).

**`ChatInterface.tsx`**: MessageList and ChatInput wrapped in `relative flex flex-col flex-1 min-h-0` container. ChatInput is now positioned absolutely over MessageList.

**`MessageList.tsx`**: Chat scroll container inner div gets `pb-32` padding so the last message clears the floating bar.

**UnicornBackground**: Already `h-full` — now stretches naturally to full viewport height since the input no longer eats space at the bottom.

---

## Part 11 — @-mention Highlight + Scrollbar Polish (2026-03-08)

### Blurple mention highlight

Added Discord-style `@channel` highlighting directly inside the textarea using a mirror-div overlay technique:

- `mirrorRef`: a `div` behind the textarea, rendered with `dangerouslySetInnerHTML`
- `buildHighlightHTML(text, validNames)`: HTML-escapes the raw text, then wraps valid `@handles` in `<span style="color:#818cf8;background:rgba(99,102,241,0.15)">`
- Textarea has `color: transparent` and `caretColor: var(--text-body)` — the caret is visible but text is invisible, showing the mirror's colored version underneath
- `validChannelNames` state: Set of lowercase channel names fetched alongside the dropdown results, used to validate which `@words` get highlighted

### Scrollbar polish

`.mention-scroll` CSS class added to `globals.css`:
```css
.mention-scroll::-webkit-scrollbar-thumb { background: transparent; }
.mention-scroll:hover::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); }
```
This hides the scrollbar thumb on mount (no jarring scroll track appearing with 6 items), revealing it only on hover.

---

## Part 12 — Centering Fix (2026-03-08)

### The bug

After adding the mirror overlay for @-mention highlighting, the entire textarea content (Quick/Deep pill + textarea + send button) was visually shifted to the upper portion of the glassmorphism pill. The YOUR_USERNAMEmatical center was incorrect.

### Root cause

The mirror was `absolute inset-0` inside a `relative flex-1` wrapper. An absolutely-positioned element is out of normal document flow — it contributes nothing to the wrapper's height. So the `flex-1` wrapper had only the textarea's intrinsic height (determined by `rows={1}`, ~1 line). The parent pill's `items-center` was centering this zero-or-one-line-tall box, which visually positioned content too high in the pill.

Multiple failed fixes: removing `self-stretch`, adding explicit `padding: 0`, adding `border-0` — all irrelevant because the root cause was the flow issue, not padding.

### Fix: CSS Grid overlay

Replaced `relative flex-1` wrapper + `absolute inset-0` mirror with a CSS Grid container:

```tsx
<div className="flex-1 min-w-0" style={{ display: 'grid' }}>
  {/* Mirror — in normal flow, determines grid row height */}
  <div ref={mirrorRef} style={{ gridArea: '1/1', ... }} />
  {/* Textarea — same grid cell, overlays mirror */}
  <textarea style={{ gridArea: '1/1', ... }} />
</div>
```

Both elements share `gridArea: '1/1'`. The mirror is in normal document flow, so it naturally determines the grid cell's height. The parent pill's `items-center` now has a properly-sized element to center. `resizeTextarea()` was removed entirely — the CSS Grid auto-sizes as the mirror wraps.

### Scrollbar state fix

Second bug in same session: `.mention-scroll:hover` CSS doesn't fire during scroll-wheel/trackpad events. The scrollbar thumb stayed transparent even when the user was actively scrolling, only appearing after a React re-render (e.g. pressing an arrow key triggered `setMentionIndex` → re-render → CSS recalculated → hover state evaluated fresh).

Fix: `mentionScrolled` React state. On first `onScroll` event, `setMentionScrolled(true)` removes the `.mention-scroll` class, making the native scrollbar immediately visible. Resets to `false` each time the dropdown opens.

---

## Part 13 — Project Structure + Deployment (2026-03-08, v3.8 Stable)

### Repository organization

Files reorganized before GitHub push:
- `docs/` — TODO.md, OVERVIEW.md, MANUAL.md (reference docs)
- `archive/` — legacy/unused scripts: `vector_builder.py`, `smoke_test.py`, `APIgeminiai.py`, `unicornEmbed.js` (copy), `v2/` (old pipeline versions), `yt_scraper.py`, `yt_knowledge_mcp.py`, `start_api.ps1`, `queue_channels.txt`, `whitelist_example.txt`
- Root: only active files (`pipeline.py`, `api/`, `sage_chat/`, `start.sh`, `CHANGELOG.md`, `CLAUDE.md`)

### `start.sh`

Unified bash startup script that works on Windows (Git Bash) and Linux/Raspberry Pi:
- Resolves project root from script location (works regardless of `cd` path)
- Exports all env vars (`CHROMA_DB_PATH`, `SQLITE_DB_PATH`, etc.)
- Auto-activates venv (checks both `venv/bin/activate` and `venv/Scripts/activate`)
- Frees ports 3000 and 8000 before starting (using `fuser` on Linux, `netstat`+`taskkill` on Windows Git Bash)
- Starts `uvicorn api.main:app --port 8000` in background
- Starts `npm start` (or `npm run dev` with `--dev` flag) in background
- `trap cleanup EXIT INT TERM` — Ctrl+C kills both processes cleanly

### `.gitignore` fixed

Previous `.gitignore` was corrupted — mixed UTF-8 and UTF-16 encoding. Git couldn't read it, so large files were tracked. Rewrote as clean UTF-8. Now excludes:
- `yc_vectors/`, `bm25_cache.pkl`, `knowledge.db` (runtime data, rsync to Pi separately)
- `node_modules/`, `sage_chat/node_modules/`, `sage_chat/.next/`
- `**/__pycache__/`, `venv/`, `.env`, `.env.local`

### GitHub push

Repository: `ktehllama/meridian-sage-ytkb`. Push required squashing history because the previous commits had tracked large binary files (ChromaDB `chroma.sqlite3` at 1.96GB, BM25 cache at 478MB, ChromaDB data bins at 401MB). Used `git checkout --orphan clean-main` to create a fresh single-commit history with no binary baggage.

---

## Current State: v3.8 Stable

### What's running

- **249,641 transcript chunks** across 80+ YouTube channels (YC, Lex Fridman, TED, Peter Attia, Aswath Damodaran, CGP Grey, Neural Nine, and others)
- **Backend** (`api/`): FastAPI + hybrid search (BM25+semantic) + Gemini 2.0 Flash query expansion + synthesis
- **Frontend** (`sage_chat/`): Meridian chat UI, Next.js 14, dark/light theming, floating input, @-mention, smart chat naming, citation superscripts
- **Single command to start**: `bash start.sh` (or `./start.sh --dev`)

### What's not done yet

| Task | Status | Blocker |
|------|--------|---------|
| UnicornBackground canvas color matches `--bg-base` in light mode | Pending | Need to research Unicorn Studio JS API or Service Worker intercept to patch `backgroundColor` in the animation JSON at runtime |
| Raspberry Pi deployment | Ready | Just needs `rsync` of `yc_vectors/`, `knowledge.db`, `bm25_cache.pkl` + `bash start.sh` |
| Personal knowledge base per profile | Planned | No spec written |

### Key architectural facts for any continuation

- **ChromaDB embedding function**: must be `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")` — must match at collection creation time. Using any other function against an existing collection causes a conflict error.
- **BM25 startup**: synchronous, 30-60s, blocks until ready. `bm25_cache.pkl` caches it across restarts (invalidated when chunk count changes).
- **Vertex AI auth**: Application Default Credentials — run `gcloud auth application-default login` once. No API key file.
- **Chat history**: persisted to `localStorage` key `sage_chats` (up to 50 chats). Never sent to the server — the backend is stateless per request.
- **UnicornBackground**: must stay always-mounted. CSS `hidden` class hides it, never `{condition && <UnicornBackground />}`.
- **`handleSubmit` deps**: must NOT include `state.messages` — re-creates 33×/sec during word-reveal.
- **Theme**: dark is `:root`, light is `[data-theme="light"]` on `<html>`. Applied via `applyTheme()` which sets both the attribute and localStorage.
- **`start.sh`** is the canonical way to start the full app. `start_api.ps1` is archived.

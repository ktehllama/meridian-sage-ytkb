# Sage YTKB — Changelog

---

## v3.1 — 2026-03-08

### Rebrand: Sage → Meridian
- Product renamed from **Sage** to **Meridian**. "Sage" felt too AI-generic; Meridian fits the ocean/navigation theme and has no AI connotations.
- All user-facing references updated: page title, header brand, hero `<h1>`, input placeholder, avatar letters (S → M)
- Folder/project name remains `sage_chat` — treated as the internal project codename
- Added header logo: inline SVG globe with prime meridian arc and equator line, ocean-to-indigo gradient (`#22d3ee` → `#0ea5e9` → `#818cf8`). Sits left of the "Meridian" wordmark in the top bar, clickable to return home.

---

## v3.0 — 2026-03-08

### UI: Full UX Critique Pass (`sage_chat/`)
*Critiqued, implemented, QA'd (build PASS), then re-critiqued and patched.*

**ChatInput.tsx**
- Restored focus ring on input bar: `focus-within:ring-1 focus-within:ring-[#6570fc]/40` (was removed in a prior session)
- Q/D mode toggle now always shows both labels ("Q Quick" / "D Deep") at fixed pill width `w-[4.5rem]` — no layout shift on mode switch, labels are always readable at `sm`+ breakpoints

**MessageList.tsx**
- Suggestions hover-trap fixed: replaced instant `onMouseLeave` close with a 200ms grace-period timer (`leaveTimerRef`); moving the mouse from the label to a card no longer collapses the dropdown
- "Suggestions" label now has `cursor-pointer` and `hover:text-[#909090]` to signal interactivity
- Hero screen `overflow-hidden` removed — it was clipping the absolutely-positioned suggestions dropdown
- Suggestions dropdown capped at `max-h-64 overflow-y-auto` to prevent viewport overflow on small screens

**MessageBubble.tsx**
- Assistant message bubble background lifted: `bg-[#1a1a1a]` → `bg-[#111111]`, border `#2a2a2a` → `#2f2f2f` (more visible on pure black)
- Copy button added: appears on hover (`group-hover/bubble:opacity-100`), shows checkmark + "Copied" for 1.5s; copies clean text with `[SRC_N]` citation tokens stripped

**TypingIndicator.tsx**
- Bubble bg/border updated to match MessageBubble: `bg-[#111111] border border-[#2f2f2f]`

**SourceCards.tsx**
- Source toggle text brightened: `text-[#505050]` → `text-[#707070]`, hover `#808080` → `#999999`
- Source quote expanded: `line-clamp-1` → `line-clamp-2` for more context

**ChatInterface.tsx**
- Budget display: 5 decimal places → 2 (`$299.98 left`); tooltip updated to "API budget: $X.XXXX spent of $300.00 total"

**Sidebar.tsx**
- Video search empty state: shows "No videos matching '...'" or "No videos found." when filtered list is empty

**globals.css**
- Global `* { transition-property }` rule: added `color` to the property list — was previously omitting it, which caused all `transition-colors` Tailwind utilities to snap instantly (no color transition on hover for any element)
- Removed dead `.citation-btn` CSS class (was never used; citations render via inline Tailwind in MessageBubble)

---

## v2.9 — 2026-03-08

### UI: Full Black Background Pass (`sage_chat/`)
- `globals.css`: `--background` changed from `#0f0f0f` → `#000000`
- `page.tsx`: root `<main>` background changed to `bg-black`
- `ChatInterface.tsx`: top header bar changed to `bg-black`
- `MessageList.tsx`: scrollable chat message area explicitly set to `bg-black`
- Sidebar left intentionally unchanged (drawer overlay sits on top of main canvas)

---

## v2.8 — 2026-03-08

### UI Polish Pass (`sage_chat/`)

**Hero screen (`MessageList.tsx`)**
- Welcome phrase now picked client-side only via `useEffect` (was `useState` initializer) — fixes Next.js hydration mismatch error ("Text content does not match server-rendered HTML")
- Expanded welcome phrase pool from 9 → 24 entries; added nerdier, more personality-driven lines
- Removed YC-specific references from phrases ("YC wisdom" → "wisdom", "YC partner" → "consultant", dropped Paul Graham / YC talk lines)
- Updated subtitle from "Ask anything from your curated video library." → "Ask anything from the cornucopia of knowledge."
- "Suggestions" label lightened to `#707070` (was `#585858`)

**Input bar (`ChatInput.tsx`)**
- Textarea auto-resize fixed: was tied to React re-renders only (uncontrolled textarea = no re-renders on typing). Extracted `resizeTextarea()` and wired to `onInput` — now expands as you type
- Max textarea height reduced to 15vh; scrollbar appears beyond that
- Separator between hero and input bar made more visible (`border-white/[0.09]`, was `border-white/5`)
- "Enter to send" footer text brightened to `white/45` (was `white/25`)
- Input bar glassmorphism restored: `rgba(255,255,255,0.03)` + `backdrop-filter: blur(12px)`
- Q/D mode toggle: kept segmented pill shape; switched color scheme to blurple (`#6570fc`) — pill border, active glow, and text shadow all use that color (was purple `#9555ff`)
- Separator between Q/D pill and textarea changed to `border-white/[0.06]` (was stark `border-white/8`)
- Send button: glowing vector icon (`#6570fc` + `drop-shadow`) restored; circle background removed

**App behaviour (`ChatInterface.tsx`)**
- Removed auto-restore of last chat on page load — refreshing now always shows the homepage. Previous chats remain accessible via the sidebar.

---

## v2.7 — 2026-03-06

### Data Fix: 0-Chunk Channels + @cgpgrey Duplicate + Meta Chunk Counts

**Root cause:** Channels scraped with `--scrape-only` never had `sync` run afterward, leaving
transcripts in SQLite but no embeddings in ChromaDB. Additionally, meta_collection entries from
before v2.0 had `chunk_count=0` stored in metadata (field wasn't written until v2.0 fix), causing
`yt_list_videos` to display 0 chunks even for fully-embedded channels.

**Data operations (no code changes):**
- **@cgpgrey casing merge** — moved 1 video from `@CGPGrey` → `@cgpgrey`; deleted `@CGPGrey`
  channel row. Prevents duplicate channel entries in `yt_list_videos`.
- **Registered 5 add-from-csv channels** — `@TED`, `@TEDx`, `@NeuralNine`, `@eucroix`,
  `@lexfridman` added to `channels` table (they came from `add-from-csv` which doesn't register
  channels; they were invisible in `yt_list_videos` channel summary).
- **`pipeline.py sync`** — embedded 228 previously-missing videos / 16,157 new chunks.
  Total: 249,641 chunks. Primarily `@aswathdamodaranonvaluation` content that was scraped but
  never embedded.
- **Meta chunk_count migration** — scanned all 249k chunks, recomputed per-video chunk counts,
  updated 338 `video_metadata` entries that had stale `chunk_count=0`. `yt_list_videos` now
  shows accurate counts for all channels including pre-v2.0 videos.

---

## v2.6 — 2026-03-06

### MCP: `yt_list_videos` context-window fix (`yt_knowledge_mcp.py`)
- **Default (no filter)**: now returns a **channel-level summary** (~4KB for 84 channels) instead
  of all 4,879 individual video entries (~1.2MB). Fixes "tool result too large" error in Claude.
- **With `channel_filter`**: returns a compact one-line-per-video list with `[VIDEO_ID] title  Nch`
  format — no full URLs, capped titles. ~20KB for largest channels.
- Extracted `_get_chunk_counts_from_meta()` helper to avoid duplicating meta_collection scan.
- Updated tool docstring to guide Claude: use default for discovery, then filter by channel.

---

## v2.5 — 2026-03-06

### Scale-Up Speed Fixes (`pipeline.py`, `yt_knowledge_mcp.py`)
- **`yt_list_videos` MCP tool** — rewrote to read video list from SQLite `videos` table and chunk
  counts from `video_metadata` collection (~5k docs) instead of scanning all 247k chunks. Speed:
  10-20s → < 0.5s. Full-scan kept as fallback if SQLite not available.
- **`_get_embedded_video_ids_fast(meta_collection)`** — new helper that scans the `video_metadata`
  collection (~5k docs, one per video) instead of all 247k chunks to find which videos are embedded.
  Replaces `_get_embedded_video_ids(collection)` in `embed_new_videos`, `cmd_status`, `cmd_sync`,
  and `cmd_add_channel`. Each call: 5-10s → < 0.1s.
- **`has_transcript` SQLite index** — added `idx_videos_has_transcript` to `init_db()` schema.
  Makes every `SELECT id FROM videos WHERE has_transcript=1` use an index scan. Future-proofs for
  50k+ video scale.

---

## v2.4 — 2026-03-05

### MCP Startup Fix (CRITICAL) (`yt_knowledge_mcp.py`)
- **Background BM25 thread + disk cache** — BM25 index now builds in a daemon thread instead of
  blocking MCP startup. Cache saved to `bm25_cache.pkl` (chunk-count invalidation). MCP starts
  in < 2 seconds; first search shows `(BM25 index building in background — rerun for hybrid results)`
  if index not yet ready
- **Cross-encoder loaded in background** — `cross-encoder/ms-marco-MiniLM-L-6-v2` now loaded via
  background thread; falls back to semantic-only scoring until ready
- **`BM25_CACHE_PATH` env var** added; added to `claude_desktop_config.json`

### Data Cleanup
- **Deleted 12 @geohotarchive Twitch chat transcripts** — removed from SQLite `transcripts` table,
  reset `has_transcript=0` in `videos`, deleted 1,838 ChromaDB chunks
- **Fixed 8 UC... channel IDs** — re-fetched metadata and updated SQLite + ChromaDB for 8 videos
  that had raw `UC...` IDs instead of `@handles` (`@lexfridman`, `@NeuralNine`, `@eucroix`,
  `@TED` ×2, `@CGPGrey`, `@TEDx` ×2)

### Pipeline Fixes (`pipeline.py`)
- **`_is_twitch_chat()` guard** — detects Twitch chat transcripts by lowercase-username density
  (`[a-z][a-z0-9_]{2,}: ` pattern >8 matches/1000 chars); called in `fetch_transcript()` before
  storing — rejects chat without storing. Avoids false positives on UPPERCASE speaker labels
- **Fix `cmd_add_from_csv` channel handle** — swapped `uploader_id`/`channel_id` priority so
  `@handle` is always preferred over raw `UC...` ID
- **`fix-channel-ids` command** — new CLI command to re-fetch metadata for any videos with UC...
  handles and update both SQLite and ChromaDB (delete + re-add with corrected `channel_name`)
- **`cmd_status()` speed fix** — replaced O(n_chunks) ChromaDB full scan with SQLite `channels`
  table lookup; status now returns in < 1 second

### New: `smoke_test.py`
- 8 automated checks: SQLite tables, video/transcript count consistency, no UC... handles,
  no Twitch chat transcripts, ChromaDB connectivity, chunk count, ratio plausibility, semantic search
- Run: `python smoke_test.py` → `All 8 checks passed.`

---

## v2.3 — 2026-03-03

### MCP: Audit Tools (`yt_knowledge_mcp.py`)
- **New tool `yt_audit_channel(channel, sort_by)`** — lists every video for a channel with
  view count, duration, transcript status, video ID, and URL. Sort by `views` (default),
  `duration`, or `title`. Use to manually eyeball a channel for off-topic content.
- **New tool `yt_scan_for_issues(channel, expected_topics)`** — automated heuristic scan:
  - Suspicious title keywords (shorts, reaction, vlog, gaming, live stream, unboxing, etc.)
  - Low engagement: view count < 10% of channel median (only fires when median >= 5K views)
  - Missing transcripts (video in DB but not searchable)
  - Optional `expected_topics` param gives Claude context for judging borderline titles
- Added `SQLITE_DB_PATH` env var to MCP server (needed for audit tools to read view counts
  and durations from SQLite)
- Updated `claude_desktop_config.json` with `SQLITE_DB_PATH` pointing to `knowledge.db`

---

## v2.2 — 2026-03-03

### Pipeline: Queue Management (`pipeline.py`)
- **`queue remove` subcommand** — delete entries from the queue:
  - `queue remove @channel` — remove all entries for that channel handle
  - `queue remove --id 3` — remove a specific entry by queue row ID
  - `queue remove --status done` — bulk-remove all entries with a given status
- **`queue run --scrape-only` flag** — skips ChromaDB embedding entirely; fetches transcripts
  into SQLite only. Run `python pipeline.py sync` afterward to embed offline with no IP risk.

---

## v2.1 — 2026-03-03

### Phase 3: Queue System, Video Selection & Run Receipts (`pipeline.py`)

#### Channel Queue System
- **New SQLite table `channel_queue`** — persistent queue with per-channel settings
  (limit, sort_by, min/max duration, skip keywords, whitelist CSV) and status tracking
  (pending -> running -> done / paused / failed)
- **`queue add`** — enqueue a channel with full scraping options
- **`queue run`** — process all pending channels in order; auto-stops on rate limit
- **`queue status`** — show all entries with status, progress, and timing
- **`queue reset`** — reset paused/failed back to pending (run after IP change)
- **`RateLimitError`** custom exception + `_is_rate_limit()` signal detection
- **`ChannelStats` dataclass** — tracks attempted, success, no-transcript, skipped,
  chunks, elapsed, and status per channel run

#### Video Selection
- **`--sort-by views`** on `add-channel` and `queue add** — fetches full channel list,
  sorts by view count descending, applies limit. Guarantees top-N most-viewed, not newest-N.
- **`--whitelist <file>`** on `add-channel` — restrict scrape to video IDs in a whitelist file
- **`add-from-csv <file>`** — scrape specific videos from a URL/ID list with no channel needed.
  Fetches metadata per-video via yt-dlp. Supports full URLs, short URLs, raw IDs.
  Bad/deleted/private IDs are skipped gracefully with a warning.
- **`_parse_whitelist_csv()`** — parses whitelist files (# comments, blank lines ignored)

#### Run Receipts
- **`_print_receipt()`** — formatted summary after every `add-channel`, `queue run`, and `sync`:
  per-channel results (scraped, success, no-transcript, chunks, elapsed) plus overall totals
- **`_fmt_elapsed()`** — formats seconds as Xh Xm Xs

#### Other changes
- `embed_new_videos()` now returns `(n_videos, n_chunks)` tuple
- `scrape_channel_to_db()` now returns `(video_ids, ChannelStats)` tuple
- `fetch_transcript()` raises `RateLimitError` instead of returning `None` on rate-limit signals
- `fetch_video_list()` accepts `sort_by`; skips `playlistend` when `sort_by="views"` so the
  full channel list is fetched before local truncation
- `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` for emoji output on Windows

---

## v2.0 — 2026-03-03

### ChromaDB Scan Limit Fixes (`pipeline.py`, `yt_knowledge_mcp.py`)
- **`_get_embedded_video_ids()`** — replaced `limit=50_000` cap with paginated 10K-batch loop;
  fixes sync re-embedding already-indexed videos beyond ~526 videos
- **`cmd_status()`** — same pagination fix for channel extraction from ChromaDB
- **`embed_new_videos()`** — added `"chunk_count": len(chunks)` to `video_metadata` collection
  entries (was missing, causing `yt_list_videos` to always show 0 chunks per video)
- **`_build_bm25_index()`** (MCP) — replaced 50K cap with paginated loop
- **`yt_list_videos`** (MCP) — replaced `limit=5000` chunk cap with paginated loop;
  fixes tool returning ~61 videos instead of 338+

---

## v2.7.1 — 2026-03-07 (approx.)

### UI Build: Hero Screen + Animated Background (`sage_chat/`)
*Reconstructed from code — context was cleared before changelog was written.*

**Animated hero background**
- Built `lib/unicornEmbed.js` — custom utility that injects a Unicorn Studio scene into any DOM element; crops the bottom badge via `cropPx` option; lazy-loads the Unicorn Studio SDK script on first call; suppresses the watermark link via injected `<style>`
- Built `app/components/UnicornBackground.tsx` — React wrapper that mounts the Unicorn Studio animation (`data-us-project="qFZJmsATe1qivAJHWPuL"`) into an `absolute inset-0` layer on the hero screen; uses `useEffect` + `ref` so the embed fires after hydration

**Hero screen (`MessageList.tsx`)**
- Empty-state screen (shown when no messages) replaced plain placeholder with full-viewport hero on `bg-black`
- `UnicornBackground` mounted behind all content at `z-index: 0`
- Dark radial vignette overlay (`rgba(10,10,15,0.88)` → transparent) placed behind text to maintain legibility against the animated background
- Gradient `<h1>` title ("Sage") using `linear-gradient(135deg, #818cf8 → #a5b4fc → #c7d2fe)` via `WebkitBackgroundClip: text`
- Rotating welcome phrase drawn from a pool of 9 (later expanded to 24) lines
- Static subtitle: "Ask anything from the cornucopia of knowledge."
- **Suggestions dropdown** — hover-triggered panel showing 3 randomly picked starter queries from a pool of 20; clicking a suggestion fires it as a query; shuffle button re-picks with a 160ms card-exit/enter CSS transition (`suggestion-card`, `suggestion-card-exit`, `suggestion-card-enter` keyframes in `globals.css`)

**Chat history persistence (`lib/api.ts` + `ChatInterface.tsx`)**
- `loadChats()` / `saveChat()` / `deleteChat()` / `renameChat()` added to `lib/api.ts` — reads/writes `StoredChat[]` to `localStorage` key `sage_chats`
- `ChatInterface` saves messages on every change; sidebar lists all saved chats with restore, rename, delete actions
- Active chat highlighted in sidebar with indigo accent

**Sidebar expansion (`Sidebar.tsx`)**
- Added **Chats tab** as default tab — lists all `StoredChat` entries with mode badge (Quick/Deep), message count, timestamp, inline rename (click pencil → input → Enter), and delete (trash icon, hover-reveal)
- "New Chat" dashed button at top of chats tab
- Channel category filter pills added to Channels tab (reads from `lib/channelCategories.ts`)

---

## v1.x — Phase 1-5

- Unified pipeline (`pipeline.py`) replacing legacy `yt_scraper.py` + `vector_builder.py`
- Two-layer incremental ingestion: SQLite (transcripts) -> ChromaDB (vectors)
- Video filtering: min/max duration, keyword skip list
- MCP server (`yt_knowledge_mcp.py`) with 3 tools:
  `yt_search_knowledge_base`, `yt_get_video_context`, `yt_list_videos`
- Hybrid search: BM25 + semantic search + video-level metadata boost + cross-encoder re-ranking
- ChromaDB chunking: ~150 words with 50-word overlap, title prepended to each chunk
- Incremental sync: `sync`, `rebuild`, `rechunk` pipeline commands

# Meridian Chat — Changelog

---

## 2026-03-12 — Meridian SDK v1.1 (bug fixes + polish)

### Fixed
- **BM25 unpack error** (`_search.py`) — `for i, cid in top_idx` was trying to unpack integers as tuples. Fixed to `for i in top_idx`.
- **Multi-source citation stripping** (`core.py`) — regex only matched single `[SRC_N]` tags. Updated to also strip `[SRC_4, SRC_8]` and `[SRC_1, SRC_2, SRC_3]` style citations. Source extractor simplified to `SRC_(\d+)` to catch all formats.
- **Serious mode prompt** (`_llm.py`) — was still producing framing sentences like "There are varying definitions of...". Rewrote prompt to explicitly ban setup sentences and require starting with the actual answer.

### Added
- **`verbose=True`** on `.search()` — prints typo correction, all query variants with `[1/3]`/`[2/3]`/`[3/3]` progress steps.
- **`show_sources=True`** on `.search()` — returns `{"answer": str, "sources": {"SRC_1": {"title": ..., "url": ...}}}` with only actually-cited chunks included.
- **Default citation stripping** — `[SRC_N]` markers are always stripped from the displayed answer. Clean output by default.
- **`expand_query()`** now returns `(variants, corrected)` tuple so verbose mode can show typo corrections.

---

## 2026-03-12 — Meridian SDK

### Added
- **`meridian_sdk/`** — standalone Python package that exposes Meridian's full query pipeline without the web app or API server.
  - `Meridian` class with a single `.search(query, mode)` entry point
  - **`mode="raw"`** — returns raw `list[dict]` chunks from hybrid search, no LLM
  - **`mode="serious"`** — LLM-synthesized answer, terse and direct (no filler)
  - **`mode="chat"`** — LLM-synthesized answer, natural conversational tone (default)
  - Full pipeline: typo correction → multi-query expansion → hybrid search (semantic + BM25) → LLM synthesis
  - Reads the same `yc_vectors/`, `knowledge.db`, and `bm25_cache.pkl` as the webapp — no copying or syncing
  - Zero imports from `api/` — completely standalone

### Usage
```python
from meridian_sdk import Meridian

m = Meridian()  # reads env vars or defaults to ./yc_vectors, ./knowledge.db

results = m.search("fundraising cold emails", mode="raw")     # list of chunks
answer  = m.search("how to find product market fit", mode="serious")  # terse answer
answer  = m.search("what makes a good co-founder", mode="chat")       # conversational
```

Constructor accepts explicit paths if running from a different directory:
```python
m = Meridian(
    chroma_path="/path/to/yc_vectors",
    sqlite_path="/path/to/knowledge.db",
    gcp_project="your-gcp-project",
)
```

---

## 2026-03-10 — @-mention dropdown z-index fix

### Fixed
- **@-mention dropdown behind hero content** (`ChatInput.tsx`) — dropdown was rendering below the hero title, description, and suggestion chips. Added `z-50` to the dropdown wrapper so it appears above all hero elements.

---

## 2026-03-10 — Mobile + Budget Polish (v4.1 follow-up)

### Fixed
- **Mobile viewport height** (`page.tsx`) — `h-screen` (`100vh`) includes the browser address bar on Android/iOS, making the app taller than the visible area and causing scroll. Changed to `h-[100dvh]` (dynamic viewport height) which tracks the actual visible area.
- **Sidebar backdrop DOM** (`Sidebar.tsx`) — restructured to proper modal pattern: single outer `div` is both the backdrop and click handler, `aside` is a child. `onClick` uses `e.target === e.currentTarget` so only direct taps on the backdrop close the sidebar, not bubbled events from inside the panel. Removes reliance on `stopPropagation` which is unreliable on mobile.
- **Budget cap not synced** (`lib/api.ts`) — `initBudgetFromServer()` now also writes `cap` from the server response to localStorage, overriding any stale local cap. `setBudgetCap()` now fire-and-forgets `PUT /api/budget` with the new cap so all devices stay in sync.
- **New Chat shown on home screen** (`Sidebar.tsx`, `ChatInterface.tsx`) — "New Chat" button in sidebar now only renders when `hasMessages=true` (inside an active chat). Removed redundant "New Chat" button from the top navbar.

### Result
Budget now fully synced: both `spent` and `cap` come from server on init and are written back on every change. Any device opening the app sees the same remaining budget.

---

## 2026-03-10 — Mobile Hero + New Chat Fix + Server-Side Budget (v4.1)

### Fixed
- **Mobile hero padding** (`MessageList.tsx`) — hero container was `py-10` (symmetric). On mobile, the floating chat bar covers the lower ~80px, shifting the visual center up. Changed to `pt-4 pb-28` on mobile, `md:pt-10 md:pb-10` on desktop. Title also shrinks from `text-5xl` to `text-4xl md:text-5xl` so it fits without overflow.
- **"+ New Chat" on mobile** (`Sidebar.tsx`) — tap on the New Chat button was propagating to the full-screen backdrop (`onClick={onClose}`), firing `onClose` before the button's own handler. Added `e.stopPropagation()` to the button's `onClick` — backdrop tap still closes sidebar, but taps inside the panel don't reach the backdrop.
- **Budget synced across devices** — budget spent was stored in `localStorage` per-origin, so phone always started at $300 while PC showed $299.99. Now stored server-side:
  - `api/chat_db.py` — added `settings` table (key-value) to `chats.db`, plus `get_setting()`/`set_setting()` helpers
  - `api/models.py` — added `BudgetResponse` and `BudgetRequest` Pydantic models
  - `api/main.py` — added `GET /api/budget` and `PUT /api/budget` routes
  - `sage_chat/lib/api.ts` — added `_budgetSpent` in-memory cache, `initBudgetFromServer()` async init, `addBudgetSpent()` now fire-and-forgets `PUT /api/budget` on every query
  - `sage_chat/app/components/ChatInterface.tsx` — calls `initBudgetFromServer()` on mount, updates UI state after server values load

### Result
Any device accessing Meridian sees the same remaining budget. Spend $5 on the phone → laptop shows the same $5 spent, not a fresh $300.

---

## 2026-03-10 — Server-Side Chat Persistence

### Added
- **`api/chat_db.py`** — New SQLite CRUD module for `chats.db` (separate from `knowledge.db`). Functions: `init_db`, `upsert_chat`, `list_chats`, `delete_chat`, `rename_chat`.
- **`/api/chats` routes** (`api/main.py`) — `GET` (list all), `POST` (upsert), `DELETE /{id}`, `PATCH /{id}` (rename). Chats stored server-side, sorted by `saved_at DESC`, capped at 50.
- **`CHATS_DB_PATH`** config env var (`api/config.py`, `start.sh`) — defaults to `./chats.db` at project root.
- **`initChatsFromServer()`** (`lib/api.ts`) — async function that fetches all chats from the API and populates the in-memory cache. Called on app mount and on every Sidebar open.

### Changed
- **`lib/api.ts`** — `saveChat`, `deleteChat`, `renameChat` now fire-and-forget API calls in addition to updating the in-memory cache. `localStorage` chat storage removed entirely — server is the single source of truth.
- **`Sidebar.tsx`** — `useEffect` on `isOpen` now calls `initChatsFromServer()` before setting state, so sidebar always shows the latest server-side chats.
- **`ChatInterface.tsx`** — Calls `initChatsFromServer()` on mount to pre-populate cache before sidebar is first opened.

### Result
Chats are now accessible from any origin or device — `192.168.1.45:3000`, `meridian-pi.duckdns.org`, Tailscale, etc. all share the same chat history stored on the Pi.

---

## 2026-03-10 — Raspberry Pi Deployment + nginx + HTTPS

### Added
- **nginx reverse proxy** on Pi — proxies `meridian-pi.duckdns.org` (port 80/443) to Next.js (3000) and API (8000). No port needed in the URL.
- **Let's Encrypt SSL** via DuckDNS certbot DNS challenge (`certbot-dns-duckdns`) — valid HTTPS cert for `meridian-pi.duckdns.org` without requiring public port forwarding.
- **DuckDNS hostname** — `meridian-pi.duckdns.org` → `192.168.1.45`. Clean URL for all LAN devices and phones, no hosts file changes needed.

### Fixed
- **Mixed content / CORS over HTTPS** (`lib/api.ts`) — API URL now uses `window.location.protocol` to detect HTTPS context. Over HTTPS uses same-origin (`https://host/api/...`) so nginx proxies internally; over HTTP uses direct `:8000`. Eliminates mixed content blocks.
- **CORS regex** (`api/main.py`) — Added `https://.*\.duckdns\.org` pattern to allow the duckdns origin without a port.
- **`Access-Control-Allow-Private-Network`** header — Added `PrivateNetworkMiddleware` to handle Chrome's Private Network Access policy for cross-port local requests.

---

## 2026-03-10 — UX + Model Display Fixes

### Added
- **Model name in header** (`ChatInterface.tsx`) — Fetches active Gemini model from `/api/health` on mount (with retry), displays centered in the top navbar in bold gray text. Hidden on mobile (`hidden md:block`), only visible during active chat (not on hero screen).
- **`formatModelName()`** (`lib/api.ts`) — Converts `gemini-2.0-flash` → `Gemini 2.0 Flash`, strips `-preview-...` suffixes.
- **`model` field in `/api/health`** (`api/models.py`, `api/main.py`) — Health endpoint now returns the active `GEMINI_MODEL` string.

### Fixed
- **Typing indicator during word-reveal** (`ChatInterface.tsx`) — `SET_LOADING: false` now dispatched immediately when the assistant message is added (before word-reveal starts), not after all words finish revealing. Typing indicator disappears as soon as the answer begins.
- **Copy button layout** (`MessageBubble.tsx`) — Copy icon is now `absolute -right-7` outside the bubble's right edge, zero layout impact on bubble width or the sources/token row below.
- **Copy button hitbox** (`MessageBubble.tsx`) — Added `pt-2 pb-4 px-1` padding for easier targeting.
- **UnicornBackground not resuming** (`MessageList.tsx`) — Changed from `hidden` (display:none kills WebGL render loop) to `opacity-0/100` with 500ms transition. Canvas stays warm, fades smoothly on home↔chat navigation.
- **Health check on startup** (`ChatInterface.tsx`) — Retries `/api/health` up to 8× every 2 seconds so model name loads even if backend takes a moment to start.

---

## 2026-03-10 — Token Cost Tracking + Query Expansion Fixes

### Fixed
- **Accurate cost display** — Token count now sums both the query expansion call and the synthesis call. Previously only synthesis tokens were tracked, underreporting cost.
- **Query expansion returning 1 variant** (`api/gemini.py`) — 200-token limit was being hit, truncating output mid-response. Bumped to 400 tokens. Prompt restructured to explicit line format (line 1 = corrected query, lines 2-4 = paraphrases) at `temperature=0.4` for reliable instruction-following.
- **Typo correction in query expansion** (`api/gemini.py`) — Gemini now corrects misspellings (e.g. "claude coed" → "claude code") before generating paraphrases. Original query still included as first variant for fallback. `expand_query` now returns `(variants, usage)` tuple.

---

## 2026-03-08 — Centering Fix + Scrollbar Fix

### Fixed
- **Textarea vertical centering** (`ChatInput.tsx`) — Replaced `relative flex-1` wrapper + `absolute inset-0` mirror with a CSS Grid container (`display: grid`). Both the highlight mirror and the textarea now share `gridArea: '1/1'`, so the mirror (in normal document flow) determines the grid cell height and the parent pill's `items-center` correctly centers the whole block. Previously the `absolute` mirror was out of flow, causing content to render in the upper portion of the pill.
- **Removed `resizeTextarea`** (`ChatInput.tsx`) — Manual height juggling via `el.style.height = 'auto'` / `scrollHeight` is no longer needed; the CSS Grid auto-sizes as the mirror wraps. Removed the function and all call sites (`handleSubmit`, `insertMention`, `onInput`, mount effect).
- **`@`-mention scrollbar not appearing on scroll** (`ChatInput.tsx`) — The `.mention-scroll` CSS class hides the scrollbar thumb until `:hover`, but `:hover` doesn't activate during scroll-wheel/trackpad events, so the scrollbar stayed invisible until a React re-render (e.g. arrow key press) refreshed the CSS state. Fixed by tracking `mentionScrolled` state: on first `onScroll` event the class is removed and the native scrollbar appears immediately. Resets to false each time the dropdown opens.

---

## 2026-03-08 — @-mention Highlight + Scrollbar Polish

### Added
- **Blurple `@mention` highlight in textarea** (`ChatInput.tsx`) — Valid channel names typed as `@handle` are now highlighted in indigo (`#818cf8` with 15% indigo background) directly inside the chat input, matching Discord-style mention styling. Uses a transparent textarea overlaid on a mirror `div` that renders colored HTML. Only channels present in the fetched channel list are highlighted; unrecognized `@words` remain unstyled.

### Fixed
- **Mention dropdown scrollbar flash** (`ChatInput.tsx`, `globals.css`) — Scrollbar thumb is hidden until the user hovers over the dropdown, preventing a scrollbar from flickering in on mount. Added `.mention-scroll` CSS class with `transparent` thumb default and `var(--scrollbar-thumb)` on `:hover`.

---

## 2026-03-08 — Mention Fixes + Pill Contrast

### Fixed
- **`@`-mention double `@@`** (`ChatInput.tsx`) — Channel names from the API include their own `@` prefix. `insertMention` and the dropdown display now strip the leading `@` before prepending one, so the result is always `@ChannelName` not `@@ChannelName`.
- **Quick/Deep pill selected text in light mode** (`ChatInput.tsx`, `globals.css`) — Added `--pill-active-text` CSS variable: `#c4b5fd` (light violet) in dark mode, `#3730a3` (deep indigo-900) in light mode. Selected pill label is now clearly distinct from the inactive `--text-dim` in both themes.
- **`@`-mention dropdown infinite scroll** (`ChatInput.tsx`) — Dropdown now stores all filtered results and renders 6 at a time. Scrolling near the bottom of the list reveals 6 more. "scroll for more" hint shown when more results exist. `mentionVisible` resets to 6 on each new `@` query.

---

## 2026-03-08 — Floating Chat Bar (Wave 4)

### Changed
- **Floating chat input** — Chat bar now floats above the bottom edge in ALL app states (home + chat), like Claude.ai and ChatGPT. Never docked flush to the viewport bottom.
- **`ChatInput.tsx`** — New `floating?: boolean` prop. When true: `absolute bottom-6 left-0 right-0` positioning, no `border-t`, deeper drop shadow (`box-shadow: 0 8px 40px rgba(0,0,0,0.45)`).
- **`ChatInterface.tsx`** — MessageList + ChatInput wrapped in `relative flex flex-col flex-1 min-h-0` container so ChatInput overlays MessageList absolutely.
- **`MessageList.tsx`** — Chat scroll container inner div gets `pb-32` so the last message is never hidden behind the floating input.
- `UnicornBackground` home animation now stretches naturally to the full viewport height since the input no longer occupies space at the bottom.

---

## 2026-03-08 — UX Polish Sprint (Wave 1–2)

### New
- **`lib/chatName.ts`** — Pure-TS extractive keyword scorer for smart chat naming. Tokenizes user + assistant messages, drops stopwords, boosts user-message words ×1.5, returns top-4 Title Case keywords (e.g. "Startup Fundraising Pitch Investors"). No deps, no LLM.
- **`@-mention channel autocomplete`** (`ChatInput.tsx`) — Type `@` in the chat input to get a floating dropdown of matching channels (substring search). ArrowUp/Down to navigate, Enter/Tab to select, Escape to dismiss. Inserts exact channel handle (e.g. `@PeterAttiaMD`) so the AI always gets the precise name. Channel list cached in-memory after first fetch.

### Fixed / Improved
- **Smart chat naming** (`ChatInterface.tsx`) — Name now generated once after the first complete exchange (user + non-empty assistant message both present). Cached in `chatNameRef` so it never overwrites. Replaces `slice(0,40)` which produced duplicate names for repeated questions.
- **Sidebar relative timestamps** (`Sidebar.tsx`) — Replaced `toLocaleDateString` with humanized age: "just now", "X min ago", "X hours ago", "Yesterday", "X days ago", "X weeks ago", "X months ago", "half a year ago", actual date for ≥1 year.
- **Sidebar meta row contrast** (`Sidebar.tsx`) — `·` separators bumped `--text-faintest` → `--text-dim`; msg count + timestamp bumped `--text-faint` → `--text-muted`. Video channel/duration similarly bumped.
- **Light mode contrast — Quick/Deep pill** (`ChatInput.tsx`) — Inactive pill buttons changed from `text-white/25 hover:text-white/50` (invisible on cream) to `text-[var(--text-dim)] hover:text-[var(--text-muted)]`.
- **Light mode contrast — pill separator** (`ChatInput.tsx`) — `border-white/[0.06]` → `border-[var(--border-primary)]`.
- **Light mode contrast — theme toggle** (`SettingsPanel.tsx`) — Selected theme label changed from hardcoded `text-[#c4b5fd]` to `text-[var(--text-primary)]` so it reads dark-on-light in light mode.
- **Dark mode text readability** (`globals.css`) — `--text-faint: #505050` → `#686868`, `--text-faintest: #404040` → `#545454` (slightly brighter globally in dark mode).
- **Dark mode text readability** (`SourceCards.tsx`) — Source quote `--text-faint` → `--text-muted`; timestamp `--text-faint` → `--text-dim`.
- **Dark mode text readability** (`MessageBubble.tsx`) — Copy button base `--text-faint` → `--text-dim`, hover `--text-muted` → `--text-secondary`; "response stopped" `--text-faint` → `--text-muted`.

---

## 2026-03-08 — Favicon + Theming + Settings

### New
- **Favicon** (`public/favicon.svg`) — Meridian starburst SVG rendered in browser tab. Dark circle background, indigo radial gradient, 8 spokes + crossbars.
- **CSS variable theming system** (`app/globals.css`) — 20 semantic tokens (`--bg-*`, `--border-*`, `--text-*`, `--input-*`, `--scrollbar-*`) defined on `:root` (dark) with `[data-theme="light"]` overrides using a warm Solarized cream palette (`#FDF6E3` base).
- **`lib/theme.ts`** — `getTheme()`, `setTheme()`, `applyTheme()` helpers. Persists to `localStorage`.
- **`lib/profiles.ts`** — Profile CRUD (add, rename, delete, set active) using `localStorage`. Default profile always protected.
- **SettingsPanel** (`app/components/SettingsPanel.tsx`) — Right-side drawer with gear icon trigger:
  - Theme toggle (Dark ↔ Light solarized)
  - Profile list with add/rename/delete/switch, "coming soon" note for personal KBs
- **Anti-flash script** in `app/layout.tsx` — inline `<script>` reads theme from localStorage before React hydrates to prevent white flash.
- **Favicon metadata** in `app/layout.tsx` — `icons: { icon: '/favicon.svg' }` + `<link>` fallback.

### Fixed
- **Dark mode input border** — `--input-border` bumped from `rgba(255,255,255,0.08)` → `0.14` so the chat bar outline is visible against the black background.

### Modified
- All components migrated from hardcoded hex to CSS variable Tailwind syntax (`bg-[var(--token)]`):
  - `ChatInterface.tsx`, `MessageBubble.tsx`, `TypingIndicator.tsx`, `ChatInput.tsx`
  - `Sidebar.tsx`, `SourceCards.tsx`, `MessageList.tsx`, `app/page.tsx`
- **ChatInterface.tsx** — Settings gear icon button in header; renders `<SettingsPanel>`.
- **Budget display** — always `text-emerald-500` (no hover state, should always be bright).
- **Sidebar rename icon** — changed from pencil-with-box (looks like "create file") to a plain pencil stroke.
- **SettingsPanel add profile** — input dismisses back to "+ Add profile" button on blur when field is empty.

---

## 2026-03-07 — Performance Fixes

### Root Cause Fixed: UnicornBackground WebGL Accumulation
- **`MessageList.tsx`** — Restructured from two conditional return paths to single root element. `UnicornBackground` is always mounted, hidden via CSS `hidden` class when not on home screen. Previously each home↔chat navigation mounted a new WebGL context and never destroyed the old one, causing GPU render loop accumulation.

### Additional Fixes
- **`ChatInterface.tsx`** — `handleNewChat` now aborts in-flight fetch via `abortRef.current.abort()`. Previously navigating home mid-request left orphaned fetch firing 50+ state dispatches.
- **`ChatInterface.tsx`** — `CLEAR_CHAT` reducer now resets `loading: false`. Previously blocked next message submission after clearing.
- **`lib/api.ts`** — `saveChat` uses in-memory `Map` cache; no longer calls `loadChats()` on every save (was O(N×M) as chats accumulated).
- **`ChatInterface.tsx`** — `handleSubmit` useCallback dep array no longer includes `state.messages` (was recreating the callback 33×/sec during word-reveal, cascading to unnecessary re-renders).
- **`ChatInterface.tsx`** — save effect returns cleanup function (fixes StrictMode double-invocation).
- **`MessageList.tsx`, `MessageBubble.tsx`** — Wrapped with `React.memo`.

---

## TODO

### ~~[#3] Light mode contrast audit~~ — DONE (2026-03-08)
- Quick/Deep pill: ✅ Fixed
- SettingsPanel theme toggle: ✅ Fixed
- ChatInput hints/textarea/placeholder: ✅ Already used CSS vars from previous sprint

### [#2] Research: Unicorn Studio JSON intercept via Service Worker
- Prerequisite for task #4. Unicorn Studio fetches an animation JSON that sets the canvas background color.
- Need to confirm whether a Service Worker can intercept + patch this JSON before the engine parses it.

### [#4] UnicornBackground canvas color — match `--bg-base`
- Canvas is hardcoded black; shows as black rectangle behind hero animation in light mode.
- **Blocked by #2**. Once intercept pattern confirmed, patch canvas bg dynamically on theme change.

### ~~[#7] @-mention channel autocomplete~~ — DONE (2026-03-08)

### ~~[#6] Floating chat bar — full app refactor~~ — DONE (2026-03-08)
- ✅ Shipped — see 2026-03-08 entry above.

### ~~[#5] UI polish — dark system text readability~~ — DONE (2026-03-08)

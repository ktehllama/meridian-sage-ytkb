# Meridian Chat — Changelog

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

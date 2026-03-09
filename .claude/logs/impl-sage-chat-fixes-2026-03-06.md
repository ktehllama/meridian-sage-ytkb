# Implementation Log — Sage Chat UI Fixes (Session 2)
Date: 2026-03-06

## Files Created/Modified

### Backend

**`api/models.py`**
- Added `UsageInfo` Pydantic model (`prompt_tokens`, `completion_tokens`)
- Updated `ChatResponse` to include `usage: Optional[UsageInfo] = None`

**`api/gemini.py`**
- Changed `synthesize()` return type to `tuple[str, Optional[dict]]`
- Reads `response.usage_metadata` after `generate_content()` to extract token counts
- Returns `(text, usage_dict)` on success, `(error_message, None)` on failure

**`api/main.py`**
- Added `UsageInfo` to imports from `api.models`
- Unpacked `answer, raw_usage = gemini_module.synthesize(...)`
- Builds `UsageInfo` object and passes it into `ChatResponse`

### Frontend

**`sage_chat/package.json`**
- Added `"rehype-raw": "^7.0.0"` to dependencies (installed successfully)

**`sage_chat/lib/api.ts`**
- Added `UsageInfo` interface
- Updated `ChatResponse` to include `usage?: UsageInfo`
- Updated `chat()` to accept `signal?: AbortSignal`, forwarded to fetch
- Added `calcCost()`, `getBudgetSpent()`, `addBudgetSpent()` helpers
- Pricing: $0.075/1M input tokens, $0.30/1M output tokens (Gemini 2.0 Flash Vertex AI)

**`sage_chat/app/components/MessageBubble.tsx`** — full rewrite
- Single `ReactMarkdown` pass using `rehype-raw` (fixes the multi-`<p>` citation bug)
- Preprocesses: `[SRC_N]` and `[SRC_N, SRC_M, ...]` become `<cite data-ids="N,M">` HTML tags
- Custom `cite` component renders one `<sup><button>` per ID, linking to YouTube
- Accepts `usage` prop; renders token counts + per-request cost below bubble

**`sage_chat/app/components/SourceCards.tsx`** — full rewrite
- Replaced horizontal scroll with collapsible toggle (collapsed by default)
- "N sources" toggle with rotating chevron SVG
- Expanded: number badge, title + timestamp, quote snippet, YouTube icon per row

**`sage_chat/app/components/ChatInput.tsx`** — full rewrite
- Added `onStop?: () => void` prop
- When `disabled=true`: red stop-square button that calls `onStop`
- When `disabled=false`: indigo send-arrow button (original behavior)

**`sage_chat/app/components/MessageList.tsx`**
- Added `usage?: { prompt_tokens: number; completion_tokens: number; cost_usd: number }` to `ChatMessage` interface
- Passes `usage={msg.usage}` to `MessageBubble`

**`sage_chat/app/components/ChatInterface.tsx`**
- Added `abortRef` (AbortController) and `revealIntervalRef` (setInterval) refs
- Added `totalSpent` useState initialized from `getBudgetSpent()`
- `revealWords()` now accepts `intervalRef` and stores interval handle in it
- `handleStop()`: aborts fetch, clears reveal interval, sets loading=false
- `handleSubmit()`: creates AbortController per request, passes signal to `chat()`, computes cost, tracks budget, attaches usage to `ADD_ASSISTANT_MSG`
- Catch block silently handles `AbortError` (no error UI shown on stop)
- `handleRestoreChat()`: SET_MODE → RESTORE_MESSAGES → CLOSE_SIDEBAR
- Header shows `$X.XX left` budget indicator
- Passes `onStop` to `ChatInput`, `onRestoreChat` to `Sidebar`
- `ADD_ASSISTANT_MSG` action type updated to carry optional `usage`

**`sage_chat/app/components/Sidebar.tsx`** — full rewrite
- Added `SavedChat` interface and `onRestoreChat?` prop
- Tab order: `['chats', 'channels', 'videos']`
- Chats tab reads localStorage on open, sorts newest first, renders preview cards
- Clicking a chat card calls `onRestoreChat?.(messages, mode)`
- Channels and videos tabs unchanged in behavior

## Tests Written
None — no test infrastructure exists in this project.

## Deviations from Spec
None. All fixes implemented as specified.

## What QA Should Focus On
1. Run `npm install` (rehype-raw was installed; verify it's in node_modules)
2. **Citation rendering**: Test `[SRC_3]`, `[SRC_3, SRC_4]`, `[SRC_3, SRC_4, SRC_6]` — no extra newlines, superscripts appear inline with text
3. **Multi-citation**: Multiple IDs in one bracket render as adjacent superscripts
4. **Source cards**: Collapsed by default; expand on click; each row links to correct YouTube URL
5. **Stop button**: Red while loading; clicking it aborts in-flight fetch + word reveal; no error shown
6. **Budget display**: Counter decrements after each query; persists across page refresh
7. **Usage line**: Token counts + cost appear below each assistant bubble when backend returns usage_metadata
8. **Chats tab**: After conversations exist, sidebar Chats tab shows them; clicking one restores correctly
9. **Abort then new query**: After stopping, submitting a new query works normally

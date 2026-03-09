# impl-sage-chat-fixes2-2026-03-06

## Files Modified

### `sage_chat/lib/api.ts`
- Added `StoredChat` interface (id, name, mode, messages, savedAt)
- Added `CHATS_KEY = 'sage_chats'` constant
- Added `loadChats()`, `saveChat()`, `deleteChat()`, `renameChat()`, `newChatId()` exports
- All existing exports (`getBudgetSpent`, `addBudgetSpent`, `calcCost`, etc.) preserved

### `sage_chat/app/components/ChatInterface.tsx`
- Added imports: `loadChats`, `saveChat`, `deleteChat`, `renameChat`, `newChatId`, `StoredChat`
- Added `currentChatIdRef = useRef<string | null>(null)` (not state — no re-render cost)
- Replaced old mount useEffect (reads from `sage_chat_ephemeral`/`sage_chat_conversation`) with new one reading from `loadChats()`
- Replaced old save useEffect with new one that uses `currentChatIdRef` and calls `saveChat()`
- `handleModeChange` — removed stale `localStorage.removeItem` call
- `handleNewChat` — clears ref and dispatches `CLEAR_CHAT`
- `handleRestoreChat` — now accepts `StoredChat` (was `messages + mode` pair)
- Added `handleDeleteChat` — calls `deleteChat()`, clears chat if active
- Added `handleRenameChat` — thin wrapper around `renameChat()`
- Updated `<Sidebar>` JSX to pass `onDeleteChat`, `onRenameChat`, `onNewChat`, `activeChatId`
- FIX 3: Budget span changed from `text-[#404040] text-[10px]` to `text-xs text-emerald-600/80` with hover state and better title tooltip

### `sage_chat/app/components/Sidebar.tsx`
- Removed `SavedChat` local interface (replaced by `StoredChat` from api)
- Removed `ChatMessage` import (no longer needed)
- Added `StoredChat`, `loadChats` to api imports
- Updated `SidebarProps`: added `onDeleteChat`, `onRenameChat`, `onNewChat`, `activeChatId`
- Updated `savedChats` state type from `SavedChat[]` to `StoredChat[]`
- Added `editingId` and `editingName` state for inline rename
- Replaced old chats-tab load logic (loop over 2 localStorage keys) with `loadChats()`
- Replaced entire chats tab UI: now has "New Chat" button at top, per-chat rename/delete action buttons on hover, active chat highlight, name display (not preview), mode badge "Quick"/"Deep"

### `sage_chat/app/components/MessageBubble.tsx`
- FIX 4: Added citation pre-pass in `processedContent` useMemo — regex `(\[SRC_[\d,\s_]+\])([\.\!\?])` → `$2$1` moves citations after punctuation
- FIX 2: Removed standalone usage `<div>` block
- FIX 2: Changed `{sources.length > 0 && <SourceCards sources={sources} />}` to `{(sources.length > 0 || usage) && <SourceCards sources={sources} usage={usage} />}`

### `sage_chat/app/components/SourceCards.tsx`
- FIX 2: Added `usage` prop to `SourceCardsProps`
- FIX 2: Guard changed from `sources.length === 0` to `sources.length === 0 && !usage` (allows usage-only render)
- FIX 2: Replaced single `<button>` toggle row with `<div className="flex items-center justify-between">` containing sources toggle (left) and usage display (right)
- Usage display: up/down arrow icon, `1.2K / 0.3K · $0.0021` format in monospace

## Tests Written
None — this is a pure frontend UI component change with no logic that warrants unit tests beyond manual verification. All changes are deterministic transformations.

## Deviations from Spec
None. All changes match spec exactly.

## What QA Should Focus On

1. **Chat persistence across page reloads** — verify the most recent chat restores on mount
2. **New chat flow** — clicking "New Chat" in sidebar or header should clear the UI and set `currentChatIdRef` to null, so the next message creates a fresh entry in `sage_chats`
3. **Rename inline editing** — Enter commits, Escape cancels, blur commits. Verify optimistic UI update (setSavedChats) matches what's persisted to localStorage
4. **Delete active chat** — should clear the main chat view; delete non-active chat should leave current chat untouched
5. **50-chat cap** — `saveChat` slices to 50; verify old entries are dropped
6. **Citation order** — responses ending with `[SRC_3].` should render as `.<sup>3</sup>` not `<sup>3</sup>.`
7. **Usage display** — should appear on same row as sources toggle; verify when there are 0 sources (usage only) the row still renders correctly without the sources button
8. **Budget display** — should be visible green text `$299.98 left` format
9. **Mode badge** — "Quick" for ephemeral, "Deep" for conversation (was "Deep Dive" before)
10. **activeChatId highlight** — the currently loaded chat should show indigo-tinted background in the sidebar list

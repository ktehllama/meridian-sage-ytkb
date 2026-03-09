# PRD: Meridian Chat — Performance Fix (Cumulative Slowdown)

## Problem

The chat UI gets progressively slower with each chat session. Reproducing:
1. Fresh page load
2. Start a chat (send message, receive response)
3. Click Meridian logo to go home
4. Repeat — each cycle is noticeably more sluggish

Root cause analysis identified 4 compounding issues.

## Root Causes (confirmed by code audit)

### 1. `saveChat` reads + rewrites ALL chats on every save (api.ts:186-192)
```ts
const chats = loadChats().filter(c => c.id !== chat.id); // JSON.parse ALL
chats.unshift(chat);
localStorage.setItem(CHATS_KEY, JSON.stringify(chats.slice(0, 50))); // stringify ALL
```
Every `saveChat` call deserializes the entire chat history (up to 50 chats × all messages),
builds a new array, then re-serializes everything. As chats accumulate this grows O(N×M).
Fix: maintain an in-memory `Map<id, StoredChat>` cache so reads never hit localStorage during
a save; only write to localStorage.

### 2. `handleSubmit` lists `state.messages` as a useCallback dependency (ChatInterface.tsx:243)
```tsx
const handleSubmit = useCallback(async (text) => { ... }, [state.loading, state.mode, state.messages]);
```
`state.messages` is a new array reference on every `APPEND_WORD` dispatch (30ms interval).
This recreates `handleSubmit` 33×/sec → `handleVideoSelect` (depends on it) also recreates →
both passed as props to `MessageList` and `ChatInput`, forcing unnecessary re-renders.
Fix: remove `state.messages` from the dep array. The messages are only needed for `history`
in conversation mode — read from a ref instead, or use `useReducer` dispatch pattern that
doesn't need the stale closure.

### 3. `APPEND_WORD` triggers full re-render of MessageBubble tree (ChatInterface.tsx:61-68)
Every word append re-renders the entire message list. Each `MessageBubble` runs
`useMemo` for citation preprocessing on every parent re-render.
Fix: wrap `MessageList` and `MessageBubble` with `React.memo`. The bubbles for completed
messages have stable props and should not re-render during word-reveal of the latest message.

### 4. `saveEffect` missing cleanup return (ChatInterface.tsx:159-169)
In React StrictMode (default in Next.js dev), effects without cleanup are double-invoked.
The save effect sets a timer but never returns a cleanup function, so on unmount the timer
fires against a stale closure.
Fix: return `() => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); }` from
the effect.

## Out of Scope
- UI changes
- Backend changes
- Any new features

## Acceptance Criteria
1. Opening 10 consecutive chats shows no measurable degradation in input responsiveness
2. `saveChat` in api.ts never calls `loadChats()` during a save (only on explicit load)
3. `handleSubmit` useCallback dep array does NOT include `state.messages`
4. `MessageList` and `MessageBubble` are wrapped with `React.memo`
5. `saveEffect` returns a cleanup function
6. `npm run build` passes with zero errors

## Files to Modify
- `sage_chat/lib/api.ts` — fix `saveChat`, add in-memory cache
- `sage_chat/app/components/ChatInterface.tsx` — fix handleSubmit deps, fix saveEffect cleanup
- `sage_chat/app/components/MessageList.tsx` — add React.memo
- `sage_chat/app/components/MessageBubble.tsx` — add React.memo

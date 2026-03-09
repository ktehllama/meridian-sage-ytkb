# impl: smart-chat-naming — 2026-03-08

## Files created / modified

- `sage_chat/lib/chatName.ts` (created)
  Pure-TS extractive keyword scorer. Tokenizes user + assistant text, applies 1.5x boost to user words, returns top-4 capitalized keywords joined as the chat name. Uses `Array.from(freq.entries())` instead of spread to satisfy the project's pre-ES2015 TypeScript target.

- `sage_chat/app/components/ChatInterface.tsx` (modified)
  - Added `import { generateChatName } from '../../lib/chatName'` after the MessageList import.
  - Added `chatNameRef = useRef<string | null>(null)` after `saveTimerRef`.
  - Added `chatNameRef.current = null` reset inside `handleNewChat` (alongside the existing `currentChatIdRef.current = null`).
  - Replaced the save-effect name derivation: computes the name once (when both a user and non-empty assistant message exist) and caches it in `chatNameRef`; subsequent saves reuse the cached value.

## Tests written

None — pure utility function, no test runner configured in the project. The scorer logic is straightforward (tokenize → frequency map → top-N sort) and was validated manually via the TypeScript type-check pass.

## Deviations from spec

One fix beyond the spec: changed `[...freq.entries()]` to `Array.from(freq.entries())`. The project's `tsconfig.json` targets an ES level where spreading a `MapIterator` directly fails the compiler. `Array.from` is the standard workaround and is semantically identical.

## What QA should focus on

1. Start a fresh chat, send a message, wait for the assistant reply — confirm the sidebar shows a keyword-based name (4 capitalized words) rather than a raw 40-char slice of the first message.
2. Start a new chat immediately after (before the assistant replies) — confirm the name falls back to the 40-char slice of the user message, not a stale name from a previous chat.
3. Restore a saved chat from the sidebar, then start another new chat — confirm `chatNameRef` resets and the new chat gets its own fresh name.
4. Send a message with only stopwords or very short tokens (e.g. "Hi") — confirm fallback to `userMsg.slice(0, 40)` rather than an empty string or crash.

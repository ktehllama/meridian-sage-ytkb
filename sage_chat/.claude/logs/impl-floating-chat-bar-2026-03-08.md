# Impl Log: Floating Chat Bar — 2026-03-08

## Files Modified

### `app/components/ChatInput.tsx`
- Line 13: Added `floating?: boolean` to `ChatInputProps` interface
- Line 18: Added `floating = false` to destructure in function signature
- Lines 136-139: Replaced static outer wrapper div with conditional — `absolute bottom-6 left-0 right-0 px-4` when floating, original docked styles otherwise
- Line 137: Changed inner `max-w-3xl` div from no `relative` to `relative max-w-3xl mx-auto` (needed for @-mention dropdown positioning)
- Lines 166-169: Added `boxShadow` spread conditional to glassmorphism container style when `floating` is true

### `app/components/ChatInterface.tsx`
- Lines 401-422: Replaced bare `<MessageList>` + `<ChatInput>` with a `relative flex flex-col flex-1 min-h-0` wrapper div containing both; `<ChatInput>` now receives `floating` prop (boolean shorthand); removed the old docked `<ChatInput>` without `floating`

### `app/components/MessageList.tsx`
- Line 241: Added `pb-32` to the chat scroll inner div (`max-w-3xl mx-auto w-full pb-32`) so last message is not hidden behind the floating input

## Tests Written
None — UI layout change with no logic. Visual verification via `npm run build`.

## Build Result
`npm run build` passed with zero TypeScript errors and zero lint errors.

## Deviations from Spec
- Added `flex flex-col` to the wrapper div in `ChatInterface.tsx` in addition to `relative flex-1 min-h-0`. This was required because `MessageList`'s own outer div uses `flex-1` to fill available height — without a flex container parent, `flex-1` has no effect and the list collapses. The spec did not mention this but it is necessary for correct layout.

## What QA Should Focus On
1. Home screen: floating input appears centered ~24px above bottom edge, with glassmorphism shadow visible against the UnicornBackground animation
2. Chat view: messages scroll freely; last message is fully visible above the floating input (pb-32 clearance)
3. @-mention dropdown: opens upward above the input pill correctly (relative positioning preserved)
4. Mode switch (Quick/Deep): still functional with no visual regression
5. Stop button during streaming: still reachable and clickable through the floating layer
6. Resize behavior: textarea expansion still capped at 15vh; floating container moves up as textarea grows (absolute bottom-6 anchors to bottom edge of relative parent)
7. Light theme: shadow values use rgba black — confirm they remain visible against the warm cream background

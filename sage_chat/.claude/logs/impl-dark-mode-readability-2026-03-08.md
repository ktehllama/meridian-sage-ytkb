# impl-dark-mode-readability-2026-03-08

## Files Modified

- `app/globals.css` — Bumped `:root` dark theme tokens `--text-faint` from `#505050` to `#686868` and `--text-faintest` from `#404040` to `#545454`.
- `app/components/SourceCards.tsx` — Changed source timestamp span from `--text-faint` to `--text-dim`; changed source quote paragraph from `--text-faint` to `--text-muted`.
- `app/components/MessageBubble.tsx` — Changed copy button base color from `--text-faint` to `--text-dim`, hover from `--text-muted` to `--text-secondary`; changed "response stopped" indicator from `--text-faint` to `--text-muted`.

## Tests Written

No unit tests applicable — pure CSS token and Tailwind class changes with no logic.

## Deviations from ADR

None.

## Build Verification

TypeScript type check passed clean. The `npm run build` exit-1 is a pre-existing standalone output copy race condition in Next.js 14 (`ENOENT` on `.next/standalone` directory) unrelated to these changes. The first stale-cache run also had a pre-existing `chatName.ts` MapIterator error that was already fixed in the source file but cached; the clean rebuild confirmed zero TS errors.

## QA Focus Areas

- Dark mode: verify timestamp and quote text in expanded SourceCards is legible against `--bg-surface` / `--bg-hover` card backgrounds.
- Dark mode: verify copy button is visible at rest (`--text-dim`) and clearly readable on hover (`--text-secondary`).
- Dark mode: verify "response stopped" text is clearly visible at `--text-muted`.
- Light mode: these tokens are untouched in `[data-theme="light"]`, so no light mode regression expected — confirm source cards and copy button appearance unchanged in light theme.

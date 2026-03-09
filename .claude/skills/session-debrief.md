---
name: session-debrief
description: >
  At the end of a work session, reads git log, scratchpad, and session logs,
  then writes a structured summary to .claude/logs/. Captures what was built,
  decisions made and why, what's left, and what the next session should start
  with. Builds continuity across sessions. Triggers on: "debrief", "end of
  session", "wrap up", "summarize what we did", "write the session log",
  "what did we accomplish", "close out this session", "save session state".
user-invocable: true
---

# Session Debrief

You capture what happened so the next session doesn't start cold.
You write for your future self — the version that won't remember
what decisions were made or why.

## Process

1. **Gather session data**
   ```bash
   git log --oneline --since="8 hours ago"    # what was committed
   git diff HEAD~$(git log --oneline --since="8 hours ago" | wc -l) --stat  # scope of changes
   ```
   Read:
   - `.claude/memory/scratchpad.md` — active session state
   - `.claude/plans/active-plan.md` — what was planned
   - Any QA reports or review reports from `.claude/logs/`

2. **Write the debrief** and save to `.claude/logs/debrief-[YYYY-MM-DD].md`

```markdown
# Session Debrief — [date]
Duration: [rough estimate if trackable]

## What Was Accomplished
[Bullet list of concrete things that got done — be specific]
- Implemented user authentication (JWT, refresh token rotation)
- Fixed the null pointer bug in cart checkout (was missing null check on line 78)
- Updated 3 API endpoints to match new response schema

## Commits
[List git commits from this session with one-line description of what they actually did]

## Decisions Made
[Every significant choice made during this session, with reasoning]

| Decision | Why | Alternatives rejected |
|----------|-----|-----------------------|
| Used Redis for session storage | Already in stack, low latency reads | DB storage would require extra queries per request |
| Kept old endpoint for backwards compat | 3 mobile app versions use it | Breaking it would require coordinated mobile release |

## What Was Deferred
[Things that were planned but not done, with reason]
- [ ] Rate limiting on auth endpoint — deferred: needs Redis config, do next session
- [ ] Mobile-responsive layout — out of scope for this sprint, tracked in issue #45

## Problems Encountered
[Anything that took longer than expected, any surprises, any blockers]
- Stripe webhook verification was failing — turned out the shared secret had extra whitespace
- Tests were flaky due to async setup — fixed with explicit await in beforeEach

## What the Next Session Should Start With
[The most important context for picking up where this left off]

1. **First thing to do**: [specific action]
2. **Read first**: [file or doc that will restore context fastest]
3. **Known blocker**: [anything that needs resolution before progress can continue]
4. **Open question**: [decision that still needs to be made]

## State of the Codebase
- Tests: [passing/failing — and which if failing]
- Build: [clean/errors]
- Active branch: [branch name]
- Uncommitted changes: [yes/no — what if yes]

## Notes for the Human
[Anything that needs human attention or decision]
- [ ] [Action needed from human]
```

3. **Update the scratchpad**
   Clear completed items, carry forward what's still in progress:
   ```markdown
   ## Scratchpad — Updated [date]
   [Remove done items, keep open items with current status]
   ```

## Hard rules
- Always write the "next session should start with" section — it's the most valuable part
- If tests are failing at end of session: note it prominently at the top
- Don't summarize vaguely — "fixed bugs" is useless. "Fixed null pointer in cart checkout when item count is 0" is useful
- If a decision was made under uncertainty: note the assumption — future sessions need to know what might be wrong

---
description: "Generate a standup/status update from git log and active plan"
argument-hint: "[--yesterday | --week | --sprint]"
---

# /standup — Status Report

Generate a concise status update from what actually happened (git log) vs what was planned.

## Steps

1. **Gather data**:
   - `git log --oneline --since="yesterday"` (or `--since="1 week ago"` for weekly)
   - Active plan: `.claude/plans/active-plan.md`
   - Scratchpad: `.claude/memory/scratchpad.md`
   - Recent session logs: `.claude/logs/`

2. **Generate standup** in this format:
```markdown
## Yesterday
- [what was actually completed, from git log]

## Today
- [what's next, from active plan]

## Blockers
- [anything in open questions or unresolved items]

## Metrics
- Commits: X
- Files changed: Y
- Tests: [pass/fail from most recent QA report]
```

3. **Offer**: "Want me to format this as a Slack message / email / Jira comment?"

## Usage
```
/standup            # yesterday's work
/standup --week     # last 7 days
/standup --sprint   # since last tag/release
```

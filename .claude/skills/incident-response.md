---
name: incident-response
description: >
  Full incident response workflow: given an error, production bug, or crash, 
  traces root cause, proposes fix, and writes a regression test. Triggers on: 
  "there's a bug", "this is crashing", "production is down", "something broke", 
  "error in production", paste of an error/stack trace.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash(rg *)
  - Bash(git log *)
  - Bash(git blame *)
  - Bash(git diff *)
  - Bash(cat *)
---

# Incident Response Skill

## Triage

First, assess severity:
- 🔴 **P0** — Production down, data loss, security breach → say this immediately, then investigate
- 🟡 **P1** — Major feature broken, significant user impact → investigate immediately  
- 🟢 **P2** — Edge case, minor degradation → standard investigation

## Investigation protocol

**Collect first, conclude later:**
1. Get the full error/stack trace (ask if not provided)
2. `rg "[error string]"` — find where this originates in the codebase
3. `git log --oneline -20` — what changed recently?
4. `git blame [file]:[line]` — who touched this last and when?
5. Read the full function/module where the error occurs
6. Find the test file for the affected module — are there tests? Are they passing?

**Stack trace reading:**
- Read from the bottom — the bottom frame is closest to root cause
- Find the first frame in YOUR code (not library code) — that's your entry point
- Trace the call chain from there

## Dispatch debugger agent

For non-obvious bugs, dispatch the debugger agent with:
- Full error/stack trace
- Recent git log
- Relevant file contents
- Your initial hypotheses

## Output structure

```markdown
# Incident Report — [brief description]
**Time**: [now]
**Severity**: P0/P1/P2
**Status**: Investigating | Root Cause Found | Fixed | Closed

## Error
```[error message verbatim]```

## Root Cause
[Precise explanation of what's wrong and why]

## Fix
[Specific code change needed]

## Regression Test
```[test code that would have caught this]```

## Timeline
- [time]: Error first observed
- [commit]: Last working state
- [commit]: Change that introduced the bug

## Prevention
[What process or check would prevent this class of bug in future]
```

## After fix
1. Write the regression test FIRST (before fixing)
2. Confirm the test fails (reproduces the bug)
3. Implement the fix
4. Confirm the test passes
5. Dispatch qa-engineer to run the full suite

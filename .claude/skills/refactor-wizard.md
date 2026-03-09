---
name: refactor-wizard
description: >
  Analyzes a file, function, or module and produces a complete refactor plan
  before touching any code. Triggers on: "refactor this", "clean up this code",
  "this function is too long", "improve this", "this is getting messy",
  "extract this", "this violates SOLID", "make this more maintainable".
  Always plans before implementing — never jumps straight to changes.
user-invocable: true
---

# Refactor Wizard

You refactor code thoughtfully. You diagnose before you operate. You never
rewrite code without first explaining exactly what's wrong and what you'll do.

## Process

### Phase 1: Diagnosis (always first)
1. Read the target file/function completely — understand what it does
2. Read 2-3 related files to understand usage patterns and context
3. Check CLAUDE.md for code standards this project follows
4. Run `rg` to find all callers of the function/module being refactored
5. Identify every problem — categorize each:

```
## Diagnosis: [file/function name]

### Issues Found
**Complexity**
- [specific issue: e.g., "function does 4 unrelated things — line X does A, line Y does B"]

**Coupling**
- [specific issue: e.g., "directly imports UserService inside a utility function — breaks separation"]

**Readability**
- [specific issue: e.g., "variable `d` at line 34 — no indication what it holds"]

**Testability**
- [specific issue: e.g., "side effect on line 67 makes unit testing impossible without mocking the world"]

**Pattern violations**
- [specific issue vs. how the codebase does it elsewhere]
```

### Phase 2: Plan (present before implementing)
6. Write the refactor plan:

```
## Refactor Plan

### Approach
[One paragraph: what strategy — extract, split, rename, invert dependency, etc.]

### Changes
1. Extract [X] into [new function name] — because [reason]
2. Rename [Y] to [Z] — because [Z more accurately describes what it does]
3. Replace [pattern] with [pattern] — already used in [other file] for consistency

### Files Affected
- [file]: [what changes]
- [file]: [what changes — including callers that need updates]

### What stays the same
- [external interface / return type / behavior that will NOT change]

### Risk
[Low/Medium/High]: [why, and what to verify after]
```

7. **STOP HERE.** Present diagnosis + plan to human. Ask:
   "Does this look right? Should I proceed with the refactor?"

### Phase 3: Execute (only after confirmation)
8. Implement changes exactly as described in the plan
9. Update all callers found in Phase 1
10. Run tests: `[dev command from CLAUDE.md]`
11. If tests fail: fix before declaring done

## Hard rules
- Never refactor without diagnosis first — even if the fix seems obvious
- Never change external behavior — refactoring is internal structure only
- If the change would affect the public API: STOP and raise to human
- If tests don't exist for the code being refactored: note it, write them first

## Output
Summary of what changed and what the human should verify in the diff.

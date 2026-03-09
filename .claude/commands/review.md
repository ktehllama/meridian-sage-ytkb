---
description: "Trigger code review on current staged changes or specified files"
argument-hint: "[file or directory to review, or empty for staged changes]"
---

# /review — Code Review

Dispatch the code-reviewer agent on the current changes.

## Steps

1. **Determine scope**:
   - If argument given: review those files
   - If no argument: review `git diff --staged` or `git diff HEAD` if nothing staged

2. **Dispatch code-reviewer agent** with:
   - The diff or file list
   - Relevant spec (if found in `.claude/plans/`)
   - CLAUDE.md code standards section

3. **Output**: Full review report in terminal. If blockers found, pause and present to human.

## Usage
```
/review                       # review staged changes
/review src/auth/             # review specific directory  
/review src/auth/login.ts     # review specific file
```

---
description: "Full pipeline from description to shipped code: PRD → plan → team → implement → validate"
argument-hint: "<feature description or path to existing PRD>"
---

# /ship — Full Pipeline

Execute the complete development pipeline for the provided feature or PRD.

## Steps

1. **Check if PRD exists**: Look for `.claude/plans/prd-*.md` matching the argument
   - If found: use it
   - If not: run the prd-wizard skill to create one first, then continue

2. **Spawn team**: Run the spawn-team skill with the PRD as context
   - It will analyze the work, propose team composition, and get confirmation

3. **Execute pipeline**: Dispatch the orchestrator with:
   - The PRD location
   - The team plan location  
   - Instruction to track progress in `.claude/memory/scratchpad.md`
   - Instruction to write session log on completion

4. **Gate before commit**: Confirm qa-engineer PASS verdict exists before any commit

5. **Report to human**: When done, show:
   - What was built (files created/modified)
   - QA status
   - Code review findings (if blocker-level issues, pause for human)
   - What to review in the git diff

## Usage
```
/ship                          # use active PRD
/ship add user authentication  # describe feature (creates PRD first)
/ship .claude/plans/prd-auth.md  # point to existing PRD
```

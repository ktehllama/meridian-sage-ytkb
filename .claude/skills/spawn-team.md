---
name: spawn-team
description: >
  Analyzes a task, PRD, or project description and automatically assembles the 
  right agent team with correct roles, sequencing, and a coordination plan. 
  Creates the team execution plan and dispatches the orchestrator. Triggers on: 
  "spawn a team", "build this with agents", "start the team", "run the pipeline", 
  "assemble agents for this", or when a PRD file exists and user wants to execute it.
user-invocable: true
---

# Spawn Team Skill

You analyze the work at hand, decide which agents are needed, sequence them correctly, and produce a coordination plan that the orchestrator can execute.

## Step 1: Analyze the task

Read (in this order):
1. The active PRD (`.claude/plans/prd-*.md`) or the task description
2. CLAUDE.md for stack and constraints
3. `.claude/memory/decisions.md` for existing architectural decisions
4. The codebase structure (quick `find` to understand layout)

## Step 2: Decide team composition

Match task complexity to team size:

**Minimal team** (simple bug fix, small feature):
- implementer → qa-engineer

**Standard team** (feature with design choices):
- pm-spec → architect → implementer → qa-engineer + code-reviewer (parallel)

**Full team** (new system, complex feature, multi-file changes):
- pm-spec → architect → [implementer × N parallel] → qa-engineer → code-reviewer → doc-writer

**Investigation team** (unknown bug, production incident):
- debugger → [implementer for fix] → qa-engineer

## Step 3: Write the team plan

Create `.claude/plans/team-plan-[task]-[date].md`:

```markdown
# Team Plan: [Task Name]
**Date**: [date]
**PRD**: [link if exists]
**Complexity**: Simple | Standard | Full | Investigation

## Team Roster
| Agent | Role | Model | Inputs | Outputs |
|-------|------|-------|--------|---------|
| pm-spec | Clarify requirements | sonnet | task description | spec file |
| architect | Design approach | sonnet | spec | ADR |
| implementer | Write code | sonnet | ADR | code + tests |
| qa-engineer | Validate | sonnet | code | QA report |
| code-reviewer | Async review | haiku | git diff | review report |

## Execution Sequence
```
Phase 1 (serial): pm-spec → architect
Phase 2 (parallel): implementer-auth, implementer-api [if independent modules]
Phase 3 (serial): qa-engineer
Phase 4 (parallel): code-reviewer, doc-writer [async, non-blocking]
```

## Parallelization Plan
Safe to parallelize:
- [module A] and [module B] touch different files

Must serialize:
- architect must complete before implementer starts (dependency)
- qa-engineer needs all implementers done (dependency)

## Context Each Agent Needs
- pm-spec: [what to read]
- architect: [what to read]  
- implementer: [what to read + specific file scope]
- qa-engineer: [what to run + spec location]

## Success Criteria
Team is done when:
- [ ] QA report shows PASS
- [ ] Code review has no blockers
- [ ] Docs updated
- [ ] Scratchpad tasks all checked

## Estimated Token Cost
[rough estimate based on team size × task complexity]
```

## Step 4: Dispatch

After writing the plan:
1. Show the human the team roster and sequencing
2. Confirm: "This is the team I'll assemble. Does this look right?"
3. On confirmation, dispatch the orchestrator with the team plan as context

Tell the orchestrator:
"Read `.claude/plans/team-plan-[task]-[date].md` and execute the team plan. Dispatch agents in the sequence specified. Track progress in `.claude/memory/scratchpad.md`."

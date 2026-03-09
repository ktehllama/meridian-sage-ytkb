---
description: "Bootstrap a new project with CLAUDE.md, memory structure, and initial ADR"
argument-hint: "<project name and brief description>"
---

# /new-project — Project Bootstrap

Set up a new project's Claude Code infrastructure from scratch.

## Steps

1. **Gather project info** (ask if not provided in argument):
   - Project name
   - Tech stack (language, framework, database)
   - Dev commands (how to run, test, build, lint)
   - Existing architecture or starting fresh?
   - Team size / solo?

2. **Create CLAUDE.md** in project root:
```markdown
# [Project Name]

## Stack
[tech, versions]

## Architecture
[how codebase is organized]

## Dev Commands
- run: [command]
- test: [command]
- build: [command]
- lint: [command]

## Code Standards
[language conventions, patterns]

## Critical Gotchas
[update this as you discover things]

## Sub-Agent Routing
Parallel: 3+ independent tasks, different files, no shared state
Sequential: dependencies, shared files, unclear scope
Background: research, analysis, no file modifications

## Memory
- Decisions: .claude/memory/decisions.md
- Active plan: .claude/plans/active-plan.md
- Scratchpad: .claude/memory/scratchpad.md
```

3. **Initialize memory files**:
   - `.claude/memory/decisions.md` — initial architecture decision
   - `.claude/memory/scratchpad.md` — empty, ready for use

4. **Write initial ADR** to `.claude/memory/decisions.md`:
   - Initial tech stack choices
   - Why this stack was chosen
   - Key architectural patterns

5. **Confirm** to human: "Project bootstrapped. Run `/ship [feature]` to start building."

## Usage
```
/new-project my-api A REST API for invoice management
/new-project    # interactive mode — asks questions
```

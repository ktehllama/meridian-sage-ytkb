---
name: perf-audit
description: >
  Performance audit of a module, function, or endpoint. Identifies bottlenecks, 
  N+1 queries, blocking operations, and optimization opportunities. Triggers on: 
  "this is slow", "audit performance", "find bottlenecks", "why is X slow", 
  "optimize this", "profile this".
user-invocable: true
allowed-tools:
  - Read
  - Bash(rg *)
  - Bash(cat *)
  - Bash(find * -not -path "*/node_modules/*" -not -path "*/.git/*")
---

# Perf Audit Skill

## What to look for

**Database (highest impact)**
- N+1 queries: `for` loop with DB call inside → should be single query with JOIN or batch fetch
- Missing indexes: query on column without index → check schema
- SELECT * → should select only needed fields
- No pagination on queries that could return large sets
- Repeated identical queries within a request → should be cached

**Network**
- Sequential await calls that could be `Promise.all`
- No request timeouts → can hang forever
- Downloading full resource when only partial needed
- Missing HTTP caching headers on stable responses

**Memory**
- Loading entire dataset into memory when streaming is possible
- Accumulating data in a loop without bounds
- Creating objects in hot loops that could be reused

**Compute**
- CPU-intensive work on main thread → should be worker/queue
- `JSON.parse`/`JSON.stringify` in hot paths
- Regex compiled inside loops → should be constant
- Missing memoization on pure expensive functions

## Audit output

```markdown
# Performance Audit — [module/file]
**Date**: [date]

## Critical Issues (fix immediately)
- **[file:line]** N+1 query in user list endpoint
  Current: SELECT per user in loop (N queries for N users)
  Fix: Single SELECT with JOIN or batch load
  Est. impact: 100ms → 5ms per request

## Major Issues (fix soon)
- [issue + specific fix + impact estimate]

## Minor Issues (cleanup)
- [issue]

## Quick Wins (< 30 min each)
- [specific change + impact]

## Recommendations
[Architectural changes for sustained performance]
```

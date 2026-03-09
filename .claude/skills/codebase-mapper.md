---
name: codebase-mapper
description: >
  Reads the entire project and produces a comprehensive architecture document:
  what lives where, how data flows, what calls what, entry points, and the
  public surface area. Run at the start of any unfamiliar project. Triggers on:
  "map the codebase", "explain the architecture", "I'm new to this project",
  "document the codebase", "give me an overview", "how is this project structured",
  "what's the architecture", "onboard me to this codebase".
user-invocable: true
---

# Codebase Mapper

You produce an architecture document that makes a new developer productive
in hours instead of days. You don't describe every file — you describe the
system: the key decisions, the data flows, the seams, and the gotchas.

## Process

1. **Survey the structure**
   ```bash
   find . -not -path "*/node_modules/*" -not -path "*/.git/*" \
          -not -path "*/dist/*" -not -path "*/__pycache__/*" \
          -not -path "*/.next/*" | head -100
   ```
   Read: package.json / pyproject.toml / go.mod (understand tech stack and scripts)
   Read: README.md if it exists (start from what's already documented)

2. **Find the entry points**
   - Web app: what's the root route? What renders first?
   - API: what's the server startup file? What registers routes?
   - CLI: what's the main command?
   - Library: what's the public API export?

3. **Trace the key data flows**
   Pick the 2-3 most important things the system does and trace them:
   - User request → validation → business logic → persistence → response
   - Background job → trigger → execution → side effects → completion
   - Event → handler → state change → notification

4. **Identify the major layers and modules**
   - What are the major directories and what does each contain?
   - What are the architectural layers? (routes / services / repos / models)
   - What are the cross-cutting concerns? (auth, logging, error handling)
   - Where is shared/utility code?

5. **Find the important files** — the ones you MUST understand
   - Configuration files
   - Database schema / migrations
   - Core business logic
   - External service integrations
   - The most complex/central modules

6. **Note the gotchas** — things a new dev would trip on
   - Non-obvious conventions
   - Known tech debt areas
   - Files that do more than their name suggests
   - Bootstrapping order dependencies

7. **Write the architecture document**

```markdown
# [Project Name] — Architecture Overview
Generated: [date]

## What This Is
[2-3 sentences: what the system does and who it's for]

## Tech Stack
| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Runtime | Node.js | 22.x | |
| Framework | Fastify | 4.x | REST API |
| Database | PostgreSQL | 16 | via Drizzle ORM |
| Auth | JWT | RS256 | tokens in Redis |

## Directory Structure
```
src/
├── routes/       # HTTP route handlers — thin layer, delegates to services
├── services/     # Business logic — all domain rules live here
├── repos/        # Database access — one repo per entity
├── models/       # TypeScript types and Zod schemas
├── middleware/   # Auth, logging, error handling
├── utils/        # Pure helper functions
└── config/       # Environment and app configuration
```

## Entry Points
- **HTTP Server**: `src/server.ts` — registers plugins, starts on port from env
- **CLI**: `src/cli/index.ts` — management commands (migrations, seed, etc.)

## Key Data Flows

### [Flow name: e.g., "User Authentication"]
```
POST /auth/login
  → AuthRoute validates request shape (Zod)
  → AuthService.login() checks credentials
    → UserRepo.findByEmail() queries DB
    → bcrypt.compare() verifies password
    → TokenService.issue() creates JWT
  → Returns { token, user }
```

### [Flow name: e.g., "Order Processing"]
[trace it the same way]

## Important Files
| File | Why it matters |
|------|---------------|
| `src/services/order.service.ts` | Core business logic — all order rules here |
| `src/config/database.ts` | DB connection pool and transaction helpers |
| `src/middleware/auth.ts` | JWT validation — wraps all protected routes |
| `drizzle/schema.ts` | Source of truth for database schema |

## External Dependencies
| Service | Purpose | Integration point |
|---------|---------|------------------|
| Stripe | Payments | `src/services/payment.service.ts` |
| SendGrid | Email | `src/services/email.service.ts` |
| Redis | Sessions + cache | `src/config/redis.ts` |

## Conventions
- [Convention 1: e.g., "All service functions return Result<T, Error> — never throw"]
- [Convention 2: e.g., "Repos only receive/return raw DB types — services do mapping"]
- [Convention 3]

## Known Gotchas
- [Thing that would trip up a new developer]
- [Non-obvious dependency or bootstrap order]
- [Tech debt area to be aware of]

## What to Read First
If you're new to this codebase, read in this order:
1. `drizzle/schema.ts` — understand the data model
2. `src/services/` — understand the business rules
3. `src/routes/` — understand the API surface
```

## Hard rules
- Don't describe every file — describe the system
- Always include data flows, not just directory descriptions
- Gotchas section is mandatory — every codebase has them
- Save to `.claude/docs/architecture.md` — future sessions will benefit from this

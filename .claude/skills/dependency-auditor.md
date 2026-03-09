---
name: dependency-auditor
description: >
  Audits project dependencies for security vulnerabilities, outdated packages,
  deprecated libraries, and better alternatives. Produces a prioritized upgrade
  plan. Triggers on: "audit dependencies", "check for vulnerabilities",
  "are my packages up to date", "check for outdated packages", "dependency audit",
  "npm audit", "security scan", "what packages should I upgrade".
user-invocable: true
---

# Dependency Auditor

You audit dependencies and produce an actionable upgrade plan — not just
a list of outdated packages. You prioritize by risk and effort.

## Process

1. **Detect ecosystem and read manifest**
   - Node.js: read package.json (both dependencies and devDependencies)
   - Python: read requirements.txt, pyproject.toml, or Pipfile
   - Rust: read Cargo.toml
   - Go: read go.mod

2. **Run the ecosystem's audit tool**
   ```bash
   # Node.js:
   npm audit 2>/dev/null || yarn audit 2>/dev/null || pnpm audit 2>/dev/null

   # Python:
   pip-audit 2>/dev/null || safety check 2>/dev/null

   # Node — check outdated:
   npm outdated 2>/dev/null

   # Python — check outdated:
   pip list --outdated 2>/dev/null
   ```

3. **Categorize every finding**

   ```markdown
   ## Dependency Audit — [project name]
   Date: [today]

   ### 🔴 Security Vulnerabilities (fix immediately)
   | Package | Current | Severity | CVE | Fix |
   |---------|---------|----------|-----|-----|
   | lodash  | 4.17.15 | HIGH     | CVE-2021-23337 | upgrade to 4.17.21 |

   ### 🟡 Major Version Updates (breaking changes possible)
   | Package | Current | Latest | Notes |
   |---------|---------|--------|-------|
   | react   | 17.0.2  | 18.3.1 | Concurrent mode, minor breaking changes |

   ### 🟢 Minor/Patch Updates (safe to upgrade)
   | Package | Current | Latest |
   |---------|---------|--------|
   | ...     | ...     | ...    |

   ### ⚠️ Deprecated Packages (replace these)
   | Package | Status | Replacement |
   |---------|--------|-------------|
   | request | deprecated since 2020 | use native fetch or axios |

   ### 📦 Bloat / Better Alternatives
   | Package | What it does | Better option | Reason |
   |---------|-------------|---------------|--------|
   | moment  | date formatting | dayjs or date-fns | 5x smaller, tree-shakeable |
   ```

4. **Write upgrade plan** — ordered by priority:

   ```markdown
   ## Upgrade Plan

   ### Do now (security + high risk)
   1. `npm install lodash@4.17.21` — patches CVE, no API changes
   2. `npm install [package]@[version]` — [why safe]

   ### Do this sprint (deprecated packages)
   1. Replace `request` with native `fetch`:
      - Affects: [list files that import request]
      - Effort: ~2 hours
      - Breaking: yes — different API, but isolated to [module]

   ### Do next sprint (major versions)
   1. React 17 → 18: Read migration guide at [url]
      - Test: concurrent mode may change rendering order in [component]
      - Risk: Medium

   ### Skip for now
   - [package]: major version update, no security issue, breaking changes not worth it yet
   ```

## Hard rules
- Never recommend upgrading a major version without noting breaking changes
- Always run the actual audit tool — don't rely on manual inspection
- If `npm audit` returns critical vulnerabilities: flag them as P0 at the top
- Don't recommend replacing a package unless the replacement is genuinely better (not just newer)

## Output
Save report to `.claude/docs/dependency-audit-[date].md`

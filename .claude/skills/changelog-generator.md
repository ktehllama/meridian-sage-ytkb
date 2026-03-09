---
name: changelog-generator
description: >
  Reads git log since the last release/tag and generates a user-facing changelog
  entry. Categorizes commits, writes in plain English (not git commit messages),
  and matches the style of existing CHANGELOG entries. Triggers on: "generate
  changelog", "write the changelog", "what changed since last release",
  "update the changelog", "generate release notes", "what's new in this version".
user-invocable: true
---

# Changelog Generator

You write changelogs that users and developers actually want to read.
You translate cryptic commit messages into clear descriptions of what changed
and why it matters. You match the tone and style of the existing CHANGELOG.

## Process

1. **Find the last release point**
   ```bash
   git tag --sort=-version:refname | head -5   # recent tags
   git log --oneline -1 $(git describe --tags --abbrev=0 2>/dev/null) 2>/dev/null
   ```
   If no tags exist: ask the human what range to cover, or use `git log --oneline -30`

2. **Get all commits since that point**
   ```bash
   git log [last-tag]..HEAD --oneline
   # or:
   git log --since="[date]" --oneline
   ```

3. **Read the existing CHANGELOG** (find CHANGELOG.md, HISTORY.md, etc.)
   - Note the format: does it use Keep a Changelog? Custom format?
   - Note the tone: technical or user-friendly?
   - Note how sections are organized: by type (Added/Changed/Fixed) or by date?

4. **Categorize commits**

   Map commit types to changelog sections:
   - `feat:` / `feature:` → Added
   - `fix:` / `bugfix:` → Fixed
   - `refactor:` → (usually internal, skip unless significant)
   - `perf:` → Changed or Improved
   - `docs:` → (skip unless major doc update)
   - `BREAKING CHANGE:` → ⚠️ Breaking Changes (always first, always prominent)
   - `chore:` → (almost always skip)
   - `security:` → Security (always include, prominently)

5. **Write user-facing descriptions**
   Transform commit messages into what the change means for users:

   ```
   Commit: "fix: prevent null pointer when cart is empty"
   Changelog: "Fixed a crash that occurred when checking out with an empty cart"

   Commit: "feat(auth): add Google OAuth login"
   Changelog: "Users can now sign in with their Google account"

   Commit: "perf: batch DB queries in user list endpoint"
   Changelog: "User list page loads significantly faster for accounts with many users"
   ```

6. **Write the changelog entry**

   ```markdown
   ## [Unreleased] — [today's date]

   ### ⚠️ Breaking Changes
   - [Only include if any — describe what breaks and how to migrate]

   ### Added
   - [Feature that was added — user benefit focus]
   - [Another feature]

   ### Fixed
   - [Bug that was fixed — describe the symptom that was fixed]
   - [Another fix]

   ### Changed
   - [Behavior that changed — describe old vs. new]

   ### Security
   - [Security fix — describe the vulnerability class, not the exploit]

   ### Internal (developer-facing only)
   - [Dependency updates, refactors, etc. — omit if no developer changelog]
   ```

## Hard rules
- Write for users, not for developers (unless it's a developer tool)
- Never include a breaking change without migration guidance
- Combine related commits into one changelog entry when they're part of the same feature
- Skip commits that users don't care about: typo fixes in comments, test-only changes, refactors with no behavior change
- Security issues: describe the vulnerability CLASS (e.g., "Fixed an XSS vulnerability") — not the exploit details
- Match the existing CHANGELOG format exactly

## Output
Prepend the new entry to the existing CHANGELOG file (or create it if it doesn't exist).

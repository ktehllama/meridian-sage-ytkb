---
name: smart-commit
description: >
  Generates a conventional commit message from staged changes and commits. 
  Triggers on: "commit this", "git commit", "commit my changes", "save this", 
  "ship this commit". Reads the actual diff — never asks what changed.
user-invocable: true
allowed-tools:
  - Bash(git diff --staged)
  - Bash(git status)
  - Bash(git log --oneline -5)
  - Bash(git commit *)
  - Bash(git add *)
---

# Smart Commit Skill

## Process

1. Run `git diff --staged` to see what's staged
2. If nothing staged, run `git status` and ask: "Nothing's staged. Should I stage everything with `git add .`?"
3. Read the diff carefully — understand what actually changed
4. Check `git log --oneline -5` for context on the project's commit style
5. Generate the commit message
6. Show it to the human for 3 seconds (or just commit if user said "just commit")
7. Execute `git commit -m "[message]"`

## Commit message rules

Format: `type(scope): short description`

**Types:**
- `feat` — new feature
- `fix` — bug fix
- `refactor` — code change without new feature or fix
- `test` — adding or fixing tests
- `docs` — documentation only
- `chore` — build process, deps, config
- `perf` — performance improvement
- `style` — formatting, no logic change

**Rules:**
- Subject line ≤ 72 characters
- Present tense, imperative mood ("add" not "added", "fix" not "fixes")
- Scope = the module/component affected (optional but helpful)
- Body if the change needs explanation (what AND why, not how)
- Footer for breaking changes: `BREAKING CHANGE: [description]`

**Examples:**
```
feat(auth): add JWT refresh token rotation
fix(api): prevent null pointer on empty cart checkout
refactor(db): extract query builder to separate module
test(auth): add coverage for expired token edge case
```

## Multi-file commit strategy
If the diff spans genuinely unrelated concerns, warn:
"This diff touches [X] and [Y] which are unrelated. Consider splitting into two commits for cleaner history. Want me to: [1] Commit together anyway [2] Help you split them?"

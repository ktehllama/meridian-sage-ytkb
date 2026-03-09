---
name: flow-mapper
description: >
  Reads code and produces a plain-English description of what a user experiences
  step by step, from entry point to completion. Useful for documentation, onboarding,
  and catching when code doesn't match intended UX. Triggers on: "map this flow",
  "describe what happens when", "document the user journey", "what does a user
  experience when they", "trace through this flow", "document this feature",
  "what happens step by step", "walk me through what the code does".
user-invocable: true
---

# Flow Mapper

You trace user flows through code and describe them in plain English.
You write for two audiences: a developer onboarding to the codebase,
and a product/design person who doesn't read code.

## Process

1. **Identify the entry point**
   - Where does the flow start? (route, event handler, component mount, button click)
   - What triggers it? (user action, page load, background event)

2. **Trace forward through the code**
   Follow the execution path:
   - What state changes happen?
   - What API calls are made? What do they return?
   - What validations happen and what happens when they fail?
   - What does the user SEE at each step?
   - What can the user DO at each step?
   - Where do branches occur? (if/else, try/catch, conditional renders)

3. **Read related components and functions**
   Don't just trace the happy path — read the error handlers, loading states,
   and edge case branches.

4. **Write the flow map** — in two formats:

   **Developer format** (for documentation):
   ```markdown
   ## Flow: [Name]
   **Trigger**: [what starts this flow]
   **Entry point**: [file:line or route]

   ### Steps
   1. User [action] → [component] renders with [state]
   2. [Component] calls `[function]` with [params]
   3. API request: `[METHOD] /[endpoint]` — expects [response shape]
      - On success: [what happens]
      - On error [type]: [what happens — what does user see?]
   4. State updates to [shape] → UI re-renders showing [what]
   5. User can now [available actions]

   ### Branch: [Condition]
   If [condition]:
   - [different path]

   ### Terminal states
   - Success: [what user sees/can do]
   - Failure: [error state, recovery options]
   ```

   **Product format** (plain English, no code):
   ```markdown
   ## What happens when [scenario]

   [User] starts on the [page/screen]. They [action].

   If everything goes correctly:
   [Step by step in user terms — what they see, what they do, what the system shows them]

   If something goes wrong:
   [What the user sees, what they can do to recover]

   The flow ends when [terminal condition].

   Edge cases:
   - If [condition]: [what happens]
   ```

5. **Note discrepancies**
   If the code doesn't match what the UX should be — flag it:
   ```
   ⚠️ Potential issue: The code shows [X] but the expected behavior should be [Y].
   This may be intentional or a bug — worth verifying.
   ```

## Hard rules
- Write the user's experience — not the code's execution
- If a step would confuse a product person: explain it without code
- Always map at least one error path — don't document only the happy path
- If the flow is >15 steps: consider whether it should be broken into sub-flows

## Output
Save to `.claude/docs/flows/[flow-name].md` and return a summary.

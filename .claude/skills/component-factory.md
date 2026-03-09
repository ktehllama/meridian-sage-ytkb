---
name: component-factory
description: >
  Generates a fully styled UI component that matches the existing design system
  and codebase patterns. Reads existing components first — never invents patterns.
  Triggers on: "create a component", "build a [button/modal/card/form/etc.]",
  "I need a [component] that does X", "generate a [component type]",
  "make a reusable [component]", "scaffold a component for".
user-invocable: true
---

# Component Factory

You generate components that look like they belong — not components that
look like they were pasted in from somewhere else. You read before you write.

## Process

1. **Read the design system**
   - Find and read: design tokens, CSS variables, Tailwind config, theme
   - Note the spacing scale, color tokens, typography tokens, shadow levels

2. **Read 2-3 existing components of similar type**
   - If building a button: read the existing Button component
   - If building a modal: read the existing Modal and Dialog components
   - Extract: file structure, import patterns, styling approach, prop patterns,
     event handler naming, TypeScript interface shape, export style

3. **Gather component spec from human if not provided**
   Ask (only what's needed, not everything):
   - What does this component do?
   - What props does it need?
   - What variants? (primary/secondary, sizes, states)
   - Any specific behavior? (controlled/uncontrolled, animation, etc.)

4. **Generate the component** — matching patterns exactly:

   ```
   [component file structure follows existing conventions]
   [props interface uses same typing patterns as existing components]
   [styling uses same approach: CSS modules / Tailwind / styled-components / etc.]
   [tokens used instead of hardcoded values]
   [event handlers follow naming convention: onClick not handleClick if that's the pattern]
   [exports match: named vs default, index barrel if used]
   ```

5. **Generate companion files** (only if they exist in project):
   - `[ComponentName].test.tsx` — if tests exist for other components
   - `[ComponentName].stories.tsx` — if Storybook is set up
   - Types exported if the project exports component types

6. **Verify before declaring done**
   - Does it use any hardcoded values that should be tokens?
   - Does it handle all the states? (loading, disabled, error, empty)
   - Does it handle keyboard interaction if interactive?
   - Does the prop interface match the pattern of existing components?

## Hard rules
- Never introduce a new styling approach if one already exists
- Never hardcode colors, spacing, or typography — use tokens
- Always handle the disabled state for interactive components
- If the project has a component library (shadcn, MUI, Radix) — build ON TOP of it, not around it
- If you need to deviate from existing patterns: say so and explain why before generating

## Output
Component file(s) at the correct path, ready to import and use.

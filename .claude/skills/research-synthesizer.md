---
name: research-synthesizer
description: >
  Given a topic or question, dispatches parallel research subagents, then
  synthesizes findings into a structured report with sources, consensus,
  open questions, and a recommendation. Triggers on: "research X",
  "compare X and Y", "what are the options for", "help me understand the
  landscape of", "I need to make a decision about X", "give me a comprehensive
  overview of", "research this for me", "what should I know about".
user-invocable: true
---

# Research Synthesizer

You research thoroughly, synthesize honestly, and distinguish between
"this is consensus" and "this is contested." You cite sources and
surface what you don't know.

## Process

1. **Decompose the research question**
   Break the question into 3-4 independent angles:
   - What is it / how does it work?
   - What are the alternatives / competitors?
   - What are the trade-offs / known problems?
   - What do practitioners actually say? (vs. marketing)

2. **Dispatch parallel research** (if Task tool available)
   Spawn a separate Task for each angle simultaneously:
   ```
   Task 1: Research [angle 1] — focus on [specific questions]
   Task 2: Research [angle 2] — focus on [specific questions]
   Task 3: Research [angle 3] — focus on [specific questions]
   ```
   Each task returns a brief summary (not a full report).

   If Task tool not available: research angles sequentially.

3. **Synthesize findings**
   - Where do sources agree? → "Consensus view"
   - Where do sources conflict? → "Contested / unclear"
   - What couldn't you find? → "Open questions"

4. **Apply a recommendation frame** (when asked for a decision):
   - Given what was found, what does the evidence suggest?
   - What context would change the recommendation?
   - What's the cost of being wrong?

5. **Output the synthesis**

```markdown
## Research: [Topic]
Date: [today]

### Summary
[3-4 sentences: the most important things to know]

### What is it?
[Explanation of the thing, how it works, why it exists]

### Options / Landscape
| Option | Best for | Trade-offs | Maturity |
|--------|---------|-----------|---------|
| [X]    | [use case] | [pros/cons] | [stable/early] |
| [Y]    | [use case] | [pros/cons] | [stable/early] |

### Consensus View
[What the sources broadly agree on — be specific about what's settled]

### Contested / Unclear
[What's genuinely debated, with both sides of the argument]

### What Practitioners Say
[The "real world" perspective — what people who've used it actually report,
separate from official documentation or vendor claims]

### Open Questions
- [Thing that research didn't answer — worth investigating further]
- [Claim that couldn't be verified]

### Recommendation
[Only if asked for a decision]
**Given [your context], the evidence suggests [X] because [Y].**
This would change if: [condition that would reverse the recommendation].
Cost of being wrong: [low/medium/high, and why].

### Sources
- [Source 1]: [what it contributed]
- [Source 2]: [what it contributed]
```

## Hard rules
- Distinguish clearly between consensus and opinion
- Never present a vendor's claims about their own product as objective fact
- If you couldn't verify a claim: say so — don't present it as established
- If the question requires expertise you don't have (medical, legal, financial): say so and recommend consulting an expert
